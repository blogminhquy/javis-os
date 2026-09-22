# Kế hoạch: Nhân prompt có trần đóng băng và tầng luật theo carrier

> Bản kế hoạch dev, viết 2026-09-22 trên nền code v0.62.6. Mục tiêu: chấm dứt tình trạng
> `CLAUDE.md` phình tới trần rồi phải nâng trần, bằng cách đổi **nơi luật được viết ra** chứ
> không phải đổi cách nén luật. Kèm ba lỗi thật phát hiện khi khảo sát, và một đợt rút prose
> về carrier đúng của nó.

## Bối cảnh

Đo lúc viết bản này:

```
CLAUDE.md          33.577 ký tự
Trần CI            33.600 ký tự   (tests/python/test_prompt_budget.py)
Còn lại                23 ký tự
```

Comment ngay trên cái trần đó đã viết sẵn cho lần này:

> "Lần chạm trần TIẾP THEO thì cắt thật hoặc đẩy một mục sang skill, đừng nâng số này nữa."

Trần đã được nâng ít nhất một lần rồi (`33.600 (0.50.0): nâng trần thay vì cắt`). Nên câu
hỏi thật không phải "nâng lên bao nhiêu" mà là **vì sao nó luôn đầy**.

Chạy `python tests/run.py prompt_budget -v` lúc viết bản này, ba dòng đầu của chính test đó:

```
ok  CLAUDE.md dưới trần 33,600 ký tự   [hiện 33,577 ký tự, còn 23 ký tự]
ok  CORE_CONTRACT dưới trần 2,000      [hiện 740 ký tự]
ok  đường biên dịch nhỏ hơn legacy ít nhất 10 lần
    [CORE_CONTRACT bằng 2.2% CLAUDE.md, tiết kiệm 98%]
```

Dòng thứ ba đáng chú ý: đường biên dịch **đã chứng minh** một prompt lõi 740 ký tự chạy được.
Nhưng nó chỉ áp cho engine API, còn engine gói thuê bao vẫn nhận trọn 33.577. Kế hoạch này
không đi theo hướng CORE_CONTRACT (bỏ hẳn `CLAUDE.md` là bỏ luôn tính cách Javis), nhưng con
số đó là bằng chứng rằng phần lớn 33.577 ký tự kia **không phải thứ bắt buộc phải có mặt**.

### File này đi vào đâu

`server/main.py:351-352` đọc `CLAUDE.md` ở gốc repo làm `SYSTEM_PROMPT`, và
`build_system_prompt()` (`main.py:755`) đặt nó làm nền cho mọi lượt chat của mọi engine.
Với engine gói thuê bao, `_subscription_system_prompt` (`main.py:12110`) **cố ý** giữ nguyên
`CLAUDE.md` thay vì dùng `build_adaptive_source_prompt`, lý do ghi ở `main.py:12117`:

> "bỏ CLAUDE.md đổi lấy token là món hời khi bị siết TPM và mỗi token đều tính tiền. Với gói
> thuê bao thì không tính tiền theo token"

Lập luận đó đúng về **tiền** và sai về **thời gian**. Gói thuê bao không tính tiền theo token,
nhưng 33.577 ký tự vẫn tốn y nguyên thời gian xử lý mỗi lượt. Với Antigravity nó còn đắt hơn
một bậc: chính khối này đẩy prompt vượt trần dòng lệnh (`antigravity_cli._tran_argv`, Windows
30.000 đơn vị UTF-16), buộc đi đường file ngữ cảnh, tức thêm nguyên một vòng inference để model
tự mở file ra đọc.

---

## Chẩn đoán: vì sao file phình

Gần như mọi luật trong `CLAUDE.md` đều mang một ngày sự cố: "chủ repo báo 2026-08-13", "sự cố
13/09/2026", "incidents on 2026-07-19 and 2026-08-16", "khách báo 2026-08-30". File này là một
**kho mô sẹo**, tăng đều một luật mỗi sự cố, không bao giờ giảm.

Câu hỏi đúng: vì sao mọi luật đều chảy vào đúng một file?

| Nơi viết luật | Thời gian | Ai làm được |
|---|---|---|
| Thêm đoạn vào `CLAUDE.md` | ~5 phút | Bất kỳ ai, kể cả qua chat |
| Viết validation trong code | ~2 giờ | Cần lập trình |
| Viết một tool mới | ~1 ngày | Cần lập trình |

`CLAUDE.md` không phải một lựa chọn thiết kế. Nó là **con đường ít cản trở nhất**. Dưới áp lực
thời gian, mọi luật lăn xuống chỗ trũng.

Hệ quả cần nói thẳng vì nó phủ định hai phương án hiển nhiên:

> **Bất kỳ kế hoạch nào dọn chỗ trống mà để nguyên độ dốc thì chỗ trống sẽ đầy lại.**

Nâng trần: mua thêm vài tháng. Nén bằng truy xuất: mua thêm một hai năm, đổi lấy một hệ thống
mới phải nuôi. Cả hai đều không chạm tới độ dốc.

### Vì sao truy xuất KHÔNG cho mở rộng không giới hạn

Cần ghi rõ để bản sau khỏi đi lại đường này.

Lập luận "chi phí mỗi lượt là O(top-k) nên tổng số luật tăng bao nhiêu cũng được" sai ở chỗ
**k không phải hằng số**. Số luật liên quan tới MỘT hành động tăng theo độ phức tạp hệ thống:
hôm nay tạo một agent cần biết 6 luật; khi có 20 engine, 50 connector, 5 kênh thì cần biết 6
luật cộng các luật tương tác (engine này ghi file khác engine kia, kênh này không hiện
markdown, connector kia cần quyền khác). Số cặp tương tác tăng theo bình phương bề mặt.

Truy xuất cho một **hằng số nhân tốt hơn**, không cho **sự không giới hạn**. Muốn không giới
hạn thì phải có cơ chế làm luật **biến mất**, không phải làm luật rẻ hơn khi mang theo.

---

## Bằng chứng quyết định nằm trong chính repo

Repo đã tự chạy thí nghiệm này. Hai năng lực, cùng độ phức tạp, khác nhau đúng một điều:

| Năng lực | Có tool riêng | Prose trong `CLAUDE.md` |
|---|---|---:|
| Đặt lịch, nhắc hẹn, loop | **Có** (`javis_schedule`) | **~600 ký tự** |
| Tạo agent, workflow | Không | **2.875** |
| Tạo plugin | Không | **2.114** |
| Ghi bộ nhớ dài hạn | Không | **2.297** |

Đặt lịch phức tạp hơn tạo agent: có cron, có ba mức quyền, có hai kho lưu, có điều kiện tiền
đề. Nhưng nó chỉ tốn ~600 ký tự prose, vì luật của nó nằm trong hợp đồng tool
(`system/plugins/javis-schedule/plugin.py:583`, mô tả ~1.900 ký tự).

Và quan trọng hơn: tool đó **nằm trong lazy pool**. `mcp_hub.py:837` lấy pool là mọi tool trừ
`CORE_TOOL_FNS` (`mcp_hub.py:598`, chỉ có `javis_read_file`, `javis_list_dir`,
`javis_write_file`). Nên 1.900 ký tự ấy chỉ vào ngữ cảnh khi model thật sự cần đặt lịch. Lượt
hỏi doanh thu trả 0 ký tự cho nó.

> **Cơ chế "luật đi kèm năng lực, nạp lười theo nhu cầu" đã tồn tại, đã chạy production, đã
> đo được (schema tool 11.994 ký tự xuống 2.001, giảm 83%). `CLAUDE.md` là thứ duy nhất đứng
> ngoài nó.**

Vậy nên kế hoạch này **không xây tầng truy xuất policy mới**. Nó đưa `CLAUDE.md` vào cơ chế
đang chạy.

### Lỗ hổng quy trình

`javis_schedule` đã có từ lâu, nhưng mục Orchestration trong `CLAUDE.md` vẫn còn nguyên 8.888
ký tự mô tả lại chính những luật đó. **Thêm tool không tự động rút prose.** Không có trường
nào, test nào, quy trình nào nói "luật này nay do code ép, xoá khỏi prompt".

Đó chính là độ dốc, và nó là thứ phải sửa trước tiên.

---

## Bốn thứ hỏng phát hiện khi khảo sát

Đã tự kiểm chứng trên code, không phải suy đoán. Ba cái đầu là tiền đề của kế hoạch.

**1. Hook `pre_tool_call` không chặn được gì.**

`plugins_host.py:755` bọc mọi tool call:

```python
async def _wrapped(args):
    await _fire("pre_tool_call", vault_root, {...})   # bỏ qua giá trị trả về
    result = await base_call(args)                     # gọi bất kể hook nói gì
```

Và `_fire` (`:746`) nuốt cả exception (`except Exception as e: print(...)`). Nên hook hiện
**chỉ quan sát được, không phủ quyết được, không sửa tham số được**. Docstring ở `:369` hứa
"bắn quanh MỌI tool call" nên dễ tưởng nó là chốt chặn; nó không phải.

Đây là chốt chặn rẻ nhất cho cả nhóm luật "đừng ghi sai chỗ", nên phải vá trước.

**2. Skill thứ 21 trở đi vô hình với router.**

`skill_router.py:49` đặt `SKILL_LIST_MAX = 20`. `_skill_router_block` (`main.py`) cắt ở đó rồi
ghi `…(+N skill nữa - xem Javis/index.md)`. Model không đọc file đó trừ khi được bảo, nên
skill thứ 21 trở đi **không bao giờ được route**. Một brain dùng lâu chắc chắn vượt 20.

**3. `_fit_memory_index` có bậc cuối là mất trí nhớ.**

`main.py:523` đặt `MEMORY_INDEX_MAX = 20000`. Khi vượt, `_fit_memory_index` hạ bậc: giữ nguyên
→ rút mô tả còn 100 ký tự → còn 60 → chỉ tiêu đề → **cắt bớt dòng**. Chính docstring gọi bậc
cuối là mất trí nhớ. Nguyên nhân: nó cố nhét cả CHI TIẾT vào một chỗ có trần.

**4. `build_system_prompt` chạy lại toàn bộ mỗi lượt, không cache.**

Mỗi lượt chat đọc lại `CLAUDE.md`, đọc `MEMORY.md`, gọi `system_sync.ensure_synced`,
`system_sync.mirror_skills`, quét cây skill, dựng 6 khối. Mốc nghiệm thu trong
`bench_hotpath.py` là dưới 40ms, tức 40ms chặn mỗi lượt cho một kết quả gần như không đổi
giữa các lượt. Và vì nó dựng lại chuỗi mỗi lần, không có bảo đảm nào rằng tiền tố gửi đi là
byte-identical, trong khi `engine.py:330` đang đánh `cache_control: ephemeral` lên khối system
và phụ thuộc vào đúng điều đó.

---

## Ba hằng số kiến trúc

Đây là phần phải đứng yên nhiều năm. Mọi thứ khác thay được mà không đụng tới chúng. Cả ba
đều là **quy trình và cấu trúc**, không phụ thuộc thư viện, model hay thuật toán nào, nên
chúng sống lâu được.

### Hằng số 1: Đường phân đôi tính cách và bề mặt

> **Nhân prompt chỉ chứa thứ tỉ lệ với TÍNH CÁCH của Javis. Mọi thứ tỉ lệ với BỀ MẶT của
> Javis nằm cùng carrier của nó.**

| | Tính cách | Bề mặt |
|---|---|---|
| Nội dung | Javis là ai, xưng hô, cách trình bày, thang quyết định, khi nào hỏi lại | Engine, connector, định dạng file, quy trình vận hành, sự cố |
| Tốc độ tăng | Gần như đứng yên | Tăng siêu tuyến tính |
| Bằng chứng | Thang quyết định không đổi từ đầu repo | Gemini CLI bị gỡ, Antigravity thêm, Grok thêm |
| Nơi ở | `kernel.md` (trần đóng băng) | Tool contract, skill body, code, connector metadata |

Chia theo đường này thì nhân **không lớn lên**, vì thứ làm nó lớn lên đã bị định tuyến đi chỗ
khác ngay lúc sinh ra.

### Hằng số 2: Trần nhân đóng băng, không vay được

```
system/prompt/kernel.md     trần 8.000 ký tự, VĨNH VIỄN
```

Thêm vào nhân bắt buộc phải xoá thứ khác ra. Không có "nâng trần lên 40.000".

Vì sao đây là hằng số quan trọng nhất: một cái trần nâng được không phải trần, nó là một lời
gợi ý, và trần hiện tại đã bị nâng. Trần có răng là thứ duy nhất tạo áp lực buộc phải định
tuyến luật. 8.000 ký tự cũng là mức một người **đọc soát hết trong một lần ngồi**; 33.577 thì
không ai soát nổi, nên không ai biết trong đó còn luật nào đã lỗi thời.

### Hằng số 3: Mỗi luật khai người thi hành

```yaml
id: agent-ghi-dung-thu-muc
enforced_by: javis_create_agent     # code ép → XOÁ khỏi prose
# enforced_by: ""                   # trống → ứng viên để biến thành code
added: 2026-07-19
because: "Agent ghi vào Javis/agents/ nên biến mất khỏi app"
review: 2026-12-19
```

Trường `enforced_by` biến việc rút prose từ tuỳ hứng thành tự động: có người thi hành bằng
code thì prose bị xoá, không cần ai nhớ. Đây đúng là lỗ đã để mục Orchestration sống sót
nguyên vẹn dù `javis_schedule` đã có từ lâu.

---

## Kiến trúc: bốn carrier, xếp theo giá thật

| Carrier | Chi phí mỗi lượt | Độ tin cậy | Rơi khỏi ngữ cảnh giữa chừng? |
|---|---|---|---|
| **Code / validation / hook** | **0 vĩnh viễn** | **100%** | Không thể |
| **Hợp đồng tool** (schema + description) | 0 khi ngoài phạm vi (lazy đã có) | ~95% | Không, phạm vi tool ổn định cả phiên |
| **Thân skill / policy** | 0 khi chưa nạp | ~90% | **Có** |
| **Prose trong nhân** | **Luôn trả** | ~80% | Không |

Hai carrier tốt nhất đều là code, và cả hai **miễn nhiễm với chuyện mất ngữ cảnh giữa lượt**.
Đây là lý do kế hoạch này không cần cơ chế ghim phiên: nếu phần lớn luật nặng nằm ở carrier 1
và 2 thì bệnh đó phần lớn không tồn tại.

### Nguyên tắc chọn carrier

Khi một sự cố đẻ ra một luật, chạy đúng bốn câu hỏi theo thứ tự:

```
1. Bỏ được bậc tự do không?   → tool hoặc hook.  Luật BIẾN MẤT.
2. Code phát hiện được không?  → validation.      Prose còn 1 dòng.
3. Phán đoán về một năng lực?  → tool description / skill body.
4. Phán đoán về TÍNH CÁCH?     → nhân (hiếm, và phải xoá thứ khác).
```

### Vì sao "bỏ bậc tự do" là đòn bẩy mạnh nhất

Gần như mọi luật có dạng *"khi làm X, phải làm thế này, không được làm thế kia"*. Mỗi luật như
vậy là thuế đánh lên một bậc tự do thừa. Thử với mục đắt nhất trong nhóm này:

| Luật hiện tại (mục tạo agent/workflow, 2.875 ký tự) | Bỏ bậc tự do bằng |
|---|---|
| Ghi vào `agents/` phẳng, KHÔNG phải `Javis/agents/` | Tool tự ghi đúng chỗ |
| slug ASCII không dấu | Tool tự slugify (dùng `main.py:_ascii_slug`, có `replace("đ","d")`) |
| `description` tối đa 150 ký tự, đếm sau khi viết | Validation trả lỗi kèm số ký tự thừa |
| `group` không được trống, đọc group đang dùng rồi chọn gần nhất | Tham số enum dựng từ group có sẵn |
| Workflow tham chiếu agent chưa có thì tạo agent trước | Tool kiểm tham chiếu |
| Loop tạo từ chat mặc định `enabled: false`, `mode: full` | Giá trị mặc định của tool |

Sáu luật, 2.875 ký tự, **biến mất hoàn toàn**. Không nén, không truy xuất. Và tỉ lệ đúng tăng
từ ~80% (model nhớ luật) lên 100% (code ép).

### Đường trải nhựa, không phải cái lồng

Thu hẹp giao diện làm giảm linh hoạt, mà linh hoạt là điểm bán của Javis. Nên thiết kế là hai
lớp:

- **Đường trải nhựa:** `javis_create_agent(...)` làm đúng mọi thứ, là đường dễ nhất nên model
  tự chọn
- **Lan can:** hook `pre_tool_call` chặn hoặc sửa một lệnh ghi vào `Javis/agents/`, trả về câu
  giải thích

Tool file thô vẫn còn cho việc tự do (viết bài, phân tích, dữ liệu). Ranh giới:

> **Thứ gì có frontmatter bắt buộc thì có tool. Thứ gì tự do thì giữ primitive.**

**Giới hạn phải nói thẳng:** hook chỉ bọc tool đi qua hub (`mcp_hub.py:951`). Tool `Write`
native của Claude Code và Codex **không đi qua đó**, nên lan can không với tới. Hai lớp bù:

1. `mcp_store.disallowed_tools()` đã có đường chặn tool native (`main.py:3331`), nhưng cấm
   `Write` cho chat của chủ là quá tay, không làm.
2. **Hậu kiểm sau lượt:** `channel_context.collect_turn_files` đã quét file mới sau mỗi lượt.
   Thêm một bước đối chiếu: file `.md` có frontmatter `type: agent|workflow` mà nằm sai thư
   mục thì di chuyển về đúng chỗ và ghi một dòng vào câu trả lời. Đây là chữa cháy, không phải
   phòng cháy, nhưng nó biến một lỗi câm thành một lỗi nói ra.

---

## Hợp đồng 1: `system/prompt/kernel.md`

### Tách hai khán giả

`server/main.py:351` trỏ vào `CLAUDE.md` ở gốc repo. Cùng file đó đang phục vụ hai khán giả
khác hẳn nhau:

1. **Claude Code làm việc trên repo `javis-os`** đọc nó làm project file (tự động theo cwd)
2. **Mọi người dùng cuối của Javis** nhận nó làm system prompt, mọi lượt chat

Đây là nguyên nhân **cấu trúc** của việc phình: mỗi lần thêm một quy ước dev là mọi khách hàng
trả tiền cho nó ở mọi lượt. Mục "Dev conventions" (1.005 ký tự) chỉ là phần nhìn thấy được.

Sau khi tách:

```
CLAUDE.md                    quy ước dev của repo. Claude Code đọc theo cwd.
                             KHÔNG vào system prompt của sản phẩm.
system/prompt/kernel.md      nhân prompt của sản phẩm. main.py:351 trỏ vào đây.
system/prompt/blocks/*.md    khối điều kiện (xem Hợp đồng 4)
system/prompt/policies/*.md  luật theo carrier skill (xem Hợp đồng 2)
```

### Nội dung nhân (mục lục cố định)

```
1. Javis là ai                      ~1.200   tính cách, bộ não thay được
2. Hợp đồng đầu ra                  ~1.500   ngôn ngữ, xưng hô, định dạng, cấm em dash
3. Thang quyết định                   ~700   5 dòng, không phải 8.888 ký tự
4. Khi nào hỏi lại                  ~1.200   phán đoán thật, giữ
5. Khi không có MCP phù hợp           ~150
6. MỤC LỤC NHÓM LUẬT                  ~250   luôn có mặt, chống trượt im lặng
                                    ------
                                    ~5.000   trần 8.000, dư cho luật tính cách phát sinh
```

Mục 6 là chốt chặn cho rủi ro lớn nhất của việc rút luật ra ngoài: hôm nay model thấy đủ
33.577 ký tự nên nó biết mọi luật tồn tại; sau khi rút, nó có thể không biết thứ nó cần có
tồn tại hay không. Mục lục cấp NHÓM giữ cho model luôn có **bản đồ**, chỉ là không luôn có
**nội dung**:

```
Nhóm luật hiện có: điều phối công việc · tạo năng lực · bộ nhớ · tệp và ảnh ·
số liệu và MCP · kênh và chatbot · an toàn.
Cần nhóm nào chưa có trong prompt thì gọi javis_use_skill để lấy.
```

---

## Hợp đồng 2: file luật

Một luật = một file, đặt ở `system/prompt/policies/<id>.md`, dùng lại định dạng skill đang có
nên `skill_router` và `javis_use_skill` đọc được ngay, không cần runtime mới.

```yaml
---
id: ba-muc-quyen-loop
group: dieu-phoi                  # khớp mục lục nhóm trong nhân
description: "Ba mức quyền của loop và khi nào chọn mức nào."   # <= 150, skill_router ép
requires: [thang-quyet-dinh]      # nạp cái này thì kéo theo
enforced_by: javis_schedule       # trống = chưa có code ép
added: 2026-08-16
because: "Loop mode full chạy hành động ra ngoài không hỏi"
review: 2027-02-16
---
<thân luật, không giới hạn độ dài, chỉ vào ngữ cảnh khi được nạp>
```

### Chia chunk theo QUYẾT ĐỊNH, không theo mục

Mục Orchestration 8.888 ký tự nạp cả cục thì gần như không tiết kiệm gì. Tách quanh **một
quyết định**, mỗi đơn vị 800 tới 1.500 ký tự:

```
policies/thang-quyet-dinh.md            ~900    (rút gọn còn 5 dòng đưa vào nhân)
policies/bao-ket-qua-ve-nguoi-hoi.md  ~1.200    enforced_by: server tự gắn chat_id
policies/ba-muc-quyen-loop.md         ~1.100    enforced_by: javis_schedule
policies/dieu-kien-truoc-khi-len-lich.md ~900   enforced_by: javis_schedule (can_force)
policies/zalo-gui-tin.md              ~1.000    → về mô tả zalo_send_message
policies/khong-hua-suong.md             ~200    enforced_by: background_status
```

---

## Hợp đồng 3: ba tool mới

Viết dưới dạng bundled plugin, đúng khuôn `system/plugins/javis-schedule/`. Dùng
`ctx.register_tool` (`plugins_host.py:340`), `min_mode="safe"` (ghi file, không hành động ra
ngoài). Cả ba nằm trong lazy pool, không thêm vào `CORE_TOOL_FNS`.

### `javis_create_agent` / `javis_update_agent`

```
op            create | update
slug          tuỳ chọn. Thiếu thì tool tự slugify từ name bằng _ascii_slug.
name          bắt buộc khi create.
description   bắt buộc. Tool ĐẾM và trả lỗi nếu > 150, kèm số ký tự thừa.
group         enum dựng LÚC CHẠY từ group đang dùng trong agents/ + skills/ + workflows/.
              Không khớp cái nào thì tool nhận giá trị mới nhưng trả cảnh báo.
skills        danh sách slug. Tool kiểm tồn tại, trả lỗi nếu trỏ vào skill không có.
body          nội dung prompt của agent.
```

Tool tự lo: ghi vào `<brain>/agents/<slug>.md` phẳng, dựng frontmatter đúng, chống trùng slug,
từ chối slug có dấu hoặc có `/` và `..`.

Retire: **2.875 ký tự** (mục "Creating/editing Agents and Workflows") và **1.726** (mục
"Building capabilities", vốn đã trùng skill `javis-builder`).

### `javis_create_workflow`

Cùng khuôn. Thêm một việc mà prose đang phải dặn: **kiểm tham chiếu**. Workflow trỏ tới agent
chưa tồn tại thì tool trả lỗi kèm tên agent thiếu, thay vì để model nhớ luật "tạo agent trước".

### `javis_remember`

```
type          user | preference | business | decision
content       nội dung ký ức
slug          tuỳ chọn, thiếu thì slugify từ dòng đầu của content
```

Tool tự lo: ghi `<brain>/memory/facts/<slug>.md` **chữ thường** (luật "Linux đọc chữ M hoa là
thư mục khác" biến mất), dựng frontmatter `type/created/updated`, thêm đúng một dòng vào
`memory/MEMORY.md`, và **tự phát hiện trùng** rồi cập nhật file cũ thay vì đẻ bản sao.

Retire: **2.297 ký tự**.

### `javis_create_plugin`

Ép sẵn `enabled: false`, đòi khai `min_mode` tường minh, và **trả về câu nhắc về
`JAVIS_ENABLE_USER_PLUGINS`** trong kết quả tool thay vì bắt model nhớ nói.

Retire: **2.114 ký tự**.

---

## Hợp đồng 4: khối điều kiện

Server không đoán, nó **biết**. Năm khối này lắp theo sự thật đã có sẵn, không truy xuất,
không rủi ro, không vòng tool.

| Sự thật | Khối | Ký tự | Server biết ở đâu |
|---|---|---:|---|
| Có file đính kèm | `blocks/files-attached.md` | 2.272 | `has_attachments`, `main.py:12175` |
| Có khối `[FILE ĐANG MỞ]` | `blocks/open-file.md` | 676 | server tự chèn khối đó |
| Pack CRM đã cài | `blocks/customer-inbox.md` | 329 | `packs_store` |
| Có MCP số liệu | `blocks/data-cache.md` | 824 | `javis_connections` |
| Phiên dev trên repo | (về `CLAUDE.md`) | 1.005 | không còn liên quan |

Lượt không khớp điều kiện nào trả **0 ký tự** cho cả năm.

---

## Hợp đồng 5: xếp khối theo độ ổn định

Thứ tự lắp là một phần của hợp đồng, vì `engine.py:330` phụ thuộc vào tiền tố ổn định:

```
┌─ NHÂN                     không đổi giữa các lượt, không đổi giữa các brain
├─ BỘ NHỚ (chỉ mục ngắn)    đổi khi có ký ức mới
├─ KHỐI ĐIỀU KIỆN           đổi khi điều kiện đổi, không đổi theo lượt
│  ═══ RANH GIỚI CACHE: cache_control đặt ở ĐÂY ═══
├─ ĐỒNG HỒ, NGÔN NGỮ, KÊNH  đổi mỗi lượt
└─ CÂU HỎI
```

Hôm nay khối đồng hồ (`context_compiler.dong_ho`) nằm ở **cuối** `build_system_prompt` nên đã
đúng chiều. Việc cần làm là đặt `cache_control` đúng ranh giới thay vì bọc cả khối system.

## Hợp đồng 6: nhân đúc sẵn theo chữ ký

`build_system_prompt` cache theo chữ ký, đúng khuôn `plugins_host._signature` đã làm:

```python
sig = (mtime kernel.md, mtime blocks/, mtime policies/, mtime MEMORY.md,
       chữ ký cây skill (system_sync._mirror_signature, stat-only),
       brain, lang, project_id, session_id, bộ điều kiện đang bật)
```

Hai cái lợi, và cái thứ hai quan trọng hơn:

1. Bỏ ~40ms chặn mỗi lượt
2. Tiền tố gửi đi **byte-identical** giữa các lượt, nên prompt cache ăn chắc chứ không ăn nhờ
   may

---

## Hợp đồng 7: MEMORY.md

Cùng đường phân đôi, khác thuốc, vì bộ nhớ không được phép vắng mặt.

| | Hôm nay | Sau |
|---|---|---|
| Tính cách người dùng (xưng hô, vai trò, ngành, mục tiêu) | Lẫn trong 20.000 | **~800 ký tự, luôn có mặt** |
| Chỉ mục fact (bề mặt) | Cùng chỗ, bị cắt khi đầy | Trần 3.000, mỗi fact 1 dòng ~60 ký tự → ~50 fact, **không cắt dòng nào** |
| Chi tiết fact | Nhét sẵn trong chỉ mục | Nạp khi liên quan |

Trần mới 3.000 chứa được **nhiều fact hơn** trần cũ 20.000, vì trần cũ gánh cả chi tiết. Bậc
"mất trí nhớ" trong `_fit_memory_index` biến mất.

---

## Lộ trình

Thứ tự có ràng buộc, không xếp theo cảm tính. Hai luật thứ tự:

- **Chặn nguồn phình đứng trước dọn hậu quả** (việc 1, 2 trước mọi thứ)
- **Cơ chế thay thế phải chạy trước khi rút luật ra** (việc 3, 6 trước việc 7 tới 9)

| # | Việc | Nghiệm thu | Công |
|---|---|---|---|
| 1 | Tách `CLAUDE.md` và `system/prompt/kernel.md`. `main.py:351` trỏ vào nhân | Chat của người dùng cuối không còn chứa "Dev conventions". Claude Code trên repo vẫn đọc được quy ước | 0,5 ngày |
| 2 | Đóng băng trần nhân 8.000 + bảng phân bổ ký tự trên trang Chẩn đoán | `test_prompt_budget` canh `kernel.md`, và một test thứ hai canh **tổng đã lắp**. Trang Chẩn đoán hiện ký tự từng khối | 1 ngày |
| 3 | Cho `pre_tool_call` quyền phủ quyết và sửa tham số (`plugins_host.py:755`) | Hook trả `{"deny": "lý do"}` thì tool không chạy và model nhận đúng câu đó. Test hai chiều | 0,5 ngày |
| 4 | Bốn khối điều kiện | Lượt không có đính kèm giảm đúng 2.272 ký tự, đo bằng bảng ở việc 2 | 1 ngày |
| 5 | Rút luật code đã ép + thêm `enforced_by` vào mọi file luật | Ba đoạn "hứa suông" (2.403) còn 1 dòng. Test: mọi `enforced_by` khác trống phải trỏ tới symbol có thật | 0,5 ngày |
| 6 | `javis_remember` | Retire 2.297. Ghi thử 60 ký ức, `MEMORY.md` không mất dòng nào | 1 ngày |
| 7 | `javis_create_agent`, `javis_create_workflow` + lan can hook | Retire 2.875 + 1.726. Ghi thẳng vào `Javis/agents/` bị chặn kèm câu giải thích | 2 ngày |
| 8 | `javis_create_plugin` | Retire 2.114 | 1 ngày |
| 9 | Tách Orchestration thành policy, phần lớn về tool đã có | Retire ~8.000. Nhân dưới 6.500 | 2-3 ngày |
| 10 | Nhân đúc sẵn theo chữ ký + dời `cache_control` | `bench_hotpath` build dưới 2ms khi cache nóng. Tiền tố byte-identical giữa hai lượt liên tiếp | 1 ngày |
| 11 | `MEMORY.md` tách chỉ mục và chi tiết | Bậc cắt dòng không còn với 50 fact | 2 ngày |
| 12 | Bỏ `SKILL_LIST_MAX`, chuyển sang top-k theo `capability_index` | Brain 40 skill vẫn route trúng skill thứ 35 | 2 ngày |
| 13 | `/luat-moi` phân loại tại nguồn | Lệnh chạy 4 câu hỏi và dựng khung file ở đúng carrier | 1 ngày |

**Việc 13 không phải phần thưởng cuối, nó là thứ giữ cho 12 việc trên không trôi lại.** Nếu
viết luật đúng chỗ vẫn đắt hơn viết vào nhân thì độ dốc còn nguyên.

### Kết quả dự kiến, nói theo phân phối

Không nói một con số, vì một con số là cách làm người đọc quyết định sai.

| | Hôm nay | Sau |
|---|---:|---:|
| Câu hỏi thường (p50) | 33.577 | **~6.000** |
| Có file đính kèm (p80) | 33.577 | ~8.300 |
| Đang tạo agent, tool trong phạm vi (p95) | 33.577 | ~7.000 |
| Xấu nhất (p99) | 33.577 | ~11.000 |
| Vòng inference thêm mỗi lượt | 0 | **0** |
| Prompt cache | Ăn | Ăn, tiền tố ổn định hơn |
| Trần số luật | ~33.600 ký tự | **Không có** |

Dòng p95 là chỗ khác hẳn phương án "nén bằng truy xuất": khi model **đang làm** việc cần luật,
chi phí vẫn thấp hơn hôm nay, vì hợp đồng tool cô đọng hơn prose giải thích cách dùng
primitive.

---

## Test và rào

| Test | Canh cái gì |
|---|---|
| `test_prompt_budget` (sửa) | `kernel.md` <= 8.000. **Số này không được nâng**; nâng phải kèm xoá |
| `test_prompt_assembled` (mới) | Tổng đã lắp <= 14.000 cho mọi tổ hợp điều kiện |
| `test_rule_provenance` (mới) | Mọi file luật có `id`, `group`, `description` <= 150, `added`, `because`. `enforced_by` khác trống phải trỏ tới symbol có thật |
| `test_kernel_no_surface` (mới) | Nhân không chứa tên engine, tên connector, đường dẫn file cụ thể. Đây là rào cho Hằng số 1, và là thứ bắt được việc trôi sớm nhất |
| `test_hook_veto` (mới) | Hook trả `deny` thì tool không chạy; hook lỗi thì tool VẪN chạy (fail-open, hook hỏng không được làm chết Javis) |
| `test_tool_retire` (mới) | Với mỗi tool trong bảng retire, `kernel.md` không còn chứa các cụm khoá của mục đã rút |

`test_kernel_no_surface` là test đáng giá nhất trong danh sách. Nó biến Hằng số 1 từ một lời
hứa thành một thứ CI kiểm được, và nó đỏ ngay lần đầu có người viết "Antigravity" hay
"agents/" vào nhân.

---

## Rủi ro và đường lui

| Rủi ro | Mức | Cách lui |
|---|---|---|
| Model không gọi tool mới, vẫn ghi file thô | Cao lúc đầu | Lan can hook + hậu kiểm `collect_turn_files`. Đo tỉ lệ gọi tool trong 1 tuần trước khi rút prose |
| Rút luật ra rồi model làm sai việc đó | Trung bình | **Chạy song song**: giữ prose trong nhân đồng thời tạo tool, đo 1 tuần, route trúng ổn định rồi mới cắt. Việc 7 tới 9 bắt buộc theo cách này |
| Tool mới làm mất linh hoạt | Trung bình | Primitive vẫn còn. Tool là đường trải nhựa, không phải cái lồng |
| Nhân đúc sẵn trả bản cũ sau khi sửa skill | Thấp | Chữ ký gồm mtime cây skill, đúng khuôn `plugins_host._signature` đã chạy tốt |
| Hook phủ quyết chặn nhầm | Thấp | Fail-open khi hook lỗi. Allowlist đường dẫn tường minh, không suy ngầm |
| Việc 12 (bỏ `SKILL_LIST_MAX`) làm route trượt | Trung bình | Làm sau cùng, và chỉ khi `miss_class` trên trang Chẩn đoán có dữ liệu |

**Điều kiện dừng:** bất kỳ việc nào trong 7 tới 9 mà sau 1 tuần chạy song song, tỉ lệ model
dùng đường tool dưới 90% thì **không cắt prose**, quay lại sửa mô tả tool trước.

---

## Những thứ CỐ Ý không làm

Ghi lại vì mỗi cái đều từng là một phương án được cân nhắc rồi bị loại có lý do.

- **Không xây tầng truy xuất policy mới.** Cơ chế đã có (lazy tool pool, `skill_router`,
  `javis_use_skill`) và đã đo được. Thêm tầng thứ bảy lên một chồng sáu tầng chưa có baseline
  production là lặp lại đúng sai lầm đã dẫn tới đây.
- **Không cấu hình embedding cho `capability_index`.** Khung RRF đã sẵn. Bật khi `miss_class`
  báo cần, không bật theo linh cảm. Embedding thêm độ trễ, thêm hạ tầng, khó gỡ lỗi, và phần
  lớn luật không cần nó vì chúng kích hoạt bằng **cấu trúc** (có biểu thức thời gian, có ý
  định tạo) chứ không bằng từ vựng.
- **Không xây cơ chế ghim policy theo phiên.** Chỉ cần khi luật sống trong policy body. Đưa
  luật vào hợp đồng tool thì phạm vi tool đã ổn định sẵn cả phiên, ghim là máy móc thừa.
- **Không để model tự gọi `javis_use_skill` làm đường CHÍNH.** Nó là một vòng inference đầy
  đủ, tức 30 tới 60 giây trên engine CLI. Nó là lưới an toàn cho ca truy xuất trượt, không
  phải đường đi hằng ngày.
- **Không nâng trần nhân.** Nếu bản sau thấy chạm 8.000, đó là tín hiệu có luật bề mặt lọt vào
  nhân, không phải tín hiệu trần quá nhỏ.

---

## Phụ lục: bảng định tuyến `CLAUDE.md` hiện tại

| Mục | Ký tự | Đích | Ghi chú |
|---|---:|---|---|
| Orchestration | 8.888 | Tool + nhân | Thang quyết định 5 dòng vào nhân (~700). Báo kết quả → server tự gắn `chat_id`. Ba mức quyền → tham số tool. Luật Zalo → mô tả `zalo_send_message`. Hứa suông → `background_status` đã ép, còn 1 dòng |
| What Javis is | 4.071 | Nhân + dữ liệu | Tính cách giữ ~1.200. Bảng 10 engine là **dữ liệu**, sinh từ `PROVIDERS`, không viết tay |
| Response principles | 3.812 | Nhân + kênh | Tính cách giữ ~1.500. Phần theo kênh đã có `channel_context` |
| Creating Agents/Workflows | 2.875 | Tool | `javis_create_agent`, `javis_create_workflow`. Còn 0 |
| Long-term memory | 2.297 | Tool | `javis_remember`. Còn 0 |
| Files attached | 2.272 | Khối điều kiện | `has_attachments` |
| Creating Plugins | 2.114 | Tool | `javis_create_plugin`. Còn 0 |
| Clarify before answering | 2.055 | Nhân | Phán đoán thật, giữ nguyên |
| Building capabilities | 1.726 | Skill | Đã trùng `javis-builder`. Còn 0 |
| Dev conventions | 1.005 | Tách file | Về `CLAUDE.md` của repo |
| Data Cache | 824 | Khối điều kiện | Chỉ khi có MCP số liệu |
| Open file | 676 | Khối điều kiện | Server tự chèn khối đó |
| Customer inbox | 329 | Khối điều kiện | Chỉ khi pack CRM đã cài |
| Role, công thức, khi không có MCP | ~610 | Nhân | Giữ |

**Tổng vào nhân: ~5.000 tới 6.500 ký tự.** Dưới trần 8.000, và phần dư dành cho luật tính
cách phát sinh, không dành cho luật bề mặt.

---

## Tóm tắt một đoạn

Vấn đề không phải luật quá nhiều, mà là **model có quá nhiều bậc tự do thừa, và viết prose là
cách rẻ nhất để đánh thuế lên chúng**. Kế hoạch này đổi giá: làm cho việc đặt luật đúng carrier
rẻ ngang việc nhồi vào nhân, đóng băng trần nhân để buộc phải chọn, và bắt mọi luật khai người
thi hành để luật nào code đã ép thì tự động bị xoá khỏi prompt.

Repo đã tự chứng minh mệnh đề trung tâm: `javis_schedule` có tool nên tốn ~600 ký tự prose,
trong khi tạo agent không có tool nên tốn 2.875 ký tự cho một việc đơn giản hơn. Thứ còn
thiếu không phải kiến trúc, mà là một quy trình buộc phải rút prose khi tool ra đời.
