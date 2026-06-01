(function () {
  "use strict";

  const WALLETS_KEY = "thebox_wallets_v2";
  const LEGACY_KEY = "thebox_wallet_v1";
  const SESSION_KEY = "thebox_session_account";
  const SESSION_WALLET_ID = "thebox_session_wallet_id";

  const $ = (id) => document.getElementById(id);
  const $$ = (sel) => document.querySelectorAll(sel);

  let network = { brand: "TheBox CNS", network: "signet", chain: "cube-signet" };
  let toastTimer;

  function toast(msg, kind) {
    window.theboxToast = toast;
    const el = $("toast");
    if (!el) return;
    el.textContent = msg;
    el.className = "toast " + (kind || "");
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      el.hidden = true;
    }, 5000);
  }

  async function api(path, opts) {
    const res = await fetch(path, opts);
    let data;
    try {
      data = await res.json();
    } catch {
      data = { error: "invalid response" };
    }
    return { status: res.status, data };
  }

  function fmtSats(n) {
    if (n === undefined || n === null || Number.isNaN(Number(n))) return "—";
    return Number(n).toLocaleString() + " sats";
  }

  function shortHex(hex, left, right) {
    if (!hex || hex.length < 16) return hex || "—";
    return hex.slice(0, left || 8) + "…" + hex.slice(-(right || 6));
  }

  function normalizeCubeName(raw) {
    let n = (raw || "").trim().toLowerCase();
    if (!n) return "";
    if (!n.includes(".")) n += ".cube";
    if (!n.endsWith(".cube")) return "";
    return n;
  }

  async function resolveWalletInput(raw) {
    const { data } = await api("/api/wallet/resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ input: raw }),
    });
    if (!data.ok) return { error: data.error || "Could not resolve account." };
    return { account: data.account, source: data.source };
  }

  function parseAccountInput(raw) {
    const s = (raw || "").trim();
    if (!s) return { error: "Enter your Cube account key." };
    const hex = s.replace(/^0x/i, "").toLowerCase();
    if (/^[0-9a-f]{64}$/.test(hex)) return { account: hex };
    return { error: "use_resolve" };
  }

  function bufToB64(buf) {
    return btoa(String.fromCharCode(...new Uint8Array(buf)));
  }

  function b64ToBuf(b64) {
    const bin = atob(b64);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }

  async function deriveKey(password, salt) {
    const enc = new TextEncoder();
    const base = await crypto.subtle.importKey(
      "raw",
      enc.encode(password),
      "PBKDF2",
      false,
      ["deriveKey"]
    );
    return crypto.subtle.deriveKey(
      { name: "PBKDF2", salt, iterations: 120000, hash: "SHA-256" },
      base,
      { name: "AES-GCM", length: 256 },
      false,
      ["encrypt", "decrypt"]
    );
  }

  async function encryptAccount(account, password) {
    const salt = crypto.getRandomValues(new Uint8Array(16));
    const iv = crypto.getRandomValues(new Uint8Array(12));
    const key = await deriveKey(password, salt);
    const ct = await crypto.subtle.encrypt(
      { name: "AES-GCM", iv },
      key,
      new TextEncoder().encode(account)
    );
    return {
      v: 1,
      salt: bufToB64(salt),
      iv: bufToB64(iv),
      ct: bufToB64(ct),
    };
  }

  async function decryptAccount(payload, password) {
    const key = await deriveKey(password, b64ToBuf(payload.salt));
    const plain = await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: b64ToBuf(payload.iv) },
      key,
      b64ToBuf(payload.ct)
    );
    return new TextDecoder().decode(plain);
  }

  function getSessionAccount() {
    return sessionStorage.getItem(SESSION_KEY) || "";
  }

  function setSessionAccount(account) {
    if (account) sessionStorage.setItem(SESSION_KEY, account);
    else sessionStorage.removeItem(SESSION_KEY);
  }

  function loadWalletsStore() {
    const raw = localStorage.getItem(WALLETS_KEY);
    if (raw) {
      try {
        const parsed = JSON.parse(raw);
        if (parsed && Array.isArray(parsed.wallets)) return parsed;
      } catch {
        /* migrate below */
      }
    }
    const legacy = localStorage.getItem(LEGACY_KEY);
    if (legacy) {
      try {
        const old = JSON.parse(legacy);
        if (old && old.enc) {
          const id = crypto.randomUUID();
          const store = {
            v: 2,
            wallets: [
              {
                id,
                label: "Account 1",
                enc: old.enc,
                created_at: old.created_at || new Date().toISOString(),
              },
            ],
          };
          localStorage.setItem(WALLETS_KEY, JSON.stringify(store));
          localStorage.removeItem(LEGACY_KEY);
          return store;
        }
      } catch {
        /* ignore */
      }
    }
    return { v: 2, wallets: [] };
  }

  function saveWalletsStore(store) {
    localStorage.setItem(WALLETS_KEY, JSON.stringify(store));
  }

  function walletLabel(w, index) {
    return w.label || "Account " + (index + 1);
  }

  function renderWalletSelectors() {
    const store = loadWalletsStore();
    const select = $("wallet-select");
    const switcher = $("wallet-switcher");
    const addBtn = $("add-wallet-btn");
    const hasMany = store.wallets.length > 1;

    if (select) {
      select.innerHTML = "";
      store.wallets.forEach((w, i) => {
        const opt = document.createElement("option");
        opt.value = w.id;
        opt.textContent = walletLabel(w, i);
        select.appendChild(opt);
      });
      select.classList.toggle("hidden", !hasMany);
      const activeId = sessionStorage.getItem(SESSION_WALLET_ID);
      if (activeId) select.value = activeId;
      else if (store.wallets[0]) select.value = store.wallets[0].id;
    }

    if (switcher) {
      switcher.innerHTML = "";
      if (isConnected() && store.wallets.length) {
        switcher.classList.remove("hidden");
        store.wallets.forEach((w, i) => {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className =
            "w-full text-left px-2 py-1.5 rounded-lg text-[10px] font-label-mono truncate " +
            (w.id === sessionStorage.getItem(SESSION_WALLET_ID)
              ? "bg-primary-container/20 text-primary-container"
              : "text-outline hover:text-on-surface");
          btn.textContent = walletLabel(w, i);
          btn.addEventListener("click", () => switchWallet(w.id));
          switcher.appendChild(btn);
        });
      } else {
        switcher.classList.add("hidden");
      }
    }

    if (addBtn) {
      addBtn.classList.toggle("hidden", !store.wallets.length);
    }
  }

  async function switchWallet(walletId) {
    const pass = prompt("Enter local password for this account:");
    if (!pass) return;
    try {
      const account = await unlockWalletById(walletId, pass);
      updateChrome(account);
      toast("Switched account.", "ok");
      if (location.hash.includes("dashboard")) refreshDashboard();
      else route("dashboard");
    } catch {
      toast("Wrong password.", "error");
    }
  }

  async function unlockWalletById(walletId, password) {
    const store = loadWalletsStore();
    const w = store.wallets.find((x) => x.id === walletId);
    if (!w || !w.enc) throw new Error("No wallet saved.");
    const account = await decryptAccount(w.enc, password);
    if (!/^[0-9a-f]{64}$/.test(account)) throw new Error("Unlock failed.");
    setSessionAccount(account);
    sessionStorage.setItem(SESSION_WALLET_ID, walletId);
    return account;
  }

  async function unlockWallet(password) {
    const select = $("wallet-select");
    const store = loadWalletsStore();
    const walletId =
      (select && !select.classList.contains("hidden") && select.value) ||
      store.wallets[0]?.id;
    if (!walletId) throw new Error("No wallet saved.");
    return unlockWalletById(walletId, password);
  }

  async function saveWallet(account, password, label) {
    const enc = await encryptAccount(account, password);
    const store = loadWalletsStore();
    const idx = store.wallets.length;
    const entry = {
      id: crypto.randomUUID(),
      label: (label || "").trim() || "Account " + (idx + 1),
      enc,
      created_at: new Date().toISOString(),
    };
    store.wallets.push(entry);
    saveWalletsStore(store);
    setSessionAccount(account);
    sessionStorage.setItem(SESSION_WALLET_ID, entry.id);
    return account;
  }

  async function addNewWallet(account, password, label) {
    const enc = await encryptAccount(account, password);
    const store = loadWalletsStore();
    const idx = store.wallets.length;
    const entry = {
      id: crypto.randomUUID(),
      label: (label || "").trim() || "Account " + (idx + 1),
      enc,
      created_at: new Date().toISOString(),
    };
    store.wallets.push(entry);
    saveWalletsStore(store);
    setSessionAccount(account);
    sessionStorage.setItem(SESSION_WALLET_ID, entry.id);
    return account;
  }

  function removeWallet(walletId) {
    const store = loadWalletsStore();
    store.wallets = store.wallets.filter((w) => w.id !== walletId);
    saveWalletsStore(store);
    if (sessionStorage.getItem(SESSION_WALLET_ID) === walletId) {
      setSessionAccount("");
      sessionStorage.removeItem(SESSION_WALLET_ID);
    }
    renderWalletSelectors();
    renderSettingsWallets();
    showImportMode();
  }

  function disconnect() {
    setSessionAccount("");
    sessionStorage.removeItem(SESSION_WALLET_ID);
    renderWalletSelectors();
    updateChrome("");
    route("import");
    toast("Locked — pick an account to unlock again.", "ok");
  }

  function isConnected() {
    return /^[0-9a-f]{64}$/.test(getSessionAccount());
  }

  function updateChrome(account) {
    const walletLabelEl = $("wallet-label");
    const sub = $("wallet-sub");
    const connected = isConnected();
    $$("[data-requires-wallet]").forEach((el) => {
      el.classList.toggle("opacity-40", !connected);
      el.classList.toggle("pointer-events-none", !connected);
    });
    const btn = $("connect-wallet-btn");
    const btnMobile = $("connect-wallet-btn-mobile");
    const ctaText = connected ? "Dashboard" : "Get Cube Account";
    if (btn) btn.textContent = ctaText;
    if (btnMobile) btnMobile.textContent = connected ? "Dash" : "Account";
    const pill = $("network-pill");
    const pillMobile = $("network-pill-mobile");
    const netShort = (network.network || "signet").toUpperCase();
    if (pill) pill.textContent = netShort;
    if (pillMobile) {
      pillMobile.textContent = netShort;
      pillMobile.classList.remove("hidden");
    }
    if (walletLabelEl) {
      walletLabelEl.textContent = connected ? "Connected" : "Not connected";
    }
    if (sub) {
      sub.textContent = connected ? shortHex(account, 10, 8) : "Setup guide";
    }
    const disconnectBtn = $("disconnect-btn");
    if (disconnectBtn) {
      disconnectBtn.hidden = !connected;
      disconnectBtn.textContent = connected ? "Lock session" : "Disconnect";
    }
    renderWalletSelectors();
    const primaryName = $("hero-name");
    if (primaryName && connected) {
      api("/api/my-names?account=" + encodeURIComponent(account)).then(({ data }) => {
        const names = data.records || [];
        primaryName.textContent = names[0]?.name || shortHex(account, 12, 8);
      });
    }
  }

  const PUBLIC_VIEWS = ["home", "guide", "import"];

  function route(name) {
    const views = ["home", "guide", "import", "dashboard", "register", "names", "settings"];
    views.forEach((v) => {
      const el = $("view-" + v);
      if (el) el.classList.toggle("view-hidden", v !== name);
    });
    $$("[data-nav]").forEach((a) => {
      const active = a.getAttribute("data-nav") === name;
      a.classList.toggle("bg-primary-container", active);
      a.classList.toggle("text-on-primary-container", active);
      a.classList.toggle("text-on-surface-variant", !active);
    });
    location.hash = "#/" + name;
    if (!PUBLIC_VIEWS.includes(name) && !isConnected()) {
      toast("Complete setup: get a Cube account, then import it.", "error");
      route("guide");
      return;
    }
    if (name === "home") refreshHome();
    if (name === "dashboard") refreshDashboard();
    if (name === "register") {
      resetRegisterPanel();
      loadContractInfo();
      refreshNodePanel();
    }
    if (name === "names") refreshNames();
    if (name === "settings") renderSettingsWallets();
    if (name === "import") showImportMode();
  }

  async function loadContractInfo() {
    const { data } = await api("/api/contract");
    const cid = data.contract_id || "—";
    const bal = fmtSats(data.balance);
    const prog = data.program_name || "cnsr";
    if ($("home-contract-id")) $("home-contract-id").textContent = cid;
    if ($("home-contract-bal")) $("home-contract-bal").textContent = bal;
    if ($("home-program")) $("home-program").textContent = prog;
    if ($("reg-contract-id")) $("reg-contract-id").textContent = cid;
  }

  async function refreshHome() {
    await loadContractInfo();
    const body = $("home-names-body");
    if (!body) return;
    body.innerHTML = '<tr><td colspan="3" class="p-4 text-outline">Loading…</td></tr>';
    const { data } = await api("/api/names");
    const rows = (data.records || []).filter((r) => r.name);
    body.innerHTML = "";
    if (!rows.length) {
      body.innerHTML =
        '<tr><td colspan="3" class="p-4 text-outline text-sm">No names indexed yet.</td></tr>';
      return;
    }
    rows.sort((a, b) => (a.name || "").localeCompare(b.name || ""));
    for (const rec of rows) {
      const tr = document.createElement("tr");
      tr.className = "border-t border-outline-variant/20";
      const status = rec.confirmed
        ? '<span class="text-primary-container">on-chain</span>'
        : '<span class="text-secondary">pending</span>';
      tr.innerHTML =
        "<td class='p-3 font-medium'>" +
        rec.name +
        "</td><td class='p-3 font-label-mono text-[10px]'>" +
        shortHex(rec.account, 8, 6) +
        "</td><td class='p-3 text-xs'>" +
        status +
        "</td>";
      body.appendChild(tr);
    }
  }

  async function loadOnboardingPanel(account) {
    const { data } = await api("/api/onboarding");
    const steps = $("onboard-steps");
    if (steps && data.steps) {
      steps.innerHTML = "";
      data.steps.forEach((s) => {
        const li = document.createElement("li");
        let html = s.title + " — " + s.body;
        if (s.url) {
          html += ' <a class="text-primary-container underline" href="' + s.url + '" target="_blank" rel="noopener">link</a>';
        }
        if (s.commands) {
          html +=
            '<br><code class="text-[10px]">' +
            s.commands.join("</code><br><code class='text-[10px]'>") +
            "</code>";
        }
        li.innerHTML = html;
        steps.appendChild(li);
      });
    }
    const acctEl = $("onboard-account");
    if (acctEl) acctEl.textContent = account;
    const feeNote = $("registration-fee-note");
    if (feeNote) feeNote.textContent = data.registration_fee_note || "";
  }

  async function refreshDashboard() {
    const account = getSessionAccount();
    if (!account) return;
    loadOnboardingPanel(account);
    const [{ data: bal }, { data: names }, { data: act }, { data: contract }] =
      await Promise.all([
        api("/api/balance?account=" + encodeURIComponent(account)),
        api("/api/my-names?account=" + encodeURIComponent(account)),
        api("/api/activity?account=" + encodeURIComponent(account) + "&limit=12"),
        api("/api/contract-balance"),
      ]);

    $("dash-balance").textContent = fmtSats(bal.balance);
    $("dash-balance-sub").textContent =
      (network.network || "signet").toUpperCase() + " · Cube account";
    $("dash-contract-pill").textContent =
      "CNS contract " + fmtSats(contract.balance);

    const primary = (names.records || [])[0];
    $("hero-name").textContent = primary?.name || "No .cube name yet";
    $("hero-account").textContent = shortHex(account, 10, 8);

    const tbody = $("activity-body");
    tbody.innerHTML = "";
    const rows = act.records || [];
    if (!rows.length) {
      tbody.innerHTML =
        '<tr><td colspan="4" class="p-4 text-outline text-sm">No activity yet. Register a name or sync the index.</td></tr>';
      return;
    }
    for (const r of rows) {
      const tr = document.createElement("tr");
      tr.className = "border-t border-outline-variant/20";
      const kind = r.kind || (r.note && r.note.startsWith("register") ? "register" : "transfer");
      const amt =
        r.amount && Number(r.amount) > 0 ? fmtSats(r.amount) : "—";
      tr.innerHTML =
        "<td class='p-3 font-label-mono text-[10px] text-outline'>" +
        kind +
        "</td><td class='p-3'>" +
        (r.to_name || "—") +
        "</td><td class='p-3 font-label-mono text-xs'>" +
        amt +
        "</td><td class='p-3 text-xs'>" +
        (r.status || "pending") +
        "</td>";
      tbody.appendChild(tr);
    }
  }

  function renderSettingsWallets() {
    const list = $("settings-wallets");
    if (!list) return;
    const store = loadWalletsStore();
    const activeId = sessionStorage.getItem(SESSION_WALLET_ID);
    list.innerHTML = "";
    if (!store.wallets.length) {
      list.innerHTML = '<li class="text-outline text-xs">No saved accounts.</li>';
      return;
    }
    store.wallets.forEach((w, i) => {
      const li = document.createElement("li");
      li.className = "flex items-center justify-between gap-2 border border-outline-variant/40 rounded-lg px-3 py-2";
      const active = w.id === activeId && isConnected();
      li.innerHTML =
        '<span><span class="font-medium">' +
        walletLabel(w, i) +
        "</span>" +
        (active ? ' <span class="text-[10px] text-primary-container">(active)</span>' : "") +
        '</span><button type="button" data-remove-wallet="' +
        w.id +
        '" class="text-[10px] text-error uppercase">Remove</button>';
      list.appendChild(li);
    });
    list.querySelectorAll("[data-remove-wallet]").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (confirm("Remove this account from this browser?")) {
          removeWallet(btn.getAttribute("data-remove-wallet"));
          toast("Account removed from browser storage.", "ok");
        }
      });
    });
  }

  function setupTreasuryUI(treasury) {
    const mainnet = treasury?.donations?.mainnet?.btc || "";
    const signet = treasury?.donations?.signet?.btc || "";
    if ($("treasury-mainnet")) $("treasury-mainnet").textContent = mainnet || "—";
    if ($("treasury-signet")) $("treasury-signet").textContent = signet || "—";
    const link = $("treasury-bip21");
    const qr = $("treasury-qr");
    if (mainnet && link) {
      const uri = "bitcoin:" + mainnet;
      link.href = uri;
      link.classList.remove("hidden");
      if (qr) {
        qr.src =
          "https://api.qrserver.com/v1/create-qr-code/?size=160x160&data=" +
          encodeURIComponent(uri);
        qr.classList.remove("hidden");
      }
    } else if (link) {
      link.classList.add("hidden");
    }
  }

  async function refreshNames() {
    const account = getSessionAccount();
    const body = $("names-body");
    body.innerHTML = "";
    const { data } = await api(
      "/api/my-names?account=" + encodeURIComponent(account)
    );
    const rows = data.records || [];
    if (!rows.length) {
      body.innerHTML =
        '<tr><td colspan="4" class="p-6 text-outline">No names yet. <a href="#/register" class="text-primary-container underline">Register one</a>.</td></tr>';
      return;
    }
    for (const rec of rows) {
      const tr = document.createElement("tr");
      const status = rec.confirmed
        ? '<span class="text-primary-container">on-chain</span>'
        : '<span class="text-secondary-container">pending</span>';
      tr.innerHTML =
        "<td class='p-4'>" +
        rec.name +
        "</td><td class='p-4 font-label-mono text-xs'>" +
        shortHex(rec.account, 8, 6) +
        "</td><td class='p-4'>" +
        fmtSats(rec.balance) +
        "</td><td class='p-4'>" +
        status +
        "</td>";
      body.appendChild(tr);
    }
  }

  function resetRegisterPanel() {
    $("register-result").classList.add("view-hidden");
    $("register-search").value = "";
  }

  async function verifyName() {
    const name = normalizeCubeName($("register-search").value);
    if (!name) {
      toast("Enter a valid .cube name (e.g. saturn.cube).", "error");
      return;
    }
    const { data } = await api("/api/availability?name=" + encodeURIComponent(name));
    const panel = $("register-result");
    panel.classList.remove("view-hidden");
    $("reg-display-name").textContent = data.name;
    const avail = data.available;
    $("reg-availability").textContent = avail
      ? "Availability: Available"
      : "Availability: Taken";
    $("reg-availability").className = avail
      ? "font-label-mono text-label-mono text-primary-container uppercase tracking-widest"
      : "font-label-mono text-label-mono text-error uppercase tracking-widest";
    $("reg-register-btn").disabled = !avail;
    $("reg-register-btn").dataset.name = data.name;
  }

  function showCallPackage(pkg) {
    const hintEl = $("reg-hint");
    if (!hintEl) return;
    hintEl.classList.remove("hidden");
    hintEl.textContent = JSON.stringify(pkg, null, 2);
  }

  async function buildRegisterCall() {
    const account = getSessionAccount();
    const name = $("reg-register-btn").dataset.name;
    if (!name || !account) {
      toast("Check name availability first.", "error");
      return;
    }
    const { data } = await api("/api/register/call-package", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, account }),
    });
    if (!data.ok) {
      toast(data.error || "Could not build call", "error");
      return;
    }
    showCallPackage(data.call_package);
    toast("Call package ready — copy or submit.", "ok");
  }

  async function refreshNodePanel() {
    const line = $("node-status-line");
    const out = $("node-output");
    if (!line) return;
    const { data } = await api("/api/node/status");
    if (!data.ok && data.error) {
      line.textContent = "Node: " + data.error;
      return;
    }
    const running = data.running || data.attached;
    const ready = data.cli_ready;
    line.textContent =
      "Node: " +
      (running ? (ready ? "running, ready" : "running, syncing…") : "not running (start in SysMon)");
  }

  function formatNodeOutput(data) {
    if (!data) return "";
    const events = data.events || [];
    if (events.length) {
      return events.map((e) => (e.kind === "err" ? "✗ " : e.kind === "ok" ? "✓ " : "· ") + (e.message || "")).join("\n");
    }
    const inner = data.output;
    if (inner && Array.isArray(inner.events) && inner.events.length) {
      return inner.events.map((e) => e.message || "").join("\n");
    }
    if (typeof inner === "string") return inner;
    if (inner && typeof inner.output === "string") return inner.output;
    if (data.error) return data.error;
    return data.ok === false ? "Command failed" : "Done";
  }

  async function execNodeAction(action, params = {}) {
    const out = $("node-output");
    if (out) out.textContent = "Running " + action + "…";
    const waitMs = action.startsWith("deploy") ? 4000 : 1500;
    const { data } = await api("/api/node/exec", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, params, wait_ms: waitMs }),
    });
    if (out) out.textContent = formatNodeOutput(data);
    if (!data.ok) toast(data.error || data.input?.error || "Node command failed", "error");
    else toast("Cube node updated", "ok");
    refreshNodePanel();
  }

  async function submitRegisterCall() {
    const account = getSessionAccount();
    const name = $("reg-register-btn").dataset.name;
    const nsec = ($("reg-nsec")?.value || "").trim();
    if (!name || !account) {
      toast("Check name availability first.", "error");
      return;
    }
    if (!nsec) {
      toast("Enter your nsec to verify identity for submit.", "error");
      return;
    }
    const { data } = await api("/api/register/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, account, nsec }),
    });
    if (!data.ok) {
      toast(data.error || "Submit failed", "error");
      return;
    }
    showCallPackage(data.call_package);
    if (data.on_chain) {
      toast((data.entry?.name || name) + " submitted on-chain.", "ok");
    } else {
      toast(
        (data.entry?.name || name) +
          " indexed as pending only. On-chain register is not available in Cube yet.",
        "ok"
      );
    }
    verifyName();
    refreshNames();
    refreshDashboard();
    refreshHome();
  }

  async function registerName() {
    const account = getSessionAccount();
    const name = $("reg-register-btn").dataset.name;
    if (!name || !account) return;
    const { data } = await api("/api/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, account }),
    });
    if (!data.ok) {
      toast(data.error || "Registration failed", "error");
      return;
    }
    if (data.call_package) showCallPackage(data.call_package);
    toast(
      (data.entry?.name || name) +
        " saved to index as pending (not on-chain until Cube supports call).",
      "ok"
    );
    verifyName();
    refreshNames();
    refreshDashboard();
    refreshHome();
  }

  function bindWalletActions() {
    $("btn-generate-identity")?.addEventListener("click", async () => {
      const { data } = await api("/api/wallet/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      if (!data.ok) {
        toast(data.error || "Generate failed", "error");
        return;
      }
      $("gen-nsec").textContent = data.nsec;
      $("gen-account").textContent = data.account;
      $("generated-keys").classList.remove("view-hidden");
      toast("Copy your nsec now — shown once", "ok");
    });
    $("btn-use-generated")?.addEventListener("click", () => {
      const acct = $("gen-account").textContent;
      if (acct) $("import-key").value = acct;
      route("import");
      toast("Account filled — set a local password", "ok");
    });
    $("btn-resolve-paste")?.addEventListener("click", async () => {
      const raw = $("resolve-paste").value;
      const resolved = await resolveWalletInput(raw);
      if (resolved.error) {
        toast(resolved.error, "error");
        return;
      }
      $("import-key").value = resolved.account;
      toast("Resolved from " + (resolved.source || "paste"), "ok");
    });
  }

  function bindImportForm() {
    const form = $("import-form");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const key = $("import-key").value;
      const pass = $("import-pass").value;
      const pass2 = $("import-pass-confirm").value;
      if (pass.length < 8) {
        toast("Local password must be at least 8 characters.", "error");
        return;
      }
      if (pass !== pass2) {
        toast("Passwords do not match.", "error");
        return;
      }
      let parsed = parseAccountInput(key);
      if (parsed.error === "use_resolve") {
        parsed = await resolveWalletInput(key);
      }
      if (parsed.error) {
        toast(parsed.error, "error");
        return;
      }
      try {
        const store = loadWalletsStore();
        const hadWallets = store.wallets.length > 0;
        if (hadWallets) {
          await addNewWallet(parsed.account, pass);
          toast("Another account saved on this device.", "ok");
        } else {
          await saveWallet(parsed.account, pass);
          toast("Account saved in this browser only.", "ok");
        }
        updateChrome(parsed.account);
        route("dashboard");
      } catch (err) {
        toast("Could not save wallet: " + err.message, "error");
      }
    });

    $("unlock-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const account = await unlockWallet($("unlock-pass").value);
        updateChrome(account);
        toast("Wallet unlocked.", "ok");
        route("dashboard");
      } catch {
        toast("Wrong password or corrupted wallet data.", "error");
      }
    });
  }

  function bindNav() {
    $$("[data-nav]").forEach((a) => {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        route(a.getAttribute("data-nav"));
      });
    });
    const disconnectBtn = $("disconnect-btn");
    if (disconnectBtn) {
      disconnectBtn.addEventListener("click", () => disconnect());
    }
    function onConnectClick() {
      if (isConnected()) route("dashboard");
      else route("guide");
    }
    $("connect-wallet-btn")?.addEventListener("click", onConnectClick);
    $("connect-wallet-btn-mobile")?.addEventListener("click", onConnectClick);
    document.querySelectorAll('a[href="#/register"]').forEach((a) => {
      a.addEventListener("click", (e) => {
        if (!isConnected()) {
          e.preventDefault();
          toast("Import a Cube account first, then register.", "error");
          route("guide");
        }
      });
    });
    $("guide-to-import").addEventListener("click", () => route("import"));
    $("add-wallet-btn")?.addEventListener("click", () => route("import"));
    $("settings-add-wallet")?.addEventListener("click", () => route("import"));
    $("import-to-guide").addEventListener("click", () => route("guide"));
    $("verify-name-btn").addEventListener("click", verifyName);
    $("reg-register-btn").addEventListener("click", registerName);
    $("reg-build-call-btn")?.addEventListener("click", buildRegisterCall);
    $("reg-submit-call-btn")?.addEventListener("click", submitRegisterCall);
    $("home-refresh-names")?.addEventListener("click", refreshHome);
    $$("[data-node-cmd]").forEach((btn) => {
      btn.addEventListener("click", () => execNodeAction(btn.getAttribute("data-node-cmd")));
    });
    $("sync-index-btn").addEventListener("click", async () => {
      const { data } = await api("/api/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      toast("Index synced: " + (data.total_names ?? "?") + " names", "ok");
      refreshDashboard();
    });
    $("copy-account-btn").addEventListener("click", () => {
      const acct = getSessionAccount();
      if (acct) navigator.clipboard.writeText(acct);
      toast("Account copied.", "ok");
    });

    const toggle = $("toggle-key-vis");
    if (toggle) {
      toggle.addEventListener("click", () => {
        const input = $("import-key");
        const hidden = input.type === "password";
        input.type = hidden ? "text" : "password";
        toggle.textContent = hidden ? "visibility" : "visibility_off";
      });
    }

    $$(".input-focus-accent input").forEach((input) => {
      const parent = input.closest(".input-focus-accent");
      const sync = () => {
        if (document.activeElement === input || input.value) parent.classList.add("focused");
        else parent.classList.remove("focused");
      };
      input.addEventListener("focus", sync);
      input.addEventListener("blur", sync);
      input.addEventListener("input", sync);
    });
  }

  function showImportMode() {
    const store = loadWalletsStore();
    const hasWallets = store.wallets.length > 0;
    const addingAnother = isConnected();
    if (!hasWallets) {
      $("import-panel").classList.remove("view-hidden");
      $("unlock-panel").classList.add("view-hidden");
    } else if (addingAnother) {
      $("import-panel").classList.remove("view-hidden");
      $("unlock-panel").classList.add("view-hidden");
    } else {
      $("import-panel").classList.add("view-hidden");
      $("unlock-panel").classList.remove("view-hidden");
    }
    renderWalletSelectors();
    const title = document.querySelector("#view-import h1");
    if (title) {
      title.textContent = addingAnother
        ? "Add another account"
        : hasWallets
          ? "Unlock account"
          : "Import Cube Account";
    }
  }

  async function init() {
    const { data } = await api("/api/network");
    network = { ...network, ...data };
    const netLabel = (network.network || "signet").toUpperCase() + " · Cube CNS";
    if ($("network-pill")) $("network-pill").textContent = netLabel;
    if ($("network-pill-mobile")) $("network-pill-mobile").textContent = netLabel.split(" · ")[0];
    const host = network.public_host || location.hostname;
    $("domain-hint").textContent = host;
    const treasury = await api("/api/treasury");
    setupTreasuryUI(treasury.data);

    bindWalletActions();
    bindImportForm();
    bindNav();
    showImportMode();

    const hash = (location.hash || "").replace("#/", "") || "";
    let start = hash;
    if (!start) start = "home";
    if (!isConnected() && !PUBLIC_VIEWS.includes(start)) start = "home";
    await loadContractInfo();
    updateChrome(getSessionAccount());
    renderSettingsWallets();
    route(start);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
