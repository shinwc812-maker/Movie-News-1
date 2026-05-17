"""맥스무비 홈페이지 구조 탐색용 일회성 스크립트.

Next.js SSR 사이트로 추정. <script id="__NEXT_DATA__"> JSON 우선,
없으면 일반 HTML 파싱 폴백을 판단하기 위한 탐색.
"""

import json
import sys

import httpx
from selectolax.parser import HTMLParser

URL = "https://www.maxmovie.com/"

# 봇 User-Agent가 403을 유발하면 브라우저 UA로 폴백 탐색.
UAS = {
    "bot": "MovieNewsBot/0.1 (personal use)",
    "browser": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}


def walk_keys(obj, depth=0, max_depth=4):
    """JSON 트리에서 리스트형 데이터가 들어있는 키 경로를 대략 출력."""
    if depth > max_depth:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, list) and v:
                print(f"  {'  ' * depth}{k}: list[{len(v)}]", file=sys.stderr)
            elif isinstance(v, (dict, list)):
                print(f"  {'  ' * depth}{k}: {type(v).__name__}", file=sys.stderr)
                walk_keys(v, depth + 1, max_depth)


def main() -> None:
    for label, ua in UAS.items():
        try:
            resp = httpx.get(URL, headers={"User-Agent": ua}, timeout=15,
                             follow_redirects=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[{label}] 요청 실패: {exc}", file=sys.stderr)
            continue

        print(f"\n===== UA={label} status={resp.status_code} "
              f"len={len(resp.text)} =====", file=sys.stderr)
        if resp.status_code != 200:
            continue

        tree = HTMLParser(resp.text)
        next_data = tree.css_first("script#__NEXT_DATA__")
        print(f"__NEXT_DATA__ present: {next_data is not None}", file=sys.stderr)

        if next_data is not None:
            try:
                data = json.loads(next_data.text())
            except json.JSONDecodeError as exc:
                print(f"  JSON 파싱 실패: {exc}", file=sys.stderr)
            else:
                print("--- __NEXT_DATA__ key tree ---", file=sys.stderr)
                walk_keys(data)
                print("\n--- raw __NEXT_DATA__ (first 1500 chars) ---")
                print(json.dumps(data, ensure_ascii=False)[:1500])
            return

        # 폴백: /news/<id> 패턴 링크 탐색
        links = tree.css("a[href*='/news/']")
        print(f"/news/ links: {len(links)}", file=sys.stderr)
        for a in links[:5]:
            print(" ", a.attributes.get("href"), "|",
                  a.text(strip=True)[:60], file=sys.stderr)
        if links:
            node = links[0]
            for depth in range(1, 4):
                node = node.parent
                if node is None:
                    break
                print(f"\n--- ancestor depth {depth} tag={node.tag} "
                      f"class={node.attributes.get('class')} ---")
                print((node.html or "")[:1200])
        return


if __name__ == "__main__":
    main()
