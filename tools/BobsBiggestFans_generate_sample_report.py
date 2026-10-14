from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from pydantic import BaseModel
from typing import Optional
import random


class LineItem(BaseModel):
    category: str
    budgeted_usd: float
    actual_usd: float
    variance_usd: float
    variance_pct: float
    status: str  # "On Track" | "Over Budget" | "Under Budget"


class SampleFinancialReport(BaseModel):
    report_title: str
    report_period: str
    department: str
    total_budgeted_usd: float
    total_actual_usd: float
    total_variance_usd: float
    total_variance_pct: float
    line_items: list[LineItem]
    summary: str


@tool(permission=ToolPermission.READ_ONLY)
def BobsBiggestFans_generate_sample_report(
    report_type: str = "Q3 Marketing Budget",
    department: Optional[str] = None,
) -> SampleFinancialReport:
    """Generate a realistic mock financial report for executive review and demonstration purposes.

    Args:
        report_type (str): The type of report to generate, e.g. 'Q3 Marketing Budget', 'IT Infrastructure Grant', 'Operational Expense Report'. Defaults to 'Q3 Marketing Budget'.
        department (Optional[str]): Optional department name to include in the report header.
    Returns:
        SampleFinancialReport: A structured mock financial report with line items, variances, and a summary.
    """
    dept = department or "Corporate"

    templates: dict[str, list[dict]] = {
        "Q3 Marketing Budget": [
            {"category": "Digital Advertising", "budgeted": 120_000, "actual": 134_500},
            {"category": "Events & Sponsorships", "budgeted": 85_000, "actual": 79_200},
            {"category": "Content Production", "budgeted": 45_000, "actual": 46_800},
            {"category": "Agency Fees", "budgeted": 60_000, "actual": 71_300},
            {"category": "Market Research", "budgeted": 25_000, "actual": 18_900},
            {"category": "PR & Communications", "budgeted": 30_000, "actual": 30_100},
        ],
        "IT Infrastructure Grant": [
            {"category": "Hardware Procurement", "budgeted": 200_000, "actual": 198_400},
            {"category": "Cloud Services", "budgeted": 95_000, "actual": 112_800},
            {"category": "Security Licensing", "budgeted": 40_000, "actual": 40_000},
            {"category": "Implementation Services", "budgeted": 75_000, "actual": 88_500},
            {"category": "Training & Enablement", "budgeted": 20_000, "actual": 14_200},
            {"category": "Contingency Reserve", "budgeted": 30_000, "actual": 7_600},
        ],
        "Operational Expense Report": [
            {"category": "Salaries & Benefits", "budgeted": 450_000, "actual": 452_300},
            {"category": "Facilities & Rent", "budgeted": 80_000, "actual": 80_000},
            {"category": "Travel & Expenses", "budgeted": 35_000, "actual": 41_700},
            {"category": "Software Subscriptions", "budgeted": 28_000, "actual": 31_200},
            {"category": "Office Supplies", "budgeted": 8_000, "actual": 6_400},
            {"category": "Legal & Compliance", "budgeted": 50_000, "actual": 47_800},
        ],
    }

    raw = templates.get(report_type, templates["Q3 Marketing Budget"])
    line_items: list[LineItem] = []

    for item in raw:
        budgeted = item["budgeted"]
        actual = item["actual"]
        variance = actual - budgeted
        variance_pct = round((variance / budgeted) * 100, 2) if budgeted else 0.0
        if variance_pct > 5:
            status = "Over Budget"
        elif variance_pct < -5:
            status = "Under Budget"
        else:
            status = "On Track"
        line_items.append(LineItem(
            category=item["category"],
            budgeted_usd=budgeted,
            actual_usd=actual,
            variance_usd=round(variance, 2),
            variance_pct=variance_pct,
            status=status,
        ))

    total_budgeted = sum(li.budgeted_usd for li in line_items)
    total_actual = sum(li.actual_usd for li in line_items)
    total_variance = round(total_actual - total_budgeted, 2)
    total_variance_pct = round((total_variance / total_budgeted) * 100, 2) if total_budgeted else 0.0

    over_items = [li.category for li in line_items if li.status == "Over Budget"]
    summary = (
        f"Total spend is ${total_actual:,.2f} against a budget of ${total_budgeted:,.2f} "
        f"({'+' if total_variance >= 0 else ''}{total_variance_pct}% variance). "
        + (f"Categories over budget: {', '.join(over_items)}." if over_items else "All categories within threshold.")
    )

    return SampleFinancialReport(
        report_title=report_type,
        report_period="Q3 2025",
        department=dept,
        total_budgeted_usd=total_budgeted,
        total_actual_usd=total_actual,
        total_variance_usd=total_variance,
        total_variance_pct=total_variance_pct,
        line_items=line_items,
        summary=summary,
    )
