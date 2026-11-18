(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const MIN = 15;
  let samples = [];
  let historyEnabled = true;

  // ---- tiny DOM helpers: all dynamic text goes through textContent (no innerHTML) ----
  function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === "class") node.className = v; else if (k === "text") node.textContent = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v); else node.setAttribute(k, v);
    }
    for (const c of children) if (c != null) node.append(c);
    return node;
  }
  const clear = (n) => { while (n.firstChild) n.removeChild(n.firstChild); return n; };

  async function api(path, opts) {
    let res;
    try { res = await fetch(path, opts); } catch { throw new Error("Cannot reach the server. Is it running?"); }
    let body = null;
    try { body = await res.json(); } catch { /* ignore */ }
    if (!res.ok || !body || body.ok === false) {
      throw new Error((body && body.error && body.error.message) || `Request failed (HTTP ${res.status}).`);
    }
    return body.data;
  }

  // ---- providers / banner ----
  function updateBanner() {
    const sel = $("provider"), opt = sel.selectedOptions[0];
    const banner = $("mode-banner");
    const demo = opt && opt.dataset.simulated === "true";
    banner.className = "banner" + (demo ? " sim" : "");
    banner.textContent = demo
      ? "Demo mode: results are SIMULATED by deterministic rules, not by an AI model. No API key or network needed."
      : `Live mode: your description will be sent to ${opt ? opt.textContent.replace(/ \(.*/, "") : "the provider"}. Errors are shown as-is; there is no silent fallback to demo.`;
    $("provider-hint").textContent = opt && opt.dataset.model ? `Model: ${opt.dataset.model}` : "";
  }

  async function loadProviders() {
    const data = await api("/api/providers");
    const sel = clear($("provider"));
    for (const p of data.providers) {
      const o = el("option", { value: p.id, text: p.simulated ? `${p.label} - no API key needed` :
        (p.configured ? p.label : `${p.label} - not configured`) });
      o.dataset.simulated = String(p.simulated);
      o.dataset.model = p.model || "";
      o.disabled = !p.configured;
      o.title = p.hint || "";
      sel.append(o);
    }
    sel.value = data.providers.some((p) => p.id === data.default && p.configured) ? data.default : "demo";
    updateBanner();
  }

  async function loadSamples() {
    samples = await api("/api/samples");
    const sel = $("sample");
    for (const s of samples) sel.append(el("option", { value: s.id, text: s.label }));
  }

  // ---- form ----
  function showFormError(msg) { const e = $("form-error"); e.hidden = !msg; e.textContent = msg || ""; }
  function updateCount() { $("count").textContent = $("description").value.length; }

  function setBusy(busy) {
    const b = $("submit"); b.disabled = busy; b.textContent = busy ? "Analyzing…" : "Analyze incident";
  }

  async function onSubmit(ev) {
    ev.preventDefault();
    showFormError("");
    const description = $("description").value.trim();
    if (description.length < MIN) { showFormError(`Please describe the incident in at least ${MIN} characters.`); return; }
    const payload = { description, provider: $("provider").value, title: $("title").value, service: $("service").value,
                      reported_severity: $("reported").value || null };
    setBusy(true);
    clear($("result")).append(el("p", { class: "empty" }, el("span", { class: "spinner" }), "Analyzing incident…"));
    try {
      const data = await api("/api/analyze", { method: "POST", headers: { "Content-Type": "application/json" },
                                               body: JSON.stringify(payload) });
      renderResult(data);
      refreshHistory();
    } catch (e) {
      clear($("result")).append(el("div", { class: "error", role: "alert" },
        el("strong", { text: "Analysis failed. " }), e.message));
    } finally { setBusy(false); }
  }

  // ---- results ----
  const list = (items, tag = "ul") => el(tag, {}, ...(items || []).map((t) => el("li", { text: t })));

  function renderResult(d) {
    const r = d.result, sig = d.severity_signals || {}, root = clear($("result"));
    const head = el("div", { class: "sev-head" },
      el("span", { class: `badge sev-big ${r.severity}`, text: r.severity }),
      el("span", { class: "badge neutral", text: `Priority ${r.suggested_priority}` }),
      el("span", { class: "badge neutral", text: d.escalation && d.escalation.should_escalate ? "Escalate to a human" : "No escalation needed" }));
    if (d.simulated) head.append(el("span", { class: "badge sim", text: "SIMULATED" }));
    root.append(head);
    if (d.notice) root.append(el("div", { class: "banner sim", text: d.notice }));

    root.append(el("p", { class: "summary", text: r.summary }));
    root.append(el("h3", { text: "Why this severity" }), el("p", { text: r.severity_reasoning }));
    const bits = [`AI/engine: ${sig.model}`];
    if (sig.rules) bits.push(`rules: ${sig.rules}` + (sig.matched_rules.length ? ` (${sig.matched_rules.join(", ")})` : ""));
    if (sig.reported) bits.push(`your estimate: ${sig.reported}`);
    root.append(el("p", { class: "hint", text: `Signals - ${bits.join(" · ")}. Final severity is never lower than the rules' floor.` }));

    root.append(el("h3", { text: "Impact" }), el("div", { class: "impact" },
      el("div", {}, el("strong", { text: "Business" }), r.impact.business),
      el("div", {}, el("strong", { text: "Operational" }), r.impact.operational)));

    if (r.possible_root_causes.length) {
      root.append(el("h3", { text: "Possible root causes" }), el("ul", {}, ...r.possible_root_causes.map((c) =>
        el("li", { class: "cause" }, c.cause, el("small", { text: `${c.confidence} confidence` + (c.evidence ? ` · ${c.evidence}` : "") })))));
    }
    if (r.investigation_steps.length) root.append(el("h3", { text: "Investigation steps" }), list(r.investigation_steps, "ol"));
    if (r.resolution_steps.length) root.append(el("h3", { text: "Recommended resolution" }), list(r.resolution_steps, "ol"));
    if (r.next_actions.length) root.append(el("h3", { text: "Next actions" }), list(r.next_actions));
    if (d.escalation) root.append(el("p", { class: "hint", text: `Suggested routing: ${d.escalation.route_to}` }));

    root.append(el("div", { class: "meta", text:
      `${d.simulated ? "Simulated" : "Generated"} by ${d.provider} / ${d.model} · ${d.latency_ms} ms · confidence: ${r.confidence} · ${d.created_at}` }));
  }

  // ---- history ----
  async function refreshHistory() {
    const box = clear($("history"));
    let items;
    try { items = await api("/api/incidents"); } catch (e) {
      historyEnabled = false; $("clear").hidden = true;
      box.append(el("p", { class: "muted", text: "History is unavailable (disabled on the server)." })); return;
    }
    $("clear").hidden = items.length === 0;
    if (!items.length) { box.append(el("p", { class: "muted", text: "Nothing here yet. Analyses you run will appear here." })); return; }
    for (const it of items) {
      box.append(el("div", { class: "hist-item" },
        el("span", { class: `badge ${it.severity}`, text: it.severity }),
        el("div", { class: "t" }, el("b", { text: it.title || it.summary || it.id }),
          el("span", { text: `${it.simulated ? "Simulated" : it.provider} · ${it.created_at}` })),
        el("span", {}, el("button", { class: "link", type: "button", text: "View", onclick: () => viewIncident(it.id) }),
          el("button", { class: "link danger", type: "button", text: "Delete", onclick: () => removeIncident(it.id) }))));
    }
  }

  async function viewIncident(id) {
    try {
      const it = await api(`/api/incidents/${encodeURIComponent(id)}`);
      const res = it.result;
      renderResult({ id: it.id, created_at: it.created_at, provider: it.provider, model: it.model, simulated: it.simulated,
        latency_ms: it.latency_ms, result: res, severity_signals: res.severity_signals, escalation: res.escalation,
        notice: it.simulated ? "SIMULATED: generated by deterministic demo rules, not by an AI model." : undefined });
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) { clear($("result")).append(el("div", { class: "error", text: e.message })); }
  }

  async function removeIncident(id) {
    try { await api(`/api/incidents/${encodeURIComponent(id)}`, { method: "DELETE" }); } catch (e) { /* refresh anyway */ }
    refreshHistory();
  }

  async function init() {
    $("form").addEventListener("submit", onSubmit);
    $("provider").addEventListener("change", updateBanner);
    $("description").addEventListener("input", updateCount);
    $("sample").addEventListener("change", (e) => {
      const s = samples.find((x) => x.id === e.target.value);
      if (!s) return;
      $("title").value = s.title; $("service").value = s.service; $("description").value = s.description; updateCount();
    });
    $("clear").addEventListener("click", async () => {
      if (confirm("Delete all saved analyses from the local database?")) {
        try { await api("/api/incidents", { method: "DELETE" }); } catch (e) { /* ignore */ }
        refreshHistory();
      }
    });
    try { await Promise.all([loadProviders(), loadSamples()]); }
    catch (e) { showFormError(e.message); }
    refreshHistory();
  }
  init();
})();
