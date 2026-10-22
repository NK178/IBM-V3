from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from ibm_watsonx_orchestrate.agent_builder.connections import ConnectionType
from ibm_watsonx_orchestrate.run import connections
from pydantic import BaseModel
from typing import Optional
import json
import urllib.error
import urllib.parse
import urllib.request

APP_ID = "bobs_report_api"


def _api(method: str, path: str, params: Optional[dict] = None, body: Optional[dict] = None) -> dict:
    base = connections.key_value(APP_ID)["base_url"].rstrip("/")
    url = f"{base}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=75) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError) as e:
        raise RuntimeError(f"Report service is unavailable ({e}). Try again in a minute.") from e


class EmailReportSummary(BaseModel):
    id: int
    sender: str
    subject: str
    received_at: str
    status: str           # "Unread" | "Read"
    line_items_count: int
    attachment_name: str
    has_data: bool


class EmailInboxResult(BaseModel):
    total: int
    unread: int
    reports: list[EmailReportSummary]


@tool(
    permission=ToolPermission.READ_ONLY,
    expected_credentials=[{"app_id": APP_ID, "type": ConnectionType.KEY_VALUE}],
)
def BobsBiggestFans_list_email_reports() -> EmailInboxResult:
    """List all inbound email reports received from employees via Mailgun.

    Returns a summary of every email in the inbox, including the sender, subject,
    received timestamp, read/unread status, and how many financial line items were
    parsed from the attachment or email body. Use this to show the boss a collated
    view of what employees have submitted, then offer to analyze any report with
    BobsBiggestFans_analyze_financial_report.

    Returns:
        EmailInboxResult: Total count, unread count, and list of email summaries.
    """
    raw: list[dict] = _api("GET", "/api/list_email_reports")
    summaries = [
        EmailReportSummary(
            id=r["id"],
            sender=r["sender"],
            subject=r["subject"],
            received_at=r["received_at"],
            status=r["status"],
            line_items_count=len(r.get("line_items") or []),
            attachment_name=r.get("attachment_name") or "",
            has_data=len(r.get("line_items") or []) > 0,
        )
        for r in raw
    ]
    unread = sum(1 for s in summaries if s.status == "Unread")
    return EmailInboxResult(total=len(summaries), unread=unread, reports=summaries)
