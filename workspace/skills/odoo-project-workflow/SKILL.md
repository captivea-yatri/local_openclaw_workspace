---
name: odoo-project-workflow
description: Automates Odoo project management workflow, including status navigation, project overview, invoice blocking rules, portal access provisioning, progress report generation, production review, requirement gathering, test session handling, feedback processing, project planning, and access‑request integration with GitHub & Teams. Use when you need a deterministic, repeatable script‑driven automation of the internal ERP (Odoo) project lifecycle.
---

# Odoo Project Workflow Automation Skill

This skill provides a scripted, step‑by‑step automation of the comprehensive Odoo project management process described in the user‑provided documentation.

## When to Use
- Set up a new Odoo project from the **Projects** module.
- Apply status changes and colour‑code rules based on invoice due dates.
- Grant portal access to customers and share editable project links.
- Generate and send a **Project Progress Report** with calculated global/validation metrics.
- Run **Production Review**, **Requirement gathering**, **Test Session**, **Feedback**, and **Project Planning** actions.
- Automate **Access Request** approvals that add users to GitHub repositories and MS‑Teams groups.

## How It Works
The skill bundles a series of Bash/Python helper scripts (see `scripts/` directory) that perform Odoo‑specific API calls via `odoo-client` (or `curl` with XML‑RPC) and orchestrate the required Odoo UI actions.

### Main Entry Point
Run the master script:
```bash
./run_odoo_project_workflow.sh "<project_name>" "<customer_name>" "<phase>"
```
The script will:
1. Create or locate the project.
2. Set the appropriate **Status** and configure **Number of days authorized in late**.
3. Configure **Portal Access** and share the project.
4. Refresh domain calculations.
5. Generate a progress report for the supplied phase.
6. Optionally trigger production review, test sessions, feedback collection, and planning based on flags.
7. If an access request is pending, approve it and add the user to GitHub & Teams.

### Flags
- `--no‑report` – skip progress report generation.
- `--review` – run production review workflow.
- `--test` – initialise a test session.
- `--feedback` – open feedback creation for the project.
- `--plan` – update project planning based on weekly capacity.
- `--access‑request <user>` – approve a pending access request for `<user>`.

## Extensibility
- Add new phases by editing `scripts/phase_helpers.py`.
- Extend GitHub/Teams integration in `scripts/access_integration.sh`.
- Adjust colour thresholds in `scripts/invoice_blocking.py`.

## Resources
- `scripts/` – executable helpers.
- `references/` – Odoo API endpoints and XML‑RPC payload examples (optional, load only when needed).

**Note:** This skill assumes the Odoo server credentials are available in environment variables `ODOO_URL`, `ODOO_DB`, `ODOO_USER`, and `ODOO_PASSWORD`.
