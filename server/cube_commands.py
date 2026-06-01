"""Whitelisted Cube node commands (shared rules with SysMon)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

HEX64_RE = re.compile(r"^[0-9a-fA-F]{64}$")
HEX_RE = re.compile(r"^0x[0-9a-fA-F]+$")
UINT_RE = re.compile(r"^[0-9]{1,10}$")

CUBE_FORBIDDEN = frozenset(";|&$`<>\n\r")

ALLOWED_ACTIONS = frozenset(
    {
        "coins",
        "liftaddr",
        "liftup",
        "lifts",
        "tip",
        "rootaccount",
        "conn",
        "ping",
        "move",
        "deploy",
        "deploy_cns",
        "deploy_hello",
        "print_registery",
    }
)

CUBE_ONESHOT_ACTIONS = frozenset({"gensec", "genesis_signet", "test"})


def _check_chars(s: str) -> str | None:
    if any(ch in s for ch in CUBE_FORBIDDEN):
        return "invalid characters"
    return None


def _hex64(val: str, field: str) -> tuple[str | None, str | None]:
    h = (val or "").strip().lower().replace("0x", "")
    if not HEX64_RE.match(h):
        return None, f"{field} must be 64 hex characters"
    return h, None


def _program_hex(val: str) -> tuple[str | None, str | None]:
    s = (val or "").strip()
    if err := _check_chars(s):
        return None, err
    if not HEX_RE.match(s) or len(s) < 10:
        return None, "program must be 0x… hex"
    return s, None


def _amount(val: str) -> tuple[str | None, str | None]:
    s = (val or "").strip()
    if not UINT_RE.match(s):
        return None, "amount must be a positive integer (sats)"
    if int(s) <= 0:
        return None, "amount must be greater than 0"
    return s, None


def load_cns_deploy_line(manifest_path: Path | None = None) -> str:
    manifest = manifest_path or Path(__file__).resolve().parent.parent / "artifacts" / "program.json"
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            line = data.get("deploy_example")
            if isinstance(line, str) and line.strip():
                return line.strip()
        except (json.JSONDecodeError, OSError):
            pass
    return (
        "deploy 5000 0x04636e737200060872656769737265720002071f0504007ccd6165077265736f6c76650001071f0400ce6161650572656e65770002071f0504007ccd616504786665720002071f0208007c6bce6c51cc61650762616c6e616d650001071f0400ce51ca650773656c6662616c00000400cb616165"
    )


def build_action(action: str, params: dict[str, Any] | None = None) -> tuple[str | None, str | None]:
    params = params or {}
    act = (action or "").strip().lower()
    if act not in ALLOWED_ACTIONS and act not in CUBE_ONESHOT_ACTIONS:
        return None, f"unknown action: {act}"

    if act == "gensec":
        return "gensec", None
    if act == "test":
        return "test", None
    if act == "genesis_signet":
        return "genesis signet", None

    if act in ("liftaddr", "liftup", "lifts", "tip", "rootaccount", "conn", "ping", "print_registery"):
        if params:
            return None, f"{act} takes no parameters"
        if act == "print_registery":
            return "print registery", None
        return act, None

    if act == "coins":
        acct = params.get("account")
        if not acct:
            return "coins", None
        h, err = _hex64(str(acct), "account")
        if err:
            return None, err
        return f"coins {h}", None

    if act == "move":
        amt, err = _amount(str(params.get("amount", "")))
        if err:
            return None, err
        acct, err = _hex64(str(params.get("to_account", "")), "to_account")
        if err:
            return None, err
        return f"move {amt} {acct}", None

    if act == "deploy":
        amt, err = _amount(str(params.get("amount", "")))
        if err:
            return None, err
        prog, err = _program_hex(str(params.get("program_hex", "")))
        if err:
            return None, err
        return f"deploy {amt} {prog}", None

    if act == "deploy_cns":
        line = load_cns_deploy_line()
        if params.get("amount"):
            amt, err = _amount(str(params["amount"]))
            if err:
                return None, err
            parts = line.split(maxsplit=2)
            if len(parts) >= 3:
                return f"deploy {amt} {parts[2]}", None
        return line, None

    if act == "deploy_hello":
        amt = "1000"
        if params.get("amount"):
            amt, err = _amount(str(params["amount"]))
            if err:
                return None, err
        return f"deploy {amt} 0x0464656d6f00010268690000040051515165", None

    return None, f"unhandled action: {act}"


def validate_built_line(line: str) -> str | None:
    if err := _check_chars(line):
        return err
    parts = line.strip().split()
    if not parts:
        return "empty command"
    return None


def parse_output_events(chunk: str) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    if not chunk:
        return events
    for raw_line in chunk.splitlines():
        line = raw_line.strip()
        if not line or "Enter nsec:" in line:
            continue
        if line.startswith("[sysmon]"):
            events.append({"kind": "info", "message": line.replace("[sysmon]", "").strip() or "system"})
            continue
        low = line.lower()
        if "syncing complete" in low:
            events.append({"kind": "ok", "message": "Cube node synced — ready for commands"})
        elif "successfully executed" in low:
            events.append({"kind": "ok", "message": "Command completed successfully"})
        elif "insufficient" in low and "balance" in low:
            events.append({"kind": "err", "message": "Insufficient balance"})
        elif line.startswith("Error") or " error:" in low:
            events.append({"kind": "err", "message": line[:160]})
    return events
