"""Analysis history endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.deps import get_db
from app.schemas import ScanDetailResponse, ScanListResponse, HistoryListResponse
from app.crud import get_scan, get_scans, count_scans, delete_scan, get_scan_history

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/", response_model=HistoryListResponse)
def list_history(db: Session = Depends(get_db)):
    """Get previous uploaded hyperspectral analyses ordered by newest first."""
    items = get_scan_history(db)
    return HistoryListResponse(items=items)


@router.get("", response_model=ScanListResponse)
def list_scans(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    """
    Get list of all scans.
    
    - **skip**: Number of records to skip (for pagination)
    - **limit**: Maximum number of records to return
    """
    total = count_scans(db)
    scans = get_scans(db, skip=skip, limit=limit)
    return ScanListResponse(total=total, scans=scans)


@router.get("/{scan_id}", response_model=ScanDetailResponse)
def get_scan_detail(
    scan_id: int,
    db: Session = Depends(get_db),
):
    """Get complete details of a specific scan with all related data."""
    scan = get_scan(db, scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return scan


@router.delete("/{scan_id}")
def delete_scan_record(
    scan_id: int,
    db: Session = Depends(get_db),
):
    """Delete a scan record and all associated data."""
    if not delete_scan(db, scan_id):
        raise HTTPException(status_code=404, detail="Scan not found")
    return {"detail": "Scan deleted successfully"}
