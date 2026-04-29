"""
export_hsi_to_tiff.py
Run with venv active:
    python3 export_hsi_to_tiff.py

Downloads one real hyperspectral plant image and saves it as a
multi-band TIFF ready for your Hidden Hunger app.
"""

import numpy as np
import tifffile
from hsi_dataset_api import HsiDataset

# ── Download (first run only, ~200 MB cached locally after) ───
dataset = HsiDataset('.', data_type='train')

# ── Grab first sample ─────────────────────────────────────────
sample = dataset[0]
image  = sample['image']   # shape: (H, W, 237 bands), float64

print(f"Raw shape  : {image.shape}")
print(f"Value range: {image.min():.4f} → {image.max():.4f}")

# ── Rearrange to (bands, H, W) — what rasterio expects ────────
image_banded = image.transpose(2, 0, 1).astype(np.float32)  # (237, H, W)

# ── Save as multi-band GeoTIFF ─────────────────────────────────
OUT = "samples/hsi_plant_sample.tif"
tifffile.imwrite(OUT, image_banded)

print(f"\nSaved : {OUT}")
print(f"Shape : {image_banded.shape}  →  {image_banded.shape[0]} bands, "
      f"{image_banded.shape[1]}×{image_banded.shape[2]} px")

# ── Recommend band numbers ─────────────────────────────────────
# HSI Dataset covers 400–900 nm across 237 bands
# Band spacing = 500 nm / 237 ≈ 2.11 nm per band
# RedEdge ≈ 710 nm → band index ≈ (710-400)/2.11 ≈ 147 → band 148 (1-indexed)
# NIR     ≈ 800 nm → band index ≈ (800-400)/2.11 ≈ 190 → band 191 (1-indexed)

RE_BAND  = 148
NIR_BAND = 191

# ── Quick sanity check: compute NDRE right here ────────────────
nir = image_banded[NIR_BAND - 1].astype(np.float64)
re  = image_banded[RE_BAND  - 1].astype(np.float64)
denom = nir + re
ndre  = np.where(denom == 0, 0.0, (nir - re) / denom)

print()
print("=" * 52)
print("  NDRE preview (computed locally for verification)")
print("=" * 52)
print(f"  Min    : {ndre.min():.4f}")
print(f"  Max    : {ndre.max():.4f}")
print(f"  Mean   : {ndre.mean():.4f}")
print(f"  Std    : {ndre.std():.4f}")
stress_pct = (ndre < 0.2).sum() / ndre.size * 100
print(f"  Stress : {stress_pct:.1f}%  (pixels with NDRE < 0.2)")
print()
print("  Upload settings for your app:")
print(f"    NIR Band     → {NIR_BAND}")
print(f"    RedEdge Band → {RE_BAND}")
print()
print("  Compare these numbers to what the site reports.")
print("  They should match within ±0.0001.")
