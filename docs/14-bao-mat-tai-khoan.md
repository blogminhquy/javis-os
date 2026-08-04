# Bảo mật & tài khoản

Trang này giải thích cách Javis OS tự bảo vệ khi bạn đưa nó lên mạng, và cách dùng trang **Tài khoản** trong dashboard để đặt mật khẩu, đăng xuất, tắt đăng nhập và đổi tên workspace.

## Tính năng này là gì

Javis chạy bộ não AI với **toàn quyền trên máy/VPS** của bạn: nó đọc được tệp, chạy lệnh, gọi công cụ. Vì thế nếu để dashboard hở ra Internet mà không có mật khẩu thì bất kỳ ai biết địa chỉ cũng điều khiển được máy của bạn.

Javis xử lý việc này theo 6 lớp:

1. **Tự bắt buộc đăng nhập khi chạy public.** Khi server nghe ra ngoài (không phải chỉ máy này), Javis chặn mọi chức năng cho tới khi bạn đăng nhập. Chạy trên máy cá nhân (localhost) thì không ép, dùng thẳng như cũ.
2. **Chống chiếm tài khoản lần đầu.** Người đầu tiên muốn tạo admin phải có **MÃ THIẾT LẬP** (in trong log server) hoặc admin đã được đặt sẵn qua biến môi trường. Kẻ chỉ biết URL không tạo được tài khoản.
3. **Chống dò mật khẩu.** Sai nhiều lần bị khoá tạm theo địa chỉ IP; mỗi lần sai bị làm chậm.
4. **Chặn trang web lạ sai khiến Javis (CSRF) và chặn tên miền lạ trỏ về máy bạn (DNS-rebinding).** Xem mục riêng bên dưới.
5. **Mã hoá khoá bí mật lưu trong `settings.json`.** API key, token Telegram, token GitHub... không nằm dạng chữ thô trên đĩa.
6. **Token API cho CLI và script, mặc định KHÔNG có cái nào.** Cookie đăng nhập chỉ hợp với trình duyệt; muốn gọi Javis từ terminal thì phải tự tay tạo token, chọn phạm vi, và thu hồi được bất cứ lúc nào. Xem mục riêng bên dưới.

## Mở ở đâu trong Javis

Mọi thao tác tài khoản nằm ở mục **Tài khoản** trong nhóm **Hệ thống** trên thanh nav bên trái (phụ đề "Đăng nhập, workspace, token API"). Từ trang **Cài đặt** cũng có lối tắt tới đây; không có form tài khoản trùng lặp ở nơi khác.

Trang **Tài khoản** có 3 khối:

- **Workspace**: đổi tên workspace hiển thị.
- **Tài khoản đăng nhập**: đặt mật khẩu, đăng xuất, tắt đăng nhập.
- **Token API (cho CLI)**: tạo và thu hồi token để [Javis CLI](24-cli-terminal.md) hay script gọi được Javis. Nằm cùng trang vì token cũng là một cách đăng nhập, chỉ khác là dành cho máy chứ không cho trình duyệt.

## Khi nào Javis bắt buộc đăng nhập

Javis quyết định có ép đăng nhập hay không dựa vào cách server đang chạy:

| Tình huống | Có bắt buộc đăng nhập? |
|---|---|
| Chạy trên máy cá nhân, nghe `127.0.0.1` / `localhost` (hoặc `::1`) | Không (trừ khi bạn đã tự đặt mật khẩu) |
| Chạy public (Docker/VPS/Hostinger), nghe `0.0.0.0`, `::` hoặc IP LAN | Có, tự bật |
| Đã đặt mật khẩu trong trang Tài khoản | Có, ở mọi chế độ |

Có thể ép cứng bằng biến môi trường `JAVIS_REQUIRE_LOGIN`:

- `JAVIS_REQUIRE_LOGIN=1` : luôn bắt buộc đăng nhập, kể cả localhost. Nên đặt khi bạn mở Javis qua tunnel (Cloudflare Tunnel, ngrok...) trên máy cá nhân.
- `JAVIS_REQUIRE_LOGIN=0` : tắt bắt buộc đăng nhập.

Nguyên tắc an toàn (fail-closed): nếu server nghe địa chỉ **không phải** thuần localhost thì Javis mặc định coi là public và bật đăng nhập. Chi tiết biến môi trường xem [Cấu hình .env](16-cau-hinh-env.md).

## Cách dùng (từng bước)

### A. Tạo tài khoản admin lần đầu trên VPS/public

Khi mở dashboard lần đầu trên server công khai, Javis hiện màn **tạo tài khoản** và yêu cầu **MÃ THIẾT LẬP**. Có 2 cách:

**Cách 1 - Đặt sẵn admin bằng biến môi trường (khuyến nghị):**

1. Trong cấu hình deploy (ví dụ compose của Hostinger), thêm 2 biến:
   - `JAVIS_ADMIN_PASSWORD` : mật khẩu admin bạn chọn.
   - `JAVIS_ADMIN_USER` : tên đăng nhập (tuỳ chọn, mặc định là `admin`).
2. Khởi động Javis. Lúc boot, Javis tự tạo admin từ 2 biến này và **đóng luôn** màn tạo tài khoản. Bạn mở app là vào thẳng màn đăng nhập.
3. Đăng nhập bằng đúng user/password vừa đặt.

**Cách 2 - Dùng MÃ THIẾT LẬP in trong log:**

1. Mở log/terminal của server. Lúc khởi động, nếu đang public mà chưa có admin, Javis sinh mã thiết lập và lưu ra tệp `.setup_token` trong thư mục state.
   - Trên Hostinger, vào bên trong container (App terminal) chạy: `cat /data/state/.setup_token`.
   - Trên VPS chạy Docker: xem `docker compose logs javis` và tìm dòng có `SETUP TOKEN`.
2. Mở dashboard, ở màn tạo tài khoản nhập: tên tài khoản, mật khẩu (**tối thiểu 8 ký tự**), và dán **MÃ THIẾT LẬP**.
3. Bấm nút tạo tài khoản. Nếu mã đúng, Javis tạo admin, đăng nhập bạn luôn và mã thiết lập tự huỷ (dùng 1 lần).

Nếu nhập sai/thiếu mã, Javis báo: "Sai hoặc thiếu MÃ THIẾT LẬP - xem mã trong log/terminal của server."

Mã thiết lập chỉ được sinh **lúc server khởi động**. Nếu bạn đã dùng nó rồi (mã bị xoá) và sau đó lại cần tạo tài khoản mới, phải khởi động lại server để Javis sinh mã mới.

### B. Đặt mật khẩu (khi đang chạy máy cá nhân, chưa có mật khẩu)

Nếu bạn chạy Javis ở nhà mà muốn khoá lại trước khi đưa lên VPS:

1. Vào **Tài khoản** trên thanh nav trái.
2. Ở khối **Tài khoản đăng nhập**, nhập **Tài khoản** (để trống sẽ dùng `admin`).
3. Nhập **Mật khẩu**.
4. Bấm **Đặt mật khẩu**.
5. Javis lưu tài khoản và cấp phiên đăng nhập ngay cho bạn (không tự khoá bạn ra ngoài).

Lưu ý về độ dài mật khẩu, vì hai bên kiểm khác nhau và dễ gây bối rối:

| Nơi kiểm | Ngưỡng | Thông báo khi trượt |
|---|---|---|
| Giao diện (trước khi gửi) | dưới 4 ký tự là chặn ngay | ⚠ Mật khẩu tối thiểu 4 ký tự. |
| Server (khi lưu thật) | dưới 8 ký tự là từ chối | Mật khẩu tối thiểu 8 ký tự |

Nghĩa là nhập 4-7 ký tự thì giao diện cho qua nhưng server vẫn không lưu, và bạn nhận hai con số khác nhau trong hai lần bấm. Cứ đặt từ 8 ký tự trở lên là hết chuyện.

### C. Đổi mật khẩu (phải đi vòng)

Khi đã có mật khẩu, khối **Tài khoản đăng nhập** hiện dòng "🔒 Đã đặt mật khẩu · tài khoản: <tên của bạn>" và nút chuyển nhãn thành **Đổi mật khẩu**.

Nói thẳng để bạn khỏi mất thời gian: **nút Đổi mật khẩu hiện không đổi được gì.** Nó gửi tới đúng cái cửa dùng lúc tạo tài khoản lần đầu (`/auth/setup`), mà cửa đó luôn từ chối khi máy đã có tài khoản. Bấm vào bạn sẽ nhận đúng một dòng: **⚠ Đã có tài khoản - hãy đăng nhập.**

Đường đi được, khi bạn đang chạy trên **máy cá nhân**:

1. Vào **Tài khoản**, bấm **Tắt đăng nhập**.
2. Xác nhận ở hộp thoại "Tắt đăng nhập? Ai mở dashboard cũng dùng được." Javis xoá mật khẩu cũ và đăng xuất mọi phiên.
3. Khối quay lại trạng thái chưa có mật khẩu. Nhập **Tài khoản** + **Mật khẩu** mới rồi bấm **Đặt mật khẩu**.

Trên **VPS/public** thì cách trên không chạy trọn: vừa tắt xong là Javis ép ngay màn tạo tài khoản kèm MÃ THIẾT LẬP, mà mã cũ đã bị huỷ sau lần tạo đầu. Trên VPS hãy đổi mật khẩu bằng đường deploy:

1. Dừng container.
2. Xoá (hoặc làm rỗng) khối `"auth"` trong `settings.json` ở thư mục state (Docker: `/data/state/settings.json`).
3. Đặt `JAVIS_ADMIN_PASSWORD` (và `JAVIS_ADMIN_USER` nếu muốn) rồi khởi động lại. Javis tạo lại admin từ biến môi trường lúc boot.

### D. Đăng xuất

1. Vào **Tài khoản**.
2. Bấm **Đăng xuất**.
3. Javis xoá phiên hiện tại và tải lại trang. Lần sau vào phải đăng nhập lại.

Đăng xuất chỉ kết thúc phiên trên trình duyệt này, không xoá mật khẩu.

### E. Tắt đăng nhập (xoá mật khẩu)

Chỉ nên làm khi chạy máy cá nhân, tuyệt đối không làm trên VPS.

1. Vào **Tài khoản**.
2. Bấm **Tắt đăng nhập**.
3. Xác nhận ở hộp thoại "Tắt đăng nhập? Ai mở dashboard cũng dùng được."
4. Javis xoá mật khẩu và **đăng xuất mọi phiên** đang mở.

Lưu ý: nếu server vẫn đang chạy public (hoặc bạn đặt `JAVIS_REQUIRE_LOGIN=1`), tắt mật khẩu **không** làm dashboard mở toang, mà quay lại màn ép tạo tài khoản mới. Đăng nhập chỉ thật sự tắt khi server nghe localhost và không ép login.

### F. Đổi tên workspace

1. Vào **Tài khoản**.
2. Ở khối **Workspace**, sửa **Tên workspace**.
3. Bấm **Lưu**. Tên mới hiển thị ngay trên đầu dashboard.

## Chặn CSRF và DNS-rebinding

Đây là lớp bảo vệ chạy ngầm, bạn không phải bật gì, nhưng nên biết nó tồn tại vì đôi khi nó là thủ phạm của lỗi 403 khó hiểu.

Vấn đề nó giải: dashboard nghe ở `localhost:7777`. Khi bạn **chưa** đặt mật khẩu, một trang web bất kỳ đang mở trong trình duyệt của bạn vẫn có thể bắn request POST tới `http://localhost:7777/...`. Trình duyệt chặn trang đó ĐỌC kết quả, nhưng không chặn request chạy, nên hành động vẫn xảy ra. Kẻ tấn công cũng có thể trỏ một tên miền của chúng về `127.0.0.1` để lách kiểm tra nguồn gốc.

Javis chặn hai đường đó bằng một cổng gác đứng trước cả cổng đăng nhập:

| Trường hợp | Xử lý |
|---|---|
| Request GHI (POST/PUT/DELETE/PATCH) kèm `Origin` khác Host và không nằm trong allowlist | Chặn, trả 403 kèm `"cross-origin request bị chặn"` |
| Request đến với tên miền (Host) lạ, trong khi **chưa** bật cổng đăng nhập | Chặn, trả 403 kèm `"host không được phép"` |
| Cùng nguồn gốc (Origin trùng Host) | Cho qua |
| Client không phải trình duyệt (không gửi `Origin`, ví dụ CLI, curl, MCP) | Cho qua |
| Host là một địa chỉ IP | Bỏ qua bước kiểm Host |

Allowlist gồm: `localhost`, `127.0.0.1`, `::1`, `0.0.0.0`, cộng tên miền riêng bạn đã đặt trong **Cài đặt → Tên miền & SSL**, cộng mọi tên trong biến môi trường `JAVIS_ALLOWED_HOSTS` (nhiều tên cách nhau dấu phẩy).

Khi nào bạn cần đụng tới: chạy Javis sau một reverse proxy với tên miền chưa khai trong app, mà lại **chưa** đặt mật khẩu. Lúc đó Javis coi tên miền đó là lạ và trả 403. Cách sửa: đặt mật khẩu (bật cổng đăng nhập là bước kiểm Host tự bỏ qua), hoặc thêm tên miền vào `JAVIS_ALLOWED_HOSTS`.

## Token API - cửa cho CLI và script

Cookie đăng nhập chỉ hợp với trình duyệt. Khi bạn muốn [Javis CLI](24-cli-terminal.md) hay một script gọi được Javis, cần một credential khác: **token API**, tạo ở **Tài khoản > Token API (cho CLI)** (nhóm Hệ thống, cùng trang với mật khẩu đăng nhập).

Điểm quan trọng nhất: **không có token nào sẵn**. Chưa tự tay bấm tạo thì không token nào tồn tại, và không cửa nào vào ngoài trình duyệt. Mở thêm một cổng ra Internet phải là một hành động có ý thức.

Cách Javis giữ token:

| Luật | Vì sao |
|---|---|
| Hai mức phạm vi: **chỉ chat** và **toàn quyền** | Mức chỉ chat đi theo danh sách TRẮNG (`/chat`, `/version`, `/health`, `/sessions`). Chọn chiều trắng chứ không chiều đen, vì danh sách đen nghĩa là mỗi endpoint mới thêm vào Javis tự động phơi ra cho token hẹp. |
| Trên đĩa chỉ có bản băm SHA-256 | Ai đọc được file cấu hình của máy chủ cũng không lấy được token. Chuỗi thô hiện đúng một lần lúc tạo. |
| So bằng `compare_digest` | So chuỗi thường thoát sớm ở ký tự đầu khác nhau, và chênh lệch thời gian đó đủ để dò token theo từng ký tự. |
| Token đi trong header `Authorization`, không bao giờ trong query string | Query string nằm trong log của mọi proxy trên đường đi. |
| **Không dùng token để tạo token** | Tạo token đòi session trình duyệt. Thiếu rào này thì một token rò ra là kẻ cầm nó tự cấp thêm token vĩnh viễn, và thu hồi cái đã rò thành vô nghĩa. |
| Nhưng token **tự thu hồi được chính mình** | Mất laptop mà không mở nổi trình duyệt thì vẫn phải hạ được credential ngay. |
| Sai quá 10 lần trong 5 phút thì IP bị chặn 15 phút | Ghi vào `auth_audit.jsonl`, chỉ 12 ký tự đầu (file log hay bị gửi kèm báo lỗi). Một cuộc dò token trở thành thứ nhìn thấy được thay vì chạy im lặng hàng tháng. |

Danh sách token hiện **lần dùng cuối** của từng cái. Thấy một token bạn không nhớ đang được dùng đều đặn thì thu hồi ngay - thu hồi có hiệu lực lập tức, không hoàn tác được.

## Khoá bí mật trong settings.json được mã hoá

Các trường nhạy cảm trong `settings.json` không lưu dạng chữ thô. Javis mã hoá chúng bằng Fernet (AES-128-CBC + HMAC) trước khi ghi ra đĩa, và tự giải mã khi đọc lên. Giá trị đã mã hoá có tiền tố `enc:`.

Những trường được mã hoá:

| Trường | Là gì |
|---|---|
| `model.openrouter_key` | API key OpenRouter |
| `model.anthropic_api_key` | API key Anthropic |
| `model.openai_api_key` | API key OpenAI |
| `model.gemini_api_key` | API key Google Gemini |
| `model.openai_oauth.access_token` / `refresh_token` / `id_token` | Token đăng nhập ChatGPT |
| `telegram.token` | Bot token Telegram |
| `backup.token` | GitHub PAT dùng sao lưu brain |
| `voice.elevenlabs_key` | API key ElevenLabs |

Khoá dùng để mã hoá nằm ở tệp **`.secret_key`** trong thư mục state (`JAVIS_STATE_DIR`, Docker: `/data/state/.secret_key`). Tệp này sinh một lần, không lên git.

Hệ quả vận hành phải nhớ:

- **Chép `settings.json` sang máy khác mà quên `.secret_key` thì mất trắng mọi khoá.** Javis đọc thấy `enc:` nhưng không giải mã được nên trả về chuỗi rỗng, bạn phải nhập lại từng key. Đây là đánh đổi có chủ ý: thà bắt nhập lại còn hơn để key nằm phơi.
- **Sao lưu thì sao lưu cả cặp** `settings.json` + `.secret_key`, và giữ chúng ở nơi kín như nhau.
- Nếu máy thiếu thư viện `cryptography`, Javis không mã hoá được: secret rơi về tiền tố `plain:` và server in cảnh báo ra log. Cài bằng `pip install cryptography` rồi khởi động lại là mã hoá bật lại.
- Giá trị cũ chưa có tiền tố (lưu từ bản trước khi có mã hoá) vẫn đọc được bình thường, và tự được bọc `enc:` ở lần ghi kế tiếp.

## Cách bảo mật hoạt động (dành cho người muốn hiểu sâu)

| Cơ chế | Chi tiết thực tế |
|---|---|
| Lưu mật khẩu | Không lưu mật khẩu thô. Javis băm bằng PBKDF2-HMAC-SHA256 (120.000 vòng) kèm salt ngẫu nhiên. |
| Phiên đăng nhập | Cấp qua cookie `javis_session`, cookie dạng `httponly` (JavaScript không đọc được), `samesite=lax`. |
| Hết hạn phiên | Mỗi phiên sống tối đa **30 ngày** rồi tự hết hạn, phải đăng nhập lại. |
| Phiên qua khởi động lại | Phiên lưu ra tệp, nên **khởi động lại server không làm bạn bị đăng xuất**. |
| Chống dò mật khẩu | Đếm số lần sai theo IP. Sai đủ số lần liên tiếp (8 lần) bị khoá tạm khoảng 5 phút; mỗi lần sai bị làm chậm nửa giây. Khi bị khoá, Javis báo "Quá nhiều lần sai - thử lại sau ít phút." |
| Cookie an toàn khi HTTPS | Khi bạn truy cập qua **tên miền riêng** đã bật HTTPS (Caddy On-Demand TLS), cookie được đánh dấu `secure` (chỉ gửi qua HTTPS). |
| CORS | Chỉ mở cho `localhost` / `127.0.0.1` / `::1` (tiện lúc dev). Trang web khác không đọc được API qua trình duyệt. |
| Cổng gác CSRF | Chặn request ghi từ nguồn gốc chéo, và chặn Host lạ khi chưa bật đăng nhập (xem mục riêng ở trên). |
| Secret trên đĩa | API key và token trong `settings.json` mã hoá Fernet bằng `.secret_key` trong thư mục state. |

Về cookie `secure`: mặc định Javis **không** ép cookie `secure` để chạy được cả HTTP lẫn HTTPS (tránh kẹt vòng đăng nhập sau proxy HTTP như đường dẫn dạng `http://host/PORT/`). Nếu bạn chắc chắn chạy HTTPS đầu-cuối, bật `JAVIS_SECURE_COOKIE=1` trong biến môi trường (xem [Cấu hình .env](16-cau-hinh-env.md)). Truy cập qua đúng tên miền riêng thì Javis tự bật `secure` mà không cần đặt biến này (dựa vào Host khớp tên miền, không suy từ `X-Forwarded-Proto`).

## Bảng tra nhanh nút và trạng thái

| Nút / dòng chữ | Ở đâu | Xảy ra chuyện gì |
|---|---|---|
| **Đặt mật khẩu** | Tài khoản → Tài khoản đăng nhập (khi chưa có mật khẩu) | Tạo tài khoản admin và cấp phiên ngay cho bạn |
| **Đổi mật khẩu** | Cùng chỗ, khi đã có mật khẩu | Luôn báo "Đã có tài khoản - hãy đăng nhập." Xem mục C để biết đường vòng |
| **Đăng xuất** | Tài khoản → Tài khoản đăng nhập | Xoá phiên trình duyệt này, tải lại trang |
| **Tắt đăng nhập** | Tài khoản → Tài khoản đăng nhập | Xoá mật khẩu + đăng xuất mọi phiên (hỏi xác nhận trước) |
| **Lưu** | Tài khoản → Workspace | Đổi tên workspace hiển thị |
| 🔒 Đã đặt mật khẩu · tài khoản: ... | Tài khoản đăng nhập | Đang có admin, tên đăng nhập hiện ngay sau dấu hai chấm |
| Chưa đặt mật khẩu - ai mở dashboard cũng dùng được. Đặt mật khẩu nếu đưa lên VPS. | Tài khoản đăng nhập | Chưa có admin |
| ✅ Đã lưu tài khoản. | Tài khoản đăng nhập | Đặt mật khẩu thành công |
| ⚠ Mật khẩu tối thiểu 4 ký tự. | Tài khoản đăng nhập | Giao diện chặn trước khi gửi lên server |
| **Quên mật khẩu?** | Màn đăng nhập | Bấm vào hiện hướng dẫn xoá khối `"auth"` trong `server/settings.json` rồi khởi động lại |

## Mẹo

- **Luôn đặt admin trước khi công khai.** Cách chắc nhất là đặt `JAVIS_ADMIN_USER` + `JAVIS_ADMIN_PASSWORD` khi deploy, khỏi phải đi tìm MÃ THIẾT LẬP.
- **Đặt mật khẩu đủ dài.** Tối thiểu 8 ký tự; dùng cụm dài, khó đoán.
- **Chạy qua HTTPS khi truy cập từ xa.** Dùng tên miền riêng (ví dụ Hostinger `*.hstgr.cloud`) hoặc Cloudflare Tunnel thay vì phơi cổng 7777 thô ra Internet. Cách trỏ tên miền và bật HTTPS xem [Thương hiệu & tên miền riêng](15-thuong-hieu-ten-mien.md).
- **Localhost + tunnel thì bật `JAVIS_REQUIRE_LOGIN=1`.** Khi máy chỉ nghe localhost nhưng bạn mở ra ngoài bằng tunnel, Javis không tự biết là đang public, nên hãy ép login thủ công.
- **MÃ THIẾT LẬP chỉ dùng 1 lần.** Sau khi tạo admin xong, mã tự huỷ. Cần mã mới thì phải khởi động lại server.
- **Sao lưu `.secret_key` cùng `settings.json`.** Thiếu một trong hai là phải nhập lại toàn bộ API key.

## Sự cố thường gặp

**Mở app báo cần MÃ THIẾT LẬP.**
Bạn đang chạy public và chưa có admin. Lấy mã trong state: App terminal (trong container) chạy `cat /data/state/.setup_token`; trên host chạy `docker compose logs javis` rồi tìm dòng có `SETUP TOKEN`. Hoặc đặt `JAVIS_ADMIN_PASSWORD` để khỏi cần mã.

**Bấm Đổi mật khẩu thì báo "Đã có tài khoản - hãy đăng nhập."**
Đúng như thiết kế hiện tại, không phải lỗi máy bạn. Nút đó không đổi được mật khẩu. Làm theo mục C ở trên: máy cá nhân thì Tắt đăng nhập rồi Đặt mật khẩu lại; VPS thì xoá khối `"auth"` trong `settings.json` rồi đặt lại qua `JAVIS_ADMIN_PASSWORD`.

**Nhập đúng user/password nhưng vẫn quay lại màn đăng nhập (kẹt vòng đăng nhập).**
Thường do cookie `secure` bị bật trong khi bạn đang truy cập qua HTTP (nhiều proxy phục vụ HTTP dạng `http://host/PORT/`). Đừng bật `JAVIS_SECURE_COOKIE` trừ khi bạn chắc chắn HTTPS đầu-cuối. Nếu đã lỡ bật, gỡ biến này rồi khởi động lại server.

**Bị báo "Quá nhiều lần sai - thử lại sau ít phút."**
Bạn (hoặc ai đó cùng IP) đã sai mật khẩu quá số lần cho phép. Đợi khoảng 5 phút rồi thử lại. Khởi động lại server cũng xoá bộ đếm này.

**Mọi thao tác đều trả 403 "host không được phép".**
Bạn đang vào Javis bằng một tên miền mà Javis chưa biết, trong lúc chưa đặt mật khẩu. Thêm tên miền đó vào `JAVIS_ALLOWED_HOSTS`, hoặc nhập nó ở **Cài đặt → Tên miền & SSL**, hoặc đơn giản là đặt mật khẩu.

**Thao tác nào cũng báo 403 "cross-origin request bị chặn".**
Bạn đang gọi API Javis từ một trang khác (script, tiện ích, iframe của bên thứ ba). Đây là lớp chống CSRF chặn đúng việc của nó. Nếu đó là công cụ của chính bạn, thêm hostname của nó vào `JAVIS_ALLOWED_HOSTS`.

**Quên mật khẩu.**
Trên Windows, repo có sẵn script **`reset-auth.bat`** ở thư mục gốc dự án: chạy nó là xoá tài khoản/mật khẩu trong `server/settings.json` và đưa app về bộ cài đặt (nó in "OK - da xoa mat khau." rồi hướng dẫn khởi động lại). Nếu không dùng được script: sửa/xoá phần `auth` trong `settings.json` ở thư mục state (Docker: `/data/state`) rồi khởi động lại; hoặc đặt lại admin bằng `JAVIS_ADMIN_PASSWORD` sau khi đã xoá phần `auth` cũ.

**Đổi máy/khôi phục backup xong thì mọi API key trống trơn.**
Bạn chép `settings.json` mà không chép `.secret_key` đi cùng. Không có cách khôi phục: nhập lại key ở trang Models, Kênh và Cài đặt. Lần sau nhớ mang cả hai tệp.

**Tắt đăng nhập rồi mà vẫn bị hỏi tài khoản.**
Vì server vẫn đang public (hoặc `JAVIS_REQUIRE_LOGIN=1`). Ở chế độ này Javis không cho tắt đăng nhập hoàn toàn, mà bắt tạo lại tài khoản. Muốn dùng không mật khẩu thì phải chạy server nghe thuần localhost.

## Liên quan

- [Bắt đầu & thiết lập lần đầu](01-bat-dau-thiet-lap.md) - dựng Javis và tạo admin lần đầu.
- [Thương hiệu & tên miền riêng](15-thuong-hieu-ten-mien.md) - trỏ tên miền và bật HTTPS tự động.
- [Cấu hình .env](16-cau-hinh-env.md) - danh sách biến môi trường bảo mật (`JAVIS_HOST`, `JAVIS_REQUIRE_LOGIN`, `JAVIS_ADMIN_USER/PASSWORD`, `JAVIS_SECURE_COOKIE`, `JAVIS_ALLOWED_HOSTS`, `JAVIS_STATE_DIR`).
- [Plugins](20-plugins.md) - vì sao plugin do bạn cài phải bật riêng bằng biến môi trường.
- [Javis CLI (terminal)](24-cli-terminal.md) - dùng token API để gọi Javis từ máy khác.
- [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md) - các lỗi thường gặp khác.
