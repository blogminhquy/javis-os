// model-picker.js — đổi model (đa nhà cung cấp) + effort ngay trên khung chat.
// Thuần frontend: đọc/ghi qua /settings + /provider/models (đã có sẵn ở backend).
(function () {
  "use strict";

  // Thang độ sâu suy nghĩ - phải KHỚP engine.REASONING_LEVELS bên server, nếu không người dùng
  // chọn xong server lọc về "off" mà giao diện vẫn khoe đang bật.
  const EFFORT = [["off", "Tắt"], ["low", "Thấp"], ["medium", "Vừa"],
                  ["high", "Cao"], ["xhigh", "Rất cao"], ["ultra", "Tối đa"]];
  const modelCache = {};   // provider id -> {models, ts}; không giữ catalog cũ suốt cả tab
  const MODEL_CACHE_MS = 5 * 60 * 1000;
  let state = { providers: [], main: { provider: "", model: "" }, reasoning: "off" };
  let expanded = null;     // provider đang mở rộng trong popover
  let filter = "";

  const short = (m) => (m || "").split("/").pop().replace(/^(claude-|gpt-)/, "").slice(0, 26) || "mặc định";
  const provShort = (lbl) => (lbl || "").split(" ")[0];
  const $ = (id) => document.getElementById(id);

  async function saveModel(patch) {
    const fd = new FormData();
    fd.append("section", "model");
    fd.append("data", JSON.stringify(patch));
    try { await fetch("/settings", { method: "POST", body: fd }); } catch (e) {}
  }

  async function loadState() {
    try {
      const s = await (await fetch("/settings")).json();
      const m = s.model || {};
      state.providers = m.providers || [];
      state.main = m.main || { provider: "anthropic-cli", model: "" };
      state.reasoning = m.reasoning || "off";
    } catch (e) {}
  }

  function renderBar() {
    const p = state.providers.find((x) => x.id === state.main.provider);
    const mt = $("mbModelTxt"), et = $("mbEffortTxt");
    if (mt) mt.textContent = (p ? provShort(p.label) : "Model") + " · " + short(state.main.model);
    if (et) et.textContent = "Effort: " + (EFFORT.find((e) => e[0] === state.reasoning) || EFFORT[0])[1];
  }

  async function fetchModels(pid) {
    const cached = modelCache[pid];
    if (cached && Date.now() - cached.ts < MODEL_CACHE_MS) return cached.models;
    try {
      const force = pid === "openai-oauth" ? "&refresh=1" : "";
      const d = await (await fetch("/provider/models?provider=" + encodeURIComponent(pid) + force)).json();
      modelCache[pid] = { models: d.models || [], ts: Date.now() };
    } catch (e) { modelCache[pid] = { models: [], ts: Date.now() }; }
    return modelCache[pid].models;
  }

  async function renderPop() {
    const pop = $("mbPop");
    if (!pop) return;
    if (!expanded) expanded = state.main.provider || "anthropic-cli";
    let html = `<input class="mb-search" id="mbSearch" placeholder="Tìm model..." value="${filter.replace(/"/g, "&quot;")}">`;
    for (const p of state.providers) {
      const on = !!p.configured;
      html += `<div class="mb-prov ${on ? "" : "off"}" data-prov="${on ? p.id : ""}">
                 <span>${p.label}${p.is_main ? " " + ic("check", { cls: "ic-ok" }) : ""}</span><span>${on ? ic(p.id === expanded ? "chevron-down" : "chevron-right") : ic("lock", { cls: "ic-dim" })}</span></div>`;
      if (!on) { html += `<div class="mb-link" data-goto="models">+ Thêm API key ở trang Models để mở khoá</div>`; continue; }
      if (p.id === expanded) {
        let ids = await fetchModels(p.id);
        if (filter) ids = ids.filter((id) => id.toLowerCase().includes(filter.toLowerCase()));
        if (!ids.length) {
          html += `<div class="mb-empty">${filter ? "Không có model khớp." : "Chưa lấy được danh sách model."}</div>`;
        }
        for (const id of ids.slice(0, 60)) {
          const cur = p.id === state.main.provider && id === state.main.model;
          html += `<div class="mb-item ${cur ? "cur" : ""}" data-prov="${p.id}" data-model="${id.replace(/"/g, "&quot;")}">
                     <span class="tick">${cur ? ic("check", { cls: "ic-ok" }) : ""}</span><span>${short(id)}</span></div>`;
        }
      }
    }
    html += `<div class="mb-eff-row"><span class="lbl">Effort</span>` +
      EFFORT.map(([v, l]) => `<button class="mb-eff-btn ${state.reasoning === v ? "cur" : ""}" data-eff="${v}">${l}</button>`).join("") +
      `</div>`;
    pop.innerHTML = html;
    const se = $("mbSearch");
    if (se) {
      se.oninput = () => { filter = se.value; renderPop(); };
      // giữ con trỏ ở ô tìm khi gõ lại
      se.focus(); se.selectionStart = se.selectionEnd = se.value.length;
    }
  }

  function open() { const pop = $("mbPop"); if (pop) { pop.hidden = false; renderPop(); } }
  function close() { const pop = $("mbPop"); if (pop) pop.hidden = true; }
  function isOpen() { const pop = $("mbPop"); return pop && !pop.hidden; }

  document.addEventListener("click", async (e) => {
    if (e.target.closest("#mbOpen")) { isOpen() ? close() : open(); return; }
    if (!e.target.closest("#modelBar") && !e.target.closest("#mbPop") && !e.target.closest("#mbOpen")) { if (isOpen()) close(); return; }

    const goto = e.target.closest("[data-goto]");
    if (goto) {
      close();
      try { if (window.Alpine) Alpine.store("nav").go(goto.dataset.goto); } catch (er) {}
      return;
    }
    const item = e.target.closest(".mb-item");
    if (item) {
      await saveModel({ main: { provider: item.dataset.prov, model: item.dataset.model } });
      await loadState(); renderBar(); close();
      if (window.refreshEngineBadge) window.refreshEngineBadge();
      return;
    }
    const eff = e.target.closest(".mb-eff-btn");
    if (eff) {
      state.reasoning = eff.dataset.eff;      // cập nhật lạc quan để UI phản hồi ngay
      await saveModel({ reasoning: eff.dataset.eff });
      renderBar(); renderPop();
      return;
    }
    const prov = e.target.closest(".mb-prov");
    if (prov && prov.dataset.prov) { expanded = prov.dataset.prov; renderPop(); return; }
  });

  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && isOpen()) close(); });

  window.initModelBar = async function () { await loadState(); renderBar(); };
  if (document.readyState !== "loading") window.initModelBar();
  else document.addEventListener("DOMContentLoaded", () => window.initModelBar());
})();
