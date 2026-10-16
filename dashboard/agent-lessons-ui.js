/* Mục "Hạn mức tự chạy" của bảng Nhịp một trợ lý (T3 phần L, 0.156.0; rút gọn 0.190.0).

   Phần P dựng bảng từ GET /agents/{slug}/pulse; mục của phần L nằm ở `view.parts.lessons` (sổ đăng ký phía máy chủ
   `register_view_part("lessons", ...)`). File này góp hàm vẽ vào sổ phía trang `window.JavisPulseParts` ({name, render})
   theo đúng hợp đồng của agent-pulse.js: `render(view)` trả HTML đã escape.

   0.190.0 (chủ repo 16/10/2026: "bài học cũ của một agent quá lòng vòng... Thu hồi với Dùng ở mọi nơi, thực chất người
   dùng không biết dùng đâu"): mục chỉ còn hạn mức lượt tự phát hôm nay và ô chọn hạn mức. Danh sách bài học theo phạm
   vi, bài học cũ trong MEMORY.md, thay đổi của tự rà soát và đề xuất không còn trên màn hình: người dùng nhắn trong chat
   ("thôi đừng làm vậy nữa"), Javis dùng tool `javis_memory` (op=lessons, lesson_revoke, lesson_add).

   Ô chọn gọi POST /agents/{slug}/budget. Chỉ hiện "Đã lưu" và vẽ lại SAU khi máy chủ trả 200; lỗi thì nói lý do, giữ
   giá trị cũ. `partHtml`, `budgetLine`, `actionRequest` thuần (không DOM, không mạng) để test chạy dưới node. */
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

  var CAP_CHOICES = [0, 2, 4, 6, 10, 20];

  function budgetLine(b) {
    var x = b || {};
    if (x.cap == null) return tw("lessons.budget_unlimited", { used: x.used || 0 });
    return tw("lessons.budget_line", { used: x.used || 0, cap: x.cap, reserved: x.reserved == null ? 2 : x.reserved });
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
    var b = p.budget || {};
    var cur = b.cap == null ? "unlimited" : String(b.cap);
    var choices = CAP_CHOICES.slice();
    if (b.cap != null && choices.indexOf(Number(b.cap)) < 0) choices.push(Number(b.cap));
    choices.sort(function (x, y) { return x - y; });
    var html = '<div class="lessons-part" data-slug="' + esc(p.slug || "") + '" data-agent="' + esc(p.agent_key || "") +
      '"><div class="pulse-sub">' + esc(tw("lessons.title")) + infoBtn() + "</div>" +
      infoBody('<div class="pulse-line pulse-note">' + esc(tw("lessons.budget_note")) + "</div>") +
      '<div class="pulse-line">' + esc(budgetLine(b)) + "</div>" +
      '<label class="lessons-budget"><span>' + esc(tw("lessons.budget_label")) + '</span><select class="lessons-budget-sel" data-prev="' + esc(cur) + '"' +
      dis + ">" + choices.map(function (n) {
        return '<option value="' + n + '"' + (String(n) === cur ? " selected" : "") + ">" + esc(String(n)) + "</option>";
      }).join("") + '<option value="unlimited"' + (cur === "unlimited" ? " selected" : "") + ">" +
      esc(tw("lessons.unlimited")) + "</option></select></label>";
    if (o.err) html += '<div class="pulse-line pulse-err" role="alert">' + esc(tw("lessons.error", { e: o.err })) + "</div>";
    else if (o.msg) html += '<div class="pulse-line pulse-ok" role="status">' + esc(o.msg) + "</div>";
    return html + "</div>";
  }

  /* 0.190.0: the one plain line of the Auto block in an assistant's settings: "Tự làm tối đa [6] lần mỗi ngày", with
     how many it did today. No reserve numbers, no explanation box. Same select and same save path as the full part. */
  function capHtml(view, opts) {
    var o = opts || {}, v = view || {};
    var p = (v.parts && v.parts.lessons) || null;
    if (!p || p.error) return "";
    var b = p.budget || {};
    var cur = b.cap == null ? "unlimited" : String(b.cap);
    var choices = CAP_CHOICES.slice();
    if (b.cap != null && choices.indexOf(Number(b.cap)) < 0) choices.push(Number(b.cap));
    choices.sort(function (x, y) { return x - y; });
    var html = '<div class="lessons-part lessons-cap" data-compact="1" data-slug="' + esc(p.slug || "") + '">' +
      '<label class="lessons-budget"><span>' + esc(tw("lessons.cap_before")) + '</span><select class="lessons-budget-sel" ' +
      'data-prev="' + esc(cur) + '">' + choices.map(function (n) {
        return '<option value="' + n + '"' + (String(n) === cur ? " selected" : "") + ">" + esc(String(n)) + "</option>";
      }).join("") + '<option value="unlimited"' + (cur === "unlimited" ? " selected" : "") + ">" +
      esc(tw("lessons.cap_unlimited")) + '</option></select><span>' + esc(tw("lessons.cap_after")) + "</span></label>" +
      '<div class="pulse-line pulse-note">' + esc(tw("lessons.cap_today", { used: b.used || 0 })) + "</div>";
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

  /* URL và thân của lệnh đổi hạn mức. Thuần để test. */
  function actionRequest(slug, brain, value) {
    return { url: "/agents/" + encodeURIComponent(slug) + "/budget?brain=" + encodeURIComponent(brain || "brain"),
      body: { daily_calls: value === "unlimited" ? "unlimited" : Number(value) } };
  }

  function redraw(box, view, o) {
    if (box.getAttribute && box.getAttribute("data-compact") === "1") { box.outerHTML = capHtml(view, o); return; }
    var part = box.closest ? box.closest(".pulse-part") : null;
    (part || box.parentNode || box).innerHTML = partHtml(view, o);
  }

  function setBudget(box, sel) {
    var slug = box.getAttribute("data-slug");
    if (!slug) return;
    var req = actionRequest(slug, brainName(), sel.value);
    post(req.url, req.body).then(function (res) {
      if (res.code !== 200 || !res.j || res.j.ok !== true) throw res.j;
      var lv = res.j.view && res.j.view.name === "lessons" ? res.j.view : null;
      if (lv) redraw(box, { parts: { lessons: lv } }, { msg: tw("lessons.done") });
    }).catch(function (e) {
      // Hạn mức bị từ chối: ô chọn về lại giá trị đang lưu (review T3 L P3), không giữ giá trị máy chủ chưa nhận.
      sel.value = sel.getAttribute("data-prev");
      var note = box.querySelector(".lessons-note");
      if (!note) {
        note = document.createElement("div");
        note.className = "pulse-line pulse-err lessons-note";
        note.setAttribute("role", "alert");
        box.appendChild(note);
      }
      note.textContent = tw("lessons.error", { e: (e && e.error) || tw("lessons.error_generic") });
    });
  }

  if (typeof document !== "undefined" && document.addEventListener) {
    document.addEventListener("change", function (ev) {
      var s = ev.target;
      if (!s || !s.classList || !s.classList.contains("lessons-budget-sel")) return;
      var box = s.closest(".lessons-part");
      if (box) setBudget(box, s);
    });
  }

  var part = { name: "lessons", render: function (view) { return partHtml(view, {}); },
    compact: function (view) { return capHtml(view, {}); } };
  if (typeof window !== "undefined") {
    window.JavisPulseParts = window.JavisPulseParts || [];
    if (!window.JavisPulseParts.some(function (x) { return x && x.name === "lessons"; })) window.JavisPulseParts.push(part);
  }
  var apiOut = { partHtml: partHtml, capHtml: capHtml, budgetLine: budgetLine, actionRequest: actionRequest, part: part };
  if (typeof module !== "undefined" && module.exports) module.exports = apiOut;
})();
