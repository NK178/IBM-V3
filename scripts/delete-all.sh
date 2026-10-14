#!/bin/bash

# Activate virtual environment
source venv/Scripts/activate 2>/dev/null || source venv/bin/activate

echo "==> Removing agent..."
orchestrate agents remove -n BobsBiggestFans_Financial_Report_Review_Agent --kind native || true

echo "==> Removing tools..."
orchestrate tools remove -n BobsBiggestFans_record_approval_decision || true
orchestrate tools remove -n BobsBiggestFans_analyze_financial_report || true
orchestrate tools remove -n BobsBiggestFans_generate_sample_report || true

echo "==> Done. All BobsBiggestFans resources removed."
