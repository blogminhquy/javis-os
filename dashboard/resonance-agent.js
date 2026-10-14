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
     giao một việc riêng cho trợ lý phù hợp ở tab Công việc. Tiêu chí hoàn thành, góp ý và lịch sử review cũ vẫn giữ. */
  function verifyNoteHtml() {
    return '<div class="rsa-sub rsa-note rsa-verify">' + esc(tw("resonance.verify_note")) + "</div>";
  }

  function panelHtml(row, session, goals, all) {
    var r = row || { status: "unregistered", enabled: false };
    var on = !!r.enabled && r.status === "active";
    // T0: công tắc nằm trên dòng trợ lý ở cột trái (một nơi duy nhất). Ở đây chỉ còn trạng thái bằng chữ.
    var html = '<div class="rsa-head"><span class="rsa-title">' + esc(tw("resonance.a1_title")) + "</span>" +
      '<span class="rsa-state">' + esc(tw(stateKey(r))) + "</span></div>" +
      '<div class="rsa-sub rsa-desc">' + esc(tw("resonance.auto_desc")) + "</div>" +
      '<div class="rsa-sub">' + esc(tw("resonance.t0_where")) + "</div>" +
      '<div class="rsa-sub rsa-note">' + esc(tw("resonance.auto_not_full")) + "</div>";
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
    if (on) html += verifyNoteHtml();
    var list = (goals || []).filter(function (g) { return g && g.goal_id; });
    html += '<div class="rsa-goals-title">' + esc(tw("resonance.a1_goals_title")) + "</div>";
    if (!list.length) html += '<div class="rsa-sub">' + esc(tw("resonance.a1_no_goals")) + "</div>";
    list.forEach(function (g) {
      html += '<div class="rs-card rsa-card" data-goal="' + esc(g.goal_id) + '"></div>';
    });
    return html;
  }

  /* A3: mục "Bài học" của trợ lý (GET /resonance/lessons). Một cột (luật trang cài đặt xếp một cột): đề xuất kèm câu cũ
     và câu mới xếp dọc, bài học đang dùng có nút Thu hồi, lịch sử ngắn. Khoá từ điển nguyên văn qua bảng tra. */
  var LESSON_KEYS = {
    "notice_detail:brief": "resonance.a3_p_brief",
    "notice_detail:full": "resonance.a3_p_full",
    "notice_ping:quiet": "resonance.a3_p_quiet",
    "notice_ping:ping": "resonance.a3_p_ping"
  };
  var STATUS_KEYS = {
    proposed: "resonance.a3_st_proposed", active: "resonance.a3_st_active", superseded: "resonance.a3_st_superseded",
    revoked: "resonance.a3_st_revoked", dismissed: "resonance.a3_st_dismissed", expired: "resonance.a3_st_expired",
    stale: "resonance.a3_st_stale", skipped: "resonance.a3_st_skipped", rejected: "resonance.a3_st_rejected",
    unknown: "resonance.a3_st_unknown", out_of_scope: "resonance.a3_st_out_of_scope",
    trial_pending: "resonance.a3_st_trial_pending", trialing: "resonance.a3_st_trialing"
  };

  /* Câu xem trước dựng từ mẫu tin báo (markdown): bỏ cú pháp liên kết, giữ chữ. */
  function plainMd(s) {
    return String(s == null ? "" : s).replace(/\[([^\]]*)\]\(([^)]*)\)/g, "$1");
  }

  function lessonLabel(l) {
    if (l.lane === "method") return tw("resonance.a3_m_method", { to: l.to_label || l.to_value || "" });
    var k = String(l.key || "") + ":" + String(l.to_value || "");
    return tw(Object.prototype.hasOwnProperty.call(LESSON_KEYS, k) ? LESSON_KEYS[k] : "resonance.a3_p_other");
  }

  function statusLabel(st) {
    return tw(Object.prototype.hasOwnProperty.call(STATUS_KEYS, st) ? STATUS_KEYS[st] : "resonance.a3_st_unknown");
  }

  function lessonsHtml(data) {
    var d = data || {};
    var all = d.lessons || [];
    var html = '<div class="rsa-goals-title">' + esc(tw("resonance.a3_lessons_title")) + "</div>";
    var props = all.filter(function (l) { return l.status === "proposed" && l.lane === "presentation"; });
    var act = all.filter(function (l) { return l.status === "active"; });
    // Phép thử cách làm đang chờ hay đang chạy: hiện riêng kèm nút Bỏ qua, không lẫn vào lịch sử.
    var trying = all.filter(function (l) {
      return l.lane === "method" && (l.status === "trial_pending" || l.status === "trialing");
    });
    var hist = all.filter(function (l) {
      return l.status !== "proposed" && l.status !== "active" && trying.indexOf(l) < 0;
    }).slice(0, 5);
    if (!all.length) html += '<div class="rsa-sub">' + esc(tw("resonance.a3_lessons_empty")) + "</div>";
    props.forEach(function (l) {
      var n = ((l.evidence || {}).reactions || []).length;
      html += '<div class="rsa-lesson rsa-proposed" data-lid="' + esc(l.id) + '">' +
        '<div class="rsa-lesson-text">' + esc(lessonLabel(l)) + "</div>" +
        '<div class="rsa-sub">' + esc(tw("resonance.a3_evidence", { n: n })) + "</div>";
      var pv = l.preview || {};
      if (pv.kind === "detail") {
        html += '<div class="rsa-pv"><div class="rsa-pv-label">' + esc(tw("resonance.a3_preview_old")) + "</div>" +
          '<div class="rsa-pv-text">' + esc(plainMd(pv.old)) + "</div>" +
          '<div class="rsa-pv-label">' + esc(tw("resonance.a3_preview_new")) + "</div>" +
          '<div class="rsa-pv-text">' + esc(plainMd(pv.new)) + "</div></div>";
      } else if (pv.kind === "ping") {
        html += '<div class="rsa-sub">' + esc(tw("resonance.a3_preview_ping")) + "</div>";
      }
      html += '<div class="rsa-sub">' + esc(tw("resonance.a3_mandatory_note")) + "</div>" +
        '<div class="rsa-acts"><button type="button" class="ws-btn rsa-lesson-act" data-act="apply" data-lid="' +
        esc(l.id) + '" data-upd="' + esc(l.updated_at) + '">' + esc(tw("resonance.a3_apply")) + "</button>" +
        '<button type="button" class="ws-btn rsa-lesson-act" data-act="dismiss" data-lid="' + esc(l.id) + '">' +
        esc(tw("resonance.a3_dismiss")) + "</button></div></div>";
    });
    trying.forEach(function (l) {
      html += '<div class="rsa-lesson rsa-trying" data-lid="' + esc(l.id) + '">' +
        '<div class="rsa-lesson-text">' + esc(lessonLabel(l)) + " · " + esc(statusLabel(l.status)) + "</div>" +
        (l.goal_label ? '<div class="rsa-sub">' + esc(l.goal_label) + "</div>" : "") +
        '<div class="rsa-acts"><button type="button" class="ws-btn rsa-lesson-act" data-act="dismiss" data-lid="' +
        esc(l.id) + '">' + esc(tw("resonance.a3_dismiss")) + "</button></div></div>";
    });
    act.forEach(function (l) {
      html += '<div class="rsa-lesson rsa-active" data-lid="' + esc(l.id) + '">' +
        '<div class="rsa-lesson-text">' + esc(lessonLabel(l)) + " · " + esc(statusLabel(l.status)) + "</div>" +
        (l.goal_label ? '<div class="rsa-sub">' + esc(l.goal_label) + "</div>" : "") +
        '<div class="rsa-sub">' + esc(tw(l.lane === "method" ? "resonance.a3_scope_goal" : "resonance.a3_scope_agent")) +
        "</div>" +
        (l.evidence_missing ? '<div class="rsa-sub">' + esc(tw("resonance.a3_evidence_missing")) + "</div>" : "") +
        '<div class="rsa-acts"><button type="button" class="ws-btn rsa-lesson-act" data-act="revoke" data-lid="' +
        esc(l.id) + '">' + esc(tw("resonance.a3_revoke")) + "</button></div></div>";
    });
    if (hist.length) {
      html += '<div class="rsa-sub">' + esc(tw("resonance.a3_history")) + "</div>" + hist.map(function (l) {
        return '<div class="rsa-sub rsa-hist">' + esc(lessonLabel(l)) + " · " + esc(statusLabel(l.status)) + "</div>";
      }).join("");
    }
    var st = d.stats || {};
    if (st.up || st.down) {
      html += '<div class="rsa-sub">' + esc(tw("resonance.a3_stats", { up: st.up || 0, down: st.down || 0 })) + "</div>";
    }
    return html;
  }

  /* Khối trên trang Cài đặt (T0): chỉ còn tóm tắt và đường sang trang Cộng sự, nơi bật, tắt từng trợ lý. Trợ lý mất
     file vẫn được liệt kê bằng chữ để thấy; mã mồ côi; mục tiêu chờ gán kèm ô chọn trợ lý. */
  function settingsHtml(data, unassigned) {
    var d = data || {};
    var agents = d.agents || [];
    var html = '<div class="opt-sub">' + esc(tw("resonance.a1_settings_desc")) + "</div>";
    if (!agents.length) html += '<div class="opt-sub">' + esc(tw("resonance.a1_settings_empty")) + "</div>";
    else {
      var nOn = agents.filter(function (a) { return a && a.enabled && a.status === "active"; }).length;
      html += '<div class="opt-sub rsa-summary">' + esc(tw("resonance.t0_settings_summary", { n: nOn })) + "</div>" +
        '<button type="button" class="ws-btn rsa-goto-ws">' + esc(tw("resonance.t0_settings_manage")) + "</button>";
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
        host.innerHTML = panelHtml(row, session, goals, (res.j && res.j.agents) || []);
        wire(host, row);
        if (key) {
          // A3: mục Bài học của trợ lý (đọc ghi bù hết hạn đề xuất ở server). Lỗi tải thì bỏ qua mục này.
          getJson("/resonance/lessons?brain=" + q(brain()) + "&agent_key=" + q(key)).then(function (lr) {
            if (t !== S.ticket || lr.code !== 200) return;
            var box = document.createElement("div");
            box.className = "rsa-lessons";
            // Câu báo xung đột của lần bấm trước được giữ qua lần vẽ lại (không thì vừa hiện đã mất).
            box.innerHTML = (S.lessonNote ? '<div class="rsa-warn">' + esc(S.lessonNote) + "</div>" : "") +
              lessonsHtml(lr.j);
            S.lessonNote = "";
            host.appendChild(box);
          }).catch(function () {});
        }
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
    // `host` sống qua nhiều lần vẽ lại: chỉ gắn trình nghe MỘT lần, không thì một lần bấm gửi nhiều request.
    if (!host._a3Wired && host.addEventListener) {
      host._a3Wired = true;
      host.addEventListener("click", function (ev) {
        var b = ev.target && ev.target.closest && ev.target.closest(".rsa-lesson-act");
        if (!b) return;
        var act = b.getAttribute("data-act");
        if (act === "revoke" && !window.confirm(tw("resonance.a3_revoke_q"))) return;
        b.disabled = true;
        var upd = b.getAttribute("data-upd");
        postJson("/resonance/lessons/" + q(b.getAttribute("data-lid")) + "/decision?brain=" + q(brain()),
          { action: act, expected_status: act === "apply" ? "proposed" : "", expected_updated_at: upd || "" })
          .then(function (res) {
            if (res.code !== 200) {
              S.lessonNote = tw("resonance.a3_changed");
            }
            refresh();
          }).catch(function () { b.disabled = false; });
      });
    }
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
    // A3: một phản hồi trên tin báo vừa ghi (chat-resonance.js); không tải lại thì mục Bài học vẫn hiện "chưa có".
    window.addEventListener("javis:resonance-lessons", function () {
      if (S.host && S.host.isConnected) refresh();
    });
    // T0: công tắc trên dòng trợ lý (hay tab khác) vừa đổi trạng thái: bảng bên phải hỏi lại host.
    window.addEventListener("javis:resonance-agents-changed", function () {
      if (S.host && S.host.isConnected) refresh();
    });
  }

  var api = { mount: mount, refresh: refresh, panelHtml: panelHtml, verifyNoteHtml: verifyNoteHtml,
    rowToggleHtml: rowToggleHtml, stateKey: stateKey, offConfirmText: offConfirmText, toggleAgent: toggleAgent,
    settingsHtml: settingsHtml, toggleNote: toggleNote,
    lessonsHtml: lessonsHtml, supportHtml: supportHtml };
  if (typeof window !== "undefined") window.JavisResonanceAgent = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
