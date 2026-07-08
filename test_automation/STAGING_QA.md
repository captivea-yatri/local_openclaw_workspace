# Staging QA automation

Runbook for **100% staging-level QA** using `test_automation/`.

## Setup (once per machine)

```bash
cd /path/to/custom_addons
cp test_automation/staging.env.example test_automation/staging.env
# Edit staging.env — staging URL/DB only, never production
```

Load env before every run:

```bash
set -a && source test_automation/staging.env && set +a
```

Or use `--load-staging-env` on runners (reads `test_automation/staging.env`).

## Run tiers

| Tier | When | Command | ~Duration |
|------|------|---------|-----------|
| **T0 Smoke** | Every deploy / PR | `run_staging_smoke.sh` or below | 2–5 min |
| **T1 Business × roles** | Daily / after access changes | `--all --mode role --strict` | 20–30 min |
| **T2 Scripts × roles** | Nightly | `--all --mode role-scripts --strict` | 2–4 h |
| **T3 Full matrix** | Weekly | `--all --mode full --strict` | 3–5 h |

### T0 — Smoke (required gate)

```bash
./test_automation/run_staging_smoke.sh
# or:
python3 test_automation/run_test_suite.py --all --mode smoke \
  --load-staging-env --report-file test_automation/reports/smoke.json
```

**Pass criteria:** 14/14 scenarios exit 0.

### T1 — Business role matrix

```bash
python3 test_automation/run_test_suite.py --all --mode role \
  --load-staging-env --roles-from db --strict \
  --report-file test_automation/reports/role_matrix.json
```

### T2 — Script role matrix

```bash
python3 test_automation/run_test_suite.py --all --mode role-scripts \
  --load-staging-env --roles-from db --strict \
  --report-file test_automation/reports/script_matrix.json
```

### T3 — Full matrix

```bash
python3 test_automation/run_matrix.py --all --roles-from db --strict \
  --load-staging-env --report-file test_automation/reports/full_matrix.json
```

### Live Mistral (optional tier)

```bash
python3 test_automation/run_matrix.py --scenario connect_mistral_ai \
  --roles-from db --live --agent-id 2 --mistral-key "$MISTRAL_API_KEY" \
  --load-staging-env --report-file test_automation/reports/mistral.json
```

## Verdicts

| Verdict | Meaning |
|---------|---------|
| **PASS** | Role in `full_access` and flow succeeded |
| **BLOCKED_OK** | Role in `blocked` and failed at expected step with AccessError |
| **FAIL** | Wrong outcome vs expectations, or `--strict` failure |
| **REPORT** | No expectation — review and add to JSON |

## Fill expectations from a matrix run

```bash
# 1) Run matrix (no strict)
python3 test_automation/run_matrix.py --scenario so_cancel_old_customer \
  --roles-from db --load-staging-env \
  --report-file /tmp/so_cancel_matrix.json

# 2) Propose expectations
python3 test_automation/scripts/report_to_expectations.py \
  --report /tmp/so_cancel_matrix.json --scenario so_cancel_old_customer --dry-run

# 3) Write after review
python3 test_automation/scripts/report_to_expectations.py \
  --report /tmp/so_cancel_matrix.json --scenario so_cancel_old_customer --write

# 4) Validate coverage (with role list from report)
python3 test_automation/scripts/validate_expectations.py \
  --roles-file /tmp/so_cancel_matrix.json --scenario so_cancel_old_customer --strict
```

Repeat for each scenario until `--strict` passes with 0 FAIL.

## Safety rules

1. **Staging DB only** — runners refuse URLs/DBs that look like production (see `staging.py`).
2. **`admin1`** — setup/cleanup only; never strip roles without backup.
3. **`feature_matrix_tester`** — all role RPC tests (except `connect_mistral_ai` script uses admin).
4. Default **cleanup on**; use `--no-cleanup` only when debugging.
5. After changing `access_rights_management` roles → update expectations in the **same PR**.

## CI example (GitLab)

```yaml
staging-qa-smoke:
  stage: test
  script:
    - cd custom_addons
    - set -a && source test_automation/staging.env && set +a
    - python3 test_automation/run_test_suite.py --all --mode smoke
      --load-staging-env --report-file test_automation/reports/smoke.json
  artifacts:
    paths: [custom_addons/test_automation/reports/smoke.json]
  rules:
    - if: $CI_PIPELINE_SOURCE == "schedule"
      when: never
    - when: on_success

staging-qa-matrix-nightly:
  stage: test
  rules:
    - if: $CI_PIPELINE_SOURCE == "schedule"
  script:
    - cd custom_addons
    - set -a && source test_automation/staging.env && set +a
    - python3 test_automation/run_matrix.py --all --roles-from db --strict
      --load-staging-env --report-file test_automation/reports/full_matrix.json
  artifacts:
    paths: [custom_addons/test_automation/reports/full_matrix.json]
  timeout: 6h
```

Enable nightly matrix only after expectations are complete.

## Triage

| Symptom | Action |
|---------|--------|
| Smoke FAIL on business scenario | Run single scenario with `--roles "Team Manager" --no-cleanup`; check Odoo server log |
| Matrix REPORT for all roles | Fill expectations via `report_to_expectations.py` |
| AccessError unexpected | Fix role in Odoo or update `blocked` in expectations |
| admin1 cannot read users | Restore from backup / Odoo shell; restart Odoo |
| Script timeout | Increase `ODOO_SCRIPT_TIMEOUT` in staging.env |

## Docs

- [ADD_SCENARIO.md](ADD_SCENARIO.md) — add a new feature to automation
- [PR_CHECKLIST.md](PR_CHECKLIST.md) — PR checklist
- `--list` — full catalog and use cases
