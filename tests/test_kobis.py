from datetime import date

import httpx

from crawler.briefing_models import BoxOfficeMovie, ReservationMovie
from crawler.kobis import (
    _fetch_movie_distributors,
    build_daily_boxoffice_url,
    enrich_movies_with_distributors,
    enrich_reservation_movies_with_kobis,
    kst_yesterday,
    load_distributor_cache,
    parse_daily_boxoffice,
    parse_movie_distributors,
    parse_reservation_movies,
    parse_reservation_top,
    parse_seat_metrics_gviz,
    save_distributor_cache,
)


def test_kst_yesterday_formats_target_date():
    assert kst_yesterday(date(2026, 5, 18)) == "20260517"


def test_build_daily_boxoffice_url_uses_key_and_target_date():
    url = build_daily_boxoffice_url("abc", "20260517")

    assert "key=abc" in url
    assert "targetDt=20260517" in url
    assert "searchDailyBoxOfficeList.json" in url


def test_parse_daily_boxoffice_keeps_top_five_by_rank():
    payload = {
        "boxOfficeResult": {
            "dailyBoxOfficeList": [
                {
                    "rank": "1",
                    "movieCd": "m1",
                    "movieNm": "왕과 사는 남자",
                    "audiCnt": "221,380",
                    "audiInten": "-12,345",
                    "audiChange": "-5.3",
                    "audiAcc": "12,435,466",
                },
                {
                    "rank": "2",
                    "movieCd": "m2",
                    "movieNm": "호퍼스",
                    "audiCnt": "17445",
                    "audiAcc": "375392",
                },
                {
                    "rank": "6",
                    "movieCd": "m6",
                    "movieNm": "기타",
                    "audiCnt": "1",
                    "audiAcc": "2",
                },
            ]
        }
    }

    movies = parse_daily_boxoffice(payload)

    assert [m.rank for m in movies] == [1, 2]
    assert movies[0].title == "왕과 사는 남자"
    assert movies[0].audi_count == 221380
    assert movies[0].audi_inten == -12345
    assert movies[0].audi_change == -5.3


def test_parse_seat_metrics_gviz_keeps_target_date_raw_values():
    text = """
    google.visualization.Query.setResponse({
      "table": {
        "rows": [
          {"c": [
            {"v": "마이클"},
            {"v": "외화"},
            {"v": "Date(2026,4,18)", "f": "2026-05-18"},
            {"v": "Date(2026,4,13)", "f": "2026-05-13"},
            {"v": 0.05400000000000001, "f": "0.05"},
            {"v": 0.4745, "f": "0.47"},
            {"v": 805113.0, "f": "805,113"},
            {"v": 43646.0, "f": "43,646"},
            {"v": 691558.0, "f": "691,558"}
          ]},
          {"c": [
            {"v": "마이클"},
            {"v": "외화"},
            {"v": "Date(2026,4,17)", "f": "2026-05-17"},
            {"v": "Date(2026,4,13)", "f": "2026-05-13"},
            {"v": 0.1846},
            {"v": 0.45},
            {"v": 969307.0},
            {"v": 178987.0},
            {"v": 647873.0}
          ]}
        ]
      }
    });
    """

    metrics = parse_seat_metrics_gviz(text, "20260518")
    metric = metrics[("마이클", "2026-05-13")]

    assert metric.seat_count == 805113
    assert metric.seat_share == 0.4745
    assert metric.seat_sales_rate == 0.05400000000000001


def test_parse_movie_distributors_marks_lotte_distribution():
    payload = {
        "movieInfoResult": {
            "movieInfo": {
                "companys": [
                    {"companyNm": "제작사", "companyPartNm": "제작사"},
                    {
                        "companyNm": "롯데컬처웍스(주)롯데엔터테인먼트",
                        "companyNmEn": "Lotte Entertainment",
                        "companyPartNm": "배급사",
                    },
                ]
            }
        }
    }

    distributors, is_lotte = parse_movie_distributors(payload)

    assert distributors == ["롯데컬처웍스(주)롯데엔터테인먼트", "Lotte Entertainment"]
    assert is_lotte is True


def test_parse_reservation_top_from_kobis_mobile_html():
    html = """
    <h3>실시간 예매율</h3>
    <p>1</p>
    <p>군체  (COLONY)</p>
    <p>예매율(예매관객수)</p>
    <p>46.5% (110,465명)</p>
    """

    top_movie, top_rate = parse_reservation_top(html)

    assert top_movie == "군체"
    assert top_rate == "46.5%"


def test_parse_reservation_movies_keeps_top_five_rates_from_kobis_mobile_html():
    html = """
    <h3>실시간 예매율</h3>
    <p>예매율 (예매관객수)</p>
    <p>전체영화</p>
    <p>1</p>
    <p>군체</p>
    <p>(COLONY)</p>
    <p>예매율(예매관객수)</p>
    <p>46.7% (125,334명)</p>
    <p>2</p>
    <p>마이클</p>
    <p>(Michael)</p>
    <p>예매율(예매관객수)</p>
    <p>13.2% (35,480명)</p>
    <p>3</p>
    <p>와일드 씽</p>
    <p>(Wild Sing)</p>
    <p>예매율(예매관객수)</p>
    <p>7.4% (19,775명)</p>
    <p>4</p>
    <p>신극장판 은혼: 요시와라 대염상</p>
    <p>(Gintama: Yoshiwara in Flames)</p>
    <p>예매율(예매관객수)</p>
    <p>4.3% (11,427명)</p>
    <p>5</p>
    <p>악마는 프라다를 입는다 2</p>
    <p>(The Devil Wears Prada 2)</p>
    <p>예매율(예매관객수)</p>
    <p>3.2% (8,710명)</p>
    """

    movies = parse_reservation_movies(html)

    assert [movie.rank for movie in movies] == [1, 2, 3, 4, 5]
    assert movies[0].title == "군체"
    assert movies[0].english_title == "COLONY"
    assert movies[0].reservation_rate == 46.7
    assert movies[0].reservation_count == 125334
    assert movies[4].title == "악마는 프라다를 입는다 2"


def test_parse_reservation_movies_shortens_overlong_official_titles_for_briefing():
    html = """
    <h3>실시간 예매율</h3>
    <p>5</p>
    <p>너바나 더 밴드 : 전설적 밴드 ‘너바나’와는 별 관련 없는 ‘너바나 더 밴드’의 콤비 맷과 제이. 어느 날 공연을 위해 타임머신을 만드는 황당한 작전을 세우고 처음 만났던 17년 전으로 돌</p>
    <p>(Nirvanna the Band the Show the Movie)</p>
    <p>예매율(예매관객수)</p>
    <p>2.2% (8,675명)</p>
    """

    movies = parse_reservation_movies(html)

    assert movies[0].title == "너바나 더 밴드"
    assert movies[0].english_title == "Nirvanna the Band the Show the Movie"


def test_enrich_reservation_movies_with_kobis_marks_lotte_distributor_from_wild_sing():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/searchMovieList.json"):
            query = request.url.params.get("movieNm")
            if query == "와일드 씽":
                return httpx.Response(200, json={"movieListResult": {"movieList": []}})
            assert query == "Wild Sing"
            return httpx.Response(
                200,
                json={
                    "movieListResult": {
                        "movieList": [
                            {
                                "movieCd": "20248252",
                                "movieNm": "와일드 씽",
                                "movieNmEn": "Wild Sing",
                            }
                        ]
                    }
                },
            )
        if request.url.path.endswith("/searchMovieInfo.json"):
            assert request.url.params.get("movieCd") == "20248252"
            return httpx.Response(
                200,
                json={
                    "movieInfoResult": {
                        "movieInfo": {
                            "companys": [
                                {
                                    "companyNm": "롯데컬처웍스(주)롯데엔터테인먼트",
                                    "companyNmEn": "Lotte Entertainment",
                                    "companyPartNm": "배급사",
                                }
                            ]
                        }
                    }
                },
            )
        raise AssertionError(f"Unexpected URL: {request.url}")

    movies = [
        ReservationMovie(
            rank=3,
            title="와일드 씽",
            english_title="Wild Sing",
            reservation_rate=7.4,
            reservation_count=19775,
        )
    ]

    enrich_reservation_movies_with_kobis(
        movies,
        httpx.Client(transport=httpx.MockTransport(handler)),
        api_key="kobis-key",
    )

    assert movies[0].movie_code == "20248252"
    assert movies[0].distributors == ["롯데컬처웍스(주)롯데엔터테인먼트", "Lotte Entertainment"]
    assert movies[0].is_lotte_distributed is True


def test_distributor_cache_roundtrip(tmp_path):
    path = tmp_path / "distributor_cache.json"
    cache = {"와일드 씽": {"movie_code": "20248252", "distributors": ["롯데컬처웍스(주)롯데엔터테인먼트"], "is_lotte": True}}

    save_distributor_cache(cache, path)

    assert load_distributor_cache(path) == cache


def test_load_distributor_cache_missing_file_returns_empty(tmp_path):
    assert load_distributor_cache(tmp_path / "nope.json") == {}


def test_enrich_reservation_falls_back_to_cache_when_live_lookup_fails(monkeypatch):
    monkeypatch.setattr("crawler.kobis.time.sleep", lambda *args, **kwargs: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)  # 모든 KOBIS 호출 실패

    movies = [
        ReservationMovie(
            rank=3,
            title="와일드 씽",
            english_title="Wild Sing",
            reservation_rate=7.4,
            reservation_count=19775,
        )
    ]
    cache = {
        "와일드 씽": {
            "movie_code": "20248252",
            "distributors": ["롯데컬처웍스(주)롯데엔터테인먼트"],
            "is_lotte": True,
        }
    }

    enrich_reservation_movies_with_kobis(
        movies,
        httpx.Client(transport=httpx.MockTransport(handler)),
        api_key="kobis-key",
        cache=cache,
    )

    # 라이브 호출이 실패해도 캐시로 롯데 인정
    assert movies[0].is_lotte_distributed is True
    assert movies[0].movie_code == "20248252"


def test_enrich_movies_with_distributors_populates_cache():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/searchMovieInfo.json")
        return httpx.Response(
            200,
            json={
                "movieInfoResult": {
                    "movieInfo": {
                        "companys": [
                            {
                                "companyNm": "롯데컬처웍스(주)롯데엔터테인먼트",
                                "companyNmEn": "Lotte Entertainment",
                                "companyPartNm": "배급사",
                            }
                        ]
                    }
                }
            },
        )

    movies = [
        BoxOfficeMovie(rank=3, movie_code="20248252", title="와일드 씽", audi_count=0, audi_acc=0)
    ]
    cache: dict = {}

    enrich_movies_with_distributors(
        movies,
        httpx.Client(transport=httpx.MockTransport(handler)),
        api_key="kobis-key",
        cache=cache,
    )

    assert movies[0].is_lotte_distributed is True
    assert cache["와일드 씽"]["is_lotte"] is True
    assert cache["와일드 씽"]["movie_code"] == "20248252"


def test_get_with_retry_recovers_after_transient_failure(monkeypatch):
    monkeypatch.setattr("crawler.kobis.time.sleep", lambda *args, **kwargs: None)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)  # 첫 시도 실패
        return httpx.Response(
            200,
            json={
                "movieInfoResult": {
                    "movieInfo": {
                        "companys": [
                            {
                                "companyNm": "롯데컬처웍스(주)롯데엔터테인먼트",
                                "companyPartNm": "배급사",
                            }
                        ]
                    }
                }
            },
        )

    distributors, is_lotte = _fetch_movie_distributors(
        "20248252", httpx.Client(transport=httpx.MockTransport(handler)), "kobis-key"
    )

    assert is_lotte is True
    assert calls["n"] == 2  # 재시도로 성공
