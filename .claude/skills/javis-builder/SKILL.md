---
name: Javis Builder
description: "Tạo hoặc sửa năng lực của Javis: agent, skill, workflow, loop, plugin. Kèm mẫu file chuẩn và luật chống trùng."
description_en: "Create or edit a Javis capability: agent, skill, workflow, loop, plugin. Ships file templates and the rules against duplicates."
group: AI
---

# Javis Builder - tạo agent / skill / workflow / loop

## Khi nào dùng

Kích hoạt khi người dùng nói những câu như: "tạo agent chuyên X", "thêm kỹ năng Y",
"dựng workflow nghiên cứu rồi viết", "tạo loop mỗi 2 tiếng làm Z", "viết tool/plugin
tính ...", "làm cho Javis biết làm ...".

Khi người dùng muốn Javis có thêm một năng lực, bạn TỰ GHI FILE .md đúng chuẩn dưới đây vào
vault (brain đang chọn). Studio / trang tương ứng tự nhận file mới. Luôn báo cáo ngắn sau khi tạo.

## Quy trình (làm đúng thứ tự)

1. **Hiểu nhu cầu.** Nếu mô tả đủ rõ thì làm luôn; thiếu điểm cốt lõi (mục tiêu, đầu ra mong
   muốn) thì hỏi 1 câu ngắn rồi làm. Đừng hỏi lan man.
2. **Chọn đúng LOẠI năng lực:**
   - Việc trả lời/kiến thức cách-làm tái dùng nhiều lần -> **skill**.
   - Một "vai" chuyên môn có system prompt riêng -> **agent**.
   - Chuỗi nhiều bước, nhiều vai nối nhau -> **workflow** (tạo trước các agent còn thiếu).
   - Việc LẶP theo chu kỳ, tự chạy nền -> **loop**.
   - Cần một TOOL native mới (làm được bằng Python, tái dùng, mọi engine gọi được) mà chưa có MCP -> **plugin**. Chỉ là hướng dẫn cách làm bằng tool sẵn -> skill. Nguồn dữ liệu ngoài có sẵn MCP -> đấu MCP.
   - Việc làm 1 lần -> KHÔNG tạo gì, cứ làm luôn hoặc đề xuất task Kanban.
3. **Chống trùng.** TRƯỚC khi tạo, đọc folder tương ứng (agents/ workflows/ skills/
   loops/). Nếu đã có cái gần giống -> cập nhật cái cũ, đừng đẻ bản sao.
4. **Ghi file** đúng frontmatter (mẫu bên dưới). slug = ASCII không dấu, gạch nối. Tên hiển thị
   tiếng Việt. TUYỆT ĐỐI không dùng ký tự em dash, dùng "-".
   **Phân loại là BẮT BUỘC.** Agent dùng `tags` (danh sách, gắn được nhiều tag); skill và workflow
   dùng `group` (một nhóm). Trước khi chọn, đọc tag đang dùng trong `agents/*.md` và nhóm đang dùng
   trong `workflows/*.md`, `skills/*/SKILL.md` rồi lấy cái sát nhất; không cái nào hợp thì đặt tên
   mới ngắn theo lĩnh vực. Agent bỏ trống `tags` thì nằm ở "Chưa gắn tag", skill/workflow bỏ trống
   `group` thì rơi vào "Chung". Tag chỉ để phân loại và tìm agent: không thêm agent vào nhóm chat,
   không chọn reviewer, không cấp quyền.
5. **Báo cáo ngắn** bằng văn nói: đã tạo loại gì, tên/đường dẫn file, dùng ở đâu.

## Mẫu file (ghi CHÍNH XÁC theo đây)

### Agent -> `<brain>/agents/<slug>.md` (PHẲNG ở gốc brain - KHÔNG phải Javis/agents, ghi vào đó là app không thấy)
```
---
type: agent
name: <Tên tiếng Việt>
slug: <ascii>
role: <vai trò 1 câu>
tags: [Marketing, Viết nội dung]   # một hay nhiều tag; ví dụ Marketing, Bán hàng, Nội dung, Vận hành, Tài chính, AI, Năng suất, Cá nhân
skills: [slug-skill]      # [] nếu chưa gán; chỉ gán skill đã có trong skills/
model: ""                 # "" = dùng model chính | tên model, vd sonnet, gpt-5.5, claude-sonnet-5-5, gemini-2.5-pro
model_provider: ""        # "" = suy theo tên model | anthropic-cli, openai-oauth, anthropic-api, openai, openrouter, gemini...
updated: <YYYY-MM-DD>
---
<system prompt: cách làm việc, nguyên tắc, định dạng đầu ra mong muốn>
```
Gán hay đổi model cho trợ lý: ưu tiên tool `javis_team` op=set_agent_model (slug, model, model_provider). Tool tự kiểm
model_provider hợp lệ và chạy trên MỌI engine, kể cả engine API. Cùng một tên model có ở hai nhà (claude-* có ở Claude Code
lẫn Anthropic API) thì PHẢI ghi model_provider.

**Viết system prompt cho agent theo khung metaprompt** (rút từ metaprompt của Anthropic - ĐỪNG viết 1-2 câu chung chung kiểu "bạn là chuyên gia X"):
1. Vai + mục tiêu: 1 câu nêu vai, 1 câu nêu kết quả tốt trông như thế nào.
2. Bối cảnh nghiệp vụ: 2-3 dòng về sản phẩm/khách/lĩnh vực, lấy từ Memory nếu liên quan.
3. Quy trình: các bước làm việc đánh số, đúng thứ tự agent nên làm thật.
4. Định dạng đầu ra: nêu CỤ THỂ (độ dài, cấu trúc, giọng, ngôn ngữ); đầu ra có khuôn cố định thì kèm 1 ví dụ mẫu ngắn.
5. Trường hợp khó: thiếu dữ liệu / yêu cầu mơ hồ / ngoài phạm vi thì agent làm gì (nêu giả định rồi làm tiếp, hỏi lại 1 câu, hay từ chối).
6. Điều cấm: chỉ cấm CỤ THỂ kèm lý do (vd không bịa số liệu, không em dash), đừng viết cả tràng "không được".
Prompt tốt thường 10-25 dòng. Viết xong tự đọc lại bằng mắt một agent mới: có đủ để làm việc mà không phải hỏi thêm không? Thân skill cũng áp khung này (bỏ mục 1, thay bằng mô tả trigger).

### Skill -> `skills/<slug>/SKILL.md`
```
---
name: <Tên skill>
description: <nêu THẲNG năng lực, TỐI ĐA 150 ký tự - vd "Tóm tắt biên bản họp thành danh sách việc cần làm.">
group: <Marketing|Bán hàng|Nội dung|Vận hành|Tài chính|AI|Năng suất|Cá nhân>
---
<hướng dẫn chi tiết cho AI khi skill kích hoạt>
```

#### Chuẩn viết skill (bắt buộc - KHÔNG có ai gác, tự bạn phải giữ)

**Không có lưới an toàn.** Skill viết theo tài liệu này là GHI THẲNG RA ĐĨA: không qua
`POST /skills` nên không có kiểm tra phía server, và lint CI chỉ soi skill HỆ THỐNG, không
soi skill trong `skills/` của brain. Vi phạm chuẩn dưới đây sẽ KHÔNG có thông báo lỗi nào -
skill cứ thế hỏng âm thầm lúc chạy. Bạn là lớp phòng thủ duy nhất.

1. `description` **TỐI ĐA 150 ký tự**. **Viết xong hãy ĐẾM, đừng ước lượng** - đây là việc
   bắt buộc, không phải lời khuyên. Router cắt đúng ở đó (`skill_router.SKILL_DESC_MAX`) ở
   cả system prompt lẫn mô tả tool, nên viết dài hơn là phần đuôi MẤT IM LẶNG và skill không
   route được. Không ai cảnh báo bạn: không đếm là hỏng mà không biết.
2. `description` nêu THẲNG năng lực. KHÔNG mở đầu bằng "Kích hoạt khi...", "Sử dụng skill
   này khi..." - mọi skill đều mở như vậy nên nó đốt 29 ký tự mà không phân biệt gì.
   Tốt: `Tóm tắt biên bản họp thành danh sách việc cần làm.`
   Xấu: `Kích hoạt khi người dùng muốn tóm tắt biên bản...`
3. `description` có dấu hai chấm thì phải bọc cả giá trị trong nháy kép, kẻo YAML hiểu
   nhầm thành mapping.
4. Ví dụ trigger đầy đủ đưa vào THÂN file, mục `## Khi nào dùng` - nơi không bị cắt và chỉ
   đọc khi skill đã nạp. Index để TÌM, thân file để LÀM.
5. Thứ tự mục trong thân: `## Khi nào dùng` / `## Chuẩn bị` / `## Cách chạy` /
   `## Quy trình` / `## Bẫy` / `## Kiểm chứng`. Mục nào không có nội dung thật thì bỏ,
   đừng bịa cho đủ.
6. KHÔNG bịa flag, đường dẫn, API chưa thấy trong nguồn. Không thấy thì đừng viết.
7. Thân file khoảng 100 dòng cho skill đơn giản, 200 cho skill phức tạp. Dài hơn thì tách
   nội dung xuống `skills/<slug>/references/<chủ-đề>.md`, script xuống
   `skills/<slug>/scripts/`, và trỏ tới bằng đường dẫn tương đối. Từ bản 0.9.64: bản mirror
   sang `.claude/skills` (đường Claude Code nạp NATIVE) copy ĐỆ QUY cả cây, nên với skill
   trong brain, `references/`/`scripts/` tới được CẢ đường router lẫn đường native. Từ bản
   0.33.0, skill HỆ THỐNG (bundled theo app, cài vào brain qua system sync) cũng ship CẢ cây
   con - trước đó nó chỉ chuyển mỗi `SKILL.md` nên skill hệ thống nào cần `tools/` là hỏng ở
   mọi brain. Giờ viết skill hệ thống có cây con là hợp lệ.
8. KHÔNG viết skill kiểu router chỉ trỏ sang skill khác.

### Workflow -> `<brain>/workflows/<slug>.md` (PHẲNG ở gốc brain - KHÔNG phải Javis/workflows)
```
---
type: workflow
name: <Tên>
slug: <ascii>
status: 'off'             # tạo mới để 'off' cho user xem trước rồi bật; GIỮ dấu nháy (off trần = boolean). Quy trình tắt không chạy nền
group: <Marketing|Bán hàng|Nội dung|Vận hành|Tài chính|AI|Năng suất|Cá nhân>
description: <mô tả ngắn>
steps:
  - agent: <agent-slug>
    task: "<việc; {{input}}=đầu vào user, {{prev}}=kết quả bước trước>"
    verify_agent: <agent-slug>   # tùy chọn: agent soi lỗi, PHẢI trả JSON {"pass":true|false,...}; vẫn trượt sau max_retries thì quy trình DỪNG
    max_retries: 1               # tùy chọn
    tools: [javis_generate_image] # tùy chọn: tool plugin riêng bước này cần khi chạy nền dưới Toàn quyền (vd tạo/xem ảnh); WebFetch, WebSearch cũng nhận
updated: <YYYY-MM-DD>
---
<mô tả>
```
Nếu workflow tham chiếu agent chưa tồn tại -> TẠO agent đó trước.

### Nhóm chat -> tool `javis_team` (KHÔNG ghi file tay, KHÔNG điều khiển trình duyệt)
Người dùng muốn một nhóm chat gồm vài trợ lý: gọi `javis_team` op=create một lần, `members` là slug trợ lý có sẵn, `new_agents`
là trợ lý cần tạo mới (`name`, `role`, `prompt`, `model`, `model_provider` nếu muốn model riêng), `leader` là slug hay tên trưởng
nhóm. Sửa: op=update, add_member, remove_member, set_leader, set_agent_model. Xoá: op=archive trước, op=delete kèm confirm=true chỉ
khi người dùng nói rõ là xoá. Xem trước trợ lý đang có bằng op=list_agents để khỏi tạo trùng.

### Loop -> `Javis/loops/<slug>.md`

**Việc LẶP MỚI: ưu tiên GỌI TOOL `javis_schedule`** (op=create, name/prompt/schedule - vd
schedule="120m" hoặc "mỗi 2 tiếng") thay vì tự ghi file. Tool tự đặt đúng slug, đúng frontmatter
(kể cả `goal: custom` bên dưới - thiếu field này là lỗi thật đã xảy ra: self_improve.py mặc định
`goal: business`, loop chỉ đọc số liệu MCP và BỎ QUA HOÀN TOÀN nhiệm vụ ở thân file), và chặn
trùng tên. **CHỈ tự ghi file tay** (mẫu dưới) khi: (a) SỬA loop ĐÃ CÓ, hoặc (b) cần trường nâng
cao mà tool chưa nhận - `quiet_hours` (giờ im lặng, vd "23-07"), `max_runs_per_day`, `workspace`
(+ `tools_profile: code` khi loop sửa mã trên thư mục ngoài - có Bash/Web, KHÔNG MCP),
`ambient_mcp` (cho loop THẤY connector claude.ai của máy - Gmail/Drive/lịch; MẶC ĐỊNH tắt để bản
fork sạch, chỉ bật khi user yêu cầu rõ; vẫn chặn cứng Bash/Web), `notify: false` (loop quá ồn thì
ngừng báo mỗi vòng), hoặc `goal` khác `custom` (`business`/`brain`/`product`).
```
---
type: loop
name: <Tên>
slug: <ascii>
enabled: false            # LUÔN tạo ở trạng thái TẮT - user bấm Bật ở trang Việc
mode: full                # full=toàn quyền (MẶC ĐỊNH) | auto=chỉ ghi nháp | suggest=chỉ đọc/đề xuất
goal: custom              # BẮT BUỘC khi ghi tay - thiếu dòng này self_improve.py mặc định
                           # 'business' (chỉ đọc số liệu MCP, bỏ qua hoàn toàn thân file dưới đây)
interval_min: 120         # tối thiểu 5
owner_chat: "<chat_id>"   # chat_id NGƯỜI YÊU CẦU (tạo qua chat Telegram) - để báo đúng người;
                           # bỏ trống nếu tạo trên web (báo về ID Telegram đầu tiên)
updated: <YYYY-MM-DD>
---
<mô tả nhiệm vụ: mỗi vòng loop làm ĐÚNG việc này - đây chính là prompt của loop, viết tự-đủ>
```

### Plugin -> tool `javis_plugin` op=write (KHÔNG ghi file tay, KHÔNG đưa file zip cho người dùng)
Cài thẳng vào app, mọi engine đều gọi được: `javis_plugin` op=write, slug, `files` = {đường dẫn tương đối: nội dung}
(lần tạo cần ít nhất plugin.yaml + plugin.py), `scope` = "global" (mặc định, chung mọi brain, nằm ở
`<JAVIS_STATE_DIR>/plugins/<slug>/`) hoặc "brain" (riêng brain này, `<vault>/plugins/<slug>/`).
- Trước khi tạo: op=list xem đã có plugin nào trùng việc chưa; có thì op=read rồi sửa plugin đó.
- Sửa: op=read lấy file hiện tại, op=write chỉ gửi file đổi; `remove` = danh sách file cần xoá.
- Tool tự từ chối lỗi cú pháp Python, đường dẫn lạ, đuôi file lạ, slug trùng plugin hệ thống: đọc câu ERROR, sửa, gửi lại.
- Plugin mới, hoặc bản sửa đổi mã (.py) hay đổi tools/hooks/min_mode, luôn nằm TẮT. Javis KHÔNG bật được;
  nói rõ với người dùng: đọc mã rồi bật ở trang Plugins. Sửa chỉ phần mô tả thì giữ nguyên trạng thái.
- op=delete chỉ gỡ plugin do chính tool này tạo và đang tắt; còn lại để người dùng gỡ ở trang Plugins.

Nội dung hai file chính:
`plugin.yaml`:
```
name: <Tên tiếng Việt>
slug: <ascii>
version: 1.0.0
description: <tool này làm gì, khi nào engine nên gọi>
author: <ai tạo>
enabled: false            # LUÔN tắt (tool tự ép, ghi true cũng thành false)
min_mode: readonly        # BẮT BUỘC: readonly=chỉ đọc/tính | safe=có ghi | full=hành động thật
tools: [<ten_tool>]
hooks: []                 # vd [post_tool_call] nếu dùng hook
```
`plugin.py`:
```python
def register(ctx):
    def handler(args, ctx):            # args=dict; trả str (hoặc dict). Lỗi -> "ERROR: ...". Có thể async.
        return "..."
    ctx.register_tool(
        name="ten_tool", description="mô tả cho engine + tham số",
        handler=handler, min_mode="readonly",
        schema={"type":"object","properties":{},"required":[]})
    # tuỳ chọn hook: ctx.register_hook("post_tool_call", lambda tool_name="", **_: None)
```
ctx có `ctx.vault_root`, `ctx.data_dir` (state riêng plugin, không đụng vault), `ctx.slug`.

## Rào an toàn (BẮT BUỘC)

- Loop tạo qua chat LUÔN `enabled: false` (user bấm Bật ở trang Việc) và mặc định `mode: full`:
  chủ dự án đã bỏ luật "không giao tự động tiền/đơn/đăng bài/nhắn khách" (2026-09-10), nên
  loop tự thao tác ra ngoài và KHÔNG cần cảnh báo rủi ro. Chỉ hạ `mode: auto/suggest` khi user
  muốn loop đó nhẹ hơn.
- KHÔNG bao giờ để một loop/automation tự tạo hoặc tự bật loop khác (chống phình vô hạn) - chỉ ĐỀ XUẤT.
- Skill do engine TỰ HỌC sinh ra -> tạo BẬT sẵn (đánh dấu `origin: javis-learned`), nhưng KHÔNG ghi
  đè skill đã có và KHÔNG hồi sinh skill user đã tắt; agent tự động -> để nháp chờ duyệt. Skill do
  user yêu cầu trực tiếp -> tạo bật luôn nhưng phải kiểm trùng + `description` nêu rõ năng lực,
  phân biệt được với skill khác (mô tả mơ hồ làm Javis chọn skill sai). Đừng tạo skill trùng
  chức năng skill đã có.
- Plugin user (toàn cục lẫn vault) chạy CODE PYTHON THẬT trong tiến trình server -> tạo qua `javis_plugin`
  (tool tự để `enabled: false`), `min_mode` đúng việc tool làm, và NÓI RÕ với user: plugin nằm tắt cho tới khi họ bật nó trong app. Từ 15/10/2026
  Javis cho tải plugin người dùng mặc định; máy nào muốn chặn hẳn thì đặt env `JAVIS_ENABLE_USER_PLUGINS=false`
  rồi khởi động lại. Plugin làm hành động ra ngoài thì khai `min_mode: full` cho đúng, hub xét theo mức quyền của chỗ gọi.
- Sau khi tạo, KHÔNG tự chạy thứ có side-effect; để user xem trước.
