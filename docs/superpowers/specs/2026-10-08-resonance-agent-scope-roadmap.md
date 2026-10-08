# Resonance dành cho agent: phạm vi và lộ trình sau MVP

Ngày chốt hướng: 08/10/2026. Mã đối chiếu: main `09f254d0e4d009451dc58cb2e97788631c5acc1a` (0.86.1). MVP Resonance đã phát hành trong 0.86.0, commit `438f8309`, PR #587.

**Trạng thái tài liệu:** hướng sản phẩm theo yêu cầu mới của chủ dự án, kèm lộ trình và điều kiện nghiệm thu. Tiến độ cập nhật 08/10/2026: A1 đạt review mã và pilot một kịch bản (mục 12), chờ chủ dự án quyết merge; A2–A5 chưa triển khai. Đây không phải lệnh chạy model, bật tính năng hoặc sửa hệ thống đang vận hành. Kế hoạch code chi tiết của từng PR được viết từ tài liệu này và mã mới nhất khi bắt đầu.

## 1. Điều anh muốn và điều giữ lại

- Cộng hưởng trang bị cho **từng agent**, không tự trang bị cho cuộc trò chuyện thông thường.
- Có một công tắc Cộng hưởng rõ ràng trên mỗi agent. Agent tự hình thành mục tiêu từ lời giao, không bắt người dùng chọn hoặc điền mục tiêu.
- Agent biết lúc nào cần làm, khi nào chờ; nhịp tim thích nghi và vòng học từ phản hồi phải có trong đợt sau MVP, trước đội AI.
- Luật nền ít và cố định; cách làm, lịch, bài học và cách trình bày được thay đổi trong phạm vi đó.
- M1–M5 không làm lại: giữ kho mục tiêu, revision, receipt, bằng chứng, guard, hạn mức, bàn giao sản phẩm, thẻ và thử phương pháp.

Phạm vi “toàn bộ tiến độ” trong đợt rà này là chương trình Resonance cùng các hệ agent/workflow/loop/học có liên quan trong Javis. Không phải kiểm toán mọi tính năng khác của Javis hay kiểm chứng lại toàn bộ suite.

## 2. Bốn bất biến làm khung chung

1. **Có chủ thể và quyền:** mỗi mục tiêu có agent chịu trách nhiệm do host xác định, đúng brain, đúng quyền và hạn mức. Chat hoặc model không tự khai danh tính để được cấp quyền.
2. **Kết quả có căn cứ:** thành công dựa trên tiêu chí và bằng chứng đúng revision/sản phẩm; không dựa riêng vào lời model, reaction hoặc số lần làm việc.
3. **Quyền dừng luôn thắng:** tắt, tạm dừng, huỷ, thu hồi quyền và guard được kiểm trước hành động tiếp theo; học tập không được tự mở lại các chốt này.
4. **Thay đổi phải truy lại được:** ghi nguồn yêu cầu, quyết định, sản phẩm, phản hồi và cách làm; thay đổi đã áp dụng có phạm vi và đường quay lại phù hợp. Không hứa undo tác động không thể hoàn tác.

Không thêm một “điểm beat tổng” vừa quyết định quyền, vừa chấm thành công, vừa điều khiển tần suất. Các tín hiệu có ý nghĩa khác nhau phải giữ riêng.

## 3. Ranh giới sản phẩm mới

| Ngữ cảnh | Hành vi đích |
|---|---|
| Chat thông thường | Trả lời hoặc làm việc một lần theo cơ chế hiện có; không tự tạo mục tiêu Resonance hoặc lịch theo đuổi |
| Chat giao việc rõ cho agent | Hướng mở rộng sau A1: host chuyển giao có dấu vết sang agent được trang bị. A1 chưa triển khai đường này |
| Chat với agent có Cộng hưởng | Vẫn phân biệt hỏi đáp, việc một lần, nối mục tiêu và tạo mục tiêu; không tạo goal cho mọi câu |
| Workflow, loop, chatbot, kênh ngoài | Chỉ dùng Resonance khi có adapter xác định agent và uỷ quyền rõ; chưa nối thì không ngầm suy ra quyền |
| Đội AI sau này | Một agent chịu trách nhiệm mục tiêu; các vai thực hiện/review được cấp phạm vi, không sở hữu chồng chéo |

Brain là nơi dữ liệu và cấu hình chung; engine là bộ máy chạy; agent là chủ thể thực hiện. Không dùng ba khái niệm này thay nhau. Dữ liệu nguồn từ session `agent:<slug>` có thể dùng để host phân giải agent, nhưng slug trong prompt không phải căn cứ cấp quyền.

## 4. A1: phạm vi agent, công tắc và tiến độ tối thiểu

**Đây là PR chức năng đầu tiên cần làm.** Phạm vi A1 đã thu hẹp: chỉ lập mục tiêu từ phiên agent được trang bị; đường giao từ chat thường tách thành hạng mục sau A1, không gộp ngầm vào A2. Gộp màn hình tối thiểu với công tắc để người dùng nhìn thấy ngay trạng thái của chính agent vừa bật.

### Danh tính và cổng quyền

- Bổ sung liên kết agent vào goal và sự kiện. Dùng danh tính bền vững trong brain; đổi tên hiển thị không chuyển quyền hoặc làm mất mục tiêu. Phải rà cách lưu agent hiện có trước khi chọn schema cụ thể.
- Host phân giải agent từ phiên/đường dispatch đã xác thực. Áp cùng cổng ở tool, HTTP API, scheduler, bước tiếp nhận/đăng sản phẩm và phép thử phương pháp. Không chỉ ẩn `javis_goal` khỏi danh sách tool.
- `Principal("agent", "javis", brain)` hiện tại không đủ làm danh tính riêng cho nhiều agent. `/goal-requests` cũng phải chuyển qua cổng agent, không được thành đường vòng từ chat thường.
- Danh sách mục tiêu, phản hồi, revision và sản phẩm phải được lọc đúng agent/brain, kể cả hai brain trùng slug. Người dùng owner có đường quản lý mục tiêu theo quyền hiện có.

### Công tắc

Một công tắc **Cộng hưởng** trong cấu hình agent, mặc định tắt khi chưa được trang bị. Tắt Cộng hưởng không tắt khả năng chat/làm việc một lần của agent và không tác động các loop/reminder độc lập.

| Thao tác | Ngữ nghĩa |
|---|---|
| Bật | Cho phép agent nhận và tiếp tục mục tiêu hợp lệ trong quyền/hạn mức; không tự mở guard, pause hoặc goal đã huỷ |
| Tắt | Chặn giữ lượt mới và tác động mới; yêu cầu dừng công việc đang chạy theo khả năng engine; giữ dữ liệu để xem lại |
| Đang có lượt model | Lượt đã bắt đầu vẫn tính; không quảng bá “dừng tức thì” hay hoàn lại chi phí. Chặn đăng/nộp khi đã thu hồi quyền; lưu kết quả để đối soát nếu có |
| Bật lại | Đối soát phần dở, dùng lại đầu ra hợp lệ khi đủ điều kiện; không tự nhân bản hành động hoặc bắt đầu goal đã kết thúc |

Đề xuất lưu cờ hiệu lực và số phiên bản cấu hình trong nguồn host quản lý, để quyết định giữ hạn mức/áp dụng có thể kiểm nhất quán. Không để agent tự ghi file cấu hình để bật lại quyền của mình. Chi tiết persistence và đồng bộ với metadata agent phải được chốt trong thiết kế PR A1.

### Di chuyển dữ liệu cũ

- `Javis/resonance.json` cũ là cờ theo brain; không được tự nhân nó thành “mọi agent đều bật”. Có thể giữ nó làm công tắc quản trị tổng trong giai đoạn chuyển đổi, nhưng UI phải nói rõ khi nó chặn agent.
- Goal cũ chưa có danh tính agent đáng tin cậy: giữ nguyên lịch sử, đưa vào danh sách chờ gán. Không tự gán theo tên gần giống hay phiên mới nhất. Owner gán một lần qua đường có kiểm quyền; sau đó mới đủ điều kiện chạy tiếp.
- Goal mới chỉ thuộc agent; chat thường có thể hiển thị tiến độ đã được uỷ quyền, không được tự thành chủ thể thực thi.
- Không xoá SQLite, bằng chứng hoặc mục tiêu đã nghiệm thu để “làm sạch” migration. Kiểm với bản sao dữ liệu cũ và đường khôi phục trước khi phát hành.

### Màn hình tối thiểu trên trang agent

Hiện: bật/tắt, mục tiêu/revision, tiêu chí đạt/chưa đạt/chưa biết cùng căn cứ, sản phẩm đang có hiệu lực, đang chờ ai hoặc bị chặn vì gì, lần thức tiếp theo và lý do, hạn mức đã dùng/còn, nút dừng. Chat thường chỉ hiện thẻ liên kết tới mục tiêu agent khi có việc đã giao.

Không dùng một phần trăm do model đoán. Tỷ lệ tiêu chí đã xác minh, nếu hiển thị, phải gọi đúng tên và không coi là phần trăm khối lượng công việc.

**Nghiệm thu A1:** chat thường không tạo goal kể cả gọi API/tool trực tiếp; agent A bật không cấp quyền cho agent B; tắt trong lượt chặn bước tiếp theo; rename/delete/restart không chuyển nhầm chủ thể; dữ liệu cũ không mất hoặc tự chạy; thẻ và điều khiển hoạt động đúng agent.

## 5. A2: heartbeat thích nghi

Lịch MVP đã có claim/lease, next_wake, backoff và restart. Dùng lại nền đó; không dựng thêm một scheduler độc lập gọi model song song.

Một heartbeat là bước host xem có lý do hợp lệ để thực thi hay không. Không có lý do thì không dựng engine và không gọi model.

- Ưu tiên sự kiện có ích: góp ý mới, nguồn dữ liệu đổi, kết quả tác vụ phụ hoặc mốc xem lại thực sự tới hạn.
- Chờ phản hồi người dùng thì ngủ; im lặng không bị phạt và không tự thành quyền hành động.
- Có bước hữu ích tiếp theo thì giữ lượt trong hạn mức; lỗi hoặc thiếu thông tin thì giãn nhịp/chờ đúng điều kiện. Không tự thử lại vô hạn.
- Gom các sự kiện trùng; một sự kiện, một hành động logic. Thông báo do chính agent phát ra không được kích hoạt vòng tự gọi mình.
- Tách lịch quan sát guard với lịch làm việc. Giãn worker không được bỏ theo dõi guard đã cam kết; thu hồi quyền quan sát phải báo mất khả năng giám sát, không giả là clear.
- Cùng một công việc đã gắn goal chỉ có một bên quản lịch. Loop cũ khác việc và reminder giờ cố định vẫn giữ ngữ nghĩa hiện tại.
- Tần suất là kết quả của chính sách có phiên bản, dựa vào trạng thái, thông tin mới, độ khẩn cấp và chi phí còn lại. Các khoảng tối thiểu/tối đa là cấu hình, không thêm luật cố định theo ngành.

**Nghiệm thu A2:** đồng hồ giả kiểm ngủ/thức, event trùng, hai scheduler, restart, nguồn hồi phục, guard khi worker ngủ, hết hạn mức và tắt agent; mỗi lần thức có lý do truy được; không có sự kiện cần xử lý thì 0 lượt model.

## 6. A3: vòng phản hồi và học từ reaction

M4 đã có phản hồi cách hiểu/đầu ra; M5 đã có compare_methods và áp dụng trong revision. Phần mới là biến phản hồi có nguồn thành đề xuất học, thử và ghi nhận, không gắn điểm emoji trực tiếp vào scheduler.

| Tín hiệu | Dùng cho | Không được suy ra |
|---|---|---|
| Reaction trên lời nói của agent | Giả thuyết về cách trình bày, độ dài, thời điểm báo tin, mức làm phiền | Công việc đạt, thêm quyền, tăng hạn mức, tự tăng số lượt |
| Đúng ý / Hiểu chưa đúng | Sửa hoặc xác nhận cách hiểu của đúng revision | Sản phẩm đã đạt |
| Đạt yêu cầu / Cần chỉnh | Tiêu chí human_confirmation của đúng artifact hash/revision | Vượt guard hoặc thay kết quả kiểm khách quan |
| Kết quả đo, bằng chứng, chi phí | So cách làm trên cùng thước đo | Quy công mọi biến động cho hành động agent khi chưa có căn cứ |

Vòng đích: **ghi phản hồi có nguồn → đề xuất thay đổi nhỏ → thử trong ngân sách → so với cách cũ → áp dụng trong phạm vi đã kiểm hoặc giữ nguyên → tiếp tục quan sát**.

- Reaction thay đổi/thu hồi phải thay thế đóng góp cũ, không cộng điểm mỗi lần bấm; gắn message, agent, goal/revision/artifact khi liên quan và người phản hồi có quyền.
- Chat thường không bị thu vào vòng học Resonance toàn cục. Phản hồi tại thẻ của agent có thể tới agent đó ngay cả khi thẻ được xem trong chat thường.
- Không phạt việc người dùng không bấm. Một reaction không tự sinh lượt model; gom phản hồi để xử lý cùng lượt hợp lệ hoặc trong ngân sách khám phá đã cấp.
- Bài học ban đầu là giả thuyết có phạm vi và bằng chứng. Không biến thành sở thích toàn hệ thống chỉ vì một người thích một câu trả lời.
- Phản hồi “nói ít hơn” có thể giảm số thông báo; không làm chậm việc kiểm guard hay giấu một cảnh báo bắt buộc. Phản hồi không được biến việc khó thành tiêu chí dễ để đạt điểm cao.
- Cách làm tốt được áp dụng qua cơ chế thử M5; còn giới hạn theo revision cho tới khi có bằng chứng chuyển giao. Cách trình bày có thể lưu theo agent/người dùng nhưng vẫn có provenance và khả năng rút lại.

**Nghiệm thu A3:** 👍 không làm goal thành công; 👎 không tự ghi thất bại khách quan; không phản hồi là unknown; phản hồi muộn/sai revision không áp nhầm; bấm lại không tăng điểm; ứng viên thua/unknown giữ cách cũ; thu hồi bài học ngừng áp dụng.

## 7. A4 và A5

**A4: bàn giao sản phẩm đa engine.** Một hợp đồng host kiểm đường dẫn/quyền, kết quả thực thi, bytes/hash và revision. Claude Code hiện có adapter Write thành công; thêm từng adapter Codex/Grok/Antigravity hoặc nộp nội dung để host ghi trong đúng quyền. Không coi lời model tự khai là receipt. Cùng bộ ca kiểm để so tương đương, không tuyên bố mọi engine đã hỗ trợ chỉ vì cùng tên API.

**A5: đội AI làm và review.** Tái sử dụng workflow graph, verify_agent và runtime có grant; bắt đầu một agent làm và một agent review, một goal chịu trách nhiệm cuối. Review gắn đúng hash/revision, reviewer không tự sửa tiêu chí, cả hai dùng hạn mức chung có chia phần. Bản bị sửa sau review phải được review lại. Owner dừng thì cả hai dừng theo phạm vi công việc, không tự sinh agent mới để vượt chốt.

Đội AI là sau A1–A3. Theo lộ trình mặc định A4 đứng trước A5 để thống nhất bàn giao; nếu chỉ dùng một engine đã được kiểm thì A4 không phải phụ thuộc kỹ thuật bắt buộc của mô hình hai vai.

## 8. Thứ tự, đầu ra và cổng hoàn thành

| Mốc | Kết quả nhìn thấy được | Trạng thái 08/10 |
|---|---|---|
| D0 | Xác minh vận hành trên máy triển khai | Localhost thử ghim `438f8309` (0.86.0) đạt 13 kiểm không model và 1 chat thật; commit, cách chạy và kết quả ở [biên bản D0](../../dev/resonance-d0-local-check-2026-10-08.md). VPS chưa kiểm, không chặn thiết kế A1 |
| A1 | Trang agent có công tắc Cộng hưởng, mục tiêu đúng chủ thể và tiến độ tối thiểu | Đạt review mã (`cc79deb2`), pilot A1-1 đạt kỹ thuật và nội dung trong một kịch bản. PR #590, chưa merge. Biên bản: [resonance-a1-verification](../../dev/resonance-a1-verification.md) |
| A2 | Agent thức vì lý do cụ thể, ngủ khi chờ, không gọi model vô ích | Có nền MVP; chưa tích hợp nhịp thích nghi theo agent |
| A3 | Phản hồi dẫn tới điều chỉnh có kiểm chứng; không chạy theo emoji | Có feedback M4 và so phương pháp M5; chưa có vòng học reaction |
| A4 | Các engine nộp sản phẩm theo cùng hợp đồng host | Có bàn giao Claude Code; adapter khác chưa có |
| A5 | Một agent làm, một agent review; báo rõ ai đang chờ ai | Có hạ tầng workflow/reviewer; chưa thành đội Resonance |

A1–A5 là thứ tự phát triển, không phải năm tính năng đã có. Mỗi mốc ra một PR hoặc các PR nhỏ có giá trị kiểm riêng; không cần xí chỗ toàn bộ số phiên bản ngay bây giờ. Không đưa lịch ngày hoàn thành hoặc % công sức khi chưa ước lượng.

Chỉ gọi model thật khi điều kiện/mục tiêu pilot và hạn mức của lần chạy đó đã rõ; ngân sách các pilot cũ không chuyển thành quyền gọi thêm. Review tài liệu này không tự mở phát hành chức năng.

## 9. Đối chiếu bộ kế hoạch 01/02/03 cũ

| Kế hoạch cũ | Cách dùng tiếp |
|---|---|
| A1–A4 Foundation: hợp đồng/kho/evaluator/framer | MVP đã làm lõi. Rà phần thiếu và scope agent, không dựng lại song song |
| A5 Foundation và B5 Runtime: UI | Phần một agent đưa sớm vào A1 mới; UI nhóm để A5 mới |
| B1/B2: grant/thực thi | Tái dùng M1/M3 và bổ sung cổng theo agent trong A1 |
| B3: beat | Đưa thành A2 mới, dùng lịch hiện có, không chờ toàn bộ Runtime |
| C1/C2: thử/áp dụng phương pháp | Dùng M5 làm nền của A3; giữ giới hạn bằng chứng hiện có |
| C3: bài học có nguồn | Đưa phần phản hồi vào A3 mới |
| B4: nhóm/mục tiêu con | Thu hẹp ban đầu thành cặp làm/review A5 |
| B6, C4/C5: undo tổng quát, supervisor, tự sửa code | Hoãn; không nằm trên đường bắt buộc đợt kế |

Ba kế hoạch cũ là tài liệu tham khảo; không thực thi nguyên tuần tự sau MVP. Khi có mâu thuẫn về **phạm vi mới và thứ tự sau MVP**, tài liệu ngày 08/10 này được ưu tiên. Không sửa lại lịch sử nghiệm thu M1–M5.

## 10. Những điểm cần chốt khi viết thiết kế PR A1

Danh tính agent bền vững và rename/delete; kho lưu công tắc do host kiểm soát; schema/migration cho goal cũ; uỷ quyền từ chat/kênh ngoài; giới hạn quyền cho agent được nối tới khách hàng; vòng đời công việc đang chạy khi tắt. Đây là quyết định kỹ thuật cần đọc mã mới nhất, không phải câu hỏi bắt người dùng tự đặt mục tiêu.

Nguồn audit và các khoảng trống bằng chứng: [Báo cáo tiến độ 08/10](../../dev/resonance-progress-audit-2026-10-08.md). Trang theo dõi: HTML (`exports/javis-resonance-tien-do.html`, ngoài git, chỉ có trên máy chủ dự án).

## 11. Cập nhật sau review đề xuất A1 (08/10/2026)

- **Phạm vi A1 thu hẹp:** chỉ lập mục tiêu trong phiên của agent đã bật Cộng hưởng. Đường giao việc từ chat thường sang agent là hạng mục riêng sau A1, không gộp vào A2. Chat thường vẫn xem thẻ hợp lệ theo quyền chủ dự án; lệnh dừng và huỷ không mất hiệu lực.
- **D0:** biên bản [resonance-d0-local-check-2026-10-08.md](../../dev/resonance-d0-local-check-2026-10-08.md). Bằng chứng vận hành cục bộ, không phải VPS hay server cổng 7777.
- **Thiết kế A1:** [2026-10-08-resonance-a1-agent-scope-design.md](2026-10-08-resonance-a1-agent-scope-design.md). Đã qua các vòng review, xem mục 12 dưới.

## 12. Tiến độ A1 (08/10/2026)

- **Mã:** PR #590. Review mã đạt ở `cc79deb2`; `e01eb3c2` thêm test hồi quy phục hồi, `e0a60352` thêm hồ sơ pilot.
- **Pilot A1-1** (phiên trợ lý, 2 lượt chat Opus, 0 việc nền Sonnet, xác nhận cuối mô phỏng): đạt kỹ thuật và nội dung, trong một kịch bản.
- **Biên bản nghiệm thu:** [resonance-a1-verification](../../dev/resonance-a1-verification.md).
- **Chưa làm:** chưa merge (chờ chủ dự án). A2–A5 chưa bắt đầu code. Hiệu năng VPS đi PR riêng (#592).
