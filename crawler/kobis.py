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
KOBIS_MOVIE_INFO_URL = (
    "https://www.kobis.or.kr/kobisopenapi/webservice/rest/movie/"
    "searchMovieInfo.json"
)
KOBIS_MOVIE_LIST_URL = (
    "https://www.kobis.or.kr/kobisopenapi/webservice/rest/movie/"
    "searchMovieList.json"
)
KOBIS_RESERVATION_URL = "https://www.kobis.or.kr/kobis/mobile/main/findRealTicketList.do"
LOTTE_DISTRIBUTOR_ALIASES = (
    "롯데엔터테인먼트",
    "롯데컬처웍스",
    "롯데컬처웍스(주)롯데엔터테인먼트",
    "Lotte Entertainment",
)


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


def parse_movie_distributors(payload: dict) -> tuple[list[str], bool]:
    """Return distributor company names and whether a movie is Lotte-distributed."""
    companies = payload.get("movieInfoResult", {}).get("movieInfo", {}).get("companys", [])
    distributors: list[str] = []
    seen: set[str] = set()
    for company in companies:
        if not isinstance(company, dict):
            continue
        part_name = str(company.get("companyPartNm") or "")
        if "배급" not in part_name:
            continue
        for key in ("companyNm", "companyNmEn"):
            name = str(company.get(key) or "").strip()
            if name and name not in seen:
                seen.add(name)
                distributors.append(name)
    distributor_text = " ".join(distributors).casefold()
    is_lotte = any(alias.casefold() in distributor_text for alias in LOTTE_DISTRIBUTOR_ALIASES)
    return distributors, is_lotte


def _movie_search_candidates(payload: dict) -> list[dict]:
    return [
        item
        for item in payload.get("movieListResult", {}).get("movieList", [])
        if isinstance(item, dict) and item.get("movieCd")
    ]


def _best_movie_search_match(
    candidates: list[dict],
    title: str,
    english_title: Optional[str],
) -> Optional[str]:
    normalized_title = _normalize_search_value(title)
    normalized_english = _normalize_search_value(english_title or "")
    for candidate in candidates:
        if _normalize_search_value(str(candidate.get("movieNm") or "")) == normalized_title:
            return str(candidate["movieCd"])
    if normalized_english:
        for candidate in candidates:
            if _normalize_search_value(str(candidate.get("movieNmEn") or "")) == normalized_english:
                return str(candidate["movieCd"])
    return str(candidates[0]["movieCd"]) if candidates else None


def _normalize_search_value(value: str) -> str:
    return " ".join(value.casefold().split())


def find_kobis_movie_code(
    title: str,
    english_title: Optional[str],
    client: httpx.Client,
    api_key: str,
) -> Optional[str]:
    """Find a KOBIS movie code by Korean title, falling back to English title."""
    for query in (title, english_title):
        if not query:
            continue
        response = client.get(
            KOBIS_MOVIE_LIST_URL,
            params={"key": api_key, "movieNm": query},
        )
        response.raise_for_status()
        candidates = _movie_search_candidates(response.json())
        match = _best_movie_search_match(candidates, title, english_title)
        if match:
            return match
    return None


def _fetch_movie_distributors(
    movie_code: str,
    client: httpx.Client,
    api_key: str,
) -> tuple[list[str], bool]:
    response = client.get(
        KOBIS_MOVIE_INFO_URL,
        params={"key": api_key, "movieCd": movie_code},
    )
    response.raise_for_status()
    return parse_movie_distributors(response.json())


def enrich_movies_with_distributors(
    movies: list[BoxOfficeMovie],
    client: httpx.Client,
    api_key: str,
) -> None:
    for movie in movies:
        if not movie.movie_code:
            continue
        try:
            distributors, is_lotte = _fetch_movie_distributors(movie.movie_code, client, api_key)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] KOBIS movie detail failed for {movie.title} — {exc}", file=sys.stderr)
            continue
        movie.distributors = distributors
        movie.is_lotte_distributed = is_lotte


def enrich_reservation_movies_with_kobis(
    movies: list[ReservationMovie],
    client: httpx.Client,
    api_key: str,
) -> None:
    for movie in movies:
        try:
            movie_code = find_kobis_movie_code(movie.title, movie.english_title, client, api_key)
            if not movie_code:
                continue
            distributors, is_lotte = _fetch_movie_distributors(movie_code, client, api_key)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] KOBIS reservation movie detail failed for {movie.title} — {exc}", file=sys.stderr)
            continue
        movie.movie_code = movie_code
        movie.distributors = distributors
        movie.is_lotte_distributed = is_lotte


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
        movies = parse_daily_boxoffice(payload)
        enrich_movies_with_distributors(movies, client, api_key)

    return MarketSnapshot(
        target_date=target,
        fetched_at=datetime.now(timezone.utc),
        movies=movies,
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
        english_title = None
        if cursor < len(lines) and lines[cursor].startswith("("):
            english_title = lines[cursor].strip("()").strip() or None
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
                english_title=english_title,
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


def fetch_reservation_snapshot(api_key: Optional[str] = None) -> ReservationSnapshot:
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
            if api_key:
                enrich_reservation_movies_with_kobis(movies, client, api_key)
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
