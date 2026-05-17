"""정적 사이트 생성: data/articles.json → dist/index.html.

상대 시간(KST)은 여기서 미리 계산해 템플릿에 넘긴다(JS 의존 최소화).
언어 토글만 클라이언트 JS로 처리한다.
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

# tier 번호 → (이모지, 섹션 제목)
TIER_META = {
    1: ("🏢", "롯데 관련"),
    2: ("🎬", "파라마운트 배급 관련"),
    3: ("📦", "기타 배급사"),
    4: ("🎨", "일반 문화예술"),
}


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
        "tier": article.get("tier", 4),
        "country": article.get("country", ""),
        "source": article.get("source", ""),
        "url": article.get("url", ""),
        "image_url": article.get("image_url"),
        "matched_keywords": article.get("matched_keywords") or [],
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

    views = [to_view(a, now) for a in raw_articles]

    tiers = []
    for tier_num in (1, 2, 3, 4):
        emoji, label = TIER_META[tier_num]
        tiers.append({
            "num": tier_num,
            "emoji": emoji,
            "label": label,
            "articles": [v for v in views if v["tier"] == tier_num],
        })

    env = Environment(
        loader=FileSystemLoader(str(SITE_DIR)),
        autoescape=True,
    )
    template = env.get_template("template.html.j2")
    css = (SITE_DIR / "style.css").read_text(encoding="utf-8")

    html = template.render(
        tiers=tiers,
        css=css,
        total=len(views),
        updated_at=now.astimezone(KST).strftime("%Y년 %m월 %d일 %H:%M"),
    )

    DIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    DIST_PATH.write_text(html, encoding="utf-8")
    print(f"Built {DIST_PATH} ({len(views)} articles)")


if __name__ == "__main__":
    build()
