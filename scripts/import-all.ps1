# Windows PowerShell import script
# Run as: powershell -File scripts/import-all.ps1

$orchestrate = ".\venv\Scripts\orchestrate.exe"

Write-Host "==> Setting up the report API connection..."
# Tools that read/write report state call the Render web app (app.py).
# Set it first, e.g.:  $env:REPORT_API_URL = "https://financial-report-review-agent.onrender.com"
if (-not $env:REPORT_API_URL) { Write-Error "Set REPORT_API_URL to your Render web app URL"; exit 1 }
& $orchestrate connections add -a bobs_report_api
foreach ($envName in @("draft", "live")) {
  & $orchestrate connections configure -a bobs_report_api --env $envName --kind key_value --type team
  & $orchestrate connections set-credentials -a bobs_report_api --env $envName -e "base_url=$env:REPORT_API_URL"
}

Write-Host "==> Importing tools..."
& $orchestrate tools import -k python -f tools/BobsBiggestFans_generate_sample_report.py
& $orchestrate tools import -k python -f tools/BobsBiggestFans_analyze_financial_report.py
& $orchestrate tools import -k python -f tools/BobsBiggestFans_fetch_historical_justification.py
& $orchestrate tools import -k python -f tools/BobsBiggestFans_route_overrun_approval.py
& $orchestrate tools import -k python -f tools/BobsBiggestFans_record_approval_decision.py -a bobs_report_api
& $orchestrate tools import -k python -f tools/BobsBiggestFans_get_report.py -a bobs_report_api
& $orchestrate tools import -k python -f tools/BobsBiggestFans_compare_reports.py -a bobs_report_api
& $orchestrate tools import -k python -f tools/BobsBiggestFans_update_report_status.py -a bobs_report_api

Write-Host "==> Importing agent..."
& $orchestrate agents import -f agents/BobsBiggestFans_Financial_Report_Review_Agent.yaml

Write-Host "==> Done. BobsBiggestFans_Financial_Report_Review_Agent is deployed."
