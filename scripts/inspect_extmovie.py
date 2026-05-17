"""익스트림무비 홈페이지 '뉴스' 섹션 구조 탐색용 일회성 스크립트."""

import sys

import httpx
from selectolax.parser import HTMLParser

URL = "https://extmovie.com/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


def main() -> None:
    resp = httpx.get(URL, headers=HEADERS, timeout=15, follow_redirects=True)
    resp.encoding = "utf-8"
    print(f"status={resp.status_code} len={len(resp.text)}", file=sys.stderr)
    tree = HTMLParser(resp.text)

    # '뉴스' 라는 텍스트를 가진 헤더/제목 요소 주변을 찾는다.
    for node in tree.css("h1, h2, h3, h4, strong, span, a, div"):
        text = node.text(strip=True)
        if text in ("뉴스", "영화뉴스", "NEWS", "익스트림 뉴스"):
            print(f"  found heading {text!r} tag={node.tag} "
                  f"class={node.attributes.get('class')}", file=sys.stderr)

    # 게시판 글 링크 후보 패턴
    patterns = [
        "a[href*='/news']",
        "a[href*='document_srl']",
        "a[href*='/movienews']",
        "a[href*='extmovie.com/']",
    ]
    for sel in patterns:
        nodes = tree.css(sel)
        print(f"{sel!r:34s} -> {len(nodes)}", file=sys.stderr)
        for a in nodes[:4]:
            print("    ", a.attributes.get("href"), "|",
                  a.text(strip=True)[:50], file=sys.stderr)

    # 본문에서 상대시간 표기 샘플 수집
    import re
    rel = re.findall(r"\d+\s*(?:분|시간|일)\s*전|방금\s*전|\d{4}\.\d{2}\.\d{2}",
                     resp.text)
    print(f"\n상대/절대 시간 표기 샘플: {rel[:15]}", file=sys.stderr)

    # 첫 번째 그럴듯한 뉴스 링크의 카드 구조 출력
    links = tree.css("a[href*='/news']")
    if links:
        node = links[0]
        for depth in range(1, 5):
            node = node.parent
            if node is None:
                break
            print(f"\n--- ancestor depth {depth} tag={node.tag} "
                  f"class={node.attributes.get('class')} ---")
            print((node.html or "")[:1400])


if __name__ == "__main__":
    main()
