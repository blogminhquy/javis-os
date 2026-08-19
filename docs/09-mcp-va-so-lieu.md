# Kết nối & số liệu kinh doanh

Trang **Kết nối** là nơi bạn "đấu" Javis vào các công cụ bạn đang dùng: Pancake POS, Zalo, Webcake Landing, Botcake, quảng cáo Meta/Google/TikTok, lịch, CRM... Sau khi đấu, Javis đọc được số liệu THẬT và (nếu bạn cho quyền) thao tác thật trên các công cụ đó. Trang này hướng dẫn: kết nối một dịch vụ từ Kho, nối nhiều tài khoản, phân quyền, xem nhật ký, và cách đọc số liệu.

## Tính năng này là gì

Bên dưới, mỗi kết nối là một "đường ống" MCP (Model Context Protocol) nối Javis tới dịch vụ ngoài - nhưng bạn không cần biết chi tiết đó. Điểm mới từ bản 0.9:

- **Kho kết nối cài sẵn**: chọn dịch vụ, dán API key (hoặc quét QR với Zalo) là xong. Javis tự kiểm tra key và tự đặt tên tài khoản (ví dụ lấy đúng tên cửa hàng từ Pancake POS). Không còn phải gõ URL hay header.
- **Một dịch vụ, nhiều tài khoản**: 3 cửa hàng Pancake = 3 tài khoản trong cùng một thẻ Pancake POS. 2 số Zalo = 2 tài khoản Zalo chạy song song. Mỗi tài khoản bật/tắt, phân quyền, đặt mặc định riêng.
- **Mọi bộ não dùng chung**: Claude Code, ChatGPT (Codex), OpenRouter, OpenAI API, Anthropic API và Google Gemini (API) đều dùng chung kho Kết nối này qua "hub" của Javis - đấu một lần, đổi model thoải mái. Riêng Gemini có một điểm lệch: phần chạy bên dưới đã gọi được công cụ qua hub, nhưng trang Kết nối vẫn hiện dòng cảnh báo vàng "⚠ Main Model đang là Google Gemini (API) - chưa hỗ trợ gọi công cụ. Đổi ở trang Models." vì danh sách trên giao diện chưa được cập nhật. Cứ dùng bình thường.
- **Phân quyền cứng**: mỗi tài khoản có mức quyền. Javis CHẶN thật sự (không phải chỉ nhắc bằng lời) các thao tác vượt quyền, ví dụ tạo đơn khi đang ở mức Chỉ đọc.

## Mở ở đâu trong Javis

1. Vào dashboard (cổng mặc định `7777`).
2. Thanh bên trái, mở nhóm **Kết nối**, rồi bấm mục **Kết nối** (biểu tượng phích cắm, phụ đề "Nguồn dữ liệu & công cụ").
3. Trang có 3 khu:
   - **◆ Đã kết nối** - các tài khoản bạn đang đấu, kèm ô tick "Chỉ dùng kết nối của Javis (bỏ kết nối sẵn của máy)".
   - **◆ Kho kết nối** - 24 dịch vụ cài sẵn để đấu thêm, có ô "Tìm dịch vụ…" và dãy nút lọc: **Tất cả**, Kho ứng dụng, Bán hàng, Nhắn tin, Marketing, Văn phòng, Quảng cáo, Mạng xã hội, Sáng tạo. Sáu dịch vụ Google gom chung vào MỘT thẻ **Google** ghi "6 dịch vụ" - bấm **Chọn dịch vụ** trên thẻ đó mới ra danh sách con.
   - **◆ Kết nối sẵn của Claude Code và Codex** - khối GẬP SẴN ở cuối trang, phụ đề "chỉ hiển thị - bấm để xem". Đây là những nguồn đã đăng nhập sẵn trong tài khoản Claude (đồng bộ từ claude.ai) và trong Codex CLI. Danh sách chỉ tải khi bạn bấm mở, và hơi lâu vì Javis phải kiểm tra tình trạng từng nguồn. Chỉ để xem, không sửa được ở đây.

## Cách dùng (từng bước)

### 1. Kết nối Pancake POS (dán API key)

1. Ở **Kho kết nối**, tìm thẻ **Pancake POS**, bấm **Kết nối**.
2. Làm theo hướng dẫn trong cửa sổ: mở Pancake POS > Cấu hình cửa hàng > Ứng dụng & API > tạo API key, rồi dán vào ô.
3. Bấm **Kết nối**. Javis tự kiểm tra key - đúng thì hiện "✓ Đã kết nối: <tên cửa hàng>" và tài khoản xuất hiện ở khu Đã kết nối. Key sai thì báo lỗi ngay tại chỗ.
4. Có nhiều cửa hàng? Bấm **+ Thêm tài khoản** trên thẻ Pancake POS, dán key của shop tiếp theo. Mỗi shop một chip riêng.

Pancake POS mặc định ở mức **Chỉ đọc** - Javis xem được doanh thu, đơn, khách... nhưng không thể tạo đơn hay đụng tiền. Muốn Javis thao tác thật, xem mục Phân quyền bên dưới.

### 2. Kết nối Zalo (quét QR)

Cần Node.js 20+ trên máy chạy Javis (tải tại nodejs.org, cài một lần).

1. Ở Kho kết nối, bấm **Kết nối** trên thẻ **Zalo Agent MCP**.
2. Đọc cảnh báo rủi ro: đây là công cụ KHÔNG chính thức, tài khoản Zalo có thể bị hạn chế hoặc khoá - khuyến nghị dùng tài khoản phụ. Bấm "Tôi hiểu rủi ro, hiện mã QR".
3. Mở Zalo trên điện thoại > biểu tượng QR góc trên > quét mã trong màn hình Javis.
4. Quét xong, tài khoản tự xuất hiện. Nối thêm số Zalo khác bằng **+ Thêm tài khoản** - các tài khoản chạy cô lập, không giẫm nhau.

Zalo mặc định ở mức Toàn quyền để dùng được tool gửi tin. Có thể hạ xuống Ghi nháp hoặc
Chỉ đọc trên chip tài khoản. Tích hợp mới dùng trực tiếp bảy tool của `zalo-agent-cli`,
không còn listener/webhook riêng hay chuyển tiếp tin sang Telegram. Xem
[hướng dẫn Zalo Agent MCP](12-zalo.md).

### 3b. Kết nối Slack / Systeme.io

- **Slack** (MCP chính chủ, chỉ cần đăng nhập trong dashboard): Slack bắt buộc MCP đi qua một app của chính bạn nên hơi nhiều bước một lần: vào api.slack.com/apps tạo app trong workspace, ở "OAuth & Permissions" thêm Redirect URL `http://localhost:7777/connect/oauth/callback` (VPS thì thêm địa chỉ tên miền) và thêm các "User Token Scopes" (search, channels, users, chat:write, canvases...), rồi copy Client ID + Secret dán vào cửa sổ kết nối. Nếu workspace bắt duyệt app thì cần admin chấp thuận. Mặc định Chỉ đọc - gửi tin phải nâng Toàn quyền.
- **Systeme.io** (MCP chính chủ, dán key là xong): vào systeme.io > Cài đặt hồ sơ > "MCP & API keys" > tạo MCP key (hạn tối đa 90 ngày), dán vào. Javis quản lý được liên hệ, tag, newsletter, phễu. Mặc định Chỉ đọc.
- **Lark** (MCP chính chủ, chạy local, cần Node.js 18+): nhắn tin, tài liệu, bảng dữ liệu Base, wiki, danh bạ trong Lark. Tạo một Lark app tại open.larksuite.com/app, cấp quyền (im, docx, bitable, contact...), lấy App ID + App Secret dán vào. Javis chỉ làm được đúng phạm vi quyền bạn cấp cho app. Mặc định Chỉ đọc - gửi tin nhắn và cấp quyền file phải nâng Toàn quyền.

### 3c. Kết nối Shopify (tra cứu cửa hàng)

Mỗi cửa hàng Shopify có sẵn một MCP công khai theo chuẩn UCP, nên đây là kết nối dễ nhất kho: **không cần API key, không cần cài app, và không cần bạn là chủ shop**.

1. Ở **Kho kết nối**, tìm thẻ **Shopify**, bấm **Kết nối**.
2. Dán địa chỉ cửa hàng (tên miền riêng hay dạng `...myshopify.com` đều được). Gõ thiếu `https://`, thừa gạch chéo hay dán nguyên URL trang sản phẩm cũng không sao, Javis tự cắt về đúng tên miền.
3. Ô **hồ sơ agent UCP** đã điền sẵn - cứ để nguyên rồi bấm Kết nối.

Javis tra được sản phẩm, giá, tồn kho, và dựng sẵn giỏ hàng để bạn bấm thanh toán. Mặc định **Chỉ đọc** (chỉ tra cứu); muốn Javis dựng giỏ hàng thật thì nâng lên **Ghi nháp**.

Hai điều nên biết:

- Giỏ hàng **chưa phải đơn hàng** và chưa trừ tiền. Shopify trả về một đường link để người thật bấm vào thanh toán - Javis không khai năng lực thanh toán nên không tự trả tiền được.
- Đây là kênh **công khai của cửa hàng**, không phải cổng quản trị: nó không cho xem doanh thu, đơn hàng hay khách hàng của shop.

Ô hồ sơ agent UCP là gì: Shopify bắt mỗi lời gọi phải kèm đường dẫn tới một tờ khai "agent này làm được những gì" để cửa hàng tải về và thoả thuận. Javis tự đính kèm ở mọi lời gọi, bạn không phải làm gì. Chỉ khi muốn dùng tờ khai riêng thì mới sửa ô đó.

### 3. Kết nối Webcake Landing / Botcake

- **Webcake Landing**: lấy JWT tại webcake.io > Cài đặt > Mã truy cập > Tạo API keys, dán vào. Javis sẽ thiết kế/sửa landing page bằng lời nói. Cần Node.js 18+.
- **Botcake**: mở Botcake > Cấu hình > Tích hợp > Public API > Tạo API Key; dán Page ID + key. Javis đọc được khách hàng, tag, flow và (nếu cho Toàn quyền) gửi flow tới khách.

### 4. Kết nối bộ Google (Sheets, Search Console, Lịch, Gmail, Workspace, Tasks, Keep)

Trừ Search Console, các dịch vụ Google nằm chung trong một thẻ **Google** ở Kho kết nối (ghi "6 dịch vụ"). Bấm **Chọn dịch vụ** để mở danh sách rồi chọn cái cần đấu. Đã tạo OAuth client cho một dịch vụ rồi thì các dịch vụ sau bấm **Dùng lại key** là xong, không phải vào Google Cloud lần nữa.

- **Google Sheets**: đổ báo cáo doanh thu/tồn kho/công nợ ra bảng tính. Tạo service account trong Google Cloud (hướng dẫn có trong cửa sổ kết nối), share thư mục Drive cho email service account, dán nội dung file key JSON + ID thư mục là xong - không cần đăng nhập gì thêm.
- **Google Search Console**: số liệu SEO website (khách tìm từ khoá gì, lượt bấm). Cũng dán service account JSON, thêm email đó làm người dùng trong Search Console.
- **Google Calendar** và **Gmail** (2 kết nối riêng, MCP chính chủ của Google, chạy remote nên dùng được cả trên VPS): Calendar xem lịch, tìm chỗ trống, tạo/sửa/xoá sự kiện, nhắc hẹn; Gmail đọc/tìm thư, soạn NHÁP, gắn nhãn. Điểm an toàn: server Gmail chính chủ KHÔNG có tool gửi thẳng, nên Javis luôn dừng ở bản nháp để bạn tự bấm gửi. Cần tạo OAuth client một lần (console.cloud.google.com > Thông tin xác thực > OAuth client ID loại "Ứng dụng web", thêm URI chuyển hướng đúng như cửa sổ kết nối chỉ, và thêm email mình vào Test users). Dán Client ID + Secret, bấm Kết nối là trình duyệt mở cho bạn đăng nhập Google. Dùng CHUNG một OAuth client cho cả Calendar lẫn Gmail (chỉ cần bật thêm API tương ứng). Cả hai mặc định Chỉ đọc; nâng lên Ghi nháp để tạo sự kiện/soạn nháp, Toàn quyền mới xoá được sự kiện. **Phải khai đủ phạm vi quyền** ở trang Quyền dữ liệu (Data Access) của Google Auth Platform - server MCP của Google không nhận mỗi phạm vi gộp `calendar`, riêng việc tìm giờ trống đòi đúng `calendar.events.freebusy`; thiếu nó thì đăng nhập vẫn xanh nhưng hễ kiểm tra rảnh bận là báo thiếu quyền, xoá đi cài lại không chữa được (cửa sổ kết nối liệt kê sẵn đủ danh sách để dán).
- **Google Workspace** (Gmail + Lịch + Drive + Docs + Sheets trong 1 kết nối, chạy local): cần tạo OAuth client trong Google Cloud một lần (~10 phút, hướng dẫn từng bước trong cửa sổ kết nối), loại "Ứng dụng dành cho máy tính" nên KHÔNG phải khai URI chuyển hướng như hai thẻ trên. **Chỉ dùng được trên máy có màn hình**: lần đầu Javis gọi tool, trình duyệt của chính máy chạy Javis mở ra để bấm đồng ý - cài trên VPS thì dùng hai kết nối Calendar và Gmail ở trên. Bật API cho từng dịch vụ định dùng (Gmail, Calendar, Drive, Docs là bốn cái cơ bản; thêm Sheets, Slides, Forms, People, Tasks nếu cần) - quên cái nào thì đúng nhóm công cụ đó báo lỗi, phần còn lại vẫn chạy. Nên điền luôn ô email Google, bỏ trống thì mỗi lần gọi tool server lại hỏi ngược xem dùng tài khoản nào. Mặc định ở mức Ghi nháp: Javis soạn nháp mail, tạo lịch, tạo tài liệu được nhưng KHÔNG tự gửi mail hay xoá gì - bật Toàn quyền phải xác nhận rủi ro. Chọn cái này nếu muốn CẢ Drive/Docs/Sheets trong một mối; nếu chỉ cần Lịch + Gmail thì 2 kết nối riêng ở trên gọn hơn (ít công cụ, chạy remote, dùng được trên VPS).
- **Google Tasks** (việc cần làm, chạy local qua `uvx`): xem danh sách, thêm việc, đặt hạn, đánh dấu xong. Chỉ xin quyền Tasks, không đọc được Gmail hay Drive. Dùng chung OAuth client với Google Workspace, chỉ cần bật thêm Google Tasks API cho project và tạo client loại "Ứng dụng dành cho máy tính". Mặc định **Ghi nháp** - ở mức này Javis đã tạo, sửa, đánh dấu xong và xoá được từng việc lẻ; Toàn quyền mới thêm quyền tạo/đổi tên/XOÁ cả danh sách (xoá danh sách là mất hết việc bên trong, không hoàn tác). Chạy chung server với Google Workspace nên cũng **chỉ dùng được trên máy có màn hình**: lần đầu Javis gọi tool, trình duyệt trên máy chạy Javis mở ra để bạn bấm đồng ý.
- **Google Keep** (ghi chú, chạy local qua `uvx`): tìm note, tạo note và danh sách việc, gắn nhãn, ghim, lưu trữ. **Đọc kỹ trước khi đấu**: Keep không có API chính chủ nên kết nối này phải dùng **master token có TOÀN QUYỀN tài khoản Google** (Gmail, Drive, Photos), không phải OAuth giới hạn phạm vi như Gmail hay Lịch. Javis chỉ thao tác ghi chú, nhưng token đó nếu lộ là mở cả tài khoản. Cách đấu: bật xác minh 2 bước, tạo App Password 16 ký tự, dán email + chuỗi đó vào; Javis đổi lấy token và KHÔNG lưu lại App Password. Ô `unsafe_mode` để trống thì Javis chỉ sửa được note do chính nó tạo, gõ `true` thì sửa được mọi note kể cả note bạn viết tay. Mặc định **Chỉ đọc**.

- **Google NotebookLM** (chạy local qua `uvx`): liệt kê notebook, đọc nguồn bên trong, hỏi đáp ngay trong notebook, thêm nguồn, lưu ghi chú, tạo tóm tắt hoặc audio ở Studio. **Đọc kỹ trước khi đấu**: NotebookLM chưa có API chính chủ, nên kết nối này mượn **cookie phiên trình duyệt** của bạn, tức là một credential tương đương đang đăng nhập tài khoản Google, không phải OAuth giới hạn phạm vi như Gmail hay Lịch. Cách đấu: trên **máy cá nhân có trình duyệt** (không làm được trên VPS) chạy `uvx --from "notebooklm-py[browser]" notebooklm login`, đăng nhập Google rồi mở NotebookLM một lần; sau đó mở tệp `~/.notebooklm/profiles/default/storage_state.json` vừa sinh ra, copy toàn bộ nội dung dán vào ô trong cửa sổ kết nối. Phiên hết hạn thì chạy lại lệnh đó và dán chuỗi mới. Mặc định **Chỉ đọc** - mức Ghi nháp mới cho hỏi đáp và tạo tóm tắt (tiêu quota NotebookLM), mức Toàn quyền mới cho xoá notebook và chia sẻ ra ngoài. Thư viện bên dưới (`notebooklm-py`) là bản không chính thức nên Google đổi giao thức lúc nào cũng có thể làm kết nối này gãy.

Mẹo: nếu chỉ cần Gmail/Lịch/Drive và bạn dùng engine Claude Code, cách nhanh hơn là bấm Connect ngay trong app Claude (claude.ai > Settings > Connectors) - Javis tự thấy chúng trong khối gập **◆ Kết nối sẵn của Claude Code và Codex** ở cuối trang.

Tương tự với engine ChatGPT (Codex): MCP bạn đã đăng ký thẳng trong Codex CLI (`codex mcp add <tên> --url https://...` cho server HTTP, hoặc `codex mcp add <tên> -- <lệnh>` cho server stdio) được engine ChatGPT tự nạp khi chạy, và cũng hiện trong chính khối gập đó (danh sách Codex nằm ngay dưới danh sách Claude Code). Server đăng nhập kiểu OAuth thì chạy `codex mcp login <tên>` một lần trong terminal. Server OAuth thêm ở form "Tự thêm (nâng cao)" của Javis cũng được đăng ký vào cả hai CLI (Claude Code lẫn Codex) để đổi engine không mất công cụ.

### 5. Kết nối quảng cáo (Meta Ads, Google Ads, TikTok Ads)

Cả 3 mặc định ở mức **Chỉ đọc** - Javis xem báo cáo, phân tích chi phí/hiệu quả nhưng không đụng được vào chiến dịch.

- **Meta Ads (Facebook & Instagram)** có HAI kết nối trong kho, chọn 1:
  - **Meta Ads (MCP chính chủ)**: MCP hosted của Meta. Hiện đang beta GIỚI HẠN: Meta chỉ cho vài ứng dụng được cấp phép sẵn (trợ lý ChatGPT/Claude/Perplexity) kết nối và đã tắt tự đăng ký, nên Javis - và cả công cụ khác - CHƯA nối tự phục vụ được. Không phải lỗi máy bạn; chờ Meta mở thêm theo tài khoản. Xem chi tiết bên dưới.
  - **Meta Ads (tự tạo app - Graph API)**: cách CHẠY ĐƯỢC ngay hôm nay (giống Composio/byadsco dùng) - Javis gọi thẳng Marketing API của Meta bằng một Facebook App do BẠN tạo. CHỈ ĐỌC số liệu, không tiêu tiền. Hướng dẫn tạo app ở mục bên dưới.
- **Google Ads**: MCP chính chủ của Google, thuần chỉ đọc (truy vấn số liệu GAQL: chiến dịch, chi phí, chuyển đổi, từ khoá). Cài đặt kỹ thuật nhất trong kho, cần bốn thứ: developer token (lấy trong Google Ads API Center của tài khoản quản lý MCC, mức Explorer là đủ để đọc), một project Google Cloud đã bật Google Ads API, một OAuth client ID loại **"Ứng dụng web"**, và trong client đó phải thêm URI chuyển hướng `http://localhost:7777/connect/oauth/callback` (chạy trên VPS thì thêm cả `https://<tên-miền>/connect/oauth/callback`). Điền xong bấm nút đăng nhập trên giao diện là trình duyệt mở cho bạn cấp quyền - **Javis tự dựng file đăng nhập, KHÔNG cần cài Google Cloud CLI và không phải chạy lệnh nào**. Ai đã tự chạy `gcloud` trước đó rồi thì dán thẳng nội dung file `application_default_credentials.json` vào ô cuối cho nhanh. Chạy ads qua agency/MCC thì điền thêm ID tài khoản quản lý. Gặp cảnh báo "ứng dụng chưa được xác minh" thì bấm Nâng cao > Tiếp tục, vì đây là app của chính bạn.
- **TikTok Ads**: TikTok chưa mở MCP chính chủ (mới công bố tại TikTok World 5/2026), nên Javis dùng server cộng đồng chạy trên Marketing API chính thức - thuần chỉ đọc (tài khoản, chiến dịch, báo cáo). Tạo app Marketing API tại business-api.tiktok.com, lấy App ID + Secret + Access Token dán vào. Khi TikTok mở bản chính chủ sẽ thay trong kho.

Google Ads và TikTok Ads chạy local qua công cụ `uv` - máy chạy Javis cần cài một lần: `winget install astral-sh.uv` (Windows) hoặc xem docs.astral.sh/uv. Riêng **Google Ads cần thêm Git** trên máy chạy Javis, vì `uvx` tải server thẳng từ GitHub. Thiếu Git là kết nối chết ngay, dù `uv` đã có.

#### Kết nối Meta Ads qua Graph API (tự tạo Facebook App) - làm 1 lần, ~10 phút

Đây là con đường tự phục vụ chạy được ngay, không phụ thuộc beta MCP của Meta. Bạn tạo một Facebook App của riêng mình, Javis dùng nó để đọc số liệu ad account của bạn. Vì app do chính bạn làm và giữ ở chế độ thử nghiệm, bạn tự cấp được quyền đọc mà KHÔNG cần Meta duyệt.

**Trước khi bắt đầu: xem bạn đang dùng giao diện nào.** Meta đang chuyển dần trang quản lý ứng dụng sang bản mới, nên hai người mở cùng lúc có thể thấy hai kiểu menu khác nhau. Nhìn **cột trái** trong trang app:

- Thấy mục **"Sản phẩm"** (Products) là **giao diện CŨ**.
- Thấy mục **"Trường hợp sử dụng"** (Use cases) và KHÔNG có mục "Sản phẩm" là **giao diện MỚI**.

Hai bản làm giống nhau ở mọi bước, chỉ khác đúng chỗ mở phần Đăng nhập bằng Facebook (bước 2). Nếu bạn tìm mãi không thấy "Sản phẩm" hay "Đăng nhập bằng Facebook cho doanh nghiệp" thì gần như chắc chắn bạn đang ở bản mới, không phải do thiếu quyền hay do Business Manager chưa xác minh.

1. Vào [developers.facebook.com/apps](https://developers.facebook.com/apps) > **Create App**. Chọn loại **Business** (hoặc "Other"), đặt tên bất kỳ (vd "Javis đọc ads").
2. Mở phần **Đăng nhập bằng Facebook**, tuỳ giao diện:
   - **Bản CŨ**: **Sản phẩm > Thêm sản phẩm** > thêm **Đăng nhập bằng Facebook** (bản THƯỜNG, KHÔNG phải "cho doanh nghiệp"), rồi bấm **Cài đặt**.
   - **Bản MỚI**: cột trái **Trường hợp sử dụng** > mở **"Xác thực và yêu cầu dữ liệu từ người dùng qua phương thức Đăng nhập bằng Facebook"** > **Tùy chỉnh** > **Cài đặt**. Mục này thường đã có sẵn khi tạo app, bạn không phải thêm gì.
3. Ô **URI chuyển hướng OAuth hợp lệ** (Valid OAuth Redirect URIs) - **làm khác nhau tuỳ nơi bạn cài Javis**:
   - **Cài trên máy cá nhân** (địa chỉ `localhost`): **bỏ qua ô này, không cần điền.** Khi app ở Chế độ phát triển, Meta **tự động cho phép** chuyển hướng về localhost, nên ô này cố tình không nhận localhost. Meta có chú thích ngay tại đó: "Khi ở chế độ phát triển, hệ thống sẽ tự động cho phép http://localhost chuyển hướng và bạn không cần phải thêm vào đây." Không điền được là **đúng**, không phải lỗi, cứ đi tiếp. Chỉ nhớ Javis phải chạy ở địa chỉ **localhost** chứ không phải 127.0.0.1.
   - **Cài trên VPS / tên miền riêng**: **bắt buộc phải điền**, dán đúng địa chỉ https của bạn rồi Lưu, vd `https://javis.tenmiencuaban.com/connect/oauth/callback`. Ngoài localhost thì Meta không tự cho phép và cũng bắt buộc **https**, thiếu bước này là đăng nhập bị từ chối.
   - **Đừng tự gõ tay**: hộp thoại Kết nối của Javis có ô địa chỉ kèm nút **Sao chép** sinh sẵn ĐÚNG địa chỉ theo tên miền máy bạn - bấm Sao chép rồi dán nguyên văn. Facebook bắt khớp **từng ký tự** (kể cả dấu `/` cuối), lệch một chữ là báo **"URL bị chặn"**.
   - **Cũng cho VPS / tên miền riêng**: vào **Cài đặt ứng dụng > Thông tin cơ bản**, ô **Miền ứng dụng** (App Domains) điền tên miền trần, vd `javis.tenmiencuaban.com` (KHÔNG có `https://`, KHÔNG có dấu `/`), kéo xuống cuối trang bấm **Lưu thay đổi**. Hộp thoại Kết nối của Javis cũng có ô Sao chép sẵn tên miền này. Thiếu bước này Facebook báo **"Không thể tải URL - Miền của URL này không được đưa vào miền của ứng dụng"**.
   - Đừng vào "Cài đặt ứng dụng > Nâng cao", đó là chỗ khác không liên quan.
4. Giữ app ở chế độ **Development** (công tắc góc trên cùng để ở "In development"). Đảm bảo bạn là **Admin** của app và của tài khoản quảng cáo muốn đọc - khi đó quyền `ads_read` tự cấp được, không cần App Review.
5. **Bỏ qua "Xác minh doanh nghiệp" và "Xét duyệt ứng dụng"** dù bảng "Việc cần làm" của app có gợi ý. Hai bước đó chỉ cần khi app của bạn phục vụ doanh nghiệp KHÁC truy cập dữ liệu của họ; bạn tự dùng cho tài khoản của chính mình thì không cần, làm chỉ mất thêm nhiều ngày chờ duyệt.
6. Vào **App settings > Basic**, copy **App ID** và **App Secret**.
7. Về Javis, trang **Kết nối** > thẻ **Meta Ads (tự tạo app - Graph API)** > dán App ID + App Secret > **Kết nối**. Trình duyệt mở trang Facebook để bạn đồng ý; xong quay lại Javis bấm làm mới.

Sau khi kết nối, hỏi Javis bằng lời: "tài khoản quảng cáo Facebook của tôi tuần này tiêu bao nhiêu, hiệu quả thế nào?". Javis có sẵn các công cụ đọc: danh sách tài khoản ads, hiệu suất (chi tiêu/hiển thị/click/CTR/CPC/reach/chuyển đổi) theo kỳ, và danh sách chiến dịch. Tất cả CHỈ ĐỌC - Javis không tạo/sửa chiến dịch, không tiêu tiền của bạn.

Về thời hạn: token Facebook sống khoảng 60 ngày, Javis tự gia hạn khi còn dùng. Nếu quá lâu không dùng và token hết hạn, chỉ cần bấm Kết nối lại để đăng nhập Facebook một lần nữa.

### 5b. Kết nối Facebook Trang và Theo dõi Facebook

Hai kết nối này nằm ở nhóm **Mạng xã hội** trong Kho, khác hẳn nhau về mục đích:

- **Facebook Trang (tự tạo app - Graph API)**: quản lý Trang/Fanpage của CHÍNH bạn. Chỉ đọc thì xem danh sách Trang, bài và bình luận; nâng Toàn quyền thì đăng bài chữ, ảnh, album nhiều ảnh, video, sửa bài đã đăng, trả lời và xoá bình luận. Cách đấu giống hệt Meta Ads (Graph API) ở trên và **dùng lại được đúng Facebook App đó** - vẫn phải bật thêm quyền Trang. Khi Facebook hỏi quyền, nhớ TICK chọn các Trang. Mặc định **Chỉ đọc**; xoá bài là không hoàn tác được (Trang không có thùng rác) nên chỉ nâng Toàn quyền khi thật sự cần Javis đăng bài.
- **Theo dõi Facebook (Apify)**: theo dõi Trang và Nhóm **công khai** của người khác để tìm bài viral, trả về số share/react/bình luận để lọc bài hot. Điểm quan trọng: nó quét qua dịch vụ Apify chứ KHÔNG dùng tài khoản Facebook cá nhân của bạn, nên không lo bị khoá và chạy tốt trên VPS 24/7. Cách đấu: đăng ký apify.com, vào Console > Settings > API & Integrations copy "Personal API token", dán vào. Chi phí tính theo lượt quét, khoảng 2.6 USD cho 1000 bài. Kết nối này **chỉ đọc**, không có đường ghi. Nhóm KÍN chưa hỗ trợ (sẽ cần thêm cookie).

### 5c. Các kết nối còn lại trong kho

- **Composio** (nhóm Kho ứng dụng): một kết nối mở ra hơn 500 app (Gmail, Notion, Sheets, GitHub, Linear, Slack...). Vào platform.composio.dev, tạo một MCP server, copy API key dạng `ck_...` dán vào. Sau đó muốn dùng app nào thì bảo thẳng trong chat ("nối Notion qua Composio"), Composio đưa link đăng nhập app đó cho bạn tự đăng nhập. **Lưu ý quan trọng về quyền**: mọi hành động của mọi app đều chạy qua MỘT tool chung của Composio nên Javis không tách được lệnh đọc với lệnh ghi. Mức Chỉ đọc (mặc định) chỉ tìm và xem mô tả tool, chưa chạy được gì; muốn Javis thao tác thật phải nâng **Toàn quyền**, và khi đó Javis làm được MỌI hành động trên các app bạn đã nối, kể cả gửi tin và xoá dữ liệu.
- **Higgsfield** (nhóm Sáng tạo): tạo và chỉnh ảnh/video bằng AI - sinh ảnh, sinh video, nâng nét, mở rộng khung hình, xoá nền, cắt nhân vật. Đăng nhập một chạm, không cần tạo app hay dán key: bấm **Kết nối** rồi đăng nhập tài khoản Higgsfield và cấp quyền. Mỗi lần tạo hoặc chỉnh **tiêu credit trả trước** trong tài khoản Higgsfield của bạn. Mặc định Ghi nháp (tạo được ngay, chặn xoá và thanh toán); muốn Javis chỉ xem lịch sử cho đỡ tốn credit thì hạ xuống Chỉ đọc.
- **X (Twitter)** (nhóm Mạng xã hội): tìm và đọc bài đăng, xem hồ sơ và số liệu công khai qua MCP chính chủ của X. Vào developer.x.com > Developer Portal > Projects & Apps > tab "Keys and tokens" > Generate **Bearer Token**, dán vào. Đây là token App-only nên **chỉ đọc** - chưa đăng bài được.
- **Substack** (nhóm Marketing): soạn và đăng bài viết / newsletter bằng lời. Javis gọi thẳng API Substack bằng Python nội bộ nên KHÔNG cần cài Node. Cần ba thứ: địa chỉ trang Substack của bạn, session token (cookie `substack.sid` lấy trong DevTools) và User ID; nút **Hướng dẫn** trong cửa sổ kết nối mở trang có trợ lý lấy nhanh User ID và địa chỉ trang. Mặc định **Ghi nháp** - chỉ tạo nháp, chưa đăng, chưa gửi ai. Muốn Javis đăng bài THẬT phải nâng Toàn quyền; kể cả khi đó, đăng mặc định chỉ lên web, chỉ khi bạn nói rõ "gửi email cho người đăng ký" Javis mới bật cờ gửi mail - và đã gửi mail thì không thu lại được. Session token có toàn quyền tài khoản Substack, giữ kín như mật khẩu.

### 6. Quản lý một tài khoản (chip)

Bấm vào chip tài khoản ở khu Đã kết nối để mở menu:

- **Test kết nối**: gọi thử, báo số công cụ khả dụng.
- **Đặt làm mặc định**: khi có nhiều tài khoản cùng dịch vụ, Javis ưu tiên tài khoản mặc định khi bạn không nói rõ shop nào.
- **Đổi tên** / **Tắt tạm** / **Xoá**.
- **Đổi quyền**: xem mục Phân quyền.
- **Chặn tool cụ thể**: dành cho người rành - gõ tên tool muốn cấm hẳn.
- **Nhật ký gọi tool**: xem Javis đã gọi gì, lúc nào, bị chặn gì.

### 7. Phân quyền 3 mức (quan trọng)

Mỗi tài khoản có một mức quyền, Javis chặn CỨNG tại chỗ:

- **Chỉ đọc**: chỉ xem số liệu. Tạo đơn, sửa dữ liệu, gửi tin... đều bị chặn. An toàn nhất, mặc định cho POS.
- **Ghi nháp**: được ghi/sửa dữ liệu thường (ghi chú, sản phẩm...), vẫn CHẶN hành động tiền/đơn/gửi tin.
- **Toàn quyền**: thao tác THẬT - tạo đơn, gửi tin, publish trang. Khi bật phải tick "Tôi hiểu rủi ro"; với Zalo có cảnh báo riêng.

Thông minh hơn bản cũ: Javis hiểu cả công cụ "2 trong 1" của Pancake - cùng tool đơn hàng, hỏi `danh sách đơn` thì cho qua, `tạo đơn` thì chặn nếu chưa đủ quyền.

Loop chạy nền còn bị siết thêm theo mode của loop: loop `suggest` chỉ đọc, loop `auto` không bao giờ đụng tiền/đơn/gửi tin - bất kể tài khoản đặt quyền gì.

### 8. Tự thêm dịch vụ ngoài kho (nâng cao)

Dịch vụ chưa có trong Kho? Bấm thẻ **Tự thêm (nâng cao)** - form kỹ thuật như bản cũ (URL/lệnh + header/env, hỗ trợ HTTP, SSE, stdio). Dịch vụ đăng nhập kiểu OAuth chuẩn MCP thì Javis tự mở trang đăng nhập và tự giữ token, chạy được cả trên VPS.

### 9. Chế độ "Chỉ dùng kết nối của Javis" (strict)

Tick ô này ở khu Đã kết nối nếu muốn Javis CHỈ dùng các kết nối khai ở đây, bỏ qua MCP cài sẵn trong Claude Code trên máy - kiểm soát chặt, tránh gọi nhầm công cụ của tài khoản Claude. Lưu ý: ô này áp cho engine Claude Code (cờ strict của Claude CLI); kho MCP gốc của Codex do lệnh codex quản riêng - muốn engine ChatGPT bỏ một server gốc thì gỡ bằng `codex mcp remove <tên>`.

## Đọc số liệu

Không đổi so với trước: hỏi trực tiếp trong chat ("hôm nay bán được bao nhiêu, so hôm qua thế nào?"), Javis gọi đúng nguồn, trả lời theo công thức số liệu + so kỳ trước + nguyên nhân + đề xuất, và tự đẩy 3-6 chỉ số lên bảng số liệu cột trái trang Javis. Kỳ đã đóng lưu cache trong `05 - Data Cache/` của brain. Có nhiều shop thì nói rõ tên shop, không nói thì Javis dùng tài khoản mặc định.

## Mẹo

- Đặt tên tài khoản theo cửa hàng cho dễ gọi trong chat ("shop Kim Khí" vs "shop 2").
- POS cứ để Chỉ đọc nếu bạn chỉ cần xem báo cáo - không lo Javis vô tình tạo đơn.
- Tin nhắn đầu sau khi bật máy có thể hơi chậm với kết nối dạng chạy local (Zalo, Webcake) do phải khởi động công cụ - các lượt sau nhanh vì Javis giữ kết nối sống.
- Nhật ký gọi tool là chỗ đầu tiên nên xem khi nghi Javis "làm gì đó lạ".

## Sự cố thường gặp

- **Facebook báo "URL bị chặn" lúc đăng nhập**: redirect URI trong app Facebook chưa khớp. Mở hộp thoại Kết nối của Javis, bấm **Sao chép** ở ô địa chỉ chuyển hướng rồi dán NGUYÊN VĂN vào ô "URI chuyển hướng OAuth hợp lệ" (Đăng nhập bằng Facebook > Cài đặt), Lưu. Đừng gõ tay - Facebook bắt khớp từng ký tự.
- **Facebook báo "Không thể tải URL - Miền của URL này không được đưa vào miền của ứng dụng"**: thiếu Miền ứng dụng. Vào Cài đặt ứng dụng > Thông tin cơ bản > ô "Miền ứng dụng", dán tên miền trần (không https, không dấu /) - có sẵn ô Sao chép trong hộp thoại Kết nối - rồi bấm "Lưu thay đổi" ở cuối trang.
- **Dán key báo "Key chưa đúng hoặc chưa đủ quyền"**: tạo lại API key trong dịch vụ, dán lại. Với Pancake kiểm tra key thuộc đúng cửa hàng.
- **Zalo báo "Cần cài Node.js 20+"**: cài Node.js từ nodejs.org rồi thử lại.
- **Google Ads / TikTok Ads báo không kết nối được**: kiểm tra máy đã cài `uv` chưa (`winget install astral-sh.uv`). Riêng **Google Ads phải có cả Git** vì `uvx` kéo server từ GitHub - máy thiếu Git thì có `uv` cũng chết. Lần kết nối đầu phải tải gói nên có thể chậm - bấm Test lại sau 1-2 phút.
- **Meta Ads (MCP chính chủ) báo "chưa cho kết nối tự phục vụ / DCR"**: đúng thực tế, không phải lỗi máy bạn - MCP hosted của Meta đang beta, chỉ nhận vài ứng dụng được Meta cấp phép sẵn. Muốn đọc số liệu ngay thì dùng kết nối **Meta Ads (tự tạo app - Graph API)** ở trên.
- **Meta Ads (Graph API) báo "Facebook từ chối / redirect_uri"**: kiểm tra theo nơi cài. Chạy trên **máy cá nhân**: (1) app đang ở chế độ Development - đây là thứ khiến localhost được chấp nhận, rời khỏi Development là hỏng ngay; (2) Javis mở bằng địa chỉ `localhost` chứ không phải 127.0.0.1; (3) App ID + App Secret dán đúng. Chạy trên **VPS/tên miền**: kiểm tra ô Valid OAuth Redirect URIs đã điền đúng địa chỉ **https** của bạn, khớp từng ký tự kể cả đường dẫn `/connect/oauth/callback`.
- **Không điền được localhost vào ô "URI chuyển hướng OAuth hợp lệ"**: đúng như vậy, không phải lỗi. App ở Chế độ phát triển thì Meta tự cho phép localhost và chặn không cho thêm tay, có chú thích ngay cạnh ô. Bỏ qua ô đó và đi tiếp; chỉ bản chạy trên VPS/tên miền mới phải điền.
- **Hiện bảng "Invalid Scopes: pages_show_list, pages_read_engagement, ..." (hoặc ads_read, business_management)**: **cứ bấm OK và đi tiếp.** Đây là cảnh báo Meta chỉ hiện cho người tạo app, **không chặn đăng nhập** - chính thông báo đó ghi "This message is only shown to developers". Khi app còn ở Chế độ phát triển và bạn là Quản trị viên của app, Facebook vẫn cấp đủ quyền, nên phần lớn trường hợp kết nối xong là dùng được ngay. Kiểm chứng nhanh: kết nối xong hỏi Javis "liệt kê các Trang của tôi"; thấy đủ Trang là ổn, không cần làm gì thêm.

  **Chỉ khi** kết nối xong mà Javis không thấy Trang nào (hoặc không thấy tài khoản quảng cáo nào) thì mới cần thêm quyền cho app. Trong **giao diện mới**, quyền bị khoá theo trường hợp sử dụng: app tạo bằng trường hợp "Xác thực và yêu cầu dữ liệu từ người dùng" chỉ có `email` và `public_profile`. Cách thêm:
  - **Quyền Trang**: **Thêm trường hợp sử dụng** > chọn **"Quản lý mọi thứ trên Trang của bạn"** > **Tùy chỉnh** > tab **Quyền** > bấm Thêm cho `pages_read_engagement`, `pages_manage_posts`, `pages_manage_engagement`. Hai quyền `pages_show_list` và `business_management` thường đã có sẵn trong trường hợp sử dụng này.
  - **Quyền quảng cáo**: **Thêm trường hợp sử dụng** > chọn trường hợp liên quan quảng cáo (Marketing API) > **Tùy chỉnh** > tab **Quyền** > Thêm `ads_read` và `business_management`.
  - **Giao diện cũ**: vào **Sản phẩm > Thêm sản phẩm**, thêm **Marketing API** (cho quảng cáo) hoặc **Đăng nhập bằng Facebook** bản thường (cho Trang); ở Chế độ phát triển bạn tự cấp được các quyền này mà không cần App Review.
  Thêm xong quay lại Javis bấm Kết nối lại là chạy.
- **Muốn cho Javis quản lý THÊM một Trang (fanpage) nữa**: bấm **Kết nối lại** trên thẻ Facebook Trang. Facebook sẽ hiện lại màn **"Chọn nội dung bạn cho phép"** - tick thêm Trang mới, đồng thời **giữ nguyên các Trang cũ** (bỏ tick Trang nào là Javis mất quyền Trang đó), rồi bấm Tiếp tục. Không phải xoá tài khoản đi đấu lại từ đầu. Nếu Facebook vẫn nhảy thẳng qua kiểu "Tiếp tục với tên bạn" mà không cho chọn, kiểm tra Javis đã cập nhật lên bản 0.9.249 trở lên; bản cũ thiếu tham số ép Facebook hỏi lại nên bị bỏ qua màn chọn Trang.
- **Meta Ads (Graph API) báo "không thấy tài khoản quảng cáo"**: token thiếu quyền `ads_read` hoặc tài khoản Facebook đăng nhập không phải admin của ad account nào - kiểm tra vai trò trong Business/Ads Manager.
- **Trong app không thấy mục "Sản phẩm", hoặc không thấy "Đăng nhập bằng Facebook cho doanh nghiệp"**: bạn đang ở **giao diện MỚI** của Meta, nơi menu Sản phẩm đã bị thay bằng **Trường hợp sử dụng**. Vào cột trái **Trường hợp sử dụng > Tùy chỉnh > Cài đặt** là thấy ô URI chuyển hướng. Đây KHÔNG phải do Business Manager chưa xác minh, cũng không phải do thiếu quyền - xem lại bước 2 ở mục hướng dẫn trên.
- **Không thấy "Đăng nhập bằng Facebook cho doanh nghiệp" dù đã tìm đúng chỗ**: bản "cho doanh nghiệp" chỉ hiện với app tạo đúng **loại Doanh nghiệp (Business)**, và loại app đã tạo thì không đổi được. Nhưng cách đấu của Javis dùng **Đăng nhập bằng Facebook bản THƯỜNG**, nên bạn không cần bản cho doanh nghiệp.
- **Mã QR hết hạn**: bấm thử lại để lấy QR mới (QR Zalo sống ~3 phút).
- **Tool bị chặn kèm dòng "đang ở mức quyền hạn chế"**: đúng thiết kế - nâng quyền tài khoản trong menu chip nếu bạn thật sự muốn Javis làm việc đó.
- **Sau khi cập nhật từ bản cũ**: các server MCP cũ tự chuyển thành tài khoản trong trang Kết nối (bản gốc backup ở `mcp_servers.v1.bak.json`), không phải khai lại.
- **Muốn quay về cơ chế cũ** (mỗi server một entry, không qua hub): đặt `"mcp": {"hub": false}` trong `server/settings.json` rồi khởi động lại.

## Liên quan

- [Models & engine](10-models-va-engine.md) - bộ não nào dùng được gì, đổi model ở đâu.
- [Zalo Agent MCP](12-zalo.md) - đăng nhập QR, bảy tool và cách phân quyền.
- [Trò chuyện & giọng nói](02-tro-chuyen-va-giong-noi.md) - hỏi số liệu bằng lời.
- [Mức dùng: token & chi phí](23-muc-dung-token.md) - xem việc gọi công cụ đang đốt bao nhiêu.
