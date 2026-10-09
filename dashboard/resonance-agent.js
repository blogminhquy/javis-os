/* Cộng hưởng theo từng trợ lý (Resonance A1).

   Hai chỗ dùng:
   - Trang Cộng sự, cột phải của một trợ lý (workspace.js gọi `mount`): công tắc Cộng hưởng, trạng thái của phiên
     đang mở, khả năng theo engine, và khung "Mục tiêu của trợ lý" (mỗi mục tiêu là một thẻ của chat-resonance.js
     nên các nút Đúng ý, Tạm dừng, Huỷ... dùng chung một đường).
   - Trang Cài đặt (#resonanceBlock): danh sách trợ lý kèm công tắc, mục "Chờ gán" cho mục tiêu có trước A1.

   Công tắc CHỈ đổi qua API của chủ dự án (/resonance/agents/toggle); không tool nào của bộ não chạm tới được.
   Bật trong một phiên mở trước lúc trợ lý được cấp mã (thường gặp: trợ lý tạo lại cùng tên) thì server trả
   `needs_new_session` (review A1 vòng 2, P2): nói rõ và đưa nút mở cuộc trò chuyện mới, không tự chuyển phiên cũ.

   Hàm `panelHtml`, `settingsHtml`, `toggleNote` thuần (không DOM, không mạng) để test chạy dưới node. */
(function () {
  "use strict";

  function tw(khoa, bien) {
    if (typeof window !== "undefined" && window.t) return window.t(khoa, bien);
    try {
      var s = require("./i18n/vi.json")[khoa] || khoa;
      return String(s).replace(/\{(\w+)\}/g, function (m, ten) {
        return (bien && bien[ten] != null) ? String(bien[ten]) : m;
      });
    } catch (e) { return khoa; }
  }

  function esc(t) {
    return String(t == null ? "" : t)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function brain() {
    try {
      if (typeof window !== "undefined" && window.JavisSessions && window.JavisSessions.brain) return window.JavisSessions.brain();
      return (window.currentBrainPath && window.currentBrainPath()) || "brain";
    } catch (e) { return "brain"; }
  }

  /* Dòng giải thích ngay dưới công tắc: theo trạng thái trợ lý và phiên đang mở. */
  function toggleNote(agent, session) {
    if (!agent || agent.status === "missing") return tw("resonance.a1_missing");
    if (agent.status === "retired") return tw("resonance.a1_retired");
    if (!agent.enabled) return tw("resonance.a1_off_note");
    if (session === "needs_new_session") return tw("resonance.a1_needs_new_session");
    return tw("resonance.a1_on_note");
  }

  /* Cảnh báo theo engine của trợ lý (thiết kế A1 mục 2): lập mục tiêu, nhận bản chat, việc nền. */
  function supportHtml(support) {
    var s = support || {};
    if (s.goal === false) return '<div class="rsa-warn">' + esc(tw("resonance.a1_engine_no_goal")) + "</div>";
    if (s.chat_output === false) return '<div class="rsa-sub">' + esc(tw("resonance.a1_engine_no_chat_output")) + "</div>";
    return "";
  }

  /* Khối Cộng hưởng của MỘT trợ lý. `row`: một mục của GET /resonance/agents (hay null khi chưa tải được),
     `session`: ready | needs_new_session | not_this_agent | null, `goals`: GET /resonance/goals?agent_key=. */
  function panelHtml(row, session, goals) {
    var r = row || { status: "unregistered", enabled: false };
    var on = !!r.enabled && r.status === "active";
    var html = '<div class="rsa-head"><span class="rsa-title">' + esc(tw("resonance.a1_title")) + "</span>" +
      '<label class="toggle"><input type="checkbox" class="rsa-toggle"' + (on ? " checked" : "") +
      (r.status === "missing" ? " disabled" : "") + "><span></span></label></div>";
    html += '<div class="rsa-sub rsa-note">' + esc(toggleNote(r.status === "unregistered" ? { status: "active",
      enabled: false } : r, session)) + "</div>";
    if (on && session === "needs_new_session") {
      html += '<button type="button" class="ws-btn rsa-new-session">' + esc(tw("resonance.a1_open_new")) + "</button>";
    }
    if (r.status === "missing") {
      html += '<div class="rsa-acts"><button type="button" class="ws-btn rsa-confirm" data-same="1">' +
        esc(tw("resonance.a1_confirm_same")) + '</button><button type="button" class="ws-btn rsa-confirm" data-same="0">' +
        esc(tw("resonance.a1_confirm_new")) + "</button></div>";
    }
    html += supportHtml(r.support);
    var list = (goals || []).filter(function (g) { return g && g.goal_id; });
    html += '<div class="rsa-goals-title">' + esc(tw("resonance.a1_goals_title")) + "</div>";
    if (!list.length) html += '<div class="rsa-sub">' + esc(tw("resonance.a1_no_goals")) + "</div>";
    list.forEach(function (g) {
      html += '<div class="rs-card rsa-card" data-goal="' + esc(g.goal_id) + '"></div>';
    });
    return html;
  }

  /* Khối trên trang Cài đặt: mỗi trợ lý một công tắc; mã đã mất file; mục tiêu chờ gán kèm ô chọn trợ lý. */
  function settingsHtml(data, unassigned) {
    var d = data || {};
    var agents = d.agents || [];
    var html = '<div class="opt-sub">' + esc(tw("resonance.a1_settings_desc")) + "</div>";
    if (!agents.length) html += '<div class="opt-sub">' + esc(tw("resonance.a1_settings_empty")) + "</div>";
    agents.forEach(function (a) {
      var on = !!a.enabled && a.status === "active";
      html += '<label class="loop-row rsa-row" style="padding:6px 0"><span>' + esc(a.name || a.slug) +
        (a.goals_open ? ' <small class="rsa-sub">' + esc(tw("resonance.a1_goals_open", { n: a.goals_open })) + "</small>" : "") +
        (a.support && a.support.goal === false ? ' <small class="rsa-warn">' + esc(tw("resonance.a1_engine_short")) + "</small>" : "") +
        (a.status === "missing" ? ' <small class="rsa-warn">' + esc(tw("resonance.a1_missing_short")) + "</small>" : "") +
        '</span><label class="toggle"><input type="checkbox" class="rsa-set-toggle" data-slug="' + esc(a.slug) + '"' +
        (on ? " checked" : "") + (a.status === "missing" ? " disabled" : "") + "><span></span></label></label>";
    });
    (d.orphans || []).forEach(function (o) {
      html += '<div class="opt-sub rsa-warn">' + esc(tw("resonance.a1_orphan", { slug: o.slug, n: o.goals_open || 0 })) + "</div>";
    });
    var wait = (unassigned || []).filter(function (g) { return g && g.goal_id; });
    if (wait.length) {
      var live = agents.filter(function (a) { return a.status === "active" && a.agent_key; });
      html += '<div class="popover-label rsa-wait-title">' + esc(tw("resonance.a1_unassigned_title")) + "</div>" +
        '<div class="opt-sub">' + esc(tw("resonance.a1_unassigned_desc")) + "</div>";
      wait.forEach(function (g) {
        html += '<div class="rsa-wait" data-goal="' + esc(g.goal_id) + '" data-rev="' + esc(g.revision) + '">' +
          '<div class="rsa-wait-text">' + esc(g.understanding || g.goal_id) + "</div>" +
          '<select class="rsa-assign-pick"><option value="">' + esc(tw("resonance.a1_pick_agent")) + "</option>" +
          live.map(function (a) { return '<option value="' + esc(a.agent_key) + '">' + esc(a.name || a.slug) + "</option>"; }).join("") +
          '</select><button type="button" class="ws-btn rsa-assign">' + esc(tw("resonance.a1_assign")) + "</button></div>";
      });
    }
    if (d.legacy_brain_switch) html += '<div class="opt-sub rsa-sub">' + esc(tw("resonance.a1_legacy_note")) + "</div>";
    return html;
  }

  // ───────────── phần chạy trong trình duyệt ─────────────

  function getJson(url) {
    return fetch(url, { credentials: "same-origin" }).then(function (r) {
      return r.json().then(function (j) { return { code: r.status, j: j }; });
    });
  }

  function postJson(url, body) {
    return fetch(url, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}) }).then(function (r) {
      return r.json().then(function (j) { return { code: r.status, j: j }; });
    });
  }

  function q(s) { return encodeURIComponent(s); }

  var S = { host: null, slug: "", sessionId: "", onNewSession: null, ticket: 0 };

  /* Phiên đang mở của trang (đổi khi người dùng mở cuộc khác), rơi về phiên lúc gắn khối. */
  function currentSession() {
    try {
      var cur = window.JavisSessions && window.JavisSessions.current && window.JavisSessions.current();
      if (cur) return String(cur);
    } catch (e) {}
    return S.sessionId;
  }

  /* Vẽ khối của trợ lý `opts.slug` vào `host`. Gọi lại (đổi trợ lý, mở phiên khác) thì vẽ lại từ đầu; lần tải cũ
     chưa về thì bị bỏ qua nhờ `ticket`. */
  function mount(host, opts) {
    if (!host) return Promise.resolve();
    var o = opts || {};
    S.host = host; S.slug = String(o.slug || ""); S.onNewSession = o.onNewSession || null;
    S.sessionId = String(o.sessionId || "");
    return refresh();
  }

  /* Vẽ lại theo trạng thái HOST trả về, kể cả trạng thái của phiên đang mở (review A1 tích hợp, P2): tải lại trang,
     đổi phiên hay bật ở trang Cài đặt rồi quay lại đều hỏi lại host, không giữ kết quả của lần bật trong bộ nhớ. */
  function refresh() {
    var host = S.host;
    if (!host || !S.slug) return Promise.resolve();
    var t = ++S.ticket;
    var sid = currentSession();
    S.lastSid = sid;
    return getJson("/resonance/agents?brain=" + q(brain()) + "&slug=" + q(S.slug) +
                   (sid ? "&session_id=" + q(sid) : "")).then(function (res) {
      if (t !== S.ticket) return;
      var session = (res.j && res.j.session) || null;
      var row = ((res.j && res.j.agents) || []).filter(function (a) { return a.slug === S.slug; })[0] || null;
      var key = row && row.agent_key;
      var goalsP = key ? getJson("/resonance/goals?brain=" + q(brain()) + "&agent_key=" + q(key))
        : Promise.resolve({ j: { goals: [] } });
      return goalsP.then(function (gr) {
        if (t !== S.ticket) return;
        var goals = (gr.j && gr.j.goals) || [];
        host.innerHTML = panelHtml(row, session, goals);
        wire(host, row);
        if (window.JavisResonance) {
          goals.forEach(function (g) {
            var el = host.querySelector('.rsa-card[data-goal="' + g.goal_id + '"]');
            if (el) { el._goal = g; el.innerHTML = window.JavisResonance.viewHtml(g); }
          });
        }
      });
    }).catch(function () {
      if (t === S.ticket) host.innerHTML = '<div class="rsa-sub">' + esc(tw("resonance.unavailable")) + "</div>";
    });
  }

  function wire(host, row) {
    var box = host.querySelector(".rsa-toggle");
    if (box) box.addEventListener("change", function () {
      box.disabled = true;
      postJson("/resonance/agents/toggle?brain=" + q(brain()), { slug: S.slug, enabled: box.checked,
        session_id: currentSession() })
        .then(function (res) {
          if (res.code !== 200) {
            host.insertAdjacentHTML("beforeend", '<div class="rsa-warn">' + esc((res.j && res.j.error) || tw("resonance.failed")) + "</div>");
            box.checked = !box.checked; box.disabled = false;
            return;
          }
          refresh();
        })
        .catch(function () { box.checked = !box.checked; box.disabled = false; });
    });
    var nb = host.querySelector(".rsa-new-session");
    if (nb) nb.addEventListener("click", function () {
      // Mở phiên mới đi đúng đường của trang; trang gắn lại khối với phiên mới và host nói nó có dùng được không.
      if (S.onNewSession) Promise.resolve(S.onNewSession()).then(function () { refresh(); });
    });
    host.querySelectorAll(".rsa-confirm").forEach(function (b) {
      b.addEventListener("click", function () {
        if (!row || !row.agent_key) return;
        var same = b.getAttribute("data-same") === "1";
        if (!same && !window.confirm(tw("resonance.a1_confirm_new_q"))) return;
        postJson("/resonance/agents/confirm?brain=" + q(brain()), { agent_key: row.agent_key, same: same })
          .then(function () { refresh(); });
      });
    });
  }

  /* Trang Cài đặt: nạp lại mỗi lần khối được mở hay rê chuột tới, vì brain đang chọn có thể đã đổi. */
  function settingsInit() {
    var block = document.getElementById("resonanceBlock");
    var host = document.getElementById("resonanceAgents");
    if (!block || !host) return;
    var busy = false;
    function sync() {
      if (busy) return;
      busy = true;
      var b = q(brain());
      getJson("/resonance/agents?brain=" + b).then(function (res) {
        var data = res.j || {};
        var p = data.unassigned ? getJson("/resonance/goals?brain=" + b + "&unassigned=1") : Promise.resolve({ j: { goals: [] } });
        return p.then(function (gr) { host.innerHTML = settingsHtml(data, (gr.j && gr.j.goals) || []); });
      }).catch(function () {}).then(function () { busy = false; });
    }
    host.addEventListener("change", function (ev) {
      var box = ev.target && ev.target.closest && ev.target.closest(".rsa-set-toggle");
      if (!box) return;
      box.disabled = true;
      postJson("/resonance/agents/toggle?brain=" + q(brain()), { slug: box.getAttribute("data-slug"), enabled: box.checked })
        .then(function () { sync(); }).catch(sync);
    });
    host.addEventListener("click", function (ev) {
      var btn = ev.target && ev.target.closest && ev.target.closest(".rsa-assign");
      if (!btn) return;
      var row = btn.closest(".rsa-wait");
      var pick = row && row.querySelector(".rsa-assign-pick");
      if (!pick || !pick.value) return;
      btn.disabled = true;
      postJson("/goals/" + q(row.getAttribute("data-goal")) + "/assign?brain=" + q(brain()),
        { agent_key: pick.value, expected_revision: Number(row.getAttribute("data-rev")) || 0 })
        .then(function (res) {
          if (res.code !== 200) row.insertAdjacentHTML("beforeend", '<div class="rsa-warn">' + esc((res.j && res.j.error) || tw("resonance.failed")) + "</div>");
          sync();
        }).catch(sync);
    });
    block.addEventListener("mouseenter", sync);
    block.addEventListener("focusin", function (ev) { if (!host.contains(ev.target)) sync(); });
    sync();
  }

  if (typeof document !== "undefined" && document.addEventListener) {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", settingsInit);
    else settingsInit();
  }
  // Người dùng mở một cuộc khác của cùng trợ lý (tab Lịch sử): hỏi lại host phiên MỚI có dùng được Cộng hưởng không.
  if (typeof window !== "undefined" && window.addEventListener) {
    window.addEventListener("javis:sessions-changed", function () {
      if (S.host && S.host.isConnected && currentSession() !== S.lastSid) refresh();
    });
  }

  var api = { mount: mount, refresh: refresh, panelHtml: panelHtml, settingsHtml: settingsHtml, toggleNote: toggleNote };
  if (typeof window !== "undefined") window.JavisResonanceAgent = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
