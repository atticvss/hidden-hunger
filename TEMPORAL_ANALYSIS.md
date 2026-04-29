# Temporal Analysis Feature Guide

## Overview

The temporal analysis feature tracks scan-to-scan progression for the same plant/sample by comparing against the most recent previous scan. It detects trends (improving/stable/worsening) and flags early stress onset.

## Key Features

### 1. Trend Classification
- **improving**: NDRE increases, stress decreases, confidence rises → plant recovering
- **stable**: Changes within small thresholds → no significant shift
- **worsening**: NDRE drops, stress increases, confidence rises toward disease → degradation

### 2. Onset Detection
Triggers when **2 or more** conditions are met:
- Stress percentage jumped ≥5%
- NDRE mean dropped ≤−0.02
- Prediction confidence increased ≥0.08 (shift toward current stress class)

Each trigger is logged in `onset_reason` string.

### 3. Sample/Plant Matching
Temporal analysis requires a **sample ID** to match scans. Configure this via:
- **Frontend**: Enter "Sample ID" or "Plant ID" in upload form (optional fields)
- **Database**: Values stored in `scan_metadata.extra_metadata` JSON
- **Fallback**: If neither field provided, no baseline available (first scan recorded)

---

## Quick Start

### 1. Upload First Scan for a Sample

1. Open browser → `http://localhost:8000`
2. Upload an NPY file
3. Enter **Sample ID** (e.g., "Plant-A" or "Row-3-Col-5")
4. Click **Process Image**
5. Check "Onset" section (should show "Not detected" + "First scan for this sample")

### 2. Upload Second Scan for Same Sample

1. Upload another NPY file (same plant, few days later)
2. Enter **same Sample ID** ("Plant-A")
3. Click **Process Image**
4. Temporal analysis now shows:
   - **Trend**: improving/stable/worsening
   - **NDRE Change**: ±delta value
   - **Stress Change**: ±delta percentage
   - **Onset**: Detected/Not detected + reason
   - **Temporal Notes**: Sample ID + reason + score

### 3. View History with Trends

1. Scroll to "Previous Analyses" table
2. New columns: **Trend** and **Onset**
3. Color coding:
   - Trend "improving" = green
   - Trend "worsening" = red
   - Trend "stable" = gray
   - Onset "Yes" = red, "No" = green

---

## Database Schema

### New Table: `temporal_analysis`

```sql
CREATE TABLE temporal_analysis (
  id INTEGER PRIMARY KEY,
  scan_id INTEGER UNIQUE NOT NULL,          -- FK to scans(id)
  sample_id VARCHAR,                         -- Plant/sample identifier
  baseline_scan_id INTEGER,                  -- FK to scans(id) for prior scan
  has_baseline BOOLEAN DEFAULT FALSE,
  no_baseline_reason VARCHAR,                -- Why no baseline found
  trend_label VARCHAR,                       -- improving|stable|worsening
  trend_score FLOAT,                         -- Numeric trend score
  ndre_mean_delta FLOAT,                     -- Current NDRE - baseline NDRE
  stress_percentage_delta FLOAT,             -- Current stress% - baseline stress%
  confidence_delta FLOAT,                    -- Current conf - baseline conf
  onset_detected BOOLEAN DEFAULT FALSE,
  onset_reason VARCHAR,                      -- Reasons separated by `;`
  onset_score FLOAT,                         -- 0.0-1.0 onset likelihood
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_temporal_sample_id ON temporal_analysis(sample_id);
```

**Database is auto-created** on first app startup via SQLAlchemy.

---

## Configuration & Tuning

All thresholds are in [app/services/temporal.py](app/services/temporal.py), top 10 lines:

```python
NDRE_STABLE_EPS = 0.015          # NDRE change below this = stable
STRESS_STABLE_EPS = 3.0          # Stress % change below this = stable
CONFIDENCE_STABLE_EPS = 0.05     # Confidence change below this = stable

ONSET_STRESS_JUMP = 5.0          # Stress % increase to trigger onset
ONSET_NDRE_DROP = -0.02          # NDRE decrease to trigger onset
ONSET_CONFIDENCE_RISE = 0.08     # Confidence increase to trigger onset
```

### Example: Make Onset More Sensitive

To detect stress earlier, lower thresholds:
```python
ONSET_STRESS_JUMP = 3.0          # Lower = more sensitive
ONSET_NDRE_DROP = -0.015         # Less negative = more sensitive
ONSET_CONFIDENCE_RISE = 0.06     # Lower = more sensitive
```

Then restart backend. No database changes needed.

---

## API Endpoints

### Upload Response (POST `/api/scans/upload`)

Request form fields (multipart/form-data):
```
file: <NPY file>
nir_band: 5 (optional)
red_edge_band: 4 (optional)
stress_threshold: 0.2 (optional)
sample_id: "Plant-A" (optional)
plant_id: "Row-3-Col-5" (optional)
```

Response includes:
```json
{
  "scan_id": 1,
  "temporal_analysis": {
    "sample_id": "Plant-A",
    "has_baseline": true,
    "baseline_scan_id": 1,
    "trend_label": "improving",
    "trend_score": 2.5,
    "ndre_mean_delta": 0.045,
    "stress_percentage_delta": -8.3,
    "confidence_delta": 0.12,
    "onset_detected": false,
    "onset_reason": "No early stress progression detected.",
    "onset_score": 0.15
  }
}
```

### History List (GET `/api/history/`)

Response items now include:
```json
{
  "scan_id": 2,
  "file_name": "scan2.npy",
  "trend_label": "improving",
  "ndre_mean_delta": 0.045,
  "stress_percentage_delta": -8.3,
  "confidence_delta": 0.12,
  "onset_detected": false,
  "onset_reason": "No early stress progression detected.",
  "sample_id": "Plant-A"
}
```

---

## Error Handling

### Missing Sample ID
- **Result**: `has_baseline = false`, `no_baseline_reason = "No sample_id/plant_id found in metadata."`
- **Action**: Trend defaults to "stable", onset defaults to false
- **Fix**: Add sample_id in next upload

### First Scan for Sample
- **Result**: `has_baseline = false`, `no_baseline_reason = "First scan for this sample_id/plant_id."`
- **Action**: Temporal analysis shows baseline info, no deltas
- **Fix**: Upload more scans for same sample to enable comparison

### Baseline Scan Missing Data
- **Result**: Skipped during baseline search, tries earlier scans
- **Impact**: Minimal—algorithm looks backward until finding complete data

### Database Insert Fails
- **Result**: Upload succeeds, but temporal record missing
- **Indicator**: Check response—if `temporal_analysis` field is absent, DB error occurred
- **Log**: Check backend console for `DatabaseWriteError: create_temporal_analysis`

---

## Troubleshooting

### Temporal Analysis Not Showing Up
1. Check browser DevTools → Network → see if response includes `temporal_analysis` field
2. If missing, check backend logs: `DatabaseWriteError: create_temporal_analysis`
3. Ensure database tables exist: `sqlite3 hidden_hunger.db ".tables"` should list `temporal_analysis`

### Baseline Never Found
1. Verify sample_id is consistent across uploads (case-sensitive)
2. Check `scan_metadata.extra_metadata` in database has sample_id key:
   ```sql
   SELECT extra_metadata FROM scan_metadata WHERE scan_id = 1;
   ```
3. If empty JSON `{}`, sample_id was not sent in upload form

### Trend Not Changing Between Scans
1. Check if deltas are within stable thresholds:
   - NDRE Δ < 0.015 → stable
   - Stress Δ < 3.0% → stable
   - Confidence Δ < 0.05 → stable
2. To see actual values, check response `ndre_mean_delta`, `stress_percentage_delta`

### Onset Triggered Unexpectedly
1. Check `onset_reason` field—lists which conditions triggered
2. Adjust thresholds in [app/services/temporal.py](app/services/temporal.py)
3. Restart backend after changes

---

## Database Migration (Optional, for Alembic)

If you use Alembic:

```bash
alembic revision --autogenerate -m "Add temporal analysis table"
alembic upgrade head
```

Otherwise, table is auto-created by SQLAlchemy on startup.

---

## Testing

### Manual Test: Two-Scan Workflow

```bash
# Terminal 1: Start backend
cd /Users/shubhamsahoo/Desktop/hidden-hunger
source .venv/bin/activate
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

```bash
# Terminal 2: Upload first scan
curl -X POST http://localhost:8000/api/scans/upload \
  -F "file=@test_scan1.npy" \
  -F "sample_id=TestPlant" \
  -F "nir_band=5" \
  -F "red_edge_band=4" \
  -F "stress_threshold=0.2" \
  | jq '.temporal_analysis'
```

Should show:
```json
{
  "sample_id": "TestPlant",
  "has_baseline": false,
  "no_baseline_reason": "First scan for this sample_id/plant_id."
}
```

```bash
# Terminal 2: Upload second scan (same sample)
curl -X POST http://localhost:8000/api/scans/upload \
  -F "file=@test_scan2.npy" \
  -F "sample_id=TestPlant" \
  -F "nir_band=5" \
  -F "red_edge_band=4" \
  -F "stress_threshold=0.2" \
  | jq '.temporal_analysis'
```

Should show:
```json
{
  "sample_id": "TestPlant",
  "has_baseline": true,
  "baseline_scan_id": 1,
  "trend_label": "improving|stable|worsening",
  "ndre_mean_delta": ...,
  "stress_percentage_delta": ...,
  "confidence_delta": ...,
  "onset_detected": true|false,
  "onset_reason": "..."
}
```

---

## Code Structure Reference

| File | Purpose |
|------|---------|
| [app/models.py](app/models.py) | TemporalAnalysis SQLAlchemy model |
| [app/services/temporal.py](app/services/temporal.py) | Threshold logic, trend/onset rules |
| [app/crud.py](app/crud.py) | CRUD: create/get temporal records |
| [app/routers/upload.py](app/routers/upload.py) | Integration in upload endpoint |
| [app/schemas.py](app/schemas.py) | TemporalAnalysisResponse Pydantic schema |
| [frontend/index.html](frontend/index.html) | Sample ID/Plant ID form inputs, temporal display cards |
| [frontend/script.js](frontend/script.js) | Render temporal fields, history table coloring |

---

## Support & FAQ

**Q: Can I use plant_id instead of sample_id?**
A: Yes. Either field works. Resolved in priority order: `sample_id` → `plant_id`.

**Q: What if I upload the same file twice?**
A: Two separate scan records created (different timestamps). Temporal comparison works as normal.

**Q: Can I manually set a trend?**
A: No. Trends are computed from deltas. Modify thresholds if needed.

**Q: What happens to temporal data if I delete a scan?**
A: Cascade delete removes temporal record. If that scan was a baseline, future scan won't find it.

**Q: Can I export temporal analysis?**
A: Not yet. Data is in `temporal_analysis` table—query directly or enhance `/api/history/` endpoint.

---

## Summary

✅ **Foolproof Setup Checklist**
- [x] Database auto-created on first run
- [x] Frontend form accepts sample_id/plant_id
- [x] Upload response includes temporal_analysis
- [x] History table shows trend/onset columns
- [x] Thresholds centralized and documented
- [x] Error handling for missing baseline
- [x] Color-coded UI indicators
- [x] Comprehensive API documentation

Next: Run backend, upload two scans with same sample_id, verify temporal analysis in UI.
