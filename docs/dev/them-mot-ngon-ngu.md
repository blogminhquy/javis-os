# Thêm một ngôn ngữ vào Javis

Tài liệu này là **bài kiểm tra nghiệm thu** của cả tầng đa ngôn ngữ. Nếu thêm một thứ tiếng mà
phải sửa file ngoài danh sách dưới đây, thì kiến trúc đã hỏng ở đâu đó - **sửa kiến trúc trước,
đừng vá lén một chỗ cho xong**.

Thiết kế đầy đủ nằm ở `docs/dev/2026-08-da-ngon-ngu-spec.md`. Đây là bản việc-cần-làm.

Ví dụ xuyên suốt: thêm **tiếng Thái (`th`)**.

---

## ĐỌC TRƯỚC: Javis đã trả lời được tiếng Thái rồi

Không đăng ký gì cả, người dùng gõ tiếng Thái thì Javis vẫn đáp tiếng Thái. Từ 0.35.0, ngôn
ngữ TRẢ LỜI do **model** lo: prompt bảo nó bám theo thứ tiếng người dùng vừa viết, và nó làm
được với mọi thứ tiếng.

Vậy đăng ký để được gì. Đúng bốn thứ, đều là chỗ **không có model trong vòng lặp**:

| Được gì | Không đăng ký thì sao |
|---------|-----------------------|
| Chữ trên màn hình dịch được | giao diện vẫn tiếng Việt |
| Giọng đọc TTS đúng tiếng | đọc bằng giọng Việt, nghe như máy hỏng |
| Múi giờ, tiền tệ, định dạng số mặc định | dùng của Việt Nam cho tới khi user tự đổi |
| Đường tắt tiết kiệm token bật được | vẫn chạy, chỉ tốn hơn |

Nói cách khác đây là việc **nên** làm, không phải việc **phải** làm để Javis nói được thứ
tiếng đó. Đừng để ai chờ hết bốn bước dưới rồi mới dám mời người dùng Thái vào.

---

## Bốn bước bắt buộc

### 1. Khai ngôn ngữ trong sổ đăng ký

`server/lang_registry.py`, thêm một mục vào `LANGS`:

```python
"th": Lang(
    code="th", native="ไทย", english="Thai", script="thai", rtl=False,
    stopwords=("และ", "ที่", "เป็น", "ของ", "ไม่", ...),   # hư từ, dùng để DÒ
    request_words=("ช่วย", "อยาก", ...),                    # từ mở đầu câu nhờ vả
    stt="th", tts={"edge": "th-TH-PremwadeeNeural", ...},
    tz_default="Asia/Bangkok", currency="THB", first_day=0,
    number_locale="th-TH", plural=True,
    nudge="...", weekdays=(...), clock_template="...",
    lang_directive="Reply in Thai.",
),
```

Hai trường hay bị làm ẩu:

- **`stopwords`** là bằng chứng để `lang.detect()` chấm điểm, và bộ dò nay chỉ phục vụ CỔNG
  CHẶN với GIỌNG ĐỌC chứ không quyết định ngôn ngữ trả lời nữa. Chọn hư từ **thường gặp và
  riêng** của thứ tiếng đó, và **chỉ hư từ, đừng lấy danh từ** - danh từ đi xuyên ngôn ngữ
  (bản thử từng thêm "week" với "report" vào tiếng Anh, thế là câu tiếng Hà Lan thành tiếng
  Anh). Cũng đừng lấy chữ trùng tiếng Việt viết không dấu; xem `lang._TU_NGOAI` để biết danh
  sách những chữ đã bị loại và vì sao.
- **`weekdays`** theo `datetime.weekday()`, tức **0 = thứ hai**. Cron dùng 0 = chủ nhật.
  `cron_util._ten_thu()` đã bù lệch này; đừng bù lần thứ hai.

Chữ không phải Latin thì thêm luôn khoảng mã Unicode vào `lang._KHOANG_CHU` (tiếng Thái đã có
sẵn). Bảng đó xét theo **thứ tự ưu tiên**, không phải gặp trước lấy trước: tiếng Nhật phải đứng
trước tiếng Trung vì văn bản Nhật có kanji lẫn kana.

### 2. Chép và dịch từ điển giao diện

```
cp dashboard/i18n/vi.json dashboard/i18n/th.json
```

Rồi dịch phần giá trị. **Không cần dịch hết ngay.** Key thiếu tự rơi về `vi`, rồi rơi về chính
tên key - giao diện không bao giờ vỡ, chỉ lẫn tiếng cho tới khi bản dịch đầy dần.

Hai key kỹ thuật phải sửa: `_meta.name` (tên hiện trong ô chọn) và `_meta.number_locale`.

### 3. Viết bộ từ vựng cho cổng an toàn (**tuỳ chọn, nhưng đọc kỹ chỗ này**)

`server/lexicon/th.py`, đủ 12 tập tên trong `lexicon.BAT_BUOC`.

**Không viết cũng được. Viết MỘT NỬA thì nguy hiểm hơn không viết.**

Đây là chỗ dễ sai nhất trong cả tầng đa ngôn ngữ, nên nói cho rõ vì sao:

- **Không có `th.py`**: `lexicon.get("th")` trả `None`, các cổng biết là mình mù, đường tắt tiết
  kiệm token tự tắt, rào chắn hạ xuống tầng model phụ. Javis chạy **đúng**, chỉ tốn hơn.
- **Có `th.py` nhưng thiếu tập DENY**: cổng tưởng mình đọc được tiếng Thái. Câu khớp ALLOW thì
  đi thẳng, mà không gì chặn lại. **Rò rỉ, và rò trong im lặng.**

Nên hoặc viết đủ 12 tập, hoặc đừng tạo file. `lexicon/__init__.py` có kiểm số tập lúc nạp, và
test `test_lang_bat_bien.py` canh cùng chuyện đó ở cả hai đầu.

Viết sau khi đã có người dùng thật cũng được - đó là thứ tự đúng, không phải sự lười.

### 4. Chạy test

```
python tests/run.py
```

`test_da_ngon_ngu.py`, `test_lang_bat_bien.py` và `test_locale.py` đối chiếu key giữa các từ
điển, kiểm bất biến sổ đăng ký, và canh những chỗ hay mọc lại (ghim cứng UTC+7, khoá cứng
`lang == "vi"`).

---

## Hai bước tuỳ chọn, làm sau cũng được

### 5. Mô tả skill theo ngôn ngữ

Trong `SKILL.md`, thêm khoá `description_th` (và `name_th` nếu tên cũng cần dịch) cạnh bản gốc:

```yaml
---
name: Notes
description: Lưu tin nhắn hiện tại nguyên văn vào sources/ ...
description_en: Save the current message verbatim into sources/ ...
description_th: ...
group: AI
---
```

Thiếu thì rơi về `description` gốc. Mô tả skill là **bề mặt đối chiếu** giữa câu người dùng vừa
gõ và danh sách skill, nên cùng thứ tiếng thì định tuyến sắc hơn - nhưng khác tiếng vẫn chạy.

Bản dịch cũng chịu đúng trần `SKILL_DESC_MAX` (150 ký tự) như bản gốc, vì nó đi vào cùng chỗ
trong prompt. `system_sync._cap_desc` cắt mọi khoá mô tả, không riêng khoá gốc.

### 6. Tài liệu

Tài liệu người dùng dịch tay, không qua từ điển. Quy ước đặt tên: `README.en.md`,
`QUICKSTART.en.md`, `docs/en/*.md`. Mỗi bản đặt một dòng link qua lại ở đầu file.

---

## Những gì **không** phải làm

Liệt kê ra đây vì đây là chỗ người ta hay đi thừa:

- **Không** dịch system prompt hay `CLAUDE.md`. Prompt giữ tiếng Việt; khối
  `# === NGÔN NGỮ ===` ở cuối mới là thứ quyết định Javis trả lời tiếng gì. Model đọc được
  hướng dẫn tiếng Việt rồi trả lời tiếng Thái - đó là chuyện bình thường, và một bộ prompt
  cho mỗi thứ tiếng là một bộ nữa để trôi lệch.
- **Không** dịch nhãn mốc trong prompt (`# === SKILL KHẢ DỤNG`, `# === BÂY GIỜ ===`...). Chúng
  là **mốc đo**: `context_runtime` đếm token theo đúng chuỗi đó. Dịch chúng là làm phép đo im
  lặng ngừng chạy cho đúng nhóm người dùng mới thêm vào.
- **Không** suy locale từ ngôn ngữ. Đọc giao diện tiếng Anh mà vẫn ngồi ở Việt Nam là chuyện
  bình thường; múi giờ và tiền tệ ở `server/localefmt.py`, chọn riêng.
- **Không** viết `if lang == "th"` ở bất kỳ đâu ngoài `lang_registry.py`. Có test canh.

---

## Ngôn ngữ ĐÃ ĐĂNG KÝ

Nhắc lại: đây KHÔNG phải danh sách thứ tiếng Javis nói được. Javis trả lời được mọi thứ tiếng.
Đây là danh sách thứ tiếng đã có giao diện, giọng đọc và cổng chặn riêng.

| Mã | Tên | Từ điển giao diện | Bộ từ vựng cổng | Mô tả skill |
|----|-----|-------------------|-----------------|-------------|
| `vi` | Tiếng Việt | đủ | đủ | gốc |
| `en` | English | đủ | đủ | đủ |
