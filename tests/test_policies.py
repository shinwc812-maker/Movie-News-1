from crawler.policies import parse_kofic_business_notices, policy_relevance_summary


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
