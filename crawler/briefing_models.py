"""Dashboard-specific data models for market, community, and policy artifacts."""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional


def _datetime_to_json(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _datetime_from_json(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromisoformat(value)


@dataclass
class BoxOfficeMovie:
    rank: int
    movie_code: str
    title: str
    audi_count: int
    audi_acc: int
    open_date: Optional[str] = None
    rank_change: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BoxOfficeMovie":
        return cls(
            rank=int(data.get("rank", 0)),
            movie_code=str(data.get("movie_code") or ""),
            title=str(data.get("title") or ""),
            audi_count=int(data.get("audi_count") or 0),
            audi_acc=int(data.get("audi_acc") or 0),
            open_date=data.get("open_date"),
            rank_change=data.get("rank_change"),
        )


@dataclass
class MarketSnapshot:
    target_date: str
    fetched_at: datetime
    movies: list[BoxOfficeMovie] = field(default_factory=list)
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "target_date": self.target_date,
            "fetched_at": self.fetched_at.isoformat(),
            "movies": [movie.to_dict() for movie in self.movies],
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MarketSnapshot":
        return cls(
            target_date=str(data.get("target_date") or ""),
            fetched_at=datetime.fromisoformat(data["fetched_at"]),
            movies=[
                BoxOfficeMovie.from_dict(movie)
                for movie in data.get("movies", [])
                if isinstance(movie, dict)
            ],
            error_message=data.get("error_message"),
        )


@dataclass
class ReservationSnapshot:
    captured_at: datetime
    image_path: Optional[str] = None
    top_movie: Optional[str] = None
    top_rate: Optional[str] = None
    capture_failed: bool = False
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["captured_at"] = self.captured_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ReservationSnapshot":
        data = dict(data)
        data["captured_at"] = datetime.fromisoformat(data["captured_at"])
        return cls(**data)


@dataclass
class CommunityReaction:
    id: str
    source: str
    title: str
    url: str
    excerpt: str = ""
    mood_summary: str = ""
    published_at: Optional[datetime] = None
    image_url: Optional[str] = None
    matched_keywords: list[str] = field(default_factory=list)
    content_kind: str = "community"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["published_at"] = _datetime_to_json(self.published_at)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "CommunityReaction":
        data = dict(data)
        data["published_at"] = _datetime_from_json(data.get("published_at"))
        data.setdefault("matched_keywords", [])
        data.setdefault("content_kind", "community")
        return cls(**data)


@dataclass
class PolicyItem:
    id: str
    source: str
    category: str
    title: str
    url: str
    published_at: Optional[datetime] = None
    summary: str = ""
    deadline: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["published_at"] = _datetime_to_json(self.published_at)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PolicyItem":
        data = dict(data)
        data["published_at"] = _datetime_from_json(data.get("published_at"))
        return cls(**data)


@dataclass
class CrawlDiagnostic:
    source: str
    ok: bool
    message: str = ""
    collected_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CrawlDiagnostic":
        return cls(
            source=str(data.get("source") or ""),
            ok=bool(data.get("ok")),
            message=str(data.get("message") or ""),
            collected_count=int(data.get("collected_count") or 0),
        )
