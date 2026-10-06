# Kiểm chứng Javis Resonance MVP

Báo cáo này ghi những gì đã chạy thật cho từng mốc của [kế hoạch MVP](../superpowers/plans/2026-10-06-resonance-00-mvp.md). Mỗi mục tách rõ phần chạy với engine giả và phần chạy với engine thật. Điều gì chưa kiểm được thì ghi là chưa kiểm.

## M1: đường chạy engine và receipt do host quan sát (06/10/2026)

### Nền mã và môi trường

| Mục | Giá trị |
|---|---|
| Commit nền | `origin/main` = `7d264236b61e10077dc7833c1b063076023ea7bb` (0.83.2), fetch ngày 06/10/2026 |
| Nhánh, PR | `claude/resonance-mvp-m1`, PR #566 (nháp), phiên bản xí chỗ 0.84.0 |
| Commit pilot cuối | `ba404185a0ef066b3a6d2922a5ebe5c38235a131` (sạch, không có thay đổi chưa commit trong `server/`) |
| Head khi viết báo cáo | `5162dfab`: commit sau pilot chỉ sửa thư mục tạm của engine giả trong test, không đổi đường chạy pilot |
| Máy | Windows 11 Pro 10.0.26200 |
| Python | 3.12.10, `.venv` của checkout gốc `D:\Project\Javis-OS` |
| Claude Code CLI | `~/.local/bin/claude`, đăng nhập bằng gói thuê bao |
| Engine việc nền đang chọn | `anthropic-cli`, model `sonnet` |
| Bộ não chính | `anthropic-cli`, model `claude-opus-5-5` |
| Key OpenRouter | có trong cài đặt thật (không chép sang pilot, xem Giới hạn) |

Checkout gốc `D:\Project\Javis-OS` đang ở nhánh cũ `codex/restore-chat-colors`, chậm hơn main 121 commit. Toàn bộ khảo sát dưới đây đọc mã trên nhánh M1, tức là main 0.83.2.

### Các điểm tích hợp đã dò trên mã thật

| Điểm | Mã thật làm gì | Dùng cho M1? |
|---|---|---|
| `aux_engine.swap` | Mức dưới full dựng `_FallbackChain`: engine đã chọn, Claude, bộ não chính, OpenRouter free. Mức full không có chuỗi, nhưng Codex chạy toàn quyền | Dùng ở mức suggest, rồi chỉ giữ mắt đầu |
| `aux_engine.strip_tools` | Lột hub và MCP của engine API, Codex, Grok; bỏ Antigravity và loại lạ, lùi về engine Claude gốc. **Không** gỡ công cụ native của Codex và Grok | Dùng, kèm bộ chọn chặt (xem dưới) |
| `main._reply_policy_sandbox_engine` | Claude trong thư mục trống, `allowed_tools` cố ý không khớp công cụ nào, MCP trống, cấm thêm công cụ native | Dùng, thêm tham số `cwd_name` để có thư mục trống riêng `resonance_cwd` |
| `claude_sdk_engine.map_message` | `ResultMessage` lỗi mà vẫn có chữ được chuyển thành `final` thường, mất cờ lỗi | Sửa: `final` mang thêm `is_error`, `subtype` (chỉ thêm khoá) |
| `main._workflow_agent_helpers`, `main._run_workflow_step` | Agent chạy với `cwd` là brain và có công cụ, dành cho workflow | Không dùng: cấp quyền rộng hơn một lượt chỉ chữ cần |
| `agent_runtime.AgentRunner` | Chỉ nhận khi `agent_canary` bật và slug nằm trong danh sách | Không phải đường live: trong cài đặt thật `allocation_basis_points = 0`, `allowed_slugs = []`. Không bật |
| `workflow_runtime.WorkflowCanary` | Tương tự | Không phải đường live: `allocation_basis_points = 0`. Không bật |
| `evidence_store.EvidenceStore.put` | Cần `TurnTrace` của `context_runtime`, mã hoá artifact | Chưa nối ở M1, thuộc M3 |
| `self_improve`, `mcp_hub` | Loop dựng Claude rồi swap; hub công cụ | Không sửa |

### Đường đã chốt

- `resonance.GoalDeps.run_once(goal, prompt, action_id) -> ActionReceipt`.
- Engine do `main._resonance_engine` dựng: engine Claude trong thư mục trống, swap theo engine việc nền ở mức `suggest`, `strip_tools`, rồi `resonance.pick_text_only_link`.
- Bộ chọn chỉ nhận mắt đầu khi đủ cả hai điều kiện: đúng provider người dùng đã chọn, và có cơ chế chỉ chữ đã kiểm. M1 có hai cơ chế: Claude với cổng `can_use_tool` (`allowed_tools` có giá trị không khớp công cụ nào), và engine API với `no_tools`. Codex và Grok còn công cụ native nên bị chặn trước khi gọi. `text_only` chỉ là `true` khi được nhận.
- Model chỉ sinh chữ. Host ghi đầu ra vào `output_root` của mục tiêu, tên file là `action_id`, rồi đọc lại byte vừa ghi để tính SHA-256.
- Receipt ghi: trạng thái, engine thật sự chạy, đường dẫn và hash đầu ra, usage, số lần gọi công cụ, mã lỗi. Trường usage nào engine không báo thì để vắng; không có số liệu nào thì `usage` là `None`.
- `final` mang `is_error` thì lượt đó thất bại (`engine_result_error`), giữ usage, không ghi file.
- Đầu ra vượt 200.000 ký tự thì thất bại (`output_too_large`), không cắt âm thầm.
- Hạn mức: giữ một chỗ trước khi gọi. Dừng trước lúc gọi model thì trả chỗ lại.
- Chạy lại cùng `action_id` bị từ chối với `action_exists` và không gọi model.
- Chưa có nơi nào ngoài test gọi `_resonance_engine`. Resonance vẫn tắt với người dùng.

### Sửa theo review PR #566

| Mục | Lỗi | Sửa | Test chứng minh |
|---|---|---|---|
| P1-1 | `ResultMessage(is_error=True)` có chữ đi qua `map_message` thành `final` thường, receipt ghi `succeeded` | `map_message` thêm `is_error`, `subtype` vào `final`; `run_once` coi đó là `engine_result_error` | `ResultMessage` thật của SDK qua `map_message` thật: lượt lỗi `failed`, không file, giữ usage, tính 1 lượt; lượt `success` vẫn `succeeded` |
| P1-2 | Bộ chọn nhận Codex, Grok và khai `text_only=true` dù chúng còn công cụ native; với `JAVIS_CODEX_SANDBOX=off` Codex còn bỏ cả sandbox | Chỉ nhận Claude có `allowed_tools` hoặc engine API có `no_tools`; còn lại chặn trước khi gọi | Codex dựng bằng `aux_engine.swap` và `_build_codex` thật (cả `auto` và `off`, xác nhận `sandbox is None` ở `off`), Grok bằng `_build_grok` thật: đều bị chặn, `text_only=false`, `run_once` không tốn lượt. Claude thiếu `allowed_tools` cũng bị chặn |
| P2-1 | Usage của Grok (`input_tokens`/`output_tokens`) ra 0; `final` chỉ có `cost_usd` bị bịa token bằng 0 | Chuẩn hoá tên khoá theo engine; trường thiếu để vắng | `GrokCLI._usage` thật cho 9028/54; `final` chỉ có cost cho đúng `{"cost_usd": 0.02}`; `final` trống số liệu cho `None` |
| P2-2 | Đầu ra quá 200.000 ký tự bị cắt âm thầm mà vẫn `succeeded` | Trả `output_too_large`, không ghi file | 200.000 ký tự cộng `IMPORTANT_TAIL`: `failed`, không file, giữ usage |
| Báo cáo | Pilot chỉ ghi hash "khớp", test pilot chưa tự tính lại hash | Nhánh pilot tự tính SHA-256 trên byte đọc từ đĩa và kiểm cấu trúc đầu ra; xuất bằng chứng có prompt, đầu ra, hash, commit, bỏ đường dẫn cá nhân | [`resonance-mvp-m1-pilot.json`](resonance-mvp-m1-pilot.json) |

Trong lúc sửa, test Grok mới tự gây một lỗi: `strip_tools` ghi `.grok/config.toml` vào `cwd` của engine, và engine giả có `cwd=None` nên file rơi vào gốc repo, làm `test_ignore_files.py` đỏ. Đã xoá file rỗng đó (chưa từng được git theo dõi) và cho engine giả một thư mục tạm (commit `5162dfab`).

### Kết quả với engine giả

```
python tests/run.py resonance_mvp_integration -v
  [ 1/1] ok   test_resonance_mvp_integration.py
1/1 xanh
```

73 kiểm tra xanh, không gọi model. Thứ tự TDD: test vào trước và đỏ vì chưa có module; ba test đối soát hạn mức thêm sau đỏ trước khi sửa; 11 test theo review đỏ trước khi sửa.

Các nhóm đã kiểm:

- **Thành công:** host ghi file, SHA-256 khớp đúng byte trên đĩa, file dùng LF, usage lấy từ `final`.
- **Usage:** engine API, Grok, `final` chỉ có cost, `final` trống số liệu.
- **Lặp `action_id`:** model chỉ được gọi một lần, không tốn thêm lượt.
- **Hết hạn mức:** không dựng engine, không gọi model.
- **Thất bại không ghi file:**
  - engine trả lỗi;
  - Claude kết thúc lỗi mà vẫn có chữ (qua `map_message` thật);
  - mất đăng nhập nhưng trả `final`;
  - đua làm mới token;
  - gọi công cụ trong lượt chỉ chữ;
  - đầu ra rỗng;
  - không có `final`;
  - đầu ra quá dài;
  - engine chưa sẵn sàng;
  - factory báo chặn hoặc ném lỗi;
  - quá giờ.
- **Đối soát hạn mức:** dừng trước lúc gọi model thì trả chỗ, đã gọi model thì tính một lượt.
- **Vùng ghi chưa cấp và `action_id` lạ:** bị chặn trước khi dựng engine.
- **Bộ chọn, chạy trên `aux_engine.swap` và `strip_tools` thật:**
  - có key OpenRouter thì giữ đúng Claude, bỏ mắt sau;
  - không có chuỗi thì giữ nguyên Claude;
  - Antigravity bị lùi về Claude thì chặn;
  - OpenRouter giữ mắt API đã tắt công cụ;
  - Codex (sandbox `auto` và `off`) và Grok, dựng bằng builder thật, bị chặn;
  - Claude thiếu `allowed_tools` bị chặn.

Các test dùng chung bộ ánh xạ SDK và engine việc nền cũng chạy xanh sau khi sửa:

```
python tests/run.py sdk_engine claude_ket_thuc_luot aux_engine aux_fallback tao_file_tu_chat resonance
6/6 xanh trong 21 giây
```

### Kết quả pilot thật

Lệnh chạy, với hai đường dẫn đặt theo máy:

```
JAVIS_RESONANCE_PILOT=1 JAVIS_RESONANCE_PILOT_SETTINGS=D:/Project/Javis-OS/server/settings.json JAVIS_RESONANCE_PILOT_CALLS=1 python tests/python/test_resonance_mvp_integration.py
```

- **Đầu vào:** một danh sách việc mô phỏng ghi rõ là không có thật, yêu cầu một ghi chú Markdown có tiêu đề `# Việc đang dở` và đúng ba gạch đầu dòng. Prompt nguyên văn nằm trong file bằng chứng.
- **State:** `JAVIS_STATE_DIR` là thư mục tạm. Settings tạm chỉ chứa khối chọn engine (`auxiliary`, `main`, `engine`, `claude_model`), không có khoá nào. Không ghi gì vào state thật.
- **Hạn mức:** đã chạy ba lần, tổng cộng 3 lượt gọi model trên trần 5 lượt được cho phép. Mỗi lần dùng đúng 1 lượt; lượt chạy lại cùng id không gọi model.

| | Lần 1 | Lần 2 | Lần 3, code sau review |
|---|---|---|---|
| Commit | `24611b4b` cộng `main.py` chưa commit | `2404fc70` | `ba404185`, sạch |
| Trạng thái receipt | `succeeded` | `succeeded` | `succeeded` |
| Engine thật sự chạy | `anthropic-cli` / `sonnet` / `ClaudeSDK` | như lần 1 | như lần 1, `text_only=true` |
| Gọi công cụ quan sát được | 0 | 0 | 0 |
| SHA-256 tính lại từ byte trên đĩa | khớp (kiểm tay) | khớp (kiểm tay) | khớp (test tự kiểm) |
| Đúng cấu trúc yêu cầu | đúng (đọc tay) | đúng (đọc tay) | đúng (test tự kiểm) |
| Thời gian lượt | khoảng 7,9 giây | 5,96 giây | 6,26 giây |
| Token vào / ra (Claude Code tự báo) | 17.893 / 421 | 17.888 / 197 | 17.893 / 240 |
| `cost_usd` (Claude Code tự báo) | 0,0758 | 0,0203 | 0,0207 |
| Chạy lại cùng `action_id` | `action_exists`, không gọi model | như lần 1 | như lần 1 |

Bằng chứng của lần 3 nằm ở [`resonance-mvp-m1-pilot.json`](resonance-mvp-m1-pilot.json): commit, prompt, receipt, lượt chạy lại, hạn mức, SHA-256 tính trên đĩa và toàn văn đầu ra. File được ghi ở dạng JSON thoát ký tự (`\uXXXX`), vì đầu ra của model có dấu em dash mà repo này không cho phép xuất hiện nguyên dạng. Đường dẫn cá nhân đã được bỏ, chỉ giữ tên file đầu ra. SHA-256 đầu ra lần 3: `c690255823b0f391209f951ff5d4c06a3e097dff9303a09ca3ac2db578142ad3`.

**Kết luận M1:** trên máy này có một đường chạy được. Đường đó là engine việc nền người dùng đã chọn (Claude Code, sonnet), dựng qua `aux_engine` ở chế độ chỉ chữ có cơ chế chặn công cụ thật, và trả về một receipt mà host quan sát được. Đây là kết quả của một lượt chỉ chữ trên dữ liệu mô phỏng, chưa phải bằng chứng cho một vòng mục tiêu đầy đủ.

### Giới hạn và những gì chưa kiểm

1. **Chỉ gọi thật engine Claude.** Engine API mới được kiểm qua bộ chọn với cấu hình giả. Codex và Grok bị chặn có chủ đích cho tới khi có cơ chế chỉ chữ cho công cụ native của chúng.
2. **Pilot không có key OpenRouter.** Trong pilot, swap không dựng mắt OpenRouter nên không có mắt nào để bỏ. Trường hợp "có chuỗi dự phòng thì chỉ giữ mắt đầu" mới được kiểm bằng `aux_engine.swap` thật với cài đặt giả.
3. **Đầu ra của model có dấu em dash.** Ở M1 file chỉ nằm trong thư mục tạm. Từ M3, khi host ghi đầu ra vào brain của người dùng, cần một tiêu chí hoặc bước kiểm cho luật cấm em dash. Không sửa chữ của model một cách âm thầm.
4. **`cost_usd` không phải tiền bị trừ.** Đây là con số Claude Code tự báo, trên gói thuê bao là số quy đổi. Phần lớn khoảng 17.900 token vào là system prompt mặc định của Claude Code.
5. **Cộng dồn usage chỉ đúng cho engine được nhận.** Claude phát một `final`, engine API không công cụ phát một `usage` cho một vòng. Engine phát số tổng lặp lại nhiều lần (như Grok) phải xử lý riêng trước khi được nhận.
6. **Chống chạy trùng còn khe hở.** Cơ chế hiện dựa vào file đầu ra theo `action_id`. Nó chưa chống gọi lại model khi lượt trước thất bại trước lúc ghi file, và chưa chống trùng giữa hai tiến trình. M3 thay bằng khoá và idempotency trong SQLite.
7. **Trạng thái `uncertain` chưa dùng.** Lượt chỉ chữ không có tác động ra ngoài.
8. **Receipt chưa vào EvidenceStore.** `evidence_ids` hiện rỗng. M3 nối phần này.
9. **`requested_provider` là spec sau phanh ngân sách.** Nếu chủ bật tự phanh và đã vượt trần tháng, `aux_engine.read_spec` có thể đã hạ engine trước khi Resonance thấy.
10. **Pilot để lại transcript.** Mỗi lần pilot mở một phiên Claude Code trong thư mục tạm, và Claude CLI lưu transcript của phiên đó trong `~/.claude/projects` như mọi phiên khác.
11. **Lần 1 rơi đúng cửa sổ token sắp hết hạn.** Cổng xếp hàng làm mới token (`claude_token_gate`) có kích hoạt, ghi nhãn `di-truoc`, và cho lượt này đi trước. Claude CLI tự làm mới token như lượt chat thường. Không có lỗi đăng nhập.
12. **Không chạy test JS.** M1 không đổi file JS nào.

### Toàn bộ test Python

Chạy `python tests/run.py --py` trên main sạch trước khi sửa, và trên head cuối của nhánh M1.

| | Main sạch (`7d264236`) | Nhánh M1 sau review (`5162dfab`) |
|---|---|---|
| Xanh | 387/403 | 389/404 |
| File đỏ | 16 | 15 |
| Đỏ mới so với main | | không có |

Các file đỏ có sẵn trên main sạch, không liên quan M1:

- `test_agy_prompt_dai.py`
- `test_antigravity_cli.py`
- `test_ba_loi_mac_va_telegram.py`
- `test_cai_windows.py`
- `test_grok_cli.py`
- `test_image_vision.py`
- `test_install_admin.py`
- `test_khoi_dong_nhe.py`
- `test_link_file_uri.py`
- `test_machine_translations.py`
- `test_memory_hoa_thuong.py`
- `test_model_theo_phien.py`
- `test_ollama_local.py`
- `test_terminal.py`
- `test_windows_no_console.py`

`test_project_khung.py` đỏ trên main sạch nhưng xanh trên nhánh M1 ở cả ba lượt chạy sau đó. M1 không đụng mã mà test này kiểm, nên nhiều khả năng đây là test chập chờn chứ không phải được M1 sửa.

Một lượt chạy giữa chừng (sau commit `ba404185`) có `test_ignore_files.py` đỏ. Nguyên nhân là file `.grok/config.toml` do test Grok mới của M1 để lại ở gốc repo, đã sửa ở `5162dfab` như ghi ở mục Sửa theo review. Lượt chạy trên head cuối không còn file đỏ mới.

## M2: phân luồng và tự hình thành mục tiêu (06/10/2026)

### Nền và nhánh

| Mục | Giá trị |
|---|---|
| Nhánh, PR | `claude/resonance-mvp-m2`, PR #567 (nháp), xếp chồng trên #566; phiên bản xí chỗ 0.84.1 |
| Base của PR | `claude/resonance-mvp-m1` tại `306e96cb` (head M1 đã qua review, CI xanh) |
| Commit nền của chuỗi | `origin/main` = `7d264236` (0.83.2), không đổi khi bắt đầu M2 |
| Model thật | Không gọi lượt nào ở M2. Tất cả kiểm chứng dùng engine giả hoặc gọi thẳng tool như engine sẽ gọi |

### Quyết định thiết kế cần người review soát

1. **Bộ não tự quyết định có lập mục tiêu hay không, ngay trong lượt chat, bằng tool `javis_goal`.**
   - Spec mục 4.0 yêu cầu "tận dụng bộ định tuyến hội thoại hiện có" và "không gọi thêm một model cho mọi tin nhắn". Dò mã 0.83.2 cho thấy chưa có bộ định tuyến bốn nhánh nào.
   - Thứ gần nhất là cách bộ não đã tự quyết giao việc nền bằng tool `javis_task` (Kanban) và `javis_schedule` (nhắc hẹn, loop). Nên `javis_goal` đi đúng mẫu đó: một plugin bundled, không thêm lượt gọi model, không dò từ khoá.
   - Đổi lại, chất lượng quyết định phụ thuộc vào bộ não đọc mô tả tool. Pilot thật để đo điều này thuộc M3.
2. **Host kiểm đề xuất theo SMART** (`resonance.validate_proposal`):
   - **R:** `relevant_quote` phải trích đúng một đoạn trong lời người dùng (so khớp bỏ hoa thường và khoảng trắng). Đây là chốt chặn mục tiêu do agent tự nghĩ ra.
   - **M:** ít nhất một tiêu chí dùng evaluator đã có (`artifact_contract`, `human_confirmation`); evaluator lạ bị loại.
   - **T:** có chân trời `deadline`, `review`, `event` hoặc `maintain`. Hạn chót chỉ giữ khi trích được câu người dùng nêu hạn; không thì thành mốc xem lại nội bộ, `from_user=false`.
   - **S:** chưa nói được kết quả cụ thể thì mục tiêu ở `discovery`, không bị từ chối.
   - Chỉ tiêu không có câu trích trong lời người dùng chuyển thành giả định. Người dùng đã nói chưa biết thì bỏ câu hỏi, ghi giả định, bắt đầu bằng khám phá.
   - Ràng buộc người dùng nêu luôn có trong khung. Kho từ chối mọi revision bỏ chúng.
3. **Phân nhánh sau lượt dựa trên những gì lượt đó thật sự đã làm** (`resonance.route_request`, `route_after_turn`):
   - Có sự kiện `created` của đúng tin nhắn này thì là `create_goal`; sự kiện `reframe` thì là `continue_goal`.
   - Có việc Kanban mới của đúng khung chat này, tạo trong lượt, thì là `task_now`. Còn lại là `answer_now`.
   - Có mục tiêu đang mở KHÔNG đủ để nối tin mới vào nó. Đây là lỗi bản review trước đã bắt ở phụ lục cũ.
   - Không đoán tên tool từ luồng sự kiện (tên khác nhau theo engine, và chế độ lazy giấu tên thật sau `javis_run_tool`); đọc thẳng kho mục tiêu và kho Kanban.
4. **Khoá chống trùng là id tin nhắn người dùng trong kho phiên.**
   - Trước M2, id này bị bỏ ngay sau `append_message`. Giờ `main.py` giữ lại cho cả tin gõ lẫn tin giọng nói (`message_id` của phiếu nhận giọng nói), và truyền xuống sổ lượt đang chạy (`luot_dang_chay`) cùng lời người dùng.
   - Tool chạy qua hub, có khi ở tiến trình khác, nên đọc sổ đó để biết đúng tin nào. Không chắc (hai khung chat cùng chạy trên một brain, hoặc kênh chưa truyền id tin như Telegram) thì tool từ chối, không đoán.
5. **Tool chỉ hiện ở brain đã bật.**
   - `plugins_host.register_tool` nhận thêm `visible_fn(vault_root)`; `plugin_tools` giấu tool khi hàm trả False. `check_fn` có sẵn chỉ chặn lúc gọi nhưng tool vẫn hiện, không đủ.
   - Công tắc là `<brain>/Javis/resonance.json` có `{"enabled": true}`. Mặc định tắt, file hỏng coi như tắt. Giao diện bật tắt thuộc M4.
   - Chỉ mục năng lực (dòng trong system prompt và `Javis/index.md`) cũng chỉ liệt kê tool đang hiện với brain đó; trước sửa, chỉ mục đọc manifest và vẫn kể `javis_goal` ở brain chưa bật.
6. **System prompt có thêm đúng một dòng gợi ý `javis_goal`, chỉ ở brain đã bật.** `CLAUDE.md` còn đúng 1 ký tự ngân sách nên không đụng tới; brain chưa bật không dài thêm chữ nào.
7. **M2 chỉ LƯU mục tiêu.** Kết quả tool dặn bộ não rằng chưa có gì tự thực hiện hay tự báo cáo, để nó không hứa suông (đúng luật "không hứa sẽ làm rồi báo lại" của `CLAUDE.md`).

### Thay đổi

| File | Nội dung |
|---|---|
| `server/resonance_store.py` (mới) | `GoalStore` trên `resonance.sqlite3`: bảng `intents`, `goals`, `goal_revisions`, `goal_events`, `outbox`. Mọi thao tác qua `Principal` đúng brain. Tạo và sửa ghi sự kiện cùng outbox trong một giao dịch `BEGIN IMMEDIATE`. `revise` cần `expected_revision`, giữ pause, ngân sách, số lượt đã dùng. Chỉ người dùng đổi được pause |
| `server/resonance.py` | `GoalRecord` thêm khung SMART và trạng thái (giữ nguyên sáu trường của M1). `GoalRejected`, `RouteDecision`, `enabled_for`, `validate_proposal`, `route_request`, `route_after_turn`, `message_ref`, `framer_prompt`, `form_goal`. Phần gọi engine của `run_once` tách thành `GoalDeps._ask` dùng chung với bộ lập mục tiêu, hành vi M1 không đổi |
| `system/plugins/javis-goal/` (mới) | Tool `javis_goal`: `create`, `update`, `list` |
| `server/plugins_host.py` | `visible_fn` cho tool plugin |
| `server/luot_dang_chay.py` | `bat_dau` nhận `msg_id`, `user_text`; thêm `doan_luot`. Gọi kiểu cũ vẫn chạy |
| `server/main.py` | Giữ id tin người dùng; truyền vào `run_turn`; `_resonance_after_turn` ghi runtime event `resonance.route`; dòng gợi ý system prompt; chỉ mục năng lực lọc tool đang giấu |

### Kết quả với engine giả

```
python tests/run.py resonance -v
  test_resonance_mvp_core.py         58 kiểm tra
  test_resonance_mvp_integration.py  73 kiểm tra (M1, vẫn xanh sau khi tách _ask)
  test_resonance_mvp_main.py         15 kiểm tra
  test_resonance_mvp_wiring.py       29 kiểm tra
```

TDD: cả ba file mới chạy đỏ trước khi có mã (`ModuleNotFoundError: No module named 'resonance_store'`, rồi `TypeError: bat_dau() got an unexpected keyword argument 'msg_id'`).

Tám test kế hoạch M2 nêu tên, đều có mặt trong `test_resonance_mvp_core.py` (nhãn kiểm tra mang đúng tên):

| Test kế hoạch | Kiểm gì |
|---|---|
| `test_chat_does_not_create_goal` | Lượt không gọi tool mục tiêu là `answer_now`, kể cả khi đang có mục tiêu mở |
| `test_inline_job_stays_inline` | Làm xong trong lượt, có ghi file, vẫn là `answer_now` |
| `test_followup_reuses_goal` | Bổ sung ý cho mục tiêu mở là `continue_goal` đúng mục tiêu đó |
| `test_persistent_request_creates_once` | Cùng tin nhắn hai lần: một mục tiêu, một sự kiện `created` |
| `test_proposed_plan_does_not_schedule` | Câu căn cứ không có trong lời người dùng (ý agent tự đề xuất) bị từ chối |
| `test_ambiguous_goal_smart` | Thiếu S về `discovery`; thiếu M hoặc T bị từ chối |
| `test_user_unsure_discovers` | Người dùng chưa rõ: vẫn lập mục tiêu khám phá, không hỏi lại, ghi giả định |
| `test_no_invented_target_or_deadline` | Hạn không trích được thành mốc xem lại; chỉ tiêu không căn cứ thành giả định |

Kiểm thêm:

- **Kho:** chống trùng theo tin nhắn; brain khác không đọc, sửa, liệt kê được; `expected_revision` cũ thì xung đột và không đổi gì; revision cũ còn nguyên; pause, ngân sách, số lượt đã dùng giữ qua revision; không bỏ được ràng buộc của người dùng; outbox có `goal.created` và `goal.revised`; tạo với bản ghi ý định không tồn tại thì không để lại mục tiêu nửa vời; mở lại kho vẫn còn dữ liệu.
- **`form_goal`:** có đề xuất của bộ não thì không gọi model, không tốn lượt; không có đề xuất thì bộ lập mục tiêu gọi đúng một lượt chỉ chữ, lời người dùng nằm trong rào như dữ liệu; trả rác thì từ chối và vẫn tính một lượt; engine bị chặn thì trả lại lượt.
- **Plugin qua `plugins_host` thật:** brain chưa bật không thấy tool, bật ở brain này không làm brain khác thấy; tạo, tạo lặp, đề xuất sai luật (không để lại mục tiêu), cập nhật lên revision 2 và route `continue_goal`, cập nhật lặp bị xung đột, mục tiêu không tồn tại, `list`; hai khung chat cùng chạy và lượt không có id tin thì từ chối; tắt lại thì tool biến mất và gọi bằng tham chiếu cũ cũng bị từ chối.
- **`main.py`:** brain tắt thì không làm gì, không tạo file kho, prompt không nhắc `javis_goal`; brain bật thì có dòng gợi ý (dưới 450 ký tự); bộ não gọi tool trong lượt rồi `main` phân nhánh `create_goal`, mục tiêu đúng brain theo `_brain_key`, vùng đầu ra nằm trong brain; việc Kanban của đúng khung chat trong lượt là `task_now`, việc tạo trước lượt không tính; kho lỗi thì nuốt, không làm hỏng lượt chat.

### Lỗi tự gây trong lúc làm, đã sửa

- **Canary giọng nói.** `test_voice_ten_javis.py` đọc mã nguồn `main.py`, tìm đúng dòng `store.append_message(conv_sid, "user", user_message)` để chắc tên nghe nhầm được sửa trước khi lưu. Em bọc dòng đó trong `int(... or 0)` nên canary đỏ ở lượt chạy toàn bộ đầu tiên. Sửa mã cho khớp canary (commit `f6fd4841`), không sửa canary.
- **Chỉ mục năng lực.** Test `main` bắt được `javis_goal` vẫn hiện trong system prompt của brain chưa bật, qua dòng "Plugins đang chạy". Đã lọc theo tool thật sự hiện.

### Sửa theo review PR #567

Review của ChatGPT (`exports/reviews/PR-567-M2-review.md`, diff `306e96cb..c79e27c5`) nêu 1 lỗi P1 và 2 lỗi P2, cả ba đều tái hiện được qua tool thật. Sửa ở commit `709f016a` và `279ef56a`, test hành vi ở `tests/python/test_resonance_mvp_revise.py` (28 kiểm tra) và 7 kiểm tra thêm trong `test_resonance_mvp_main.py`.

- **P1-1: tin bổ sung làm mất hạn và chỉ tiêu cũ.** Nhánh `update` của tool nay gọi `resonance.revise_goal`. Hàm này đọc revision hiện tại TRƯỚC khi kiểm, rồi gọi `validate_proposal(..., prior=..., source_ref=...)`:
  - trường bản cập nhật bỏ trống thì kế thừa;
  - hạn chót người dùng nêu ở tin trước được giữ nguyên cả giá trị lẫn nguồn khi bản cập nhật giữ đúng thời điểm và câu trích; chỉ tiêu cũ cũng vậy khi giữ đúng chữ và câu trích;
  - hạn hay chỉ tiêu MỚI vẫn phải trích được từ tin hiện tại, nên người dùng dời hạn thì hạn mới thắng; agent tự dời hạn thì vẫn thành mốc xem lại;
  - mượn câu trích cũ cho một chỉ tiêu khác chữ thì không được coi là chỉ tiêu cũ;
  - mỗi hạn chót và chỉ tiêu của người dùng nay mang `source` là tin nhắn làm căn cứ.

  Host tự suy quan hệ của bản cập nhật: `replace` khi hạn hay chỉ tiêu có nguồn người dùng không còn nguyên, còn lại `amend`. Quan hệ ghi vào bản ghi ý định mới (nay nối về ý định của revision trước qua `prev_intent_id`, thay cột `supersedes` chưa dùng) và vào sự kiện `reframe`. (Bản này còn cho bộ não bỏ chỉ tiêu mà chỉ ghi `replace`; vòng review 2 bác, đã sửa ở mục dưới.)
- **P2-1: làn giọng nói và lượt chạy lại không mang id tin.** `run_voice_turn` nhận `user_mid` và truyền vào cả hai lời gọi `run_turn` (giữ câu gốc, rơi về bộ não chính). Hẹn chạy lại sau hạn mức mang theo `user_mid` và `user_text` của lượt gốc, nên chạy lại cùng tin không tạo mục tiêu thứ hai. Nhánh trả lời trong phiên quy trình cũng truyền id. `run_turn` nhận thêm `user_text`: đúng lời người dùng, đã bóc khối ngữ cảnh giao diện và không kèm ghi chú câu nghe hay khối quy trình host gắn vào prompt. Lượt nối tiếp do host tự mở sau việc nền vẫn KHÔNG mang id, vì chữ mở lượt là của host.
- **P2-2: tiêu chí rỗng vẫn qua cổng M.** Mô tả được chuẩn hoá khoảng trắng; tiêu chí rỗng bị loại; không còn tiêu chí nào thì từ chối với lời nói rõ cần mô tả điều cần kiểm. Kiểm cấu trúc `params` theo từng evaluator để sang M3, như review đề nghị.

Sửa P2-1 làm đỏ hai canary giọng nói đọc mã nguồn `main.py` ở lượt chạy toàn bộ đầu tiên. `test_dien_giai_thuat_ngu.py` cấm `_giu_cau_goc` nhắc tới câu bộ não giọng diễn giải, nên lời người dùng được tính một lần thành `_loi_goc` cạnh `original_message`, sửa mã chứ không sửa canary. `test_voice_turn_integrity.py` dựng `run_voice_turn` với một `run_turn` giả không nhận tham số từ khoá; hàm giả được cho nhận thêm `user_mid`, `user_text`, mọi kiểm tra của nó giữ nguyên.

Chạy lại `PR-567-M2-repro.py` trên nhánh: assertion mô tả lỗi P1 không còn đúng (hạn giữ là `deadline`), tức lỗi đã hết. Hai phép còn lại được phủ bằng test hành vi ở trên.

### Sửa theo review PR #567 vòng 2

Review vòng 2 (`exports/reviews/PR-567-M2-review-round2.md`, diff `c79e27c5..9f2e9a32`) xác nhận P2 thiếu id và P2 tiêu chí rỗng đã đóng, nêu thêm 1 P1 và 1 P2.

- **P1: nhãn `replace` không thay được căn cứ.** (Cách sửa ở mục này bị vòng 3 bác và đã thay, xem mục Sửa theo review vòng 3.) Bản vòng 1 vẫn để bộ não gửi `targets=[]` hay tự dời hạn ở một tin chỉ đổi trình bày; host lưu và ghi `replace`. Nay hạn chót và chỉ tiêu người dùng đã nêu là chỉ dẫn đang có hiệu lực (bất biến 2.1). Bản cập nhật chỉ đổi hay bỏ được chúng khi tin HIỆN TẠI có câu trích làm căn cứ:
  - đổi hạn: hạn mới kèm `quote` trích từ tin này;
  - bỏ hạn: chân trời mới kèm `horizon.quote` trích câu bỏ hạn; chân trời ghi lại câu và tin làm căn cứ;
  - bỏ chỉ tiêu: một mục trong `remove_targets` (trường mới của tool) cùng chữ, kèm `quote` trích từ tin này.

  Thiếu căn cứ thì host GIỮ chỉ dẫn cũ, không từ chối cả bản cập nhật, và tool trả thêm dòng "Host giữ lại chỉ dẫn cũ của người dùng" kèm lý do để bộ não biết. Mốc xem lại agent tự đặt không đè lên deadline đang có hiệu lực. `replace` nay chỉ được ghi cho thay đổi đã được phép. Người dùng nhắc lại một chỉ tiêu thì chỉ tiêu đó giữ một mục, nguồn mới. Test cũ khẳng định bỏ chỉ tiêu là đúng đã được đổi kỳ vọng.
- **P2: cập nhật từng phần làm rơi ràng buộc.** `_prior_view` nay mang `constraints`; khung mới hợp ràng buộc cũ, ràng buộc của tin mới và ràng buộc đề xuất. Cập nhật từng phần trên mục tiêu có ràng buộc thành công và giữ nguyên ràng buộc; bộ não gửi `constraints=[]` cũng không gỡ được. Tool nói rõ chưa hỗ trợ gỡ ràng buộc.
- **Ý định mồ côi khi cập nhật (điểm 5 của review):** bản ghi ý định nay được ghi trong CÙNG transaction với revision (`GoalStore.new_intent` + `revise(intent=...)`), nên revision bị kho từ chối (xung đột, thiếu ràng buộc) không để lại ý định. Đường TẠO mục tiêu vẫn ghi ý định trước rồi mới `create`; nếu hai lượt cùng tin chen nhau, ý định của lượt thua còn lại.
- **Kiểm hành vi đường truyền id (điểm 6):** test mới `test_resonance_mvp_handoff.py` (12 kiểm tra) trích nguyên `run_turn`, `run_voice_turn`, `_start_resumed_turn` từ `main.py` rồi chạy với dịch vụ giả, theo cách dựng của script kiểm độc lập vòng 2. Kiểm sổ lượt và tool nhận đúng id, đúng lời người dùng (đã bóc khối ngữ cảnh giao diện, không kèm ghi chú câu nghe) ở hai nhánh giọng nói và nhánh chạy lại; ba lượt cùng tin chỉ tạo một mục tiêu; lượt không có id thì tool từ chối.
- **Test:** `test_resonance_mvp_revise.py` lên 42 kiểm tra (thêm ca tin chỉ đổi trình bày kèm bỏ chỉ tiêu hay tự dời hạn, mốc xem lại agent đặt, `remove_targets` với câu trích không có trong tin, người dùng bỏ chỉ tiêu và bỏ hạn có căn cứ, nhắc lại chỉ tiêu, ràng buộc kế thừa, ý định không mồ côi, và hai ca qua tool thật).
- **Đổi schema bảng `intents` không kèm migration.** Bảng đổi cột `supersedes` thành `prev_intent_id`, `relation`. M2 chưa phát hành nên chưa có dữ liệu người dùng cần giữ. Kho thử tạo theo schema M2 cũ KHÔNG tự nâng cấp được; nếu đã có dữ liệu cần giữ thì phải viết migration, không xoá kho để chữa.

Chạy lại `PR-567-M2-round2-checks.py` trên nhánh: assertion REPRO của P1 (bộ não gửi `targets=[]` làm mất chỉ tiêu) không còn đúng, tức lỗi đã hết; các ca P1 và P2 còn lại được phủ bằng test hành vi ở trên.

### Sửa theo review PR #567 vòng 3

Review vòng 3 (`exports/reviews/PR-567-M2-review-round3.md`, diff `9f2e9a32..2b1b212f`) xác nhận ràng buộc kế thừa, bảo vệ khi bộ não quên trường hay dùng câu trích cũ, ý định ghi cùng transaction và test handoff đều đạt. Còn hai điểm:

- **P1: câu trích CÓ MẶT trong tin vẫn bỏ được chỉ dẫn.** Bộ não trích "thêm bảng tổng hợp" làm căn cứ bỏ chỉ tiêu và bỏ hạn, host chấp nhận. Phép tìm chuỗi chỉ chứng minh câu có trong tin, không chứng minh người dùng muốn đổi. Lỗ này rộng hơn review nêu: đường ĐỔI hạn (hạn mới kèm câu trích từ tin hiện tại) cũng có cùng điểm yếu.

  Chọn phương án thu hẹp phạm vi M2 do review đề xuất, khớp bất biến 2.1 của thiết kế chuẩn: hạn chót, chỉ tiêu và ràng buộc người dùng đã nêu KHÔNG đổi hay bỏ được qua bản cập nhật ở M2, dù câu trích có mặt hay không. Host giữ nguyên cả giá trị lẫn nguồn. Tool trả "Host giữ nguyên chỉ dẫn cũ, phần sau CHƯA áp dụng" và dặn bộ não nói rõ với người dùng là chưa đổi được, đừng báo là đã đổi. Bản cập nhật không còn gì đổi được áp dụng thì không ghi revision, không ghi ý định, và tool nói "KHÔNG có thay đổi nào được áp dụng". Thêm chỉ dẫn MỚI vẫn được, cùng luật trích như lúc tạo: chỉ tiêu mới, ràng buộc mới, và hạn khi mục tiêu chưa có hạn người dùng. Người dùng nhắc lại một chỉ tiêu thì vẫn một mục, giữ nguồn cũ. Agent vẫn tự sửa cách hiểu, tiêu chí, giả định, câu hỏi. Đường sửa chỉ dẫn có thẩm quyền do host xác định (thao tác của người dùng trên thẻ mục tiêu, hoặc xác nhận đúng phần thay đổi) để sang M4.
- **P2: chỉ gửi `remove_targets` thì báo thành công mà không bỏ gì.** Không còn là chức năng: trường `remove_targets` đã gỡ khỏi schema của tool; nếu bộ não vẫn gửi thì host báo "remove_targets chưa hỗ trợ" và không ghi revision.
- **Test:** `test_resonance_mvp_revise.py` lên 48 kiểm tra, viết lại các ca đổi/bỏ chỉ dẫn theo phạm vi mới: câu trích cũ, câu trích có mặt nhưng không liên quan (đúng phép tái hiện vòng 3), người dùng thật sự dời hạn, người dùng thật sự bỏ chỉ tiêu và hạn, chỉ gửi `remove_targets`, thêm chỉ tiêu mới, thêm hạn khi chưa có hạn người dùng, nhắc lại chỉ tiêu. Mỗi ca kiểm trạng thái cuối trong kho, không chỉ kiểm tool trả thành công.

Chạy lại `PR-567-M2-round3-checks.py`: hai assertion PASS đầu vẫn qua. Bước 4 của script dừng ở xung đột revision, vì script giả định bước 3 ghi revision mới, trong khi nay bản cập nhật không đổi được gì thì không ghi revision. Chạy một bản sao chỉ đổi `expected_revision` bước 4 thành revision hiện tại: assertion REPRO P1 không còn đúng (chỉ tiêu và hạn còn nguyên). Ca P2 được phủ trong test của PR.

### Sửa theo review PR #567 vòng 4

Review vòng 4 (`exports/reviews/PR-567-M2-review-round4.md`, diff `2b1b212f..439fe922`) đóng P1 trong phạm vi M2 đã thu hẹp và giữ nguyên quyết định phạm vi. Còn hai lỗi P2 cục bộ:

- **P2-1: chân trời bị chặn vẫn kéo `mode` đổi theo.** `mode` được tính từ biến `kind` của đề xuất chứ không từ chân trời cuối cùng host nhận, nên đề xuất `maintain` bị chặn vẫn đổi mục tiêu `achieve` thành `maintain` và ghi một revision. Nay `mode` tính từ chân trời đã nhận; không gửi `mode` thì giữ mode trước đó.
- **P2-2: tool lọc mất `remove_targets` trước khi validator kịp báo.** `_proposal` của plugin nay chuyển tiếp trường cũ này (vẫn ngoài schema) để validator báo "chưa hỗ trợ". Tóm tắt của tool nay có dòng "Chỉ tiêu người dùng nêu", nên bộ não thấy chỉ tiêu còn giữ.
- **Test:** `test_resonance_mvp_revise.py` lên 58 kiểm tra. `_frozen` kiểm thêm mode và stage. Ba ca mới đi qua `plugins_host` thật, so toàn bộ `GoalRecord` và số dòng của `intents`, `goal_revisions`, `goal_events`, `outbox` trước và sau: chân trời maintain bị chặn; chỉ gửi `remove_targets`; sửa hợp lệ pha trộn với `remove_targets` (phần hợp lệ được áp dụng, tool báo "Đã cập nhật" kèm phần CHƯA áp dụng và chỉ tiêu còn giữ). Đếm dòng dùng `closing` để không giữ kết nối SQLite.

Chạy lại `PR-567-M2-round4-checks.py`: hai PASS qua; assertion REPRO P2-1 không còn đúng. Một bản sao bỏ hai assertion của P2-1 để chạy tới P2-2: assertion REPRO P2-2 cũng không còn đúng.

### Giới hạn và những gì chưa kiểm

1. **Chưa gọi model thật ở M2.** Chưa đo bộ não thật có gọi `javis_goal` đúng lúc hay không, và có điền đề xuất qua được luật SMART hay không. Pilot thật một mục tiêu là việc của M3 theo kế hoạch.
2. **Chỉ khung chat web.** Telegram và Zalo chưa truyền id tin, nên tool từ chối lập mục tiêu ở đó. (Bản đầu còn sót làn giọng nói, lượt chạy lại sau hạn mức và phiên quy trình; đã sửa theo review, xem mục dưới.)
3. **Chưa có guard trong mô hình dữ liệu.** Kế hoạch nói đổi cách hiểu giữ "quyền, ngân sách, guard, pause". M2 giữ ngân sách, số lượt đã dùng, pause; guard đến cùng M3.
4. **Bản ghi ý định có thể mồ côi ở đường tạo.** Đường cập nhật đã ghi ý định cùng transaction với revision (vòng review 2). Đường tạo vẫn ghi ý định trước `create`: hai lượt cùng một tin chen nhau thì ý định của lượt thua còn lại. Bảng chỉ ghi thêm, không gây sai.
5. **`reminders_created` chưa được nối.** Hàm phân nhánh nhận số nhắc hẹn tạo trong lượt, nhưng `main` mới đếm việc Kanban. Lượt chỉ đặt nhắc hẹn hiện được ghi là `answer_now`.
6. **Nhánh phân xong mới chỉ được ghi vào runtime event.** M4 dùng nó để vẽ thẻ "Em đang hướng tới".
7. **Không chạy test JS.** M2 không đổi file JS nào.
8. **Không phải mọi đường giọng nói đều hỗ trợ Resonance.** Việc nền do làn nhanh giao (V3, `JAVIS_ASK_MAIN`), là đường giao việc bình thường của làn nhanh, không gọi `run_turn` và không đăng ký lượt kèm id tin, nên tool từ chối. Chỉ hai nhánh giọng nói chuyển về `run_turn` (giữ câu gốc, rơi về bộ não chính) mang id. Nếu pilot M3 có giao việc bằng giọng nói thì phải truyền nguồn yêu cầu đáng tin qua đường việc nền trước.
9. **Đường truyền id kiểm bằng hàm thật với dịch vụ giả.** Chưa chạy end-to-end với model, micro, HTTP/WebSocket thật hay chờ hạn mức thật.
10. **Chưa đổi hay bỏ được chỉ dẫn người dùng đã nêu.** Hạn chót, chỉ tiêu, ràng buộc đã lưu chỉ thêm được, không đổi hay bỏ được bằng chat ở M2; tool báo rõ phần chưa áp dụng. Đường sửa có thẩm quyền để M4. Không dùng giới hạn này để bỏ qua lệnh dừng hay thu hồi quyền khi có runtime thực thi.
11. **Kiểm `params` theo từng evaluator chưa làm.** Hiện chỉ kiểm là object rồi sao chép; việc của M3.

### Toàn bộ test Python

| | Main sạch (`7d264236`) | Nhánh M2 (`f6fd4841`) | M2 sau review (`279ef56a`) | M2 sau review vòng 2 (`daa5684e`) | M2 sau review vòng 3 (`1f9099c9`) | M2 sau review vòng 4 (`d57cd14e`) |
|---|---|---|---|---|---|---|
| Xanh | 387/403 | 392/407 | 391/408 | 393/409 | 391/409 | 393/409 |
| File đỏ | 16 | 15 | 17 | 16 | 18 | 16 |
| Đỏ mới so với main | | không có | không có do M2 gây ra | không có | không có do M2 gây ra | không có do M2 gây ra |

Lượt vòng 2: 16 file đỏ đúng bằng danh sách đỏ trên main sạch (15 file ở mục M1 cộng `test_project_khung.py`).

Lượt vòng 3: 16 file đó cộng hai file chập chờn. `test_hoi_thoai_nhom.py` đã ghi ở trên. `test_bao_viec_ve_chat_web.py` đỏ trong lượt toàn bộ, chạy riêng ba lần trên cùng mã đều xanh, không chạm mã Resonance.

Lượt vòng 4: 15 file đỏ sẵn ở mục M1 cộng `test_hoi_thoai_nhom.py` (chập chờn). `test_project_khung.py` xanh ở lượt này.

Ở lượt sau review, 17 file đỏ gồm 15 file đỏ sẵn ở mục M1, `test_project_khung.py` (đỏ trên main sạch) và `test_write_path_phase9.py`. File cuối chạy riêng hai lần trên cùng mã thì một xanh một đỏ (`test_restart_marks_running_writes_unknown_without_rerunning`), không chạm mã Resonance nào: test chập chờn. `test_hoi_thoai_nhom.py` cũng chập chờn (chạy riêng ba lần: xanh một, đỏ hai, kiểm thứ tự ghim hội thoại M2 không đụng tới); lượt toàn bộ này nó xanh.

Danh sách 15 file đỏ trùng đúng danh sách đỏ sẵn ở mục M1. `test_project_khung.py` tiếp tục xanh trên nhánh, như ở M1.

Lượt chạy toàn bộ đầu tiên của M2 (commit `66328b61`) có `test_voice_ten_javis.py` đỏ do M2 gây ra, đã sửa ở `f6fd4841` như ghi ở mục Lỗi tự gây.

## M3: thực thi, bằng chứng và lịch nhỏ (06/10/2026)

### Nền và nhánh

- Nhánh `claude/resonance-mvp-m3` tách từ head M2 đã qua review (`fa7e264d`), PR nháp #570 xếp chồng trên #567. Phiên bản 0.84.4: `origin/main` đã lên 0.84.2 (`bacb1cfe`) và PR #569 đang giữ 0.84.3.
- `origin/main` đi tiếp đúng một commit so với nền `7d264236` của chuỗi (`bacb1cfe`, Zalo vào nhóm). Commit đó chỉ sửa phần Zalo cùng `VERSION` và hai CHANGELOG, không chạm file nào của Resonance. Không đồng bộ vào chuỗi lúc này: đồng bộ sẽ thêm merge commit vào hai PR đã qua review mà không đổi gì của Resonance. VERSION và CHANGELOG sẽ chỉnh một lần lúc merge.

### Quyết định thiết kế cần người review soát

1. **Một vòng `advance(goal_id, event, deps)` tiếp tục được sau restart** (spec mục 7). Mỗi lần: kiểm công tắc brain, pause, guard; nhận khoá lượt có hạn (`claim_lease`); đối soát hành động dở; đánh giá bằng chứng đã gắn với ĐÚNG revision hiện tại; chỉ khi chưa đạt và sự kiện là loại được làm việc (`start`, `wake`, `user_message`, `resume`) mới làm MỘT bước. `observe` chỉ quan sát guard; `reaction` không làm gì; `user_schedule` sửa lịch.
2. **Ghi ý định trước tác động.** `GoalStore.begin_action` ghi hành động `running` và giữ một lượt gọi model trong CÙNG giao dịch (`calls_used < budget_calls`), kèm lịch phục hồi tại lúc hết khoá. Không ghi được thì không dựng engine. Hết hạn mức thì blocked `budget`, không gọi.
3. **Đối soát sau restart.** Hành động `running` mà khoá đã hết: có file đầu ra đúng `action_id` thì chốt succeeded (`reconciled: true`), không gọi model lại; không có thì `failed: interrupted` (model có thể đã được gọi nên vẫn tính vào hạn mức) và lượt sau dùng id MỚI. Hành động đăng sản phẩm đối soát bằng hash file đích.
4. **Bằng chứng qua EvidenceStore thật.** `main._ResonanceEvidence` mở một turn runtime kênh `resonance` cho mỗi lần ghi, mã hoá, đọc lại qua `get_valid` (kiểm hạn và hash). Kho chưa có cơ chế ghim nên hạn lưu đặt 90 ngày. Không ghi được bằng chứng thì coi như CHƯA có bằng chứng và không xác nhận thành công. Mỗi lần đánh giá file trong brain cũng chụp nội dung vào kho (bỏ qua nếu cùng hash).
5. **Đặt sản phẩm vào brain có rào.** Đầu ra của model nằm trong vùng làm việc `Javis/resonance/outputs/<goal>`; host đăng bản đó vào đường dẫn tiêu chí `artifact_contract` đầu tiên khai `path`, khi và chỉ khi: đường dẫn nằm trong brain sau resolve; đuôi `.md` hoặc `.txt`; KHÔNG nằm ở chỗ Javis tự chạy hay tự nạp (thư mục ẩn, `Javis/`, `agents/`, `skills/`, `workflows/`, `plugins/`, `memory/`, file `CLAUDE.md`/`AGENTS.md`/`GEMINI.md`/`MEMORY.md`); file chưa có, hoặc có nhưng hash đúng bằng lần chính mục tiêu này đăng trước. File người dùng hay tác vụ khác đã sửa thì xung đột: giữ nguyên, ghi `publish_conflict`, báo người dùng. Kiểm lại công tắc brain NGAY TRƯỚC khi đăng.
6. **Kết luận.** `evaluate_artifact` trả met / not_met / unknown theo từng tiêu chí: thiếu file khai rõ là not_met; chưa có hoặc không đọc lại được bằng chứng là unknown; đường dẫn ra ngoài brain là unknown (lỗi evaluator); `human_confirmation` luôn unknown tới M4. Mục tiêu achieve chỉ thành `succeeded` khi MỌI tiêu chí met và `GoalStore.finish` so đúng revision đã đánh giá (CAS). Mục tiêu maintain đạt thì giữ active, hẹn xem lại. Chỉ còn tiêu chí người dùng thì chuyển `waiting`, không hẹn gọi model.
7. **Lịch.** Bảng `wakeups` (một lịch `work` và một lịch `observe` mỗi mục tiêu). `main._resonance_tick` được scheduler 30 giây có sẵn khởi bằng `create_task` (cờ bận chống chồng nhịp); chưa có `resonance.sqlite3` thì thoát ngay. `tick` chỉ đọc lịch tới hạn bằng code và nhận mỗi lịch bằng CAS. `next_wake`: không có nguồn sự kiện thì xem lại trong khoảng 6 đến 24 giờ; chân trời `event` chưa có adapter nên cũng chỉ xem lại có giới hạn; chưa đạt sau một lượt thì làm lại sau 15 phút nếu còn hạn mức; lỗi engine lùi 1 giờ, 4 giờ, 24 giờ hoặc chờ mốc mở lại hạn mức gói (`limit_learner.parse_subscription_limit`); người dùng hẹn thì sửa lịch trực tiếp; reaction không đổi gì. Tạo và sửa mục tiêu ghi lịch `work` ngay trong giao dịch của chúng.
8. **Guard.** Trường mới `guards` trong khung mục tiêu (tool nhận). Chỉ `artifact_contract` có adapter đọc: file khai phải còn và đạt điều kiện. Nguồn khác ghi unknown "chưa hỗ trợ nguồn ... (chưa có adapter đọc)". Lịch quan sát guard riêng (1 giờ), đọc bằng code, không gọi model. Guard nhảy thì blocked `guard`, xoá mọi lịch, báo người dùng, không tự mở lại khi bị đánh thức.
9. **Báo người dùng qua outbox.** `drain_outbox` gửi đúng các tin có ý nghĩa (`goal.succeeded`, `goal.maintained`, `goal.waiting_human`, `goal.blocked`, `goal.guard`, `goal.publish_conflict`) tới `_notify_owner("web:<phiên đã giao>")` (khung chat cộng hộp thư) rồi đánh dấu đã gửi; tin nội bộ chỉ đánh dấu. Khoá `idem` duy nhất theo mục tiêu chống báo lặp. Gửi lỗi thì để lại cho nhịp sau.
10. **Lời gửi model.** Mục tiêu, CẢ chuỗi lời người dùng (lần theo `prev_intent_id`, tối đa 5 tin), tiêu chí, ràng buộc, giả định, phần chưa đạt lần trước và bản sản phẩm hiện có, lời người dùng và bản cũ nằm trong rào dữ liệu. Engine vẫn là đường chỉ chữ của M1 (`main._resonance_engine`), không có chuỗi dự phòng.
11. **Schema.** Bảng mới `actions`, `assessments`, `evidence_links`, `wakeups`, `published`; cột mới `goals.run_state/block_reason/lease_owner/lease_until`, `outbox.idem` thêm bằng `ALTER TABLE` khi mở kho, nên kho tạo bởi bản M2 nâng cấp tại chỗ, không xoá dữ liệu.
12. **Kiểm `params` theo evaluator** (review M2 giao cho M3): `artifact_contract` của tiêu chí và guard chỉ nhận `path` (tương đối, không `..`, không ổ đĩa), `min_chars` (số nguyên trong trần đầu ra), `must_contain` (tối đa 10 chuỗi không rỗng); tham số lạ hay sai kiểu thì từ chối đề xuất với lời nói rõ. `human_confirmation` không mang params.
13. **`run_once` đổi em dash thành "-" trước khi ghi** (luật cấm em dash trong file, kể cả brain), receipt ghi số chỗ đã đổi (`normalized_em_dash`); hash là của đúng bytes đã ghi.

### Kết quả với engine giả

`tests/python/test_resonance_mvp_run.py` (71 kiểm tra ở bản đầu, 92 sau sửa review), kho SQLite thật, engine giả theo hợp đồng sự kiện của aux_engine, cổng bằng chứng giả cùng hợp đồng với `_ResonanceEvidence`. Đủ các test Task M3 đặt tên: `done_is_not_success`, `missing_evidence_unknown`, `restart_does_not_repeat_effect`, `old_revision_cannot_finish`, `pause_and_revoke`, `audit_failure_before_effect`, `budget_reserved_before_call`, `limit_keeps_checkpoint`, `no_paid_provider_fallback`, `idle_does_not_call_model`, `guard_wakes_without_worker`, `no_source_uses_bounded_review`. Thêm: không ghi đè file người dùng đã sửa, chín đường dẫn bị cấm đăng, mục tiêu duy trì làm tiếp sau tin bổ sung (lời gửi model có cả lời gốc, tin mới và bản hiện có), báo một lần mỗi revision.

`tests/python/test_resonance_mvp_main.py` thêm 10 kiểm tra (tổng 32): cổng bằng chứng ghi rồi đọc lại EvidenceStore THẬT, `_resonance_deps` dựng đúng principal và engine, và một mục tiêu đi trọn vòng trên host với engine giả: tool `javis_goal` tạo, `main._resonance_tick` làm ở nền, sản phẩm vào brain, mục tiêu thành công, báo về đúng `web:<phiên>` kèm link; nhịp sau không gọi engine.

Phép thử đột biến (phá từng hành vi rồi chạy lại test, phải đỏ): bỏ kiểm xung đột khi đăng, bỏ trần hạn mức, bỏ kiểm pause, đối soát không xem file đầu ra, coi unknown là xong, `finish` không so revision, cắt chuỗi ý định, bỏ danh sách cấm đăng. Cả tám đều bị test bắt.

### Kết quả pilot thật

`tests/python/test_resonance_mvp_pilot.py`, chỉ chạy khi `JAVIS_RESONANCE_PILOT=1`. Bằng chứng: `docs/dev/resonance-mvp-m3-pilot.json` (không có đường dẫn cá nhân).

- **Commit:** `9f3dad13`, cây `server/` sạch. Sau đó có thêm thay đổi ở đường báo tin (`goal.maintained`) và danh sách cấm đăng; hai phần này được kiểm bằng engine giả, KHÔNG chạy lại pilot thật để giữ hạn mức.
- **Môi trường:** `JAVIS_STATE_DIR` tạm, chỉ chép các ô chọn engine (`anthropic-cli` / `sonnet`), brain tạm với dữ liệu mô phỏng, kênh báo thay bằng bộ ghi lại.
- **Kịch bản:** mục tiêu duy trì "ghi chú `Inbox/viec-tuan.md` liệt kê việc đang dở" có guard "ghi chú cũ vẫn còn", hạn mức 3 lượt. Nhịp 1 qua `main._resonance_tick`; người dùng bổ sung "gia hạn tên miền"; giả lập khởi động lại (bỏ đối tượng kho, mở kho mới); nhịp 2; nhịp 3.
- **Kết quả:** 2 lượt gọi model thật (6,0 và 5,0 giây), cả hai receipt succeeded, đúng provider đã chọn, 0 lần gọi công cụ, hash khớp file trên đĩa. Hai lần đăng sản phẩm succeeded (lần 2 ghi đè được vì đúng hash lần 1 của chính mục tiêu). Cả hai revision host kiểm met. Nhịp 3 không gọi thêm. Dùng 2/3 lượt. Bằng chứng revision 2 đọc lại được từ EvidenceStore thật, hash khớp. Ghi chú cũ còn nguyên, không có em dash.
- **Usage engine báo:** khoảng 18,1 nghìn và 18,5 nghìn token vào, khoảng 300 token ra mỗi lượt; `cost_usd` là con số SDK tự tính trên gói thuê bao, không phải hoá đơn.
- **Pilot làm lộ hai điều:** (a) mục tiêu duy trì đạt mà không báo người dùng gì, đã sửa bằng `goal.maintained`; (b) model tự viết câu sai "các ghi chú cũ trong Inbox/viec-tuan.md được giữ nguyên", trong khi ghi chú cũ nằm ở `Notes/`. Bộ thực thi chỉ chữ chỉ thấy ràng buộc dạng chữ, không thấy file, nên có thể viết lời khẳng định không kiểm chứng. Đây là giới hạn chất lượng, không sửa ở M3.

### Lỗi tự gây hoặc tự phát hiện trong lúc làm, đã sửa

- **Mất ngữ cảnh khi làm tiếp.** Sau tin bổ sung, ý định của revision là tin bổ sung đó, nên bước làm tiếp chỉ đưa tin mới cho model, mất lời giao gốc và bản đã làm. Phát hiện khi thiết kế pilot; sửa ở `9f3dad13`.
- **Mục tiêu duy trì im lặng.** Phát hiện ở pilot; sửa ở `a71b124e`.
- **Sản phẩm có thể tạo file cấu hình Javis.** Tự soát diff thấy đường dẫn do model khai có thể tạo `Javis/loops/*.md`, `agents/*.md`, `skills/*/SKILL.md`, `memory/...` hay `CLAUDE.md`, tức tự mở rộng quyền. Thêm danh sách cấm ở `_publish`.
- **Hai lỗi trong test của chính em:** chân trời `maintain` làm mục tiêu thành maintain nên không "thành công" (đúng thiết kế, sửa test); `tick` chung xử lý cả mục tiêu khác đang tới hạn (sửa test đếm theo mục tiêu).

### Sửa theo review PR #570

Review của ChatGPT (`exports/reviews/PR-570-M3-review.md`, diff `fa7e264d..e5a42409`) nêu 5 lỗi P1 và 1 lỗi P2, cả sáu đều tái hiện được trên GoalStore SQLite thật. Đồng ý cả sáu. Sửa trong một commit, test hồi quy nằm ở cuối `test_resonance_mvp_run.py` (lên 92 kiểm tra).

- **P1-1, pause giữa lượt bị bỏ qua ở bước đăng.** Thêm `_gate`: mục tiêu còn active, công tắc brain còn bật, người dùng không tạm dừng, mọi guard clear. Cổng chạy trước MỌI lần đăng sản phẩm và mọi kết luận thành công, kể cả ngay sau khi model trả về. Bị chặn thì đầu ra giữ trong vùng làm việc, receipt và lượt đã dùng vẫn ghi. Tiếp tục (`set_paused(False)` nay hẹn lịch làm ngay) thì `_publish_latest` đăng đầu ra đã lưu của revision hiện tại qua cổng, KHÔNG gọi model lần hai.
- **P1-2, guard chưa bảo vệ đủ đường.** (a) Sau khi model chạy, cổng quan sát guard lại. (b) `_reconcile` nay chỉ chốt receipt; việc đăng đầu ra đã đối soát đi qua cổng như mọi lần khác, nên guard đã nhảy thì receipt được chốt mà sản phẩm không được đăng. (c) Guard unknown (nguồn chưa hỗ trợ hoặc không đọc được) không còn coi như clear: blocked `guard_unknown`, không đăng, không kết luận, báo người dùng một lần mỗi revision, kiểm lại bằng code sau ít nhất 6 giờ. Kết quả guard đi cùng assessment.
- **P1-3, bản cập nhật bỏ được guard.** Guard đang có được giữ qua mọi bản cập nhật: `guards=[]`, đổi path, đổi evaluator đều chỉ có thể THÊM guard mới, guard cũ giữ nguyên id và điều kiện; phần muốn bỏ hay sửa báo "chưa hỗ trợ". Cùng phạm vi đã chốt cho hạn, chỉ tiêu và ràng buộc ở M2.
- **P1-4, nhận lịch bằng xoá làm mất việc.** `tick` nhận lịch bằng `claim_wake`: CAS trên `due_at` rồi DỜI lịch tới lúc hết hạn nhận (thời gian tối đa một lượt cộng biên), không xoá. Tiến trình chết sau khi nhận mà trước khi `advance` ghi gì thì lịch tự tới hạn lại; `advance` ghi đè hoặc xoá lịch khi đã có trạng thái tiếp theo. Mục tiêu đang bận khoá của lượt khác thì lịch còn đó để chạy sau.
- **P1-5, đạt bước khám phá đóng luôn nhu cầu gốc.** Tiêu chí met ở stage `discovery` không gọi `finish`: mục tiêu chờ `discovery_done`, báo người dùng đây mới là bước tìm hiểu. Kèm sửa một lỗi mặc định từ M2 lộ ra khi sửa ca này: không khai `stage` thì trước đây luôn là `discovery`, nay là `delivery` khi đã có cách hiểu cụ thể (đúng nghĩa chữ S), nếu không mọi mục tiêu bộ não lập mà bỏ trống stage sẽ không bao giờ hoàn thành.
- **P2-1, chỉ có tiêu chí người dùng thì chưa làm đã chờ.** "Chỉ còn chờ người dùng" nay đòi đã có sản phẩm của revision hiện tại khi không có tiêu chí kiểm được nào khác. Mục tiêu chỉ có `human_confirmation` làm ra bản để duyệt trước, tin chờ duyệt kèm link tới bản đó trong vùng làm việc.

Chạy lại `PR-570-M3-checks.py`: script dừng ở assertion REPRO đầu tiên vì lỗi đó đã hết. Một bản sao bọc riêng từng ca cho kết quả: 2 PASS đối chứng vẫn qua (đường cơ bản, hash pilot lưu trữ), cả 8 assertion REPRO đều không còn đúng. Sáu phép thử đột biến trên phần sửa (bỏ cổng sau khi model chạy, coi guard unknown là clear, bỏ kế thừa guard, nhận lịch bằng xoá, cho discovery đóng mục tiêu, cho human-only chờ khi chưa có bản) đều làm test đỏ.

Không chạy lại pilot thật cho phần sửa này: các thay đổi nằm ở cổng kiểm, đối soát và lịch, đều kiểm được tất định bằng engine giả.

### Sửa theo review PR #570 vòng 2

Review vòng 2 (`exports/reviews/PR-570-M3-review-round2.md`, diff `e5a42409..9aad1f5d`) xác nhận sáu nhóm sửa vòng 1 đạt bằng assertion theo hành vi đúng, và nêu một lỗi P1 còn hở của P1-2: cổng kiểm guard chạy TRƯỚC khi đăng, rồi ảnh chụp đó được gắn vào đánh giá SAU khi đăng. Khi guard đọc đúng file sản phẩm và bản mới làm guard sai (ví dụ bỏ mất tiêu đề phải giữ), mục tiêu vẫn bị đóng thành công. Lỗi xảy ra tuần tự, không phải khe tranh chấp đã ghi ở giới hạn.

- **Kiểm bản ứng viên trước khi thay file.** `_publish` đem nội dung sắp ghi kiểm theo mọi guard `artifact_contract` đọc đúng file đích. Bản mới làm guard sai thì giữ bản đang hợp lệ, bản mới ở lại vùng làm việc, ghi sự kiện `publish_blocked_by_guard`.
- **Kiểm lại trên trạng thái cuối.** `_after_publish` chạy lại cổng sau khi đăng rồi mới đánh giá; guard trong assessment là kết quả của lần kiểm này. Bản ứng viên bị guard chặn thì assessment thêm một dòng not_met nêu tên guard, nên không kết luận đạt, không báo `goal.maintained`, và lượt làm lại đưa phản hồi đó cho model.
- **Cả hai đường.** Đường làm việc thường và đường dùng lại đầu ra đã lưu (sau pause, sau gián đoạn) đều đi qua hai bước trên. Đầu ra đã lưu mà hợp lệ thì resume vẫn đăng và đạt KHÔNG tốn thêm lượt model; đầu ra đã lưu làm guard sai thì không đăng, và host làm lại một lượt trong hạn mức có phản hồi về guard.
- **Test:** thêm 7 kiểm tra theo đúng hai kịch bản của review cùng ca đối chứng (`test_resonance_mvp_run.py` lên 99). Bỏ bước kiểm bản ứng viên thì 6 kiểm tra đỏ. Script `PR-570-M3-round2-checks.py`: 10 PASS đầu vẫn qua; ở cả hai ca REPRO guard thật vẫn clear và mục tiêu không bị đóng. Ca resume của script còn một assertion "không có lượt gọi thêm" viết cho trạng thái lỗi; sau sửa, đầu ra vi phạm guard dẫn tới đúng một lượt làm lại có phản hồi, theo thiết kế ở trên.

### Giới hạn và những gì chưa kiểm

1. **Chưa có chính sách khi tới hạn chót.** Không mục tiêu nào bị kết luận `failed`; tới deadline mà chưa đạt vẫn chỉ là chưa đạt. Spec 7 yêu cầu ghi unknown và áp chính sách deadline đã chốt.
2. **Bộ thực thi chỉ có chữ.** Không đọc được file hay dữ liệu của brain; mục tiêu cần dữ liệu thì bộ não phải làm trong lượt chat. Model có thể viết lời khẳng định không kiểm chứng (ví dụ ở pilot).
3. **Một sản phẩm mỗi mục tiêu.** Chỉ tiêu chí `artifact_contract` đầu tiên có `path` được đăng; tiêu chí khác chỉ được đánh giá.
4. **Khe giữa kiểm và ghi khi đăng sản phẩm.** Người dùng sửa file đúng giữa lúc host so hash và lúc thay file thì bản của người dùng có thể bị thay. Chưa có khoá file.
5. **Báo tin ít nhất một lần.** Tiến trình chết giữa lúc gửi và lúc đánh dấu thì tin có thể gửi lặp. Phát lại không trùng tại kho tin nhắn là việc của M4.
6. **Guard.** Chỉ `artifact_contract` đọc được; nguồn khác làm mục tiêu dừng ở `guard_unknown` cho tới khi có adapter; đọc guard không chụp vào kho bằng chứng; guard đã nhảy và guard cũ chưa có đường mở lại hay sửa (lệnh người dùng ở M4).
7. **Bằng chứng không ghim.** Hạn lưu 90 ngày; quá hạn thì đánh giá lại ra unknown.
8. **Thao tác SQLite đồng bộ trong event loop.** Mỗi lần nhỏ, nhưng chưa đưa ra luồng riêng. Mỗi nhịp xử lý tối đa 3 lịch.
9. **Pilot thật chạy ở `9f3dad13`**, trước hai thay đổi cuối (báo `goal.maintained`, danh sách cấm đăng); hai thay đổi đó chỉ kiểm bằng engine giả.
10. **Từ M2 vẫn còn:** việc nền do làn giọng nói tự giao chưa lập mục tiêu; chưa đổi hay bỏ được chỉ dẫn người dùng đã nêu.

### Toàn bộ test Python

| | Main sạch (`7d264236`) | Nhánh M3 (`e07c68cd`) | M3 sau review (`6c840c93`) | M3 sau review vòng 2 (`7ceb987e`) |
|---|---|---|---|---|
| Xanh | 387/403 | 396/411 | 395/411 | 396/411 |
| File đỏ | 16 | 15 | 16 | 15 |
| Đỏ mới so với main | | không có | không có | không có |

Lượt sau review: 15 file đỏ sẵn ở mục M1 cộng `test_project_khung.py` (đỏ trên main sạch, chập chờn).

15 file đỏ trùng đúng danh sách đỏ sẵn ở mục M1. Một lượt chạy trước đó (trên cây đang sửa, giữa hai commit) bị ngắt ở file 408/411 và để lại năm file Zalo/YouTube đỏ liền nhau ngay trước lúc dừng; chạy riêng tám file cuối đều xanh, nên không tính lượt đó.
