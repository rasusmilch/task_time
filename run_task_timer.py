"""Root launcher for Task Timer development and packaging."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
SRC_DIR = REPO_ROOT / "src"

if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))

from task_timer.main import main


if __name__ == "__main__":
    main()
