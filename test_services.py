#!/usr/bin/env python3
"""Test script for preprocessing and indices services."""

import numpy as np
from app.services import indices

def test_indices_service():
    """Test vegetation indices computation and analysis."""
    
    print("="*60)
    print("INDICES SERVICE TESTS")
    print("="*60)
    
    # Test 1: NDRE computation with sample data
    print("\nTest 1: NDRE Computation")
    print("-" * 40)
    
    # Create sample bands (512x512)
    height, width = 512, 512
    nir = np.random.uniform(100, 200, (height, width)).astype(np.float32)
    red_edge = np.random.uniform(50, 150, (height, width)).astype(np.float32)
    
    ndre = indices.compute_ndre(nir, red_edge)
    
    print(f"  NIR shape: {nir.shape}")
    print(f"  Red Edge shape: {red_edge.shape}")
    print(f"  NDRE shape: {ndre.shape}")
    print(f"  NDRE dtype: {ndre.dtype}")
    print(f"  NDRE range: [{ndre.min():.4f}, {ndre.max():.4f}]")
    assert ndre.dtype == np.float32, "NDRE should be float32"
    assert -1.1 <= ndre.min() <= 1.1, "NDRE should be in reasonable range"
    print("  ✓ NDRE computation correct")
    
    # Test 2: Divide-by-zero handling
    print("\nTest 2: Divide-by-Zero Protection")
    print("-" * 40)
    
    # Create test case with zero denominator
    nir_zero = np.zeros((10, 10), dtype=np.float32)
    red_edge_zero = np.zeros((10, 10), dtype=np.float32)
    
    ndre_zero = indices.compute_ndre(nir_zero, red_edge_zero)
    
    print(f"  Input all zeros, NDRE result: {np.unique(ndre_zero)}")
    assert np.all(ndre_zero == 0.0), "0/0 case should return 0.0"
    print("  ✓ Zero division handled correctly")
    
    # Test 3: Index statistics
    print("\nTest 3: Index Statistics")
    print("-" * 40)
    
    stats = indices.get_index_stats(ndre)
    
    print(f"  Min: {stats.min}")
    print(f"  Max: {stats.max}")
    print(f"  Mean: {stats.mean}")
    print(f"  Std: {stats.std}")
    print(f"  Median: {stats.median}")
    print(f"  Valid count: {stats.count_valid}")
    assert stats.count_valid == height * width, "All pixels should be valid"
    print("  ✓ Statistics computed correctly")
    
    # Test 4: Stress percentage calculation
    print("\nTest 4: Stress Analysis")
    print("-" * 40)
    
    threshold = 0.2
    stress_pct, stressed_count, healthy_count = indices.compute_stress_percentage(
        ndre,
        threshold=threshold
    )
    
    print(f"  Stress threshold: {threshold}")
    print(f"  Stressed pixels: {stressed_count}")
    print(f"  Healthy pixels: {healthy_count}")
    print(f"  Total: {stressed_count + healthy_count}")
    print(f"  Stress percentage: {stress_pct}%")
    assert stressed_count + healthy_count == height * width, "Counts should sum to total"
    assert 0 <= stress_pct <= 100, "Stress percentage should be 0-100"
    print("  ✓ Stress analysis correct")
    
    # Test 5: Complete NDRE analysis
    print("\nTest 5: Complete NDRE Analysis")
    print("-" * 40)
    
    analysis = indices.analyze_ndre(nir, red_edge, stress_threshold=0.2)
    
    print(f"  NDRE array shape: {analysis.ndre_array.shape}")
    print(f"  Mean NDRE: {analysis.stats.mean}")
    print(f"  Stress: {analysis.stress_percentage}%")
    print(f"  Healthy: {analysis.healthy_count}")
    print(f"  Stressed: {analysis.stressed_count}")
    assert analysis.ndre_array.shape == (height, width), "Shape should match input"
    print("  ✓ Complete analysis computed")
    
    # Test 6: Health status classification
    print("\nTest 6: Health Status Classification")
    print("-" * 40)
    
    test_cases = [
        (5.0, "healthy"),
        (25.0, "at_risk"),
        (75.0, "stressed"),
    ]
    
    for stress_pct, expected_status in test_cases:
        status = indices.classify_health_status(stress_pct)
        print(f"  {stress_pct}% stress → {status}")
        assert status == expected_status, f"Expected {expected_status}, got {status}"
    print("  ✓ Health classification correct")
    
    # Test 7: Vegetation vigor
    print("\nTest 7: Vegetation Vigor Scoring")
    print("-" * 40)
    
    vigor = indices.compute_vegetation_vigor(stats)
    
    print(f"  Mean NDRE: {stats.mean}")
    print(f"  Vigor score (0-100): {vigor}")
    assert 0 <= vigor <= 100, "Vigor should be 0-100"
    print("  ✓ Vigor score computed")
    
    # Test 8: Edge cases
    print("\nTest 8: Edge Cases")
    print("-" * 40)
    
    # Test with NaN values
    ndre_with_nan = ndre.copy()
    ndre_with_nan[0, 0] = np.nan
    ndre_with_nan[1, 1] = np.inf
    
    stats_nan = indices.get_index_stats(ndre_with_nan)
    print(f"  With NaN/inf: valid count = {stats_nan.count_valid}")
    assert stats_nan.count_valid == height * width - 2, "Should exclude NaN/inf"
    print("  ✓ NaN/inf handling correct")
    
    # Test small array
    small_nir = np.array([[100.0, 120.0], [110.0, 130.0]], dtype=np.float32)
    small_red = np.array([[50.0, 60.0], [55.0, 65.0]], dtype=np.float32)
    small_ndre = indices.compute_ndre(small_nir, small_red)
    print(f"  Small array: {small_ndre.shape}")
    assert small_ndre.shape == (2, 2), "Shape preservation failed"
    print("  ✓ Small arrays handled")
    
    print("\n" + "="*60)
    print("✓ ALL INDICES TESTS PASSED")
    print("="*60)


def test_ndvi_computation():
    """Test NDVI computation."""
    
    print("\n" + "="*60)
    print("NDVI COMPUTATION TEST")
    print("="*60)
    
    nir = np.random.uniform(100, 200, (256, 256)).astype(np.float32)
    red = np.random.uniform(50, 100, (256, 256)).astype(np.float32)
    
    ndvi = indices.compute_ndvi(nir, red)
    
    print(f"\nNDVI shape: {ndvi.shape}")
    print(f"NDVI range: [{ndvi.min():.4f}, {ndvi.max():.4f}]")
    assert ndvi.dtype == np.float32, "NDVI should be float32"
    print("✓ NDVI computation works")


if __name__ == "__main__":
    test_indices_service()
    test_ndvi_computation()
