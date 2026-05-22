from datetime import datetime, timezone
import sys

import httpx

from crawler.briefing_models import MarketTrendItem
from crawler.market_trends import (
    _naver_news_get_with_retry,
    build_market_trends,
    classify_market_trend_article,
    enrich_market_trends_with_ai,
    fetch_market_trend_articles_from_naver,
    parse_google_news_rss_items,
    parse_naver_news_items,
    parse_public_naver_news_items,
)
from crawler.models import Article


def article(title: str, summary: str = "", url: str = "https://example.com/a") -> Article:
    return Article(
        id=title[:12],
        source="테스트뉴스",
        country="KR",
        title=title,
        summary=summary,
        url=url,
        published_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
    )


def test_classify_market_trend_article_matches_reference_categories():
    immersive = article(
        "일본 몰입형 전시공간 3곳",
        "관객이 직접 참여하는 이머시브 테마파크와 체험형 콘텐츠가 확산",
    )
    ip = article(
        "티니핑 IP 확장 가속화",
        "공연 영화 굿즈 게임을 연결하는 OSMU 전략",
    )
    popup = article(
        "K팝 팬들이 팝업 오픈런에 나서는 이유",
        "팝업스토어가 팬덤 소비의 기본 동선으로 자리매김",
    )

    assert classify_market_trend_article(immersive).category == "체험형 콘텐츠 + 공연"
    assert classify_market_trend_article(ip).category == "IP/OSMU"
    assert classify_market_trend_article(popup).category == "팝업/공간"


def test_classify_market_trend_article_does_not_match_ip_inside_english_words():
    generic = article(
        "Philip Barantini Takes a Trip to Cannes",
        "A director joins a studio thriller without franchise expansion context.",
    )

    assert classify_market_trend_article(generic) is None


def test_classify_market_trend_article_ignores_search_query_without_context():
    generic = article("일반 배우 인터뷰", "시장동향과 무관한 작품 홍보 기사")
    generic.matched_keywords = ["IP 사업 OSMU 굿즈 공연"]

    assert classify_market_trend_article(generic) is None


def test_build_market_trends_creates_business_notes_and_limits_per_category():
    articles = [
        article("바우어랩 이머시브 콘텐츠 올빗 공개", "공간 재해석과 참여형 스토리텔링"),
        article("선거 테마 야외 방탈출 운영", "공공 콘텐츠를 게임 문화 체험과 접목"),
        article("아이돌 팝업스토어 오픈런", "한정 굿즈와 포토카드 중심의 팬덤 문화"),
        article("웹툰 IP 팝업에 1만5000명 방문", "지역 관광 수요를 견인"),
        article("일반 배우 인터뷰", "시장동향 키워드 없음"),
    ]

    trends = build_market_trends(articles, limit_per_category=1)

    assert [item.category for item in trends] == ["체험형 콘텐츠 + 공연", "IP/OSMU", "팝업/공간"]
    assert all(item.frame for item in trends)
    assert all(item.note for item in trends)
    assert all(item.implication for item in trends)
    assert "일반 배우 인터뷰" not in [item.title for item in trends]


def test_enrich_market_trends_without_ai_command_keeps_rule_based_summary():
    item = MarketTrendItem(
        id="m1",
        category="팝업/공간",
        title="아이돌 팝업스토어 오픈런",
        url="https://example.com/popup",
        source="테스트뉴스",
        frame="팝업이 팬덤 소비 동선으로 자리매김",
        note="한정 굿즈 중심의 방문 동선.",
        implication="극장 공간 운영에 참고.",
    )

    enriched = enrich_market_trends_with_ai([item], command=None)

    assert enriched[0].frame == item.frame
    assert enriched[0].note == item.note
    assert enriched[0].implication == item.implication


def test_enrich_market_trends_uses_ai_json_when_command_succeeds():
    item = MarketTrendItem(
        id="m1",
        category="팝업/공간",
        title="아이돌 팝업스토어 오픈런",
        url="https://example.com/popup",
        source="테스트뉴스",
        frame="old",
        note="old",
        implication="old",
    )
    command = [
        sys.executable,
        "-c",
        (
            "import json;"
            "print(json.dumps([{'id':'m1','frame':'AI 프레임','note':'AI 단평','implication':'AI 시사점'}], ensure_ascii=False))"
        ),
    ]

    enriched = enrich_market_trends_with_ai([item], command=command)

    assert enriched[0].frame == "AI 프레임"
    assert enriched[0].note == "AI 단평"
    assert enriched[0].implication == "AI 시사점"


def test_enrich_market_trends_falls_back_when_ai_command_fails():
    item = MarketTrendItem(
        id="m1",
        category="IP/OSMU",
        title="티니핑 IP 확장 가속화",
        url="https://example.com/ip",
        source="테스트뉴스",
        frame="rule frame",
        note="rule note",
        implication="rule implication",
    )

    enriched = enrich_market_trends_with_ai(
        [item],
        command=[sys.executable, "-c", "raise SystemExit(2)"],
    )

    assert enriched[0].frame == "rule frame"
    assert enriched[0].note == "rule note"
    assert enriched[0].implication == "rule implication"


def test_parse_naver_news_items_returns_articles_with_clean_text():
    payload = {
        "items": [
            {
                "title": "<b>팝업스토어</b> 오픈런",
                "description": "한정 <b>굿즈</b>와 팬덤 소비",
                "originallink": "https://example.com/original",
                "link": "https://n.news.naver.com/article/1",
                "pubDate": "Wed, 20 May 2026 08:00:00 +0900",
            }
        ]
    }

    articles = parse_naver_news_items(payload, query="팝업스토어 팬덤")

    assert articles[0].title == "팝업스토어 오픈런"
    assert articles[0].summary == "한정 굿즈와 팬덤 소비"
    assert articles[0].url == "https://example.com/original"
    assert articles[0].matched_keywords == ["팝업스토어 팬덤"]


def test_parse_public_naver_news_items_extracts_news_results():
    html = """
    <html>
      <body>
        <a href="https://search.naver.com/search.naver?where=news">뉴스 탭</a>
        <div class="news_area">
          <a class="news_tit" href="https://example.com/popup">
            성수 팝업스토어 오픈런, 한정 굿즈 완판
          </a>
          <div class="news_dsc">팬덤 소비와 브랜드 체험을 결합했다</div>
        </div>
        <a href="/internal">무시할 링크</a>
      </body>
    </html>
    """

    articles = parse_public_naver_news_items(html, query="팝업스토어 팬덤")

    assert len(articles) == 1
    assert articles[0].title == "성수 팝업스토어 오픈런, 한정 굿즈 완판"
    assert articles[0].summary == "팬덤 소비와 브랜드 체험을 결합했다"
    assert articles[0].url == "https://example.com/popup"
    assert articles[0].source == "Naver News"


def test_parse_google_news_rss_items_extracts_publisher_and_title():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <item>
          <title>몰입형 전시공간 확대, 극장형 체험 강화 - 전자신문</title>
          <link>https://news.google.com/rss/articles/example</link>
          <description>이머시브 콘텐츠와 참여형 스토리텔링이 결합했다</description>
          <pubDate>Wed, 20 May 2026 08:00:00 GMT</pubDate>
          <source url="https://example.com">전자신문</source>
        </item>
      </channel>
    </rss>
    """

    articles = parse_google_news_rss_items(xml, query="이머시브 콘텐츠")

    assert len(articles) == 1
    assert articles[0].title == "몰입형 전시공간 확대, 극장형 체험 강화"
    assert articles[0].summary == "이머시브 콘텐츠와 참여형 스토리텔링이 결합했다"
    assert articles[0].source == "전자신문"


def test_parse_google_news_rss_items_preserves_spaces_before_regular_words():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <item>
          <title>K팝 팬들이 팝업 오픈런에 나서는 이유 - 네이트</title>
          <link>https://news.google.com/rss/articles/popup</link>
          <description>대박 터진 이베이 사례와 구분되어야 한다</description>
          <source url="https://example.com">네이트</source>
        </item>
      </channel>
    </rss>
    """

    articles = parse_google_news_rss_items(xml, query="팝업스토어 팬덤")

    assert articles[0].title == "K팝 팬들이 팝업 오픈런에 나서는 이유"
    assert articles[0].summary == "대박 터진 이베이 사례와 구분되어야 한다"


def test_naver_news_get_with_retry_recovers_after_transient_failure(monkeypatch):
    monkeypatch.setattr("crawler.market_trends.time.sleep", lambda *a, **k: None)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)  # 첫 시도 실패
        return httpx.Response(200, json={"items": [{
            "title": "와일드 씽 시사회",
            "description": "롯데엔터테인먼트 공식",
            "originallink": "https://example.com/wild",
            "pubDate": "Tue, 20 May 2026 10:00:00 +0900",
        }]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    response = _naver_news_get_with_retry(client, "와일드 씽", 5, "id", "secret")
    articles = parse_naver_news_items(response.json(), query="와일드 씽")

    assert calls["n"] == 2  # 재시도로 성공
    assert articles[0].title == "와일드 씽 시사회"


def test_fetch_market_trend_articles_falls_back_to_public_when_open_api_fails(monkeypatch):
    monkeypatch.setattr("crawler.market_trends.time.sleep", lambda *a, **k: None)

    def boom(*args, **kwargs):
        raise RuntimeError("naver open api down")

    monkeypatch.setattr("crawler.market_trends._naver_news_get_with_retry", boom)
    sentinel = [article("와일드 씽 공개검색 결과")]
    monkeypatch.setattr(
        "crawler.market_trends.fetch_market_trend_fallback_articles",
        lambda queries, display: sentinel,
    )

    out = fetch_market_trend_articles_from_naver(
        "id", "secret", queries=["와일드 씽"], display=5, public_fallback=True,
    )

    assert out == sentinel  # 오픈 API 실패 → 공개검색 폴백으로 확보


def test_fetch_market_trend_articles_no_fallback_returns_empty_on_failure(monkeypatch):
    monkeypatch.setattr("crawler.market_trends.time.sleep", lambda *a, **k: None)

    def boom(*args, **kwargs):
        raise RuntimeError("naver open api down")

    monkeypatch.setattr("crawler.market_trends._naver_news_get_with_retry", boom)

    def fail_fallback(queries, display):
        raise AssertionError("public_fallback=False면 폴백을 쓰면 안 됨")

    monkeypatch.setattr("crawler.market_trends.fetch_market_trend_fallback_articles", fail_fallback)

    out = fetch_market_trend_articles_from_naver(
        "id", "secret", queries=["와일드 씽"], display=5, public_fallback=False,
    )

    assert out == []
