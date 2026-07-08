-- Read-only SQL helpers for tracing mail.activity Missing Record errors
-- on cap_quality_issue_log + approval.request production systems.
--
-- Replace placeholders before running:
--   :activity_id  — from error e.g. 1743636
--   :user_id      — from error e.g. 42

-- ---------------------------------------------------------------------------
-- 1) Confirm whether the activity still exists
-- ---------------------------------------------------------------------------
SELECT id, res_model, res_id, user_id, summary, activity_type_id,
       date_deadline, create_date, write_date, active
FROM mail_activity
WHERE id = :activity_id;
-- Empty result = activity was deleted → matches "Missing Record" error


-- ---------------------------------------------------------------------------
-- 2) Open activities for affected user (current risky state)
-- ---------------------------------------------------------------------------
SELECT ma.id, ma.res_model, ma.res_id, ma.summary, ma.date_deadline, ma.create_date
FROM mail_activity ma
WHERE ma.user_id = :user_id
  AND ma.res_model IN ('quality.issue.log', 'approval.request')
ORDER BY ma.date_deadline;


-- ---------------------------------------------------------------------------
-- 3) Quality logs stuck in 'reviewing' for this manager
-- ---------------------------------------------------------------------------
SELECT q.id, q.state, q.log_type, q.write_date, q.create_date,
       e.name AS employee, m.name AS manager
FROM quality_issue_log q
JOIN hr_employee e ON e.id = q.employee_id
LEFT JOIN hr_employee m ON m.id = e.parent_id
WHERE m.user_id = :user_id
  AND q.state = 'reviewing'
ORDER BY q.write_date DESC;


-- ---------------------------------------------------------------------------
-- 4) Linked approval requests (Studio field — adjust column name if different)
-- ---------------------------------------------------------------------------
-- Check column exists first:
-- SELECT column_name FROM information_schema.columns
-- WHERE table_name = 'approval_request' AND column_name LIKE '%quality%';

SELECT ar.id, ar.name, ar.request_status, ar.create_date, ar.write_date,
       ar.x_studio_quality_issue_log AS quality_log_id
FROM approval_request ar
WHERE ar.x_studio_quality_issue_log IN (
    SELECT q.id
    FROM quality_issue_log q
    JOIN hr_employee e ON e.id = q.employee_id
    JOIN hr_employee m ON m.id = e.parent_id
    WHERE m.user_id = :user_id AND q.state = 'reviewing'
);


-- ---------------------------------------------------------------------------
-- 5) Mismatch: approval finished but QIL still reviewing
-- ---------------------------------------------------------------------------
SELECT q.id AS quality_log_id, q.state AS qil_state,
       ar.id AS approval_id, ar.request_status
FROM quality_issue_log q
JOIN approval_request ar ON ar.x_studio_quality_issue_log = q.id
JOIN hr_employee e ON e.id = q.employee_id
JOIN hr_employee m ON m.id = e.parent_id
WHERE m.user_id = :user_id
  AND q.state = 'reviewing'
  AND ar.request_status IN ('approved', 'refused', 'cancel');


-- ---------------------------------------------------------------------------
-- 6) Pending approval with NO open activity (deleted activity scenario)
-- ---------------------------------------------------------------------------
SELECT ar.id AS approval_id, ar.request_status, aa.id AS approver_line_id, aa.status AS approver_status
FROM approval_approver aa
JOIN approval_request ar ON ar.id = aa.request_id
WHERE aa.user_id = :user_id
  AND aa.status IN ('pending', 'waiting')
  AND NOT EXISTS (
      SELECT 1 FROM mail_activity ma
      WHERE ma.res_model = 'approval.request'
        AND ma.res_id = ar.id
        AND ma.user_id = :user_id
  );


-- ---------------------------------------------------------------------------
-- 7) Legacy review activities on quality.issue.log
-- ---------------------------------------------------------------------------
SELECT ma.id, ma.res_id AS quality_log_id, ma.summary, ma.create_date, q.state
FROM mail_activity ma
JOIN quality_issue_log q ON q.id = ma.res_id
WHERE ma.user_id = :user_id
  AND ma.res_model = 'quality.issue.log'
  AND ma.summary = 'Review Quality Issue';


-- ---------------------------------------------------------------------------
-- 8) ir.logging (only if log_db enabled in odoo.conf)
-- ---------------------------------------------------------------------------
SELECT id, create_date, level, name, path, line, func,
       LEFT(message, 500) AS message_preview
FROM ir_logging
WHERE create_date >= NOW() - INTERVAL '14 days'
  AND (
      message ILIKE '%does not exist%'
      OR message ILIKE '%mail.activity%'
      OR message ILIKE '%Missing%'
  )
  AND (message ILIKE '%' || :activity_id || '%' OR message ILIKE '%' || :user_id || '%')
ORDER BY create_date DESC
LIMIT 50;
