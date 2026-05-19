"""Film policy and public support notice collection."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import httpx
from selectolax.parser import HTMLParser

from crawler.briefing_models import PolicyItem
from crawler.sources.base import REQUEST_TIMEOUT, USER_AGENT, make_article_id

KST = ZoneInfo("Asia/Seoul")
KOFIC_BASE_URL = "https://www.kofic.or.kr"
KOFIC_BUSINESS_NOTICE_URL = (
    "https://www.kofic.or.kr/kofic/business/prom/promotionBoardList.do"
    "?mode=I&searchCategoryId=13061001"
)
KOCCA_BASE_URL = "https://www.kocca.kr"
KOCCA_SUPPORT_NOTICE_URL = "https://www.kocca.kr/kocca/pims/list.do?menuNo=204104"
MCST_FILM_SUPPORT_URL = "https://www.mcst.go.kr/site/s_policy/govPolicy/performView.jsp?pSeq=1106"

POLICY_KEYWORDS = (
    "영화",
    "제작지원",
    "지원사업",
    "관람",
    "할인권",
    "독립예술영화",
    "국제공동제작",
    "상영",
    "배급",
    "콘텐츠",
)
KOCCA_POLICY_KEYWORDS = (
    *POLICY_KEYWORDS,
    "모집",
    "참가기업",
    "입주기업",
    "한류",
    "마켓",
    "KOMICS",
    "게임",
    "브랜드",
)


def policy_relevance_summary(title: str) -> str:
    text = title or ""
    if any(term in text for term in ("제작지원", "지원사업", "할인권", "관람 활성화")):
        return "영화 지원사업"
    if any(term in text for term in ("결과", "선정")):
        return "선정/결과"
    if "공고" in text:
        return "공고"
    return "정책"


def _parse_date(raw: str) -> datetime | None:
    raw = (raw or "").strip()
    for fmt in ("%Y.%m.%d", "%Y-%m-%d", "%y.%m.%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=KST).astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _row_texts(row) -> list[str]:
    return [cell.text(strip=True) for cell in row.css("td")]


def parse_kofic_business_notices(html: str) -> list[PolicyItem]:
    tree = HTMLParser(html)
    items: list[PolicyItem] = []
    for row in tree.css("tr"):
        cells = _row_texts(row)
        if len(cells) < 4:
            continue
        category = cells[1]
        title = cells[2]
        date_text = cells[3]
        if not title or not any(keyword in title for keyword in POLICY_KEYWORDS):
            continue
        link = row.css_first("a[href]")
        href = link.attributes.get("href", "") if link is not None else ""
        url = urljoin(KOFIC_BASE_URL, href)
        items.append(
            PolicyItem(
                id=make_article_id(url or title),
                source="영화진흥위원회",
                category=category or policy_relevance_summary(title),
                title=title,
                url=url,
                published_at=_parse_date(date_text),
                summary=policy_relevance_summary(title),
            )
        )
    return items


def _first_link(row):
    return row.css_first("a[href]")


def parse_kocca_support_notices(html: str) -> list[PolicyItem]:
    tree = HTMLParser(html)
    items: list[PolicyItem] = []
    for row in tree.css("tr"):
        cells = _row_texts(row)
        if len(cells) < 3:
            continue
        link = _first_link(row)
        if link is None:
            continue
        title = link.text(strip=True)
        if not title or not any(keyword in title for keyword in KOCCA_POLICY_KEYWORDS):
            continue
        category = cells[0]
        date_text = next((cell for cell in cells[2:] if _parse_date(cell)), "")
        href = link.attributes.get("href", "")
        url = urljoin(KOCCA_BASE_URL, href)
        items.append(
            PolicyItem(
                id=make_article_id(url or title),
                source="한국콘텐츠진흥원",
                category=category or policy_relevance_summary(title),
                title=title,
                url=url,
                published_at=_parse_date(date_text),
                summary=policy_relevance_summary(title),
            )
        )
    return items


def _mcst_support_item(html: str) -> list[PolicyItem]:
    tree = HTMLParser(html)
    title = ""
    title_node = tree.css_first("h3")
    if title_node is not None:
        title = title_node.text(strip=True)
    text = tree.text(separator=" ", strip=True)
    if (
        not title
        or "영화" not in text
        or not any(keyword in title for keyword in POLICY_KEYWORDS)
    ):
        return []
    return [
        PolicyItem(
            id=make_article_id(MCST_FILM_SUPPORT_URL),
            source="문화체육관광부",
            category="정책",
            title=title,
            url=MCST_FILM_SUPPORT_URL,
            summary="영화산업 지원 정책",
        )
    ]


def fetch_policy_items() -> list[PolicyItem]:
    items: list[PolicyItem] = []
    with httpx.Client(
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    ) as client:
        try:
            response = client.get(KOFIC_BUSINESS_NOTICE_URL)
            response.raise_for_status()
            response.encoding = "utf-8"
            items.extend(parse_kofic_business_notices(response.text))
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] KOFIC policy fetch failed — {exc}", file=sys.stderr)

        try:
            response = client.get(KOCCA_SUPPORT_NOTICE_URL)
            response.raise_for_status()
            response.encoding = "utf-8"
            items.extend(parse_kocca_support_notices(response.text))
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] KOCCA policy fetch failed — {exc}", file=sys.stderr)

        try:
            response = client.get(MCST_FILM_SUPPORT_URL)
            response.raise_for_status()
            response.encoding = "utf-8"
            items.extend(_mcst_support_item(response.text))
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] MCST policy fetch failed — {exc}", file=sys.stderr)

    seen: set[str] = set()
    unique: list[PolicyItem] = []
    for item in items:
        if item.url in seen:
            continue
        seen.add(item.url)
        unique.append(item)
    return unique


def save_policy_items(items: list[PolicyItem], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([item.to_dict() for item in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
