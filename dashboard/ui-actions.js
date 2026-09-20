/* ui-actions.js - dashboard NHẬN lệnh từ tool javis_ui và trả kết quả (Voice V1, spec mục 6).

   Server bắn frame {"type":"ui_action","id","action","target","session_id"} qua /ws khi model
   gọi tool javis_ui. File này: kiểm lại target (không tin server tuyệt đối vì đây là bên thực
   hiện), chạy bằng đúng những hàm dashboard đã có (JavisNav.go, JavisOpenVaultPath,
   JavisKanbanShow), rồi gửi {"action":"ui_result","id","ok","detail"} về để tool trả lời model
   ngay trong lượt.

   Tab đang xem phiên KHÁC với session_id trong frame thì trả `skipped=true` (server bỏ qua,
   chờ tab đúng phiên). Không có session_id thì mọi tab đều làm.

   Phần kiểm (validate) tách thuần để test bằng node. Ghi chú: KHÔNG dùng ký tự em dash. */
(function () {
  "use strict";

  // Cùng danh sách với RAIL_ITEMS trong console.js và PAGES trong plugin javis-ui.
  var PAGES = ["home", "chat", "settings", "workspace", "skills", "chatbots", "conversations", "files",
               "terminal", "selfimprove", "learn", "kanban", "models", "channels", "mcp", "plugins",
               "packs", "logs", "account", "usage", "pet", "share"];
  // Nhóm trên thanh bên (accordion). Cùng danh sách với RAIL_GROUPS trong console.js và GROUPS
  // trong plugin javis-ui. Mở một NHÓM khác với mở một TRANG: người dùng hay muốn bung phần
  // đang gập lại để nhìn xem có gì, chứ chưa chọn trang nào.
  var GROUPS = ["bo_nao", "code", "nang_luc", "viec", "ket_noi", "he_thong"];
  var ACTIONS = ["open_page", "open_file", "open_task", "scroll", "open_group", "sidebar"];
  // Phạm vi cuộn. Cùng danh sách với SCROLL_TARGETS trong server/ui_targets.py. `top`/`bottom` để
  // TRANG NÀY tự chọn (xem khungCuonTrang): người nói "cuộn xuống" muốn cuộn thứ họ đang nhìn, mà chỉ
  // trình duyệt mới biết đang có trang nội dung nào mở và nó có cuộn được không.
  var SCROLLS = ["top", "bottom", "page_top", "page_bottom", "chat_top", "chat_bottom"];

  function validate(frame) {
    frame = frame || {};
    var action = String(frame.action || "");
    var target = String(frame.target || "").trim();
    if (ACTIONS.indexOf(action) < 0) return { ok: false, error: "action không hỗ trợ: " + action };
    if (action === "open_page") {
      if (PAGES.indexOf(target) < 0) return { ok: false, error: "trang không tồn tại: " + target };
    } else if (action === "open_file") {
      var p = target.replace(/\\/g, "/");
      if (!p) return { ok: false, error: "thiếu đường dẫn file" };
      if (p.charAt(0) === "/" || p.charAt(0) === "~" || /^[a-zA-Z]:/.test(p) || /^[a-z]+:\/\//i.test(p)
          || p.split("/").indexOf("..") >= 0) {
        return { ok: false, error: "đường dẫn phải tương đối trong brain" };
      }
      target = p.replace(/^\.\//, "");
    } else if (action === "open_task") {
      if (!target || !/^[\w.\-:]+$/.test(target)) return { ok: false, error: "mã việc không hợp lệ" };
    } else if (action === "scroll") {
      if (SCROLLS.indexOf(target) < 0) return { ok: false, error: "scroll chỉ nhận: " + SCROLLS.join(", ") };
    } else if (action === "open_group") {
      if (GROUPS.indexOf(target) < 0) return { ok: false, error: "không có nhóm: " + target };
    } else if (action === "sidebar") {
      if (target !== "open" && target !== "close") return { ok: false, error: "sidebar chỉ nhận open/close" };
    }
    return { ok: true, action: action, target: target };
  }

  if (typeof module !== "undefined" && module.exports) module.exports = { validate: validate, PAGES: PAGES, GROUPS: GROUPS, SCROLLS: SCROLLS };
  if (typeof document === "undefined") return;   // node: chỉ lấy hàm thuần

  function tw(k, v) { try { return window.t ? window.t(k, v) : k; } catch (e) { return k; } }

  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  function cuonDuoc(el) {
    if (!el || el.scrollHeight - el.clientHeight <= 4) return false;
    var oy = "";
    try { oy = window.getComputedStyle(el).overflowY; } catch (e) { oy = "auto"; }
    return oy === "auto" || oy === "scroll" || oy === "overlay";
  }

  /* Khung cuộn của TRANG NỘI DUNG đang mở, hoặc null khi đang ở cockpit / trang không có gì
     để cuộn. Đây là chỗ sửa BUG-001: trước đây "cuộn xuống" luôn nhắm #chatArea nên đứng ở
     trang Tự học hay Việc định kỳ thì danh sách đứng im.

     #cviewBody là khung cuộn mặc định của mọi trang. Vài trang dán sát mép (.cview-flush:
     Terminal, trình sửa file) tắt cuộn ở đó và tự cuộn bên trong, nên phải tìm tiếp con cháu
     nào cuộn được và lấy cái CAO NHẤT (khung chính, không phải một danh sách nhỏ trong góc). */
  function khungCuonTrang() {
    var cview = document.getElementById("cview");
    if (!cview || !cview.getClientRects().length) return null;    // cockpit: cview đang ẩn
    var body = document.getElementById("cviewBody");
    if (cuonDuoc(body)) return body;
    var goc = body || cview, tot = null;
    var con = goc.querySelectorAll("*");
    for (var i = 0; i < con.length; i++) {
      if (!cuonDuoc(con[i]) || !con[i].getClientRects().length) continue;
      if (!tot || con[i].clientHeight > tot.clientHeight) tot = con[i];
    }
    return tot;
  }

  async function execute(v) {
    if (v.action === "open_page") {
      if (window.JavisNav && typeof window.JavisNav.go === "function") { window.JavisNav.go(v.target); return { ok: true, detail: "" }; }
      return { ok: false, detail: "bộ điều hướng chưa sẵn sàng" };
    }
    if (v.action === "open_file") {
      if (typeof window.JavisOpenVaultPath === "function") { window.JavisOpenVaultPath(v.target); return { ok: true, detail: "" }; }
      if (typeof window.JavisEditFile === "function") { window.JavisEditFile(v.target); return { ok: true, detail: "" }; }
      return { ok: false, detail: "trình mở file chưa sẵn sàng" };
    }
    if (v.action === "open_task") {
      if (window.JavisNav && typeof window.JavisNav.go === "function") window.JavisNav.go("kanban");
      // renderKanban là async: đợi nó gắn JavisKanbanShow (tối đa ~3 giây).
      for (var i = 0; i < 30; i++) {
        if (typeof window.JavisKanbanShow === "function") {
          try { await window.JavisKanbanShow(v.target); } catch (e) {}
          return { ok: true, detail: "" };
        }
        await sleep(100);
      }
      return { ok: false, detail: "trang Việc không mở kịp" };
    }
    if (v.action === "open_group") {
      if (window.JavisNav && typeof window.JavisNav.openGroup === "function") {
        return window.JavisNav.openGroup(v.target)
          ? { ok: true, detail: "" } : { ok: false, detail: "không có nhóm đó trên thanh bên" };
      }
      return { ok: false, detail: "bộ điều hướng chưa sẵn sàng" };
    }
    if (v.action === "sidebar") {
      if (window.JavisNav && typeof window.JavisNav.setCollapsed === "function") {
        window.JavisNav.setCollapsed(v.target === "close");
        return { ok: true, detail: "" };
      }
      return { ok: false, detail: "bộ điều hướng chưa sẵn sàng" };
    }
    if (v.action === "scroll") {
      var len = v.target.indexOf("top") >= 0;
      var pham_vi = v.target.indexOf("page") === 0 ? "page" : (v.target.indexOf("chat") === 0 ? "chat" : "auto");
      var chat = document.getElementById("chatArea");
      var el = null, ten = "";
      if (pham_vi !== "chat") {
        el = khungCuonTrang();
        // Trang "Trò chuyện" bê thẳng #chatArea vào khung nội dung (chat-zoom.js), nên khung
        // cuộn của trang CHÍNH LÀ khung chat: gọi tên cho đúng thứ vừa cuộn.
        ten = el && el === chat ? tw("ui.scroll_chat") : tw("ui.scroll_page");
      }
      if (!el && pham_vi !== "page") {
        el = chat;
        ten = tw("ui.scroll_chat");
        if (el && !cuonDuoc(el)) { el = null; ten = ""; }
      }
      if (!el) {
        if (pham_vi === "page") return { ok: false, detail: tw("ui.scroll_no_page") };
        // Không khung nào cuộn được (màn hẹp, cả trang là một dải dọc): cuộn chính tài liệu.
        window.scrollTo({ top: len ? 0 : document.body.scrollHeight, behavior: "smooth" });
        return { ok: true, detail: tw("ui.scroll_window") };
      }
      try { el.scrollTo({ top: len ? 0 : el.scrollHeight, behavior: "smooth" }); }
      catch (e) { el.scrollTop = len ? 0 : el.scrollHeight; }
      return { ok: true, detail: ten };
    }
    return { ok: false, detail: "không hỗ trợ" };
  }

  function send(obj) {
    try { if (typeof window.JavisWsSend === "function") window.JavisWsSend(obj); } catch (e) {}
  }

  function currentSid() {
    try { return (window.JavisSessions && window.JavisSessions.current()) || ""; } catch (e) { return ""; }
  }

  async function handle(frame) {
    frame = frame || {};
    var id = String(frame.id || "");
    if (!id) return;
    var want = String(frame.session_id || "");
    if (want && want !== currentSid()) { send({ action: "ui_result", id: id, ok: false, skipped: true, detail: "" }); return; }
    var v = validate(frame);
    if (!v.ok) { send({ action: "ui_result", id: id, ok: false, detail: v.error }); return; }
    var r;
    try { r = await execute(v); } catch (e) { r = { ok: false, detail: String(e && e.message || e) }; }
    send({ action: "ui_result", id: id, ok: !!r.ok, detail: r.detail || "" });
    try { if (window.JavisUiActions && typeof window.JavisUiActions.onDone === "function") window.JavisUiActions.onDone(v, r); } catch (e) {}
  }

  window.JavisUiActions = { validate: validate, handle: handle, PAGES: PAGES, GROUPS: GROUPS, onDone: null };
})();
