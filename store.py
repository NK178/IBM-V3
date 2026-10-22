"""Single source of truth for report state and dual-signature approvals.

Both the dashboard (app.py) and the watsonx Orchestrate tools (via the HTTP API)
read and write through this module, so the chat and the web UI always agree.

Backed by SQLite so state is shared across gunicorn workers. On Render's free
plan the disk is ephemeral: data resets to SEED_REPORTS on redeploy/restart.
"""
import os
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

REPORT_FIELDS = ("report_id", "title", "date", "status", "summary", "recommendation")


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
        c.executemany(
            "INSERT OR IGNORE INTO reports VALUES (:report_id, :title, :date, :status, :summary, :recommendation)",
            SEED_REPORTS,
        )


# ---------------------------------------------------------------- reports
def get_report(report_id: int) -> dict | None:
    with _db() as c:
        row = c.execute("SELECT * FROM reports WHERE report_id = ?", (report_id,)).fetchone()
    return dict(row) if row else None


def list_reports() -> list[dict]:
    with _db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM reports ORDER BY report_id")]


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
    init_db()


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
