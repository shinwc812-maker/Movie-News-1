"""중복 기사 제거.

여러 매체가 같은 사건을 보도한 경우 제목 유사도로 묶어, 그룹에서 점수가
가장 높은 기사 하나만 남긴다. 한국어 기사와 영어 기사는 절대 같은 그룹으로
묶지 않는다(country가 다르면 비교 자체를 하지 않음).
"""

from rapidfuzz import fuzz

from crawler.models import Article

SIMILARITY_THRESHOLD = 85


def dedupe(articles: list[Article]) -> list[Article]:
    """제목 유사도 기반 중복 제거. 그룹별로 최고 점수 기사만 남긴다.

    하루 수백 건 수준이라 단순 O(n^2) 비교로 충분하다.
    """
    representatives: list[Article] = []
    for article in articles:
        matched_index = None
        for index, rep in enumerate(representatives):
            # country가 다르면(한국어 vs 영어) 비교하지 않는다.
            if rep.country != article.country:
                continue
            ratio = fuzz.token_set_ratio(rep.title, article.title)
            if ratio >= SIMILARITY_THRESHOLD:
                matched_index = index
                break

        if matched_index is None:
            representatives.append(article)
        elif article.score > representatives[matched_index].score:
            # 같은 그룹 — 점수가 더 높으면 대표 교체
            representatives[matched_index] = article

    return representatives
