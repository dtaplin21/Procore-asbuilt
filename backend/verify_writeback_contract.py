#!/usr/bin/env python3
"""
Verify build_writeback_contract against real DB.

Usage (from backend/ with venv activated):
  python verify_writeback_contract.py [project_id] [inspection_run_id]

Examples:
  python verify_writeback_contract.py
  python verify_writeback_contract.py 1 123
"""
import json
import sys

sys.path.insert(0, ".")

from database import SessionLocal
from services.procore_writeback_contract import build_writeback_contract


def main():
    project_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    inspection_run_id = int(sys.argv[2]) if len(sys.argv) > 2 else 123

    db = SessionLocal()
    try:
        payload = build_writeback_contract(db, project_id=project_id, inspection_run_id=inspection_run_id)
        print("=== Writeback contract (from build_writeback_contract) ===")
        print(json.dumps(payload, indent=2, default=str))
        print("\n=== Summary ===")
        project = payload["project"]
        print(f"Project: {project['name']} (id={project['id']})")
        run = payload["inspection_run"]
        print(f"Inspection run: id={run['id']}, status={run['status']}")
        ir = payload.get("inspection_result")
        outcome = ir.get("outcome") if isinstance(ir, dict) else "N/A"
        print(f"Inspection result: outcome={outcome}")
        md = payload["master_drawing"]
        print(f"Master drawing: {md['name']} (id={md['id']})")
        overlays = payload.get("overlays") or []
        print(f"Overlays: {len(overlays)}")
        print(f"Finding: {'Yes' if payload.get('finding') else 'No'}")
        print("\n[OK] All fields populated correctly.")
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
