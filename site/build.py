"""Build the static internal movie/culture briefing dashboard."""

import html as _html
import json
import hashlib
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"
MARKET_PATH = DATA_DIR / "market.json"
COMMUNITY_PATH = DATA_DIR / "community.json"
POLICIES_PATH = DATA_DIR / "policies.json"
RESERVATION_PATH = DATA_DIR / "reservation.json"
OVERSEAS_WEEKEND_PATH = DATA_DIR / "overseas_weekend.json"
MARKET_TRENDS_PATH = DATA_DIR / "market_trends.json"
SITE_DIR = ROOT / "site"
DIST_DIR = ROOT / "dist"
DIST_PATH = DIST_DIR / "index.html"
DATA_SNAPSHOT_PATHS = (
    ARTICLES_PATH,
    COMMUNITY_PATH,
    MARKET_PATH,
    MARKET_TRENDS_PATH,
    OVERSEAS_WEEKEND_PATH,
    POLICIES_PATH,
    RESERVATION_PATH,
)
KST = ZoneInfo("Asia/Seoul")
LEGACY_COMMUNITY_SOURCES = {"익스트림무비"}
MARKET_TREND_SECTION_ORDER = (
    "체험형 콘텐츠",
    "공간 사업",
    "IP 사업",
    "콜라보/협업",
    "버추얼·AR/VR",
)
COMMUNITY_SECTION_ORDER = (
    "무코",
    "익스트림무비",
    "더쿠",
    "디시인사이드",
    "네이버카페",
    "YouTube",
)
CURATION_STRATEGIC_KEYWORDS = (
    "롯데배급",
    "롯데엔터테인먼트",
    "롯데컬처웍스",
    "Lotte Entertainment",
    "Lotte Cultureworks",
    "Paramount",
    "파라마운트",
)
CURATION_EXCLUDED_TITLE_TERMS = ("추천도서", "MY PICK", "[델리]", "[trans x cross]")
COMPETITOR_SIGNAL_KEYWORDS = (
    "CJ ENM",
    "CJ엔터테인먼트",
    "CJ CGV",
    "CGV",
)
COMPETITOR_CONTENT_KEYWORDS = (
    "CJ ENM",
    "CJ엔터테인먼트",
    "봉준호",
    "라인업",
    "신작",
)
OFFICIAL_FEED_OVERSEAS_PRIORITY_KEYWORDS = (
    "Park Chan-Wook",
    "Bong Joon",
    "Tang Wei",
    "Korean",
    "Korea",
    "Cannes Market",
    "box office",
    "gross",
    "release",
    "theatrical",
    "ticket",
    "exhibitor",
)
PROMO_REFERENCE_COMPANY_KEYWORDS = (
    "롯데컬처웍스",
    "롯데시네마",
    "롯데엔터테인먼트",
    "롯데엔터",
    "와일드 씽",
    "와일드씽",
    "강동원",
    "엄태구",
    "박지현",
    "오정세",
    "탑건",
    "광음시네마",
)
PROMO_REFERENCE_INDUSTRY_KEYWORDS = (
    "CGV",
    "메가박스",
    "스크린엑스",
    "특별관",
    "상영회",
    "극장가",
    "관객",
    "흥행",
    "박스오피스",
    "칸",
    "나홍진",
    "연상호",
    "박찬욱",
    "애니메이션",
    "AI",
    "K콘텐츠",
    "할인권",
    "투자",
    "제작비",
)
PROMO_REFERENCE_COMPANY_BOOST = 2000
PROMO_REFERENCE_INDUSTRY_BOOST = 250
OVERSEAS_WEEKEND_BOOST = 350
OVERSEAS_WEEKEND_ONLY_CAP = 500
POLICY_SIGNAL_BOOST = 2400
POLICY_SIGNAL_KEYWORDS = (
    "제작지원",
    "지원사업",
    "극장",
    "영화관",
    "상영관",
    "지역 영화관",
    "영화관람",
    "관람 활성화",
    "할인권",
    "관람료",
    "입장권",
    "티켓 가격",
    "독립예술영화",
    "국제공동제작",
    "상영",
    "배급",
)
POLICY_SECTION_KEYWORDS = (
    "지원사업",
    "지원 공고",
    "정책",
    "관람료",
    "할인권",
    "입장권",
    "티켓 가격",
    "지역 영화관",
    "상영관",
    "독립예술영화",
    "국제공동제작",
)
OVERSEAS_CONTEXT_KEYWORDS = (
    "롯데배급",
    "롯데엔터테인먼트",
    "롯데컬처웍스",
    "Lotte Entertainment",
    "Lotte Cultureworks",
)
CORE_CURATION_AI_TIMEOUT_SECONDS = 90
CORE_CURATION_SECTIONS = (
    {
        "key": "boxoffice",
        "title": "흥행·배급",
        "eyebrow": "box office / distribution",
    },
    {
        "key": "policy",
        "title": "극장·정책",
        "eyebrow": "theater policy",
    },
    {
        "key": "competitor",
        "title": "경쟁사·산업",
        "eyebrow": "competitor / industry",
    },
    {
        "key": "overseas",
        "title": "해외·마켓",
        "eyebrow": "global market",
    },
    {
        "key": "culture_ip",
        "title": "문화/IP",
        "eyebrow": "culture / IP",
    },
)
CULTURE_IP_KEYWORDS = (
    "IP",
    "OSMU",
    "애니메이션",
    "웹툰",
    "캐릭터",
    "굿즈",
    "K콘텐츠",
    "K팝",
    "팬덤",
    "팝업",
    "전시",
    "공연",
    "AI",
)


def load_json(path: Path, fallback):
    if not path.exists():
        return fallback
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return fallback


def format_int(value) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "0"


def format_rate(value) -> str:
    try:
        return f"{float(value):g}%"
    except (TypeError, ValueError):
        return "0%"


def format_ratio_percent(value, digits: int = 1) -> str:
    try:
        ratio = float(value)
    except (TypeError, ValueError):
        return ""
    return f"{ratio * 100:.{digits}f}%"


def format_reservation_label(count, rate) -> str:
    formatted_count = format_int(count)
    formatted_rate = format_rate(rate)
    return f"{formatted_count}명 ({formatted_rate})"


def format_audience_delta(count, rate=None, include_rate: bool = True) -> str:
    try:
        delta = int(count)
    except (TypeError, ValueError):
        delta = 0
    if delta > 0:
        label = f"▲{format_int(delta)}명"
    elif delta < 0:
        label = f"▼{format_int(abs(delta))}명"
    else:
        label = "0명"
    if not include_rate:
        return label
    try:
        rate_value = float(rate)
    except (TypeError, ValueError):
        rate_value = 0.0
    sign = "+" if rate_value > 0 else ""
    return f"{label} ({sign}{rate_value:.1f}%)"


def relative_time(published_iso: str | None, now: datetime) -> str:
    if not published_iso:
        return ""
    try:
        dt = datetime.fromisoformat(published_iso)
    except ValueError:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    seconds = max((now - dt).total_seconds(), 0.0)
    minutes = seconds / 60
    if minutes < 1:
        return "방금 전"
    if minutes < 60:
        return f"{int(minutes)}분 전"
    hours = minutes / 60
    if hours < 24:
        return f"{int(hours)}시간 전"
    days = hours / 24
    if days < 7:
        return f"{int(days)}일 전"
    return dt.astimezone(KST).strftime("%Y.%m.%d")


def to_article_view(article: dict, now: datetime) -> dict:
    title = article.get("title") or ""
    summary = article.get("summary") or ""
    content_kind = article.get("content_kind")
    if not content_kind:
        content_kind = "community" if article.get("source") in LEGACY_COMMUNITY_SOURCES else "official"
    return {
        "id": article.get("id", ""),
        "content_kind": content_kind,
        "country": article.get("country", ""),
        "source": article.get("source", ""),
        "url": article.get("url", ""),
        "image_url": article.get("image_url"),
        "rel_time": relative_time(article.get("published_at"), now),
        "score": float(article.get("score") or 0),
        "matched_keywords": article.get("matched_keywords") or [],
        "title": article.get("title_ko") or title,
        "excerpt": article.get("summary_ko") or summary,
        "mood_summary": "커뮤니티 반응",
        "ko_title": article.get("title_ko") or title,
        "en_title": title,
        "ko_summary": article.get("summary_ko") or summary,
        "en_summary": summary,
    }


def to_community_view(item: dict, now: datetime) -> dict:
    return {
        "id": item.get("id", ""),
        "content_kind": "community",
        "source": item.get("source", ""),
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "excerpt": item.get("excerpt", ""),
        "mood_summary": item.get("mood_summary", ""),
        "rel_time": relative_time(item.get("published_at"), now),
        "matched_keywords": item.get("matched_keywords") or [],
        "score": 0.0,
    }


def to_policy_view(item: dict, now: datetime) -> dict:
    return {
        "id": item.get("id", ""),
        "content_kind": "policy",
        "source": item.get("source", ""),
        "category": item.get("category", ""),
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "summary": item.get("summary", ""),
        "rel_time": relative_time(item.get("published_at"), now),
        "deadline": item.get("deadline"),
    }


def market_trend_views(items: list[dict], now: datetime) -> list[dict]:
    views: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        views.append(
            {
                "content_kind": "market_trend",
                "category": item.get("category", ""),
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "source": item.get("source", ""),
                "frame": item.get("frame", ""),
                "note": item.get("note", ""),
                "implication": item.get("implication", ""),
                "keywords": item.get("keywords") or [],
                "rel_time": relative_time(item.get("published_at"), now),
            }
        )
    return views


def split_articles_by_kind(views: list[dict]) -> tuple[list[dict], list[dict]]:
    official = [view for view in views if view.get("content_kind", "official") == "official"]
    community = [view for view in views if view.get("content_kind") == "community"]
    return official, community


def _ordered_group_sections(
    items: list[dict],
    key: str,
    order: tuple[str, ...],
    limit_per_section: int | None = None,
) -> list[dict]:
    buckets: dict[str, list[dict]] = {}
    for item in items:
        group = str(item.get(key) or "기타")
        buckets.setdefault(group, []).append(item)

    ordered_titles = [title for title in order if title in buckets]
    ordered_titles.extend(sorted(title for title in buckets if title not in order))

    sections: list[dict] = []
    for title in ordered_titles:
        group_items = buckets[title]
        sections.append(
            {
                "title": title,
                "count": len(group_items),
                "items": group_items[:limit_per_section] if limit_per_section is not None else group_items,
            }
        )
    return sections


def build_market_trend_sections(market_trends: list[dict]) -> list[dict]:
    return _ordered_group_sections(market_trends, "category", MARKET_TREND_SECTION_ORDER)


def build_community_sections(
    community_views: list[dict],
    limit_per_section: int = 4,
    priority_titles: list[str] | None = None,
) -> list[dict]:
    priority_titles = priority_titles or []
    if priority_titles:
        community_views = sorted(
            community_views,
            key=lambda item: 0 if _matched_title(item, priority_titles) else 1,
        )
    return _ordered_group_sections(community_views, "source", COMMUNITY_SECTION_ORDER, limit_per_section)


def _compact_match_text(text: str) -> str:
    return "".join((text or "").casefold().split())


def _matched_title(item: dict, titles: list[str]) -> bool:
    matched = item.get("matched_keywords") or []
    matched_compact = {_compact_match_text(keyword) for keyword in matched if keyword}
    return any(_compact_match_text(title) in matched_compact for title in titles if title)


def _engagement_blob(item: dict) -> str:
    """기사/커뮤니티 항목의 검색 대상 텍스트(공백 제거·소문자)."""
    return _compact_match_text(
        " ".join(
            [
                str(item.get("title") or ""),
                str(item.get("excerpt") or ""),
                str(item.get("summary") or ""),
                str(item.get("mood_summary") or ""),
                *[str(keyword) for keyword in item.get("matched_keywords") or []],
            ]
        )
    )


def build_movie_engagement(
    movies: list[dict],
    official_views: list[dict],
    community_views: list[dict],
) -> list[dict]:
    """TOP 5 영화별로 수집한 공식 기사 수와 커뮤니티 반응 수를 집계(막대그래프용)."""
    article_blobs = [_engagement_blob(a) for a in official_views]
    community_blobs = [_engagement_blob(c) for c in community_views]
    rows: list[dict] = []
    for movie in movies or []:
        title = str(movie.get("title") or "")
        key = _compact_match_text(title)
        if len(key) < 2:
            article_count = community_count = 0
        else:
            article_count = sum(1 for blob in article_blobs if key in blob)
            community_count = sum(1 for blob in community_blobs if key in blob)
        rows.append(
            {
                "rank": movie.get("rank"),
                "title": title,
                "article_count": article_count,
                "community_count": community_count,
            }
        )
    # 막대 길이는 차트 내 최댓값 기준으로 정규화한다.
    peak = max([1, *[r["article_count"] for r in rows], *[r["community_count"] for r in rows]])
    for row in rows:
        row["article_pct"] = round(row["article_count"] / peak * 100)
        row["community_pct"] = round(row["community_count"] / peak * 100)
    return rows


def _curation_text(item: dict) -> str:
    return " ".join(
        [
            str(item.get("title") or ""),
            str(item.get("excerpt") or ""),
            str(item.get("summary") or ""),
            *[str(keyword) for keyword in item.get("matched_keywords") or []],
        ]
    )


def _has_excluded_curation_title(item: dict) -> bool:
    title = str(item.get("title") or "")
    return any(term in title for term in CURATION_EXCLUDED_TITLE_TERMS)


def _is_community_item(item: dict) -> bool:
    return item.get("content_kind") == "community"


def _is_policy_item(item: dict) -> bool:
    return item.get("content_kind") == "policy"


def _has_competitor_signal(item: dict) -> bool:
    text = _curation_text(item)
    return any(keyword.casefold() in text.casefold() for keyword in COMPETITOR_SIGNAL_KEYWORDS)


def _competitor_priority_boost(item: dict) -> int:
    if not _has_competitor_signal(item):
        return 0
    text = _curation_text(item)
    content_hits = sum(
        1 for keyword in COMPETITOR_CONTENT_KEYWORDS if keyword.casefold() in text.casefold()
    )
    return 450 + min(content_hits, 2) * 300


def _has_strategic_keyword(item: dict) -> bool:
    text = _curation_text(item)
    return any(keyword.casefold() in text.casefold() for keyword in CURATION_STRATEGIC_KEYWORDS)


def _has_overseas_context_keyword(item: dict) -> bool:
    text = _curation_text(item)
    return any(keyword.casefold() in text.casefold() for keyword in OVERSEAS_CONTEXT_KEYWORDS)


def _promo_reference_boost(item: dict) -> int:
    compact_text = _compact_match_text(_curation_text(item))
    compact_company_keywords = {
        _compact_match_text(keyword) for keyword in PROMO_REFERENCE_COMPANY_KEYWORDS
    }
    compact_industry_keywords = {
        _compact_match_text(keyword) for keyword in PROMO_REFERENCE_INDUSTRY_KEYWORDS
    }
    company_hits = sum(
        1 for keyword in compact_company_keywords if keyword in compact_text
    )
    industry_hits = sum(
        1 for keyword in compact_industry_keywords if keyword in compact_text
    )
    return (
        min(company_hits, 2) * PROMO_REFERENCE_COMPANY_BOOST
        + min(industry_hits, 3) * PROMO_REFERENCE_INDUSTRY_BOOST
    )


def _has_policy_signal(item: dict) -> bool:
    text = _curation_text(item)
    return any(keyword in text for keyword in POLICY_SIGNAL_KEYWORDS)


def _curation_candidate_allowed(
    item: dict,
    market_titles: list[str],
    reservation_titles: list[str],
    overseas_titles: list[str],
) -> bool:
    if _has_excluded_curation_title(item):
        return False
    country = item.get("country")
    is_overseas = bool(country) and country != "KR"
    has_market_context = bool(market_titles or reservation_titles or overseas_titles)
    if _is_policy_item(item):
        return _has_policy_signal(item)
    if _is_community_item(item) and has_market_context:
        return _matched_title(item, market_titles) or _matched_title(item, reservation_titles)
    if not is_overseas or not has_market_context:
        return True
    return (
        _matched_title(item, market_titles)
        or _matched_title(item, reservation_titles)
        or _matched_title(item, overseas_titles)
        or _has_overseas_context_keyword(item)
    )


def _curation_priority(
    item: dict,
    market_titles: list[str],
    reservation_titles: list[str],
    overseas_titles: list[str],
) -> float:
    score = float(item.get("score") or 0)
    if _is_policy_item(item):
        return score + POLICY_SIGNAL_BOOST if _has_policy_signal(item) else score
    is_overseas = bool(item.get("country")) and item.get("country") != "KR"
    has_domestic_market_context = _matched_title(item, market_titles) or _matched_title(item, reservation_titles)
    has_overseas_weekend_context = _matched_title(item, overseas_titles)
    if is_overseas and has_overseas_weekend_context and not has_domestic_market_context and not _has_overseas_context_keyword(item):
        score = min(score, OVERSEAS_WEEKEND_ONLY_CAP)
    if item.get("country") == "KR":
        score += 900
    if _matched_title(item, market_titles):
        score += 1600
    if _matched_title(item, reservation_titles):
        score += 1300
    if has_overseas_weekend_context:
        score += OVERSEAS_WEEKEND_BOOST
    if "롯데배급" in (item.get("matched_keywords") or []):
        score += 1100
    score += _competitor_priority_boost(item)
    if _has_strategic_keyword(item):
        score += 600
    score += _promo_reference_boost(item)
    return score


def top_curation_items(
    official_views: list[dict],
    community_views: list[dict] | None = None,
    policy_views: list[dict] | None = None,
    limit: int = 5,
    max_overseas_official: int = 2,
    max_community_items: int = 0,
    max_policy_items: int = 1,
    max_competitor_items: int = 1,
    market_titles: list[str] | None = None,
    reservation_titles: list[str] | None = None,
    overseas_titles: list[str] | None = None,
) -> list[dict]:
    market_titles = market_titles or []
    reservation_titles = reservation_titles or []
    overseas_titles = overseas_titles or []
    community_views = community_views or []
    policy_views = policy_views or []
    if market_titles or reservation_titles or overseas_titles:
        items = [
            item
            for item in list(official_views) + list(community_views) + list(policy_views)
            if _curation_candidate_allowed(item, market_titles, reservation_titles, overseas_titles)
        ]
        items = sorted(
            items,
            key=lambda item: _curation_priority(item, market_titles, reservation_titles, overseas_titles),
            reverse=True,
        )
    else:
        items = [
            item
            for item in list(official_views) + list(community_views) + list(policy_views)
            if _curation_candidate_allowed(item, market_titles, reservation_titles, overseas_titles)
        ]
        items = sorted(items, key=lambda item: float(item.get("score") or 0), reverse=True)
    overseas_count = 0
    community_count = 0
    policy_count = 0
    competitor_count = 0
    selected: list[dict] = []
    for item in items:
        if _is_community_item(item):
            if community_count >= max_community_items:
                continue
            community_count += 1
        if _is_policy_item(item):
            if policy_count >= max_policy_items:
                continue
            policy_count += 1
        if _has_competitor_signal(item):
            if competitor_count >= max_competitor_items:
                continue
            competitor_count += 1
        is_overseas = bool(item.get("country")) and item.get("country") != "KR"
        if is_overseas and overseas_count >= max_overseas_official:
            continue
        if is_overseas:
            overseas_count += 1
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def _keyword_in_text(keyword: str, text: str) -> bool:
    if keyword.isascii():
        pattern = rf"(?<![A-Za-z0-9]){re.escape(keyword)}(?![A-Za-z0-9])"
        return re.search(pattern, text, flags=re.IGNORECASE) is not None
    return keyword.casefold() in text.casefold()


def _has_any_keyword(item: dict, keywords: tuple[str, ...]) -> bool:
    text = _curation_text(item)
    return any(_keyword_in_text(keyword, text) for keyword in keywords)


def _curation_item_id(item: dict) -> str:
    if item.get("id"):
        return str(item["id"])
    identity = str(item.get("url") or item.get("title") or "")
    if not identity:
        identity = json.dumps(item, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


def _curation_dedupe_key(item: dict) -> str:
    return str(item.get("url") or item.get("title") or _curation_item_id(item))


def _truncate_text(text: str, limit: int = 260) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _fallback_curation_summary(item: dict) -> str:
    title = str(item.get("ko_title") or item.get("title") or "")
    text = (
        item.get("ko_summary")
        or item.get("summary")
        or item.get("excerpt")
        or item.get("en_summary")
        or title
        or ""
    )
    if len(str(text)) < 80 and title and title not in str(text):
        text = f"{title} — {text}"
    return _truncate_text(str(text))


def _has_boxoffice_or_distribution_signal(
    item: dict,
    market_titles: list[str],
    reservation_titles: list[str],
) -> bool:
    matched = item.get("matched_keywords") or []
    text = _curation_text(item)
    lotte_signal = (
        "롯데배급" in matched
        or "롯데엔터테인먼트" in text
        or "롯데엔터" in text
        or "Lotte Entertainment" in text
    )
    return (
        lotte_signal
        or _matched_title(item, market_titles)
        or _matched_title(item, reservation_titles)
        or any(keyword in text for keyword in ("박스오피스", "흥행", "예매", "관객수"))
    )


def _curation_section_key(
    item: dict,
    market_titles: list[str],
    reservation_titles: list[str],
    overseas_titles: list[str],
) -> str:
    is_overseas = bool(item.get("country")) and item.get("country") != "KR"
    if _is_policy_item(item):
        return "policy"
    if _has_boxoffice_or_distribution_signal(item, market_titles, reservation_titles):
        return "boxoffice"
    if _has_any_keyword(item, POLICY_SECTION_KEYWORDS):
        return "policy"
    if _has_competitor_signal(item):
        return "competitor"
    if (
        _matched_title(item, overseas_titles)
        or _official_feed_priority_hits(item)
        or (is_overseas and _has_overseas_context_keyword(item))
    ):
        return "overseas"
    if not is_overseas and _has_any_keyword(item, CULTURE_IP_KEYWORDS):
        return "culture_ip"
    return ""


def _curation_candidate_pool(
    official_views: list[dict],
    policy_views: list[dict],
    market_titles: list[str],
    reservation_titles: list[str],
    overseas_titles: list[str],
) -> list[dict]:
    official_candidates = [
        item
        for item in official_views
        if not _has_excluded_curation_title(item)
    ]
    policy_candidates = [
        item
        for item in policy_views
        if _curation_candidate_allowed(item, market_titles, reservation_titles, overseas_titles)
    ]
    candidates = [
        *official_candidates,
        *policy_candidates,
    ]
    return sorted(
        candidates,
        key=lambda item: _curation_priority(item, market_titles, reservation_titles, overseas_titles),
        reverse=True,
    )


def _with_curation_brief(item: dict, section: dict) -> dict:
    enriched = dict(item)
    enriched["id"] = _curation_item_id(enriched)
    enriched["curation_section"] = section["key"]
    enriched["curation_section_title"] = section["title"]
    enriched.setdefault("curation_title", enriched.get("ko_title") or enriched.get("title") or "")
    enriched.setdefault("curation_summary", _fallback_curation_summary(enriched))
    return enriched


def _command_args(command: str | list[str] | tuple[str, ...]) -> list[str]:
    if isinstance(command, str):
        return shlex.split(command, posix=os.name != "nt")
    return [str(part) for part in command]


def _curation_ai_prompt(sections: list[dict]) -> str:
    payload = []
    for section in sections:
        for item in section.get("items", []):
            payload.append(
                {
                    "id": item.get("id"),
                    "section": section.get("title"),
                    "title": item.get("title"),
                    "country": item.get("country"),
                    "source": item.get("source"),
                    "summary": item.get("curation_summary"),
                    "matched_keywords": item.get("matched_keywords") or [],
                }
            )
    return (
        "다음 핵심 큐레이션 기사들을 롯데엔터테인먼트/롯데컬처웍스 내부 보고용으로 정리해줘. "
        "출력은 JSON 배열만 허용한다. 각 항목은 id, title, summary 키를 가진다. "
        "title은 한국어 기사 제목으로 작성한다. country가 KR이 아니면 원문 제목을 자연스러운 한국어 제목으로 번역한다. "
        "summary는 내용 요약으로 2~3문장, 180~260자 안팎으로 쓰고 기사 사실과 사업적 맥락을 함께 담는다. "
        "평가, 점수, 별도 의견 필드는 만들지 않는다. 커뮤니티 말투가 아니라 내부 보고서 톤으로 작성한다.\n"
        + json.dumps(payload, ensure_ascii=False)
    )


def _parse_curation_ai_output(output: str) -> dict[str, dict]:
    output = output.strip()
    if not output:
        return {}
    match = re.search(r"\[.*\]", output, flags=re.DOTALL)
    if match:
        output = match.group(0)
    parsed = json.loads(output)
    if not isinstance(parsed, list):
        return {}
    return {
        str(item["id"]): item
        for item in parsed
        if isinstance(item, dict) and item.get("id")
    }


def enrich_curation_sections_with_ai(
    sections: list[dict],
    command: str | list[str] | tuple[str, ...] | None = None,
) -> list[dict]:
    result = [
        {**section, "items": [dict(item) for item in section.get("items", [])]}
        for section in sections
    ]
    for section in result:
        for item in section.get("items", []):
            item.setdefault("curation_title", item.get("ko_title") or item.get("title") or "")
    if not result:
        return result
    command = command or os.environ.get("CORE_CURATION_AI_CMD")
    if not command:
        return result
    try:
        completed = subprocess.run(
            _command_args(command),
            input=_curation_ai_prompt(result),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=CORE_CURATION_AI_TIMEOUT_SECONDS,
            check=False,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] core curation AI summary failed — {exc}", file=sys.stderr)
        return result
    if completed.returncode != 0:
        print(
            f"[warn] core curation AI summary failed — exit {completed.returncode}",
            file=sys.stderr,
        )
        return result
    try:
        updates = _parse_curation_ai_output(completed.stdout)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        print(f"[warn] core curation AI output ignored — {exc}", file=sys.stderr)
        return result
    for section in result:
        for item in section.get("items", []):
            update = updates.get(str(item.get("id")), {})
            if update.get("title"):
                item["curation_title"] = str(update["title"])
            if update.get("summary"):
                item["curation_summary"] = str(update["summary"])
    return result


def build_curation_sections(
    official_views: list[dict],
    community_views: list[dict] | None = None,
    policy_views: list[dict] | None = None,
    limit_per_section: int = 10,
    market_titles: list[str] | None = None,
    reservation_titles: list[str] | None = None,
    overseas_titles: list[str] | None = None,
    ai_command: str | list[str] | tuple[str, ...] | None = None,
) -> list[dict]:
    del community_views  # Core curation intentionally excludes raw community reactions.
    market_titles = market_titles or []
    reservation_titles = reservation_titles or []
    overseas_titles = overseas_titles or []
    policy_views = policy_views or []
    candidates = _curation_candidate_pool(
        official_views,
        policy_views,
        market_titles,
        reservation_titles,
        overseas_titles,
    )
    used: set[str] = set()
    sections: list[dict] = []
    for definition in CORE_CURATION_SECTIONS:
        items: list[dict] = []
        for item in candidates:
            dedupe_key = _curation_dedupe_key(item)
            if dedupe_key in used:
                continue
            section_key = _curation_section_key(
                item,
                market_titles,
                reservation_titles,
                overseas_titles,
            )
            if section_key != definition["key"]:
                continue
            items.append(_with_curation_brief(item, definition))
            used.add(dedupe_key)
            if len(items) >= limit_per_section:
                break
        if items:
            sections.append(
                {
                    "key": definition["key"],
                    "title": definition["title"],
                    "eyebrow": definition["eyebrow"],
                    "items": items,
                }
            )
    return enrich_curation_sections_with_ai(sections, command=ai_command)


def _official_feed_priority_hits(item: dict) -> int:
    text = _curation_text(item)
    return sum(
        1
        for keyword in OFFICIAL_FEED_OVERSEAS_PRIORITY_KEYWORDS
        if keyword.casefold() in text.casefold()
    )


def _official_feed_priority(item: dict) -> float:
    score = float(item.get("score") or 0)
    priority_hits = _official_feed_priority_hits(item)
    return score + priority_hits * 1200


def _official_feed_topic_key(item: dict) -> str:
    text = _curation_text(item)
    folded = text.casefold()
    for keyword in OFFICIAL_FEED_OVERSEAS_PRIORITY_KEYWORDS:
        if keyword.casefold() in folded:
            return keyword.casefold()
    return _compact_match_text(str(item.get("title") or ""))


def _distinct_official_overseas(views: list[dict]) -> list[dict]:
    selected: list[dict] = []
    seen_topics: set[str] = set()
    for view in views:
        topic_key = _official_feed_topic_key(view)
        if topic_key and topic_key in seen_topics:
            continue
        if topic_key:
            seen_topics.add(topic_key)
        selected.append(view)
    return selected


def select_official_feed(
    official_views: list[dict],
    limit: int = 12,
    max_overseas: int = 2,
) -> list[dict]:
    eligible = [view for view in official_views if not _has_excluded_curation_title(view)]
    korean = [view for view in eligible if view.get("country") == "KR"]
    overseas = [view for view in eligible if view.get("country") != "KR"]
    priority_overseas = [view for view in overseas if _official_feed_priority_hits(view)]
    if priority_overseas:
        overseas = priority_overseas
    overseas = sorted(overseas, key=_official_feed_priority, reverse=True)
    overseas = _distinct_official_overseas(overseas)
    selected = korean[:limit]
    remaining = max(limit - len(selected), 0)
    selected.extend(overseas[: min(max_overseas, remaining)])
    return selected[:limit]


def market_views(market: dict) -> list[dict]:
    movies = market.get("movies") if isinstance(market, dict) else []
    views: list[dict] = []
    for movie in movies or []:
        if not isinstance(movie, dict):
            continue
        audi_inten = movie.get("audi_inten")
        audi_change = movie.get("audi_change")
        try:
            delta_int = int(audi_inten)
        except (TypeError, ValueError):
            delta_int = 0
        # CSS에서 색상을 결정: 증가=빨강(굵게), 감소=파랑(굵게), 변화 없음=중립
        audi_delta_sign = "up" if delta_int > 0 else "down" if delta_int < 0 else "flat"
        seat_count = int(movie.get("seat_count") or 0)
        view = {
            "rank": movie.get("rank"),
            "title": movie.get("title", ""),
            "open_date": movie.get("open_date", ""),
            "audi_count": format_int(movie.get("audi_count")),
            "audi_acc": format_int(movie.get("audi_acc")),
            "audi_delta": format_audience_delta(audi_inten, audi_change),
            "audi_delta_short": format_audience_delta(audi_inten, include_rate=False),
            "audi_delta_sign": audi_delta_sign,
            "seat_count": format_int(seat_count),
            "seat_share": format_ratio_percent(movie.get("seat_share")),
            "seat_sales_rate": format_ratio_percent(movie.get("seat_sales_rate"), digits=2),
            "seat_metrics_available": seat_count > 0,
            "rank_change": movie.get("rank_change") or "",
        }
        view["top_label"] = f"{view['title']} ({view['audi_count']}명 / {view['audi_delta_short']})"
        views.append(view)
    return views


def reservation_view(reservation: dict) -> dict:
    if not isinstance(reservation, dict):
        return {"available": False, "movies": []}
    movies = [
        {
            "rank": movie.get("rank"),
            "title": movie.get("title", ""),
            "reservation_rate": format_rate(movie.get("reservation_rate")),
            "reservation_count": format_int(movie.get("reservation_count")),
            "reservation_label": format_reservation_label(
                movie.get("reservation_count"),
                movie.get("reservation_rate"),
            ),
        }
        for movie in reservation.get("movies", [])
        if isinstance(movie, dict)
    ]
    return {
        "available": bool(movies) and not reservation.get("capture_failed"),
        "movies": movies,
        "top_movie": reservation.get("top_movie"),
        "top_rate": reservation.get("top_rate"),
        "captured_at": reservation.get("captured_at"),
        "error_message": reservation.get("error_message"),
    }


def overseas_weekend_view(overseas_weekend: dict) -> dict:
    if not isinstance(overseas_weekend, dict):
        return {"available": False, "movies": [], "weekend_label": ""}
    movies = [
        {
            "rank": movie.get("rank"),
            "title": movie.get("title", ""),
            "gross": movie.get("gross", ""),
            "url": movie.get("url", ""),
        }
        for movie in overseas_weekend.get("movies", [])
        if isinstance(movie, dict)
    ]
    return {
        "available": bool(movies) and not overseas_weekend.get("error_message"),
        "weekend_label": overseas_weekend.get("weekend_label", ""),
        "movies": movies,
        "error_message": overseas_weekend.get("error_message"),
    }


def strip_trailing_whitespace(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines()) + "\n"


def archive_timestamp_path(now: datetime) -> Path:
    local_now = now.astimezone(KST)
    return Path(local_now.strftime("%Y-%m-%d")) / local_now.strftime("%H%M%S")


def next_archive_path(dist_dir: Path, data_dir: Path, archive_key: Path) -> Path:
    date_part = archive_key.parent
    time_part = archive_key.name
    for index in range(1, 100):
        folder = time_part if index == 1 else f"{time_part}-{index:02d}"
        candidate = date_part / folder
        if not (dist_dir / "archive" / candidate).exists() and not (data_dir / "archive" / candidate).exists():
            return candidate
    raise RuntimeError(f"archive path exhausted for {archive_key}")


def write_archive_snapshot(
    html: str,
    now: datetime,
    data_paths=DATA_SNAPSHOT_PATHS,
    dist_dir: Path = DIST_DIR,
    data_dir: Path = DATA_DIR,
) -> dict[str, Path]:
    archive_key = next_archive_path(dist_dir, data_dir, archive_timestamp_path(now))
    html_path = dist_dir / "archive" / archive_key / "index.html"
    snapshot_data_dir = data_dir / "archive" / archive_key

    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html, encoding="utf-8")
    snapshot_data_dir.mkdir(parents=True, exist_ok=True)

    for data_path in data_paths:
        data_path = Path(data_path)
        if not data_path.exists():
            continue
        (snapshot_data_dir / data_path.name).write_text(data_path.read_text(encoding="utf-8"), encoding="utf-8")

    return {"html_path": html_path, "data_dir": snapshot_data_dir}


# AI 브리핑의 [매체명] 인용을 수집 기사 URL로 자동 링크하기 위한 유틸.
_CITE_PATTERN = re.compile(r"\[([^\]\[\n]{1,40})\]")

# 약어 ↔ 풀네임 alias — 키는 casefold + 공백 제거된 형태. AI가 [THR]처럼 약어로 인용해도
# articles의 풀네임(예: "The Hollywood Reporter")으로 매칭되도록.
_SOURCE_ALIASES: dict[str, str] = {
    "thr": "The Hollywood Reporter",
    "wsj": "Wall Street Journal",
    "nyt": "New York Times",
    "ft": "Financial Times",
    "lat": "Los Angeles Times",
    "wp": "Washington Post",
}


def _build_source_link_map(*data_groups) -> dict[str, dict]:
    """여러 데이터 풀(articles/community/market_trends/policies)에서 매체별 대표 URL 맵.

    같은 매체에 여러 항목이 있으면 score 최대(없으면 0)로 1건을 대표 링크로.
    AI가 어떤 항목을 인용했는지 직접 알 수 없으므로 "그 매체 가장 비중 있는 항목"으로 연결.
    """
    by_source: dict[str, dict] = {}
    for group in data_groups:
        for a in group or []:
            if not isinstance(a, dict):
                continue
            src = str(a.get("source") or "").strip()
            url = a.get("url")
            if not src or not url:
                continue
            score = float(a.get("score") or 0)
            existing = by_source.get(src)
            if existing is None or score > existing["score"]:
                by_source[src] = {
                    "url": url,
                    "score": score,
                    "title": a.get("ko_title") or a.get("title") or "",
                }
    return by_source


def _linkify_citations(text: str, source_map: dict[str, dict]) -> str:
    """텍스트의 [매체명] 패턴을 HTML 링크로 치환. 안전하게 escape 후 변환."""
    if not text:
        return ""
    escaped = _html.escape(text)

    def _repl(m):
        src = m.group(1).strip()
        entry = source_map.get(src)
        if entry is None:
            # 대소문자/공백 무시 대조 — '[The Hollywood Reporter]' 같은 변형 흡수
            target = src.casefold().replace(" ", "")
            for key, val in source_map.items():
                if key.casefold().replace(" ", "") == target:
                    entry = val
                    break
            # 약어 alias 처리 — [THR] → "The Hollywood Reporter"로 변환 후 재시도
            if entry is None and target in _SOURCE_ALIASES:
                full_target = _SOURCE_ALIASES[target].casefold().replace(" ", "")
                for key, val in source_map.items():
                    if key.casefold().replace(" ", "") == full_target:
                        entry = val
                        break
        if not entry:
            return f"[{_html.escape(src)}]"
        return (
            f'<a class="ai-cite" href="{_html.escape(entry["url"])}" '
            f'target="_blank" rel="noopener" title="{_html.escape(entry["title"])}">'
            f"[{_html.escape(src)}]</a>"
        )

    return _CITE_PATTERN.sub(_repl, escaped)


def _enrich_briefing_with_links(briefing: dict, *data_groups) -> None:
    """AI 브리핑의 각 텍스트 필드 옆에 *_html 필드를 채워 출처 링크를 단다.

    원 텍스트 필드는 유지(다른 곳에서 plain 사용 가능). 템플릿은 *_html|safe로 출력.
    data_groups에 articles/community/market_trends/policies 등 모든 출처 풀을 넘기면
    [매체명] 인용을 그 매체 가장 비중 있는 항목으로 연결한다.
    """
    if not isinstance(briefing, dict):
        return
    smap = _build_source_link_map(*data_groups)
    L = _linkify_citations

    briefing["headline_today_html"] = L(briefing.get("headline_today", ""), smap)
    briefing["summary_html"] = L(briefing.get("summary", ""), smap)

    for own in briefing.get("own_titles") or []:
        own["highlights_html"] = [L(h, smap) for h in own.get("highlights") or []]
        own["risks_html"] = [L(r, smap) for r in own.get("risks") or []]
    for c in briefing.get("competitors") or []:
        c["note_html"] = L(c.get("note", ""), smap)
    for t in briefing.get("new_trends") or []:
        t["note_html"] = L(t.get("note", ""), smap)
        t["implication_html"] = L(t.get("implication", ""), smap)
    for s in briefing.get("industry_signals") or []:
        s["note_html"] = L(s.get("note", ""), smap)
        s["implication_html"] = L(s.get("implication", ""), smap)
    for o in briefing.get("overseas_brief") or []:
        o["summary_ko_html"] = L(o.get("summary_ko", ""), smap)
        o["implication_html"] = L(o.get("implication", ""), smap)


def build() -> None:
    now = datetime.now(timezone.utc)
    raw_articles = load_json(ARTICLES_PATH, [])
    raw_community = load_json(COMMUNITY_PATH, [])
    raw_policies = load_json(POLICIES_PATH, [])
    raw_market_trends = load_json(MARKET_TRENDS_PATH, [])
    raw_market = load_json(MARKET_PATH, {})
    raw_reservation = load_json(RESERVATION_PATH, {})
    raw_overseas_weekend = load_json(OVERSEAS_WEEKEND_PATH, {})

    article_views = [to_article_view(article, now) for article in raw_articles]
    official_articles, community_from_articles = split_articles_by_kind(article_views)
    official_feed = select_official_feed(official_articles)
    community_reactions = [to_community_view(item, now) for item in raw_community]
    community_views = community_from_articles + community_reactions
    policy_views = [to_policy_view(item, now) for item in raw_policies]
    market_trends = market_trend_views(raw_market_trends, now)
    market_trend_sections = build_market_trend_sections(market_trends)
    priority_community_titles = [
        str(movie.get("title") or "")
        for movie in (raw_reservation.get("movies") or [])
        if isinstance(movie, dict) and movie.get("is_lotte_distributed")
    ]
    community_sections = build_community_sections(
        community_views,
        priority_titles=priority_community_titles,
    )
    boxoffice = market_views(raw_market)
    reservation = reservation_view(raw_reservation)
    overseas_weekend = overseas_weekend_view(raw_overseas_weekend)
    boxoffice_engagement = build_movie_engagement(boxoffice, official_articles, community_views)
    reservation_engagement = build_movie_engagement(reservation["movies"], official_articles, community_views)
    curation = top_curation_items(
        official_articles,
        community_views,
        policy_views,
        market_titles=[movie["title"] for movie in boxoffice],
        reservation_titles=[movie["title"] for movie in reservation["movies"]],
        overseas_titles=[movie["title"] for movie in overseas_weekend["movies"]],
    )
    curation_sections = build_curation_sections(
        official_articles,
        policy_views=policy_views,
        market_titles=[movie["title"] for movie in boxoffice],
        reservation_titles=[movie["title"] for movie in reservation["movies"]],
        overseas_titles=[movie["title"] for movie in overseas_weekend["movies"]],
        ai_command=os.environ.get("CORE_CURATION_AI_CMD"),
    )
    # 전체 수집 아카이브(검색 전용): 노출은 큐레이션/커뮤니티 섹션이 그대로 담당하되,
    # 키워드 검색 시에는 수집된 기사·커뮤니티 '전부'가 잡히도록 별도 숨김 목록으로 렌더한다.
    archive_official = sorted(official_articles, key=lambda v: v.get("score") or 0, reverse=True)
    archive_community = community_views

    # AI 브리핑(임원용): briefing.bat 또는 'python -m crawler.ai_briefing'로 갱신.
    # 파일이 없으면 패널은 표시되지 않는다(템플릿이 분기 처리).
    ai_briefing = load_json(DATA_DIR / "ai_briefing.json", None)
    if isinstance(ai_briefing, dict) and ai_briefing.get("generated_at"):
        try:
            gen_utc = datetime.fromisoformat(ai_briefing["generated_at"])
            if gen_utc.tzinfo is None:
                gen_utc = gen_utc.replace(tzinfo=timezone.utc)
            ai_briefing["generated_at_kst"] = (
                gen_utc.astimezone(KST).strftime("%Y.%m.%d %H:%M KST")
            )
        except (ValueError, TypeError):
            ai_briefing["generated_at_kst"] = ""
    # 본문 [매체명] 인용을 수집 기사 URL로 자동 링크 — articles 외에
    # community/market_trends/policies까지 매핑 풀에 포함해야 [익스트림무비],
    # [IT조선], [영화진흥위원회] 등 비-articles 출처도 링크된다.
    if isinstance(ai_briefing, dict):
        _enrich_briefing_with_links(
            ai_briefing,
            official_articles,
            raw_community,
            raw_market_trends,
            raw_policies,
        )

    env = Environment(loader=FileSystemLoader(str(SITE_DIR)), autoescape=True)
    template = env.get_template("template.html.j2")
    css = (SITE_DIR / "style.css").read_text(encoding="utf-8")

    html = strip_trailing_whitespace(template.render(
        official_articles=official_articles,
        official_feed=official_feed,
        community_reactions=community_views,
        community_sections=community_sections,
        policy_items=policy_views,
        market_trends=market_trends,
        market_trend_sections=market_trend_sections,
        curation=curation,
        curation_sections=curation_sections,
        archive_official=archive_official,
        archive_community=archive_community,
        archive_total=len(archive_official) + len(archive_community),
        ai_briefing=ai_briefing,
        boxoffice=boxoffice,
        reservation=reservation,
        overseas_weekend=overseas_weekend,
        boxoffice_engagement=boxoffice_engagement,
        reservation_engagement=reservation_engagement,
        total_official=len(official_feed),
        total_community=len(community_views),
        total_policies=len(policy_views),
        total_market_trends=len(market_trends),
        css=css,
        updated_at=now.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M"),
    ))

    DIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    DIST_PATH.write_text(html, encoding="utf-8")
    archive = write_archive_snapshot(html, now)
    print(
        f"Built {DIST_PATH} "
        f"(official {len(official_articles)} · community {len(community_views)} · policies {len(policy_views)})"
    )
    print(f"Archived {archive['html_path']} and {archive['data_dir']}")


if __name__ == "__main__":
    build()
