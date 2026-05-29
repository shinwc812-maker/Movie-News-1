"""AI 브리핑 메일 발송.

파이차트를 외부 URL(quickchart.io)이 아니라 메일 본문 안에 인라인 이미지(CID)로
심는다. Gmail은 외부 이미지를 프록시해 보여주지만 사내 Outlook 등은 외부 이미지를
차단·미표시하므로, 빌드 시점(러너)에 차트 PNG를 받아 메일에 직접 첨부해야 어떤
클라이언트에서도 깨지지 않는다.

환경변수:
  GMAIL_USER, GMAIL_APP_PASSWORD  — 필수(없으면 발송 생략)
  GMAIL_RECIPIENTS                — 쉼표 구분 다중 수신자(미설정 시 GMAIL_USER 본인)
  MAIL_SUBJECT                    — 제목(기본 "[오늘의 AI 브리핑]")
"""
from __future__ import annotations

import os
import smtplib
import sys
import urllib.request
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

import build_mail_body as bmb


def _download(url: str, timeout: int = 20) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (briefing-mail-bot)"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if getattr(resp, "status", 200) != 200:
                return None
            return resp.read()
    except Exception as exc:  # noqa: BLE001 — 차트 한 장 실패가 메일 발송 전체를 막지 않게
        print(f"[send_mail] 차트 다운로드 실패: {exc}", file=sys.stderr)
        return None


def build_message(subject: str, sender: str, recipients: list[str]) -> MIMEMultipart | None:
    briefing = bmb._load_json(bmb.BRIEFING_PATH, None)
    if not briefing:
        print("[send_mail] 브리핑 JSON이 없습니다 — 발송 생략")
        return None
    market = bmb._load_json(bmb.MARKET_PATH, {}) or {}
    reservation = bmb._load_json(bmb.RESERVATION_PATH, {}) or {}
    overseas = bmb._load_json(bmb.OVERSEAS_PATH, {}) or {}
    articles = bmb._load_json(bmb.ARTICLES_PATH, [])

    text_body = bmb.render_text(briefing, market=market, reservation=reservation, overseas=overseas)

    bmb.set_cid_mode(True)
    html_body = bmb.render_html(
        briefing, articles, market=market, reservation=reservation, overseas=overseas,
    )
    charts = bmb.get_chart_registry()
    bmb.set_cid_mode(False)

    inline_images: list[tuple[str, bytes]] = []
    for ch in charts:
        data = _download(ch["url"])
        if data:
            inline_images.append((ch["cid"], data))
        else:
            # 다운로드 실패 시 외부 URL로 폴백 — 최소 Gmail에서는 보이게.
            html_body = html_body.replace(f"cid:{ch['cid']}", bmb._esc(ch["url"]))

    related = MIMEMultipart("related")
    related["Subject"] = subject
    related["From"] = sender
    related["To"] = ", ".join(recipients)

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(text_body, "plain", "utf-8"))
    alt.attach(MIMEText(html_body, "html", "utf-8"))
    related.attach(alt)

    for cid, data in inline_images:
        img = MIMEImage(data, _subtype="png")
        img.add_header("Content-ID", f"<{cid}>")
        img.add_header("Content-Disposition", "inline", filename=f"{cid}.png")
        related.attach(img)

    print(f"[send_mail] html {len(html_body)}자 · 인라인 차트 {len(inline_images)}/{len(charts)}장")
    return related


def main() -> int:
    user = os.environ.get("GMAIL_USER", "").strip()
    password = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    if not user or not password:
        print("[send_mail] GMAIL_USER/GMAIL_APP_PASSWORD 미설정 — 발송 생략")
        return 0

    recipients_raw = os.environ.get("GMAIL_RECIPIENTS", "").strip() or user
    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]
    subject = os.environ.get("MAIL_SUBJECT", "[오늘의 AI 브리핑]")
    sender = formataddr(("AI Briefing Bot", user))

    msg = build_message(subject, sender, recipients)
    if msg is None:
        return 0

    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(user, password)
        smtp.sendmail(user, recipients, msg.as_string())
    print(f"[send_mail] 발송 완료 — 수신자 {len(recipients)}명")
    return 0


if __name__ == "__main__":
    sys.exit(main())
