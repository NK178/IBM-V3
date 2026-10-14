#!/bin/bash
# macOS/Linux: run as  bash scripts/import-all.sh
# Windows:     run as  powershell -File scripts/import-all.ps1  (see import-all.ps1)
set -e

source venv/Scripts/activate 2>/dev/null || source venv/bin/activate

echo "==> Importing tools..."
orchestrate tools import -k python -f tools/BobsBiggestFans_generate_sample_report.py
orchestrate tools import -k python -f tools/BobsBiggestFans_analyze_financial_report.py
orchestrate tools import -k python -f tools/BobsBiggestFans_record_approval_decision.py

echo "==> Importing agent..."
orchestrate agents import -f agents/BobsBiggestFans_Financial_Report_Review_Agent.yaml

echo "==> Done. BobsBiggestFans_Financial_Report_Review_Agent is deployed."
