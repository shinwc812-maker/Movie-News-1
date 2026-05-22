import json
from datetime import datetime, timedelta, timezone

from crawler.briefing_models import BoxOfficeMovie, MarketSnapshot, ReservationMovie, ReservationSnapshot
from crawler.main import (
    collect_focused_movie_news,
    collect_market_trend_items,
    community_search_terms,
    filter_recent,
    focused_movie_news_terms,
    save_json_items,
)
from crawler.market_trends import MARKET_TREND_RECENCY_DAYS
from crawler.models import Article


def test_collect_market_trend_items_combines_existing_articles_with_naver(monkeypatch):
    # collect_market_trend_items는 now를 주입할 수 없으므로(내부 datetime.now 사용)
    # 7일 하드 필터에 걸리지 않도록 기사 날짜를 현재 기준 상대값으로 둔다.
    recent = datetime.now(timezone.utc) - timedelta(hours=12)
    base_article = Article(
        id="base",
        source="테스트뉴스",
        country="KR",
        title="이머시브 콘텐츠 올빗 공개",
        summary="공간 재해석과 참여형 스토리텔링",
        url="https://example.com/base",
        published_at=recent,
    )
    naver_article = Article(
        id="naver",
        source="Naver News",
        country="KR",
        title="아이돌 팝업스토어 오픈런",
        summary="한정 굿즈와 팬덤 소비",
        url="https://example.com/naver",
        published_at=recent,
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

    assert [trend.category for trend in trends] == ["체험형 콘텐츠", "공간 사업"]
    assert {trend.title for trend in trends} == {
        "이머시브 콘텐츠 올빗 공개",
        "아이돌 팝업스토어 오픈런",
    }


def test_filter_recent_supports_wider_window_for_market_trends():
    now = datetime(2026, 5, 22, tzinfo=timezone.utc)
    fresh = Article(
        id="f", source="s", country="KR", title="48h내", summary="",
        url="https://example.com/f", published_at=now - timedelta(hours=24),
    )
    five_days = Article(
        id="d", source="s", country="KR", title="5일전", summary="",
        url="https://example.com/d", published_at=now - timedelta(days=5),
    )

    # 기본 48h: 5일 전 기사는 제외(공식 브리핑)
    assert {a.id for a in filter_recent([fresh, five_days], now=now)} == {"f"}

    # 7일 창: 5일 전 기사도 포함(시장 동향 live/ip/팝업)
    wide = filter_recent(
        [fresh, five_days], now=now, max_age_hours=MARKET_TREND_RECENCY_DAYS * 24
    )
    assert {a.id for a in wide} == {"f", "d"}


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
