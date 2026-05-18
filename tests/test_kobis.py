from datetime import date

from crawler.kobis import (
    build_daily_boxoffice_url,
    kst_yesterday,
    parse_daily_boxoffice,
    parse_reservation_top,
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
