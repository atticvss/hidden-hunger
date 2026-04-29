"""
prepare_dataset.py

Build a tabular training dataset from labeled hyperspectral NPY samples.

Supports two input modes:
1) Folder structure mode:
   data_root/
     healthy/
    sample1.npy
     nitrogen_deficient/
    sample2.npy
     phosphorus_deficient/
    sample3.npy
     drought_stress/
    sample4.npy

2) CSV manifest mode with at least columns:
    - file_path (or path / file / id)
   - label
   Optional per-row overrides:
   - nir_band
   - red_edge_band
   - red_band

Example usage:
    python3 prepare_dataset.py \
        --input-dir dataset/train \
        --output-csv training_features.csv \
        --nir-band 191 \
        --red-edge-band 148 \
        --red-band 120

  python3 prepare_dataset.py \
    --manifest dataset_manifest.csv \
    --output-csv training_features.csv
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np


VALID_EXTENSIONS = {".npy"}
DEFAULT_LABELS = {
    "healthy",
    "nitrogen_deficient",
    "drought_stress",
    "disease_stress",
    "pest_stress",
}


@dataclass
class SampleSpec:
    """Input sample specification."""

    file_path: Path
    label: str
    nir_band: int
    red_edge_band: int
    red_band: int | None


def safe_normalized_difference(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Compute (a-b)/(a+b) with divide-by-zero protection."""
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    denom = a + b
    return np.divide(a - b, denom, out=np.zeros_like(a), where=denom != 0)


def finite_stats(arr: np.ndarray, prefix: str) -> dict[str, float]:
    """Return min/max/mean/std stats for finite values."""
    vals = arr[np.isfinite(arr)]
    if vals.size == 0:
        return {
            f"{prefix}_min": np.nan,
            f"{prefix}_max": np.nan,
            f"{prefix}_mean": np.nan,
            f"{prefix}_std": np.nan,
        }

    return {
        f"{prefix}_min": float(np.min(vals)),
        f"{prefix}_max": float(np.max(vals)),
        f"{prefix}_mean": float(np.mean(vals)),
        f"{prefix}_std": float(np.std(vals)),
    }


def percentiles(arr: np.ndarray, prefix: str) -> dict[str, float]:
    """Return p10/p50/p90 for finite values."""
    vals = arr[np.isfinite(arr)]
    if vals.size == 0:
        return {
            f"{prefix}_p10": np.nan,
            f"{prefix}_p50": np.nan,
            f"{prefix}_p90": np.nan,
        }

    p10, p50, p90 = np.percentile(vals, [10, 50, 90])
    return {
        f"{prefix}_p10": float(p10),
        f"{prefix}_p50": float(p50),
        f"{prefix}_p90": float(p90),
    }


def collect_from_folder(
    input_dir: Path,
    nir_band: int,
    red_edge_band: int,
    red_band: int | None,
) -> list[SampleSpec]:
    """Collect samples from label subfolders."""
    specs: list[SampleSpec] = []

    if not input_dir.exists() or not input_dir.is_dir():
        raise ValueError(f"Input directory does not exist: {input_dir}")

    for label_dir in sorted([p for p in input_dir.iterdir() if p.is_dir()]):
        label = label_dir.name.strip().lower()

        for path in sorted(label_dir.rglob("*")):
            if path.is_file() and path.suffix.lower() in VALID_EXTENSIONS:
                specs.append(
                    SampleSpec(
                        file_path=path,
                        label=label,
                        nir_band=nir_band,
                        red_edge_band=red_edge_band,
                        red_band=red_band,
                    )
                )

    return specs


def load_cube_from_npy(path: Path) -> np.ndarray:
    """Load NPY cube and normalize shape to (bands, height, width)."""
    data = np.load(path, allow_pickle=False)
    arr = np.asarray(data)

    if arr.ndim != 3:
        raise ValueError(f"Expected 3D cube in {path}, got shape={arr.shape}")

    # Accept both (bands, height, width) and (height, width, bands)
    if arr.shape[0] <= arr.shape[1] and arr.shape[0] <= arr.shape[2]:
        cube = arr
    elif arr.shape[2] <= arr.shape[0] and arr.shape[2] <= arr.shape[1]:
        cube = np.transpose(arr, (2, 0, 1))
    else:
        raise ValueError(f"Unable to infer band axis for {path}, shape={arr.shape}")

    return np.asarray(cube, dtype=np.float32)


def collect_from_manifest(
    manifest_path: Path,
    default_nir_band: int,
    default_red_edge_band: int,
    default_red_band: int | None,
    base_dir: Path | None = None,
) -> list[SampleSpec]:
    """Collect samples from CSV manifest."""
    if not manifest_path.exists() or not manifest_path.is_file():
        raise ValueError(f"Manifest file does not exist: {manifest_path}")

    specs: list[SampleSpec] = []
    root_dir = base_dir.resolve() if base_dir else manifest_path.parent.resolve()

    with manifest_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        cols = {c.strip().lower() for c in (reader.fieldnames or [])}

        if "label" not in cols:
            raise ValueError("Manifest must include a 'label' column.")

        path_col = None
        for candidate in ("file_path", "path", "file", "id"):
            if candidate in cols:
                path_col = candidate
                break

        if path_col is None:
            raise ValueError("Manifest must include one of: file_path, path, file, id")

        for row in reader:
            label = str(row.get("label", "")).strip().lower()
            path_val = str(row.get(path_col, "")).strip()
            if not path_val:
                continue

            p = Path(path_val)
            if not p.is_absolute():
                p = (root_dir / p).resolve()

            nir_band = int(row.get("nir_band") or default_nir_band)
            red_edge_band = int(row.get("red_edge_band") or default_red_edge_band)

            red_raw = row.get("red_band")
            if red_raw is None or str(red_raw).strip() == "":
                red_band = default_red_band
            else:
                red_band = int(red_raw)

            specs.append(
                SampleSpec(
                    file_path=p,
                    label=label,
                    nir_band=nir_band,
                    red_edge_band=red_edge_band,
                    red_band=red_band,
                )
            )

    return specs


def check_band_index(band: int, total_bands: int, name: str) -> None:
    """Validate 1-based band index."""
    if band < 1 or band > total_bands:
        raise ValueError(
            f"{name} band index out of range: {band}. File has {total_bands} bands."
        )


def extract_features(spec: SampleSpec) -> dict[str, float | int | str]:
    """Extract tabular features from one hyperspectral NPY sample."""
    cube = load_cube_from_npy(spec.file_path)
    total_bands, height, width = cube.shape

    check_band_index(spec.nir_band, total_bands, "NIR")
    check_band_index(spec.red_edge_band, total_bands, "Red-edge")

    nir = cube[spec.nir_band - 1]
    red_edge = cube[spec.red_edge_band - 1]

    ndre = safe_normalized_difference(nir, red_edge)
    ndre_valid = ndre[np.isfinite(ndre)]

    row: dict[str, float | int | str] = {
        "file_path": str(spec.file_path),
        "label": spec.label,
        "height": int(height),
        "width": int(width),
        "total_bands": int(total_bands),
        "nir_band": int(spec.nir_band),
        "red_edge_band": int(spec.red_edge_band),
        "red_band": int(spec.red_band) if spec.red_band is not None else "",
    }

    # NDRE summary features
    row.update(finite_stats(ndre, "ndre"))
    row.update(percentiles(ndre, "ndre"))
    if ndre_valid.size > 0:
        row["stress_percentage"] = float((ndre_valid < 0.2).sum() * 100.0 / ndre_valid.size)
    else:
        row["stress_percentage"] = 0.0

    # NDVI summary features (if red band is provided and valid)
    if spec.red_band is not None and 1 <= spec.red_band <= total_bands:
        red = cube[spec.red_band - 1]
        ndvi = safe_normalized_difference(nir, red)
        ndvi_stats = finite_stats(ndvi, "ndvi")
    else:
        ndvi_stats = {
            "ndvi_min": np.nan,
            "ndvi_max": np.nan,
            "ndvi_mean": np.nan,
            "ndvi_std": np.nan,
        }
    row.update(ndvi_stats)

    # Per-band global summaries (across all bands/pixels)
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

    row.update(
        {
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
            "low_region_mean": float(np.mean(low_region)) if low_region.size > 0 else 0.0,
            "mid_region_mean": float(np.mean(mid_region)) if mid_region.size > 0 else 0.0,
            "high_region_mean": float(np.mean(high_region)) if high_region.size > 0 else 0.0,
            "low_mid_ratio": float(np.mean(low_region) / np.mean(mid_region)) if low_region.size > 0 and mid_region.size > 0 and np.mean(mid_region) != 0 else 0.0,
            "mid_high_ratio": float(np.mean(mid_region) / np.mean(high_region)) if mid_region.size > 0 and high_region.size > 0 and np.mean(high_region) != 0 else 0.0,
            "cube_min": float(np.min(cube)),
            "cube_max": float(np.max(cube)),
            "cube_mean": float(np.mean(cube)),
            "cube_std": float(np.std(cube)),
        }
    )

    # Red-edge statistics and simple red-edge-to-NIR relation features
    row.update(finite_stats(red_edge, "red_edge"))
    row.update(percentiles(red_edge, "red_edge"))

    row.update(
        {
            "nir_mean": float(np.mean(nir)),
            "nir_std": float(np.std(nir)),
            "red_edge_nir_diff_mean": float(np.mean(nir - red_edge)),
            "red_edge_nir_ratio_mean": float(
                np.mean(np.divide(red_edge, nir, out=np.zeros_like(red_edge), where=nir != 0))
            ),
        }
    )

    return row


def write_csv(rows: Iterable[dict], output_csv: Path) -> None:
    """Write feature rows to CSV."""
    rows = list(rows)
    if not rows:
        raise ValueError("No valid samples were processed; output CSV not written.")

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())

    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare tabular dataset features from labeled hyperspectral NPY samples."
    )
    parser.add_argument("--input-dir", type=Path, default=None, help="Labeled folder root")
    parser.add_argument("--manifest", type=Path, default=None, help="CSV manifest path")
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=None,
        help="Optional base directory for relative paths in manifest (useful when manifest contains file ids)",
    )
    parser.add_argument("--output-csv", type=Path, required=True, help="Output dataset CSV path")

    parser.add_argument("--nir-band", type=int, default=5, help="Default NIR band (1-based)")
    parser.add_argument("--red-edge-band", type=int, default=4, help="Default red-edge band (1-based)")
    parser.add_argument("--red-band", type=int, default=None, help="Default red band for NDVI (1-based)")

    parser.add_argument(
        "--strict-labels",
        action="store_true",
        help="Fail if labels outside expected set are found",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if bool(args.input_dir) == bool(args.manifest):
        raise ValueError("Provide exactly one input source: --input-dir OR --manifest")

    if args.input_dir:
        specs = collect_from_folder(
            input_dir=args.input_dir,
            nir_band=args.nir_band,
            red_edge_band=args.red_edge_band,
            red_band=args.red_band,
        )
    else:
        specs = collect_from_manifest(
            manifest_path=args.manifest,
            default_nir_band=args.nir_band,
            default_red_edge_band=args.red_edge_band,
            default_red_band=args.red_band,
            base_dir=args.base_dir,
        )

    if not specs:
        raise ValueError("No NPY samples found to process.")

    labels_found = {s.label for s in specs}
    unknown_labels = sorted(labels_found - DEFAULT_LABELS)
    if unknown_labels:
        msg = f"Found non-default labels: {', '.join(unknown_labels)}"
        if args.strict_labels:
            raise ValueError(msg)
        print(f"Warning: {msg}")

    rows: list[dict] = []
    failed = 0

    for i, spec in enumerate(specs, start=1):
        try:
            row = extract_features(spec)
            rows.append(row)
        except Exception as exc:
            failed += 1
            print(f"[{i}/{len(specs)}] Skipped {spec.file_path}: {exc}")
            continue

        if i % 10 == 0 or i == len(specs):
            print(f"Processed {i}/{len(specs)} samples...")

    write_csv(rows, args.output_csv)

    print("\nDataset preparation complete")
    print(f"  Input samples found : {len(specs)}")
    print(f"  Output rows written : {len(rows)}")
    print(f"  Samples skipped     : {failed}")
    print(f"  Output CSV          : {args.output_csv}")


if __name__ == "__main__":
    main()
