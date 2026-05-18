from datetime import datetime, timezone

from crawler.briefing_models import BoxOfficeMovie, MarketSnapshot
from crawler.models import Article
from crawler.scorer import score_all


def test_boxoffice_rank_one_boosts_matching_article_above_unmatched():
    market = MarketSnapshot(
        target_date="20260517",
        fetched_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
        movies=[
            BoxOfficeMovie(
                rank=1,
                movie_code="m1",
                title="왕과 사는 남자",
                audi_count=221380,
                audi_acc=12435466,
            ),
            BoxOfficeMovie(
                rank=5,
                movie_code="m5",
                title="휴민트",
                audi_count=4308,
                audi_acc=1955611,
            ),
        ],
    )
    matched = Article(id="a1", source="씨네21", country="KR", title="왕과 사는 남자 흥행 독주")
    unmatched = Article(id="a2", source="씨네21", country="KR", title="다른 영화 소식")

    score_all(
        [matched, unmatched],
        now=datetime(2026, 5, 18, tzinfo=timezone.utc),
        market=market,
    )

    assert matched.score > unmatched.score
    assert "왕과 사는 남자" in matched.matched_keywords


def test_community_score_is_lower_than_official_for_same_boxoffice_match():
    market = MarketSnapshot(
        target_date="20260517",
        fetched_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
        movies=[
            BoxOfficeMovie(
                rank=1,
                movie_code="m1",
                title="왕과 사는 남자",
                audi_count=221380,
                audi_acc=12435466,
            )
        ],
    )
    official = Article(
        id="a1",
        source="씨네21",
        country="KR",
        title="왕과 사는 남자 흥행",
        content_kind="official",
    )
    community = Article(
        id="c1",
        source="커뮤니티",
        country="KR",
        title="왕과 사는 남자 반응",
        content_kind="community",
    )

    score_all(
        [official, community],
        now=datetime(2026, 5, 18, tzinfo=timezone.utc),
        market=market,
    )

    assert official.score > community.score
