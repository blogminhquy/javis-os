# Spec: Đa ngôn ngữ cho Javis OS

> Bản spec dev, viết 2026-08-10 trên nền v0.26.16. Mục tiêu: Javis nói được nhiều thứ tiếng
> mà **thêm ngôn ngữ thứ N+1 là thêm DỮ LIỆU, không phải sửa mã**.
>
> **Trạng thái: ĐỢT 1 ĐÃ TRIỂN KHAI** (2026-08-14, trên nền v0.34.1) cho hai ngôn ngữ
> **vi** và **en**. Xem mục 6 để biết đúng cái gì đã làm và cái gì chưa.
>
> Phần khảo sát dưới đây viết trên nền v0.26.16 nên SỐ DÒNG đã lệch. Bốn chỗ spec nói
> SAI hoặc nói QUÁ đã được đính chính tại chỗ, đánh dấu **[ĐÍNH CHÍNH]** - đọc chúng
> trước khi lấy spec này ra xếp ưu tiên.

## 1. Quyết định cốt lõi và vì sao

**"Đa ngôn ngữ" không phải một việc. Nó là BỐN việc khác nhau bị gọi chung một tên**, và ba
trong bốn việc đó không liên quan gì tới nhau về mặt kỹ thuật. Gộp chúng lại là cách chắc chắn
nhất để làm xong tầng dễ nhất rồi tưởng đã xong.

| # | Tầng | Câu hỏi thật sự | Khó ở đâu |
|---|------|-----------------|-----------|
| 1 | **Ngôn ngữ TRẢ LỜI** | Javis đáp lại bằng tiếng gì | Gần như đã xong sẵn, chỉ vướng một dòng luật trong `CLAUDE.md` |
| 2 | **Ngôn ngữ GIAO DIỆN** | Chữ trên nút, nhãn, thông báo lỗi | 3.520 dòng tiếng Việt nhúng cứng, không có bước build |
| 3 | **Ngôn ngữ của LOGIC** | Cổng chặn, bộ phân loại, bộ dò lời hứa | **Nguy hiểm nhất. Hỏng trong im lặng.** |
| 4 | **Locale** | Múi giờ, tiền tệ, định dạng ngày, giọng đọc | UTC+7 nhúng cứng ở 6 chỗ |

**Tầng 3 là lý do spec này tồn tại.** Tầng 1 và 2 hỏng thì người dùng NHÌN THẤY ngay và phàn
nàn. Tầng 3 hỏng thì không ai thấy gì cả: một người dùng tiếng Thái sẽ được Javis phục vụ y như
thường, chỉ khác là đường tắt tiết kiệm token nuốt luôn câu hỏi cần dữ liệu live, bộ bắt "nói dối
đã làm xong" không bao giờ nổ, và cổng chặn thao tác lịch không bao giờ đóng. Không có log đỏ,
không có ngoại lệ, chỉ có câu trả lời sai một cách lịch sự.

Vì vậy **quyết định số một: ngôn ngữ KHÔNG được là điều kiện của logic.** Ở đâu hôm nay đang có
`re.compile(r"...dat lich|dang bai...")` quyết định hành vi thì ở đó phải chuyển thành "tra một
bộ từ vựng theo ngôn ngữ", cộng một **luật suy biến an toàn** cho ngôn ngữ chưa có bộ từ vựng.

**Quyết định số hai: một bản CLAUDE.md duy nhất.** Không dịch 30KB luật hành xử ra N bản. Repo
này đã một lần mắc bẫy "viết bản thứ hai của thứ đã có rồi hai bản trôi lệch" ở 0.15.0 (xem
[spec CLI](2026-08-cli-spec.md) mục 1). Prompt hệ thống 30KB nhân N ngôn ngữ là đúng cái bẫy đó,
ở quy mô tệ hơn: hai bản luật an toàn lệch nhau thì phiên bản tiếng Anh mất một rào chắn mà
không ai biết. Model không cần đọc luật bằng tiếng Anh để TRẢ LỜI bằng tiếng Anh.

**Quyết định số ba: tách ba biến ngôn ngữ, đừng nhập một.** Ngôn ngữ giao diện, ngôn ngữ trả
lời, và ngôn ngữ nội dung trong brain là ba thứ độc lập. Một người Việt bán hàng cho khách Nhật
muốn giao diện tiếng Việt, brain tiếng Việt, nhưng con chatbot chăm khách phải trả lời tiếng
Nhật. Nhập ba biến làm một là chặn đứng đúng ca dùng đáng tiền nhất.

## 2. Hiện trạng: đã soi mã, không đoán

### 2.1. Tầng TRẢ LỜI - gần xong rồi

Đây là tin tốt. Hợp đồng đầu ra **đã** language-agnostic từ trước:

- `context_compiler.ContextCompiler._output_contract` (context_compiler.py:366) trả
  `{"language": "match_user", ...}`.
- `_output_contract_text` (context_compiler.py:394) viết thành lời: *"Dùng đúng ngôn ngữ người
  dùng đang dùng."*

Nghĩa là đường tiết kiệm token đã bám ngôn ngữ người dùng. Chỗ kéo ngược lại là **đường legacy**,
nơi prompt hệ thống là nguyên văn `CLAUDE.md`:

- `main.py:231-232` nạp `CLAUDE.md` thành `SYSTEM_PROMPT`.
- `main.py:354` `build_system_prompt()` nối thêm bộ nhớ, lớp agentic, đồng hồ, mức dùng.
- `CLAUDE.md` mục "Nguyên tắc phản hồi" luật số 5: **"Tiếng Việt là ngôn ngữ chính"**.

Một dòng đó đè lên `match_user` ở mọi lượt chạy đường legacy. Sửa tầng 1 chủ yếu là sửa dòng đó
cho có điều kiện, cộng một khối NGÔN NGỮ chèn động.

Còn vài chỗ ép tiếng Việt cứng trong prompt phụ:

- `main.py:3016` mô tả ảnh "bằng tiếng Việt".
- `main.py:5801` prompt lint "Tiếng Việt".
- `meta_tools.py:79` "Tiếng Việt là ngôn ngữ chính".
- `reminders.py:689` prompt tóm tắt nhắc hẹn "tiếng Việt".
- `context_compiler.dong_ho()` (context_compiler.py:60) sinh câu "Bây giờ là 14:30 thứ hai ngày
  10/08/2026, giờ Việt Nam (UTC+7)".
- `channel_context.build_channel_block()` (channel_context.py:28) - toàn bộ khối kênh viết bằng
  tiếng Việt, khoảng 60 dòng luật gửi thẳng cho model.

Khối kênh và CORE_CONTRACT viết bằng tiếng Việt thì **không cần dịch** (xem quyết định số hai),
nhưng câu đồng hồ thì có: nó chứa "thứ hai", "giờ Việt Nam" - dữ liệu, không phải luật.

### 2.2. Tầng GIAO DIỆN - 3.520 dòng, không có bước build

Dashboard là JS thuần, `app.mount("/static", StaticFiles(...))` (main.py:218). Không webpack,
không vite, không bundler. Chuỗi tiếng Việt nằm rải trong template literal và thuộc tính HTML.

| File | Dòng có tiếng Việt |
|------|--------------------|
| `dashboard/console.js` | 1.464 |
| `dashboard/app.js` | 449 |
| `dashboard/chatbots.js` | 291 |
| `dashboard/index.html` | 215 |
| `dashboard/sessions-ui.js` | 135 |
| `dashboard/studio.js` | 128 |
| 18 file còn lại | ~838 |
| **Tổng** | **3.520** |

Cộng thêm phía server: **182 chuỗi lỗi tiếng Việt** trả về giao diện dạng `{"error": "..."}`
(ví dụ `"Sai tài khoản hoặc mật khẩu"`, `"Mật khẩu tối thiểu 8 ký tự"`).

**Còn 9.384 dòng tiếng Việt trong `server/*.py` thì phần lớn KHÔNG phải bề mặt sản phẩm.** Chỗ
này hay bị đếm nhầm nên bóc bằng AST cho hết đường suy đoán:

| Loại | Dòng | Ai đọc | Có dịch không |
|------|------|--------|----------------|
| Chú thích (`#`) | 3.142 | lập trình viên | Không |
| **Docstring** | **3.313** | **lập trình viên** | **Không** |
| Chuỗi thật (prompt gửi model + lỗi hiện cho user) | 2.482 | model và người dùng | Chỉ phần hiện cho user |

**69% dòng tiếng Việt trong server là chú thích và docstring.** Repo này cố ý viết docstring
dài để giải thích *vì sao* (một mình `dong_ho()` đã 15 dòng), nên con số 9.384 nhìn thì to mà
bề mặt sản phẩm thật chỉ khoảng **2.500 dòng**, trong đó 182 là chuỗi lỗi hiện cho user còn lại
gần hết là prompt.

Nói cách khác: **ai quy đổi "9.384 dòng tiếng Việt" thành "9.384 dòng phải dịch" là đang ước
lượng cao hơn thực tế khoảng 3,7 lần.** Phạm vi thật của cả dự án đa ngôn ngữ là 3.520 dòng
giao diện cộng 182 chuỗi lỗi, không phải hai vạn dòng.

### 2.3. Tầng LOGIC - chỗ chảy máu

Đây là danh sách đầy đủ những nơi hành vi của Javis phụ thuộc vào việc người dùng gõ tiếng Việt.
Mỗi mục đều đọc mã, có số dòng.

| Chỗ | Mã | Hỏng thế nào khi người dùng nói tiếng khác |
|-----|----|--------------------------------------------|
| Cổng đường tắt nhanh | `fast_path_runtime.py:52-100` - `_DENY` bắt `dinh kem`, `hom nay`, `doanh thu`, `dat lich` | Câu hỏi cần dữ liệu live LỌT qua đường tắt vốn không phát tool. Model bịa. Chính là ca đã ghi trong docstring `dong_ho()`. |
| Cổng một bước chỉ đọc | `readonly_path_runtime.py:44-49` - `_WRITE_INTENT`, `_STATE_REF` | Câu có ý ĐỊNH GHI bị coi là chỉ đọc |
| Điều phối chỉ đọc | `readonly_orchestrator.py:79` | Như trên |
| Bộ bắt khai man hành động | `context_compiler.py:1093-1110` - `_FALSE_ACTION`, `_ACTION_VERBS`, `_QUANTITATIVE` | **Javis nói "đã gửi xong" mà chưa gửi thì không ai chặn.** Đây là rào chắn an toàn, không phải tính năng. |
| Bộ dò lời hứa suông | `background_status.py:60-85` - `_PROMISE` | Luật "KHÔNG hứa em sẽ báo lại" trong `CLAUDE.md` mất hiệu lực im lặng |
| Cổng thao tác lịch | `engine.py:1143-1220` - danh sách từ khoá `hom nay`, `nhac hen`, `dat lich tu van`... | Vừa bỏ sót lệnh thật, vừa nổ nhầm khi khách chỉ nói chuyện phiếm |
| Tìm kiếm cho chatbot khách | `chatbot_grounding.py:70-115` - bỏ dấu tiếng Việt, danh sách từ đụng nhau soạn tay | Chatbot phục vụ khách nước ngoài tra tài liệu kém hẳn |
| Cò ưu tiên ghi ký ức **[ĐÍNH CHÍNH]** | `learn.py:313` - `_REMEMBER_RE` | Bản đầu của spec viết *"Javis không học gì cả"*. **Sai mức độ.** Đọc lại mã: mẫu này chỉ bật cờ `urgent` (dòng 341) để `_should_fire` nổ sau 30 giây thay vì chờ đủ 3 lượt. Cổng quyết định HỌC HAY KHÔNG là `_classify_turn` trả `"low"`, và cổng đó độc lập ngôn ngữ. Sự thật: người dùng tiếng Anh học **CHẬM HƠN**, không phải không học. Bù lại tìm ra một lỗ spec không thấy: mẫu không bỏ dấu nên `"ghi nho gium anh"` (tiếng Việt KHÔNG DẤU) cũng trượt |
| **Dò bot bí** | `chatbot_runtime.py:497` - `_DAU_BI` gồm `chưa có thông tin`, `chuyển nhân viên`, `em chưa rõ`... | **Thuần tiếng Việt, không một chữ tiếng Anh.** Bot chăm khách nước ngoài không bao giờ được tính là bí, tab "Bot bí" rỗng, chủ nhìn vào tưởng bot chạy hoàn hảo |
| Rút trạng thái hội thoại | `conversation_state.py:26-29` - `_GOAL_RE`, `_DECISION_RE`, `_CONSTRAINT_RE`, `_DONE_RE` | Mục tiêu, quyết định, ràng buộc và việc đã xong không được mang sang lượt sau |
| Gợi ý tra bộ nhớ | `memory_index.py:28` - `_MEMORY_HINT_RE` | Không kích hoạt tra ký ức khi đáng tra |
| Suy ý định việc nền | `tasks.py:575` | Phân loại việc sai nhóm |
| Cắt câu để đặt tên phiên | `sessions.py:153` - cắt ở dấu chấm vì "tiếng Việt chấm nhiều" | Tên phiên xấu, không nguy hiểm |

Mười ba chỗ, không phải chín như bản khảo sát đầu. Bốn chỗ tìm ra sau lại **tệ hơn** nhóm tìm
ra trước, vì hai trong số đó đánh vào chính hai thứ làm Javis là Javis: **nó có học được từ
người dùng không**, và **chủ có biết bot của mình đang bí không**.

**[ĐÍNH CHÍNH] Nguy hiểm nằm ở NỬA bộ từ vựng, không phải ở việc thiếu bộ từ vựng.** Bản
đầu của spec viết rằng ngôn ngữ lạ làm các cổng hỏng trong im lặng. Đo lại trên mã thật thì
KHÔNG phải vậy, và sự thật còn đáng chú ý hơn:

    "tóm tắt đơn hàng"    -> bị chặn đúng (mẫu `don hang` khớp)
    "summarize my orders" -> LỌT qua đường tắt, model bịa số đơn hàng
    "สรุปยอดขายวันนี้"     -> không khớp gì cả -> `intent_uncertain` -> đường đầy đủ, AN TOÀN

Tiếng Thái an toàn **vì nó không khớp gì hết**; bộ phân loại vốn đã mặc định từ chối. Tiếng
Anh nguy hiểm **vì nó khớp một nửa**: `summarize` khớp ALLOW, còn DENY tiếng Anh lại thiếu
`orders`. Nói cách khác, ngôn ngữ càng được phục vụ dở dang thì càng nguy hiểm, và ngôn ngữ
sắp thêm vào (tiếng Anh) đúng là ngôn ngữ dở dang đó. Luật suy biến ở mục 4.3 vì vậy vẫn cần,
nhưng lý do thật của nó là **chặn cái nửa vời**, không phải chặn cái chưa có.

**Nhỏ KHÔNG có nghĩa là ít rủi ro.** Mười ba chỗ này
cộng lại chưa tới 60 dòng mã trên tổng số 49.000, nên nhìn bảng dễ kết luận "khoanh vùng được,
không đáng lo". Sai. Chúng nhỏ **chính vì chúng là cổng**: một cái cổng ba dòng điều khiển toàn
bộ thứ chạy sau nó. Thước đo đúng là **bán kính vụ nổ**, không phải số dòng.

Tất cả các bộ trên dùng chung một thủ thuật `_norm()`: bỏ dấu rồi hạ chữ thường, kèm map tay
`đ -> d` vì NFKD không phân rã được `đ` (`fast_path_runtime.py:25`, `readonly_path_runtime.py:34`,
`background_status.py:49`). **Thủ thuật này chỉ đúng cho chữ Latin có dấu.** Tiếng Nhật, tiếng
Thái, tiếng Ả Rập đi qua `_norm()` ra nguyên si, và không mẫu ASCII nào khớp được.

Đáng chú ý: vài mẫu đã có sẵn từ tiếng Anh trộn vào (`send|delete|create|book|publish`). Nghĩa
là tiếng Anh hôm nay được phục vụ **một nửa** - đủ để tưởng là ổn, không đủ để đúng.

### 2.4. Tầng LOCALE

- **Múi giờ UTC+7 nhúng cứng 6 chỗ**: `usage_index.py:28`, `usage_parsers.py:19`,
  `system_sync.py:67`, `main.py:555`, `main.py:3470`, `context_compiler._bay_gio`.
- **Plugin `datetime-vn`** (`system/plugins/datetime-vn/plugin.yaml`) cấp tool `javis_now` và
  `javis_date_add` cho MỌI bộ não, mô tả ghi thẳng "theo múi giờ Việt Nam (UTC+7)".
- **Tiền tệ VND [ĐÍNH CHÍNH]**: đã XONG SẴN ở thượng nguồn. Commit `5c59de7` (0.32.1) gỡ hết phần quy đổi USD sang đồng khỏi trang Mức dùng. Hạng mục này rơi khỏi phạm vi. Phần ĐỊNH DẠNG SỐ thì chưa: `toLocaleString("vi-VN")` vẫn còn ở `usage.js`.
- **Định dạng số/ngày**: `toLocaleString("vi-VN")` ở `usage.js`, `console.js:1245,4045`,
  `sessions-ui.js:20`, `chatbots.js:368`, `studio.js:595`; `localeCompare(..., "vi")` ở
  `dataview.js:365`, `studio.js:442`.
- **Cron ra chữ**: `cron_util.describe_cron()` (cron_util.py:185) sinh "7:00 mỗi ngày", "thứ hai
  hằng tuần". Có sẵn đường suy biến tốt: dạng lạ thì trả nguyên biểu thức cron.
- **Giọng nói**: STT mặc định `language="vi"` (`stt.py:82-96`); TTS mặc định
  `vi-VN-HoaiMyNeural` (`main.py:6347`, `main.py:7110`, `voice.js:7,23`); danh sách giọng Edge
  **lọc cứng** `v["Locale"].startswith("vi")` (main.py:7148); giao diện chỉ cho chọn vi-VN hoặc
  en-US (`index.html:288-306`).
- `<html lang="vi">` (index.html:2).

Một tài sản có sẵn đáng dùng: `voice.elevenlabs_model` đã là `eleven_multilingual_v2`
(`config.py` `_DEFAULT`). Đường ElevenLabs gần như chạy được đa ngôn ngữ ngay.

### 2.5. Chưa có hạ tầng i18n nào

Không `gettext`, không `Babel`, không thư viện dịch trong `requirements.txt`. Bắt đầu từ số
không, và đó là chuyện tốt: được chọn thứ vừa vặn thay vì gánh một khung nặng.

## 3. Phạm vi

### 3.1. Có làm

- **Bản nhỏ nhất đo được nhu cầu trước (mục 6)**, rồi mới tới phần còn lại của danh sách này.
- Ba biến ngôn ngữ tách rời + một hàm quyết định duy nhất `resolve_lang()`.
- Lớp **bộ từ vựng (lexicon)** thay cho regex nhúng cứng, kèm luật suy biến an toàn.
- Hạ tầng i18n cho dashboard không cần bước build, kèm test chống thoái lui.
- Khối NGÔN NGỮ chèn động vào prompt; giữ **một** bản `CLAUDE.md`.
- Mã lỗi cho 182 chuỗi lỗi server, dịch ở phía giao diện.
- Tách locale (múi giờ, tiền, định dạng) khỏi ngôn ngữ.
- Bản đồ giọng nói theo ngôn ngữ cho STT và TTS.
- Trường ngôn ngữ riêng cho từng chatbot chuyên trách.
- Sổ tay "thêm một ngôn ngữ mới" kèm test nghiệm thu.
- Ngôn ngữ thứ hai đi kèm bản này: **tiếng Anh**.

### 3.2. KHÔNG làm, kể cả khi bị thúc

- **Không dịch `CLAUDE.md` ra N bản.** Lý do ở mục 1.
- **Không dịch máy 27 tài liệu người dùng ở mỗi lần phát hành.** Bản dịch cũ nói sai về phần mềm
  mới còn tệ hơn không có bản dịch. Chỉ dịch tay cửa vào: `README.md`, `QUICKSTART.md`,
  `docs/01-bat-dau-thiet-lap.md`. Phần còn lại ghi thẳng "chưa dịch".
- **Không dịch lại câu trả lời của model sau khi nó nói xong.** Tốn gấp đôi, vỡ số liệu, vỡ
  markdown, mà model vốn tự trả lời đúng ngôn ngữ được.
- **Không dịch nội dung brain.** Ghi chú, wiki, ký ức là của người dùng.
- **Không nhét ngôn ngữ vào đường dẫn URL** kiểu `/en/chat`. Dashboard là một trang đơn có rail
  tự định tuyến; một ô cài đặt cộng `localStorage` là đủ.
- **Không nhân bản `SKILL.md` theo ngôn ngữ.** Chỉ cho phép map `description` theo ngôn ngữ, và
  chỉ với 4 skill hệ thống.
- **Không đổi slug plugin `datetime-vn`.** Đổi slug là bắt mọi brain đang chạy phải di trú, đổi
  lấy con số không giá trị. Giữ slug, đổi hành vi.
- **Không đụng chữ phải-viết-hoa của thương hiệu**: "Javis", tên bộ não, tên tool.

## 4. Kiến trúc chốt

### 4.1. Ba biến, một hàm quyết định

```
ui_lang       Ngôn ngữ CHỮ TRÊN MÀN HÌNH. Người dùng chọn. Lưu theo thiết bị.
reply_lang    Ngôn ngữ Javis TRẢ LỜI. Mặc định "auto" (bám người dùng từng lượt).
content_lang  Ngôn ngữ NỘI DUNG brain. Chỉ dùng để gợi ý, không ép.
```

Một hàm duy nhất, `server/lang.py`:

```python
@dataclass(frozen=True)
class LangDecision:
    lang: str          # "vi" | "en" | "ja" ... (mã gọn, không phải BCP-47 đầy đủ)
    source: str        # turn | chatbot | brain | channel | detect | ui | default
    confidence: float  # 0..1
    has_lexicon: bool  # có bộ từ vựng cho ngôn ngữ này không

def resolve_reply_lang(*, turn_text, session, brain, channel, chatbot=None) -> LangDecision
```

**Thứ tự ưu tiên, cao xuống thấp:**

1. Người dùng ra lệnh thẳng trong lượt này ("trả lời tiếng Anh giùm").
2. Ngôn ngữ ghim của chatbot chuyên trách (nếu lượt này là của bot).
3. Ngôn ngữ ghim của brain.
4. Mặc định của kênh (Zalo mặc định `vi` vì đó là nền tảng Việt Nam).
5. Dò từ tin nhắn người dùng.
6. `ui_lang`.
7. `vi`.

**Chống nhảy qua nhảy lại.** Dò ngôn ngữ mỗi lượt rồi đổi ngay là hỏng: người đang nói tiếng
Việt chèn một câu tiếng Anh không có nghĩa là muốn đổi ngôn ngữ. Luật: ngôn ngữ **dính theo
phiên**; chỉ đổi khi kết quả dò khác ngôn ngữ đang dùng **hai lượt liên tiếp** với
`confidence >= 0.8`. Ghi cả `lang` lẫn `lang_source` vào trace để soi được ca dò sai ngoài thực
địa.

**Dò bằng gì.** Không thêm phụ thuộc (repo này đã bỏ `rich` khỏi CLI cho gọn). Chỉ cần phân biệt
giữa các ngôn ngữ ĐÃ ĐĂNG KÝ, nên đủ dùng hai tầng: nhận diện hệ chữ qua khoảng mã Unicode (giải
quyết xong ja, ko, zh, th, ar, ru, hi trong vài dòng), và với các thứ tiếng chữ Latin thì chấm
điểm bằng tập hư từ nằm ngay trong hồ sơ ngôn ngữ. Nghĩa là **thêm ngôn ngữ mới cũng là thêm dữ
liệu**, không phải sửa bộ dò.

### 4.2. Sổ đăng ký ngôn ngữ - một file, mọi thứ về một ngôn ngữ

`server/lang_registry.py`. Đây là **trái tim của tính mở rộng**: thêm ngôn ngữ = thêm một mục.

```python
LANGS = {
  "vi": Lang(
    code="vi", native="Tiếng Việt", english="Vietnamese",
    script="latin", rtl=False,
    stopwords={"và","của","là","không","được","cho","với","này"},
    stt="vi",                                  # mã cho Whisper
    tts={"edge": "vi-VN-HoaiMyNeural", "openai": "alloy", "elevenlabs": None},
    tz_default="Asia/Ho_Chi_Minh", currency="VND", first_day=1,
    plural=False,                              # tiếng Việt không chia số nhiều
    nudge="Trả lời bằng tiếng Việt.",          # dùng cho model yếu, xem 4.5
  ),
  "en": Lang(code="en", native="English", english="English", script="latin",
             stopwords={"the","and","of","is","not","for","with","this"},
             stt="en", tts={"edge": "en-US-AriaNeural", "openai": "alloy",
                            "elevenlabs": None},
             tz_default="UTC", currency="USD", first_day=0, plural=True,
             nudge="Answer in English."),
}
```

Luật: **không mã nào ngoài file này được viết `if lang == "vi"`.** Cần biết gì về một ngôn ngữ
thì hỏi sổ đăng ký. Có một test canh đúng luật này (mục 8).

### 4.3. Lớp bộ từ vựng và luật suy biến an toàn

Đây là phần khó nhất và đáng tiền nhất.

```
server/lexicon/__init__.py    get(lang) -> Lexicon | None
server/lexicon/vi.py          bê nguyên các regex đang có, không đổi một ký tự
server/lexicon/en.py          viết mới
```

Mỗi `Lexicon` cấp đúng những tập mà các cổng đang cần, đặt tên theo Ý NGHĨA chứ không theo chỗ
gọi: `WRITE_INTENT`, `LIVE_DATA`, `ATTACHMENT`, `STATE_REF`, `PROMISE`, `FALSE_ACTION`,
`ACTION_VERBS`, `QUANTITATIVE`, `CAPABILITY_DENIAL`, `SCHEDULE_OPS`.

**Phase 2 bắt đầu bằng việc chép nguyên văn regex tiếng Việt sang `lexicon/vi.py`.** Không sửa,
không "tiện tay dọn". Hành vi tiếng Việt phải giống hệt từng bit, và bộ test hiện có phải xanh
mà không sửa một dòng test nào. Dọn dẹp để lượt sau.

**Luật suy biến - phần quan trọng nhất của cả spec.** Khi ngôn ngữ đã dò ra không có bộ từ vựng,
mỗi cổng suy biến theo **loại của nó**, không phải theo một luật chung:

| Loại cổng | Ví dụ | Không có bộ từ vựng thì |
|-----------|-------|-------------------------|
| **Cổng MỞ RỘNG quyền** (bỏ qua bước, đi đường tắt) | đường tắt nhanh, một bước chỉ đọc | **Từ chối, đi đường đầy đủ.** Trả giá bằng token, không trả giá bằng tính đúng. |
| **Cổng BẮT LỖI** (rào chắn an toàn) | bắt khai man hành động, dò lời hứa suông | **KHÔNG được lặng lẽ cho qua.** Hạ xuống một lượt gọi model phụ rẻ (`aux_engine`), phân loại nhị phân, nhớ tạm theo băm của câu trả lời. Model phụ hỏng thì đánh dấu trace `unverified` và ghi log, chứ không giả vờ đã kiểm. |
| **Cổng TRÌNH BÀY** (chỉ để hiển thị) | cắt câu đặt tên phiên, cron ra chữ | Suy biến thô: cắt theo ký tự, in nguyên biểu thức cron. `describe_cron` đã sẵn đường này rồi. |

Nói cách khác: **thiếu bộ từ vựng làm Javis TỐN HƠN, không làm Javis LỎNG HƠN.** Đó là câu duy
nhất cần nhớ từ mục này.

### 4.4. i18n giao diện, không có bước build

```
dashboard/i18n/index.js    t(), setLang(), applyDom()
dashboard/i18n/vi.json     nguồn chuẩn, đủ 100% key theo định nghĩa
dashboard/i18n/en.json     dịch
```

**Nạp.** `index.html` nạp `i18n/index.js` trước `app.js`. Bộ từ điển nằm trong `localStorage`
kèm dấu phiên bản (cùng cơ chế `?v=` mà `main.py:599` đang đóng dấu cho tài nguyên tĩnh), nên F5
không nháy chữ. Cache trượt phiên bản thì nạp lại một lần rồi vẽ.

**Quy ước key.** Key ASCII, chấm phân cấp, đặt theo TRANG rồi tới ý: `chat.input.placeholder`,
`nav.viec`, `err.login.wrong`. **Tuyệt đối không lấy chính chuỗi tiếng Việt làm key** - sửa một
lỗi chính tả trong bản tiếng Việt mà làm hỏng cả bản tiếng Anh là kiểu hỏng không đáng có.

**Suy biến.** `<đã chọn> -> vi -> chính key`. `vi.json` đủ 100% key vì nó được rút ra từ mã đang
chạy. Người dùng không bao giờ nhìn thấy một key trần.

**Số nhiều.** Tiếng Việt không chia, tiếng Anh có. Không kéo cả ICU MessageFormat vào cho một
việc này. Từ điển được phép khai `key.one` và `key.other`; `t()` chọn theo `{count}` khi có
truyền; ngôn ngữ không chia số nhiều chỉ khai `key.other`.

**Thay biến.** Chỉ `{ten}`. **Cấm HTML trong từ điển** - từ điển là dữ liệu, đưa HTML vào đó là
mở một cửa XSS mà sau này không ai nhớ để đóng. Cần in đậm một phần thì tách chuỗi.

**HTML tĩnh.** `index.html` dùng `data-i18n`, `data-i18n-title`, `data-i18n-aria`; `applyDom()`
quét một lượt sau khi nạp.

**Cách di trú 3.520 dòng mà không đứng hình.** Không làm một phát. Đi theo lưu lượng dùng: khung
chat -> rail điều hướng -> trang Cài đặt -> phần còn lại. Mỗi lượt thêm tên file vào một danh
sách `I18N_MIGRATED`, và một test **báo đỏ nếu file đã di trú lại xuất hiện chữ tiếng Việt ngoài
chú thích**. Không có cái chốt đó thì lần dọn nào cũng bị lượt sửa tính năng kế tiếp làm bẩn lại.

**182 chuỗi lỗi của server: dùng mã lỗi, đừng dịch ở server.** Server trả thêm một trường `code`
bên cạnh chuỗi tiếng Việt đang có:

```python
{"error": "Sai tài khoản hoặc mật khẩu", "code": "auth.bad_credentials"}
```

Giao diện ưu tiên `t("err." + code)`, không có thì hiện nguyên `error`. Tương thích ngược tuyệt
đối, làm dần từng endpoint được, và server không phải biết người dùng đang xem bằng tiếng gì.

### 4.5. Prompt hệ thống: một bản, cộng một khối NGÔN NGỮ

`build_system_prompt()` (main.py:354) chèn thêm, cạnh khối `# === BÂY GIỜ ===`:

```
# === NGÔN NGỮ ===
Ngôn ngữ trả lời: English (en). Người dùng đang viết bằng: en.
Viết TOÀN BỘ câu trả lời bằng ngôn ngữ này, kể cả tiêu đề, nhãn, đơn vị, câu cảnh báo.
Giữ nguyên không dịch: tên riêng, đường dẫn file, tên tool, khối mã, trích dẫn từ brain.
Nội dung brain viết bằng ngôn ngữ khác thì cứ đọc bình thường, chỉ TRẢ LỜI bằng ngôn ngữ trên.
```

`CLAUDE.md` luật số 5 đổi từ "**Tiếng Việt** là ngôn ngữ chính" thành "**Trả lời đúng ngôn ngữ
ghi ở khối NGÔN NGỮ**; không có khối đó thì bám theo ngôn ngữ người dùng đang dùng". Cùng cách
sửa cho `meta_tools.py:79`, `main.py:3016`, `main.py:5801`, `reminders.py:689`.

`context_compiler.dong_ho()` sinh câu theo ngôn ngữ và múi giờ đã cấu hình. Tên thứ trong tuần
lấy từ sổ đăng ký, không phải từ `_THU_VN` nhúng cứng.

**Một điểm phải nói thật, không được giấu.** Model mạnh trả lời đúng ngôn ngữ được yêu cầu dù
luật viết bằng tiếng Việt. Model yếu thì **trôi theo ngôn ngữ của prompt** - đây là chuyện thật
với các model nhỏ chạy qua Groq hay Ollama Cloud, hai đường Javis đang đấu. Cách xử: hồ sơ ngôn
ngữ có sẵn trường `nudge`, một câu viết bằng CHÍNH ngôn ngữ đích; với engine bị đánh dấu yếu thì
dán câu đó lên đầu tin nhắn cuối. Một dòng, đúng chỗ, và vẫn là dữ liệu chứ không phải mã.

**Chi phí token.** Khối NGÔN NGỮ khoảng 60 token mỗi lượt. Không đáng kể so với 30KB `CLAUDE.md`,
và không làm hỏng thêm lần đệm prompt nào: prompt hệ thống của Javis vốn đã đổi mỗi lượt vì khối
MỨC DÙNG HÔM NAY đếm theo thời gian thật (lập luận đã ghi trong docstring `dong_ho()`,
context_compiler.py:56).

### 4.6. Locale tách khỏi ngôn ngữ

Thêm vào `config._DEFAULT`:

```python
"locale": {
    "ui_lang": "vi",          # ngôn ngữ giao diện
    "reply_lang": "auto",     # auto | vi | en | ...
    "tz": "Asia/Ho_Chi_Minh",
    "currency": "VND",
    "first_day": 1,
},
```

**Bẫy đặt tên phải tránh: KHÔNG đặt file là `server/locale.py`.** Các module trong `server/` nạp
phẳng (`import config`, `import system_sync`), nên một file tên `locale.py` sẽ che luôn `locale`
của thư viện chuẩn. Đặt là **`server/localefmt.py`**, cấp `now()`, `today()`, `fmt_money()`,
`fmt_dt()`. `zoneinfo` có sẵn trong thư viện chuẩn, không thêm phụ thuộc.

Thay 6 chỗ UTC+7 nhúng cứng bằng `localefmt.now()`.

**Một chỗ phải cẩn thận: `usage_index._TZ` quyết định ranh giới NGÀY của thống kê mức dùng.** Đổi
múi giờ là đổi ý nghĩa của dữ liệu cũ. Luật: dữ liệu mới theo múi giờ đã cấu hình, dữ liệu cũ để
nguyên, và đóng dấu múi giờ vào bản ghi. Không viết lại lịch sử.

Plugin `datetime-vn` giữ nguyên slug và giữ nguyên tên tool `javis_now` / `javis_date_add` (hai
tên này đã nằm trong prompt và trong thói quen dùng). Chỉ đổi: đọc múi giờ từ cấu hình, và mô tả
plugin thôi ghi cứng "Việt Nam".

`toLocaleString("vi-VN")` ở 6 chỗ phía dashboard đổi thành hằng số `LOCALE` do `i18n/index.js`
cấp. Quy đổi VND ở `usage.js:181-199` đổi theo `currency`; tiền tệ khác VND thì bỏ luôn dòng
quy đổi thay vì bịa tỷ giá.

### 4.7. Giọng nói

- **STT** (`stt.py:82-96`): tham số `language` lấy từ `resolve_reply_lang()`. Khi `reply_lang`
  là `auto` và chưa có căn cứ nào chắc, truyền **rỗng** để Whisper tự dò. Mặc định cứng `"vi"`
  hôm nay đang chủ động làm hỏng giọng nói không phải tiếng Việt.
- **TTS**: bỏ `startswith("vi")` ở `main.py:7148`; lọc theo ngôn ngữ đang chọn. Giọng lấy từ
  `LANGS[lang].tts[provider]`. Không có giọng cho cặp ngôn ngữ-nhà cung cấp đó thì rơi về
  ElevenLabs `eleven_multilingual_v2` (đã cấu hình sẵn), rồi mới tới giọng Edge mặc định.
- Giao diện: hai nút radio cứng ở `index.html:288-306` đổi thành danh sách sinh từ sổ đăng ký.

### 4.8. Kênh và chatbot chuyên trách

- **Chatbot chuyên trách** (`chatbot_store.py`) thêm trường `ngon_ngu`, mặc định `auto`. Đây là
  ca dùng đáng tiền nhất của cả spec: bot phục vụ NGƯỜI LẠ, không phải chủ, nên ngôn ngữ của nó
  không việc gì phải theo ngôn ngữ giao diện của chủ.
- **Telegram**: ngôn ngữ theo từng cuộc chat, dò từ tin nhắn, dính theo cuộc chat.
- **Zalo**: mặc định `vi`, cho phép ghi đè.
- **CLI**: theo `reply_lang` toàn cục, cộng cờ `--lang`.
- Khối kênh (`channel_context.py`) **giữ nguyên tiếng Việt**. Đó là luật cho model, không phải
  chữ cho người dùng.

### 4.9. Skill

`skill_router.SKILL_DESC_MAX` giữ nguyên 150 ký tự, áp **cho từng ngôn ngữ**. Frontmatter được
phép khai map:

```yaml
description:
  vi: "Tiêu hoá một source thô vào Second Brain..."
  en: "Digest a raw source into the Second Brain..."
```

Dạng chuỗi phẳng vẫn hợp lệ và vẫn là dạng khuyến nghị cho skill người dùng tự viết. Router đọc
`description[lang]`, không có thì rơi về `description[vi]`, rồi tới chuỗi phẳng. **Chỉ 4 skill
hệ thống** (`javis-builder`, `ingest-source`, `query-wiki`, `lint-wiki`) khai map; skill người
dùng không đụng tới.

## 5. Thêm một ngôn ngữ mới: sổ tay

Đây là **bài kiểm tra nghiệm thu của cả spec**. Thêm tiếng Thái phải là chừng này việc, không hơn:

1. `server/lang_registry.py`: thêm một mục `th` (tên bản ngữ, hệ chữ, hư từ để dò, mã STT, giọng
   TTS, múi giờ và tiền tệ mặc định, có chia số nhiều không, câu `nudge`).
2. `dashboard/i18n/th.json`: chép `vi.json`, dịch. Thiếu key thì tự rơi về tiếng Việt, không vỡ
   giao diện.
3. `server/lexicon/th.py`: **tuỳ chọn**. Không có thì đường tắt tiết kiệm token tự tắt cho người
   dùng tiếng Thái, còn rào chắn an toàn hạ xuống tầng model phụ. Javis vẫn chạy ĐÚNG, chỉ tốn
   hơn. Viết sau khi có người dùng thật cũng được.
4. Chạy `python tests/run.py`. Bộ test đối chiếu key và test bất biến sổ đăng ký phải xanh.

**Không sửa file nào khác. Phải sửa chỗ khác nghĩa là spec này đã hỏng - sửa spec trước, đừng
sửa lén.**

## 6. Bản nhỏ nhất đo được nhu cầu

Trước khi bỏ hai tuần, có một câu hỏi hợp lý: **có nhu cầu thật không, hay đây là tính năng tự
kỷ ám thị?** Câu đó đáng trả lời bằng tiền thật chứ không bằng suy đoán. Nhưng phép thử phải
được thiết kế cẩn thận, vì bản trực giác của nó **trả về số liệu bẩn**.

### 6.1. Cái bẫy: phép thử rẻ mà kết quả sai

Bản trực giác nghe rất hợp lý: *chèn "Reply in English" vào prompt, dịch vài chục nhãn chính,
ship, có 50 người nước ngoài dùng thật thì mới đầu tư sâu.* Một tới hai ngày công.

Vấn đề: kế hoạch đó **bật tiếng Anh mà không đụng vào 13 cái cổng ở mục 2.3**. Nghĩa là 50
người dùng thử đó nhận một Javis mà:

- đường tắt tiết kiệm token nuốt câu hỏi cần dữ liệu live rồi model bịa,
- bộ bắt khai man không nổ khi Javis nói "đã gửi xong" mà chưa gửi,
- **cò ghi ký ức không kích hoạt, nên Javis không học được gì từ họ** - đúng cái làm Javis khác
  một khung chat thường,
- bot chăm khách không bao giờ được tính là bí.

Rồi anh đo ra "không có nhu cầu". **Nhưng thứ vừa đo là một sản phẩm hỏng, không phải thị
trường.** Một phép thử rẻ mà trả về âm tính giả thì tệ hơn không thử, vì anh sẽ hành động theo
nó và đóng cửa một hướng đi vì lý do sai.

### 6.2. Cách sửa, và nó rẻ hơn vẻ ngoài

**Không cần cả Phase 2.** Chỉ cần luật suy biến ở mục 4.3, rút gọn còn đúng một điều kiện:

> Phiên không phải tiếng Việt thì **tắt hết đường tối ưu, đi đường đầy đủ.**

Tắt đường tắt nhanh, tắt một-bước-chỉ-đọc. Tốn thêm token cho vài chục người dùng beta, tốn gần
như không gì để viết. Cộng một nhãn thành thật trên giao diện: *"beta, chưa tối ưu cho ngôn ngữ
này"*.

Bản nhỏ nhất vì vậy gồm:

1. Phase 0 rút gọn: `lang.py` + sổ đăng ký hai mục `vi`, `en`, ghi `lang` vào trace.
2. Khối NGÔN NGỮ trong prompt + sửa `CLAUDE.md` luật 5.
3. **Luật một dòng ở trên: phiên không phải tiếng Việt thì không đi đường tối ưu.**
4. Trường `ngon_ngu` cho chatbot chuyên trách.
5. STT và TTS theo ngôn ngữ đã chọn.

**Hai tới ba ngày thay vì một tới hai.** Đổi lại số liệu đo được đáng tin. Đánh đổi này quá hời:
một ngày công để một quyết định chiến lược không dựa trên dữ liệu rác.

Ba thứ **KHÔNG** có trong bản nhỏ nhất: dịch giao diện (không cần, xem 6.3), lớp bộ từ vựng đầy
đủ, và locale.

### 6.3. Chĩa phép thử vào đâu

Đây là chỗ dễ chọn sai, và chọn sai thì hai tuần sau mới biết.

Bản trực giác chĩa vào **chủ shop nước ngoài**: dịch giao diện, chờ người Mỹ tới. Phép thử đó
đắt (phải dịch giao diện trước mới thử được), chậm (phải có kênh phân phối ở thị trường mới), và
**đánh vào chỗ Javis yếu nhất** - ra khỏi Zalo, ra khỏi POS Việt, vào một cái chợ có hàng trăm
AI dashboard đang đánh nhau.

Chĩa đúng là vào **chủ shop Việt phục vụ khách ngoại**:

> Chủ shop Việt có chatbot chăm khách Nhật, Hàn, Trung, hoặc bán hàng xuất khẩu. Giao diện chủ
> vẫn tiếng Việt, brain vẫn tiếng Việt, Zalo vẫn Zalo. **Chỉ đổi một trường `ngon_ngu` trên con
> bot đối ngoại.**

Ba cái lợi, cái thứ ba lớn nhất:

- **Không phải dịch một nhãn giao diện nào**, vì chủ shop không bao giờ rời tiếng Việt. Bản nhỏ
  nhất bớt được nguyên hạng mục đắt nhất.
- **Đo trên tập khách đã có**, không phải đi tìm thị trường mới rồi mới đo được.
- **Đào sâu hào thay vì đổi hào.** Đây là tính năng mà đám dashboard quốc tế không đấu lại được,
  vì họ không có Zalo và không có ngữ cảnh kinh doanh Việt. Còn "dịch giao diện ra tiếng Anh rồi
  ra quốc tế" thì là bỏ lợi thế duy nhất để bước vào chỗ mình không có lợi thế nào.

Nói cho rõ, vì chỗ này hay bị gộp: **đa ngôn ngữ KHÔNG đồng nghĩa với ra quốc tế.** Có ít nhất
ba đường dùng nó, và đường thứ hai mới là đường nên thử trước:

| Hướng | Ai trả tiền | Có phải dịch giao diện không | Quan hệ với hào Zalo/POS |
|-------|-------------|------------------------------|--------------------------|
| Chủ ngoại dùng Javis | khách hoàn toàn mới | Có, toàn bộ | Bỏ hào |
| **Chủ Việt, khách ngoại** | **khách đã có** | **Không** | **Đào sâu hào** |
| Chủ Việt thích dùng UI tiếng Anh | khách đã có | Có, một phần | Trung tính |

### 6.4. Chốt ngưỡng TRƯỚC khi chạy

Phép thử chỉ có nghĩa khi con số quyết định được ghi ra **trước** lúc nhìn kết quả, nếu không
thì nhìn số nào cũng thấy hợp lý. Ngưỡng cụ thể là quyết định của chủ repo, nhưng nó phải có
hình dạng như: *"trong N tuần, có ít nhất X chủ shop bật `ngon_ngu` khác `vi` trên bot của họ và
còn bật sau hai tuần"*. Chỉ số "còn bật sau hai tuần" quan trọng hơn số lượt bật, vì bật thử
một lần là tò mò chứ chưa phải nhu cầu.

Chạm ngưỡng thì đi tiếp Phase 2 và 3. Không chạm thì dừng ở đây, và cái đã làm vẫn không phí:
luật suy biến ở bước 3 là một rào an toàn có giá trị tự thân, kể cả khi Javis mãi mãi chỉ nói
tiếng Việt.

### 6.5. ĐÃ TRIỂN KHAI (2026-08-14, trên v0.34.1)

Đợt 1 đã viết mã và xanh 226/226 test. Ghi lại đúng cái gì có và cái gì chưa, để không ai đọc
spec rồi tưởng phần chưa làm đã làm.

**Có:**

| Thứ | Ở đâu |
|-----|-------|
| Sổ đăng ký ngôn ngữ (vi, en) | `server/lang_registry.py` |
| Dò ngôn ngữ + chốt 8 mức ưu tiên + quán tính theo phiên | `server/lang.py` |
| Bộ từ vựng theo ngôn ngữ | `server/lexicon/{__init__,vi,en}.py` |
| Khối NGÔN NGỮ, **ba** điểm chèn | `main.build_system_prompt`, `context_compiler._output_contract_text`, `chatbot_runtime.build_bot_prompt` |
| Cổng đường tắt + hai cổng chỉ đọc tra bộ từ vựng | `fast_path_runtime`, `readonly_path_runtime`, `readonly_orchestrator` |
| Đồng hồ theo ngôn ngữ | `context_compiler.dong_ho(lang=)` |
| Trường `ngon_ngu` cho chatbot + ô chọn | `chatbot_store`, `chatbots.js` |
| Ô "Ngôn ngữ trả lời" ở Cài đặt | `console.js`, `POST /settings` nhánh `locale` |
| STT ba trạng thái, TTS lọc giọng theo ngôn ngữ | `stt.py`, `GET /tts/voices?lang=` |
| Test hành vi + test bất biến chống thoái lui | `test_da_ngon_ngu.py`, `test_lang_bat_bien.py` |

**Ba điểm chèn, không phải một.** Đây là chỗ bản spec đầu thiếu. Đường TIẾT KIỆM TOKEN không
đi qua `build_system_prompt`, và prompt của chatbot chuyên trách không đi qua cả hai đường kia.
Chỉ sửa `build_system_prompt` thì hai vùng còn lại mất khối NGÔN NGỮ trong im lặng - mà vùng
thứ ba đúng là ca dùng đáng tiền nhất ở mục 6.3.

### 6.6. ĐỢT 2 VÀ NỀN CỦA ĐỢT 3 (2026-08-14)

**Đợt 2 khép lại: hai cổng BẮT LỖI đã đấu vào bộ từ vựng.**

| Cổng | Ở đâu | Suy biến khi thiếu bộ từ vựng |
|------|-------|-------------------------------|
| Bắt khai man hành động | `context_compiler.DeterministicQualityGate.evaluate` | chạy HỢP mẫu của mọi bộ, rồi đánh dấu `lang_unverified` vào trace |
| Dò lời hứa suông | `background_status.detect_promise` | như trên |

Một chi tiết đáng ghi lại vì nó tiết kiệm cả một vòng luồn tham số: hai cổng này **tự dò ngôn
ngữ từ chính câu trả lời** thay vì nhận tham số từ nơi gọi. Chúng kiểm thứ model THẬT SỰ đã
viết ra, nên ngôn ngữ của văn bản đó là căn cứ đúng hơn ngôn ngữ ta đã YÊU CẦU - model vẫn có
thể trả lời sai ngôn ngữ, và đúng lúc ấy ta muốn kiểm bằng bộ từ vựng khớp với cái nó viết.
Nhờ vậy năm nơi gọi `evaluate()` không phải sửa một dòng nào.

Và `lang_unverified` KHÔNG đổi `status`: đánh trượt mọi câu trả lời tiếng Nhật chỉ vì chưa có
lexicon tiếng Nhật là phạt người dùng vì một thiếu sót của chúng ta.

**Nền của Đợt 3 đã dựng, giao diện chưa dịch xong.**

- `dashboard/i18n/index.js` - `t()`, suy biến `<đã chọn> -> vi -> key`, quét DOM qua
  `data-i18n*`, số nhiều bằng `.one`/`.other`, tự nạp lúc khởi động rồi phát `javis:i18n`.
- `dashboard/i18n/{vi,en}.json` - tầng điều hướng (rail, tiêu đề trang) và ô cài đặt ngôn ngữ.
- `console.js` - `RAIL_ITEMS`, `RAIL_GROUPS`, `VIEW_META` lấy nhãn từ từ điển qua getter, cộng
  biến đếm `i18nTick` để Alpine vẽ lại khi từ điển về hoặc khi user đổi ngôn ngữ.
- Ô **Ngôn ngữ giao diện** ở trang Cài đặt, đổi là ăn ngay không cần F5.
- `tests/js/test_i18n.mjs` - khớp key hai chiều, cấm HTML trong từ điển, cấm em dash, bắt
  trường hợp "chép nguyên tiếng Việt sang en.json", và **`I18N_MIGRATED`** là chốt chặn thoái
  lui: file đã dọn mà lấm lại chữ tiếng Việt trong mã chạy thì test đỏ ngay.

Một cái bẫy đáng ghi vì nó tốn thời gian một cách ngớ ngẩn: viết `dashboard/i18n/*.json` trong
một chú thích `//` làm hàm bóc chú thích của test hiểu `/*` là mở khối chú thích, và nó nuốt
luôn 20 dòng mã phía sau. Ba test đỏ vì một dấu sao trong câu văn.

**Chưa làm, cố ý:** phần lớn 3.520 chuỗi giao diện (mới dịch tầng điều hướng), mã lỗi cho 182
chuỗi lỗi server, locale (múi giờ, định dạng số), và `description` skill theo ngôn ngữ.

## 7. Sáu giai đoạn

Mục này là kế hoạch ĐẦY ĐỦ, chạy sau khi bản nhỏ nhất ở mục 6 đã chạm ngưỡng. Bản nhỏ nhất
chính là một lát cắt mỏng của Phase 0 và 1 cộng một mẩu của Phase 2, nên làm nó không phải là
làm thừa.

**Phase 0 - Đo và khoá (nửa ngày).** Thêm `server/lang.py`, `lang_registry.py` với đúng một mục
`vi`, thêm cụm `locale` vào cấu hình, ghi `lang` và `lang_source` vào trace. **Không đổi một
hành vi nào.** Chốt là mọi test cũ xanh nguyên.

**Phase 1 - Ngôn ngữ trả lời (2 ngày).** Khối NGÔN NGỮ, sửa `CLAUDE.md` luật 5 cùng 4 chỗ prompt
ép tiếng Việt, `dong_ho()` theo ngôn ngữ, `resolve_reply_lang()` đủ 7 mức ưu tiên, dính theo
phiên, STT và TTS theo ngôn ngữ, trường `ngon_ngu` cho chatbot. Thêm tiếng Anh vào sổ đăng ký.
**Giao diện vẫn tiếng Việt hoàn toàn.** Đây là giai đoạn phần lớn người dùng gọi là "đã có đa
ngôn ngữ", và nó là giai đoạn rẻ nhất.

**Phase 2 - Bộ từ vựng và cổng an toàn (2 tới 3 ngày).** Rút regex ra `lexicon/vi.py` nguyên
văn, viết `lexicon/en.py`, cài luật suy biến theo loại cổng, hạ tầng model phụ cho cổng bắt lỗi.
**Làm TRƯỚC phần giao diện**, vì đây là tầng hỏng trong im lặng, còn giao diện thì hỏng ra mặt.

**Phase 3 - i18n giao diện (4 tới 5 ngày, rải ra được).** Hạ tầng `i18n/index.js`, rút `vi.json`,
dịch `en.json`, di trú theo lưu lượng: chat -> rail -> Cài đặt -> phần còn lại. Mã lỗi cho lỗi
server, làm dần từng endpoint. Ô chọn ngôn ngữ trong trang Cài đặt.

**Phase 4 - Locale (1 ngày).** `localefmt.py`, thay 6 chỗ UTC+7, tiền tệ, `describe_cron` theo
ngôn ngữ, `toLocaleString` theo locale, plugin `datetime-vn` đọc múi giờ cấu hình.

**Phase 5 - Skill và tài liệu (1 ngày).** Map `description` cho 4 skill hệ thống. Dịch tay
`README.md`, `QUICKSTART.md`, `docs/01`. Viết `docs/dev/` mục "thêm một ngôn ngữ" trỏ về mục 5
của spec này.

**Thứ tự nên ra bản dùng được**: Phase 0 tới 2 thành một bản trọn vẹn (Javis trả lời đúng ngôn
ngữ, các cổng an toàn không bị vô hiệu), rồi Phase 3 theo nhịp có sức, rồi Phase 4 và 5. Tổng
khoảng hai tuần làm tập trung.

## 8. Kiểm thử

Bộ test hiện có nằm ở `tests/python`, `tests/js`, chạy qua `tests/run.py`. Thêm:

- `test_lang_resolve.py` - đủ 7 mức ưu tiên, chống nhảy qua nhảy lại, dính theo phiên.
- `test_lang_registry_invariant.py` - **quét mã tìm `lang == "vi"` hay `"vi-VN"` viết cứng ngoài
  sổ đăng ký, thấy là báo đỏ.** Đây là cái chốt giữ cho tính mở rộng không mục dần.
- `test_lexicon_parity.py` - mọi tên tập trong `lexicon/vi.py` phải có mặt ở mọi lexicon khác.
- `test_lexicon_degrade.py` - ngôn ngữ không có lexicon: cổng mở rộng quyền phải TỪ CHỐI, cổng
  bắt lỗi phải gọi model phụ hoặc đánh dấu `unverified`, không được lặng lẽ cho qua.
- `test_vi_behavior_frozen.py` - chạy lại đúng bộ ca tiếng Việt hiện có sau khi rút regex, kết
  quả phải trùng từng bit.
- `tests/js/test_i18n.mjs` - key thừa, key thiếu, cấm HTML trong từ điển, và **cấm chữ tiếng
  Việt trong file đã di trú**.
- `test_prompt_lang_block.py` - đúng một khối NGÔN NGỮ, đúng ngôn ngữ, có `nudge` khi engine yếu.

## 9. Rủi ro và bẫy

- **Cổng an toàn tắt trong im lặng.** Rủi ro lớn nhất của cả spec. Cách chống duy nhất đáng tin
  là `test_lexicon_degrade.py`, và ghi `unverified` ra trace để nhìn thấy được ngoài thực địa.
- **Dò ngôn ngữ nhảy loạn.** Người Việt gõ tiếng Việt không dấu trộn tiếng Anh là chuyện thường
  ngày. Luật hai lượt liên tiếp cộng ngưỡng tin cậy là để trị ca này; phải có test bằng câu
  trộn thật.
- **Model yếu trôi theo ngôn ngữ prompt.** Đã có `nudge`, nhưng phải thử tay trên Groq và Ollama
  Cloud trước khi tuyên bố xong Phase 1.
- **Bản dịch giao diện thoái lui.** Lượt sửa tính năng kế tiếp sẽ nhúng chuỗi tiếng Việt vào file
  đã dọn nếu không có test chặn. Danh sách `I18N_MIGRATED` phải vào từ ngày đầu Phase 3, không
  phải cuối.
- **Đổi múi giờ làm lệch thống kê cũ.** Đóng dấu múi giờ, không viết lại lịch sử.
- **Brain trộn ngôn ngữ.** Người dùng ghi chú tiếng Việt rồi hỏi bằng tiếng Anh là ca bình
  thường, không phải lỗi. Khối NGÔN NGỮ đã nói rõ: đọc ngôn ngữ nào cũng được, chỉ TRẢ LỜI theo
  một ngôn ngữ.
- **Giọng đọc thiếu.** Không có giọng thì phải nói thẳng ra giao diện, đừng đọc bằng giọng tiếng
  Việt cho một câu tiếng Nhật.

## 10. Ba câu hỏi đã tự chốt

**Tiếng Việt hay tiếng Anh làm từ điển gốc?** Chốt **tiếng Việt**. `vi.json` được rút ra từ mã
đang chạy nên đủ 100% key theo định nghĩa, và mọi ngôn ngữ khác suy biến về nó thì không bao giờ
có ô chữ trống. Lấy tiếng Anh làm gốc nghĩa là phải dịch 3.520 chuỗi TRƯỚC khi có cái gì chạy
được - trả trước toàn bộ chi phí để đổi lấy một sự gọn gàng trên giấy.

**Có tự đổi ngôn ngữ giao diện theo `Accept-Language` của trình duyệt không?** Chốt **chỉ gợi ý
lần đầu**, không tự đổi. Javis chạy trên VPS, người dùng mở từ nhiều máy nhiều trình duyệt; giao
diện tự nhảy sang ngôn ngữ khác vì hôm nay mở bằng máy khác là kiểu "thông minh" gây khó chịu.
Lần đầu chưa chọn gì thì gợi ý một dòng, chọn rồi thì nhớ theo thiết bị.

**Ngôn ngữ trả lời mặc định là `auto` hay `vi`?** Chốt **`auto`**. Hợp đồng đầu ra hôm nay đã là
`match_user` (context_compiler.py:366) và nó đang chạy tốt; đặt mặc định thành `vi` là tự tay
làm thụt lùi một hành vi đang đúng. Ai muốn ghim thì ghim theo brain hoặc theo bot.

## 11. Nguồn trong repo

- [Kiến trúc tổng quan](01-kien-truc.md) - một lượt chat chạy qua đâu
- [Spec Javis CLI](2026-08-cli-spec.md) - tiền lệ "kênh thứ ba" và bài học không nhân bản runtime
- [Spec Bot chuyên trách](2026-08-bot-chuyen-trach-spec.md) - vì sao bot phục vụ khách lạ cần
  giả định riêng
- [Spec Adaptive Context Runtime](2026-08-adaptive-context-runtime-spec.md) - Context Compiler,
  nơi hợp đồng đầu ra `match_user` đang sống
- `CLAUDE.md` - luật hành xử, mục "Nguyên tắc phản hồi" luật số 5 là chỗ phải sửa đầu tiên
