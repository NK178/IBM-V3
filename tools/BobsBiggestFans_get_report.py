from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from pydantic import BaseModel
from typing import Optional


class ReportDetail(BaseModel):
    report_id: int
    title: str
    date: str
    status: str
    summary: str
    recommendation: str


# ---------------------------------------------------------------------------
# In-memory mock data store shared across tools in this module.
# Import and mutate MOCK_REPORTS from other tool files via the helper below.
# ---------------------------------------------------------------------------
MOCK_REPORTS: dict[int, dict] = {
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


@tool(permission=ToolPermission.READ_ONLY)
def BobsBiggestFans_get_report(report_id: int) -> ReportDetail:
    """Retrieve a single system report by its ID from the mock data store.

    Args:
        report_id (int): The numeric ID of the report to retrieve (e.g. 101, 102, 103).
    Returns:
        ReportDetail: Full report details including title, date, status, summary, and recommendation.
    """
    report = MOCK_REPORTS.get(report_id)
    if report is None:
        return ReportDetail(
            report_id=report_id,
            title="Report Not Found",
            date="N/A",
            status="Not Found",
            summary=f"No report with ID {report_id} exists in the data store.",
            recommendation="Please request a valid report ID (101, 102, or 103).",
        )
    return ReportDetail(**report)
