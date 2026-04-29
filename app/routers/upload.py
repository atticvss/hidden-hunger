"""Upload and image processing endpoints."""

import base64
from typing import Optional

import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.crud import (
    create_prediction,
    create_scan,
    create_scan_metadata,
    create_spectral_stats,
    create_temporal_analysis,
)
from app.deps import get_db
from app.errors import (
    DatabaseWriteError,
    InvalidUploadError,
    RasterReadError,
    UnsupportedBandIndexError,
    UnsupportedFileTypeError,
)
from app.schemas import MulticlassUploadResponse, PredictionCreate, ProcessImageResponse, ScanCreate
from app.services import (
    explainability,
    indices,
    inference,
    preprocessing,
    rgb_inference,
    rgb_preprocessing,
    storage,
    temporal,
)

router = APIRouter(prefix="/api", tags=["upload"])


def _metric_labels(analysis_mode: str, stress_threshold: float) -> dict[str, str]:
    """Return UI labels that match the active analysis mode."""
    threshold_text = f"{float(stress_threshold):.2f}"
    if analysis_mode == "rgb_proxy":
        return {
            "heatmap_title": "Proxy Health Map",
            "min_label": "Proxy Min",
            "max_label": "Proxy Max",
            "mean_label": "Proxy Mean",
            "std_label": "Proxy Std Dev",
            "stress_label": "Low Health Area",
            "stress_hint": f"proxy score below {threshold_text}",
            "temporal_delta_label": "Proxy Change",
        }

    return {
        "heatmap_title": "NDRE Heatmap",
        "min_label": "NDRE Min",
        "max_label": "NDRE Max",
        "mean_label": "Mean",
        "std_label": "Std Dev",
        "stress_label": "Stress Area",
        "stress_hint": f"pixels below {threshold_text}",
        "temporal_delta_label": "NDRE Change",
    }


def _serialize_explainability(xai_result: explainability.ExplainabilityResult) -> dict[str, object]:
    """Convert explainability output to a response-friendly payload."""
    return {
        "top_features": [
            {
                "feature": item.feature,
                "value": item.value,
                "contribution": item.contribution,
                "direction": item.direction,
            }
            for item in xai_result.top_features
        ],
        "feature_values": xai_result.feature_values,
        "explanation_summary": xai_result.explanation_summary,
        "method": xai_result.method,
    }


def _rank_alternatives(class_probabilities: dict[str, float], predicted_class: str) -> list[dict[str, float | str]]:
    """Return the next-most-likely classes for compact UI display."""
    return [
        {
            "class_name": cls,
            "probability": round(prob, 4),
        }
        for cls, prob in sorted(class_probabilities.items(), key=lambda item: item[1], reverse=True)
        if cls != predicted_class
    ][:2]


def _persist_upload_records(
    db: Session,
    *,
    file_name: str,
    file_contents: bytes,
    image_width: int,
    image_height: int,
    total_bands: int,
    selected_nir_band: int,
    selected_red_edge_band: int,
    predicted_class: str,
    confidence: float,
    model_version: Optional[str],
    stats: dict[str, float],
    stress_percentage: float,
    stress_threshold: float,
    heatmap_base64: str,
    heatmap_vmin: float,
    heatmap_vmax: float,
    spectral_data: dict,
    metadata_payload: dict,
    artifact_specs: Optional[list[tuple[str, str, bytes, str]]] = None,
):
    """Persist upload, analysis, metadata, and temporal snapshot records."""
    try:
        storage_file = storage.save_uploaded_file(file_name, file_contents)
    except IOError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(exc)}") from exc

    scan_create = ScanCreate(
        filename=file_name,
        file_path=storage_file.full_path,
        image_width=image_width,
        image_height=image_height,
        total_bands=total_bands,
        selected_nir_band=selected_nir_band,
        selected_red_edge_band=selected_red_edge_band,
    )

    try:
        db_scan = create_scan(db, scan_create)
    except SQLAlchemyError as exc:
        db.rollback()
        raise DatabaseWriteError(details={"operation": "create_scan", "reason": str(exc)}) from exc

    if artifact_specs:
        for artifact_type, extension, artifact_bytes, metadata_key in artifact_specs:
            try:
                artifact_file = storage.save_artifact(
                    artifact_bytes=artifact_bytes,
                    scan_id=db_scan.id,
                    artifact_type=artifact_type,
                    extension=extension,
                )
            except IOError as exc:
                raise HTTPException(status_code=500, detail=f"Failed to save artifact: {str(exc)}") from exc
            metadata_payload[metadata_key] = artifact_file.relative_path

    try:
        db_prediction = create_prediction(
            db,
            PredictionCreate(
                scan_id=db_scan.id,
                predicted_class=predicted_class,
                confidence=confidence,
                model_version=model_version,
                heatmap_path=None,
            ),
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise DatabaseWriteError(details={"operation": "create_prediction", "reason": str(exc)}) from exc

    try:
        create_spectral_stats(
            db,
            scan_id=db_scan.id,
            ndre_min=stats["min"],
            ndre_max=stats["max"],
            ndre_mean=stats["mean"],
            ndre_std=stats["std"],
            stress_percentage=stress_percentage,
            stress_threshold=stress_threshold,
            heatmap_base64=heatmap_base64,
            spectral_data=spectral_data,
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise DatabaseWriteError(details={"operation": "create_spectral_stats", "reason": str(exc)}) from exc

    try:
        create_scan_metadata(
            db,
            db_scan.id,
            health_status=str(metadata_payload.get("reconciled_health_status", "")) or None,
            metadata=metadata_payload,
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise DatabaseWriteError(details={"operation": "create_scan_metadata", "reason": str(exc)}) from exc

    resolved_sample_id = temporal.resolve_sample_id(metadata_payload)
    baseline_snapshot = temporal.find_previous_snapshot_for_sample(
        db,
        current_scan_id=db_scan.id,
        current_upload_timestamp=db_scan.upload_timestamp,
        sample_id=resolved_sample_id,
        current_analysis_mode=str(metadata_payload.get("analysis_mode", "hyperspectral")),
    )
    temporal_result = temporal.compute_temporal_analysis(
        sample_id=resolved_sample_id,
        baseline=baseline_snapshot,
        current_ndre_mean=stats["mean"],
        current_stress_percentage=stress_percentage,
        current_confidence=confidence,
    )

    try:
        db_temporal = create_temporal_analysis(
            db,
            scan_id=db_scan.id,
            sample_id=temporal_result.sample_id,
            has_baseline=temporal_result.has_baseline,
            baseline_scan_id=temporal_result.baseline_scan_id,
            no_baseline_reason=temporal_result.no_baseline_reason,
            trend_label=temporal_result.trend_label,
            trend_score=temporal_result.trend_score,
            ndre_mean_delta=temporal_result.ndre_mean_delta,
            stress_percentage_delta=temporal_result.stress_percentage_delta,
            confidence_delta=temporal_result.confidence_delta,
            onset_detected=temporal_result.onset_detected,
            onset_reason=temporal_result.onset_reason,
            onset_score=temporal_result.onset_score,
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise DatabaseWriteError(details={"operation": "create_temporal_analysis", "reason": str(exc)}) from exc

    metadata_payload["heatmap_vmin"] = heatmap_vmin
    metadata_payload["heatmap_vmax"] = heatmap_vmax
    return storage_file, db_scan, db_prediction, db_temporal, metadata_payload


def _build_upload_response(
    *,
    db_scan,
    db_prediction,
    db_temporal,
    filename: str,
    analysis_mode: str,
    source_format: str,
    cube_shape: dict[str, int],
    bands_used: Optional[dict[str, int]],
    selected_nir_band: Optional[int],
    selected_red_edge_band: Optional[int],
    auto_band_selection_used: bool,
    auto_band_score: Optional[float],
    threshold_auto_calibrated: bool,
    stats: dict[str, float],
    stress_percentage: float,
    stress_threshold: float,
    heatmap_base64: str,
    heatmap_vmin: float,
    heatmap_vmax: float,
    predicted_class: str,
    confidence: float,
    health_status: str,
    class_probabilities: dict[str, float],
    explanation_payload: dict[str, object],
    source_image_base64: Optional[str] = None,
    source_image_path: Optional[str] = None,
    source_image_bands: Optional[dict[str, int]] = None,
    converted_npy_path: Optional[str] = None,
):
    """Build the common API response shape for both upload branches."""
    return {
        "scan_id": db_scan.id,
        "prediction_id": db_prediction.id,
        "filename": filename,
        "analysis_mode": analysis_mode,
        "source_format": source_format,
        "converted_npy_path": converted_npy_path,
        "metric_labels": _metric_labels(analysis_mode, stress_threshold),
        "cube_shape": cube_shape,
        "bands_used": bands_used,
        "selected_nir_band": selected_nir_band,
        "selected_red_edge_band": selected_red_edge_band,
        "auto_band_selection_used": auto_band_selection_used,
        "auto_band_score": auto_band_score,
        "threshold_auto_calibrated": threshold_auto_calibrated,
        "ndre_stats": stats,
        "stress_percentage": stress_percentage,
        "stress_threshold": stress_threshold,
        "heatmap_base64": heatmap_base64,
        "heatmap_vmin": heatmap_vmin,
        "heatmap_vmax": heatmap_vmax,
        "source_image_base64": source_image_base64,
        "source_image_path": source_image_path,
        "source_image_bands": source_image_bands,
        "upload_timestamp": db_scan.upload_timestamp,
        "classification": {
            "predicted_class": predicted_class,
            "confidence": round(confidence, 4),
            "health_status": health_status,
        },
        "class_probabilities": {key: round(value, 4) for key, value in class_probabilities.items()},
        "top_alternatives": _rank_alternatives(class_probabilities, predicted_class),
        "top_features": explanation_payload["top_features"],
        "feature_values": explanation_payload["feature_values"],
        "explanation_summary": explanation_payload["explanation_summary"],
        "explainability_method": explanation_payload["method"],
        "temporal_analysis": {
            "sample_id": db_temporal.sample_id,
            "has_baseline": db_temporal.has_baseline,
            "baseline_scan_id": db_temporal.baseline_scan_id,
            "no_baseline_reason": db_temporal.no_baseline_reason,
            "trend_label": db_temporal.trend_label,
            "trend_score": float(db_temporal.trend_score or 0.0),
            "ndre_mean_delta": db_temporal.ndre_mean_delta,
            "stress_percentage_delta": db_temporal.stress_percentage_delta,
            "confidence_delta": db_temporal.confidence_delta,
            "onset_detected": db_temporal.onset_detected,
            "onset_reason": db_temporal.onset_reason or "",
            "onset_score": float(db_temporal.onset_score or 0.0),
        },
    }


def _handle_hyperspectral_upload(
    *,
    file_name: str,
    contents: bytes,
    nir_band: int,
    red_edge_band: int,
    stress_threshold: float,
    auto_select_bands: bool,
    auto_calibrate_threshold: bool,
    sample_id: Optional[str],
    plant_id: Optional[str],
    db: Session,
):
    """Existing NPY upload path, kept intact but wrapped for branching."""
    try:
        cube_obj, metadata = preprocessing.load_npy_cube(contents)
        auto_band_score: Optional[float] = None
        if auto_select_bands:
            selection = preprocessing.auto_select_ndre_bands(
                cube_obj,
                stress_threshold=stress_threshold,
            )
            nir_band = selection.nir_band
            red_edge_band = selection.red_edge_band
            auto_band_score = float(selection.score)
        cube = cube_obj.data
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "INVALID_FILE",
                "message": f"Failed to load NPY: {str(exc)}",
            },
        ) from exc

    bands, height, width = cube.shape
    nir_idx = nir_band - 1
    red_edge_idx = red_edge_band - 1

    if not (0 <= nir_idx < bands and 0 <= red_edge_idx < bands):
        raise HTTPException(
            status_code=422,
            detail={
                "error": "UNSUPPORTED_BAND_INDEX",
                "message": f"Bands {nir_band}/{red_edge_band} out of range for {bands}-band cube",
                "total_bands": bands,
                "valid_range": [1, bands],
            },
        )

    nir = cube[nir_idx].astype(np.float32)
    red_edge = cube[red_edge_idx].astype(np.float32)

    ndre_analysis = indices.analyze_ndre(
        nir,
        red_edge,
        stress_threshold=stress_threshold,
        auto_calibrate_threshold=auto_calibrate_threshold,
    )
    ndre_stats = {
        "min": ndre_analysis.stats.min,
        "max": ndre_analysis.stats.max,
        "mean": ndre_analysis.stats.mean,
        "std": ndre_analysis.stats.std,
    }

    heatmap_range = preprocessing.resolve_heatmap_range(ndre_analysis.ndre_array)
    heatmap_b64 = preprocessing.array_to_heatmap_base64(
        ndre_analysis.ndre_array,
        vmin=heatmap_range.vmin,
        vmax=heatmap_range.vmax,
        auto_scale=True,
    )

    source_preview_b64 = None
    source_preview_bytes = None
    source_preview_bands = None
    try:
        source_preview_bytes, source_preview_bands = preprocessing.cube_to_rgb_preview_bytes(
            cube,
            nir_band,
            red_edge_band,
        )
        source_preview_b64 = base64.b64encode(source_preview_bytes).decode("utf-8")
    except Exception:
        source_preview_b64 = None
        source_preview_bytes = None
        source_preview_bands = None

    feature_map = inference.extract_features_from_cube(
        cube=cube,
        nir_band=nir_band,
        red_edge_band=red_edge_band,
        stress_threshold=stress_threshold,
    )

    inference_result = None
    model_engine = None
    feature_vector = None
    feature_cols: list[str] = []
    try:
        model_engine = inference.ModelBasedInferenceEngine()
        feature_cols = [str(col) for col in model_engine.feature_columns]
        feature_vector = np.array([feature_map.get(col, 0.0) for col in feature_cols], dtype=np.float32)
        inference_result = model_engine.predict(feature_vector)
    except Exception:
        inference_result = None

    if inference_result is None:
        ndre_mean = float(feature_map.get("ndre_mean", ndre_analysis.stats.mean))
        stress_pct = float(feature_map.get("stress_percentage", ndre_analysis.stress_percentage))
        inference_result = inference.RuleBasedInferenceEngine().predict(ndre_mean, stress_pct)

    final_health_status = inference.reconcile_health_status(
        predicted_class=inference_result.predicted_class,
        stress_percentage=ndre_analysis.stress_percentage,
        confidence=float(inference_result.confidence),
    )

    if model_engine is not None and feature_vector is not None and feature_cols:
        xai_result = explainability.explain_single_sample(
            model=model_engine.model,
            feature_vector=feature_vector,
            feature_names=feature_cols,
            predicted_class=inference_result.predicted_class,
            confidence=inference_result.confidence,
            top_k=5,
            timeout_seconds=1.5,
        )
    else:
        xai_result = explainability.explain_rule_based(
            features=feature_map,
            predicted_class=inference_result.predicted_class,
            confidence=inference_result.confidence,
            top_k=5,
        )

    explanation_payload = _serialize_explainability(xai_result)
    metadata_payload = {
        "analysis_mode": "hyperspectral",
        "source_format": "npy",
        "stress_threshold": stress_threshold,
        "applied_stress_threshold": ndre_analysis.stress_threshold,
        "nir_band": nir_band,
        "red_edge_band": red_edge_band,
        "auto_select_bands": auto_select_bands,
        "auto_calibrate_threshold": auto_calibrate_threshold,
        "auto_band_score": auto_band_score,
        "model_health_status": inference_result.health_status,
        "reconciled_health_status": final_health_status,
        "heatmap_vmin": heatmap_range.vmin,
        "heatmap_vmax": heatmap_range.vmax,
        "source_image_bands": source_preview_bands,
        "explainability": explanation_payload,
    }
    if sample_id and sample_id.strip():
        metadata_payload["sample_id"] = sample_id.strip()
    if plant_id and plant_id.strip():
        metadata_payload["plant_id"] = plant_id.strip()

    spectral_data = {
        "ndre": ndre_stats,
        "healthy_pixels": ndre_analysis.healthy_count,
        "stressed_pixels": ndre_analysis.stressed_count,
        "heatmap_range": {"vmin": heatmap_range.vmin, "vmax": heatmap_range.vmax},
        "analysis_mode": "hyperspectral",
        "feature_map": feature_map,
    }

    model_version = None
    if model_engine is not None:
        model_version = str(model_engine.metadata.get("model_type", "ensemble"))

    artifact_specs = None
    if source_preview_bytes is not None:
        artifact_specs = [("source_preview", "png", source_preview_bytes, "source_image_path")]

    _, db_scan, db_prediction, db_temporal, persisted_metadata = _persist_upload_records(
        db,
        file_name=file_name,
        file_contents=contents,
        image_width=metadata.width,
        image_height=metadata.height,
        total_bands=metadata.total_bands,
        selected_nir_band=nir_band,
        selected_red_edge_band=red_edge_band,
        predicted_class=inference_result.predicted_class,
        confidence=float(inference_result.confidence),
        model_version=model_version,
        stats=ndre_stats,
        stress_percentage=ndre_analysis.stress_percentage,
        stress_threshold=ndre_analysis.stress_threshold,
        heatmap_base64=heatmap_b64,
        heatmap_vmin=heatmap_range.vmin,
        heatmap_vmax=heatmap_range.vmax,
        spectral_data=spectral_data,
        metadata_payload=metadata_payload,
        artifact_specs=artifact_specs,
    )

    class_probs = inference_result.class_probabilities or {}
    return _build_upload_response(
        db_scan=db_scan,
        db_prediction=db_prediction,
        db_temporal=db_temporal,
        filename=file_name,
        analysis_mode="hyperspectral",
        source_format="npy",
        converted_npy_path=persisted_metadata.get("converted_npy_path"),
        cube_shape={"height": height, "width": width, "bands": bands},
        bands_used={"nir_band": nir_band, "red_edge_band": red_edge_band},
        selected_nir_band=nir_band,
        selected_red_edge_band=red_edge_band,
        auto_band_selection_used=auto_select_bands,
        auto_band_score=auto_band_score,
        threshold_auto_calibrated=auto_calibrate_threshold,
        stats=ndre_stats,
        stress_percentage=ndre_analysis.stress_percentage,
        stress_threshold=ndre_analysis.stress_threshold,
        heatmap_base64=heatmap_b64,
        heatmap_vmin=heatmap_range.vmin,
        heatmap_vmax=heatmap_range.vmax,
        predicted_class=inference_result.predicted_class,
        confidence=float(inference_result.confidence),
        health_status=final_health_status,
        class_probabilities=class_probs,
        explanation_payload=explanation_payload,
        source_image_base64=source_preview_b64,
        source_image_path=persisted_metadata.get("source_image_path"),
        source_image_bands=source_preview_bands,
    )


def _handle_rgb_upload(
    *,
    file_name: str,
    contents: bytes,
    stress_threshold: float,
    sample_id: Optional[str],
    plant_id: Optional[str],
    db: Session,
):
    """Photo upload path that converts RGB imagery into a 3-band NPY artifact."""
    rgb_payload, metadata = rgb_preprocessing.load_rgb_image(contents)
    rgb_analysis = rgb_inference.analyze_rgb_image(
        rgb_payload.image,
        stress_threshold=stress_threshold,
    )

    proxy_stats = {
        "min": rgb_analysis.stats.min,
        "max": rgb_analysis.stats.max,
        "mean": rgb_analysis.stats.mean,
        "std": rgb_analysis.stats.std,
    }
    heatmap_range = preprocessing.resolve_heatmap_range(rgb_analysis.proxy_index)
    heatmap_b64 = preprocessing.array_to_heatmap_base64(
        rgb_analysis.proxy_index,
        vmin=heatmap_range.vmin,
        vmax=heatmap_range.vmax,
        auto_scale=True,
    )

    xai_result = explainability.explain_rule_based(
        features=rgb_analysis.feature_map,
        predicted_class=rgb_analysis.inference_result.predicted_class,
        confidence=rgb_analysis.inference_result.confidence,
        top_k=5,
    )
    explanation_payload = _serialize_explainability(xai_result)

    metadata_payload = {
        "analysis_mode": "rgb_proxy",
        "source_format": "rgb_photo",
        "converted_from_photo": True,
        "stress_threshold": stress_threshold,
        "applied_stress_threshold": rgb_analysis.stress_threshold,
        "model_health_status": rgb_analysis.inference_result.health_status,
        "reconciled_health_status": rgb_analysis.inference_result.health_status,
        "heatmap_vmin": heatmap_range.vmin,
        "heatmap_vmax": heatmap_range.vmax,
        "plant_pixel_count": rgb_analysis.plant_pixel_count,
        "background_pixel_count": rgb_analysis.background_pixel_count,
        "explainability": explanation_payload,
    }
    if sample_id and sample_id.strip():
        metadata_payload["sample_id"] = sample_id.strip()
    if plant_id and plant_id.strip():
        metadata_payload["plant_id"] = plant_id.strip()

    spectral_data = {
        "ndre": proxy_stats,
        "healthy_pixels": rgb_analysis.healthy_count,
        "stressed_pixels": rgb_analysis.stressed_count,
        "heatmap_range": {"vmin": heatmap_range.vmin, "vmax": heatmap_range.vmax},
        "analysis_mode": "rgb_proxy",
        "plant_pixel_count": rgb_analysis.plant_pixel_count,
        "background_pixel_count": rgb_analysis.background_pixel_count,
        "feature_map": rgb_analysis.feature_map,
    }

    converted_cube_bytes = rgb_preprocessing.serialize_rgb_cube(rgb_payload.cube)
    _, db_scan, db_prediction, db_temporal, persisted_metadata = _persist_upload_records(
        db,
        file_name=file_name,
        file_contents=contents,
        image_width=metadata.width,
        image_height=metadata.height,
        total_bands=metadata.total_bands,
        selected_nir_band=0,
        selected_red_edge_band=0,
        predicted_class=rgb_analysis.inference_result.predicted_class,
        confidence=float(rgb_analysis.inference_result.confidence),
        model_version="rgb_proxy_v1",
        stats=proxy_stats,
        stress_percentage=rgb_analysis.stress_percentage,
        stress_threshold=rgb_analysis.stress_threshold,
        heatmap_base64=heatmap_b64,
        heatmap_vmin=heatmap_range.vmin,
        heatmap_vmax=heatmap_range.vmax,
        spectral_data=spectral_data,
        metadata_payload=metadata_payload,
        artifact_specs=[("rgb_cube", "npy", converted_cube_bytes, "converted_npy_path")],
    )

    class_probs = rgb_analysis.inference_result.class_probabilities or {}
    return _build_upload_response(
        db_scan=db_scan,
        db_prediction=db_prediction,
        db_temporal=db_temporal,
        filename=file_name,
        analysis_mode="rgb_proxy",
        source_format="rgb_photo",
        converted_npy_path=persisted_metadata.get("converted_npy_path"),
        cube_shape={"height": metadata.height, "width": metadata.width, "bands": metadata.total_bands},
        bands_used=None,
        selected_nir_band=None,
        selected_red_edge_band=None,
        auto_band_selection_used=False,
        auto_band_score=None,
        threshold_auto_calibrated=False,
        stats=proxy_stats,
        stress_percentage=rgb_analysis.stress_percentage,
        stress_threshold=rgb_analysis.stress_threshold,
        heatmap_base64=heatmap_b64,
        heatmap_vmin=heatmap_range.vmin,
        heatmap_vmax=heatmap_range.vmax,
        predicted_class=rgb_analysis.inference_result.predicted_class,
        confidence=float(rgb_analysis.inference_result.confidence),
        health_status=str(rgb_analysis.inference_result.health_status or "unknown"),
        class_probabilities=class_probs,
        explanation_payload=explanation_payload,
        source_image_base64=None,
        source_image_path=persisted_metadata.get("source_image_path"),
        source_image_bands=None,
    )


@router.post("/process-image", response_model=ProcessImageResponse)
async def process_image(
    file: UploadFile = File(...),
    nir_band: int = 5,
    red_edge_band: int = 4,
    stress_threshold: float = 0.2,
    auto_select_bands: bool = False,
    auto_calibrate_threshold: bool = False,
    db: Session = Depends(get_db),
):
    """Process hyperspectral NPY image and compute NDRE analysis."""
    if not file or not file.filename:
        raise InvalidUploadError(message="No file was uploaded.")
    if not preprocessing.validate_npy_file(file.filename):
        raise UnsupportedFileTypeError(filename=file.filename, allowed_types=".npy")
    if nir_band < 1 or red_edge_band < 1:
        raise UnsupportedBandIndexError(
            message="Band indices must be positive 1-based values.",
            details={"nir_band": nir_band, "red_edge_band": red_edge_band},
        )

    contents = await file.read()
    if not contents:
        raise InvalidUploadError(message="Uploaded file is empty.", details={"filename": file.filename})

    try:
        cube, metadata = preprocessing.load_npy_cube(contents)
        if auto_select_bands:
            selection = preprocessing.auto_select_ndre_bands(cube, stress_threshold=stress_threshold)
            nir_band = selection.nir_band
            red_edge_band = selection.red_edge_band

        nir = cube.get_band(nir_band, dtype=np.float32)
        red_edge = cube.get_band(red_edge_band, dtype=np.float32)
    except (UnsupportedBandIndexError, RasterReadError):
        raise

    try:
        storage_file = storage.save_uploaded_file(file.filename, contents)
    except IOError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(exc)}")

    scan_create = ScanCreate(
        filename=file.filename,
        file_path=storage_file.full_path,
        image_width=metadata.width,
        image_height=metadata.height,
        total_bands=metadata.total_bands,
        selected_nir_band=nir_band,
        selected_red_edge_band=red_edge_band,
    )
    try:
        db_scan = create_scan(db, scan_create)
    except SQLAlchemyError as exc:
        db.rollback()
        raise DatabaseWriteError(details={"operation": "create_scan", "reason": str(exc)})

    ndre_analysis = indices.analyze_ndre(
        nir,
        red_edge,
        stress_threshold=stress_threshold,
        auto_calibrate_threshold=auto_calibrate_threshold,
    )
    ndre_stats = {
        "min": ndre_analysis.stats.min,
        "max": ndre_analysis.stats.max,
        "mean": ndre_analysis.stats.mean,
        "std": ndre_analysis.stats.std,
    }

    heatmap_range = preprocessing.resolve_heatmap_range(ndre_analysis.ndre_array)
    heatmap_b64 = preprocessing.array_to_heatmap_base64(
        ndre_analysis.ndre_array,
        vmin=heatmap_range.vmin,
        vmax=heatmap_range.vmax,
        auto_scale=True,
    )

    try:
        create_spectral_stats(
            db,
            scan_id=db_scan.id,
            ndre_min=ndre_analysis.stats.min,
            ndre_max=ndre_analysis.stats.max,
            ndre_mean=ndre_analysis.stats.mean,
            ndre_std=ndre_analysis.stats.std,
            stress_percentage=ndre_analysis.stress_percentage,
            stress_threshold=ndre_analysis.stress_threshold,
            heatmap_base64=heatmap_b64,
            spectral_data={
                "ndre": ndre_stats,
                "healthy_pixels": ndre_analysis.healthy_count,
                "stressed_pixels": ndre_analysis.stressed_count,
                "heatmap_range": {"vmin": heatmap_range.vmin, "vmax": heatmap_range.vmax},
            },
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise DatabaseWriteError(details={"operation": "create_spectral_stats", "reason": str(exc)})

    try:
        create_scan_metadata(
            db,
            db_scan.id,
            health_status=indices.classify_health_status(ndre_analysis.stress_percentage),
            metadata={
                "stress_threshold": stress_threshold,
                "applied_stress_threshold": ndre_analysis.stress_threshold,
                "nir_band": nir_band,
                "red_edge_band": red_edge_band,
                "auto_calibrate_threshold": auto_calibrate_threshold,
                "heatmap_vmin": heatmap_range.vmin,
                "heatmap_vmax": heatmap_range.vmax,
            },
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise DatabaseWriteError(details={"operation": "create_scan_metadata", "reason": str(exc)})

    return ProcessImageResponse(
        scan_id=db_scan.id,
        filename=storage_file.original_filename,
        heatmap_base64=heatmap_b64,
        image_shape={"height": metadata.height, "width": metadata.width},
        ndre_stats=ndre_stats,
        stress_percentage=ndre_analysis.stress_percentage,
        stress_threshold=ndre_analysis.stress_threshold,
        upload_timestamp=db_scan.upload_timestamp,
    )


@router.post("/scans/upload", response_model=MulticlassUploadResponse)
async def upload_multiclass_scan(
    file: UploadFile = File(...),
    nir_band: int = Form(5),
    red_edge_band: int = Form(4),
    stress_threshold: float = Form(0.2),
    auto_select_bands: bool = Form(False),
    auto_calibrate_threshold: bool = Form(False),
    sample_id: Optional[str] = Form(None),
    plant_id: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Upload either a hyperspectral cube or a plant photo for analysis."""
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    try:
        contents = await file.read()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read upload: {str(exc)}") from exc

    if not contents:
        raise HTTPException(status_code=400, detail="File is empty")

    filename = file.filename
    if preprocessing.validate_npy_file(filename):
        return _handle_hyperspectral_upload(
            file_name=filename,
            contents=contents,
            nir_band=nir_band,
            red_edge_band=red_edge_band,
            stress_threshold=stress_threshold,
            auto_select_bands=auto_select_bands,
            auto_calibrate_threshold=auto_calibrate_threshold,
            sample_id=sample_id,
            plant_id=plant_id,
            db=db,
        )

    if rgb_preprocessing.validate_rgb_file(filename):
        return _handle_rgb_upload(
            file_name=filename,
            contents=contents,
            stress_threshold=stress_threshold,
            sample_id=sample_id,
            plant_id=plant_id,
            db=db,
        )

    raise UnsupportedFileTypeError(
        filename=filename,
        allowed_types=".npy, .jpg, .jpeg, .png, .webp",
    )
