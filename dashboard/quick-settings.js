/* quick-settings.js - công tắc BẬT/TẮT đọc trả lời bằng giọng (nhớ qua reload).
   Đồng bộ 2 chiều: công tắc trong Cài đặt nhanh (#qsTts) ↔ nút loa trên thanh nhập chat
   (#ttsToggleBar). Tách riêng để không đụng app.js.
   Nút loa ở header (#ttsToggle) đã bỏ ở 0.48.3 - ba chỗ bấm cho cùng một công tắc là thừa. */
(function () {
  "use strict";
  function $(id) { return document.getElementById(id); }
  function getVoice() { try { return (typeof voice !== "undefined") ? voice : null; } catch (e) { return null; } }
  // Mặc định TẮT: chưa từng bật (chưa có khoá, hoặc "0") thì coi như đang tắt tiếng.
  function isOff() { return localStorage.getItem("javis.ttsEnabled") !== "1"; }
  function persist(on) { try { localStorage.setItem("javis.ttsEnabled", on ? "1" : "0"); } catch (e) {} }

  // Cập nhật MỌI chỗ hiển thị trạng thái đọc-giọng (Cài đặt nhanh + nút trên thanh nhập).
  function reflect(on) {
    var qs = $("qsTts"); if (qs) qs.checked = on;
    var bar = $("ttsToggleBar");
    if (bar) { bar.classList.toggle("muted", !on); bar.title = on ? "Tắt giọng đọc" : "Bật giọng đọc"; }
  }
  function applyState(on) {
    persist(on);
    var v = getVoice();
    if (v) { v.ttsEnabled = on; if (!on && v.stopSpeaking) { try { v.stopSpeaking(); } catch (e) {} } }
    reflect(on);
  }

  function bind() {
    var on = !isOff();
    reflect(on);
    var v = getVoice(); if (v) v.ttsEnabled = on;

    var qs = $("qsTts"); if (qs) qs.addEventListener("change", function () { applyState(qs.checked); });

    // Nút loa trên khung chat: bấm là bật/tắt luôn (đi qua khung chat / màn Javis đều thấy).
    var bar = $("ttsToggleBar");
    if (bar) bar.addEventListener("click", function () { applyState(isOff()); });   // đang OFF → bật, đang ON → tắt
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind);
  else bind();
})();
