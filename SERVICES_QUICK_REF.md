"""
PREPROCESSING & INDICES SERVICES - QUICK REFERENCE
====================================================

PREPROCESSING.PY
================

Load TIFF files using rasterio and extract bands safely.

Key Functions:

  validate_tiff_file(filename) → bool
    Check if file is TIFF format
  
  load_tiff_cube(bytes) → (HyperspectralCube, TIFFMetadata)
    Load complete 3D cube (bands, height, width)
  
  read_bands_from_tiff(bytes, nir_band, red_edge_band) → (nir, red_edge, total_bands, (h, w))
    Load specific bands for NDRE computation
  
  extract_band(bytes, band_index) → 2D_array
    Extract single band (1-based indexing)
  
  array_to_heatmap_base64(ndarray) → base64_string
    Convert index to PNG heatmap (base64)
  
  array_to_heatmap_bytes(ndarray) → bytes
    Convert index to PNG bytes


HyperspectralCube Class:

  .get_band(band_index, dtype) → ndarray
    Safe band extraction with validation
  
  .shape → (bands, height, width)
  .metadata → TIFFMetadata


INDICES.PY
==========

Compute vegetation indices with stress analysis.

Key Functions:

  compute_ndre(nir, red_edge) → ndarray
    NDRE = (NIR - RED) / (NIR + RED)
    Safe division (returns 0 where denominator = 0)
  
  compute_ndvi(nir, red) → ndarray
    NDVI = (NIR - Red) / (NIR + Red)
  
  get_index_stats(array) → IndexStats
    Returns: min, max, mean, std, median, count_valid
  
  compute_stress_percentage(array, threshold=0.2) → (stress%, stressed_count, healthy_count)
    Percentage of pixels below threshold
  
  analyze_ndre(nir, red_edge, threshold=0.2) → NDREAnalysis
    *** MAIN FUNCTION ***
    Complete analysis with stats and stress metrics
  
  classify_health_status(stress_percentage) → "healthy" | "at_risk" | "stressed"
  
  compute_vegetation_vigor(stats) → score (0-100)


Named Tuples:

  IndexStats
    .min, .max, .mean, .std, .median, .count_valid
  
  NDREAnalysis
    .ndre_array, .stats, .stress_percentage, .healthy_count, .stressed_count


API ENDPOINT USAGE
==================

POST /api/process-image

  1. Validate TIFF:
     if not preprocessing.validate_tiff_file(filename): ...
  
  2. Read bands:
     nir, red, total, (h, w) = preprocessing.read_bands_from_tiff(contents, 5, 4)
  
  3. Analyze:
     analysis = indices.analyze_ndre(nir, red, stress_threshold=0.2)
  
  4. Visualize:
     heatmap = preprocessing.array_to_heatmap_base64(analysis.ndre_array)
  
  5. Store:
     db.create_spectral_stats(
       ndre_min=analysis.stats.min,
       ndre_max=analysis.stats.max,
       ndre_mean=analysis.stats.mean,
       ndre_std=analysis.stats.std,
       stress_percentage=analysis.stress_percentage,
       heatmap_base64=heatmap
     )


DIVISION BY ZERO PROTECTION
============================

compute_ndre() uses numpy.divide with where= parameter:
  denominator = nir + red_edge
  result = np.divide(num, denom, out=zeros, where=denom!=0)

Result: 0.0 where denominator is 0 (no warnings/errors)


NaN/INF FILTERING
=================

get_index_stats() automatically filters:
  valid = array[np.isfinite(array)]
  
Only valid pixels included in min, max, mean, std, median


BAND INDEXING
=============

All band indices are 1-based (matching TIFF convention):
  Band 1 = first band
  Band 4 = red edge (common for Micasense)
  Band 5 = NIR (common for Micasense)

Do NOT use 0-based indexing with these functions


STRESS CLASSIFICATION
=====================

stress_threshold default: 0.2

  Healthy:   < 20% pixels below threshold
  At Risk:   20-50% pixels below threshold
  Stressed:  > 50% pixels below threshold


COLORMAP FOR HEATMAP
====================

RdYlGn (Red-Yellow-Green) default:
  -1.0 → Red (unhealthy)
   0.0 → Yellow (neutral)
   1.0 → Green (healthy)

Perfect for vegetation indices (lower = less healthy)


TYPICAL VALUES
==============

NDRE range: [-1.0, 1.0]
  < 0.2: Stressed vegetation
  0.2-0.4: Low vegetation
  0.4-0.6: Moderate vegetation
  > 0.6: Healthy vegetation

NDVI range: [-0.5, 1.0]
  < 0: No vegetation (water, soil)
  0-0.3: Sparse vegetation
  0.3-0.6: Moderate vegetation
  > 0.6: Dense vegetation


ERROR HANDLING
==============

ValueError exceptions from:
  - load_tiff_cube(): Invalid TIFF format
  - extract_band(): Band index out of range
  - get_index_stats(): No valid pixels (all NaN)

Check input validation before these functions


PERFORMANCE TIPS
================

Memory:
  512×512 image, 100 bands, float32 = ~100 MB

Speed:
  NDRE computation: < 10ms for 512×512
  Statistics: < 5ms
  Heatmap PNG: ~50-100ms (slowest)

For large files:
  Consider lazy loading of only needed bands
  Or process in batches


COMPLETE WORKFLOW
=================

# 1. Validate
if not preprocessing.validate_tiff_file(filename):
    raise HTTPException(400, "Invalid file")

# 2. Load specific bands
nir, red, total, (h, w) = preprocessing.read_bands_from_tiff(
    contents, nir_band=5, red_edge_band=4
)

# 3. Analyze
analysis = indices.analyze_ndre(nir, red, stress_threshold=0.2)

# 4. Generate visualization
heatmap_b64 = preprocessing.array_to_heatmap_base64(
    analysis.ndre_array,
    vmin=-1.0, vmax=1.0
)

# 5. Classify health
health = indices.classify_health_status(analysis.stress_percentage)

# 6. Compute vigor
vigor = indices.compute_vegetation_vigor(analysis.stats)

# Result contains:
# - analysis.stats: {min, max, mean, std, median, count_valid}
# - analysis.stress_percentage: 0-100%
# - analysis.healthy_count: number of healthy pixels
# - analysis.stressed_count: number of stressed pixels
# - heatmap_b64: base64-encoded PNG visualization
# - health: "healthy" | "at_risk" | "stressed"
# - vigor: 0-100 score
"""
