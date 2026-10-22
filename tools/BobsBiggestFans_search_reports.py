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


def _api(method: str, path: str, params: Optional[dict] = None, body: Optional[dict] = None) -> dict:
    base = connections.key_value(APP_ID)["base_url"].rstrip("/")
    url = f"{base}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        # Generous timeout: a sleeping Render free instance can take ~50s to wake up.
        with urllib.request.urlopen(req, timeout=75) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError) as e:
        raise RuntimeError(f"Report service is unavailable ({e}). Try again in a minute.") from e


class ReportListing(BaseModel):
    report_id: int
    title: str
    date: str
    status: str
    version: int
    parent_id: Optional[int] = None
    change_note: Optional[str] = None


class ReportSearchResult(BaseModel):
    count: int
    reports: list[ReportListing]


@tool(
    permission=ToolPermission.READ_ONLY,
    expected_credentials=[{"app_id": APP_ID, "type": ConnectionType.KEY_VALUE}],
)
def BobsBiggestFans_search_reports(
    query: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    latest_only: bool = True,
) -> ReportSearchResult:
    """Search and filter system reports by text, status, and date.

    Args:
        query (Optional[str]): Free-text search over report ID, title, summary, recommendation and change notes (e.g. "latency", "security", "102").
        status (Optional[str]): Comma-separated statuses to keep, e.g. "Pending Review", "Revision Requested", "Accepted,Approved", "Declined", "Superseded".
        date_from (Optional[str]): Earliest report date to include, as YYYY-MM-DD.
        date_to (Optional[str]): Latest report date to include, as YYYY-MM-DD.
        latest_only (bool): When True (default), hide older versions that were superseded by a revision.
    Returns:
        ReportSearchResult: Matching reports (newest first) with their ID, title, date, status and version.
    """
    params = {"sort": "date_desc", "latest": "1" if latest_only else "0"}
    if query:
        params["q"] = query
    if status:
        params["status"] = status
    if date_from:
        params["from"] = date_from
    if date_to:
        params["to"] = date_to
    rows = _api("GET", "/api/list_reports", params)
    return ReportSearchResult(count=len(rows), reports=[ReportListing(**r) for r in rows])
