"""Market trend collection and briefing summaries for Live/IP/popup signals."""

from __future__ import annotations

import html
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Sequence
from urllib.parse import parse_qs, unquote, urlparse

import feedparser
import httpx
from selectolax.parser import HTMLParser

from crawler.briefing_models import MarketTrendItem
from crawler.models import Article
from crawler.sources.base import (
    REQUEST_TIMEOUT,
    USER_AGENT,
    entry_published_utc,
    make_article_id,
    strip_html,
)

NAVER_NEWS_URL = "https://openapi.naver.com/v1/search/news.json"
NAVER_PUBLIC_SEARCH_URL = "https://search.naver.com/search.naver"
GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
AI_TIMEOUT_SECONDS = 45
MARKET_TREND_QUERIES = (
    "이머시브 콘텐츠 체험형 전시",
    "공간 재해석 체험형 콘텐츠",
    "IP 사업 OSMU 굿즈 공연",
    "K팝 팝업스토어 팬덤 굿즈",
    "팝업스토어 오픈런 한정 굿즈",
)


@dataclass(frozen=True)
class MarketTrendCategory:
    category: str
    frame: str
    implication: str
    keywords: tuple[str, ...]


CATEGORIES = (
    MarketTrendCategory(
        category="체험형 콘텐츠",
        frame="공간 재해석·참여형 스토리텔링 기반의 현실 참여형 콘텐츠 확산",
        implication="극장 유휴공간, 특별관, 영화 IP를 관객 참여형 이벤트로 확장하는 기획에 참고할 만함.",
        keywords=(
            "체험형",
            "이머시브",
            "몰입형",
            "방탈출",
            "참여형",
            "전시공간",
            "전시",
            "테마파크",
            "스토리텔링",
            "공간 재해석",
            "실감",
            "LED 돔",
            "인터랙티브",
        ),
    ),
    MarketTrendCategory(
        category="IP/OSMU",
        frame="게임·K팝·키즈 IP가 공연·영화·굿즈·공간으로 확장",
        implication="영화/애니메이션 IP를 굿즈, 공연, 팝업, 극장 이벤트로 연결하는 OSMU 관점에서 추적 필요.",
        keywords=(
            "IP",
            "OSMU",
            "굿즈",
            "캐릭터",
            "게임 IP",
            "게임업계",
            "넥슨",
            "크래프톤",
            "K팝",
            "K-팝",
            "아이돌",
            "키즈",
            "애니메이션",
            "웹툰",
            "공연",
            "뮤지컬",
            "팬미팅",
        ),
    ),
    MarketTrendCategory(
        category="팝업/공간",
        frame="팝업이 팬덤 소비의 기본 동선으로 자리매김",
        implication="극장 로비와 상권 거점에서 한정 굿즈·포토존·예매 동선을 묶는 실험 여지가 큼.",
        keywords=(
            "팝업",
            "팝업스토어",
            "오픈런",
            "팬덤",
            "한정 굿즈",
            "포토카드",
            "성수",
            "명동",
            "오프라인 매장",
            "브랜드 체험",
            "지역 관광",
        ),
    ),
)


def _normalise_text(text: str) -> str:
    text = " ".join(html.unescape(strip_html(text or "")).split())
    particle = r"(?:에도|은|는|이|가|와|과|을|를|에|도|만)"
    return re.sub(
        rf"(?<=[가-힣A-Za-z0-9])\s+({particle})(?=\s|$|[.,!?…'\"”’\]\)])",
        r"\1",
        text,
    )


def _truncate(text: str, limit: int = 120) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _keyword_hits(text: str, keywords: Sequence[str]) -> list[str]:
    hits: list[str] = []
    for keyword in keywords:
        if keyword.isascii():
            pattern = rf"(?<![A-Za-z0-9]){re.escape(keyword)}(?![A-Za-z0-9])"
            if re.search(pattern, text, flags=re.IGNORECASE):
                hits.append(keyword)
            continue
        if keyword.casefold() in text.casefold():
            hits.append(keyword)
    return hits


def _article_text(article: Article) -> str:
    return f"{article.title} {article.summary}"


def classify_market_trend_article(article: Article) -> MarketTrendCategory | None:
    text = _article_text(article)
    ranked: list[tuple[int, int, MarketTrendCategory]] = []
    for index, category in enumerate(CATEGORIES):
        hits = _keyword_hits(text, category.keywords)
        if hits:
            ranked.append((len(hits), -index, category))
    if not ranked:
        return None
    ranked.sort(reverse=True)
    return ranked[0][2]


def _matched_market_keywords(article: Article, category: MarketTrendCategory) -> list[str]:
    text = _article_text(article)
    return _keyword_hits(text, category.keywords)


def _rule_note(article: Article) -> str:
    source_text = article.summary or article.title
    return _truncate(source_text, 130)


def market_trend_from_article(article: Article, category: MarketTrendCategory) -> MarketTrendItem:
    keywords = _matched_market_keywords(article, category)
    return MarketTrendItem(
        id=article.id or make_article_id(article.url or article.title),
        category=category.category,
        title=article.title,
        url=article.url,
        source=article.source,
        frame=category.frame,
        note=_rule_note(article),
        implication=category.implication,
        published_at=article.published_at,
        keywords=keywords[:5],
    )


def build_market_trends(
    articles: Sequence[Article],
    limit_per_category: int = 3,
    ai_command: str | Sequence[str] | None = None,
) -> list[MarketTrendItem]:
    buckets: dict[str, list[MarketTrendItem]] = {category.category: [] for category in CATEGORIES}
    seen_urls: set[str] = set()
    for article in articles:
        category = classify_market_trend_article(article)
        if category is None:
            continue
        dedupe_key = f"{article.url}|{article.title}" if article.url else article.title
        if dedupe_key in seen_urls:
            continue
        seen_urls.add(dedupe_key)
        buckets[category.category].append(market_trend_from_article(article, category))

    items: list[MarketTrendItem] = []
    for category in CATEGORIES:
        category_items = sorted(
            buckets[category.category],
            key=lambda item: item.published_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        items.extend(category_items[:limit_per_category])
    return enrich_market_trends_with_ai(items, command=ai_command)


def _command_args(command: str | Sequence[str]) -> list[str]:
    if isinstance(command, str):
        return shlex.split(command, posix=os.name != "nt")
    return [str(part) for part in command]


def _ai_prompt(items: Sequence[MarketTrendItem]) -> str:
    payload = [
        {
            "id": item.id,
            "category": item.category,
            "title": item.title,
            "source": item.source,
            "note": item.note,
            "keywords": item.keywords,
        }
        for item in items
    ]
    return (
        "다음 기사들을 롯데컬처웍스 Live/IP/극장 공간 사업 관점으로 요약해줘. "
        "출력은 JSON 배열만 허용한다. 각 항목은 id, frame, note, implication 키를 가진다. "
        "frame은 시장 프레임 한 줄, note는 체험사업팀 스크랩의 '내용:' 같은 1문장 단평, "
        "implication은 롯데컬처웍스가 볼 사업적 시사점 1문장으로 작성한다.\n"
        + json.dumps(payload, ensure_ascii=False)
    )


def _parse_ai_output(output: str) -> dict[str, dict]:
    output = output.strip()
    if not output:
        return {}
    match = re.search(r"\[.*\]", output, flags=re.DOTALL)
    if match:
        output = match.group(0)
    data = json.loads(output)
    if not isinstance(data, list):
        return {}
    parsed: dict[str, dict] = {}
    for item in data:
        if isinstance(item, dict) and item.get("id"):
            parsed[str(item["id"])] = item
    return parsed


def enrich_market_trends_with_ai(
    items: Sequence[MarketTrendItem],
    command: str | Sequence[str] | None = None,
) -> list[MarketTrendItem]:
    result = list(items)
    if not result:
        return result
    command = command or os.environ.get("MARKET_TRENDS_AI_CMD")
    if not command:
        return result
    try:
        completed = subprocess.run(
            _command_args(command),
            input=_ai_prompt(result),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=AI_TIMEOUT_SECONDS,
            check=False,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] market trends AI summary failed — {exc}", file=sys.stderr)
        return result
    if completed.returncode != 0:
        print(
            f"[warn] market trends AI summary failed — exit {completed.returncode}",
            file=sys.stderr,
        )
        return result
    try:
        updates = _parse_ai_output(completed.stdout)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"[warn] market trends AI output ignored — {exc}", file=sys.stderr)
        return result

    enriched: list[MarketTrendItem] = []
    for item in result:
        update = updates.get(item.id, {})
        data = item.to_dict()
        data.update(
            {
                "frame": str(update.get("frame") or item.frame),
                "note": str(update.get("note") or item.note),
                "implication": str(update.get("implication") or item.implication),
            }
        )
        enriched.append(MarketTrendItem.from_dict(data))
    return enriched


def _parse_pubdate(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_naver_news_items(payload: dict, query: str) -> list[Article]:
    articles: list[Article] = []
    for item in payload.get("items", []):
        if not isinstance(item, dict):
            continue
        url = str(item.get("originallink") or item.get("link") or "").strip()
        title = _normalise_text(str(item.get("title") or ""))
        if not url or not title:
            continue
        articles.append(
            Article(
                id=make_article_id(url),
                source="Naver News",
                country="KR",
                title=title,
                summary=_normalise_text(str(item.get("description") or "")),
                url=url,
                published_at=_parse_pubdate(item.get("pubDate")),
                matched_keywords=[query],
            )
        )
    return articles


def _normalise_public_result_url(href: str) -> str:
    href = (href or "").strip()
    if not href:
        return ""
    parsed = urlparse(href)
    if parsed.scheme not in {"http", "https"}:
        return ""
    if parsed.netloc.lower().endswith("search.naver.com"):
        for values in parse_qs(parsed.query).values():
            for value in values:
                decoded = unquote(value)
                decoded_parsed = urlparse(decoded)
                if decoded_parsed.scheme in {"http", "https"} and decoded_parsed.netloc:
                    return decoded
        return ""
    return href


def _public_result_summary(link) -> str:
    parent = link.parent
    if parent is None:
        return ""
    summary_node = parent.css_first(".news_dsc, .api_txt_lines, .dsc_txt, .total_dsc")
    if summary_node is not None:
        return _normalise_text(summary_node.text(separator=" ", strip=True))
    title = _normalise_text(link.text(separator=" ", strip=True))
    return _normalise_text(parent.text(separator=" ", strip=True)).replace(title, "", 1).strip(" ·-")


def parse_public_naver_news_items(html_text: str, query: str) -> list[Article]:
    tree = HTMLParser(html_text or "")
    links = tree.css("a.news_tit[href]") or tree.css("a[href]")
    articles: list[Article] = []
    seen: set[str] = set()
    for link in links:
        url = _normalise_public_result_url(link.attributes.get("href") or "")
        if not url or url in seen:
            continue
        title = _normalise_text(link.text(separator=" ", strip=True))
        if len(title) < 4:
            continue
        seen.add(url)
        articles.append(
            Article(
                id=make_article_id(url),
                source="Naver News",
                country="KR",
                title=title,
                summary=_public_result_summary(link),
                url=url,
                matched_keywords=[query],
            )
        )
    return articles


def _entry_source_title(entry) -> str:
    source = entry.get("source", {})
    if isinstance(source, dict):
        return str(source.get("title") or "").strip()
    return str(getattr(source, "title", "") or "").strip()


def _clean_google_news_title(title: str, source: str) -> str:
    title = _normalise_text(title)
    suffix = f" - {source}" if source else ""
    if suffix and title.endswith(suffix):
        return title[: -len(suffix)].rstrip()
    return title


def parse_google_news_rss_items(xml_text: str | bytes, query: str) -> list[Article]:
    feed = feedparser.parse(xml_text)
    articles: list[Article] = []
    for entry in feed.entries:
        url = str(entry.get("link") or "").strip()
        raw_title = str(entry.get("title") or "")
        if not url or not raw_title:
            continue
        source = _entry_source_title(entry) or "Google News RSS"
        title = _clean_google_news_title(raw_title, source)
        articles.append(
            Article(
                id=make_article_id(url),
                source=source,
                country="KR",
                title=title,
                summary=_normalise_text(str(entry.get("summary") or "")),
                url=url,
                published_at=entry_published_utc(entry),
                matched_keywords=[query],
            )
        )
    return articles


def fetch_market_trend_articles_from_google_news(
    queries: Sequence[str] = MARKET_TREND_QUERIES,
    display: int = 5,
) -> list[Article]:
    articles: list[Article] = []
    try:
        with httpx.Client(
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            for query in queries:
                response = client.get(
                    GOOGLE_NEWS_RSS_URL,
                    params={"q": query, "hl": "ko", "gl": "KR", "ceid": "KR:ko"},
                )
                response.raise_for_status()
                articles.extend(parse_google_news_rss_items(response.content, query=query)[:display])
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] market trend Google News RSS failed — {exc}", file=sys.stderr)
    return articles


def fetch_market_trend_fallback_articles(
    queries: Sequence[str] = MARKET_TREND_QUERIES,
    display: int = 5,
) -> list[Article]:
    seen: set[str] = set()
    articles: list[Article] = []
    for article in [
        *fetch_market_trend_articles_from_public_naver(queries, display),
        *fetch_market_trend_articles_from_google_news(queries, display),
    ]:
        key = article.url or article.title
        if not key or key in seen:
            continue
        seen.add(key)
        articles.append(article)
    return articles


def fetch_market_trend_articles_from_public_naver(
    queries: Sequence[str] = MARKET_TREND_QUERIES,
    display: int = 5,
) -> list[Article]:
    articles: list[Article] = []
    try:
        with httpx.Client(
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            for query in queries:
                response = client.get(
                    NAVER_PUBLIC_SEARCH_URL,
                    params={"where": "news", "query": query},
                )
                response.raise_for_status()
                articles.extend(parse_public_naver_news_items(response.text, query=query)[:display])
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] market trend public search failed — {exc}", file=sys.stderr)
    return articles


def fetch_market_trend_articles_from_naver(
    client_id: str | None,
    client_secret: str | None,
    queries: Sequence[str] = MARKET_TREND_QUERIES,
    display: int = 5,
    public_fallback: bool = True,
) -> list[Article]:
    if not client_id or not client_secret:
        print("[warn] NAVER_CLIENT_ID/SECRET missing — skipping market trend news", file=sys.stderr)
        return fetch_market_trend_fallback_articles(queries, display) if public_fallback else []
    articles: list[Article] = []
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            for query in queries:
                response = client.get(
                    NAVER_NEWS_URL,
                    params={"query": query, "display": display, "sort": "date"},
                    headers={
                        "X-Naver-Client-Id": client_id,
                        "X-Naver-Client-Secret": client_secret,
                    },
                )
                response.raise_for_status()
                articles.extend(parse_naver_news_items(response.json(), query=query))
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] market trend news fetch failed — {exc}", file=sys.stderr)
        if public_fallback and not articles:
            return fetch_market_trend_fallback_articles(queries, display)
    if public_fallback and not articles:
        return fetch_market_trend_fallback_articles(queries, display)
    return articles


def save_market_trends(items: Sequence[MarketTrendItem], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([item.to_dict() for item in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
