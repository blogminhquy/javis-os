# Nhật ký cập nhật

Lịch sử phiên bản Javis OS. Bản mới nhất ở trên cùng. Xem ngay trong app tại mục **Cập nhật** trên thanh bên trái.

Định dạng: mỗi phiên bản là một khối `## [x.y.z] - ngày`, bên dưới nhóm thay đổi theo `### Thêm mới / Sửa lỗi / Cải thiện / Bảo mật`.

## [0.9.103] - 2026-07-19
Phần Skills trong Studio trên điện thoại giờ dễ đọc, dễ bấm. Trước đây dưới 860px khung Skills vẫn giữ 2 cột như máy tính (cột nhóm 210px + cột skill), khiến cột skill chỉ còn khoảng 150px và mô tả bị xuống dòng mỗi chữ một dòng; các nút Sửa/Xuất/Xoá lại chỉ hiện khi rê chuột nên trên điện thoại không bao giờ bấm được. Chỉ đổi bản điện thoại.
### Cải thiện
- **Skills trên điện thoại xếp dọc**: dưới 860px, khung Skills chuyển từ 2 cột sang xếp dọc. Danh sách nhóm thành dải chip cuộn ngang gọn ở trên (bấm để lọc), danh sách skill chiếm trọn bề ngang nên mô tả đọc bình thường thay vì vỡ từng từ.
- **Nút thao tác skill luôn hiện trên điện thoại**: Sửa/Xuất/Xoá tách xuống một hàng riêng dưới mỗi thẻ và luôn hiển thị (bỏ kiểu chỉ hiện khi hover), vùng chạm to hơn, ô chọn bật/tắt cũng lớn hơn. Ô tìm skill dùng cỡ chữ 16px để iOS không tự phóng to khi focus.

## [0.9.102] - 2026-07-19
Màn Javis (cockpit) trên điện thoại giờ là một khung cố định không trôi: quả cầu thu nhỏ ở trên, khung chat cuộn được ngay dưới để đọc kết quả. Chỉ đổi bản điện thoại.
### Cải thiện
- **Cockpit điện thoại thành 1 khung cố định**: khoá cuộn cả trang trên điện thoại (không còn cảnh trôi lên trôi xuống lộ quả cầu), quả cầu não thu về khoảng 34% màn hình ở trên, phần chat chiếm khoảng còn lại và tự cuộn bên trong để đọc hội thoại. Header cố định + ô nhập bám đáy như cũ.

## [0.9.101] - 2026-07-19
Facebook cá nhân: nhận diện đúng trang ĐĂNG NHẬP mbasic trả về khi cookie bị từ chối, thay vì đọc nhầm trang login thành feed. Trước đó fix User-Agent (0.9.99) đã hết lỗi "không hỗ trợ", nhưng nếu cookie hết hạn/bị Facebook chặn thì mbasic trả trang đăng nhập (URL vẫn là mbasic, không redirect) nên không bị bắt.
### Sửa lỗi
- **fb-personal đọc nhầm trang đăng nhập thành feed**: thêm `_is_login()` (trang có cả ô email lẫn ô mật khẩu) vào lớp `_fetch`; gặp trang đăng nhập (theo NỘI DUNG, không chỉ theo URL redirect) thì trả lỗi rõ nêu 3 nguyên nhân thường gặp (cookie hết hạn/đã logout; Javis chạy ở IP/máy khác nơi đăng nhập nên Facebook chặn phiên lạ; tài khoản bị checkpoint) kèm cách sửa, thay vì trả nội dung trang login. Test lên 31 kiểm tra.
Trang Việc định kỳ giờ gộp MỌI brain, mỗi việc gắn nhãn brain và chuyển được sang brain khác; tạo việc qua chat báo rõ brain; lựa chọn /brain trên Telegram được nhớ bền qua khởi động lại. Gỡ cái rối "tạo việc qua Telegram vào brain mặc định, tìm ở brain đang làm không thấy" - hai khái niệm brain (phiên Telegram vs brain đang xem trên dashboard) vốn tách rời, việc vẫn chạy nhưng người dùng không nhìn thấy.
### Thêm mới
- **Trang Việc gộp mọi brain**: endpoint `GET /viec/all` trả loop + nhắc hẹn của TẤT CẢ brain, nhóm theo brain (brain đang xem lên đầu, gắn "đang xem"), mỗi thẻ có nhãn brain. Nút bật/tắt/xoá/chạy/huỷ nhắm ĐÚNG brain của chính việc đó thay vì brain ở sidebar.
- **Chuyển việc sang brain khác**: nút "Chuyển brain" trên mỗi loop/nhắc (`POST /loops/move`, `POST /reminders/move`). Loop dời nguyên file .md + trạng thái chạy; trùng tên ở brain đích thì từ chối, KHÔNG ghi đè (định danh loop theo tên file). Form tạo loop mới có ô chọn brain đích.
- **Nhớ bền /brain Telegram**: lựa chọn brain của mỗi cuộc chat lưu bền ở `tg_brain.json` (theo tên brain), sống sót qua khởi động lại bot thay vì mất về mặc định như trước; brain bị xoá thì tự về mặc định + dọn mục cũ.
### Cải thiện
- **javis_schedule báo rõ brain**: câu xác nhận khi tạo việc/nhắc qua chat nêu tên brain ("Đã tạo việc ... trong brain Kim Khí Hà Lộc") để biết ngay việc rơi vào brain nào, không phải đi tìm mới ngã ngửa.
- Test mới `test_viec_xuyen_brain.py` (30 kiểm tra): di chuyển loop/nhắc hẹn (thành công, va chạm slug, brain trùng, không tồn tại), nhớ bền tg brain qua restart + brain xoá, `/viec/all` gắn đúng brain cho từng item.

## [0.9.99] - 2026-07-19
Vá lỗi Facebook cá nhân (0.9.95) trả trang "Trình duyệt không hỗ trợ, hãy tải Facebook Lite" thay vì feed. Nguyên nhân: mbasic.facebook.com chê User-Agent - đã dò thật, mbasic chỉ nhả HTML cho trình duyệt DI ĐỘNG (UA iPhone Safari nhận được trang thật, UA desktop/Firefox mobile bị đẩy sang trang Lite).
### Sửa lỗi
- **fb-personal đọc feed ra trang "không hỗ trợ / Facebook Lite"**: đổi User-Agent mặc định sang iPhone Safari + danh sách UA dự phòng. Thêm lớp `_fetch` tự đổi UA khi gặp trang bị chê; nếu MỌI UA đều bị chê thì trả lỗi kèm cách sửa (dán UA riêng, lấy cookie từ trình duyệt di động) thay vì trả rác. Phát hiện đúng trang "không hỗ trợ" và trang login/checkpoint để báo lỗi rõ. Thêm field tuỳ chọn `user_agent` vào connector `facebook-personal` (khớp UA với trình duyệt nơi lấy cookie là chắc nhất) + cập nhật hướng dẫn. Test `test_fb_personal.py` lên 28 kiểm tra (thêm phát hiện UA + tự đổi UA + override).

## [0.9.98] - 2026-07-19
Vá triệt để lỗi header điện thoại ở trang quản lý (0.9.97 chưa dứt): header giờ CỐ ĐỊNH trên cùng nên luôn thấy nút ☰ để vào menu, và quả cầu cockpit ẩn hẳn sau trang quản lý. Chỉ đổi bản điện thoại.
### Sửa lỗi
- **Mất header (không vào được menu ☰) + lộ quả cầu ở trang quản lý**: header trước nằm trong lưới nên bị cuộn trôi mất, để lộ quả cầu 3D/2D phía sau. Nay header `position: fixed` trên cùng (nền đặc, luôn hiện ☰ · chip model · ＋ ở mọi trang), và ẩn hẳn `hud-body` (quả cầu) khi đang ở trang quản lý nên không còn lộ hay kéo trượt được. Màn cockpit vẫn hiển thị quả cầu bình thường.

## [0.9.97] - 2026-07-19
Vá lỗi trên điện thoại: ở trang quản lý (Tổng quan, Kết nối...) quả cầu 2D phía sau bị lộ ra và trượt nhẹ ở mép trên header. Chỉ đổi bản điện thoại.
### Sửa lỗi
- **Quả cầu cockpit lộ sau lưng trang quản lý khi cuộn**: mobile bật cuộn body cho màn cockpit dài, nhưng trang quản lý (cview đè lên) khi cuộn nhẹ làm header trượt lên để lộ quả cầu 3D/2D phía sau. Nay khoá cuộn body khi đang ở trang quản lý (`body.in-console`), nội dung trang tự cuộn bên trong khung - header cố định, không còn lộ cockpit. Màn cockpit vẫn cuộn bình thường.

## [0.9.96] - 2026-07-19
Vá nút + (hội thoại mới) trên header điện thoại: hết lệch khỏi header và bấm được. Chỉ đổi bản điện thoại.
### Sửa lỗi
- **Nút + bị rớt khỏi header, bấm không ăn**: header mobile trước là lưới 3 cột, thêm ☰ và chip model làm dư ô nên nút + rớt xuống dòng, đè lên quả cầu 3D và bị canvas chặn tap. Nay header thành một hàng flex (☰ · chip model căn giữa · +), nút + là con trực tiếp header (không còn nằm trong cụm bị ẩn ở trang quản lý). Bấm + giờ mở hội thoại mới và focus ô nhập luôn.

## [0.9.95] - 2026-07-19
Thêm connector **Facebook cá nhân (cookie - thử nghiệm)** và plugin `fb-personal`: tự động hoá tài khoản Facebook CÁ NHÂN bằng cookie phiên (Facebook đã đóng API cá nhân) - lướt/đọc feed, đăng bài lên tường, bình luận. Đi đường cookie + mbasic bằng httpx nên chạy được trên VPS headless, không cần Chromium. CẢNH BÁO: vi phạm điều khoản Facebook, rủi ro khoá tài khoản; mặc định TẮT, cookie mã hoá at rest. Đây là bước 2 nối tiếp connector Trang (0.9.90) cho nhu cầu lướt feed cá nhân.
### Thêm mới
- **Connector `facebook-personal`** (apikey, field `cookie` mã hoá): dán cookie phiên Facebook (kèm hướng dẫn lấy an toàn từ DevTools). Mặc định Chỉ đọc; đăng/bình luận chỉ chạy khi nâng Toàn quyền. Khai trong `system/mcp-catalog.json`.
- **Plugin `fb-personal`** (bundled) - 3 tool: `fb_feed_read` (readonly, trả văn bản feed đã làm sạch + link bài để Javis tóm tắt) và `fb_personal_post`, `fb_personal_comment` (min_mode full). Engine gọi `mbasic.facebook.com` bằng httpx + cookie, tự bóc `fb_dtsg` và tìm form soạn bài/bình luận (best-effort, chỉnh selector khi Facebook đổi). Chặn rõ khi cookie bị đẩy về login/checkpoint.
- **`validate_connection` nhận connector ẢO**: connector plugin-backed không có URL/command (Meta/Facebook gọi qua plugin) nay qua cửa thêm-kết-nối mà không dial MCP (đếm tool theo `tool_meta`). Trước đây connector apikey không URL sẽ bị xoá khi thêm. Sửa trong `mcp_hub.py` + bơm không đổi.
- Test `server/test_fb_personal.py` (24 kiểm tra, không mạng): catalog hợp lệ, min_mode đúng, gate chưa-có-cookie, bóc fb_dtsg/tìm form, đọc feed + chặn login, đăng/bình luận build đúng POST, và nhánh validate connector ẢO.

### Ghi chú
- Phần tự động hoá Facebook cá nhân là THỬ NGHIỆM và chỉ kiểm chứng được khi chạy thật với cookie thật trên máy đích; mbasic có thể bị Facebook đổi/đóng nên bộ tìm form là best-effort, cần tinh chỉnh khi kết nối thực tế.
Đổi font chữ toàn app sang **Montserrat** cho sạch, dễ đọc (thay font monospace cũ trông "lỗi lỗi" ở các nhãn). Code vẫn giữ font monospace. Và vá header màn cockpit trên điện thoại.
### Cải thiện
- **Font Montserrat**: nạp Montserrat (Google Fonts) và dùng làm font chính cho toàn giao diện (nhãn, tiêu đề, chữ thân, thanh bên). Khối mã và mã inline giữ font monospace riêng (`--mono`) cho dễ đọc code. Tải lại trang là thấy (đã bump ?v).
- **Header cockpit điện thoại hết lệch**: ẩn nút "Lịch sử" trên điện thoại để header màn "Javis" (buồng lái) khỏi bị chồng dòng, gọn còn ☰ + chip model + nút hội thoại mới. (Lịch sử vẫn xem được ở khung chat phóng to trên máy tính.)

## [0.9.93] - 2026-07-19
Chỉnh tiếp giao diện chat điện thoại theo phản hồi: header hết chồng lên nhau, bấm chip model là sổ ra danh sách được, và mục Hệ thống trong ngăn kéo gọn lại. Chỉ đổi bản điện thoại.
### Sửa lỗi
- **Header điện thoại bị chồng lên nhau**: ẩn tên workspace + ngày trên mobile để chip model làm phần giữa header, không còn đè lên tiêu đề hội thoại.
- **Bấm chip model không sổ ra danh sách**: popover chọn model giờ dùng vị trí cố định (không bị khung cha cắt), và sửa model-picker để bấm trong popover (chọn model, đổi effort) không tự đóng - trước đó do popover đã dời khỏi khung model-bar nên bị hiểu là bấm ra ngoài.
- **Rò dòng comment ra màn hình** ("...parse vào đây nhưng không hiển thị"): comment HTML lồng nhau ở stub số liệu làm rò chữ; đã gỡ dấu comment lồng.
- **Mục Hệ thống trong ngăn kéo**: bỏ nút Studio (không dùng nữa) và vá lỗi cụm chọn brain bị định vị đè lên đầu ngăn kéo.

## [0.9.92] - 2026-07-19
Wizard cài đặt cho các connector tự-tạo-app (Facebook Trang, Meta Ads): thêm nút mở thẳng trang tạo Facebook App và ô Redirect URI kèm nút Sao chép, để bớt thao tác dán tay hay dán sai. Chỉ đổi trang Kết nối, tải lại trang là thấy.
### Cải thiện
- **Nút mở trang + copy Redirect URI khi kết nối**: modal đăng nhập OAuth giờ đọc thêm `auth.setup` từ catalog để vẽ dãy nút "Bước 1: Tạo App mới / App của tôi" (mở tab mới) và một ô Redirect URI chỉ-đọc kèm nút Sao chép (tự lấy đúng cổng đang chạy). Hướng dẫn bằng chữ được rút gọn theo, trỏ vào các nút này. Áp cho connector `facebook-pages` và `meta-ads-graph`; connector không khai `setup` thì không đổi. Thêm trường `setup` vào `public_catalog()`, hàm `oauthWizard()` trong `console.js`, style `.conn-wizard/.wiz-*` trong `console.css`. Bump `console.js?v=72`, `console.css?v=21`.
Vá tiếp giao diện chat điện thoại (0.9.89): rút gọn dòng gợi ý trong ô nhập cho khỏi xuống dòng, và đưa "phần Hệ thống" trở lại. Chỉ đổi bản điện thoại.
### Sửa lỗi
- **Dòng gợi ý ô nhập bị xuống dòng trên điện thoại**: đổi placeholder mobile thành câu ngắn "Nói hoặc gõ cho Javis…" cho vừa một dòng (bản máy tính giữ câu đầy đủ).
- **Mất phần Hệ thống trên điện thoại**: chọn brain, Cài đặt, Đổi tông, Studio, bật/tắt loa và dải trạng thái HỆ THỐNG/MCP nay gom vào mục "Hệ thống" ở đáy ngăn kéo ☰ (trước đó bị ẩn mất). Dùng lại đúng nút cũ nên bấm là chạy như thường.

## [0.9.90] - 2026-07-19
Thêm connector **Facebook Trang (tự tạo app - Graph API)** và plugin `meta-pages-graph`: quản lý Fanpage của bạn qua Graph API chính chủ. Vẫn theo kiểu tự tạo app (BYO) nên KHÔNG cần Facebook duyệt app khi thao tác trên Trang bạn là admin, và mỗi bản fork tự đứng được một mình. Xem danh sách Trang, đọc bài và bình luận (chỉ đọc); đăng bài và trả lời bình luận (toàn quyền, không tự chạy lén). Dùng lại nguyên hạ tầng OAuth Meta sẵn có, không đụng `oauth_mcp`. Lưu ý: "lướt feed" trên trang cá nhân KHÔNG làm được qua Page API (Facebook đã đóng), để dành bài toán browser-automation đợt sau.
### Thêm mới
- **Connector `facebook-pages`**: OAuth BYO app kiểu Meta (dùng chung app với Meta Ads được), scope `pages_show_list, pages_read_engagement, pages_manage_posts, pages_manage_engagement`. Mặc định thêm ở mức Chỉ đọc; đăng/trả lời chỉ chạy khi user nâng lên Toàn quyền. Khai trong `system/mcp-catalog.json`, kèm hướng dẫn tạo app (~5 phút, redirect localhost).
- **Plugin `meta-pages-graph`** (bundled) - 5 tool cho mọi engine: `fb_pages_list`, `fb_page_posts`, `fb_page_comments` (readonly) và `fb_page_post`, `fb_page_reply` (min_mode full). Mỗi thao tác trên một Trang dùng Page Access Token RIÊNG lấy từ `/me/accounts`, không dùng token cá nhân; `fb_pages_list` không lộ token Trang ra output. Tự chọn Trang khi chỉ có 1, bắt chỉ rõ khi có nhiều.
- Test `server/test_meta_pages.py` (27 kiểm tra, không mạng): catalog hợp lệ, min_mode đúng (đọc readonly / ghi full), gate chưa-kết-nối, chọn Trang, đăng/trả lời dùng đúng token Trang, không lộ token.

## [0.9.89] - 2026-07-19
Giao diện chat trên điện thoại gọn hẳn: ô nhập thành viên bo tròn lớn, header chỉ còn menu ☰ + chip model + nút hội thoại mới, dãy công cụ chuyển thành ngăn kéo trượt từ trái. Chỉ đổi bản điện thoại (màn hẹp dưới 860px), bản máy tính giữ nguyên. Có spec + plan ở `docs/superpowers/specs/2026-07-19-mobile-chat-declutter-design.md`.
### Cải thiện
- **Khung chat điện thoại gọn tối đa**: ô nhập nở to thành một viên (đính kèm bên trái, ô gõ chiếm gần hết bề ngang và tự cao lên, mic và nút gửi bên phải); bỏ hai hàng điều khiển chật (dải HỆ THỐNG/MCP và thanh công cụ ở đáy). Header rút còn ☰ (mở ngăn kéo công cụ) + chip model (bấm đổi model/engine như cũ) + nút hội thoại mới. Nút đọc tiếng dời khỏi thanh nhập. Bản máy tính không đổi.

## [0.9.88] - 2026-07-18
Mỗi lần tải lại Javis giờ vào thẳng hội thoại mới thay vì mở lại phiên cũ. Chỉ đổi frontend, tải lại trang là có.
### Cải thiện
- **Tải trang = hội thoại mới**: trước đây F5 khôi phục phiên gần nhất vào khung chat; nay mặc định mở khung trống cho hội thoại mới. Hội thoại cũ KHÔNG mất - vẫn nằm trong panel Lịch sử (lưu ở server), bấm để mở lại. Bỏ gọi `restoreSession()` lúc load + xoá phiên tạm trong localStorage. Bump `app.js?v=70`.

## [0.9.87] - 2026-07-18
Chỉnh menu lệnh `/` sau lần chạy thật: mô tả skill dài giờ cắt gọn 1 dòng, tràn thì hiện "...". Chỉ đổi frontend, tải lại trang là thấy.
### Sửa lỗi
- **Mô tả trong menu `/` tràn nhiều dòng**: các skill mô tả dài (vd jay-abraham-sales) đẩy menu cao ngoằng, che cả các lệnh khác. Nay tên + mô tả mỗi cái cắt đúng 1 dòng, quá dài thì "..." (grid `minmax(0,1fr)` + `text-overflow: ellipsis`). Bump `style.css?v=46`.
- **`/notes` chưa hiện trong menu ở brain đang mở**: skill hệ thống chỉ rải vào brain lần đầu truy cập trong đời process, mà server đã chạy từ trước khi thêm `notes` nên brain đang mở bị bỏ sót. Đã rải `notes` vào cả 3 brain trên đĩa (`system_sync.sync_brain`); endpoint `/skills` đọc đĩa nên menu thấy ngay, không cần khởi động lại. Brain mới hoặc sau khi restart thì tự có.

## [0.9.86] - 2026-07-18
Khung lệnh `/` cho khung chat web (giống Telegram/Claude) và lệnh đầu tiên `/notes`: gõ `/notes` thì lưu tin nhắn hiện tại nguyên văn vào `sources/` (kèm ảnh), rồi tự chưng cất lên wiki nếu note đáng. Chỉ đổi frontend + thêm 1 skill hệ thống, không cần khởi động lại server; chỉ cần tải lại trang.
### Thêm mới
- **Menu lệnh `/` trên web**: gõ `/` ở ô chat hiện menu gợi ý các skill của brain + vài lệnh phiên (`/new`, `/reset`, `/stop`), lọc dần khi gõ, chọn bằng chuột hoặc phím mũi tên + Enter. Chọn skill thì điền `/slug ` để gõ tiếp nội dung; lệnh phiên chạy ngay. Nhất quán với Telegram (mọi `/<slug>` = gọi skill cùng tên).
- **Skill hệ thống `notes`**: lưu nhanh một note vào Second Brain. Giữ nguyên văn phần chữ người dùng gõ (không biên tập), ảnh đính kèm chuyển vào `attachments/` và nhúng `![[...]]`. Sau khi lưu vào `sources/`, tự đánh giá đáng-wiki: đáng thì chưng cất lên `wiki/` đủ 3 kỷ luật của vault; không đáng thì vẫn giữ source, chỉ báo nhẹ. Chạy được cả trên web lẫn Telegram, mọi engine. Là skill hệ thống nên tự có ở mọi brain qua `system_sync`.
- Frontend: thêm `dashboard/chat-slash.js` (logic parse/route/menu + menu DOM) và `dashboard/test_chat_slash.js` (test node headless); chặn `/` trong `sendMessage` của `app.js`. Bump `app.js?v=69`, thêm `chat-slash.js?v=1`.

## [0.9.85] - 2026-07-18
Bản đánh dấu để kiểm tra luồng tự cập nhật 1-click (nút "Cập nhật ngay") chạy end-to-end trên bản Docker có Watchtower. Không đổi tính năng, không cần thao tác gì thêm.
### Cải thiện
- **Thử nút "Cập nhật ngay"**: bump phiên bản để xác nhận app phát hiện bản mới, gọi Watchtower kéo image + dựng lại container, rồi tự tải lại trang. Không ảnh hưởng dữ liệu hay cấu hình.

## [0.9.84] - 2026-07-18
### Sửa lỗi
- **Đề xuất trong Dashboard Token thiếu dấu tiếng Việt**: các câu insight (cache thấp, hoạt động ngầm ngốn nhiều, opus chiếm nhiều, phiên phình, spike) viết trong `usage_index.py` bị gõ không dấu nên hiện ra "Hoat dong ngam chiem...", lệch với phần còn lại của app. Nay sửa thành tiếng Việt có dấu đầy đủ. CẦN KHỞI ĐỘNG LẠI SERVER (đổi ở backend) để đề xuất hiện đúng.

## [0.9.83] - 2026-07-18
Dashboard Token: nâng trang **Mức dùng** thành bảng theo dõi tiêu thụ token thật, đọc từ log của Claude Code và Codex trên máy (không cần API riêng). CẦN KHỞI ĐỘNG LẠI SERVER (thêm module `usage_index` + route `/usage/*`); sau đó tải lại trang.
### Thêm mới
- **Lọc theo kỳ**: hôm nay, hôm qua, tuần này, tuần trước, tháng này, tháng trước, 3 tháng gần nhất, năm nay - mỗi kỳ tự so với kỳ tương đương liền trước (delta %).
- **Bóc tách nguồn tiêu**: theo provider (Claude Code / ChatGPT-Codex / API), theo nguồn (bạn gõ tay vs Javis tự chạy qua SDK), theo hoạt động (chat / nền loop-lịch / subagent), theo model, theo dự án. Phát hiện nhanh chỗ ngốn token nhất.
- **Chỉ số hiệu quả**: tổng token, token/ngày, cache hit (tái dùng ngữ cảnh), số phiên + token trung bình mỗi phiên, và chi phí QUY ĐỔI theo giá API (với gói thuê bao là "tiết kiệm được bao nhiêu", chỉ OpenRouter là tiền thật).
- **Đề xuất tự động**: cache thấp gợi ý /compact, hoạt động nền ngốn nhiều gợi ý giảm loop, opus dùng nhiều gợi ý hạ model, phiên phình gợi ý tách, spike bất thường cảnh báo sớm.
- Backend: `usage_index.py` quét tăng dần `~/.claude/projects` + `~/.codex/sessions` (bỏ file chưa đổi), phân loại chat/nền qua `conversations.db`, gộp vào SQLite. Nhánh API ghi log tiến tới qua `usage_store`. Route `/usage/summary|insights|refresh`. Bump `console.js?v=71`, thêm `usage.js?v=1`.

## [0.9.82] - 2026-07-18
### Sửa lỗi
- **Nhãn nút trong khung sửa file thiếu dấu tiếng Việt**: các nút của `file-editor.js` viết không dấu ("Sua / Nguon / Luu / Da luu / Loi / Tai ve / Dong / Mo tab moi"), lệch với phần còn lại của app. Nay sửa thành "Sửa / Nguồn / Lưu / Đã lưu / Lỗi / Tải về / Đóng / Mở tab mới". Nội dung tiếng Việt gõ vào vẫn hiển thị đúng như trước, chỉ nhãn nút thiếu dấu. Bump `file-editor.js?v=3`, chỉ cần tải lại trang.

## [0.9.81] - 2026-07-18
Nâng khung sửa file .md trong chat lên WYSIWYG (soạn như Word), dùng lại đúng bộ máy của editor cây. Thuần giao diện, KHÔNG cần khởi động lại server (chỉ tải lại trang, đã bump `?v`).
### Cải thiện
- **Khung sửa .md trong chat giờ là WYSIWYG 2 khung**: gõ trực tiếp trên bản render (đậm, nghiêng, tiêu đề, danh sách, trích dẫn, link, kẻ ngang qua thanh công cụ), gạt "Sửa / Nguồn" để xem markdown thô. Dùng lại Turndown + thanh công cụ + đổi HTML sang markdown của editor cây (`window.JavisNoteEditor` mới expose từ `console.js`), giữ nguyên `[[wikilink]]` và `![[ảnh]]`. File text không phải `.md` vẫn là textarea nguồn như cũ. Turndown nạp lazy từ CDN; offline thì tự ở lại chế độ Nguồn (vẫn sửa tốt). Đã kiểm chứng trên trình duyệt thật với Turndown thật: mở ra vào chế độ Sửa, gõ thêm nội dung, lưu ra markdown đúng (giữ tiêu đề, in đậm, danh sách), gạt Sửa/Nguồn đổi qua lại đúng.
- **Bấm link/ảnh khi đang soạn không bung editor lồng nhau**: handler click trong chat nay bỏ qua khi click rơi vào vùng đang soạn (`[contenteditable]` / `.jvfe-modal` / `.note-editor`).

## [0.9.80] - 2026-07-18
Nút "Cập nhật ngay" làm chắc lại toàn diện: kiểm tra sức khoẻ sau khi cập nhật, bản git (Windows/native) lỗi thì TỰ QUAY VỀ bản cũ, có thanh tiến trình theo bước và xem trước "bản mới có gì" trước khi bấm; bản Docker có hướng dẫn lùi rõ ràng. **Cần khởi động lại server** (đổi luồng cập nhật + thêm endpoint). Có spec + plan ở `docs/superpowers/specs/2026-07-18-update-triet-de-design.md` và `docs/superpowers/plans/2026-07-18-update-triet-de.md`.
### Thêm mới
- **Updater đa nền tự rollback (bản git)**: thêm `server/updater.py` chạy tách rời, chỉ dùng thư viện chuẩn (vẫn chạy được cả khi bản mới làm hỏng dependency). Chuỗi: dừng server -> (git stash nếu cây bẩn) -> `git pull` -> `pip install` -> khởi động lại -> chờ `/health` khoảng 90 giây. Bản mới không lên được thì `git reset --hard` về commit cũ + cài lại lib + khởi động lại (tự rollback). Mọi bước ghi trạng thái vào `update_state.json` (sống qua restart).
- **Thanh tiến trình + xem trước bản mới trong panel Phiên bản**: dashboard hiện changelog của bản mới trước khi bấm, và khi cập nhật hiện các bước Chuẩn bị -> Tải code -> Cài thư viện -> Khởi động lại -> Kiểm tra sức khoẻ -> Xong; lỗi thì báo đã tự quay về bản cũ (git) hoặc hiện cách lùi (Docker), kèm thông báo khi có sửa đổi cục bộ được cất vào git stash.
- **Endpoint `GET /update/status` + `previous_version` trong `/version`**: UI theo dõi tiến trình qua trạng thái có cấu trúc + đuôi `update.log`, và biết bản cũ để lùi.
- **CI xuất tag phiên bản GHCR**: image thêm tag `:x.y.z` (đọc từ VERSION) cạnh `:latest` và `:<sha>`, để luôn có bản cũ cố định mà pin khi cần lùi trên Docker.
### Sửa lỗi
- **Bản Windows thiếu bước cài thư viện khi cập nhật**: updater cũ chỉ `git pull` rồi bật lại, không `pip install`, nên bản mới thêm thư viện là app crash. Nay mọi bản git đều cài lib khi cập nhật.
- **`git pull` chết khi cây làm việc bẩn**: có sửa đổi cục bộ ở file tracked là pull abort im lặng, cập nhật thất bại mà không rõ lý do. Nay tự `git stash` (giữ lại, không mất, không tự pop để tránh xung đột) trước khi pull và báo cho người dùng.
### Bảo mật
- **Chống double-click spawn 2 updater**: `POST /update` claim trạng thái ngay sau guard (không có await ở giữa) và chỉ chặn khi lần cập nhật đang dở BẮT ĐẦU gần đây, nên bấm hai lần không tạo hai tiến trình cập nhật chồng nhau, đồng thời không kẹt "đang cập nhật" vĩnh viễn nếu một lần cập nhật bị gián đoạn.

## [0.9.79] - 2026-07-18
Trong khung chat giờ bấm được link, và file .md/text bấm là bung ngay khung sửa giữa màn hình để xem và chỉnh sửa. Thuần giao diện, KHÔNG cần khởi động lại server (chỉ tải lại trang - đã bump `?v` để nạp bản mới). Có brainstorm + spec ở `docs/superpowers/specs/2026-07-18-chat-link-va-sua-md-design.md`.
### Thêm mới
- **Bấm file .md/text trong chat bung khung sửa giữa màn hình**: thêm `dashboard/file-editor.js` dựng một modal độc lập gắn thẳng vào `<body>` nên chạy được từ mọi trang. Với `.md` và file text hiện `<textarea>` sửa được (riêng `.md` có nút gạt "Nguồn / Xem", bản Xem render bằng `mdToHtml` sẵn có); ảnh/PDF xem trước; file khác cho tải. Lưu qua `/files/write` có ghép sẵn tiền tố "nhà" của brain nên ghi ĐÚNG chỗ kể cả trên localhost (trần duyệt = cả ổ đĩa). Đóng bằng Esc / ✕ / bấm nền mờ, lưu nhanh Ctrl+S. Bấm link thư mục vẫn nhảy trang Tệp tin như cũ; ảnh inline giữ nguyên.
- **URL trần trong chat tự thành link mở tab mới**: URL `http(s)://...` Javis gõ thẳng (không bọc markdown) nay tự nhận thành link bấm được. Chạy sau khi code block / inline code / ảnh / link markdown đã cất vào placeholder nên không đụng vào chúng; dấu câu ở đuôi URL nằm ngoài link.
### Sửa lỗi
- **Link file có khoảng trắng hoặc dấu ngoặc bị cắt cụt đường dẫn**: regex link/ảnh markdown cũ (`[chữ](đường-dẫn)`) chỉ bắt tới khoảng trắng đầu tiên rồi dừng ở dấu `)` đầu tiên, nên đường dẫn kiểu `06 - Sources/Tên (Tư Duy Ngược).md` bị cắt còn `06` và phần đuôi rớt ra thành chữ. Nay bắt cả cặp ngoặc cân bằng 1 tầng và cho phép khoảng trắng, đồng thời cắt title markdown tùy chọn (`( "tiêu đề" )`). Nhờ vậy bấm đúng file cần mở.

## [0.9.78] - 2026-07-18
### Sửa lỗi
- **Số liệu trên header ("N note · N kết nối") không còn ngắt xuống 2 dòng**: `.graph-stats` thiếu `white-space: nowrap` nên chữ tự xuống dòng khi cụm trái thiếu chỗ; và grid `.hud-top` là `1fr auto 1fr` ép cột trái bằng cột phải, trong khi cụm trái (chọn brain + nút + số liệu) rộng hơn hẳn. Nay: (1) `nowrap` cho `.graph-stats`; (2) grid đổi thành `auto minmax(0,1fr) auto` để cụm trái/phải bám theo nội dung, cụm giữa (tên + ngày) co giãn phần còn lại và cắt gọn bằng `…` khi màn hình quá hẹp thay vì đè lên nhau. Đã đo ở 1000px (một dòng, không đè, giữa tự cắt) và 1280px (đủ chỗ, hiện đầy đủ).

## [0.9.77] - 2026-07-18
Xoá não giờ LAN sang mọi máy đồng bộ (không còn bị "hồi sinh"), và giữ bản sao trong thùng rác cục bộ 30 ngày. **Cần khởi động lại server** (đổi luồng sync + endpoint xoá); giao diện tự nạp lại nhờ bump `?v=7`. Có brainstorm + spec + plan ở `docs/superpowers/specs/2026-07-18-brain-delete-sync-propagation-design.md` và `docs/superpowers/plans/2026-07-18-brain-delete-sync-propagation.md`.
### Thêm mới
- **Giấy báo tử (tombstone) đồng bộ để lan việc xoá não**: khi xoá 1 não (đã gõ đúng tên xác nhận), Javis ghi một file nhỏ `<BRAINS_DIR>/.javis-tombstones/<tên>.json` đồng bộ theo repo. Bước `_apply_tombstones` mới trong sync đọc tombstone và xoá dứt khoát não đó ở mọi máy, ghi đè đúng chính sách "xoá không thắng bản còn sống" - NHƯNG chỉ cho lần xoá cố ý. Có chốt thời gian: não được tạo/sửa lại sau khi xoá thì không bị giết oan (tombstone tự gỡ, và tạo lại não cùng tên qua `/brains/new` cũng gỡ tombstone). Não mặc định miễn nhiễm.
- **Thùng rác cục bộ 30 ngày**: xoá não giờ CHUYỂN dữ liệu vào `<STATE_DIR>/brain-trash/<tên>__<thời-gian>/` (ngoài vùng đồng bộ, mỗi máy một thùng riêng) thay vì xoá cứng; tự dọn mục quá 30 ngày ở đầu mỗi lần sync. Lời xác nhận khi xoá báo rõ điều này. Khôi phục bằng tay (chuyển folder từ thùng rác về `brains/`). Endpoint xoá là nguyên tử: ghi tombstone lỗi thì hoàn tác việc chuyển thùng rác.
### Sửa lỗi
- **Não đã xoá bị "hồi sinh" khi sync/update**: chính sách sync cũ cố tình không cho việc xoá thắng bản còn sống (chống mất dữ liệu), nên một não xoá ở máy này bị máy/remote khác đẩy ngược lại. Nay lần xoá cố ý lan đi qua tombstone; lá chắn chống mất dữ liệu chung vẫn nguyên vẹn cho mọi trường hợp KHÔNG có tombstone (folder biến mất do volume chưa mount, engine ghi dở... được `_restore_missing_brains` khôi phục, không bị lan xoá).

## [0.9.76] - 2026-07-18
Giãn thanh header cho hết dồn cục, và thêm nút đổi tông tối-đậm / tối-nhạt. Có brainstorm + spec ở `docs/superpowers/specs/2026-07-18-header-theme-toggle-design.md`.
### Thêm mới
- **Nút đổi tông giao diện ở góc phải header**: lật giữa tối-đậm (mặc định, nền `#0e0e16`) và tối-nhạt (nền xám `#282a37`, chữ dịu cho đỡ chói). KHÔNG có light mode nền trắng - giữ cả app tông tối nên cockpit 3D không bị phá. Đặt `data-theme="dim"` trên `<html>` override ~9 biến CSS (màu nền/chữ + nền rail); graph 3D dùng màu hard-code nên giữ nền tối, nhưng hai tông đều tối nên nhìn liền. Nhớ lựa chọn qua `localStorage["javis.theme"]`, có inline script đầu `<head>` áp trước khi vẽ để không nháy.
### Cải thiện
- **Header hết "díu dít", giãn đều 3 cột**: `.hud-top` (grid `1fr auto 1fr`) trước đây có 4 con phẳng; ở trang quản lý `.brand` + `.hud-actions` bị ẩn khiến 2 con còn lại dồn vào cột 1-2, cột 3 (~414px) trống hoác. Nay gói thành 3 nhóm cố định cột: trái (brand + chọn brain + số liệu), giữa (tên + ngày), phải (nút theme + cụm nút cockpit). Con ẩn chỉ tự co, nhóm vẫn giữ cột nên cân ở CẢ home lẫn trang quản lý; nút theme là con trực tiếp nhóm phải nên luôn hiện, lấp đúng cột phải từng bỏ trống.

## [0.9.75] - 2026-07-18
Sửa lỗi dropdown chọn não giữ lại "folder ngoài" (📁) đã xoá khỏi ổ đĩa hoặc trùng với một não thật - chúng sống dai qua cả xoá folder, xoá não, lẫn update lên bản mới. **Cần khởi động lại server** để có endpoint `/path/exists`; phần giao diện tự nạp lại nhờ bump `?v=6`.
### Sửa lỗi
- **Menu chọn não hiện lại não cũ đã xoá**: dropdown gộp option từ 2 nguồn ĐỘC LẬP. Loại 🧠 (`data-brain`) do `brains-ui.js` nạp tươi từ `GET /brains` (đọc đĩa thật) nên xoá folder/xoá não là tự biến mất khi tải lại. Nhưng loại 📁 (`data-custom`) do `app.js` nạp từ `localStorage["javis.brains"]` (folder ngoài tự chọn qua nút duyệt) thì KHÔNG BAO GIỜ được kiểm tra tồn tại, không dọn, không có nút gỡ. `localStorage` sống theo origin trình duyệt nên trụ qua cả xoá folder, xoá não lẫn update app - đúng triệu chứng. Nút thùng rác khi chọn 📁 còn báo "folder ngoài thì bỏ khỏi danh sách" nhưng không cung cấp cách bỏ nào → entry kẹt vĩnh viễn.
- **`brains-ui.js` giờ tự dọn danh sách 📁 mỗi lần nạp**: sau khi có danh sách não thật, hàm `pruneCustomBrains` bỏ khỏi `localStorage` những entry TRÙNG path một não thật (tránh hiện 2 lần) và entry mà path KHÔNG còn là thư mục (đã xoá khỏi đĩa), GIỮ lại folder ngoài hợp lệ khác path. Dọn ngay nguồn `localStorage` nên lần `app.js` render sau vẫn đúng, không "sống lại" qua update. Chạy TRƯỚC bước khôi phục lựa chọn để không khôi phục về một path đã chết.
- **Nút thùng rác gỡ được folder ngoài 📁**: chọn một 📁 rồi bấm xoá giờ hỏi xác nhận và gỡ khỏi menu + `localStorage` (KHÔNG đụng dữ liệu trên ổ đĩa), thay vì chỉ báo lỗi rồi bó tay như trước.
### Thêm mới
- **Endpoint `GET /path/exists?path=`** (đọc-only, chỉ `os.path`, nhẹ): trả `{exists, is_dir}` cho một đường dẫn tuyệt đối. Dùng để dropdown kiểm tra folder ngoài còn tồn tại không. FAIL-SAFE: lỗi truy cập trả `exists=null` → frontend hiểu là "chưa xác định" và GIỮ entry, chỉ dọn khi server xác nhận rõ path đã mất (endpoint thiếu/404 vì server chưa restart, hay lỗi mạng, đều không làm mất entry hợp lệ). Kèm test `server/test_path_exists.py` + `dashboard/test_brains_ui.mjs` (mock DOM, chạy thẳng logic dọn đúng kịch bản bug thật).

## [0.9.74] - 2026-07-18
Gom phần "mức dùng" thành một trang riêng có đồ thị, bỏ widget nổi vướng víu, và tinh chỉnh nốt nút thu/mở rail. **Cần khởi động lại server** để đồ thị mức dùng có dữ liệu (thêm field ở endpoint `/usage`); phần còn lại chỉ cần tải lại trang.
### Thêm mới
- **Trang "Mức dùng" trong rail (nhóm Hệ thống) có đồ thị 14 ngày**: thay cho hộp mức dùng nhỏ trước đây, giờ là một trang đầy đủ gồm 3 thẻ tổng (hôm nay, tổng tích luỹ, số dư OpenRouter), đồ thị cột token/ngày 14 ngày gần nhất, và bảng chi tiết theo nhà cung cấp/model (token vào/ra, số lượt, chi phí). Endpoint `/usage` thêm field `daily` (hàm `usage_store.daily(14)` gộp per-day, lấp cả ngày trống cho trục liền mạch). Số liệu vẫn do Javis tự đo, giữ 30 ngày.
### Cải thiện
- **Bỏ widget "MỨC DÙNG" nổi ở góc dưới khung giữa**: user thấy vướng. Gỡ khối HTML + CSS; hàm `refreshUsage`/`initUsageToggle` trong app.js tự thành no-op (đã có guard khi không thấy element) nên không cần đụng tới, không còn fetch `/usage` mỗi lượt chat.
- **Nút thu/mở rail dời sang PHẢI, version/tác giả sang trái**: `.rail-foot` xếp `space-between` (dùng `order`), icon nút to lên chút (18px) cho cân với icon nav; khi thu gọn chỉ còn nút, căn giữa.
- **Tooltip nhãn khi rê chuột lúc thu gọn hiện nhanh hơn**: native `title` trễ ~500ms, thay bằng tooltip tự vẽ (1 node body-level, thoát mọi overflow của rail) hiện sau 90ms, đặt cạnh phải icon; tạm gỡ `title` lúc hover để không lòi thêm tooltip native chậm, trả lại khi rời chuột (giữ cho screen-reader).

## [0.9.73] - 2026-07-18
Tinh chỉnh nút thu/mở rail (bản 0.9.72) theo góp ý: đổi icon, dời vị trí, và sửa link tác giả.
### Cải thiện
- **Icon nút thu/mở đổi sang kiểu "panel sidebar"**: thay mũi tên kép `«` bằng khung vuông chia hai với cột trái có các dòng nội dung (giống icon toggle sidebar quen thuộc). Icon tĩnh, bỏ hiệu ứng xoay 180° khi thu (kiểu panel không cần chỉ hướng, trạng thái đã có tooltip).
- **Dời nút thu/mở nằm CẠNH dòng version thay vì phía trên**: `.rail-foot` đổi từ xếp dọc sang hàng ngang, nút ở trái kề số phiên bản + "by Minh Quý". Khi thu gọn vẫn ẩn version/tác giả, chỉ còn mỗi nút căn giữa.
- **Link "by Minh Quý" trỏ về javisos.com** thay cho minhquy.vn.

## [0.9.72] - 2026-07-18
Làm gọn thanh điều hướng bên trái (rail) theo góp ý trực tiếp: chữ khó đọc vì dùng font monospace, header nhóm trơ không icon, và rail chiếm quá nhiều bề ngang màn hình.
### Thêm mới
- **Nút thu/mở sidebar ở góc dưới**: bấm để thu rail còn 60px chỉ hiện cột icon dọc (tên mục hiện qua tooltip khi rê chuột), bấm lần nữa bung lại đầy chữ 160px. Phần nội dung bên phải tự giãn chiếm lại chỗ khi thu (mọi offset chạy qua biến `--rail-w`, thu chỉ đổi 1 biến trên `body.rail-collapsed`). Trạng thái nhớ qua `localStorage` nên lần sau vào giữ nguyên. Mũi tên nút xoay 180° báo trạng thái (xoay cả nút chứ không xoay riêng `<svg>` để né quirk transform-box của SVG root). Luật thu gọn bọc trong `@media (min-width: 861px)` nên KHÔNG chạm thanh dưới ngang trên mobile.
### Cải thiện
- **Rail thành 2 tầng gập/mở thay cho danh sách phẳng dài phải cuộn**: tầng 1 là tên nhóm bấm để xổ, tầng 2 là các mục con trượt ra dưới (max-height transition). Mỗi lúc chỉ 1 nhóm mở; nhóm chứa trang đang xem tự mở, nếu đang gập thì tên nhóm hé màu cam để biết mình ở đâu. Store `nav` thêm `openGroup`/`toggleGroup`/`collapsed`/`toggleCollapsed`.
- **Sửa font sai + chữ to hơn**: nhãn rail trước dùng biến `--font` (monospace `SF Mono`/`Consolas`) làm chữ tiếng Việt có dấu cứng và lệch. Thêm biến `--font-ui` (Segoe UI sans-serif) cho riêng rail; cỡ chữ tên nhóm 12.5px, tên mục 13.5px (trước 11 và 12.5px).
- **Thêm icon cho tên nhóm (tầng 1)**: 6 icon line-style đồng bộ với icon mục (`GICON`) cho Trợ lý/Bộ não/Năng lực/Việc/Kết nối/Hệ thống, hết trơ.
- **Thu bề ngang rail 172→160px** ở chế độ mở rộng cho đỡ dư diện tích; đã đo không mục nào bị cắt chữ (kể cả "Việc định kỳ").

## [0.9.71] - 2026-07-17
Bản 0.9.70 ship tool `javis_schedule` ra ngoài trong tình trạng KHÔNG dùng được thật - review độc lập (chạy code, không đoán) tìm ra 2 lỗi Critical, 3 lỗi Important và 1 khoản nợ kỹ thuật. Bản này vá toàn bộ. Cảm ơn review đã chỉ đúng: "cả hai nửa của tool đều không làm được việc nó hứa".
### Sửa lỗi
- **[Critical] `httpx` ĐỒNG BỘ gọi ngược vào chính server đang chạy nó → treo CẢ SERVER**: handler `javis_schedule` (`plugin.py`) là `def` thuần, và 3 hàm `_post_reminder`/`_get_reminders`/`_cancel_reminder` gọi `httpx.post`/`httpx.get` ĐỒNG BỘ tới `http://127.0.0.1:<port>/reminders`. `plugins_host._make_call` gọi handler plugin bằng `res = handler(args, ctx)` rồi mới `await` - KHÔNG bọc `asyncio.to_thread` - nên lệnh `httpx.post` chặn NGUYÊN event loop của uvicorn (1 worker duy nhất, `main.py:5037`) trong lúc nó tự chờ CHÍNH request đó được trả lời → deadlock, `ReadTimeout` sau ~5-10s, và trong lúc đó server không trả lời được BẤT KỲ ai (mọi user, mọi tool). Tệ hơn: nhắc hẹn vẫn được tạo thật (đã vào hàng đợi trước khi treo), tool trả lỗi nên model retry → tạo THÊM 1 nhắc trùng + treo thêm 1 lần. Vá: cả 4 hàm chuyển `async def` + `httpx.AsyncClient`, đúng khuôn `system/plugins/meta-ads-graph/plugin.py` (`_get()`) và `system/plugins/image-chatgpt/plugin.py` (`_gen()`) - 2 plugin bundled còn lại vốn đã làm đúng từ đầu, `javis-schedule` là ngoại lệ duy nhất phá quy ước.
- **[Critical] Loop tạo qua tool KHÔNG BAO GIỜ làm việc user yêu cầu**: `_create_loop_file` ghi frontmatter thiếu hẳn field `goal`. `self_improve.py:250` `goal = fm.get("goal", "business")` mặc định `"business"` khi thiếu, và nhánh `goal == "business"` (`self_improve.py:546`) không đọc `loop["body"]` một chữ nào (thân file - đúng chỗ chứa prompt user vừa gõ qua chat). Hai kiểu hỏng: chưa đấu MCP số liệu kinh doanh → `skip_reason` khiến loop bỏ qua VÔ HẠN mọi vòng; có POS/ads → loop âm thầm chạy "phân tích chỉ số kinh doanh" (nhiệm vụ mặc định) thay vì việc user thật sự yêu cầu, rồi vẫn báo Telegram như đã làm đúng việc. Form web tạo loop vốn làm đúng (`self_improve.py:914` `goal = goal or (old["goal"] if old else "custom")`) - tool là nơi DUY NHẤT sai. Vá: `_create_loop_file` ghi cứng `goal: custom` vào frontmatter, kèm comment giải thích tại sao dòng này bắt buộc để không ai vô tình xoá.
- **`notify_only` không có tác dụng gì - mọi nhắc đều dựng nguyên engine Claude + MCP để "làm hộ"**: `_do_create` hard-code `"mode": "task"` trong payload gửi `POST /reminders`, bất kể `notify_only`. Hậu quả: "30 phút nữa nhắc anh gọi khách" (chỉ muốn 1 câu nhắc) tới giờ lại chạy `reminders.py:418 _run_task` (dựng CLI, đọc MCP, `max_wall_s=300`) rồi gửi "⏰ Nhắc hẹn (Javis đã làm): ..." thay vì đúng "⏰ Nhắc anh: ..." (`reminders.py:342`) - ngược hẳn mô tả tool tự khai và ngược CLAUDE.md ("notify_only=true nếu chỉ nhắc"). Vá: `"mode": "notify" if notify_only else "task"`.
- **Lịch "mỗi tuần"/"mỗi ngày"/"mỗi tháng"/"mỗi sáng" đều bị hiểu thành chạy MỖI 5 PHÚT**: `_UNIT_ALT` trước đó chỉ biết phút/giờ (VN + tắt tiếng Anh), không có ngày/tuần/tháng; các chuỗi này không match được số+đơn vị nên `_interval_min` rơi về sàn cứng 5 phút - "việc mỗi tuần tổng kết doanh thu" thành ra chạy 5 phút/lần (cộng lỗi goal ở trên = spam Telegram + đốt phí LLM thật). Ca nặng hơn: "mỗi sáng 7h" bị hiểu thành "mỗi 7 TIẾNG" (`interval_min=420`) vì regex chỉ thấy số "7" + đơn vị "h", không phân biệt được đó là MỐC GIỜ TRONG NGÀY chứ không phải khoảng cách lặp. Vá 3 lớp: (1) thêm `ngay=1440`/`tuan=10080`/`thang=43200` vào bảng quy đổi, và cho phép đơn vị đứng một mình ngầm định số lượng 1 ("mỗi ngày" = "mỗi 1 ngày"); (2) hàm `_daily_cron` mới dò tín hiệu LẶP HẰNG NGÀY (`mỗi` + buổi sáng/trưa/chiều/tối, hoặc từ "ngày", hoặc cụm "hằng ngày") CỘNG một mốc giờ đồng hồ (`7h`, `07:00`) → route sang kho reminders dạng cron 5 trường thay vì loop interval; (3) **luật an toàn**: lịch mơ hồ không rút được đơn vị/mốc giờ nào (vd "mỗi sáng" trơ, "mỗi khi rảnh") → `_interval_min` trả `None`, `_create_loop_file` trả `"ERROR: ..."` yêu cầu nói rõ hơn - KHÔNG còn âm thầm rơi về 5 phút trong bất kỳ trường hợp nào.
- **Skill `javis-builder` dạy gõ YAML tay, thắng cả chỉ dẫn "ưu tiên gọi tool" của CLAUDE.md**: `CLAUDE.md` (mục "Tự tạo năng lực") nói dùng skill `javis-builder`; skill này nạp SAU nên cụ thể hơn thắng - mà mục Loop của nó (trước bản này) chỉ có mẫu YAML để tự ghi file, không nhắc một chữ `javis_schedule`, nên model vẫn gõ tay dù tool đã có sẵn (và thiếu cả `owner_chat` trong mẫu → loop viết tay báo nhầm người). Vá: mục Loop giờ dạy ưu tiên gọi tool `javis_schedule` (op=create) trước, chỉ ghi file tay khi SỬA loop đã có hoặc cần trường nâng cao tool chưa nhận (`quiet_hours`/`max_runs_per_day`/`workspace`/`ambient_mcp`/`goal` khác `custom`); mẫu YAML còn lại thêm `goal: custom` + `owner_chat` cho đúng chuẩn tool đang tạo ra. Kèm hash bản cũ vào `system_sync.py:LEGACY_HASHES["skills/javis-builder"]` để brain user tự nhận bản vá này qua sync (không bị coi là "đã sửa tay").
- **`apply_mcp` không truyền `brain` ở vài đường UNGATED, plugin in-process vẫn có thể mù brain**: những nơi tạo CLI với `allowed_tools=None` (ungated) đều nạp plugin in-process (`claude_sdk_engine._plugins_server`, đọc `cli.javis_vault`) - thiếu `brain` là tái diễn đúng bug 0.9.70 vừa vá ở đường chat (`image-chatgpt` lưu nhầm `brains/Brain Default`). Vá `self_improve._make_cli` nhận thêm tham số `brain`, truyền xuống cả 3 lần gọi `apply_mcp` bên trong (nhánh `mode=full`, nhánh `ambient_mcp`, và nhánh mặc định - nhánh này thật ra GATED nên plugin không nạp, nhưng vẫn truyền cho nhất quán/phòng hờ); 2 điểm gọi `_make_cli` trong `run_cycle`/kiểm chứng nay truyền `brain=brain` có sẵn trong scope. Thêm `else` nhánh ungated của `execute_workflow` (`main.py`, Studio "chạy full quyền") gắn thẳng `c.javis_vault = vault_root` - KHÔNG gọi `_apply_mcp()` ở đây vì nhánh này cố ý dựa `setting_sources` để kế thừa MCP máy như phiên `claude` tương tác thật, gọi `_apply_mcp` sẽ đổi hành vi ngoài phạm vi bug đang vá. **2 đường còn lại KHÔNG sửa được** vì không có biến brain/vault nào trong scope để truyền (không bịa biến): `/metrics` (`main.py:1451`) không nhận tham số brain (endpoint dùng chung mọi brain); `/ingest-upload` (`main.py:1733`) chỉ nhận `staged`/`sources`/`attachments` đã resolve sẵn, không có brain gốc.
### Kiểm thử
- `test_javis_schedule.py` thêm 5 nhóm test chặn đúng các lỗi trên: (1) `inspect.iscoroutinefunction` trên handler + 3 hàm HTTP - lưới hồi quy chặn quay lại lối sync; (2) LƯỚI THẬT cho lỗi goal - đưa loop vừa tạo qua ĐÚNG API `self_improve.LoopFeature.get_loop` (không chỉ kiểm tra chữ đã ghi ra file) và khẳng định `goal == "custom"` + thân file tới được nơi sẽ chạy; (3) monkeypatch `_post_reminder` bắt payload, khẳng định `mode` đổi đúng theo `notify_only`; (4) `_interval_min` cho ngày/tuần/tháng + cron mốc giờ cố định + lịch mơ hồ phải `None`/`ERROR`; (5) dispatcher với `op` sai và `vault_root` rỗng. `test_loop_ambient.py` cập nhật stub `_apply_mcp` nhận thêm `brain=None` để khớp chữ ký mới.

## [0.9.70] - 2026-07-17
### Thêm mới
- **Tool `javis_schedule` - chat đặt được việc định kỳ, thôi gõ YAML tay**: trước đây muốn "tạo việc mỗi 2 tiếng quét đơn" phải tự gõ YAML frontmatter vào `Javis/loops/<slug>.md`, hoặc shell ra `curl POST /reminders` (`reminders.py:17` vốn ghi thẳng cách đó). Đường thứ hai còn tự mâu thuẫn: loop mode suggest/auto bị chặn Bash (`self_improve.py:112`) nên loop không tự đặt nhắc được cho chính nó. Nay một câu chat gọi thẳng tool, `op=create` tự route vào 1 trong 2 kho theo tính chất việc: lặp + bền → file `.md` (sửa được trong Obsidian); nhắc/cron/một lần → kho reminders (đã có cron 5 trường sẵn: `cron_util.py`, tự tính lần kế ở `reminders.py:364`). `op=list` nhìn CẢ HAI kho, `op=cancel` huỷ nhắc đang chờ. An toàn giữ nguyên luật CLAUDE.md: loop tạo qua chat luôn `enabled: false` + `mode: suggest`, không nhận tham số để đổi; trùng slug báo lỗi chứ không đẻ bản sao song song (định danh theo TÊN FILE, `self_improve.py:321-327`).
- **Vì sao là plugin bundled chứ không phải tool trong hub**: hub không với tới được mọi engine cho việc này, vướng hai rào. Rào 1: `_builtin_tools` (`mcp_hub.py:211-212`) early-return ngay khi `vault_root` rỗng - không đăng ký thêm tool nào cần biết brain - mà đường HTTP hub (`tools/list`/`tools/call`, `mcp_hub.py:392,398`) luôn gọi `discover_all` không kèm brain nên `vault_root` luôn `None` ở đường đó. Rào 2: `claude_config_path` (`mcp_hub.py:448-453`) trả `None` khi chưa có connector MCP nào bật, tức Claude Code còn chưa từng thấy hub tồn tại. Plugin đi qua MCP server IN-PROCESS của engine SDK (`claude_sdk_engine.py:162-186`, phần `_plugins_server`), không dính rào nào trong hai rào đó.
### Sửa lỗi
- **Plugin gọi từ chat luôn mù brain, `javis_generate_image` âm thầm lưu ảnh vào Brain Default**: `_plugins_server` (`claude_sdk_engine.py`) trước đây tự suy brain từ `self.cwd`, nhưng chat luôn chạy với `cwd=CLAUDE_CWD` (`main.py:318`, gốc project - không có thư mục `Javis/`) nên phép suy này luôn trượt về `None` ở đúng đường chat, mọi plugin gọi từ Claude Code đều nhận `ctx.vault_root=None`. Hệ quả cụ thể: `image_gen._resolve_vault` rơi về fallback `brains/Brain Default`, không có lỗi nào báo. Việc build `javis_schedule` (cần ghi đúng `Javis/loops/` của brain đang mở) mới lộ ra brain chưa từng được truyền tường minh qua engine SDK. Vá: `_apply_mcp` (`main.py`) nhận thêm tham số brain, đặt `cli.javis_vault` tường minh ở cả hai đường chat (dashboard websocket + Telegram, brain có sẵn trong scope) - không còn suy từ cwd.
- **Tên việc chứa ký tự chỉ-thị YAML làm loop chết âm thầm**: `_yaml_scalar` trước đó chỉ escape `[:#'"\n]`, bỏ sót các ký tự YAML coi là chỉ thị đầu dòng (`- @ * ! % ? | & >`). Tên việc dùng ký tự này ghi ra frontmatter vỡ, `yaml.safe_load` ném `ScannerError`/`ConstructorError`, và `self_improve.list_loops()` nuốt lỗi bằng try/except nên loop biến mất khỏi tab Việc định kỳ dù tool vừa báo "đã tạo thành công". Sửa bằng cách luôn trả về chuỗi nháy kép kiểu JSON (`json.dumps`) thay vì liệt kê ký tự cần escape - YAML 1.2 là superset của JSON nên scalar nháy kép JSON luôn hợp lệ. Áp dụng cả cho `owner_chat` (trước đó nối chuỗi tay, không qua hàm escape nào).
- **`op=cancel` luôn 401 trên instance đã bật mật khẩu**: `POST /reminders/cancel` thiếu trong `_AUTH_LOCAL_EXACT` (`main.py`), nên khi `gate_active()=True`, `javis_schedule` gọi httpx từ localhost (không cookie) luôn bị chặn. `/reminders` (tạo nhắc) đã được miễn cùng nhóm từ trước; huỷ là thao tác yếu hơn tạo nên miễn cùng mức mới nhất quán.
### Cải thiện
- **CLAUDE.md dạy đúng thứ vừa xây**: mục "Điều phối" bậc 6 (Nhắc hẹn) đổi từ `POST /reminders` sang gọi tool `javis_schedule`; bậc 7 (Loop) thêm câu ưu tiên gọi tool thay vì tự ghi file. Lý do phải sửa ngay trong bản có tool: mô tả tool cạnh tranh trực tiếp với chỉ dẫn trong system prompt, và prompt thường thắng - có tool mà tài liệu vẫn dạy gõ YAML tay thì model vẫn gõ tay. Phần mô tả format file loop giữ nguyên bên dưới, vẫn cần để SỬA loop đã có.

## [0.9.69] - 2026-07-17
### Bảo mật
- **`/automations/sync` là một lỗ bảo mật, xoá cùng toàn bộ tính năng giả nó thuộc về**: route gọi `claude_engine(...)` không truyền `allowed_tools`, nên theo `claude_sdk_engine.py:290-301` nó chạy `permission_mode="bypassPermissions"` VÀ nạp `setting_sources=["user","project","local"]` - engine call ít rào nhất trong codebase. Bảo đảm "CHỈ LIỆT KÊ" của route này chỉ là chữ trong prompt, không có gate thật nào đứng sau. Xoá route cùng lúc với toàn bộ registry `automations`.
### Cải thiện
- **Tab "Lịch" từng là tính năng giả, nay xoá sạch**: `Javis/automations.json` chưa từng có executor nào đọc - `_scheduler_loop` (`server/main.py`) tick 6 việc (loop, learn, kanban, reminders, backup, index) và không nhánh nào đọc file này. Kiểm tra thực tế trước khi xoá: 0 file `automations.json` tồn tại trên cả 4 brain đang chạy, 0 test phủ. Cái làm nó trông giống thật: badge xanh "N đang chạy" cho những dòng không bao giờ nổ, và ô lịch là free text không dòng code nào parse - vì tab phần lớn đang chiếu chính Loop qua hai lớp `_loops_as_routines` (main.py) và `pending_as_automations` (reminders.py), với chuỗi "mỗi N phút" bị bịa ra ngay lúc GET chứ không đọc từ đâu cả. Cả hai lớp chiếu, 3 helper registry và 5 route `/automations*` nay đã xoá.
- **Một trang "Việc" thay cho hai trang Loop + Lịch**: rail `selfimprove` đổi nhãn "Loop" thành "Việc định kỳ", gộp thêm khối "Nhắc hẹn đang chờ" (đọc `GET /reminders`, huỷ qua `POST /reminders/cancel`) - bắt buộc phải gộp vì nhắc hẹn trước đây CHỈ hiện ở tab Lịch vừa xoá. Không thêm endpoint mới: trang đọc thẳng `GET /loops` và `GET /reminders` vốn đã có sẵn.
- **Ô thống kê ROUTINES xoá hẳn, không thay bằng ô khác**: ô này ở `index.html` đếm "routines đang chạy" bằng cách fetch `/automations` trong `loadBrainStats()` (`app.js`) - chính route vừa xoá ở trên, nên sau khi route biến mất, số hiển thị mãi mãi là 0 vì lỗi 404 bị `.catch(() => ({}))` nuốt âm thầm. Ô này đúng là badge nói dối mà việc dọn tab Lịch sinh ra để diệt, chỉ là kế hoạch ban đầu bỏ sót nó vì chưa từng grep `app.js`.
- **Dọn 138 dòng cụm chết của panel loop cũ**: panel `<div class="loop-box" style="display:none">` trong `index.html` cùng cụm phục vụ nó trong `app.js` (`loadLoopConfig`, `saveLoopConfig`, `renderLoopStatus`, `loadLoopLog`, listener `loopRunNow` kèm vòng poll, listener `lintBtn`, các fetch `/loop/config`, `/loop/log`, `/loop/run-now`) - panel đã bị ẩn cứng bằng `display:none` và không dòng code nào từng gỡ nó ra, nên toàn bộ cụm phía sau không thể chạm tới được nữa. Backend `/loop/config` và `/lint` giữ nguyên, chỉ dọn phía UI đã chết.

## [0.9.68] - 2026-07-17
### Cải thiện
- **Lịch sử hội thoại chỉ hiện 20 mục, có nút "Xem thêm 20"**: sidebar trước đây đổ thẳng 100 hội thoại ra một mạch, chat nhiều thì danh sách dài lê thê phải cuộn mãi mới hết. Nay mặc định 20 mục, mỗi lần bấm mở thêm 20 nữa, hết hội thoại thì nút tự ẩn. Không cần sửa server: endpoint `/sessions` vốn nhận `limit` tự do nên client chỉ việc xin dư đúng 1 mục (`limit = shown + 1`) để biết còn dữ liệu phía sau hay không.
- Số mục đang mở được giữ nguyên khi danh sách tự làm mới lúc có tin nhắn mới (nếu không thì đang xem 60 mục lại bị thu về 20), và chỉ reset về 20 khi đổi brain. Lần render lại cũng giữ chỗ cuộn để bấm "Xem thêm" không bị nhảy vọt lên đầu.
- **Tìm kiếm vẫn quét toàn bộ hội thoại** như cũ, không bị giới hạn 20 mục này chạm vào.

## [0.9.67] - 2026-07-17
### Sửa lỗi
- **Xoá một bước làm MẤT TRẮNG chữ đang gõ dở ở các bước khác**: nút ✕ gọi thẳng `steps.splice(i, 1)` rồi `render()` mà quên gọi `captureSteps()` trước (nút "+ Bước" thì có gọi), nên `render()` vẽ đè mọi ô nhập bằng giá trị cũ trong mảng. Sửa vài bước, chưa Lưu, bấm xoá một bước bất kỳ là bay sạch, rất dễ tưởng mình gõ nhầm. Đã dựng lại đúng kịch bản trên cả bản cũ lẫn bản mới để đối chứng: bản cũ trả về chữ cũ, bản mới giữ nguyên chữ vừa gõ.
- **Dòng "Kiểm chứng" vỡ thành ba dòng**: quy tắc gộp `.editor-box input { width: 100% }` có specificity (0,1,1), thắng `.st-retries { width: 48px }` chỉ (0,1,0), nên ô số lần bị kéo full-width và đẩy chữ "lần" xuống dòng riêng. Ý đồ ban đầu là ba thứ nằm gọn một dòng nhưng CSS chưa bao giờ chạy đúng ý đó. Nay đổi thành `.editor-box .st-retries` (0,2,0). Ô chọn agent kiểm chứng không dính lỗi này vì nó có `flex: 1`.
### Cải thiện
- **Form Sửa workflow gập bước lại để thấy toàn cảnh**: workflow 11 bước trước đây trải hết cỡ trong hộp cao 86vh nên chỉ thấy được một bước rưỡi mỗi lần, muốn nắm tổng thể phải cuộn liên tục. Nay mỗi bước là một dòng gọn gồm số, tên agent và trích nội dung việc; bấm vào thì mở ra sửa, mở bước khác thì bước cũ tự gập. Các ô nhập vẫn nằm trong DOM khi gập (chỉ ẩn bằng CSS) nên `captureSteps()` đọc đủ, bước đang gập vẫn giữ nguyên cấu hình kiểm chứng lúc Lưu.
- **Thêm nút lên/xuống đổi thứ tự bước**: trước đây muốn chuyển bước 9 lên trước bước 4 phải chép tay qua lại. Nút ↑ ở bước đầu và ↓ ở bước cuối tự mờ đi.

## [0.9.66] - 2026-07-17
### Cải thiện
- **Biến workflow trong ô bước đọc thành lời thay vì dấu ba chấm**: mã cũ thay mọi `{{...}}` bằng `…`, nên bước đầu của viral-video-production hiện ra "Nhận …, tạo project folder" đọc lên cụt nghĩa. Nay `{{input}}` thành "đầu vào", `{{prev}}` thành "kết quả bước trước", và biến lạ thì hiện thẳng tên biến chứ không nuốt mất. Xử đúng cả trường hợp có khoảng trắng trong ngoặc như `{{ input }}`.

## [0.9.65] - 2026-07-17
### Sửa lỗi
- **Trang Workflows hiện các bước thành mấy cột cao lêu nghêu, rỗng ruột**: dải bước dùng `flex: 1` chia đều bề ngang, nên workflow 11 bước (viral-video-production) bị bóp mỗi ô còn khoảng 35px, trong khi tên agent `viral-video-director` có `white-space: nowrap` nên bị cắt sạch không còn chữ nào, chỉ trơ lại số thứ tự. Nay mỗi ô rộng tối thiểu 150px và tự xuống dòng khi hết chỗ, chữ luôn đọc được. Đo thật trên màn 1720px: 10 ô một hàng, ô thứ 11 xuống hàng dưới; 1280px được 7 ô; 900px được 5; 600px được 3; 380px được 2. Bề rộng ô luôn nằm trong 152 tới 173px ở mọi khổ và không khổ nào tràn ngang.
- **Bước từ thứ 10 trở đi đánh số sai thành `010`, `011`**: mã nối chuỗi `0${i+1}` nên chỉ đúng với bước 1 tới 9. Thay bằng `padStart(2, "0")`.
- **Thẻ workflow bị nhét vào lưới cột hẹp**: panel Workflows dùng chung lưới `.cards` (`auto-fill, minmax(280px, 1fr)`) với Agents và Lịch, mà pipeline lại nằm ngang nên hai thứ đánh nhau, và khi chỉ có một workflow thì phần còn lại của hàng bỏ trống. Nay Workflows có `.wf-list` và `.wf-row` riêng, mỗi workflow một hàng đầy chiều rộng; Agents, Lịch, plugin và loop giữ nguyên `.cards`/`.wf-card` cũ nên không bị ảnh hưởng.
### Cải thiện
- **Ô bước lấy việc làm làm chữ chính, tên agent hạ xuống chữ phụ**: nhiều workflow gọi cùng một agent ở mọi bước, lấy agent làm chữ chính thì 11 ô hiện chữ giống hệt nhau và không phân biệt được bước nào với bước nào. Nội dung task cắt gọn 2 dòng, di chuột vào xem đầy đủ.
- **Cụm nút và số bước dồn lên cùng hàng với tên workflow**, thay vì nằm dưới cùng, nên quét nhanh hơn khi có nhiều workflow.

## [0.9.64] - 2026-07-17
### Sửa lỗi
- **Javis tốn tới ~52ms mỗi lượt chat chỉ để đồng bộ skill, và nó chặn cả tiến trình**: hàm mirror skill đọc và băm lại `SKILL.md` của MỌI skill (cả bản nguồn lẫn bản đích) mỗi lần dựng system prompt, tức mỗi lượt chat, mỗi tin Telegram, mỗi task Kanban, mỗi vòng loop, mỗi nhắc hẹn. Đo thật trên 3 brain đang chạy, trước khi sửa: My Bullet Journal (27 skill/41 file) 52,48ms/lượt, Ngọc Thu Phạm (16 skill/30 file) 44,23ms/lượt, Brain Default (6 skill/9 file) 11,62ms/lượt - chạy đồng bộ trên event loop nên làm đứng luôn các kết nối khác. Nay thay bằng cổng chữ ký chỉ dùng `stat` (không đọc nội dung file nào), chỉ copy thật khi cây skill có thay đổi. Đo lại đúng 3 brain đó sau khi sửa: còn 8,30ms, 6,05ms, 2,28ms/lượt theo cùng thứ tự - nhanh hơn khoảng 5 tới 7 lần tuỳ brain (5,1x / 6,3x / 7,3x), không phải một con số cố định. Lỗi có sẵn, không ai biết cho tới khi đo.
- **File phụ trong skill đổi nội dung mà bản mirror không bao giờ nhận**: cổng cũ chỉ băm `SKILL.md`, nên sửa một file ảnh hay tài liệu ngang hàng trong thư mục skill thì bản Claude Code nạp native vẫn giữ bản cũ mãi. Chữ ký mới phủ mọi file (đường dẫn tương đối, thời gian sửa, kích thước) nên hết lỗi này.
### Thêm mới
- **Skill mang theo được `references/` và `scripts/`**: bản mirror sang `.claude/skills` nay copy cả cây con, nên skill có tài liệu tách riêng hay script đi kèm chạy được cả trên đường Claude Code nạp native, không chỉ đường router. 10 skill trong các brain hiện có đã dùng `references/` từ trước và tới giờ vẫn chưa tới được đường native; đã xác nhận cả 10 tới nơi sau bản này.
### Đã biết, chưa sửa
- **Skill hệ thống vẫn chưa ship được cây con**: `html-to-webcake` ship kèm `tools/` và `examples/` nhưng cơ chế cài skill hệ thống chỉ chuyển mỗi `SKILL.md`, nên cây con chưa bao giờ tới brain nào. Bản này KHÔNG sửa lỗi đó: nó nằm ở tầng cài đặt, phía trên tầng mirror.
- **Bản mirror bị phá từ bên ngoài sẽ không tự lành cho tới khi khởi động lại**: cổng chữ ký tính trên cây nguồn và nhớ trong bộ nhớ, nên nếu ai đó xoá tay file trong `.claude/skills` mà không đụng vào skill gốc thì Javis sẽ không nhận ra. Đánh đổi có chủ đích để lấy tốc độ; tắt/bật skill hay khởi động lại đều đưa nó về đúng.

## [0.9.63] - 2026-07-17
### Sửa lỗi
- **Skill Javis TỰ HỌC mất sạch frontmatter khi mô tả có dấu hai chấm**: `learn.py` ghi `description: <giá trị>` không bọc nháy kép. Mô tả tiếng Việt rất hay có dấu hai chấm (chính bản 0.9.62 phải bọc nháy kép cho 2 trong 5 skill hệ thống, tức khoảng 40%), và khi đó PyYAML ném lỗi trên CẢ KHỐI frontmatter chứ không riêng một dòng: `name`, `group`, `origin`, `status` mất theo, `split_frontmatter` nuốt lỗi trả về rỗng, và skill đó im lặng không bao giờ route được. Nay mọi giá trị do model sinh (`name`, `description`, `group`) đều đi qua `_yaml_scalar` (bọc nháy kép + escape đúng), kèm test round-trip gọi thẳng mã thật.
- **`learn.py` chưa hề ép trần 150 ký tự**: bản 0.9.62 chỉ chặn ở `POST /skills`. Đường tự học vẫn ghi thẳng mô tả quá dài xuống đĩa rồi để runtime cắt cụt. Nay `_promote_sync` gọi `validate_description` và đưa vi phạm vào danh sách bị chặn, cùng khuôn với quét secret và quét injection sẵn có.
- **`javis-builder` vẫn dạy đúng cái lỗi mà 0.9.62 sinh ra để diệt**: mẫu file trong skill đó, nằm dưới tiêu đề "ghi CHÍNH XÁC theo đây", vẫn ghi `description: <mô tả NGẮN nêu rõ KHI NÀO kích hoạt - đây là trigger, viết kỹ>` trong khi bộ chuẩn ngay 14 dòng dưới nói ngược lại. **CHANGELOG 0.9.62 tuyên bố "cả hai" tài liệu đã sửa là SAI**: `CLAUDE.md` sửa rồi, `javis-builder` thì chưa. Vì skill viết qua chat ghi thẳng ra đĩa nên không lớp chặn nào bắt được, và người viết theo mẫu sẽ tạo ra skill không route được mà không có lỗi nào báo. Nay đã sửa mẫu và một chỗ thứ hai cùng loại.
- **Sidecar đếm lượt dùng bị hỏng KIỂU dữ liệu làm sập cả trang Skill**: `GET /skills` và `is_stale` ép kiểu số mà không phòng thủ, nên một bản ghi bị sửa tay hỏng sẽ trả lỗi 500 cho toàn trang, trái đúng cam kết "sidecar hỏng không bao giờ được làm gãy". Nặng hơn: nó không tự lành, vì `bump` cũng vấp đúng chỗ đó rồi nuốt lỗi, nên bản ghi hỏng tồn tại vĩnh viễn và cả brain ngừng đếm. Nay cả ba chỗ đều phòng thủ, và `bump` ghi đè để tự lành ở lượt dùng kế tiếp.
### Thêm mới
- **Javis biết skill nào THẬT SỰ được dùng**: mỗi lần nạp skill qua `javis_use_skill` được ghi vào `Javis/skill-usage.json` của brain. Trang Skill hiện "đã dùng N lần, gần nhất ..." hoặc "chưa thấy dùng" cho skill đủ già mà chưa có tín hiệu. **Đây là tín hiệu MỘT CHIỀU và cần hiểu đúng**: Claude Code còn nạp skill NATIVE qua bản mirror `.claude/skills`, đường đó không đi qua bộ đếm. Nên "đã dùng" là chắc chắn, còn "chưa thấy dùng" chỉ có nghĩa **chưa có bằng chứng**, KHÔNG có nghĩa skill vô dụng. Không có gì tự tắt, tự archive hay tự dọn skill dựa trên con số này; mọi quyết định vẫn là của người dùng.
- **Chuẩn viết skill trong prompt của vòng tự học**: 9 điểm bắt buộc (trần 150 nội suy từ hằng số chứ không viết cứng, cấm mở đầu sáo rỗng, bọc nháy kép khi có dấu hai chấm, thứ tự mục thân file, cấm bịa flag và đường dẫn, trần độ dài thân, cấm skill kiểu router), kèm `group` thành trường bắt buộc trong schema.
- **Sidecar không lọt vào lịch sử học**: `Javis/skill-usage.json` là state runtime nên được thêm vào `.gitignore` của brain và loại khỏi bản backup. Brain cũ trước đây không bao giờ nhận được cập nhật `.gitignore` (hàm khởi tạo repo trả về sớm, và cả nhánh init cũng bỏ qua nếu file đã tồn tại); nay được hợp nhất thêm dòng còn thiếu ở lần bật tự học hoặc bấm học tiếp theo, giữ nguyên các dòng người dùng tự thêm. Việc này tạo một commit `chore:` một lần trong repo của brain, cố ý tách khỏi tiền tố `learn:` để không hiện ở trang Duyệt và không bị hoàn tác nhầm.
### Đã biết, chưa sửa
- **Skill hệ thống `html-to-webcake` đang hỏng ở mọi brain**: nó ship kèm `tools/` và `examples/`, thân skill bảo agent chạy chúng, nhưng cơ chế cài skill hệ thống chỉ chuyển mỗi `SKILL.md` nên cây con chưa bao giờ tới brain nào. Lỗi có sẵn, không do bản này gây ra.
- **`references/` và `scripts/` trong skill chỉ tới được đường router, chưa tới bản mirror `.claude/skills`**: bản mirror hiện chỉ copy file top-level. Đã ghi rõ giới hạn này ngay trong `javis-builder` để người viết skill biết trước. Làm mirror đệ quy đã được cân nhắc và HOÃN có chủ đích sau khi rà soát thấy 6 rào chặn thật (đắt nhất: nó sẽ quét và băm toàn bộ cây skill mỗi lượt chat, và chặn cả event loop). Chi tiết trong `docs/superpowers/specs/2026-07-16-skill-telemetry-authoring-design.md`.
- **Bản mirror không nhận file phụ đổi nội dung nếu `SKILL.md` không đổi**: cổng bỏ qua chỉ băm `SKILL.md`. Lỗi có sẵn, cùng hồ sơ với hai mục trên.

## [0.9.62] - 2026-07-16
### Sửa lỗi
- **Mô tả skill bị cắt cụt âm thầm nên skill không route được**: Javis cắt `description` của skill ở BA nơi với BA hạn mức khác nhau mà không ai biết: 60 ký tự ở mô tả tool `javis_use_skill`, 100 ký tự ở khối router trong system prompt, 140 ký tự ở đường dự phòng khi frontmatter thiếu `description`. Người viết skill không có cách nào biết mình đang bị chấm theo thước nào. Đo bằng chính `skill_router` trên brain đang chạy: **6/6 skill đang bật đều bị cắt**, mất từ 79 tới 316 ký tự mỗi cái, và phần bị vứt đúng là các ví dụ trigger, tức là thứ khiến routing hoạt động. Nay gom cả ba về một hằng số duy nhất `skill_router.SKILL_DESC_MAX = 150`, và gộp luôn hai hạn mức số-skill-liệt-kê (15 ở system prompt, 20 ở hub) về `SKILL_LIST_MAX = 20`.
- **Tài liệu đang dạy viết sai**: `CLAUDE.md` bảo `description` phải "viết rõ trigger" và `javis-builder` bảo "viết kỹ", trong khi runtime cắt cụt. Nay cả hai nêu rõ trần 150 KÈM LÝ DO (viết dài hơn là mất im lặng, skill không route được, viết xong phải tự đếm) và chỉ rõ ví dụ trigger đầy đủ thuộc về mục `## Khi nào dùng` trong thân file, nơi không bị cắt. Kiến trúc: index để TÌM, thân file để LÀM.
- **`javis-builder` trỏ sai chỗ ghi skill**: skill builder dạy ghi vào `.claude/skills/<slug>/SKILL.md` ở ba chỗ khác nhau, nhưng đó là bản MIRROR phái sinh. Canonical là `skills/<slug>/SKILL.md`. Đã sửa cả ba.
### Thêm mới
- **Viết lại mô tả 5 skill hệ thống cho lọt trần**: `html-to-webcake` (376 ký tự), `javis-builder` (333), `ingest-source` (266), `query-wiki` (249), `lint-wiki` (213) rút còn 69 tới 110 ký tự. Không mất thông tin: mọi ví dụ trigger chuyển xuống mục `## Khi nào dùng` trong thân file. Bỏ luôn cụm mở đầu sáo rỗng "Kích hoạt khi người dùng muốn" (29 ký tự giống hệt nhau ở mọi skill, đốt gần nửa ngân sách mà không phân biệt được gì).
- **Lint CI chặn lỗi tái phát**: `server/test_skill_caps.py` quét mọi skill hệ thống, fail nếu có mô tả vượt trần, dính boilerplate, rỗng, hoặc frontmatter vỡ. Liệt kê MỌI skill vi phạm trong một lần chạy chứ không dừng ở cái đầu.
- **`POST /skills` từ chối mô tả sai ngay lúc ghi**: trước đây endpoint chỉ kiểm slug, mô tả 400 ký tự vẫn lưu được rồi bị cắt âm thầm. Nay trả 400 kèm lý do, và kiểm TRƯỚC khi tạo thư mục nên request bị từ chối không để lại folder rỗng trên đĩa.
- **Chuẩn viết skill nhúng vào `javis-builder`**: 8 điểm bắt buộc (trần 150, cấm boilerplate, bọc nháy kép khi mô tả có dấu hai chấm, thứ tự mục thân file, cấm bịa flag/path, trần độ dài thân, cấm skill kiểu router). Nói thẳng rằng skill do chat ghi thẳng ra đĩa KHÔNG qua lớp chặn nào và lint CI chỉ soi skill hệ thống, nên tự đếm là phòng tuyến duy nhất.

## [0.9.61] - 2026-07-16
### Thêm mới
- **Khối hỏi-lại có lựa chọn trong khung chat**: Javis hỏi lại được bằng nút bấm ngay trong chat, kiểu Claude Code: nhúng khối ẩn `JAVIS_ASK` ở cuối câu trả lời, dashboard vẽ thành hàng chip dưới bong bóng. Bấm một nút là gửi đi như gõ tay, cùng phiên. Chỉ tin nhắn cuối mới bấm được; cuộn lên lịch sử thì chip đã đông cứng.
- **Chạy trên mọi engine**: Claude Agent SDK, Codex CLI, các engine API đều dùng được vì chỉ dựa vào system prompt, không đụng MCP hub.
### Sửa lỗi
- **Khối điều khiển không còn lọt sang Telegram**: khối `JAVIS_METRICS` trước đây lọt nguyên xi sang Telegram. Nay mọi khối điều khiển đều bị bóc trước khi ra kênh chữ ở cả 4 đường trả lời Telegram (chat, báo cáo Loop, báo cáo Việc Kanban, nhắc hẹn kiểu task); riêng `JAVIS_ASK` hạ xuống danh sách đánh số để nhắn lại "1" là chọn.
- **Chip hỏi-lại: nhãn hiện và nhãn gửi lệch nhau khi dài quá 40 ký tự**: nút chip trước đây cắt gọn LÚC VẼ nhưng vẫn gửi nguyên nhãn gốc khi bấm, nên nhãn dài (ẩn cả trong nội dung do connector ngoài chèn vào) có thể gửi đi phần người dùng chưa từng đọc hết. Nay cắt ngay ở bước bóc dữ liệu (`extract()`), thứ hiện và thứ gửi luôn giống nhau.

## [0.9.60] - 2026-07-16
### Sửa lỗi
- **Loop nền thấy lại connector claude.ai (Gmail/Drive/lịch) qua cờ opt-in `ambient_mcp`**: từ bản chuyển engine sang Agent SDK (quãng v0.9.35-0.9.37), loop tự chạy không còn "nhìn thấy" các connector claude.ai như Gmail, Google Drive, Google Calendar, nên loop kiểu "chiều đọc Gmail tóm tắt" ngưng chạy dù trước đó chạy được. Nguyên nhân: loop chạy ở nhánh fork nền có khoá quyền (duyệt từng tool, mặc định từ chối mọi tool ngoài whitelist), và ở nhánh này engine SDK cố tình KHÔNG nạp cấu hình máy (`setting_sources`) để allow-rule trong settings không che được lớp gate. Hệ quả phụ là connector claude.ai (vốn chỉ xuất hiện khi nạp cấu hình máy, như `claude -p` vẫn làm) biến mất khỏi loop. Nhánh Popen cũ trước đó chạy `--dangerously-skip-permissions` cộng `--mcp-config` không kèm `--strict` nên connector luôn được gộp vào, đó là lý do loop cũ đọc được Gmail. Chat (web và Telegram) KHÔNG dính vì chạy nhánh không-khoá-quyền đã được nạp lại `setting_sources`. Cách sửa: thêm cờ frontmatter `ambient_mcp: true` cho từng loop. Bật thì loop đó chạy nhánh không-gated (nạp cấu hình máy nên connector claude.ai xuất hiện lại), vẫn chặn cứng Bash/WebFetch/WebSearch/Task và tool tiền/đơn qua hub vẫn khoá theo mode. MẶC ĐỊNH TẮT để bản fork về sạch, không loop nào tự chạm Gmail/Drive của ai; chỉ bật khi user yêu cầu rõ. Bước kiểm chứng luôn giữ khoá chặt dù cờ bật. Kèm test hành vi trong `test_loop_ambient.py`.
### Bảo mật
- **Không lộ định danh thật trong ví dụ cấu hình + soát sạch git**: `system/mcp-catalog.json` dùng nhầm một mã định danh thật làm placeholder gợi ý, nay đổi thành số giả `1234567890` để bản fork không thấy thông tin thật của ai. Đã soát toàn bộ file đang được git theo dõi: mọi file dữ liệu kết nối (Kho kết nối, hub config, settings, khoá bí mật, token) đều đã nằm trong `.gitignore` và chưa từng bị commit, nên người fork về có bản trắng, không kết nối nào cài sẵn.

## [0.9.59] - 2026-07-16
### Cải thiện
- **Navbar gom nhóm cho dễ tìm công cụ**: thanh điều hướng trái trước đây xếp phẳng 18 mục thành một cột dài, tìm mỏi mắt. Nay gom theo chức năng thành 5 nhóm có nhãn nhỏ (Trợ lý, Bộ não, Năng lực, Việc & lịch, Kết nối) và ghim cụm Hệ thống (Cài đặt, Cập nhật, Tài khoản) xuống đáy rail (có đường kẻ ngăn). Sắp lại thứ tự các mục cho hợp mạch dùng. Trên mobile các nhóm tự dàn phẳng thành một hàng ngang như cũ (ẩn nhãn nhóm). Cấu trúc nhóm khai trong `RAIL_GROUPS` (console.js) - đổi thành viên/thứ tự chỉ sửa một chỗ, mục nào quên xếp nhóm sẽ tự dồn vào cụm Hệ thống nên không bao giờ mất mục.
- **Trang Cập nhật phân trang 20 bản mỗi trang**: nhật ký dài 98 bản trước đây đổ hết ra một trang vừa nặng DOM vừa khó đọc. Nay chỉ hiện 20 bản mới nhất mỗi trang, cuối trang có thanh "‹ Mới hơn · Trang x/y · N bản · Cũ hơn ›"; đổi trang dùng lại dữ liệu đã tải (không gọi lại mạng) và tự cuộn lên đầu cho dễ theo dõi.

## [0.9.58] - 2026-07-16
### Sửa lỗi
- **Đồ thị 3D chói trắng + mất hiệu ứng nhấp nháy lúc "đang suy nghĩ"**: từ v0.9.55 bản 3D được tô đa màu theo danh mục (bảng màu cầu vồng) và kéo co tròn chặt, nhưng bản 3D render bằng `AdditiveBlending` (cộng dồn ánh sáng) nên nhiều màu cộng dồn trong khối chặt dồn về TRẮNG - lõi cháy trắng, nhìn chói. Nền đã sáng sẵn nên node loé lên lúc suy nghĩ không còn nổi bật, mất cảm giác nhấp nháy (code hiệu ứng vẫn còn nguyên, chỉ bị chìm). Sửa trong `graph3d.js`: hạ lõi glow từ trắng đặc `1.0` xuống `0.7` và cho màu danh mục ra sớm (giữ đúng hue thay vì cháy trắng); hạ độ sáng nền lúc nghỉ từ `0.85` xuống `0.5`; cho node "suy nghĩ" loé dày hơn (mỗi 14 khung thay vì 22, nhiều điểm khởi phát hơn). Kết quả: nền dịu, hết chói, node loé lên nổi bật rõ trên nền tối nên nhấp nháy quay lại. Vẫn giữ đa màu.

## [0.9.57] - 2026-07-16
### Thêm mới
- **Đổi tên / xoá file ngay trong trình sửa note**: thanh nút của editor thêm ✎ (đổi tên) và 🗑 (xoá) bên cạnh Lưu/Tab mới/Tải/Phóng/Đóng, thao tác trên đúng file đang mở. Đổi tên sẽ tự lưu nội dung đang gõ trước (không mất chữ) rồi mở lại file ở tên mới; xoá thì đóng editor. Cả hai đều làm mới cây mà giữ nguyên các thư mục đang mở.

## [0.9.56] - 2026-07-16
### Sửa lỗi
- **Thêm/đổi tên/xoá file trong cây Vault làm SẬP hết các thư mục đang mở**: mỗi thao tác gọi `renderVaultTree()` dựng lại cả cây từ đầu (mọi thư mục về trạng thái đóng), nên đang mở sâu vào thư mục nào là bị đóng mất, rất khó chịu. Sửa: thêm `_vtRebuildReExpand()` - trước khi dựng lại thì GHI LẠI các thư mục đang mở (childBox không ẩn), dựng tươi xong tự mở lại đúng chúng theo thứ tự nông-trước-sâu (cha trước con). Áp cho cả 4 thao tác: thêm file (nút ＋ đầu VAULT và ＋ trên node), đổi tên, xoá. Riêng thêm file còn tự bung thêm tới đúng thư mục vừa tạo để thấy file mới ngay. Nút ↻ làm mới thủ công vẫn thu gọn như cũ.

## [0.9.55] - 2026-07-16
### Thêm mới
- **Giao diện brain mới - cột trái thành Vault explorer (cây thư mục kiểu Obsidian + tìm note)** thay cho panel số liệu kinh doanh cũ. Cây lồng nhiều tầng mở lazy (bấm mới nạp), neo trong gốc brain. Ô tìm 2 chế độ: Tên (quét toàn vault ở trình duyệt qua `/files/list`, bỏ dấu tiếng Việt) và Nội dung (endpoint mới `GET /files/search` quét ruột file text, chạy threadpool, cap kết quả). Rê chuột vào node hiện 3 nút: ＋ thêm file (bấm ở thư mục tạo bên trong, ở file tạo cùng thư mục; mặc định `.md`; tạo xong tự bung cây tới đúng chỗ), ✎ đổi tên, 🗑 xoá.
- **Trình sửa note đè lên khoang não 3D**: bấm note mở editor neo trong khung giữa (cây trái + chat phải vẫn sống). File `.md` mặc định mở dạng WYSIWYG - sửa trực tiếp trên bản render markdown, có thanh công cụ (đậm, nghiêng, H1-H3, danh sách, trích dẫn, code, link, kẻ ngang); lưu chuyển HTML→markdown (turndown) GIỮ nguyên `[[wikilink]]`. Còn chế độ Nguồn cho markdown thô lossless. Ảnh xem inline, docx/pdf chỉ hiện thẻ tải về. Tái dùng `window.mdToHtml`, cụm endpoint `/files/*` sẵn có.
- **Công tắc đồ thị 2D / 3D trong Cài đặt (Tổng quan)**, mặc định 2D cho nhẹ máy (render ở trình duyệt, không phải VPS). Bản 2D dùng thư viện `force-graph` (engine d3-force, cùng họ với 3D và Obsidian): node phát sáng tô MÀU THEO DANH MỤC (thư mục), hover rọi đèn (sáng vùng liên kết, mờ phần còn lại, chỉ hiện tên note đang trỏ), co tròn về tâm, kéo node tự trôi về, zoom giới hạn vừa khung, và hiện CẢ note cô đơn (tham số `/graph?orphans=1`). three.js chỉ nạp lazy khi chọn 3D.

### Cải thiện
- **Đồ thị 3D cũng đa màu theo danh mục + co tròn** như 2D (dùng chung cách gán màu).
- **Nhãn danh mục quanh não tô chữ "% Vault" đúng màu cụm note** của thư mục đó; bấm nhãn rọi sáng đúng cụm.
- **Dời HỆ THỐNG + MCP ĐANG DÙNG xuống thanh chọn model** (ngang hàng, giải phóng cột chat). **Dời MỨC DÙNG token thành hộp nổi gọn ở góc dưới-phải khung giữa**, có nút thu nhỏ / mở rộng (nhớ trạng thái).
- **Click node trong đồ thị mở đúng editor cây** (WYSIWYG + công cụ) thay cho popup đọc/sửa phẳng cũ.
- Số liệu kinh doanh gỡ khỏi giao diện theo yêu cầu (giữ 3 id ẩn để không lỗi app.js).

## [0.9.54] - 2026-07-15
### Cải thiện
- **Bấm link/ảnh/thư mục Javis chèn trong chat giờ mở thẳng trang Tệp tin ĐÚNG vị trí (thay vì tải file thô)**: trước đây bấm ảnh hoặc link file mà Javis đính trong chat sẽ mở file thô trong tab mới - thấy nội dung nhưng không biết nó nằm ở đâu trong brain. Nay mọi link trỏ vào file/thư mục trong vault (đường dẫn tương đối gốc brain, vd `attachments/anh.jpg`, `videos/`) khi bấm sẽ nhảy sang trang **Tệp tin** mở đúng thư mục chứa, cuộn tới và tô sáng file mục tiêu để tìm thấy ngay. Link ra ngoài (http, mailto) vẫn mở tab trình duyệt mới như cũ. Ảnh vẫn hiện inline trong chat như trước, chỉ đổi hành vi khi bấm. Giữ deep-link `#open=<đường-dẫn>` trên thẻ link nên Ctrl/Cmd+bấm hoặc chuột giữa vẫn mở TAB TRÌNH DUYỆT MỚI và tab đó cũng tự vào đúng vị trí trong Tệp tin (chat ở tab cũ không mất). Khớp ngữ nghĩa đường dẫn với server: path trong chat tính theo gốc brain, còn File Manager duyệt theo trần (trên localhost là cả ổ đĩa) nên tự ghép tiền tố brain (`home` từ `/files/list`) để ra đúng thư mục. Nếu chat đang mở dạng phóng to (overlay) thì tự thu lại để thấy trang Tệp tin. Đã test trong trình duyệt: render ra đúng thẻ link mở-vị-trí cho ảnh/file/thư mục vault (link ngoài không đổi), bấm điều hướng sang trang Tệp tin, và deep-link `#open=` khi nạp tab mới cũng vào thẳng trang Tệp tin.

## [0.9.53] - 2026-07-15
### Sửa lỗi
- **Kết nối Substack báo "Substack 403: <!DOCTYPE html>..." khi Test/lấy cookie**: cầu nối `server/substack_mcp.py` gọi API Substack bằng `httpx`, nhưng Substack đứng sau Cloudflare - chặn client Python theo TLS fingerprint (trả 403 kèm nguyên trang HTML). Nghĩa là không chỉ nút Test, mà cả tạo nháp/đăng bài đều dính. Sửa: chuyển toàn bộ lời gọi HTTP của cầu nối sang `curl` (đã xác minh curl chạm được app Substack, trả JSON / "Not authorized"; có sẵn cả trên Windows lẫn Docker image). Kèm lọc thông điệp lỗi cho NGẮN GỌN, sạch (không đổ HTML dài vào chat và form Kết nối). Với session token đúng, Test giờ ra 200 và kết nối thành công.
- **Form Kết nối vẫn tràn/không cuộn được dù đã vá ở v0.9.49**: bản vá CSS (`.conn-form` cuộn được) đã có trong `console.css` nhưng KHÔNG hiện ra vì `index.html` nạp `console.css?v=14` (cache-bust) chưa được bump - trình duyệt vẫn dùng bản CSS cũ trong cache. Sửa: bump lên `?v=15` để trình duyệt tải bản mới. Thêm thanh cuộn NHÌN RÕ cho `.conn-form` (màu nhấn khi rê chuột) và chặn thông báo lỗi trong footer không phình quá cao đẩy nút Kết nối ra ngoài.

## [0.9.52] - 2026-07-15
### Sửa lỗi
- **Bấm "Open" file (video/ảnh/tài liệu) do Javis đính trong chat báo "Không tìm thấy file" dù file có thật**: link và ảnh Javis chèn vào chat dùng đường dẫn tương đối GỐC VAULT (vd `videos/tin-tuc.mp4`, `attachments/anh.jpg`) đúng theo quy ước trong CLAUDE.md, nhưng endpoint phục vụ file (`/files/raw`, `/files/read`, `/files/download`) lại resolve đường dẫn theo TRẦN duyệt của File Manager. Khi chạy localhost (không bắt đăng nhập) trần duyệt mở tới cả Ổ ĐĨA, nên `videos/tin-tuc.mp4` bị hiểu thành `D:\videos\tin-tuc.mp4` và luôn 404. Lỗi chỉ hiện trên bản localhost; bản public/login (trần = gốc brain) thì trùng nên không dính. Sửa: thêm resolver `_safe_serve_path` cho các endpoint CHỈ-ĐỌC, chấp nhận CẢ HAI quy ước - thử tương đối trần trước (giữ nguyên hành vi File Manager), không thấy thì thử tương đối gốc vault (link/ảnh trong chat). Cả hai nhánh vẫn khoá trong trần duyệt, nhánh vault còn siết chặt trong gốc brain nên không nới rộng phạm vi truy cập, không đụng các endpoint ghi/xoá/đổi tên. Đã test bằng cách gọi thẳng hàm thật của server: đường dẫn vault trước đây 404 nay phục vụ đúng file, đường dẫn kiểu File Manager vẫn chạy, thử `../` ra ngoài vault không bị nới. Cần khởi động lại server Javis để bản vá có hiệu lực.

## [0.9.51] - 2026-07-15
### Sửa lỗi
- **Trợ lý lấy User ID của Substack không chạy do Substack đổi định dạng link Hồ sơ**: Substack đã bỏ URL Hồ sơ kiểu `substack.com/profile/12345678-ten` (có dãy số) sang `substack.com/@handle` (không còn số), nên "Cách A" cũ (bóc số từ URL) vô dụng. Thêm endpoint backend `GET /connect/substack/resolve-uid` nhận handle hoặc link Hồ sơ rồi hỏi API công khai của Substack, trả về User ID kèm gợi ý Publication URL. Vì Substack đứng sau Cloudflare (chặn httpx theo TLS fingerprint, trả 403) nên endpoint gọi qua `curl` (có sẵn cả Windows lẫn Docker image) - handle được validate chặt + truyền dạng argv nên không có nguy cơ SSRF/chèn lệnh; endpoint vẫn nằm sau auth guard. Trang Docs cập nhật Cách A: dán link `@handle` rồi bấm "Lấy User ID" là ra số + nút Copy + danh sách Publication URL gợi ý bấm để copy. Đã test end-to-end backend (curl thật) lẫn front-end (mock fetch trong trình duyệt).

## [0.9.50] - 2026-07-15
### Sửa lỗi
- **CI và build Docker đỏ mỗi lần push (xung đột thư viện trong requirements.txt)**: GitHub Actions cứ gửi mail "Run failed" ở cả workflow CI lẫn Build Docker, fail ngay bước `pip install -r requirements.txt`. Nguyên nhân có từ v0.9.35 (không liên quan Substack): commit thêm engine Agent SDK ghim `starlette<0.39`, nhưng `fastapi==0.115.6` (bump ở bản vá bảo mật v0.9.12) lại đòi `starlette>=0.40` - hai ràng buộc chọi nhau nên pip không giải được. Bản 0.115.6 thực tế chưa từng được cài; app vẫn chạy fastapi 0.115.0 + starlette 0.38.6. Sửa: hạ pin về `fastapi==0.115.0` cho khớp `starlette<0.39` và đúng bản đang chạy thật. Lộ thêm xung đột thứ hai bị che: `uvicorn==0.30.6` chọi với `mcp` (đòi `uvicorn>=0.31.1`) - nâng lên `uvicorn==0.51.0` (bản .venv đang dùng). Đã resolve thử sạch và chạy đủ bộ test cục bộ (8/8 pass) trước khi push. Kèm ghi chú trong requirements.txt về việc fastapi-starlette bị khoá cặp để không tái phạm.

## [0.9.49] - 2026-07-15
### Sửa lỗi
- **Form Kết nối dài không cuộn được, bị cắt mất nút và ô cuối**: modal Kết nối (vd Substack với 3 ô + phần hướng dẫn dài) tràn quá chiều cao màn hình nhưng không cuộn xuống được, che mất ô User ID và nút Kết nối. Nguyên nhân: `.conn-form` nằm trong `.mp-box` giới hạn `max-height: 86vh` nhưng bản thân nó không có vùng cuộn. Sửa: cho `.conn-form` co lại và cuộn (`flex: 1 1 auto; min-height: 0; overflow-y: auto`), phần đầu đề và hàng nút Kết nối/Huỷ vẫn ghim cố định. Áp dụng cho MỌI connector có form dài, không riêng Substack.
### Cải thiện
- **Substack: thêm trợ lý lấy nhanh User ID + Publication URL, gọn phần hướng dẫn trong form**: trang hướng dẫn (`/static/docs/substack.html`) nay có công cụ tương tác: (A) dán link trang Hồ sơ là tự bóc ra User ID kèm nút Copy, không cần DevTools; (B) một dòng lệnh dán vào Console DevTools trên substack.com tự lấy cả User ID lẫn Publication URL (gọi `api/v1/user/profile/self`, tự copy User ID). Session token vẫn phải copy tay vì Substack khoá cookie HttpOnly - JS không đọc được, đã nói rõ trong trang. Đồng thời rút gọn đoạn `guide` hiển thị trong form Kết nối cho đỡ dài, dẫn người dùng bấm 'Hướng dẫn' để dùng trợ lý.

## [0.9.48] - 2026-07-15
### Cải thiện
- **Substack: hướng dẫn riêng trong Docs của Javis (không trỏ ra GitHub nữa)**: thêm trang hướng dẫn tự chứa `dashboard/docs/substack.html` (khớp giao diện tối của Javis, phục vụ tại `/static/docs/substack.html`) và đổi link "Hướng dẫn" của connector Substack trỏ vào trang này thay vì repo GitHub gốc. Trang gồm các bước lấy 3 thông tin đăng nhập (publication URL, cookie `substack.sid`, User ID), giới thiệu 3 tool, bảng mức quyền và cách bật quyền đăng bài, các lớp an toàn (loop không tự đăng, mặc định không gửi email), và bảng markdown gọn dựng nội dung.

## [0.9.47] - 2026-07-15
### Thêm mới
- **Substack: thêm quyền ĐĂNG BÀI (không chỉ tạo nháp)**: server MCP cộng đồng `substack-mcp` chỉ có đúng 1 tool tạo nháp và không đăng được, nên Javis thay bằng cầu nối Substack tự dựng (`server/substack_mcp.py`, transport `internal` giống Botcake) gọi thẳng API Substack. Ưu điểm kèm theo: chạy Python thuần, KHÔNG cần cài Node/npx nữa. Bộ tool mới: `substack_list_drafts` (liệt kê nháp - đọc), `substack_create_draft` (tạo nháp - ghi), `substack_publish` (đăng bài - nguy hiểm). Tool đăng tạo mới rồi đăng (title+body) hoặc đăng một nháp có sẵn (draft_id); có bộ chuyển markdown gọn sang định dạng thân bài của Substack (tiêu đề #, danh sách, trích dẫn, **đậm**, *nghiêng*, [link], `code`). An toàn: đăng bài xếp loại NGUY HIỂM nên mức mặc định (Ghi nháp) CHẶN - phải nâng kết nối lên Toàn quyền mới đăng được, và ngay cả khi Toàn quyền thì loop chạy nền vẫn không bao giờ tự đăng (chỉ đăng khi bạn yêu cầu trực tiếp trong chat). Đăng mặc định chỉ lên web, KHÔNG gửi email cho người đăng ký; chỉ khi bạn nói rõ mới bật cờ gửi mail (đã gửi thì không hoàn tác). Nút Test kết nối giờ kiểm tra token thật qua danh sách nháp.

## [0.9.46] - 2026-07-15
### Thêm mới
- **Đấu được Substack vào kho Kết nối**: thêm connector `substack` (dùng server MCP cộng đồng `substack-mcp` của marcomoauro, chạy local qua `npx`). Javis soạn tiêu đề, phụ đề và nội dung rồi đẩy vào Substack ở dạng BẢN NHÁP để bạn tự vào bấm Publish - không tự xuất bản, không gửi email cho người đăng ký. Đăng nhập bằng 3 thông tin dán ở trang Kết nối: địa chỉ trang (publication URL), session token (cookie `substack.sid`) và User ID (dãy số trong URL trang Hồ sơ); form kèm hướng dẫn lấy từng thứ. Phân quyền: tool `create_draft_post` xếp loại "ghi", mặc định mức Ghi nháp để tạo nháp chạy được trong chat, nhưng bị chặn ở mức Chỉ đọc và với loop chạy nền (không bao giờ tự tạo nháp). Kèm logo Substack chính chủ. Connector nạp thẳng từ `system/mcp-catalog.json`, dùng chung đường ống stdio sẵn có nên mọi engine (Claude Code, Codex, API) đều gọi được.

## [0.9.45] - 2026-07-14
### Sửa lỗi
- **Hết lỗi "CLINotFoundError: Claude Code not found at ...\_bundled\claude.exe" khi làm việc nặng (system prompt dài)**: engine Claude báo không tìm thấy Claude Code dù đã cài và đăng nhập bình thường. Thủ phạm KHÔNG phải thiếu Claude Code, mà là giới hạn độ dài dòng lệnh của Windows (32767 ký tự): thư viện Agent SDK nhét cả system prompt của Javis vào THAM SỐ dòng lệnh khi khởi chạy Claude, và với brain nhiều note/bộ nhớ thì system prompt vượt ngưỡng, Windows từ chối tạo tiến trình, Python báo lỗi "file not found" và SDK dán nhãn nhầm thành "Claude Code not found" (trỏ vào bản bundled). Đã dò và tái hiện đúng ngưỡng: prompt ~32k chạy được, ~33k trở lên là vỡ. Cách sửa: đẩy system prompt qua FILE (`--append-system-prompt-file`) thay vì nhét vào dòng lệnh, nên độ dài prompt không còn giới hạn (đã kiểm chứng chạy trơn ở 48k-60k ký tự). File tạm được dọn sau mỗi lượt, kèm quét dọn file sót nếu tiến trình bị kill giữa chừng. Lỗi này ảnh hưởng mọi tác vụ chat/edit trên brain lớn, không riêng gì làm video. Kèm test trong `test_sdk_engine.py`.

## [0.9.44] - 2026-07-13
### Sửa lỗi
- **Chat qua Telegram không còn mất ngữ cảnh khi phiên dài (vá nốt cùng lớp lỗi của v0.9.43)**: bản 0.9.43 chỉ vá đường chat trên dashboard; đường chat Telegram vẫn dính y hệt lỗi quên phần đầu hội thoại khi phiên dài hoặc khi vừa đổi từ engine Claude (Claude Code) sang một engine API. Nguyên nhân: khác dashboard (dựng lại lịch sử từ database mỗi lượt rồi nén), phiên Telegram giữ lịch sử TRONG BỘ NHỚ (`sess["or"]` theo từng chat_id) và sau mỗi lượt chỉ CẮT CỨNG còn 12 message gần nhất - phần cũ hơn bị bỏ CÂM không tóm tắt nên model quên sạch mạch đầu. Nay thay bước cắt cứng bằng `compact_mem` - bản in-memory của cơ chế nén dashboard: phần cũ rơi khỏi cửa sổ được TÓM TẮT (gộp cả tóm tắt cũ) rồi chèn làm system message ngay sau phần đầu, phần gần nhất giữ nguyên văn, tóm tắt chỉ được tạo khi đủ dài để đáng một lần nén, provider lỗi thì lùi về cắt an toàn để payload không phình vô hạn. Logic tóm tắt được tách dùng chung với đường dashboard (`compaction._summarize`). Kèm test hành vi trong `test_compaction.py` (phủ nén cuộn nhiều vòng, phiên ngắn giữ nguyên văn, và ca provider lỗi).

## [0.9.43] - 2026-07-13
### Sửa lỗi
- **Chat engine API (OpenAI/OpenRouter/Gemini/Anthropic API) không còn mất ngữ cảnh giữa chừng**: khi phiên dài hoặc khi vừa đổi từ engine Claude (Claude Code) sang một engine API, Javis hay quên sạch phần đầu hội thoại và trả lời lạc mục đích (vd đang bàn edit video mà hỏi "viết lại kế hoạch" thì lại đi viết kế hoạch sản phẩm Javis OS). Nguyên nhân: mỗi lượt chat engine API dựng lại lịch sử từ database rồi cắt cứng còn 12 message gần nhất - phần cũ hơn lẽ ra phải thay bằng bản tóm tắt nén, nhưng bản tóm tắt CHỈ được tạo khi các lượt trước cũng chạy bằng engine API. Nếu trước đó dùng Claude Code (engine này tự quản trí nhớ, không tạo tóm tắt) thì phần đầu bị cắt CÂM không tóm tắt, model chỉ còn system prompt + câu hỏi cuối nên bịa nội dung theo system prompt. Nay thay bước cắt cứng bằng `prepare_history`: phần cũ CHỈ rời khỏi payload khi đã nằm trong tóm tắt nén; nếu đuôi hội thoại chưa nén quá dài (đổi engine giữa chừng, hoặc nén nền chưa kịp) thì nén ĐỒNG BỘ ngay một nhịp trước khi gửi để gấp phần cũ vào tóm tắt. Đảm bảo không bao giờ bỏ câm một message nào. Kèm test hành vi trong `test_compaction.py` (phủ cả ca đổi engine Claude→API và ca phiên ngắn giữ nguyên văn).

## [0.9.42] - 2026-07-13
### Sửa lỗi
- **Tác vụ dài (edit video, render, tách nền...) không còn bị chém oan ở giây 180**: watchdog chống treo coi "engine im lặng 180 giây" là treo và ngắt phiên, nhưng khi Claude/Codex gọi một tool chạy lâu (render video cả tiếng, tách nền, build) thì im lặng suốt lúc tool chạy là BÌNH THƯỜNG - kết quả là đang làm dở việc dài thì bị dừng với thông báo "Claude không phản hồi 180s". Nay watchdog phân biệt hai trạng thái: đang CHỜ TOOL chạy thì trần chờ riêng 1 tiếng (đổi bằng biến `JAVIS_CLAUDE_TOOL_TIMEOUT`, xem [Cấu hình env](docs/16-cau-hinh-env.md)), còn im lặng khi KHÔNG tool nào chạy (treo thật) vẫn ngắt ở 180 giây như cũ. Áp dụng cho cả engine Claude (Agent SDK) lẫn Codex CLI. Kèm 2 test hành vi trong `test_sdk_engine.py`.
- **Hết cảnh "(không có nội dung trả về)" câm lặng**: khi phiên Claude kết thúc LỖI mà không có chữ nào (hay gặp ở lượt hỏi ngay sau khi phiên trước bị ngắt giữa chừng), engine giờ báo rõ loại lỗi và gợi ý cách thoát (gửi lại / mở hội thoại mới) thay vì để khung chat hiện dòng rỗng không rõ nguyên nhân.

## [0.9.41] - 2026-07-13
### Sửa lỗi
- **Giọng Javis không còn bị thu ngược vào khung chat**: trước đây khi Javis đọc câu trả lời (TTS), micro nhận dạng giọng nói vẫn mở và nghe lại chính giọng Javis phát ra loa, chép thành chữ rồi sau 1.5 giây im lặng tự gửi vào khung chat như tin nhắn của người dùng (hay gặp nhất khi bật chế độ rảnh tay rồi gõ phím gửi tin - mic mở suốt lúc Javis nói). Nguyên nhân: bộ nhận dạng (SpeechRecognition) thu âm bằng luồng riêng KHÔNG được khử vọng, và không có cơ chế loại trừ lẫn nhau giữa nghe với nói. Nay sửa 2 lớp trong voice.js: (1) Javis bắt đầu đọc mà mic đang nghe thì tạm NGỪNG nhận dạng ngay (bỏ cả phần lỡ nghe dở), đọc xong toàn bộ tự mở nghe lại sau một nhịp ngắn bằng phiên nhận dạng mới sạch; (2) mọi kết quả nhận dạng lọt về trong lúc đang phát tiếng đều bị bỏ (chắc chắn đó là giọng Javis, không phải người dùng). Ngắt lời bằng giọng (barge-in) vẫn hoạt động bình thường vì nó đo mức âm qua luồng mic đã khử vọng, không dựa vào nhận dạng. Người dùng chủ động tắt mic (Esc/bấm nút) thì không bị tự mở lại.

## [0.9.40] - 2026-07-12
### Thêm mới
- **Kết nối Meta Ads bằng cách CHẠY ĐƯỢC ngay: tự tạo Facebook App, gọi thẳng Marketing API (như Composio)**: vì MCP chính chủ của Meta đang beta khóa allowlist (không tự nối được), Javis thêm connector mới "Meta Ads (tự tạo app - Graph API)" đi đường vòng đã được chứng minh - bạn tạo một Facebook App của riêng mình (~10 phút, có hướng dẫn từng bước trong app và trong tài liệu), dán App ID + App Secret, Javis đọc thẳng số liệu quảng cáo của bạn qua Graph API. Có sẵn công cụ: liệt kê tài khoản quảng cáo, hiệu suất (chi tiêu/hiển thị/click/CTR/CPC/reach/chuyển đổi) theo kỳ, danh sách chiến dịch, và một công cụ đọc Graph API tùy ý. TẤT CẢ CHỈ ĐỌC - không tạo/sửa chiến dịch, không tiêu tiền. Token Facebook (~60 ngày) được Javis tự gia hạn; hết hạn thì bấm Kết nối lại. Đây đúng là mô hình các nền tảng như Composio dùng cho Meta Ads. Kèm hướng dẫn tạo app đầy đủ trong [MCP & số liệu](docs/09-mcp-va-so-lieu.md) và test tự động (`test_meta_graph.py`).

## [0.9.39] - 2026-07-12
### Sửa lỗi
- **Kết nối Meta Ads báo lỗi trung thực, hết ngõ cụt "cần client_id thủ công"**: sau khi điều tra sâu (probe thật endpoint của Meta + đối chiếu tài liệu chính chủ và báo cáo cộng đồng), xác định `mcp.facebook.com/ads` là MCP chính chủ của Meta đang ở beta GIỚI HẠN: máy chủ chỉ chấp nhận vài ứng dụng được Meta cấp phép sẵn (trợ lý của ChatGPT, Claude, Perplexity) và đã TẮT tự đăng ký ứng dụng (DCR) - nên Javis, và cả các công cụ khác, chưa nối tự phục vụ được. Đây là giới hạn phía Meta, không phải lỗi máy người dùng. Thông báo lỗi cũ ("Server không hỗ trợ tự đăng ký client (DCR) - cần client_id thủ công") gây hiểu nhầm rằng chỉ cần dán client_id là xong, giờ đổi thành giải thích rõ + hiện nguyên văn thông báo của Meta. Mô tả và hướng dẫn của connector Meta Ads cũng viết lại đúng thực tế (bỏ câu "đăng nhập 1 chạm, không cần tạo app").

## [0.9.38] - 2026-07-12
### Thêm mới
- **Trang Tệp tin duyệt được ra ngoài brain (tới cả ổ đĩa)**: trước đây File Manager khoá cứng trong thư mục brain, bấm "Lên" tới gốc brain là hết - không đọc/sửa được dữ liệu nằm ngoài vault. Nay khi chạy trên máy cá nhân (localhost), trần duyệt mở tới ổ đĩa chứa brain: mặc định mở vẫn vào đúng thư mục brain như cũ, nhưng bấm "Lên" đi ra được tới tận gốc ổ đĩa để đọc/sửa/tải mọi file. Thêm nút "⌂ Brain" để nhảy nhanh về thư mục brain, và nút "Lên" tự ẩn khi đã ở gốc. An toàn giữ nguyên khi chạy public (VPS/có đăng nhập): vẫn khoá trong brain để không hở cả ổ đĩa ra web. Tinh chỉnh bằng biến `JAVIS_FILES_ROOT` (xem [Cấu hình env](docs/16-cau-hinh-env.md)): ép khoá brain, mở cả ổ đĩa, hay chỉ một thư mục cụ thể. Không xoá được thư mục brain hay gốc ổ đĩa.

## [0.9.37] - 2026-07-12
### Cải thiện
- **Gỡ hẳn nhánh engine Claude kiểu cũ (Popen) - khép hồ sơ kế hoạch Agent SDK**: engine Claude giờ chạy duy nhất qua Agent SDK chính chủ. Xoá ~220 dòng code tự chế spawn/parse tiến trình trong claude_cli.py (nơi từng phát sinh các lỗi kiểu WinError 206); Codex CLI và phần auth/ngắt tiến trình dùng chung giữ nguyên. Biến `JAVIS_CLAUDE_ENGINE` không còn tác dụng (đặt `cli`/`sdk-loops` sẽ bị bỏ qua kèm một dòng log). Máy chưa cài claude-agent-sdk sẽ được engine báo rõ cách cài thay vì lỗi khó hiểu. Toàn bộ 6 bộ test + kiểm tra sống qua factory đều pass; nhật ký hoàn công ở docs/dev/2026-07-ke-hoach-agent-sdk.md.

## [0.9.36] - 2026-07-12
### Thêm mới
- **Engine Claude chạy Agent SDK chính chủ theo MẶC ĐỊNH (hoàn tất cả 4 phase kế hoạch)**: sau spike và smoke đạt toàn bộ, engine Claude giờ mặc định chạy qua claude-agent-sdk. Người dùng không phải làm gì - vẫn đăng nhập Claude Code như cũ, chat/loop/workflow/Telegram chạy y hệt nhưng nền tảng do Anthropic bảo trì, fork nền được chặn quyền theo từng lần gọi tool kèm audit. Trục trặc thì đặt biến môi trường `JAVIS_CLAUDE_ENGINE=cli` là quay về cách cũ ngay (giữ tối thiểu một bản phát hành); có thêm mức trung gian `sdk-loops` (chỉ tác vụ nền dùng SDK). Đã kiểm chứng bằng phiên chạy thật cô lập đủ 3 luồng: chat 2 lượt có nhớ phiên, workflow chạy trọn chuỗi bước, loop chế độ đề xuất bị lệnh "tạo file bằng được" vẫn không tạo được file; log server sạch không lỗi không fallback.
- **Plugin chạy thẳng trong tiến trình server (in-process) trên engine SDK**: tool plugin (tạo ảnh ChatGPT, ngày giờ VN, plugin user tự viết) không còn đi vòng qua hub HTTP - engine gọi thẳng handler Python, nhanh hơn và dùng được plugin cả khi CHƯA đấu kết nối MCP nào. Hub tự bỏ nhóm plugin khi engine đã có bản in-process (không còn nguy cơ model thấy 2 tool trùng chức năng); các engine khác (Codex, API) vẫn dùng plugin qua hub như cũ. Mức quyền min_mode của plugin vẫn được tôn trọng đúng theo chế độ suggest/auto/full.

## [0.9.35] - 2026-07-12
### Thêm mới
- **Engine Claude chạy được qua Agent SDK chính chủ (thử nghiệm, Phase 0-2 của kế hoạch)**: spike đạt cả 7 hạng mục (auth subscription không cần API key, stream, resume, interrupt, MCP config, prompt 43k ký tự không WinError 206, và tới token đầu còn NHANH HƠN cách cũ 3.6s vs 4.0s). Thêm engine `claude_sdk_engine.py` cùng hợp đồng với engine CLI cũ; bật thử bằng biến môi trường `JAVIS_CLAUDE_ENGINE=sdk` rồi khởi động lại - mặc định vẫn là `cli` như cũ, SDK lỗi thì tự rơi về CLI. Nút Dừng ngắt được cả hai loại engine.
- **Quyền per-call cho fork nền (nâng cấp an toàn lớn nhất của đợt này)**: khi chạy engine SDK, các fork nền an toàn (loop suggest/auto, task, reminder, learn) chặn tool NGOÀI whitelist theo TỪNG LẦN GỌI kể cả Bash/Write builtin - kèm audit JSONL ở `logs/sdk_tool_audit.jsonl` trong thư mục state. Smoke test thật: fork chỉ-đọc bị lệnh "tạo file bằng mọi cách" vẫn không tạo được file. Trước đây chỉ giới hạn được bằng danh sách tĩnh lúc spawn, không có audit tool builtin.
### Sửa lỗi
- **Ghim starlette tránh gãy server khi cài dependency mới**: package `mcp` (dependency của claude-agent-sdk) kéo starlette 1.x xung đột fastapi 0.115; requirements.txt ghim `starlette<0.39` + `sse-starlette<3` (pip check sạch).

## [0.9.34] - 2026-07-12
### Thêm mới
- **Chat engine API hết "mất trí nhớ" trong phiên dài (nén hội thoại)**: trước đây phiên chat dài trên engine API (OpenRouter/OpenAI/Anthropic API/Gemini) chỉ giữ 12 message gần nhất, phần cũ bị cắt bỏ - hỏi lại chuyện đầu phiên là Javis quên sạch. Nay phần lịch sử cũ rơi khỏi cửa sổ được TÓM TẮT tự động (chạy nền sau mỗi lượt, gộp dồn với tóm tắt trước) và bơm lại vào đầu phiên - Javis vẫn nhớ mạch cũ (quyết định, con số, việc dang dở) mà payload không phình. Tóm tắt lưu bền trong SQLite theo phiên, DB cũ tự migrate. Port ý tưởng session_memory_compaction của cookbook Anthropic. Kèm test `test_compaction.py` chạy trong CI.
### Cải thiện
- **Workflow tự cải thiện đúng kiểu evaluator-optimizer**: bước có `verify_agent` khi bị chấm CHƯA ĐẠT giờ được xem lại KẾT QUẢ LẦN TRƯỚC kèm phản hồi để sửa tiếp (giữ phần tốt, sửa chỗ bị chê) thay vì làm lại mù từ đầu - đỡ lặp đúng lỗi cũ, hội tụ nhanh hơn. Mẫu workflow trong tài liệu hệ thống bổ sung 2 khoá tuỳ chọn `verify_agent`/`max_retries` để Javis tạo workflow qua chat biết dùng vòng kiểm chứng.
- **Kế hoạch chuyển engine Claude sang Agent SDK chính chủ**: viết bản kế hoạch chi tiết ở `docs/dev/2026-07-ke-hoach-agent-sdk.md` - vì sao (lớp Popen tự chế là ổ bug WinError 206, quyền tool tĩnh), kiến trúc adapter giữ nguyên giao diện ClaudeCLI, map 3 mức quyền suggest/auto/full vào callback `can_use_tool` từng tool call, lộ trình 4 phase + spike go/no-go, rủi ro và tiêu chí thành công. Chưa code - chờ duyệt.

## [0.9.33] - 2026-07-12
### Thêm mới
- **Prompt caching cho engine API**: học từ cookbook chính chủ của Anthropic. Nhánh Anthropic API có tool MCP (nhánh chạy nhiều request nhất - mỗi vòng gọi tool là một request chở lại nguyên system prompt ~26k ký tự + schema tool + hội thoại) giờ được cache system + tools + hội thoại, các vòng sau chỉ trả ~10% giá input cho phần đã cache. Cách đánh dấu mới không mutate hội thoại gốc nên không còn nguy cơ tích luỹ marker vượt trần 4 breakpoint của API (lý do trước đây nhánh này phải tắt cache). Model Claude chạy qua OpenRouter cũng được cache system prompt. Kèm test mới `test_engine_cache.py` chạy trong CI.
- **Second Brain: trang wiki tự đủ ngữ cảnh (contextual retrieval)**: skill `ingest-source` giờ yêu cầu mỗi trang wiki mở đầu bằng 1-2 câu định vị (khái niệm gì, thuộc nguồn/chủ đề nào, dùng khi nào) và khai `aliases` (tên gọi khác, thuật ngữ tiếng Anh) trong frontmatter - để sau này hỏi bằng từ khác thì tìm kiếm vẫn trúng trang, và đọc trang lẻ tách khỏi source vẫn hiểu. Ý tưởng lấy từ công thức contextual retrieval của Anthropic, áp cho search dạng file không cần vector DB.
- **javis-builder viết system prompt theo khung metaprompt**: khi tạo agent qua chat, Javis giờ dựng system prompt theo khung 6 phần rút từ metaprompt của Anthropic (vai + mục tiêu, bối cảnh nghiệp vụ, quy trình đánh số, định dạng đầu ra kèm ví dụ, cách xử lý trường hợp khó, điều cấm cụ thể) thay vì 1-2 câu chung chung - agent tạo ra làm việc được ngay, đỡ phải sửa đi sửa lại. Hai skill hệ thống tự cập nhật vào mọi brain chưa chỉnh tay (brain đã chỉnh giữ nguyên bản riêng).

## [0.9.32] - 2026-07-12
### Sửa lỗi
- **Kết nối Meta Ads hết báo "Server này không khai OAuth chuẩn MCP"**: Meta khai issuer OAuth có path (`mcp.facebook.com/ads`) và đặt metadata theo đúng chuẩn RFC 8414 dạng chèn giữa (`/.well-known/oauth-authorization-server/ads`), trong khi Javis chỉ tìm dạng nối đuôi và gốc domain nên không thấy. Nay bước discovery thử đủ cả hai dạng (chèn giữa trước, nối đuôi fallback) cho issuer lẫn URL MCP có path - bấm Kết nối là ra trang đăng nhập Facebook như thiết kế. Các connector OAuth khác không đổi hành vi.

## [0.9.31] - 2026-07-11
### Sửa lỗi
- **Dán bài dài vào chat không còn nổ "Subprocess error: WinError 206"**: trước đây tin nhắn (cộng system prompt) được truyền cho engine CLI qua command line, mà Windows giới hạn command line tối đa 32767 ký tự - dán một bài báo dài hay đoạn văn bản lớn là vượt trần và lỗi "FileNotFoundError: The filename or extension is too long" ngay trước khi engine kịp chạy. Nay prompt được bơm qua stdin (không đi qua command line) nên dán bao nhiêu cũng chạy; áp dụng cho cả engine Claude Code lẫn Codex. Đã test thật với prompt hơn 40 nghìn ký tự.

## [0.9.30] - 2026-07-11
### Thêm mới
- **Key ElevenLabs trong Cài đặt dùng chung cho chỉnh sửa video**: Javis giờ biết dựng và cắt sửa video qua hai bộ công cụ ngoài (HyperFrames tạo video mới từ HTML, video-use cắt từ thừa / chèn phụ đề / chỉnh màu footage quay thật - cài dạng skill cho engine CLI). Phần phiên âm của video-use cần key ElevenLabs: chỉ cần nhập key một chỗ ở **Cài đặt > Giọng đọc (ElevenLabs)** như lâu nay, server tự bơm biến môi trường `ELEVENLABS_API_KEY` cho engine và tool con lúc khởi động và ngay khi lưu Cài đặt (không cần restart, không phải sửa file .env). Key vẫn được mã hóa at rest như các secret khác.
### Sửa lỗi
- **Tiến trình Python con hết crash Unicode trên Windows**: server tự đặt `PYTHONUTF8=1` cho tiến trình con (tôn trọng giá trị user đã đặt sẵn), tránh lỗi UnicodeEncodeError khi tool như video-use in ký tự đặc biệt ra console cp1252.
- **Giá trị che "••••" không còn đè được key ElevenLabs thật**: client lạ lấy cài đặt từ GET /settings (key hiển thị dạng che) rồi POST nguyên object về sẽ không làm mất key đã lưu nữa.

## [0.9.29] - 2026-07-10
### Thêm mới
- **Nút tắt/bật giọng đọc ngay trên khung chat**: thêm một nút loa cạnh nút mic và đính kèm ở thanh nhập chat (hiện ở cả màn 3D lẫn tab Trò chuyện). Bấm để tắt/bật việc Javis đọc câu trả lời bằng giọng mà không phải lên góc trên hay vào Cài đặt. Khi tắt, nút chuyển màu đỏ kèm gạch chéo cho dễ thấy; trạng thái đồng bộ hai chiều với nút loa ở header và công tắc "Đọc trả lời bằng giọng" trong Cài đặt nhanh, và nhớ qua các lần tải lại.

## [0.9.28] - 2026-07-09
### Thêm mới
- **Telegram hiện trạng thái trung gian khi chờ**: trước đây nhắn cho Javis qua Telegram rồi phải chờ im lặng tới khi có câu trả lời, dễ tưởng bị treo. Nay bot gửi một tin trạng thái ("🤔 Javis đang xử lý…") rồi tự cập nhật theo tiến trình thật của lượt (đang gọi công cụ nào, đã nhận dữ liệu, đang soạn câu trả lời); soạn xong thì xoá tin trạng thái và gửi câu trả lời. Có tiết chế nhịp cập nhật (~2.5s) để không spam / dính giới hạn của Telegram. Áp dụng cho cả engine Claude Code lẫn engine API.

## [0.9.27] - 2026-07-09
### Thêm mới
- **Click node trên graph 3D mở popup đọc/sửa note**: trước đây bấm một node trên biểu đồ là gửi thẳng một câu hỏi vào khung chat (gây nhầm lẫn). Nay bấm node mở một cửa sổ hiện nội dung note để đọc và sửa trực tiếp rồi Lưu (đọc/ghi qua đúng API Tệp tin), kèm nút mở tab mới; nhấn Esc hoặc ✕ để đóng.
### Cải thiện
- **Esc không còn dừng câu trả lời / ngắt Javis đang nói**: trước đây nhấn Esc vừa tạm dừng giọng đọc vừa ngắt luôn lượt đang chạy, rất dễ lỡ tay mất câu trả lời. Nay Esc chỉ thoát chế độ rảnh tay, tắt mic và đóng popup. Muốn dừng thì dùng nút Dừng (ô đỏ) hoặc nút bật/tắt tiếng.

## [0.9.26] - 2026-07-09
### Thêm mới
- **Nhiều hội thoại chạy song song (như Claude)**: bấm "Hội thoại mới" giờ KHÔNG còn làm dừng hội thoại đang trả lời. Mỗi lượt chat chạy nền độc lập, nên bạn có thể mở một hội thoại mới và hỏi việc khác NGAY trong khi hội thoại cũ vẫn đang generate - cả hai chạy cùng lúc. Danh sách Lịch sử hiện dấu ⏳ ở hội thoại đang trả lời; bấm vào một hội thoại đang chạy nền để xem tiếp phần đang soạn trực tiếp, và mọi lượt tự lưu vào phiên của nó dù bạn đang xem chỗ khác. Nút Dừng chỉ ngắt đúng hội thoại đang xem, các hội thoại nền khác không bị ảnh hưởng.
### Cải thiện
- **Lõi chat xử lý mỗi lượt như một tác vụ nền**: server không còn khoá kiểu một-kết-nối-một-lượt-một-lúc; mỗi lượt có engine riêng và mọi gói gửi kèm session_id để giao diện định tuyến đúng phiên (có khoá ghi để nhiều lượt không xen kẽ làm hỏng gói). Toàn bộ luồng stream, phiên, MCP/skill và giọng nói giữ nguyên. Ngoài ra nếu chưa cài Claude Code CLI mà dùng engine API/OpenRouter thì không còn bị chặn kết nối như trước (báo lỗi theo từng lượt nếu thực sự cần CLI).

## [0.9.25] - 2026-07-09
### Thêm mới
- **Tab "Trò chuyện" - màn chat riêng, rộng rãi**: thêm tab mới trên thanh bên trái (ngay dưới "Javis") mở khung chat toàn màn hình kiểu Claude, tiện hơn hẳn khung chat chật ở cạnh màn hình 3D. Cột trái là lịch sử hội thoại (nút tạo mới, ô tìm trong mọi hội thoại, nhóm theo Hôm nay / 7 ngày qua / Cũ hơn, đổi tên và xoá, phiên đang mở được tô sáng); giữa là khung chat lớn dễ đọc kèm tiêu đề và badge engine thật (vd "CLI · opus"); ngay trên ô nhập là thanh chọn model + effort, dưới cùng là ô gõ kèm nút mic và đính kèm file. Tab này KHÔNG viết lại bộ máy chat mà dùng lại chính khung chat của màn 3D (mượn rồi trả về khi rời tab) nên cùng một cuộc trò chuyện hiện ở cả hai nơi, giữ nguyên WebSocket, stream, phiên, giọng nói và đính kèm; rời tab thì màn 3D vẫn chat bình thường. Vào tab chat, đồ hoạ 3D tự tắt cho nhẹ máy. Màn hẹp (điện thoại) thì cột lịch sử thu thành ngăn kéo, bấm nút 🕘 để mở.
### Sửa lỗi
- **Chống mất nội dung khi đổi trang nhanh**: mỗi lần chuyển trang quản lý, khung nội dung (`#cviewBody`) được thay bằng một vùng mới, nên nếu một trang tải chậm (Tổng quan, Models, Kết nối...) trả kết quả về TRỄ sau khi bạn đã sang trang khác thì cú ghi đó rơi vào vùng cũ đã bỏ, không đè lên trang đang xem. Trước đây chuyển thật nhanh từ một trang tải-chậm sang tab Trò chuyện có thể xoá mất khung chat vừa mở; nay đã an toàn, đồng thời hết luôn hiện tượng thoáng thấy nội dung trang cũ khi đổi trang.

## [0.9.20] - 2026-07-09
### Thêm mới
- **Loop và Việc tự báo kết quả về Telegram người yêu cầu**: giờ là hành vi mặc định của Javis - mỗi vòng loop chạy nền chạy xong, và mỗi việc (Kanban task) hoàn tất, đều tự nhắn kết quả về Telegram của đúng người đã yêu cầu (kèm tóm tắt, dòng kiểm chứng, và cảnh báo nếu loop tự tạm dừng). Loop hoặc việc tạo trên bản web (không rõ chủ) thì báo về ID Telegram đầu tiên trong whitelist. Loop lưu thêm `owner_chat` (chat_id người tạo) trong frontmatter; việc lưu `chat_id` tương ứng - Javis tự gắn khi bạn tạo qua chat. Vòng bị bỏ qua vì chưa có số liệu thì không nhắn để khỏi làm phiền; muốn một loop ngừng báo mỗi vòng thì đặt `notify: false` trong frontmatter loop đó.

- **Khung chat render chân thật như Claude, xem được Artifact**: câu trả lời của AI giờ hiện đầy đủ như trên khung chat Claude. Khi trả về một trang HTML tự chứa, ảnh SVG, sơ đồ mermaid hoặc một file code dài, Javis hiện một thẻ artifact gọn trong luồng chat; bấm vào mở một panel bên phải có tab Xem trước / Mã nguồn cùng nút Copy và Tải về. HTML chạy trong iframe sandbox cô lập (không đụng được trang cha), SVG render không cho script, mermaid vẽ thành sơ đồ (offline thì tự hạ xuống hiện mã nguồn kèm ghi chú). Nhấn Esc để đóng panel, không thu nhỏ luôn khung chat đang phóng to.
### Cải thiện
- **Markdown và code block đầy đủ hơn**: thêm heading nhiều cấp, danh sách đánh số + lồng nhau + checkbox, blockquote, đường kẻ ngang, in nghiêng, gạch ngang; code block có nhãn ngôn ngữ và tô màu cú pháp, giữ nút Copy. Lúc đang stream, đoạn code chưa đóng vẫn hiện gọn dạng khối code đang gõ thay vì chữ thô. Bộ render tách sang file riêng `dashboard/chat-render.js`, giữ nguyên số liệu panel trái, ảnh vault và link như cũ.

## [0.9.18] - 2026-07-07
### Cải thiện
- **Menu đổi model + effort có luôn trong khung chat phóng to**: trước đây thanh chọn model chỉ hiện ở khung chat thường; khi bấm phóng to hội thoại (nút ⛶ / Thu nhỏ bằng Esc) thì thanh này bị bỏ lại nên không thấy. Nay khi vào chế độ toàn màn hình, thanh chọn model được đưa theo vào ngay trên ô nhập, mở menu chọn nhà cung cấp/model và đổi effort bình thường; thu nhỏ lại thì trả về đúng chỗ cũ.

## [0.9.17] - 2026-07-07
### Thêm mới
- **Đổi model + effort ngay trên khung chat**: thêm một thanh nhỏ ngay phía trên ô chat của dashboard, hiện nhà cung cấp, model và mức "Suy nghĩ" (effort) đang chạy. Bấm vào mở một menu gộp: danh sách model gom theo 6 nhà cung cấp (Claude Code, ChatGPT, OpenRouter, Anthropic API, OpenAI API, Google Gemini), có ô tìm model và hàng chọn effort (Tắt/Thấp/Vừa/Cao) ở dưới. Nhà cung cấp đã nối thì bung ra chọn model (danh sách nạp động theo tài khoản), nhà cung cấp chưa nối hiện khoá kèm lối tắt sang trang Models để thêm key. Chọn model hay effort là lưu ngay vào cấu hình và có hiệu lực ở lượt chat kế, badge engine tự cập nhật. Toàn bộ tái dùng các endpoint sẵn có nên không đổi luồng chat/engine.

## [0.9.16] - 2026-07-07
### Thêm mới
- **Tự khởi động cùng máy (Windows)**: thêm mục "Khởi động cùng máy" ở trang Tổng quan để bật/tắt việc Javis tự chạy khi mở máy. Bật lên là Javis chạy nền ẩn ngay sau khi bạn đăng nhập Windows (không cửa sổ đen, mở `localhost:7777` để dùng), và tự tắt bản cũ trước khi chạy nên không mở trùng. Cơ chế dùng khóa registry theo tài khoản (`HKCU...\Run`, không cần quyền admin) trỏ tới `start-javis.vbs` sẵn có; kèm 2 endpoint `/autostart` để xem trạng thái và bật/tắt, có cờ nhận biết khi bạn dời thư mục cài đặt. Mục này tự ẩn trên bản Docker/Linux.
- **Nhắc hẹn từ chat**: nói kiểu "30 phút nữa nhắc anh...", "8h30 sáng mai nhắc...", "mỗi sáng 7h nhắc uống thuốc" là Javis tự đặt lịch, tới giờ tự thức dậy bắn nhắc qua Telegram cho đúng người đang nói. Hẹn được theo số phút, theo giờ trong ngày, theo ngày cụ thể, hoặc lịch định kỳ bằng biểu thức cron; server tự tính giờ Việt Nam nên chỉ cần nói bằng lời. Ba chế độ: chỉ nhắc lại (notify), tự làm việc rồi gửi kết quả về (task), hoặc chạy một script giám sát KHÔNG cần AI cho rẻ (script, chỉ chạy file bạn đã bỏ sẵn trong `Javis/scripts`). Nhắc hẹn hiện luôn ở trang Việc/Lịch, gạt công tắc để huỷ.
- **Thêm nhà cung cấp Google Gemini**: cắm API key Gemini là dùng được các model 2.5 Flash/Pro và 2.0 Flash để chat, kể cả chế độ agent dùng MCP của Javis y như OpenAI. Đi qua endpoint tương thích OpenAI nên tận dụng lại đúng luồng stream + tool-calling; danh sách model nạp động theo tài khoản, và bật "Suy nghĩ" áp cho model 2.5 trở lên.
- **Skill HTML → Webcake (.pke)**: chuyển một file hoặc đoạn HTML thành file Webcake mở sửa được trên trình dựng landing - đọc HTML, tái dựng thành `page_source` đúng khuôn Webcake rồi xuất `.pke` để tải lên chỉnh tiếp.

## [0.9.15] - 2026-07-06
### Sửa lỗi
- **Favicon giờ khớp logo app**: icon trên tab trình duyệt trước đây vẫn là ảnh mặc định cũ dù link đã trỏ đúng. Nguyên nhân: đường `/favicon.ico` (trình duyệt LUÔN tự gọi) trả về 404 nên trình duyệt giữ icon cache cũ. Đã thêm route trả thẳng logo hiện tại (mặc định `logo.png`, tự đổi theo ảnh bạn tải lên). Trình duyệt cache favicon rất lì nên cần đóng mở lại tab để thấy icon mới.
- **Dải trống bên trên khung chat**: lưới `.hud` khai báo thiếu một hàng nên thanh đính kèm (lúc trống) chiếm mất hàng 70px, để lại một dải trống chạy hết bề ngang ngay trên ô nhập. Đã thêm hàng `auto` cho thanh đính kèm để nó co về 0 khi trống; phần thân giờ giãn hết xuống sát ô chat.
- **Nút "Lịch sử" đè lên nút header**: nút "Lịch sử" để nổi cố định ở góc phải, che mất các nút Cài đặt / Đọc / Reset hội thoại phía dưới. Đã đưa nút vào nằm chung hàng với dãy nút header nên không còn chồng lên nhau.

## [0.9.14] - 2026-07-06
### Thêm mới
- **Panel "Mức dùng" - đo token đa nhà cung cấp**: sidebar giờ hiện lượng token Javis **tự đo** qua từng nhà cung cấp/model trong ngày (vào ↑ / ra ↓ + ước tính chi phí ở nơi provider trả về, vd Claude Code), cộng tổng. Đồng nhất cho mọi engine (Claude Code, ChatGPT/Codex, OpenRouter, OpenAI API, Anthropic API) vì Javis đọc usage trong mọi phản hồi. Kèm **số dư THẬT của OpenRouter** nếu đã cắm key (provider duy nhất lộ số dư qua API). Đây là lượng Javis dùng, KHÔNG phải hạn mức gói thuê bao - đa số nhà cung cấp không cho lấy hạn mức tài khoản qua API nên xem trong app của họ.

## [0.9.13] - 2026-07-06
### Thêm mới
- **Chia sẻ agent / skill / workflow qua file**: mỗi agent, skill, workflow giờ có nút **⤓ Xuất** để tải về một gói `.zip`, và mỗi trang (Agents / Skills / Workflows) có nút **⤒ Nhập** để tải gói lên - trao đổi năng lực với người khác dễ dàng. Gói workflow tự **kèm các agent nó dùng + skill của agent** (skill của bạn, KHÔNG kèm skill hệ thống) để bên nhận chạy được ngay; gói agent kèm skill của nó. Nhập chấp nhận `.zip`, file `.md` lẻ (agent/workflow), và **cả gói skill `.skill` của Claude** (Javis tự nhận diện `SKILL.md` trong gói và đưa vào đúng thư mục skill). Có rào an toàn (chống zip-slip, giới hạn dung lượng) và trùng tên thì bỏ qua trừ khi bạn chọn ghi đè.

## [0.9.12] - 2026-07-06
### Bảo mật
- **Vá 2 lỗ hổng DoS trong thư viện nền** (CVE-2024-47874 Starlette, CVE-2024-53981 python-multipart): nâng fastapi lên 0.115.6 (kéo Starlette lên 0.41.3) và python-multipart lên 0.0.18. Trước đây kẻ tấn công CHƯA đăng nhập có thể gửi multipart form dị dạng vào endpoint công khai (đăng nhập / thiết lập) để làm quá tải server VPS.
- **Chặn XSS trong dashboard**: các hàm escape giờ escape cả dấu nháy (`"` và `'`), tránh nội dung do AI/MCP sinh ra (tên file, nội dung task...) thoát khỏi thuộc tính HTML và chạy JavaScript same-origin điều khiển Javis. Ngoài ra link ngoài (kết quả tìm kiếm, URL xác thực) chỉ được render khi là http/https, chặn scheme `javascript:`.

## [0.9.11] - 2026-07-06
### Thêm mới
- **X (Twitter) vào kho Kết nối** (MCP chính chủ của X, remote): tìm và đọc bài đăng, xem hồ sơ và số liệu công khai. Dán Bearer Token App-only từ X Developer Portal; mặc định Chỉ đọc (token app-only không đăng bài/nhắn tin được nên an toàn). Đăng bài theo tài khoản người dùng cần OAuth - sẽ bổ sung khi bạn cần.
### Cải thiện
- **Logo thương hiệu cho connector**: X, Higgsfield, TikTok Ads, Google Ads và Gmail giờ hiện logo thật thay cho biểu tượng emoji.

## [0.9.10] - 2026-07-06
### Thêm mới
- **Higgsfield vào kho Kết nối** (MCP chính chủ, remote): tạo và chỉnh ảnh/video bằng AI - sinh ảnh, sinh video, nâng nét (upscale), mở rộng khung hình, xoá nền, cắt nhân vật, điều khiển chuyển động. Đăng nhập Higgsfield 1 chạm: Javis tự đăng ký ứng dụng theo chuẩn OAuth của MCP (tự dò metadata + DCR + PKCE, không cần tạo app hay dán key), dùng được trên mọi engine. Mặc định mức Ghi nháp để Javis tạo được nội dung ngay và chặn thao tác xoá/thanh toán; mỗi lần tạo tiêu credit Higgsfield trả trước của bạn.

## [0.9.9] - 2026-07-06
### Thêm mới
- **Xem ảnh và mở file ngay trong chat + trang Tệp tin**: Javis nhúng được ảnh vào câu trả lời (hiện luôn trong khung chat, bấm là mở full ở tab mới) và đính link mở/tải file như PDF, DOCX, XLSX. Trang Tệp tin xem trước được ảnh và PDF ngay trong app; file khác có nút "Mở" ra tab mới bằng đường dẫn tĩnh. Thêm endpoint `/files/raw` phục vụ file inline (khác `/files/download` luôn ép tải).
### Sửa lỗi
- **Ảnh/file trong chat bấm vào không xem được; trang Tệp tin không xem được ảnh và không mở được PDF/DOCX** (chỉ tải về): do khung chat chưa render ảnh/link markdown và chưa có URL phục vụ file inline. Nay hiển thị ảnh, mở PDF trong app, và mọi file đều có đường dẫn tĩnh để mở/tải.

## [0.9.8] - 2026-07-06
### Thêm mới
- **Skill chạy trên MỌI engine, hết phụ thuộc cấu trúc của Claude**: trước đây skill chỉ hoạt động ngon trên Claude Code (đọc native từ `.claude/skills`), còn ChatGPT/Codex thì gọi không ra. Nay Javis có một **skill router riêng** dùng chung cho mọi engine: danh sách skill (tên + mô tả) được bơm thẳng vào system prompt, kèm tool `javis_use_skill` để nạp nội dung skill và làm theo. Claude Code, ChatGPT/Codex, OpenRouter, OpenAI API và Anthropic API giờ đều dùng được skill như nhau.
- **Nơi lưu skill chuyển sang `skills/` (phẳng, do Javis sở hữu)**: đồng bộ với `agents/`, `workflows/`, `memory/`. Brain cũ để skill ở `.claude/skills` được **tự dời sang `skills/`** một lần (an toàn, không mất dữ liệu, giữ nguyên skill đang tắt). Javis vẫn tự **mirror** sang `.claude/skills` để Claude Code nạp native như một điểm cộng - nhưng router chính không còn phụ thuộc thư mục đó nữa.
### Cải thiện
- **Skill do Javis tự học giờ BẬT sẵn** (thay vì để nháp tắt chờ duyệt), đánh dấu `origin: javis-learned` để nhận diện; vẫn tuyệt đối KHÔNG ghi đè skill bạn đã có và KHÔNG hồi sinh skill bạn cố ý tắt.
### Sửa lỗi
- **ChatGPT/Codex không tìm thấy skill**: nhánh chat qua Codex trước đây không được nạp system prompt của Javis và chạy sai thư mục làm việc nên không thấy skill nào. Nay Codex chạy đúng thư mục brain và nhận đủ router skill, gọi được skill người dùng đã tạo.
- **Sửa skill đang tắt bị rỗng nội dung**: nút Sửa trước đây chỉ đọc skill ở vị trí bật nên skill đang tắt mở ra form trống. Nay đọc được cả skill trong `.disabled`; và Lưu khi sửa giữ nguyên trạng thái bật/tắt (không tự bật skill đang tắt, không để lại bản nháp mồ côi).

## [0.9.7] - 2026-07-05
### Cải thiện
- **Giọng nói mượt hơn, hết chèn giọng lạ, biết dừng khi bạn nói**: (1) audio đầu tiên phát NHANH hơn - tách câu đầu ra đoạn nhỏ để tổng hợp + tải tức thì, bớt cảnh khựng vài giây sau khi chữ đã hiện; (2) khi một đoạn đọc lỗi mạng, Javis thử lại đúng giọng Việt và TUYỆT ĐỐI không rơi về giọng mặc định trình duyệt (thường là tiếng Anh) - hết cảnh "giọng Anh lạ chèn giữa chừng"; (3) ngắt lời (barge-in) khi rảnh tay: đang đọc mà nghe bạn nói đủ rõ thì tự dừng và mở nghe ngay, kèm bật khử vọng/khử ồn mic để đỡ nghe lại chính giọng mình.
### Sửa lỗi
- Một đoạn đọc lỗi trước đây bị xử lý 2 lần (Chrome bắn cả sự kiện error lẫn play() reject cho cùng audio) gây 2 luồng đọc chồng nhau và audio không dừng được; nay mỗi đoạn lỗi chỉ xử lý đúng một lần.

## [0.9.6] - 2026-07-04
### Cải thiện
- **Trang Cài đặt gọn và hợp lý hơn**: gộp "Nhà cung cấp giọng đọc" vào chung nhóm Giọng nói (trước đây nằm tách tận cuối trang, sau avatar và tên miền); bỏ nút "Nghe thử" bị trùng (giữ 1 nút duy nhất); ẩn danh sách giọng Edge (HoaiMy/NamMinh) khi chọn provider OpenAI/ElevenLabs vì lúc đó chọn giọng ngay trong khối provider; sửa tiêu đề gây hiểu nhầm (bỏ "Giao diện" vì không có mục đó); nút nghe thử chuyển sang viền để nút Lưu nổi đúng vai trò chính.
- **Thông báo cập nhật bản Docker rõ ràng hơn**: bản Docker không bật Watchtower giờ hướng dẫn thẳng cách **Redeploy** để lấy image mới nhất (Hostinger bấm nút Redeploy trong Docker Manager; VPS chạy `docker compose up -d --pull always`), thay vì bảo "tự thêm service watchtower". Panel Phiên bản hiện luôn hướng dẫn này khi có bản mới mà không tự cập nhật tại chỗ được, không còn để bấm nút "Cập nhật ngay" rồi mới báo lỗi.
### Sửa lỗi
- Nút "Cập nhật ngay" trước đây coi là tự cập nhật được chỉ vì biến `WATCHTOWER_TOKEN` có sẵn trong compose (dù Watchtower chưa chạy), bấm vào trigger âm thầm thất bại rồi báo "phiên bản chưa đổi". Nay **dò Watchtower thật** (kiểm tra cổng, không gửi HTTP để khỏi kích hoạt update nhầm) mới quyết định, tránh báo nhầm.

## [0.9.5] - 2026-07-04
### Thêm mới
- **Lark** vào kho Kết nối (MCP chính chủ của Lark/LarkSuite, chạy local qua `@larksuiteoapi/lark-mcp`): nhắn tin, tài liệu (Docs), bảng dữ liệu (Base/Bitable), wiki, danh bạ. Tạo một Lark app rồi dán App ID + App Secret; Javis chỉ làm được đúng quyền bạn cấp cho app. Cần Node.js 18+. Mặc định Chỉ đọc; gửi tin nhắn và cấp quyền file là hành động nguy hiểm (phải Toàn quyền). Phân loại quyền theo 19 tool thật đã kiểm chứng.
- **Logo Zalo và Google Sheets**: hai connector này giờ hiện logo thật thay cho emoji.

## [0.9.4] - 2026-07-04
### Thêm mới
- **Slack** vào kho Kết nối (MCP chính chủ của Slack, remote): tìm/đọc/gửi tin, xem kênh và thành viên, quản lý canvas. Đăng nhập bằng OAuth qua một Slack app của chính bạn (Slack không cho tự đăng ký client, cần tạo app trong workspace + admin duyệt). Mặc định Chỉ đọc; gửi tin phải nâng Toàn quyền.
- **Systeme.io** vào kho Kết nối (MCP chính chủ, remote): quản lý liên hệ, tag, trường tuỳ biến, newsletter, phễu. Chỉ cần dán MCP key (tạo trong Cài đặt hồ sơ, hạn tối đa 90 ngày). Mặc định Chỉ đọc.
- **Logo thương hiệu cho connector**: các thẻ trong kho Kết nối giờ hiện logo thật (Pancake POS, Botcake, Webcake, Meta Ads, Google Calendar, Gmail, Slack, Systeme.io) thay cho biểu tượng emoji; connector chưa có logo vẫn dùng emoji như cũ.
### Cải thiện
- Nhánh OAuth explicit của hub nhận thêm 2 tinh chỉnh theo hãng: tên tham số scope và dấu ngăn (Slack dùng `user_scope` + dấu phẩy cho token người dùng, Google giữ `scope` + dấu cách) - để hỗ trợ đúng các nhà cung cấp OAuth không theo chuẩn chung.

## [0.9.3] - 2026-07-04
### Thêm mới
- **Kho Kết nối có Google Calendar và Gmail** (MCP chính chủ của Google, remote - chạy được cả trên VPS): Calendar xem lịch, tìm chỗ trống, tạo/sửa/xoá sự kiện; Gmail đọc/tìm thư, soạn NHÁP, gắn nhãn. Gmail bản chính chủ KHÔNG có tool gửi thẳng nên Javis luôn dừng ở bản nháp để bạn tự bấm gửi. Đăng nhập Google ngay trong dashboard; cần tạo OAuth client 1 lần (~10 phút, hướng dẫn từng bước trong cửa sổ kết nối, dùng chung 1 client cho cả hai). Mặc định Chỉ đọc; nâng lên Ghi nháp để tạo sự kiện/soạn nháp, Toàn quyền mới xoá được sự kiện.
### Cải thiện
- Hub OAuth giờ nhận **client tự khai (BYO client_id/secret)** cho nhà cung cấp không hỗ trợ tự đăng ký client như Google (trước đây chỉ chạy với server có DCR). Tự xin `access_type=offline` để giữ kết nối lâu dài (tự làm mới token), gửi kèm client secret khi đổi/làm mới token, và tự đặt tên tài khoản bằng email Google sau khi đăng nhập.

## [0.9.2] - 2026-07-04
### Thêm mới
- **Kho Kết nối có nhóm Quảng cáo - đủ 3 nền tảng lớn**: **Meta Ads** (Facebook & Instagram) qua MCP chính chủ của Meta - bấm Kết nối là đăng nhập Facebook, không cần tạo app hay dán key; **Google Ads** qua MCP chính chủ của Google (chỉ đọc, truy vấn GAQL: chi phí, chuyển đổi, từ khoá); **TikTok Ads** qua server cộng đồng trên Marketing API chính thức (chỉ đọc - TikTok chưa mở MCP chính chủ, khi mở sẽ thay trong kho). Cả 3 mặc định Chỉ đọc; Meta bật Toàn quyền mới tạo/sửa được chiến dịch (cảnh báo tiền thật, chiến dịch tạo mới luôn ở trạng thái tạm dừng chờ bạn tự bật).
### Cải thiện
- Kết nối OAuth (vd Meta Ads) sau khi đăng nhập giờ **tự đặt tên tài khoản** (lấy đúng tên tài khoản ads) như flow dán key, và ghi ngay profile MCP cho Codex - trước đây tên để mặc định và Codex phải đợi lần đổi cấu hình sau.

## [0.9.1] - 2026-07-04
### Sửa lỗi
- `start-javis.bat` chạy server ẩn hoàn toàn - hết cửa sổ CMD đen nằm lì.

## [0.9.0] - 2026-07-04
### Thêm mới
- **Trang "Kết nối" thay trang MCP**: kho connector cài sẵn (Pancake POS, Zalo cá nhân, Webcake Landing, Botcake) - bấm Kết nối, dán key (hoặc quét QR với Zalo) là xong, không còn tự gõ URL/transport/header. Javis tự kiểm tra key và tự đặt tên tài khoản (lấy đúng tên cửa hàng từ POS). Form kỹ thuật cũ vẫn còn ở card "Tự thêm (nâng cao)".
- **Đa tài khoản chính thức**: một dịch vụ nối NHIỀU tài khoản (nhiều shop POS, nhiều số Zalo) - mỗi tài khoản một chip có tên + quyền + dấu mặc định, thêm/tắt/xoá từng cái. Zalo mỗi tài khoản chạy cô lập (home riêng) nên nhiều số chạy song song không giẫm nhau.
- **MCP HUB**: mọi bộ não (Claude Code, ChatGPT/Codex, OpenRouter, OpenAI API, Anthropic API) đấu qua MỘT điểm - Codex và engine API giờ dùng được cả MCP local dạng stdio (Zalo, Webcake) chứ không chỉ http như trước.
- **Anthropic API có vòng gọi tool** - hết cảnh "chat thuần không MCP". Engine API còn được thêm tool đọc/ghi file trong vault, `javis_use_skill` (kích hoạt skill của brain) và `javis_connections` - engine nào cũng là agent thực thụ.
- **Phân quyền 3 mức mỗi kết nối** (Chỉ đọc / Ghi nháp / Toàn quyền) chặn CỨNG tại hub theo từng lời gọi, hiểu cả tool đa hành động kiểu Pancake (`action=list` cho qua, `action=create` chặn). Loop nền mode suggest/auto bị hub chặn hành động ghi/tiền-đơn bất kể prompt nói gì. Bật Toàn quyền phải tick xác nhận rủi ro; Zalo có cảnh báo riêng về nguy cơ bị khoá tài khoản (API không chính thức).
- **Nhật ký gọi tool (audit)** xem theo từng kết nối, nút Test lại, rate limit chống spam cho Zalo.
- **Đăng nhập Zalo bằng quét QR ngay trong dashboard**: Javis tự chạy zalo-agent-cli, hiện mã QR trong modal, quét xong tự tạo kết nối (cần Node.js 20+).
- **OAuth chuẩn MCP** (PKCE + tự đăng ký client): server nào theo chuẩn thì bấm Kết nối là xong ngay trên VPS, Javis tự giữ và tự refresh token - bỏ cảnh mở terminal gõ /mcp.
- Cầu nối **Botcake** tự viết qua Public API v1 (13 tool: khách hàng, tag, flow, gửi flow, keyword...) - không cần cài gì thêm.
- **3 card Google cho kinh doanh**: Google Sheets (đổ báo cáo doanh thu/tồn kho ra bảng tính - dán service account JSON là chạy, không cần đăng nhập), Google Search Console (số liệu SEO: khách tìm gì ra website), Google Workspace (Gmail + Lịch + Drive + Docs trong 1 kết nối, OAuth tự tạo có hướng dẫn từng bước; mặc định Ghi nháp - soạn nháp được nhưng KHÔNG tự gửi mail/xoá, bật Toàn quyền phải xác nhận). Kho hỗ trợ field dạng file (dán JSON, Javis tự lo phần còn lại) và tự kèm sẵn uv/uvx để chạy connector Python.
### Cải thiện
- MCP client có **session pool sống lâu** (giữ kết nối giữa các tin nhắn) + hỗ trợ stdio/internal: hết cảnh "mỗi tin nhắn kết nối MCP lại nên hơi chậm". Hub tự làm nóng lúc khởi động.
- Registry MCP chuyển sang STATE_DIR (Docker ghi được) và **tự migrate** từ bản cũ: server cũ thành connection, backup nguyên bản ở `mcp_servers.v1.bak.json`, không mất dữ liệu.
### Bảo mật
- API key/token của kết nối **mã hoá at rest** (Fernet, key riêng theo máy). Nhật ký audit chỉ ghi TÊN tham số, không ghi giá trị. Endpoint hub xác thực bằng token nội bộ riêng, không dùng session dashboard.

## [0.8.13] - 2026-07-03
### Cải thiện
- Bảng chọn model trong Telegram làm lại theo UX gateway Hermes: chọn provider ĐÃ KẾT NỐI (Claude Code, **ChatGPT**, OpenRouter, Claude API, OpenAI API - trước đây thiếu hẳn ChatGPT) có dấu ✓ + số model, rồi lưới model 2 cột **phân trang ◀ 1/N ▶**. Danh sách model lấy LIVE từ provider (OpenRouter đủ vài trăm model thay vì vài cái trong catalog; ChatGPT hiện model Codex), có mẹo gõ `/model <id>` chọn nhanh.
- Gõ tay `/model gpt-5.5` hoặc `/model gpt-5.3-codex` giờ tự hiểu là ChatGPT (Codex) nếu đã kết nối OAuth, không còn bị nhét nhầm sang Claude.

## [0.8.12] - 2026-07-03
### Thêm mới
- Telegram có lệnh **`/brain`** - xem và đổi brain (vault) cho RIÊNG phiên của mình: gõ `/brain` mở bảng nút bấm chọn (brain đang dùng có dấu ✓), hoặc gõ thẳng tên `/brain <tên>` (khớp một phần cũng được). Đổi xong hội thoại tự reset để nạp đúng bộ nhớ/skill của brain mới; người khác dùng chung bot và dashboard KHÔNG bị ảnh hưởng. `/reset` giữ nguyên brain đã chọn.
- File gửi lên Telegram giờ rơi vào `inbox/telegram` của brain PHIÊN người gửi (trước đây luôn vào brain mặc định).
- `/status` hiển thị brain phiên đang dùng.

## [0.8.11] - 2026-07-03
### Thêm mới
- Telegram **đa phiên theo tài khoản**: mỗi chat ID giờ có ngữ cảnh hội thoại RIÊNG, không còn lẫn lộn khi nhiều người dùng chung 1 bot. Trước đây tất cả người dùng dùng chung một session (người sau nối tiếp mạch của người trước, và chỉ 1 người được trả lời tại một thời điểm). Nay mỗi tài khoản có session Claude riêng (giữ `--resume` độc lập), lịch sử OpenRouter riêng, câu `/retry` riêng.
- Các tài khoản **chạy song song**: A đang được trả lời thì B hỏi vẫn được xử lý ngay, không phải xếp hàng chờ. Trong CÙNG một tài khoản vẫn tuần tự 1 lượt/lúc (gửi câu mới khi đang bận sẽ báo "đang xử lý câu trước").
- `/reset` và `/stop` chỉ tác động **phiên của chính người gõ**: reset xoá đúng ngữ cảnh của họ, stop chỉ giết đúng tiến trình Claude của họ (không đụng người khác đang chat). `/status` hiển thị mã phiên.
- File Javis tạo ra gửi về **đúng người đang hỏi**: endpoint `POST /telegram/send-file` nhận thêm `chat_id`, và gateway nhắc engine luôn gắn chat_id của người hỏi vào lệnh gửi (thiếu thì rơi về chủ bot như cũ). Whitelist vẫn chặn ID lạ.
### Sửa lỗi
- Dashboard web: nút **Stop không còn giết nhầm lượt của người khác** đang chat song song. Mỗi kết nối WebSocket giờ có tag phiên riêng (server phát qua message hello, frontend gửi kèm khi POST `/stop`) - web vốn đã đa phiên (mỗi tab/kết nối một session, lưu SQLite resume được), đây là lỗ hổng chéo duy nhất còn lại.
- Khung chat **phóng to (chat workspace) trước đây KHÔNG hiện trạng thái** "đang suy nghĩ / đang gọi tool": thanh trạng thái cũ nằm ngoài `#chatArea` nên bị bỏ lại khi phóng to. Đã thay bằng chip hoạt động ngay trong khung chat.
### Cải thiện
- **Chip hoạt động trong khung chat** (cả thường lẫn phóng to): bong bóng 3 chấm nhún + dòng trạng thái sống ("Javis đang suy nghĩ...", "⚙ Đang gọi: pos_statistics", "✍ Đang soạn câu trả lời...") + đồng hồ đếm giây khi đợi lâu (hiện từ giây thứ 3). Chip hiện NGAY khi bấm gửi, luôn nằm dưới cùng kể cả dưới bubble đang stream, tự biến mất khi xong lượt.

## [0.8.10] - 2026-07-03
### Thêm mới
- Telegram hỗ trợ **NHIỀU chat ID** dùng chung 1 bot: ô "Chat ID được phép dùng" giờ nhận nhiều ID cách nhau dấu phẩy (vd `123456789, 987654321`) - thêm người thân/nhân viên nhắn với Javis mà không phải dựng bot riêng. Whitelist chặn đúng theo danh sách; ID nhóm (số âm) cũng dùng được.
- Nút **Gửi test** gửi tin thử tới TẤT CẢ ID và báo rõ ID nào lỗi (thường do người đó chưa bấm Start bot); thông báo nền (loop tự tạm dừng...) cũng gửi tới tất cả ID; dòng trạng thái hiện số ID được phép, cảnh báo rõ khi đang để trống (mọi người nhắn được). File tự gửi về Telegram không kèm chat cụ thể sẽ về ID ĐẦU TIÊN (chủ bot).
- Tương thích ngược hoàn toàn: cấu hình 1 ID cũ giữ nguyên, không phải làm lại gì.

## [0.8.9] - 2026-07-03
### Thêm mới
- **Trang chủ giới thiệu** (`website/index.html`): landing page 1 file HTML/CSS/JS thuần, phong cách dark nebula đồng bộ dashboard - hero gõ chữ tự động, nền đồ thị hạt sao canvas, bảng so sánh chatbot vs Javis, bento 8 tính năng, mockup Telegram có bong bóng chạy, timeline 3 bước deploy, section giới thiệu tác giả Nguyễn Minh Quý, FAQ accordion, nút copy lệnh. Mọi link tài liệu trỏ về GitHub; KHÔNG hiển thị số phiên bản trên trang. Dùng ảnh thật: screenshot đồ thị tri thức trong ô tính năng lớn (kiêm og:image khi share) + chân dung tác giả (fallback chữ MQ nếu ảnh lỗi).

## [0.8.8] - 2026-07-03
### Sửa lỗi
- Đổi tên file mẫu `.env.example` → `env.example` (bỏ dấu chấm đầu): Docker Manager của Hostinger tự quét file `.env*` trong repo khi deploy từ URL và nhập nguyên nội dung (kể cả dòng chú thích `#`) vào ô Environment, gây một loạt biến đỏ "Invalid variable name" mỗi lần deploy. Ô Environment trên Hostinger giờ chỉ cần đúng 1 biến `DOMAIN_NAME`. Ai đã dính: xoá các dòng có dấu `#` trong ô Environment một lần là sạch vĩnh viễn. Chạy local không đổi gì ngoài lệnh copy: `cp env.example .env`.

## [0.8.7] - 2026-07-03
### Thêm mới
- **Telegram thành kênh làm việc đầy đủ** (port ý tưởng gateway của hermes-agent):
  - Javis giờ **biết mình đang trả lời qua kênh nào**: gateway chèn block "Kênh hội thoại hiện tại" (Telegram DM/nhóm với ai, chat_id, các nền tảng đang kết nối) vào system prompt mỗi lượt - hỏi "em đang chat với anh qua đâu" là khai đúng, không đoán.
  - **Tự gửi file về Telegram**: file Javis tạo trong lượt (tool Write) hoặc file có đường dẫn tuyệt đối nhắc trong câu trả lời được tự động đính kèm gửi ngay sau câu trả lời (tối đa 10 file/lượt, mỗi file dưới 50MB; ảnh gửi dạng photo có preview, còn lại gửi dạng document).
  - Endpoint nội bộ `POST /telegram/send-file` (CHỈ nhận từ localhost - bên ngoài qua proxy vẫn bị chặn đăng nhập): agent chủ động gửi file bất kỳ có sẵn trên máy giữa lượt bằng curl.
  - **Nhận file/ảnh từ Telegram**: gửi file/ảnh (kèm caption) cho bot là Javis tự tải về `inbox/telegram/` trong brain rồi đọc như file đính kèm trong chat (trần tải 20MB của bot API). Voice/video chưa hỗ trợ - Javis sẽ nói rõ.
  - Tin nhắn trả lời render **MarkdownV2** (đậm/nghiêng/code/link hiện đẹp), tự fallback plain text nếu Telegram từ chối parse - không mất tin.
### Cải thiện
- Dashboard web cũng có block kênh riêng: Javis phân biệt đang nói chuyện qua web hay Telegram, và biết cách đẩy file sang Telegram khi user yêu cầu (nếu bot đang chạy).

## [0.8.6] - 2026-07-02
### Thêm mới
- **Chat workspace**: phóng to chat (nút ⛶ hoặc 🕘 Lịch sử) giờ mở thành không gian làm việc gần full màn hình kiểu Claude/Cowork - cột trái là **sidebar Lịch sử hội thoại** (＋ Hội thoại mới, tìm toàn văn, danh sách nhóm Hôm nay/Hôm qua/7 ngày/Cũ hơn, badge engine + số tin, đổi tên/xoá khi rê chuột, phiên đang mở tô sáng, bấm phát mở lại ngay), cột phải là nội dung chat căn giữa rộng tối đa ~980px. Sidebar ẩn/hiện được (nhớ trạng thái); màn hẹp tự chuyển thành ngăn kéo nổi, Esc đóng ngăn kéo trước rồi mới thu nhỏ chat. Panel Lịch sử trượt bên phải cũ được gỡ, nút 🕘 góc phải mở thẳng workspace.
- Tiện ích đọc/soạn trong chat: nút **⧉ Copy** cho từng khối code + copy cả tin nhắn Javis (hiện khi rê chuột); tin nhắn dài của bạn tự thu gọn sau 10 dòng kèm "Xem thêm"; đang cuộn đọc phía trên thì tin mới KHÔNG kéo giật xuống - hiện nút **↓ Tin mới** ở đáy khung; chip file đính kèm hiển thị ngay trong workspace khi phóng to.
### Sửa lỗi
- Tin nhắn nhiều dòng của bạn (Shift+Enter) trước đây hiển thị dính thành một dòng - giờ giữ nguyên xuống dòng.
- Copy hoạt động cả khi trình duyệt chặn Clipboard API (tự fallback), vd truy cập qua HTTP LAN.

## [0.8.5] - 2026-07-02
### Thay đổi
- Sao lưu GitHub nâng cấp thành **đồng bộ 2 CHIỀU**: mỗi lượt vừa đẩy thay đổi của máy lên repo, vừa kéo thay đổi từ máy khác về và tự hoà nhập. Dùng được nhiều máy chung 1 repo (máy nhà + VPS làm việc xen kẽ, các máy tự khớp nhau) - hết cảnh 2 máy force-push đè mất backup của nhau.
- Xung đột cùng 1 file sửa ở 2 nơi: bản có lần sửa MỚI HƠN thắng, bản thua giữ nguyên thành file `.conflict-<local|remote>-<thời điểm>` ngay cạnh (không âm thầm mất chữ nào); một bên sửa một bên xoá thì bản sửa thắng. Đẩy lên bằng push thường (bỏ force-push); máy khác chen ngang thì tự kéo về hoà tiếp rồi đẩy lại.
- Khôi phục máy mới không cần git tay: dán repo + token rồi bấm Đồng bộ ngay là brain về đủ. Thư mục brains trống được coi là chế độ KHÔI PHỤC - chỉ nhận về, không bao giờ đẩy "trạng thái trống" lên đè backup. File thiếu cục bộ (wipe/volume mới) tự được vá lại từ bản đồng bộ.
### Sửa lỗi
- Đồng bộ truyền byte nguyên văn giữa các máy (tắt autocrlf của git trên mirror) - hết cảnh cùng 1 file lệch CRLF/LF giữa Windows và VPS Linux mãi không khớp.
### Cải thiện
- Trang Tự học: mục đổi tên "⇅ Đồng bộ brain với GitHub (2 chiều)", nút "Đồng bộ ngay" báo kết quả chi tiết (nhận về bao nhiêu file, có đẩy lên không, danh sách file xung đột); trạng thái lần cuối lưu kèm báo cáo. Không đẩy được về máy (file bị khoá) thì HOÃN push để giữ an toàn dữ liệu, lần sau tự thử lại.

## [0.8.4] - 2026-07-02
### Thay đổi
- Tách 2 tầng rõ ràng: **tầng hệ thống** (chức năng mặc định của Javis OS - skill javis-builder / ingest-source / query-wiki / lint-wiki + loop tự-cải-tiến) giờ đi theo mã nguồn app tại `.claude/skills/` và `system/loops/`, cập nhật cùng phiên bản khi update app; **tầng brain** chỉ còn dữ liệu của bạn (ký ức, sources, wiki, agent/skill/workflow/loop tự tạo). Đổi brain không còn mất chức năng mặc định.
- Đồng bộ có manifest (`.javis/system-manifest.json` trong mỗi brain): app lên bản mới thì bản skill/loop hệ thống trong brain được cập nhật theo, NHƯNG file bạn đã sửa thì giữ nguyên bản của bạn (user override); loop giữ nguyên trạng thái bật/tắt, chế độ, chu kỳ bạn đã chỉnh. Lỡ xoá file hệ thống thì tự cài lại (muốn ngừng dùng hãy TẮT skill - trạng thái tắt được tôn trọng qua mọi lần update).
- Lúc khởi động đồng bộ cho MỌI brain trong thư mục brains (trước đây chỉ Brain Default được seed lúc boot, brain tạo ở bản cũ không bao giờ nhận skill mới); brain ngoài chọn qua `path:` được đồng bộ ngay lượt dùng đầu. Nút "Tạo cấu trúc" (vault init) giờ seed đầy đủ như brain mới tạo.
- Skill hệ thống được nạp NATIVE cho chat ở mọi brain (nguồn chuẩn nằm trong thư mục app - engine Claude Code đọc trực tiếp), không còn phụ thuộc bản sao trong brain.
### Cải thiện
- Trang Skills: skill hệ thống có nhãn "hệ thống", không xoá được (chỉ tắt/bật hoặc sửa - sửa thì thành bản riêng của bạn và ngừng tự cập nhật).

## [0.8.3] - 2026-07-02
### Thêm mới
- Javis Index (`Javis/index.md`): chỉ mục tầng vận hành - liệt kê MỌI agent/skill/workflow/loop/lịch trong brain, tự sinh từ file (không sửa tay), kèm dòng tổng quan + cờ sức khoẻ (workflow trỏ agent không tồn tại, agent mồ côi, skill tắt, loop tự tạm dừng). Song song wiki/index.md để bất kỳ AI/engine đọc 1 chỗ là hiểu Javis có năng lực gì.
- Bản gọn (live) được chèn vào system prompt mọi engine (Claude/Codex/OpenRouter) → giải bài toán "đổi model là mất nhận biết skill", và giúp không tạo trùng năng lực. Endpoint GET /javis/index. Tự dựng lại khi khởi động + theo nhịp nền (chỉ ghi khi đổi, không churn git).

## [0.8.2] - 2026-07-02
### Cải thiện
- Engine Tự học siết 3 kỷ luật chống bịa (đồng bộ schema vault): citation cứng cho mọi câu wiki cụ thể, gắn nhãn mục-tiêu-vs-thực-tế (không biến câu tầm nhìn thành claim chắc nịch), giữ mâu thuẫn không ghi đè. Wiki tự sinh giờ ít mà chất, đáng tin để tích luỹ.
### Thêm mới
- 3 skill vận hành Second Brain (seed vào mỗi brain, create-if-missing): **ingest-source** (tiêu hoá source, kèm 3-pass cho source dài), **query-wiki** (trả lời có trích dẫn + lưu lại kết quả giá trị), **lint-wiki** (health-check 8 loại lỗi, chỉ trả checklist). Biến 3 phép toán INGEST/QUERY/LINT từ prose thành công cụ tự kích hoạt, nhất quán đa engine.

## [0.8.1] - 2026-07-02
### Thêm mới
- Brain mặc định giờ là bộ "compounding wiki" phổ quát (không còn tối giản): mỗi brain tự seed schema doc (CLAUDE.md + AGENTS.md để Claude Code lẫn Codex tự nạp) + file điều hướng wiki (index.md, log.md, _open-questions.md) + _session-handoff.md (chuyển giữa các model không mất mạch). Encode pattern tích luỹ tri thức + 3 kỷ luật chống bịa (citation bắt buộc, mục tiêu vs thực tế, mâu thuẫn giữ rõ) + 3 phép toán INGEST/QUERY/LINT.
- Trung lập ngành: KHÔNG seed folder marketing/Bullet Journal; taxonomy mọc dần theo source thật, gói theo-ngành để dành làm opt-in. Tất cả create-if-missing (không đè file bạn đã sửa).

## [0.8.0] - 2026-07-02
### Thay đổi
- Sao lưu GitHub giờ đồng bộ **TOÀN BỘ thư mục brains** (mọi brain) trong MỘT lần thay vì từng brain (sửa lỗi các brain đè nhau khi tự động backup vào cùng repo). Mỗi brain là một thư mục con trong repo; xoá brain khỏi máy thì backup sau cũng bỏ. Khuyến nghị để mọi brain trong thư mục brains (tạo brain mới bằng nút ➕ là tự vào đó) để chuyển máy dễ.
- Cơ chế mới dùng bản sao sạch (mirror): bỏ hội thoại gốc/log/khoá + git thô của từng brain (tránh lỗi nested-repo), token không lọt .git/config.
### Thêm mới
- Đổi avatar/logo mặc định của Javis.

## [0.7.9] - 2026-07-02
### Thêm mới
- Bộ "meta-capabilities" khởi đầu, tự seed vào mỗi brain: skill **javis-builder** (dạy Javis tự tạo agent/skill/workflow/loop đúng chuẩn, có chống trùng + rào an toàn) và loop **tự-cải-tiến-javis** (mặc định TẮT, chế độ đề xuất - mỗi vòng rà hệ thống, đề xuất 1 cải tiến nhỏ an toàn, ghi báo cáo vào 05 - Projects). Tạo dạng create-if-missing, không đè file bạn đã sửa.
- Quy tắc "Làm rõ trước khi trả lời" trong system prompt: câu hỏi phức tạp/mơ hồ thì Javis tự diễn đạt lại cách hiểu + nêu giả định rồi mới làm, chỉ hỏi lại khi thực sự tắc.

## [0.7.8] - 2026-07-02
### Thêm mới
- Agent chọn được model của ChatGPT/Codex (GPT-5.x) bên cạnh Claude (Sonnet/Opus/Haiku/Fable). Agent model Codex chạy qua Codex CLI - vẫn đọc/ghi file vault + dùng MCP. Dropdown model trong Studio chia 2 nhóm Claude / ChatGPT.
- An toàn: workflow chạy nền tự động (dispatcher, file-only) luôn dùng Claude Code để giữ giới hạn công cụ, kể cả khi agent chọn Codex; model Codex chỉ áp khi chạy workflow trực tiếp ở Studio.
### Thay đổi
- Tài liệu mô tả lại: Javis xây trên CLI dạng agent của nhà cung cấp (Claude Code + Codex) và tận dụng gói subscription, không còn xoay quanh chỉ Claude. Cập nhật README, docs 07/10, nhãn Docker và system prompt.

## [0.7.7] - 2026-07-02
### Sửa lỗi
- Agent: phần chọn Model (Sonnet/Opus/Haiku) trước đây lưu vào file nhưng KHÔNG được áp khi chạy - workflow luôn dùng model mặc định. Nay model của từng agent (kể cả agent kiểm chứng) được áp THẬT vào CLI lúc chạy. Thêm lựa chọn "Fable" + "Mặc định (theo CLI)" trong dropdown; agent để trống model = dùng model mặc định.

## [0.7.6] - 2026-07-02
### Sửa lỗi
- ChatGPT/Codex trên VPS báo "gpt-5-mini không hỗ trợ khi dùng Codex với tài khoản ChatGPT": model API thường (gpt-5-mini, gpt-4o, o3...) không chạy được qua Codex. Nay tự đổi (coerce) sang model Codex hợp lệ trong catalog (mặc định gpt-5.5) ở cả chat lẫn Telegram, tự chữa lại cấu hình đã lưu, và báo cho người dùng. Bộ chọn model của ChatGPT-OAuth cũng chỉ còn liệt kê đúng model Codex (bỏ nguồn trả model ChatGPT chung).
### Thêm mới
- Guide khi deploy: thêm OCI image labels (documentation/source/url) + nhãn compose để Docker Manager (Hostinger) hiện link Documentation/Quick start cho project. Thêm QUICKSTART.md (deploy 3 cách + sự cố hay gặp) ở gốc repo; mọi link tài liệu trỏ về docs trên GitHub.

## [0.7.5] - 2026-07-02
### Thêm mới
- Sao lưu brain lên GitHub: mục mới trong trang Tự học, có hướng dẫn 3 bước ngay trên màn hình (tạo repo private → tạo token fine-grained → dán vào). Nút Kiểm tra kết nối + Sao lưu ngay + công tắc tự sao lưu định kỳ. Tài liệu chi tiết: docs/18-sao-luu-github.md.
- Backup đẩy toàn bộ brain lên repo GitHub riêng (force-push, local là bản gốc); khôi phục bằng git clone khi mất máy/VPS.
### An toàn
- Token GitHub lưu nội bộ settings.json (gitignored), KHÔNG đẩy lên repo và tự che trong mọi thông báo lỗi; push dùng URL tạm nên token không nằm trong .git/config. File nhạy cảm (log thô, hội thoại gốc, khoá lock) được .gitignore loại khỏi bản đẩy. Cảnh báo rõ trên UI: chỉ dùng repo Private.

## [0.7.4] - 2026-07-02
### Thay đổi
- Tự học: mặc định BẬT sẵn + chế độ Tự ghi + bật cả 4 khả năng (Ký ức, Wiki, Kỹ năng, Việc) cho cài mới. Học chạy ngay từ đầu, không phải vào bật thủ công.
- Bỏ yêu cầu git: chế độ Tự ghi giờ hoạt động KỂ CẢ khi máy chưa có git (trước đây tự hạ về Chạy thử). Có git thì vẫn tự commit để hoàn tác 1 chạm; không có git thì vẫn ghi bình thường, chỉ thiếu undo/backup.
- Tự học giờ tự đăng ký brain đang trò chuyện: chat trên vault nào là học vault đó, không cần vào trang Tự học bấm lưu để thêm vault vào danh sách.
### An toàn
- Các rào an toàn của engine học GIỮ NGUYÊN: fork chỉ-đọc cô lập (0 MCP), quét lộ khoá + câu tiêm, chặn ghi ngoài phạm vi, ký ức chỉ thêm không đè.

## [0.7.3] - 2026-07-02
### Thêm mới
- Loop có thêm chế độ "Toàn quyền" (mode full): loop tự thao tác THẬT ra ngoài qua MCP không cần hỏi (tạo/sửa đơn, chạy quảng cáo tiêu tiền, gửi tin, đăng bài). Dành cho ai muốn loop tự làm hết. Kèm cảnh báo rủi ro đỏ trong form + hộp xác nhận khi lưu và khi bật; tab Lịch đánh dấu "⚠ TOÀN QUYỀN".
- 3 mức quyền rõ ràng: Đề xuất (chỉ đọc) · Tự làm an toàn (ghi nháp + đọc MCP, KHÔNG tiền/đơn) · Toàn quyền (làm mọi thứ). Mặc định vẫn là mức an toàn; chế độ toàn quyền phải tự bật.
### An toàn
- Loop toàn quyền vẫn tôn trọng cài đặt "chặn tool" (deny_tools) của từng MCP server; bước tự kiểm chứng chuyển sang soi "đúng phạm vi nhiệm vụ" thay vì cấm hành động. Javis khi chat KHÔNG bao giờ tự đặt loop sang toàn quyền - chỉ khi người dùng yêu cầu rõ.

## [0.7.2] - 2026-07-02
### Thay đổi
- Form tạo Loop gọn còn Tên + Mô tả (+ chế độ + chu kỳ): bỏ bộ chọn "Loại nhiệm vụ" 4 nút. Mỗi loop giờ chỉ cần mô tả việc cần làm mỗi vòng. Tinh chỉnh nâng cao (giờ im lặng, trần vòng/ngày, profile code) sửa trực tiếp trong file Javis/loops/<tên>.md.
- Loop giờ ĐỌC được dữ liệu thật qua MCP (POS, quảng cáo, lịch...) để làm việc - trước đây loop bị cô lập 0-MCP. An toàn giữ 3 lớp: tôn trọng deny_tools từng server, chỉ dẫn cứng cấm tạo đơn/tiêu tiền/quảng cáo/đăng bài/gửi tin (chỉ được đọc + ghi nháp), và kiểm chứng độc lập sẽ fail nếu phát hiện hành động ghi ra ngoài. Loop chạy nền vẫn KHÔNG có Bash/Web (trừ profile code cho loop sửa mã, vốn 0-MCP).

## [0.7.1] - 2026-07-02
### Cải thiện
- Trang loop: đổi tên mục sidebar "Tự cải thiện" thành "Loop" cho gọn, đúng bản chất.
- Bỏ nút "LINT Wiki" khỏi trang Loop (engine Tự học đã lo bảo trì Wiki qua curator/LINT chỉ-đề-xuất), tránh trùng chức năng.

## [0.7.0] - 2026-07-02
### Thêm mới
- MULTI-LOOP: "Vòng lặp tự cải thiện" nâng thành hệ NHIỀU loop. Mỗi loop = 1 file `Javis/loops/<slug>.md` trong vault (sửa được bằng Obsidian/chat/Studio), có bật/tắt, chu kỳ riêng, giờ im lặng (quiet_hours), trần vòng/ngày, workspace + tools_profile (vault-safe mặc định / code cho loop sửa mã). Thực thi TUẦN TỰ (1 vòng/lúc), state runtime tách riêng ở `Javis/loop-state.json`.
- Tự bảo vệ: loop lỗi/kiểm chứng ✗ 3 lần liên tiếp thì TỰ TẠM DỪNG (ghi lý do + log, báo Telegram nếu có bot); bật lại hoặc Chạy ngay để tiếp tục.
- API mới `/loops` (list/tạo/sửa/toggle/xoá/run-now/log lọc theo loop). `/loop/*` cũ giữ nguyên, trỏ về loop legacy `vong-lap-goc`.
- Trang "Tự cải thiện" thành DANH SÁCH loop: trạng thái, lần chạy cuối + kết quả kiểm chứng, next run, nút bật/tắt - chạy ngay - sửa - xoá, form tạo loop đầy đủ, nhật ký lọc theo loop.
- Tab Lịch hiện MỌI loop như routine builtin (id `__loop__:<slug>`): bật/tắt ngay tại đó; xoá thì phải sang trang Tự cải thiện.
- Javis chat = ĐIỀU PHỐI VIÊN: system prompt thêm quy trình chọn công cụ nhỏ nhất đủ hoàn thành (trả lời → task Kanban → skill → agent → workflow → lịch → loop), kiểm tra trùng trước khi tạo, loop tạo qua chat mặc định suggest + tắt.
### Cải thiện
- Migrate 1 lần: `loop_config.json` cũ tự sinh `Javis/loops/vong-lap-goc.md` (giữ nguyên toàn bộ custom_goal), json cũ giữ làm backup.

## [0.6.6] - 2026-07-02
### Thêm mới
- Nối engine tự học vào Kanban: capability "Việc (Kanban)" - sau mỗi hội thoại, engine học đề xuất việc nền vào backlog (dedup theo tên, chờ duyệt).
### Sửa lỗi
- Dashboard chết toàn bộ (Enter không gửi, stats trống, không graph) do app.js bám nút học cũ đã gỡ - đã guard + nghỉ hưu auto-learn client cũ.

## [0.6.5] - 2026-07-02
### Sửa lỗi
- docker-compose.hostinger.yml "không cài được": bỏ ${DOMAIN_NAME:?...} (bắt buộc biến, thiếu là deploy fail). Nay LUÔN deploy được: chưa đặt DOMAIN_NAME thì chạy tạm ở :7777, đặt DOMAIN_NAME thì có HTTPS. Publish lại cổng 7777 làm đường vào dự phòng.

## [0.6.4] - 2026-07-02
### Sửa lỗi
- docker-compose.yml: Watchtower chuyển sang profile "update" (mặc định TẮT) nên deploy base compose KHÔNG còn "Partially running" (Watchtower cần Docker socket, Hostinger hay chặn). Bật auto-update khi cần: docker compose --profile update up -d.
### Cải thiện
- README: sửa mục cài Hostinger dùng docker-compose.hostinger.yml + đặt DOMAIN_NAME cho tên miền/HTTPS; bỏ thông tin sai "Hostinger tự cấp URL hstgr.cloud".

## [0.6.3] - 2026-07-02
### Sửa lỗi
- docker-compose.hostinger.yml: đổi ports "7777:7777" (cố định) thành "7777" (ngẫu nhiên, giống Hermes) để nút Open trỏ thẳng domain HTTPS của Traefik thay vì http://<ip>:7777. Truy cập qua https://<DOMAIN_NAME>.

## [0.6.2] - 2026-07-02
### Sửa lỗi
- docker-compose.hostinger.yml: đã kiểm chứng Hostinger KHÔNG cấp biến TRAEFIK_HOST cho compose dán tay (link ra "javis-os." cụt). Nay Host BẮT BUỘC DOMAIN_NAME (dùng ${DOMAIN_NAME:?...}): thiếu thì deploy báo lỗi rõ ràng thay vì ra link hỏng. Tài liệu chỉ rõ đặt DOMAIN_NAME=javis.<hostname-vps>.hstgr.cloud ở ô Environment.

## [0.6.1] - 2026-07-01
### Sửa lỗi
- docker-compose.hostinger.yml: Host mặc định dùng ${COMPOSE_PROJECT_NAME}.${TRAEFIK_HOST} (đúng mẫu Hermes) thay cho giá trị localhost -> deploy trên Hostinger là TỰ có link <tên-project>.<hostname-vps>.hstgr.cloud + HTTPS, không cần đặt biến gì. Muốn tên miền riêng thì đặt DOMAIN_NAME (ghi đè). Ai deploy trên VPS của họ cũng ra link đúng.

## [0.6.0] - 2026-07-01
### Thay đổi
- Đồng bộ NỐT toàn bộ tên hạ tầng nội bộ sang javis: biến môi trường JAVIS_*, volume javis-data/javis-brains, service/container/user javis (/home/javis), profile codex javis, marker JAVIS_METRICS, và các file javis.service / start-javis.vbs / stop-javis.bat. Toàn dự án dùng một tên duy nhất.
- LƯU Ý khi redeploy: volume đã đổi tên nên bản mới bắt đầu TRỐNG (cần tạo lại admin + nạp lại brain), hoặc tự chép dữ liệu từ volume cũ sang javis-data/javis-brains. Nếu trước đó đặt biến admin trên Hostinger, đổi tiền tố sang JAVIS_ADMIN_USER / JAVIS_ADMIN_PASSWORD.

## [0.5.1] - 2026-07-01
### Thay đổi
- Đổi tên repo/image GitHub sang javis-os (image ghcr.io/blogminhquy/javis-os, GITHUB_REPO, link cài đặt trong README/DEPLOY).

## [0.5.0] - 2026-07-01
### Thay đổi
- Đổi thương hiệu hiển thị sang Javis (giao diện, tài liệu, README, system prompt).
### Thêm mới
- docker-compose.hostinger.yml dùng ${COMPOSE_PROJECT_NAME} cho tên router/service Traefik: chạy được nhiều bản Javis trên cùng 1 VPS mà không đụng nhau (giống đuôi ngẫu nhiên -efxd của Hermes).

## [0.4.7] - 2026-07-01
### Sửa lỗi
- docker-compose.hostinger.yml gắn nhãn Traefik đúng mẫu app Hermes: BỎ phần networks/external traefik-proxy (chính chỗ làm deploy báo "network not found"). Traefik của Hostinger tự thấy container qua nhãn.
### Thêm mới
- Có link mặc định chạy HTTPS mà không cần mua tên miền: đặt DOMAIN_NAME=javis.<hostname-vps>.hstgr.cloud (Hostinger có wildcard DNS + tự cấp SSL).

## [0.4.6] - 2026-07-01
### Sửa lỗi
- docker-compose.hostinger.yml không deploy được trên Hostinger: bỏ yêu cầu mạng ngoài `traefik-proxy` (gây lỗi "network not found"). Bản mới chỉ 1 container, publish cổng 7777, deploy là chạy; gắn tên miền + HTTPS là bước tùy chọn (Hostinger UI hoặc nhãn Traefik thủ công, hướng dẫn trong file).

## [0.4.5] - 2026-07-01
### Sửa lỗi
- docker-compose.hostinger.yml bỏ Watchtower (cần Docker socket, hay gây "Partially running" trên Hostinger Docker Manager). Bản Hostinger giờ chỉ 1 container javis + nhãn Traefik, cập nhật bằng Redeploy.

## [0.4.4] - 2026-07-01
### Thêm mới
- File docker-compose.hostinger.yml: chạy Javis trên Hostinger với tên miền riêng + HTTPS qua Traefik có sẵn của Hostinger, bỏ cổng :7777.
### Sửa lỗi
- Tài liệu Hostinger nói đúng thực tế: compose gốc chỉ vào bằng IP:7777; muốn tên miền và SSL phải dùng bản có nhãn Traefik (docker-compose.hostinger.yml).

## [0.4.3] - 2026-07-01
### Thêm mới
- Khu Tên miền & SSL trong Cài đặt làm mới: huy hiệu trạng thái DNS và SSL, nút Bật SSL chủ động xin chứng chỉ rồi kiểm tra kết quả.
### Sửa lỗi
- Số phiên bản ở góc thanh bên nay đọc đúng bản đang chạy (trước bị cố định 0.4.0).
### Cải thiện
- Trạng thái tên miền rõ ràng: DNS đã trỏ đúng chưa, SSL bật chưa, kèm lệnh bật Caddy cho bản Docker khi cần.

## [0.4.2] - 2026-07-01
### Thêm mới
- Trang **Cập nhật** (mục Logs cũ trên thanh bên): nhật ký phiên bản và các thay đổi mới, đọc thẳng trong app.
- Tự đối chiếu bản đang cài với bản mới nhất trên GitHub, đánh dấu phiên bản "đang dùng" và bản "có thể cập nhật".

## [0.4.1] - 2026-07-01
### Sửa lỗi
- Upload file trên Docker/VPS báo "lỗi máy chủ (500)": thư mục stage tạm đổi sang STATE_DIR ghi được (`/data/state`) thay vì code tree `/app` chỉ đọc.
- Endpoint upload bọc chống lỗi: sự cố môi trường trả thông báo rõ ràng kèm log thay vì lỗi 500 khó đoán.
### Thêm mới
- Bộ tài liệu hướng dẫn sử dụng chi tiết trong `docs/` (17 trang) và mục lục nối vào README.
### Cải thiện
- Bỏ toàn bộ ký tự gạch ngang dài khỏi giao diện và tài liệu cho giọng nói đọc mượt hơn.

## [0.4.0] - 2026-06-30
### Thêm mới
- Trang **Cài đặt** riêng: chọn giọng đọc theo nhà cung cấp (Edge TTS, OpenAI, ElevenLabs), tinh chỉnh giao diện, avatar, tên miền.
- Nút **Cập nhật ngay** trong Tổng quan: cập nhật phiên bản mới ngay trên giao diện, không cần terminal.
- Đổi logo/avatar và trỏ tên miền riêng chạy HTTPS ngay trong app.
### Cải thiện
- Gộp cài đặt vào thanh bên, thu gọn điều hướng.

## [0.3.0] - 2026-06-29
### Thêm mới
- Chạy ChatGPT qua Codex CLI trên VPS: đăng nhập bằng gói subscription, dùng được cả MCP của Javis.
- Đăng nhập Claude bằng OAuth device-code ngay trong giao diện (không cần terminal).
- Kiến trúc đa Second Brain: quản lý nhiều brain trong thư mục `brains/`, tạo và xoá brain trong app.
### Sửa lỗi
- Trạng thái bot Telegram hiển thị đúng thực tế (đang chạy, lỗi 409, chưa bật).

## [0.2.0] - 2026-06-28
### Thêm mới
- Bộ cài đặt lần đầu (wizard) chọn 1 trong 3 nhà cung cấp: Claude Code, ChatGPT, OpenRouter.
- Triển khai 1-click qua Hostinger Docker Manager (kéo image GHCR).
- Tự bật HTTPS bằng Caddy, logo và favicon thương hiệu.
### Bảo mật
- Bắt buộc đăng nhập khi chạy public, MÃ THIẾT LẬP chống chiếm tài khoản admin.

## [0.1.0] - 2026-06-26
### Thêm mới
- Bản đầu tiên: trợ lý AI cá nhân chạy bằng Claude Code, giọng nói, đồ thị tri thức 3D, Second Brain.
- README chi tiết: giới thiệu, cài đặt mọi cách, hướng dẫn dùng, bảo mật, khắc phục sự cố.
