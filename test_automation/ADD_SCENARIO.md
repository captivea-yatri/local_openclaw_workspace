# Add a new scenario to test_automation

Use **Path 1** for almost all new features (bundled RPC script).  
Use **Path 2** only when you need step-level role checks (like SO cancel).

---

## Path 1 — Bundled script (recommended)

### 1. Write the module RPC test

Create in your module:

```
cap_my_module/scripts/test_my_feature_rpc.py
```

Required CLI args:

```
--url --db --user --password --protocol|--rpc [--no-cleanup]
```

Exit `0` on success, `1` on failure.

### 2. Register in sync map

Edit `test_automation/sync_bundled_scripts.py`:

```python
"my_feature.py": "cap_my_module/scripts/test_my_feature_rpc.py",
```

Run:

```bash
python3 test_automation/sync_bundled_scripts.py
```

### 3. Register in catalog

Edit `test_automation/catalog.py` → `SCRIPT_ENTRIES`:

```python
ScenarioEntry(
    id="my_feature",
    kind="script",
    description="Short description",
    modules=("cap_my_module",),
    use_case="What access/workflow this validates",
    script_path=Path("my_feature.py"),
    protocol_flag="protocol",  # or "rpc"
),
```

No change to `registry.py` — scripts auto-register.

### 4. Expectations stub

```bash
cp test_automation/expectations/scripts/_template.json \
   test_automation/expectations/scripts/my_feature.json
# Edit scenario id and description
```

### 5. (Optional) Non-default auth

Edit `test_automation/script_matrix/config.py` only if RPC must run as admin:

```python
"my_feature": ScriptMatrixConfig(auth_user="admin"),
```

Default is `feature_matrix_tester` with role assigned per matrix row.

### 6. Verify

```bash
set -a && source test_automation/staging.env && set +a

# Smoke
python3 test_automation/run_test_suite.py --scenario my_feature --mode smoke --load-staging-env

# Matrix (all roles)
python3 test_automation/run_matrix.py --scenario my_feature --roles-from db \
  --load-staging-env --report-file /tmp/my_feature_matrix.json

# Generate expectations draft
python3 test_automation/scripts/report_to_expectations.py \
  --report /tmp/my_feature_matrix.json --scenario my_feature --write
```

### 7. PR

Include checklist from [PR_CHECKLIST.md](PR_CHECKLIST.md).

---

## Path 2 — Native role-matrix scenario

For flows where expectations need **specific steps** (e.g. blocked at `create_sale_order`):

1. Add `test_automation/scenarios/my_feature.py` (see `so_cancel_old_customer.py`)
2. Register in `scenarios/registry.py`
3. Add `ROLE_MATRIX_ENTRIES` in `catalog.py`
4. Add `expectations/my_feature.json` (copy `_template.json`, list `steps[]`)
5. Run `run_feature_matrix.py --scenario my_feature`

---

## Naming

| Item | Convention |
|------|------------|
| Scenario id | `snake_case`, matches catalog |
| Bundled file | `my_feature.py` |
| Module RPC test | `test_my_feature_rpc.py` |

---

## After merge

- T0 smoke runs in CI on staging deploy
- QA fills expectations from first matrix report
- Nightly `--strict` matrix once expectations complete

See [STAGING_QA.md](STAGING_QA.md).
