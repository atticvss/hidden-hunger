"""Storage Service Documentation and Usage Guide."""

"""
FILE STORAGE SERVICE
====================

The storage service (`app/services/storage.py`) provides production-friendly
file management with UUID-based naming, automatic directory creation, and
organized folder structures.


DIRECTORY STRUCTURE
===================

Generated at runtime:

project_root/
├── uploads/          # Uploaded TIFF files (with UUID names)
├── outputs/
│   ├── heatmaps/    # Generated heatmap PNG images
│   └── artifacts/   # Analysis results, debug data, etc.


KEY FEATURES
============

1. UUID-Based Naming
   - Files are saved with UUID4 identifiers while preserving extensions
   - Example: a1b2c3d4-e5f6-7890-abcd-ef1234567890.tif
   - Prevents filename conflicts and collisions
   - Secures against path traversal attacks

2. Automatic Directory Creation
   - All directories are created automatically on first use
   - Safe for concurrent access
   - Uses Path.mkdir(exist_ok=True, parents=True)

3. StorageFile Named Tuple
   - Structured return value with file information:
     - original_filename: User's uploaded filename
     - saved_filename: UUID-based name
     - full_path: Absolute file path
     - relative_path: Path relative to project root


API REFERENCE
=============

save_uploaded_file(original_filename: str, contents: bytes) -> StorageFile
  Save an uploaded file to uploads/ directory
  
  Args:
    original_filename: Original filename from user (e.g., "scan.tif")
    contents: Raw file bytes
    
  Returns:
    StorageFile with file paths and names
    
  Example:
    file_info = storage.save_uploaded_file("field.tif", file_bytes)
    print(file_info.original_filename)  # "field.tif"
    print(file_info.saved_filename)     # "a1b2c3d4-....tif"
    print(file_info.full_path)          # "/absolute/path/uploads/a1b2c3d4-....tif"


save_heatmap(heatmap_bytes: bytes, scan_id: int, format: str = "png") -> StorageFile
  Save a heatmap image to outputs/heatmaps/
  
  Args:
    heatmap_bytes: Image file contents
    scan_id: ID to associate with heatmap
    format: Image format (default: "png")
    
  Returns:
    StorageFile with heatmap path
    
  Example:
    heatmap_info = storage.save_heatmap(png_bytes, scan_id=5)
    # Saves to: outputs/heatmaps/scan_5_<uuid>.png


get_heatmap_output_path(scan_id: int, filename: str = None) -> str
  Get output path for heatmap (before generation)
  
  Args:
    scan_id: Scan identifier
    filename: Optional specific filename
    
  Returns:
    Path where heatmap will be/will be stored
    
  Use Case:
    # Store path in database before heatmap generation
    heatmap_path = storage.get_heatmap_output_path(scan_id=5)
    db_record.heatmap_path = heatmap_path


get_artifact_output_path(scan_id: int, artifact_type: str, extension: str = "json") -> str
  Get output path for analysis artifacts
  
  Args:
    scan_id: Scan identifier
    artifact_type: Type of artifact (e.g., "analysis", "debug", "raw_data")
    extension: File extension (default: "json")
    
  Returns:
    Path where artifact will be stored
    
  Example:
    analysis_path = storage.get_artifact_output_path(scan_id=5, artifact_type="analysis")
    # Returns: outputs/artifacts/scan_5_analysis_<uuid>.json


delete_file(file_path: str) -> bool
  Delete a file
  
  Args:
    file_path: Path to file (relative or absolute)
    
  Returns:
    True if deleted, False if not found


file_exists(file_path: str) -> bool
  Check if file exists
  
  Args:
    file_path: Path to file
    
  Returns:
    True if file exists, False otherwise


get_file_size(file_path: str) -> int
  Get file size in bytes
  
  Args:
    file_path: Path to file
    
  Returns:
    File size in bytes, or 0 if file doesn't exist


cleanup_old_files(directory: str, max_age_days: int = 30) -> int
  Remove files older than specified days
  
  Args:
    directory: "uploads" or "outputs"
    max_age_days: Delete files older than this (default: 30)
    
  Returns:
    Number of files deleted
    
  Example:
    # Remove uploads older than 30 days
    deleted = storage.cleanup_old_files("uploads", max_age_days=30)
    print(f"Cleaned up {deleted} files")


USAGE EXAMPLES
==============

1. Save Uploaded TIFF File
   ========================
   
   from app.services import storage
   
   async def process_upload(file: UploadFile):
       contents = await file.read()
       file_info = storage.save_uploaded_file(file.filename, contents)
       
       # Use the structured information
       print(f"Saved as: {file_info.saved_filename}")
       print(f"Full path: {file_info.full_path}")
       print(f"Original: {file_info.original_filename}")
       
       # Store in database
       scan = Scan(
           filename=file_info.original_filename,
           file_path=file_info.full_path,
           ...
       )


2. Process File and Save Heatmap
   ==============================
   
   import numpy as np
   from app.services import storage, preprocessing
   
   # Read file back from storage
   with open(file_info.full_path, 'rb') as f:
       nir, red_edge, _, _ = preprocessing.read_bands_from_tiff(
           f.read(),
           nir_band=5,
           red_edge_band=4
       )
   
   # Generate heatmap PNG
   heatmap_bytes, base64_str = generate_heatmap(nir, red_edge)
   
   # Save heatmap with scan association
   heatmap_info = storage.save_heatmap(heatmap_bytes, scan_id=5)
   # Saves to: outputs/heatmaps/scan_5_<uuid>.png


3. Store Analysis Artifacts
   ==========================
   
   import json
   from app.services import storage
   
   # Get path for analysis results
   analysis_path = storage.get_artifact_output_path(
       scan_id=5,
       artifact_type="analysis",
       extension="json"
   )
   
   # Save analysis results
   results = {
       "ndre_mean": 0.45,
       "stress_percentage": 15.2,
       "bands_used": [4, 5],
   }
   
   with open(analysis_path, 'w') as f:
       json.dump(results, f)


4. Maintenance and Cleanup
   ========================
   
   from app.services import storage
   
   # Perform periodic cleanup
   deleted_uploads = storage.cleanup_old_files("uploads", max_age_days=30)
   deleted_outputs = storage.cleanup_old_files("outputs", max_age_days=60)
   
   print(f"Cleaned {deleted_uploads} old uploads")
   print(f"Cleaned {deleted_outputs} old outputs")


PRODUCTION CONSIDERATIONS
==========================

1. File Permissions
   - Ensure proper umask is set before running the application
   - Database user should have read/write access to upload directories

2. Storage Location
   - For production, consider using cloud storage (S3, Azure Blob, GCS)
   - For high-volume systems, implement:
     - Sharded directories (daily or time-based)
     - Separate storage service/CDN
     - Archive old files to cheaper storage

3. Scalability
   - UUID-based naming allows horizontal scaling
   - Multiple workers can safely save files simultaneously
   - Consider load balancing across multiple servers

4. Disk Usage
   - Monitor disk space on storage volume
   - Implement cleanup schedule to remove old files
   - Archive heatmaps and artifacts separately from uploads

5. Security
   - Never allow user-controlled filenames to be used directly
   - UUID naming prevents directory traversal
   - Validate file extensions before processing
   - Consider rate limiting on upload endpoints

6. Backup Strategy
   - Backup uploads and outputs directories regularly
   - Database records link to file paths (important for recovery)
   - Consider S3 versioning or similar for durability


DATABASE INTEGRATION
====================

The storage paths are stored in the Scan model:

    scan = Scan(
        filename="original_name.tif",           # Original name
        file_path=file_info.full_path,          # Full absolute path
        ...
    )
    
    spectral_stats = SpectralStats(
        scan_id=scan.id,
        heatmap_path=storage.get_heatmap_output_path(scan.id),
        heatmap_base64=base64_encoded_data,
        ...
    )

This allows:
- Easy file retrieval by scan_id
- Cleanup of orphaned files (compare DB records with filesystem)
- File serving/streaming endpoints
- Integration with CDN services


TESTING
=======

Mock storage for unit tests:

    from unittest.mock import patch, MagicMock
    
    @patch('app.services.storage.save_uploaded_file')
    def test_upload(mock_save):
        mock_save.return_value = storage.StorageFile(
            original_filename="test.tif",
            saved_filename="uuid-test.tif",
            full_path="/tmp/uploads/uuid-test.tif",
            relative_path="uploads/uuid-test.tif"
        )
        # Test code here
"""
