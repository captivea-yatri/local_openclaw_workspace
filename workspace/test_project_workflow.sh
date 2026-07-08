#!/usr/bin/env bash

# -----------------------------------------------------------------
# Automated Test Script for Odoo Custom Project Workflow
# ---------------------------------------------------------------
# This script drives the end‑to‑end QA test cases described in the
# "Custom Odoo Project Module — QA Test Script" using OpenClaw.
#
# It works by spawning a dedicated sub‑agent that runs the
# "odoo‑project‑workflow" skill (see
# ~/.openclaw/workspace/skills/odoo-project-workflow/SKILL.md).
# The sub‑agent performs the series of actions (login, record creation,
# UI navigation, validation, etc.) and returns a JSON summary of each
# test case – pass/fail and any error messages.
#
# Prerequisites
# --------------
# 1. OpenClaw must be installed and the gateway running.
# 2. The Odoo instance (captivea.com) must be reachable and the test
#    users/records defined in the QA specification must exist.
# 3. The "odoo‑project‑workflow" skill must be present and functional.
#
# Usage
# -----
#   chmod +x test_project_workflow.sh
#   ./test_project_workflow.sh   # runs all sections 1‑11
#   ./test_project_workflow.sh --section 3   # run only section 3 (blocking logic)
#
# The script prints a concise report to STDOUT and also writes a full
# JSON log to "test_project_workflow_results.json".
# -----------------------------------------------------------------

set -euo pipefail

# Helper: print coloured status messages
info()   { echo -e "\e[34m[INFO]\e[0m $*"; }
success(){ echo -e "\e[32m[SUCCESS]\e[0m $*"; }
error()  { echo -e "\e[31m[ERROR]\e[0m $*"; }

# Default: run all sections (1‑11)
SECTION="all"
if [[ $# -gt 0 ]]; then
    while [[ $# -gt 0 ]]; do
        case $1 in
            --section)
                SECTION="$2"
                shift 2
                ;;
            *)
                error "Unknown argument: $1"
                exit 1
                ;;
        esac
    done
fi

# Build the payload for the sub‑agent.  The "odoo‑project‑workflow" skill
# expects a JSON object with at least two keys:
#   "run_sections": array of section numbers to execute (e.g. [1,2,3])
#   "options": object with any extra toggles (e.g. {"dry_run":false})
# If SECTION is "all" we omit the field – the skill defaults to the full
# matrix.
payload_file=$(mktemp)
if [[ "$SECTION" == "all" ]]; then
    cat > "$payload_file" <<'EOF'
{
  "run_sections": "all"
}
EOF
else
    # Accept a comma‑separated list like "1,3,5"
    IFS=',' read -ra secs <<< "$SECTION"
    json_secs=$(printf "%s" "${secs[@]}" | jq -R 'split(",") | map(tonumber)')
    cat > "$payload_file" <<EOF
{
  "run_sections": $json_secs
}
EOF
fi

# Spawn the isolated sub‑agent.  We store the job ID so we can poll the
# result later.
info "Spawning Odoo project workflow test sub‑agent…"
job=$(openclaw sessions_spawn \
    --agent-id "odoo-project-workflow" \
    --task "run_tests" \
    --payload "$(cat $payload_file)" \
    --mode run \
    --runtime subagent \
    --label "odoo_project_workflow_test" \
    --timeout-seconds 1800)

# The CLI returns a JSON object that includes the job ID.  Extract it.
job_id=$(echo "$job" | jq -r '.job_id // .id')
if [[ -z "$job_id" || "$job_id" == "null" ]]; then
    error "Failed to obtain job ID from spawn command"
    exit 1
fi
success "Sub‑agent spawned (job ID: $job_id)"

# Wait for the sub‑agent to finish.  We poll the job run history every
# 10 seconds (max 30 minutes).  Adjust if you expect longer runs.
max_wait=1800   # seconds
interval=10
elapsed=0
while true; do
    run=$(openclaw cron runs --jobId "$job_id" --runMode due 2>/dev/null || true)
    status=$(echo "$run" | jq -r '.[0].status // empty')
    if [[ "$status" == "completed" ]]; then
        success "Test run completed"
        break
    elif [[ "$status" == "failed" ]]; then
        error "Test run failed – see sub‑agent output"
        break
    fi
    if (( elapsed >= max_wait )); then
        error "Timeout waiting for test run (>$max_wait s)"
        break
    fi
    sleep $interval
    (( elapsed += interval ))
done

# Retrieve the full result payload (the sub‑agent returns a JSON report).
info "Fetching test result payload…"
result=$(openclaw cron runs --jobId "$job_id" --runMode due | jq -r '.[0].payload // empty')
if [[ -z "$result" || "$result" == "null" ]]; then
    error "No payload returned from sub‑agent"
    exit 1
fi

# Save the detailed JSON log
log_file="test_project_workflow_results.json"
echo "$result" > "$log_file"
success "Full JSON log written to $log_file"

# Print a human‑readable summary.  Assume the payload contains an array
# "test_cases" with fields: id, name, status (passed/failed), message.
summary=$(echo "$result" | jq -r '.test_cases[] | "- \(.id) \(.name): \(.status) \(.message)"')
info "Test Summary:"
echo "$summary"

# Clean up temporary payload file
rm -f "$payload_file"

exit 0
