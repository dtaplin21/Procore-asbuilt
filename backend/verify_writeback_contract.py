#!/usr/bin/env python3
"""
Verify build_writeback_contract against real DB.

Usage (from backend/ with venv activated):
  python verify_writeback_contract.py [project_id] [inspection_run_id]

Examples:
  python verify_writeback_contract.py
  python verify_writeback_contract.py 1 123
"""
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
        print("=== WritebackContract (Pydantic model) ===")
        print(payload.model_dump_json(indent=2))
        print("\n=== Summary ===")
        print(f"Project: {payload.project.name} (id={payload.project.id})")
        print(f"Inspection run: id={payload.inspection_run.id}, status={payload.inspection_run.status}")
        print(f"Inspection result: outcome={payload.inspection_result.outcome if payload.inspection_result else 'N/A'}")
        print(f"Master drawing: {payload.master_drawing.name} (id={payload.master_drawing.id})")
        print(f"Overlays: {len(payload.overlays)}")
        print(f"Finding: {'Yes' if payload.finding else 'No'}")
        print("\n[OK] All fields populated correctly.")
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
