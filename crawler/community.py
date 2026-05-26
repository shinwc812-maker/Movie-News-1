"""Community reaction collection.

Community reactions are stored separately from official articles. The first
supported source is Extreme Movie, and additional public list pages can be
configured with CSS selectors.
"""

import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, quote, unquote, urljoin, urlparse

import httpx
from selectolax.parser import HTMLParser

from crawler.briefing_models import CommunityReaction
from crawler.sources.base import REQUEST_TIMEOUT, USER_AGENT, make_article_id
from crawler.sources.extmovie import parse_extmovie_time

EXTMOVIE_BASE_URL = "https://extmovie.com"
EXTMOVIE_HOME_URL = "https://extmovie.com/"
THEQOO_BASE_URL = "https://theqoo.net"
DCINSIDE_SEARCH_URL = "https://search.dcinside.com/post/q"
MUKO_BASE_URL = "https://muko.kr"
MUKO_SEARCH_URL = f"{MUKO_BASE_URL}/index.php"
NAVER_SEARCH_URL = "https://openapi.naver.com/v1/search/{endpoint}.json"
NAVER_PUBLIC_SEARCH_URL = "https://search.naver.com/search.naver"
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
GENERIC_COMMUNITY_TERMS = {"영화 관객 반응", "영화 후기"}
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
SENSITIVE_QUERY_PARAM_PATTERN = re.compile(
    r"([?&](?:key|api_key|apikey|client_id|client_secret|serviceKey)=)[^&\s]+",
    flags=re.IGNORECASE,
)

# 커뮤니티 글 분류용 어휘 — 게시글 제목+발췌만 검사하므로 변형형·은어를 폭넓게 포함.
# 짧은 단음절('좋','잘','갓' 등)은 오매칭 위험이 커서 의도적으로 제외하고,
# 의미가 분명한 2자 이상 변형만 등록한다.
POSITIVE_TERMS = (
    # 재미/호감 (커뮤니티 은어 포함)
    "재밌", "재미있", "재밋", "잼있", "잼나", "꿀잼", "갓잼", "개잼", "혼잼", "씐잼",
    # 평가
    "추천", "강추", "호평", "만족", "명작", "띵작", "갓작", "수작", "역대급", "역대",
    # 기대/호응
    "기대됨", "기대된다", "기대돼", "기대된", "기대중", "기대감", "기다려",
    # 강조형 호감
    "쩐다", "쩔어", "지렸", "지림", "찐맛", "ㄹㅇ재밌", "개좋",
    # '좋' 류 — 부정문(안 좋 등)에 오매칭되지 않도록 명확한 변형만
    "좋아", "좋네", "좋다", "좋더라", "좋았", "좋고", "좋은", "좋더", "좋군",
    # 흥행/객관적 호조
    "흥행", "흥행몰이", "흥행질주", "흥행 질주", "돌파", "신기록", "매진",
    # 짧은 강조
    "최고", "갓갓",
)
NEGATIVE_TERMS = (
    # 재미 부정/은어
    "노잼", "재미없", "잼없", "잼엄", "꿀잼없",
    # 평가
    "별로", "별로네", "별로임", "별로다", "실망", "걱정", "혹평", "불호", "최악",
    "비추", "비추함", "아쉽", "안타깝", "안타까",
    # 작품/품질
    "쓰레기", "망작", "폭망", "똥망", "망함", "망했", "망쳤", "노답", "구려", "구림", "구린",
    # 미적/스토리
    "지루", "지루함", "지루해", "졸려", "졸렸", "졸림", "산만", "산만함",
    "진부", "뻔해", "뻔하", "뻔한", "클리셰", "한계",
    # 부정문(긍정어를 무력화) — 부정 카운트로 합산
    "안 좋", "안좋", "안 재밌", "안재밌", "안 재미있", "안재미있",
    "안 기대", "안기대", "기대 안", "기대안",
)


def _redact_sensitive_query_params(text: str) -> str:
    return SENSITIVE_QUERY_PARAM_PATTERN.sub(r"\1[REDACTED]", text)


def _safe_exception_message(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        return f"HTTP {exc.response.status_code} for {_redact_sensitive_query_params(str(exc.request.url))}"
    return _redact_sensitive_query_params(str(exc))


def summarize_reaction_mood(text: str) -> str:
    """Return a deterministic short mood summary for community snippets.

    제목+발췌가 짧고 다수가 단순 정보/공지(예: '200만 돌파', 'GV 일정')라
    감정어가 안 잡히는 경우가 많다. 그런 글은 "단순 정보/공지"로 라벨한다.
    """
    positive = sum(text.count(term) for term in POSITIVE_TERMS)
    negative = sum(text.count(term) for term in NEGATIVE_TERMS)
    if positive and negative:
        return "호불호가 함께 보임"
    if positive:
        return "긍정 반응 우세"
    if negative:
        return "우려/부정 반응 우세"
    return "단순 정보/공지"


def _text(node, selector: str) -> str:
    if node is None:
        return ""
    target = node.css_first(selector) if selector else node
    return target.text(strip=True) if target is not None else ""


def _first_attr(node, selector: str, attr: str) -> Optional[str]:
    if node is None:
        return None
    target = node.css_first(selector) if selector else node
    if target is None:
        return None
    value = target.attributes.get(attr)
    return value.strip() if value else None


def _normalise_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "").casefold()


def _query_appears_in_text(query: str, text: str) -> bool:
    query = query or ""
    if not query:
        return True
    return _compact_text(query) in _compact_text(text)


def _movie_specific_terms(search_terms: list[str], limit: int | None = None) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for term in search_terms:
        if not term or term in GENERIC_COMMUNITY_TERMS or term in seen:
            continue
        seen.add(term)
        terms.append(term)
        if limit is not None and len(terms) >= limit:
            break
    return terms


def _usable_direct_search_title(title: str) -> bool:
    compact = _compact_text(title)
    return len(compact) >= 3 and not compact.isdecimal()


def _clean_muko_result_title(text: str) -> str:
    title = _normalise_spaces(text)
    title = re.sub(r"\[\d+\].*$", "", title).strip()
    title = re.sub(r"·\d+.*$", "", title).strip()
    return title


def _clean_muko_result_excerpt(container_text: str, raw_title: str, title: str) -> str:
    excerpt = _normalise_spaces(container_text)
    for candidate in (raw_title, title):
        candidate = _normalise_spaces(candidate)
        if candidate and candidate in excerpt:
            excerpt = excerpt.split(candidate, 1)[1]
            break
    excerpt = excerpt.strip(" ·-")
    excerpt = re.split(r"·\d+(?!(?:시간|분|초|일|개월|년|\.))(?=[가-힣A-Za-z[(<])", excerpt, maxsplit=1)[0]
    excerpt = re.sub(r"·\d+$", "", excerpt)
    return excerpt.strip(" ·-")


def _strip_html(text: str) -> str:
    return _normalise_spaces(unescape(re.sub(r"<[^>]+>", "", text or "")))


def _parse_iso_datetime(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_extmovie_community_cards(html: str) -> list[CommunityReaction]:
    """Parse Extreme Movie cards into community reaction records."""
    tree = HTMLParser(html)
    search_roots = []
    for title in tree.css("div.widget-title"):
        if title.text(strip=True).startswith("뉴스"):
            search_roots.append(title.parent or tree.root)
    if not search_roots:
        search_roots = [tree.root]

    reactions: list[CommunityReaction] = []
    seen: set[str] = set()
    for root in search_roots:
        for card in root.css("div.widget-body > a"):
            href = card.attributes.get("href", "").strip()
            title = _text(card, "span.title-text")
            if not href or not title:
                continue
            url = urljoin(EXTMOVIE_BASE_URL, href.split("?", 1)[0])
            if url in seen:
                continue
            seen.add(url)

            excerpt = _text(card, "span.summary")
            date_text = _text(card, "span.meta span.date")
            image_url = _first_attr(card, "img", "src")
            if image_url:
                image_url = urljoin(EXTMOVIE_BASE_URL, image_url)

            reactions.append(
                CommunityReaction(
                    id=make_article_id(url),
                    source="익스트림무비",
                    title=title,
                    url=url,
                    excerpt=excerpt,
                    mood_summary=summarize_reaction_mood(f"{title} {excerpt}"),
                    published_at=parse_extmovie_time(date_text),
                    image_url=image_url,
                )
            )
    return reactions


@dataclass
class ConfiguredCommunityListSource:
    """Config-driven public community list parser for expansion targets."""

    name: str
    list_url: str
    item_selector: str
    title_selector: str
    link_selector: str
    summary_selector: str = ""
    date_selector: str = ""

    def fetch(self) -> list[CommunityReaction]:
        try:
            with httpx.Client(
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
            ) as client:
                response = client.get(self.list_url)
                response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] {self.name}: community fetch failed — {exc}", file=sys.stderr)
            return []
        return self.parse(response.text)

    def parse(self, html: str) -> list[CommunityReaction]:
        tree = HTMLParser(html)
        reactions: list[CommunityReaction] = []
        seen: set[str] = set()
        for item in tree.css(self.item_selector):
            title = _text(item, self.title_selector)
            href = _first_attr(item, self.link_selector, "href")
            if not title or not href:
                continue
            url = urljoin(self.list_url, href)
            if url in seen:
                continue
            seen.add(url)
            excerpt = _text(item, self.summary_selector)
            date_text = _text(item, self.date_selector)
            reactions.append(
                CommunityReaction(
                    id=make_article_id(url),
                    source=self.name,
                    title=title,
                    url=url,
                    excerpt=excerpt,
                    mood_summary=summarize_reaction_mood(f"{title} {excerpt}"),
                    published_at=parse_extmovie_time(date_text),
                )
            )
        return reactions


class ExtMovieCommunitySource:
    name = "익스트림무비"

    def fetch(self) -> list[CommunityReaction]:
        try:
            with httpx.Client(
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
            ) as client:
                response = client.get(EXTMOVIE_HOME_URL)
                response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] {self.name}: community fetch failed — {exc}", file=sys.stderr)
            return []
        response.encoding = "utf-8"
        return parse_extmovie_community_cards(response.text)


@dataclass
class NaverPublicCafeSearchSource:
    """Public Naver search fallback for Cafe posts.

    This does not require Naver Open API credentials. It is intentionally
    conservative: only direct `cafe.naver.com` results are converted.
    """

    source_name: str = "네이버카페"
    query_suffix: str = "영화 후기 관객 반응"

    def fetch(self, search_terms: list[str]) -> list[CommunityReaction]:
        reactions: list[CommunityReaction] = []
        with httpx.Client(
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            for term in search_terms:
                query = f"{term} {self.query_suffix}".strip()
                try:
                    response = client.get(
                        NAVER_PUBLIC_SEARCH_URL,
                        params={"where": "article", "query": query},
                    )
                    response.raise_for_status()
                except Exception as exc:  # noqa: BLE001
                    print(f"[warn] {self.source_name}: public search failed — {exc}", file=sys.stderr)
                    continue
                reactions.extend(self.parse(response.text, query=term))
        return reactions

    def parse(self, html: str, query: str) -> list[CommunityReaction]:
        tree = HTMLParser(html)
        reactions: list[CommunityReaction] = []
        seen: set[str] = set()
        for link in tree.css("a[href]"):
            url = self._extract_cafe_url(link.attributes.get("href") or "")
            if not url or url in seen:
                continue
            title = _normalise_spaces(link.text(strip=True))
            if not title:
                continue
            seen.add(url)
            parent = link.parent
            container_text = _normalise_spaces(parent.text(strip=True)) if parent and parent.tag not in {"html", "body"} else title
            excerpt = container_text.replace(title, "", 1).strip(" ·-")
            if not _query_appears_in_text(query, f"{title} {excerpt}"):
                continue
            reactions.append(
                CommunityReaction(
                    id=make_article_id(url),
                    source=self.source_name,
                    title=title,
                    url=url,
                    excerpt=excerpt,
                    mood_summary=summarize_reaction_mood(f"{title} {excerpt}"),
                    matched_keywords=[query],
                )
            )
        return reactions

    def _extract_cafe_url(self, href: str) -> str:
        parsed = urlparse(href)
        host = parsed.netloc.lower()
        if "cafe.naver.com" in host and self._is_article_url(parsed):
            return href
        for values in parse_qs(parsed.query).values():
            for value in values:
                decoded = unquote(value)
                decoded_parsed = urlparse(decoded)
                if "cafe.naver.com" in decoded_parsed.netloc.lower() and self._is_article_url(decoded_parsed):
                    return decoded
        return ""

    def _is_article_url(self, parsed_url) -> bool:
        path_parts = [part for part in parsed_url.path.split("/") if part]
        if parsed_url.path.lower().endswith("articleread.nhn"):
            return bool(parse_qs(parsed_url.query).get("articleid"))
        return len(path_parts) >= 2


@dataclass
class NaverPublicWebSearchSource:
    """Public Naver web search fallback for allowed community domains.

    Note: SNS platforms (Instagram, X/Twitter, Facebook) are intentionally not
    collected. This generic source is currently unused in production.
    """

    source_name: str
    query_suffix: str
    allowed_domains: tuple[str, ...]
    where: str = "web"
    required_path_fragments: tuple[str, ...] = ()
    required_path_pattern: str = ""

    def fetch(self, search_terms: list[str]) -> list[CommunityReaction]:
        reactions: list[CommunityReaction] = []
        with httpx.Client(
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            for term in search_terms:
                query = f"{term} {self.query_suffix}".strip()
                try:
                    response = client.get(
                        NAVER_PUBLIC_SEARCH_URL,
                        params={"where": self.where, "query": query},
                    )
                    response.raise_for_status()
                except Exception as exc:  # noqa: BLE001
                    print(f"[warn] {self.source_name}: public search failed — {exc}", file=sys.stderr)
                    continue
                reactions.extend(self.parse(response.text, query=term))
        return reactions

    def parse(self, html: str, query: str) -> list[CommunityReaction]:
        tree = HTMLParser(html)
        reactions: list[CommunityReaction] = []
        seen: set[str] = set()
        for link in tree.css("a[href]"):
            url = self._extract_allowed_url(link.attributes.get("href") or "")
            if not url or url in seen:
                continue
            title = _normalise_spaces(link.text(strip=True))
            if not title:
                continue
            seen.add(url)
            parent = link.parent
            container_text = _normalise_spaces(parent.text(strip=True)) if parent and parent.tag not in {"html", "body"} else title
            excerpt = container_text.replace(title, "", 1).strip(" ·-")
            if not _query_appears_in_text(query, f"{title} {excerpt}"):
                continue
            reactions.append(
                CommunityReaction(
                    id=make_article_id(url),
                    source=self.source_name,
                    title=title,
                    url=url,
                    excerpt=excerpt,
                    mood_summary=summarize_reaction_mood(f"{title} {excerpt}"),
                    matched_keywords=[query],
                )
            )
        return reactions

    def _extract_allowed_url(self, href: str) -> str:
        parsed = urlparse(href)
        if self._url_allowed(parsed):
            return href
        for values in parse_qs(parsed.query).values():
            for value in values:
                decoded = unquote(value)
                if self._url_allowed(urlparse(decoded)):
                    return decoded
        return ""

    def _url_allowed(self, parsed_url) -> bool:
        if not self._host_allowed(parsed_url.netloc):
            return False
        if self.required_path_pattern and not re.search(self.required_path_pattern, parsed_url.path):
            return False
        return all(fragment in parsed_url.path for fragment in self.required_path_fragments)

    def _host_allowed(self, host: str) -> bool:
        host = host.lower()
        return any(domain in host for domain in self.allowed_domains)


@dataclass
class TheQooDirectSearchSource:
    """Direct board search for public TheQoo posts."""

    source_name: str = "더쿠"
    boards: tuple[str, ...] = ("movie",)
    max_queries: int = 30
    max_items_per_query: int = 10
    request_interval_seconds: float = 0.5

    def fetch(self, search_terms: list[str]) -> list[CommunityReaction]:
        reactions: list[CommunityReaction] = []
        with httpx.Client(
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            for term in _movie_specific_terms(search_terms, limit=self.max_queries):
                for board in self.boards:
                    try:
                        response = client.get(
                            f"{THEQOO_BASE_URL}/{board}",
                            params={"search_target": "title_content", "search_keyword": term},
                        )
                        response.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        if exc.response.status_code == 429:
                            print(f"[warn] {self.source_name}: rate limited — stopping direct search", file=sys.stderr)
                            return reactions
                        print(f"[warn] {self.source_name}: direct search failed — {exc}", file=sys.stderr)
                        continue
                    except Exception as exc:  # noqa: BLE001
                        print(f"[warn] {self.source_name}: direct search failed — {exc}", file=sys.stderr)
                        continue
                    reactions.extend(self.parse(response.text, query=term))
                    time.sleep(self.request_interval_seconds)
        return reactions

    def parse(self, html: str, query: str) -> list[CommunityReaction]:
        tree = HTMLParser(html)
        reactions: list[CommunityReaction] = []
        seen: set[str] = set()
        for link in tree.css("a[href]"):
            url = self._extract_post_url(link.attributes.get("href") or "")
            if not url or url in seen:
                continue
            title = _normalise_spaces(link.text(strip=True))
            if not title or not _usable_direct_search_title(title):
                continue
            container_text = _normalise_spaces((link.parent or link).text(strip=True))
            excerpt = container_text.replace(title, "", 1).strip(" ·-")
            if not _query_appears_in_text(query, title):
                continue
            seen.add(url)
            reactions.append(
                CommunityReaction(
                    id=make_article_id(url),
                    source=self.source_name,
                    title=title,
                    url=url,
                    excerpt=excerpt,
                    mood_summary=summarize_reaction_mood(f"{title} {excerpt}"),
                    matched_keywords=[query],
                )
            )
            if len(reactions) >= self.max_items_per_query:
                break
        return reactions

    def _extract_post_url(self, href: str) -> str:
        url = urljoin(THEQOO_BASE_URL, href)
        parsed = urlparse(url)
        if not self._host_allowed(parsed.netloc):
            return ""
        if re.search(r"^/(movie|square)/\d+$", parsed.path):
            return url
        return ""

    def _host_allowed(self, host: str) -> bool:
        host = host.lower()
        return host == "theqoo.net" or host.endswith(".theqoo.net")


@dataclass
class DCInsideDirectSearchSource:
    """Direct public search for DCInside posts."""

    source_name: str = "디시인사이드"
    max_queries: int = 30
    max_items_per_query: int = 10
    allowed_gallery_ids: tuple[str, ...] = (
        "commercial_movie",
        "oticket",
        "movie",
        "movie2",
        "mmovie",
        "nouvellevague",
    )

    def fetch(self, search_terms: list[str]) -> list[CommunityReaction]:
        reactions: list[CommunityReaction] = []
        with httpx.Client(
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            for term in _movie_specific_terms(search_terms, limit=self.max_queries):
                try:
                    response = client.get(f"{DCINSIDE_SEARCH_URL}/{quote(term, safe='')}")
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 429:
                        print(f"[warn] {self.source_name}: rate limited — stopping direct search", file=sys.stderr)
                        return reactions
                    print(f"[warn] {self.source_name}: direct search failed — {exc}", file=sys.stderr)
                    continue
                except Exception as exc:  # noqa: BLE001
                    print(f"[warn] {self.source_name}: direct search failed — {exc}", file=sys.stderr)
                    continue
                reactions.extend(self.parse(response.text, query=term))
        return reactions

    def parse(self, html: str, query: str) -> list[CommunityReaction]:
        tree = HTMLParser(html)
        reactions: list[CommunityReaction] = []
        seen: set[str] = set()
        for link in tree.css("a[href]"):
            url = self._extract_post_url(link.attributes.get("href") or "")
            if not url or url in seen:
                continue
            title = _normalise_spaces(link.text(strip=True))
            if not title or not _usable_direct_search_title(title):
                continue
            container_text = _normalise_spaces((link.parent or link).text(strip=True))
            excerpt = container_text.replace(title, "", 1).strip(" ·-")
            if not _query_appears_in_text(query, title):
                continue
            seen.add(url)
            reactions.append(
                CommunityReaction(
                    id=make_article_id(url),
                    source=self.source_name,
                    title=title,
                    url=url,
                    excerpt=excerpt,
                    mood_summary=summarize_reaction_mood(f"{title} {excerpt}"),
                    matched_keywords=[query],
                )
            )
            if len(reactions) >= self.max_items_per_query:
                break
        return reactions

    def _extract_post_url(self, href: str) -> str:
        parsed = urlparse(href)
        if parsed.netloc.lower() != "gall.dcinside.com":
            return ""
        if "/board/view/" not in parsed.path:
            return ""
        gallery_id = parse_qs(parsed.query).get("id", [""])[0]
        if gallery_id not in self.allowed_gallery_ids:
            return ""
        return href


@dataclass
class MukoDirectSearchSource:
    """Direct search for Muko movie-community posts."""

    source_name: str = "무코"
    max_queries: int = 30
    max_items_per_query: int = 10
    request_interval_seconds: float = 0.3
    allowed_sections: tuple[str, ...] = (
        "all",
        "movietalk",
        "goods",
        "ott",
        "free",
        "hot",
        "event",
        "index",
    )

    def fetch(self, search_terms: list[str]) -> list[CommunityReaction]:
        reactions: list[CommunityReaction] = []
        with httpx.Client(
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": BROWSER_USER_AGENT},
            follow_redirects=True,
        ) as client:
            for term in _movie_specific_terms(search_terms, limit=self.max_queries):
                try:
                    response = client.get(MUKO_SEARCH_URL, params={"act": "dispMuko_search", "q": term})
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 429:
                        print(f"[warn] {self.source_name}: rate limited — stopping direct search", file=sys.stderr)
                        return reactions
                    print(f"[warn] {self.source_name}: direct search failed — {exc}", file=sys.stderr)
                    continue
                except Exception as exc:  # noqa: BLE001
                    print(f"[warn] {self.source_name}: direct search failed — {exc}", file=sys.stderr)
                    continue
                reactions.extend(self.parse(response.text, query=term))
                time.sleep(self.request_interval_seconds)
        return reactions

    def parse(self, html: str, query: str) -> list[CommunityReaction]:
        tree = HTMLParser(html)
        reactions: list[CommunityReaction] = []
        seen: set[str] = set()
        for link in tree.css("a[href]"):
            url = self._extract_post_url(link.attributes.get("href") or "")
            if not url or url in seen:
                continue
            raw_title = _normalise_spaces(link.text(strip=True))
            title = _clean_muko_result_title(raw_title)
            if not title or not _usable_direct_search_title(title):
                continue
            parent = link.parent
            container_text = title
            if parent and parent.tag not in {"html", "body"}:
                post_links = [
                    candidate
                    for candidate in parent.css("a[href]")
                    if self._extract_post_url(candidate.attributes.get("href") or "")
                ]
                if len(post_links) <= 1:
                    container_text = _normalise_spaces(parent.text(strip=True))
            excerpt = _clean_muko_result_excerpt(container_text, raw_title, title)
            if not _query_appears_in_text(query, f"{title} {excerpt}"):
                continue
            seen.add(url)
            reactions.append(
                CommunityReaction(
                    id=make_article_id(url),
                    source=self.source_name,
                    title=title,
                    url=url,
                    excerpt=excerpt,
                    mood_summary=summarize_reaction_mood(f"{title} {excerpt}"),
                    matched_keywords=[query],
                )
            )
            if len(reactions) >= self.max_items_per_query:
                break
        return reactions

    def _extract_post_url(self, href: str) -> str:
        url = urljoin(MUKO_BASE_URL, href)
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        if host != "muko.kr" and not host.endswith(".muko.kr"):
            return ""
        document_srl = parse_qs(parsed.query).get("document_srl", [""])[0]
        if document_srl.isdigit():
            return f"{MUKO_BASE_URL}/all/{document_srl}"
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) != 2 or path_parts[0] not in self.allowed_sections or not path_parts[1].isdigit():
            return ""
        return f"{MUKO_BASE_URL}/{path_parts[0]}/{path_parts[1]}"


@dataclass
class NaverSearchCommunitySource:
    """Naver Search API backed community source.

    Use `cafearticle` for Naver Cafe posts. (`webkr` web-search fallback exists
    but SNS platforms like Instagram/X/Facebook are intentionally not collected.)
    """

    source_name: str
    endpoint: str
    client_id: str
    client_secret: str
    base_query_suffix: str
    display: int = 20
    allowed_domains: tuple[str, ...] = ()

    def fetch(self, search_terms: list[str]) -> list[CommunityReaction]:
        reactions: list[CommunityReaction] = []
        with httpx.Client(
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": USER_AGENT,
                "X-Naver-Client-Id": self.client_id,
                "X-Naver-Client-Secret": self.client_secret,
            },
            follow_redirects=True,
        ) as client:
            for term in search_terms:
                query = f"{term} {self.base_query_suffix}".strip()
                try:
                    response = client.get(
                        NAVER_SEARCH_URL.format(endpoint=self.endpoint),
                        params={"query": query, "display": self.display, "sort": "date"},
                    )
                    response.raise_for_status()
                except Exception as exc:  # noqa: BLE001
                    print(f"[warn] {self.source_name}: Naver search failed — {exc}", file=sys.stderr)
                    if getattr(exc, "response", None) is not None and exc.response.status_code == 401:
                        break
                    continue
                reactions.extend(self.parse_payload(response.json(), query=term))
        return reactions

    def parse_payload(self, payload: dict, query: str) -> list[CommunityReaction]:
        reactions: list[CommunityReaction] = []
        for item in payload.get("items", []):
            if not isinstance(item, dict):
                continue
            url = item.get("link") or item.get("originallink") or ""
            if not url:
                continue
            if self.allowed_domains:
                host = urlparse(url).netloc.lower()
                if not any(domain in host for domain in self.allowed_domains):
                    continue
            title = _strip_html(item.get("title") or "")
            description = _strip_html(item.get("description") or "")
            if not title:
                continue
            cafe_name = _strip_html(item.get("cafename") or "")
            excerpt = f"{cafe_name} · {description}" if cafe_name else description
            reactions.append(
                CommunityReaction(
                    id=make_article_id(url),
                    source=self.source_name,
                    title=title,
                    url=url,
                    excerpt=excerpt,
                    mood_summary=summarize_reaction_mood(f"{title} {description}"),
                    matched_keywords=[query],
                )
            )
        return reactions


@dataclass
class YouTubeCommunitySource:
    """YouTube Data API backed video reaction source."""

    api_key: str
    source_name: str = "YouTube"
    query_suffix: str = "영화 리뷰 관객 반응"
    max_results: int = 10

    def fetch(self, search_terms: list[str]) -> list[CommunityReaction]:
        reactions: list[CommunityReaction] = []
        with httpx.Client(
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            for term in search_terms:
                query = f"{term} {self.query_suffix}".strip()
                try:
                    response = client.get(
                        YOUTUBE_SEARCH_URL,
                        params={
                            "key": self.api_key,
                            "part": "snippet",
                            "q": query,
                            "type": "video",
                            "order": "date",
                            "maxResults": self.max_results,
                            "regionCode": "KR",
                            "relevanceLanguage": "ko",
                            "safeSearch": "moderate",
                        },
                    )
                    response.raise_for_status()
                except Exception as exc:  # noqa: BLE001
                    print(
                        f"[warn] {self.source_name}: YouTube search failed — {_safe_exception_message(exc)}",
                        file=sys.stderr,
                    )
                    break
                reactions.extend(self.parse_payload(response.json(), query=term))
        return reactions

    def parse_payload(self, payload: dict, query: str) -> list[CommunityReaction]:
        reactions: list[CommunityReaction] = []
        for item in payload.get("items", []):
            if not isinstance(item, dict):
                continue
            item_id = item.get("id") if isinstance(item.get("id"), dict) else {}
            video_id = item_id.get("videoId")
            if item_id.get("kind") != "youtube#video" or not video_id:
                continue
            snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
            title = _strip_html(snippet.get("title") or "")
            description = _strip_html(snippet.get("description") or "")
            if not title:
                continue
            channel = _strip_html(snippet.get("channelTitle") or "")
            excerpt = f"{channel} · {description}" if channel else description
            image_url = self._thumbnail_url(snippet)
            url = f"https://www.youtube.com/watch?v={video_id}"
            reactions.append(
                CommunityReaction(
                    id=make_article_id(url),
                    source=self.source_name,
                    title=title,
                    url=url,
                    excerpt=excerpt,
                    mood_summary=summarize_reaction_mood(f"{title} {description}"),
                    published_at=_parse_iso_datetime(snippet.get("publishedAt")),
                    image_url=image_url,
                    matched_keywords=[query],
                )
            )
        return reactions

    def _thumbnail_url(self, snippet: dict) -> Optional[str]:
        thumbnails = snippet.get("thumbnails")
        if not isinstance(thumbnails, dict):
            return None
        for key in ("medium", "high", "default"):
            thumbnail = thumbnails.get(key)
            if isinstance(thumbnail, dict) and thumbnail.get("url"):
                return str(thumbnail["url"])
        return None


def _naver_sources_from_env() -> list[NaverSearchCommunitySource]:
    client_id = os.environ.get("NAVER_CLIENT_ID")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("[warn] NAVER_CLIENT_ID/SECRET missing — skipping Naver community search", file=sys.stderr)
        return []
    return [
        NaverSearchCommunitySource(
            source_name="네이버카페",
            endpoint="cafearticle",
            client_id=client_id,
            client_secret=client_secret,
            base_query_suffix="영화 관객 반응 후기",
            display=10,
        ),
    ]


def _youtube_sources_from_env() -> list[YouTubeCommunitySource]:
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        print("[warn] YOUTUBE_API_KEY missing — skipping YouTube community search", file=sys.stderr)
        return []
    return [YouTubeCommunitySource(api_key=api_key)]


COMMUNITY_SOURCES = [ExtMovieCommunitySource()]
# 주의: 인스타그램·X(트위터)·페이스북 등 SNS는 수집하지 않는다(약관·법적 리스크).
PUBLIC_SEARCH_SOURCES = [
    MukoDirectSearchSource(),
    TheQooDirectSearchSource(),
    DCInsideDirectSearchSource(),
    NaverPublicCafeSearchSource(),
]


def default_search_terms() -> list[str]:
    return ["영화", "관객 반응", "박스오피스"]


def fetch_community_reactions(search_terms: Optional[list[str]] = None) -> list[CommunityReaction]:
    search_terms = [term for term in (search_terms or default_search_terms()) if term]
    reactions: list[CommunityReaction] = []
    seen: set[str] = set()
    for source in COMMUNITY_SOURCES:
        for reaction in source.fetch():
            if reaction.url in seen:
                continue
            seen.add(reaction.url)
            reactions.append(reaction)
    for source in PUBLIC_SEARCH_SOURCES:
        for reaction in source.fetch(search_terms):
            if reaction.url in seen:
                continue
            seen.add(reaction.url)
            reactions.append(reaction)
    for source in _naver_sources_from_env():
        for reaction in source.fetch(search_terms):
            if reaction.url in seen:
                continue
            seen.add(reaction.url)
            reactions.append(reaction)
    for source in _youtube_sources_from_env():
        for reaction in source.fetch(search_terms):
            if reaction.url in seen:
                continue
            seen.add(reaction.url)
            reactions.append(reaction)
    return reactions


def save_community_reactions(reactions: list[CommunityReaction], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([reaction.to_dict() for reaction in reactions], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
