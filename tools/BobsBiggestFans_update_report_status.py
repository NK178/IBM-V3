from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone


class ReportStatusUpdate(BaseModel):
    report_id: int
    report_title: str
    previous_status: str
    new_status: str
    decision: str
    reason: Optional[str]
    timestamp_utc: str
    confirmation_message: str


# Inline mock store — mutable dict simulating a persistent store within a session.
# Kept in sync with BobsBiggestFans_get_report.py and BobsBiggestFans_compare_reports.py.
_MOCK_REPORTS: dict[int, dict] = {
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


@tool(permission=ToolPermission.WRITE_ONLY)
def BobsBiggestFans_update_report_status(
    report_id: int,
    decision: str,
    reason: Optional[str] = None,
) -> ReportStatusUpdate:
    """Accept or decline a system report, updating its status and returning a confirmation.

    Args:
        report_id (int): The numeric ID of the report to act on (e.g. 101, 102, 103).
        decision (str): The action to take. Must be either 'Accept' or 'Decline'.
        reason (Optional[str]): Optional reason or note when declining a report.
    Returns:
        ReportStatusUpdate: Confirmation record showing the previous status, new status, decision, and a confirmation message.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    report = _MOCK_REPORTS.get(report_id)
    if report is None:
        return ReportStatusUpdate(
            report_id=report_id,
            report_title="Report Not Found",
            previous_status="N/A",
            new_status="N/A",
            decision=decision,
            reason=reason,
            timestamp_utc=timestamp,
            confirmation_message=(
                f"❌ Report {report_id} was not found in the data store. "
                "Please use a valid report ID (101, 102, or 103)."
            ),
        )

    normalized = decision.strip().title()
    if normalized not in {"Accept", "Decline"}:
        normalized = "Decline"

    previous_status = report["status"]
    new_status = "Accepted" if normalized == "Accept" else "Declined"

    # Mutate the in-session store so subsequent get_report / compare_reports
    # calls within the same invocation reflect the change.
    report["status"] = new_status

    if normalized == "Accept":
        confirmation = (
            f"✅ Report {report_id} has been accepted and logged successfully. "
            f"Status updated from \"{previous_status}\" to \"{new_status}\" at {timestamp}."
        )
    else:
        reason_suffix = f" Reason provided: \"{reason}\"." if reason else ""
        confirmation = (
            f"🚫 Report {report_id} has been marked as declined.{reason_suffix} "
            f"Status updated from \"{previous_status}\" to \"{new_status}\" at {timestamp}."
        )

    return ReportStatusUpdate(
        report_id=report_id,
        report_title=report["title"],
        previous_status=previous_status,
        new_status=new_status,
        decision=normalized,
        reason=reason,
        timestamp_utc=timestamp,
        confirmation_message=confirmation,
    )
