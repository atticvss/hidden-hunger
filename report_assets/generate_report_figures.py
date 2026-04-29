"""Generate report-ready evaluation figures for the Hidden Hunger project."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from joblib import load
from sklearn.base import clone
from sklearn.metrics import ConfusionMatrixDisplay, classification_report
from sklearn.model_selection import StratifiedKFold, learning_curve, train_test_split


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_CSV = ROOT / "training_features_ot_full.csv"
DEFAULT_MODEL_PATH = ROOT / "models_store" / "stress_model.pkl"
DEFAULT_META_PATH = ROOT / "models_store" / "feature_columns.json"
DEFAULT_OUTPUT_DIR = ROOT / "report_assets" / "generated"


plt.style.use("seaborn-v0_8-whitegrid")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate report figures for the Hidden Hunger model.")
    parser.add_argument("--data-csv", type=Path, default=DEFAULT_DATA_CSV, help="Feature CSV used for training")
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH, help="Trained model artifact")
    parser.add_argument("--meta-path", type=Path, default=DEFAULT_META_PATH, help="Feature metadata JSON")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for generated figures")
    parser.add_argument("--random-state", type=int, default=42, help="Split seed used for evaluation")
    parser.add_argument("--test-size", type=float, default=0.2, help="Held-out evaluation split ratio")
    return parser.parse_args()


def _is_float(value: str) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _impute_nan_columns(X: np.ndarray) -> np.ndarray:
    medians = np.zeros(X.shape[1], dtype=np.float32)
    for idx in range(X.shape[1]):
        col = X[:, idx]
        finite = col[np.isfinite(col)]
        medians[idx] = float(np.median(finite)) if finite.size > 0 else 0.0

    inds = np.where(np.isnan(X))
    if inds[0].size > 0:
        X[inds] = np.take(medians, inds[1])
    return X


def load_feature_csv(path: Path, label_col: str) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Load numeric features from a CSV and return X, y, and feature names."""
    if not path.exists():
        raise FileNotFoundError(f"Training CSV not found: {path}")

    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV is missing a header row")
        header = [field.strip() for field in reader.fieldnames]
        if label_col not in header:
            raise ValueError(f"Label column '{label_col}' not found in {path}")
        rows = list(reader)

    feature_cols: list[str] = []
    for col in header:
        if col == label_col:
            continue
        valid = True
        for row in rows:
            raw = (row.get(col) or "").strip()
            if raw and not _is_float(raw):
                valid = False
                break
        if valid:
            feature_cols.append(col)

    X_rows: list[list[float]] = []
    y_rows: list[str] = []
    for row in rows:
        y_val = (row.get(label_col) or "").strip()
        if not y_val:
            continue

        features: list[float] = []
        bad_row = False
        for col in feature_cols:
            raw = (row.get(col) or "").strip()
            if not raw:
                features.append(np.nan)
                continue
            if not _is_float(raw):
                bad_row = True
                break
            features.append(float(raw))

        if bad_row:
            continue

        X_rows.append(features)
        y_rows.append(y_val)

    X = np.asarray(X_rows, dtype=np.float32)
    y = np.asarray(y_rows)
    X = _impute_nan_columns(X)
    return X, y, feature_cols


def map_multiclass_labels(y: np.ndarray, meta: dict) -> np.ndarray:
    """Apply the same numeric stress-to-class mapping used in training."""
    label_info = meta.get("label_info", {})
    mode = label_info.get("label_mode", "multiclass")
    if mode != "multiclass-4way":
        return y.astype(str)

    thresholds = label_info.get("optimized_thresholds")
    if thresholds and len(thresholds) == 3:
        t1, t2, t3 = (float(t) for t in thresholds)
    else:
        t1, t2, t3 = (15.0, 40.0, 75.0)

    values = np.asarray([float(v) for v in y], dtype=np.float32)

    def bucket(v: float) -> str:
        if v <= t1:
            return "healthy"
        if v <= t2:
            return "nutrient_like_stress"
        if v <= t3:
            return "drought_like_stress"
        return "disease_like_stress"

    return np.asarray([bucket(v) for v in values])


def prepare_dataset(data_csv: Path, meta: dict) -> tuple[np.ndarray, np.ndarray, list[str], list[str]]:
    label_col = str(meta.get("label_column", "label"))
    X, y_raw, feature_cols = load_feature_csv(data_csv, label_col=label_col)
    y = map_multiclass_labels(y_raw, meta)

    class_labels = meta.get("label_info", {}).get(
        "class_labels",
        ["healthy", "nutrient_like_stress", "drought_like_stress", "disease_like_stress"],
    )
    return X, y, feature_cols, [str(label) for label in class_labels]


def split_dataset(
    X: np.ndarray,
    y: np.ndarray,
    *,
    test_size: float,
    random_state: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Reproduce the held-out evaluation split used by training."""
    return train_test_split(
        X,
        y,
        test_size=test_size,
        random_state=random_state,
        stratify=y,
    )


def save_figure(fig: plt.Figure, base_path: Path) -> None:
    """Save each figure as both PNG and SVG."""
    fig.savefig(base_path.with_suffix(".png"), dpi=220, bbox_inches="tight")
    fig.savefig(base_path.with_suffix(".svg"), bbox_inches="tight")
    plt.close(fig)


def plot_learning_curve(estimator, X: np.ndarray, y: np.ndarray, output_dir: Path) -> None:
    """Create a train-vs-validation accuracy curve over increasing dataset sizes."""
    curve_estimator = clone(estimator)
    if hasattr(curve_estimator, "n_estimators"):
        curve_estimator.set_params(n_estimators=min(160, int(curve_estimator.n_estimators)))

    train_sizes, train_scores, val_scores = learning_curve(
        curve_estimator,
        X,
        y,
        train_sizes=np.linspace(0.25, 1.0, 5),
        cv=StratifiedKFold(n_splits=5, shuffle=True, random_state=42),
        scoring="accuracy",
        n_jobs=1,
    )

    train_mean = np.mean(train_scores, axis=1)
    train_std = np.std(train_scores, axis=1)
    val_mean = np.mean(val_scores, axis=1)
    val_std = np.std(val_scores, axis=1)
    best_idx = int(np.argmax(val_mean))

    fig, ax = plt.subplots(figsize=(10.5, 6.2))
    ax.plot(train_sizes, train_mean, marker="o", linewidth=2.2, color="#1d4ed8", label="Training Accuracy")
    ax.plot(train_sizes, val_mean, marker="o", linewidth=2.2, color="#dc2626", label="Validation Accuracy")
    ax.fill_between(train_sizes, train_mean - train_std, train_mean + train_std, color="#93c5fd", alpha=0.25)
    ax.fill_between(train_sizes, val_mean - val_std, val_mean + val_std, color="#fca5a5", alpha=0.18)
    ax.axvline(train_sizes[best_idx], linestyle="--", color="#15803d", linewidth=1.6, label=f"Best Validation Size ({int(train_sizes[best_idx])} rows)")

    ax.set_title(
        "Hidden Hunger Model Learning Curve\nTraining accuracy remains strong while validation performance saturates gradually",
        fontsize=15,
        pad=12,
    )
    ax.set_xlabel("Training Samples", fontsize=12)
    ax.set_ylabel("Accuracy", fontsize=12)
    ax.set_ylim(0.0, 1.02)
    ax.legend(loc="lower right", frameon=True)
    ax.grid(True, alpha=0.25)
    save_figure(fig, output_dir / "figure_1_learning_curve")


def plot_class_distribution(y: np.ndarray, class_labels: list[str], output_dir: Path) -> None:
    """Plot the dataset class balance."""
    counts = [int(np.sum(y == label)) for label in class_labels]
    labels = [label.replace("_", "\n") for label in class_labels]
    colors = ["#16a34a", "#f59e0b", "#ea580c", "#dc2626"]

    fig, ax = plt.subplots(figsize=(9.6, 5.8))
    bars = ax.bar(labels, counts, color=colors, alpha=0.88)
    ax.set_title("Hidden Hunger Dataset Class Distribution", fontsize=15, pad=12)
    ax.set_ylabel("Number of Samples", fontsize=12)
    ax.set_xlabel("Stress Class", fontsize=12)
    ax.grid(axis="y", alpha=0.25)

    total = max(1, len(y))
    for bar, count in zip(bars, counts):
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            bar.get_height() + max(counts) * 0.02,
            f"{count}\n({(count / total) * 100:.1f}%)",
            ha="center",
            va="bottom",
            fontsize=10,
        )

    save_figure(fig, output_dir / "figure_2_class_distribution")


def plot_confusion_matrix(model, X_test: np.ndarray, y_test: np.ndarray, class_labels: list[str], output_dir: Path) -> None:
    """Plot the held-out confusion matrix."""
    fig, ax = plt.subplots(figsize=(8.8, 7.4))
    ConfusionMatrixDisplay.from_estimator(
        model,
        X_test,
        y_test,
        display_labels=[label.replace("_", "\n") for label in class_labels],
        cmap="YlGnBu",
        colorbar=True,
        ax=ax,
        xticks_rotation=18,
    )
    ax.set_title("Hidden Hunger Multiclass Confusion Matrix (Held-out Test Set)", fontsize=14, pad=10)
    save_figure(fig, output_dir / "figure_3_confusion_matrix")


def plot_feature_importance(model, feature_cols: list[str], output_dir: Path, top_k: int = 12) -> None:
    """Plot the top feature importances from the trained forest."""
    importances = getattr(model, "feature_importances_", None)
    if importances is None:
        return

    importances = np.asarray(importances, dtype=np.float32)
    order = np.argsort(importances)[::-1][:top_k]
    values = importances[order][::-1]
    labels = [feature_cols[idx] for idx in order][::-1]

    fig, ax = plt.subplots(figsize=(10.4, 7.0))
    ax.barh(labels, values, color="#0f766e", alpha=0.9)
    ax.set_title("Top Feature Importances in the Hidden Hunger Random Forest", fontsize=15, pad=12)
    ax.set_xlabel("Importance Score", fontsize=12)
    ax.set_ylabel("Feature", fontsize=12)
    ax.grid(axis="x", alpha=0.25)
    save_figure(fig, output_dir / "figure_4_feature_importance")


def plot_confidence_histogram(model, X_test: np.ndarray, y_test: np.ndarray, output_dir: Path) -> None:
    """Plot confidence distributions for correct vs incorrect predictions."""
    if not hasattr(model, "predict_proba"):
        return

    probs = model.predict_proba(X_test)
    preds = model.classes_[np.argmax(probs, axis=1)]
    confidences = np.max(probs, axis=1)
    correct_mask = preds == y_test

    fig, ax = plt.subplots(figsize=(9.8, 5.8))
    ax.hist(confidences[correct_mask], bins=12, alpha=0.72, color="#2563eb", label="Correct Predictions")
    ax.hist(confidences[~correct_mask], bins=12, alpha=0.72, color="#dc2626", label="Incorrect Predictions")
    ax.axvline(float(np.mean(confidences)), linestyle="--", color="#15803d", linewidth=1.6, label=f"Mean Confidence ({np.mean(confidences):.2f})")
    ax.set_title("Prediction Confidence Distribution on the Held-out Test Set", fontsize=15, pad=12)
    ax.set_xlabel("Model Confidence", fontsize=12)
    ax.set_ylabel("Number of Samples", fontsize=12)
    ax.legend(frameon=True)
    ax.grid(axis="y", alpha=0.25)
    save_figure(fig, output_dir / "figure_5_confidence_histogram")


def plot_metric_bars(y_test: np.ndarray, y_pred: np.ndarray, class_labels: list[str], output_dir: Path) -> None:
    """Plot precision, recall, and F1-score by class."""
    report = classification_report(y_test, y_pred, labels=class_labels, output_dict=True, zero_division=0)
    precision = [report[label]["precision"] for label in class_labels]
    recall = [report[label]["recall"] for label in class_labels]
    f1 = [report[label]["f1-score"] for label in class_labels]

    x = np.arange(len(class_labels))
    width = 0.23
    display_labels = [label.replace("_", "\n") for label in class_labels]

    fig, ax = plt.subplots(figsize=(10.8, 6.1))
    ax.bar(x - width, precision, width, label="Precision", color="#2563eb")
    ax.bar(x, recall, width, label="Recall", color="#f59e0b")
    ax.bar(x + width, f1, width, label="F1-score", color="#059669")

    ax.set_title("Per-class Evaluation Metrics on the Held-out Test Set", fontsize=15, pad=12)
    ax.set_ylabel("Score", fontsize=12)
    ax.set_xlabel("Stress Class", fontsize=12)
    ax.set_xticks(x)
    ax.set_xticklabels(display_labels)
    ax.set_ylim(0.0, 1.0)
    ax.legend(frameon=True)
    ax.grid(axis="y", alpha=0.25)
    save_figure(fig, output_dir / "figure_6_per_class_metrics")


def write_caption_guide(output_dir: Path, summary: dict[str, float]) -> None:
    """Write a small caption helper for the generated figures."""
    caption_text = f"""# Report Figure Guide

Generated on this project for direct use in the report.

## Suggested captions

1. `figure_1_learning_curve`
   Hidden Hunger learning curve showing training and validation accuracy as the number of training samples increases. Validation performance saturates gradually, indicating limited but stable generalization on the current dataset.

2. `figure_2_class_distribution`
   Distribution of the four stress classes used for multiclass training. The dataset is moderately imbalanced, with drought-like stress contributing the largest share of samples.

3. `figure_3_confusion_matrix`
   Confusion matrix of the multiclass Random Forest model on the held-out test split. The strongest confusion appears between adjacent stress-severity classes.

4. `figure_4_feature_importance`
   Top feature importances learned by the Random Forest classifier. Stress percentage and vegetation-index summary features dominate the decision process.

5. `figure_5_confidence_histogram`
   Distribution of prediction confidence on the held-out test set. Correct predictions tend to cluster at slightly higher confidence than incorrect predictions.

6. `figure_6_per_class_metrics`
   Precision, recall, and F1-score per class for the held-out test set, highlighting stronger recall for drought-like stress and weaker performance on the healthy class.

## Current summary values

- Held-out accuracy: {summary["accuracy"]:.4f}
- Train rows: {int(summary["train_rows"])}
- Test rows: {int(summary["test_rows"])}
- Feature count: {int(summary["feature_count"])}

## Putting figures into the report

- In Word/Google Docs:
  Insert -> Image -> Upload from computer, then choose the PNG files from `report_assets/generated/`.
- In Markdown:
  `![Learning Curve](report_assets/generated/figure_1_learning_curve.png)`
- In LaTeX:
  `\\includegraphics[width=\\linewidth]{{report_assets/generated/figure_1_learning_curve.png}}`

Use PNG for quick report insertion and SVG when you want cleaner scaling in design tools.
"""
    (output_dir / "REPORT_FIGURES.md").write_text(caption_text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    meta = json.loads(args.meta_path.read_text(encoding="utf-8"))
    X, y, feature_cols, class_labels = prepare_dataset(args.data_csv, meta)
    model = load(args.model_path)

    X_train, X_test, y_train, y_test = split_dataset(
        X,
        y,
        test_size=args.test_size,
        random_state=args.random_state,
    )
    y_pred = model.predict(X_test)
    accuracy = float(np.mean(y_pred == y_test))

    print("Generating learning curve...")
    plot_learning_curve(model, X, y, args.output_dir)
    print("Generating class distribution...")
    plot_class_distribution(y, class_labels, args.output_dir)
    print("Generating confusion matrix...")
    plot_confusion_matrix(model, X_test, y_test, class_labels, args.output_dir)
    print("Generating feature importance chart...")
    plot_feature_importance(model, feature_cols, args.output_dir)
    print("Generating confidence histogram...")
    plot_confidence_histogram(model, X_test, y_test, args.output_dir)
    print("Generating per-class metric bars...")
    plot_metric_bars(y_test, y_pred, class_labels, args.output_dir)

    write_caption_guide(
        args.output_dir,
        {
            "accuracy": accuracy,
            "train_rows": len(y_train),
            "test_rows": len(y_test),
            "feature_count": len(feature_cols),
        },
    )

    print(f"Generated figures in: {args.output_dir}")
    print(f"Held-out accuracy: {accuracy:.4f}")


if __name__ == "__main__":
    main()
