from crawler.community import parse_extmovie_community_cards, summarize_reaction_mood


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
