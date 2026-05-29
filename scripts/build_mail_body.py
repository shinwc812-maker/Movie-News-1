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
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
BRIEFING_PATH = ROOT / "data" / "ai_briefing.json"
ARTICLES_PATH = ROOT / "data" / "articles.json"
MARKET_PATH = ROOT / "data" / "market.json"
RESERVATION_PATH = ROOT / "data" / "reservation.json"
OVERSEAS_PATH = ROOT / "data" / "overseas_weekend.json"
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
                overseas: dict | None = None) -> str:
    lines: list[str] = []
    gen = _format_generated_kst(b)
    if gen:
        lines.append(f"생성: {gen}")
        lines.append("")
    # KPI 요약 (시장 종합)
    s = _market_summary(market or {}, reservation or {})
    if s:
        lines.append("━━ 핵심 지표 ━━")
        total_line = f"  전일 총 입장객: {s['total_audi']}명"
        if s["total_audi_delta"]:
            total_line += f" {s['total_audi_delta']}"
        lines.append(total_line)
        lines.append(f"  평균 좌석판매율: {s['avg_seat_sales']}")
        res_line = f"  예매 1위: {s['res_top_rate'] or '-'}"
        if s["res_top_title"]:
            res_line += f" ({s['res_top_title']})"
        lines.append(res_line)
        top1_line = f"  TOP1 집중도: {s['top1_share']}"
        if s["top1_title"]:
            top1_line += f" ({s['top1_title']})"
        lines.append(top1_line)
        lines.append("")

    # AI 브리핑 — 카테고리별 정보 (우선순위 순)
    for cat in b.get("categories") or []:
        items = cat.get("items") or []
        if not items:
            continue
        lines.append(f"━━ {cat.get('name','')} ━━")
        for it in items:
            line = f"• {it.get('summary','')}"
            if it.get("source"):
                line += f" [{it['source']}]"
            lines.append(line)
            if it.get("source_url"):
                lines.append(f"  {it['source_url']}")
        lines.append("")

    if market and market.get("movies"):
        lines.append("━━ 전일 입장객 TOP 5 (KOBIS) ━━")
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
        lines.append(f"━━ 북미 주말 TOP 5 (Box Office Mojo{(' · '+label) if label else ''}) ━━")
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


def _fmt_int(n) -> str:
    try:
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return ""


def _fmt_delta_audi(audi_inten, audi_change) -> str:
    """전일대비 증감 — 회사 표기 규칙: 증가는 숫자만, 감소는 ▲ 접두(▲=마이너스). 색은 통일."""
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
    mark = "▲" if inten < 0 else ""
    abs_n = _fmt_int(abs(inten))
    pct = f"({mark}{abs(change):.1f}%)" if change else ""
    parts = [p for p in [f"{mark}{abs_n}명", pct] if p]
    inner = " ".join(parts)
    return f'<span style="color:#374151;font-weight:800;">{inner}</span>'


PIE_PALETTE = ("#dc2626", "#d97706", "#2563eb", "#059669", "#7c3aed")


def _share_segments(movies: list[dict], value_key: str) -> list[dict]:
    """TOP5 각 항목의 value 비중(파이차트용). site/build.py와 동일 색상·로직."""
    items = [m for m in (movies or [])[:5] if isinstance(m, dict)]

    def _i(value) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    total = sum(_i(m.get(value_key)) for m in items)
    segments: list[dict] = []
    for idx, movie in enumerate(items):
        pct = (_i(movie.get(value_key)) / total * 100) if total else 0.0
        segments.append({
            "title": movie.get("title", ""),
            "pct": round(pct, 1),
            "color": PIE_PALETTE[idx % len(PIE_PALETTE)],
        })
    return segments


# 메일 발송 시 파이차트를 외부 URL이 아닌 인라인(CID) 이미지로 심기 위한 레지스트리.
# Outlook 등은 외부 이미지(quickchart.io)를 차단·미표시하므로, send_mail.py가
# CID 모드를 켜고 등록된 URL을 빌드 시점에 PNG로 받아 메일에 인라인 첨부한다.
_CID_MODE = False
_CHART_REGISTRY: list[dict] = []


def set_cid_mode(enabled: bool) -> None:
    """파이차트 <img>를 'cid:...' 참조로 렌더하도록 전환하고 레지스트리를 비운다."""
    global _CID_MODE
    _CID_MODE = enabled
    _CHART_REGISTRY.clear()


def get_chart_registry() -> list[dict]:
    """[{'cid': ..., 'url': ...}] — CID 모드로 렌더된 파이차트의 원본 QuickChart URL."""
    return list(_CHART_REGISTRY)


def _register_chart(url: str) -> str:
    """URL을 레지스트리에 등록하고 cid 참조 문자열을 반환."""
    cid = f"pie{len(_CHART_REGISTRY)}"
    _CHART_REGISTRY.append({"cid": cid, "url": url})
    return f"cid:{cid}"


def _quickchart_pie_url(segments: list[dict]) -> str:
    """비중 세그먼트를 QuickChart 파이차트 이미지 URL로 변환(메일용 — 이메일은 conic 미지원)."""
    if not segments:
        return ""
    # 범례·조각 라벨은 끄고 파이 원만 그린다(범례 텍스트 길이에 따라 원 크기가
    # 달라지는 문제 방지 → 두 차트 크기 동일). 범례는 메일 HTML에서 따로 그린다.
    config = {
        "type": "pie",
        "data": {
            "datasets": [{
                "data": [s["pct"] for s in segments],
                "backgroundColor": [s["color"] for s in segments],
                "borderWidth": 0,
            }],
        },
        "options": {
            "legend": {"display": False},
            "plugins": {"datalabels": {"display": False}},
        },
    }
    encoded = urllib.parse.quote(json.dumps(config, ensure_ascii=False, separators=(",", ":")))
    return f"https://quickchart.io/chart?w=120&h=120&bkg=white&c={encoded}"


def _market_summary(market: dict, reservation: dict | None = None) -> dict:
    """박스오피스 TOP5로 시장 종합 지표(KPI)를 계산. site/build.py와 동일 로직."""
    movies = [m for m in ((market or {}).get("movies") or []) if isinstance(m, dict)]
    if not movies:
        return {}

    def _int(value) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _float(value) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    total_today = sum(_int(m.get("audi_count")) for m in movies)
    total_delta = sum(_int(m.get("audi_inten")) for m in movies)
    total_yesterday = total_today - total_delta
    delta_pct = (total_delta / total_yesterday * 100) if total_yesterday > 0 else 0.0
    mark = "▲" if delta_pct < 0 else ""
    delta_label = f"({mark}{abs(delta_pct):.1f}%)" if total_yesterday > 0 else ""

    total_seat = sum(_int(m.get("seat_count")) for m in movies)
    if total_seat:
        avg_seat = sum(_float(m.get("seat_sales_rate")) * _int(m.get("seat_count")) for m in movies) / total_seat * 100
    else:
        avg_seat = 0.0

    res_movies = [m for m in ((reservation or {}).get("movies") or []) if isinstance(m, dict)]
    res_top = res_movies[0] if res_movies else {}
    res_rate = res_top.get("reservation_rate")
    res_rate_label = f"{_float(res_rate):.1f}%" if res_rate is not None else ""
    res_title = res_top.get("title") or ""

    top1 = movies[0]
    top1_share = (_int(top1.get("audi_count")) / total_today * 100) if total_today else 0.0

    audi_segments = _share_segments(movies, "audi_count")
    res_segments = _share_segments(res_movies, "reservation_count")

    return {
        "total_audi": _fmt_int(total_today),
        "total_audi_delta": delta_label,
        "avg_seat_sales": f"{avg_seat:.1f}%",
        "res_top_rate": res_rate_label,
        "res_top_title": res_title,
        "top1_share": f"{top1_share:.1f}%",
        "top1_title": top1.get("title") or "",
        "audi_segments": audi_segments,
        "res_segments": res_segments,
    }


def _kpi_block(market: dict, reservation: dict | None = None) -> str:
    s = _market_summary(market, reservation)
    if not s:
        return ""

    def _cell(label: str, value_html: str, width: str = "50%") -> str:
        return (
            f'<td valign="top" width="{width}" style="padding:8px 10px;background:#fff;'
            'border:1px solid #efe9c4;border-radius:6px;">'
            f'<div style="font-size:11px;font-weight:700;color:#92400e;">{label}</div>'
            f'<div style="margin-top:3px;font-size:12px;font-weight:700;color:#111827;">{value_html}</div>'
            '</td>'
        )

    sub = 'color:#6b7280;font-weight:600;font-size:11px;'
    total_val = f'<b>{s["total_audi"]}명</b>'
    if s["total_audi_delta"]:
        total_val += f' <span style="{sub}">{_esc(s["total_audi_delta"])}</span>'
    seat_val = f'<b>{s["avg_seat_sales"]}</b>'

    def _pie_cell(label: str, segments: list[dict]) -> str:
        url = _quickchart_pie_url(segments)
        if not url:
            return _cell(label, "-")
        alt = label + (
            f': {segments[0]["title"]} {segments[0]["pct"]}%' if segments else ""
        )
        img_src = _register_chart(url) if _CID_MODE else url
        img = (
            f'<img src="{_esc(img_src)}" alt="{_esc(alt)}" width="96" height="96" '
            'style="display:block;flex-shrink:0;">'
        )
        legend_rows = []
        for seg in segments:
            t = seg["title"] or ""
            t = (t[:15] + "…") if len(t) > 15 else t
            legend_rows.append(
                '<div style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">'
                f'<span style="display:inline-block;width:8px;height:8px;border-radius:2px;'
                f'background:{seg["color"]};margin-right:5px;"></span>'
                f'{_esc(t)} <b>{seg["pct"]}%</b></div>'
            )
        legend = (
            '<div style="font-size:10px;line-height:1.6;color:#374151;min-width:0;">'
            + "".join(legend_rows) + '</div>'
        )
        return (
            '<td valign="top" width="50%" style="padding:6px 8px;background:#fff;'
            'border:1px solid #efe9c4;border-radius:6px;">'
            f'<div style="font-size:11px;font-weight:700;color:#92400e;margin-bottom:4px;">{label}</div>'
            '<table cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td valign="middle" style="padding-right:8px;">{img}</td>'
            f'<td valign="middle">{legend}</td>'
            '</tr></table>'
            '</td>'
        )

    return (
        '<table width="100%" cellspacing="6" cellpadding="0" border="0" '
        'style="border-collapse:separate;margin:8px 4px 4px;">'
        f'<tr>{_cell("전일 총 입장객", total_val)}{_cell("평균 좌석판매율", seat_val)}</tr>'
        f'<tr>{_pie_cell("전일 입장객 비중", s["audi_segments"])}'
        f'{_pie_cell("실시간 예매량 비중", s["res_segments"])}</tr>'
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
    return _block("📊 전일 입장객 TOP 5  <span style='color:#6b7280;font-size:11px;font-weight:600;'>KOBIS</span>", inner)


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
    return _block(f"🌎 북미 주말 TOP 5  <span style='color:#6b7280;font-size:11px;font-weight:600;'>Box Office Mojo{sub}</span>", inner)


def _category_block(name: str, items: list[dict], L) -> str:
    """AI 브리핑 카테고리 블록 — '핵심 한줄요약 [출처](링크)' 리스트."""
    if not items:
        return ""
    lis = []
    for it in items:
        summary = L(it.get("summary", ""))
        src = _esc(it.get("source", ""))
        url = it.get("source_url", "")
        cite = ""
        if src:
            if url:
                cite = (
                    f' <a href="{_esc(url)}" style="color:#1d4ed8;'
                    f'text-decoration:none;font-weight:700;">[{src}]</a>'
                )
            else:
                cite = f' <span style="color:#6b7280;">[{src}]</span>'
        lis.append(f"{summary}{cite}")
    return _block(_esc(name), _ul(lis))


def render_html(b: dict, articles: list, market: dict | None = None,
                reservation: dict | None = None, overseas: dict | None = None) -> str:
    smap = _build_source_link_map(articles)
    L = lambda s: _linkify_html(s, smap)

    gen = _format_generated_kst(b)

    # AI 브리핑 — 카테고리별 정보(우선순위 순) 세로 나열
    cat_parts = []
    for cat in b.get("categories") or []:
        blk = _category_block(cat.get("name", ""), cat.get("items") or [], L)
        if blk:
            cat_parts.append(f'<div style="margin-bottom:10px;">{blk}</div>')
    categories_html = "".join(cat_parts)

    kpi_html = _kpi_block(market or {}, reservation or {})
    box_html = _boxoffice_top5_block(market or {})
    res_html = _reservation_top5_block(reservation or {})
    mojo_html = _mojo_top5_block(overseas or {})

    # 좌측 본문 — 카테고리 정보 + 푸터(인라인)
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
    left_inner = (categories_html or "") + footer_inline

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
        <span style="background:#d97706;color:#fff;font-size:11px;padding:2px 7px;border-radius:4px;font-weight:800;vertical-align:2px;">AI SUMMARY</span>
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
    if mode == "html":
        articles = _load_json(ARTICLES_PATH, [])
        sys.stdout.write(render_html(
            briefing, articles,
            market=market, reservation=reservation, overseas=overseas,
        ))
    else:
        sys.stdout.write(render_text(
            briefing,
            market=market, reservation=reservation, overseas=overseas,
        ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
