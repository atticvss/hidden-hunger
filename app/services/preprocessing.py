"""Image preprocessing and validation for hyperspectral NPY cubes."""
import io
import base64
from typing import NamedTuple
import numpy as np
from PIL import Image
import matplotlib.cm as cm
import matplotlib.colors as mcolors
from app.errors import RasterReadError, UnsupportedBandIndexError


class CubeMetadata(NamedTuple):
    """Metadata information about a hyperspectral cube."""
    height: int
    width: int
    total_bands: int
    dtype: str
    source_format: str


class AutoBandSelection(NamedTuple):
    """Auto-selected NDRE band pair with diagnostics."""
    nir_band: int
    red_edge_band: int
    score: float
    estimated_stress_percentage: float
    estimated_ndre_std: float
    estimated_ndre_spread: float


class HeatmapRange(NamedTuple):
    """Resolved visualization range for index heatmaps."""
    vmin: float
    vmax: float


class HyperspectralCube:
    """Container for hyperspectral image data."""
    
    def __init__(self, data: np.ndarray, metadata: CubeMetadata):
        """
        Initialize hyperspectral cube.
        
        Args:
            data: 3D array (bands, height, width)
            metadata: CubeMetadata with image information
        """
        self.data = data
        self.metadata = metadata
        self.bands_loaded = list(range(1, metadata.total_bands + 1))
    
    @property
    def shape(self) -> tuple:
        """Get shape of cube (bands, height, width)."""
        return self.data.shape
    
    def get_band(self, band_index: int, dtype: type = np.float32) -> np.ndarray:
        """
        Safely extract a specific band.
        
        Args:
            band_index: Band number (1-based indexing)
            dtype: Output data type (default: float32)
            
        Returns:
            2D array of band data
            
        Raises:
            ValueError: If band index is out of range
        """
        if band_index < 1 or band_index > self.metadata.total_bands:
            raise UnsupportedBandIndexError(
                f"Band {band_index} out of range. "
                f"File has {self.metadata.total_bands} bands.",
                details={
                    "requested_band": band_index,
                    "total_bands": self.metadata.total_bands,
                },
            )
        
        # Convert to 0-based indexing
        band_data = self.data[band_index - 1, :, :]
        return band_data.astype(dtype)


def validate_npy_file(filename: str) -> bool:
    """
    Validate that file is an NPY file.
    
    Args:
        filename: Filename to validate
        
    Returns:
        True if file is NPY format
    """
    return filename.lower().endswith(".npy")


def _normalize_cube_shape(data: np.ndarray) -> np.ndarray:
    """Normalize cube to (bands, height, width).

    Supports both common layouts:
    - (bands, height, width)
    - (height, width, bands)
    """
    if data.ndim != 3:
        raise RasterReadError(
            message="Invalid NPY shape. Expected 3D hyperspectral cube.",
            details={"shape": list(data.shape)},
        )

    bands_first = data.shape[0]
    bands_last = data.shape[-1]

    # Heuristic: the spectral axis is usually the smallest axis in HSI cubes.
    if bands_first <= data.shape[1] and bands_first <= data.shape[2]:
        cube = data
    elif bands_last <= data.shape[0] and bands_last <= data.shape[1]:
        cube = np.transpose(data, (2, 0, 1))
    else:
        inferred_axis = _infer_band_axis_by_correlation(data)
        if inferred_axis is None:
            raise RasterReadError(
                message="Unable to infer band axis from NPY cube shape.",
                details={"shape": list(data.shape)},
            )
        cube = np.moveaxis(data, inferred_axis, 0)

    return np.asarray(cube, dtype=np.float32)


def _infer_band_axis_by_correlation(data: np.ndarray) -> int | None:
    """Infer spectral axis by maximizing adjacent-band correlation."""
    best_axis = None
    best_score = -np.inf

    for axis in (0, 1, 2):
        moved = np.moveaxis(data, axis, 0)
        bands = moved.shape[0]
        if bands < 3:
            continue

        # Downsample spatially to keep the check fast on large cubes.
        flat = moved[:, ::4, ::4].reshape(bands, -1).astype(np.float32)
        pair_count = min(10, bands - 1)
        if pair_count <= 0:
            continue

        sample_indices = np.linspace(0, bands - 2, num=pair_count, dtype=int)
        correlations: list[float] = []

        for i in sample_indices:
            a = flat[i]
            b = flat[i + 1]

            mask = np.isfinite(a) & np.isfinite(b)
            if np.sum(mask) < 16:
                continue

            a = a[mask]
            b = b[mask]
            a_std = float(np.std(a))
            b_std = float(np.std(b))
            if a_std < 1e-8 or b_std < 1e-8:
                continue

            corr = float(np.corrcoef(a, b)[0, 1])
            if np.isfinite(corr):
                correlations.append(corr)

        if not correlations:
            continue

        score = float(np.mean(correlations))
        if score > best_score:
            best_score = score
            best_axis = axis

    return best_axis


def auto_select_ndre_bands(
    cube: HyperspectralCube,
    stress_threshold: float = 0.2,
    max_candidates: int = 18,
) -> AutoBandSelection:
    """Pick a robust NIR/RedEdge pair by maximizing NDRE signal quality."""
    bands = cube.metadata.total_bands
    if bands < 6:
        raise UnsupportedBandIndexError(
            message="Auto band selection requires at least 6 bands.",
            details={"total_bands": bands},
        )

    data = cube.data[:, ::4, ::4]
    candidate_idx = np.linspace(0, bands - 1, num=min(max_candidates, bands), dtype=int)
    candidate_idx = np.unique(candidate_idx)

    best: AutoBandSelection | None = None

    for nir_i in candidate_idx:
        for red_i in candidate_idx:
            if nir_i <= red_i:
                continue
            if (nir_i - red_i) < 4:
                continue

            nir = data[nir_i]
            red = data[red_i]
            denom = nir + red
            ndre = np.divide(nir - red, denom, out=np.zeros_like(nir), where=denom != 0)

            valid = ndre[np.isfinite(ndre)]
            if valid.size < 64:
                continue

            ndre_std = float(np.std(valid))
            q10, q90 = np.percentile(valid, [10, 90])
            spread = float(q90 - q10)
            stress_pct = float(np.mean(valid < stress_threshold) * 100.0)
            balance = max(0.0, 1.0 - abs(stress_pct - 50.0) / 50.0)

            score = (1.8 * ndre_std) + (1.1 * spread) + (0.25 * balance)

            current = AutoBandSelection(
                nir_band=int(nir_i + 1),
                red_edge_band=int(red_i + 1),
                score=round(score, 4),
                estimated_stress_percentage=round(stress_pct, 2),
                estimated_ndre_std=round(ndre_std, 4),
                estimated_ndre_spread=round(spread, 4),
            )

            if best is None or current.score > best.score:
                best = current

    if best is None:
        fallback_nir = min(5, bands)
        fallback_red = max(1, fallback_nir - 1)
        return AutoBandSelection(
            nir_band=fallback_nir,
            red_edge_band=fallback_red,
            score=0.0,
            estimated_stress_percentage=0.0,
            estimated_ndre_std=0.0,
            estimated_ndre_spread=0.0,
        )

    return best


def load_npy_cube(file_contents: bytes) -> tuple[HyperspectralCube, CubeMetadata]:
    """
    Load complete hyperspectral NPY cube into memory.
    
    Args:
        file_contents: Raw NPY file bytes
        
    Returns:
        Tuple of (HyperspectralCube, CubeMetadata)
        
    Raises:
        ValueError: If file is not a valid NPY cube
        MemoryError: If file is too large to load
    """
    try:
        raw = np.load(io.BytesIO(file_contents), allow_pickle=False)
    except Exception as e:
        raise RasterReadError(
            message="Failed to load NPY file.",
            details={"reason": str(e)},
        )

    cube_data = _normalize_cube_shape(np.asarray(raw))
    total_bands, height, width = cube_data.shape

    metadata = CubeMetadata(
        height=int(height),
        width=int(width),
        total_bands=int(total_bands),
        dtype=str(cube_data.dtype),
        source_format="npy",
    )

    return HyperspectralCube(cube_data, metadata), metadata


def read_bands_from_npy(
    file_contents: bytes,
    nir_band: int,
    red_edge_band: int
) -> tuple[np.ndarray, np.ndarray, int, tuple[int, int]]:
    """
    Read specific bands from an NPY cube.
    
    Convenience function that loads cube and extracts specific bands.
    
    Args:
        file_contents: Raw NPY file bytes
        nir_band: Band index for NIR (1-based)
        red_edge_band: Band index for Red Edge (1-based)
        
    Returns:
        Tuple of (nir_array, red_edge_array, total_bands, (height, width))
        
    Raises:
        ValueError: If bands are out of range
    """
    cube, metadata = load_npy_cube(file_contents)
    
    # Validate band indices
    if min(nir_band, red_edge_band) < 1 or max(nir_band, red_edge_band) > metadata.total_bands:
        raise UnsupportedBandIndexError(
            f"File has {metadata.total_bands} bands; "
            f"requested NIR={nir_band}, RedEdge={red_edge_band}.",
            details={
                "nir_band": nir_band,
                "red_edge_band": red_edge_band,
                "total_bands": metadata.total_bands,
            },
        )
    
    # Extract bands safely
    nir = cube.get_band(nir_band, dtype=np.float32)
    red_edge = cube.get_band(red_edge_band, dtype=np.float32)
    
    return nir, red_edge, metadata.total_bands, (metadata.height, metadata.width)


def extract_band(file_contents: bytes, band_index: int, dtype: type = np.float32) -> np.ndarray:
    """
    Extract a single band from NPY cube.
    
    Args:
        file_contents: Raw NPY file bytes
        band_index: Band number (1-based indexing)
        dtype: Output data type (default: float32)
        
    Returns:
        2D array of band data
        
    Raises:
        ValueError: If band index is out of range
    """
    cube, _ = load_npy_cube(file_contents)
    return cube.get_band(band_index, dtype=dtype)


def _normalize_band_for_rgb(
    band: np.ndarray,
    lower_percentile: float = 2.0,
    upper_percentile: float = 98.0,
) -> np.ndarray:
    """Normalize a band into 0-1 range for visualization."""
    band = np.asarray(band, dtype=np.float32)
    valid = band[np.isfinite(band)]
    if valid.size == 0:
        return np.zeros_like(band, dtype=np.float32)

    lo, hi = np.percentile(valid, [lower_percentile, upper_percentile])
    lo = float(lo)
    hi = float(hi)
    if hi - lo < 1e-6:
        return np.zeros_like(band, dtype=np.float32)

    scaled = (band - lo) / (hi - lo)
    return np.clip(scaled, 0.0, 1.0).astype(np.float32)


def _select_preview_bands(total_bands: int, nir_band: int, red_edge_band: int) -> tuple[int, int, int]:
    """Pick three bands for an RGB-style preview (1-based indices)."""
    if total_bands <= 1:
        return (1, 1, 1)
    if total_bands == 2:
        return (2, 1, 1)

    red_band = max(1, min(total_bands, nir_band))
    green_band = max(1, min(total_bands, red_edge_band))
    blue_band = max(1, min(total_bands, red_edge_band - 2))

    if blue_band in (red_band, green_band):
        blue_band = max(1, min(total_bands, red_edge_band + 2))
    if blue_band in (red_band, green_band):
        blue_band = 1 if 1 not in (red_band, green_band) else total_bands

    return (red_band, green_band, blue_band)


def cube_to_rgb_preview_bytes(
    cube: np.ndarray,
    nir_band: int,
    red_edge_band: int,
) -> tuple[bytes, dict[str, int]]:
    """Build a pseudo-RGB preview PNG from a hyperspectral cube."""
    if cube.ndim != 3:
        raise RasterReadError(
            message="Invalid cube shape for preview.",
            details={"shape": list(cube.shape)},
        )

    total_bands = cube.shape[0]
    r_band, g_band, b_band = _select_preview_bands(total_bands, nir_band, red_edge_band)

    r = _normalize_band_for_rgb(cube[r_band - 1])
    g = _normalize_band_for_rgb(cube[g_band - 1])
    b = _normalize_band_for_rgb(cube[b_band - 1])
    rgb = np.stack([r, g, b], axis=-1)

    img = Image.fromarray((rgb * 255.0).astype(np.uint8), mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue(), {"r": r_band, "g": g_band, "b": b_band}


def cube_to_rgb_preview_base64(
    cube: np.ndarray,
    nir_band: int,
    red_edge_band: int,
) -> tuple[str, dict[str, int]]:
    """Return a base64-encoded RGB preview plus band mapping."""
    png_bytes, bands = cube_to_rgb_preview_bytes(cube, nir_band, red_edge_band)
    return base64.b64encode(png_bytes).decode("utf-8"), bands


def array_to_heatmap_base64(
    index_array: np.ndarray,
    vmin: float | None = None,
    vmax: float | None = None,
    cmap: str = "RdYlGn",
    auto_scale: bool = True,
) -> str:
    """
    Convert index array to base64-encoded heatmap image.
    
    Args:
        index_array: 2D array of index values
        vmin: Minimum value for normalization
        vmax: Maximum value for normalization
        cmap: Colormap name (default: RdYlGn for vegetation index)
        
    Returns:
        Base64-encoded PNG image string
    """
    heatmap_range = resolve_heatmap_range(
        index_array,
        vmin=vmin,
        vmax=vmax,
        auto_scale=auto_scale,
    )
    norm = mcolors.Normalize(vmin=heatmap_range.vmin, vmax=heatmap_range.vmax)
    
    # Get colormap (RdYlGn is red-yellow-green, good for vegetation)
    colormap = cm.get_cmap(cmap)
    rgba = colormap(norm(index_array))  # Shape: (H, W, 4) float64
    
    # Convert to uint8
    rgba_uint8 = (rgba * 255).astype(np.uint8)
    
    # Create PIL image and encode
    img = Image.fromarray(rgba_uint8, mode="RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def array_to_heatmap_bytes(
    index_array: np.ndarray,
    vmin: float | None = None,
    vmax: float | None = None,
    cmap: str = "RdYlGn",
    auto_scale: bool = True,
) -> bytes:
    """
    Convert index array to PNG heatmap as bytes.
    
    Args:
        index_array: 2D array of index values
        vmin: Minimum value for normalization
        vmax: Maximum value for normalization
        cmap: Colormap name (default: RdYlGn)
        
    Returns:
        PNG binary data
    """
    heatmap_range = resolve_heatmap_range(
        index_array,
        vmin=vmin,
        vmax=vmax,
        auto_scale=auto_scale,
    )
    norm = mcolors.Normalize(vmin=heatmap_range.vmin, vmax=heatmap_range.vmax)
    
    # Get colormap
    colormap = cm.get_cmap(cmap)
    rgba = colormap(norm(index_array))  # Shape: (H, W, 4) float64
    
    # Convert to uint8
    rgba_uint8 = (rgba * 255).astype(np.uint8)
    
    # Create PIL image and encode
    img = Image.fromarray(rgba_uint8, mode="RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    
    return buf.getvalue()


def resolve_heatmap_range(
    index_array: np.ndarray,
    vmin: float | None = None,
    vmax: float | None = None,
    auto_scale: bool = True,
    lower_percentile: float = 2.0,
    upper_percentile: float = 98.0,
    min_span: float = 0.04,
) -> HeatmapRange:
    """Resolve robust vmin/vmax so heatmaps remain visually informative."""
    if not auto_scale and vmin is not None and vmax is not None and vmin < vmax:
        return HeatmapRange(float(vmin), float(vmax))

    valid = np.asarray(index_array, dtype=np.float32)
    valid = valid[np.isfinite(valid)]
    if valid.size == 0:
        return HeatmapRange(-1.0, 1.0)

    lo, hi = np.percentile(valid, [lower_percentile, upper_percentile])
    lo = float(lo)
    hi = float(hi)
    if hi - lo < min_span:
        center = float(np.median(valid))
        lo = center - (min_span / 2.0)
        hi = center + (min_span / 2.0)

    lo = max(-1.0, lo)
    hi = min(1.0, hi)
    if hi <= lo:
        lo, hi = -1.0, 1.0

    return HeatmapRange(round(lo, 4), round(hi, 4))


def save_ndre_heatmap(
    ndre_array: np.ndarray,
    scan_id: int,
    include_base64: bool = False,
    vmin: float | None = None,
    vmax: float | None = None,
    cmap: str = "RdYlGn",
    auto_scale: bool = True,
) -> tuple[str, str | None]:
    """
    Generate NDRE heatmap, save to disk with UUID naming, and optionally return base64 preview.
    
    This helper function generates a matplotlib heatmap visualization, saves it as a PNG file
    to the outputs/heatmaps/ directory using UUID-based naming for collision avoidance, and
    optionally returns a base64-encoded preview for API responses.
    
    Args:
        ndre_array: 2D array of NDRE values
        scan_id: ID of the scan (stored in filename for association)
        include_base64: If True, also return base64-encoded preview (default: False)
        vmin: Minimum value for normalization (default: -1.0)
        vmax: Maximum value for normalization (default: 1.0)
        cmap: Colormap name (default: RdYlGn for vegetation)
        
    Returns:
        Tuple of (file_path, base64_string_or_None)
        - file_path: Relative path where heatmap was saved (e.g., "outputs/heatmaps/scan_1_abc123.png")
        - base64_string: Base64-encoded PNG data if include_base64=True, else None
        
    Raises:
        IOError: If file cannot be written
        
    Example:
        # Save heatmap with base64 preview for API response
        file_path, preview_b64 = save_ndre_heatmap(
            ndre_array=analysis.ndre_array,
            scan_id=db_scan.id,
            include_base64=True
        )
        
        # Now file_path can be stored in database
        # and preview_b64 can be sent to frontend
    """
    from app.services import storage
    
    # Generate heatmap as PNG bytes
    heatmap_bytes = array_to_heatmap_bytes(
        ndre_array,
        vmin=vmin,
        vmax=vmax,
        cmap=cmap,
        auto_scale=auto_scale,
    )
    
    # Save to disk with UUID-based naming
    storage_file = storage.save_heatmap(heatmap_bytes, scan_id, format="png")
    
    # Generate base64 preview if requested
    base64_preview = None
    if include_base64:
        base64_preview = base64.b64encode(heatmap_bytes).decode("utf-8")
    
    return storage_file.relative_path, base64_preview
