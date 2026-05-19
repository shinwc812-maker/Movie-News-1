"""Build the static internal movie/culture briefing dashboard."""

import json
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
SITE_DIR = ROOT / "site"
DIST_DIR = ROOT / "dist"
DIST_PATH = DIST_DIR / "index.html"
KST = ZoneInfo("Asia/Seoul")
LEGACY_COMMUNITY_SOURCES = {"익스트림무비"}
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
    "영화관람",
    "관람 활성화",
    "할인권",
    "독립예술영화",
    "국제공동제작",
    "상영",
    "배급",
)
OVERSEAS_CONTEXT_KEYWORDS = (
    "롯데배급",
    "롯데엔터테인먼트",
    "롯데컬처웍스",
    "Lotte Entertainment",
    "Lotte Cultureworks",
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
        "content_kind": "policy",
        "source": item.get("source", ""),
        "category": item.get("category", ""),
        "title": item.get("title", ""),
        "url": item.get("url", ""),
        "summary": item.get("summary", ""),
        "rel_time": relative_time(item.get("published_at"), now),
        "deadline": item.get("deadline"),
    }


def split_articles_by_kind(views: list[dict]) -> tuple[list[dict], list[dict]]:
    official = [view for view in views if view.get("content_kind", "official") == "official"]
    community = [view for view in views if view.get("content_kind") == "community"]
    return official, community


def _compact_match_text(text: str) -> str:
    return "".join((text or "").casefold().split())


def _matched_title(item: dict, titles: list[str]) -> bool:
    matched = item.get("matched_keywords") or []
    matched_compact = {_compact_match_text(keyword) for keyword in matched if keyword}
    return any(_compact_match_text(title) in matched_compact for title in titles if title)


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
    max_community_items: int = 2,
    max_policy_items: int = 1,
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
        is_overseas = bool(item.get("country")) and item.get("country") != "KR"
        if is_overseas and overseas_count >= max_overseas_official:
            continue
        if is_overseas:
            overseas_count += 1
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def select_official_feed(
    official_views: list[dict],
    limit: int = 12,
    max_overseas: int = 4,
) -> list[dict]:
    korean = [view for view in official_views if view.get("country") == "KR"]
    overseas = [view for view in official_views if view.get("country") != "KR"]
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
        seat_count = int(movie.get("seat_count") or 0)
        view = {
            "rank": movie.get("rank"),
            "title": movie.get("title", ""),
            "open_date": movie.get("open_date", ""),
            "audi_count": format_int(movie.get("audi_count")),
            "audi_acc": format_int(movie.get("audi_acc")),
            "audi_delta": format_audience_delta(audi_inten, audi_change),
            "audi_delta_short": format_audience_delta(audi_inten, include_rate=False),
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


def build() -> None:
    now = datetime.now(timezone.utc)
    raw_articles = load_json(ARTICLES_PATH, [])
    raw_community = load_json(COMMUNITY_PATH, [])
    raw_policies = load_json(POLICIES_PATH, [])
    raw_market = load_json(MARKET_PATH, {})
    raw_reservation = load_json(RESERVATION_PATH, {})
    raw_overseas_weekend = load_json(OVERSEAS_WEEKEND_PATH, {})

    article_views = [to_article_view(article, now) for article in raw_articles]
    official_articles, community_from_articles = split_articles_by_kind(article_views)
    official_feed = select_official_feed(official_articles)
    community_reactions = [to_community_view(item, now) for item in raw_community]
    community_views = community_from_articles + community_reactions
    policy_views = [to_policy_view(item, now) for item in raw_policies]
    boxoffice = market_views(raw_market)
    reservation = reservation_view(raw_reservation)
    overseas_weekend = overseas_weekend_view(raw_overseas_weekend)
    curation = top_curation_items(
        official_articles,
        community_views,
        policy_views,
        market_titles=[movie["title"] for movie in boxoffice],
        reservation_titles=[movie["title"] for movie in reservation["movies"]],
        overseas_titles=[movie["title"] for movie in overseas_weekend["movies"]],
    )

    env = Environment(loader=FileSystemLoader(str(SITE_DIR)), autoescape=True)
    template = env.get_template("template.html.j2")
    css = (SITE_DIR / "style.css").read_text(encoding="utf-8")

    html = strip_trailing_whitespace(template.render(
        official_articles=official_articles,
        official_feed=official_feed,
        community_reactions=community_views,
        policy_items=policy_views,
        curation=curation,
        boxoffice=boxoffice,
        reservation=reservation,
        overseas_weekend=overseas_weekend,
        total_official=len(official_feed),
        total_community=len(community_views),
        total_policies=len(policy_views),
        css=css,
        updated_at=now.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M"),
    ))

    DIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    DIST_PATH.write_text(html, encoding="utf-8")
    print(
        f"Built {DIST_PATH} "
        f"(official {len(official_articles)} · community {len(community_views)} · policies {len(policy_views)})"
    )


if __name__ == "__main__":
    build()
