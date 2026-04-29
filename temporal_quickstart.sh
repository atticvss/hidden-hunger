#!/bin/bash
# Temporal Analysis Feature - Quick Start & Validation Script
# Usage: bash temporal_quickstart.sh

set -e

echo "═══════════════════════════════════════════════════════════"
echo "Hidden Hunger Temporal Analysis - Quick Start"
echo "═══════════════════════════════════════════════════════════"
echo ""

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Step 1: Verify venv
echo -e "${BLUE}[1/6] Checking virtual environment...${NC}"
if [ ! -d ".venv" ]; then
    echo -e "${RED}✗ Virtual environment not found${NC}"
    echo "Create it first with: python3 -m venv .venv"
    exit 1
fi
source .venv/bin/activate
echo -e "${GREEN}✓ Virtual environment activated${NC}"
echo ""

# Step 2: Check Python imports
echo -e "${BLUE}[2/6] Validating Python imports...${NC}"
./.venv/bin/python -c "
from app.main import app
from app.models import TemporalAnalysis
from app.services import temporal
from app.crud import create_temporal_analysis
print('✓ All imports successful')
" || { echo -e "${RED}✗ Import validation failed${NC}"; exit 1; }
echo -e "${GREEN}✓ Python imports OK${NC}"
echo ""

# Step 3: Initialize database
echo -e "${BLUE}[3/6] Initializing database...${NC}"
./.venv/bin/python << 'EOF'
from app.database import init_db, SessionLocal
from app.models import TemporalAnalysis

init_db()
db = SessionLocal()
try:
    result = db.query(TemporalAnalysis).first()
    print("✓ TemporalAnalysis table created/accessible")
finally:
    db.close()
EOF
echo -e "${GREEN}✓ Database initialized${NC}"
echo ""

# Step 4: Verify temporal constants
echo -e "${BLUE}[4/6] Verifying temporal analysis configuration...${NC}"
./.venv/bin/python << 'EOF'
from app.services import temporal

print("Temporal Analysis Thresholds:")
print(f"  NDRE_STABLE_EPS = {temporal.NDRE_STABLE_EPS}")
print(f"  STRESS_STABLE_EPS = {temporal.STRESS_STABLE_EPS}")
print(f"  CONFIDENCE_STABLE_EPS = {temporal.CONFIDENCE_STABLE_EPS}")
print(f"  ONSET_STRESS_JUMP = {temporal.ONSET_STRESS_JUMP}")
print(f"  ONSET_NDRE_DROP = {temporal.ONSET_NDRE_DROP}")
print(f"  ONSET_CONFIDENCE_RISE = {temporal.ONSET_CONFIDENCE_RISE}")
EOF
echo -e "${GREEN}✓ Configuration validated${NC}"
echo ""

# Step 5: Check frontend assets
echo -e "${BLUE}[5/6] Checking frontend assets...${NC}"
if [ -f "frontend/index.html" ] && [ -f "frontend/script.js" ]; then
    echo -e "${GREEN}✓ Frontend files present${NC}"
    if grep -q "temporal-trend\|sample-id\|plant-id" frontend/index.html; then
        echo -e "${GREEN}✓ Temporal UI elements detected${NC}"
    fi
else
    echo -e "${RED}✗ Frontend files missing${NC}"
    exit 1
fi
echo ""

# Step 6: Summary
echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ ALL CHECKS PASSED${NC}"
echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${BLUE}Next Steps:${NC}"
echo ""
echo "1. Start the backend server:"
echo "   $ make dev"
echo "   OR"
echo "   $ python -m uvicorn app.main:app --reload"
echo ""
echo "2. Open browser at:"
echo "   http://localhost:8000"
echo ""
echo "3. Try the two-scan workflow:"
echo "   a) Upload scan 1 with Sample ID: 'TestPlant'"
echo "   b) Check temporal info (should show 'First scan')"
echo "   c) Upload scan 2 with Sample ID: 'TestPlant'"
echo "   d) Check temporal info (should show trend, deltas, onset)"
echo ""
echo "4. View history to see Trend and Onset columns"
echo ""
echo -e "${YELLOW}Documentation:${NC}"
echo "  See TEMPORAL_ANALYSIS.md for complete guide"
echo ""
