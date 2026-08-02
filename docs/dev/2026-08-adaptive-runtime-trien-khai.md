# Kế hoạch triển khai Adaptive Context Runtime v2

Tài liệu này nối tiếp `2026-08-adaptive-context-runtime-spec.md`. Spec trả lời "xây cái gì".
Tài liệu này trả lời "đưa nó tới người dùng bằng cách nào mà không gãy".

Trạng thái lúc viết: 12 phase đã code xong, đã kiểm chứng là **nằm im ở mặc định**. Chưa một
request thật nào đi qua đường mới.

## 0. Điểm xuất phát thật

Hai thứ cần nói rõ trước khi lập kế hoạch, vì chúng đổi khối lượng công việc:

- `main` **đã mang sẵn** code Phase 0 tới 12 (PR #53 tới #57 đã merge). Phần còn lại trên
  nhánh chỉ là 5 commit của PR #58. Nghĩa là bước "đưa vào bản chính" nhỏ hơn nhiều so với
  cảm giác.
- Cơ chế cập nhật VPS là `git pull` trên nhánh đang checkout, kèm **rollback tự động**: nếu
  `/health` không lên trong khoảng 90 giây thì updater `git reset --hard <sha cũ>`, cài lại
  deps rồi khởi động lại. Đây là lưới an toàn mạnh nhất đang có, và nó miễn phí.

Nâng cấp schema DB **không cần thao tác tay**: `runtime.db` và registry đều dùng
`CREATE TABLE IF NOT EXISTS` cộng `ALTER TABLE ADD COLUMN` chạy lúc mở kết nối, idempotent.
DB dựng bởi bản cũ tự lên schema mới, không mất dữ liệu.

## 1. Hai tính chất vận hành đã kiểm bằng thực nghiệm

Cả hai đều quyết định cách viết quy trình bên dưới, nên đã chạy thử chứ không suy luận.

### 1.1 Bật/tắt canary KHÔNG cần restart

`read_settings()` cache theo `(mtime_ns, size)` của `settings.json`, còn `_policy()` đọc
settings ở mỗi lượt. Sửa file là lượt kế tiếp ăn ngay.

Hệ quả quan trọng: **rollback một canary là tức thì**. Đặt allocation về 0, lưu file, xong.
Không cần deploy, không cần restart, không có cửa sổ downtime. Điều này cho phép bật thử
mạnh dạn hơn bình thường.

### 1.2 Cái bẫy merge một tầng (phải đọc trước khi sửa settings)

`read_settings()` gộp cấu hình người dùng đè lên mặc định bằng `.update()` **chỉ một tầng**:

```python
for k, v in (data or {}).items():
    if isinstance(v, dict) and isinstance(cfg.get(k), dict):
        cfg[k].update(v)      # <-- một tầng, KHÔNG đệ quy
```

Các knob canary nằm sâu **hai tầng** (`context_runtime.canary.allocation_basis_points`).
Nên nếu sửa tay kiểu này:

```json
{ "context_runtime": { "canary": { "allocation_basis_points": 100 } } }
```

thì toàn bộ sub-dict `canary` bị **thay thế**, không phải bổ sung. Đã chạy thử, kết quả:

```
canary sau khi chỉ ghi 1 field: {"allocation_basis_points": 100}
=> quota_profiles còn không: False
```

`quota_profiles` biến mất. Mà thiết kế fail-closed nói rằng thiếu quota profile thì **rơi về
legacy**. Nghĩa là anh bật 1 phần trăm, tưởng đã bật, và **không có gì xảy ra cả**, im lặng,
không lỗi, không cảnh báo.

Đây đúng là kiểu hỏng tệ nhất: knob xoay được, đèn không sáng, không ai biết vì sao.

**Luật khi sửa tay:** phải ghi **trọn vẹn** sub-dict của canary đó, copy đủ mọi field từ
`_DEFAULT` trong `server/config.py` rồi mới đổi giá trị cần đổi.

**Cách tự kiểm sau khi sửa:** mở trang Chẩn đoán, xem mục canary. Nó hiện `quota_rules` và
`allowlist` dạng số đếm. Thấy `quota_rules: 0` là biết vừa dính bẫy.

## 2. Lộ trình

### Bước 1: Đưa code vào bản chính và lên VPS

Không bật gì cả. Mục tiêu duy nhất là đưa cỗ máy lên chỗ nó sẽ chạy, và xác nhận nó nằm im
đúng như thiết kế.

1. Merge PR #58 (5 commit) vào `main`.
2. Nâng version. Đề xuất `0.10.0` chứ không phải một bản patch: đây là mốc nền tảng mới, dù
   chưa đổi hành vi. Viết changelog **trung thực**, nói thẳng là chạy shadow và chưa đổi gì
   cho người dùng, kèm trang Chẩn đoán là thứ duy nhất nhìn thấy được.
3. Cập nhật VPS bằng luồng cập nhật sẵn có.

Nghiệm thu bước 1, làm ngay sau khi VPS lên:

- Mở trang Chẩn đoán. Banner phải ghi `mode: shadow`.
- Bảng canary phải cho thấy **tất cả** allocation bằng 0.
- Chat vài câu bình thường, quay lại trang Chẩn đoán, phải thấy task mới hiện ra với
  `execution_path` là `legacy` hoặc `unassigned`. Thấy đúng nghĩa là trace đang ghi thật.
- Nếu `/health` không lên, updater tự rollback. Không cần làm gì.

### Bước 2: Gom baseline (2 tới 3 tuần, không code)

Đây là bước không hào nhoáng và là bước hay bị bỏ nhất. Không có nó thì không có cách nào
biết đường mới tốt hơn hay tệ hơn đường cũ, và mọi con số sau này đều là cảm tính.

Việc phải làm: dùng Javis như bình thường. Không đụng gì.

Mỗi tuần mở trang Chẩn đoán một lần và ghi lại bốn thứ:

- `estimate_error_pct`. Đây là chỉ số quan trọng nhất. Nó nói bộ ước lượng token lệch bao
  nhiêu so với thực tế. Lệch lớn thì mọi quyết định ngân sách phía sau đều xây trên cát.
- `capsule` median và max. Cho biết capsule đang to cỡ nào so với prompt hiện tại.
- `miss_classes`. Resolver trượt vì gì. Nếu trượt chủ yếu vì thiếu capability trong registry
  thì vấn đề nằm ở registry chứ không phải ở resolver.
- `quality`. Quality Gate kêu gì ở shadow.

Điều kiện ra khỏi bước 2: có đủ vài trăm task trong cửa sổ quan sát, và `estimate_error_pct`
ổn định chứ không nhảy loạn giữa các tuần.

### Bước 3: Vá cái bẫy trước khi bật (nên làm trong lúc chờ bước 2)

Hiện **không có UI nào** để chỉnh `context_runtime`. Đã tìm cả `dashboard/`, không có một
tham chiếu nào ngoài trang Chẩn đoán đọc ra để hiển thị.

Cộng với cái bẫy merge một tầng ở mục 1.2, nghĩa là quy trình bật hiện tại là: SSH vào VPS,
sửa tay JSON lồng hai tầng, và nếu sửa thiếu thì hỏng im lặng.

Ba lựa chọn, xếp theo công sức:

1. **Chỉ viết quy trình.** Rẻ nhất, nhưng để nguyên cái bẫy. Không khuyến nghị.
2. **Thêm endpoint đặt canary.** Một `POST /runtime/canary` nhận tên đường và allocation, tự
   đọc `_DEFAULT`, merge đệ quy đúng cách rồi ghi. Diệt cái bẫy tận gốc, không cần đụng giao
   diện. **Đây là lựa chọn em khuyến nghị.**
3. **Thêm UI vào trang Chẩn đoán.** Đẹp nhất nhưng tốn nhất, và chỉ có một người dùng là chủ
   repo nên chưa đáng.

Dù chọn gì cũng nên sửa `read_settings()` thành merge **đệ quy**. Cái bẫy này không chỉ hại
`context_runtime`, nó hại mọi cấu hình lồng từ hai tầng trở lên trong tương lai.

### Bước 4: Bật đường đầu tiên

Bật **fast path** (`canary`) trước, không bật cái nào khác. Lý do: nó đơn giản nhất trong 11
đường, chỉ ảnh hưởng một lượt chat, không ghi gì ra ngoài, không có nhiều bước để hỏng ở
giữa. Nếu có gì sai thì sai ở chỗ dễ đọc nhất.

Trình tự:

1. Khai `quota_profiles` thật cho model đang dùng, gồm giá và cửa sổ ngữ cảnh. Thiếu giá thật
   thì router và ngân sách đều fail-closed, tức là bật cũng như không.
2. Đặt `allocation_basis_points` lên **100** (tức 1 phần trăm), ghi trọn sub-dict theo luật ở
   mục 1.2.
3. Mở trang Chẩn đoán, xác nhận `quota_rules` khác 0. Đây là bước bắt lỗi im lặng.
4. Chat vài chục lượt. Xem histogram `paths` đã xuất hiện `fast` chưa. Chưa xuất hiện thì đọc
   `fallback_reasons` để biết nó từ chối vì gì.

Điều kiện giữ lại: chất lượng không tệ hơn baseline ở bước 2, và `estimate_error_pct` không
xấu đi. Điều kiện gỡ: bất cứ dấu hiệu nào cho thấy câu trả lời tệ đi. Gỡ bằng cách đặt
allocation về 0, có hiệu lực ngay, không cần deploy.

Nâng dần 100 rồi 500 rồi 2000 basis points, mỗi mức để chạy ít nhất vài ngày.

### Bước 5: Mở rộng theo đúng thứ tự rủi ro

Chỉ bật đường kế tiếp khi đường trước đã ở mức cao và ổn định. Thứ tự theo mức độ hậu quả khi
sai, nhẹ trước nặng sau:

1. `canary` (fast path). Một lượt chat, không ghi.
2. `readonly_canary`. Có gọi MCP nhưng chỉ đọc.
3. `context_sources`, `memory_canary`, `lazy_skill_canary`. Đổi cách nạp ngữ cảnh.
4. `orchestrator_canary`. Nhiều vòng, vẫn chỉ đọc.
5. `model_router_canary`. Đổi model, cần bảng giá thật.
6. `workflow_canary`, `agent_canary`. Có nhánh dừng chờ người.
7. `write_canary`. **Cuối cùng, luôn luôn.** Đây là đường duy nhất tạo ra hành động không hoàn
   tác được ra thế giới thật.

Trước khi tới nhóm 6 và 7, phải có bộ gold benchmark. Đường có tác dụng phụ mà chỉ đánh giá
bằng cảm tính là đánh bạc.

## 3. Lưới an toàn đang có

Ghi lại để khỏi phát minh lại:

- **Rollback deploy tự động** khi `/health` không lên.
- **Rollback canary tức thì** bằng cách sửa settings, không cần restart (mục 1.1).
- **Fail-closed ở mọi chỗ**: allowlist rỗng, thiếu quota profile, thiếu giá đều rơi về legacy.
- **Test hàng rào bất biến** `test_repository_defaults_activate_no_canary_path` chạy admission
  thật của cả 8 đường bằng chính hằng trong `config.py`. Ai lỡ tay bật một đường ở mặc định
  thì CI đỏ.
- **Trang Chẩn đoán** là nơi duy nhất nhìn thấy sự thật. Mọi bước ở trên đều nghiệm thu bằng
  nó chứ không bằng cảm giác.

## 4. Thứ vẫn chưa có

Nói thẳng để không ai tưởng là đã đủ:

- Chưa có baseline production. Bước 2 sinh ra nó.
- Chưa có `quota_profiles` và bảng giá do người vận hành khai. Bước 4 cần.
- Chưa có gold benchmark. Nhóm 6 và 7 ở bước 5 cần.
- Chưa có UI hoặc endpoint đặt canary an toàn. Bước 3 giải quyết.

Chừng nào bốn thứ này còn thiếu thì con số đúng cho mọi allocation vẫn là 0.
