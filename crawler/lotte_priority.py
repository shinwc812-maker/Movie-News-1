"""자사(롯데) 우선 작품 분류 — KOBIS distributor + 수동 yaml 매칭."""

from pathlib import Path
from typing import Optional

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "lotte_priority_titles.yaml"

# 우선순위가 높은 카테고리가 앞에 — 같은 작품이 여러 카테고리에 잡히면 첫 매칭 사용.
PRIORITY_ORDER = ("lotte_ip", "lotte_exclusive", "paramount_lotte")

# 화면 표시용 한글 라벨
KIND_LABELS = {
    "lotte_ip": "자사 IP",
    "lotte_exclusive": "롯데 단독상영",
    "paramount_lotte": "파라마운트(롯데 배급)",
    "lotte_distrib": "롯데 배급",
}


def _compact(text: str) -> str:
    return "".join(str(text or "").casefold().split())


def load_priority_config(path: Path = CONFIG_PATH) -> dict[str, list[str]]:
    """yaml에서 카테고리별 작품 제목 리스트를 로드. 비어 있으면 빈 dict 반환."""
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}
    return {
        key: [str(title).strip() for title in (data.get(key) or []) if str(title).strip()]
        for key in PRIORITY_ORDER
    }


def classify_movie(
    title: str,
    is_lotte_distributed: bool,
    config: Optional[dict[str, list[str]]] = None,
) -> Optional[str]:
    """영화 한 편의 자사 분류 카테고리를 반환. 자사 아님이면 None.

    우선순위:
      1. config의 lotte_ip → 'lotte_ip'
      2. config의 lotte_exclusive → 'lotte_exclusive'
      3. config의 paramount_lotte → 'paramount_lotte'
      4. is_lotte_distributed(KOBIS) → 'lotte_distrib'
      5. 위 모두 미해당 → None
    """
    if config is None:
        config = load_priority_config()
    compact_title = _compact(title)
    if not compact_title:
        return "lotte_distrib" if is_lotte_distributed else None

    for kind in PRIORITY_ORDER:
        for entry in config.get(kind, []):
            compact_entry = _compact(entry)
            if not compact_entry:
                continue
            # 정확 일치 또는 어느 한쪽이 다른 쪽을 포함(부제 등 차이 흡수)
            if (
                compact_title == compact_entry
                or compact_entry in compact_title
                or compact_title in compact_entry
            ):
                return kind

    if is_lotte_distributed:
        return "lotte_distrib"
    return None


def kind_label(kind: Optional[str]) -> str:
    """분류 코드를 화면 표시용 한글 라벨로 변환."""
    if not kind:
        return ""
    return KIND_LABELS.get(kind, kind)
