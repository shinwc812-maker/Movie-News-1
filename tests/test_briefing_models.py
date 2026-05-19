from datetime import datetime, timezone

from crawler.briefing_models import (
    BoxOfficeMovie,
    CommunityReaction,
    MarketSnapshot,
    PolicyItem,
    ReservationMovie,
    ReservationSnapshot,
)
from crawler.models import Article


def test_article_defaults_to_official_content_kind():
    article = Article(id="a1", source="Variety", country="US", title="News")

    data = article.to_dict()
    restored = Article.from_dict(data)

    assert data["content_kind"] == "official"
    assert restored.content_kind == "official"


def test_market_snapshot_round_trips_datetime():
    snapshot = MarketSnapshot(
        target_date="20260517",
        fetched_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
        movies=[
            BoxOfficeMovie(
                rank=1,
                movie_code="20260001",
                title="왕과 사는 남자",
                audi_count=221380,
                audi_acc=12435466,
                audi_inten=-12345,
                audi_change=-5.3,
                seat_count=805113,
                seat_share=0.4745,
                seat_sales_rate=0.0542,
                distributors=["롯데엔터테인먼트"],
                is_lotte_distributed=True,
                tmdb_id=123,
                tmdb_poster_path="/poster.jpg",
            )
        ],
    )

    restored = MarketSnapshot.from_dict(snapshot.to_dict())

    assert restored.target_date == "20260517"
    assert restored.movies[0].title == "왕과 사는 남자"
    assert restored.movies[0].audi_count == 221380
    assert restored.movies[0].audi_inten == -12345
    assert restored.movies[0].audi_change == -5.3
    assert restored.movies[0].seat_count == 805113
    assert restored.movies[0].seat_share == 0.4745
    assert restored.movies[0].seat_sales_rate == 0.0542
    assert restored.movies[0].distributors == ["롯데엔터테인먼트"]
    assert restored.movies[0].is_lotte_distributed is True
    assert restored.movies[0].tmdb_id == 123
    assert restored.fetched_at.tzinfo is not None


def test_community_and_policy_models_serialize_minimal_fields():
    reaction = CommunityReaction(
        id="c1",
        source="익스트림무비",
        title="관객 반응",
        url="https://example.com/community/1",
        excerpt="본문 일부",
        mood_summary="호평과 우려가 함께 보임",
        matched_keywords=["왕과 사는 남자"],
    )
    policy = PolicyItem(
        id="p1",
        source="영화진흥위원회",
        category="공고",
        title="제작지원 사업 공고",
        url="https://example.com/policy/1",
        published_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
        summary="장편 극영화 제작지원",
    )
    reservation = ReservationSnapshot(
        captured_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
        top_movie="군체",
        top_rate="46.5%",
        movies=[
            ReservationMovie(
                rank=1,
                title="군체",
                english_title="COLONY",
                reservation_rate=46.5,
                reservation_count=110465,
                movie_code="20260001",
                distributors=["롯데엔터테인먼트"],
                is_lotte_distributed=True,
            )
        ],
    )

    assert CommunityReaction.from_dict(reaction.to_dict()).mood_summary == "호평과 우려가 함께 보임"
    assert PolicyItem.from_dict(policy.to_dict()).category == "공고"
    reservation_data = reservation.to_dict()
    restored_reservation = ReservationSnapshot.from_dict(reservation_data)

    assert "image_path" not in reservation_data
    assert restored_reservation.top_rate == "46.5%"
    assert restored_reservation.movies[0].reservation_count == 110465
    assert restored_reservation.movies[0].english_title == "COLONY"
    assert restored_reservation.movies[0].movie_code == "20260001"
    assert restored_reservation.movies[0].is_lotte_distributed is True
