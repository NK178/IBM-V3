"""Build a one-page-ish executive decision memo (PDF) for an approved report."""
import hashlib
import io
import re
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

INK = colors.HexColor("#161a23")
MUTED = colors.HexColor("#5b6172")
RULE = colors.HexColor("#d9dce3")
ACCENT = colors.HexColor("#2f6fdf")
OK = colors.HexColor("#15803d")
OK_BG = colors.HexColor("#e8f6ec")
ZEBRA = colors.HexColor("#f5f6f9")

_base = dict(fontName="Helvetica", fontSize=10, leading=14, textColor=INK, alignment=TA_LEFT)
S = {
    "brand": ParagraphStyle("brand", **{**_base, "fontName": "Helvetica-Bold", "fontSize": 9, "textColor": ACCENT}),
    "title": ParagraphStyle("title", **{**_base, "fontName": "Helvetica-Bold", "fontSize": 20, "leading": 24}),
    "h2": ParagraphStyle("h2", **{**_base, "fontName": "Helvetica-Bold", "fontSize": 11, "leading": 14,
                                  "spaceBefore": 10, "spaceAfter": 4}),
    "body": ParagraphStyle("body", **_base),
    "small": ParagraphStyle("small", **{**_base, "fontSize": 8.5, "leading": 11, "textColor": MUTED}),
    "label": ParagraphStyle("label", **{**_base, "fontName": "Helvetica-Bold", "fontSize": 8.5, "leading": 11,
                                       "textColor": MUTED}),
    "cell": ParagraphStyle("cell", **{**_base, "fontSize": 9, "leading": 12}),
    "verdict": ParagraphStyle("verdict", **{**_base, "fontName": "Helvetica-Bold", "fontSize": 13, "leading": 16,
                                           "textColor": OK}),
}


def _clean(text) -> str:
    """Strip markdown/emoji and escape for ReportLab's mini-HTML; keep WinAnsi-safe characters."""
    if text is None:
        return ""
    t = str(text).replace("**", "")
    t = t.encode("cp1252", errors="ignore").decode("cp1252")
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"\s+", " ", t).strip()


def _fmt_ts(ts: str) -> str:
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            d = datetime.strptime(ts, fmt)
            return d.strftime("%d %b %Y, %H:%M UTC") if "T" in ts else d.strftime("%d %b %Y")
        except (TypeError, ValueError):
            continue
    return ts or ""


def _p(text, style="body"):
    return Paragraph(_clean(text), S[style])


def _kv_table(rows, col0=32 * mm):
    t = Table([[Paragraph(_clean(k), S["label"]), Paragraph(_clean(v), S["body"])] for k, v in rows],
              colWidths=[col0, None], hAlign="LEFT")
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
    ]))
    return t


def build_memo(approval: dict, report: dict | None, history: list[dict], next_steps: list[str],
               generated_at: str) -> bytes:
    title = approval["report_title"]
    memo_no = "DM-" + (approval.get("timestamp") or "")[:10].replace("-", "") + "-" + \
        hashlib.sha1(f"{approval['report_key']}|{approval.get('timestamp')}".encode()).hexdigest()[:6].upper()
    signers = [s.strip() for s in str(approval.get("decided_by", "")).split("+") if s.strip()]
    dual = len(signers) > 1

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title=f"Decision Memo - {title}", author="FinReview", subject="Executive decision memo")
    story = [
        _p("FINREVIEW  ·  EXECUTIVE DECISION RECORD", "brand"),
        Spacer(1, 4),
        _p("Decision Memorandum", "title"),
        Spacer(1, 8),
        _kv_table([
            ("Memo No.", memo_no),
            ("Date", _fmt_ts(approval.get("timestamp", ""))),
            ("To", "Finance Team; Report Owner; Compliance Records"),
            ("From", " and ".join(signers) or "Executive"),
            ("Subject", f"Approval of {title}"),
        ]),
        Spacer(1, 6),
        HRFlowable(width="100%", thickness=0.8, color=RULE, spaceBefore=2, spaceAfter=8),
    ]

    verdict = "DUAL-SIGNATURE APPROVED" if dual else str(approval.get("decision", "Approved")).upper()
    box = Table([[Paragraph(_clean(verdict), S["verdict"])],
                 [Paragraph(_clean(
                     f"{title} was {str(approval.get('decision', 'approved')).lower()} by "
                     f"{' and '.join(signers) or 'an executive'} on {_fmt_ts(approval.get('timestamp', ''))}."
                 ), S["body"])]],
                colWidths=["100%"])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), OK_BG),
        ("LINEBEFORE", (0, 0), (0, -1), 3, OK),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
    ]))
    story += [box]

    if report:
        story += [_p("Report", "h2"), _kv_table([
            ("Report ID", f"#{report['report_id']}"),
            ("Title", report["title"]),
            ("Report date", _fmt_ts(report["date"])),
            ("Current status", report["status"]),
            ("Summary", report["summary"]),
            ("Recommendation", report["recommendation"]),
        ])]

    # Approval record: signature legs + final decision
    sig_rows = [h for h in history if h["decision"] in ("First Signature", "Countersignature")]
    if dual and sig_rows:
        story.append(_p("Signatures", "h2"))
        rows = [[_p("Leg", "label"), _p("Signed by", "label"), _p("Time", "label")]]
        for h in sig_rows[-2:]:
            rows.append([_p("First signature" if h["decision"] == "First Signature" else "Countersignature", "cell"),
                         _p(h["decided_by"], "cell"), _p(_fmt_ts(h["timestamp"]), "cell")])
        story.append(_table(rows, [40 * mm, 55 * mm, None]))

    if approval.get("notes"):
        story += [_p("Notes and conditions", "h2"), _p(approval["notes"])]

    story += [_p("Next steps", "h2")]
    story += [_p(f"{i}.  {step}") for i, step in enumerate(next_steps, 1)]

    if history:
        rows = [[_p("Time", "label"), _p("Action", "label"), _p("By", "label"), _p("Notes", "label")]]
        for h in history:
            rows.append([_p(_fmt_ts(h["timestamp"]), "cell"), _p(h["decision"], "cell"),
                         _p(h["decided_by"], "cell"), _p(h.get("notes") or "-", "cell")])
        story.append(KeepTogether([_p("Decision history", "h2"), _table(rows, [38 * mm, 32 * mm, 38 * mm, None])]))

    story += [
        Spacer(1, 14),
        HRFlowable(width="100%", thickness=0.5, color=RULE, spaceAfter=4),
        _p(f"Generated by FinReview on {_fmt_ts(generated_at)} from the shared decision log. "
           "This memo reflects the system of record at the time of export.", "small"),
    ]

    def _footer(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(20 * mm, 10 * mm, f"{memo_no}  ·  {_clean(title)}")
        canvas.drawRightString(A4[0] - 20 * mm, 10 * mm, f"Page {d.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()


def _table(rows, widths):
    t = Table(rows, colWidths=widths, hAlign="LEFT", repeatRows=1)
    t.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, RULE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ZEBRA]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t
