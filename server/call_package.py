"""Build CNS register call payloads for Cube Call entries."""

from __future__ import annotations

import hashlib
from typing import Any


def normalize_name(name: str) -> str:
    n = name.strip().lower()
    if not n.endswith(".cube"):
        n = f"{n}.cube"
    return n


def name_hash_hex(name: str) -> str:
    return hashlib.sha256(normalize_name(name).encode("utf-8")).hexdigest()


def register_call_package(manifest: dict, name: str, account: str) -> dict[str, Any]:
    nh = name_hash_hex(name)
    acct = account.lower().replace("0x", "")
    methods = manifest.get("methods") or {}
    idx = methods.get("register", 0)
    cid = (manifest.get("contract_id") or "").replace("0x", "")
    handlers = manifest.get("handlers") or {}

    return {
        "entry_kind": "call",
        "contract_id": cid,
        "program_name": manifest.get("program_name", "cnsr"),
        "method": "register",
        "method_index": idx,
        "handler": handlers.get("register", "register(bytes32 name_hash, account)"),
        "calldata": {"name_hash": nh, "account": acct},
        "calldata_elements": [
            {"type": "bytes32", "value": nh},
            {"type": "account", "value": acct},
        ],
        "ops_budget": 2_000_000,
        "ops_price_ppm": 1000,
        "note": (
            "Submit this Call entry via your Cube Engine when Call TCP is enabled. "
            "Until then, the name stays pending in the CNS index after you save here."
        ),
    }
