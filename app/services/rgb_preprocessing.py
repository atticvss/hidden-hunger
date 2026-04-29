"""RGB image preprocessing helpers for photo uploads."""

from __future__ import annotations

import io
from typing import NamedTuple

import numpy as np
from PIL import Image

from app.errors import RasterReadError


SUPPORTED_RGB_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


class RGBImageMetadata(NamedTuple):
    """Metadata for an uploaded RGB image."""

    height: int
    width: int
    total_bands: int
    dtype: str
    source_format: str


class RGBUploadData(NamedTuple):
    """Normalized RGB payload used by the photo analysis branch."""

    image: np.ndarray
    cube: np.ndarray


def validate_rgb_file(filename: str) -> bool:
    """Return True when the filename looks like a supported RGB image."""
    return filename.lower().endswith(SUPPORTED_RGB_EXTENSIONS)


def load_rgb_image(file_contents: bytes) -> tuple[RGBUploadData, RGBImageMetadata]:
    """Load uploaded image bytes and normalize to RGB float arrays."""
    try:
        image = Image.open(io.BytesIO(file_contents)).convert("RGB")
    except Exception as exc:
        raise RasterReadError(
            message="Failed to decode RGB image.",
            details={"reason": str(exc)},
        ) from exc

    rgb = np.asarray(image, dtype=np.float32) / 255.0
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise RasterReadError(
            message="Decoded image is not a 3-channel RGB image.",
            details={"shape": list(rgb.shape)},
        )

    cube = np.transpose(rgb, (2, 0, 1)).astype(np.float32)
    height, width = rgb.shape[:2]

    metadata = RGBImageMetadata(
        height=int(height),
        width=int(width),
        total_bands=3,
        dtype=str(cube.dtype),
        source_format="rgb",
    )

    return RGBUploadData(image=rgb.astype(np.float32), cube=cube), metadata


def serialize_rgb_cube(cube: np.ndarray) -> bytes:
    """Serialize a 3-band RGB cube into NPY bytes for artifact storage."""
    buf = io.BytesIO()
    np.save(buf, np.asarray(cube, dtype=np.float32), allow_pickle=False)
    buf.seek(0)
    return buf.getvalue()
