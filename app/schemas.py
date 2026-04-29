"""Pydantic schemas for request/response validation."""
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


# ============== SPECTRAL STATS SCHEMAS ==============

class NDREStats(BaseModel):
    """NDRE statistics."""
    min: float
    max: float
    mean: float
    std: float


class SpectralStatsCreate(BaseModel):
    """Schema for creating spectral statistics."""
    scan_id: int
    ndre_min: float
    ndre_max: float
    ndre_mean: float
    ndre_std: float
    stress_percentage: float
    stress_threshold: float = 0.2
    heatmap_base64: Optional[str] = None
    heatmap_path: Optional[str] = None
    spectral_data: Optional[Dict[str, Any]] = None


class SpectralStatsResponse(BaseModel):
    """Response schema for spectral statistics."""
    id: int
    scan_id: int
    ndre_min: float
    ndre_max: float
    ndre_mean: float
    ndre_std: float
    stress_percentage: float
    stress_threshold: float
    heatmap_path: Optional[str]
    spectral_data: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============== PREDICTION SCHEMAS ==============

class PredictionCreate(BaseModel):
    """Schema for creating predictions."""
    scan_id: int
    predicted_class: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    model_version: Optional[str] = None
    heatmap_path: Optional[str] = None


class PredictionResponse(BaseModel):
    """Response schema for predictions."""
    id: int
    scan_id: int
    predicted_class: str
    confidence: float
    model_version: Optional[str]
    heatmap_path: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ============== MULTICLASS STRESS CLASSIFICATION SCHEMAS ==============

class ClassProbability(BaseModel):
    """Class probability for a single stress type."""
    class_name: str
    probability: float = Field(..., ge=0.0, le=1.0)
    description: Optional[str] = None


class StressClassification(BaseModel):
    """Multiclass stress classification with probabilities and alternatives."""
    predicted_class: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    description: Optional[str] = None
    class_probabilities: Dict[str, float]
    top_alternatives: list[ClassProbability] = []


# ============== SCAN METADATA SCHEMAS ==============

class ScanMetadataCreate(BaseModel):
    """Schema for creating scan metadata."""
    scan_id: int
    health_status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ScanMetadataResponse(BaseModel):
    """Response schema for scan metadata."""
    id: int
    scan_id: int
    health_status: Optional[str]
    metadata: Optional[Dict[str, Any]] = Field(default=None, validation_alias="extra_metadata")
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ============== SCAN SCHEMAS ==============

class ScanCreate(BaseModel):
    """Schema for creating a new scan."""
    filename: str
    file_path: str
    image_width: int
    image_height: int
    total_bands: int
    selected_nir_band: int = 5
    selected_red_edge_band: int = 4


class ScanResponse(BaseModel):
    """Response schema for scan information."""
    id: int
    filename: str
    file_path: str
    upload_timestamp: datetime
    image_width: int
    image_height: int
    total_bands: int
    selected_nir_band: int
    selected_red_edge_band: int

    class Config:
        from_attributes = True


# ============== IMAGE PROCESSING RESPONSE ==============

class ImageShape(BaseModel):
    """Image dimensions."""
    height: int
    width: int


class ProcessImageResponse(BaseModel):
    """Response from image processing endpoint."""
    scan_id: int
    filename: str
    heatmap_base64: str
    image_shape: ImageShape
    ndre_stats: NDREStats
    stress_percentage: float
    stress_threshold: float
    upload_timestamp: datetime


# ============== COMPOSITE RESPONSE SCHEMAS ==============

class ScanDetailResponse(BaseModel):
    """Complete scan information with all related data."""
    id: int
    filename: str
    file_path: str
    upload_timestamp: datetime
    image_width: int
    image_height: int
    total_bands: int
    selected_nir_band: int
    selected_red_edge_band: int
    metadata: Optional[ScanMetadataResponse] = Field(default=None, validation_alias="scan_metadata")
    predictions: list[PredictionResponse] = []
    spectral_stats: Optional[SpectralStatsResponse] = None
    temporal_analysis: Optional["TemporalAnalysisResponse"] = None

    class Config:
        from_attributes = True


class ScanListResponse(BaseModel):
    """Schema for listing scans."""
    total: int
    scans: list[ScanResponse]


class HistoryItemResponse(BaseModel):
    """Flattened history item for joined scan analysis results."""
    scan_id: int
    file_name: str
    uploaded_at: datetime
    health_status: Optional[str] = None
    predicted_class: Optional[str] = None
    confidence: Optional[float] = None
    stress_percentage: Optional[float] = None
    sample_id: Optional[str] = None
    trend_label: Optional[str] = None
    ndre_mean_delta: Optional[float] = None
    stress_percentage_delta: Optional[float] = None
    confidence_delta: Optional[float] = None
    onset_detected: Optional[bool] = None
    onset_reason: Optional[str] = None


class HistoryListResponse(BaseModel):
    """Response schema for scan history list endpoint."""
    items: list[HistoryItemResponse]


# ============== SCAN UPLOAD RESPONSE ==============

class ScanUploadResponse(BaseModel):
    """Response from scan upload endpoint."""
    scan_id: int
    prediction_id: int
    filename: str
    image_width: int
    image_height: int
    total_bands: int
    ndre_stats: NDREStats
    stress_percentage: float
    stress_threshold: float
    heatmap_base64: str
    health_status: str
    predicted_class: Optional[str] = None
    confidence: Optional[float] = None
    vigor_score: float
    upload_timestamp: datetime
    crop_type: Optional[str] = None
    growth_stage: Optional[str] = None
    selected_nir_band: Optional[int] = None
    selected_red_edge_band: Optional[int] = None
    auto_band_selection_used: bool = False
    auto_band_score: Optional[float] = None
    threshold_auto_calibrated: bool = False
    heatmap_vmin: Optional[float] = None
    heatmap_vmax: Optional[float] = None
    temporal_analysis: Optional["TemporalAnalysisResponse"] = None


class ExplainabilityFeature(BaseModel):
    """One feature contribution from explainability service."""

    feature: str
    value: float
    contribution: float
    direction: str


class UploadBandsUsed(BaseModel):
    """Bands used during model inference."""

    nir_band: Optional[int] = None
    red_edge_band: Optional[int] = None


class UploadClassification(BaseModel):
    """Multiclass classification summary."""

    predicted_class: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    health_status: str


class CubeShapeResponse(BaseModel):
    """Shape details for uploaded hyperspectral cube."""

    height: int
    width: int
    bands: int


class TemporalAnalysisResponse(BaseModel):
    """Rule-based temporal comparison against most recent baseline scan."""

    sample_id: Optional[str] = None
    has_baseline: bool
    baseline_scan_id: Optional[int] = None
    no_baseline_reason: Optional[str] = None
    trend_label: str
    trend_score: float
    ndre_mean_delta: Optional[float] = None
    stress_percentage_delta: Optional[float] = None
    confidence_delta: Optional[float] = None
    onset_detected: bool
    onset_reason: str
    onset_score: float

    class Config:
        from_attributes = True


class MulticlassUploadResponse(BaseModel):
    """Upload response with classification and explainability output."""

    scan_id: int
    prediction_id: int
    filename: str
    analysis_mode: str = "hyperspectral"
    source_format: Optional[str] = None
    converted_npy_path: Optional[str] = None
    metric_labels: Dict[str, str] = Field(default_factory=dict)
    cube_shape: CubeShapeResponse
    bands_used: Optional[UploadBandsUsed] = None
    selected_nir_band: Optional[int] = None
    selected_red_edge_band: Optional[int] = None
    auto_band_selection_used: bool = False
    auto_band_score: Optional[float] = None
    threshold_auto_calibrated: bool = False
    ndre_stats: NDREStats
    stress_percentage: float
    stress_threshold: float
    heatmap_base64: str
    heatmap_vmin: float
    heatmap_vmax: float
    source_image_base64: Optional[str] = None
    source_image_path: Optional[str] = None
    source_image_bands: Optional[Dict[str, int]] = None
    upload_timestamp: datetime
    classification: UploadClassification
    class_probabilities: Dict[str, float]
    top_alternatives: list[ClassProbability] = []
    top_features: list[ExplainabilityFeature] = []
    feature_values: Dict[str, float] = {}
    explanation_summary: str
    explainability_method: str
    temporal_analysis: Optional[TemporalAnalysisResponse] = None


ScanDetailResponse.model_rebuild()
ScanUploadResponse.model_rebuild()
