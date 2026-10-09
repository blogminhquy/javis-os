# Kế hoạch nối Resonance A1 (sau review vòng 2)

- **Ngày:** 08/10/2026.
- **Nền:** PR #590, head `241fbb5d`. Thiết kế: `docs/superpowers/specs/2026-10-08-resonance-a1-agent-scope-design.md`.
- **Review vòng 2:** cho tiếp tục, kèm một P2 (phiên mở trước lần bật đầu của agent tạo lại cùng tên) và hai điểm cần chốt: dùng lại đầu ra sau tắt/bật, phạm vi bằng chứng quay về.
- **Không làm trong đợt này:** A2 trở đi, đường giao việc từ chat thường, pilot model thật, merge.

## Chính sách chung: một hàm cổng agent

`resonance.agent_gate(store, brain_id, agent_key, version=None)` trả `(agent | None, lý do)`. Mọi đường dưới đây gọi đúng hàm này, không tự đọc công tắc. Lý do chặn:
- `unassigned`: mục tiêu chưa gán agent;
- `agent_missing`, `agent_retired`: mã không còn `active`;
- `agent_off`: công tắc tắt;
- `agent_changed`: `config_version` khác với bản người gọi đang giữ.

## Nhóm 1: danh tính, mục tiêu theo agent, cổng (một commit kiểm riêng)

1. **Kho:**
   - `create` nhận `agent_key` cùng `agent_version`, ghi `goal_agents` và `handoff_agents` trong cùng giao dịch;
   - `revise` ghi `handoff_agents` khi mở bàn giao;
   - `GoalRecord` có `agent_key` (đọc từ `goal_agents`);
   - `list_open` lọc theo `agent_key`;
   - `begin_action` nhận intent có `agent_key` cùng `agent_config_version`.
2. **Tool `javis_goal`:**
   - Danh tính lấy từ `turn_context.current()`: phải có `agent`, `session_id`, `message_id`.
   - Lời người dùng lấy từ sổ lượt đang chạy theo ĐÚNG khoá `(web:<phiên>, id tin)` của ngữ cảnh lượt, không đoán "lượt duy nhất". Đây là bản lời host đã dùng cho lượt (đã bóc khối ngữ cảnh giao diện, giữ câu gốc của lượt giọng nói).
   - Thiếu một trong các thứ trên, hay cổng agent chặn: từ chối trước mọi lần ghi kho.
   - `list` và `update` chỉ thấy mục tiêu của đúng agent.
   - `visible_fn`:
     - có ngữ cảnh lượt thì theo agent của lượt;
     - không có thì hiện nếu brain có ít nhất một agent bật. Chỉ để gợi ý.
3. **`_gate` (scheduler, đăng, kết luận, phép thử):** thay công tắc brain bằng `agent_gate` theo mã của mục tiêu.
   - `unassigned`: chặn, không đặt lịch; việc gán đặt lại lịch.
   - Các lý do còn lại: chặn, hẹn kiểm lại bằng code.
4. **Đầu ra theo agent và version:**
   - `_work_step` ghi `agent_key` cùng version vào intent lúc giữ lượt.
   - Trước khi đăng, so với cổng hiện tại. Lệch thì giữ đầu ra, hẹn thức ngay để lần sau xét lại.
   - `_publish_latest` chỉ dùng đầu ra của hành động mang ĐÚNG `agent_key` của mục tiêu. Đầu ra trước lúc gán và của agent khác không được đăng.
5. **Dùng lại đầu ra sau tắt/bật** (chốt theo review):
   - Intent gốc giữ nguyên, không sửa version.
   - Khi cổng mở lại, `_publish_latest` kiểm đủ: mã của hành động bằng mã của mục tiêu, agent `active` và bật, revision, guard, baseline.
   - Sau đó ghi một hành động `publish` MỚI. Intent của nó mang version HIỆN TẠI cùng `source_action` trỏ về lượt việc cũ. Không gọi model lại.
6. **Bàn giao trong lượt:** `handoff_after_turn` thay công tắc brain bằng cổng agent. Version ghi ở `handoff_agents` phải bằng version hiện tại.
7. **Phép thử và áp dụng (M5):** `_trial_gate` đi qua `_gate`. `apply_method` kiểm lại cổng agent trong cùng giao dịch ghi.
8. **main.py:**
   - Dòng gợi ý trong system prompt chỉ có khi lượt thuộc agent đang bật.
   - `_resonance_after_turn` và sổ biên nhận ghi chỉ chạy khi lượt có agent.
   - `/agents/delete` cho mã đang sống nghỉ.
9. **Test:**
   - Helper chung bật agent cho test cũ M2 đến M5. Nội dung kiểm của chúng giữ nguyên.
   - Test mới cho ma trận 1 đến 7 và 11, 12.
   - Transport: plugin trong tiến trình, hub HTTP với khoá `X-Javis-Turn` (Codex), khoá giả hay đã chết.

## Nhóm 2: API của chủ dự án

1. `GET /resonance/agents?brain=`: file agent của brain ghép với sổ đăng ký, cùng số mục tiêu chờ gán.
2. `POST /resonance/agents/toggle {slug, enabled, session_id?}`:
   - Bật đòi file agent có thật.
   - Có `session_id` thì trả trạng thái của phiên đó: `ready`, hoặc `needs_new_session` khi phiên không dùng được mã hiện tại (P2 vòng 2). Không tự chuyển phiên.
   - Bật thì đặt lịch thức cho mục tiêu `active`, không tạm dừng, của mã đó.
3. `POST /resonance/agents/confirm {agent_key, same}`: đòi file có thật.
4. `POST /goals/{id}/assign {agent_key, expected_revision}`: chỉ mục tiêu chưa gán, mã `active` cùng brain, CAS.
5. **`/goal-requests`:** tin phải thuộc phiên mà mã ghim (cùng hàm với `run_turn`) đang bật; mục tiêu gắn mã đó.
6. **`GET /resonance/goals`:** lọc `agent_key`; `unassigned=1` cho mục "Chờ gán".
7. **Phản hồi trên thẻ:** đòi agent của mục tiêu đang bật. Xem, tạm dừng, huỷ, bỏ chỉ dẫn không đòi gì như cũ.

## Nhóm 3: giao diện tối thiểu

1. **Trang Cộng sự, cột phải của agent:** khối Cộng hưởng.
   - Có công tắc và dòng trạng thái của phiên đang mở.
   - Khi bị `needs_new_session`: câu giải thích và nút "Mở cuộc trò chuyện mới".
   - Có danh sách "Mục tiêu của trợ lý" (cách hiểu, tiêu chí, sản phẩm, đang chờ gì, lần thức kế, lượt đã dùng, nút tạm dừng và huỷ).
2. **Trang Cài đặt:**
   - Khối công tắc theo brain đổi thành danh sách agent kèm công tắc.
   - Có mục "Chờ gán" với ô chọn agent.
   - Có ghi chú rằng công tắc brain cũ không còn dùng.
3. **Engine:** dòng cảnh báo khi engine của agent chưa mang được khoá lượt (Grok, Antigravity). Phân biệt ba khả năng: lập mục tiêu, nhận bản chat, việc nền.
4. Chuỗi qua `vi.json` và `en.json`. Test JS cho phần dựng khối và luồng `needs_new_session`.

## Sau ba nhóm

- Vòng quay về có thêm một mục tiêu A1 thật (đã gán agent, có `handoff_agents`).
- Ca tắt trong lượt, version cũ, restart, CAS gán, giữ đầu ra: đếm số lượt engine lẫn bản được đăng.
- Gửi review tích hợp A1 kèm base/head, test và giới hạn.
- Pilot thật chỉ trình sau khi đường engine giả đạt, với phạm vi và hạn mức riêng.
