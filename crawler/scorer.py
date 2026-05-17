"""기사 우선순위 스코어링.

config/keywords.yaml의 배급사 키워드 매칭 + 최신성 보너스로 tier와 score를 산정한다.
"""

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from crawler.models import Article

KEYWORDS_PATH = Path(__file__).resolve().parent.parent / "config" / "keywords.yaml"


def load_keywords(path: Path = KEYWORDS_PATH) -> dict:
    """keywords.yaml을 로드해 dict로 반환."""
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


_MATCHER_CACHE: dict[str, re.Pattern] = {}


def _matcher(keyword: str) -> re.Pattern:
    """키워드용 정규식 매처를 생성/캐싱한다.

    - 영문·숫자(ASCII) 키워드: 단어 경계 매칭 — 'NEW'가 'news'에 오매칭되지 않게.
    - 한글 등 비ASCII 키워드: 그대로(부분 문자열) 비교.
    - 'NEW'/'CJ ENM'/'A24'처럼 전부 대문자인 약어·브랜드: 대소문자 구분 매칭 —
      영어 단어 'new' 등에 오매칭되는 것을 방지. 그 외에는 대소문자 무시.
    """
    cached = _MATCHER_CACHE.get(keyword)
    if cached is not None:
        return cached

    pattern = re.escape(keyword)
    if keyword.isascii():
        pattern = rf"(?<![A-Za-z0-9]){pattern}(?![A-Za-z0-9])"
    flags = 0 if keyword.isupper() else re.IGNORECASE
    cached = re.compile(pattern, flags)
    _MATCHER_CACHE[keyword] = cached
    return cached


def _find_matches(text: str, keywords: list[str]) -> list[str]:
    """text 안에서 매칭된 키워드를 반환 (영문은 단어 경계, 약어는 대소문자 구분)."""
    return [kw for kw in keywords if kw and _matcher(kw).search(text)]


def score_article(
    article: Article, keywords: dict, now: datetime
) -> tuple[int, float, list[str]]:
    """기사 하나의 (tier, score, matched_keywords)를 계산한다.

    tier는 매칭된 가장 높은 우선순위(숫자가 작을수록 우선), score는 누적 합산.
    """
    # 대소문자 구분 매칭(약어)을 위해 원문 그대로 사용 — 대소문자 무시는 정규식 플래그로 처리
    text = f"{article.title} {article.summary}"
    tier = 4
    score = 0.0
    matched: list[str] = []

    # Tier 1 — 롯데
    t1 = keywords.get("tier1_lotte", {})
    t1_hits = _find_matches(text, t1.get("keywords", []))
    if t1_hits:
        tier = 1
        score += t1.get("weight", 0)
        matched.extend(t1_hits)

    # Tier 2 — 파라마운트 (+ 배급 맥락 보너스)
    t2 = keywords.get("tier2_paramount", {})
    t2_hits = _find_matches(text, t2.get("keywords", []))
    if t2_hits:
        tier = min(tier, 2)
        score += t2.get("weight", 0)
        matched.extend(t2_hits)
        boost = t2.get("context_boost", {})
        boost_hits = _find_matches(text, boost.get("keywords", []))
        if boost_hits:
            score += boost.get("weight", 0)
            matched.extend(boost_hits)

    # Tier 3 — 기타 배급사 (매칭 개수 × weight)
    t3 = keywords.get("tier3_distributors", {})
    t3_hits = _find_matches(text, t3.get("keywords", []))
    if t3_hits:
        tier = min(tier, 3)
        score += len(t3_hits) * t3.get("weight", 0)
        matched.extend(t3_hits)

    # 최신성 보너스: 발행 후 hours_to_zero 시간까지 선형 감소
    recency = keywords.get("recency_boost", {})
    if article.published_at is not None:
        published = article.published_at
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        hours_old = max((now - published).total_seconds() / 3600, 0.0)
        hours_to_zero = recency.get("hours_to_zero", 0)
        max_bonus = recency.get("max_bonus", 0)
        if hours_to_zero and hours_old < hours_to_zero:
            score += max_bonus * (1 - hours_old / hours_to_zero)

    return tier, score, matched


def score_all(articles: list[Article], now: Optional[datetime] = None) -> None:
    """모든 기사에 tier/score/matched_keywords를 in-place로 채운다."""
    if now is None:
        now = datetime.now(timezone.utc)
    keywords = load_keywords()
    for article in articles:
        tier, score, matched = score_article(article, keywords, now)
        article.tier = tier
        article.score = score
        article.matched_keywords = matched
