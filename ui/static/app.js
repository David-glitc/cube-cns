(function () {
  "use strict";

  function $(id) {
    return document.getElementById(id);
  }

  function fmtSats(n) {
    if (n === undefined || n === null) return "—";
    return Number(n).toLocaleString() + " sats";
  }

  async function api(path, opts) {
    const res = await fetch(path, opts);
    return { status: res.status, data: await res.json() };
  }

  async function loadContractBalance() {
    const { data } = await api("/api/contract-balance");
    $("contract-balance-pill").textContent =
      "contract " + fmtSats(data.balance);
  }

  async function loadManifest() {
    const { data } = await api("/api/manifest");
    $("manifest").textContent = JSON.stringify(data, null, 2);
  }

  async function loadIndex() {
    const { data } = await api("/api/names");
    $("index-meta").textContent =
      "Updated " + (data.updated_at || "—") + " · " + (data.records || []).length + " names";
    const body = $("index-body");
    body.innerHTML = "";
    const rows = data.records || [];
    for (const rec of rows) {
      let bal = "—";
      if (rec.account) {
        const br = await api(
          "/api/balance?account=" + encodeURIComponent(rec.account)
        );
        if (br.data.balance !== undefined) bal = fmtSats(br.data.balance);
      }
      const tr = document.createElement("tr");
      const status =
        rec.source === "chain" || rec.confirmed
          ? '<span class="badge-ok">on-chain</span>'
          : '<span class="badge-pending">pending</span>';
      tr.innerHTML =
        "<td>" +
        (rec.name || rec.name_hash.slice(0, 12) + "…") +
        "</td><td>" +
        (rec.account ? rec.account.slice(0, 16) + "…" : "—") +
        "</td><td>" +
        bal +
        "</td><td>" +
        status +
        "</td>";
      body.appendChild(tr);
    }
  }

  $("balance-form").addEventListener("submit", async function (e) {
    e.preventDefault();
    const q = new FormData(e.target).get("query").trim();
    const isAccount = /^[0-9a-fA-F]{64}$/.test(q.replace(/^0x/, ""));
    const url = isAccount
      ? "/api/balance?account=" + encodeURIComponent(q.replace(/^0x/, ""))
      : "/api/balance?name=" + encodeURIComponent(q);
    const { data } = await api(url);
    $("balance-display").innerHTML =
      "<strong>" +
      fmtSats(data.balance) +
      "</strong><br><span class='sub'>" +
      (data.account || q) +
      "</span>";
  });

  $("reg-form").addEventListener("submit", async function (e) {
    e.preventDefault();
    const fd = new FormData(e.target);
    const { data } = await api("/api/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: fd.get("name"), account: fd.get("account") }),
    });
    $("reg-result").textContent = JSON.stringify(data, null, 2);
    loadIndex();
  });

  $("renew-form").addEventListener("submit", async function (e) {
    e.preventDefault();
    const fd = new FormData(e.target);
    const { data } = await api("/api/renew", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: fd.get("name"), account: fd.get("account") }),
    });
    $("renew-result").textContent = JSON.stringify(data, null, 2);
    loadIndex();
  });

  $("xfer-form").addEventListener("submit", async function (e) {
    e.preventDefault();
    const fd = new FormData(e.target);
    const { data } = await api("/api/transfer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        to_name: fd.get("to_name"),
        amount: parseInt(fd.get("amount"), 10),
        mode: fd.get("mode"),
      }),
    });
    $("xfer-result").textContent = JSON.stringify(data, null, 2);
  });

  $("resolve-form").addEventListener("submit", async function (e) {
    e.preventDefault();
    const name = new FormData(e.target).get("name");
    const { status, data } = await api("/api/resolve?name=" + encodeURIComponent(name));
    $("resolve-result").textContent = JSON.stringify(
      status === 200 ? data : data,
      null,
      2
    );
  });

  $("sync-btn").addEventListener("click", async function () {
    const { data } = await api("/api/sync", { method: "POST", body: "{}" });
    alert("Sync: " + JSON.stringify(data));
    loadIndex();
    loadContractBalance();
  });

  async function loadTreasury() {
    const { data } = await api("/api/treasury");
    const parts = [];
    const m = data.donations?.mainnet?.btc;
    const s = data.donations?.signet?.btc;
    if (m) parts.push("mainnet: " + m);
    if (s) parts.push("signet: " + s);
    $("treasury-addresses").textContent =
      parts.length ? parts.join(" · ") : "See DONATIONS.md on GitHub";
  }

  loadManifest();
  loadContractBalance();
  loadTreasury();
  loadIndex();
  setInterval(function () {
    loadContractBalance();
    loadIndex();
  }, 30000);
})();
