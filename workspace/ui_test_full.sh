#!/usr/bin/env bash
# Full UI test for Odoo v19 using OpenClaw browser tool.
# Logs in with the Marketing Manager user and validates menu visibility,
# hidden module exposure, direct URL bypasses, and basic navigation.

set -euo pipefail

BASE_URL="https://staging-odoo19-captivea.odoo.com"
LOGIN_URL="${BASE_URL}/web/login"
USER="princy.randimbimanana@captivea.com"
PASS="c5749279cc522fd159d71ed628162491237be7c6"
TAB_LABEL="odoo_ui_test"
REPORT="ui_test_report.json"

# Initialize empty JSON array
echo "[]" > "$REPORT"

run_cmd(){
  local desc="$1"; shift
  echo "[${desc}]" >&2
  openclaw browser "$@"
  local rc=$?
  if [ $rc -ne 0 ]; then
    echo "{\"error\": \"${desc} failed with rc $rc\"}" >&2
    exit $rc
  fi
}

# Helper to append a result object to the JSON report
append_result(){
  local module="$1" expected="$2" found="$3" status="$4"
  # Use jq if available, otherwise manual string concat
  if command -v jq >/dev/null 2>&1; then
    jq ". += [{\"module\": \"$module\", \"expected\": $expected, \"found\": $found, \"status\": \"$status\"}]" "$REPORT" > "$REPORT.tmp" && mv "$REPORT.tmp" "$REPORT"
  else
    # Manual JSON handling – very simple (no commas handling for first element)
    if [ "$(cat $REPORT)" = "[]" ]; then
      echo "[{\"module\": \"$module\", \"expected\": $expected, \"found\": $found, \"status\": \"$status\"}]" > $REPORT
    else
      # Strip trailing ] and add comma + new object + ]
      sed -i '$ s/\]$//' $REPORT
      echo ", {\"module\": \"$module\", \"expected\": $expected, \"found\": $found, \"status\": \"$status\"}]" >> $REPORT
    fi
  fi
}

# 1. Open login page
run_cmd "Open login page" open "$LOGIN_URL" --label "$TAB_LABEL"

# 2. Wait for login form (input fields)
run_cmd "Wait for login form" wait "input[name='login']"

# 3. Fill email and submit
run_cmd "Fill email" type "input[name='login']" "$USER" --submit

# 4. Fill password and submit
run_cmd "Fill password" type "input[name='password']" "$PASS" --submit

# 5. Wait for dashboard – look for the word "Dashboard" in the page
run_cmd "Wait for dashboard" wait "Dashboard" --timeout 15000

# Helper to test visibility of a menu entry (text should appear on the page)
# Parameters: module_name expected_presence(true/false)
check_visibility(){
  local module="$1" expect="$2"
  if openclaw browser wait --text "$module" --timeout 5000; then
    found=true
  else
    found=false
  fi
  if [ "$found" = "$expect" ]; then
    status="PASS"
  else
    status="FAIL"
  fi
  # expected and found need to be JSON booleans (no quotes)
  append_result "$module" $expect $found "$status"
}

# Expected visible modules for Marketing Manager
check_visibility "CRM" true
check_visibility "Contacts" true
check_visibility "Helpdesk" true
check_visibility "Website" true
check_visibility "Employees" true
check_visibility "Attendance" true

# Modules that must NOT be visible
check_visibility "Purchase" false
check_visibility "Recruitment" false
check_visibility "Accounting" false
check_visibility "Manufacturing" false

# Direct URL bypass tests – open a URL and verify we get an access‑denied page or redirection to login
# Function to test a URL and expect blocked (true = should be blocked)
check_url_block(){
  local url="$1" name="$2" expect_block="${3:-true}"
  # Open new tab for the URL
  openclaw browser open "$url" --label "tmp_$name"
  # Focus the new tab
  openclaw browser focus "tmp_$name"
  # Wait a short moment for page load
  sleep 3
  # Look for typical Odoo access denied text
  if openclaw browser wait --text "Access Denied" --timeout 5000; then
    blocked=true
  elif openclaw browser wait --text "Login" --timeout 5000; then
    blocked=true
  else
    blocked=false
  fi
  if [ "$blocked" = "$expect_block" ]; then
    status="PASS"
  else
    status="FAIL"
  fi
  append_result "$name" $expect_block $blocked "$status"
  # Close the temp tab
  openclaw browser close "tmp_$name" || true
}

# Attempt to open Purchase Order list (should be blocked)
check_url_block "${BASE_URL}/web#action=mail.action_mail_channel&model=purchase.order" "PurchaseURL" true
# Attempt to open Recruitment page (should be blocked)
check_url_block "${BASE_URL}/web#action=mail.action_mail_channel&model=hr.recruitment.stage" "RecruitmentURL" true
# Attempt to open a Helpdesk ticket (should be allowed – visible list)
check_url_block "${BASE_URL}/web#action=helpdesk.action_helpdesk_tickets" "HelpdeskURL" false

# Finished – print report location
echo "UI test completed. Report written to $REPORT"
