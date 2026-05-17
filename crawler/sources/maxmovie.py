"""맥스무비 (KR) — Next.js SSR 사이트 스크래핑 소스.

홈페이지 <script id="__NEXT_DATA__"> 안의 JSON에서 기사 데이터를 추출한다.
JSON이 없으면 일반 HTML(/news/<id> 링크) 파싱으로 폴백.
봇 User-Agent는 403을 받으므로 브라우저 User-Agent를 사용한다.
"""

import json
import re
import sys
from datetime import datetime, timezone
from typing import Optional

import httpx
from selectolax.parser import HTMLParser

from crawler.models import Article
from crawler.sources.base import REQUEST_TIMEOUT, Source, make_article_id

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# __NEXT_DATA__ 안에서 기사 리스트가 들어있는 키들
NEWS_LIST_KEYS = ("listNewsHome", "listNewsContents", "listHotNews")


def _parse_time(raw: Optional[str]) -> Optional[datetime]:
    """ISO 8601 문자열(말미 Z 포함 가능)을 UTC datetime으로 변환."""
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except (ValueError, AttributeError):
        return None


class MaxMovieSource(Source):
    name = "맥스무비"
    country = "KR"
    base_url = "https://www.maxmovie.com"
    home_url = "https://www.maxmovie.com/"

    async def fetch(self) -> list[Article]:
        try:
            async with httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": BROWSER_UA},
                follow_redirects=True,
            ) as client:
                resp = await client.get(self.home_url)
                resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] {self.name}: 홈페이지 요청 실패 — {exc}", file=sys.stderr)
            return []

        items = self._extract_items(resp.text)
        articles: list[Article] = []
        for item in items:
            try:
                article = self._to_article(item)
            except Exception as exc:  # noqa: BLE001
                print(f"[warn] {self.name}: 항목 파싱 실패 — {exc}", file=sys.stderr)
                continue
            if article is not None:
                articles.append(article)
        return articles

    def _extract_items(self, html: str) -> list[dict]:
        """__NEXT_DATA__ JSON에서 기사 dict 리스트를 추출 (mi_id 기준 중복 제거)."""
        tree = HTMLParser(html)
        node = tree.css_first("script#__NEXT_DATA__")
        if node is None:
            print(f"[warn] {self.name}: __NEXT_DATA__ 없음 — HTML 폴백",
                  file=sys.stderr)
            return self._fallback_items(tree)

        try:
            data = json.loads(node.text())
        except json.JSONDecodeError as exc:
            print(f"[warn] {self.name}: __NEXT_DATA__ JSON 파싱 실패 — {exc}",
                  file=sys.stderr)
            return self._fallback_items(tree)

        req_data = (
            data.get("props", {}).get("pageProps", {}).get("reqData", {})
        )
        merged: list[dict] = []
        for key in NEWS_LIST_KEYS:
            value = req_data.get(key)
            if isinstance(value, list):
                merged.extend(v for v in value if isinstance(v, dict))

        seen: set = set()
        unique: list[dict] = []
        for item in merged:
            mi_id = item.get("mi_id")
            if mi_id is None or mi_id in seen:
                continue
            seen.add(mi_id)
            unique.append(item)
        return unique

    def _fallback_items(self, tree: HTMLParser) -> list[dict]:
        """JSON 추출 실패 시 /news/<숫자id> 링크에서 최소 정보만 수집."""
        items: list[dict] = []
        seen: set = set()
        for link in tree.css("a[href*='/news/']"):
            href = link.attributes.get("href", "")
            match = re.search(r"/news/(\d+)", href)
            if not match:
                continue
            mi_id = int(match.group(1))
            if mi_id in seen:
                continue
            seen.add(mi_id)
            items.append({"mi_id": mi_id, "title": link.text(strip=True)})
        return items

    def _to_article(self, item: dict) -> Optional[Article]:
        mi_id = item.get("mi_id")
        if mi_id is None:
            return None
        url = f"{self.base_url}/news/{mi_id}"

        summary = (
            item.get("summary")
            or item.get("sub_title")
            or item.get("contents")
            or ""
        )
        summary = " ".join(summary.split())

        published = _parse_time(item.get("release_time")) or _parse_time(
            item.get("reg_date")
        )

        return Article(
            id=make_article_id(url),
            source=self.name,
            country=self.country,
            title=(item.get("title") or "").strip(),
            summary=summary,
            url=url,
            published_at=published,
            image_url=item.get("main_image"),
        )
