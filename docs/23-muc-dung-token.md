# Mức dùng: token & chi phí

***Tiếng Việt** · [English](en/23-usage-and-cost.md)*

Trang **Mức dùng** trả lời hai câu hỏi đi liền nhau: *bạn đã đốt bao nhiêu token* và *làm sao đốt ít đi*. Javis tự đo lấy con số này từ log thật trên máy, không phải xin từ nhà cung cấp, nên bạn thấy được cả phần mà Claude hay ChatGPT không bao giờ lộ ra: phần do chính Javis chạy nền tiêu tốn.

Ngay đầu trang là khối **Chế độ tiết kiệm token** với ba nút. Từ bản 0.24.7 nó nằm ở đây; trước đó là một trang riêng tên "Tiết kiệm" trong thanh bên. Gộp lại vì tách hai chỗ thì người dùng đọc hết hoá đơn mà không bao giờ thấy cái công tắc.

Trang này hướng dẫn chọn mức tiết kiệm, rồi đọc từng thẻ, từng đồ thị, từng bảng, và cách dùng nó để tìm chỗ đang ăn hạn mức của bạn.

## Tính năng này là gì

Javis nhìn thấy số token vào/ra trong **mọi** lượt trả lời, bất kể lượt đó chạy qua engine nào (Claude Code, ChatGPT/Codex, OpenRouter, OpenAI, Anthropic). Vì thế con số ở đây là con số đồng nhất, **không phụ thuộc nhà cung cấp có cho xem hạn mức hay không**.

Hai điều phải nhớ trước khi đọc bất cứ số nào:

- **Đây là lượng BẠN ĐÃ DÙNG, không phải hạn mức còn lại của gói thuê bao.** Đa số nhà cung cấp không cho lấy hạn mức qua API. Trang này đếm những gì đã đi qua, chứ không biết gói của bạn còn bao nhiêu. Ngoại lệ duy nhất là OpenRouter (xem mục dưới).
- **Chi phí trên trang là QUY ĐỔI, không phải tiền thật.** Với gói thuê bao Claude hay ChatGPT, con số đô la chỉ trả lời "nếu tính theo giá API thì việc này đáng bao nhiêu". Chỉ OpenRouter mới là tiền thật.

Trang cho bạn: bộ lọc 8 kỳ và 4 nhà cung cấp, các thẻ tổng kèm so kỳ trước, đồ thị token theo ngày, ba biểu đồ cột bóc tách (nguồn tiêu / hoạt động / nhà cung cấp), hai bảng xếp hạng (model và dự án), và một danh sách đề xuất tiết kiệm tự sinh.

## Mở ở đâu trong Javis

Mở dashboard (mặc định tại cổng 7777). Trên thanh điều hướng bên trái, bấm mở nhóm **Hệ thống** (nhóm này được ghim ở đáy thanh), rồi bấm mục **Mức dùng** (biểu tượng 📊).

Đầu trang hiện tiêu đề **Mức dùng** kèm dòng phụ "Token & chi phí theo ngày, theo nhà cung cấp".

## Chế độ tiết kiệm token (khối đầu trang)

Mỗi lần bạn chat, Javis phải gửi kèm một mớ thông tin nền cho model: nó là ai, có công cụ nào, nhớ gì về bạn, đã nói gì trước đó. Mớ đó tốn tiền và ăn vào hạn mức. Ba nút ở đây quyết định mớ đó to bao nhiêu.

- **Tắt** - chế độ Đầy đủ. Gửi mọi thứ, mỗi lượt. An toàn nhất, tốn nhất.
- **Tối ưu** - chỉ gửi phần liên quan tới câu vừa hỏi: bộ nhớ có chọn lọc, skill nạp khi cần.
- **Siêu tiết kiệm** - như Tối ưu, cộng thêm đường tắt cho câu hỏi đơn giản không cần tra cứu gì. **Đây là mặc định từ bản 0.24.7.**

Mỗi nút ghi sẵn nó tiết kiệm bao nhiêu phần trăm và còn bao nhiêu token mỗi lượt. Con số đó là **ước lượng đo trên chính bộ não và bộ nhớ của bạn**, không phải số quảng cáo, nên hai máy khác nhau sẽ thấy hai con số khác nhau.

Nếu bộ não bạn đang chạy không ăn được một mức nào đó, nút của mức ấy ghi thẳng *"không áp cho bộ não đang dùng"*. Ví dụ đường tắt của Siêu tiết kiệm chỉ chạy trên bộ não dùng API key, nên với gói thuê bao thì nó bằng đúng mức Tối ưu.

Khi đã có đủ lượt chạy ở cả hai chế độ trong 24 giờ, một khối số **đo thật** hiện ngay dưới ba nút: token mỗi lượt ở chế độ Đầy đủ, token mỗi lượt khi tiết kiệm, và phần trăm giảm được. Đây là số thật, không phải ước lượng.

**Đổi mức có hiệu lực ngay**, không cần khởi động lại. Thấy Javis trả lời tệ đi thì bấm **Tắt** là quay lại như cũ lập tức.

### Vì sao mặc định là Siêu tiết kiệm

Trước 0.24.7 mặc định là **Tắt**, và gần như không ai tự bật - nghĩa là đa số đang trả tiền cho chế độ đắt nhất mà không biết. Đo trên một brain mẫu: mức Tắt tốn khoảng 8.900 token cố định mỗi lượt, mức Siêu tiết kiệm khoảng 460.

Đây là mặc định an toàn được, không phải liều: mọi đường trong mức này đều **fail-closed**. Thiếu điều kiện thì lượt đó tự rơi về chế độ Đầy đủ chứ không trả lời sai.

Nếu bạn **đã từng tự bấm một mức**, Javis ghim lựa chọn đó lại và không bản cập nhật nào đổi nó nữa - kể cả khi bạn cố ý bấm **Tắt**. Dòng chữ dưới ba nút cho biết bạn đang ở mặc định hay ở lựa chọn của mình.

## Cách dùng (từng bước)

### Bước 1: Mở trang và chờ quét lần đầu

Vừa vào, trang hiện dòng "Đang dựng chỉ số token...". Lần mở đầu tiên Javis **quét lại log** rồi mới vẽ, nên có thể chậm vài giây nếu bạn đã dùng nhiều tháng. Những lần đổi bộ lọc sau đó thì không quét nữa, chỉ đọc lại từ chỉ mục nên rất nhanh.

Nếu trang báo "Không tải được số liệu token." thì server chưa trả được dữ liệu, xem mục Sự cố thường gặp.

### Bước 2: Chọn kỳ

Hàng đầu tiên là 8 nút bấm kỳ: **Hôm nay**, **Hôm qua**, **Tuần này**, **Tuần trước**, **Tháng này**, **Tháng trước**, **3 tháng**, **Năm nay**. Kỳ đang chọn được tô màu nhấn. Mặc định khi mở trang là **Tháng này**.

Mỗi kỳ tự so với kỳ tương đương liền trước, và kết quả so sánh hiện ngay dưới thẻ "Tổng token".

### Bước 3: Lọc theo nhà cung cấp

Ngay bên phải dãy nút kỳ là một cụm 4 nút liền nhau: **Tất cả** (mặc định), **Claude Code**, **ChatGPT**, **API**. Bấm để chỉ xem một nguồn.

Bộ lọc này ảnh hưởng tới các thẻ tổng, đồ thị và các bảng bóc tách. Riêng phần **Đề xuất** ở cuối trang luôn tính trên toàn bộ nhà cung cấp, không theo bộ lọc này.

### Bước 4: Đọc các thẻ tổng

Hàng thẻ ngay dưới bộ lọc:

| Thẻ | Con số | Dòng dưới |
|---|---|---|
| **Tổng token** | Tổng token trong kỳ (đã gồm token đọc-cache) | "▲ x%" hoặc "▼ x%" kèm chữ "vs kỳ trước"; chưa có số kỳ trước thì ghi "kỳ trước chưa có số" |
| **Token/ngày** | Trung bình mỗi ngày trong kỳ | "trung bình trong kỳ" |
| **Cache hit** | Tỷ lệ phần trăm token đầu vào là đọc lại cache | "tái dùng ngữ cảnh (cao = rẻ)" |
| **Phiên** | Số phiên có phát sinh token trong kỳ | "tb ... /phiên" - trung bình token mỗi phiên |
| **Chi phí quy đổi** | Tiền quy đổi theo bảng giá API | "nếu tính giá API" |
| **OpenRouter còn** | Số dư thật còn lại (chỉ hiện khi đã cắm key OpenRouter) | "tiền thật đã dùng $..." |

Lưu ý màu của mũi tên: **▲ (tăng) tô đỏ, ▼ (giảm) tô xanh**. Ở đây tăng là tin xấu chứ không phải tin tốt.

Về **Cache hit**: "Tổng token" gồm cả token đọc-cache nên nhìn rất lớn. Cache hit cao nghĩa là phần lớn con số khổng lồ đó chỉ là đọc lại ngữ cảnh cũ (rất rẻ), chứ không phải nạp mới. Nên đọc hai thẻ này cùng nhau.

### Bước 5: Xem đồ thị token theo ngày

Mục **Token theo ngày** vẽ mỗi ngày một cột. Cột được xếp chồng 3 màu theo nhà cung cấp, có chú thích ngay dưới:

- **Claude** - màu nhấn của giao diện
- **ChatGPT** - xanh lá
- **API** - xanh dương

Trục ngang ghi ngày trong tháng. Rê chuột lên một cột hiện chú thích dạng "2026-07-29: 12.3M token". Kỳ dài (3 tháng, Năm nay) thì đồ thị cuộn ngang.

### Bước 6: Tìm chỗ đang ngốn token

Phần dưới đồ thị là ba biểu đồ cột ngang, đây là chỗ quan trọng nhất của trang:

- **Nguồn tiêu (bạn vs Javis)** - hai dòng: "Bạn gõ tay" và "Javis (tự chạy)".
- **Hoạt động** - bốn dòng: "Chat", "Nền (loop/lịch)", "Subagent", "Thủ công".
- **Provider** - "Claude Code", "ChatGPT/Codex", "API (OpenRouter...)".

Ý nghĩa từng nhãn nằm ở mục [Nguồn tiêu và loại hoạt động](#nguồn-tiêu-và-loại-hoạt-động) bên dưới.

Kế đó là hai bảng xếp hạng, mỗi bảng hiện tối đa 8 dòng:

- **Model ngốn nhất**: cột Model, Token, Quy đổi. Tên model được rút gọn cho vừa (bỏ tiền tố `claude-` / `gpt-`, cắt bớt phần đuôi dài). Cột Quy đổi hiện "-" khi model đó không có trong bảng giá.
- **Dự án ngốn nhất**: cột Dự án, Token, Phiên. "Dự án" là tên brain nếu Javis nhận ra phiên đó thuộc brain nào, còn lại là tên thư mục làm việc.

### Bước 7: Đọc phần Đề xuất

Nếu số liệu chạm ngưỡng, Javis sinh các thẻ đề xuất ở cuối trang. Thẻ ⚠️ viền cam là việc nên làm, thẻ 💡 viền xanh là gợi ý. Chi tiết ngưỡng ở mục [Các đề xuất tiết kiệm](#các-đề-xuất-tiết-kiệm).

Không có thẻ nào nghĩa là mọi chỉ số đang trong ngưỡng bình thường, không phải lỗi.

## Bảng tra nhanh 8 kỳ

Mọi mốc ngày tính theo giờ Việt Nam (UTC+7).

| Nút | Kỳ đang xem | So với |
|---|---|---|
| **Hôm nay** | Hôm nay | Hôm qua |
| **Hôm qua** | Hôm qua | Hôm kia |
| **Tuần này** | Thứ Hai đến hôm nay | Cùng đoạn của tuần trước |
| **Tuần trước** | Thứ Hai đến Chủ nhật tuần trước | Tuần trước nữa |
| **Tháng này** | Mùng 1 đến hôm nay | Cùng số ngày đầu của tháng trước |
| **Tháng trước** | Trọn tháng trước | Trọn tháng trước nữa |
| **3 tháng** | 90 ngày gần nhất | 90 ngày liền trước đó |
| **Năm nay** | 1/1 đến hôm nay | 1/1 năm ngoái đến cùng ngày năm ngoái |

Cách so của "Tuần này" và "Tháng này" là cố ý: kỳ đang chạy dở chỉ so với **đúng đoạn tương ứng** của kỳ trước, chứ không so với cả kỳ trọn vẹn. Nếu không thì ngày mùng 3 nào cũng báo giảm 90%.

## Nguồn tiêu và loại hoạt động

Đây là chỗ để biết **cái gì đang ăn hạn mức của bạn**, và cũng là thứ mà bảng thống kê của nhà cung cấp không cho bạn thấy.

**Nguồn tiêu** chia hai:

| Nhãn | Nghĩa là gì |
|---|---|
| **Bạn gõ tay** | Phiên bạn tự mở `claude` trong terminal, không đi qua Javis |
| **Javis (tự chạy)** | Phiên do Javis khởi động qua Agent SDK: chat trên dashboard, chat qua Telegram, việc nền, workflow |

**Hoạt động** chia bốn:

| Nhãn | Nghĩa là gì |
|---|---|
| **Chat** | Lượt gắn với một phiên hội thoại có thật trong lịch sử của bạn |
| **Nền (loop/lịch)** | Lượt do Javis tự chạy mà không gắn phiên hội thoại nào: việc định kỳ, nhắc hẹn, việc Kanban, tiêu hoá nguồn, tự học |
| **Subagent** | Lượt do một agent con được engine gọi ra để làm việc phụ |
| **Thủ công** | Lượt của phiên bạn gõ tay ngoài Javis |

Cột **Nền (loop/lịch)** phình to là dấu hiệu rõ nhất rằng bạn đang có loop chạy quá dày. Xem lại chúng ở trang **Việc định kỳ** ([Việc định kỳ & Nhắc hẹn](08-viec-dinh-ky.md)) hoặc trang **Việc** ([Việc / Kanban](21-viec-kanban.md)).

Một hạn chế cần biết: **cách chia này chỉ chính xác với Claude Code.** Với ChatGPT/Codex, Javis chưa tách được nền khỏi chat nên mọi lượt đều rơi vào "Javis (tự chạy)" + "Chat". Nhánh API cũng vậy.

## Chi phí quy đổi và tiền thật

Cột **Chi phí quy đổi** và cột **Quy đổi** trong bảng model được tính từ một bảng giá cố định (USD trên mỗi triệu token) đi kèm app, tại `server/usage_pricing.json`. Bảng hiện có giá cho các dòng `claude-opus`, `claude-sonnet`, `claude-haiku`, `claude-fable`, `gpt-5`, `gpt-4o`. Model được khớp theo tiền tố dài nhất; **model không có trong bảng thì chi phí tính bằng 0** và hiện dấu "-".

Nghĩa là con số quy đổi luôn là ước lượng, và luôn thấp hơn thực tế nếu bạn dùng model chưa có trong bảng giá. Muốn chính xác hơn thì sửa file đó bằng tay rồi khởi động lại server.

**Số dư thật của OpenRouter** là thứ duy nhất trên trang này là tiền thật. Thẻ "OpenRouter còn" chỉ xuất hiện khi bạn đã lưu key OpenRouter ở trang **Models** (nhóm Kết nối). Javis hỏi thẳng OpenRouter số tín dụng đã nạp và đã dùng, rồi hiện phần còn lại kèm dòng "tiền thật đã dùng $...". Không cắm key thì không có thẻ này, và không có nhà cung cấp nào khác cho lấy số tương đương.

## Các đề xuất tiết kiệm

Danh sách này tự sinh từ chính số liệu của kỳ đang xem. Các ngưỡng đặt trong `server/usage_index.py`:

| Đề xuất | Xuất hiện khi | Mức |
|---|---|---|
| **Cache hit thấp (x%)** | Cache hit dưới 50%, và kỳ đủ lớn (từ 200.000 token đầu vào trở lên) | ⚠️ |
| **Hoạt động ngầm chiếm x% token** | Phần "Nền (loop/lịch)" chiếm từ 25% tổng token | ⚠️ |
| **Opus chiếm x% token** | Các model `claude-opus` chiếm từ 50% tổng token | 💡 |
| **Có phiên phình to (x token vào)** | Một phiên nạp từ 1 triệu token đầu vào | ⚠️ |
| **Token/ngày tăng x% so kỳ trước** | Token mỗi ngày của kỳ này gấp từ 1,5 lần kỳ trước | ⚠️ |

Mỗi thẻ kèm một dòng gợi ý hành động cụ thể, ví dụ đề xuất cache thấp khuyên dùng `/compact` hoặc chia phiên, đề xuất opus khuyên hạ model cho việc nhẹ. Ngưỡng 200.000 token cho cảnh báo cache là để trang không kêu ầm lên khi bạn mới dùng vài phút.

## Số liệu này lấy từ đâu

Javis không gọi API nào của nhà cung cấp để lấy thống kê. Nó **đọc lại log thô trên chính máy bạn** rồi dựng chỉ mục riêng:

| Nguồn | Ở đâu | Cho ra |
|---|---|---|
| Log Claude Code | `~/.claude/projects/**/*.jsonl` | Cột Claude, đủ cả cache, phân loại chat/nền/subagent |
| Log Codex | `~/.codex/sessions/**/rollout-*.jsonl` | Cột ChatGPT, mỗi file là một phiên |
| Nhật ký nội bộ | `usage-events.jsonl` trong thư mục state | Cột API, và là nguồn dự phòng cho Claude/ChatGPT |
| Kho phiên hội thoại | `conversations.db` trong thư mục state | Dùng để biết lượt nào là chat thật, lượt nào là chạy nền |

Kết quả gộp vào một cơ sở dữ liệu SQLite là `usage_index.db`, cũng trong thư mục state (đặt bằng biến `JAVIS_STATE_DIR`, xem [Cấu hình .env](16-cau-hinh-env.md)).

Việc quét là **quét tăng dần**: file nào không đổi kích thước và thời gian sửa thì bỏ qua hẳn. Vì thế lần quét đầu chậm còn các lần sau rất nhanh, kể cả khi bạn có hàng nghìn file log.

Nhánh API không có log thô nào để đọc, nên nó chỉ có số **từ lúc bạn nâng lên bản có tính năng này trở đi**. Claude và Codex thì có lịch sử ngược về tận lúc bạn bắt đầu dùng, vì log của chúng vốn đã nằm sẵn trên máy.

Nếu bản cài không đọc được log thô (điển hình là bản Docker trên VPS, nơi thư mục `~/.claude` của bạn không có trong container), Javis dựng số từ nhật ký nội bộ thay thế, nên trang vẫn có số chứ không còn báo 0 như trước. Ngày nào có cả hai nguồn thì log thô thắng, không bị đếm trùng. Dấu hiệu nhận biết: trong bảng "Dự án ngốn nhất", dòng tên `(events)` là dòng dựng từ nhật ký nội bộ, dòng `(api)` là lượt qua provider API.

## Bảng tra nhanh nút và trạng thái

| Bạn thấy | Ý nghĩa / thao tác |
|---|---|
| 8 nút kỳ (**Hôm nay** ... **Năm nay**) | Đổi kỳ xem; nút sáng màu là kỳ đang chọn |
| Cụm **Tất cả / Claude Code / ChatGPT / API** | Lọc theo nhà cung cấp |
| **↻ Làm mới** | Quét lại log rồi vẽ lại; trong lúc chạy nút đổi thành "Đang quét..." |
| "Đang dựng chỉ số token..." | Đang tải lần đầu |
| "Không tải được số liệu token." | Không gọi được server |
| "Chưa có dữ liệu." | Ô đó không có số trong kỳ đang chọn |
| "kỳ trước chưa có số" | Kỳ trước bằng 0 nên không tính được phần trăm thay đổi |
| ▲ đỏ / ▼ xanh | Tăng / giảm so kỳ trước |
| Thẻ ⚠️ viền cam | Đề xuất mức cảnh báo |
| Thẻ 💡 viền xanh | Đề xuất mức gợi ý |

## Mẹo

- Mở **Tháng này** trước để nhìn xu hướng, rồi mới bấm **Hôm nay** để soi ngày cụ thể. Đọc ngược lại dễ hoảng vì một ngày lẻ luôn trông bất thường.
- Nghi loop chạy quá dày thì lọc **Claude Code** rồi nhìn cột "Nền (loop/lịch)" trong mục Hoạt động. Đây là con số duy nhất nói thẳng cho bạn biết Javis đang tự tiêu bao nhiêu khi bạn không ngồi trước máy.
- Cache hit thấp mà tổng token cao thì vấn đề nằm ở độ dài phiên, không phải ở số lượt chat. Tách phiên ra là cách rẻ nhất để hạ.
- Bảng "Dự án ngốn nhất" là cách nhanh để biết brain nào đang tốn nhất, khi bạn dùng nhiều brain.
- Chỉ bấm **↻ Làm mới** khi bạn vừa chạy xong một việc lớn và muốn thấy nó ngay. Bình thường lần mở trang đã tự quét rồi.

## Sự cố thường gặp

- **Trang báo toàn số 0.** Thường là bản cài không đọc được log thô, hay gặp nhất trên Docker/VPS vì thư mục `~/.claude` và `~/.codex` của bạn không nằm trong container. Từ bản mới, Javis lấy nhật ký nội bộ làm nguồn dự phòng nên vẫn ra số, nhưng chỉ tính từ thời điểm bạn nâng cấp trở đi. Đã nâng cấp mà vẫn 0 thì nghĩa là chưa có lượt chat nào được ghi lại kể từ đó, hãy chat vài câu rồi bấm **↻ Làm mới**.
- **Số thấp hơn nhiều so với cảm nhận.** Kiểm tra bạn có đang lọc một nhà cung cấp không, và kiểm tra kỳ đang chọn. Ngoài ra phần "Bạn gõ tay" chỉ đếm được khi bạn chạy Claude Code trên **cùng máy** với Javis.
- **Cắm key Google Gemini nhưng cột API không nhúc nhích.** Lượt Gemini có được ghi vào nhật ký nội bộ, nhưng bộ dựng chỉ mục hiện chỉ nhận các nhà cung cấp OpenRouter, OpenAI và Anthropic vào cột API, nên phần Gemini chưa lên đồ thị này.
- **Không thấy thẻ "OpenRouter còn".** Thẻ chỉ hiện khi có key OpenRouter trong Cài đặt model và OpenRouter trả lời được. Vào trang **Models** (nhóm Kết nối) kiểm tra key, xem [Models & engine](10-models-va-engine.md).
- **Trang hiện bảng đơn giản kiểu "Hôm nay / Tổng tích luỹ" thay vì bộ lọc kỳ.** Đó là giao diện dự phòng, xuất hiện khi tệp giao diện mới chưa nạp được. Tải lại trang, xoá cache trình duyệt nếu cần.
- **Chi phí quy đổi hiện "-" cho model mình đang dùng.** Model đó chưa có trong bảng giá `server/usage_pricing.json`. Đây là bảng cập nhật tay, thêm dòng cho model của bạn rồi khởi động lại server.
- **Vừa nâng cấp Javis nhưng trang chưa có gì đổi.** Trang này có phần chạy ở backend, nên sau khi cập nhật cần **khởi động lại server** rồi mới tải lại trang.

## Liên quan

- [Models & engine](10-models-va-engine.md) - đổi model, cắm key OpenRouter, hiểu từng engine ghi số vào đâu.
- [Việc định kỳ & Nhắc hẹn](08-viec-dinh-ky.md) - nơi tắt bớt loop khi cột "Nền (loop/lịch)" phình to.
- [Việc / Kanban](21-viec-kanban.md) - việc chạy nền cũng tính vào phần "Javis (tự chạy)".
- [Cấu hình .env](16-cau-hinh-env.md) - biến `JAVIS_STATE_DIR` quyết định chỉ mục token nằm ở đâu.
- [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md) - các lỗi chung của dashboard.
