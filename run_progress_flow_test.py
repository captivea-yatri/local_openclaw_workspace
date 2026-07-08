#!/usr/bin/env python3
"""Run only the integrated progress‑report flow test from the QA suite.
This isolates the heavy QA sections and validates that the flow works
inside the main test workflow.
"""
import importlib.util, sys, os

# Load the QA test module
module_path = '/home/captivea/.openclaw/workspace/odoo_project_qa_test_captivea2.py'
spec = importlib.util.spec_from_file_location('qa_test', module_path)
qa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qa)

# Re‑use its connection helper
uid, models = qa.connect_to_odoo()
if not uid:
    sys.exit(1)
# Run the progress‑report flow test (project 2904 by default)
qa.test_project_progress_flow(uid, models)
print('Done')
