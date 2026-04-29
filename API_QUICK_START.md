"""
HYPERSPECTRAL PLANT ANALYSIS - API QUICK START
===============================================

MAIN ENDPOINT
=============

POST /api/process-image

Upload and analyze hyperspectral TIFF image


REQUEST
-------

Content-Type: multipart/form-data

Parameters:
  - file (required): GeoTIFF file
  - nir_band (optional): NIR band index, default: 5
  - red_edge_band (optional): Red Edge band index, default: 4
  - stress_threshold (optional): Stress threshold, default: 0.2


RESPONSE (200 OK)
-----------------

{
  "scan_id": 1,
  "filename": "field_scan.tif",
  "heatmap_base64": "iVBORw0KGgoAAAANS...",
  "image_shape": {
    "height": 512,
    "width": 512
  },
  "ndre_stats": {
    "min": -0.1234,
    "max": 0.8765,
    "mean": 0.4521,
    "std": 0.1234
  },
  "stress_percentage": 15.8,
  "stress_threshold": 0.2,
  "upload_timestamp": "2026-03-29T17:18:00"
}


CURL EXAMPLE
============

curl -X POST "http://localhost:8000/api/process-image" \
  -F "file=@field_scan.tif" \
  -F "nir_band=5" \
  -F "red_edge_band=4" \
  -F "stress_threshold=0.2"


HISTORY ENDPOINTS
=================

GET /api/history
  List all scans (paginated)
  
  Parameters:
    - skip: int (default: 0)
    - limit: int (default: 100)
  
  Response:
    {
      "total": 42,
      "scans": [
        {
          "id": 1,
          "filename": "field_scan.tif",
          "file_path": "/absolute/path/uploads/uuid.tif",
          "upload_timestamp": "2026-03-29T17:18:00",
          "image_width": 512,
          "image_height": 512,
          "total_bands": 100,
          "selected_nir_band": 5,
          "selected_red_edge_band": 4
        }
      ]
    }


GET /api/history/{scan_id}
  Get complete scan details with all related data
  
  Response:
    {
      "id": 1,
      "filename": "field_scan.tif",
      "file_path": "/absolute/path/uploads/uuid.tif",
      "upload_timestamp": "2026-03-29T17:18:00",
      "image_width": 512,
      "image_height": 512,
      "total_bands": 100,
      "selected_nir_band": 5,
      "selected_red_edge_band": 4,
      "metadata": {
        "id": 1,
        "scan_id": 1,
        "health_status": "healthy",
        "metadata": {
          "field_name": "North Plot",
          ...
        },
        "created_at": "2026-03-29T17:18:00",
        "updated_at": "2026-03-29T17:18:00"
      },
      "predictions": [
        {
          "id": 1,
          "scan_id": 1,
          "predicted_class": "healthy",
          "confidence": 0.92,
          "model_version": "v2.1.0",
          "created_at": "2026-03-29T17:18:00"
        }
      ],
      "spectral_stats": {
        "id": 1,
        "scan_id": 1,
        "ndre_min": -0.1234,
        "ndre_max": 0.8765,
        "ndre_mean": 0.4521,
        "ndre_std": 0.1234,
        "stress_percentage": 15.8,
        "stress_threshold": 0.2,
        "heatmap_path": "outputs/heatmaps/scan_1_heatmap.png",
        "spectral_data": {
          "ndre": {
            "min": -0.1234,
            "max": 0.8765,
            "mean": 0.4521,
            "std": 0.1234
          },
          "healthy_pixels": 430848,
          "stressed_pixels": 65792
        },
        "created_at": "2026-03-29T17:18:00",
        "updated_at": "2026-03-29T17:18:00"
      }
    }


DELETE /api/history/{scan_id}
  Delete scan and all associated data
  
  Response:
    {
      "detail": "Scan deleted successfully"
    }


PYTHON USAGE
============

import requests

# Upload and analyze
files = {'file': open('scan.tif', 'rb')}
params = {
    'nir_band': 5,
    'red_edge_band': 4,
    'stress_threshold': 0.2
}

response = requests.post(
    'http://localhost:8000/api/process-image',
    files=files,
    params=params
)

result = response.json()

print(f"Scan ID: {result['scan_id']}")
print(f"Mean NDRE: {result['ndre_stats']['mean']}")
print(f"Stress: {result['stress_percentage']}%")

# Display heatmap (base64 encoded)
import base64
from PIL import Image
import io

heatmap_data = base64.b64decode(result['heatmap_base64'])
img = Image.open(io.BytesIO(heatmap_data))
img.show()


SERVICE FUNCTIONS
=================

preprocessing.read_bands_from_tiff(file_bytes, nir_band, red_edge_band)
  → (nir_array, red_edge_array, total_bands, (height, width))

indices.analyze_ndre(nir, red_edge, stress_threshold)
  → NDREAnalysis(ndre_array, stats, stress_percentage, healthy_count, stressed_count)

preprocessing.array_to_heatmap_base64(ndre_array)
  → base64_encoded_png_string

indices.classify_health_status(stress_percentage)
  → "healthy" | "at_risk" | "stressed"

indices.compute_vegetation_vigor(stats)
  → vigor_score (0-100)


DATABASE SCHEMA
===============

Tables:
  - scans: Main upload records
  - scan_metadata: Health status and context
  - predictions: ML model predictions
  - spectral_stats: NDRE and vegetation indices

Relationships:
  - Scan → (one-to-one) ScanMetadata
  - Scan → (one-to-many) Prediction
  - Scan → (one-to-one) SpectralStats


FILE ORGANIZATION
=================

uploads/
  └── <uuid>.tif (uploaded TIFF files)

outputs/
  ├── heatmaps/
  │   └── scan_<id>_<uuid>.png
  └── artifacts/
      └── scan_<id>_<type>_<uuid>.json

hidden_hunger.db
  SQLite database with all metadata


STRESS LEVELS
=============

Threshold: 0.2 (NDRE value)

Classification:
  < 20% pixels below threshold:  Healthy
  20-50% pixels below threshold: At Risk
  > 50% pixels below threshold:  Stressed


EXPECTED NDRE VALUES
====================

NDRE = (NIR - Red Edge) / (NIR + Red Edge)

Typical ranges:
  -1.0 to -0.3: Water, bare soil (unhealthy)
  -0.3 to 0.0: No vegetation signal
   0.0 to 0.3: Sparse vegetation (poor)
   0.3 to 0.6: Moderate vegetation (fair)
   0.6 to 1.0: Healthy vegetation (excellent)


TROUBLESHOOTING
===============

Error: "Only GeoTIFF files are supported"
  → Ensure file has .tif or .tiff extension

Error: "File has X bands; requested NIR=Y, RedEdge=Z"
  → Check band indices don't exceed total bands
  → Typical: NIR=5, RedEdge=4 for Micasense cameras

Error: "Scan not found"
  → Check scan ID exists: GET /api/history

Empty stress percentage or stats
  → Verify TIFF has valid spectral data
  → Check bands aren't all zeros or saturated


PERFORMANCE EXPECTATIONS
=========================

Small image (256×256, 50 bands):
  - Upload + Process: ~200 ms
  - Response: <500 ms total

Medium image (512×512, 100 bands):
  - Upload + Process: ~600 ms
  - Response: ~1 second total

Large image (2048×2048, 200 bands):
  - Upload + Process: ~5 seconds
  - Response: ~10 seconds total

Heatmap generation slowest (PNG encoding)


RATE LIMITS
===========

Currently: None (configure in production)

Recommendations:
  - Limit file size: Max 100 MB
  - Limit requests: 10 per minute per IP
  - Timeout: 30 seconds per upload


NEXT STEPS
==========

1. Start server:
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

2. Test with Postman, curl, or Python requests

3. View API docs at:
   http://localhost:8000/docs

4. Check database:
   sqlite3 hidden_hunger.db ".schema"

5. Monitor logs for errors

6. Consider deploying to production with:
   - PostgreSQL instead of SQLite
   - Redis for caching
   - Cloud storage (S3, Azure, GCS)
   - Load balancing
   - Monitoring and alerting
"""
