#!/usr/bin/env python3
import json, subprocess, sys, os

# Run the QA test script and capture its JSON output
script_path = os.path.join(os.getcwd(), 'workspace', 'qa_odoo_full_test.py')
try:
    raw = subprocess.check_output([sys.executable, script_path], stderr=subprocess.STDOUT, timeout=300)
except subprocess.CalledProcessError as e:
    print('Error executing qa_odoo_full_test.py:')
    print(e.output.decode())
    sys.exit(1)
except Exception as e:
    print('Unexpected error:', e)
    sys.exit(1)

try:
    results = json.loads(raw)
except Exception as e:
    print('Failed to parse JSON output:', e)
    sys.exit(1)

# Produce a readable report
out_lines = []
out_lines.append('=== Odoo QA Full Test Report ===')
out_lines.append(f'Total test cases: {len(results)}')
out_lines.append('')
for rec in results:
    tc = rec.get('tc')
    module = rec.get('module')
    action = rec.get('action')
    status = rec.get('status')
    detail = rec.get('detail', '')
    out_lines.append(f"TC {tc:4d} | {module:<30} | {action:<12} | {status:<8} | {detail}")

print('\n'.join(out_lines))
