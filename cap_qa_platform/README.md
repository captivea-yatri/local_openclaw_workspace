# CAP QA Platform

**Standalone** full-stack QA for Captivea custom Odoo modules.

- Does **not** modify `test_automation/` or any existing module code
- **Backend (RPC):** role-matrix + bundled scripts from custom modules
- **Frontend (UI):** Playwright hybrid flows (RPC setup + browser checks)
- **NLP:** `run_qa.py ask "..."` for teammates
- **MCP:** AI assistant tools (`run_qa.py mcp`)

Test user: **`cap_qa_tester`** / **`cap_qa_test`** (separate from `feature_matrix_tester`)

---

## Setup

```bash
cd custom_addons/cap_qa_platform
pip install -r requirements.txt
playwright install chromium
cp staging.env.example staging.env
# edit staging.env
set -a && source staging.env && set +a
```

---

## Quick commands

```bash
# List all scenarios (14 custom workflows)
python3 run_qa.py list

# Natural language (for teammates)
python3 run_qa.py ask "run smoke so_cancel_old_customer for President"
python3 run_qa.py ask "test matrix so_cancel_old_customer all roles"
python3 run_qa.py ask "run ui so_cancel_old_customer"

# Explicit backend
python3 run_qa.py backend --scenario so_cancel_old_customer --roles President --load-staging-env
python3 run_qa.py backend --scenario so_cancel_old_customer --roles-from db --load-staging-env

# UI + backend together
python3 run_qa.py full --scenario so_cancel_old_customer --role President --load-staging-env

# Add new scenario stub
python3 run_qa.py scaffold my_feature "Confirm SO and check partner status"

# MCP server for Cursor / Claude
python3 run_qa.py mcp
```

---

## Architecture

```
cap_qa_platform/
  run_qa.py                 # Main CLI
  cap_qa_platform/
    catalog.py              # All scenarios + custom modules
    backend/runner.py       # RPC matrix engine
    ui/                     # Playwright pages + flows
    mcp/server.py           # MCP tools for AI
    nlp/prompt_cli.py       # Natural language parser
    scenarios/              # Native role-matrix flows
    expectations/           # full_access / blocked per role
```

### Scenario types

| Kind | Examples | Backend | UI |
|------|----------|---------|-----|
| role_matrix | so_cancel_old_customer, QIL ask review | Native Python | so_cancel (hybrid) |
| script | ksc_auto_invoice, inter_company, AI connectors | Subprocess to module/bundled scripts | Planned |

Script scenarios invoke existing RPC tests under `custom_addons/*/scripts/` or read-only `test_automation/bundled_scripts/` — **no files created there**.

---

## Teammate workflow (new feature)

1. **Prompt:** `python3 run_qa.py ask "scaffold scenario my_feature that does X"`
2. **Implement** generated `scenarios/my_feature.py`
3. **Register** in `catalog.py`
4. **Test:** `python3 run_qa.py ask "run smoke my_feature for President"`
5. **Matrix:** `python3 run_qa.py backend --scenario my_feature --roles-from db`
6. Update `expectations/my_feature.json`

---

## MCP tools (for AI)

| Tool | Purpose |
|------|---------|
| `list_scenarios_tool` | Catalog |
| `run_backend_smoke` | One role RPC |
| `run_backend_matrix` | All roles |
| `run_ui_smoke_tool` | Hybrid UI |
| `ask_qa` | Natural language |
| `scaffold_scenario_tool` | New scenario stub |

---

## Safety

- `staging.py` blocks suspected production URLs (same pattern as test_automation)
- Use `--allow-production` only when intentional
- Setup user needs `base.group_system` if `rpc_helper` blocks `res.users` RPC

---

## vs test_automation

| | test_automation | cap_qa_platform |
|--|-----------------|-----------------|
| Location | existing folder | **new** standalone |
| Test user | feature_matrix_tester | cap_qa_tester |
| UI tests | No | **Yes** (Playwright) |
| NLP / MCP | No | **Yes** |
| Edits existing files | — | **None** |
