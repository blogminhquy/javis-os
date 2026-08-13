# Skills

Skill là "kỹ năng đóng gói" cho Javis: một hướng dẫn viết sẵn để AI làm đúng một loại việc theo chuẩn của bạn (ví dụ viết email bán hàng, dựng trang bán hàng, nghiên cứu chuyên sâu). Khi bạn nói một câu khớp với mô tả của skill, Javis tự lấy hướng dẫn đó ra dùng, không cần bạn dán lại quy trình mỗi lần.

Trang này hướng dẫn quản lý skill trong dashboard: xem theo nhóm, tìm kiếm, bật/tắt, thêm, sửa, xoá, xuất/nhập, gọi tay bằng menu lệnh, và cách nhờ Javis tự tạo skill bằng lời.

## Tính năng này là gì

Một skill trong Javis là một thư mục chứa file `SKILL.md`, đặt tại `skills/<slug>/SKILL.md` bên trong brain đang chọn (Javis tự mirror sang `.claude/skills` để Claude Code nạp native; brain cũ để ở `.claude/skills` sẽ được tự dời sang `skills/`). File này có 3 phần đầu (frontmatter) quan trọng:

- `name`: tên hiển thị của skill.
- `description`: mô tả ngắn, chính là **trigger** - quyết định KHI NÀO skill được kích hoạt. Trường này có luật viết riêng, đọc kỹ mục ngay bên dưới trước khi điền.
- `group`: tên nhóm để dashboard gom skill lại cho gọn (ví dụ Marketing, Bán hàng, Nội dung). Trường này bắt buộc; nếu để trống skill sẽ rơi vào nhóm "Chung".

Phần còn lại của file là nội dung hướng dẫn chi tiết cho AI khi skill chạy.

Bản chuẩn (canonical) của skill nằm ở `skills/<slug>/SKILL.md` - đúng cái dashboard hiển thị và đúng cái Javis nạp qua router. Ngoài ra Javis còn giữ một bản **mirror** ở `.claude/skills/<slug>` để Claude Code nạp native. Bản mirror giống hệt bản gốc, chỉ khác một chỗ: nếu `description` dài quá 150 ký tự thì bản mirror bị rút xuống 150 ký tự kèm dấu "…" (bản trong `skills/` giữ nguyên chữ bạn viết). Chuyện này chỉ xảy ra với skill nhập từ gói ngoài hoặc viết tay qua trang Tệp tin, vì skill lưu qua biểu mẫu đã bị chặn từ trước.

## Luật viết `description` (đọc trước khi tạo skill)

Đây là chỗ hay làm người dùng tắc mà không hiểu vì sao. Khi bạn bấm **💾 Lưu**, server kiểm tra `description` và **từ chối lưu** nếu vi phạm một trong hai luật:

**1. Tối đa 150 ký tự.** Đây không phải chuyện thẩm mỹ. Javis cắt mô tả đúng ở 150 ký tự khi bơm vào system prompt và vào mô tả tool `javis_use_skill`, nên phần dư mất im lặng và skill không route được. Lý do từ chối hiện đúng chữ: "description dài N ký tự, vượt trần 150. Router cắt đúng ở 150 nên phần dư MẤT IM LẶNG và skill không route được. Đưa ví dụ trigger xuống mục '## Khi nào dùng' trong thân file."

**2. Không mở đầu bằng cụm sáo rỗng.** Các cụm bị chặn: "Kích hoạt khi...", "Sử dụng skill này khi...", "Dùng skill này khi...", "Skill này dùng / Skill này được dùng...", "Use this skill when...", "Activate when...". Mọi skill đều mở y hệt nhau nên cụm đó đốt ngân sách ký tự mà không phân biệt được skill nào với skill nào. Lý do từ chối gợi ý luôn cách viết đúng: nêu thẳng năng lực, ví dụ "Tóm tắt biên bản họp thành danh sách việc cần làm."

Cách viết đúng: một câu nêu thẳng skill **làm được gì**, dưới 150 ký tự. Ví dụ trigger dài, danh sách từ khoá, các tình huống chi tiết thì đưa xuống mục `## Khi nào dùng` trong **thân** file `SKILL.md` - chỗ đó không bị cắt và chỉ được đọc khi skill đã nạp. Nói gọn: phần mô tả để TÌM, thân file để LÀM.

Luật này áp cho cả biểu mẫu trên dashboard lẫn skill do trang **Tự học** đề xuất (skill vi phạm bị chặn, ghi vào danh sách bỏ qua).

## Trigger hoạt động thế nào

Skill tự kích hoạt dựa trên trường `description` (và bạn cũng gọi tay được, xem mục kế tiếp). Khi bạn gõ hoặc nói một yêu cầu, Javis so khớp yêu cầu với `description` của các skill đang bật, thấy khớp thì nạp hướng dẫn tương ứng. Trên Claude Code là nạp native; trên các engine khác Javis bơm danh sách skill vào system prompt và nạp qua tool `javis_use_skill`.

Vì vậy chất lượng của một skill phụ thuộc lớn vào cách bạn viết `description`. Mô tả nêu đúng năng lực và đúng từ khoá thì skill "bắt" đúng lúc. Mô tả chung chung sẽ khiến skill hoặc không bao giờ chạy, hoặc chạy nhầm.

Lưu ý: skill dùng được trên **mọi engine**. Claude Code nạp native; ChatGPT/Codex, OpenRouter và OpenAI/Anthropic/Google Gemini API dùng skill qua router (Javis bơm danh sách skill vào system prompt) và tool `javis_use_skill`. Xem [Models & engine](10-models-va-engine.md) để biết chi tiết từng engine.

## Gọi skill bằng tay: menu lệnh "/"

Không phải lúc nào cũng phải chờ trigger tự bắt. Gõ dấu **`/`** ở ô chat là một menu hiện ra ngay phía trên ô nhập:

- Ba lệnh phiên đứng đầu: **`/new` Hội thoại mới**, **`/reset` Reset phiên**, **`/stop` Dừng**.
- Bên dưới là danh sách skill của brain đang chọn, mỗi dòng gồm `/slug`, tên skill và dòng mô tả.

Cách dùng: gõ tiếp vài chữ để lọc dần (khớp theo slug trước, rồi tới tên), dùng phím **mũi tên lên/xuống** để chọn, **Enter** hoặc **Tab** để chốt, **Esc** để đóng menu. Bấm chuột vào một dòng cũng được.

Chọn một skill thì ô chat được điền sẵn `/slug ` và con trỏ đứng chờ - bạn gõ tiếp nội dung yêu cầu rồi Enter để gửi. Javis dịch câu đó thành lời nhắc: "Hãy dùng skill `<slug>` với yêu cầu: ... Nếu không có skill tên này thì cứ xử lý yêu cầu của tôi bình thường." Chọn một lệnh phiên thì nó chạy ngay, không cần Enter.

Trên Telegram, nhắn `/<slug>` (kèm nội dung phía sau nếu cần) cho ra đúng mẫu tương tự. Riêng khi engine đang là OpenRouter, Javis trả lời "⚠ Skill cần engine Claude CLI. Gửi /cli để đổi, rồi /<slug> lại."

## Trần 20 skill của router

Danh sách skill mà Javis bơm vào system prompt và vào mô tả tool `javis_use_skill` bị **cắt ở 20 skill**. Phần dư chỉ còn một dòng "…(+N skill nữa - xem `Javis/index.md`)".

Hệ quả cần biết: nếu brain của bạn bật nhiều hơn 20 skill, những skill từ thứ 21 trở đi **không nằm trong router**, nên trên các engine dùng router (ChatGPT/Codex, OpenRouter, OpenAI/Anthropic/Google Gemini API) chúng sẽ không tự kích hoạt. Chúng vẫn còn nguyên và vẫn nạp được: gọi tay bằng `/slug` là chạy bình thường, vì tool `javis_use_skill` nhận mọi slug đang bật chứ không chỉ 20 cái được liệt kê.

Cách xử lý: tắt bớt skill không dùng tới để 20 chỗ trong router dành cho những skill bạn thật sự muốn Javis tự bắt.

## Skill hệ thống và skill của bạn

Javis chia skill làm 2 loại:

- **Skill hệ thống** (thẻ có nhãn "hệ thống"): chức năng mặc định của Javis OS, hiện gồm 6 cái:

  | Slug | Làm gì |
  |---|---|
  | `javis-builder` | Tạo hoặc sửa năng lực của Javis: agent, skill, workflow, loop, plugin |
  | `ingest-source` | Tiêu hoá một source thô vào Second Brain, chưng cất thành tri thức wiki |
  | `query-wiki` | Khai thác tri thức trong Second Brain, trả lời có trích dẫn |
  | `lint-wiki` | Rà soát sức khoẻ wiki, trả về danh sách vấn đề |
  | `notes` | Lưu tin nhắn hiện tại nguyên văn vào `sources/` (kèm ảnh), tự chưng cất lên wiki nếu note đáng |
  | `html-to-webcake` | Chuyển một trang HTML thành file `.pke` mở được trong trình dựng trang Webcake |

  Bản gốc nằm trong thư mục cài đặt của app (không nằm trong brain), nên chúng **có mặt ở mọi brain** và **tự cập nhật khi bạn cập nhật Javis OS** lên phiên bản mới. Loại này không xoá được từ dashboard (lỡ xoá file thủ công thì lần khởi động sau tự cài lại); muốn ngừng dùng thì **tắt** như skill thường - trạng thái tắt được giữ nguyên qua mọi lần cập nhật.
- **Skill của bạn**: tạo qua nút + Skill, qua chat, nhập từ gói `.zip`, hoặc do trang Tự học đề xuất. Đây là dữ liệu của brain - đổi brain thì bộ skill đổi theo, cập nhật app không đụng tới.

Bạn vẫn **Sửa** được skill hệ thống. Khi đó bản trong brain trở thành bản riêng của bạn: Javis giữ đúng chỉnh sửa đó và ngừng tự cập nhật đè lên. Muốn quay về bản chuẩn (kèm tự cập nhật), xoá thư mục skill đó trong `skills/` của brain (bằng trang Tệp tin) rồi khởi động lại - bản hệ thống mới nhất sẽ được cài lại sạch.

## Skill khác Plugin chỗ nào

Hai thứ này dễ lẫn vì cùng nằm trong nhóm **Năng lực** trên thanh điều hướng.

| | Skill | Plugin |
|---|---|---|
| Bản chất | Tri thức **CÁCH LÀM**: một file hướng dẫn cho AI đọc rồi làm theo | **CODE Python thật** chạy trong tiến trình server |
| Cho ra cái gì | Một quy trình, khung mẫu, bộ quy tắc | Một **tool** mới mà mọi engine gọi được, và/hoặc **hook** chạy quanh mỗi lần gọi tool |
| Nằm ở đâu | `skills/<slug>/SKILL.md` trong brain | Thư mục `plugins/<slug>/` (gồm `plugin.yaml` + `plugin.py`) |
| Bật thế nào | Tích ô đánh dấu trên thẻ là xong | Plugin do bạn cài còn cần biến môi trường `JAVIS_ENABLE_USER_PLUGINS=true` rồi khởi động lại |

Chọn thế nào: cần **hướng dẫn** làm việc bằng công cụ sẵn có thì viết Skill. Cần một **hành động Python cụ thể** chưa có nguồn nào phủ (tính toán, biến đổi dữ liệu, gọi một API đơn giản) thì viết Plugin. Còn nếu là một nguồn dữ liệu ngoài đã có sẵn server thì đấu MCP ở trang Kết nối, đừng viết plugin. Chi tiết ở [Plugins](20-plugins.md) và [Kết nối & số liệu kinh doanh](09-mcp-va-so-lieu.md).

## Mở ở đâu trong Javis

Mở dashboard (mặc định tại cổng 7777), nhìn thanh điều hướng bên trái, mở nhóm **Năng lực** rồi bấm mục **Skills**. Nhóm này có 4 mục: Agents, Skills, Workflows, Plugins.

Đầu trang có tiêu đề **Skills** kèm dòng trạng thái, ví dụ "3/5 bật · nguồn `skills/`". Con số này cho biết bao nhiêu skill đang bật trên tổng số, và nhắc rằng nguồn skill là thư mục `skills/` của brain hiện tại.

Bên phải tiêu đề là hai nút: **⤒ Nhập** (đưa gói skill từ ngoài vào) và **+ Skill** (tạo skill mới).

Nếu brain chưa có skill nào, trang hiện dòng "Brain chưa có skill. Bấm + Skill để tạo (tự lưu vào `skills/` + xếp nhóm)".

## Bố cục màn hình Skills

Khi đã có skill, màn hình chia 2 phần:

- **Cột nhóm (bên trái):** liệt kê các nhóm, đứng đầu là **Tất cả**, rồi tới từng nhóm theo thứ tự chữ cái. Mỗi dòng có số lượng skill trong nhóm đó. Bấm một nhóm để lọc danh sách chỉ còn skill thuộc nhóm ấy.
- **Danh sách skill (bên phải):** phía trên có tiêu đề nhóm đang xem, số skill đang hiện, và ô **Tìm skill…**. Bên dưới là các thẻ skill.

Mỗi thẻ skill hiển thị:

1. Ô đánh dấu (checkbox) bật/tắt ở đầu thẻ.
2. Tên skill (kèm biểu tượng 🧩). Skill hệ thống có thêm huy hiệu **hệ thống**.
3. Dòng mô tả (`description`).
4. Dòng cuối: 📂 tên nhóm · slug. Nếu skill đến từ thư mục `.agents` sẽ có thêm ghi chú ".agents". Cuối dòng này còn có thông tin mức dùng (xem ngay bên dưới).

Skill đang tắt sẽ hiển thị mờ đi. Khi rê chuột vào thẻ, các nút thao tác hiện ra ở góc phải: **Sửa**, **⤓ Xuất**, **Xoá**. Riêng skill **hệ thống** chỉ có mỗi nút **Sửa** (không xuất, không xoá được). Trên màn hình hẹp dưới 860px, các nút này luôn hiện sẵn ở đáy thẻ vì điện thoại không có thao tác rê chuột.

### Dòng "đã dùng N lần" và "chưa thấy dùng"

Ở cuối dòng nhóm · slug, Javis hiện một trong hai nhãn:

- **"đã dùng N lần, gần nhất <ngày>"** khi skill đã được nạp ít nhất một lần.
- **"chưa thấy dùng"** (chữ mờ, nghiêng) khi skill đã quá 30 ngày mà không có tín hiệu dùng nào.

Đây là **tín hiệu dương một chiều**, cần hiểu đúng kẻo oan cho skill: Javis chỉ đếm được lần nạp đi qua tool `javis_use_skill`. Claude Code nạp skill native qua `.claude/skills` thì **không** đi qua bộ đếm. Vậy nên "đã dùng N lần" chắc chắn đúng, còn "chưa thấy dùng" chỉ có nghĩa là chưa có bằng chứng, **không** có nghĩa skill vô dụng. Rê chuột vào nhãn đó sẽ thấy đúng lời giải thích này. Không có gì tự tắt hay tự xoá dựa trên nhãn này - bạn tự quyết.

Số liệu này lưu ở `Javis/skill-usage.json` trong brain, tách khỏi file `SKILL.md` để mỗi lần dùng skill không đẻ ra một thay đổi rác trong git của brain.

## Tìm kiếm skill

Gõ vào ô **Tìm skill…** ở đầu danh sách. Javis lọc ngay khi bạn gõ, so khớp từ khoá với cả tên, mô tả và slug của skill. Bộ lọc tìm kiếm chồng lên bộ lọc nhóm: nếu đang đứng ở một nhóm cụ thể, tìm kiếm chỉ chạy trong nhóm đó; muốn tìm toàn bộ thì bấm **Tất cả** trước.

## Bật và tắt skill (từng cái)

1. Vào trang **Skills**.
2. Tìm skill cần đổi trạng thái.
3. Bấm vào ô đánh dấu (checkbox) ở đầu thẻ skill. Có dấu tích là bật, bỏ tích là tắt.

Khi bạn tắt một skill, Javis chuyển thư mục skill đó vào một chỗ riêng tên là `.disabled` (đường dẫn thành `skills/.disabled/<slug>`) và gỡ bản mirror trong `.claude/skills`. Đây là cách **tắt thật**: skill nằm trong `.disabled` sẽ không được engine nạp nữa, nên Javis không còn tự dùng nó. Khi bật lại, thư mục được chuyển ngược ra `skills/<slug>` và mirror lại cho Claude native.

Bật/tắt không xoá nội dung skill. Bạn có thể tắt tạm rồi bật lại bất cứ lúc nào mà không mất hướng dẫn đã viết.

Nếu có lỗi khi đổi trạng thái, Javis báo "Không đổi được trạng thái" kèm lý do.

## Thêm skill mới (từng bước)

1. Ở trang **Skills**, bấm **+ Skill**.
2. Điền các ô trong biểu mẫu:
   - **Tên skill**: tên dễ nhớ, ví dụ "Viết email bán hàng".
   - **Nhóm**: gõ tên nhóm, ví dụ "Marketing". Ô này có gợi ý sẵn các nhóm bạn đã dùng để bấm chọn cho nhất quán. Không nên để trống (sẽ vào "Chung").
   - **Mô tả (description - quyết định khi nào skill kích hoạt)**: một câu nêu thẳng skill làm được gì, **dưới 150 ký tự**, không mở đầu bằng "Kích hoạt khi..." (xem mục "Luật viết `description`" ở trên). Viết sai luật thì server từ chối và skill không được lưu.
   - **Nội dung (SKILL.md - hướng dẫn cho AI)**: viết hướng dẫn chi tiết cho AI khi skill chạy (các bước, khung mẫu, quy tắc). Đây là chỗ đặt mục `## Khi nào dùng` với đầy đủ ví dụ trigger. Nếu để trống, Javis tự tạo nội dung tối thiểu từ tên và mô tả.
3. Bấm **💾 Lưu**. Muốn bỏ thì bấm **Huỷ**.

Khi lưu, Javis tự sinh **slug** từ tên skill: chuyển thành chữ thường, bỏ dấu tiếng Việt, thay khoảng trắng bằng gạch nối (ví dụ "Viết email" thành `viet-email`). Slug ASCII không dấu giúp mọi engine nạp skill ổn định hơn. Thư mục `skills/<slug>/SKILL.md` được tạo tự động, bạn không cần tự tạo file.

## Sửa skill

1. Rê chuột vào thẻ skill, bấm **Sửa**.
2. Biểu mẫu hiện lại với nội dung hiện tại của skill (tên, nhóm, mô tả, nội dung SKILL.md).
3. Chỉnh phần cần đổi.
4. Bấm **💾 Lưu**.

Sửa skill giữ nguyên slug và thư mục cũ, chỉ ghi đè nội dung `SKILL.md`. Đây là chỗ để bạn tinh chỉnh `description` cho skill kích hoạt đúng hơn, hoặc bổ sung thêm bước vào hướng dẫn.

Sửa một skill đang **tắt** thì nó vẫn ở trạng thái tắt sau khi lưu, Javis không tự bật lên.

## Đổi nhóm skill

Cách đơn giản nhất: bấm **Sửa** skill, đổi ô **Nhóm**, rồi **💾 Lưu**. Nhóm chỉ là nhãn phân loại trong frontmatter; đổi nhóm không ảnh hưởng tới việc skill có được nạp hay không, chỉ thay đổi chỗ skill xuất hiện trong cột nhóm.

## Xoá skill

1. Rê chuột vào thẻ skill, bấm **Xoá**.
2. Javis hỏi xác nhận: `Xoá skill "<tên>"? Sẽ xoá cả thư mục skills/<slug>.`
3. Bấm đồng ý để xoá.

Xoá là thao tác dứt điểm: cả thư mục skill bị xoá khỏi ổ đĩa, không đưa vào thùng rác. Nếu chỉ muốn ngừng dùng tạm thời, hãy **tắt** thay vì xoá. Skill hệ thống không có nút Xoá.

## Xuất và nhập skill

- **⤓ Xuất** (trên từng thẻ skill): tải về một gói `.zip` chứa skill đó để gửi cho người khác. Skill **hệ thống** không có nút này vì brain nào cũng đã có sẵn.
- **⤒ Nhập** (ở đầu trang, cạnh nút + Skill): chọn file để đưa vào brain đang chọn. Nhận `.zip` (gói Javis), `.md` lẻ, hoặc gói `.skill` của Claude (Javis tự nhận diện `SKILL.md` trong gói và đưa vào đúng thư mục). Javis hỏi trước: "Nếu đã có agent/skill/workflow TRÙNG TÊN thì GHI ĐÈ bằng bản mới?" - bấm OK để ghi đè, bấm Huỷ để giữ bản cũ và chỉ nhập cái chưa có. Nhập xong Javis liệt kê đã nhập gì, bỏ qua gì.

Lưu ý: nội dung skill là hướng dẫn cho AI làm theo, nên chỉ nhập gói từ nguồn bạn tin tưởng. Chi tiết cơ chế đóng gói kèm phụ thuộc ở [Agents & Workflows](07-agents-va-workflows.md).

## Nhờ Javis tạo skill bằng lời

Bạn không bắt buộc phải điền biểu mẫu. Có thể mở cửa sổ trò chuyện và yêu cầu Javis tạo skill giúp, ví dụ: "Tạo cho tôi một skill viết caption Facebook cho shop mỹ phẩm, kích hoạt khi tôi nhờ viết caption bán hàng." Javis sẽ viết `SKILL.md` và lưu vào `skills/`. Cách trò chuyện xem thêm ở [Trò chuyện & giọng nói](02-tro-chuyen-va-giong-noi.md).

Khi tạo skill mới, Javis được hướng dẫn tự xếp vào đúng nhóm: nó đọc các skill hiện có để biết bạn đang dùng những nhóm nào, rồi chọn nhóm sát nhất. Chỉ khi không nhóm nào hợp nó mới đặt nhóm mới, với tên ngắn gọn theo lĩnh vực (Marketing, Bán hàng, Nội dung, Vận hành, Tài chính, AI, Năng suất, Cá nhân). Nhờ vậy skill mới không bị rơi lung tung vào "Chung".

## Skill và Agent

Trong trang **Agents**, khi tạo hoặc sửa một agent, bạn thấy phần **Skills** liệt kê các skill có sẵn để tích chọn gán cho agent đó. Agent chỉ liệt kê được skill khi brain đã có skill trong `skills/`; nếu chưa có, phần này hiện ghi chú "Vault chưa có skill trong skills/ - vẫn tạo agent được, gán skill sau". Chi tiết ở [Agents & Workflows](07-agents-va-workflows.md).

## Bảng tra nhanh nút và trạng thái

| Bạn thấy | Ý nghĩa / thao tác |
|---|---|
| **⤒ Nhập** | Đưa gói `.zip` / `.md` / `.skill` vào brain đang chọn |
| **+ Skill** | Mở biểu mẫu tạo skill mới |
| Ô đánh dấu đầu thẻ | Có tích = bật; bỏ tích = tắt (chuyển vào/ra `.disabled`) |
| **Sửa** | Mở biểu mẫu chỉnh sửa skill |
| **⤓ Xuất** | Tải skill về dạng gói `.zip` để chia sẻ (không có ở skill hệ thống) |
| **Xoá** | Xoá hẳn thư mục skill (có hỏi xác nhận; không có ở skill hệ thống) |
| **💾 Lưu** | Lưu skill (tạo mới hoặc ghi đè) |
| **Huỷ** | Đóng biểu mẫu, không lưu |
| Ô **Tìm skill…** | Lọc theo tên, mô tả, slug |
| Cột **Nhóm** / **Tất cả** | Lọc danh sách theo nhóm |
| Huy hiệu **hệ thống** | Skill đi theo app, có ở mọi brain, chỉ tắt được chứ không xoá |
| Thẻ hiển thị mờ | Skill đang tắt |
| Dòng "x/y bật" | x skill đang bật trên tổng y |
| "đã dùng N lần, gần nhất …" | Skill đã được nạp qua tool `javis_use_skill` N lần |
| "chưa thấy dùng" | Quá 30 ngày không có tín hiệu dùng; chỉ là tham khảo, không phải phán quyết |

## Mẹo

- Viết `description` như một dòng tựa: nêu thẳng năng lực, dưới 150 ký tự. Đẩy toàn bộ ví dụ trigger và từ khoá xuống mục `## Khi nào dùng` trong thân file - vừa không bị chặn, vừa không bị cắt.
- Đếm ký tự trước khi lưu. 150 ký tự ngắn hơn bạn tưởng, khoảng hai câu ngắn.
- Một skill nên làm một việc rõ ràng. Việc quá rộng thì trigger dễ nhầm; chia nhỏ thành nhiều skill và đặt cùng một nhóm sẽ dễ quản lý hơn.
- Giữ số skill đang bật dưới 20 để tất cả đều nằm trong router. Skill nào chưa cần thì tắt.
- Dùng nhóm nhất quán. Khi gõ ô **Nhóm**, ưu tiên chọn từ gợi ý sẵn thay vì tự chế tên mới, để cột nhóm không bị phân mảnh.
- Muốn thử nghiệm một skill mà chưa chắc chắn, cứ tạo rồi **tắt** khi không dùng, thay vì xoá đi tạo lại.
- Muốn chắc chắn một skill được dùng cho đúng việc, gọi tay bằng `/slug` thay vì trông chờ trigger tự bắt.

## Sự cố thường gặp

- **Bấm 💾 Lưu mà skill không xuất hiện trong danh sách:** gần như chắc chắn là `description` vi phạm luật (dài quá 150 ký tự, hoặc mở đầu bằng "Kích hoạt khi..."). Server từ chối lưu và trang chỉ quay về danh sách chứ không hiện lời báo lỗi. Bấm **+ Skill** lại, rút gọn mô tả xuống dưới 150 ký tự và bỏ cụm mở đầu sáo rỗng, rồi lưu lại.
- **Tạo skill nhưng Javis không tự dùng:** kiểm tra ba thứ theo thứ tự. Một, skill có đang **bật** không (thẻ không bị mờ, ô đánh dấu có tích). Hai, `description` có nêu đúng năng lực không. Ba, brain có đang bật quá 20 skill không - nếu có, skill của bạn có thể đã rơi ra ngoài router; tắt bớt skill khác hoặc gọi tay bằng `/slug`.
- **Danh sách trống dù đã tạo skill:** đảm bảo đang xem đúng brain. Nguồn skill là `skills/` của brain đang chọn; đổi brain thì danh sách đổi theo.
- **Bấm bật/tắt báo lỗi "Không đổi được trạng thái":** thường do quyền ghi thư mục hoặc thư mục đang bị khoá. Xem thêm [Khắc phục sự cố & FAQ](17-khac-phuc-su-co.md).
- **Skill ghi "chưa thấy dùng" dù bạn biết nó có chạy:** bình thường. Javis chỉ đếm được lần nạp qua tool `javis_use_skill`; Claude Code nạp native thì không qua bộ đếm. Đừng xoá skill chỉ vì nhãn này.
- **Thẻ skill không hiện nút Xoá:** đó là skill hệ thống. Muốn ngừng dùng thì tắt.
- **Lỡ tay Xoá:** xoá là dứt điểm, không khôi phục được từ dashboard. Lần sau nếu chỉ muốn ngừng dùng tạm, hãy tắt.
- **Nhóm bị rơi vào "Chung":** do để trống ô Nhóm khi lưu. Bấm **Sửa** và điền tên nhóm.

## Liên quan

- [Agents & Workflows](07-agents-va-workflows.md) - gán skill cho agent, dựng chuỗi công việc, xuất/nhập gói kèm phụ thuộc.
- [Plugins](20-plugins.md) - khi bạn cần một tool chạy code thật chứ không phải một bản hướng dẫn.
- [Models & engine](10-models-va-engine.md) - skill chạy trên mọi engine; xem khác biệt native (Claude Code) vs router (`javis_use_skill`).
- [Trò chuyện & giọng nói](02-tro-chuyen-va-giong-noi.md) - nhờ Javis tạo skill bằng lời, và menu lệnh "/" trong khung chat.
- [Tự học](22-tu-hoc.md) - nơi Javis đề xuất skill mới từ hội thoại đã qua.
- [Second Brain: bộ nhớ, Wiki, INGEST](13-second-brain-bo-nho-wiki.md) - hiểu khái niệm brain nơi skill được lưu.
