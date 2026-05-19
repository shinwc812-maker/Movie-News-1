from crawler.briefing_models import BoxOfficeMovie, ReservationMovie
import httpx

from crawler.tmdb import fetch_tmdb_movie_metadata, parse_tmdb_movie_result


def test_parse_tmdb_movie_result_maps_first_search_item():
    payload = {
        "results": [
            {
                "id": 123,
                "title": "마이클",
                "original_title": "Michael",
                "overview": "마이클 잭슨 전기 영화",
                "poster_path": "/poster.jpg",
                "release_date": "2026-04-29",
            }
        ]
    }

    metadata = parse_tmdb_movie_result(payload)

    assert metadata == {
        "tmdb_id": 123,
        "tmdb_title": "마이클",
        "tmdb_original_title": "Michael",
        "tmdb_overview": "마이클 잭슨 전기 영화",
        "tmdb_poster_path": "/poster.jpg",
        "tmdb_release_date": "2026-04-29",
    }


def test_boxoffice_movie_accepts_tmdb_metadata_fields():
    movie = BoxOfficeMovie(
        rank=1,
        movie_code="m1",
        title="마이클",
        audi_count=100,
        audi_acc=200,
        tmdb_id=123,
        tmdb_title="마이클",
    )

    restored = BoxOfficeMovie.from_dict(movie.to_dict())

    assert restored.tmdb_id == 123
    assert restored.tmdb_title == "마이클"


def test_reservation_movie_accepts_tmdb_metadata_fields():
    movie = ReservationMovie(
        rank=3,
        title="와일드 씽",
        english_title="Wild Sing",
        reservation_rate=7.4,
        tmdb_id=456,
        tmdb_title="와일드 씽",
    )

    restored = ReservationMovie.from_dict(movie.to_dict())

    assert restored.tmdb_id == 456
    assert restored.tmdb_title == "와일드 씽"


def test_tmdb_fetch_falls_back_to_reservation_english_title():
    queries = []

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params.get("query")
        queries.append(query)
        if query == "와일드 씽":
            return httpx.Response(200, json={"results": []})
        assert query == "Wild Sing"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": 456,
                        "title": "와일드 씽",
                        "original_title": "Wild Sing",
                    }
                ]
            },
        )

    movie = ReservationMovie(
        rank=3,
        title="와일드 씽",
        english_title="Wild Sing",
        reservation_rate=7.4,
    )

    metadata = fetch_tmdb_movie_metadata(
        movie,
        api_key="tmdb-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert queries == ["와일드 씽", "Wild Sing"]
    assert metadata["tmdb_id"] == 456
