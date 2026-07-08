#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Full end‑to‑end QA flow for cap_account_intern_company_transection (Odoo 19).
Adjusted: skips the "button_draft" step to avoid the draft‑button issue.
"""

import datetime, json, ssl, sys, time, xmlrpc.client
from urllib.parse import urljoin

ODOO_URL = "https://uriah-apolitical-masako.ngrok-free.dev"
DB = "odoo19_captivea2"
ADMIN = "admin1"
PASS = "a"
REPORT_PATH = "full_inter_company_transaction_flow_report.json"
CMD_CREATE = 0
CMD_CLEAR = 5

def log(msg):
    print(msg)

def connect_admin():
    ctx = ssl._create_unverified_context()
    common = xmlrpc.client.ServerProxy(urljoin(ODOO_URL, "/xmlrpc/2/common"), context=ctx, allow_none=True)
    uid = common.authenticate(DB, ADMIN, PASS, {})
    if not uid:
        raise RuntimeError("Authentication failed")
    models = xmlrpc.client.ServerProxy(urljoin(ODOO_URL, "/xmlrpc/2/object"), context=ctx, allow_none=True)
    return uid, models

def execute(models, uid, model, method, *args, **kwargs):
    return models.execute_kw(DB, uid, PASS, model, method, list(args), kwargs or {})

def retry(label, func, attempts=3, delay=5):
    for attempt in range(attempts):
        try:
            return func()
        except Exception as exc:
            log(f"[!] {label} attempt {attempt+1}/{attempts} failed: {exc}")
            if attempt == attempts-1:
                raise
            time.sleep(delay)

def m2o_id(v):
    if not v:
        return None
    return v[0] if isinstance(v, (list, tuple)) else v

def multi_company_context(a_id, b_id):
    """Context that allows writes for both companies while defaulting to Company A.
    a_id – Company A (source), b_id – Company B (target).
    Needed because the invoice references a partner that belongs to Company B.
    """
    return {"allowed_company_ids": [a_id, b_id], "default_company_id": a_id, "force_company": a_id}

def read_move(models, uid, move_id):
    fields = ["name","move_type","state","partner_id","company_id","is_internal_invoice","inverse_move_type","inter_comp_journal_entry_id","ref","payment_reference","invoice_date","invoice_date_due","amount_total"]
    return execute(models, uid, "account.move", "read", [move_id], fields=fields)[0]

def check_result(res, label, cond, detail=""):
    res.append({"label": label, "passed": bool(cond), "detail": detail})
    log(f"[{'PASS' if cond else 'FAIL'}] {label}" + (f" -> {detail}" if detail else ""))
    return bool(cond)

def get_payable_receivable_maturity_ok(models, uid, move_id):
    line_ids = execute(models, uid, "account.move.line", "search", [("move_id", "=", move_id), ("account_id.account_type", "in", ["liability_payable", "asset_receivable"])])
    if not line_ids:
        return True, 0, 0
    lines = execute(models, uid, "account.move.line", "read", line_ids, fields=["date_maturity"])
    with_maturity = sum(1 for l in lines if l.get("date_maturity"))
    return with_maturity == len(lines), len(lines), with_maturity

def main():
    uid, models = retry("Admin connect", connect_admin)
    ts = int(time.time())
    today = datetime.date.today()
    results = []
    report = {"timestamp": ts, "database": DB, "odoo_url": ODOO_URL, "module": "cap_account_intern_company_transection", "checks": results}
    log("="*80)
    log("CAP Inter‑Company Transaction – flow without draft step")
    log("="*80)
    # Resolve companies
    company_ids = execute(models, uid, "res.company", "search", [], order="id")
    if len(company_ids) < 2:
        log("Creating Company B")
        company_b_id = execute(models, uid, "res.company", "create", {"name": f"CAP Co B {ts}"})
        execute(models, uid, "account.chart.template", "try_loading", "generic_coa", company_b_id, install_demo=False)
        company_ids = execute(models, uid, "res.company", "search", [], order="id")
    company_a_id, company_b_id = company_ids[0], company_ids[1]
    comps = execute(models, uid, "res.company", "read", [company_a_id, company_b_id], fields=["id","name","partner_id"])
    comp_a = next(c for c in comps if c["id"]==company_a_id)
    comp_b = next(c for c in comps if c["id"]==company_b_id)
    partner_a_id = m2o_id(comp_a["partner_id"])
    partner_b_id = m2o_id(comp_b["partner_id"])
    report.update({"company_a_id": company_a_id, "company_b_id": company_b_id, "company_a_name": comp_a["name"], "company_b_name": comp_b["name"]})
    # product
    prod_ids = execute(models, uid, "product.product", "search", [("sale_ok", "=", True), ("type", "=", "service")], limit=1)
    product_id = prod_ids[0] if prod_ids else execute(models, uid, "product.product", "create", {"name": f"CAP Service {ts}", "type": "service", "list_price": 450.0})
    report["product_id"] = product_id
    def create_out_invoice(suffix=""):
        vals = {"move_type": "out_invoice", "partner_id": partner_b_id, "company_id": company_a_id, "invoice_date": today.strftime("%Y-%m-%d"), "invoice_date_due": today.strftime("%Y-%m-%d"), "invoice_payment_term_id": False, "invoice_line_ids": [(CMD_CREATE,0,{"product_id": product_id, "name": f"CAP line {ts}{suffix}", "quantity":1.0, "price_unit":450.0, "tax_ids": [(CMD_CLEAR,0,0)]})]}
        return retry(f"create out_invoice{suffix}", lambda: execute(models, uid, "account.move", "create", vals, context=multi_company_context(company_a_id, company_b_id)))
    # 4 create invoice and related
    out_id = create_out_invoice()
    out = read_move(models, uid, out_id)
    rel_id = m2o_id(out.get("inter_comp_journal_entry_id"))
    check_result(results, "is_internal_invoice", out["is_internal_invoice"] is True)
    check_result(results, "inverse_move_type", out.get("inverse_move_type")=="in_invoice", out.get("inverse_move_type",""))
    check_result(results, "inter_comp_journal_entry_id", rel_id is not None, str(rel_id))
    # Skipping button_draft step as requested
    # 6 action_post
    post_id = create_out_invoice("-post")
    post_rel = m2o_id(read_move(models, uid, post_id).get("inter_comp_journal_entry_id"))
    retry("action_post", lambda: execute(models, uid, "account.move", "action_post", [post_id], context=multi_company_context(company_a_id, company_b_id)))
    post = read_move(models, uid, post_id)
    check_result(results, "action_post posted", post["state"]=="posted", post["state"])
    if post_rel:
        post_rel_move = read_move(models, uid, post_rel)
        check_result(results, "post related posted", post_rel_move["state"]=="posted", post_rel_move["state"])
        ok,total,filled = get_payable_receivable_maturity_ok(models, uid, post_rel)
        check_result(results, "date_maturity", ok, f"{filled}/{total}")
    # final summary
    passed=sum(1 for r in results if r["passed"])
    failed=sum(1 for r in results if not r["passed"])
    report["summary"]={"passed":passed,"failed":failed,"total":len(results),"success":failed==0}
    with open(REPORT_PATH,"w",encoding="utf-8") as f:
        json.dump(report,f,indent=2)
    log("Report written to "+REPORT_PATH)
    print(json.dumps(report,indent=2))
    if failed:
        sys.exit(1)

if __name__=="__main__":
    main()
