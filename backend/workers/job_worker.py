"""
Job queue worker CLI.

Run from the ``backend`` directory::

    python -m workers.job_worker

Delegates to :mod:`services.job_worker` (dispatch includes ``drawing_render``).
"""

from __future__ import annotations

from services.job_worker import main

if __name__ == "__main__":
    main()
