"""data/ai_briefing.json을 사람이 읽기 좋은 메일 본문으로 변환.

사용: python scripts/build_mail_body.py > mail_body.txt
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BRIEFING_PATH = Path(__file__).resolve().parent.parent / "data" / "ai_briefing.json"
KST = ZoneInfo("Asia/Seoul")
REPO_URL = "https://github.com/shyain456/Movie-News"


def main() -> int:
    if not BRIEFING_PATH.exists():
        print("(브리핑 JSON이 없습니다.)")
        return 0
    b = json.loads(BRIEFING_PATH.read_text(encoding="utf-8"))

    gen_iso = b.get("generated_at")
    gen_kst = ""
    if gen_iso:
        try:
            dt = datetime.fromisoformat(gen_iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            gen_kst = dt.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")
        except ValueError:
            pass

    lines: list[str] = []
    if gen_kst:
        lines.append(f"생성: {gen_kst}")
        lines.append("")
    if b.get("headline_today"):
        lines.append(f"■ {b['headline_today']}")
        lines.append("")
    if b.get("summary"):
        lines.append(b["summary"])
        lines.append("")

    if b.get("own_titles"):
        lines.append("━━ 자사 작품 위치 ━━")
        for t in b["own_titles"]:
            title = t.get("title", "")
            kind = t.get("kind_label", "")
            lines.append(f"▶ {title}" + (f"  [{kind}]" if kind else ""))
            for h in t.get("highlights") or []:
                lines.append(f"   • {h}")
            for r in t.get("risks") or []:
                lines.append(f"   ▼ {r}")
        lines.append("")

    if b.get("competitors"):
        lines.append("━━ 경쟁작 동향 ━━")
        for c in b["competitors"]:
            title = c.get("title", "")
            dist = c.get("distributor", "")
            note = c.get("note", "")
            head = f"• {title}" + (f" ({dist})" if dist else "")
            lines.append(head + (f" — {note}" if note else ""))
        lines.append("")

    if b.get("new_trends"):
        lines.append("━━ 신규 트렌드 ━━")
        for x in b["new_trends"]:
            label = x.get("label", "")
            note = x.get("note", "")
            impl = x.get("implication", "")
            line = f"• [{label}] {note}" if label else f"• {note}"
            if impl:
                line += f"  → {impl}"
            lines.append(line)
        lines.append("")

    if b.get("industry_signals"):
        lines.append("━━ 산업 시그널 ━━")
        for x in b["industry_signals"]:
            label = x.get("label", "")
            note = x.get("note", "")
            impl = x.get("implication", "")
            line = f"• [{label}] {note}" if label else f"• {note}"
            if impl:
                line += f"  → {impl}"
            lines.append(line)
        lines.append("")

    if b.get("overseas_brief"):
        lines.append("━━ 외신 핵심 ━━")
        for o in b["overseas_brief"]:
            t = o.get("title_ko", "")
            s = o.get("summary_ko", "")
            impl = o.get("implication", "")
            url = o.get("source_url", "")
            lines.append(f"• {t}")
            if s:
                lines.append(f"  {s}")
            if impl:
                lines.append(f"  시사점: {impl}")
            if url:
                lines.append(f"  {url}")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"전체 대시보드: {REPO_URL}")
    lines.append("(원격 PC에서 git pull 후 dist/index.html 더블클릭)")

    sys.stdout.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
