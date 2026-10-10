/* chat-resonance.js - thẻ "Javis đang hướng tới" của Hệ thống cộng hưởng (Resonance M4).

   Server gắn vào tin nhắn một khối ẩn (cùng khuôn với JAVIS_VIEC, JAVIS_ASK):
       <!-- JAVIS_RESONANCE: {"goal_id":"g_...","revision":1,"report":"outbox:12"} -->
   Khối chỉ mang id mục tiêu; trạng thái SỐNG luôn đọc lại qua GET /goals/{id}, nên F5, mở lại hội thoại hay
   nhận lại tin cũ đều vẽ đúng tình trạng hiện tại, không phải ảnh chụp lúc gửi.

   Hai câu hỏi TÁCH RIÊNG (spec 4.5, 4.7):
     - Đúng ý / Chưa đúng ý: xác nhận CÁCH HIỂU của đúng revision đang hiện.
     - Đạt yêu cầu / Cần chỉnh: xác nhận SẢN PHẨM cho đúng tiêu chí người dùng tự duyệt và đúng bản đang hiện.
   Mọi nút gửi kèm revision (và artifact_ref) lấy từ trạng thái đã TẢI về, không tự điền; thẻ cũ bấm vào
   revision mới thì server trả 409 và thẻ vẽ lại theo trạng thái mới. Im lặng không phải xác nhận.

   Hàm thuần (tach, viewHtml, requestFor) test được bằng node. Không dùng ký tự em dash ở bất kỳ đâu. */
(function () {
  "use strict";

  var RE = /<!--\s*JAVIS_RESONANCE:\s*([\s\S]*?)\s*-->\s*/g;

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

  /* Bóc mọi khối JAVIS_RESONANCE. LUÔN trả `clean` đã bỏ khối, kể cả khi JSON hỏng: khối hỏng không được lọt ra
     màn hình hay bị đọc thành tiếng. */
  function tach(text) {
    var s = String(text == null ? "" : text);
    var cards = [];
    var clean = s.replace(RE, function (m, json) {
      try {
        var d = JSON.parse(json);
        if (d && typeof d === "object" && typeof d.goal_id === "string" && d.goal_id) {
          cards.push({ goal_id: d.goal_id, revision: Number(d.revision) || 0, report: String(d.report || "") });
        }
      } catch (e) { /* khối hỏng: bỏ qua, vẫn bóc */ }
      return "";
    }).replace(/^\s+|\s+$/g, "");
    return { clean: clean, cards: cards };
  }

  /* Tình trạng hiện ra cho người đọc: một khoá từ điển theo status / run_state / block_reason. */
  function stateKey(g) {
    if (g.status === "succeeded") return "resonance.st_succeeded";
    if (g.status === "cancelled") return "resonance.st_cancelled";
    if (g.status === "failed") return "resonance.st_failed";
    if (g.paused) return "resonance.st_paused";
    var r = String(g.block_reason || "");
    var known = ["human_confirmation", "fit_rejected", "guard", "guard_unknown", "budget", "discovery_done",
                 "healthy", "scheduled", "feature_off", "engine_blocked",
                 // A1: cổng theo trợ lý
                 "unassigned", "agent_off", "agent_missing", "agent_retired", "agent_changed", "agent_unknown",
                 // A2: nhịp tim thích nghi
                 "stalled", "source_drift", "handoff",
                 // A4: phạm vi ghi do chủ dự án cho phép
                 "scope_pending", "scope_denied", "grant_revoked", "grant_missing", "path_rejected"];
    if (known.indexOf(r) >= 0) return "resonance.st_" + r;
    if (g.run_state === "running") return "resonance.st_running";
    if (g.run_state === "blocked") return "resonance.st_blocked";
    return "resonance.st_working";
  }

  /* Nhãn dịch được cho mã lý do thức (A2). Mã lạ hiện như lần xem lại định kỳ, không lộ mã thô. */
  var WAKE_KEYS = {
    created: "resonance.wake.created",
    revised: "resonance.wake.revised",
    assigned: "resonance.wake.assigned",
    feedback: "resonance.wake.feedback",
    user_schedule: "resonance.wake.user_schedule",
    retry_not_met: "resonance.wake.retry_not_met",
    error_retry: "resonance.wake.error_retry",
    recovery: "resonance.wake.recovery",
    action_recovery: "resonance.wake.recovery",
    handoff_wait: "resonance.wake.handoff_wait",
    handoff_done: "resonance.wake.handoff_done",
    resumed: "resonance.wake.resumed",
    agent_enabled: "resonance.wake.agent_enabled",
    agent_recheck: "resonance.wake.agent_recheck",
    agent_changed: "resonance.wake.agent_changed",
    guard_recheck: "resonance.wake.guard_recheck",
    review: "resonance.wake.review",
    deadline: "resonance.wake.deadline",
    drift_recheck: "resonance.wake.drift_recheck",
    guard_observe: "resonance.wake.guard_observe",
    // A3: phép thử cách làm khi bế tắc, và lượt làm sản phẩm bằng cách làm vừa học
    method_trial: "resonance.wake.method_trial",
    method_followup: "resonance.wake.method_followup",
    trial_recovery: "resonance.wake.recovery",
    // A4: chủ dự án vừa cho phép phạm vi ghi
    scope_granted: "resonance.wake.scope_granted"
  };

  /* A3: dòng "cách làm đã học" trên thẻ, theo trạng thái bài học làn M của revision hiện tại. Khoá nguyên văn. */
  var LEARN_KEYS = {
    trial_pending: "resonance.a3_learn_pending",
    trialing: "resonance.a3_learn_trialing",
    active: "resonance.a3_learn_active",
    rejected: "resonance.a3_learn_kept",
    unknown: "resonance.a3_learn_kept",
    skipped: "resonance.a3_learn_skipped",
    dismissed: "resonance.a3_learn_dismissed",
    revoked: "resonance.a3_learn_revoked"
  };
  var SKIP_KEYS = {
    budget: "resonance.a3_skip_budget",
    no_holdout: "resonance.a3_skip_no_holdout",
    untestable: "resonance.a3_skip_untestable",
    new_feedback: "resonance.a3_skip_new_feedback"
  };

  function learnHtml(g) {
    var l = g.learning;
    if (!l || !Object.prototype.hasOwnProperty.call(LEARN_KEYS, l.status)) return "";
    var h = '<div class="rs-line rs-learn">' + esc(tw(LEARN_KEYS[l.status], { to: l.to_label || l.to || "" }));
    if (l.status === "skipped") {
      h += " " + esc(tw(Object.prototype.hasOwnProperty.call(SKIP_KEYS, l.reason) ? SKIP_KEYS[l.reason]
        : "resonance.a3_skip_other"));
    }
    if (g.status === "active" && l.status === "active") {
      h += ' <button type="button" class="rs-act" data-act="revert_method">' + esc(tw("resonance.btn_revert_method")) +
        "</button>";
    }
    if (g.status === "active" && (l.status === "trial_pending" || l.status === "trialing")) {
      h += ' <button type="button" class="rs-act" data-act="lesson_dismiss" data-lesson="' + esc(l.lesson_id) + '">' +
        esc(tw("resonance.btn_lesson_dismiss")) + "</button>";
    }
    return h + "</div>";
  }

  /* A4: dòng quyền của thẻ (thiết kế A4 mục 8). Chỉ hiển thị; kho mới là căn cứ. Cho phép gửi đúng yêu cầu, đường,
     bản nháp và sha đang hiện; thẻ cũ thì server trả 409 và thẻ vẽ lại. Javis không cấp quyền ghi từ lời chat. */
  function kb(n) {
    var v = Number(n) || 0;
    return (Math.round(v / 102.4) / 10).toLocaleString();
  }

  function scopeHtml(g) {
    var s = g.scope;
    if (!s || g.status !== "active" || !s.state || s.state === "none" || s.state === "unknown") return "";
    var path = '<code class="rs-path">' + esc(s.path || "") + "</code>";
    var h = "";
    if (s.state === "granted") {
      h += '<div class="rs-line rs-scope">' + tw("resonance.a4_scope_granted", { path: path,
        budget: g.budget_calls || 0 }) + ' <button type="button" class="rs-act" data-act="revoke_grant">' +
        esc(tw("resonance.btn_revoke_grant")) + "</button></div>";
    } else if (s.state === "pending" && s.request) {
      h += '<div class="rs-warn rs-scope">' + tw("resonance.a4_scope_ask", { path: path });
      if (s.draft) {
        h += " " + esc(tw("resonance.a4_scope_draft", { kb: kb(s.draft.size) }));
      }
      h += '<span class="rs-btns"><button type="button" class="rs-act" data-act="approve_scope">' +
        esc(tw("resonance.btn_approve_scope")) + "</button>" +
        '<button type="button" class="rs-act" data-act="deny_scope">' + esc(tw("resonance.btn_deny_scope")) + "</button>" +
        (s.draft ? '<button type="button" class="rs-act" data-act="draft_preview">' + esc(tw("resonance.btn_preview")) +
          "</button>" : "") + "</span></div>";
    } else if (s.state === "revoked") {
      h += '<div class="rs-warn rs-scope">' + tw("resonance.a4_scope_revoked", { path: path }) + "</div>";
    } else if (s.state === "denied") {
      h += '<div class="rs-warn rs-scope">' + tw("resonance.a4_scope_denied", { path: path }) + "</div>";
    } else {
      h += '<div class="rs-warn rs-scope">' + tw("resonance.a4_scope_missing", { path: path }) + "</div>";
    }
    if (s.pending_publish) {
      h += '<div class="rs-line rs-muted">' + esc(tw("resonance.a4_drafts_waiting", { n: s.pending_publish })) + "</div>";
    }
    if (s.conflict) h += '<div class="rs-warn">' + esc(tw("resonance.a4_draft_conflict")) + "</div>";
    return h;
  }

  /* A3 làn P: hàng phản hồi dưới tin báo do host ghi (khối thẻ có khoá báo cáo `outbox:`). Thuần để test. */
  var REASONS = ["too_long", "too_often", "unclear"];
  var REASON_KEYS = { too_long: "resonance.react_too_long", too_often: "resonance.react_too_often",
                      unclear: "resonance.react_unclear" };

  function reactHtml(st, open, note) {
    st = st || {};
    var v = st.value || "none";
    function b(act, on, label, title, reason) {
      return '<button type="button" class="rs-react-b' + (on ? " rs-on" : "") + '" data-ract="' + act + '"' +
        (reason ? ' data-reason="' + reason + '"' : "") + ' aria-pressed="' + (on ? "true" : "false") +
        '" title="' + esc(title) + '">' + esc(label) + "</button>";
    }
    var h = '<span class="rs-react-q">' + esc(tw("resonance.react_q")) + "</span>" +
      b("up", v === "up", tw("resonance.react_up"), tw("resonance.react_up")) +
      b("down", v === "down", tw("resonance.react_down"), tw("resonance.react_down"));
    if (open || v === "down") {
      h += '<span class="rs-react-why">' + REASONS.map(function (r) {
        return b("reason", v === "down" && st.reason === r, tw(REASON_KEYS[r]), tw(REASON_KEYS[r]), r);
      }).join("") + "</span>";
    }
    if (note) h += '<div class="rs-note">' + esc(note) + "</div>";
    return h;
  }

  /* Request của một lần bấm. API ĐẶT giá trị theo request (không tự đảo); luật "bấm lại đúng nút đang sáng là thu
     hồi" là của giao diện, nên trang tự gửi `none`. Mỗi lần bấm một nonce mới; gửi lại chính request đó giữ nonce. */
  function reactBody(cur, act, reason, ctx, nonce) {
    cur = cur || {};
    var value, why = "";
    if (act === "up") {
      value = cur.value === "up" ? "none" : "up";
    } else if (act === "reason") {
      value = (cur.value === "down" && cur.reason === reason) ? "none" : "down";
      why = value === "down" ? String(reason || "") : "";
    } else {
      value = (cur.value === "down" && !cur.reason) ? "none" : "down";
    }
    return { session_id: String((ctx || {}).session_id || ""), report: String((ctx || {}).report || ""),
             goal_id: String((ctx || {}).goal_id || ""), value: value, reason: why, nonce: nonce || newNonce() };
  }

  /* Chỉ tin báo do host ghi (khối thẻ mang khoá báo cáo `outbox:`) mới có hàng phản hồi; server vẫn kiểm biên nhận. */
  function isNotice(card) {
    return /^outbox:[0-9]+$/.test(String((card || {}).report || ""));
  }

  function veReact(msgEl, card) {
    if (!isNotice(card)) return null;
    if (msgEl.querySelector('.rs-react[data-report="' + card.report + '"]')) return null;
    var row = document.createElement("div");
    row.className = "rs-react";
    row.setAttribute("data-report", card.report);
    row.setAttribute("data-goal", card.goal_id);
    // Không gửi phiên: lúc vẽ tin, phiên "đang mở" có thể còn là phiên cũ (trang Cộng sự vừa đổi trợ lý), và một
    // phiên sai làm server từ chối. Khoá `outbox:` chỉ thuộc một tin, server tự tra biên nhận theo khoá và mục tiêu.
    row._ctx = { session_id: "", report: card.report, goal_id: card.goal_id };
    row._st = {};
    var bubble = msgEl.querySelector(".bubble");
    (bubble || msgEl).appendChild(row);
    var c = row._ctx;
    fetch("/resonance/reactions?brain=" + encodeURIComponent(brain()) + "&session_id=" + encodeURIComponent(c.session_id) +
          "&report=" + encodeURIComponent(c.report) + "&goal_id=" + encodeURIComponent(c.goal_id),
          { credentials: "same-origin" })
      .then(function (r) { return r.json().then(function (j) { return { code: r.status, j: j }; }); })
      .then(function (res) {
        if (res.code !== 200) { row.remove(); return; }
        row._st = res.j.reaction || {};
        row.innerHTML = reactHtml(row._st, false);
      })
      .catch(function () { row.remove(); });
    return row;
  }

  function sendReact(row, act, reason) {
    var body = reactBody(row._st, act, reason, row._ctx);
    if (act === "down" && body.value === "down") row._open = true;
    var btns = row.querySelectorAll("button");
    for (var i = 0; i < btns.length; i++) btns[i].disabled = true;
    fetch("/resonance/reactions?brain=" + encodeURIComponent(brain()), {
      method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    })
      .then(function (r) { return r.json().then(function (j) { return { code: r.status, j: j }; }); })
      .then(function (res) {
        if (res.code !== 200) { row.innerHTML = reactHtml(row._st, row._open, res.j.error || tw("resonance.failed")); return; }
        row._st = res.j.reaction || {};
        row.innerHTML = reactHtml(row._st, row._open && row._st.value !== "none",
          res.j.proposal ? tw("resonance.react_proposal") : "");
        // Mục Bài học ở ngăn trợ lý (resonance-agent.js) đang mở thì tải lại: đề xuất mới và số đếm 30 ngày vừa đổi.
        try { window.dispatchEvent(new CustomEvent("javis:resonance-lessons")); } catch (e) {}
      })
      .catch(function () { row.innerHTML = reactHtml(row._st, row._open, tw("resonance.failed")); });
  }

  function wakeLabel(code) {
    return tw(Object.prototype.hasOwnProperty.call(WAKE_KEYS, code) ? WAKE_KEYS[code] : WAKE_KEYS.review);
  }

  function verdictKey(v) {
    return v === "met" ? "resonance.v_met" : v === "not_met" ? "resonance.v_not_met" : "resonance.v_unknown";
  }

  function fmtTime(ts) {
    if (!ts) return "";
    try {
      var d = new Date(Number(ts) * 1000);
      return d.toLocaleString();
    } catch (e) { return ""; }
  }

  /* HTML của thẻ từ trạng thái GET /goals/{id}. Thuần: không đụng DOM, không gọi mạng. */
  function viewHtml(g, note) {
    g = g || {};
    var active = g.status === "active";
    var h = '<div class="rs-head"><span class="rs-title">' + esc(tw("resonance.card_title")) + "</span>" +
      '<span class="rs-state rs-' + esc(String(g.status || "")) + '">' + esc(tw(stateKey(g))) + "</span></div>";
    h += '<div class="rs-understanding">' + esc(g.understanding || tw("resonance.no_understanding")) + "</div>";
    var crit = (g.criteria || []).map(function (c) {
      var buttons = "";
      if (active && c.evaluator === "human_confirmation" && g.artifact_ref && c.verdict === "unknown") {
        buttons = '<span class="rs-btns">' +
          '<button type="button" class="rs-act" data-act="out_ok" data-crit="' + esc(c.id) + '">' +
          esc(tw("resonance.btn_out_ok")) + "</button>" +
          '<button type="button" class="rs-act" data-act="out_no" data-crit="' + esc(c.id) + '">' +
          esc(tw("resonance.btn_out_no")) + "</button></span>";
      }
      return '<li class="rs-crit rs-v-' + esc(c.verdict || "unknown") + '"><span class="rs-v">' +
        esc(tw(verdictKey(c.verdict))) + "</span> " + esc(c.description || "") +
        (c.reason && c.verdict !== "met" ? ' <span class="rs-reason">(' + esc(c.reason) + ")</span>" : "") +
        buttons + "</li>";
    }).join("");
    if (crit) h += '<div class="rs-label">' + esc(tw("resonance.criteria")) + '</div><ul class="rs-list">' + crit + "</ul>";
    if (g.deliverable) {
      h += '<div class="rs-line"><span class="rs-label">' + esc(tw("resonance.deliverable")) + "</span> " +
        '<code class="rs-path">' + esc(g.deliverable) + "</code></div>";
    }
    if ((g.assumptions || []).length) {
      h += '<div class="rs-label">' + esc(tw("resonance.assumptions")) + '</div><ul class="rs-list">' +
        g.assumptions.map(function (a) { return "<li>" + esc(a) + "</li>"; }).join("") + "</ul>";
    }
    if (active && (g.directives || []).length) {
      var DIR = { deadline: "resonance.dir_deadline", target: "resonance.dir_target",
                  constraint: "resonance.dir_constraint", guard: "resonance.dir_guard" };
      h += '<div class="rs-label">' + esc(tw("resonance.directives")) + '</div><ul class="rs-list">' +
        g.directives.map(function (d) {
          return '<li class="rs-dir">' + esc(tw(DIR[d.field] || "resonance.dir_target", { text: d.text })) +
            ' <button type="button" class="rs-act rs-drop" data-act="drop" data-field="' + esc(d.field) +
            '" data-key="' + esc(d.key) + '">' + esc(tw("resonance.btn_drop")) + "</button></li>";
        }).join("") + "</ul>";
    }
    if (g.next_wake && active && !g.paused) {
      h += '<div class="rs-line rs-muted">' + esc(tw("resonance.next_wake", { at: fmtTime(g.next_wake.at) })) +
        " (" + esc(wakeLabel(g.next_wake.code)) + ")</div>";
    }
    // A2: file bị sửa ngoài Javis, và trạng thái theo dõi điều kiện bảo vệ (không hiện như đang an toàn khi đã ngừng).
    if (active && g.source_drift) {
      h += '<div class="rs-warn">' + esc(tw("resonance.drift", { path: g.source_drift.path || "",
        at: g.next_wake ? fmtTime(g.next_wake.at) : "" })) + "</div>";
    }
    if (active && g.observe && g.observe.state === "lost") {
      h += '<div class="rs-warn">' + esc(tw("resonance.observe_lost")) + "</div>";
    } else if (active && g.observe && g.observe.state === "on" && g.observe.next_at) {
      h += '<div class="rs-line rs-muted">' + esc(tw("resonance.observe_on", { at: fmtTime(g.observe.next_at) })) +
        "</div>";
    }
    h += scopeHtml(g);
    h += learnHtml(g);
    h += '<div class="rs-line rs-muted">' + esc(tw("resonance.budget", { used: g.calls_used || 0,
      total: g.budget_calls || 0 })) + "</div>";
    if (active) {
      var fit = g.fit === "confirmed" ? tw("resonance.fit_confirmed")
        : g.fit === "rejected" ? tw("resonance.fit_rejected") : "";
      h += '<div class="rs-actions">' +
        (fit ? '<span class="rs-fit">' + esc(fit) + "</span>" : "") +
        '<button type="button" class="rs-act" data-act="fit_ok">' + esc(tw("resonance.btn_fit_ok")) + "</button>" +
        '<button type="button" class="rs-act" data-act="fit_no">' + esc(tw("resonance.btn_fit_no")) + "</button>" +
        (g.paused
          ? '<button type="button" class="rs-act" data-act="resume">' + esc(tw("resonance.btn_resume")) + "</button>"
          : '<button type="button" class="rs-act" data-act="pause">' + esc(tw("resonance.btn_pause")) + "</button>") +
        (g.block_reason === "guard"
          ? '<button type="button" class="rs-act" data-act="resume">' + esc(tw("resonance.btn_reopen")) + "</button>"
          : "") +
        '<button type="button" class="rs-act rs-danger" data-act="cancel">' + esc(tw("resonance.btn_cancel")) +
        "</button></div>";
    }
    var tl = (g.timeline || []).map(function (x) {
      return "<li>" + esc(fmtTime(x.at)) + " " + esc(x.kind === "publish" ? tw("resonance.kind_publish") : tw("resonance.kind_work")) +
        ": " + esc(x.status) + (x.error_code ? " (" + esc(x.error_code) + ")" : "") + "</li>";
    }).join("");
    var wk = (g.wakes_recent || []).slice().reverse().map(function (x) {
      var codes = (x.codes || []).length ? x.codes : [x.kind === "observe" ? "guard_observe" : "review"];
      return "<li>" + esc(fmtTime(x.at)) + " · " + esc(wakeLabel(codes[0])) + " · " +
        esc(tw(x.model_calls ? "resonance.wake_model" : "resonance.wake_no_model")) + "</li>";
    }).join("");
    h += '<details class="rs-details"><summary>' + esc(tw("resonance.details", { rev: g.revision || 0 })) +
      "</summary>" + (tl ? '<ul class="rs-list rs-timeline">' + tl + "</ul>" : "") +
      (wk ? '<div class="rs-label">' + esc(tw("resonance.wakes_recent")) + '</div><ul class="rs-list rs-wakes">' +
        wk + "</ul>" : "") + "</details>";
    if (note) h += '<div class="rs-note">' + esc(note) + "</div>";
    return h;
  }

  /* Request của một nút, dựng TỪ TRẠNG THÁI ĐÃ TẢI: revision, artifact_ref, criterion_id đều là của đúng bản
     người dùng đang nhìn. Thuần để test. */
  /* `nonce` định danh MỘT lần bấm (review M4, P1-2): gửi lại chính request đó dùng lại khoá nên server ghi đúng
     một lần, còn một lần bấm mới (kể cả sau khi đã bấm ý ngược lại) có khoá mới và luôn được ghi. Không truyền
     nonce thì tự sinh: mỗi request dựng ra là một lần bấm riêng. */
  function newNonce() {
    return Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
  }

  function requestFor(act, g, critId, dir, nonce) {
    nonce = nonce || newNonce();
    var id = encodeURIComponent(g.goal_id);
    var rev = Number(g.revision) || 0;
    var key = g.goal_id + ":" + rev + ":" + act + (critId ? ":" + critId : "") + ":" + String(nonce);
    if (act === "fit_ok" || act === "fit_no") {
      return { url: "/goals/" + id + "/feedback", body: { kind: act === "fit_ok" ? "goal_fit_confirmed" : "goal_fit_rejected",
        expected_revision: rev, idempotency_key: key } };
    }
    if (act === "out_ok" || act === "out_no") {
      return { url: "/goals/" + id + "/feedback", body: { kind: act === "out_ok" ? "outcome_accepted" : "outcome_rejected",
        expected_revision: rev, criterion_id: String(critId || ""), artifact_ref: String(g.artifact_ref || ""),
        idempotency_key: key } };
    }
    if (act === "lesson_dismiss") {
      return { url: "/resonance/lessons/" + encodeURIComponent(String((dir || {}).lesson || "")) + "/decision",
        body: { action: "dismiss" } };
    }
    if (act === "drop") {
      return { url: "/goals/" + id + "/commands", body: { command: "drop_directive", expected_revision: rev,
        field: String((dir || {}).field || ""), key: String((dir || {}).key || "") } };
    }
    // A4: Cho phép / Không gửi ĐÚNG yêu cầu, đường và bản nháp (mã, sha) đang hiện trên thẻ; thẻ cũ nhận 409.
    var sc = g.scope || {};
    if (act === "approve_scope") {
      var d = sc.draft || {};
      return { url: "/goals/" + id + "/commands", body: { command: "approve_scope", expected_revision: rev,
        request_id: String((sc.request || {}).id || ""), path: String(sc.path || ""),
        submission_id: String(d.submission_id || ""), sha256: String(d.sha256 || "") } };
    }
    if (act === "deny_scope") {
      return { url: "/goals/" + id + "/commands", body: { command: "deny_scope", expected_revision: rev,
        request_id: String((sc.request || {}).id || "") } };
    }
    return { url: "/goals/" + id + "/commands", body: { command: act, expected_revision: rev } };
  }

  function brain() {
    try { return (window.currentBrainPath && window.currentBrainPath()) || "brain"; }
    catch (e) { return "brain"; }
  }

  /* HTML gọn cho thẻ CŨ của cùng mục tiêu: một mục tiêu có thể xuất hiện ở nhiều tin (lúc lập, lúc báo tiến
     triển). Chỉ thẻ mới nhất hiện đầy đủ và có nút; thẻ cũ chỉ còn một dòng tình trạng, không mâu thuẫn nhau. */
  function compactHtml(g) {
    return '<div class="rs-head"><span class="rs-title">' + esc(tw("resonance.card_title")) + "</span>" +
      '<span class="rs-state rs-' + esc(String(g.status || "")) + '">' + esc(tw(stateKey(g))) + "</span></div>" +
      '<div class="rs-muted">' + esc(g.understanding || "") + " · " + esc(tw("resonance.see_latest")) + "</div>";
  }

  /* Vẽ MỌI thẻ của cùng mục tiêu theo cùng một trạng thái: thẻ cuối đầy đủ, thẻ trước gọn. */
  function render(el, g, note) {
    var all = (typeof document !== "undefined" && document.querySelectorAll)
      ? Array.prototype.slice.call(document.querySelectorAll('.rs-card[data-goal="' + g.goal_id + '"]')) : [el];
    if (all.indexOf(el) < 0) all.push(el);
    var last = all[all.length - 1];
    all.forEach(function (x) {
      x._goal = g;
      x.classList.toggle("rs-done", g.status !== "active");
      x.classList.toggle("rs-old", x !== last);
      x.innerHTML = x === last ? viewHtml(g, note) : compactHtml(g);
    });
  }

  /* Tải trạng thái MỘT mục tiêu cho các thẻ của nó (audit tốc độ 08/10/2026). Mở lại hội thoại có nhiều tin báo của
     cùng mục tiêu từng phát mỗi thẻ một GET và mỗi kết quả vẽ lại MỌI thẻ: 50 thẻ ra 50 request và 2.500 lần vẽ.
     Nay các thẻ cùng (brain, mục tiêu) trong lúc một request đang chạy dùng chung request đó, và kết quả vẽ mọi thẻ
     ĐÚNG MỘT LẦN. Kết quả về khi đã đổi brain thì bỏ. `fresh`: sau một thao tác (bấm nút) luôn đọc lại trạng thái MỚI,
     không ghép vào request cũ đang chạy, để revision và artifact_ref là của bản hiện hành. */
  var INFLIGHT = {};

  function load(el, fresh) {
    var id = el.getAttribute("data-goal");
    var b = brain();
    var key = b + "\n" + id;
    var cur = INFLIGHT[key];
    if (cur && !fresh) {
      if (cur.els.indexOf(el) < 0) cur.els.push(el);
      return cur.promise;
    }
    var entry = { els: [el], brain: b };
    function fail(msg) {
      entry.els.forEach(function (x) { x.innerHTML = '<div class="rs-note">' + esc(msg) + "</div>"; });
    }
    entry.promise = fetch("/goals/" + encodeURIComponent(id) + "?brain=" + encodeURIComponent(b),
                          { credentials: "same-origin" })
      .then(function (r) { return r.json().then(function (j) { return { code: r.status, j: j }; }); })
      .then(function (res) {
        if (INFLIGHT[key] === entry) delete INFLIGHT[key];
        if (brain() !== entry.brain) return;            // đã đổi brain: kết quả thuộc brain cũ, không vẽ
        if (res.code === 200 && res.j.goal) render(entry.els[entry.els.length - 1], res.j.goal);
        else fail(res.j.error || tw("resonance.unavailable"));
      })
      .catch(function () {
        if (INFLIGHT[key] === entry) delete INFLIGHT[key];
        fail(tw("resonance.unavailable"));
      });
    if (!fresh) INFLIGHT[key] = entry;
    return entry.promise;
  }

  /* Gắn thẻ vào một tin nhắn đã vẽ. Gọi lại với cùng goal_id trên cùng tin thì không gắn thêm. */
  function ve(msgEl, card) {
    if (!msgEl || !card || !card.goal_id) return null;
    var cur = msgEl.querySelector && msgEl.querySelector('.rs-card[data-goal="' + card.goal_id + '"]');
    if (cur) return cur;
    var el = document.createElement("div");
    el.className = "rs-card";
    el.setAttribute("data-goal", card.goal_id);
    el.innerHTML = '<div class="rs-note">' + esc(tw("resonance.loading")) + "</div>";
    var bubble = msgEl.querySelector(".bubble");
    (bubble || msgEl).appendChild(el);
    load(el);
    veReact(msgEl, card);
    return el;
  }

  /* Câu ghi chú sau một lần bấm, từ phản hồi THẬT của server (thuần để test). A4: Cho phép chỉ nói "đã đăng" khi
     server xác nhận `publish` là succeeded hay same; cấp quyền thành công không có nghĩa là file đã được ghi. */
  function noteFor(act, res) {
    var j = (res && res.j) || {};
    if (res.code === 409) return tw("resonance.changed");
    if (res.code !== 200) return j.error || tw("resonance.failed");
    if (j.ok === false && j.reason) return j.reason;
    if (act === "fit_no") return tw("resonance.fit_no_hint");
    if (act === "out_no") return tw("resonance.out_no_hint");
    if (act === "out_ok") return tw("resonance.out_ok_hint");
    if (act === "approve_scope") {
      if (!j.submission_id) return tw("resonance.a4_approved");
      if (j.publish === "succeeded" || j.publish === "same") return tw("resonance.a4_approved_draft");
      if (j.publish === "conflict") return tw("resonance.a4_approved_draft_conflict");
      return tw("resonance.a4_approved_draft_pending");
    }
    if (act === "revoke_grant") return tw("resonance.a4_revoked");
    return "";
  }

  /* A4: xem trước bản nháp đang chờ cho phép (chỉ đọc, đúng bản có mã và sha trên thẻ). */
  function preview(el, g) {
    var d = ((g.scope || {}).draft) || {};
    if (!d.submission_id) return;
    var box = el.querySelector(".rs-preview");
    if (box) { box.remove(); return; }
    fetch("/goals/" + encodeURIComponent(g.goal_id) + "/drafts/" + encodeURIComponent(d.submission_id) + "?brain=" +
          encodeURIComponent(brain()), { credentials: "same-origin" })
      .then(function (r) { return r.json().then(function (j) { return { code: r.status, j: j }; }); })
      .then(function (res) {
        var txt = res.code === 200 ? String(res.j.content || "") : (res.j.error || tw("resonance.failed"));
        el.insertAdjacentHTML("beforeend", '<pre class="rs-preview">' + esc(txt) + "</pre>");
      })
      .catch(function () { el.insertAdjacentHTML("beforeend", '<div class="rs-note">' + esc(tw("resonance.failed")) +
        "</div>"); });
  }

  function send(el, act, critId, dir) {
    var g = el._goal;
    if (!g) return;
    if (act === "cancel" && !window.confirm(tw("resonance.cancel_confirm"))) return;
    if (act === "drop" && !window.confirm(tw("resonance.drop_confirm"))) return;
    if (act === "revoke_grant" && !window.confirm(tw("resonance.revoke_confirm"))) return;
    if (act === "draft_preview") { preview(el, g); return; }
    var req = requestFor(act, g, critId, dir, newNonce());
    var btns = el.querySelectorAll("button.rs-act");
    for (var i = 0; i < btns.length; i++) btns[i].disabled = true;
    fetch(req.url + "?brain=" + encodeURIComponent(brain()), {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(req.body)
    })
      .then(function (r) { return r.json().then(function (j) { return { code: r.status, j: j }; }); })
      .then(function (res) {
        var note = noteFor(act, res);
        if (res.j.goal) render(el, res.j.goal, note);
        else load(el, true).then(function () { if (note) el.insertAdjacentHTML("beforeend", '<div class="rs-note">' + esc(note) + "</div>"); });
      })
      .catch(function () { render(el, g, tw("resonance.failed")); });
  }

  if (typeof document !== "undefined" && document.addEventListener) {
    document.addEventListener("click", function (ev) {
      var b = ev.target && ev.target.closest && ev.target.closest("button.rs-act");
      if (!b) return;
      var el = b.closest(".rs-card");
      if (!el) return;
      ev.preventDefault();
      send(el, b.getAttribute("data-act"), b.getAttribute("data-crit"),
           { field: b.getAttribute("data-field"), key: b.getAttribute("data-key"),
             lesson: b.getAttribute("data-lesson") });
    });
    document.addEventListener("click", function (ev) {
      var b = ev.target && ev.target.closest && ev.target.closest("button.rs-react-b");
      if (!b) return;
      var row = b.closest(".rs-react");
      if (!row) return;
      ev.preventDefault();
      sendReact(row, b.getAttribute("data-ract"), b.getAttribute("data-reason"));
    });
  }

  /* Công tắc theo BRAIN cũ đã bỏ (A1): công tắc nay theo từng trợ lý, ở resonance-agent.js. */

  var api = { tach: tach, viewHtml: viewHtml, compactHtml: compactHtml, requestFor: requestFor, stateKey: stateKey, wakeLabel: wakeLabel,
    ve: ve, render: render, reactHtml: reactHtml, reactBody: reactBody, learnHtml: learnHtml, isNotice: isNotice,
    scopeHtml: scopeHtml, noteFor: noteFor, _send: send };
  if (typeof window !== "undefined") window.JavisResonance = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
