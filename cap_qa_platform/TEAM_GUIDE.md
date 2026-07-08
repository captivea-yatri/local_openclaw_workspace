# Team guide — CAP QA Platform

## One-line testing (NLP)

```bash
cd custom_addons/cap_qa_platform
set -a && source staging.env && set +a

python3 run_qa.py ask "run smoke so_cancel_old_customer for President"
python3 run_qa.py ask "test matrix so_cancel_old_customer all roles"
python3 run_qa.py ask "run ui so_cancel_old_customer"
python3 run_qa.py ask "run full so_cancel_old_customer President"
```

## Add a new feature (≈2–4 hours)

```bash
# 1. Scaffold from plain English
python3 run_qa.py ask "scaffold scenario my_feature that confirms invoice and checks total"

# 2. Edit cap_qa_platform/scenarios/my_feature.py (implement steps)

# 3. Register in cap_qa_platform/catalog.py

# 4. Test
python3 run_qa.py ask "run smoke my_feature for President"
```

## Backend vs UI

| Layer | Command | When |
|-------|---------|------|
| Backend only | `run_qa.py backend --scenario X` | All roles, fast |
| UI hybrid | `run_qa.py ui --scenario so_cancel_old_customer` | Browser + RPC |
| Both | `run_qa.py full --scenario X --role President` | Release gate |

## MCP (Cursor / Claude)

```bash
python3 run_qa.py mcp
```

Connect in your AI tool as stdio MCP server `cap-qa-platform`.

Tools: `list_scenarios_tool`, `run_backend_smoke`, `run_backend_matrix`, `run_ui_smoke_tool`, `ask_qa`, `scaffold_scenario_tool`.

## Test user

- **Setup:** `--user` (admin1 / yatri…) assigns roles
- **RPC/UI test:** `cap_qa_tester` / `cap_qa_test`

Separate from `test_automation` so both can coexist.
