# Second Brain: bộ nhớ, Wiki, INGEST

***Tiếng Việt** · [English](en/13-second-brain.md)*

Second Brain là "bộ não ngoài" của Javis: một thư mục chứa các ghi chú Markdown mà Javis đọc, tích luỹ và nhớ lâu dài. Nhờ nó, Javis không chỉ trả lời câu hỏi trong lúc chat mà còn nhớ về bạn, về việc kinh doanh của bạn, và ngày càng hiểu bạn hơn theo thời gian.

Trang này hướng dẫn: hiểu Second Brain gồm những gì, cách tạo và chọn nhiều "não" khác nhau, cách để Javis nhớ (bộ nhớ dài hạn), và cách "tiêu hoá" tài liệu (INGEST) để biến file thô thành tri thức dùng lại được.

## Tính năng này là gì

Một Second Brain (gọi tắt là "brain" hay "vault") là một thư mục trên máy/VPS gồm các nhóm con:

| Lớp | Thư mục | Vai trò |
|---|---|---|
| Sources | `sources/` | Ghi chú thô: bài viết, ảnh chụp, file bạn thả vào. Đây là "bản gốc". |
| Wiki | `wiki/` | Tri thức đã chưng cất: khái niệm, framework, quy trình, có liên kết chéo `[[...]]`. |
| Memory | `memory/` | Bộ nhớ sống: những gì Javis nhớ về bạn và doanh nghiệp. |
| Agents / Workflows | `agents/`, `workflows/` | Lớp vận hành (xem [Agents & Workflows](07-agents-va-workflows.md)). |
| Skills | `skills/` | Bản chuẩn của kỹ năng, mỗi skill một thư mục `skills/<slug>/SKILL.md`. Javis tự mirror sang `.claude/skills` cho Claude Code nạp native (xem [Skills](06-skills.md)). |
| Tầng vận hành | `Javis/` | Thứ do chat sinh ra: việc lặp `Javis/loops/<slug>.md`, luật từng cuộc chat Zalo `Javis/zalo/<slug>.md`, nhắc hẹn `Javis/reminders.json`, và chỉ mục năng lực `Javis/index.md` (tự sinh từ file, đừng sửa tay). |
| Sổ bullet journal | `00 - Dashboard/`, `01 - Daily Log/`, `02 - Weekly Log/`... | Nơi ghi chép và task hằng ngày; khối Dataview kéo dữ liệu từ đây (xem [Task & Dataview trong note](19-task-va-dataview.md)). |
| Vùng cache | `attachments/`, `inbox/` | Ảnh và file đính kèm; `inbox/telegram/` là nơi file gửi qua Telegram rơi xuống. **Hai thư mục này là cache, tự hết hạn** - đọc mục riêng bên dưới trước khi để tài liệu quý ở đây. |

Ba lớp cốt lõi của "second brain" theo đúng nghĩa là **Sources + Wiki + Memory**:

- **Sources** là nơi chứa nguyên liệu thô, chưa xử lý.
- **Wiki** là tri thức đã tinh lọc, nối với nhau thành mạng, chính là thứ Javis vẽ ra trong [Đồ thị tri thức](03-do-thi-tri-thuc.md).
- **Memory** là bộ nhớ dài hạn giúp Javis "nhớ bạn".

Nguyên lý vận hành: **Sources -> (INGEST) -> Wiki**. Tri thức được tích luỹ dần, làm dày bộ não, không phải mỗi lần hỏi lại đi tìm từ đầu.

## Brain nằm ở đâu trên đĩa

Mọi brain nằm chung trong một thư mục cha tên `brains/`, mỗi thư mục con là một brain. Bản chạy trên máy thì đó là `brains/` ngay trong thư mục Javis; bản Docker/VPS mặc định là `/brains` (mount riêng để sao lưu được). Đổi chỗ bằng biến môi trường `BRAINS_DIR`, xem [Cấu hình .env](16-cau-hinh-env.md).

Brain khởi đầu tên **Brain Default**, nằm ở `brains/Brain Default`.

Biến `BRAIN_PATH` chỉ còn là biến cũ từ thời Javis có một brain duy nhất, giữ lại để chuyển dữ liệu sang cấu trúc mới. Đừng dùng nó để trỏ brain đang làm việc.

## Mở ở đâu trong Javis

Second Brain không nằm gọn trong một trang riêng mà rải ở vài chỗ trên dashboard (cổng mặc định `7777`). Rail điều hướng bên trái gom các trang thành nhóm, phải mở nhóm mới thấy mục con:

1. **Thanh trên cùng, góc trái**: ô chọn brain cùng 3 nút nhỏ ➕ 🗑 📁. Đây là nơi tạo, chọn, xoá brain.
2. **Khung chat** (màn **Javis** hoặc trang **Trò chuyện**, nhóm **Trợ lý**): nơi thả file để INGEST và ra lệnh "nhớ điều này".
3. **Trang Tự học** (nhóm **Bộ não**): số ký ức đã học, nút học ngay, Curator dọn dẹp, và khối đồng bộ brain lên GitHub. Xem [Tự học](22-tu-hoc.md).
4. **Trang Tệp tin** (nhóm **Bộ não**): duyệt, sửa, tải lên/tải về mọi file trong brain. Xem [Quản lý tệp tin](05-quan-ly-tep-tin.md).
5. **Trang Việc định kỳ** (nhóm **Việc**): đặt việc lặp để Javis tự tiêu hoá nguồn theo lịch. Xem [Việc định kỳ & Nhắc hẹn](08-viec-dinh-ky.md).
6. **Trang Cài đặt** (nhóm **Hệ thống**): nhóm **Giao diện & Brain**, mục **Cấu trúc brain**, để chuẩn hoá thư mục.

## Đa-brain: nhiều bộ não trong một Javis

Bạn có thể nuôi nhiều brain tách biệt, ví dụ một brain cho công việc kinh doanh, một brain cho học tập cá nhân. Mỗi brain là một second brain độc lập: sources, wiki, bộ nhớ, skills, agents đều riêng.

Ô chọn brain nằm ở góc trái thanh trên cùng. Bên cạnh nó có 3 nút:

| Nút | Nhãn (di chuột để xem) | Việc nó làm |
|---|---|---|
| ➕ | Tạo brain mới trong thư mục brains | Tạo một second brain mới |
| 🗑 | Xoá brain đang chọn (xác nhận gõ đúng tên) | Đưa brain đang chọn vào thùng rác (giữ 30 ngày) |
| 📁 | Chọn brain từ folder ngoài bất kỳ | Trỏ tới một thư mục ghi chú `.md` sẵn có trên máy |

Brain khởi đầu tên **Brain Default**, không xoá được (đây là "não gốc").

### Chọn brain đang làm việc

1. Bấm vào ô chọn brain ở góc trái thanh trên.
2. Chọn tên brain muốn dùng. Mỗi dòng hiển thị dạng `🧠 Tên brain · 128`, con số phía sau là số note `.md` Javis đếm được trong brain đó. Nếu số đó chạm trần đếm (5000) sẽ có thêm dấu `+`, nghĩa là "ít nhất ngần này" chứ không phải tổng thật.
3. Toàn bộ Javis (chat, đồ thị, bộ nhớ, agents) lập tức chuyển sang brain đó. Không cần tải lại trang.

### Tạo brain mới

1. Bấm nút ➕ ở cạnh ô chọn brain.
2. Nhập tên vào ô hiện ra (dòng hỏi là "Tên brain mới:"), rồi xác nhận.
3. Javis tạo một thư mục con mới trong `brains/` kèm sẵn cấu trúc chuẩn (sources, agents, workflows, memory, skills, wiki, attachments và bộ sổ bullet journal) rồi chọn ngay brain vừa tạo.

Tên brain sẽ bị bỏ các ký tự đặc biệt (`: * ? " < > |`), bỏ dấu chấm ở hai đầu, và cắt còn tối đa 60 ký tự cho an toàn.

### Chọn một thư mục ghi chú sẵn có (folder ngoài)

Nếu bạn đã có sẵn một kho ghi chú `.md` ở đâu đó trên máy (ví dụ vault Obsidian):

1. Bấm nút 📁.
2. Chọn đúng thư mục chứa các file `.md`.
3. Javis dùng thư mục đó làm brain. Lưu ý: folder ngoài chỉ được "trỏ tới", nút 🗑 sẽ không xoá nó khỏi ổ đĩa (chỉ bỏ khỏi danh sách).

Danh sách folder ngoài được Javis tự dọn: entry nào trùng đường dẫn với một brain thật, hoặc trỏ tới thư mục đã bị xoá khỏi ổ đĩa, sẽ tự biến khỏi menu. Trường hợp không kiểm chứng được (server chớp lỗi) thì entry được giữ nguyên, không xoá nhầm.

### Xoá một brain (vào thùng rác, giữ 30 ngày)

Xoá brain **không phải là mất vĩnh viễn**. Javis chuyển cả thư mục vào thùng rác cục bộ rồi mới dọn hẳn sau 30 ngày. Đồng thời Javis ghi một "giấy báo tử" để việc xoá lan sang mọi máy đang đồng bộ chung, và nếu bạn đã bật sao lưu GitHub thì lệnh xoá được đẩy lên remote ngay chứ không chờ chu kỳ.

1. Chọn brain muốn xoá trong ô chọn brain.
2. Bấm nút 🗑.
3. Hộp thoại hiện ra ghi rõ: "Não này sẽ được chuyển vào THÙNG RÁC (giữ 30 ngày rồi tự xoá hẳn), và việc xoá sẽ ĐỒNG BỘ sang mọi máy khác." Nó yêu cầu **gõ CHÍNH XÁC tên brain** để xác nhận.
4. Gõ đúng thì brain được đưa vào thùng rác và Javis quay về Brain Default, kèm thông báo "Đã xoá brain ... (đưa vào thùng rác 30 ngày, đồng bộ xoá sang các máy khác)". Gõ sai tên thì hiện "Tên không khớp - đã huỷ xoá".

Thùng rác nằm ở thư mục `brain-trash` trong thư mục state của Javis (`JAVIS_STATE_DIR`; bản chạy máy là thư mục `server/`, bản Docker là volume state). Mỗi lần xoá tạo một thư mục con dạng `Tên brain__20260729-153012`. Việc dọn thùng rác quá 30 ngày chạy kèm mỗi lượt đồng bộ brain lên GitHub.

Không thể xoá **Brain Default**, bấm 🗑 lúc đang chọn nó sẽ báo "Không thể xoá Brain mặc định (não khởi đầu)."

Với folder ngoài (📁), nút 🗑 làm việc khác hẳn: nó hỏi 'Bỏ folder ngoài "..." khỏi danh sách? Chỉ gỡ khỏi menu chọn não, KHÔNG xoá dữ liệu trên ổ đĩa' rồi chỉ gỡ entry khỏi menu. Dữ liệu trên đĩa còn nguyên.

### Chuẩn hoá cấu trúc một brain

Nếu một brain có cấu trúc cũ (ví dụ ghi chú nằm trong `Javis/agents`, `Memory` viết hoa, skill nằm trong `.claude/skills`), bạn có thể gom về dạng phẳng đồng nhất:

1. Vào **Cài đặt** (nhóm **Hệ thống** trên rail).
2. Mở nhóm **Giao diện & Brain**, kéo tới mục **Cấu trúc brain**.
3. Bấm **Chuẩn hóa brain đang chọn**, rồi xác nhận hộp thoại: "Chuẩn hóa cấu trúc brain đang chọn? (Di chuyển Javis/agents→agents, Javis/workflows→workflows, Memory→memory. Có git backup.)"

Thao tác này an toàn: chỉ di chuyển khi thư mục đích chưa tồn tại, không ghi đè. Nó gộp `Javis/agents` về `agents/`, `Javis/workflows` về `workflows/`, `Memory` về `memory/`, và dời skill cũ ở `.claude/skills` sang `skills/` (kể cả nhánh skill đang tắt, để skill bạn đã tắt không bị bật lại).

## `attachments/` và `inbox/` là vùng cache, không phải kho lưu trữ

Đây là luật dễ làm mất dữ liệu nhất nếu không biết trước. Từ bản 0.9.247, hai thư mục này được Javis coi là **vùng cache**: nguyên liệu đi qua, không phải tri thức.

- File trong hai thư mục đó quá **30 ngày** sẽ tự bị dọn. Nếu tổng dung lượng vượt trần **300MB**, Javis dọn từ cũ tới mới cho tới khi xuống dưới trần.
- Riêng ghi chú `.md` lỡ nằm trong hai thư mục đó thì được chừa ra, không bị dọn.
- Javis quét dọn mỗi 6 tiếng. Thư mục stage tạm (nơi file bạn vừa dán vào khung chat rơi xuống) có hạn riêng, ngắn hơn: **3 ngày**.
- Hai thư mục này **nằm ngoài git của brain**, nên chúng không đi theo bản sao lưu GitHub và không phình lịch sử repo.
- Ảnh cũ đã hết hạn khi hiện lại trong hội thoại sẽ thành một ô xám viền đứt ghi **"Ảnh đã hết hạn"** thay vì biểu tượng ảnh vỡ.
- Muốn tắt hẳn việc tự dọn, đặt `enabled: false` ở khoá `media` trong `settings.json`. Ngưỡng ngày và dung lượng cũng chỉnh ở đó.

Kết luận thực dụng: tài liệu bạn muốn giữ lâu dài thì chuyển sang `sources/` hoặc `wiki/`, đừng để nằm trong `attachments/` hay `inbox/`. Chi tiết ở [Quản lý tệp tin](05-quan-ly-tep-tin.md).

## Bộ nhớ dài hạn: làm Javis "nhớ bạn"

Bộ nhớ sống nằm ở `memory/` trong brain đang chọn, gồm:

- `memory/MEMORY.md`: chỉ mục, mỗi ký ức một dòng. File này được nạp sẵn vào đầu mỗi câu hỏi, nên Javis luôn "nhớ nền" về bạn.
- `memory/facts/*.md`: chi tiết từng ký ức, mỗi file là một sự thật.
- `memory/conversations/YYYY-MM-DD.md`: log hội thoại thô, làm nguyên liệu để học.

Javis phân 4 loại ký ức: thông tin về bạn (`user`), cách bạn thích làm việc (`preference`), sự thật về kinh doanh (`business`), và quyết định đã chốt (`decision`).

### Chỉ mục MEMORY.md có trần nạp vào ngữ cảnh

Vì `MEMORY.md` được nạp vào **mọi** lượt chat, nó có trần khoảng **20.000 ký tự** (đổi bằng biến môi trường `JAVIS_MEMORY_INDEX_MAX`). Brain dày lên vượt trần thì Javis hạ dần theo bậc, ưu tiên giữ đủ số ký ức:

1. Rút mô tả mỗi dòng còn 100 ký tự, rồi 60 ký tự.
2. Chỉ giữ tiêu đề và đường dẫn file, bỏ mô tả.
3. Cùng lắm mới bỏ bớt dòng, và khi đó Javis ghi rõ còn bao nhiêu ký ức chưa liệt kê kèm lời chỉ đường đọc tiếp trong `Memory/facts/`.

Nghĩa là ký ức không mất, chỉ là chỉ mục hiển thị gọn lại; chi tiết đầy đủ vẫn nằm trong `memory/facts/` và Javis đọc được bất cứ lúc nào.

### Log hội thoại được che secret trước khi ghi

Trước khi ghi vào `memory/conversations/`, Javis tự che (mask) những thứ trông giống bí mật mà bạn lỡ dán vào chat: khoá API (`sk-`, `xai-`, `gsk_`, `hf_`, `tvly-`), token GitHub (`ghp_`, `gho_`, `github_pat_`), khoá Google (`AIza`), JWT, token bot Telegram, header `Authorization`, và mật khẩu trong chuỗi kết nối cơ sở dữ liệu. Chúng bị thay bằng dạng rút gọn kiểu `sk-abc...wxyz` hoặc `***`.

Ngoài ra mỗi tin nhắn dài hơn 4.000 ký tự bị cắt bớt phần giữa (giữ 2.800 ký tự đầu và 1.000 ký tự cuối) kèm dòng ghi rõ đã cắt bao nhiêu, để log không phình.

Hai điểm nữa đáng biết:

- Hội thoại qua **Telegram** cũng được ghi vào `memory/conversations/` giống chat web, và cũng vào vòng tự học. Xem [Kênh Telegram](11-telegram.md).
- Thư mục `memory/conversations/` nằm trong `.gitignore` của brain, nên log thô **không** lên bản sao lưu GitHub. Git chỉ version tri thức đã chưng cất: `facts/`, `wiki/`, `skills/`, `MEMORY.md`.

### Xem số ký ức đã học

Số ký ức nằm ở dòng **Chỉ số** trên trang **Tự học** (nhóm **Bộ não**), dạng `Chỉ số · Ký ức: 87 · Wiki: 42 · MEMORY.md: 18363B ...`. Con số "Ký ức" chính là số file trong `memory/facts/` của brain đang chọn; đổi brain thì con số đổi theo.

Widget "BỘ NHỚ DÀI HẠN" ở cột chat ngày trước đã được gỡ, mọi thứ liên quan tới học và bộ nhớ nay gom về trang Tự học.

### Ép Javis ghi nhớ một điều

Trong lúc chat, chỉ cần nói rõ:

- "nhớ điều này"
- "ghi nhớ ..."

Khi bạn dùng các cụm đó, Javis bắt buộc tạo ngay một ký ức mới: viết một file trong `memory/facts/` và thêm một dòng vào `MEMORY.md`. Ví dụ: "Nhớ điều này: shop tôi nghỉ bán Chủ Nhật" sẽ được lưu thành một sự thật `business`.

Javis chỉ ghi những điều bền vững, đáng nhớ. Nó bỏ qua chuyện nhất thời và không nhân bản ký ức đã có (trùng thì cập nhật file cũ).

### Học từ hội thoại (vòng hợp nhất)

Đây là vòng lặp giúp Javis thông minh dần: đọc lại hội thoại gần đây, rút ra sự thật mới, gộp trùng lặp, bỏ ký ức đã sai, và **đúc kết khái niệm tái dùng được vào Wiki**.

Vòng này nay chạy tự động ở tầng server sau mỗi lượt chat (có độ trễ chống dồn dập), bằng một tiến trình học chỉ-đọc và cô lập; người ghi file là code tin cậy chứ không phải AI. Mặc định bật sẵn.

Điểm quan trọng của vòng này: Javis phân biệt rõ hai thứ. Sự thật về bạn và doanh nghiệp vào `memory/facts/`. Còn khái niệm, framework, quy trình dùng lại được thì chưng cất thành trang Wiki (có `[[wikilink]]`). Cái nào ra cái nấy, nhờ vậy đồ thị tri thức dày lên chứ không lẫn lộn với ghi chú cá nhân.

Bật/tắt, chọn chế độ ghi, chọn học cái gì, bấm học ngay, xem "Javis đã tự học gì" và hoàn tác một lần học: tất cả ở trang **Tự học**. Xem [Tự học](22-tu-hoc.md).

## INGEST: tiêu hoá tài liệu thành tri thức

INGEST là quy trình biến một file thô (bài viết, ảnh chụp, ghi chú) thành nguồn trong `sources/`, rồi từ đó chưng cất lên Wiki. Kết quả: Javis tóm tắt, rút insight, viết Wiki và có thể gợi ý task.

### Cách dùng (từng bước)

1. Mở khung chat (màn **Javis** hoặc trang **Trò chuyện**).
2. Thả file vào ô nhập chat (kéo thả, vùng thả ghi "📎 Thả file vào đây → lưu vào Sources"), hoặc bấm nút đính kèm hình cái ghim giấy cạnh ô nhập (tooltip "Đính kèm file (ảnh, text, tài liệu) → lưu vào Sources"). Ảnh và file văn bản đều được. File được tải lên và chờ ở khu tạm.
3. Mặc định, Javis **chỉ đọc file rồi trả lời**, chưa lưu đi đâu. Nếu bạn chỉ cần tóm tắt nhanh thì gõ câu hỏi bình thường.
4. Muốn Javis lưu và tiêu hoá, hãy nói rõ trong tin nhắn một trong các cụm: **"lưu vào source"**, **"ingest"**, hoặc **"ghi vào second brain"**.
5. Khi đó Javis sẽ:
   - Với file văn bản: đọc toàn bộ, tạo một file `.md` sạch trong `sources/` kèm frontmatter nguồn.
   - Với ảnh: đọc hiểu và mô tả nội dung ảnh bằng tiếng Việt, tạo `.md` trong `sources/`, chuyển ảnh gốc vào `attachments/` rồi nhúng lại.
6. Từ nguồn đó, Javis rút insight và cập nhật Wiki, đồng thời có thể đề xuất task nếu tài liệu mở ra việc cần làm.

Nhớ luật vùng cache ở trên: ảnh gốc trong `attachments/` sẽ hết hạn sau 30 ngày, còn file `.md` trong `sources/` thì ở lại vĩnh viễn. Đó chính là lý do phải ingest chứ không chỉ thả file rồi để đó.

### Để Javis xử lý mẻ nguồn theo lịch

Nếu bạn dồn nhiều nguồn chưa xử lý, có thể giao cho Javis một **việc lặp** chạy nền:

1. Vào **Việc định kỳ** (nhóm **Việc** trên rail).
2. Bấm **+ Thêm việc**.
3. Ở **Loại việc**, giữ **🔁 Việc lặp**.
4. Đặt **Tên** (ví dụ "Tiêu hoá nguồn mới").
5. Điền ô **Mô tả nhiệm vụ (mỗi vòng Javis làm đúng việc này)**, ví dụ: "Mỗi vòng đọc 1 source chưa xử lý trong sources rồi đề xuất Wiki page nên tạo".
6. Chọn **Chế độ**: **Đề xuất (chỉ đọc)** để Javis chỉ gợi ý, hoặc **Tự làm (an toàn)** để nó được ghi file nháp trong brain.
7. Đặt **Chu kỳ (phút, tối thiểu 5)**, chọn **Brain (nơi lưu việc)**, rồi bấm **💾 Lưu**.

Chi tiết từng chế độ, cách bật/tắt, xem nhật ký và mẹo an toàn: [Việc định kỳ & Nhắc hẹn](08-viec-dinh-ky.md).

## Soát lỗi Wiki (LINT)

Khi Wiki đã dày, bạn nên soát định kỳ. LINT chỉ **đọc và liệt kê vấn đề**, không tự sửa, nên rất an toàn.

Nút "LINT Wiki" riêng lẻ ngày trước không còn nữa. LINT nay chạy bên trong **Curator** ở trang **Tự học** (nhóm **Bộ não**), với mô tả đúng chữ trên giao diện: "Dọn index, LINT Wiki (chỉ đề xuất), nén MEMORY.md. Không xoá."

1. Vào **Tự học** ở nhóm **Bộ não** trên rail.
2. Bấm **🧹 Curator ngay** để chạy một lượt liền. Nút đổi thành "Đang dọn...".
3. Hoặc bấm nút trạng thái ở mục **Curator (bảo trì định kỳ)** cho nó chuyển từ "○ Tắt" sang "● Bật", rồi bấm **💾 Lưu cấu hình** để Javis tự chạy theo chu kỳ (mặc định Curator đang tắt, chu kỳ khi bật là 24 giờ).

Kết quả không sửa gì cả, chỉ đổ xuống khối **Nhật ký học** dưới dạng "Wiki LINT (đề xuất, chưa sửa)". Nó tìm: trang trùng lặp, trang không ai trỏ tới (orphan), liên kết `[[...]]` gãy, mâu thuẫn chưa giải, và vùng kiến thức mỏng (gap). Đọc danh sách rồi tự quyết định sửa cái nào, đừng để Javis sửa hàng loạt cùng lúc.

## Bảng tra nhanh nút và trạng thái

| Bạn muốn | Vào đâu | Bấm gì |
|---|---|---|
| Đổi brain đang làm việc | Thanh trên cùng, góc trái | Ô chọn brain (`🧠 Tên brain · số note`) |
| Tạo brain mới | Thanh trên cùng, góc trái | ➕ |
| Xoá brain (vào thùng rác 30 ngày) | Thanh trên cùng, góc trái | 🗑, rồi gõ đúng tên brain |
| Trỏ tới vault Obsidian sẵn có | Thanh trên cùng, góc trái | 📁 |
| Gỡ folder ngoài khỏi menu | Chọn folder ngoài rồi bấm | 🗑 (không đụng ổ đĩa) |
| Xem số ký ức, số trang Wiki | Nhóm Bộ não → Tự học | Đọc dòng **Chỉ số** |
| Ép học một lượt ngay | Nhóm Bộ não → Tự học | **▶ Học ngay** |
| Soát lỗi Wiki | Nhóm Bộ não → Tự học | **🧹 Curator ngay** |
| Hoàn tác lần học gần nhất | Nhóm Bộ não → Tự học | **↶ Hoàn tác lần học gần nhất** |
| Sao lưu brain lên GitHub | Nhóm Bộ não → Tự học | Khối **⇅ Đồng bộ brain với GitHub (2 chiều)** |
| Duyệt/sửa file trong brain | Nhóm Bộ não → Tệp tin | Cây thư mục bên trái |
| Giao việc lặp tiêu hoá nguồn | Nhóm Việc → Việc định kỳ | **+ Thêm việc** |
| Chuẩn hoá thư mục brain | Nhóm Hệ thống → Cài đặt | **Chuẩn hóa brain đang chọn** |

## Mẹo

- **Tách brain theo mục đích.** Một brain cho kinh doanh, một brain cho cá nhân sẽ giúp đồ thị tri thức và bộ nhớ gọn, đỡ nhiễu.
- **Nói "nhớ điều này" cho những gì bền vững.** Ví dụ ngách sản phẩm, kênh bán chính, quyết định giá. Đừng ghi chuyện nhất thời (hôm nay bận, tin nhắn vừa gửi), Javis vốn đã bỏ qua loại này.
- **Muốn tiêu hoá tài liệu thì phải nói rõ.** Chỉ thả file không đủ để lưu, phải kèm cụm "lưu vào source" hoặc "ingest". Nếu chỉ hỏi bình thường, Javis đọc xong là thôi.
- **Bộ nhớ đi theo thư mục.** Đổi máy hoặc chuyển VPS, chỉ cần trỏ Javis về đúng thư mục brain là mọi ký ức và Wiki còn nguyên.
- **Đừng tự dựng git tay để đồng bộ.** Javis đã có sẵn khối **⇅ Đồng bộ brain với GitHub (2 chiều)** trên trang Tự học: đẩy toàn bộ thư mục brains lên một repo riêng tư và kéo thay đổi từ máy khác về. Hướng dẫn từng bước ở [Sao lưu brain lên GitHub](18-sao-luu-github.md).
- **Xem tri thức trực quan** ở [Đồ thị tri thức](03-do-thi-tri-thuc.md): mỗi nguồn và trang Wiki là một điểm, liên kết `[[...]]` là các đường nối.

## Sự cố thường gặp

- **Không tìm thấy mục "BỘ NHỚ DÀI HẠN" hay nút "Học ngay từ hội thoại" ở cột chat.** Widget đó đã được gỡ. Mọi thứ về học và bộ nhớ nay ở trang **Tự học** (nhóm **Bộ não**): số ký ức ở dòng **Chỉ số**, học tay bằng nút **▶ Học ngay**.
- **Số ký ức vẫn là 0 dù đã chat nhiều.** Ký ức chỉ được ghi khi có thông tin bền vững đáng nhớ, hoặc khi bạn nói "nhớ điều này", hoặc sau khi chạy một lượt học. Chat phiếm không sinh ký ức. Kiểm tra thêm ở trang Tự học xem tự học có đang bật và chế độ ghi có phải **Tự ghi** không.
- **Thả file mà không thấy vào Sources.** Đúng như thiết kế: mặc định chỉ đọc. Phải gõ kèm "lưu vào source" / "ingest" trong tin nhắn thì Javis mới tạo file `.md` trong `sources/`.
- **Ảnh cũ trong hội thoại thành ô xám "Ảnh đã hết hạn".** Đúng như thiết kế: `attachments/` là vùng cache, ảnh quá 30 ngày bị dọn. Nội dung ảnh đã được rút thành `.md` trong `sources/` lúc ingest thì vẫn còn.
- **Xoá nhầm brain.** Không mất ngay: thư mục nằm trong `brain-trash` ở thư mục state của Javis, tên dạng `Tên brain__20260729-153012`, giữ 30 ngày. Cách lấy lại an toàn: bấm ➕ tạo lại brain **đúng tên cũ** (thao tác này gỡ giấy báo tử để brain không bị xoá lại khi đồng bộ), rồi chép nội dung từ thùng rác vào thư mục đó.
- **Brain báo cấu trúc chưa chuẩn.** Vào Cài đặt, nhóm Giao diện & Brain, mục Cấu trúc brain, bấm **Chuẩn hóa brain đang chọn** để Javis gom lại các thư mục.
- **Ký ức không theo sang máy mới.** Kiểm tra bạn đã trỏ đúng thư mục brain chứa `memory/`. Bộ nhớ nằm trong thư mục, không nằm trong tài khoản. Muốn hai máy tự khớp nhau thì bật đồng bộ GitHub, xem [Sao lưu brain lên GitHub](18-sao-luu-github.md).
- **Sao lưu GitHub xong không thấy log hội thoại và ảnh.** Đúng như thiết kế: `memory/conversations/`, `attachments/` và `inbox/` đều nằm ngoài git của brain. Bản sao lưu chỉ giữ tri thức đã chưng cất.

## Liên quan

- [Tự học](22-tu-hoc.md) - bật/tắt tự học, chế độ ghi, Curator, hoàn tác một lần học.
- [Quản lý tệp tin](05-quan-ly-tep-tin.md) - duyệt và sửa trực tiếp file trong brain, chi tiết vùng cache.
- [Sao lưu brain lên GitHub](18-sao-luu-github.md) - đồng bộ hai chiều mọi brain giữa các máy.
- [Đồ thị tri thức](03-do-thi-tri-thuc.md) - nhìn Sources và Wiki dưới dạng mạng lưới.
- [Skills](06-skills.md) - kỹ năng nằm trong `skills/` của brain.
- [Agents & Workflows](07-agents-va-workflows.md) - lớp vận hành trong `agents/` và `workflows/`.
- [Việc định kỳ & Nhắc hẹn](08-viec-dinh-ky.md) - giao việc lặp cho Javis tiêu hoá nguồn theo lịch.
- [Task & Dataview trong note](19-task-va-dataview.md) - bộ sổ bullet journal trong brain.
- [Cấu hình .env](16-cau-hinh-env.md) - biến `BRAINS_DIR`, `JAVIS_STATE_DIR`, `JAVIS_MEMORY_INDEX_MAX`.
