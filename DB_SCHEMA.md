"""Database schema documentation and examples."""

"""
DATABASE SCHEMA OVERVIEW
========================

The hyperspectral plant analysis system uses SQLite with 4 main tables
connected through foreign key relationships:

1. scans (parent)
2. scan_metadata (child of scans)
3. predictions (child of scans)
4. spectral_stats (child of scans)

TABLE RELATIONSHIP DIAGRAM:

    scans (1)
        ├── scan_metadata (1:1)
        ├── predictions (1:N)
        └── spectral_stats (1:1)


DETAILED TABLE SPECIFICATIONS
=============================

1. SCANS TABLE
--------------
Primary table for all uploaded hyperspectral images.

Columns:
    id (PK)                     - Auto-increment primary key
    filename (str, unique)      - Original uploaded filename with extension
    file_path (str, unique)     - Absolute path to stored file
    upload_timestamp (datetime) - When the file was uploaded (UTC)
    image_width (int)           - Image width in pixels
    image_height (int)          - Image height in pixels
    total_bands (int)           - Total number of spectral bands
    selected_nir_band (int)     - Band index used for NIR (default: 5)
    selected_red_edge_band (int)- Band index used for Red Edge (default: 4)

Relationships:
    - One-to-One with scan_metadata
    - One-to-Many with predictions
    - One-to-One with spectral_stats

Example:
    {
        "id": 1,
        "filename": "field_2026_03_29.tif",
        "file_path": "uploads/field_2026_03_29.tif",
        "upload_timestamp": "2026-03-29T14:30:00",
        "image_width": 512,
        "image_height": 512,
        "total_bands": 100,
        "selected_nir_band": 5,
        "selected_red_edge_band": 4
    }


2. SCAN_METADATA TABLE
----------------------
Additional metadata for scans, including health status classification.

Columns:
    id (PK)             - Auto-increment primary key
    scan_id (FK)        - Foreign key to scans table (unique, 1:1)
    health_status (str) - Health classification (e.g., "healthy", "stressed", "diseased")
    metadata (JSON)     - Flexible JSON field for additional context
    created_at (datetime) - Timestamp when record was created
    updated_at (datetime) - Timestamp of last update

Relationships:
    - One-to-One with scans (via scan_id)

Example:
    {
        "id": 1,
        "scan_id": 1,
        "health_status": "stressed",
        "metadata": {
            "field_name": "North Plot",
            "crop_type": "wheat",
            "soil_moisture": 45.2,
            "air_temperature": 22.5
        },
        "created_at": "2026-03-29T14:31:00",
        "updated_at": "2026-03-29T14:35:00"
    }


3. PREDICTIONS TABLE
--------------------
ML model predictions and confidence scores for scans.
Multiple predictions per scan are allowed (e.g., different models).

Columns:
    id (PK)             - Auto-increment primary key
    scan_id (FK)        - Foreign key to scans table (indexed)
    predicted_class (str) - Predicted class (e.g., "healthy", "stressed", "diseased")
    confidence (float)  - Confidence score (0.0 to 1.0)
    model_version (str) - Optional version identifier of the model used
    created_at (datetime) - Timestamp when prediction was made

Relationships:
    - Many-to-One with scans (via scan_id)

Example:
    {
        "id": 1,
        "scan_id": 1,
        "predicted_class": "stressed",
        "confidence": 0.87,
        "model_version": "v2.1.0",
        "created_at": "2026-03-29T14:31:00"
    }


4. SPECTRAL_STATS TABLE
-----------------------
Computed spectral statistics and vegetation indices for scans.

Columns:
    id (PK)             - Auto-increment primary key
    scan_id (FK)        - Foreign key to scans table (unique, 1:1)
    
    NDRE Statistics:
    ndre_min (float)    - Minimum NDRE value in the image
    ndre_max (float)    - Maximum NDRE value in the image
    ndre_mean (float)   - Mean NDRE value
    ndre_std (float)    - Standard deviation of NDRE values
    
    Stress Metrics:
    stress_percentage (float) - % of pixels below stress_threshold
    stress_threshold (float)  - NDRE threshold for stress classification (default: 0.2)
    
    Visualization:
    heatmap_base64 (str) - Base64-encoded PNG heatmap image
    heatmap_path (str)   - Optional: path to saved heatmap file
    
    Additional Data:
    spectral_data (JSON) - Additional spectral indices (NDVI, etc.)
    created_at (datetime) - Timestamp when stats were computed
    updated_at (datetime) - Timestamp of last update

Relationships:
    - One-to-One with scans (via scan_id)

Example:
    {
        "id": 1,
        "scan_id": 1,
        "ndre_min": -0.1234,
        "ndre_max": 0.8765,
        "ndre_mean": 0.4521,
        "ndre_std": 0.1234,
        "stress_percentage": 15.8,
        "stress_threshold": 0.2,
        "heatmap_base64": "iVBORw0KGgoAAAANS...",
        "heatmap_path": "heatmaps/field_2026_03_29_heatmap.png",
        "spectral_data": {
            "ndvi": 0.6234,
            "ndvi_mean": 0.5821
        },
        "created_at": "2026-03-29T14:31:00",
        "updated_at": "2026-03-29T14:31:00"
    }


USAGE EXAMPLES
==============

Creating Complete Analysis Record:
----------------------------------
# 1. Create scan
scan = Scan(
    filename="field.tif",
    file_path="uploads/field.tif",
    image_width=512,
    image_height=512,
    total_bands=100,
    selected_nir_band=5,
    selected_red_edge_band=4
)

# 2. Create metadata
metadata = ScanMetadata(
    scan_id=scan.id,
    health_status="healthy",
    metadata={"field": "North Plot"}
)

# 3. Create spectral stats
stats = SpectralStats(
    scan_id=scan.id,
    ndre_min=-0.1,
    ndre_max=0.9,
    ndre_mean=0.5,
    ndre_std=0.15,
    stress_percentage=10.5,
    heatmap_base64="base64_string_here"
)

# 4. Create prediction (optional)
prediction = Prediction(
    scan_id=scan.id,
    predicted_class="healthy",
    confidence=0.92,
    model_version="v2.1.0"
)


Querying Data:
--------------
# Get complete scan with all related data
scan = db.query(Scan).filter(Scan.id == 1).first()
print(scan.filename)
print(scan.metadata.health_status)
print(scan.spectral_stats.ndre_mean)
print(scan.predictions[0].predicted_class)

# Get latest prediction for a scan
latest_pred = db.query(Prediction).filter(
    Prediction.scan_id == 1
).order_by(Prediction.created_at.desc()).first()

# Get all scans with stress > 20%
stressed_scans = db.query(Scan).join(
    SpectralStats, Scan.id == SpectralStats.scan_id
).filter(SpectralStats.stress_percentage > 20).all()


DATABASE INITIALIZATION
=======================

The database is automatically initialized when the app starts:

from app.database import init_db

init_db()  # Creates all tables if they don't exist


MIGRATION NOTES
===============

SQLite Compatibility:
- All tables use INTEGER primary keys
- Foreign keys are supported (check_same_thread=False for SQLite)
- JSON columns are supported via SQLAlchemy type mapping
- Relationships use cascading deletes

To switch to PostgreSQL for production:
- Update DATABASE_URL in app/database.py
- No schema changes needed (models are DB-agnostic)
- Example: "postgresql://user:password@localhost:5432/hidden_hunger"
"""
