// model-picker.js — đổi model (đa nhà cung cấp) + effort ngay trên khung chat.
// Thuần frontend: đọc/ghi qua /settings + /provider/models (đã có sẵn ở backend).
//
// MODEL THEO PHIÊN (16/08): đổi model NGAY TRONG một phiên chat = ghim model đó cho
// riêng phiên (POST /sessions/{id}/model) + vẫn cập nhật mặc định chung như cũ. Mở lại
// phiên cũ là thấy đúng model đã chọn trong nó; đổi model ở phiên/tab khác không kéo
// phiên đã ghim đổi theo. Phiên chưa từng đổi tay vẫn bám mặc định chung.
(function () {
  "use strict";

  // Thang độ sâu suy nghĩ - phải KHỚP engine.REASONING_LEVELS bên server, nếu không người dùng
  // chọn xong server lọc về "off" mà giao diện vẫn khoe đang bật.
  const EFFORT = [["off", "Tắt"], ["low", "Thấp"], ["medium", "Vừa"],
                  ["high", "Cao"], ["xhigh", "Rất cao"], ["ultra", "Tối đa"]];
  const modelCache = {};   // provider id -> {models, ts}; không giữ catalog cũ suốt cả tab
  const MODEL_CACHE_MS = 5 * 60 * 1000;
  let state = { providers: [], main: { provider: "", model: "" }, reasoning: "off" };
  let sessionPin = null;   // {provider, model} phiên đang mở đã ghim; null = theo mặc định chung
  let pinBroken = false;   // phiên có ghim nhưng ghim HỎNG (provider mất key) - server đang chạy mặc định chung
  let pinSid = null;       // phiên mà sessionPin đang nói về (chống vẽ nhầm khi đổi phiên nhanh)
  let pendingPin = null;   // model chọn khi CHƯA có phiên (chat trống) - áp ngay khi mint id
  let expanded = null;     // provider đang mở rộng trong popover
  let filter = "";

  const short = (m) => (m || "").split("/").pop().replace(/^(claude-|gpt-)/, "").slice(0, 26) || "mặc định";
  const provShort = (lbl) => (lbl || "").split(" ")[0];
  const $ = (id) => document.getElementById(id);
  const curSid = () => { try { return (window.JavisSessions && window.JavisSessions.current()) || null; } catch (e) { return null; } };
  const curBrain = () => { try { return (window.JavisSessions && window.JavisSessions.brain()) || ""; } catch (e) { return ""; } };
  // Model ĐANG HIỆU LỰC cho khung chat trước mặt: ghim của phiên thắng mặc định chung.
  const effective = () => sessionPin || state.main;

  async function saveModel(patch) {
    const fd = new FormData();
    fd.append("section", "model");
    fd.append("data", JSON.stringify(patch));
    try { await fetch("/settings", { method: "POST", body: fd }); } catch (e) {}
  }

  async function pinToSession(sid, prov, model) {
    const fd = new FormData();
    fd.append("provider", prov);
    fd.append("model", model || "");
    fd.append("brain", curBrain());   // phiên chưa có hàng trong DB thì server tự tạo
    try { await fetch(`/sessions/${encodeURIComponent(sid)}/model`, { method: "POST", body: fd }); } catch (e) {}
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

  // Hỏi server "phiên đang mở có ghim model riêng không". Đổi phiên nhanh tay thì chỉ
  // kết quả của phiên MỚI NHẤT được vẽ (so pinSid trước khi dùng).
  async function loadSessionPin() {
    const sid = curSid();
    pinSid = sid;
    if (!sid) { sessionPin = null; pinBroken = false; pendingPin = null; return; }
    pendingPin = null;
    try {
      const r = await fetch(`/sessions/${encodeURIComponent(sid)}/meta`);
      const d = r.ok ? await r.json() : null;
      if (pinSid !== sid) return;   // user đã nhảy sang phiên khác trong lúc chờ
      // pin_ok=false: ghim còn trong DB nhưng không chạy được (provider mất key) -
      // server đang rơi về mặc định chung, nên hiển thị cũng phải theo mặc định chung.
      pinBroken = !!(d && d.pinned_provider && d.pin_ok === false);
      sessionPin = (d && d.pinned_provider && !pinBroken)
        ? { provider: d.pinned_provider, model: d.pinned_model || "" } : null;
    } catch (e) { if (pinSid === sid) { sessionPin = null; pinBroken = false; } }
  }

  function renderBar() {
    const eff = effective();
    const p = state.providers.find((x) => x.id === eff.provider);
    const mt = $("mbModelTxt"), et = $("mbEffortTxt");
    if (mt) {
      mt.textContent = (p ? provShort(p.label) : "Model") + " · " + short(eff.model)
        + (sessionPin ? " · ghim" : pinBroken ? " · ghim hỏng" : "");
      mt.title = sessionPin
        ? "Model ghim riêng cho phiên chat này (đổi ở phiên khác không ảnh hưởng)"
        : pinBroken
          ? "Model ghim của phiên không còn dùng được (provider đã bị gỡ key) - đang chạy model mặc định chung"
          : "Theo model mặc định chung";
    }
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
          const _eff = effective();
          const cur = p.id === _eff.provider && id === _eff.model;
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
      // Ghi mặc định chung (chat mới sau này theo cái vừa chọn) + GHIM cho phiên đang
      // mở (phiên này giữ đúng model kể cả khi mặc định chung bị đổi ở chỗ khác).
      await saveModel({ main: { provider: item.dataset.prov, model: item.dataset.model } });
      const sid = curSid();
      if (sid) {
        sessionPin = { provider: item.dataset.prov, model: item.dataset.model };
        pinBroken = false;   // ghim mới đè ghim hỏng cũ
        pinSid = sid;
        await pinToSession(sid, item.dataset.prov, item.dataset.model);
      } else {
        // Chat trống chưa mint id: nhớ lựa chọn, app.js gọi claimPending(sid) lúc gửi
        // tin đầu để phiên mới sinh ra đã mang đúng ghim.
        pendingPin = { provider: item.dataset.prov, model: item.dataset.model };
        sessionPin = null;
      }
      await loadState(); renderBar(); close();
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

  window.initModelBar = async function () { await loadState(); await loadSessionPin(); renderBar(); };

  // Phiên mới mint id xong (app.js gọi ngay lúc gửi tin đầu): model đã chọn khi khung
  // còn trống đi theo phiên vừa sinh, không bị phiên khác đổi mặc định chung đè mất.
  window.JavisModelBar = {
    claimPending: function (sid) {
      if (!pendingPin || !sid) return;
      sessionPin = pendingPin; pinSid = sid;
      pinToSession(sid, pendingPin.provider, pendingPin.model);
      pendingPin = null;
      renderBar();
    },
    // app.js gọi mỗi lần GỬI TIN: server đóng dấu model đang chạy cho phiên ngay lượt
    // đầu, nên bar phải chuyển sang "ghim" tại chỗ - không chờ tới lần đổi phiên mới
    // vẽ lại, kẻo trong lúc đó đổi mặc định chung ở trang Models là bar nói sai.
    noteStamped: function (sid) {
      if (!sid || (sessionPin && pinSid === sid)) return;
      sessionPin = { provider: state.main.provider, model: state.main.model };
      pinBroken = false; pinSid = sid;
      renderBar();
    },
  };

  // Đổi phiên (mở phiên cũ, chat mới, xoá phiên) → hỏi lại ghim của phiên rồi vẽ lại.
  window.addEventListener("javis:sessions-changed", async () => { await loadSessionPin(); renderBar(); });

  if (document.readyState !== "loading") window.initModelBar();
  else document.addEventListener("DOMContentLoaded", () => window.initModelBar());
})();
