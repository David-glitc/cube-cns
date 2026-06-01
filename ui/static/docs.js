(function () {
  "use strict";

  const DOCS = {
    "contract-flow": "CONTRACT-FLOW.md",
    cns: "CNS.md",
    onchain: "ONCHAIN-REGISTER.md",
  };

  const nav = document.querySelector(".docs-nav");
  const content = document.getElementById("docs-content");

  function slugFromHash() {
    const h = (location.hash || "#/contract-flow").replace("#/", "").toLowerCase();
    return DOCS[h] ? h : "contract-flow";
  }

  function setActive(slug) {
    document.querySelectorAll(".docs-nav-link[data-doc]").forEach((a) => {
      const active = a.getAttribute("href") === "#/" + slug;
      a.classList.toggle("docs-nav-active", active);
    });
  }

  function enhanceMarkdown(html) {
    const wrap = document.createElement("div");
    wrap.innerHTML = html;
    wrap.querySelectorAll("pre code.language-mermaid, pre code.mermaid").forEach((el) => {
      const pre = el.closest("pre");
      if (pre) {
        const div = document.createElement("div");
        div.className = "mermaid";
        div.textContent = el.textContent;
        pre.replaceWith(div);
      }
    });
    wrap.querySelectorAll("pre code").forEach((el) => {
      const lang = (el.className || "").replace("language-", "");
      if (lang === "mermaid") {
        const div = document.createElement("div");
        div.className = "mermaid";
        div.textContent = el.textContent;
        el.closest("pre").replaceWith(div);
      }
    });
    return wrap.innerHTML;
  }

  async function loadDoc(slug) {
    const file = DOCS[slug];
    if (!file) return;
    setActive(slug);
    content.innerHTML = "<p class=\"text-outline\">Loading…</p>";
    try {
      const res = await fetch("/raw/docs/" + file);
      if (!res.ok) throw new Error("HTTP " + res.status);
      let md = await res.text();
      md = md.replace(/```mermaid\n([\s\S]*?)```/g, function (_, body) {
        return "\n<div class=\"mermaid\">\n" + body.trim() + "\n</div>\n";
      });
      let html = marked.parse(md);
      html = enhanceMarkdown(html);
      content.innerHTML = html;
      if (window.mermaid) {
        window.mermaid.initialize({ startOnLoad: false, theme: "dark" });
        await window.mermaid.run({ nodes: content.querySelectorAll(".mermaid") });
      }
    } catch (err) {
      content.innerHTML =
        "<p class=\"docs-error\">Could not load " +
        file +
        ": " +
        err.message +
        "</p>";
    }
  }

  if (nav) {
    nav.addEventListener("click", (e) => {
      const link = e.target.closest("[data-doc]");
      if (!link) return;
      e.preventDefault();
      const slug = link.getAttribute("href").replace("#/", "");
      location.hash = "#/" + slug;
      loadDoc(slug);
    });
  }

  window.addEventListener("hashchange", () => loadDoc(slugFromHash()));

  const script = document.createElement("script");
  script.src = "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js";
  script.onload = () => loadDoc(slugFromHash());
  script.onerror = () => loadDoc(slugFromHash());
  document.head.appendChild(script);
})();
