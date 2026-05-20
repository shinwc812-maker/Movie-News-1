import httpx

from crawler.community import (
    DCInsideDirectSearchSource,
    MukoDirectSearchSource,
    NaverPublicCafeSearchSource,
    NaverPublicWebSearchSource,
    NaverSearchCommunitySource,
    PUBLIC_SEARCH_SOURCES,
    TheQooDirectSearchSource,
    YouTubeCommunitySource,
    _safe_exception_message,
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


def test_public_search_sources_include_theqoo_and_dcinside():
    source_names = [source.source_name for source in PUBLIC_SEARCH_SOURCES]

    assert "더쿠" in source_names
    assert "디시인사이드" in source_names


def test_theqoo_direct_search_source_parses_board_post_links():
    source = TheQooDirectSearchSource(max_items_per_query=3)
    html = """
    <a href="/event/4207015072">더쿠 이벤트</a>
    <a href="/movie/4208700057">1</a>
    <a href="/movie/4208700057">와일드씽 내일 싸다구한다</a>
    <a href="/square/4208700058">와일드 씽 후기 반응</a>
    """

    reactions = source.parse(html, query="와일드씽")

    assert len(reactions) == 2
    assert reactions[0].source == "더쿠"
    assert reactions[0].url == "https://theqoo.net/movie/4208700057"
    assert reactions[1].matched_keywords == ["와일드씽"]


def test_dcinside_direct_search_source_parses_search_result_links():
    source = DCInsideDirectSearchSource(max_items_per_query=2)
    html = """
    <a href="https://gall.dcinside.com/mgallery/board/view/?id=oticket&no=2548641">와일드씽 굿즈는 탐나는데</a>
    <a href="https://gall.dcinside.com/board/view/?id=commercial_movie&no=23109664">와일드 씽 예매율 올라왔네</a>
    <a href="https://www.dcinside.com/">디시 홈</a>
    """

    reactions = source.parse(html, query="와일드 씽")

    assert len(reactions) == 2
    assert reactions[0].source == "디시인사이드"
    assert reactions[0].url.startswith("https://gall.dcinside.com/")
    assert reactions[1].matched_keywords == ["와일드 씽"]


def test_dcinside_direct_search_source_skips_non_movie_gallery_links():
    source = DCInsideDirectSearchSource(max_items_per_query=2)
    html = """
    <a href="https://gall.dcinside.com/mgallery/board/view/?id=slay&no=404675">사일런트 &lt;&lt; 잠행군체담당일진임</a>
    <a href="https://gall.dcinside.com/mgallery/board/view/?id=oticket&no=2548641">군체 아이맥스 예매 열렸네</a>
    """

    reactions = source.parse(html, query="군체")

    assert len(reactions) == 1
    assert reactions[0].url.endswith("id=oticket&no=2548641")


def test_muko_direct_search_source_parses_movie_community_links():
    source = MukoDirectSearchSource(max_items_per_query=3)
    html = """
    <a href="/all/19936933">(상황종료) &lt;와일드 씽&gt; 싸다구 실패하신분들 취줍하러 가세요~</a>
    <a href="https://muko.kr/movietalk/19932635">박찬욱 서부극 신작 - 워너 브라더스 새 인디 레이블이 배급권 획득</a>
    <a href="/db/movie/19516429">트루먼 쇼 별점</a>
    """

    reactions = source.parse(html, query="와일드 씽")

    assert len(reactions) == 1
    assert reactions[0].source == "무코"
    assert reactions[0].url == "https://muko.kr/all/19936933"
    assert reactions[0].matched_keywords == ["와일드 씽"]


def test_naver_public_web_search_source_parses_theqoo_links():
    source = NaverPublicWebSearchSource(
        source_name="더쿠",
        query_suffix="site:theqoo.net 영화 반응",
        allowed_domains=("theqoo.net",),
        required_path_pattern=r"/[^/]+/\d+$",
    )
    html = """
    <a href="https://theqoo.net/square/123456">와일드씽 관객 반응 좋다는 글</a>
    <a href="https://theqoo.net/movie">더쿠 영화 게시판 홈</a>
    <a href="https://blog.naver.com/example/1">블로그 글</a>
    """

    reactions = source.parse(html, query="와일드씽")

    assert len(reactions) == 1
    assert reactions[0].source == "더쿠"
    assert reactions[0].matched_keywords == ["와일드씽"]


def test_naver_public_web_search_source_skips_unrelated_breadcrumb_links():
    source = NaverPublicWebSearchSource(
        source_name="더쿠",
        query_suffix="site:theqoo.net 영화 반응",
        allowed_domains=("theqoo.net",),
        required_path_pattern=r"/[^/]+/\d+$",
    )
    html = """
    <a href="https://theqoo.net/west/198379109">더쿠theqoo.net›west</a>
    <div>AI 출처 정보더쿠는 다양한 주제의 게시글이 공유되는 포럼입니다.</div>
    """

    reactions = source.parse(html, query="와일드씽")

    assert reactions == []


def test_naver_public_web_search_source_parses_dcinside_links():
    source = NaverPublicWebSearchSource(
        source_name="디시인사이드",
        query_suffix="site:dcinside.com 영화 반응",
        allowed_domains=("dcinside.com",),
        required_path_pattern=r"/board/view/",
    )
    html = """
    <a href="https://gall.dcinside.com/mgallery/board/view/?id=movie&no=123">와일드 씽 후기</a>
    <a href="https://www.dcinside.com/">디시 홈</a>
    """

    reactions = source.parse(html, query="와일드 씽")

    assert len(reactions) == 1
    assert reactions[0].source == "디시인사이드"
    assert reactions[0].url.startswith("https://gall.dcinside.com/")


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


def test_safe_exception_message_redacts_youtube_api_key():
    request = httpx.Request(
        "GET",
        "https://www.googleapis.com/youtube/v3/search?key=secret-key&part=snippet",
    )
    response = httpx.Response(403, request=request)
    exc = httpx.HTTPStatusError("failed with secret-key", request=request, response=response)

    message = _safe_exception_message(exc)

    assert "secret-key" not in message
    assert "key=[REDACTED]" in message
