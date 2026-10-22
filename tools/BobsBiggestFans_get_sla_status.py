from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from ibm_watsonx_orchestrate.agent_builder.connections import ConnectionType
from ibm_watsonx_orchestrate.run import connections
from pydantic import BaseModel
from typing import Optional
import json
import urllib.error
import urllib.parse
import urllib.request

# Report and approval state lives in the shared store behind the Render web app
# (app.py + store.py), so the chat and the dashboard always agree.
# The base URL comes from the key_value connection below, key "base_url".
APP_ID = "bobs_report_api"


def _api(method: str, path: str, params: Optional[dict] = None) -> dict | list:
    base = connections.key_value(APP_ID)["base_url"].rstrip("/")
    url = f"{base}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    req = urllib.request.Request(url, method=method,
                                 headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=75) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError) as e:
        raise RuntimeError(f"Report service is unavailable ({e}). Try again in a minute.") from e


class SLAStatus(BaseModel):
    report_title: str
    first_signer: str
    first_role: str
    first_timestamp: str
    pending_cosignatory: str      # The role that must countersign
    sla_due: str                  # ISO-8601 date by which the second signature is due
    business_days_remaining: int  # Business days left before SLA breach
    calendar_days_remaining: int  # Calendar days left (may be negative when breached)
    is_breached: bool             # True if today is past the SLA due date
    status_label: str             # Human-readable label e.g. "🟢 2 business days remaining"


@tool(
    permission=ToolPermission.READ_ONLY,
    expected_credentials=[{"app_id": APP_ID, "type": ConnectionType.KEY_VALUE}],
)
def BobsBiggestFans_get_sla_status(
    report_title: Optional[str] = None,
) -> list[SLAStatus]:
    """Return SLA countdown timers for reports currently in 'Pending Second Signature'.

    The SLA window is 3 business days from the first signature. This tool surfaces
    how many business days remain before the second-signature deadline is breached.

    Args:
        report_title (Optional[str]): Title of a specific report to check. If omitted,
            returns SLA status for ALL reports currently awaiting a second signature.
    Returns:
        list[SLAStatus]: One record per pending report, including who must countersign,
            the due date, days remaining, and a colour-coded status label.
    """
    params = {"title": report_title} if report_title else None
    raw = _api("GET", "/api/sla_status", params=params)
    # Endpoint returns a single dict when ?title is supplied, list otherwise.
    if isinstance(raw, dict):
        raw = [raw]
    return [SLAStatus(**item) for item in raw]
