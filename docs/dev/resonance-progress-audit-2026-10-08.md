# Rà soát tiến độ Resonance và điều chỉnh phạm vi agent

Ngày kiểm: 08/10/2026, Asia/Saigon. Snapshot mã: `09f254d0e4d009451dc58cb2e97788631c5acc1a` (main 0.86.1). Phạm vi: Resonance, agent/workflow/loop/học có liên quan và bộ tài liệu tiến độ. Không kiểm toán toàn bộ tính năng Javis.

## Bổ sung sau báo cáo kiểm cục bộ

Theo báo cáo Claude được chủ dự án chuyển lại: server thử localhost 0.86.0 đã đạt 13 kiểm không model và một chat thật (1 Opus, engine ok, turn completed). ChatGPT chưa chạy lại; cần gắn báo cáo/log và commit vào hồ sơ triển khai. Không suy ra server thật cổng 7777 hoặc VPS đã được kiểm. VPS vẫn chưa kiểm vì kết nối Hostinger ngắt.

A1 thu hẹp về phiên agent; giao từ chat thường tách sau A1. Xem review và chỉ dẫn Claude (`exports/reviews/Resonance-A1-review-and-Claude-instructions-2026-10-08.md`, ngoài git, chỉ có trên máy chủ dự án).

## Kết luận tiến độ

- **MVP M1–M5: 5/5 mốc hoàn tất và phát hành trong 0.86.0.** Squash `438f83097db4ee64e96b7b4880deb581521f217a`, PR #587. Các PR xếp chồng đã đóng; không bắt đầu lại từ M1.
- Main đã lên **0.86.1**, PR #589 cải thiện hiển thị bước đang chạy của Codex; không phải một mốc Resonance mới.
- Pilot 5 đạt nội dung và kỹ thuật trong một kịch bản, 2 lượt Opus, 0 Sonnet, xác nhận cuối mô phỏng. Không suy thành mọi engine/kênh hoặc định tuyến luôn đúng.
- **Hướng mới A1–A5: 0/5 mốc mới được nghiệm thu.** Có nền tái sử dụng đáng kể; con số này là đếm mốc, không phải 0% code hoặc 0% công sức.
- Chưa có bằng chứng một VPS cụ thể đã cập nhật và chạy ổn. Chưa có bằng chứng thực thi goal chỉ được cấp cho từng agent ở sản phẩm hiện tại.
- Tại lúc rà, danh sách PR mở do GitHub trả về là rỗng. Không có PR đang mở được dùng làm bằng chứng rằng A1–A5 đã bắt đầu.

## M1–M5 đã mang lại gì?

| Mốc | Kết quả đã có | Giới hạn cần giữ |
|---|---|---|
| M1 | Engine thực thi có receipt, hạn mức, lỗi và usage | Không suy ra mọi engine có cùng khả năng |
| M2 | Tự hình thành/cập nhật mục tiêu, lưu lời giao và revision | Hiện scope theo brain, agent chung javis; không phải agent riêng |
| M3 | Làm/kiểm/chờ/dừng, guard, bằng chứng, next_wake, restart | Chưa phải scheduler thích nghi học theo giá trị cho từng agent |
| M4 | Thẻ, phản hồi cách hiểu/đầu ra, điều khiển, chống báo trùng | Công tắc theo brain; chưa có màn hình tiến độ riêng theo agent |
| M5 | So phương pháp, giới hạn thử, áp dụng có điều kiện | Chưa tự đề xuất phép thử; chưa vòng học reaction; pilot thật chưa áp dụng ứng viên thắng |

Bàn giao sau pilot 3 đã bổ sung tiếp nhận Write thành công từ Claude Code; pilot 5 chứng minh đường chat → tiếp nhận → góp ý → tiếp nhận bản sửa. Không gọi Sonnet trong lần đó là đúng ca tránh viết lại, không phải thiếu lượt phải chạy bù.

## Bằng chứng mã và hệ có thể tái sử dụng

| Nơi đọc ở snapshot | Quan sát | Tác động lên kế hoạch |
|---|---|---|
| `server/resonance.py: enabled_for` | Đọc `<brain>/Javis/resonance.json`; thiếu/hỏng thì tắt | Công tắc hiện chưa theo agent |
| `system/plugins/javis-goal/plugin.py: javis_goal` | Dùng Principal agent/javis, gate theo brain; `_turn` dựa lượt web | Phải đổi danh tính và gate tool ở A1 |
| `server/resonance_api.py: goal_request` | Form goal qua agent/javis trong brain | Phải chặn đường vòng HTTP, không chỉ đổi UI |
| `server/resonance_store.py: _SCHEMA` | Goal có brain/owner/session; chưa có khóa agent thực thi riêng | Cần migration có chủ thể; không coi owner là agent_id |
| `server/workflow_chat.py: persona_cua_phien` | Có phân giải session agent:<slug>/workflow:<slug> | Có điểm tích hợp danh tính, chưa tự là chính sách cấp quyền |
| `server/resonance.py: next_wake, advance, tick` | Đã có lịch rẻ, backoff, chờ, lease; reaction bị bỏ qua khi đổi lịch | A2 tái dùng; A3 không nối điểm emoji trực tiếp vào nhịp |
| `server/resonance_store.py: record_feedback, fit_status` và `dashboard/chat-resonance.js` | Có feedback đúng revision và hash | Nền dùng lại cho vòng học, chưa là vòng học hoàn chỉnh |
| `server/resonance.py: compare_methods`, `server/resonance_store.py: apply_method` | Có thử trên cùng thước đo và áp dụng hạn chế phạm vi | Dùng cho A3, không xây ExperimentService lớn trước |
| `server/self_improve.py: LoopFeature` | Loop có cấu hình/lịch/chế độ và cơ chế báo kết quả | Tránh goal và loop cùng chạy một việc; không thay mọi loop bằng Resonance |
| `server/learn.py` | Có hệ tự học, fork/promote, hạn mức và lịch curator | Không thể nói Javis chưa có học; cần adapter/phạm vi để khỏi hai hệ cùng sửa một agent |
| `server/agent_runtime.py`, `workflow_graph.py` | Agent có replan có grant; workflow có verify_agent | Đội Resonance chưa có, nhưng có nền làm/review để nối |
| `dashboard/chatbots-reply-policy.js` | Có thumb gắn quyết định trả lời của chatbot | Không coi đó là reaction loop chung cho Resonance |

Không nhầm heartbeat giữ kết nối hoặc heartbeat cuộc gọi voice với nhịp thực thi mục tiêu.

## Những sai lệch trong hồ sơ đã xử lý ở đợt này

1. HTML cũ dừng ở 80% và review pilot trước lần 2; thay bằng mốc phát hành 0.86.0, snapshot main 0.86.1 và lộ trình mới.
2. README cũ nói bộ tài liệu chưa chứng minh triển khai, bảo bắt đầu M1; đổi thành danh mục hiện hành, dẫn hướng agent và hồ sơ đã phát hành.
3. File lệnh triển khai M1–M5 cũ còn có hạn mức pilot và lệnh chạy; gắn nhãn lịch sử, không cấp lại hạn mức cũ cho việc mới.
4. Spec và kế hoạch 00/01/02/03 cũ được giữ để tra, thêm chỉ dẫn tới tài liệu mới. Không xoá bằng chứng hoặc viết lại kết quả quá khứ.

Bản trước khi chỉnh được lưu cùng manifest SHA-256 tại `exports/archive/resonance-before-agent-scope-20261008-120051/`.

## Lộ trình hiện hành

**A1 agent + công tắc + tiến độ tối thiểu → A2 heartbeat thích nghi → A3 học từ phản hồi → A4 bàn giao đa engine → A5 đội làm/review.**

Kiểm một VPS (D0) có thể làm song song việc thiết kế A1; bật thử có model cần phạm vi và hạn mức của lần thử đó. Không dùng ngày hoàn thành hoặc tổng % tuỳ ý cho phần chưa ước lượng.

Xem [phạm vi và điều kiện nghiệm thu chi tiết](../superpowers/specs/2026-10-08-resonance-agent-scope-roadmap.md).

## Trạng thái đầu ra của lần rà này

Đã cập nhật tài liệu và trang HTML theo dõi. **Chưa sửa runtime, schema, API, công tắc đang dùng hoặc cấu hình brain/agent.** Không gọi model, không đổi nhánh checkout chính, không commit/push hoặc triển khai lên máy người dùng. Những thay đổi hành vi A1–A5 cần các PR tiếp theo.

Các file tài liệu ở checkout chính hiện là bản làm việc cục bộ (checkout chính vẫn ở nhánh cũ); mã nguồn được đọc từ checkout review riêng tại snapshot main nêu đầu tài liệu. Khi giao triển khai, mang tài liệu mới sang nhánh dựa trên main mới nhất, không code trên checkout cũ và không lấy số dòng lịch sử làm hợp đồng.

## Nguồn phát hành và nghiệm thu

- [PR #587](https://github.com/blogminhquy/javis-os/pull/587)
- [CI sau merge](https://github.com/blogminhquy/javis-os/actions/runs/37726542811)
- [Build/push 0.86.0](https://github.com/blogminhquy/javis-os/actions/runs/37726542815)
- [Hồ sơ pilot 5 tại commit bằng chứng](https://github.com/blogminhquy/javis-os/blob/450dd095/docs/dev/resonance-mvp-e2e-pilot-5.json)
- Review nội dung độc lập (`exports/reviews/PR-579-pilot5-content-review.md`, ngoài git, chỉ có trên máy chủ dự án)
- Review sau phát hành (`exports/reviews/Resonance-0860-post-release-review.md`, ngoài git, chỉ có trên máy chủ dự án)
- Trang theo dõi mới (`exports/javis-resonance-tien-do.html`, ngoài git, chỉ có trên máy chủ dự án)
