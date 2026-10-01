/* call-bar.js - THANH GỌI ngay trên khung chat (0.65.18, docs/dev/2026-10-voice-call-spec.md mục 4).

   Bấm mic là gọi Javis; thanh này cho biết cuộc gọi đang ở đâu (đang nghe, Javis đang nói, đang
   làm việc, đang chờ gọi tên, đang nối lại), đếm giờ, và có hai nút: tắt mic (Javis vẫn nói được)
   và cúp máy. Lời hai bên vẫn chạy thành bong bóng chat thường nên bảng số, file, kết quả việc
   hiện đầy đủ, thanh chỉ là phần điều khiển.

   Thanh nằm trong CHAT_NODE_IDS (console.js) nên sang trang Trò chuyện là đi theo khung chat.
   Module không tự đọc trạng thái: app.js tính trạng thái thật (đạo diễn lượt nói, rào chú ý,
   phiên Live) rồi gọi setState, giống luật orb chỉ vẽ qua capNhatOrb().
   Ghi chú: KHÔNG dùng ký tự em dash. */
(function (root) {
  "use strict";

  var STATE_KEYS = {
    connecting: "call.connecting",
    listening: "call.listening",
    speaking: "call.speaking",
    working: "call.working_plain",
    waiting_wake: "call.waiting_wake",
    reconnecting: "call.reconnecting",
    muted: "call.muted",
  };

  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function clock(sec) {
    sec = Math.max(0, Math.floor(sec));
    var h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
    return (h ? h + ":" + pad(m) : pad(m)) + ":" + pad(s);
  }

  function create(opts) {
    opts = opts || {};
    var el = opts.el, doc = opts.document || root.document;
    var t = opts.t || function (k) { return k; };
    var now = opts.now || Date.now;
    var setIntervalFn = opts.setInterval || root.setInterval, clearIntervalFn = opts.clearInterval || root.clearInterval;
    var state = "connecting", detail = "", engine = "", muted = false, startedAt = 0, timer = null;

    function span(cls) { var s = doc.createElement("span"); s.className = cls; return s; }
    var dot = span("call-dot"), engineEl = span("call-engine"), stateEl = span("call-state"), clockEl = span("call-clock");
    var muteBtn = doc.createElement("button"), hangBtn = doc.createElement("button");
    muteBtn.type = hangBtn.type = "button";
    muteBtn.className = "call-btn call-mute";
    hangBtn.className = "call-btn call-hangup";
    muteBtn.onclick = function () { if (opts.onMute) opts.onMute(!muted); };
    hangBtn.onclick = function () { if (opts.onHangup) opts.onHangup(); };
    if (el) {
      el.innerHTML = "";
      [dot, engineEl, stateEl, clockEl, muteBtn, hangBtn].forEach(function (n) { el.appendChild(n); });
      el.setAttribute("role", "status");
    }

    function render() {
      if (!el) return;
      var shown = muted ? "muted" : state;
      el.dataset.state = shown;
      engineEl.textContent = engine;
      engineEl.hidden = !engine;
      stateEl.textContent = (shown === "working" && detail) ? t("call.working", { tool: detail }) : t(STATE_KEYS[shown] || STATE_KEYS.listening);
      clockEl.textContent = startedAt ? clock((now() - startedAt) / 1000) : "";
      muteBtn.textContent = t(muted ? "call.unmute" : "call.mute");
      muteBtn.setAttribute("aria-pressed", muted ? "true" : "false");
      hangBtn.textContent = t("call.hangup");
    }

    return {
      show: function (engineLabel) {
        engine = engineLabel || "";
        state = "connecting"; detail = ""; muted = false;
        startedAt = now();
        if (el) el.hidden = false;
        if (timer) clearIntervalFn(timer);
        timer = setIntervalFn(render, 1000);
        render();
      },
      hide: function () {
        if (timer) clearIntervalFn(timer);
        timer = null; startedAt = 0; muted = false;
        if (el) el.hidden = true;
      },
      setState: function (next, info) {
        state = STATE_KEYS[next] ? next : "listening";
        detail = info || "";
        render();
      },
      setEngine: function (label) { engine = label || ""; render(); },
      setMuted: function (value) { muted = !!value; render(); },
      isVisible: function () { return !!(el && !el.hidden); },
      state: function () { return muted ? "muted" : state; },
      clock: clock,
    };
  }

  var api = { create: create, clock: clock };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.JavisCallBar = api;
})(typeof window !== "undefined" ? window : globalThis);
