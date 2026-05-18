import importlib.util
from pathlib import Path


def load_site_build_module():
    path = Path(__file__).resolve().parents[1] / "site" / "build.py"
    spec = importlib.util.spec_from_file_location("movie_news_site_build", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_split_articles_by_kind_separates_official_and_community():
    build = load_site_build_module()
    views = [
        {"content_kind": "official", "title": "공식"},
        {"content_kind": "community", "title": "커뮤니티"},
    ]

    official, community = build.split_articles_by_kind(views)

    assert official[0]["title"] == "공식"
    assert community[0]["title"] == "커뮤니티"


def test_legacy_extmovie_articles_are_treated_as_community():
    build = load_site_build_module()
    view = build.to_article_view(
        {
            "source": "익스트림무비",
            "country": "KR",
            "title": "관객 반응",
            "summary": "댓글 분위기",
            "score": 10,
        },
        build.datetime(2026, 5, 18, tzinfo=build.timezone.utc),
    )

    official, community = build.split_articles_by_kind([view])

    assert official == []
    assert community[0]["title"] == "관객 반응"
    assert community[0]["excerpt"] == "댓글 분위기"


def test_top_curation_items_limits_to_five_score_order():
    build = load_site_build_module()
    views = [{"title": str(i), "score": i} for i in range(10)]

    result = build.top_curation_items(views)

    assert [item["title"] for item in result] == ["9", "8", "7", "6", "5"]


def test_top_curation_items_caps_overseas_official_articles():
    build = load_site_build_module()
    official = [
        {"title": "US 1", "score": 100, "country": "US"},
        {"title": "US 2", "score": 90, "country": "US"},
        {"title": "US 3", "score": 80, "country": "US"},
        {"title": "KR 1", "score": 70, "country": "KR"},
        {"title": "KR 2", "score": 60, "country": "KR"},
    ]

    result = build.top_curation_items(official, limit=5, max_overseas_official=2)

    assert [item["title"] for item in result] == ["US 1", "US 2", "KR 1", "KR 2"]


def test_select_official_feed_prefers_korean_and_caps_overseas():
    build = load_site_build_module()
    articles = [
        {"title": "US 1", "score": 100, "country": "US"},
        {"title": "US 2", "score": 90, "country": "US"},
        {"title": "US 3", "score": 80, "country": "US"},
        {"title": "KR 1", "score": 70, "country": "KR"},
        {"title": "KR 2", "score": 60, "country": "KR"},
    ]

    result = build.select_official_feed(articles, limit=4, max_overseas=1)

    assert [item["title"] for item in result] == ["KR 1", "KR 2", "US 1"]


def test_reservation_view_returns_structured_top_five_without_image_asset():
    build = load_site_build_module()
    view = build.reservation_view(
        {
            "captured_at": "2026-05-18T07:30:19+00:00",
            "image_path": "assets/legacy.png",
            "movies": [
                {"rank": 1, "title": "군체", "reservation_rate": 46.7, "reservation_count": 125334},
                {"rank": 2, "title": "마이클", "reservation_rate": 13.2, "reservation_count": 35480},
            ],
        }
    )

    assert view["movies"][0]["title"] == "군체"
    assert view["movies"][0]["reservation_rate"] == "46.7%"
    assert view["movies"][0]["reservation_label"] == "125,334명 (46.7%)"
    assert "image_url" not in view


def test_strip_trailing_whitespace_removes_generated_blank_padding():
    build = load_site_build_module()

    assert build.strip_trailing_whitespace("a  \n   \nb") == "a\n\nb\n"
