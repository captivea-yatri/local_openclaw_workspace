#!/usr/bin/env bash
# T0 staging smoke — run from custom_addons root.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p test_automation/reports
if [[ -f test_automation/staging.env ]]; then
  set -a
  # shellcheck source=/dev/null
  source test_automation/staging.env
  set +a
fi
exec python3 test_automation/run_test_suite.py --all --mode smoke \
  --load-staging-env \
  --report-file test_automation/reports/smoke.json \
  "$@"
