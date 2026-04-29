# Hidden Hunger - Hyperspectral Plant Analysis API

## Project Structure

```
app/
├── __init__.py
├── main.py                 # FastAPI app initialization and routing
├── database.py            # SQLAlchemy setup and session management
├── models.py              # SQLAlchemy ORM models
├── schemas.py             # Pydantic request/response schemas
├── deps.py                # Dependency injection utilities
├── crud.py                # Database CRUD operations
├── routers/
│   ├── __init__.py
│   ├── upload.py          # Image upload and processing endpoints
│   └── history.py         # Analysis history and retrieval endpoints
└── services/
    ├── __init__.py
    ├── indices.py         # Vegetation indices computation (NDRE, NDVI)
    ├── preprocessing.py   # Image preprocessing and validation
    ├── storage.py         # File storage utilities
    └── inference.py       # ML model inference (placeholder for future)
```

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the application:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Or use the provided script:
```bash
chmod +x run.sh
./run.sh
```

## API Endpoints

### Upload and Processing
- **POST** `/api/process-image`
  - Upload a GeoTIFF file for analysis
  - Parameters: `file`, `nir_band` (default: 5), `red_edge_band` (default: 4)
  - Returns: NDRE statistics, heatmap (base64), stress percentage, and analysis ID

### Analysis History
- **GET** `/api/history` - List all analyses (with pagination)
- **GET** `/api/history/{analysis_id}` - Get details of a specific analysis
- **DELETE** `/api/history/{analysis_id}` - Delete an analysis record

### Health Checks
- **GET** `/` - API info
- **GET** `/health` - Health check

## Database

The project uses SQLite by default for development. Update `DATABASE_URL` in `app/database.py` to use PostgreSQL for production:

```python
DATABASE_URL = "postgresql://user:password@localhost/hidden_hunger"
```

## Key Features

1. **NDRE Computation**: Computes Normalized Difference Red Edge index from hyperspectral data
2. **Database Persistence**: Stores analysis results with full metadata
3. **Heatmap Generation**: Generates RGBA heatmaps with RdYlGn colormap (base64 encoded)
4. **Stress Analysis**: Calculates percentage of pixels below stress threshold
5. **RESTful API**: Clean, documented API endpoints with OpenAPI/Swagger UI at `/docs`

## Current NDRE Behavior (Preserved)

- NDRE formula: (NIR - Red Edge) / (NIR + Red Edge)
- Default bands: NIR=5, Red Edge=4
- Stress threshold: 0.2
- Statistics: min, max, mean, std (on valid pixels)
- Visualization: RdYlGn colormap [-1.0, 1.0]

## Next Steps

- Add async database support with async SQLAlchemy
- Add authentication and authorization
- Create ML model inference endpoints
- Add data validation and error handling enhancements
- Implement caching for frequently accessed analyses
- Add CSV/JSON export of analysis results
