"""SQLAlchemy database models with relationships for hyperspectral analysis."""
from datetime import datetime
from sqlalchemy import Boolean, Column, Integer, String, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.database import Base


class Scan(Base):
    """
    Main model for hyperspectral image scans.
    Represents a single uploaded hyperspectral cube file.
    """
    __tablename__ = "scans"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False, index=True)
    file_path = Column(String, nullable=False, unique=True)
    upload_timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    # Image dimensions
    image_width = Column(Integer, nullable=False)
    image_height = Column(Integer, nullable=False)
    total_bands = Column(Integer, nullable=False)
    
    # Band configuration used for analysis
    selected_nir_band = Column(Integer, default=5, nullable=False)
    selected_red_edge_band = Column(Integer, default=4, nullable=False)
    
    # Relationships
    scan_metadata = relationship("ScanMetadata", back_populates="scan", uselist=False, cascade="all, delete-orphan")
    predictions = relationship("Prediction", back_populates="scan", cascade="all, delete-orphan")
    spectral_stats = relationship("SpectralStats", back_populates="scan", uselist=False, cascade="all, delete-orphan")
    temporal_analysis = relationship(
        "TemporalAnalysis",
        back_populates="scan",
        uselist=False,
        cascade="all, delete-orphan",
        foreign_keys="[TemporalAnalysis.scan_id]",
    )


class ScanMetadata(Base):
    """
    Metadata associated with a scan.
    Includes health status and additional contextual information.
    """
    __tablename__ = "scan_metadata"

    id = Column(Integer, primary_key=True, index=True)
    scan_id = Column(Integer, ForeignKey("scans.id"), nullable=False, unique=True, index=True)
    
    # Health status classification
    health_status = Column(String, nullable=True)  # e.g., "healthy", "stressed", "diseased"
    
    # Additional metadata as JSON for flexibility
    extra_metadata = Column("metadata", JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationship back to scan
    scan = relationship("Scan", back_populates="scan_metadata")


class Prediction(Base):
    """
    ML model predictions for a scan.
    Stores predicted class and confidence score.
    """
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    scan_id = Column(Integer, ForeignKey("scans.id"), nullable=False, index=True)
    
    # Prediction results
    predicted_class = Column(String, nullable=False)  # e.g., "healthy", "stressed", "diseased"
    confidence = Column(Float, nullable=False)  # 0.0 to 1.0
    model_version = Column(String, nullable=True)  # Version of model used
    
    # Visualization
    heatmap_path = Column(String, nullable=True)  # Path to NDRE heatmap PNG file
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationship back to scan
    scan = relationship("Scan", back_populates="predictions")


class SpectralStats(Base):
    """
    Spectral statistics for a scan.
    Contains vegetation indices and stress metrics.
    """
    __tablename__ = "spectral_stats"

    id = Column(Integer, primary_key=True, index=True)
    scan_id = Column(Integer, ForeignKey("scans.id"), nullable=False, unique=True, index=True)
    
    # NDRE (Normalized Difference Red Edge) statistics
    ndre_min = Column(Float, nullable=False)
    ndre_max = Column(Float, nullable=False)
    ndre_mean = Column(Float, nullable=False)
    ndre_std = Column(Float, nullable=False)
    
    # Stress analysis
    stress_percentage = Column(Float, nullable=False)  # Percentage of pixels below threshold
    stress_threshold = Column(Float, default=0.2, nullable=False)  # Threshold value used
    
    # Heatmap visualization
    heatmap_path = Column(String, nullable=True)  # Path to saved heatmap image or base64 in JSON
    heatmap_base64 = Column(String, nullable=True)  # Base64-encoded heatmap PNG
    
    # Additional spectral indices for future expansion
    spectral_data = Column(JSON, default={})  # e.g., NDVI, other indices
    
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationship back to scan
    scan = relationship("Scan", back_populates="spectral_stats")


class TemporalAnalysis(Base):
    """
    Scan-to-scan temporal comparison against the latest prior scan for the same sample.
    Stores rule-based trend and onset signals.
    """
    __tablename__ = "temporal_analysis"

    id = Column(Integer, primary_key=True, index=True)
    scan_id = Column(Integer, ForeignKey("scans.id"), nullable=False, unique=True, index=True)
    sample_id = Column(String, nullable=True, index=True)
    baseline_scan_id = Column(Integer, ForeignKey("scans.id"), nullable=True, index=True)

    has_baseline = Column(Boolean, default=False, nullable=False)
    no_baseline_reason = Column(String, nullable=True)
    trend_label = Column(String, nullable=True)  # improving | stable | worsening
    trend_score = Column(Float, nullable=True)

    ndre_mean_delta = Column(Float, nullable=True)
    stress_percentage_delta = Column(Float, nullable=True)
    confidence_delta = Column(Float, nullable=True)

    onset_detected = Column(Boolean, default=False, nullable=False)
    onset_reason = Column(String, nullable=True)
    onset_score = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    scan = relationship("Scan", back_populates="temporal_analysis", foreign_keys=[scan_id])
    baseline_scan = relationship(
        "Scan",
        foreign_keys=[baseline_scan_id],
        viewonly=True,
    )
