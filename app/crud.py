"""CRUD operations for database models."""
from sqlalchemy.orm import Session, aliased
from app.models import Scan, ScanMetadata, Prediction, SpectralStats, TemporalAnalysis
from app.schemas import ScanCreate, PredictionCreate


# ============== SCAN CRUD ==============

def create_scan(db: Session, scan: ScanCreate) -> Scan:
    """Create a new scan record."""
    db_scan = Scan(**scan.model_dump(exclude={"metadata", "predictions", "spectral_stats"}))
    db.add(db_scan)
    db.commit()
    db.refresh(db_scan)
    return db_scan


def get_scan(db: Session, scan_id: int) -> Scan | None:
    """Get a specific scan by ID."""
    return db.query(Scan).filter(Scan.id == scan_id).first()


def get_scan_by_filename(db: Session, filename: str) -> Scan | None:
    """Get a scan by filename."""
    return db.query(Scan).filter(Scan.filename == filename).first()


def get_scans(db: Session, skip: int = 0, limit: int = 100) -> list[Scan]:
    """Get a list of scans with pagination."""
    return db.query(Scan).offset(skip).limit(limit).all()


def count_scans(db: Session) -> int:
    """Count total number of scans."""
    return db.query(Scan).count()


def delete_scan(db: Session, scan_id: int) -> bool:
    """Delete a scan record and all related data."""
    db_scan = get_scan(db, scan_id)
    if not db_scan:
        return False
    db.delete(db_scan)
    db.commit()
    return True


# ============== SCAN METADATA CRUD ==============

def create_scan_metadata(db: Session, scan_id: int, health_status: str | None = None, metadata: dict | None = None) -> ScanMetadata:
    """Create metadata for a scan."""
    db_metadata = ScanMetadata(
        scan_id=scan_id,
        health_status=health_status,
        extra_metadata=metadata or {}
    )
    db.add(db_metadata)
    db.commit()
    db.refresh(db_metadata)
    return db_metadata


def get_scan_metadata(db: Session, scan_id: int) -> ScanMetadata | None:
    """Get metadata for a specific scan."""
    return db.query(ScanMetadata).filter(ScanMetadata.scan_id == scan_id).first()


def update_scan_metadata(db: Session, scan_id: int, health_status: str | None = None, metadata: dict | None = None) -> ScanMetadata | None:
    """Update metadata for a scan."""
    db_metadata = get_scan_metadata(db, scan_id)
    if not db_metadata:
        return None
    
    if health_status is not None:
        db_metadata.health_status = health_status
    if metadata is not None:
        db_metadata.extra_metadata = metadata
    
    db.commit()
    db.refresh(db_metadata)
    return db_metadata


# ============== PREDICTION CRUD ==============

def create_prediction(db: Session, prediction: PredictionCreate) -> Prediction:
    """Create a new prediction record."""
    db_prediction = Prediction(**prediction.model_dump())
    db.add(db_prediction)
    db.commit()
    db.refresh(db_prediction)
    return db_prediction


def get_prediction(db: Session, prediction_id: int) -> Prediction | None:
    """Get a specific prediction by ID."""
    return db.query(Prediction).filter(Prediction.id == prediction_id).first()


def get_predictions_by_scan(db: Session, scan_id: int) -> list[Prediction]:
    """Get all predictions for a specific scan."""
    return db.query(Prediction).filter(Prediction.scan_id == scan_id).all()


def get_latest_prediction(db: Session, scan_id: int) -> Prediction | None:
    """Get the latest prediction for a scan."""
    return db.query(Prediction).filter(
        Prediction.scan_id == scan_id
    ).order_by(Prediction.created_at.desc()).first()


# ============== SPECTRAL STATS CRUD ==============

def create_spectral_stats(db: Session, scan_id: int, ndre_min: float, ndre_max: float, 
                         ndre_mean: float, ndre_std: float, stress_percentage: float,
                         stress_threshold: float = 0.2, heatmap_base64: str | None = None,
                         heatmap_path: str | None = None, spectral_data: dict | None = None) -> SpectralStats:
    """Create spectral statistics for a scan."""
    db_stats = SpectralStats(
        scan_id=scan_id,
        ndre_min=ndre_min,
        ndre_max=ndre_max,
        ndre_mean=ndre_mean,
        ndre_std=ndre_std,
        stress_percentage=stress_percentage,
        stress_threshold=stress_threshold,
        heatmap_base64=heatmap_base64,
        heatmap_path=heatmap_path,
        spectral_data=spectral_data or {}
    )
    db.add(db_stats)
    db.commit()
    db.refresh(db_stats)
    return db_stats


def get_spectral_stats(db: Session, scan_id: int) -> SpectralStats | None:
    """Get spectral statistics for a specific scan."""
    return db.query(SpectralStats).filter(SpectralStats.scan_id == scan_id).first()


def update_spectral_stats(db: Session, scan_id: int, spectral_data: dict | None = None) -> SpectralStats | None:
    """Update spectral statistics for a scan."""
    db_stats = get_spectral_stats(db, scan_id)
    if not db_stats:
        return None
    
    if spectral_data is not None:
        db_stats.spectral_data = spectral_data
    
    db.commit()
    db.refresh(db_stats)
    return db_stats


# ============== TEMPORAL ANALYSIS CRUD ==============

def create_temporal_analysis(
    db: Session,
    *,
    scan_id: int,
    sample_id: str | None,
    has_baseline: bool,
    baseline_scan_id: int | None,
    no_baseline_reason: str | None,
    trend_label: str,
    trend_score: float,
    ndre_mean_delta: float | None,
    stress_percentage_delta: float | None,
    confidence_delta: float | None,
    onset_detected: bool,
    onset_reason: str,
    onset_score: float,
) -> TemporalAnalysis:
    """Create temporal analysis record for a scan."""
    db_temporal = TemporalAnalysis(
        scan_id=scan_id,
        sample_id=sample_id,
        has_baseline=has_baseline,
        baseline_scan_id=baseline_scan_id,
        no_baseline_reason=no_baseline_reason,
        trend_label=trend_label,
        trend_score=trend_score,
        ndre_mean_delta=ndre_mean_delta,
        stress_percentage_delta=stress_percentage_delta,
        confidence_delta=confidence_delta,
        onset_detected=onset_detected,
        onset_reason=onset_reason,
        onset_score=onset_score,
    )
    db.add(db_temporal)
    db.commit()
    db.refresh(db_temporal)
    return db_temporal


def get_temporal_analysis(db: Session, scan_id: int) -> TemporalAnalysis | None:
    """Get temporal analysis for a specific scan."""
    return db.query(TemporalAnalysis).filter(TemporalAnalysis.scan_id == scan_id).first()


def get_scan_history(db: Session) -> list[dict]:
    """Get flattened history items by joining scans with latest predictions and spectral stats.

    Returns rows ordered by newest upload first.
    """
    latest_prediction = aliased(Prediction)

    latest_prediction_subquery = (
        db.query(
            Prediction.scan_id.label("scan_id"),
            Prediction.id.label("prediction_id"),
        )
        .distinct(Prediction.scan_id)
        .order_by(Prediction.scan_id, Prediction.created_at.desc())
        .subquery()
    )

    rows = (
        db.query(
            Scan.id.label("scan_id"),
            Scan.filename.label("file_name"),
            Scan.upload_timestamp.label("uploaded_at"),
            ScanMetadata.health_status.label("health_status"),
            latest_prediction.predicted_class.label("predicted_class"),
            latest_prediction.confidence.label("confidence"),
            SpectralStats.stress_percentage.label("stress_percentage"),
            TemporalAnalysis.sample_id.label("sample_id"),
            TemporalAnalysis.trend_label.label("trend_label"),
            TemporalAnalysis.ndre_mean_delta.label("ndre_mean_delta"),
            TemporalAnalysis.stress_percentage_delta.label("stress_percentage_delta"),
            TemporalAnalysis.confidence_delta.label("confidence_delta"),
            TemporalAnalysis.onset_detected.label("onset_detected"),
            TemporalAnalysis.onset_reason.label("onset_reason"),
        )
        .outerjoin(ScanMetadata, ScanMetadata.scan_id == Scan.id)
        .outerjoin(latest_prediction_subquery, latest_prediction_subquery.c.scan_id == Scan.id)
        .outerjoin(latest_prediction, latest_prediction.id == latest_prediction_subquery.c.prediction_id)
        .outerjoin(SpectralStats, SpectralStats.scan_id == Scan.id)
        .outerjoin(TemporalAnalysis, TemporalAnalysis.scan_id == Scan.id)
        .order_by(Scan.upload_timestamp.desc())
        .all()
    )

    return [
        {
            "scan_id": row.scan_id,
            "file_name": row.file_name,
            "uploaded_at": row.uploaded_at,
            "health_status": row.health_status,
            "predicted_class": row.predicted_class,
            "confidence": row.confidence,
            "stress_percentage": row.stress_percentage,
            "sample_id": row.sample_id,
            "trend_label": row.trend_label,
            "ndre_mean_delta": row.ndre_mean_delta,
            "stress_percentage_delta": row.stress_percentage_delta,
            "confidence_delta": row.confidence_delta,
            "onset_detected": row.onset_detected,
            "onset_reason": row.onset_reason,
        }
        for row in rows
    ]
