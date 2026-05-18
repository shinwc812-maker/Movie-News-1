from crawler.community import (
    NaverPublicCafeSearchSource,
    NaverPublicWebSearchSource,
    NaverSearchCommunitySource,
    YouTubeCommunitySource,
    parse_extmovie_community_cards,
    summarize_reaction_mood,
)


def test_parse_extmovie_community_cards_extracts_reaction_fields():
    html = """
    <div class="widget-title">뉴스</div>
    <div class="widget-body">
      <a href="/movietalk/1">
        <span class="title-text">'왕과 사는 남자' 관객 반응</span>
        <span class="summary">재밌다는 반응과 CG 아쉽다는 의견이 같이 있습니다.</span>
        <span class="meta"><span class="date">1시간 전</span></span>
      </a>
    </div>
    """

    reactions = parse_extmovie_community_cards(html)

    assert len(reactions) == 1
    assert reactions[0].source == "익스트림무비"
    assert reactions[0].excerpt.startswith("재밌다는")
    assert reactions[0].content_kind == "community"


def test_summarize_reaction_mood_detects_mixed_sentiment():
    summary = summarize_reaction_mood("재밌다 좋다 아쉽다 별로다 기대된다")

    assert "호불호" in summary


def test_naver_search_source_parses_cafe_items():
    source = NaverSearchCommunitySource(
        source_name="네이버카페",
        endpoint="cafearticle",
        client_id="id",
        client_secret="secret",
        base_query_suffix="영화 관객 반응",
    )
    payload = {
        "items": [
            {
                "title": "<b>마이클</b> 영화 후기",
                "description": "재밌다는 반응과 아쉽다는 반응이 같이 있습니다.",
                "link": "https://cafe.naver.com/specup/1",
                "cafename": "스펙업",
            }
        ]
    }

    reactions = source.parse_payload(payload, query="마이클")

    assert len(reactions) == 1
    assert reactions[0].source == "네이버카페"
    assert reactions[0].title == "마이클 영화 후기"
    assert reactions[0].excerpt.startswith("스펙업")
    assert "호불호" in reactions[0].mood_summary


def test_naver_webkr_source_keeps_only_twitter_links_when_requested():
    source = NaverSearchCommunitySource(
        source_name="X/Twitter",
        endpoint="webkr",
        client_id="id",
        client_secret="secret",
        base_query_suffix="site:x.com OR site:twitter.com 영화 반응",
        allowed_domains=("x.com", "twitter.com"),
    )
    payload = {
        "items": [
            {
                "title": "마이클 반응",
                "description": "기대된다는 반응",
                "link": "https://x.com/example/status/1",
            },
            {
                "title": "블로그 반응",
                "description": "좋다는 반응",
                "link": "https://blog.naver.com/example/1",
            },
        ]
    }

    reactions = source.parse_payload(payload, query="마이클")

    assert len(reactions) == 1
    assert reactions[0].source == "X/Twitter"
    assert reactions[0].url.startswith("https://x.com/")


def test_naver_public_cafe_search_source_parses_public_search_html():
    source = NaverPublicCafeSearchSource()
    html = """
    <html>
      <body>
        <a href="https://cafe.naver.com/movie02/12345">마이클 후기 재밌다는 반응</a>
        <div class="desc">관객들이 음악 장면을 추천하고 있습니다.</div>
        <a href="https://blog.naver.com/example/1">블로그 글</a>
      </body>
    </html>
    """

    reactions = source.parse(html, query="마이클")

    assert len(reactions) == 1
    assert reactions[0].source == "네이버카페"
    assert reactions[0].title == "마이클 후기 재밌다는 반응"
    assert reactions[0].matched_keywords == ["마이클"]
    assert "긍정" in reactions[0].mood_summary


def test_naver_public_cafe_search_source_skips_cafe_home_links():
    source = NaverPublicCafeSearchSource()
    html = """
    <a href="https://cafe.naver.com/specup">스펙업 카페 홈</a>
    <a href="https://cafe.naver.com/specup/7814907">영화마이클쿠키영상 후기</a>
    """

    reactions = source.parse(html, query="마이클")

    assert len(reactions) == 1
    assert reactions[0].url.endswith("/7814907")


def test_naver_public_web_search_source_parses_twitter_links():
    source = NaverPublicWebSearchSource(
        source_name="X/Twitter",
        query_suffix="site:x.com 영화 반응",
        allowed_domains=("x.com", "twitter.com"),
    )
    html = """
    <a href="https://x.com/moviefan/status/123">마이클 관객 반응 좋다는 의견</a>
    <a href="https://blog.naver.com/example/1">블로그 글</a>
    """

    reactions = source.parse(html, query="마이클")

    assert len(reactions) == 1
    assert reactions[0].source == "X/Twitter"
    assert reactions[0].url == "https://x.com/moviefan/status/123"


def test_naver_public_web_search_source_can_require_status_links():
    source = NaverPublicWebSearchSource(
        source_name="X/Twitter",
        query_suffix="site:x.com 영화 반응",
        allowed_domains=("x.com", "twitter.com"),
        required_path_fragments=("/status/",),
    )
    html = """
    <a href="https://x.com/moviefan">프로필 링크</a>
    <a href="https://twitter.com/moviefan/status/123">마이클 실관람 반응</a>
    """

    reactions = source.parse(html, query="마이클")

    assert len(reactions) == 1
    assert "/status/" in reactions[0].url


def test_youtube_source_parses_video_search_payload():
    source = YouTubeCommunitySource(api_key="fake-key")
    payload = {
        "items": [
            {
                "id": {"kind": "youtube#video", "videoId": "abc123"},
                "snippet": {
                    "title": "마이클 관객 반응 리뷰",
                    "description": "재밌다는 평가와 기대 반응 정리",
                    "channelTitle": "영화채널",
                    "publishedAt": "2026-05-18T02:00:00Z",
                    "thumbnails": {"medium": {"url": "https://i.ytimg.com/vi/abc123/mqdefault.jpg"}},
                },
            },
            {
                "id": {"kind": "youtube#channel", "channelId": "not-video"},
                "snippet": {"title": "채널"},
            },
        ]
    }

    reactions = source.parse_payload(payload, query="마이클")

    assert len(reactions) == 1
    assert reactions[0].source == "YouTube"
    assert reactions[0].url == "https://www.youtube.com/watch?v=abc123"
    assert reactions[0].excerpt.startswith("영화채널")
    assert reactions[0].image_url.endswith("mqdefault.jpg")
