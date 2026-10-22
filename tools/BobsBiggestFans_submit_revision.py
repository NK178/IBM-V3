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

class RevisionSubmission(BaseModel):
    ok: bool
    previous_report_id: int
    new_report_id: Optional[int] = None
    new_title: Optional[str] = None
    version: Optional[int] = None
    message: str


@tool(
    permission=ToolPermission.WRITE_ONLY,
    expected_credentials=[{"app_id": APP_ID, "type": ConnectionType.KEY_VALUE}],
)
def BobsBiggestFans_submit_revision(
    report_id: int,
    summary: Optional[str] = None,
    recommendation: Optional[str] = None,
    change_note: Optional[str] = None,
    submitted_by: Optional[str] = None,
) -> RevisionSubmission:
    """Submit a revised version of a report that is in 'Revision Requested' status.

    Creates a new report (e.g. "Q4 System Performance Audit (v2)") with status 'Pending Review' and marks the
    old version 'Superseded'. Afterwards, call BobsBiggestFans_compare_reports with the old and new IDs to show
    what changed. At least one of summary or recommendation must differ from the previous version.

    Args:
        report_id (int): The ID of the report that was sent back for revision.
        summary (Optional[str]): The revised summary. Omit to keep the previous one.
        recommendation (Optional[str]): The revised recommendation. Omit to keep the previous one.
        change_note (Optional[str]): A short note describing what changed in this version.
        submitted_by (Optional[str]): Who submitted the revision (e.g. 'Report Owner').
    Returns:
        RevisionSubmission: The new report's ID, title and version, plus a confirmation message.
    """
    r = _api_allow_error("POST", "/api/submit_revision", {
        "report_id": report_id, "summary": summary, "recommendation": recommendation,
        "change_note": change_note, "submitted_by": submitted_by,
    })
    new = r.get("report") or {}
    return RevisionSubmission(ok=bool(r.get("ok")), previous_report_id=report_id,
                              new_report_id=new.get("report_id"), new_title=new.get("title"),
                              version=new.get("version"), message=r.get("message", "Unknown error"))
