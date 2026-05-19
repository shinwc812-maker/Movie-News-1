from datetime import datetime, timezone

from crawler.briefing_models import BoxOfficeMovie, MarketSnapshot, ReservationMovie, ReservationSnapshot
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


def test_lotte_distributed_boxoffice_movie_gets_extra_article_weight():
    base_market = MarketSnapshot(
        target_date="20260517",
        fetched_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
        movies=[
            BoxOfficeMovie(
                rank=2,
                movie_code="m1",
                title="마이클",
                audi_count=10000,
                audi_acc=20000,
                is_lotte_distributed=False,
            )
        ],
    )
    lotte_market = MarketSnapshot(
        target_date="20260517",
        fetched_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
        movies=[
            BoxOfficeMovie(
                rank=2,
                movie_code="m1",
                title="마이클",
                audi_count=10000,
                audi_acc=20000,
                distributors=["롯데엔터테인먼트"],
                is_lotte_distributed=True,
            )
        ],
    )
    base = Article(id="a1", source="씨네21", country="KR", title="마이클 흥행 분석")
    lotte = Article(id="a2", source="씨네21", country="KR", title="마이클 흥행 분석")

    score_all([base], now=datetime(2026, 5, 18, tzinfo=timezone.utc), market=base_market)
    score_all([lotte], now=datetime(2026, 5, 18, tzinfo=timezone.utc), market=lotte_market)

    assert lotte.score > base.score
    assert "롯데배급" in lotte.matched_keywords


def test_lotte_distributed_reservation_movie_gets_extra_article_weight():
    reservation = ReservationSnapshot(
        captured_at=datetime(2026, 5, 18, tzinfo=timezone.utc),
        movies=[
            ReservationMovie(
                rank=3,
                title="와일드 씽",
                english_title="Wild Sing",
                reservation_rate=7.4,
                reservation_count=19775,
                movie_code="20248252",
                distributors=["롯데컬처웍스(주)롯데엔터테인먼트", "Lotte Entertainment"],
                is_lotte_distributed=True,
            )
        ],
    )
    article = Article(id="a1", source="씨네21", country="KR", title="와일드 씽 예매 상승")

    score_all(
        [article],
        now=datetime(2026, 5, 18, tzinfo=timezone.utc),
        reservation=reservation,
    )

    assert article.score > 0
    assert "와일드 씽" in article.matched_keywords
    assert "롯데배급" in article.matched_keywords
