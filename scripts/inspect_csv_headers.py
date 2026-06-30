from __future__ import annotations

import csv
from pathlib import Path
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("Uso: python3 scripts/inspect_csv_headers.py archivo.csv [archivo2.csv ...]")
        return 2

    for raw_path in sys.argv[1:]:
        path = Path(raw_path)
        if not path.exists():
            print(f"{path}: no existe")
            continue

        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.reader(handle)
            headers = next(reader, [])

        print(f"{path}:")
        for index, header in enumerate(headers, start=1):
            print(f"  {index}. {header}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
