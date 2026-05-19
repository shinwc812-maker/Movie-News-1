"""씨네21 (KR) — HTML 스크래핑 소스.

RSS가 없어 뉴스 목록 페이지에서 기사 URL을 모은 뒤,
각 상세 페이지의 메타 태그(og:description, article:published_time, og:image)를
파싱한다. 사이트 매너를 위해 요청 사이에 1초 sleep.
"""

import asyncio
import sys
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import httpx
from selectolax.parser import HTMLParser

from crawler.models import Article
from crawler.sources.base import USER_AGENT, REQUEST_TIMEOUT, Source, make_article_id

KST = ZoneInfo("Asia/Seoul")
REQUEST_DELAY = 1.0  # 요청 사이 sleep (초)
EXCLUDED_TITLE_TERMS = ("추천도서",)


def _meta(tree: HTMLParser, prop: str) -> Optional[str]:
    node = tree.css_first(f'meta[property="{prop}"]')
    if node is None:
        return None
    content = node.attributes.get("content")
    return content.strip() if content else None


def _parse_published(tree: HTMLParser) -> Optional[datetime]:
    """article:published_time 메타를 UTC datetime으로 변환.

    값에 +09:00 오프셋이 있으면 그대로, 없으면 KST로 간주한 뒤 UTC 변환.
    메타가 없으면 .date 요소(YYYY-MM-DD)로 폴백.
    """
    raw = _meta(tree, "article:published_time")
    if raw:
        try:
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=KST)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass

    date_node = tree.css_first(".date")
    if date_node:
        text = date_node.text(strip=True)
        try:
            dt = datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=KST)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass
    return None


def _excluded_list_title(title: str) -> bool:
    return any(term in title for term in EXCLUDED_TITLE_TERMS)


def parse_cine21_news_list(html: str, base_url: str) -> list[tuple[str, str]]:
    """뉴스 목록 HTML에서 기사 URL과 제목을 추출한다."""
    tree = HTMLParser(html)
    seen: set[str] = set()
    results: list[tuple[str, str]] = []
    for li in tree.css("li.list_with_thumb_item_m"):
        link = li.css_first("a[href*='/news/view/']")
        if link is None:
            continue
        href = link.attributes.get("href", "").strip()
        if not href:
            continue

        title_node = li.css_first("p.news_title")
        title = title_node.text(strip=True) if title_node else ""
        if _excluded_list_title(title):
            continue

        url = urljoin(base_url, href)
        if url in seen:
            continue
        seen.add(url)
        results.append((url, title))
    return results


class Cine21Source(Source):
    name = "씨네21"
    country = "KR"
    base_url = "https://www.cine21.com"
    list_url = "https://www.cine21.com/news"

    async def fetch(self) -> list[Article]:
        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            urls = await self._fetch_list(client)
            articles: list[Article] = []
            for index, (url, list_title) in enumerate(urls):
                if index > 0:
                    await asyncio.sleep(REQUEST_DELAY)
                article = await self._fetch_detail(client, url, list_title)
                if article is not None:
                    articles.append(article)
            return articles

    async def _fetch_list(self, client: httpx.AsyncClient) -> list[tuple[str, str]]:
        """뉴스 목록 페이지에서 (절대 URL, 제목) 쌍을 추출. 중복 URL 제거."""
        try:
            resp = await client.get(self.list_url)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] {self.name}: 목록 페이지 요청 실패 — {exc}", file=sys.stderr)
            return []

        resp.encoding = "utf-8"
        try:
            return parse_cine21_news_list(resp.text, self.base_url)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] {self.name}: 목록 파싱 실패 — {exc}", file=sys.stderr)
            return []

    async def _fetch_detail(
        self, client: httpx.AsyncClient, url: str, list_title: str
    ) -> Optional[Article]:
        """상세 페이지에서 요약/발행일/이미지를 파싱해 Article 생성."""
        try:
            resp = await client.get(url)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            tree = HTMLParser(resp.text)

            title = list_title or _meta(tree, "og:title") or ""
            summary = _meta(tree, "og:description") or ""
            summary = " ".join(summary.split())  # 개행/공백 정리

            return Article(
                id=make_article_id(url),
                source=self.name,
                country=self.country,
                title=title,
                summary=summary,
                url=url,
                published_at=_parse_published(tree),
                image_url=_meta(tree, "og:image"),
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] {self.name}: 상세 페이지 파싱 실패 ({url}) — {exc}",
                  file=sys.stderr)
            return None
