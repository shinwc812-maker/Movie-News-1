"""Deadline (US) — RSS 피드 소스."""

from crawler.sources.base import RssSource


class DeadlineSource(RssSource):
    name = "Deadline"
    country = "US"
    feed_url = "https://deadline.com/v/film/feed/"
