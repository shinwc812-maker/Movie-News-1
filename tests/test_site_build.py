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


def test_top_curation_items_prioritizes_market_and_korean_official_articles():
    build = load_site_build_module()
    official = [
        {"title": "Generic Paramount", "score": 1200, "country": "US", "matched_keywords": ["Paramount"]},
        {"title": "Michael box office", "score": 500, "country": "US", "matched_keywords": ["마이클"]},
        {"title": "Local release interview", "score": 120, "country": "KR", "matched_keywords": []},
        {"title": "Warner only", "score": 900, "country": "US", "matched_keywords": ["Warner Bros"]},
    ]
    community = [
        {"title": "Community spike", "score": 5000, "country": "KR", "content_kind": "community"},
    ]

    result = build.top_curation_items(
        official,
        community,
        market_titles=["마이클"],
        reservation_titles=[],
    )

    titles = [item["title"] for item in result]
    assert titles[:2] == ["Michael box office", "Local release interview"]
    assert "Generic Paramount" not in titles
    assert "Warner only" not in titles
    assert "Community spike" not in titles


def test_top_curation_items_excludes_low_value_cine21_sections():
    build = load_site_build_module()
    official = [
        {"title": "[MY PICK] 한선화의 MY PICK✩", "score": 9999, "country": "KR", "matched_keywords": []},
        {
            "title": "[델리] 인도 박스오피스 흥행 신기록",
            "score": 9998,
            "country": "KR",
            "matched_keywords": [],
        },
        {"title": "국내 극장가 투자 시스템 변화", "score": 10, "country": "KR", "matched_keywords": []},
    ]

    result = build.top_curation_items(official, market_titles=["마이클"])

    assert [item["title"] for item in result] == ["국내 극장가 투자 시스템 변화"]


def test_top_curation_items_excludes_recommended_books():
    build = load_site_build_module()
    official = [
        {"title": "씨네21 추천도서 - <꿈의 방>", "score": 9999, "country": "KR", "matched_keywords": []},
        {"title": "와일드씽 팬 이벤트 반응", "score": 10, "country": "KR", "matched_keywords": ["와일드 씽"]},
    ]

    result = build.top_curation_items(official, market_titles=["와일드 씽"])

    assert [item["title"] for item in result] == ["와일드씽 팬 이벤트 반응"]


def test_top_curation_items_boosts_promo_reference_signals():
    build = load_site_build_module()
    official = [
        {"title": "국내 극장가 단신", "summary": "일반 문화 소식", "score": 500, "country": "KR", "matched_keywords": []},
        {
            "title": "강동원·엄태구·박지현 와일드씽 팬 이벤트",
            "summary": "롯데엔터테인먼트 배급작 홍보 현장",
            "score": 100,
            "country": "KR",
            "matched_keywords": ["와일드 씽"],
        },
    ]

    result = build.top_curation_items(official, market_titles=["마이클"])

    assert result[0]["title"] == "강동원·엄태구·박지현 와일드씽 팬 이벤트"


def test_top_curation_items_can_include_matched_community_reactions():
    build = load_site_build_module()
    official = [
        {"title": "국내 극장가 투자 시스템 변화", "score": 10, "country": "KR", "matched_keywords": []},
    ]
    community = [
        {"title": "마이클 실관람 반응", "content_kind": "community", "matched_keywords": ["마이클"], "score": 0},
        {"title": "와일드씽 예매 반응", "content_kind": "community", "matched_keywords": ["와일드 씽"], "score": 0},
        {"title": "군체 일반 반응", "content_kind": "community", "matched_keywords": ["군체"], "score": 0},
        {"title": "잡담", "content_kind": "community", "matched_keywords": [], "score": 9999},
    ]

    result = build.top_curation_items(
        official,
        community,
        market_titles=["마이클", "군체"],
        reservation_titles=["와일드 씽"],
    )

    community_titles = [item["title"] for item in result if item.get("content_kind") == "community"]
    assert community_titles == ["와일드씽 예매 반응", "마이클 실관람 반응"]
    assert "잡담" not in [item["title"] for item in result]


def test_top_curation_items_uses_overseas_weekend_as_weak_context():
    build = load_site_build_module()
    official = [
        {"title": "국내 극장가 투자 시스템 변화", "score": 100, "country": "KR", "matched_keywords": []},
        {"title": "Michael keeps weekend box office lead", "score": 900, "country": "US", "matched_keywords": ["Michael"]},
        {"title": "Warner only", "score": 1200, "country": "US", "matched_keywords": ["Warner Bros"]},
    ]

    result = build.top_curation_items(
        official,
        market_titles=["마이클"],
        overseas_titles=["Michael"],
    )

    titles = [item["title"] for item in result]
    assert "Michael keeps weekend box office lead" in titles
    assert "Warner only" not in titles
    assert titles.index("국내 극장가 투자 시스템 변화") < titles.index("Michael keeps weekend box office lead")


def test_top_curation_items_can_include_one_policy_signal():
    build = load_site_build_module()
    official = [
        {"title": "국내 극장가 투자 시스템 변화", "score": 100, "country": "KR", "matched_keywords": []},
    ]
    policy = [
        {"content_kind": "policy", "title": "2026년 영화 제작지원 사업 공고", "summary": "영화 지원사업"},
        {"content_kind": "policy", "title": "콘텐츠 기업 입주기업 모집", "summary": "정책"},
    ]

    result = build.top_curation_items(
        official,
        policy_views=policy,
        market_titles=["마이클"],
    )

    policy_titles = [item["title"] for item in result if item.get("content_kind") == "policy"]
    assert policy_titles == ["2026년 영화 제작지원 사업 공고"]


def test_overseas_weekend_view_formats_top_five():
    build = load_site_build_module()

    view = build.overseas_weekend_view(
        {
            "weekend_label": "May 15-17",
            "movies": [
                {"rank": 1, "title": "Michael", "gross": "$26.1M", "url": "https://example.com/michael"},
                {"rank": 2, "title": "The Devil Wears Prada 2", "gross": "$17.9M"},
            ],
        }
    )

    assert view["available"] is True
    assert view["weekend_label"] == "May 15-17"
    assert view["movies"][0]["title"] == "Michael"
    assert view["movies"][0]["gross"] == "$26.1M"


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


def test_market_views_formats_audience_delta_and_seat_metrics():
    build = load_site_build_module()
    views = build.market_views(
        {
            "movies": [
                {
                    "rank": 1,
                    "title": "마이클",
                    "open_date": "2026-05-13",
                    "audi_count": 43653,
                    "audi_inten": -135371,
                    "audi_change": -75.6,
                    "audi_acc": 691565,
                    "seat_count": 805113,
                    "seat_share": 0.4745,
                    "seat_sales_rate": 43653 / 805113,
                }
            ]
        }
    )

    assert views[0]["top_label"] == "마이클 (43,653명 / ▼135,371명)"
    assert views[0]["audi_delta"] == "▼135,371명 (-75.6%)"
    assert views[0]["seat_count"] == "805,113"
    assert views[0]["seat_share"] == "47.4%"
    assert views[0]["seat_sales_rate"] == "5.42%"


def test_strip_trailing_whitespace_removes_generated_blank_padding():
    build = load_site_build_module()

    assert build.strip_trailing_whitespace("a  \n   \nb") == "a\n\nb\n"
