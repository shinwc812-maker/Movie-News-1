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
SITE_DIR = ROOT / "site"
DIST_DIR = ROOT / "dist"
DIST_PATH = DIST_DIR / "index.html"
KST = ZoneInfo("Asia/Seoul")
LEGACY_COMMUNITY_SOURCES = {"익스트림무비"}


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


def top_curation_items(
    official_views: list[dict],
    community_views: list[dict] | None = None,
    limit: int = 5,
    max_overseas_official: int = 2,
) -> list[dict]:
    community_views = community_views or []
    overseas_count = 0
    capped_official: list[dict] = []
    for item in official_views:
        is_overseas = bool(item.get("country")) and item.get("country") != "KR"
        if is_overseas and overseas_count >= max_overseas_official:
            continue
        if is_overseas:
            overseas_count += 1
        capped_official.append(item)
    items = capped_official + list(community_views)
    return sorted(items, key=lambda item: float(item.get("score") or 0), reverse=True)[:limit]


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


def strip_trailing_whitespace(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.splitlines()) + "\n"


def build() -> None:
    now = datetime.now(timezone.utc)
    raw_articles = load_json(ARTICLES_PATH, [])
    raw_community = load_json(COMMUNITY_PATH, [])
    raw_policies = load_json(POLICIES_PATH, [])
    raw_market = load_json(MARKET_PATH, {})
    raw_reservation = load_json(RESERVATION_PATH, {})

    article_views = [to_article_view(article, now) for article in raw_articles]
    official_articles, community_from_articles = split_articles_by_kind(article_views)
    official_feed = select_official_feed(official_articles)
    community_reactions = [to_community_view(item, now) for item in raw_community]
    community_views = community_from_articles + community_reactions
    policy_views = [to_policy_view(item, now) for item in raw_policies]
    boxoffice = market_views(raw_market)
    reservation = reservation_view(raw_reservation)
    curation = top_curation_items(official_articles, community_views)

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
