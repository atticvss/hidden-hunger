"""Rule-based temporal comparison utilities for scan history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.models import Prediction, Scan

NDRE_STABLE_EPS = 0.015
STRESS_STABLE_EPS = 3.0
CONFIDENCE_STABLE_EPS = 0.05

ONSET_STRESS_JUMP = 5.0
ONSET_NDRE_DROP = -0.02
ONSET_CONFIDENCE_RISE = 0.08


@dataclass(frozen=True)
class TemporalSnapshot:
    """Minimal values required for temporal calculations."""

    scan_id: int
    upload_timestamp: datetime
    ndre_mean: float
    stress_percentage: float
    confidence: float


@dataclass(frozen=True)
class TemporalAnalysisResult:
    """Computed temporal output for a scan."""

    sample_id: Optional[str]
    has_baseline: bool
    baseline_scan_id: Optional[int]
    no_baseline_reason: Optional[str]
    trend_label: str
    trend_score: float
    ndre_mean_delta: Optional[float]
    stress_percentage_delta: Optional[float]
    confidence_delta: Optional[float]
    onset_detected: bool
    onset_reason: str
    onset_score: float


def resolve_sample_id(extra_metadata: Optional[dict]) -> Optional[str]:
    """Resolve sample/plant identifier from flexible metadata payload."""
    if not isinstance(extra_metadata, dict):
        return None

    for key in ("sample_id", "plant_id"):
        value = extra_metadata.get(key)
        if value is None:
            continue
        value_text = str(value).strip()
        if value_text:
            return value_text
    return None


def _latest_prediction_for_scan(scan: Scan) -> Optional[Prediction]:
    if not scan.predictions:
        return None
    return max(scan.predictions, key=lambda pred: pred.created_at)


def find_previous_snapshot_for_sample(
    db: Session,
    *,
    current_scan_id: int,
    current_upload_timestamp: datetime,
    sample_id: Optional[str],
    current_analysis_mode: str = "hyperspectral",
) -> Optional[TemporalSnapshot]:
    """Find newest prior scan for the same sample_id/plant_id."""
    if not sample_id:
        return None

    candidates = (
        db.query(Scan)
        .options(
            joinedload(Scan.scan_metadata),
            joinedload(Scan.spectral_stats),
            joinedload(Scan.predictions),
        )
        .filter(
            Scan.id != current_scan_id,
            Scan.upload_timestamp < current_upload_timestamp,
        )
        .order_by(Scan.upload_timestamp.desc())
        .all()
    )

    for scan in candidates:
        if not scan.scan_metadata or not scan.spectral_stats:
            continue

        candidate_sample_id = resolve_sample_id(scan.scan_metadata.extra_metadata)
        if candidate_sample_id != sample_id:
            continue

        candidate_mode = str(scan.scan_metadata.extra_metadata.get("analysis_mode", "hyperspectral"))
        if candidate_mode != current_analysis_mode:
            continue

        latest_prediction = _latest_prediction_for_scan(scan)
        baseline_confidence = float(latest_prediction.confidence) if latest_prediction else 0.0

        return TemporalSnapshot(
            scan_id=scan.id,
            upload_timestamp=scan.upload_timestamp,
            ndre_mean=float(scan.spectral_stats.ndre_mean),
            stress_percentage=float(scan.spectral_stats.stress_percentage),
            confidence=baseline_confidence,
        )

    return None


def classify_trend(
    ndre_delta: float,
    stress_delta: float,
    confidence_delta: float,
) -> tuple[str, float]:
    """Classify trend using transparent threshold-based scoring."""
    trend_score = (
        (ndre_delta / NDRE_STABLE_EPS)
        - (stress_delta / STRESS_STABLE_EPS)
        - (confidence_delta / CONFIDENCE_STABLE_EPS)
    )

    if trend_score >= 1.0:
        return "improving", float(trend_score)
    if trend_score <= -1.0:
        return "worsening", float(trend_score)
    return "stable", float(trend_score)


def detect_onset(
    ndre_delta: float,
    stress_delta: float,
    confidence_delta: float,
) -> tuple[bool, str, float]:
    """Detect early stress progression with compact, practical rules."""
    triggered_reasons: list[str] = []

    if stress_delta >= ONSET_STRESS_JUMP:
        triggered_reasons.append("stress_percentage increased notably")
    if ndre_delta <= ONSET_NDRE_DROP:
        triggered_reasons.append("ndre_mean dropped noticeably")
    if confidence_delta >= ONSET_CONFIDENCE_RISE:
        triggered_reasons.append("prediction confidence increased toward current class")

    onset_detected = len(triggered_reasons) >= 2

    stress_component = max(0.0, min(1.0, stress_delta / 12.0)) if stress_delta > 0 else 0.0
    ndre_component = max(0.0, min(1.0, abs(min(ndre_delta, 0.0)) / 0.05))
    conf_component = max(0.0, min(1.0, max(confidence_delta, 0.0) / 0.20))
    onset_score = float((stress_component + ndre_component + conf_component) / 3.0)

    if onset_detected:
        return True, "; ".join(triggered_reasons), onset_score
    return False, "No early stress progression detected.", onset_score


def compute_temporal_analysis(
    *,
    sample_id: Optional[str],
    baseline: Optional[TemporalSnapshot],
    current_ndre_mean: float,
    current_stress_percentage: float,
    current_confidence: float,
) -> TemporalAnalysisResult:
    """Compute temporal result using current metrics and optional baseline."""
    if baseline is None:
        reason = (
            "No sample_id/plant_id found in metadata."
            if not sample_id
            else "First scan for this sample_id/plant_id."
        )
        return TemporalAnalysisResult(
            sample_id=sample_id,
            has_baseline=False,
            baseline_scan_id=None,
            no_baseline_reason=reason,
            trend_label="stable",
            trend_score=0.0,
            ndre_mean_delta=None,
            stress_percentage_delta=None,
            confidence_delta=None,
            onset_detected=False,
            onset_reason="No baseline scan available.",
            onset_score=0.0,
        )

    ndre_delta = float(current_ndre_mean - baseline.ndre_mean)
    stress_delta = float(current_stress_percentage - baseline.stress_percentage)
    confidence_delta = float(current_confidence - baseline.confidence)

    trend_label, trend_score = classify_trend(ndre_delta, stress_delta, confidence_delta)
    onset_detected, onset_reason, onset_score = detect_onset(ndre_delta, stress_delta, confidence_delta)

    return TemporalAnalysisResult(
        sample_id=sample_id,
        has_baseline=True,
        baseline_scan_id=baseline.scan_id,
        no_baseline_reason=None,
        trend_label=trend_label,
        trend_score=trend_score,
        ndre_mean_delta=ndre_delta,
        stress_percentage_delta=stress_delta,
        confidence_delta=confidence_delta,
        onset_detected=onset_detected,
        onset_reason=onset_reason,
        onset_score=onset_score,
    )
