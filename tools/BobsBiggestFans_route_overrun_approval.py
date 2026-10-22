from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from pydantic import BaseModel
from typing import Optional


# ---------------------------------------------------------------------------
# Approval tier thresholds (USD)
# ---------------------------------------------------------------------------
_AUTO_CLEAR_CEILING = 5_000.00   # < $5,000  → single-click auto-clear
_DUAL_SIG_FLOOR = 50_000.00      # > $50,000 → dual-signature (CFO + VP)
# Between $5,000 and $50,000 → standard single-approver review


class ApprovalRequirement(BaseModel):
    approver_role: str            # e.g. "Auto-Clear" | "Single Approver" | "CFO + VP (Dual-Signature)"
    approvers_required: list[str] # ordered list of required approver titles
    signatures_needed: int        # 1 for single, 2 for dual
    action_label: str             # UI button label hint
    escalation_reason: str        # human-readable rationale


class OverrunApprovalRoute(BaseModel):
    report_title: str
    overrun_amount_usd: float
    overrun_pct: float
    approval_tier: str            # "AUTO_CLEAR" | "STANDARD" | "DUAL_SIGNATURE"
    approval_requirement: ApprovalRequirement
    auto_clear_eligible: bool
    routing_summary: str
    next_action: str


@tool(permission=ToolPermission.READ_ONLY)
def BobsBiggestFans_route_overrun_approval(
    report_title: str,
    overrun_amount_usd: float,
    total_budgeted_usd: float,
    overrun_category: Optional[str] = None,
) -> OverrunApprovalRoute:
    """Determine the correct multi-level approval route for a budget overrun based on its dollar amount.

    Tier rules:
      • Overrun < $5,000   → AUTO_CLEAR: single-click auto-clear recommendation; no manual sign-off required.
      • Overrun $5,000–$50,000 → STANDARD: routed to a single approver (VP Finance) for review.
      • Overrun > $50,000  → DUAL_SIGNATURE: requires co-signatures from both CFO and VP Finance before clearance.

    Args:
        report_title (str): The title of the financial report containing the overrun.
        overrun_amount_usd (float): The absolute dollar value of the budget overrun (positive number).
        total_budgeted_usd (float): The total budget for the report, used to compute the overrun percentage.
        overrun_category (Optional[str]): The specific line-item category driving the overrun, if known.
    Returns:
        OverrunApprovalRoute: Structured routing record with tier classification, required approvers,
            action labels, and a plain-language routing summary.
    """
    overrun = abs(overrun_amount_usd)
    overrun_pct = round((overrun / total_budgeted_usd) * 100, 2) if total_budgeted_usd else 0.0
    category_clause = f" in the **{overrun_category}** category" if overrun_category else ""

    # -----------------------------------------------------------------------
    # Tier 1 — AUTO_CLEAR  (< $5,000)
    # -----------------------------------------------------------------------
    if overrun < _AUTO_CLEAR_CEILING:
        tier = "AUTO_CLEAR"
        requirement = ApprovalRequirement(
            approver_role="Auto-Clear",
            approvers_required=[],
            signatures_needed=0,
            action_label="✅ Auto-Clear Overrun",
            escalation_reason=(
                f"Overrun of ${overrun:,.2f} ({overrun_pct}%){category_clause} is below the "
                f"${_AUTO_CLEAR_CEILING:,.0f} auto-clear threshold. "
                "No manual sign-off is required; the system recommends immediate clearance."
            ),
        )
        routing_summary = (
            f"This overrun of **${overrun:,.2f}**{category_clause} qualifies for **auto-clear**. "
            "Click [Auto-Clear Overrun] to record clearance without escalation."
        )
        next_action = (
            "Click [Auto-Clear Overrun] to instantly clear this overrun. "
            "A clearance record will be logged automatically."
        )
        auto_clear_eligible = True

    # -----------------------------------------------------------------------
    # Tier 3 — DUAL_SIGNATURE  (> $50,000)
    # -----------------------------------------------------------------------
    elif overrun > _DUAL_SIG_FLOOR:
        tier = "DUAL_SIGNATURE"
        requirement = ApprovalRequirement(
            approver_role="CFO + VP Finance (Dual-Signature)",
            approvers_required=["CFO", "VP Finance"],
            signatures_needed=2,
            action_label="🔐 Submit for Dual-Signature Approval",
            escalation_reason=(
                f"Overrun of ${overrun:,.2f} ({overrun_pct}%){category_clause} exceeds the "
                f"${_DUAL_SIG_FLOOR:,.0f} dual-signature threshold. "
                "Both the CFO and VP Finance must co-sign before this overrun can be cleared."
            ),
        )
        routing_summary = (
            f"This overrun of **${overrun:,.2f}**{category_clause} requires **dual-signature approval** "
            f"from the **CFO** and **VP Finance**. "
            "Both signatures must be recorded before clearance is issued."
        )
        next_action = (
            "Step 1 — CFO: review and sign via [Record CFO Approval]. "
            "Step 2 — VP Finance: review and countersign via [Record VP Approval]. "
            "Clearance is issued only after both signatures are captured."
        )
        auto_clear_eligible = False

    # -----------------------------------------------------------------------
    # Tier 2 — STANDARD  ($5,000 – $50,000)
    # -----------------------------------------------------------------------
    else:
        tier = "STANDARD"
        requirement = ApprovalRequirement(
            approver_role="VP Finance (Single Approver)",
            approvers_required=["VP Finance"],
            signatures_needed=1,
            action_label="📋 Submit for VP Finance Review",
            escalation_reason=(
                f"Overrun of ${overrun:,.2f} ({overrun_pct}%){category_clause} falls in the "
                f"standard review band (${_AUTO_CLEAR_CEILING:,.0f}–${_DUAL_SIG_FLOOR:,.0f}). "
                "A single VP Finance sign-off is required."
            ),
        )
        routing_summary = (
            f"This overrun of **${overrun:,.2f}**{category_clause} requires **VP Finance approval**. "
            "One authorised signature is sufficient to clear this overrun."
        )
        next_action = (
            "Submit to VP Finance via [Submit for VP Finance Review]. "
            "Record the approval decision once the VP has reviewed."
        )
        auto_clear_eligible = False

    return OverrunApprovalRoute(
        report_title=report_title,
        overrun_amount_usd=overrun,
        overrun_pct=overrun_pct,
        approval_tier=tier,
        approval_requirement=requirement,
        auto_clear_eligible=auto_clear_eligible,
        routing_summary=routing_summary,
        next_action=next_action,
    )
