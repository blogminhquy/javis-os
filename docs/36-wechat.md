# 36 - WeChat (Official Account)

***Tiếng Việt** · [English](en/36-wechat.md)*

Một Bot chuyên trách trả lời được khách nhắn vào **WeChat Official Account** của bạn (tài khoản doanh nghiệp mà khách bấm Theo dõi), giống bot đang trả lời trên Zalo OA, Messenger hay Telegram: cùng Agent, cùng brain, cùng giờ trực, mọi cuộc chat vào Hộp thư, tiếp quản được khi cần người thật.

## WeChat có mấy đường, vì sao Javis chọn Official Account

| Đường | Ai nhắn được cho bot | Cần gì | Javis |
|---|---|---|---|
| **Official Account** (tài liệu này) | Mọi người dùng WeChat đã theo dõi tài khoản | Tài khoản đã xác minh, tên miền công khai | Có, kênh **WeChat** |
| **WeChat ClawBot** (iLink Bot API của Tencent, 2026) | Chỉ đúng người quét mã QR | Một nick WeChat cá nhân | Chưa. Đây là trợ lý riêng, không phải kênh khách hàng |
| **WeCom, Chăm sóc khách hàng** | Người dùng WeChat bấm vào link của doanh nghiệp | Doanh nghiệp WeCom đã xác minh | Chưa |
| Nick cá nhân qua công cụ không chính thức | Ai cũng nhắn được | Phần mềm lách giao thức | Không. Trái điều khoản WeChat, nick dễ bị khoá |

Chatbot là để KHÁCH nhắn vào, nên chỉ Official Account hợp việc. Javis đi qua API chính thức của WeChat (`api.weixin.qq.com`).

| | WeChat Official Account |
|---|---|
| Javis kết nối thế nào | Webhook: WeChat gọi vào Javis, **cần địa chỉ công khai** ở cổng 443 (https) hoặc 80 |
| Nhóm | Không, chỉ chat riêng với tài khoản |
| File | Nhận chữ, ảnh, tin thoại, vị trí, link. Gửi chữ và ảnh JPG/PNG/GIF (tối đa 10MB). Không gửi được tài liệu |
| Tin thoại | Chép thành chữ (dùng bản WeChat tự nhận dạng nếu có, không thì cần key Groq ở trang Models) |
| Trả lời | Bằng "tin chăm sóc khách hàng", chỉ trong 48 giờ sau tin cuối của khách |
| Định dạng | Chữ thường, mỗi tin tối đa 2048 byte. Javis tự bỏ ký hiệu Markdown và tự chia tin dài |
| Tên khách | WeChat không còn cho đọc tên. Khách hiện bằng mã OpenID |

## 1. Bạn cần có gì

- **Một Official Account đã xác minh.** WeChat chỉ cho tài khoản đã xác minh gửi tin chăm sóc khách hàng qua API. Doanh nghiệp ngoài Trung Quốc đăng ký được loại Service Account, có phí xác minh hằng năm. Tài khoản cá nhân chưa xác minh thì bot nhận được tin nhưng không trả lời được (lỗi 48001).
- **Muốn thử trước:** dùng **tài khoản thử nghiệm** miễn phí ở [mp.weixin.qq.com/debug/cgi-bin/sandbox?t=sandbox/login](https://mp.weixin.qq.com/debug/cgi-bin/sandbox?t=sandbox/login), quét bằng WeChat là có ngay AppID, AppSecret và đủ quyền API. Tối đa 100 người theo dõi.
- **Javis mở ra Internet** bằng tên miền (xem [tài liệu 15](15-thuong-hieu-ten-mien.md)), và máy chạy Javis có **IP ra ngoài cố định**: WeChat chỉ cấp access token cho IP nằm trong danh sách cho phép.

## 2. Lấy địa chỉ và Token từ Javis

1. Mở Javis **bằng tên miền**, vào **Chatbot**, tab **Bot**, bấm **Thêm kênh**, chọn **WeChat**.
2. Form hiện hai dòng: **Địa chỉ webhook** (dạng `https://<tên miền>/wechat/webhook`) và **Mã xác minh**. Mã này chính là ô **Token** bên WeChat. Javis tự sinh một lần cho cả máy và dùng nó để kiểm chữ ký từng tin.

## 3. Cấu hình bên WeChat

Trong [mp.weixin.qq.com](https://mp.weixin.qq.com), mục **Cài đặt và Phát triển**, **Cấu hình cơ bản** (设置与开发, 基本配置). Nếu không thấy mục này, WeChat có thể đã chuyển nó sang trang dành cho nhà phát triển; tên các ô vẫn như dưới.

1. Chép **AppID** và tạo, chép **AppSecret** (WeChat chỉ hiện AppSecret một lần).
2. **IP whitelist** (IP白名单): thêm IP ra ngoài của máy chạy Javis. Chưa biết IP nào thì cứ làm tiếp, lúc bấm Kiểm tra Javis báo đúng IP cần thêm.
3. **Cấu hình máy chủ** (服务器配置), bấm sửa:
   - **URL**: dán Địa chỉ webhook của Javis.
   - **Token**: dán Mã xác minh của Javis.
   - **EncodingAESKey**: bấm tạo ngẫu nhiên, chép lại.
   - **Cách mã hoá tin**: chọn **Chế độ an toàn** (安全模式, Safe mode).
4. Bấm **Gửi**. WeChat gọi thử vào Javis ngay lúc đó, đúng Token thì báo thành công. Rồi bấm **Bật** (启用).

Tài khoản thử nghiệm không có ô EncodingAESKey: chỉ điền URL và Token, nó chạy ở Chế độ văn bản thường.

## 4. Thêm tài khoản WeChat trong Javis

1. Ở ô Token của form **Thêm kênh**, **WeChat**, dán các thứ cách nhau dấu cách (thứ tự nào cũng được, Javis nhận ra theo hình dạng):

   ```
   <AppID> <AppSecret> <EncodingAESKey>
   ```

   Chạy Chế độ văn bản thường thì bỏ EncodingAESKey.
2. Bấm **Kiểm tra**. Javis xin thử một access token: qua được nghĩa là AppID, AppSecret đúng và IP đã nằm trong whitelist.
3. Bấm **Lưu**, rồi vào **Chatbot**, **Bot** để tạo bot hoặc gắn bot có sẵn cho kênh này. Bot bật lên là bắt đầu trả lời.

## 5. Vì sao nên chọn Chế độ an toàn

Ở Chế độ văn bản thường, chữ ký của WeChat chỉ ký lên Token, thời điểm và một số ngẫu nhiên, **không ký lên nội dung tin**. Ai chặn được một địa chỉ gọi hợp lệ thì gắn được nội dung giả vào đó. Chế độ an toàn mã hoá nội dung bằng AES và ký lên bản mã, nên không giả được.

Javis siết thêm hai điều: yêu cầu nào có thời điểm cũ hơn 15 phút đều bị từ chối, và tài khoản đã khai EncodingAESKey thì **chỉ nhận tin đã mã hoá**.

**Nhiều tài khoản ở Chế độ văn bản thường:** tin chưa mã hoá chỉ ghi ID gốc (`gh_...`) của tài khoản, nên Javis không tự biết tin của tài khoản nào. Thêm ID gốc vào cuối thông tin đăng nhập của từng tài khoản (`<AppID> <AppSecret> gh_...`), hoặc dùng Chế độ an toàn. Chỉ có một tài khoản thì không cần.

## 6. Giới hạn của WeChat cần biết

- **5 giây:** WeChat đòi máy chủ trả lời trong 5 giây, mà một lượt của Agent thường lâu hơn. Nên Javis báo "đã nhận" ngay rồi gửi câu trả lời sau qua API tin chăm sóc khách hàng. Khách vẫn thấy câu trả lời như thường.
- **48 giờ:** quá 48 giờ kể từ tin cuối của khách thì không gửi được nữa. Khách nhắn lại là mở lại.
- **Số tin sau mỗi tin của khách có hạn.** Javis gộp câu trả lời vào ít tin nhất có thể; trả lời rất dài bị chia nhiều tin thì có thể chạm trần.
- **Sự kiện** theo dõi, bấm menu, quét mã không mở lượt trả lời. Bot chỉ trả lời khi khách nhắn.

## 7. Khi bot im lặng

- **Lỗi 40164, IP chưa nằm trong whitelist:** câu lỗi ghi rõ IP. Thêm IP đó vào IP whitelist ở bước 3. Máy đổi IP thì phải thêm lại, nên dùng VPS có IP cố định.
- **Lỗi 48001, chưa được cấp quyền API:** tài khoản chưa xác minh. Xác minh tài khoản, hoặc thử bằng tài khoản thử nghiệm.
- **Lỗi 40125 hoặc 40001:** AppSecret sai, hoặc đã bị đặt lại. Sửa kênh, dán AppSecret mới.
- **Lỗi 45015:** khách đã quá 48 giờ không nhắn.
- **Lỗi 45047:** đã gửi hết số tin WeChat cho phép sau tin của khách. Chờ khách nhắn tiếp.
- **WeChat báo "Token xác minh thất bại" khi bấm Gửi:** URL phải đúng y địa chỉ Javis hiện, Token đúng y Mã xác minh, và Javis phải mở được từ Internet.
- **Thẻ bot báo "WeChat đang gửi tin chưa mã hoá":** bạn đã khai EncodingAESKey trong Javis nhưng bên WeChat đang ở Chế độ văn bản thường. Chuyển WeChat sang Chế độ an toàn, hoặc bỏ EncodingAESKey trong Javis.
- **Khách thấy "tài khoản đang gặp sự cố":** Javis không trả lời kịp WeChat. Kiểm tra máy chủ Javis còn chạy và tên miền còn trỏ đúng.
