#!/usr/bin/env python3
"""CNS API — registration, transfer, balances, SQLite sync."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
UI_DIR = ROOT / "ui"
DATA_DIR = ROOT / "data"
MANIFEST_FILE = ROOT / "artifacts" / "program.json"
TREASURY_PUBLIC = ROOT / "config" / "treasury.public.json"


def load_treasury() -> dict:
    return load_json(TREASURY_PUBLIC, {})

sys.path.insert(0, str(ROOT / "server"))
import db  # noqa: E402

NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z][a-z0-9-]{0,15})?$")
ACCOUNT_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def normalize_name(name: str) -> str:
    return name.strip().lower()


def name_hash_hex(name: str) -> str:
    return hashlib.sha256(normalize_name(name).encode("utf-8")).hexdigest()


def load_manifest() -> dict:
    if not MANIFEST_FILE.exists():
        return {}
    return json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))


def save_labels_from_entry(entry: dict) -> None:
    labels_path = DATA_DIR / "labels.json"
    labels: list = []
    if labels_path.exists():
        labels = json.loads(labels_path.read_text(encoding="utf-8"))
    labels = [e for e in labels if e.get("name_hash") != entry["name_hash"]]
    labels.append(entry)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    labels_path.write_text(json.dumps(labels, indent=2) + "\n", encoding="utf-8")


def calldata_hint(method: str, manifest: dict, **fields) -> dict:
    methods = manifest.get("methods", {})
    idx = methods.get(method)
    return {
        "contract_id": manifest.get("contract_id"),
        "method": method,
        "method_index": idx,
        "calldata": fields,
        "note": "Submit via Cube Call entry when available, or use Cube node CLI.",
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print(f"[cns] {self.address_string()} {fmt % args}")

    def _send(self, code: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/static/"):
            rel = path.removeprefix("/static/")
            file_path = (UI_DIR / "static" / rel).resolve()
            if not str(file_path).startswith(str((UI_DIR / "static").resolve())):
                self._send(403, b"Forbidden", "text/plain")
                return
            if file_path.is_file():
                ctype = "text/css" if rel.endswith(".css") else "application/javascript"
                self._send(200, file_path.read_bytes(), ctype)
                return
            self._send(404, b"Not found", "text/plain")
            return

        if path in ("/", "/index.html"):
            self._send(200, (UI_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
            return

        manifest = load_manifest()

        if path == "/api/manifest":
            self._send(200, json.dumps(manifest).encode())
            return

        if path == "/api/names":
            db.sync_all()
            rows = db.list_names()
            self._send(
                200,
                json.dumps(
                    {
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "contract_id": manifest.get("contract_id"),
                        "records": rows,
                    }
                ).encode(),
            )
            return

        if path == "/api/resolve":
            qs = parse_qs(urlparse(self.path).query)
            name = (qs.get("name") or [""])[0]
            if not name:
                self._send(400, json.dumps({"error": "name required"}).encode())
                return
            db.sync_all()
            rec = db.find_by_name(name)
            if not rec:
                nh = name_hash_hex(name)
                self._send(
                    404,
                    json.dumps({"error": "not found", "name_hash": nh}).encode(),
                )
                return
            bal = db.get_balance(rec["account"])
            rec["balance"] = bal.get("balance")
            self._send(200, json.dumps(rec).encode())
            return

        if path == "/api/balance":
            qs = parse_qs(urlparse(self.path).query)
            account = (qs.get("account") or [""])[0].lower().replace("0x", "")
            name = (qs.get("name") or [""])[0]
            db.sync_all()
            if name and not account:
                rec = db.find_by_name(name)
                if not rec:
                    self._send(404, json.dumps({"error": "name not found"}).encode())
                    return
                account = rec["account"]
            if not ACCOUNT_RE.match(account):
                self._send(400, json.dumps({"error": "account or name required"}).encode())
                return
            bal = db.get_balance(account)
            if not bal:
                from db import _account_balance, ROOT as DB_ROOT

                storage = Path(
                    os.environ.get(
                        "CNS_STORAGE_PATH",
                        str(DB_ROOT / "../cube/storage/signet/states"),
                    )
                )
                live = _account_balance(storage, account)
                bal = {"account": account, "balance": live, "updated_at": datetime.now(timezone.utc).isoformat()}
            self._send(200, json.dumps(bal).encode())
            return

        if path == "/api/treasury":
            self._send(200, json.dumps(load_treasury()).encode())
            return

        if path == "/api/contract-balance":
            db.sync_all()
            cid = manifest.get("contract_id", "").replace("0x", "")
            bal = db.get_balance(f"contract:{cid}")
            self._send(
                200,
                json.dumps(
                    {
                        "contract_id": manifest.get("contract_id"),
                        "balance": bal.get("balance"),
                        "updated_at": bal.get("updated_at"),
                    }
                ).encode(),
            )
            return

        self._send(404, b"Not found", "text/plain")

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        body = self._read_json()
        manifest = load_manifest()

        if path == "/api/sync":
            result = db.sync_all()
            self._send(200, json.dumps(result).encode())
            return

        if path == "/api/register":
            name = normalize_name(str(body.get("name", "")))
            account = str(body.get("account", "")).lower().replace("0x", "")
            if not NAME_RE.match(name) or not ACCOUNT_RE.match(account):
                self._send(400, json.dumps({"error": "invalid name or account"}).encode())
                return
            nh = name_hash_hex(name)
            entry = {
                "name": name,
                "name_hash": nh,
                "account": account,
                "submitted_at": datetime.now(timezone.utc).isoformat(),
                "confirmed": False,
            }
            save_labels_from_entry(entry)
            db.sync_all()
            hint = calldata_hint("register", manifest, name_hash=nh, account=account)
            self._send(200, json.dumps({"ok": True, "entry": entry, **hint}).encode())
            return

        if path == "/api/renew":
            name = normalize_name(str(body.get("name", "")))
            account = str(body.get("account", "")).lower().replace("0x", "")
            if not NAME_RE.match(name) or not ACCOUNT_RE.match(account):
                self._send(400, json.dumps({"error": "invalid name or account"}).encode())
                return
            nh = name_hash_hex(name)
            entry = {
                "name": name,
                "name_hash": nh,
                "account": account,
                "submitted_at": datetime.now(timezone.utc).isoformat(),
                "confirmed": False,
            }
            save_labels_from_entry(entry)
            db.sync_all()
            hint = calldata_hint("renew", manifest, name_hash=nh, account=account)
            self._send(200, json.dumps({"ok": True, "entry": entry, **hint}).encode())
            return

        if path == "/api/transfer":
            to_name = normalize_name(str(body.get("to_name", "")))
            amount = int(body.get("amount", 0))
            mode = str(body.get("mode", "cns")).lower()
            if not NAME_RE.match(to_name) or amount <= 0:
                self._send(400, json.dumps({"error": "invalid to_name or amount"}).encode())
                return
            db.sync_all()
            rec = db.find_by_name(to_name)
            if not rec:
                self._send(404, json.dumps({"error": "name not registered"}).encode())
                return
            to_account = rec["account"]
            nh = rec["name_hash"]
            tid = db.record_transfer(to_name, to_account, amount, note=mode)

            hints = {
                "ok": True,
                "transfer_id": tid,
                "to_name": to_name,
                "to_account": to_account,
                "amount": amount,
            }
            if mode == "cns":
                hints["cns_call"] = calldata_hint(
                    "xfer", manifest, name_hash=nh, amount=amount
                )
                hints["note"] = (
                    "xfer sends from CNS contract balance. Fund contract via deploy initial_balance + deposits."
                )
            else:
                hints["move_cli"] = f"move {amount} {to_account}"
                hints["note"] = "Account-to-account move from your Cube node account."

            self._send(200, json.dumps(hints).encode())
            return

        self._send(404, b"Not found", "text/plain")


def main() -> None:
    host = os.environ.get("CNS_HOST", "127.0.0.1")
    port = int(os.environ.get("CNS_PORT", "8780"))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    db.sync_all()
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"CNS UI http://{host}:{port}/")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
