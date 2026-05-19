from crawler.policies import (
    _mcst_support_item,
    parse_kocca_support_notices,
    parse_kofic_business_notices,
    policy_relevance_summary,
)


def test_parse_kofic_business_notices_extracts_recent_film_support_items():
    html = """
    <table>
      <tr><th>번호</th><th>분류</th><th>제목</th><th>작성일자</th></tr>
      <tr>
        <td>1</td><td>공고</td>
        <td><a href="/kofic/business/prom/promotionBoardDetail.do?seqNo=17677">2026년 독립예술영화 제작지원 사업 공고</a></td>
        <td>2026.05.14</td>
      </tr>
    </table>
    """

    items = parse_kofic_business_notices(html)

    assert len(items) == 1
    assert items[0].source == "영화진흥위원회"
    assert items[0].category == "공고"
    assert "제작지원" in items[0].title


def test_policy_relevance_summary_marks_support_program():
    assert policy_relevance_summary("2026년 국민 영화관람 활성화 지원사업 공고") == "영화 지원사업"


def test_parse_kocca_support_notices_extracts_content_support_items():
    html = """
    <table>
      <tr><th>구분</th><th>제목</th><th>공고일</th><th>접수기간</th><th>조회</th></tr>
      <tr>
        <td>모집공모</td>
        <td><a href="/kocca/pims/view.do?intcNo=326D00001001&menuNo=204104">2026 콘텐츠 스타트업 해외마켓 참가기업 모집 공고</a></td>
        <td>26.03.16</td>
        <td>26.03.16 ~ 26.03.30</td>
        <td>618</td>
      </tr>
      <tr>
        <td>모집공모</td>
        <td><a href="/kocca/pims/view.do?intcNo=326D00101001&menuNo=204104">2026년 관계부처 합동 한류마케팅 참가기업 모집</a></td>
        <td>26.05.19</td>
        <td>26.05.19 ~ 26.06.09</td>
        <td>55</td>
      </tr>
      <tr>
        <td>일반공지</td>
        <td><a href="/kocca/pims/view.do?intcNo=326D00001002&menuNo=204104">기관 휴무 안내</a></td>
        <td>26.03.15</td>
        <td></td>
        <td>12</td>
      </tr>
    </table>
    """

    items = parse_kocca_support_notices(html)

    assert len(items) == 2
    assert items[0].source == "한국콘텐츠진흥원"
    assert items[0].category == "모집공모"
    assert "콘텐츠 스타트업" in items[0].title
    assert items[0].url == "https://www.kocca.kr/kocca/pims/view.do?intcNo=326D00001001&menuNo=204104"
    assert items[1].title == "2026년 관계부처 합동 한류마케팅 참가기업 모집"


def test_mcst_support_item_skips_unrelated_page_title_even_if_text_mentions_movie():
    html = """
    <h3>정보공개</h3>
    <p>영화 관련 문구가 페이지 공통 영역에 있습니다.</p>
    """

    assert _mcst_support_item(html) == []
