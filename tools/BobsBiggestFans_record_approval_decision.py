from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# In-session dual-signature state store.
# Keyed by report_title; tracks the first signature while awaiting the second.
# ---------------------------------------------------------------------------
_PENDING_DUAL_SIG: dict[str, dict] = {}


class ApprovalRecord(BaseModel):
    report_title: str
    decision: str           # "Approved" | "Rejected" | "Revision Requested" | "Pending Second Signature"
    decided_by: str         # For dual-sig, shows both signatories once complete
    timestamp_utc: str
    notes: Optional[str]
    next_steps: list[str]
    confirmation_message: str
    dual_signature_complete: bool   # True only when both CFO + VP have signed
    pending_cosignatory: Optional[str]  # The role still required when dual-sig is pending


@tool(permission=ToolPermission.WRITE_ONLY)
def BobsBiggestFans_record_approval_decision(
    report_title: str,
    decision: str,
    decided_by: str,
    notes: Optional[str] = None,
    requires_dual_signature: bool = False,
) -> ApprovalRecord:
    """Record the executive's approval decision for a financial report.

    Supports three approval modes:
      • Standard single-approver: set requires_dual_signature=False (default).
      • Dual-signature first leg: set requires_dual_signature=True for the first signatory
        (CFO or VP Finance). The record is held as 'Pending Second Signature'.
      • Dual-signature second leg: call again with requires_dual_signature=True for the
        second signatory. Both signatures are combined and clearance is issued.

    Args:
        report_title (str): The title of the financial report being decided upon.
        decision (str): The decision. Must be one of: 'Approved', 'Rejected', or 'Revision Requested'.
        decided_by (str): Name or title of the approver (e.g. 'CFO', 'VP Finance').
        notes (Optional[str]): Optional notes or conditions attached to the decision.
        requires_dual_signature (bool): Set True when this decision is part of a dual-signature
            workflow (overruns > $50,000). Defaults to False.
    Returns:
        ApprovalRecord: A structured record of the decision including timestamp, dual-signature
            state, next steps, and a confirmation message.
    """
    valid_decisions = {"Approved", "Rejected", "Revision Requested"}
    normalized = decision.strip().title()
    if normalized not in valid_decisions:
        normalized = "Revision Requested"

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # -----------------------------------------------------------------------
    # Dual-signature path
    # -----------------------------------------------------------------------
    if requires_dual_signature and normalized == "Approved":
        _DUAL_SIG_APPROVERS = ["CFO", "VP Finance"]
        pending = _PENDING_DUAL_SIG.get(report_title)

        if pending is None:
            # First leg — store and await second signature
            _PENDING_DUAL_SIG[report_title] = {
                "first_signer": decided_by,
                "first_timestamp": timestamp,
                "notes": notes,
            }
            # Determine who still needs to sign
            signer_upper = decided_by.strip().upper()
            if "CFO" in signer_upper:
                awaiting = "VP Finance"
            elif "VP" in signer_upper:
                awaiting = "CFO"
            else:
                awaiting = next(
                    (r for r in _DUAL_SIG_APPROVERS if r.upper() not in signer_upper), "VP Finance"
                )

            return ApprovalRecord(
                report_title=report_title,
                decision="Pending Second Signature",
                decided_by=decided_by,
                timestamp_utc=timestamp,
                notes=notes,
                next_steps=[
                    f"First signature recorded from **{decided_by}** at {timestamp}.",
                    f"Awaiting countersignature from **{awaiting}** to complete dual-signature approval.",
                    "Budget release is on hold until both signatures are captured.",
                    f"Notify {awaiting} to review and countersign at their earliest convenience.",
                ],
                confirmation_message=(
                    f"🖊️ FIRST SIGNATURE RECORDED — '{report_title}' has been signed by **{decided_by}** "
                    f"on {timestamp}. "
                    f"Awaiting countersignature from **{awaiting}** before clearance can be issued."
                ),
                dual_signature_complete=False,
                pending_cosignatory=awaiting,
            )

        else:
            # Second leg — both signatures present; issue clearance
            first_signer = pending["first_signer"]
            first_ts = pending["first_timestamp"]
            combined_notes = "; ".join(filter(None, [pending.get("notes"), notes]))
            del _PENDING_DUAL_SIG[report_title]

            both_signers = f"{first_signer} + {decided_by}"
            return ApprovalRecord(
                report_title=report_title,
                decision="Approved",
                decided_by=both_signers,
                timestamp_utc=timestamp,
                notes=combined_notes or None,
                next_steps=[
                    f"First signature: **{first_signer}** at {first_ts}.",
                    f"Second signature: **{decided_by}** at {timestamp}.",
                    "Dual-signature approval complete — budget release authorised.",
                    "Finance team notified; report archived to compliance records.",
                    "Approval confirmation dispatched to all stakeholders.",
                ],
                confirmation_message=(
                    f"✅ DUAL-SIGNATURE APPROVED — '{report_title}' has been co-signed by "
                    f"**{first_signer}** and **{decided_by}**. "
                    "Both signatures captured. Budget release authorised and stakeholders notified."
                ),
                dual_signature_complete=True,
                pending_cosignatory=None,
            )

    # -----------------------------------------------------------------------
    # Standard single-approver path
    # -----------------------------------------------------------------------
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
        dual_signature_complete=(normalized == "Approved"),
        pending_cosignatory=None,
    )
