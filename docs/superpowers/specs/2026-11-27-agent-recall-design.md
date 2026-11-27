# Trí nhớ theo nhu cầu cho cộng sự (Agent Recall)

Ngày: 2026-11-27. Trạng thái: chủ duyệt cùng ngày (trần 8.000 ký tự, bật sẵn học lúc ghi, làm cả A B C); đã làm,
xem mục 11.

Chủ repo 27/11/2026: "phần tự học về các file tài liệu ở trong agent nó quá nhiều, mình cần một bộ tìm kiếm để
không nhồi tất cả ngữ cảnh vào, mà tìm cho phù hợp ... thiết kế có tính đột phá và có tính scale, không ảnh hưởng
khi lượng data memory lớn".

## 1. Vấn đề, đo trên code hiện tại

| Nguồn trí nhớ của một cộng sự | Cách nạp hôm nay | Hậu quả |
|---|---|---|
| `memory/agents/<slug>/MEMORY.md` | Nạp NGUYÊN file mỗi lượt (`_agent_memory`, `_agent_sysprompt` trong `server/main.py`), không trần | LCX 52,8 KB: khoảng 15-18 nghìn token mỗi lượt, kể cả câu hỏi "có hay không"; Antigravity cắt đuôi, mất câu hỏi (PR #1898) |
| Kho bài học (`agent_lessons`) | 12 bài MỚI NHẤT mỗi phạm vi, kho giữ tối đa 40 | Bài học cũ mà đúng chủ đề bị bỏ, bài mới mà lạc đề vẫn được nạp |
| Tài liệu đính kèm | Chỉ liệt kê tên, file ghim thì nạp nguyên (có trần) | Model phải tự mở file, mà thường không mở |

So sánh: bộ nhớ chính của Javis đã có trần 20.000 ký tự và một bộ tìm kiếm (`server/memory_index.py`). Cộng sự
chưa dùng bộ nào. Bộ tìm kiếm hiện có cũng chưa scale: đổi một file là dựng lại TOÀN BỘ chỉ mục (kể cả đồ thị liên
kết), và bước khớp từ khoá quét cả bảng bằng `LIKE '%từ%'`.

## 2. Nguyên tắc

1. **Chi phí mỗi lượt không tăng theo dung lượng trí nhớ.** Bộ nhớ 50 KB hay 50 MB thì phần nạp vào lượt vẫn dưới
   một trần cố định (mặc định khoảng 16.000 ký tự).
2. **Luật của chủ không bao giờ phụ thuộc may rủi tìm kiếm.** Câu hỏi không nhắc tới Zalo thì luật "nhắn Zalo không
   dùng markdown" vẫn phải có mặt.
3. **Markdown vẫn là gốc.** Chỉ mục là bản phái sinh, xoá đi dựng lại được, không bao giờ mất ký ức.
4. **Không hồi quy.** Cộng sự có bộ nhớ nhỏ chạy y như hôm nay.
5. **Chạy trên cả 11 bộ não**, không cần mua API embedding, không thêm thư viện nặng vào image Docker.

## 3. Kiến trúc: bốn tầng, mở dần theo nhu cầu

```
Tầng 0  Hiến pháp      luôn nạp, có trần ~8.000 ký tự      luật chủ dặn, vai, mục chủ đánh dấu "luôn nạp"
Tầng 1  Bản đồ         luôn nạp, có trần ~1.500 ký tự      mục lục: có những mục nào, bao nhiêu ghi nhớ, tài liệu gì
Tầng 2  Gợi nhớ        mỗi lượt, có trần ~6.000 ký tự      các đoạn khớp nhất với câu hỏi và vài lượt gần đây
Tầng 3  Tự tra         khi cần, tool `javis_recall`         model tự tìm thêm khi thấy thiếu
```

**Tầng 0, Hiến pháp.** Phần mở đầu của MEMORY.md (trước mục `##` đầu tiên), mục `## Luật chủ dặn`, và mục nào chủ
đánh dấu luôn nạp (tiêu đề kết thúc bằng `(luôn nạp)`, hoặc dòng `always_on:` ở frontmatter). Vượt trần thì KHÔNG cắt
im lặng: phần vượt xuống Tầng 2 với độ ưu tiên cao nhất, Bản đồ ghi rõ "còn N luật chưa hiện, tra trước khi làm", và
trang Cộng sự hiện một cảnh báo "luật đã quá dài, nên gộp lại".

**Tầng 1, Bản đồ.** Model không thể tìm thứ nó không biết là có (bài học từ `fit_memory_index`, bản 0.222.0). Bản đồ
liệt kê tên từng mục kèm số đoạn, tên tài liệu, số bài học theo phạm vi. Nhiều quá thì gom theo cấp tiêu đề cao hơn,
luôn dưới trần.

**Tầng 2, Gợi nhớ tự động.** Truy vấn = tin nhắn mới nhất + 2 lượt gần nhất + tên vai. Lấy các đoạn đạt ngưỡng điểm,
đóng gói tới trần ký tự. Không đoạn nào đạt thì không nạp gì: câu "em có tạo được ảnh không" chỉ tốn Tầng 0 và 1.

Vị trí đặt khối này là điểm mấu chốt cho cả tiền lẫn độ đúng:
- **Chat riêng nhiều lượt:** đặt ở ĐẦU tin nhắn của lượt (cùng chỗ `_turn_facts_header`), không vào system prompt.
  System prompt giữ nguyên giữa các lượt nên prompt cache vẫn trúng, và mạch Antigravity hay Claude Code đã nối
  (chỉ gửi tin mới, không gửi lại system prompt) vẫn nhận được gợi nhớ mới mỗi lượt.
- **Lượt chạy một lần** (bước quy trình, việc Kanban, lượt nhóm): nội dung việc chính là truy vấn, khối gợi nhớ ghép
  thẳng vào prompt của lượt đó.

**Tầng 3, Tự tra.** Tool `javis_recall` (op=search, op=read) cho mọi engine qua MCP Hub, chỉ đọc, chỉ trong trí nhớ
của đúng cộng sự đang chạy và đúng phạm vi bài học (chat riêng không đọc bài học của nhóm). Đây cũng là lưới an toàn
cho đường nào chưa có Tầng 2.

## 4. Chỉ mục: tăng dần, mỗi cộng sự một vùng

- **Nguồn:** MEMORY.md (mọi mục, kể cả Hiến pháp để tool tra được), kho bài học `agent_lessons`, tài liệu đính kèm
  dạng chữ (md, txt, csv, json; pdf và docx khi đã có bản chữ trong brain).
- **Cắt đoạn** theo tiêu đề rồi theo đoạn văn, 600-1.200 ký tự, giữ số dòng để trích nguồn `file#Lx-Ly` và đọc lại
  bản gốc khi cần (cơ chế `_read_detail` đã có).
- **Lưu:** SQLite FTS5 `unicode61 remove_diacritics 2` (gõ có dấu hay không dấu đều khớp), file
  `STATE_DIR/agent_recall.db`. Vùng của từng cộng sự là một cột được ĐÁNH CHỈ MỤC trong FTS (`scope:<agent> AND ...`),
  không lọc sau.
- **Tăng dần:** mỗi nguồn có hash nội dung. Lượt chạy chỉ so `mtime + size` (rẻ), nguồn nào đổi mới cắt lại và
  chỉ thay đúng các đoạn của nguồn đó. Ghi một bài học = chèn một bản ghi.

Đo trên máy dev 27/11/2026, kịch bản xấu nhất (chữ ngẫu nhiên, từ nào cũng khớp gần như mọi đoạn):

| Việc | Kết quả |
|---|---|
| Nạp 50.000 đoạn (khoảng 30 MB chữ, 20 cộng sự) | 2,8 giây, một lần |
| Một lần tìm trong vùng một cộng sự | 6-15 mili giây |
| Thêm một ghi nhớ | khoảng 1 mili giây |
| Lọc vùng SAU khi tìm (cách làm sai) | 40-60 mili giây |

Tức trí nhớ to gấp ngàn lần LCX hôm nay vẫn tìm trong vài phần trăm giây.

## 5. Xếp hạng: lai, không cần embedding

Điểm = BM25 (FTS5)
+ khớp tiêu đề mục
+ khớp thực thể (tên sản phẩm, mã đơn, số điện thoại, chữ trong `[[...]]` và trong dấu `` ` ``)
+ trọng số nguồn: luật chủ > bài học chủ duyệt > tài liệu > bài học tự rút
+ độ mới (chỉ cho bài học).

Sau đó: đa dạng hoá (không lấy quá 2 đoạn cùng một mục), ngưỡng tin cậy, đóng gói theo trần ký tự.

## 6. Phần đột phá: học lúc ghi, không phải lúc đọc

Điểm yếu của tìm theo từ khoá là đồng nghĩa: hỏi "giá sỉ" mà ghi nhớ viết "giá đại lý" thì trượt. Cách phổ biến là
embedding, nhưng nó cần API trả tiền theo mỗi lần tìm, hoặc một model cục bộ nặng hàng trăm MB.

Thiết kế này đảo chiều: **mỗi khi một đoạn mới hoặc vừa đổi**, một lượt model nền (model rẻ chủ chọn, mặc định model
phụ của brain) viết thêm cho đoạn đó:
- 3-5 câu hỏi mà đoạn đó trả lời được,
- các cách gọi khác của khái niệm chính ("giá sỉ, giá đại lý, giá buôn"),
- một dòng tóm tắt để Bản đồ dùng.

Phần này được đánh chỉ mục cùng đoạn gốc (chỉ để tìm, không nạp cho model). Kết quả:
- Tìm "theo nghĩa" mà mỗi lần tìm vẫn chỉ là FTS5, miễn phí và vài mili giây.
- Chi phí trả MỘT lần lúc ghi, lưu theo hash đoạn: đoạn không đổi không bao giờ tốn lần hai.
- Có trần số lượt mỗi ngày, bật tắt được; tắt hay hết trần thì vẫn chạy bằng từ khoá như thường.

Hai vòng tự cải thiện đi kèm (giai đoạn sau):
- **Tín hiệu dùng:** đoạn được gợi mà model thực sự dựa vào (trích nguồn, hoặc gọi `javis_recall op=read`) được cộng
  điểm. Đoạn nhiều tháng không ai cần thì được đề xuất gộp hoặc dọn, chủ duyệt mới làm.
- **Hiến pháp tự gọn:** Tầng 0 vượt trần thì Javis soạn một bản gộp luật (bỏ trùng, bỏ luật đã có luật mới thay), đi
  qua `javis_improve` có sao lưu và hoàn tác, chủ bấm duyệt.

## 7. Áp dụng ở đâu

Một điểm chặn duy nhất cho Tầng 0, 1, 3: `_agent_sysprompt` trong `server/main.py`, dùng chung cho chat riêng
(dashboard, Telegram, CLI, gọi thoại), bước quy trình, việc Kanban và lượt nhóm. Tầng 2 thêm ở: lượt chat riêng trên
dashboard (mọi engine), lượt Telegram và CLI của cộng sự, bước quy trình, việc Kanban, lượt nhóm.

## 8. An toàn và không hồi quy

- Tổng trí nhớ dưới `JAVIS_AGENT_RECALL_MIN` (mặc định 12.000 ký tự): nạp nguyên như hôm nay.
- Chỉ mục hỏng hay lỗi bất kỳ: rơi về cách nạp cũ cho lượt đó, ghi log. Không bao giờ để lượt chat chết vì bộ tìm kiếm.
- `JAVIS_AGENT_RECALL=0` tắt toàn bộ.
- Mỗi lượt ghi một biên nhận: bao nhiêu đoạn được gợi, nạp bao nhiêu ký tự, tiết kiệm bao nhiêu so với nạp nguyên.

## 9. Lộ trình

| PR | Nội dung | Ai thấy gì |
|---|---|---|
| A, lõi | `server/agent_recall.py` (chỉ mục tăng dần, tìm, đóng gói), Tầng 0-1 trong `_agent_sysprompt`, Tầng 2 cho chat riêng và lượt chạy một lần, tool `javis_recall`, test | LCX hết bị cắt, lượt chat nhẹ đi khoảng 3-4 lần, trả lời nhanh hơn |
| B, học lúc ghi | Làm giàu đoạn bằng model nền, biên nhận hiện ở "Tài liệu & Đã học" | Hỏi bằng từ khác vẫn nhớ ra |
| C, mở rộng | Javis Core chuyển sang cùng bộ máy (thay `memory_index` dựng lại toàn bộ), tín hiệu dùng, Hiến pháp tự gọn | Trí nhớ chính cũng scale như cộng sự |

Test bắt buộc của PR A:
- Luật trong `## Luật chủ dặn` có mặt ở MỌI lượt, kể cả câu hỏi không liên quan.
- Trí nhớ 5 MB: prompt dưới trần, một lượt tìm dưới 50 mili giây.
- Sửa một mục chỉ cắt lại đúng nguồn đó.
- Bộ nhớ dưới ngưỡng: prompt giống hệt bản cũ từng byte.
- Chat riêng không đọc được bài học phạm vi nhóm qua `javis_recall`.

## 10. Chủ cần chốt

1. Trần Tầng 0 là 8.000 ký tự, vượt thì cảnh báo và đẩy phần vượt xuống tìm kiếm ưu tiên cao: đồng ý không?
2. PR B gọi model nền lúc ghi (tốn một ít quota của model phụ): bật mặc định hay để chủ tự bật?
3. Có làm luôn PR C cho Javis Core sau khi A và B ổn không?

## 11. Đã làm (2026-11-27)

Chủ chốt: 1 đồng ý, 2 bật sẵn, 3 làm cả A, B, C.

| Phần | Ở đâu | Ghi chú |
|---|---|---|
| Chỉ mục tăng dần, tìm, Hiến pháp, Bản đồ | `server/agent_recall.py` | Đo: trí nhớ 3,2 MB dựng lần đầu 2 giây, prompt 1.545 ký tự, mỗi lần tìm 1-40 mili giây, lượt sau không đổi 9 mili giây |
| Tầng 0-1 trong prompt cộng sự | `_agent_sysprompt` (`server/main.py`) | Bộ nhớ dưới ngưỡng: prompt giống hệt bản cũ (có test) |
| Tầng 2 | `run_turn` (chat riêng mọi engine), `_cli_turn` (Telegram, CLI), hai đường chạy bước quy trình, lượt nhóm (`team_runner.recall_block`) | Khối nằm ở đầu tin nhắn, `chat_recall.strip_block` gỡ nó trước khi lưu lịch sử |
| Tầng 3 | tool `javis_recall` (`agent_recall.build`, gắn ở `mcp_hub`) | Luôn hiện (hat_nhan), chỉ đọc, không cho bot khách |
| Học lúc ghi (PR B) | `AgentRecall.enrich_pending`, `_agent_recall_enrich_soon` | Model nền hạng nhẹ (`learn-agent-recall`), trần 60 lượt/ngày (`JAVIS_AGENT_RECALL_ENRICH_DAILY`), tắt bằng `agent_recall.enrich: false` hoặc `JAVIS_AGENT_RECALL_ENRICH=0` |
| Biên nhận (PR B) | tab "Đã học" của cộng sự, log `[agent recall]` mỗi lượt | `GET /agents/<slug>/learned` trả thêm `memory` |
| Javis Core (PR C) | `server/memory_index.py` v6 | Dựng lại tăng dần (5.000 ghi nhớ: thêm một cái từ 2,8 giây xuống 0,3 giây), FTS giữ chữ đã chuẩn hoá, bước từ khoá hỏi FTS thay vì quét LIKE |
| Tín hiệu dùng (PR C) | bảng `usage` của `agent_recall` | Đoạn được `javis_recall` mở lại được cộng điểm |
| Cảnh báo Hiến pháp vượt trần (PR C) | tab "Đã học" | Hiện cảnh báo; việc gộp luật làm bằng cách nhờ chính trợ lý trong chat (đi qua `javis_improve`, có hoàn tác) |

Khác với bản thiết kế, nói thẳng:
- Kho bài học `agent_lessons` chưa vào chỉ mục: nó đã có trần riêng (12 bài mỗi phạm vi), không phải nguồn phình.
- Javis Core giữ bộ chỉ mục riêng (nâng cấp tại chỗ) thay vì chuyển hẳn sang `agent_recall`: hai thứ khác nhau về đơn vị
  (file ghi nhớ so với đoạn trong một file lớn), gộp là một việc riêng.
- Việc nền chạy dưới vai một cộng sự (nhắc hẹn, loop) chưa có Tầng 2 tự động; nó vẫn có Tầng 0, 1 và tool `javis_recall`.
- Chưa có nút "gộp luật giúp tôi" một chạm; mới có cảnh báo.
