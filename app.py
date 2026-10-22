from flask import Flask, request, jsonify, render_template
from datetime import datetime, timezone
import json

app = Flask(__name__)

# ---------------------------------------------------------------------------
# In-memory mock data store (session-scoped, resets on restart)
# ---------------------------------------------------------------------------
MOCK_REPORTS = {
    101: {
        "report_id": 101,
        "title": "Q3 System Performance Audit",
        "date": "2026-09-15",
        "status": "Pending Review",
        "summary": "CPU utilization averaged 68%, memory peak at 82%, zero unauthorized access attempts detected.",
        "recommendation": "Upgrade server pool B prior to Q4 traffic spikes.",
    },
    102: {
        "report_id": 102,
        "title": "Q4 System Performance Audit",
        "date": "2026-10-15",
        "status": "Pending Review",
        "summary": "CPU utilization averaged 84%, memory peak at 94%, 2 minor latency warnings detected.",
        "recommendation": "Immediate scaling of server pool B required.",
    },
    103: {
        "report_id": 103,
        "title": "Annual Security Compliance Review",
        "date": "2026-10-01",
        "status": "Approved",
        "summary": "Fully compliant with ISO/IEC 27001 standards.",
        "recommendation": "Maintain current access control policies.",
    },
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


@app.route("/api/get_report", methods=["GET"])
def get_report():
    try:
        report_id = int(request.args.get("report_id", 0))
    except ValueError:
        return jsonify({"error": "Invalid report_id"}), 400

    report = MOCK_REPORTS.get(report_id)
    if report is None:
        return jsonify({
            "report_id": report_id,
            "title": "Report Not Found",
            "date": "N/A",
            "status": "Not Found",
            "summary": f"No report with ID {report_id} exists in the data store.",
            "recommendation": "Please request a valid report ID (101, 102, or 103).",
        })
    return jsonify(report)


@app.route("/api/list_reports", methods=["GET"])
def list_reports():
    return jsonify([
        {"report_id": r["report_id"], "title": r["title"], "date": r["date"], "status": r["status"]}
        for r in MOCK_REPORTS.values()
    ])


@app.route("/api/compare_reports", methods=["GET"])
def compare_reports():
    try:
        id_a = int(request.args.get("report_id_a", 0))
        id_b = int(request.args.get("report_id_b", 0))
    except ValueError:
        return jsonify({"error": "Invalid report IDs"}), 400

    def not_found(rid):
        return {"report_id": rid, "title": f"Report {rid} Not Found",
                "date": "N/A", "status": "Not Found",
                "summary": f"No report with ID {rid} exists.", "recommendation": "N/A"}

    a = MOCK_REPORTS.get(id_a) or not_found(id_a)
    b = MOCK_REPORTS.get(id_b) or not_found(id_b)

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
    data = request.get_json() or {}
    try:
        report_id = int(data.get("report_id", 0))
    except ValueError:
        return jsonify({"error": "Invalid report_id"}), 400

    decision = str(data.get("decision", "")).strip().title()
    reason = data.get("reason")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    report = MOCK_REPORTS.get(report_id)
    if report is None:
        return jsonify({
            "report_id": report_id, "report_title": "Report Not Found",
            "previous_status": "N/A", "new_status": "N/A",
            "decision": decision, "reason": reason, "timestamp_utc": timestamp,
            "confirmation_message": f"Report {report_id} was not found. Use a valid ID (101, 102, or 103).",
        })

    if decision not in {"Accept", "Decline"}:
        decision = "Decline"

    previous_status = report["status"]
    new_status = "Accepted" if decision == "Accept" else "Declined"
    report["status"] = new_status

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


@app.route("/api/record_approval_decision", methods=["POST"])
def record_approval_decision():
    data = request.get_json() or {}
    report_title = data.get("report_title", "Untitled Report")
    decision = str(data.get("decision", "")).strip().title()
    decided_by = data.get("decided_by", "Executive")
    notes = data.get("notes")
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    valid = {"Approved", "Rejected", "Revision Requested"}
    if decision not in valid:
        decision = "Revision Requested"

    next_steps_map = {
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

    msg_map = {
        "Approved": f"APPROVED — '{report_title}' has been approved by {decided_by} on {timestamp}.",
        "Rejected": f"REJECTED — '{report_title}' has been rejected by {decided_by} on {timestamp}.",
        "Revision Requested": f"REVISION REQUESTED — '{report_title}' requires revision per {decided_by} on {timestamp}.",
    }

    return jsonify({
        "report_title": report_title, "decision": decision,
        "decided_by": decided_by, "timestamp_utc": timestamp,
        "notes": notes, "next_steps": next_steps_map[decision],
        "confirmation_message": msg_map[decision],
    })


if __name__ == "__main__":
    app.run(debug=False)
