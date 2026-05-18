"""크롤링 결과를 담는 데이터 모델."""

from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Literal, Optional


@dataclass
class Article:
    id: str                                  # sha256(url)[:16]
    source: str                              # "Variety" 등
    country: Literal["US", "KR"]
    title: str
    title_ko: Optional[str] = None
    summary: str = ""
    summary_ko: Optional[str] = None
    url: str = ""
    published_at: Optional[datetime] = None  # UTC
    image_url: Optional[str] = None
    content_kind: Literal["official", "community"] = "official"
    tier: int = 4                            # 1=롯데, 2=파라마운트, 3=기타배급, 4=일반
    score: float = 0.0
    matched_keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """JSON 직렬화 가능한 dict로 변환. datetime은 ISO 8601 문자열."""
        d = asdict(self)
        if self.published_at is not None:
            d["published_at"] = self.published_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Article":
        """to_dict()로 만든 dict를 다시 Article로 복원."""
        d = dict(d)
        pa = d.get("published_at")
        if isinstance(pa, str):
            d["published_at"] = datetime.fromisoformat(pa)
        d.setdefault("content_kind", "official")
        return cls(**d)
