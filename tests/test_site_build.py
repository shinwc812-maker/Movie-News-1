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


def test_strip_trailing_whitespace_removes_generated_blank_padding():
    build = load_site_build_module()

    assert build.strip_trailing_whitespace("a  \n   \nb") == "a\n\nb\n"
