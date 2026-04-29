"""
SERVICE MODULES DOCUMENTATION
==============================

OVERVIEW
========

Two core service modules handle the hyperspectral image processing pipeline:

1. app/services/preprocessing.py - TIFF file loading and visualization
2. app/services/indices.py - Vegetation indices computation and analysis


SERVICE 1: PREPROCESSING.PY
===========================

This module handles all TIFF file I/O operations and rasterio integration.

Key Classes:
  - TIFFMetadata: Container for TIFF file metadata
  - HyperspectralCube: Wrapper for 3D spectral data with safe band extraction

Key Functions:

  validate_tiff_file(filename: str) -> bool
    Validate that filename is a TIFF file
    Parameters:
      - filename: Filename to validate
    Returns: True if TIFF extension, False otherwise

  load_tiff_cube(file_contents: bytes) -> (HyperspectralCube, TIFFMetadata)
    Load complete TIFF cube into memory
    Reads all bands into single 3D array
    Returns:
      - HyperspectralCube: Wrapper with safe band access
      - TIFFMetadata: File information (height, width, bands, dtype, CRS)
    Raises:
      - ValueError: If file is invalid TIFF

  read_bands_from_tiff(file_contents: bytes, nir_band: int, red_edge_band: int)
    -> (ndarray, ndarray, int, tuple)
    Convenience function to load specific bands
    Returns:
      - nir_array: NIR band as float32
      - red_edge_array: Red Edge band as float32
      - total_bands: Count of all bands
      - (height, width): Image dimensions
    Raises:
      - ValueError: If bands out of range

  extract_band(file_contents: bytes, band_index: int, dtype: type) -> ndarray
    Extract single band from TIFF
    Parameters:
      - file_contents: Raw TIFF bytes
      - band_index: Band number (1-based)
      - dtype: Output type (default: float32)
    Returns:
      - 2D array of band data
    Raises:
      - ValueError: If band index invalid

  array_to_heatmap_base64(index_array: ndarray, vmin: float, vmax: float) -> str
    Convert index array to base64-encoded PNG
    Parameters:
      - index_array: 2D index values (e.g., NDRE)
      - vmin: Normalization minimum (default: -1.0)
      - vmax: Normalization maximum (default: 1.0)
    Returns:
      - Base64-encoded PNG string

  array_to_heatmap_bytes(index_array: ndarray, ...) -> bytes
    Convert index array to PNG bytes
    Parameters same as array_to_heatmap_base64
    Returns:
      - PNG binary data


CLASS: HyperspectralCube
========================

Container for multi-band image data with safe band extraction.

Constructor:
  HyperspectralCube(data: ndarray, metadata: TIFFMetadata)
    data: 3D array (bands, height, width)
    metadata: TIFFMetadata object

Properties:
  .data: 3D array (bands, height, width)
  .metadata: TIFFMetadata
  .bands_loaded: List of available band indices
  .shape: Tuple (bands, height, width)

Methods:
  get_band(band_index: int, dtype: type) -> ndarray
    Safely extract specific band
    Parameters:
      - band_index: Band number (1-based)
      - dtype: Output type (default: float32)
    Returns:
      - 2D array of band data
    Raises:
      - ValueError: If band out of range


SERVICE 2: INDICES.PY
=====================

This module computes vegetation indices and plant health metrics.

Key Functions:

  compute_ndre(nir: ndarray, red_edge: ndarray) -> ndarray
    Compute Normalized Difference Red Edge index
    Formula: NDRE = (NIR - Red Edge) / (NIR + Red Edge)
    
    Division by zero handled safely (returns 0 where denominator = 0)
    
    Parameters:
      - nir: NIR band array
      - red_edge: Red Edge band array
    Returns:
      - NDRE array (float32), values in [-1.0, 1.0]

  compute_ndvi(nir: ndarray, red: ndarray) -> ndarray
    Compute Normalized Difference Vegetation Index
    Formula: NDVI = (NIR - Red) / (NIR + Red)
    
    Parameters:
      - nir: NIR band array
      - red: Red band array
    Returns:
      - NDVI array (float32)

  get_index_stats(index_array: ndarray) -> IndexStats
    Compute comprehensive statistics for an index
    Automatically filters NaN/Inf values
    
    Parameters:
      - index_array: 2D index array
    Returns:
      - IndexStats namedtuple with:
        * min, max, mean, std: Statistical values
        * median: Median value
        * count_valid: Count of valid pixels

  compute_stress_percentage(index_array: ndarray, threshold: float) 
    -> (float, int, int)
    Calculate percentage of pixels below stress threshold
    
    Parameters:
      - index_array: Index values
      - threshold: Stress threshold (default: 0.2)
    Returns:
      - stress_percentage: Float 0-100
      - stressed_count: Number of stressed pixels
      - healthy_count: Number of healthy pixels

  analyze_ndre(nir: ndarray, red_edge: ndarray, stress_threshold: float) 
    -> NDREAnalysis
    Complete NDRE computation and analysis
    *** MAIN PRODUCTION FUNCTION ***
    
    Parameters:
      - nir: NIR band
      - red_edge: Red Edge band
      - stress_threshold: Stress classification threshold (default: 0.2)
    Returns:
      - NDREAnalysis with:
        * ndre_array: Computed NDRE
        * stats: IndexStats
        * stress_percentage: Percent below threshold
        * healthy_count, stressed_count: Pixel counts

  classify_health_status(stress_percentage: float) -> str
    Classify plant health as string
    
    Parameters:
      - stress_percentage: Percentage of stressed pixels
    Returns:
      - "healthy" (< 20%)
      - "at_risk" (20-50%)
      - "stressed" (> 50%)

  compute_vegetation_vigor(ndre_stats: IndexStats) -> float
    Compute vigor score (0-100)
    
    Parameters:
      - ndre_stats: IndexStats from get_index_stats()
    Returns:
      - Vigor score 0-100


KEY NAMEDTUPLES
===============

IndexStats
  - min: Minimum value
  - max: Maximum value
  - mean: Mean value
  - std: Standard deviation
  - median: Median value
  - count_valid: Number of valid pixels

NDREAnalysis
  - ndre_array: Computed NDRE values
  - stats: IndexStats
  - stress_percentage: % below threshold
  - stress_threshold: Threshold value used
  - healthy_count: Healthy pixels
  - stressed_count: Stressed pixels

TIFFMetadata
  - height: Image height in pixels
  - width: Image width in pixels
  - total_bands: Number of bands
  - dtype: Data type string
  - crs: Coordinate reference system (or None)
  - transform: Rasterio transform object


WORKFLOW EXAMPLE
================

1. Validate and load file:
   if not preprocessing.validate_tiff_file(filename):
       raise ValueError("Not a TIFF file")
   
   cube, metadata = preprocessing.load_tiff_cube(file_contents)

2. Extract specific bands:
   nir = cube.get_band(5, dtype=np.float32)
   red_edge = cube.get_band(4, dtype=np.float32)
   
   OR use convenience function:
   nir, red_edge, total_bands, (h, w) = \
       preprocessing.read_bands_from_tiff(contents, 5, 4)

3. Analyze vegetation index:
   analysis = indices.analyze_ndre(nir, red_edge, stress_threshold=0.2)
   
   # Access results:
   print(f"Mean NDRE: {analysis.stats.mean}")
   print(f"Stress: {analysis.stress_percentage}%")
   print(f"Health: {indices.classify_health_status(analysis.stress_percentage)}")

4. Visualize:
   heatmap_b64 = preprocessing.array_to_heatmap_base64(
       analysis.ndre_array,
       vmin=-1.0,
       vmax=1.0
   )


ERROR HANDLING
==============

Division by Zero Protection:
  - NDRE: Uses numpy.divide with where= parameter
  - Returns 0.0 where NIR + Red Edge = 0
  - No warnings or exceptions
  
NaN/Inf Handling:
  - get_index_stats() filters them automatically
  - Returns only valid pixels in statistics
  - compute_stress_percentage() ignores invalid values

Band Index Validation:
  - get_band() raises ValueError if out of range
  - Band indices are 1-based (matching TIFF convention)

File Validation:
  - validate_tiff_file() checks extension
  - load_tiff_cube() validates with rasterio
  - Raises ValueError with descriptive messages


PERFORMANCE NOTES
=================

- Full cube loading: Entire file loaded into memory
  * 512x512 image with 100 bands ≈ 100 MB
  * Be cautious with very large files

- Band extraction: O(height × width)
  * 512x512 band ≈ 1 MB for float32

- NDRE computation: Single pass, very fast
  * Vectorized numpy operations

- Statistics: Single pass with numpy
  * O(height × width)

- Visualization: PNG encoding is slowest step
  * Base64 encoding adds ~30% overhead


INTEGRATION WITH FASTAPI
=========================

In app/routers/upload.py:

  1. Validate TIFF:
     if not preprocessing.validate_tiff_file(file.filename):
         raise HTTPException(400, "Not TIFF")

  2. Load and process:
     nir, red_edge, total, (h, w) = \
         preprocessing.read_bands_from_tiff(contents, 5, 4)

  3. Analyze:
     analysis = indices.analyze_ndre(nir, red_edge)

  4. Visualize:
     heatmap_b64 = preprocessing.array_to_heatmap_base64(
         analysis.ndre_array
     )

  5. Store results:
     db.create_spectral_stats(
         scan_id=scan.id,
         ndre_min=analysis.stats.min,
         ndre_max=analysis.stats.max,
         ndre_mean=analysis.stats.mean,
         ndre_std=analysis.stats.std,
         stress_percentage=analysis.stress_percentage,
         heatmap_base64=heatmap_b64,
     )


TESTING
=======

Unit tests can verify:
  1. NDRE formula correctness
  2. Division by zero handling
  3. Statistics accuracy
  4. Band extraction validation
  5. NaN/Inf filtering

Example test:
  nir = np.random.uniform(100, 200, (512, 512))
  red = np.random.uniform(50, 150, (512, 512))
  
  analysis = indices.analyze_ndre(nir, red)
  
  assert analysis.ndre_array.dtype == np.float32
  assert -1.1 <= analysis.stats.min <= 1.1
  assert 0 <= analysis.stress_percentage <= 100


FUTURE ENHANCEMENTS
====================

1. Add more indices:
   - Red Edge NDVI (RE-NDVI)
   - Normalized Difference Soil Index (NDSI)
   - Enhanced Vegetation Index (EVI)

2. Multi-threaded processing:
   - Load cube in parallel
   - Compute multiple indices simultaneously

3. Lazy loading:
   - Load bands on-demand instead of full cube
   - More memory efficient for large files

4. Spectral unmixing:
   - Estimate endmember fractions
   - Advanced analysis of mixed pixels

5. Temporal analysis:
   - Track seasonal changes
   - Predict drought stress
"""
