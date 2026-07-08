---
name: project-workflow-test
description: |
  Executes the full automated functional test of the Odoo Project workflow.
  The script `test_project_workflow.py` creates a sales order, verifies
  auto‑project creation, walks through all status transitions, checks the
  invoice colour logic, timesheet blocking, late‑authorization, requirement → task
  generation, test & feedback flow, progress‑report snapshot and portal access.
run: |
  # Run the skill
  # This assumes the Odoo virtual‑env `odoo_venv` is present in the workspace.
  ./odoo_venv/bin/python test_project_workflow.py
author: Odoo Assistant
version: 1.0.0
---

## Usage
```bash
openclaw skill run project-workflow-test
```
The command will execute the script and output a JSON summary on stdout.
