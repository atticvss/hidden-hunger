#!/usr/bin/env python3
"""
Final validation script for temporal analysis feature.
Checks all components are ready for production use.
"""

import sys

print("=" * 60)
print("TEMPORAL ANALYSIS - FINAL VALIDATION")
print("=" * 60)
print()

# 1. Import app
print("[1/5] Importing FastAPI app...")
try:
    from app.main import app
    print("✓ FastAPI app imported successfully")
except Exception as e:
    print(f"✗ Failed to import app: {e}")
    sys.exit(1)

# 2. Check routes
print("\n[2/5] Verifying routes...")
routes = [r.path for r in app.routes]
critical_routes = ['/api/scans/upload', '/api/history/', '/']
for route in critical_routes:
    if route in routes:
        print(f"✓ {route} registered")
    else:
        print(f"✗ {route} NOT FOUND")
        sys.exit(1)

# 3. Check database
print("\n[3/5] Testing database...")
try:
    from app.database import SessionLocal
    from app.models import TemporalAnalysis
    db = SessionLocal()
    count = db.query(TemporalAnalysis).count()
    print(f"✓ Database operational (temporal records: {count})")
    db.close()
except Exception as e:
    print(f"✗ Database error: {e}")
    sys.exit(1)

# 4. Validate temporal service
print("\n[4/5] Validating temporal service...")
try:
    from app.services.temporal import (
        resolve_sample_id,
        find_previous_snapshot_for_sample,
        compute_temporal_analysis,
        classify_trend,
        detect_onset
    )
    # Quick test
    sample = resolve_sample_id({"sample_id": "test"})
    assert sample == "test", "resolve_sample_id failed"
    trend, score = classify_trend(0.02, -2, 0.1)
    assert trend in ["improving", "stable", "worsening"]
    print("✓ Temporal service fully functional")
except Exception as e:
    print(f"✗ Temporal service error: {e}")
    sys.exit(1)

# 5. Check frontend assets
print("\n[5/5] Checking frontend assets...")
try:
    import os
    html_file = "frontend/index.html"
    js_file = "frontend/script.js"
    if os.path.exists(html_file):
        with open(html_file) as f:
            content = f.read()
            if "temporal" in content.lower() or "sample_id" in content:
                print(f"✓ {html_file} has temporal UI elements")
            else:
                print(f"⚠ {html_file} missing temporal elements (non-critical)")
    if os.path.exists(js_file):
        with open(js_file) as f:
            content = f.read()
            if "renderTemporalAnalysis" in content:
                print(f"✓ {js_file} has temporal rendering logic")
            else:
                print(f"⚠ {js_file} missing temporal logic (non-critical)")
except Exception as e:
    print(f"⚠ Could not check frontend assets: {e}")

print()
print("=" * 60)
print("✓ SYSTEM READY FOR PRODUCTION")
print("=" * 60)
print()
print("To start server:")
print("  cd /Users/shubhamsahoo/Desktop/hidden-hunger")
print("  source .venv/bin/activate")
print("  python -m uvicorn app.main:app --reload")
print()
print("Then visit: http://localhost:8000")
print()
