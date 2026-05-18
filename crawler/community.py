"""Community reaction collection.

Community reactions are stored separately from official articles. The first
supported source is Extreme Movie, and additional public list pages can be
configured with CSS selectors.
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

import httpx
from selectolax.parser import HTMLParser

from crawler.briefing_models import CommunityReaction
from crawler.sources.base import REQUEST_TIMEOUT, USER_AGENT, make_article_id
from crawler.sources.extmovie import parse_extmovie_time

EXTMOVIE_BASE_URL = "https://extmovie.com"
EXTMOVIE_HOME_URL = "https://extmovie.com/"

POSITIVE_TERMS = ("재밌", "좋", "기대", "호평", "추천", "만족")
NEGATIVE_TERMS = ("아쉽", "별로", "혹평", "실망", "걱정", "불호")


def summarize_reaction_mood(text: str) -> str:
    """Return a deterministic short mood summary for community snippets."""
    positive = sum(text.count(term) for term in POSITIVE_TERMS)
    negative = sum(text.count(term) for term in NEGATIVE_TERMS)
    if positive and negative:
        return "호불호가 함께 보임"
    if positive:
        return "긍정 반응 우세"
    if negative:
        return "우려/부정 반응 우세"
    return "중립적 반응"


def _text(node, selector: str) -> str:
    if node is None:
        return ""
    target = node.css_first(selector) if selector else node
    return target.text(strip=True) if target is not None else ""


def _first_attr(node, selector: str, attr: str) -> Optional[str]:
    if node is None:
        return None
    target = node.css_first(selector) if selector else node
    if target is None:
        return None
    value = target.attributes.get(attr)
    return value.strip() if value else None


def parse_extmovie_community_cards(html: str) -> list[CommunityReaction]:
    """Parse Extreme Movie cards into community reaction records."""
    tree = HTMLParser(html)
    search_roots = []
    for title in tree.css("div.widget-title"):
        if title.text(strip=True).startswith("뉴스"):
            search_roots.append(title.parent or tree.root)
    if not search_roots:
        search_roots = [tree.root]

    reactions: list[CommunityReaction] = []
    seen: set[str] = set()
    for root in search_roots:
        for card in root.css("div.widget-body > a"):
            href = card.attributes.get("href", "").strip()
            title = _text(card, "span.title-text")
            if not href or not title:
                continue
            url = urljoin(EXTMOVIE_BASE_URL, href.split("?", 1)[0])
            if url in seen:
                continue
            seen.add(url)

            excerpt = _text(card, "span.summary")
            date_text = _text(card, "span.meta span.date")
            image_url = _first_attr(card, "img", "src")
            if image_url:
                image_url = urljoin(EXTMOVIE_BASE_URL, image_url)

            reactions.append(
                CommunityReaction(
                    id=make_article_id(url),
                    source="익스트림무비",
                    title=title,
                    url=url,
                    excerpt=excerpt,
                    mood_summary=summarize_reaction_mood(f"{title} {excerpt}"),
                    published_at=parse_extmovie_time(date_text),
                    image_url=image_url,
                )
            )
    return reactions


@dataclass
class ConfiguredCommunityListSource:
    """Config-driven public community list parser for expansion targets."""

    name: str
    list_url: str
    item_selector: str
    title_selector: str
    link_selector: str
    summary_selector: str = ""
    date_selector: str = ""

    def fetch(self) -> list[CommunityReaction]:
        try:
            with httpx.Client(
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
            ) as client:
                response = client.get(self.list_url)
                response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] {self.name}: community fetch failed — {exc}", file=sys.stderr)
            return []
        return self.parse(response.text)

    def parse(self, html: str) -> list[CommunityReaction]:
        tree = HTMLParser(html)
        reactions: list[CommunityReaction] = []
        seen: set[str] = set()
        for item in tree.css(self.item_selector):
            title = _text(item, self.title_selector)
            href = _first_attr(item, self.link_selector, "href")
            if not title or not href:
                continue
            url = urljoin(self.list_url, href)
            if url in seen:
                continue
            seen.add(url)
            excerpt = _text(item, self.summary_selector)
            date_text = _text(item, self.date_selector)
            reactions.append(
                CommunityReaction(
                    id=make_article_id(url),
                    source=self.name,
                    title=title,
                    url=url,
                    excerpt=excerpt,
                    mood_summary=summarize_reaction_mood(f"{title} {excerpt}"),
                    published_at=parse_extmovie_time(date_text),
                )
            )
        return reactions


class ExtMovieCommunitySource:
    name = "익스트림무비"

    def fetch(self) -> list[CommunityReaction]:
        try:
            with httpx.Client(
                timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": USER_AGENT},
                follow_redirects=True,
            ) as client:
                response = client.get(EXTMOVIE_HOME_URL)
                response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] {self.name}: community fetch failed — {exc}", file=sys.stderr)
            return []
        response.encoding = "utf-8"
        return parse_extmovie_community_cards(response.text)


COMMUNITY_SOURCES = [ExtMovieCommunitySource()]


def fetch_community_reactions() -> list[CommunityReaction]:
    reactions: list[CommunityReaction] = []
    seen: set[str] = set()
    for source in COMMUNITY_SOURCES:
        for reaction in source.fetch():
            if reaction.url in seen:
                continue
            seen.add(reaction.url)
            reactions.append(reaction)
    return reactions


def save_community_reactions(reactions: list[CommunityReaction], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([reaction.to_dict() for reaction in reactions], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
