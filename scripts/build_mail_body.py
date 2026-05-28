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
MARKET_PATH = ROOT / "data" / "market.json"
RESERVATION_PATH = ROOT / "data" / "reservation.json"
OVERSEAS_PATH = ROOT / "data" / "overseas_weekend.json"
MARKET_TRENDS_PATH = ROOT / "data" / "market_trends.json"
COMMUNITY_PATH = ROOT / "data" / "community.json"
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

def render_text(b: dict, market: dict | None = None, reservation: dict | None = None,
                overseas: dict | None = None, trend_count: int = 0, comm_count: int = 0) -> str:
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

    # KPI 요약
    box0 = ((market or {}).get("movies") or [{}])[0]
    res0 = ((reservation or {}).get("movies") or [{}])[0]
    if box0 or res0 or trend_count or comm_count:
        lines.append("━━ 핵심 지표 ━━")
        if box0:
            aud = _fmt_int(box0.get("audi_count"))
            inten = box0.get("audi_inten")
            change = box0.get("audi_change")
            try:
                inten_i = int(inten) if inten is not None else 0
            except (TypeError, ValueError):
                inten_i = 0
            mark = "▲" if inten_i > 0 else ("▼" if inten_i < 0 else "")
            pct = f"{float(change):+.1f}%" if change is not None else ""
            delta = f"{mark}{_fmt_int(abs(inten_i))}{(' ('+pct+')') if pct else ''}".strip()
            lines.append(f"  전일 1위: {box0.get('title','')} ({aud}명 / {delta})")
        if res0:
            rate = res0.get("reservation_rate")
            cnt = _fmt_int(res0.get("reservation_count"))
            rate_s = f"{float(rate):.1f}%" if rate is not None else ""
            lines.append(f"  예매 1위: {res0.get('title','')} ({rate_s} / {cnt}매)")
        lines.append(f"  시장동향: {trend_count}건")
        lines.append(f"  커뮤니티 반응: {comm_count}건")
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

    if market and market.get("movies"):
        lines.append("━━ 전일 관객 TOP 5 (KOBIS) ━━")
        for m in (market.get("movies") or [])[:5]:
            aud = _fmt_int(m.get("audi_count"))
            acc = _fmt_int(m.get("audi_acc"))
            lines.append(f"  {m.get('rank','')}. {m.get('title','')} — {aud}명 / 누적 {acc}명")
        lines.append("")

    if reservation and reservation.get("movies"):
        lines.append("━━ 실시간 예매량 TOP 5 (영진위) ━━")
        for m in (reservation.get("movies") or [])[:5]:
            rate = m.get("reservation_rate")
            cnt = _fmt_int(m.get("reservation_count"))
            rate_s = f"{float(rate):.1f}%" if rate is not None else ""
            lines.append(f"  {m.get('rank','')}. {m.get('title','')} — {rate_s} / {cnt}매")
        lines.append("")

    if overseas and overseas.get("movies"):
        label = overseas.get("weekend_label") or ""
        lines.append(f"━━ 해외 주말 TOP 5 (Box Office Mojo{(' · '+label) if label else ''}) ━━")
        for m in (overseas.get("movies") or [])[:5]:
            lines.append(f"  {m.get('rank','')}. {m.get('title','')} — {m.get('gross','')}")
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


def _fmt_int(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return ""


def _fmt_delta_audi(audi_inten, audi_change) -> str:
    """전일대비 증감을 ▲/▼ + 절대수 + 비율로 — 증가 빨강, 감소 파랑."""
    if audi_inten is None and audi_change is None:
        return ""
    try:
        inten = int(audi_inten) if audi_inten is not None else 0
    except (TypeError, ValueError):
        inten = 0
    try:
        change = float(audi_change) if audi_change is not None else 0.0
    except (TypeError, ValueError):
        change = 0.0
    if inten > 0:
        color, mark = "#dc2626", "▲"
    elif inten < 0:
        color, mark = "#1d4ed8", "▼"
    else:
        color, mark = "#6b7280", ""
    abs_n = _fmt_int(abs(inten))
    pct = f"{change:+.1f}%" if change else ""
    parts = [p for p in [mark, abs_n, f"({pct})" if pct else ""] if p]
    inner = " ".join(parts)
    return f'<span style="color:{color};font-weight:800;">{inner}</span>'


def _kpi_block(market: dict, reservation: dict, trend_count: int, comm_count: int) -> str:
    box = (market.get("movies") or [{}])[0] if market else {}
    res = (reservation.get("movies") or [{}])[0] if reservation else {}
    box_title = _esc(box.get("title") or "데이터 없음")
    box_aud = _fmt_int(box.get("audi_count"))
    box_delta = _fmt_delta_audi(box.get("audi_inten"), box.get("audi_change"))
    res_title = _esc(res.get("title") or "데이터 없음")
    res_rate = res.get("reservation_rate")
    res_count = _fmt_int(res.get("reservation_count"))
    res_label = ""
    if res_rate is not None:
        try:
            res_label = f"{float(res_rate):.1f}% / {res_count}매"
        except (TypeError, ValueError):
            res_label = f"{res_count}매" if res_count else ""

    def _cell(label: str, value_html: str) -> str:
        return (
            '<td valign="top" width="25%" style="padding:8px 6px;background:#fff;'
            'border:1px solid #efe9c4;border-radius:6px;">'
            f'<div style="font-size:11px;font-weight:700;color:#92400e;">{label}</div>'
            f'<div style="margin-top:3px;font-size:12px;font-weight:700;color:#111827;">{value_html}</div>'
            '</td>'
        )

    box_val = f'<b>{box_title}</b>'
    if box_aud:
        box_val += f' <span style="color:#6b7280;font-weight:600;">({box_aud}명{(" / " + box_delta) if box_delta else ""})</span>'
    res_val = f'<b>{res_title}</b>'
    if res_label:
        res_val += f' <span style="color:#6b7280;font-weight:600;">({res_label})</span>'

    return (
        '<table width="100%" cellspacing="6" cellpadding="0" border="0" '
        'style="border-collapse:separate;margin:8px 4px 4px;">'
        f'<tr>{_cell("전일 1위", box_val)}{_cell("예매 1위", res_val)}'
        f'{_cell("시장동향", f"<b>{trend_count}건</b>")}'
        f'{_cell("커뮤니티 반응", f"<b>{comm_count}건</b>")}</tr>'
        '</table>'
    )


def _boxoffice_top5_block(market: dict) -> str:
    movies = (market.get("movies") or [])[:5] if market else []
    if not movies:
        return ""
    rows = []
    for m in movies:
        rank = _esc(m.get("rank") or "")
        title = _esc(m.get("title") or "")
        open_date = m.get("open_date") or ""
        open_html = f' <span style="color:#6b7280;font-size:11px;">(개봉 {_esc(open_date)})</span>' if open_date else ""
        aud = _fmt_int(m.get("audi_count"))
        acc = _fmt_int(m.get("audi_acc"))
        delta = _fmt_delta_audi(m.get("audi_inten"), m.get("audi_change"))
        meta_bits = []
        if aud:
            meta_bits.append(f"관객 <b>{aud}명</b>")
        if delta:
            meta_bits.append(f"전일대비 {delta}")
        if acc:
            meta_bits.append(f"누적 {acc}명")
        meta = " · ".join(meta_bits)
        rows.append(
            '<li style="margin-bottom:5px;">'
            f'<span style="display:inline-block;min-width:22px;color:#92400e;font-weight:800;">{rank}.</span>'
            f' <b>{title}</b>{open_html}'
            f'<div style="margin:1px 0 0 22px;color:#374151;font-size:12px;">{meta}</div>'
            '</li>'
        )
    inner = '<ol style="margin:0;padding:0;list-style:none;font-size:13px;line-height:1.55;">' + "".join(rows) + '</ol>'
    return _block("📊 전일 관객 TOP 5  <span style='color:#6b7280;font-size:11px;font-weight:600;'>KOBIS</span>", inner)


def _reservation_top5_block(reservation: dict) -> str:
    movies = (reservation.get("movies") or [])[:5] if reservation else []
    if not movies:
        return ""
    rows = []
    for m in movies:
        rank = _esc(m.get("rank") or "")
        title = _esc(m.get("title") or "")
        rate = m.get("reservation_rate")
        cnt = _fmt_int(m.get("reservation_count"))
        try:
            rate_str = f"{float(rate):.1f}%" if rate is not None else ""
        except (TypeError, ValueError):
            rate_str = ""
        meta_bits = [f"<b>{rate_str}</b>"] if rate_str else []
        if cnt:
            meta_bits.append(f"{cnt}매")
        meta = " · ".join(meta_bits)
        rows.append(
            '<li style="margin-bottom:4px;">'
            f'<span style="display:inline-block;min-width:22px;color:#92400e;font-weight:800;">{rank}.</span>'
            f' <b>{title}</b> <span style="color:#374151;font-size:12px;">— {meta}</span>'
            '</li>'
        )
    inner = '<ol style="margin:0;padding:0;list-style:none;font-size:13px;line-height:1.55;">' + "".join(rows) + '</ol>'
    return _block("🎟️ 실시간 예매량 TOP 5  <span style='color:#6b7280;font-size:11px;font-weight:600;'>영진위 통합전산망</span>", inner)


def _mojo_top5_block(overseas: dict) -> str:
    movies = (overseas.get("movies") or [])[:5] if overseas else []
    if not movies:
        return ""
    label = overseas.get("weekend_label") or ""
    rows = []
    for m in movies:
        rank = _esc(m.get("rank") or "")
        title = _esc(m.get("title") or "")
        url = m.get("url") or ""
        gross = _esc(m.get("gross") or "")
        title_html = (
            f'<a href="{_esc(url)}" style="color:#1d4ed8;text-decoration:none;font-weight:700;">{title}</a>'
            if url else f'<b>{title}</b>'
        )
        rows.append(
            '<li style="margin-bottom:4px;">'
            f'<span style="display:inline-block;min-width:22px;color:#92400e;font-weight:800;">{rank}.</span>'
            f' {title_html} <span style="color:#374151;font-size:12px;">— <b>{gross}</b></span>'
            '</li>'
        )
    sub = f" · {_esc(label)}" if label else ""
    inner = '<ol style="margin:0;padding:0;list-style:none;font-size:13px;line-height:1.55;">' + "".join(rows) + '</ol>'
    return _block(f"🌎 해외 주말 TOP 5  <span style='color:#6b7280;font-size:11px;font-weight:600;'>Box Office Mojo{sub}</span>", inner)


def render_html(b: dict, articles: list, market: dict | None = None,
                reservation: dict | None = None, overseas: dict | None = None,
                trend_count: int = 0, comm_count: int = 0) -> str:
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
    overseas_brief_html = _overseas_block(b.get("overseas_brief") or [], L)

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
    if signals or overseas_brief_html:
        grid_rows.append(
            f'<tr>{_cell(signals)}{_cell(overseas_brief_html)}</tr>'
        )
    grid_html = (
        '<table width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="border-collapse:collapse;margin:0;padding:0 8px;">'
        f'{"".join(grid_rows)}'
        '</table>'
        if grid_rows else ""
    )

    kpi_html = _kpi_block(market or {}, reservation or {}, trend_count, comm_count)
    box_html = _boxoffice_top5_block(market or {})
    res_html = _reservation_top5_block(reservation or {})
    mojo_html = _mojo_top5_block(overseas or {})

    # 본문 헤더 박스(headline + summary)
    head_box = ""
    if headline_html or summary_html:
        head_box = (
            '<div style="background:#fff;border:1px solid #efe9c4;border-radius:8px;'
            'padding:10px 12px;margin:0 0 10px;">'
            f'{headline_html}{summary_html}'
            '</div>'
        )

    # 좌측 본문 — headline/summary + 자사 + 그리드 + 푸터(인라인)
    # 푸터를 좌측 컬럼 끝에 두어, 우측 TOP5보다 좌측이 짧을 때 생기는 큰 빈 여백 아래쪽에 버튼이 떨어지는 문제를 막음
    footer_inline = (
        '<div style="border-top:1px dashed #e3deb6;'
        'padding:12px 6px 6px;text-align:center;margin-top:12px;">'
        f'<a href="{_esc(DASHBOARD_URL)}" style="color:#1d4ed8;font-weight:800;'
        'text-decoration:none;font-size:14px;">📊 전체 대시보드 보기 →</a>'
        '<div style="color:#94a3b8;font-size:11px;margin-top:6px;">'
        f'<a href="{_esc(REPO_URL)}" style="color:#94a3b8;text-decoration:none;">소스 저장소</a>'
        '</div></div>'
    )
    left_inner = head_box + (own or "") + (grid_html or "") + footer_inline

    # 우측 사이드 스택 — 전일관객/예매/해외 TOP5
    side_parts = []
    for blk in (box_html, res_html, mojo_html):
        if blk:
            side_parts.append(f'<div style="margin-bottom:8px;">{blk}</div>')
    right_inner = "".join(side_parts)

    body_table = (
        '<table width="100%" cellspacing="0" cellpadding="0" border="0" '
        'style="border-collapse:collapse;">'
        '<tr>'
        '<td valign="top" width="62%" style="padding:6px 6px 6px 10px;">'
        f'{left_inner}'
        '</td>'
        '<td valign="top" width="38%" style="padding:6px 10px 6px 6px;">'
        f'{right_inner}'
        '</td>'
        '</tr></table>'
    )

    return f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#f1f5f9;">
<div style="max-width:820px;margin:18px auto;font-family:-apple-system,'Apple SD Gothic Neo','Malgun Gothic',Arial,sans-serif;color:#1f2937;">
  <div style="background:#fdfbe9;border:1px solid #e3deb6;border-radius:10px 10px 0 0;padding:14px 18px 8px;">
    <div style="display:flex;align-items:baseline;justify-content:space-between;gap:12px;">
      <div style="font-size:17px;font-weight:800;color:#1f2937;">
        🤖 오늘의 AI 브리핑
        <span style="background:#d97706;color:#fff;font-size:11px;padding:2px 7px;border-radius:4px;font-weight:800;margin-left:4px;vertical-align:2px;">AI SUMMARY</span>
      </div>
      <div style="color:#94a3b8;font-size:11px;">{_esc(gen)}</div>
    </div>
    {kpi_html}
  </div>
  <div style="background:#fdfbe9;border:1px solid #e3deb6;border-top:none;border-radius:0 0 10px 10px;">
    {body_table}
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
    market = _load_json(MARKET_PATH, {}) or {}
    reservation = _load_json(RESERVATION_PATH, {}) or {}
    overseas = _load_json(OVERSEAS_PATH, {}) or {}
    market_trends = _load_json(MARKET_TRENDS_PATH, []) or []
    community = _load_json(COMMUNITY_PATH, []) or []
    trend_count = len(market_trends) if isinstance(market_trends, list) else 0
    comm_count = len(community) if isinstance(community, list) else 0
    if mode == "html":
        articles = _load_json(ARTICLES_PATH, [])
        sys.stdout.write(render_html(
            briefing, articles,
            market=market, reservation=reservation, overseas=overseas,
            trend_count=trend_count, comm_count=comm_count,
        ))
    else:
        sys.stdout.write(render_text(
            briefing,
            market=market, reservation=reservation, overseas=overseas,
            trend_count=trend_count, comm_count=comm_count,
        ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
