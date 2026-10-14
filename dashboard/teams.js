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
  // Icon lấy từ bộ Lucide của dashboard; chạy trong Node (test) thì không có, trả chuỗi rỗng.
  var ic = function (n, o) { return (typeof window !== "undefined" && window.ic) ? window.ic(n, o) : ""; };

  // Vai chỉ hiện cho bước của việc; câu trả lời trò chuyện thường không cần nhãn.
  var ROLE_KEY = { plan: "teams.role.plan", work: "teams.role.work", help: "teams.role.help",
    synthesize: "teams.role.synthesize" };
  var TURN_ROLE_KEY = { leader_reply: "teams.role.reply", member_reply: "teams.role.reply", plan: "teams.role.plan",
    work: "teams.role.work", help: "teams.role.help", synthesize: "teams.role.synthesize" };
  // Khoá viết TRỌN (không ghép chuỗi) để bộ kiểm i18n đọc được từng khoá đang dùng.
  var STATUS_KEY = { done: "teams.status.done", late_cancelled: "teams.status.late_cancelled", late: "teams.status.late",
    old_revision: "teams.status.old_revision", member_left: "teams.status.member_left", leader_changed: "teams.status.leader_changed" };
  var TEAM_STATUS_KEY = { active: "teams.status_active", paused: "teams.status_paused", archived: "teams.status_archived" };
  var BLOCK_KEY = { failed: "teams.block.failed", interrupted: "teams.block.interrupted", no_leader: "teams.block.no_leader",
    assignee_removed: "teams.block.assignee_removed", no_progress: "teams.block.no_progress", cap_reached: "teams.block.cap_reached",
    agent_busy_long: "teams.block.agent_busy_long", waiting_user: "teams.block.waiting_user", cancelled: "teams.block.cancelled" };
  var CAP_KEY = { task_turns: "teams.cap.task_turns", task_steps: "teams.cap.task_steps", daily_turns: "teams.cap.daily_turns",
    mentions: "teams.cap.mentions" };
  var TAB_KEY = { jobs: "teams.tab_jobs", team: "teams.tab_team" };
  var LATE = ["late_cancelled", "late", "old_revision", "member_left", "leader_changed"];
  var CAP_FIELDS = ["task_turns", "task_steps", "daily_turns", "mentions"];
  // Toàn quyền (T3, spec 13): trần trưởng nhóm đổi được trong trần trần của chủ.
  var AUTH_CAPS = ["task_turns", "task_steps", "help_depth", "daily_turns"];
  var AUTH_CAP_KEY = { task_turns: "teams.cap.task_turns", task_steps: "teams.cap.task_steps",
    help_depth: "teams.cap.help_depth", daily_turns: "teams.cap.daily_turns" };
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
  // Sáu reaction (spec mục 14.1). Emoji ở đây là DỮ LIỆU sản phẩm (giá trị chủ chọn, lưu nguyên loại), không phải icon
  // trang trí: test_icons.py cho phép đúng sáu ký tự này trong file này và kiểm cả sáu luôn có mặt.
  var REACTIONS = [
    { value: "like", emoji: "👍", key: "teams.react.like" },
    { value: "love", emoji: "❤️", key: "teams.react.love" },
    { value: "haha", emoji: "😂", key: "teams.react.haha" },
    { value: "wow", emoji: "😮", key: "teams.react.wow" },
    { value: "sad", emoji: "😢", key: "teams.react.sad" },
    { value: "angry", emoji: "😡", key: "teams.react.angry" }
  ];
  var REASON_KEY = { on_point: "teams.reason.on_point", wrong_facts: "teams.reason.wrong_facts",
    missing: "teams.reason.missing", too_long: "teams.reason.too_long", unclear: "teams.reason.unclear",
    off_topic: "teams.reason.off_topic" };
  var REASONS = ["on_point", "wrong_facts", "missing", "too_long", "unclear", "off_topic"];
  var COMMENT_MAX = 500;
  var INPUT_MAX_PX = 132;   // khung soạn tự cao theo chữ, tối đa khoảng năm dòng

  function reactionOf(value) {
    for (var i = 0; i < REACTIONS.length; i++) if (REACTIONS[i].value === value) return REACTIONS[i];
    return null;
  }

  // Chọn lại emoji đang chọn là bỏ; chọn cái khác là đổi (spec 14.1).
  function nextReaction(current, picked) {
    return current === picked ? "none" : picked;
  }

  function reactionChipHtml(m, reaction) {
    if (!reaction) return "";
    var r = reactionOf(reaction.value);
    var bits = [];
    if (r) bits.push('<span class="tm-react-emoji">' + r.emoji + "</span>" + esc(tw(r.key)));
    if ((reaction.reasons || []).length) bits.push(esc(tw("teams.react_reasons_n", { n: reaction.reasons.length })));
    if (reaction.comment) bits.push(esc(tw("teams.react_has_comment")));
    if (!bits.length) return "";
    return '<button type="button" class="tm-react-chip" data-react-open="' + esc(m.id) + '" title="' +
      esc(tw("teams.react_change")) + '">' + bits.join(" · ") + "</button>";
  }

  function pinButtonHtml(m) {
    return '<button type="button" class="ws-btn tm-pin" data-decision="' + esc(m.id) + '" data-on="1">' + ic("pin") +
      esc(tw("teams.decision_pin")) + "</button>";
  }

  // `draft`: lý do và góp ý đang soạn dở (giữ qua lần vẽ lại khi có tin mới tới). `pin`: thêm nút Ghim vào bảng.
  function reactionPickerHtml(m, reaction, draft, pin) {
    reaction = reaction || {};
    if (draft) reaction = { value: reaction.value, reasons: draft.reasons, comment: draft.comment };
    var row = REACTIONS.map(function (r) {
      var on = reaction.value === r.value;
      return '<button type="button" class="tm-react-pick" data-react="' + r.value + '" data-mid="' + esc(m.id) + '"' +
        ' aria-pressed="' + (on ? "true" : "false") + '" aria-label="' + esc(tw(r.key)) + '" title="' + esc(tw(r.key)) + '">' +
        r.emoji + "</button>";
    }).join("");
    var have = {};
    (reaction.reasons || []).forEach(function (x) { have[x] = true; });
    var reasons = REASONS.map(function (x) {
      return '<label class="tm-react-reason"><input type="checkbox" name="tm-reason" value="' + x + '"' +
        (have[x] ? " checked" : "") + "> " + esc(tw(REASON_KEY[x])) + "</label>";
    }).join("");
    return '<div class="tm-react-panel" data-panel="' + esc(m.id) + '" role="dialog" aria-label="' + esc(tw("teams.react")) + '">' +
      '<div class="tm-react-row">' + row + "</div>" +
      '<div class="tm-react-sub">' + esc(tw("teams.react_reasons")) + "</div>" +
      '<div class="tm-react-reasons">' + reasons + "</div>" +
      '<label class="tm-react-sub" for="tm-react-comment-' + esc(m.id) + '">' + esc(tw("teams.react_comment")) + "</label>" +
      '<textarea class="tm-react-comment" id="tm-react-comment-' + esc(m.id) + '" maxlength="' + COMMENT_MAX + '" rows="2"' +
      ' placeholder="' + esc(tw("teams.react_comment_ph")) + '">' + esc(reaction.comment || "") + "</textarea>" +
      '<div class="tm-react-note">' + esc(tw("teams.react_note")) + "</div>" +
      '<div class="tm-actions"><button type="button" class="ws-btn" data-react-save="' + esc(m.id) + '">' +
      esc(tw("teams.react_save")) + '</button><button type="button" class="ws-btn" data-react-clear="' + esc(m.id) + '">' +
      esc(tw("teams.react_clear")) + "</button>" + (pin ? pinButtonHtml(m) : "") +
      '<button type="button" class="ws-btn" data-react-close="' + esc(m.id) + '">' +
      esc(tw("teams.react_close")) + "</button></div></div>";
  }

  // Bảng của tin do chủ gửi (nhấn giữ hay nút ba chấm): chỉ có Ghim làm quyết định.
  function ownerPanelHtml(m) {
    return '<div class="tm-react-panel tm-owner-panel" data-panel="' + esc(m.id) + '" role="dialog" aria-label="' +
      esc(tw("teams.msg_more")) + '"><div class="tm-actions">' + pinButtonHtml(m) +
      '<button type="button" class="ws-btn" data-react-close="' + esc(m.id) + '">' + esc(tw("teams.react_close")) +
      "</button></div></div>";
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
  function teamAvatarHtml(t, box) {
    t = t || {};
    box = box || 44;
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
    return (who ? who + ": " : "") + last.text;
  }

  // `menuId`: nhóm đang mở menu Ghim / Bỏ ghim (nhấn giữ trên điện thoại, chuột phải trên máy tính). Mỗi dòng còn có nút
  // ghim riêng (anh em của nút mở nhóm, không lồng nút), hiện khi rê chuột hay focus.
  function teamListHtml(teams, activeId, now, menuId) {
    if (!teams || !teams.length) return guideHtml();
    return teams.map(function (t) {
      var on = t.team_id === activeId;
      var last = t.last || {};
      var pinned = !!t.pinned_at;
      var pin = pinned ? '<span class="tm-pinned" title="' + esc(tw("teams.pinned")) + '" aria-label="' +
        esc(tw("teams.pinned")) + '">' + ic("pin") + "</span>" : "";
      var label = esc(tw(pinned ? "teams.unpin_team" : "teams.pin_team"));
      var data = 'data-pin-team="' + esc(t.team_id) + '" data-on="' + (pinned ? "0" : "1") + '"';
      var menu = menuId === t.team_id ? '<div class="tm-row-menu" role="menu" aria-label="' + esc(tw("teams.row_menu")) + '">' +
        '<button type="button" role="menuitem" ' + data + ">" + ic("pin") + label + "</button></div>" : "";
      return '<div class="tm-team-wrap"><button type="button" class="tm-team" data-team="' + esc(t.team_id) + '"' +
        (on ? ' aria-current="true"' : "") + ">" +
        teamAvatarHtml(t, 44) + '<span class="tm-team-main"><span class="tm-team-top"><span class="tm-team-name">' + esc(t.name) +
        '</span><span class="tm-team-time">' + esc(timeShort(last.ts || t.updated_at, now)) + "</span></span>" +
        '<span class="tm-team-bottom"><span class="tm-team-sub">' + esc(previewText(t)) + "</span>" + teamBadge(t) + pin +
        "</span></span></button>" +
        '<button type="button" class="tm-row-pin" ' + data + ' aria-label="' + label + '" title="' + label + '">' + ic("pin") +
        "</button>" + menu + "</div>";
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
    timeout: "teams.reply.why.timeout", auth: "teams.reply.why.auth", no_leader: "teams.reply.why.no_leader" };
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
    if (meta.job_result) head.push('<span class="tm-result">' + esc(tw("teams.job_result")) + "</span>");
    var late = !mine && LATE.indexOf(meta.status) >= 0;
    var body = '<div class="tm-text">' + esc(m.content).replace(/\n/g, "<br>") + "</div>";
    // "Xong" là bình thường nên không hiện; chỉ báo khi câu trả lời KHÔNG được áp dụng.
    var lateLine = late ? '<div class="tm-late">' + ic("triangle-alert") + esc(tw(STATUS_KEY[meta.status])) + "</div>" : "";
    var notes = (meta.notes || []).map(function (n) { return '<div class="tm-note-line">' + esc(n) + "</div>"; }).join("");
    var prop = "";
    if (meta.proposal && meta.proposal.title) {
      prop = '<div class="tm-proposal"><div>' + esc(tw("teams.proposal", { name: who, title: meta.proposal.title })) + "</div>" +
        '<div class="tm-actions"><button type="button" class="ws-btn tm-primary" data-accept="' + esc(m.id) + '">' +
        esc(tw("teams.proposal_create")) + '</button><button type="button" class="ws-btn" data-skip="' + esc(m.id) + '">' +
        esc(tw("teams.proposal_skip")) + "</button></div></div>";
    }
    // Quyết định đã ghim: nhãn là nút bỏ ghim. Chưa ghim: nút Ghim nằm trong bảng nhấn giữ / ba chấm.
    var decision = meta.decision ? '<button type="button" class="tm-decision" data-decision="' + esc(m.id) + '" data-on="0" title="' +
      esc(tw("teams.decision_unpin")) + '">' + ic("pin") + esc(tw("teams.decision_pinned")) + "</button>" : "";
    // Nút mở bảng nằm CẠNH bong bóng (không thêm một hàng dưới mỗi tin); bảng mở ra chiếm trọn bề ngang bên dưới.
    var foot = decision, panel = "", side;
    if (mine) {
      // Tin của chủ đã ghim: bảng của nó chỉ có Ghim nên trống; bỏ nút, bỏ ghim bằng nhãn Quyết định (review T5 I5).
      side = meta.decision ? "" : '<button type="button" class="tm-more-btn" data-react-open="' + esc(m.id) + '" aria-label="' +
        esc(tw("teams.msg_more")) + '" title="' + esc(tw("teams.msg_more")) + '">' + ic("ellipsis-vertical") + "</button>";
      if (open && !meta.decision) panel = ownerPanelHtml(m);
    } else {
      foot += reactionChipHtml(m, m.reaction);
      side = '<button type="button" class="tm-react-btn" data-react-open="' + esc(m.id) + '" aria-label="' +
        esc(tw("teams.react")) + '" title="' + esc(tw("teams.react")) + '">' + ic("smile") + "</button>";
      if (open) panel = reactionPickerHtml(m, m.reaction, ctx.draft && ctx.draft.mid === m.id ? ctx.draft : null, !meta.decision);
    }
    var cls = "tm-msg" + (mine ? " tm-msg-owner" : " tm-msg-agent") + (late ? " tm-msg-late" : "") +
      (meta.job_result ? " tm-msg-result" : "") + (hit ? " tm-msg-hit" : "");
    var bubble = '<div class="tm-bubble">' + (head.length ? '<div class="tm-head">' + head.join("") + "</div>" : "") +
      body + lateLine + notes + prop + (foot ? '<div class="tm-foot">' + foot + "</div>" : "") + "</div>";
    var face = mine ? "" : agentAva(author || { name: who }, 28);
    return '<div class="' + cls + '" data-mid="' + esc(m.id) + '">' +
      (mine ? side + bubble : face + bubble + side) + panel + "</div>" + (mine ? replyStatusHtml(m, ctx) : "");
  }

  // ───────────── việc ─────────────

  // Việc bị chặn: MỘT nút giải quyết theo lý do (T5). Hết lượt thì "Cho thêm lượt" (nâng đúng giới hạn rồi chạy tiếp),
  // lỗi hay không làm ra gì mới thì Thử lại, bị dừng giữa chừng thì Làm tiếp, chưa có trưởng nhóm thì mở chỗ chọn.
  function blockedAction(kind) {
    if (kind === "cap_reached") return { act: "extend", key: "teams.act.extend" };
    if (kind === "failed" || kind === "no_progress") return { act: "retry", key: "teams.act.retry" };
    if (kind === "interrupted") return { act: "retry", key: "teams.act.continue" };
    if (kind === "no_leader") return { act: "leader", key: "teams.pick_leader" };
    if (kind === "agent_busy_long" || kind === "waiting_user") return { act: "resume", key: "teams.resume" };
    return null;
  }

  function blockedButtonHtml(t) {
    var a = blockedAction(t.block_kind || "failed");
    if (!a) return "";
    var label = esc(tw(a.key));
    if (a.act === "extend") return '<button type="button" class="ws-btn tm-primary" data-extend="' + esc(t.id) + '">' + label + "</button>";
    if (a.act === "leader") return '<button type="button" class="ws-btn tm-primary" data-open-team="1">' + label + "</button>";
    return '<button type="button" class="ws-btn tm-primary" data-unblock="' + esc(t.id) + '" data-action="' + a.act + '">' +
      label + "</button>";
  }

  function blockedCardHtml(t) {
    var kind = t.block_kind || "failed";
    return '<div class="tm-jcard"><div class="tm-jcard-text"><strong class="tm-qtitle">' + esc(t.title) + "</strong>" +
      '<span class="tm-qwhy">' + esc(t.block_reason || tw(BLOCK_KEY[kind] || BLOCK_KEY.failed)) + "</span></div>" +
      '<span class="tm-actions">' + blockedButtonHtml(t) +
      '<button type="button" class="ws-btn" data-cancel="' + esc(t.id) + '">' + esc(tw("teams.cancel")) + "</button></span></div>";
  }

  function runningRowHtml(t, withView) {
    return '<div class="tm-qrow tm-jrun"><span class="tm-spin" aria-hidden="true">' + ic("loader") + "</span>" +
      '<span class="tm-qtitle">' + esc(tw("teams.doing", { title: t.title })) + '</span><span class="tm-actions">' +
      (withView ? '<button type="button" class="ws-btn" data-view-task="' + esc(t.id) + '">' + esc(tw("teams.view_msgs")) + "</button>" : "") +
      '<button type="button" class="ws-btn" data-amend="' + esc(t.id) + '">' + esc(tw("teams.amend")) + "</button>" +
      '<button type="button" class="ws-btn" data-cancel="' + esc(t.id) + '">' + esc(tw("teams.cancel")) + "</button></span></div>";
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
  function queueHtml(q) {
    q = q || {};
    var running = q.running || [], waiting = q.waiting || [], blocked = q.blocked || [];
    if (!running.length && !waiting.length && !blocked.length) return '<div class="tm-empty">' + esc(tw("teams.queue_empty")) + "</div>";
    var h = "";
    if (running.length) {
      h += '<div class="tm-qhead">' + esc(tw("teams.queue_running")) + "</div>";
      h += running.map(function (t) { return runningRowHtml(t, true); }).join("");
    }
    if (blocked.length) {
      h += '<div class="tm-qhead">' + esc(tw("teams.queue_blocked")) + "</div>";
      h += blocked.map(blockedCardHtml).join("");
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
          '<button type="button" class="ws-btn" data-cancel="' + esc(t.id) + '">' + esc(tw("teams.cancel")) + "</button></span></div>";
      }).join("");
    }
    return h;
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
    return { keys: out, ambiguous: ambiguous };
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
  function callsHtml(keys, members) {
    if (!(keys || []).length) return "";
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
        '<span class="tm-actions">' + (lead
          ? '<button type="button" class="ws-btn" data-leader="">' + esc(tw("teams.remove_leader")) + "</button>"
          : '<button type="button" class="ws-btn" data-leader="' + esc(m.agent_key) + '">' + esc(tw("teams.make_leader")) + "</button>") +
        '<button type="button" class="ws-btn" data-remove="' + esc(m.agent_key) + '">' + esc(tw("teams.remove")) + "</button></span></div></div>";
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
    return '<fieldset class="tm-levels">' + legend + LEVELS.map(function (L) {
      return '<label class="tm-level"><input type="radio" name="tm-level" value="' + L.n + '"' + (lvl === L.n ? " checked" : "") +
        '><span class="tm-level-body"><strong>' + esc(tw(L.key)) + '</strong><span class="tm-level-desc">' + esc(tw(L.desc)) +
        "</span></span></label>";
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
    return '<form class="tm-form" onsubmit="return false">' +
      '<label class="tm-field"><span>' + esc(tw("teams.name")) + '</span><input name="tm-set-name" value="' + esc(team.name) + '"></label>' +
      '<label class="tm-field"><span>' + esc(tw("teams.description")) + '</span><textarea name="tm-set-desc" rows="2">' + esc(team.description) + "</textarea></label>" +
      '<div class="tm-field"><span>' + esc(tw("teams.status")) + '</span><div class="tm-radios">' + st + "</div></div>" +
      '<button type="button" class="ws-btn tm-save">' + esc(tw("teams.save")) + "</button></form>";
  }

  // Các số giới hạn của nhóm (trong Nâng cao). Nút Lưu ở cuối.
  function capsFormHtml(team) {
    var caps = team.caps || {};
    var capRows = CAP_FIELDS.map(function (k) {
      return '<label class="tm-field tm-cap"><span>' + esc(tw(CAP_KEY[k])) + '</span><input type="number" min="0" name="tm-cap-' + k +
        '" value="' + esc(caps[k] == null ? "" : caps[k]) + '"></label>';
    }).join("");
    return '<form class="tm-form tm-caps-form" onsubmit="return false"><div class="tm-qhead">' + esc(tw("teams.caps")) + "</div>" +
      // Trưởng nhóm đang được tự quyết: số trong hộp quyền đè số ở đây; nói rõ thay vì để "Đã lưu" mà không đổi gì.
      (team.authority && team.authority.authority ? '<div class="tm-note-line">' + esc(tw("teams.caps_full_note")) + "</div>" : "") +
      capRows + '<button type="button" class="ws-btn tm-caps-save">' + esc(tw("teams.save")) + "</button></form>";
  }

  function capText(v) {
    return v === null || v === undefined ? tw("teams.auth.unlimited") : String(v);
  }

  function capInputs(name, v) {
    var unl = !!(v && typeof v === "object" && v.unlimited);
    var num = !unl && v !== null && v !== undefined && typeof v !== "object" ? String(v) : "";
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
    var rows = AUTH_CAPS.map(function (k) {
      return '<div class="tm-field tm-auth-cap"><span>' + esc(tw(AUTH_CAP_KEY[k])) + "</span>" +
        '<span class="tm-auth-pair"><span class="tm-auth-lbl">' + esc(tw("teams.auth.cap_value")) + "</span>" +
        capInputs("tm-auth-cap-" + k, (grant.caps || {})[k]) + "</span>" +
        '<span class="tm-auth-pair"><span class="tm-auth-lbl">' + esc(tw("teams.auth.cap_ceiling")) + "</span>" +
        capInputs("tm-auth-ceil-" + k, (grant.ceilings || {})[k]) + "</span></div>";
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
    AUTH_CAPS.forEach(function (k) {
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
    return '<div class="tm-turns"><div class="tm-qhead">' + esc(tw("teams.turns_today", { n: today, cap: (team.caps || {}).daily_turns })) + "</div>" +
      "<div>" + esc(tw("teams.turns_by_agent")) + ": " + list(byAgent, function (k) { return nameOf(team.members, k); }) + "</div>" +
      "<div>" + esc(tw("teams.turns_by_role")) + ": " + list(byRole, function (k) { return tw(k); }) + "</div>" +
      '<div class="tm-sub">' + esc(tw("teams.turns_note")) + "</div></div>";
  }

  // Tab Nhóm: thành viên, mức tự quyết, số lần đã dùng hôm nay, tên và trạng thái; mọi con số trong Nâng cao (đóng sẵn).
  function teamTabHtml(team, agents, ui) {
    ui = ui || {};
    var nAct = (team.members || []).filter(function (m) { return !m.status || m.status === "active"; }).length;
    return '<section class="tm-sec"><div class="tm-qhead">' + esc(tw("teams.tab_members")) + " · " +
      esc(tw("teams.head_people", { n: nAct })) + "</div>" +
      membersHtml(team, agents, ui.openMember) + "</section>" +
      '<section class="tm-sec">' + levelsHtml(team) + usageHtml(team) + "</section>" +
      '<section class="tm-sec"><div class="tm-qhead">' + esc(tw("teams.tab_team")) + "</div>" +
      '<label class="tm-rs tm-pin-row"><input type="checkbox" class="tm-pin-toggle"' + (team.pinned_at ? " checked" : "") +
      "><span>" + esc(tw("teams.pin_top")) + "</span></label>" + settingsFormHtml(team) + "</section>" +
      '<details class="tm-adv"' + (ui.advOpen ? " open" : "") + '><summary class="tm-adv-sum">' + esc(tw("teams.advanced")) +
      '</summary><div class="tm-sub">' + esc(tw("teams.advanced_note")) + "</div>" + capsFormHtml(team) + authorityHtml(team) +
      turnsHtml(ui.turns || [], team) + "</details>";
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

  function call(method, url, body) {
    var opt = { method: method, credentials: "same-origin" };
    if (body !== undefined) {
      opt.headers = { "Content-Type": "application/json" };
      opt.body = JSON.stringify(body);
    }
    var sep = url.indexOf("?") >= 0 ? "&" : "?";
    return fetch(url + sep + "brain=" + q(brain()), opt).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) { return { code: r.status, j: j || {} }; });
    });
  }

  var S = null;

  function fresh(el) {
    return { el: el, teams: [], next: null, activeId: "", team: null, queue: null, msgs: [], hasMore: false,
      agents: [], asJob: false, pending: null, tab: "jobs", side: false, view: "list", loaded: false,
      filterTask: "", taskTitles: {}, teamNames: {}, note: "", skipped: {}, picker: null, draft: null,
      focusPicker: false, focusBack: null, searchOpen: false, searchResults: null, searchQuery: "", jumped: null,
      openMember: null, advOpen: false, turns: [], sideOpener: null, rowMenu: null, focusRowMenu: false, swallowClick: false,
      picked: [], retrying: {}, pickSt: null, pickOpener: null, pickHost: null, roster: [] };
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
      '<button type="button" class="ws-btn tm-new">' + ic("plus") + esc(tw("teams.create")) + "</button></div>" +
      '<div class="tm-teams"></div><button type="button" class="ws-btn tm-more-teams" hidden>' + esc(tw("teams.next_page")) + "</button></aside>" +
      '<section class="tm-chat"><div class="tm-bar tm-chat-head"></div><div class="tm-search" hidden></div>' +
      '<div class="tm-banners"></div><div class="tm-jobs" hidden></div>' +
      '<div class="tm-filterbar" hidden></div><div class="tm-msgs" aria-live="polite"></div><div class="tm-composer"></div></section>' +
      // Vùng thông báo chung NGOÀI khung chat: trên điện thoại khung chat bị ẩn khi đang ở danh sách, thông báo (vd. ghim
      // lỗi) vẫn phải nhìn thấy (review 4f6268bd #2).
      '<aside class="tm-side" hidden></aside><div class="tm-scrim" hidden></div><div class="tm-note" role="status" aria-live="polite" hidden></div></div>';
  }

  function drawList() {
    var box = S.el.querySelector(".tm-teams");
    if (box) box.innerHTML = S.loaded || S.teams.length ? teamListHtml(S.teams, S.activeId, undefined, S.rowMenu) : "";
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
    var back = '<button type="button" class="ws-btn tm-back" aria-label="' + esc(tw("teams.back")) + '" title="' +
      esc(tw("teams.back")) + '">' + ic("chevron-left") + "</button>";
    if (!S.team) {
      head.innerHTML = "";
      head.hidden = true;
    } else {
      var t = S.team;
      var lead = headLine(t);
      head.hidden = false;
      head.innerHTML = back + teamAvatarHtml(t, 36) +
        '<div class="tm-title"><strong>' + esc(t.name) + '</strong><span class="tm-sub">' + esc(lead) + "</span></div>" +
        jobsChipHtml(S.queue, S.side && S.tab === "jobs") +
        '<button type="button" class="ws-btn tm-icon tm-search-btn" aria-label="' + esc(tw("teams.search")) + '" title="' +
        esc(tw("teams.search")) + '"' + (S.searchOpen ? ' aria-expanded="true"' : ' aria-expanded="false"') + ">" + ic("search") +
        "</button>" +
        '<button type="button" class="ws-btn tm-icon tm-gear" aria-expanded="' + (S.side && S.tab === "team" ? "true" : "false") +
        '" aria-label="' + esc(tw("teams.settings_btn")) + '" title="' + esc(tw("teams.settings_btn")) + '">' +
        ic("ellipsis-vertical") + "</button>";
    }
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
      '</span><button type="button" class="ws-btn tm-filter-clear">' + esc(tw("teams.filter_clear")) + "</button>";
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

  function ctx() {
    return { members: S.team ? S.team.members : [], authors: S.team ? S.team.authors : null,
      leaderKey: S.team && S.team.leader_key, taskTitles: S.taskTitles,
      picker: S.picker, draft: S.draft, jumped: S.jumped, retrying: S.retrying };
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

  function drawMsgs(stick) {
    var box = S.el.querySelector(".tm-msgs");
    if (!box) return;
    if (!S.team) {
      box.innerHTML = S.teams.length ? '<div class="tm-empty tm-empty-chat">' + esc(tw("teams.pick_team")) + "</div>" : "";
      return;
    }
    var atEnd = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
    // Đang soạn góp ý trong bộ chọn mà có tin mới tới: giữ con trỏ và chỗ cuộn, không kéo xuống cuối (review T2).
    var act = document.activeElement;
    var typing = S.picker !== null && act && act.classList && act.classList.contains("tm-react-comment") ?
      { start: act.selectionStart, end: act.selectionEnd, top: box.scrollTop } : null;
    var list = S.msgs.filter(function (m) { return !S.skipped[m.id]; });
    box.innerHTML = (S.jumped !== null && S.jumped !== undefined ? '<div class="tm-jumped">' + esc(tw("teams.search_viewing")) +
      ' <button type="button" class="ws-btn tm-jump-back">' + ic("chevrons-down") + esc(tw("teams.search_back")) +
      "</button></div>" : "") + (S.hasMore ? '<button type="button" class="ws-btn tm-older">' + esc(tw("teams.older")) + "</button>" : "") +
      (!list.length && !S.hasMore ? '<div class="tm-empty tm-empty-chat">' + esc(tw("teams.chat_empty")) + "</div>" : "") +
      list.map(function (m) {
        var mm = m;
        if (S.skipped["p" + m.id] && m.meta && m.meta.proposal) mm = Object.assign({}, m, { meta: Object.assign({}, m.meta, { proposal: null }) });
        return messageHtml(mm, ctx());
      }).join("");
    if (typing) {
      box.scrollTop = typing.top;
      var ta = box.querySelector(".tm-react-comment");
      if (ta) { ta.focus(); try { ta.setSelectionRange(typing.start, typing.end); } catch (e) {} }
      return;
    }
    // Bảng đang "mở" mà không vẽ ra (tin đã đổi, đã ghim): bỏ trạng thái mở, kẻo tin mới không còn tự cuộn xuống.
    if (S.picker !== null && !box.querySelector('[data-panel="' + S.picker + '"]')) S.picker = null;
    if ((stick || atEnd) && S.picker === null) box.scrollTop = box.scrollHeight;
    if (S.focusPicker) {
      // Mở bộ chọn: focus vào nút đầu của bảng (bàn phím và trình đọc màn hình vào được bảng, Escape đóng được).
      S.focusPicker = false;
      var first = box.querySelector(".tm-react-panel .tm-react-pick") || box.querySelector(".tm-react-panel button");
      if (first) first.focus();
    }
    if (S.focusBack !== null && S.focusBack !== undefined) {
      var back = box.querySelector('.tm-react-btn[data-react-open="' + S.focusBack + '"]') ||
        box.querySelector('.tm-more-btn[data-react-open="' + S.focusBack + '"]');
      S.focusBack = null;
      if (back) back.focus();
    }
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
    var draft = S.pending ? S.pending.text : old ? old.value : "";
    var off = S.team.status === "archived";
    box.innerHTML = '<div class="tm-sug" role="listbox" id="tm-sug" aria-label="' + esc(tw("teams.mention_list")) + '" hidden></div>' +
      '<div class="tm-calls" hidden></div><div class="tm-hint" hidden></div>' +
      '<div class="tm-row"><button type="button" class="tm-mode tm-asjob" aria-pressed="' + (S.asJob ? "true" : "false") +
      '" title="' + esc(tw("teams.as_job_title")) + '"' + (off ? " disabled" : "") + ">" + ic("list-todo") + "<span>" +
      esc(tw("teams.as_job")) + "</span></button>" +
      '<textarea class="tm-input" rows="1" aria-autocomplete="list" aria-controls="tm-sug" placeholder="' + esc(tw(S.asJob ? "teams.placeholder_job" : "teams.placeholder")) + '"' +
      (off ? " disabled" : "") + ">" + esc(draft) + "</textarea>" +
      '<button type="button" class="tm-send" aria-label="' + esc(tw("teams.send")) + '" title="' + esc(tw("teams.send")) + '">' +
      ic("send") + "</button></div>";
    grow(box.querySelector(".tm-input"));
    drawHint();
    if (S.focusComposer && !off) {
      S.focusComposer = false;
      var inp = box.querySelector(".tm-input");
      if (inp) { try { inp.focus(); } catch (e) {} }
    }
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

  function drawHint() {
    var hintEl = S.el.querySelector(".tm-hint");
    if (!hintEl || !S.team) return;
    var sc = currentScan();
    var h = composerHint({ mentions: sc.keys, ambiguous: sc.ambiguous, asJob: S.asJob, cap: (S.team.caps || {}).mentions,
      members: S.team.members, leaderKey: S.team.leader_key });
    hintEl.textContent = h.text;
    hintEl.hidden = !h.text;
    var calls = S.el.querySelector(".tm-calls");
    if (calls) {
      var ch = callsHtml(sc.keys, S.team.members);
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
    var tabs = ["jobs", "team"].map(function (k) {
      return '<button type="button" class="tm-tab" role="tab" data-tab="' + k + '" aria-selected="' + (S.tab === k ? "true" : "false") +
        '">' + esc(tw(TAB_KEY[k])) + "</button>";
    }).join("");
    var body = S.tab === "jobs" ? queueHtml(S.queue)
      : teamTabHtml(S.team, S.agents, { openMember: S.openMember, advOpen: S.advOpen, turns: S.turns });
    side.innerHTML = '<div class="tm-bar tm-side-bar"><div class="tm-tabs" role="tablist">' + tabs + "</div>" +
      '<button type="button" class="ws-btn tm-icon tm-close" aria-label="' + esc(tw("teams.close")) + '" title="' +
      esc(tw("teams.close")) + '">' + ic("x") + '</button></div><div class="tm-side-body" role="tabpanel" aria-label="' +
      esc(tw(TAB_KEY[S.tab])) + '">' + body + "</div>";
    var nb = side.querySelector(".tm-side-body");
    if (nb && keep) nb.scrollTop = top;
  }

  function drawAll(stick) {
    drawPage(); drawList(); drawHead(); drawJobs(); drawMsgs(stick); drawComposer(); drawSide();
  }

  // Mở ngăn: nhớ nút đã mở (chip việc, ba chấm, nút trên băng hay thẻ việc) để lúc đóng trả focus về đúng nút đó.
  function openSide(tab, opener) {
    if (opener && opener.matches) S.sideOpener = opener.matches(".tm-jobs-chip") ? ".tm-jobs-chip"
      : opener.matches(".tm-gear") ? ".tm-gear" : null;
    S.side = true;
    S.tab = tab;
    drawSide(true);
    drawHead();
    if (tab === "team") loadAgents().then(function () { if (S.side && S.tab === "team") drawSide(); });
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
        openTeam(want, wantTask);
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

  function loadTeam() {
    if (!S.activeId) return Promise.resolve();
    var forTeam = S.activeId;
    return call("GET", teamUrl()).then(function (r) {
      if (S.activeId !== forTeam) return;
      if (r.code !== 200) return fail(r);
      S.team = r.j.team;
      drawHead(); drawHint(); drawSide();
    });
  }

  function loadMsgs(older) {
    if (!S.activeId) return Promise.resolve();
    // Tải khúc mới nhất (gửi tin, lọc việc, về tin mới nhất): thoát chế độ xem tin cũ, tin mới tới lại được nối vào.
    if (!older) S.jumped = null;
    var url = S.filterTask ? teamUrl("/tasks/" + q(S.filterTask)) : teamUrl("/messages");
    if (older && S.msgs.length && !S.filterTask) url += "?before_ts=" + q(S.msgs[0].ts) + "&before_id=" + q(S.msgs[0].id);
    var forTeam = S.activeId;
    return call("GET", url).then(function (r) {
      if (S.activeId !== forTeam) return;
      if (r.code !== 200) return fail(r);
      var got = r.j.messages || [];
      // Lọc theo một việc đã xong (mở từ tab Công việc): việc không còn trong hàng đợi, học tên từ chính bản ghi việc để
      // thanh lọc và nhãn tin hiện tên việc thay vì mã (0.142.0).
      if (S.filterTask && r.j.task && r.j.task.id) {
        S.taskTitles[r.j.task.id] = r.j.task.title || S.taskTitles[r.j.task.id] || "";
        got.forEach(function (m) { if (m.task_id === r.j.task.id && !m.task_title) m.task_title = r.j.task.title || ""; });
        drawFilterbar();
      }
      S.msgs = older ? got.concat(S.msgs) : got;
      S.hasMore = !S.filterTask && !!r.j.has_more;
      drawMsgs(!older);
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
    var input = S.el.querySelector(".tm-input");
    if (input) input.value = "";
    setNote("");
    drawAll(true);
    Promise.all([loadTeam(), loadQueue(), loadMsgs(false)]).then(function () { if (S.activeId === id) drawAll(true); });
  }

  function send() {
    var input = S.el.querySelector(".tm-input");
    if (!input || !S.team) return;
    var text = input.value.trim();
    if (!text) return;
    var scan = mentionScan(text, S.team.members, S.picked);
    if (scan.ambiguous.length) { drawHint(); return; }
    var mentions = scan.keys;
    // Gửi lại sau rớt mạng: cùng chữ thì giữ ĐÚNG mã cũ để server trả tin cũ, không thêm lượt.
    if (!S.pending || S.pending.text !== text) S.pending = { text: text, id: newClientId() };
    var body = { text: text, mentions: mentions, as_job: S.asJob, client_msg_id: S.pending.id };
    var btn = S.el.querySelector(".tm-send");
    if (btn) btn.disabled = true;
    var forTeam = S.activeId;
    call("POST", teamUrl("/messages"), body).then(function (r) {
      if (S.activeId !== forTeam) return;
      if (r.code !== 200) { fail(r); drawHint(); return; }
      S.pending = null; S.asJob = false; S.picked = []; input.value = "";
      setNote(r.j.notes && r.j.notes.length ? r.j.notes.filter(function (n) { return !/^[a-z_]+$/.test(n); }).join(" · ") : "");
      if ((r.j.notes || []).indexOf("daily_cap") >= 0) setNote(tw("teams.daily_cap"));
      drawComposer();
      var again = S.el.querySelector(".tm-input");
      if (again) again.focus();
      loadMsgs(false); loadQueue();
    }).catch(function () {
      setNote(tw("teams.err_network"));
      drawHint();
    });
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
    S.sugKeys = list.map(function (a) { return a.agent_key; });
    if (S.sugIdx == null || S.sugIdx >= list.length) S.sugIdx = 0;
    box.hidden = !list.length;
    input.setAttribute("aria-expanded", list.length ? "true" : "false");
    box.innerHTML = list.map(function (a, i) {
      // Trùng tên: thêm mã ngắn (slug) để chọn đúng người. Vai của trợ lý (dòng "role" ở Cộng sự) nằm dưới tên.
      var dup = seen[foldName(a.name || a.slug).trim()] > 1;
      var on = i === S.sugIdx;
      return '<button type="button" class="tm-sug-item' + (on ? " is-active" : "") + '" role="option" id="tm-sug-' + i +
        '" aria-selected="' + (on ? "true" : "false") + '" data-mention="' + esc(a.agent_key) + '">' + agentAva(a, 28) +
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
    S.focusRowMenu = true;
    drawList();
  }

  function closeRowMenu(focusRow) {
    var id = S.rowMenu;
    S.rowMenu = null;
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
    if (back) { try { back.focus(); } catch (e) {} }
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
    if (!t || !(S.el.contains(t) || (S.pickHost && S.pickHost.contains(t)))) return;
    var d = t.dataset || {};
    // Nhấn giữ vừa mở menu ghim: cú bấm sinh ra lúc nhấc tay không được mở nhóm.
    if (d.team && S.swallowClick) { S.swallowClick = false; return; }
    if (d.pinTeam) {
      if (S.rowMenu) closeRowMenu();
      return pinTeam(d.pinTeam, d.on === "1", S.el.contains(t) ? t : null);
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
    if (t.classList.contains("tm-asjob")) {
      S.asJob = !S.asJob;
      // Đổi loại tin là một tin KHÁC: mã client cũ thuộc tin trước, gửi lại bằng nó sẽ được trả tin cũ khác loại.
      S.pending = null;
      t.setAttribute("aria-pressed", S.asJob ? "true" : "false");
      var inp = S.el.querySelector(".tm-input");
      if (inp) { inp.placeholder = tw(S.asJob ? "teams.placeholder_job" : "teams.placeholder"); inp.focus(); }
      drawHint();
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
    if (d.jump) return jumpTo(d.jump, d.ts);
    if (t.classList.contains("tm-jump-back")) { S.jumped = null; loadMsgs(false); return; }
    if (t.classList.contains("tm-filter-clear")) { S.filterTask = ""; drawFilterbar(); loadMsgs(false); return; }
    if (d.reactOpen) {
      var was = S.picker;
      S.picker = S.picker === Number(d.reactOpen) ? null : Number(d.reactOpen);
      S.draft = null;
      if (S.picker !== null) S.focusPicker = true; else S.focusBack = was;
      drawMsgs(false);
      return;
    }
    if (d.reactClose) { S.focusBack = S.picker; S.picker = null; S.draft = null; drawMsgs(false); return; }
    if (d.react) {
      var cur = msgById(Number(d.mid));
      var form = panelValues(Number(d.mid), cur);
      return sendReaction(Number(d.mid), nextReaction(cur && cur.reaction && cur.reaction.value, d.react), form.reasons,
        form.comment);
    }
    if (d.reactSave) {
      var cm = msgById(Number(d.reactSave));
      var fv = panelValues(Number(d.reactSave), cm);
      return sendReaction(Number(d.reactSave), (cm && cm.reaction && cm.reaction.value) || "none", fv.reasons, fv.comment);
    }
    if (d.reactClear) return sendReaction(Number(d.reactClear), "none", [], "");
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
    if (d.skip) { S.skipped["p" + d.skip] = true; drawMsgs(false); return; }
    if (d.decision) {
      return call("POST", teamUrl("/messages/" + q(d.decision) + "/decision"), { on: d.on === "1" }).then(function (r) {
        if (r.code !== 200) return fail(r);
        S.picker = null; S.draft = null;
        loadMsgs(false);
      });
    }
    if (d.prio) {
      return call("POST", teamUrl("/queue/" + q(d.prio) + "/priority"),
        { on: d.on === "1", expected_queue_version: (S.queue && S.queue.version) || 0 }).then(function (r) { act(r); });
    }
    if (d.cancel) {
      var ct = S.taskTitles[d.cancel] || d.cancel;
      if (typeof confirm === "function" && !confirm(tw("teams.cancel_confirm", { title: ct }))) return;
      return call("POST", teamUrl("/tasks/" + q(d.cancel) + "/cancel")).then(function (r) { act(r); });
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

  // Lý do và góp ý đang soạn trong bảng chọn (chưa lưu thì lấy theo phản hồi đã có).
  function panelValues(mid, m) {
    var panel = S.el.querySelector('[data-panel="' + mid + '"]');
    var have = (m && m.reaction) || {};
    if (!panel) return { reasons: have.reasons || [], comment: have.comment || "" };
    var reasons = Array.prototype.map.call(panel.querySelectorAll('input[name="tm-reason"]:checked'), function (x) { return x.value; });
    var box = panel.querySelector(".tm-react-comment");
    return { reasons: reasons, comment: box ? box.value.trim().slice(0, COMMENT_MAX) : "" };
  }

  // Thả cảm xúc: chỉ ghi phản hồi (không mở lượt, không gọi model). Mỗi lần gửi một nonce mới.
  function sendReaction(mid, value, reasons, comment) {
    return call("POST", teamUrl("/messages/" + q(mid) + "/reaction"),
      { value: value, reasons: reasons, comment: comment, nonce: newClientId() }).then(function (r) {
      if (r.code !== 200) return fail(r);
      var m = msgById(mid);
      if (m) m.reaction = r.j.reaction || null;
      S.focusBack = S.picker;
      S.picker = null;
      S.draft = null;
      setNote(tw("teams.react_saved"));
      drawMsgs(false);
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

  function saveCaps() {
    var caps = {};
    CAP_FIELDS.forEach(function (k) {
      var v = val("tm-cap-" + k);
      if (v !== "" && Number(v) !== Number((S.team.caps || {})[k])) caps[k] = Number(v);
    });
    if (!Object.keys(caps).length) { setNote(tw("teams.saved")); return; }
    call("POST", teamUrl("/caps"), { caps: caps }).then(function (r) {
      if (r.code === 200) setNote(tw("teams.saved"));
      act(r, drawSide);
    });
  }

  function onChange(e) {
    if (S.pickSt && e.target.classList && e.target.classList.contains("tmp-check")) {
      pickToggle(e.target.getAttribute("data-pick-slug"));
      return;
    }
    if (S.pickSt && e.target.classList && e.target.classList.contains("tmp-leader-pick")) {
      S.pickSt = Object.assign({}, S.pickSt, { leader: e.target.value, leaderTouched: true });
      return;
    }
    if (e.target.name === "tm-reason" && S.picker !== null) {
      var pv = panelValues(S.picker, msgById(S.picker));
      S.draft = { mid: S.picker, reasons: pv.reasons, comment: pv.comment };
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
    if (e.target.name && /^tm-auth-(cap|ceil)-[a-z_]+-unl$/.test(e.target.name)) {
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
    if (e.key === "Escape" && S.picker !== null) { S.focusBack = S.picker; S.picker = null; S.draft = null; drawMsgs(false); return; }
    if (e.key === "Escape" && S.side) { closeSide(); return; }
    if (e.target.classList && e.target.classList.contains("tm-input") && e.key === "Enter" && !e.shiftKey && !e.isComposing &&
        e.keyCode !== 229) {
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
    if (e.target.classList.contains("tm-react-comment") && S.picker !== null) {
      S.draft = { mid: S.picker, reasons: panelValues(S.picker, msgById(S.picker)).reasons, comment: e.target.value };
      return;
    }
    if (e.target.classList.contains("tm-input")) {
      S.pending = S.pending && S.pending.text === e.target.value.trim() ? S.pending : null;
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
    if (d.type === "team_message" && d.team_id === S.activeId && d.message && !S.filterTask) {
      var i = S.msgs.findIndex(function (m) { return m.id === d.message.id; });
      // Gói không mang phản hồi (tin đổi nhãn, kết quả việc): giữ phản hồi đang có của tin.
      var nm = d.message;
      if (i >= 0 && !("reaction" in nm)) nm = Object.assign({}, nm, { reaction: S.msgs[i].reaction });
      if (i >= 0 && !("replies" in nm) && S.msgs[i].replies) nm = Object.assign({}, nm, { replies: S.msgs[i].replies });
      if (i >= 0) S.msgs[i] = nm; else if (S.jumped === null || S.jumped === undefined) S.msgs.push(nm);
      drawMsgs(false);
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
    if (S && S.pickSt) closePicker();
    if (S) { S.side = false; S.picker = null; }
  }

  function render(el) {
    S = fresh(el);
    shell();
    el.addEventListener("click", onClick);
    el.addEventListener("change", onChange);
    el.addEventListener("input", onInput);
    el.addEventListener("keydown", onKey);
    // Điện thoại: nhấn giữ một tin mở bảng của tin đó (cảm xúc và ghim cho tin trợ lý, ghim cho tin của chủ; spec 14.3).
    var hold = null, hx = 0, hy = 0, held = false;
    var stopHold = function () { clearTimeout(hold); hold = null; };
    el.addEventListener("pointerdown", function (e) {
      S.swallowClick = false;
      if (e.pointerType === "mouse") return;   // chuột đã có nút khi rê; giữ chuột để bôi chữ như thường
      // Nhấn giữ một dòng nhóm: mở menu Ghim / Bỏ ghim của nhóm đó, và chặn cú bấm mở nhóm sinh ra lúc nhấc tay.
      var row = e.target.closest && e.target.closest(".tm-team");
      if (row) {
        stopHold();
        hx = e.clientX; hy = e.clientY;
        hold = setTimeout(function () {
          hold = null; held = true; S.swallowClick = true;
          openRowMenu(row.getAttribute("data-team"));
        }, 500);
        return;
      }
      var msg = e.target.closest && e.target.closest(".tm-msg");
      if (!msg || e.target.closest("button, a, input, textarea, select")) return;
      // Tin của chủ đã ghim: bảng của nó trống (bỏ ghim bằng nhãn Quyết định), khỏi mở.
      if (msg.classList.contains("tm-msg-owner") && msg.querySelector(".tm-decision")) return;
      stopHold();
      hx = e.clientX; hy = e.clientY;
      hold = setTimeout(function () {
        hold = null; held = true;
        S.picker = Number(msg.getAttribute("data-mid")); S.draft = null; S.focusPicker = true; drawMsgs(false);
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
    ["pointerup", "pointercancel", "pointerleave"].forEach(function (n) { el.addEventListener(n, stopHold); });
    drawAll(false);
    loadTeams(false);
  }

  if (typeof window !== "undefined" && window.addEventListener) {
    window.addEventListener("javis:team-event", onTeamEvent);
    // Auto bật/tắt ở trang Cộng sự hay tab khác (0.142.0): danh sách thành viên của nhóm đang mở đọc lại trạng thái.
    window.addEventListener("javis:resonance-agents-changed", function () {
      if (!S || !S.el || !S.el.isConnected || !S.activeId) return;
      loadTeam();
      if (S.side && S.tab === "team") loadAgents().then(function () { if (S.side && S.tab === "team") drawSide(); });
    });
  }

  var api = { render: render, leave: leave, open: open, teamListHtml: teamListHtml, messageHtml: messageHtml, queueHtml: queueHtml,
    jobStripHtml: jobStripHtml, blockedAction: blockedAction, jobsChip: jobsChip, jobsChipHtml: jobsChipHtml, timeShort: timeShort,
    mentionMatches: mentionMatches, mentionsFromText: mentionsFromText, mentionScan: mentionScan, removeMention: removeMention,
    callsHtml: callsHtml, foldName: foldName, emailBefore: emailBefore, composerHint: composerHint, newClientId: newClientId,
    membersHtml: membersHtml, settingsFormHtml: settingsFormHtml, capsFormHtml: capsFormHtml, teamTabHtml: teamTabHtml,
    levelOf: levelOf, grantFor: grantFor, teamAvatarHtml: teamAvatarHtml, savePin: savePin, pinTeamWith: pinTeamWith, noteHtml: noteHtml, levelsHtml: levelsHtml, turnsHtml: turnsHtml,
    bannersHtml: bannersHtml, reactionPickerHtml: reactionPickerHtml, reactionChipHtml: reactionChipHtml,
    nextReaction: nextReaction, REACTIONS: REACTIONS, authorityHtml: authorityHtml, readGrant: readGrant,
    searchResultsHtml: searchResultsHtml, replyStatusHtml: replyStatusHtml, headLine: headLine };
  if (typeof window !== "undefined") window.JavisTeams = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
