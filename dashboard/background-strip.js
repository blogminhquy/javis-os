/* background-strip.js - dải "đang chạy ngầm" ngay trên khung nhập.
 *
 * VÌ SAO CÓ FILE NÀY
 * Chủ repo báo (2026-08-06): "có agent chạy ngầm thì anh cũng không biết là nó đang chạy thật
 * hay không, không giống Claude nếu đang chạy ngầm thì vẫn có báo ở đầu hội thoại. Đây là
 * không thấy gì luôn và không chạy luôn."
 *
 * Đúng cả hai vế. Khung chat trước bản này KHÔNG hiện một chữ nào về việc nền: việc Kanban,
 * loop, nhắc hẹn đều sống ở trang khác. Muốn biết phải tự mở trang Việc - mà người dùng thì
 * không có lý do gì để nghĩ là phải mở. Tệ hơn, điều phối Kanban mặc định TẮT nên việc giao
 * từ chat nằm im vô thời hạn, và đó cũng là thứ không hiện ở đâu cả.
 *
 * Dải này trả lời đúng một câu hỏi: "ngay lúc này có cái gì đang chạy cho tôi không". Ba mức:
 *   - đang chạy thật  -> chấm xanh nhấp nháy + tên việc
 *   - đã giao, đang xếp hàng, điều phối TẮT -> chấm vàng + nói thẳng là nó KHÔNG tự chạy
 *   - không có gì      -> ẩn hẳn dải (im lặng đúng nghĩa, không phải im lặng vì mù)
 */
(function () {
  "use strict";

  var POLL_MS = 6000;         // nhịp hỏi server khi tab đang được nhìn
  var POLL_IDLE_MS = 30000;   // tab ẩn: vẫn hỏi nhưng thưa, để quay lại là thấy số đúng ngay
  var timer = null, inflight = false, lastKey = "";

  function el() { return document.getElementById("bgStrip"); }

  function sid() {
    try { return (window.JavisSessions && window.JavisSessions.current()) || ""; }
    catch (e) { return ""; }
  }

  function brain() {
    try { return (window.JavisSessions && window.JavisSessions.brain()) || "brain"; }
    catch (e) { return "brain"; }
  }

  function esc(t) {
    return String(t == null ? "" : t).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  var NHAN = {
    running: "đang chạy", review: "chờ duyệt", blocked: "kẹt", ready: "sẵn sàng",
    todo: "chờ tới lượt", triage: "mới nhận", enabled: "đang bật", pending: "chờ tới giờ"
  };
  var LOAI = { task: "Việc", loop: "Loop", reminder: "Nhắc" };

  function hide() {
    var e = el();
    if (e) { e.hidden = true; e.innerHTML = ""; }
    lastKey = "";
  }

  function render(d) {
    var e = el();
    if (!e) return;
    var items = d.items || [];
    if (!items.length) { hide(); return; }

    // Khoá so sánh: không vẽ lại DOM khi không có gì đổi. Vẽ lại mỗi 6 giây làm nháy chấm
    // nhấp nháy và làm mất selection nếu người dùng đang bôi đen tên việc.
    var key = JSON.stringify([d.orchestration, d.stalled_count, items.map(function (x) {
      return [x.kind, x.id, x.status, x.mine].join("|");
    })]);
    if (key === lastKey) return;
    lastKey = key;

    var chay = d.running_count || 0;
    var dung = d.stalled_count || 0;
    var muc;
    if (chay) muc = "run";
    else if (dung) muc = "stall";
    else muc = "idle";

    var dau;
    if (chay) dau = chay + " việc đang chạy ngầm";
    else if (dung) dau = dung + " việc đã giao nhưng KHÔNG tự chạy";
    else dau = items.length + " việc nền đang chờ tới giờ";
    if (d.mine_count) dau += " · " + d.mine_count + " của hội thoại này";

    var chips = items.map(function (x) {
      return '<span class="bg-chip' + (x.mine ? " mine" : "") +
        (x.status === "running" ? " on" : "") + '" title="' +
        esc(LOAI[x.kind] || x.kind) + " · " + esc(NHAN[x.status] || x.status) +
        (x.mine ? " · giao từ hội thoại này" : "") + '">' +
        '<b>' + esc(LOAI[x.kind] || x.kind) + '</b> ' + esc(x.title) +
        ' <i>' + esc(NHAN[x.status] || x.status) + '</i></span>';
    }).join("");
    if (d.truncated) chips += '<span class="bg-chip">+' + d.truncated + " nữa</span>";

    var canhbao = "";
    if (dung) {
      canhbao = '<div class="bg-warn">Điều phối của brain này đang ở mức "' +
        esc(d.orchestration) + '" nên việc chỉ nằm xếp hàng. Bật "AI tự vận hành" ở trang ' +
        'Việc thì chúng mới chạy và tự báo kết quả về đây.</div>';
    }

    e.hidden = false;
    e.className = "bg-strip bg-" + muc;
    e.innerHTML =
      '<div class="bg-head"><span class="bg-dot"></span><span class="bg-title">' + esc(dau) +
      '</span><button type="button" class="bg-open">Trang Việc</button></div>' +
      '<div class="bg-chips">' + chips + '</div>' + canhbao;

    var btn = e.querySelector(".bg-open");
    if (btn) btn.onclick = function () {
      try { window.Alpine.store("nav").go("kanban"); } catch (err) { location.hash = "#kanban"; }
    };
  }

  function refresh() {
    var e = el();
    if (!e || inflight) return;
    var s = sid();
    inflight = true;
    var url = "/background?brain=" + encodeURIComponent(brain()) +
      "&chat_id=" + encodeURIComponent(s ? "web:" + s : "");
    fetch(url, { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) { if (d && d.ok) render(d); })
      .catch(function () { /* mất mạng thì giữ nguyên dải cũ, đừng nháy */ })
      .then(function () { inflight = false; });
  }

  function tick() {
    if (timer) clearTimeout(timer);
    refresh();
    timer = setTimeout(tick, document.hidden ? POLL_IDLE_MS : POLL_MS);
  }

  function start() { if (!timer) tick(); }
  function stop() { if (timer) { clearTimeout(timer); timer = null; } }

  document.addEventListener("visibilitychange", function () {
    // Quay lại tab: hỏi NGAY một nhát rồi mới về nhịp thường. Người dùng rời máy 10 phút rồi
    // quay lại mà phải đợi thêm 6 giây mới thấy số đúng là đủ để họ kết luận "lại không chạy".
    if (!document.hidden) tick();
  });

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();

  // Đổi hội thoại thì dải cũ không còn đúng nữa: xoá ngay rồi hỏi lại, đừng để chip của phiên
  // trước nằm lại vài giây trên phiên mới.
  window.JavisBackground = {
    refresh: refresh,
    reset: function () { hide(); refresh(); },
    start: start,
    stop: stop
  };
})();
