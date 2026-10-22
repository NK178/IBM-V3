from flask import Flask, request, jsonify, render_template
from datetime import datetime, timezone
import csv
import hashlib
import hmac
import io
import json
import os
import logging
import threading
import urllib.error
import urllib.parse
import urllib.request

import store
from chat_auth import bp as chat_bp

log = logging.getLogger(__name__)

app = Flask(__name__)
app.register_blueprint(chat_bp)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _not_found_report(report_id: int, title: str = "Report Not Found") -> dict:
    valid = ", ".join(str(r["report_id"]) for r in store.list_reports())
    return {
        "report_id": report_id,
        "title": title,
        "date": "N/A",
        "status": "Not Found",
        "summary": f"No report with ID {report_id} exists in the data store.",
        "recommendation": f"Please request a valid report ID ({valid}).",
    }

FINANCIAL_TEMPLATES = {
    "Q3 Marketing Budget": [
        {"category": "Digital Advertising",   "budgeted": 120000, "actual": 134500},
        {"category": "Events & Sponsorships", "budgeted":  85000, "actual":  79200},
        {"category": "Content Production",    "budgeted":  45000, "actual":  46800},
        {"category": "Agency Fees",           "budgeted":  60000, "actual":  71300},
        {"category": "Market Research",       "budgeted":  25000, "actual":  18900},
        {"category": "PR & Communications",   "budgeted":  30000, "actual":  30100},
    ],
    "IT Infrastructure Grant": [
        {"category": "Hardware Procurement",      "budgeted": 200000, "actual": 198400},
        {"category": "Cloud Services",            "budgeted":  95000, "actual": 112800},
        {"category": "Security Licensing",        "budgeted":  40000, "actual":  40000},
        {"category": "Implementation Services",   "budgeted":  75000, "actual":  88500},
        {"category": "Training & Enablement",     "budgeted":  20000, "actual":  14200},
        {"category": "Contingency Reserve",       "budgeted":  30000, "actual":   7600},
    ],
    "Operational Expense Report": [
        {"category": "Salaries & Benefits",       "budgeted": 450000, "actual": 452300},
        {"category": "Facilities & Rent",         "budgeted":  80000, "actual":  80000},
        {"category": "Travel & Expenses",         "budgeted":  35000, "actual":  41700},
        {"category": "Software Subscriptions",    "budgeted":  28000, "actual":  31200},
        {"category": "Office Supplies",           "budgeted":   8000, "actual":   6400},
        {"category": "Legal & Compliance",        "budgeted":  50000, "actual":  47800},
    ],
}

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/healthz")
def healthz():
    return "ok"


@app.route("/api/get_report", methods=["GET"])
def get_report():
    try:
        report_id = int(request.args.get("report_id", 0))
    except ValueError:
        return jsonify({"error": "Invalid report_id"}), 400
    return jsonify(store.get_report(report_id) or _not_found_report(report_id))


@app.route("/api/list_reports", methods=["GET"])
def list_reports():
    return jsonify([
        {"report_id": r["report_id"], "title": r["title"], "date": r["date"], "status": r["status"]}
        for r in store.list_reports()
    ])


@app.route("/api/compare_reports", methods=["GET"])
def compare_reports():
    try:
        id_a = int(request.args.get("report_id_a", 0))
        id_b = int(request.args.get("report_id_b", 0))
    except ValueError:
        return jsonify({"error": "Invalid report IDs"}), 400

    a = store.get_report(id_a) or _not_found_report(id_a, f"Report {id_a} Not Found")
    b = store.get_report(id_b) or _not_found_report(id_b, f"Report {id_b} Not Found")

    fields = ["title", "date", "status", "summary", "recommendation"]
    diffs = [
        {"field": f.replace("_", " ").title(),
         "report_a_value": str(a[f]),
         "report_b_value": str(b[f]),
         "differs": a[f] != b[f]}
        for f in fields
    ]

    takeaways = [
        f"{d['field']} changed from \"{d['report_a_value']}\" → \"{d['report_b_value']}\"."
        for d in diffs if d["differs"]
    ] or ["Both reports are identical across all compared fields."]

    if a["recommendation"] == b["recommendation"]:
        rec_variance = "Both reports share the same recommendation."
    else:
        rec_variance = (
            f"Report {id_a} recommends: \"{a['recommendation']}\" — "
            f"Report {id_b} recommends: \"{b['recommendation']}\". "
            "These recommendations differ and may reflect escalating system conditions."
        )

    return jsonify({
        "report_a_id": id_a, "report_b_id": id_b,
        "report_a_title": a["title"], "report_b_title": b["title"],
        "field_differences": diffs,
        "key_takeaways": takeaways,
        "recommendation_variance": rec_variance,
    })


@app.route("/api/update_report_status", methods=["POST"])
def update_report_status():
    data = request.get_json(silent=True) or {}
    try:
        report_id = int(data.get("report_id", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid report_id"}), 400

    decision = str(data.get("decision", "")).strip().title()
    reason = data.get("reason") or None
    decided_by = str(data.get("decided_by") or "Executive").strip()[:80]
    timestamp = _now()

    if decision not in {"Accept", "Decline"}:
        decision = "Decline"
    new_status = "Accepted" if decision == "Accept" else "Declined"

    result = store.set_report_status(report_id, new_status)
    if result is None:
        valid = ", ".join(str(r["report_id"]) for r in store.list_reports())
        return jsonify({
            "report_id": report_id, "report_title": "Report Not Found",
            "previous_status": "N/A", "new_status": "N/A",
            "decision": decision, "reason": reason, "timestamp_utc": timestamp,
            "confirmation_message": f"Report {report_id} was not found. Use a valid ID ({valid}).",
        })

    report, previous_status = result
    store.log_decision(report["title"], new_status, decided_by, timestamp, reason, report_id=report_id)
    if decision == "Accept":
        msg = f"Report {report_id} has been accepted. Status updated from \"{previous_status}\" to \"{new_status}\" at {timestamp}."
    else:
        reason_suffix = f" Reason: \"{reason}\"." if reason else ""
        msg = f"Report {report_id} has been declined.{reason_suffix} Status updated from \"{previous_status}\" to \"{new_status}\" at {timestamp}."

    return jsonify({
        "report_id": report_id, "report_title": report["title"],
        "previous_status": previous_status, "new_status": new_status,
        "decision": decision, "reason": reason,
        "timestamp_utc": timestamp, "confirmation_message": msg,
        "memo_url": _memo_url(report["title"]) if decision == "Accept" else None,
    })


@app.route("/api/reset", methods=["POST"])
def reset():
    """Restore the seed data and clear pending signatures (use before a demo).

    If the RESET_KEY env var is set, the request must send it as the X-Reset-Key header.
    """
    import os
    key = os.environ.get("RESET_KEY")
    if key and request.headers.get("X-Reset-Key") != key:
        return jsonify({"error": "Forbidden"}), 403
    store.reset()
    return jsonify({"ok": True, "reports": store.list_reports()})

# ---------------------------------------------------------------------------
# File upload parser
# ---------------------------------------------------------------------------

# Flexible column aliases  →  canonical name
_COL_ALIASES = {
    # category
    "category":        "category",
    "line item":       "category",
    "line_item":       "category",
    "description":     "category",
    "account":         "category",
    "item":            "category",
    "name":            "category",
    # budgeted
    "budgeted":        "budgeted",
    "budgeted_usd":    "budgeted",
    "budget":          "budgeted",
    "budget usd":      "budgeted",
    "budget ($)":      "budgeted",
    "planned":         "budgeted",
    "planned_usd":     "budgeted",
    "forecast":        "budgeted",
    # actual
    "actual":          "actual",
    "actual_usd":      "actual",
    "actual usd":      "actual",
    "actual ($)":      "actual",
    "spend":           "actual",
    "spent":           "actual",
    "cost":            "actual",
    "costs":           "actual",
    "amount":          "actual",
}


def _parse_number(v: str) -> float:
    """Strip currency symbols, commas, whitespace and cast to float."""
    cleaned = str(v).replace("$", "").replace(",", "").replace(" ", "").strip()
    if cleaned in ("", "-", "—", "n/a"):
        return 0.0
    return float(cleaned)


def _rows_to_line_items(rows: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Map a list of raw dicts (one per CSV/sheet row) to line_items.
    Returns (line_items, warnings).
    Skips blank rows and sub-total rows (where category looks like total/subtotal).
    """
    SKIP_WORDS = {"total", "subtotal", "sub-total", "grand total", "sum", ""}
    line_items = []
    warnings = []

    for i, row in enumerate(rows, start=2):   # 1-based + header = row 2
        cat_raw = str(row.get("category", "")).strip()
        if cat_raw.lower() in SKIP_WORDS:
            continue

        try:
            budgeted = _parse_number(row.get("budgeted", 0))
            actual   = _parse_number(row.get("actual",   0))
        except ValueError as exc:
            warnings.append(f"Row {i}: skipped — {exc}")
            continue

        if budgeted == 0 and actual == 0:
            continue

        variance     = round(actual - budgeted, 2)
        variance_pct = round((variance / budgeted) * 100, 2) if budgeted else 0.0

        if variance_pct > 5:
            status = "Over Budget"
        elif variance_pct < -5:
            status = "Under Budget"
        else:
            status = "On Track"

        line_items.append({
            "category":     cat_raw,
            "budgeted_usd": budgeted,
            "actual_usd":   actual,
            "variance_usd": variance,
            "variance_pct": variance_pct,
            "status":       status,
        })

    return line_items, warnings


def _normalise_headers(raw_headers: list[str]) -> dict[int, str]:
    """Return {col_index: canonical_name} for recognised columns."""
    mapping = {}
    for idx, h in enumerate(raw_headers):
        canonical = _COL_ALIASES.get(h.strip().lower())
        if canonical:
            mapping[idx] = canonical
    return mapping


def _parse_csv_bytes(data: bytes) -> tuple[list[dict], list[str]]:
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    all_rows = list(reader)
    if not all_rows:
        return [], ["File appears to be empty."]

    raw_headers = all_rows[0]
    col_map = _normalise_headers(raw_headers)
    if "category" not in col_map.values() or "budgeted" not in col_map.values() or "actual" not in col_map.values():
        missing = [c for c in ("category", "budgeted", "actual") if c not in col_map.values()]
        return [], [f"Could not find required columns: {', '.join(missing)}. "
                    f"Headers found: {', '.join(raw_headers)}"]

    rows = []
    for raw in all_rows[1:]:
        row = {}
        for idx, canonical in col_map.items():
            row[canonical] = raw[idx] if idx < len(raw) else ""
        rows.append(row)

    return _rows_to_line_items(rows)


def _parse_xlsx_bytes(data: bytes) -> tuple[list[dict], list[str]]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    ws = wb.active
    all_rows = [[str(c.value) if c.value is not None else "" for c in row] for row in ws.iter_rows()]
    wb.close()

    if not all_rows:
        return [], ["Workbook sheet appears to be empty."]

    raw_headers = all_rows[0]
    col_map = _normalise_headers(raw_headers)
    if "category" not in col_map.values() or "budgeted" not in col_map.values() or "actual" not in col_map.values():
        missing = [c for c in ("category", "budgeted", "actual") if c not in col_map.values()]
        return [], [f"Could not find required columns: {', '.join(missing)}. "
                    f"Headers found: {', '.join(raw_headers)}"]

    rows = []
    for raw in all_rows[1:]:
        row = {}
        for idx, canonical in col_map.items():
            row[canonical] = raw[idx] if idx < len(raw) else ""
        rows.append(row)

    return _rows_to_line_items(rows)


# ---------------------------------------------------------------------------
# Email ingest (Mailgun inbound routing webhook)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Notifications — email (Mailgun) + Slack
# ---------------------------------------------------------------------------
# All notification env vars are optional; each channel is silently skipped when
# its credentials are absent so the app works locally without configuration.

def _notify_second_signer(
    report_title: str,
    first_signer: str,
    awaiting_role: str,
    sla_due: str,
    timestamp: str,
) -> None:
    """Fire email + Slack notifications for a 'Pending Second Signature' event.

    Runs in a background thread so the API response is never delayed.
    Required env vars (all optional — omit to disable that channel):
      MAILGUN_API_KEY    — Mailgun private API key
      MAILGUN_DOMAIN     — Mailgun sending domain  (e.g. mg.example.com)
      NOTIFICATION_EMAIL_TO — comma-separated recipient(s) for the alert email
      SLACK_WEBHOOK_URL  — Incoming Webhook URL for a Slack channel
    """
    subject = f"[Action Required] Second signature needed: {report_title}"
    body_text = (
        f"A dual-signature approval for '{report_title}' is pending your review.\n\n"
        f"First signature: {first_signer}\n"
        f"Required next:   {awaiting_role}\n"
        f"SLA due:         {sla_due} (3 business days)\n"
        f"Recorded at:     {timestamp}\n\n"
        "Please countersign via the Financial Report Review Agent at your earliest convenience."
    )
    body_html = (
        f"<p>A dual-signature approval for <strong>{report_title}</strong> is pending your review.</p>"
        f"<table style='border-collapse:collapse;font-family:sans-serif'>"
        f"<tr><td style='padding:4px 12px 4px 0;color:#555'>First signature</td><td><strong>{first_signer}</strong></td></tr>"
        f"<tr><td style='padding:4px 12px 4px 0;color:#555'>Required next</td><td><strong>{awaiting_role}</strong></td></tr>"
        f"<tr><td style='padding:4px 12px 4px 0;color:#555'>SLA due</td><td><strong>{sla_due}</strong> (3 business days)</td></tr>"
        f"<tr><td style='padding:4px 12px 4px 0;color:#555'>Recorded at</td><td>{timestamp}</td></tr>"
        f"</table>"
        "<p>Please countersign via the Financial Report Review Agent at your earliest convenience.</p>"
    )

    def _send() -> None:
        _send_mailgun_email(subject, body_text, body_html)
        _send_slack_message(
            f":pen: *Second signature required* — _{report_title}_\n"
            f">First signature: *{first_signer}*\n"
            f">Awaiting: *{awaiting_role}* by *{sla_due}* (3 business days)\n"
            f">Recorded at {timestamp}"
        )

    threading.Thread(target=_send, daemon=True).start()


def _send_mailgun_email(subject: str, body_text: str, body_html: str) -> None:
    api_key = os.environ.get("MAILGUN_API_KEY", "")
    domain  = os.environ.get("MAILGUN_DOMAIN", "")
    to_raw  = os.environ.get("NOTIFICATION_EMAIL_TO", "")
    if not (api_key and domain and to_raw):
        return

    recipients = [r.strip() for r in to_raw.split(",") if r.strip()]
    payload = urllib.parse.urlencode({
        "from":    f"Financial Reports <mailgun@{domain}>",
        "to":      ",".join(recipients),
        "subject": subject,
        "text":    body_text,
        "html":    body_html,
    }).encode()

    req = urllib.request.Request(
        f"https://api.mailgun.net/v3/{domain}/messages",
        data=payload,
        method="POST",
    )
    # Basic auth: api:API_KEY
    import base64
    cred = base64.b64encode(f"api:{api_key}".encode()).decode()
    req.add_header("Authorization", f"Basic {cred}")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            log.info("Mailgun notification sent: %s", resp.status)
    except Exception as exc:
        log.warning("Mailgun notification failed: %s", exc)


def _send_slack_message(text: str) -> None:
    webhook = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not webhook:
        return
    payload = json.dumps({"text": text}).encode()
    req = urllib.request.Request(webhook, data=payload, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            log.info("Slack notification sent: %s", resp.status)
    except Exception as exc:
        log.warning("Slack notification failed: %s", exc)


# ---------------------------------------------------------------------------
# Mailgun inbound signature verification
# ---------------------------------------------------------------------------
def _verify_mailgun_signature(token: str, timestamp: str, signature: str) -> bool:
    """Return True if the request is genuinely from Mailgun."""
    signing_key = os.environ.get("MAILGUN_SIGNING_KEY", "")
    if not signing_key:
        # Key not configured — allow in dev, reject in prod by checking env
        return os.environ.get("FLASK_ENV", "production") != "production"
    value = timestamp + token
    digest = hmac.new(signing_key.encode(), value.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)


def _extract_line_items_from_body(body: str) -> tuple[list[dict], list[str]]:
    """
    Best-effort extraction of a CSV table embedded in an email body.
    Employees can paste a CSV block anywhere in the message body.
    Lines that don't parse as CSV data are ignored.
    """
    # Try to find a contiguous block that looks like CSV (has commas, at least 2 cols)
    candidate_lines = [l for l in body.splitlines() if l.count(",") >= 1]
    if len(candidate_lines) < 2:
        return [], ["No CSV table found in email body."]
    csv_text = "\n".join(candidate_lines)
    return _parse_csv_bytes(csv_text.encode("utf-8"))


@app.route("/api/email_ingest", methods=["POST"])
def email_ingest():
    """Mailgun inbound routing webhook.

    Mailgun POSTs a multipart/form-data with the following fields:
      sender, from, subject, body-plain, body-html,
      timestamp, token, signature,
      attachment-count, attachment-1 … attachment-N
    """
    # ── Signature verification ──────────────────────────────────────────────
    token     = request.form.get("token", "")
    timestamp = request.form.get("timestamp", "")
    signature = request.form.get("signature", "")

    if not _verify_mailgun_signature(token, timestamp, signature):
        return jsonify({"error": "Invalid signature"}), 403

    # ── Extract metadata ─────────────────────────────────────────────────────
    sender   = request.form.get("sender") or request.form.get("from", "unknown@unknown.com")
    subject  = request.form.get("subject", "(no subject)").strip()
    body     = request.form.get("body-plain") or request.form.get("body-html", "")
    received_at = _now()

    line_items: list[dict] = []
    warnings:   list[str]  = []
    attachment_name = ""

    # ── Try attachments first (CSV or XLSX take priority over body text) ─────
    att_count = int(request.form.get("attachment-count", 0))
    for i in range(1, att_count + 1):
        f = request.files.get(f"attachment-{i}")
        if f is None:
            continue
        fname = (f.filename or "").lower()
        if fname.endswith(".csv"):
            data = f.read()
            line_items, warnings = _parse_csv_bytes(data)
            attachment_name = f.filename
            break
        elif fname.endswith(".xlsx"):
            data = f.read()
            line_items, warnings = _parse_xlsx_bytes(data)
            attachment_name = f.filename
            break

    # ── Fall back to body-embedded CSV if no usable attachment ───────────────
    if not line_items and body.strip():
        line_items, warnings = _extract_line_items_from_body(body)

    # ── Persist regardless of whether we extracted line items ────────────────
    email_id = store.add_email_report(
        sender=sender,
        subject=subject,
        received_at=received_at,
        body_text=body[:4000],      # cap stored body at 4 KB
        line_items=line_items,
        warnings=warnings,
        attachment_name=attachment_name,
    )

    return jsonify({
        "ok": True,
        "email_id": email_id,
        "sender": sender,
        "subject": subject,
        "line_items_parsed": len(line_items),
        "attachment": attachment_name or None,
        "warnings": warnings,
    })


@app.route("/api/list_email_reports", methods=["GET"])
def list_email_reports():
    return jsonify(store.list_email_reports())


@app.route("/api/get_email_report", methods=["GET"])
def get_email_report_route():
    try:
        email_id = int(request.args.get("id", 0))
    except ValueError:
        return jsonify({"error": "Invalid id"}), 400
    report = store.get_email_report(email_id)
    if report is None:
        return jsonify({"error": f"Email report {email_id} not found"}), 404
    store.mark_email_read(email_id)
    return jsonify(report)


@app.route("/api/delete_email_report", methods=["POST"])
def delete_email_report_route():
    data = request.get_json(silent=True) or {}
    try:
        email_id = int(data.get("id", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid id"}), 400
    deleted = store.delete_email_report(email_id)
    return jsonify({"ok": deleted})


@app.route("/api/parse_upload", methods=["POST"])
def parse_upload():
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "No file attached."}), 400

    filename = (f.filename or "").lower()
    data = f.read()

    if filename.endswith(".csv"):
        line_items, warnings = _parse_csv_bytes(data)
    elif filename.endswith((".xlsx", ".xls")):
        if filename.endswith(".xls"):
            return jsonify({"error": "Legacy .xls format is not supported. Please save as .xlsx or .csv."}), 415
        line_items, warnings = _parse_xlsx_bytes(data)
    else:
        return jsonify({"error": "Unsupported file type. Please upload a .csv or .xlsx file."}), 415

    if not line_items and warnings:
        return jsonify({"error": warnings[0], "warnings": warnings}), 422

    total_budgeted = sum(li["budgeted_usd"] for li in line_items)
    total_actual   = sum(li["actual_usd"]   for li in line_items)
    total_variance = round(total_actual - total_budgeted, 2)
    total_variance_pct = round((total_variance / total_budgeted) * 100, 2) if total_budgeted else 0.0

    return jsonify({
        "line_items":          line_items,
        "total_budgeted_usd":  total_budgeted,
        "total_actual_usd":    total_actual,
        "total_variance_usd":  total_variance,
        "total_variance_pct":  total_variance_pct,
        "warnings":            warnings,
        "row_count":           len(line_items),
    })


@app.route("/api/generate_sample_report", methods=["GET"])
def generate_sample_report():
    report_type = request.args.get("report_type", "Q3 Marketing Budget")
    department = request.args.get("department", "Corporate")

    raw = FINANCIAL_TEMPLATES.get(report_type, FINANCIAL_TEMPLATES["Q3 Marketing Budget"])
    line_items = []
    for item in raw:
        budgeted = item["budgeted"]
        actual = item["actual"]
        variance = actual - budgeted
        variance_pct = round((variance / budgeted) * 100, 2) if budgeted else 0.0
        if variance_pct > 5:
            status = "Over Budget"
        elif variance_pct < -5:
            status = "Under Budget"
        else:
            status = "On Track"
        line_items.append({
            "category": item["category"],
            "budgeted_usd": budgeted,
            "actual_usd": actual,
            "variance_usd": round(variance, 2),
            "variance_pct": variance_pct,
            "status": status,
        })

    total_budgeted = sum(li["budgeted_usd"] for li in line_items)
    total_actual = sum(li["actual_usd"] for li in line_items)
    total_variance = round(total_actual - total_budgeted, 2)
    total_variance_pct = round((total_variance / total_budgeted) * 100, 2) if total_budgeted else 0.0

    over_items = [li["category"] for li in line_items if li["status"] == "Over Budget"]
    summary = (
        f"Total spend is ${total_actual:,.2f} against a budget of ${total_budgeted:,.2f} "
        f"({'+' if total_variance >= 0 else ''}{total_variance_pct}% variance). "
        + (f"Categories over budget: {', '.join(over_items)}." if over_items else "All categories within threshold.")
    )

    return jsonify({
        "report_title": report_type, "report_period": "Q3 2025",
        "department": department,
        "total_budgeted_usd": total_budgeted, "total_actual_usd": total_actual,
        "total_variance_usd": total_variance, "total_variance_pct": total_variance_pct,
        "line_items": line_items, "summary": summary,
    })


@app.route("/api/analyze_financial_report", methods=["POST"])
def analyze_financial_report():
    data = request.get_json() or {}
    report_title = data.get("report_title", "Untitled Report")
    total_budgeted = float(data.get("total_budgeted_usd", 0))
    total_actual = float(data.get("total_actual_usd", 0))
    line_items = data.get("line_items", [])

    total_variance = round(total_actual - total_budgeted, 2)
    total_variance_pct = round((total_variance / total_budgeted) * 100, 2) if total_budgeted else 0.0

    flags = []
    risk_bullets = []

    for item in line_items:
        vpct = float(item.get("variance_pct", 0))
        vusd = float(item.get("variance_usd", 0))
        cat = item.get("category", "Unknown")

        if abs(vpct) <= 5:
            continue

        if vpct > 15:
            severity = "High"
            note = f"{cat} is {vpct:+.1f}% over budget (${vusd:+,.2f}). Immediate review required."
        elif vpct > 5:
            severity = "Medium"
            note = f"{cat} is {vpct:+.1f}% over budget (${vusd:+,.2f}). Monitor closely."
        elif vpct < -15:
            severity = "Medium"
            note = f"{cat} is {abs(vpct):.1f}% under budget (${abs(vusd):,.2f} saved). Verify scope delivery."
        else:
            severity = "Low"
            note = f"{cat} is {abs(vpct):.1f}% under budget (${abs(vusd):,.2f}). May indicate deferred spend."

        flags.append({"category": cat, "variance_usd": vusd, "variance_pct": vpct, "severity": severity, "note": note})
        if severity in ("High", "Medium"):
            risk_bullets.append(note)

    high_flags = [f for f in flags if f["severity"] == "High"]
    if total_variance_pct > 10 or len(high_flags) >= 2:
        overall_status = "Critical Overrun"
        recommendation = ("This report contains critical budget overruns across multiple line items. "
                          "Immediate executive intervention is recommended before approval. "
                          "Consider rejecting and requesting a revised budget plan with corrective actions.")
    elif total_variance_pct > 5 or len(high_flags) == 1:
        overall_status = "Requires Scrutiny"
        recommendation = ("This report shows notable variances that warrant leadership attention. "
                          "Review flagged line items with department heads before issuing approval.")
    else:
        overall_status = "Approved for Review"
        recommendation = ("Overall spend is within acceptable tolerance. "
                          "Minor variances are noted but do not represent material risk. "
                          "Report is ready for executive sign-off pending your review.")

    if not risk_bullets:
        risk_bullets = ["No material budget risks identified. All line items within acceptable variance thresholds."]

    return jsonify({
        "report_title": report_title,
        "total_budgeted_usd": total_budgeted, "total_actual_usd": total_actual,
        "total_variance_usd": total_variance, "total_variance_pct": total_variance_pct,
        "overall_status": overall_status, "flags": flags,
        "executive_risk_assessment": risk_bullets, "recommendation": recommendation,
    })



# ---------------------------------------------------------------------------
# Approval decisions (single approver + dual signature)
# ---------------------------------------------------------------------------
_DUAL_SIG_ROLES = ("CFO", "VP Finance")

_NEXT_STEPS = {
    "Approved": [
        "Finance team notified of executive approval.",
        "Report archived to compliance records.",
        "Budget release authorized — department leads may proceed with spend.",
        "Approval confirmation sent to stakeholders.",
    ],
    "Rejected": [
        "Department head notified of rejection with executive notes.",
        "Report returned to originator with required corrections.",
        "Revised report must be resubmitted within 5 business days.",
        "Finance team placed on hold — no budget release until re-approval.",
    ],
    "Revision Requested": [
        "Revision request sent to report owner with executive feedback.",
        "Department has 3 business days to address flagged items.",
        "Revised report will be re-queued for executive review.",
        "Budget on hold pending resubmission and re-approval.",
    ],
}


def _signer_role(decided_by: str) -> str | None:
    """Map a free-text signer ('CFO', 'Jane Tan, VP Finance', ...) to a dual-sig role."""
    s = decided_by.upper()
    if "CFO" in s or "CHIEF FINANCIAL" in s:
        return "CFO"
    if "VP" in s or "VICE PRESIDENT" in s:
        return "VP Finance"
    return None


def _record(report_title, decision, decided_by, timestamp, notes, next_steps, message,
            complete=False, pending=None):
    return jsonify({
        "report_title": report_title, "decision": decision, "decided_by": decided_by,
        "timestamp_utc": timestamp, "notes": notes, "next_steps": next_steps,
        "confirmation_message": message,
        "dual_signature_complete": complete, "pending_cosignatory": pending,
        "memo_url": _memo_url(report_title) if decision == "Approved" else None,
    })


# Keep a matching system report's status in step with approval decisions.
_STATUS_FOR_DECISION = {"Approved": "Approved", "Rejected": "Declined", "Revision Requested": "Pending Review"}


def _log_final(report_title, decision, decided_by, timestamp, notes):
    store.log_decision(report_title, decision, decided_by, timestamp, notes)
    match = store.find_report_by_title(report_title)
    if match and decision in _STATUS_FOR_DECISION:
        store.set_report_status(match["report_id"], _STATUS_FOR_DECISION[decision])


@app.route("/api/pending_signatures", methods=["GET"])
def pending_signatures():
    return jsonify(store.list_pending_signatures())


@app.route("/api/dual_signatures", methods=["GET"])
def dual_signatures():
    """Pending and completed dual-signature approvals (drives the dashboard tracker)."""
    return jsonify({"pending": store.list_pending_signatures(),
                    "completed": store.list_completed_signatures()})


@app.route("/api/record_approval_decision", methods=["POST"])
def record_approval_decision():
    data = request.get_json(silent=True) or {}
    report_title = str(data.get("report_title") or "Untitled Report").strip()
    decided_by = str(data.get("decided_by") or "Executive").strip()
    notes = data.get("notes") or None
    dual = bool(data.get("requires_dual_signature", False))
    timestamp = _now()

    decision = str(data.get("decision", "")).strip().title()
    if decision not in _NEXT_STEPS:
        decision = "Revision Requested"

    # ---------------- dual-signature approval ----------------
    if dual and decision == "Approved":
        role = _signer_role(decided_by)
        pending = store.get_pending_signature(report_title)

        if role is None:
            awaiting = None
            if pending:
                awaiting = next(r for r in _DUAL_SIG_ROLES if r != pending["first_role"])
            return _record(
                report_title, "Signature Not Accepted", decided_by, timestamp, notes,
                [f"Dual-signature approvals must be signed by the {' and the '.join(_DUAL_SIG_ROLES)}.",
                 f"'{decided_by}' is not one of these roles, so no signature was recorded."],
                f"⚠️ SIGNATURE NOT ACCEPTED — '{decided_by}' is not authorised to sign a dual-signature "
                f"approval for '{report_title}'. Only the CFO or VP Finance can sign.",
                pending=awaiting,
            )

        if pending is None:
            sla_due = store.compute_sla_due(timestamp)
            store.add_pending_signature(report_title, decided_by, role, timestamp, notes, sla_due=sla_due)
            store.log_decision(report_title, "First Signature", decided_by, timestamp, notes)
            awaiting = next(r for r in _DUAL_SIG_ROLES if r != role)
            _notify_second_signer(report_title, decided_by, awaiting, sla_due, timestamp)
            return _record(
                report_title, "Pending Second Signature", decided_by, timestamp, notes,
                [f"First signature recorded from **{decided_by}** at {timestamp}.",
                 f"Awaiting countersignature from **{awaiting}** to complete dual-signature approval.",
                 "Budget release is on hold until both signatures are captured.",
                 f"Notify {awaiting} to review and countersign at their earliest convenience.",
                 f"⏱️ Revision due by **{sla_due}** (3 business days). An email and Slack notification has been dispatched to {awaiting}."],
                f"🖊️ FIRST SIGNATURE RECORDED — '{report_title}' has been signed by **{decided_by}** "
                f"on {timestamp}. Awaiting countersignature from **{awaiting}** before clearance can be issued. "
                f"SLA due: **{sla_due}**.",
                pending=awaiting,
            )

        if role == pending["first_role"]:
            awaiting = next(r for r in _DUAL_SIG_ROLES if r != role)
            return _record(
                report_title, "Pending Second Signature", pending["first_signer"], pending["first_timestamp"],
                pending["notes"],
                [f"The {role} already signed at {pending['first_timestamp']} ({pending['first_signer']}).",
                 f"A second signature must come from the **{awaiting}**, not the {role} again."],
                f"⚠️ DUPLICATE SIGNATURE — the {role} has already signed '{report_title}'. "
                f"Still awaiting countersignature from **{awaiting}**.",
                pending=awaiting,
            )

        first_signer, first_ts = pending["first_signer"], pending["first_timestamp"]
        store.complete_dual_signature(report_title, f"{first_signer} + {decided_by}", timestamp)
        combined_notes = "; ".join(filter(None, [pending.get("notes"), notes])) or None
        store.log_decision(report_title, "Countersignature", decided_by, timestamp, notes)
        _log_final(report_title, "Approved", f"{first_signer} + {decided_by}", timestamp, combined_notes)
        return _record(
            report_title, "Approved", f"{first_signer} + {decided_by}", timestamp, combined_notes,
            [f"First signature: **{first_signer}** at {first_ts}.",
             f"Second signature: **{decided_by}** at {timestamp}.",
             "Dual-signature approval complete — budget release authorised.",
             "Finance team notified; report archived to compliance records.",
             "Approval confirmation dispatched to all stakeholders."],
            f"✅ DUAL-SIGNATURE APPROVED — '{report_title}' has been co-signed by "
            f"**{first_signer}** and **{decided_by}**. "
            "Both signatures captured. Budget release authorised and stakeholders notified.",
            complete=True,
        )

    # A rejection or revision request cancels any half-finished dual signature.
    if dual:
        store.clear_pending_signature(report_title)

    # ---------------- single approver ----------------
    messages = {
        "Approved": (
            f"✅ APPROVED — '{report_title}' has been approved by {decided_by} on {timestamp}. "
            "Budget release authorized. Confirmation dispatched to stakeholders."
        ),
        "Rejected": (
            f"❌ REJECTED — '{report_title}' has been rejected by {decided_by} on {timestamp}. "
            "The report has been returned to the originator with required corrections."
        ),
        "Revision Requested": (
            f"🔄 REVISION REQUESTED — '{report_title}' requires revision per {decided_by} on {timestamp}. "
            "The report owner has been notified and must resubmit within 3 business days."
        ),
    }
    _log_final(report_title, decision, decided_by, timestamp, notes)
    return _record(
        report_title, decision, decided_by, timestamp, notes,
        _NEXT_STEPS[decision], messages[decision],
        complete=(decision == "Approved"),
    )



@app.route("/api/sla_status", methods=["GET"])
def sla_status():
    """Return SLA countdown(s) for reports currently in 'Pending Second Signature'.

    Optional query param: ?title=<report_title> — returns a single record.
    Without ?title, returns all pending SLA records.
    """
    title = (request.args.get("title") or "").strip()
    if title:
        result = store.get_sla_status(title)
        if result is None:
            return jsonify({"error": f"No pending second signature found for '{title}'"}), 404
        return jsonify(result)
    return jsonify(store.list_sla_statuses())


# ---------------------------------------------------------------------------
# Decision memos (PDF export)
# ---------------------------------------------------------------------------
from urllib.parse import quote as _quote
from flask import send_file
import io
import memo_pdf


def _memo_url(report_title: str) -> str:
    return f"/api/memo.pdf?title={_quote(report_title)}"


@app.route("/api/approved", methods=["GET"])
def approved():
    """Approved / accepted reports that have a downloadable decision memo."""
    items = store.list_approved()
    for it in items:
        it["memo_url"] = _memo_url(it["report_title"])
    return jsonify(items)


@app.route("/api/memo.pdf", methods=["GET"])
def decision_memo():
    title = (request.args.get("title") or "").strip()
    if not title and request.args.get("report_id"):
        rep = store.get_report(int(request.args["report_id"])) if request.args["report_id"].isdigit() else None
        title = rep["title"] if rep else ""
    approval = next((a for a in store.list_approved() if a["report_key"] == store.report_key(title)), None)
    if not title or approval is None:
        return jsonify({"error": "No approved decision found for that report."}), 404

    pdf = memo_pdf.build_memo(
        approval=approval,
        report=store.get_report(approval["report_id"]) if approval.get("report_id") else None,
        history=store.decision_history(approval["report_title"]),
        next_steps=_NEXT_STEPS["Approved"],
        generated_at=_now(),
    )
    filename = "Decision-Memo-" + "".join(ch if ch.isalnum() else "-" for ch in approval["report_title"]).strip("-") + ".pdf"
    return send_file(io.BytesIO(pdf), mimetype="application/pdf", as_attachment=True, download_name=filename)


if __name__ == "__main__":
    app.run(debug=False)
