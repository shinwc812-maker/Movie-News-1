"""네이버 일반 기사 표시 필터.

네이버 검색은 포털 전체에서 긁어와 노이즈(연예가십·정치·행정홍보·광고)가 섞인다.
영화/공연 신호가 강한 기사만 남기고 노이즈를 제거한다.

규칙(네이버 소스에만 적용, 다른 매체는 그대로 통과):
1. 배급사/박스오피스가 매칭된 기사(matched_keywords 보유)는 항상 유지 — 핵심 가치.
2. exclude_any 단어가 하나라도 있으면 제거 (정치·가십·행정 신호).
3. require_any 단어가 하나도 없으면 제거 (영화/공연 핵심 신호 부재).

require_any/exclude_any 목록은 config/sources.yaml의 naver.filter에서 조정한다.
설정이 비어 있으면 필터를 적용하지 않는다(전량 통과).
"""

import sys
from pathlib import Path

import yaml

from crawler.models import Article

CONFIG = Path(__file__).resolve().parent.parent / "config" / "sources.yaml"
TARGET_SOURCE = "네이버뉴스"


def _load_filter_config() -> dict:
    try:
        with CONFIG.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except OSError as exc:
        print(f"[warn] 표시 필터: 설정 로드 실패 — {exc}", file=sys.stderr)
        return {}
    return (data.get("naver") or {}).get("filter") or {}


def filter_naver(articles: list[Article]) -> list[Article]:
    """네이버 기사 중 영화/공연 관련만 남긴다. 다른 소스는 그대로 둔다."""
    cfg = _load_filter_config()
    require = cfg.get("require_any") or []
    exclude = cfg.get("exclude_any") or []
    if not require and not exclude:
        return articles

    kept: list[Article] = []
    dropped = 0
    for a in articles:
        if a.source != TARGET_SOURCE:
            kept.append(a)
            continue
        if a.matched_keywords:  # 배급사/박스오피스 매칭 → 항상 유지
            kept.append(a)
            continue
        text = f"{a.title} {a.summary}"
        if any(x in text for x in exclude):
            dropped += 1
            continue
        if require and not any(x in text for x in require):
            dropped += 1
            continue
        kept.append(a)

    print(f"네이버 표시 필터: {dropped}건 제외 → {len(kept)}건 유지", file=sys.stderr)
    return kept
