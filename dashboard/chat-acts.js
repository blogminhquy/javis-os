/* chat-acts.js - hang nut duoi moi tin nhan trong khung chat Javis.

   Moi bong bong co mot hang nho ben duoi. Tin cua NGUOI DUNG: gio gui, tua lai,
   trich dan, sao chep. Tin cua JAVIS: gio gui, trich dan, sao chep, ghim vao muc luc, doc thanh tieng. Hang nay AN san (opacity 0), chi hien khi
   hover tren may tinh hoac khi cham vao tin tren dien thoai (.acts-on).

   File nay chi giu phan THUAN (khong dung tai lieu DOM that) de test bang node:
     node dashboard/test_chat_acts.js
   Phan gan su kien nam trong app.js vi no can sendMessage / chatInput.

   Ghi chu: KHONG dung ky tu em dash o bat ky dau. */
(function () {
  "use strict";

  var THU_KEY = ["cact.thu_cn", "cact.thu_2", "cact.thu_3", "cact.thu_4", "cact.thu_5",
    "cact.thu_6", "cact.thu_7"];

  // File này chạy hai chế độ: trong trình duyệt và dưới node (test require nó).
  // Dưới node không có window nên không có ic() - trả về chuỗi rỗng để phần logic
  // vẫn test được mà không phải kéo cả tầng icon vào. Trong trình duyệt thì
  // icons.js đã nạp trước (index.html bảo đảm thứ tự, có test canh) nên lấy
  // được hàm thật.
  var ic = (typeof window !== "undefined" && window.ic) ? window.ic : function () { return ""; };

  // Chu hien ra lay tu tu dien. Trong trinh duyet la window.t (i18n/index.js nap dau tien);
  // duoi node khong co window nen doc thang vi.json, nho vay ban node van ra chu that chu
  // khong phai ma khoa tran. Cung mot ly do voi ic() o tren.
  function tw(khoa) {
    if (typeof window !== "undefined" && window.t) return window.t(khoa);
    try { return require("./i18n/vi.json")[khoa] || khoa; } catch (e) { return khoa; }
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function pad2(n) { return (n < 10 ? "0" : "") + n; }

  // Tin cu luu tu truoc ban nay khong co moc thoi gian -> tra "" de AN phan gio,
  // KHONG duoc lay gio hien tai vi nhu vay la bia so lieu.
  function toDate(ts) {
    if (!ts) return null;
    var d = new Date(ts);
    return isNaN(d.getTime()) ? null : d;
  }

  function fmtTime(ts) {
    var d = toDate(ts);
    return d ? pad2(d.getHours()) + ":" + pad2(d.getMinutes()) : "";
  }

  function fmtTimeFull(ts) {
    var d = toDate(ts);
    if (!d) return "";
    return tw(THU_KEY[d.getDay()]) + ", " + pad2(d.getDate()) + "/" + pad2(d.getMonth() + 1) +
      "/" + d.getFullYear() + " " + fmtTime(ts);
  }

  // role: "user" | "javis".
  //
  // Tin cua JAVIS chi con gio + sao chep. Nut "Tra loi lai cau hoi phia tren" da BO
  // (chu repo yeu cau 01/09): no nam ngay canh nut sao chep, ma sao chep la thao tac
  // hay dung nhat duoi mot cau tra loi - bam truot mot ly la Javis chay lai ca luot,
  // ton tien va de mat cau tra loi dang doc. Ai muon hoi lai thi go lai cau hoi, hoac
  // bam "Tua lai" ngay tren bong bong cau hoi cua chinh minh - van con day.
  //
  // canResend=false khi khong co CHU de gui lai (tin chi co anh, khong kem loi nhan).
  // Khi do bo han nut tua lai thay vi de nut bam vao khong ra gi. Bo trong
  // tham so nay thi mac dinh van co nut, de cac cho goi cu khong doi hanh vi.
  function actsHtml(role, ts, canResend) {
    var t = fmtTime(ts);
    var time = t
      ? '<span class="msg-time" title="' + esc(fmtTimeFull(ts)) + '">' + esc(t) + "</span>"
      : "";
    // 0.349.0: "Gui lai" va "Sua lai" gop thanh MOT nut Tua lai (chu repo 27/10/2026): xoa cau nay cung moi thu
    // ben duoi, dua cau hoi ve o nhap de sua hoac gui lai, hoi thoai di tiep tu do. Gui lai = tua lai roi bam gui.
    var send = "";
    if (canResend !== false && role === "user") {
      send = '<button class="msg-act" type="button" data-act="rewind" title="' + esc(tw("cact.rewind")) + '">↺</button>';
    }
    // Trich dan (0.171.0): dat doan nay len tren o nhap de hoi tiep, khoi go lai. Co o ca tin
    // nguoi dung lan tin Javis. Bam truot cung vo hai: no chi dat chip, khong chay gi.
    // Tin nguoi dung chi co anh thi khong co chu de trich, bo nut nhu nut gui lai.
    var quote = (role === "user" && canResend === false) ? "" :
      '<button class="msg-act" type="button" data-act="quote" title="' + esc(tw("cact.quote")) + '">' + ic("quote") + '</button>';
    // 0.374.0 (chu repo 28/10/2026): duoi cau tra loi them nut GHIM vao muc luc cua cuoc chat (thanh moc /
    // nut "≡ n/m") va nut LOA doc thanh tieng cau do. Nut ghim chi hien khi bong bong da co ma tin (CSS
    // .msg-javis[data-mid]): cau dang stream chua luu thi chua ghim duoc.
    var them = role === "javis"
      ? '<button class="msg-act" type="button" data-act="pin" title="' + esc(tw("cact.pin")) + '">' + ic("pin") + '</button>' +
        '<button class="msg-act" type="button" data-act="speak" title="' + esc(tw("cact.speak")) + '">' + ic("volume-2") + '</button>'
      : "";
    return '<div class="msg-acts">' + time + send + quote +
      '<button class="msg-act" type="button" data-act="copy" title="' + esc(tw("cact.copy")) + '">⧉</button>' +
      them + "</div>";
  }

  function isUserMsg(el) {
    return !!(el && el.classList && el.classList.contains("msg-user"));
  }

  // Copy text to the clipboard, shared by the main chat, the Team chat and the code block Copy button. The clipboard
  // API needs a secure context; on plain HTTP (a LAN or a VPS without https) or with the permission blocked it falls back
  // to a hidden textarea and execCommand. Resolves true when the text was copied, false when every way failed; never
  // rejects. `doc`/`nav`/`win` are for tests only.
  function copy(text, env) {
    env = env || {};
    var doc = env.doc || (typeof document !== "undefined" ? document : null);
    var nav = env.nav || (typeof navigator !== "undefined" ? navigator : null);
    var win = env.win || (typeof window !== "undefined" ? window : {});
    var s = String(text == null ? "" : text);
    function fallback() {
      if (!doc || !doc.body) return false;
      var ok = false;
      var ta = doc.createElement("textarea");
      ta.value = s; ta.style.cssText = "position:fixed;opacity:0";
      doc.body.appendChild(ta); ta.select();
      try { ok = doc.execCommand("copy") !== false; } catch (e) { ok = false; }
      ta.remove();
      return ok;
    }
    try {
      if (nav && nav.clipboard && nav.clipboard.writeText && win.isSecureContext) {
        return Promise.resolve(nav.clipboard.writeText(s)).then(function () { return true; }, fallback);
      }
    } catch (e) { /* fall through to the textarea */ }
    return Promise.resolve().then(fallback);
  }

  // Enter in a chat composer, shared by the main chat and the Team chat.
  //  - A Vietnamese IME (or any IME) can fire keydown Enter before compositionend; sending and clearing the box then
  //    lets the browser commit the composed letters into the cleared box. Some browsers report isComposing unreliably,
  //    so the caller also tracks compositionstart/compositionend itself (trackComposition) and passes that flag.
  //  - A touch screen (the MAIN pointer is a finger) keeps Enter as a new line like every messaging app: an on-screen
  //    keyboard has no Shift+Enter, so sending on Enter would make a multi-line message impossible. Measured with
  //    pointer: coarse, not screen width, so a touch laptop with a mouse still sends on Enter.
  //  - Shift+Enter is a new line on a computer.
  // `win` is for tests only.
  function touchMain(win) {
    win = win || (typeof window !== "undefined" ? window : null);
    try { return !!(win && win.matchMedia && win.matchMedia("(pointer: coarse)").matches); } catch (e) { return false; }
  }
  function enterSends(e, composing, win) {
    if (!e || composing || e.isComposing || e.keyCode === 229) return false;
    if (e.key !== "Enter" || e.shiftKey) return false;
    return !touchMain(win);
  }
  // Watch compositionstart/compositionend on `root` (the input itself, or a container whose inputs get redrawn: the
  // events bubble). Returns a function that says whether an IME composition is running now.
  function trackComposition(root) {
    var on = false;
    if (root && root.addEventListener) {
      root.addEventListener("compositionstart", function () { on = true; });
      root.addEventListener("compositionend", function () { on = false; });
    }
    return function () { return on; };
  }

  // The text the user has selected INSIDE `el` (a chat message), trimmed; "" when nothing is selected there. Quoting a
  // message with part of it selected quotes just that part (main chat and Team chat). `win` is for tests only.
  function selectedIn(el, win) {
    win = win || (typeof window !== "undefined" ? window : null);
    try {
      var sel = win && win.getSelection && win.getSelection();
      if (el && sel && !sel.isCollapsed && sel.rangeCount && el.contains(sel.getRangeAt(0).commonAncestorContainer)) {
        return String(sel.toString() || "").trim();
      }
    } catch (e) { /* no selection API */ }
    return "";
  }

  // Long messages the user wrote collapse to ten lines with "Show more" (main chat and Team chat): more than CLAMP_LINES
  // lines or CLAMP_CHARS characters. The text sits in `.utext` (class `clamped` while collapsed) and the toggle is a
  // `button.clamp-more` in the same bubble; one delegated listener below handles every chat container.
  var CLAMP_LINES = 10, CLAMP_CHARS = 900;
  function isLongText(text) {
    var s = String(text == null ? "" : text);
    return !!s && (s.split("\n").length > CLAMP_LINES || s.length > CLAMP_CHARS);
  }
  function clampButtonHtml(open) {
    return '<button class="clamp-more" type="button">' + esc(tw(open ? "app.show_less" : "app.show_more")) + "</button>";
  }
  // Open or close the long message the button belongs to. Returns true when it is open after the click.
  function toggleClamp(btn) {
    var host = (btn.closest && btn.closest(".bubble, .tm-bubble")) || btn.parentNode;
    var u = host && host.querySelector(".utext");
    if (!u) return false;
    u.classList.toggle("clamped");
    var open = !u.classList.contains("clamped");
    btn.textContent = tw(open ? "app.show_less" : "app.show_more");
    return open;
  }
  if (typeof document !== "undefined" && document.addEventListener) {
    document.addEventListener("click", function (e) {
      var t = e.target;
      if (t && t.classList && t.classList.contains("clamp-more")) toggleClamp(t);
    });
  }

  var API = {
    copy: copy,
    isLongText: isLongText,
    clampButtonHtml: clampButtonHtml,
    toggleClamp: toggleClamp,
    selectedIn: selectedIn,
    enterSends: enterSends,
    touchMain: touchMain,
    trackComposition: trackComposition,
    fmtTime: fmtTime,
    fmtTimeFull: fmtTimeFull,
    actsHtml: actsHtml,
    isUserMsg: isUserMsg,
  };

  if (typeof window !== "undefined") window.JavisActs = API;
  if (typeof module !== "undefined" && module.exports) module.exports = API;
})();
