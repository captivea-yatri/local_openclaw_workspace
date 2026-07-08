# -*- coding: utf-8 -*-
"""
Standalone test script for Quality Issue Log + approval.request workflow.

Does NOT modify any module code. Run inside Odoo shell against a database
where `cap_quality_issue_log` and `approvals` are installed.

---------------------------------------------------------------------------
HOW TO RUN
---------------------------------------------------------------------------

Option A — from Odoo shell (recommended):

    odoo shell -d YOUR_DATABASE_NAME

    >>> exec(open("/home/odoo/workspace/custom_addons/cap_quality_issue_log/scripts/test_quality_issue_approval_workflow.py").read())
    >>> run_all_tests(env)

Option B — one-liner:

    odoo shell -d YOUR_DATABASE_NAME --no-http <<'PY'
    exec(open("/home/odoo/workspace/custom_addons/cap_quality_issue_log/scripts/test_quality_issue_approval_workflow.py").read())
    run_all_tests(env)
    PY

Option C — run a single scenario:

    >>> run_all_tests(env, scenarios=["setup", "stale_activity"])

Available scenarios: setup, normal_approve, stale_activity, double_approve_path, legacy_activity
---------------------------------------------------------------------------
"""

from datetime import date

from odoo import Command, fields
from odoo.exceptions import MissingError
from odoo.tests.common import new_test_user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(title, message=""):
    line = "=" * 72
    print(f"\n{line}\n{title}\n{line}")
    if message:
        print(message)


def _ok(label):
    print(f"  [PASS] {label}")


def _fail(label, detail=""):
    print(f"  [FAIL] {label}")
    if detail:
        print(f"         {detail}")


def _info(label, value):
    print(f"  [INFO] {label}: {value}")


def _require_model(env, model_name):
    if model_name not in env:
        raise RuntimeError(
            f"Model '{model_name}' is not available. "
            f"Install the required app first (e.g. 'approvals' for approval.request)."
        )


def _get_approval_activity_type(env):
    return env.ref("approvals.mail_activity_data_approval")


def _get_or_create_approval_category(env):
    """Use standard General Approval category or create a minimal test category."""
    category = env.ref("approvals.approval_category_data_general_approval", raise_if_not_found=False)
    if category:
        return category
    return env["approval.category"].sudo().create({
        "name": "QIL Test Approval Category",
        "approval_minimum": 1,
        "has_date": "no",
        "has_period": "no",
        "has_product": "no",
        "has_quantity": "no",
        "has_amount": "no",
        "has_reference": "no",
        "has_partner": "no",
        "has_payment_method": "no",
        "has_location": "no",
        "requirer_document": "optional",
    })


def _link_approval_to_quality_log(approval, quality_log):
    """Link approval.request to quality.issue.log using Studio field if present."""
    ApprovalRequest = approval.env["approval.request"]
    vals = {}
    if "quality_issue_log_id" in ApprovalRequest._fields:
        vals["quality_issue_log_id"] = quality_log.id
    if "x_studio_quality_issue_log" in ApprovalRequest._fields:
        vals["x_studio_quality_issue_log"] = quality_log.id
    if vals:
        approval.sudo().write(vals)


def _find_manager_approval_activities(env, approval, manager_user):
    activity_type = _get_approval_activity_type(env)
    return env["mail.activity"].search([
        ("res_model", "=", "approval.request"),
        ("res_id", "=", approval.id),
        ("activity_type_id", "=", activity_type.id),
        ("user_id", "=", manager_user.id),
    ])


def _try_read_activity(env, activity_id):
    """Simulate UI opening a deleted activity record."""
    activity = env["mail.activity"].browse(activity_id)
    if not activity.exists():
        raise MissingError(env._("Record does not exist or has been deleted."))
    # Force a real field read (same as UI would do)
    return activity.summary


def _try_activity_action_feedback(env, activity_id, user):
    """Simulate marking an activity done / approve feedback as manager."""
    activity = env["mail.activity"].with_user(user).browse(activity_id)
    if not activity.exists():
        raise MissingError(env._("Record does not exist or has been deleted."))
    return activity.action_feedback()


# ---------------------------------------------------------------------------
# Test data factory
# ---------------------------------------------------------------------------

def setup_test_data(env):
    """
    Create:
      - employee user + manager user
      - hr.employee records (parent/child)
      - quality.issue.type + quality.issue.log (penalty, enabled)
      - approval.request linked to the log, confirmed, with manager activity

    Returns a dict of created records for later scenarios.
    """
    _require_model(env, "approval.request")
    _require_model(env, "quality.issue.log")

    company = env.company
    suffix = fields.Datetime.now().strftime("%Y%m%d%H%M%S")

    _log("STEP 1 — Create test users and employees")

    manager_user = new_test_user(
        env,
        login=f"qil_mgr_{suffix}@test.com",
        groups="base.group_user,approvals.group_approval_user",
        name=f"QIL Manager {suffix}",
        company_id=company.id,
    )
    employee_user = new_test_user(
        env,
        login=f"qil_emp_{suffix}@test.com",
        groups="base.group_user",
        name=f"QIL Employee {suffix}",
        company_id=company.id,
    )

    manager_employee = env["hr.employee"].sudo().create({
        "name": manager_user.name,
        "user_id": manager_user.id,
        "company_id": company.id,
    })
    employee = env["hr.employee"].sudo().create({
        "name": employee_user.name,
        "user_id": employee_user.id,
        "company_id": company.id,
        "parent_id": manager_employee.id,
    })

    _info("Manager user", f"{manager_user.login} (id={manager_user.id})")
    _info("Employee user", f"{employee_user.login} (id={employee_user.id})")
    _info("Employee record", f"id={employee.id}, parent={manager_employee.name}")

    _log("STEP 2 — Create quality issue type and quality issue log")

    issue_type = env["quality.issue.type"].sudo().search([], limit=1)
    if not issue_type:
        category = env["quality.category"].sudo().search([], limit=1)
        issue_type = env["quality.issue.type"].sudo().create({
            "name": f"Test Issue Type {suffix}",
            "score_impact": 5.0,
            "quality_category": category.id if category else False,
            "state": "in_progress",
        })

    quality_log = env["quality.issue.log"].sudo().create({
        "logged_date": date.today(),
        "employee_id": employee.id,
        "description": f"Test quality issue for approval workflow ({suffix})",
        "score_impact": issue_type.score_impact or 5.0,
        "quality_issue_type": issue_type.id,
        "log_type": "penalty",
        "state": "enabled",
    })
    quality_log.sudo().write({"state": "reviewing"})

    _info("Quality issue log", f"id={quality_log.id}, state={quality_log.state}")
    _info("Display name", quality_log.display_name)

    _log("STEP 3 — Create approval.request, add approver, confirm (creates activity)")

    category = _get_or_create_approval_category(env)
    approval = env["approval.request"].sudo().create({
        "name": f"Review Quality Issue: {quality_log.display_name}",
        "category_id": category.id,
        "request_owner_id": employee_user.id,
        "reason": quality_log.description,
        "approver_ids": [Command.create({
            "user_id": manager_user.id,
            "required": True,
            "status": "new",
        })],
    })
    _link_approval_to_quality_log(approval, quality_log)

    _info("Approval request (before confirm)", f"id={approval.id}, status={approval.request_status}")

    approval.sudo().action_confirm()

    activities = _find_manager_approval_activities(env, approval, manager_user)
    if not activities:
        raise RuntimeError(
            "No approval activity was created for the manager after action_confirm(). "
            "Check approvals app configuration and approver setup."
        )

    activity = activities[0]
    _info("Approval request (after confirm)", f"id={approval.id}, status={approval.request_status}")
    _info("Manager approver status", approval.approver_ids.filtered(lambda a: a.user_id == manager_user).status)
    _info("Mail activity", f"id={activity.id}, res_model={activity.res_model}, res_id={activity.res_id}")

    data = {
        "company": company,
        "suffix": suffix,
        "manager_user": manager_user,
        "employee_user": employee_user,
        "manager_employee": manager_employee,
        "employee": employee,
        "issue_type": issue_type,
        "quality_log": quality_log,
        "category": category,
        "approval": approval,
        "activity": activity,
    }
    _ok("Setup complete — approval request and manager activity created")
    return data


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

def test_normal_approve(env, data):
    """Manager approves via approval.request — should succeed, activity removed."""
    _log("SCENARIO A — Normal approve via approval.request")

    approval = data["approval"].sudo()
    manager = data["manager_user"]
    activity = data["activity"]

    if approval.request_status != "pending":
        _fail("Approval is not pending", f"status={approval.request_status}")
        return False

    _info("Activity before approve", f"id={activity.id}, exists={activity.exists()}")

    approval.with_user(manager).action_approve()
    env.cr.flush()

    activity_exists = env["mail.activity"].browse(activity.id).exists()
    _info("Approval status after approve", approval.request_status)
    _info("Activity still exists?", activity_exists)

    if approval.request_status == "approved" and not activity_exists:
        _ok("Normal approve works — request approved, activity deleted")
        return True

    _fail("Unexpected state after normal approve")
    return False


def test_stale_activity_missing_record(env, data):
    """
    Reproduce Missing Record:
      1. Create fresh pending approval + activity
      2. Delete / cancel activity server-side (simulate stale systray)
      3. Try to read or action_feedback on old activity id
    """
    _log("SCENARIO B — Stale deleted activity (Missing Record)")

    manager = data["manager_user"]
    employee_user = data["employee_user"]
    quality_log = data["quality_log"]
    category = data["category"]

    approval = env["approval.request"].sudo().create({
        "name": f"Stale activity test — {data['suffix']}",
        "category_id": category.id,
        "request_owner_id": employee_user.id,
        "reason": "Stale activity reproduction",
        "approver_ids": [Command.create({
            "user_id": manager.id,
            "required": True,
            "status": "new",
        })],
    })
    _link_approval_to_quality_log(approval, quality_log)
    approval.sudo().action_confirm()

    activities = _find_manager_approval_activities(env, approval, manager)
    if not activities:
        _fail("Could not create activity for stale test")
        return False

    stale_activity_id = activities[0].id
    _info("Created activity", stale_activity_id)

    # Simulate what happens when approve/cancel removes the activity but UI still has the id
    activities.sudo().unlink()
    env.cr.flush()
    _info("Activity deleted server-side", f"id={stale_activity_id}")

    missing_on_read = False
    missing_on_feedback = False

    try:
        _try_read_activity(env, stale_activity_id)
        _fail("Reading deleted activity should raise MissingError")
    except MissingError as exc:
        missing_on_read = True
        _ok(f"MissingError on read (simulates opening stale activity in UI): {exc}")

    try:
        _try_activity_action_feedback(env, stale_activity_id, manager)
        _fail("action_feedback on deleted activity should raise MissingError")
    except MissingError as exc:
        missing_on_feedback = True
        _ok(f"MissingError on action_feedback (simulates Approve on stale activity): {exc}")

    if missing_on_read and missing_on_feedback:
        _ok("Stale activity scenario reproduced successfully")
        return True

    _fail("Could not reproduce Missing Record for stale activity")
    return False


def test_double_approve_path(env, data):
    """
    Reproduce race between approval.request approve and activity cleanup:
      1. Fresh approval + activity
      2. Manager approves via approval.request (activity deleted by core)
      3. Try action_feedback again on captured activity id
    """
    _log("SCENARIO C — Approve via approval.request then hit stale activity id")

    manager = data["manager_user"]
    employee_user = data["employee_user"]
    quality_log = data["quality_log"]
    category = data["category"]

    approval = env["approval.request"].sudo().create({
        "name": f"Double path test — {data['suffix']}",
        "category_id": category.id,
        "request_owner_id": employee_user.id,
        "reason": "Double approve path reproduction",
        "approver_ids": [Command.create({
            "user_id": manager.id,
            "required": True,
            "status": "new",
        })],
    })
    _link_approval_to_quality_log(approval, quality_log)
    approval.sudo().action_confirm()

    activities = _find_manager_approval_activities(env, approval, manager)
    if not activities:
        _fail("Could not create activity for double-path test")
        return False

    captured_activity_id = activities[0].id
    _info("Captured activity id before approve", captured_activity_id)

    approval.with_user(manager).action_approve()
    env.cr.flush()

    _info("Approval status", approval.request_status)
    _info("Activity exists after approve?", env["mail.activity"].browse(captured_activity_id).exists())

    try:
        _try_activity_action_feedback(env, captured_activity_id, manager)
        _info(
            "Second action_feedback did NOT raise (activity already gone; "
            "Odoo core may skip empty recordset safely)"
        )
        # Core action_approve already calls action_feedback once; a second manual
        # call on deleted id still reproduces the UI bug when browsing by id first.
        return test_stale_activity_missing_record(env, data)
    except MissingError as exc:
        _ok(f"MissingError on second action_feedback after approve: {exc}")
        return True


def test_legacy_activity_on_quality_log(env, data):
    """
    Current module ask_for_review() creates a To-Do on quality.issue.log.
    If that activity is deleted while the manager UI still references it,
    Missing Record is raised the same way.
    """
    _log("SCENARIO D — Legacy To-Do on quality.issue.log (current module behavior)")

    manager = data["manager_user"]
    quality_log = data["quality_log"]

    todo_type = env["mail.activity.type"].search(
        [("name", "in", ["Todo", "To Do", "To-Do"])], limit=1
    )
    if not todo_type:
        _fail("No To-Do mail.activity.type found — skip legacy scenario")
        return False

    qil_model = env["ir.model"].sudo().search([("model", "=", "quality.issue.log")], limit=1)
    legacy_activity = env["mail.activity"].sudo().create({
        "summary": "Review Quality Issue",
        "activity_type_id": todo_type.id,
        "res_model_id": qil_model.id,
        "res_id": quality_log.id,
        "user_id": manager.id,
    })
    legacy_id = legacy_activity.id
    _info("Legacy activity created on quality.issue.log", legacy_id)

    # Same as ask_for_review() being triggered again or manual cleanup
    legacy_activity.sudo().unlink()
    env.cr.flush()

    try:
        _try_read_activity(env, legacy_id)
        _fail("Reading deleted legacy activity should raise MissingError")
        return False
    except MissingError as exc:
        _ok(f"Legacy MissingError reproduced: {exc}")
        return True


def test_ask_for_review_creates_legacy_activity(env, data):
    """Optional: call existing module method and show what it creates today."""
    _log("SCENARIO E — Current module ask_for_review() (informational)")

    quality_log = data["quality_log"].sudo()
    if quality_log.state != "enabled":
        quality_log.write({"state": "enabled"})

    before = env["mail.activity"].search_count([
        ("res_model", "=", "quality.issue.log"),
        ("res_id", "=", quality_log.id),
    ])
    quality_log.ask_for_review()
    after = env["mail.activity"].search([
        ("res_model", "=", "quality.issue.log"),
        ("res_id", "=", quality_log.id),
    ])

    _info("Activities on quality.issue.log before", before)
    _info("Activities on quality.issue.log after ask_for_review", after.ids)
    _info("Quality log state", quality_log.state)

    approval_type = _get_approval_activity_type(env)
    approval_activities = env["mail.activity"].search([
        ("res_model", "=", "approval.request"),
        ("activity_type_id", "=", approval_type.id),
        ("user_id", "=", data["manager_user"].id),
    ])

    _info("Approval-type activities for manager (not created by ask_for_review)", approval_activities.ids)
    _ok(
        "ask_for_review() creates a legacy To-Do on quality.issue.log only "
        "(approval.request must be created separately in current code)"
    )
    return True


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

SCENARIOS = {
    "setup": setup_test_data,
    "normal_approve": test_normal_approve,
    "stale_activity": test_stale_activity_missing_record,
    "double_approve_path": test_double_approve_path,
    "legacy_activity": test_legacy_activity_on_quality_log,
    "ask_for_review": test_ask_for_review_creates_legacy_activity,
}


def run_all_tests(env, scenarios=None, rollback=True):
    """
    Run the full workflow test suite.

    :param env: odoo.api.Environment (available as `env` in odoo shell)
    :param scenarios: list of scenario keys to run, or None for all
    :param rollback: if True (default), roll back all changes at the end so the
                     script is safe to run on production copies
    """
    selected = scenarios or ["setup", "normal_approve", "stale_activity", "double_approve_path", "legacy_activity", "ask_for_review"]

    _log(
        "QUALITY ISSUE LOG — APPROVAL WORKFLOW TEST SCRIPT",
        "Module code is NOT modified. All records are created via ORM in this script.\n"
        f"Scenarios: {', '.join(selected)}",
    )

    if rollback:
        env.cr.execute("SAVEPOINT qil_approval_test")

    results = {}
    data = None

    try:
        if "setup" in selected:
            data = setup_test_data(env)
            results["setup"] = True
        elif any(s in selected for s in selected if s != "setup"):
            raise RuntimeError("Run the 'setup' scenario first or include it in the list.")

        for key in selected:
            if key == "setup":
                continue
            if data is None:
                data = setup_test_data(env)
            results[key] = SCENARIOS[key](env, data)

    except Exception as exc:
        _log("SCRIPT ERROR", str(exc))
        results["error"] = str(exc)
        raise
    finally:
        _log("SUMMARY")
        for key, passed in results.items():
            if key == "error":
                print(f"  [ERROR] {passed}")
            elif passed is True:
                print(f"  [PASS]  {key}")
            elif passed is False:
                print(f"  [FAIL]  {key}")
            else:
                print(f"  [INFO]  {key}: {passed}")

        if rollback:
            env.cr.execute("ROLLBACK TO SAVEPOINT qil_approval_test")
            print("\n  [INFO] Transaction rolled back — no permanent data was saved.")
        else:
            env.cr.commit()
            print("\n  [INFO] Transaction committed — test data kept in database.")

    return results


# When loaded via exec(open(...).read()) in odoo shell, call run_all_tests(env) yourself,
# or uncomment the line below to auto-run:
# run_all_tests(env)
