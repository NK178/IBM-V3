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


class FieldDiff(BaseModel):
    field: str
    report_a_value: str
    report_b_value: str
    differs: bool


class ReportComparison(BaseModel):
    report_a_id: int
    report_b_id: int
    report_a_title: str
    report_b_title: str
    field_differences: list[FieldDiff]
    key_takeaways: list[str]
    recommendation_variance: str


@tool(
    permission=ToolPermission.READ_ONLY,
    expected_credentials=[{"app_id": APP_ID, "type": ConnectionType.KEY_VALUE}],
)
def BobsBiggestFans_compare_reports(report_id_a: int, report_id_b: int) -> ReportComparison:
    """Compare two system reports side by side and highlight field-level differences.

    Args:
        report_id_a (int): The numeric ID of the first report to compare (e.g. 101).
        report_id_b (int): The numeric ID of the second report to compare (e.g. 102).
    Returns:
        ReportComparison: A structured side-by-side comparison with field-level diffs, key takeaways, and recommendation variance.
    """
    return ReportComparison(**_api("GET", "/api/compare_reports",
                                   {"report_id_a": report_id_a, "report_id_b": report_id_b}))
