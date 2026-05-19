"""크롤링 파이프라인 진입점: 모든 소스를 병렬 수집 → data/articles.json 저장."""

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crawler.dedupe import dedupe
from crawler.briefing_models import MarketSnapshot, ReservationSnapshot
from crawler.community import fetch_community_reactions, save_community_reactions
from crawler.kobis import (
    fetch_reservation_snapshot,
    fetch_market_snapshot,
    save_market_snapshot,
    save_reservation_snapshot,
)
from crawler.models import Article
from crawler.policies import fetch_policy_items, save_policy_items
from crawler.scorer import score_all
from crawler.tmdb import enrich_market_with_tmdb, enrich_reservation_with_tmdb
from crawler.translator import translate_articles
from crawler.sources.base import Source
from crawler.sources.cine21 import Cine21Source
from crawler.sources.deadline import DeadlineSource
from crawler.sources.indiewire import IndieWireSource
from crawler.sources.maxmovie import MaxMovieSource
from crawler.sources.rollingstone import RollingStoneSource
from crawler.sources.thr import THRSource
from crawler.sources.variety import VarietySource

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"
MARKET_PATH = DATA_DIR / "market.json"
RESERVATION_PATH = DATA_DIR / "reservation.json"
COMMUNITY_PATH = DATA_DIR / "community.json"
POLICIES_PATH = DATA_DIR / "policies.json"

# 이 시간보다 오래된 기사는 제외 (매일 실행하므로 누적 없이 최신만 표시)
MAX_AGE_HOURS = 48

# 등록된 소스 (8개 매체 전체)
SOURCES: list[Source] = [
    VarietySource(),
    THRSource(),
    DeadlineSource(),
    IndieWireSource(),
    RollingStoneSource(),
    Cine21Source(),
    MaxMovieSource(),
]


async def gather_articles(sources: list[Source]) -> list[Article]:
    """모든 소스의 fetch()를 병렬 실행하고 결과를 합친다."""
    results = await asyncio.gather(*(s.fetch() for s in sources))
    articles: list[Article] = []
    for result in results:
        articles.extend(result)
    return articles


def filter_recent(articles: list[Article], now: datetime | None = None) -> list[Article]:
    """발행 후 MAX_AGE_HOURS 이내 기사만 남긴다.

    발행일을 알 수 없는 기사는 유지한다(8개 소스 모두 '최신 뉴스' 목록/피드에서
    수집하므로 날짜 미상이어도 사실상 최근 기사임).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=MAX_AGE_HOURS)

    kept: list[Article] = []
    for article in articles:
        published = article.published_at
        if published is None:
            kept.append(article)
            continue
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        if published >= cutoff:
            kept.append(article)
    return kept


def save_json_items(items: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")


def save_articles(articles: list[Article]) -> None:
    save_json_items([a.to_dict() for a in articles], ARTICLES_PATH)


def load_optional_market(path: Path = MARKET_PATH) -> MarketSnapshot | None:
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        return MarketSnapshot.from_dict(data)
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] market cache load failed — {exc}", file=sys.stderr)
        return None


def collect_market_snapshot() -> MarketSnapshot | None:
    api_key = os.environ.get("KOBIS_API_KEY")
    if not api_key:
        print("[warn] KOBIS_API_KEY missing — using cached market data if present", file=sys.stderr)
        return load_optional_market()
    try:
        snapshot = fetch_market_snapshot(api_key)
        save_market_snapshot(snapshot, MARKET_PATH)
        print(f"KOBIS market top 5: {len(snapshot.movies)}")
        return snapshot
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] KOBIS market fetch failed — {exc}", file=sys.stderr)
        return load_optional_market()


def enrich_market_snapshot(market: MarketSnapshot | None) -> MarketSnapshot | None:
    if market is None:
        return None
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        return market
    enrich_market_with_tmdb(market, api_key)
    save_market_snapshot(market, MARKET_PATH)
    print("TMDB market metadata enriched")
    return market


def enrich_reservation_snapshot(reservation: ReservationSnapshot | None) -> ReservationSnapshot | None:
    if reservation is None:
        return None
    api_key = os.environ.get("TMDB_API_KEY")
    if not api_key:
        return reservation
    enrich_reservation_with_tmdb(reservation, api_key)
    save_reservation_snapshot(reservation, RESERVATION_PATH)
    print("TMDB reservation metadata enriched")
    return reservation


def collect_reservation_snapshot() -> ReservationSnapshot:
    snapshot = fetch_reservation_snapshot(os.environ.get("KOBIS_API_KEY"))
    save_reservation_snapshot(snapshot, RESERVATION_PATH)
    if snapshot.capture_failed:
        print("[warn] KOBIS reservation data unavailable", file=sys.stderr)
    else:
        print(f"KOBIS reservation top 5: {len(snapshot.movies)}")
    return snapshot


def community_search_terms(
    market: MarketSnapshot | None,
    reservation: ReservationSnapshot | None = None,
) -> list[str]:
    terms: list[str] = []
    if market is not None:
        terms.extend(movie.title for movie in market.movies if movie.title)
    if reservation is not None and not reservation.capture_failed:
        terms.extend(movie.title for movie in reservation.movies if movie.title)
    terms.extend(["영화 관객 반응", "영화 후기"])
    return list(dict.fromkeys(terms))


def main() -> None:
    market = collect_market_snapshot()
    market = enrich_market_snapshot(market)
    reservation = collect_reservation_snapshot()
    reservation = enrich_reservation_snapshot(reservation)

    articles = asyncio.run(gather_articles(SOURCES))
    print(f"Fetched {len(articles)} articles from {len(SOURCES)} sources")

    recent = filter_recent(articles)
    print(f"Within last {MAX_AGE_HOURS}h: {len(recent)} (filtered out {len(articles) - len(recent)})")

    score_all(recent, market=market, reservation=reservation)

    deduped = dedupe(recent)
    print(f"Before dedupe: {len(recent)}, After dedupe: {len(deduped)}")

    translate_articles(deduped)

    deduped.sort(key=lambda a: a.score, reverse=True)

    save_articles(deduped)

    community_reactions = fetch_community_reactions(community_search_terms(market, reservation))
    save_community_reactions(community_reactions, COMMUNITY_PATH)
    print(f"Community reactions: {len(community_reactions)}")

    policy_items = fetch_policy_items()
    save_policy_items(policy_items, POLICIES_PATH)
    print(f"Policy items: {len(policy_items)}")


if __name__ == "__main__":
    main()
