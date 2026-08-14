/* Mở hội thoại cũ phải rơi vào CUỐI hội thoại, không phải câu hỏi đầu tiên.

       node tests/js/test_giu_cho_cuon_khi_doi_trang.js

   Chủ repo báo (2026-08-12): "những hội thoại cũ khi truy cập vào thì luôn bắt đầu từ phần câu
   hỏi đầu tiên. Anh muốn khi vào thì màn hình load đến cuối của hội thoại".

   Gốc KHÔNG nằm ở chỗ nạp tin. app.js đã gọi scrollBottom(true) đàng hoàng sau khi dựng xong
   bong bóng. Thứ xoá công của nó là cú DỜI NODE ngay sau đó: trang Trò chuyện mượn #chatArea
   (console.js _borrowChatNodes) rồi appendChild sang khung mới, mà dời một node đang cuộn thì
   TRÌNH DUYỆT tự đặt lại scrollTop về 0.

   Đã đo trong Chromium thật trước khi sửa: scrollTop 4059 -> 0 ngay sau appendChild. Không lỗi
   nào hiện ra, chỉ là mỗi lần mở đều rơi về đầu một hội thoại có khi hàng trăm tin.

   Sửa xong đo lại, hai ca:
     - đang ở đáy  -> dời xong vẫn ở đáy (cách đáy 0px)
     - đọc giữa chừng + khung mới RỘNG KHÁC (820 -> 560) -> vẫn đúng tin đang đọc

   Ca thứ hai là lý do không được nhớ theo pixel: cột chat ở màn chính hẹp hơn khung ở trang
   Trò chuyện, cùng nội dung mà xuống dòng khác đi nên scrollHeight đổi hẳn. Phải neo vào MỘT
   TIN cụ thể. CI chỉ có node nên file này khoá phần hợp đồng đọc được từ mã nguồn. */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const CON = fs.readFileSync(path.join(ROOT, "dashboard", "console.js"), "utf8");

const fails = [];
const check = (name, cond) => { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); };

check("có hàm neo chỗ đọc", /function _neoCuon\(\)/.test(CON));
check("có hàm thả lại chỗ đọc", /function _thaCuon\(neo\)/.test(CON));

// ============================================================
// Cả HAI chiều đều dời node, nên cả hai đều phải neo
// ============================================================
// Chỉ vá chiều đi là mở hội thoại thì đúng, nhưng quay về màn chính lại nhảy về đầu - nửa vời
// mà rất dễ tưởng là xong.
const diBorrow = CON.slice(CON.indexOf("function _borrowChatNodes"),
                           CON.indexOf("// ===== Cho tab \"Thư mục\""));
check("bóc được _borrowChatNodes", diBorrow.length > 100);
check("CANARY: chiều ĐI (mượn node) có neo chỗ đọc",
  /_neoCuon\(\)/.test(diBorrow) && /_thaCuon\(neo\)/.test(diBorrow));

// Cắt bằng ĐỘ DÀI cố định chứ không cắt tới "function renderChat": chuỗi đó còn khớp một hàm
// khác nằm trước trong file (renderChatbots), nên cắt theo nó ra chuỗi rỗng và test "xanh" mà
// chưa soi dòng nào - đúng kiểu hỏng im lặng mà bộ test này sinh ra để chặn.
const iRet = CON.indexOf("function _returnChatNodes");
const veReturn = CON.slice(iRet, iRet + 1200);
check("bóc được _returnChatNodes", veReturn.length > 100);
check("CANARY: chiều VỀ (trả node) cũng có neo chỗ đọc",
  /_neoCuon\(\)/.test(veReturn) && /_thaCuon\(neo\)/.test(veReturn));

// ============================================================
// Neo phải theo TIN NHẮN, không theo pixel
// ============================================================
// Nhớ theo pixel là sai ngay khi bề rộng khung đổi - mà đổi bề rộng chính là chuyện xảy ra mỗi
// lần chuyển giữa màn chính và trang Trò chuyện.
check("CANARY: neo vào một tin cụ thể, không nhớ scrollTop thô",
  /neo\.node\.getBoundingClientRect\(\)\.top/.test(CON));
check("đang ở đáy thì neo là 'đáy', không phải một tin",
  /return \{ day: true \}/.test(CON) && /neo\.day[\s\S]{0,120}scrollTop = ca\.scrollHeight/.test(CON));
// Tin được neo có thể biến mất giữa chừng (đổi phiên, xoá chat) - rơi về đáy chứ đừng nổ.
check("tin neo biến mất thì rơi về đáy, không nổ", /!neo\.node\.isConnected/.test(CON));

// Đo một lần rồi đặt là hụt: lúc gọi lần đầu, trang mới vừa dựng DOM nhưng bề rộng chưa chốt.
check("CANARY: đặt lại LẦN HAI ở khung hình sau (bề rộng chốt xong mới đúng)",
  /requestAnimationFrame\(dat\)/.test(CON));

console.log("");
if (fails.length) { console.log("THẤT BẠI " + fails.length + ": " + fails.join(", ")); process.exit(1); }
console.log("OK - test_giu_cho_cuon_khi_doi_trang: tất cả pass");
