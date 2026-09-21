// model-list.js - DANH SÁCH CHỌN MODEL dùng chung.
//
// Hai chỗ trong app cần đúng một danh sách này: thanh model dưới khung chat
// (model-picker.js) và ô Model trong Cài đặt trợ lý (studio.js). Tới 0.62.2 ô của trợ lý là
// một <select> thuần: không có ô tìm, và nhà chưa cắm key thì bị LỌC MẤT hẳn thay vì hiện ra
// có ổ khoá - nên người dùng không biết là có nhà đó mà chưa mở được (chủ repo báo 21/09).
//
// Đáng lẽ chỉ cần chép markup sang, nhưng chép là hai bản trôi lệch nhau ngay lần sửa sau.
// Nên phần thân (ô tìm + nhóm theo nhà + hàng model + hàng khoá) nằm ở đây, mỗi bên tự lo
// phần riêng của mình: thanh chat thêm hàng Effort và chuyện ghim phiên, trợ lý thêm hàng
// "Mặc định" và hàng "model đang lưu".
//
// CSS vẫn là các lớp .mb-* trong style.css, không đẻ bộ lớp thứ hai.
(function () {
  "use strict";

  const CACHE = {};                     // provider id -> {models, ts}
  const CACHE_MS = 5 * 60 * 1000;       // không giữ catalog cũ suốt cả tab

  const esc = (s) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  const T = (k) => (window.t ? window.t(k) : k);
  const IC = (n, o) => (window.ic ? window.ic(n, o) : "");

  // Danh sách model của một nhà. Hỏng thì trả mảng rỗng chứ không ném: một nhà chết không
  // được kéo cả bảng chọn chết theo.
  async function models(pid) {
    const c = CACHE[pid];
    if (c && Date.now() - c.ts < CACHE_MS) return c.models;
    try {
      // Codex: catalog tĩnh của nó vốn rỗng nên phải ép lấy live.
      const force = pid === "openai-oauth" ? "&refresh=1" : "";
      const d = await (await fetch("/provider/models?provider=" + encodeURIComponent(pid) + force)).json();
      CACHE[pid] = { models: d.models || [], ts: Date.now() };
    } catch (e) {
      CACHE[pid] = { models: [], ts: Date.now() };
    }
    return CACHE[pid].models;
  }

  function clearCache() { Object.keys(CACHE).forEach((k) => delete CACHE[k]); }

  // Dựng HTML thân bảng chọn. Trả chuỗi; người gọi tự nhét vào khung của mình rồi tự bắt sự
  // kiện (cả hai bên đều đã có vòng bắt click riêng, gắn thêm ở đây là bắt hai lần).
  //
  // o = {
  //   providers  : [{id, label, configured, ...}] - NGUYÊN danh sách, kể cả nhà chưa cắm key
  //                (chúng hiện ra có ổ khoá, đó mới là điều người dùng cần thấy)
  //   expanded   : id nhà đang sổ ra
  //   filter     : chữ đang lọc
  //   selected   : {provider, model} đang chọn, hoặc null
  //   searchId   : id cho ô tìm (mỗi khung một id, kẻo hai khung cùng mở là trùng)
  //   short      : (id) => nhãn hiển thị của một model; mặc định để nguyên
  //   mark       : (p)  => HTML dán sau tên nhà (thanh chat dùng để đánh dấu model chính)
  //   limit      : trần số model mỗi nhà, mặc định 60
  //   extraTop   : HTML chèn ngay dưới ô tìm (hàng "Mặc định", hàng "model đang lưu"...)
  // }
  async function render(o) {
    o = o || {};
    const provs = o.providers || [];
    const sel = o.selected || {};
    const short = o.short || ((x) => x);
    const mark = o.mark || (() => "");
    const limit = o.limit || 60;
    const q = (o.filter || "").toLowerCase();

    let html = `<input class="mb-search" id="${esc(o.searchId || "mlSearch")}" `
      + `placeholder="${esc(T("mpick.search_ph"))}" value="${esc(o.filter || "")}">`;
    html += o.extraTop || "";

    for (const p of provs) {
      const on = !!p.configured;
      // Nhà chưa cắm key: KHÔNG có data-prov (bấm vào không sổ ra được) + ổ khoá + một dòng
      // chỉ đúng chỗ đi mở khoá. Đây chính là phần ô <select> cũ làm mất.
      html += `<div class="mb-prov ${on ? "" : "off"}" data-prov="${on ? esc(p.id) : ""}">`
        + `<span>${p.label}${mark(p)}</span>`
        + `<span>${on ? IC(p.id === o.expanded ? "chevron-down" : "chevron-right")
                      : IC("lock", { cls: "ic-dim" })}</span></div>`;
      if (!on) {
        html += `<div class="mb-link" data-goto="models">+ ${esc(T("mpick.add_key"))}</div>`;
        continue;
      }
      if (p.id !== o.expanded) continue;
      let ids = await models(p.id);
      if (q) ids = ids.filter((id) => id.toLowerCase().includes(q));
      if (!ids.length) {
        html += `<div class="mb-empty">${esc(T(q ? "mpick.no_match" : "mpick.no_list"))}</div>`;
      }
      for (const id of ids.slice(0, limit)) {
        const cur = p.id === sel.provider && id === sel.model;
        html += `<div class="mb-item ${cur ? "cur" : ""}" data-prov="${esc(p.id)}" `
          + `data-model="${esc(id)}"><span class="tick">`
          + `${cur ? IC("check", { cls: "ic-ok" }) : ""}</span><span>${esc(short(id))}</span></div>`;
      }
    }
    return html;
  }

  window.JavisModelList = { models, render, clearCache };
})();
