from __future__ import annotations

import os
import sys

# Ensure backend/ is on the import path when running this script directly.
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from database import init_db  # noqa: E402


def main() -> None:
    init_db()
    print("Database initialized (tables created).")


if __name__ == "__main__":
    main()


