from __future__ import annotations

from pathlib import Path
from runpy import run_path
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]


def ensure_project_root_on_path() -> None:
    root = str(ROOT_DIR)
    if root not in sys.path:
        sys.path.insert(0, root)


def run_script(relative_path: str) -> None:
    ensure_project_root_on_path()
    run_path(str(ROOT_DIR / relative_path), run_name="__main__")
