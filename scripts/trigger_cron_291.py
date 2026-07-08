#!/usr/bin/env python3
# Quick script to trigger ir.cron id=291 on the Odoo instance
from __future__ import annotations
import json, sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

DEFAULT_URL = "https://uriah-apolitical-masako.ngrok-free.dev"
DEFAULT_DB = "odoo19_captivea2"
DEFAULT_USER = "admin1"
DEFAULT_PASSWORD = "a"
DEFAULT_PROTOCOL = "jsonrpc"

class OdooRPCClient:
    def __init__(self, url, db, username, password, protocol="jsonrpc"):
        self.url = url.rstrip('/')
        self.db = db
        self.username = username
        self.password = password
        self.protocol = protocol.lower()
        self.uid = None
        self._json_id = 0
        self._xml_common = None
        self._xml_models = None
    def authenticate(self):
        if self.protocol == "xmlrpc":
            import xmlrpc.client
            self._xml_common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common", allow_none=True)
            self._xml_models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object", allow_none=True)
            uid = self._xml_common.authenticate(self.db, self.username, self.password, {})
        else:
            uid = self._jsonrpc("common", "authenticate", [self.db, self.username, self.password, {}])
        if not uid:
            raise RuntimeError("Authentication failed")
        self.uid = uid
        return uid
    def _jsonrpc(self, service, method, args):
        self._json_id += 1
        payload = {"jsonrpc":"2.0","method":"call","params":{"service":service,"method":method,"args":args},"id":self._json_id}
        req = Request(f"{self.url}/jsonrpc", data=json.dumps(payload).encode('utf-8'), headers={"Content-Type":"application/json"}, method="POST")
        try:
            with urlopen(req, timeout=180) as resp:
                body = json.loads(resp.read().decode('utf-8'))
        except HTTPError as exc:
            raise RuntimeError(f"HTTP error {exc.code}: {exc.reason}") from exc
        except URLError as exc:
            raise RuntimeError(f"Cannot reach Odoo at {self.url}: {exc}") from exc
        if body.get('error'):
            err = body['error']
            msg = err.get('data',{}).get('message') or err.get('message') or str(err)
            raise RuntimeError(f"Odoo RPC error: {msg}")
        return body.get('result')
    def execute_kw(self, model, method, args=None, kwargs=None):
        if self.uid is None:
            raise RuntimeError("Not authenticated")
        args = args or []
        kwargs = kwargs or {}
        if self.protocol == "xmlrpc":
            return self._xml_models.execute_kw(self.db, self.uid, self.password, model, method, args, kwargs)
        return self._jsonrpc('object','execute_kw',[self.db, self.uid, self.password, model, method, args, kwargs])

def main():
    client = OdooRPCClient(DEFAULT_URL, DEFAULT_DB, DEFAULT_USER, DEFAULT_PASSWORD, DEFAULT_PROTOCOL)
    try:
        uid = client.authenticate()
        print(f"Authenticated uid={uid}")
    except Exception as e:
        print(f"Auth error: {e}", file=sys.stderr)
        sys.exit(1)
    try:
        # Trigger cron id 291 by calling method_direct_trigger on the record
        result = client.execute_kw('ir.cron', 'method_direct_trigger', [[291]])
        print("Cron triggered, result:", result)
    except Exception as e:
        print(f"Cron execution error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
