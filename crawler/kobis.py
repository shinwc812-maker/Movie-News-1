"""KOBIS market data and reservation-rate helpers."""

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
    ReservationMovie,
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


def _parse_float(raw: object) -> float:
    text = str(raw or "").replace(",", "").strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


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


def _reservation_text_lines(html: str) -> list[str]:
    text = HTMLParser(html).text(separator="\n", strip=True)
    return [line.strip() for line in text.splitlines() if line.strip()]


def _normalise_movie_title(title: str) -> str:
    return re.sub(r"\s+\([^)]*\)\s*$", "", title).strip()


def parse_reservation_movies(html: str, limit: int = 5) -> list[ReservationMovie]:
    """Extract live reservation-rate top movies from KOBIS mobile HTML."""
    lines = _reservation_text_lines(html)
    start = 0
    for index, line in enumerate(lines):
        if line == "실시간 예매율":
            start = index

    rate_pattern = re.compile(r"(\d+(?:\.\d+)?)%")
    count_pattern = re.compile(r"\((?:누적:)?([\d,]+)명\)")
    movies: list[ReservationMovie] = []
    index = start
    while index < len(lines) and len(movies) < limit:
        line = lines[index]
        if line == "전체보기":
            break
        if not line.isdigit():
            index += 1
            continue

        rank = _parse_int(line)
        if not 1 <= rank <= limit or index + 1 >= len(lines):
            index += 1
            continue

        title = _normalise_movie_title(lines[index + 1])
        cursor = index + 2
        if cursor < len(lines) and lines[cursor].startswith("("):
            cursor += 1
        while cursor < len(lines) and "예매율" not in lines[cursor]:
            cursor += 1
        if cursor + 1 >= len(lines):
            index += 1
            continue

        rate_line = lines[cursor + 1]
        rate_match = rate_pattern.search(rate_line)
        if not rate_match:
            index += 1
            continue
        count_match = count_pattern.search(rate_line)
        movies.append(
            ReservationMovie(
                rank=rank,
                title=title,
                reservation_rate=_parse_float(rate_match.group(1)),
                reservation_count=_parse_int(count_match.group(1) if count_match else 0),
            )
        )
        index = cursor + 2

    return movies


def parse_reservation_top(html: str) -> tuple[Optional[str], Optional[str]]:
    """Extract top reservation movie and rate from KOBIS mobile HTML text."""
    movies = parse_reservation_movies(html, limit=1)
    if movies:
        return movies[0].title, f"{movies[0].reservation_rate:g}%"
    return None, None


def fetch_reservation_snapshot() -> ReservationSnapshot:
    """Fetch KOBIS live reservation-rate top five as structured data."""
    captured_at = datetime.now(timezone.utc)
    try:
        with httpx.Client(
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            response = client.get(KOBIS_RESERVATION_URL)
            response.raise_for_status()
            html = response.text
        movies = parse_reservation_movies(html)
        top_movie = movies[0].title if movies else None
        top_rate = f"{movies[0].reservation_rate:g}%" if movies else None
        return ReservationSnapshot(
            captured_at=captured_at,
            top_movie=top_movie,
            top_rate=top_rate,
            movies=movies,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] KOBIS reservation fetch failed — {exc}", file=sys.stderr)
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
