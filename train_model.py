"""
train_model.py

Train a RandomForestClassifier for plant nutrient stress detection.

What it does:
- Loads feature CSV data
- Splits train/test
- Trains RandomForestClassifier
- Prints classification metrics
- Saves model to models_store/stress_model.pkl
- Saves feature column order for inference compatibility

Expected CSV:
- One label column (default: 'label')
- Numeric feature columns
- Non-numeric columns (except label) are ignored automatically

Example:
  backend/venv/bin/python train_model.py \
    --data-csv training_features.csv \
    --label-col label
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import numpy as np


MODEL_DIR = Path("models_store")
MODEL_PATH = MODEL_DIR / "stress_model.pkl"
FEATURE_ORDER_PATH = MODEL_DIR / "feature_columns.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train RandomForest model for plant stress classification")
    parser.add_argument("--data-csv", type=Path, default=None, help="Path to input feature CSV")
    parser.add_argument("--manifest", type=Path, default=None, help="Path to CSV manifest with id,label")
    parser.add_argument("--npy-dir", type=Path, default=None, help="Directory containing NPY files referenced by manifest")
    parser.add_argument("--save-generated-csv", type=Path, default=None, help="Optional output path to save generated feature table")
    parser.add_argument("--label-col", type=str, default="label", help="Label/target column name")
    parser.add_argument("--test-size", type=float, default=0.2, help="Test split ratio (default: 0.2)")
    parser.add_argument("--random-state", type=int, default=42, help="Random seed")
    parser.add_argument("--n-estimators", type=int, default=300, help="Number of trees")
    parser.add_argument("--max-depth", type=int, default=None, help="Optional tree max depth")
    parser.add_argument("--nir-band", type=int, default=5, help="Default NIR band index (1-based) for NPY feature extraction")
    parser.add_argument("--red-edge-band", type=int, default=4, help="Default red-edge band index (1-based) for NPY feature extraction")
    parser.add_argument("--red-band", type=int, default=None, help="Optional red band index (1-based) for NDVI feature extraction")
    parser.add_argument("--search-best", action="store_true", help="Search multiple model families and pick best CV accuracy")
    parser.add_argument(
        "--label-mode",
        type=str,
        choices=["auto", "multiclass", "multiclass-4way", "bin2", "bin3", "bin5"],
        default="auto",
        help="Label handling strategy: auto, multiclass, multiclass-4way, bin2, bin3, or bin5",
    )
    parser.add_argument(
        "--multiclass-map",
        type=str,
        choices=["stress-intensity", "stress-type"],
        default="stress-intensity",
        help="Multiclass mapping strategy: stress-intensity (0-15 healthy, 16-40 nutrient, 41-75 drought, 76-100 disease) or stress-type (custom)",
    )
    parser.add_argument(
        "--bin2-threshold",
        type=float,
        default=10.0,
        help="Threshold for bin2 mode: <= threshold is 'low', > threshold is 'high'",
    )
    return parser.parse_args()


def _is_float(value: str) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def load_feature_csv(path: Path, label_col: str) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Load CSV, keep numeric features, return X, y, and feature column order."""
    if not path.exists() or not path.is_file():
        raise ValueError(f"Input CSV not found: {path}")

    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV is missing a header row")

        header = [h.strip() for h in reader.fieldnames]
        if label_col not in header:
            raise ValueError(f"Label column '{label_col}' not found in CSV header")

        rows = [row for row in reader]

    if not rows:
        raise ValueError("CSV has no data rows")

    # Determine numeric feature columns from row data while preserving original column order.
    candidate_cols = [c for c in header if c != label_col]
    numeric_cols: list[str] = []

    for col in candidate_cols:
        # Keep column only if all non-empty values are numeric.
        valid = True
        for row in rows:
            raw = (row.get(col) or "").strip()
            if raw == "":
                continue
            if not _is_float(raw):
                valid = False
                break
        if valid:
            numeric_cols.append(col)

    if not numeric_cols:
        raise ValueError("No numeric feature columns found")

    X_list: list[list[float]] = []
    y_list: list[str] = []

    for row in rows:
        y_val = (row.get(label_col) or "").strip()
        if y_val == "":
            continue

        feat_row: list[float] = []
        row_has_bad_value = False

        for col in numeric_cols:
            raw = (row.get(col) or "").strip()
            if raw == "":
                feat_row.append(np.nan)
                continue
            if not _is_float(raw):
                row_has_bad_value = True
                break
            feat_row.append(float(raw))

        if row_has_bad_value:
            continue

        X_list.append(feat_row)
        y_list.append(y_val)

    if not X_list:
        raise ValueError("No valid training rows after cleaning")

    X = np.asarray(X_list, dtype=np.float32)
    y = np.asarray(y_list)

    X = _impute_nan_columns(X)

    return X, y, numeric_cols


def _write_generated_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def load_features_from_manifest(
    manifest_path: Path,
    npy_dir: Path,
    label_col: str,
    nir_band: int,
    red_edge_band: int,
    red_band: int | None,
    save_generated_csv: Path | None,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Extract tabular features from manifest + NPY samples."""
    from prepare_dataset import collect_from_manifest, extract_features

    specs = collect_from_manifest(
        manifest_path=manifest_path,
        default_nir_band=nir_band,
        default_red_edge_band=red_edge_band,
        default_red_band=red_band,
        base_dir=npy_dir,
    )

    rows: list[dict[str, Any]] = []
    skipped_missing = 0
    skipped_invalid = 0

    for i, spec in enumerate(specs, start=1):
        if not spec.file_path.exists():
            skipped_missing += 1
            continue

        try:
            row = extract_features(spec)
        except Exception:
            skipped_invalid += 1
            continue

        if label_col not in row or str(row.get(label_col, "")).strip() == "":
            skipped_invalid += 1
            continue

        rows.append(row)
        if i % 250 == 0 or i == len(specs):
            print(f"Feature extraction progress: {i}/{len(specs)}")

    if not rows:
        raise ValueError("No valid rows extracted from manifest + NPY data")

    feature_cols = [c for c in rows[0].keys() if c not in {label_col, "file_path"}]

    def as_float(value: Any) -> float:
        if value is None:
            return float("nan")
        if isinstance(value, str) and value.strip() == "":
            return float("nan")
        return float(value)

    X = np.asarray([[as_float(r[c]) for c in feature_cols] for r in rows], dtype=np.float32)
    y = np.asarray([str(r[label_col]).strip() for r in rows])

    X = _impute_nan_columns(X)

    if save_generated_csv is not None:
        _write_generated_csv(save_generated_csv, rows)
        print(f"Saved generated feature CSV: {save_generated_csv}")

    print("=" * 64)
    print("Manifest/NPY ingestion summary")
    print("=" * 64)
    print(f"Manifest rows read           : {len(specs)}")
    print(f"Rows used for training       : {len(rows)}")
    print(f"Rows skipped (missing files) : {skipped_missing}")
    print(f"Rows skipped (invalid data)  : {skipped_invalid}")

    return X, y, feature_cols


def load_training_data(args: argparse.Namespace) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Load training data from either feature CSV or manifest+NPY sources."""
    if args.data_csv and (args.manifest or args.npy_dir):
        raise ValueError("Use either --data-csv OR --manifest with --npy-dir, not both")

    if args.data_csv:
        return load_feature_csv(args.data_csv, args.label_col)

    if args.manifest and args.npy_dir:
        return load_features_from_manifest(
            manifest_path=args.manifest,
            npy_dir=args.npy_dir,
            label_col=args.label_col,
            nir_band=args.nir_band,
            red_edge_band=args.red_edge_band,
            red_band=args.red_band,
            save_generated_csv=args.save_generated_csv,
        )

    raise ValueError("Provide --data-csv OR both --manifest and --npy-dir")


def _labels_are_numeric(y: np.ndarray) -> bool:
    try:
        np.asarray([float(v) for v in y], dtype=np.float32)
        return True
    except (TypeError, ValueError):
        return False


def _impute_nan_columns(X: np.ndarray) -> np.ndarray:
    """Replace NaNs using per-column medians; fallback to 0 for all-NaN columns."""
    medians = np.zeros(X.shape[1], dtype=np.float32)
    for idx in range(X.shape[1]):
        col = X[:, idx]
        finite = col[np.isfinite(col)]
        medians[idx] = float(np.median(finite)) if finite.size > 0 else 0.0

    inds = np.where(np.isnan(X))
    if inds[0].size > 0:
        X[inds] = np.take(medians, inds[1])
    return X


def _bin_labels(
    y: np.ndarray,
    mode: str,
    bin2_threshold: float,
    multiclass_thresholds: tuple[float, float, float] | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    yn = np.asarray([float(v) for v in y], dtype=np.float32)
    if mode == "bin2":
        binned = np.where(yn <= float(bin2_threshold), "low", "high")
        meta = {
            "label_mode": "bin2",
            "bin2_threshold": float(bin2_threshold),
        }
        return np.asarray(binned), meta

    if mode == "bin3":
        binned = np.where(yn <= 33.0, "low", np.where(yn <= 66.0, "mid", "high"))
        meta = {"label_mode": "bin3", "bin_edges": [-1.0, 33.0, 66.0, 101.0]}
        return np.asarray(binned), meta

    if mode == "bin5":
        def bin5(v: float) -> str:
            if v <= 20.0:
                return "vlow"
            if v <= 40.0:
                return "low"
            if v <= 60.0:
                return "mid"
            if v <= 80.0:
                return "high"
            return "vhigh"

        binned = np.asarray([bin5(v) for v in yn])
        meta = {"label_mode": "bin5", "bin_edges": [-1.0, 20.0, 40.0, 60.0, 80.0, 101.0]}
        return binned, meta

    if mode == "multiclass-4way":
        t1, t2, t3 = multiclass_thresholds or (15.0, 40.0, 75.0)

        def bin4way(v: float) -> str:
            """Map numeric stress to 4 stress types based on stress intensity patterns."""
            if v <= t1:
                return "healthy"
            elif v <= t2:
                return "nutrient_like_stress"
            elif v <= t3:
                return "drought_like_stress"
            else:
                return "disease_like_stress"

        binned = np.asarray([bin4way(v) for v in yn])
        meta = {
            "label_mode": "multiclass-4way",
            "bin_edges": [0.0, float(t1), float(t2), float(t3), 100.0],
            "optimized_thresholds": (float(t1), float(t2), float(t3)),
            "class_labels": ["healthy", "nutrient_like_stress", "drought_like_stress", "disease_like_stress"],
            "class_descriptions": {
                "healthy": "Plant is in good health with minimal stress indicators",
                "nutrient_like_stress": "Moderate stress with patterns consistent with nutrient deficiency (yellowing, uniform distribution)",
                "drought_like_stress": "High stress with patterns consistent with drought (wilting, edge necrosis, scattered distribution)",
                "disease_like_stress": "Severe stress with patterns consistent with disease (irregular patches, high variability, local damage)",
            },
        }
        return binned, meta

    return y, {"label_mode": "multiclass"}


def _search_multiclass_thresholds(
    X: np.ndarray,
    y_numeric: np.ndarray,
    random_state: int,
) -> tuple[tuple[float, float, float], float]:
    from sklearn.ensemble import ExtraTreesClassifier
    from sklearn.model_selection import StratifiedKFold, cross_val_score

    grid_1 = [12.0, 15.0, 18.0]
    grid_2 = [35.0, 40.0, 45.0]
    grid_3 = [70.0, 75.0, 80.0]

    model = ExtraTreesClassifier(
        n_estimators=150,
        max_depth=None,
        min_samples_leaf=1,
        bootstrap=True,
        random_state=random_state,
        n_jobs=-1,
        class_weight="balanced_subsample",
    )
    cv = StratifiedKFold(n_splits=2, shuffle=True, random_state=random_state)

    best_thresholds = (15.0, 40.0, 75.0)
    best_score = -1.0

    for t1 in grid_1:
        for t2 in grid_2:
            if t2 <= t1:
                continue
            for t3 in grid_3:
                if t3 <= t2:
                    continue

                y_candidate = np.asarray(
                    [
                        "healthy"
                        if v <= t1
                        else "nutrient_like_stress"
                        if v <= t2
                        else "drought_like_stress"
                        if v <= t3
                        else "disease_like_stress"
                        for v in y_numeric
                    ]
                )

                counts = np.bincount(
                    np.asarray(
                        [
                            0
                            if label == "healthy"
                            else 1
                            if label == "nutrient_like_stress"
                            else 2
                            if label == "drought_like_stress"
                            else 3
                            for label in y_candidate
                        ]
                    ),
                    minlength=4,
                )
                if int(counts.min()) < 3:
                    continue

                scores = cross_val_score(model, X, y_candidate, cv=cv, scoring="accuracy", n_jobs=1)
                mean_score = float(np.mean(scores))
                if mean_score > best_score:
                    best_score = mean_score
                    best_thresholds = (float(t1), float(t2), float(t3))

    return best_thresholds, best_score


def main() -> None:
    args = parse_args()

    try:
        from sklearn.base import clone
        from joblib import dump
        from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier, RandomForestClassifier, VotingClassifier
        from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
        from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
    except ModuleNotFoundError as exc:
        missing = str(exc).split("No module named ")[-1].strip("'\"")
        raise RuntimeError(
            f"Missing dependency: {missing}. Install required ML packages first, e.g.\n"
            f"  backend/venv/bin/pip install scikit-learn joblib"
        ) from exc

    X, y, feature_cols = load_training_data(args)

    chosen_label_mode = args.label_mode
    label_meta: dict[str, Any] = {"label_mode": "multiclass"}

    if chosen_label_mode == "auto":
        if _labels_are_numeric(y) and len(np.unique(y)) > 20:
            chosen_label_mode = "multiclass-4way"
        else:
            chosen_label_mode = "multiclass"

    y_for_split = y
    y_numeric: np.ndarray | None = None

    if chosen_label_mode in {"bin2", "bin3", "bin5", "multiclass-4way"}:
        if not _labels_are_numeric(y):
            raise ValueError(f"Label mode '{chosen_label_mode}' requires numeric labels")
        if chosen_label_mode == "multiclass-4way":
            y_numeric = np.asarray([float(v) for v in y], dtype=np.float32)
            y_for_split, label_meta = _bin_labels(y, chosen_label_mode, args.bin2_threshold)
        else:
            y_for_split, label_meta = _bin_labels(y, chosen_label_mode, args.bin2_threshold)
        print(f"Using label mode: {chosen_label_mode}")
    else:
        label_meta = {"label_mode": "multiclass"}

    if len(np.unique(y_for_split)) < 2:
        raise ValueError("Need at least two classes in the dataset for classification")

    try:
        split_inputs: list[np.ndarray] = [X, y_for_split]
        if y_numeric is not None:
            split_inputs.append(y_numeric)

        split_outputs = train_test_split(
            *split_inputs,
            test_size=args.test_size,
            random_state=args.random_state,
            stratify=y_for_split,
        )

        if y_numeric is not None:
            X_train, X_test, y_train_split, y_test_split, y_numeric_train, y_numeric_test = split_outputs
        else:
            X_train, X_test, y_train_split, y_test_split = split_outputs
            y_numeric_train = y_numeric_test = None
    except ValueError as exc:
        # Some datasets may contain rare classes with <2 rows; stratification fails there.
        if "least populated class" not in str(exc).lower():
            raise
        print("Warning: Falling back to non-stratified split due to sparse classes.")
        split_outputs = train_test_split(
            *split_inputs,
            test_size=args.test_size,
            random_state=args.random_state,
            stratify=None,
        )
        if y_numeric is not None:
            X_train, X_test, y_train_split, y_test_split, y_numeric_train, y_numeric_test = split_outputs
        else:
            X_train, X_test, y_train_split, y_test_split = split_outputs
            y_numeric_train = y_numeric_test = None

    if chosen_label_mode == "multiclass-4way" and y_numeric_train is not None and y_numeric_test is not None:
        optimized_thresholds, threshold_cv = _search_multiclass_thresholds(X_train, y_numeric_train, args.random_state)
        print(
            "Optimized 4-way thresholds: "
            f"{optimized_thresholds[0]:.1f}, {optimized_thresholds[1]:.1f}, {optimized_thresholds[2]:.1f} "
            f"(cv_accuracy={threshold_cv:.4f})"
        )
        y_train, label_meta = _bin_labels(y_numeric_train, chosen_label_mode, args.bin2_threshold, optimized_thresholds)
        y_test, _ = _bin_labels(y_numeric_test, chosen_label_mode, args.bin2_threshold, optimized_thresholds)
        y_full_for_fit, _ = _bin_labels(y_numeric, chosen_label_mode, args.bin2_threshold, optimized_thresholds)
    else:
        y_train, y_test = y_train_split, y_test_split
        y_full_for_fit = y_for_split

    if args.search_best:
        tree_count = max(args.n_estimators, 1000)
        candidates: list[tuple[str, Any]] = [
            (
                "RandomForestClassifier(depth=None)",
                RandomForestClassifier(
                    n_estimators=tree_count,
                    max_depth=None,
                    random_state=args.random_state,
                    n_jobs=-1,
                    class_weight="balanced_subsample",
                ),
            ),
            (
                "RandomForestClassifier(depth=24,leaf=2)",
                RandomForestClassifier(
                    n_estimators=tree_count,
                    max_depth=24,
                    min_samples_leaf=2,
                    random_state=args.random_state,
                    n_jobs=-1,
                    class_weight="balanced_subsample",
                ),
            ),
            (
                "ExtraTreesClassifier(depth=None)",
                ExtraTreesClassifier(
                    n_estimators=tree_count,
                    max_depth=None,
                    random_state=args.random_state,
                    n_jobs=-1,
                    class_weight="balanced_subsample",
                ),
            ),
            (
                "ExtraTreesClassifier(depth=20,leaf=2)",
                ExtraTreesClassifier(
                    n_estimators=tree_count,
                    max_depth=20,
                    min_samples_leaf=2,
                    random_state=args.random_state,
                    n_jobs=-1,
                    class_weight="balanced_subsample",
                ),
            ),
            (
                "HistGradientBoostingClassifier(d12,lr0.03,i1200)",
                HistGradientBoostingClassifier(
                    random_state=args.random_state,
                    max_depth=12,
                    learning_rate=0.03,
                    max_iter=1200,
                    l2_regularization=0.2,
                ),
            ),
            (
                "VotingClassifier(soft:rf+et+hgb)",
                VotingClassifier(
                    estimators=[
                        (
                            "rf",
                            RandomForestClassifier(
                                n_estimators=tree_count,
                                max_depth=None,
                                random_state=args.random_state,
                                n_jobs=-1,
                                class_weight="balanced_subsample",
                            ),
                        ),
                        (
                            "et",
                            ExtraTreesClassifier(
                                n_estimators=tree_count,
                                max_depth=None,
                                random_state=args.random_state,
                                n_jobs=-1,
                                class_weight="balanced_subsample",
                            ),
                        ),
                        (
                            "hgb",
                            HistGradientBoostingClassifier(
                                random_state=args.random_state,
                                max_depth=12,
                                learning_rate=0.03,
                                max_iter=1200,
                                l2_regularization=0.2,
                            ),
                        ),
                    ],
                    voting="soft",
                    n_jobs=1,
                ),
            ),
            (
                "VotingClassifier(soft:rf+hgb)",
                VotingClassifier(
                    estimators=[
                        (
                            "rf",
                            RandomForestClassifier(
                                n_estimators=tree_count,
                                max_depth=24,
                                min_samples_leaf=2,
                                random_state=args.random_state,
                                n_jobs=-1,
                                class_weight="balanced_subsample",
                            ),
                        ),
                        (
                            "hgb",
                            HistGradientBoostingClassifier(
                                random_state=args.random_state,
                                max_depth=14,
                                learning_rate=0.02,
                                max_iter=1600,
                                l2_regularization=0.2,
                            ),
                        ),
                    ],
                    voting="soft",
                    weights=[1.0, 1.2],
                    n_jobs=1,
                ),
            ),
        ]

        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=args.random_state)
        best_name = ""
        best_cv_score = -1.0
        clf: Any = None

        print("\nModel search (5-fold CV on train split):")
        for name, model in candidates:
            scores = cross_val_score(model, X_train, y_train, cv=cv, scoring="accuracy", n_jobs=1)
            mean_score = float(np.mean(scores))
            print(f"- {name:<28} cv_accuracy={mean_score:.4f} (std={float(np.std(scores)):.4f})")
            if mean_score > best_cv_score:
                best_cv_score = mean_score
                best_name = name
                clf = model

        if clf is None:
            raise RuntimeError("Model search failed to choose a classifier")

        print(f"Selected best model: {best_name} (cv_accuracy={best_cv_score:.4f})")
    else:
        if chosen_label_mode == "multiclass-4way":
            clf = ExtraTreesClassifier(
                n_estimators=max(args.n_estimators, 1000),
                max_depth=args.max_depth,
                min_samples_leaf=1,
                bootstrap=True,
                random_state=args.random_state,
                n_jobs=-1,
                class_weight="balanced_subsample",
            )
            best_name = "ExtraTreesClassifier"
        else:
            clf = RandomForestClassifier(
                n_estimators=args.n_estimators,
                max_depth=args.max_depth,
                random_state=args.random_state,
                n_jobs=-1,
                class_weight="balanced",
            )
            best_name = "RandomForestClassifier"
        best_cv_score = None

    clf.fit(X_train, y_train)
    y_pred = clf.predict(X_test)

    acc = accuracy_score(y_test, y_pred)

    print("=" * 64)
    print(f"{best_name} Evaluation")
    print("=" * 64)
    print(f"Rows total      : {len(y)}")
    print(f"Rows train/test : {len(y_train)} / {len(y_test)}")
    print(f"Features used   : {len(feature_cols)}")
    print(f"Accuracy        : {acc:.4f}")
    if best_cv_score is not None:
        print(f"CV Accuracy     : {best_cv_score:.4f}")
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred, digits=4))
    print("Confusion Matrix:")
    print(confusion_matrix(y_test, y_pred))

    final_clf = clone(clf)
    final_clf.fit(X, y_full_for_fit)

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    dump(final_clf, MODEL_PATH)

    with FEATURE_ORDER_PATH.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "feature_columns": feature_cols,
                "label_column": args.label_col,
                "model_type": best_name,
                "label_info": label_meta,
            },
            f,
            indent=2,
        )

    print("\nSaved artifacts:")
    print(f"- Model           : {MODEL_PATH}")
    print(f"- Feature order   : {FEATURE_ORDER_PATH}")


if __name__ == "__main__":
    main()
