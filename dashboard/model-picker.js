// Per-chat Auto, explicit model pins and the shared default.
// Model selection never changes the global model settings.
(function () {
  "use strict";

  // Thang độ sâu suy nghĩ - phải KHỚP engine.REASONING_LEVELS bên server, nếu không người dùng
  // chọn xong server lọc về "off" mà giao diện vẫn khoe đang bật.
  const EFFORT = [["off", "models.r_off"], ["low", "models.r_low"], ["medium", "models.r_med"],
                  ["high", "models.r_high"], ["xhigh", "models.r_xhigh"], ["ultra", "models.r_ultra"]];
  let state = { providers: [], main: { provider: "", model: "" }, reasoning: "off" };
  let sessionPin = null;   // {provider, model} phiên đang mở đã ghim; null = theo mặc định chung
  let pinBroken = false;   // phiên có ghim nhưng ghim HỎNG (provider mất key) - server đang chạy mặc định chung
  let pinSid = null;       // phiên mà sessionPin đang nói về (chống vẽ nhầm khi đổi phiên nhanh)
  let pendingPin = null;   // model chọn khi CHƯA có phiên (chat trống) - áp ngay khi mint id
  let expanded = null;     // provider đang mở rộng trong popover; "" = đã thu hết (bấm lại tên nhà)
  let filter = "";

  const short = (m) => (m || "").split("/").pop().replace(/^(claude-|gpt-)/, "").slice(0, 26) || window.t("models.mp_default");
  const provShort = (lbl) => (lbl || "").split(" ")[0];
  const $ = (id) => document.getElementById(id);
  const curSid = () => { try { return (window.JavisSessions && window.JavisSessions.current()) || null; } catch (e) { return null; } };
  const curBrain = () => { try { return (window.JavisSessions && window.JavisSessions.brain()) || ""; } catch (e) { return ""; } };
  // Model ĐANG HIỆU LỰC cho khung chat trước mặt: ghim của phiên thắng mặc định chung.
  const effective = () => sessionPin || pendingPin || state.main;
  let routingMode = "default";
  let pendingSave = null;
  const pendingKey = () => "javis-chat-model-pending:" + curBrain();
  function rememberPending(value) {
    pendingPin = value;
    try { if (value) localStorage.setItem(pendingKey(), JSON.stringify(value)); else localStorage.removeItem(pendingKey()); } catch (e) {}
  }

  async function saveModel(patch) {
    const fd = new FormData();
    fd.append("section", "model");
    fd.append("data", JSON.stringify(patch));
    try { await fetch("/settings", { method: "POST", body: fd }); } catch (e) {}
  }

  async function pinToSession(sid, prov, model, mode = "pinned") {
    const fd = new FormData();
    fd.append("provider", prov || "");
    fd.append("routing_mode", mode);
    fd.append("model", model || "");
    fd.append("brain", curBrain());   // phiên chưa có hàng trong DB thì server tự tạo
    const r = await fetch(`/sessions/${encodeURIComponent(sid)}/model`, { method: "POST", body: fd });
    if (!r.ok) { const d = await r.json(); throw new Error(d.error || window.t("mpick.save_failed")); }
    return r.json();
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
    if (!sid) {
      sessionPin = null; pinBroken = false; routingMode = "default";
      try { pendingPin = JSON.parse(localStorage.getItem(pendingKey()) || "null"); } catch (e) { pendingPin = null; }
      if (pendingPin) routingMode = pendingPin.routing_mode || "pinned";
      return;
    }
    pendingPin = null;
    try {
      const r = await fetch(`/sessions/${encodeURIComponent(sid)}/meta`);
      const d = r.ok ? await r.json() : null;
      if (pinSid !== sid) return;   // user đã nhảy sang phiên khác trong lúc chờ
      // pin_ok=false: ghim còn trong DB nhưng không chạy được (provider mất key) -
      // server đang rơi về mặc định chung, nên hiển thị cũng phải theo mặc định chung.
      routingMode = (d && d.routing_mode) || (d && d.pinned_provider ? "pinned" : "default");
      pinBroken = !!(d && d.pinned_provider && d.pin_ok === false);
      sessionPin = (d && d.pinned_provider && !pinBroken)
        ? { provider: d.pinned_provider, model: d.pinned_model || "" } : null;
    } catch (e) { if (pinSid === sid) { sessionPin = null; pinBroken = false; } }
  }

  function renderBar() {
    const eff = effective();
    const p = state.providers.find((x) => x.id === eff.provider);
    const mt = $("mbModelTxt"), et = $("mbEffortTxt");
    if (routingMode === "auto") {
      if (mt) { mt.textContent = window.t("mpick.auto"); mt.title = window.t("mpick.auto_title"); }
      if (et) et.textContent = window.t("mpick.effort_auto");
      return;
    }
    if (mt) {
      mt.textContent = (p ? provShort(p.label) : "Model") + " · " + short(eff.model)
        + (sessionPin ? " · " + window.t("mpick.pin") : pinBroken ? " · " + window.t("mpick.pin_broken") : "");
      mt.title = sessionPin
        ? window.t("mpick.pin_title")
        : pinBroken
          ? window.t("mpick.pin_broken_title")
          : window.t("mpick.follow_default");
    }
    if (et) et.textContent = "Effort: " + window.t((EFFORT.find((e) => e[0] === state.reasoning) || EFFORT[0])[1]);
  }

  // Màn cảm ứng (điện thoại, máy tính bảng): focus một ô nhập là bật bàn phím ảo.
  const camUng = () => { try { return window.matchMedia("(pointer: coarse)").matches; } catch (e) { return false; } };
  let luotVe = 0;   // chỉ lượt vẽ MỚI NHẤT được ghi vào popup (lượt chờ mạng về muộn thì bỏ)

  async function renderPop() {
    const pop = $("mbPop");
    if (!pop) return;
    if (expanded == null) expanded = state.main.provider || "anthropic-cli";
    const luot = ++luotVe;
    // Nhà nào chưa có danh sách thì vẽ khung + dòng "đang tải" NGAY, rồi vẽ lại khi mạng về
    // (o.cho). Trước đây popup mở ra trống trơn trong lúc chờ (Codex mất vài giây).
    const o = {
    // Thân bảng (ô tìm + nhà + model + hàng khoá) dựng bởi model-list.js, dùng CHUNG với ô
    // Model của trợ lý bên Studio. Ở đây chỉ nối thêm hàng Effort - thứ duy nhất riêng của
    // thanh chat.
      providers: state.providers,
      expanded, filter,
      selected: routingMode === "auto" ? {} : effective(),
      searchId: "mbSearch",
      short,
      mark: (p) => (p.is_main ? " " + ic("check", { cls: "ic-ok" }) : ""),
      noWait: true,
    };
    let html = `<div class="mb-eff-row"><button class="mb-eff-btn ${routingMode === "auto" ? "cur" : ""}" data-routing="auto">${window.t("mpick.auto")}</button><button class="mb-eff-btn ${routingMode === "default" ? "cur" : ""}" data-routing="default">${window.t("mpick.follow_default")}</button></div>`;
    html += await window.JavisModelList.render(o);
    if (luot !== luotVe || pop.hidden) return;
    html += `<div class="mb-eff-row"><span class="lbl">Effort</span>` +
      EFFORT.map(([v, l]) => `<button class="mb-eff-btn ${state.reasoning === v ? "cur" : ""}" data-eff="${v}">${window.t(l)}</button>`).join("") +
      `</div>`;
    // Ô tìm đang được gõ thì giữ con trỏ ở đó sau khi vẽ lại. Mới MỞ bảng thì chỉ tự focus
    // trên máy có bàn phím thật: trên điện thoại focus là bật bàn phím ảo che nửa bảng, người
    // dùng chỉ muốn bấm chọn model (chủ repo báo 27/09 "tự nhảy lên bàn phím").
    const dangGo = document.activeElement && document.activeElement.id === "mbSearch";
    pop.innerHTML = html;
    const se = $("mbSearch");
    if (se) {
      se.oninput = () => { filter = se.value; renderPop(); };
      if (dangGo || !camUng()) { se.focus(); se.selectionStart = se.selectionEnd = se.value.length; }
    }
    if (o.cho.length) {
      await Promise.all(o.cho);
      if (luot === luotVe && !pop.hidden) renderPop();
    }
  }

  function open() {
    const pop = $("mbPop");
    if (!pop) return;
    // Đang gõ trong ô chat mà bấm chip model: hạ bàn phím xuống trước, kẻo bàn phím che bảng.
    if (camUng()) {
      const a = document.activeElement;
      if (a && a !== document.body && typeof a.blur === "function") a.blur();
    }
    pop.hidden = false; renderPop();
  }
  function close() { const pop = $("mbPop"); if (pop) pop.hidden = true; }
  function isOpen() { const pop = $("mbPop"); return pop && !pop.hidden; }

  // Explicit model selection pins only this conversation.
  async function chonModel(prov, model) {
    const sid = curSid();
    if (sid) await pinToSession(sid, prov, model);
    routingMode = "pinned";
    if (sid) {
      sessionPin = { provider: prov, model: model };
      pinBroken = false;   // ghim mới đè ghim hỏng cũ
      pinSid = sid;
      rememberPending(null);
    } else {
      // Chat trống chưa mint id: nhớ lựa chọn, app.js gọi claimPending(sid) lúc gửi
      // tin đầu để phiên mới sinh ra đã mang đúng ghim.
      rememberPending({ provider: prov, model: model, routing_mode: "pinned" });
      sessionPin = null;
    }
    await loadState(); renderBar();
  }

  // `/model <tên>`: tìm trong model của các nhà ĐÃ KẾT NỐI. Khớp NGUYÊN id thì thắng ngay; nếu
  // không thì khớp một phần, và chỉ đổi khi ra ĐÚNG MỘT model - đoán bừa giữa hai nhà là đổi
  // nhầm bộ não. Trả {kind: "one"|"many"|"none", prov, model, ds}.
  async function timModel(query) {
    const q = String(query || "").trim().toLowerCase();
    if (!q) return { kind: "none" };
    const nhaOk = state.providers.filter((p) => p.configured);
    const dem = await Promise.all(nhaOk.map(async (p) => {
      let ids = [];
      try { ids = (window.JavisModelList ? await window.JavisModelList.models(p.id) : p.models) || []; }
      catch (e) { ids = p.models || []; }
      return { p, ids: ids.map((m) => (typeof m === "string" ? m : (m && (m.id || m.name)) || "")).filter(Boolean) };
    }));
    const dung = [], gan = [];
    dem.forEach(({ p, ids }) => ids.forEach((id) => {
      const k = id.toLowerCase();
      if (k === q) dung.push({ prov: p.id, model: id, label: p.label });
      else if (k.includes(q)) gan.push({ prov: p.id, model: id, label: p.label });
    }));
    const kq = dung.length ? dung : gan;
    if (kq.length === 1) return { kind: "one", prov: kq[0].prov, model: kq[0].model, label: kq[0].label };
    if (kq.length > 1) return { kind: "many", ds: kq.slice(0, 6).map((x) => (provShort(x.label) + " " + x.model)) };
    return { kind: "none" };
  }

  document.addEventListener("click", async (e) => {
    if (e.target.closest("#mbOpen")) { isOpen() ? close() : open(); return; }
    if (!e.target.closest("#modelBar") && !e.target.closest("#mbPop") && !e.target.closest("#mbOpen")) { if (isOpen()) close(); return; }

    const goto = e.target.closest("[data-goto]");
    if (goto) {
      close();
      try { if (window.Alpine) Alpine.store("nav").go(goto.dataset.goto); } catch (er) {}
      return;
    }
    const route = e.target.closest("[data-routing]");
    if (route) {
      const mode = route.dataset.routing;
      const sid = curSid();
      try {
        if (sid) await pinToSession(sid, "", "", mode);
        routingMode = mode; sessionPin = null; pinBroken = false; pinSid = sid;
        rememberPending(sid ? null : { routing_mode: mode });
        renderBar(); close();
      } catch (error) { alert(error.message); }
      return;
    }
    const item = e.target.closest(".mb-item");
    if (item) {
      try { await chonModel(item.dataset.prov, item.dataset.model); } catch (error) { alert(error.message); return; }
      close();
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
    // Bấm lại tên nhà đang mở là THU lại: OpenRouter hơn 300 model, không thu được thì phải
    // cuộn hết mới sang được nhà khác (chủ repo báo 27/09).
    if (prov && prov.dataset.prov) {
      expanded = expanded === prov.dataset.prov ? "" : prov.dataset.prov;
      renderPop(); return;
    }
  });

  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && isOpen()) close(); });

  window.initModelBar = async function () {
    await loadState(); await loadSessionPin(); renderBar();
    // Tải sẵn danh sách của nhà đang dùng lúc rảnh, để lần bấm chip đầu tiên mở ra có ngay.
    try { const pid = state.main.provider; if (pid && window.JavisModelList) window.JavisModelList.models(pid); } catch (e) {}
  };

  // Phiên mới mint id xong (app.js gọi ngay lúc gửi tin đầu): model đã chọn khi khung
  // còn trống đi theo phiên vừa sinh, không bị phiên khác đổi mặc định chung đè mất.
  window.JavisModelBar = {
    claimPending: async function (sid) {
      if (pendingSave) return pendingSave;
      if (!pendingPin || !sid) return;
      sessionPin = pendingPin; pinSid = sid;
      pendingSave = pinToSession(sid, pendingPin.provider, pendingPin.model, pendingPin.routing_mode || "pinned");
      try { await pendingSave; } finally { pendingSave = null; }
      routingMode = pendingPin.routing_mode || "pinned";
      if (routingMode !== "pinned") sessionPin = null;
      rememberPending(null);
      renderBar();
    },
    // Lệnh `/model` của khung chat (chat-lenh.js): mở bảng chọn, đổi theo tên, hoặc cho biết model hiện tại.
    // Trả true nếu bảng chọn có mặt để mở (thanh model ẩn thì false, chỗ gọi tự nói model hiện tại).
    open: function () { if (!$("mbPop")) return false; open(); return true; },
    chon: async function (query) {
      const r = await timModel(query);
      if (r.kind === "one") { await chonModel(r.prov, r.model); return { kind: "one", label: provShort(r.label), model: r.model }; }
      return r;
    },
    hienTai: function () {
      const eff = effective();
      const p = state.providers.find((x) => x.id === eff.provider);
      return { label: p ? provShort(p.label) : eff.provider, model: eff.model || "" };
    },
    // app.js gọi mỗi lần GỬI TIN: server đóng dấu model đang chạy cho phiên ngay lượt
    // đầu, nên bar phải chuyển sang "ghim" tại chỗ - không chờ tới lần đổi phiên mới
    // vẽ lại, kẻo trong lúc đó đổi mặc định chung ở trang Models là bar nói sai.
    noteStamped: function (sid) {
      if (!sid || routingMode !== "pinned" || (sessionPin && pinSid === sid)) return;
      sessionPin = { provider: state.main.provider, model: state.main.model };
      pinBroken = false; pinSid = sid;
      renderBar();
    },
  };

  // Đổi phiên (mở phiên cũ, chat mới, xoá phiên) → hỏi lại ghim của phiên rồi vẽ lại.
  window.addEventListener("javis:sessions-changed", async () => { await loadSessionPin(); renderBar(); });

  // Từ điển về (fetch bất đồng bộ, thường SAU khi chip model đã vẽ) hoặc người dùng đổi
  // ngôn ngữ giao diện: vẽ lại chip, và vẽ lại cả bảng chọn nếu nó đang mở.
  window.addEventListener("javis:i18n", () => {
    renderBar();
    if (isOpen()) renderPop();
  });

  if (document.readyState !== "loading") window.initModelBar();
  else document.addEventListener("DOMContentLoaded", () => window.initModelBar());
})();
