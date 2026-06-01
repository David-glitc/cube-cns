#!/usr/bin/env python3
"""SQLite index for CNS — syncs labels, chain state, and balance cache."""

from __future__ import annotations

import json
import sqlite3
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "cns.db"
LABELS_FILE = DATA_DIR / "labels.json"
MANIFEST_FILE = ROOT / "artifacts" / "program.json"

SCHEMA = """
CREATE TABLE IF NOT EXISTS names (
    name_hash TEXT PRIMARY KEY,
    name TEXT,
    account TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'pending',
    confirmed INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transfers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    to_name TEXT NOT NULL,
    to_account TEXT,
    amount INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    note TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS balance_cache (
    account TEXT PRIMARY KEY,
    balance INTEGER,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_names_name ON names(name);
CREATE INDEX IF NOT EXISTS idx_transfers_to_name ON transfers(to_name);
"""


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_labels() -> list[dict]:
    if not LABELS_FILE.exists():
        return []
    return json.loads(LABELS_FILE.read_text(encoding="utf-8"))


def _contract_id_bytes(manifest: dict) -> bytes | None:
    cid = manifest.get("contract_id", "")
    if not cid:
        return None
    cid = cid.strip().removeprefix("0x")
    try:
        raw = bytes.fromhex(cid)
    except ValueError:
        return None
    return raw if len(raw) == 32 else None


def _scan_chain_records(contract_id: bytes, storage_path: Path) -> dict[str, str]:
    try:
        import sled  # type: ignore
    except ImportError:
        return {}

    db_path = storage_path
    if not db_path.exists():
        return {}
    db = sled.open(str(db_path))
    try:
        tree = db.open_tree(contract_id)
    except Exception:
        return {}

    out: dict[str, str] = {}
    for item in tree:
        if item is None:
            continue
        k, v = item
        out[k.hex()] = v.hex()
    return out


def _account_balance(storage_root: Path, account_hex: str) -> int | None:
    """Read account sat balance from Cube coin manager sled DB."""
    accounts_db = storage_root.parent / "coins" / "accounts"
    if not accounts_db.exists():
        return None
    try:
        import sled
    except ImportError:
        return None

    key = bytes.fromhex(account_hex.replace("0x", ""))
    if len(key) != 32:
        return None
    db = sled.open(str(accounts_db))
    try:
        tree = db.open_tree(key)
    except Exception:
        return None
    val = tree.get(bytes([0x00]))
    if val is None:
        return None
    raw = bytes(val)
    if len(raw) < 8:
        return None
    return struct.unpack("<Q", raw[:8])[0]


def _contract_balance(storage_root: Path, contract_id_hex: str) -> int | None:
    contracts_db = storage_root.parent / "coins" / "contracts"
    if not contracts_db.exists():
        return None
    try:
        import sled
    except ImportError:
        return None
    key = bytes.fromhex(contract_id_hex.replace("0x", ""))
    if len(key) != 32:
        return None
    db = sled.open(str(contracts_db))
    try:
        tree = db.open_tree(key)
    except Exception:
        return None
    val = tree.get(bytes([0x00]))
    if val is None:
        return None
    raw = bytes(val)
    if len(raw) < 8:
        return None
    return struct.unpack("<Q", raw[:8])[0]


def sync_all(
    storage_path: str | None = None,
    labels_path: Path | None = None,
) -> dict[str, Any]:
    """Sync chain state + labels into SQLite."""
    storage = Path(
        storage_path
        or __import__("os").environ.get(
            "CNS_STORAGE_PATH", str(ROOT / "../cube/storage/signet/states")
        )
    )
    manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8")) if MANIFEST_FILE.exists() else {}
    contract_id = _contract_id_bytes(manifest)
    chain_map = _scan_chain_records(contract_id, storage) if contract_id else {}

    labels = _read_labels()
    if labels_path and labels_path.exists():
        labels = json.loads(labels_path.read_text(encoding="utf-8"))

    conn = connect()
    now = _now()
    synced = 0

    label_by_hash = {e["name_hash"].lower(): e for e in labels}

    for nh, account in chain_map.items():
        label = label_by_hash.get(nh.lower())
        conn.execute(
            """
            INSERT INTO names (name_hash, name, account, source, confirmed, updated_at)
            VALUES (?, ?, ?, 'chain', 1, ?)
            ON CONFLICT(name_hash) DO UPDATE SET
                account=excluded.account,
                source='chain',
                confirmed=1,
                name=COALESCE(excluded.name, names.name),
                updated_at=excluded.updated_at
            """,
            (nh, label["name"] if label else None, account, now),
        )
        synced += 1
        bal = _account_balance(storage, account)
        if bal is not None:
            conn.execute(
                """
                INSERT INTO balance_cache (account, balance, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(account) DO UPDATE SET balance=excluded.balance, updated_at=excluded.updated_at
                """,
                (account, bal, now),
            )

    for entry in labels:
        nh = entry["name_hash"]
        on_chain = nh.lower() in {k.lower() for k in chain_map}
        conn.execute(
            """
            INSERT INTO names (name_hash, name, account, source, confirmed, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(name_hash) DO UPDATE SET
                name=excluded.name,
                account=excluded.account,
                source=excluded.source,
                confirmed=excluded.confirmed,
                updated_at=excluded.updated_at
            """,
            (
                nh,
                entry.get("name"),
                entry["account"],
                "chain" if on_chain else "pending",
                1 if on_chain else 0,
                now,
            ),
        )

    cid_hex = manifest.get("contract_id", "").replace("0x", "")
    if cid_hex:
        cb = _contract_balance(storage, cid_hex)
        if cb is not None:
            conn.execute(
                """
                INSERT INTO balance_cache (account, balance, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(account) DO UPDATE SET balance=excluded.balance, updated_at=excluded.updated_at
                """,
                (f"contract:{cid_hex}", cb, now),
            )

    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM names").fetchone()[0]
    conn.close()

    # also write legacy index.json for compatibility
    records = []
    conn = connect()
    for row in conn.execute("SELECT * FROM names ORDER BY name_hash"):
        records.append(dict(row))
    conn.close()
    index = {
        "updated_at": now,
        "contract_id": manifest.get("contract_id"),
        "records": [
            {
                "name_hash": r["name_hash"],
                "name": r["name"],
                "account": r["account"],
                "source": r["source"],
            }
            for r in records
        ],
    }
    (DATA_DIR / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")

    return {"ok": True, "synced_chain": synced, "total_names": count, "updated_at": now}


def get_name(name_hash: str) -> dict | None:
    conn = connect()
    row = conn.execute(
        "SELECT * FROM names WHERE name_hash = ?", (name_hash.lower(),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def find_by_name(name: str) -> dict | None:
    import hashlib

    conn = connect()
    row = conn.execute(
        "SELECT * FROM names WHERE name = ? COLLATE NOCASE", (name.lower(),)
    ).fetchone()
    if not row:
        nh = hashlib.sha256(name.lower().encode("utf-8")).hexdigest()
        row = conn.execute("SELECT * FROM names WHERE name_hash = ?", (nh,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_names() -> list[dict]:
    conn = connect()
    rows = [dict(r) for r in conn.execute("SELECT * FROM names ORDER BY name")]
    conn.close()
    return rows


def get_balance(account: str) -> dict:
    conn = connect()
    row = conn.execute(
        "SELECT * FROM balance_cache WHERE account = ?", (account.replace("0x", ""),)
    ).fetchone()
    conn.close()
    return dict(row) if row else {}


def record_transfer(to_name: str, to_account: str | None, amount: int, note: str = "") -> int:
    conn = connect()
    cur = conn.execute(
        """
        INSERT INTO transfers (to_name, to_account, amount, status, note, created_at)
        VALUES (?, ?, ?, 'pending', ?, ?)
        """,
        (to_name, to_account, amount, note, _now()),
    )
    conn.commit()
    tid = cur.lastrowid
    conn.close()
    return tid or 0


if __name__ == "__main__":
    import os

    result = sync_all(os.environ.get("CNS_STORAGE_PATH"))
    print(json.dumps(result, indent=2))
