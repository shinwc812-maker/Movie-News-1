"""크롤링 파이프라인 진입점: 모든 소스를 병렬 수집 → data/articles.json 저장."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from crawler.dedupe import dedupe
from crawler.models import Article
from crawler.scorer import score_all
from crawler.community import fetch_community_reactions, save_community_reactions
from crawler.translator import translate_articles
from crawler.sources.base import Source
from crawler.sources.cine21 import Cine21Source
from crawler.sources.deadline import DeadlineSource
from crawler.sources.extmovie import ExtMovieSource
from crawler.sources.indiewire import IndieWireSource
from crawler.sources.maxmovie import MaxMovieSource
from crawler.sources.rollingstone import RollingStoneSource
from crawler.sources.thr import THRSource
from crawler.sources.variety import VarietySource

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"
COMMUNITY_PATH = DATA_DIR / "community.json"

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
    ExtMovieSource(),
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


def save_articles(articles: list[Article]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with ARTICLES_PATH.open("w", encoding="utf-8") as f:
        json.dump(
            [a.to_dict() for a in articles],
            f,
            indent=2,
            ensure_ascii=False,
        )


def main() -> None:
    articles = asyncio.run(gather_articles(SOURCES))
    print(f"Fetched {len(articles)} articles from {len(SOURCES)} sources")

    recent = filter_recent(articles)
    print(f"Within last {MAX_AGE_HOURS}h: {len(recent)} (filtered out {len(articles) - len(recent)})")

    score_all(recent)

    deduped = dedupe(recent)
    print(f"Before dedupe: {len(recent)}, After dedupe: {len(deduped)}")

    translate_articles(deduped)

    deduped.sort(key=lambda a: a.score, reverse=True)

    save_articles(deduped)

    community_reactions = fetch_community_reactions()
    save_community_reactions(community_reactions, COMMUNITY_PATH)
    print(f"Community reactions: {len(community_reactions)}")


if __name__ == "__main__":
    main()
