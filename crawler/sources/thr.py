"""The Hollywood Reporter (US) — RSS 피드 소스."""

from crawler.sources.base import RssSource


class THRSource(RssSource):
    name = "The Hollywood Reporter"
    country = "US"
    feed_url = "https://www.hollywoodreporter.com/c/movies/feed/"
