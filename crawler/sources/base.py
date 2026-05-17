"""뉴스 소스 인터페이스와 공통 RSS 헬퍼."""

import asyncio
import hashlib
import sys
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

import feedparser
import httpx
from selectolax.parser import HTMLParser

from crawler.models import Article

USER_AGENT = "MovieNewsBot/0.1 (personal use)"
REQUEST_TIMEOUT = 15.0


def strip_html(html: str) -> str:
    """HTML 조각에서 태그를 제거하고 plain text만 반환."""
    if not html:
        return ""
    return HTMLParser(html).text(separator=" ", strip=True)


def entry_published_utc(entry) -> Optional[datetime]:
    """feedparser entry의 발행 시각을 UTC datetime으로 변환."""
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime(*parsed[:6], tzinfo=timezone.utc)


def make_article_id(url: str) -> str:
    """URL 기반 안정적 ID (sha256 앞 16자)."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


class Source(ABC):
    name: str
    country: str

    @abstractmethod
    async def fetch(self) -> list[Article]:
        """이 매체의 최신 기사들을 가져온다."""
        ...


class RssSource(Source):
    """RSS 피드 기반 소스 공통 구현.

    서브클래스는 클래스 변수 ``name``, ``country``, ``feed_url``만 지정하면 된다.
    """

    feed_url: str

    async def fetch(self) -> list[Article]:
        try:
            async with httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
            ) as client:
                resp = await client.get(self.feed_url)
                resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001 — 한 매체 실패가 전체를 멈추면 안 됨
            print(f"[warn] {self.name}: RSS 요청 실패 — {exc}", file=sys.stderr)
            return []

        feed = await asyncio.to_thread(feedparser.parse, resp.content)

        articles: list[Article] = []
        for entry in feed.entries:
            url = entry.get("link", "").strip()
            if not url:
                continue
            articles.append(
                Article(
                    id=make_article_id(url),
                    source=self.name,
                    country=self.country,
                    title=entry.get("title", "").strip(),
                    summary=strip_html(entry.get("summary", "")),
                    url=url,
                    published_at=entry_published_utc(entry),
                )
            )
        return articles
