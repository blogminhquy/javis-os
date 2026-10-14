# Resonance A5: kịch bản và bộ chạy pilot

**Trạng thái:** mã A5 đạt review mã vòng 2 tại `05e9b065` (Codex, 12/10/2026); bộ chạy đạt review cổng vòng 3 tại `33cec518`. **Pilot thật đã chạy hai lần tại `33cec518`, mỗi lần một lời duyệt riêng của chủ dự án:** real-1 dừng `stopped` ở cổng token (0 lượt); real-2 ra `pending_content_review`, nhánh `pass_first`, và được reviewer chấp nhận trong phạm vi một mẫu đó. Kết quả, hash và giới hạn: [biên bản, mục Pilot thật](resonance-a5-verification.md#pilot-thật-13102026). A5 chưa phát hành. Mọi lần chạy real tiếp theo vẫn cần chủ dự án duyệt riêng; review mã không cấp quyền đó.

Thiết kế: [2026-10-11-resonance-a5-maker-reviewer-design.md](../superpowers/specs/2026-10-11-resonance-a5-maker-reviewer-design.md). Biên bản kiểm mã: [resonance-a5-verification.md](resonance-a5-verification.md).

## Pilot chứng minh gì, và không chứng minh gì

Chứng minh bằng model thật, trên đường host thật (server thật, kho thật, nhịp Cộng hưởng thật, API thật của trang trợ lý và thẻ):

1. Việc nền của **vai làm** (agent làm, engine việc nền) viết một bản đạt kiểm khách quan. Host đăng đúng bytes vào file đích theo quyền A4 mà chủ đã cấp.
2. Việc nền của **vai review** (agent khác danh tính, lời dặn review, cùng engine việc nền theo thiết kế) đọc ảnh chụp của đúng bản đã tiếp nhận (hash, revision, mã reviewer đã ghim) và ra một kết luận đọc được.
3. Nhánh xảy ra thật được ghi đúng như nó xảy ra:
   - đạt ngay; hoặc
   - cần sửa, vai làm sửa theo góp ý, rồi review lại.

   Không ép nhánh, không chạy lại để có kết quả đẹp.
4. Giết rồi dựng lại server: không lượt nào được gọi thêm, kể cả thử gọi.

Không chứng minh:
- Bộ não chat tự định tuyến tới `javis_goal`: mục tiêu được lập bằng `form_goal` với đề xuất đóng băng, xem mục "Lập mục tiêu"; điểm này đã có ở pilot A4.
- Hai vai là hai model độc lập: theo thiết kế, hai vai dùng chung engine việc nền.
- Nhánh hai vòng sửa tới cùng, thử lại sau `unknown` hay sau lỗi engine: các nhánh đó cần thêm lượt hoặc hẹn một giờ, vượt trần pilot đề xuất. Chúng đã có test bằng engine giả.
- Hiệu năng hay độ trễ trên VPS: pilot chạy trên máy local.

## Kịch bản

**Đầu vào đóng băng** (`FROZEN` trong `tests/python/test_resonance_a5_pilot.py`), băm thành `frozen_sha256`. Real từ chối chạy nếu hash khác bộ đã duyệt.
- Hai trợ lý: `nguoi-lam-tom-tat` (làm) và `nguoi-duyet-tom-tat` (review), thân file cố định.
- Lời giao (dữ liệu mô phỏng): bản tóm tắt cuộc họp ở `Inbox/tom-tat-hop-a5.md`, có mục Kết luận và mục Việc tiếp theo (mỗi việc một dòng, có người phụ trách và hạn), kèm nội dung họp.
- Đề xuất mục tiêu: hai tiêu chí `artifact_contract` trên file đích, phải có "Kết luận" và "Việc tiếp theo"; `achieve/delivery`.

**Lập mục tiêu.** Không dùng lượt chat. Bộ chạy gọi `form_goal` với lời giao và đề xuất đóng băng, trong phiên của agent làm. Đây đúng là hàm mà tool `javis_goal` và route `/goal-requests` dùng, và không gọi model. `/goal-requests` không dùng được vì nó để bộ lập mục tiêu gọi một lượt model và tự đặt tiêu chí, nên tiêu chí không đóng băng được. Đây là gieo trạng thái bằng hàm host thật, không phải engine giả.

**Các bước:**

| Bước | Server | Việc | Lượt model |
|---|---|---|---|
| 0 | không | Kiểm nguồn: HEAD đúng SHA đã duyệt (`JAVIS_RESONANCE_A5_APPROVED_SHA`) và cả checkout sạch, gồm mã sản phẩm, chính bộ chạy và không file lạ (`preflight_source`). Cổng chi phí: trần pilot ≤ số đã duyệt, đủ cho nhánh ngắn nhất. Tạo sổ (từ chối nếu đã có). Cổng engine và xác thực: engine việc nền đúng cấu hình đã duyệt; `claude auth status` là gói thuê bao gốc; không có apiKeyHelper, env chọn nhà cung cấp hay settings do quản trị đặt | 0 |
| A | nhịp tạm dừng, trần kho 0, trần sổ 0 | Bật hai trợ lý qua `/resonance/agents/toggle`. Chọn người review qua `/resonance/agents/reviewer`. Lập mục tiêu (`form_goal`). Cho phép phạm vi qua lệnh `approve_scope` của thẻ. Kiểm đội đã gắn (ghim mã reviewer, 8 lượt chia 4/4, hai vòng), phạm vi đã cấp, chưa có file đích | 0 |
| B | nhịp chạy, trần kho = trần tổng pilot, trần sổ theo vai | Tiền điều kiện (hai trợ lý còn bật, đội còn ghim đúng mã, không kiểm nào hỏng), cổng token (còn ít nhất 30 phút). Quan sát tới khi mục tiêu kết thúc, sổ đóng, hay không còn lịch làm việc trong 5 phút, không có lượt đang chạy, mục tiêu không ở `running`, không lần thức nào giữ khoá mục tiêu, đúng ở hai lần quan sát liên tiếp; trần thời gian 30 phút | theo nhánh, tối đa 4 |
| C | nhịp chạy, trần kho = số đã dùng, trần sổ 0 | Chờ khoảng 95 giây (hơn ba nhịp). Sổ không có lượt hay lần thử mới; hành động và hàng review không đổi. Tạm dừng mục tiêu nếu còn mở | 0 |

**Nhánh có thể xảy ra** (bộ chạy đọc từ kho, ghi `branch`):

| Nhánh | Diễn biến | Lượt làm / review | Kết luận |
|---|---|---|---|
| `pass_first` | Làm, review pass, chốt đạt | 1 / 1 | `pending_content_review` |
| `one_fix_then_pass` | Làm, review cần sửa, sửa theo góp ý, review pass, chốt đạt | 2 / 2 | `pending_content_review` |
| `pilot_cap_after_two_reviews` | Hai lần cần sửa; lượt sửa thứ hai bị trần pilot chặn, không gọi model. Lớp chặn trước là trần kho, chặn ngay lúc giữ chỗ (`blocked/budget`, dry thấy đúng như vậy). Nếu trần kho không chặn thì sổ pilot chặn trước khi dựng engine (`blocked/engine_blocked`, host hoàn lượt) | 2 / 2 | `business_incomplete` |
| `review_unknown` | Review không đọc được (engine chạy bình thường); host hẹn thử lại sau một giờ, pilot không chờ | 1 / 1 | `business_incomplete` |
| `maker_not_met` | Bản làm chưa đạt kiểm khách quan, chưa có review; host hẹn thử lại sau 15 phút, pilot không chờ | 1 / 0 | `business_incomplete` |
| `maker_error`, `reviewer_error` | Lượt của vai làm hay vai review lỗi ở engine hay host (mọi kết cục lỗi, xem "Hạn mức"); sổ đóng | 1 / 0, 1 / 1 | `technical_failed` |
| `no_review`, `other` | Không khớp các nhánh trên; ghi nguyên, không suy diễn | | `technical_failed` |

Mục tiêu còn mở thì bộ chạy tạm dừng nó sau khi kiểm dựng lại.

## Hạn mức

| | Sản phẩm (A5, không đổi) | Pilot đề xuất |
|---|---|---|
| Tổng lượt việc nền của mục tiêu | 8 | 4 |
| Vai làm | 4 | 2 |
| Vai review | 4 | 2 |
| Vòng sửa | 2 | 1 vòng trọn (vòng sửa thứ hai bị trần pilot chặn) |
| Lượt chat | không áp dụng | 0 |

Đơn vị là **lượt engine cấp host**: một lần dựng engine cho một lượt làm hay review. Không phải request nội bộ của SDK, cũng không phải token.

Các lớp chặn (không lớp nào thay lớp nào):
- **Sổ lượt theo vai của pilot** (`tests/python/_a5_pilot_ledger.py`, launcher `tests/python/_a5_pilot_server.py`).
  - Giữ chỗ và fsync TRƯỚC khi dựng engine cho mỗi lượt.
  - Có trần vai, trần tổng và trần theo giai đoạn (A và C là 0).
  - Kết cục của lượt theo đúng luật lỗi của host (`GoalDeps._ask`): khung `error`; `final` có `is_error` hay `dua_token`; gọi công cụ trong lượt chỉ chữ (trước hay sau `final`); đầu ra rỗng, quá dài, hay là lời báo lỗi đăng nhập; ngoại lệ; huỷ khi host còn đọc (hết giờ); thiếu khung kết thúc; không dựng được. Lớp thứ hai bọc chính `_ask` của host: host kết luận lỗi sau khi đã gọi engine thì dòng sổ thành `host_<mã>`.
  - `ok` chỉ là tạm: lỗi đến sau hạ nó xuống (ghi `downgraded_from`), không bao giờ nâng lỗi thành `ok`. Host ngừng đọc sau một `final` hợp lệ thì `ok` giữ nguyên.
  - Mọi kết cục lỗi vẫn tính lượt, và sổ đóng ngay.
  - Bị chặn thì không chạm hàm dựng engine thật; host hoàn lượt theo đường not-run của A5. Sổ chỉ ghi một sự kiện `refused`.
  - Sổ đã có thì từ chối chạy; sổ hỏng thì không cấp lượt và không ghi đè.
- **Trần kho** `JAVIS_RESONANCE_CALL_CEILING`, áp cho mọi tiến trình server.
- **Trần sản phẩm** của đội (8, 4/4, hai vòng).
- **Hậu kiểm.** Sổ pilot phải khớp sổ vai của kho (`team_calls`) và `calls_used`; mỗi hàng review tính (`charged=1`) ứng với một lượt reviewer. Sổ thiếu, hỏng hay lệch là **chưa xác minh**, không bao giờ là 0.

Không thử lại, không nâng trần, không chuyển sang API trả phí. Settings của sandbox chỉ chép tên provider/model (`auxiliary`, `main`, `engine`, `claude_model`), không chép khoá hay chế độ xác thực.

## Bằng chứng mỗi điểm

| Điều cần chứng minh | Bằng chứng (`a5-pilot-real-main.json` và các file kèm) |
|---|---|
| Người làm | Hành động `work` mang `agent_key` của agent làm, `role=maker`, mốc `engine_at`; dòng sổ `maker` với provider/model; đầu ra `a5-maker-<n>.md` |
| Người review | Hành động `review` và hàng `reviews` mang mã reviewer đã ghim (khác mã agent làm), `role=reviewer`, mốc `engine_at`; dòng sổ `reviewer`; đầu ra thô `a5-reviewer-<n>.txt` (đọc từ bằng chứng đã mã hoá của host); kết luận, tiêu chí, góp ý trong `store_B.reviews` |
| Đúng hash, revision | `bundle_ref` mang đúng revision, mốc đăng, hash, mã reviewer. Hash là bytes chuẩn hoá của một đầu ra lượt làm. Ảnh chụp reviewer đã đọc băm lại đúng hash. Chốt đạt: file đích đúng bytes bản được review pass, cùng revision |
| Vòng sửa (nếu xảy ra) | Hàng `needs_changes`, lượt làm sau đó, lượt review mới trên bộ ghim mới |
| Dựng lại không gọi thêm | `restart`: không có dòng sổ, sự kiện, hành động hay hàng review mới |
| Không đụng file khác | Ảnh chụp brain trước và sau giai đoạn B: chỉ file đích đổi; ghi chú cũ còn nguyên |

## Kết luận của một lần chạy

Một hàm duy nhất, `decide_acceptance` (`tests/python/_a5_pilot_ledger.py`), quyết kết luận từ bằng chứng CUỐI. Real và dry dùng cùng luật. Thiếu trường nào thì coi như không đạt.

| Kết luận | Khi nào | Mã thoát |
|---|---|---|
| `stopped` | Dừng ở một cổng trước giai đoạn việc nền (không server nào có thể gọi model) | 1 |
| `technical_failed` | Một trong: kiểm hỏng; dừng sau khi việc nền đã bắt đầu; giai đoạn việc nền dừng bất thường (hết giờ, sổ hỏng, bẫy); sổ ở lần đọc cuối không xác minh được; có lượt kết cục khác `ok`; sổ lượt engine của server không xác minh được; dựng lại chưa kiểm hay có lượt mới; nhánh lạ; số lượt (sổ, sổ vai của kho) khác số của nhánh; trạng thái mục tiêu khác của nhánh; thiếu đầu ra đã lưu của mỗi lượt làm, mỗi lượt review, hay file đích khi chốt; ảnh chụp review chưa băm lại đúng; bảo toàn bằng chứng lỗi | 1 |
| `pending_content_review` | Kỹ thuật đạt trọn và mục tiêu chốt đạt (`pass_first`, `one_fix_then_pass`): chờ người đọc nội dung. Không có "đạt" tự động | 0 |
| `business_incomplete` | Kỹ thuật đạt trọn, nhánh nghiệp vụ chưa đạt nhưng đã định nghĩa (`pilot_cap_after_two_reviews`, `review_unknown`, `maker_not_met`); giữ nguyên `branch` | 2 |

Ca âm ở dry đạt kỳ vọng nghĩa là bộ chạy ra đúng `technical_failed` hay `stopped`. Đó là test của bộ chạy đạt, không phải một lần pilot kỹ thuật đạt.

**Ghi hồ sơ cuối là một phần của kết luận** (`finalize_record`, review cổng vòng 2):
- Khi giữ sandbox, `a5-pilot-recovery.txt` được ghi TRƯỚC; báo cáo JSON ghi SAU CÙNG. Vì vậy không bao giờ còn một báo cáo nói đạt mà file bắt buộc ghi sau nó lại hỏng.
- Lần ghi bắt buộc nào lỗi: kết luận thành `technical_failed` (mã thoát 1, kể cả khi trước đó là `pending_content_review` hay `business_incomplete`), thêm nguyên nhân cụ thể, nhánh giữ nguyên, sandbox giữ (`sandbox_kept = true`).
- Báo cáo lỗi thì ghi lại đường khôi phục với kết luận mới và thử ghi báo cáo đúng một lần nữa. Vẫn không ghi được thì in "KHÔNG GHI ĐƯỢC HỒ SƠ CUỐI" kèm đường sandbox ra stdout và stderr.
- Dòng `A5_PILOT` in sau khi chốt, kèm `report_saved`. Dòng này, báo cáo (nếu có), mã thoát và trạng thái giữ sandbox luôn cùng một kết luận.

## Bảo toàn bằng chứng

Trên MỌI nhánh, sau khi mọi server đã dừng, bộ chạy chép bằng chứng sang một thư mục MỚI `sandbox/` trong thư mục hồ sơ (không ghi đè gì có sẵn):
- kho mục tiêu và kho hội thoại, chép bằng SQLite backup (nhất quán, gồm WAL);
- sổ usage và settings (chỉ có tên provider/model);
- log của mọi server, đã che khoá và token;
- toàn bộ brain tạm (trợ lý, file đích, đầu ra các lượt làm) và kịch bản dry.

Kho và log của mọi server đã dựng là mục bắt buộc. Không chép kho bí mật hay khoá mã hoá.

**Sandbox gốc giữ nguyên** khi chạy real (luôn giữ), khi kết luận khác `pending_content_review`, khi bảo toàn lỗi, hay khi hồ sơ nằm trong sandbox. Khi đó bộ chạy in `A5_PILOT_KEPT <đường dẫn>` và ghi `a5-pilot-recovery.txt` (đường dẫn sandbox, bản sao, kết luận, lý do). Nguồn không bị sửa hay xoá; file hỏng chép nguyên bytes; sổ hỏng không bao giờ bị ghi đè. Người chạy không cần đặt biến nào thêm.

## Dry

`JAVIS_RESONANCE_A5_PILOT=dry python tests/python/test_resonance_a5_pilot.py` chạy 24 ca, mỗi ca một tiến trình con với server thật, đi qua đúng đường điều phối, hàm kết luận và pha ghi hồ sơ của real. Một ca chỉ đạt khi mã thoát đúng hợp đồng của kết luận và báo cáo JSON bắt buộc có (trừ ca chặn ghi báo cáo) cùng kết luận, nhánh, trạng thái giữ sandbox với dòng `A5_PILOT`. Dry chặn đường tới engine thật ngay từ cấu hình và đường gọi, không chỉ đếm sau khi chạy:
- settings dùng provider không tồn tại (`pilot-dry`);
- launcher thay hàm dựng engine việc nền bằng engine giả đọc kịch bản; hàm dựng "thật" là bẫy;
- không có lượt chat nào.

Mỗi ca còn xác minh sổ lượt engine của chính server sandbox (`usage.json` và `usage-events.jsonl`) bằng 0.

| Ca | Kết luận | Nhánh, sổ (làm, review) | Kiểm thêm |
|---|---|---|---|
| `main_pass` | `pending_content_review` | `pass_first` (1, 1) | mọi kiểm bằng chứng |
| `main_fix` | `pending_content_review` | `one_fix_then_pass` (2, 2) | lượt sửa riêng sau hàng cần sửa |
| `fix_cap` | `business_incomplete` | `pilot_cap_after_two_reviews` (2, 2) | trần kho chặn lượt sửa thứ ba lúc giữ chỗ |
| `ledger_cap` | `business_incomplete` | như trên (2, 2) | trần kho nâng lên 8 (chỉ dry); sổ chặn trước khi dựng engine, host hoàn lượt |
| `review_unknown` | `business_incomplete` | `review_unknown` (1, 1) | không thử lại |
| `maker_not_met` | `business_incomplete` | `maker_not_met` (1, 0) | không thử lại |
| `maker_error`, `final_is_error` | `technical_failed` | `maker_error` (1, 0) | lỗi khung `error`, hay `final` có `is_error`; sổ đóng; sandbox giữ |
| `reviewer_error` | `technical_failed` | `reviewer_error` (1, 1) | lỗi engine của vai review không gộp với review không đọc được |
| `timeout` | `technical_failed` | `maker_error` (1, 0) | engine treo quá trần thời gian (60 giây ở ca này); lượt còn giữ chỗ là chưa xác minh |
| `missing_output` | `technical_failed` | `pass_first` (1, 1) | đầu ra lượt làm không còn trước bước lưu |
| `ledger_lost_end` | `technical_failed` | `pass_first`, sổ chưa xác minh | sổ mất ngay trước lần đọc cuối (đổi tên, còn file `.lost`) |
| `save_error` | `technical_failed` | `pass_first` (1, 1) | lỗi lúc chép kho; bảo toàn lỗi; sandbox giữ, kho gốc còn, có đường khôi phục |
| `early_crash` | `technical_failed` | (0, 0) | bộ chạy lỗi trước bước lưu thông thường; log và kho vẫn được chép |
| `ledger_corrupt` | `technical_failed` | sổ chưa xác minh | sổ hỏng trước B: không cấp lượt; file hỏng giữ nguyên bytes |
| `tripwire` | `technical_failed` | (1, 0) | đường dựng engine "thật" bị gọi ở dry: bẫy ghi sự kiện |
| `report_fault` | `technical_failed` | `pass_first` (1, 1) | ghi báo cáo cuối lỗi sau một kết quả đạt: mã thoát 1, không có báo cáo, sandbox giữ, có đường khôi phục |
| `recovery_fault` | `technical_failed` | `review_unknown` (1, 1) | ghi đường khôi phục lỗi ở kết quả nghiệp vụ chưa đạt: mã thoát 1 (không phải 2); báo cáo nói technical_failed |
| `report_fault_technical` | `technical_failed` | `maker_error` (1, 0) | lỗi kỹ thuật vốn có cộng lỗi ghi báo cáo: vẫn thất bại, sandbox giữ |
| `cost`, `auth`, `ledger_exists`, `precondition`, `sha_mismatch` | `stopped` | | dừng ở cổng trước việc nền |

Logic của sổ, kết cục lượt qua `_ask` thật, kết luận, bảo toàn, quyền dọn và kiểm nguồn có test riêng, không cần server: `tests/python/test_resonance_a5_pilot_gate.py`.

## Chạy real (chỉ sau khi được duyệt)

```bash
JAVIS_RESONANCE_A5_PILOT=real JAVIS_RESONANCE_PILOT_SETTINGS=<settings.json thật> JAVIS_RESONANCE_A5_OUT=<thư mục mới, ngoài checkout> JAVIS_RESONANCE_A5_APPROVED='{"aux": {"provider": "anthropic-cli", "model": "sonnet"}}' JAVIS_RESONANCE_A5_MAX_CALLS=4 JAVIS_RESONANCE_A5_INPUTS_SHA=<frozen_sha256> JAVIS_RESONANCE_A5_APPROVED_SHA=<SHA đã duyệt> python tests/python/test_resonance_a5_pilot.py
```

Đúng một lần, trên một bản checkout sạch ở SHA đã duyệt. Bộ chạy tự kiểm (bước 0, trước mọi server) rằng HEAD đúng `JAVIS_RESONANCE_A5_APPROVED_SHA` và cả checkout sạch; sai hay không đọc được thì dừng, không lượt nào. Thư mục hồ sơ phải nằm ngoài checkout.
