import io
import base64
import tempfile
import numpy as np
import rasterio
import matplotlib.cm as cm
import matplotlib.colors as mcolors
from PIL import Image
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def compute_ndre(nir: np.ndarray, red_edge: np.ndarray) -> np.ndarray:
    denom = nir + red_edge
    return np.where(denom == 0, 0.0, (nir - red_edge) / denom).astype(np.float32)

def array_to_heatmap_base64(index_array: np.ndarray) -> str:
    norm = mcolors.Normalize(vmin=-1.0, vmax=1.0)
    rgba = cm.RdYlGn(norm(index_array))          # (H, W, 4) float64
    rgba_uint8 = (rgba * 255).astype(np.uint8)
    img = Image.fromarray(rgba_uint8, mode="RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")

@app.post("/process-image")
async def process_image(
    file: UploadFile = File(...),
    nir_band: int = 5,
    red_edge_band: int = 4,
):
    if not file.filename.lower().endswith((".tif", ".tiff")):
        raise HTTPException(status_code=400, detail="Only GeoTIFF files are supported.")

    contents = await file.read()

    with tempfile.NamedTemporaryFile(suffix=".tif", delete=True) as tmp:
        tmp.write(contents)
        tmp.flush()

        with rasterio.open(tmp.name) as src:
            total_bands = src.count
            if max(nir_band, red_edge_band) > total_bands:
                raise HTTPException(
                    status_code=422,
                    detail=f"File has {total_bands} bands; requested NIR={nir_band}, RedEdge={red_edge_band}."
                )
            nir = src.read(nir_band).astype(np.float32)
            red_edge = src.read(red_edge_band).astype(np.float32)
            height, width = nir.shape

    ndre = compute_ndre(nir, red_edge)

    valid = ndre[np.isfinite(ndre)]
    stats = {
        "min": round(float(valid.min()), 4),
        "max": round(float(valid.max()), 4),
        "mean": round(float(valid.mean()), 4),
        "std": round(float(valid.std()), 4),
    }

    STRESS_THRESHOLD = 0.2
    stress_pct = round(float(np.sum(ndre < STRESS_THRESHOLD) / ndre.size * 100), 2)

    heatmap_b64 = array_to_heatmap_base64(ndre)

    return {
        "heatmap_base64": heatmap_b64,
        "image_shape": {"height": height, "width": width},
        "ndre_stats": stats,
        "stress_percentage": stress_pct,
        "stress_threshold": STRESS_THRESHOLD,
    }
