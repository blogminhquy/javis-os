/* chat-acts.js - hang nut duoi moi tin nhan trong khung chat Javis.

   Moi bong bong co mot hang nho ben duoi. Tin cua NGUOI DUNG: gio gui, gui lai, sua lai,
   sao chep. Tin cua JAVIS: chi gio gui + sao chep. Hang nay AN san (opacity 0), chi hien khi
   hover tren may tinh hoac khi cham vao tin tren dien thoai (.acts-on).

   File nay chi giu phan THUAN (khong dung tai lieu DOM that) de test bang node:
     node dashboard/test_chat_acts.js
   Phan gan su kien nam trong app.js vi no can sendMessage / chatInput.

   Ghi chu: KHONG dung ky tu em dash o bat ky dau. */
(function () {
  "use strict";

  var THU = ["Chủ nhật", "Thứ hai", "Thứ ba", "Thứ tư", "Thứ năm", "Thứ sáu", "Thứ bảy"];

  // File này chạy hai chế độ: trong trình duyệt và dưới node (test require nó).
  // Dưới node không có window nên không có ic() - trả về chuỗi rỗng để phần logic
  // vẫn test được mà không phải kéo cả tầng icon vào. Trong trình duyệt thì
  // icons.js đã nạp trước (index.html bảo đảm thứ tự, có test canh) nên lấy
  // được hàm thật.
  var ic = (typeof window !== "undefined" && window.ic) ? window.ic : function () { return ""; };

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
    return THU[d.getDay()] + ", " + pad2(d.getDate()) + "/" + pad2(d.getMonth() + 1) +
      "/" + d.getFullYear() + " " + fmtTime(ts);
  }

  // role: "user" | "javis".
  //
  // Tin cua JAVIS chi con gio + sao chep. Nut "Tra loi lai cau hoi phia tren" da BO
  // (chu repo yeu cau 01/09): no nam ngay canh nut sao chep, ma sao chep la thao tac
  // hay dung nhat duoi mot cau tra loi - bam truot mot ly la Javis chay lai ca luot,
  // ton tien va de mat cau tra loi dang doc. Ai muon hoi lai thi go lai cau hoi, hoac
  // bam "Gui lai cau nay" ngay tren bong bong cau hoi cua chinh minh - van con day.
  //
  // canResend=false khi khong co CHU de gui lai (tin chi co anh, khong kem loi nhan).
  // Khi do bo han nut gui lai + sua lai thay vi de nut bam vao khong ra gi. Bo trong
  // tham so nay thi mac dinh van co nut, de cac cho goi cu khong doi hanh vi.
  function actsHtml(role, ts, canResend) {
    var t = fmtTime(ts);
    var time = t
      ? '<span class="msg-time" title="' + esc(fmtTimeFull(ts)) + '">' + esc(t) + "</span>"
      : "";
    var send = "";
    if (canResend !== false && role === "user") {
      send = '<button class="msg-act" type="button" data-act="retry" title="Gửi lại câu này">↻</button>' +
        '<button class="msg-act" type="button" data-act="edit" title="Sửa lại rồi gửi">' + ic("pencil") + '</button>';
    }
    return '<div class="msg-acts">' + time + send +
      '<button class="msg-act" type="button" data-act="copy" title="Sao chép nội dung">⧉</button>' +
      "</div>";
  }

  function isUserMsg(el) {
    return !!(el && el.classList && el.classList.contains("msg-user"));
  }

  var API = {
    fmtTime: fmtTime,
    fmtTimeFull: fmtTimeFull,
    actsHtml: actsHtml,
    isUserMsg: isUserMsg,
  };

  if (typeof window !== "undefined") window.JavisActs = API;
  if (typeof module !== "undefined" && module.exports) module.exports = API;
})();
