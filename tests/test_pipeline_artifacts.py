import json
from datetime import datetime, timezone

from crawler.briefing_models import BoxOfficeMovie, MarketSnapshot, ReservationMovie, ReservationSnapshot
from crawler.main import (
    collect_focused_movie_news,
    collect_market_trend_items,
    community_search_terms,
    focused_movie_news_terms,
    save_json_items,
)
from crawler.models import Article


def test_collect_market_trend_items_combines_existing_articles_with_naver(monkeypatch):
    base_article = Article(
        id="base",
        source="테스트뉴스",
        country="KR",
        title="이머시브 콘텐츠 올빗 공개",
        summary="공간 재해석과 참여형 스토리텔링",
        url="https://example.com/base",
        published_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
    )
    naver_article = Article(
        id="naver",
        source="Naver News",
        country="KR",
        title="아이돌 팝업스토어 오픈런",
        summary="한정 굿즈와 팬덤 소비",
        url="https://example.com/naver",
        published_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
    )

    def fake_fetch(client_id, client_secret):
        assert client_id == "id"
        assert client_secret == "secret"
        return [naver_article]

    monkeypatch.setenv("NAVER_CLIENT_ID", "id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "secret")
    monkeypatch.delenv("MARKET_TRENDS_AI_CMD", raising=False)
    monkeypatch.setattr("crawler.main.fetch_market_trend_articles_from_naver", fake_fetch)

    trends = collect_market_trend_items([base_article])

    assert [trend.category for trend in trends] == ["체험형 콘텐츠 + 공연", "팝업/공간"]
    assert {trend.title for trend in trends} == {
        "이머시브 콘텐츠 올빗 공개",
        "아이돌 팝업스토어 오픈런",
    }


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
    assert "와일드씽" in terms
    assert "영화 관객 반응" in terms


def test_focused_movie_news_terms_only_include_lotte_distributed_titles():
    reservation = ReservationSnapshot(
        captured_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        movies=[
            ReservationMovie(
                rank=1,
                title="마이클",
                reservation_rate=10.6,
                is_lotte_distributed=False,
            ),
            ReservationMovie(
                rank=4,
                title="와일드 씽",
                reservation_rate=6.7,
                is_lotte_distributed=True,
            ),
        ],
    )

    terms = focused_movie_news_terms(None, reservation)

    assert terms == ["와일드 씽", "와일드씽"]


def test_collect_focused_movie_news_fetches_naver_news_for_lotte_titles(monkeypatch):
    article = Article(
        id="wild",
        source="Naver News",
        country="KR",
        title="와일드 씽 티켓 프로모션",
        summary="롯데엔터테인먼트 공식 SNS 출처",
        url="https://example.com/wild",
        published_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
    )
    reservation = ReservationSnapshot(
        captured_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        movies=[
            ReservationMovie(
                rank=4,
                title="와일드 씽",
                reservation_rate=6.7,
                is_lotte_distributed=True,
            )
        ],
    )

    def fake_fetch(client_id, client_secret, queries, display, public_fallback):
        assert queries == ["와일드 씽", "와일드씽"]
        assert display == 5
        assert public_fallback is True
        return [article]

    monkeypatch.setenv("NAVER_CLIENT_ID", "id")
    monkeypatch.setenv("NAVER_CLIENT_SECRET", "secret")
    monkeypatch.setattr("crawler.main.fetch_market_trend_articles_from_naver", fake_fetch)

    articles = collect_focused_movie_news(None, reservation)

    assert [item.title for item in articles] == ["와일드 씽 티켓 프로모션"]


def test_community_search_terms_use_brief_titles_for_overlong_reservation_titles():
    reservation = ReservationSnapshot(
        captured_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        movies=[
            ReservationMovie(
                rank=5,
                title="너바나 더 밴드 : 전설적 밴드 ‘너바나’와는 별 관련 없는 ‘너바나 더 밴드’의 콤비 맷과 제이. 어느 날 공연을 위해 타임머신을 만드는 황당한 작전을 세우고 처음 만났던 17년 전으로 돌",
                reservation_rate=2.2,
            )
        ],
    )

    terms = community_search_terms(None, reservation)

    assert "너바나 더 밴드" in terms
    assert all("어느 날 공연" not in term for term in terms)
