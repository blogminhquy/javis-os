# Resonance A4: biên bản kiểm mã (10/10/2026)

**Trạng thái:** mã A4 viết xong trên nhánh `claude/resonance-a4-handoff-grants` (PR #604, đặt số 0.90.0), **chờ review mã**. Thiết kế chốt vòng 5 tại `6d774bd5` (D1: không cấp quyền ghi từ lời chat), reviewer chấp thuận để code. Chưa pilot model thật, chưa merge, chưa phát hành, không đụng VPS.

Thiết kế: [2026-10-10-resonance-a4-handoff-grants-design.md](../superpowers/specs/2026-10-10-resonance-a4-handoff-grants-design.md) (mục 12 là ma trận; mục 17 là ghi chú triển khai cần reviewer xác nhận). Hướng dẫn: [resonance-a4-grants.md](resonance-a4-grants.md).

## Test đã chạy (máy local, `.venv` của checkout gốc, không model thật)

| File | Kết quả |
|---|---|
| `tests/python/test_resonance_a4_grants.py` (kho thật, engine giả, đồng hồ giả) | 90 kiểm đạt |
| `tests/python/test_resonance_a4_transport.py` (plugin thật, hub HTTP thật với `X-Javis-Turn`, server MCP plugin của Claude SDK thật, `main.app`) | 14 kiểm đạt |
| `tests/python/test_resonance_a4_rollback.py` (mã 0.89.0 thật, `33a3c1aa`, qua `git show`) | 11 kiểm đạt |
| `tests/js/test_resonance_a4_ui.js` | 20 kiểm đạt |
| 31 file test Resonance cũ (M1 tới M5, A1 tới A3) và 5 test giao diện Resonance cũ | đều đạt (14 file sửa kỳ vọng hay thêm `RA.preapprove()`, xem dưới) |
| Toàn repo `tests/run.py` (637 file) | 619 xanh; 18 đỏ, phân định ở mục "Toàn repo" |

Lệnh chạy lại:

```bash
python tests/run.py resonance -v
python tests/run.py resonance_a4 -v
```

## Đối chiếu ma trận (thiết kế mục 12)

| Nhóm ca | Ở đâu | Ghi chú |
|---|---|---|
| G1, G2 (`narrow`) | a4_grants | phần giao; mục tiêu khác từ chối; thao tác lạ rỗng |
| G13, G45 (khoá đường, D15) | a4_grants | `a/../a` được `_brain_file` nhận nhưng khoá đường từ chối; `.`, `..`, tuyệt đối, ký tự điều khiển, đuôi lạ, thư mục cấm; chữ hoa thường trên Windows. Symlink ra ngoài: dùng lại kiểm của `_brain_file` (test cũ), không dựng symlink trên Windows |
| G15, G27, G51 tới G55, G73 tới G79 (D1) | a4_grants | sáu câu (lệnh trực tiếp, phủ định, điều kiện, câu hỏi, ví dụ minh họa, câu cần dịch): chờ cho phép, không gốc, không gọi model, không ghi file; `begin_action` ném `GrantError(scope_pending)` |
| G57 tới G61 (bản nháp, Cho phép, Không, thẻ cũ) | a4_grants, a4_transport | đăng đúng bản nháp, 0 lượt model; thẻ cũ 409; lượt cũ `scope_decided` |
| G23, G24 (đổi đích, cùng đích) | a4_grants | |
| G17, G36, G37, G41 | a4_grants | |
| G38, G39 (Write A + nộp B) | a4_grants | |
| G10, G44, G46, G5, G20 | a4_grants, a4_transport | phát lại sau thu hồi trả biên nhận `stale` |
| G30, G43, G85 (chọn liên kết) | a4_grants | |
| G29, G70, G80 tới G84 (thứ tự quyền) | a4_grants | gồm `created_at` bị đặt lùi về 0: vẫn không nhận gốc cấp lại sau ảnh chụp |
| G31, G32, G33 (mốc commit với thu hồi) | a4_grants | |
| G62, G64, G65, G66 (khởi động lại, đối soát) | a4_grants | tiếp nhận đúng một lần khi chạy đối soát hai lần |
| G67, G68, G69 (nhiều revision một tin) | a4_grants | |
| G7 (thu hồi khi lượt nền đang chạy) | a4_grants | |
| G34 (thu hồi giữa phép thử) | a4_grants | cổng lượt thử dừng; không mở được phép thử mới (`GrantError(grant_revoked)`) |
| G40 (một phần: chết giữa ý định và mốc commit) | a4_grants | đối soát huỷ, bản nộp về `candidate`, lần thức sau đăng, 0 lượt model |
| G72 (cổng `_gate` vẫn chạy) | a4_grants | tạm dừng |
| G86 (tác động đã commit dưới quyền đã thu hồi) | a4_grants | |
| G47, G28, G49, G48, G50 (nâng, legacy, hạ) | a4_grants, a4_rollback | G48 chứng minh giới hạn đã công bố là đúng sự thật, KHÔNG chứng minh đã chặn |
| G22 (khả năng engine, đường truyền thật) | a4_grants, a4_transport, a1_gates | Grok, Antigravity: không có khoá lượt nên hub trả lỗi, không ghi bản nộp |
| G18 | a4_grants | |
| G3, G4, G6, G8, G9, G11, G12, G14, G35, G42 | test cũ và a4_grants một phần | G3: A4 không có đường giao tiếp nào (không có công cụ); G4, G11: danh tính chỉ từ ngữ cảnh lượt (A1); G12: prompt không chứa bản nháp; G14: Write native không biên nhận thành bytes lạ (G39) |

**Chưa có ca riêng (nêu thật):** G40 đầy đủ (tiêm lỗi ở MỌI điểm của mục 4.7; mới có chết giữa ý định và mốc commit, G62 tới G66 và G86), G71 (khe giữa mốc commit và `os.replace`, giới hạn đã công bố).

## Soát nội bộ trước review

Một lượt soát độc lập (agent chỉ đọc, có chạy thử trên kho tạm) tìm sáu lỗi; đã sửa cả sáu, mỗi lỗi có ca hồi quy R1 tới R5 trong `test_resonance_a4_grants.py` (lỗi 6 phủ bởi G38):

1. **Lách quyền:** đường sản phẩm có `.` hay đoạn rỗng (`./Inbox/x.md`) làm khoá đường rỗng, phạm vi rơi thành `none`, Write trong lượt chat được tiếp nhận không cần cho phép. Sửa: có đường thô mà không có khoá thì phạm vi `invalid` (chặn, `path_rejected`); `_artifact_params` từ chối `.` và `//` ngay lúc lập.
2. `ensure_scope_request` vỡ khoá duy nhất khi còn yêu cầu chờ của revision trước (đường nâng lại §7.4). Sửa: thay yêu cầu cũ trước.
3. `os.replace` lỗi sau mốc commit bị chốt `conflict`. Sửa: để hành động chạy, đối soát hoàn tất theo luật tác động đã commit.
4. Chốt guard có thể bị cổng ghi đè ở hai chỗ gọi mới. Sửa: `_gate` trả ngay khi đang chốt guard.
5. Đang thu hồi, lời sửa của model dựng lại thẻ Cho phép (thành cấp lại qua thẻ). Sửa: `_scope_sync` không tạo yêu cầu khi gốc cuối là `revoked`.
6. Bàn giao Write A rồi nộp B nhả lịch trước khi đăng B. Sửa: tiếp nhận A không nhả lịch (`release=False`), bước đăng B mới đóng bàn giao.

## Test cũ phải sửa vì hành vi đổi theo thiết kế

- 13 file thêm `RA.preapprove()`: đóng vai chủ dự án bấm Cho phép ngay sau mỗi lần lập, sửa, gán mục tiêu, để nội dung kiểm cũ giữ nguyên. Lượt chat lập mục tiêu vẫn không nhận quyền mới (đúng luật thứ tự quyền).
- `test_resonance_a1_gates.py` ca 7 (tắt bật trợ lý giữa lượt): bản nộp của lượt cũ `stale`, lần sau làm lại một lượt thay vì đăng lại đầu ra giữ (ghi chú I5). Ca 11: Write trong lượt lập không được tiếp nhận (D1). Ca 12: Codex và engine API nộp được qua công cụ.
- `test_resonance_mvp_main.py` lượt 302 và `test_resonance_e2e_achieve_harness.py` P2-2, `test_resonance_inline_handoff.py`: bàn giao bản chat chuyển sang lượt CẬP NHẬT sau khi đã cho phép (lượt lập không có quyền).
- `test_resonance_a1_turn_agent.py`: lượt của trợ lý mang thêm `authority_seq` và `provider`.
- `test_resonance_a2_ui.js`: thêm nhãn lý do thức `scope_granted`.
- `tests/python/route_table.json`: thêm đúng một route ở cuối bảng (`GET /goals/{goal_id}/drafts/{submission_id}`, đăng ký qua `register_a4` sau mọi route cũ).

## Ranh giới bằng chứng

- Engine giả và đồng hồ giả; không có lượt model thật, không chạy server thật ngoài `TestClient`.
- Test rollback chạy mã 0.89.0 thật lấy bằng `git show 33a3c1aa`.
- Chưa kiểm giao diện bằng trình duyệt thật (chỉ hàm thuần của thẻ).
- Các điểm I1, I2 ở mục 17 của thiết kế chạm cơ chế quyền và **cần reviewer xác nhận**.

## Toàn repo

`tests/run.py` chạy đủ 637 file trên máy Windows này: 619 xanh. 18 file đỏ, phân định:

- 14 file đỏ sẵn trên `main` sạch của máy này (môi trường, đã ghi từ trước): `test_agy_prompt_dai`, `test_antigravity_cli`, `test_ba_loi_mac_va_telegram`, `test_cai_windows`, `test_grok_cli`, `test_install_admin`, `test_link_file_uri`, `test_machine_translations`, `test_memory_hoa_thuong`, `test_model_theo_phien`, `test_ollama_local`, `test_terminal`, `test_windows_no_console`, và `test_ignore_files` (thư mục `exports/` chưa track).
- `test_khoi_dong_nhe` (tỉ lệ thời gian nạp `main`): đỏ cả trên worktree sạch `6d774bd5` khi máy đang chạy bộ test lớn (6,29 và 6,50 lần, bản A4 5,16 và 5,17 lần); không do A4.
- `test_hoi_thoai_nhom`: chạy lại riêng thì xanh.
- `test_route_table`: do route mới; đã chuyển route xuống cuối bảng và chụp lại (thêm đúng 1 mục).
- `test_update`: báo nhầm, khoá cache crc32 của `style.css` mới đổi thành `72de33ed`, chứa chuỗi `?v=72` mà test cấm theo chuỗi con. Sửa test so nguyên khoá.

Sau các sửa trên, chạy lại `resonance`, `test_update`, `route_table` trên mã cuối: 45/45 xanh. Log đủ ở `exports/reviews/A4-code-full-suite.log` (ngoài git).
