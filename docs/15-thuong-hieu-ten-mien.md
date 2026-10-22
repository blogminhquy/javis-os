# Thương hiệu & tên miền riêng

***Tiếng Việt** · [English](en/15-branding-and-domains.md)*

Trang này hướng dẫn hai việc: đổi logo/avatar của Javis thành ảnh của bạn, và trỏ một tên miền riêng (ví dụ `javis.tencuaban.com`) vào Javis để chạy qua HTTPS. Các thao tác nằm trong **Cài đặt → Chung**.

## Tính năng này là gì

- **Ảnh đại diện (logo/avatar):** thay ảnh JAVIS OS mặc định bằng ảnh của bạn. Ảnh mới hiện ngay ở góc trên bên trái, ở thanh bên, ở màn hình đăng nhập, ở cửa sổ chào mừng, và làm luôn icon tab trình duyệt (favicon).
- **Tên miền riêng (HTTPS):** thay vì mở Javis bằng địa chỉ IP kèm cổng (kiểu `http://12.34.56.78:7777`), bạn dùng một tên miền dễ nhớ và có khóa an toàn HTTPS. Javis tự cấp chứng chỉ HTTPS (cơ chế On-Demand TLS qua Caddy), và có nút **Bật SSL** để chủ động xin chứng chỉ ngay thay vì ngồi đợi.

Lưu ý quan trọng ngay từ đầu: phần **Tên miền riêng** chỉ hoạt động khi bạn deploy Javis bằng Docker trên VPS và đã mở cổng 80/443. Nếu bạn chạy Javis trên máy cá nhân (Windows, macOS), hãy dùng mục **Truy cập từ xa** ngay bên dưới: Javis tự dựng Cloudflare Tunnel, có HTTPS và cả tên miền riêng mà không cần VPS. Xem [Truy cập từ xa trên máy Windows hoặc macOS](#truy-cập-từ-xa-trên-máy-windows-hoặc-macos). Chi tiết deploy xem [Cấu hình .env](16-cau-hinh-env.md) và file `DEPLOY.md` trong thư mục dự án.

## Mở ở đâu trong Javis

Cả hai tính năng nằm trong **Cài đặt → Chung**. Trong tab Chung có hai thẻ:

- Ô **ẢNH ĐẠI DIỆN**: có ảnh xem trước, nút **Tải ảnh lên** và nút **Khôi phục mặc định**.
- Ô **TÊN MIỀN & SSL**: có ô nhập (chỗ trống ghi "vd: javis.tencuaban.com"), nút **Lưu & kiểm tra**, hai badge trạng thái DNS và SSL, hai nút **Bật SSL** và **Kiểm tra lại**, cùng wizard ba bước đổi nội dung theo đúng môi trường VPS/Hostinger.

Mỗi lần mở Cài đặt, Javis tự nạp lại giá trị đang dùng, kiểm tra DNS/HTTPS và đưa ra đúng bước tiếp theo.

## Đổi logo/avatar (từng bước)

1. Mở **Cài đặt → Chung**, tìm ô **ẢNH ĐẠI DIỆN**.
2. Bấm nút **Tải ảnh lên**. Cửa sổ chọn tệp của máy hiện ra.
3. Chọn một tệp ảnh. Định dạng nhận: PNG, JPG, WEBP, GIF. Dung lượng tối đa 5MB.
4. Sau khi chọn, Javis hiện dòng trạng thái **Đang tải lên…** rồi **Đã cập nhật ảnh ✓** khi xong. Ảnh mới thay ngay ở tất cả vị trí (góc trên, thanh bên, màn đăng nhập, ô xem trước) mà không cần tải lại trang.

Riêng icon tab trình duyệt (favicon) đổi chậm hơn một nhịp: Javis phục vụ nó với bộ nhớ đệm 5 phút, và trình duyệt còn giữ icon rất lì. Muốn thấy ngay thì mở lại tab hoặc tải lại trang bỏ qua cache.

### Khôi phục ảnh mặc định

1. Trong ô **ẢNH ĐẠI DIỆN**, bấm nút **Khôi phục mặc định**.
2. Javis hiện **Đang khôi phục…** rồi **Đã về ảnh mặc định.** Logo trở lại ảnh gốc của hệ thống.

### Thông báo trạng thái ảnh có thể gặp

| Thông báo | Ý nghĩa |
|---|---|
| Đang dùng ảnh tùy chỉnh. | Bạn đã tải ảnh riêng lên và Javis đang dùng nó. |
| Đang dùng ảnh mặc định. | Chưa tải ảnh riêng, hoặc đã khôi phục về mặc định. |
| Đang tải lên… | Đang gửi ảnh lên server. |
| Đã cập nhật ảnh ✓ | Ảnh mới đã được nhận và áp dụng. |
| Đang khôi phục… | Đang gỡ ảnh tuỳ chỉnh. |
| Đã về ảnh mặc định. | Đã gỡ xong, đang dùng lại ảnh gốc. |
| Tải lên thất bại | Server từ chối tệp (sai định dạng, quá lớn hoặc rỗng). Lý do cụ thể hiện thay cho dòng này khi server có gửi kèm. |
| Lỗi mạng khi tải lên | Mất kết nối giữa chừng, thử lại. |
| Không khôi phục được | Không gỡ được ảnh tuỳ chỉnh, thử lại. |

## Trỏ tên miền riêng và bật HTTPS (từng bước)

Phần này giả định bạn đã deploy Javis bằng Docker trên VPS, đã bật Caddy (On-Demand TLS) và mở cổng 80/443. Nếu chưa, làm phần deploy trước theo `DEPLOY.md`.

### Bước A: nhập và lưu tên miền

1. Mở **Cài đặt → Chung**, tìm ô **TÊN MIỀN & SSL**.
2. Nhập tên miền (hoặc tên miền con) bạn muốn dùng vào ô, ví dụ `javis.tencuaban.com`. Không cần gõ `https://`; nếu có gõ, Javis tự bỏ.
3. Bấm nút **Lưu & kiểm tra** (hoặc nhấn Enter trong ô nhập). Javis hiện **Đang lưu và kiểm tra…**, lưu tên miền, rồi tự chạy kiểm tra DNS/SSL và vẽ wizard ba bước ngay trên UI.
4. Nếu tên miền sai định dạng, Javis báo: **Tên miền không hợp lệ (vd: javis.tencuaban.com)**. Sửa lại rồi lưu tiếp.

Muốn **xóa** tên miền: xóa trống ô nhập rồi bấm **Lưu & kiểm tra**. Javis báo **Đã xoá tên miền.** và ẩn phần hướng dẫn.

### Bước B: tạo bản ghi DNS theo hướng dẫn

Sau khi lưu (hoặc khi bấm **Kiểm tra lại**), wizard hiện bước **2. Trỏ DNS về VPS** kèm bản ghi cần tạo và nút **Sao chép bản ghi**. Bản ghi hiện dưới dạng một dòng gọn `A · <tên miền> · <IP máy chủ>`:

1. Vào trang quản lý tên miền của nhà cung cấp (nơi bạn mua domain) và tạo một bản ghi:

   | Trường | Giá trị |
   |---|---|
   | Loại (Type) | A |
   | Tên (Name/Host) | tên miền bạn vừa nhập, ví dụ `javis.tencuaban.com` |
   | Trỏ tới (Value/Points to) | địa chỉ IP máy chủ VPS của bạn (Javis tự dò và điền sẵn IP này trong wizard) |

2. Đợi DNS lan (vài phút đến vài giờ), bấm **Kiểm tra lại**. Khi DNS đúng, bước 2 chuyển sang dấu ✓ và dòng mô tả đổi thành "Bản ghi A đã trỏ đúng IP máy chủ."

### Bước C: bấm Bật SSL để xin chứng chỉ

Khi bước 2 đã ✓, wizard hiện bước **3. Bật HTTPS** với dòng "Khi DNS đã đúng, bấm Bật SSL để Javis xin chứng chỉ."

1. Bấm nút **Bật SSL**. Javis hiện **Đang bật SSL và xin chứng chỉ… (có thể mất khoảng 10 giây)**.
2. Server lưu ý định bật SSL rồi tự mở `https://<tên miền>/health` từ chính nó. Chính cú gọi này buộc Caddy đi xin chứng chỉ ở lần đầu, thay vì bạn phải mở trình duyệt thủ công.
3. Xong, Javis chạy lại kiểm tra và cập nhật badge. Khi chứng chỉ đã sống, dòng trạng thái ghi **HTTPS đang chạy cho `<tên miền>`.**, nút đổi nhãn thành **Kích hoạt lại**, và wizard hiện thêm liên kết **Mở https://`<tên miền>` ↗**.
4. Nếu chưa lên, Javis nói rõ lý do và bổ sung câu **"Chạy trên VPS: docker compose -f docker-compose.yml -f docker-compose.https.yml up -d"** khi bạn đang chạy bản Docker mà chưa bật lớp HTTPS.

Nút **Kiểm tra lại** dùng được bất cứ lúc nào: nó chỉ đọc trạng thái (hiện **Đang kiểm tra…** rồi vẽ lại badge), không đụng chứng chỉ.

Trên Hostinger, nút **Bật SSL** bị ẩn đi, vì Traefik của hPanel mới là bên cấp chứng chỉ. Xem mục Hostinger bên dưới.

## Truy cập từ xa trên máy Windows hoặc macOS

Mục **TRUY CẬP TỪ XA** (Cài đặt, ngay dưới Tên miền & SSL) mở Javis ra Internet qua **Cloudflare Tunnel** (hoặc riêng tư qua **Tailscale**, xem Cách 3) mà không cần VPS, không mở cổng modem, không gõ lệnh. Javis tự tải `cloudflared` (công cụ chính thức, miễn phí của Cloudflare) đúng bản cho máy (Windows x64/ARM, macOS Intel/Apple Silicon, Linux), chạy nó cùng Javis và tự nối lại khi rớt mạng. Có HTTPS nên micro và giọng nói chạy được trên điện thoại.

**Bắt buộc đặt mật khẩu đăng nhập trước** (mục Tài khoản đăng nhập). Khi tunnel đang bật, Javis luôn đòi đăng nhập và không cho tắt đăng nhập. Nếu mật khẩu bị xoá (ví dụ chạy `reset-auth`), tunnel tự dừng trong vài giây.

### Cách 1: Link nhanh (không cần tài khoản)

1. Chọn **Link nhanh**, bấm **Bật truy cập từ xa**.
2. Lần đầu Javis tải `cloudflared` (khoảng 40 MB), rồi hiện link dạng `https://ba-tu-ngau-nhien.trycloudflare.com`.
3. Mở link đó trên điện thoại, đăng nhập bằng mật khẩu.

Link này **đổi mỗi lần Javis khởi động lại**, hợp để thử hoặc dùng tạm.

### Cách 2: Tên miền riêng (link cố định)

Cần một tài khoản Cloudflare miễn phí và một tên miền đang dùng DNS của Cloudflare.

1. Vào [one.dash.cloudflare.com](https://one.dash.cloudflare.com), mục **Networks**, chọn **Tunnels**, bấm **Create a tunnel**, chọn **Cloudflared**, đặt tên.
2. Ở bước cài connector, bấm sao chép dòng lệnh (bản Windows hay Mac đều được). **Không cần chạy lệnh đó**, chỉ cần dán nguyên dòng vào ô **Token tunnel Cloudflare** trong Javis. Javis tự lấy token ra.
3. Sang bước **Public Hostname**: chọn tên miền con (ví dụ `javis.tencuaban.com`), Service chọn **HTTP**, ô URL điền địa chỉ dịch vụ Javis hiện ra (mặc định `127.0.0.1:7777`, có nút sao chép).
4. Quay lại Javis, chọn **Tên miền riêng**, bấm **Bật truy cập từ xa**. Khi trạng thái là **Đang chạy**, Javis đọc tên miền bạn vừa đặt và hiện link `https://javis.tencuaban.com`.

Token được mã hoá khi lưu, không bao giờ gửi ngược ra trình duyệt, và đưa cho `cloudflared` qua biến môi trường chứ không nằm trên dòng lệnh.

### Cách 3: Tailscale (riêng tư, chỉ máy của bạn)

Hợp khi chỉ mình bạn dùng: link không lộ ra Internet, chỉ máy đã cài Tailscale và đăng nhập cùng tài khoản mới mở được. Javis không tự cài Tailscale (nó cần quyền hệ thống và đăng nhập tài khoản), nhưng lo phần còn lại.

1. Cài [Tailscale](https://tailscale.com/download) trên máy chạy Javis và trên điện thoại, đăng nhập cùng một tài khoản.
2. Trong Javis chọn **Tailscale**, bấm **Bật truy cập từ xa**. Javis tự chạy `tailscale serve`, không cần gõ lệnh.
3. Lần đầu, Tailscale có thể đòi bật HTTPS cho mạng của bạn: Javis hiện link **Mở trang bật HTTPS**, bấm vào rồi bấm **Enable**. Javis tự thử lại.
4. Mở link `https://ten-may.ten-mang.ts.net` trên điện thoại đang bật Tailscale.

Link Tailscale vẫn chạy khi Javis khởi động lại; bấm **Tắt** thì Javis gỡ đúng phần nó đã thêm, không đụng các cấu hình Tailscale khác của bạn. Người ngoài mạng Tailscale của bạn không mở được link này, nên nó không dùng cho link chia sẻ hay webhook từ dịch vụ bên ngoài; những việc đó dùng Cách 1 hoặc Cách 2.

### Nên biết

- Máy tắt hoặc ngủ thì link cũng tắt. Muốn mở 24/7, tắt chế độ Sleep (Windows) hoặc bật "Prevent automatic sleeping" (macOS).
- Javis bật lại tunnel sau khi khởi động lại hoặc cập nhật, nếu lần trước bạn để nó bật.
- Nếu Javis báo Cloudflare đang trỏ tới một địa chỉ khác, sửa URL dịch vụ trong Public Hostname thành đúng địa chỉ Javis hiện.
- Bản Docker trên VPS vẫn có thể dùng cách cũ (`docker compose --profile tunnel`) trong `DEPLOY.md`.

## Bảng tra nhanh nút và trạng thái

Hai badge nằm ngay dưới ô nhập tên miền:

| Badge DNS | Nghĩa là |
|---|---|
| DNS: đang kiểm tra | Chưa có kết quả (vừa mở trang) |
| DNS: đã trỏ đúng | Bản ghi A khớp IP máy chủ |
| DNS: sai IP (`<ip>`) | Có bản ghi nhưng trỏ về IP khác, IP thật hiện trong ngoặc |
| DNS: chưa trỏ | Không tra được bản ghi nào cho tên miền |

| Badge SSL | Nghĩa là |
|---|---|
| SSL: đang kiểm tra | Chưa có kết quả |
| SSL: đang bật | HTTPS đã chạy thật cho tên miền |
| SSL: qua Hostinger | Đang deploy trên Hostinger, chứng chỉ do Traefik của hPanel lo |
| SSL: đang chờ | Bạn đã bật SSL nhưng chứng chỉ chưa sống |
| SSL: tắt | Chưa bật SSL cho tên miền này |

| Nút | Xảy ra chuyện gì |
|---|---|
| **Lưu & kiểm tra** | Lưu tên miền vào Javis rồi tự chạy kiểm tra DNS/SSL |
| **Bật SSL** | Lưu ý định bật SSL và chủ động buộc Caddy xin chứng chỉ ngay |
| **Kích hoạt lại** | Cùng nút trên, đổi nhãn khi HTTPS đã chạy; bấm để xin lại chứng chỉ |
| **Kiểm tra lại** | Chỉ đọc trạng thái DNS/SSL, không đụng chứng chỉ |
| **Sao chép bản ghi** | Chép dòng `A · <tên miền> · <IP>` vào clipboard (đổi thành "Đã sao chép ✓" khoảng 1 giây) |
| **Sao chép biến** | Chỉ có ở wizard Hostinger: chép dòng `DOMAIN_NAME=<tên miền>` |

Dòng trạng thái dưới cùng của card có thể là:

| Dòng trạng thái | Ý nghĩa | Việc cần làm |
|---|---|---|
| Chưa đặt tên miền. | Chưa lưu tên miền nào. | Nhập tên miền rồi bấm Lưu & kiểm tra. |
| Đang lưu và kiểm tra… / Đang kiểm tra… | Đang chạy, chờ chút. | Không phải làm gì. |
| Đã lưu. Đang kiểm tra DNS/SSL… | Đã ghi tên miền, đang tra DNS. | Chờ kết quả. |
| Đã xoá tên miền. | Bạn vừa lưu ô trống. | Không phải làm gì. |
| HTTPS đang chạy cho `<tên miền>`. | Xong xuôi. | Không cần làm gì thêm. |
| Bạn đang mở qua HTTPS | Bạn đang truy cập chính tên miền đó bằng HTTPS. | Xong. |
| Chứng chỉ chưa hợp lệ - DNS chưa trỏ đúng hoặc chứng chỉ chưa cấp xong | Kết nối được nhưng chứng chỉ chưa dùng được. | Kiểm tra badge DNS; nếu DNS đúng thì đợi thêm rồi bấm Bật SSL lần nữa. |
| Không kết nối được cổng 443 - Caddy/HTTPS chưa chạy, hoặc cổng 80/443 bị proxy khác chiếm | Không ai trả lời ở cổng 443. | Bật lớp HTTPS theo lệnh Javis gợi ý, và kiểm tra cổng 80/443 có bị dịch vụ khác chiếm không. |
| Đã lưu trong Javis; còn bước đặt DOMAIN_NAME và Redeploy trên Hostinger. | Hostinger: route Traefik chưa khớp tên miền. | Làm bước 3 của wizard Hostinger. |
| Hãy nhập và lưu tên miền trước. | Bấm Bật SSL khi ô tên miền còn trống. | Nhập tên miền rồi lưu. |
| Tên miền không hợp lệ (vd: javis.tencuaban.com) | Chuỗi nhập không đúng dạng tên miền. | Bỏ khoảng trắng, bỏ đường dẫn phía sau, gõ dạng `ten.tencuaban.com`. |
| Bật SSL thất bại | Server từ chối bật. | Đọc thêm dòng lý do đi kèm. |
| Không kiểm tra được (lỗi mạng). | Trình duyệt không gọi được server. | Thử lại sau ít phút. |
| Lỗi mạng khi lưu / Lỗi mạng khi bật SSL | Mất kết nối giữa chừng. | Thử lại. |

## Về Caddy và On-Demand TLS (nên biết)

- Javis dùng Caddy để tự xin và tự gia hạn chứng chỉ HTTPS (Let's Encrypt) theo cơ chế On-Demand TLS. Bạn không phải tự cài chứng chỉ.
- Để chống lạm dụng, trước khi cấp chứng chỉ Caddy hỏi Javis (qua cổng gác nội bộ `/tls-check`) và chỉ cấp cho đúng tên miền bạn đã nhập trong app. Người lạ trỏ DNS bừa vào IP máy chủ sẽ không ép được server xin chứng chỉ lung tung.
- Khi đổi hoặc xóa tên miền trên VPS dùng Caddy, bạn chỉ cần sửa trong ô **TÊN MIỀN & SSL** rồi bấm **Lưu & kiểm tra**, sau đó **Bật SSL** cho tên miền mới. Hostinger cần Redeploy khi đổi route Traefik.
- Việc bật Caddy (chạy lệnh `docker compose ... up -d` với file cấu hình HTTPS) và mở cổng 80/443 là bước deploy hạ tầng, nằm ngoài giao diện này. Xem hướng dẫn deploy chi tiết trong `DEPLOY.md` của dự án.
- Khi bạn vào Javis đúng bằng tên miền riêng qua HTTPS, server tự đánh dấu cookie đăng nhập là `secure`, khỏi phải đặt `JAVIS_SECURE_COOKIE` thủ công. Xem [Bảo mật & tài khoản](14-bao-mat-tai-khoan.md).

## Nếu bạn deploy trên Hostinger (khác cách trên)

> 🛒 Chưa có VPS Hostinger? [Đăng ký tại đây](https://www.hostinger.com?REFERRALCODE=UTRBLOGMIDSN).

Hostinger VPS đã cài sẵn reverse proxy Traefik lo SSL, và cổng 80/443 đã bị Traefik chiếm. Javis vẫn cho nhập tên miền, kiểm tra DNS và tạo sẵn biến cần dùng ngay trên UI, nhưng container không có quyền sửa route Traefik của hPanel. Vì thế nút **Bật SSL** bị ẩn, badge SSL ghi **SSL: qua Hostinger**, và bước 3 của wizard đổi thành **3. Kích hoạt route HTTPS trên Hostinger**:

1. Trỏ DNS: bản ghi `A  <tên miền của bạn> → <IP VPS Hostinger>`.
2. Deploy bằng file compose có nhãn Traefik của Hostinger: `docker-compose.hostinger.yml` (Docker Manager → Compose → URL).
3. Bấm **Sao chép biến** trong wizard, đặt `DOMAIN_NAME=<tên miền của bạn>` trong Docker Manager rồi bấm **Redeploy**. Wizard hiện luôn route Traefik hiện tại để bạn đối chiếu.
4. Mở `https://<tên miền>`; Traefik tự xin chứng chỉ ở lần đầu. Không còn phải vào bằng `:7777`.

Nếu bạn cố bấm Bật SSL trên Hostinger (ví dụ qua API), Javis từ chối và nói rõ: Hostinger quản lý HTTPS bằng Traefik, hãy đặt `DOMAIN_NAME` trong Docker Manager rồi Redeploy.

Sau khi Redeploy, trở lại Cài đặt và bấm **Kiểm tra lại**. Chi tiết và xử lý sự cố xem mục "Tên miền + HTTPS trên Hostinger" trong `DEPLOY.md`; hai link tài liệu cũng nằm ngay dưới card tên miền.

### Badge SSL nói gì (từ 0.248.0)

Mỗi lần Kiểm tra lại, Javis tự mở `https://<tên miền>` từ chính máy chủ và xem ai trả lời, rồi ghi đúng bước đang hỏng lên badge:

- **SSL: đang bật**: xong, mở link là vào được.
- **SSL: Hostinger chưa nhận tên miền**: DNS đã tới VPS nhưng Traefik chưa có đường cho tên miền này. Dòng `traefik...rule=Host(...)` của dự án vẫn là tên cũ: đặt `DOMAIN_NAME` đúng tên miền (hoặc sửa thẳng dòng `Host` trong YAML) rồi **Redeploy**. Đây là ca hay gặp nhất: đã nhập tên miền trong Javis và trỏ DNS, nhưng chưa Redeploy với tên miền mới.
- **SSL: đang chờ cấp chứng chỉ**: đường đã thông tới Javis, Let's Encrypt chưa cấp xong. Đợi vài phút rồi Kiểm tra lại.
- **SSL: proxy không gọi được Javis**: Traefik báo 502, kiểm tra container Javis có đang chạy.
- **SSL: tên miền mở nhầm trang khác**: tên miền đang trỏ vào một trang khác hoặc một bản Javis khác (ví dụ stack thứ hai trên cùng VPS).
- **SSL: không kết nối được cổng 443**: không có gì trả lời ở cổng HTTPS của VPS.

Nếu bạn sửa thẳng dòng `Host(...)` trong YAML thay vì đặt `DOMAIN_NAME`, Javis không còn báo "còn bước Redeploy" khi tên miền đã chạy HTTPS.

## Theme riêng cho người vận hành (CSS)

Ai triển khai Javis cho khách (white-label) có thể đặt một file `theme.css` vào thư mục
`branding/` trong thư mục dữ liệu của Javis (cạnh logo đã tải lên; Docker là
`/data/state/branding/theme.css`). Có file này thì mọi trang dashboard tải nó SAU các file CSS
gốc, nên nó đè được màu, font, bo góc. File nằm ngoài mã nguồn nên sống qua mọi lần cập nhật.
Xoá file là về giao diện gốc. Trần 512 KB.

- **Màu ở chế độ sáng:** biến màu của chế độ sáng khai trong `:root[data-theme="light"]`, đặc
  hơn `:root`. Muốn đổi màu cho cả hai chế độ thì khai cả hai khối, ví dụ
  `:root{--accent:#e4572e}` và `:root[data-theme="light"]{--accent:#e4572e}`.
- **Chế độ mặc định:** thêm dòng `/* javis-default-mode: light */` (hoặc `dark`, `auto`) trong
  4 KB đầu file để chọn sáng/tối cho thiết bị chưa từng tự chọn. Người dùng đã tự chọn thì giữ
  lựa chọn của họ.

## Mẹo

- Ảnh logo nên là ảnh vuông (tỉ lệ 1:1) để không bị cắt méo, vì Javis hiển thị logo trong khung vuông bo góc.
- Sau khi tải ảnh mới mà chỗ nào đó vẫn còn ảnh cũ, chờ khoảng 1 phút hoặc tải lại trang; hệ thống có bộ nhớ đệm ngắn cho ảnh logo (favicon lâu hơn, khoảng 5 phút).
- Nếu chưa có VPS hay tên miền riêng mà vẫn muốn truy cập từ xa có HTTPS, dùng mục **Truy cập từ xa** (xem phần trên).
- Dùng đúng bản ghi loại **A** (trỏ theo IPv4). Đừng dùng CNAME cho tên miền này trừ khi bạn hiểu rõ hệ quả.
- Đừng bấm **Bật SSL** liên tục khi DNS chưa đúng. Mỗi lần bấm là một lần Javis buộc Caddy đi xin chứng chỉ, xin hỏng nhiều lần sẽ chạm giới hạn của Let's Encrypt.

## Sự cố thường gặp

- **Bấm Lưu báo "Tên miền không hợp lệ":** kiểm tra lại chính tả, không có khoảng trắng, không kèm đường dẫn phía sau. Định dạng đúng là dạng `tên.tencuaban.com`.
- **Đã tạo bản ghi A nhưng badge vẫn ghi "DNS: chưa trỏ":** DNS cần thời gian lan. Đợi thêm vài phút đến vài giờ rồi bấm **Kiểm tra lại**.
- **Badge ghi "DNS: sai IP (...)":** IP trong bản ghi A khác IP máy chủ Javis. Copy đúng IP mà Javis hiển thị ở bước 2 của wizard và cập nhật lại bản ghi A.
- **DNS đã đúng nhưng bấm Bật SSL báo "Không kết nối được cổng 443":** lớp HTTPS chưa chạy. Trên VPS Docker, chạy đúng lệnh Javis gợi ý (`docker compose -f docker-compose.yml -f docker-compose.https.yml up -d`) rồi bấm lại, và kiểm tra cổng 80/443 đã mở, không bị proxy khác chiếm.
- **Bấm Bật SSL báo "Chứng chỉ chưa hợp lệ":** thường là DNS vừa mới đúng, Caddy chưa cấp xong. Đợi một hai phút rồi bấm lại.
- **Không thấy nút Bật SSL:** bạn đang chạy trên Hostinger. Javis ẩn nút này vì Traefik của hPanel mới cấp được chứng chỉ; làm theo wizard Hostinger ở trên.
- **Tải ảnh báo lỗi định dạng hoặc quá lớn:** chỉ dùng PNG, JPG, WEBP hoặc GIF, dung lượng dưới 5MB.
- **Không thấy ô Tên miền hoạt động như mong đợi trên máy cá nhân:** đây là tính năng cho bản deploy Docker trên VPS có cổng 80/443. Trên máy cá nhân, phần tên miền/HTTPS sẽ không kích hoạt.

## Liên quan

- [Bắt đầu & thiết lập lần đầu](01-bat-dau-thiet-lap.md)
- [Bảo mật & tài khoản](14-bao-mat-tai-khoan.md)
- [Cấu hình .env](16-cau-hinh-env.md)
- [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md)
