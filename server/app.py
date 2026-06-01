#!/usr/bin/env python3
"""CNS API — registration, transfer, balances, SQLite sync."""

from __future__ import annotations

import hashlib
import ipaddress
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


def load_json(path: Path, default: dict | None = None) -> dict:
    if not path.exists():
        return default or {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_treasury() -> dict:
    return load_json(TREASURY_PUBLIC, {})

sys.path.insert(0, str(ROOT / "server"))
import call_package  # noqa: E402
import db  # noqa: E402
import sysmon_relay  # noqa: E402
import wallet  # noqa: E402

CUBE_RELAY = os.environ.get("CNS_CUBE_RELAY", "0") == "1"
NODE_RELAY_ENABLED = os.environ.get("CNS_NODE_RELAY", "1") == "1"

NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z][a-z0-9-]{0,15})?$")
ACCOUNT_RE = re.compile(r"^[0-9a-fA-F]{64}$")

_PUBLIC_HOST = os.environ.get("CNS_PUBLIC_HOST", "").strip().lower()
_DEFAULT_HOSTS = (
    f"{_PUBLIC_HOST},localhost,127.0.0.1" if _PUBLIC_HOST else "localhost,127.0.0.1"
)
ALLOWED_HOSTS = {
    h.strip().lower()
    for h in os.environ.get("CNS_ALLOWED_HOSTS", _DEFAULT_HOSTS).split(",")
    if h.strip()
}
ALLOWED_IPS = {
    ip.strip()
    for ip in os.environ.get("CNS_ALLOWED_IPS", "127.0.0.1,::1,10.0.0.0/8").split(",")
    if ip.strip() and "/" not in ip.strip()
}
ALLOWED_NETWORKS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = tuple(
    ipaddress.ip_network(entry.strip(), strict=False)
    for entry in os.environ.get("CNS_ALLOWED_IPS", "127.0.0.1,::1,10.0.0.0/8").split(",")
    if entry.strip() and "/" in entry.strip()
)
BLOCK_PUBLIC = os.environ.get("CNS_BLOCK_PUBLIC", "1") == "1"


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


def _node_relay_allowed(handler: BaseHTTPRequestHandler) -> bool:
    if not NODE_RELAY_ENABLED or not sysmon_relay.configured():
        return False
    if os.environ.get("CNS_NODE_RELAY_PUBLIC", "0") == "1":
        return True
    peer = handler._peer_ip()
    if peer in ("127.0.0.1", "::1"):
        return True
    try:
        addr = ipaddress.ip_address(peer)
        return addr.is_private or addr.is_loopback
    except ValueError:
        return False


def onchain_register_guide(manifest: dict) -> dict:
    account = "4bcde3e947f2d0b0269427041b0bb62002fe8803b2f60917402003ac7d70aad6"
    names = ["david.cube", "satoshi.cube"]
    entries = []
    for name in names:
        nh = name_hash_hex(name)
        entries.append(
            {
                "name": name,
                "name_hash": nh,
                "account": account,
                "call_package": call_package.register_call_package(manifest, name, account),
            }
        )
    deploy = manifest.get("deploy_example", "")
    return {
        "account": account,
        "names": entries,
        "contract_id": manifest.get("contract_id"),
        "deploy_example": deploy,
        "blocker": (
            "Cube Signet has no `call` CLI or Call TCP protocol yet. "
            "You can deploy the CNS contract and fund your account from SysMon; "
            "on-chain register() will work once Cube ships Call submission."
        ),
        "sysmon_steps": [
            "Open SysMon (monitor.chessonchain.online) → Cube terminal.",
            "Start node with the nsec for account 4bcde3e9…aad6 (must match david/satoshi owner).",
            "Wait for: Syncing complete.",
            "coins — confirm balance (need sats for deploy + future register fees).",
            f"If CNS not deployed: {deploy}",
            "After Cube adds `call`: submit register for each name_hash (see call_package in TheBox Register).",
            "In TheBox: Sync index — names show on-chain.",
        ],
    }


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

    def _peer_ip(self) -> str:
        return self.client_address[0]

    def _host_allowed(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0].lower()
        if not host or not ALLOWED_HOSTS:
            return True
        return host in ALLOWED_HOSTS

    def _ip_allowed(self) -> bool:
        if not ALLOWED_IPS and not ALLOWED_NETWORKS and not BLOCK_PUBLIC:
            return True
        peer = self._peer_ip()
        if peer in ALLOWED_IPS:
            return True
        try:
            addr = ipaddress.ip_address(peer)
        except ValueError:
            return False
        for network in ALLOWED_NETWORKS:
            if addr in network:
                return True
        if BLOCK_PUBLIC and not (addr.is_private or addr.is_loopback):
            return False
        return not BLOCK_PUBLIC

    def _request_allowed(self) -> bool:
        if not self._host_allowed():
            self._send(403, b"Forbidden host", "text/plain")
            return False
        if not self._ip_allowed():
            self._send(403, b"Forbidden", "text/plain")
            return False
        return True

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

    def _public_asset_paths(self) -> tuple[str, ...]:
        return (
            "/",
            "/index.html",
            "/docs",
            "/docs.html",
            "/docs/",
            "/favicon.ico",
            "/robots.txt",
        )

    def do_HEAD(self) -> None:
        if not self._request_allowed():
            return
        path = urlparse(self.path).path
        if path.startswith("/static/") or path in self._public_asset_paths():
            self.send_response(200)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if path.startswith("/raw/docs/") or path.startswith("/docs/"):
            self.send_response(200)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if path.startswith("/api/"):
            self.send_response(200)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()

    def do_OPTIONS(self) -> None:
        if not self._request_allowed():
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        if not self._request_allowed():
            return
        path = urlparse(self.path).path
        if path.startswith("/static/"):
            rel = path.removeprefix("/static/")
            file_path = (UI_DIR / "static" / rel).resolve()
            if not str(file_path).startswith(str((UI_DIR / "static").resolve())):
                self._send(403, b"Forbidden", "text/plain")
                return
            if file_path.is_file():
                if rel.endswith(".css"):
                    ctype = "text/css; charset=utf-8"
                elif rel.endswith(".js"):
                    ctype = "application/javascript; charset=utf-8"
                elif rel.endswith(".svg"):
                    ctype = "image/svg+xml"
                elif rel.endswith(".png"):
                    ctype = "image/png"
                elif rel.endswith(".ico"):
                    ctype = "image/x-icon"
                elif rel.endswith(".webmanifest"):
                    ctype = "application/manifest+json"
                else:
                    ctype = "application/octet-stream"
                self._send(200, file_path.read_bytes(), ctype)
                return
            self._send(404, b"Not found", "text/plain")
            return

        if path == "/favicon.ico":
            fav = UI_DIR / "static" / "favicon.svg"
            if fav.is_file():
                self._send(200, fav.read_bytes(), "image/svg+xml")
                return
            self._send(404, b"Not found", "text/plain")
            return

        if path in ("/", "/index.html"):
            self._send(200, (UI_DIR / "index.html").read_bytes(), "text/html; charset=utf-8")
            return

        if path in ("/docs", "/docs/", "/docs.html"):
            doc_page = UI_DIR / "docs.html"
            if doc_page.is_file():
                self._send(200, doc_page.read_bytes(), "text/html; charset=utf-8")
                return
            self._send(404, b"docs page missing", "text/plain")
            return

        if path.startswith("/raw/docs/"):
            rel = path.removeprefix("/raw/docs/")
            doc_path = (ROOT / "docs" / rel).resolve()
            if not str(doc_path).startswith(str((ROOT / "docs").resolve())):
                self._send(403, b"Forbidden", "text/plain")
                return
            if doc_path.is_file():
                ctype = "text/markdown; charset=utf-8"
                if rel.endswith(".json"):
                    ctype = "application/json; charset=utf-8"
                self._send(200, doc_path.read_bytes(), ctype)
                return
            self._send(404, b"Not found", "text/plain")
            return

        if path.startswith("/docs/"):
            rel = path.removeprefix("/docs/")
            doc_path = (ROOT / "docs" / rel).resolve()
            if not str(doc_path).startswith(str((ROOT / "docs").resolve())):
                self._send(403, b"Forbidden", "text/plain")
                return
            if doc_path.is_file() and rel.endswith(".md"):
                body = doc_path.read_bytes()
                html = (
                    b"<!DOCTYPE html><html><head><meta charset=utf-8>"
                    b'<meta http-equiv="refresh" content="0;url=/docs"></head><body>'
                    b'<p>Redirecting to <a href="/docs">documentation</a>.</p></body></html>'
                )
                self._send(200, html, "text/html; charset=utf-8")
                return
            self._send(404, b"Not found", "text/plain")
            return

        manifest = load_manifest()

        if path == "/api/node/status":
            if not _node_relay_allowed(self):
                self._send(
                    503,
                    json.dumps(
                        {
                            "ok": False,
                            "error": "Node relay unavailable (configure CNS_SYSMON_URL + CNS_SYSMON_TOKEN on server).",
                            "configured": sysmon_relay.configured(),
                        }
                    ).encode(),
                )
                return
            result = sysmon_relay.cube_status()
            self._send(200, json.dumps(result).encode())
            return

        if path == "/api/onchain/guide":
            self._send(200, json.dumps(onchain_register_guide(load_manifest())).encode())
            return

        if path == "/api/contract":
            db.sync_all()
            cid = manifest.get("contract_id", "").replace("0x", "")
            bal = db.get_balance(f"contract:{cid}")
            self._send(
                200,
                json.dumps(
                    {
                        "program_name": manifest.get("program_name", "cnsr"),
                        "contract_id": manifest.get("contract_id"),
                        "methods": manifest.get("methods", {}),
                        "handlers": manifest.get("handlers", {}),
                        "deploy_example": manifest.get("deploy_example"),
                        "balance": bal.get("balance"),
                        "balance_updated_at": bal.get("updated_at"),
                        "relay_enabled": CUBE_RELAY,
                    }
                ).encode(),
            )
            return

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

        if path == "/api/network":
            self._send(
                200,
                json.dumps(
                    {
                        "brand": "TheBox CNS",
                        "network": os.environ.get("CNS_NETWORK", "signet"),
                        "chain": "cube-signet",
                        "public_host": os.environ.get("CNS_PUBLIC_HOST", ""),
                        "btc_wallet_note": (
                            "Browser BTC wallets do not control Cube accounts. "
                            "Use Create identity or paste nsec / 64-char account hex."
                        ),
                    }
                ).encode(),
            )
            return

        if path == "/api/availability":
            qs = parse_qs(urlparse(self.path).query)
            name = normalize_name((qs.get("name") or [""])[0])
            if not name:
                self._send(400, json.dumps({"error": "name required"}).encode())
                return
            if not NAME_RE.match(name):
                self._send(400, json.dumps({"error": "invalid name"}).encode())
                return
            if not name.endswith(".cube"):
                name = f"{name}.cube"
            db.sync_all()
            rec = db.find_by_name(name)
            available = rec is None
            self._send(
                200,
                json.dumps(
                    {
                        "name": name,
                        "available": available,
                        "registered": rec is not None,
                        "confirmed": bool(rec and rec.get("confirmed")),
                        "record": rec,
                    }
                ).encode(),
            )
            return

        if path == "/api/activity":
            qs = parse_qs(urlparse(self.path).query)
            account = (qs.get("account") or [""])[0].lower().replace("0x", "")
            limit = min(int((qs.get("limit") or ["20"])[0]), 50)
            if account and ACCOUNT_RE.match(account):
                rows = db.list_activity_for_account(account, limit)
            else:
                rows = [
                    {
                        "kind": "transfer",
                        "to_name": r.get("to_name"),
                        "amount": r.get("amount"),
                        "status": r.get("status"),
                        "note": r.get("note"),
                        "created_at": r.get("created_at"),
                    }
                    for r in db.list_transfers(limit)
                ]
            self._send(200, json.dumps({"records": rows}).encode())
            return

        if path == "/api/onboarding":
            treasury = load_treasury()
            signet = treasury.get("donations", {}).get("signet", {})
            mainnet = treasury.get("donations", {}).get("mainnet", {})
            self._send(
                200,
                json.dumps(
                    {
                        "network": os.environ.get("CNS_NETWORK", "signet"),
                        "treasury_signet_btc": signet.get("btc", ""),
                        "treasury_mainnet_btc": mainnet.get("btc", ""),
                        "registration_fee_note": (
                            "Registering a .cube name requires sats on your Cube Signet account "
                            "for the on-chain Call. Name fees and contract funding support the "
                            "CNS treasury on Signet; Bitcoin mainnet donations support development."
                        ),
                        "steps": [
                            {
                                "title": "Cube node",
                                "body": "Install and run Cube on Signet on your own machine or VPS.",
                                "url": "https://github.com/cube-btc/cube",
                            },
                            {
                                "title": "Signet BTC",
                                "body": "Fund your node's Bitcoin Signet wallet (faucet or send test coins).",
                                "url": "https://en.bitcoin.it/wiki/Signet",
                            },
                            {
                                "title": "Onboard coins to your account",
                                "body": "On the Cube CLI: liftaddr <your_64_char_account_hex> then liftup <sats>.",
                                "commands": ["liftaddr <account_hex>", "liftup 5000"],
                            },
                            {
                                "title": "Register on-chain",
                                "body": "When Cube Call entries work, submit register(name_hash, account) to the CNS contract.",
                                "url": None,
                            },
                        ],
                    }
                ).encode(),
            )
            return

        if path == "/api/my-names":
            qs = parse_qs(urlparse(self.path).query)
            account = (qs.get("account") or [""])[0].lower().replace("0x", "")
            if not ACCOUNT_RE.match(account):
                self._send(400, json.dumps({"error": "account required"}).encode())
                return
            db.sync_all()
            rows = db.list_names_for_account(account)
            for rec in rows:
                bal = db.get_balance(rec["account"])
                rec["balance"] = bal.get("balance")
            self._send(200, json.dumps({"records": rows}).encode())
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
        if not self._request_allowed():
            return
        path = urlparse(self.path).path
        body = self._read_json()

        if path == "/api/wallet/generate":
            try:
                self._send(200, json.dumps(wallet.generate_identity()).encode())
            except Exception as exc:
                self._send(500, json.dumps({"ok": False, "error": str(exc)}).encode())
            return

        if path == "/api/wallet/resolve":
            raw = str(body.get("input", body.get("paste", "")))
            self._send(200, json.dumps(wallet.resolve_paste(raw)).encode())
            return

        manifest = load_manifest()

        if path == "/api/sync":
            result = db.sync_all()
            self._send(200, json.dumps(result).encode())
            return

        if path == "/api/node/exec":
            if not _node_relay_allowed(self):
                self._send(503, json.dumps({"ok": False, "error": "Node relay not allowed"}).encode())
                return
            if body.get("line"):
                self._send(
                    400,
                    json.dumps({"ok": False, "error": "raw line disabled — send action and optional params"}).encode(),
                )
                return
            action = str(body.get("action", "")).strip().lower()
            if not action:
                self._send(400, json.dumps({"ok": False, "error": "action required"}).encode())
                return
            params = body.get("params") if isinstance(body.get("params"), dict) else {}
            wait_ms = min(int(body.get("wait_ms", 1200)), 10000)
            if action.startswith("deploy"):
                wait_ms = max(wait_ms, 3000)
            result = sysmon_relay.exec_cli_action(action, params=params, wait_ms=wait_ms)
            self._send(200, json.dumps(result).encode())
            return

        if path == "/api/node/cns/deploy":
            if not _node_relay_allowed(self):
                self._send(503, json.dumps({"ok": False, "error": "Node relay not allowed"}).encode())
                return
            result = sysmon_relay.exec_cli_action("deploy_cns", params={}, wait_ms=4000)
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
            db.record_registration(name, account, status="pending")
            hint = calldata_hint("register", manifest, name_hash=nh, account=account)
            pkg = call_package.register_call_package(manifest, name, account)
            treasury = load_treasury()
            signet_btc = treasury.get("donations", {}).get("signet", {}).get("btc", "")
            self._send(
                200,
                json.dumps(
                    {
                        "ok": True,
                        "entry": entry,
                        **hint,
                        "call_package": pkg,
                        "status": "pending",
                        "next_steps": [
                            "Fund your Cube account on Signet (liftaddr / liftup on your node).",
                            "Sign & submit the register Call (button on Register page).",
                            "Sync index here after confirmation — status becomes on-chain.",
                        ],
                        "treasury_signet_btc": signet_btc,
                    }
                ).encode(),
            )
            return

        if path == "/api/register/call-package":
            name = normalize_name(str(body.get("name", "")))
            account = str(body.get("account", "")).lower().replace("0x", "")
            if not NAME_RE.match(name) or not ACCOUNT_RE.match(account):
                self._send(400, json.dumps({"error": "invalid name or account"}).encode())
                return
            pkg = call_package.register_call_package(manifest, name, account)
            self._send(200, json.dumps({"ok": True, "call_package": pkg}).encode())
            return

        if path == "/api/register/submit":
            name = normalize_name(str(body.get("name", "")))
            account = str(body.get("account", "")).lower().replace("0x", "")
            nsec = str(body.get("nsec", "")).strip()
            if not NAME_RE.match(name) or not ACCOUNT_RE.match(account):
                self._send(400, json.dumps({"error": "invalid name or account"}).encode())
                return
            if nsec:
                resolved = wallet.resolve_paste(nsec)
                if not resolved.get("ok"):
                    self._send(400, json.dumps(resolved).encode())
                    return
                if resolved["account"] != account:
                    self._send(
                        400,
                        json.dumps({"error": "nsec does not match the active account"}).encode(),
                    )
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
            db.record_registration(name, account, status="pending")
            db.sync_all()
            pkg = call_package.register_call_package(manifest, name, account)
            relay_result: dict = {
                "ok": False,
                "error": (
                    "On-chain Call submit is not wired on this server yet "
                    "(Cube Engine Call TCP has no public CLI). "
                    "Your name is saved as pending; copy the call package to your node."
                ),
            }
            if CUBE_RELAY:
                try:
                    import cube_ops  # noqa: E402

                    relay_result = cube_ops.try_submit_register_call(pkg, nsec)
                except Exception as exc:
                    relay_result = {"ok": False, "error": str(exc)}
            self._send(
                200,
                json.dumps(
                    {
                        "ok": True,
                        "indexed": True,
                        "on_chain": relay_result.get("ok", False),
                        "relay": relay_result,
                        "call_package": pkg,
                        "entry": entry,
                    }
                ).encode(),
            )
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
    public = os.environ.get("CNS_PUBLIC_HOST", "")
    print(f"CNS UI http://{host}:{port}/")
    if public:
        print(f"  Public URL:  https://{public}/")
    print(f"  Allowed hosts: {', '.join(sorted(ALLOWED_HOSTS))}")
    print(f"  Block public :{port}: {BLOCK_PUBLIC}")
    httpd.serve_forever()


if __name__ == "__main__":
    main()
