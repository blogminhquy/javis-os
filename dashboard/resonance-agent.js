/* Cộng hưởng theo từng trợ lý (Resonance A1).

   Hai chỗ dùng:
   - Trang Cộng sự, cột phải của một trợ lý (workspace.js gọi `mount`): công tắc Cộng hưởng, trạng thái của phiên
     đang mở, khả năng theo engine, và khung "Mục tiêu của trợ lý" (mỗi mục tiêu là một thẻ của chat-resonance.js
     nên các nút Đúng ý, Tạm dừng, Huỷ... dùng chung một đường).
   - Trang Cài đặt (#resonanceBlock): tóm tắt số trợ lý đang bật, đường sang trang Cộng sự, mục "Chờ gán" cho mục
     tiêu có trước A1.
   - T0 nhóm chat team: công tắc từng trợ lý nằm trên DÒNG của trợ lý ở cột trái trang Cộng sự (`rowToggleHtml`,
     `toggleAgent`), một nơi duy nhất; bảng bên phải và trang Cài đặt chỉ hiện trạng thái.

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
  // Nút "i" (info-tip.js, 0.175.0): có thì lời giải thích ẩn sau nút cạnh tiêu đề; không có (test Node) thì vẽ thẳng ra.
  function infoBtn() { var J = typeof window !== "undefined" && window.JavisInfo; return J ? J.btn(tw("info.more")) : ""; }
  function infoBody(html) {
    var J = typeof window !== "undefined" && window.JavisInfo;
    return J ? J.body(html) : '<div class="info-body">' + html + "</div>";
  }


  function brain() {
    try {
      if (typeof window !== "undefined" && window.JavisSessions && window.JavisSessions.brain) return window.JavisSessions.brain();
      return (window.currentBrainPath && window.currentBrainPath()) || "brain";
    } catch (e) { return "brain"; }
  }

  /* Dòng giải thích theo trạng thái trợ lý và phiên đang mở. Trả về KHOÁ (như stateKey); chữ chỉ được vẽ trong khối
     (i) của panelHtml. */
  function toggleNoteKey(agent, session) {
    if (!agent || agent.status === "missing") return "resonance.a1_missing";
    if (agent.status === "retired") return "resonance.a1_retired";
    if (!agent.enabled) return "resonance.a1_off_note";
    if (session === "needs_new_session") return "resonance.a1_needs_new_session";
    return "resonance.a1_on_note";
  }

  function sub(text, cls) { return '<div class="rsa-sub' + (cls ? " " + cls : "") + '">' + esc(text) + "</div>"; }

  /* Cảnh báo theo engine của trợ lý (thiết kế A1 mục 2): lập mục tiêu, việc nền. Ghi chú "chưa nhận bản chat" nằm
     trong khối (i) của panelHtml. */
  function supportHtml(support) {
    var s = support || {};
    if (s.goal === false) return '<div class="rsa-warn">' + esc(tw("resonance.a1_engine_no_goal")) + "</div>";
    // A4 (mục 6.1): engine nộp được qua công cụ hub thì nói rõ Javis đăng, và chỉ khi bạn đã cho phép file đích.
    if (s.submit_tool) return '<div class="rsa-sub">' + esc(tw("resonance.a4_engine_submit")) + "</div>";
    return "";
  }

  /* T0 nhóm chat team (spec 2026-10-13-team-chat-design mục 10): trạng thái Cộng hưởng của MỘT trợ lý bằng chữ, cho
     dòng ở cột trái trang Cộng sự. Không chỉ dựa vào màu. */
  function stateKey(row) {
    var r = row || {};
    if (r.status === "missing") return "resonance.t0_state_missing";
    if (r.status === "retired") return "resonance.t0_state_retired";
    return r.enabled && r.status === "active" ? "resonance.t0_state_on" : "resonance.t0_state_off";
  }

  /* Công tắc trên dòng trợ lý: nơi DUY NHẤT bật, tắt từng trợ lý. Không có dữ liệu thì không vẽ gì (không đoán trạng
     thái). `missing` và `retired` không có ô bật mà có nút mở bảng bên phải, nơi có hai nút xác nhận của A1. */
  function rowToggleHtml(row, opts) {
    if (!row || !row.slug) return "";
    var o = opts || {};
    var label = o.saving ? tw("resonance.t0_saving") : tw(stateKey(row));
    if (row.status === "missing" || row.status === "retired") {
      return '<button type="button" class="ws-rs ws-rs-confirm" data-rs-open="' + esc(row.slug) + '">' +
        '<span class="ws-rs-text">' + esc(label) + "</span></button>";
    }
    var on = !!row.enabled && row.status === "active";
    // Trạng thái bằng chữ ("Auto: Bật") nằm đầu nhãn cho trình đọc màn hình và tooltip; mắt thấy nhãn ngắn "Auto" và
    // màu của công tắc.
    var aria = tw(stateKey(row)) + " · " + tw("resonance.t0_toggle_aria", { name: row.name || row.slug });
    // 0.142.0: nhãn ngắn "Auto" và công tắc nhỏ nằm TRONG thẻ trợ lý (góc dưới phải). Bật màu cam Javis, tắt xám; trạng
    // thái đọc được bằng chữ qua aria và tooltip, không chỉ bằng màu. Đang lưu thì khoá và nói "Đang lưu".
    return '<label class="ws-rs ws-auto' + (on ? " is-on" : "") + (o.saving ? " is-saving" : "") + '" title="' + esc(aria) + '">' +
      '<span class="ws-rs-text">' + esc(o.saving ? label : tw("resonance.auto_label")) + "</span>" +
      '<span class="toggle toggle-sm"><input type="checkbox" class="ws-rs-toggle" data-rs="' + esc(row.slug) + '"' +
      ' role="switch" aria-checked="' + (on ? "true" : "false") + '" aria-label="' + esc(aria) + '"' + (on ? " checked" : "") +
      (o.saving ? " disabled" : "") + "><span></span></span></label>";
  }

  /* Hỏi lại trước khi TẮT khi trợ lý còn mục tiêu mở (hợp đồng A1: dừng ở bước kế tiếp). Không có thì không hỏi. */
  function offConfirmText(row) {
    var n = Number((row || {}).goals_open || 0);
    if (!row || !row.enabled || n <= 0) return "";
    return tw("resonance.t0_off_confirm", { name: row.name || row.slug, n: n });
  }

  /* Khối Cộng hưởng của MỘT trợ lý. `row`: một mục của GET /resonance/agents (hay null khi chưa tải được),
     `session`: ready | needs_new_session | not_this_agent | null, `goals`: GET /resonance/goals?agent_key=. */
  /* 0.142.0: bỏ ô Người review (cặp làm/review cố định của A5). Mục tiêu mới không gắn người review; cần kiểm chứng thì
     giao một việc riêng cho trợ lý phù hợp ở tab Công việc (dòng rsa-verify trong khối (i)). Tiêu chí hoàn thành, góp ý
     và lịch sử review cũ vẫn giữ. */
  function panelHtml(row, session, goals, all) {
    var r = row || { status: "unregistered", enabled: false };
    var on = !!r.enabled && r.status === "active";
    // T0: công tắc nằm trên dòng trợ lý ở cột trái (một nơi duy nhất). Ở đây chỉ còn trạng thái bằng chữ.
    // 0.175.0 (chủ repo 16/10/2026: "bên cài đặt quá rồi... có một nút nhỏ kiểu nút i"): đầu mục chỉ còn tên và trạng thái.
    // Mọi câu giải thích (Auto làm gì, bật ở đâu, Auto không phải Toàn quyền, ghi chú công tắc, kiểm chứng) nằm sau nút i.
    // Thứ cần chủ làm (mở phiên mới, xác nhận trợ lý, cảnh báo engine) vẫn đứng ngoài, không bị giấu.
    var html = '<div class="rsa-head"><span class="rsa-title">' + esc(tw("resonance.a1_title")) + infoBtn() + "</span>" +
      '<span class="rsa-state">' + esc(tw(stateKey(r))) + "</span></div>";
    var sup = supportHtml(r.support);
    var supWarn = sup.indexOf("rsa-warn") >= 0;
    var noChat = !supWarn && (r.support || {}).chat_output === false;
    var nk = toggleNoteKey(r.status === "unregistered" ? { status: "active", enabled: false } : r, session);
    html += infoBody(sub(tw("resonance.auto_desc"), "rsa-desc") + sub(tw("resonance.t0_where")) +
      sub(tw("resonance.auto_not_full"), "rsa-note") + sub(tw(nk), "rsa-note") +
      (noChat ? sub(tw("resonance.a1_engine_no_chat_output")) : supWarn ? "" : sup) +
      (on ? sub(tw("resonance.verify_note"), "rsa-note rsa-verify") : ""));
    if (on && session === "needs_new_session") {
      html += '<button type="button" class="ws-btn rsa-new-session">' + esc(tw("resonance.a1_open_new")) + "</button>";
    }
    if (r.status === "missing") {
      html += '<div class="rsa-acts"><button type="button" class="ws-btn rsa-confirm" data-same="1">' +
        esc(tw("resonance.a1_confirm_same")) + '</button><button type="button" class="ws-btn rsa-confirm" data-same="0">' +
        esc(tw("resonance.a1_confirm_new")) + "</button></div>";
    }
    if (supWarn) html += sup;
    var list = (goals || []).filter(function (g) { return g && g.goal_id; });
    // 0.190.0 (chủ repo 16/10/2026: "tối giản nhất"): no goals means nothing to show, not a "no goals yet" line.
    if (list.length) html += '<div class="rsa-goals-title">' + esc(tw("resonance.a1_goals_title")) + "</div>";
    list.forEach(function (g) {
      html += '<div class="rs-card rsa-card" data-goal="' + esc(g.goal_id) + '"></div>';
    });
    return html;
  }

  /* 0.190.0 (owner, 16/10/2026): the A3 "Lessons" list (proposals, active lessons with Revoke, history) is no longer on
     the assistant's column. People never used it; lessons are handled in chat with the javis_memory tool. Method
     lessons still surface as cards in the chat itself (chat-resonance.js). */

  /* Khối trên trang Cài đặt (T0): chỉ còn tóm tắt và đường sang trang Cộng sự, nơi bật, tắt từng trợ lý. Trợ lý mất
     file vẫn được liệt kê bằng chữ để thấy; mã mồ côi; mục tiêu chờ gán kèm ô chọn trợ lý. */
  function settingsHtml(data, unassigned) {
    var d = data || {};
    var agents = d.agents || [];
    // 0.214.0: what Auto does sits behind the (i) at the end of the first line (summary, or the empty note).
    var html = "";
    var nOn = agents.filter(function (a) { return a && a.enabled && a.status === "active"; }).length;
    html += agents.length
      ? '<div class="opt-sub rsa-summary">' + esc(tw("resonance.t0_settings_summary", { n: nOn })) + infoBtn() + "</div>"
      : '<div class="opt-sub">' + esc(tw("resonance.a1_settings_empty")) + infoBtn() + "</div>";
    html += infoBody('<div class="opt-sub">' + esc(tw("resonance.a1_settings_desc")) + "</div>");
    if (agents.length) {
      html += '<button type="button" class="ws-btn rsa-goto-ws">' + esc(tw("resonance.t0_settings_manage")) + "</button>";
    }
    agents.forEach(function (a) {
      if (!a || a.status !== "missing") return;
      html += '<div class="opt-sub rsa-warn">' + esc(a.name || a.slug) + " " + esc(tw("resonance.a1_missing_short")) +
        (a.goals_open ? " · " + esc(tw("resonance.a1_goals_open", { n: a.goals_open })) : "") + "</div>";
    });
    (d.orphans || []).forEach(function (o) {
      html += '<div class="opt-sub rsa-warn">' + esc(tw("resonance.a1_orphan", { slug: o.slug, n: o.goals_open || 0 })) + "</div>";
    });
    var wait = (unassigned || []).filter(function (g) { return g && g.goal_id; });
    if (wait.length) {
      var live = agents.filter(function (a) { return a.status === "active" && a.agent_key; });
      html += '<div class="popover-label rsa-wait-title">' + esc(tw("resonance.a1_unassigned_title")) + infoBtn() + "</div>" +
        infoBody('<div class="opt-sub">' + esc(tw("resonance.a1_unassigned_desc")) + "</div>");
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
        host.innerHTML = panelHtml(row, session, goals, (res.j && res.j.agents) || []);
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

  /* T0: bật hay tắt MỘT trợ lý từ dòng ở cột trái (hay danh sách thành viên nhóm). Không gửi session_id: trạng thái
     của phiên đang mở do bảng bên phải hỏi lại host. Chỉ trả ok khi server xác nhận; luôn phát sự kiện để mọi chỗ tải
     lại TRẠNG THÁI THẬT, kể cả khi lỗi (409 agent cần xác nhận, rớt mạng). */
  function toggleAgent(slug, enabled) {
    function done(out) {
      try { window.dispatchEvent(new CustomEvent("javis:resonance-agents-changed")); } catch (e) {}
      return out;
    }
    return postJson("/resonance/agents/toggle?brain=" + q(brain()), { slug: slug, enabled: !!enabled })
      .then(function (res) {
        if (res.code === 200 && res.j && res.j.ok) return done({ ok: true, error: "" });
        return done({ ok: false, error: String((res.j && res.j.error) || tw("resonance.failed")) });
      }, function () { return done({ ok: false, error: tw("resonance.failed") }); });
  }

  function wire(host, row) {
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
        // T0: phát sự kiện trong tab (dòng trợ lý ở cột trái đổi ngay, không chờ gói WS) rồi vẽ lại bảng này.
        postJson("/resonance/agents/confirm?brain=" + q(brain()), { agent_key: row.agent_key, same: same })
          .then(function () {
            try { window.dispatchEvent(new CustomEvent("javis:resonance-agents-changed")); } catch (e) {}
            refresh();
          }, function () { refresh(); });
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
    host.addEventListener("click", function (ev) {
      // T0: bật, tắt từng trợ lý ở trang Cộng sự; trang Cài đặt chỉ đưa đường sang đó.
      var go = ev.target && ev.target.closest && ev.target.closest(".rsa-goto-ws");
      // Mở đúng tab Trợ lý (JavisNav.go thì rơi vào tab đang nhớ dở, có thể là Quy trình).
      if (go) {
        try {
          if (window.JavisWorkspace && window.JavisWorkspace.openTab) window.JavisWorkspace.openTab("agent");
          else window.JavisNav.go("workspace");
        } catch (e) {}
        return;
      }
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
    // Trợ lý vừa được bật, tắt ở tab này hay tab khác (gói WS resonance_agents): tóm tắt đổi theo.
    window.addEventListener("javis:resonance-agents-changed", sync);
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
    // T0: công tắc trên dòng trợ lý (hay tab khác) vừa đổi trạng thái: bảng bên phải hỏi lại host.
    window.addEventListener("javis:resonance-agents-changed", function () {
      if (S.host && S.host.isConnected) refresh();
    });
  }

  var api = { mount: mount, refresh: refresh, panelHtml: panelHtml,
    rowToggleHtml: rowToggleHtml, stateKey: stateKey, offConfirmText: offConfirmText, toggleAgent: toggleAgent,
    settingsHtml: settingsHtml, toggleNoteKey: toggleNoteKey, supportHtml: supportHtml };
  if (typeof window !== "undefined") window.JavisResonanceAgent = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
