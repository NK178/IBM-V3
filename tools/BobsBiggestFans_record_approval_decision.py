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


def _absolute(url: Optional[str]) -> Optional[str]:
    """Turn the API's relative memo link into a full URL the user can click."""
    if not url:
        return None
    return connections.key_value(APP_ID)["base_url"].rstrip("/") + url


class ApprovalRecord(BaseModel):
    report_title: str
    decision: str           # "Approved" | "Rejected" | "Revision Requested" | "Pending Second Signature" | "Signature Not Accepted"
    decided_by: str         # For dual-sig, shows both signatories once complete
    timestamp_utc: str
    notes: Optional[str]
    next_steps: list[str]
    confirmation_message: str
    dual_signature_complete: bool       # True only when both CFO + VP have signed
    pending_cosignatory: Optional[str]  # The role still required when dual-sig is pending
    memo_url: Optional[str] = None      # PDF decision memo link (set once the decision is Approved)


@tool(
    permission=ToolPermission.WRITE_ONLY,
    expected_credentials=[{"app_id": APP_ID, "type": ConnectionType.KEY_VALUE}],
)
def BobsBiggestFans_record_approval_decision(
    report_title: str,
    decision: str,
    decided_by: str,
    notes: Optional[str] = None,
    requires_dual_signature: bool = False,
) -> ApprovalRecord:
    """Record the executive's approval decision for a financial report.

    Supports three approval modes:
      • Standard single-approver: set requires_dual_signature=False (default).
      • Dual-signature first leg: set requires_dual_signature=True for the first signatory
        (CFO or VP Finance). The record is held as 'Pending Second Signature'.
      • Dual-signature second leg: call again with requires_dual_signature=True for the
        other signatory. Both signatures are combined and clearance is issued.
    The same role cannot sign both legs, and only the CFO or VP Finance can sign a dual-signature
    approval; otherwise the decision comes back as 'Signature Not Accepted' or stays pending.
    A 'Rejected' or 'Revision Requested' decision cancels any pending dual signature.

    Args:
        report_title (str): The title of the financial report being decided upon.
        decision (str): The decision. Must be one of: 'Approved', 'Rejected', or 'Revision Requested'.
        decided_by (str): Name or title of the approver (e.g. 'CFO', 'VP Finance').
        notes (Optional[str]): Optional notes or conditions attached to the decision.
        requires_dual_signature (bool): Set True when this decision is part of a dual-signature
            workflow (overruns > $50,000). Defaults to False.
    Returns:
        ApprovalRecord: A structured record of the decision including timestamp, dual-signature
            state, next steps, and a confirmation message.
    """
    result = _api("POST", "/api/record_approval_decision", body={
        "report_title": report_title,
        "decision": decision,
        "decided_by": decided_by,
        "notes": notes,
        "requires_dual_signature": requires_dual_signature,
    })
    result["memo_url"] = _absolute(result.get("memo_url"))
    return ApprovalRecord(**result)
