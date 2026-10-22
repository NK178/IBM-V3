from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from pydantic import BaseModel
from typing import Optional


# ---------------------------------------------------------------------------
# Embedded Knowledge Base
# Simulates a connected KB of past emails, project proposals, and vendor
# contracts that the agent queries automatically when a variance is High Risk.
# In production this would call a watsonx Discovery / vector-store endpoint.
# ---------------------------------------------------------------------------
_KNOWLEDGE_BASE: list[dict] = [
    # --- Digital Advertising overruns ---
    {
        "keywords": ["digital advertising", "marketing", "advertising", "social media", "media buy"],
        "source_type": "Email",
        "source_ref": "EMAIL-2024-0312 · VP Marketing → CFO",
        "date": "2024-03-12",
        "root_cause": "Campaign scope expanded mid-quarter after board approval of an emergency brand-awareness push following a competitor product launch. Agency retainer was increased by $48K under urgent PO #MKT-9921.",
        "corrective_action": "VP Marketing committed to a revised Q4 media plan with a capped contingency line.",
        "confidence": "High",
    },
    {
        "keywords": ["digital advertising", "programmatic", "display", "google ads", "meta"],
        "source_type": "Vendor Contract",
        "source_ref": "CONTRACT-MEDIABUY-2024-Q3",
        "date": "2024-07-01",
        "root_cause": "Minimum spend clause triggered on programmatic display contract (§4.2) after traffic conversion targets were missed in June. Penalty fee of $22,500 was non-negotiable.",
        "corrective_action": "Legal reviewing contract renewal terms to remove minimum-spend penalty clause.",
        "confidence": "High",
    },
    # --- Cloud / IT Infrastructure overruns ---
    {
        "keywords": ["cloud", "aws", "azure", "gcp", "cloud services", "infrastructure", "it infrastructure"],
        "source_type": "Project Proposal",
        "source_ref": "PROPOSAL-INFRA-2024-09 · CTO Office",
        "date": "2024-09-05",
        "root_cause": "Unplanned DR environment replication triggered by a production incident (INC-8872) on 2024-08-29. Emergency cloud resources provisioned outside the approved CapEx plan, adding ~$31K in compute costs.",
        "corrective_action": "CTO submitted a retroactive budget amendment (REQ-2024-0190). Cloud cost tagging policy updated to flag emergency provisioning in real time.",
        "confidence": "High",
    },
    {
        "keywords": ["cloud", "saas", "software license", "license", "subscription"],
        "source_type": "Email",
        "source_ref": "EMAIL-2024-0801 · IT Procurement → Finance",
        "date": "2024-08-01",
        "root_cause": "Three enterprise SaaS licenses renewed at a higher tier following a vendor-forced migration (end-of-life notification). Total additional annual cost: $18,200.",
        "corrective_action": "Procurement team evaluating open-source alternatives for two of the three tools.",
        "confidence": "Medium",
    },
    # --- Salaries / Headcount overruns ---
    {
        "keywords": ["salaries", "salary", "headcount", "payroll", "compensation", "benefits", "overtime"],
        "source_type": "Project Proposal",
        "source_ref": "PROPOSAL-HC-2024-Q2 · CHRO → Finance Committee",
        "date": "2024-06-15",
        "root_cause": "Three senior engineering backfills approved in Q2 to prevent project delivery slippage (Project ATLAS). Offers were signed at market rates 12–18% above the original band assumptions in the annual budget model.",
        "corrective_action": "CHRO aligned Q3 budget amendment. Future hiring plans to include a 15% market-rate buffer in salary bands.",
        "confidence": "High",
    },
    {
        "keywords": ["overtime", "contract labor", "consultants", "contractors", "temp staff"],
        "source_type": "Vendor Contract",
        "source_ref": "CONTRACT-CONSULT-2024-07 · PMO",
        "date": "2024-07-10",
        "root_cause": "Surge contractor engagement (SOW-PMO-2024-04) for a time-boxed regulatory compliance sprint. Fixed-fee SOW of $65K executed under emergency procurement (waiver PROC-2024-112).",
        "corrective_action": "PMO will include regulatory buffer line in 2025 annual budget. Emergency procurement waiver process under review.",
        "confidence": "High",
    },
    # --- Security / Compliance overruns ---
    {
        "keywords": ["security", "compliance", "audit", "pen test", "penetration", "sox", "gdpr"],
        "source_type": "Email",
        "source_ref": "EMAIL-2024-1001 · CISO → CFO",
        "date": "2024-10-01",
        "root_cause": "External penetration test scope was expanded after an internal vulnerability scan (SCAN-Q3-2024) surfaced two critical-severity findings. Remediation and re-test added $29K above the approved security budget.",
        "corrective_action": "CISO created a dedicated Security Reserve line ($50K) in 2025 budget proposal.",
        "confidence": "High",
    },
    # --- Travel / Events overruns ---
    {
        "keywords": ["travel", "events", "conference", "t&e", "entertainment", "hospitality"],
        "source_type": "Email",
        "source_ref": "EMAIL-2024-0520 · Sales Ops → Finance",
        "date": "2024-05-20",
        "root_cause": "Two unplanned executive roadshows (Chicago + London) were approved at short notice by the CEO to support a key enterprise deal closure. Total cost overrun: $17,400.",
        "corrective_action": "Sales Ops updated T&E policy to require 5-business-day lead time for roadshows above $5K.",
        "confidence": "Medium",
    },
    # --- Generic / fallback ---
    {
        "keywords": ["general", "miscellaneous", "other", "operational", "expense"],
        "source_type": "Project Proposal",
        "source_ref": "PROPOSAL-OPEX-2024-Q3 · Finance Business Partners",
        "date": "2024-08-20",
        "root_cause": "General operational expense variance attributable to inflationary price increases across multiple supplier contracts renewed in Q3. Average unit cost increase of 8.3% vs. prior-year assumption.",
        "corrective_action": "Finance Business Partners initiating a supplier renegotiation programme for Q1 2025.",
        "confidence": "Medium",
    },
]


class HistoricalJustification(BaseModel):
    category: str
    severity: str
    source_type: str
    source_ref: str
    date: str
    root_cause: str
    corrective_action: str
    confidence: str
    pre_fetch_summary: str


@tool(permission=ToolPermission.READ_ONLY)
def BobsBiggestFans_fetch_historical_justification(
    category: str,
    variance_usd: float,
    variance_pct: float,
    severity: str,
    report_title: Optional[str] = None,
) -> HistoricalJustification:
    """Query the connected Knowledge Base (past emails, project proposals, and vendor contracts) to retrieve the most likely root-cause justification for a High Risk budget variance. Attach the result directly to the executive review prompt so the reviewer has full context without manually searching.

    Call this tool automatically whenever a variance is flagged as 'High' severity by BobsBiggestFans_analyze_financial_report. Do NOT wait for the user to ask.

    Args:
        category (str): The line-item category with the High Risk variance (e.g. 'Digital Advertising', 'Cloud Services', 'Salaries').
        variance_usd (float): The dollar value of the variance (positive = over budget).
        variance_pct (float): The percentage variance (positive = over budget).
        severity (str): The severity classification from the analysis tool ('High', 'Medium', or 'Low').
        report_title (Optional[str]): The title of the financial report, used to narrow the KB search context.
    Returns:
        HistoricalJustification: A structured justification record including source type, document reference, root cause, corrective action, and a pre-formatted executive summary ready to attach to the review prompt.
    """
    category_lower = category.lower()

    # Score each KB entry by keyword overlap with the category string
    best_match: Optional[dict] = None
    best_score = -1

    for entry in _KNOWLEDGE_BASE:
        score = sum(1 for kw in entry["keywords"] if kw in category_lower)
        if score > best_score:
            best_score = score
            best_match = entry

    # Fall back to the generic "operational" entry if no keyword matched
    if best_match is None or best_score == 0:
        best_match = _KNOWLEDGE_BASE[-1]  # generic fallback

    direction = "over" if variance_usd >= 0 else "under"
    abs_usd = abs(variance_usd)
    abs_pct = abs(variance_pct)
    report_clause = f" in **{report_title}**" if report_title else ""

    pre_fetch_summary = (
        f"**📎 KB Pre-Fetch — {severity} Risk: {category}**\n\n"
        f"The **{category}** line item is **{abs_pct:.1f}% {direction} budget** "
        f"(${abs_usd:,.2f}){report_clause}. "
        f"The Knowledge Base surfaced the following historical justification "
        f"(confidence: **{best_match['confidence']}**):\n\n"
        f"**Source:** {best_match['source_type']} — _{best_match['source_ref']}_ ({best_match['date']})\n\n"
        f"**Root Cause:** {best_match['root_cause']}\n\n"
        f"**Corrective Action on Record:** {best_match['corrective_action']}\n\n"
        f"_This context was automatically retrieved from the connected Knowledge Base "
        f"and attached to your review prompt to eliminate manual search time._"
    )

    return HistoricalJustification(
        category=category,
        severity=severity,
        source_type=best_match["source_type"],
        source_ref=best_match["source_ref"],
        date=best_match["date"],
        root_cause=best_match["root_cause"],
        corrective_action=best_match["corrective_action"],
        confidence=best_match["confidence"],
        pre_fetch_summary=pre_fetch_summary,
    )
