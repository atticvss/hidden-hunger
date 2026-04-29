"""
STORAGE SERVICE - USAGE EXAMPLES
=================================

Example 1: Upload and Save File
================================

from app.services import storage
from pathlib import Path

async def handle_upload(file: UploadFile):
    '''Save uploaded file with UUID naming.'''
    contents = await file.read()
    
    # Save file with automatic UUID naming
    file_info = storage.save_uploaded_file(file.filename, contents)
    
    # file_info contains:
    # - original_filename: "scan.tif"
    # - saved_filename: "a1b2c3d4-e5f6....tif"
    # - full_path: "/absolute/path/uploads/a1b2c3d4-....tif"
    # - relative_path: "uploads/a1b2c3d4-....tif"
    
    return file_info


Example 2: Save Generated Heatmap
==================================

import io
from PIL import Image
from app.services import storage

def generate_and_save_heatmap(ndre_array, scan_id):
    '''Generate heatmap visualization and save to storage.'''
    
    # Generate heatmap visualization (as PIL Image)
    # ... visualization code ...
    img = Image.fromarray(heatmap_rgb)
    
    # Convert to bytes
    png_buffer = io.BytesIO()
    img.save(png_buffer, format='PNG')
    heatmap_bytes = png_buffer.getvalue()
    
    # Save to outputs/heatmaps/ with scan association
    heatmap_info = storage.save_heatmap(heatmap_bytes, scan_id=scan_id, format="png")
    
    # Now heatmap_info.full_path can be stored in database
    return heatmap_info


Example 3: Store Output Paths Before Generation
================================================

from app.services import storage
import json

def prepare_analysis(scan_id):
    '''Pre-generate paths for analysis outputs.'''
    
    # Get heatmap path before generating heatmap
    heatmap_path = storage.get_heatmap_output_path(scan_id)
    
    # Get artifact path for analysis results
    artifact_path = storage.get_artifact_output_path(
        scan_id=scan_id,
        artifact_type="analysis",
        extension="json"
    )
    
    debug_path = storage.get_artifact_output_path(
        scan_id=scan_id,
        artifact_type="debug",
        extension="json"
    )
    
    # Store paths in database or config
    return {
        "heatmap_path": heatmap_path,
        "analysis_path": artifact_path,
        "debug_path": debug_path,
    }


Example 4: Complete Upload Workflow
====================================

from fastapi import UploadFile
from sqlalchemy.orm import Session
from app.services import storage, preprocessing, indices
from app.models import Scan, SpectralStats
from app.crud import create_scan, create_spectral_stats
import numpy as np

async def process_uploaded_image(
    file: UploadFile,
    db: Session,
    nir_band: int = 5,
    red_edge_band: int = 4
):
    '''Complete workflow: upload → save → process → store.'''
    
    # 1. Read file contents
    contents = await file.read()
    
    # 2. Save uploaded file
    file_info = storage.save_uploaded_file(file.filename, contents)
    
    # 3. Create Scan record
    scan = Scan(
        filename=file_info.original_filename,
        file_path=file_info.full_path,
        image_width=512,
        image_height=512,
        total_bands=100,
        selected_nir_band=nir_band,
        selected_red_edge_band=red_edge_band
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)
    
    # 4. Read and process TIFF bands
    nir, red_edge, total_bands, (height, width) = \
        preprocessing.read_bands_from_tiff(contents, nir_band, red_edge_band)
    
    # 5. Compute indices
    ndre = indices.compute_ndre(nir, red_edge)
    ndre_stats = indices.get_index_stats(ndre)
    
    # 6. Generate heatmap
    heatmap_base64 = preprocessing.array_to_heatmap_base64(ndre)
    
    # 7. Save heatmap file
    heatmap_path = storage.get_heatmap_output_path(scan.id)
    
    # 8. Store spectral statistics
    stats = SpectralStats(
        scan_id=scan.id,
        ndre_min=ndre_stats["min"],
        ndre_max=ndre_stats["max"],
        ndre_mean=ndre_stats["mean"],
        ndre_std=ndre_stats["std"],
        stress_percentage=15.8,
        heatmap_base64=heatmap_base64,
        heatmap_path=heatmap_path,
        spectral_data={"ndre": ndre_stats}
    )
    db.add(stats)
    db.commit()
    
    return scan


Example 5: File Management Operations
======================================

from app.services import storage

# Check if file exists
exists = storage.file_exists("uploads/a1b2c3d4-....tif")
print(f"File exists: {exists}")

# Get file size
size_bytes = storage.get_file_size("uploads/a1b2c3d4-....tif")
print(f"File size: {size_bytes} bytes")

# Delete a file
deleted = storage.delete_file("uploads/old_file.tif")
print(f"Deleted: {deleted}")

# Cleanup files older than 30 days
removed_count = storage.cleanup_old_files("uploads", max_age_days=30)
print(f"Removed {removed_count} old files")


Example 6: Organization Structure
==================================

In a real application, the structure looks like:

project_root/
├── app/
│   ├── main.py
│   ├── models.py
│   ├── services/
│   │   ├── storage.py      <- File management
│   │   └── preprocessing.py
│   └── routers/
│       └── upload.py
├── uploads/                 <- Auto-created by ensure_storage_dirs()
│   ├── uuid1-....tif
│   ├── uuid2-....tif
│   └── uuid3-....tif
├── outputs/                 <- Auto-created by ensure_storage_dirs()
│   ├── heatmaps/
│   │   ├── scan_1_uuid1.png
│   │   └── scan_2_uuid2.png
│   └── artifacts/
│       ├── scan_1_analysis_uuid1.json
│       └── scan_2_debug_uuid2.json
├── hidden_hunger.db         <- SQLite database
└── requirements.txt


Example 7: Integration with FastAPI Route
===========================================

from fastapi import APIRouter, UploadFile, File, Depends
from sqlalchemy.orm import Session
from app.deps import get_db
from app.services import storage

router = APIRouter()

@router.post("/upload/scan")
async def upload_scan(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    '''Upload a hyperspectral TIFF scan.'''
    
    contents = await file.read()
    
    # Save with UUID naming
    file_info = storage.save_uploaded_file(file.filename, contents)
    
    # Use file information in database operations
    # file_info.original_filename: Show to user
    # file_info.saved_filename: For internal organization
    # file_info.full_path: For file server/processing
    
    return {
        "message": "File uploaded successfully",
        "original_name": file_info.original_filename,
        "saved_name": file_info.saved_filename,
        "path": file_info.relative_path
    }


Example 8: Error Handling
=========================

from app.services import storage
from fastapi import HTTPException

async def safe_upload(file: UploadFile):
    '''Upload with proper error handling.'''
    
    contents = await file.read()
    
    try:
        # Attempt to save file
        file_info = storage.save_uploaded_file(file.filename, contents)
        
    except IOError as e:
        # Handle file I/O errors
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save file: {str(e)}"
        )
    
    except Exception as e:
        # Unexpected errors
        raise HTTPException(
            status_code=500,
            detail="Unexpected error during file upload"
        )
    
    return file_info


Example 9: Maintenance Tasks
=============================

from app.services import storage
import logging

logger = logging.getLogger(__name__)

def maintenance_cleanup():
    '''Run periodic maintenance tasks.'''
    
    # Remove uploads older than 30 days
    uploads_deleted = storage.cleanup_old_files(
        "uploads",
        max_age_days=30
    )
    logger.info(f"Cleaned {uploads_deleted} old uploads")
    
    # Remove artifacts older than 60 days
    artifacts_deleted = storage.cleanup_old_files(
        "outputs/artifacts",
        max_age_days=60
    )
    logger.info(f"Cleaned {artifacts_deleted} old artifacts")
    
    return {
        "uploads_deleted": uploads_deleted,
        "artifacts_deleted": artifacts_deleted
    }

# Schedule with APScheduler or Celery
# from apscheduler.schedulers.background import BackgroundScheduler
# scheduler = BackgroundScheduler()
# scheduler.add_job(maintenance_cleanup, 'cron', hour=2, minute=0)
# scheduler.start()


Example 10: Testing Storage Service
===================================

import pytest
from unittest.mock import patch, MagicMock
from app.services import storage

def test_save_uploaded_file():
    '''Test file save functionality.'''
    
    test_content = b"test tiff data"
    result = storage.save_uploaded_file("test.tif", test_content)
    
    assert result.original_filename == "test.tif"
    assert result.saved_filename.endswith(".tif")
    assert storage.file_exists(result.full_path)
    
    # Cleanup
    storage.delete_file(result.full_path)

def test_output_paths():
    '''Test output path generation.'''
    
    heatmap_path = storage.get_heatmap_output_path(scan_id=1)
    assert "heatmaps" in heatmap_path
    assert "scan_1" in heatmap_path
    
    artifact_path = storage.get_artifact_output_path(
        scan_id=1,
        artifact_type="test"
    )
    assert "artifacts" in artifact_path
    assert "scan_1_test" in artifact_path
"""
