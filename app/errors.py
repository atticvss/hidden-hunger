"""Application-level exception types and structured error payload helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppError(Exception):
    """Base app exception mapped to structured JSON response."""

    message: str
    code: str
    status_code: int
    details: Any = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "success": False,
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            },
        }


class InvalidUploadError(AppError):
    def __init__(self, message: str = "Invalid file upload.", details: Any = None):
        super().__init__(
            message=message,
            code="INVALID_UPLOAD",
            status_code=400,
            details=details or {},
        )


class UnsupportedFileTypeError(AppError):
    def __init__(self, filename: str | None = None, allowed_types: str = ".npy"):
        super().__init__(
            message=f"Unsupported file type. Allowed: {allowed_types}",
            code="UNSUPPORTED_FILE_TYPE",
            status_code=415,
            details={"filename": filename or "", "allowed_types": allowed_types},
        )


class UnsupportedBandIndexError(AppError):
    def __init__(self, message: str, details: Any = None):
        super().__init__(
            message=message,
            code="UNSUPPORTED_BAND_INDEX",
            status_code=422,
            details=details or {},
        )


class RasterReadError(AppError):
    def __init__(self, message: str = "Failed to read hyperspectral cube.", details: Any = None):
        super().__init__(
            message=message,
            code="RASTER_READ_FAILED",
            status_code=422,
            details=details or {},
        )


class DatabaseWriteError(AppError):
    def __init__(self, message: str = "Database write failed.", details: Any = None):
        super().__init__(
            message=message,
            code="DATABASE_WRITE_FAILED",
            status_code=500,
            details=details or {},
        )


class MissingModelFilesError(AppError):
    def __init__(self, details: Any = None):
        super().__init__(
            message="Model artifacts are missing. Train the model before using model-only inference.",
            code="MODEL_FILES_MISSING",
            status_code=503,
            details=details or {},
        )
