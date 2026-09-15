/* quick-settings.js - trạng thái đọc trả lời bằng giọng trong phiên trang hiện tại.
   Từ 02/09 loa ĐI THEO MIC: app.js gọi window.JavisTts.set() khi bật/tắt mic, và mic là công
   tắc duy nhất bật được loa. Nút loa trên thanh nhập (#ttsToggleBar) đã bỏ theo yêu cầu
   chủ repo; nút loa header (#ttsToggle) bỏ từ 0.48.3. Công tắc trong Cài đặt nhanh (#qsTts)
   giữ lại làm chỗ TẮT tiếng thủ công, và nó cũng đi qua applyState.

   Lựa chọn này KHÔNG được nhớ qua reload: mỗi lần nạp trang bắt đầu im lặng, vì trang tự đọc
   thành tiếng ngay khi mở là điều không ai chờ đợi. Vì thế ở đây không còn ghi localStorage. */
(function () {
  "use strict";
  function $(id) { return document.getElementById(id); }
  function getVoice() { try { return (typeof voice !== "undefined") ? voice : null; } catch (e) { return null; } }
  function tr(k) { try { return window.t ? window.t(k) : k; } catch (e) { return k; } }
  function micDangBat() { try { return typeof handsFreeActive === "function" && !!handsFreeActive(); } catch (e) { return false; } }
  // Luôn khởi động tắt, kể cả lần trước đã bật mic; chỉ thao tác bật mic mới bật lại.
  var enabled = false;
  function isOff() { return !enabled; }

  // Cập nhật chỗ hiển thị trạng thái đọc-giọng (Cài đặt nhanh).
  //
  // Mic tắt thì công tắc này KHOÁ luôn: bật nó lên trong lúc mic tắt chỉ dẫn tới applyState(false),
  // tức là nó tự nảy về vị trí cũ mà không ai giải thích gì - người dùng tưởng nút hỏng. Khoá
  // lại rồi nói lý do bằng title thì màn hình nói đúng sự thật.
  function reflect(on) {
    var qs = $("qsTts"); if (!qs) return;
    qs.checked = on;
    var khoa = !on && !micDangBat();
    qs.disabled = khoa;
    var hang = (qs.closest && qs.closest(".qs-row")) || qs;
    if (khoa) hang.title = tr("qs.tts_can_mic");
    else if (hang.removeAttribute) hang.removeAttribute("title");
  }
  function applyState(on) {
    enabled = !!on;
    var v = getVoice();
    if (v) { v.ttsEnabled = on; if (!on && v.stopSpeaking) { try { v.stopSpeaking(); } catch (e) {} } }
    reflect(enabled);
  }

  function bind() {
    var on = enabled;
    reflect(on);
    var v = getVoice(); if (v) v.ttsEnabled = on;

    var qs = $("qsTts"); if (qs) qs.addEventListener("change", function () { applyState(qs.checked && micDangBat()); });
    // Từ điển về muộn (i18n nạp bằng fetch) thì vẽ lại câu giải thích, không để trơ tên key.
    if (window.addEventListener) window.addEventListener("javis:i18n", function () { reflect(enabled); });
  }

  // Cho app.js gọi khi bật/tắt mic: loa đi theo mic (02/09). Đi qua applyState để lớp giọng và
  // công tắc Cài đặt nhanh cùng đổi - không có đường "đổi lén" nào.
  window.JavisTts = { set: applyState, isOn: function () { return !isOff(); } };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bind);
  else bind();
})();
