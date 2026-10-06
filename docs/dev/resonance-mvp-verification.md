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
