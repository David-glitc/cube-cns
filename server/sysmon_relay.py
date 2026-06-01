"""Proxy Cube node operations to SysMon (private VPS)."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from cube_commands import parse_output_events

SYSMON_URL = os.environ.get("CNS_SYSMON_URL", "http://127.0.0.1:8765").rstrip("/")
SYSMON_TOKEN = os.environ.get("CNS_SYSMON_TOKEN", "").strip()
SYSMON_HOST = os.environ.get("CNS_SYSMON_HOST", "127.0.0.1").strip()


def configured() -> bool:
    return bool(SYSMON_URL and SYSMON_TOKEN)


def _request(method: str, path: str, body: dict | None = None) -> dict[str, Any]:
    if not configured():
        return {
            "ok": False,
            "error": "SysMon relay not configured (set CNS_SYSMON_URL and CNS_SYSMON_TOKEN on the server).",
        }
    url = SYSMON_URL + path
    data = None
    headers = {
        "Authorization": f"Bearer {SYSMON_TOKEN}",
        "Accept": "application/json",
        "Host": SYSMON_HOST,
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            if not raw:
                return {"ok": True}
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8"))
        except (json.JSONDecodeError, OSError):
            detail = {"error": exc.reason or str(exc)}
        return {"ok": False, "status": exc.code, **detail}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def cube_status() -> dict[str, Any]:
    return _request("GET", "/api/cube/status")


def cube_command(action: str, params: dict | None = None) -> dict[str, Any]:
    return _request(
        "POST",
        "/api/cube/command",
        {"action": action, "params": params or {}},
    )


def cube_session_output(since: int = 0) -> dict[str, Any]:
    qs = urllib.parse.urlencode({"since": since})
    return _request("GET", f"/api/cube/session/output?{qs}")


def exec_cli_action(action: str, params: dict | None = None, wait_ms: int = 800) -> dict[str, Any]:
    """Send a whitelisted action to the Cube session and return parsed activity."""
    status = cube_status()
    if not status.get("ok", True) and status.get("error"):
        return status
    if not status.get("attached") and not status.get("running"):
        return {
            "ok": False,
            "error": "Cube node is not running in SysMon. Open SysMon → Cube → Start node.",
            "status": status,
        }
    since = int(status.get("seq") or 0)
    sent = cube_command(action, params)
    if not sent.get("ok", True) and sent.get("error"):
        return sent
    time.sleep(max(wait_ms, 100) / 1000.0)
    out = cube_session_output(since=since)
    events = list(sent.get("events") or [])
    events.extend(out.get("events") or [])
    if not events and out.get("output"):
        events = parse_output_events(str(out["output"]))
    return {
        "ok": sent.get("ok", True) and out.get("ok", True),
        "action": action,
        "input": sent,
        "events": events,
        "output": out,
    }
