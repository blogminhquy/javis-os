# Resonance A4: biên bản kiểm mã (10/10/2026)

**Trạng thái:** mã A4 trên nhánh `claude/resonance-a4-handoff-grants` (PR #604, số 0.96.0; đánh số lại bốn lần vì `main` đi qua 0.91.0, 0.92.1, 0.94.0 rồi 0.95.1) đã sửa theo **review mã vòng 1** (`a3356165`: 1 P1, 3 P2) **vòng 2** (`7b47e246`: 3 P2) và **vòng 3** (`d26c0f09`: 1 P2); **review mã vòng 5 đạt tại `5b5e3ef0`** (không còn P1, P2 chặn). Sau đó: smoke giao diện trên sandbox bằng engine giả (một lỗi thẻ đã sửa ở `f6aeb6d1`) và bộ chạy pilot (review cổng pilot đạt tại `5305687a`, dry 13/13). **Pilot thật đã chạy MỘT lần** tại `5305687a` (chủ dự án duyệt 11/10): 2 lượt chat Claude Code `claude-opus-5-5` qua gói thuê bao, 0 việc nền; kết quả gốc `technical_failed` do bộ chạy, đã khép bằng hậu kiểm offline (mục "Pilot thật real-1"). Thiết kế chốt vòng 5 tại `6d774bd5` (D1: không cấp quyền ghi từ lời chat), reviewer chấp thuận để code. Review tích hợp và review cuối đạt tại `3606362c`; **đã phát hành 0.96.0** (`d36ebb3e`, PR #604, 11/10/2026; CI `main` run 38146898745 và build image run 38146898746 thành công; image `ghcr.io/blogminhquy/javis-os:0.96.0`, digest `sha256:8f1751d2…`; VPS chưa kéo). Pilot real-1 chạy trên `5305687a`, không phải trên bản tích hợp.

Thiết kế: [2026-10-10-resonance-a4-handoff-grants-design.md](../superpowers/specs/2026-10-10-resonance-a4-handoff-grants-design.md) (mục 12 là ma trận; mục 17 là ghi chú triển khai cần reviewer xác nhận). Hướng dẫn: [resonance-a4-grants.md](resonance-a4-grants.md).

## Test đã chạy (máy local, `.venv` của checkout gốc, không model thật)

| File | Kết quả |
|---|---|
| `tests/python/test_resonance_a4_grants.py` (kho thật, engine giả, đồng hồ giả) | 124 kiểm đạt |
| `tests/python/test_resonance_a4_transport.py` (plugin thật, hub HTTP thật với `X-Javis-Turn`, server MCP plugin của Claude SDK thật, `main.app`) | 14 kiểm đạt |
| `tests/python/test_resonance_a4_rollback.py` (mã 0.95.1 thật, `adb103ed`, bản cuối trước A4, qua `git show`) | 11 kiểm đạt |
| `tests/js/test_resonance_a4_ui.js` (gồm hành vi `send()` thật với phản hồi server giả) | 27 kiểm đạt |
| `tests/python/test_resonance_a4_pilot.py` (`JAVIS_RESONANCE_A4_PILOT=dry`, server thật, lượt chat mô phỏng) | 13/13 ca, 0 lượt thật, mỗi ca xác minh 0 lượt engine; không đặt biến thì bỏ qua |
| `tests/python/test_resonance_a4_pilot_gate.py` (mã thật của bộ chạy nạp bằng AST, không server, không model) | 133 kiểm đạt |
| 31 file test Resonance cũ (M1 tới M5, A1 tới A3) và 5 test giao diện Resonance cũ | đều đạt (14 file sửa kỳ vọng hay thêm `RA.preapprove()`, xem dưới) |
| Toàn repo `tests/run.py` (639 file, lần chạy cuối tại `f6aeb6d1`) | 625 xanh; 14 đỏ, đều do môi trường, phân định ở mục "Toàn repo" |

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

## Smoke giao diện trên sandbox (sau review vòng 5)

Server sandbox cổng 7788, state và brain riêng (`exports/sandbox-a4`, ngoài git), nhịp tắt, engine giả có bộ đếm, khoá file THẬT trên Windows (một tiến trình giữ file: chặn `os.replace`, hay chặn cả đọc). Chromium qua Playwright, desktop 1366x860 và khổ hẹp 375x812, tiếng Việt; hộp xác nhận gốc trả lời thật, tab thứ hai thật. Biên bản và 16 ảnh: `exports/reviews/A4-ui-sandbox-record.md`, `exports/reviews/a4-ui/` (ngoài git).

Đạt, đối chiếu kho và hash file:
- xin quyền đích mới, xem trước đúng bản nháp, Cho phép đăng đúng bytes, 0 lượt engine;
- Không cho phép; thẻ cũ trả 409 sau khi tab khác đã bấm; tạm dừng giữ bản 2; thu hồi (Huỷ không gửi gì, Đồng ý thì bản 2 `stale`); cấp lại không làm sống lại bản 2;
- file đích có sẵn: báo chưa đăng, giữ file; file nháp khoá: giữ bản, thử lại thưa dần, mở khoá đăng đúng bản; file đích khoá: gác `publish_settling`, khởi động lại và F5 thẻ "Đang hoàn tất lần đăng đã chốt", mở khoá đăng đúng bản 2; file đã đăng bị sửa tay: `source_drift`, không ghi đè;
- khổ hẹp không cuộn ngang.

**Lỗi tìm ra, đã sửa (`f6aeb6d1`):** ở trang Cộng sự, thẻ chat bị thu gọn và câu báo "Đã cho phép và đăng…" rơi vào thẻ ngăn trợ lý đang ẩn (thẻ cuối trong DOM). Có từ 0.87.0; nay thẻ ngăn trợ lý luôn đầy đủ và luật "thẻ mới nhất" chỉ xét thẻ chat. Hai kiểm mới trong `test_resonance_a4_ui.js`, đỏ trên mã cũ.

**Câu hỏi thiết kế, chưa đổi:** Cho phép gặp file đích có sẵn của chủ dự án (không baseline) thì lịch làm việc vẫn chạy lượt việc nền (sandbox: 3 trên hạn mức 4, mỗi bản đều xung đột) rồi dừng `stalled`. Đây là hành vi MVP đã review (kiểm "3a"); thử đổi làm đỏ 5 file test cũ nên trả lại. Cần chủ dự án quyết.

## Bộ chạy pilot A4 (đã chạy thật một lần, xem "Pilot thật real-1")

`tests/python/test_resonance_a4_pilot.py`. Real chạy Claude Code (gói thuê bao) ở lượt chat của trợ lý, tối đa 2 lượt (sổ giữ chỗ fsync trước mỗi lần gửi, đóng khi có lỗi, không đặt lại), trần kho 0 cho mọi tiến trình server. Dry 10 ca: chính, cổng chi phí, cổng xác thực, thẻ cũ 409, biên nhận đăng không thành, lỗi engine, không nộp, tự ghi file đích, thiếu bằng chứng, sổ còn giữ chỗ. Đơn xin chạy: `exports/reviews/A4-pilot-run-request.md` (ngoài git). Engine khác Claude Code chỉ kiểm bằng engine giả.

**Review cổng pilot (`1719303d`): 3 P2 trong bộ chạy, đã sửa.**

| Điểm | Sửa |
|---|---|
| P2-1: có `turn_done` là ghi thành công | Chỉ `engine_status == ok` và `turn_status == completed` là thành công; `ws_chat` giữ nguyên siêu dữ liệu `turn_done`. Lỗi engine, không rõ, huỷ, thất bại, thiếu trạng thái, không có `turn_done`: vẫn tính lượt, đóng sổ, lỗi kỹ thuật (không phải định tuyến) |
| P2-2: kiểm hỏng vẫn gọi lượt 2 | Cổng nằm trong `reserve` của sổ (kiểm bắt buộc đã hỏng, hay token không đạt trước lượt đó: không giữ chỗ, không gửi); tiền điều kiện của bước có tác động là kiểm cứng (dừng ngay); cổng tường minh trước Cho phép và trước lượt 2; kiểm đăng nhập và hạn token trước MỖI lượt |
| P2-3: phiên rỗng vẫn đạt | `audit_notices`: mỗi tin outbox loại được gửi có đúng một tin trong phiên, đúng mục tiêu, có biên nhận; không khoá lạ hay lặp, không tin chờ; rỗng không đạt; phải có tin ở revision cuối; dựng lại lần hai (D) không đổi tập tin |

Hồi quy bền: `tests/python/test_resonance_a4_pilot_gate.py` nạp mã thật của bộ chạy (sổ, `chat`, `ws_chat`, `audit_notices`, đoạn điều phối trước lượt 2) và chạy với nguồn khung giả, không server, không mạng, không model. Dry thêm ca `contract`, `token`, `notice`.

Sự cố trong lúc sửa: một ca dry thử đi qua `/ws` với bộ não API không khoá, settings thiếu `engine`, nên runtime lùi về Claude Code và chạy 1 lượt thật bằng gói thuê bao. Đã bỏ đường đó: dry không bao giờ gửi tin qua `/ws`, mỗi ca dry kiểm bộ đếm lượt engine của server sandbox phải bằng 0. Hồ sơ ngoài git: `exports/reviews/a4-pilot-incident-2026-10-11/`.

**Review cổng pilot vòng 2 (`da2b8c0b`): 1 P2 ở hậu kiểm dry, đã sửa.**

- Số đếm KHÔNG đọc được không bao giờ thành 0. Hai sổ lượt của server sandbox (`usage.json`, `usage-events.jsonl`) được tạo sẵn, rỗng và hợp lệ, trước khi dựng server. Chỉ báo 0 khi đọc được, đúng cấu trúc và hai sổ khớp. Ngoài ra là `None` kèm lý do `unverified: ...`, và kiểm dry hỏng.
- Ca nào báo khác 0 đã xác minh (có lượt, không xác minh được, có lượt thật, không có báo cáo): bộ điều phối dry DỪNG CẢ ĐỢT, không mở ca kế tiếp. Ca đó giữ nguyên thư mục (state, sổ usage như lúc phát hiện, log server) và bộ điều phối chép vào hồ sơ. Ca âm đúng kỳ vọng mà đã xác minh 0 lượt thì vẫn chạy tiếp.
- Đây là HẬU KIỂM, không phải chốt chặn: `usage_store` bỏ lượt không có token và ghi kiểu cố gắng. Chốt chặn của dry vẫn là `ws_chat` từ chối gửi tin khi không phải real.
- Hồi quy trong `test_resonance_a4_pilot_gate.py`, chạy đúng nút AST của bộ chạy.
- **Vòng 3 (`dd2b1d58`):** sổ từng lượt đã tạo sẵn nên BẮT BUỘC còn và đọc được (mất sổ là không xác minh được, không bỏ đối chiếu); mỗi mục `total` bắt buộc có `turns` là số nguyên không âm (không mặc định 0). `total = {}` với sổ từng lượt rỗng vẫn là 0 hợp lệ. Hai phản ví dụ đi trọn chuỗi: không xác minh được, kiểm hỏng, giữ bằng chứng, dừng cả đợt. Test: 84 kiểm.

Lời giao: hai bộ đầu vào ghim hash. v1 là lời gốc, có thể được làm ngay trong lượt, đúng như lượt lọt cho thấy. v2 là đề xuất giao trách nhiệm sau lượt. Real bắt buộc chọn bộ đã duyệt.

### Pilot thật real-1 (11/10/2026)

**Phạm vi.** Chạy đúng MỘT lần, theo lời duyệt của chủ dự án, trên bản checkout tách riêng ở commit đã review `5305687a` (0.93.0 lúc đó; cây sạch). Một mẫu, một engine: Claude Code `claude-opus-5-5` qua gói thuê bao (`authMethod: claude.ai`, `firstParty`), bộ đầu vào v2. Không chứng minh Codex, Grok, Antigravity hay bảy engine API; không kiểm lượt việc nền bằng model thật. Đây KHÔNG phải bằng chứng đã chạy thử bản tích hợp 0.96.0.

**Hạn mức.** Sổ lượt chat 2/2, cả hai `ok` và `completed`; trần kho 0 giữ qua bốn server, 0 lượt engine cấp kho; bộ đếm lượt engine của server sandbox 2, đã xác minh. Token: 534.079 vào, 5.152 ra; app ước tính 1,23 USD, trong gói thuê bao. Không thử lại, không API trả phí.

**Kết quả gốc giữ nguyên:** `acceptance: technical_failed`, chỉ hai kiểm đối chiếu tin báo hỏng. Báo cáo, sổ và hai sản phẩm không sửa. Hash: báo cáo `3ab7aaf9…4b4a3`, bản 1 `80e28006…3b6a1` (662 byte), bản 2 `135ac274…90c6e` (827 byte).

**Nguyên nhân: lỗi bộ chạy, không phải lỗi giao tin.** Host đặt thẻ `turn:<message_ref>` sau mỗi lượt chat lập hay sửa mục tiêu (`_resonance_push_card`); `audit_notices` cũ đòi tập khoá phiên bằng đúng tập `outbox:<id>` nên loại nhầm hai thẻ đó. Dry mô phỏng lượt chat nên không có thẻ turn; review cổng pilot cũng chưa thấy. Tin báo bắt buộc `outbox:3` (`goal.waiting_human`, revision 2) có đúng một tin, đúng phiên, có biên nhận khớp chính tin, không lặp sau hai lần dựng lại.

**Sửa bộ chạy (`8582bdd6`), không đổi mã sản phẩm.** `read_notice_evidence` đọc chỉ đọc (SQLite `mode=ro`), dùng chung cho bộ chạy và hậu kiểm offline. Biên nhận chỉ tính khi dòng biên nhận duy nhất của (khoá, mục tiêu) trỏ đúng phiên và đúng CHÍNH tin đó. Thẻ turn chỉ được có thêm khi message_ref thuộc chính phiên và kho mục tiêu có sự kiện `created`, `reframe` hay `continued` cùng mục tiêu, cùng message_ref, cùng revision; thẻ turn không bao giờ thay tin outbox bắt buộc. Khoá lạ, khoá lặp vẫn không đạt. Test cổng thêm ba thẻ thật làm fixture và các ca âm (chỉ có turn, thiếu hay sai biên nhận, sai mục tiêu hay phiên, không nối sự kiện, lặp, khoá lạ, outbox revision cũ). Đối chứng: test mới trên bộ chạy `5305687a` đỏ đúng ca ba thẻ thật.

**Hậu kiểm offline** trên bản sao dữ liệu đã lưu, chỉ đọc, không dựng server, không xác thực, không gọi engine: bộ đối chiếu mới cho `matched_ok` và `required_ok` đúng; hàm cũ trên cùng dữ liệu tái hiện kết quả sai; cây bằng chứng 85 file không đổi byte nào. Script hậu kiểm độc lập của reviewer: 16 kiểm đạt. Hồ sơ ngoài git: `exports/reviews/A4-real-1-postcheck.md`.

**Bốn điều cần chứng minh, theo hậu kiểm:** lượt 1 lập đúng một mục tiêu của trợ lý và nộp qua `javis_submit_deliverable`, host giữ nháp chờ quyền, không có file đích; Cho phép đăng đúng bytes đã giữ, không gọi model; lượt 2 sửa mục tiêu, bản 2 được host tự đăng, không hỏi lại quyền; dựng lại hai lần không gọi thêm, tin báo đúng và không lặp. Ghi nhận phụ: lần gọi `javis_goal` đầu của lượt 1 bị host từ chối (thiếu `at_iso` đọc được), bộ não tự sửa trong cùng lượt.

**Nội dung (reviewer).** Bản cuối (revision 2) ĐẠT: đủ ý, mục Việc tiếp theo đúng người và hạn, giữ nguyên lời hẹn "thứ Hai tuần sau". Bản 1 CHƯA ĐẠT hoàn toàn: tự thêm ngày "(19/10/2026)" không có trong lời giao (11/10 là Chủ nhật, theo cách tính thông thường "thứ Hai tuần sau" là 12/10). Lỗi này giữ nguyên trong hồ sơ; bản cuối đã bỏ ngày đó. Không tuyên bố chất lượng model ổn định từ một mẫu.

## Review mã vòng 3 (`d26c0f09`) và cách sửa

| Điểm | Sửa | Hồi quy (bản nộp `candidate` còn lại sau khi tiến trình bị ngắt, mở lại kho, `tick` thật) |
|---|---|---|
| P2: lỗi đăng phát sinh ngay trong lần thức làm việc vẫn mở lượt model (thay file sau mốc commit; đọc file nháp trước mốc commit) | Xét lại nghĩa vụ sau `_publish_latest` rồi gác `publish_settling`; file nháp chưa đọc được thì giữ bản nộp, lịch `settle` thử lại bằng code có giãn cách (I16) | V3, cho cả hai vị trí lỗi: lần thức đầu 0 lượt engine, `calls_used` 0, không action work, lý do làm việc còn chờ; lỗi kéo dài 20 nhịp 30 giây có mở lại kho: thức thưa dần, không mở model; hết lỗi: đăng đúng bản đã giữ một lần, tiếp nhận một lần, gỡ gác, không còn lịch `settle`; đối chứng không lỗi đăng ngay |

**Bản nộp đang giữ khi mục tiêu đổi trạng thái** (bổ sung lúc chốt vòng 3): tạm dừng, thu hồi, huỷ, đổi revision trong lúc giữ thì hết khoá vẫn không tự đăng bản cũ, nghĩa vụ giữ được bỏ, không còn lịch `settle`; đổi revision thì bản mới hơn được đăng. Trong cùng revision, bản khác nội dung bị từ chối `submission_conflict`, bản đang giữ được đăng đúng một lần khi hết khoá. Thu hồi và đổi revision ghi trạng thái bằng câu SQL riêng nên trước đây còn sót `hold_until` trên dòng không còn `candidate` (không ảnh hưởng lịch vì chỉ dòng `candidate` được đếm); nay xoá cùng lúc.

**Script của reviewer:** `PR-604-A4-code-r2-checks.py --expect-fixed` 14/14 và `PR-604-A4-code-r3-checks.py --expect-fixed` 4/4, cả hai exit 0. Output: `exports/reviews/A4-code-r5-reviewer-checks.txt`.

**Đối chứng trên head cũ:** bản test mới chạy trên `d26c0f09`: cả 7 kiểm V3 đỏ (1 lượt engine, action work, bản nộp không được đăng đúng), ca đối chứng không lỗi vẫn xanh. Output: `exports/reviews/A4-code-r4-control-on-d26c0f09.txt`.

## Review mã vòng 2 (`7b47e246`) và cách sửa

| Điểm | Sửa | Hồi quy (đi qua `handoff_after_turn`, `tick` thật có cả lịch thường và `settle`, mở lại kho) |
|---|---|---|
| P2-1: file nháp không đọc được tạm thời bị chốt `conflict/target_changed` | `_sub_read` tách lỗi I/O tạm thời (giữ nghĩa vụ, giãn cách) khỏi mất hay sai hash (`reject_submission`, lý do riêng) (I13) | V2-P2-1: khoá file nháp một và nhiều lần, mở lại kho, hết khoá thì đăng đúng bản gốc, 0 lượt engine; bản nháp sai hash không lên đích, `draft_hash_mismatch`, không có sự kiện xung đột; đối chứng đích thật sự bị sửa vẫn `conflict` |
| P2-2: lịch phục hồi bị xoá trước khi tiếp nhận | Lịch `settle` sống tới khi tiếp nhận xong; lần thức `settle` tiếp nhận bản đã đăng; lỗi tiếp nhận không văng ra ngoài (I14) | V2-P2-2: lỗi khoá SQLite một lần ở bước tiếp nhận, rồi active, thu hồi, huỷ, tạm dừng, mở lại kho, ba tick: tiếp nhận đúng một lần, một hành động đăng, không còn lịch thừa, 0 lượt engine |
| P2-3: lịch làm việc gọi model khi lần đăng đã chốt còn chờ I/O | `_wake_work` gác `publish_settling` khi còn nghĩa vụ hoàn tất; `_settle_done` gỡ gác (I15) | V2-P2-3: thay file lỗi lặp qua nhiều tick có cả lịch thường, mở lại kho: 0 lượt engine, 0 action work, trạng thái gác; mở khoá: bản gốc đăng đúng một lần, tiếp nhận, gỡ gác |

**Script của reviewer** (`PR-604-A4-code-r2-checks.py`): `--expect-fixed` 14/14, exit 0. Chế độ tái hiện mặc định giờ báo 4 hỏng, nghĩa là bốn ca N1, N2 thu hồi, N2 huỷ, N3 không còn tái hiện. Output hai chế độ: `exports/reviews/A4-code-r3-reviewer-checks.txt`.

**Đối chứng trên head cũ:** bản test mới chạy trên `37a86fe9` (bằng `7b47e246` cộng merge `main` 0.91.0):
- ba ca V2-P2-1 đỏ;
- ca V2-P2-2 văng `sqlite3.OperationalError` ra ngoài, tức chính lỗi bước tiếp nhận làm hỏng luồng.

Output: `exports/reviews/A4-code-r3-control-on-37a86fe9.txt`.

## Review mã vòng 1 (`a3356165`) và cách sửa

| Điểm | Sửa | Hồi quy |
|---|---|---|
| P1-1: "Chưa đúng ý" ghi trước mốc commit vẫn đăng | `_publish_held` kiểm phản hồi cách hiểu mới nhất của đúng revision trong giao dịch ý định (gồm nhánh `same`) và mốc commit | V1-P1: từ chối trước commit (qua `handoff_after_turn`), trước nhánh `same`, đối chứng "Đúng ý", đổi lại "Đúng ý" rồi đăng, 0 lượt model |
| P2-1: lỗi I/O tạm thời ở đối soát chốt `conflict` vĩnh viễn | `_reconcile_publish` phân biệt không đọc hay ghi được với bằng chứng đích đổi; `publish_retry` giữ `running`, giãn cách, hẹn `settle` | V1-P2-1: lỗi ở lần đăng đầu và ba lần đối soát, mở lại kho xen giữa, rồi hoàn tất đúng một lần; đối chứng file thật bị sửa giữ nguyên và `conflict` |
| P2-2: thu hồi làm mất đường scheduler tới tác động đã commit | Lịch vật lý `settle` (I10) | V1-P2-2: `tick` thật sau thu hồi và mở lại kho, cho "chưa thay file" và "đã thay file chưa ghi mốc", nhịp thứ hai không làm gì; mục tiêu đã huỷ; đối chứng thu hồi trước commit vẫn chặn |
| P2-3: thẻ nói "đã đăng bản nháp" khi server báo xung đột | `noteFor` chọn câu theo `publish`; hai câu mới (xung đột, chưa đăng) | `send()` thật với phản hồi `conflict` và `succeeded` |
| I1, I2 | Chấp nhận; §5.3, §4.2, §4.7 đồng bộ | |

**Đối chứng trên head cũ:** chép hai file test mới vào worktree tạm tại `a3356165`. Kết quả:
- 7 ca hồi quy phía server đỏ;
- test thẻ hỏng vì `RS.noteFor` chưa tồn tại;
- các ca đối chứng vẫn xanh.

Output ở `exports/reviews/A4-code-r2-control-on-a3356165.txt` (ngoài git).

**Script kiểm độc lập của reviewer:** `--expect-fixed` xanh cả 9 ca (5 đối chứng, 4 lỗi). Ca R4 của script tách riêng thân `send()`, nên câu ghi chú nó thấy là câu lỗi chung, vì `noteFor` nằm ngoài phạm vi tách. Câu đúng được kiểm bởi test hành vi `send()` thật ở trên.

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
- Test rollback chạy mã 0.91.0 thật lấy bằng `git show 1d0b515c` (trước khi merge `main` mới là 0.89.0 `33a3c1aa`).
- Chưa kiểm giao diện bằng trình duyệt thật (chỉ hàm thuần của thẻ).
- Các điểm I1, I2 ở mục 17 của thiết kế chạm cơ chế quyền; reviewer đã chấp nhận ở review mã vòng 1.

## Toàn repo

**Lần chạy cuối (11/10/2026, `f6aeb6d1`, mã sản phẩm bằng head của gói pilot):** 639 file, 625 xanh, 14 đỏ. Chạy lại từng file đỏ trên worktree sạch `main` `1d0b515c`: 13 file đỏ y như vậy (môi trường máy này); `test_ignore_files` xanh trên `main` và đỏ trên worktree PR chỉ vì thư mục `exports/` (hồ sơ review, không track). Không có file đỏ mới do A4. Log và phân định: `exports/reviews/A4-full-suite-f6aeb6d1.*` (ngoài git).

**Lần chạy đầu (trước review mã vòng 1):**

`tests/run.py` chạy đủ 637 file trên máy Windows này: 619 xanh. 18 file đỏ, phân định:

- 14 file đỏ sẵn trên `main` sạch của máy này (môi trường, đã ghi từ trước): `test_agy_prompt_dai`, `test_antigravity_cli`, `test_ba_loi_mac_va_telegram`, `test_cai_windows`, `test_grok_cli`, `test_install_admin`, `test_link_file_uri`, `test_machine_translations`, `test_memory_hoa_thuong`, `test_model_theo_phien`, `test_ollama_local`, `test_terminal`, `test_windows_no_console`, và `test_ignore_files` (thư mục `exports/` chưa track).
- `test_khoi_dong_nhe` (tỉ lệ thời gian nạp `main`): đỏ cả trên worktree sạch `6d774bd5` khi máy đang chạy bộ test lớn (6,29 và 6,50 lần, bản A4 5,16 và 5,17 lần); không do A4.
- `test_hoi_thoai_nhom`: chạy lại riêng thì xanh.
- `test_route_table`: do route mới; đã chuyển route xuống cuối bảng và chụp lại (thêm đúng 1 mục).
- `test_update`: báo nhầm, khoá cache crc32 của `style.css` mới đổi thành `72de33ed`, chứa chuỗi `?v=72` mà test cấm theo chuỗi con. Sửa test so nguyên khoá.

Sau các sửa trên, chạy lại `resonance`, `test_update`, `route_table` trên mã cuối: 45/45 xanh. Log đủ ở `exports/reviews/A4-code-full-suite.log` (ngoài git).
