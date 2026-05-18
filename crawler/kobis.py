"""KOBIS market data and reservation-rate capture helpers."""

import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
from selectolax.parser import HTMLParser

from crawler.briefing_models import (
    BoxOfficeMovie,
    MarketSnapshot,
    ReservationSnapshot,
)
from crawler.sources.base import REQUEST_TIMEOUT, USER_AGENT

KST = ZoneInfo("Asia/Seoul")
KOBIS_DAILY_URL = (
    "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/"
    "searchDailyBoxOfficeList.json"
)
KOBIS_RESERVATION_URL = "https://www.kobis.or.kr/kobis/mobile/main/findRealTicketList.do"


def kst_yesterday(today: Optional[date] = None) -> str:
    """Return yesterday in KST as YYYYMMDD."""
    if today is None:
        today = datetime.now(KST).date()
    return (today - timedelta(days=1)).strftime("%Y%m%d")


def build_daily_boxoffice_url(api_key: str, target_date: str) -> str:
    query = urlencode({"key": api_key, "targetDt": target_date})
    return f"{KOBIS_DAILY_URL}?{query}"


def _parse_int(raw: object) -> int:
    text = str(raw or "").replace(",", "").strip()
    if not text:
        return 0
    try:
        return int(text)
    except ValueError:
        return 0


def parse_daily_boxoffice(payload: dict) -> list[BoxOfficeMovie]:
    """Parse KOBIS daily box-office response and return audience top five."""
    raw_items = payload.get("boxOfficeResult", {}).get("dailyBoxOfficeList", [])
    movies: list[BoxOfficeMovie] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        rank = _parse_int(item.get("rank"))
        if not 1 <= rank <= 5:
            continue
        movies.append(
            BoxOfficeMovie(
                rank=rank,
                movie_code=str(item.get("movieCd") or ""),
                title=str(item.get("movieNm") or ""),
                open_date=item.get("openDt") or None,
                audi_count=_parse_int(item.get("audiCnt")),
                audi_acc=_parse_int(item.get("audiAcc")),
                rank_change=str(item.get("rankInten") or item.get("rankOldAndNew") or ""),
            )
        )
    return sorted(movies, key=lambda movie: movie.rank)


def fetch_market_snapshot(api_key: str, target_date: Optional[str] = None) -> MarketSnapshot:
    """Fetch yesterday's KOBIS daily box office."""
    target = target_date or kst_yesterday()
    url = build_daily_boxoffice_url(api_key, target)
    with httpx.Client(
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        response = client.get(url)
        response.raise_for_status()
        payload = response.json()

    return MarketSnapshot(
        target_date=target,
        fetched_at=datetime.now(timezone.utc),
        movies=parse_daily_boxoffice(payload),
    )


def parse_reservation_top(html: str) -> tuple[Optional[str], Optional[str]]:
    """Extract top reservation movie and rate from KOBIS mobile HTML text."""
    text = HTMLParser(html).text(separator="\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    rate_pattern = re.compile(r"(\d+(?:\.\d+)?)%")
    for index, line in enumerate(lines):
        match = rate_pattern.search(line)
        if not match:
            continue
        for previous in reversed(lines[:index]):
            if previous.isdigit():
                continue
            if "예매율" in previous or "전체영화" in previous or "외국영화" in previous:
                continue
            movie = re.sub(r"\s+\([^)]*\)\s*$", "", previous).strip()
            if movie:
                return movie, f"{match.group(1)}%"
    return None, None


def _reservation_asset_path(output_dir: Path, captured_at: datetime) -> Path:
    stamp = captured_at.astimezone(KST).strftime("%Y%m%d-%H%M%S")
    return output_dir / f"kobis-reservation-{stamp}.png"


def capture_reservation_snapshot(output_dir: Path) -> ReservationSnapshot:
    """Capture KOBIS live reservation-rate page screenshot.

    Browser capture is best-effort. Failures are recorded in the snapshot rather
    than raised so the daily static build can still complete.
    """
    captured_at = datetime.now(timezone.utc)
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        from playwright.sync_api import sync_playwright

        image_path = _reservation_asset_path(output_dir, captured_at)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 390, "height": 900})
            page.goto(KOBIS_RESERVATION_URL, wait_until="networkidle", timeout=60000)
            html = page.content()
            top_movie, top_rate = parse_reservation_top(html)
            page.screenshot(path=str(image_path), full_page=True)
            browser.close()

        return ReservationSnapshot(
            captured_at=captured_at,
            image_path=str(image_path.relative_to(output_dir.parent)),
            top_movie=top_movie,
            top_rate=top_rate,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] KOBIS reservation capture failed — {exc}", file=sys.stderr)
        return ReservationSnapshot(
            captured_at=captured_at,
            capture_failed=True,
            error_message=str(exc),
        )


def save_market_snapshot(snapshot: MarketSnapshot, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_reservation_snapshot(snapshot: ReservationSnapshot, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
