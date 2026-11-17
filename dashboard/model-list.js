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
  //
  // Cache HẾT HẠN thì trả ngay bản cũ và làm mới NGẦM (stale-while-revalidate). Trước đây
  // hết 5 phút là lần bấm sau phải chờ trọn một lượt tải live - với Codex (ép refresh=1) là
  // vài giây popup trống trơn, chủ repo báo 27/09 "ấn vào danh sách model load rất chậm".
  const DANG_TAI = {};                  // provider id -> Promise đang bay (gộp các lần gọi trùng)
  // 2026-11-13: an EMPTY answer is not a list to keep. It used to sit in the cache for five minutes and then be
  // handed out once more while the refresh ran, so one slow gateway (or a card fixed a moment ago on the Models
  // page) left the picker saying "no model list" long after the list was there. An empty entry is asked again on
  // the next open, and it carries the server's reason so the picker can say WHY (`why`).
  const EMPTY_MS = 4000;                // only spares the server a burst of repeats while one popup redraws
  let GEN = 0;                          // bumped by clearCache: an answer asked for before it is not kept
  function tai(pid) {
    if (DANG_TAI[pid]) return DANG_TAI[pid];
    // Codex: catalog tĩnh của nó vốn rỗng nên phải ép lấy live.
    const force = pid === "openai-oauth" ? "&refresh=1" : "";
    const gen = GEN;
    const p = fetch("/provider/models?provider=" + encodeURIComponent(pid) + force)
      .then((r) => r.json())
      .then((d) => {
        const ids = (d && d.models) || [];
        return { models: ids, ts: Date.now(), why: ids.length ? "" : String((d && d.error) || "") };
      })
      .catch(() => {
        // The network failed: a list already in hand is worth more than an empty one, and is tried again at the
        // usual pace instead of on every open.
        const c = gen === GEN ? CACHE[pid] : null;
        return c && c.models.length ? { models: c.models, ts: Date.now(), why: "" } : { models: [], ts: Date.now(), why: "" };
      })
      .then((e) => {
        if (DANG_TAI[pid] === p) delete DANG_TAI[pid];
        if (gen === GEN) CACHE[pid] = e;   // the Models page changed a key meanwhile: this answer is the old one
        return e.models;
      });
    DANG_TAI[pid] = p;
    return p;
  }
  async function models(pid) {
    const c = CACHE[pid];
    if (c) {
      const age = Date.now() - c.ts;
      if (!c.models.length) return age >= EMPTY_MS ? tai(pid) : c.models;
      if (age >= CACHE_MS) tai(pid);
      return c.models;
    }
    return tai(pid);
  }
  /** Danh sách đang có sẵn (kể cả đã cũ), hoặc null khi chưa từng tải: để người gọi biết có
   *  phải chờ mạng hay không mà vẽ khung trước. An empty answer that is due for another try counts as "not
   *  loaded", so the caller draws "loading" and asks again instead of repeating the old empty list. */
  function peek(pid) {
    const c = CACHE[pid];
    if (!c) return null;
    if (!c.models.length && Date.now() - c.ts >= EMPTY_MS) return null;
    return c.models;
  }
  /** Why the last answer for this provider was empty (the server's own sentence), or "". */
  function why(pid) { return (CACHE[pid] && CACHE[pid].why) || ""; }

  function clearCache() {
    GEN++;
    Object.keys(CACHE).forEach((k) => delete CACHE[k]);
    Object.keys(DANG_TAI).forEach((k) => delete DANG_TAI[k]);
  }

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
  //   noWait     : chưa có danh sách của nhà đang mở thì vẽ dòng "đang tải" chứ không chờ
  // }
  //
  // Sau khi gọi, o.cho là mảng Promise của những nhà còn đang tải (lúc tìm kiếm, hoặc noWait).
  // Người gọi đợi chúng rồi vẽ lại; KHÔNG chặn cả bảng chờ mạng.
  //
  // Ba luật chủ repo chốt 27/09:
  // - Nhà ĐÃ KẾT NỐI đứng đầu, nhà còn khoá xuống dưới (giữ thứ tự gốc trong mỗi nhóm).
  //   Trước đây nhà khoá xen giữa, phải cuộn qua mới thấy nhà dùng được.
  // - expanded rỗng = không nhà nào sổ ra. Bấm lại tên nhà đang mở là thu lại (người gọi đặt
  //   expanded = ""), để OpenRouter hơn 300 model không chắn lối sang nhà khác.
  // - Có chữ tìm thì tìm TRÊN MỌI nhà đã kết nối, không chỉ nhà đang mở. Chữ trùng tên nhà thì
  //   hiện cả danh sách của nhà đó.
  function nhaDaXep(provs) {
    return provs.map((p, i) => [p, i])
      .sort((x, y) => (Number(!!y[0].configured) - Number(!!x[0].configured)) || (x[1] - y[1]))
      .map((x) => x[0]);
  }

  async function render(o) {
    o = o || {};
    o.cho = [];
    // 0.350.0 (owner, docs/dev/2026-10-model-routing-spec.md 2.6): the chat composer lists connected providers only.
    // Callers that still want the locked rows with their "add a key" way out (the assistant's model list) leave it off.
    const provs = nhaDaXep((o.providers || []).filter((p) => !o.connectedOnly || p.configured));
    const sel = o.selected || {};
    const short = o.short || ((x) => x);
    const mark = o.mark || (() => "");
    const limit = o.limit || 60;
    const q = (o.filter || "").trim().toLowerCase();

    const dauNha = (p, mo) => {
      const on = !!p.configured;
      // Nhà chưa cắm key: KHÔNG có data-prov (bấm vào không sổ ra được) + ổ khoá + một dòng
      // chỉ đúng chỗ đi mở khoá. Đây chính là phần ô <select> cũ làm mất.
      return `<div class="mb-prov ${on ? "" : "off"}" data-prov="${on ? esc(p.id) : ""}">`
        + `<span>${p.label}${mark(p)}</span>`
        + `<span>${on ? IC(mo ? "chevron-down" : "chevron-right")
                      : IC("lock", { cls: "ic-dim" })}</span></div>`
        + (on ? "" : `<div class="mb-link" data-goto="models">+ ${esc(T("mpick.add_key"))}</div>`);
    };
    const hangModel = (p, ids) => {
      let h = "";
      for (const id of ids.slice(0, limit)) {
        const cur = p.id === sel.provider && id === sel.model;
        h += `<div class="mb-item ${cur ? "cur" : ""}" data-prov="${esc(p.id)}" `
          + `data-model="${esc(id)}"><span class="tick">`
          + `${cur ? IC("check", { cls: "ic-ok" }) : ""}</span><span>${esc(short(id))}</span></div>`;
      }
      if (ids.length > limit) {
        h += `<div class="mb-empty">${esc(T("mpick.more").replace("{n}", String(ids.length - limit)))}</div>`;
      }
      return h;
    };
    const dangTai = `<div class="mb-empty pg-loading">${esc(T("mpick.loading"))}</div>`;
    // No list: say why (the server's sentence: wrong address, refused key, a seller that lists nothing) and give
    // the way out, the Models page, where the address is fixed or a model name is typed. Both callers already send
    // a click on [data-goto] to that page.
    const khongCoDanhSach = (p) => {
      const lyDo = why(p.id);
      return `<div class="mb-empty">${esc(T("mpick.no_list"))}${lyDo ? " " + esc(lyDo) : ""}</div>`
        + `<div class="mb-link" data-goto="models">${esc(T("mpick.fix_on_models"))}</div>`;
    };

    let html = `<input class="mb-search" id="${esc(o.searchId || "mlSearch")}" `
      + `placeholder="${esc(T("mpick.search_ph"))}" value="${esc(o.filter || "")}">`;
    html += o.extraTop || "";

    if (q) {
      let thay = 0;
      for (const p of provs) {
        const trungTen = (p.label || "").toLowerCase().includes(q) || (p.id || "").toLowerCase().includes(q);
        if (!p.configured) {
          if (trungTen) { html += dauNha(p, false); thay++; }
          continue;
        }
        // Search reads what is in hand, an empty answer included: asking a dead gateway again on every keystroke
        // would flash "loading" under the search box. Opening the provider is what asks again.
        const ds = CACHE[p.id] ? CACHE[p.id].models : null;
        if (!ds) {
          o.cho.push(models(p.id));
          html += dauNha(p, true) + dangTai;
          thay++;
          continue;
        }
        if (Date.now() - (CACHE[p.id].ts || 0) >= CACHE_MS) models(p.id);   // làm mới ngầm
        const ids = trungTen ? ds : ds.filter((id) => id.toLowerCase().includes(q));
        if (!ids.length) continue;
        html += dauNha(p, true) + hangModel(p, ids);
        thay++;
      }
      if (!thay) html += `<div class="mb-empty">${esc(T("mpick.no_match"))}</div>`;
      return html;
    }

    for (const p of provs) {
      const mo = !!o.expanded && p.id === o.expanded;
      html += dauNha(p, mo);
      if (!p.configured || !mo) continue;
      // noWait: chưa có danh sách thì vẽ dòng "đang tải" thay vì bắt cả bảng chờ mạng.
      if (o.noWait && !peek(p.id)) {
        o.cho.push(models(p.id));
        html += dangTai;
        continue;
      }
      const ids = await models(p.id);
      if (!ids.length) html += khongCoDanhSach(p);
      html += hangModel(p, ids);
    }
    return html;
  }

  const T2 = (k, vars) => {
    let s = window.t ? window.t(k, vars) : k;
    if (vars && typeof s === "string") {
      s = s.replace(/\{(\w+)\}/g, (m, n) => (Object.prototype.hasOwnProperty.call(vars, n) ? String(vars[n]) : m));
    }
    return s;
  };

  const ALIASES = {
    invalid_provider: "provider_unknown",
    provider_required: "provider_unknown",
    provider_not_ready: "auth_missing",
    engine_unavailable: "build_failed",
    engine_build_failed: "build_failed",
    auth: "auth_missing",
    quota: "quota_or_rate_limit",
    rate_limit: "quota_or_rate_limit",
  };
  const REASON_KEYS = {
    capability_unsupported: "teams.reply.why.capability_unsupported",
    auth_missing: "teams.reply.why.auth_missing",
    model_invalid: "teams.reply.why.model_invalid",
    provider_unknown: "teams.reply.why.provider_unknown",
    quota_or_rate_limit: "teams.reply.why.quota_or_rate_limit",
    network: "teams.reply.why.network",
    build_failed: "teams.reply.why.build_failed",
  };
  const CONFIG_CODES = {
    capability_unsupported: 1,
    auth_missing: 1,
    model_invalid: 1,
    provider_unknown: 1,
    build_failed: 1,
  };
  const MODE_ORDER = ["solo_chat", "team_text", "team_tool_full", "team_tool_gated"];
  const MODE_KEYS = {
    solo_chat: "cap.mode.solo_chat",
    team_text: "cap.mode.team_text",
    team_tool_full: "cap.mode.team_tool_full",
    team_tool_gated: "cap.mode.team_tool_gated",
  };
  const NO_TEAM_TEXT_PROVS = { "antigravity-cli": 1, "grok-cli": 1 };
  const CLI_PROVS = { "anthropic-cli": 1, "openai-oauth": 1, "grok-cli": 1, "antigravity-cli": 1 };

  function normalizeCode(code) {
    const c = String(code || "").trim();
    return ALIASES[c] || c;
  }
  function isConfigError(code, retryable) {
    if (retryable === false) return true;
    return Boolean(CONFIG_CODES[normalizeCode(code)]);
  }
  function reasonText(code) {
    const c = normalizeCode(code);
    if (!c) return T2("teams.reply.why.unknown");
    const k = REASON_KEYS[c];
    return k ? T2(k) : T2("teams.reply.why.unknown");
  }
  function statusLabel(st) {
    if (st === "blocked") return T2("cap.status_blocked");
    if (st === "warning") return T2("cap.status_warning");
    if (st === "unverified") return T2("cap.status_unverified");
    return T2("cap.status_ready");
  }
  function formatPair(prov, model, provLabel) {
    const pName = (provLabel && provLabel(prov)) || prov || "-";
    return model ? T2("cap.eff_pair", { prov: pName, model: model }) : pName;
  }
  function formatEffective(eff, provLabel) {
    if (!eff) return "";
    const pName = (provLabel && provLabel(eff.provider)) || eff.provider || "";
    const m = eff.model || "";
    if (eff.source === "main") {
      return m ? T2("cap.eff_main", { prov: pName || "-", model: m })
               : T2("cap.eff_main_def", { prov: pName || "-" });
    }
    if (eff.source === "legacy") {
      return pName ? T2("cap.eff_legacy", { model: m || "-", prov: pName })
                   : T2("cap.eff_legacy_none", { model: m || "-" });
    }
    return formatPair(eff.provider, m, provLabel);
  }

  function computeLocalEffective(mProv, mModel, mainCfg, provs, serverEff, origProv, origModel) {
    const p = String(mProv || "").trim();
    const m = String(mModel || "").trim();
    if (serverEff && p === String(origProv || "").trim() && m === String(origModel || "").trim()) {
      return serverEff;
    }
    const provMap = {};
    (provs || []).forEach((x) => { if (x && x.id) provMap[x.id] = x; });
    let effProv = p, effModel = m, source = "agent";
    if (!p && !m) {
      effProv = String((mainCfg && mainCfg.provider) || "anthropic-cli");
      effModel = String((mainCfg && mainCfg.model) || "");
      source = "main";
    } else if (!p && m) {
      effProv = "";
      effModel = m;
      source = "legacy";
    }
    const pObj = effProv ? provMap[effProv] : null;
    const known = Boolean(effProv && (pObj || CLI_PROVS[effProv]));
    const confOk = pObj ? Boolean(pObj.configured) : true;
    const apiEmpty = known && !CLI_PROVS[effProv] && !effModel;
    const modeRes = (mode) => {
      if (!known) return { ok: false, reason_code: "provider_unknown" };
      if (apiEmpty) return { ok: false, reason_code: "model_invalid" };
      const adOk = (mode === "solo_chat" || mode === "team_tool_full")
        ? true
        : !NO_TEAM_TEXT_PROVS[effProv];
      if (!adOk) return { ok: false, reason_code: "capability_unsupported" };
      if (!confOk) return { ok: false, reason_code: "auth_missing" };
      return { ok: true, reason_code: "" };
    };
    const modes = {};
    MODE_ORDER.forEach((md) => { modes[md] = modeRes(md); });
    const primary = modes.solo_chat;
    const teamText = modes.team_text;
    const code = !primary.ok ? primary.reason_code : (!teamText.ok ? teamText.reason_code : "");
    const status = !primary.ok ? "blocked" : (!teamText.ok ? "warning" : "ready");
    return {
      provider: effProv,
      model: effModel,
      source: source,
      status: status,
      reason_code: code,
      message: code ? reasonText(code) : "",
      fix_hint: "",
      modes: modes,
    };
  }

  function modesHtml(modes) {
    if (!modes) return "";
    return '<div class="cap-modes">' + MODE_ORDER.map((m) => {
      const r = modes[m];
      if (!r) return "";
      const ok = Boolean(r.ok);
      const why = !ok && r.reason_code ? " title=\"" + esc(reasonText(r.reason_code)) + "\"" : "";
      return `<span class="cap-mode ${ok ? "is-ok" : "is-no"}"${why}>`
        + `${esc(T2(MODE_KEYS[m] || m))}: ${esc(T2(ok ? "cap.mode_ok" : "cap.mode_no"))}</span>`;
    }).join("") + "</div>";
  }

  function teamSupportsText(provId) {
    return Boolean(provId && !NO_TEAM_TEXT_PROVS[provId]);
  }

  function openImpactDialog(html, onConfirm, forced) {
    return new Promise((resolve) => {
      if (typeof document === "undefined" || !document.body) { resolve(true); return; }
      const old = document.getElementById("javisCapModal");
      if (old) old.remove();
      const wrap = document.createElement("div");
      wrap.id = "javisCapModal";
      wrap.className = "mp-overlay open cap-modal-overlay";
      wrap.innerHTML = `<div class="mp-box cap-modal-box" role="dialog" aria-modal="true">${html}`
        + `<div class="mp-foot cap-modal-foot">`
        + (forced
          ? `<button type="button" class="mp-btn primary" data-cap-act="ok">${esc(T2("cap.main_impact_ack"))}</button>`
          : `<button type="button" class="mp-btn" data-cap-act="cancel">${esc(T2("common.cancel"))}</button>`
            + `<button type="button" class="mp-btn primary" data-cap-act="ok">${esc(onConfirm || T2("cap.main_impact_confirm"))}</button>`)
        + `</div></div>`;
      const done = (ans) => {
        document.removeEventListener("keydown", onKey, true);
        wrap.remove();
        resolve(ans);
      };
      const onKey = (e) => {
        if (e.key === "Escape") { e.preventDefault(); done(Boolean(forced)); }
      };
      document.addEventListener("keydown", onKey, true);
      wrap.addEventListener("click", (e) => {
        if (e.target === wrap) { done(Boolean(forced)); return; }
        const btn = e.target.closest && e.target.closest("[data-cap-act]");
        if (!btn) return;
        done(btn.dataset.capAct === "ok");
      });
      document.body.appendChild(wrap);
    });
  }

  function confirmMainImpact(impact, opts) {
    opts = opts || {};
    if (!impact) return Promise.resolve(true);
    const agents = impact.agents || [];
    const teams = impact.teams || [];
    const blocking = Number(impact.blocking || 0);
    if (!agents.length && !teams.length && !blocking) return Promise.resolve(true);
    const b = impact.before || {};
    const a = impact.after || {};
    const fromTxt = formatPair(b.provider, b.model);
    const toTxt = formatPair(a.provider, a.model);
    let body = `<div class="mp-head"><div><div class="mp-title">${esc(T2(opts.forced ? "cap.main_impact_forced_title" : "cap.main_impact_title"))}</div>`
      + `<div class="mp-sub">${esc(T2("cap.main_impact_pair", { from: fromTxt, to: toTxt }))}</div></div></div>`
      + `<div class="cap-modal-body">`;
    if (blocking > 0) {
      body += `<div class="cap-alert is-blocked">${esc(T2("cap.main_impact_blocking", { n: blocking }))}</div>`;
    }
    if (agents.length) {
      body += `<div class="cap-sec-title">${esc(T2("cap.main_impact_agents", { n: agents.length }))}</div><ul class="cap-list">`;
      agents.slice(0, 25).forEach((ag) => {
        const tr = T2("cap.status_transition", { before: statusLabel(ag.before_status), after: statusLabel(ag.after_status) });
        const why = ag.reason_code ? " - " + reasonText(ag.reason_code) : "";
        body += `<li><b>${esc(ag.name || ag.key)}</b> <span class="cap-dim">(${esc(tr)}${esc(why)})</span></li>`;
      });
      body += `</ul>`;
    }
    if (teams.length) {
      body += `<div class="cap-sec-title">${esc(T2("cap.main_impact_teams", { n: teams.length }))}</div><ul class="cap-list">`;
      teams.slice(0, 25).forEach((tm) => {
        const tr = T2("cap.status_transition", { before: statusLabel(tm.before), after: statusLabel(tm.after) });
        const iss = (tm.issues || [])[0];
        const why = iss ? " - " + (iss.message || reasonText(iss.reason_code)) : "";
        body += `<li><b>${esc(tm.name || tm.team_id)}</b> <span class="cap-dim">(${esc(tr)}${esc(why)})</span></li>`;
      });
      body += `</ul>`;
    }
    body += `</div>`;
    return openImpactDialog(body, T2("cap.main_impact_confirm"), Boolean(opts.forced));
  }

  async function previewAndConfirmMain(newMain, impactUrl) {
    if (!newMain || !newMain.provider) return { confirmed: true, impact: null };
    let impact = null;
    try {
      const fd = new FormData();
      fd.append("provider", newMain.provider);
      fd.append("model", newMain.model || "");
      const r = await fetch(impactUrl || "/models/main/impact", { method: "POST", body: fd, credentials: "same-origin" });
      if (r && r.ok) impact = await r.json();
    } catch (e) { impact = null; }
    if (!impact || (!((impact.agents || []).length) && !((impact.teams || []).length) && !impact.blocking)) {
      return { confirmed: true, impact: impact };
    }
    const ok = await confirmMainImpact(impact, { forced: false });
    return { confirmed: ok, impact: impact };
  }

  function confirmAgentImpact(agentName, impact, usedByTeams) {
    const imp = impact || {};
    const byId = {};
    const teams = [];
    (imp.teams || []).forEach((t) => {
      const k = t.team_id || t.name;
      byId[k] = t;
      teams.push(t);
    });
    (usedByTeams || []).forEach((t) => {
      const k = t.team_id || t.name;
      if (!byId[k]) teams.push(t);
    });
    const workflows = imp.workflows || [];
    const chatbots = imp.chatbots || [];
    const sessions = Number(imp.sessions || imp.solo_sessions || 0);
    const blocking = Number(imp.blocking || 0);
    if (!teams.length && !workflows.length && !chatbots.length && !sessions && !blocking) {
      return Promise.resolve(true);
    }
    let body = `<div class="mp-head"><div><div class="mp-title">${esc(T2("cap.agent_impact_title", { name: agentName }))}</div>`
      + `<div class="mp-sub">${esc(T2("cap.agent_impact_sub", { name: agentName }))}</div></div></div>`
      + `<div class="cap-modal-body">`;
    if (blocking > 0) {
      body += `<div class="cap-alert is-blocked">${esc(T2("cap.main_impact_blocking", { n: blocking }))}</div>`;
    }
    if (teams.length) {
      body += `<div class="cap-sec-title">${esc(T2("cap.agent_impact_teams", { n: teams.length }))}</div><ul class="cap-list">`;
      teams.forEach((tm) => {
        const tr = tm.before && tm.after
          ? " (" + T2("cap.status_transition", { before: statusLabel(tm.before), after: statusLabel(tm.after) }) + ")"
          : (tm.role ? " (" + tm.role + ")" : "");
        const iss = (tm.issues || [])[0];
        const why = iss ? " - " + (iss.message || reasonText(iss.reason_code)) : "";
        body += `<li><b>${esc(tm.name || tm.team_id)}</b><span class="cap-dim">${esc(tr + why)}</span></li>`;
      });
      body += `</ul>`;
    }
    if (workflows.length) {
      body += `<div class="cap-sec-title">${esc(T2("cap.agent_impact_workflows", { n: workflows.length }))}</div><ul class="cap-list">`;
      workflows.forEach((w) => { body += `<li><b>${esc(w.name || w.slug)}</b></li>`; });
      body += `</ul>`;
    }
    if (chatbots.length) {
      body += `<div class="cap-sec-title">${esc(T2("cap.agent_impact_chatbots", { n: chatbots.length }))}</div><ul class="cap-list">`;
      chatbots.forEach((cb) => { body += `<li><b>${esc(cb.name || cb.id)}</b></li>`; });
      body += `</ul>`;
    }
    if (sessions > 0) {
      body += `<div class="cap-sec-title">${esc(T2("cap.agent_impact_sessions", { n: sessions }))}</div>`;
    }
    body += `</div>`;
    return openImpactDialog(body, T2("cap.agent_impact_confirm"), false);
  }

  const CapUI = {
    ALIASES, REASON_KEYS, CONFIG_CODES, MODE_ORDER,
    normalizeCode, isConfigError, reasonText, statusLabel,
    formatPair, formatEffective, computeLocalEffective, modesHtml, teamSupportsText,
    confirmMainImpact, previewAndConfirmMain, confirmAgentImpact,
  };

  window.JavisModelList = { models, peek, why, render, clearCache };
  window.JavisCapUI = CapUI;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { ModelList: window.JavisModelList, CapUI: CapUI };
  }
})();
