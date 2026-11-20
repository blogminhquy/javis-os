# Sổ tay vận hành Zalo 7 phần trên Javis OS và danh mục Cutover

Tài liệu này quy định kiến trúc đồng bộ 3 chỗ ghim `javis-zalo`, cấu hình mẫu kiểm chứng được cho Scheduler (`reminders` + `cron_util`) và Workflow (`workflow_graph`) trên Javis OS, cùng danh mục chuyển đổi (Cutover Checklist) để tắt hẳn `serve-with-ids` và các tác vụ Zalo tự động cũ bên `nexme_marathon` mà không mất dữ liệu hay đụng độ hai kết nối WebSocket.

## 1. Bất biến kiến trúc: 1 tài khoản Zalo = 1 kết nối WebSocket duy nhất

- `javis-zalo` chỉ đóng vai trò lớp vận chuyển (transport) tối giản: mỗi tài khoản Zalo chỉ mở duy nhất một kết nối WebSocket trong tiến trình `javis-zalo mcp start`, cô lập theo thư mục `HOME` riêng của từng kết nối (`isolate_home: true`).
- Cơ chế bảo vệ trên Javis OS (`#1643`):
  - `server/zalo_login.py` kiểm tra trùng tài khoản (`account_ids`, `_same_account`) ngay lúc quét QR và tự dọn thư mục phiên trùng trong `_reader`.
  - `server/mcp_client.py` (`_close_later`, `holds_spec`) và `server/mcp_hub.py` (`_single_socket_unchanged`) giữ nguyên tiến trình MCP Zalo đang sống khi làm mới bộ đệm kết nối, không khởi động tiến trình thứ hai đè lên cùng một `HOME`.
- Mọi lịch trình định kỳ trên Javis OS (khung giờ im lặng `22:30 -> 05:30` giờ Việt Nam, tạo/đọc/khoá poll cho `nexme marathon`, gửi tin/file/thoại/video) đều chạy qua `reminders` (`mode: "task"`, `muc_quyen: "full"`, múi giờ `Asia/Ho_Chi_Minh` qua `localefmt.tz()`, có `once_ledger` chống chạy trùng) và gọi thẳng các tool `zalo_*` trên phiên MCP đang sống. Không bao giờ gọi CLI `--listen` hay mở daemon giữ socket thứ hai cho cùng tài khoản.

## 2. Đồng bộ 3 chỗ ghim và quy trình nâng tag phát hành

Ba chỗ ghim phiên bản `javis-zalo` trong Javis OS phải luôn khớp tuyệt đối:

1. `system/mcp-catalog.json` (`connectors[id="zalo"].args`)
2. `server/zalo_cli.py` (`CLI_PACKAGE`)
3. `server/zalo_login.py` (`_CLI_PACKAGE`)

Hiện tại cả 3 chỗ ghim đang ở tag đã phát hành `v1.14.0` (và `lenh_cu` chứa đủ `v1.0.0` đến `v1.13.0`) để `python3 tools/release.py check` cùng toàn bộ bài kiểm thử hiện tại đạt PASS, không bị lỗi HTTP 404 khi tải tarball.

Khi `blogminhquy/javis-zalo` gộp xong bộ PR 7 phần (`#21`, `#22`, `#23`, PR `#4` `feat/mcp-polls`, PR `#5` `feat/mcp-send-voice`, PR `#6` `feat/mcp-send-video`) và phát hành tag mới (ví dụ `v1.15.0`), thực hiện nâng tag trong 1 bước:

1. Thêm `{ "command": "npx", "args": ["-y", "--prefer-offline", "https://codeload.github.com/blogminhquy/javis-zalo/tar.gz/refs/tags/v1.14.0", "mcp", "start"] }` vào mảng `lenh_cu` của connector `zalo` trong `system/mcp-catalog.json`.
2. Đổi đồng loạt `v1.14.0` sang tag mới ở cả 3 chỗ (`system/mcp-catalog.json`, `server/zalo_cli.py`, `server/zalo_login.py`).
3. Cập nhật mốc kiểm tra phiên bản trong `tests/python/test_zalo_send_file.py` rồi chạy lại `python3 tools/release.py check` và bộ kiểm thử Zalo.

## 3. Phân loại quyền 24 công cụ MCP (`tool_meta`)

- **Nhóm `read` (11 công cụ)**: `zalo_get_messages`, `zalo_get_history`, `zalo_search_history`, `zalo_get_group_joins`, `zalo_list_join_requests`, `zalo_list_threads`, `zalo_search_threads`, `zalo_view_media`, `zalo_get_labels`, `zalo_get_group_settings`, `zalo_get_poll`.
- **Nhóm `write` (1 công cụ)**: `zalo_mark_read`.
- **Nhóm `danger` (12 công cụ, yêu cầu mức Toàn quyền `full`)**: `zalo_send_message`, `zalo_send_link`, `zalo_send_typing`, `zalo_send_file`, `zalo_send_voice`, `zalo_send_video`, `zalo_undo_message`, `zalo_add_reaction`, `zalo_review_join_requests`, `zalo_update_group_settings`, `zalo_create_poll`, `zalo_lock_poll`.

## 4. Cấu hình chuẩn cho Scheduler và Workflow trên Javis OS

Khối JSON dưới đây là cấu hình chuẩn cho:
- **(a) Nhóm im lặng theo giờ Việt Nam (`22:30` khoá nhóm -> `05:30` mở nhóm, `Asia/Ho_Chi_Minh`)**, bảo toàn đủ 9 cờ cài đặt nhóm theo PR `#21` (`blockName`, `signAdminMsg`, `addMemberOnly`, `setTopicOnly`, `enableMsgHistory`, `joinAppr`, `lockCreatePost`, `lockCreatePoll`, `lockSendMsg`).
- **(b) Vòng đời Poll của `nexme marathon` kết hợp `nexme-ops`**: tự động tạo poll (`zalo_create_poll`) -> đọc danh sách người đã bình chọn và đối chiếu hội viên qua `nexme-ops` (`zalo_get_poll` với `includeVoters=true`) -> chốt bản chụp cuối và tự động khoá poll (`zalo_lock_poll`, lưu ý poll đã khoá không thể mở lại qua Zalo API).

```json:javis-zalo-7parts-schedules
{
  "schema_version": 1,
  "timezone": "Asia/Ho_Chi_Minh",
  "single_websocket_invariant": true,
  "sandbox": {
    "profile": "nexme",
    "group_name": "Test nhom zalo",
    "thread_id": "2928062252153346304",
    "thread_type": 1,
    "forbidden_profiles": ["congdau", "haiyen"]
  },
  "preserved_group_flags": [
    "blockName",
    "signAdminMsg",
    "addMemberOnly",
    "setTopicOnly",
    "enableMsgHistory",
    "joinAppr",
    "lockCreatePost",
    "lockCreatePoll",
    "lockSendMsg"
  ],
  "reminders": [
    {
      "slug": "zalo-quiet-hours-lock",
      "name": "Khoá nhắn tin nhóm Zalo ban đêm (22:30 giờ VN)",
      "mode": "task",
      "muc_quyen": "full",
      "cron": "30 22 * * *",
      "timezone": "Asia/Ho_Chi_Minh",
      "once_ledger": true,
      "mcp_tools": ["zalo_get_group_settings", "zalo_update_group_settings"],
      "target_flag": "lockSendMsg",
      "desired_value": true,
      "verify_readback": true,
      "prompt": "Trên kết nối Zalo profile=nexme (hoặc nhóm mục tiêu đã cấu hình), gọi zalo_get_group_settings(threadId) để kiểm tra isAdmin và ghi nhận đủ 9 cờ cài đặt nhóm. Nếu không có quyền isAdmin hoặc không đọc được cài đặt thì dừng an toàn và báo chủ. Nếu lockSendMsg đã là true thì trả [SILENT]. Nếu lockSendMsg đang là false, gọi zalo_update_group_settings(threadId, lockSendMsg=true) để khoá gửi tin mà vẫn bảo toàn 8 cờ còn lại, sau đó kiểm tra kết quả readback đảm bảo settings.lockSendMsg == true."
    },
    {
      "slug": "zalo-quiet-hours-unlock",
      "name": "Mở nhắn tin nhóm Zalo buổi sáng (05:30 giờ VN)",
      "mode": "task",
      "muc_quyen": "full",
      "cron": "30 5 * * *",
      "timezone": "Asia/Ho_Chi_Minh",
      "once_ledger": true,
      "mcp_tools": ["zalo_get_group_settings", "zalo_update_group_settings"],
      "target_flag": "lockSendMsg",
      "desired_value": false,
      "verify_readback": true,
      "prompt": "Trên kết nối Zalo profile=nexme (hoặc nhóm mục tiêu đã cấu hình), gọi zalo_get_group_settings(threadId) để kiểm tra isAdmin và 9 cờ cài đặt nhóm. Nếu không có quyền isAdmin thì dừng an toàn và báo chủ. Nếu lockSendMsg đã là false thì trả [SILENT]. Nếu lockSendMsg đang là true, gọi zalo_update_group_settings(threadId, lockSendMsg=false) để mở gửi tin buổi sáng mà vẫn bảo toàn 8 cờ còn lại, sau đó kiểm tra readback đảm bảo settings.lockSendMsg == false."
    },
    {
      "slug": "zalo-marathon-poll-create",
      "name": "Tạo poll điểm danh nexme marathon buổi sáng",
      "mode": "task",
      "muc_quyen": "full",
      "cron": "0 6 * * *",
      "timezone": "Asia/Ho_Chi_Minh",
      "once_ledger": true,
      "mcp_tools": ["zalo_create_poll"],
      "poll_defaults": {
        "allowMultiChoices": false,
        "allowAddNewOption": false,
        "hideVotePreview": false,
        "isAnonymous": false,
        "expireMinutes": 0
      },
      "prompt": "Gọi zalo_create_poll trên nhóm mục tiêu với isAnonymous=false để Zalo trả danh sách người bình chọn. Lưu pollId, threadId, question và thời điểm tạo vào sổ trạng thái notes/zalo-active-polls.json trong brain để bước đối chiếu và bước khoá poll sử dụng."
    },
    {
      "slug": "zalo-marathon-poll-reconcile",
      "name": "Đọc danh sách bình chọn poll và đối chiếu hội viên qua nexme-ops",
      "mode": "task",
      "muc_quyen": "full",
      "cron": "0 20 * * *",
      "timezone": "Asia/Ho_Chi_Minh",
      "once_ledger": true,
      "mcp_tools": ["zalo_get_poll"],
      "companion_skill": "nexme-ops",
      "prompt": "Đọc pollId đang mở từ notes/zalo-active-polls.json, gọi zalo_get_poll(pollId, includeVoters=true) để lấy danh sách phương án và mảng voters đã chuẩn hoá { id, name }. Đối chiếu với danh sách hội viên của nhóm qua nexme-ops (giữ nguyên các cổng kiểm tra dữ liệu của nexme-ops) để tách rõ danh sách hội viên đã bình chọn và chưa bình chọn."
    },
    {
      "slug": "zalo-marathon-poll-lock",
      "name": "Chốt kết quả và khoá poll nexme marathon cuối ngày",
      "mode": "task",
      "muc_quyen": "full",
      "cron": "0 22 * * *",
      "timezone": "Asia/Ho_Chi_Minh",
      "once_ledger": true,
      "mcp_tools": ["zalo_get_poll", "zalo_lock_poll"],
      "irreversible_lock": true,
      "reopen_policy": "Zalo API không cho phép mở lại poll đã khoá; muốn mở đợt mới phải gọi zalo_create_poll tạo poll mới hoặc dùng lockCreatePoll trong zalo_update_group_settings.",
      "prompt": "Đọc pollId đang mở từ notes/zalo-active-polls.json. Bước 1: gọi zalo_get_poll(pollId, includeVoters=true) để lưu bản chụp cuối cùng của danh sách người đã bình chọn. Bước 2: gọi zalo_lock_poll(pollId) để khoá bình chọn và cập nhật trạng thái closed=true, irreversible=true. Lưu ý: poll đã khoá không mở lại được qua Zalo API; vòng tiếp theo bắt buộc tạo poll mới bằng zalo_create_poll."
    }
  ],
  "workflows": [
    {
      "slug": "zalo-quiet-hours-guard",
      "meta": {
        "name": "Kiểm tra và chuyển trạng thái khung giờ im lặng nhóm Zalo",
        "description": "Đọc 9 cờ cài đặt nhóm, chỉ đổi lockSendMsg khi cần và xác nhận readback trên cùng kết nối MCP.",
        "status": "active",
        "nodes": [
          {
            "id": "read_settings",
            "kind": "model_step",
            "agent": "zalo-ops",
            "task": "Gọi zalo_get_group_settings(threadId) kiểm tra isAdmin và chụp nguyên trạng 9 cờ cài đặt nhóm."
          },
          {
            "id": "toggle_lock_send_msg",
            "kind": "model_step",
            "depends_on": ["read_settings"],
            "agent": "zalo-ops",
            "task": "Nếu lockSendMsg khác giá trị mục tiêu, gọi zalo_update_group_settings(threadId, lockSendMsg=desired) và kiểm tra readback đảm bảo 8 cờ còn lại không đổi."
          }
        ],
        "output_node": "toggle_lock_send_msg"
      }
    },
    {
      "slug": "zalo-poll-nexme-reconcile",
      "meta": {
        "name": "Vòng đời poll nexme marathon và đối chiếu hội viên nexme-ops",
        "description": "Đọc danh sách bình chọn chuẩn hoá từ zalo_get_poll, đối chiếu hội viên qua nexme-ops và khoá poll một chiều bằng zalo_lock_poll.",
        "status": "active",
        "nodes": [
          {
            "id": "fetch_poll_voters",
            "kind": "model_step",
            "agent": "zalo-ops",
            "task": "Gọi zalo_get_poll(pollId, includeVoters=true) lấy danh sách người bình chọn { id, name } đã chuẩn hoá."
          },
          {
            "id": "reconcile_nexme_members",
            "kind": "model_step",
            "depends_on": ["fetch_poll_voters"],
            "agent": "nexme-ops",
            "task": "Đối chiếu danh sách voters với danh sách hội viên của nhóm trong nexme-ops để xác định ai đã bình chọn và ai chưa bình chọn."
          },
          {
            "id": "lock_poll_final",
            "kind": "model_step",
            "depends_on": ["reconcile_nexme_members"],
            "agent": "zalo-ops",
            "task": "Khi tới giờ đóng bình chọn, chụp kết quả cuối cùng qua zalo_get_poll rồi gọi zalo_lock_poll(pollId). Poll đã khoá không mở lại được; đợt mới phải gọi zalo_create_poll."
          }
        ],
        "output_node": "lock_poll_final"
      }
    }
  ]
}
```

## 5. Cutover Checklist: Chuyển đổi an toàn từ `nexme_marathon` sang Javis OS

### 5.1. Danh mục thành phần Zalo cũ bên `nexme_marathon` cần tắt

1. **Tiến trình PM2 giữ kết nối WebSocket trực tiếp (`serve-with-ids`)**:
   - `zca-serve` (khai báo trong `ecosystem.zca.config.js`, chạy `scripts/zca-serve-with-ids/serve-with-ids.ts`, cổng `56789`, biến `ZCA_ACCOUNTS=nexme,congdau`, gọi `listener.start()` giữ WebSocket).
   - Các tiến trình PM2 phụ trợ / thử nghiệm: `zca-listener-nexme`, `zca-listener-congdau`, `zca-spike-serve` (cổng `56790`, chạy `scripts/zca-native-video-spike/spike-serve.ts`).
2. **Container và biến môi trường trong Docker Compose (`docker-compose.mac.yml`, `docker-compose.zca-sole.yml`)**:
   - Các dịch vụ `worker` (`marathon-worker`) và `worker-test` (`marathon-worker-test`) kết nối tới `ZCA_API_URL=http://host.docker.internal:56789` (cùng `api` và `api-test`).
3. **Các CronJob và hàng đợi BullMQ trong `apps/web/worker.ts`**:
   - Hàng đợi: `zcaNexmeQueue`, `zcaCongdauQueue`, `zcaHaiyenQueue`, `ZCA_FLOW`.
   - Các job định kỳ: `zcaSchedulerJob`, `quietHoursJob` (cờ `ZCA_GROUP_QUIET_HOURS_ENABLED`), `groupDmJob` (cờ `ZCA_GROUP_DM_ENABLED`), `flowSchedulerJob` (cờ `AUTOMATION_WORKFLOW_ENABLED`), `flowReconcilerJob`, `dmRecallReconcilerJob`, `dmDeliveryRecoveryJob`, `zcaHealthJob` (`*/2 * * * *`), `friendSyncJob` (`15 */6 * * *`).
4. **Các script tạo/khoá poll độc lập**:
   - `scripts/zalo-poll-create.mjs`, `scripts/zalo-poll-lock.mjs` và tệp trạng thái `scripts/active_polls.json` (cùng mọi cron hoặc launchd gọi chúng).

### 5.2. Kiểm tra trước chuyển đổi (Pre-flight Checks)

- [ ] **Chụp trạng thái dữ liệu bên `nexme_marathon`**: xuất bản chụp (snapshot) các bảng `ZcaGroupQuietHours`, `ZcaSchedule`, các bản ghi `ZcaPollLog` đang mở và tệp `scripts/active_polls.json` để không sót lịch hay poll đang chạy dở.
- [ ] **Kiểm tra phiên Zalo trên Javis OS**: xác nhận `tools/release.py check` và bộ kiểm thử Zalo đạt PASS; mỗi tài khoản Zalo chỉ có tối đa 1 connection trong `mcp_servers.json` (`#1643`), quyền đặt ở mức `full`.
- [ ] **Xác nhận thông tin nhóm Sandbox nghiệm thu**: khoá cứng cấu hình kiểm thử vào `profile=nexme`, nhóm `Test nhom zalo`, `threadId=2928062252153346304` (`threadType=1`). Tuyệt đối không dùng tài khoản `congdau`, `haiyen`, tin nhắn riêng hay nhóm vận hành thật để chạy thử nghiệm.

### 5.3. Thứ tự dừng bên `nexme_marathon` trước khi bật lịch trên Javis OS

Thực hiện đúng thứ tự dưới đây để không mất job đang chạy và không bao giờ có 2 kết nối WebSocket cùng lúc:

1. **Tắt cờ lập lịch mới bên `nexme_marathon`**:
   - Đặt `ZCA_GROUP_QUIET_HOURS_ENABLED=false`, `ZCA_GROUP_DM_ENABLED=false`, `AUTOMATION_WORKFLOW_ENABLED=false`.
   - Tắt mọi cron/launchd gọi `scripts/zalo-poll-create.mjs` và `scripts/zalo-poll-lock.mjs`.
2. **Đợi hàng đợi BullMQ rút cạn (drain)**:
   - Theo dõi `zcaNexmeQueue`, `zcaCongdauQueue`, `zcaHaiyenQueue` và `ZCA_FLOW` cho tới khi số job `active` và `waiting` đều về `0`.
3. **Dừng worker ZCA / `zcaHealthJob`**:
   - Dừng nhánh cron ZCA trong `marathon-worker` (hoặc dừng `marathon-worker` / `marathon-worker-test`) để `zcaHealthJob` (`*/2 * * * *`) không gọi lại cổng `56789`.
4. **Tắt và xoá hẳn các tiến trình PM2 giữ WebSocket Zalo**:
   - Chạy `pm2 stop zca-serve zca-spike-serve zca-listener-nexme zca-listener-congdau` rồi `pm2 delete zca-serve zca-spike-serve zca-listener-nexme zca-listener-congdau`.
   - Kiểm tra `lsof -i :56789 -i :56790` đảm bảo cả hai cổng đã trống hoàn toàn và không còn tiến trình `bun` hay `node` nào chạy `serve-with-ids.ts` hoặc `spike-serve.ts`.
   - Đợi tối thiểu 15 giây để máy chủ Zalo đóng hẳn phiên WebSocket cũ.

### 5.4. Bước nghiệm thu trên nhóm Sandbox (`profile=nexme`, `threadId=2928062252153346304`)

Sau khi bên `nexme_marathon` đã nhả hoàn toàn WebSocket, bật kết nối `nexme` trên Javis OS và nghiệm thu đủ 7 phần trên nhóm `Test nhom zalo` (`threadId=2928062252153346304`):

1. **Phần 1 (Cài đặt nhóm & 9 cờ)**: gọi `zalo_get_group_settings(threadId="2928062252153346304")`, sau đó gọi `zalo_update_group_settings(threadId="2928062252153346304", lockSendMsg=true)` rồi trả lại `lockSendMsg=false`; kiểm tra 8 cờ còn lại giữ nguyên 100%.
2. **Phần 2 (`cliMsgId` & thu hồi tin)**: gọi `zalo_send_message` vào nhóm `2928062252153346304`, lấy `messageId` + `cliMsgId` rồi thu hồi ngay bằng `zalo_undo_message`.
3. **Phần 3 (`zalo_send_file`)**: gửi một tệp thử nghiệm qua hộp gửi phiên vào nhóm `2928062252153346304`, xác nhận Zalo trả `file_done` trên kết nối MCP đang sống.
4. **Phần 4 (Nhận media sạch & HTTP 202 / 0-byte)**: kiểm tra luồng đọc/tải media không lưu tệp 0-byte, có thử lại khi CDN trả HTTP 202 và không ghi URL có chữ ký ra log.
5. **Phần 5 (Vòng đời Poll)**: gọi `zalo_create_poll` trên nhóm `2928062252153346304` (`isAnonymous=false`), gọi `zalo_get_poll(pollId, includeVoters=true)` kiểm tra danh sách `{ id, name }`, sau đó gọi `zalo_lock_poll(pollId)` xác nhận `closed: true` và `irreversible: true`.
6. **Phần 6 (`zalo_send_voice`)**: gửi tin thoại từ URL `https:` hợp lệ (`ttl >= 0`) vào nhóm `2928062252153346304`, xác nhận không lộ URL có chữ ký trong log.
7. **Phần 7 (`zalo_send_video` chặn cứng `duration > 0` cho nhóm)**: thử gọi `zalo_send_video` với `threadType=1` và `duration=0` để xác nhận bị chặn ngay trước khi gọi Zalo; sau đó gọi với `duration > 0` (mili-giây) và URL `https:` hợp lệ.

### 5.5. Bật lịch chính thức trên Javis OS

- Khi cả 7 hạng mục sandbox đạt PASS, kích hoạt các nhắc hẹn định kỳ trong mục 4 (`zalo-quiet-hours-lock` lúc `22:30`, `zalo-quiet-hours-unlock` lúc `05:30`, và cụm lịch Poll `nexme marathon`).
- Giám sát lượt chạy `22:30 -> 05:30` đầu tiên qua nhật ký `work_log` và bảng `once_ledger.sqlite3`.

### 5.6. Phương án Rollback an toàn (tránh xung đột WebSocket)

Nếu phát sinh sự cố cần đưa vận hành Zalo về lại `nexme_marathon`, bắt buộc làm theo thứ tự ngược lại:

1. **Dừng lịch và đóng kết nối trên Javis OS trước**:
   - Tạm dừng hoặc huỷ các lịch nhắc hẹn Zalo (`zalo-quiet-hours-*`, `zalo-marathon-poll-*`) trên Javis OS.
   - Tắt kết nối Zalo `nexme` ở trang Kết nối (`enabled: false`) để `mcp_client.pool` đóng hẳn tiến trình `javis-zalo mcp start`.
   - Đợi 15 giây và kiểm tra không còn tiến trình `javis-zalo` nào giữ phiên `nexme`.
2. **Bật lại `zca-serve` bên `nexme_marathon`**:
   - Chạy `pm2 start ecosystem.zca.config.js --only zca-serve`.
   - Kiểm tra `http://127.0.0.1:56789/health` và `/api/nexme/me` để xác nhận phiên đăng nhập và WebSocket listener đã lên xanh.
3. **Bật lại cờ và worker bên `nexme_marathon`**:
   - Khôi phục `ZCA_GROUP_QUIET_HOURS_ENABLED=true`, `ZCA_GROUP_DM_ENABLED=true`, `AUTOMATION_WORKFLOW_ENABLED=true` và khởi động lại `marathon-worker` cùng lịch poll từ bản chụp ở Bước 5.2.
