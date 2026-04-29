"""Vegetation indices computation with health stress analysis."""
import numpy as np
from typing import NamedTuple


class IndexStats(NamedTuple):
    """Statistics for a vegetation index."""
    min: float
    max: float
    mean: float
    std: float
    median: float
    count_valid: int


class NDREAnalysis(NamedTuple):
    """Complete NDRE analysis including stress metrics."""
    ndre_array: np.ndarray
    stats: IndexStats
    stress_percentage: float
    stress_threshold: float
    healthy_count: int
    stressed_count: int


def compute_ndre(nir: np.ndarray, red_edge: np.ndarray) -> np.ndarray:
    """
    Compute Normalized Difference Red Edge (NDRE) index.
    
    Formula: NDRE = (NIR - Red Edge) / (NIR + Red Edge)
    
    Division by zero is handled safely: returns 0.0 where denominator is 0.
    
    Args:
        nir: NIR band array (must be float type)
        red_edge: Red Edge band array (must be float type)
        
    Returns:
        NDRE index array (float32) with values in range [-1.0, 1.0]
        
    Notes:
        - Values range from -1 (low vegetation) to 1 (high vegetation)
        - 0 indicates no vegetation signal
        - NaN values are preserved from input
    """
    # Ensure float type for safe division
    nir = np.asarray(nir, dtype=np.float32)
    red_edge = np.asarray(red_edge, dtype=np.float32)
    
    # Compute denominator
    denom = nir + red_edge
    
    # Compute NDRE with safe division (avoid divide by zero warning)
    # Where denom is 0, result is 0.0
    ndre = np.divide(
        nir - red_edge,
        denom,
        out=np.zeros_like(nir),
        where=denom != 0
    )
    
    return ndre.astype(np.float32)


def compute_ndvi(nir: np.ndarray, red: np.ndarray) -> np.ndarray:
    """
    Compute Normalized Difference Vegetation Index (NDVI).
    
    Formula: NDVI = (NIR - Red) / (NIR + Red)
    
    Args:
        nir: NIR band array
        red: Red band array
        
    Returns:
        NDVI index array (float32)
    """
    nir = np.asarray(nir, dtype=np.float32)
    red = np.asarray(red, dtype=np.float32)
    
    denom = nir + red
    ndvi = np.divide(
        nir - red,
        denom,
        out=np.zeros_like(nir),
        where=denom != 0
    )
    
    return ndvi.astype(np.float32)


def get_index_stats(index_array: np.ndarray) -> IndexStats:
    """
    Compute comprehensive statistics for a vegetation index.
    
    Args:
        index_array: 2D array of index values
        
    Returns:
        IndexStats with min, max, mean, std, median, and valid count
    """
    # Filter out NaN and infinite values
    valid = index_array[np.isfinite(index_array)]
    
    if valid.size == 0:
        raise ValueError("No valid values in index array")
    
    return IndexStats(
        min=round(float(np.min(valid)), 4),
        max=round(float(np.max(valid)), 4),
        mean=round(float(np.mean(valid)), 4),
        std=round(float(np.std(valid)), 4),
        median=round(float(np.median(valid)), 4),
        count_valid=int(valid.size)
    )


def compute_stress_percentage(
    index_array: np.ndarray,
    threshold: float = 0.2
) -> tuple[float, int, int]:
    """
    Compute percentage of pixels below stress threshold.
    
    Args:
        index_array: 2D array of index values
        threshold: NDRE threshold below which plant is considered stressed
        
    Returns:
        Tuple of (stress_percentage, stressed_count, healthy_count)
    """
    # Count valid pixels
    valid = index_array[np.isfinite(index_array)]
    total = valid.size
    
    if total == 0:
        return 0.0, 0, 0
    
    # Count stressed pixels (below threshold)
    stressed = np.sum(valid < threshold)
    healthy = total - stressed
    
    stress_pct = round(float(stressed / total * 100), 2)
    
    return stress_pct, int(stressed), int(healthy)


def calibrate_stress_threshold(
    index_array: np.ndarray,
    fallback_threshold: float = 0.2,
    min_threshold: float = -0.1,
    max_threshold: float = 0.4,
) -> float:
    """Estimate a per-scan stress threshold from NDRE distribution.

    This avoids using a fixed percentile target (which can force similar
    stress percentages across many scans).
    """
    valid = index_array[np.isfinite(index_array)]
    if valid.size < 128:
        return float(fallback_threshold)

    p10, p25, p50, p75, p90 = np.percentile(valid, [10, 25, 50, 75, 90])
    iqr = float(p75 - p25)

    # If NDRE spread is tiny, prefer the user threshold to avoid noisy jumps.
    if iqr < 0.015:
        suggested = float(fallback_threshold)
    else:
        # Distribution-aware baseline: move below median by a fraction of IQR.
        robust_baseline = float(p50 - 0.35 * iqr)

        # Lightly anchor to the user threshold so behavior remains predictable.
        blend = 0.65 * robust_baseline + 0.35 * float(fallback_threshold)

        # Keep threshold inside central NDRE range for the scan.
        lower_bound = float(p10 - 0.05 * iqr)
        upper_bound = float(p90 + 0.05 * iqr)
        suggested = min(max(blend, lower_bound), upper_bound)

    suggested = max(min_threshold, min(max_threshold, suggested))
    return round(float(suggested), 4)


def analyze_ndre(
    nir: np.ndarray,
    red_edge: np.ndarray,
    stress_threshold: float = 0.2,
    auto_calibrate_threshold: bool = False,
) -> NDREAnalysis:
    """
    Complete NDRE analysis: compute index and all statistics.
    
    This is the main production function that combines NDRE computation
    with comprehensive health stress analysis.
    
    Args:
        nir: NIR band array
        red_edge: Red Edge band array
        stress_threshold: NDRE threshold for stress classification (default: 0.2)
        
    Returns:
        NDREAnalysis with index array, statistics, and stress metrics
        
    Example:
        analysis = analyze_ndre(nir_band, red_edge_band, stress_threshold=0.2)
        
        print(f"Mean NDRE: {analysis.stats.mean}")
        print(f"Stressed: {analysis.stress_percentage}%")
        print(f"Healthy pixels: {analysis.healthy_count}")
        print(f"Stressed pixels: {analysis.stressed_count}")
    """
    # Compute NDRE with safe division
    ndre = compute_ndre(nir, red_edge)
    
    # Compute statistics
    stats = get_index_stats(ndre)
    
    effective_threshold = (
        calibrate_stress_threshold(ndre, fallback_threshold=stress_threshold)
        if auto_calibrate_threshold
        else stress_threshold
    )

    # Compute stress metrics
    stress_pct, stressed_count, healthy_count = compute_stress_percentage(
        ndre,
        threshold=effective_threshold
    )
    
    return NDREAnalysis(
        ndre_array=ndre,
        stats=stats,
        stress_percentage=stress_pct,
        stress_threshold=float(effective_threshold),
        healthy_count=healthy_count,
        stressed_count=stressed_count
    )


def classify_health_status(stress_percentage: float, confidence_threshold: float = 25.0) -> str:
    """
    Classify plant health status based on stress percentage.
    
    Args:
        stress_percentage: Percentage of pixels below stress threshold
        confidence_threshold: Threshold for confident classification (default: 25%)
        
    Returns:
        Health status string: "healthy", "at_risk", "stressed", or "unknown"
    """
    if stress_percentage <= confidence_threshold:
        return "healthy"
    elif stress_percentage <= 50.0:
        return "at_risk"
    else:
        return "stressed"


def compute_vegetation_vigor(ndre_stats: IndexStats) -> float:
    """
    Compute overall vegetation vigor score (0-100).
    
    Based on NDRE mean value and distribution.
    
    Args:
        ndre_stats: Index statistics
        
    Returns:
        Vigor score from 0 (low) to 100 (high)
    """
    # Map NDRE mean (-1 to 1) to vigor score (0 to 100)
    # Shift from [-1, 1] to [0, 2], then scale to [0, 100]
    vigor = (ndre_stats.mean + 1.0) / 2.0 * 100.0
    return round(max(0, min(100, vigor)), 2)
