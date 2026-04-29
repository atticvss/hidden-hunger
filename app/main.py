"""FastAPI application factory and configuration."""
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.database import init_db
from app.routers import upload, history
from app.errors import AppError, InvalidUploadError

# Initialize database
init_db()

# Create FastAPI app
app = FastAPI(
    title="Hidden Hunger API",
    description="Hyperspectral plant analysis API using NDRE index",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(upload.router)
app.include_router(history.router)

# Serve frontend when available so users can load the website from the same server.
BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
INDEX_FILE = FRONTEND_DIR / "index.html"
if FRONTEND_DIR.exists():
    app.mount("/frontend", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")

OUTPUTS_DIR = BASE_DIR / "outputs"
if OUTPUTS_DIR.exists():
    app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")


@app.exception_handler(AppError)
async def handle_app_error(_: Request, exc: AppError):
    """Return typed application errors in a structured JSON shape."""
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload())


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_: Request, exc: RequestValidationError):
    """Map request validation issues (missing file/fields, bad types) to frontend-friendly payload."""
    app_exc = InvalidUploadError(
        message="Request validation failed.",
        details={"validation_errors": exc.errors()},
    )
    return JSONResponse(status_code=422, content=app_exc.to_payload())


@app.exception_handler(HTTPException)
async def handle_http_exception(_: Request, exc: HTTPException):
    """Wrap generic HTTP errors in structured error payload."""
    detail = exc.detail if isinstance(exc.detail, dict) else {"detail": exc.detail}
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": "HTTP_ERROR",
                "message": "Request failed.",
                "details": detail,
            },
        },
    )


@app.exception_handler(Exception)
async def handle_unexpected_exception(_: Request, exc: Exception):
    """Final safety net to avoid leaking stack traces to frontend clients."""
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Unexpected server error.",
                "details": {"type": type(exc).__name__},
            },
        },
    )


@app.get("/")
def read_root():
    """Root endpoint: serve frontend app if present, else API metadata."""
    if INDEX_FILE.exists():
        return FileResponse(str(INDEX_FILE))
    return {
        "message": "Hidden Hunger API",
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
