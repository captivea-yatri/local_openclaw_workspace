# Migrating test_automation

Copy the entire `test_automation/` folder to another machine or Odoo addons path. It is self-contained: scenarios, bundled RPC scripts, expectations, and runners.

## Package layout

```
test_automation/
  bundled_scripts/     # Portable copies of module RPC tests (11 files)
  scenarios/           # All 14 scenario classes (3 native + 11 script wrappers)
  expectations/        # Per-role expectation JSON
  rpc/                 # Odoo JSON-RPC client + role manager
  catalog.py           # Scenario metadata
  run_matrix.py          # Unified matrix runner (recommended)
  run_test_suite.py      # Smoke / role / full modes
  sync_bundled_scripts.py  # Re-copy scripts from module sources
```

## Requirements

- Python 3.10+
- Stdlib only (no pip dependencies)
- Odoo instance with the modules listed in `catalog.py` installed
- `base_user_role` for role-matrix tests
- `access_rights_management/data/roles_data.xml` for `--roles-from xml` (optional if using `--roles-from db`)

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `CUSTOM_ADDONS_ROOT` | Parent of `test_automation/` | Odoo addons root (cwd for subprocess scripts) |
| `ODOO_URL` | `http://localhost:8069` | Target Odoo URL |
| `ODOO_DB` | `odoo` | Database name |
| `ODOO_USER` / `ODOO_PASSWORD` | `admin` / `admin` | Admin credentials |
| `ODOO_RPC` | `jsonrpc` | `jsonrpc` or `xmlrpc` |

## Quick start

From the addons root (parent of `test_automation/`):

```bash
# List scenarios
python3 test_automation/run_test_suite.py --list

# Smoke: each scenario once
python3 test_automation/run_test_suite.py --all --mode smoke \\
  --url http://localhost:8069 --db mydb --user admin --password admin

# One scenario × all roles
python3 test_automation/run_matrix.py --scenario so_cancel_old_customer \\
  --roles-from db --url ... --db ... --user ... --password ...

# All 14 scenarios × all roles (very long)
python3 test_automation/run_matrix.py --all --roles-from db \\
  --url ... --db ... --user ... --password ...
```

## Updating bundled scripts

When module RPC tests change in `cap_*` / `ksc_*` folders, refresh copies:

```bash
python3 test_automation/sync_bundled_scripts.py
```

## Migrating to another repo

1. Copy `test_automation/` into the target addons directory.
2. Set `CUSTOM_ADDONS_ROOT` if the folder is not a direct child of addons root.
3. Ensure required Odoo modules are installed on the target database.
4. Run `--list` then `--mode smoke` to validate connectivity.

## OpenClaw skill

Team documentation: `skills/odoo-rpc-test-automation/SKILL.md`
