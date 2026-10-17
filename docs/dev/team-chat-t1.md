# Nhóm chat team T1: lõi nhóm chat, Quyền giới hạn (0.111.0)

Spec: [2026-10-13-team-chat-design.md](../superpowers/specs/2026-10-13-team-chat-design.md) (D1 tới D7 đã chốt ngày 13/10/2026). Kế hoạch: [2026-10-13-team-chat-t1.md](../superpowers/plans/2026-10-13-team-chat-t1.md), phán quyết R1 tới R3 ở đó.

## Luồng hữu ích đầu tiên

1. Chủ tạo nhóm ở trang **Nhóm** (thanh bên, nhóm Năng lực, cạnh Cộng sự): tên, mô tả, thành viên, trưởng nhóm.
2. Tin không @ thì trưởng nhóm trả lời (D1). Chọn @ từ gợi ý thì chỉ người được gọi trả lời, theo thứ tự @; người sau thấy câu trả lời của người trước.
3. Bật **Giao việc** thì tin thành một việc nhóm trong hàng đợi (D2). Không @: trưởng nhóm lập kế hoạch, giao từng phần, rồi tổng hợp. Có @: người được gọi làm thẳng.
4. Hàng đợi có **Ưu tiên** / **Bỏ ưu tiên**, đánh số đúng thứ tự chạy. Việc bị chặn rời chỗ chạy, hiện ở "Bị chặn, chờ bạn" kèm lý do, có tin vào hộp thư.
5. Kết quả về đúng nhóm, mỗi tin có tác giả, vai, nhãn việc và trạng thái bằng chữ; bản cuối có nhãn "Kết quả việc".

## Bản đồ mã

| Phần | File | Việc |
|---|---|---|
| Danh tính | `server/resonance_store.py` (`agent_register`), `server/main.py` (`save_agent`) | Mã bền cho thành viên, không bật Cộng hưởng. Tạo agent trùng slug trả 409, không ghi đè |
| Kho nhóm | `server/team_store.py` (`team.sqlite3`) | Nhóm, thành viên, sự kiện, bước nội bộ, sổ lượt, khoá bận; `set_caps`, `log_event` |
| Tin có người gửi | `server/sessions.py` | Cột `author_kind`, `author_ref`, `client_msg_id` (duy nhất trong phiên), `reply_to`, `task_id`, `step_id`, `meta_json`; ẩn `team:` và `teammate:` khỏi lịch sử chat; sổ quyết định; tin theo việc |
| Hàng đợi | `server/task_store.py` (làn `team` của `kanban.sqlite3`) | `enqueue_team` (khoá = tin nguồn, không gộp theo tiêu đề), `team_queue`, `team_priority` (CAS `queue_version`, 409), `claim_team_next` (một việc chạy mỗi nhóm, cùng giao dịch), chặn, gỡ chặn, xong, huỷ, sửa yêu cầu, khôi phục. Mã bảng Việc cũ bỏ qua mọi dòng `lane='team'` |
| Bộ chạy | `server/team_runner.py` | Định tuyến, lượt trả lời, việc nhóm (`plan`, `work`, `help`, `synthesize`), khối `JAVIS_TEAM`, trần, chống vòng, đầu ra muộn, khoá bận FIFO, sổ lượt, huỷ giữa lượt, phục hồi sau restart |
| Route | `server/team_api.py`, nối ở cuối `server/main.py` | `/teams/*` (19 route), vòng điều phối 5 giây, nhắc việc chặn quá 24 giờ, engine chỉ chữ, hộp thư, gói WS `team_message` / `team_state` |
| Giao diện | `dashboard/teams.js`, `console.js`, `index.html`, `console.css`, `app.js`, i18n | Trang Nhóm ba cột, ngăn kéo dưới 1060px, một cột dưới 760px |
| Nâng, hạ | `server/team_migration.py`, `tools/team_chat_restore_pre.py` | Snapshot `.pre-0.111.0` của `kanban.sqlite3` và `conversations.db`, công cụ khôi phục |

## Khối JAVIS_TEAM (phán quyết R1)

Agent điều phối bằng khối do host đọc ở cuối câu trả lời:

```
<!-- JAVIS_TEAM: {"op": "assign", "agent": "<mã hay slug>", "brief": "..."} -->
<!-- JAVIS_TEAM: {"op": "request_help", "agent": "<mã hay slug>", "question": "..."} -->
<!-- JAVIS_TEAM: {"op": "propose_job", "title": "...", "brief": "..."} -->
```

| Vai của lượt | Op dùng được |
|---|---|
| Trưởng nhóm trả lời trò chuyện | `propose_job` (thành thẻ, chủ bấm Tạo việc mới có việc) |
| Thành viên trả lời trò chuyện | Không có |
| Lập kế hoạch | `assign` |
| Làm, Hỗ trợ | `request_help` (một người mỗi lượt) |
| Tổng hợp | Không có |

Op sai (JSON hỏng, op lạ, người ngoài nhóm, nhờ ngược, quá độ sâu) bị bỏ, ghi chú hiện dưới tin; không có lượt nào ngoài trần.

## Trần (D7, chỉnh ở tab Cài đặt của nhóm)

12 lượt mỗi việc; 8 bước mỗi việc; độ sâu nhờ hỗ trợ 2; không nhờ ngược; 2 lượt liền cùng kết quả thì dừng (`no_progress`); 3 @ mỗi tin; 100 lượt mỗi nhóm mỗi ngày (tính cả lượt trò chuyện); 1 việc chạy mỗi nhóm; 2 nhóm chạy cùng lúc; 1 lượt cùng lúc mỗi agent (D3); chờ khoá bận 30 phút. Trần kiểm TRƯỚC khi giữ chỗ lượt, nên chạm trần không gọi model.

## Sổ lượt

Một dòng mỗi lời gọi model. Giữ chỗ và kiểm trần (ngày, việc) nằm trong CÙNG một giao dịch `BEGIN IMMEDIATE` (`reserve_turn` có `daily_cap`, `task_cap`), nên hai lượt đồng thời không cùng lọt qua chỗ trống cuối. Lỗi trước mốc gọi engine thì hoàn (`refunded`) đúng một lần. Sau mốc thì tính, kể cả lỗi, bị huỷ giữa lượt (`interrupted`), restart (`interrupted`, không tự chạy lại).

**Mốc gọi engine (review vòng 1, R4):** engine thật (`fn.marks_engine`) dựng xong engine, kiểm `is_available`, rồi mới gọi `req["engine_started"]`; bộ chạy ghi mốc ở đó. Dựng hỏng (`_resonance_engine` trả None, engine báo chưa sẵn sàng, cấu hình ném lỗi) hay bị huỷ khi đang dựng thì lượt hoàn, việc chặn `failed` với lý do "Không dựng được engine" để Chạy lại. Engine giả không khai báo thì mốc ghi ngay trước lời gọi như trước.

**Kết cục engine (R1):** adapter đọc sự kiện theo `team_runner.TextOnlyOutcome`, cùng luật với `_engine_outcome_pop` của lượt chat: final `is_error`, cờ `auth_refresh_race`, sự kiện `error` (kể cả sau final), gọi công cụ (`tool_call`, `tool_use`, `tool_result`), thiếu final, final rỗng đều là lượt `error` (đã tính), bước lỗi, việc chặn `failed`. Lỗi mất mạch đã được engine mồi lại trong lượt (`resume_failed`) không tính là lỗi.

**Bài học bền (R3):** adapter chỉ BÓC `JAVIS_LESSON` / `JAVIS_RULE` (rule hạ thành bài học vì trong nhóm chủ không nói trực tiếp với agent), trả `commit`. Pha chấp nhận (`_accept`) kiểm đầu ra còn hợp lệ rồi gọi `commit` trong cùng `accept_lock` (lượt trò chuyện); bước của việc nhóm thì `commit` chạy ở pha áp dụng (`_apply_step`) sau lần kiểm cuối (vòng 2, R7); các thao tác làm đầu ra hết hợp lệ (bỏ thành viên, đổi trưởng nhóm, huỷ, sửa yêu cầu, lưu trữ, xoá agent ở `delete_agent`) giữ cùng khoá. `commit` kiểm lại danh tính (mã bền còn trỏ đúng slug) ngay trước khi ghi, và `claim_commit(turn_id)` cho ghi đúng một lần mỗi lượt. Đầu ra không hợp lệ chỉ là bằng chứng: tin có `applied=false` và `held_lessons`, bộ nhớ agent không đổi.

## Giới hạn đã biết của T1

- **Lượt nhóm chỉ chữ** (R3): không đọc, ghi file, không MCP, không `javis_goal`. Mở công cụ cùng cổng quyền theo nhóm để T3.
  - **Đổi ở 0.142.0** ([team-chat-0142.md](team-chat-0142.md)): lượt nhóm KHÔNG còn dựng engine qua hợp đồng Cộng hưởng (`_resonance_engine`, model việc nền, chỉ Claude và engine API). Hợp đồng riêng `server/team_engine.py`: model của trợ lý, thiếu thì model chính; Codex chạy chỉ chữ (không profile, MCP rỗng, tắt công cụ native, luôn `--sandbox read-only`). Giới hạn R3 giữ nguyên: vẫn chỉ chữ, không công cụ, không MCP, không hub; Grok và Antigravity chạy bằng model chính kèm ghi chú.
  - **Đổi ở 0.194.0** (chủ 17/10/2026: "team phải đầy đủ các quyền thì mới làm việc được"): bước **Làm** và **Hỗ trợ** của một việc nhóm (`team_runner.TOOL_ROLES`) chạy CÓ công cụ như chat riêng với trợ lý: cwd là thư mục làm việc ghim của nhóm (không có thì bộ não), hub MCP gắn ở mức `full` (`main.TEAM_WORK_MODE`), file bộ não qua `javis_vault`, dựng bằng `team_engine.build_tools` (provider khác Claude đi qua các builder việc nền `aux_engine._build_*`, nên Grok Build và Antigravity cũng chạy được lượt Làm). Kết cục đọc theo `team_runner.ToolTurnOutcome` (gọi công cụ là bình thường, các luật lỗi khác giữ nguyên). Lượt công cụ trên cùng một bộ não chạy lần lượt (khoá trong tiến trình theo bộ não). Lượt trò chuyện, lập kế hoạch, tổng hợp, quét và học vẫn chỉ chữ. Test: `tests/python/test_team_work_tools.py`.
- **Không resume mạch thành viên:** mỗi lượt là một lời gọi mới mang khối nhóm: cửa sổ 20 tin GẦN NHẤT của chính phiên nhóm (gồm tin cũ của chủ và câu trả lời trước của mọi thành viên, kể cả của agent đó; tin sau lượt trước của agent có nhãn "mới"), tối đa 8.000 ký tự; sổ quyết định; đầu vào của bước. Trước review vòng 1 khối này chỉ có tin SAU lượt trước của agent, nên câu hỏi nối tiếp mất dữ kiện (R2). Tin cũ hơn cửa sổ chỉ còn qua sổ quyết định.
- **I/O ở luồng phụ (R5):** mọi đọc, ghi SQLite và file của bộ chạy và của route `/teams/*` chạy qua `run_io` (luồng phụ). Bị huỷ, kể cả huỷ lặp, khi luồng phụ đang ghi thì chờ ghi xong, chạy bước hoàn tác (hoàn lượt vừa giữ chỗ, nhả dòng khoá vừa lấy, trả việc vừa nhận về hàng) rồi mới ném huỷ; dòng khoá bận chỉ nhả sau khi lượt đã chốt. Gói WS, hộp thư và huỷ task asyncio từ luồng phụ được xếp về event loop.
- **Không stream từng chữ** (R2): câu trả lời về khi xong.
- **Chưa có reaction** (T2), **chưa có Toàn quyền** (T3).
- **Chat riêng 1:1 với agent không lấy khoá bận:** một agent có thể cùng lúc chạy một lượt nhóm và một lượt chat riêng.
- **Bỏ qua thẻ đề xuất** chỉ ẩn trong tab đang mở.
- Hiệu năng thật trên VPS chưa đo; ngưỡng 100 ms trong test là chỉ dấu cục bộ với kho giả chậm 250 ms, không phải SLA. Đo ở T4.

## Review cuối (người review mới, model mạnh nhất)

Kết luận "sẵn sàng sau khi sửa": 0 lỗi nghiêm trọng, 5 lỗi quan trọng, đã sửa hết, mỗi lỗi có test đỏ trước rồi xanh.
- Trưởng nhóm giao theo tên hiển thị ("Minh") bị bỏ và việc báo xong khi chưa ai làm: giờ khớp cả tên, không phân biệt hoa thường; mọi lệnh giao đều hỏng thì việc bị chặn.
- Sửa yêu cầu của việc @ nhiều người chỉ làm lại phần một người: giờ mọi người được giao còn thiếu kết quả bản mới đều làm lại.
- Tạm dừng rồi tiếp tục ngay làm kẹt nhóm; lỗi bất ngờ để việc treo `team_running`; vòng nền chạy phục hồi nhầm ở máy cài mới: đều đã sửa.
- Sửa thêm (nâng mức theo tác động): lượt trả lời không chạy khi nhóm đã tạm dừng, lưu trữ huỷ cả việc đang treo, bước không tiến triển thành bước lỗi để Chạy lại, khoá bận không kẹt khi huỷ, phiên nhóm không hiện trong ô tìm của khung chat chính.
- Để lại (ghi trong sổ phán quyết): bài học từ lượt đến muộn vẫn ghi vào bộ nhớ agent; trần ngày có thể vượt vài lượt khi nhiều lượt cùng lúc; khoá bận không gia hạn sau 15 phút; chữ lý do từ server chỉ có tiếng Việt; dựng tên thành viên tốn đọc file mỗi lượt (đo ở T4).

## Review mã vòng 1 (14/10/2026, head `c729f464`)

Reviewer tái hiện 2 P1 và 4 P2 bằng `exports/reviews/PR-628-T1-review-checks.py` (ngoài repo, engine giả). Trên `c729f464` cả 6 tái hiện (chế độ mặc định exit 0, `--expect-fixed` exit 1). Đã sửa, mỗi lỗi có hồi quy riêng trong repo:

| Lỗi | Sửa | Hồi quy |
|---|---|---|
| R1 [P1] engine lỗi, rỗng thành Xong | `TextOnlyOutcome` trong adapter; lượt `error` đã tính, việc chặn `failed` | `test_team_t1_review.py` mục R1: 9 kết cục xấu qua factory thật, đối chứng final hợp lệ, `resume_failed`, Chạy lại, lượt trò chuyện |
| R2 [P2] lượt hai mất ngữ cảnh | Cửa sổ 20 tin gần nhất của chính phiên nhóm | mục R2: SOURCE và câu trả lời trước có ở lượt hai, nhãn (bạn) và mới, không lẫn nhóm khác, trần 20 tin, trần 8.000 ký tự |
| R3 [P1] đầu ra muộn ghi bộ nhớ bền | Adapter chỉ bóc, `commit` sau kiểm trong `accept_lock`, ghim danh tính, `claim_commit` | mục R3: đối chứng ghi đúng, rule hạ thành bài học, rời nhóm, huỷ, sửa yêu cầu, đổi trưởng nhóm, xoá rồi tạo lại cùng slug, tranh khoá, xử lý lặp |
| R4 [P2] engine chưa dựng vẫn tính | Mốc `engine_started` sau khi dựng xong | mục R4: `_resonance_engine` trả None, engine chưa sẵn sàng, dựng ném lỗi, huỷ khi đang dựng, restart |
| R5 [P2] chặn event loop | `run_io` cho runner và mọi route `/teams/*`; giữ chỗ kèm kiểm trần một giao dịch | mục R5: kho chậm (lượt trả lời, việc, route thật), hai lượt đồng thời trần 1, tám luồng trần 3, huỷ lặp khi giữ chỗ, huỷ khi chốt lượt, huỷ khi lấy khoá, kho lỗi |
| R6 [P2] nhóm sống trỏ phiên đã mất | Khôi phục cả bộ ba kho, đối soát nhóm mồ côi lúc khởi động | `test_team_rollback.py` mục R6: vòng đầy đủ với nhóm thật và mã 0.109.0 thật, nhóm mồ côi, thiếu snapshot, hỏng giữa chừng |

Quyết định đổi so với bản trước: khối ngữ cảnh có lịch sử, không chỉ tin mới (R2); `JAVIS_RULE` trong lượt nhóm vẫn hạ thành bài học nhưng chỉ ghi khi đầu ra được chấp nhận (R3); `team.sqlite3` không còn "để nguyên" khi khôi phục (R6). Ngoài phạm vi: Toàn quyền, công cụ, stream, reaction (T2, T3).

## Review mã vòng 2 (14/10/2026, head `280959a7`)

Sáu ca vòng 1 giữ đạt. Reviewer tái hiện thêm 1 P1 và 2 P2 bằng `exports/reviews/PR-628-T1-r2-race-checks.py` (engine giả, barrier có hạn). Đã sửa:

| Lỗi | Sửa | Hồi quy (`test_team_t1_review.py`) |
|---|---|---|
| R7 [P1] kết quả bản cũ chốt Xong cho yêu cầu đã sửa | `_apply_step` và `_job_tick` chạy trong `accept_lock`, kiểm lại hiệu lực ngay trước khi áp tác động; hết hiệu lực thì tin thành bằng chứng (`superseded`, applied=false) và đi đúng nhánh đến muộn. `team_finish(expected_rev=...)` là CAS ở kho. Bài học của bước việc ghi ở pha áp dụng, không ở pha chấp nhận | mục R7: kế hoạch trả lời trực tiếp, bước làm, tổng hợp (mỗi ca sửa yêu cầu ở cửa áp dụng rồi làm lại theo bản mới), hoàn tất thắng trước thì sửa bị từ chối, huỷ, bỏ thành viên, đổi trưởng nhóm ở cửa áp dụng, CAS kho, đối chứng không sửa |
| R8 [P2] hai lần đánh thức vượt trần pool | Tính chỗ, nhận việc, giữ chỗ (`_pool`) là một đoạn găng trong `_claim_batch` (`_pool_lock`, luồng phụ); chỗ trả khi task xong; model chạy ngoài khoá; lỗi giữa chừng trả cả việc đang tạo bước đầu về hàng | mục R8: bốn nhóm, trần 2, hai dispatch qua barrier; đối chứng tuần tự; khoá không bị giữ khi model chạy; lỗi giữa lúc nhận; huỷ lặp khi đang nhận |
| R9 [P2] khôi phục hỏng sau ghi để lẫn kho | Kho tính là "có thể đã đụng" TRƯỚC khi ghi; trả về từ bản sao rồi kiểm lại (số dòng từng bảng); đích vốn không có thì gỡ; không trả được thì báo `unrecoverable` kèm bản sao | mục R9: lỗi trước và sau ghi từng kho, lỗi khi gỡ kho nhóm, đích vốn không có, không trả về được, đối chứng |

## Nâng, hạ phiên bản

- Lần đầu 0.111.0 mở `kanban.sqlite3` và `conversations.db` có từ trước, mỗi kho được chụp một bản `<tên>.pre-0.111.0` bằng SQLite backup, trước khi thêm cột. Kho mới tinh thì không chụp.
- **Hạ về 0.109.0:** tắt Javis, chạy `python tools/team_chat_restore_pre.py --yes`. Công cụ khôi phục CẢ BỘ ba kho (review vòng 1, R6):
  1. Kiểm trước cả bộ, chưa ghi gì: kho nào đã nâng thì phải có snapshot hợp lệ. Thiếu hay hỏng một snapshot là dừng, không đụng kho nào.
  2. Chép mọi kho hiện có (kể cả `team.sqlite3`) sang `<tên>.post-0.111.0-<thời điểm>`.
  3. Gỡ `team.sqlite3` khỏi chỗ chạy: trước 0.111.0 không có kho này.
  4. Ghi snapshot vào hai kho kia. Hỏng giữa chừng thì trả mọi kho đã đụng về bản ở bước 2 và báo lỗi, không báo thành công.
- **Mất khỏi kho chạy / giữ lại:** việc Kanban, tin chat và nhóm sau lúc nâng rời kho chạy; cả ba có bản `.post-0.111.0-*` để đọc lại. Nâng lại thì không có nhóm nào trỏ vào phiên đã mất, snapshot `.pre-0.111.0` dùng lại, không chụp đè.
- **Nhóm mồ côi:** nếu kho phiên bị đưa về bản cũ mà `team.sqlite3` còn (công cụ trước review, hay chép tay), lần khởi động sau vòng nền lưu trữ nhóm, ghi sự kiện `session_missing`, huỷ việc còn mở; dữ liệu nhóm giữ để đối chiếu. Gửi tin vào nhóm đó trả lỗi nghiệp vụ (TeamError), không phải lỗi khoá ngoại.
- **Hạ không khôi phục:** mã cũ không bao giờ nhặt việc nhóm, nhưng trang Việc hiện các dòng `team_*` với trạng thái lạ và phiên `team:` hiện như phiên thường.

## Kiểm

| Lệnh | Kết quả |
|---|---|
| `tests/python/test_team_identity.py` | Mã bền không bật Cộng hưởng; tạo trùng slug 409, file cũ không đổi |
| `tests/python/test_team_store.py` | 24 ca: nhóm, thành viên, trưởng nhóm, bước CAS, sổ lượt, khoá bận |
| `tests/python/test_team_messages.py` | Người gửi, chống gửi trùng, phân trang, ẩn khỏi lịch sử chat |
| `tests/python/test_team_queue.py` | 33 ca: TC9, TC14 tới TC18 (ví dụ A, C, B), cách ly bảng Việc |
| `tests/python/test_team_runner.py` | 65 ca, engine giả: TC6 tới TC13, TC17 tới TC23, khối JAVIS_TEAM sai khuôn, huỷ giữa lượt |
| `tests/python/test_team_api.py` | 40 ca trên app thật với engine giả: route, 409, đề xuất, sổ quyết định, xoá agent rồi tạo lại (TC5), lưu trữ |
| `tests/js/test_teams_ui.js` | 53 ca: danh sách, tin, hàng đợi, khung soạn, cài đặt, chỗ nối, CSS, i18n |
| `tests/python/test_team_rollback.py` | 31 ca với mã 0.109.0 thật (`bfb1c29f`): snapshot, hạ có và không khôi phục, nâng lại; R6 với nhóm thật, nhóm mồ côi, thiếu snapshot, hỏng giữa chừng |
| `tests/python/test_team_t1_review.py` | 101 ca: review vòng 1 (R1 tới R5, qua factory thật `main._team_engine_for` với engine giả) và vòng 2 (R7 tới R9), có đối chứng hợp lệ |
| `python tests/run.py --js` | 186/186 |

**Smoke giao diện** (sandbox cổng 7788, state trong worktree). Trần lượt ngày của nhóm đặt 0 trước khi gửi gì, nên không lượt nào tới engine thật; sổ lượt cuối buổi 0 dòng. Ảnh ở `exports/reviews/team-t1-smoke/`, ngoài repo.
- Tạo nhóm qua form; trưởng nhóm, số thành viên hiện ở đầu khung chat.
- Tin thường: lưu, báo "Nhóm đã dùng hết lượt hôm nay", không ai trả lời.
- @ gõ "mi" hiện gợi ý Minh; chọn thì thành thẻ; bật Giao việc thì gợi ý "Tạo 1 việc · giao cho Minh · vào cuối hàng (vị trí 1)".
- Việc chạm trần, vào "Bị chặn, chờ bạn" kèm lý do và nút Cho chạy tiếp.
- Tạm dừng nhóm, thêm B rồi C, bấm Ưu tiên C: C lên vị trí 1 với nhãn "Ưu tiên" có icon sao và nút Bỏ ưu tiên.
- 375px: danh sách là trang đầu; khung chat toàn màn, đầu khung hai hàng; cài đặt trượt lên, nền đặc; không cuộn ngang; nút 44px.
- Smoke tìm ra và đã sửa: nút ẩn vẫn hiện (`.ws-btn` đè `hidden`), cột cài đặt trống khi chưa mở nhóm, đầu khung chat bị ép trên điện thoại, ngăn kéo trong suốt, nút quay lại hẹp hơn 44px.
