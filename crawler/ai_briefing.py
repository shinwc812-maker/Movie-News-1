"""임원용 AI 브리핑 생성 — claude -p로 호출하여 추가 비용 없이 진행.

사용:
    python -m crawler.ai_briefing

전제:
    - 환경에 `claude` CLI가 설치·인증돼 있어야 한다 (Claude Code).
    - data/articles.json·community.json·market.json·… 가 이미 갱신돼 있어야 한다.
      (즉, 크롤러 또는 GitHub Actions의 자동 갱신 이후에 호출)

운영 흐름:
    GitHub Actions(매일) — 데이터 갱신만, 이 모듈은 호출 안 함
    로컬 briefing.bat 또는 Claude Code 세션에서 명령 → 이 모듈 실행
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from crawler.lotte_priority import classify_movie, kind_label, load_priority_config

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BRIEFING_PATH = DATA_DIR / "ai_briefing.json"

# claude -p 호출 한도 — 너무 길면 timeout, 너무 짧으면 응답 미완.
CLAUDE_TIMEOUT_SEC = 180
# 입력 토큰 절약: 기사·커뮤니티는 핵심 필드만, 본문은 잘라 사용.
MAX_OFFICIAL_FOR_AI = 60
MAX_COMMUNITY_FOR_AI = 30
EXCERPT_CAP = 220


def _load(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _clip(text: str, cap: int = EXCERPT_CAP) -> str:
    text = (text or "").strip()
    if len(text) <= cap:
        return text
    return text[: cap - 1] + "…"


def _movie_brief(movie: dict, config: dict) -> dict:
    """KOBIS 영화 dict에서 AI 입력용 간략 정보를 추린다."""
    title = movie.get("title", "")
    kind = classify_movie(
        title,
        bool(movie.get("is_lotte_distributed")),
        config=config,
    )
    return {
        "rank": movie.get("rank"),
        "title": title,
        "open_date": movie.get("open_date", ""),
        "audi_count": movie.get("audi_count"),
        "audi_acc": movie.get("audi_acc"),
        "audi_inten": movie.get("audi_inten"),
        "audi_change": movie.get("audi_change"),
        "seat_share": movie.get("seat_share"),
        "seat_sales_rate": movie.get("seat_sales_rate"),
        "distributors": movie.get("distributors") or [],
        "lotte_kind": kind,            # 'lotte_distrib' / 'paramount_lotte' / None …
        "lotte_label": kind_label(kind),  # '롯데 배급' 등 (자사 아니면 '')
    }


def _article_brief(article: dict) -> dict:
    return {
        "id": article.get("id", ""),
        "source": article.get("source", ""),
        "country": article.get("country", ""),
        "title": article.get("title_ko") or article.get("title", ""),
        "summary": _clip(article.get("summary_ko") or article.get("summary", "")),
        "url": article.get("url", ""),
        "matched_keywords": (article.get("matched_keywords") or [])[:5],
        "score": article.get("score") or 0,
    }


def _community_brief(item: dict) -> dict:
    return {
        "source": item.get("source", ""),
        "title": item.get("title", ""),
        "excerpt": _clip(item.get("excerpt", "")),
        "mood": item.get("mood_summary", ""),
        "url": item.get("url", ""),
        "matched_keywords": (item.get("matched_keywords") or [])[:5],
    }


def build_input_payload() -> dict:
    """AI에 넘길 입력 데이터(JSON)를 조립."""
    config = load_priority_config()
    market = _load(DATA_DIR / "market.json", {})
    reservation = _load(DATA_DIR / "reservation.json", {})
    overseas = _load(DATA_DIR / "overseas_weekend.json", {})
    articles = _load(DATA_DIR / "articles.json", [])
    community = _load(DATA_DIR / "community.json", [])
    # 디시인사이드는 워딩이 공격적이라 AI 브리핑 입력에서 제외 (대시보드 패널에는 그대로 노출)
    community = [c for c in community if c.get("source") != "디시인사이드"]
    market_trends = _load(DATA_DIR / "market_trends.json", [])
    policies = _load(DATA_DIR / "policies.json", [])
    previous = _load(BRIEFING_PATH, None)  # 어제 브리핑 — '달라진 것' 비교에 사용

    # 기사 — 점수 상위 우선, 한국/해외 모두 포함
    sorted_articles = sorted(
        articles, key=lambda a: float(a.get("score") or 0), reverse=True
    )[:MAX_OFFICIAL_FOR_AI]

    return {
        "today_kst": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M"),
        "boxoffice_top5": [
            _movie_brief(m, config) for m in (market.get("movies") or [])[:5]
        ],
        "reservation_top5": [
            _movie_brief(m, config) for m in (reservation.get("movies") or [])[:5]
        ],
        "overseas_weekend_top5": [
            {
                "rank": m.get("rank"),
                "title": m.get("title", ""),
                "gross": m.get("gross"),
                "url": m.get("url", ""),
            }
            for m in (overseas.get("movies") or [])[:5]
        ],
        "articles": [_article_brief(a) for a in sorted_articles],
        "community": [_community_brief(c) for c in (community or [])[:MAX_COMMUNITY_FOR_AI]],
        "market_trends": market_trends,
        "policies": policies[:10] if isinstance(policies, list) else [],
        "previous_briefing": previous,  # 어제 것 (없으면 None)
    }


PROMPT_INSTRUCTION = """당신은 롯데컬처웍스 컨텐츠사업부 임원에게 매일 아침 영화·문화 산업 동향을 보고하는 분석가입니다. 아래 JSON 데이터(KOBIS 박스오피스, 수집 기사, 커뮤니티 반응, 시장동향, 정책)를 토대로 '오늘의 AI 브리핑'을 작성하세요.

【제약 — 매우 중요】
1. 추측·단정 금지. 데이터에서 직접 확인되는 수치·표현만 사용한다. "손익분기 안정권 진입" 같은 추정은 금지. "누적 X만 — KOBIS 기준"처럼 출처와 수치만 적는다.
2. 모든 주장 옆에 출처 키워드를 [매체명] 또는 [KOBIS] 형식으로 짧게 표기한다. URL은 응답에 넣지 않는다(URL은 별도 source_url 필드).
3. 자사(롯데) 작품과 경쟁작을 명확히 분리한다. 자사 판정은 입력 데이터의 lotte_kind/lotte_label을 그대로 사용한다(임의 추가 금지).
4. headline_today에 '어제 대비 무엇이 달라졌는가'를 한 줄로 적는다. previous_briefing이 null이면 '첫 브리핑'이라고 적는다.
5. 응답은 아래 JSON 스키마 그대로의 단일 JSON 객체로만 반환한다. 코드펜스(```json) 안에 넣어도 좋다. 설명 문장·인사말 금지.

【출력 JSON 스키마】
{
  "headline_today": "어제 대비 핵심 변화 한 줄",
  "summary": "전체 요약 2~4문장 — 시장 전반",
  "own_titles": [
    {
      "title": "와일드 씽",
      "kind_label": "롯데 배급",
      "highlights": ["요약 포인트1 [출처]", "요약 포인트2 [출처]"],
      "risks": ["리스크 한 줄 [출처]"]
    }
  ],
  "competitors": [
    {
      "title": "군체",
      "distributor": "쇼박스",
      "note": "수치/맥락 한 줄 [KOBIS]",
      "sources": ["매체명1", "매체명2"]
    }
  ],
  "new_trends": [
    {"label": "이머시브 뮤지컬", "note": "한 줄 요약 [매체명]", "implication": "자사 사업 연계 시사점(있을 때만)"}
  ],
  "industry_signals": [
    {"label": "K-콘텐츠", "note": "한 줄 [매체명]", "implication": "시사점(선택)"}
  ],
  "overseas_brief": [
    {"title_ko": "Variety 기사 한글 제목", "summary_ko": "1-2문장", "implication": "국내·자사 시사점 (선택)", "source": "Variety", "source_url": "https://..."}
  ]
}

own_titles는 입력 boxoffice/reservation에서 lotte_kind가 비어있지 않은 작품만 포함한다. 없으면 빈 배열.
competitors는 boxoffice/reservation TOP5 중 자사 아닌 작품 위주 3~5개.
overseas_brief는 articles 중 country='US' 항목 위주 3~5개.
new_trends/industry_signals은 market_trends·articles에서 임원 의사결정에 유의미한 것만 각 2~4개.
"""


def build_prompt(payload: dict) -> str:
    return (
        PROMPT_INSTRUCTION
        + "\n\n【입력 데이터(JSON)】\n```json\n"
        + json.dumps(payload, ensure_ascii=False, indent=1)
        + "\n```\n"
    )


def _resolve_claude_cli() -> str:
    """Windows에서 subprocess가 .cmd 래퍼를 못 찾는 문제를 피하려고 풀 경로로 해결.

    PATH 검색 → PATHEXT 등록(.CMD/.BAT) 포함. Linux/macOS는 그냥 'claude'.
    """
    cli = shutil.which("claude")
    if cli:
        return cli
    # Windows에서 npm 글로벌 설치 위치를 보강 검사
    if os.name == "nt":
        for candidate in ("claude.cmd", "claude.exe", "claude.bat"):
            found = shutil.which(candidate)
            if found:
                return found
    raise RuntimeError(
        "claude CLI를 찾을 수 없습니다. Claude Code가 설치/PATH에 있는지 확인하세요."
    )


def call_claude(prompt: str, timeout: int = CLAUDE_TIMEOUT_SEC) -> str:
    """claude -p에 stdin으로 prompt를 보내고 stdout 텍스트를 받는다."""
    cli = _resolve_claude_cli()
    try:
        result = subprocess.run(
            [cli, "-p"],
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "claude CLI를 찾을 수 없습니다. Claude Code가 설치/PATH에 있는지 확인하세요."
        ) from exc
    if result.returncode != 0:
        raise RuntimeError(
            f"claude -p 실패 (exit {result.returncode}): {result.stderr.strip()[:500]}"
        )
    return result.stdout


_JSON_BLOCK_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)
_RAW_JSON_RE = re.compile(r"(\{[\s\S]*\})", re.S)


def parse_briefing(text: str) -> dict:
    """응답 텍스트에서 JSON 객체를 추출. 코드펜스 → raw JSON 순으로 시도."""
    text = text or ""
    block = _JSON_BLOCK_RE.search(text)
    if block:
        candidate = block.group(1)
    else:
        raw = _RAW_JSON_RE.search(text)
        if not raw:
            raise ValueError("응답에서 JSON 객체를 찾지 못했습니다.")
        candidate = raw.group(1)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 파싱 실패: {exc}") from exc


def generate_briefing() -> dict:
    """전체 파이프라인: 입력 조립 → claude -p → 파싱 → 저장."""
    payload = build_input_payload()
    prompt = build_prompt(payload)
    print(f"[ai_briefing] claude -p 호출 (입력 {len(prompt):,}자)…", file=sys.stderr)
    response = call_claude(prompt)
    briefing = parse_briefing(response)
    briefing["generated_at"] = datetime.now(timezone.utc).isoformat()
    briefing["model"] = "claude-code (claude -p)"
    BRIEFING_PATH.parent.mkdir(parents=True, exist_ok=True)
    BRIEFING_PATH.write_text(
        json.dumps(briefing, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[ai_briefing] 저장: {BRIEFING_PATH}", file=sys.stderr)
    return briefing


if __name__ == "__main__":
    try:
        generate_briefing()
    except Exception as exc:  # noqa: BLE001
        print(f"[ai_briefing] 실패: {exc}", file=sys.stderr)
        sys.exit(1)
