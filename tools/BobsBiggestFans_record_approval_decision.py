from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone


class ApprovalRecord(BaseModel):
    report_title: str
    decision: str  # "Approved" | "Rejected" | "Revision Requested"
    decided_by: str
    timestamp_utc: str
    notes: Optional[str]
    next_steps: list[str]
    confirmation_message: str


@tool(permission=ToolPermission.WRITE_ONLY)
def BobsBiggestFans_record_approval_decision(
    report_title: str,
    decision: str,
    decided_by: str,
    notes: Optional[str] = None,
) -> ApprovalRecord:
    """Record the executive's approval decision for a financial report and return a structured confirmation with next steps.

    Args:
        report_title (str): The title of the financial report being decided upon.
        decision (str): The decision made by the executive. Must be one of: 'Approved', 'Rejected', or 'Revision Requested'.
        decided_by (str): Name or title of the executive making the decision (e.g. 'CFO', 'VP Finance').
        notes (Optional[str]): Optional notes or conditions attached to the decision.
    Returns:
        ApprovalRecord: A structured record of the decision including timestamp, next steps, and a confirmation message.
    """
    valid_decisions = {"Approved", "Rejected", "Revision Requested"}
    normalized = decision.strip().title()
    if normalized not in valid_decisions:
        normalized = "Revision Requested"

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    next_steps_map: dict[str, list[str]] = {
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

    confirmation_map: dict[str, str] = {
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

    return ApprovalRecord(
        report_title=report_title,
        decision=normalized,
        decided_by=decided_by,
        timestamp_utc=timestamp,
        notes=notes,
        next_steps=next_steps_map[normalized],
        confirmation_message=confirmation_map[normalized],
    )
