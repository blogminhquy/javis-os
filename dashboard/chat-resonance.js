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
                 "stalled", "source_drift", "handoff"];
    if (known.indexOf(r) >= 0) return "resonance.st_" + r;
    if (g.run_state === "running") return "resonance.st_running";
    if (g.run_state === "blocked") return "resonance.st_blocked";
    return "resonance.st_working";
  }

  /* Nhãn dịch được cho mã lý do thức (A2). Mã lạ hiện như lần xem lại định kỳ, không lộ mã thô. */
  var WAKE_CODES = ["created", "revised", "assigned", "feedback", "user_schedule", "retry_not_met", "error_retry",
                    "recovery", "handoff_wait", "handoff_done", "resumed", "agent_enabled", "agent_recheck",
                    "agent_changed", "guard_recheck", "review", "deadline", "drift_recheck", "guard_observe"];

  function wakeLabel(code) {
    return tw("resonance.wake." + (WAKE_CODES.indexOf(code) >= 0 ? code : "review"));
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
    if (act === "drop") {
      return { url: "/goals/" + id + "/commands", body: { command: "drop_directive", expected_revision: rev,
        field: String((dir || {}).field || ""), key: String((dir || {}).key || "") } };
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

  function load(el) {
    var id = el.getAttribute("data-goal");
    return fetch("/goals/" + encodeURIComponent(id) + "?brain=" + encodeURIComponent(brain()),
                 { credentials: "same-origin" })
      .then(function (r) { return r.json().then(function (j) { return { code: r.status, j: j }; }); })
      .then(function (res) {
        if (res.code === 200 && res.j.goal) render(el, res.j.goal);
        else el.innerHTML = '<div class="rs-note">' + esc(res.j.error || tw("resonance.unavailable")) + "</div>";
      })
      .catch(function () { el.innerHTML = '<div class="rs-note">' + esc(tw("resonance.unavailable")) + "</div>"; });
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
    return el;
  }

  function send(el, act, critId, dir) {
    var g = el._goal;
    if (!g) return;
    if (act === "cancel" && !window.confirm(tw("resonance.cancel_confirm"))) return;
    if (act === "drop" && !window.confirm(tw("resonance.drop_confirm"))) return;
    var req = requestFor(act, g, critId, dir, newNonce());
    var btns = el.querySelectorAll("button.rs-act");
    for (var i = 0; i < btns.length; i++) btns[i].disabled = true;
    fetch(req.url + "?brain=" + encodeURIComponent(brain()), {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json" }, body: JSON.stringify(req.body)
    })
      .then(function (r) { return r.json().then(function (j) { return { code: r.status, j: j }; }); })
      .then(function (res) {
        var note = "";
        if (res.code === 409) note = tw("resonance.changed");
        else if (res.code !== 200) note = res.j.error || tw("resonance.failed");
        else if (res.j.ok === false && res.j.reason) note = res.j.reason;
        else if (act === "fit_no") note = tw("resonance.fit_no_hint");
        else if (act === "out_no") note = tw("resonance.out_no_hint");
        else if (act === "out_ok") note = tw("resonance.out_ok_hint");
        if (res.j.goal) render(el, res.j.goal, note);
        else load(el).then(function () { if (note) el.insertAdjacentHTML("beforeend", '<div class="rs-note">' + esc(note) + "</div>"); });
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
           { field: b.getAttribute("data-field"), key: b.getAttribute("data-key") });
    });
  }

  /* Công tắc theo BRAIN cũ đã bỏ (A1): công tắc nay theo từng trợ lý, ở resonance-agent.js. */

  var api = { tach: tach, viewHtml: viewHtml, compactHtml: compactHtml, requestFor: requestFor, stateKey: stateKey, wakeLabel: wakeLabel,
    ve: ve, render: render };
  if (typeof window !== "undefined") window.JavisResonance = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
