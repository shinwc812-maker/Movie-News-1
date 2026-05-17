"""Variety (US) — RSS 피드 소스."""

from crawler.sources.base import RssSource


class VarietySource(RssSource):
    name = "Variety"
    country = "US"
    feed_url = "https://variety.com/v/film/feed/"
