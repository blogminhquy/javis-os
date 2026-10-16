/* Bộ phán xử của từng trợ lý (T3 phần J, 0.156.0): lịch sử quyết định nói / chờ / im và nút sửa.

   Thiết kế: docs/superpowers/specs/2026-10-15-team-adaptive-design.md mục 7.6, 10; tài liệu docs/dev/team-chat-t3-judge.md.

   Hai chỗ hiện:
   - Thẻ trợ lý: phần "judge" của khung nhịp (phần P dựng `GET /agents/{slug}/pulse`, mỗi phần tự vẽ):
     `window.JavisPulseParts.push({name: "judge", render})`. Phần P chưa có thì mảng chỉ nằm chờ, không lỗi.
   - Hàng thành viên trong ngăn Nhóm (teams.js): ô `.agj-host[data-judge-slug][data-judge-ctx]`, `hydrate(root)` tải
     `GET /agents/{slug}/judge?context_ref=team:<id>` và vẽ đúng ngữ cảnh nhóm đó.

   Nút "Đáng lẽ nên nói" / "Nên im (chen ngang)" gọi `POST /agents/{slug}/judge/label`; chỉ báo thành công SAU khi máy chủ trả
   200, lỗi thì nói lý do và giữ nguyên trạng thái cũ. Ca im không có tin vẫn có dòng để sửa (không giả một tin để thả emoji).

   Các hàm *Html, postLabel thuần (không DOM) để test chạy dưới node. */
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
  var VERDICT_KEY = { speak: "judge.verdict.speak", wait: "judge.verdict.wait", silent: "judge.verdict.silent" };
  var KIND_KEY = { direct: "judge.kind.direct", message: "judge.kind.message", related: "judge.kind.related",
    wait: "judge.kind.wait", proactive: "judge.kind.proactive", clarify: "judge.kind.clarify" };
  var CODE_KEY = { no_signal: "judge.code.no_signal", code_only: "judge.code.code_only",
    policy_error: "judge.code.policy_error", timeout: "judge.code.timeout", bad_json: "judge.code.bad_json",
    engine_unavailable: "judge.code.engine_unavailable", judge_busy: "judge.code.judge_busy",
    judge_cap: "judge.code.judge_cap", server_ceiling: "judge.code.server_ceiling",
    below_threshold: "judge.code.below_threshold", not_selected: "judge.code.not_selected", k_zero: "judge.code.k_zero",
    batch_full: "judge.code.batch_full", rejudge_limit: "judge.code.rejudge_limit", wait_expired: "judge.code.wait_expired",
    depth_limit: "judge.code.depth_limit", loop: "judge.code.loop", waiting_quota: "judge.code.waiting_quota",
    no_sender: "judge.code.no_sender", turn_blocked: "judge.code.turn_blocked", model_silent: "judge.code.model_silent",
    wait_cancelled: "judge.code.wait_cancelled" };
  var EFFECT_KEY = { applied: "judge.effect.applied", stored_only: "judge.effect.stored_only",
    stored_before_resume: "judge.effect.stored_before_resume", stored_direct: "judge.effect.stored_direct" };
  var LABEL_KEY = { should_speak: "judge.label.should_speak", should_silent: "judge.label.should_silent" };
  var LABELS = ["should_speak", "should_silent"];

  function num(v) { return (v === null || v === undefined || isNaN(Number(v))) ? "" : Number(v).toFixed(2); }

  function when(ts) {
    if (!ts) return "";
    try { return new Date(Number(ts) * 1000).toLocaleString(); } catch (e) { return ""; }
  }

  function ctxTitle(c) {
    if (String(c.context_ref || "").indexOf("dm:") === 0) return tw("judge.ctx_dm");
    return c.label ? tw("judge.ctx_team", { name: c.label }) : tw("judge.ctx_team_unnamed");
  }

  // Một quyết định. `busy`: id đang lưu; `note`: {id: chữ} kết quả lần bấm gần nhất (chỉ có sau khi máy chủ trả lời).
  function decisionHtml(d, opts) {
    opts = opts || {};
    var id = String(d.decision_id);
    var verdict = VERDICT_KEY[d.verdict] ? tw(VERDICT_KEY[d.verdict]) : d.verdict;
    var kind = KIND_KEY[d.kind] ? tw(KIND_KEY[d.kind]) : "";
    var why = d.reason || (CODE_KEY[d.silence_code] ? tw(CODE_KEY[d.silence_code]) : "");
    var score = d.score !== null && d.score !== undefined && d.threshold !== null && d.threshold !== undefined
      ? tw("judge.score", { score: num(d.score), threshold: num(d.threshold) }) : "";
    var head = '<div class="agj-dhead"><span class="agj-verdict agj-v-' + esc(d.verdict) + '">' + esc(verdict) + "</span>" +
      (kind ? '<span class="agj-kind">' + esc(kind) + "</span>" : "") +
      (d.volunteer ? '<span class="agj-kind">' + esc(tw("judge.volunteer")) + "</span>" : "") +
      '<span class="agj-when">' + esc(when(d.created_at)) + "</span></div>";
    var body = (d.excerpt ? '<div class="agj-excerpt">' + esc(d.excerpt) + "</div>" : "") +
      (why ? '<div class="agj-why">' + esc(why) + "</div>" : "") +
      (score ? '<div class="agj-score">' + esc(score) + "</div>" : "") +
      (d.message_ref ? "" : (d.verdict !== "speak" ? '<div class="agj-sub">' + esc(tw("judge.no_message")) + "</div>" : ""));
    var lab = "";
    if (d.label) {
      lab = '<div class="agj-labeled">' + esc(tw("judge.labeled", { label: tw(LABEL_KEY[d.label] || d.label) })) +
        (EFFECT_KEY[d.label_effect] ? " · " + esc(tw(EFFECT_KEY[d.label_effect])) : "") + "</div>";
    }
    var actions = "";
    if (d.address === "certain") {
      actions = '<div class="agj-sub">' + esc(tw("judge.direct_note")) + "</div>";
    } else {
      var busy = String(opts.busy || "") === id;
      actions = '<div class="agj-actions" role="group" aria-label="' + esc(tw("judge.fix")) + '">' + LABELS.map(function (L) {
        var on = d.label === L;
        return '<button type="button" class="ws-btn agj-btn" data-agj-label="' + L + '" data-agj-id="' + esc(id) + '"' +
          ' aria-pressed="' + (on ? "true" : "false") + '"' + (busy ? " disabled" : "") + ">" + esc(tw(LABEL_KEY[L])) + "</button>";
      }).join("") + (d.label ? '<button type="button" class="ws-btn agj-btn" data-agj-label="" data-agj-id="' + esc(id) + '"' +
        (busy ? " disabled" : "") + ">" + esc(tw("judge.label.clear")) + "</button>" : "") + "</div>";
    }
    var note = opts.note && opts.note[id] ? '<div class="agj-note" role="status">' + esc(opts.note[id]) + "</div>" : "";
    return '<li class="agj-dec" data-agj-row="' + esc(id) + '">' + head + body + lab + actions + note + "</li>";
  }

  function contextHtml(c, opts) {
    var decs = c.decisions || [];
    var meta = tw("judge.threshold", { threshold: num(c.threshold), offset: (Number(c.offset) >= 0 ? "+" : "") + num(c.offset) });
    return '<section class="agj-ctx" aria-label="' + esc(ctxTitle(c)) + '"><div class="agj-ctx-head">' + esc(ctxTitle(c)) +
      '</div><div class="agj-sub">' + esc(meta) + "</div>" +
      (decs.length ? '<ul class="agj-list">' + decs.map(function (d) { return decisionHtml(d, opts); }).join("") + "</ul>"
        : '<div class="agj-sub">' + esc(tw("judge.empty")) + "</div>") + "</section>";
  }

  // Cả phần "judge" (thẻ trợ lý) hay một ngữ cảnh (hàng thành viên nhóm, `opts.compact`).
  function viewHtml(view, opts) {
    opts = opts || {};
    if (!view) return "";
    var ctxs = view.contexts || [];
    // 0.175.0: hai câu giải thích nằm sau nút i cạnh tiêu đề (chủ repo: tab Cài đặt "nhiều thông tin quá").
    var head = opts.compact ? "" : '<div class="agj-head">' + esc(tw("judge.title")) + infoBtn() + "</div>" +
      infoBody('<div class="agj-sub">' + esc(tw("judge.intro")) + "</div>" + '<div class="agj-sub">' +
        esc(tw(view.resonance_on ? "judge.learn_on" : "judge.learn_off")) + "</div>");
    return '<div class="agj">' + head + (ctxs.length ? ctxs.map(function (c) { return contextHtml(c, opts); }).join("")
      : '<div class="agj-sub">' + esc(tw("judge.empty")) + "</div>") + "</div>";
  }

  function labelUrl(slug, brain) {
    return "/agents/" + encodeURIComponent(slug) + "/judge/label?brain=" + encodeURIComponent(brain || "brain");
  }

  function viewUrl(slug, brain, ctx) {
    return "/agents/" + encodeURIComponent(slug) + "/judge?brain=" + encodeURIComponent(brain || "brain") +
      (ctx ? "&context_ref=" + encodeURIComponent(ctx) : "");
  }

  // Gửi nhãn. Trả Promise {ok, decision, text}: `ok` chỉ khi máy chủ trả 200.
  function postLabel(fetchFn, slug, brain, decisionId, label) {
    return fetchFn(labelUrl(slug, brain), {
      method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision_id: Number(decisionId), label: label || "" }),
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (r.status === 200 && j && j.ok) {
          return { ok: true, decision: j.decision || null, text: tw(label ? "judge.saved" : "judge.cleared") };
        }
        return { ok: false, decision: null, text: (j && j.error) || tw("judge.save_failed") };
      });
    }, function () { return { ok: false, decision: null, text: tw("judge.save_failed") }; });
  }

  // ───────────── phần DOM ─────────────

  function brain() {
    try {
      if (window.JavisSessions && window.JavisSessions.brain) return window.JavisSessions.brain();
      return (window.currentBrainPath && window.currentBrainPath()) || "brain";
    } catch (e) { return "brain"; }
  }

  var CACHE_MS = 15000;
  var cache = {};     // slug|ctx -> {at, view}
  var state = {};     // slug|ctx -> {busy, note}

  function replaceDecision(view, dec) {
    (view.contexts || []).forEach(function (c) {
      (c.decisions || []).forEach(function (d, i) { if (String(d.decision_id) === String(dec.decision_id)) c.decisions[i] = dec; });
    });
  }

  function paint(host, key, view, compact) {
    host.innerHTML = viewHtml(view, { compact: compact, busy: (state[key] || {}).busy, note: (state[key] || {}).note });
  }

  // Tải lại khung phán xử của một ô sau khi lưu nhãn (ngưỡng và độ lệch do máy chủ tính). Lỗi mạng thì giữ khung cũ.
  function refreshView(host, slug, key, compact) {
    if (typeof window === "undefined" || !window.fetch) return null;
    var ctx = key.slice(key.indexOf("|") + 1);
    return window.fetch(viewUrl(slug, brain(), ctx === "*" ? "" : ctx), { credentials: "same-origin" }).then(function (r) {
      return r.json().then(function (j) { return { code: r.status, j: j || {} }; });
    }).then(function (r) {
      if (r.code !== 200 || !r.j.judge) return;
      cache[key] = { at: Date.now(), view: r.j.judge };
      paint(host, key, r.j.judge, compact);
    }).catch(function () { return null; });
  }

  function bind(host, slug, key, getView, compact) {
    if (host.getAttribute("data-agj-bound") === "1") return;
    host.setAttribute("data-agj-bound", "1");
    host.addEventListener("click", function (e) {
      var b = e.target.closest ? e.target.closest("[data-agj-id]") : null;
      if (!b || !host.contains(b)) return;
      e.preventDefault();
      e.stopPropagation();
      var id = b.getAttribute("data-agj-id"), label = b.getAttribute("data-agj-label") || "";
      var st = state[key] = state[key] || { note: {} };
      if (st.busy) return;
      st.busy = id;
      st.note[id] = tw("judge.saving");
      paint(host, key, getView(), compact);
      postLabel(window.fetch.bind(window), slug, brain(), id, label).then(function (res) {
        st.busy = null;
        st.note[id] = res.text;
        if (res.ok && res.decision) replaceDecision(getView(), res.decision);
        paint(host, key, getView(), compact);
        // Nhãn dịch ngưỡng của ngữ cảnh ở máy chủ: lấy lại khung để dòng "Ngưỡng ... (độ lệch ...)" đúng số mới.
        if (res.ok) refreshView(host, slug, key, compact);
      });
    });
  }

  // Vẽ vào mọi `.agj-host[data-judge-slug]` trong `root` (hàng thành viên đang mở).
  function hydrate(root) {
    if (!root || !root.querySelectorAll) return;
    Array.prototype.forEach.call(root.querySelectorAll(".agj-host[data-judge-slug]"), function (host) {
      var slug = host.getAttribute("data-judge-slug"), ctx = host.getAttribute("data-judge-ctx") || "";
      var key = slug + "|" + ctx;
      var hit = cache[key];
      var getView = function () { return (cache[key] || {}).view; };
      bind(host, slug, key, getView, true);
      if (hit && Date.now() - hit.at < CACHE_MS) { paint(host, key, hit.view, true); return; }
      host.innerHTML = '<div class="agj-sub">' + esc(tw("judge.loading")) + "</div>";
      window.fetch(viewUrl(slug, brain(), ctx), { credentials: "same-origin" }).then(function (r) {
        return r.json().then(function (j) { return { code: r.status, j: j || {} }; });
      }).then(function (r) {
        if (r.code !== 200 || !r.j.judge) { host.innerHTML = '<div class="agj-sub">' + esc(tw("judge.load_failed")) + "</div>"; return; }
        cache[key] = { at: Date.now(), view: r.j.judge };
        paint(host, key, r.j.judge, true);
      }).catch(function () { host.innerHTML = '<div class="agj-sub">' + esc(tw("judge.load_failed")) + "</div>"; });
    });
  }

  // Phần "judge" trong khung nhịp của thẻ trợ lý. Hai cách gọi: trang nhịp (agent-pulse.js) gọi `render(view, null,
  // {slug})` và cần CHUỖI HTML (mục lấy ở `view.parts.judge`); cách cũ `render(part, el, ctx)` vẽ thẳng vào `el`.
  function render(a, el, ctx) {
    var slug = (ctx && ctx.slug) || "";
    var key = slug + "|*";
    if (el) {
      cache[key] = { at: Date.now(), view: a };
      paint(el, key, a, false);
      if (slug) bind(el, slug, key, function () { return (cache[key] || {}).view; }, false);
      return el.innerHTML;
    }
    // Hàng thành viên của một nhóm đã có ô phán xử riêng cho đúng nhóm đó (teams.js): không vẽ lần hai trong khung nhịp.
    if (ctx && ctx.only) return "";
    var part = a && a.parts ? a.parts.judge : a;
    if (!part || part.error || !part.contexts) return "";
    cache[key] = { at: Date.now(), view: part };
    // Gắn nút sửa sau khi trang nhịp đã chèn chuỗi vào DOM (một lần mỗi ô).
    if (slug && typeof setTimeout === "function" && typeof document !== "undefined") {
      setTimeout(function () {
        Array.prototype.forEach.call(document.querySelectorAll(".agj-host.agj-pulse"), function (h) {
          if (h.getAttribute("data-judge-slug") !== slug) return;
          bind(h, slug, key, function () { return (cache[key] || {}).view; }, false);
        });
      }, 0);
    }
    return '<div class="agj-host agj-pulse" data-judge-slug="' + esc(slug) + '" data-judge-ctx="">' +
      viewHtml(part, { compact: false }) + "</div>";
  }

  var api = { decisionHtml: decisionHtml, contextHtml: contextHtml, viewHtml: viewHtml, postLabel: postLabel,
    labelUrl: labelUrl, viewUrl: viewUrl, hydrate: hydrate, render: render, refreshView: refreshView };
  if (typeof window !== "undefined") {
    window.JavisAgentJudge = api;
    window.JavisPulseParts = window.JavisPulseParts || [];
    window.JavisPulseParts.push({ name: "judge", render: render });
  }
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
