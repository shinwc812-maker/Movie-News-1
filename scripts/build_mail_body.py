"""data/ai_briefing.json → 메일 본문(텍스트 또는 HTML) 생성.

사용:
    python scripts/build_mail_body.py            # 텍스트(기본, 호환용)
    python scripts/build_mail_body.py text       # 텍스트 명시
    python scripts/build_mail_body.py html       # HTML(권장)

워크플로우는 두 가지를 모두 만들어 메일 액션에 body / html_body로 전달한다.
"""

from __future__ import annotations

import html as _html
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
BRIEFING_PATH = ROOT / "data" / "ai_briefing.json"
ARTICLES_PATH = ROOT / "data" / "articles.json"
KST = ZoneInfo("Asia/Seoul")
REPO_URL = "https://github.com/shinwc812-maker/Movie-News-1"
DASHBOARD_URL = "https://shinwc812-maker.github.io/Movie-News-1/"

CITE_PATTERN = re.compile(r"\[([^\]\[\n]{1,40})\]")


# ---------- 공통 ----------

def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _format_generated_kst(briefing: dict) -> str:
    gen = briefing.get("generated_at")
    if not gen:
        return ""
    try:
        dt = datetime.fromisoformat(gen)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M KST")
    except ValueError:
        return ""


# ---------- 인용 → 링크 ----------

def _build_source_link_map(articles) -> dict[str, dict]:
    by_source: dict[str, dict] = {}
    for a in articles or []:
        src = str(a.get("source") or "").strip()
        url = a.get("url")
        if not src or not url:
            continue
        score = float(a.get("score") or 0)
        existing = by_source.get(src)
        if existing is None or score > existing["score"]:
            by_source[src] = {
                "url": url,
                "score": score,
                "title": (a.get("title_ko") or a.get("title") or ""),
            }
    return by_source


def _linkify_html(text: str, smap: dict[str, dict]) -> str:
    """[매체명] → <a> 인라인 링크(이메일 호환 인라인 스타일)."""
    if not text:
        return ""
    escaped = _html.escape(text)

    def _repl(m):
        src = m.group(1).strip()
        entry = smap.get(src)
        if entry is None:
            target = src.casefold().replace(" ", "")
            for k, v in smap.items():
                if k.casefold().replace(" ", "") == target:
                    entry = v
                    break
        if not entry:
            return f"[{_html.escape(src)}]"
        return (
            f'<a href="{_html.escape(entry["url"])}" '
            f'style="color:#1d4ed8;text-decoration:none;font-weight:700;" '
            f'title="{_html.escape(entry["title"])}">[{_html.escape(src)}]</a>'
        )

    return CITE_PATTERN.sub(_repl, escaped)


# ---------- 텍스트 본문(fallback) ----------

def render_text(b: dict) -> str:
    lines: list[str] = []
    gen = _format_generated_kst(b)
    if gen:
        lines.append(f"생성: {gen}")
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
            head = f"• {c.get('title','')}"
            if c.get("distributor"):
                head += f" ({c['distributor']})"
            if c.get("note"):
                head += f" — {c['note']}"
            lines.append(head)
        lines.append("")

    if b.get("new_trends"):
        lines.append("━━ 신규 트렌드 ━━")
        for x in b["new_trends"]:
            line = f"• [{x.get('label','')}] {x.get('note','')}"
            if x.get("implication"):
                line += f"  → {x['implication']}"
            lines.append(line)
        lines.append("")

    if b.get("industry_signals"):
        lines.append("━━ 산업 시그널 ━━")
        for x in b["industry_signals"]:
            line = f"• [{x.get('label','')}] {x.get('note','')}"
            if x.get("implication"):
                line += f"  → {x['implication']}"
            lines.append(line)
        lines.append("")

    if b.get("overseas_brief"):
        lines.append("━━ 외신 핵심 ━━")
        for o in b["overseas_brief"]:
            lines.append(f"• {o.get('title_ko','')}")
            if o.get("summary_ko"):
                lines.append(f"  {o['summary_ko']}")
            if o.get("implication"):
                lines.append(f"  시사점: {o['implication']}")
            if o.get("source_url"):
                lines.append(f"  {o['source_url']}")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"대시보드: {DASHBOARD_URL}")
    lines.append(f"저장소:   {REPO_URL}")
    return "\n".join(lines) + "\n"


# ---------- HTML 본문 ----------

def _esc(s) -> str:
    return _html.escape(str(s or ""))


def _ul(items_html: list[str], color: str = "#374151") -> str:
    if not items_html:
        return ""
    lis = "".join(
        f'<li style="margin-bottom:3px;">{x}</li>' for x in items_html if x
    )
    return (
        f'<ul style="margin:4px 0 0;padding-left:20px;color:{color};'
        f'font-size:13px;line-height:1.55;">{lis}</ul>'
    )


def _block(title: str, inner: str, *, head_color: str = "#111827") -> str:
    """일반 박스(베이지 톤)."""
    return (
        '<div style="background:#fffef5;border:1px solid #efe9c4;'
        'border-radius:8px;padding:11px 13px;height:100%;box-sizing:border-box;">'
        f'<div style="margin:0 0 6px;font-size:13px;font-weight:800;'
        f'color:{head_color};">{title}</div>'
        f'{inner}'
        '</div>'
    )


def _own_block(items: list[dict], L) -> str:
    """자사 작품 블록 — 빨간 테두리 강조."""
    inner_parts = []
    for i, t in enumerate(items or []):
        title = _esc(t.get("title", ""))
        kind = _esc(t.get("kind_label", ""))
        kind_tag = (
            f'<span style="display:inline-block;margin-left:6px;border-radius:999px;'
            f'padding:1px 8px;background:#fee2e2;color:#b91c1c;font-size:11px;'
            f'font-weight:800;">{kind}</span>'
            if kind else ""
        )
        sep = (
            'border-top:1px dashed #fecaca;padding-top:7px;margin-top:7px;'
            if i > 0 else ""
        )
        highlights = _ul(
            [L(h) for h in (t.get("highlights") or [])],
            color="#374151",
        )
        risks_lis = [f"▼ {L(r)}" for r in (t.get("risks") or [])]
        risks = _ul(risks_lis, color="#b91c1c") if risks_lis else ""
        inner_parts.append(
            f'<div style="{sep}">'
            f'<div style="font-size:14px;font-weight:800;color:#111827;">'
            f'{title}{kind_tag}</div>'
            f'{highlights}{risks}'
            f'</div>'
        )
    if not inner_parts:
        return ""
    return (
        '<div style="margin:10px 12px;background:#fef2f2;border:2px solid #dc2626;'
        'border-radius:8px;padding:12px 14px;">'
        '<div style="margin:0 0 8px;font-size:14px;font-weight:800;color:#b91c1c;">'
        '📌 자사 작품 위치</div>'
        f'{"".join(inner_parts)}'
        '</div>'
    )


def _tag(label: str, bg: str = "#e0ecff", color: str = "#1d4ed8") -> str:
    if not label:
        return ""
    return (
        f'<span style="display:inline-block;margin-right:4px;border-radius:999px;'
        f'padding:0 7px;background:{bg};color:{color};font-size:11px;'
        f'font-weight:800;">{_esc(label)}</span>'
    )


def _competitors_block(items, L) -> str:
    if not items:
        return ""
    lis = []
    for c in items:
        title = _esc(c.get("title", ""))
        dist = _esc(c.get("distributor", ""))
        dist_html = (
            f' <span style="color:#6b7280;font-size:12px;">({dist})</span>'
            if dist else ""
        )
        note = L(c.get("note", ""))
        lis.append(f"<b>{title}</b>{dist_html} — {note}")
    return _block("🎬 경쟁작 동향", _ul(lis))


def _trend_block(items, L, *, label: str) -> str:
    if not items:
        return ""
    lis = []
    for x in items:
        tag = _tag(x.get("label", ""))
        note = L(x.get("note", ""))
        impl_html = ""
        if x.get("implication"):
            impl = L(x.get("implication", ""))
            impl_html = (
                f' <b style="color:#047857;">— {impl}</b>'
            )
        lis.append(f"{tag}{note}{impl_html}")
    return _block(label, _ul(lis))


def _overseas_block(items, L) -> str:
    if not items:
        return ""
    parts = []
    for i, o in enumerate(items):
        title = _esc(o.get("title_ko", ""))
        url = o.get("source_url", "")
        title_html = (
            f'<a href="{_esc(url)}" style="color:#1d4ed8;text-decoration:none;">{title}</a>'
            if url else title
        )
        sep = (
            'border-top:1px dashed #efe9c4;padding-top:6px;margin-top:6px;'
            if i > 0 else ""
        )
        summary = L(o.get("summary_ko", ""))
        impl = L(o.get("implication", ""))
        src = _esc(o.get("source", "") or "외신")
        impl_line = (
            f'<div style="color:#6b7280;font-size:11px;margin-top:2px;">'
            f'{src} · 시사점: {impl}</div>'
            if o.get("implication") else ""
        )
        parts.append(
            f'<div style="{sep}">'
            f'<div style="font-weight:700;font-size:13px;color:#111827;">{title_html}</div>'
            f'<div style="color:#374151;font-size:12px;line-height:1.5;margin-top:2px;">{summary}</div>'
            f'{impl_line}'
            '</div>'
        )
    return _block("🌐 외신 핵심", "".join(parts))


def render_html(b: dict, articles: list) -> str:
    smap = _build_source_link_map(articles)
    L = lambda s: _linkify_html(s, smap)

    gen = _format_generated_kst(b)
    headline = L(b.get("headline_today", ""))
    summary = L(b.get("summary", ""))

    headline_html = (
        f'<p style="margin:8px 0 4px;font-size:14px;font-weight:800;color:#92400e;">{headline}</p>'
        if headline else ""
    )
    summary_html = (
        f'<p style="margin:0;color:#374151;font-size:13px;line-height:1.6;">{summary}</p>'
        if summary else ""
    )

    own = _own_block(b.get("own_titles") or [], L)
    comp = _competitors_block(b.get("competitors") or [], L)
    trends = _trend_block(b.get("new_trends") or [], L, label="🔥 신규 트렌드")
    signals = _trend_block(b.get("industry_signals") or [], L, label="📡 산업 시그널")
    overseas = _overseas_block(b.get("overseas_brief") or [], L)

    # 2x2 그리드 (이메일 호환을 위해 table 사용)
    def _cell(content: str) -> str:
        return (
            '<td valign="top" width="50%" style="padding:0 4px 8px 4px;">'
            f'{content or ""}'
            '</td>'
        )

    grid_rows = []
    if comp or trends:
        grid_rows.append(
            f'<tr>{_cell(comp)}{_cell(trends)}</tr>'
        )
    if signals or overseas:
        grid_rows.append(
            f'<tr>{_cell(signals)}{_cell(overseas)}</tr>'
        )
    grid_html = (
        '<table width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="border-collapse:collapse;margin:0;padding:0 8px;">'
        f'{"".join(grid_rows)}'
        '</table>'
        if grid_rows else ""
    )

    return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#f1f5f9;">
<div style="max-width:760px;margin:18px auto;font-family:-apple-system,'Apple SD Gothic Neo','Malgun Gothic',Arial,sans-serif;color:#1f2937;">
  <div style="background:#fdfbe9;border:1px solid #e3deb6;border-radius:10px 10px 0 0;padding:16px 18px 12px;">
    <div style="display:flex;align-items:baseline;justify-content:space-between;gap:12px;">
      <div style="font-size:17px;font-weight:800;color:#1f2937;">
        🤖 오늘의 AI 브리핑
        <span style="background:#d97706;color:#fff;font-size:11px;padding:2px 7px;border-radius:4px;font-weight:800;margin-left:4px;vertical-align:2px;">AI SUMMARY</span>
      </div>
      <div style="color:#94a3b8;font-size:11px;">{_esc(gen)}</div>
    </div>
    {headline_html}
    {summary_html}
  </div>
  {own}
  <div style="background:#fdfbe9;border-left:1px solid #e3deb6;border-right:1px solid #e3deb6;padding:6px 0;">
    {grid_html}
  </div>
  <div style="background:#fdfbe9;border:1px solid #e3deb6;border-top:1px dashed #e3deb6;border-radius:0 0 10px 10px;padding:12px 18px;text-align:center;">
    <a href="{_esc(DASHBOARD_URL)}" style="color:#1d4ed8;font-weight:800;text-decoration:none;font-size:14px;">📊 전체 대시보드 보기 →</a>
    <div style="color:#94a3b8;font-size:11px;margin-top:6px;"><a href="{_esc(REPO_URL)}" style="color:#94a3b8;text-decoration:none;">소스 저장소</a></div>
  </div>
</div>
</body></html>
"""


# ---------- main ----------

def main() -> int:
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else "text"
    briefing = _load_json(BRIEFING_PATH, None)
    if not briefing:
        sys.stdout.write("(브리핑 JSON이 없습니다.)\n")
        return 0
    if mode == "html":
        articles = _load_json(ARTICLES_PATH, [])
        sys.stdout.write(render_html(briefing, articles))
    else:
        sys.stdout.write(render_text(briefing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
