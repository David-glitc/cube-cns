"""Cube Signet node control for TheBox CNS (local VPS only)."""

from __future__ import annotations

import base64
import json
import os
import re
import signal
import subprocess
import threading
import time
import urllib.request
from collections import deque
from pathlib import Path

CUBE_ROOT = Path(os.environ.get("CUBE_ROOT", "/home/david/cube"))
CUBE_SCRIPT = os.environ.get("CNS_CUBE_SCRIPT", str(CUBE_ROOT / "run-cube.sh")).strip()
CUBE_NSEC = os.environ.get("CNS_CUBE_NSEC", "").strip()
CUBE_NODE_ARGS = os.environ.get(
    "CNS_CUBE_NODE_ARGS",
    "pruned signet node http://127.0.0.1:38332 cube cube true",
).strip()
CUBE_CMD_TIMEOUT = int(os.environ.get("CNS_CUBE_CMD_TIMEOUT", "600"))
CUBE_BITCOIND_RPC = os.environ.get("CNS_CUBE_BITCOIND_RPC", "http://127.0.0.1:38332").strip()
CUBE_BITCOIND_USER = os.environ.get("CNS_CUBE_BITCOIND_USER", "cube").strip()
CUBE_BITCOIND_PASS = os.environ.get("CNS_CUBE_BITCOIND_PASS", "cube").strip()
CUBE_BITCOIND_CONTAINER = os.environ.get(
    "CNS_CUBE_BITCOIND_CONTAINER", "cube-bitcoind-signet"
).strip()
CUBE_SEEDS_DIR = os.environ.get("CNS_CUBE_SEEDS_DIR", str(CUBE_ROOT / "data/seeds")).strip()
NSEC_PATTERN = re.compile(r"nsec1[a-z0-9]+")
CNS_ARTIFACTS = Path(__file__).resolve().parent.parent / "artifacts"

CUBE_ONESHOT = {
    "gensec": 0,
    "test": 0,
    "genesis": 1,
}

CUBE_NODE_COMMANDS = frozenset(
    {
        "deploy",
        "move",
        "liftup",
        "liftaddr",
        "lifts",
        "coins",
        "tip",
        "comp",
        "decompile",
        "config",
        "conn",
        "ping",
        "npub",
        "clear",
        "rootaccount",
        "engine",
        "print",
        "batchrecord",
        "liftuplocal",
        "swapout",
        "account",
        "contract",
        "exit",
        "runexplorer",
        "registery",
        "coinmanager",
        "flamemanager",
    }
)

CUBE_FORBIDDEN = frozenset(";|&$`<>")


def try_submit_register_call(call_package: dict, nsec: str = "") -> dict:
    """Attempt on-chain register via local Cube node (optional relay)."""
    if not _cube_script_ok():
        return {
            "ok": False,
            "error": "Cube node script not configured on this server (CNS_CUBE_SCRIPT).",
        }
    st = _cube_session.status()
    if not st.get("running"):
        return {
            "ok": False,
            "error": (
                "Cube node is not running on this server. "
                "Copy the call package to your own Cube node instead."
            ),
        }
    return {
        "ok": False,
        "error": (
            "Cube Engine does not expose a Call CLI/TCP hook yet. "
            "Your registration is indexed as pending; submit the call package "
            "from your node when Call entries are supported."
        ),
        "call_package": call_package,
        "node_running": True,
    }


def _cube_script_ok() -> bool:
    return bool(CUBE_SCRIPT) and Path(CUBE_SCRIPT).is_file()


def _cube_split_line(line: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    quote: str | None = None
    for ch in line.strip():
        if quote:
            if ch == quote:
                quote = None
            else:
                current.append(ch)
            continue
        if ch in "\"'":
            quote = ch
            continue
        if ch.isspace():
            if current:
                parts.append("".join(current))
                current = []
            continue
        current.append(ch)
    if current:
        parts.append("".join(current))
    return parts


def validate_cube_oneshot(args: list[str]) -> str | None:
    if not args:
        return "empty command"
    if any(ch in arg for arg in args for ch in CUBE_FORBIDDEN):
        return "invalid characters in command"
    if any("\n" in arg or "\r" in arg for arg in args):
        return "invalid characters in command"
    cmd = args[0].lower()
    if cmd not in CUBE_ONESHOT:
        return f"one-shot command not allowed: {cmd}"
    expected = CUBE_ONESHOT[cmd]
    if len(args) - 1 != expected:
        return f"usage: {cmd}" + (" <chain>" if cmd == "genesis" else "")
    if cmd == "genesis" and args[1].lower() not in ("signet", "mainnet", "testbed"):
        return "genesis chain must be signet, mainnet, or testbed"
    return None


def validate_cube_session_line(line: str) -> str | None:
    stripped = line.strip()
    if not stripped:
        return "empty command"
    if any(ch in stripped for ch in CUBE_FORBIDDEN):
        return "invalid characters in command"
    if "\n" in stripped or "\r" in stripped:
        return "invalid characters in command"
    parts = _cube_split_line(stripped)
    if not parts:
        return "empty command"
    if parts[0].lower() not in CUBE_NODE_COMMANDS:
        return f"node command not allowed: {parts[0]}"
    return None


CUBE_NODE_PGREP = r"target/debug/cube pruned signet node"


def cube_node_pids() -> list[int]:
    try:
        out = subprocess.check_output(
            ["pgrep", "-f", CUBE_NODE_PGREP],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return [int(pid) for pid in out.split() if pid.strip().isdigit()]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


def stop_cube_node_processes() -> list[int]:
    stopped: list[int] = []
    for pid in cube_node_pids():
        try:
            os.kill(pid, signal.SIGTERM)
            stopped.append(pid)
        except OSError:
            continue
    return stopped


def run_cube_oneshot(args: list[str]) -> dict:
    err = validate_cube_oneshot(args)
    if err:
        return {"ok": False, "error": err}
    if not _cube_script_ok():
        return {"ok": False, "error": "CNS_CUBE_SCRIPT not configured or missing"}
    cmd = ["bash", CUBE_SCRIPT, *args]
    try:
        out = subprocess.check_output(
            cmd,
            text=True,
            timeout=CUBE_CMD_TIMEOUT,
            stderr=subprocess.STDOUT,
            cwd=str(Path(CUBE_SCRIPT).resolve().parent),
        )
        return {"ok": True, "output": out[-12000:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"command timed out after {CUBE_CMD_TIMEOUT}s"}
    except subprocess.CalledProcessError as exc:
        output = exc.output or ""
        return {"ok": False, "error": "command failed", "output": output[-12000:]}


class CubeSession:
    """Interactive Cube node CLI backed by run-cube.sh."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[str] | None = None
        self._output: deque[str] = deque(maxlen=20000)
        self._seq = 0
        self._reader: threading.Thread | None = None
        self._nsec_sent = False
        self._pending_nsec = ""
        self._started_at = 0.0
        self._cli_ready = False

    def _append(self, chunk: str) -> None:
        if not chunk:
            return
        with self._lock:
            self._output.append(chunk)
            self._seq += 1
            if "Syncing chain." in chunk:
                self._cli_ready = False
            if "Syncing complete." in chunk or "Enter command" in chunk:
                self._cli_ready = True

    def _reader_loop(self) -> None:
        proc = self._proc
        if not proc or not proc.stdout:
            return
        buffer = ""
        while True:
            char = proc.stdout.read(1)
            if not char:
                break
            buffer += char
            if char == "\n" or len(buffer) >= 512:
                self._append(buffer)
                if (
                    not self._nsec_sent
                    and "Enter nsec:" in buffer
                    and self._pending_nsec
                    and proc.stdin
                ):
                    proc.stdin.write(self._pending_nsec + "\n")
                    proc.stdin.flush()
                    self._nsec_sent = True
                    self._append("[thebox] sent nsec\n")
                buffer = ""
        if buffer:
            self._append(buffer)
        code = proc.wait()
        self._append(f"\n[thebox] cube exited ({code})\n")

    def _attached(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def status(self) -> dict:
        with self._lock:
            attached = self._attached()
            pids = cube_node_pids()
            process_running = bool(pids)
            return {
                "running": attached or process_running,
                "attached": attached,
                "detached": process_running and not attached,
                "cli_ready": self._cli_ready,
                "pids": pids,
                "seq": self._seq,
                "started_at": self._started_at,
                "nsec_configured": bool(CUBE_NSEC),
                "script": CUBE_SCRIPT,
                "node_args": CUBE_NODE_ARGS,
            }

    def start(self, nsec: str = "") -> dict:
        if not _cube_script_ok():
            return {"ok": False, "error": "CNS_CUBE_SCRIPT not configured or missing"}
        with self._lock:
            if self._attached():
                return {"ok": False, "error": "cube session already running"}
            orphan_pids = cube_node_pids()
            if orphan_pids:
                return {
                    "ok": False,
                    "error": "cube node already running outside this terminal (detached). Click Stop to end it, then Start again.",
                    "detached": True,
                    "pids": orphan_pids,
                }
            self._output.clear()
            self._seq = 0
            self._cli_ready = False
            self._nsec_sent = False
            self._pending_nsec = (nsec.strip() or CUBE_NSEC).strip()
            args = ["bash", CUBE_SCRIPT, *_cube_split_line(CUBE_NODE_ARGS)]
            self._proc = subprocess.Popen(
                args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=0,
                cwd=str(Path(CUBE_SCRIPT).resolve().parent),
                start_new_session=True,
            )
            self._started_at = time.time()
            self._reader = threading.Thread(target=self._reader_loop, daemon=True)
            self._reader.start()
        return {"ok": True, "message": "cube node starting", "nsec_provided": bool(self._pending_nsec)}

    def stop(self) -> dict:
        stopped_pids: list[int] = []
        with self._lock:
            if self._attached():
                try:
                    if self._proc.stdin:
                        self._proc.stdin.write("exit\n")
                        self._proc.stdin.flush()
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                self._proc = None
        stopped_pids = stop_cube_node_processes()
        msg = "cube session stopped"
        if stopped_pids:
            msg += f" (pids: {', '.join(str(p) for p in stopped_pids)})"
        return {"ok": True, "message": msg, "stopped_pids": stopped_pids}

    def write(self, line: str) -> dict:
        err = validate_cube_session_line(line)
        if err:
            return {"ok": False, "error": err}
        with self._lock:
            if not self._attached():
                if cube_node_pids():
                    return {
                        "ok": False,
                        "error": "cube is running detached from this UI — click Stop, then Start node again",
                        "detached": True,
                    }
                return {"ok": False, "error": "cube session not running — click Start Node"}
            if not self._cli_ready:
                return {
                    "ok": False,
                    "error": "cube is still syncing chain — wait for 'Syncing complete.' in the terminal",
                    "syncing": True,
                }
            if not self._proc.stdin:
                return {"ok": False, "error": "cube stdin unavailable"}
            self._proc.stdin.write(line.strip() + "\n")
            self._proc.stdin.flush()
        return {"ok": True}

    def read(self, since: int = 0) -> dict:
        with self._lock:
            text = "".join(self._output)
            attached = self._attached()
            pids = cube_node_pids()
            running = attached or bool(pids)
            return {
                "ok": True,
                "output": text,
                "seq": self._seq,
                "running": running,
                "attached": attached,
                "detached": bool(pids) and not attached,
                "cli_ready": self._cli_ready,
                "since": since,
            }

    def clear_output(self) -> dict:
        with self._lock:
            self._output.clear()
            self._seq += 1
        return {"ok": True, "message": "session output cleared"}


_cube_session = CubeSession()


class BitcoindLoadingError(RuntimeError):
    """RPC up but chain index not ready (bitcoind error -28)."""


def bitcoin_rpc(method: str, params: list | None = None) -> dict:
    payload = json.dumps({"jsonrpc": "1.0", "id": "sysmon", "method": method, "params": params or []}).encode(
        "utf-8"
    )
    creds = f"{CUBE_BITCOIND_USER}:{CUBE_BITCOIND_PASS}".encode("utf-8")
    auth = "Basic " + base64.b64encode(creds).decode("ascii")
    req = urllib.request.Request(
        CUBE_BITCOIND_RPC,
        data=payload,
        headers={"Content-Type": "text/plain", "Authorization": auth},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if body.get("error"):
        err = body["error"]
        code = err.get("code") if isinstance(err, dict) else None
        if code == -28:
            msg = err.get("message", "loading") if isinstance(err, dict) else str(err)
            raise BitcoindLoadingError(msg)
        raise RuntimeError(str(err))
    return body["result"]


def bitcoind_docker_state() -> dict:
    if not CUBE_BITCOIND_CONTAINER:
        return {"configured": False}
    try:
        out = subprocess.check_output(
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.Status}}|{{.State.Running}}",
                CUBE_BITCOIND_CONTAINER,
            ],
            text=True,
            timeout=10,
            stderr=subprocess.DEVNULL,
        ).strip()
        parts = out.split("|")
        return {
            "configured": True,
            "name": CUBE_BITCOIND_CONTAINER,
            "status": parts[0] if parts else "unknown",
            "running": parts[1].lower() == "true" if len(parts) > 1 else False,
            "health": None,
        }
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return {"configured": True, "name": CUBE_BITCOIND_CONTAINER, "status": "not found", "running": False}


def bitcoind_status() -> dict:
    docker = bitcoind_docker_state()
    try:
        info = bitcoin_rpc("getblockchaininfo")
        net = bitcoin_rpc("getnetworkinfo")
        synced = not info.get("initialblockdownload", True)
        progress = float(info.get("verificationprogress", 0.0))
        return {
            "ok": True,
            "reachable": True,
            "chain": info.get("chain"),
            "blocks": info.get("blocks"),
            "headers": info.get("headers"),
            "synced": synced,
            "initialblockdownload": info.get("initialblockdownload"),
            "progress_pct": round(progress * 100, 2),
            "bestblockhash": info.get("bestblockhash"),
            "connections": net.get("connections"),
            "docker": docker,
            "ready_for_cube": synced and info.get("chain") == "signet",
        }
    except BitcoindLoadingError as exc:
        return {
            "ok": True,
            "reachable": True,
            "loading": True,
            "chain": "signet",
            "error": str(exc),
            "docker": docker,
            "synced": False,
            "initialblockdownload": True,
            "ready_for_cube": False,
        }
    except Exception as exc:  # noqa: BLE001
        docker_running = bool(docker.get("running"))
        return {
            "ok": True,
            "reachable": False,
            "error": str(exc),
            "docker": docker,
            "ready_for_cube": False,
            "hint": "start container" if not docker_running else "check RPC URL/credentials",
        }


def save_gensec_seed() -> dict:
    result = run_cube_oneshot(["gensec"])
    if not result.get("ok"):
        return result
    output = result.get("output", "")
    match = NSEC_PATTERN.search(output)
    if not match:
        return {"ok": False, "error": "nsec not found in gensec output", "output": output[-2000:]}
    nsec = match.group(0)
    seeds_dir = Path(CUBE_SEEDS_DIR)
    seeds_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(seeds_dir, 0o700)
    except OSError:
        pass
    stamp = time.strftime("%Y%m%d-%H%M%S")
    seed_file = seeds_dir / f"nsec-{stamp}.txt"
    seed_file.write_text(
        f"# Cube nsec generated {time.strftime('%Y-%m-%d %H:%M:%S %Z')}\n{nsec}\n",
        encoding="utf-8",
    )
    os.chmod(seed_file, 0o600)
    log_file = seeds_dir / "seeds.log"
    with log_file.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp}\t{seed_file.name}\t{nsec}\n")
    try:
        os.chmod(log_file, 0o600)
    except OSError:
        pass
    return {
        "ok": True,
        "nsec": nsec,
        "file": str(seed_file),
        "seeds_dir": str(seeds_dir),
        "output": output,
        "message": f"saved to {seed_file}",
    }


def list_saved_seeds() -> dict:
    seeds_dir = Path(CUBE_SEEDS_DIR)
    if not seeds_dir.is_dir():
        return {"ok": True, "seeds": [], "seeds_dir": str(seeds_dir)}
    seeds = []
    for path in sorted(seeds_dir.glob("nsec-*.txt"), reverse=True)[:20]:
        seeds.append(
            {
                "file": path.name,
                "path": str(path),
                "mtime": path.stat().st_mtime,
                "size": path.stat().st_size,
            }
        )
    return {"ok": True, "seeds": seeds, "seeds_dir": str(seeds_dir)}


def _read_seed_file(name: str) -> tuple[int, dict]:
    if not name or ".." in name or "/" in name or "\\" in name:
        return 400, {"ok": False, "error": "invalid seed file name"}
    if not name.startswith("nsec-") or not name.endswith(".txt"):
        return 400, {"ok": False, "error": "only nsec-*.txt files allowed"}
    seeds_dir = Path(CUBE_SEEDS_DIR).resolve()
    seed_path = (seeds_dir / name).resolve()
    if not str(seed_path).startswith(str(seeds_dir)):
        return 400, {"ok": False, "error": "invalid path"}
    if not seed_path.is_file():
        return 404, {"ok": False, "error": "seed file not found"}
    text = seed_path.read_text(encoding="utf-8")
    match = NSEC_PATTERN.search(text)
    if not match:
        return 400, {"ok": False, "error": "nsec not found in file"}
    return 200, {"ok": True, "file": name, "nsec": match.group(0)}


def cube_examples() -> dict:
    deploy_cns = "deploy 5000 0x04636e7372"
    manifest = CNS_ARTIFACTS / "program.json"
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            deploy_cns = data.get("deploy_example", deploy_cns)
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "deploy_cns": deploy_cns,
        "workflow": [
            "gensec",
            "genesis signet",
            "Start node → wait Syncing complete.",
            "liftaddr",
            "fund lift address (Signet)",
            "liftup",
            "coins",
        ],
    }


def handle_cube_api(path: str, method: str, payload: dict) -> tuple[int, dict]:
    if not _cube_script_ok():
        return 400, {"ok": False, "error": "CNS_CUBE_SCRIPT not configured or missing"}

    if path == "/api/cube/status" and method == "GET":
        status = _cube_session.status()
        status["ok"] = True
        status["examples"] = cube_examples()
        status["bitcoind"] = bitcoind_status()
        status["seeds"] = list_saved_seeds()
        return 200, status

    if path == "/api/cube/bitcoind" and method == "GET":
        return 200, bitcoind_status()

    if path == "/api/cube/gensec/save" and method == "POST":
        result = save_gensec_seed()
        return (200 if result.get("ok") else 400), result

    if path == "/api/cube/seeds" and method == "GET":
        return 200, list_saved_seeds()

    if path.startswith("/api/cube/seeds/") and method == "GET":
        name = path.removeprefix("/api/cube/seeds/").strip("/")
        return _read_seed_file(name)

    if path == "/api/cube/session/clear" and method == "POST":
        return 200, _cube_session.clear_output()

    if path == "/api/cube/run" and method == "POST":
        args = payload.get("args")
        if isinstance(args, list):
            clean = [str(a) for a in args]
        else:
            line = str(payload.get("line", "")).strip()
            clean = _cube_split_line(line)
        result = run_cube_oneshot(clean)
        code = 200 if result.get("ok") else 400
        return code, result

    if path == "/api/cube/session/start" and method == "POST":
        nsec = str(payload.get("nsec", ""))
        result = _cube_session.start(nsec=nsec)
        return (200 if result.get("ok") else 400), result

    if path == "/api/cube/session/stop" and method == "POST":
        return 200, _cube_session.stop()

    if path == "/api/cube/session/input" and method == "POST":
        line = str(payload.get("line", ""))
        result = _cube_session.write(line)
        return (200 if result.get("ok") else 400), result

    if path == "/api/cube/session/output" and method == "GET":
        since = int(payload.get("since", 0) or 0)
        return 200, _cube_session.read(since=since)

    return 404, {"ok": False, "error": "not found"}
