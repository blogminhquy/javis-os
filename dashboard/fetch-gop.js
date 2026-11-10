/* fetch-gop.js - gộp các lượt ĐỌC trùng nhau trong một khoảnh khắc (0.416.0).

   Đo lúc mở app ngày 30/10/2026: /settings bị hỏi 9 lần, /agents, /skills, /workflows mỗi cái 2 lần, /connect/health
   2 lần, vì mỗi phần của dashboard (app.js, console.js, pet.js, branding.js, model-picker.js...) tự hỏi lấy cái nó
   cần. Qua Cloudflare mỗi lượt là một chuyến đi về, và chúng tranh chỗ với chính các file đang tải.

   Sửa từng chỗ gọi thì sót, và chỗ mới viết mai lại sót tiếp. Nên gộp ở MỘT điểm: bọc window.fetch. Cùng một GET tới
   cùng một địa chỉ trong DANH SÁCH dưới đây, gọi trong vòng 1,5 giây, thì dùng chung một câu trả lời (mỗi bên nhận một
   bản sao riêng, đọc thoải mái). Bất kỳ lượt GHI nào (POST, PUT, PATCH, DELETE) đều xoá sạch phần đã nhớ, nên đọc ngay
   sau khi lưu luôn ra dữ liệu mới. Chỉ gộp các địa chỉ trong danh sách: đọc thì rẻ để trùng, còn đường lạ (stream,
   tải file) thì không bao giờ động tới.

   0.417.0, THỬ LẠI. Ngày 30/10/2026 một khách bấm cập nhật, trang mở lại giữa lúc máy chủ (hay đường hầm Cloudflare trước
   nó) còn khởi động; mọi lượt hỏi nhận về trang lỗi 502 và giao diện vỡ luôn ("The string did not match the expected
   pattern" là câu Safari báo khi đọc trang lỗi HTML như JSON). Lớp này giờ còn làm thêm một việc cho cả dashboard:
   - lượt ĐỌC (GET) cùng máy chủ gặp lỗi đường truyền hay mã 502, 503, 504, 520-530 (mã của Cloudflare khi không tới được
     máy chủ) thì tự thử lại sau 0,5, 1, 2, 3, 4 giây (tổng khoảng 10 giây) trước khi trả lỗi cho chỗ gọi;
   - lượt GHI không bao giờ tự gửi lại: gửi trùng một lệnh là làm hai lần;
   - 500 là lỗi thật của code, không thử lại; lượt tự lo việc chờ (`cache: no-store`, có `signal`) cũng không đụng;
   - đang thử lại thì hiện một dải nhỏ "Đang kết nối lại máy chủ" ở đầu trang, có câu trả lời tốt là tự ẩn.

   gopDuoc, khoaGop, thuLaiDuoc, maTam là hàm thuần để node test chạy được. */
(function () {
  "use strict";

  var GIU_MS = 1500;
  // Đường đọc an toàn để dùng chung: trả JSON nhỏ, không có tác dụng phụ.
  // 2026-11-05: + `sessions/<id>/meta`, asked twice on every chat switch (model bar and project chip).
  // 2026-11-10: + `chat/route`, asked twice at start by the model bar (a plain read of where a new chat would run).
  var DUONG = /^\/(settings|config|brains|agents|skills|workflows|connect\/health|auth\/status|voice\/ear|voice\/call|plan-limits|chat\/route|sessions\/[^/?]+\/meta)(\?|$)/;

  function laGet(init) {
    var m = init && init.method ? String(init.method).toUpperCase() : "GET";
    return m === "GET" || m === "HEAD" ? m : "";
  }

  // Khoá gộp cho một lời gọi, hoặc "" khi không được gộp. `input` là chuỗi URL (Request object thì để nguyên).
  function khoaGop(input, init, goc) {
    if (typeof input !== "string") return "";
    var m = laGet(init);
    if (m !== "GET" || (init && init.body)) return "";
    // Có hẹn huỷ riêng (AbortController) thì không gộp: một bên huỷ là bên kia cũng mất. Người gọi ghi rõ muốn bản mới
    // nhất (no-store, reload) thì cũng không.
    if (init && (init.signal || init.cache === "no-store" || init.cache === "reload")) return "";
    var u;
    try { u = new URL(input, goc || "http://x"); } catch (e) { return ""; }
    if (goc && u.origin !== new URL(goc).origin) return "";
    var duong = u.pathname + u.search;
    return DUONG.test(duong) ? duong : "";
  }

  function gopDuoc(input, init, goc) { return khoaGop(input, init, goc) !== ""; }

  // ── Stale-while-revalidate for the console pages (2026-11-08) ──
  // Owner, 2026-11-08: pages "load" for seconds. Measured over a 250 ms tunnel: 0.3-1.4 s per page, spent waiting for
  // the server, every visit. The reads below feed the console pages (Skills, Connections, Channels, Settings, Models,
  // Self-learning, Usage, Webhooks...). While a page is first drawn (EARLY_MS after its visit began) each of them is
  // answered at once from the copy the last visit left (up to SWR_MAX_AGE_MS old) while the server is asked again;
  // console.js draws the page again when the answer differs. Later reads on the same visit (polling, a refresh button)
  // go to the server as before, so nothing stays one step behind. Any write clears every copy (except the bookkeeping
  // posts in NO_CHANGE_POSTS), and so does the end of every chat turn (app.js): Javis may have just changed a skill, a
  // connection or a setting.
  var SWR_MAX_AGE_MS = 10 * 60 * 1000;
  var SWR = new RegExp("^/(settings|agents|skills|workflows|brains|plugins|tools/optional|packs|logins|share/list|"
    + "webhooks|webhooks/health|connect/(catalog|health)|github/status|messenger/setup|threads/setup|"
    + "(telegram|whatsapp|zalo-bot|discord|slack|lark)/status|claude/status|autostart|domain/status|"
    + "remote-access/status|auth/tokens|learn/(config|metrics|review|log)|auto-learning|backup/status|"
    + "usage/(insights|theo-gio|tong-quan)|runtime/muc|cache-keepwarm)(\\?|$)");
  // Posts that change nothing a page shows: a chat marked read on every switch, error and diagnostics reports.
  var NO_CHANGE_POSTS = /^\/(sessions\/[^/?]+\/read|client-errors|diag\/|star-nudge\/check|batch)(\?|$)/;

  // Key of a read that may be answered from a kept copy, or "". Like khoaGop, other list; a refresh asked explicitly
  // (`refresh=1`, no-store, reload) always goes to the server. A read with its own timeout (AbortController) is
  // allowed: a copy answers at once, and without one it still gets its own request with its own signal.
  function swrKey(input, init, goc) {
    if (typeof input !== "string" || laGet(init) !== "GET" || (init && init.body)) return "";
    if (init && (init.cache === "no-store" || init.cache === "reload")) return "";
    var u;
    try { u = new URL(input, goc || "http://x"); } catch (e) { return ""; }
    if (goc && u.origin !== new URL(goc).origin) return "";
    if (/(^|[?&])refresh=(1|true)(&|$)/.test(u.search)) return "";
    var path = u.pathname + u.search;
    return SWR.test(path) ? path : "";
  }

  // Does this call leave every kept copy valid? Only reads and the bookkeeping posts above do.
  function keepsCopies(input, init, goc) {
    if (laGet(init) && !(init && init.body)) return true;
    var path = "";
    try { var u = new URL(typeof input === "string" ? input : input.url, goc || "http://x"); path = u.pathname; } catch (e) {}
    return NO_CHANGE_POSTS.test(path);
  }

  // ── Batched reads (2026-11-08, performance stage 2) ──
  // Each moment of the app (its start, a console page, a chat switch) makes the same reads every time, but in 3 to 5
  // waves: a module asks only once the answer before it drew its part. Over a 250 ms tunnel the waves, not the server,
  // were the cost. So every moment is recorded once (which reads it made in its first REC_MS) and the next time it
  // happens all of them leave together in ONE request to POST /batch (server/read_batch.py), which streams each answer
  // back as soon as it is ready. The modules' own fetches then find their answer waiting. Reads the server leaves out,
  // or a batch that fails, simply go to the server as before. Only plain reads the server also allows (keep this list
  // in step with ALLOWED_PATHS in server/read_batch.py; tests/python/test_read_batch.py compares them).
  var BATCH_RE = new RegExp("^/(settings|config|brains|agents|agents/get|agents/unread|agents/jobs/counts|agents/[^/?]+/pulse|"
    + "skills|workflows|plugins|tools/optional|packs|logins|share/list|webhooks|webhooks/health|connect/catalog|"
    + "connect/health|github/status|github/icons|github/session/[^/?]+|coding/session/[^/?]+|messenger/setup|"
    + "threads/setup|(telegram|whatsapp|zalo-bot|discord|slack|lark)/status|claude/status|autostart|domain/status|"
    + "remote-access/status|auth/status|auth/tokens|ui/order|pet/menu|voice/ear|voice/call|vault/check|files/list|"
    + "files/md-hong|graph|projects|sessions|sessions/[0-9a-z]{8,64}|sessions/[0-9a-z]{8,64}/meta|background|chat/route|"
    + "inbox|notifications|notifications/read|resonance/agents|resonance/goals|teams|learn/config|learn/metrics|"
    + "learn/review|learn/log|auto-learning|backup/status|incidents|kanban|loops/log|my-tasks|my-tasks/calendar|"
    + "reminders|schedules/this-machine|tasks/bots|viec/all|watch|channels/accounts|conversations|usage/insights|"
    + "usage/summary|usage/theo-gio|usage/tong-quan|runtime/muc|cache-keepwarm|plan-limits)(\\?[^#]*)?$");
  var BATCH_MAX = 40;

  function hasHeaders(h) {
    if (!h) return false;
    if (typeof h.forEach === "function" && !Array.isArray(h)) { var n = 0; h.forEach(function () { n++; }); return n > 0; }
    return Object.keys(h).length > 0;
  }
  // Path of a read that may travel in a batch, or "". A read with headers of its own is never batched: the batch
  // carries only the caller's cookie and language.
  function batchPath(input, init, goc) {
    if (typeof input !== "string" || laGet(init) !== "GET" || (init && init.body)) return "";
    if (init && (init.cache === "no-store" || init.cache === "reload")) return "";
    if (init && hasHeaders(init.headers)) return "";
    var u;
    try { u = new URL(input, goc || "http://x"); } catch (e) { return ""; }
    if (goc && u.origin !== new URL(goc).origin) return "";
    if (/(^|[?&])(refresh|nocache)=(1|true)(&|$)/i.test(u.search)) return "";
    var path = u.pathname + u.search;
    return path.length <= 600 && BATCH_RE.test(path) ? path : "";
  }
  // A recorded path made reusable: the moment's own values (the chat id of a switch) become {name}.
  function toTemplate(path, vars) {
    var out = path;
    Object.keys(vars || {}).forEach(function (k) {
      var v = String(vars[k] || "");
      if (v.length >= 6) out = out.split(v).join("{" + k + "}");
    });
    return out;
  }
  // And back, for this moment's values. "" when the template needs a value this moment does not have.
  function fromTemplate(tpl, vars) {
    var miss = false;
    var out = String(tpl).replace(/\{([a-z]+)\}/g, function (m, k) {
      var v = vars && vars[k];
      if (!v) { miss = true; return m; }
      return String(v);
    });
    return miss ? "" : out;
  }

  var CHO_THU_LAI = [500, 1000, 2000, 3000, 4000];

  // Mã trả về cho thấy máy chủ CHƯA tới được (đang khởi động, đường hầm chập chờn), không phải lỗi của chính yêu cầu.
  function maTam(status) { return status === 502 || status === 503 || status === 504 || (status >= 520 && status <= 530); }

  // Lời gọi này có được tự thử lại không: GET tới chính máy chủ Javis, không phải file tĩnh, không tự lo việc chờ.
  function thuLaiDuoc(input, init, goc) {
    if (typeof input !== "string") return false;
    if (laGet(init) !== "GET" || (init && init.body)) return false;
    if (init && (init.signal || init.cache === "no-store" || init.cache === "reload")) return false;
    var u;
    try { u = new URL(input, goc || "http://x"); } catch (e) { return false; }
    if (goc && u.origin !== new URL(goc).origin) return false;
    return u.pathname.indexOf("/static/") !== 0 && !/stream|events|sse/i.test(u.pathname);
  }

  // A session that expires while the tab is open (2026-11-10): chat keeps running over the WebSocket opened earlier,
  // but every HTTP call gets 401, so chat images turn into blank boxes and lists stop loading with no visible sign.
  // A 401 from this server outside /auth/* raises "javis:unauthorized"; app.js asks /auth/status and shows sign-in.
  function isSessionLost(status, input, origin) {
    if (status !== 401) return false;
    var u;
    try { u = new URL(typeof input === "string" ? input : (input && input.url) || "", origin || "http://x"); } catch (e) { return false; }
    if (origin && u.origin !== new URL(origin).origin) return false;
    return u.pathname.indexOf("/auth/") !== 0;
  }

  var api = { khoaGop: khoaGop, gopDuoc: gopDuoc, thuLaiDuoc: thuLaiDuoc, maTam: maTam, CHO_THU_LAI: CHO_THU_LAI, GIU_MS: GIU_MS,
    isSessionLost: isSessionLost,
    swrKey: swrKey, keepsCopies: keepsCopies, SWR_MAX_AGE_MS: SWR_MAX_AGE_MS,
    batchPath: batchPath, toTemplate: toTemplate, fromTemplate: fromTemplate, BATCH_MAX: BATCH_MAX };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window === "undefined" || typeof window.fetch !== "function") return;

  var gocThat = window.fetch.bind(window);
  var nho = {};   // khoá -> { luc, p: Promise<Response> }

  // ── Dải "Đang kết nối lại máy chủ" ──
  var dangThu = 0, dai = null;
  // True while at least one read waits to be tried again (the reconnect band is on screen). The Partners page holds its
  // "taking too long" error meanwhile: the band already says what is going on (#1213).
  api.retrying = function () { return dangThu > 0; };
  function veDai(hien) {
    try {
      if (hien) {
        if (!dai) {
          dai = document.createElement("div");
          dai.id = "javisKetNoiLai";
          dai.setAttribute("role", "status");
          dai.style.cssText = "position:fixed;left:50%;top:max(10px,env(safe-area-inset-top));transform:translateX(-50%);"
            + "z-index:99998;padding:8px 16px;border-radius:999px;font-size:15px;line-height:1.4;"
            + "background:var(--bg2,#1b1f2a);color:var(--text,#e8eaf0);border:1px solid var(--yellow,#e0a800);"
            + "box-shadow:0 6px 20px rgba(0,0,0,.3);pointer-events:none";
        }
        // Từ điển chưa về (máy chủ đang khởi động thì nó cũng đang thử lại) thì chỉ hiện dấu chấm, không hiện mã khoá.
        var chu = window.t ? window.t("net.reconnecting") : "";
        dai.textContent = chu && chu !== "net.reconnecting" ? chu : "…";
        if (!dai.isConnected && document.body) document.body.appendChild(dai);
      } else if (dai && dai.isConnected) {
        dai.remove();
      }
    } catch (e) { /* dải báo không bao giờ được làm hỏng lời gọi */ }
  }

  function reportSessionLost(input, r) {
    if (!r || !isSessionLost(r.status, input, location.origin)) return;
    try { window.dispatchEvent(new Event("javis:unauthorized")); } catch (e) { /* never break the call */ }
  }

  function ngu(ms) { return new Promise(function (xong) { setTimeout(xong, ms); }); }
  // 0.444.4: lệch ngẫu nhiên ±30%. Không có nó, mọi lượt đọc của mọi tab thử lại ĐÚNG cùng nhịp và dồn một lúc vào
  // máy chủ vừa chậm lại, làm nó càng chậm.
  function lech(ms) { return Math.round(ms * (0.7 + Math.random() * 0.6)); }

  // fetch thật, kèm thử lại cho lượt đọc khi máy chủ chưa tới được.
  function goc(input, init) {
    if (!thuLaiDuoc(input, init, location.origin)) {
      return gocThat(input, init).then(function (r) {
        if (dangThu === 0 && dai && r.ok) veDai(false);
        reportSessionLost(input, r);
        return r;
      });
    }
    var lan = 0, dangBao = false;
    function bao(on) {
      if (on && !dangBao) { dangBao = true; dangThu++; veDai(true); }
      if (!on && dangBao) { dangBao = false; dangThu--; if (dangThu <= 0) { dangThu = 0; veDai(false); } }
    }
    function thu() {
      return gocThat(input, init).then(function (r) {
        if (maTam(r.status) && lan < CHO_THU_LAI.length) {
          bao(true);
          return ngu(lech(CHO_THU_LAI[lan++])).then(thu);
        }
        bao(false);
        reportSessionLost(input, r);
        return r;
      }, function (loi) {
        if (lan < CHO_THU_LAI.length) {
          bao(true);
          return ngu(lech(CHO_THU_LAI[lan++])).then(thu);
        }
        bao(false);
        throw loi;
      });
    }
    return thu();
  }

  // ── Batched reads: answers on their way (see BATCH_RE above) ──
  var REC_MS = 2500;        // a moment's reads are the ones it makes this long after it began
  var PENDING_MS = 8000;    // a batched answer nobody asked for within this time is dropped
  var pending = {};         // path -> { at, p: Promise<{s, t, b} | null>, res }
  var recs = [];            // moments being recorded: { kind, vars, until, paths, timer }

  function manifestKey(kind) { return "javis.batch." + kind; }
  function readManifest(kind) {
    try { var a = JSON.parse(localStorage.getItem(manifestKey(kind)) || "[]"); return Array.isArray(a) ? a : []; }
    catch (e) { return []; }
  }
  function writeManifest(kind, list) {
    try { localStorage.setItem(manifestKey(kind), JSON.stringify(list.slice(0, BATCH_MAX))); } catch (e) {}
  }
  // A recording that ran its whole window replaces the manifest; one cut short (the moment came again) only adds.
  function endRec(r, whole) {
    try { clearTimeout(r.timer); } catch (e) {}
    recs = recs.filter(function (x) { return x !== r; });
    var tpls = [];
    r.paths.forEach(function (p) { var t = toTemplate(p, r.vars); if (tpls.indexOf(t) < 0) tpls.push(t); });
    if (!tpls.length) return;
    if (!whole) readManifest(r.kind).forEach(function (t) { if (tpls.indexOf(t) < 0) tpls.push(t); });
    writeManifest(r.kind, tpls);
  }
  function record(path) {
    var now = Date.now();
    recs.forEach(function (r) { if (now <= r.until && r.paths.indexOf(path) < 0) r.paths.push(path); });
  }

  // Server-sent events of POST /batch, handed one by one to `each` as they arrive.
  function readEvents(r, each) {
    if (!r.body || !r.body.getReader || typeof TextDecoder === "undefined") {
      return r.text().then(function (t) { splitEvents(t, each); });
    }
    var reader = r.body.getReader(), dec = new TextDecoder(), buf = "";
    function step() {
      return reader.read().then(function (x) {
        if (x.done) { splitEvents(buf + "\n\n", each); return; }
        buf += dec.decode(x.value, { stream: true });
        var cut = buf.lastIndexOf("\n\n");
        if (cut >= 0) { splitEvents(buf.slice(0, cut + 2), each); buf = buf.slice(cut + 2); }
        return step();
      });
    }
    return step();
  }
  function splitEvents(text, each) {
    String(text).split("\n\n").forEach(function (ev) {
      var line = ev.split("\n").filter(function (l) { return l.indexOf("data: ") === 0; }).map(function (l) { return l.slice(6); }).join("\n");
      if (!line) return;
      try { each(JSON.parse(line)); } catch (e) {}
    });
  }

  function sendBatch(paths) {
    var now = Date.now();
    // 2026-11-08, the Partners chat box that stayed locked: answers go to THIS batch's own entries (`mine`), never
    // looked up in `pending` again. A write in between (POST /seen goes out on every partner click) replaces `pending`
    // with a fresh object; looking the entry up there found nothing, so a read that had already started waiting on it
    // (the chat's messages) waited forever, and the chat box unlocks only once those messages are read.
    var mine = {};
    paths.forEach(function (p) {
      var d = { at: now, res: null };
      d.p = new Promise(function (ok) { d.res = ok; });
      pending[p] = d;
      mine[p] = d;
    });
    var answer = function (p, x) { var d = mine[p]; if (d && d.res) { d.res(x); d.res = null; } };
    gocThat("/batch", { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ paths: paths }) })
      .then(function (r) { if (!r.ok) throw new Error("batch " + r.status); return readEvents(r, function (x) { if (x && x.p) answer(x.p, x); }); })
      .catch(function () { batchOff = true; })
      .then(function () { paths.forEach(function (p) { answer(p, null); }); });
  }

  // 2026-11-08 (customer report: after the update the Partners page chat box stayed locked, Ctrl+Shift+R did not help):
  // the cause is fixed in sendBatch above, and this is the net under it. A read used to wait for its batched answer with
  // no limit, so anything that kept the answer away (a read stuck on the server, a proxy holding the stream back, a bug
  // like that one) kept the page waiting for good. A batched answer not there ANSWER_WAIT_MS after the page asked is
  // given up: the read goes to the server on its own, and this tab stops batching (batchOff) so the next moments do not
  // wait again. Batching only ever saves a round trip; it must not cost one.
  var ANSWER_WAIT_MS = 4000;
  var batchOff = false;
  api.ANSWER_WAIT_MS = ANSWER_WAIT_MS;
  api.batchOff = function () { return batchOff; };

  // The network, for a read: its batched answer when one is on its way (for at most ANSWER_WAIT_MS), the server otherwise.
  function net(input, init) {
    var bp = batchPath(input, init, location.origin);
    var d = bp && pending[bp];
    if (!d || Date.now() - d.at > PENDING_MS) return goc(input, init);
    var late = new Promise(function (ok) { setTimeout(function () { ok("late"); }, ANSWER_WAIT_MS); });
    return Promise.race([d.p, late]).then(function (x) {
      if (x === "late") { batchOff = true; if (pending[bp] === d) delete pending[bp]; return goc(input, init); }
      if (!x || !x.s || maTam(x.s)) return goc(input, init);
      return new Response(x.b, { status: x.s, headers: { "Content-Type": x.t || "application/json" } });
    });
  }

  // A moment begins: "boot", "page:<id>", "chat" ({sid}). Send what it read last time in one batch, record what it
  // reads this time.
  api.visit = function (kind, vars) {
    kind = String(kind || ""); vars = vars || {};
    if (!kind) return;
    recs.filter(function (r) { return r.kind === kind; }).forEach(function (r) { endRec(r, false); });
    var r = { kind: kind, vars: vars, until: Date.now() + REC_MS, paths: [] };
    try { r.timer = setTimeout(function () { endRec(r, true); }, REC_MS + 100); } catch (e) {}
    recs.push(r);
    var now = Date.now(), list = [];
    readManifest(kind).forEach(function (t) {
      var p = fromTemplate(t, vars);
      if (!p || list.indexOf(p) >= 0) return;
      var d = pending[p], c = copies[p];
      if (d && now - d.at <= PENDING_MS) return;
      if (c && now - c.at <= GIU_MS) return;
      list.push(p);
    });
    if (list.length >= 2 && !batchOff) sendBatch(list.slice(0, BATCH_MAX));
  };

  // ── Kept copies for the console pages (see SWR above) ──
  var copies = {};         // key -> { at, text, status, ct }
  var inflight = {};       // key -> Promise<Response>, one request in flight per key
  var page = "";           // the console page being drawn (console.js tells, see api.pageStart)
  var readThisVisit = {};  // keys read on this page visit (a changed answer for one of them redraws the page)
  var visitAt = 0;         // when the page visit began
  var EARLY_MS = 2500;     // reads this soon after the visit began belong to its first drawing and may use a copy

  function fromCopy(c) { return new Response(c.text, { status: c.status, headers: { "Content-Type": c.ct } }); }

  // Keep the answer's text as the copy of `key`; when it differs from the copy the page was drawn from, ask
  // console.js to draw the page again.
  function keep(key, r) {
    if (!r.ok) { delete copies[key]; return Promise.resolve(r); }
    return r.clone().text().then(function (text) {
      var c0 = copies[key];
      copies[key] = { at: Date.now(), text: text, status: r.status, ct: r.headers.get("Content-Type") || "application/json" };
      if (c0 && c0.text !== text && page && readThisVisit[key]) {
        try { window.dispatchEvent(new CustomEvent("javis:page-data", { detail: { page: page, key: key } })); } catch (e) {}
      }
      return r;
    }, function () { return r; });
  }

  // One shared request per key. Never carries a caller's signal: one caller giving up must not cancel it for the rest.
  function refetch(key, input, init) {
    if (inflight[key]) return inflight[key];
    var own = {};
    for (var k in (init || {})) if (k !== "signal") own[k] = init[k];
    var p = net(input, own).then(function (r) { return keep(key, r); });
    inflight[key] = p;
    var done = function () { if (inflight[key] === p) delete inflight[key]; };
    p.then(done, done);
    return p;
  }

  function fromCopyOrServer(key, input, init) {
    var c = copies[key], now = Date.now();
    var early = now - visitAt <= EARLY_MS;
    readThisVisit[key] = true;
    if (c && now - c.at <= GIU_MS) return Promise.resolve(fromCopy(c));
    if (early && c && now - c.at <= SWR_MAX_AGE_MS) {
      refetch(key, input, init).catch(function () {});
      return Promise.resolve(fromCopy(c));
    }
    // No usable copy: a caller with its own timeout keeps its own request; the others share one.
    if (init && init.signal) return net(input, init).then(function (r) { return keep(key, r); }).then(function (r) { return r.clone(); });
    return refetch(key, input, init).then(function (r) { return r.clone(); });
  }

  // console.js: a page starts drawing (a visit, or a redraw). Its first read of each key may use a kept copy again.
  api.pageStart = function (id) {
    page = String(id || ""); readThisVisit = {}; visitAt = Date.now();
    api.visit("page:" + page);
  };
  // Forget every kept copy (a chat turn ended: Javis may have changed what the pages show).
  api.forget = function () { copies = {}; nho = {}; };

  window.fetch = function (input, init) {
    // Một lượt ghi: những gì đã nhớ có thể đã cũ.
    if (!keepsCopies(input, init, location.origin)) { nho = {}; copies = {}; pending = {}; }
    if (recs.length) { var rp = batchPath(input, init, location.origin); if (rp) record(rp); }
    var copyKey = swrKey(input, init, location.origin);
    if (copyKey) return fromCopyOrServer(copyKey, input, init);
    var khoa = khoaGop(input, init, location.origin);
    if (!khoa) return net(input, init);
    var bay = Date.now();
    var e = nho[khoa];
    if (!e || bay - e.luc > GIU_MS) {
      e = { luc: bay, p: net(input, init) };
      nho[khoa] = e;
      // Hỏng thì quên ngay, lần sau gọi lại thật.
      e.p.then(function (r) { if (!r.ok && nho[khoa] === e) delete nho[khoa]; },
        function () { if (nho[khoa] === e) delete nho[khoa]; });
    }
    return e.p.then(function (r) { return r.clone(); });
  };
  window.JavisFetchGop = api;
  // The app's start is a moment too: its reads leave in one batch from the second start on.
  api.visit("boot");
})();
