/* quick-settings.js - trạng thái BẬT/TẮT đọc trả lời bằng giọng (nhớ qua reload).
   Từ 02/09 loa ĐI THEO MIC: app.js gọi window.JavisTts.set() khi bật/tắt mic, và mic là công
   tắc duy nhất người dùng bấm. Nút loa trên thanh nhập (#ttsToggleBar) đã bỏ theo yêu cầu
   chủ repo; nút loa header (#ttsToggle) bỏ từ 0.48.3. Công tắc trong Cài đặt nhanh (#qsTts)
   giữ lại làm chỗ tắt tiếng thủ công, và nó cũng đi qua applyState. */
(function () {
  "use strict";
  function $(id) { return document.getElementById(id); }
  function getVoice() { try { return (typeof voice !== "undefined") ? voice : null; } catch (e) { return null; } }
  // Mặc định TẮT: chưa từng bật (chưa có khoá, hoặc "0") thì coi như đang tắt tiếng.
  function isOff() { return localStorage.getItem("javis.ttsEnabled") !== "1"; }
  function persist(on) { try { localStorage.setItem("javis.ttsEnabled", on ? "1" : "0"); } catch (e) {} }

  // Cập nhật chỗ hiển thị trạng thái đọc-giọng (Cài đặt nhanh).
  function reflect(on) {
    var qs = $("qsTts"); if (qs) qs.checked = on;
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
  }

  // Cho app.js gọi khi bật/tắt mic: loa đi theo mic (02/09). Đi qua applyState để nút loa,
  // công tắc Cài đặt nhanh và localStorage cùng đổi - không có đường "đổi lén" nào.
  window.JavisTts = { set: applyState, isOn: function () { return !isOff(); } };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind);
  else bind();
})();
