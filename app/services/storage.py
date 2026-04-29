"""File storage utilities with UUID-based naming for production."""
import os
from pathlib import Path
from uuid import uuid4
from typing import NamedTuple


# Storage directories
UPLOADS_DIR = Path("uploads")
OUTPUTS_DIR = Path("outputs")
HEATMAPS_DIR = OUTPUTS_DIR / "heatmaps"
ARTIFACTS_DIR = OUTPUTS_DIR / "artifacts"


class StorageFile(NamedTuple):
    """Information about a stored file."""
    original_filename: str
    saved_filename: str
    full_path: str
    relative_path: str


def ensure_storage_dirs() -> None:
    """Ensure all storage directories exist."""
    UPLOADS_DIR.mkdir(exist_ok=True, parents=True)
    OUTPUTS_DIR.mkdir(exist_ok=True, parents=True)
    HEATMAPS_DIR.mkdir(exist_ok=True, parents=True)
    ARTIFACTS_DIR.mkdir(exist_ok=True, parents=True)


def _get_unique_filename(original_filename: str) -> str:
    """
    Generate a unique filename using UUID.
    
    Preserves the original file extension.
    
    Args:
        original_filename: Original filename (e.g., "scan.tif")
        
    Returns:
        UUID-based filename with original extension (e.g., "a1b2c3d4-e5f6-7890-abcd-ef1234567890.tif")
    """
    _, ext = os.path.splitext(original_filename)
    unique_name = f"{uuid4()}{ext}"
    return unique_name


def save_uploaded_file(original_filename: str, contents: bytes) -> StorageFile:
    """
    Save an uploaded file to the uploads directory with UUID-based naming.
    
    Args:
        original_filename: Original filename from upload
        contents: File contents as bytes
        
    Returns:
        StorageFile with original_filename, saved_filename, full_path, and relative_path
        
    Raises:
        IOError: If file cannot be written
    """
    ensure_storage_dirs()
    
    # Generate unique filename
    saved_filename = _get_unique_filename(original_filename)
    file_path = UPLOADS_DIR / saved_filename
    
    # Write file
    try:
        with open(file_path, "wb") as f:
            f.write(contents)
    except IOError as e:
        raise IOError(f"Failed to save file {saved_filename}: {str(e)}")
    
    return StorageFile(
        original_filename=original_filename,
        saved_filename=saved_filename,
        full_path=str(file_path.resolve()),
        relative_path=str(file_path)
    )


def save_heatmap(heatmap_bytes: bytes, scan_id: int, format: str = "png") -> StorageFile:
    """
    Save a heatmap image to the outputs/heatmaps directory.
    
    Args:
        heatmap_bytes: Image file contents as bytes
        scan_id: ID of the scan this heatmap is for
        format: Image format extension (default: "png")
        
    Returns:
        StorageFile with heatmap path information
    """
    ensure_storage_dirs()
    
    # Generate filename with scan_id for easy association
    saved_filename = f"scan_{scan_id}_{uuid4()}.{format}"
    file_path = HEATMAPS_DIR / saved_filename
    
    try:
        with open(file_path, "wb") as f:
            f.write(heatmap_bytes)
    except IOError as e:
        raise IOError(f"Failed to save heatmap {saved_filename}: {str(e)}")
    
    return StorageFile(
        original_filename=f"heatmap_{scan_id}.{format}",
        saved_filename=saved_filename,
        full_path=str(file_path.resolve()),
        relative_path=str(file_path)
    )


def save_artifact(artifact_bytes: bytes, scan_id: int, artifact_type: str, extension: str) -> StorageFile:
    """
    Save a generated artifact to outputs/artifacts with a stable scan_id prefix.

    Args:
        artifact_bytes: Artifact file contents
        scan_id: ID of the scan this artifact belongs to
        artifact_type: Logical artifact type (e.g. "rgb_cube", "analysis")
        extension: File extension without leading dot

    Returns:
        StorageFile with artifact path information
    """
    ensure_storage_dirs()

    saved_filename = f"scan_{scan_id}_{artifact_type}_{uuid4()}.{extension}"
    file_path = ARTIFACTS_DIR / saved_filename

    try:
        with open(file_path, "wb") as f:
            f.write(artifact_bytes)
    except IOError as e:
        raise IOError(f"Failed to save artifact {saved_filename}: {str(e)}")

    return StorageFile(
        original_filename=f"{artifact_type}.{extension}",
        saved_filename=saved_filename,
        full_path=str(file_path.resolve()),
        relative_path=str(file_path),
    )


def get_heatmap_output_path(scan_id: int, filename: str | None = None) -> str:
    """
    Get output path for a heatmap (for database storage before generation).
    
    Args:
        scan_id: ID of the scan
        filename: Optional specific filename. If None, generates a placeholder path.
        
    Returns:
        Relative path where heatmap will be stored
    """
    ensure_storage_dirs()
    
    if filename is None:
        filename = f"scan_{scan_id}_heatmap.png"
    
    output_path = HEATMAPS_DIR / filename
    return str(output_path)


def get_artifact_output_path(scan_id: int, artifact_type: str, extension: str = "json") -> str:
    """
    Get output path for artifact files (analysis results, debug data, etc.).
    
    Args:
        scan_id: ID of the scan
        artifact_type: Type of artifact (e.g., "analysis", "debug", "raw_data")
        extension: File extension (default: "json")
        
    Returns:
        Relative path where artifact will be stored
    """
    ensure_storage_dirs()
    
    filename = f"scan_{scan_id}_{artifact_type}_{uuid4()}.{extension}"
    artifact_path = ARTIFACTS_DIR / filename
    return str(artifact_path)


def delete_file(file_path: str) -> bool:
    """
    Delete a file.
    
    Args:
        file_path: Path to file (relative or absolute)
        
    Returns:
        True if deleted, False if not found
    """
    try:
        path = Path(file_path)
        if path.exists():
            path.unlink()
            return True
        return False
    except Exception:
        return False


def file_exists(file_path: str) -> bool:
    """Check if file exists."""
    return Path(file_path).exists()


def get_file_size(file_path: str) -> int:
    """
    Get file size in bytes.
    
    Args:
        file_path: Path to file
        
    Returns:
        File size in bytes, or 0 if file doesn't exist
    """
    try:
        return Path(file_path).stat().st_size
    except FileNotFoundError:
        return 0


def cleanup_old_files(directory: str, max_age_days: int = 30) -> int:
    """
    Clean up files older than specified days.
    
    Args:
        directory: Directory to clean ("uploads" or "outputs")
        max_age_days: Delete files older than this many days
        
    Returns:
        Number of files deleted
    """
    import time
    
    dir_path = Path(directory)
    if not dir_path.exists():
        return 0
    
    deleted_count = 0
    current_time = time.time()
    max_age_seconds = max_age_days * 24 * 60 * 60
    
    for item in dir_path.rglob("*"):
        if item.is_file():
            file_age = current_time - item.stat().st_mtime
            if file_age > max_age_seconds:
                try:
                    item.unlink()
                    deleted_count += 1
                except Exception:
                    pass
    
    return deleted_count
