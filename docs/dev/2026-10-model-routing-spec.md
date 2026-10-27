# Spec: thứ tự model, nhiều tài khoản và model việc nền

Ngày chốt: 27/10/2026. Chủ repo duyệt từng ý qua bản duyệt giao diện (artifact "Trang Model Javis",
bản 14). Tài liệu này là nguồn chân lý khi triển khai: mọi quyết định dưới đây đã chốt, đừng đổi
khi chưa hỏi lại chủ repo.

## 1. Mục tiêu

Người dùng sắp một danh sách nhà cung cấp đã đăng nhập theo thứ tự muốn dùng. Mỗi nhà có thể có
nhiều tài khoản hoặc nhiều API key. Javis dùng hết tài khoản của nhà trên rồi mới sang nhà dưới.
Việc nền có model riêng, cố định, không chạy theo MAIN. Trang Models gọn lại còn hai phần chính:
**Thứ tự dùng** và **Model việc nền**.

## 2. Các quyết định đã chốt

### 2.1. Thứ tự dùng

1. Phần **Thứ tự dùng** chỉ có các nhà **đã đăng nhập / đã kết nối**. Thẻ trên cùng là **MAIN**,
   các thẻ sau là **Dự phòng 1, 2, 3...**
2. Đổi thứ tự bằng **kéo thả** (chuột: giữ phần đầu thẻ rồi kéo; cảm ứng: giữ biểu tượng 6 chấm,
   hoặc giữ yên phần đầu thẻ khoảng 350ms) hoặc bấm nút **⇅ Đảo** nằm giữa hai thẻ liền nhau.
3. Mỗi thẻ có hai chip giống hệt khung chat: **chip model** (chấm xanh, tên, ▾) và **chip Effort**
   (mức, ▾). Bấm đầu thẻ hoặc chip model mở bảng chọn model của nhà đó. Chip Effort mở thanh trượt
   6 nấc như khung chat.
4. Thẻ đang được chat dùng mà không phải MAIN thì có nhãn **ĐANG DÙNG**. Viên tài khoản đang dùng
   tô xanh (chat) hoặc tím (việc nền).
5. Nhà **chưa kết nối** không hiện. Cuối trang chỉ có một nút **＋ Kết nối thêm nhà cung cấp (N)**,
   bấm mới mở danh sách để đăng nhập. Kết nối xong thì nhà đó **vào cuối** phần Thứ tự dùng.
   Gỡ tài khoản cuối cùng (ngắt kết nối) thì nhà đó rời phần Thứ tự dùng.
6. Chọn model của một nhà khác ở **khung chat** (giữ nguyên hành vi hiện tại: ghim cho phiên và
   đổi luôn model chính) thì thẻ nhà đó **tự lên đầu** thành MAIN. Các thẻ còn lại giữ thứ tự
   tương đối, MAIN cũ thành Dự phòng 1.

### 2.2. Nhiều tài khoản trong một nhà

1. Mỗi thẻ có danh sách tài khoản (gói) hoặc key (API) đánh số **1, 2, 3...**, có nút lên/xuống,
   kéo thả, nút ⋯ (Tắt/Bật, Đăng nhập lại hoặc Đổi key, Gỡ) và nút **＋ Thêm tài khoản / ＋ Thêm key**
   viền nét đứt giống trang Kết nối.
2. **Tự xoay vòng tuần tự:** dùng tài khoản 1 tới khi hết lượt, sang 2, ... hết cả nhà thì sang
   thẻ kế. Tài khoản 1 hồi lượt thì quay lại dùng nó trước. Không chia đều từng câu.
3. Thêm nhiều tài khoản gói thuê bao: người dùng **tự chịu rủi ro**. Form thêm hiện một dòng nhắc
   giọng nhẹ nhàng (chủ repo, 0.352.0): có nguy cơ bị khoá nhưng Javis chưa ghi nhận trường hợp
   nào, gặp thì báo nhà phát triển qua Issues. Không bắt tích ô xác nhận.
4. Nhiều key API trong một nhà được hỗ trợ đầy đủ. Không bắt khai nhóm hạn mức: Javis thử lần
   lượt, key đang nghỉ thì bỏ qua ngay.
5. Antigravity CLI chỉ 1 tài khoản (token trong keyring của máy), thẻ ghi rõ lý do, không có nút thêm.
6. Tài khoản mới vào **cuối** danh sách của thẻ đó. Gỡ một tài khoản chỉ đăng xuất đúng tài khoản đó.

### 2.3. Model và Effort

1. Mỗi thẻ nhớ **model + Effort riêng**, lưu cùng nhau. Thay cho ô "Mức suy luận" chung (bỏ ô đó).
2. Nhãn Effort giữ đúng khung chat: Off, Light, Medium, High, Extra, Ultra (`eff.*`).
3. Model không có mức đã chọn thì chạy ở **nấc gần nhất** model đó có (cách đều thì lấy nấc thấp).
   Chip hiện ví dụ `Extra → High`. **Lựa chọn đã lưu không bị sửa**, đổi lại model cũ là về mức cũ.
4. **Off = không gửi tham số suy luận.** Model bắt buộc suy luận thì tự chạy mức mặc định của nó.
5. Model không có suy luận thì chạy như Off.
6. Javis Core khi chưa tự chọn mức thì lấy Effort của thẻ MAIN. Agent có mức riêng thì giữ nguyên.

### 2.4. Model việc nền

1. Ô **Model việc nền** giữ kiểu ô hiện tại (tên model màu cam, tên nhà, nút **Đổi model ▾**),
   nằm **ngay dưới** phần Thứ tự dùng, có thêm chip Effort. **Không có** "Về như MAIN".
2. **Lần đầu** (người mới, hoặc lúc nâng cấp mà chưa đặt): Javis chọn sẵn **cấu hình mặc định
   của nhà cung cấp** (nhà đầu tiên đã đăng nhập): model mặc định và Effort mặc định của model đó.
   Sau đó **giữ cố định**, đổi MAIN không kéo theo.
3. Thứ tự chạy của việc nền: **Model nền → Dự phòng 1 → Dự phòng 2 → ... → MAIN sau cùng**.
   Mỗi bước sau bước đầu chạy **cấu hình mặc định lúc mới đăng nhập của nhà đó** (không phải model
   người dùng chọn cho chat). Bỏ bước trùng (cùng nhà, cùng model). Nhà chạy bằng gói (Claude Code,
   ChatGPT, Grok Build, Antigravity) chỉ xuất hiện **một lần**: hạn mức của gói tính theo tài khoản chứ
   không theo model, thử lại cùng gói bằng model khác chỉ tốn thêm một lượt gọi hỏng.
4. Trang **không** hiện chuỗi thứ tự này. Chỉ khi model nền hết lượt mới hiện một dòng:
   "Haiku 5.5 đang hết lượt, việc nền chạy tạm ChatGPT · GPT-5.5."
5. Bảng chọn model nền: **máy tính** dùng bảng hai cột như hiện tại (nhà | model); **điện thoại**
   (≤ 600px) dùng bảng kiểu chip model của khung chat (ô tìm, tên nhà viết hoa bấm để mở/thu, ✓).
   Cả hai **chỉ liệt kê nhà đã kết nối**.
6. Mọi bảng chọn (popover) **mở lên trên** như khung chat; chỉ lật xuống khi phía trên không đủ chỗ;
   chiều cao tự co theo chỗ trống, danh sách dài thì cuộn bên trong.

### 2.5. Telegram

1. **Bỏ ô "Model Telegram"** trên trang Models.
2. Mặc định mọi cuộc trò chuyện Telegram **đi theo MAIN**: đổi model trên web là Telegram đổi theo.
3. Gõ `/model <tên>` **trong** một cuộc trò chuyện Telegram thì ghim model đó **cho riêng cuộc
   trò chuyện đó** (không đổi MAIN, không đụng web). `/model theo` gỡ ghim. `/model ghim` ghim vào
   model đang chạy.
4. Ghim hết lượt thì cuộc trò chuyện đó đi tiếp theo Thứ tự dùng như chat.
5. Chủ repo đã biết và chấp nhận rủi ro: thử model trên web sẽ kéo Telegram của cả nhà theo, trừ
   cuộc trò chuyện đã tự ghim.

### 2.6. Khung chat

1. Giữ nguyên hành vi: chọn model ở chip khung chat = ghim cho phiên + đổi MAIN. Chip Effort ở
   khung chat = Effort của thẻ MAIN.
2. Thay đổi duy nhất: bảng chọn model ở khung chat **chỉ liệt kê nhà đã kết nối** (bỏ dòng ổ khoá
   và "+ Thêm key").

### 2.7. An toàn khi chuyển

1. Chỉ chuyển sang tài khoản hoặc nhà kế tiếp khi lượt hỏng **trước lần gọi công cụ đầu tiên**.
   Đã gọi công cụ rồi mà hỏng thì dừng và báo, không chạy lại (tránh gửi tin, đăng bài hai lần).
   Luật này áp dụng cho cả việc nền mức `full` (trước đây `full` không có dự phòng).
2. Chuyển chỉ đổi đường đang chạy của lượt đó, **không sửa** thứ tự hay model đã lưu.
3. Không chạy song song nhiều đường để lấy kết quả nhanh nhất.

## 3. Dữ liệu (`settings.json`, mục `model`)

Thêm mới, tên trường tiếng Anh:

```
model.order        = ["anthropic-cli", "openai-oauth", "groq", ...]   # thứ tự dùng, [0] là MAIN
model.profiles     = { "<provider>": {"model": "...", "reasoning": "off|low|...|ultra"} }
model.accounts     = { "<provider>": [ {"id": "acc_xxxx", "label": "...", "enabled": true,
                                         "key": "<mã hoá>"            # nhà API
                                         "home": "accounts/<id>"      # nhà CLI (giai đoạn sau)
                                       } ] }
model.auxiliary    = {"provider": "...", "model": "...", "reasoning": "..."}   # đã có, thêm reasoning
model.telegram_chats = { "<chat key>": {"provider": "...", "model": "..."} }  # ghim từng chat
model.routing_version = 1
```

Quy tắc đồng bộ để không phải sửa ~150 chỗ đang đọc trường cũ:

- `model.main` luôn = `{order[0], profiles[order[0]].model}`. Chỉ một hàm ghi cả hai.
- `model.reasoning` luôn = `profiles[order[0]].reasoning`.
- Trường key cũ của mỗi nhà API (`openai_api_key`, `groq_api_key`...) luôn = key của **tài khoản
  bật đầu tiên** của nhà đó. Các đường phụ (giọng nói, team, Lark...) vẫn đọc trường cũ.
- Key trong `model.accounts` mã hoá như các secret khác (`_SECRET_PATHS` thêm đường cho phần tử
  danh sách).
- Trạng thái nghỉ (hết lượt) của từng tài khoản lưu ở `STATE_DIR/account_rest.json` khi nhà cung
  cấp báo rõ giờ mở lại; còn lại để trong bộ nhớ tiến trình như hiện nay.

## 4. Chuyển đổi cấu hình cũ (chạy một lần, chạy lại an toàn)

Chạy khi đọc settings mà `routing_version` < 1:

1. `order` = [MAIN hiện tại] + các nhà khác **đang kết nối** theo thứ tự `PROVIDER_DEFS`.
2. `profiles[MAIN]` = model chính + `reasoning` hiện tại. Nhà khác: model mặc định của nhà, Effort
   mặc định.
3. Mỗi nhà API đang có key: tạo **một** tài khoản từ key đó (id ổn định, tên "Key 1"). Không nhân
   đôi khi chạy lại.
4. `auxiliary`: giữ nguyên nếu đã đặt provider khác rỗng; nếu rỗng thì lấy cấu hình mặc định của
   nhà đầu tiên trong `order`. Thêm `reasoning` mặc định của model đó.
5. Ghim Telegram chung (`model.telegram`) nếu có: chép thành ghim riêng cho **mọi** cuộc trò chuyện
   Telegram đang biết (`telegram.chat_id` và bảng phiên Telegram), rồi xoá ô chung.
6. Không bật lại thứ gì người dùng đã tắt. Không xoá trường cũ nào ngoài `model.telegram`.

## 5. Ánh xạ vào mã

| Việc | Chỗ sửa |
|---|---|
| Đọc/ghi thứ tự, hồ sơ, tài khoản; chuyển đổi | module mới `server/model_routing.py` (không import main) |
| `model.main` đồng bộ khi đổi thứ tự hay đổi chip | `main._set_main_model` gọi `model_routing.promote(...)` |
| Chọn đường cho chat | `main._chat_provider` / `_chat_provider_for_session` hỏi `model_routing.chat_route(...)` |
| Key theo tài khoản | `main._provider_key` + `aux_engine.api_key_for` hỏi tài khoản bật, không nghỉ |
| Chuỗi việc nền | `aux_engine.swap` dựng chuỗi từ `model_routing.background_chain(...)`, bỏ chuỗi cứng (Claude, model chính, OpenRouter free) |
| Dừng chuyển sau khi đã gọi công cụ | `aux_engine._FallbackChain.query` nhớ đã thấy sự kiện `tool_call` |
| Telegram ghim theo chat | `main._chat_provider_kenh` nhận chat key; lệnh `/model` ghi `telegram_chats` |
| Nấc Effort gần nhất | hàm chung `model_routing.nearest_effort(level, supported)`; Off không gửi |
| Lưu từ trang Models | `POST /settings` mục `model` nhận `order`, `profiles`, `accounts`, `auxiliary.reasoning` |
| Giao diện | `dashboard/console.js` (tab Cloud của trang Models), CSS trong `console.css`, chữ trong `i18n/vi.json` + `en.json` |
| Bảng chọn ở khung chat | `dashboard/model-list.js`: bỏ nhà chưa kết nối |

## 6. Phân kỳ phát hành

Mỗi bản là một PR, CI xanh thì merge, mỗi bản một số phiên bản.

1. **0.350.0: dữ liệu, chuyển đổi, bộ điều phối.** `model_routing.py`, chuyển đổi, đồng bộ trường
   cũ, chuỗi việc nền mới (model nền → dự phòng mặc định → MAIN), luật dừng sau `tool_call`,
   nhiều key API có xoay vòng, Telegram ghim theo chat, Effort gần nhất, chip khung chat chỉ hiện
   nhà đã kết nối. Kèm test.
2. **0.351.0: giao diện trang Models** theo bản duyệt: Thứ tự dùng (kéo thả, ⇅, chip model/Effort),
   danh sách key của thẻ API, ô Model việc nền (bảng chọn hai kiểu, mở lên trên), ẩn nhà chưa kết
   nối, bỏ ô Telegram, ô Main Model và ô Mức suy luận chung. Server gửi kèm `model.routing` (thứ tự,
   profile từng thẻ, model nền, thẻ chat và việc nền đang chạy) để trang không tự suy.
   Chưa làm ở bản này: chip `Extra → High` (2.3.3) cần bảng mức suy luận của từng model, mà danh
   sách model hiện chỉ có tên. Tới khi có bảng đó, chip hiện đúng mức đã chọn và engine tự hạ mức
   như trước. Danh sách tài khoản cho gói (CLI) đi cùng bản 3.
3. **0.353.0: nhiều tài khoản cho CLI** (chủ repo bảo làm cả ba cùng lúc). Codex (`CODEX_HOME`),
   Grok (`GROK_HOME`) và Claude Code (`CLAUDE_CONFIG_DIR`), mỗi tài khoản thêm một thư mục
   `STATE_DIR/accounts/<id>/<codex|grok|claude>/`; tài khoản 1 giữ nguyên thư mục mặc định của CLI.
   Mã ở `server/plan_accounts.py`. Đăng nhập tài khoản thêm: ChatGPT bằng luồng device code của
   Javis (token ghi vào `auth.json` của thư mục đó), Grok bằng `grok login --device-auth`, Claude
   bằng `claude auth login` (link rồi dán mã). Hết lượt: tài khoản đó nghỉ (`mark_rest`), tài
   khoản kế chạy; chỉ khi không còn tài khoản nào thì thẻ mới tính là hết lượt (`_PIN_LIMITED`).
   Chưa đi theo tài khoản (ghi rõ trong hướng dẫn): đồng hồ hạn mức, tạo ảnh, giọng nói và các
   đường ChatGPT không qua Codex CLI vẫn dùng tài khoản 1. Claude trên macOS giữ token trong
   Keychain; Javis coi tài khoản là đã đăng nhập khi thấy lượt đăng nhập xong (file đánh dấu).
4. **0.354.0: chat tự chuyển khi hết lượt.** Lượt chat hỏng vì hết lượt trước khi có chữ hoặc công
   cụ nào thì chạy lại ngay bằng đường kế tiếp, kèm một dòng "Đang dùng ChatGPT vì Claude hết lượt".
   Hỏng giữa chừng thì dừng, có nút "Chạy lại". Trước bản này, chat vẫn chọn đường còn lượt ngay
   từ đầu lượt (bản 1).
   Cách làm: `_SendProxy` của lượt đếm chữ đã stream và công cụ đã gọi (dòng nén mạch, co ngữ cảnh
   của Javis không tính), giữ lại khung lỗi tới cuối lượt khi chưa có gì. Cuối `_do_turn`, lỗi hết
   lượt (gói: `_limit_frame`; API: `limit_exceeded` không phải "co nhỏ" hoặc lỗi 429/quota, key đó
   nghỉ qua `_note_api_limit`) mà chưa có gì thì `_chat_next_route` chọn đường kế (tài khoản/key kế
   cùng thẻ, rồi thẻ kế, bỏ thẻ đã thử), bỏ các khung đã giữ, không lưu câu báo; `run_turn` gửi khung
   `reroute` (dòng "Đang dùng...") rồi chạy lại, tối đa 3 lần. Hỏng giữa chừng: giữ câu dở, thẻ
   limit_resume lý do `partial` (không tự chạy, chỉ nút Chạy lại ngay). Telegram: `_tg_answer` lặp
   lại `_tg_answer_engine` khi lõi trả câu hết lượt và chưa có dòng "⚙" nào; bot chuyên trách không
   đổi đường. Test: `tests/python/test_chat_doi_duong.py`.

## 7. Tiêu chí nghiệm thu

- Nâng cấp từ bản cũ: chat, Telegram, việc nền chạy đúng model như trước; chạy chuyển đổi hai lần
  không nhân đôi tài khoản hay đổi thứ tự.
- Đổi model ở chip khung chat: thẻ nhà đó lên đầu, `model.main` và trang Models khớp nhau.
- Tài khoản 1 đang nghỉ: chat và việc nền dùng tài khoản 2 cùng nhà trước khi sang nhà kế.
- Việc nền: model nền hết lượt thì chạy dự phòng bằng cấu hình mặc định của nhà đó, MAIN sau cùng.
- Engine việc nền đã gọi công cụ rồi mới hỏng: không chạy lại bằng engine khác.
- Telegram: `/model x` trong chat A không đổi chat B, không đổi web. Web đổi MAIN thì chat chưa ghim
  đổi theo.
- Effort: chọn Extra rồi đổi sang model chỉ có tới High thì chạy High; đổi lại thì về Extra.
  Off không gửi tham số nào.
- Bảng chọn model ở khung chat không còn nhà chưa kết nối.
- Key không xuất hiện trong log, nhật ký, export hay vault.

## 8. Ngoài phạm vi

Cân bằng tải, luân phiên chia đều từng câu, tự chọn model theo nội dung câu hỏi, tự đổi model để
tối ưu giá, model riêng cho từng tài khoản, thứ tự riêng cho từng kênh khác ngoài Telegram.
