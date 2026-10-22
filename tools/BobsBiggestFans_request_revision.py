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



def _api_allow_error(method: str, path: str, body: dict) -> dict:
    """Like _api, but returns the JSON body of 4xx responses (they carry a user-facing message)."""
    try:
        return _api(method, path, body=body)
    except RuntimeError as e:
        cause = e.__cause__
        if isinstance(cause, urllib.error.HTTPError) and 400 <= cause.code < 500:
            try:
                return json.loads(cause.read())
            except ValueError:
                pass
        raise

class RevisionRequest(BaseModel):
    ok: bool
    report_id: int
    report_title: str
    status: str
    message: str


@tool(
    permission=ToolPermission.WRITE_ONLY,
    expected_credentials=[{"app_id": APP_ID, "type": ConnectionType.KEY_VALUE}],
)
def BobsBiggestFans_request_revision(
    report_id: int,
    notes: Optional[str] = None,
    decided_by: Optional[str] = None,
) -> RevisionRequest:
    """Send a 'Pending Review' system report back to its owner for revision.

    The report's status becomes 'Revision Requested'. The owner then submits a new version with
    BobsBiggestFans_submit_revision, which creates v2 and marks this version as Superseded.

    Args:
        report_id (int): The numeric ID of the report to send back (e.g. 102).
        notes (Optional[str]): What needs to change, e.g. "Add root-cause analysis for the latency warnings".
        decided_by (Optional[str]): Who is requesting the revision (e.g. 'Boss').
    Returns:
        RevisionRequest: Whether it worked, the report's new status, and a confirmation message.
    """
    r = _api_allow_error("POST", "/api/request_revision",
                         {"report_id": report_id, "notes": notes, "decided_by": decided_by})
    rep = r.get("report") or {}
    return RevisionRequest(ok=bool(r.get("ok")), report_id=report_id, report_title=rep.get("title", "N/A"),
                           status=rep.get("status", "N/A"), message=r.get("message", "Unknown error"))
