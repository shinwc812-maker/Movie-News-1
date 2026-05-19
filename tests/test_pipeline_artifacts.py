import json
from datetime import datetime, timezone

from crawler.briefing_models import BoxOfficeMovie, MarketSnapshot, ReservationMovie, ReservationSnapshot
from crawler.main import community_search_terms, save_json_items


def test_save_json_items_creates_parent_and_writes_utf8(tmp_path):
    path = tmp_path / "data" / "community.json"

    save_json_items([{"title": "왕과 사는 남자"}], path)

    assert json.loads(path.read_text(encoding="utf-8"))[0]["title"] == "왕과 사는 남자"


def test_community_search_terms_include_reservation_top_five_titles():
    market = MarketSnapshot(
        target_date="20260517",
        fetched_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
        movies=[
            BoxOfficeMovie(
                rank=1,
                movie_code="m1",
                title="마이클",
                audi_count=100,
                audi_acc=200,
            )
        ],
    )
    reservation = ReservationSnapshot(
        captured_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
        movies=[
            ReservationMovie(
                rank=3,
                title="와일드 씽",
                reservation_rate=7.4,
            )
        ],
    )

    terms = community_search_terms(market, reservation)

    assert terms[:2] == ["마이클", "와일드 씽"]
    assert "영화 관객 반응" in terms
