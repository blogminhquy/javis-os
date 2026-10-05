# Kiểm chứng Javis Resonance MVP

Báo cáo này ghi những gì đã chạy thật cho từng mốc của [kế hoạch MVP](../superpowers/plans/2026-10-06-resonance-00-mvp.md). Mỗi mục tách rõ phần chạy với engine giả và phần chạy với engine thật. Điều gì chưa kiểm được thì ghi là chưa kiểm.

## M1: đường chạy engine và receipt do host quan sát (06/10/2026)

### Nền mã và môi trường

| Mục | Giá trị |
|---|---|
| Commit nền | `origin/main` = `7d264236b61e10077dc7833c1b063076023ea7bb` (0.83.2), fetch ngày 06/10/2026 |
| Nhánh, PR | `claude/resonance-mvp-m1`, PR #566 (nháp), phiên bản xí chỗ 0.84.0 |
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
| `aux_engine.strip_tools` | Lột hub và MCP của engine API, Codex, Grok; bỏ Antigravity và loại lạ, lùi về engine Claude gốc | Dùng |
| `main._reply_policy_sandbox_engine` | Claude trong thư mục trống, `allowed_tools` cố ý không khớp công cụ nào, MCP trống, cấm thêm công cụ native | Dùng, thêm tham số `cwd_name` để có thư mục trống riêng `resonance_cwd` |
| `main._workflow_agent_helpers`, `main._run_workflow_step` | Agent chạy với `cwd` là brain và có công cụ, dành cho workflow | Không dùng: cấp quyền rộng hơn một lượt chỉ chữ cần |
| `agent_runtime.AgentRunner` | Chỉ nhận khi `agent_canary` bật và slug nằm trong danh sách | Không phải đường live: trong cài đặt thật `allocation_basis_points = 0`, `allowed_slugs = []`. Không bật |
| `workflow_runtime.WorkflowCanary` | Tương tự | Không phải đường live: `allocation_basis_points = 0`. Không bật |
| `evidence_store.EvidenceStore.put` | Cần `TurnTrace` của `context_runtime`, mã hoá artifact | Chưa nối ở M1, thuộc M3 |
| `self_improve` | Loop dựng Claude rồi swap | Chỉ tham khảo, không sửa |
| `mcp_hub` | Hub công cụ | Không sửa; engine chỉ chữ không qua hub |

### Đường đã chốt

- `resonance.GoalDeps.run_once(goal, prompt, action_id) -> ActionReceipt`.
- Engine do `main._resonance_engine` dựng. Hàm này lấy engine Claude trong thư mục trống, swap theo engine việc nền ở mức `suggest`, chạy `strip_tools`, rồi `resonance.pick_text_only_link` giữ đúng mắt người dùng đã chọn.
- Nếu mắt đầu không phải provider đã chọn, hàm trả `None` kèm lý do và lượt đó thất bại với `engine_blocked`. Lý do là swap có thể tự lùi về Claude, và Resonance không được tự đổi provider.
- Model chỉ sinh chữ. Host ghi đầu ra vào `output_root` của mục tiêu, tên file là `action_id`. Host đọc lại byte vừa ghi để tính SHA-256.
- Receipt ghi các mục: trạng thái, engine thật sự chạy, đường dẫn và hash đầu ra, usage, số lần gọi công cụ, mã lỗi.
- Usage không đo được thì ghi `None`, không bao giờ ghi 0.
- Hạn mức: giữ một chỗ trước khi gọi. Nếu dừng trước lúc gọi model thì trả chỗ lại.
- Chạy lại cùng `action_id` bị từ chối với `action_exists` và không gọi model.
- Chưa có nơi nào ngoài test gọi `_resonance_engine`. Resonance vẫn tắt với người dùng.

### Kết quả với engine giả

Lệnh chạy:

```
python tests/run.py resonance_mvp_integration -v
```

Kết quả: 54 kiểm tra xanh, CI chạy được vì không gọi model. Các nhóm đã kiểm:

- **Thành công:** host ghi file, SHA-256 khớp đúng byte trên đĩa, file dùng LF, usage lấy từ sự kiện `final` của Claude SDK.
- **Usage của engine API:** cộng đúng từ sự kiện `usage`. Usage vắng thì ghi `None`.
- **Lặp `action_id`:** model chỉ được gọi một lần, không tốn thêm lượt.
- **Hết hạn mức:** không dựng engine, không gọi model.
- **Thất bại không ghi file:**
  - engine trả lỗi;
  - mất đăng nhập nhưng trả `final`;
  - đua làm mới token;
  - gọi công cụ trong lượt chỉ chữ;
  - đầu ra rỗng;
  - không có `final`;
  - engine chưa sẵn sàng;
  - factory báo chặn hoặc ném lỗi;
  - quá giờ.
- **Đối soát hạn mức:** dừng trước lúc gọi model thì trả chỗ, đã gọi model thì tính một lượt.
- **Vùng ghi chưa cấp và `action_id` lạ:** bị chặn trước khi dựng engine.
- **Bộ chọn engine chạy trên `aux_engine.swap` và `strip_tools` thật, với cài đặt giả:**
  - có key OpenRouter thì swap dựng chuỗi dự phòng, bộ chọn giữ đúng Claude và bỏ mắt sau;
  - không có chuỗi thì giữ nguyên Claude;
  - chọn Antigravity bị lùi về Claude thì chặn;
  - chọn OpenRouter thì giữ mắt API đã tắt công cụ;
  - Codex và Grok được nhận đúng provider, không bị chặn oan.

### Kết quả pilot thật

Lệnh chạy, với hai đường dẫn đặt theo máy:

```
JAVIS_RESONANCE_PILOT=1 JAVIS_RESONANCE_PILOT_SETTINGS=D:/Project/Javis-OS/server/settings.json JAVIS_RESONANCE_PILOT_CALLS=1 python tests/python/test_resonance_mvp_integration.py
```

- **Đầu vào:** một danh sách việc mô phỏng ghi rõ là không có thật, yêu cầu một ghi chú Markdown có ba gạch đầu dòng.
- **State:** `JAVIS_STATE_DIR` là thư mục tạm. Settings tạm chỉ chứa khối chọn engine (`auxiliary`, `main`, `engine`, `claude_model`), không có khoá nào.
- **Ghi:** không ghi gì vào state thật.

Đã chạy hai lần, tổng cộng 2 lượt gọi model trên trần 5 lượt được cho phép.

| | Lần 1 | Lần 2 (code cuối) |
|---|---|---|
| Commit | `24611b4b` cộng `main.py` chưa commit; đường thành công giống hệt bản cuối | `2404fc70` |
| Trạng thái receipt | `succeeded` | `succeeded` |
| Engine thật sự chạy | `anthropic-cli` / `sonnet` / `ClaudeSDK`, khớp engine đã chọn | như lần 1 |
| Số mắt dự phòng bị bỏ | 0 | 0 |
| Gọi công cụ quan sát được | 0 | 0 |
| Đầu ra host ghi | 630 byte, 471 ký tự | 335 ký tự |
| SHA-256 tính lại độc lập trên đĩa | khớp | khớp |
| Thời gian lượt | khoảng 7,9 giây | 5,96 giây |
| Token vào / ra (Claude Code tự báo) | 17.893 / 421 | 17.888 / 197 |
| `cost_usd` (Claude Code tự báo) | 0,0758 | 0,0203 |
| Chạy lại cùng `action_id` | `cancelled` / `action_exists`, không gọi model | như lần 1 |
| Hạn mức | 1 trên 1 lượt | 1 trên 1 lượt |

Ở cả hai lần, đầu ra đúng yêu cầu: tiêu đề `# Việc đang dở` và ba gạch đầu dòng, mỗi gạch có một bước kế tiếp.

**Kết luận M1:** trên máy này có một đường chạy được. Đường đó là engine việc nền người dùng đã chọn (Claude Code, sonnet), dựng qua `aux_engine` ở chế độ chỉ chữ, và trả về một receipt mà host quan sát được. Đây là kết quả của một lượt chỉ chữ trên dữ liệu mô phỏng, chưa phải bằng chứng cho một vòng mục tiêu đầy đủ.

### Giới hạn và những gì chưa kiểm

1. **Chỉ gọi thật engine Claude.** Codex, Grok và engine API mới được kiểm qua bộ chọn với đối tượng giả hoặc cấu hình giả, chưa gọi thật.
2. **Pilot không có key OpenRouter.** Trong pilot, swap không dựng mắt OpenRouter nên không có mắt nào để bỏ. Trường hợp "có chuỗi dự phòng thì chỉ giữ mắt đầu" mới được kiểm bằng `aux_engine.swap` thật với cài đặt giả, chưa kiểm bằng lượt gọi thật.
3. **`cost_usd` không phải tiền bị trừ.** Đây là con số Claude Code tự báo. Trên gói thuê bao nó là số quy đổi. Phần lớn khoảng 17.900 token vào là system prompt mặc định của Claude Code.
4. **Chống chạy trùng còn khe hở.** Cơ chế hiện dựa vào file đầu ra theo `action_id`. Nếu hai tiến trình cùng chạy một id, vẫn còn khe hở nhỏ giữa lúc kiểm và lúc đổi tên file. M3 thay bằng khoá và idempotency trong SQLite.
5. **Trạng thái `uncertain` chưa dùng.** Lượt chỉ chữ không có tác động ra ngoài nên chưa cần tới.
6. **Receipt chưa vào EvidenceStore.** `evidence_ids` hiện rỗng. M3 nối phần này.
7. **Codex ở mức suggest chạy sandbox read-only.** Sandbox đó vẫn đọc được file ngoài thư mục trống. Máy này không dùng Codex cho việc nền nên chưa ảnh hưởng.
8. **`requested_provider` là spec sau phanh ngân sách.** Nếu chủ bật tự phanh và đã vượt trần tháng, `aux_engine.read_spec` có thể đã hạ engine trước khi Resonance thấy.
9. **Pilot để lại transcript.** Pilot mở một phiên Claude Code trong thư mục tạm, và Claude CLI lưu transcript của phiên đó trong `~/.claude/projects` như mọi phiên khác.
10. **Lần 1 rơi đúng cửa sổ token sắp hết hạn.** Cổng xếp hàng làm mới token (`claude_token_gate`) có kích hoạt, ghi nhãn `di-truoc`, và cho lượt này đi trước. Claude CLI tự làm mới token như lượt chat thường. Không có lỗi đăng nhập.
11. **Không chạy test JS.** M1 không đổi file JS nào.

### Toàn bộ test Python

Chạy `python tests/run.py --py` hai lần: một lần trên main sạch trước khi sửa, một lần trên nhánh M1 sau khi sửa.

| | Main sạch (`7d264236`) | Nhánh M1 (`2404fc70`) |
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

`test_project_khung.py` đỏ trên main sạch nhưng xanh trên nhánh M1. M1 không đụng mã mà test này kiểm, nên nhiều khả năng đây là test chập chờn chứ không phải được M1 sửa.
