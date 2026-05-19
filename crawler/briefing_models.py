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
    audi_inten: int = 0
    audi_change: float = 0.0
    seat_count: int = 0
    seat_share: Optional[float] = None
    seat_sales_rate: Optional[float] = None
    rank_change: Optional[str] = None
    distributors: list[str] = field(default_factory=list)
    is_lotte_distributed: bool = False
    tmdb_id: Optional[int] = None
    tmdb_title: Optional[str] = None
    tmdb_original_title: Optional[str] = None
    tmdb_overview: str = ""
    tmdb_poster_path: Optional[str] = None
    tmdb_release_date: Optional[str] = None

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
            audi_inten=int(data.get("audi_inten") or 0),
            audi_change=float(data.get("audi_change") or 0.0),
            seat_count=int(data.get("seat_count") or 0),
            seat_share=float(data["seat_share"]) if data.get("seat_share") is not None else None,
            seat_sales_rate=float(data["seat_sales_rate"]) if data.get("seat_sales_rate") is not None else None,
            rank_change=data.get("rank_change"),
            distributors=[
                str(distributor)
                for distributor in data.get("distributors", [])
                if distributor
            ],
            is_lotte_distributed=bool(data.get("is_lotte_distributed")),
            tmdb_id=int(data["tmdb_id"]) if data.get("tmdb_id") else None,
            tmdb_title=data.get("tmdb_title"),
            tmdb_original_title=data.get("tmdb_original_title"),
            tmdb_overview=str(data.get("tmdb_overview") or ""),
            tmdb_poster_path=data.get("tmdb_poster_path"),
            tmdb_release_date=data.get("tmdb_release_date"),
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
class ReservationMovie:
    rank: int
    title: str
    reservation_rate: float
    reservation_count: int = 0
    english_title: Optional[str] = None
    movie_code: str = ""
    distributors: list[str] = field(default_factory=list)
    is_lotte_distributed: bool = False
    tmdb_id: Optional[int] = None
    tmdb_title: Optional[str] = None
    tmdb_original_title: Optional[str] = None
    tmdb_overview: str = ""
    tmdb_poster_path: Optional[str] = None
    tmdb_release_date: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ReservationMovie":
        return cls(
            rank=int(data.get("rank", 0)),
            title=str(data.get("title") or ""),
            reservation_rate=float(data.get("reservation_rate") or 0.0),
            reservation_count=int(data.get("reservation_count") or 0),
            english_title=data.get("english_title"),
            movie_code=str(data.get("movie_code") or ""),
            distributors=[
                str(distributor)
                for distributor in data.get("distributors", [])
                if distributor
            ],
            is_lotte_distributed=bool(data.get("is_lotte_distributed")),
            tmdb_id=int(data["tmdb_id"]) if data.get("tmdb_id") else None,
            tmdb_title=data.get("tmdb_title"),
            tmdb_original_title=data.get("tmdb_original_title"),
            tmdb_overview=str(data.get("tmdb_overview") or ""),
            tmdb_poster_path=data.get("tmdb_poster_path"),
            tmdb_release_date=data.get("tmdb_release_date"),
        )


@dataclass
class ReservationSnapshot:
    captured_at: datetime
    image_path: Optional[str] = None
    top_movie: Optional[str] = None
    top_rate: Optional[str] = None
    movies: list[ReservationMovie] = field(default_factory=list)
    capture_failed: bool = False
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        data = {
            "captured_at": self.captured_at.isoformat(),
            "top_movie": self.top_movie,
            "top_rate": self.top_rate,
            "movies": [movie.to_dict() for movie in self.movies],
            "capture_failed": self.capture_failed,
            "error_message": self.error_message,
        }
        if self.image_path:
            data["image_path"] = self.image_path
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ReservationSnapshot":
        data = dict(data)
        data["captured_at"] = datetime.fromisoformat(data["captured_at"])
        data["movies"] = [
            ReservationMovie.from_dict(movie)
            for movie in data.get("movies", [])
            if isinstance(movie, dict)
        ]
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
