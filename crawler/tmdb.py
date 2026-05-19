"""Optional TMDB enrichment for KOBIS movie snapshots."""

import sys
from datetime import date
from typing import Optional

import httpx

from crawler.briefing_models import MarketSnapshot, ReservationSnapshot
from crawler.sources.base import REQUEST_TIMEOUT, USER_AGENT

TMDB_SEARCH_MOVIE_URL = "https://api.themoviedb.org/3/search/movie"


def parse_tmdb_movie_result(payload: dict) -> Optional[dict]:
    results = payload.get("results", [])
    if not results or not isinstance(results[0], dict):
        return None
    item = results[0]
    return {
        "tmdb_id": item.get("id"),
        "tmdb_title": item.get("title"),
        "tmdb_original_title": item.get("original_title"),
        "tmdb_overview": item.get("overview") or "",
        "tmdb_poster_path": item.get("poster_path"),
        "tmdb_release_date": item.get("release_date"),
    }


def _release_year(open_date: Optional[str]) -> Optional[str]:
    if not open_date:
        return None
    try:
        return str(date.fromisoformat(open_date).year)
    except ValueError:
        if len(open_date) >= 4 and open_date[:4].isdigit():
            return open_date[:4]
    return None


def _query_candidates(movie: object) -> list[str]:
    candidates = [
        str(getattr(movie, "title", "") or "").strip(),
        str(getattr(movie, "english_title", "") or "").strip(),
    ]
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def fetch_tmdb_movie_metadata(
    movie: object,
    api_key: str,
    client: httpx.Client,
) -> Optional[dict]:
    params = {
        "api_key": api_key,
        "language": "ko-KR",
        "region": "KR",
        "include_adult": "false",
    }
    year = _release_year(getattr(movie, "open_date", None))
    if year:
        params["primary_release_year"] = year
    for query in _query_candidates(movie):
        response = client.get(TMDB_SEARCH_MOVIE_URL, params={**params, "query": query})
        response.raise_for_status()
        metadata = parse_tmdb_movie_result(response.json())
        if metadata:
            return metadata
    return None


def apply_tmdb_metadata(movie: object, metadata: dict) -> None:
    movie.tmdb_id = int(metadata["tmdb_id"]) if metadata.get("tmdb_id") else None
    movie.tmdb_title = metadata.get("tmdb_title")
    movie.tmdb_original_title = metadata.get("tmdb_original_title")
    movie.tmdb_overview = str(metadata.get("tmdb_overview") or "")
    movie.tmdb_poster_path = metadata.get("tmdb_poster_path")
    movie.tmdb_release_date = metadata.get("tmdb_release_date")


def _enrich_movies_with_tmdb(movies: list, api_key: str) -> None:
    if not api_key:
        return
    with httpx.Client(
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        for movie in movies:
            try:
                metadata = fetch_tmdb_movie_metadata(movie, api_key, client)
            except Exception as exc:  # noqa: BLE001
                print(f"[warn] TMDB search failed for {movie.title} — {exc}", file=sys.stderr)
                continue
            if metadata:
                apply_tmdb_metadata(movie, metadata)


def enrich_market_with_tmdb(snapshot: MarketSnapshot, api_key: str) -> None:
    _enrich_movies_with_tmdb(snapshot.movies, api_key)


def enrich_reservation_with_tmdb(snapshot: ReservationSnapshot, api_key: str) -> None:
    _enrich_movies_with_tmdb(snapshot.movies, api_key)
