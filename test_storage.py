#!/usr/bin/env python3
"""Test script for storage service."""

from app.services.storage import (
    StorageFile,
    ensure_storage_dirs,
    _get_unique_filename,
    save_uploaded_file,
    get_heatmap_output_path,
    get_artifact_output_path,
    file_exists,
    delete_file
)

def test_storage_service():
    """Run comprehensive storage service tests."""
    
    # Test 1: Ensure directories
    print("Test 1: Creating storage directories...")
    ensure_storage_dirs()
    print("✓ Directories created successfully")

    # Test 2: UUID filename generation
    print("\nTest 2: UUID filename generation...")
    filename = _get_unique_filename("test_image.tif")
    print(f"  Generated UUID filename: {filename}")
    assert filename.endswith(".tif"), "Extension not preserved"
    assert len(filename) == 40, "UUID filename format incorrect"
    print("  ✓ UUID format correct")

    # Test 3: Save file
    print("\nTest 3: Saving test file...")
    test_content = b"test data for storage service"
    storage_file = save_uploaded_file("test_scan.tif", test_content)
    print(f"  Original filename: {storage_file.original_filename}")
    print(f"  Saved filename: {storage_file.saved_filename}")
    print(f"  Full path: {storage_file.full_path}")
    assert file_exists(storage_file.full_path), "File not saved"
    print("  ✓ File saved successfully")

    # Test 4: Output paths
    print("\nTest 4: Generating output paths...")
    heatmap_path = get_heatmap_output_path(scan_id=1)
    print(f"  Heatmap path: {heatmap_path}")
    assert "heatmaps" in heatmap_path, "Heatmap path incorrect"
    print("  ✓ Heatmap path correct")

    artifact_path = get_artifact_output_path(scan_id=1, artifact_type="analysis", extension="json")
    print(f"  Artifact path: {artifact_path}")
    assert "artifacts" in artifact_path, "Artifact path incorrect"
    assert "scan_1" in artifact_path, "Scan ID not in path"
    print("  ✓ Artifact path correct")

    # Test 5: Cleanup
    print("\nTest 5: Cleanup...")
    deleted = delete_file(storage_file.full_path)
    assert deleted, "File not deleted"
    assert not file_exists(storage_file.full_path), "File still exists"
    print("  ✓ File deleted successfully")

    print("\n" + "="*60)
    print("✓ ALL STORAGE SERVICE TESTS PASSED")
    print("="*60)

if __name__ == "__main__":
    test_storage_service()
