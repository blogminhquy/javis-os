# Kế hoạch: Nhân prompt có trần đóng băng và tầng luật theo carrier

> Bản kế hoạch dev, viết 2026-09-22 trên nền code v0.63.0. Mục tiêu: chấm dứt tình trạng
> `CLAUDE.md` phình tới trần rồi phải nâng trần, bằng cách đổi **nơi luật được viết ra** chứ
> không phải đổi cách nén luật.

## Đọc gì nếu chỉ có 2 phút

1. `CLAUDE.md` còn **23 ký tự** trước khi chạm trần CI. Trần này đã bị nâng một lần rồi.
2. Nguyên nhân không phải "luật quá nhiều". Nguyên nhân là **viết prose vào `CLAUDE.md` là
   cách rẻ nhất để ép model làm đúng**, nên mọi luật đều chảy về đó. Dọn chỗ trống mà không
   sửa cái đó thì chỗ trống sẽ đầy lại.
3. Bằng chứng nằm sẵn trong repo: việc đặt lịch **có tool riêng** nên chỉ tốn ~600 ký tự
   prose; việc tạo agent **không có tool** nên tốn 2.875 ký tự cho một việc đơn giản hơn.
4. Nên hướng đi là: **biến luật thành tool và code**, không phải nén luật cho khéo hơn.
5. Ba hằng số giữ cho nó không trôi lại: nhân chỉ chứa thứ thuộc về **tính cách** Javis, trần
   nhân **đóng băng không vay được**, và mỗi luật phải khai **ai đang thi hành nó**.

---

# Phần 1: Chuyện gì đang xảy ra

## Số đo

```
CLAUDE.md          33.577 ký tự
Trần CI            33.600 ký tự   (tests/python/test_prompt_budget.py)
Còn lại                23 ký tự
```

Chạy `python tests/run.py prompt_budget -v` lúc viết bản này:

```
ok  CLAUDE.md dưới trần 33,600 ký tự   [hiện 33,577 ký tự, còn 23 ký tự]
ok  CORE_CONTRACT dưới trần 2,000      [hiện 740 ký tự]
ok  đường biên dịch nhỏ hơn legacy ít nhất 10 lần
    [CORE_CONTRACT bằng 2.2% CLAUDE.md, tiết kiệm 98%]
```

Comment ngay trên cái trần đó đã viết sẵn cho lần này:

> "Lần chạm trần TIẾP THEO thì cắt thật hoặc đẩy một mục sang skill, đừng nâng số này nữa."

Trần đã bị nâng một lần (`33.600 (0.50.0): nâng trần thay vì cắt`). Nên câu hỏi thật không
phải "nâng lên bao nhiêu" mà là **vì sao nó luôn đầy**.

## File này đi vào đâu

`server/main.py:351-352` đọc `CLAUDE.md` ở gốc repo làm `SYSTEM_PROMPT`, và
`build_system_prompt()` (`main.py:755`) đặt nó làm nền cho **mọi lượt chat của mọi engine**.

Với engine gói thuê bao, `_subscription_system_prompt` (`main.py:12110`) cố ý giữ nguyên
`CLAUDE.md`. Lý do ghi ở `main.py:12117`:

> "bỏ CLAUDE.md đổi lấy token là món hời khi bị siết TPM và mỗi token đều tính tiền. Với gói
> thuê bao thì không tính tiền theo token"

Lập luận này đúng về **tiền** và sai về **thời gian**. Gói thuê bao không tính tiền theo token,
nhưng 33.577 ký tự vẫn tốn y nguyên thời gian xử lý mỗi lượt.

Dòng thứ ba trong kết quả test ở trên đáng chú ý: đường biên dịch **đã chứng minh** một prompt
lõi 740 ký tự chạy được. Nó chỉ áp cho engine API. Bản kế hoạch này không đi theo hướng
CORE_CONTRACT (bỏ hẳn `CLAUDE.md` là bỏ luôn tính cách Javis), nhưng con số đó là bằng chứng
rằng phần lớn 33.577 ký tự kia **không phải thứ bắt buộc phải có mặt ở mọi lượt**.

---

# Phần 2: Vì sao file cứ phình

## Nó là kho mô sẹo

Gần như mọi luật trong `CLAUDE.md` đều mang một ngày sự cố: "chủ repo báo 2026-08-13", "sự cố
13/09/2026", "incidents on 2026-07-19 and 2026-08-16", "khách báo 2026-08-30".

File này tăng đều một luật mỗi sự cố, và không bao giờ giảm. Đó là một vòng học tốt, nhưng là
**vòng học không có cơ chế quên**.

## Nhưng nguyên nhân sâu hơn là giá

Câu hỏi đúng: vì sao mọi luật đều chảy vào đúng một file?

| Nơi viết luật | Thời gian | Ai làm được |
|---|---|---|
| Thêm đoạn vào `CLAUDE.md` | ~5 phút | Bất kỳ ai, kể cả qua chat |
| Viết validation trong code | ~2 giờ | Cần lập trình |
| Viết một tool mới | ~1 ngày | Cần lập trình |

`CLAUDE.md` không phải một lựa chọn thiết kế. Nó là **con đường ít cản trở nhất**. Dưới áp lực
thời gian, mọi luật đều lăn xuống chỗ trũng.

Hệ quả phải nói thẳng, vì nó phủ định hai phương án nghe có vẻ hiển nhiên:

> **Bất kỳ kế hoạch nào dọn chỗ trống mà để nguyên độ dốc thì chỗ trống sẽ đầy lại.**

Nâng trần: mua thêm vài tháng. Nén bằng một tầng truy xuất: mua thêm một hai năm, đổi lấy một
hệ thống mới phải nuôi. Cả hai đều không chạm tới độ dốc.

## Và vì sao truy xuất không phải câu trả lời

Ghi lại để bản sau khỏi đi lại đường này.

Lập luận "chi phí mỗi lượt là O(top-k) nên tổng số luật tăng bao nhiêu cũng được" sai ở chỗ
**k không phải hằng số**.

Số luật liên quan tới MỘT hành động tăng theo độ phức tạp hệ thống. Hôm nay tạo một agent cần
biết 6 luật. Khi Javis có 20 engine, 50 connector, 5 kênh thì cần biết 6 luật đó **cộng** các
luật tương tác: engine này ghi file khác engine kia, kênh này không hiện markdown, connector
kia cần quyền khác. Số cặp tương tác tăng theo bình phương bề mặt.

Truy xuất cho một **hằng số nhân tốt hơn**, không cho **sự không giới hạn**. Muốn không giới
hạn thì phải có cơ chế làm luật **biến mất**, không phải làm luật rẻ hơn khi mang theo.

---

# Phần 3: Bằng chứng ngay trong repo

Repo đã tự chạy thí nghiệm này rồi, chỉ là chưa ai đọc kết quả.

Hai năng lực, cùng độ phức tạp, khác nhau đúng một điều:

| Năng lực | Có tool riêng | Prose trong `CLAUDE.md` |
|---|---|---:|
| Đặt lịch, nhắc hẹn, loop | **Có** (`javis_schedule`) | **~600 ký tự** |
| Tạo agent, workflow | Không | **2.875** |
| Tạo plugin | Không | **2.114** |
| Ghi bộ nhớ dài hạn | Không | **2.297** |

Đặt lịch **phức tạp hơn** tạo agent: có cron, có ba mức quyền, có hai kho lưu khác nhau, có
điều kiện tiền đề. Nhưng nó chỉ tốn ~600 ký tự prose, vì luật của nó nằm trong hợp đồng tool
(`system/plugins/javis-schedule/plugin.py:583`, mô tả ~1.900 ký tự).

Và quan trọng hơn: tool đó **nằm trong lazy pool**. `mcp_hub.py:837` lấy pool là mọi tool trừ
`CORE_TOOL_FNS` (`mcp_hub.py:598`, chỉ có `javis_read_file`, `javis_list_dir`,
`javis_write_file`). Nên 1.900 ký tự ấy chỉ vào ngữ cảnh khi model thật sự cần đặt lịch. Lượt
hỏi doanh thu trả 0 ký tự cho nó.

> **Cơ chế "luật đi kèm năng lực, nạp lười theo nhu cầu" đã tồn tại, đã chạy production, đã đo
> được (schema tool 11.994 ký tự xuống 2.001, giảm 83%). `CLAUDE.md` là thứ duy nhất đứng
> ngoài nó.**

Vì vậy kế hoạch này **không xây tầng truy xuất mới**. Nó đưa `CLAUDE.md` vào cơ chế đang chạy.

## Lỗ hổng quy trình

`javis_schedule` đã có từ lâu, nhưng mục Orchestration trong `CLAUDE.md` vẫn còn nguyên 8.888
ký tự mô tả lại chính những luật đó.

**Thêm tool không tự động rút prose.** Không có trường nào, test nào, quy trình nào nói "luật
này nay do code ép, xoá khỏi prompt". Đó chính là độ dốc, và nó là thứ phải sửa trước tiên.

---

# Phần 4: Sáu lỗi thật phát hiện khi khảo sát

Đã tự kiểm chứng trên code. Ba cái đầu là tiền đề của kế hoạch.

## 4.1. Hai hằng số mâu thuẫn nhau, và Antigravity trả giá

Lỗi này chỉ lộ ra khi đặt hai con số ở hai file cạnh nhau.

- `compaction.AGY_BOOTSTRAP_MAX_CHARS = 100_000`: lịch sử gửi lại mỗi lượt
- `antigravity_cli._tran_argv()`: trần dòng lệnh, **120.000 byte** trên Linux

**Số đo thật (2026-09-22), không phải ước lượng:**

```
tỉ lệ byte/ký tự tiếng Việt (đo trên docs/dev)      1,202
build_system_prompt (brain mẫu)                    37.767 ký tự
+ khối kênh                                         8.412
= SYSPROMPT THẬT                                   46.179 ký tự
```

> **Đính chính so với bản đầu:** bản đầu ước lượng sysprompt "~36.000". Số thật là **46.179**,
> cao hơn 28%. Riêng khối kênh đã 8.412 ký tự, nhiều hơn hẳn mức đáng có cho một khối lắp vào
> mọi lượt - đáng soi riêng, nhưng không thuộc đợt này.

Áp vào ngân sách `120.000 x 0,97 / 1,21 = 96.198 ký tự`:

| Tình huống | Sysprompt | Lịch sử | Tổng | Kết quả |
|---|---:|---:|---:|---|
| Trước khi sửa | 46.179 | 100.000 | 146.179 | **VƯỢT nặng** |
| Chỉ hạ lịch sử xuống 80.000 | 46.179 | 80.000 | 126.179 | **VẪN VƯỢT** |
| **Sau khi sửa (đợt này)** | 46.179 | **45.000** | 91.179 | **vừa** |

### Vượt trần thì sao, nói cho đúng mức độ

> **Đính chính thứ hai, quan trọng hơn.** Bản đầu viết "vượt trần nghĩa là prompt phải đi qua
> file ngữ cảnh, thêm một vòng inference". Đọc kỹ `_chon_duong` lúc triển khai thì KHÔNG phải:
>
> ```python
> if do_dai <= _tran_argv():
>     return "argv"
> return duong_prompt_dai(self.cli_path)   # -> "stdin:<công thức>" HOẶC "file"
> ```
>
> Vượt trần thì thử **stdin trước**, và stdin không có trần. Chỉ máy nào không công thức stdin
> nào chạy được mới rơi xuống đường file. Nên cái giá 30-60 giây là của MỘT NHÓM MÁY, không
> phải của mọi lượt như bản đầu nói.

Lợi ích của việc hạ hằng số này vì vậy có hai phần, và phần thứ hai mới là phần chắc chắn:

1. **Máy dùng đường file:** bỏ được một vòng tool mỗi lượt.
2. **Mọi máy dùng đường file:** file ngắn hơn thì tool đọc file ít bị cắt cụt hơn. Đây là bug
   **đã được báo** (2026-09-18/19): model đọc nửa đầu file rồi trả lời một câu hỏi cũ. Lần hạ
   trước (300.000 xuống 100.000) cũng vì lý do này, và 100.000 vẫn còn đủ dài để dính.

### Đánh đổi

`agy` **không nối lại mạch**, nên gói lịch sử này là toàn bộ trí nhớ hội thoại của nó. Hạ
xuống 45.000 ký tự là khoảng 20-30 lượt chat thường. `bootstrap_prompt` giữ phần **gần nhất**
và không cắt `summary`, nên phần rơi ra là các lượt cũ nhất chứ không phải ngẫu nhiên.

Đổi lại là không còn trả lời nhầm câu hỏi cũ. Với một bug đã có người báo, đó là đổi đúng chiều.

### Trên Windows thì vô phương

Trần là **30.000 đơn vị UTF-16**, tức riêng sysprompt 46.179 đã không lọt dù hạ lịch sử xuống
bao nhiêu. Đường argv ở đó chết hẳn; đường đúng là stdin, và `duong_prompt_dai` đã ưu tiên
sẵn. Ghi rõ để không ai đi tối ưu nhầm hướng.

## 4.2. Hook `pre_tool_call` không chặn được gì

`plugins_host.py:755` bọc mọi tool call:

```python
async def _wrapped(args):
    await _fire("pre_tool_call", vault_root, {...})   # bỏ qua giá trị trả về
    result = await base_call(args)                     # gọi bất kể hook nói gì
```

Và `_fire` (`:746`) nuốt cả exception. Nên hook hiện **chỉ quan sát được**: không phủ quyết
được, không sửa tham số được. Docstring ở `:369` hứa "bắn quanh MỌI tool call" nên dễ tưởng nó
là chốt chặn; nó không phải.

Phần 8 sẽ cho thấy đây không phải một lỗi nhỏ: **nó là thứ quyết định cả kế hoạch có lãi hay
không.**

## 4.3. Skill thứ 21 trở đi vô hình với router

`skill_router.py:49` đặt `SKILL_LIST_MAX = 20`. `_skill_router_block` cắt ở đó rồi ghi
`…(+N skill nữa - xem Javis/index.md)`. Model không đọc file đó trừ khi được bảo, nên skill thứ
21 trở đi **không bao giờ được route**. Một brain dùng lâu chắc chắn vượt 20.

## 4.4. `_fit_memory_index`: NÓI QUÁ, đã đính chính

> **Đính chính 2026-09-22, sau khi đọc kỹ code lúc triển khai.** Bản đầu của tài liệu này gọi
> đây là "bậc cuối là mất ký ức", dựa vào chính docstring của hàm ("Mất hẳn dòng mới là mất
> trí nhớ"). Đọc code thật thì nhẹ hơn: bậc cuối có cắt dòng khỏi PROMPT, nhưng nó **đếm số
> dòng bị cắt và nói ra**, kèm đường đi tiếp:
>
> ```
> (Chỉ mục quá dài nên còn {N} ký ức chưa liệt kê ở đây.
>  Đọc memory/MEMORY.md để xem đủ danh sách, và memory/facts/ để xem chi tiết.)
> ```
>
> Không có ký ức nào mất khỏi ĐĨA, và model biết là còn thiếu. Đây không phải hỏng im lặng,
> nên nó KHÔNG thuộc nhóm "lỗi thật" và không được sửa trong đợt này.

Cái còn đúng: `MEMORY_INDEX_MAX = 20000` (`main.py:523`) lớn như vậy vì chỉ mục đang gánh cả
mô tả chi tiết. Tách chỉ mục khỏi chi tiết (Hợp đồng 7) vẫn đáng làm, nhưng vì lý do **gọn và
rẻ**, không phải vì "đang mất trí nhớ". Xếp lại ưu tiên cho đúng.

## 4.5. `build_system_prompt` chạy lại mỗi lượt: SỐ SAI, đã đo lại

> **Đính chính 2026-09-22.** Bản đầu viết "~40 ms chặn event loop". Con số đó là **mốc nghiệm
> thu** trong `bench_hotpath.py`, không phải số đo. Chạy `python bench_hotpath.py` thật:
>
> ```
> build_system_prompt   baseline 150,8 ms -> nay 3.9 ms   (đích < 60)
> ```
>
> **3,9 ms.** Việc tối ưu này đã được làm rồi, từ 150,8 xuống 3,9. Phần còn lại không đáng để
> đánh đổi lấy rủi ro cache trả bản cũ, và nhất là không đáng để bỏ qua hai tác dụng phụ lên
> ĐĨA mà hàm này đang gánh (`system_sync.ensure_synced` và `mirror_skills` - Claude Code dựa
> vào bản mirror đó để thấy skill).

**Kết luận: bỏ việc "nhân đúc sẵn theo chữ ký" khỏi lộ trình.** Lý do CPU đã hết. Lý do còn
lại (tiền tố byte-identical cho prompt cache) tự nó không đủ để dựng thêm một tầng cache có
chữ ký, nhất là khi đường CLI không dùng prompt cache của Javis.

Bài học chung, đáng ghi hơn cả bản vá: **một mốc nghiệm thu trong file bench không phải một số
đo.** Đọc nhầm hai thứ đó là dựng cả một hạng mục công việc trên một con số không ai từng đo.

## 4.6. Cache 1 giờ: KHUYẾN NGHỊ SAI, đã tra tài liệu và rút lại

`engine.py:320` có tham số `cache_ttl` nhận `"5m"` hoặc `"1h"`, và chỗ gọi duy nhất
(`engine.py:716`) không truyền gì nên luôn là 5 phút. Bản đầu của tài liệu này đề xuất
"truyền `cache_ttl='1h'`, một dòng sửa".

> **Đính chính 2026-09-22, sau khi tra tài liệu Claude API thay vì viết theo trí nhớ.** Cú
> pháp thì đúng và không cần beta header. Nhưng KINH TẾ thì ngược:
>
> - Ghi cache tốn **1,25x với TTL 5 phút**, và **2x với TTL 1 giờ**.
> - Hoà vốn: TTL 5 phút cần 2 request, TTL 1 giờ cần ít nhất 3.
> - Tài liệu nói thẳng: hai request cách nhau dưới 5 phút thì *"the 1-hour TTL buys nothing
>   there except the doubled write price"*.
>
> Chat là loại traffic dồn dập, tức đúng cái ca mà 1 giờ chỉ tốn thêm tiền. Bật đại trà là
> **làm đắt lên cho phần lớn người dùng** để phục vụ một thiểu số.

**Kết luận: bỏ việc "bật cache 1 giờ" khỏi lộ trình dưới dạng một dòng sửa.** TTL 1 giờ chỉ
đúng cho khoảng cách 5 tới 60 phút giữa hai lượt. Muốn làm cho đúng thì phải CHỌN theo khoảng
cách thật của từng phiên (Javis biết được: kho phiên có thời điểm lượt trước), và đó là một
tính năng có thiết kế riêng, không phải một tham số mặc định.

Bài học: `5m` mặc định hiện tại **đang đúng** cho ca phổ biến nhất. Một nhánh code viết sẵn mà
chưa ai gọi không tự động có nghĩa là ai đó quên gọi.

---

# Phần 5: Dốc và vách

Đây là khung để đọc mọi con số trong tài liệu này. Không có nó thì rất dễ tối ưu nhầm chỗ.

**Dốc** là hằng số mà sai một chút thì tốn một chút. Ví dụ: nhân 8.000 thay vì 6.000 là thêm
~393 token, tức khoảng **130 mili giây**. Trên một lượt mất 30 tới 90 giây thì đó là dưới
ngưỡng cảm nhận.

**Vách** là ngưỡng mà vượt qua là hành vi **nhảy bậc**. Ví dụ: vượt trần argv là thêm nguyên
một vòng inference, tức **30 tới 60 giây**.

Chênh lệch giữa hai loại là **hơn 200 lần**. Nên:

> Hiệu suất của Javis nằm ở chỗ đứng đúng bên của vài cái vách, không ở chỗ gọt từng nghìn
> ký tự trên dốc.

Bốn cái vách trong hệ thống:

| Vách | Ngưỡng | Vượt qua là gì |
|---|---|---|
| Trần dòng lệnh Antigravity | 120.000 byte (Linux), 30.000 UTF-16 (Windows) | Thêm 1 vòng inference, 30-60 giây |
| Ngưỡng lazy tool | 40 tool **hoặc** 6.000 ký tự schema | ~10.000 ký tự schema, đổi lấy khả năng thêm 1 vòng `javis_search_tools` |
| Hạn cache | 5 phút (hoặc 1 giờ nếu bật) | Mất toàn bộ tiền tố đã cache |
| Kích thước tối thiểu để cache | 512 tới 4.096 token, tuỳ model | **Dưới ngưỡng thì cache im lặng không chạy** |

Cái vách thứ tư là thứ mới phát hiện khi tra tài liệu API, và nó là **cái bẫy của chính kế
hoạch này**: cắt prompt quá tay có thể làm tiền tố tụt xuống dưới mức tối thiểu, và lúc đó
caching **ngừng hoạt động mà không báo gì**. Phần 9 có cách kiểm.

Ngưỡng lazy cũng đáng lưu ý: ba tool mới ở Phần 9 **làm pool to ra**, nên chúng có thể đẩy một
brain đang ở 38 tool vượt mốc 40. Đó là một thay đổi hành vi cần biết trước, không phải bất ngờ.

---

# Phần 6: Ba hằng số kiến trúc

Đây là phần phải đứng yên nhiều năm. Cả ba đều là **quy trình và cấu trúc**, không phụ thuộc
thư viện, model hay thuật toán nào, nên chúng sống lâu được.

## Hằng số 1: Đường phân đôi tính cách và bề mặt

> **Nhân prompt chỉ chứa thứ tỉ lệ với TÍNH CÁCH của Javis. Mọi thứ tỉ lệ với BỀ MẶT của
> Javis nằm cùng carrier của nó.**

| | Tính cách | Bề mặt |
|---|---|---|
| Nội dung | Javis là ai, xưng hô, cách trình bày, thang quyết định, khi nào hỏi lại | Engine, connector, định dạng file, quy trình vận hành, sự cố |
| Tốc độ tăng | Gần như đứng yên | Tăng siêu tuyến tính |
| Bằng chứng | Thang quyết định không đổi từ đầu repo | Gemini CLI bị gỡ, Antigravity thêm vào, Grok thêm vào |
| Nơi ở | `kernel.md` (trần đóng băng) | Tool contract, skill body, code, connector metadata |

Chia theo đường này thì nhân **không lớn lên**, vì thứ làm nó lớn lên đã bị định tuyến đi chỗ
khác ngay lúc sinh ra. Đó là tính bền mà kế hoạch này nhắm tới.

## Hằng số 2: Trần nhân đóng băng, không vay được

```
system/prompt/kernel.md     trần 8.000 ký tự, VĨNH VIỄN
```

Thêm vào nhân bắt buộc phải xoá thứ khác ra.

Vì sao đây là hằng số quan trọng nhất: **một cái trần nâng được không phải trần, nó là một lời
gợi ý.** Trần hiện tại đã bị nâng. Trần có răng là thứ duy nhất tạo áp lực buộc phải định
tuyến luật đi chỗ khác.

8.000 ký tự cũng là mức một người **đọc soát hết trong một lần ngồi**. 33.577 thì không ai soát
nổi, nên không ai biết trong đó còn luật nào đã lỗi thời.

Nói rõ để không ai hiểu nhầm: con số 8.000 **không phải một tối ưu hiệu suất**. Chênh lệch
giữa 8.000 và 6.000 chỉ là ~130 ms. Nó tồn tại vì kỷ luật.

## Hằng số 3: Mỗi luật khai người thi hành

```yaml
id: agent-ghi-dung-thu-muc
enforced_by: javis_create_agent     # code ép → XOÁ khỏi prose
# enforced_by: ""                   # trống → ứng viên để biến thành code
added: 2026-07-19
because: "Agent ghi vào Javis/agents/ nên biến mất khỏi app"
review: 2026-12-19
```

Trường `enforced_by` biến việc rút prose từ **tuỳ hứng** thành **tự động**: có người thi hành
bằng code thì prose bị xoá, không cần ai nhớ. Đây đúng là lỗ đã để mục Orchestration sống sót
nguyên vẹn dù `javis_schedule` có từ lâu.

---

# Phần 7: Bốn carrier và cách chọn

## Bảng giá thật

| Carrier | Chi phí mỗi lượt | Độ tin cậy | Rơi khỏi ngữ cảnh giữa chừng? |
|---|---|---|---|
| **Code / validation / hook** | **0 vĩnh viễn** | **100%** | Không thể |
| **Hợp đồng tool** (schema + description) | 0 khi ngoài phạm vi (lazy đã có) | ~95% | Không, phạm vi tool ổn định cả phiên |
| **Thân skill / policy** | 0 khi chưa nạp | ~90% | **Có** |
| **Prose trong nhân** | **Luôn trả** | ~80% | Không |

Hai carrier tốt nhất đều là code, và cả hai **miễn nhiễm với chuyện mất ngữ cảnh giữa lượt**.

Điều này giải quyết luôn một nỗi lo hiển nhiên: "rút luật ra rồi lượt sau model quên thì sao?".
Nếu phần lớn luật nặng nằm ở carrier 1 và 2 thì bệnh đó phần lớn không tồn tại, và **không cần
xây cơ chế ghim phiên** nào cả. Bớt được một hệ thống phải nuôi.

## Nguyên tắc chọn: bốn câu hỏi theo thứ tự

Khi một sự cố đẻ ra một luật:

```
1. Bỏ được bậc tự do không?   → tool hoặc hook.  Luật BIẾN MẤT.
2. Code phát hiện được không?  → validation.      Prose còn 1 dòng.
3. Phán đoán về một năng lực?  → tool description / skill body.
4. Phán đoán về TÍNH CÁCH?     → nhân (hiếm, và phải xoá thứ khác).
```

## Vì sao câu 1 là đòn bẩy mạnh nhất

Gần như mọi luật có dạng *"khi làm X, phải làm thế này, không được làm thế kia"*. Mỗi luật như
vậy là **thuế đánh lên một bậc tự do thừa** mà model lẽ ra không nên có.

Thử với mục đắt nhất trong nhóm này, mục tạo agent và workflow (2.875 ký tự):

| Luật hiện tại | Vì sao nó tồn tại | Bỏ bậc tự do bằng |
|---|---|---|
| Ghi vào `agents/` phẳng, KHÔNG phải `Javis/agents/` | Model được chọn đường dẫn | Tool tự ghi đúng chỗ |
| slug ASCII không dấu | Model tự đặt slug | Tool tự slugify (`main.py:_ascii_slug`, có `replace("đ","d")`) |
| `description` tối đa 150 ký tự, đếm sau khi viết | Model tự đếm | Validation trả lỗi kèm số ký tự thừa |
| `group` không được trống, đọc group đang dùng rồi chọn gần nhất | Model phải tự khảo sát | Tham số enum dựng từ group có sẵn |
| Workflow tham chiếu agent chưa có thì tạo agent trước | Model phải tự kiểm | Tool kiểm tham chiếu |
| Loop tạo từ chat mặc định `enabled: false`, `mode: full` | Model phải nhớ | Giá trị mặc định của tool |

Sáu luật, 2.875 ký tự, **biến mất hoàn toàn**. Không nén, không truy xuất. Và tỉ lệ đúng tăng
từ ~80% (model nhớ luật) lên 100% (code ép).

## Đường trải nhựa, không phải cái lồng

Thu hẹp giao diện làm giảm linh hoạt, mà linh hoạt là điểm bán của Javis. Nên thiết kế là hai
lớp:

- **Đường trải nhựa:** `javis_create_agent(...)` làm đúng mọi thứ, là đường dễ nhất nên model
  tự chọn
- **Lan can:** hook `pre_tool_call` chặn hoặc sửa một lệnh ghi vào `Javis/agents/`, kèm câu
  giải thích

Tool file thô vẫn còn cho việc tự do (viết bài, phân tích, dữ liệu). Ranh giới:

> **Thứ gì có frontmatter bắt buộc thì có tool. Thứ gì tự do thì giữ primitive.**

**Giới hạn phải nói thẳng:** hook chỉ bọc tool đi qua hub (`mcp_hub.py:951`). Tool `Write`
native của Claude Code và Codex **không đi qua đó**, nên lan can không với tới. Hai lớp bù:

1. `mcp_store.disallowed_tools()` đã có đường chặn tool native (`main.py:3331`), nhưng cấm
   `Write` cho chat của chủ là quá tay, không làm.
2. **Hậu kiểm sau lượt:** `channel_context.collect_turn_files` đã quét file mới sau mỗi lượt.
   Thêm bước đối chiếu: file `.md` có frontmatter `type: agent|workflow` mà nằm sai thư mục thì
   di chuyển về đúng chỗ và ghi một dòng vào câu trả lời. Đây là chữa cháy chứ không phải
   phòng cháy, nhưng nó biến một lỗi câm thành một lỗi nói ra.

---

# Phần 8: Kinh tế học của việc cắt

Phần này quyết định **cắt tới đâu thì dừng**, và nó sửa một con số mà trực giác hay đặt sai.

## Câu hỏi đúng

Không phải "cắt bao nhiêu thì nhanh hơn", mà **"cắt tới đâu thì bắt đầu chậm đi"**.

Vì một luật bị cắt mà model làm sai thì phải làm lại, và một lần làm lại đắt hơn rất nhiều so
với phần ký tự tiết kiệm được.

## Bảng hoà vốn

Dùng số đo thật: `CLAUDE.md` 33.369 ký tự tiếng Anh = 6.555 token, tức **5,09 ký tự/token**.
Tốc độ nạp prompt lấy rộng rãi 3.000 token/giây (con số này có lợi cho việc cắt).

**Cắt một mục 2.000 ký tự khỏi nhân:**

| Tình huống | Tiết kiệm | Một lần hỏng tốn | Chỉ lãi nếu | Tỉ lệ model làm đúng phải đạt |
|---|---:|---:|---|---:|
| **Có lan can** (hook bắt, thêm 1 vòng tool ~10s) | 131 ms/lượt | 10 s | dưới 1 lần hỏng / 76 lượt | **≥ 98,7%** |
| **Không lan can** (người dùng phát hiện, 1 lượt sửa ~60s) | 131 ms/lượt | 60 s | dưới 1 lần hỏng / 458 lượt | **≥ 99,8%** |

**Cắt cả mục Orchestration 8.888 ký tự:**

| Tình huống | Tiết kiệm | Chỉ lãi nếu | Tỉ lệ phải đạt |
|---|---:|---|---:|
| Có lan can | 582 ms/lượt | dưới 1 lần hỏng / 17 lượt | ≥ 94,2% |
| Không lan can | 582 ms/lượt | dưới 1 lần hỏng / 103 lượt | ≥ 99,0% |

## Hai kết luận

**Một: ngưỡng dừng là 98%, không phải 90%.**

Một bản nháp trước của kế hoạch này đặt "tỉ lệ model dùng đường tool dưới 90% thì không cắt".
90% nghĩa là 1 lần hỏng mỗi 10 lượt, trong khi hoà vốn là 1 mỗi 76. Tức ngưỡng đó **lỏng hơn
mức cần thiết gần 8 lần**, và làm theo nó là cắt xong rồi chậm đi mà không ai truy ra vì sao.

**Hai: lan can là điều kiện tiên quyết, không phải việc tiện thể.**

Bảng trên cho thấy hook phủ quyết kéo yêu cầu từ **99,8% (không đạt nổi)** xuống **98,7% (đạt
được)**. Không có lan can thì **toàn bộ việc rút prose không có lãi**, bất kể làm khéo tới đâu.

Nên trong lộ trình, việc hook phủ quyết **chặn cứng** mọi việc rút prose phía sau.

---

# Phần 9: Bảy hợp đồng

## Hợp đồng 1: `system/prompt/kernel.md`

### Tách hai khán giả

`server/main.py:351` trỏ vào `CLAUDE.md` ở gốc repo. Cùng file đó đang phục vụ hai khán giả
khác hẳn nhau:

1. **Claude Code làm việc trên repo `javis-os`** đọc nó làm project file (tự động theo cwd)
2. **Mọi người dùng cuối của Javis** nhận nó làm system prompt, mọi lượt chat

Đây là nguyên nhân **cấu trúc** của việc phình: mỗi lần thêm một quy ước dev là mọi khách hàng
trả tiền cho nó ở mọi lượt. Mục "Dev conventions" (1.005 ký tự) chỉ là phần nhìn thấy được;
áp lực thì còn mãi vì hai khán giả cùng ghi vào một file.

Sau khi tách:

```
CLAUDE.md                    quy ước dev của repo. Claude Code đọc theo cwd.
                             KHÔNG vào system prompt của sản phẩm.
system/prompt/kernel.md      nhân prompt của sản phẩm. main.py:351 trỏ vào đây.
system/prompt/blocks/*.md    khối điều kiện (Hợp đồng 4)
system/prompt/policies/*.md  luật theo carrier skill (Hợp đồng 2)
```

### Mục lục cố định của nhân

```
1. Javis là ai                      ~1.200   tính cách, bộ não thay được
2. Hợp đồng đầu ra                  ~1.500   ngôn ngữ, xưng hô, định dạng, cấm em dash
3. Thang quyết định                   ~700   5 dòng, không phải 8.888 ký tự
4. Khi nào hỏi lại                  ~1.200   phán đoán thật, giữ
5. Khi không có MCP phù hợp           ~150
6. MỤC LỤC NHÓM LUẬT                  ~250   luôn có mặt
                                    ------
                                    ~5.000   trần 8.000, dư cho luật tính cách phát sinh
```

Mục 6 là chốt chặn cho rủi ro lớn nhất của việc rút luật ra ngoài. Hôm nay model thấy đủ 33.577
ký tự nên nó biết mọi luật tồn tại; sau khi rút, nó có thể không biết thứ nó cần có tồn tại hay
không. Mục lục cấp **nhóm** giữ cho model luôn có **bản đồ**, chỉ là không luôn có **nội dung**:

```
Nhóm luật hiện có: điều phối công việc · tạo năng lực · bộ nhớ · tệp và ảnh ·
số liệu và MCP · kênh và chatbot · an toàn.
Cần nhóm nào chưa có trong prompt thì gọi javis_use_skill để lấy.
```

## Hợp đồng 2: file luật

Một luật = một file ở `system/prompt/policies/<id>.md`, dùng lại định dạng skill đang có nên
`skill_router` và `javis_use_skill` đọc được ngay, **không cần runtime mới**.

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
policies/thang-quyet-dinh.md              ~900   (rút gọn 5 dòng đưa vào nhân)
policies/bao-ket-qua-ve-nguoi-hoi.md    ~1.200   enforced_by: server tự gắn chat_id
policies/ba-muc-quyen-loop.md           ~1.100   enforced_by: javis_schedule
policies/dieu-kien-truoc-khi-len-lich.md  ~900   enforced_by: javis_schedule (can_force)
policies/zalo-gui-tin.md                ~1.000   → về mô tả zalo_send_message
policies/khong-hua-suong.md               ~200   enforced_by: background_status
```

## Hợp đồng 3: ba tool mới

Viết dưới dạng bundled plugin, đúng khuôn `system/plugins/javis-schedule/`. Dùng
`ctx.register_tool` (`plugins_host.py:340`), `min_mode="safe"`. Cả ba nằm trong lazy pool,
**không** thêm vào `CORE_TOOL_FNS`.

### `javis_create_agent` / `javis_update_agent`

```
op            create | update
slug          tuỳ chọn. Thiếu thì tool tự slugify từ name bằng _ascii_slug.
name          bắt buộc khi create.
description   bắt buộc. Tool ĐẾM và trả lỗi nếu > 150, kèm số ký tự thừa.
group         enum dựng LÚC CHẠY từ group đang dùng trong agents/ + skills/ + workflows/.
              Không khớp cái nào thì nhận giá trị mới nhưng trả cảnh báo.
skills        danh sách slug. Tool kiểm tồn tại, trả lỗi nếu trỏ vào skill không có.
body          nội dung prompt của agent.
```

Tool tự lo: ghi vào `<brain>/agents/<slug>.md` **phẳng**, dựng frontmatter đúng, chống trùng
slug, từ chối slug có dấu hoặc có `/` và `..`.

Retire: **2.875 ký tự** (mục "Creating/editing Agents and Workflows") và **1.726** (mục
"Building capabilities", vốn đã trùng skill `javis-builder`).

### `javis_create_workflow`

Cùng khuôn. Thêm **kiểm tham chiếu**: workflow trỏ tới agent chưa tồn tại thì tool trả lỗi kèm
tên agent thiếu, thay vì để model nhớ luật "tạo agent trước".

### `javis_remember`

```
type          user | preference | business | decision
content       nội dung ký ức
slug          tuỳ chọn, thiếu thì slugify từ dòng đầu
```

Tool tự lo: ghi `<brain>/memory/facts/<slug>.md` **chữ thường** (luật "Linux đọc chữ M hoa là
thư mục khác" biến mất), dựng frontmatter `type/created/updated`, thêm đúng một dòng vào
`memory/MEMORY.md`, và **tự phát hiện trùng** rồi cập nhật file cũ thay vì đẻ bản sao.

Retire: **2.297 ký tự**.

### `javis_create_plugin`

Ép sẵn `enabled: false`, đòi khai `min_mode` tường minh, và **trả về câu nhắc về
`JAVIS_ENABLE_USER_PLUGINS`** trong kết quả tool thay vì bắt model nhớ nói.

Retire: **2.114 ký tự**.

## Hợp đồng 4: khối điều kiện

Server không đoán, nó **biết**. Năm khối này lắp theo sự thật đã có sẵn: không truy xuất, không
rủi ro, không vòng tool.

| Sự thật | Khối | Ký tự | Server biết ở đâu |
|---|---|---:|---|
| Có file đính kèm | `blocks/files-attached.md` | 2.272 | `has_attachments`, `main.py:12175` |
| Có khối `[FILE ĐANG MỞ]` | `blocks/open-file.md` | 676 | server tự chèn khối đó |
| Pack CRM đã cài | `blocks/customer-inbox.md` | 329 | `packs_store` |
| Có MCP số liệu | `blocks/data-cache.md` | 824 | `javis_connections` |
| Phiên dev trên repo | (về `CLAUDE.md`) | 1.005 | không còn liên quan |

Lượt không khớp điều kiện nào trả **0 ký tự** cho cả năm.

## Hợp đồng 5: xếp khối theo độ ổn định

Thứ tự lắp là một phần của hợp đồng. Tài liệu API nói rõ:

> "Caching is a prefix match. Any byte change anywhere in the prefix invalidates everything
> after it. Render order is `tools` → `system` → `messages`. Keep stable content first, put
> volatile content after the last `cache_control` breakpoint."

Nên:

```
┌─ NHÂN                     không đổi giữa các lượt, không đổi giữa các brain
├─ BỘ NHỚ (chỉ mục ngắn)    đổi khi có ký ức mới
├─ KHỐI ĐIỀU KIỆN           đổi khi điều kiện đổi, không đổi theo lượt
│  ═══ RANH GIỚI CACHE: cache_control đặt ở ĐÂY ═══
├─ ĐỒNG HỒ, NGÔN NGỮ, KÊNH  đổi mỗi lượt
└─ CÂU HỎI
```

Hôm nay khối đồng hồ (`context_compiler.dong_ho`) đã nằm ở cuối `build_system_prompt`, tức
đúng chiều. Việc cần làm là đặt `cache_control` đúng ranh giới thay vì bọc cả khối system.

### Ba điều phải nói thẳng về cache

**Một: cách tốt hơn cho khối đổi mỗi lượt.** Tài liệu API mô tả một cơ chế first-class:

> "Mid-conversation operator instructions (Claude Opus 5, Opus 4.8, Fable 5/5.1; **not Sonnet
> 5**; no beta header): append `{"role": "system", ...}` to `messages[]` instead of editing
> top-level `system`. Preserves the cached history prefix and is the prompt-injection-safe
> operator channel."

Tức đồng hồ, khối kênh và khối điều kiện nên đi vào `messages[]` dưới dạng system message
giữa hội thoại, thay vì nối vào `system` ở trên. Như vậy tiền tố cached **không bị đụng tới
chút nào**. Ràng buộc: phải đứng sau một message `user`, và phải là entry cuối hoặc được theo
sau bởi một lượt `assistant`; không được là `messages[0]`. Model-gated, nên cần đường lui cho
model không hỗ trợ.

**Hai: cắt quá tay có thể giết cache.** Tài liệu ghi: *"Minimum cacheable prefix is
model-dependent (512-4096 tokens) - shorter prefixes silently won't cache."*

Nhân 6.000 ký tự ≈ 1.180 token. Cộng bộ nhớ và khối điều kiện thì tiền tố khoảng 2.500 token,
tức **có thể vẫn trên ngưỡng, nhưng không chắc với mọi model**. Đây là cái vách thứ tư ở Phần
5, và nó là bẫy của chính kế hoạch này.

**Cách kiểm, bắt buộc làm ở việc 5 của lộ trình:** đọc `usage.cache_read_input_tokens` qua vài
lượt liên tiếp. Bằng 0 nghĩa là cache không chạy.

**Ba: phạm vi.** Toàn bộ lập luận cache chỉ áp cho engine API. Với Claude Code, Codex và `agy`,
Javis không điều khiển cache, CLI và nhà cung cấp tự lo. Với đúng những bộ não hay bị than là
chậm, thứ quyết định là Vách 1 (trần argv), không phải cache.

## Hợp đồng 6: nhân đúc sẵn theo chữ ký

`build_system_prompt` cache theo chữ ký, đúng khuôn `plugins_host._signature` đã chạy tốt:

```python
sig = (mtime kernel.md, mtime blocks/, mtime policies/, mtime MEMORY.md,
       chữ ký cây skill (system_sync._mirror_signature, stat-only),
       brain, lang, project_id, session_id, bộ điều kiện đang bật)
```

Hai cái lợi, và cái thứ hai quan trọng hơn:

1. Bỏ ~40 ms chặn event loop mỗi lượt
2. Tiền tố gửi đi **giống nhau tới từng byte** giữa các lượt, nên prompt cache ăn chắc chứ
   không ăn nhờ may

## Hợp đồng 7: `MEMORY.md`

Cùng đường phân đôi, khác thuốc, vì bộ nhớ không được phép vắng mặt.

| | Hôm nay | Sau |
|---|---|---|
| Tính cách người dùng (xưng hô, vai trò, ngành, mục tiêu) | Lẫn trong 20.000 | **~800 ký tự, luôn có mặt** |
| Chỉ mục fact (bề mặt) | Cùng chỗ, bị cắt khi đầy | Trần 3.000, mỗi fact 1 dòng ~60 ký tự → ~50 fact, **không cắt dòng nào** |
| Chi tiết fact | Nhét sẵn trong chỉ mục | Nạp khi liên quan |

Nghe ngược đời nhưng đúng: **trần mới 3.000 chứa được nhiều fact hơn trần cũ 20.000**, vì trần
cũ gánh cả chi tiết. Và bậc "mất trí nhớ" trong `_fit_memory_index` biến mất.

---

# Phần 10: Lộ trình

Thứ tự có ràng buộc thật, không xếp theo cảm tính. Ba luật thứ tự:

- **Chặn nguồn phình trước dọn hậu quả** (việc 1, 2 trước mọi thứ)
- **Lan can trước khi rút bất cứ luật nào** (việc 3 chặn cứng việc 6 tới 9, xem Phần 8)
- **Hai hằng số của Antigravity phải sửa cùng nhau** (việc 4, xem Phần 4.1)

| # | Việc | Nghiệm thu | Công |
|---|---|---|---|
| 1 | Tách `CLAUDE.md` (dev repo) và `system/prompt/kernel.md` (sản phẩm) | Chat của người dùng cuối không còn "Dev conventions". Claude Code trên repo vẫn đọc được quy ước | 0,5 ngày |
| 2 | Đóng băng trần nhân 8.000 + bảng phân bổ ký tự trên trang Chẩn đoán | Test canh `kernel.md`, test thứ hai canh **tổng đã lắp**. Trang Chẩn đoán hiện ký tự từng khối | 1 ngày |
| 3 | **XONG: `pre_tool_call` phủ quyết được** (`plugins_host.py`) | Hook trả `{"deny": "lý do"}` thì tool không chạy, model nhận đúng câu đó. Hook lỗi thì tool VẪN chạy (fail-open) | 0,5 ngày |
| 4 | ~~`AGY_BOOTSTRAP_MAX_CHARS` 100.000 → 80.000~~ **XONG: → 45.000** (số thật sau khi đo sysprompt 46.179) | `test_ba_loi_tran_prompt.py` | ✅ |
| 5 | Bốn khối điều kiện + dời `cache_control` + **kiểm `cache_read_input_tokens`** | Lượt không đính kèm giảm đúng 2.272 ký tự. Cache read khác 0 qua 3 lượt liên tiếp | 1,5 ngày |
| 6 | Rút luật code đã ép + thêm `enforced_by` vào mọi file luật | Ba đoạn "hứa suông" (2.403) còn 1 dòng. Test: `enforced_by` khác trống phải trỏ tới symbol có thật | 0,5 ngày |
| 7 | `javis_remember` | Retire 2.297. Ghi thử 60 ký ức, `MEMORY.md` không mất dòng nào | 1 ngày |
| 8 | `javis_create_agent`, `javis_create_workflow` + lan can hook | Retire 2.875 + 1.726. Ghi thẳng vào `Javis/agents/` bị chặn kèm giải thích | 2 ngày |
| 9 | `javis_create_plugin` | Retire 2.114 | 1 ngày |
| 10 | Tách Orchestration thành policy | Retire ~8.000. Nhân dưới 6.500 | 2-3 ngày |
| ~~11~~ | ~~Nhân đúc sẵn theo chữ ký~~ **RÚT LẠI** | Đo được 3,9 ms chứ không phải 40 ms (xem 4.5). Lý do CPU không còn | - |
| ~~12~~ | ~~`cache_ttl="1h"`~~ **RÚT LẠI** | TTL 1 giờ tốn 2x ghi và chỉ đúng cho khoảng cách 5-60 phút (xem 4.6). Mặc định 5m đang đúng | - |
| 13 | `MEMORY.md` tách chỉ mục và chi tiết | Bậc cắt dòng không còn với 50 fact | 2 ngày |
| 14 | **XONG một nửa:** xếp theo mức hay dùng + cắt theo ngân sách ký tự. Top-k theo `capability_index` để sau | `test_ba_loi_tran_prompt.py` | ✅ |
| 15 | `/luat-moi` phân loại tại nguồn | Lệnh chạy 4 câu hỏi và dựng khung file ở đúng carrier | 1 ngày |

**Việc 15 không phải phần thưởng cuối, nó là thứ giữ cho 14 việc trên không trôi lại.** Nếu
viết luật đúng chỗ vẫn đắt hơn viết vào nhân thì độ dốc còn nguyên.

## Kết quả dự kiến, nói theo phân phối

Không nói một con số, vì một con số là cách làm người đọc quyết định sai.

| | Hôm nay | Sau |
|---|---:|---:|
| Câu hỏi thường (p50) | 33.577 | **~6.000** |
| Có file đính kèm (p80) | 33.577 | ~8.300 |
| Đang tạo agent, tool trong phạm vi (p95) | 33.577 | ~7.000 |
| Xấu nhất (p99) | 33.577 | ~11.000 |
| Vòng inference thêm mỗi lượt | 0 | **0** |
| Antigravity trên Linux phải đi đường file | **Luôn luôn** | Chỉ khi hội thoại rất dài |
| Trần số luật | ~33.600 ký tự | **Không có** |

Dòng p95 là chỗ khác hẳn phương án "nén bằng truy xuất": khi model **đang làm** việc cần luật,
chi phí vẫn thấp hơn hôm nay, vì hợp đồng tool cô đọng hơn prose giải thích cách dùng
primitive.

---

# Phần 11: Test và rào

| Test | Canh cái gì |
|---|---|
| `test_prompt_budget` (sửa) | `kernel.md` <= 8.000. **Số này không được nâng**; nâng phải kèm xoá |
| `test_prompt_assembled` (mới) | Tổng đã lắp <= 14.000 cho mọi tổ hợp điều kiện |
| `test_rule_provenance` (mới) | Mọi file luật có `id`, `group`, `description` <= 150, `added`, `because`. `enforced_by` khác trống phải trỏ tới symbol có thật |
| `test_kernel_no_surface` (mới) | Nhân không chứa tên engine, tên connector, đường dẫn file cụ thể |
| `test_hook_veto` (mới) | Hook trả `deny` thì tool không chạy; hook lỗi thì tool VẪN chạy |
| `test_agy_argv_fit` (mới) | `AGY_BOOTSTRAP_MAX_CHARS` + trần nhân, quy ra byte tiếng Việt, phải dưới `_tran_argv()` Linux với biên 3% |
| `test_tool_retire` (mới) | Với mỗi tool trong bảng retire, `kernel.md` không còn chứa các cụm khoá của mục đã rút |

Hai test đáng giá nhất:

- **`test_kernel_no_surface`** biến Hằng số 1 từ một lời hứa thành một thứ CI kiểm được. Nó đỏ
  ngay lần đầu có người viết "Antigravity" hay "agents/" vào nhân.
- **`test_agy_argv_fit`** là thứ ngăn đúng cái lỗi ở Phần 4.1 tái diễn: hai hằng số ở hai file
  khác nhau, không ai đặt cạnh nhau, và hậu quả thì im lặng.

---

# Phần 12: Rủi ro và đường lui

| Rủi ro | Mức | Cách lui |
|---|---|---|
| Model không gọi tool mới, vẫn ghi file thô | Cao lúc đầu | Lan can hook + hậu kiểm `collect_turn_files`. Đo tỉ lệ gọi tool 1 tuần trước khi rút prose |
| Rút luật ra rồi model làm sai việc đó | Trung bình | **Chạy song song**: giữ prose đồng thời tạo tool, đo 1 tuần, **tỉ lệ dùng tool dưới 98% thì không cắt** (căn cứ ở Phần 8) |
| Cắt quá tay làm tiền tố tụt dưới mức tối thiểu, cache im lặng ngừng chạy | Trung bình | Kiểm `usage.cache_read_input_tokens` ở việc 5. Bằng 0 qua 3 lượt là dấu hiệu |
| Ba tool mới đẩy brain vượt ngưỡng lazy 40 | Thấp | Đo `pool_chars` trước và sau. Ngưỡng nằm ở `config.py:228`, chỉnh được |
| Tool mới làm mất linh hoạt | Trung bình | Primitive vẫn còn. Tool là đường trải nhựa, không phải cái lồng |
| Nhân đúc sẵn trả bản cũ sau khi sửa skill | Thấp | Chữ ký gồm mtime cây skill, đúng khuôn `plugins_host._signature` |
| Hook phủ quyết chặn nhầm | Thấp | Fail-open khi hook lỗi. Allowlist đường dẫn tường minh, không suy ngầm |
| Việc 14 (bỏ `SKILL_LIST_MAX`) làm route trượt | Trung bình | Làm sau cùng, và chỉ khi `miss_class` trên trang Chẩn đoán có dữ liệu |

**Điều kiện dừng:** bất kỳ việc nào trong 7 tới 10 mà sau 1 tuần chạy song song, tỉ lệ model
dùng đường tool **dưới 98%** thì không cắt prose, quay lại sửa mô tả tool trước.

---

# Phần 13: Những thứ CỐ Ý không làm

Ghi lại vì mỗi cái đều từng được cân nhắc rồi bị loại có lý do.

- **Không xây tầng truy xuất policy mới.** Cơ chế đã có (lazy tool pool, `skill_router`,
  `javis_use_skill`) và đã đo được. Thêm tầng thứ bảy lên một chồng sáu tầng chưa có baseline
  production là lặp lại đúng sai lầm đã dẫn tới đây.
- **Không cấu hình embedding cho `capability_index`.** Khung RRF đã sẵn. Bật khi `miss_class`
  báo cần. Phần lớn luật kích hoạt bằng **cấu trúc** (có biểu thức thời gian, có ý định tạo)
  chứ không bằng từ vựng, nên embedding giải một bài toán mà chúng không có.
- **Không xây cơ chế ghim policy theo phiên.** Chỉ cần khi luật sống trong policy body. Đưa
  luật vào hợp đồng tool thì phạm vi tool đã ổn định sẵn cả phiên.
- **Không để model tự gọi `javis_use_skill` làm đường CHÍNH.** Nó là một vòng inference đầy đủ,
  tức 30 tới 60 giây trên engine CLI. Nó là lưới an toàn cho ca truy xuất trượt.
- **Không cấm `Write` native cho chat của chủ.** Quá tay. Dùng hậu kiểm thay vì cấm.
- **Không nâng trần nhân.** Chạm 8.000 là tín hiệu có luật bề mặt lọt vào nhân, không phải tín
  hiệu trần quá nhỏ.

---

# Phụ lục A: định tuyến `CLAUDE.md` hiện tại

| Mục | Ký tự | Đích | Ghi chú |
|---|---:|---|---|
| Orchestration | 8.888 | Tool + nhân | Thang quyết định 5 dòng vào nhân (~700). Báo kết quả → server tự gắn `chat_id`. Ba mức quyền → tham số tool. Luật Zalo → mô tả `zalo_send_message`. Hứa suông → `background_status` đã ép |
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

**Tổng vào nhân: ~5.000 tới 6.500 ký tự.**

---

# Phụ lục B: mọi hằng số và loại của nó

| Hằng số | Ở đâu | Loại | Ảnh hưởng |
|---|---|---|---|
| `_tran_argv` 120.000 / 30.000 | `antigravity_cli.py` | **Vách** | Vượt là thêm 1 vòng inference, 30-60 giây |
| `AGY_BOOTSTRAP_MAX_CHARS` 100.000 → **45.000** | `compaction.py` | **Vách** (qua trần argv) | Đã sửa. Số 45.000 đến từ sysprompt ĐO THẬT 46.179, không phải ước lượng 36.000 |
| `lazy_threshold` 40 / `lazy_char_budget` 6000 | `config.py:228` | **Vách** hai chiều | ~10.000 ký tự, đổi lấy khả năng thêm 1 vòng tool |
| Mức tối thiểu để cache 512-4096 token | API | **Vách** | Dưới ngưỡng thì cache im lặng không chạy |
| `cache_ttl` giữ 5 phút | `engine.py:320` | **Vách** theo thời gian | KHÔNG đổi: 1 giờ tốn 2x ghi, chỉ đúng cho khoảng cách 5-60 phút |
| `SUBSCRIPTION_THREAD_MAX_TOKENS` 1M | `compaction.py:73` | Vách | Xoay mạch, mồi lại transcript |
| Trần nhân 8.000 | (mới) | Dốc | ~130 ms so với 6.000. Tồn tại vì **kỷ luật**, không vì tốc độ |
| `MEMORY_INDEX_MAX` 20.000 → 3.000 | `main.py:523` | Dốc | Lý do là **gọn và rẻ**, KHÔNG phải "đang mất ký ức" (xem đính chính 4.4) |
| Trần tổng đã lắp 14.000 | (mới) | Dốc | Thước đo, không phải công tắc hiệu suất |
| `SKILL_LIST_MAX` 20 → **40** + `SKILL_LIST_CHAR_BUDGET` 4.000 | `skill_router.py` | **Trần ẩn** | Đã sửa: xếp theo mức hay dùng trước khi cắt, nên cái bị cắt không còn là cái tên vần cuối |
| Ngưỡng dừng khi rút prose 98% | (mới) | **Quyết định** | Đặt 90% là lỗ ròng, xem Phần 8 |

---

# Tóm tắt một đoạn

Vấn đề không phải luật quá nhiều, mà là **model có quá nhiều bậc tự do thừa, và viết prose là
cách rẻ nhất để đánh thuế lên chúng**. Kế hoạch này đổi giá: làm cho việc đặt luật đúng carrier
rẻ ngang việc nhồi vào nhân, đóng băng trần nhân để buộc phải chọn, và bắt mọi luật khai người
thi hành để luật nào code đã ép thì tự động bị xoá khỏi prompt.

Về hiệu suất, điều quan trọng nhất phải nhớ: **thứ quyết định không phải vài nghìn ký tự trên
dốc, mà là đứng đúng bên của vài cái vách.** Cái vách đắt nhất là trần dòng lệnh của
Antigravity, và nó chỉ vượt qua được khi sửa `AGY_BOOTSTRAP_MAX_CHARS` **cùng lúc** với thu nhỏ
nhân. Sửa một cái là không đủ.

Repo đã tự chứng minh mệnh đề trung tâm: `javis_schedule` có tool nên tốn ~600 ký tự prose,
trong khi tạo agent không có tool nên tốn 2.875 ký tự cho một việc đơn giản hơn. Thứ còn thiếu
không phải kiến trúc, mà là một quy trình buộc phải rút prose khi tool ra đời.
