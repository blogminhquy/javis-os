# Bảo mật & tài khoản

***Tiếng Việt** · [English](en/14-security-and-accounts.md)*

Trang này giải thích cách Javis OS tự bảo vệ khi bạn đưa nó lên mạng, và cách dùng trang **Tài khoản** trong dashboard để đặt mật khẩu, đăng xuất, tắt đăng nhập và đổi tên workspace.

## Tính năng này là gì

Javis chạy bộ não AI với **toàn quyền trên máy/VPS** của bạn: nó đọc được tệp, chạy lệnh, gọi công cụ. Vì thế nếu để dashboard hở ra Internet mà không có mật khẩu thì bất kỳ ai biết địa chỉ cũng điều khiển được máy của bạn.

Javis xử lý việc này theo 7 lớp:

1. **Tự bắt buộc đăng nhập khi chạy public.** Khi server nghe ra ngoài (không phải chỉ máy này), Javis chặn mọi chức năng cho tới khi bạn đăng nhập. Chạy trên máy cá nhân (localhost) thì không ép, dùng thẳng như cũ.
2. **Đặt admin sớm, rồi bật xác thực 2 lớp.** Màn chạy lần đầu chỉ hỏi tên đăng nhập và mật khẩu, nên trên server public **ai mở link trước khi có admin sẽ tạo được admin**. Đặt sẵn admin qua biến môi trường (hoặc tạo tài khoản ngay sau khi deploy), rồi bật 2FA (TOTP) ở trang **Tài khoản**.
3. **Chống dò mật khẩu.** Sai nhiều lần bị khoá tạm theo địa chỉ IP; mỗi lần sai bị làm chậm.
4. **Chặn trang web lạ sai khiến Javis (CSRF) và chặn tên miền lạ trỏ về máy bạn (DNS-rebinding).** Xem mục riêng bên dưới.
5. **Mã hoá khoá bí mật lưu trong `settings.json`.** API key, token Telegram, token GitHub... không nằm dạng chữ thô trên đĩa.
6. **Token API cho CLI và script, mặc định KHÔNG có cái nào.** Cookie đăng nhập chỉ hợp với trình duyệt; muốn gọi Javis từ terminal thì phải tự tay tạo token, chọn phạm vi, và thu hồi được bất cứ lúc nào. Xem mục riêng bên dưới.
7. **Chặn công cụ tìm kiếm và bot AI.** Lỡ lộ link quản trị ra ngoài thì Google không đưa lên kết quả tìm kiếm, bot AI không đọc được gì, kể cả màn hình đăng nhập. Xem mục riêng bên dưới.

## Mở ở đâu trong Javis

Mọi thao tác tài khoản nằm ở mục **Tài khoản** trong nhóm **Hệ thống** trên thanh nav bên trái. Trang **Cài đặt** có một khối rút gọn làm được ba việc hay dùng nhất (đổi mật khẩu, đăng xuất, tắt đăng nhập) cùng một dòng trạng thái xác thực 2 lớp; bật 2 lớp và xem lịch sử đăng nhập ở tab **Bảo mật** của trang **Tài khoản**. Token API cho CLI và script nằm ở trang **Tích hợp** (nhóm **Việc**), tab **Token API**.

Trang **Tài khoản** có 2 tab.

Tab **Tài khoản**:

- **Workspace**: đổi tên workspace hiển thị.
- **Tài khoản đăng nhập**: đặt mật khẩu, đăng xuất, tắt đăng nhập.

Tab **Bảo mật** (từ bản sau sự cố 09/11/2026):

- **Tổng quan**: 2FA bật hay chưa, số thiết bị đang đăng nhập, lần đăng nhập gần nhất (giờ, IP, thiết bị), số lần đăng nhập sai trong 7 ngày, số token API. Dòng đỏ khi file cài đặt từng bị sửa từ ngoài Javis, dòng vàng khi `JAVIS_ADMIN_PASSWORD` hay `JAVIS_RESET_2FA` còn nằm trong biến môi trường.
- **Xác thực 2 lớp**: bật, tắt, tạo lại mã khôi phục.
- **Thiết bị đang đăng nhập**: mỗi trình duyệt một dòng (thiết bị, IP, lần hoạt động cuối). Đăng xuất từng cái, hoặc bấm **Đăng xuất mọi thiết bị khác** mà không cần đổi mật khẩu.
- **Lịch sử đăng nhập và bảo mật**: mọi lần đăng nhập đúng và sai, đăng xuất, đổi tên hay mật khẩu, bật tắt 2FA, tạo token, đặt lại qua biến môi trường, file cài đặt bị sửa từ ngoài, lần trợ lý AI bị chặn khi định đụng file bí mật. Lọc theo Đăng nhập, Thay đổi, Cảnh báo.

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

Khi mở dashboard lần đầu trên server công khai mà chưa có admin, Javis hiện màn **tạo tài khoản**, chỉ hỏi tên đăng nhập và mật khẩu. Ai mở link trước sẽ tạo được admin, nên đừng để khoảng trống này kéo dài. Có 2 cách:

**Cách 1 - Đặt sẵn admin bằng biến môi trường (khuyến nghị):**

1. Trong cấu hình deploy (ví dụ compose của Hostinger), thêm 2 biến:
   - `JAVIS_ADMIN_PASSWORD` : mật khẩu admin bạn chọn.
   - `JAVIS_ADMIN_USER` : tên đăng nhập (tuỳ chọn, mặc định là `admin`).
2. Khởi động Javis. Lúc boot, Javis tự tạo admin từ 2 biến này và **đóng luôn** màn tạo tài khoản. Bạn mở app là vào thẳng màn đăng nhập.
3. Đăng nhập bằng đúng user/password vừa đặt.

**Cách 2 - Tạo tài khoản ngay sau khi deploy:**

1. Deploy xong là mở dashboard luôn.
2. Ở màn tạo tài khoản nhập: tên tài khoản và mật khẩu (**tối thiểu 8 ký tự**).
3. Bấm nút tạo tài khoản. Javis tạo admin và đăng nhập bạn luôn.

Dù dùng cách nào, sau lần đăng nhập đầu hãy **bật xác thực 2 lớp (2FA)** ở trang **Tài khoản**.

### B. Đặt mật khẩu (khi đang chạy máy cá nhân, chưa có mật khẩu)

Nếu bạn chạy Javis ở nhà mà muốn khoá lại trước khi đưa lên VPS:

1. Vào **Tài khoản** trên thanh nav trái.
2. Ở khối **Tài khoản đăng nhập**, nhập **Tài khoản** (để trống sẽ dùng `admin`).
3. Nhập **Mật khẩu**.
4. Bấm **Đặt mật khẩu**.
5. Javis lưu tài khoản và cấp phiên đăng nhập ngay cho bạn (không tự khoá bạn ra ngoài).

Mật khẩu tối thiểu **8 ký tự**, và giao diện chặn đúng ở con số đó trước khi gửi đi, nên bạn không bấm Lưu xong mới biết mình gõ ngắn.

### C. Đổi mật khẩu / tên đăng nhập

Khi đã có mật khẩu, khối **Tài khoản đăng nhập** hiện dòng "🔒 Đã đặt mật khẩu · tài khoản: <tên của bạn>", thêm ô **Mật khẩu hiện tại**, và nút chuyển nhãn thành **Đổi mật khẩu**.

1. Vào **Tài khoản** trên thanh nav trái (hoặc khối **Tài khoản đăng nhập** trong trang **Cài đặt**, hai chỗ làm được như nhau).
2. Nhập **Mật khẩu hiện tại**. Bắt buộc, kể cả khi bạn đang đăng nhập sẵn: một máy mở dashboard bỏ đó không được phép đổi mật khẩu rồi khoá chính chủ ra ngoài.
3. Nhập **Mật khẩu mới** (từ 8 ký tự). Muốn đổi mỗi tên đăng nhập thì để trống ô này và chỉ sửa ô **Tài khoản**.
4. Bấm **Đổi mật khẩu**.

Đổi xong, **mọi phiên đăng nhập khác bị huỷ** (máy khác, trình duyệt khác, điện thoại) còn máy bạn vừa thao tác được cấp phiên mới ngay nên không bị văng ra. Xác thực 2 lớp và bộ mã khôi phục giữ nguyên, không phải quét lại QR.

Đổi mỗi tên đăng nhập thì các phiên khác vẫn sống, vì mật khẩu chưa đổi.

**Quên mật khẩu hiện tại** thì không có đường vòng nào trong dashboard, phải sửa từ máy chủ.

Chạy bằng Docker/Hostinger (từ 0.77.1): đổi `JAVIS_ADMIN_PASSWORD` (và `JAVIS_ADMIN_USER` nếu muốn) trong ô Environment rồi Redeploy. Lúc khởi động, Javis thấy giá trị env khác lần trước nên đặt lại tài khoản admin theo nó: 2FA giữ nguyên, mọi phiên đăng nhập cũ bị huỷ. Env để nguyên thì không có gì thay đổi, nên mật khẩu bạn đổi trong dashboard không bị env ghi đè mỗi lần khởi động lại.

Cách thủ công (máy không dùng env):

1. Dừng container (hoặc dừng Javis).
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

## Nhật ký bảo mật và báo động

Javis ghi mỗi sự kiện bảo mật thành một dòng trong `security_log.jsonl` ở thư mục state (Docker: `/data/state`), nên nhật ký **còn nguyên sau khi cập nhật hay Redeploy**, khác với log của container. Mỗi dòng có giờ, IP, trình duyệt, tên đăng nhập đã gõ và chi tiết. Không bao giờ ghi mật khẩu, mã 2FA hay token. Đằng sau Caddy hoặc Traefik, IP là địa chỉ thật của người truy cập chứ không phải của proxy.

Các sự kiện sau được **báo ngay cho chủ** (chuông, thông báo đẩy, Telegram của chủ):

- Đăng nhập từ một mạng chưa từng thấy (cùng dải /24 thì không tính là mới, để điện thoại đổi trạm không báo liên tục).
- Đăng nhập bằng mã khôi phục 2FA.
- Đổi tên đăng nhập, đổi mật khẩu, bật hay tắt 2FA, tạo lại mã khôi phục, tạo token API, tắt đăng nhập.
- Tài khoản được tạo hoặc đặt lại từ biến môi trường, 2FA bị gỡ bằng `JAVIS_RESET_2FA`.
- **File cài đặt bị sửa từ bên ngoài Javis** (xem dưới).

### Phát hiện file cài đặt bị sửa từ ngoài

Mỗi lần Javis tự ghi tài khoản (đổi mật khẩu, bật 2FA...), nó lưu một dấu vân tay của khối tài khoản vào `.auth_stamp.json`. Nếu tên đăng nhập, mật khẩu hay 2FA trong `settings.json` đổi mà KHÔNG qua Javis (ai đó vào terminal của máy chủ rồi sửa file), Javis thấy dấu vân tay lệch trong vòng vài giây, **đăng xuất mọi thiết bị**, ghi sự kiện và báo cho chủ. Trước đây sửa file kiểu này không đăng xuất ai, nên chủ máy có thể không hay biết.

Đây là lớp phát hiện, không phải lớp chặn: người đã có quyền ghi file trên máy chủ vẫn sửa được. Nó cho bạn biết NGAY để xử lý theo mục "Khi nghi bị chiếm quyền" bên dưới. Chính bạn sửa file qua SSH (ví dụ gỡ 2FA bằng tay) thì cũng bị đăng xuất một lần, đăng nhập lại là xong.

### Trợ lý AI không được đụng file bí mật

Trợ lý chạy lệnh được bên trong máy chủ và đọc tin nhắn từ bên ngoài (Zalo, Telegram, webhook). Một tin nhắn cài bẫy có thể xúi nó sửa file cài đặt. Vì vậy ở **mọi mức quyền**, Javis từ chối lệnh shell hay lời gọi công cụ chạm vào: `settings.json` trong thư mục state, `.secret_key`, các file phiên đăng nhập và token, nhật ký bảo mật, `~/.claude/.credentials.json`, `~/.codex/auth.json`, `authorized_keys`. Áp dụng cho Claude Code (chặn trước khi công cụ chạy) và terminal của các engine API. Mỗi lần chặn được ghi vào nhật ký. Codex, Grok Build và Antigravity chạy trong sandbox riêng của chúng nên chưa có lớp này.

Lớp này chặn yêu cầu thẳng, không phải bức tường: mã chạy cùng quyền hệ điều hành vẫn có thể ghép đường dẫn từng mảnh. Cần đọc hay sửa các file đó thì dùng trang Tài khoản hoặc terminal thật của máy chủ (SSH, hPanel).

## Khi nghi bị chiếm quyền

Dấu hiệu: tên đăng nhập lạ, mật khẩu đúng mà báo sai, mã 2FA của bạn không còn đúng, báo động "file cài đặt bị sửa từ ngoài", hoặc thiết bị lạ trong tab Bảo mật. Làm theo thứ tự:

1. **Lấy lại tài khoản.** Trên Hostinger: thêm `JAVIS_ADMIN_USER` và `JAVIS_ADMIN_PASSWORD` (mật khẩu MỚI) vào ô Environment rồi Redeploy. Javis đặt lại tài khoản, giữ 2FA và đăng xuất mọi phiên cũ.
2. **2FA không phải của bạn?** Thêm `JAVIS_RESET_2FA=1` cùng lúc ở bước 1. Javis gỡ 2FA đúng một lần khi khởi động. Biến chỉ có tác dụng một lần cho mỗi giá trị; lần sau cần lại thì đặt giá trị khác, ví dụ ngày hôm đó (`JAVIS_RESET_2FA=2026-11-09`).
3. **Đăng nhập, mở Tài khoản > Bảo mật.** Xem lịch sử đăng nhập (IP, thiết bị, giờ) và bấm **Đăng xuất mọi thiết bị khác**.
4. **Bật lại 2FA** bằng điện thoại của bạn, cất 8 mã khôi phục vào nơi an toàn.
5. **Xoá `JAVIS_ADMIN_PASSWORD` và `JAVIS_RESET_2FA` khỏi ô Environment** rồi Redeploy. Tài khoản không bị ảnh hưởng. Mật khẩu nằm ở ô đó dạng chữ thường nên đừng để lâu.
6. **Tìm đường vào của kẻ lạ.** Người sửa được file cài đặt đã vào được máy chủ: kiểm tra SSH key lạ (`cat /root/.ssh/authorized_keys`), đổi mật khẩu root (`passwd`), đổi mật khẩu và bật 2FA cho tài khoản Hostinger, chặn cổng 7777 ở tường lửa nếu đã có tên miền HTTPS.
7. **Đổi các khoá kết nối** lưu trong Javis (POS, Cloudflare, Gmail, Zalo, API key), ưu tiên cái chạm tới tiền và dữ liệu khách: người vào được máy chủ có thể đã đọc chúng.
8. **Rà xem có để lại gì không**: việc định kỳ, nhắc hẹn, agent, plugin, MCP lạ; trên máy chủ chạy `crontab -l`.

Từ bản này, compose Hostinger tự đóng cổng 7777 ra Internet khi đã đặt `DOMAIN_NAME` (chỉ còn HTTPS qua tên miền). Chưa đặt tên miền thì cổng vẫn mở như cũ vì đó là đường vào duy nhất.

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

## Chặn công cụ tìm kiếm và bot AI

Lớp này cũng chạy ngầm, không cần bật. Nó dành cho lúc đường link quản trị lộ ra ngoài: dán nhầm vào nhóm chat, nằm trong nhật ký chứng chỉ SSL công khai, hay bị máy quét Internet tìm thấy. Khi đó Google không đưa trang lên kết quả tìm kiếm, và bot AI không đọc được gì, kể cả màn hình đăng nhập.

| Lớp | Làm gì |
|---|---|
| Header `X-Robots-Tag: noindex` | Gắn vào MỌI câu trả lời của Javis (trang đăng nhập, link chia sẻ, trang lỗi), nên trang nào lỡ bị công cụ tìm kiếm ghé cũng bị loại khỏi kết quả. |
| `/robots.txt` | Cấm bot AI (GPTBot, ClaudeBot, PerplexityBot, CCBot...), công cụ SEO và mọi bot lạ đọc bất cứ thứ gì. |
| Trả 403 | Request tự xưng là bot AI, máy tìm kiếm, công cụ SEO, máy quét (Shodan, Censys) hoặc ký tên bot (`Signature-Agent`) nhận 403, không thấy chữ nào của trang. |

Không bị chặn: trình duyệt của người thật (kể cả trình duyệt trong Zalo, Facebook, Cốc Cốc), khung xem trước khi dán link vào Zalo, Telegram, Facebook, Slack, Discord, webhook và cửa OAuth của dịch vụ bên ngoài, Javis Gate (ChatGPT và Claude gọi vào Javis), CLI, `curl` và các công cụ chạy ngay trên máy này.

Vì sao `robots.txt` không cấm Google: Google chỉ gỡ được trang mà nó đọc được. Bị cấm trong `robots.txt` thì Google không đọc, không thấy `noindex`, và vẫn có thể hiện link trần trong kết quả nếu chỗ khác trỏ tới. Cho Google ghé rồi trả 403 kèm `noindex` mới gỡ hẳn link khỏi kết quả.

Kiểm tra nhanh trên máy chủ của bạn (đổi tên miền):

```bash
curl -s -o /dev/null -w "%{http_code}\n" -A GPTBot https://ten-mien-cua-ban/
```

Phải ra `403`. Mở bằng trình duyệt thì vẫn vào bình thường.

Lớp này chỉ bắt bot TỰ KHAI tên. Bot giả làm Chrome thì vẫn chỉ thấy màn hình đăng nhập, nên mật khẩu và 2FA vẫn là lớp bảo vệ chính. Một dịch vụ bạn dùng bị chặn nhầm vì tên trùng danh sách thì đặt `JAVIS_BLOCK_BOTS=0` rồi khởi động lại: chỉ lớp 403 tắt, header `noindex` và `robots.txt` vẫn giữ.

## Token API - cửa cho CLI và script

Cookie đăng nhập chỉ hợp với trình duyệt. Khi bạn muốn [Javis CLI](24-cli-terminal.md) hay một script gọi được Javis, cần một credential khác: **token API**, tạo ở **Tích hợp > Token API (cho CLI)** (nhóm Việc, cùng trang với webhook: cả hai đều là cửa để chương trình khác gọi vào Javis).

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
| Chặn bot | `noindex` trên mọi câu trả lời, `/robots.txt`, và 403 cho bot AI, máy tìm kiếm, công cụ SEO, máy quét tự khai tên (xem mục riêng ở trên). |
| Secret trên đĩa | API key và token trong `settings.json` mã hoá Fernet bằng `.secret_key` trong thư mục state. |

Về cookie `secure`: mặc định Javis **không** ép cookie `secure` để chạy được cả HTTP lẫn HTTPS (tránh kẹt vòng đăng nhập sau proxy HTTP như đường dẫn dạng `http://host/PORT/`). Nếu bạn chắc chắn chạy HTTPS đầu-cuối, bật `JAVIS_SECURE_COOKIE=1` trong biến môi trường (xem [Cấu hình .env](16-cau-hinh-env.md)). Truy cập qua đúng tên miền riêng thì Javis tự bật `secure` mà không cần đặt biến này (dựa vào Host khớp tên miền, không suy từ `X-Forwarded-Proto`).

## Bảng tra nhanh nút và trạng thái

| Nút / dòng chữ | Ở đâu | Xảy ra chuyện gì |
|---|---|---|
| **Đặt mật khẩu** | Tài khoản → Tài khoản đăng nhập (khi chưa có mật khẩu) | Tạo tài khoản admin và cấp phiên ngay cho bạn |
| **Đổi mật khẩu** | Cùng chỗ, khi đã có mật khẩu | Đổi mật khẩu và/hoặc tên đăng nhập. Phải nhập mật khẩu hiện tại; đổi xong mọi phiên khác bị đăng xuất |
| **Đăng xuất** | Tài khoản → Tài khoản đăng nhập | Xoá phiên trình duyệt này, tải lại trang |
| **Tắt đăng nhập** | Tài khoản → Tài khoản đăng nhập | Xoá mật khẩu + đăng xuất mọi phiên (hỏi xác nhận trước) |
| **Lưu** | Tài khoản → Workspace | Đổi tên workspace hiển thị |
| 🔒 Đã đặt mật khẩu · tài khoản: ... | Tài khoản đăng nhập | Đang có admin, tên đăng nhập hiện ngay sau dấu hai chấm |
| Chưa đặt mật khẩu - ai mở dashboard cũng dùng được. Đặt mật khẩu nếu đưa lên VPS. | Tài khoản đăng nhập | Chưa có admin |
| ✅ Đã lưu tài khoản. | Tài khoản đăng nhập | Đặt mật khẩu thành công |
| ⚠ Mật khẩu tối thiểu 8 ký tự. | Tài khoản đăng nhập | Giao diện chặn trước khi gửi lên server, cùng ngưỡng với server |
| ⚠ Sai mật khẩu hiện tại. | Tài khoản đăng nhập | Ô **Mật khẩu hiện tại** gõ sai, không có gì bị đổi |
| **Quên mật khẩu?** | Màn đăng nhập | Bấm vào hiện hướng dẫn xoá khối `"auth"` trong `server/settings.json` rồi khởi động lại |

## Mẹo

- **Luôn đặt admin trước khi công khai.** Cách chắc nhất là đặt `JAVIS_ADMIN_USER` + `JAVIS_ADMIN_PASSWORD` khi deploy, để server không có lúc nào trống admin.
- **Đặt mật khẩu đủ dài.** Tối thiểu 8 ký tự; dùng cụm dài, khó đoán.
- **Chạy qua HTTPS khi truy cập từ xa.** Dùng tên miền riêng (ví dụ Hostinger `*.hstgr.cloud`) hoặc Cloudflare Tunnel thay vì phơi cổng 7777 thô ra Internet. Cách trỏ tên miền và bật HTTPS xem [Thương hiệu & tên miền riêng](15-thuong-hieu-ten-mien.md).
- **Localhost + tunnel tự chạy thì bật `JAVIS_REQUIRE_LOGIN=1`.** Khi máy chỉ nghe localhost nhưng bạn tự chạy tunnel (cloudflared, ngrok...) bên ngoài Javis, Javis không tự biết là đang public, nên hãy ép login thủ công. Dùng mục **Truy cập từ xa** trong Cài đặt thì không cần: Javis biết tunnel đang bật, tự bắt đăng nhập và chỉ chạy khi đã có mật khẩu.
- **Bật xác thực 2 lớp (2FA) ngay sau lần đăng nhập đầu.** Lộ mật khẩu thì kẻ lạ vẫn thiếu mã TOTP trên điện thoại bạn.
- **Sao lưu `.secret_key` cùng `settings.json`.** Thiếu một trong hai là phải nhập lại toàn bộ API key.

## Sự cố thường gặp

**Bấm Đổi mật khẩu thì báo "Đã có tài khoản - hãy đăng nhập."**
Lỗi của các bản trước 0.28.3, đã sửa. Trang đang mở còn giữ bản cũ trong bộ nhớ đệm trình duyệt thì tải lại bằng Ctrl+F5 (máy Mac là Cmd+Shift+R) rồi làm lại theo mục C.

**Đổi mật khẩu xong thì điện thoại (hoặc máy khác) đòi đăng nhập lại.**
Đúng như thiết kế. Đổi mật khẩu huỷ mọi phiên cũ để người đang mượn máy bạn không dùng tiếp được; đăng nhập lại bằng mật khẩu mới là xong.

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
