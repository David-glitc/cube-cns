(function () {
  "use strict";

  let sessionRunning = false;
  let sessionAttached = false;
  let sessionDetached = false;
  let cliReady = false;
  let pendingCommands = [];
  let lastSeq = 0;
  let lastOutputLen = 0;
  let pollTimer = null;

  function $(id) {
    return document.getElementById(id);
  }

  function toast(msg, isErr) {
    if (window.theboxToast) {
      window.theboxToast(msg, isErr ? "error" : "ok");
      return;
    }
    console.log(isErr ? "ERR" : "OK", msg);
  }

  async function api(path, opts) {
    const res = await fetch(
      path,
      Object.assign({ headers: { "Content-Type": "application/json" } }, opts || {})
    );
    return res.json().catch(function () {
      return { ok: false, error: "invalid json" };
    });
  }

  function appendOutput(text, cls) {
    const out = $("cube-output");
    if (!out) return;
    const span = document.createElement("span");
    if (cls) span.className = cls;
    span.textContent = text;
    out.appendChild(span);
    out.scrollTop = out.scrollHeight;
  }

  function applySessionState(st) {
    sessionRunning = !!(st && st.running);
    sessionAttached = !!(st && st.attached);
    sessionDetached = !!(st && st.detached);
    cliReady = !!(st && st.cli_ready);
    const pill = $("cube-status");
    if (!pill) return;
    if (sessionDetached) {
      pill.textContent = "detached";
      pill.className = "font-label-mono text-xs px-2 py-1 rounded-full bg-secondary-container/20 text-secondary";
    } else if (sessionRunning && !cliReady) {
      pill.textContent = "syncing";
      pill.className = "font-label-mono text-xs px-2 py-1 rounded-full bg-secondary-container/30 text-secondary";
    } else if (sessionRunning) {
      pill.textContent = "ready";
      pill.className = "font-label-mono text-xs px-2 py-1 rounded-full bg-primary-container/20 text-primary-container";
    } else {
      pill.textContent = "offline";
      pill.className = "font-label-mono text-xs px-2 py-1 rounded-full bg-surface-container-highest text-outline";
    }
  }

  async function runOneshot(line) {
    appendOutput("› " + line + "\n", "cube-sys");
    const data = await api("/api/cube/run", {
      method: "POST",
      body: JSON.stringify({ line: line }),
    });
    if (data.output) appendOutput(data.output + "\n");
    if (!data.ok) appendOutput((data.error || "failed") + "\n", "cube-err");
    toast(data.ok ? "done" : data.error || "failed", !data.ok);
    return data;
  }

  async function gensecAndSave() {
    appendOutput("› gensec & save\n", "cube-sys");
    const data = await api("/api/cube/gensec/save", { method: "POST", body: "{}" });
    if (data.output) appendOutput(data.output + "\n");
    if (data.ok && data.nsec) {
      $("cube-nsec").value = data.nsec;
      toast("Seed saved — start node when ready");
    } else {
      toast(data.error || "gensec failed", true);
    }
  }

  async function startNode() {
    appendOutput("[thebox] starting node…\n", "cube-sys");
    const data = await api("/api/cube/session/start", {
      method: "POST",
      body: JSON.stringify({
        nsec: $("cube-nsec") ? $("cube-nsec").value.trim() : "",
      }),
    });
    if (!data.ok) {
      appendOutput((data.error || "start failed") + "\n", "cube-err");
      toast(data.error || "start failed", true);
      return;
    }
    applySessionState({ running: true, attached: true, cli_ready: false });
    lastOutputLen = 0;
    pendingCommands = [];
    startPolling();
    toast("Node starting");
  }

  async function stopNode() {
    await api("/api/cube/session/stop", { method: "POST", body: "{}" });
    applySessionState({ running: false });
    stopPolling();
    appendOutput("[thebox] stopped\n", "cube-sys");
  }

  async function sendSessionLine(line, fromQueue) {
    appendOutput("› " + line + "\n", "cube-sys");
    const data = await api("/api/cube/session/input", {
      method: "POST",
      body: JSON.stringify({ line: line }),
    });
    if (!data.ok) {
      if (data.syncing && !fromQueue) {
        pendingCommands.push(line);
        toast("Queued until sync completes");
        return;
      }
      appendOutput((data.error || "rejected") + "\n", "cube-err");
      toast(data.error || "rejected", true);
    }
  }

  async function pollOutput() {
    const data = await api("/api/cube/session/output?since=" + lastSeq);
    if (!data.ok) return;
    if (data.output && data.output.length > lastOutputLen) {
      const chunk = data.output.slice(lastOutputLen);
      appendOutput(chunk);
      if (chunk.indexOf("Syncing complete.") !== -1 || chunk.indexOf("Enter command") !== -1) {
        cliReady = true;
      }
      lastOutputLen = data.output.length;
    }
    if (typeof data.seq === "number") lastSeq = data.seq;
    if (typeof data.cli_ready === "boolean") cliReady = data.cli_ready;
    applySessionState(data);
    if (cliReady && pendingCommands.length) {
      const batch = pendingCommands.slice();
      pendingCommands = [];
      for (const line of batch) await sendSessionLine(line, true);
    }
    if (!data.running) stopPolling();
  }

  function startPolling() {
    stopPolling();
    pollTimer = setInterval(pollOutput, 800);
    pollOutput();
  }

  function stopPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
  }

  function submitLine(line) {
    const cmd = line.trim().split(/\s+/)[0].toLowerCase();
    if (!line.trim()) return;
    if (cmd === "gensec" || cmd === "test" || cmd === "genesis") {
      runOneshot(line.trim());
      return;
    }
    if (!sessionRunning || !sessionAttached) {
      toast("Start node first", true);
      return;
    }
    if (!cliReady) {
      pendingCommands.push(line.trim());
      toast("Queued — wait for Syncing complete.");
      return;
    }
    sendSessionLine(line.trim());
  }

  function bindTerminal() {
    const form = $("cube-form");
    if (!form || form.dataset.bound) return;
    form.dataset.bound = "1";

    $("cube-gensec")?.addEventListener("click", gensecAndSave);
    $("cube-start")?.addEventListener("click", startNode);
    $("cube-stop")?.addEventListener("click", stopNode);
    $("cube-clear")?.addEventListener("click", function () {
      $("cube-output").innerHTML = "";
      lastOutputLen = 0;
      api("/api/cube/session/clear", { method: "POST", body: "{}" });
    });

    document.querySelectorAll("[data-cube-cmd]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const line = btn.getAttribute("data-cube-cmd") || "";
        if ($("cube-input")) $("cube-input").value = line;
        submitLine(line);
      });
    });

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      const line = $("cube-input").value;
      $("cube-input").value = "";
      submitLine(line);
    });

    appendOutput("TheBox Cube terminal — one command per line.\n", "cube-sys");
    api("/api/cube/status").then(function (data) {
      applySessionState(data);
      if (data.running) startPolling();
    });
  }

  window.initCubeTerminal = bindTerminal;
})();
