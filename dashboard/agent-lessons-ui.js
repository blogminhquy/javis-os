/* Mục "Bài học và hạn mức" của bảng Nhịp một trợ lý (T3 phần L, 0.156.0; thiết kế 2026-10-15 mục 8, 9, 10).

   Phần P dựng bảng từ GET /agents/{slug}/pulse; mục của phần L nằm ở `view.parts.lessons` (sổ đăng ký phía máy chủ
   `register_view_part("lessons", ...)`). File này góp hàm vẽ vào sổ phía trang `window.JavisPulseParts` ({name, render})
   theo đúng hợp đồng của agent-pulse.js: `render(view)` trả HTML đã escape.

   Nội dung: bài học đang dùng theo phạm vi (chat riêng, từng nhóm, mọi nơi) kèm nguồn, nút Thu hồi và Dùng ở mọi nơi;
   bài học cũ trong MEMORY.md ghi "bài học cũ chưa có phạm vi"; thay đổi của tự rà soát với trước/sau, bằng chứng, trạng
   thái và nút Quay lại; đề xuất cần chủ quyết; hạn mức lượt tự phát hôm nay và ô chọn hạn mức.

   Nút gọi POST /agents/{slug}/lessons/{id}/revoke, /lessons/{id}/promote, /budget (phần L) và /pulse/revert kèm
   change_id (phần P). Chỉ hiện "Đã lưu" và vẽ lại SAU khi máy chủ trả 200; lỗi thì nói lý do, giữ nguyên trạng thái cũ.

   `partHtml`, `scopeLabel`, `changeLine`, `budgetLine` thuần (không DOM, không mạng) để test chạy dưới node. */
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


  // Khoá viết TRỌN để bộ kiểm i18n đọc được từng khoá.
  var SOURCE_KEY = { owner: "lessons.source.owner", teammate: "lessons.source.teammate", leader: "lessons.source.leader",
    self: "lessons.source.self", review: "lessons.source.review" };
  var KIND_KEY = { speak: "lessons.kind.speak", method: "lessons.kind.method", presentation: "lessons.kind.presentation",
    collab: "lessons.kind.collab" };
  var CHANGE_KEY = { offset_set: "lessons.change.offset_set", eagerness_set: "lessons.change.eagerness_set",
    lesson_add: "lessons.change.lesson_add", lesson_remove: "lessons.change.lesson_remove",
    lesson_promote: "lessons.change.lesson_promote" };
  var STATUS_KEY = { applied: "lessons.status.applied", kept: "lessons.status.kept", reverted: "lessons.status.reverted",
    rejected: "lessons.status.rejected", interrupted: "lessons.status.interrupted" };
  var REVERT_KEY = { judge_error_up: "lessons.revert.judge_error_up", estimate_down: "lessons.revert.estimate_down",
    owner: "lessons.revert.owner", owner_held: "lessons.revert.owner_held", policy_revert: "lessons.revert.policy_revert" };
  var AREA_KEY = { permissions: "lessons.area.permissions", owner_rule: "lessons.area.owner_rule", code: "lessons.area.code",
    skill: "lessons.area.skill", workflow: "lessons.area.workflow", structure: "lessons.area.structure",
    other: "lessons.area.other" };
  var REJECT_KEY = { evidence: "lessons.reject.evidence", owner_held: "lessons.reject.owner_held",
    reverted_recently: "lessons.reject.reverted_recently", contexts: "lessons.reject.contexts",
    context: "lessons.reject.context", value: "lessons.reject.value", no_change: "lessons.reject.no_change",
    lesson: "lessons.reject.lesson", over_limit: "lessons.reject.over_limit" };
  var EAGER_KEY = { low: "lessons.eager.low", medium: "lessons.eager.medium", high: "lessons.eager.high" };
  var CAP_CHOICES = [0, 2, 4, 6, 10, 20];

  function pick(map, v, dflt) { return Object.prototype.hasOwnProperty.call(map, v) ? map[v] : dflt; }

  function scopeLabel(scope, teamNames) {
    var s = String(scope || "");
    if (s === "*") return tw("lessons.scope.all");
    if (s.indexOf("dm:") === 0) return tw("lessons.scope.dm");
    if (s.indexOf("team:") === 0 && teamNames && teamNames[s.slice(5)]) {
      return tw("lessons.scope.team", { name: teamNames[s.slice(5)] });
    }
    if (s.indexOf("team:") === 0) {
      var JP = (typeof window !== "undefined" && window.JavisPulse) || null;
      return JP && JP.contextLabel ? JP.contextLabel(s) : tw("lessons.scope.team", { name: s.slice(5) });
    }
    return s;
  }

  function settingText(kind, obj) {
    var o = obj || {};
    if (kind === "offset_set") return o.offset == null ? "" : (Number(o.offset) >= 0 ? "+" : "") + Number(o.offset).toFixed(2);
    if (kind === "eagerness_set") return o.eagerness ? tw(pick(EAGER_KEY, o.eagerness, "lessons.eager.medium")) : "";
    if (o.text) return o.text;
    if (o.scope) return scopeLabel(o.scope);
    return "";
  }

  /* Một thay đổi của tự rà soát: loại, ngữ cảnh, trước -> sau, trạng thái (kèm lý do quay lại hay từ chối). */
  function changeLine(ch) {
    var c = ch || {};
    var parts = [tw(pick(CHANGE_KEY, c.kind, "lessons.change.lesson_add")), scopeLabel(c.context_ref)];
    var b = settingText(c.kind, c.before), a = settingText(c.kind, c.after);
    if (b || a) parts.push(tw("lessons.before_after", { before: b || tw("lessons.none"), after: a || tw("lessons.none") }));
    var st = tw(pick(STATUS_KEY, c.status, "lessons.status.applied"));
    if (c.status === "reverted" && c.revert_reason) {
      st += " (" + (pick(REVERT_KEY, c.revert_reason, "") ? tw(REVERT_KEY[c.revert_reason]) : c.revert_reason) + ")";
    } else if (c.status === "rejected" && c.reject_reason) {
      st += " (" + (pick(REJECT_KEY, c.reject_reason, "") ? tw(REJECT_KEY[c.reject_reason]) : c.reject_reason) + ")";
    }
    parts.push(st);
    var ev = (c.evidence || []).length;
    if (ev) parts.push(tw("lessons.evidence", { n: ev }));
    return parts.join(" · ");
  }

  function budgetLine(b) {
    var x = b || {};
    if (x.cap == null) return tw("lessons.budget_unlimited", { used: x.used || 0 });
    return tw("lessons.budget_line", { used: x.used || 0, cap: x.cap, reserved: x.reserved == null ? 2 : x.reserved });
  }

  function lessonItem(l) {
    var refs = (l.source_refs || []).slice(0, 2).join(", ");
    var meta = tw("lessons.meta", { source: tw(pick(SOURCE_KEY, l.source, "lessons.source.self")),
      kind: tw(pick(KIND_KEY, l.kind, "lessons.kind.method")) }) + (refs ? " · " + refs : "");
    var acts = '<button type="button" class="ws-btn lessons-act" data-lessons-act="revoke" data-id="' + esc(l.id) + '">' +
      esc(tw("lessons.btn.revoke")) + "</button>";
    if (l.scope !== "*") {
      acts += '<button type="button" class="ws-btn lessons-act" data-lessons-act="promote" data-id="' + esc(l.id) + '">' +
        esc(tw("lessons.btn.promote")) + "</button>";
    }
    return '<li class="lessons-item"><div class="lessons-text">' + esc(l.text) + '</div><div class="lessons-meta">' +
      esc(meta) + '</div><div class="lessons-acts">' + acts + "</div></li>";
  }

  /* Cả mục. `view`: kết quả GET /agents/{slug}/pulse (dùng `view.parts.lessons`). `o`: {msg, err, busy}. */
  function partHtml(view, opts) {
    var o = opts || {}, v = view || {};
    var p = (v.parts && v.parts.lessons) || null;
    if (!p || p.error) {
      return p && p.error ? '<div class="pulse-sub">' + esc(tw("lessons.title")) + '</div><div class="pulse-line pulse-err">' +
        esc(tw("lessons.error_load")) + "</div>" : "";
    }
    var dis = o.busy ? " disabled" : "";
    var html = '<div class="lessons-part" data-slug="' + esc(p.slug || "") + '" data-agent="' + esc(p.agent_key || "") +
      '"><div class="pulse-sub">' + esc(tw("lessons.title")) + infoBtn() + "</div>" +
      infoBody('<div class="pulse-line pulse-note">' + esc(tw("lessons.budget_note")) + "</div>");
    var b = p.budget || {};
    var cur = b.cap == null ? "unlimited" : String(b.cap);
    var choices = CAP_CHOICES.slice();
    if (b.cap != null && choices.indexOf(Number(b.cap)) < 0) choices.push(Number(b.cap));
    choices.sort(function (x, y) { return x - y; });
    html += '<div class="pulse-line">' + esc(budgetLine(b)) + "</div>" +
      '<label class="lessons-budget"><span>' + esc(tw("lessons.budget_label")) + '</span><select class="lessons-budget-sel" data-prev="' + esc(cur) + '"' +
      dis + ">" + choices.map(function (n) {
        return '<option value="' + n + '"' + (String(n) === cur ? " selected" : "") + ">" + esc(String(n)) + "</option>";
      }).join("") + '<option value="unlimited"' + (cur === "unlimited" ? " selected" : "") + ">" +
      esc(tw("lessons.unlimited")) + "</option></select></label>";
    var scopes = p.scopes || [];
    // Hàng thành viên của MỘT nhóm: chỉ bài học của nhóm đó và bài học dùng mọi nơi (không hiện chat riêng ở đây).
    if (o.only) scopes = scopes.filter(function (x) { return x.scope === o.only || x.scope === "*"; });
    if (!scopes.length) {
      html += '<div class="pulse-line">' + esc(tw("lessons.empty")) + "</div>";
    }
    scopes.forEach(function (s) {
      html += '<div class="lessons-scope"><div class="lessons-scope-name">' + esc(scopeLabel(s.scope, o.teamNames)) + "</div>" +
        '<ul class="pulse-list lessons-list">' + (s.lessons || []).map(lessonItem).join("") + "</ul></div>";
    });
    if ((p.legacy || []).length) {
      html += '<div class="lessons-scope"><div class="lessons-scope-name">' + esc(tw("lessons.legacy")) + "</div>" +
        '<div class="pulse-line pulse-note">' + esc(tw("lessons.legacy_note")) + '</div><ul class="pulse-list">' +
        p.legacy.slice(0, 15).map(function (t) { return "<li>" + esc(t) + "</li>"; }).join("") + "</ul></div>";
    }
    var changes = p.changes || [];
    if (changes.length) {
      html += '<div class="pulse-sub">' + esc(tw("lessons.changes_title")) + '</div><ul class="pulse-list">' +
        changes.slice(0, 10).map(function (c) {
          var why = c.why ? '<div class="lessons-meta">' + esc(c.why) + "</div>" : "";
          var btn = c.can_revert ? ' <button type="button" class="ws-btn lessons-act" data-lessons-act="revert" ' +
            'data-change="' + esc(c.policy_change_id) + '"' + dis + ">" + esc(tw("lessons.btn.revert")) + "</button>" : "";
          return "<li>" + esc(changeLine(c)) + btn + why + "</li>";
        }).join("") + "</ul>";
    }
    var props = p.proposals || [];
    if (props.length) {
      html += '<div class="pulse-sub">' + esc(tw("lessons.proposals_title")) + '</div><ul class="pulse-list">' +
        props.map(function (x) {
          return "<li>" + esc(tw(pick(AREA_KEY, x.area, "lessons.area.other"))) + ": " + esc(x.text) + "</li>";
        }).join("") + "</ul>";
    }
    if (o.err) html += '<div class="pulse-line pulse-err" role="alert">' + esc(tw("lessons.error", { e: o.err })) + "</div>";
    else if (o.msg) html += '<div class="pulse-line pulse-ok" role="status">' + esc(o.msg) + "</div>";
    return html + "</div>";
  }

  function brainName() {
    try { return (window.JavisSessions && window.JavisSessions.brain()) || "brain"; } catch (e) { return "brain"; }
  }

  /* {code, j}: thành công chỉ khi máy chủ trả 200 và ok = true. */
  function post(url, body) {
    return fetch(url, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}) }).then(function (r) {
      return r.json().then(function (j) { return { code: r.status, j: j }; }, function () { return { code: r.status, j: {} }; });
    });
  }

  /* URL và thân cho một hành động. Thuần để test. */
  function actionRequest(slug, brain, act, el) {
    var base = "/agents/" + encodeURIComponent(slug);
    var q = "?brain=" + encodeURIComponent(brain || "brain");
    if (act === "revoke") return { url: base + "/lessons/" + encodeURIComponent(el.id) + "/revoke" + q, body: {} };
    if (act === "promote") return { url: base + "/lessons/" + encodeURIComponent(el.id) + "/promote" + q, body: {} };
    if (act === "revert") return { url: base + "/pulse/revert" + q, body: { change_id: Number(el.change) } };
    if (act === "budget") {
      return { url: base + "/budget" + q, body: { daily_calls: el.value === "unlimited" ? "unlimited" : Number(el.value) } };
    }
    return null;
  }

  function redraw(box, view, o) {
    var part = box.closest ? box.closest(".pulse-part") : null;
    (part || box.parentNode || box).innerHTML = partHtml(view, o);
  }

  function run(box, act, el) {
    var slug = box.getAttribute("data-slug");
    var req = slug ? actionRequest(slug, brainName(), act, el) : null;
    if (!req) return;
    var keep = { parts: { lessons: null } };
    post(req.url, req.body).then(function (res) {
      if (res.code !== 200 || !res.j || res.j.ok !== true) throw res.j;
      // Route của phần L trả mục "lessons" mới; route quay lại của phần P trả cả khung nhịp.
      var lv = res.j.view && res.j.view.name === "lessons" ? res.j.view : (res.j.view && res.j.view.parts || {}).lessons;
      keep.parts.lessons = lv || null;
      if (keep.parts.lessons) redraw(box, keep, { msg: tw("lessons.done") });
    }).catch(function (e) {
      Array.prototype.forEach.call(box.querySelectorAll("[data-lessons-act]"), function (x) { x.disabled = false; });
      // Hạn mức bị từ chối: ô chọn về lại giá trị đang lưu (review T3 L P3), không giữ giá trị máy chủ chưa nhận.
      if (el && el.sel && el.prev != null) el.sel.value = el.prev;
      var err = (e && e.error) || tw("lessons.error_generic");
      var note = box.querySelector(".lessons-note");
      if (!note) {
        note = document.createElement("div");
        note.className = "pulse-line pulse-err lessons-note";
        note.setAttribute("role", "alert");
        box.appendChild(note);
      }
      note.textContent = tw("lessons.error", { e: err });
    });
  }

  if (typeof document !== "undefined" && document.addEventListener) {
    document.addEventListener("click", function (ev) {
      var b = ev.target && ev.target.closest ? ev.target.closest("[data-lessons-act]") : null;
      if (!b || b.disabled) return;
      var box = b.closest(".lessons-part");
      if (!box) return;
      b.disabled = true;
      run(box, b.getAttribute("data-lessons-act"), { id: b.getAttribute("data-id"), change: b.getAttribute("data-change") });
    });
    document.addEventListener("change", function (ev) {
      var s = ev.target;
      if (!s || !s.classList || !s.classList.contains("lessons-budget-sel")) return;
      var box = s.closest(".lessons-part");
      if (box) run(box, "budget", { value: s.value, prev: s.getAttribute("data-prev"), sel: s });
    });
  }

  var part = { name: "lessons", render: function (view, _el, ctx) {
    return partHtml(view, { only: (ctx && ctx.only) || "", teamNames: (ctx && ctx.teamNames) || {} });
  } };
  if (typeof window !== "undefined") {
    window.JavisPulseParts = window.JavisPulseParts || [];
    if (!window.JavisPulseParts.some(function (x) { return x && x.name === "lessons"; })) window.JavisPulseParts.push(part);
  }
  var apiOut = { partHtml: partHtml, scopeLabel: scopeLabel, changeLine: changeLine, budgetLine: budgetLine,
    actionRequest: actionRequest, part: part };
  if (typeof module !== "undefined" && module.exports) module.exports = apiOut;
})();
