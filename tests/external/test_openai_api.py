from __future__ import annotations

import os
from collections.abc import Iterator

import httpx
import pytest


RUN_OPENAI_TESTS = os.getenv("RUN_OPENAI_INTEGRATION_TESTS") == "1"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_TEST_MODEL = os.getenv("OPENAI_TEST_MODEL")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")


pytestmark = pytest.mark.skipif(
    not RUN_OPENAI_TESTS or not OPENAI_API_KEY or not OPENAI_TEST_MODEL,
    reason=(
        "OpenAI external tests require RUN_OPENAI_INTEGRATION_TESTS=1, "
        "OPENAI_API_KEY and OPENAI_TEST_MODEL."
    ),
)


def _extract_text(value) -> Iterator[str]:
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, list):
        for item in value:
            yield from _extract_text(item)
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _extract_text(item)


def _responses_api(input_text: str, *, max_output_tokens: int = 120) -> dict:
    response = httpx.post(
        f"{OPENAI_BASE_URL}/responses",
        headers={
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENAI_TEST_MODEL,
            "input": input_text,
            "max_output_tokens": max_output_tokens,
        },
        timeout=45,
    )
    response.raise_for_status()
    return response.json()


def test_openai_responses_api_smoke():
    body = _responses_api("Return exactly this phrase: suplematch-openai-smoke", max_output_tokens=40)

    text = "\n".join(_extract_text(body)).lower()

    assert body.get("id")
    assert "suplematch-openai-smoke" in text


def test_openai_can_normalize_lab_biomarker_text_for_suplematch():
    body = _responses_api(
        "\n".join(
            [
                "You are validating a lab OCR parser for a supplement recommendation prototype.",
                "Return only compact JSON, no markdown.",
                "Normalize this text:",
                "Vit D 25 OH: 12 ng/mL ref 20 - 100",
                "Creatinina serica: 2.4 mg/dL ref 0.7 - 1.3",
                "Required JSON keys: vitamin_d_ng_ml, creatinine_mg_dl, safety.",
                "Use safety value medical_review_required.",
            ]
        ),
        max_output_tokens=120,
    )

    text = "\n".join(_extract_text(body)).lower()

    assert "vitamin_d_ng_ml" in text
    assert "creatinine_mg_dl" in text
    assert "medical_review_required" in text
