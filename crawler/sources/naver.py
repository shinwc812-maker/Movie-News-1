"""네이버 뉴스 검색 API (KR) 소스.

영화·공연·문화·예술 관련 키워드를 검색 API로 폭넓게 수집한다.
오픈 API는 카테고리(문화/예술) 파라미터가 없어 키워드 검색으로만 모은다.

- 자격증명: 환경변수 ``NAVER_CLIENT_ID`` / ``NAVER_CLIENT_SECRET``
  (미설정 시 경고 후 빈 리스트 반환 — 다른 소스 수집은 정상 진행)
- 설정: ``config/sources.yaml``의 ``naver`` 섹션 (queries, display, sort)
- 여러 쿼리를 병렬 검색하고 originallink(원문 URL) 기준으로 소스 내부 중복 제거
- title/description의 ``<b>`` 태그·HTML 엔티티는 strip_html로 정리
- pubDate(RFC 1123, 예: "Tue, 20 May 2026 18:30:00 +0900")는 email.utils로 파싱
"""

import asyncio
import os
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional

import httpx
import yaml

from crawler.models import Article
from crawler.sources.base import (
    REQUEST_TIMEOUT,
    USER_AGENT,
    Source,
    make_article_id,
    strip_html,
)

API_URL = "https://openapi.naver.com/v1/search/news.json"
SOURCES_CONFIG = (
    Path(__file__).resolve().parent.parent.parent / "config" / "sources.yaml"
)

# config 누락/오류 시 폴백 기본값
DEFAULT_QUERIES = ["영화", "박스오피스", "영화 개봉", "공연", "뮤지컬"]
DEFAULT_DISPLAY = 30
DEFAULT_SORT = "date"  # date=최신순, sim=정확도순
MAX_DISPLAY = 100      # 네이버 API 상한


def _load_naver_config() -> dict:
    """config/sources.yaml의 naver 섹션을 반환. 없으면 빈 dict."""
    try:
        with SOURCES_CONFIG.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except OSError as exc:
        print(f"[warn] 네이버뉴스: 설정 로드 실패 — {exc}", file=sys.stderr)
        return {}
    return data.get("naver") or {}


def _parse_pubdate(raw: str) -> Optional[datetime]:
    """네이버 pubDate(RFC 1123)를 UTC datetime으로 변환."""
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class NaverNewsSource(Source):
    name = "네이버뉴스"
    country = "KR"

    async def fetch(self) -> list[Article]:
        client_id = os.environ.get("NAVER_CLIENT_ID")
        client_secret = os.environ.get("NAVER_CLIENT_SECRET")
        if not (client_id and client_secret):
            print(
                "[warn] 네이버뉴스: NAVER_CLIENT_ID/SECRET 미설정 — 건너뜀",
                file=sys.stderr,
            )
            return []

        cfg = _load_naver_config()
        queries = cfg.get("queries") or DEFAULT_QUERIES
        display = min(int(cfg.get("display", DEFAULT_DISPLAY)), MAX_DISPLAY)
        sort = cfg.get("sort", DEFAULT_SORT)

        headers = {
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
            "User-Agent": USER_AGENT,
        }

        async with httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT, headers=headers
        ) as client:
            batches = await asyncio.gather(
                *(self._search(client, q, display, sort) for q in queries)
            )

        # 여러 쿼리가 같은 기사를 반환할 수 있어 URL 기준으로 중복 제거
        seen: set[str] = set()
        articles: list[Article] = []
        for batch in batches:
            for art in batch:
                if art.url in seen:
                    continue
                seen.add(art.url)
                articles.append(art)
        return articles

    async def _search(
        self, client: httpx.AsyncClient, query: str, display: int, sort: str
    ) -> list[Article]:
        """쿼리 하나를 검색해 Article 리스트로 변환. 실패 시 빈 리스트."""
        params = {"query": query, "display": display, "sort": sort}
        try:
            resp = await client.get(API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:  # noqa: BLE001 — 한 쿼리 실패가 전체를 멈추면 안 됨
            print(f"[warn] 네이버뉴스: '{query}' 검색 실패 — {exc}", file=sys.stderr)
            return []

        articles: list[Article] = []
        for item in data.get("items", []):
            # originallink(원문 매체 URL)를 우선 — 타 소스와의 중복 제거에 유리
            url = (item.get("originallink") or item.get("link") or "").strip()
            if not url:
                continue
            articles.append(
                Article(
                    id=make_article_id(url),
                    source=self.name,
                    country=self.country,
                    title=strip_html(item.get("title", "")),
                    summary=strip_html(item.get("description", "")),
                    url=url,
                    published_at=_parse_pubdate(item.get("pubDate", "")),
                )
            )
        return articles
