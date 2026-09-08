# Tự học: Javis thông minh dần lên

***Tiếng Việt** · [English](en/22-self-learning.md)*

Mỗi lần bạn trò chuyện với Javis là một lần có thông tin đáng giữ trôi qua: một sự thật về công việc của bạn, một khái niệm vừa được giải thích, một quy trình vừa làm xong. Trang **Tự học** bật cái vòng lặp nhặt những thứ đó lại và ghi vào brain, để lần sau Javis không phải hỏi lại.

Trang này hướng dẫn bật tự học, chọn mức độ mạnh tay của nó, hiểu nó học được cái gì và chặn cái gì, và hoàn tác khi nó học sai.

## Tính năng này là gì

Sau vài lượt chat, Javis mở một **tiến trình học riêng** để đọc lại đoạn hội thoại vừa rồi và rút ra tri thức. Tiến trình này bị khoá rất chặt:

- **Chỉ đọc.** Nó chỉ được dùng `Read`, `Glob`, `Grep`, `LS`. Các công cụ `Bash`, `WebFetch`, `WebSearch`, `Task` bị chặn thẳng.
- **Cô lập, không MCP.** Nó chạy với file cấu hình MCP rỗng ở chế độ nghiêm ngặt, nên không đụng được POS, quảng cáo, Zalo hay bất kỳ nguồn dữ liệu nào bạn đã đấu. Nếu không tạo được file MCP rỗng thì Javis từ chối chạy luôn, chứ không chạy tạm với MCP của máy.
- **Ghim trong brain**, và có trần thời gian 240 giây cho mỗi lượt học.
- **Nó KHÔNG ghi file.** Kết quả duy nhất nó trả về là một khối JSON mô tả "nên học gì". Người ghi file là code Python của Javis. Nhờ vậy không có chuyện model ghi đè nhầm `MEMORY.md`, ghi ra ngoài brain, hay xoá mất ghi chú của bạn.

Trước khi ghi, code còn quét thêm hai lớp: **quét lộ khoá bí mật** (API key, token Telegram, JWT, chuỗi kết nối cơ sở dữ liệu, dòng có nhãn "mật khẩu"/"password") và **quét câu chèn lệnh** kiểu "bỏ qua mọi chỉ dẫn trước đó". Cái nào dính là bị chặn, không ghi, và lý do được ghi vào nhật ký. Ngược chiều cũng vậy: nội dung hội thoại đưa cho tiến trình học đọc đã được vô hiệu hoá các câu mệnh lệnh, để một tin nhắn khách gửi vào không điều khiển được vòng học.

Cuối cùng, Javis chỉ cho phép ghi vào đúng các thư mục `memory/`, `Memory/`, `Wiki/`, `skills/`, `.claude/skills/`, `agents/`, `workflows/`, `Javis/` của brain. Đường dẫn nào lọt ra ngoài danh sách này sẽ bị khôi phục lại ngay.

## Mở ở đâu trong Javis

Ở thanh điều hướng bên trái, mở nhóm **Bộ não**, rồi bấm **Tự học** (biểu tượng 🧠). Đầu trang hiện tiêu đề **Tự học** kèm dòng phụ "Rewire Memory · Wiki · Skill (an toàn, undo được)".

Trang làm việc trên **brain đang chọn**. Đổi brain ở đầu màn hình rồi quay lại đây thì mọi chỉ số, commit và nhật ký đều đổi theo brain mới.

## Cách dùng (từng bước)

### Bước 1: Bật tự học

Ở ô **Bật tự học**, bấm nút trạng thái. Nút đổi giữa hai nhãn:

| Nhãn nút | Nghĩa |
| --- | --- |
| `● Đang bật` | Javis đang tự học sau mỗi vài lượt chat |
| `○ Đang tắt` | Không học gì cả, kể cả khi bạn chat rất nhiều |

Lần đầu bấm bật, nút hiện "Đang git-init..." trong giây lát: Javis biến thư mục brain thành một kho git cục bộ. Việc này chỉ làm một lần và **không đẩy gì lên mạng**. Có git thì mỗi lần học là một commit, nên bạn xem lại được và hoàn tác được bằng một nút.

Xong, dòng ghi chú ngay dưới nút đổi thành kết quả thật, ví dụ "Đã git-init brain → auto-write an toàn/undo được.". Nếu máy chưa cài git, dòng đó bắt đầu bằng "⚠ Chưa git được (thiếu git?)". Câu này còn nói "auto sẽ tự hạ dry-run", nhưng đó là chữ cũ: từ bản hiện tại, tự học **vẫn ghi file bình thường khi không có git**, chỉ mất khả năng hoàn tác một chạm và mất đường sao lưu. Xem mục "Máy chưa cài git thì sao" ở dưới.

Bấm nút một lần nữa để tắt. Lúc tắt, Javis lưu ngay trạng thái tắt, không cần bấm Lưu cấu hình.

### Bước 2: Chọn chế độ ghi

Ô **Chế độ ghi** có ba nút. Bấm một nút để chọn, dòng mô tả bên dưới đổi theo.

| Nút | Mô tả hiện trên màn hình | Thực tế |
| --- | --- | --- |
| **Chạy thử** | "Chỉ ghi nhật ký 'sẽ học gì' - KHÔNG đụng file. An toàn nhất." | Vẫn chạy phân tích và ghi vào Nhật ký học, nhưng không tạo file nào trong brain |
| **Đề xuất** | "Như chạy thử, để bạn xem trước khi cho ghi." | Giống hệt Chạy thử về mặt file: liệt kê ra thứ nó định học, không ghi |
| **Tự ghi** | "Ghi thẳng vào Memory/Wiki - git-commit + undo được." | Chế độ duy nhất thật sự ghi file. Có git thì kèm luôn một commit |

**Mặc định của bản cài mới là Tự ghi.** Nếu bạn muốn quan sát vài ngày trước khi cho Javis động vào brain, chuyển sang Chạy thử rồi đọc Nhật ký học một thời gian.

### Bước 3: Chọn học cái gì

Ô **Học cái gì** có sáu công tắc. Chấm tròn đặc `●` là đang bật, chấm rỗng `○` là đang tắt. Bấm để đảo trạng thái.

| Công tắc | Mặc định | Học ra cái gì |
| --- | --- | --- |
| **Ký ức (Memory)** | Bật | Sự thật bền vững về chính bạn và doanh nghiệp bạn, ghi thành file trong `memory/facts/` và thêm một dòng vào `MEMORY.md` |
| **Tri thức (Wiki)** | Bật | Khái niệm, framework, quy trình tái dùng được, ghi thành note trong thư mục Wiki của brain |
| **Kỹ năng (Skill)** | Bật | Quy trình nhiều bước Javis vừa tự làm và thấy lặp lại được, ghi thành `skills/<slug>/SKILL.md` |
| **Vai (Agent)** | **Tắt** | Vai chuyên môn bạn nhờ đi nhờ lại trong hội thoại, ghi thành `agents/<slug>.md`. Vai đã có mà cần cải tiến thì **sửa tại chỗ**, không đẻ bản sao |
| **Chuỗi bước (Workflow)** | **Tắt** | Chuỗi từ 2 bước nhiều vai bạn đã làm lặp lại, ghi thành `workflows/<slug>.md` ở trạng thái tắt để bạn xem trước rồi tự bật. Chuỗi đã có mà thiếu bước, thừa bước hay sai thứ tự thì **sửa tại chỗ** |
| **Việc (Kanban)** | **Tắt** | Đề xuất việc nền, đẩy vào bảng ở trang **Việc** |

Dòng gợi ý dưới các nút ghi: "Wiki/Skill nên bật sau khi đã quen với Ký ức (lộ trình Phase 2/3). Việc = học xong đề xuất task nền vào bảng Việc (Kanban) - chỉ tạo thật ở chế độ Tự ghi, và task luôn chờ bạn duyệt."

Về công tắc **Việc**: nó mặc định tắt và Javis **chủ động tắt lại một lần** cho những máy đã bật từ trước. Lý do rất thực tế: khi soi bảng việc thật, gần như toàn bộ việc trong đó là do máy tự nghĩ ra, mà phần lớn worker nền không làm nổi (cần đăng nhập, cần gửi tin ra ngoài, cần chờ người khác duyệt, cần đụng mã nguồn ngoài brain). Kể từ đó, việc chỉ sinh ra khi bạn **bảo thẳng** trong chat. Công tắc vẫn còn ở đây cho ai muốn bật lại.

#### Javis sửa vai và chuỗi đã có như thế nào

Khi hội thoại cho thấy một agent hay workflow **đang có** làm sai, thiếu bước, thừa bước hay giao nhầm vai, Javis sửa thẳng vào đúng file đó thay vì tạo một bản gần giống bên cạnh. Việc ghi đè này có bốn rào, tất cả đều do code ép chứ không phải dặn bằng lời:

1. **File phải đang tồn tại.** Nói sửa mà không tìm thấy file thì bỏ qua, không âm thầm tạo mới.
2. **Phải nêu lý do**, rút từ chính hội thoại. Không có lý do thì không được sửa, và lý do đó hiện trong Nhật ký học để bạn đọc lại.
3. **Giữ nguyên những gì thuộc về bạn:** tên hiển thị bạn đặt, trạng thái bật/tắt, model bạn chọn cho agent, và mọi dòng lạ bạn tự thêm trong phần đầu file. Sửa một chuỗi không bao giờ làm nó tự bật lên hay tự tắt đi.
4. **Bạn khoá được từng file.** Thêm dòng `learn_lock: true` vào phần đầu file (frontmatter) là tự học cấm đụng file đó, mãi mãi.

Mỗi lần sửa, Javis nối một dòng ngày tháng kèm lý do vào mục `## Lịch sử (tự học)` ở cuối thân file, giữ 10 dòng gần nhất. Phần bạn viết tay nằm ngoài mục đó không bao giờ bị chạm. Và vì mỗi mẻ học vẫn được git-commit, sửa nhầm thì bấm **Hoàn tác lần học gần nhất** là xong.

**Lộ trình bật dần được khuyên dùng:** bật riêng Ký ức trước, chạy vài ngày rồi mở `MEMORY.md` xem Javis nhớ đúng chưa. Ổn thì bật thêm Tri thức Wiki. Quen tay nữa mới bật Kỹ năng, vì skill sai làm lệch cả cách Javis xử lý về sau. Hai công tắc Vai (Agent) và Chuỗi bước (Workflow) cũng mặc định tắt vì chúng tạo thứ hiện thẳng trong Studio: chỉ bật khi bạn muốn Javis tự đóng vai/chuỗi từ những việc bạn nhờ lặp lại, và cũng như skill, chúng đi qua một lượt kiểm tra thứ hai độc lập trước khi ghi (với một mục sửa thì lượt đó soi kỹ hơn: lý do sửa có căn cứ thật không, bản mới có giữ được phần đang đúng không), workflow luôn tạo ở trạng thái tắt. Công tắc Việc để cuối cùng, và chỉ khi bạn thật sự muốn Javis tự đẻ việc nền.

### Bước 4: Bật Curator nếu muốn dọn dẹp định kỳ

Ô **Curator (bảo trì định kỳ)** có một nút `● Bật` / `○ Tắt`, **mặc định là tắt**. Xem mục "Curator" ở dưới để biết nó làm gì.

### Bước 5: Lưu cấu hình

Bấm **💾 Lưu cấu hình**. Nút đổi thành "Đang lưu..." rồi "✓ Đã lưu" khoảng một giây rưỡi trước khi trở lại.

Chế độ ghi, bốn công tắc và Curator **chỉ có hiệu lực sau khi bấm Lưu**. Riêng nút Bật/tắt tự học thì lưu ngay lúc bấm.

### Bước 6: Bấm Học ngay để thử một lượt

Bấm **▶ Học ngay**. Javis tự lưu cấu hình hiện tại rồi chạy một lượt học trên brain đang chọn. Nút hiện "Đang học..." khoảng 2,5 giây rồi tự tải lại các khối bên dưới.

Lưu ý: **Học ngay vẫn tôn trọng chế độ ghi**. Đang ở Chạy thử thì bấm Học ngay cũng không tạo file, chỉ ra nhật ký.

Nếu chưa có lượt chat nào đang chờ, Javis lấy phiên hội thoại mới nhất của brain đó để học. Hội thoại quá ngắn thì nó bỏ qua lặng lẽ, không tạo mục nhật ký nào, nên thấy Nhật ký học không có gì mới thì thường là brain đó chưa có nội dung đủ dài để học.

## Javis học lúc nào (nhịp tự động)

Bạn không phải bấm gì. Mỗi lượt chat xong, Javis phân loại lượt đó rồi cộng vào một hàng chờ theo brain:

- Lượt quá ngắn hoặc chỉ là chào hỏi, "ok", "cảm ơn" thì bị bỏ ngay, không tính.
- Lượt có dấu hiệu **đặc tri thức** (câu hỏi "là gì", "gồm mấy bước", "công thức", "nguyên lý", "quy trình", "khái niệm", "cách làm") được đánh dấu riêng.
- Bạn nói "ghi nhớ", "nhớ giúp", "lưu lại" thì lượt đó được đánh dấu **gấp**.

Cứ khoảng 30 giây, Javis kiểm tra hàng chờ và bắn một mẻ học khi thoả một trong các điều kiện: đủ **3 lượt** tích luỹ, hoặc lượt gấp và đã trôi qua 30 giây, hoặc lượt đặc tri thức và đã **im 3 phút**, hoặc **im 10 phút** mà vẫn còn lượt chưa học.

Mỗi mẻ học đọc tối đa 3 phiên hội thoại gần nhất, mỗi phiên lấy 12 tin cuối, tổng nội dung cắt ở khoảng 24.000 ký tự. Nghĩa là nó học từ đoạn **vừa xảy ra**, không đào lại toàn bộ lịch sử.

Chỉ một mẻ học chạy tại một thời điểm. Tự học, Curator và các tiến trình ghi khác dùng chung một khoá trên brain nên không giẫm chân nhau.

## Cửa lọc trước khi ghi (vì sao Javis học ít hơn bạn tưởng)

Đây là phần hay gây thắc mắc: bạn thấy nhật ký ghi "đã học" nhưng file không xuất hiện. Lý do là mỗi loại đều có cửa lọc riêng.

**Ký ức (facts):**
- Độ tự tin phải từ 2 trở lên mới ghi.
- **Chỉ thêm, không đè.** File ký ức đã tồn tại thì bỏ qua, trừ khi thông tin mới được đánh dấu là thay thế cái cũ. Khi đó file cũ được gắn `superseded_by` và thêm một dòng lịch sử, chứ vẫn không bị xoá.
- Ghi xong, Javis tự chèn một dòng vào `MEMORY.md` trỏ tới file ký ức mới.

**Tri thức Wiki:**
- Mật độ (mức được giải thích có cấu trúc) phải từ 2 trở lên.
- Điều gì **chính Javis tự nói mà không có nguồn** thì **không được vào Wiki**. Nó bị đẩy sang file `_open-questions.md` để bạn tự xác minh. Đây là rào chống Javis tự đầu độc bộ nhớ bằng chính lời mình.
- Trùng khái niệm với note đã có thì không tạo note mới, chỉ ghi một đề xuất bổ sung.
- Mâu thuẫn với note cũ thì **không ghi đè**, mà thêm mục `## Mâu thuẫn` vào note cũ kèm quan điểm mới, và mở một câu hỏi cần xác minh.
- Ghi xong, Javis thêm dòng vào `index.md` (mục "## Tự học") và một dòng vào `log.md` của Wiki.

**Kỹ năng:**
- Trước khi ghi, Javis mở **một lượt kiểm tra thứ hai độc lập**, giả định các skill vừa đề xuất là sai hoặc thừa, và chỉ giữ lại cái được duyệt.
- `description` dài quá **150 ký tự** là bị chặn (bộ định tuyến cắt đúng ở đó nên phần dư mất im lặng), mở đầu bằng cụm sáo rỗng kiểu "Kích hoạt khi..." cũng bị chặn.
- **Không bao giờ ghi đè skill đã có**, và **không hồi sinh skill bạn đã tắt**.

**Việc (Kanban), khi bạn bật công tắc đó:**
- Tối đa 3 việc mỗi mẻ, độ tự tin từ 2 trở lên.
- Một cửa gác chặn thẳng các việc worker nền chắc chắn làm không nổi: việc dính đăng nhập / cookie / OTP / mã QR / đổi mật khẩu / 2FA, việc gửi hay đăng ra ngoài (Zalo, Telegram, email, fanpage, bình luận), việc chỉ ngồi chờ người khác duyệt, và việc đụng mã nguồn nằm ngoài brain. Lý do bị chặn được ghi vào nhật ký.

Mọi thứ bị chặn đều xuất hiện trong Nhật ký học ở phần **Bị chặn**, kèm lý do cụ thể. Đọc phần đó là biết ngay vì sao file không ra.

## Trần chống tốn hạn mức

Tự học chạy bằng **model việc nền** chứ không phải model chính. Bạn chọn model đó ở trang **Models** (nhóm **Kết nối**), khối "◆ Model việc nền" có ghi rõ nó phục vụ "loop · việc Kanban · nhắc hẹn · tự học · tiêu hoá nguồn". Chọn model rẻ ở đó là tự học rẻ theo.

Ngoài ra Javis tự đặt ba cái trần cứng, tính theo ngày và độc lập với nhịp gom lượt:

| Trần | Giá trị mặc định | Chạm trần thì sao |
| --- | --- | --- |
| Khoảng cách tối thiểu giữa hai mẻ | 90 giây | Mẻ đó không được ghi file |
| Số mẻ học mỗi ngày | 40 | Hạ về chạy thử |
| Token ước tính mỗi ngày | 300.000 | Hạ về chạy thử |

Khi bị hạ, Javis vẫn phân tích và vẫn ghi nhật ký "sẽ học gì", chỉ là không ghi file. Trạng thái trong nhật ký ghi rõ lý do, ví dụ "dry-run (đã chạm trần fork/ngày → hạ dry-run (backpressure))".

Bấm **▶ Học ngay** cũng chịu đúng các trần này: phần phân tích luôn chạy, nhưng muốn ra file thì phải đang ở chế độ Tự ghi **và** chưa chạm trần nào.

## Curator: bảo trì định kỳ, không xoá gì

Nút **Curator (bảo trì định kỳ)** bật một vòng dọn dẹp chạy mỗi **24 giờ**. Mô tả trên màn hình: "Dọn index, LINT Wiki (chỉ đề xuất), nén MEMORY.md. Không xoá."

Cụ thể nó làm ba việc:

1. **Dựng lại chỉ mục bộ nhớ.** Quét `memory/facts/`, thấy file ký ức nào chưa có dòng trong `MEMORY.md` thì thêm vào. Đây là cách bắt trường hợp bạn tự tạo file ký ức bằng tay mà quên thêm vào chỉ mục.
2. **Cảnh báo khi chỉ mục phình.** `MEMORY.md` được nạp vào **mọi lượt chat**, nên nó dài là mọi câu hỏi đều đắt lên. Vượt khoảng **150 dòng**, Curator ghi vào nhật ký dòng "⚠ vượt trần index (~150 dòng) - cân nhắc nén.". Nó **không tự nén**, việc gộp lại là bạn quyết.
3. **Soi sức khoẻ Wiki (LINT).** Tìm note trùng lặp, note mồ côi không ai trỏ tới, wikilink gãy, mâu thuẫn chưa giải, và chỗ còn thiếu. Kết quả chỉ là **danh sách đề xuất** ghi vào nhật ký dưới tiêu đề "Wiki LINT (đề xuất, chưa sửa)". Curator không tự sửa và không tự xoá note nào.

Nút "🩺 LINT Wiki" từng có trên dashboard đã bỏ. LINT nay chạy bên trong Curator.

Curator có ba mẹo tiết kiệm đáng biết:

- **Wiki không đổi thì bỏ hẳn vòng đó**, không gọi model.
- **Có đổi thì chỉ soi những note vừa đổi**, không quét lại cả kho. Riêng khi phát hiện note bị xoá hoặc đổi tên thì phải quét toàn bộ, vì hai việc đó làm gãy wikilink ở cả những trang không đổi.
- **Mỗi 30 ngày quét toàn bộ một lần** để bắt các vấn đề liên trang tích tụ dần.
- **Brain im lặng quá 14 ngày bị bỏ qua.** Danh sách brain của tự học chỉ có thêm chứ không bớt, nên nếu không lọc thì Curator cứ 24 giờ lại chạy trên cả những brain bạn đã bỏ từ lâu.

Muốn chạy ngay một vòng, bấm **🧹 Curator ngay**. Nút hiện "Đang dọn..." rồi tự tải lại.

## Bảng tra nhanh nút và trạng thái

| Nút / dòng | Ở đâu | Xảy ra chuyện gì |
| --- | --- | --- |
| `● Đang bật` / `○ Đang tắt` | Ô Bật tự học | Bật lần đầu thì git-init brain rồi lưu ngay. Tắt cũng lưu ngay |
| `Chạy thử` / `Đề xuất` / `Tự ghi` | Ô Chế độ ghi | Chọn mức ghi. Chỉ Tự ghi mới tạo file |
| `● Ký ức (Memory)` … `○ Việc (Kanban)` | Ô Học cái gì | Sáu công tắc loại tri thức được học |
| `● Bật` / `○ Tắt` | Ô Curator | Bật vòng bảo trì 24 giờ |
| **💾 Lưu cấu hình** | Hàng nút | Lưu chế độ + công tắc + Curator. Hiện "Đang lưu..." rồi "✓ Đã lưu" |
| **▶ Học ngay** | Hàng nút | Lưu cấu hình rồi chạy một mẻ học trên brain đang chọn |
| **🧹 Curator ngay** | Hàng nút | Chạy một vòng bảo trì ngay |
| **■ Dừng** | Hàng nút | Huỷ mẻ học và vòng Curator đang chạy |
| **↶ Hoàn tác lần học gần nhất** | Hàng nút (chữ cam) | Hỏi xác nhận "Hoàn tác (git revert) lần học gần nhất?" rồi git revert commit học cuối |

## Dòng "Chỉ số"

Ngay dưới hàng nút là một dòng tóm tắt sức khoẻ bộ não, dạng:

`Chỉ số · Ký ức: 87 · Wiki: 174 · MEMORY.md: 18363B · Fork hôm nay: 3 · Token ước tính: 41200 · Commit học: 26`

Đọc dòng này thế nào:

| Ô | Nghĩa |
| --- | --- |
| **Ký ức** | Số file trong `memory/facts/` |
| **Wiki** | Số note trong thư mục Wiki (không tính `index`, `log` và file bắt đầu bằng gạch dưới) |
| **MEMORY.md** | Kích thước chỉ mục bộ nhớ, tính bằng byte. Con số này nạp vào mọi lượt chat nên càng nhỏ càng rẻ |
| **Fork hôm nay** | Số mẻ học đã ghi được trong ngày, so với trần 40 |
| **Token ước tính** | Token tự học đã tiêu trong ngày (ước lượng thô), so với trần 300.000 |
| **Commit học** | Số commit học tìm thấy trong lịch sử git của brain (đếm tối đa 50 commit gần nhất) |

## Khối "Javis đã tự học gì (commit gần nhất)"

Khối này liệt kê tối đa 12 commit học gần nhất của brain, mỗi dòng gồm tiêu đề commit, mã hash ngắn, thời điểm, và danh sách tối đa 6 file đã đổi.

Tiêu đề commit có dạng `learn: +2 fact +1 wiki +0 skill (2026-07-29)` với mẻ học, và `curator: reindex memory (2026-07-29)` với vòng bảo trì. Chỉ hai loại tiền tố này được coi là "commit học", nên commit nền do Javis tạo lúc khởi tạo repo sẽ không lọt vào đây và cũng không bị nút Hoàn tác đụng tới.

Chưa có gì thì khối hiện "Chưa có commit học nào.". Nếu brain chưa phải kho git, khối hiện dòng cam "Brain chưa phải git repo - bật Tự học để git-init (mới xem/undo được commit)."

**Hoàn tác:** bấm **↶ Hoàn tác lần học gần nhất**, xác nhận, Javis chạy `git revert` trên commit học cuối. Thành công thì hiện hộp thoại "Đã hoàn tác:" kèm tiêu đề commit. Ba lý do thất bại thường gặp:

- "Brain chưa phải git repo"
- "Không có commit học nào để undo"
- "Các file học đang bị sửa dở, hãy tự xử lý trước: ..." (bạn đang sửa dở đúng file nằm trong commit đó. Lưu hoặc hoàn lại chỉnh sửa của bạn rồi thử lại. File dở dang **không liên quan** thì không chặn undo)

Một điểm an tâm: git ở đây chỉ theo dõi **tri thức đã chưng cất** (ký ức, Wiki, skill, `MEMORY.md`). Log thô, nhật ký học, nhật ký loop, log hội thoại, thư mục `attachments/` và `inbox/` đều nằm ngoài, nên revert luôn sạch và không đụng vào file cá nhân.

## Khối "Nhật ký học"

Khối cuối trang hiện tối đa 10 mục gần nhất, gom từ ba file nhật ký mới nhất trong `Javis/learn-log/` của brain (mỗi ngày một file `YYYY-MM-DD.md`).

Mỗi mục có mốc giờ, loại (`learn` hoặc `curator`), lý do chạy (`auto` khi tự bắn, `manual` khi bạn bấm nút), trạng thái (`auto-ghi` hoặc `dry-run` kèm lý do bị hạ), rồi danh sách những gì đã học dạng `fact=[...] wiki=[...] skill=[...]`, và mã commit nếu có. Phần thân là câu tóm tắt tiếng Việt của mẻ học, kèm mục **Bị chặn** liệt kê từng thứ bị cửa lọc chặn và vì sao.

Chưa có gì thì khối hiện "Chưa có nhật ký học.".

Nhật ký này là file markdown thường, mở được ở trang **Tệp tin** (nhóm **Bộ não**) nếu bạn muốn đọc đầy đủ thay vì 10 mục cuối.

## Đồng bộ brain với GitHub

Giữa trang còn một khối **⇅ Đồng bộ brain với GitHub (2 chiều)**. Nó nằm ở đây vì cùng dựa trên git, nhưng là một tính năng khác: đẩy toàn bộ thư mục `brains` lên một repo riêng tư và kéo về từ máy khác. Hướng dẫn đầy đủ (tạo repo, tạo token, xử lý file `.conflict-*`) ở trang [Sao lưu brain lên GitHub](18-sao-luu-github.md).

## Máy chưa cài git thì sao

Tự học **vẫn chạy và vẫn ghi file** bình thường. Ô Chế độ ghi sẽ hiện thêm dòng: "ℹ Máy chưa có `git`: Tự học VẪN chạy bình thường, chỉ là chưa có hoàn tác 1-chạm/backup lên GitHub. Cài git để bật undo + sao lưu brain."

Cái bạn mất khi không có git:

- Nút **↶ Hoàn tác lần học gần nhất** không dùng được.
- Khối "Javis đã tự học gì" trống, không xem lại được từng lần học đã đổi file nào.
- Không đồng bộ brain lên GitHub được.

Các rào an toàn còn lại giữ nguyên: tiến trình học vẫn chỉ đọc, vẫn quét khoá bí mật và câu chèn lệnh, ký ức vẫn chỉ-thêm-không-đè, và vẫn không ghi ra ngoài phạm vi thư mục cho phép.

Cài git rồi thì tắt tự học và bật lại một lần để Javis git-init brain.

## Mẹo

- **Muốn Javis nhớ chắc chắn một điều, nói thẳng "ghi nhớ ..." trong chat.** Câu có "ghi nhớ", "nhớ giúp", "lưu lại", "nhớ là" được đánh dấu gấp và học ở mẻ ngay sau đó thay vì phải chờ đủ 3 lượt.
- **Kiểm tra Javis học đúng chưa bằng chính `MEMORY.md`.** Mở trang **Tệp tin**, vào `memory/MEMORY.md`. Mỗi dòng là một ký ức. Dòng nào sai thì sửa hoặc xoá thẳng ở đó, nhanh hơn hoàn tác cả một commit.
- **Giữ `MEMORY.md` gọn.** File này nạp vào mọi lượt chat. Chỉ số vượt khoảng 150 dòng là lúc nên gộp các ký ức vụn thành một ký ức lớn hơn.
- **Muốn tri thức Wiki chất lượng, hãy nói ra nguồn.** Điều gì chỉ do Javis tự suy ra sẽ không được vào Wiki. Bạn khẳng định hoặc dẫn nguồn có tên thì nó mới được ghi.
- **Chạy thử vài ngày trước khi mở Tự ghi** nếu brain của bạn đã có nhiều ghi chú viết tay và bạn muốn chắc chắn Javis không làm loạn cách đặt tên.
- **Đổi model việc nền sang model rẻ** ở trang **Models** nếu thấy tự học ăn nhiều hạn mức. Tự học không cần model mạnh nhất.

## Sự cố thường gặp

**Bật tự học rồi, chat cả buổi mà chẳng thấy gì học.**
Kiểm tra theo thứ tự: chế độ ghi có đang là **Tự ghi** không (Chạy thử và Đề xuất đều không tạo file); các lượt chat có "đủ chất" không (chào hỏi, "ok", "cảm ơn" bị bỏ); đã đủ 3 lượt hoặc đã im 10 phút chưa; và dòng Chỉ số xem "Fork hôm nay" đã chạm 40 chưa. Nhật ký học luôn có câu trả lời chính xác.

**Nhật ký ghi đã học nhưng không thấy file mới.**
Đọc mục **Bị chặn** trong đúng mục nhật ký đó. Lý do hay gặp: ký ức trùng file đã có nên không đè, note Wiki bị loại vì Javis tự nói không có nguồn, note trùng khái niệm đã có, skill trùng tên hoặc `description` dài quá 150 ký tự.

**Bấm Học ngay không thấy gì đổi.**
Nếu đang có một mẻ học hoặc vòng Curator chạy dở thì lượt mới bị từ chối. Chờ mẻ đang chạy xong (tối đa 240 giây) rồi bấm lại, hoặc bấm **■ Dừng** trước.

**Bấm Hoàn tác báo "Các file học đang bị sửa dở".**
Bạn đang sửa dở đúng file nằm trong commit học đó. Lưu lại hoặc hoàn tác chỉnh sửa của bạn trước, rồi bấm lại. Javis cố tình không revert đè lên chỉnh tay của bạn.

**Javis học vào nhầm brain.**
Trang này làm việc trên brain đang chọn ở đầu màn hình. Đổi đúng brain rồi bấm Lưu cấu hình và Học ngay lại. Bản thân vòng học tự động thì học đúng brain của cuộc trò chuyện, không phụ thuộc brain bạn đang mở trên trang này.

**Curator bật rồi mà không thấy chạy.**
Nó chạy 24 giờ một lần, và bỏ qua brain đã im lặng quá 14 ngày. Ngoài ra khi Wiki không đổi note nào thì nó bỏ hẳn vòng đó cho đỡ tốn, nhật ký sẽ ghi lý do "wiki không đổi note nào". Muốn thấy ngay thì bấm **🧹 Curator ngay**.

**Sợ tự học làm hỏng ghi chú viết tay.**
Tiến trình học không có quyền ghi. Code ghi thì không đè file ký ức đã có, không đè note Wiki đã có, không đè skill đã có, không xoá gì, chỉ sửa agent/workflow đã có khi có lý do rõ ràng và bạn chưa khoá file đó, và chỉ được động vào các thư mục `memory/`, `Wiki/`, `skills/`, `agents/`, `workflows/`, `Javis/`. Đường dẫn nào lọt ra ngoài bị khôi phục lại ngay.

## Liên quan

- [Second Brain: bộ nhớ và Wiki](13-second-brain-bo-nho-wiki.md) - cấu trúc `memory/facts/`, `MEMORY.md` và thư mục Wiki mà tự học ghi vào
- [Skills](06-skills.md) - skill do tự học tạo ra nằm chung danh sách với skill bạn tự viết, bật tắt như nhau
- [Việc (Kanban)](21-viec-kanban.md) - nơi việc do công tắc "Việc (Kanban)" đề xuất rơi xuống
- [Sao lưu brain lên GitHub](18-sao-luu-github.md) - khối đồng bộ nằm ngay trong trang này
- [Models & engine](10-models-va-engine.md) - chọn model việc nền cho tự học
- [Quản lý tệp tin](05-quan-ly-tep-tin.md) - mở `MEMORY.md`, note Wiki và file nhật ký học để đọc hoặc sửa tay
- [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md)
