"""익스트림무비 (KR) — 홈페이지 '뉴스' 섹션 스크래핑 소스.

홈페이지 한 번만 요청하므로 robots.txt의 Crawl-delay 2는 자동 충족.
기사 링크의 ?category= 쿼리는 robots.txt에서 차단되므로 제거해 정규 URL만 사용.
발행시간은 '4시간 전' 같은 상대 표기 → 현재 시각 기준 UTC datetime으로 변환.
"""

import re
import sys
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import httpx
from dateutil.relativedelta import relativedelta
from selectolax.parser import HTMLParser

from crawler.models import Article
from crawler.sources.base import USER_AGENT, REQUEST_TIMEOUT, Source, make_article_id

KST = ZoneInfo("Asia/Seoul")

_REL_PATTERNS = [
    (re.compile(r"(\d+)\s*분\s*전"), "minutes"),
    (re.compile(r"(\d+)\s*시간\s*전"), "hours"),
    (re.compile(r"(\d+)\s*일\s*전"), "days"),
]
_ABS_PATTERN = re.compile(r"(\d{4})\.(\d{1,2})\.(\d{1,2})")


def parse_extmovie_time(text: str, now: Optional[datetime] = None) -> Optional[datetime]:
    """'방금 전' / 'N분·시간·일 전' / '2026.05.16' 표기를 UTC datetime으로 변환."""
    if not text:
        return None
    if now is None:
        now = datetime.now(timezone.utc)
    text = text.strip()

    if "방금" in text:
        return now

    for pattern, unit in _REL_PATTERNS:
        match = pattern.search(text)
        if match:
            return now - relativedelta(**{unit: int(match.group(1))})

    abs_match = _ABS_PATTERN.search(text)
    if abs_match:
        year, month, day = (int(g) for g in abs_match.groups())
        try:
            kst_midnight = datetime(year, month, day, tzinfo=KST)
        except ValueError:
            return None
        return kst_midnight.astimezone(timezone.utc)

    return None


def _strip_query(url: str) -> str:
    """URL에서 쿼리/프래그먼트를 제거 (robots.txt가 category= 등을 차단)."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


class ExtMovieSource(Source):
    name = "익스트림무비"
    country = "KR"
    base_url = "https://extmovie.com"
    home_url = "https://extmovie.com/"

    async def fetch(self) -> list[Article]:
        try:
            async with httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
            ) as client:
                resp = await client.get(self.home_url)
                resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] {self.name}: 홈페이지 요청 실패 — {exc}", file=sys.stderr)
            return []

        resp.encoding = "utf-8"
        return self._parse(resp.text)

    def _parse(self, html: str) -> list[Article]:
        tree = HTMLParser(html)

        # '뉴스' 위젯 컨테이너 찾기
        widget = None
        for title in tree.css("div.widget-title"):
            if title.text(strip=True).startswith("뉴스"):
                widget = title.parent
                break
        if widget is None:
            print(f"[warn] {self.name}: '뉴스' 위젯을 찾지 못함", file=sys.stderr)
            return []

        now = datetime.now(timezone.utc)
        articles: list[Article] = []
        seen: set[str] = set()
        for card in widget.css("div.widget-body > a"):
            try:
                article = self._card_to_article(card, now)
            except Exception as exc:  # noqa: BLE001
                print(f"[warn] {self.name}: 카드 파싱 실패 — {exc}", file=sys.stderr)
                continue
            if article is None or article.url in seen:
                continue
            seen.add(article.url)
            articles.append(article)
        return articles

    def _card_to_article(self, card, now: datetime) -> Optional[Article]:
        href = card.attributes.get("href", "").strip()
        if not href:
            return None
        url = href if href.startswith("http") else self.base_url + href
        url = _strip_query(url)

        title_node = card.css_first("span.title-text")
        title = title_node.text(strip=True) if title_node else ""
        if not title:
            return None

        summary_node = card.css_first("span.summary")
        summary = summary_node.text(strip=True) if summary_node else ""

        date_node = card.css_first("span.meta span.date")
        published = (
            parse_extmovie_time(date_node.text(strip=True), now)
            if date_node
            else None
        )

        image_url = None
        img = card.css_first("img")
        if img is not None:
            src = img.attributes.get("src")
            if src:
                image_url = src if src.startswith("http") else self.base_url + src

        return Article(
            id=make_article_id(url),
            source=self.name,
            country=self.country,
            title=title,
            summary=summary,
            url=url,
            published_at=published,
            image_url=image_url,
        )
