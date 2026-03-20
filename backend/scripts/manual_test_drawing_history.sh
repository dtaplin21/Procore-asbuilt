#!/bin/bash
# Manual test commands for drawing comparison history endpoints.
# Ensure the server is running (e.g. uvicorn main:app --port 8000) and has test data.
#
# Default: http://localhost:8000
# Override: BASE_URL=http://localhost:2000 ./manual_test_drawing_history.sh

BASE_URL="${BASE_URL:-http://localhost:8000}"

echo "=== 11.1 Test alignments history ==="
echo "GET $BASE_URL/api/projects/1/drawings/10/alignments"
echo ""
curl -s "$BASE_URL/api/projects/1/drawings/10/alignments" | python3 -m json.tool
echo ""
echo "Check: newest alignment first, subDrawing.id and subDrawing.name included"
echo ""

echo "=== 11.2 Test diffs history for all alignments ==="
echo "GET $BASE_URL/api/projects/1/drawings/10/diffs"
echo ""
curl -s "$BASE_URL/api/projects/1/drawings/10/diffs" | python3 -m json.tool
echo ""
echo "Check: newest diff first, includes summary, severity, createdAt, diffRegions"
echo ""

echo "=== 11.3 Test diffs filtered to one alignment ==="
echo "GET $BASE_URL/api/projects/1/drawings/10/diffs?alignment_id=5"
echo ""
curl -s "$BASE_URL/api/projects/1/drawings/10/diffs?alignment_id=5" | python3 -m json.tool
echo ""
echo "Check: only diffs from alignment 5"
