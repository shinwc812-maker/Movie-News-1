"""크롤링 파이프라인 진입점: 모든 소스를 병렬 수집 → data/articles.json 저장."""

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crawler.dedupe import dedupe
from crawler.briefing_models import MarketSnapshot, OverseasWeekendSnapshot, ReservationSnapshot
from crawler.boxofficemojo import fetch_overseas_weekend_snapshot, save_overseas_weekend_snapshot
from crawler.community import fetch_community_reactions, save_community_reactions
from crawler.kobis import (
    fetch_reservation_snapshot,
    fetch_market_snapshot,
    save_market_snapshot,
    save_reservation_snapshot,
)
from crawler.market_trends import (
    build_market_trends,
    fetch_market_trend_articles_from_naver,
    save_market_trends,
)
from crawler.models import Article
from crawler.policies import fetch_policy_items, save_policy_items
from crawler.scorer import score_all
from crawler.tmdb import enrich_market_with_tmdb, enrich_reservation_with_tmdb
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
OVERSEAS_WEEKEND_PATH = DATA_DIR / "overseas_weekend.json"
MARKET_TRENDS_PATH = DATA_DIR / "market_trends.json"

# 이 시간보다 오래된 기사는 제외 (매일 실행하므로 누적 없이 최신만 표시)
MAX_AGE_HOURS = 48
BRIEF_TITLE_MAX_LENGTH = 40

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


def load_optional_overseas_weekend(path: Path = OVERSEAS_WEEKEND_PATH) -> OverseasWeekendSnapshot | None:
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as f:
            data = json.load(f)
        return OverseasWeekendSnapshot.from_dict(data)
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] overseas weekend cache load failed — {exc}", file=sys.stderr)
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


def collect_overseas_weekend_snapshot() -> OverseasWeekendSnapshot | None:
    snapshot = fetch_overseas_weekend_snapshot()
    if snapshot.movies:
        save_overseas_weekend_snapshot(snapshot, OVERSEAS_WEEKEND_PATH)
        print(f"Box Office Mojo overseas weekend top 5: {len(snapshot.movies)}")
        return snapshot
    cached = load_optional_overseas_weekend()
    if cached is not None:
        print("[warn] Box Office Mojo unavailable — using cached overseas weekend data", file=sys.stderr)
        return cached
    save_overseas_weekend_snapshot(snapshot, OVERSEAS_WEEKEND_PATH)
    return snapshot


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


def brief_movie_title(title: str) -> str:
    title = str(title or "").strip()
    if len(title) > BRIEF_TITLE_MAX_LENGTH and " : " in title:
        return title.split(" : ", 1)[0].strip()
    if len(title) > 60:
        title = re.split(r"\.\s+", title, maxsplit=1)[0].strip()
    return title


def community_search_terms(
    market: MarketSnapshot | None,
    reservation: ReservationSnapshot | None = None,
) -> list[str]:
    base_terms: list[str] = []
    market_titles: list[str] = []
    reservation_titles: list[str] = []
    if market is not None:
        market_titles.extend(brief_movie_title(movie.title) for movie in market.movies if movie.title)
    if reservation is not None and not reservation.capture_failed:
        reservation_titles.extend(brief_movie_title(movie.title) for movie in reservation.movies if movie.title)
    for index in range(max(len(market_titles), len(reservation_titles))):
        if index < len(market_titles):
            base_terms.append(market_titles[index])
        if index < len(reservation_titles):
            base_terms.append(reservation_titles[index])
    terms: list[str] = []
    for term in base_terms:
        if term not in terms:
            terms.append(term)
        compact = "".join(term.split())
        if compact and compact != term and compact not in terms:
            terms.append(compact)
    terms.extend(["영화 관객 반응", "영화 후기"])
    return list(dict.fromkeys(terms))


def focused_movie_news_terms(
    market: MarketSnapshot | None,
    reservation: ReservationSnapshot | None = None,
) -> list[str]:
    """Return official-news search terms for owned/priority distributed titles."""
    terms: list[str] = []
    movies = []
    if market is not None:
        movies.extend(market.movies)
    if reservation is not None and not reservation.capture_failed:
        movies.extend(reservation.movies)
    for movie in movies:
        if not getattr(movie, "is_lotte_distributed", False):
            continue
        title = brief_movie_title(movie.title)
        if title and title not in terms:
            terms.append(title)
        compact = "".join(title.split())
        if compact and compact != title and compact not in terms:
            terms.append(compact)
    return terms


def collect_focused_movie_news(
    market: MarketSnapshot | None,
    reservation: ReservationSnapshot | None = None,
) -> list[Article]:
    terms = focused_movie_news_terms(market, reservation)
    if not terms:
        print("Focused movie news: no priority(Lotte) titles to search")
        return []
    # public_fallback=True: Naver 오픈 API가 실패/빈응답이어도 공개검색으로 폴백해
    # 롯데 우선작(예: 와일드 씽) 공식 기사를 놓치지 않는다.
    articles = fetch_market_trend_articles_from_naver(
        os.environ.get("NAVER_CLIENT_ID"),
        os.environ.get("NAVER_CLIENT_SECRET"),
        queries=terms,
        display=5,
        public_fallback=True,
    )
    print(f"Focused movie news: {len(articles)} articles for terms {terms}")
    return articles


def collect_market_trend_items(articles: list[Article]):
    trend_articles = fetch_market_trend_articles_from_naver(
        os.environ.get("NAVER_CLIENT_ID"),
        os.environ.get("NAVER_CLIENT_SECRET"),
    )
    items = build_market_trends(
        [*articles, *trend_articles],
        ai_command=os.environ.get("MARKET_TRENDS_AI_CMD"),
    )
    return items


def main() -> None:
    market = collect_market_snapshot()
    market = enrich_market_snapshot(market)
    reservation = collect_reservation_snapshot()
    reservation = enrich_reservation_snapshot(reservation)
    overseas_weekend = collect_overseas_weekend_snapshot()

    articles = asyncio.run(gather_articles(SOURCES))
    focused_news = collect_focused_movie_news(market, reservation)
    articles.extend(focused_news)
    print(f"Fetched {len(articles)} articles from {len(SOURCES)} sources")

    recent = filter_recent(articles)
    print(f"Within last {MAX_AGE_HOURS}h: {len(recent)} (filtered out {len(articles) - len(recent)})")

    score_all(recent, market=market, reservation=reservation, overseas_weekend=overseas_weekend)

    deduped = dedupe(recent)
    print(f"Before dedupe: {len(recent)}, After dedupe: {len(deduped)}")

    deduped.sort(key=lambda a: a.score, reverse=True)

    save_articles(deduped)

    market_trends = collect_market_trend_items(deduped)
    save_market_trends(market_trends, MARKET_TRENDS_PATH)
    print(f"Market trends: {len(market_trends)}")

    community_reactions = fetch_community_reactions(community_search_terms(market, reservation))
    save_community_reactions(community_reactions, COMMUNITY_PATH)
    print(f"Community reactions: {len(community_reactions)}")

    policy_items = fetch_policy_items()
    save_policy_items(policy_items, POLICIES_PATH)
    print(f"Policy items: {len(policy_items)}")


if __name__ == "__main__":
    main()
