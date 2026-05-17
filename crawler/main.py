"""크롤링 파이프라인 진입점: 모든 소스를 병렬 수집 → data/articles.json 저장."""

import asyncio
import json
from pathlib import Path

from crawler.dedupe import dedupe
from crawler.models import Article
from crawler.scorer import score_all
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

    score_all(articles)

    deduped = dedupe(articles)
    print(f"Before dedupe: {len(articles)}, After dedupe: {len(deduped)}")

    translate_articles(deduped)

    deduped.sort(key=lambda a: a.score, reverse=True)

    save_articles(deduped)


if __name__ == "__main__":
    main()
