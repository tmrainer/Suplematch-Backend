from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _compat import run_script


run_script("scripts/catalog/parser_composicion.py")
