# Plugins: thêm công cụ native cho mọi engine

Plugin là cách thêm **công cụ mới** cho Javis mà không phải sửa mã nguồn: một thư mục Python thả vào đúng chỗ, Javis tự nạp, và từ đó mọi engine (Claude Code, ChatGPT/Codex, OpenRouter, OpenAI, Anthropic, Gemini) đều gọi được công cụ đó.

Trang này hướng dẫn đọc danh sách plugin trong dashboard, bật/tắt từng cái, hiểu 11 plugin có sẵn, và cách tự cài plugin riêng kèm rào an toàn bắt buộc phải biết trước khi làm.

## Tính năng này là gì

Một plugin là **một thư mục** gồm 2 file:

- `plugin.yaml`: khai báo tên, slug, mô tả, phiên bản, bật hay tắt, mức quyền tối thiểu, danh sách tool và hook.
- `plugin.py`: mã Python, bắt buộc có hàm `register(ctx)`. Trong hàm đó bạn gọi `ctx.register_tool(...)` để thêm tool, và/hoặc `ctx.register_hook(...)` để thêm hook.

Plugin cho Javis hai thứ:

- **Tool**: một công cụ engine gọi được, ví dụ `javis_now` (hỏi bây giờ mấy giờ theo giờ Việt Nam) hay `javis_generate_image` (tạo ảnh). Tool của plugin đi qua MCP Hub nên **mọi engine đều dùng được**, không riêng Claude Code.
- **Hook**: đoạn mã chạy **quanh mỗi lần gọi tool**. Bản hiện tại hỗ trợ hai sự kiện: `pre_tool_call` (trước khi tool chạy) và `post_tool_call` (sau khi tool chạy xong). Khi không plugin nào đăng ký hook thì Javis không bọc gì cả, nên không tốn thêm gì.

Tool của plugin **tôn trọng đúng 3 mức quyền** của Javis y như tool khác, nên một loop đang ở chế độ chỉ-đọc sẽ không tự gọi được tool ghi của plugin.

## Plugin khác Skill và MCP thế nào

Ba thứ này hay bị lẫn. Phân biệt bằng câu hỏi "cái đang thiếu là gì":

| Thiếu gì | Dùng cái nào | Bản chất |
|---|---|---|
| Javis chưa biết **cách làm** một loại việc theo chuẩn của bạn | **Skill** | Một file `SKILL.md` chứa hướng dẫn. Không chạy mã, chỉ dạy AI làm đúng quy trình. Xem [Skills](06-skills.md). |
| Cần một **hành động thật** bằng Python (tính toán, biến đổi dữ liệu, gọi một API đơn giản, đọc/ghi file theo luật riêng) mà chưa có nguồn nào phủ | **Plugin** | Mã Python chạy thật, thêm tool/hook cho mọi engine. |
| Cần **nguồn dữ liệu ngoài** đã có server sẵn (POS, quảng cáo, lịch, email, ghi chú...) | **Kết nối (MCP)** | Đấu server có sẵn ở trang Kết nối, không phải viết mã. Xem [Kết nối & số liệu kinh doanh](09-mcp-va-so-lieu.md). |

Nói ngắn: skill là **tri thức cách làm**, plugin là **mã chạy thật**, MCP là **nguồn dữ liệu có sẵn**. Nếu việc bạn cần đã có MCP thì đừng viết plugin.

## Mở ở đâu trong Javis

Mở dashboard (mặc định tại cổng 7777), nhìn thanh điều hướng bên trái, bấm nhóm **Năng lực** để mở ra, rồi bấm mục **Plugins**. Đầu trang hiện tiêu đề **Plugins** kèm dòng phụ "Tool/hook native cho mọi engine".

Ngay dưới tiêu đề là ba khối giới thiệu:

1. Dòng mô tả: "Plugin thêm **tool** (công cụ engine gọi được) và **hook** native cho Javis mà không sửa lõi - dùng được ở MỌI engine (Claude Code, Codex, API) qua hub, tôn trọng 3 mức quyền như tool khác."
2. Khung cảnh báo màu cam (chỉ hiện khi chưa mở khoá): "**⚠ Plugin do bạn cài đang bị chặn.** Plugin toàn cục/brain chạy code Python thật trong server nên mặc định TẮT. Để bật: đặt biến môi trường `JAVIS_ENABLE_USER_PLUGINS=true` rồi khởi động lại Javis. Plugin có sẵn (bundled) vẫn chạy bình thường."
3. Dòng chỉ đường xám: "Thả plugin TOÀN CỤC (dùng cho MỌI brain) vào `<đường dẫn thật trên máy bạn>` · mỗi plugin gồm `plugin.yaml` + `plugin.py`. Hoặc bảo Javis trong khung chat: "tạo plugin ..."."

Đường dẫn trong dòng thứ 3 là đường dẫn **thật** trên máy đang chạy Javis, cứ sao chép từ màn hình ra chứ đừng gõ tay theo tài liệu.

Bên dưới là danh sách thẻ plugin, xếp theo nguồn: Có sẵn trước, rồi Toàn cục, rồi Brain này; trong mỗi nhóm xếp theo tên. Nếu chưa có plugin nào, trang hiện dòng "Chưa có plugin nào. Thả một thư mục plugin vào `<đường dẫn>` rồi tải lại."

## Đọc một thẻ plugin

Mỗi plugin là một thẻ. Đọc từ trên xuống:

**Dòng đầu (bên trái):** biểu tượng 🧩, tên hiển thị của plugin, rồi **slug** in nhỏ mờ (chính là tên thư mục), rồi một nhãn nguồn:

| Nhãn nguồn | Nghĩa là | Nằm ở đâu |
|---|---|---|
| **Có sẵn** (xanh lá) | Plugin đi kèm app, do Javis phát hành, tin cậy | `system/plugins/<slug>/` trong thư mục cài đặt |
| **Toàn cục** (xanh dương) | Plugin bạn tự cài, dùng chung cho **mọi brain** | Thư mục state của Javis, `<JAVIS_STATE_DIR>/plugins/<slug>/` |
| **Brain này** (cam) | Plugin bạn tự cài, chỉ dùng cho **một brain** | `<brain>/plugins/<slug>/` (brain cũ có thể là `<brain>/Javis/plugins/<slug>/`) |

Trùng slug thì nguồn sau đè nguồn trước: một plugin "Brain này" tên `datetime-vn` sẽ thay chỗ bản "Có sẵn" cùng tên.

**Dòng đầu (bên phải):** trạng thái hiện tại (xem bảng ở mục "Bảng tra nhanh nút và trạng thái").

**Dòng mô tả:** nội dung trường `description` trong `plugin.yaml`.

**Dòng thông tin:** ghép bằng dấu chấm giữa, gồm "quyền tối thiểu: ..." rồi phiên bản (`v1.0.0`) rồi tác giả. Ví dụ: "quyền tối thiểu: chỉ đọc · v1.0.0 · Javis (bundled)".

**Hàng chip:** mỗi tool plugin cung cấp là một chip có biểu tượng 🔧 kèm tên tool; mỗi hook là một chip 🪝 kèm tên sự kiện. Đây chính là những cái tên engine sẽ gọi, nên nếu muốn nhờ Javis dùng đúng tool nào, cứ nhắc tên trong chip.

**Nút cuối thẻ:** **Bật** hoặc **Tắt** (nhãn đổi theo trạng thái hiện tại).

Thẻ của plugin không chạy sẽ hiển thị mờ đi. Nếu plugin lỗi, dòng lý do lỗi hiện màu đỏ ngay dưới hàng chip.

## Cách dùng (từng bước)

### Bước 1: Xem plugin nào đang chạy

Vào **Năng lực > Plugins**. Nhìn cột trạng thái bên phải mỗi thẻ. Chỉ những thẻ ghi **● đang chạy** mới thực sự có tool bơm ra cho engine. Thẻ mờ là không dùng được lúc này.

### Bước 2: Bật hoặc tắt một plugin

1. Tìm thẻ plugin cần đổi.
2. Bấm nút **Bật** (hoặc **Tắt**) ở cuối thẻ.
3. Danh sách tự tải lại, trạng thái đổi ngay.

Với plugin **Có sẵn**, Javis không sửa file của app: lựa chọn bật/tắt được ghi ra file `plugins.json` trong thư mục state. Nhờ vậy cập nhật Javis lên bản mới **không làm mất** lựa chọn của bạn.

Với plugin **Toàn cục** và **Brain này**, Javis ghi thẳng `enabled: true/false` vào `plugin.yaml` của plugin đó.

Bật/tắt có hiệu lực ngay, không cần khởi động lại: Javis làm mới bộ nhớ đệm của hub nên tool xuất hiện hoặc biến mất ở lượt chat kế tiếp, và chỉ mục năng lực `Javis/index.md` của brain cũng được dựng lại.

Ngoại lệ duy nhất: nếu bạn bật một plugin **Toàn cục/Brain này** trong khi chưa mở khoá biến môi trường, Javis hiện hộp thoại báo: "Đã bật trong manifest NHƯNG plugin do người dùng cài chỉ chạy khi đặt biến môi trường JAVIS_ENABLE_USER_PLUGINS=true rồi khởi động lại (bảo vệ chống chạy code lạ)." Thẻ khi đó chuyển sang **⚠ chờ bật env**.

### Bước 3: Kiểm tra tool đã ra tới engine chưa

Mở khung trò chuyện và hỏi thẳng, ví dụ "bây giờ mấy giờ" (plugin `datetime-vn`) hoặc "liệt kê các Trang Facebook của tôi" (plugin `meta-pages-graph`). Javis biết plugin nào đang chạy vì danh sách "Plugins đang chạy" kèm tên tool được đưa sẵn vào ngữ cảnh mỗi lượt chat.

Nếu tool bị chặn vì mức quyền, câu trả lời sẽ chứa nguyên văn dòng lỗi bắt đầu bằng `ERROR: tool '<tên>' cần mức quyền cao hơn`. Nếu tool cần một kết nối chưa có, lỗi sẽ nói rõ phải vào trang nào để đấu nối.

## Các plugin có sẵn

Đây là các plugin đi kèm app (nhãn **Có sẵn**). Tất cả bật sẵn trừ `tool-audit`.

| Tên trên thẻ | slug | Tool cung cấp | Quyền tối thiểu | Mặc định |
|---|---|---|---|---|
| Thời gian & ngày (VN) | `datetime-vn` | `javis_now`, `javis_date_add` | chỉ đọc | Bật |
| Đặt việc định kỳ & nhắc hẹn | `javis-schedule` | `javis_schedule` | ghi (safe) | Bật |
| Giao việc Kanban | `javis-task` | `javis_task` | ghi (safe) | Bật |
| Đấu thêm MCP | `javis-connect` | `javis_add_mcp` | ghi (safe) | Bật |
| Tạo ảnh (ChatGPT) | `image-chatgpt` | `javis_generate_image` | ghi (safe) | Bật |
| Đọc video YouTube | `youtube-read` | `javis_youtube_read` | chỉ đọc | Bật |
| Meta Ads (Graph API) | `meta-ads-graph` | `meta_ads_accounts`, `meta_ads_insights`, `meta_ads_campaigns`, `meta_ads_get` | chỉ đọc | Bật |
| Facebook Trang (Graph API) | `meta-pages-graph` | `fb_pages_list`, `fb_page_posts`, `fb_page_comments`, `fb_page_post`, `fb_page_photo`, `fb_page_album`, `fb_page_video`, `fb_page_edit`, `fb_page_delete`, `fb_page_reply` | toàn quyền | Bật |
| Theo dõi Facebook (Apify) | `fb-monitor-apify` | `fb_monitor` | chỉ đọc | Bật |
| Gửi ảnh & file qua Zalo | `zalo-image` | `zalo_send_image` | toàn quyền | Bật |
| Nhật ký dùng tool | `tool-audit` | `javis_tool_stats` + hook `post_tool_call` | chỉ đọc | **Tắt** |

Từng cái làm được gì:

- **Giao việc Kanban**: giao một việc nền vào hàng đợi ngay từ chat (`op=add`) và xem việc đang chạy tới đâu (`op=list`). Có từ 0.17.1. Trước đó đường duy nhất để giao việc là `POST /kanban/task`, mà gọi được nó thì phải chạy được lệnh máy - nên chỉ Claude Code với Codex làm được, dù tài liệu vẫn hứa mọi bộ não đều làm được. Tool này gọi thẳng vào hàng đợi in-process, không mở thêm cửa HTTP nào. Hai rào cứng: **không tạo được việc mức `full`** (mức tự tiêu tiền, tạo đơn, gửi tin - phải do chính bạn đặt ở trang Việc), và mặc định là `suggest`. Chuyển cột, huỷ việc, duyệt việc chờ phê duyệt vẫn làm ở trang Việc.
- **Đấu thêm MCP**: nhờ Javis ngay trong chat đấu một nguồn MCP mới, và nó **hiện ra trang Kết nối** ở khu "Đã kết nối" như tài khoản bạn tự thêm bằng tay, dùng chung cho mọi bộ não. Trước plugin này Javis không có đường nào ghi vào kho kết nối, nên nó chỉ còn cách chạy `claude mcp add` - server đó rơi vào cấu hình riêng của Claude Code, sáu bộ não còn lại không thấy, và trên trang Kết nối nó không nằm ở khu "Đã kết nối" mà lọt xuống khu gập "Kết nối sẵn của Claude Code và Codex" (mặc định đóng), nên nhìn vào tưởng như chẳng có gì được thêm. Ba rào an toàn: mức quyền mặc định là **chỉ đọc** (muốn cho ghi thì bạn tự nâng ở trang Kết nối); nguồn chạy bằng **lệnh trên máy** (stdio) được thêm ở trạng thái **tắt** để bạn tự đọc lệnh rồi mới bật; dịch vụ đã có sẵn trong Kho kết nối (Gmail, Lịch, POS...) thì Javis chỉ tay sang đúng card chứ không đẻ một bản tự khai song song. Thử kết nối hỏng thì mục đó **vẫn nằm lại** trang Kết nối kèm lý do, chứ không biến mất im lặng.
- **Gửi ảnh & file qua Zalo**: gửi ảnh (ví dụ ảnh Javis vừa tạo) hoặc file kèm lời nhắn qua Zalo, bằng chính tài khoản đã quét QR ở trang Kết nối. Có vì tool `zalo_send_message` của MCP chuẩn chỉ gửi được chữ, trong khi thư viện bên dưới làm được từ lâu và bản 1.6.2 đã là bản mới nhất nên chờ upstream là chờ vô hạn. Chỉ gửi được file NẰM TRONG bộ não đang dùng - rào cố ý, vì tin nhắn Zalo gửi đi thì không thu hồi được. Cần Node.js 20+. Chi tiết ở [Zalo](12-zalo.md).
- **Thời gian & ngày (VN)**: cho Javis biết hôm nay là ngày nào, mấy giờ, thứ mấy theo giờ Việt Nam (UTC+7), và tính ngày tương đối ("3 ngày nữa", "tuần trước"). Thuần thư viện chuẩn, không cần mạng. Đây cũng là plugin mẫu đơn giản nhất để đọc khi bạn muốn tự viết plugin.
- **Đặt việc định kỳ & nhắc hẹn**: cho phép tạo, liệt kê, huỷ việc định kỳ và nhắc hẹn **ngay trong câu chat**, khỏi gõ YAML tay. Việc lặp và bền được ghi ra `Javis/loops/<slug>.md` (mở sửa được trong Obsidian); nhắc một lần hoặc lịch cron thì vào kho nhắc hẹn. Chi tiết ở [Việc định kỳ & Nhắc hẹn](08-viec-dinh-ky.md).
- **Tạo ảnh (ChatGPT)**: tạo ảnh từ mô tả bằng chính **gói ChatGPT** bạn đang đăng nhập (OAuth), không cần khoá API OpenAI. Ảnh lưu vào `attachments/` của brain rồi nhúng thẳng vào câu trả lời. Cần đã kết nối ChatGPT ở trang **Models**; chưa kết nối thì tool trả về câu "Chưa kết nối ChatGPT (OAuth). Vào trang Model đăng nhập ChatGPT rồi thử lại...".
- **Đọc video YouTube**: dán link video vào chat rồi nhờ tóm tắt. Plugin lấy **phụ đề thật** của video (đường mà trình phát YouTube dùng) nên Javis đọc được lời thoại chứ không đoán theo tiêu đề. Không cần khoá API, không cần đăng nhập YouTube, chạy trên **mọi engine** kể cả engine API vốn không mở được URL. Video không có phụ đề, video riêng tư hoặc bị YouTube chặn thì tool nói thẳng lý do để Javis khỏi bịa. Video dài bị cắt bớt thì nhờ "đọc tiếp" là nó đọc khúc sau. Chi tiết ở [Trò chuyện](02-tro-chuyen-va-giong-noi.md).
- **Luật cho từng cuộc chat Zalo**: đặt cách ứng xử cho từng nhóm hoặc từng khách trên Zalo bằng lời (im lặng, báo mọi tin, báo theo từ khoá, nhắc khi quên trả lời quá N phút). Luật ghi ra `Javis/zalo/<slug>.md` nên xem và sửa lại được.
- **Gửi tin Zalo an toàn**: gửi tin Zalo thay cho tool thô. Nó khoá cứng vào tài khoản đang nghe và chỉ gửi được cho cuộc chat trong danh sách đang theo dõi; tên khớp nhiều người thì từ chối và bắt hỏi lại. Hai plugin Zalo dùng chung với [Kênh Zalo](12-zalo.md).
- **Meta Ads (Graph API)**: đọc số liệu quảng cáo Facebook/Instagram (danh sách tài khoản ads, chiến dịch, hiệu suất). **Chỉ đọc, không tiêu tiền.** Cần đã đấu kết nối "Meta Ads (tự tạo app - Graph API)" ở trang Kết nối.
- **Facebook Trang (Graph API)**: quản lý Trang/Fanpage. Đọc danh sách Trang, bài và bình luận là chỉ-đọc; đăng bài, đăng ảnh, đăng album, đăng video, sửa chữ, xoá bài, trả lời bình luận là hành động **thật, công khai** và cần mức toàn quyền. Cần kết nối "Facebook Trang (tự tạo app - Graph API)".
- **Theo dõi Facebook (Apify)**: theo dõi Trang và Nhóm **công khai** để tìm bài nhiều lượt chia sẻ, qua dịch vụ Apify. Chỉ đọc, không đụng tài khoản cá nhân, chạy được trên VPS. Cần dán Personal API token của apify.com vào kết nối "Theo dõi Facebook (Apify)".
- **Nhật ký dùng tool**: đếm số lần **mỗi** tool được engine gọi (qua hook `post_tool_call`) rồi cho xem thống kê tool hay dùng nhất. Đây là ví dụ minh hoạ cơ chế hook, nên mặc định để tắt; bật ở trang Plugins, chat vài lượt có gọi tool, rồi hỏi Javis "tool nào hay dùng nhất".

Lưu ý về cột "Quyền tối thiểu": đó là mức khai báo cho **cả plugin** và là cái hiển thị trên thẻ. Từng tool bên trong vẫn có mức riêng. Ví dụ `meta-pages-graph` ghi "toàn quyền" trên thẻ, nhưng ba tool đọc bài/bình luận của nó chỉ cần mức chỉ-đọc, còn các tool đăng và xoá mới cần toàn quyền.

## Mức quyền tối thiểu và chế độ chạy

Mỗi tool plugin khai báo một mức quyền tối thiểu; mỗi lượt chạy của Javis lại có một trần quyền. Tool chỉ chạy khi trần của lượt chạy đủ cao.

| Mức tối thiểu của tool (nhãn trên thẻ) | Ý nghĩa | Chạy được ở chế độ nào |
|---|---|---|
| `readonly` - "chỉ đọc" | Chỉ đọc hoặc tính toán, không đổi gì | Mọi chế độ |
| `safe` - "ghi (safe)" | Có ghi file hoặc tiêu quota | Chế độ Tự làm an toàn và Toàn quyền |
| `full` - "toàn quyền" | Hành động thật ra ngoài (đăng bài, xoá, gửi) | Chỉ chế độ Toàn quyền |

Khung chat bạn gõ tay chạy ở mức đầy đủ nên gọi được cả ba loại. Ngược lại, một [việc định kỳ](08-viec-dinh-ky.md) đang để chế độ **Đề xuất** chỉ chạy được tool chỉ-đọc; gặp tool mức cao hơn nó trả về `ERROR: tool '<tên>' cần mức quyền cao hơn (...)` và dừng lại thay vì làm liều. Đây là lớp chặn cứng trong mã, không phải lời dặn trong prompt, nên model không "nói khéo" để vượt được.

## Cài plugin của bạn

### Bước 1: Chọn nơi đặt

Có hai chỗ, tuỳ bạn muốn plugin dùng chung hay dùng riêng:

- **Toàn cục** (khuyên dùng): `<JAVIS_STATE_DIR>/plugins/<slug>/`. Mọi brain đều thấy plugin này, và mọi engine đều gọi được. Đường dẫn thật đang hiện sẵn ở dòng chỉ đường trên trang Plugins, cứ sao chép từ đó. Mặc định `JAVIS_STATE_DIR` là thư mục `server/` của dự án; trên Docker/VPS thường là `/data/state`.
- **Riêng một brain**: `<brain>/plugins/<slug>/`. Chỉ brain đó dùng được. Hợp khi plugin gắn chặt với dữ liệu của một brain cụ thể.

`<slug>` là tên thư mục, phải là chữ thường ASCII không dấu, bắt đầu bằng chữ hoặc số, chỉ chứa chữ số, dấu chấm, gạch dưới, gạch nối. Sai kiểu chữ thì Javis bỏ qua plugin và báo "slug không hợp lệ".

### Bước 2: Viết plugin.yaml

```yaml
name: Tính tiền ship
slug: tinh-tien-ship
version: 1.0.0
description: Tính phí giao hàng theo cân nặng và khu vực theo bảng giá của shop.
author: Bạn
enabled: false            # luôn tạo ở trạng thái TẮT, tự bật sau khi đọc lại mã
min_mode: readonly        # readonly | safe | full
tools: [tinh_tien_ship]
hooks: []                 # ví dụ: [post_tool_call]
```

Hai trường `tools` và `hooks` ở đây chỉ để **hiển thị chip trên thẻ**. Cái thực sự tạo ra tool là mã trong `plugin.py`, nên hãy giữ hai danh sách này khớp với mã cho khỏi rối.

### Bước 3: Viết plugin.py

```python
def register(ctx):
    def handler(args, ctx):        # args là dict; trả về chuỗi. Lỗi thì trả "ERROR: ..."
        kg = float((args or {}).get("kg") or 0)
        return f"Phí ship: {int(kg * 5000)} đồng"

    ctx.register_tool(
        name="tinh_tien_ship",
        description="Tính phí giao hàng theo cân nặng (kg). Dùng khi khách hỏi phí ship.",
        handler=handler,
        min_mode="readonly",
        schema={"type": "object",
                "properties": {"kg": {"type": "number", "description": "Cân nặng kiện hàng"}},
                "required": ["kg"]},
    )
```

Vài điều cần nhớ khi viết:

- Tên tool phải bắt đầu bằng chữ thường, chỉ gồm chữ thường, số và gạch dưới.
- `description` là thứ engine đọc để quyết định **khi nào** gọi tool, nên viết rõ tình huống và tham số. Mô tả mờ thì tool nằm im không ai gọi.
- Handler có thể là hàm thường hoặc `async`. Trả về chuỗi là gọn nhất; trả về dict thì Javis tự chuyển thành JSON.
- `ctx` có sẵn `ctx.slug`, `ctx.vault_root` (brain đang làm việc) và `ctx.data_dir` (thư mục riêng để plugin lưu state, **không** nằm trong brain nên không làm bẩn ghi chú của bạn).
- Muốn tool tự từ chối khi chưa đủ điều kiện (chưa đăng nhập, thiếu khoá), truyền thêm `check_fn=` là một hàm trả về `None` khi sẵn sàng hoặc một câu tiếng Việt giải thích khi chưa.
- Một plugin lỗi **không làm sập** Javis: mọi bước nạp, mọi lần gọi tool và hook đều được bọc lại, lỗi chỉ hiện trên thẻ plugin đó.

### Bước 4: Mở khoá bằng biến môi trường

Plugin bạn tự cài **mặc định bị chặn**, kể cả khi `enabled: true`. Để mở khoá:

1. Mở file `.env` ở thư mục gốc dự án (chưa có thì tạo, xem [Cấu hình .env](16-cau-hinh-env.md)).
2. Thêm một dòng: `JAVIS_ENABLE_USER_PLUGINS=true`
3. Lưu file và **khởi động lại Javis**.
4. Quay lại trang **Plugins**: khung cảnh báo màu cam biến mất, và plugin đang bật chuyển sang **● đang chạy**.

Giá trị nhận là `1`, `true`, `yes` hoặc `on` (không phân biệt hoa thường). Tên cũ `JAVIS_ENABLE_VAULT_PLUGINS` vẫn còn tác dụng để tương thích, nhưng nên dùng tên mới.

## Rào an toàn (đọc trước khi cài plugin lạ)

Đây là phần quan trọng nhất của trang này.

- **Plugin do bạn cài chạy mã Python thật, trong chính tiến trình server của Javis.** Nó có quyền của tiến trình đó: đọc ghi file, gọi mạng, đọc biến môi trường. Vì vậy Javis **chặn cứng theo mặc định** và chỉ chạy khi bạn tự tay đặt `JAVIS_ENABLE_USER_PLUGINS=true` rồi khởi động lại. Đây là rào chống việc ai đó ghi được một thư mục vào brain là chạy được mã trên máy bạn.
- **Chỉ mở khoá khi bạn đã tự đọc mã** của mọi plugin đang nằm trong hai thư mục đó. Biến môi trường này mở khoá cho **tất cả** plugin người dùng, không mở lẻ từng cái.
- **Plugin có sẵn (nhãn "Có sẵn") không chịu rào này** vì chúng đi kèm bản phát hành Javis. Chúng vẫn chạy bình thường khi biến môi trường chưa bật.
- **Plugin do Javis tạo qua chat luôn ở trạng thái tắt** (`enabled: false`) và mức `readonly`. Javis không tự bật hộ; bạn phải đọc mã rồi tự bấm **Bật**.
- **Đừng viết plugin để làm hành động tiền bạc, tạo đơn, gửi tin hay đăng bài.** Những việc đó nên đi qua kết nối MCP và hệ mức quyền, nơi đã có lớp chặn và nhật ký. Plugin nên để `min_mode: readonly` trừ khi bạn cố ý cần khác.
- **Đừng nhân bản plugin có sẵn vào brain.** Chúng đi theo app và tự cập nhật; bản sao trong brain sẽ đè mất bản gốc và không được cập nhật nữa.

## Nhờ Javis tạo plugin bằng lời

Bạn không cần tự gõ hai file. Mở khung trò chuyện và nói thẳng, ví dụ: "Tạo cho tôi một plugin tính phí ship theo cân nặng, bảng giá 5 nghìn một ký, dưới 1 ký tính tròn."

Javis sẽ tự chọn loại năng lực phù hợp trước (nếu chỉ cần hướng dẫn thì nó tạo skill, nếu là nguồn dữ liệu có sẵn thì nó khuyên đấu MCP), kiểm tra trùng với những gì brain đã có, rồi mới ghi thư mục plugin. Khi tạo xong nó báo lại tên file và nhắc bạn rằng plugin đang tắt cùng cách mở khoá biến môi trường.

Sau đó bạn tự làm 3 việc: mở `plugin.py` đọc lại mã (dùng trang **Tệp tin** nếu plugin nằm trong brain), đặt biến môi trường nếu chưa có, rồi vào **Plugins** bấm **Bật**.

## Hook: chạy quanh mỗi lần gọi tool

Ngoài tool, plugin còn đăng ký được hook. Bản hiện tại có hai sự kiện:

| Sự kiện | Bắn khi nào | Nhận được gì |
|---|---|---|
| `pre_tool_call` | Ngay trước khi một tool bất kỳ chạy | `tool_name`, `args`, `mode`, `vault_root` |
| `post_tool_call` | Ngay sau khi tool chạy xong | thêm `result` |

Hook bọc **mọi** tool call, kể cả tool của MCP và tool lõi, chứ không riêng tool của plugin đó. Dùng để ghi nhật ký, đếm, cảnh báo. Khi không plugin nào đăng ký hook, Javis không bọc gì nên không mất thêm hiệu năng. Plugin `tool-audit` là ví dụ chạy được: bật nó lên là mỗi lượt gọi tool được đếm vào một file riêng của plugin.

## Bảng tra nhanh nút và trạng thái

| Bạn thấy | Ý nghĩa / thao tác |
|---|---|
| **● đang chạy** (xanh lá) | Plugin đã nạp, tool của nó đang có mặt cho engine |
| **⚠ chờ bật env** (cam) | Bạn đã bật plugin nhưng chưa đặt `JAVIS_ENABLE_USER_PLUGINS=true`, hoặc đặt rồi mà chưa khởi động lại |
| **⚠ lỗi** (đỏ) | Manifest hỏng hoặc mã nạp không được; lý do hiện ngay dưới hàng chip |
| **○ tắt** (xám) | Plugin có mặt nhưng đang tắt, không có tool nào ra |
| **● bật (chưa nạp)** (cam) | Trạng thái hiếm: đã bật nhưng chưa nạp được vì lý do khác. Tải lại trang, nếu vẫn vậy thì xem log server |
| Nhãn **Có sẵn** / **Toàn cục** / **Brain này** | Nguồn của plugin (app / thư mục chung mọi brain / một brain) |
| Chip **🔧 tên** | Một tool plugin cung cấp; đây là tên engine sẽ gọi |
| Chip **🪝 tên** | Một hook plugin đăng ký (`pre_tool_call` hoặc `post_tool_call`) |
| "quyền tối thiểu: chỉ đọc / ghi (safe) / toàn quyền" | Mức quyền tối thiểu để tool của plugin được phép chạy |
| Nút **Bật** | Bật plugin (thẻ đang tắt) |
| Nút **Tắt** | Tắt plugin (thẻ đang bật) |
| Thẻ hiển thị mờ | Plugin không đang chạy |
| Khung cảnh báo cam đầu trang | Chưa mở khoá plugin người dùng; plugin có sẵn vẫn chạy |

## Mẹo

- Trước khi định viết plugin, hỏi lại: cái thiếu là **cách làm** hay **hành động**? Thiếu cách làm thì viết skill, rẻ và dễ sửa hơn nhiều.
- Đọc `system/plugins/datetime-vn/plugin.py` làm mẫu khởi động: nó ngắn, thuần thư viện chuẩn, đủ minh hoạ một tool đọc. Muốn xem mẫu có hook thì đọc `tool-audit`.
- Đặt plugin ở **Toàn cục** trừ khi có lý do rõ ràng để buộc vào một brain. Toàn cục không phụ thuộc brain nên bạn đổi brain vẫn dùng được.
- Không dùng plugin nào thì **tắt** thay vì xoá thư mục, để lần sau bật lại là xong.
- Tắt bớt plugin không dùng cũng làm gọn danh sách tool đưa cho model, giúp nó chọn tool đúng hơn.
- Muốn biết Javis đang thấy những năng lực gì (agent, skill, workflow, loop, plugin) thì mở file `Javis/index.md` trong brain bằng trang **Tệp tin**; file này tự dựng lại mỗi khi bạn bật/tắt plugin.

## Sự cố thường gặp

- **Thẻ ghi "⚠ chờ bật env":** bạn chưa đặt `JAVIS_ENABLE_USER_PLUGINS=true`, hoặc đã đặt nhưng chưa khởi động lại Javis. Biến này chỉ được đọc lúc khởi động.
- **Đã đặt biến môi trường mà vẫn bị chặn:** kiểm tra file `.env` nằm đúng thư mục gốc dự án, dòng biến không bị dấu `#` ở đầu, và giá trị là `true` (hoặc `1`/`yes`/`on`). Trên Docker thì đặt biến ở phần Environment của container chứ không phải trong file trên máy chủ.
- **Plugin mới thả vào mà không hiện trên trang:** thư mục phải nằm **trực tiếp** trong thư mục plugins (không lồng thêm cấp), và bên trong phải có `plugin.py` (hoặc `__init__.py`). Thiếu thì Javis không coi đó là plugin. Tên thư mục cũng phải là slug hợp lệ (chữ thường không dấu).
- **Thẻ ghi "⚠ lỗi" kèm "thiếu plugin.py":** thư mục chỉ có `plugin.yaml`. Thêm file mã vào.
- **Thẻ ghi "⚠ lỗi" kèm "manifest lỗi: ...":** `plugin.yaml` sai cú pháp YAML. Hay gặp nhất là mô tả có dấu hai chấm mà không bọc nháy.
- **Thẻ ghi "⚠ lỗi" kèm "thiếu hàm register(ctx)":** `plugin.py` chưa có hàm `register`, hoặc bạn đặt tên khác. Hàm phải tên đúng là `register` và nhận một tham số.
- **Thẻ ghi "⚠ lỗi" kèm tên một lỗi Python (ví dụ `ModuleNotFoundError`):** mã plugin dùng thư viện chưa cài trong môi trường Python của Javis. Cài thư viện đó vào đúng môi trường ảo Javis đang chạy, rồi khởi động lại.
- **Plugin đang chạy nhưng engine không thấy tool:** nhiều khả năng tên tool **trùng** với một tool đã có của MCP hoặc tool lõi. Javis không cho plugin chiếm chỗ tool lõi, nó bỏ qua tool trùng và ghi một dòng vào log server. Đổi tên tool trong `plugin.py` cho khác đi (đặt tiền tố riêng là cách chắc nhất). Các tên lõi không được dùng lại: `javis_connections`, `javis_read_file`, `javis_list_dir`, `javis_write_file`, `javis_use_skill`.
- **Tool trả về `ERROR: tool '<tên>' cần mức quyền cao hơn`:** lượt chạy đang bị hạn chế mức quyền. Nếu là việc định kỳ, nâng chế độ của việc đó (xem [Việc định kỳ & Nhắc hẹn](08-viec-dinh-ky.md)); nếu là plugin của bạn thì xem lại `min_mode` khai trong `register_tool`.
- **Tool trả về "Chưa kết nối ...":** plugin cần một kết nối mà bạn chưa đấu. Làm theo đúng câu hướng dẫn trong lỗi, thường là vào trang **Kết nối** (hoặc **Models** với plugin tạo ảnh).
- **Bấm Bật báo "không tìm thấy plugin":** danh sách trên màn hình đã cũ so với đĩa (bạn vừa xoá hoặc đổi tên thư mục). Tải lại trang.
- **Bấm Bật báo "ghi manifest lỗi":** Javis không ghi được vào `plugin.yaml`, thường do quyền thư mục hoặc file đang mở khoá bởi chương trình khác. Xem thêm [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md).

## Liên quan

- [Skills](06-skills.md) - khi cái bạn thiếu là tri thức cách làm chứ không phải mã chạy.
- [Kết nối & số liệu kinh doanh](09-mcp-va-so-lieu.md) - đấu nguồn dữ liệu ngoài; các plugin Meta Ads, Facebook Trang và Apify lấy token từ đây.
- [Models & engine](10-models-va-engine.md) - vì sao mọi engine đều gọi được tool của plugin.
- [Việc định kỳ & Nhắc hẹn](08-viec-dinh-ky.md) - ba mức quyền của việc chạy nền, và plugin `javis-schedule`.
- [Zalo Agent MCP](12-zalo.md) - Zalo nay dùng MCP upstream, không còn plugin riêng.
- [Cấu hình .env](16-cau-hinh-env.md) - cách đặt biến môi trường và khởi động lại.
- [Agents & Workflows](07-agents-va-workflows.md) - các loại năng lực khác của Javis.
