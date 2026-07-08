# PR checklist — test_automation

Copy into your PR description when the change adds or modifies a testable workflow.

## test_automation

- [ ] RPC test exists (`cap_*/scripts/test_*_rpc.py` or native scenario)
- [ ] `test_automation/catalog.py` updated (`SCRIPT_ENTRIES` or `ROLE_MATRIX_ENTRIES`)
- [ ] `test_automation/bundled_scripts/` updated OR `sync_bundled_scripts.py` + sync run
- [ ] `test_automation/expectations/` stub added or updated
- [ ] Smoke passes:
  ```bash
  python3 test_automation/run_test_suite.py --scenario <id> --mode smoke --load-staging-env
  ```
- [ ] If access rights changed: expectations updated (`report_to_expectations.py`)
- [ ] `--list` shows new scenario with description and use case

## Not required in same PR (but follow-up)

- [ ] Full matrix run on staging + expectations `--write`
- [ ] `--strict` matrix green on staging

See [ADD_SCENARIO.md](ADD_SCENARIO.md) and [STAGING_QA.md](STAGING_QA.md).
