"""KOFIC(KOBIS) 일별 박스오피스 TOP N 영화명 조회.

뉴스 소스가 아니라 채점 보조 데이터다. '현재 흥행작' = 시의성 높은 기사라는
신호로, 박스오피스에 오른 영화명이 기사에 등장하면 가점을 준다(scorer 참조).

- 자격증명: 환경변수 ``KOFIC_API_KEY`` (미설정 시 빈 리스트 → 가점 없이 진행)
- 어제(KST) 기준 일별 박스오피스 조회 (당일 집계는 다음날 제공되므로 전날을 본다)
- 키 오류·네트워크 실패·형식 이상 시 모두 빈 리스트 (전체 파이프라인을 막지 않음)
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import httpx

from crawler.sources.base import REQUEST_TIMEOUT, USER_AGENT

API_URL = (
    "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
    "boxoffice/searchDailyBoxOfficeList.json"
)
KST = ZoneInfo("Asia/Seoul")
TOP_N = 10


def fetch_boxoffice_titles(now: Optional[datetime] = None) -> list[str]:
    """어제(KST) 일별 박스오피스 TOP N 영화명 리스트를 반환. 실패 시 []."""
    key = os.environ.get("KOFIC_API_KEY")
    if not key:
        print("[warn] 박스오피스: KOFIC_API_KEY 미설정 — 가점 건너뜀", file=sys.stderr)
        return []

    if now is None:
        now = datetime.now(KST)
    target = (now.astimezone(KST) - timedelta(days=1)).strftime("%Y%m%d")

    params = {"key": key, "targetDt": target, "itemPerPage": str(TOP_N)}
    try:
        resp = httpx.get(
            API_URL,
            params=params,
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001 — 박스오피스 실패가 전체를 멈추면 안 됨
        print(f"[warn] 박스오피스: 조회 실패 — {exc}", file=sys.stderr)
        return []

    # KOFIC은 키/요청 오류 시 faultInfo로 응답한다.
    if isinstance(data, dict) and "faultInfo" in data:
        msg = data.get("faultInfo", {}).get("message", "")
        print(f"[warn] 박스오피스: API 오류 — {msg}", file=sys.stderr)
        return []

    try:
        rows = data["boxOfficeResult"]["dailyBoxOfficeList"]
    except (KeyError, TypeError):
        print("[warn] 박스오피스: 예상치 못한 응답 형식 — 가점 건너뜀", file=sys.stderr)
        return []

    titles = [
        name
        for row in rows
        if (name := (row.get("movieNm") or "").strip())
    ]
    print(f"박스오피스 TOP {len(titles)} ({target}): {titles}")
    return titles
