#!/usr/bin/env bash
# UI test for Odoo v19 using OpenClaw browser tool.
# Logs in as Webmaster, checks module menu visibility per role spec, and records results.

BASE_URL="https://staging-odoo19-captivea.odoo.com"
LOGIN_URL="${BASE_URL}/web/login"
USER="sebastien.riss@captivea.com"
PASS="a"
TAB_LABEL="odoo_ui_test"
REPORT="ui_test_report.json"
TMP="/tmp/ui_report.tmp"

# Helper to run a browser command and abort on error.
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

# 1. Open login page.
run_cmd "Open login page" open "${LOGIN_URL}" --label "${TAB_LABEL}"

# 2. Wait for login fields.
run_cmd "Wait for username" wait --time 3
run_cmd "Wait for password" wait --time 3

# 3. Fill credentials.
run_cmd "Fill username" fill --selector "input[name='login']" --text "${USER}"
run_cmd "Fill password" fill --selector "input[name='password']" --text "${PASS}"

# 4. Submit login.
run_cmd "Click login" click --selector "button[type='submit']"

# 5. Wait for the main navigation bar (dashboard) to appear.
run_cmd "Wait for dashboard" wait --selector ".o_main_navbar"

# Helper to evaluate visibility of a menu entry.
check_menu(){
  local name="$1"
  local selector="$2"
  # Evaluate presence via JS; returns true/false string.
  local result=$(openclaw browser eval --script "document.querySelector('$selector') !== null")
  if [[ "$result" == *"true"* ]]; then
    echo "{\"module\":\"$name\",\"visible\":true}" >> "$TMP"
  else
    echo "{\"module\":\"$name\",\"visible\":false}" >> "$TMP"
  fi
}

# 6. Gather menu visibility according to spec.
# Start JSON array.
printf "[\n" > "$TMP"
check_menu "CRM" "a[data-menu-xmlid='crm.crm_menu_root']"
check_menu "Contacts" "a[data-menu-xmlid='contacts.menu_root']"
check_menu "Employees" "a[data-menu-xmlid='hr.menu_hr_root']"
check_menu "Helpdesk" "a[data-menu-xmlid='helpdesk.menu_main_helpdesk']"
check_menu "Website" "a[data-menu-xmlid='website.menu_website_configuration']"
check_menu "Purchase" "a[data-menu-xmlid='purchase.menu_purchase_root']"
check_menu "Recruitment" "a[data-menu-xmlid='hr_recruitment.menu_hr_recruitment_root']"
# Remove trailing commas and close array.
sed -i '$ s/},/}/' "$TMP"
printf "]\n" >> "$TMP"
mv "$TMP" "$REPORT"

# 7. Capture a screenshot for manual verification.
run_cmd "Capture screenshot" screenshot --output "dashboard.png"
