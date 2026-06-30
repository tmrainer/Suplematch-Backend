from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser(description="Convierte CSVs a parquet para uso local.")
    parser.add_argument("inputs", nargs="+", help="CSV de entrada.")
    parser.add_argument("--out-dir", default="data/raw/parquet", help="Directorio de salida.")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for raw_input in args.inputs:
        input_path = Path(raw_input)
        if not input_path.exists():
            raise FileNotFoundError(input_path)

        output_path = out_dir / f"{input_path.stem}.parquet"
        pd.read_csv(input_path).to_parquet(output_path, index=False)
        print(f"{input_path} -> {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
