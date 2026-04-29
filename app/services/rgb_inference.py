"""Rule-based RGB photo analysis used alongside the hyperspectral workflow."""

from __future__ import annotations

from typing import NamedTuple

import numpy as np
from matplotlib.colors import rgb_to_hsv

from app.services import inference, indices


class RGBAnalysisResult(NamedTuple):
    """Photo analysis payload returned to the upload router."""

    proxy_index: np.ndarray
    stats: indices.IndexStats
    stress_percentage: float
    stress_threshold: float
    healthy_count: int
    stressed_count: int
    plant_pixel_count: int
    background_pixel_count: int
    feature_map: dict[str, float]
    inference_result: inference.InferenceResult


def _majority_filter(mask: np.ndarray, min_neighbors: int = 5, passes: int = 2) -> np.ndarray:
    """Denoise small mask speckles with a compact majority filter."""
    filtered = np.asarray(mask, dtype=np.uint8)
    height, width = filtered.shape

    for _ in range(max(1, passes)):
        padded = np.pad(filtered, 1, mode="edge")
        neighbors = np.zeros((height, width), dtype=np.uint8)
        for row_offset in range(3):
            for col_offset in range(3):
                neighbors += padded[row_offset : row_offset + height, col_offset : col_offset + width]
        filtered = (neighbors >= min_neighbors).astype(np.uint8)

    return filtered.astype(bool)


def _build_plant_mask(rgb: np.ndarray, hsv: np.ndarray) -> np.ndarray:
    """Estimate a plant mask from an RGB photo using simple color cues."""
    red = rgb[..., 0]
    green = rgb[..., 1]
    blue = rgb[..., 2]
    hue = hsv[..., 0]
    sat = hsv[..., 1]
    val = hsv[..., 2]

    excess_green = (2.0 * green) - red - blue
    greenish = (hue >= 0.16) & (hue <= 0.48) & (sat >= 0.12) & (val >= 0.08)
    dominant_green = (green >= red * 0.9) & (green >= blue * 0.9) & (sat >= 0.08) & (val >= 0.10)
    mask = greenish | dominant_green | (excess_green > 0.02)
    mask = _majority_filter(mask, min_neighbors=5, passes=2)

    coverage = float(np.mean(mask))
    if coverage < 0.01:
        fallback = (sat >= 0.10) & (val >= 0.12)
        mask = _majority_filter(fallback, min_neighbors=4, passes=1)

    if float(np.mean(mask)) < 0.005:
        mask = np.ones(rgb.shape[:2], dtype=bool)

    return mask


def _softmax(scores: dict[str, float]) -> dict[str, float]:
    """Compute a normalized probability dictionary from unbounded scores."""
    keys = list(scores.keys())
    values = np.asarray([scores[key] for key in keys], dtype=np.float32)
    values -= float(np.max(values))
    probs = np.exp(values)
    probs /= float(np.sum(probs))
    return {key: float(prob) for key, prob in zip(keys, probs)}


def analyze_rgb_image(rgb_image: np.ndarray, stress_threshold: float = 0.2) -> RGBAnalysisResult:
    """Analyze an RGB plant photo and derive a proxy health map plus class label."""
    rgb = np.asarray(rgb_image, dtype=np.float32)
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("Expected RGB image with shape (height, width, 3)")

    rgb = np.clip(rgb, 0.0, 1.0)
    hsv = rgb_to_hsv(rgb)

    red = rgb[..., 0]
    green = rgb[..., 1]
    blue = rgb[..., 2]
    hue = hsv[..., 0]
    sat = hsv[..., 1]
    val = hsv[..., 2]

    plant_mask = _build_plant_mask(rgb, hsv)
    plant_pixels = int(np.sum(plant_mask))
    background_pixels = int(plant_mask.size - plant_pixels)

    excess_green = (2.0 * green) - red - blue
    green_balance = np.clip((green - ((red + blue) * 0.5) + 0.20) / 0.80, 0.0, 1.0)
    excess_green_scaled = np.clip((excess_green + 0.35) / 1.15, 0.0, 1.0)

    hue_distance = np.abs(hue - 0.33)
    hue_distance = np.minimum(hue_distance, 1.0 - hue_distance)
    hue_score = np.clip(1.0 - (hue_distance / 0.22), 0.0, 1.0)

    yellowness = np.clip((red + green - (2.0 * blue)) / 1.15, 0.0, 1.0)
    yellowness *= np.clip(1.0 - (np.abs(red - green) / 0.22), 0.0, 1.0)

    brownness = np.clip((red - green) / 0.35, 0.0, 1.0)
    brownness *= np.clip((green - blue) / 0.35, 0.0, 1.0)
    brownness *= np.clip((0.85 - val) / 0.85, 0.0, 1.0)

    darkness = np.clip((0.40 - val) / 0.40, 0.0, 1.0) * sat
    dryness = np.clip((0.45 - green) / 0.45, 0.0, 1.0) * np.clip(val / 0.70, 0.0, 1.0)

    stress_signal = (
        (0.32 * (1.0 - excess_green_scaled))
        + (0.18 * (1.0 - hue_score))
        + (0.16 * yellowness)
        + (0.16 * brownness)
        + (0.10 * darkness)
        + (0.08 * dryness)
    )
    health_score = np.clip(1.0 - stress_signal, 0.0, 1.0)

    proxy_index = (health_score * 2.0) - 1.0
    proxy_index = proxy_index.astype(np.float32)
    proxy_index[~plant_mask] = np.nan

    stats = indices.get_index_stats(proxy_index)
    stress_pct, stressed_count, healthy_count = indices.compute_stress_percentage(
        proxy_index,
        threshold=stress_threshold,
    )

    valid_proxy = proxy_index[np.isfinite(proxy_index)]
    proxy_mean = float(np.mean(valid_proxy)) if valid_proxy.size else 0.0
    proxy_std = float(np.std(valid_proxy)) if valid_proxy.size else 0.0

    plant_coverage = float(plant_pixels * 100.0 / plant_mask.size) if plant_mask.size else 0.0
    yellow_fraction = float(np.mean(yellowness[plant_mask] > 0.45) * 100.0) if plant_pixels else 0.0
    brown_fraction = float(np.mean(brownness[plant_mask] > 0.40) * 100.0) if plant_pixels else 0.0
    dark_fraction = float(np.mean(darkness[plant_mask] > 0.35) * 100.0) if plant_pixels else 0.0
    low_vigor_fraction = float(np.mean(health_score[plant_mask] < 0.45) * 100.0) if plant_pixels else 0.0
    saturation_mean = float(np.mean(sat[plant_mask]) * 100.0) if plant_pixels else 0.0
    green_balance_mean = float(np.mean(green_balance[plant_mask]) * 100.0) if plant_pixels else 0.0
    texture_variability = proxy_std * 100.0
    patchiness = min(1.0, proxy_std / 0.45)

    feature_map = {
        "proxy_mean": round(proxy_mean, 4),
        "proxy_std": round(proxy_std, 4),
        "stress_percentage": round(stress_pct, 2),
        "plant_coverage": round(plant_coverage, 2),
        "yellow_fraction": round(yellow_fraction, 2),
        "brown_fraction": round(brown_fraction, 2),
        "dark_fraction": round(dark_fraction, 2),
        "low_vigor_fraction": round(low_vigor_fraction, 2),
        "saturation_mean": round(saturation_mean, 2),
        "green_balance_mean": round(green_balance_mean, 2),
        "texture_variability": round(texture_variability, 2),
    }

    stress_ratio = stress_pct / 100.0
    proxy_ratio = np.clip((proxy_mean + 1.0) / 2.0, 0.0, 1.0)
    yellow_ratio = yellow_fraction / 100.0
    brown_ratio = brown_fraction / 100.0
    dark_ratio = dark_fraction / 100.0
    low_vigor_ratio = low_vigor_fraction / 100.0
    saturation_ratio = saturation_mean / 100.0

    scores = {
        "healthy": (2.40 * (1.0 - stress_ratio)) + (1.60 * proxy_ratio) - (1.00 * yellow_ratio) - (1.20 * brown_ratio),
        "nutrient_like_stress": (1.40 * yellow_ratio) + (0.55 * stress_ratio) + (0.35 * (1.0 - brown_ratio)) + (0.30 * (1.0 - abs(proxy_ratio - 0.55))),
        "drought_like_stress": (1.20 * stress_ratio) + (0.80 * (1.0 - proxy_ratio)) + (0.60 * low_vigor_ratio) + (0.30 * (1.0 - saturation_ratio)),
        "disease_like_stress": (1.30 * brown_ratio) + (1.00 * dark_ratio) + (0.80 * patchiness) + (0.40 * stress_ratio),
    }
    class_probabilities = _softmax(scores)
    predicted_class = max(class_probabilities, key=class_probabilities.get)
    confidence = float(class_probabilities[predicted_class])
    health_status = inference.reconcile_health_status(
        predicted_class=predicted_class,
        stress_percentage=stress_pct,
        confidence=confidence,
    )

    inference_result = inference.InferenceResult(
        predicted_class=predicted_class,
        confidence=confidence,
        class_probabilities=class_probabilities,
        health_status=health_status,
    )

    return RGBAnalysisResult(
        proxy_index=proxy_index,
        stats=stats,
        stress_percentage=stress_pct,
        stress_threshold=float(stress_threshold),
        healthy_count=healthy_count,
        stressed_count=stressed_count,
        plant_pixel_count=plant_pixels,
        background_pixel_count=background_pixels,
        feature_map=feature_map,
        inference_result=inference_result,
    )
