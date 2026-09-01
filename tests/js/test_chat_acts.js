/* Test hang nut duoi tin nhan (chat-acts.js). Chay tay / CI:
       node dashboard/test_chat_acts.js
   KHONG can trinh duyet: chi test ham thuan + mot vai node DOM gia.
   Ghi chu: KHONG dung ky tu em dash o bat ky dau. */
const A = require("../../dashboard/chat-acts.js");

let fails = [];
function check(name, cond) {
  console.log((cond ? "ok   " : "FAIL ") + name);
  if (!cond) fails.push(name);
}
function has(h, s) { return h.indexOf(s) !== -1; }

// Mốc giờ dựng theo giờ máy để không lệ thuộc múi giờ chạy test.
const TS = new Date(2026, 6, 27, 6, 38, 0).getTime();   // 06:38 ngày 27/07/2026
const THU = ["Chủ nhật", "Thứ hai", "Thứ ba", "Thứ tư", "Thứ năm", "Thứ sáu", "Thứ bảy"];

// ---- 1. Định dạng giờ ----
check("giờ: HH:mm có số 0 đứng đầu", A.fmtTime(TS) === "06:38");
check("giờ đầy đủ: có ngày tháng năm", has(A.fmtTimeFull(TS), "27/07/2026"));
check("giờ đầy đủ: có thứ đúng", has(A.fmtTimeFull(TS), THU[new Date(TS).getDay()]));
check("giờ đầy đủ: kèm cả giờ phút", has(A.fmtTimeFull(TS), "06:38"));

// ---- 2. Tin cũ chưa có mốc giờ thì ẨN, tuyệt đối không lấy giờ hiện tại ----
check("không có ts: giờ rỗng", A.fmtTime(0) === "" && A.fmtTime(null) === "" && A.fmtTime(undefined) === "");
check("không có ts: giờ đầy đủ rỗng", A.fmtTimeFull(0) === "");
check("ts hỏng: giờ rỗng", A.fmtTime("khong-phai-so") === "");
check("không có ts: hàng nút không có ô giờ", !has(A.actsHtml("user", 0), "msg-time"));
check("không có ts: vẫn còn các nút", has(A.actsHtml("user", 0), 'data-act="retry"'));

// ---- 3. Tin của người dùng: giờ + gửi lại + sửa lại + copy ----
let h = A.actsHtml("user", TS);
check("tin user: có ô giờ", has(h, '<span class="msg-time"') && has(h, ">06:38</span>"));
check("tin user: giờ đầy đủ nằm ở title", has(h, "27/07/2026 06:38"));
check("tin user: có nút gửi lại", has(h, 'data-act="retry"'));
check("tin user: có nút sửa lại", has(h, 'data-act="edit"'));
check("tin user: có nút copy", has(h, 'data-act="copy"'));
check("tin user: nút không submit form", (h.match(/type="button"/g) || []).length === 3);

// ---- 4. Tin Javis: CHỈ giờ + copy ----
// Nút "Trả lời lại câu hỏi phía trên" bỏ ở 0.52.13 (chủ repo yêu cầu): nó nằm ngay cạnh nút
// sao chép - thao tác hay dùng nhất dưới một câu trả lời - nên bấm trượt một ly là Javis chạy
// lại cả lượt, tốn tiền và mất câu trả lời đang đọc.
h = A.actsHtml("javis", TS);
check("tin javis: có giờ", has(h, "msg-time"));
check("tin javis: KHÔNG còn nút chạy lại", !has(h, 'data-act="retry"'));
check("tin javis: KHÔNG có nút sửa", !has(h, 'data-act="edit"'));
check("tin javis: có copy", has(h, 'data-act="copy"'));
check("tin javis: chỉ còn đúng 1 nút", (h.match(/class="msg-act"/g) || []).length === 1);
// Đường hỏi lại KHÔNG mất: nó nằm trên chính bong bóng câu hỏi của người dùng.
check("gửi lại vẫn còn ở tin người dùng", has(A.actsHtml("user", TS), 'data-act="retry"'));

// ---- 5. Chuỗi tiếng Việt hiển thị cho người dùng phải CÓ DẤU ----
h = A.actsHtml("user", TS);
check("nhãn có dấu: Gửi lại", has(h, "Gửi lại câu này"));
check("nhãn có dấu: Sửa lại", has(h, "Sửa lại rồi gửi"));
check("nhãn có dấu: Sao chép", has(h, "Sao chép nội dung"));

// ---- 6. Tìm ngược lên tin người dùng gần nhất (nút trả lời lại ở tin Javis) ----
function node(cls, text) {
  return {
    classList: { contains: function (c) { return cls.split(" ").indexOf(c) !== -1; } },
    dataset: { text: text },
    previousElementSibling: null,
  };
}
function chain(list) {
  for (let i = 1; i < list.length; i++) list[i].previousElementSibling = list[i - 1];
  return list;
}
const u1 = node("msg msg-user", "câu hỏi một");
const j1 = node("msg msg-javis", "");
const u2 = node("msg msg-user", "câu hỏi hai");
const j2 = node("msg msg-javis", "");
chain([u1, j1, u2, j2]);

// prevUserText đã BỎ cùng nút "trả lời lại": nó sinh ra chỉ để ngược lên tìm câu hỏi cho nút
// đó. Không còn nút thì không còn ai gọi, và giữ lại một hàm không ai gọi là để lại rác.
check("prevUserText đã gỡ khỏi API", A.prevUserText === undefined);
check("nhận diện tin user", A.isUserMsg(u1) === true && A.isUserMsg(j1) === false);
check("nhận diện: node rỗng không nổ", A.isUserMsg(null) === false);

// ---- 7. Tin chỉ có ảnh (không có chữ): bỏ hẳn nút gửi lại + sửa lại ----
h = A.actsHtml("user", TS, false);
check("chỉ có ảnh: bỏ nút gửi lại", !has(h, 'data-act="retry"'));
check("chỉ có ảnh: bỏ nút sửa lại", !has(h, 'data-act="edit"'));
check("chỉ có ảnh: vẫn còn nút copy", has(h, 'data-act="copy"'));
check("chỉ có ảnh: vẫn còn giờ", has(h, "msg-time"));
check("chỉ có ảnh: chỉ còn đúng 1 nút", (h.match(/class="msg-act"/g) || []).length === 1);

h = A.actsHtml("javis", TS, false);
check("javis không có câu hỏi chữ: bỏ nút gửi lại", !has(h, 'data-act="retry"'));
check("javis không có câu hỏi chữ: vẫn còn copy", has(h, 'data-act="copy"'));

// Bỏ trống tham số thì giữ nguyên hành vi cũ (các chỗ gọi cũ không đổi)
h = A.actsHtml("user", TS);
check("không truyền canResend: vẫn đủ 3 nút", (h.match(/class="msg-act"/g) || []).length === 3);
check("canResend=true: vẫn đủ 3 nút", (A.actsHtml("user", TS, true).match(/class="msg-act"/g) || []).length === 3);

// ---- 8. Escape: nhãn/giờ nhét vào HTML không được mở thẻ ----
check("hàng nút không chứa thẻ lạ", !has(A.actsHtml("user", TS), "<script"));

console.log(fails.length ? "\n" + fails.length + " test HỎNG" : "\nTất cả test đều đạt");
process.exit(fails.length ? 1 : 0);
