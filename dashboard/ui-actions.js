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
  var PAGES = ["home", "chat", "settings", "workflows", "agents", "skills", "chatbots", "files",
               "terminal", "selfimprove", "learn", "kanban", "models", "channels", "mcp", "plugins",
               "packs", "logs", "account", "usage", "pet"];
  // Nhóm trên thanh bên (accordion). Cùng danh sách với RAIL_GROUPS trong console.js và GROUPS
  // trong plugin javis-ui. Mở một NHÓM khác với mở một TRANG: người dùng hay muốn bung phần
  // đang gập lại để nhìn xem có gì, chứ chưa chọn trang nào.
  var GROUPS = ["bo_nao", "code", "nang_luc", "viec", "ket_noi", "he_thong"];
  var ACTIONS = ["open_page", "open_file", "open_task", "scroll", "open_group", "sidebar"];

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
      if (target !== "top" && target !== "bottom") return { ok: false, error: "scroll chỉ nhận top/bottom" };
    } else if (action === "open_group") {
      if (GROUPS.indexOf(target) < 0) return { ok: false, error: "không có nhóm: " + target };
    } else if (action === "sidebar") {
      if (target !== "open" && target !== "close") return { ok: false, error: "sidebar chỉ nhận open/close" };
    }
    return { ok: true, action: action, target: target };
  }

  if (typeof module !== "undefined" && module.exports) module.exports = { validate: validate, PAGES: PAGES, GROUPS: GROUPS };
  if (typeof document === "undefined") return;   // node: chỉ lấy hàm thuần

  function tw(k, v) { try { return window.t ? window.t(k, v) : k; } catch (e) { return k; } }

  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

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
      var area = document.getElementById("chatArea");
      if (area) area.scrollTop = v.target === "top" ? 0 : area.scrollHeight;
      window.scrollTo({ top: v.target === "top" ? 0 : document.body.scrollHeight, behavior: "smooth" });
      return { ok: true, detail: "" };
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
