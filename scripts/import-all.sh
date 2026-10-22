#!/bin/bash
# macOS/Linux: run as  bash scripts/import-all.sh
# Windows:     run as  powershell -File scripts/import-all.ps1  (see import-all.ps1)
set -e

source venv/Scripts/activate 2>/dev/null || source venv/bin/activate

echo "==> Setting up the report API connection..."
# Tools that read/write report state call the Render web app (app.py).
# Set REPORT_API_URL to your Render URL first, e.g.
#   export REPORT_API_URL=https://financial-report-review-agent.onrender.com
: "${REPORT_API_URL:?Set REPORT_API_URL to your Render web app URL}"
orchestrate connections add -a bobs_report_api || true
for ENV in draft live; do
  orchestrate connections configure -a bobs_report_api --env $ENV --kind key_value --type team
  orchestrate connections set-credentials -a bobs_report_api --env $ENV -e base_url="$REPORT_API_URL"
done

echo "==> Importing tools..."
orchestrate tools import -k python -f tools/BobsBiggestFans_generate_sample_report.py
orchestrate tools import -k python -f tools/BobsBiggestFans_analyze_financial_report.py
orchestrate tools import -k python -f tools/BobsBiggestFans_fetch_historical_justification.py
orchestrate tools import -k python -f tools/BobsBiggestFans_route_overrun_approval.py
orchestrate tools import -k python -f tools/BobsBiggestFans_record_approval_decision.py -a bobs_report_api
orchestrate tools import -k python -f tools/BobsBiggestFans_get_report.py -a bobs_report_api
orchestrate tools import -k python -f tools/BobsBiggestFans_compare_reports.py -a bobs_report_api
orchestrate tools import -k python -f tools/BobsBiggestFans_update_report_status.py -a bobs_report_api
orchestrate tools import -k python -f tools/BobsBiggestFans_list_email_reports.py -a bobs_report_api
orchestrate tools import -k python -f tools/BobsBiggestFans_search_reports.py -a bobs_report_api
orchestrate tools import -k python -f tools/BobsBiggestFans_request_revision.py -a bobs_report_api
orchestrate tools import -k python -f tools/BobsBiggestFans_submit_revision.py -a bobs_report_api
orchestrate tools import -k python -f tools/BobsBiggestFans_get_sla_status.py -a bobs_report_api

echo "==> Importing agent..."
orchestrate agents import -f agents/BobsBiggestFans_Financial_Report_Review_Agent.yaml

echo "==> Done. BobsBiggestFans_Financial_Report_Review_Agent is deployed."
