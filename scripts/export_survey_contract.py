from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from app.schemas.survey_contract import survey_contract


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Exporta el contrato de encuesta para el frontend.")
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT_DIR.parent / "frontend-suplematch" / "src" / "contracts" / "surveyContract.json",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(survey_contract(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"survey_contract_exported={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
