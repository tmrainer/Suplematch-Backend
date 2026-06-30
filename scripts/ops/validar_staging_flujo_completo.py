from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


API_BASE_URL = os.environ.get("API_BASE_URL", "https://suplematch.lmdemo.com").rstrip("/")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
TIMEOUT_SECONDS = int(os.environ.get("TIMEOUT_SECONDS", "20"))
USER_AGENT = os.environ.get("USER_AGENT", "SupleMatchStagingSmoke/1.0")


def load_root_staging_env() -> dict[str, str]:
    root_env = Path(__file__).resolve().parents[3] / ".env.staging"
    if not root_env.exists():
        return {}
    values: dict[str, str] = {}
    for line in root_env.read_text(errors="ignore").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def fail(message: str) -> None:
    raise SystemExit(f"staging_full_flow=failed reason={message}")


def request_json(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    token: str | None = None,
) -> Any:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(
        f"{API_BASE_URL}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
            if not body:
                return {}
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")[:500]
        fail(f"http_{exc.code}_{path}_{body}")
    except Exception as exc:  # noqa: BLE001 - smoke output should be concise.
        fail(f"request_error_{path}_{type(exc).__name__}")


def main() -> None:
    env_file_values = load_root_staging_env()
    admin_email = ADMIN_EMAIL or env_file_values.get("ADMIN_EMAIL", "")
    admin_password = ADMIN_PASSWORD or env_file_values.get("ADMIN_PASSWORD", "")

    if not admin_email or not admin_password:
        fail("missing_admin_credentials")

    print("== health ==")
    health = request_json("GET", "/api/v1/health")
    if health.get("status") != "ok":
        fail("health_not_ok")

    ready = request_json("GET", "/api/v1/health/ready")
    if ready.get("status") not in {"ready", "degraded"}:
        fail("ready_bad_status")
    checks = ready.get("checks", {})
    for key in ("db", "alembic_head", "models"):
        if checks.get(key) is not True:
            fail(f"ready_check_false_{key}")
    if int(checks.get("catalog_products") or 0) <= 0:
        fail("catalog_empty")

    print("== admin login/catalog ==")
    admin_login = request_json(
        "POST",
        "/api/v1/auth/login",
        {"email": admin_email, "password": admin_password},
    )
    admin_token = admin_login.get("access_token")
    if not admin_token:
        fail("admin_token_missing")

    quality = request_json("GET", "/api/v1/admin/catalog/quality", token=admin_token)
    if "traceability_rate" not in quality:
        fail("catalog_quality_missing_traceability")

    products = request_json("GET", "/api/v1/admin/products?limit=1", token=admin_token)
    if not isinstance(products, list) or not products:
        fail("admin_products_empty")
    product_id = products[0].get("id")
    if not product_id:
        fail("admin_product_id_missing")

    print("== register user ==")
    stamp = int(time.time())
    user_email = f"smoke-{stamp}@suplematch.test"
    user_password = "UserSmoke12345"
    user_register = request_json(
        "POST",
        "/api/v1/auth/register",
        {
            "email": user_email,
            "password": user_password,
            "first_name": "Smoke",
            "last_name": "Staging",
            "age": 34,
            "weight_value": 68,
            "weight_unit": "kg",
        },
    )
    user_token = user_register.get("access_token")
    if not user_token:
        fail("user_token_missing")

    print("== recommendation ==")
    recommendation = request_json(
        "POST",
        "/api/v1/recommend",
        {
            "edad_rango": "31_50",
            "sexo": "masculino",
            "tipo_dieta": "omnivoro",
            "horas_sueno": "5_7h",
            "frecuencia_ejercicio": "1_2_semana",
            "dieta": "regular",
            "fatiga": "a_menudo",
            "exposicion_solar": "menos_15min",
            "frecuencia_enfermedad": "1_2_anio",
            "estres": "moderado",
            "alcohol": "ocasional",
            "toma_suplementos": "no",
            "restricciones": ["sin_restricciones"],
            "condiciones_seguridad": ["ninguna"],
            "objetivos": ["energia", "salud_osea"],
        },
        token=user_token,
    )
    recommendation_id = recommendation.get("recommendation_id")
    if not recommendation_id:
        fail("recommendation_id_missing")
    packs = recommendation.get("packs_ranked") or []
    if not packs:
        fail("recommendation_packs_empty")
    pack_id = packs[0].get("pack_id") or "pack_smoke"

    print("== feedback/review ==")
    request_json(
        "POST",
        "/api/v1/feedback",
        {
            "recommendation_id": recommendation_id,
            "pack_id": pack_id,
            "component_ids": ["COMP_94DFE28A9A5C"],
            "selected_product_ids": [product_id],
            "chosen_product_id": product_id,
            "rating": 5,
            "conditions": ["DEFICIT_VIT_D"],
            "product_context": {
                "selected_products": [
                    {"product_id": product_id, "commercial_score": 0.9}
                ]
            },
        },
        token=user_token,
    )
    request_json(
        "POST",
        "/api/v1/reviews/supplements",
        {
            "product_id": product_id,
            "rating": 5,
            "effectiveness_score": 4,
            "side_effects_score": 5,
            "price_value_score": 4,
            "comment": "Review smoke controlada para validar staging.",
        },
        token=user_token,
    )

    print("== labs text ==")
    labs = request_json(
        "POST",
        "/api/v1/labs/text",
        {
            "consent_health_data": True,
            "persist": True,
            "source_type": "text",
            "raw_text": (
                "Hemoglobina 11.8 g/dL 12.0 - 16.0\n"
                "Ferritina 14 ng/mL 13 - 150\n"
                "Vitamina D 25-OH 18.3 ng/mL 30 - 100\n"
                "Glucosa 95 mg/dL 70 - 100\n"
                "TSH 0.32 mUI/L 0.4 - 4.0"
            ),
        },
        token=user_token,
    )
    if "biomarkers" not in labs:
        fail("labs_missing_biomarkers")

    print("== ops ==")
    ops = request_json("GET", "/api/v1/health/ops", token=admin_token)
    if "checks" not in ops:
        fail("ops_missing_checks")

    print("staging_full_flow=ok")


if __name__ == "__main__":
    main()
