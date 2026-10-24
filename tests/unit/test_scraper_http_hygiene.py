"""Higiene HTTP del scraper de farmacias (sin red: httpx.MockTransport).

Cubre: backoff ante 429 con Retry-After, robots.txt disallow, unquote en
name_from_url y salto del scraper Algolia cuando faltan credenciales.
"""

from __future__ import annotations

import httpx
import pytest

import scripts.scraping.scraper_suplementos as scraper
from scripts.scraping.scraper_suplementos import (
    ALGOLIA_API_KEY_ENV,
    ALGOLIA_APP_ID_ENV,
    USER_AGENT,
    BaseScraper,
    HtmlSearchScraper,
    InretailAlgoliaScraper,
    PoliteHttp,
    RobotsDisallowed,
    build_scrapers,
    name_from_url,
    retry_after_seconds,
)


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Captura las pausas del scraper en vez de dormir de verdad."""
    recorded: list[float] = []
    monkeypatch.setattr(scraper.time, "sleep", lambda seconds: recorded.append(float(seconds)))
    monkeypatch.setattr(scraper.random, "uniform", lambda _a, _b: 0.0)
    return recorded


def make_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), headers={"User-Agent": USER_AGENT})


# ---------------------------------------------------------------------------
# Backoff / Retry-After
# ---------------------------------------------------------------------------


def test_retry_after_seconds_parses_integer_and_missing_header() -> None:
    assert retry_after_seconds(httpx.Response(429, headers={"Retry-After": "7"})) == 7.0
    assert retry_after_seconds(httpx.Response(429)) is None
    assert retry_after_seconds(None) is None


def test_request_retries_on_429_and_honours_retry_after(sleeps: list[float]) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        if len([c for c in calls if c == "/api"]) == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        return httpx.Response(200, json={"ok": True})

    with make_client(handler) as client:
        http = PoliteHttp(client, delay=0.1)
        response = http.request("https://farmacia.example/api")

    assert response.status_code == 200
    assert calls.count("/api") == 2
    assert http.retries == 1
    # Retry-After=2 se respeta tal cual; además hay una pausa `delay` tras cada request real.
    assert 2.0 in sleeps
    assert sleeps.count(0.1) == 2


def test_request_uses_exponential_backoff_on_5xx_and_gives_up(sleeps: list[float]) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        attempts += 1
        return httpx.Response(503)

    with make_client(handler) as client:
        http = PoliteHttp(client, delay=0.0, base_backoff=1.0)
        response = http.request("https://farmacia.example/api")

    assert attempts == 3
    assert response.status_code == 503  # el llamador decide (raise_for_status)
    # Dos esperas entre tres intentos: 1*2^0, 1*2^1 (jitter fijado en 0 por el fixture).
    assert sleeps == [1.0, 2.0]


def test_request_retries_on_network_error_then_succeeds(sleeps: list[float]) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, text="ok")

    with make_client(handler) as client:
        http = PoliteHttp(client, delay=0.0)
        assert http.request("https://farmacia.example/page").text == "ok"
    assert attempts == 2


def test_get_json_raises_for_status_after_exhausted_retries(sleeps: list[float]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(500)

    with make_client(handler) as client:
        base = BaseScraper(client, limit=10, delay=0.0)
        with pytest.raises(httpx.HTTPStatusError):
            base.get_json("https://farmacia.example/api")


# ---------------------------------------------------------------------------
# robots.txt
# ---------------------------------------------------------------------------


ROBOTS_TXT = """
User-agent: *
Disallow: /privado/

User-agent: SupleMatch
Disallow: /api/
"""


def test_robots_disallow_skips_url_and_caches_per_host(sleeps: list[float]) -> None:
    robots_fetches = 0
    fetched_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal robots_fetches
        if request.url.path == "/robots.txt":
            robots_fetches += 1
            return httpx.Response(200, text=ROBOTS_TXT)
        fetched_paths.append(request.url.path)
        return httpx.Response(200, text="<html></html>")

    with make_client(handler) as client:
        http = PoliteHttp(client, delay=0.0)
        with pytest.raises(RobotsDisallowed):
            http.request("https://farmacia.example/api/search?q=zinc")
        with pytest.raises(RobotsDisallowed):
            http.request("https://farmacia.example/api/other")
        http.request("https://farmacia.example/producto/zinc.html")

    assert robots_fetches == 1, "robots.txt se consulta una sola vez por host"
    assert fetched_paths == ["/producto/zinc.html"]
    assert http.robots_skipped == [
        "https://farmacia.example/api/search?q=zinc",
        "https://farmacia.example/api/other",
    ]


def test_ignore_robots_flag_bypasses_check_only_when_explicit(sleeps: list[float]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        return httpx.Response(200, text="ok")

    with make_client(handler) as client:
        strict = PoliteHttp(client, delay=0.0)
        with pytest.raises(RobotsDisallowed):
            strict.request("https://farmacia.example/x")
        lax = PoliteHttp(client, delay=0.0, ignore_robots=True)
        assert lax.request("https://farmacia.example/x").text == "ok"


def test_html_scraper_skips_disallowed_product_page(sleeps: list[float]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /producto/\n")
        return httpx.Response(200, text="<h1>No deberia llegar</h1>")

    with make_client(handler) as client:
        html_scraper = HtmlSearchScraper(client, 10, 0.0, "Demo", "https://farmacia.example")
        assert html_scraper._row_from_page("https://farmacia.example/producto/zinc.html") is None
    assert html_scraper.http.robots_skipped == ["https://farmacia.example/producto/zinc.html"]


def test_build_scrapers_share_one_robots_cache(sleeps: list[float]) -> None:
    with make_client(lambda request: httpx.Response(404)) as client:
        http = PoliteHttp(client, delay=0.0)
        scrapers = build_scrapers(client, set(), 10, 0.0, http=http)
    assert scrapers
    assert all(item.http is http for item in scrapers)


# ---------------------------------------------------------------------------
# name_from_url
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.boticasperu.pe/vitamina-c-%2B-zinc/12345.html", "Vitamina C + Zinc"),
        ("https://www.boticasperu.pe/omega-3-%2C-6-%2C-9/12345.html", "Omega 3, 6, 9"),
        ("https://www.boticasperu.pe/calcio-%26-magnesio/12345.html", "Calcio & Magnesio"),
        ("https://www.boticasperu.pe/melatonina_5mg/12345.html", "Melatonina 5Mg"),
    ],
)
def test_name_from_url_unquotes_percent_encoding(url: str, expected: str) -> None:
    name = name_from_url(url)
    assert name == expected
    assert "%" not in name


# ---------------------------------------------------------------------------
# Algolia credentials
# ---------------------------------------------------------------------------


def test_algolia_scraper_skips_without_env_credentials(monkeypatch: pytest.MonkeyPatch, capsys, sleeps) -> None:
    monkeypatch.delenv(ALGOLIA_APP_ID_ENV, raising=False)
    monkeypatch.delenv(ALGOLIA_API_KEY_ENV, raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"no debe haber tráfico sin credenciales: {request.url}")

    with make_client(handler) as client:
        algolia = InretailAlgoliaScraper(client, 10, 0.0, "Inkafarma", "https://inkafarma.pe")
        assert algolia.configured is False
        assert algolia.fetch() == []

    out = capsys.readouterr().out
    assert "scraper_skipped=Inkafarma" in out
    assert "missing_algolia_credentials" in out
    assert ALGOLIA_APP_ID_ENV in out


def test_algolia_scraper_reads_credentials_from_env(monkeypatch: pytest.MonkeyPatch, sleeps) -> None:
    monkeypatch.setenv(ALGOLIA_APP_ID_ENV, "appid")
    monkeypatch.setenv(ALGOLIA_API_KEY_ENV, "secret-key")
    seen_headers: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(404)
        seen_headers.update({k: v for k, v in request.headers.items() if k.startswith("x-algolia")})
        assert request.method == "POST"
        assert request.url.host == "appid-dsn.algolia.net"
        return httpx.Response(200, json={"hits": [], "nbPages": 0})

    with make_client(handler) as client:
        algolia = InretailAlgoliaScraper(client, 10, 0.0, "Inkafarma", "https://inkafarma.pe", terms=["zinc"])
        assert algolia.configured is True
        assert algolia.fetch() == []

    assert seen_headers["x-algolia-api-key"] == "secret-key"
    assert seen_headers["x-algolia-application-id"] == "appid"


def test_no_hardcoded_algolia_credentials_in_source() -> None:
    source = scraper.__file__
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    assert "15W622LAQ4" not in text
    assert "3ba15abece13b00b123c5501680690f7" not in text
