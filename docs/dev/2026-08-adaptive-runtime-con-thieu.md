# Còn thiếu gì để đạt mục đích gốc

Đi cùng `2026-08-adaptive-context-runtime-spec.md` (xây cái gì) và
`2026-08-adaptive-runtime-trien-khai.md` (đưa lên bằng cách nào).

Tài liệu này soi lại 12 phase dưới góc nhìn **mục đích gốc**, chứ không phải dưới góc nhìn
spec. Mục đích gốc không phải hiệu năng trừu tượng, mà rất cụ thể: gói Groq on_demand miễn phí
với `llama-3.3-70b-versatile` cho 12.000 token mỗi phút, còn một lượt Javis gửi đi 21.446
token, nên bị chặn ngay trước khi kịp trả lời.

## 1. Cấu thành 21.446 token, đo lại hôm nay

| Khối | Lúc chẩn đoán | Hôm nay | Có phase nào chạm tới chưa |
|---|---|---|---|
| `CLAUDE.md` làm system prompt | 21.479 ký tự | 21.479, y nguyên | Có, Phase 8 |
| `Memory/MEMORY.md` | 18.723 ký tự | trần 20.000 | Có, `memory_canary` |
| 30 skill + context động | ~5.400 ký tự | trần theo `SKILL_LIST_MAX` | Có, `lazy_skill_canary` |
| **26 schema MCP/tool** | **17.161 ký tự** | vẫn nguyên | **Chưa. Xem mục 3.1** |

## 2. Phần kiến trúc đã làm được thật

Đây là tin tốt, và cần nói rõ để khỏi làm lại:

- **Thay system prompt bằng capsule biên dịch.** `build_adaptive_source_prompt` cố ý **không**
  bọc `CLAUDE.md`. Khi `context_sources` bật, prompt lõi là `CORE_CONTRACT` của Context
  Compiler. Đo thật: **724 ký tự (~207 token) thay cho 26.505 ký tự (~7.573 token), giảm 97%**
  riêng khối này.
- **TPM có thật, không phải chỗ để trống.** `context_runtime.py:1031` có admission cửa sổ
  trượt 60 giây, atomic, fail-closed khi không biết hạn mức. Cả 5 đường canary đều truyền
  `rolling_tpm` xuống Context Compiler, và compiler đưa nó vào công thức ngân sách cùng
  `context_window` và `output_reserve`.
- **Evidence Store** để không gửi lại JSON kết quả tool qua mỗi vòng.
- **Model Router theo bước**, lọc cứng theo capability, cửa sổ ngữ cảnh, hạn chót, chi phí.

Nói cách khác: **kiến trúc giải được bài toán Groq. Nó chỉ đang tắt.**

## 3. Những chỗ thật sự còn thiếu

### 3.1 Schema tool chưa bao giờ vào tầng lazy (lỗ lớn nhất)

Đây là việc chính chủ đã chỉ ra ngay trong đoạn chat gốc, và **12 phase không đụng tới**.

`mcp_hub._apply_lazy` chỉ giấu tool đến từ connector MCP:

```python
pool = [t for t in tools_spec if (route.get(t["fn"]) or {}).get("conn")]
# Builtins + plugin (entry 'call' không 'conn') LUÔN hiện trực tiếp
```

Cộng thêm `lazy_threshold: 40` mặc định, mà máy đang có 26 tool, nên **lazy chưa từng kích
hoạt lần nào**. Toàn bộ 17.161 ký tự schema đi thẳng vào mọi request, cho mọi model.

Đây là khối lớn thứ hai sau `CLAUDE.md`, và quan trọng hơn cả: **sửa nó có tác dụng ngay trên
đường legacy đang chạy hôm nay, không cần bật canary nào.** Mọi thứ khác trong 12 phase đều
phải chờ rollout mới có tác dụng. Riêng cái này thì không.

### 3.2 Chưa ai khai hạn mức Groq, nên mọi lớp bảo vệ đều fail-closed thành vô dụng

`quota_profiles` mặc định là `[]`. Fail-closed nghĩa là thiếu profile thì rơi về legacy.

Hệ quả trớ trêu: cỗ máy dựng ra để cứu Groq, khi gặp đúng tình huống Groq, sẽ **không làm gì
cả** vì nó không biết Groq bị giới hạn bao nhiêu. `config.py:136` đã có sẵn khuôn
(`"rolling_tpm":12000, "context_window":131072`), chỉ là chưa ai điền.

### 3.3 Fail-closed đang đi ngược chiều với bài toán TPM

Khi compiler thấy `estimate.input_tokens + reserved > rolling_tpm_remaining`, nó thêm lý do
`rolling_tpm` và trả về **legacy**. Nhưng legacy chính là đường gửi 21.446 token.

Tức là: phát hiện "request này quá to so với hạn mức" rồi phản ứng bằng cách **gửi một
request còn to hơn**. Với đường đọc thì fail-closed về legacy là đúng. Với ràng buộc TPM thì
nó sai chiều.

Yêu cầu gốc nói rõ điều cần làm: *"Nếu vẫn vượt thì chuyển sang engine khác hoặc báo cần đổi
model. Không gửi một request chắc chắn vượt TPM rồi mới để Groq trả lỗi."* Phần "chuyển engine
hoặc báo" chưa được xây.

### 3.4 Không có gì canh kích thước prompt lõi

**Đính chính một khẳng định sai của chính tài liệu này ở bản đầu:** bản đầu ghi `CLAUDE.md`
đã phình 23%, từ 21.479 lên 26.505. Sai. Đó là so **byte** với **ký tự**: `wc -c` trả 26.505
byte, còn `len()` trả 21.479 ký tự, và chẩn đoán gốc đếm bằng ký tự. Tiếng Việt có dấu nên
mỗi ký tự chiếm nhiều hơn một byte. `CLAUDE.md` **không hề phình, nó y nguyên**.

Nhưng kết luận thì vẫn giữ, chỉ đổi lý do: không có gì canh. Không có test, không có cảnh
báo. Việc nó chưa trôi cho tới giờ là may, không phải do có rào.

Chừng nào Phase 8 chưa bật thì mỗi dòng thêm vào `CLAUDE.md` là thuế đánh lên mọi lượt chat
của mọi model, và không ai nhìn thấy khoản thuế đó tăng.

### 3.5 Chưa có `capability_index.py`, mới chỉ có keyword

Registry đang dùng FTS5, tức là **chỉ keyword**. Kế hoạch gốc yêu cầu hybrid: keyword cộng
semantic cộng graph, kèm dynamic widening khi độ tin cậy thấp.

Với vài chục capability thì keyword đủ. Nhưng mục tiêu chủ repo nói rõ là "sau này cắm thêm
nhiều hơn nữa MCP, model, workflow". Đến lúc đó resolver keyword sẽ bắt đầu trượt im lặng, và
`miss_class` trên trang Chẩn đoán là chỗ nhìn thấy điều đó trước khi nó thành vấn đề.

Đây là rủi ro chất lượng khi mở rộng, không phải lỗi hôm nay.

### 3.6 Module theo kế hoạch gốc: có, gộp, và thiếu

- Có riêng: `capability_registry`, `capability_resolver`, `context_compiler`, `evidence_store`,
  `model_router`.
- Gộp vào chỗ khác, chấp nhận được: quality gate nằm trong `context_compiler`; task state và
  orchestrator nằm trong `context_runtime` cộng `readonly_orchestrator`; policy engine nằm rải
  trong resolver và executor.
- **Thiếu thật:** `capability_index` (mục 3.5) và `quota_scheduler` như một dịch vụ chung. TPM
  hiện được tính trong `context_runtime`, đủ cho từng đường canary, nhưng chưa có ai điều phối
  hạn mức **giữa** chat, loop, task nền và nhắc hẹn. Bốn nguồn đó cùng ăn một hạn mức Groq mà
  không ai biết ai.

## 4. Kế hoạch bổ sung

Xếp theo nguyên tắc: thứ có tác dụng sớm nhất và rẻ nhất lên trước.

### Việc 1: Đưa builtin và plugin vào tầng lazy, hạ ngưỡng

**Vì sao trước tiên:** đây là thứ duy nhất có tác dụng **ngay trên đường legacy hôm nay**,
không cần bật canary, không cần chờ baseline. Nhắm giảm khoảng 17.000 ký tự xuống còn vài
nghìn.

- Mở rộng `pool` trong `_apply_lazy` để nhận cả builtin và plugin, giữ lại một nhóm nhỏ tool
  hạt nhân luôn hiện: tìm tool, chạy tool, đọc file, và các tool phiên bắt buộc.
- Hạ `lazy_threshold` xuống mức làm nó thật sự kích hoạt ở cấu hình hiện tại.
- Nhóm hạt nhân phải **khai bằng danh sách tường minh**, không suy ra từ việc có `conn` hay
  không. Suy ra ngầm chính là nguyên nhân của lỗ này.
- Rào: test đối chiếu hai chiều, mọi tool hạt nhân phải tồn tại thật trong route, để đổi tên
  tool mà quên sửa danh sách thì CI đỏ chứ không hỏng câm.

Nghiệm thu: đo tổng ký tự schema trước và sau trên cùng một cấu hình. Và một test canh trần,
tổng schema gửi đi không được vượt ngưỡng khai báo.

### Việc 2: Canh kích thước prompt lõi

Một test đọc `CLAUDE.md` và fail khi vượt ngân sách khai báo. Kèm một dòng trong tài liệu nói
rõ đây là thuế trên mọi lượt chat. Rẻ, và nó chặn đúng kiểu trôi đã xảy ra suốt tám phase.

### Việc 3: Endpoint đặt canary an toàn, và merge đệ quy

Đã mô tả ở mục 3 của tài liệu triển khai. Phải làm trước Việc 4, vì nếu không thì khai hạn
mức Groq bằng tay sẽ dính bẫy merge một tầng và `quota_profiles` biến mất im lặng.

Sửa `read_settings()` thành merge đệ quy là phần quan trọng nhất ở đây.

### Việc 4: Khai hạn mức thật cho Groq và các model đang dùng

Không code, chỉ dữ liệu, nhưng phải sau Việc 3. Điền `rolling_tpm`, `context_window`, giá.
Đây là thứ mở khoá toàn bộ cỗ máy đã xây.

Nghiệm thu bằng trang Chẩn đoán: `quota_rules` khác 0.

### Việc 5: Sửa chiều fail-closed cho ràng buộc TPM

Khi lý do từ chối là `rolling_tpm`, không được rơi về legacy. Ba nấc, theo đúng yêu cầu gốc:

1. Nén mạnh hơn: bỏ bớt context item giá trị thấp rồi biên dịch lại.
2. Vẫn vượt thì chuyển provider theo Model Router, dựa trên hạn mức thật của từng model.
3. Vẫn không được thì **nói với người dùng**, kèm con số ước lượng và hạn mức, gợi ý đổi model.

Tuyệt đối không im lặng gửi một request chắc chắn vượt.

Nghiệm thu: dựng model giả có `rolling_tpm` rất nhỏ, khẳng định hệ thống **không** gọi
provider đó, và khẳng định nó không rơi về legacy.

### Việc 6: `quota_scheduler` dùng chung cho mọi nguồn

Chat, loop, task nền và nhắc hẹn đang cùng ăn một hạn mức mà không biết nhau. Gom kế toán TPM
và RPM về một chỗ, mọi đường gọi model đều xin phép qua đó.

Chưa cấp bách khi chỉ có một người dùng, nhưng sẽ thành cấp bách ngay khi loop chạy nền cùng
lúc với chat.

### Việc 7: `capability_index` hybrid

Thêm semantic và graph bên cạnh keyword, kèm dynamic widening khi độ tin cậy thấp. Làm khi
`miss_classes` trên trang Chẩn đoán cho thấy resolver bắt đầu trượt, chứ không làm trước.

Đây là việc bảo vệ **chất lượng** khi số capability tăng, và nó là điều kiện để lời hứa
"cắm thêm bao nhiêu MCP cũng được" đứng vững.

## 5. Thứ tự và lý do

Việc 1 và 2 độc lập với toàn bộ chuyện canary, làm được ngay, có tác dụng ngay hôm nay.

Việc 3, 4, 5 là một chuỗi phải theo thứ tự, và chúng mới là thứ thật sự làm Groq chạy được.

Việc 6 và 7 là chuyện mở rộng, làm khi có tín hiệu từ trang Chẩn đoán chứ không làm theo linh
cảm.

Điểm cần nhớ: sau 12 phase, thứ chặn Groq hôm nay **không phải kiến trúc còn thiếu**, mà là
một khối schema tool chưa ai đưa vào tầng lazy, cộng với một dòng cấu hình hạn mức chưa ai
điền.
