// ============================================================
// Javis - Bộ phán xử hội thoại nhóm (0.65.0): phần giao diện.
//
// Hai mảnh, cả hai do chatbots.js gọi:
//   - khối TRONG FORM bot (formHtml / bind / read): chế độ Tắt / Chạy thử / Bật, độ hăng hái, luật lên
//     tiếng, tên gọi thêm, người được dạy bot, tự học. Chỉ hiện khi chọn "Tự đánh giá" ở phần Bot trả lời ai.
//   - PANEL "Bộ phán xử" của một bot (openPanel): mọi quyết định gần đây KỂ CẢ lúc bot im, nút Đúng/Sai để
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

  var MODES = ["off", "shadow", "on"], EAG = ["low", "medium", "high"], GROUND = ["docs", "role"];
  var MODE_LB = { off: "rp.mode_off", shadow: "rp.mode_shadow", on: "rp.mode_on" };
  var MODE_H = { off: "rp.mode_off_h", shadow: "rp.mode_shadow_h", on: "rp.mode_on_h" };
  var EAG_LB = { low: "rp.eag_low", medium: "rp.eag_medium", high: "rp.eag_high" };
  var GROUND_LB = { docs: "rp.ground_docs", role: "rp.ground_role" };
  var GROUND_H = { docs: "rp.ground_docs_h", role: "rp.ground_role_h" };
  var CODE_LB = {
    no_signal: "rp.code_no_signal", junk: "rp.code_junk", addressed_other: "rp.code_addressed_other",
    no_grounding: "rp.code_no_grounding", rate_limited: "rp.code_rate_limited",
    rate_limited_user: "rp.code_rate_limited", just_spoke: "rp.code_just_spoke",
    policy_error: "rp.code_policy_error", owner_typing: "rp.code_owner_typing",
    judge_silent: "rp.code_judge_silent", below_threshold: "rp.code_below_threshold",
  };
  var LABEL_LB = { correct: "rp.label_correct", missed: "rp.label_missed", intruded: "rp.label_intruded",
                   taught: "rp.label_taught" };
  var SOURCE_LB = { auto: "rp.source_auto", owner: "rp.source_owner", bootstrap: "rp.source_bootstrap" };

  // Cấu hình mặc định = ĐÚNG mặc định của server (`chatbot_reply_policy.normalize_config`): tắt, vừa, tài
  // liệu, không học. Bản ghi cũ chưa có khoá này thì form hiện đúng các giá trị đó.
  function normalize(rp) {
    var r = rp && typeof rp === "object" ? rp : {};
    return {
      mode: MODES.indexOf(r.mode) >= 0 ? r.mode : "off",
      eagerness: EAG.indexOf(r.eagerness) >= 0 ? r.eagerness : "medium",
      grounding: GROUND.indexOf(r.grounding) >= 0 ? r.grounding : "docs",
      guidelines: String(r.guidelines || ""),
      aliases: Array.isArray(r.aliases) ? r.aliases.slice() : [],
      trainer_ids: Array.isArray(r.trainer_ids) ? r.trainer_ids.slice() : [],
      learning_enabled: r.learning_enabled === true,
    };
  }

  // ---------------------------------------------------------------- khối trong form
  // `seg(id, name, [{v, t}], cur)` là htmlSeg của chatbots.js (nút bấm chọn một), truyền vào để dùng chung.
  function formHtml(rp, seg, opts) {
    var c = normalize(rp);
    var canDraft = !!(opts && opts.canDraft);
    return '<div id="cbRpBox" class="cb-rp" style="display:none">' +
      '<div class="cb-sub">' + esc(tt("rp.section")) + '</div>' +
      seg("cbRpMode", "cbRpMode", MODES.map(function (m) { return { v: m, t: tt(MODE_LB[m]) }; }), c.mode) +
      '<div class="cb-hint" id="cbRpModeH"></div>' +
      '<div id="cbRpMore">' +
        '<div class="cb-sub">' + esc(tt("rp.eag_lb")) + '</div>' +
        seg("cbRpEag", "cbRpEag", EAG.map(function (m) { return { v: m, t: tt(EAG_LB[m]) }; }), c.eagerness) +
        '<div class="cb-sub">' + esc(tt("rp.ground_lb")) + '</div>' +
        seg("cbRpGround", "cbRpGround", GROUND.map(function (m) { return { v: m, t: tt(GROUND_LB[m]) }; }), c.grounding) +
        '<div class="cb-hint" id="cbRpGroundH"></div>' +
        '<label for="cbRpGuide">' + esc(tt("rp.guide_lb")) + '</label>' +
        '<textarea id="cbRpGuide" rows="4" maxlength="2000" placeholder="' + esc(tt("rp.guide_ph")) + '">' +
          esc(c.guidelines) + '</textarea>' +
        '<div class="cb-hint">' + esc(tt("rp.guide_h")) + '</div>' +
        (canDraft ? '<div class="cb-rp-draft"><button type="button" class="s-btn-ghost" id="cbRpDraft">' +
          esc(tt("rp.draft")) + '</button><span class="cb-hint" id="cbRpDraftS"></span></div>' : '') +
        '<label for="cbRpAliases">' + esc(tt("rp.alias_lb")) + '</label>' +
        '<input id="cbRpAliases" placeholder="' + esc(tt("rp.alias_ph")) + '" value="' + esc(c.aliases.join(", ")) + '">' +
        '<div class="cb-hint">' + esc(tt("rp.alias_h")) + '</div>' +
        '<label class="cb-rp-learn"><input type="checkbox" id="cbRpLearn"' + (c.learning_enabled ? " checked" : "") + '> ' +
          esc(tt("rp.learn_lb")) + '</label>' +
        '<div class="cb-hint">' + esc(tt("rp.learn_h")) + '</div>' +
        '<div id="cbRpTrainBox"' + (c.learning_enabled ? "" : ' style="display:none"') + '>' +
          '<label for="cbRpTrainers">' + esc(tt("rp.trainer_lb")) + '</label>' +
          '<input id="cbRpTrainers" placeholder="' + esc(tt("rp.trainer_ph")) + '" value="' + esc(c.trainer_ids.join(", ")) + '">' +
          '<div class="cb-hint">' + esc(tt("rp.trainer_h")) + '</div>' +
        '</div>' +
      '</div>' +
    '</div>';
  }

  function split(v) {
    return String(v || "").split(/[,\n;]/).map(function (x) { return x.trim(); }).filter(Boolean);
  }
  function checked(box, name) {
    var n = box.querySelector('input[name="' + name + '"]:checked');
    return n ? n.value : "";
  }

  // Đọc form ra đúng khuôn `reply_policy` của server. Khối ẩn (không chọn Tự đánh giá) vẫn được đọc, để
  // cấu hình đã đặt không mất khi chủ tạm chuyển sang chế độ lên tiếng khác.
  function read(box) {
    return {
      mode: checked(box, "cbRpMode") || "off",
      eagerness: checked(box, "cbRpEag") || "medium",
      grounding: checked(box, "cbRpGround") || "docs",
      guidelines: (box.querySelector("#cbRpGuide") || {}).value || "",
      aliases: split((box.querySelector("#cbRpAliases") || {}).value),
      trainer_ids: split((box.querySelector("#cbRpTrainers") || {}).value),
      learning_enabled: !!(box.querySelector("#cbRpLearn") || {}).checked,
    };
  }

  function sync(box, name) {
    box.querySelectorAll('input[name="' + name + '"]').forEach(function (i) {
      i.parentNode.classList.toggle("on", i.checked);
    });
  }

  // `opts`: { botId, onDrafted(text) }. Gắn hành vi cho khối sau khi form đã vào DOM.
  function bind(box, opts) {
    function ve() {
      sync(box, "cbRpMode"); sync(box, "cbRpEag"); sync(box, "cbRpGround");
      var m = checked(box, "cbRpMode") || "off";
      box.querySelector("#cbRpModeH").textContent = tt(MODE_H[m]);
      box.querySelector("#cbRpMore").style.display = m === "off" ? "none" : "";
      box.querySelector("#cbRpGroundH").textContent = tt(GROUND_H[checked(box, "cbRpGround") || "docs"]);
      box.querySelector("#cbRpTrainBox").style.display = box.querySelector("#cbRpLearn").checked ? "" : "none";
    }
    ["cbRpMode", "cbRpEag", "cbRpGround"].forEach(function (n) {
      box.querySelectorAll('input[name="' + n + '"]').forEach(function (i) { i.onchange = ve; });
    });
    box.querySelector("#cbRpLearn").onchange = ve;
    var nut = box.querySelector("#cbRpDraft");
    if (nut && opts && opts.botId) {
      nut.onclick = async function () {
        var s = box.querySelector("#cbRpDraftS");
        nut.disabled = true;
        s.textContent = tt("rp.drafting");
        try {
          var d = await api("/chatbots/" + encodeURIComponent(opts.botId) + "/reply-policy/draft-guidelines",
                            { method: "POST" });
          s.textContent = tt("rp.drafted");
          if (opts.onDrafted) opts.onDrafted(d.generated_text || "");
        } catch (e) {
          s.textContent = tt("rp.draft_err") + " " + e.message;
        }
        nut.disabled = false;
      };
    }
    ve();
    return ve;
  }

  // Một dòng tóm tắt cho thẻ bot; "" khi bộ phán xử tắt (thẻ không cần nói gì).
  function summary(b) {
    var c = normalize(b && b.reply_policy);
    return c.mode === "off" ? "" : tt(c.mode === "on" ? "rp.tt_on" : "rp.tt_shadow");
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
      var hoc = d.config.learning_enabled;
      return '<div class="cb-rp-row" data-id="' + x.id + '">' +
        '<div class="cb-rp-h">' + chip(noi ? "ok" : "off", tt(noi ? "rp.verdict_reply" : "rp.verdict_silent")) +
          ' <b>' + esc(x.sender || "") + '</b>' +
          (x.sender_id && (d.config.trainer_ids || []).indexOf(x.sender_id) < 0
            ? ' <button type="button" class="cb-rp-lnk rp-owner" data-sid="' + esc(x.sender_id) + '">' + esc(tt("rp.is_owner")) + '</button>' : '') +
          ' <span class="cb-rp-ts">' + esc(gio(x.ts)) + '</span></div>' +
        '<div class="cb-rp-t">' + esc(x.text || "") + '</div>' +
        '<div class="cb-rp-m">' + esc(ly) + (diem ? ' · ' + esc(diem) : '') +
          (x.label ? ' ' + chip(x.label === "correct" ? "ok" : "warn", tt(LABEL_LB[x.label] || "rp.label_correct")) : '') +
          (hoc && x.candidate ? ' <button type="button" class="cb-rp-lnk rp-thumb" data-t="up">' + esc(tt("rp.thumb_up")) + '</button>' +
            '<button type="button" class="cb-rp-lnk rp-thumb" data-t="down">' + esc(tt("rp.thumb_down")) + '</button>' : '') +
        '</div></div>';
    }

    function ve() {
      var s = d.stats || {};
      var h = '<div class="cb-sum">' + esc(tt("rp.stats", { decisions: s.decisions || 0, silent: s.silent || 0,
        labeled: s.labeled || 0, cases: s.cases || 0, lessons: s.lessons || 0 })) + '</div>';
      if (d.config.mode === "off") h += '<div class="cb-hint">' + esc(tt("rp.off_note")) + '</div>';
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

  window.JavisReplyPolicy = { formHtml: formHtml, bind: bind, read: read, normalize: normalize, summary: summary,
                              openPanel: openPanel };
})();
