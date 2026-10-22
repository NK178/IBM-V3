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


class ReportStatusUpdate(BaseModel):
    report_id: int
    report_title: str
    previous_status: str
    new_status: str
    decision: str
    reason: Optional[str]
    timestamp_utc: str
    confirmation_message: str


@tool(
    permission=ToolPermission.WRITE_ONLY,
    expected_credentials=[{"app_id": APP_ID, "type": ConnectionType.KEY_VALUE}],
)
def BobsBiggestFans_update_report_status(
    report_id: int,
    decision: str,
    reason: Optional[str] = None,
) -> ReportStatusUpdate:
    """Accept or decline a system report, updating its status and returning a confirmation.

    Args:
        report_id (int): The numeric ID of the report to act on (e.g. 101, 102, 103).
        decision (str): The action to take. Must be either 'Accept' or 'Decline'.
        reason (Optional[str]): Optional reason or note when declining a report.
    Returns:
        ReportStatusUpdate: Confirmation record showing the previous status, new status, decision, and a confirmation message.
    """
    return ReportStatusUpdate(**_api("POST", "/api/update_report_status",
                                     body={"report_id": report_id, "decision": decision, "reason": reason}))
