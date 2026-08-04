# Đề xuất: đấu 9Router vào trang Models

Nhiều khách hàng hỏi Javis có dùng được API của 9Router không. Tài liệu này là bản đào trước
khi làm: 9Router thật ra là cái gì, đấu vào Javis thì vướng chỗ nào, có mấy đường đi.

## TRẠNG THÁI: GÁC LẠI, KHÔNG LÀM (chốt 2026-08-04)

Chủ repo đọc xong và quyết định **không làm**, giữ tài liệu để đó. Lý do, ghi nguyên ý:

> Tạm thời không phù hợp. Nó không thực tế và chỉ hợp với những người muốn rẻ. Javis sắp lên
> môi trường doanh nghiệp nên không cần dùng trộn như vậy.

Lý do này **bền hơn bản thân 9Router**, nên đọc kỹ trước khi mở lại đề xuất nào cùng dạng:

- **Hướng sản phẩm là doanh nghiệp.** Doanh nghiệp mua sự ổn định và một đường trách nhiệm rõ
  ràng, không mua việc ghép nhiều tài khoản rẻ lại với nhau. Một tính năng mà giá trị cốt lõi
  của nó là "tiết kiệm tiền bằng cách trộn nguồn" thì đang kéo sản phẩm về đúng nhóm khách
  ngược với hướng đang đi.
- **Trộn nguồn tự động chống lại thứ doanh nghiệp cần nhất: biết chắc mình đang chạy gì.**
  Điểm bán hàng của 9Router là tự nhảy sang nhà cung cấp khác khi hết quota. Với người dùng cá
  nhân đó là tiện. Với doanh nghiệp thì đó là "không ai biết câu trả lời vừa rồi do model nào
  sinh ra, dữ liệu đi qua đâu" - một câu hỏi kiểm toán không trả lời được.
- **Nó đòi một tiến trình chạy trên máy người dùng.** Thêm một thứ có thể tắt, và Javis không
  quản được.

**Điều này KHÔNG có nghĩa là mọi thứ trong tài liệu vô dụng.** Ba phần vẫn dùng lại được nếu
sau này có nhu cầu khác:

- Mục 2 (bức tường "localhost trên VPS không phải máy người dùng") áp cho **mọi** đề xuất đấu
  một dịch vụ chạy tại máy: LiteLLM, vLLM, Ollama máy nhà, one-api.
- Mục 3 (rủi ro mất tool calling trong im lặng) áp cho **mọi** nhà cung cấp mới. Đây là phép
  thử nên chạy trước khi nhận bất kỳ endpoint lạ nào.
- Mục 6 (danh sách chỗ phải chạm khi thêm một nhà cung cấp) là bản đồ dùng được ngay cho lần
  thêm nhà cung cấp tiếp theo, bất kể là ai.

Phần còn lại của tài liệu giữ nguyên như lúc trình, không sửa lại cho hợp với kết luận.

---

## 1. 9Router là cái gì, nói cho đúng

**Nó KHÔNG phải một dịch vụ trên mạng để mua API key.** Đây là chỗ dễ hiểu nhầm nhất, và hiểu
nhầm chỗ này thì cả kế hoạch sai theo.

So sánh cho dễ hình dung:

| | OpenRouter (Javis đang có) | 9Router |
|---|---|---|
| Chạy ở đâu | Máy chủ của họ, trên Internet | **Máy của chính người dùng** |
| Địa chỉ | `https://openrouter.ai/api/v1` cố định, ai cũng như ai | `http://localhost:20128/v1`, mỗi người một chỗ |
| API key lấy đâu | Đăng ký ở openrouter.ai | Tự sinh trong bảng điều khiển 9Router của chính mình |
| Trả tiền cho ai | Trả OpenRouter | 9Router **miễn phí vĩnh viễn**, tiền trả thẳng cho các nhà cung cấp bên dưới |
| Cài thế nào | Không phải cài gì | `npm install -g 9router` hoặc chạy Docker |

Nói cách khác: 9Router là **một cái tổng đài đặt tại nhà**. Người dùng khai vào đó các tài
khoản họ đang có (gói Claude Code, gói ChatGPT, Copilot, GLM, MiniMax, các nhà cung cấp miễn
phí như Kiro hay OpenCode), rồi 9Router đứng ra nhận yêu cầu và tự chọn đường rẻ nhất còn
quota. Hết quota chỗ này thì nó tự nhảy sang chỗ khác, không đứt việc giữa chừng.

Hai thứ khiến người ta thích nó:

- **Tự chuyển tiếp khi hết quota** (họ gọi là "combo": một danh sách model xếp theo thứ tự ưu
  tiên, cái đầu hết lượt thì rơi xuống cái sau).
- **Nén token (RTK)**, họ công bố giảm 20-40% token đầu vào bằng cách lọc bớt phần thừa trong
  kết quả tool trước khi gửi đi.

Mặt kỹ thuật, phần Javis cần biết:

```
POST http://localhost:20128/v1/chat/completions
Authorization: Bearer <api key của chính người dùng>
{"model": "cc/claude-opus-4-6", "messages": [...], "stream": true}

GET  http://localhost:20128/v1/models     → trả model + combo, định dạng OpenAI
```

Định dạng **giống hệt OpenAI**, tên model có tiền tố nhà cung cấp (`cc/`, `glm/`, `kr/`...).
Đây là tin tốt: Javis đã có sẵn cả một đường xử lý cho endpoint kiểu OpenAI (OpenRouter,
Groq, Gemini, Ollama đều đi chung đường đó).

---

## 2. Vướng ở đâu: đúng cái tường Javis đã đâm vào một lần rồi

Ở bản **0.16.1**, Javis **cố ý bỏ** khả năng đấu Ollama bản chạy máy nhà, chỉ giữ Ollama
Cloud. Lý do ghi thẳng trong mã (`server/engine.py:310`, `server/config.py:61`):

> Javis CỐ Ý chỉ đấu bản Cloud: bản chạy trên máy nhà đòi một ô địa chỉ riêng, tức một ca đặc
> biệt duy nhất xuyên suốt lớp nhà cung cấp, trong khi phần đông người dùng Javis chạy nó trên
> VPS - nơi "localhost" là chính cái container chứ không phải máy họ.

9Router vấp **đúng hai điều đó**:

1. **Nó đòi thêm một ô địa chỉ.** Tám nhà cung cấp hiện tại chỉ cần một ô API key, địa chỉ là
   hằng số trong mã. 9Router là cái đầu tiên mà mỗi người một địa chỉ.
2. **`localhost` trên VPS không phải máy người dùng.** Javis của anh chạy trên VPS. Người dùng
   cài 9Router trên máy tính cá nhân của họ. Javis gọi `http://localhost:20128` là gọi vào
   chính cái container Javis, ở đó không có gì cả. Đây không phải lỗi có thể vá, đây là địa lý
   mạng.

Nên câu hỏi thật không phải "code thế nào" mà là: **người dùng của anh chạy Javis ở đâu?**

| Người dùng chạy Javis | 9Router chạy ở đâu | Đấu được không |
|---|---|---|
| Máy cá nhân (Windows, `setup.bat`) | Cùng máy đó | **Được**, `localhost:20128` đúng nghĩa |
| VPS | Máy cá nhân của họ | **Không**, trừ khi họ mở 9Router ra Internet |
| VPS | Cùng VPS đó | **Được**, nhưng họ phải tự cài thêm 9Router lên VPS |

Ô địa chỉ vẫn phải có trong cả ba trường hợp, vì cổng và máy chủ mỗi người một khác.

---

## 3. Rủi ro lớn nhất, và nó không nằm ở chỗ ai cũng nghĩ

Rủi ro không phải "kết nối không được". Kết nối được thì rất dễ thấy. Rủi ro là **kết nối
được nhưng Javis mất năng lực mà không ai biết**.

Javis sống bằng **gọi tool**: đọc MCP, ghi file vault, giao việc Kanban, chạy skill. Bỏ tool
đi thì Javis chỉ còn là một khung chat.

Mà 9Router **không ghi một chữ nào về tool calling** trong toàn bộ tài liệu công khai của họ
(em đã đọc README 54KB, trang setup guide, và trang chủ). Không ghi không có nghĩa là không
có, nhưng cũng không có nghĩa là có.

Có một suy luận mạnh nghiêng về "có": tài liệu của họ hướng dẫn trỏ **Claude Code**, Cursor,
Cline, Codex vào 9Router. Bốn công cụ đó không chạy nổi một giây nếu thiếu tool calling. Nên
gần như chắc chắn 9Router có chuyển tiếp `tools`.

Nhưng **suy luận không đủ để phát hành**, và còn một tầng rủi ro nữa sâu hơn:

> Điểm bán hàng của 9Router là **tự nhảy sang nhà cung cấp khác khi hết quota**. Không phải
> model nào cũng hỗ trợ tool calling. Nếu cú nhảy rơi trúng một model không có tool, Javis sẽ
> nhận lời rồi trả về một câu trả lời chay - không gọi MCP, không ghi file, không báo lỗi.

Đây đúng loại hỏng mà repo này ghét nhất và đã vá một lần ở 0.17.1: *"engine sẽ TỰ TIN nhận
lời rồi im lặng không làm gì. Người dùng ngồi đợi một việc không bao giờ chạy, và không có một
dòng lỗi nào ở đâu cả."*

Nên nếu làm, **bắt buộc phải có một lớp phát hiện**: gửi một tool giả, xem model có gọi lại
không; không gọi thì nói thẳng với người dùng là combo hiện tại không dùng tool được, đừng để
họ tự phát hiện sau ba ngày.

---

## 4. Ba đường đi

### Đường A - Nhà cung cấp mới `9router`, có ô địa chỉ riêng (đề xuất chọn)

Thêm một mục vào trang Models như OpenRouter, khác ở chỗ có **hai ô**: địa chỉ máy chủ và API
key. Địa chỉ mặc định điền sẵn `http://localhost:20128/v1` để người chạy máy cá nhân chỉ việc
dán key.

- **Được**: đúng cái khách hàng hỏi, dùng lại gần hết đường xử lý OpenAI-compat sẵn có.
- **Mất**: phá vỡ luật "mọi nhà cung cấp chỉ cần một ô key" - đây chính là điều 0.16.1 tránh.
  Nhưng lần này có lý do khác hẳn Ollama: **khách hàng đang hỏi**, còn Ollama máy nhà thì
  không ai hỏi.
- **Khối lượng**: vừa. Ước lượng ở mục 6.

### Đường B - Gộp vào một mục chung "Máy chủ tương thích OpenAI"

Thay vì làm riêng cho 9Router, làm **một** nhà cung cấp tên "Máy chủ OpenAI-compat" nhận địa
chỉ + key. Đấu được 9Router, LiteLLM, Ollama máy nhà, vLLM, one-api, và bất kỳ thứ gì sau này.

- **Được**: một ca đặc biệt duy nhất, dùng được cho cả một họ sản phẩm chứ không riêng một cái
  tên. Nếu 9Router mai kia hết thời thì công sức không mất.
- **Mất**: người dùng phải tự biết mình đang đấu cái gì; không có hướng dẫn riêng cho 9Router
  nên người mới sẽ lúng túng hơn. Không "trả lời đúng câu hỏi của khách" bằng đường A.
- **Dung hoà**: làm đường B ở tầng dữ liệu, nhưng trong kho connector có sẵn một **mẫu
  9Router** điền sẵn địa chỉ và hướng dẫn. Người dùng vẫn thấy chữ "9Router", còn mã thì
  không có ca đặc biệt nào.

### Đường C - Không đấu, hướng dẫn dùng qua Claude Code

9Router đã hỗ trợ trỏ Claude Code vào nó. Về lý thuyết người dùng có thể cấu hình Claude Code
trỏ vào 9Router rồi Javis dùng Claude Code như bình thường.

- **Được**: không viết dòng code nào.
- **Mất**: rất mong manh. Javis quản vòng đời Claude Code khá sâu (đăng nhập, model, MCP,
  phiên) nên chen một proxy vào giữa dễ vỡ ở chỗ khó lần. Và nó không trả lời được câu hỏi của
  khách: họ muốn thấy 9Router **trong trang Models**.

**Đề xuất của em: đường B kèm mẫu 9Router điền sẵn.** Cùng công sức nhưng mở ra cả một họ, và
không để lại một ca đặc biệt mang tên một sản phẩm bên thứ ba trong lớp nhà cung cấp.

---

## 5. Phải kiểm chứng TRƯỚC khi viết code

Bốn câu hỏi này chưa có câu trả lời chắc chắn, và cả bốn đều đổi thiết kế nếu trả lời khác đi.
Kiểm bằng cách cài 9Router lên một máy rồi chạy vài lệnh, khoảng 30 phút.

1. **Có chuyển tiếp `tools` không?** Gửi một request kèm `tools` và xem có `tool_calls` trong
   phản hồi không. Nếu KHÔNG thì dừng cả đề xuất, vì Javis không dùng được.
2. **Có streaming kèm tool không?** Javis chạy chữ dần từng chữ. Nếu bật `stream: true` mà tool
   gãy thì phải rơi về chế độ không stream, và điều đó phải nói trước cho người dùng.
3. **`GET /v1/models` trả về hình dạng gì?** Trang Models của Javis liệt kê model động. Cần
   biết combo hiện ra thế nào để phân biệt với model thường.
4. **Combo nhảy sang model không có tool thì sao?** Đây là rủi ro ở mục 3. Cách kiểm: dựng một
   combo có model không hỗ trợ tool ở vị trí thứ hai, ép hết quota cái đầu, xem chuyện gì xảy ra.

Lệnh kiểm nhanh câu 1 và 3, chạy trên máy đã cài 9Router:

```bash
KEY=<key lấy trong dashboard 9router>
BASE=http://localhost:20128/v1

curl -s $BASE/models -H "Authorization: Bearer $KEY" | head -40

curl -s $BASE/chat/completions -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" -d '{
  "model": "<điền tên model hoặc combo>",
  "messages": [{"role":"user","content":"Mấy giờ rồi? Dùng tool đi."}],
  "tools": [{"type":"function","function":{"name":"gio_hien_tai",
    "description":"Trả về giờ hiện tại","parameters":{"type":"object","properties":{}}}}]
}' | python -m json.tool
```

Thấy `tool_calls` trong kết quả là qua cửa. Không thấy thì dừng.

---

## 6. Nếu làm thì đụng những đâu

Ghi ra đây để anh thấy khối lượng thật, không phải để làm ngay.

**Tầng nhà cung cấp (phần chính)**

- `server/config.py` - thêm ô key + ô địa chỉ vào cấu hình, thêm vào danh sách che secret
  (dòng 374), thêm mồi model.
- `server/engine.py` - địa chỉ dựng từ cấu hình chứ không hằng số hoá; thêm vào bảng
  `endpoints` (dòng 613); hàm stream; hàm vòng lặp tool (`*_chat_with_mcp`).
- `server/aux_engine.py` - thêm vào `API_PROVIDERS` và `_KEY_FIELD` để việc nền định tuyến được.
- `server/main.py` - `/provider/models` hỏi `GET /v1/models` của người dùng;
  `_WORKFLOW_ROUTABLE_PROVIDERS`; `_TG_PROVIDERS` (nút chọn model trên Telegram).
- `server/usage_index.py` - thêm vào `_API_PROVIDERS` để tính token.
- `server/connect_health.py` - thăm dò sức khoẻ; **thêm nhánh riêng cho lỗi "không nối được
  địa chỉ"**, vì đây là nhà cung cấp đầu tiên mà lỗi mạng là chuyện thường ngày (máy tắt, đổi
  cổng, VPS không thấy máy nhà).

**Giao diện**

- `dashboard/console.js` - `KEYFIELD` (dòng 3066), `MCP_PROVIDERS` (4060), `_UZ_PROV` (372),
  bảng nhãn engine (4438). Cộng thêm **ô địa chỉ**, thứ chưa nhà cung cấp nào có, nên form
  trang Models phải mở rộng chứ không chỉ thêm một dòng.
- `dashboard/usage.js`, `dashboard/app.js` - nhãn.

**Lớp an toàn mới (không có sẵn, phải viết)**

- Kiểm tool calling lúc bấm Kết nối: gửi tool giả, không thấy gọi lại thì cảnh báo ngay tại
  màn hình kết nối chứ không để phát hiện muộn.
- Rào địa chỉ: chỉ cho `http://` khi trỏ vào máy nội bộ; trỏ ra Internet thì phải `https://`,
  kẻo API key đi qua mạng dưới dạng trần.

**Tài liệu**

- `docs/10-models-va-engine.md` - mục mới, kèm nói thẳng chuyện VPS không thấy máy nhà.
- `CLAUDE.md` - câu "**Tám** bộ não hiện dùng được..." phải sửa. Câu đó xuất hiện trong system
  prompt mỗi lượt chat nên sai là Javis nói sai với mọi người dùng.

**Ước lượng**: khoảng một bản nhỏ (kiểu 0.19.0), phần lớn công sức nằm ở lớp an toàn và giao
diện có ô địa chỉ, chứ không nằm ở việc gọi API.

---

## 7. Điều em KHÔNG khuyên làm

- **Đừng ghim `localhost:20128` làm mặc định rồi thôi.** Nó đúng cho máy cá nhân và sai cho
  mọi bản chạy VPS. Phải có ô địa chỉ thật, và phải có câu giải thích ngay cạnh ô đó.
- **Đừng hứa "tự tiết kiệm 20-40% token".** Con số RTK là của 9Router công bố, Javis không đo
  được và không kiểm soát được. Nói lại con số của người khác như thể của mình là chỗ mất uy
  tín rẻ tiền nhất.
- **Đừng để 9Router thành nhà cung cấp mặc định.** Nó phụ thuộc một tiến trình chạy trên máy
  người dùng; tiến trình đó tắt là Javis chết mà người dùng không hiểu vì sao.

---

## 8. Cần anh chốt ba điều

1. **Đường A hay đường B?** (Em nghiêng B: một mục "Máy chủ OpenAI-compat" kèm mẫu 9Router
   điền sẵn, mở ra cả họ thay vì một cái tên.)
2. **Khách hàng của anh chạy Javis ở đâu?** Nếu phần lớn chạy VPS thì giá trị thật của tính
   năng này thấp hơn nhiều so với vẻ ngoài, và nên nói trước với họ thay vì làm xong mới biết.
3. **Ai chạy được bước kiểm chứng ở mục 5?** Cần một máy cài 9Router. Máy dựng của em không
   cài được (không có tài khoản nhà cung cấp nào để khai vào 9Router).

Trả lời xong ba câu đó là bắt tay được ngay.

> **Ba câu trên đã hết hiệu lực.** Đề xuất bị gác lại ở mức cao hơn: không phải chọn sai đường
> mà là không đi hướng này. Xem mục Trạng thái ở đầu tài liệu.
