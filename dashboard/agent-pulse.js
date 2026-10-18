/* Bảng Nhịp chủ động của một trợ lý (T3, 0.156.0; thiết kế 2026-10-15 mục 10, hợp đồng T3 mục 4).

   Hai chỗ dùng:
   - Trang Cộng sự, cột phải của một trợ lý (workspace.js gọi `mount`): mọi ngữ cảnh (chat riêng, từng nhóm).
   - Dòng thành viên ở ngăn Nhóm (teams.js gọi `mount` với `only: "team:<id>"`): đúng ngữ cảnh của nhóm đó.

   Đọc GET /agents/{slug}/pulse; nút Đánh thức, Tạm dừng/Tiếp, Đặt lại nhịp, Quay lại thay đổi, Nhịp nhanh nhất gọi
   POST /agents/{slug}/pulse/<hành động>. Chỉ hiện "Đã lưu" và vẽ lại SAU khi máy chủ trả 200 (không hiện thành công
   trước). Phần J (phán xử) và L (bài học) góp mục riêng qua sổ đăng ký `window.JavisPulseParts` (mảng {name, render(view)}):
   file này không biết gì về chúng.

   `panelHtml`, `contextLabel`, `changeLine`, `partsHtml` thuần (không DOM, không mạng) để test chạy dưới node. */
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


  // Khoá viết TRỌN (không ghép chuỗi) để bộ kiểm i18n đọc được từng khoá đang dùng.
  var TIER_KEY = ["pulse.tier_0", "pulse.tier_1", "pulse.tier_2", "pulse.tier_3", "pulse.tier_4", "pulse.tier_5",
    "pulse.tier_6", "pulse.tier_7", "pulse.tier_8"];
  var STATE_KEY = { active: "pulse.state.active", awake: "pulse.state.awake", slowed: "pulse.state.slowed",
    hibernating: "pulse.state.hibernating", waiting_owner: "pulse.state.waiting_owner", paused: "pulse.state.paused",
    off: "pulse.state.off" };
  // Đổi chính sách (cửa sổ quan sát 6.4): tên loại dùng chung với mục Bài học, trạng thái riêng của bảng Nhịp.
  var POLICY_KIND = { offset_set: "lessons.change.offset_set", eagerness_set: "lessons.change.eagerness_set",
    lesson_add: "lessons.change.lesson_add", lesson_remove: "lessons.change.lesson_remove",
    lesson_promote: "lessons.change.lesson_promote" };
  var POLICY_STATUS = { observing: "pulse.policy.status.observing", kept: "pulse.policy.status.kept",
    reverted: "pulse.policy.status.reverted" };
  var WHY_KEY = { direct_call: "pulse.why.direct_call", owner_message: "pulse.why.owner_message",
    owner_reply: "pulse.why.owner_reply", new_job: "pulse.why.new_job", reaction: "pulse.why.reaction",
    manual: "pulse.why.manual", related_event: "pulse.why.related_event" };
  var REASON_KEY = { helpful: "pulse.reason.helpful", unhelpful: "pulse.reason.unhelpful",
    low_demand: "pulse.reason.low_demand", wake: "pulse.reason.wake", max_tier: "pulse.reason.max_tier" };
  var EV_KEY = { tier_change: "pulse.ev.tier_change", revert: "pulse.ev.revert", reset: "pulse.ev.reset",
    max_tier: "pulse.ev.max_tier", on: "pulse.ev.on", off: "pulse.ev.off", paused: "pulse.ev.paused",
    resume: "pulse.ev.resume", policy_change: "pulse.ev.policy_change", policy_revert: "pulse.ev.policy_revert" };
  var FB_KIND_KEY = { reaction: "pulse.fb.kind.reaction", reaction_reason: "pulse.fb.kind.reaction_reason",
    host_event: "pulse.fb.kind.host_event", seen_ignored: "pulse.fb.kind.seen_ignored" };
  var FB_STATUS_KEY = { live: "pulse.fb.status.live", superseded: "pulse.fb.status.superseded",
    void: "pulse.fb.status.void" };

  var PROP_STATUS_KEY = { pending: "pulse.prop.status.pending", accepted: "pulse.prop.status.accepted",
    rejected: "pulse.prop.status.rejected" };

  /* Đề xuất của lượt quét: chờ thì có Nhận thành việc / Bác; đã quyết thì chỉ trạng thái. */
  function proposalsHtml(list, o) {
    var items = (list || []).filter(function (p) { return !o.only || p.context_ref === o.only; });
    if (!items.length) return "";
    return '<div class="pulse-sub">' + esc(tw("pulse.proposals_title")) + '</div><ul class="pulse-list">' +
      items.slice(0, 8).map(function (p) {
        var busy = o.busy && o.busy["pp" + p.id] ? " disabled" : "";
        var acts = p.status === "pending" ? '<div class="pulse-acts">' +
          '<button type="button" class="ws-btn pulse-act" data-pulse-act="proposal_accept" data-pid="' + esc(p.id) + '"' +
            busy + ">" + esc(tw("pulse.btn.accept")) + "</button>" +
          '<button type="button" class="ws-btn pulse-act" data-pulse-act="proposal_reject" data-pid="' + esc(p.id) + '"' +
            busy + ">" + esc(tw("pulse.btn.reject")) + "</button></div>" : "";
        return "<li><strong>" + esc(p.title) + "</strong>" + (p.brief ? " · " + esc(p.brief) : "") + " · " +
          esc(contextLabel(p.context_ref, o.teamNames)) + " · " +
          esc(tw(pick(PROP_STATUS_KEY, p.status, "pulse.prop.status.pending"))) + acts + "</li>";
      }).join("") + "</ul>";
  }

  function pick(map, v, dflt) { return Object.prototype.hasOwnProperty.call(map, v) ? map[v] : dflt; }

  function tierLabel(tier) {
    var n = Number(tier);
    return n >= 0 && n <= 8 ? tw(TIER_KEY[n]) : "";
  }

  function stateLabel(st) { return tw(pick(STATE_KEY, st, "pulse.state.awake")); }

  function contextLabel(ctx, teamNames) {
    var c = String(ctx || "");
    if (c === "*") return tw("pulse.ctx_all");
    if (c.indexOf("dm:") === 0) return tw("pulse.ctx_dm");
    if (c.indexOf("team:") === 0) {
      var id = c.slice(5), names = teamNames || {};
      return tw("pulse.ctx_team", { name: names[id] || id });
    }
    return c;
  }

  function when(ts) {
    if (ts == null) return tw("pulse.never");
    try { return new Date(Number(ts) * 1000).toLocaleString(); } catch (e) { return String(ts); }
  }

  function num(v, d) { return (Math.round(Number(v || 0) * Math.pow(10, d)) / Math.pow(10, d)).toFixed(d); }

  /* Một lần đổi nhịp: trước/sau, lý do, nguồn. */
  function changeLine(ev) {
    var e = ev || {};
    var parts = [];
    if (e.kind === "tier_change" || e.kind === "revert" || e.kind === "reset") {
      var b = (e.before || {}).tier, a = (e.after || {}).tier;
      if (b != null && a != null) parts.push(tw("pulse.change_line", { before: tierLabel(b), after: tierLabel(a) }));
    }
    parts.unshift(tw(pick(EV_KEY, e.kind, "pulse.ev.tier_change")));
    if (e.reason && pick(REASON_KEY, e.reason, "")) parts.push(tw(REASON_KEY[e.reason]));
    if (e.source) parts.push(tw("pulse.source", { s: pick(WHY_KEY, e.source, "") ? tw(WHY_KEY[e.source]) :
      (e.source === "owner" ? tw("pulse.by_owner") : e.source === "schedule" ? tw("pulse.by_schedule") :
        e.source === "auto" ? tw("pulse.by_auto") : e.source) }));
    return parts.join(" · ");
  }

  function emojiOf(v) {
    var JR = (typeof window !== "undefined" && window.JavisReactions) || null;
    if (!JR) { try { JR = require("./reactions.js"); } catch (e) { JR = null; } }
    var r = JR && JR.emojiOf ? JR.emojiOf(v) : null;
    return r ? (r.emoji || "") : "";
  }

  function feedbackLine(f) {
    var x = f || {};
    var kind = tw(pick(FB_KIND_KEY, x.kind, "pulse.fb.kind.host_event"));
    var status = tw(pick(FB_STATUS_KEY, x.status, "pulse.fb.status.live"));
    var mark = x.kind === "reaction" || x.kind === "reaction_reason" ? emojiOf(x.emoji) : "";
    var share = Number(x.share) < 0.999 ? " " + tw("pulse.fb.share", { p: Math.round(Number(x.share) * 100) }) : "";
    return (mark ? mark + " " : "") + kind + share + " · " + contextLabel(x.context_ref) + " · " + status;
  }

  function ctxRowHtml(c, o) {
    var ctx = c.context_ref, paused = c.state === "paused", off = c.state === "off";
    var lines = [
      tw("pulse.state_tier", { s: stateLabel(c.state), t: c.state === "hibernating" ? tierLabel(8) : tierLabel(c.tier) }),
      tw("pulse.last_review", { t: when(c.last_eval_at) }),
      tw("pulse.next_review", { t: c.next_due_at == null ? tw("pulse.none_scheduled") : when(c.next_due_at) })
    ];
    if (c.last_wake_why) {
      lines.push(tw("pulse.wake_reason", { r: pick(WHY_KEY, c.last_wake_why, "") ? tw(WHY_KEY[c.last_wake_why])
        : c.last_wake_why }));
    }
    lines.push(tw("pulse.usefulness", { u: num(c.u, 2), c: num(c.confidence, 2) }));
    var busy = o.busy && o.busy[ctx];
    var dis = busy || off ? " disabled" : "";
    var acts = '<div class="pulse-acts">' +
      '<button type="button" class="ws-btn pulse-act" data-pulse-act="wake" data-ctx="' + esc(ctx) + '"' +
        (paused ? " disabled" : dis) + ">" + esc(tw("pulse.btn.wake")) + "</button>" +
      '<button type="button" class="ws-btn pulse-act" data-pulse-act="' + (paused ? "resume" : "pause") + '" data-ctx="' +
        esc(ctx) + '"' + dis + ">" + esc(tw(paused ? "pulse.btn.resume" : "pulse.btn.pause")) + "</button>" +
      '<button type="button" class="ws-btn pulse-act" data-pulse-act="reset" data-ctx="' + esc(ctx) + '"' + dis + ">" +
        esc(tw("pulse.btn.reset")) + "</button></div>";
    return '<div class="pulse-ctx" data-ctx="' + esc(ctx) + '"><div class="pulse-ctx-head"><span class="pulse-ctx-name">' +
      esc(contextLabel(ctx, o.teamNames)) + "</span>" + (c.quota_wait ? '<span class="pulse-badge">' +
      esc(tw("pulse.quota")) + "</span>" : "") + "</div>" +
      lines.map(function (l) { return '<div class="pulse-line">' + esc(l) + "</div>"; }).join("") + acts + "</div>";
  }

  /* Đổi chính sách đang quan sát (6.4): chủ quay lại được bằng nút (review T3 P P3). */
  function policyHtml(list, o) {
    var pcs = (list || []).filter(function (p) { return !o.only || p.context_ref === o.only || p.context_ref === "*"; });
    if (!pcs.length) return "";
    return '<div class="pulse-sub">' + esc(tw("pulse.policy_title")) + '</div><ul class="pulse-list">' +
      pcs.slice(0, 8).map(function (p) {
        var can = p.status === "observing", key = "pc" + p.id;
        return "<li>" + esc(tw(POLICY_KIND[p.kind] || "pulse.policy.kind_other")) + " · " +
          esc(contextLabel(p.context_ref, o.teamNames)) + " · " + esc(tw(POLICY_STATUS[p.status] || "pulse.policy.status.observing")) +
          (can ? ' <button type="button" class="ws-btn pulse-act" data-pulse-act="revert_policy" data-change="' + esc(p.id) +
            '"' + (o.busy && o.busy[key] ? " disabled" : "") + ">" + esc(tw("pulse.btn.revert")) + "</button>" : "") + "</li>";
      }).join("") + "</ul>";
  }

  /* Mục của phần J/L (sổ đăng ký). Mỗi mục tự escape; lỗi của một mục không làm hỏng bảng. */
  function partsHtml(view, registry, ctx) {
    var list = registry || (typeof window !== "undefined" ? window.JavisPulseParts : null) || [];
    return list.map(function (p) {
      try {
        // `render(view, null, {slug})`: mục nào cần slug (nút sửa của phán xử, nút thu hồi bài học) lấy từ ngữ cảnh.
        var h = p && typeof p.render === "function" ? p.render(view || {}, null, ctx || {}) : "";
        return h ? '<div class="pulse-part" data-part="' + esc(p.name || "") + '">' + h + "</div>" : "";
      } catch (e) { return ""; }
    }).join("");
  }

  function noteLines(xs) {
    return xs.filter(Boolean).map(function (x) { return '<div class="pulse-line pulse-note">' + esc(x) + "</div>"; }).join("");
  }

  /* Cả bảng. `view`: kết quả GET /agents/{slug}/pulse. `o`: {only, teamNames, busy, msg, err, registry}. */
  function panelHtml(view, opts) {
    var o = opts || {}, v = view || {};
    var html = '<div class="pulse-head"><span class="pulse-title">' + esc(tw("pulse.title")) + infoBtn() + "</span></div>";
    // 0.175.0 (chủ repo 16/10/2026: tab Cài đặt "nhiều thông tin quá"): mọi câu giải thích nằm sau nút i cạnh tiêu đề.
    // Ngoài mặt chỉ còn các dòng nhịp và ô chọn.
    var hi = html.length;
    var ctxs = (v.contexts || []).filter(function (c) { return !o.only || c.context_ref === o.only; });
    if (!v.agent_key || !ctxs.length) {
      // Auto đang bật mà chưa có dòng nhịp (chưa tới lần thức đầu): nói đúng như vậy, không khuyên "bật Auto".
      html += '<div class="pulse-line">' + esc(tw(v.resonance ? "pulse.empty_waiting" : "pulse.empty")) + "</div>";
    } else {
      html += ctxs.map(function (c) { return ctxRowHtml(c, o); }).join("");
    }
    if (!o.only && v.agent_key) {
      var mt = v.aggregate ? Number(v.aggregate.max_tier) : 1;
      html += '<label class="pulse-max"><span>' + esc(tw("pulse.max_tier")) + '</span><select class="pulse-max-sel">' +
        [0, 1, 2, 3, 4, 5, 6, 7].map(function (n) {
          return '<option value="' + n + '"' + (n === mt ? " selected" : "") + ">" + esc(tierLabel(n)) + "</option>";
        }).join("") + "</select></label>";
    }
    // The (i) block goes right after the title; empty lines are dropped.
    html = html.slice(0, hi) + infoBody(noteLines([
      tw(v.resonance ? "pulse.resonance_on" : "pulse.resonance_off"),
      o.only ? "" : tw("pulse.intro"),
      !o.only && v.agent_key ? tw("pulse.max_tier_note") : ""
    ])) + html.slice(hi);
    var changes = (v.changes || []).filter(function (e) { return !o.only || e.context_ref === o.only || e.context_ref === "*"; });
    if (changes.length) {
      html += '<div class="pulse-sub">' + esc(tw("pulse.changes_title")) + '</div><ul class="pulse-list">' +
        changes.slice(0, 8).map(function (e) {
          var can = e.kind === "tier_change" && !e.reverted_by;
          return "<li>" + esc(changeLine(e)) + " · " + esc(contextLabel(e.context_ref, o.teamNames)) +
            (can ? ' <button type="button" class="ws-btn pulse-act" data-pulse-act="revert" data-ev="' + esc(e.id) +
              '">' + esc(tw("pulse.btn.revert")) + "</button>" : "") + "</li>";
        }).join("") + "</ul>";
    }
    html += policyHtml(v.policy_changes, o);
    var fb = (v.feedback || []).filter(function (f) { return !o.only || f.context_ref === o.only; });
    if (fb.length) {
      html += '<div class="pulse-sub">' + esc(tw("pulse.feedback_title")) + '</div><ul class="pulse-list">' +
        fb.slice(0, 8).map(function (f) { return "<li>" + esc(feedbackLine(f)) + "</li>"; }).join("") + "</ul>";
    }
    html += proposalsHtml(v.proposals, o);
    // Hàng thành viên của MỘT nhóm (`only`): các mục chỉ vẽ phần của ngữ cảnh đó; tên nhóm thay cho mã.
    html += partsHtml(v, o.registry, { slug: o.slug || v.slug || "", only: o.only || "", teamNames: o.teamNames || {} });
    if (o.err) html += '<div class="pulse-line pulse-err" role="alert">' + esc(tw("pulse.error", { e: o.err })) + "</div>";
    else if (o.msg) html += '<div class="pulse-line pulse-ok" role="status">' + esc(o.msg) + "</div>";
    return html;
  }

  /* 0.190.0 (chủ repo 16/10/2026: "tối giản nhất"): bản GỌN cho cột Cài đặt của một trợ lý. Không nhịp, không ngưỡng,
     không lịch sử thay đổi: chỉ dòng hạn mức bằng lời thường (mục nào trong sổ đăng ký có `compact(view)`) và đề xuất
     đang chờ chủ quyết, nếu có. Bảng đầy đủ vẫn ở hàng thành viên của ngăn Nhóm. */
  function compactHtml(view, opts) {
    var o = opts || {}, v = view || {};
    var list = o.registry || (typeof window !== "undefined" ? window.JavisPulseParts : null) || [];
    var html = list.map(function (p) {
      try { return p && typeof p.compact === "function" ? p.compact(v) : ""; } catch (e) { return ""; }
    }).join("");
    html += proposalsHtml((v.proposals || []).filter(function (p) { return p.status === "pending"; }), o);
    if (o.err) html += '<div class="pulse-line pulse-err" role="alert">' + esc(tw("pulse.error", { e: o.err })) + "</div>";
    else if (o.msg) html += '<div class="pulse-line pulse-ok" role="status">' + esc(o.msg) + "</div>";
    return html;
  }

  /* {code, j}: thành công chỉ khi máy chủ trả 200 và ok = true. */
  function call(url, body) {
    var init = { credentials: "same-origin" };
    if (body !== undefined) {
      init.method = "POST";
      init.headers = { "Content-Type": "application/json" };
      init.body = JSON.stringify(body || {});
    }
    return fetch(url, init).then(function (r) {
      return r.json().then(function (j) { return { code: r.status, j: j }; }, function () { return { code: r.status, j: {} }; });
    });
  }

  function brainOf(o) {
    if (o && o.brain) return o.brain;
    try { return (window.JavisSessions && window.JavisSessions.brain()) || "brain"; } catch (e) { return "brain"; }
  }

  /* Gắn bảng vào `host`. Trả {reload}. Mọi hành động chỉ báo thành công sau khi máy chủ trả 200. */
  function mount(host, opts) {
    if (!host || !opts || !opts.slug) return null;
    var o = Object.assign({ busy: {} }, opts), view = null;
    var base = "/agents/" + encodeURIComponent(o.slug) + "/pulse";
    function draw() { host.classList.add("pulse-panel"); host.innerHTML = o.compact ? compactHtml(view, o) : panelHtml(view, o); }
    function load() {
      return call(base + "?brain=" + encodeURIComponent(brainOf(o))).then(function (res) {
        if (res.code !== 200 || !res.j || res.j.ok !== true) throw res.j;
        view = res.j; o.err = ""; draw();
      }).catch(function (e) { o.err = (e && e.error) || tw("pulse.error_generic"); draw(); });
    }
    function act(name, body, key) {
      o.busy[key] = true; o.msg = ""; o.err = ""; draw();
      return call(base + "/" + name + "?brain=" + encodeURIComponent(brainOf(o)), body || {}).then(function (res) {
        if (res.code !== 200 || !res.j || res.j.ok !== true) throw res.j;
        view = res.j.view || view; o.msg = tw("pulse.done");
      }).catch(function (e) {
        o.err = (e && e.error) || tw("pulse.error_generic");
      }).then(function () { o.busy[key] = false; draw(); });
    }
    host.addEventListener("click", function (ev) {
      var b = ev.target && ev.target.closest ? ev.target.closest("[data-pulse-act]") : null;
      if (!b || b.disabled || !host.contains(b)) return;
      var name = b.getAttribute("data-pulse-act");
      if (name === "revert") return act("revert", { event_id: Number(b.getAttribute("data-ev")) }, "ev" + b.getAttribute("data-ev"));
      if (name === "revert_policy") {
        return act("revert", { change_id: Number(b.getAttribute("data-change")) }, "pc" + b.getAttribute("data-change"));
      }
      if (name === "proposal_accept" || name === "proposal_reject") {
        var pid = b.getAttribute("data-pid");
        return act("proposals/" + encodeURIComponent(pid) + (name === "proposal_accept" ? "/accept" : "/reject"), {}, "pp" + pid);
      }
      var ctx = b.getAttribute("data-ctx");
      act(name, { context_ref: ctx }, ctx);
    });
    host.addEventListener("change", function (ev) {
      if (ev.target && ev.target.classList && ev.target.classList.contains("pulse-max-sel")) {
        act("max_tier", { tier: Number(ev.target.value) }, "max");
      }
    });
    if (!o.teamNames) {
      // Tên nhóm cho nhãn ngữ cảnh (chỉ đọc). Lỗi thì nhãn dùng mã nhóm.
      o.teamNames = {};
      call("/teams?brain=" + encodeURIComponent(brainOf(o))).then(function (res) {
        ((res.j && res.j.teams) || []).forEach(function (t) { o.teamNames[t.team_id] = t.name || ""; });
        if (view) draw();
      }).catch(function () {});
    }
    load();
    return { reload: load };
  }

  if (typeof window !== "undefined" && !window.JavisPulseParts) window.JavisPulseParts = [];
  var apiOut = { panelHtml: panelHtml, contextLabel: contextLabel, changeLine: changeLine, feedbackLine: feedbackLine,
    partsHtml: partsHtml, compactHtml: compactHtml, proposalsHtml: proposalsHtml, policyHtml: policyHtml, tierLabel: tierLabel, stateLabel: stateLabel, mount: mount };
  if (typeof window !== "undefined") window.JavisPulse = apiOut;
  if (typeof module !== "undefined" && module.exports) module.exports = apiOut;
})();
