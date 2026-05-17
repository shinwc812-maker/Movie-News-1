"""씨네21 뉴스 페이지의 HTML 구조 탐색용 일회성 스크립트.

기사 카드의 후보 컨테이너를 찾아 첫 카드의 HTML을 출력한다.
"""

import sys

import httpx
from selectolax.parser import HTMLParser

URL = "https://www.cine21.com/news"
HEADERS = {"User-Agent": "MovieNewsBot/0.1 (personal use)"}


def main() -> None:
    resp = httpx.get(URL, headers=HEADERS, timeout=15, follow_redirects=True)
    resp.encoding = "utf-8"
    print(f"status={resp.status_code} len={len(resp.text)}", file=sys.stderr)

    tree = HTMLParser(resp.text)

    # 기사 카드 컨테이너 후보 셀렉터들을 훑어본다.
    candidates = [
        "ul.news_list li",
        ".news_list li",
        "div.news_list .item",
        "li.news",
        "div.mov_list li",
        "article",
        ".list_news li",
        "ul li a[href*='/news/view/']",
    ]
    for sel in candidates:
        nodes = tree.css(sel)
        print(f"{sel!r:40s} -> {len(nodes)} nodes", file=sys.stderr)

    # /news/view/ 링크가 들어있는 가장 가까운 반복 단위를 찾는다.
    links = tree.css("a[href*='/news/view/']")
    print(f"\n/news/view/ links: {len(links)}", file=sys.stderr)
    if links:
        first = links[0]
        print("\n--- first /news/view/ link ---")
        print(first.html)
        # 부모 2단계까지 출력
        parent = first.parent
        for depth in range(1, 4):
            if parent is None:
                break
            print(f"\n--- ancestor depth {depth} (tag={parent.tag}, "
                  f"class={parent.attributes.get('class')}) ---")
            html = parent.html or ""
            print(html[:2000])
            parent = parent.parent


if __name__ == "__main__":
    main()
