"""Explainability service for one-sample model explanations with fallback support."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import importlib
from typing import Any, NamedTuple

import numpy as np


class FeatureContribution(NamedTuple):
    """Single feature contribution for one prediction."""

    feature: str
    value: float
    contribution: float
    direction: str


class ExplainabilityResult(NamedTuple):
    """Explainability output suitable for API/frontend display."""

    top_features: list[FeatureContribution]
    feature_values: dict[str, float]
    explanation_summary: str
    method: str


def _prepare_input(feature_vector: list[float] | np.ndarray) -> np.ndarray:
    """Ensure model input has shape (1, n_features)."""
    x = np.asarray(feature_vector, dtype=np.float32)
    if x.ndim == 1:
        x = x.reshape(1, -1)
    if x.ndim != 2 or x.shape[0] != 1:
        raise ValueError("feature_vector must be 1D or shape (1, n_features)")
    return x


def _resolve_feature_names(model: Any, n_features: int, feature_names: list[str] | None) -> list[str]:
    """Resolve feature names from argument or trained model metadata."""
    if feature_names and len(feature_names) == n_features:
        return feature_names

    model_names = getattr(model, "feature_names_in_", None)
    if model_names is not None and len(model_names) == n_features:
        return [str(n) for n in model_names]

    return [f"feature_{i}" for i in range(n_features)]


def _extract_class_shap_values(shap_values: Any, class_index: int, n_features: int) -> np.ndarray:
    """Extract SHAP values for the predicted class across SHAP output formats."""
    if isinstance(shap_values, list):
        if not shap_values:
            return np.zeros(n_features, dtype=np.float32)
        idx = max(0, min(class_index, len(shap_values) - 1))
        return np.asarray(shap_values[idx][0], dtype=np.float32)

    arr = np.asarray(shap_values)

    if arr.ndim == 2:
        return np.asarray(arr[0], dtype=np.float32)

    if arr.ndim == 3 and arr.shape[0] == 1 and arr.shape[1] == n_features:
        idx = max(0, min(class_index, arr.shape[2] - 1))
        return np.asarray(arr[0, :, idx], dtype=np.float32)

    if arr.ndim == 3 and arr.shape[2] == n_features:
        idx = max(0, min(class_index, arr.shape[0] - 1))
        return np.asarray(arr[idx, 0, :], dtype=np.float32)

    return np.zeros(n_features, dtype=np.float32)


def _run_shap_for_one_sample(model: Any, x: np.ndarray, class_index: int) -> np.ndarray:
    """Run SHAP and return one contribution vector for the selected class."""
    shap_module = importlib.import_module("shap")
    explainer = shap_module.TreeExplainer(model)
    shap_values = explainer.shap_values(x)
    return _extract_class_shap_values(shap_values, class_index=class_index, n_features=x.shape[1])


def _model_class_index(model: Any, predicted_class: str) -> int:
    """Return class index for the predicted label."""
    classes = [str(c) for c in getattr(model, "classes_", [])]
    if predicted_class in classes:
        return classes.index(predicted_class)
    return 0


def _build_top_features(
    feature_names: list[str],
    values: np.ndarray,
    contributions: np.ndarray,
    top_k: int,
) -> list[FeatureContribution]:
    """Build ranked top-k contribution list."""
    k = max(1, min(top_k, len(feature_names)))
    ranked_idx = np.argsort(np.abs(contributions))[::-1][:k]
    top: list[FeatureContribution] = []

    for idx in ranked_idx:
        contribution = float(contributions[idx])
        top.append(
            FeatureContribution(
                feature=feature_names[idx],
                value=float(values[idx]),
                contribution=contribution,
                direction="increased" if contribution >= 0 else "decreased",
            )
        )

    return top


def _fallback_contributions(model: Any, x: np.ndarray) -> np.ndarray:
    """Fallback contribution proxy when SHAP is unavailable or too slow."""
    importances = getattr(model, "feature_importances_", None)
    values = np.asarray(x[0], dtype=np.float32)

    if importances is None:
        return np.abs(values)

    imp = np.asarray(importances, dtype=np.float32)
    if imp.shape[0] != values.shape[0]:
        return np.abs(values)

    return np.abs(imp * values)


def _build_summary(
    predicted_class: str,
    confidence: float,
    top_features: list[FeatureContribution],
    method: str,
) -> str:
    """Create beginner-friendly explanation text for UI cards."""
    if not top_features:
        return (
            f"The model predicted {predicted_class} with {confidence * 100:.1f}% confidence. "
            "A feature-level explanation was not available for this sample."
        )

    top_names = ", ".join(f.feature for f in top_features[:3])
    strongest = top_features[0]

    if method == "shap":
        return (
            f"The model predicted {predicted_class} with {confidence * 100:.1f}% confidence. "
            f"The strongest drivers were {top_names}. "
            f"{strongest.feature} ({strongest.value:.4f}) {strongest.direction} the score for this class."
        )

    return (
        f"The model predicted {predicted_class} with {confidence * 100:.1f}% confidence. "
        f"SHAP was unavailable or slow, so a fast feature-importance fallback was used. "
        f"The most influential inputs were {top_names}."
    )


def explain_single_sample(
    model: Any,
    feature_vector: list[float] | np.ndarray,
    predicted_class: str,
    confidence: float,
    feature_names: list[str] | None = None,
    top_k: int = 5,
    timeout_seconds: float = 1.5,
) -> ExplainabilityResult:
    """Explain one uploaded sample with SHAP and fallback importance strategy."""
    x = _prepare_input(feature_vector)
    resolved_names = _resolve_feature_names(model, x.shape[1], feature_names)
    values = np.asarray(x[0], dtype=np.float32)
    class_index = _model_class_index(model, predicted_class=predicted_class)

    method = "shap"
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_run_shap_for_one_sample, model, x, class_index)
            contributions = np.asarray(future.result(timeout=timeout_seconds), dtype=np.float32)
    except (ModuleNotFoundError, ImportError, FutureTimeoutError, Exception):
        method = "feature_importance"
        contributions = _fallback_contributions(model, x)

    top = _build_top_features(
        feature_names=resolved_names,
        values=values,
        contributions=contributions,
        top_k=top_k,
    )

    feature_values = {item.feature: float(item.value) for item in top}
    summary = _build_summary(
        predicted_class=predicted_class,
        confidence=float(confidence),
        top_features=top,
        method=method,
    )

    return ExplainabilityResult(
        top_features=top,
        feature_values=feature_values,
        explanation_summary=summary,
        method=method,
    )


def explain_rule_based(
    features: dict[str, float],
    predicted_class: str,
    confidence: float,
    top_k: int = 5,
) -> ExplainabilityResult:
    """Explain rule-based outputs when no trained model is available."""
    ranked = sorted(features.items(), key=lambda kv: abs(float(kv[1])), reverse=True)[: max(1, top_k)]
    top = [
        FeatureContribution(
            feature=name,
            value=float(value),
            contribution=float(abs(value)),
            direction="increased",
        )
        for name, value in ranked
    ]
    feature_values = {item.feature: float(item.value) for item in top}

    uses_proxy_features = any("proxy" in name or "coverage" in name for name in features)
    key_signal_text = (
        "Key indicators include the proxy health index, foliage coverage, and stress-related color signals."
        if uses_proxy_features
        else "Key indicators include NDRE and stress-related features."
    )

    summary = (
        f"The system predicted {predicted_class} with {confidence * 100:.1f}% confidence. "
        "This explanation uses rule-based signals because a trained model explanation was not available. "
        f"{key_signal_text}"
    )

    return ExplainabilityResult(
        top_features=top,
        feature_values=feature_values,
        explanation_summary=summary,
        method="rule_based",
    )
