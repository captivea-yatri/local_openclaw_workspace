# Odoo RPC test automation

Self-contained **staging QA toolkit**. See [STAGING_QA.md](STAGING_QA.md) for the full runbook.

**New feature?** → [ADD_SCENARIO.md](ADD_SCENARIO.md) · **PR?** → [PR_CHECKLIST.md](PR_CHECKLIST.md)

**Main entry:** `run_test_suite.py` or `python3 -m test_automation`  
**Unified matrix:** `run_matrix.py`  
**T0 smoke:** `./test_automation/run_staging_smoke.sh`

## Quick start (staging)

```bash
cp test_automation/staging.env.example test_automation/staging.env
# edit staging.env

./test_automation/run_staging_smoke.sh
# or:
python3 test_automation/run_test_suite.py --all --mode smoke --load-staging-env
```

## Commands

```bash
# Catalog + all use cases
python3 test_automation/run_test_suite.py --list

# Smoke: every scenario once (~5 min)
python3 test_automation/run_test_suite.py --all --mode smoke --load-staging-env

# Role-based: 3 business features × all roles
python3 test_automation/run_test_suite.py --all --mode role \\
  --load-staging-env --roles-from db --strict

# 11 scripts × all roles
python3 test_automation/run_test_suite.py --all --mode role-scripts \\
  --load-staging-env --roles-from db --strict

# Complete matrix
python3 test_automation/run_matrix.py --all --roles-from db --strict --load-staging-env

# Expectations from matrix report
python3 test_automation/scripts/report_to_expectations.py \\
  --report /tmp/matrix.json --scenario so_cancel_old_customer --write
```

## Structure

| Path | Purpose |
|------|---------|
| `STAGING_QA.md` | Run tiers, CI, triage |
| `ADD_SCENARIO.md` | Onboard new features |
| `staging.env.example` | Staging credentials template |
| `scenarios/` | Native + script wrapper classes |
| `bundled_scripts/` | Portable RPC tests |
| `expectations/` | Per-role PASS/FAIL/BLOCKED policy |
| `scripts/report_to_expectations.py` | Matrix JSON → expectations |
| `run_staging_smoke.sh` | T0 gate script |

See also [MIGRATION.md](MIGRATION.md).

