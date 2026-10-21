# Windows PowerShell import script
# Run as: powershell -File scripts/import-all.ps1

$orchestrate = ".\venv\Scripts\orchestrate.exe"

Write-Host "==> Importing tools..."
& $orchestrate tools import -k python -f tools/BobsBiggestFans_generate_sample_report.py
& $orchestrate tools import -k python -f tools/BobsBiggestFans_analyze_financial_report.py
& $orchestrate tools import -k python -f tools/BobsBiggestFans_record_approval_decision.py
& $orchestrate tools import -k python -f tools/BobsBiggestFans_get_report.py
& $orchestrate tools import -k python -f tools/BobsBiggestFans_compare_reports.py
& $orchestrate tools import -k python -f tools/BobsBiggestFans_update_report_status.py

Write-Host "==> Importing agent..."
& $orchestrate agents import -f agents/BobsBiggestFans_Financial_Report_Review_Agent.yaml

Write-Host "==> Done. BobsBiggestFans_Financial_Report_Review_Agent is deployed."
