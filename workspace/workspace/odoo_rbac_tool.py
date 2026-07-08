#!/usr/bin/env python3
"""
════════════════════════════════════════════════════════════════════════=======
 ODOO FULL RBAC DISCOVERY & COMPARISON TOOL
════════════════════════════════════════════════════════════════════════=======

 Discovers EVERYTHING a user can access: all menus, all models, CRUD,
 field-level access, buttons/actions. Creates comprehensive baseline.

 PHASE 1 — DISCOVER v18.0:
 python3 odoo_rbac_tool.py discover --excel credentials.xlsx
 python3 odoo_rbac_tool.py discover --excel credentials.xlsx --roles "President,CEO"
 python3 odoo_rbac_tool.py discover --excel credentials.xlsx --test-connection
 python3 odoo_rbac_tool.py discover --excel credentials.xlsx --list-roles

 PHASE 2 — COMPARE v19.0:
 python3 odoo_rbac_tool.py compare --baseline baseline_v18_XXX.xlsx --excel creds_v19.xlsx

 REQUIREMENTS: pip install openpyxl requests
"""

import argparse, datetime, json, logging, os, re, sys, time, traceback
from collections import defaultdict, OrderedDict
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
except ImportError:
    sys.exit("pip install requests")
try:
    import openpyxl
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from openpyxl.formatting.rule import CellIsRule
except ImportError:
    sys.exit("pip install openpyxl")

TS = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = f"rbac_full_discovery_{TS}.log"

def setup_logging():
    lg = logging.getLogger("rbac")
    lg.setLevel(logging.DEBUG)
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s"))
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s", datefmt="%H:%M:%S"))
    lg.addHandler(fh)
    lg.addHandler(ch)
    return lg

log = setup_logging()

def fix_url(url):
    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"

def guess_db(url):
    h = urlparse(url).hostname or ""
    parts = h.split(".")
    return parts[0] if len(parts) >= 2 else ""

def norm_role(n):
    return re.sub(r'[\s_\-/()]+', '', n.lower().strip())

def match_roles(filters, available):
    am = {norm_role(n): n for n in available}
    matched, unmatch = set(), []
    for fn in filters:
        fn = fn.strip()
        if fn in available:
            matched.add(fn)
            continue
        fn_n = norm_role(fn)
        if fn_n in am:
            matched.add(am[fn_n])
            continue
        partial = [n for n in available if fn_n in norm_role(n)]
        if partial:
            matched.add(partial[0])
            continue
        unmatch.append(fn)
    return matched, unmatch

# ═══════════════════════════════════════════════════════════════
# KEY MODELS TO TEST (with create data and write fields)
# ═══════════════════════════════════════════════════════════════

KEY_MODELS = OrderedDict([
    ("res.partner", {"label": "Contacts", "create": {"name": "__RBAC_DISC__"}, "wfield": "phone", "wval": "0000"}),
    ("crm.lead", {"label": "CRM Leads", "create": {"name": "__RBAC_DISC__"}, "wfield": "description", "wval": "test"}),
    ("sale.order", {"label": "Sales Orders", "create": "auto", "wfield": "note", "wval": "test"}),
    ("project.project", {"label": "Projects", "create": {"name": "__RBAC_DISC__"}, "wfield": "description", "wval": "test"}),
    ("project.task", {"label": "Tasks", "create": {"name": "__RBAC_DISC__"}, "wfield": "description", "wval": "test"}),
    ("account.analytic.line", {"label": "Timesheets", "create": {"name": "__RBAC_DISC__", "unit_amount": 1.0}, "wfield": "name", "wval": "test"}),
    ("account.move", {"label": "Journal Entries", "create": "auto", "wfield": "narration", "wval": "test"}),
    ("account.asset", {"label": "Assets", "create": {"name": "__RBAC_DISC__"}, "wfield": "name", "wval": "__RBAC_DISC_W__"}),
    ("purchase.order", {"label": "Purchase Orders", "create": "auto", "wfield": "notes", "wval": "test"}),
    ("hr.employee", {"label": "Employees (Private)", "create": {"name": "__RBAC_DISC__"}, "wfield": "work_phone", "wval": "0000"}),
    ("hr.employee.public", {"label": "Employees (Public)", "create": "skip", "wfield": "auto", "wval": "test"}),
    ("gamification.goal", {"label": "Goals", "create": "skip", "wfield": "auto", "wval": "test"}),
    ("gamification.challenge", {"label": "Challenges", "create": {"name": "__RBAC_DISC__"}, "wfield": "description", "wval": "test"}),
    ("hr.attendance", {"label": "Attendance", "create": "skip", "wfield": "auto", "wval": "test"}),
    ("hr.applicant", {"label": "Recruitment", "create": {"partner_name": "__RBAC_DISC__"}, "wfield": "priority", "wval": "1"}),
    ("helpdesk.ticket", {"label": "Helpdesk Tickets", "create": {"name": "__RBAC_DISC__"}, "wfield": "description", "wval": "test"}),
    ("website", {"label": "Website", "create": "skip", "wfield": "auto", "wval": "test"}),
    ("marketing.activity", {"label": "Marketing Automation", "create": "skip", "wfield": "auto", "wval": "test"}),
    ("mailing.mailing", {"label": "Email Marketing", "create": {"subject": "__RBAC_DISC__"}, "wfield": "subject", "wval": "__RBAC_DISC_W__"}),
    ("social.post", {"label": "Social Marketing", "create": {"message": "__RBAC_DISC__"}, "wfield": "message", "wval": "__RBAC_DISC_W__"}),
    ("hr.leave", {"label": "Time Off", "create": "skip", "wfield": "auto", "wval": "test"}),
    ("hr.expense", {"label": "Expenses", "create": {"name": "__RBAC_DISC__"}, "wfield": "name", "wval": "__RBAC_DISC_W__"}),
    ("hr.contract", {"label": "Contracts", "create": "skip", "wfield": "name", "wval": "__RBAC_DISC_W__"}),
    ("hr.payslip", {"label": "Payslips", "create": "skip", "wfield": "auto", "wval": "test"}),
    ("approval.request", {"label": "Approvals", "create": {"name": "__RBAC_DISC__"}, "wfield": "name", "wval": "__RBAC_DISC_W__"}),
    ("fleet.vehicle", {"label": "Fleet", "create": "auto", "wfield": "auto", "wval": "test"}),
    ("lunch.order", {"label": "Lunch", "create": "skip", "wfield": "auto", "wval": "test"}),
    ("planning.slot", {"label": "Planning", "create": "skip", "wfield": "auto", "wval": "test"}),
    ("sign.request", {"label": "Sign Requests", "create": "skip", "wfield": "auto", "wval": "test"}),
    ("event.event", {"label": "Events", "create": {"name": "__RBAC_DISC__"}, "wfield": "name", "wval": "__RBAC_DISC_W__"}),
    ("survey.survey", {"label": "Surveys", "create": {"title": "__RBAC_DISC__"}, "wfield": "title", "wval": "__RBAC_DISC_W__"}),
    ("documents.document", {"label": "Documents", "create": {"name": "__RBAC_DISC__"}, "wfield": "name", "wval": "__RBAC_DISC_W__"}),
    ("hr.appraisal", {"label": "Appraisals", "create": "skip", "wfield": "auto", "wval": "test"}),
    ("account.payment", {"label": "Payments", "create": "skip", "wfield": "auto", "wval": "test"}),
    ("account.bank.statement", {"label": "Bank Statements", "create": {"name": "__RBAC_DISC__"}, "wfield": "name", "wval": "__RBAC_DISC_W__"}),
    ("product.template", {"label": "Products", "create": {"name": "__RBAC_DISC__"}, "wfield": "name", "wval": "__RBAC_DISC_W__"}),
])

# Buttons to test (model, method, label, domain filter)
BUTTONS_TO_TEST = [
    ("purchase.order", "button_confirm", "Confirm PO", [("state","=","draft")]),
    ("sale.order", "action_confirm", "Confirm SO", [("state","=","draft")]),
    ("account.move", "action_post", "Post Invoice", [("state","=","draft"),("move_type","in",["out_invoice","in_invoice"])]) ,
    ("helpdesk.ticket", "assign_ticket_to_self", "Assign Ticket", []),
]

# Fields to check (model, field_name, friendly label)
FIELDS_TO_CHECK = [
    ("purchase.order", "credit_card_no", "PO Credit Card Field"),
    ("sale.order", "amount_total", "SO Total Amount"),
    ("sale.order", "amount_untaxed", "SO Untaxed Amount"),
    ("hr.employee", "private_street", "Employee Private Address"),
    ("hr.employee", "km_home_work", "Employee Home-Work Distance"),
    ("hr.employee", "private_phone", "Employee Private Phone"),
    ("hr.contract", "wage", "Contract Wage"),
    ("account.move", "amount_total", "Invoice Total"),
    ("res.partner", "credit_limit", "Partner Credit Limit"),
    ("res.partner", "total_invoiced", "Partner Total Invoiced"),
    ("res.partner", "total_due", "Partner Total Due"),
    ("res.partner", "sale_order_count", "Partner SO Count"),
]

# ═══════════════════════════════════════════════════════════════
# ODOO CLIENT
# ═══════════════════════════════════════════════════════════════

class OdooClient:
    def __init__(self, base_url, db, login, password):
        self.base_url = fix_url(base_url)
        self.db = db.strip() if db else ""
        self.login_email = login.strip()
        self.password = password.strip()
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        self.uid = None
        self.user_context = {}
        self.actual_db = self.db

    def authenticate(self):
        cands = [self.db] if self.db else []
        g = guess_db(self.base_url)
        if g and g not in cands:
            cands.append(g)
        try:
            r = self.session.post(f"{self.base_url}/web/database/list",
                json={"jsonrpc":"2.0","method":"call","params":{},"id":1}, timeout=10).json()
            if "result" in r:
                for d in r["result"]:
                    if d not in cands:
                        cands.append(d)
        except Exception:
            pass
        for db in cands:
            if self._try_auth(db):
                return True
        return self._try_session_auth()

    def _try_auth(self, db):
        try:
            r = self.session.post(f"{self.base_url}/web/session/authenticate",
                json={"jsonrpc":"2.0","method":"call","params":{"db":db,"login":self.login_email,"password":self.password},"id":int(time.time()*1000)}, timeout=30).json()
            if "error" not in r and r.get("result",{}).get("uid"):
                self.uid = r["result"]["uid"]
                self.user_context = r["result"].get("user_context",{})
                self.actual_db = db
                return True
        except Exception:
            pass
        return False

    def _try_session_auth(self):
        try:
            pg = self.session.get(f"{self.base_url}/web/login", timeout=15)
            csrf = ""
            m = re.search(r'csrf_token["\s]*[=:]\s*["\']([^"\']+)', pg.text)
            if m:
                csrf = m.group(1)
            form = {"login":self.login_email,"password":self.password,"csrf_token":csrf}
            dm = re.search(r'name[="\']db[="\'][^>]*value[="\']([^"\']+)', pg.text)
            if dm:
                form["db"] = dm.group(1)
            rp = self.session.post(f"{self.base_url}/web/login", data=form, timeout=30, allow_redirects=True)
            if "/web/login" not in rp.url or rp.url.endswith("/web"):
                si = self._rpc("/web/session/get_session_info", {})
                if isinstance(si, dict) and not si.get("_err") and si.get("uid"):
                    self.uid = si["uid"]
                    self.user_context = si.get("user_context",{})
                    self.actual_db = si.get("db", "")
                    return True
        except Exception:
            pass
        return False

    def _rpc(self, ep, params):
        try:
            r = self.session.post(f"{self.base_url}{ep}", json={"jsonrpc":"2.0","method":"call","params":params,"id":int(time.time()*1000)}, timeout=30).json()
            if "error" in r:
                ed = r["error"]
                return {"_err": True, "_msg": ed.get("data",{}).get("message", str(ed.get("message",""))), "_name": ed.get("data",{}).get("name", "")}
            return r.get("result")
        except requests.exceptions.RequestException as e:
            return {"_err": True, "_msg": str(e), "_name": "ConnectionError"}

    def _kw(self, model, method, args=None, kwargs=None):
        return self._rpc("/web/dataset/call_kw", {"model": model, "method": method, "args": args or [], "kwargs": kwargs or {}})

    def _iserr(self, r):
        return isinstance(r, dict) and r.get("_err")
    def _isaccess(self, r):
        if not self._iserr(r):
            return False
        m = (r.get("_msg","") + " " + r.get("_name","")).lower()
        return any(k in m for k in ["accesserror","access_error","not allowed","denied","forbidden","restricted","ir.rule","record rule","not have access","security"])
    def _emsg(self, r):
        return r.get("_msg","")[:300] if self._iserr(r) else ""

    # CRUD helpers -------------------------------------------------
    def search_read(self, model, domain=None, fields=None, limit=5):
        r = self._kw(model, "search_read", [domain or []], {"fields": fields or ["id","display_name"], "limit": limit, "context": self.user_context})
        if self._iserr(r):
            return {"ok": False, "access": self._isaccess(r), "err": self._emsg(r), "recs": [], "cnt": 0}
        recs = r if isinstance(r, list) else []
        return {"ok": True, "recs": recs, "cnt": len(recs)}
    def search_count(self, model, domain=None):
        r = self._kw(model, "search_count", [domain or []], {"context": self.user_context})
        if self._iserr(r):
            return {"ok": False, "access": self._isaccess(r), "err": self._emsg(r)}
        return {"ok": True, "cnt": r}
    def create(self, model, vals):
        r = self._kw(model, "create", [vals], {"context": self.user_context})
        if self._iserr(r):
            return {"ok": False, "access": self._isaccess(r), "err": self._emsg(r)}
        return {"ok": True, "id": r}
    def write(self, model, rid, vals):
        r = self._kw(model, "write", [[rid], vals], {"context": self.user_context})
        if self._iserr(r):
            return {"ok": False, "access": self._isaccess(r), "err": self._emsg(r)}
        return {"ok": True}
    def unlink(self, model, rid):
        r = self._kw(model, "unlink", [[rid]], {"context": self.user_context})
        if self._iserr(r):
            return {"ok": False, "access": self._isaccess(r), "err": self._emsg(r)}
        return {"ok": True}
    def call_btn(self, model, method, rids):
        r = self._kw(model, method, [rids], {"context": self.user_context})
        if self._iserr(r):
            return {"ok": False, "access": self._isaccess(r), "err": self._emsg(r)}
        return {"ok": True}
    def fields_get(self, model, field_names=None):
        attrs = ["string","type","readonly","required","groups"]
        r = self._kw(model, "fields_get", [], {"attributes": attrs, "context": self.user_context})
        if self._iserr(r):
            return {"ok": False, "err": self._emsg(r)}
        if field_names:
            return {"ok": True, "fields": {k:v for k,v in r.items() if k in field_names}}
        return {"ok": True, "fields": r}
    def load_menus(self):
        for ep in ["/web/action/load_menus","/web/webclient/load_menus"]:
            r = self._rpc(ep, {"hash":""})
            if not self._iserr(r) and r:
                return {"ok": True, "data": r, "src": ep}
        r3 = self.search_read("ir.ui.menu", [], ["id","name","parent_id","complete_name","action"], limit=1000)
        if r3["ok"] and r3["cnt"] > 0:
            return {"ok": True, "data": {"_flat": r3["recs"]}, "src": "ir.ui.menu"}
        return {"ok": False}
    def get_all_menus(self, mdata):
        menus = []
        if isinstance(mdata, dict) and "_flat" in mdata:
            for m in mdata["_flat"]:
                menus.append({"name": m.get("name",""), "path": m.get("complete_name",""), "id": m.get("id")})
        else:
            self._collect_menus(mdata, menus, "")
        return menus
    def _collect_menus(self, data, menus, prefix):
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, dict):
                    nm = v.get("name","")
                    path = f"{prefix}/{nm}" if prefix else nm
                    if nm:
                        menus.append({"name": nm, "path": path, "id": v.get("id")})
                    for ck in ("children","childrenTree"):
                        if v.get(ck):
                            self._collect_menus(v[ck], menus, path)
                elif isinstance(v, list):
                    self._collect_menus(v, menus, prefix)
        elif isinstance(data, list):
            for i in data:
                self._collect_menus(i, menus, prefix)
    def get_groups(self):
        u = self._kw("res.users", "read", [self.uid], {"fields": ["name","login","groups_id"], "context": self.user_context})
        if self._iserr(u) or not u:
            return []
        gids = u[0].get("groups_id", [])
        if not gids:
            return []
        gs = self._kw("res.groups", "read", [gids], {"fields": ["full_name","name","category_id"]})
        return gs if not self._iserr(gs) else []

# ═══════════════════════════════════════════════════════════════
# FULL DISCOVERY ENGINE
# ═══════════════════════════════════════════════════════════════

class FullDiscovery:
    def __init__(self):
        self.all_results = OrderedDict()

    def discover(self, creds, roles_filter=None):
        test_roles = set(creds.keys())
        if roles_filter:
            matched, _ = match_roles(roles_filter, test_roles)
            test_roles = matched
        log.info(f"{'='*70}\n FULL RBAC DISCOVERY | Roles: {len(test_roles)}\n{'='*70}")
        for role in sorted(test_roles):
            cr = creds[role]
            log.info(f"\n{'═'*70}\n ROLE: {role} | {cr['login']}\n{'═'*70}")
            cli = OdooClient(cr["url"], cr["db"], cr["login"], cr["password"])
            if not cli.authenticate():
                log.error(" ✗ AUTH FAILED")
                self.all_results[role] = [{"category":"Auth","test":"Login","result":"FAILED","detail":"Cannot authenticate"}]
                continue
            log.info(f" ✓ Auth OK (uid={cli.uid}, db={cli.actual_db})")
            tests = []
            trash = []
            # 1. USER GROUPS
            groups = cli.get_groups()
            group_names = sorted(set(g.get("full_name",g.get("name","")) for g in groups)) if groups else []
            tests.append({"category":"User Info","test":"Security Groups","result":f"{len(group_names)} groups","detail":"; ".join(group_names)})
            log.info(f" Groups: {len(group_names)}")
            # 2. MENUS
            menus_res = cli.load_menus()
            if menus_res.get("ok"):
                all_menus = cli.get_all_menus(menus_res["data"])
                log.info(f" Menus: {len(all_menus)} visible")
                tests.append({"category":"Menus","test":"Total Visible Menus","result":str(len(all_menus)),"detail":""})
                top_menus = set()
                for m in all_menus:
                    path = m.get("path","")
                    top = path.split("/")[0] if "/" in path else m.get("name","")
                    if top and top not in top_menus:
                        top_menus.add(top)
                        tests.append({"category":"Menus","test":f"Menu: {top}","result":"Visible","detail":""})
                for m in all_menus:
                    nm = m.get("name","").lower()
                    path = m.get("path","") or m.get("complete_name","") or ""
                    if "configuration" in nm or "settings" in nm:
                        tests.append({"category":"Menus","test":f"Submenu: {m.get('name','')}","result":"Visible","detail":path})
                    if "reporting" in nm or "reports" in nm:
                        tests.append({"category":"Menus","test":f"Submenu: {m.get('name','')}","result":"Visible","detail":path})
            else:
                tests.append({"category":"Menus","test":"Menu Loading","result":"FAILED","detail":"Could not load menus"})
            # 3. MODEL CRUD ACCESS
            log.info(" Testing model access...")
            for model, cfg in KEY_MODELS.items():
                label = cfg["label"]
                log.info(f" {label} ({model})...")
                # READ
                sr = cli.search_read(model, [], ["id","display_name"], limit=5)
                if sr["ok"]:
                    cnt = cli.search_count(model)
                    total = cnt.get("cnt", sr["cnt"]) if cnt.get("ok") else sr["cnt"]
                    tests.append({"category":"Model Access","test":f"{label} — Read","result":"YES","detail":f"Total records visible: {total}"})
                else:
                    if sr.get("access"):
                        tests.append({"category":"Model Access","test":f"{label} — Read","result":"NO","detail":"Access denied"})
                    else:
                        tests.append({"category":"Model Access","test":f"{label} — Read","result":"ERROR","detail":sr.get("err","")[:100]})
                # WRITE
                wfield = cfg.get("wfield")
                wval = cfg.get("wval", "test")
                if wfield == "auto" and sr["cnt"] > 0:
                    fg = cli.fields_get(model)
                    if fg.get("ok"):
                        for fn, fi in fg["fields"].items():
                            if fi.get("type") in ("char","text","html") and not fi.get("readonly") and fn not in ("name","display_name","__last_update") and not fn.startswith("x_"):
                                wfield = fn
                                wval = "__RBAC_W_TEST__"
                                break
                        if wfield == "auto":
                            if "name" in fg["fields"] and not fg["fields"]["name"].get("readonly"):
                                wfield = "name"
                                wval = "__RBAC_W_TEST__"
                if wfield and wfield != "auto" and sr["cnt"] > 0:
                    rec_id = sr["recs"][0]["id"]
                    orig = cli.search_read(model, [("id","=",rec_id)], [wfield], limit=1)
                    orig_val = orig["recs"][0].get(wfield) if orig["ok"] and orig["cnt"] > 0 else None
                    wr = cli.write(model, rec_id, {wfield: wval})
                    if wr["ok"]:
                        tests.append({"category":"Model Access","test":f"{label} — Write","result":"YES","detail":f"Can edit field '{wfield}'"})
                        if orig_val is not None:
                            try:
                                cli.write(model, rec_id, {wfield: orig_val})
                            except Exception:
                                pass
                    else:
                        tests.append({"category":"Model Access","test":f"{label} — Write","result":"NO","detail":wr.get("err","")[:100]})
                elif sr["cnt"] == 0:
                    tests.append({"category":"Model Access","test":f"{label} — Write","result":"NO RECORDS","detail":"No records to test write"})
                else:
                    car = cli._kw(model, "check_access_rights", ["write"], {"raise_exception": False})
                    if not cli._iserr(car) and car is True:
                        tests.append({"category":"Model Access","test":f"{label} — Write","result":"YES (rights check)","detail":"check_access_rights=True, no field to verify"})
                    elif not cli._iserr(car) and car is False:
                        tests.append({"category":"Model Access","test":f"{label} — Write","result":"NO","detail":"check_access_rights=False"})
                    else:
                        tests.append({"category":"Model Access","test":f"{label} — Write","result":"UNKNOWN","detail":"Could not determine write access"})
                # CREATE / DELETE
                cv = cfg.get("create")
                if cv == "skip":
                    car = cli._kw(model, "check_access_rights", ["create"], {"raise_exception": False})
                    if not cli._iserr(car) and car is True:
                        tests.append({"category":"Model Access","test":f"{label} — Create","result":"YES (rights check)","detail":"check_access_rights=True"})
                    elif not cli._iserr(car) and car is False:
                        tests.append({"category":"Model Access","test":f"{label} — Create","result":"NO","detail":"check_access_rights=False"})
                    else:
                        tests.append({"category":"Model Access","test":f"{label} — Create","result":"UNKNOWN","detail":"Could not determine"})
                    car_d = cli._kw(model, "check_access_rights", ["unlink"], {"raise_exception": False})
                    if not cli._iserr(car_d) and car_d is True:
                        tests.append({"category":"Model Access","test":f"{label} — Delete","result":"YES (rights check)","detail":"check_access_rights=True"})
                    elif not cli._iserr(car_d) and car_d is False:
                        tests.append({"category":"Model Access","test":f"{label} — Delete","result":"NO","detail":"check_access_rights=False"})
                    else:
                        tests.append({"category":"Model Access","test":f"{label} — Delete","result":"UNKNOWN","detail":""})
                elif cv == "auto":
                    fg = cli.fields_get(model)
                    if fg.get("ok"):
                        auto_vals = {}
                        for fn, fi in fg["fields"].items():
                            if fi.get("required") and not fi.get("readonly") and fn not in ("id","create_uid","write_uid","create_date","write_date","__last_update"):
                                ft = fi.get("type","")
                                if ft in ("char","text"):
                                    auto_vals[fn] = "__RBAC_DISC__"
                                elif ft ==