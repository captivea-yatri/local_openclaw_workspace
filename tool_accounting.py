#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Merged runner for three RPC/flow tests:

1. full_inter_company_transaction_flow.py – inter‑company transaction flow
2. models/test_product_account_restriction_rpc.py – product & account restriction
3. models/test_ksc_auto_invoice_rpc.py – security‑deposit auto‑invoice flow

Executes each script with the same Odoo credentials, captures its stdout,
extracts PASS/FAILED counts, and prints a concise human‑readable summary.
"""

import subprocess
import sys
import re
from pathlib import Path

# -------------------------- Configuration --------------------------
# NOTE: the original URL had a stray "ng://" which broke the string. Use the correct URL.
ODOO_URL = "https://uriah-apolitical-masako.ngrok-free.dev"
DB = "odoo19_captivea2"
USER = "admin1"
PASSWORD = "a"
PROTOCOL = "jsonrpc"
# -----------------------------------------------------------------

SCRIPTS = [
    {
        "path": Path(__file__).parent / "full_inter_company_transaction_flow.py",
        "args": ["--url", ODOO_URL, "--db", DB, "--user", USER, "--password", PASSWORD],
        "label": "Inter‑Company Transaction Flow",
    },
    {
        "path": Path(__file__).parent / "models" / "test_product_account_restriction_rpc.py",
        "args": ["--url", ODOO_URL, "--db", DB, "--user", USER, "--password", PASSWORD, "--protocol", PROTOCOL],
        "label": "Product & Account Restriction",
    },
    {
        "path": Path(__file__).parent / "models" / "test_ksc_auto_invoice_rpc.py",
        "args": ["--url", ODOO_URL, "--db", DB, "--user", USER, "--password", PASSWORD, "--protocol", PROTOCOL],
        "label": "Security Deposit Auto‑Invoice",
    },
]

def run_script(script_path: Path, args: list[str], label: str) -> dict:
    """Run a test script and extract PASS/FAILED counts.
    Returns a dict with keys: label, passed, failed, total, output.
    """
    cmd = [sys.executable, str(script_path)] + args
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return {"label": label, "passed": 0, "failed": 0, "total": 0, "output": "TIMEOUT after 300 s"}
    out = proc.stdout + proc.stderr
    passed = failed = 0
    m = re.search(r"Result:\s*(\d+)\s*passed,\s*(\d+)\s*failed", out)
    if m:
        passed = int(m.group(1))
        failed = int(m.group(2))
    total = passed + failed
    return {"label": label, "passed": passed, "failed": failed, "total": total, "output": out}

def main() -> int:
    results = []
    for script in SCRIPTS:
        print(f"\n=== Running {script['label']} ===")
        res = run_script(script["path"], script["args"], script["label"]) 
        results.append(res)
        print(res["output"])
    print("\n===== Consolidated Test Summary =====")
    grand_pass = sum(r["passed"] for r in results)
    grand_fail = sum(r["failed"] for r in results)
    grand_total = sum(r["total"] for r in results)
    for r in results:
        print(f"- {r['label']}: {r['passed']} passed, {r['failed']} failed (total {r['total']})")
    print(f"\nGrand Total: {grand_pass} passed, {grand_fail} failed, {grand_total} checks")
    return 0 if grand_fail == 0 else 1

if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""
Merged runner for three RPC/flow tests:

1. full_inter_company_transaction_flow.py - inter-company transaction flow
2. models/test_product_account_restriction_rpc.py - product & account restriction
3. models/test_ksc_auto_invoice_rpc.py - security-deposit auto-invoice flow

Executes each script with the same Odoo credentials, captures its stdout,
extracts PASS/FAIL counts, and prints a concise human-readable summary.
"""

import subprocess
import sys
import re
from pathlib import Path

# -------------------------- Configuration --------------------------
ODOO_URL = "https://uriah-apolitical-masako.ngrok-free.dev"
DB = "odoo19_captivea2"
USER = "admin1"
PASSWORD = "a"
PROTOCOL = "jsonrpc"
# -----------------------------------------------------------------

SCRIPTS = [
    {
        "path": Path(__file__).parent / "full_inter_company_transaction_flow.py",
        "args": ["--url", ODOO_URL, "--db", DB, "--user", USER, "--password", PASSWORD],
        "label": "Inter-Company Transaction Flow",
    },
    {
        "path": Path(__file__).parent / "models" / "test_product_account_restriction_rpc.py",
        "args": ["--url", ODOO_URL, "--db", DB, "--user", USER, "--password", PASSWORD, "--protocol", PROTOCOL],
        "label": "Product & Account Restriction",
    },
    {
        "path": Path(__file__).parent / "models" / "test_ksc_auto_invoice_rpc.py",
        "args": ["--url", ODOO_URL, "--db", DB, "--user", USER, "--password", PASSWORD, "--protocol", PROTOCOL],
        "label": "Security Deposit Auto-Invoice",
    },
]

def run_script(script_path: Path, args: list[str], label: str) -> dict:
    """Execute a test script and extract PASS/FAIL counts.
    Returns a dict with keys: label, passed, failed, total, output.
    """
    cmd = [sys.executable, str(script_path)] + args
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return {"label": label, "passed": 0, "failed": 0, "total": 0, "output": "TIMEOUT after 300 s"}
    out = proc.stdout + proc.stderr
    # Parse a line like "Result: X passed, Y failed"
    passed = failed = 0
    m = re.search(r"Result:\s*(\d+)\s*passed,\s*(\d+)\s*failed", out)
    if m:
        passed = int(m.group(1))
        failed = int(m.group(2))
    total = passed + failed
    return {"label": label, "passed": passed, "failed": failed, "total": total, "output": out}

def main() -> int:
    results = []
    for script in SCRIPTS:
        print(f"\n=== Running {script['label']} ===")
        res = run_script(script["path"], script["args"], script["label"])
        results.append(res)
        print(res["output"])

# -*- coding: utf-8 -*-
"""
Merged runner for three RPC/flow tests:

1. full_inter_company_transaction_flow.py - inter-company transaction flow
2. models/test_product_account_restriction_rpc.py - product & account restriction
3. models/test_ksc_auto_invoice_rpc.py - security-deposit auto-invoice flow

Executes each script with the same Odoo credentials, captures its stdout,
extracts PASS/FAIL counts, and prints a concise human-readable summary.
"""

import subprocess
import sys
import re
from pathlib import Path

# -------------------------- Configuration --------------------------
ODOO_URL = "https://uriah-apolitical-masako.ngrok-free.dev"
DB = "odoo19_captivea2"
USER = "admin1"
PASSWORD = "a"
PROTOCOL = "jsonrpc"
# -----------------------------------------------------------------

SCRIPTS = [
    {
        "path": Path(__file__).parent / "full_inter_company_transaction_flow.py",
        "args": ["--url", ODOO_URL, "--db", DB, "--user", USER, "--password", PASSWORD],
        "label": "Inter-Company Transaction Flow",
    },
    {
        "path": Path(__file__).parent / "models" / "test_product_account_restriction_rpc.py",
        "args": ["--url", ODOO_URL, "--db", DB, "--user", USER, "--password", PASSWORD, "--protocol", PROTOCOL],
        "label": "Product & Account Restriction",
    },
    {
        "path": Path(__file__).parent / "models" / "test_ksc_auto_invoice_rpc.py",
        "args": ["--url", ODOO_URL, "--db", DB, "--user", USER, "--password", PASSWORD, "--protocol", PROTOCOL],
        "label": "Security Deposit Auto-Invoice",
    },
]

def run_script(script_path: Path, args: list[str], label: str) -> dict:
    """Run a script via subprocess, capture output, and parse PASS/FAIL counts.
    Returns a dict with keys: label, passed, failed, total, output.
    """
    cmd = [sys.executable, str(script_path)] + args
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return {"label": label, "passed": 0, "failed": 0, "total": 0, "output": f"TIMEOUT after 300 s"}
    out = proc.stdout + proc.stderr
    # Look for a line like "Result: X passed, Y failed"
    passed = failed = 0
    m = re.search(r"Result:\s*(\d+)\s*passed,\s*(\d+)\s*failed", out)
    if m:
        passed = int(m.group(1))
        failed = int(m.group(2))
    total = passed + failed
    return {"label": label, "passed": passed, "failed": failed, "total": total, "output": out}

def main() -> int:
    results = []
    for script in SCRIPTS:
        print(f"\n=== Running {script['label']} ===")
        res = run_script(script["path"], script["args"], script["label"])
        results.append(res)
        print(res["output"])

    # Consolidated summary
    print("\n===== Consolidated Test Summary =====")
    grand_pass = sum(r["passed"] for r in results)
    grand_fail = sum(r["failed"] for r in results)
    grand_total = sum(r["total"] for r in results)
    for r in results:
        print(f"- {r['label']}: {r['passed']} passed, {r['failed']} failed (total {r['total']})")
    print(f"\nGrand Total: {grand_pass} passed, {grand_fail} failed, {grand_total} checks")
    return 0 if grand_fail == 0 else 1

# -*- coding: utf-8 -*-
"""
Merged runner for three RPC/flow tests:

1. full_inter_company_transaction_flow.py - inter-company transaction flow
2. models/test_product_account_restriction_rpc.py - product & account restriction
3. models/test_ksc_auto_invoice_rpc.py - security-deposit auto-invoice flow

Executes each script with the same Odoo credentials, captures its stdout,
extracts PASS/FAIL counts, and prints a concise human-readable summary.
"""

import subprocess
import sys
import re
from pathlib import Path

# -------------------------- Configuration --------------------------
ODOO_URL = "https://uriah-apolitical-masako.ngrok-free.dev"
DB = "odoo19_captivea2"
USER = "admin1"
PASSWORD = "a"
PROTOCOL = "jsonrpc"
# -----------------------------------------------------------------

SCRIPTS = [
    {
        "path": Path(__file__).parent / "full_inter_company_transaction_flow.py",
        "args": ["--url", ODOO_URL, "--db", DB, "--user", USER, "--password", PASSWORD],
        "label": "Inter-Company Transaction Flow",
    },
    {
        "path": Path(__file__).parent / "models" / "test_product_account_restriction_rpc.py",
        "args": ["--url", ODOO_URL, "--db", DB, "--user", USER, "--password", PASSWORD, "--protocol", PROTOCOL],
        "label": "Product & Account Restriction",
    },
    {
        "path": Path(__file__).parent / "models" / "test_ksc_auto_invoice_rpc.py",
        "args": ["--url", ODOO_URL, "--db", DB, "--user", USER, "--password", PASSWORD, "--protocol", PROTOCOL],
        "label": "Security Deposit Auto-Invoice",
    },
]

def run_script(script_path: Path, args: list[str], label: str) -> dict:
    """Run a script via subprocess, capture output, and parse PASS/FAIL counts.
    Returns a dict with keys: label, passed, failed, total, output.
    """
    cmd = [sys.executable, str(script_path)] + args
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    except subprocess.TimeoutExpired:
        return {"label": label, "passed": 0, "failed": 0, "total": 0, "output": f"TIMEOUT after 300 s"}
    out = proc.stdout + proc.stderr
    # Look for a line like "Result: X passed, Y failed"
    passed = failed = 0
    m = re.search(r"Result:\s*(\d+)\s*passed,\s*(\d+)\s*failed", out)
    if m:
        passed = int(m.group(1))
        failed = int(m.group(2))
    total = passed + failed
    return {"label": label, "passed": passed, "failed": failed, "total": total, "output": out}

def main() -> int:
    results = []
    for script in SCRIPTS:
        print(f"\n=== Running {script['label']} ===")
        res = run_script(script["path"], script["args"], script["label"])
        results.append(res)
        print(res["output"])

    # Consolidated summary
    print("\n===== Consolidated Test Summary =====")
    grand_pass = sum(r["passed"] for r in results)
    grand_fail = sum(r["failed"] for r in results)
    grand_total = sum(r[
# -*- coding: utf-8 -*-
"""
Merged runner for three RPC/flow tests:

1. full_inter_company_transaction_flow.py (inter-company transaction flow)
2. models/test_product_account_restriction_rpc.py (product & account restriction)
3. models/test_ksc_auto_invoice_rpc.py (security-deposit auto-invoice flow)

The script executes each test with the same Odoo connection parameters,
captures their stdout, extracts PASS/FAIL counts and prints a concise
human-readable summary.
"""

import subprocess
import sys
import json
import re
from pathlib import Path

# -------------------------- Configuration --------------------------
ODOO_URL = "https://uriah-apolitical-masako.ngrok-free.dev"
DB = "odoo19_captivea2"
USER = "admin1"
PASSWORD = "a"
PROTOCOL = "jsonrpc"
# -----------------------------------------------------------------

SCRIPTS = [
    {
        "path": Path(__file__).parent / "full_inter_company_transaction_flow.py",
        "args": ["--url", ODOO_URL, "--db", DB, "--user", USER, "--password", PASSWORD],
        "label": "Inter-Company Transaction Flow",
    },
    {
        "path": Path(__file__).parent / "models" / "test_product_account_restriction_rpc.py",
        "args": ["