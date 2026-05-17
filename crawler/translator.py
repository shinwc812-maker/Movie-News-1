"""영문 기사 한국어 번역 (Claude API).

country=="US" 기사의 title/summary를 한국어로 번역한다.

- 모델: claude-haiku-4-5-20251001
- 결과는 data/translations.json에 캐싱 (article_id → {title_ko, summary_ko})
- 이미 캐시에 있으면 재번역하지 않음
- 10개씩 배치로 묶어 JSON 입력 → JSON 출력으로 받아 파싱
- 배치 파싱/호출 실패 시 해당 배치만 스킵하고 다음 배치 진행
- ANTHROPIC_API_KEY는 환경 변수에서 읽음 (미설정 시 번역 건너뜀)
"""

import json
import os
import sys
from pathlib import Path

import anthropic

from crawler.models import Article

MODEL = "claude-haiku-4-5-20251001"
BATCH_SIZE = 10
SUMMARY_MAX_CHARS = 500          # 토큰 절약: 긴 요약은 앞 500자만 번역
MAX_TOKENS = 4096

TRANSLATIONS_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "translations.json"
)

SYSTEM_PROMPT = (
    "영화 산업 전문 번역가다. 제목과 요약을 자연스러운 한국어로 번역하라. "
    "영화 제목은 한국 개봉명이 있으면 그것을 쓰고, 없으면 원제 그대로. "
    "인명은 한국에서 통용되는 표기로."
)


def load_cache(path: Path = TRANSLATIONS_PATH) -> dict:
    """번역 캐시를 로드한다. 파일이 없거나 깨졌으면 빈 dict."""
    if path.exists():
        try:
            with path.open(encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[warn] translator: 캐시 로드 실패 — {exc}", file=sys.stderr)
    return {}


def save_cache(cache: dict, path: Path = TRANSLATIONS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _strip_code_fence(text: str) -> str:
    """모델 출력에 ```json ... ``` 펜스가 있으면 제거."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


def _translate_batch(client: "anthropic.Anthropic", batch: list[Article]) -> dict:
    """한 배치를 번역해 {id: {title_ko, summary_ko}}를 반환. 실패 시 빈 dict."""
    payload = [
        {
            "id": a.id,
            "title": a.title,
            "summary": a.summary[:SUMMARY_MAX_CHARS],
        }
        for a in batch
    ]
    user_message = (
        "다음 영화 뉴스 기사들을 한국어로 번역하라. "
        "각 기사의 id는 그대로 두고 title_ko, summary_ko를 채워라.\n"
        "출력은 오직 JSON 배열만. 다른 설명이나 마크다운 코드펜스 없이 "
        '다음 형식의 JSON 배열만 출력하라:\n'
        '[{"id": "...", "title_ko": "...", "summary_ko": "..."}]\n\n'
        "입력:\n" + json.dumps(payload, ensure_ascii=False)
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            # 시스템 프롬프트는 모든 배치에서 동일 → 프롬프트 캐싱 대상으로 표시
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIError as exc:
        print(f"[warn] translator: API 호출 실패 — {exc}", file=sys.stderr)
        return {}

    if response.stop_reason == "max_tokens":
        print("[warn] translator: max_tokens 도달 — 배치 스킵", file=sys.stderr)
        return {}

    raw = next((b.text for b in response.content if b.type == "text"), "")
    try:
        items = json.loads(_strip_code_fence(raw))
        result = {}
        for item in items:
            result[item["id"]] = {
                "title_ko": item["title_ko"],
                "summary_ko": item["summary_ko"],
            }
        return result
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"[warn] translator: 응답 파싱 실패 — {exc} — 배치 스킵",
              file=sys.stderr)
        return {}


def translate_articles(articles: list[Article]) -> None:
    """US 기사들을 한국어로 번역하고 title_ko/summary_ko를 in-place로 채운다."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[warn] translator: ANTHROPIC_API_KEY 미설정 — 번역 건너뜀",
              file=sys.stderr)
        return

    cache = load_cache()
    us_articles = [a for a in articles if a.country == "US"]
    to_translate = [a for a in us_articles if a.id not in cache]

    if to_translate:
        client = anthropic.Anthropic()
        for batch in _chunks(to_translate, BATCH_SIZE):
            translated = _translate_batch(client, batch)
            if translated:
                cache.update(translated)
                save_cache(cache)  # 배치마다 저장 → 중단돼도 진행분 보존

    # 캐시 내용을 기사 객체에 반영
    translated_count = 0
    for article in us_articles:
        entry = cache.get(article.id)
        if entry:
            article.title_ko = entry.get("title_ko")
            article.summary_ko = entry.get("summary_ko")
            translated_count += 1

    print(f"Translated {translated_count}/{len(us_articles)} US articles")
