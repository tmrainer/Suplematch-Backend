"""Sin `__init__.py`, pytest importa cada test por su nombre de archivo: dos con el mismo nombre en carpetas distintas
no pueden correr en la misma sesion ("import file mismatch")."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parents[1]


def test_test_file_names_are_unique_across_folders() -> None:
    by_name: dict[str, list[str]] = defaultdict(list)
    for path in TESTS_DIR.rglob("test_*.py"):
        by_name[path.name].append(str(path.relative_to(TESTS_DIR)))
    duplicates = {name: paths for name, paths in by_name.items() if len(paths) > 1}
    assert not duplicates, f"renombrar uno de cada par: {duplicates}"
