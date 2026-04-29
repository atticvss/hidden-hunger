"""Inference service with model-backed prediction and class probability output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import NamedTuple, Protocol

import numpy as np
from app.errors import MissingModelFilesError


MODEL_PATH = Path("models_store/stress_model.pkl")
FEATURES_PATH = Path("models_store/feature_columns.json")


class InferenceResult(NamedTuple):
    """Standardized inference output used by routers and persistence layers."""

    predicted_class: str
    confidence: float
    class_probabilities: dict[str, float] | None = None
    health_status: str | None = None  # Legacy field for backwards compatibility


class InferenceEngine(Protocol):
    """Contract for inference implementations.

    Any future trained model can implement this interface so calling code does
    not need to change.
    """

    def predict(self, features: np.ndarray) -> InferenceResult:
        """Return stress class prediction from feature vector."""


class ModelBasedInferenceEngine:
    """Trained model-based inference with probability outputs.
    
    Loads a trained classifier and returns class probabilities for all classes.
    """

    def __init__(self):
        """Initialize and load trained model and metadata."""
        if not MODEL_PATH.exists() or not FEATURES_PATH.exists():
            raise MissingModelFilesError(
                message="Model files not found. Please train a model first.",
                model_path=str(MODEL_PATH),
                features_path=str(FEATURES_PATH),
            )

        try:
            from joblib import load
        except ModuleNotFoundError as exc:
            raise RuntimeError("joblib not installed. Install scikit-learn first.") from exc

        self.model = load(MODEL_PATH)
        with FEATURES_PATH.open() as f:
            self.metadata = json.load(f)

        self.feature_columns = self.metadata.get("feature_columns", [])
        self.label_info = self.metadata.get("label_info", {})

    def predict(self, features: np.ndarray) -> InferenceResult:
        """Predict stress class from feature vector and return probabilities.
        
        Args:
            features: Feature vector shaped (num_features,) or (1, num_features).
                     Should have same order as training features.
        
        Returns:
            InferenceResult with predicted_class, confidence, and class_probabilities.
        """
        if features.ndim == 1:
            features = features.reshape(1, -1)
        elif features.ndim != 2 or features.shape[0] != 1:
            raise ValueError(f"Expected features shape (num_features,) or (1, num_features), got {features.shape}")

        # Get class prediction
        prediction = self.model.predict(features)[0]

        # Get class probabilities
        class_probabilities = None
        confidence = 0.0
        
        if hasattr(self.model, "predict_proba"):
            # Model supports probability output
            proba = self.model.predict_proba(features)[0]  # Shape: (num_classes,)
            classes = self.model.classes_  # Class label order
            class_probabilities = {str(cls): float(prob) for cls, prob in zip(classes, proba)}
            confidence = float(np.max(proba))
        elif hasattr(self.model, "estimators_"):
            # Ensemble model; try to extract probabilities from ensemble components
            try:
                proba = self.model.predict_proba(features)[0]
                classes = self.model.classes_
                class_probabilities = {str(cls): float(prob) for cls, prob in zip(classes, proba)}
                confidence = float(np.max(proba))
            except (AttributeError, NotImplementedError):
                # Fallback: use prediction only
                confidence = 0.85
        else:
            # No probability output available
            confidence = 0.85

        # Derive health_status from predicted_class for backwards compatibility
        health_status = self._derive_health_status(str(prediction))

        return InferenceResult(
            predicted_class=str(prediction),
            confidence=confidence,
            class_probabilities=class_probabilities,
            health_status=health_status,
        )

    def _derive_health_status(self, predicted_class: str) -> str:
        """Derive health status from predicted class for backwards compatibility.
        
        Maps multiclass predictions to simple health status:
        - healthy -> "healthy"
        - nutrient_like_stress, drought_like_stress, disease_like_stress -> "stressed"
        """
        pc = str(predicted_class).lower()
        if "healthy" in pc:
            return "healthy"
        else:
            return "stressed"


class RuleBasedInferenceEngine:
    """Baseline rules for plant health prediction.

    Rules use NDRE mean and stress percentage and are intentionally simple,
    deterministic, and easy to replace with a trained model later.
    """

    def predict(self, ndre_mean: float, stress_percentage: float) -> InferenceResult:
        """Predict plant condition using NDRE thresholds.

        Args:
            ndre_mean: Mean NDRE value (typically in range [-1.0, 1.0]).
            stress_percentage: Percentage of stressed pixels (0.0 to 100.0).

        Returns:
            InferenceResult with predicted_class, confidence, and class_probabilities.
        """
        # Clamp to expected ranges for robust behavior with noisy inputs.
        ndre_mean = max(-1.0, min(1.0, float(ndre_mean)))
        stress_percentage = max(0.0, min(100.0, float(stress_percentage)))

        # Determine stress class based on intensity
        # Thresholds tuned to match actual stress distribution (median=49%)
        if stress_percentage <= 25.0:
            predicted_class = "healthy"
            confidence = 0.95
        elif stress_percentage <= 50.0:
            predicted_class = "nutrient_like_stress"
            confidence = 0.80
        elif stress_percentage <= 80.0:
            predicted_class = "drought_like_stress"
            confidence = 0.78
        else:
            predicted_class = "disease_like_stress"
            confidence = 0.76

        # Create class probabilities based on distance to boundaries
        class_probs = self._compute_class_probabilities(stress_percentage)

        health_status = "healthy" if stress_percentage <= 25.0 else "stressed"

        return InferenceResult(
            predicted_class=predicted_class,
            confidence=confidence,
            class_probabilities=class_probs,
            health_status=health_status,
        )

    def _compute_class_probabilities(self, stress_pct: float) -> dict[str, float]:
        """Compute soft probability distribution across classes based on stress percentage."""
        # Gaussian-like distribution centered on each class
        # Centers tuned to match new thresholds (25%, 50%, 80%)
        classes = ["healthy", "nutrient_like_stress", "drought_like_stress", "disease_like_stress"]
        centers = [12.5, 37.5, 65.0, 90.0]
        width = 15.0

        probs = {}
        for cls, center in zip(classes, centers):
            dist = abs(stress_pct - center)
            prob = np.exp(-(dist ** 2) / (2 * width ** 2))
            probs[cls] = float(prob)

        # Normalize
        total = sum(probs.values())
        if total > 0:
            probs = {k: v / total for k, v in probs.items()}

        return probs


def stress_pct_to_health_status(stress_percentage: float) -> str:
    """Convert stress percentage into API health buckets.

    Keeps health status grounded in observed NDRE stress distribution:
    - <=25%: healthy
    - <=50%: at_risk
    - >50%: stressed
    """
    sp = max(0.0, min(100.0, float(stress_percentage)))
    if sp <= 25.0:
        return "healthy"
    if sp <= 50.0:
        return "at_risk"
    return "stressed"


def reconcile_health_status(
    predicted_class: str,
    stress_percentage: float,
    confidence: float,
) -> str:
    """Reconcile model class bucket with NDRE evidence bucket.

    Health status shown to users should prioritize observed stress evidence,
    while the detailed multiclass prediction remains available separately.
    """
    model_bucket = _health_status_from_class(predicted_class)
    evidence_bucket = stress_pct_to_health_status(stress_percentage)

    if model_bucket == evidence_bucket:
        return model_bucket

    # Favor evidence to avoid persistent over-reporting of "stressed".
    _ = confidence  # reserved for future confidence-weighted reconciliation
    return evidence_bucket



def _evidence_health_status(ndre_mean: float, stress_percentage: float) -> str:
    """Compute health status directly from NDRE and stress evidence."""
    rule = RuleBasedInferenceEngine().predict(ndre_mean=ndre_mean, stress_percentage=stress_percentage)
    return rule.health_status


def _reconcile_model_prediction(
    predicted_class: str,
    confidence: float,
    ndre_mean: float,
    stress_percentage: float,
) -> tuple[str, str, float]:
    """Reconcile model class with index-derived evidence.

    This prevents contradictory outputs such as low stress percentage with
    "high"/"stressed" class labels.
    """
    model_health = _health_status_from_class(predicted_class)
    evidence_health = _evidence_health_status(ndre_mean=ndre_mean, stress_percentage=stress_percentage)

    if model_health == evidence_health:
        return model_health, predicted_class, confidence

    # Trust evidence when stress is clearly low and vegetation index is decent.
    if stress_percentage <= 25.0 and ndre_mean >= 0.2:
        if evidence_health == "healthy":
            return "healthy", "low", max(0.65, min(confidence, 0.9))
        return "at_risk", "mid", max(0.6, min(confidence, 0.85))

    # Trust evidence when stress is clearly high and NDRE is weak.
    if stress_percentage >= 60.0 or ndre_mean < 0.12:
        return "stressed", "high", max(0.65, min(confidence, 0.95))

    # Ambiguous zone: report intermediate risk rather than extreme class.
    return "at_risk", "mid", max(0.55, min(confidence, 0.8))


def predict_from_ndre(ndre_mean: float, stress_percentage: float) -> InferenceResult:
    """Convenience function for current API usage.

    This function keeps call-sites simple today and can later delegate to a
    loaded ML model without changing endpoint code.
    """
    engine = RuleBasedInferenceEngine()
    return engine.predict(ndre_mean=ndre_mean, stress_percentage=stress_percentage)


def _safe_normalized_difference(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Compute (a-b)/(a+b) with divide-by-zero protection."""
    denom = a + b
    return np.divide(a - b, denom, out=np.zeros_like(a, dtype=np.float32), where=denom != 0)


def _finite_stats(values: np.ndarray) -> tuple[float, float, float, float]:
    """Return min/max/mean/std over finite values."""
    v = values[np.isfinite(values)]
    if v.size == 0:
        return 0.0, 0.0, 0.0, 0.0
    return float(np.min(v)), float(np.max(v)), float(np.mean(v)), float(np.std(v))


def _percentiles(values: np.ndarray) -> tuple[float, float, float]:
    """Return p10/p50/p90 for finite values."""
    v = values[np.isfinite(values)]
    if v.size == 0:
        return 0.0, 0.0, 0.0
    p10, p50, p90 = np.percentile(v, [10, 50, 90])
    return float(p10), float(p50), float(p90)


def extract_features_from_cube(
    cube: np.ndarray,
    nir_band: int,
    red_edge_band: int,
    red_band: int | None = None,
    stress_threshold: float = 0.2,
) -> dict[str, float]:
    """Extract model features from a hyperspectral cube.

    Args:
        cube: Hyperspectral array with shape (bands, height, width).
        nir_band: NIR band index (1-based).
        red_edge_band: Red-edge band index (1-based).
        red_band: Optional red band index for NDVI (1-based).
        stress_threshold: NDRE threshold used for stress percentage.
    """
    if cube.ndim != 3:
        raise ValueError("Expected cube shape (bands, height, width)")

    total_bands, _, _ = cube.shape
    if not (1 <= nir_band <= total_bands):
        raise ValueError(f"nir_band out of range: {nir_band}, total bands={total_bands}")
    if not (1 <= red_edge_band <= total_bands):
        raise ValueError(f"red_edge_band out of range: {red_edge_band}, total bands={total_bands}")

    cube = np.asarray(cube, dtype=np.float32)
    nir = cube[nir_band - 1]
    red_edge = cube[red_edge_band - 1]

    ndre = _safe_normalized_difference(nir, red_edge)
    ndre_min, ndre_max, ndre_mean, ndre_std = _finite_stats(ndre)
    ndre_p10, ndre_p50, ndre_p90 = _percentiles(ndre)

    valid_ndre = ndre[np.isfinite(ndre)]
    if valid_ndre.size == 0:
        stress_percentage = 0.0
    else:
        stress_percentage = float((valid_ndre < stress_threshold).sum() * 100.0 / valid_ndre.size)

    if red_band is not None and 1 <= red_band <= total_bands:
        red = cube[red_band - 1]
        ndvi = _safe_normalized_difference(nir, red)
        ndvi_min, ndvi_max, ndvi_mean, ndvi_std = _finite_stats(ndvi)
    else:
        ndvi_min = ndvi_max = ndvi_mean = ndvi_std = 0.0

    band_means = np.mean(cube, axis=(1, 2))
    band_stds = np.std(cube, axis=(1, 2))
    band_means_p10, band_means_p50, band_means_p90 = np.percentile(band_means, [10, 50, 90])
    band_stds_p10, band_stds_p50, band_stds_p90 = np.percentile(band_stds, [10, 50, 90])
    spectral_diff = np.diff(band_means)

    split_1 = max(1, total_bands // 3)
    split_2 = max(split_1 + 1, (2 * total_bands) // 3)
    low_region = band_means[:split_1]
    mid_region = band_means[split_1:split_2]
    high_region = band_means[split_2:]

    low_region_mean = float(np.mean(low_region)) if low_region.size > 0 else 0.0
    mid_region_mean = float(np.mean(mid_region)) if mid_region.size > 0 else 0.0
    high_region_mean = float(np.mean(high_region)) if high_region.size > 0 else 0.0

    red_edge_min, red_edge_max, red_edge_mean, red_edge_std = _finite_stats(red_edge)
    red_edge_p10, red_edge_p50, red_edge_p90 = _percentiles(red_edge)

    red_edge_nir_ratio = np.divide(red_edge, nir, out=np.zeros_like(red_edge), where=nir != 0)

    return {
        "height": float(cube.shape[1]),
        "width": float(cube.shape[2]),
        "total_bands": float(total_bands),
        "nir_band": float(nir_band),
        "red_edge_band": float(red_edge_band),
        "red_band": float(red_band) if red_band is not None else 0.0,
        "ndre_min": ndre_min,
        "ndre_max": ndre_max,
        "ndre_mean": ndre_mean,
        "ndre_std": ndre_std,
        "ndre_p10": ndre_p10,
        "ndre_p50": ndre_p50,
        "ndre_p90": ndre_p90,
        "ndvi_min": ndvi_min,
        "ndvi_max": ndvi_max,
        "ndvi_mean": ndvi_mean,
        "ndvi_std": ndvi_std,
        "band_means_mean": float(np.mean(band_means)),
        "band_means_std": float(np.std(band_means)),
        "band_means_p10": float(band_means_p10),
        "band_means_p50": float(band_means_p50),
        "band_means_p90": float(band_means_p90),
        "band_stds_mean": float(np.mean(band_stds)),
        "band_stds_std": float(np.std(band_stds)),
        "band_stds_p10": float(band_stds_p10),
        "band_stds_p50": float(band_stds_p50),
        "band_stds_p90": float(band_stds_p90),
        "spectral_slope_mean": float(np.mean(spectral_diff)) if spectral_diff.size > 0 else 0.0,
        "spectral_slope_std": float(np.std(spectral_diff)) if spectral_diff.size > 0 else 0.0,
        "spectral_slope_min": float(np.min(spectral_diff)) if spectral_diff.size > 0 else 0.0,
        "spectral_slope_max": float(np.max(spectral_diff)) if spectral_diff.size > 0 else 0.0,
        "low_region_mean": low_region_mean,
        "mid_region_mean": mid_region_mean,
        "high_region_mean": high_region_mean,
        "low_mid_ratio": float(low_region_mean / mid_region_mean) if mid_region_mean != 0 else 0.0,
        "mid_high_ratio": float(mid_region_mean / high_region_mean) if high_region_mean != 0 else 0.0,
        "cube_min": float(np.min(cube)),
        "cube_max": float(np.max(cube)),
        "cube_mean": float(np.mean(cube)),
        "cube_std": float(np.std(cube)),
        "red_edge_min": red_edge_min,
        "red_edge_max": red_edge_max,
        "red_edge_mean": red_edge_mean,
        "red_edge_std": red_edge_std,
        "red_edge_p10": red_edge_p10,
        "red_edge_p50": red_edge_p50,
        "red_edge_p90": red_edge_p90,
        "nir_mean": float(np.mean(nir)),
        "nir_std": float(np.std(nir)),
        "red_edge_nir_diff_mean": float(np.mean(nir - red_edge)),
        "red_edge_nir_ratio_mean": float(np.mean(red_edge_nir_ratio)),
        "stress_percentage": stress_percentage,
    }


def _health_status_from_class(predicted_class: str) -> str:
    """Normalize model class names to API health status buckets."""
    c = predicted_class.strip().lower()
    if c in {"low", "vlow"}:
        return "healthy"
    if c in {"mid"}:
        return "at_risk"
    if c in {"high", "vhigh"}:
        return "stressed"
    if c == "healthy":
        return "healthy"
    if c in {"nitrogen_deficient", "phosphorus_deficient", "drought_stress"}:
        return "stressed"
    return "at_risk"


def _load_model_artifacts(
    model_path: Path = MODEL_PATH,
    features_path: Path = FEATURES_PATH,
    strict: bool = False,
):
    """Load trained model and feature order metadata from disk."""
    if not model_path.exists() or not features_path.exists():
        if strict:
            raise MissingModelFilesError(
                details={
                    "model_path": str(model_path),
                    "features_path": str(features_path),
                }
            )
        return None, None

    try:
        from joblib import load
    except ModuleNotFoundError:
        if strict:
            raise MissingModelFilesError(
                details={"reason": "joblib_not_installed"}
            )
        return None, None

    with features_path.open("r", encoding="utf-8") as f:
        meta = json.load(f)

    feature_cols = meta.get("feature_columns") if isinstance(meta, dict) else None
    if not isinstance(feature_cols, list) or not feature_cols:
        if strict:
            raise MissingModelFilesError(
                details={"reason": "invalid_feature_columns_metadata", "features_path": str(features_path)}
            )
        return None, None

    model = load(model_path)
    return model, feature_cols


def predict_from_features(
    features: dict[str, float],
    ndre_mean: float,
    stress_percentage: float,
    model_path: Path = MODEL_PATH,
    features_path: Path = FEATURES_PATH,
    require_model: bool = False,
) -> InferenceResult:
    """Predict from extracted features with model-first, rule-based fallback."""
    model, feature_cols = _load_model_artifacts(
        model_path=model_path,
        features_path=features_path,
        strict=require_model,
    )

    if model is None or feature_cols is None:
        return RuleBasedInferenceEngine().predict(ndre_mean=ndre_mean, stress_percentage=stress_percentage)

    x = np.asarray([[float(features.get(col, 0.0)) for col in feature_cols]], dtype=np.float32)

    try:
        pred = str(model.predict(x)[0])
        proba_vec = model.predict_proba(x)[0]
        classes = [str(c) for c in model.classes_]

        class_probabilities = {
            cls: round(float(prob), 6)
            for cls, prob in zip(classes, proba_vec)
        }

        confidence = float(np.max(proba_vec))
        reconciled_health, reconciled_class, reconciled_conf = _reconcile_model_prediction(
            predicted_class=pred,
            confidence=round(confidence, 3),
            ndre_mean=float(ndre_mean),
            stress_percentage=float(stress_percentage),
        )
        return InferenceResult(
            health_status=reconciled_health,
            predicted_class=reconciled_class,
            confidence=round(reconciled_conf, 3),
            class_probabilities=class_probabilities,
        )
    except Exception:
        return RuleBasedInferenceEngine().predict(ndre_mean=ndre_mean, stress_percentage=stress_percentage)


def predict_from_image_cube(
    cube: np.ndarray,
    nir_band: int,
    red_edge_band: int,
    red_band: int | None = None,
    stress_threshold: float = 0.2,
    model_path: Path = MODEL_PATH,
    features_path: Path = FEATURES_PATH,
    require_model: bool = False,
) -> InferenceResult:
    """Extract features from hyperspectral cube and run inference."""
    features = extract_features_from_cube(
        cube=cube,
        nir_band=nir_band,
        red_edge_band=red_edge_band,
        red_band=red_band,
        stress_threshold=stress_threshold,
    )
    return predict_from_features(
        features=features,
        ndre_mean=features.get("ndre_mean", 0.0),
        stress_percentage=features.get("stress_percentage", 0.0),
        model_path=model_path,
        features_path=features_path,
        require_model=require_model,
    )


def predict_from_uploaded_image(
    file_contents: bytes,
    nir_band: int,
    red_edge_band: int,
    red_band: int | None = None,
    stress_threshold: float = 0.2,
    model_path: Path = MODEL_PATH,
    features_path: Path = FEATURES_PATH,
    require_model: bool = False,
) -> InferenceResult:
    """Load hyperspectral NPY bytes, extract features, and run inference."""
    from app.services import preprocessing

    cube, _ = preprocessing.load_npy_cube(file_contents)
    return predict_from_image_cube(
        cube=cube.data,
        nir_band=nir_band,
        red_edge_band=red_edge_band,
        red_band=red_band,
        stress_threshold=stress_threshold,
        model_path=model_path,
        features_path=features_path,
        require_model=require_model,
    )
