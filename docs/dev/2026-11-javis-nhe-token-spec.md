# Javis Nhẹ: vì sao tốn token và thiết kế cắt giảm trên gói thuê bao

Spec này viết ngày 10/11/2026 (bản 0.526.1), sau khi nhiều người dùng báo Javis "ngày càng đốt token": mở hạn mức
được 40 phút, gần như không làm gì mà hết 30%. Phần 1 đến 4 là điều tra, phần 5 trở đi là thiết kế.

Mỗi con số đều ghi rõ là **đo** (có nguồn) hay **ước** (suy từ số đo, chưa chạy thật).

**Trạng thái (10/11/2026):** chủ repo đã chốt hướng đi sau khi đọc bản đầu. Mục 0 ghi các quyết định đó và phần đã
làm trong cùng PR. Mục 5 trở đi là bản thiết kế gốc; chỗ nào bị quyết định ở mục 0 thay thế thì mục 0 thắng.

## 0. Đã chốt và đã làm

Nguyên tắc chủ repo đặt ra: **không cắt chữ trong prompt của lượt chat** (sợ ảnh hưởng chất lượng trả lời), và
**không thêm cài đặt nào cho người dùng**. Vì vậy phần "làn nhẹ L1" ở mục 5.3 và "prompt ăn kiêng" ở mục 5.6 KHÔNG
nằm trong lộ trình chính nữa; chi phí được cắt ở ba thừa số còn lại: việc nền, model của việc nền, và các lượt chỉ
cần chữ.

Đã làm trong PR này:

| Việc | Ở đâu | Thay cho mục |
|---|---|---|
| Model việc nền có chế độ **Tự động**, là mặc định. Nhà cung cấp theo MAIN; hai model: `light` cho việc Javis tự làm, `mid` cho việc chủ giao | `server/auto_background.py`, `server/model_routing.py` (`background_spec`), `server/aux_engine.py` (`tier_for_tag`) | 5.4.2 |
| Chọn hai model đó KHÔNG theo bảng tên: model chính đọc danh sách (kèm mô tả) của chính nhà cung cấp một lần, được phép trả "không chắc"; id ngoài danh sách bị bỏ; không chọn được thì dùng model của MAIN | `auto_background.choose`, `main._auto_background_tick` | mới |
| Chỉ chọn lại khi danh sách model của nhà đó đổi (chữ ký danh sách, so mỗi ngày và lúc khởi động). Model chủ tự tay chọn không bao giờ bị ghi đè | `auto_background.signature`, `model_routing.background_auto` | mới |
| Tự học mặc định chỉ ký ức và wiki; máy đã cài được tắt skill một lần | `server/learn.py` (`DEFAULT`, `_MIGRATIONS`) | 5.4.3 (một phần) |
| Tự học nổ **15 phút sau sự kiện cuối cùng** của brain (lượt chat, việc nền xong, khách nhắn chatbot), một mẻ cho cả cuộc trò chuyện; bỏ luật "sau mỗi 3 lượt". Mỗi mẻ đọc đúng các lượt mới kể từ mẻ trước, phần vượt ngân sách xếp lại cho mẻ kế | `learn.LearnFeature._should_fire`, `touch`, `_build_digest`, `run_once` | 5.4.3 |
| **Bỏ trần ngày** của tự học (40 mẻ, 15 triệu token): chủ repo chốt "người dùng nhiều người dùng ít", một con số chung không hợp | `learn.LearnFeature._rate_check` | thay P0.2 |
| Lượt chỉ cần chữ đi trần: prompt riêng, `disallowed_tools` có `"*"` | `main._reply_policy_sandbox_engine(bare=True)` | P0.1, 5.4.1 |
| Cửa sổ 5 giờ của gói dùng từ 80% thì việc Javis tự làm nghỉ tới lúc reset | `plan_limits.side_pause`, `main._side_work_paused` | thay ngân sách nền 5.4.4 |

Vì sao bỏ ý "khớp theo tên dòng model": bản nháp đầu đề nghị tìm `mini`, `haiku` trong tên. Chủ repo chỉ ra ngay là
dòng model của gói ChatGPT đã mang tên khác, tức luật theo tên sai từ ngày đầu và sẽ sai lại mỗi lần hãng đổi tên.
Tín hiệu duy nhất không lỗi thời là danh sách và mô tả do chính nhà cung cấp trả về cho tài khoản đó.

Ba lượt chỉ cần chữ vẫn giữ preset (`bare=False`): lượt của thành viên nhóm, lượt Resonance, và vòng cải tiến skill.
Phiên và bằng chứng kiểm định của chúng được dựng trên preset nên chưa đổi trong đợt này.

**Bước tiếp theo đã làm trong cùng PR:** hai bậc "nhẹ" và "giữa" ở bảng trên chỉ còn là điểm xuất phát. Mỗi việc nền
tự leo hay tự hạ bậc theo kết quả của chính nó và theo ý định chủ nói trong chat. Thiết kế ở
`2026-11-so-diem-viec-nen-spec.md`.

Còn mở, theo thứ tự đáng làm:

1. **Việc nền chỉ ăn hạn mức thừa:** dồn việc Javis tự làm về cuối cửa sổ 5 giờ, khi còn dư.
2. **Giảm số vòng thay vì giảm chữ:** ghim tool hay dùng, gọi trước tool chỉ-đọc khi bộ dò đoán chắc.
3. **Một tiền tố cache chung** cho mọi phiên của một brain (mục P0.3), và dòng giờ rời đầu prompt biên dịch (P0.4).
4. **Tách "chat, việc bạn giao, Javis tự làm"** trong vòng tròn hạn mức, cần ghi tên việc vào usage event trước (P0.5).
5. **Mẻ tự học thành một lượt chữ** thay cho phiên agentic đọc file (mục 5.4.3), để mỗi mẻ rẻ hơn nữa.

Chưa đo trên engine thật (môi trường viết mã không có `claude` hay `codex` đăng nhập): lượt chỉ cần chữ sau khi đi
trần, và câu trả lời của model chính khi đọc danh sách model thật. Cả hai đều có đường lui: lỗi hay trả lời không
dùng được thì việc nền chạy model của MAIN như trước.

## 1. Kết luận ngắn

1. **Người dùng nói đúng.** Trên gói Claude Code, một lượt chat của Javis mang khoảng 57.000 đến 66.000 token ngữ
   cảnh cố định cho MỖI vòng gọi model, trong khi chính Claude Code trần là khoảng 27.700 và một lượt hỏi không
   tool chỉ cần 183.
2. **Phần tốn nhất không nằm ở lượt chat mà nằm ở những việc Javis tự chạy.** Tự học bật sẵn, nổ sau mỗi 3 lượt chat
   và 10 phút sau lượt cuối, chạy bằng model mặc định (đắt nhất) của gói. Số đo thật: 12,5 triệu token trong một ngày.
   Đây là lời giải thích khớp nhất cho "không làm gì mà hết 30%".
3. **Gốc rễ là một giả định sai nằm ở ba chỗ trong mã: "gói thuê bao thì không tính tiền theo token".** Vì giả định đó
   mà mọi cơ chế tiết kiệm đã xây (Adaptive Context Runtime, model việc nền, xoay mạch) đều nhường engine thuê bao,
   đúng nơi người dùng cảm nhận hạn mức rõ nhất.
4. **Thiết kế đề xuất ("Javis Nhẹ")**: coi hạn mức gói là tiền; cho gói thuê bao chạy theo làn nhẹ giống engine API
   (nhân luật nhỏ cộng tool của hub) và chỉ leo lên làn đầy đủ khi lượt thật sự cần shell hay sửa code; đưa mọi việc
   nền về model rẻ, một lượt chữ, có ngân sách ngày. Kỳ vọng: phần cố định mỗi vòng giảm khoảng 10 đến 15 lần ở lượt
   chat thường, việc nền mặc định giảm hơn 20 lần.

## 2. Số đo

### 2.1 Đã đo (có nguồn)

| # | Thứ được đo | Con số | Nguồn |
|---|---|---|---|
| D1 | "chào em" qua `claude`, prompt trần, không tool | 183 token vào | `server/main.py:3756-3760` |
| D2 | "chào em" qua `claude`, preset `claude_code` cùng mọi schema tool và danh sách skill | 27.665 token vào | như trên |
| D3 | Lượt đầu một khung chat mới của Javis trên Claude Code | 8.907 đọc cache + 47.834 đến 57.320 ghi cache, tức 57.000 đến 66.000 | issue #975, đo từ `~/.claude/projects` |
| D4 | Một câu chào trên Claude Code hiện ở khung chat | "60k token" | `server/main.py:22810` |
| D5 | Số lần mở phiên Claude Code trong một ngày của một người dùng | 74 lần, phần ghi lại cache chiếm khoảng 30% mức dùng | issue #975 |
| D6 | System prompt Javis, brain mới tinh | 41.666 ký tự (CLAUDE.md 29.013, khối kênh 8.195) | `tests/python/test_prompt_budget.py`, chạy lại 10/11 |
| D7 | System prompt Javis, brain giả lập 140 skill, 15 agent, 150 ghi nhớ | 61.455 ký tự (bộ nhớ 16.730, skill 4.502) | script đo trong phiên điều tra |
| D8 | Tỉ lệ ký tự trên token của CLAUDE.md với tokenizer Claude | khoảng 2,7 (28.599 ký tự ra khoảng 10.500 token) | `tests/python/test_prompt_budget.py:80-81` |
| D9 | Lượt Codex trong cùng một hội thoại | 36k, 83k, 191k, 412k, 552k token vào; model chỉ viết 266 đến 1.496 token | `server/compaction.py:88-108` |
| D10 | Tự học, một ngày thật | 12,5 triệu token (ước lượng cũ ghi 395 nghìn) | `server/learn.py:439-442`, `docs/22-tu-hoc.md:176` |
| D11 | Curator (mặc định tắt), mỗi vòng | 2,46 triệu tăng lên 5,22 triệu sau ba tuần | `server/learn.py:886-888` |
| D12 | Một đợt auto-learning chạy toàn bằng Opus | 176 lượt gọi, quy đổi 3,02 USD; với model nền Haiku còn 0,24 đến 1,10 USD | `docs/superpowers/evidence/2026-10-27-auto-learning-cost.json` |
| D13 | Một lần gọi `javis_search_tools` trên brain thật của chủ repo | trả về khoảng 9.000 đến 10.000 ký tự, riêng mô tả `javis_use_skill` nhúng 20 mô tả skill | gọi thử trong phiên điều tra |

Từ D6, D7 và D8: phần Javis nối thêm vào mỗi vòng gọi là khoảng 15.000 token (brain mới) tới hơn 22.000 token
(brain dùng lâu). Cộng D2 ra đúng khoảng của D3, nên ba nguồn đo khớp nhau.

### 2.2 Một lượt chat thật tốn bao nhiêu (ước, từ các số đo trên)

Mỗi vòng gọi tool là một request mới, đọc lại toàn bộ phần cố định. `tokens_in` Javis ghi là TỔNG mọi vòng, gồm cả
đọc cache (`server/claude_sdk_engine.py:412-413`).

| Loại lượt trên gói Claude Code | Số vòng | Token vào (ước) |
|---|---|---|
| Câu chào, đi đường tắt Siêu tiết kiệm | 1 | 500 đến 1.500 |
| Hỏi thường, không tool, đường đầy đủ | 1 | khoảng 60.000 |
| Hỏi số liệu qua hub (tìm tool, gọi tool, trả lời) | 3 | khoảng 180.000 đến 200.000 |
| Việc nhiều bước (5 đến 10 lần gọi tool) | 6 đến 11 | 400.000 đến 800.000 |
| Gợi ý câu tiếp theo sau MỖI lượt, khi không có key Groq | 1 phiên `claude` riêng | khoảng 20.000 đến 28.000 |
| Một mẻ tự học (sau mỗi 3 lượt) | vòng agentic đọc file | 150.000 đến 500.000 |

Phần lớn là đọc cache. Anthropic không công bố đọc cache tính bao nhiêu vào hạn mức gói; các báo cáo của người
dùng mâu thuẫn nhau. Điều chắc chắn: ghi cache và phiên mở nguội thì tính đủ, và mọi việc nền của Javis đều là
phiên nguội.

## 3. So với app gốc

| | App Claude / ChatGPT | Claude Code trần | Javis hôm nay (gói Claude Code) |
|---|---|---|---|
| Ngữ cảnh cố định mỗi vòng | vài nghìn đến khoảng 20.000 token (ước, không đo được từ ngoài) | 27.665 (đo, D2) | 57.000 đến 66.000 (đo, D3) |
| Số vòng gọi model cho một câu hỏi số liệu | 1 đến 2 | 2 | 3 (thêm vòng tìm tool) |
| Lệnh gọi phụ sau mỗi lượt | không | không | 1 (gợi ý câu tiếp theo) |
| Việc tự chạy khi người dùng ngồi yên | không | không | tự học, chấm điểm skill, nhịp trợ lý, loop, nhắc hẹn |
| Model cho việc phụ | model nhỏ của hãng | không có | model mặc định của gói, tức model đắt nhất |

Một ngày 10 lượt hỏi số liệu (ước): app gốc khoảng 0,1 đến 0,3 triệu token; Javis khoảng 1,2 đến 2 triệu cho chat,
0,2 đến 0,3 triệu cho gợi ý, 0,5 đến 2 triệu cho ba bốn mẻ tự học. Tức gấp cỡ 10 lần trở lên, và ngày đo thật D10
cho thấy riêng tự học đã có thể lên 12,5 triệu.

Lưu ý công bằng: Javis làm được việc mà app gốc không làm (nối POS, Zalo, lịch, chạy nền). Vấn đề không phải là
Javis tốn hơn, mà là nó tốn như nhau cho câu "doanh thu hôm nay bao nhiêu" và cho việc sửa cả một repo.

## 4. Bảy nguyên nhân gốc

**N1. Tự học bật sẵn, nổ dày, chạy đắt, và trần không chặn được tiền.**
- Mặc định `enabled: True, mode: auto` (`server/learn.py:425-427`). Mọi lượt chat không tầm thường đều xếp hàng
  (`server/main.py:18646`).
- Nổ khi đủ 3 lượt, hoặc 10 phút sau lượt cuối, hoặc 3 phút nếu lượt "đậm" (`server/learn.py:633-647`). Chính mốc
  10 phút tạo ra cảnh "ngồi yên mà hạn mức vẫn tụt".
- Mỗi mẻ là một phiên `claude` agentic mới, mang trọn `build_system_prompt` bản không ổn định
  (`server/learn.py:1134-1142`), cộng digest tới 24.000 ký tự, chỉ mục nhớ tới 16.000, chỉ mục wiki tới 20.000.
  Có skill đề xuất thì thêm phiên thứ hai để phản biện (`server/learn.py:1858-1867`).
- Trần `fork_day 40` và `token_day 15M` được kiểm SAU khi phiên đã chạy và chỉ hạ việc ghi file về chạy thử
  (`server/learn.py:506-518`, `1846` so với `1875`). `docs/22-tu-hoc.md:178-180` xác nhận phần phân tích luôn chạy.

**N2. Mỗi vòng gọi trên Claude Code gánh hai bộ luật chồng nhau.** Preset `claude_code` cùng tool native (D2) cộng
prompt Javis nối thêm (`server/claude_sdk_engine.py:797-804`), cộng `setting_sources` user, project, local và MCP có
sẵn của máy ở mức Toàn quyền (`server/claude_sdk_engine.py:887`, `server/main.py:5245`; máy chủ repo từng đo 85 MCP,
`docs/dev/2026-10-toc-do-luot-chat-spec.md`). Skill bị liệt kê hai lần: bản mirror `.claude/skills` cho Claude Code
tự đọc và khối router trong prompt.

**N3. Giả định "gói thuê bao không tính tiền theo token" ở ba chỗ.**
- `server/main.py:19031-19035`: vì thế giữ nguyên CLAUDE.md cho engine thuê bao; mức Tối ưu chỉ đổi chỉ mục nhớ và
  danh sách skill.
- `server/aux_engine.py:188-190`: model việc nền mặc định rỗng, tức model mặc định của `claude`, và phanh ngân sách
  bỏ qua gói thuê bao.
- `server/compaction.py:84-105`: mạch Claude Code, Codex chỉ xoay khi lượt trước vượt 1.000.000 token.

**N4. Việc nền nào cũng là phiên nguội.** Nhắc hẹn, việc Kanban, loop, bước workflow đều dựng
`build_system_prompt(brain)` bản có đồng hồ và mức dùng (`server/reminders.py:1144-1153`, `server/tasks.py:759-768`,
`server/self_improve.py:845-892`), nên mỗi lần chạy ghi lại cache toàn bộ khoảng 60.000 token rồi mới bắt đầu
vòng tool. Lỗi #975 mới chỉ được vá cho làn chat.

**N5. Lệnh gọi chỉ-cần-chữ vẫn mang nguyên bộ đồ nghề.** Gợi ý câu tiếp theo (bật sẵn từ 07/11/2026,
`server/next_prompt.py:43`), người phán xử, phân loại sự cố, huấn luyện thói quen, nhịp trợ lý đều đi qua
`_reply_policy_sandbox_engine` (`server/main.py:2405-2418`): preset `claude_code` cộng một danh sách cấm khoảng 19
tool theo tên, không phải `["*"]` như đường tắt đã chứng minh là rút được từ 27.665 xuống 183 token.

**N6. Mạch dài và mồi lại nặng.** Ngưỡng xoay 1 triệu token nghĩa là trên thực tế không bao giờ xoay. Sau một lượt
đường tắt, mạch native bị xoá và lượt kế mồi lại transcript với trần 300.000 ký tự (`server/main.py:19140`,
`server/compaction.py:30`). Nghỉ quá giờ sống của cache (1 giờ trên gói) thì lượt kế ghi lại cache cả mạch.

**N7. Prompt trùng lặp và dễ vỡ cache.** Khối kênh 8.195 ký tự tiếng Việt lặp lại nhiều luật đã có trong CLAUDE.md
(không hứa suông, luật lịch, luật trình bày). Chỉ mục nhớ được nạp tới 20.000 ký tự mỗi lượt
(`server/main.py:816`). Ở mức mặc định Siêu tiết kiệm, prompt biên dịch cho engine thuê bao đặt dòng giờ theo phút
ngay sau Core Contract (`server/context_compiler.py:523-526`), đứng TRƯỚC CLAUDE.md; nếu nhánh này được dùng ở đa số
lượt thì bản vá #975 bị vô hiệu ở đúng mức mặc định. Điểm này cần một phép đo xác nhận (mục 9).

## 5. Thiết kế "Javis Nhẹ"

### 5.1 Bốn nguyên tắc

1. **Hạn mức là tiền.** Mọi quyết định tiết kiệm áp cho gói thuê bao y như cho API key.
2. **Trả theo nhu cầu của lượt, không trả theo những gì Javis đang có.** Thêm skill, thêm MCP, thêm ghi nhớ không
   được làm lượt "doanh thu hôm nay" đắt lên.
3. **Việc nền không được tiêu nhiều hơn chủ.** Có ngân sách ngày, model rẻ, và trần phải chặn TRƯỚC khi gọi model.
4. **Leo thang chứ không đoán sai.** Làn nhẹ không đủ thì tự leo lên làn đầy đủ ngay trong lượt; không bao giờ trả
   lời thiếu chỉ để tiết kiệm.

### 5.2 Điểm hạn mức: một đơn vị chi phí cho cả gói thuê bao

Thêm `usage_parsers.quota_points(event)`: token vào mới x1, ghi cache x1,25 (x2 với cache 1 giờ), đọc cache x0,1,
token ra x5, nhân hệ số model lấy theo tỉ lệ giá trong `usage_pricing.json` (hiện là Haiku 1, Sonnet 2 đến 3, Opus 5, Fable 10).
Đây là mô hình thận trọng vì hãng không công bố công thức; hệ số để trong cấu hình và được hiệu chỉnh bằng
`rate_limit_event` mà `plan_limits.py` đã thu sẵn.

Ba chỗ ở N3 đổi sang hỏi điểm hạn mức thay vì hỏi "có phải API key không".

### 5.3 Ba làn thực thi cho engine thuê bao (phần đột phá)

Ý tưởng: bảy engine API của Javis vốn đã chạy rất gọn (nhân luật nhỏ cộng 5 tool lazy của hub, 500 vòng). Engine
thuê bao tốn vì nó luôn khoác cả bộ Claude Code hay Codex. Vậy thì cho gói thuê bao chạy đúng kiểu engine API, qua
chính binary `claude` (vẫn là đường chính chủ, không đụng token đăng nhập), và chỉ khoác bộ đầy đủ khi cần.

| Làn | Dùng khi | Gửi gì mỗi vòng | Cố định mỗi vòng (ước) |
|---|---|---|---|
| L0 Tức thì | chào hỏi, hỏi kiến thức, không cần dữ liệu | capsule, không tool (đã có: `_claude_sub_stream(tiet_kiem=True)`) | 0,5 đến 1,5 nghìn |
| L1 Nhẹ | hỏi số liệu, lịch, Zalo, đọc ghi file trong brain, đặt nhắc hẹn, giao việc: phần lớn việc của một trợ lý kinh doanh | nhân luật (mục 5.6) cộng tool hub: `javis_search_tools`, `javis_run_tool`, ba tool file | 4 đến 6 nghìn |
| L2 Đầy đủ | chạy lệnh máy, sửa code, trang Coding, skill cần Bash, sub-agent | như hôm nay, sau khi gọt ở mục 5.6 | 40 đến 45 nghìn |

**L1 trên gói Claude Code** dựng bằng những thứ SDK đã có (`claude-agent-sdk` 0.2.116):
- `system_prompt` trần qua file (đã có `_raw_prompt_through_file`, `server/main.py:3710`);
- `tools=[]`, SDK đổi thành `--tools ""`, tắt hẳn tool native nên không còn schema nào của chúng;
- `mcp_servers` chỉ có hub kèm `X-Javis-Vault` để hub phát tool file (đúng cách `_claude_sub_stream_tools` đang làm
  cho bot, `server/main.py:3848-3880`), `strict_mcp_config`, và không nạp `setting_sources`;
- bọc `_options` từ ngoài như `_raw_prompt_through_file`, không sửa `claude_sdk_engine.py` (file đó bị ghim bởi bằng
  chứng kiểm định native).

**L1 trên gói ChatGPT** là đường `engine.responses_with_mcp` đã chạy cho bot chuyên trách
(`server/main.py:24903`), thay cho việc mở Codex CLI.

**Chọn làn và leo thang:**
- Trước lượt, bằng mã, không gọi model: bộ phân loại của đường tắt (`server/fast_path_runtime.py`) quyết L0; phiên
  Coding, tệp đính kèm cần xử lý bằng lệnh, hoặc skill khai cần Bash thì vào thẳng L2; còn lại vào L1.
- Trong lượt: L1 có thêm đúng một tool nhỏ `javis_escalate(reason)`. Model gọi nó khi cần shell hay sửa code. Cổng
  dừng vòng L1 và chạy lại lượt ở L2, mồi bằng transcript kèm danh sách tool hub đã gọi trong lượt (lấy từ nhật ký
  hub) để không làm lại hành động ra ngoài.
- Làn dính theo hội thoại và chỉ đi lên: hội thoại đã lên L2 thì ở L2 cho tới khi nghỉ quá giờ sống của cache, lúc
  đó lượt kế được xét lại từ đầu vì đằng nào cache cũng nguội.
- Mỗi làn một mạch native riêng (system prompt của mạch Claude Code đông cứng từ lượt đầu, xem
  `server/context_compiler.py:113-118`). Đổi làn thì mồi lại từ SQLite bằng `compaction.bootstrap_prompt` với trần
  nhỏ (tóm tắt cộng 6 tin gần nhất), không phải trần 300.000 ký tự.
- Người dùng luôn có nút ghim "Đầy đủ" cho một hội thoại, và dòng nhỏ dưới câu trả lời ghi làn đã chạy.

Rủi ro chính: L1 không còn 29.000 ký tự luật của CLAUDE.md nên hành vi có thể lệch. Giảm rủi ro bằng mục 5.6 (luật
giao đúng lúc), bằng canary có sẵn (`allocation_basis_points`), và bằng Quality Gate đang chạy ở chế độ quan sát.

### 5.4 Việc nền có ngân sách

1. **Lệnh gọi chỉ-cần-chữ đi trần.** `_reply_policy_sandbox_engine` đổi sang prompt trần cộng `tools=[]` (hoặc
   `disallowed_tools=["*"]`). Áp cho gợi ý câu tiếp theo, người phán xử, phân loại sự cố, huấn luyện thói quen, nhịp
   trợ lý, viết lại lời đọc. Từ khoảng 20.000 đến 28.000 token xuống dưới 1.000 mỗi lần.
2. **Model việc nền mặc định là model rẻ nhất của chính gói đó** (`haiku` trên gói Claude, model mini trên gói
   ChatGPT) thay cho chuỗi rỗng. Ai đã tự chọn thì giữ nguyên. Việc người dùng tự hẹn ở mức Toàn quyền (nhắc hẹn làm
   việc, loop) vẫn được chọn model riêng trên từng việc.
3. **Tự học đổi nhịp và đổi cách chạy:**
   - nhịp: gom theo phiên, nổ khi brain đã yên 30 phút và có ít nhất 4 lượt đáng học, tối đa 4 mẻ một ngày; câu
     "ghi nhớ giúp" vẫn học ngay như cũ;
   - cách chạy: một lượt chữ duy nhất, không vòng đọc file. Digest và hai chỉ mục vốn đã được nhét sẵn vào prompt
     (`server/learn.py:674-688`, `809`, `928`); thứ còn thiếu thì mã Python tra bằng `memory_index` trước khi gọi;
   - trần ngày kiểm TRƯỚC khi gọi model; chạm trần thì bỏ mẻ, không chạy thử;
   - kỳ vọng mỗi mẻ khoảng 25.000 đến 35.000 token trên model rẻ, cả ngày dưới 150.000, so với 12,5 triệu ở D10.
4. **Ngân sách nền theo ngày, tính bằng điểm hạn mức.** Mặc định: việc Javis tự khởi (tự học, chấm skill, nhịp trợ
   lý, gợi ý) không vượt 15% điểm đã tiêu trong ngày và không vượt một trần tuyệt đối. Chạm trần thì các việc tự khởi
   nghỉ tới hôm sau; việc người dùng tự hẹn vẫn chạy nhưng báo lên chuông. Trang Mức dùng thêm một thẻ "Nền hôm nay:
   X điểm trên Y".
5. **Việc nền dựng prompt ổn định** (`stable=True`, đồng hồ đưa vào tin nhắn) và mặc định chạy ở L1; chỉ loop hay
   việc Kanban khai cần lệnh máy mới lên L2.
6. **Gợi ý câu tiếp theo:** vẫn bật khi có key nhanh (Groq) hoặc khi đường trần ở trên đã áp; không bao giờ mở một
   phiên `claude` đầy đủ cho nó nữa.

### 5.5 Giữ mạch gọn

- Xoay mạch theo KÍCH THƯỚC NGỮ CẢNH của vòng đầu trong lượt (lấy từ usage của vòng đầu, không phải tổng mọi vòng),
  ngưỡng đề xuất 120.000 token, thay cho tổng 1.000.000.
- **Luật cache nguội:** lượt tới sau khi cache đã hết hạn (1 giờ trên gói, 5 phút với API key) mà mạch dài hơn
  40.000 token thì mở mạch mới từ bản tóm tắt cộng 6 tin gần nhất. Ghi lại 200.000 token cache để nói tiếp một câu
  là khoản tốn vô ích nhất hiện nay.
- Lượt L0 không xoá mạch native nữa: câu hỏi và câu đáp của nó được ghi thành một dòng ghi chú ở đầu tin nhắn kế tiếp.
- Kết quả tool đi qua hub có trần ký tự theo làn và trả kèm `result_view`; phần dài cất vào evidence store (đã có,
  `server/evidence_store.py`) và model lấy thêm bằng một lần gọi khi cần.

### 5.6 Prompt ăn kiêng (áp cho cả L1 lẫn L2)

- **Luật giao đúng lúc.** Luật chỉ liên quan tới một nhóm tool thì đi kèm KẾT QUẢ của lần đầu gọi tool đó trong
  mạch, không nằm trong system prompt. Ví dụ luật "đủ điều kiện mới tạo lịch" đi cùng `javis_schedule`, luật Zalo đi
  cùng `zalo_*`, luật plugin đi cùng `javis_plugin`. Hub đã là điểm nghẽn duy nhất của mọi lần gọi tool nên đây là
  một bảng `tool hoặc nhóm tool -> đoạn luật` cộng một dòng mã ở `_handle_one`.
- **Nhân luật cho L1** khoảng 6.000 ký tự: danh tính, không bịa số liệu, hai lối đúng khi gặp việc dài, cách trình
  bày của kênh, ngôn ngữ, xưng hô. Viết bằng tiếng Anh (D8 và chú thích trong `test_prompt_budget.py` cho thấy tiếng
  Anh ít token hơn). Thêm trần cho nó vào `tests/python/test_prompt_budget.py`.
- **Khối kênh** bỏ các luật trùng với CLAUDE.md, chỉ giữ dữ kiện của kênh. Mục tiêu từ 8.195 xuống dưới 2.500 ký tự.
- **Bộ nhớ:** hồ sơ luôn nạp cộng tối đa 6 ghi nhớ tra theo câu hỏi (Phase 8 đã có), đặt ở cuối prompt hoặc trong
  tin nhắn để không vỡ cache. Bật mặc định cho engine thuê bao.
- **Skill:** một danh sách duy nhất. Trên Claude Code L2 dùng danh sách native và bỏ khối router; trên L1 dùng
  `javis_use_skill` với mô tả không nhúng danh sách skill.
- **`javis_search_tools`:** kết quả trả tên, một dòng mô tả và các tham số bắt buộc; schema đầy đủ chỉ cho 2 tool
  đứng đầu. Mô tả của chính nó thôi liệt kê từng plugin nội bộ, chỉ đếm theo nhóm (D13).
- **Dòng giờ theo phút** rời khỏi đầu prompt biên dịch (N7), đi vào tin nhắn như bản vá #975.

### 5.7 Nhìn thấy được

- Dòng dưới mỗi câu trả lời: làn đã chạy, số vòng, token mới và token đọc cache tách riêng (khung `_ctx_frame` đã có).
- Trang Mức dùng: tách "phần của bạn" (câu hỏi, lịch sử, kết quả tool) với "phần của Javis" (luật, tool, việc nền),
  và cảnh báo khi phần nền vượt ngân sách.
- Việc nền nào cũng ghi `execution` vào `usage-events.jsonl` (trường đã có) để bảng "cái gì ăn hạn mức" gọi được
  tên: tự học, gợi ý, loop nào, nhắc hẹn nào.

## 6. Kỳ vọng sau khi làm (ước, phải qua cổng đo ở mục 9)

| Thứ | Hôm nay | Sau | Giảm |
|---|---|---|---|
| Cố định mỗi vòng, lượt hỏi số liệu (L1) | 57.000 đến 66.000 | 4.000 đến 6.000 | 10 đến 15 lần |
| Một lượt hỏi số liệu 3 vòng | khoảng 180.000 đến 200.000 | khoảng 15.000 đến 25.000 | 8 đến 12 lần |
| Lệnh gọi chỉ-cần-chữ (gợi ý, phán xử) | 20.000 đến 28.000 | dưới 1.000 | hơn 20 lần |
| Tự học mỗi ngày | tới 12,5 triệu (đo) | dưới 150.000 trên model rẻ | hơn 50 lần |
| Việc nền mở phiên nguội | khoảng 60.000 ghi cache mỗi lần | 4.000 đến 6.000 (L1) | 10 lần |
| Lượt đầy đủ L2 | 57.000 đến 66.000 | 40.000 đến 45.000 | khoảng 30% |
| Nói tiếp sau khi nghỉ hơn 1 giờ, mạch 200.000 token | ghi lại 200.000 | khoảng 10.000 | 20 lần |

## 7. Lộ trình

Mỗi pha là các PR nhỏ, mỗi PR một mảnh `changelog.d/`, có test, và có số đo trước sau ghi trong mô tả PR.

**Pha 0: cắt phần lãng phí thuần tuý, không đổi hành vi (làm ngay).**
- P0.1 Lệnh gọi chỉ-cần-chữ đi trần (mục 5.4.1). File: `server/main.py` quanh `_reply_policy_sandbox_engine`.
- P0.2 Trần tự học chặn trước khi gọi model; đếm mẻ lúc mở phiên chứ không phải lúc commit (`server/learn.py`).
- P0.3 Việc nền dựng prompt ổn định (`server/reminders.py`, `server/tasks.py`, `server/self_improve.py`,
  `server/learn.py`, bước workflow ở `server/main.py:12231`).
- P0.4 Dòng giờ rời đầu prompt biên dịch của engine thuê bao, kèm test so hai prompt của hai phiên liền nhau.
- P0.5 Ghi tên việc nền vào usage event để đo được các pha sau.

**Pha 1: việc nền có ngân sách.** Điểm hạn mức (5.2), model nền mặc định rẻ (5.4.2), tự học một lượt chữ và nhịp mới
(5.4.3), ngân sách nền ngày và thẻ trên trang Mức dùng (5.4.4). Cần chủ repo chốt ba mặc định ở mục 8.

**Pha 2: làn L1 cho gói Claude Code.** Canary theo `allocation_basis_points`, bắt đầu với hội thoại mới trên
dashboard, đo chất lượng bằng Quality Gate và bằng tỉ lệ leo thang. Sau đó tới Telegram, Zalo, rồi việc nền.

**Pha 3: L1 cho gói ChatGPT, giữ mạch gọn (5.5).**

**Pha 4: prompt ăn kiêng (5.6).** Luật giao đúng lúc trước, rồi gọt khối kênh, rồi CLAUDE.md.

Thứ tự này đặt phần chắc ăn và ít rủi ro lên trước: Pha 0 và Pha 1 đã xử lý nguyên nhân khớp nhất với lời phàn nàn
(N1, N4, N5) mà chưa đụng tới chất lượng câu trả lời.

## 8. Việc cần chủ repo quyết (đã trả lời 10/11/2026, xem mục 0)

1. Model việc nền mặc định: **đã chốt** Tự động, hai bậc, chọn theo danh sách của nhà cung cấp.
2. Nhịp tự học: **đã chốt** 15 phút sau sự kiện cuối cùng, không có trần ngày.
3. Gợi ý câu tiếp theo: **giữ bật**, đã đi trần và chạy trên model nhẹ.
4. Làn L1 làm mặc định: **không làm**, vì cắt luật của lượt chat có thể ảnh hưởng chất lượng trả lời.

## 9. Điều chưa chắc và cách đo

- **Đọc cache tính bao nhiêu vào hạn mức gói:** chưa có nguồn chính thức. Đo bằng cách chạy một kịch bản cố định
  trước và sau từng pha rồi so thanh hạn mức `rate_limit_event` (`server/plan_limits.py`).
- **`--tools ""` cộng MCP trên bản `claude` người dùng đang cài:** D1 chứng minh `disallowed_tools=["*"]` rút sạch
  schema; cần đo lại một lượt L1 thật (kỳ vọng dưới 6.000 token vào ở vòng đầu) trước khi mở canary.
- **Prompt biên dịch có thật sự được dùng ở đa số lượt Claude Code không (N7):** đếm sự kiện
  `context_sources.*` trong `runtime.db` trên một máy thật, và so `cache_creation_input_tokens` của dòng assistant đầu
  tiên giữa hai phiên liền nhau như issue #975 đã làm.
- **Chất lượng ở L1:** bộ câu hỏi vàng tổng hợp đã có cho Phase 5 đến 8; thêm 30 câu việc kinh doanh thật (POS, lịch,
  Zalo, nhắc hẹn) và chấm tỉ lệ leo thang, tỉ lệ trả lời sai làn.
- **Codex CLI:** chưa đo phần cố định của riêng nó; D9 chỉ cho tổng. Cần một phép đo như D1 và D2 cho `codex`.

## 10. Người dùng làm được gì ngay hôm nay (chưa cần bản mới)

1. **Models, khối Model việc nền:** chọn model rẻ (Haiku trên gói Claude, hoặc một key Groq, DeepSeek, OpenRouter
   free). Đây là câu trả lời cho "dùng mô hình nào chạy việc nền cho đỡ tốn".
2. **Tự học:** tắt, hoặc chuyển khỏi chế độ Tự ghi nếu không cần; bật lại khi đã có bản Pha 1.
3. **Gợi ý câu tiếp theo** (menu "+" ở ô chat): tắt nếu không có key Groq.
4. **Mở khung chat mới cho việc mới.** Mạch dài là thứ đắt nhất trên gói thuê bao, và hiện Javis chưa tự xoay.
5. **Loop và nhắc hẹn làm việc:** giãn nhịp; việc chỉ cần canh một trang web thì dùng `javis_watch` (không gọi model).
6. Xem trang Cài đặt, Mức dùng, cột "Nền (loop/lịch)" để biết phần nền đang chiếm bao nhiêu.
