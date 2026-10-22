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


class ReportDetail(BaseModel):
    report_id: int
    title: str
    date: str
    status: str
    summary: str
    recommendation: str


@tool(
    permission=ToolPermission.READ_ONLY,
    expected_credentials=[{"app_id": APP_ID, "type": ConnectionType.KEY_VALUE}],
)
def BobsBiggestFans_get_report(report_id: int) -> ReportDetail:
    """Retrieve a single system report by its ID from the shared report store.

    Args:
        report_id (int): The numeric ID of the report to retrieve (e.g. 101, 102, 103).
    Returns:
        ReportDetail: Full report details including title, date, status, summary, and recommendation.
    """
    return ReportDetail(**_api("GET", "/api/get_report", {"report_id": report_id}))
