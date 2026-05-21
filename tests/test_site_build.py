import importlib.util
from pathlib import Path
import sys


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


def test_market_trend_views_preserve_frame_note_and_implication():
    build = load_site_build_module()
    views = build.market_trend_views(
        [
            {
                "content_kind": "market_trend",
                "category": "팝업/공간",
                "title": "팝업이 팬덤 소비 동선으로 이동",
                "url": "https://example.com/popup",
                "source": "Example",
                "frame": "팝업은 기본 동선",
                "note": "한정 굿즈와 포토카드 중심의 방문 수요.",
                "implication": "극장 공간과 IP 이벤트를 묶을 수 있음.",
                "keywords": ["팝업", "팬덤"],
            }
        ],
        build.datetime(2026, 5, 20, tzinfo=build.timezone.utc),
    )

    assert views[0]["content_kind"] == "market_trend"
    assert views[0]["category"] == "팝업/공간"
    assert views[0]["frame"] == "팝업은 기본 동선"
    assert views[0]["implication"].startswith("극장")
    assert views[0]["keywords"] == ["팝업", "팬덤"]


def test_build_market_trend_sections_uses_business_category_order():
    build = load_site_build_module()
    trends = [
        {"category": "팝업/공간", "title": "팝업"},
        {"category": "체험형 콘텐츠 + 공연", "title": "공연"},
        {"category": "IP/OSMU", "title": "IP"},
    ]

    sections = build.build_market_trend_sections(trends)

    assert [section["title"] for section in sections] == ["체험형 콘텐츠 + 공연", "IP/OSMU", "팝업/공간"]
    assert sections[0]["items"][0]["title"] == "공연"


def test_build_community_sections_groups_by_source_order_and_limits_items():
    build = load_site_build_module()
    community = [
        {"source": "네이버카페", "title": "네이버1"},
        {"source": "무코", "title": "무코1"},
        {"source": "무코", "title": "무코2"},
        {"source": "익스트림무비", "title": "익무1"},
    ]

    sections = build.build_community_sections(community, limit_per_section=1)

    assert [section["title"] for section in sections] == ["무코", "익스트림무비", "네이버카페"]
    assert sections[0]["count"] == 2
    assert [item["title"] for item in sections[0]["items"]] == ["무코1"]


def test_build_community_sections_prioritizes_lotte_distributed_titles_within_source():
    build = load_site_build_module()
    community = [
        {"source": "무코", "title": "마이클 굿즈", "matched_keywords": ["마이클"]},
        {"source": "무코", "title": "와일드씽 싸다구", "matched_keywords": ["와일드 씽"]},
        {"source": "무코", "title": "군체 후기", "matched_keywords": ["군체"]},
    ]

    sections = build.build_community_sections(
        community,
        limit_per_section=2,
        priority_titles=["와일드 씽"],
    )

    assert [item["title"] for item in sections[0]["items"]] == ["와일드씽 싸다구", "마이클 굿즈"]


def test_write_archive_snapshot_uses_kst_timestamp_and_copies_current_data(tmp_path):
    build = load_site_build_module()
    data_dir = tmp_path / "data"
    dist_dir = tmp_path / "dist"
    data_dir.mkdir()
    articles = data_dir / "articles.json"
    community = data_dir / "community.json"
    articles.write_text('[{"title":"오늘 기사"}]', encoding="utf-8")
    community.write_text('[{"title":"오늘 반응"}]', encoding="utf-8")
    now = build.datetime(2026, 5, 21, 1, 2, 3, tzinfo=build.timezone.utc)

    archive = build.write_archive_snapshot(
        "<html>today</html>\n",
        now,
        data_paths=[articles, community, data_dir / "missing.json"],
        dist_dir=dist_dir,
        data_dir=data_dir,
    )

    assert archive["html_path"] == dist_dir / "archive" / "2026-05-21" / "100203" / "index.html"
    assert archive["data_dir"] == data_dir / "archive" / "2026-05-21" / "100203"
    assert archive["html_path"].read_text(encoding="utf-8") == "<html>today</html>\n"
    assert (archive["data_dir"] / "articles.json").read_text(encoding="utf-8") == '[{"title":"오늘 기사"}]'
    assert (archive["data_dir"] / "community.json").read_text(encoding="utf-8") == '[{"title":"오늘 반응"}]'
    assert not (archive["data_dir"] / "missing.json").exists()


def test_write_archive_snapshot_does_not_overwrite_same_second_archive(tmp_path):
    build = load_site_build_module()
    data_dir = tmp_path / "data"
    dist_dir = tmp_path / "dist"
    data_dir.mkdir()
    now = build.datetime(2026, 5, 21, 1, 2, 3, tzinfo=build.timezone.utc)

    first = build.write_archive_snapshot("<html>first</html>\n", now, data_paths=[], dist_dir=dist_dir, data_dir=data_dir)
    second = build.write_archive_snapshot("<html>second</html>\n", now, data_paths=[], dist_dir=dist_dir, data_dir=data_dir)

    assert first["html_path"] == dist_dir / "archive" / "2026-05-21" / "100203" / "index.html"
    assert second["html_path"] == dist_dir / "archive" / "2026-05-21" / "100203-02" / "index.html"
    assert first["html_path"].read_text(encoding="utf-8") == "<html>first</html>\n"
    assert second["html_path"].read_text(encoding="utf-8") == "<html>second</html>\n"


def test_template_contains_market_trends_section():
    template = Path(__file__).resolve().parents[1] / "site" / "template.html.j2"

    assert "시장동향 / Live·IP·팝업" in template.read_text(encoding="utf-8")


def test_template_removes_lower_official_feed_panel():
    template = Path(__file__).resolve().parents[1] / "site" / "template.html.j2"
    text = template.read_text(encoding="utf-8")

    assert "<h2>공식 기사</h2>" not in text
    assert "<span>공식 기사</span>" not in text
    assert "<span>시장동향</span>" in text
    assert "<h2>커뮤니티 반응</h2>" in text
    assert "community-only-panel" in text


def test_template_keeps_market_trend_cards_summary_only():
    template = Path(__file__).resolve().parents[1] / "site" / "template.html.j2"
    text = template.read_text(encoding="utf-8")

    assert "<b>요약</b>" in text
    assert "<b>시사점</b>" not in text


def test_template_contains_sectioned_curation_briefing_labels():
    template = Path(__file__).resolve().parents[1] / "site" / "template.html.j2"
    text = template.read_text(encoding="utf-8")

    assert "curation_sections" in text
    assert "흥행·배급" in text
    assert "내용 요약" in text
    assert "평가" not in text


def test_template_renders_curation_sections_without_dict_method_collision():
    build = load_site_build_module()
    env = build.Environment(
        loader=build.FileSystemLoader(str(Path(__file__).resolve().parents[1] / "site")),
        autoescape=True,
    )
    html = env.get_template("template.html.j2").render(
        official_articles=[],
        official_feed=[],
        community_reactions=[],
        community_sections=[],
        policy_items=[],
        market_trends=[],
        market_trend_sections=[],
        curation=[],
        curation_sections=[
            {
                "title": "흥행·배급",
                "eyebrow": "box office / distribution",
                "items": [
                    {
                        "content_kind": "official",
                        "title": "와일드씽 예매 상승",
                        "url": "https://example.com/a",
                        "source": "테스트뉴스",
                        "curation_summary": "예매 상승세가 확인됨.",
                        "matched_keywords": ["와일드 씽"],
                    }
                ],
            }
        ],
        boxoffice=[],
        reservation={"movies": []},
        overseas_weekend={"movies": []},
        total_official=0,
        total_community=0,
        total_policies=0,
        total_market_trends=0,
        css="",
        updated_at="2026년 05월 20일 10:00",
    )

    assert "흥행·배급" in html
    assert "1건" in html
    assert html.index("흥행·배급") < html.index("와일드씽 예매 상승")
    assert html.index("와일드씽 예매 상승") < html.index("내용 요약")
    assert "예매 상승세가 확인됨." in html
    assert "평가" not in html


def test_template_renders_market_and_community_sections_without_dict_method_collision():
    build = load_site_build_module()
    env = build.Environment(
        loader=build.FileSystemLoader(str(Path(__file__).resolve().parents[1] / "site")),
        autoescape=True,
    )
    html = env.get_template("template.html.j2").render(
        official_articles=[],
        official_feed=[],
        community_reactions=[{"source": "무코", "title": "와일드 씽 반응"}],
        community_sections=[
            {
                "title": "무코",
                "count": 1,
                "items": [{"source": "무코", "title": "와일드 씽 반응", "url": "https://muko.kr/all/1"}],
            }
        ],
        policy_items=[],
        market_trends=[{"category": "체험형 콘텐츠 + 공연", "title": "공연형 팝업"}],
        market_trend_sections=[
            {
                "title": "체험형 콘텐츠 + 공연",
                "count": 1,
                "items": [
                    {
                        "category": "체험형 콘텐츠 + 공연",
                        "title": "공연형 팝업",
                        "url": "https://example.com/trend",
                        "source": "테스트뉴스",
                        "note": "요약",
                        "implication": "시사점",
                        "keywords": ["공연"],
                    }
                ],
            }
        ],
        curation=[],
        curation_sections=[],
        boxoffice=[],
        reservation={"movies": []},
        overseas_weekend={"movies": []},
        total_official=0,
        total_community=1,
        total_policies=0,
        total_market_trends=1,
        css="",
        updated_at="2026년 05월 20일 10:00",
    )

    assert "체험형 콘텐츠 + 공연" in html
    assert "공연형 팝업" in html
    assert "무코" in html
    assert "와일드 씽 반응" in html


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


def test_build_curation_sections_groups_executive_briefing_topics():
    build = load_site_build_module()
    official = [
        {
            "title": "와일드씽 롯데엔터테인먼트 예매 상승",
            "summary": "롯데배급 신작 예매가 반등",
            "score": 80,
            "country": "KR",
            "matched_keywords": ["와일드 씽", "롯데배급"],
            "url": "https://example.com/lotte",
        },
        {
            "title": "CJ ENM 봉준호 신작 애니메이션 라인업 공개",
            "summary": "경쟁사 IP 라인업 확대",
            "score": 1000,
            "country": "KR",
            "matched_keywords": ["CJ ENM"],
            "url": "https://example.com/cj",
        },
        {
            "title": "Michael keeps overseas weekend box office lead",
            "summary": "International box office gross remains strong",
            "score": 900,
            "country": "US",
            "matched_keywords": ["Michael"],
            "url": "https://example.com/michael",
        },
        {
            "title": "티니핑 IP 극장 이벤트 확대",
            "summary": "캐릭터 IP와 극장 공간을 연결",
            "score": 700,
            "country": "KR",
            "matched_keywords": ["IP"],
            "url": "https://example.com/ip",
        },
    ]
    policy = [
        {
            "content_kind": "policy",
            "title": "지역 영화관 관람료 할인권 지원 공고",
            "summary": "극장 정책과 영화관 관람 활성화 지원",
            "url": "https://example.com/policy",
        }
    ]

    sections = build.build_curation_sections(
        official,
        policy_views=policy,
        market_titles=["와일드 씽"],
        overseas_titles=["Michael"],
        limit_per_section=2,
    )

    assert [section["title"] for section in sections] == [
        "흥행·배급",
        "극장·정책",
        "경쟁사·산업",
        "해외·마켓",
        "문화/IP",
    ]
    titles = [item["title"] for section in sections for item in section["items"]]
    assert len(titles) == len(set(titles))
    assert "와일드씽 롯데엔터테인먼트 예매 상승" in titles
    assert all(item["curation_summary"] for section in sections for item in section["items"])
    assert not any("curation_evaluation" in item for section in sections for item in section["items"])


def test_build_curation_sections_keeps_longer_content_summary():
    build = load_site_build_module()
    long_summary = (
        "롯데배급 신작의 예매가 주요 상영관을 중심으로 반등하고 있으며, 개봉 이후 관객 전환율을 "
        "다시 점검해야 하는 상황이다. 경쟁작 대비 좌석 배정과 프로모션 메시지를 함께 확인할 필요가 있다. "
        "초반 인지도 확보 이후 실제 구매로 이어지는 흐름을 보기 위해 지역별 예매 편차와 상영 회차 조정을 같이 봐야 한다."
    )
    official = [
        {
            "title": "와일드씽 롯데엔터테인먼트 예매 상승",
            "summary": long_summary,
            "score": 80,
            "country": "KR",
            "matched_keywords": ["와일드 씽", "롯데배급"],
            "url": "https://example.com/lotte",
        }
    ]

    sections = build.build_curation_sections(
        official,
        market_titles=["와일드 씽"],
        limit_per_section=1,
    )

    summary = sections[0]["items"][0]["curation_summary"]
    assert len(summary) > 115
    assert "프로모션 메시지" in summary


def test_build_curation_sections_expands_too_short_summary_with_title_context():
    build = load_site_build_module()
    policy = [
        {
            "content_kind": "policy",
            "title": "2026년 독립예술영화 제작지원 장편 극영화부문 사업 공고",
            "summary": "영화 지원사업",
            "url": "https://example.com/policy",
        }
    ]

    sections = build.build_curation_sections([], policy_views=policy)

    summary = sections[0]["items"][0]["curation_summary"]
    assert "독립예술영화 제작지원" in summary
    assert "영화 지원사업" in summary


def test_build_curation_sections_does_not_backfill_low_context_overseas_ai_items():
    build = load_site_build_module()
    official = [
        {
            "title": "Steven Soderbergh on using AI as a creative tool",
            "summary": "A director talks about a documentary interview process",
            "score": 900,
            "country": "US",
            "matched_keywords": [],
            "url": "https://example.com/ai",
        },
        {
            "title": "Park Chan-Wook Western moves forward at Warner Bros.",
            "summary": "Korean director project gains international market attention",
            "score": 100,
            "country": "US",
            "matched_keywords": [],
            "url": "https://example.com/park",
        },
    ]

    sections = build.build_curation_sections(official, limit_per_section=2)

    titles = [item["title"] for section in sections for item in section["items"]]
    assert "Park Chan-Wook Western moves forward at Warner Bros." in titles
    assert "Steven Soderbergh on using AI as a creative tool" not in titles


def test_enrich_curation_sections_uses_ai_json_when_command_succeeds():
    build = load_site_build_module()
    sections = [
        {
            "key": "boxoffice",
            "title": "흥행·배급",
            "items": [
                {
                    "id": "a1",
                    "title": "와일드씽 예매 상승",
                    "source": "테스트뉴스",
                    "country": "US",
                    "curation_summary": "fallback summary",
                }
            ],
        }
    ]
    command = [
        sys.executable,
        "-c",
        (
            "import json;"
            "print(json.dumps([{'id':'a1','title':'와일드씽 해외 예매 상승','summary':'AI가 두세 문장 분량으로 확장한 내용 요약입니다. 해외 기사 제목은 한국어로 번역되어 함께 표시됩니다.'}], ensure_ascii=False))"
        ),
    ]

    enriched = build.enrich_curation_sections_with_ai(sections, command=command)

    item = enriched[0]["items"][0]
    assert item["curation_title"] == "와일드씽 해외 예매 상승"
    assert item["curation_summary"].startswith("AI가 두세 문장")
    assert "curation_evaluation" not in item


def test_enrich_curation_sections_keeps_fallback_when_command_fails():
    build = load_site_build_module()
    sections = [
        {
            "key": "policy",
            "title": "극장·정책",
            "items": [
                {
                    "id": "p1",
                    "title": "영화관 관람료 할인권",
                    "source": "KOFIC",
                    "curation_summary": "fallback summary",
                }
            ],
        }
    ]

    enriched = build.enrich_curation_sections_with_ai(
        sections,
        command=[sys.executable, "-c", "raise SystemExit(2)"],
    )

    item = enriched[0]["items"][0]
    assert item["curation_summary"] == "fallback summary"
    assert item["curation_title"] == "영화관 관람료 할인권"
    assert "curation_evaluation" not in item


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


def test_top_curation_items_keeps_community_reactions_out_of_core_curation():
    build = load_site_build_module()
    official = [
        {"title": "국내 극장가 투자 시스템 변화", "score": 10, "country": "KR", "matched_keywords": []},
    ]
    community = [
        {"title": "마이클 실관람 반응", "content_kind": "community", "matched_keywords": ["마이클"], "score": 9000},
        {"title": "와일드씽 예매 반응", "content_kind": "community", "matched_keywords": ["와일드 씽"], "score": 8000},
        {"title": "군체 일반 반응", "content_kind": "community", "matched_keywords": ["군체"], "score": 7000},
        {"title": "잡담", "content_kind": "community", "matched_keywords": [], "score": 9999},
    ]

    result = build.top_curation_items(
        official,
        community,
        market_titles=["마이클", "군체"],
        reservation_titles=["와일드 씽"],
    )

    assert [item["title"] for item in result] == ["국내 극장가 투자 시스템 변화"]


def test_top_curation_items_keeps_one_competitor_signal_and_theater_policy():
    build = load_site_build_module()
    official = [
        {
            "title": "CJ ENM 봉준호 신작 애니메이션 라인업 공개",
            "score": 1000,
            "country": "KR",
            "matched_keywords": ["CJ ENM"],
        },
        {
            "title": "CGV 특별관 확대와 티켓 가격 전략",
            "score": 950,
            "country": "KR",
            "matched_keywords": ["CGV"],
        },
        {
            "title": "마이클 박스오피스 1위 유지",
            "score": 100,
            "country": "KR",
            "matched_keywords": ["마이클"],
        },
        {
            "title": "와일드씽 롯데엔터테인먼트 예매 상승",
            "score": 80,
            "country": "KR",
            "matched_keywords": ["와일드 씽", "롯데배급"],
        },
    ]
    policy = [
        {
            "content_kind": "policy",
            "title": "지역 영화관 관람료 할인권 지원 공고",
            "summary": "극장 정책과 영화관 관람 활성화 지원",
        }
    ]

    result = build.top_curation_items(
        official,
        policy_views=policy,
        market_titles=["마이클"],
        reservation_titles=["와일드 씽"],
        limit=5,
    )

    titles = [item["title"] for item in result]
    competitor_titles = [title for title in titles if "CJ" in title or "CGV" in title]
    assert "와일드씽 롯데엔터테인먼트 예매 상승" in titles
    assert "마이클 박스오피스 1위 유지" in titles
    assert "지역 영화관 관람료 할인권 지원 공고" in titles
    assert len(competitor_titles) == 1
    assert competitor_titles[0] == "CJ ENM 봉준호 신작 애니메이션 라인업 공개"


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


def test_select_official_feed_filters_low_value_sections():
    build = load_site_build_module()
    articles = [
        {"title": "씨네21 추천도서 - <꿈의 방>", "score": 999, "country": "KR"},
        {"title": "[MY PICK] 한선화의 MY PICK✩", "score": 998, "country": "KR"},
        {"title": "[델리] 해외 단신", "score": 997, "country": "KR"},
        {"title": "[trans x cross] 극장 인터뷰", "score": 996, "country": "KR"},
        {"title": "CJ ENM 봉준호 신작 애니메이션 라인업 공개", "score": 10, "country": "KR"},
        {"title": "Michael 해외 흥행 분석", "score": 9, "country": "US"},
    ]

    result = build.select_official_feed(articles, limit=4, max_overseas=2)

    assert [item["title"] for item in result] == [
        "CJ ENM 봉준호 신작 애니메이션 라인업 공개",
        "Michael 해외 흥행 분석",
    ]


def test_select_official_feed_defaults_to_two_overseas_articles():
    build = load_site_build_module()
    articles = [
        {"title": "CJ ENM 봉준호 신작 애니메이션 라인업 공개", "score": 100, "country": "KR"},
        {"title": "US 1", "score": 99, "country": "US"},
        {"title": "US 2", "score": 98, "country": "US"},
        {"title": "US 3", "score": 97, "country": "US"},
    ]

    result = build.select_official_feed(articles, limit=6)

    assert [item["title"] for item in result] == [
        "CJ ENM 봉준호 신작 애니메이션 라인업 공개",
        "US 1",
        "US 2",
    ]


def test_select_official_feed_prefers_overseas_korean_talent_or_market_context():
    build = load_site_build_module()
    articles = [
        {"title": "CJ ENM 봉준호 신작 애니메이션 라인업 공개", "score": 100, "country": "KR"},
        {"title": "Rick and Morty Movie In Development at Warner Bros.", "score": 1000, "country": "US"},
        {
            "title": "Park Chan-Wook Project Sells at Cannes Market",
            "score": 100,
            "country": "US",
        },
    ]

    result = build.select_official_feed(articles, limit=3, max_overseas=1)

    assert [item["title"] for item in result] == [
        "CJ ENM 봉준호 신작 애니메이션 라인업 공개",
        "Park Chan-Wook Project Sells at Cannes Market",
    ]


def test_select_official_feed_dedupes_same_overseas_topic():
    build = load_site_build_module()
    articles = [
        {"title": "CJ ENM 봉준호 신작 애니메이션 라인업 공개", "score": 100, "country": "KR"},
        {
            "title": "Park Chan-Wook Project Sells at Cannes Market",
            "score": 100,
            "country": "US",
        },
        {
            "title": "Warner Bros Closing In on Park Chan-Wook Project",
            "score": 99,
            "country": "US",
        },
        {"title": "Rick and Morty Movie In Development at Warner Bros.", "score": 98, "country": "US"},
    ]

    result = build.select_official_feed(articles, limit=4)

    assert [item["title"] for item in result] == [
        "CJ ENM 봉준호 신작 애니메이션 라인업 공개",
        "Park Chan-Wook Project Sells at Cannes Market",
    ]


def test_select_official_feed_does_not_backfill_low_context_overseas_when_priority_exists():
    build = load_site_build_module()
    articles = [
        {"title": "CJ ENM 봉준호 신작 애니메이션 라인업 공개", "score": 100, "country": "KR"},
        {
            "title": "Park Chan-Wook Project Sells at Cannes Market",
            "score": 100,
            "country": "US",
        },
        {"title": "Rick and Morty Movie In Development at Warner Bros.", "score": 1000, "country": "US"},
    ]

    result = build.select_official_feed(articles, limit=4)

    assert [item["title"] for item in result] == [
        "CJ ENM 봉준호 신작 애니메이션 라인업 공개",
        "Park Chan-Wook Project Sells at Cannes Market",
    ]


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
