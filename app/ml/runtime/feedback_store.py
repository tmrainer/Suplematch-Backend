from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any

from app.core.config import settings


RUNTIME_DIR = Path(__file__).resolve().parent

RECOMMENDATION_EVENTS_PATH = RUNTIME_DIR / "recommendation_events.json"
USER_FEEDBACK_EVENTS_PATH = RUNTIME_DIR / "user_feedback_events.json"
FEEDBACK_DB_PATH = settings.FEEDBACK_DB_PATH


def _ensure_files() -> None:
    for path in [RECOMMENDATION_EVENTS_PATH, USER_FEEDBACK_EVENTS_PATH]:
        if not path.exists() or path.stat().st_size == 0:
            path.write_text("[]\n", encoding="utf-8")


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    _ensure_files()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = []

    return data if isinstance(data, list) else []


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_loads(value: str | None, default: Any) -> Any:
    if value is None:
        return default

    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return default

    return data


def _connect() -> sqlite3.Connection:
    Path(FEEDBACK_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(FEEDBACK_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    _ensure_db(conn)
    _migrate_json_events(conn)
    return conn


def _ensure_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS recommendation_events (
            recommendation_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            conditions_json TEXT NOT NULL,
            packs_ranked_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS feedback_events (
            feedback_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            recommendation_id TEXT NOT NULL,
            pack_id TEXT,
            component_ids_json TEXT NOT NULL,
            rating_overall REAL,
            conditions_context_json TEXT NOT NULL,
            comment TEXT,
            extra_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_feedback_events_pack_id ON feedback_events(pack_id)"
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_feedback_events_recommendation_id
        ON feedback_events(recommendation_id)
        """
    )
    conn.commit()


def _migrate_json_events(conn: sqlite3.Connection) -> None:
    for event in _read_json_list(RECOMMENDATION_EVENTS_PATH):
        recommendation_id = event.get("recommendation_id")
        if not recommendation_id:
            continue

        conn.execute(
            """
            INSERT OR IGNORE INTO recommendation_events (
                recommendation_id,
                timestamp,
                conditions_json,
                packs_ranked_json
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                recommendation_id,
                event.get("timestamp") or _now_iso(),
                _json_dumps(event.get("conditions") or []),
                _json_dumps(event.get("packs_ranked") or []),
            ),
        )

    for event in _read_json_list(USER_FEEDBACK_EVENTS_PATH):
        feedback_id = event.get("feedback_id")
        if not feedback_id:
            continue

        final_rating = event.get("rating_overall", event.get("rating"))
        conn.execute(
            """
            INSERT OR IGNORE INTO feedback_events (
                feedback_id,
                timestamp,
                recommendation_id,
                pack_id,
                component_ids_json,
                rating_overall,
                conditions_context_json,
                comment,
                extra_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feedback_id,
                event.get("timestamp") or _now_iso(),
                event.get("recommendation_id") or "",
                event.get("pack_id"),
                _json_dumps(event.get("component_ids") or []),
                final_rating,
                _json_dumps(event.get("conditions_context") or []),
                event.get("comment"),
                _json_dumps(event.get("extra") or {}),
            ),
        )

    conn.commit()


def _rating_to_score(rating: int | float | None) -> float | None:
    if rating is None:
        return None

    try:
        value = float(rating)
    except (TypeError, ValueError):
        return None

    value = max(1.0, min(5.0, value))
    return (value - 1.0) / 4.0


def _pack_key(component_ids: list[str]) -> str:
    clean = sorted(str(cid) for cid in component_ids if cid)
    raw = "|".join(clean)
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]
    return f"pack_{digest}"


def save_recommendation_event(
    conditions: list[str],
    packs_ranked: list[dict[str, Any]],
) -> str:
    recommendation_id = f"rec_{uuid4().hex}"

    event = {
        "recommendation_id": recommendation_id,
        "timestamp": _now_iso(),
        "conditions": conditions,
        "packs_ranked": packs_ranked,
    }

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO recommendation_events (
                recommendation_id,
                timestamp,
                conditions_json,
                packs_ranked_json
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                event["recommendation_id"],
                event["timestamp"],
                _json_dumps(event["conditions"]),
                _json_dumps(event["packs_ranked"]),
            ),
        )

    return recommendation_id


def save_feedback_event(
    recommendation_id: str,
    pack_id: str | None = None,
    component_ids: list[str] | None = None,
    rating_overall: int | float | None = None,
    rating: int | float | None = None,
    conditions_context: list[str] | None = None,
    comment: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    feedback_id = f"fb_{uuid4().hex}"

    final_rating = rating_overall if rating_overall is not None else rating

    event = {
        "feedback_id": feedback_id,
        "timestamp": _now_iso(),
        "recommendation_id": recommendation_id,
        "pack_id": pack_id,
        "component_ids": component_ids or [],
        "rating_overall": final_rating,
        "conditions_context": conditions_context or [],
        "comment": comment,
        "extra": extra or {},
    }

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO feedback_events (
                feedback_id,
                timestamp,
                recommendation_id,
                pack_id,
                component_ids_json,
                rating_overall,
                conditions_context_json,
                comment,
                extra_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["feedback_id"],
                event["timestamp"],
                event["recommendation_id"],
                event["pack_id"],
                _json_dumps(event["component_ids"]),
                event["rating_overall"],
                _json_dumps(event["conditions_context"]),
                event["comment"],
                _json_dumps(event["extra"]),
            ),
        )

    return feedback_id


def load_recommendation_events() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT recommendation_id, timestamp, conditions_json, packs_ranked_json
            FROM recommendation_events
            ORDER BY timestamp ASC
            """
        ).fetchall()

    return [
        {
            "recommendation_id": row["recommendation_id"],
            "timestamp": row["timestamp"],
            "conditions": _json_loads(row["conditions_json"], []),
            "packs_ranked": _json_loads(row["packs_ranked_json"], []),
        }
        for row in rows
    ]


def load_feedback_events() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                feedback_id,
                timestamp,
                recommendation_id,
                pack_id,
                component_ids_json,
                rating_overall,
                conditions_context_json,
                comment,
                extra_json
            FROM feedback_events
            ORDER BY timestamp ASC
            """
        ).fetchall()

    return [
        {
            "feedback_id": row["feedback_id"],
            "timestamp": row["timestamp"],
            "recommendation_id": row["recommendation_id"],
            "pack_id": row["pack_id"],
            "component_ids": _json_loads(row["component_ids_json"], []),
            "rating_overall": row["rating_overall"],
            "conditions_context": _json_loads(row["conditions_context_json"], []),
            "comment": row["comment"],
            "extra": _json_loads(row["extra_json"], {}),
        }
        for row in rows
    ]


def get_feedback_stats_by_pack() -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}

    for event in load_feedback_events():
        component_ids = [str(cid) for cid in event.get("component_ids") or [] if cid]
        pack_id = event.get("pack_id")

        if not pack_id and not component_ids:
            continue

        pack_id = pack_id or _pack_key(component_ids)
        score = _rating_to_score(event.get("rating_overall", event.get("rating")))

        if score is None:
            continue

        if pack_id not in stats:
            stats[pack_id] = {
                "n": 0.0,
                "sum": 0.0,
                "component_ids": component_ids,
                "last_feedback_at": event.get("timestamp"),
            }

        stats[pack_id]["n"] += 1.0
        stats[pack_id]["sum"] += score

        if component_ids and not stats[pack_id]["component_ids"]:
            stats[pack_id]["component_ids"] = component_ids

        timestamp = event.get("timestamp")
        if timestamp and (
            not stats[pack_id]["last_feedback_at"]
            or str(timestamp) > str(stats[pack_id]["last_feedback_at"])
        ):
            stats[pack_id]["last_feedback_at"] = timestamp

    for item in stats.values():
        n = max(float(item["n"]), 1.0)
        avg_score = float(item["sum"]) / n
        item["avg_score"] = avg_score
        item["avg_rating"] = 1.0 + (4.0 * avg_score)

    return stats


def get_feedback_summary(limit: int = 5) -> dict[str, Any]:
    events = load_feedback_events()
    stats = get_feedback_stats_by_pack()

    ranked = sorted(
        stats.items(),
        key=lambda item: (item[1].get("avg_score", 0.0), item[1].get("n", 0.0)),
        reverse=True,
    )

    top_rated_packs = []
    for pack_id, item in ranked[:limit]:
        top_rated_packs.append({
            "pack_id": pack_id,
            "feedback_count": int(item["n"]),
            "avg_rating": round(float(item["avg_rating"]), 2),
            "avg_score": round(float(item["avg_score"]), 4),
            "component_ids": item.get("component_ids", []),
            "last_feedback_at": item.get("last_feedback_at"),
        })

    return {
        "total_feedback_events": len(events),
        "packs_with_feedback": len(stats),
        "top_rated_packs": top_rated_packs,
    }


def get_recommendation_events() -> list[dict[str, Any]]:
    return load_recommendation_events()


def get_feedback_events() -> list[dict[str, Any]]:
    return load_feedback_events()
