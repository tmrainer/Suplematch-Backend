from pathlib import Path
import pandas as pd
import pyarrow.parquet as pq

from app.core.config import settings


def inspect_csv(path: Path) -> dict:
    try:
        df = pd.read_csv(path, nrows=5)
        return {
            "file": path.name,
            "path": str(path),
            "columns": list(df.columns),
            "num_columns": len(df.columns),
            "sample_rows": df.to_dict(orient="records"),
        }
    except Exception as exc:
        return {
            "file": path.name,
            "path": str(path),
            "error": str(exc),
        }


def inspect_parquet(path: Path) -> dict:
    try:
        parquet_file = pq.ParquetFile(path)
        schema = parquet_file.schema_arrow
        return {
            "file": path.name,
            "path": str(path),
            "columns": schema.names,
            "num_columns": len(schema.names),
            "num_rows": parquet_file.metadata.num_rows,
        }
    except Exception as exc:
        return {
            "file": path.name,
            "path": str(path),
            "error": str(exc),
        }


def inspect_data_sources() -> dict:
    csv_dir = Path(settings.RAW_CSV_DIR)
    raw_parquet_dir = Path(settings.RAW_PARQUET_DIR)
    processed_dir = Path(settings.PROCESSED_DATA_DIR)

    report = {
        "csv_dir": str(csv_dir),
        "raw_parquet_dir": str(raw_parquet_dir),
        "processed_data_dir": str(processed_dir),
        "csv_files": [],
        "parquet_files": [],
    }

    if csv_dir.exists():
        for path in csv_dir.glob("*.csv"):
            report["csv_files"].append(inspect_csv(path))

    for directory in [raw_parquet_dir, processed_dir]:
        if directory.exists():
            for path in directory.glob("*.parquet"):
                report["parquet_files"].append(inspect_parquet(path))

    return report
