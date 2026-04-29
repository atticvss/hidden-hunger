# Temporal Analysis - Setup Checklist & Troubleshooting

## Pre-Flight Checklist ✅

Before running the server, verify:

- [x] Virtual environment active: `.venv/bin/activate`
- [x] Python imports validated 
- [x] Database initialized with `temporal_analysis` table
- [x] Frontend HTML has temporal UI elements (Sample ID, Plant ID inputs)
- [x] Frontend script has temporal rendering functions
- [x] All thresholds configured in `app/services/temporal.py`

**Status**: All checks passed ✓

---

## Quick Start (3 commands)

### Start Backend
```bash
cd /Users/shubhamsahoo/Desktop/hidden-hunger
source .venv/bin/activate
python -m uvicorn app.main:app --reload
# Or with uvicorn directly:
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Should show:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Application startup complete
```

### Test Uploads (Sequential)

**Upload 1 - First Scan:**
```bash
curl -X POST http://localhost:8000/api/scans/upload \
  -F "file=@test_scan1.npy" \
  -F "sample_id=TestPlant" \
  -F "nir_band=5" \
  -F "red_edge_band=4" \
  -F "stress_threshold=0.2" | jq '.temporal_analysis'
```

Expected response:
```json
{
  "sample_id": "TestPlant",
  "has_baseline": false,
  "baseline_scan_id": null,
  "no_baseline_reason": "First scan for this sample_id/plant_id.",
  "trend_label": "stable",
  "trend_score": 0.0,
  "ndre_mean_delta": null,
  "stress_percentage_delta": null,
  "confidence_delta": null,
  "onset_detected": false,
  "onset_reason": "No baseline scan available.",
  "onset_score": 0.0
}
```

**Upload 2 - Same Sample, Different Scan:**
```bash
curl -X POST http://localhost:8000/api/scans/upload \
  -F "file=@test_scan2.npy" \
  -F "sample_id=TestPlant" \
  -F "nir_band=5" \
  -F "red_edge_band=4" \
  -F "stress_threshold=0.2" | jq '.temporal_analysis'
```

Expected response:
```json
{
  "sample_id": "TestPlant",
  "has_baseline": true,
  "baseline_scan_id": 1,
  "no_baseline_reason": null,
  "trend_label": "improving|stable|worsening",  ← depends on actual data
  "trend_score": -2.5,
  "ndre_mean_delta": 0.025,
  "stress_percentage_delta": -5.0,
  "confidence_delta": 0.08,
  "onset_detected": true|false,
  "onset_reason": "...",
  "onset_score": 0.15
}
```

---

## Common Issues & Fixes

### Issue: Database Lock Error
```
sqlalchemy.exc.OperationalError: database is locked
```
**Cause**: Multiple processes accessing SQLite  
**Fix**: 
1. Kill all Python processes
2. Delete `hidden_hunger.db` (loses data, recreates on startup)
3. Restart server

```bash
pkill -f "python.*uvicorn"
rm hidden_hunger.db
python -m uvicorn app.main:app --reload
```

### Issue: "temporal_analysis table does not exist"
```
sqlalchemy.exc.OperationalError: no such table: temporal_analysis
```
**Cause**: Database initialized before temporal feature added  
**Fix**:
```bash
rm hidden_hunger.db
# Restart server - table auto-created
```

### Issue: Sample ID Not Recognized
**Symptom**: Always shows "First scan for this sample_id"  
**Cause**: Sample ID not sent in upload, or typo in value  
**Fix**:
1. Verify form includes sample_id field:
   ```html
   <input id="sample-id" type="text" placeholder="optional">
   ```
2. Frontend sends it in FormData:
   ```js
   if (sampleIdInput?.value?.trim()) {
     formData.append("sample_id", sampleIdInput.value.trim());
   }
   ```
3. Check database:
   ```bash
   sqlite3 hidden_hunger.db "SELECT scan_id, extra_metadata FROM scan_metadata LIMIT 1"
   ```
   Should show: `{"sample_id": "TestPlant", ...}`

### Issue: Trend Always "Stable"
**Symptom**: Even with very different NDRE/stress values  
**Cause**: Deltas within stable thresholds  
**Fix**: Check thresholds in `app/services/temporal.py`
```python
NDRE_STABLE_EPS = 0.015        # Lower = more sensitive
STRESS_STABLE_EPS = 3.0        # Lower = more sensitive
CONFIDENCE_STABLE_EPS = 0.05   # Lower = more sensitive
```
If NDRE changes only by 0.01, it's "stable" (below 0.015). Lower thresholds to 0.01 for testing.

### Issue: Backend Won't Start
**Error**: `ModuleNotFoundError: No module named 'app'`  
**Fix**:
```bash
cd /Users/shubhamsahoo/Desktop/hidden-hunger
# Make sure you're in project root
pwd  # Should end with /hidden-hunger
python -m uvicorn app.main:app --reload
```

### Issue: Import Error: "No module named 'app.services.temporal'"
**Cause**: File not saved or syntax error  
**Fix**:
```bash
python -m py_compile app/services/temporal.py
# Should produce no output (no errors)
```

---

## Database Inspection

### Check Temporal Records
```bash
sqlite3 hidden_hunger.db

-- Get all temporal analyses
SELECT 
  t.scan_id, 
  t.sample_id, 
  t.trend_label, 
  t.onset_detected
FROM temporal_analysis t;

-- Get baseline relationships
SELECT 
  t.scan_id, 
  t.baseline_scan_id, 
  t.has_baseline, 
  t.ndre_mean_delta, 
  t.stress_percentage_delta
FROM temporal_analysis t;

-- Get scans with their sample IDs
SELECT 
  s.id, 
  s.filename, 
  sm.extra_metadata 
FROM scans s 
LEFT JOIN scan_metadata sm ON s.id = sm.scan_id;
```

### Reset Everything (Destructive)
```bash
rm hidden_hunger.db
# Backend will auto-create on startup
```

---

## Performance Checklist

✓ **Temporal lookup**: O(n) backward scan search - fast for typical histories  
✓ **Memory**: No accumulation, computed on-the-fly per upload  
✓ **Database query**: Single JOIN, indexed on sample_id  

---

## Code Files Summary

| File | Changes | Impact |
|------|---------|--------|
| `app/models.py` | +TemporalAnalysis model | Database table, relationships |
| `app/services/temporal.py` | +200 lines | Threshold logic, trend/onset rules |
| `app/crud.py` | +50 lines | Persistence layer |
| `app/routers/upload.py` | +70 lines | Integration in upload handler |
| `app/schemas.py` | +30 lines | Response validation |
| `frontend/index.html` | +30 lines | UI form fields + display cards |
| `frontend/script.js` | +80 lines | Render functions + history coloring |

---

## Testing Scenarios

### Scenario 1: First Scan Only
- Upload scan with sample_id
- ✓ Temporal shows "no baseline"
- ✓ Onset = false
- ✓ Trend = stable

### Scenario 2: Progressive Improvement
- Upload scan 1 (stress=50%, NDRE=0.3, conf=0.6)
- Upload scan 2 (stress=35%, NDRE=0.35, conf=0.7)
- ✓ Temporal shows "improving"
- ✓ Onset = false
- ✓ Deltas: stress -15%, NDRE +0.05, conf +0.1

### Scenario 3: Rapid Onset
- Upload scan 1 (stress=20%, NDRE=0.5, conf=0.5)
- Upload scan 2 (stress=30%, NDRE=0.42, conf=0.65)
- ✓ Temporal shows "worsening"
- ✓ Onset = true (2+ triggers: stress jump +10%, NDRE drop -0.08, conf jump +0.15)
- ✓ Onset reason lists multiple triggers

### Scenario 4: No Sample ID
- Upload without sample_id field
- ✓ Temporal shows "No sample_id found"
- ✓ No baseline lookup performed
- ✓ Next upload with same plant_id should still work (uses plant_id as fallback)

---

## Monitoring Checklist

**In production, monitor:**

- [ ] Database size growth (new table adds ~500B/scan)
- [ ] Query latency for history endpoint (join complexity)
- [ ] Sample ID consistency (typos break baseline matching)
- [ ] Threshold appropriateness (adjust per crop)

---

## Success Criteria

✅ Backend starts without errors  
✅ Database table created  
✅ Frontend shows temporal inputs  
✅ Two-scan workflow shows baseline comparison  
✅ Trend/onset labels appear in history  
✅ All imports validate  

**Status**: READY FOR PRODUCTION ✓
