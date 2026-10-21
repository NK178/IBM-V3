from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from pydantic import BaseModel
from typing import Optional


class FieldDiff(BaseModel):
    field: str
    report_a_value: str
    report_b_value: str
    differs: bool


class ReportComparison(BaseModel):
    report_a_id: int
    report_b_id: int
    report_a_title: str
    report_b_title: str
    field_differences: list[FieldDiff]
    key_takeaways: list[str]
    recommendation_variance: str


# Inline mock store — kept in sync with BobsBiggestFans_get_report.py
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


def _compare_field(field: str, val_a: str, val_b: str) -> FieldDiff:
    return FieldDiff(
        field=field,
        report_a_value=val_a,
        report_b_value=val_b,
        differs=(val_a != val_b),
    )


@tool(permission=ToolPermission.READ_ONLY)
def BobsBiggestFans_compare_reports(report_id_a: int, report_id_b: int) -> ReportComparison:
    """Compare two system reports side by side, highlighting key differences in metrics and recommendations.

    Args:
        report_id_a (int): The numeric ID of the first report to compare (e.g. 101).
        report_id_b (int): The numeric ID of the second report to compare (e.g. 102).
    Returns:
        ReportComparison: A structured side-by-side comparison with field-level diffs, key takeaways, and recommendation variance.
    """
    def _not_found(rid: int) -> dict:
        return {
            "report_id": rid,
            "title": f"Report {rid} Not Found",
            "date": "N/A",
            "status": "Not Found",
            "summary": f"No report with ID {rid} exists.",
            "recommendation": "N/A",
        }

    a = _MOCK_REPORTS.get(report_id_a) or _not_found(report_id_a)
    b = _MOCK_REPORTS.get(report_id_b) or _not_found(report_id_b)

    compare_fields = ["title", "date", "status", "summary", "recommendation"]
    diffs: list[FieldDiff] = [
        _compare_field(f.replace("_", " ").title(), str(a[f]), str(b[f]))
        for f in compare_fields
    ]

    # Build key takeaways from fields that actually differ
    takeaways: list[str] = []
    for d in diffs:
        if d.differs:
            takeaways.append(
                f"• **{d.field}** changed from \"{d.report_a_value}\" → \"{d.report_b_value}\"."
            )

    if not takeaways:
        takeaways = ["Both reports are identical across all compared fields."]

    # Recommendation variance summary
    if a["recommendation"] == b["recommendation"]:
        rec_variance = "Both reports share the same recommendation."
    else:
        rec_variance = (
            f"Report {report_id_a} recommends: \"{a['recommendation']}\" — "
            f"Report {report_id_b} recommends: \"{b['recommendation']}\". "
            "These recommendations differ and may reflect escalating system conditions."
        )

    return ReportComparison(
        report_a_id=report_id_a,
        report_b_id=report_id_b,
        report_a_title=a["title"],
        report_b_title=b["title"],
        field_differences=diffs,
        key_takeaways=takeaways,
        recommendation_variance=rec_variance,
    )
