"""정적 사이트 생성: data/articles.json → dist/index.html.

기사는 국내(KR)/해외(US) 두 탭으로 나눠 보여준다. 각 탭 안에서는 articles.json의
정렬 순서(점수 내림차순 = 우선순위 순)를 그대로 유지한다 — 우선순위 라벨은
표시하지 않고 순서로만 반영.
상대 시간(KST)은 빌드 시 미리 계산한다(JS 의존 최소화).
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
ARTICLES_PATH = ROOT / "data" / "articles.json"
SITE_DIR = ROOT / "site"
DIST_PATH = ROOT / "dist" / "index.html"
KST = ZoneInfo("Asia/Seoul")


def relative_time(published_iso: str, now: datetime) -> str:
    """ISO 발행 시각 → '2시간 전' 형식. 7일 이상이면 KST 절대 날짜."""
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


def to_view(article: dict, now: datetime) -> dict:
    """기사 dict → 템플릿용 view dict. 한/영 양쪽 텍스트를 모두 준비."""
    title = article.get("title") or ""
    summary = article.get("summary") or ""
    return {
        "country": article.get("country", ""),
        "source": article.get("source", ""),
        "url": article.get("url", ""),
        "image_url": article.get("image_url"),
        "rel_time": relative_time(article.get("published_at"), now),
        # 한국어 모드: 번역본이 있으면 그것, 없으면 원문 폴백
        "ko_title": article.get("title_ko") or title,
        "en_title": title,
        "ko_summary": article.get("summary_ko") or summary,
        "en_summary": summary,
    }


def build() -> None:
    now = datetime.now(timezone.utc)
    with ARTICLES_PATH.open(encoding="utf-8") as f:
        raw_articles = json.load(f)

    # articles.json은 점수(우선순위) 내림차순 정렬 상태 — 순서를 그대로 유지
    views = [to_view(a, now) for a in raw_articles]
    kr_articles = [v for v in views if v["country"] == "KR"]
    us_articles = [v for v in views if v["country"] == "US"]

    env = Environment(
        loader=FileSystemLoader(str(SITE_DIR)),
        autoescape=True,
    )
    template = env.get_template("template.html.j2")
    css = (SITE_DIR / "style.css").read_text(encoding="utf-8")

    html = template.render(
        kr_articles=kr_articles,
        us_articles=us_articles,
        total=len(views),
        css=css,
        updated_at=now.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M"),
    )

    DIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    DIST_PATH.write_text(html, encoding="utf-8")
    print(f"Built {DIST_PATH} (국내 {len(kr_articles)} · 해외 {len(us_articles)})")


if __name__ == "__main__":
    build()
