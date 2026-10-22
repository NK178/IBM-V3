"""Single source of truth for report state and dual-signature approvals.

Both the dashboard (app.py) and the watsonx Orchestrate tools (via the HTTP API)
read and write through this module, so the chat and the web UI always agree.

Backed by SQLite so state is shared across gunicorn workers. On Render's free
plan the disk is ephemeral: data resets to SEED_REPORTS on redeploy/restart.
"""
import os
import re
import sqlite3
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.db"))

SEED_REPORTS = [
    {
        "report_id": 101,
        "title": "Q3 System Performance Audit",
        "date": "2026-09-15",
        "status": "Pending Review",
        "summary": "CPU utilization averaged 68%, memory peak at 82%, zero unauthorized access attempts detected.",
        "recommendation": "Upgrade server pool B prior to Q4 traffic spikes.",
    },
    {
        "report_id": 102,
        "title": "Q4 System Performance Audit",
        "date": "2026-10-15",
        "status": "Pending Review",
        "summary": "CPU utilization averaged 84%, memory peak at 94%, 2 minor latency warnings detected.",
        "recommendation": "Immediate scaling of server pool B required.",
    },
    {
        "report_id": 103,
        "title": "Annual Security Compliance Review",
        "date": "2026-10-01",
        "status": "Approved",
        "summary": "Fully compliant with ISO/IEC 27001 standards.",
        "recommendation": "Maintain current access control policies.",
    },
]

REPORT_FIELDS = ("report_id", "title", "date", "status", "summary", "recommendation",
                 "version", "parent_id", "root_id", "change_note")


@contextmanager
def _db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _db() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute(
            """CREATE TABLE IF NOT EXISTS reports (
                   report_id INTEGER PRIMARY KEY,
                   title TEXT NOT NULL, date TEXT NOT NULL, status TEXT NOT NULL,
                   summary TEXT NOT NULL, recommendation TEXT NOT NULL)"""
        )
        # Versioning (revision loop). Added with ALTER so existing databases upgrade in place.
        cols = {r["name"] for r in c.execute("PRAGMA table_info(reports)")}
        for col, ddl in (("version", "INTEGER NOT NULL DEFAULT 1"), ("parent_id", "INTEGER"),
                         ("root_id", "INTEGER"), ("change_note", "TEXT")):
            if col not in cols:
                c.execute(f"ALTER TABLE reports ADD COLUMN {col} {ddl}")
        c.execute("UPDATE reports SET root_id = report_id WHERE root_id IS NULL")
        c.execute(
            """CREATE TABLE IF NOT EXISTS pending_dual_sig (
                   report_key TEXT PRIMARY KEY,
                   report_title TEXT NOT NULL,
                   first_signer TEXT NOT NULL,
                   first_role TEXT NOT NULL,
                   first_timestamp TEXT NOT NULL,
                   notes TEXT)"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS completed_dual_sig (
                   report_key TEXT PRIMARY KEY,
                   report_title TEXT NOT NULL,
                   signers TEXT NOT NULL,
                   completed_timestamp TEXT NOT NULL)"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS decisions (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   report_key TEXT NOT NULL,
                   report_id INTEGER,
                   report_title TEXT NOT NULL,
                   decision TEXT NOT NULL,
                   decided_by TEXT NOT NULL,
                   notes TEXT,
                   timestamp TEXT NOT NULL)"""
        )
        c.execute("CREATE INDEX IF NOT EXISTS decisions_by_key ON decisions(report_key, id)")
        c.execute(
            """CREATE TABLE IF NOT EXISTS email_reports (
                   id          INTEGER PRIMARY KEY AUTOINCREMENT,
                   sender      TEXT NOT NULL,
                   subject     TEXT NOT NULL,
                   received_at TEXT NOT NULL,
                   body_text   TEXT NOT NULL DEFAULT '',
                   status      TEXT NOT NULL DEFAULT 'Unread',
                   line_items  TEXT NOT NULL DEFAULT '[]',
                   warnings    TEXT NOT NULL DEFAULT '[]',
                   attachment_name TEXT NOT NULL DEFAULT '')"""
        )
        c.executemany(
            "INSERT OR IGNORE INTO reports (report_id, title, date, status, summary, recommendation, root_id)"
            " VALUES (:report_id, :title, :date, :status, :summary, :recommendation, :report_id)",
            SEED_REPORTS,
        )


# ---------------------------------------------------------------- reports
def get_report(report_id: int) -> dict | None:
    with _db() as c:
        row = c.execute("SELECT * FROM reports WHERE report_id = ?", (report_id,)).fetchone()
    return dict(row) if row else None


def list_reports(q: str | None = None, statuses: list[str] | None = None, date_from: str | None = None,
                 date_to: str | None = None, latest_only: bool = False, sort: str = "id") -> list[dict]:
    """All reports, optionally filtered.

    q            case-insensitive match on id, title, summary, recommendation or change note
    statuses     keep only these statuses (case-insensitive)
    date_from/to inclusive ISO dates (YYYY-MM-DD) on the report date
    latest_only  hide versions that have been superseded by a newer revision
    sort         "id" | "date_desc" | "date_asc" | "title"
    """
    with _db() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM reports ORDER BY report_id")]
    if q:
        needle = q.strip().lower().lstrip("#")
        rows = [r for r in rows if needle in " ".join(
            str(r.get(f) or "") for f in ("report_id", "title", "summary", "recommendation", "change_note")).lower()]
    if statuses:
        wanted = {s.strip().lower() for s in statuses if s.strip()}
        rows = [r for r in rows if r["status"].lower() in wanted]
    if date_from:
        rows = [r for r in rows if r["date"] >= date_from]
    if date_to:
        rows = [r for r in rows if r["date"] <= date_to]
    if latest_only:
        rows = [r for r in rows if r["status"] != "Superseded"]
    if sort == "date_desc":
        rows.sort(key=lambda r: (r["date"], r["report_id"]), reverse=True)
    elif sort == "date_asc":
        rows.sort(key=lambda r: (r["date"], r["report_id"]))
    elif sort == "title":
        rows.sort(key=lambda r: (r["title"].lower(), r["version"]))
    return rows


# ---------------------------------------------------------- revision loop
_VERSION_SUFFIX = re.compile(r"\s*\(v\d+\)\s*$")


def base_title(title: str) -> str:
    return _VERSION_SUFFIX.sub("", title).strip()


def version_chain(report_id: int) -> list[dict]:
    """Every version of the report's family, oldest first."""
    rep = get_report(report_id)
    if rep is None:
        return []
    with _db() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM reports WHERE root_id = ? ORDER BY version, report_id", (rep["root_id"],))]


def create_revision(parent_id: int, summary: str, recommendation: str, change_note: str | None,
                    date: str) -> dict | None:
    """Create the next version of a report and mark the parent as superseded. Returns the new report."""
    with _db() as c:
        parent = c.execute("SELECT * FROM reports WHERE report_id = ?", (parent_id,)).fetchone()
        if parent is None:
            return None
        parent = dict(parent)
        root_id = parent["root_id"] or parent["report_id"]
        latest = c.execute("SELECT MAX(version) FROM reports WHERE root_id = ?", (root_id,)).fetchone()[0] or 1
        new_version = latest + 1
        new_id = (c.execute("SELECT MAX(report_id) FROM reports").fetchone()[0] or 100) + 1
        c.execute(
            "INSERT INTO reports (report_id, title, date, status, summary, recommendation,"
            " version, parent_id, root_id, change_note) VALUES (?, ?, ?, 'Pending Review', ?, ?, ?, ?, ?, ?)",
            (new_id, f"{base_title(parent['title'])} (v{new_version})", date, summary, recommendation,
             new_version, parent_id, root_id, change_note),
        )
        c.execute("UPDATE reports SET status = 'Superseded' WHERE report_id = ?", (parent_id,))
        row = c.execute("SELECT * FROM reports WHERE report_id = ?", (new_id,)).fetchone()
    return dict(row)


def set_report_status(report_id: int, new_status: str) -> tuple[dict, str] | None:
    """Update a report's status. Returns (updated_report, previous_status) or None if missing."""
    with _db() as c:
        row = c.execute("SELECT * FROM reports WHERE report_id = ?", (report_id,)).fetchone()
        if row is None:
            return None
        c.execute("UPDATE reports SET status = ? WHERE report_id = ?", (new_status, report_id))
    report = dict(row)
    previous = report["status"]
    report["status"] = new_status
    return report, previous


def reset() -> None:
    """Restore seed data and clear pending signatures (handy before a demo)."""
    with _db() as c:
        c.execute("DELETE FROM reports")
        c.execute("DELETE FROM pending_dual_sig")
        c.execute("DELETE FROM completed_dual_sig")
        c.execute("DELETE FROM decisions")
        c.execute("DELETE FROM email_reports")
    init_db()


# ------------------------------------------------------- email reports
import json as _json


def add_email_report(
    sender: str,
    subject: str,
    received_at: str,
    body_text: str,
    line_items: list,
    warnings: list,
    attachment_name: str,
) -> int:
    """Insert a parsed inbound email report. Returns the new row id."""
    with _db() as c:
        cur = c.execute(
            """INSERT INTO email_reports
               (sender, subject, received_at, body_text, status, line_items, warnings, attachment_name)
               VALUES (?, ?, ?, ?, 'Unread', ?, ?, ?)""",
            (
                sender, subject, received_at, body_text,
                _json.dumps(line_items), _json.dumps(warnings), attachment_name,
            ),
        )
        return cur.lastrowid


def list_email_reports() -> list[dict]:
    with _db() as c:
        rows = c.execute("SELECT * FROM email_reports ORDER BY received_at DESC").fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["line_items"] = _json.loads(d["line_items"])
        d["warnings"]   = _json.loads(d["warnings"])
        result.append(d)
    return result


def get_email_report(email_id: int) -> dict | None:
    with _db() as c:
        row = c.execute("SELECT * FROM email_reports WHERE id = ?", (email_id,)).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["line_items"] = _json.loads(d["line_items"])
    d["warnings"]   = _json.loads(d["warnings"])
    return d


def mark_email_read(email_id: int) -> None:
    with _db() as c:
        c.execute("UPDATE email_reports SET status = 'Read' WHERE id = ?", (email_id,))


def delete_email_report(email_id: int) -> bool:
    with _db() as c:
        cur = c.execute("DELETE FROM email_reports WHERE id = ?", (email_id,))
    return cur.rowcount > 0


# ------------------------------------------------------- dual signatures
def _key(report_title: str) -> str:
    return " ".join(report_title.lower().split())


def get_pending_signature(report_title: str) -> dict | None:
    with _db() as c:
        row = c.execute("SELECT * FROM pending_dual_sig WHERE report_key = ?", (_key(report_title),)).fetchone()
    return dict(row) if row else None


def list_pending_signatures() -> list[dict]:
    with _db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM pending_dual_sig ORDER BY first_timestamp")]


def add_pending_signature(report_title: str, signer: str, role: str, timestamp: str, notes: str | None) -> None:
    """Start a dual-signature cycle (also clears any earlier completed cycle for this title)."""
    with _db() as c:
        c.execute("DELETE FROM completed_dual_sig WHERE report_key = ?", (_key(report_title),))
        c.execute(
            "INSERT OR REPLACE INTO pending_dual_sig VALUES (?, ?, ?, ?, ?, ?)",
            (_key(report_title), report_title, signer, role, timestamp, notes),
        )


def clear_pending_signature(report_title: str) -> None:
    with _db() as c:
        c.execute("DELETE FROM pending_dual_sig WHERE report_key = ?", (_key(report_title),))



def complete_dual_signature(report_title: str, signers: str, timestamp: str) -> None:
    """Close a dual-signature cycle: drop the pending row and remember the completion."""
    with _db() as c:
        c.execute("DELETE FROM pending_dual_sig WHERE report_key = ?", (_key(report_title),))
        c.execute(
            "INSERT OR REPLACE INTO completed_dual_sig VALUES (?, ?, ?, ?)",
            (_key(report_title), report_title, signers, timestamp),
        )


def list_completed_signatures() -> list[dict]:
    with _db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM completed_dual_sig ORDER BY completed_timestamp")]



# ------------------------------------------------------------ decision log
# Every Accept / Decline / Approve / signature is logged here, so decision memos
# (PDF export) can show who decided what and when.
APPROVED_DECISIONS = ("Approved", "Accepted")


def report_key(report_title: str) -> str:
    return _key(report_title)


def find_report_by_title(report_title: str) -> dict | None:
    with _db() as c:
        for row in c.execute("SELECT * FROM reports"):
            if _key(row["title"]) == _key(report_title):
                return dict(row)
    return None


def log_decision(report_title: str, decision: str, decided_by: str, timestamp: str,
                 notes: str | None = None, report_id: int | None = None) -> None:
    if report_id is None:
        match = find_report_by_title(report_title)
        report_id = match["report_id"] if match else None
    with _db() as c:
        c.execute(
            "INSERT INTO decisions (report_key, report_id, report_title, decision, decided_by, notes, timestamp)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (_key(report_title), report_id, report_title, decision, decided_by, notes, timestamp),
        )


def decision_history(report_title: str) -> list[dict]:
    with _db() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM decisions WHERE report_key = ? ORDER BY id", (_key(report_title),))]


def list_approved() -> list[dict]:
    """Everything whose latest final decision is an approval, plus seeded reports already 'Approved'.

    Signature legs ('First Signature') are not final decisions and are skipped when finding the latest.
    """
    finals = ("Approved", "Accepted", "Rejected", "Declined", "Revision Requested")
    with _db() as c:
        rows = [dict(r) for r in c.execute(
            f"""SELECT d.* FROM decisions d
                JOIN (SELECT report_key, MAX(id) AS id FROM decisions
                      WHERE decision IN ({','.join('?' * len(finals))}) GROUP BY report_key) last
                  ON d.id = last.id""", finals)]
        approved = [r for r in rows if r["decision"] in APPROVED_DECISIONS]
        logged = {r["report_key"] for r in rows}
        # Seed reports that start out approved and were never re-decided in the app.
        for rep in c.execute("SELECT * FROM reports WHERE status IN ('Approved', 'Accepted')"):
            if _key(rep["title"]) not in logged:
                approved.append({"report_key": _key(rep["title"]), "report_id": rep["report_id"],
                                 "report_title": rep["title"], "decision": rep["status"],
                                 "decided_by": "approver on file", "notes": None,
                                 "timestamp": rep["date"]})
    return sorted(approved, key=lambda r: r["timestamp"], reverse=True)


init_db()
