#!/usr/bin/env python3
"""
Test the compare drawings API endpoint.
Run from backend/: python scripts/test_compare_api.py

Requires: backend server running on port 8000 or 2000.
"""
import json
import sys

try:
    import httpx
except ImportError:
    print("Install httpx: pip install httpx")
    sys.exit(1)

BASE = "http://localhost:8000"
ALT_BASE = "http://localhost:2000"


def test_compare(project_id: int = 1, master_id: int = 10, sub_id: int = 20):
    url = f"{BASE}/api/projects/{project_id}/drawings/{master_id}/compare"
    try:
        r = httpx.post(
            url,
            json={"subDrawingId": sub_id},
            timeout=30.0,
        )
    except httpx.ConnectError:
        url = f"{ALT_BASE}/api/projects/{project_id}/drawings/{master_id}/compare"
        try:
            r = httpx.post(
                url,
                json={"subDrawingId": sub_id},
                timeout=30.0,
            )
        except httpx.ConnectError:
            print("Could not connect. Start server: cd backend && uvicorn main:app --port 8000")
            sys.exit(1)

    print(f"Status: {r.status_code}")
    data = r.json()
    print(json.dumps(data, indent=2))
    return data


if __name__ == "__main__":
    project_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    master_id = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    sub_id = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    test_compare(project_id, master_id, sub_id)
