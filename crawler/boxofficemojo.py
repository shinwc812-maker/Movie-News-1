"""Box Office Mojo overseas weekend box office collection."""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import httpx
from selectolax.parser import HTMLParser

from crawler.briefing_models import OverseasWeekendMovie, OverseasWeekendSnapshot
from crawler.sources.base import REQUEST_TIMEOUT

BOXOFFICE_MOJO_HOME_URL = "https://www.boxofficemojo.com/"
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _normalise_lines(html: str) -> list[str]:
    text = HTMLParser(html).text(separator="\n", strip=True)
    return [line.strip() for line in text.splitlines() if line.strip()]


def _link_by_title(html: str, base_url: str) -> dict[str, str]:
    tree = HTMLParser(html)
    links: dict[str, str] = {}
    for link in tree.css("a[href]"):
        title = link.text(strip=True)
        href = link.attributes.get("href", "").strip()
        if title and href and title not in links:
            links[title] = urljoin(base_url, href)
    return links


def _weekend_start(lines: list[str]) -> tuple[int, str]:
    for index, line in enumerate(lines):
        if "Latest Weekend" not in line:
            continue
        match = re.search(r"Latest Weekend:?\s*(.+)?", line)
        label = (match.group(1) or "").strip() if match else ""
        return index, label
    return -1, ""


def parse_latest_weekend(html: str, base_url: str = BOXOFFICE_MOJO_HOME_URL) -> OverseasWeekendSnapshot:
    """Parse the homepage Latest Weekend block into a top-five snapshot."""
    lines = _normalise_lines(html)
    links = _link_by_title(html, base_url)
    start, label = _weekend_start(lines)
    movies: list[OverseasWeekendMovie] = []
    if start < 0:
        return OverseasWeekendSnapshot(
            weekend_label="",
            fetched_at=datetime.now(timezone.utc),
            movies=[],
            error_message="Latest Weekend block not found",
        )

    compact_pattern = re.compile(r"^(\d+)\s+(.+?)\s+(\$[\d,.]+[KMB]?)\b")
    money_pattern = re.compile(r"^\$[\d,.]+[KMB]?$")
    index = start + 1
    while index < len(lines) and len(movies) < 5:
        line = lines[index]
        if line == "More »" or line.startswith("Recent Release Date Changes"):
            break

        compact = compact_pattern.match(line)
        if compact:
            rank = int(compact.group(1))
            title = compact.group(2).strip()
            gross = compact.group(3)
            if 1 <= rank <= 5:
                movies.append(
                    OverseasWeekendMovie(
                        rank=rank,
                        title=title,
                        gross=gross,
                        url=links.get(title, ""),
                    )
                )
            index += 1
            continue

        if line.isdigit():
            rank = int(line)
            if not 1 <= rank <= 5 or index + 1 >= len(lines):
                index += 1
                continue
            title = lines[index + 1]
            gross = ""
            cursor = index + 2
            while cursor < len(lines) and cursor <= index + 5:
                if money_pattern.match(lines[cursor]):
                    gross = lines[cursor]
                    break
                cursor += 1
            if gross:
                movies.append(
                    OverseasWeekendMovie(
                        rank=rank,
                        title=title,
                        gross=gross,
                        url=links.get(title, ""),
                    )
                )
                index = cursor + 1
                continue

        index += 1

    return OverseasWeekendSnapshot(
        weekend_label=label,
        fetched_at=datetime.now(timezone.utc),
        movies=movies,
    )


def fetch_overseas_weekend_snapshot() -> OverseasWeekendSnapshot:
    """Fetch Box Office Mojo homepage and parse the latest weekend top five."""
    fetched_at = datetime.now(timezone.utc)
    try:
        with httpx.Client(
            timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": BROWSER_UA},
            follow_redirects=True,
        ) as client:
            response = client.get(BOXOFFICE_MOJO_HOME_URL)
            response.raise_for_status()
        snapshot = parse_latest_weekend(response.text)
        snapshot.fetched_at = fetched_at
        return snapshot
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] Box Office Mojo fetch failed — {exc}", file=sys.stderr)
        return OverseasWeekendSnapshot(
            weekend_label="",
            fetched_at=fetched_at,
            error_message=str(exc),
        )


def save_overseas_weekend_snapshot(snapshot: OverseasWeekendSnapshot, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
