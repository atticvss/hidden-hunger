"""
make_plant_tiff.py  (fixed — uses rasterio to write)
Run with venv active:
    python3 make_plant_tiff.py
Outputs: samples/plant_scene.tif
"""

import numpy as np
import rasterio
from rasterio.transform import from_bounds
import os

os.makedirs("samples", exist_ok=True)

rng = np.random.default_rng(42)
H, W, BANDS = 256, 256, 10

y, x = np.mgrid[0:H, 0:W]
cx, cy = W / 2, H / 2

# ── Spatial masks ─────────────────────────────────────────────
leaf       = ((x - cx) / 90)**2 + ((y - cy) / 110)**2 < 1.0
midrib     = leaf & (np.abs(x - cx) < 8)
veins      = leaf & (np.abs((y - cy) % 40 - 20) < 4) & ~midrib
leaf_inner = ((x - cx) / 80)**2 + ((y - cy) / 100)**2 < 1.0
edges      = leaf & ~leaf_inner
stress1    = ((x - (cx - 35)) / 28)**2 + ((y - (cy - 30)) / 22)**2 < 1.0
stress2    = ((x - (cx + 40)) / 20)**2 + ((y - (cy + 35)) / 25)**2 < 1.0
stress     = (stress1 | stress2) & leaf & ~midrib & ~veins
healthy    = leaf & ~stress & ~midrib & ~veins & ~edges
background = ~leaf

# ── Build band array (BANDS, H, W) ───────────────────────────
NIR_IDX = 4   # band 5 (1-indexed in rasterio)
RE_IDX  = 3   # band 4 (1-indexed in rasterio)

data = rng.uniform(0.05, 0.15, (BANDS, H, W)).astype(np.float32)

def set_zone(mask, nir, re, jitter=0.03):
    n = mask.sum()
    data[NIR_IDX][mask] = nir + rng.uniform(-jitter, jitter, n)
    data[RE_IDX ][mask] = re  + rng.uniform(-jitter, jitter, n)

set_zone(healthy,    0.82, 0.28)   # NDRE ≈ +0.49  🟢
set_zone(veins,      0.75, 0.30)   # NDRE ≈ +0.43  🟡
set_zone(edges,      0.55, 0.40)   # NDRE ≈ +0.16  🟠
set_zone(stress,     0.30, 0.55)   # NDRE ≈ -0.30  🔴
set_zone(midrib,     0.40, 0.40)   # NDRE ≈  0.00  🟡
set_zone(background, 0.18, 0.12)   # NDRE ≈ +0.20  🟤

# ── Write with rasterio so band count is correct ─────────────
OUT = "samples/plant_scene.tif"
transform = from_bounds(0, 0, 1, 1, W, H)

with rasterio.open(
    OUT, 'w',
    driver='GTiff',
    height=H, width=W,
    count=BANDS,
    dtype=np.float32,
    crs='EPSG:4326',
    transform=transform,
) as dst:
    for i in range(BANDS):
        dst.write(data[i], i + 1)

# ── Verify band count ─────────────────────────────────────────
with rasterio.open(OUT) as src:
    actual_bands = src.count

# ── Compute expected stats ────────────────────────────────────
nir   = data[NIR_IDX].astype(np.float64)
re    = data[RE_IDX ].astype(np.float64)
denom = nir + re
ndre  = np.where(denom == 0, 0.0, (nir - re) / denom)
stress_pct = (ndre < 0.2).sum() / ndre.size * 100

print()
print("=" * 54)
print(f"  plant_scene.tif — {actual_bands} bands confirmed, 256×256 px")
print("=" * 54)
print()
print("  Upload settings:")
print("    NIR Band     →  5")
print("    RedEdge Band →  4")
print()
print("  Expected site output:")
print(f"    Min    : {ndre.min():.4f}")
print(f"    Max    : {ndre.max():.4f}")
print(f"    Mean   : {ndre.mean():.4f}")
print(f"    Std    : {ndre.std():.4f}")
print(f"    Stress : {stress_pct:.1f}%")
print()
print("  Heatmap should show:")
print("    • Green oval leaf in the centre")
print("    • Two red/orange stress blotches")
print("    • Neutral soil background")
