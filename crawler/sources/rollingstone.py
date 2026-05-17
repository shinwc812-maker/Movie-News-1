"""Rolling Stone (US) — RSS 피드 소스 (TV/Movies 섹션)."""

from crawler.sources.base import RssSource


class RollingStoneSource(RssSource):
    name = "Rolling Stone"
    country = "US"
    feed_url = "https://www.rollingstone.com/tv-movies/feed/"
