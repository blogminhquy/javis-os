// ============================================================
// Javis - Bộ phán xử hội thoại nhóm: phần giao diện.
//
// Từ 0.65.1 KHÔNG còn ô cài đặt nào cho bộ phán xử. Chọn "Tự đánh giá" ở phần Bot trả lời ai là xong: máy tự
// chọn mức hăng hái, tự tra tài liệu hay dựa vào vai, tự học từ phản ứng trong nhóm. Chủ chỉ còn hai việc, đều
// làm ngay trên dữ liệu thật: bấm Đúng/Sai ở từng quyết định, và bấm "Là chủ" ở tin của mình để bot nghe lời dạy.
//
// Hai mảnh, cả hai do chatbots.js gọi:
//   - formHtml(): một dòng giải thích trong FORM bot, chỉ hiện khi chọn "Tự đánh giá".
//   - openPanel(bot): PANEL "Bộ phán xử" của một bot: mọi quyết định gần đây KỂ CẢ lúc bot im, nút Đúng/Sai để
//     dạy, ca đã học, bài học, nút Quên hết.
//
// Đặc tả: docs/superpowers/specs/2026-09-30-bo-phan-xu-nhom-design.md. Mọi chữ hiện ra lấy từ từ điển
// (khoá `rp.*`); mã im (`silence_code`) và nhãn là DỮ LIỆU trong bảng bên dưới, không ghép chuỗi khoá.
// ============================================================
(function () {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function el(html) { var d = document.createElement("div"); d.innerHTML = html.trim(); return d.firstChild; }
  function tt(k, v) { return window.t(k, v); }
  function loc() { return (window.JavisI18n && window.JavisI18n.locale()) || "vi-VN"; }
  function gio(ts) {
    if (!ts) return "";
    try { return new Date(ts * 1000).toLocaleString(loc()); } catch (e) { return ""; }
  }
  async function api(url, opts) {
    var r = await fetch(url, opts || {});
    var d = null;
    try { d = await r.json(); } catch (e) { d = {}; }
    if (!r.ok || d.ok === false) throw new Error((d && d.error) || tt("cb.loi_ma", { ma: r.status }));
    return d;
  }
  function fd(obj) {
    var f = new FormData();
    Object.keys(obj || {}).forEach(function (k) { if (obj[k] != null) f.append(k, obj[k]); });
    return f;
  }

  var CODE_LB = {
    no_signal: "rp.code_no_signal", junk: "rp.code_junk", addressed_other: "rp.code_addressed_other",
    no_grounding: "rp.code_no_grounding", rate_limited: "rp.code_rate_limited",
    rate_limited_user: "rp.code_rate_limited", just_spoke: "rp.code_just_spoke",
    policy_error: "rp.code_policy_error", owner_typing: "rp.code_owner_typing",
    judge_silent: "rp.code_judge_silent", below_threshold: "rp.code_below_threshold",
    agent_silent: "rp.code_agent_silent", taken_over: "rp.code_taken_over",
  };
  var LABEL_LB = { correct: "rp.label_correct", missed: "rp.label_missed", intruded: "rp.label_intruded",
                   taught: "rp.label_taught" };
  var SOURCE_LB = { auto: "rp.source_auto", owner: "rp.source_owner", bootstrap: "rp.source_bootstrap" };

  // ---------------------------------------------------------------- khối trong form
  // Chỉ một dòng giải thích. `#cbRpBox` giữ nguyên để chatbots.js bật/tắt theo lựa chọn "Tự đánh giá".
  function formHtml() {
    return '<div id="cbRpBox" class="cb-hint cb-rp-note" style="display:none">' + esc(tt("rp.auto_note")) + '</div>';
  }

  // Một dòng tóm tắt cho thẻ bot; "" khi bot không ở chế độ Tự đánh giá (thẻ không cần nói gì).
  function summary(b) {
    return b && b.reply_when === "auto" ? tt("rp.tt_on") : "";
  }

  // ---------------------------------------------------------------- panel của một bot
  async function openPanel(bot) {
    var box = el('<div class="cb-modal"><div class="cb-form cb-rp-form">' +
      '<h3>' + esc(tt("rp.title", { name: bot.name })) + '</h3>' +
      '<div class="cb-rp-body">' + esc(tt("common.loading")) + '</div>' +
      '<div class="cb-form-acts">' +
        '<button class="s-btn-ghost" id="rpForget" type="button">' + esc(tt("rp.forget")) + '</button>' +
        '<button class="s-btn" id="rpClose" type="button">' + esc(tt("common.close")) + '</button>' +
      '</div></div></div>');
    document.body.appendChild(box);
    var dong = function () { if (box.parentNode) box.parentNode.removeChild(box); };
    box.onmousedown = function (e) { if (e.target === box) dong(); };
    box.querySelector("#rpClose").onclick = dong;
    var than = box.querySelector(".cb-rp-body");
    var base = "/chatbots/" + encodeURIComponent(bot.id) + "/reply-policy";
    var soloSilent = false, d = null;

    async function tai() {
      try { d = await api(base + "?limit=100" + (soloSilent ? "&only_silent=true" : "")); }
      catch (e) { than.textContent = tt("rp.load_err") + " " + e.message; return; }
      ve();
    }

    function chip(cls, text) { return '<span class="cb-rp-chip ' + cls + '">' + esc(text) + '</span>'; }

    function dongQuyetDinh(x) {
      var noi = x.verdict === "reply";
      var diem = (x.score == null) ? "" : (Number(x.score).toFixed(2) + (x.threshold != null ? " / " + Number(x.threshold).toFixed(2) : ""));
      var ly = x.silence_code ? (CODE_LB[x.silence_code] ? tt(CODE_LB[x.silence_code]) : x.silence_code) : (x.reason || "");
      return '<div class="cb-rp-row" data-id="' + x.id + '">' +
        '<div class="cb-rp-h">' + chip(noi ? "ok" : "off", tt(noi ? "rp.verdict_reply" : "rp.verdict_silent")) +
          ' <b>' + esc(x.sender || "") + '</b>' +
          (x.sender_id && (d.config.trainer_ids || []).indexOf(x.sender_id) < 0
            ? ' <button type="button" class="cb-rp-lnk rp-owner" data-sid="' + esc(x.sender_id) + '">' + esc(tt("rp.is_owner")) + '</button>' : '') +
          ' <span class="cb-rp-ts">' + esc(gio(x.ts)) + '</span></div>' +
        '<div class="cb-rp-t">' + esc(x.text || "") + '</div>' +
        '<div class="cb-rp-m">' + esc(ly) + (diem ? ' · ' + esc(diem) : '') +
          (x.label ? ' ' + chip(x.label === "correct" ? "ok" : "warn", tt(LABEL_LB[x.label] || "rp.label_correct")) : '') +
          (x.candidate ? ' <button type="button" class="cb-rp-lnk rp-thumb" data-t="up">' + esc(tt("rp.thumb_up")) + '</button>' +
            '<button type="button" class="cb-rp-lnk rp-thumb" data-t="down">' + esc(tt("rp.thumb_down")) + '</button>' : '') +
        '</div></div>';
    }

    function ve() {
      var s = d.stats || {};
      var h = '<div class="cb-sum">' + esc(tt("rp.stats", { decisions: s.decisions || 0, silent: s.silent || 0,
        labeled: s.labeled || 0, cases: s.cases || 0, lessons: s.lessons || 0 })) + '</div>';
      h += '<div class="cb-hint">' + esc(tt("rp.panel_h")) + '</div>';
      h += '<label class="cb-rp-learn"><input type="checkbox" id="rpSolo"' + (soloSilent ? " checked" : "") + '> ' +
        esc(tt("rp.only_silent")) + '</label>';
      h += '<div class="cb-rp-list">' + ((d.decisions || []).length
        ? d.decisions.map(dongQuyetDinh).join("") : '<div class="cb-empty">' + esc(tt("rp.empty")) + '</div>') + '</div>';
      h += '<div class="cb-sub">' + esc(tt("rp.lessons")) + '</div>' + ((d.lessons || []).length
        ? '<ul class="cb-rp-ul">' + d.lessons.map(function (x) { return '<li>' + esc(x.text) + '</li>'; }).join("") + '</ul>'
        : '<div class="cb-hint">' + esc(tt("rp.no_lessons")) + '</div>');
      h += '<div class="cb-sub">' + esc(tt("rp.cases")) + '</div>' + ((d.cases || []).length
        ? '<div class="cb-rp-list">' + d.cases.map(function (c) {
            return '<div class="cb-rp-row" data-case="' + c.id + '"><div class="cb-rp-h">' +
              chip(c.correct_verdict === "reply" ? "ok" : "off", tt(c.correct_verdict === "reply" ? "rp.verdict_reply" : "rp.verdict_silent")) +
              ' ' + chip("", tt(SOURCE_LB[c.source] || "rp.source_auto")) +
              ' <button type="button" class="cb-rp-lnk rp-case-del">' + esc(tt("rp.case_del")) + '</button></div>' +
              '<div class="cb-rp-t">' + esc(c.text || "") + '</div></div>';
          }).join("") + '</div>'
        : '<div class="cb-hint">' + esc(tt("rp.no_cases")) + '</div>');
      if (d.role_profile) h += '<div class="cb-sub">' + esc(tt("rp.role_lb")) + '</div><pre class="cb-rp-pre">' + esc(d.role_profile) + '</pre>';
      than.innerHTML = h;
      var solo = than.querySelector("#rpSolo");
      if (solo) solo.onchange = function () { soloSilent = solo.checked; tai(); };
      than.querySelectorAll(".rp-thumb").forEach(function (b) {
        b.onclick = async function () {
          var id = b.closest(".cb-rp-row").dataset.id;
          try { await api(base + "/label", { method: "POST", body: fd({ decision_id: id, thumb: b.dataset.t }) }); await tai(); }
          catch (e) { window.alert(e.message); }
        };
      });
      than.querySelectorAll(".rp-owner").forEach(function (b) {
        b.onclick = async function () {
          var ids = (d.config.trainer_ids || []).concat([b.dataset.sid]);
          try {
            await api("/chatbots/" + encodeURIComponent(bot.id) + "/update",
                      { method: "POST", body: fd({ reply_policy: JSON.stringify({ trainer_ids: ids }) }) });
            await tai();
          } catch (e) { window.alert(e.message); }
        };
      });
      than.querySelectorAll(".rp-case-del").forEach(function (b) {
        b.onclick = async function () {
          var id = b.closest(".cb-rp-row").dataset["case"];
          try { await api(base + "/cases/" + encodeURIComponent(id) + "/delete", { method: "POST" }); await tai(); }
          catch (e) { window.alert(e.message); }
        };
      });
    }

    box.querySelector("#rpForget").onclick = async function () {
      if (!window.confirm(tt("rp.forget_confirm"))) return;
      try { await api(base + "/forget", { method: "POST", body: fd({}) }); await tai(); }
      catch (e) { window.alert(e.message); }
    };
    await tai();
  }

  window.JavisReplyPolicy = { formHtml: formHtml, summary: summary, openPanel: openPanel };
})();
