/* Tab Công việc của một trợ lý ở trang Cộng sự (0.142.0), thay tab Thư mục.
 *
 * Đọc GET /agents/{slug}/jobs: việc của trợ lý gom theo agent_key từ nhóm, chat riêng và Auto (cùng bản ghi gốc, không
 * sao chép). Lọc theo nguồn (Tất cả, Nhóm, Chat riêng, Auto) và theo bốn trạng thái (Đang làm, Đang chờ, Cần bạn, Đã
 * xong); lọc và phân trang làm ở server, nút "Xem thêm" đọc trang sau.
 *
 * Mỗi thẻ: nguồn, vai (Điều phối, Thực hiện, Hỗ trợ, Kiểm chứng), cập nhật lúc nào, bước kế tiếp (server tính), kết quả
 * hay lý do, mục được kiểm (việc kiểm chứng). Thao tác dùng route gốc của từng nguồn: Mở, Huỷ, Tiếp tục (mục tiêu đang
 * dừng, gửi kèm revision), Ưu tiên (việc chờ trong hàng của nhóm), Giao kiểm chứng (mở form với mục này đã gắn).
 *
 * Giao việc: yêu cầu, tiêu chí xong, nơi nhận kết quả (chat riêng hay một nhóm trợ lý đang ở), kiểu việc (thường hay
 * kiểm chứng), rồi một bước xác nhận trước khi tạo. `nonce` giữ nguyên qua các lần gửi lại để server trả đúng việc cũ.
 *
 * Đồng bộ trực tiếp: trong lúc tab đang gắn, nghe gói nhóm (`javis:team-event`), mục tiêu đổi
 * (`javis:resonance-agents-changed`), tin việc nền về (`javis:sessions-changed`) và việc vừa tạo, huỷ ở chính tab
 * (`javis:agent-jobs-changed`), tải lại sau 800ms gộp nhịp. Kanban chưa có gói WS riêng nên thêm một nhịp hỏi thưa lúc
 * trang đang hiện. `destroy` gỡ hết.
 *
 * Hàm vẽ là hàm THUẦN (test dưới node); `mount` gắn sự kiện và gọi API.
 */
(function () {
  "use strict";

  var STR = {};
  function tw(khoa, bien) {
    var s = (typeof window !== "undefined" && window.t) ? window.t(khoa, bien) : (STR[khoa] || khoa);
    if (bien) {
      s = String(s).replace(/\{(\w+)\}/g, function (m, ten) {
        return Object.prototype.hasOwnProperty.call(bien, ten) ? String(bien[ten]) : m;
      });
    }
    return s;
  }
  function esc(t) {
    return String(t == null ? "" : t).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  var ic = function (n) { return (typeof window !== "undefined" && window.ic) ? window.ic(n) : ""; };

  var PAGE = 30;
  var RELOAD_MS = 800;
  var POLL_MS = 20000;
  var BUCKETS = ["needs_you", "running", "waiting", "done"];
  var SOURCES = ["team", "chat", "auto"];
  var BUCKET_KEY = { needs_you: "ajobs.b.needs_you", running: "ajobs.b.running", waiting: "ajobs.b.waiting",
    done: "ajobs.b.done" };
  // Bốn vai hiển thị. Mã cũ (assignee, owner, reviewer) vẫn đọc được để dữ liệu cũ không hiện mã thô.
  var ROLE_KEY = { coordinator: "ajobs.role.coordinator", worker: "ajobs.role.worker", helper: "ajobs.role.helper",
    verifier: "ajobs.role.verifier", verifier_legacy: "ajobs.role.verifier_legacy",
    assignee: "ajobs.role.worker", owner: "ajobs.role.worker", reviewer: "ajobs.role.verifier_legacy" };
  var SOURCE_KEY = { team: "ajobs.src.team", chat: "ajobs.src.chat", auto: "ajobs.src.auto" };
  var SOURCE_CHIP = { team: "ajobs.srcf.team", chat: "ajobs.srcf.chat", auto: "ajobs.srcf.auto" };
  var REASON_KEY = { review_removed: "ajobs.reason.review_removed", paused: "ajobs.reason.paused" };
  var SOURCE_ICON = { team: "users", chat: "message-circle", auto: "zap" };

  // Tên nhóm đã mở đầu bằng chữ "Nhóm" thì không ghép thêm chữ đó lần nữa ("Nhóm Nhóm kiểm thử"): `teamLabel` cho nhãn
  // "Nhóm {name}", `bareTeam` bỏ chữ đầu khi câu đã có sẵn "nhóm {team}".
  function teamHead() { return tw("ajobs.src.team", { name: "" }).trim().toLowerCase(); }
  function teamLabel(name) {
    name = String(name || "");
    var head = teamHead();
    return head && name.toLowerCase().indexOf(head + " ") === 0 ? name : tw("ajobs.src.team", { name: name });
  }
  function bareTeam(name) {
    name = String(name || "");
    var head = teamHead();
    return head && name.toLowerCase().indexOf(head + " ") === 0 ? name.slice(head.length + 1) : name;
  }

  function sourceText(j) {
    if (j.source === "team") {
      // Tên nhóm đã mở đầu bằng chữ "Nhóm" thì không ghép thêm ("Nhóm Nhóm kiểm thử").
      var name = String(j.source_label || ""), head = tw("ajobs.src.team", { name: "" }).trim().toLowerCase();
      return head && name.toLowerCase().indexOf(head) === 0 ? name : tw("ajobs.src.team", { name: name });
    }
    return tw(SOURCE_KEY[j.source] || "ajobs.src.chat");
  }

  // "5 phút trước": dùng chung khoá thời gian tương đối của chuông thông báo.
  function relTime(ts, nowSec) {
    if (!ts) return "";
    var now = nowSec != null ? nowSec : Date.now() / 1000;
    var s = Math.max(0, Math.floor(now - Number(ts)));
    if (s < 60) return tw("noti.ago_now");
    if (s < 3600) return tw("noti.ago_min", { count: Math.floor(s / 60) });
    if (s < 86400) return tw("noti.ago_hour", { count: Math.floor(s / 3600) });
    return tw("noti.ago_day", { count: Math.floor(s / 86400) });
  }

  // Bước kế tiếp do server tính (mã + tham số), đọc bằng lời.
  function nextText(j) {
    var n = j && j.next;
    if (!n || !n.code) return "";
    if (n.code === "queue") return n.n ? tw("ajobs.next.queue", { n: n.n, team: bareTeam(n.team) }) : "";
    if (n.code === "busy") return tw("ajobs.next.busy", { team: bareTeam(n.team) });
    if (n.code === "needs_you") return n.reason ? tw("ajobs.next.needs_you", { reason: n.reason }) : tw("ajobs.next.needs_you_plain");
    if (n.code === "board_off") return tw("ajobs.next.board_off");
    if (n.code === "agent_busy") return tw("ajobs.next.agent_busy");
    if (n.code === "queued") return tw("ajobs.next.queued");
    if (n.code === "resume") return tw("ajobs.next.resume");
    return "";
  }

  function jobHtml(j, ui) {
    ui = ui || {};
    var roles = (j.roles || []).filter(function (r, i, a) { return a.indexOf(r) === i; }).map(function (r) {
      return '<span class="aj-role aj-role-' + esc(r) + '">' + esc(tw(ROLE_KEY[r] || "ajobs.role.worker")) + "</span>";
    }).join("");
    var lines = [];
    if (j.progress && j.progress.total) lines.push(tw("ajobs.progress", { done: j.progress.done, total: j.progress.total }));
    if (j.queue_pos && !j.next) lines.push(tw("ajobs.queue_pos", { n: j.queue_pos }));
    if (j.board_off && !(j.next && j.next.code === "board_off")) lines.push(tw("ajobs.board_off"));
    if (j.cancelled) lines.push(tw("ajobs.cancelled"));
    if (j.failed) lines.push(tw("ajobs.failed"));
    var when = relTime(j.updated_at, ui.now);
    if (when) lines.push(tw("ajobs.updated", { when: when }));
    var nxt = nextText(j);
    // Mã lý do của mục tiêu Auto (đang dừng, đã gỡ người review cố định) đọc bằng lời thường; lý do khác hiện nguyên văn.
    // Bước kế "Chờ bạn: <lý do>" đã mang lý do thì không lặp lại dòng lý do.
    var why = REASON_KEY[j.reason_code] ? tw(REASON_KEY[j.reason_code])
      : (j.next && j.next.code === "needs_you" && j.next.reason ? "" : j.reason);
    var reason = why ? '<div class="aj-reason">' + esc(why) + "</div>" : "";
    var result = j.result ? '<div class="aj-result">' + esc(j.result) + "</div>" : "";
    var link = "";
    if (j.link) {
      var lt = j.link.title || (j.link.missing ? tw("ajobs.link_missing") : j.link.id);
      link = '<div class="aj-link">' + ic("circle-check") + '<span>' + esc(tw("ajobs.link_label", { title: lt })) + "</span>" +
        (j.link.open ? '<button type="button" class="ws-btn aj-link-open" data-aj-link="' + esc(j.id) + '">' + esc(tw("ajobs.open")) +
          "</button>" : "") + "</div>";
    }
    var openable = j.open && (j.open.team_id || j.open.session_id || j.open.task_id);
    var busy = ui.cancelling && ui.cancelling[j.id];
    var working = ui.busy && ui.busy[j.id];
    var acts = (openable ? '<button type="button" class="ws-btn aj-open" data-aj-open="' + esc(j.id) + '">' + ic("external-link") +
      esc(tw("ajobs.open")) + "</button>" : "") +
      (j.resume ? '<button type="button" class="ws-btn aj-resume" data-aj-resume="' + esc(j.id) + '"' + (working ? " disabled" : "") + ">" +
        esc(tw("ajobs.resume")) + "</button>" : "") +
      (j.priority ? '<button type="button" class="ws-btn aj-prio" data-aj-prio="' + esc(j.id) + '"' + (working ? " disabled" : "") + ">" +
        esc(tw(j.priority.on ? "ajobs.prio_on" : "ajobs.prio_off")) + "</button>" : "") +
      (ui.canVerify && j.kind !== "verify" ? '<button type="button" class="ws-btn aj-verify" data-aj-verify="' + esc(j.id) + '">' +
        esc(tw("ajobs.verify_this")) + "</button>" : "") +
      (j.cancel ? '<button type="button" class="ws-btn aj-cancel" data-aj-cancel="' + esc(j.id) + '"' + (busy ? " disabled" : "") + ">" +
        esc(tw(busy ? "ajobs.cancelling" : "ajobs.cancel")) + "</button>" : "");
    return '<li class="aj-job aj-' + esc(j.bucket) + '" data-aj-id="' + esc(j.id) + '">' +
      '<div class="aj-top"><span class="aj-title">' + esc(j.title) + "</span></div>" +
      '<div class="aj-meta"><span class="aj-src">' + ic(SOURCE_ICON[j.source] || "circle") + esc(sourceText(j)) + "</span>" + roles + "</div>" +
      (nxt ? '<div class="aj-next">' + esc(nxt) + "</div>" : "") +
      (lines.length ? '<div class="aj-line">' + esc(lines.join(" · ")) + "</div>" : "") + link + reason + result +
      (acts ? '<div class="aj-acts">' + acts + "</div>" : "") + "</li>";
  }

  function chipHtml(attr, key, label, n, on, extra) {
    return '<button type="button" class="aj-chip' + (on ? " is-on" : "") + (extra || "") + '" ' + attr + '="' + esc(key) +
      '" aria-pressed="' + (on ? "true" : "false") + '">' + esc(label) + (n != null ? ' <span class="aj-n">' + esc(n) + "</span>" : "") +
      "</button>";
  }

  function sourceFilterHtml(data, ui) {
    var sc = (data && data.source_counts) || {};
    var cur = ui.source || "";
    var total = SOURCES.reduce(function (a, s) { return a + (sc[s] || 0); }, 0);
    return '<div class="aj-filters aj-sources" role="group" aria-label="' + esc(tw("ajobs.srcf.label")) + '">' +
      chipHtml("data-aj-source", "", tw("ajobs.srcf.all"), total, !cur, " aj-chip-src") +
      SOURCES.map(function (s) { return chipHtml("data-aj-source", s, tw(SOURCE_CHIP[s]), sc[s] || 0, cur === s, " aj-chip-src"); }).join("") +
      "</div>";
  }

  function filterHtml(data, ui) {
    var counts = (data && data.counts) || {};
    var partial = data && data.counts_partial && data.counts_partial.done;
    var cur = ui.filter || "";
    var total = BUCKETS.reduce(function (a, b) { return a + (counts[b] || 0); }, 0);
    return '<div class="aj-filters" role="group" aria-label="' + esc(tw("ajobs.filter")) + '">' +
      chipHtml("data-aj-filter", "", tw("ajobs.all"), total + (partial ? "+" : ""), !cur) +
      ["running", "waiting", "needs_you", "done"].map(function (b) {
        return chipHtml("data-aj-filter", b, tw(BUCKET_KEY[b]), (counts[b] || 0) + (b === "done" && partial ? "+" : ""), cur === b,
          " aj-chip-" + b);
      }).join("") + "</div>";
  }

  // Tên nơi nhận kết quả cho ô chọn và cho bước xác nhận.
  function destLabel(ui, data, target) {
    var name = ui.verifyFor ? verifierName(ui) : (ui.name || "");
    if (!target || target === "chat") return tw("ajobs.dest_chat", { name: name });
    var id = target.slice(5);
    var tm = ((data && data.teams) || []).filter(function (x) { return x.team_id === id; })[0];
    return teamLabel(tm ? tm.name : id);
  }
  function verifierName(ui) {
    var a = (ui.agents || []).filter(function (x) { return x.slug === ui.verifier; })[0];
    return a ? (a.name || a.slug) : "";
  }
  function linkTitle(ui) {
    if (ui.verifyFor) return ui.verifyFor.title || ui.verifyFor.id;
    var it = (ui.targets || []).filter(function (x) { return x.id === ui.link; })[0];
    return it ? it.title : "";
  }

  function assignHtml(ui, data) {
    ui = ui || {};
    if (!ui.assignOpen) {
      return '<button type="button" class="ws-btn primary aj-assign-open">' + ic("plus") + esc(tw("ajobs.assign")) + "</button>";
    }
    if (ui.step === "confirm") return confirmHtml(ui, data);
    var verify = ui.kind === "verify";
    var kindRow = ui.verifyFor ? "" : '<div class="aj-kind" role="group" aria-label="' + esc(tw("ajobs.kind_label")) + '">' +
      chipHtml("data-aj-kind", "task", tw("ajobs.kind_task"), null, !verify) +
      chipHtml("data-aj-kind", "verify", tw("ajobs.kind_verify"), null, verify) + "</div>";
    var head = ui.verifyFor
      ? '<div class="aj-assign-label">' + esc(tw("ajobs.verify_for", { title: ui.verifyFor.title || ui.verifyFor.id })) + "</div>"
      : '<div class="aj-assign-label">' + esc(tw(verify ? "ajobs.verify_label" : "ajobs.assign_label", { name: ui.name || "" })) +
        "</div>";
    var verifier = "";
    if (ui.verifyFor) {
      var others = ui.agents || [];
      verifier = '<label class="aj-field-label" for="ajVerifier">' + esc(tw("ajobs.verifier_label")) + "</label>" +
        (others.length ? '<select id="ajVerifier" class="aj-sel aj-verifier">' + others.map(function (a) {
          return '<option value="' + esc(a.slug) + '"' + (a.slug === ui.verifier ? " selected" : "") + ">" + esc(a.name || a.slug) + "</option>";
        }).join("") + "</select>" : '<div class="aj-help">' + esc(tw("ajobs.verifier_none")) + "</div>");
    }
    var linkSel = "";
    if (verify && !ui.verifyFor) {
      var opts = ui.targets || [];
      linkSel = '<label class="aj-field-label" for="ajLink">' + esc(tw("ajobs.link_pick")) + "</label>" +
        (ui.targetsLoading ? '<div class="aj-help">' + esc(tw("ajobs.loading")) + "</div>"
          : '<select id="ajLink" class="aj-sel aj-link-sel"><option value="">' + esc(tw("ajobs.link_none")) + "</option>" +
            opts.map(function (x) {
              return '<option value="' + esc(x.id) + '"' + (x.id === ui.link ? " selected" : "") + ">" +
                esc(tw("ajobs.link_option", { title: x.title, name: x.name || x.slug })) + "</option>";
            }).join("") + "</select>");
    }
    var dest = "";
    if (!ui.verifyFor) {
      var teams = (data && data.teams) || [];
      dest = '<label class="aj-field-label" for="ajTarget">' + esc(tw("ajobs.dest_label")) + "</label>" +
        '<select id="ajTarget" class="aj-sel aj-target"><option value="chat"' + (!ui.target || ui.target === "chat" ? " selected" : "") + ">" +
        esc(destLabel(ui, data, "chat")) + "</option>" + teams.map(function (tm) {
          var v = "team:" + tm.team_id;
          return '<option value="' + esc(v) + '"' + (ui.target === v ? " selected" : "") + ">" + esc(teamLabel(tm.name)) +
            "</option>";
        }).join("") + "</select>";
    }
    return '<div class="aj-assign">' + head + kindRow + verifier +
      '<label class="aj-field-label" for="ajText">' + esc(tw("ajobs.req_label")) + "</label>" +
      '<textarea id="ajText" class="aj-text" rows="3" maxlength="4000" placeholder="' + esc(tw(verify ? "ajobs.verify_ph" : "ajobs.assign_ph")) + '">' +
      esc(ui.draft || "") + "</textarea>" +
      '<label class="aj-field-label" for="ajCrit">' + esc(tw(verify ? "ajobs.crit_label_req" : "ajobs.crit_label")) + "</label>" +
      '<textarea id="ajCrit" class="aj-text aj-crit" rows="2" maxlength="2000" placeholder="' + esc(tw("ajobs.crit_ph")) + '">' +
      esc(ui.criteria || "") + "</textarea>" +
      linkSel + dest +
      '<div class="aj-help">' + esc(tw("ajobs.assign_help")) + "</div>" +
      (ui.assignError ? '<div class="aj-err" role="alert">' + esc(ui.assignError) + "</div>" : "") +
      '<div class="aj-acts"><button type="button" class="ws-btn aj-assign-cancel">' + esc(tw("ajobs.cancel_form")) + "</button>" +
      '<button type="button" class="ws-btn primary aj-assign-next">' + esc(tw("ajobs.next_step")) + "</button></div></div>";
  }

  // Bước xác nhận: tóm tắt đúng cái sẽ tạo, Xác nhận hay Sửa.
  function confirmHtml(ui, data) {
    var verify = ui.kind === "verify";
    var who = ui.verifyFor ? verifierName(ui) : (ui.name || "");
    var rows = [tw(verify ? "ajobs.sum_verify_to" : "ajobs.sum_to", { name: who, text: ui.draft || "" }),
      ui.criteria ? tw("ajobs.sum_crit", { crit: ui.criteria }) : tw("ajobs.sum_crit_none")];
    var lt = verify ? linkTitle(ui) : "";
    if (lt) rows.push(tw("ajobs.sum_link", { title: lt }));
    rows.push(tw("ajobs.sum_dest", { dest: destLabel(ui, data, ui.verifyFor ? "chat" : ui.target) }));
    return '<div class="aj-assign aj-confirm" role="group" aria-label="' + esc(tw("ajobs.confirm_label")) + '">' +
      '<div class="aj-assign-label">' + esc(tw("ajobs.confirm_label")) + "</div>" +
      '<ul class="aj-sum">' + rows.map(function (r) { return "<li>" + esc(r) + "</li>"; }).join("") + "</ul>" +
      (ui.assignError ? '<div class="aj-err" role="alert">' + esc(ui.assignError) + "</div>" : "") +
      '<div class="aj-acts"><button type="button" class="ws-btn aj-assign-edit"' + (ui.sending ? " disabled" : "") + ">" +
      esc(tw("ajobs.edit")) + "</button>" +
      '<button type="button" class="ws-btn primary aj-assign-send"' + (ui.sending ? " disabled" : "") + ">" +
      esc(tw(ui.sending ? "ajobs.sending" : "ajobs.confirm")) + "</button></div></div>";
  }

  function html(data, ui) {
    ui = ui || {};
    var head = '<div class="aj-head">' + assignHtml(ui, data) + "</div>";
    if (ui.note) head += '<div class="aj-note" role="status">' + esc(ui.note) + "</div>";
    if (!data) return '<div class="aj">' + head + '<div class="aj-empty">' + esc(tw(ui.error ? "ajobs.load_err" : "ajobs.loading")) +
      (ui.error ? ' <button type="button" class="ws-btn aj-reload">' + esc(tw("ajobs.reload")) + "</button>" : "") + "</div></div>";
    var jobs = (data.jobs || []).filter(function (j) {
      return (!ui.filter || j.bucket === ui.filter) && (!ui.source || j.source === ui.source);
    });
    var errs = (data.errors || []).map(function (e) {
      return '<div class="aj-err">' + esc(tw("ajobs.source_err", { src: tw(SOURCE_KEY[e.source] || "ajobs.src.chat", { name: "" }) })) + "</div>";
    }).join("");
    var body;
    var anyAtAll = SOURCES.some(function (s) { return ((data.source_counts || {})[s] || 0) > 0; }) || (data.jobs || []).length;
    if (!jobs.length) {
      body = '<div class="aj-empty">' + esc(tw(anyAtAll ? "ajobs.empty_filter" : "ajobs.empty")) + "</div>";
    } else if (ui.filter) {
      body = '<ul class="aj-list">' + jobs.map(function (j) { return jobHtml(j, ui); }).join("") + "</ul>";
    } else {
      body = BUCKETS.map(function (b) {
        var part = jobs.filter(function (j) { return j.bucket === b; });
        if (!part.length) return "";
        var n = (data.counts && data.counts[b] != null) ? data.counts[b] : part.length;
        return '<section class="aj-sec"><h4 class="aj-sec-h">' + esc(tw(BUCKET_KEY[b])) + ' <span class="aj-n">' + esc(n) +
          '</span></h4><ul class="aj-list">' + part.map(function (j) { return jobHtml(j, ui); }).join("") + "</ul></section>";
      }).join("");
    }
    var more = data.next ? '<button type="button" class="ws-btn aj-more"' + (ui.loadingMore ? " disabled" : "") + ">" +
      esc(tw(ui.loadingMore ? "ajobs.loading" : "ajobs.more")) + "</button>" : "";
    var foot = '<div class="aj-foot">' + esc(tw(data.board === "off" ? "ajobs.foot_off" : "ajobs.foot", { n: data.max_workers || 2 })) +
      "</div>";
    return '<div class="aj">' + head + sourceFilterHtml(data, ui) + filterHtml(data, ui) + errs + body + more + foot + "</div>";
  }

  // Huy hiệu việc trên thẻ trợ lý (trang Cộng sự): Đang làm và Cần bạn, tách khỏi công tắc Auto.
  function badgeHtml(c) {
    if (!c || (!c.running && !c.needs_you)) return "";
    var label = tw("ajobs.badge_aria", { running: c.running || 0, needs: c.needs_you || 0 });
    return '<span class="ws-jb" role="img" aria-label="' + esc(label) + '" title="' + esc(label) + '">' +
      (c.running ? '<span class="ws-jb-run">' + ic("loader") + esc(c.running) + "</span>" : "") +
      (c.needs_you ? '<span class="ws-jb-need">' + ic("hand") + esc(c.needs_you) + "</span>" : "") + "</span>";
  }

  function newNonce() {
    try { if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID(); } catch (e) { /* cũ */ }
    return "n" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
  }

  function changed() {
    try { window.dispatchEvent(new CustomEvent("javis:agent-jobs-changed")); } catch (e) { /* node */ }
  }

  // ───────────── gắn vào trang ─────────────
  // opts: { slug, name, brain: () => string, agents: () => [{slug, name}] (trợ lý KHÁC, để chọn người kiểm chứng),
  //         openChat(sessionId), openTeam(teamId, taskId), openWork(taskId) }
  function mount(host, opts) {
    if (!host) return null;
    var st = { data: null, nonce: "",
      ui: { filter: "", source: "", assignOpen: false, step: "edit", kind: "task", draft: "", criteria: "", target: "chat",
        link: "", verifier: "", verifyFor: null, targets: null, name: opts.name, cancelling: {}, busy: {}, canVerify: true,
        agents: [] } };
    var alive = true, seq = 0, timer = null, poll = null;
    function q(s) { return encodeURIComponent(s); }
    function others() {
      try { return (opts.agents ? opts.agents() : []) || []; } catch (e) { return []; }
    }
    function draw() {
      if (!alive || !host.isConnected) return;
      st.ui.agents = others();
      st.ui.canVerify = st.ui.agents.length > 0;
      var act = typeof document !== "undefined" ? document.activeElement : null;
      var keepId = act && host.contains && host.contains(act) && act.id ? act.id : "";
      var keep = keepId && act.selectionStart != null ? { s: act.selectionStart, e: act.selectionEnd } : null;
      host.innerHTML = html(st.data, st.ui);
      if (keepId && host.querySelector) {
        var nt = host.querySelector("#" + keepId);
        if (nt) { nt.focus(); if (keep) { try { nt.setSelectionRange(keep.s, keep.e); } catch (e) {} } }
      }
    }
    function listUrl(cursor, limit) {
      return "/agents/" + q(opts.slug) + "/jobs?brain=" + q(opts.brain()) + "&source=" + q(st.ui.source || "all") +
        "&bucket=" + q(st.ui.filter || "") + "&limit=" + limit + (cursor ? "&cursor=" + q(cursor) : "");
    }
    // keep: tải lại tại chỗ (đồng bộ trực tiếp) giữ số việc đang xem, không thu về trang đầu.
    function load(keep) {
      var forSlug = opts.slug, my = ++seq;
      var shown = keep && st.data ? (st.data.jobs || []).length : 0;
      var limit = Math.min(100, Math.max(PAGE, shown));
      return fetch(listUrl("", limit)).then(function (r) { return r.json(); }).then(function (j) {
        if (!alive || forSlug !== opts.slug || my !== seq) return;
        if (!j || !j.ok) { st.ui.error = true; draw(); return; }
        st.data = j; st.ui.error = false; draw();
      }, function () { if (alive && my === seq) { st.ui.error = true; draw(); } });
    }
    function loadMore() {
      if (!st.data || !st.data.next || st.ui.loadingMore) return;
      var my = seq, forSlug = opts.slug;
      st.ui.loadingMore = true; draw();
      fetch(listUrl(st.data.next, PAGE)).then(function (r) { return r.json(); }).then(function (j) {
        st.ui.loadingMore = false;
        if (!alive || forSlug !== opts.slug || my !== seq) return;
        if (!j || !j.ok) { st.ui.note = tw("ajobs.load_err"); draw(); return; }
        var have = {};
        (st.data.jobs || []).forEach(function (x) { have[x.id] = true; });
        st.data.jobs = (st.data.jobs || []).concat((j.jobs || []).filter(function (x) { return !have[x.id]; }));
        st.data.next = j.next; st.data.counts = j.counts; st.data.source_counts = j.source_counts;
        draw();
      }, function () { st.ui.loadingMore = false; st.ui.note = tw("ajobs.net_err"); draw(); });
    }
    // Đang gõ trong form Giao việc (hay đang dùng bộ gõ IME): không vẽ lại cả khung, kẻo mất chữ hay nhảy con trỏ (review
    // 0.142.0, #3). Hẹn lại tới khi rời form; đóng form thì tải lại như thường.
    function typing() {
      var act = typeof document !== "undefined" ? document.activeElement : null;
      return st.ui.assignOpen || !!host._ajComposing || !!(act && host.contains && host.contains(act) &&
        (act.tagName === "TEXTAREA" || act.tagName === "INPUT" || act.tagName === "SELECT"));
    }
    function schedule() {
      if (!alive) return;
      if (timer) clearTimeout(timer);
      timer = setTimeout(function () {
        timer = null;
        if (!alive || !host.isConnected) return;
        if (typing()) { schedule(); return; }
        load(true);
      }, RELOAD_MS);
    }
    function loadTargets() {
      st.ui.targetsLoading = true; draw();
      fetch("/agents/" + q(opts.slug) + "/jobs/verify-targets?brain=" + q(opts.brain())).then(function (r) { return r.json(); })
        .then(function (j) { st.ui.targetsLoading = false; st.ui.targets = (j && j.ok && j.items) || []; draw(); },
          function () { st.ui.targetsLoading = false; st.ui.targets = []; draw(); });
    }
    function byId(id) { return ((st.data && st.data.jobs) || []).filter(function (x) { return x.id === id; })[0]; }
    function jsonPost(url, body) {
      return fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) })
        .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j2) { return { ok: r.ok && j2.ok !== false, j: j2, status: r.status }; }); });
    }
    function cancelJob(j) {
      var c = j.cancel || {};
      if (typeof confirm === "function" && !confirm(tw("ajobs.cancel_confirm", { title: j.title }))) return;
      st.ui.cancelling[j.id] = true; draw();
      var b = q(opts.brain()), req;
      if (c.kind === "team") req = jsonPost("/teams/" + q(c.team_id) + "/tasks/" + q(c.task_id) + "/cancel?brain=" + b);
      else if (c.kind === "kanban") {
        var fd = new FormData(); fd.append("id", c.task_id); fd.append("brain", opts.brain());
        req = fetch("/kanban/task/cancel", { method: "POST", body: fd })
          .then(function (r) { return r.json().catch(function () { return {}; }).then(function (j2) { return { ok: r.ok && j2.ok !== false, j: j2 }; }); });
      } else if (c.kind === "goal") {
        req = jsonPost("/goals/" + q(c.goal_id) + "/commands?brain=" + b, { command: "cancel", expected_revision: c.revision });
      } else return;
      req.then(function (res) {
        delete st.ui.cancelling[j.id];
        st.ui.note = res.ok ? tw("ajobs.cancelled_note", { title: j.title }) : tw("ajobs.cancel_err", { e: (res.j && res.j.error) || "" });
        changed(); load(true);
      }, function () { delete st.ui.cancelling[j.id]; st.ui.note = tw("ajobs.net_err"); draw(); });
    }
    function resumeJob(j) {
      var r0 = j.resume || {};
      st.ui.busy[j.id] = true; draw();
      jsonPost("/goals/" + q(r0.goal_id) + "/commands?brain=" + q(opts.brain()), { command: "resume", expected_revision: r0.revision })
        .then(function (res) {
          delete st.ui.busy[j.id];
          st.ui.note = res.ok ? tw("ajobs.resumed_note", { title: j.title }) : tw("ajobs.action_err", { e: (res.j && res.j.error) || "" });
          changed(); load(true);
        }, function () { delete st.ui.busy[j.id]; st.ui.note = tw("ajobs.net_err"); draw(); });
    }
    function prioJob(j) {
      var p = j.priority || {};
      st.ui.busy[j.id] = true; draw();
      jsonPost("/teams/" + q(p.team_id) + "/queue/" + q(p.task_id) + "/priority?brain=" + q(opts.brain()),
        { on: !!p.on, expected_queue_version: p.version })
        .then(function (res) {
          delete st.ui.busy[j.id];
          st.ui.note = res.ok ? "" : (res.j && res.j.code === "queue_changed" ? tw("ajobs.queue_changed")
            : tw("ajobs.action_err", { e: (res.j && res.j.error) || "" }));
          load(true);
        }, function () { delete st.ui.busy[j.id]; st.ui.note = tw("ajobs.net_err"); draw(); });
    }
    function resetForm() {
      st.nonce = "";
      st.ui.assignOpen = false; st.ui.step = "edit"; st.ui.kind = "task"; st.ui.draft = ""; st.ui.criteria = "";
      st.ui.target = "chat"; st.ui.link = ""; st.ui.verifyFor = null; st.ui.verifier = ""; st.ui.assignError = "";
    }
    function openForm(verifyJob) {
      resetForm();
      st.ui.assignOpen = true; st.ui.note = "";
      if (verifyJob) {
        st.ui.kind = "verify"; st.ui.verifyFor = { id: verifyJob.id, title: verifyJob.title };
        st.ui.link = verifyJob.id;
        var o = others(); st.ui.verifier = o.length ? o[0].slug : "";
      }
      draw();
      var ta = host.querySelector && host.querySelector(".aj-text"); if (ta && ta.focus) ta.focus();
    }
    function validate() {
      if (!String(st.ui.draft || "").trim()) return tw("ajobs.need_text");
      if (st.ui.kind === "verify" && !String(st.ui.criteria || "").trim()) return tw("ajobs.need_crit");
      if (st.ui.verifyFor && !st.ui.verifier) return tw("ajobs.need_verifier");
      return "";
    }
    function send() {
      var bad = validate();
      if (bad) { st.ui.step = "edit"; st.ui.assignError = bad; draw(); return; }
      if (!st.nonce) st.nonce = newNonce();   // gửi lại sau rớt mạng: cùng mã, server trả đúng việc cũ
      st.ui.sending = true; st.ui.assignError = ""; draw();
      var slug = st.ui.verifyFor ? st.ui.verifier : opts.slug;
      var body = { text: String(st.ui.draft).trim(), criteria: String(st.ui.criteria || "").trim(), nonce: st.nonce,
        kind: st.ui.kind, target: st.ui.verifyFor ? "chat" : (st.ui.target || "chat") };
      if (st.ui.kind === "verify" && st.ui.link) body.link = st.ui.link;
      var forOther = !!st.ui.verifyFor, who = forOther ? verifierName(st.ui) : opts.name;
      jsonPost("/agents/" + q(slug) + "/jobs?brain=" + q(opts.brain()), body).then(function (res) {
        st.ui.sending = false;
        var j = res.j || {};
        if (!res.ok) { st.ui.assignError = j.error || tw("ajobs.net_err"); draw(); return; }
        var team = String(body.target).indexOf("team:") === 0;
        resetForm();
        st.ui.note = team ? tw("ajobs.assigned_team") : forOther ? tw("ajobs.assigned_other", { name: who })
          : tw(j.board === "off" ? "ajobs.assigned_off" : "ajobs.assigned");
        changed(); load(true);
      }, function () { st.ui.sending = false; st.ui.assignError = tw("ajobs.net_err"); draw(); });
    }
    function openTarget(open) {
      if (!open) return;
      if (open.kind === "team" && opts.openTeam) opts.openTeam(open.team_id, open.task_id);
      else if (open.kind === "chat" && open.session_id && opts.openChat) opts.openChat(open.session_id);
      else if (opts.openWork) opts.openWork(open.task_id);
    }
    function onInput(e) {
      var t = e.target, cl = t && t.classList;
      if (!cl) return;
      if (cl.contains("aj-crit")) { st.ui.criteria = t.value; st.nonce = ""; return; }
      if (cl.contains("aj-text")) { st.ui.draft = t.value; st.nonce = ""; return; }
      if (cl.contains("aj-target")) { st.ui.target = t.value; st.nonce = ""; return; }
      if (cl.contains("aj-link-sel")) { st.ui.link = t.value; st.nonce = ""; return; }
      if (cl.contains("aj-verifier")) { st.ui.verifier = t.value; st.nonce = ""; return; }
    }
    function onClick(e) {
      var t = e.target.closest ? e.target.closest("button") : null;
      if (!t || !host.contains(t)) return;
      var d = t.dataset || {};
      if (d.ajFilter !== undefined) { st.ui.filter = d.ajFilter; draw(); load(false); return; }
      if (d.ajSource !== undefined) { st.ui.source = d.ajSource; draw(); load(false); return; }
      if (d.ajKind !== undefined) {
        st.ui.kind = d.ajKind === "verify" ? "verify" : "task"; st.nonce = ""; st.ui.assignError = "";
        if (st.ui.kind === "verify" && st.ui.targets == null && !st.ui.targetsLoading) loadTargets(); else draw();
        return;
      }
      if (t.classList.contains("aj-assign-open")) { openForm(null); return; }
      if (t.classList.contains("aj-assign-cancel")) { resetForm(); draw(); return; }
      if (t.classList.contains("aj-assign-next")) {
        var bad = validate();
        st.ui.assignError = bad; if (!bad) st.ui.step = "confirm";
        draw(); return;
      }
      if (t.classList.contains("aj-assign-edit")) { st.ui.step = "edit"; draw(); return; }
      if (t.classList.contains("aj-assign-send")) { send(); return; }
      if (t.classList.contains("aj-reload")) { st.ui.error = false; draw(); load(false); return; }
      if (t.classList.contains("aj-more")) { loadMore(); return; }
      if (d.ajCancel) { var jc = byId(d.ajCancel); if (jc) cancelJob(jc); return; }
      if (d.ajResume) { var jr = byId(d.ajResume); if (jr) resumeJob(jr); return; }
      if (d.ajPrio) { var jp = byId(d.ajPrio); if (jp) prioJob(jp); return; }
      if (d.ajVerify) { var jv = byId(d.ajVerify); if (jv) openForm(jv); return; }
      if (d.ajLink) { var jl = byId(d.ajLink); if (jl && jl.link) openTarget(jl.link.open); return; }
      if (d.ajOpen) { var j = byId(d.ajOpen); if (j) openTarget(j.open); }
    }
    // Khung `host` sống qua nhiều lần gắn (đổi trợ lý, đổi tab). Trình nghe gắn MỘT lần cho khung và chuyển cho lần gắn
    // đang sống; gắn chồng là một lần bấm Giao gửi nhiều việc, một lần Huỷ hỏi nhiều lần (review 0.142.0, #1).
    host._ajActive = { input: onInput, click: onClick };
    if (!host._ajWired) {
      host._ajWired = true;
      host.addEventListener("input", function (e) { if (host._ajActive) host._ajActive.input(e); });
      host.addEventListener("change", function (e) { if (host._ajActive) host._ajActive.input(e); });
      host.addEventListener("click", function (e) { if (host._ajActive) host._ajActive.click(e); });
      host.addEventListener("compositionstart", function () { host._ajComposing = true; });
      host.addEventListener("compositionend", function () { host._ajComposing = false; });
    }
    var mine = host._ajActive;
    // Đồng bộ trực tiếp: các sự kiện của app gộp nhịp rồi tải lại tại chỗ. Gỡ ở destroy.
    var EVENTS = ["javis:team-event", "javis:resonance-agents-changed", "javis:sessions-changed", "javis:agent-jobs-changed"];
    var hasWin = typeof window !== "undefined" && window.addEventListener;
    if (hasWin) EVENTS.forEach(function (ev) { window.addEventListener(ev, schedule); });
    if (typeof setInterval === "function") {
      poll = setInterval(function () {
        if (typeof document !== "undefined" && document.hidden) return;
        schedule();
      }, POLL_MS);
      if (poll && poll.unref) poll.unref();   // node (test): nhịp hỏi không giữ tiến trình sống
    }
    draw();
    load(false);
    return { reload: function () { return load(true); }, state: function () { return st; }, schedule: schedule,
      destroy: function () {
        alive = false;
        if (host._ajActive === mine) host._ajActive = null;
        if (timer) { clearTimeout(timer); timer = null; }
        if (poll) { clearInterval(poll); poll = null; }
        if (hasWin && window.removeEventListener) EVENTS.forEach(function (ev) { window.removeEventListener(ev, schedule); });
      } };
  }

  // Huy hiệu cho cả brain: GET /agents/jobs/counts -> { slug: {running, needs_you} }. Lỗi thì null (giữ bản cũ).
  function loadCounts(brain) {
    return fetch("/agents/jobs/counts?brain=" + encodeURIComponent(brain)).then(function (r) { return r.json(); })
      .then(function (j) { return j && j.ok ? (j.counts || {}) : null; }, function () { return null; });
  }

  var api = { html: html, jobHtml: jobHtml, filterHtml: filterHtml, sourceFilterHtml: sourceFilterHtml, assignHtml: assignHtml,
    confirmHtml: confirmHtml, badgeHtml: badgeHtml, nextText: nextText, relTime: relTime, mount: mount, loadCounts: loadCounts,
    RELOAD_MS: RELOAD_MS, setStrings: function (o) { STR = o || {}; } };
  if (typeof window !== "undefined") window.JavisAgentJobs = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})();
