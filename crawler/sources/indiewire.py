"""IndieWire (US) — RSS 피드 소스."""

from crawler.sources.base import RssSource


class IndieWireSource(RssSource):
    name = "IndieWire"
    country = "US"
    feed_url = "https://www.indiewire.com/c/film/feed/"
