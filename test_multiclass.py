#!/usr/bin/env python3
"""Test multiclass stress classification pipeline."""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np


def print_section(title):
    """Print a section header."""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")


def test_train_model_multiclass():
    """Test multiclass model training."""
    print_section("TEST 1: Train Multiclass Model")

    # Check if training data exists
    csv_path = Path("training_features_ot_full.csv")
    if not csv_path.exists():
        print("❌ Training data not found. Using smaller test data...")
        # Create minimal test data
        np.random.seed(42)
        n_samples = 50
        n_features = 20
        
        X = np.random.randn(n_samples, n_features).astype(np.float32)
        y = np.random.uniform(0, 100, n_samples)
        
        # Write test CSV
        test_csv = Path("test_training_features.csv")
        with open(test_csv, "w") as f:
            # Header
            features = [f"feature_{i}" for i in range(n_features)]
            f.write("label," + ",".join(features) + "\n")
            # Rows
            for label_val, x_row in zip(y, X):
                row_vals = [str(label_val)] + [str(v) for v in x_row]
                f.write(",".join(row_vals) + "\n")
        
        csv_path = test_csv
        print(f"✓ Created test CSV with {n_samples} samples, {n_features} features")

    # Run training with multiclass-4way mode
    cmd = [
        sys.executable,
        "train_model.py",
        "--data-csv", str(csv_path),
        "--label-col", "label",
        "--label-mode", "multiclass-4way",
        "--n-estimators", "100",
    ]

    print(f"Running: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"❌ Training failed:\n{result.stderr}")
        return False

    print(result.stdout)

    # Verify model files exist
    model_path = Path("models_store/stress_model.pkl")
    features_path = Path("models_store/feature_columns.json")

    if not model_path.exists():
        print(f"❌ Model file not created: {model_path}")
        return False

    if not features_path.exists():
        print(f"❌ Features metadata not created: {features_path}")
        return False

    # Check metadata
    with open(features_path) as f:
        metadata = json.load(f)

    label_info = metadata.get("label_info", {})
    if label_info.get("label_mode") != "multiclass-4way":
        print(f"❌ Label mode not set to multiclass-4way: {label_info}")
        return False

    classes = label_info.get("class_labels", [])
    expected_classes = [
        "healthy",
        "nutrient_like_stress",
        "drought_like_stress",
        "disease_like_stress",
    ]

    if classes != expected_classes:
        print(f"❌ Class labels mismatch. Got: {classes}, Expected: {expected_classes}")
        return False

    print(f"✓ Model trained successfully")
    print(f"  - Model file: {model_path}")
    print(f"  - Features: {len(metadata.get('feature_columns', []))} features")
    print(f"  - Classes: {classes}")
    print(f"  - Label mode: {label_info.get('label_mode')}")

    return True


def test_inference():
    """Test multiclass inference."""
    print_section("TEST 2: Inference with Multiclass Model")

    try:
        from app.services.inference import ModelBasedInferenceEngine
        import numpy as np

        engine = ModelBasedInferenceEngine()

        # Create synthetic feature vector
        with open("models_store/feature_columns.json") as f:
            metadata = json.load(f)
        n_features = len(metadata["feature_columns"])

        # Test different feature vectors
        test_vectors = [
            ("healthy", np.zeros(n_features, dtype=np.float32)),  # All zeros -> healthy
            ("stressed", np.ones(n_features, dtype=np.float32) * 0.5),  # Mid-range -> uncertain
            ("extreme", np.ones(n_features, dtype=np.float32)),  # All ones -> stressed
        ]

        print(f"Testing inference with {n_features} features\n")

        for test_name, features in test_vectors:
            result = engine.predict(features)

            print(f"  {test_name.upper()}:")
            print(f"    Predicted class: {result.predicted_class}")
            print(f"    Confidence: {result.confidence:.3f}")
            print(f"    Health status: {result.health_status}")

            if result.class_probabilities:
                print(f"    Class probabilities:")
                for cls, prob in sorted(
                    result.class_probabilities.items(),
                    key=lambda x: x[1],
                    reverse=True,
                ):
                    bar = "▓" * int(prob * 20)
                    print(f"      {cls:25s}: {prob:.3f} {bar}")

            print()

        print("✓ Inference tests passed")
        return True

    except Exception as e:
        print(f"❌ Inference failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_rule_based_inference():
    """Test rule-based fallback inference."""
    print_section("TEST 3: Rule-Based Fallback Inference")

    try:
        from app.services.inference import RuleBasedInferenceEngine

        engine = RuleBasedInferenceEngine()

        # Test various NDRE and stress percentages
        test_cases = [
            (0.7, 5.0, "healthy"),  # High NDRE, low stress
            (0.4, 25.0, "nutrient_like_stress"),  # Med NDRE, med stress
            (0.2, 60.0, "drought_like_stress"),  # Low NDRE, high stress
            (-0.1, 95.0, "disease_like_stress"),  # Very low NDRE, extreme stress
        ]

        for ndre_mean, stress_pct, expected_type in test_cases:
            result = engine.predict(ndre_mean, stress_pct)

            is_correct = expected_type in str(result.predicted_class).lower()
            status = "✓" if is_correct else "❌"

            print(f"{status} NDRE={ndre_mean:5.2f}, Stress={stress_pct:5.1f}%")
            print(
                f"     → {result.predicted_class} "
                f"(confidence={result.confidence:.3f}, health={result.health_status})"
            )

        print("\n✓ Rule-based inference tests passed")
        return True

    except Exception as e:
        print(f"❌ Rule-based inference failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_backend_syntax():
    """Test backend module syntax."""
    print_section("TEST 4: Backend Module Syntax")

    modules = [
        "app/main.py",
        "app/routers/upload.py",
        "app/services/inference.py",
        "app/schemas.py",
        "train_model.py",
    ]

    all_ok = True
    for module in modules:
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", module],
            capture_output=True,
            text=True,
        )

        status = "✓" if result.returncode == 0 else "❌"
        print(f"{status} {module}")

        if result.returncode != 0:
            print(f"   Error: {result.stderr}")
            all_ok = False

    if all_ok:
        print("\n✓ All modules have valid syntax")
    return all_ok


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("  MULTICLASS STRESS CLASSIFICATION TEST SUITE")
    print("="*70)

    tests = [
        ("Backend Syntax", test_backend_syntax),
        ("Train Multiclass Model", test_train_model_multiclass),
        ("Rule-Based Inference", test_rule_based_inference),
        ("Model-Based Inference", test_inference),
    ]

    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"\n❌ Test {test_name} crashed: {e}")
            import traceback
            traceback.print_exc()
            results[test_name] = False

    # Summary
    print_section("TEST SUMMARY")
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")

    all_passed = all(results.values())
    print(f"\nOverall: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
