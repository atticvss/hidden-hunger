# Hidden Hunger

Hidden Hunger is a FastAPI-based plant health analysis platform for detecting crop nutrient stress from hyperspectral imagery. It processes TIFF/HSI scans, computes vegetation indices such as NDRE, generates stress heatmaps, stores scan history, and provides model-backed predictions with explainability support for the most influential spectral features.

## Features

- Upload and analyze hyperspectral plant scans through a FastAPI API and simple web frontend.
- Compute NDRE statistics, stress percentage, vegetation vigor, and health status.
- Generate visual heatmaps and persist uploaded scans, outputs, and analysis metadata.
- Store scan history with SQLite/SQLAlchemy and modular CRUD services.
- Support ML inference, multiclass stress prediction, temporal analysis, and SHAP-style explanations with a feature-importance fallback.

## Data

Large datasets and generated artifacts are stored in Google Drive:

https://drive.google.com/drive/folders/17GGyFkM7WV1SdjVFK1m4G1_89litFl2z?usp=sharing

Expected contents (repo root level):
- beyond-visible-spectrum-ai-for-agriculture-2025/
- outputs/
- uploads/
- models_store/

These directories are excluded from git via .gitignore. Download the Drive contents and place the folders at the repository root to match the project paths.
