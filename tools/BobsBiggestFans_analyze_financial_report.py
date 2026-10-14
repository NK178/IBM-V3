from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from pydantic import BaseModel
from typing import Optional


class VarianceFlag(BaseModel):
    category: str
    variance_usd: float
    variance_pct: float
    severity: str  # "High" | "Medium" | "Low"
    note: str


class FinancialAnalysis(BaseModel):
    report_title: str
    total_budgeted_usd: float
    total_actual_usd: float
    total_variance_usd: float
    total_variance_pct: float
    overall_status: str  # "Approved for Review" | "Requires Scrutiny" | "Critical Overrun"
    flags: list[VarianceFlag]
    executive_risk_assessment: list[str]
    recommendation: str


@tool(permission=ToolPermission.READ_ONLY)
def BobsBiggestFans_analyze_financial_report(
    report_title: str,
    total_budgeted_usd: float,
    total_actual_usd: float,
    line_items_json: str,
) -> FinancialAnalysis:
    """Analyze a financial report's line items to produce variance flags, risk assessment, and an executive recommendation.

    Args:
        report_title (str): The title of the financial report being analyzed.
        total_budgeted_usd (float): Total budgeted amount in USD across all line items.
        total_actual_usd (float): Total actual spend in USD across all line items.
        line_items_json (str): JSON string of line items, each with keys: category, budgeted_usd, actual_usd, variance_usd, variance_pct, status.
    Returns:
        FinancialAnalysis: Structured analysis including variance flags, risk bullets, overall status, and recommendation.
    """
    import json

    total_variance = round(total_actual_usd - total_budgeted_usd, 2)
    total_variance_pct = round((total_variance / total_budgeted_usd) * 100, 2) if total_budgeted_usd else 0.0

    try:
        items = json.loads(line_items_json)
    except (json.JSONDecodeError, TypeError):
        items = []

    flags: list[VarianceFlag] = []
    risk_bullets: list[str] = []

    for item in items:
        vpct = float(item.get("variance_pct", 0))
        vusd = float(item.get("variance_usd", 0))
        cat = item.get("category", "Unknown")

        if abs(vpct) <= 5:
            continue  # within normal tolerance

        if vpct > 15:
            severity = "High"
            note = f"{cat} is {vpct:+.1f}% over budget (${vusd:+,.2f}). Immediate review required."
        elif vpct > 5:
            severity = "Medium"
            note = f"{cat} is {vpct:+.1f}% over budget (${vusd:+,.2f}). Monitor closely."
        elif vpct < -15:
            severity = "Medium"
            note = f"{cat} is {abs(vpct):.1f}% under budget (${vusd:,.2f} saved). Verify scope delivery."
        else:
            severity = "Low"
            note = f"{cat} is {abs(vpct):.1f}% under budget (${vusd:,.2f}). May indicate deferred spend."

        flags.append(VarianceFlag(
            category=cat,
            variance_usd=vusd,
            variance_pct=vpct,
            severity=severity,
            note=note,
        ))

        if severity in ("High", "Medium"):
            risk_bullets.append(note)

    # Determine overall status
    high_flags = [f for f in flags if f.severity == "High"]
    if total_variance_pct > 10 or len(high_flags) >= 2:
        overall_status = "Critical Overrun"
        recommendation = (
            "This report contains critical budget overruns across multiple line items. "
            "Immediate executive intervention is recommended before approval. "
            "Consider rejecting and requesting a revised budget plan with corrective actions."
        )
    elif total_variance_pct > 5 or len(high_flags) == 1:
        overall_status = "Requires Scrutiny"
        recommendation = (
            "This report shows notable variances that warrant leadership attention. "
            "Review flagged line items with department heads before issuing approval. "
            "A revision request is advisable if root cause explanations are not provided."
        )
    else:
        overall_status = "Approved for Review"
        recommendation = (
            "Overall spend is within acceptable tolerance. "
            "Minor variances are noted but do not represent material risk. "
            "Report is ready for executive sign-off pending your review."
        )

    if not risk_bullets:
        risk_bullets = ["No material budget risks identified. All line items within acceptable variance thresholds."]

    return FinancialAnalysis(
        report_title=report_title,
        total_budgeted_usd=total_budgeted_usd,
        total_actual_usd=total_actual_usd,
        total_variance_usd=total_variance,
        total_variance_pct=total_variance_pct,
        overall_status=overall_status,
        flags=flags,
        executive_risk_assessment=risk_bullets,
        recommendation=recommendation,
    )
