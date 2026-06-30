from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_URL = "https://www.digemid.minsa.gob.pe/rsProductosFarmaceuticos/"
DEFAULT_OUT = ROOT_DIR / "data/reports/digemid/digemid_visual_candidates.csv"
DEFAULT_REPORT = ROOT_DIR / "data/reports/digemid/digemid_visual_scrape_report.json"
DEFAULT_EVIDENCE_DIR = ROOT_DIR / "data/reports/digemid/visual_html"

OUTPUT_COLUMNS = [
    "item",
    "Distribuidor",
    "Producto",
    "Fabricante",
    "composicion_por",
    "Forma Farmacéutica",
    "Procedencia",
    "Liberación",
    "Composición",
    "Vías de Administración",
    "Presentación",
    "codigo_atc",
    "descripcion_clasificacion",
    "grupo_atc_3",
    "grupo_atc_4",
    "source_query",
    "source_url",
    "scraped_at",
    "extraction_status",
]

HEADER_ALIASES = {
    "item": {"item", "rs", "registro sanitario", "registro_sanitario", "nro registro", "n registro sanitario"},
    "Distribuidor": {"distribuidor", "titular", "solicitante", "representante"},
    "Producto": {"producto", "nombre", "nombre producto", "producto farmacéutico", "producto farmaceutico"},
    "Fabricante": {"fabricante", "laboratorio", "fabricante laboratorio"},
    "composicion_por": {"composición por", "composicion por", "por"},
    "Forma Farmacéutica": {"forma farmacéutica", "forma farmaceutica", "forma"},
    "Procedencia": {"procedencia", "pais", "país"},
    "Liberación": {"liberación", "liberacion"},
    "Composición": {"composición", "composicion", "principio activo", "principios activos"},
    "Vías de Administración": {"vías de administración", "vias de administracion", "via administracion"},
    "Presentación": {"presentación", "presentacion"},
    "codigo_atc": {"codigo atc", "código atc", "atc"},
    "descripcion_clasificacion": {"clasificación", "clasificacion", "descripcion clasificacion"},
    "grupo_atc_3": {"grupo atc 3", "atc 3"},
    "grupo_atc_4": {"grupo atc 4", "atc 4"},
}

REGISTRY_RE = re.compile(r"\b(?:DE|EE|BE|N|P|I)[-\/\s]?[A-Z0-9]{3,20}\b", flags=re.IGNORECASE)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def clean(value: Any) -> str:
    return str(value or "").strip()


def normalize_text(value: Any) -> str:
    text = clean(value).lower()
    text = (
        text.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ü", "u")
        .replace("ñ", "n")
    )
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_rs(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", clean(value).upper())


def canonical_header(header: Any) -> str | None:
    normalized = normalize_text(header)
    if not normalized:
        return None
    for canonical, aliases in HEADER_ALIASES.items():
        if normalized in {normalize_text(alias) for alias in aliases}:
            return canonical
        if any(normalize_text(alias) in normalized for alias in aliases if len(normalize_text(alias)) >= 4):
            return canonical
    return None


def normalize_records(raw_records: list[dict[str, Any]], *, query: str, source_url: str, scraped_at: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for raw in raw_records:
        normalized = {column: "" for column in OUTPUT_COLUMNS}
        for key, value in raw.items():
            canonical = canonical_header(key)
            if canonical:
                normalized[canonical] = clean(value)

        raw_text = " ".join(clean(value) for value in raw.values())
        if not normalized["item"]:
            match = REGISTRY_RE.search(raw_text)
            if match:
                normalized["item"] = normalize_rs(match.group(0))
        else:
            normalized["item"] = normalize_rs(normalized["item"])

        if not normalized["Producto"]:
            for key, value in raw.items():
                if "producto" in normalize_text(key) or "nombre" in normalize_text(key):
                    normalized["Producto"] = clean(value)
                    break

        normalized["source_query"] = query
        normalized["source_url"] = source_url
        normalized["scraped_at"] = scraped_at
        normalized["extraction_status"] = "complete" if (
            normalized["item"] and normalized["Producto"] and normalized["Composición"]
        ) else "partial"

        if normalized["item"] or normalized["Producto"] or normalized["Composición"]:
            rows.append(normalized)

    return rows


def dedupe_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, str]] = []
    for row in rows:
        key = (row.get("item", ""), normalize_text(row.get("Producto")), normalize_text(row.get("Composición")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_queries(values: list[str], query_file: Path | None) -> list[str]:
    queries: list[str] = []
    for value in values:
        for part in value.split(","):
            if clean(part):
                queries.append(clean(part))
    if query_file and query_file.exists():
        for line in query_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                queries.append(line)
    deduped: list[str] = []
    seen: set[str] = set()
    for query in queries:
        key = normalize_text(query)
        if key not in seen:
            seen.add(key)
            deduped.append(query)
    return deduped


def extraction_script() -> str:
    return """
() => {
  const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const tables = Array.from(document.querySelectorAll('table'));
  const records = [];
  for (const table of tables) {
    const rows = Array.from(table.querySelectorAll('tr'));
    if (rows.length < 2) continue;
    let headers = Array.from(rows[0].querySelectorAll('th,td')).map((cell) => clean(cell.innerText));
    if (!headers.length) continue;
    for (const row of rows.slice(1)) {
      const cells = Array.from(row.querySelectorAll('td,th')).map((cell) => clean(cell.innerText));
      if (!cells.some(Boolean)) continue;
      const record = {};
      headers.forEach((header, index) => {
        record[header || `col_${index + 1}`] = cells[index] || '';
      });
      record._row_text = clean(row.innerText);
      records.push(record);
    }
  }
  return records;
}
"""


def detect_blocked_html(html: str) -> bool:
    text = html.lower()
    return (
        "just a moment" in text
        or "attention required" in text
        or "cloudflare" in text and "cf-error" in text
        or "challenge-platform" in text
    )


def choose_input(page: Any) -> Any:
    candidates = []
    locator = page.locator("input:not([type='hidden']), textarea")
    for index in range(locator.count()):
        element = locator.nth(index)
        try:
            if not element.is_visible():
                continue
            attrs = " ".join(
                clean(element.get_attribute(attr))
                for attr in ("id", "name", "placeholder", "aria-label", "title", "type")
            )
            score = 0
            normalized = normalize_text(attrs)
            for token in ("producto", "composicion", "composición", "buscar", "search", "nombre"):
                if normalize_text(token) in normalized:
                    score += 2
            if "text" in normalized or "search" in normalized:
                score += 1
            candidates.append((score, index))
        except Exception:
            continue
    if not candidates:
        return None
    _, best_index = sorted(candidates, reverse=True)[0]
    return locator.nth(best_index)


def submit_search(page: Any) -> None:
    submitters = page.locator("button, input[type='submit'], input[type='button']")
    for index in range(submitters.count()):
        element = submitters.nth(index)
        try:
            label = " ".join(
                [
                    clean(element.inner_text(timeout=500)),
                    clean(element.get_attribute("value")),
                    clean(element.get_attribute("title")),
                    clean(element.get_attribute("id")),
                    clean(element.get_attribute("name")),
                ]
            )
            normalized = normalize_text(label)
            if any(token in normalized for token in ("buscar", "consultar", "search", "filtrar")) and element.is_visible():
                element.click(timeout=5000)
                return
        except Exception:
            continue
    page.keyboard.press("Enter")


def click_next_page(page: Any) -> bool:
    candidates = [
        "a[rel='next']",
        "button[aria-label*='iguiente']",
        "a:has-text('Siguiente')",
        "button:has-text('Siguiente')",
        "a:has-text('>')",
        "a:has-text('»')",
    ]
    for selector in candidates:
        try:
            locator = page.locator(selector).first
            if locator.count() and locator.is_visible() and locator.is_enabled():
                locator.click(timeout=5000)
                return True
        except Exception:
            continue
    return False


def run_visual_scrape(args: argparse.Namespace) -> dict[str, Any]:
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        return {
            "status": "unavailable",
            "reason": "playwright_not_installed",
            "detail": str(exc),
            "generated_at": utc_now(),
        }

    queries = load_queries(args.query, args.query_file)
    if not queries:
        return {
            "status": "skipped",
            "reason": "no_queries",
            "generated_at": utc_now(),
        }

    all_rows: list[dict[str, str]] = []
    query_reports: list[dict[str, Any]] = []
    scraped_at = utc_now()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(
                headless=not args.headed,
                args=["--disable-dev-shm-usage"],
            )
        except Exception as exc:
            return {
                "status": "unavailable",
                "reason": "browser_launch_failed",
                "detail": str(exc),
                "generated_at": utc_now(),
            }

        context_kwargs = {
            "user_agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "locale": "es-PE",
        }
        if args.storage_state and args.storage_state.exists():
            context_kwargs["storage_state"] = str(args.storage_state)
        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        page.set_default_timeout(args.timeout_ms)

        for query_index, query in enumerate(queries[: args.max_queries], start=1):
            query_report = {"query": query, "status": "started", "rows": 0}
            try:
                page.goto(args.url, wait_until="domcontentloaded", timeout=args.navigation_timeout_ms)
                page.wait_for_timeout(args.challenge_wait_ms)
                html = page.content()
                if detect_blocked_html(html):
                    evidence = args.evidence_dir / f"blocked_{query_index:03d}.html"
                    evidence.write_text(html, encoding="utf-8")
                    query_report.update({"status": "blocked", "evidence": str(evidence)})
                    query_reports.append(query_report)
                    continue

                input_element = choose_input(page)
                if input_element is None:
                    evidence = args.evidence_dir / f"no_input_{query_index:03d}.html"
                    evidence.write_text(html, encoding="utf-8")
                    query_report.update({"status": "no_search_input", "evidence": str(evidence)})
                    query_reports.append(query_report)
                    continue

                input_element.fill(query)
                submit_search(page)
                try:
                    page.wait_for_load_state("networkidle", timeout=args.navigation_timeout_ms)
                except PlaywrightTimeoutError:
                    page.wait_for_timeout(args.after_submit_wait_ms)

                query_rows: list[dict[str, str]] = []
                for page_number in range(1, args.max_pages_per_query + 1):
                    html = page.content()
                    evidence = args.evidence_dir / f"query_{query_index:03d}_page_{page_number:03d}.html"
                    evidence.write_text(html, encoding="utf-8")
                    if detect_blocked_html(html):
                        query_report.update({"status": "blocked_after_submit", "evidence": str(evidence)})
                        break

                    raw_records = page.evaluate(extraction_script())
                    normalized_rows = normalize_records(raw_records, query=query, source_url=page.url, scraped_at=scraped_at)
                    query_rows.extend(normalized_rows)
                    if page_number >= args.max_pages_per_query or not click_next_page(page):
                        break
                    try:
                        page.wait_for_load_state("networkidle", timeout=args.navigation_timeout_ms)
                    except PlaywrightTimeoutError:
                        page.wait_for_timeout(args.after_submit_wait_ms)

                query_rows = dedupe_rows(query_rows)
                all_rows.extend(query_rows)
                query_report.update(
                    {
                        "status": query_report.get("status") if query_report.get("status") != "started" else "ok",
                        "rows": len(query_rows),
                    }
                )
            except Exception as exc:
                query_report.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
            query_reports.append(query_report)

        if args.save_storage_state:
            args.save_storage_state.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(args.save_storage_state))
        context.close()
        browser.close()

    all_rows = dedupe_rows(all_rows)
    write_csv(args.out, all_rows)
    complete_rows = sum(1 for row in all_rows if row.get("extraction_status") == "complete")
    report = {
        "status": "passed" if all_rows else "no_rows",
        "generated_at": utc_now(),
        "url": args.url,
        "queries": len(queries[: args.max_queries]),
        "rows": len(all_rows),
        "complete_rows": complete_rows,
        "partial_rows": len(all_rows) - complete_rows,
        "out": str(args.out),
        "evidence_dir": str(args.evidence_dir),
        "query_reports": query_reports,
    }
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scraper visual opcional para la consulta pública DIGEMID.")
    parser.add_argument("--url", default=os.getenv("DIGEMID_VISUAL_URL", DEFAULT_URL))
    parser.add_argument("--query", action="append", default=[])
    parser.add_argument("--query-file", type=Path, default=os.getenv("DIGEMID_VISUAL_QUERY_FILE"))
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--report-out", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--max-queries", type=int, default=int(os.getenv("DIGEMID_VISUAL_MAX_QUERIES", "20")))
    parser.add_argument("--max-pages-per-query", type=int, default=int(os.getenv("DIGEMID_VISUAL_MAX_PAGES_PER_QUERY", "3")))
    parser.add_argument("--timeout-ms", type=int, default=int(os.getenv("DIGEMID_VISUAL_TIMEOUT_MS", "10000")))
    parser.add_argument("--navigation-timeout-ms", type=int, default=int(os.getenv("DIGEMID_VISUAL_NAVIGATION_TIMEOUT_MS", "30000")))
    parser.add_argument("--challenge-wait-ms", type=int, default=int(os.getenv("DIGEMID_VISUAL_CHALLENGE_WAIT_MS", "8000")))
    parser.add_argument("--after-submit-wait-ms", type=int, default=int(os.getenv("DIGEMID_VISUAL_AFTER_SUBMIT_WAIT_MS", "3000")))
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--storage-state", type=Path, default=os.getenv("DIGEMID_VISUAL_STORAGE_STATE"))
    parser.add_argument("--save-storage-state", type=Path, default=os.getenv("DIGEMID_VISUAL_SAVE_STORAGE_STATE"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    report = run_visual_scrape(args)
    write_json(args.report_out, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] in {"passed", "no_rows", "skipped"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
