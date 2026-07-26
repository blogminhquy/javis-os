# Second Brain: bộ nhớ, Wiki, INGEST

Second Brain là "bộ não ngoài" của Javis: một thư mục chứa các ghi chú Markdown mà Javis đọc, tích luỹ và nhớ lâu dài. Nhờ nó, Javis không chỉ trả lời câu hỏi trong lúc chat mà còn nhớ về anh, về việc kinh doanh của anh, và ngày càng hiểu anh hơn theo thời gian.

Trang này hướng dẫn: hiểu Second Brain gồm những gì, cách tạo và chọn nhiều "não" khác nhau, cách để Javis nhớ (bộ nhớ dài hạn), và cách "tiêu hoá" tài liệu (INGEST) để biến file thô thành tri thức dùng lại được.

## Tính năng này là gì

Một Second Brain (gọi tắt là "brain" hay "vault") là một thư mục trên máy/VPS gồm các nhóm con:

| Lớp | Thư mục | Vai trò |
|---|---|---|
| Sources | `sources/` | Ghi chú thô: bài viết, ảnh chụp, file anh thả vào. Đây là "bản gốc". |
| Wiki | `wiki/` | Tri thức đã chưng cất: khái niệm, framework, quy trình, có liên kết chéo `[[...]]`. |
| Memory | `memory/` | Bộ nhớ sống: những gì Javis nhớ về anh và doanh nghiệp. |
| Agents / Workflows | `agents/`, `workflows/` | Lớp vận hành (xem [Agents & Workflows](07-agents-va-workflows.md)). |
| Attachments | `attachments/` | Ảnh và file đính kèm. |

Ba lớp cốt lõi của "second brain" theo đúng nghĩa là **Sources + Wiki + Memory**:

- **Sources** là nơi chứa nguyên liệu thô, chưa xử lý.
- **Wiki** là tri thức đã tinh lọc, nối với nhau thành mạng, chính là thứ Javis vẽ ra trong [Đồ thị tri thức 3D](03-do-thi-tri-thuc-3d.md).
- **Memory** là bộ nhớ dài hạn giúp Javis "nhớ anh".

Nguyên lý vận hành: **Sources -> (INGEST) -> Wiki**. Tri thức được tích luỹ dần, làm dày bộ não, không phải mỗi lần hỏi lại đi tìm từ đầu.

## Mở ở đâu trong Javis

Second Brain không nằm gọn trong một trang riêng mà rải ở vài chỗ trên dashboard (cổng mặc định `7777`):

1. **Thanh trên cùng, góc trái**: ô chọn brain (Select Brain) cùng 3 nút nhỏ ➕ 🗑 📁. Đây là nơi tạo, chọn, xoá brain.
2. **Cột trái màn hình chat**: mục **BỘ NHỚ DÀI HẠN** có nút **Học ngay từ hội thoại** và bộ đếm số ký ức.
3. **Ô nhập chat**: nơi thả file để INGEST và ra lệnh "nhớ điều này".
4. **Trang Tự cải thiện** (nav trái): có nút **LINT Wiki** để soát lỗi Wiki, và loại nhiệm vụ **Bộ não (Wiki)** cho vòng chạy nền.
5. **Trang Cài đặt** (nav trái): nhóm **Giao diện & Brain** để chuẩn hoá thư mục.

## Đa-brain: nhiều bộ não trong một Javis

Anh có thể nuôi nhiều brain tách biệt, ví dụ một brain cho công việc kinh doanh, một brain cho học tập cá nhân. Mỗi brain là một second brain độc lập: sources, wiki, bộ nhớ, agents đều riêng.

Ô chọn brain nằm ở góc trái thanh trên cùng. Bên cạnh nó có 3 nút:

| Nút | Nhãn (di chuột để xem) | Việc nó làm |
|---|---|---|
| ➕ | Tạo brain mới trong thư mục brains | Tạo một second brain mới |
| 🗑 | Xoá brain đang chọn (xác nhận gõ đúng tên) | Xoá vĩnh viễn brain đang chọn |
| 📁 | Chọn brain từ folder ngoài bất kỳ | Trỏ tới một thư mục ghi chú `.md` sẵn có trên máy |

Brain khởi đầu tên **Brain Default**, không xoá được (đây là "não gốc").

### Chọn brain đang làm việc

1. Bấm vào ô chọn brain ở góc trái thanh trên.
2. Chọn tên brain muốn dùng. Mỗi dòng hiển thị dạng `🧠 Tên brain`.
3. Toàn bộ Javis (chat, đồ thị, bộ nhớ, agents) lập tức chuyển sang brain đó. Không cần tải lại trang.

### Tạo brain mới

1. Bấm nút ➕ ở cạnh ô chọn brain.
2. Nhập **Tên brain mới** vào ô hiện ra, rồi xác nhận.
3. Javis tạo một thư mục con mới kèm sẵn cấu trúc chuẩn (sources, wiki, memory, agents, workflows, attachments) và chọn ngay brain vừa tạo.

Tên brain sẽ bị bỏ các ký tự đặc biệt (`\ / : * ? " < > |`) và cắt còn tối đa 60 ký tự cho an toàn.

### Chọn một thư mục ghi chú sẵn có (folder ngoài)

Nếu anh đã có sẵn một kho ghi chú `.md` ở đâu đó trên máy (ví dụ vault Obsidian):

1. Bấm nút 📁.
2. Chọn đúng thư mục chứa các file `.md`.
3. Javis dùng thư mục đó làm brain. Lưu ý: folder ngoài chỉ được "trỏ tới", nút 🗑 sẽ không xoá nó khỏi ổ đĩa (chỉ bỏ khỏi danh sách).

### Xoá một brain

Đây là thao tác không thể hoàn tác, toàn bộ tri thức trong brain đó (sources, wiki, agents, workflows, bộ nhớ) sẽ mất vĩnh viễn.

1. Chọn brain muốn xoá trong ô chọn brain.
2. Bấm nút 🗑.
3. Hộp thoại cảnh báo hiện ra, yêu cầu **gõ CHÍNH XÁC tên brain** để xác nhận.
4. Nếu gõ đúng, brain bị xoá và Javis quay về Brain Default. Gõ sai tên thì thao tác bị huỷ.

Không thể xoá **Brain Default**. Cũng không xoá được folder ngoài (nút 📁) theo cách này.

### Chuẩn hoá cấu trúc một brain

Nếu một brain có cấu trúc cũ (ví dụ ghi chú nằm trong `Javis/agents`, `Memory` viết hoa), anh có thể gom về dạng phẳng đồng nhất:

1. Vào **Cài đặt** ở nav trái.
2. Mở nhóm **Giao diện & Brain**.
3. Bấm **Chuẩn hóa brain đang chọn**, rồi xác nhận.

Thao tác này an toàn: chỉ di chuyển khi thư mục đích chưa tồn tại, không ghi đè. Nó gộp `Javis/agents` về `agents/`, `Javis/workflows` về `workflows/`, `Memory` về `memory/`.

## Bộ nhớ dài hạn: làm Javis "nhớ anh"

Bộ nhớ sống nằm ở `memory/` trong brain đang chọn, gồm:

- `memory/MEMORY.md`: chỉ mục, mỗi ký ức một dòng. File này được nạp sẵn vào đầu mỗi câu hỏi, nên Javis luôn "nhớ nền" về anh.
- `memory/facts/*.md`: chi tiết từng ký ức, mỗi file là một sự thật.
- `memory/conversations/YYYY-MM-DD.md`: log hội thoại thô, làm nguyên liệu để học.

Javis phân 4 loại ký ức: thông tin về anh (`user`), cách anh thích làm việc (`preference`), sự thật về kinh doanh (`business`), và quyết định đã chốt (`decision`).

### Xem số ký ức đã học

Ở cột trái màn hình chat, mục **BỘ NHỚ DÀI HẠN** có một con số nhỏ. Đó là số ký ức (số file trong `memory/facts/`) của brain đang chọn. Đổi brain thì con số đổi theo.

Mô tả ngay dưới ghi rõ: "Ký ức lưu ngay trong vault đang chọn - đổi máy chỉ cần trỏ lại vault là Javis nhớ như cũ." Nghĩa là bộ nhớ đi theo thư mục, không kẹt trong máy nào.

### Ép Javis ghi nhớ một điều

Trong lúc chat, chỉ cần nói rõ:

- "nhớ điều này"
- "ghi nhớ ..."

Khi anh dùng các cụm đó, Javis bắt buộc tạo ngay một ký ức mới: viết một file trong `memory/facts/` và thêm một dòng vào `MEMORY.md`. Ví dụ: "Nhớ điều này: shop tôi nghỉ bán Chủ Nhật" sẽ được lưu thành một sự thật `business`.

Javis chỉ ghi những điều bền vững, đáng nhớ. Nó bỏ qua chuyện nhất thời và không nhân bản ký ức đã có (trùng thì cập nhật file cũ).

### Học từ hội thoại (vòng hợp nhất / rewire)

Đây là vòng lặp giúp Javis thông minh dần: đọc lại hội thoại gần đây, rút ra sự thật mới, gộp trùng lặp, bỏ ký ức đã sai, và **đúc kết khái niệm tái dùng được vào Wiki**.

Có hai cách kích hoạt:

**Cách 1 - Bấm tay:**

1. Ở cột trái, mục **BỘ NHỚ DÀI HẠN**, bấm nút **🧠 Học ngay từ hội thoại**.
2. Nút đổi thành "🧠 Đang học..." trong lúc Javis đọc lại hội thoại.
3. Khi xong, kết quả tóm tắt hiện ra ngay dưới nút (học thêm mấy ký ức, đúc kết mấy khái niệm Wiki). Con số ký ức cũng tự cập nhật.

**Cách 2 - Tự học nền:**

Ngay dưới đó có ô tích **Tự học sau mỗi 6 lượt**. Khi bật (mặc định), cứ sau 6 lượt hội thoại Javis tự chạy một vòng học nền, không làm gián đoạn anh. Bỏ tích nếu muốn tắt.

Điểm quan trọng của vòng này: Javis phân biệt rõ hai thứ. Sự thật về anh và doanh nghiệp vào `memory/facts/`. Còn khái niệm, framework, quy trình dùng lại được thì chưng cất thành trang Wiki (có `[[wikilink]]`). Cái nào ra cái nấy, nhờ vậy đồ thị tri thức dày lên chứ không lẫn lộn với ghi chú cá nhân.

## INGEST: tiêu hoá tài liệu thành tri thức

INGEST là quy trình biến một file thô (bài viết, ảnh chụp, ghi chú) thành nguồn trong `sources/`, rồi từ đó chưng cất lên Wiki. Kết quả: Javis tóm tắt, rút insight, viết Wiki và có thể gợi ý task.

### Cách dùng (từng bước)

1. Mở màn hình chat.
2. Thả file vào ô nhập chat (kéo thả), hoặc bấm nút đính kèm để chọn file. Ảnh và file văn bản đều được. File được tải lên và chờ ở khu tạm.
3. Mặc định, Javis **chỉ đọc file rồi trả lời**, chưa lưu đi đâu. Nếu anh chỉ cần tóm tắt nhanh thì gõ câu hỏi bình thường.
4. Muốn Javis lưu và tiêu hoá, hãy nói rõ trong tin nhắn một trong các cụm: **"lưu vào source"**, **"ingest"**, hoặc **"ghi vào second brain"**.
5. Khi đó Javis sẽ:
   - Với file văn bản: đọc toàn bộ, tạo một file `.md` sạch trong `sources/` kèm frontmatter nguồn.
   - Với ảnh: đọc hiểu và mô tả nội dung ảnh bằng tiếng Việt, tạo `.md` trong `sources/`, chuyển ảnh gốc vào `attachments/` rồi nhúng lại.
6. Từ nguồn đó, Javis rút insight và cập nhật Wiki, đồng thời có thể đề xuất task nếu tài liệu mở ra việc cần làm.

### Ép Javis xử lý mẻ nguồn theo lịch

Nếu anh dồn nhiều nguồn chưa xử lý, có thể để Javis tự làm nền:

1. Vào **Tự cải thiện** ở nav trái.
2. Ở **Loại nhiệm vụ**, chọn **Bộ não (Wiki)**. Mô tả của nó là: "Ingest source mới, trả lời open-question, sửa lỗi Wiki".
3. Đặt chu kỳ (phút) và bấm **Lưu cấu hình**, hoặc bấm **Chạy ngay** để chạy một vòng liền.

Chi tiết cấu hình vòng nền xem [Tự cải thiện](08-tu-cai-thien.md).

## Soát lỗi Wiki (LINT)

Khi Wiki đã dày, anh nên soát định kỳ. LINT chỉ **đọc và liệt kê vấn đề**, không tự sửa, nên rất an toàn.

1. Vào **Tự cải thiện** ở nav trái.
2. Bấm nút **🩺 LINT Wiki**.
3. Nút đổi thành "Đang quét Wiki..." rồi trả về một danh sách check theo nhóm.

LINT tìm 8 loại vấn đề: mâu thuẫn giữa các trang, thông tin cũ chưa cập nhật (stale claim), trang không có ai trỏ tới (orphan page), khái niệm thiếu trang riêng (missing page), liên kết `[[...]]` gãy (broken wikilink), trang trùng lặp, vùng kiến thức mỏng (gap), và câu hỏi mở chưa được lấp (open-question). Đọc danh sách rồi tự quyết định sửa cái nào, đừng để Javis sửa hàng loạt cùng lúc.

## Mẹo

- **Tách brain theo mục đích.** Một brain cho kinh doanh, một brain cho cá nhân sẽ giúp đồ thị tri thức và bộ nhớ gọn, đỡ nhiễu.
- **Nói "nhớ điều này" cho những gì bền vững.** Ví dụ ngách sản phẩm, kênh bán chính, quyết định giá. Đừng ghi chuyện nhất thời (hôm nay bận, tin nhắn vừa gửi), Javis vốn đã bỏ qua loại này.
- **Muốn tiêu hoá tài liệu thì phải nói rõ.** Chỉ thả file không đủ để lưu, phải kèm cụm "lưu vào source" hoặc "ingest". Nếu chỉ hỏi bình thường, Javis đọc xong là thôi.
- **Bộ nhớ đi theo thư mục.** Đổi máy hoặc chuyển VPS, chỉ cần trỏ Javis về đúng thư mục brain là mọi ký ức và Wiki còn nguyên.
- **Đồng bộ bằng git.** Vì brain là thư mục file `.md`, anh có thể sao lưu và đồng bộ nhiều máy bằng git một cách tự nhiên.
- **Xem tri thức trực quan** ở [Đồ thị tri thức 3D](03-do-thi-tri-thuc-3d.md): mỗi nguồn và trang Wiki là một điểm, liên kết `[[...]]` là các đường nối.

## Sự cố thường gặp

- **Bấm Học từ hội thoại báo lỗi "Claude CLI chưa cài".** Bộ nhớ và INGEST cần Claude Code CLI làm bộ não. Kiểm tra cài đặt CLI, xem [Bắt đầu & thiết lập](01-bat-dau-thiet-lap.md) và [Khắc phục sự cố](17-khac-phuc-su-co.md).
- **Số ký ức vẫn là 0 dù đã chat nhiều.** Ký ức chỉ được ghi khi có thông tin bền vững đáng nhớ, hoặc khi anh nói "nhớ điều này", hoặc sau khi chạy Học từ hội thoại. Chat phiếm không sinh ký ức.
- **Thả file mà không thấy vào Sources.** Đúng như thiết kế: mặc định chỉ đọc. Phải gõ kèm "lưu vào source" / "ingest" trong tin nhắn thì Javis mới tạo file `.md` trong `sources/`.
- **Xoá nhầm brain.** Không khôi phục được. Vì thế hộp thoại bắt gõ đúng tên brain. Nếu chỉ muốn tạm ngừng dùng một kho ghi chú, hãy trỏ folder ngoài bằng nút 📁 thay vì xoá.
- **Brain báo cấu trúc chưa chuẩn.** Vào Cài đặt, nhóm Giao diện & Brain, bấm **Chuẩn hóa brain đang chọn** để Javis gom lại các thư mục.
- **Ký ức không theo sang máy mới.** Kiểm tra anh đã trỏ đúng thư mục brain chứa `memory/`. Bộ nhớ nằm trong thư mục, không nằm trong tài khoản.
