/* Trang Nhóm: nhóm chat team (T1 tới T5).

   Thiết kế: docs/superpowers/specs/2026-10-13-team-chat-design.md mục 16; bố cục gọn kiểu app chat ở T5
   (docs/dev/team-chat-t5.md). Hai phần chính: danh sách nhóm (trái) và khung chat. Mọi thứ ít dùng nằm trong một
   ngăn "Việc | Nhóm" mở từ đầu khung chat (cột phải trên máy tính, trang trượt lên trên điện thoại).

   Gửi tin bằng POST /teams/{id}/messages kèm `client_msg_id`: rớt mạng thì gửi lại ĐÚNG mã cũ, server trả tin cũ, không
   thêm lượt hay việc. Câu trả lời và trạng thái về qua WebSocket chung (app.js đổi gói `team_message` / `team_state`
   thành sự kiện `javis:team-event`).

   @: chọn từ gợi ý chèn "@Tên " vào chữ; lúc gửi, người được gọi là các "@Tên" CÒN trong chữ (xoá chữ là bỏ gọi).

   Các hàm *Html, mentionMatches, mentionsFromText, composerHint, levelOf, grantFor thuần (không DOM, không mạng) để test
   chạy dưới node. */
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
  // 0.214.0: the (i) button and its hidden block (info-tip.js); in Node tests (no JavisInfo) the text is drawn open.
  function infoBtn() { var J = typeof window !== "undefined" && window.JavisInfo; return J ? J.btn(tw("info.more")) : ""; }
  function infoBody(html) {
    var J = typeof window !== "undefined" && window.JavisInfo;
    return J ? J.body(html) : '<div class="info-body">' + html + "</div>";
  }
  // Icon lấy từ bộ Lucide của dashboard; chạy trong Node (test) thì không có, trả chuỗi rỗng.
  var ic = function (n, o) { return (typeof window !== "undefined" && window.ic) ? window.ic(n, o) : ""; };

  // Vai chỉ hiện cho bước của việc; câu trả lời trò chuyện thường không cần nhãn.
  var ROLE_KEY = { plan: "teams.role.plan", work: "teams.role.work", help: "teams.role.help",
    synthesize: "teams.role.synthesize" };
  var TURN_ROLE_KEY = { leader_reply: "teams.role.reply", member_reply: "teams.role.reply", plan: "teams.role.plan",
    work: "teams.role.work", help: "teams.role.help", synthesize: "teams.role.synthesize" };
  // Khoá viết TRỌN (không ghép chuỗi) để bộ kiểm i18n đọc được từng khoá đang dùng.
  var STATUS_KEY = { done: "teams.status.done", late_cancelled: "teams.status.late_cancelled", late: "teams.status.late",
    old_revision: "teams.status.old_revision", member_left: "teams.status.member_left", leader_changed: "teams.status.leader_changed",
    lease_lost: "teams.status.lease_lost" };
  var TEAM_STATUS_KEY = { active: "teams.status_active", paused: "teams.status_paused", archived: "teams.status_archived" };
  var BLOCK_KEY = { failed: "teams.block.failed", interrupted: "teams.block.interrupted", no_leader: "teams.block.no_leader",
    assignee_removed: "teams.block.assignee_removed", no_progress: "teams.block.no_progress", cap_reached: "teams.block.cap_reached",
    agent_busy_long: "teams.block.agent_busy_long", waiting_user: "teams.block.waiting_user", cancelled: "teams.block.cancelled",
    rejected: "teams.block.rejected", approval_expired: "teams.block.approval_expired",
    acceptance_review: "teams.block.acceptance_review", acceptance_failed: "teams.block.acceptance_failed",
    acceptance_checking: "teams.block.acceptance_checking",
    server_ceiling: "teams.block.server_ceiling" };
  var CAP_KEY = { task_turns: "teams.cap.task_turns", task_steps: "teams.cap.task_steps", daily_turns: "teams.cap.daily_turns",
    mentions: "teams.cap.mentions", help_depth: "teams.cap.help_depth", busy_wait_s: "teams.cap.busy_wait_s",
    judge_daily: "teams.cap.judge_daily", volunteer_k: "teams.cap.volunteer_k", judge_off_batch: "teams.cap.judge_off_batch",
    reply_parallel: "teams.cap.reply_parallel" };
  var TAB_KEY = { info: "teams.tab_info", jobs: "teams.tab_jobs", team: "teams.tab_team" };
  var LATE = ["late_cancelled", "late", "old_revision", "member_left", "leader_changed", "lease_lost"];
  // Trần chủ nhóm chỉnh được (team_store.OWNER_CAPS). Bốn trần đầu có "Không giới hạn" (lưu null, GOAL T1 mục 9).
  var CAP_FIELDS = ["task_turns", "task_steps", "help_depth", "daily_turns", "mentions", "busy_wait_s", "judge_daily",
    "volunteer_k"];
  var OWNER_UNL = ["task_turns", "task_steps", "help_depth", "daily_turns", "judge_daily"];
  // Ô chọn chế độ (T3 phần J): phán xử khi Cộng hưởng của trợ lý tắt, 1 = lọc code + lô, 0 = chỉ lọc code. Chỉ chủ chỉnh.
  // 0.260.0: reply_parallel, 1 = mọi người được @ trả lời cùng lúc, 0 = lần lượt theo thứ tự @.
  var CAP_MODES = ["judge_off_batch", "reply_parallel"];
  // Nhãn hai lựa chọn của từng ô chế độ: [nhãn của 1, nhãn của 0]. Khoá viết trọn cho bộ kiểm i18n.
  var MODE_LABELS = { judge_off_batch: ["teams.limits.mode_batch", "teams.limits.mode_code"],
    reply_parallel: ["teams.limits.mode_parallel", "teams.limits.mode_sequential"] };
  // Bảng giới hạn (GOAL T1 mục 9): bốn nhóm theo ai đổi được, nhãn từng dòng. Khoá viết trọn cho bộ kiểm i18n.
  var LIMIT_CATS = [{ id: "owner", key: "teams.limits.owner" }, { id: "leader", key: "teams.limits.leader" },
    { id: "server", key: "teams.limits.server" }, { id: "provider", key: "teams.limits.provider" }];
  // Nhãn bậc nhịp (T3) viết trọn khoá để bộ kiểm i18n đọc được.
  var PULSE_TIER_KEY = ["pulse.tier_0", "pulse.tier_1", "pulse.tier_2", "pulse.tier_3", "pulse.tier_4", "pulse.tier_5",
    "pulse.tier_6", "pulse.tier_7", "pulse.tier_8"];
  var LIMIT_KEY = { running_jobs: "teams.limits.running_jobs", max_parallel_teams: "teams.limits.max_parallel_teams",
    agent_one_turn: "teams.limits.agent_one_turn",
    engine_slots_cli: "teams.limits.engine_slots_cli", engine_slots_api: "teams.limits.engine_slots_api",
    job_parallel: "teams.limits.job_parallel", tool_slots: "teams.limits.tool_slots", busy_lease: "teams.limits.busy_lease", no_progress: "teams.limits.no_progress",
    turn_timeout: "teams.limits.turn_timeout", step_timeout: "teams.limits.step_timeout",
    admin_ops_per_turn: "teams.limits.admin_ops_per_turn", history_window: "teams.limits.history_window",
    text_only: "teams.limits.text_only", server_call_ceiling: "teams.limits.server_call_ceiling",
    max_tier: "teams.limits.max_tier", autonomous_reserve: "teams.limits.autonomous_reserve",
    agent_daily_calls: "teams.limits.agent_daily_calls",
    provider_quota: "teams.limits.provider_quota", account: "teams.limits.account" };
  // Toàn quyền (T3, spec 13): trần trưởng nhóm đổi được trong trần trần của chủ.
  var AUTH_CAPS = ["task_turns", "task_steps", "help_depth", "daily_turns"];
  var AUTH_CAP_KEY = { task_turns: "teams.cap.task_turns", task_steps: "teams.cap.task_steps",
    help_depth: "teams.cap.help_depth", daily_turns: "teams.cap.daily_turns", judge_daily: "teams.cap.judge_daily",
    volunteer_k: "teams.cap.volunteer_k" };
  // T3 phần J: trần phán xử trưởng nhóm Toàn quyền chỉnh được trong trần tối đa của chủ. Nằm ngoài AUTH_CAPS để ba mức tự
  // quyết (levelOf, grantFor) giữ nguyên nghĩa; hộp cấp quyền chi tiết có thêm hai dòng này.
  var AUTH_JUDGE_CAPS = ["judge_daily", "volunteer_k"];
  // Provider được "Không giới hạn" lượt (D6). Từ 0.142.0 lượt nhóm chạy model của trợ lý hay model chính, không còn model
  // việc nền, nên nhãn là provider thật của lượt (gói đăng ký). Quyền cũ ghi "aux" không còn khớp lượt nào: trần về mức
  // của nhóm, tức chặt hơn, không bao giờ rộng hơn.
  var PROVIDERS = [{ id: "anthropic-cli", key: "teams.auth.provider_claude" }, { id: "openai-oauth", key: "teams.auth.provider_codex" }];
  var FIXED_KEYS = ["teams.auth.fixed_server", "teams.auth.fixed_provider", "teams.auth.fixed_account",
    "teams.auth.fixed_technical"];
  // Ba mức tự quyết của trưởng nhóm (T5), đặt lên Toàn quyền của T3. Mức 2: trần tối đa vừa phải, không ngắt việc.
  // Mức 3: trần tối đa không giới hạn và được ngắt việc; lượt model vẫn theo trần của nhóm vì không provider nào được
  // Không giới hạn (D6), nên vẫn trong hạn mức gói của chủ.
  var LEVEL2_CEILINGS = { task_turns: 24, task_steps: 12, help_depth: 3, daily_turns: 200 };
  var LEVELS = [{ n: 1, key: "teams.level_1", desc: "teams.level_1_desc" },
    { n: 2, key: "teams.level_2", desc: "teams.level_2_desc" },
    { n: 3, key: "teams.level_3", desc: "teams.level_3_desc" }];
  // Sáu reaction, lý do, trục nói/im, chip, bộ chọn và trạng thái nằm ở reactions.js (bảng sáu emoji duy nhất của repo,
  // dùng chung với chat riêng; hợp đồng T2 mục 6). File này chỉ giữ tên hàm cũ làm lớp mỏng với họ class "tm".
  var JR = (typeof window !== "undefined" && window.JavisReactions) || require("./reactions.js");
  var REACTIONS = JR.EMOJI;
  var COMMENT_MAX = JR.COMMENT_MAX;
  var INPUT_MAX_PX = 132;   // khung soạn tự cao theo chữ, tối đa khoảng năm dòng
  var nextReaction = JR.nextReaction;
  // Nonce theo thao tác: thử lại sau lỗi mạng gửi đúng nonce cũ, thành công hay lỗi 4xx thì lần sau nonce mới.
  var reactNonces = JR.nonceKeeper(newClientId);

  // 0.176.0 (owner, 2026-10-16): reactions are plain emoji, like Zalo or Messenger. No reasons, no talk/silent axis,
  // no comment box: to correct an answer the owner REPLIES to that message, which reaches the assistant directly.
  // The server route still takes reasons/axis/comment (private chat uses them); this page always sends them empty.

  // Six emoji pill and the Zalo-style reaction corner come from reactions.js (shared with the main chat, 0.177.0).
  function reactBarHtml(m, cur) { return JR.barHtml(m.id, cur, { prefix: "tm" }); }

  // The latest assistant message keeps its corner visible (`last`); older ones show it on hover.
  function reactCornerHtml(m, last) {
    return JR.cornerHtml(m.id, m.reaction, { prefix: "tm", last: last, icon: ic("thumbs-up") });
  }

  // Time, reply (quote), copy and pin in one row UNDER the bubble, like the main chat (0.194.1, owner 17/10/2026: beside the
  // bubble it looked cluttered). Shown on hover (mouse); touch screens use swipe left (reply) and long press.
  function actsApi() {
    if (typeof window !== "undefined" && window.JavisActs) return window.JavisActs;
    try { return require("./chat-acts.js"); } catch (e) { return null; }
  }

  function timeHtml(m) {
    var A = actsApi();
    // Team messages carry epoch seconds; the main chat's formatter takes what `new Date` takes.
    var ms = Number(m.ts) > 0 ? (Number(m.ts) < 1e12 ? Number(m.ts) * 1000 : Number(m.ts)) : 0;
    var t = A && ms ? A.fmtTime(ms) : "";
    return t ? '<span class="tm-time" title="' + esc(A.fmtTimeFull(ms)) + '">' + esc(t) + "</span>" : "";
  }

  function hoverActsHtml(m) {
    var id = esc(m.id);
    return '<div class="tm-hacts">' + timeHtml(m) +
      '<button type="button" class="tm-hact" data-reply="' + id + '" aria-label="' + esc(tw("teams.msg_reply")) + '" title="' +
      esc(tw("teams.msg_reply")) + '">' + ic("quote") + "</button>" +
      '<button type="button" class="tm-hact" data-copy="' + id + '" aria-label="' + esc(tw("teams.copy")) + '" title="' +
      esc(tw("teams.copy")) + '">' + ic("copy") + "</button>" +
      ((m.meta || {}).decision ? "" : '<button type="button" class="tm-hact" data-decision="' + id + '" data-on="1" aria-label="' +
        esc(tw("teams.decision_pin")) + '" title="' + esc(tw("teams.decision_pin")) + '">' + ic("pin") + "</button>") + "</div>";
  }

  // Long press on a touch screen: emoji row (assistant messages) and Reply / Copy / Pin, right under the message.
  function sheetHtml(m, mine) {
    var id = esc(m.id);
    var cur = m.reaction && m.reaction.value !== "none" ? m.reaction.value : "";
    var btn = function (attr, icon, key) {
      return '<button type="button" class="tm-sheet-act" ' + attr + ">" + ic(icon) + "<span>" + esc(tw(key)) + "</span></button>";
    };
    return '<div class="tm-sheet" data-panel="' + id + '" role="dialog" aria-label="' + esc(tw("teams.msg_more")) + '">' +
      (mine ? "" : reactBarHtml(m, cur)) + '<div class="tm-sheet-acts">' +
      btn('data-reply="' + id + '"', "reply", "teams.msg_reply") + btn('data-copy="' + id + '"', "copy", "teams.copy") +
      ((m.meta || {}).decision ? "" : btn('data-decision="' + id + '" data-on="1"', "pin", "teams.decision_pin")) +
      btn('data-react-close="' + id + '"', "x", "teams.close") + "</div></div>";
  }

  // Message body. Assistant text goes through the main chat's markdown renderer and inherits its look (bold in the
  // accent colour, lists, code, tables), so the two chats read the same. Owner text stays plain like the main chat's
  // user bubble, with a reply quote block on top when the message quotes an earlier one.
  function quoteApi() {
    if (typeof window !== "undefined" && window.JavisQuote) return window.JavisQuote;
    try { return require("./chat-quote.js"); } catch (e) { return null; }
  }

  function quoteHtml(q) {
    var mm = /^([^:\n]{1,60}):\s+([\s\S]*)$/.exec(q);
    // 0.192.0: the quote carries the same quote mark as the main chat's quote chip.
    return '<div class="tm-quote"><span class="tm-quote-ico" aria-hidden="true">' + ic("quote") + "</span><span class=\"tm-quote-body\">" +
      (mm ? "<b>" + esc(mm[1]) + "</b>" + esc(mm[2]) : esc(q)).replace(/\n/g, "<br>") + "</span></div>";
  }

  // 0.192.0 (owner, 16/10/2026: "agent phản hồi ai thì phải tag vào hoặc quote lại"): an assistant's message that answers
  // another one shows that message on top, like a reply in a group chat. Tapping it goes to the message.
  function replyRefHtml(m, ctx) {
    var to = m.reply_to != null ? Number(m.reply_to) : 0;
    var t = to && ctx && ctx.byId ? ctx.byId[to] : null;
    if (!t) return "";
    var mine = t.author_kind === "owner";
    var a = mine ? null : (memberOf(ctx.members, t.author_ref) || (ctx.authors || {})[t.author_ref] || null);
    var who = mine ? tw("teams.owner") : t.author_kind === "agent" ? (a ? (a.name || a.slug) : t.author_ref) : tw("teams.system");
    return '<button type="button" class="tm-quote tm-quote-ref" data-jump="' + esc(t.id) + '" data-ts="' + esc(t.ts) + '" title="' +
      esc(tw("teams.quote_open")) + '"><span class="tm-quote-ico" aria-hidden="true">' + ic("quote") + "</span>" +
      '<span class="tm-quote-body"><b>' + esc(who) + "</b>" + esc(plainPreview(t.content, 140)) + "</span></button>";
  }

  // 0.192.0: "@Chủ nhóm" and "@Name" written by an assistant are drawn as mentions; calling the owner flags the message.
  // The words an assistant may use to call the owner ("@Chủ nhóm", "@Owner", the owner label): teams.owner_tags.
  function ownerTags() {
    return String(tw("teams.owner_tags") || "").split(",").concat([tw("teams.owner")]).map(function (x) {
      return String(x || "").trim();
    }).filter(function (x) { return x && x !== "teams.owner_tags" && x !== "teams.owner"; });
  }
  function markMentions(html, members) {
    var names = [];
    ownerTags().forEach(function (n) { names.push({ n: n, me: true }); });
    (members || []).forEach(function (m) {
      [m.name, m.slug].forEach(function (n) { n = String(n || "").trim(); if (n) names.push({ n: n, me: false }); });
    });
    names.sort(function (a, b) { return b.n.length - a.n.length; });
    var me = false;
    var rx = new RegExp("@(" + names.map(function (x) {
      return esc(x.n).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }).join("|") + ")(?![\\p{L}\\p{M}\\p{N}_])", "giu");
    // Only text between tags is touched, never an attribute or a link target.
    var out = String(html).split(/(<[^>]*>)/).map(function (part) {
      if (!part || part.charAt(0) === "<") return part;
      return part.replace(rx, function (all, name) {
        var low = name.toLowerCase();
        var isMe = names.some(function (x) { return x.me && esc(x.n).toLowerCase() === low; });
        if (isMe) me = true;
        return '<span class="tm-at' + (isMe ? " tm-at-me" : "") + '">' + all + "</span>";
      });
    }).join("");
    return { html: out, me: me };
  }

  // `open`: the owner opened this long message with "Show more" (kept across redraws of the list).
  function bodyHtml(m, mine, open) {
    var text = String(m.content == null ? "" : m.content);
    if (mine) {
      var Q = quoteApi();
      var t = Q ? Q.tach(text) : { quote: "", rest: text };
      // 0.191.0: files sent with the message show as chips; the paperclip names line stored for the team turns is not repeated.
      var files = ((m.meta || {}).files || []).filter(function (f) { return f && f.path; });
      var rest = files.length ? t.rest.replace(/(?:\n\n)?\uD83D\uDCCE [^\n]*$/, "") : t.rest;
      // A long message collapses to ten lines with "Show more", like the main chat (chat-acts.js).
      var A = actsApi();
      var long = !!(A && A.isLongText && A.isLongText(rest));
      return (t.quote ? quoteHtml(t.quote) : "") + (rest ? '<div class="tm-text utext' + (long && !open ? " clamped" : "") + '">' +
        esc(rest).replace(/\n/g, "<br>") + "</div>" + (long ? A.clampButtonHtml(!!open) : "") : "") +
        (files.length ? '<div class="tm-files">' + files.map(function (f) { return fileChipHtml(f, m.ts); }).join("") + "</div>" : "");
    }
    var md = typeof window !== "undefined" && window.mdToHtml;
    if (md) {
      // anhV: the message's own time is the version of the pictures it shows, like the main chat, so a picture the AI
      // overwrote under the same name shows the new one in a newer message instead of the browser's cached copy.
      try {
        return '<div class="tm-text msg-javis tm-mdwrap"><div class="bubble">' + md(text, brain(), m.ts ? { anhV: String(m.ts) } : undefined) +
          "</div></div>";
      }
      catch (e) { /* fall through to plain text */ }
    }
    return '<div class="tm-text">' + esc(text).replace(/\n/g, "<br>") + "</div>";
  }

  function rawUrl(path) { return "/files/raw?brain=" + q(brain()) + "&path=" + q(path); }
  // A file sent with an owner's message. A picture opens in the in-app viewer (chat-render.js lightbox, a.jv-img-link,
  // named by data-img-ten) like every other picture in the chats, and a picture that cannot load any more becomes the
  // main chat's "not available" box (jvImgGone) instead of a broken icon. `ver` (the message time) is the picture's
  // version, so a file overwritten under the same name is not served from the browser cache.
  function fileChipHtml(f, ver) {
    var img = !!f.image || /\.(png|jpe?g|gif|webp)$/i.test(String(f.path || ""));
    var url = rawUrl(f.path) + (ver ? "&v=" + q(String(ver)) : "");
    var name = f.name || f.path;
    if (img) {
      return '<a class="tm-file is-img jv-img-link" href="' + esc(url) + '" data-img-ten="' + esc(name) +
        '" target="_blank" rel="noopener" title="' + esc(tw("chat.att_zoom")) + '"><img src="' + esc(url) + '" alt="' + esc(name) +
        '" loading="lazy" onerror="jvImgGone(this)"><span>' + esc(name) + "</span></a>";
    }
    return '<a class="tm-file" href="' + esc(url) + '" target="_blank" rel="noopener" title="' + esc(name) + '">' + ic("file-text") +
      "<span>" + esc(name) + "</span></a>";
  }

  // One-line plain preview of a message for the reply bar and the quote: markdown marks and an earlier quote dropped.
  function plainPreview(text, n) {
    var Q = quoteApi();
    var s = String(text == null ? "" : text);
    if (Q) s = Q.tach(s).rest;
    // Hidden blocks (JAVIS_CARD, JAVIS_ASK... are HTML comments) never show in a preview or a quote.
    s = s.replace(/<!--[\s\S]*?-->/g, " ").replace(/<!--[\s\S]*$/, " ");
    // 0.192.0: a preview reads as text: pictures dropped, [label](path) and [[note|label]] become their label.
    s = s.replace(/!\[[^\]]*\]\([^)]*\)/g, " ").replace(/!\[\[[^\]]*\]\]/g, " ")
      .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
      .replace(/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g, function (a, t, l) { return l || t; });
    return Q ? Q.xemTruoc(s, n || 160) : s.replace(/\s+/g, " ").trim().slice(0, n || 160);
  }

  function initial(name) {
    var s = String(name || "?").trim();
    return s ? s.charAt(0).toUpperCase() : "?";
  }

  // Màu ảnh đại diện cố định theo tên (8 màu), để nhận ra người trong khung chat mà không cần đọc tên.
  function avaClass(name) {
    var s = String(name || ""), h = 0;
    for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 997;
    return "tm-ava tm-ava-c" + (h % 8);
  }

  function avaHtml(name) {
    return '<span class="' + avaClass(name) + '" aria-hidden="true">' + esc(initial(name)) + "</span>";
  }

  // Ảnh trợ lý: ĐÚNG ảnh trợ lý đang dùng (bộ vẽ JavisAvatar của trang Cộng sự, theo slug và `avatar` trong file trợ
  // lý; trợ lý chưa chọn ảnh thì bộ vẽ tự suy từ slug, giống mọi trang khác). Chưa có bộ vẽ (test dưới node) thì về chữ
  // đầu trên nền màu.
  function agentAva(m, size) {
    m = m || {};
    var A = typeof window !== "undefined" && window.JavisAvatar;
    // `avatar_seed`: tác giả cũ không còn xác nhận được nhân dạng thì ảnh suy từ chính mã của họ, không suy từ slug (slug
    // có thể đã thuộc trợ lý mới; review 4f6268bd #1).
    if (A && A.html && m.slug) {
      return '<span class="tm-face" aria-hidden="true">' + A.html({ slug: m.avatar_seed || m.slug, avatar: m.avatar || undefined },
        size || 28) +
        "</span>";
    }
    return avaHtml(m.name || m.slug);
  }

  // Gương mặt cho ảnh nhóm: dòng danh sách đã kèm `faces` và `member_count` từ server; đầu khung chat thì suy từ thành
  // viên (đang hoạt động, trưởng nhóm trước).
  function facesOf(t) {
    if (t.faces) return { faces: t.faces, count: t.member_count != null ? Number(t.member_count) : t.faces.length };
    var act = (t.members || []).filter(function (m) { return !m.status || m.status === "active"; });
    var lead = act.filter(function (m) { return m.agent_key === t.leader_key; });
    act = lead.concat(act.filter(function (m) { return m.agent_key !== t.leader_key; }));
    return { faces: act.slice(0, 4), count: act.length };
  }

  // Ảnh nhóm ghép từ ảnh thành viên: 1 người một ảnh, 2 người hai ảnh chéo, 3 người ba ảnh tam giác, từ 4 người lưới 2x2;
  // hơn 4 người thì ba ảnh và ô đếm "+N" (quá 99 ghi "99+"), như nhóm Zalo. Chưa có ai thì chữ đầu của tên nhóm.
  // Ảnh nhóm tự tải lên (0.176.0): tên ảnh do máy chủ đặt (băm + đuôi); có thì thay ảnh ghép.
  var TEN_ANH = /^[0-9a-f]{20}\.(png|jpg|webp|gif)$/;
  function teamAvatarHtml(t, box) {
    t = t || {};
    box = box || 44;
    if (typeof t.avatar_image === "string" && TEN_ANH.test(t.avatar_image)) {
      return '<span class="tm-gava tm-gava-img" style="--gava:' + box + 'px" aria-hidden="true"><img src="/avatars/' +
        esc(t.avatar_image) + '" alt="" loading="lazy" decoding="async" draggable="false"></span>';
    }
    var f = facesOf(t);
    if (!f.faces.length) return avaHtml(t.name);
    var more = f.count > 4 ? f.count - 3 : 0;
    var shown = more ? f.faces.slice(0, 3) : f.faces.slice(0, 4);
    var n = more ? 4 : shown.length;
    var size = Math.round(box * [1, 1, 0.64, 0.56, 0.5][n]);
    return '<span class="tm-gava tm-gava-' + n + '" style="--gava:' + box + 'px;--face:' + size + 'px" aria-hidden="true">' +
      shown.map(function (x) { return agentAva(x, size); }).join("") +
      (more ? '<span class="tm-gava-more">' + (more > 99 ? "99+" : "+" + more) + "</span>" : "") + "</span>";
  }

  function memberOf(members, key) {
    for (var i = 0; i < (members || []).length; i++) if (members[i].agent_key === key) return members[i];
    return null;
  }

  function nameOf(members, key) {
    var m = memberOf(members, key);
    return m ? (m.name || m.slug || key) : key;
  }

  function pad2(n) { return (n < 10 ? "0" : "") + n; }

  // Giờ ngắn cho danh sách nhóm: hôm nay "14:05", ngày khác "13/10".
  function timeShort(ts, now) {
    if (!ts) return "";
    var d = new Date(Number(ts) * 1000), n = new Date(now === undefined ? Date.now() : Number(now) * 1000);
    if (d.getFullYear() === n.getFullYear() && d.getMonth() === n.getMonth() && d.getDate() === n.getDate()) {
      return pad2(d.getHours()) + ":" + pad2(d.getMinutes());
    }
    return pad2(d.getDate()) + "/" + pad2(d.getMonth() + 1);
  }

  // ───────────── danh sách nhóm ─────────────

  function guideHtml() {
    return '<div class="tm-guide"><strong>' + esc(tw("teams.guide_title")) + "</strong><ol>" +
      ["teams.guide_1", "teams.guide_2", "teams.guide_3"].map(function (k) { return "<li>" + esc(tw(k)) + "</li>"; }).join("") +
      '</ol><button type="button" class="ws-btn tm-primary tm-new">' + ic("plus") + esc(tw("teams.create_title")) +
      "</button></div>";
  }

  function teamBadge(t) {
    var c = t.counts || {};
    if (t.status === "archived") return '<span class="tm-badge">' + esc(tw("teams.status_archived")) + "</span>";
    if (c.blocked) return '<span class="tm-badge tm-badge-owner">' + esc(tw("teams.needs_you")) + "</span>";
    if (t.status === "paused") return '<span class="tm-badge">' + esc(tw("teams.status_paused")) + "</span>";
    if (c.running) return '<span class="tm-badge tm-badge-run">' + esc(tw("teams.badge_running")) + "</span>";
    return "";
  }

  // 0.197.0 (owner, 17/10/2026: "hiện châm nổi bao nhiêu tin chưa đọc, có @ mình hay không"): the unread count of a team
  // (assistant and system messages since the owner last read it) and an @ mark when one of them calls the owner. The
  // team open on screen shows none: the owner is reading it. A muted team keeps its count, drawn grey.
  function seeing(t, activeId) {
    return t.team_id === activeId && (typeof document === "undefined" || document.visibilityState !== "hidden");
  }
  function unreadOf(t, activeId) {
    var u = t.unread || {};
    return seeing(t, activeId) ? { n: 0, at: 0 } : { n: Number(u.n) || 0, at: Number(u.at) || 0 };
  }
  function unreadHtml(t, activeId) {
    var u = unreadOf(t, activeId);
    // 0.204.0: its own class. It shared "tm-at" with the @mentions inside messages, and this round 20px badge rule
    // squeezed every mention into a circle, one letter per line.
    return (u.at ? '<span class="tm-at-badge" title="' + esc(tw("teams.calls_you")) + '" aria-label="' + esc(tw("teams.calls_you")) +
        '">@</span>' : "") +
      (u.n ? '<span class="notification-badge tm-unread' + (t.muted ? " is-muted" : "") + '" title="' +
        esc(tw("teams.unread_n", { n: u.n })) + '">' + (u.n > 99 ? "99+" : String(u.n)) + "</span>" : "");
  }

  // Dòng phụ ở đầu khung chat (0.142.0): "Bạn + N trợ lý · X điều phối". Bạn là người tạo, quản lý (người thật); điều
  // phối là một trợ lý AI. Chỉ đếm trợ lý đang hoạt động.
  function headLine(t) {
    var n = (t.members || []).filter(function (m) { return !m.status || m.status === "active"; }).length;
    var who = tw("teams.head_people", { n: n });
    return who + " · " + (t.leader_key ? tw("teams.head_leader", { name: nameOf(t.members, t.leader_key) })
      : tw("teams.no_leader_short"));
  }

  function previewText(t, members) {
    var last = t.last;
    if (!last || !last.text) return tw("teams.no_messages");
    var who = last.author_kind === "owner" ? tw("teams.you") : last.author_kind === "agent" ? (last.author || "") : "";
    return (who ? who + ": " : "") + plainPreview(last.text, 120);
  }

  // Inline name editor (list row and chat header). Enter saves, Escape cancels, leaving the box saves.
  function renameInputHtml(t) {
    return '<input class="tm-rename-input" data-rename-for="' + esc(t.team_id) + '" value="' + esc(t.name) + '" maxlength="80" ' +
      'aria-label="' + esc(tw("teams.rename")) + '" enterkeyhint="done">';
  }

  // ───────────── tag (0.195.0) ─────────────
  // Owner, 17/10/2026: "nhiều team đang triển khai cùng 1 dự án thì sẽ có thể add vào 1 tag", then "tag em làm dropdown
  // giống bên cộng sự ... cái gì mà có rồi thì tái sử dụng". So the filter is the Partners page's bar and dropdown, and
  // tags are set from the row menu with the Partners page's picker (both from tag-picker.js); tags on a row show in its
  // tooltip, as on a partner card. Tags live on the team (server cleans them: team_store.clean_tags).
  var TAG_NONE = "\u0001none";   // filter value "no tag yet", like the Partners page's TAG_NONE

  function tagKey(s) { var v = String(s == null ? "" : s); try { v = v.normalize("NFC"); } catch (e) {} return v.toLowerCase(); }

  // Every tag the listed teams carry, once (case folded), with how many teams carry it, sorted by name.
  function allTags(teams) {
    var seen = {}, out = [];
    (teams || []).forEach(function (t) {
      (t.tags || []).forEach(function (g) {
        var k = tagKey(g);
        if (!Object.prototype.hasOwnProperty.call(seen, k)) { seen[k] = { ten: g, key: k, n: 0 }; out.push(seen[k]); }
        seen[k].n++;
      });
    });
    return out.sort(function (a, b) { return a.ten.localeCompare(b.ten, "vi"); });
  }

  function hasTag(t, key) {
    return (t.tags || []).some(function (g) { return tagKey(g) === key; });
  }

  function filterTeams(teams, key) {
    if (!key) return teams || [];
    if (key === TAG_NONE) return (teams || []).filter(function (t) { return !(t.tags || []).length; });
    return (teams || []).filter(function (t) { return hasTag(t, key); });
  }

  function tagLabel(teams, key) {
    if (!key) return tw("teams.tags_all");
    if (key === TAG_NONE) return tw("ws.tag_none");
    var g = allTags(teams).filter(function (x) { return x.key === key; })[0];
    return g ? g.ten : key;
  }

  // The filter bar on top of the list: the Partners page's bar (JavisTagPicker.barHtml).
  function tagBarHtml(teams, key) {
    var TP = tagPicker();
    if (!TP) return "";
    return TP.barHtml({ label: tagLabel(teams, key), icon: !key ? "layers" : key === TAG_NONE ? "circle" : "tag",
                        canClear: !!key, pickTitle: tw("teams.tag_pick_title"), clearTitle: tw("ws.tag_clear_title") });
  }

  // Rows of the filter dropdown (JavisChatSide.menu, the same dropdown the Partners page opens).
  function tagMenuRows(teams, key, pick) {
    var tags = allTags(teams);
    var none = (teams || []).filter(function (t) { return !(t.tags || []).length; }).length;
    var rows = [
      { label: tw("teams.tags_all"), icon: "layers", right: String((teams || []).length), on: !key, run: function () { pick(""); } },
      { label: tw("ws.tag_none"), icon: "circle", right: String(none), on: key === TAG_NONE, run: function () { pick(TAG_NONE); } },
    ];
    if (tags.length) rows.push({ sep: true });
    tags.forEach(function (g) {
      rows.push({ label: g.ten, icon: "tag", right: String(g.n), on: key === g.key, run: function () { pick(g.key); } });
    });
    return rows;
  }

  // Rows of the "Tag" picker in a team's row menu: every tag in the list plus the team's own, checked when it has it.
  function tagPickRows(team, teams) {
    var mine = {}, out = [];
    (team.tags || []).forEach(function (g) { mine[tagKey(g)] = g; });
    var seen = {};
    allTags(teams).forEach(function (g) { seen[g.key] = 1; out.push({ ten: g.ten, key: g.key, on: !!mine[g.key] }); });
    Object.keys(mine).forEach(function (k) { if (!seen[k]) out.push({ ten: mine[k], key: k, on: true }); });
    return out.sort(function (a, b) { return a.ten.localeCompare(b.ten, "vi"); });
  }

  function tagPicker() {
    if (typeof window !== "undefined" && window.JavisTagPicker) return window.JavisTagPicker;
    try { return require("./tag-picker.js"); } catch (e) { return null; }
  }

  // The team the owner worked in last (0.195.0): the highest `owner_at` (sent a message or opened it, on any device).
  // Teams never touched since this version fall back to their latest message, then their last update.
  function lastWorkedTeam(teams) {
    var best = null, bestAt = -1;
    (teams || []).forEach(function (t) {
      var at = Number(t.owner_at) || 0;
      var rank = at ? 2e12 + at : Number((t.last || {}).ts || t.updated_at || 0);
      if (rank > bestAt) { bestAt = rank; best = t; }
    });
    return best;
  }

  // `menuId`: the team whose menu is open (the "..." button, long press on a phone, right click on a computer): Pin or
  // Unpin, Rename, Delete. `renaming`: the team whose name is being edited in place.
  function teamListHtml(teams, activeId, now, menuId, renaming, tagMode) {
    if (!teams || !teams.length) return guideHtml();
    return teams.map(function (t) {
      var on = t.team_id === activeId;
      var last = t.last || {};
      var pinned = !!t.pinned_at;
      var id = esc(t.team_id);
      if (renaming === t.team_id) {
        return '<div class="tm-team-wrap"><div class="tm-team tm-team-edit">' + teamAvatarHtml(t, 44) + renameInputHtml(t) +
          "</div></div>";
      }
      var pin = pinned ? '<span class="tm-pinned" title="' + esc(tw("teams.pinned")) + '" aria-label="' +
        esc(tw("teams.pinned")) + '">' + ic("pin") + "</span>" : "";
      var mute = t.muted ? '<span class="tm-muted" title="' + esc(tw("teams.muted")) + '" aria-label="' +
        esc(tw("teams.muted")) + '">' + ic("bell-off") + "</span>" : "";
      var unread = unreadHtml(t, activeId);
      var open = menuId === t.team_id;
      // 0.195.0: "Tag" opens the Partners page's tag picker right in this menu (tagMode), like a partner's row menu.
      var picker = open && tagMode === t.team_id && tagPicker();
      var menu = !open ? "" : picker ? '<div class="tm-row-menu tm-tag-menu" role="menu" aria-label="' + esc(tw("ws.tag_menu")) + '">' +
        // Suggestions come from EVERY team, not only those the filter shows.
        picker.pickerHtml(tagPickRows(t, (S && S.teams && S.teams.length ? S.teams : teams))) + "</div>" : '<div class="tm-row-menu" role="menu" aria-label="' + esc(tw("teams.row_menu")) + '">' +
        '<button type="button" role="menuitem" data-pin-team="' + id + '" data-on="' + (pinned ? "0" : "1") + '">' + ic("pin") +
        esc(tw(pinned ? "teams.unpin_team" : "teams.pin_team")) + "</button>" +
        '<button type="button" role="menuitem" data-tag-team="' + id + '">' + ic("tag") + esc(tw("ws.tag_menu")) + "</button>" +
        // 0.197.0: notifications per team, so the owner follows only the teams they choose.
        '<button type="button" role="menuitem" data-mute-team="' + id + '" data-on="' + (t.muted ? "0" : "1") + '">' +
        ic(t.muted ? "bell" : "bell-off") + esc(tw(t.muted ? "teams.unmute_team" : "teams.mute_team")) + "</button>" +
        '<button type="button" role="menuitem" data-rename-team="' + id + '">' + ic("pencil") + esc(tw("teams.rename")) + "</button>" +
        // 0.200.0: the whole team as one file (server/team_bundle.py).
        '<button type="button" role="menuitem" data-share-team="' + id + '">' + ic("share-2") + esc(tw("teams.share_team")) + "</button>" +
        '<button type="button" role="menuitem" class="tm-danger" data-delete-team="' + id + '">' + ic("trash-2") +
        esc(tw("teams.delete_team")) + "</button></div>";
      var tagTip = (t.tags || []).length ? ' title="' + esc(t.name + "\n" + tw("teams.tags_title") + ": " + t.tags.join(", ")) + '"' : "";
      return '<div class="tm-team-wrap' + (open ? " is-menu" : "") + '"><button type="button" class="tm-team' +
        (unread ? " has-unread" : "") + '" data-team="' + id + '"' + (on ? ' aria-current="true"' : "") + tagTip + ">" +
        teamAvatarHtml(t, 44) + (unread ? '<span class="tm-mini-unread">' + unread + "</span>" : "") +
        '<span class="tm-team-main"><span class="tm-team-top"><span class="tm-team-name">' + esc(t.name) +
        "</span>" + pin + mute + '<span class="tm-team-time">' + esc(timeShort(last.ts || t.updated_at, now)) + "</span></span>" +
        '<span class="tm-team-bottom"><span class="tm-team-sub">' + esc(previewText(t)) + "</span>" + teamBadge(t) + unread +
        "</span></span></button>" +
        '<button type="button" class="tm-row-more" data-row-menu="' + id + '" aria-haspopup="menu" aria-expanded="' +
        (open ? "true" : "false") + '" aria-label="' + esc(tw("teams.row_menu")) + '" title="' + esc(tw("teams.row_menu")) + '">' +
        ic("ellipsis") + "</button>" + menu + "</div>";
    }).join("");
  }

  // ───────────── tin ─────────────

  // Kết cục từng lượt trả lời của một tin chủ nhóm (0.142.0): chờ, đang trả lời, lỗi kèm lý do và Thử lại. "Đã trả lời"
  // không hiện (câu trả lời đã nằm ngay dưới); chỉ báo khi còn chờ hay khi hỏng, để không có tin nào im lặng.
  var REPLY_WHY = { engine_unavailable: "teams.reply.why.engine_unavailable", engine: "teams.reply.why.engine",
    cap: "teams.reply.why.cap", busy: "teams.reply.why.busy", team_paused: "teams.reply.why.team_paused",
    member_left: "teams.reply.why.member_left", restart: "teams.reply.why.restart",
    interrupted: "teams.reply.why.interrupted", internal: "teams.reply.why.internal",
    leader_changed: "teams.reply.why.leader_changed", superseded: "teams.reply.why.superseded",
    lease_lost: "teams.reply.why.lease_lost",
    timeout: "teams.reply.why.timeout", auth: "teams.reply.why.auth", no_leader: "teams.reply.why.no_leader",
    server_ceiling: "teams.reply.why.server_ceiling" };
  var STUCK_QUEUED_S = 600;   // khớp team_store.STUCK_QUEUED_S: chờ lâu hơn thì cho Thử lại
  var LEADER_SLOT = "__leader__";   // khớp team_runner.LEADER_SLOT: tin thường gửi lúc nhóm chưa có điều phối

  // Thao tác xử lý theo từng loại lỗi (0.142.0), ngoài nút Thử lại: lỗi model hay đăng nhập thì mở trợ lý để đổi model
  // hoặc mở trang Models; hết lượt thì mở giới hạn của nhóm; chưa có hay mất điều phối thì mở danh sách thành viên.
  function replyActions(x, ctx) {
    var out = [];
    var slug = (memberOf(ctx.members, x.agent_key) || {}).slug || "";
    if (x.reason === "auth") out.push({ act: "models", key: "teams.reply.act.models" });
    if ((x.reason === "engine" || x.reason === "engine_unavailable" || x.reason === "timeout" || x.reason === "auth") && slug) {
      out.push({ act: "agent", key: "teams.reply.act.agent", slug: slug });
    }
    if (x.reason === "cap") out.push({ act: "limits", key: "teams.reply.act.limits" });
    if (x.reason === "no_leader" || (x.reason === "member_left" && ctx.leaderKey === x.agent_key) ||
        x.reason === "leader_changed") {
      out.push({ act: "leader", key: "teams.reply.act.leader" });
    }
    if (x.reason === "team_paused") out.push({ act: "resume", key: "teams.reply.act.resume" });
    return out.map(function (a) {
      return '<button type="button" class="ws-btn tm-reply-act" data-reply-act="' + esc(a.act) + '"' +
        (a.slug ? ' data-slug="' + esc(a.slug) + '"' : "") + ">" + esc(tw(a.key)) + "</button>";
    }).join("");
  }

  function replyStatusHtml(m, ctx) {
    var rows = (m.replies || []).filter(function (x) { return x.status !== "done"; });
    if (!rows.length) return "";
    var retrying = (ctx && ctx.retrying) || {};
    return '<div class="tm-replies">' + rows.map(function (x) {
      var slot = x.agent_key === LEADER_SLOT;
      // Người đã rời nhóm không còn trong `members`: tra sổ tác giả (giữ tên theo agent_key) trước khi rơi về mã.
      var mm = memberOf(ctx.members, x.agent_key) || (ctx.authors || {})[x.agent_key];
      var who = slot ? tw("teams.reply.leader_slot") : (mm && (mm.name || mm.slug)) || x.agent_key;
      var face = slot ? "" : agentAva(memberOf(ctx.members, x.agent_key) || (ctx.authors || {})[x.agent_key] || { name: who }, 20);
      var busy = retrying[m.id + "|" + x.agent_key];
      var retryBtn = '<button type="button" class="ws-btn tm-reply-retry" data-retry="' + esc(m.id) + '" data-retry-key="' +
        esc(x.agent_key) + '"' + (busy ? " disabled" : "") + ">" + ic("rotate-cw") +
        esc(tw(busy ? "teams.reply.retrying" : "teams.reply.retry")) + "</button>";
      if (x.status === "error") {
        var why = REPLY_WHY[x.reason] || "teams.reply.why.unknown";
        var detail = x.detail && x.reason !== "timeout" && x.reason !== "no_leader"
          ? '<span class="tm-reply-detail">' + esc(String(x.detail).slice(0, 200)) + "</span>" : "";
        var whyText = x.reason === "timeout" ? tw(why, { n: x.detail || "?" }) : tw(why);
        // Rời nhóm thì không thử lại được; hết lượt hôm nay thì Thử lại chỉ chạy được sau khi mở thêm giới hạn.
        var canRetry = x.reason !== "member_left";
        return '<div class="tm-reply tm-reply-error" role="status">' + face + '<span class="tm-reply-main"><b>' + esc(who) +
          "</b> " + esc(tw(slot ? "teams.reply.error_slot" : "teams.reply.error")) + ": " + esc(whyText) + detail + "</span>" +
          '<span class="tm-reply-acts">' + replyActions(x, ctx) + (canRetry ? retryBtn : "") + "</span></div>";
      }
      var answering = x.status === "running" && x.reason === "answering";
      var waiting = x.status === "running" && x.reason === "waiting_busy";
      var stuck = x.status === "queued" && x.updated_at && (Date.now() / 1000 - Number(x.updated_at)) > STUCK_QUEUED_S;
      if (stuck) {
        return '<div class="tm-reply tm-reply-error" role="status">' + face + '<span class="tm-reply-main"><b>' + esc(who) +
          "</b> " + esc(tw("teams.reply.stuck")) + '</span><span class="tm-reply-acts">' + retryBtn + "</span></div>";
      }
      var label = answering ? tw("teams.reply.answering") : waiting ? (x.detail ? tw("teams.reply.waiting_busy_in",
        { team: x.detail }) : tw("teams.reply.waiting_busy")) : tw("teams.reply.queued");
      return '<div class="tm-reply tm-reply-' + (answering ? "answering" : "queued") + '" role="status">' + face +
        '<span class="tm-reply-main"><b>' + esc(who) + "</b> " + esc(label) +
        '<span class="tm-dots" aria-hidden="true"><i></i><i></i><i></i></span></span></div>';
    }).join("") + "</div>";
  }

  function messageHtml(m, ctx) {
    ctx = ctx || {};
    var meta = m.meta || {};
    var open = ctx.picker !== undefined && ctx.picker !== null && Number(ctx.picker) === Number(m.id);
    var hit = ctx.jumped !== undefined && ctx.jumped !== null && Number(ctx.jumped) === Number(m.id);
    if (m.author_kind !== "owner" && m.author_kind !== "agent" && meta.kind === "approval_request" && meta.approval) {
      return approvalCardHtml(m);
    }
    if (m.author_kind !== "owner" && m.author_kind !== "agent" && meta.kind === "mandate_opportunity" && meta.opportunity) {
      return opportunityCardHtml(m);
    }
    if (m.author_kind !== "owner" && m.author_kind !== "agent" && meta.kind === "acceptance_review" && meta.acceptance) {
      return acceptanceCardHtml(m);
    }
    if (m.author_kind !== "owner" && m.author_kind !== "agent") {
      return '<div class="tm-sys' + (hit ? " tm-msg-hit" : "") + '" data-mid="' + esc(m.id) + '">' +
        esc(m.content).replace(/\n/g, "<br>") + "</div>";
    }
    var mine = m.author_kind === "owner";
    // Tác giả tra theo thành viên đang hoạt động rồi tới sổ tác giả (cả người đã rời): tin cũ giữ đúng tên và ảnh.
    var author = mine ? null : (memberOf(ctx.members, m.author_ref) || (ctx.authors || {})[m.author_ref] || null);
    var who = mine ? tw("teams.owner") : author ? (author.name || author.slug || m.author_ref) : m.author_ref;
    var head = [];
    if (!mine) head.push('<span class="tm-who">' + esc(who) + "</span>");
    if (!mine && meta.role && ROLE_KEY[meta.role]) head.push('<span class="tm-role">' + esc(tw(ROLE_KEY[meta.role])) + "</span>");
    if (m.task_id) {
      var title = (ctx.taskTitles || {})[m.task_id] || m.task_title || m.task_id;
      head.push('<button type="button" class="tm-tag" data-task="' + esc(m.task_id) + '">' + ic("list-todo") +
        '<span class="tm-tag-text">' + esc(tw("teams.job_tag", { title: title })) + "</span></button>");
    } else if (mine && meta.as_job) {
      head.push('<span class="tm-tag tm-tag-new">' + ic("list-todo") + esc(tw("teams.as_job")) + "</span>");
    }
    // 0.357.0: a job Javis Core gave the team on the owner's behalf (javis_team op=dispatch, issue #826).
    if (mine && meta.via_core) head.push('<span class="tm-role">' + esc(tw("teams.via_core")) + "</span>");
    if (meta.job_result) head.push('<span class="tm-result">' + esc(tw("teams.job_result")) + "</span>");
    var late = !mine && LATE.indexOf(meta.status) >= 0;
    var body = bodyHtml(m, mine, !!(ctx.unclamped && ctx.unclamped[m.id]));
    var asksMe = false;
    if (!mine && m.author_kind === "agent") {
      var mk = markMentions(body, ctx.members);
      body = replyRefHtml(m, ctx) + mk.html;
      asksMe = mk.me || !!meta.asks_owner;
      if (asksMe) head.push('<span class="tm-asks">' + ic("at-sign") + esc(tw("teams.asks_you")) + "</span>");
    }
    // "Xong" là bình thường nên không hiện; chỉ báo khi câu trả lời KHÔNG được áp dụng.
    var lateLine = late ? '<div class="tm-late">' + ic("triangle-alert") + esc(tw(STATUS_KEY[meta.status])) + "</div>" : "";
    var notes = (meta.notes || []).map(function (n) { return '<div class="tm-note-line">' + esc(n) + "</div>"; }).join("");
    // "Sao em không trả lời?": máy chủ chỉ GỢI Ý quyết định im gần nhất (T3 phần J); bấm mở lịch sử quyết định để sửa.
    if (mine && meta.judge_hint && meta.judge_hint.agent_key) {
      var hm = memberOf(ctx.members, meta.judge_hint.agent_key);
      notes += '<button type="button" class="tm-note-line tm-judge-hint" data-judge-hint="' + esc(meta.judge_hint.agent_key) +
        '">' + esc(tw("judge.hint", { name: hm ? (hm.name || hm.slug) : meta.judge_hint.agent_key })) + "</button>";
    }
    var prop = "";
    if (meta.proposal && meta.proposal.title) {
      // T3: trạng thái thẻ do máy chủ ghi (mọi tab thấy). Bỏ qua là bác đề xuất (-0.4 cho trợ lý đề xuất), chỉ hiện sau 200.
      var pst = meta.proposal_status === "accepted" ? tw("teams.proposal_accepted")
        : meta.proposal_status === "rejected" ? tw("teams.proposal_rejected") : "";
      prop = '<div class="tm-proposal"><div>' + esc(tw("teams.proposal", { name: who, title: meta.proposal.title })) + "</div>" +
        (pst ? '<div class="tm-proposal-state">' + esc(pst) + "</div>"
          : '<div class="tm-actions"><button type="button" class="ws-btn tm-primary" data-accept="' + esc(m.id) + '">' +
            esc(tw("teams.proposal_create")) + '</button><button type="button" class="ws-btn" data-skip="' + esc(m.id) + '">' +
            esc(tw("teams.proposal_skip")) + "</button></div>") + "</div>";
    }
    // Pinned decision: the label is the unpin button. Not pinned yet: Pin sits in the hover actions and the long-press sheet.
    var decision = meta.decision ? '<button type="button" class="tm-decision" data-decision="' + esc(m.id) + '" data-on="0" title="' +
      esc(tw("teams.decision_unpin")) + '">' + ic("pin") + esc(tw("teams.decision_pinned")) + "</button>" : "";
    // Reactions of the leader and members: read-only chips with the assistant's name (T2 contract 5).
    var foot = decision + JR.agentChipsHtml(m.agent_reactions, { prefix: "tm" });
    var corner = mine ? "" : reactCornerHtml(m, ctx.lastAgent !== undefined && ctx.lastAgent !== null &&
      Number(ctx.lastAgent) === Number(m.id));
    var cls = "tm-msg" + (mine ? " tm-msg-owner" : " tm-msg-agent") + (late ? " tm-msg-late" : "") + (asksMe ? " tm-msg-asks" : "") +
      (meta.job_result ? " tm-msg-result" : "") + (hit ? " tm-msg-hit" : "") + (open ? " is-sheet" : "");
    var bubble = '<div class="tm-bubble">' + (head.length ? '<div class="tm-head">' + head.join("") + "</div>" : "") +
      body + lateLine + notes + prop + (foot ? '<div class="tm-foot">' + foot + "</div>" : "") + corner + "</div>";
    // The assistant's picture opens that assistant's settings right here (name, role, model, prompt, skills).
    var face = "";
    if (!mine) {
      var slug = author && !author.avatar_seed ? author.slug : "";
      face = slug ? '<button type="button" class="tm-face-btn" data-agent-edit="' + esc(slug) + '" aria-label="' +
        esc(tw("teams.agent_settings", { name: who })) + '" title="' + esc(tw("teams.agent_settings", { name: who })) + '">' +
        agentAva(author, 28) + "</button>" : agentAva(author || { name: who }, 28);
    }
    // The bubble and its action row stack in one column, so the row sits right under the bubble on its side.
    var col = '<div class="tm-col">' + bubble + hoverActsHtml(m) + "</div>";
    return '<div class="' + cls + '" data-mid="' + esc(m.id) + '">' +
      (mine ? col : face + col) + (open ? sheetHtml(m, mine) : "") + "</div>" +
      (mine ? replyStatusHtml(m, ctx) : "");
  }

  // ───────────── việc ─────────────

  // Việc bị chặn: MỘT nút giải quyết theo lý do (T5). Hết lượt thì "Cho thêm lượt" (nâng đúng giới hạn rồi chạy tiếp),
  // lỗi hay không làm ra gì mới thì Thử lại, bị dừng giữa chừng thì Làm tiếp, chưa có trưởng nhóm thì mở chỗ chọn.
  function blockedAction(kind) {
    if (kind === "cap_reached") return { act: "extend", key: "teams.act.extend" };
    // 0.436.0: auto_retry waits for its own retry time; the same button runs it now.
    if (kind === "failed" || kind === "no_progress" || kind === "auto_retry") return { act: "retry", key: "teams.act.retry" };
    if (kind === "interrupted") return { act: "retry", key: "teams.act.continue" };
    if (kind === "no_leader") return { act: "leader", key: "teams.pick_leader" };
    if (kind === "agent_busy_long") return { act: "resume", key: "teams.resume" };
    // 0.207.0: waiting for an approval: the card in the chat decides, this button only shows it. Rejected or expired:
    // the owner edits the job to give a new direction (cancel stays next to it).
    if (kind === "waiting_user") return { act: "view", key: "teams.ap.show" };
    if (kind === "rejected" || kind === "approval_expired") return { act: "amend", key: "teams.amend" };
    // 0.209.0: waiting for the owner's acceptance: the card decides; out of fix rounds: edit the job for a new try.
    if (kind === "acceptance_review") return { act: "view", key: "teams.acc.show" };
    if (kind === "acceptance_failed") return { act: "amend", key: "teams.amend" };
    return null;
  }

  function blockedButtonHtml(t) {
    var a = blockedAction(t.block_kind || "failed");
    if (!a) return "";
    var label = esc(tw(a.key));
    if (a.act === "extend") return '<button type="button" class="ws-btn tm-primary" data-extend="' + esc(t.id) + '">' + label + "</button>";
    if (a.act === "leader") return '<button type="button" class="ws-btn tm-primary" data-open-team="1">' + label + "</button>";
    if (a.act === "view") return '<button type="button" class="ws-btn tm-primary" data-view-task="' + esc(t.id) + '">' + label + "</button>";
    if (a.act === "amend") return '<button type="button" class="ws-btn tm-primary" data-amend="' + esc(t.id) + '">' + label + "</button>";
    return '<button type="button" class="ws-btn tm-primary" data-unblock="' + esc(t.id) + '" data-action="' + a.act + '">' +
      label + "</button>";
  }

  function blockedCardHtml(t) {
    var kind = t.block_kind || "failed";
    return '<div class="tm-jcard"><div class="tm-jcard-text"><strong class="tm-qtitle">' + esc(t.title) + "</strong>" +
      '<span class="tm-qwhy">' + esc(t.block_reason || tw(BLOCK_KEY[kind] || BLOCK_KEY.failed)) + "</span></div>" +
      '<span class="tm-actions">' + blockedButtonHtml(t) +
      // 0.209.0 review: criteria can be set on a stopped job too (acceptance_failed re-checks without redoing the work).
      (kind === "acceptance_review" || kind === "acceptance_checking" ? "" :
        '<button type="button" class="ws-btn" data-acc-edit="' + esc(t.id) + '">' + esc(tw("teams.acc.set")) + "</button>") +
      '<button type="button" class="ws-btn" data-cancel="' + esc(t.id) + '">' + esc(tw("teams.cancel")) + "</button></span></div>";
  }

  function runningRowHtml(t, withView) {
    return '<div class="tm-qrow tm-jrun"><span class="tm-spin" aria-hidden="true">' + ic("loader") + "</span>" +
      '<span class="tm-qtitle">' + esc(tw("teams.doing", { title: t.title })) + '</span><span class="tm-actions">' +
      (withView ? '<button type="button" class="ws-btn" data-view-task="' + esc(t.id) + '">' + esc(tw("teams.view_msgs")) + "</button>" : "") +
      '<button type="button" class="ws-btn" data-amend="' + esc(t.id) + '">' + esc(tw("teams.amend")) + "</button>" +
      (withView ? '<button type="button" class="ws-btn" data-acc-edit="' + esc(t.id) + '">' + esc(tw("teams.acc.set")) + "</button>" : "") +
      '<button type="button" class="ws-btn" data-cancel="' + esc(t.id) + '">' + esc(tw("teams.cancel")) + "</button></span></div>";
  }

  // 0.209.0: acceptance criteria of a job, one per line (parsed by parseCriteria):
  //   file: path | contains: path | min chars | phrase, phrase | json: path | key, key | cmd: command | confirm: path
  function parseCriteria(text) {
    var out = [], bad = [];
    String(text || "").split("\n").forEach(function (line) {
      var l = line.trim();
      if (!l) return;
      var i = l.indexOf(":");
      var k = i > 0 ? l.slice(0, i).trim().toLowerCase() : "";
      var parts = (i > 0 ? l.slice(i + 1) : "").split("|").map(function (x) { return x.trim(); });
      var list = function (x) { return String(x || "").split(",").map(function (y) { return y.trim(); }).filter(Boolean); };
      if (k === "file" && parts[0]) out.push({ kind: "file_exists", path: parts[0] });
      else if (k === "contains" && parts[0]) out.push({ kind: "file_contains", path: parts[0], min_chars: Number(parts[1]) || 0, must_contain: list(parts[2]) });
      else if (k === "json" && parts[0]) out.push({ kind: "json_keys", path: parts[0], keys: list(parts[1]) });
      else if (k === "cmd" && parts[0]) out.push({ kind: "command_ok", command: l.slice(i + 1).trim() });
      else if (k === "confirm-message") out.push({ kind: "owner_confirm", target: "message" });
      else if (k === "confirm") out.push(parts[0] ? { kind: "owner_confirm", path: parts[0] } : { kind: "owner_confirm" });
      else bad.push(l);
    });
    return { criteria: out, bad: bad };
  }

  function accEditorHtml(t, view) {
    if (!view || view.accEdit !== t.id) return "";
    return '<form class="tm-form tm-acc-form" data-acc-task="' + esc(t.id) + '" onsubmit="return false">' +
      // for= binds the textarea; without it the (i) button, first in the label, would become the label's control.
      '<label class="tm-field" for="tm-acc-' + esc(t.id) + '"><span>' + esc(tw("teams.acc.criteria")) + infoBtn() + '</span>' +
      '<textarea id="tm-acc-' + esc(t.id) + '" name="tm-acc-text" rows="4"></textarea></label>' +
      infoBody('<div class="tm-sub">' + esc(tw("teams.acc.help")) + "</div>") +
      '<div class="tm-sub">' + esc(tw("teams.acc.replace")) + "</div>" +
      '<label class="tm-field tm-cap"><span>' + esc(tw("teams.acc.rounds")) + '</span><input type="number" min="0" max="5" name="tm-acc-rounds" value="2"></label>' +
      '<div class="tm-actions"><button type="button" class="ws-btn tm-primary tm-acc-save">' + esc(tw("teams.save")) +
      '</button><button type="button" class="ws-btn" data-acc-edit="">' + esc(tw("teams.cancel")) + "</button></div></form>";
  }

  // The owner's acceptance card: what was checked on the product, Accept or Send back.
  var ACC_V_KEY = { pass: "teams.acc.v.pass", fail: "teams.acc.v.fail", unknown: "teams.acc.v.unknown" };
  function acceptanceCardHtml(m) {
    var a = (m.meta || {}).acceptance || {};
    var rows = (a.last || []).map(function (x) {
      var c = (a.criteria || [])[x.idx] || {};
      var what = c.label || c.path || c.command || c.kind || "";
      var ev = x.evidence || {};
      return "<li><b>" + esc(tw(ACC_V_KEY[x.verdict] || ACC_V_KEY.unknown)) + "</b> · " + esc(what) +
        (ev.detail ? " · " + esc(ev.detail) : "") + (ev.sha256 ? ' <code>' + esc(String(ev.sha256).slice(0, 12)) + "</code>" : "") + "</li>";
    }).join("");
    var waiting = a.status === "review";
    return '<div class="tm-ap tm-acc tm-ap-' + esc(a.status || "") + '" data-mid="' + esc(m.id) + '" role="group"><div class="tm-ap-head">' +
      ic("check") + "<b>" + esc(tw("teams.acc.title")) + "</b></div>" + '<ul class="tm-ap-calls">' + rows + "</ul>" +
      ((a.stale || []).length ? '<div class="tm-note-line">' + esc(tw("teams.acc.stale")) + "</div>" : "") +
      (waiting ? '<div class="tm-actions"><button type="button" class="ws-btn tm-primary" data-acc-decide="accept" data-acc="' +
        esc(a.task_id) + '" data-acc-rev="' + esc(a.revision) + '" data-acc-round="' + esc(a.rounds) +
        '" data-acc-contract="' + esc(a.contract_version || "") + '" data-acc-manifest="' + esc(a.output_manifest_hash || "") + '">' + esc(tw("teams.acc.accept")) +
        '</button><button type="button" class="ws-btn" data-acc-decide="reject" data-acc="' + esc(a.task_id) + '" data-acc-rev="' +
        esc(a.revision) + '" data-acc-round="' + esc(a.rounds) + '" data-acc-contract="' + esc(a.contract_version || "") +
        '" data-acc-manifest="' + esc(a.output_manifest_hash || "") + '">' + esc(tw("teams.acc.reject")) + "</button></div>" :
        '<div class="tm-ap-state">' + esc(tw(a.status === "accepted" ? "teams.acc.st.accepted" : "teams.acc.st.closed")) + "</div>") +
      "</div>";
  }

  function acceptanceDecisionPayload(dataset, decision, note) {
    var body = { decision: decision, note: note || "", revision: Number(dataset.accRev) || null,
      round: Number(dataset.accRound) || null, contract_version: Number(dataset.accContract) || null,
      output_manifest_hash: dataset.accManifest || "" };
    var signature = JSON.stringify(body);
    if (!dataset.accDecisionKey || dataset.accDecisionBody !== signature) {
      dataset.accDecisionKey = newClientId();
      dataset.accDecisionBody = signature;
    }
    body.decision_key = dataset.accDecisionKey;
    return body;
  }

  function qualityPolicyPayload(input) {
    var mode = input.limit_migration || "";
    var value = input.reference_usd;
    var empty = value === "" || value === null || value === undefined;
    var amount = empty ? null : Number(value);
    if ((input.enabled && mode !== "observe" && mode !== "retain") ||
        typeof value === "boolean" || (!empty && (!Number.isFinite(amount) || amount < 0))) return { ok: false };
    var body = { enabled: !!input.enabled, reference_usd: amount };
    if (mode) body.limit_migration = mode;
    return { ok: true, body: body };
  }

  function qualityTemplatePayload(template, version, criteria) {
    template = template || {};
    return { expected_version: Number(version), criteria: criteria,
      expected_outputs: template.expected_outputs || [], source_refs: template.source_refs || [],
      fix_rounds: template.fix_rounds === undefined ? 2 : template.fix_rounds };
  }

  function qualityPolicyHtml(team) {
    var p = team.quality_policy || {};
    var template = team.acceptance_template;
    var lines = template ? (template.criteria || []).map(function (c) {
      if (c.kind === "owner_confirm") return c.target === "message" ? "confirm-message:" : "confirm: " + (c.path || "");
      if (c.kind === "file_exists") return "file: " + c.path;
      if (c.kind === "file_contains") return "contains: " + c.path + " | " + (c.min_chars || 0) + " | " + (c.must_contain || []).join(", ");
      if (c.kind === "json_keys") return "json: " + c.path + " | " + (c.keys || []).join(", ");
      if (c.kind === "command_ok") return "cmd: " + c.command;
      return "";
    }).join("\n") : "confirm-message:";
    return '<section class="tm-sec"><div class="tm-qhead">' + esc(tw("teams.quality.title")) + infoBtn() + "</div>" +
      infoBody(esc(tw("teams.quality.explain"))) +
      '<form class="tm-form tm-quality-form" onsubmit="return false"><label class="tm-radio"><input type="checkbox" class="tm-quality-enabled"' +
      (p.enabled ? " checked" : "") + "><span>" + esc(tw("teams.quality.enable")) + "</span></label>" +
      '<label class="tm-field"><span>' + esc(tw("teams.quality.limit_choice")) + '</span><select class="tm-quality-migration">' +
      [["", "teams.quality.choose"], ["observe", "teams.quality.observe"], ["retain", "teams.quality.retain"]].map(function (r) {
        var selected = p.limit_migration_selected ? p.limit_migration : "";
        return '<option value="' + r[0] + '"' + (selected === r[0] ? " selected" : "") + ">" + esc(tw(r[1])) + "</option>";
      }).join("") + "</select></label>" +
      '<label class="tm-field"><span>' + esc(tw("teams.quality.reference")) + '</span><input class="tm-quality-reference" type="number" min="0" step="any" value="' +
      esc(p.reference_usd == null ? "" : p.reference_usd) + '"></label><button type="button" class="ws-btn tm-quality-save">' +
      esc(tw("teams.save")) + "</button></form>" +
      '<details><summary>' + esc(tw("teams.quality.template")) + '</summary><form class="tm-form tm-template-form" data-template-version="' +
      esc(template ? template.version : 0) + '" onsubmit="return false"><label class="tm-field"><span>' +
      esc(tw("teams.quality.criteria")) + infoBtn() + "</span>" + infoBody(esc(tw("teams.acc.help"))) +
      '<textarea class="tm-template-criteria" rows="5">' + esc(lines) + '</textarea></label><button type="button" class="ws-btn tm-template-save">' +
      esc(tw("teams.save")) + "</button></form></details></section>";
  }

  function qualityUsageHtml(u, reference) {
    if (!u) return "";
    var money = u.money || {}, coverage = u.coverage || {};
    var known = function (v) { return v !== null && v !== undefined && Number.isFinite(Number(v)); };
    var val = function (v) { return known(v) ? esc(v) : esc(tw("teams.quality.unknown")); };
    var rows = [["teams.quality.reported", money.reported_usd], ["teams.quality.estimated", money.estimated_usd],
      ["teams.quality.subscription", money.subscription_equivalent_usd]];
    var h = '<section class="tm-sec"><div class="tm-qhead">' + esc(tw("teams.quality.usage")) + infoBtn() + "</div>" +
      infoBody(esc(tw("teams.quality.usage_explain"))) +
      "<div>" + esc(tw("teams.quality.attempts")) + ": " + val(u.attempts) + " · " + esc(tw("teams.quality.requests")) + ": " + val(u.requests) + "</div>" +
      "<div>" + esc(tw("teams.quality.tokens")) + ": " + val(u.tokens_in) + " / " + val(u.tokens_out) + "</div>";
    rows.forEach(function (r) { h += "<div>" + esc(tw(r[0])) + ": " + (known(r[1]) ? esc(Number(r[1]).toFixed(4)) + " USD" : val(null)) + "</div>"; });
    if (coverage.status !== "observed") h += '<div class="tm-note-line">' + esc(tw("teams.quality.partial")) + "</div>";
    var measured = (known(money.reported_usd) ? Number(money.reported_usd) : 0) +
      (known(money.estimated_usd) ? Number(money.estimated_usd) : 0);
    if (known(reference) && measured > Number(reference)) h += '<div class="tm-note-line">' + esc(tw("teams.quality.above_reference")) + "</div>";
    var roles = u.roles || {};
    if (Object.keys(roles).length) h += '<details><summary>' + esc(tw("teams.quality.roles")) + "</summary>" +
      Object.keys(roles).map(function (role) {
        var r = roles[role];
        return "<div>" + esc(tw(TURN_ROLE_KEY[role] || "teams.quality.shared")) + ": " + val(r.attempts) + " · " +
          val(r.tokens_in) + " / " + val(r.tokens_out) + "</div>";
      }).join("") + "</details>";
    return h + "</section>";
  }

  function taskQualityHtml(detail) {
    if (!detail) return "";
    var acceptance = detail.acceptance || {};
    var stale = (acceptance.status === "passed" || acceptance.status === "accepted") && acceptance.completion_valid === false;
    var unverified = detail.task && detail.task.status === "done" &&
      (!detail.acceptance || acceptance.verification === "legacy_unverified");
    return '<details class="tm-task-quality"><summary>' + esc(tw("teams.quality.task_usage")) + "</summary>" +
      (unverified ? '<div class="tm-note-line">' + esc(tw("teams.quality.unverified")) + "</div>" : "") +
      (stale ? '<div class="tm-note-line">' + esc(tw("teams.quality.stale")) + "</div>" : "") +
      qualityUsageHtml(detail.usage) + "</details>";
  }

  // Dải việc ở đầu khung chat: việc đang làm (một dòng) và việc đang chờ chủ (thẻ có nút giải quyết).
  function jobStripHtml(q) {
    q = q || {};
    var running = q.running || [], blocked = q.blocked || [];
    var h = running.length ? runningRowHtml(running[0], false) : "";
    h += blocked.slice(0, 2).map(blockedCardHtml).join("");
    if (blocked.length > 2) {
      h += '<button type="button" class="ws-btn tm-jmore" data-open-jobs="1">' +
        esc(tw("teams.blocked_more", { n: blocked.length - 2 })) + "</button>";
    }
    return h;
  }

  // Tab Việc trong ngăn: Đang làm, Chờ bạn, Sắp làm (đánh số đúng thứ tự chạy).
  function queueHtml(q, view) {
    q = q || {};
    view = view || {};
    var running = q.running || [], waiting = q.waiting || [], blocked = q.blocked || [];
    var fin = finishedHtml(q.finished || [], q.archived || [], view);
    if (!running.length && !waiting.length && !blocked.length) {
      return (fin ? "" : '<div class="tm-empty">' + esc(tw("teams.queue_empty")) + "</div>") + fin;
    }
    var h = "";
    if (running.length) {
      h += '<div class="tm-qhead">' + esc(tw("teams.queue_running")) + "</div>";
      h += running.map(function (t) { return runningRowHtml(t, true) + accEditorHtml(t, view); }).join("");
    }
    if (blocked.length) {
      h += '<div class="tm-qhead">' + esc(tw("teams.queue_blocked")) + "</div>";
      h += blocked.map(function (t) { return blockedCardHtml(t) + accEditorHtml(t, view); }).join("");
    }
    if (waiting.length) {
      h += '<div class="tm-qhead">' + esc(tw("teams.queue_waiting")) + "</div>";
      h += waiting.map(function (t, i) {
        var star = t.team_prio != null;
        return '<div class="tm-qrow"><span class="tm-qpos">' + (i + 1) + "</span>" +
          (star ? '<span class="tm-star" title="' + esc(tw("teams.prioritized")) + '">' + ic("star") + esc(tw("teams.prioritized")) + "</span>" : "") +
          '<span class="tm-qtitle">' + esc(t.title) + '</span><span class="tm-actions">' +
          '<button type="button" class="ws-btn" data-prio="' + esc(t.id) + '" data-on="' + (star ? "0" : "1") + '">' +
          esc(tw(star ? "teams.unprioritize" : "teams.prioritize")) + "</button>" +
          '<button type="button" class="ws-btn" data-acc-edit="' + esc(t.id) + '">' + esc(tw("teams.acc.set")) + "</button>" +
          '<button type="button" class="ws-btn" data-cancel="' + esc(t.id) + '">' + esc(tw("teams.cancel")) + "</button></span></div>" +
          accEditorHtml(t, view);
      }).join("");
    }
    return h + fin;
  }

  // 0.193.0 (owner, 16/10/2026): finished jobs stay in the Jobs tab until the owner presses Done; Open shows a short report
  // (what came out, who did which step); Done moves the job to the Archive below (nothing deleted); only in the Archive
  // can a job be deleted, one by one or all at once.
  function finishedHtml(fin, arch, view) {
    var h = "";
    if (fin.length) {
      h += '<div class="tm-qhead tm-qhead-done">' + esc(tw("teams.queue_finished")) + ' <span class="tm-qn">' + fin.length + "</span></div>";
      h += fin.map(function (j) {
        var open = view.openFin === j.id;
        return '<div class="tm-qrow tm-jdone' + (j.cancelled ? " is-cancelled" : "") + '"><span class="tm-qok" aria-hidden="true">' +
          ic(j.cancelled ? "circle-x" : "circle-check") + '</span><span class="tm-qtitle">' + esc(j.title) + "</span>" +
          '<span class="tm-actions"><button type="button" class="ws-btn" data-fin-open="' + esc(j.id) + '" aria-expanded="' +
          (open ? "true" : "false") + '">' + ic(open ? "chevron-up" : "file-text") + esc(tw(open ? "teams.fin_close" : "teams.fin_open")) +
          '</button><button type="button" class="ws-btn tm-primary" data-job-archive="' + esc(j.id) + '">' + ic("check") +
          esc(tw("teams.fin_done")) + "</button></span>" + (open ? reportHtml(j, view) : "") + "</div>";
      }).join("");
    }
    if (arch.length) {
      var aopen = !!view.archOpen;
      h += '<div class="tm-qhead tm-qhead-arch"><button type="button" class="tm-arch-toggle" aria-expanded="' + (aopen ? "true" : "false") + '">' +
        ic(aopen ? "chevron-down" : "chevron-right") + esc(tw("teams.archive")) + ' <span class="tm-qn">' + arch.length + "</span></button>" +
        (aopen ? '<button type="button" class="ws-btn tm-arch-clear" data-job-delete-all="1">' + ic("trash-2") +
          esc(tw("teams.archive_clear")) + "</button>" : "") + "</div>";
      if (aopen) {
        h += arch.map(function (j) {
          return '<div class="tm-qrow tm-jarch"><span class="tm-qok" aria-hidden="true">' + ic("folder") + '</span><span class="tm-qtitle">' +
            esc(j.title) + '</span><span class="tm-actions"><button type="button" class="ws-btn" data-fin-open="' + esc(j.id) + '">' +
            esc(tw(view.openFin === j.id ? "teams.fin_close" : "teams.fin_open")) + '</button><button type="button" class="ws-btn" data-job-unarchive="' +
            esc(j.id) + '">' + esc(tw("teams.archive_back")) + '</button><button type="button" class="ws-btn" data-job-delete="' + esc(j.id) +
            '">' + ic("trash-2") + esc(tw("teams.archive_delete")) + "</button></span>" + (view.openFin === j.id ? reportHtml(j, view) : "") + "</div>";
        }).join("");
      }
    }
    return h;
  }

  function reportHtml(j, view) {
    var members = view.members || [];
    var who = {}, order = [];
    (j.steps || []).forEach(function (st) {
      if (!st.agent_key) return;
      if (!who[st.agent_key]) { who[st.agent_key] = []; order.push(st.agent_key); }
      who[st.agent_key].push(st);
    });
    var md = typeof window !== "undefined" && window.mdToHtml;
    var res = String(j.result || "").trim();
    var resHtml = res ? (md ? (function () { try { return '<div class="msg-javis tm-mdwrap"><div class="bubble">' + md(res, brain()) + "</div></div>"; }
      catch (e) { return esc(res); } })() : esc(res).replace(/\n/g, "<br>")) : '<p class="tm-sub">' + esc(tw("teams.fin_no_result")) + "</p>";
    var when = j.updated_at ? new Date(Number(j.updated_at) * 1000).toLocaleString() : "";
    return '<div class="tm-report">' +
      '<div class="tm-report-meta">' + esc(tw(j.cancelled ? "teams.fin_cancelled_at" : "teams.fin_done_at", { when: when })) + "</div>" +
      (order.length ? '<div class="tm-report-who">' + order.map(function (k) {
        var m = memberOf(members, k) || { name: k };
        var kinds = who[k].map(function (st) { return tw(ROLE_KEY[st.kind] || "teams.role.work"); }).filter(function (x, i, a) { return a.indexOf(x) === i; });
        return '<span class="tm-report-person">' + agentAva(m, 18) + "<b>" + esc(m.name || m.slug || k) + "</b>" + esc(kinds.join(", ")) + "</span>";
      }).join("") + "</div>" : "") +
      '<div class="tm-report-body">' + resHtml + "</div>" +
      (j.task_id ? '<button type="button" class="ws-btn" data-view-task="' + esc(j.task_id) + '">' + esc(tw("teams.view_msgs")) + "</button>" : "") +
      "</div>";
  }

  // ───────────── khung soạn ─────────────

  // Bỏ dấu, hoa thường, chuẩn NFC để tìm "lan" ra "Lân" và gõ tổ hợp hay dựng sẵn đều khớp. "đ" không phải dấu ghép.
  function foldName(s) {
    s = String(s == null ? "" : s);
    if (s.normalize) s = s.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
    return s.replace(/\u0111/g, "d").replace(/\u0110/g, "D").toLowerCase();
  }

  // Gợi ý @ (0.142.0): tìm KHÔNG DẤU theo đầu bất kỳ từ nào trong tên, mã (slug) hay vai; người đã gọi thì bỏ.
  function mentionMatches(members, query, chosen) {
    var q = foldName(query).trim();
    var starts = function (s) {
      s = foldName(s);
      if (!q) return true;
      if (s.indexOf(q) === 0) return true;
      return s.split(/[^\p{L}\p{N}]+/u).some(function (w) { return w && w.indexOf(q) === 0; }) ||
        s.indexOf(" " + q) >= 0;
    };
    return (members || []).filter(function (m) {
      if (m.status && m.status !== "active") return false;
      if ((chosen || []).indexOf(m.agent_key) >= 0) return false;
      return starts(m.name) || starts(m.slug) || (q && starts(m.title));
    }).slice(0, 8);
  }

  // Người được gọi là các "@Tên" (hay "@slug") còn trong chữ, theo thứ tự xuất hiện. Trước "@" phải là đầu chữ hay một ký
  // tự không phải chữ/số (địa chỉ email "ho@lan.vn" không gọi ai); sau tên phải là hết chữ hay ký tự không phải chữ/số/dấu.
  // So trên chữ đã chuẩn hoá NFC (gõ tổ hợp vẫn khớp). Hai tên cùng bắt đầu ở một chỗ ("@Lan Anh" và "@Lan") thì lấy tên
  // dài hơn.
  // Nhân dạng theo agent_key (0.142.0): người CHỌN từ gợi ý được ghi `{key, label}`. Token "@label" còn nguyên trong chữ
  // thì gọi ĐÚNG mã đó (hai trợ lý trùng tên vẫn đúng người, không suy lại theo tên); sửa hay xoá token thì lựa chọn đó
  // mất, không gọi ai theo nó nữa. Gõ tay một tên duy nhất vẫn gọi được; gõ tay một tên trùng thì không gọi ai và báo
  // `ambiguous` để chủ chọn trong gợi ý.
  var ALL_TOKEN = "all";
  function mentionScan(text, members, picked) {
    var norm = function (s) { s = String(s || ""); return (s.normalize ? s.normalize("NFC") : s).toLowerCase(); };
    var low = norm(text);
    var word = /[\p{L}\p{M}\p{N}_]/u;
    var byPos = {};
    var active = {};
    var bounded = function (i, len) {
      var prev = i ? low.charAt(i - 1) : "";
      var next = low.charAt(i + 1 + len);
      return (!prev || !word.test(prev)) && (!next || !word.test(next));
    };
    (members || []).forEach(function (m) {
      if (m.status && m.status !== "active") return;
      active[m.agent_key] = true;
      [m.name, m.slug].forEach(function (n) {
        var label = String(n || "").trim();
        n = norm(n).trim();
        if (!n) return;
        var at = 0, i;
        while ((i = low.indexOf("@" + n, at)) >= 0) {
          if (bounded(i, n.length)) {
            var g = byPos[i];
            if (!g || n.length > g.len) byPos[i] = { i: i, len: n.length, keys: [m.agent_key], label: label };
            else if (n.length === g.len && g.keys.indexOf(m.agent_key) < 0) g.keys.push(m.agent_key);
          }
          at = i + 1;
        }
      });
    });
    // Lựa chọn từ gợi ý thắng mọi cách đọc theo tên, ở đúng chỗ token của nó (mỗi lựa chọn giữ một chỗ).
    var claimed = {};
    var legacy = [];
    // Lựa chọn MỚI NHẤT xét trước (review 0.142.0, #1): chọn "Lan" rồi xoá, chọn lại "Lan Anh" thì "Lan Anh" giữ chỗ token,
    // lựa chọn cũ không còn token nào của riêng nó nên mất.
    (picked || []).forEach(function (p) { if (p && typeof p !== "object") legacy.push(p); });
    (picked || []).slice().reverse().forEach(function (p) {
      if (!p || typeof p !== "object") return;
      if (!active[p.key]) return;
      var n = norm(p.label).trim();
      if (!n) return;
      var at = 0, i;
      while ((i = low.indexOf("@" + n, at)) >= 0) {
        if (!claimed[i] && bounded(i, n.length)) {
          claimed[i] = true;
          byPos[i] = { i: i, len: n.length, keys: [p.key], label: String(p.label), picked: true };
          // Tên ngắn hơn bắt đầu ở cùng chỗ (vd. gợi ý "@Lan" nằm trong "@Lan Anh") không còn hiệu lực.
          return;
        }
        at = i + 1;
      }
    });
    // 0.192.0 (owner, 16/10/2026: "có thể tag @all để tag tất cả mọi người"): @all calls every active member.
    var all = false, ai = 0, aj;
    while ((aj = low.indexOf("@" + ALL_TOKEN, ai)) >= 0) {
      if (bounded(aj, ALL_TOKEN.length)) { all = true; break; }
      ai = aj + 1;
    }
    var used = {}, out = [], ambiguous = [];
    Object.keys(byPos).map(Number).sort(function (a, b) { return a - b; }).forEach(function (i) {
      var g = byPos[i], key = null;
      if (g.keys.length === 1) key = g.keys[0];
      else {
        legacy.some(function (k) {
          if (!used[k] && g.keys.indexOf(k) >= 0) { key = k; return true; }
          return false;
        });
        if (!key && ambiguous.indexOf(g.label) < 0) ambiguous.push(g.label);
      }
      if (key) {
        used[key] = true;
        if (out.indexOf(key) < 0) out.push(key);
      }
    });
    if (all) {
      (members || []).forEach(function (m) {
        if ((!m.status || m.status === "active") && out.indexOf(m.agent_key) < 0) out.push(m.agent_key);
      });
    }
    return { keys: out, ambiguous: ambiguous, all: all };
  }

  // Bỏ một người khỏi tin đang soạn: xoá token "@tên" của họ trong chữ (token đã chọn trước, rồi tới tên gõ tay) và bỏ
  // lựa chọn tương ứng. Trả {text, picked} mới.
  function removeMention(text, members, picked, key) {
    var norm = function (s) { s = String(s || ""); return (s.normalize ? s.normalize("NFC") : s); };
    var t = norm(text);
    var low = t.toLowerCase();
    var word = /[\p{L}\p{M}\p{N}_]/u;
    var mine = [], others = [];
    (picked || []).forEach(function (p) {
      if (p && typeof p === "object") (p.key === key ? mine : others).push(norm(p.label).toLowerCase());
    });
    (members || []).forEach(function (m) {
      if (m.status && m.status !== "active") return;
      [m.name, m.slug].forEach(function (n) { n = norm(n).trim().toLowerCase(); if (n) (m.agent_key === key ? mine : others).push(n); });
    });
    var at = function (i, n) {
      if (low.substr(i + 1, n.length) !== n) return false;
      var prev = i ? low.charAt(i - 1) : "", next = low.charAt(i + 1 + n.length);
      return (!prev || !word.test(prev)) && (!next || !word.test(next));
    };
    // Xoá từ cuối lên để chỉ số phía trước không lệch. Ở một chỗ mà tên của NGƯỜI KHÁC dài hơn cũng khớp ("@Lan Anh" khi
    // bỏ "Lan") thì đó là token của người kia, không đụng (review 0.142.0, #4).
    var cuts = [];
    for (var i = low.length - 1; i >= 0; i--) {
      if (low.charAt(i) !== "@") continue;
      var best = 0;
      mine.forEach(function (n) { if (n.length > best && at(i, n)) best = n.length; });
      if (!best) continue;
      if (others.some(function (n) { return n.length > best && at(i, n); })) continue;
      cuts.push([i, best]);
    }
    cuts.forEach(function (c) {
      var endAt = c[0] + 1 + c[1];
      if (t.charAt(endAt) === " ") endAt++;
      t = t.slice(0, c[0]) + t.slice(endAt);
    });
    return { text: t, picked: (picked || []).filter(function (p) { return !(p && typeof p === "object" ? p.key === key : p === key); }) };
  }

  // Hàng "Gọi:" trên khung soạn: mỗi người sẽ được gọi là một token riêng, bấm x để bỏ gọi.
  function callsHtml(keys, members, all) {
    if (!(keys || []).length) return "";
    if (all) {
      // @all: one chip for the whole team; its x takes "@all" out of the text.
      return '<span class="tm-calls-label">' + esc(tw("teams.calls")) + '</span><span class="tm-call">' +
        '<span class="tm-sug-all" aria-hidden="true">' + ic("users") + '</span><span class="tm-call-name">@' + ALL_TOKEN +
        " (" + keys.length + ')</span><button type="button" class="tm-call-x" data-unmention="*all" aria-label="' +
        esc(tw("teams.uncall", { name: "@" + ALL_TOKEN })) + '">' + ic("x") + "</button></span>";
    }
    return '<span class="tm-calls-label">' + esc(tw("teams.calls")) + "</span>" + keys.map(function (k) {
      var m = memberOf(members, k) || { name: k };
      return '<span class="tm-call">' + agentAva(m, 20) + '<span class="tm-call-name">@' + esc(m.name || m.slug || k) +
        '</span><button type="button" class="tm-call-x" data-unmention="' + esc(k) + '" aria-label="' +
        esc(tw("teams.uncall", { name: m.name || m.slug || k })) + '">' + ic("x") + "</button></span>";
    }).join("");
  }

  function mentionsFromText(text, members, picked) {
    return mentionScan(text, members, picked).keys;
  }

  // Một dòng gợi ý dưới khung soạn: chỉ khi Giao việc bật (sẽ tạo việc cho ai) hay khi gọi quá số người cho phép.
  function composerHint(st) {
    var cap = Number(st.cap || 3);
    var ments = st.mentions || [];
    if ((st.ambiguous || []).length) return { ok: false, text: tw("teams.mention_ambiguous", { name: st.ambiguous[0] }) };
    if (st.all) return { ok: true, text: tw("teams.hint_all", { n: ments.length }) };
    if (ments.length > cap) return { ok: false, text: tw("teams.hint_cap", { cap: cap }) };
    if (!st.asJob) return { ok: true, text: "" };
    if (ments.length) {
      var names = ments.map(function (k) { return nameOf(st.members, k); }).join(", ");
      return { ok: true, text: tw("teams.hint_job_direct", { names: names }) };
    }
    if (!st.leaderKey) return { ok: true, text: tw("teams.hint_job_noleader") };
    return { ok: true, text: tw("teams.hint_job_general", { name: nameOf(st.members, st.leaderKey) }) };
  }

  function newClientId() {
    try {
      if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
    } catch (e) { /* trình duyệt cũ: rơi xuống dưới */ }
    return "c" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
  }

  // ───────────── ngăn Nhóm ─────────────

  function rsText(on) { return tw(on ? "resonance.t0_state_on" : "resonance.t0_state_off"); }

  // Mỗi thành viên một dòng (tên đủ, vai ở dòng dưới); chạm dòng mở các thao tác.
  function membersHtml(team, agents, openKey) {
    var mem = team.members || [];
    var rows = mem.map(function (m) {
      var lead = m.agent_key === team.leader_key;
      var open = openKey === m.agent_key;
      var sub = [tw(lead ? "teams.leader" : "teams.member")];
      if (m.resonance_enabled) sub.push(rsText(true));
      return '<div class="tm-mrow"><button type="button" class="tm-mhead" data-expand="' + esc(m.agent_key) + '" aria-expanded="' +
        (open ? "true" : "false") + '">' + agentAva(m, 34) + '<span class="tm-mtext"><span class="tm-mname">' +
        esc(m.name || m.slug) + '</span><span class="tm-mrole">' + esc(sub.join(" · ")) + "</span></span>" +
        '<span class="tm-chev" aria-hidden="true">' + ic("chevron-down") + "</span></button>" +
        '<div class="tm-mact"' + (open ? "" : " hidden") + ">" +
        '<label class="tm-rs"><input type="checkbox" class="tm-rs-toggle" data-slug="' + esc(m.slug) + '"' +
        (m.resonance_enabled ? " checked" : "") + ' aria-label="' + esc(rsText(m.resonance_enabled)) + '"><span>' +
        esc(rsText(m.resonance_enabled)) + "</span></label>" +
        '<label class="tm-rs"><input type="checkbox" class="tm-managed-toggle" data-key="' + esc(m.agent_key) + '"' +
        (m.managed ? " checked" : "") + "><span>" + esc(tw("teams.managed")) + "</span></label>" +
        '<span class="tm-actions">' + (m.slug ? '<button type="button" class="ws-btn" data-agent-chat="' + esc(m.slug) + '">' +
          ic("message-circle") + esc(tw("teams.chat_private")) + "</button>" +
          '<button type="button" class="ws-btn" data-agent-edit="' + esc(m.slug) + '">' +
          ic("settings") + esc(tw("teams.agent_settings_short")) + "</button>" : "") + (lead
          ?'<button type="button" class="ws-btn" data-leader="">' + esc(tw("teams.remove_leader")) + "</button>"
          : '<button type="button" class="ws-btn" data-leader="' + esc(m.agent_key) + '">' + esc(tw("teams.make_leader")) + "</button>") +
        '<button type="button" class="ws-btn" data-remove="' + esc(m.agent_key) + '">' + esc(tw("teams.remove")) + "</button></span>" +
        // T3: nhịp chủ động của thành viên TRONG nhóm này (agent-pulse.js gắn vào sau khi vẽ).
        (open && m.slug ? '<div class="tm-pulse" data-pulse-slug="' + esc(m.slug) + '" data-pulse-ctx="team:' +
          esc(team.team_id) + '"></div>' : "") +
        // Quyết định nói / chờ / im của trợ lý trong ĐÚNG nhóm này, có nút sửa (agent-judge-ui.js vẽ khi hàng mở).
        (open && m.slug ? '<div class="agj-host" data-judge-slug="' + esc(m.slug) + '" data-judge-ctx="team:' +
          esc(team.team_id || "") + '"></div>' : "") + "</div></div>";
    }).join("");
    // Thêm người: mở hộp chọn kiểu Zalo (tìm không dấu, lọc tag, chọn nhiều người một lần), 0.142.0.
    var add = '<div class="tm-add"><button type="button" class="ws-btn tm-add-open">' + ic("users") +
      esc(tw("teams.pick.add_open")) + "</button></div>";
    // Chủ nhóm luôn đứng đầu, tách khỏi Điều phối (AI): người tạo và quản lý nhóm là bạn, không phải một trợ lý.
    // Nhân dạng người tạo lấy từ server (`team.creator`, theo phiên đăng nhập của chủ máy), không do trang tự khai.
    var cr = (team && team.creator) || {};
    var youName = tw("teams.pick.you") + (cr.name ? " (" + cr.name + ")" : "");
    var you = '<div class="tm-mrow tm-mrow-you"><div class="tm-mhead tm-mhead-static">' +
      '<span class="tmp-face tmp-initial tmp-you" aria-hidden="true">' + esc(tw("teams.pick.you").charAt(0)) + "</span>" +
      '<span class="tm-mtext"><span class="tm-mname">' + esc(youName) + '</span><span class="tm-mrole">' +
      esc(tw("teams.pick.you_role")) + '</span></span><span class="tmp-badge">' + esc(tw("teams.pick.owner_badge")) +
      "</span></div></div>";
    return you + rows + add;
  }

  // Mức tự quyết đang áp: 1 (hỏi trước, Quyền giới hạn), 2, 3, hay "custom" (đặt tay trong Nâng cao). Chỉ so trần tối
  // đa, quyền ngắt việc và provider: trần trưởng nhóm tự chỉnh trong khoảng cho phép không đổi mức.
  function levelOf(team) {
    var auth = team && team.authority && team.authority.authority;
    if (!auth) return 1;
    var g = auth.grant || {}, ce = g.ceilings || {};
    if ((g.providers_unlimited || []).length) return "custom";
    var is2 = !g.can_interrupt && AUTH_CAPS.every(function (k) { return ce[k] === LEVEL2_CEILINGS[k]; });
    var is3 = !!g.can_interrupt && AUTH_CAPS.every(function (k) { return ce[k] && typeof ce[k] === "object" && ce[k].unlimited; });
    return is2 ? 2 : is3 ? 3 : "custom";
  }

  // Hộp cấp quyền cho mức 2, 3 (POST /teams/{id}/authority mode=full). Mức 1 là thu hồi, không có hộp.
  function grantFor(level) {
    if (level === 2) {
      return { caps: {}, ceilings: Object.assign({}, LEVEL2_CEILINGS), can_interrupt: false, providers_unlimited: [],
        billing: "subscription" };
    }
    if (level === 3) {
      var ce = {};
      AUTH_CAPS.forEach(function (k) { ce[k] = { unlimited: true }; });
      return { caps: {}, ceilings: ce, can_interrupt: true, providers_unlimited: [], billing: "subscription" };
    }
    return null;
  }

  // Ba mức là một nhóm lựa chọn có tên (fieldset + legend) để trình đọc màn hình đọc câu hỏi kèm từng lựa chọn.
  function levelsHtml(team) {
    var legend = '<legend class="tm-qhead">' + esc(tw("teams.level_title")) + "</legend>";
    if (!team.leader_key) {
      return '<fieldset class="tm-levels">' + legend + '<div class="tm-note-line">' + esc(tw("teams.level_need_leader")) +
        "</div></fieldset>";
    }
    var lvl = levelOf(team);
    // 0.214.0: what each level allows sits behind the (i) in the legend; the choices keep their short names.
    legend = '<legend class="tm-qhead">' + esc(tw("teams.level_title")) + infoBtn() + "</legend>" +
      infoBody(LEVELS.map(function (L) { return "<div><b>" + esc(tw(L.key)) + "</b>: " + esc(tw(L.desc)) + "</div>"; }).join(""));
    return '<fieldset class="tm-levels">' + legend + LEVELS.map(function (L) {
      return '<label class="tm-level"><input type="radio" name="tm-level" value="' + L.n + '"' + (lvl === L.n ? " checked" : "") +
        '><span class="tm-level-body"><strong>' + esc(tw(L.key)) + "</strong></span></label>";
    }).join("") + (lvl === "custom" ? '<div class="tm-sub">' + esc(tw("teams.level_custom")) + "</div>" : "") + "</fieldset>";
  }

  function usageHtml(team) {
    var u = team.usage;
    if (!u) return "";
    return '<div class="tm-usage">' + esc(u.cap === null || u.cap === undefined
      ? tw("teams.usage_today_unl", { n: u.today }) : tw("teams.usage_today", { n: u.today, cap: u.cap })) + "</div>";
  }

  // Tên, mô tả, trạng thái của nhóm. Nút Lưu ở cuối.
  function settingsFormHtml(team) {
    var st = ["active", "paused", "archived"].map(function (s) {
      return '<label class="tm-radio"><input type="radio" name="tm-status" value="' + s + '"' + (team.status === s ? " checked" : "") +
        "><span>" + esc(tw(TEAM_STATUS_KEY[s])) + "</span></label>";
    }).join("");
    // Ảnh nhóm (0.176.0): mặc định ghép từ gương mặt thành viên; "Tải ảnh lên" thay bằng ảnh riêng, lưu ngay không chờ nút Lưu.
    var A = typeof window !== "undefined" && window.JavisAvatar;
    var ava = A && A.uploadRowHtml ? '<div class="tm-field tm-ava-set"><span>' + esc(tw("teams.avatar")) + '</span><div class="tm-ava-row">' +
      teamAvatarHtml(team, 56) + '<div class="tm-ava-acts">' + A.uploadRowHtml(!!team.avatar_image, tw("teams.avatar_use_faces")) +
      "</div></div></div>" : "";
    return '<form class="tm-form" onsubmit="return false">' + ava +
      '<label class="tm-field"><span>' + esc(tw("teams.name")) + '</span><input name="tm-set-name" value="' + esc(team.name) + '"></label>' +
      '<label class="tm-field"><span>' + esc(tw("teams.description")) + '</span><textarea name="tm-set-desc" rows="2">' + esc(team.description) + "</textarea></label>" +
      '<div class="tm-field"><span>' + esc(tw("teams.status")) + '</span><div class="tm-radios">' + st + "</div></div>" +
      '<div class="tm-actions"><button type="button" class="ws-btn tm-save">' + esc(tw("teams.save")) + "</button>" +
      '<button type="button" class="ws-btn tm-danger" data-delete-team="' + esc(team.team_id) + '">' + ic("trash-2") +
      esc(tw("teams.delete_team")) + "</button></div></form>";
  }

  // Các số giới hạn của nhóm (trong Nâng cao). Nút Lưu ở cuối.
  function capsFormHtml(team) {
    var caps = team.caps || {};
    var capRows = CAP_FIELDS.map(function (k) {
      var unl = OWNER_UNL.indexOf(k) >= 0;
      var isUnl = unl && caps[k] === null;
      // Trần có "Không giới hạn": ô tích riêng, null là không giới hạn (không thay bằng một số lớn).
      return '<div class="tm-field tm-cap"><label class="tm-cap-num"><span>' + esc(tw(CAP_KEY[k])) + '</span><input type="number" min="0" name="tm-cap-' + k +
        '" value="' + esc(caps[k] == null ? "" : caps[k]) + '"' + (isUnl ? " disabled" : "") + "></label>" +
        (unl ? '<label class="tm-unl"><input type="checkbox" name="tm-cap-' + k + '-unl"' + (isUnl ? " checked" : "") + "> " +
          esc(tw("teams.auth.unlimited")) + "</label>" : "") + "</div>";
    }).join("");
    capRows += CAP_MODES.map(function (k) {
      var cur = caps[k] === 0 ? "0" : "1";
      return '<label class="tm-field tm-cap"><span>' + esc(tw(CAP_KEY[k])) + '</span><select name="tm-cap-' + k + '">' +
        '<option value="1"' + (cur === "1" ? " selected" : "") + ">" + esc(tw(MODE_LABELS[k][0])) + "</option>" +
        '<option value="0"' + (cur === "0" ? " selected" : "") + ">" + esc(tw(MODE_LABELS[k][1])) + "</option>" +
        "</select></label>";
    }).join("");
    return '<form class="tm-form tm-caps-form" onsubmit="return false"><div class="tm-qhead">' + esc(tw("teams.caps")) + "</div>" +
      (team.quality_policy && team.quality_policy.enabled && team.quality_policy.limit_migration === "observe" ?
        '<div class="tm-qhead">' + esc(tw("teams.quality.observe")) + infoBtn() + '</div>' +
        infoBody(esc(tw("teams.quality.caps_explain"))) : "") +
      // Trưởng nhóm đang được tự quyết: số trong hộp quyền đè số ở đây; nói rõ thay vì để "Đã lưu" mà không đổi gì.
      (team.authority && team.authority.authority ? '<div class="tm-note-line">' + esc(tw("teams.caps_full_note")) + "</div>" : "") +
      capRows + '<button type="button" class="ws-btn tm-caps-save">' + esc(tw("teams.save")) + "</button></form>";
  }

  function capText(v) {
    return v === null || v === undefined ? tw("teams.auth.unlimited") : String(v);
  }

  function limitValue(x) {
    if (x.unit === "rule") return "";
    if (x.unit === "mode") {
      var ml = MODE_LABELS[x.key] || MODE_LABELS.judge_off_batch;
      return tw(x.value === 0 ? ml[1] : ml[0]);
    }
    if (x.value === null || x.value === undefined) return tw("teams.auth.unlimited");
    if (x.unit === "seconds") {
      return x.value >= 60 && x.value % 60 === 0 ? tw("teams.limits.minutes", { n: x.value / 60 })
        : tw("teams.limits.seconds", { n: x.value });
    }
    if (x.unit === "percent") return tw("pulse.percent", { n: x.value });
    if (x.unit === "tier") return tw(PULSE_TIER_KEY[x.value] || "pulse.tier_1");
    return String(x.value);
  }

  // Bảng MỌI giới hạn của nhóm (GOAL T1 mục 9), đọc từ `authority.limits` của máy chủ: chủ chỉnh được, trưởng nhóm chỉnh
  // được khi có Toàn quyền, máy chủ cố định, nhà cung cấp quyết. Không có câu "bỏ mọi giới hạn".
  function limitsHtml(team) {
    var rows = (team.authority && team.authority.limits) || [];
    if (!rows.length) return "";
    var body = LIMIT_CATS.map(function (cat) {
      var mine = rows.filter(function (x) { return x.category === cat.id; });
      if (!mine.length) return "";
      var off = cat.id === "leader" && !mine[0].granted;
      // The model-plan caveat sits behind the (i) next to the leader heading.
      var modelNote = cat.id === "leader" && !off && mine.some(function (x) { return x.model_turns; });
      var items = mine.map(function (x) {
        var label = tw(cat.id === "owner" || cat.id === "leader" ? (CAP_KEY[x.key] || AUTH_CAP_KEY[x.key] || LIMIT_KEY[x.key])
          : LIMIT_KEY[x.key]);
        var v = cat.id === "leader" ? (!x.granted ? "" : x.editable ? tw("teams.limits.leader_max", { v: limitValue(x) })
          : tw("teams.limits.leader_locked")) : limitValue(x);
        var unl = cat.id === "owner" && x.unlimited_ok ? " (" + tw("teams.limits.unl_ok") + ")" : "";
        return '<li class="tm-limit"><span class="tm-limit-k">' + esc(label) + "</span>" +
          (v ? ': <span class="tm-limit-v">' + esc(v) + "</span>" : "") + esc(unl) + "</li>";
      }).join("");
      return '<div class="tm-limits-cat"><div class="tm-limits-head">' + esc(tw(cat.key)) + (modelNote ? infoBtn() : "") + "</div>" +
        (off ? '<div class="tm-limits-note">' + esc(tw("teams.limits.leader_off")) + "</div>" : "") +
        (modelNote ? infoBody(esc(tw("teams.limits.leader_model_note"))) : "") + '<ul class="tm-limits-list">' + items + "</ul></div>";
    }).join("");
    return '<section class="tm-limits" aria-label="' + esc(tw("teams.limits.title")) + '"><div class="tm-qhead">' +
      esc(tw("teams.limits.title")) + infoBtn() + "</div>" + infoBody(esc(tw("teams.limits.intro"))) + body +
      "</section>";
  }

  function capInputs(name, v, noUnl) {
    var unl = !!(v && typeof v === "object" && v.unlimited);
    var num = !unl && v !== null && v !== undefined && typeof v !== "object" ? String(v) : "";
    if (noUnl) return '<input type="number" min="0" name="' + name + '" value="' + esc(num) + '">';
    return '<input type="number" min="0" name="' + name + '" value="' + esc(num) + '"' + (unl ? " disabled" : "") + ">" +
      '<label class="tm-unl"><input type="checkbox" name="' + name + '-unl"' + (unl ? " checked" : "") + "> " +
      esc(tw("teams.auth.unlimited")) + "</label>";
  }

  // Hộp cấp quyền chi tiết (spec 13.1), nằm trong Nâng cao: phạm vi, agent do nhóm quản lý, provider được Không giới
  // hạn, nguồn thanh toán, trần và trần trần, quyền ngắt việc, các trần không bỏ được (luôn hiện).
  function authorityHtml(team) {
    var view = team.authority || {};
    var auth = view.authority;
    var grant = (auth && auth.grant) || {};
    var eff = view.effective_caps || team.caps || {};
    var leader = team.leader_key ? nameOf(team.members, team.leader_key) : "";
    var managed = (team.members || []).filter(function (m) { return m.managed; }).map(function (m) { return m.name || m.slug; });
    var status = auth ? tw("teams.auth.on", { name: leader, when: new Date(auth.granted_at * 1000).toLocaleString() })
      : tw("teams.auth.off");
    var now = AUTH_CAPS.map(function (k) { return tw(AUTH_CAP_KEY[k]) + ": " + capText(eff[k]); }).join(" · ");
    var rows = AUTH_CAPS.concat(AUTH_JUDGE_CAPS).map(function (k) {
      return '<div class="tm-field tm-auth-cap"><span>' + esc(tw(AUTH_CAP_KEY[k])) + "</span>" +
        '<span class="tm-auth-pair"><span class="tm-auth-lbl">' + esc(tw("teams.auth.cap_value")) + "</span>" +
        capInputs("tm-auth-cap-" + k, (grant.caps || {})[k], k === "volunteer_k") + "</span>" +
        '<span class="tm-auth-pair"><span class="tm-auth-lbl">' + esc(tw("teams.auth.cap_ceiling")) + "</span>" +
        capInputs("tm-auth-ceil-" + k, (grant.ceilings || {})[k], k === "volunteer_k") + "</span></div>";
    }).join("");
    var allowed = {};
    (grant.providers_unlimited || []).forEach(function (x) { allowed[x] = true; });
    var prov = PROVIDERS.map(function (x) {
      return '<label class="tm-unl"><input type="checkbox" name="tm-auth-prov" value="' + esc(x.id) + '"' +
        (allowed[x.id] ? " checked" : "") + "> " + esc(tw(x.key)) + "</label>";
    }).join("");
    var bill = ["subscription", "api"].map(function (b) {
      return '<label class="tm-radio"><input type="radio" name="tm-auth-bill" value="' + b + '"' +
        ((grant.billing || "subscription") === b ? " checked" : "") + "><span>" +
        esc(tw(b === "api" ? "teams.auth.billing_api" : "teams.auth.billing_sub")) + "</span></label>";
    }).join("");
    var fixed = FIXED_KEYS.map(function (k) { return "<li>" + esc(tw(k)) + "</li>"; }).join("");
    if (!team.leader_key) {
      return '<section class="tm-auth"><div class="tm-qhead">' + esc(tw("teams.auth.title")) + "</div>" +
        '<div class="tm-note-line">' + esc(tw("teams.auth.need_leader")) + "</div></section>";
    }
    return '<section class="tm-auth" aria-label="' + esc(tw("teams.auth.title")) + '"><div class="tm-qhead">' +
      esc(tw("teams.auth.title")) + "</div>" +
      '<div class="tm-auth-status' + (auth ? " tm-auth-on" : "") + '">' + esc(status) + "</div>" +
      '<div class="tm-react-sub">' + esc(tw("teams.auth.now", { caps: now })) + "</div>" +
      '<div class="tm-react-sub">' + esc(tw("teams.auth.scope")) + "</div>" +
      '<div class="tm-react-sub">' + esc(managed.length ? tw("teams.auth.managed", { names: managed.join(", ") })
        : tw("teams.auth.managed_none")) + "</div>" +
      '<div class="tm-qhead">' + esc(tw("teams.auth.caps_head")) + "</div>" + rows +
      '<div class="tm-field"><span>' + esc(tw("teams.auth.providers")) + "</span>" + prov + "</div>" +
      '<div class="tm-field"><span>' + esc(tw("teams.auth.billing")) + "</span>" + bill + "</div>" +
      '<label class="tm-unl"><input type="checkbox" name="tm-auth-interrupt"' + (grant.can_interrupt ? " checked" : "") +
      "> " + esc(tw("teams.auth.interrupt")) + "</label>" +
      '<div class="tm-react-sub">' + esc(tw("teams.auth.fixed")) + '</div><ul class="tm-auth-fixed">' + fixed + "</ul>" +
      '<div class="tm-actions"><button type="button" class="ws-btn tm-auth-save">' +
      esc(tw(auth ? "teams.auth.update" : "teams.auth.grant")) + "</button>" +
      (auth ? '<button type="button" class="ws-btn tm-auth-revoke">' + esc(tw("teams.auth.revoke")) + "</button>" : "") +
      "</div></section>";
  }

  // Đọc hộp cấp quyền thành `grant` cho POST /teams/{id}/authority. Ô trống, không tích: bỏ (theo mặc định; trần trần
  // vắng nghĩa là trưởng nhóm không đổi được trần đó).
  function readGrant(root) {
    function one(name) {
      var box = root.querySelector('[name="' + name + '-unl"]');
      if (box && box.checked) return { unlimited: true };
      var inp = root.querySelector('[name="' + name + '"]');
      var v = inp ? String(inp.value).trim() : "";
      return v === "" ? undefined : Number(v);
    }
    var caps = {}, ceilings = {};
    AUTH_CAPS.concat(AUTH_JUDGE_CAPS).forEach(function (k) {
      var c = one("tm-auth-cap-" + k), l = one("tm-auth-ceil-" + k);
      if (c !== undefined) caps[k] = c;
      if (l !== undefined) ceilings[k] = l;
    });
    var bill = root.querySelector('input[name="tm-auth-bill"]:checked');
    var intr = root.querySelector('input[name="tm-auth-interrupt"]');
    return { caps: caps, ceilings: ceilings,
      providers_unlimited: Array.prototype.map.call(root.querySelectorAll('input[name="tm-auth-prov"]:checked'),
        function (x) { return x.value; }),
      billing: bill ? bill.value : "subscription", can_interrupt: !!(intr && intr.checked) };
  }

  // Kết quả tìm trong nhóm (T4): mỗi dòng là nút nhảy tới tin, kèm người gửi và đoạn trích.
  function searchResultsHtml(results, members, query) {
    if (results === null || results === undefined) return "";
    if (!results.length) return '<div class="tm-search-none">' + esc(tw("teams.search_none", { q: query || "" })) + "</div>";
    return '<div class="tm-search-count">' + esc(tw("teams.search_results", { n: results.length })) + "</div>" +
      results.map(function (x) {
        var who = x.author_kind === "owner" ? tw("teams.owner") : x.author_kind === "agent" ? nameOf(members, x.author_ref)
          : tw("teams.system");
        return '<button type="button" class="tm-search-hit" data-jump="' + esc(x.id) + '" data-ts="' + esc(x.ts) + '">' +
          '<span class="tm-who">' + esc(who) + "</span> " + '<span class="tm-search-snip">' + esc(x.snippet) + "</span></button>";
      }).join("");
  }

  function dayStart() {
    var d = new Date();
    d.setHours(0, 0, 0, 0);
    return d.getTime() / 1000;
  }

  function turnsHtml(turns, team) {
    var counted = (turns || []).filter(function (t) { return t.status !== "refunded"; });
    var today = counted.filter(function (t) { return Number(t.created_at) >= dayStart(); }).length;
    var byAgent = {}, byRole = {};
    counted.forEach(function (t) {
      byAgent[t.agent_key] = (byAgent[t.agent_key] || 0) + 1;
      var rk = TURN_ROLE_KEY[t.role] || t.role;
      byRole[rk] = (byRole[rk] || 0) + 1;
    });
    var list = function (obj, label) {
      return Object.keys(obj).map(function (k) { return esc(label(k)) + " " + obj[k]; }).join(" · ");
    };
    return '<div class="tm-turns"><div class="tm-qhead">' + esc(tw("teams.turns_today", { n: today, cap: capText((team.caps || {}).daily_turns) })) + "</div>" +
      "<div>" + esc(tw("teams.turns_by_agent")) + ": " + list(byAgent, function (k) { return nameOf(team.members, k); }) + "</div>" +
      "<div>" + esc(tw("teams.turns_by_role")) + ": " + list(byRole, function (k) { return tw(k); }) + "</div>" +
      '<div class="tm-sub">' + esc(tw("teams.turns_note")) + "</div></div>";
  }

  // 0.208.0: department mandate (team_mandate.py). Kinds, levels and states with literal keys for test_i18n.
  var MD_KINDS = ["file_changed", "job_failed", "test_failing", "connection_down"];
  var MD_KIND_KEY = { file_changed: "teams.md.kind.file_changed", job_failed: "teams.md.kind.job_failed",
    test_failing: "teams.md.kind.test_failing", connection_down: "teams.md.kind.connection_down" };
  var MD_LEVELS = ["watch", "propose", "approve", "act"];
  var MD_LEVEL_KEY = { watch: "teams.md.level.watch", propose: "teams.md.level.propose", approve: "teams.md.level.approve",
    act: "teams.md.level.act" };
  var MD_STATUS_KEY = { off: "teams.md.st.off", active: "teams.md.st.active", paused: "teams.md.st.paused",
    revoked: "teams.md.st.revoked" };
  var MD_SRC_KEY = { ok: "teams.md.src.ok", missing: "teams.md.src.missing", never: "teams.md.src.never" };
  var OPP_ST_KEY = { proposed: "teams.md.opp.proposed", enqueued: "teams.md.opp.enqueued", asked: "teams.md.opp.asked",
    rejected: "teams.md.opp.rejected", expired: "teams.md.opp.expired", dismissed: "teams.md.opp.dismissed",
    watched: "teams.md.opp.watched", open: "teams.md.opp.proposed", accepting: "teams.md.opp.enqueued" };

  function mdLevelOf(m, kind) {
    var a = (m && m.autonomy) || {};
    if ((a.act || []).indexOf(kind) >= 0) return "act";
    if ((a.approve || []).indexOf(kind) >= 0) return "approve";
    if ((a.propose || []).indexOf(kind) >= 0) return "propose";
    return "watch";
  }

  function mandateFormHtml(m) {
    m = m || {};
    var b = m.budget || {};
    var area = function (name, key, val, rows) {
      return '<label class="tm-field"><span>' + esc(tw(key)) + '</span><textarea name="' + name + '" rows="' + (rows || 2) +
        '">' + esc(val || "") + "</textarea></label>";
    };
    var num = function (name, key, val) {
      return '<label class="tm-field tm-cap"><span>' + esc(tw(key)) + '</span><input type="number" min="0" name="' + name +
        '" value="' + esc(val == null ? "" : val) + '"></label>';
    };
    var levels = MD_KINDS.map(function (k) {
      var cur = mdLevelOf(m, k);
      return '<label class="tm-field tm-cap"><span>' + esc(tw(MD_KIND_KEY[k])) + '</span><select name="tm-md-lvl-' + k + '">' +
        MD_LEVELS.map(function (l) {
          return '<option value="' + l + '"' + (l === cur ? " selected" : "") + ">" + esc(tw(MD_LEVEL_KEY[l])) + "</option>";
        }).join("") + "</select></label>";
    }).join("");
    return '<form class="tm-form tm-md-form" onsubmit="return false">' +
      area("tm-md-outcome", "teams.md.outcome", m.outcome, 2) +
      area("tm-md-metrics", "teams.md.metrics", (m.metrics || []).join("\n"), 3) +
      area("tm-md-sources", "teams.md.sources", (m.sources || []).join("\n"), 3) +
      '<div class="tm-sub">' + esc(tw("teams.md.sources_help")) + "</div>" +
      area("tm-md-scope", "teams.md.scope", m.scope, 2) +
      num("tm-md-cadence", "teams.md.cadence", m.cadence_min || 60) +
      num("tm-md-obs", "teams.md.observe_per_day", b.observe_per_day == null ? 48 : b.observe_per_day) +
      num("tm-md-jobs", "teams.md.jobs_per_day", b.jobs_per_day == null ? 3 : b.jobs_per_day) +
      num("tm-md-maxopen", "teams.md.max_open", (m.stop || {}).max_open_jobs) +
      '<div class="tm-qhead">' + esc(tw("teams.md.autonomy")) + "</div>" + levels +
      '<div class="tm-actions"><button type="button" class="ws-btn tm-primary tm-md-save">' + esc(tw("teams.save")) +
      '</button><button type="button" class="ws-btn" data-mandate-edit="0">' + esc(tw("teams.cancel")) + "</button></div></form>";
  }

  function mandateHtml(team, editing) {
    var m = team.mandate;
    var head = '<div class="tm-qhead">' + esc(tw("teams.md.title")) + "</div>";
    if (editing) return '<section class="tm-sec tm-md">' + head + mandateFormHtml(m) + "</section>";
    if (!m) {
      // No mandate yet: the title, the (i) with what a mandate does, and the Set button.
      return '<section class="tm-sec tm-md"><div class="tm-qhead">' + esc(tw("teams.md.title")) + infoBtn() + "</div>" +
        infoBody(esc(tw("teams.md.none"))) +
        '<div class="tm-actions"><button type="button" class="ws-btn" data-mandate-edit="1">' + esc(tw("teams.md.set")) +
        "</button></div></section>";
    }
    var st = m.status || "off";
    var srcs = (m.sources_state || []).map(function (x) {
      return '<li class="tm-md-src tm-md-src-' + esc(x.state) + '"><code>' + esc(x.source) + "</code> · " +
        esc(tw(MD_SRC_KEY[x.state] || MD_SRC_KEY.never)) + (x.missing ? ": " + esc(x.missing) : "") + "</li>";
    }).join("");
    var lv = MD_KINDS.map(function (k) { return esc(tw(MD_KIND_KEY[k])) + ": " + esc(tw(MD_LEVEL_KEY[mdLevelOf(m, k)])); }).join(" · ");
    var btn = function (status, key) {
      return '<button type="button" class="ws-btn" data-mandate-status="' + status + '">' + esc(tw(key)) + "</button>";
    };
    var acts = st === "revoked" ? "" : (st === "active" ? btn("paused", "teams.md.pause") : btn("active", "teams.md.start")) +
      btn("revoked", "teams.md.revoke");
    return '<section class="tm-sec tm-md">' + head +
      '<div class="tm-md-status tm-md-' + esc(st) + '">' + esc(tw(MD_STATUS_KEY[st] || MD_STATUS_KEY.off)) +
      " · " + esc(tw("teams.md.version", { v: m.version })) + "</div>" +
      '<div class="tm-md-outcome">' + esc(m.outcome) + "</div>" +
      ((m.metrics || []).length ? '<ul class="tm-md-metrics">' + m.metrics.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>" : "") +
      '<div class="tm-sub">' + esc(tw("teams.md.sources")) + '</div><ul class="tm-md-srcs">' + srcs + "</ul>" +
      '<div class="tm-sub">' + lv + "</div>" +
      (m.observing === false ? '<div class="tm-note-line">' + esc(tw("teams.md.not_observing")) + "</div>" : "") +
      '<div class="tm-actions">' + acts + '<button type="button" class="ws-btn" data-mandate-edit="1">' +
      esc(tw("teams.md.edit")) + "</button></div></section>";
  }

  // A proposal card from the mandate in the team chat: why, evidence, and the owner's two buttons.
  function opportunityCardHtml(m) {
    var o = (m.meta || {}).opportunity || {};
    var st = o.status || "proposed";
    var ev = (o.evidence || []).map(function (e) { return "<li>" + esc(e) + "</li>"; }).join("");
    var foot = (st === "proposed" || st === "open") ?
      '<div class="tm-actions"><button type="button" class="ws-btn tm-primary" data-opp-decide="accept" data-opp="' +
        esc(o.opp_id) + '">' + esc(tw("teams.md.accept")) + '</button><button type="button" class="ws-btn" data-opp-decide="reject" data-opp="' +
        esc(o.opp_id) + '">' + esc(tw("teams.md.reject")) + "</button></div>" :
      '<div class="tm-ap-state">' + esc(tw(OPP_ST_KEY[st] || OPP_ST_KEY.proposed)) + "</div>";
    return '<div class="tm-ap tm-opp tm-ap-' + esc(st) + '" data-mid="' + esc(m.id) + '" role="group"><div class="tm-ap-head">' +
      ic("lightbulb") + "<b>" + esc(tw("teams.md.opp_title")) + "</b></div>" +
      '<div>' + esc(o.reason || "") + "</div>" +
      (o.benefit ? '<div class="tm-ap-row"><span class="tm-ap-k">' + esc(tw("teams.md.benefit")) + "</span><span>" + esc(o.benefit) + "</span></div>" : "") +
      (ev ? '<div class="tm-ap-k">' + esc(tw("teams.ap.evidence")) + '</div><ul class="tm-ap-ev">' + ev + "</ul>" : "") +
      '<div class="tm-sub"><code>' + esc((o.source || "") + ":" + (o.ref || "") + " @ " + (o.version_key || "")) + "</code></div>" +
      foot + "</div>";
  }

  function readMandateForm(form) {
    var val = function (n) { var el = form.querySelector('[name="' + n + '"]'); return el ? el.value : ""; };
    var lines = function (n) { return val(n).split("\n").map(function (x) { return x.trim(); }).filter(Boolean); };
    var autonomy = { act: [], approve: [], propose: [] };
    MD_KINDS.forEach(function (k) {
      var l = val("tm-md-lvl-" + k);
      if (autonomy[l]) autonomy[l].push(k);
    });
    var body = { outcome: val("tm-md-outcome").trim(), metrics: lines("tm-md-metrics"), sources: lines("tm-md-sources"),
      scope: val("tm-md-scope").trim(), cadence_min: Number(val("tm-md-cadence")) || 60,
      budget: { observe_per_day: Number(val("tm-md-obs")), jobs_per_day: Number(val("tm-md-jobs")) }, autonomy: autonomy };
    if (val("tm-md-maxopen") !== "") body.stop = { max_open_jobs: Number(val("tm-md-maxopen")) };
    return body;
  }

  var WM_KEY = { gated: ["teams.wm.gated", "teams.wm.gated_desc"], full: ["teams.wm.full", "teams.wm.full_desc"] };
  var AP_ST_KEY = { pending: "teams.ap.st.pending", approved: "teams.ap.st.approved", consumed: "teams.ap.st.consumed",
    rejected: "teams.ap.st.rejected", changes_requested: "teams.ap.st.changes_requested", expired: "teams.ap.st.expired",
    superseded: "teams.ap.st.superseded", cancelled: "teams.ap.st.cancelled", revoked: "teams.ap.st.revoked" };

  // 0.207.0: what the team may do outside without asking. Gated (default): outside actions wait for an approval card.
  function workModeHtml(team) {
    var full = team.work_mode === "full";
    // 0.214.0: what each choice does sits behind the (i) next to the title; the choices keep their short names.
    return '<section class="tm-sec tm-wm" aria-label="' + esc(tw("teams.wm.title")) + '"><div class="tm-qhead">' +
      esc(tw("teams.wm.title")) + infoBtn() + "</div>" +
      infoBody(["gated", "full"].map(function (m) {
        return "<div><b>" + esc(tw(WM_KEY[m][0])) + "</b>: " + esc(tw(WM_KEY[m][1])) + "</div>";
      }).join("")) +
      ["gated", "full"].map(function (m) {
        return '<label class="tm-radio"><input type="radio" name="tm-wm" value="' + m + '" data-work-mode="' + m + '"' +
          ((m === "full") === full ? " checked" : "") + "><span><b>" + esc(tw(WM_KEY[m][0])) + "</b></span></label>";
      }).join("") + "</section>";
  }

  // 0.207.0: an approval request card in the team chat. State comes from the server (never guessed): waiting with three
  // buttons, approved / used / rejected / void with who and why.
  function approvalCardHtml(m) {
    var ap = (m.meta || {}).approval || {};
    var st = ap.status || "pending";
    var rows = [];
    if (ap.action) rows.push(["teams.ap.action", ap.action]);
    if (ap.scope) rows.push(["teams.ap.scope", ap.scope]);
    if (ap.impact) rows.push(["teams.ap.impact", ap.impact]);
    var body = rows.map(function (r) {
      return '<div class="tm-ap-row"><span class="tm-ap-k">' + esc(tw(r[0])) + "</span><span>" +
        esc(r[1]).replace(/\n/g, "<br>") + "</span></div>";
    }).join("");
    var acts = (ap.actions || []).map(function (a) {
      return '<li><code>' + esc(a.call || a.label) + "</code>" + (a.used ? " · " + esc(tw("teams.ap.used")) : "") + "</li>";
    }).join("");
    if (acts) body += '<div class="tm-ap-k">' + esc(tw("teams.ap.calls")) + '</div><ul class="tm-ap-calls">' + acts + "</ul>";
    var ev = (ap.evidence || []).map(function (e) { return "<li>" + esc(e) + "</li>"; }).join("");
    if (ev) body += '<div class="tm-ap-k">' + esc(tw("teams.ap.evidence")) + '</div><ul class="tm-ap-ev">' + ev + "</ul>";
    if (ap.deadline_at) {
      body += '<div class="tm-ap-row"><span class="tm-ap-k">' + esc(tw("teams.ap.deadline")) + "</span><span>" +
        esc(new Date(Number(ap.deadline_at) * 1000).toLocaleString()) + "</span></div>";
    }
    // A prose question: what Approve means sits behind the (i) in the card head.
    var prose = ap.kind === "question";
    if (prose) body = infoBody(esc(tw("teams.ap.prose"))) + body;
    var foot;
    if (st === "pending") {
      var b = function (d, k, cls) {
        return '<button type="button" class="ws-btn' + (cls || "") + '" data-ap-decide="' + d + '" data-ap="' +
          esc(ap.approval_id) + '" data-ap-rev="' + esc(ap.team_rev) + '">' + esc(tw(k)) + "</button>";
      };
      foot = '<div class="tm-actions">' + b("approve", "teams.ap.approve", " tm-primary") + b("changes", "teams.ap.changes") +
        b("reject", "teams.ap.reject") + "</div>";
    } else {
      foot = '<div class="tm-ap-state tm-ap-' + esc(st) + '">' + esc(tw(AP_ST_KEY[st] || AP_ST_KEY.pending)) +
        (ap.decision_note ? " · " + esc(ap.decision_note) : "") + (ap.close_reason && st !== "consumed" ? " · " +
        esc(ap.close_reason) : "") + "</div>" +
        (st === "approved" ? '<div class="tm-actions"><button type="button" class="ws-btn" data-ap-decide="revoke" data-ap="' +
          esc(ap.approval_id) + '">' + esc(tw("teams.ap.revoke")) + "</button></div>" : "");
    }
    return '<div class="tm-ap tm-ap-' + esc(st) + '" data-mid="' + esc(m.id) + '" role="group" aria-label="' +
      esc(tw("teams.ap.title")) + '"><div class="tm-ap-head">' + ic("shield") + "<b>" + esc(tw("teams.ap.title")) +
      "</b> " + esc(ap.title || "") + (prose ? infoBtn() : "") + "</div>" + body + foot + "</div>";
  }

  // Tab Nhóm: thành viên, mức tự quyết, số lần đã dùng hôm nay, tên và trạng thái; mọi con số trong Nâng cao (đóng sẵn).
  function teamTabHtml(team, agents, ui) {
    ui = ui || {};
    var nAct = (team.members || []).filter(function (m) { return !m.status || m.status === "active"; }).length;
    return '<section class="tm-sec"><div class="tm-qhead">' + esc(tw("teams.tab_members")) + " · " +
      esc(tw("teams.head_people", { n: nAct })) + "</div>" +
      membersHtml(team, agents, ui.openMember) + "</section>" +
      '<section class="tm-sec">' + levelsHtml(team) + usageHtml(team) + "</section>" +
      workModeHtml(team) + qualityPolicyHtml(team) + qualityUsageHtml(team.quality_usage, (team.quality_policy || {}).reference_usd) +
      mandateHtml(team, ui.mandateEdit) +
      '<section class="tm-sec"><div class="tm-qhead">' + esc(tw("teams.tab_team")) + "</div>" +
      '<label class="tm-rs tm-pin-row"><input type="checkbox" class="tm-pin-toggle"' + (team.pinned_at ? " checked" : "") +
      "><span>" + esc(tw("teams.pin_top")) + "</span></label>" + settingsFormHtml(team) + "</section>" +
      '<details class="tm-adv"' + (ui.advOpen ? " open" : "") + '><summary class="tm-adv-sum">' + esc(tw("teams.advanced")) +
      '</summary><div class="tm-sub">' + esc(tw("teams.advanced_note")) + "</div>" + capsFormHtml(team) + authorityHtml(team) +
      limitsHtml(team) + turnsHtml(ui.turns || [], team) + "</details>";
  }

  // Băng báo gọn, kèm nút giải quyết khi có: tạm dừng thì Bật lại, chưa có trưởng nhóm thì Chọn.
  function bannersHtml(team, teamNames) {
    var out = [];
    var one = function (text, btn) {
      return '<div class="tm-banner"><span>' + esc(text) + "</span>" + (btn || "") + "</div>";
    };
    if (team.status === "archived") out.push(one(tw("teams.archived_banner")));
    else if (team.status === "paused") {
      out.push(one(tw("teams.paused_banner"), '<button type="button" class="ws-btn" data-team-resume="1">' +
        esc(tw("teams.resume_team")) + "</button>"));
    }
    if (!team.leader_key) {
      out.push(one(tw("teams.no_leader"), '<button type="button" class="ws-btn" data-open-team="1">' +
        esc(tw("teams.pick")) + "</button>"));
    }
    Object.keys(team.busy || {}).forEach(function (k) {
      var other = team.busy[k];
      out.push(one(tw("teams.busy_elsewhere", { name: nameOf(team.members, k), team: (teamNames || {})[other] || other })));
    });
    return out.join("");
  }

  // Chip việc ở đầu khung chat: có việc chờ chủ thì "Cần bạn N" (màu cảnh báo), không thì "Việc N"; không có việc thì ẩn.
  // Chữ và số tách riêng để màn hẹp chỉ hiện icon kèm số.
  function jobsChip(q) {
    q = q || {};
    var blocked = (q.blocked || []).length;
    var all = (q.running || []).length + (q.waiting || []).length + blocked;
    if (!all) return null;
    return blocked ? { label: tw("teams.needs_you"), n: blocked, warn: true } : { label: tw("teams.tab_jobs"), n: all, warn: false };
  }

  function jobsChipHtml(q, open) {
    var c = jobsChip(q);
    if (!c) return "";
    return '<button type="button" class="tm-jobs-chip' + (c.warn ? " tm-jobs-chip-warn" : "") + '" data-open-jobs="1" aria-expanded="' +
      (open ? "true" : "false") + '" aria-label="' + esc(c.label + " " + c.n) + '">' + ic("list-todo") +
      '<span class="tm-chip-label">' + esc(c.label) + "</span>" +
      '<span class="tm-chip-n">' + c.n + "</span></button>";
  }

  // ───────────── phần chạy trong trình duyệt ─────────────

  function brain() {
    try {
      if (window.JavisSessions && window.JavisSessions.brain) return window.JavisSessions.brain();
      return (window.currentBrainPath && window.currentBrainPath()) || "brain";
    } catch (e) { return "brain"; }
  }

  function q(s) { return encodeURIComponent(s); }

  // 0.267.0 (a user's iPhone, 21/10/2026: "hay bị treo khung chat, thoát hẳn xong vào lại mới được"): a request sent
  // while the phone changes network, or right before the app goes to the background, can hang forever. Send kept its
  // button disabled waiting for it and nothing redrew, so only reopening the app helped. Every request now gives up after
  // CALL_MS and fails like a network error (a send that gave up is sent again with the same client id, never twice).
  var CALL_MS = 30000;
  function call(method, url, body) {
    var opt = { method: method, credentials: "same-origin" };
    if (body !== undefined) {
      opt.headers = { "Content-Type": "application/json" };
      opt.body = JSON.stringify(body);
    }
    var ctl = typeof AbortController !== "undefined" ? new AbortController() : null;
    var timer = null;
    if (ctl) { opt.signal = ctl.signal; timer = setTimeout(function () { ctl.abort(); }, CALL_MS); }
    var sep = url.indexOf("?") >= 0 ? "&" : "?";
    return fetch(url + sep + "brain=" + q(brain()), opt).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) { return { code: r.status, j: j || {} }; });
    }).then(function (x) { clearTimeout(timer); return x; }, function (e) { clearTimeout(timer); throw e; });
  }

  var S = null;

  function fresh(el) {
    return { el: el, teams: [], next: null, activeId: "", team: null, queue: null, msgs: [], hasMore: false,
      agents: [], asJob: false, pending: null, tab: "jobs", side: false, view: "list", loaded: false,
      filterTask: "", taskTitles: {}, teamNames: {}, note: "", skipped: {}, picker: null, draft: null,
      focusPicker: false, focusBack: null, searchOpen: false, searchResults: null, searchQuery: "", jumped: null,
      openMember: null, advOpen: false, turns: [], sideOpener: null, rowMenu: null, focusRowMenu: false, swallowClick: false,
      picked: [], retrying: {}, pickSt: null, pickOpener: null, pickHost: null, roster: [],
      renaming: "", renamingHead: false, replyTo: null, plusOpen: false, dict: null, dictBase: "", dictState: "idle",
      atts: [], folder: null, info: null, typing: [], pinned: [], pinsOpen: false, tagFilter: readTagFilter(),
      autoOpened: false, unclamped: {}, outbox: [] };
  }

  function teamUrl(path) { return "/teams/" + q(S.activeId) + (path || ""); }

  // Thông báo chung (lớp nổi trên cả trang, nhìn thấy cả khi đang ở danh sách): chữ, nút Thử lại khi có, nút đóng.
  function noteHtml(text, retry) {
    return '<span class="tm-note-text">' + esc(text) + "</span>" +
      (retry ? '<button type="button" class="ws-btn tm-note-retry">' + esc(tw("teams.retry_action")) + "</button>" : "") +
      '<button type="button" class="tm-note-close" aria-label="' + esc(tw("teams.close")) + '" title="' + esc(tw("teams.close")) +
      '">' + ic("x") + "</button>";
  }

  var noteTimer = null;
  // `retry`: hàm chạy lại thao tác vừa lỗi (nút Thử lại). Thông báo tự ẩn sau 8 giây, có Thử lại thì 15 giây.
  function setNote(text, retry) {
    S.note = text || "";
    S.noteRetry = S.note && typeof retry === "function" ? retry : null;
    clearTimeout(noteTimer);
    var n = S.el.querySelector(".tm-note");
    if (!n) return;
    n.innerHTML = S.note ? noteHtml(S.note, !!S.noteRetry) : "";
    n.hidden = !S.note;
    if (S.note) noteTimer = setTimeout(function () { if (S && S.note === text) setNote(""); }, S.noteRetry ? 15000 : 8000);
  }

  function fail(r) {
    setNote(tw("teams.err", { e: (r && r.j && r.j.error) || (r && r.code) || "?" }));
  }

  function shell() {
    S.el.innerHTML =
      '<div class="tm-page" data-view="' + S.view + '" data-side="0">' +
      '<aside class="tm-list"><div class="tm-bar tm-list-bar"><strong class="tm-list-title">' + esc(tw("page.teams.label")) + "</strong>" +
      '<button type="button" class="ws-btn tm-new">' + ic("plus") + esc(tw("teams.create")) + "</button>" +
      '<button type="button" class="ws-btn tm-import" title="' + esc(tw("teams.import_title")) + '">' + ic("upload-cloud") +
      esc(tw("teams.import")) + "</button></div>" +
      '<div class="cside-proj ws-nhom-bar tm-tagbar" hidden></div>' +
      '<div class="tm-teams"></div><button type="button" class="ws-btn tm-more-teams" hidden>' + esc(tw("teams.next_page")) + "</button></aside>" +
      '<section class="tm-chat"><div class="tm-bar tm-chat-head"></div><div class="tm-search" hidden></div>' +
      '<div class="tm-banners"></div><div class="tm-jobs" hidden></div>' +
      '<div class="tm-filterbar" hidden></div><div class="tm-pinbar" hidden></div><div class="tm-msgs" aria-live="polite"></div><div class="tm-composer"></div></section>' +
      // Vùng thông báo chung NGOÀI khung chat: trên điện thoại khung chat bị ẩn khi đang ở danh sách, thông báo (vd. ghim
      // lỗi) vẫn phải nhìn thấy (review 4f6268bd #2).
      '<aside class="tm-side" hidden></aside><div class="tm-scrim" hidden></div><div class="tm-note" role="status" aria-live="polite" hidden></div></div>';
  }

  function drawList() {
    var box = S.el.querySelector(".tm-teams");
    var rd = renameDraft(box);
    // 0.195.0: the tag filter. A tag no team carries any more (removed elsewhere) drops back to All.
    if (S.tagFilter && S.tagFilter !== TAG_NONE && !allTags(S.teams).some(function (x) { return x.key === S.tagFilter; })) {
      setTagFilter("");
    }
    var tb = S.el.querySelector(".tm-tagbar");
    // Shown once a team has a tag (or a filter is on): with no tag anywhere the bar would only say "All teams".
    if (tb) {
      tb.innerHTML = allTags(S.teams).length || S.tagFilter ? tagBarHtml(S.teams, S.tagFilter) : "";
      tb.hidden = !tb.innerHTML;
    }
    var shown = filterTeams(S.teams, S.tagFilter);
    if (box) box.innerHTML = S.loaded || S.teams.length ? (S.tagFilter && !shown.length ? '<p class="tm-empty">' +
      esc(tw("teams.tags_none")) + "</p>" : teamListHtml(shown, S.activeId, undefined, S.rowMenu, S.renaming, S.tagMenu)) : "";
    bindTagPicker(box);
    if (S.renaming) focusRename(box, rd);
    if (box && S.rowMenu && S.focusRowMenu) {
      S.focusRowMenu = false;
      var item = box.querySelector(".tm-row-menu [role=\"menuitem\"]");
      if (item) item.focus();
    }
    var more = S.el.querySelector(".tm-more-teams");
    if (more) more.hidden = !S.next;
    var bar = S.el.querySelector(".tm-list-bar");
    // Chưa có nhóm nào: thẻ hướng dẫn đã có nút Tạo nhóm, khỏi lặp nút ở thanh trên.
    if (bar) bar.classList.toggle("tm-list-bar-empty", S.loaded && !S.teams.length);
  }

  function drawPage() {
    var page = S.el.querySelector(".tm-page");
    if (page) page.setAttribute("data-view", S.view);
  }

  function drawHead() {
    var head = S.el.querySelector(".tm-chat-head");
    if (!head) return;
    var rd = renameDraft(head);
    var back = '<button type="button" class="ws-btn tm-back" aria-label="' + esc(tw("teams.back")) + '" title="' +
      esc(tw("teams.back")) + '">' + ic("chevron-left") + "</button>";
    if (!S.team) {
      head.innerHTML = "";
      head.hidden = true;
    } else {
      var t = S.team;
      var lead = headLine(t);
      head.hidden = false;
      // The name is a button: press it to rename the team in place (the old way hid renaming deep in the settings panel).
      var title = S.renamingHead ? '<div class="tm-title">' + renameInputHtml(t) + "</div>"
        : '<button type="button" class="tm-title tm-title-btn" data-rename-head="1" title="' + esc(tw("teams.rename_head")) + '">' +
          "<strong>" + esc(t.name) + '</strong><span class="tm-sub">' + esc(lead) + "</span></button>";
      // 0.191.0: the team picture opens the team info panel (members, files, links, working folder), like a chat app.
      head.innerHTML = back + '<button type="button" class="tm-ava-btn" data-team-info="1" aria-label="' + esc(tw("teams.info_open")) +
        '" title="' + esc(tw("teams.info_open")) + '">' + teamAvatarHtml(t, 36) + "</button>" + title +
        jobsChipHtml(S.queue, S.side && S.tab === "jobs") +
        '<button type="button" class="ws-btn tm-icon tm-search-btn" aria-label="' + esc(tw("teams.search")) + '" title="' +
        esc(tw("teams.search")) + '"' + (S.searchOpen ? ' aria-expanded="true"' : ' aria-expanded="false"') + ">" + ic("search") +
        "</button>" +
        '<button type="button" class="ws-btn tm-icon tm-gear" aria-expanded="' + (S.side && S.tab === "team" ? "true" : "false") +
        '" aria-label="' + esc(tw("teams.settings_btn")) + '" title="' + esc(tw("teams.settings_btn")) + '">' +
        ic("settings") + "</button>";
    }
    if (S.renamingHead) focusRename(head, rd);
    drawSearch();
    var b = S.el.querySelector(".tm-banners");
    if (b) b.innerHTML = S.team ? bannersHtml(S.team, S.teamNames) : "";
    drawFilterbar();
  }

  // Thanh tìm và kết quả, ngay dưới đầu khung chat (một vùng riêng, không vẽ lại khi có tin mới).
  function drawSearch() {
    var bar = S.el.querySelector(".tm-search");
    if (!bar) return;
    bar.hidden = !S.searchOpen || !S.team;
    if (bar.hidden) { bar.innerHTML = ""; return; }
    if (!bar.querySelector(".tm-search-input")) {
      bar.innerHTML = '<div class="tm-search-row"><input type="search" class="tm-search-input" maxlength="100" placeholder="' +
        esc(tw("teams.search_ph")) + '" aria-label="' + esc(tw("teams.search")) + '">' +
        '<button type="button" class="ws-btn tm-search-go">' + esc(tw("teams.search")) + "</button></div>" +
        '<div class="tm-search-list" role="list"></div>';
    }
    var list = bar.querySelector(".tm-search-list");
    if (list) list.innerHTML = searchResultsHtml(S.searchResults, S.team ? knownAuthors(S.team) : [], S.searchQuery);
  }

  // Đang lọc tin theo một việc: một băng nói rõ, kèm nút Xem tất cả (thay ô chọn lọc cũ).
  function drawFilterbar() {
    var bar = S.el.querySelector(".tm-filterbar");
    if (!bar) return;
    bar.hidden = !S.filterTask || !S.team;
    bar.innerHTML = bar.hidden ? "" : "<span>" + esc(tw("teams.filter_on", { title: S.taskTitles[S.filterTask] || S.filterTask })) +
      '</span><button type="button" class="ws-btn tm-filter-clear">' + esc(tw("teams.filter_clear")) + "</button>" +
      (S.taskDetail && S.taskDetail.task && S.taskDetail.task.id === S.filterTask ? taskQualityHtml(S.taskDetail) : "");
  }

  function runSearch() {
    var inp = S.el.querySelector(".tm-search-input");
    var qq = inp ? inp.value.trim() : "";
    if (qq.length < 2) { setNote(tw("teams.search_short")); return; }
    S.searchQuery = qq;
    var forTeam = S.activeId;
    call("GET", teamUrl("/search?q=" + q(qq))).then(function (r) {
      if (S.activeId !== forTeam) return;
      if (r.code !== 200) return fail(r);
      S.searchResults = r.j.results || [];
      drawSearch();
    });
  }

  // Nhảy tới một tin cũ: tải trang kết thúc ở đúng tin đó (tin đó và các tin trước), tô sáng, có nút về tin mới nhất.
  function jumpTo(mid, ts) {
    S.filterTask = "";
    var forTeam = S.activeId;
    return call("GET", teamUrl("/messages?before_ts=" + q(ts) + "&before_id=" + q(Number(mid) + 1))).then(function (r) {
      if (S.activeId !== forTeam) return;
      if (r.code !== 200) return fail(r);
      S.msgs = r.j.messages || [];
      S.hasMore = !!r.j.has_more;
      S.jumped = Number(mid);
      drawHead();
      drawMsgs(false);
      var hit = S.el.querySelector('[data-mid="' + Number(mid) + '"]');
      if (hit && hit.scrollIntoView) hit.scrollIntoView({ block: "center" });
    });
  }

  // Thành viên đang hoạt động cộng mọi tác giả trong sổ (cả người đã rời), cho chỗ chỉ cần tên người viết (kết quả tìm).
  function knownAuthors(team) {
    var out = (team.members || []).slice();
    Object.keys(team.authors || {}).forEach(function (k) {
      if (!memberOf(out, k)) out.push(Object.assign({ agent_key: k }, team.authors[k]));
    });
    return out;
  }

  function ctx(lastAgent) {
    var byId = {};
    (S.msgs || []).forEach(function (m) { byId[Number(m.id)] = m; });
    return { members: S.team ? S.team.members : [], authors: S.team ? S.team.authors : null, byId: byId,
      leaderKey: S.team && S.team.leader_key, taskTitles: S.taskTitles,
      picker: S.picker, jumped: S.jumped, retrying: S.retrying, lastAgent: lastAgent, unclamped: S.unclamped };
  }

  // Inline name editor: a redraw (new message, team event) must not wipe what is being typed. Read the box before the
  // redraw, put the text and the caret back after it.
  function renameDraft(root) {
    var inp = root && root.querySelector(".tm-rename-input");
    return inp ? { v: inp.value, a: inp.selectionStart, b: inp.selectionEnd } : null;
  }
  function focusRename(root, draft) {
    var inp = root && root.querySelector(".tm-rename-input");
    if (!inp) return;
    if (draft) inp.value = draft.v;
    if (inp === document.activeElement) return;
    try {
      inp.focus();
      if (draft && draft.a != null) inp.setSelectionRange(draft.a, draft.b);
      else inp.setSelectionRange(inp.value.length, inp.value.length);
    } catch (e) {}
  }

  // Lưu công tắc ghim: khoá trong lúc lưu; lưu được thì gọi `done`; HTTP khác 200 hay lỗi mạng thì trả công tắc về trạng
  // thái đã lưu, bật lại để người dùng thử lại, và gọi `failed` (lỗi mạng mang cờ `network`). Không để lỗi bị bỏ sót.
  function savePin(box, post, done, failed) {
    var want = !!box.checked;
    box.disabled = true;
    var undo = function (r) { box.checked = !want; box.disabled = false; failed(r); };
    return Promise.resolve().then(function () { return post(want); }).then(function (r) {
      if (!r || r.code !== 200) return undo(r || { code: 0, j: {} });
      box.disabled = false;
      done(r);
    }, function (err) { undo({ code: 0, j: {}, network: true, error: String(err && err.message || err) }); });
  }

  // ───────────── keyed update of the message list ─────────────
  // Every event (a message, a status, a reaction) used to rebuild the whole list, which wiped a text selection, an open
  // "Show more", a picture that had loaded, a half-typed field in a card, and the bubble under a finger mid-swipe. The list
  // is now a series of keyed items, each the HTML of one part (a message, its reply status rows, the bars on top); an
  // item whose HTML did not change keeps its nodes, a changed one is replaced in place, new ones are inserted where they
  // belong and gone ones removed. A full rebuild is left for the first draw and a team switch.

  // Reconcile `box` with `items` ([{ key, html }]) given the previous items (with their `nodes`), or rebuild when `prev`
  // is null. make(html) turns HTML into an array of nodes. Returns the items with their nodes, for the next call.
  // Pure DOM calls only (insertBefore, removeChild, appendChild, firstChild, nextSibling), so node tests can run it.
  function listSync(box, items, prev, make) {
    var usable = !!prev && prev.every(function (it) {
      return it.nodes.every(function (n) { return n.parentNode === box; });
    });
    var keep = box.lastChild && box.lastChild.classList && box.lastChild.classList.contains("jv-new-msg") ? box.lastChild : null;
    if (!usable) {
      while (box.firstChild) box.removeChild(box.firstChild);
      items.forEach(function (it) {
        it.nodes = make(it.html);
        it.nodes.forEach(function (n) { box.appendChild(n); });
      });
      if (keep) box.appendChild(keep);
      return items;
    }
    var old = {}, want = {};
    prev.forEach(function (it) { old[it.key] = it; });
    items.forEach(function (it) { want[it.key] = true; });
    prev.forEach(function (it) {
      if (!want[it.key]) it.nodes.forEach(function (n) { box.removeChild(n); });
    });
    var cursor = box.firstChild;
    items.forEach(function (it) {
      var was = old[it.key];
      if (was && was.html === it.html) {
        it.nodes = was.nodes;
        if (!it.nodes.length) return;
        if (it.nodes[0] === cursor) cursor = it.nodes[it.nodes.length - 1].nextSibling;
        else it.nodes.forEach(function (n) { box.insertBefore(n, cursor); });
        return;
      }
      if (was && was.nodes.length && was.nodes[0] === cursor) cursor = was.nodes[was.nodes.length - 1].nextSibling;
      it.nodes = make(it.html);
      it.nodes.forEach(function (n) { box.insertBefore(n, cursor); });
      if (was) was.nodes.forEach(function (n) { if (n.parentNode === box) box.removeChild(n); });
    });
    return items;
  }

  function htmlNodes(html) {
    if (!html) return [];
    var t = document.createElement("template");
    t.innerHTML = html;
    return Array.prototype.slice.call(t.content.childNodes);
  }

  // The keyed parts of the list for the open team: the bars on top, then each message and its reply status rows.
  // `lastAgent` is NOT baked into the HTML (it moves with every new answer and would replace the previous answer's
  // nodes, wiping a selection in it); drawMsgs marks it on the nodes instead.
  function listItems() {
    var list = S.msgs.filter(function (m) { return !S.skipped[m.id]; });
    var c = ctx(null);
    var items = [
      { key: "jumped", html: S.jumped !== null && S.jumped !== undefined ? '<div class="tm-jumped">' + esc(tw("teams.search_viewing")) +
        ' <button type="button" class="ws-btn tm-jump-back">' + ic("chevrons-down") + esc(tw("teams.search_back")) + "</button></div>" : "" },
      { key: "older", html: S.hasMore ? '<button type="button" class="ws-btn tm-older">' + esc(tw("teams.older")) + "</button>" : "" },
      { key: "empty", html: !list.length && !S.hasMore ? '<div class="tm-empty tm-empty-chat">' + esc(tw("teams.chat_empty")) + "</div>" : "" }];
    list.forEach(function (m) {
      var mm = m;
      if (S.skipped["p" + m.id] && m.meta && m.meta.proposal) mm = Object.assign({}, m, { meta: Object.assign({}, m.meta, { proposal: null }) });
      var h = messageHtml(mm, c);
      // An owner's message ends with its reply status rows: a key of their own, so a status change leaves the bubble alone.
      var rs = mm.author_kind === "owner" ? replyStatusHtml(mm, c) : "";
      if (rs && h.slice(-rs.length) === rs) {
        items.push({ key: "m" + m.id, html: h.slice(0, h.length - rs.length) });
        items.push({ key: "r" + m.id, html: rs });
      } else items.push({ key: "m" + m.id, html: h });
    });
    // The owner's messages still on their way, at the bottom (11: shown at once, replaced by the server's copy).
    pendingEntries().forEach(function (p) { items.push({ key: "p" + p.cid, html: pendingHtml(p) }); });
    return { items: items, list: list };
  }

  function drawMsgs(stick) {
    var box = S.el.querySelector(".tm-msgs");
    if (!box) return;
    drawPins();
    // T3 (6.2): khung tin của nhóm đang mở; pulse-seen.js đọc mã nhóm ở đây để báo tin của trợ lý đã được xem.
    if (S.team) box.setAttribute("data-seen-team", S.team.team_id); else box.removeAttribute("data-seen-team");
    if (!S.team) {
      S.listCache = null;
      box.innerHTML = S.teams.length ? '<div class="tm-empty tm-empty-chat">' + esc(tw("teams.pick_team")) + "</div>" : "";
      return;
    }
    var built = listItems();
    var prev = S.listCache && S.listCache.team === S.team.team_id && S.listCache.box === box ? S.listCache.items : null;
    S.listCache = { team: S.team.team_id, box: box, items: listSync(box, built.items, prev, htmlNodes) };
    // The latest assistant message keeps its Like button visible (like Zalo); older ones show it on hover.
    var lastAgent = null;
    for (var li = built.list.length - 1; li >= 0; li--) if (built.list[li].author_kind === "agent") { lastAgent = built.list[li].id; break; }
    Array.prototype.forEach.call(box.querySelectorAll(".tm-rx.is-last"), function (x) { x.classList.remove("is-last"); });
    var lastRx = lastAgent !== null ? box.querySelector('.tm-msg[data-mid="' + lastAgent + '"] .tm-rx') : null;
    if (lastRx) lastRx.classList.add("is-last");
    // The jump-to-latest button (chat-scroll.js) is the list's last child, so `position: sticky` keeps it at the bottom.
    if (S.scroll) { if (box.lastChild !== S.scroll.button) box.appendChild(S.scroll.button); S.scroll.update(); }
    applyReveal(box);
    // Bảng đang "mở" mà không vẽ ra (tin đã đổi, đã ghim): bỏ trạng thái mở, kẻo tin mới không còn tự cuộn xuống.
    if (S.picker !== null && !box.querySelector('[data-panel="' + S.picker + '"]')) S.picker = null;
    // Stick to the latest message like the main chat: `stick` (team opened, own message sent) jumps there; otherwise the
    // list follows only when the owner is already at the end, and holds while the mouse is on a message's buttons.
    if (S.picker === null) {
      if (stick) toLatest(true);
      else if (!S.scroll || S.scroll.stuck()) toLatest(false);
    }
    if (S.focusPicker) {
      // Mở bộ chọn: focus vào nút đầu của bảng (bàn phím và trình đọc màn hình vào được bảng, Escape đóng được).
      S.focusPicker = false;
      var first = box.querySelector(".tm-sheet .tm-rx-pick") || box.querySelector(".tm-sheet button");
      if (first) first.focus();
    }
    if (S.focusBack !== null && S.focusBack !== undefined) {
      var back = box.querySelector('.tm-rx-btn[data-rx-toggle="' + S.focusBack + '"]') ||
        box.querySelector('.tm-hact[data-reply="' + S.focusBack + '"]');
      S.focusBack = null;
      if (back) back.focus();
    }
  }

  // Scroll the message list to the latest message (chat-scroll.js; a plain jump when it is missing). Not forced: only when
  // the owner is at the end, and a message arriving while they read higher up turns the button into "New messages".
  function toLatest(force) {
    var box = S.el && S.el.querySelector(".tm-msgs");
    if (!box) return;
    if (S.scroll) S.scroll.toBottom(force);
    else box.scrollTop = box.scrollHeight;
  }

  function drawJobs() {
    var bar = S.el.querySelector(".tm-jobs");
    if (!bar) return;
    var h = S.team ? jobStripHtml(S.queue) : "";
    bar.hidden = !h;
    bar.innerHTML = h;
  }

  function drawComposer() {
    var box = S.el.querySelector(".tm-composer");
    if (!box) return;
    box.hidden = !S.team;
    if (box.hidden) { box.innerHTML = ""; return; }
    var old = box.querySelector(".tm-input");
    var draft = S.pending ? (S.pending.typed || S.pending.text) : old ? old.value : "";
    var off = S.team.status === "archived";
    box.innerHTML = '<div class="tm-typing" role="status" aria-live="polite" hidden></div>' +
      '<div class="tm-sug" role="listbox" id="tm-sug" aria-label="' + esc(tw("teams.mention_list")) + '" hidden></div>' +
      composerTopHtml() + '<div class="tm-calls" hidden></div><div class="tm-hint" hidden></div>' + plusMenuHtml(off) +
      '<div class="tm-row"><button type="button" class="tm-plus" aria-haspopup="menu" aria-expanded="' +
      (S.plusOpen ? "true" : "false") + '" aria-label="' + esc(tw("teams.plus")) + '" title="' + esc(tw("teams.plus")) + '"' +
      (off ? " disabled" : "") + ">" + ic("plus") + "</button>" +
      '<textarea class="tm-input" rows="1" aria-autocomplete="list" aria-controls="tm-sug" placeholder="' + esc(tw(S.asJob ? "teams.placeholder_job" : "teams.placeholder")) + '"' +
      (off ? " disabled" : "") + ">" + esc(draft) + "</textarea>" +
      '<button type="button" class="tm-mic' + (S.dictState !== "idle" ? " is-rec" : "") + '" aria-pressed="' +
      (S.dictState === "listening" ? "true" : "false") + '" aria-label="' + esc(tw(S.dictState === "idle" ? "teams.mic" : "teams.mic_stop")) +
      '" title="' + esc(tw(S.dictState === "idle" ? "teams.mic" : "teams.mic_stop")) + '"' + (off ? " disabled" : "") + ">" +
      ic(S.dictState === "idle" ? "mic" : "square") + "</button>" +
      '<button type="button" class="tm-send" aria-label="' + esc(tw("teams.send")) + '" title="' + esc(tw("teams.send")) + '">' +
      ic("send") + "</button></div>";
    grow(box.querySelector(".tm-input"));
    drawHint();
    drawTyping();
    if (S.focusComposer && !off) {
      S.focusComposer = false;
      var inp = box.querySelector(".tm-input");
      if (inp) { try { inp.focus(); } catch (e) {} }
    }
  }

  // Bars above the input: the message being replied to, and "this message becomes a job" while that mode is on.
  function composerTopHtml() {
    var h = "";
    if (S.replyTo) {
      h += '<div class="tm-replying"><span class="tm-replying-ico" aria-hidden="true">' + ic("quote") + '</span><div class="tm-replying-main"><b>' +
        esc(tw("teams.replying", { name: S.replyTo.who })) + '</b><span class="tm-replying-text">' + esc(S.replyTo.preview) +
        '</span></div><button type="button" class="tm-bar-x" data-reply-cancel="1" aria-label="' + esc(tw("teams.reply_cancel")) +
        '" title="' + esc(tw("teams.reply_cancel")) + '">' + ic("x") + "</button></div>";
    }
    h += chipsHtml();
    if (S.asJob) {
      h += '<div class="tm-jobmode">' + ic("list-todo") + '<span class="tm-replying-main">' + esc(tw("teams.as_job_on")) +
        '</span><button type="button" class="tm-bar-x tm-asjob" aria-label="' + esc(tw("teams.as_job_off")) + '" title="' +
        esc(tw("teams.as_job_off")) + '">' + ic("x") + "</button></div>";
    }
    return h;
  }

  // The "+" menu of the composer: Assign as a job (on/off), Mention an assistant, Search this team. Room for more later
  // without growing the composer row (the old always-visible "Assign job" pill took a third of a phone's width).
  function plusMenuHtml(off) {
    if (!S.plusOpen || off) return "";
    var item = function (attr, icon, label, checked) {
      return '<button type="button" ' + attr + ">" + ic(icon) + "<span>" + esc(label) + "</span>" +
        (checked ? '<span class="tm-plus-on">' + ic("check") + "</span>" : "") + "</button>";
    };
    return '<div class="tm-plus-menu" role="menu" aria-label="' + esc(tw("teams.plus")) + '">' +
      item('role="menuitem" data-plus-attach="1"', "paperclip", tw("teams.attach")) +
      item('role="menuitem" data-plus-folder="1"', "folder", tw("cp.pin_folder")) +
      item('role="menuitemcheckbox" aria-checked="' + (S.asJob ? "true" : "false") + '" class="tm-asjob" title="' +
        esc(tw("teams.as_job_title")) + '"', "list-todo", tw("teams.as_job"), S.asJob) +
      item('role="menuitem" data-insert-at="1"', "at-sign", tw("teams.mention_insert")) +
      item('role="menuitem" data-plus-search="1"', "search", tw("teams.search")) + "</div>";
  }

  function setPlus(open) {
    if (S.plusOpen === open) return;
    S.plusOpen = open;
    drawComposer();
    if (open) {
      var first = S.el.querySelector(".tm-plus-menu button");
      if (first) first.focus();
    }
  }

  // ───────────── mic: speak, the words land in the input (dictate.js) ─────────────

  function toggleMic() {
    var D = typeof window !== "undefined" && window.JavisDictate;
    if (!D) { setNote(tw("teams.mic_unsupported")); return; }
    if (S.dict && S.dict.active()) { S.dict.stop(); return; }
    if (S.dictState === "transcribing") return;
    var input = S.el.querySelector(".tm-input");
    S.dictBase = input ? input.value : "";
    var forTeam = S.activeId;
    S.dict = D.create({
      onText: function (text) {
        var inp = S.el.querySelector(".tm-input");
        if (!inp || S.activeId !== forTeam) return;
        inp.value = D.joinText(S.dictBase, text);
        S.pending = null;
        grow(inp);
        drawHint();
      },
      onState: function (st) {
        S.dictState = st;
        if (S.activeId !== forTeam) return;
        var btn = S.el.querySelector(".tm-mic");
        if (!btn) return;
        btn.classList.toggle("is-rec", st !== "idle");
        btn.setAttribute("aria-pressed", st === "listening" ? "true" : "false");
        var lab = tw(st === "idle" ? "teams.mic" : st === "transcribing" ? "teams.mic_busy" : "teams.mic_stop");
        btn.setAttribute("aria-label", lab); btn.title = lab;
        btn.innerHTML = ic(st === "idle" ? "mic" : st === "transcribing" ? "loader" : "square");
        if (st === "idle") { var inp = S.el.querySelector(".tm-input"); if (inp) inp.focus(); }
      },
      onError: function (code) {
        // 0.419.0: the phone's own speech service switched off (iOS Dictation) gets the note that says where to turn it on.
        var ios = D.isIOS && D.isIOS();
        setNote(tw(code === "denied" ? (ios ? "dict.denied_ios" : "teams.mic_denied")
          : code === "service" ? (ios ? "dict.service_ios" : "dict.service") : code === "unsupported" ? "teams.mic_unsupported"
          : code === "nothing" ? "dict.nothing" : "teams.mic_failed"));
      }
    });
    S.dict.start();
  }

  function stopMic() {
    if (S && S.dict && S.dict.active()) S.dict.stop();
  }

  // ───────────── reply to a message ─────────────

  // What a reply to message `m` carries: the author's name, the preview for the reply bar, the quote sent on top (just
  // `part` when the owner selected part of the message) and the assistant to call. Replying to an assistant also calls
  // that assistant (when nobody else is @-mentioned), so the correction lands with the one who wrote the answer.
  function replyTarget(m, part) {
    if (!m || !S.team) return null;
    var mine = m.author_kind === "owner";
    var author = mine ? null : (memberOf(S.team.members, m.author_ref) || (S.team.authors || {})[m.author_ref] || null);
    var who = mine ? tw("teams.owner") : author ? (author.name || author.slug || m.author_ref) : (m.author_ref || tw("teams.system"));
    var Q = quoteApi();
    var partShort = function (n) { return Q ? Q.xemTruoc(part, n) : part.replace(/\s+/g, " ").slice(0, n); };
    var active = author && memberOf(S.team.members, m.author_ref);
    return { id: Number(m.id), who: who, preview: part ? partShort(160) : plainPreview(m.content, 160),
      quote: who + ": " + (part || plainPreview(m.content, 280)),
      key: !mine && active && (!active.status || active.status === "active") ? m.author_ref : "" };
  }

  // A button of a JAVIS_CARD in an assistant's message (chat-card.js): its words are sent as the owner's reply to that
  // message, in this team (they used to go to the hidden main chat).
  function sendCardReply(btn, text) {
    var host = btn && btn.closest && btn.closest(".tm-msg");
    var target = host ? replyTarget(msgById(Number(host.getAttribute("data-mid"))), "") : null;
    text = String(text || "").trim();
    if (!target || !text || S.team.status === "archived") return;
    var Q = quoteApi();
    var body = { text: Q ? Q.ghep(target.quote, text) : text, mentions: target.key ? [target.key] : [], as_job: false,
      client_msg_id: newClientId() };
    var forTeam = S.activeId;
    var post = function () {
      return call("POST", teamUrl("/messages"), body).then(function (r) {
        if (S.activeId !== forTeam) return;
        if (r.code !== 200) { fail(r); return; }
        loadMsgs(false); loadQueue();
      }).catch(function () { setNote(tw("teams.err_network"), post); });   // retry sends the same client id: never twice
    };
    post();
  }

  function startReply(mid) {
    var m = msgById(Number(mid));
    if (!m || !S.team) return;
    // Part of the message selected: quote just that part, like the main chat (read before the redraw below drops it).
    var A = actsApi();
    var el = S.el.querySelector('.tm-msg[data-mid="' + Number(m.id) + '"]');
    S.replyTo = replyTarget(m, A && A.selectedIn && el ? A.selectedIn(el) : "");
    if (!S.replyTo) return;
    S.picker = null;
    S.pending = null;
    drawMsgs(false);
    drawComposer();
    // The reply bar makes the composer taller: keep the latest message in view when the owner was reading it.
    if (!S.scroll || S.scroll.stuck()) toLatest(false);
    var inp = S.el.querySelector(".tm-input");
    if (inp) { try { inp.focus(); } catch (e) {} }
  }

  // What Copy puts on the clipboard, the same as the main chat: an assistant's answer as its visible markdown (headings,
  // bold, links kept; hidden metadata blocks dropped), the owner's own words without the quote of an earlier message.
  function copyTextOf(m) {
    if (!m) return "";
    var text = String(m.content == null ? "" : m.content);
    if (m.author_kind === "owner") {
      var Q = quoteApi();
      return Q ? Q.tach(text).rest : text;
    }
    var vm = typeof window !== "undefined" && window.JavisVisibleMarkdown;
    return vm ? vm(text) : text;
  }

  function copyMsg(mid) {
    var m = msgById(Number(mid));
    if (!m) return;
    var A = actsApi();
    var text = copyTextOf(m);
    // chat-acts.js: clipboard API, or a textarea fallback on plain HTTP (a LAN or VPS address), so copying no longer
    // fails silently there. The note says whether it worked.
    var run = A && A.copy ? A.copy(text) : Promise.resolve(false);
    run.then(function (ok) { if (S) setNote(tw(ok ? "teams.copied" : "common.copy_fail")); });
    S.picker = null;
    drawMsgs(false);
  }

  // ───────────── rename and delete a team ─────────────

  function teamById(id) {
    if (S.team && S.team.team_id === id) return S.team;
    for (var i = 0; i < S.teams.length; i++) if (S.teams[i].team_id === id) return S.teams[i];
    return null;
  }

  function saveRename(id, value) {
    var t = teamById(id);
    var name = String(value || "").trim();
    S.renaming = ""; S.renamingHead = false;
    if (!t || !name || name === t.name) {
      if (t && !name) setNote(tw("teams.name_empty"));
      drawList(); drawHead();
      return;
    }
    call("PATCH", "/teams/" + q(id), { name: name }).then(function (r) {
      if (r.code !== 200) { fail(r); drawList(); drawHead(); return; }
      S.teams.forEach(function (x) { if (x.team_id === id) x.name = name; });
      S.teamNames[id] = name;
      if (S.team && S.team.team_id === id && r.j.team) S.team = r.j.team;
      drawList(); drawHead();
      if (S.side) drawSide(true);
    }, function () { setNote(tw("teams.err_network")); drawList(); drawHead(); });
  }

  // The server only deletes an archived team, so an active one is archived first, then deleted, after ONE confirmation.
  function deleteTeam(id) {
    var t = teamById(id);
    if (!t) return;
    if (typeof confirm === "function" && !confirm(tw("teams.delete_confirm", { name: t.name }))) return;
    var arch = t.status === "archived" ? Promise.resolve({ code: 200, j: {} })
      : call("PATCH", "/teams/" + q(id), { status: "archived" });
    arch.then(function (r) {
      if (r.code !== 200) return fail(r);
      return call("DELETE", "/teams/" + q(id)).then(function (r2) {
        if (r2.code !== 200) { fail(r2); loadTeams(false); return; }
        if (S.activeId === id) {
          S.activeId = ""; S.team = null; S.queue = null; S.msgs = []; S.view = "list"; S.side = false;
          S.picker = null; S.picked = []; S.filterTask = ""; S.turns = []; S.replyTo = null;
        }
        S.teams = S.teams.filter(function (x) { return x.team_id !== id; });
        drawAll(false);
        setNote(tw("teams.deleted", { name: t.name }));
        loadTeams(false);
      });
    }, function () { setNote(tw("teams.err_network")); });
  }

  // The assistant's own settings (the same editor as the Assistants page), opened over the chat.
  function openAgentSettings(slug) {
    if (!slug) return;
    S.picker = null;
    var St = typeof window !== "undefined" && window.JavisStudio;
    if (St && St.editAgent) {
      St.editAgent({ slug: slug }, { chatButton: true, onSaved: function () { loadTeam(); loadMsgs(false); } });
      return;
    }
    if (window.JavisWorkspace && window.JavisWorkspace.openCommand) window.JavisWorkspace.openCommand("agent", slug);
  }

  // Khung soạn một dòng, tự cao theo chữ tới khoảng năm dòng rồi cuộn trong.
  function grow(input) {
    if (!input) return;
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight || 0, INPUT_MAX_PX) + "px";
  }

  function currentScan() {
    var input = S.el.querySelector(".tm-input");
    return S.team ? mentionScan(input ? input.value : "", S.team.members, S.picked) : { keys: [], ambiguous: [] };
  }

  function currentMentions() { return currentScan().keys; }

  // ───────────── 0.192.0: answers appear as if typed ─────────────
  // Owner, 16/10/2026: "chữ đang xổ 1 phát ra cả 1 đống, anh muốn hiệu ứng chữ chạy người này gõ xong hết rồi người kia
  // gõ lần lượt ... hiện dần từng mảng từ trên xuống dưới cho nhanh". A NEW assistant message arriving live is shown one
  // block (paragraph, list item, code block) at a time, top to bottom, quickly; messages arriving together play one after
  // another in arrival order, the next one hidden until the previous is done. History, the owner's own messages, a hidden
  // tab and reduced motion show everything at once. State lives in S.rv so a redraw of the list keeps the progress.
  var REVEAL_STEP_MS = 110, REVEAL_MAX_STEPS = 40;
  function revealOff() {
    try {
      if (typeof document !== "undefined" && document.hidden) return true;
      return !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    } catch (e) { return true; }
  }
  function queueReveal(m) {
    if (!m || m.author_kind !== "agent" || revealOff()) return;
    S.rv = S.rv || { active: null, shown: 0, queue: [], timer: null };
    if (S.rv.active === null) { S.rv.active = Number(m.id); S.rv.shown = 0; }
    else S.rv.queue.push(Number(m.id));
  }
  function revealBlocks(msgEl) {
    var root = msgEl.querySelector(".tm-text .bubble") || msgEl.querySelector(".tm-text");
    if (!root) return [];
    var kids = Array.prototype.slice.call(root.children || []);
    return kids.length ? kids : [root];
  }
  function applyReveal(box) {
    var rv = S.rv;
    if (!rv || rv.active === null || !box) return;
    rv.queue.forEach(function (id) {
      var w = box.querySelector('[data-mid="' + id + '"]');
      if (w) w.classList.add("tm-rv-wait");
    });
    var el = box.querySelector('[data-mid="' + rv.active + '"]');
    if (!el) { nextReveal(); return; }
    var blocks = revealBlocks(el);
    el.classList.add("tm-rv-on");
    blocks.forEach(function (b, i) { b.classList.toggle("tm-rv-hide", i >= rv.shown); });
    if (!rv.timer) {
      rv.timer = setTimeout(function () {
        rv.timer = null;
        if (!S || S.rv !== rv) return;
        // Long answers keep a quick pace: never more than REVEAL_MAX_STEPS steps for one message.
        rv.shown += Math.max(1, Math.ceil(blocks.length / REVEAL_MAX_STEPS));
        if (rv.shown >= blocks.length) {
          el.classList.remove("tm-rv-on");
          blocks.forEach(function (b) { b.classList.remove("tm-rv-hide"); });
          nextReveal();
          return;
        }
        var msgs = S.el && S.el.querySelector(".tm-msgs");
        var atEnd = !S.scroll || S.scroll.stuck();
        applyReveal(msgs);
        if (atEnd) toLatest(false);
      }, REVEAL_STEP_MS);
    }
  }
  function nextReveal() {
    var rv = S.rv;
    if (!rv) return;
    if (rv.timer) { clearTimeout(rv.timer); rv.timer = null; }
    rv.active = rv.queue.length ? rv.queue.shift() : null;
    rv.shown = 0;
    var msgs = S.el && S.el.querySelector(".tm-msgs");
    if (!msgs) return;
    // Follow the next answer down only when the owner is at the latest message: reading higher up in the history, the
    // view stays where it is (it used to jump to the bottom at the end of every revealed answer).
    var atEnd = !S.scroll || S.scroll.stuck();
    var w = rv.active !== null ? msgs.querySelector('[data-mid="' + rv.active + '"]') : null;
    if (w) w.classList.remove("tm-rv-wait");
    if (rv.active !== null) applyReveal(msgs);
    if (atEnd) toLatest(false);
  }
  function stopReveal() {
    if (S && S.rv && S.rv.timer) clearTimeout(S.rv.timer);
    if (S) S.rv = null;
  }

  function markJobs(ids, state) {
    return call("POST", "/jobs/marks", { brain: brain(), ids: ids, state: state }).then(function (r) {
      if (r.code !== 200) return fail(r);
      if (state === "archived" && ids.indexOf(S.openFin) >= 0) S.openFin = null;
      return loadQueue();
    });
  }

  // ───────────── 0.192.0: pinned messages ─────────────
  // Owner, 16/10/2026: "làm chức năng ghim đoạn chat cho nó có tác dụng". Pinning already fed every member turn (the
  // decision book, team_runner._context) but nothing on screen showed it. A strip on top of the chat now shows the newest
  // pin, how many there are and that the whole team follows them; tap a pin to go to it, open the list to see all or unpin.
  function pinsHtml(pins, open, ctx) {
    pins = (pins || []).slice().reverse();      // newest first
    if (!pins.length) return "";
    var who = function (p) {
      if (p.author_kind === "owner") return tw("teams.owner");
      var a = memberOf(ctx.members, p.author_ref) || (ctx.authors || {})[p.author_ref];
      return a ? (a.name || a.slug) : (p.author_kind === "agent" ? p.author_ref : tw("teams.system"));
    };
    var pinRow = function (p, x) {
      return '<div class="tm-pin-row"><button type="button" class="tm-pin-go" data-jump="' + esc(p.id) + '" data-ts="' + esc(p.ts) +
        '" title="' + esc(tw("teams.quote_open")) + '"><b>' + esc(who(p)) + "</b>" + esc(plainPreview(p.content, 160)) + "</button>" +
        (x ? '<button type="button" class="tm-bar-x" data-decision="' + esc(p.id) + '" data-on="0" aria-label="' +
          esc(tw("teams.decision_unpin")) + '" title="' + esc(tw("teams.decision_unpin")) + '">' + ic("x") + "</button>" : "") + "</div>";
    };
    var pinTop = '<div class="tm-pin-head"><span class="tm-pin-ico" aria-hidden="true">' + ic("pin") + "</span>" +
      '<span class="tm-pin-title">' + esc(tw("teams.pins_title", { n: pins.length })) + "</span>" +
      '<span class="tm-pin-note">' + esc(tw("teams.pins_note")) + "</span>" +
      '<button type="button" class="tm-bar-x tm-pin-toggle" aria-expanded="' + (open ? "true" : "false") + '" aria-label="' +
      esc(tw(open ? "teams.pins_close" : "teams.pins_open")) + '" title="' + esc(tw(open ? "teams.pins_close" : "teams.pins_open")) + '">' +
      ic(open ? "chevron-up" : "chevron-down") + "</button></div>";
    return pinTop + (open ? '<div class="tm-pin-list">' + pins.map(function (p) { return pinRow(p, true); }).join("") + "</div>"
      : pinRow(pins[0], false));
  }
  function drawPins() {
    var el = S && S.el && S.el.querySelector(".tm-pinbar");
    if (!el) return;
    var h = S.team && !S.filterTask ? pinsHtml(S.pinned, !!S.pinsOpen, ctx(null)) : "";
    el.innerHTML = h;
    el.hidden = !h;
  }

  // ───────────── 0.192.0: who is writing right now ─────────────
  // Owner, 16/10/2026: "các agent khác nhau trong nhóm chat khi chat phải hiện trạng thái đang trả lời, nếu không thì sẽ
  // không biết ai đang trả lời". One strip above the input, like a group chat's "is typing": each member whose turn is at
  // the engine, with its picture. Fed by the team_typing event and by GET /teams/{id} when the chat opens.
  var TYPING_MAX = 4;
  function typingHtml(list, members) {
    var seen = {}, rows = [];
    (list || []).forEach(function (t) {
      if (!t || !t.agent_key || seen[t.agent_key]) return;
      seen[t.agent_key] = 1;
      rows.push(t);
    });
    if (!rows.length) return "";
    var shown = rows.slice(0, TYPING_MAX);
    return shown.map(function (t) {
      var m = memberOf(members, t.agent_key) || { name: t.agent_key };
      var name = m.name || m.slug || t.agent_key;
      var reply = /reply|volunteer/.test(String(t.role || ""));
      return '<span class="tm-typing-who">' + agentAva(m, 18) + '<span class="tm-typing-text">' +
        esc(tw(reply ? "teams.typing_reply" : "teams.typing_work", { name: name })) + "</span>" +
        '<span class="tm-dots" aria-hidden="true"><i></i><i></i><i></i></span></span>';
    }).join("") + (rows.length > TYPING_MAX
      ? '<span class="tm-typing-more">' + esc(tw("teams.typing_more", { n: rows.length - TYPING_MAX })) + "</span>" : "");
  }
  function drawTyping() {
    var el = S && S.el && S.el.querySelector(".tm-typing");
    if (!el) return;
    var h = S.team ? typingHtml(S.typing, S.team.members) : "";
    el.innerHTML = h;
    el.hidden = !h;
  }

  function drawHint() {
    var hintEl = S.el.querySelector(".tm-hint");
    if (!hintEl || !S.team) return;
    var sc = currentScan();
    var h = composerHint({ mentions: sc.keys, all: sc.all, ambiguous: sc.ambiguous, asJob: S.asJob, cap: (S.team.caps || {}).mentions,
      members: S.team.members, leaderKey: S.team.leader_key });
    hintEl.textContent = h.text;
    hintEl.hidden = !h.text;
    var calls = S.el.querySelector(".tm-calls");
    if (calls) {
      var ch = callsHtml(sc.keys, S.team.members, sc.all);
      calls.innerHTML = ch;
      calls.hidden = !ch;
    }
    hintEl.classList.toggle("tm-hint-bad", !h.ok);
    var send = S.el.querySelector(".tm-send");
    if (send) send.disabled = !h.ok || S.team.status === "archived";
  }

  // Đang gõ trong một ô chữ của ngăn (tên nhóm, số giới hạn, hộp quyền): đừng vẽ lại ngăn vì một sự kiện nhóm, kẻo mất
  // chữ đang gõ. Ô chọn (radio, checkbox) không tính: bấm xong vẽ lại là đúng.
  function typingIn(root) {
    var a = document.activeElement;
    if (!a || !root.contains(a)) return false;
    if (a.tagName === "TEXTAREA" || a.tagName === "SELECT") return true;
    return a.tagName === "INPUT" && !/^(radio|checkbox|button|submit)$/i.test(a.type || "");
  }

  function drawSide(force) {
    var side = S.el.querySelector(".tm-side");
    if (!side) return;
    if (!force && S.side && !side.hidden && typingIn(side)) return;
    side.hidden = !S.side || !S.team;
    var page = S.el.querySelector(".tm-page");
    if (page) page.setAttribute("data-side", side.hidden ? "0" : "1");
    var scrim = S.el.querySelector(".tm-scrim");
    if (scrim) scrim.hidden = side.hidden;
    if (side.hidden) { side.innerHTML = ""; return; }
    var keep = side.querySelector(".tm-side-body");
    var top = keep ? keep.scrollTop : 0;
    var tabs = ["info", "jobs", "team"].map(function (k) {
      return '<button type="button" class="tm-tab" role="tab" data-tab="' + k + '" aria-selected="' + (S.tab === k ? "true" : "false") +
        '">' + esc(tw(TAB_KEY[k])) + "</button>";
    }).join("");
    var body = S.tab === "info" ? infoTabHtml(S.team) : S.tab === "jobs" ? queueHtml(S.queue,
      { openFin: S.openFin, archOpen: S.archOpen, members: S.team ? S.team.members : [], accEdit: S.accEdit })
      : teamTabHtml(S.team, S.agents, { openMember: S.openMember, advOpen: S.advOpen, turns: S.turns, mandateEdit: S.mandateEdit });
    side.innerHTML = '<div class="tm-bar tm-side-bar"><div class="tm-tabs" role="tablist">' + tabs + "</div>" +
      '<button type="button" class="ws-btn tm-icon tm-close" aria-label="' + esc(tw("teams.close")) + '" title="' +
      esc(tw("teams.close")) + '">' + ic("x") + '</button></div><div class="tm-side-body" role="tabpanel" aria-label="' +
      esc(tw(TAB_KEY[S.tab])) + '">' + body + "</div>";
    var nb = side.querySelector(".tm-side-body");
    if (nb && keep) nb.scrollTop = top;
    attachSideResize(side);
    if (window.JavisPulse) {
      Array.prototype.forEach.call(side.querySelectorAll(".tm-pulse[data-pulse-slug]"), function (el) {
        var names = {};
        names[S.team.team_id] = S.team.name || "";
        window.JavisPulse.mount(el, { slug: el.getAttribute("data-pulse-slug"), brain: brain(),
          only: el.getAttribute("data-pulse-ctx"), teamNames: names });
      });
    }
    if (window.JavisAgentJudge && window.JavisAgentJudge.hydrate) window.JavisAgentJudge.hydrate(side);
  }

  function drawAll(stick) {
    drawPage(); drawList(); drawHead(); drawJobs(); drawMsgs(stick); drawComposer(); drawSide();
  }

  // Mở ngăn: nhớ nút đã mở (chip việc, ba chấm, nút trên băng hay thẻ việc) để lúc đóng trả focus về đúng nút đó.
  function openSide(tab, opener) {
    if (opener && opener.matches) S.sideOpener = opener.matches(".tm-jobs-chip") ? ".tm-jobs-chip"
      : opener.matches(".tm-gear") ? ".tm-gear" : opener.matches(".tm-ava-btn") ? ".tm-ava-btn" : null;
    S.side = true;
    S.tab = tab;
    drawSide(true);
    drawHead();
    if (tab === "team") loadAgents().then(function () { if (S.side && S.tab === "team") drawSide(); });
    if (tab === "info") { loadInfo(); loadFolder(); }
    var first = S.el.querySelector(".tm-side .tm-tab[aria-selected=\"true\"]");
    if (first) first.focus();
  }

  // Nút xử lý trên dòng lỗi của lượt trả lời (0.142.0).
  function replyAct(kind, slug, btn) {
    if (kind === "models") {
      if (typeof window !== "undefined" && window.JavisNav && window.JavisNav.go) window.JavisNav.go("models");
      return;
    }
    if (kind === "agent") {
      if (typeof window !== "undefined" && window.JavisWorkspace && window.JavisWorkspace.openCommand) {
        window.JavisWorkspace.openCommand("agent", slug);
      }
      return;
    }
    if (kind === "resume") return call("PATCH", teamUrl(), { status: "active" }).then(function (r) { act(r, drawAll); });
    // Giới hạn nằm ở Nâng cao của ngăn Nhóm; điều phối chọn trong danh sách thành viên của cùng ngăn.
    if (kind === "limits") S.advOpen = true;
    openSide("team", btn);
  }

  function closeSide() {
    S.side = false;
    drawSide(true);
    drawHead();
    var back = S.el.querySelector(S.sideOpener || ".tm-gear") || S.el.querySelector(".tm-gear");
    if (back) back.focus();
  }

  function learnTitles(qq) {
    if (!qq) return;
    ["running", "waiting", "blocked"].forEach(function (k) {
      (qq[k] || []).forEach(function (t) { S.taskTitles[t.id] = t.title; });
    });
  }

  function loadTeams(append) {
    var url = "/teams" + (append && S.next ? "?before=" + q(S.next) : "");
    return call("GET", url).then(function (r) {
      if (r.code !== 200) return fail(r);
      S.teams = append ? S.teams.concat(r.j.teams || []) : (r.j.teams || []);
      S.next = r.j.next || null;
      S.loaded = true;
      S.teams.forEach(function (t) { S.teamNames[t.team_id] = t.name; });
      drawList();
      if (!S.team) drawMsgs(false);
      // Có nhóm cần mở từ ngoài trang (bấm thư trong hộp thư): mở khi danh sách đã về.
      if (pendingOpen) {
        var want = pendingOpen, wantTask = pendingTask;
        pendingOpen = null; pendingTask = "";
        S.autoOpened = true;
        openTeam(want, wantTask);
      } else if (!append && !S.autoOpened && !S.activeId) {
        // 0.195.0 (owner, 17/10/2026: "khi vào team thì sẽ vào đoạn chat mà chủ team đang làm việc gần nhất"): opening
        // the page lands in the team worked in last. Once per visit: going back to the list stays on the list.
        S.autoOpened = true;
        var lastT = lastWorkedTeam(S.teams);
        if (lastT) openTeam(lastT.team_id);
      }
    });
  }

  var pendingOpen = null, pendingTask = "";
  // Mở một nhóm từ ngoài trang (hộp thư, thông báo đẩy về việc nhóm): đang ở trang Nhóm và danh sách đã về thì mở ngay;
  // chưa thì nhớ id, sang trang Nhóm, loadTeams() mở nó khi danh sách về.
  // `taskId` (0.142.0, tab Công việc ở trang Cộng sự): mở nhóm và lọc khung chat theo đúng việc đó.
  function open(teamId, taskId) {
    teamId = String(teamId || "");
    if (!teamId) return;
    pendingOpen = teamId; pendingTask = String(taskId || "");
    if (S && S.el && S.el.isConnected && S.loaded) {
      pendingOpen = null; pendingTask = "";
      openTeam(teamId, taskId);
      return;
    }
    if (typeof window !== "undefined" && window.JavisNav && window.JavisNav.go) window.JavisNav.go("teams");
  }

  function loadAgents() {
    return call("GET", "/resonance/agents").then(function (r) {
      if (r.code === 200) S.agents = r.j.agents || [];
    });
  }

  function loadQueue() {
    if (!S.activeId) return Promise.resolve();
    var forTeam = S.activeId;
    return call("GET", teamUrl("/queue")).then(function (r) {
      if (r.code !== 200 || S.activeId !== forTeam) return;
      S.queue = r.j;
      learnTitles(S.queue);
      drawHead(); drawJobs(); if (S.tab === "jobs") drawSide();
    });
  }

  // Nhóm đang mở vừa bị xoá (0.173.0: Javis xoá bằng công cụ javis_team, hay tab khác bấm xoá): đóng khung chat về trạng
  // thái trống thay vì giữ một nhóm không còn, ô soạn vẫn mở mà gửi tin nào cũng lỗi.
  function closeGone(id) {
    if (!S || S.activeId !== id) return;
    S.activeId = ""; S.team = null; S.queue = null; S.msgs = []; S.view = "list"; S.side = false;
    S.picker = null; S.draft = null; S.picked = []; S.filterTask = ""; S.turns = [];
    drawAll(false);
    setNote(tw("teams.gone"));
  }

  function loadTeam() {
    if (!S.activeId) return Promise.resolve();
    var forTeam = S.activeId;
    return call("GET", teamUrl()).then(function (r) {
      if (S.activeId !== forTeam) return;
      if (r.code === 404) return closeGone(forTeam);
      if (r.code !== 200) return fail(r);
      S.team = r.j.team;
      if (r.j.typing) S.typing = r.j.typing;
      S.pinned = r.j.pinned || [];
      drawHead(); drawHint(); drawSide(); drawTyping(); drawPins();
    });
  }

  function loadMsgs(older) {
    if (!S.activeId) return Promise.resolve();
    // Tải khúc mới nhất (gửi tin, lọc việc, về tin mới nhất): thoát chế độ xem tin cũ, tin mới tới lại được nối vào.
    if (!older) S.jumped = null;
    var url = S.filterTask ? teamUrl("/tasks/" + q(S.filterTask)) : teamUrl("/messages");
    if (older && S.msgs.length && !S.filterTask) url += "?before_ts=" + q(S.msgs[0].ts) + "&before_id=" + q(S.msgs[0].id);
    var forTeam = S.activeId;
    var forTask = S.filterTask;
    // 0.358.0 (owner: "gửi xong không thấy hiện câu của mình"): only the LATEST load of the newest page may replace the
    // list. An older load that answers late (the phone waking up, a reconnect) carries a list taken before the message
    // was stored, and used to wipe it off the screen.
    var seq = older ? S.msgsSeq : (S.msgsSeq = (S.msgsSeq || 0) + 1);
    return call("GET", url).then(function (r) {
      if (S.activeId !== forTeam || S.filterTask !== forTask || seq !== S.msgsSeq) return;
      if (r.code !== 200) return fail(r);
      var got = r.j.messages || [];
      if (!older && !forTask && got.length) {
        // Messages the socket brought while this load was on its way are newer than the page: keep them.
        var last = Number(got[got.length - 1].id);
        got = got.concat(S.msgs.filter(function (m) { return Number(m.id) > last; }));
      }
      // Lọc theo một việc đã xong (mở từ tab Công việc): việc không còn trong hàng đợi, học tên từ chính bản ghi việc để
      // thanh lọc và nhãn tin hiện tên việc thay vì mã (0.142.0).
      if (S.filterTask && r.j.task && r.j.task.id) {
        S.taskDetail = r.j;
        S.taskTitles[r.j.task.id] = r.j.task.title || S.taskTitles[r.j.task.id] || "";
        got.forEach(function (m) { if (m.task_id === r.j.task.id && !m.task_title) m.task_title = r.j.task.title || ""; });
        drawFilterbar();
      }
      S.msgs = older ? got.concat(S.msgs) : got;
      S.hasMore = !S.filterTask && !!r.j.has_more;
      // Older messages go in above what the owner is reading: keep them on the same message (the main chat does too).
      if (older && S.scroll) S.scroll.keep(function () { drawMsgs(false); });
      else drawMsgs(!older);
    });
  }

  function loadTurns() {
    if (!S.activeId) return Promise.resolve();
    var forTeam = S.activeId;
    return call("GET", teamUrl("/turns?since=" + (Date.now() / 1000 - 7 * 86400))).then(function (r) {
      if (S.activeId !== forTeam) return;
      if (r.code === 200) { S.turns = r.j.turns || []; if (S.side && S.tab === "team") drawSide(); }
    });
  }

  function openTeam(id, taskId) {
    S.jumped = null; S.searchResults = null; S.searchQuery = ""; S.searchOpen = false;
    S.activeId = id; S.view = "chat"; S.asJob = false; S.pending = null; S.filterTask = String(taskId || "");
    S.team = null; S.queue = null; S.msgs = []; S.taskTitles = {}; S.side = false; S.openMember = null; S.turns = [];
    S.picker = null; S.draft = null; S.picked = []; S.retrying = {};
    S.replyTo = null; S.plusOpen = false; S.renamingHead = false; forgetAtts(S.atts); S.atts = []; S.folder = null; S.info = null;
    S.typing = []; S.pinned = []; S.pinsOpen = false; S.unclamped = {}; S.listCache = null; S.outbox = []; stopReveal();
    closeFolderPanel();
    stopMic();
    var input = S.el.querySelector(".tm-input");
    if (input) input.value = "";
    setNote("");
    drawAll(true);
    Promise.all([loadTeam(), loadQueue(), loadMsgs(false)]).then(function () { if (S.activeId === id) { drawAll(true); loadFolder(); } });
    markOpened(id);
  }

  // 0.195.0: the owner works in this team now, so next visit (any device) opens it. Best effort: a failure changes nothing.
  // 0.197.0: the open team is read while the page is in front; one call per burst of messages.
  var readTimer = null;
  function readSoon() {
    clearTimeout(readTimer);
    readTimer = setTimeout(function () {
      if (S && S.activeId && S.el && S.el.isConnected && document.visibilityState !== "hidden") markOpened(S.activeId);
    }, 800);
  }
  // 0.267.0: back after AWAY_MS or more, the open team is read again from the server. On an iPhone the socket can come
  // back "open" but dead, so messages and answers that landed meanwhile never arrived and the chat looked frozen until
  // the app was closed (the main chat has done the same since 0.85.11). A short switch to another app reloads nothing.
  var AWAY_MS = 20000, hiddenAt = 0;
  function onVisible() {
    if (document.visibilityState === "hidden") { hiddenAt = Date.now(); return; }
    var away = hiddenAt && Date.now() - hiddenAt >= AWAY_MS;
    hiddenAt = 0;
    if (document.visibilityState === "visible" && S && S.activeId && S.el && S.el.isConnected) {
      markOpened(S.activeId);
      drawList();
      if (away) {
        if (S.jumped === null || S.jumped === undefined) loadMsgs(false);
        loadQueue(); loadTeam();
      }
    }
  }

  function markOpened(id) {
    var t = S.teams.filter(function (x) { return x.team_id === id; })[0];
    if (t) { t.owner_at = Date.now() / 1000; t.unread = { n: 0, at: 0 }; }
    call("POST", "/teams/" + q(id) + "/opened", {}).then(function () {}, function () {});
  }

  // The chosen tag filter is a per-device convenience (localStorage); a blocked storage only forgets it.
  var TAG_FILTER_KEY = "javis.teams.tagFilter";
  function readTagFilter() {
    try { return (typeof localStorage !== "undefined" && localStorage.getItem(TAG_FILTER_KEY)) || ""; } catch (e) { return ""; }
  }
  function setTagFilter(tag) {
    S.tagFilter = String(tag || "");
    try { if (typeof localStorage !== "undefined") localStorage.setItem(TAG_FILTER_KEY, S.tagFilter); } catch (e) {}
  }

  // The "Tag" picker of a team's row menu (0.195.0): tapping a tag adds or removes it, the box adds a new one; the menu
  // stays open so several tags can be set in one go, exactly like a partner's row menu.
  function bindTagPicker(box) {
    var TP = tagPicker();
    var m = box && S.tagMenu ? box.querySelector(".tm-tag-menu") : null;
    if (!TP || !m) return;
    var id = S.tagMenu;
    TP.bind(m, {
      back: function () { S.tagMenu = null; S.focusRowMenu = true; drawList(); },
      add: function (ten) { changeTags(id, [ten], [], TP.FOCUS_INPUT); },
      toggle: function (ten, on, key) { changeTags(id, on ? [] : [ten], on ? [key] : [], key); },
    }, S.tagFocus);
    S.tagFocus = null;
  }

  function changeTags(id, add, removeKeys, focusKey) {
    var t = S.teams.filter(function (x) { return x.team_id === id; })[0];
    if (!t || S.tagBusy) return;
    var next = (t.tags || []).filter(function (g) { return removeKeys.indexOf(tagKey(g)) < 0; }).concat(add);
    S.tagBusy = true;
    call("PATCH", "/teams/" + q(id), { tags: next }).then(function (r) {
      S.tagBusy = false;
      if (r.code !== 200 || !r.j || !r.j.team) return act(r);
      t.tags = r.j.team.tags || [];
      if (S.team && S.team.team_id === id) S.team.tags = t.tags;
      S.tagFocus = focusKey;
      drawList();
    }, function () { S.tagBusy = false; });
  }

  // ───────────── 0.191.0: files, working folder and the team info panel ─────────────
  // A team is a normal conversation underneath: its documents are that conversation's documents
  // (/sessions/{session_id}/assets) and its working folder is that conversation's pinned folder (/coding/session/...).

  // One file to /upload with progress and the main chat's stall watch (chat-upload.js): a dead connection is cut after
  // 30 s without a byte and retried, a server silent after the upload is reported, so a chip never spins forever and
  // Send is never blocked for good (it waits for busy chips). Resolves { code, j } like call(); rejects an Error with
  // `kind` once the retries are spent.
  function upload(file, a) {
    var U = typeof window !== "undefined" && window.JavisUpload;
    if (!U) {
      var fd0 = new FormData();
      fd0.append("file", file);
      fd0.append("brain", brain());
      return fetch("/upload", { method: "POST", body: fd0, credentials: "same-origin" }).then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (j) { return { code: r.status, j: j || {} }; });
      });
    }
    var tries = 0;
    var once = function () {
      var fd = new FormData();
      fd.append("file", file, (a && a.name) || file.name);
      fd.append("brain", brain());
      return U.send(fd, function (loaded, total) {
        if (!a) return;
        a.status = loaded < 0 ? tw("app.att_saving")
          : tw("app.att_progress", { pct: total ? Math.min(99, Math.floor(loaded * 100 / total)) : 0 });
        drawAttStatus(a);
      }).then(function (r) {
        var j = {};
        try { j = JSON.parse(r.text) || {}; } catch (e) { j = {}; }
        return { code: r.status, j: j };
      }, function (e) {
        var kind = (e && e.kind) || "net";
        if ((kind === "stall" || kind === "net") && tries < U.RETRIES) {
          tries++;
          if (a) { a.status = tw("app.att_retrying", { n: tries + 1 }); drawAttStatus(a); }
          return new Promise(function (res) { setTimeout(res, 1500 * tries); }).then(once);
        }
        throw e;
      });
    };
    return once();
  }

  // The words a failed upload shows on its chip (the main chat's wording).
  function uploadError(e) {
    var kind = (e && e.kind) || "net";
    if (kind === "server") return tw("app.att_server_slow");
    if (kind === "stall") return tw("app.att_stalled");
    if (kind === "client") return tw("app.att_client_err", { msg: String((e && (e.detail || e.message)) || e).slice(0, 80) });
    return tw("teams.err_network");
  }

  // Progress fires often: update the status words of that one chip in place (redrawing the composer would take the
  // focus out of the input the owner may be typing in).
  function drawAttStatus(a) {
    var i = S.atts.indexOf(a);
    var st = i >= 0 && S.el.querySelector('.tm-chip[data-att="' + i + '"] .tm-chip-st');
    if (st) st.textContent = a.status || tw("teams.uploading");
  }

  function startUpload(a) {
    a.busy = true; a.err = ""; a.status = "";
    upload(a.file, a).then(function (r) {
      a.busy = false;
      if (r.code !== 200 || !r.j.staged) a.err = (r.j && (r.j.error || r.j.detail)) || tw("teams.attach_err");
      else { a.path = r.j.staged; a.file = null; }
      drawComposer();
    }).catch(function (e) { a.busy = false; a.err = uploadError(e); drawComposer(); });
  }

  function pickFiles(onDone) {
    var inp = document.createElement("input");
    inp.type = "file"; inp.multiple = true;
    inp.addEventListener("change", function () { onDone(Array.prototype.slice.call(inp.files || [])); });
    inp.click();
  }

  function attachFiles(files) {
    files.slice(0, 10).forEach(function (f) {
      // The File stays on the chip until it is uploaded, so a failed chip can be sent again without picking it again.
      var a = { name: f.name, size: f.size, kind: /^image\//.test(f.type || "") ? "image" : "file", path: "", busy: true, err: "",
        file: f };
      // 0.192.0: a picture shows itself on its chip, like the main chat.
      if (a.kind === "image") { try { a.url = URL.createObjectURL(f); } catch (e) { a.url = ""; } }
      S.atts.push(a);
      startUpload(a);
    });
    drawComposer();
  }

  // ───────────── 0.192.0: paste and drop into the team chat ─────────────
  // Owner, 16/10/2026: "không copy và dán ảnh vào khung chat của team được". The main chat's paste and drop listeners sit on
  // the whole document and sent a picture pasted here to the hidden main chat. The team page answers first (its own
  // listeners, propagation stopped) and the page is marked data-localdrop so the main chat's drop leaves it alone.
  // Long-paste limits and the preview dialog are shared with the main chat (chat-paste.js).
  // Copy the bytes while the event is still running: a phone only lets a page read a pasted or dropped file then.
  function grabFile(f) {
    var read;
    try { read = f.arrayBuffer(); } catch (e) { return Promise.resolve(f); }
    return Promise.resolve(read).then(function (buf) {
      return buf && buf.byteLength
        ? new File([buf], f.name || "anh-dan.png", { type: f.type || "application/octet-stream", lastModified: f.lastModified || Date.now() })
        : f;
    }).catch(function () { return f; });
  }
  function canAttach() { return !!(S && S.team && S.team.status !== "archived" && S.el.querySelector(".tm-input")); }
  function attachGrabbed(list) {
    Promise.all(list.map(grabFile)).then(function (files) { if (canAttach()) attachFiles(files); });
  }
  function onPaste(e) {
    if (!canAttach()) return;
    var cd = e.clipboardData;
    var files = [];
    Array.prototype.forEach.call((cd && cd.items) || [], function (it) {
      if (it.kind === "file") { var f = it.getAsFile(); if (f) files.push(f); }
    });
    if (files.length) {
      e.preventDefault(); e.stopPropagation();
      attachGrabbed(files);
      return;
    }
    // Text up to the shared limit pastes normally. Past it, show the whole text and let the owner choose
    // paste inline / attach .txt / cancel, like the main chat (chat-paste.js, 0.430.1).
    var input = e.target;
    if (!(input && input.classList && input.classList.contains("tm-input"))) return;
    var paste = typeof window !== "undefined" ? window.JavisPaste : null;
    var txt = (cd && cd.getData("text/plain")) || "";
    if (!paste || !paste.isLong(txt)) return;
    e.preventDefault(); e.stopPropagation();
    var range = { start: input.selectionStart, end: input.selectionEnd };
    paste.offer(txt, function (value) {
      if (canAttach()) paste.insertAt(input, range, value);
    }, function (value) {
      if (canAttach()) attachFiles([paste.textFile(value)]);
    });
  }
  var dropDepth = 0;
  function hasFiles(e) {
    return !!(e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types || [], "Files") >= 0);
  }
  function markDrop(on) {
    var box = S && S.el && S.el.querySelector(".tm-composer");
    if (box) box.classList.toggle("is-drop", !!on);
  }
  function onDragEnter(e) { if (hasFiles(e) && canAttach()) { dropDepth++; markDrop(true); } }
  function onDragOver(e) { if (hasFiles(e) && canAttach()) { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; } }
  function onDragLeave() { if (--dropDepth <= 0) { dropDepth = 0; markDrop(false); } }
  function onDrop(e) {
    dropDepth = 0; markDrop(false);
    if (!hasFiles(e)) return;
    e.preventDefault(); e.stopPropagation();
    if (!canAttach()) return;
    attachGrabbed(Array.prototype.slice.call(e.dataTransfer.files || []));
  }
  function forgetAtts(list) {
    (list || []).forEach(function (a) { if (a && a.url) { try { URL.revokeObjectURL(a.url); } catch (e) {} } });
  }

  function chipsHtml() {
    var h = "";
    if (S.folder) {
      h += '<span class="tm-chip tm-chip-folder" title="' + esc(S.folder.path || S.folder.name) + '">' + ic("folder") +
        '<button type="button" class="tm-chip-name" data-folder-open="1">' + esc(S.folder.name) + "</button>" +
        '<button type="button" class="tm-chip-x" data-folder-unpin="1" aria-label="' + esc(tw("cp.pin_unpin")) + '" title="' +
        esc(tw("cp.pin_unpin")) + '">' + ic("x") + "</button></span>";
    }
    S.atts.forEach(function (a, i) {
      h += '<span class="tm-chip' + (a.err ? " is-err" : "") + (a.url ? " has-thumb" : "") + '" data-att="' + i + '">' +
        (a.url ? '<img class="tm-chip-thumb" src="' + esc(a.url) + '" alt="">' : ic(a.kind === "image" ? "image" : "paperclip")) +
        '<span class="tm-chip-name">' + esc(a.name) + "</span>" +
        (a.busy ? '<span class="tm-chip-st">' + esc(a.status || tw("teams.uploading")) + "</span>" : a.err ? '<span class="tm-chip-st">' + esc(a.err) + "</span>" : "") +
        // A failed upload: send the same file again from here (the main chat's chip retry).
        (a.err && a.file ? '<button type="button" class="tm-chip-x tm-chip-retry" data-att-retry="' + i + '" aria-label="' +
          esc(tw("app.att_retry")) + '" title="' + esc(tw("app.att_retry")) + '">' + ic("rotate-cw") + "</button>" : "") +
        '<button type="button" class="tm-chip-x" data-att-x="' + i + '" aria-label="' + esc(tw("teams.attach_remove")) + '" title="' +
        esc(tw("teams.attach_remove")) + '">' + ic("x") + "</button></span>";
    });
    return h ? '<div class="tm-attach-chips">' + h + "</div>" : "";
  }

  function sessionId() { return (S.team && S.team.session_id) || ""; }

  function loadFolder() {
    var sid = sessionId();
    if (!sid) return Promise.resolve();
    return fetch("/coding/session/" + q(sid) + "?brain=" + q(brain()), { credentials: "same-origin" })
      .then(function (r) { return r.json().catch(function () { return {}; }); }).then(function (d) {
        if (sessionId() !== sid) return;
        S.folder = (d && d.folder) || null;
        drawComposer();
        if (S.side && S.tab === "info") drawSide(true);
      }).catch(function () {});
  }

  function pinTeamFolder(p) {
    var sid = sessionId();
    if (!sid) return Promise.resolve("");
    var b = new FormData();
    b.append("path", p); b.append("brain", brain());
    return fetch("/coding/session/" + q(sid) + "/pin", { method: "POST", body: b, credentials: "same-origin" })
      .then(function (r) { return r.json().catch(function () { return {}; }); }).then(function (d) {
        if (!d || d.ok === false) return (d && d.error) || tw("cp.pin_failed");
        if (sessionId() === sid) { S.folder = d.folder || null; drawComposer(); if (S.side && S.tab === "info") drawSide(true); }
        return "";
      }).catch(function () { return tw("teams.err_network"); });
  }

  // The folder picker of the main chat (composer-folder.js), in a small pop-up above the team composer.
  function closeFolderPanel() {
    var pop = document.querySelector(".tm-folder-pop");
    if (pop) pop.remove();
    document.removeEventListener("mousedown", folderOutside, true);
    document.removeEventListener("keydown", folderEsc, true);
  }
  function folderOutside(e) { if (!(e.target.closest && e.target.closest(".tm-folder-pop"))) closeFolderPanel(); }
  function folderEsc(e) { if (e.key === "Escape") closeFolderPanel(); }
  function openFolderPanel() {
    var P = window.JavisPinnedFolder && window.JavisPinnedFolder.panelFor;
    var comp = S.el.querySelector(".tm-composer");
    if (!P || !comp || !S.team) return;
    closeFolderPanel();
    var r = comp.getBoundingClientRect();
    var pop = document.createElement("div");
    pop.className = "cp-menu tm-folder-pop";
    pop.style.left = Math.max(8, r.left + 8) + "px";
    pop.style.bottom = Math.max(8, window.innerHeight - r.top + 6) + "px";
    pop.innerHTML = '<div class="cp-mi cp-back">' + esc(tw("cp.pin_folder")) + '</div><div class="cp-sep"></div><div class="tm-folder-body"></div>';
    document.body.appendChild(pop);
    P({ brain: brain, current: function () { return S.folder; }, pin: pinTeamFolder,
      focus: function () { var i = S.el.querySelector(".tm-input"); if (i) i.focus(); } })(pop.querySelector(".tm-folder-body"),
      { close: closeFolderPanel });
    setTimeout(function () {
      document.addEventListener("mousedown", folderOutside, true);
      document.addEventListener("keydown", folderEsc, true);
    }, 0);
  }

  function loadInfo() {
    var sid = sessionId();
    if (!sid) return Promise.resolve();
    return fetch("/sessions/" + q(sid) + "/assets?brain=" + q(brain()), { credentials: "same-origin" })
      .then(function (r) { return r.json().catch(function () { return {}; }); }).then(function (d) {
        if (sessionId() !== sid) return;
        S.info = { files: (d && d.files) || [], links: (d && d.links) || [], err: d && d.ok === false ? (d.error || "") : "" };
        if (S.side && S.tab === "info") drawSide(true);
      }).catch(function () { S.info = { files: [], links: [], err: tw("teams.err_network") }; if (S.side && S.tab === "info") drawSide(true); });
  }

  function assetPost(path, form) {
    var sid = sessionId();
    if (!sid) return Promise.resolve();
    return fetch("/sessions/" + q(sid) + "/assets" + path, { method: "POST", body: form || new FormData(), credentials: "same-origin" })
      .then(function (r) { return r.json().catch(function () { return {}; }); })
      .then(function (d) { if (d && d.ok === false) setNote(d.error || tw("teams.err_generic")); return loadInfo(); })
      .catch(function () { setNote(tw("teams.err_network")); });
  }

  function addTeamLink() {
    var inp = S.el.querySelector(".tm-info-link");
    var url = inp ? inp.value.trim() : "";
    if (!url) { if (inp) inp.focus(); return; }
    if (!/^https?:\/\//i.test(url)) url = "https://" + url;
    var f = new FormData();
    f.append("url", url); f.append("label", "");
    assetPost("/links", f);
  }

  function addTeamFiles(files) {
    if (!files.length || !S.team) return;
    setNote(tw("teams.uploading"));
    Promise.all(files.slice(0, 10).map(function (f) {
      return upload(f).then(function (r) { return r.code === 200 && r.j.staged ? { path: r.j.staged, name: f.name } : null; })
        .catch(function () { return null; });
    })).then(function (got) {
      var atts = got.filter(Boolean);
      if (!atts.length) { setNote(tw("teams.attach_err")); return; }
      return call("POST", teamUrl("/files"), { attachments: atts }).then(function (r) {
        setNote(r.code === 200 ? "" : ((r.j && r.j.error) || tw("teams.attach_err")));
        loadInfo();
      });
    });
  }

  // The info panel (0.191.0): who is in the team, the working folder, pictures, files and links shared in it.
  function infoTabHtml(t) {
    if (!t) return "";
    var I = S.info;
    var members = (t.members || []).filter(function (m) { return m.status !== "left"; });
    var h = '<div class="tm-info-head">' + teamAvatarHtml(t, 64) + '<div class="tm-info-name"><strong>' + esc(t.name) + "</strong>" +
      (t.description ? '<span class="tm-sub">' + esc(t.description) + "</span>" : "") + "</div></div>";
    h += '<section class="tm-info-sec"><h4>' + esc(tw("teams.info_members", { n: members.length + 1 })) + '</h4><ul class="tm-info-members">' +
      '<li>' + avaHtml(tw("teams.you")) + "<span>" + esc(tw("teams.you")) + "</span></li>" +
      members.map(function (m) {
        return "<li>" + agentAva(m, 28) + "<span>" + esc(m.name || m.slug) + "</span>" +
          (m.agent_key && m.agent_key === t.leader_key ? '<span class="tm-info-badge">' + esc(tw("teams.leader_badge")) + "</span>" : "") +
          (m.slug ? '<button type="button" class="tm-bar-x tm-info-chat" data-agent-chat="' + esc(m.slug) + '" aria-label="' +
            esc(tw("teams.chat_private")) + '" title="' + esc(tw("teams.chat_private")) + '">' + ic("message-circle") + "</button>" : "") + "</li>";
      }).join("") + "</ul></section>";
    h += '<section class="tm-info-sec"><h4>' + esc(tw("teams.info_folder")) + "</h4>" + (S.folder
      ? '<div class="tm-info-row">' + ic("folder") + '<span class="tm-info-grow" title="' + esc(S.folder.path) + '">' + esc(S.folder.name) +
        '</span><button type="button" class="ws-btn" data-folder-open="1">' + esc(tw("teams.change")) + "</button></div>"
      : '<button type="button" class="ws-btn" data-folder-open="1">' + ic("folder") + " " + esc(tw("cp.pin_folder")) + "</button>") + "</section>";
    if (!I) return h + '<p class="tm-sub">' + esc(tw("common.loading")) + "</p>";
    var imgs = I.files.filter(function (f) { return f.image; });
    var docs = I.files.filter(function (f) { return !f.image; });
    if (imgs.length) {
      h += '<section class="tm-info-sec"><h4>' + esc(tw("teams.info_images", { n: imgs.length })) + '</h4><div class="tm-info-imgs">' +
        imgs.slice(0, 12).map(function (f) {
          return '<a class="jv-img-link" href="' + esc(rawUrl(f.brain_path || f.path)) + '" data-img-ten="' + esc(f.name) +
            '" target="_blank" rel="noopener" title="' + esc(f.name) + '"><img src="' +
            esc(rawUrl(f.brain_path || f.path)) + '" alt="" loading="lazy" onerror="jvImgGone(this)"></a>';
        }).join("") + "</div></section>";
    }
    h += '<section class="tm-info-sec"><div class="tm-info-sechead"><h4>' + esc(tw("teams.info_files", { n: docs.length })) + "</h4>" +
      '<button type="button" class="ws-btn" data-info-add-file="1">' + ic("plus") + " " + esc(tw("teams.info_add_file")) + "</button></div>" +
      (docs.length ? '<ul class="tm-info-list">' + docs.map(function (f) {
        return '<li><a href="' + esc(rawUrl(f.brain_path || f.path)) + '" target="_blank" rel="noopener">' + ic("file-text") + "<span>" +
          esc(f.label || f.name) + "</span></a>" + (f.manual && f.id ? '<button type="button" class="tm-chip-x" data-info-del-file="' + esc(f.id) +
          '" aria-label="' + esc(tw("teams.info_remove")) + '" title="' + esc(tw("teams.info_remove")) + '">' + ic("x") + "</button>" : "") + "</li>";
      }).join("") + "</ul>" : '<p class="tm-sub">' + esc(tw("teams.info_no_files")) + "</p>") + "</section>";
    h += '<section class="tm-info-sec"><h4>' + esc(tw("teams.info_links", { n: I.links.length })) + "</h4>" +
      '<div class="tm-info-addlink"><input type="url" class="tm-info-link" placeholder="' + esc(tw("teams.info_link_ph")) + '">' +
      '<button type="button" class="ws-btn" data-info-add-link="1">' + esc(tw("teams.info_add")) + "</button></div>" +
      (I.links.length ? '<ul class="tm-info-list">' + I.links.map(function (l) {
        return '<li><a href="' + esc(l.url) + '" target="_blank" rel="noopener">' + ic("link") + "<span>" + esc(l.label || l.url) + "</span></a>" +
          (l.manual && l.id ? '<button type="button" class="tm-chip-x" data-info-del-link="' + esc(l.id) + '" aria-label="' +
            esc(tw("teams.info_remove")) + '" title="' + esc(tw("teams.info_remove")) + '">' + ic("x") + "</button>" : "") + "</li>";
      }).join("") + "</ul>" : '<p class="tm-sub">' + esc(tw("teams.info_no_links")) + "</p>") + "</section>";
    if (I.err) h += '<p class="tm-sub">' + esc(I.err) + "</p>";
    return h;
  }

  function send() {
    var input = S.el.querySelector(".tm-input");
    if (!input || !S.team) return;
    var typed = input.value.trim();
    if (S.atts.some(function (a) { return a.busy; })) { setNote(tw("teams.attach_wait")); return; }
    // A file that failed to upload is not dropped silently: remove it or send it again first (main chat wording).
    if (S.atts.some(function (a) { return a.err; })) { setNote(tw("app.att_failed_send")); return; }
    var atts = S.atts.filter(function (a) { return a.path && !a.err; });
    if (!typed && !atts.length) return;
    stopMic();
    var scan = mentionScan(typed, S.team.members, S.picked);
    if (scan.ambiguous.length) { drawHint(); return; }
    var mentions = scan.keys;
    // A reply carries the quoted message as a markdown quote on top (the same convention as the main chat, so every
    // engine reads it and history shows it), and calls the assistant being replied to when nobody is @-mentioned.
    var Q = quoteApi();
    var text = S.replyTo && Q ? Q.ghep(S.replyTo.quote, typed) : typed;
    if (S.replyTo && S.replyTo.key && !mentions.length) mentions = [S.replyTo.key];
    // The message shows at once as a pending bubble keyed by its client id; the server's copy replaces it when it
    // arrives. A retry after a dropped connection sends the SAME client id, so the server returns the message it may
    // already have stored instead of adding a turn.
    var entry = { cid: newClientId(), text: text, typed: typed, atts: atts, replyTo: S.replyTo, asJob: S.asJob, picked: S.picked,
      ts: Date.now() / 1000, state: "sending", err: "" };
    var body = { text: text, mentions: mentions, as_job: S.asJob, client_msg_id: entry.cid };
    if (scan.all) body.mention_all = true;
    if (atts.length) body.attachments = atts.map(function (a) { return { path: a.path, name: a.name, kind: a.kind }; });
    entry.body = body;
    // Sent while the chat shows one job only: the message belongs to the whole chat, so go back to it (like any
    // messaging app) instead of a filtered list that would never show it.
    if (S.filterTask) { S.filterTask = ""; S.taskDetail = null; drawFilterbar(); }
    S.outbox.push(entry);
    // The composer is free again right away, like any messaging app.
    S.pending = null; S.asJob = false; S.picked = []; S.replyTo = null; S.plusOpen = false; input.value = ""; S.atts = [];
    drawComposer();
    var again = S.el.querySelector(".tm-input");
    if (again) again.focus();
    drawMsgs(true);
    postEntry(entry);
  }

  // POST one outbox message. 200: kept as "sent" until the server's copy is on screen. Refused (4xx) while the composer
  // is still empty: the draft goes back into the composer with the error, as before. Network error, timeout or 5xx: the
  // bubble turns "Not sent" with Try again.
  function postEntry(entry) {
    var forTeam = S.activeId;
    entry.state = "sending"; entry.err = "";
    var failed = function (why) {
      if (S.activeId !== forTeam || S.outbox.indexOf(entry) < 0) return;
      entry.state = "failed"; entry.err = why;
      drawMsgs(false);
    };
    call("POST", teamUrl("/messages"), entry.body).then(function (r) {
      if (S.activeId !== forTeam || S.outbox.indexOf(entry) < 0) return;
      if (r.code === 200) {
        entry.state = "sent";
        entry.mid = r.j.message_id;
        if (entry.atts.length && S.side && S.tab === "info") loadInfo();
        setNote(r.j.notes && r.j.notes.length ? r.j.notes.filter(function (n) { return !/^[a-z_]+$/.test(n); }).join(" · ") : "");
        if ((r.j.notes || []).indexOf("daily_cap") >= 0) setNote(tw("teams.daily_cap"));
        // The bubble goes only once the server's copy is on screen (`pendingEntries` hides it then); a load that failed
        // or answered late no longer takes the owner's message away with it.
        loadMsgs(false).then(function () { pruneOutbox(); drawMsgs(false); });
        loadQueue();
        return;
      }
      var inp = S.el.querySelector(".tm-input");
      if (r.code >= 400 && r.code < 500 && inp && !inp.value.trim() && !S.atts.length && !S.replyTo) {
        dropEntry(entry, false);
        inp.value = entry.typed;
        S.atts = entry.atts; S.replyTo = entry.replyTo; S.asJob = entry.asJob; S.picked = entry.picked;
        drawComposer(); drawMsgs(false);
        fail(r); drawHint();
        return;
      }
      failed(tw("teams.err", { e: (r.j && r.j.error) || r.code || "?" }));
    }).catch(function () { failed(tw("teams.err_network")); });
  }

  // Take a message out of the outbox. `done`: delivered, so its picture previews are released.
  function dropEntry(entry, done) {
    var i = S.outbox.indexOf(entry);
    if (i >= 0) S.outbox.splice(i, 1);
    if (done) forgetAtts(entry.atts);
  }

  // Delivered messages whose server copy is now in the list leave the outbox (their picture previews are released).
  function pruneOutbox() {
    var have = {}, ids = {};
    S.msgs.forEach(function (m) { if (m.client_msg_id) have[m.client_msg_id] = true; ids[Number(m.id)] = true; });
    S.outbox.slice().forEach(function (p) {
      if (p.state === "sent" && (have[p.cid] || (p.mid && ids[Number(p.mid)]))) dropEntry(p, true);
    });
  }

  // Outbox messages the server's copy has not replaced yet (it can arrive over the socket before the POST answers).
  function pendingEntries() {
    var have = {}, ids = {};
    S.msgs.forEach(function (m) { if (m.client_msg_id) have[m.client_msg_id] = true; ids[Number(m.id)] = true; });
    return S.outbox.filter(function (p) { return !have[p.cid] && !(p.mid && ids[Number(p.mid)]); });
  }

  // The owner's message while it is on its way: same bubble as a sent one, a quiet "Sending..." under it, or "Not sent"
  // with Try again and Remove.
  function pendingHtml(p) {
    var failed = p.state === "failed";
    var fake = { id: "", ts: p.ts, author_kind: "owner", content: p.text, meta: {} };
    var files = (p.atts || []).map(function (a) {
      return '<span class="tm-file' + (a.url ? " is-img" : "") + '">' + (a.url ? '<img src="' + esc(a.url) + '" alt="">' : ic("file-text")) +
        "<span>" + esc(a.name) + "</span></span>";
    }).join("");
    var st = failed
      // Short on screen ("Not sent"); the reason (no network, the server's error) in the tooltip.
      ? ic("triangle-alert") + '<span class="tm-pending-why" title="' + esc(p.err || "") + '">' + esc(tw("teams.send_failed")) + "</span>" +
        '<button type="button" class="ws-btn tm-pending-retry" data-out-retry="' + esc(p.cid) + '">' + esc(tw("teams.retry_action")) +
        '</button><button type="button" class="tm-bar-x" data-out-drop="' + esc(p.cid) + '" aria-label="' + esc(tw("teams.send_remove")) +
        '" title="' + esc(tw("teams.send_remove")) + '">' + ic("x") + "</button>"
      // Delivered but its server copy not on screen yet (a load failed or is late): say so, never "Sending..." forever.
      : "<span>" + esc(tw(p.state === "sent" ? "teams.sent_ok" : "app.sending")) + "</span>";
    return '<div class="tm-msg tm-msg-owner tm-msg-pending' + (failed ? " is-failed" : "") + '" data-cid="' + esc(p.cid) + '">' +
      '<div class="tm-col"><div class="tm-bubble">' + bodyHtml(fake, true) + (files ? '<div class="tm-files">' + files + "</div>" : "") +
      '</div><div class="tm-pending-st" role="status">' + st + "</div></div></div>";
  }

  // "@" đứng sau một chữ/số là địa chỉ email ("ho@lan.vn"), không mở gợi ý và không gọi ai.
  function emailBefore(before) {
    var m = String(before || "").match(/(^|[\s\S])@[^\s@]*$/);
    if (!m) return false;
    return !!m[1] && /[\p{L}\p{N}_.+-]/u.test(m[1]);
  }

  function suggestQuery(input) {
    var before = input.value.slice(0, input.selectionStart || 0);
    var m = before.match(/@([^\s@]*)$/);
    if (!m || emailBefore(before)) return null;
    return m[1];
  }

  function suggest() {
    var input = S.el.querySelector(".tm-input");
    var box = S.el.querySelector(".tm-sug");
    if (!input || !box || !S.team) return;
    var query = suggestQuery(input);
    if (query === null) { hideSug(); return; }
    var list = mentionMatches(S.team.members, query, mentionsFromText(input.value, S.team.members, S.picked));
    var seen = {};
    (S.team.members || []).forEach(function (a) {
      if (a.status && a.status !== "active") return;
      var n = foldName(a.name || a.slug).trim();
      seen[n] = (seen[n] || 0) + 1;
    });
    var activeN = (S.team.members || []).filter(function (a) { return !a.status || a.status === "active"; }).length;
    var withAll = activeN > 1 && ALL_TOKEN.indexOf(foldName(query).trim()) === 0;
    if (withAll) list = [{ agent_key: "*all", name: "@" + ALL_TOKEN, title: tw("teams.mention_all", { n: activeN }), all: true }].concat(list);
    S.sugKeys = list.map(function (a) { return a.agent_key; });
    if (S.sugIdx == null || S.sugIdx >= list.length) S.sugIdx = 0;
    box.hidden = !list.length;
    input.setAttribute("aria-expanded", list.length ? "true" : "false");
    box.innerHTML = list.map(function (a, i) {
      // Trùng tên: thêm mã ngắn (slug) để chọn đúng người. Vai của trợ lý (dòng "role" ở Cộng sự) nằm dưới tên.
      var dup = !a.all && seen[foldName(a.name || a.slug).trim()] > 1;
      var on = i === S.sugIdx;
      return '<button type="button" class="tm-sug-item' + (on ? " is-active" : "") + '" role="option" id="tm-sug-' + i +
        '" aria-selected="' + (on ? "true" : "false") + '" data-mention="' + esc(a.agent_key) + '">' +
        (a.all ? '<span class="tm-sug-all" aria-hidden="true">' + ic("users") + "</span>" : agentAva(a, 28)) +
        '<span class="tm-sug-text"><span class="tm-sug-name">' + esc(a.name || a.slug) +
        (dup ? ' <span class="tm-sug-slug">' + esc(a.slug) + "</span>" : "") + "</span>" +
        (a.title ? '<span class="tm-sug-role">' + esc(a.title) + "</span>" : "") + "</span></button>";
    }).join("");
    if (list.length) input.setAttribute("aria-activedescendant", "tm-sug-" + S.sugIdx);
    else input.removeAttribute("aria-activedescendant");
  }

  function hideSug() {
    var box = S.el.querySelector(".tm-sug");
    if (box) box.hidden = true;
    S.sugKeys = []; S.sugIdx = 0;
    var input = S.el.querySelector(".tm-input");
    if (input) { input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant"); }
  }

  // Phím khi danh sách gợi ý đang mở: lên/xuống chọn, Enter hay Tab chèn người đang chọn, Escape đóng. Trả true khi đã
  // xử lý (khung soạn không gửi tin, ngăn bên không đóng). Đang gõ bằng bộ gõ (IME) thì không can thiệp.
  function sugKey(e) {
    var box = S.el.querySelector(".tm-sug");
    if (!box || box.hidden || !(S.sugKeys || []).length || e.isComposing || e.keyCode === 229) return false;
    var n = S.sugKeys.length;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      S.sugIdx = ((S.sugIdx || 0) + (e.key === "ArrowDown" ? 1 : n - 1)) % n;
      suggest();
      return true;
    }
    if ((e.key === "Enter" && !e.shiftKey) || e.key === "Tab") {
      e.preventDefault();
      pickMention(S.sugKeys[S.sugIdx || 0]);
      return true;
    }
    if (e.key === "Escape") {
      e.preventDefault();
      hideSug();
      return true;
    }
    return false;
  }

  function pickMention(key) {
    var input = S.el.querySelector(".tm-input");
    if (input && key === "*all") {
      // @all is read from the text itself (mentionScan), so it needs no picked entry.
      var at = input.selectionStart || input.value.length;
      var upto = input.value.slice(0, at).replace(/@([^\s@]*)$/, "@" + ALL_TOKEN + " ");
      input.value = upto + input.value.slice(at);
      try { input.setSelectionRange(upto.length, upto.length); } catch (e) {}
      input.focus();
      grow(input);
      key = "";
    }
    if (input && key) {
      var label = nameOf(S.team.members, key);
      var pos = input.selectionStart || input.value.length;
      var before = input.value.slice(0, pos).replace(/@([^\s@]*)$/, "@" + label + " ");
      input.value = before + input.value.slice(pos);
      try { input.setSelectionRange(before.length, before.length); } catch (e) {}
      input.focus();
      grow(input);
      // Ghi đúng mã đã chọn kèm chữ của token: trùng tên vẫn gọi đúng người, sửa token thì bỏ gọi. Lựa chọn cũ mà token
      // không còn trong chữ thì bỏ luôn, kẻo nó giành chỗ của token mới.
      var low = (input.value.normalize ? input.value.normalize("NFC") : input.value).toLowerCase();
      S.picked = (S.picked || []).filter(function (p) {
        if (!p || typeof p !== "object") return true;
        var l = String(p.label || "");
        return low.indexOf("@" + (l.normalize ? l.normalize("NFC") : l).toLowerCase()) >= 0;
      }).concat([{ key: key, label: label }]);
    }
    S.pending = null;
    hideSug();
    drawHint();
  }

  function unMention(key) {
    var input = S.el.querySelector(".tm-input");
    if (!input || !S.team) return;
    if (key === "*all") {
      input.value = input.value.replace(new RegExp("(^|\\s)@" + ALL_TOKEN + "(?![\\p{L}\\p{M}\\p{N}_])\\s?", "giu"), "$1");
      S.pending = null; grow(input); input.focus(); drawHint();
      return;
    }
    var r = removeMention(input.value, S.team.members, S.picked, key);
    input.value = r.text;
    S.picked = r.picked;
    S.pending = null;
    grow(input);
    input.focus();
    drawHint();
  }

  function act(r, after) {
    if (r.code === 409 && r.j && r.j.queue) {
      S.queue = r.j.queue; learnTitles(S.queue); setNote(tw("teams.queue_changed")); drawJobs(); drawSide(); return;
    }
    if (r.code !== 200) return fail(r);
    if (r.j && r.j.team) S.team = r.j.team;
    if (r.j && r.j.queue) S.queue = r.j.queue;
    if (after) after();
    loadQueue(); loadTeam(); loadTeams(false);
  }

  function setLevel(n, input) {
    if (!S.team) return;
    var was = levelOf(S.team);
    if (n === 3 && typeof confirm === "function" && !confirm(tw("teams.level_3_confirm"))) {
      if (input) input.checked = false;
      drawSide();
      return;
    }
    var body = n === 1 ? { mode: "limited", reason: "owner_level_1" } : { mode: "full", grant: grantFor(n) };
    if (n === 1 && was === 1) return;
    call("POST", teamUrl("/authority"), body).then(function (r) {
      // Lỗi: vẽ lại để lựa chọn quay về mức đang áp thật.
      if (r.code !== 200) { fail(r); drawSide(true); return; }
      setNote(tw("teams.saved"));
      act(r, drawSide);
    });
  }

  // Menu Ghim / Bỏ ghim trên dòng nhóm (nhấn giữ hay chuột phải). Đóng bằng Escape (focus về dòng nhóm), bấm ra ngoài,
  // hay sau khi chọn.
  function openRowMenu(id) {
    S.rowMenu = id;
    S.tagMenu = null;
    S.focusRowMenu = true;
    drawList();
  }

  function closeRowMenu(focusRow) {
    var id = S.rowMenu;
    S.rowMenu = null;
    S.tagMenu = null;
    drawList();
    if (focusRow && id) {
      var row = S.el.querySelector('.tm-team[data-team="' + id + '"]');
      if (row) row.focus();
    }
  }

  // Ghim từ danh sách: cùng cách lưu với công tắc trong tab Nhóm (khoá nút trong lúc lưu, lỗi thì báo để thử lại).
  // Ghim một nhóm theo id, phụ thuộc truyền vào để test được: `post(on)` gửi, `notify(chữ, thửLại)` báo lỗi ở vùng thông
  // báo chung, `reload()` tải lại khi lưu được. Lỗi HTTP hay mất mạng: báo lỗi nhìn thấy kèm Thử lại chạy lại đúng thao tác.
  function pinTeamWith(id, on, btn, deps) {
    var box = { checked: on, disabled: false };
    if (btn) btn.disabled = true;
    var again = function () { return pinTeamWith(id, on, null, deps); };
    return savePin(box, function (want) { return deps.post(want); },
      function () { if (btn) btn.disabled = false; deps.reload(); },
      function (r) {
        if (btn) btn.disabled = false;
        deps.notify(r && r.network ? tw("teams.err_network") : tw("teams.err", { e: (r && r.j && r.j.error) || (r && r.code) || "?" }),
          again);
      });
  }

  function pinTeam(id, on, btn) {
    return pinTeamWith(id, on, btn, {
      post: function (want) { return call("POST", "/teams/" + q(id) + "/pin", { on: want }); },
      notify: setNote,
      reload: function () { loadTeams(false); if (id === S.activeId) loadTeam(); } });
  }

  // 0.197.0: turning a team's notifications off or on saves the same way as pinning it (button locked while saving, a
  // visible error with Retry).
  // 0.200.0: download the team file. Chat history, keys, model choices and Auto switches never go in.
  function shareTeam(id) {
    var a = document.createElement("a");
    a.href = "/teams/" + q(id) + "/export?brain=" + q(brain());
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setNote(tw("teams.share_note"));
  }

  // 0.200.0: add a team file. A preview first (who comes in, how many skills), then one confirm.
  function importTeam() {
    var inp = document.createElement("input");
    inp.type = "file";
    inp.accept = ".zip,application/zip";
    inp.onchange = function () {
      var f = inp.files && inp.files[0];
      if (!f) return;
      var send = function (preview) {
        var fd = new FormData();
        fd.append("file", f);
        fd.append("brain", brain());
        fd.append("preview", preview ? "1" : "0");
        return fetch("/teams/import", { method: "POST", credentials: "same-origin", body: fd })
          .then(function (r) { return r.json().catch(function () { return {}; }); });
      };
      send(true).then(function (pv) {
        if (!pv || !pv.ok) { setNote(pv && pv.error || tw("teams.import_bad")); return; }
        var ask = tw("teams.import_confirm", { name: pv.name, n: (pv.members || []).length, s: (pv.skills || []).length });
        if (typeof confirm === "function" && !confirm(ask)) return;
        send(false).then(function (r) {
          if (!r || !r.ok) { setNote(r && r.error || tw("teams.import_bad")); return; }
          setNote(tw("teams.imported", { name: r.team && r.team.name || pv.name, kept: (r.kept || []).length }));
          loadTeams(false);
        });
      });
    };
    inp.click();
  }

  function muteTeam(id, on, btn) {
    return pinTeamWith(id, on, btn, {
      post: function (want) { return call("POST", "/teams/" + q(id) + "/mute", { on: want }); },
      notify: setNote,
      reload: function () { loadTeams(false); } });
  }

  // ───────────── hộp chọn thành viên kiểu Zalo (0.142.0, team-picker.js) ─────────────

  function TP() { return (typeof window !== "undefined" && window.JavisTeamPicker) || null; }

  // Trợ lý của trang Cộng sự (tên, vai, tag, ảnh): cùng nguồn với cột trái trang Cộng sự để chip tag khớp.
  function loadRoster() {
    if (S.pickSt) S.pickSt.rosterState = "loading";
    return call("GET", "/agents?prompt=0").then(function (r) {
      if (r.code === 200) S.roster = r.j.agents || [];
      if (S.pickSt) S.pickSt.rosterState = r.code === 200 ? "ok" : "error";
    }, function () { if (S.pickSt) S.pickSt.rosterState = "error"; });
  }

  function openPicker(mode, opener) {
    if (!TP()) return;
    var exclude = mode === "add" && S.team ? (S.team.members || []).filter(function (m) { return !m.status || m.status === "active"; })
      .map(function (m) { return m.slug; }) : [];
    // `reqId`: một mã cho mỗi lần mở hộp Tạo nhóm. Bấm Tạo hai lần hay mạng chậm gửi lại thì server trả lại nhóm đã tạo.
    S.pickSt = { mode: mode, query: "", tag: "", selected: [], leader: "", leaderTouched: false, leaderDropped: false, name: "",
      desc: "", descOpen: false, exclude: exclude, saving: false, error: "", rosterState: (S.roster || []).length ? "ok" : "loading",
      reqId: newClientId() };
    S.pickOpener = opener || null;
    document.removeEventListener("keydown", pickEsc, true);
    document.addEventListener("keydown", pickEsc, true);
    drawPicker("all");
    loadRoster().then(function () { if (S.pickSt) drawPicker("all"); });
  }

  // Escape đóng hộp chọn cả khi focus đã rơi ra ngoài lớp phủ (review 0.142.0).
  function pickEsc(e) { if (e.key === "Escape" && S && S.pickSt) { e.preventDefault(); closePicker(); } }

  function closePicker() {
    document.removeEventListener("keydown", pickEsc, true);
    S.pickSt = null;
    if (S.pickHost) { S.pickHost.remove(); S.pickHost = null; }
    var back = S.pickOpener;
    S.pickOpener = null;
    if (back && back.isConnected) { try { back.focus(); } catch (e) {} }
  }

  // Vẽ lại đúng phần cần: gõ tìm hay đổi tag chỉ thay danh sách (giữ con trỏ trong ô tìm); chọn người thay chip, danh
  // sách, ô Điều phối và footer; "all" dựng lại cả hộp.
  function drawPicker(part) {
    var P = TP();
    var st = S.pickSt;
    if (!P || !st) return;
    // Lớp phủ gắn vào <body>, không vào trang: trang nằm trong .cview (một stacking context thấp hơn thanh trên của
    // app), nên trên điện thoại thanh đó đè lên đầu hộp và che nút đóng. Sự kiện gắn thẳng vào lớp phủ.
    var host = S.pickHost;
    if (!host || !host.isConnected) {
      host = document.createElement("div");
      host.className = "tmp-host";
      document.body.appendChild(host);
      host.addEventListener("click", onClick);
      host.addEventListener("change", onChange);
      host.addEventListener("input", onInput);
      host.addEventListener("keydown", onKey);
      S.pickHost = host;
    }
    var roster = S.roster || [];
    if (part === "all" || !host.firstChild) {
      host.innerHTML = P.html(st, roster);
      var first = host.querySelector(st.mode === "create" ? ".tmp-name-input" : ".tmp-search-input");
      if (first && !(typeof matchMedia === "function" && matchMedia("(pointer: coarse)").matches)) first.focus();
      return;
    }
    var put = function (sel, h) { var box = host.querySelector(sel); if (box) box.innerHTML = h; };
    put(".tmp-tags-box", P.tagsHtml(roster, st));
    put(".tmp-list", P.listHtml(roster, st));
    if (part === "filter") return;
    put(".tmp-selected-box", P.selectedHtml(roster, st));
    put(".tmp-preview-box", P.previewHtml(roster, st));
    put(".tmp-foot-box", P.footerHtml(st));
    var err = host.querySelector(".tmp-error");
    if (err && !st.error) err.remove();
  }

  function pickToggle(slug) {
    var was = document.activeElement;
    var fromChip = was && was.classList && was.classList.contains("tmp-sel-x");
    S.pickSt = TP().toggle(S.pickSt, slug);
    S.pickSt.error = "";
    drawPicker("pick");
    // Vẽ lại thay node đang có focus: đặt focus lại đúng ô vừa bấm (hay ô tìm khi bấm x trên chip), để bàn phím đi tiếp
    // và Escape vẫn đóng được hộp (review 0.142.0).
    var host = S.pickHost;
    var back = host && (fromChip ? host.querySelector(".tmp-search-input")
      : host.querySelector('.tmp-check[data-pick-slug="' + (window.CSS && CSS.escape ? CSS.escape(slug) : slug) + '"]'));
    // preventScroll: dòng vừa bấm đang nằm trong tầm nhìn, đừng để focus kéo cuộn hộp chọn.
    if (back) { try { back.focus({ preventScroll: true }); } catch (e) {} }
  }

  function pickFail(msg) {
    if (!S.pickSt) return;
    S.pickSt.saving = false;
    S.pickSt.error = msg;
    drawPicker("all");
  }

  function submitPicker() {
    var P = TP(), st = S.pickSt;
    if (!P || !st || !P.canSubmit(st)) return;
    st.saving = true; st.error = "";
    drawPicker("pick");
    if (st.mode === "create") {
      var name = String(st.name || "").trim() || P.autoName(st, S.roster || []);
      call("POST", "/teams", { name: name, description: st.desc || "", members: st.selected.slice(), leader_slug: st.leader || "",
        client_req_id: st.reqId })
        .then(function (r) {
          if (r.code !== 200) return pickFail((r.j && r.j.error) || tw("teams.err", { e: r.code }));
          // Tạo xong: vào thẳng khung chat của nhóm mới, con trỏ đặt sẵn ở khung soạn.
          closePicker();
          S.focusComposer = true;
          loadTeams(false).then(function () { openTeam(r.j.team.team_id); });
        }, function () { pickFail(tw("teams.pick.err_network")); });
      return;
    }
    // Thêm nhiều người: lần lượt từng người; ai lỗi thì GIỮ trong lựa chọn để bấm lại, ai xong thì khỏi danh sách.
    var forTeam = S.activeId, done = [], failed = [], lastErr = "";
    var nameOfSlug = function (slug) {
      var a = (S.roster || []).filter(function (x) { return x.slug === slug; })[0];
      return a ? (a.name || a.slug) : slug;
    };
    st.selected.slice().reduce(function (p, slug) {
      return p.then(function () {
        return call("POST", "/teams/" + q(forTeam) + "/members", { slug: slug }).then(function (r) {
          if (r.code === 200) done.push(slug); else { failed.push(slug); lastErr = (r.j && r.j.error) || ""; }
        }, function () { failed.push(slug); lastErr = tw("teams.err_network"); });
      });
    }, Promise.resolve()).then(function () {
      if (S.activeId === forTeam) { loadTeam(); }
      if (!failed.length) { closePicker(); return; }
      S.pickSt = Object.assign({}, st, { selected: failed, exclude: (st.exclude || []).concat(done) });
      pickFail(tw("teams.pick.add_partial", { done: done.map(nameOfSlug).join(", ") || "0",
        failed: failed.map(nameOfSlug).join(", ") }) + (lastErr ? " (" + lastErr + ")" : ""));
    });
  }

  function onClick(e) {
    var t = e.target.closest ? e.target.closest("button, [data-team], summary, .tm-scrim, .tmp-scrim") : null;
    // Bấm ở bất cứ đâu ngoài menu ghim thì đóng menu.
    if (S.rowMenu && !(e.target.closest && e.target.closest(".tm-row-menu")) && !(t && t.dataset && t.dataset.pinTeam)) {
      if (!(t && t.dataset && t.dataset.team && S.swallowClick)) closeRowMenu();
    }
    // A press anywhere outside the "+" menu closes it; outside the long-press sheet closes the sheet.
    var inside = function (sel) { return !!(e.target.closest && e.target.closest(sel)); };
    if (S.plusOpen && !inside(".tm-plus-menu") && !inside(".tm-plus")) setPlus(false);
    if (S.picker !== null && !inside(".tm-sheet") && Date.now() - (S.sheetAt || 0) > 600) {
      S.picker = null;
      drawMsgs(false);
    }
    if (!t || !(S.el.contains(t) || (S.pickHost && S.pickHost.contains(t)))) return;
    // A JAVIS_CARD button carries data-reply too (its words, not a message id): chat-card.js sends it (sendCardReply).
    if (t.classList && t.classList.contains("jv-card-btn")) return;
    // "Show more" on a long owner message: chat-acts.js toggles it (document listener, after this one). Remember the
    // state so a redraw of the list keeps the message open.
    if (t.classList && t.classList.contains("clamp-more")) {
      var cm = t.closest(".tm-msg");
      var cu = cm && cm.querySelector(".utext");
      if (cm && cu) S.unclamped[cm.getAttribute("data-mid")] = cu.classList.contains("clamped");
      return;
    }
    var d = t.dataset || {};
    if (d.rowMenu) {
      if (S.rowMenu === d.rowMenu) return closeRowMenu(true);
      return openRowMenu(d.rowMenu);
    }
    if (d.renameTeam) { S.rowMenu = null; S.renaming = d.renameTeam; drawList(); return; }
    if (d.tagTeam) { S.tagMenu = d.tagTeam; S.tagFocus = null; drawList(); return; }
    if (t.classList && t.classList.contains("cs-proj-cur") && t.closest(".tm-tagbar")) {
      var cs = typeof window !== "undefined" && window.JavisChatSide;
      if (cs && cs.menu) cs.menu(t, tagMenuRows(S.teams, S.tagFilter, function (k) { setTagFilter(k); drawList(); }));
      return;
    }
    if (t.classList && t.classList.contains("cs-proj-x") && t.closest(".tm-tagbar")) { setTagFilter(""); drawList(); return; }
    if (d.deleteTeam) { if (S.rowMenu) closeRowMenu(); return deleteTeam(d.deleteTeam); }
    if (d.renameHead) { S.renamingHead = true; drawHead(); return; }
    if (d.finOpen) { S.openFin = S.openFin === d.finOpen ? null : d.finOpen; drawSide(); return; }
    if (t.classList.contains("tm-arch-toggle")) { S.archOpen = !S.archOpen; drawSide(); return; }
    if (d.jobArchive) return markJobs([d.jobArchive], "archived");
    if (d.jobUnarchive) return markJobs([d.jobUnarchive], "");
    if (d.jobDelete) return markJobs([d.jobDelete], "deleted");
    if (d.jobDeleteAll) {
      var all = ((S.queue || {}).archived || []).map(function (j) { return j.id; });
      if (!all.length || !window.confirm(tw("teams.archive_clear_confirm", { n: all.length }))) return;
      return markJobs(all, "deleted");
    }
    if (d.agentEdit) return openAgentSettings(d.agentEdit);
    // 0.193.0: message a member privately, straight from the team (the Partners page chat with that assistant).
    if (d.agentChat) { if (window.JavisWorkspace && window.JavisWorkspace.openCommand) window.JavisWorkspace.openCommand("agent", d.agentChat); return; }
    if (d.rxToggle) {
      var rm = msgById(Number(d.rxToggle));
      return sendReaction(Number(d.rxToggle), JR.cornerToggle(rm && rm.reaction));
    }
    if (d.react && d.mid) {
      var cur = msgById(Number(d.mid));
      return sendReaction(Number(d.mid), nextReaction(cur && cur.reaction && cur.reaction.value, d.react));
    }
    if (d.reply) return startReply(d.reply);
    if (d.copy) return copyMsg(d.copy);
    if (d.replyCancel) {
      S.replyTo = null; S.pending = null; drawComposer();
      var ri = S.el.querySelector(".tm-input");
      if (ri) ri.focus();
      return;
    }
    if (t.classList.contains("tm-plus")) return setPlus(!S.plusOpen);
    if (d.teamInfo) return S.side && S.tab === "info" ? closeSide() : openSide("info", t);
    if (d.plusAttach) { setPlus(false); return pickFiles(attachFiles); }
    if (d.plusFolder || d.folderOpen) { setPlus(false); return openFolderPanel(); }
    if (d.folderUnpin) return pinTeamFolder("");
    if (d.attX !== undefined) { forgetAtts(S.atts.splice(+d.attX, 1)); drawComposer(); return; }
    if (d.outRetry) {
      var oe = S.outbox.filter(function (p) { return p.cid === d.outRetry; })[0];
      if (oe && oe.state === "failed") { postEntry(oe); drawMsgs(false); }
      return;
    }
    if (d.outDrop) {
      // Remove a message that could not be sent: its words go back into an empty composer, so nothing typed is lost.
      var od = S.outbox.filter(function (p) { return p.cid === d.outDrop; })[0];
      if (!od) return;
      dropEntry(od, false);
      var oi = S.el.querySelector(".tm-input");
      if (oi && !oi.value.trim() && !S.atts.length && !S.replyTo) {
        oi.value = od.typed; S.atts = od.atts; S.replyTo = od.replyTo; S.asJob = od.asJob; S.picked = od.picked;
        drawComposer();
      } else forgetAtts(od.atts);
      drawMsgs(false);
      return;
    }
    if (d.attRetry !== undefined) {
      var ra = S.atts[+d.attRetry];
      if (ra && ra.file && !ra.busy) { startUpload(ra); drawComposer(); }
      return;
    }
    if (d.infoAddFile) return pickFiles(addTeamFiles);
    if (d.infoDelFile) return assetPost("/files/" + q(d.infoDelFile) + "/delete");
    if (d.infoDelLink) return assetPost("/links/" + q(d.infoDelLink) + "/delete");
    if (d.infoAddLink) return addTeamLink();
    if (t.classList.contains("tm-mic")) return toggleMic();
    if (d.insertAt) {
      setPlus(false);
      var ai = S.el.querySelector(".tm-input");
      if (ai) {
        var pos = ai.selectionStart != null ? ai.selectionStart : ai.value.length;
        var pre = ai.value.slice(0, pos);
        var add = (pre && !/\s$/.test(pre) ? " " : "") + "@";
        ai.value = pre + add + ai.value.slice(pos);
        ai.focus();
        try { ai.setSelectionRange(pos + add.length, pos + add.length); } catch (x) {}
        grow(ai); suggest(); drawHint();
      }
      return;
    }
    if (d.plusSearch) {
      setPlus(false);
      S.searchOpen = true;
      drawHead();
      var ps = S.el.querySelector(".tm-search-input");
      if (ps) ps.focus();
      return;
    }
    // Nhấn giữ vừa mở menu ghim: cú bấm sinh ra lúc nhấc tay không được mở nhóm.
    if (d.team && S.swallowClick) { S.swallowClick = false; return; }
    if (d.pinTeam) {
      if (S.rowMenu) closeRowMenu();
      return pinTeam(d.pinTeam, d.on === "1", S.el.contains(t) ? t : null);
    }
    if (d.muteTeam) {
      if (S.rowMenu) closeRowMenu();
      return muteTeam(d.muteTeam, d.on === "1", null);
    }
    if (d.shareTeam) {
      if (S.rowMenu) closeRowMenu();
      return shareTeam(d.shareTeam);
    }
    if (d.team) return openTeam(d.team);
    if (t.classList.contains("tm-scrim")) return closeSide();
    if (t.classList.contains("tm-note-close")) { setNote(""); return; }
    if (t.classList.contains("tm-note-retry")) {
      var run = S.noteRetry;
      setNote("");
      if (run) run();
      return;
    }
    if (t.classList.contains("tm-adv-sum")) {
      // Nhớ Nâng cao đang mở để lần vẽ lại sau (có tin mới, đổi thành viên) không đóng nó; mở thì tải sổ lượt.
      var det = t.parentNode;
      S.advOpen = !(det && det.open);
      if (S.advOpen) loadTurns();
      return;
    }
    if (t.classList.contains("tm-new")) return openPicker("create", t);
    if (t.classList.contains("tm-import")) return importTeam();
    if (t.classList.contains("tm-add-open")) return openPicker("add", t);
    if (d.pickTag !== undefined) { S.pickSt.tag = d.pickTag; drawPicker("filter"); return; }
    if (d.pickToggle) { pickToggle(d.pickToggle); return; }
    if (d.pickLeader) { S.pickSt = TP().setLeader(S.pickSt, d.pickLeader); drawPicker("pick"); return; }
    if (t.classList.contains("tmp-reload")) { loadRoster().then(function () { if (S.pickSt) drawPicker("all"); }); drawPicker("filter"); return; }
    if (t.classList.contains("tmp-desc-sum")) { var dd = t.parentNode; if (S.pickSt) S.pickSt.descOpen = !(dd && dd.open); return; }
    if (t.classList.contains("tmp-cancel")) return closePicker();
    if (t.classList.contains("tmp-submit")) return submitPicker();
    if (t.classList.contains("tm-more-teams")) return loadTeams(true);
    if (t.classList.contains("tm-back")) {
      S.view = "list"; S.side = false;
      if (!S.team) S.activeId = "";
      drawAll(false);
      return;
    }
    if (t.classList.contains("tm-gear")) {
      if (S.side && S.tab === "team") return closeSide();
      return openSide("team", t);
    }
    if (d.openJobs) {
      if (S.side && S.tab === "jobs") return closeSide();
      return openSide("jobs", t);
    }
    if (d.openTeam) return openSide("team", t);
    if (t.classList.contains("tm-close")) return closeSide();
    if (d.tab) {
      S.tab = d.tab; drawSide(true); drawHead();
      if (d.tab === "team") loadAgents().then(function () { if (S.side && S.tab === "team") drawSide(); });
      return;
    }
    if (d.expand) { S.openMember = S.openMember === d.expand ? null : d.expand; drawSide(true); return; }
    if (d.judgeHint) { S.openMember = d.judgeHint; return openSide("team", t); }
    if (t.classList.contains("tm-asjob")) {
      S.asJob = !S.asJob;
      // Đổi loại tin là một tin KHÁC: mã client cũ thuộc tin trước, gửi lại bằng nó sẽ được trả tin cũ khác loại.
      S.pending = null;
      S.plusOpen = false;
      drawComposer();
      var inp = S.el.querySelector(".tm-input");
      if (inp) inp.focus();
      return;
    }
    if (t.classList.contains("tm-send")) return send();
    if (t.classList.contains("tm-older")) return loadMsgs(true);
    if (d.mention) return pickMention(d.mention);
    if (d.unmention) return unMention(d.unmention);
    if (t.classList.contains("tm-search-btn")) {
      S.searchOpen = !S.searchOpen;
      if (!S.searchOpen) { S.searchResults = null; S.searchQuery = ""; }
      drawHead();
      var si = S.el.querySelector(".tm-search-input");
      if (si && S.searchOpen) si.focus();
      return;
    }
    if (t.classList.contains("tm-search-go")) return runSearch();
    if (d.jump) {
      var here = S.el.querySelector('.tm-msgs [data-mid="' + Number(d.jump) + '"]');
      if (here && here.scrollIntoView) {
        here.scrollIntoView({ block: "center", behavior: "smooth" });
        here.classList.add("tm-msg-flash");
        setTimeout(function () { here.classList.remove("tm-msg-flash"); }, 1600);
        return;
      }
      return jumpTo(d.jump, d.ts);
    }
    if (t.classList.contains("tm-jump-back")) { S.jumped = null; loadMsgs(false); return; }
    if (t.classList.contains("tm-filter-clear")) { S.filterTask = ""; drawFilterbar(); loadMsgs(false); return; }
    if (d.reactClose) { S.focusBack = S.picker; S.picker = null; drawMsgs(false); return; }
    if ((d.task && t.classList.contains("tm-tag")) || d.viewTask) {
      S.filterTask = d.task || d.viewTask;
      if (d.viewTask && window.matchMedia && window.matchMedia("(max-width: 1060px)").matches) S.side = false;
      drawSide(); drawFilterbar(); loadMsgs(false);
      return;
    }
    if (d.replyAct) return replyAct(d.replyAct, d.slug || "", t);
    if (d.retry && d.retryKey) {
      var rk = d.retry + "|" + d.retryKey;
      if (S.retrying[rk]) return;
      S.retrying[rk] = true;
      drawMsgs(false);
      return call("POST", teamUrl("/messages/" + q(d.retry) + "/replies/" + q(d.retryKey) + "/retry")).then(function (r) {
        if (r.code !== 200) { delete S.retrying[rk]; fail(r); drawMsgs(false); return; }
        if (!r.j.retried) { delete S.retrying[rk]; setNote(tw("teams.reply.retry_none")); }
        // Server đã nhận Thử lại: trạng thái mới của đúng người này (chờ, đang trả lời, xong) mở khoá nút, không chỉ trông
        // vào gói WS (lỡ gói đó thì nút kẹt "Đang thử lại").
        (r.j.replies || []).forEach(function (x) { if (x.agent_key === d.retryKey && x.status !== "error") delete S.retrying[rk]; });
        var k = S.msgs.findIndex(function (m) { return Number(m.id) === Number(d.retry); });
        if (k >= 0) S.msgs[k] = Object.assign({}, S.msgs[k], { replies: r.j.replies || [] });
        drawMsgs(false);
      }).catch(function () { delete S.retrying[rk]; setNote(tw("teams.err_network")); drawMsgs(false); });
    }
    if (d.accept) return call("POST", teamUrl("/messages/" + q(d.accept) + "/accept")).then(function (r) { act(r); });
    if (d.skip) {
      return call("POST", teamUrl("/messages/" + q(d.skip) + "/reject")).then(function (r) {
        if (r.code !== 200) return fail(r);
        loadMsgs(false);
      });
    }
    if (d.decision) {
      return call("POST", teamUrl("/messages/" + q(d.decision) + "/decision"), { on: d.on === "1" }).then(function (r) {
        if (r.code !== 200) return fail(r);
        S.picker = null; S.draft = null;
        loadMsgs(false); loadTeam();
      });
    }
    if (t.classList.contains("tm-pin-toggle")) { S.pinsOpen = !S.pinsOpen; drawPins(); return; }
    if (d.prio) {
      return call("POST", teamUrl("/queue/" + q(d.prio) + "/priority"),
        { on: d.on === "1", expected_queue_version: (S.queue && S.queue.version) || 0 }).then(function (r) { act(r); });
    }
    if (d.cancel) {
      var ct = S.taskTitles[d.cancel] || d.cancel;
      if (typeof confirm === "function" && !confirm(tw("teams.cancel_confirm", { title: ct }))) return;
      return call("POST", teamUrl("/tasks/" + q(d.cancel) + "/cancel")).then(function (r) { act(r); });
    }
    if (d.apDecide) {
      var dec = d.apDecide, note = "";
      if (dec === "reject" || dec === "changes") {
        note = typeof prompt === "function" ? prompt(tw(dec === "reject" ? "teams.ap.reject_prompt" : "teams.ap.changes_prompt")) : "";
        if (!note || !note.trim()) return;
      } else if (dec === "revoke" && typeof confirm === "function" && !confirm(tw("teams.ap.revoke_confirm"))) {
        return;
      }
      // One key per decision of this card in this tab: pressing again after a lost connection replays the same answer
      // (no second action, no error), another tab has its own key and is told the request is already decided.
      S.apKeys = S.apKeys || {};
      var kk = d.ap + "|" + dec;
      var dkey = S.apKeys[kk] || (S.apKeys[kk] = "ap-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10));
      t.disabled = true;
      return call("POST", teamUrl("/approvals/" + q(d.ap) + "/decide"), { decision: dec, note: (note || "").trim(),
        decision_key: dkey, expected_rev: d.apRev ? Number(d.apRev) : null }).then(function (r) {
        if (r.code !== 200) { t.disabled = false; fail(r); }
        loadMsgs(false); loadQueue();
      }).catch(function () { t.disabled = false; setNote(tw("teams.err_network")); });
    }
    if (d.mandateEdit !== undefined) { S.mandateEdit = d.mandateEdit === "1"; drawSide(); return; }
    if (d.accEdit !== undefined) { S.accEdit = d.accEdit || null; drawSide(); return; }
    if (t.classList.contains("tm-acc-save")) {
      var af = t.closest(".tm-acc-form");
      var parsed = parseCriteria((af.querySelector('[name="tm-acc-text"]') || {}).value);
      if (parsed.bad.length || !parsed.criteria.length) { setNote(tw("teams.acc.bad", { line: parsed.bad[0] || "" })); return; }
      return call("PUT", teamUrl("/tasks/" + q(af.getAttribute("data-acc-task")) + "/acceptance"),
        { criteria: parsed.criteria, fix_rounds: Number((af.querySelector('[name="tm-acc-rounds"]') || {}).value || 2) }).then(function (r) {
        if (r.code !== 200) return fail(r);
        S.accEdit = null;
        setNote(tw("teams.saved"));
        act(r, drawSide);
      });
    }
    if (d.accDecide) {
      var anote = "";
      if (d.accDecide === "reject") {
        anote = typeof prompt === "function" ? prompt(tw("teams.acc.reject_prompt")) : "";
        if (!anote || !anote.trim()) return;
      }
      t.disabled = true;
      // The card's own revision and round: a click on an older card is refused by the server (never accepts a newer
      // product the owner did not see).
      return call("POST", teamUrl("/tasks/" + q(d.acc) + "/acceptance/decide"),
        acceptanceDecisionPayload(d, d.accDecide, anote)).then(function (r) {
        if (r.code !== 200) { t.disabled = false; fail(r); }
        loadMsgs(false); loadQueue();
      }).catch(function () { t.disabled = false; setNote(tw("teams.err_network")); });
    }
    if (t.classList.contains("tm-quality-save")) {
      var qform = t.closest(".tm-quality-form");
      var qp = qualityPolicyPayload({ enabled: qform.querySelector(".tm-quality-enabled").checked,
        limit_migration: qform.querySelector(".tm-quality-migration").value,
        reference_usd: qform.querySelector(".tm-quality-reference").value });
      if (!qp.ok) return setNote(tw("teams.quality.invalid"));
      t.disabled = true;
      return call("PUT", teamUrl("/quality-policy"), qp.body).then(function (r) {
        if (r.code !== 200) { t.disabled = false; return fail(r); }
        setNote(tw("teams.saved"));
        loadTeam();
      }).catch(function () { t.disabled = false; setNote(tw("teams.err_network")); });
    }
    if (t.classList.contains("tm-template-save")) {
      var tform = t.closest(".tm-template-form");
      var parsed = parseCriteria(tform.querySelector(".tm-template-criteria").value);
      if (parsed.bad.length || !parsed.criteria.length) return setNote(tw("teams.acc.bad"));
      t.disabled = true;
      return call("PUT", teamUrl("/acceptance-template"), qualityTemplatePayload(S.team.acceptance_template,
        tform.dataset.templateVersion, parsed.criteria)).then(function (r) {
        if (r.code !== 200) { t.disabled = false; return fail(r); }
        setNote(tw("teams.saved"));
        loadTeam();
      }).catch(function () { t.disabled = false; setNote(tw("teams.err_network")); });
    }
    if (t.classList.contains("tm-md-save")) {
      var mform = S.el.querySelector(".tm-md-form");
      if (!mform) return;
      return call("PUT", teamUrl("/mandate"), readMandateForm(mform)).then(function (r) {
        if (r.code !== 200) return fail(r);
        S.mandateEdit = false;
        setNote(tw("teams.saved"));
        act(r, drawSide);
      });
    }
    if (d.mandateStatus) {
      if (d.mandateStatus === "revoked" && typeof confirm === "function" && !confirm(tw("teams.md.revoke_confirm"))) return;
      return call("POST", teamUrl("/mandate/status"), { status: d.mandateStatus }).then(function (r) { act(r, drawSide); });
    }
    if (d.oppDecide) {
      t.disabled = true;
      return call("POST", teamUrl("/mandate/opportunities/" + q(d.opp) + "/decide"), { decision: d.oppDecide }).then(function (r) {
        if (r.code !== 200) { t.disabled = false; fail(r); }
        loadMsgs(false); loadQueue();
      }).catch(function () { t.disabled = false; setNote(tw("teams.err_network")); });
    }
    if (d.amend) {
      var at = S.taskTitles[d.amend] || d.amend;
      var text = typeof prompt === "function" ? prompt(tw("teams.amend_prompt", { title: at })) : "";
      if (!text || !text.trim()) return;
      return call("POST", teamUrl("/tasks/" + q(d.amend) + "/amend"), { text: text.trim() }).then(function (r) { act(r); });
    }
    if (d.extend) {
      t.disabled = true;
      return call("POST", teamUrl("/tasks/" + q(d.extend) + "/extend")).then(function (r) {
        if (r.code !== 200) { fail(r); drawJobs(); loadQueue(); return; }
        // Nhóm đang tạm dừng thì việc chỉ về hàng chờ: nói rõ phải bật lại nhóm, đừng hứa "chạy tiếp".
        setNote(tw(S.team && S.team.status === "paused" ? "teams.extended_paused" : "teams.extended"));
        act(r);
      });
    }
    if (d.unblock) {
      return call("POST", teamUrl("/tasks/" + q(d.unblock) + "/unblock"), { action: d.action }).then(function (r) { act(r); });
    }
    if (d.teamResume) return call("PATCH", teamUrl(), { status: "active" }).then(function (r) { act(r, drawAll); });
    if (d.leader !== undefined && t.hasAttribute("data-leader")) {
      return call("POST", teamUrl("/leader"), { agent_key: d.leader || null }).then(function (r) { act(r, drawAll); });
    }
    if (d.remove) {
      var nm = nameOf(S.team && S.team.members, d.remove);
      if (typeof confirm === "function" && !confirm(tw("teams.remove_confirm", { name: nm }))) return;
      return call("DELETE", teamUrl("/members/" + q(d.remove))).then(function (r) { S.openMember = null; act(r, drawAll); });
    }
    if (t.closest && t.closest(".tm-ava-set")) {
      var avaSet = t.closest(".tm-ava-set");
      if (t.hasAttribute("data-aa-upload")) { var inp = avaSet.querySelector("[data-aa-file]"); if (inp) inp.click(); return; }
      if (t.hasAttribute("data-aa-unimg")) {
        return call("PATCH", teamUrl(), { avatar_image: "" }).then(function (r) { act(r, drawAll); });
      }
    }
    if (t.classList.contains("tm-save")) return saveSettings();
    if (t.classList.contains("tm-caps-save")) return saveCaps();
    if (t.classList.contains("tm-auth-save")) {
      var sec = S.el.querySelector(".tm-auth");
      return call("POST", teamUrl("/authority"), { mode: "full", grant: readGrant(sec) }).then(function (r) {
        if (r.code === 200) setNote(tw("teams.saved"));
        act(r, drawSide);
      });
    }
    if (t.classList.contains("tm-auth-revoke")) {
      if (typeof confirm === "function" && !confirm(tw("teams.auth.revoke_confirm"))) return;
      return call("POST", teamUrl("/authority"), { mode: "limited" }).then(function (r) { act(r, drawSide); });
    }
  }

  function msgById(id) {
    for (var i = 0; i < S.msgs.length; i++) if (Number(S.msgs[i].id) === id) return S.msgs[i];
    return null;
  }

  // Thả cảm xúc: chỉ ghi phản hồi (không mở lượt, không gọi model). `seen_sha` là nội dung tin giao diện đang thấy. Nonce
  // giữ theo thao tác (reactNonces): rớt mạng thì Thử lại gửi đúng nonce cũ, server trả trạng thái hiện tại, không ghi trùng.
  function sendReaction(mid, value, reasons, axis, comment) {
    var m0 = msgById(mid);
    var body = JR.payload(value, reasons, axis, comment, m0 && m0.content_sha);
    var key = String(mid);
    body.nonce = reactNonces.take(key, body);
    var retry = function () { return sendReaction(mid, value, reasons, axis, comment); };
    return call("POST", teamUrl("/messages/" + q(mid) + "/reaction"), body).then(function (r) {
      reactNonces.settle(key, r.code);
      if (r.code >= 500) return setNote(tw("teams.err", { e: (r.j && r.j.error) || r.code }), retry);
      if (r.code !== 200) return fail(r);
      var m = msgById(mid);
      if (m) m.reaction = r.j.reaction || null;
      S.focusBack = S.picker;
      S.picker = null;
      drawMsgs(false);
    }, function () {
      reactNonces.settle(key, 0);
      setNote(tw("teams.err_network"), retry);
    });
  }

  function val(name) {
    var x = S.el.querySelector('[name="' + name + '"]');
    return x ? x.value : "";
  }

  function saveSettings() {
    var status = (S.el.querySelector('input[name="tm-status"]:checked') || {}).value || S.team.status;
    if (status === "archived" && S.team.status !== "archived" && typeof confirm === "function" &&
        !confirm(tw("teams.archive_confirm"))) return;
    call("PATCH", teamUrl(), { name: val("tm-set-name"), description: val("tm-set-desc"), status: status }).then(function (r) {
      if (r.code === 200) setNote(tw("teams.saved"));
      act(r, drawAll);
    });
  }

  // Dựng thân POST /caps từ form (hàm thuần, test được dưới node). `read(k)` trả {checked: bool|null, value: chuỗi};
  // checked null là trần không có ô Không giới hạn. Trả {caps, missing}: `missing` là trần vừa bỏ tích Không giới hạn mà
  // chưa nhập số, khi đó KHÔNG gửi gì (review T1 #1: không báo "Đã lưu" khi không đổi gì).
  function capsPayload(current, read) {
    var caps = {};
    var missing = null;
    CAP_FIELDS.forEach(function (k) {
      var cur = (current || {})[k];
      var f = read(k) || {};
      if (f.checked === true) {
        if (cur !== null) caps[k] = { unlimited: true };
        return;
      }
      var v = f.value == null ? "" : String(f.value);
      if (v === "" && cur === null && f.checked === false && !missing) missing = k;
      if (v !== "" && (cur === null || Number(v) !== Number(cur))) caps[k] = Number(v);
    });
    CAP_MODES.forEach(function (k) {
      var f = read(k) || {};
      var v = f.value == null ? "" : String(f.value);
      var cur = (current || {})[k];
      if (v !== "" && Number(v) !== Number(cur === undefined ? 1 : cur)) caps[k] = Number(v);
    });
    return missing ? { caps: {}, missing: missing } : { caps: caps, missing: null };
  }

  // Luồng nút Lưu giới hạn, tách khỏi DOM để test được hành vi dưới node: `form.read(k)` đọc ô, `ui.note(text)`,
  // `ui.focus(k)`, `ui.post(caps)` trả Promise. Thiếu số thì nhắc, đưa con trỏ vào ô đó và KHÔNG gửi (review T1 #1).
  function saveCapsFlow(current, read, ui) {
    var built = capsPayload(current, read);
    if (built.missing) {
      ui.note(tw("teams.cap_need_number", { name: tw(CAP_KEY[built.missing]) }));
      ui.focus(built.missing);
      return null;
    }
    if (!Object.keys(built.caps).length) { ui.note(tw("teams.saved")); return null; }
    return ui.post(built.caps);
  }

  function saveCaps() {
    saveCapsFlow(S.team.caps, function (k) {
      var box = S.el.querySelector('[name="tm-cap-' + k + '-unl"]');
      return { checked: box ? !!box.checked : null, value: val("tm-cap-" + k) };
    }, {
      note: setNote,
      focus: function (k) {
        var miss = S.el.querySelector('[name="tm-cap-' + k + '"]');
        if (miss && miss.focus) miss.focus();
      },
      post: function (caps) {
        return call("POST", teamUrl("/caps"), { caps: caps }).then(function (r) {
          if (r.code === 200) setNote(tw("teams.saved"));
          act(r, drawSide);
        });
      },
    });
  }

  // Chọn ảnh nhóm xong: thu nhỏ, tải lên (agent-avatar.js) rồi gắn vào nhóm. Lỗi báo ngay dưới nút.
  function uploadTeamAvatar(inp) {
    var f = inp.files && inp.files[0];
    var box = inp.closest(".tm-ava-set");
    var msg = box && box.querySelector(".aa-upload-msg");
    var btn = box && box.querySelector("[data-aa-upload]");
    inp.value = "";
    if (!f || !window.JavisAvatar) return;
    if (btn) btn.disabled = true;
    if (msg) { msg.textContent = tw("ws.avatar_uploading"); msg.classList.remove("loi"); }
    window.JavisAvatar.uploadImage(f).then(function (name) {
      return call("PATCH", teamUrl(), { avatar_image: name }).then(function (r) { act(r, drawAll); });
    }).catch(function (err) {
      if (btn) btn.disabled = false;
      if (msg) { msg.textContent = (err && err.message && err.message !== "decode" && err.message !== "encode") ? err.message
        : tw("ws.avatar_upload_fail"); msg.classList.add("loi"); }
    });
  }

  function onChange(e) {
    if (e.target.hasAttribute && e.target.hasAttribute("data-work-mode") && S && S.activeId) {
      // 0.207.0: the team's outside-action switch; the server logs it and posts a line in the chat.
      return call("POST", teamUrl("/work_mode"), { mode: e.target.getAttribute("data-work-mode") }).then(function (r) {
        if (r.code === 200) setNote(tw("teams.saved"));
        act(r, drawSide);
      });
    }
    if (e.target.hasAttribute && e.target.hasAttribute("data-aa-file") && e.target.closest && e.target.closest(".tm-ava-set")) {
      uploadTeamAvatar(e.target);
      return;
    }
    if (S.pickSt && e.target.classList && e.target.classList.contains("tmp-check")) {
      pickToggle(e.target.getAttribute("data-pick-slug"));
      return;
    }
    if (S.pickSt && e.target.classList && e.target.classList.contains("tmp-leader-pick")) {
      S.pickSt = Object.assign({}, S.pickSt, { leader: e.target.value, leaderTouched: true });
      return;
    }
    if (e.target.name === "tm-level") { setLevel(Number(e.target.value), e.target); return; }
    if (e.target.classList.contains("tm-pin-toggle")) {
      // Ghim nhóm lên đầu danh sách: lưu được thì act() tải lại nhóm và danh sách; lỗi thì công tắc về trạng thái đã lưu,
      // bật lại để thử lại, và báo lỗi (review b93c46bd #1).
      savePin(e.target, function (on) { return call("POST", teamUrl("/pin"), { on: on }); },
        function (r) { act(r, drawSide); },
        function (r) { if (r && r.network) setNote(tw("teams.err_network")); else fail(r); });
      return;
    }
    if (e.target.name && /^tm-(auth-(cap|ceil)|cap)-[a-z_]+-unl$/.test(e.target.name)) {
      // Tích Không giới hạn thì ô số tắt (giá trị là null + cờ, không phải một số lớn).
      var num = S.el.querySelector('[name="' + e.target.name.slice(0, -4) + '"]');
      if (num) num.disabled = e.target.checked;
      return;
    }
    if (e.target.classList.contains("tm-managed-toggle")) {
      var mb = e.target;
      var want = mb.checked;
      mb.checked = !want;
      mb.disabled = true;
      call("POST", teamUrl("/members/" + q(mb.getAttribute("data-key")) + "/managed"), { on: want }).then(function (r) {
        act(r, drawSide);
      });
      return;
    }
    if (e.target.classList.contains("tm-rs-toggle")) {
      var box = e.target;
      var on = box.checked;
      box.checked = !on;
      box.disabled = true;
      var RA = window.JavisResonanceAgent;
      var p = RA && RA.toggleAgent ? RA.toggleAgent(box.getAttribute("data-slug"), on)
        : call("POST", "/resonance/agents/toggle", { slug: box.getAttribute("data-slug"), enabled: on }).then(function (r) {
          return { ok: r.code === 200, error: r.j && r.j.error };
        });
      p.then(function (res) {
        if (!res || !res.ok) setNote(tw("teams.err", { e: (res && res.error) || "?" }));
        loadTeam();
      });
    }
  }

  function onKey(e) {
    if (e.target.classList && e.target.classList.contains("tm-search-input") && e.key === "Enter") {
      e.preventDefault();
      runSearch();
      return;
    }
    if (e.key === "Escape" && S.pickSt) { closePicker(); return; }
    if (e.target.classList && e.target.classList.contains("tm-input") && sugKey(e)) return;
    if (e.target.classList && e.target.classList.contains("tmp-name-input") && e.key === "Enter") {
      e.preventDefault();
      var srch = S.pickHost && S.pickHost.querySelector(".tmp-search-input");
      if (srch) srch.focus();
      return;
    }
    if (e.key === "Escape" && S.rowMenu) { closeRowMenu(true); return; }
    if (e.target.classList && e.target.classList.contains("tm-rename-input")) {
      if (e.key === "Enter" && !e.isComposing && e.keyCode !== 229) {
        e.preventDefault();
        saveRename(e.target.getAttribute("data-rename-for"), e.target.value);
      } else if (e.key === "Escape") {
        e.preventDefault();
        S.renaming = ""; S.renamingHead = false; drawList(); drawHead();
      }
      return;
    }
    if (e.key === "Escape" && S.plusOpen) { setPlus(false); var pb = S.el.querySelector(".tm-plus"); if (pb) pb.focus(); return; }
    if (e.key === "Escape" && S.picker !== null) { S.focusBack = S.picker; S.picker = null; drawMsgs(false); return; }
    if (e.key === "Escape" && S.replyTo && e.target.classList && e.target.classList.contains("tm-input")) {
      S.replyTo = null; S.pending = null; drawComposer();
      var ri = S.el.querySelector(".tm-input");
      if (ri) ri.focus();
      return;
    }
    if (e.key === "Escape" && S.side) { closeSide(); return; }
    // Same Enter rules as the main chat (chat-acts.js): never while an IME is composing, and a touch screen keeps Enter
    // as a new line (the Send button sends).
    var A = actsApi();
    if (e.target.classList && e.target.classList.contains("tm-input") && A && A.enterSends(e, S.composing && S.composing())) {
      e.preventDefault();
      send();
    }
  }

  function onInput(e) {
    if (S.pickSt && e.target.classList.contains("tmp-search-input")) {
      S.pickSt.query = e.target.value;
      drawPicker("filter");
      return;
    }
    if (S.pickSt && e.target.classList.contains("tmp-name-input")) { S.pickSt.name = e.target.value; return; }
    if (S.pickSt && e.target.classList.contains("tmp-desc-input")) { S.pickSt.desc = e.target.value; return; }
    if (e.target.classList.contains("tm-input")) {
      S.pending = S.pending && (S.pending.typed || S.pending.text) === e.target.value.trim() ? S.pending : null;
      grow(e.target);
      suggest();
      drawHint();
    }
  }

  var refreshTimer = null;
  function onTeamEvent(ev) {
    if (!S || !S.el || !S.el.isConnected) return;
    var d = (ev && ev.detail) || {};
    if (d.type === "team_resync") {
      // Socket vừa nối lại (0.142.0): tin và kết cục lượt trả lời trong lúc mất kết nối chưa về, tải lại từ server.
      loadTeams(false);
      if (S.activeId) { loadMsgs(false); loadQueue(); loadTeam(); }
      return;
    }
    if (d.type === "team_typing") {
      if (d.team_id === S.activeId) { S.typing = d.typing || []; drawTyping(); }
      return;
    }
    if (d.type === "team_state" && d.deleted && d.team_id === S.activeId) closeGone(d.team_id);
    if (d.type === "team_replies" && d.team_id === S.activeId) {
      // Kết cục lượt trả lời đổi (0.142.0): chỉ vẽ lại khung tin, không cần hỏi lại danh sách.
      var k = S.msgs.findIndex(function (m) { return Number(m.id) === Number(d.message_id); });
      if (k >= 0) {
        S.msgs[k] = Object.assign({}, S.msgs[k], { replies: d.replies || [] });
        (d.replies || []).forEach(function (x) { if (x.status !== "error") delete S.retrying[d.message_id + "|" + x.agent_key]; });
        drawMsgs(false);
      }
      return;
    }
    // 0.197.0: a message landing in the team on screen is read; tell the server so the badge stays clear on every device.
    if (d.type === "team_message" && d.team_id === S.activeId && d.message && d.message.author_kind !== "owner") readSoon();
    if (d.type === "team_message" && d.team_id === S.activeId && d.message) {
      var i = S.msgs.findIndex(function (m) { return Number(m.id) === Number(d.message.id); });
      // Gói không mang phản hồi (tin đổi nhãn, kết quả việc): giữ phản hồi đang có của tin.
      var nm = d.message;
      if (i >= 0 && !("reaction" in nm)) nm = Object.assign({}, nm, { reaction: S.msgs[i].reaction });
      if (i >= 0 && !("agent_reactions" in nm) && S.msgs[i].agent_reactions) {
        nm = Object.assign({}, nm, { agent_reactions: S.msgs[i].agent_reactions });
      }
      if (i >= 0 && !("replies" in nm) && S.msgs[i].replies) nm = Object.assign({}, nm, { replies: S.msgs[i].replies });
      // Khung lọc theo việc (hợp đồng T2 mục 5): chỉ vẽ lại tin ĐANG hiện (reaction đổi ở tab khác), không chèn tin mới
      // vào danh sách của việc; khung thường thì chèn như cũ.
      if (i >= 0) S.msgs[i] = S.filterTask ? Object.assign({}, S.msgs[i], nm) : nm;
      // A message not on screen is appended only when it is newer than the latest one shown: an update of an older
      // message that is not loaded (a reaction, a label) must not land at the bottom out of order.
      else if (!S.filterTask && (S.jumped === null || S.jumped === undefined) &&
          (!S.msgs.length || Number(nm.id) > Number(S.msgs[S.msgs.length - 1].id))) { S.msgs.push(nm); queueReveal(nm); }
      if (i >= 0 || !S.filterTask) drawMsgs(false);
      // A new message while the owner reads higher up: the jump button becomes "New messages" (at the end it follows).
      if (i < 0 && S.scroll && !S.scroll.stuck()) toLatest(false);
    }
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(function () {
      loadTeams(false);
      if (d.team_id === S.activeId) { loadQueue(); loadTeam(); }
    }, 300);
  }

  // Rời trang (console.js gọi qua _pageLeave): đóng ngăn, bỏ hẹn giờ; trang dựng lại từ đầu lần ghé sau.
  function leave() {
    clearTimeout(refreshTimer);
    if (colResize()) colResize().miniTip.hide();
    if (S && S.pickSt) closePicker();
    if (S) { S.side = false; S.picker = null; stopMic(); stopReveal(); if (S.unpress) { S.unpress(); S.unpress = null; }
      if (S.unswipe) { S.unswipe(); S.unswipe = null; }
      if (S.uncard) { S.uncard(); S.uncard = null; } }
  }

  // ───────────── column widths (0.196.0) ─────────────
  // Owner, 17/10/2026: drag a column edge like the Partners page; past a point the list folds into a strip of team
  // pictures (hover shows the team card) and the side panel folds away. Same helper and card as every other page
  // (col-resize.js: JavisColResize.attach with snap/collapse, JavisColResize.miniTip).
  var LIST_MINI_W = 72;   // the Partners page's avatar strip width (workspace.js MINI_W)

  function colResize() { return typeof window !== "undefined" ? window.JavisColResize : null; }

  function listResizeOpts(page) {
    var CR = colResize();
    var side = function () { var x = page.querySelector(".tm-side"); return x && !x.hidden ? x.getBoundingClientRect().width : 0; };
    return { host: page, varName: "--tm-list-w", key: "javis_tm_list_w", min: 220, max: 480, edge: "right",
      label: "teams.resize_list", keep: 420, total: function () { return page.clientWidth; }, other: side,
      snap: { below: CR.FOLD_AT(220), to: LIST_MINI_W, onSnap: function (on) {
        page.classList.toggle("tm-mini", !!on);
        if (!on) CR.miniTip.hide();
      } } };
  }

  function sideResizeOpts(page) {
    var CR = colResize();
    var list = function () { var x = page.querySelector(".tm-list"); return x ? x.getBoundingClientRect().width : 0; };
    return { host: page, varName: "--tm-side-w", key: "javis_tm_side_w", min: 300, max: 640, edge: "left",
      label: "teams.resize_side", keep: 420, total: function () { return page.clientWidth; }, other: list,
      collapse: { below: CR.FOLD_AT(300), run: function () { closeSide(); } } };
  }

  function attachListResize() {
    var CR = colResize(), page = S.el.querySelector(".tm-page"), list = S.el.querySelector(".tm-list");
    if (!CR || !page || !list) return;
    var o = listResizeOpts(page);
    CR.apply(o);
    CR.attach(list, o);
  }

  // The side panel redraws its whole content, so its handle is put back after every draw (attach skips a duplicate).
  function attachSideResize(side) {
    var CR = colResize(), page = S.el.querySelector(".tm-page");
    if (!CR || !page || !side || side.hidden) return;
    var o = sideResizeOpts(page);
    CR.apply(o);
    CR.attach(side, o);
  }

  // The team card next to a team picture while the list is a strip (the Partners page's card): name, time, last line,
  // and what waits (badge).
  function miniCard(row) {
    var CR = colResize(), page = S.el.querySelector(".tm-page");
    if (!CR || !page || !page.classList.contains("tm-mini")) return;
    var ava = row.querySelector(".tm-gava, .tm-ava");
    var txt = function (sel) { var x = row.querySelector(sel); return x ? x.textContent.trim() : ""; };
    var badge = row.querySelector(".tm-team-bottom .tm-badge");
    // The card's state colours are the job-state ones (need red, run blue), so a team that needs you reads the same.
    var st = badge ? (badge.classList.contains("tm-badge-owner") ? "need" : badge.classList.contains("tm-badge-run") ? "run" : "") : "";
    // 0.197.0: with no job state to show, the card says how many messages wait unread.
    var un = row.querySelector(".tm-team-bottom .tm-unread");
    CR.miniTip.show(row, { ava: ava ? ava.outerHTML : "", name: txt(".tm-team-name"), time: txt(".tm-team-time"),
      sub: txt(".tm-team-sub"), stText: badge ? badge.textContent.trim() : un ? un.getAttribute("title") : "",
      st: badge ? st : un ? "need" : "" });
  }

  function render(el) {
    if (S && S.scroll) S.scroll.detach();
    S = fresh(el);
    shell();
    var CS = typeof window !== "undefined" && window.JavisChatScroll;
    var msgsBox = el.querySelector(".tm-msgs");
    S.scroll = CS && msgsBox ? CS.attach(msgsBox, { buttonClass: "jv-new-msg tm-new-msg", msg: ".tm-msg",
      hold: ".tm-hacts:hover, .tm-rx:hover", key: "data-mid", followLoads: true }) : null;
    attachListResize();
    el.addEventListener("mouseover", function (e) {
      var row = e.target.closest && e.target.closest(".tm-team");
      if (row && !row.contains(e.relatedTarget)) miniCard(row);
    });
    el.addEventListener("mouseout", function (e) {
      var row = e.target.closest && e.target.closest(".tm-team");
      if (row && !row.contains(e.relatedTarget) && colResize()) colResize().miniTip.hide();
    });
    el.addEventListener("focusin", function (e) { if (e.target.classList && e.target.classList.contains("tm-team")) miniCard(e.target); });
    el.addEventListener("focusout", function (e) {
      if (e.target.classList && e.target.classList.contains("tm-team") && colResize()) colResize().miniTip.hide();
    });
    el.addEventListener("click", onClick);
    el.addEventListener("change", onChange);
    el.addEventListener("input", onInput);
    el.addEventListener("keydown", onKey);
    var AC = actsApi();
    S.composing = AC && AC.trackComposition ? AC.trackComposition(el) : null;
    // 0.192.0: paste and drop land in this team, not in the hidden main chat (see onPaste).
    el.setAttribute("data-localdrop", "");
    el.addEventListener("paste", onPaste);
    el.addEventListener("dragenter", onDragEnter);
    el.addEventListener("dragover", onDragOver);
    el.addEventListener("dragleave", onDragLeave);
    el.addEventListener("drop", onDrop);
    // Leaving an inline name editor saves it (a redraw that removes the box does not count: the box is gone by then).
    el.addEventListener("focusout", function (e) {
      var x = e.target;
      if (!x.classList || !x.classList.contains("tm-rename-input")) return;
      setTimeout(function () {
        if (!x.isConnected || x === document.activeElement) return;
        if (S.renaming || S.renamingHead) saveRename(x.getAttribute("data-rename-for"), x.value);
      }, 0);
    });
    // Phone: long press a team row opens its Pin / Unpin menu. Long press on a message is msg-press.js and swipe to reply
    // is msg-swipe.js, both bound below.
    var hold = null, hx = 0, hy = 0, held = false;
    var stopHold = function () { clearTimeout(hold); hold = null; };
    el.addEventListener("pointerdown", function (e) {
      S.swallowClick = false;
      if (e.pointerType === "mouse") return;   // chuột đã có nút khi rê; giữ chuột để bôi chữ như thường
      // Nhấn giữ một dòng nhóm: mở menu Ghim / Bỏ ghim của nhóm đó, và chặn cú bấm mở nhóm sinh ra lúc nhấc tay.
      var row = e.target.closest && e.target.closest(".tm-team");
      if (!row) return;
      stopHold();
      hx = e.clientX; hy = e.clientY;
      hold = setTimeout(function () {
        hold = null; held = true; S.swallowClick = true;
        openRowMenu(row.getAttribute("data-team"));
      }, 500);
    });
    // Nhấn giữ đã mở bộ chọn: chặn menu ngữ cảnh mặc định của máy chạm (chọn chữ, sao chép) cho lần giữ đó.
    el.addEventListener("contextmenu", function (e) {
      if (held) { e.preventDefault(); held = false; return; }
      // Chuột phải lên một dòng nhóm (máy tính): menu Ghim / Bỏ ghim thay cho menu của trình duyệt.
      var row = e.target.closest && e.target.closest(".tm-team");
      if (row) { e.preventDefault(); openRowMenu(row.getAttribute("data-team")); }
    });
    el.addEventListener("pointermove", function (e) {
      if (hold && (Math.abs(e.clientX - hx) > 10 || Math.abs(e.clientY - hy) > 10)) stopHold();
    });
    el.addEventListener("pointerup", stopHold);
    ["pointercancel", "pointerleave"].forEach(function (n) { el.addEventListener(n, stopHold); });
    // Phone: swipe a message to the left to reply to it, like Zalo, with the same gesture as the main chat (msg-swipe.js:
    // the bubble follows the finger, a quote mark shows once far enough, vertical moves keep scrolling, a wide code block
    // or table scrolls sideways instead). Own and assistant messages both reply, as before.
    // JAVIS_CARD buttons inside this page answer in this team, not in the hidden main chat (chat-card.js).
    var JC = typeof window !== "undefined" && window.JavisCard;
    if (JC && JC.onSend) S.uncard = JC.onSend(el, function (text, btn) { sendCardReply(btn, text); });
    var SW = typeof window !== "undefined" && window.JavisMsgSwipe;
    if (SW) {
      S.unswipe = SW.bind(el, {
        selector: ".tm-msg",
        bubble: ".tm-bubble",
        can: function (m) { return !m.classList.contains("is-sheet") && !m.classList.contains("tm-msg-pending"); },
        run: function (m) { startReply(m.getAttribute("data-mid")); }
      });
    }
    // Phone (0.179.0): hold a message for the msg-press.js menu, emoji above the finger (slide to pick, assistant
    // messages) and Reply / Copy / Pin at the bottom.
    var MP = typeof window !== "undefined" && window.JavisMsgPress;
    if (MP) {
      S.unpress = MP.bind(el, {
        selector: ".tm-msg",
        bubble: ".tm-bubble",
        holdOn: ".tm-rx-btn",
        emoji: REACTIONS,
        canReact: function (m) { return m.classList.contains("tm-msg-agent"); },
        current: function (m) {
          var x = msgById(Number(m.getAttribute("data-mid")));
          return x && x.reaction && x.reaction.value !== "none" ? x.reaction.value : "";
        },
        react: function (m, value) {
          var mid = Number(m.getAttribute("data-mid"));
          var x = msgById(mid);
          sendReaction(mid, nextReaction(x && x.reaction && x.reaction.value, value));
        },
        actions: function (m) {
          var mid = m.getAttribute("data-mid");
          var x = msgById(Number(mid));
          if (!x) return [];
          var out = [{ icon: "reply", label: tw("teams.msg_reply"), run: function () { startReply(mid); } },
            { icon: "copy", label: tw("teams.copy"), run: function () { copyMsg(mid); } }];
          if (!(x.meta || {}).decision) {
            out.push({ icon: "pin", label: tw("teams.decision_pin"), run: function () {
              call("POST", teamUrl("/messages/" + q(mid) + "/decision"), { on: true }).then(function (r) {
                if (r.code !== 200) return fail(r);
                loadMsgs(false);
              });
            } });
          }
          return out;
        }
      });
    }
    drawAll(false);
    loadTeams(false);
  }

  if (typeof window !== "undefined" && window.addEventListener) {
    window.addEventListener("javis:team-event", onTeamEvent);
    // 0.197.0: back to this tab with a team open: what arrived while away is read now.
    if (typeof document !== "undefined" && document.addEventListener) document.addEventListener("visibilitychange", onVisible);
    // Auto bật/tắt ở trang Cộng sự hay tab khác (0.142.0): danh sách thành viên của nhóm đang mở đọc lại trạng thái.
    window.addEventListener("javis:resonance-agents-changed", function () {
      if (!S || !S.el || !S.el.isConnected || !S.activeId) return;
      loadTeam();
      if (S.side && S.tab === "team") loadAgents().then(function () { if (S.side && S.tab === "team") drawSide(); });
    });
  }

  var api = { render: render, leave: leave, open: open, teamListHtml: teamListHtml, messageHtml: messageHtml, queueHtml: queueHtml,
    jobStripHtml: jobStripHtml, blockedAction: blockedAction, approvalCardHtml: approvalCardHtml, workModeHtml: workModeHtml,
    mandateHtml: mandateHtml, opportunityCardHtml: opportunityCardHtml, readMandateForm: readMandateForm,
    parseCriteria: parseCriteria, acceptanceCardHtml: acceptanceCardHtml, acceptanceDecisionPayload: acceptanceDecisionPayload,
    qualityPolicyHtml: qualityPolicyHtml, qualityPolicyPayload: qualityPolicyPayload, qualityTemplatePayload: qualityTemplatePayload,
    qualityUsageHtml: qualityUsageHtml,
    taskQualityHtml: taskQualityHtml,
    jobsChip: jobsChip, jobsChipHtml: jobsChipHtml, timeShort: timeShort,
    mentionMatches: mentionMatches, mentionsFromText: mentionsFromText, mentionScan: mentionScan, removeMention: removeMention,
    callsHtml: callsHtml, foldName: foldName, emailBefore: emailBefore, composerHint: composerHint, newClientId: newClientId,
    membersHtml: membersHtml, settingsFormHtml: settingsFormHtml, capsFormHtml: capsFormHtml, capsPayload: capsPayload, saveCapsFlow: saveCapsFlow, teamTabHtml: teamTabHtml, limitsHtml: limitsHtml,
    levelOf: levelOf, grantFor: grantFor, teamAvatarHtml: teamAvatarHtml, savePin: savePin, pinTeamWith: pinTeamWith, noteHtml: noteHtml, levelsHtml: levelsHtml, turnsHtml: turnsHtml,
    bannersHtml: bannersHtml, reactCornerHtml: reactCornerHtml, reactBarHtml: reactBarHtml, sheetHtml: sheetHtml,
    hoverActsHtml: hoverActsHtml, bodyHtml: bodyHtml, listSync: listSync, pendingHtml: pendingHtml, copyTextOf: copyTextOf, fileChipHtml: fileChipHtml, uploadError: uploadError, plainPreview: plainPreview, previewText: previewText,
    nextReaction: nextReaction, REACTIONS: REACTIONS, authorityHtml: authorityHtml, readGrant: readGrant,
    searchResultsHtml: searchResultsHtml, replyStatusHtml: replyStatusHtml, headLine: headLine,
    typingHtml: typingHtml, pinsHtml: pinsHtml, markMentions: markMentions, replyRefHtml: replyRefHtml,
    allTags: allTags, filterTeams: filterTeams, tagBarHtml: tagBarHtml, tagMenuRows: tagMenuRows, tagPickRows: tagPickRows,
    lastWorkedTeam: lastWorkedTeam, TAG_NONE: TAG_NONE, unreadHtml: unreadHtml };
  if (typeof window !== "undefined") window.JavisTeams = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
