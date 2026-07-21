# Kế hoạch: Kho Kết nối (MCP Hub) + Agent độc lập engine

> Bản kế hoạch dev, viết 2026-07-04 trên nền code v0.8.13. Mục tiêu: nâng cấp toàn bộ trải nghiệm MCP của Javis và tách Javis khỏi sự phụ thuộc cấu trúc Claude Code.

## 1. Mục tiêu (3 việc)

1. **Kho MCP mẫu (catalog)**: người dùng mở trang, thấy sẵn Pancake POS, Zalo, Botcake, Webcake Landing... bấm "Kết nối" là xong. Không phải tự gõ URL, transport, header như hiện nay.
2. **Một connector nối được NHIỀU tài khoản** (multi-account kiểu Hermes): cùng Pancake POS nhưng 3 cửa hàng, cùng Zalo nhưng 2 tài khoản. Mỗi tài khoản đăng nhập dễ như Claude: dán key hoặc quét QR hoặc bấm OAuth, có xác nhận "Đã kết nối: <tên shop>".
3. **Mọi engine đều dùng được mọi thứ**: MCP, skill, loop, đọc/ghi file chạy như nhau dù Main Model là Claude Code, Codex, OpenRouter, OpenAI API hay Anthropic API. Javis là agent thực thụ, Claude Code chỉ là MỘT trong các bộ não.

## 2. Hiện trạng (đọc code ngày 2026-07-04)

Phần đã có và giữ lại được:

- `server/mcp_store.py`: registry server phẳng (name/transport/url/headers/env), sinh `.mcp_config.json` cho `claude --mcp-config`, sinh profile toml cho Codex, có deny_tools + strict mode. Multi-shop giải quyết bằng cách nhân bản dòng cùng URL khác header.
- `server/mcp_client.py`: MCP client tự viết (Streamable HTTP, JSON-RPC), cho engine API (OpenRouter/OpenAI) chạy vòng tool-calling. Namespacing `ten-server__ten-tool` đã có.
- UI trang MCP trong `dashboard/console.js` (renderMcp, ~dòng 1399): form kỹ thuật + khu ambient (MCP sẵn của Claude Code, chỉ xem).

Khoảng trống so với mục tiêu:

- Không có catalog: mọi thứ nhập tay, người thường không làm nổi.
- Multi-account là "mẹo" (nhân bản dòng), không phải mô hình chính thức: không gom nhóm theo connector, không label tài khoản, không mặc định tài khoản nào.
- Client tự viết chỉ HTTP: KHÔNG stdio (nên Zalo CLI local chỉ chạy được qua Claude Code), KHÔNG OAuth, mỗi tool call mở session mới (chậm, docs phải xin lỗi "tin nhắn đầu hơi chậm").
- OAuth MCP đẩy sang `claude mcp add` + bắt user mở terminal gõ `/mcp`: chỉ chạy máy có màn hình, chỉ engine Claude Code. Đây là chỗ "bám Claude Code" nặng nhất.
- Engine matrix lệch (docs/10): Anthropic API chat thuần không MCP; ChatGPT OAuth (responses) không MCP; skill + loop chỉ Claude Code; engine API không có tool file.
- Secrets nằm plaintext trong `mcp_servers.json` (gitignored nhưng vẫn plaintext).

## 3. Kiến trúc đích: JAVIS MCP HUB

Ý tưởng trung tâm: mọi engine đấu vào MỘT điểm duy nhất do Javis làm chủ. Hub lo kết nối, tài khoản, quyền, log. Engine chỉ thấy "một MCP server tên javis".

```
Claude Code  --mcp-config 1 entry --\
Codex        profile toml 1 entry ---+--> [ JAVIS MCP HUB ] --> Pancake POS (shop A) (shop B)
Engine API   gọi in-process --------/          |               --> Zalo (TK 1) (TK 2)
                                               |               --> Botcake, Webcake, ...
                              catalog + permission + audit + cache + OAuth token store
```

Lợi ích của việc dồn về 1 điểm:

- Multi-account routing, đặt tên tool, quyền, log gọi tool: làm MỘT lần, mọi engine hưởng.
- OAuth: hub giữ token và tự refresh, engine nào cũng dùng được (kể cả Claude Code, vì hub chỉ là 1 MCP http với nó). Bỏ hẳn cảnh "mở terminal gõ /mcp".
- 3 mức quyền loop (suggest/auto/full) được ENFORCE tại hub (chặn tool ghi thật sự) thay vì chỉ nhờ prompt như hiện nay.

### 3.1 Mô hình dữ liệu: Connector (mẫu) tách khỏi Connection (tài khoản)

**Connector** = mẫu trong catalog, đi theo app, versioned:

```json
// system/mcp-catalog.json (mảng connector)
{
  "id": "pancake-pos",
  "name": "Pancake POS",
  "icon": "pos.png",
  "category": "Bán hàng",
  "description": "Đơn hàng, doanh thu, khách hàng, tồn kho từ Pancake POS.",
  "transport": "http",
  "url": "https://mcp-pos.pancake.biz/mcp",
  "auth": {
    "type": "apikey",
    "fields": [{ "key": "api_key", "label": "API key của cửa hàng", "header": "Authorization: Bearer {api_key}" }],
    "guide": "Vào Pancake POS > Cài đặt > Ứng dụng & API > tạo API key.",
    "guide_url": "https://docs.pancake.biz/pos/st-f13/st-p2?lang=vi"
  },
  "validate": { "tool": "pos_shop", "label_from": "$.name" },
  "tool_meta": {
    "write": ["pos_order", "pos_purchase", "pos_transaction", "pos_debt", "pos_voucher", "pos_promotion"],
    "danger": ["pos_transaction"]
  },
  "default_perm": "readonly"
}
```

- `auth.type`: `apikey` | `oauth` | `qr` | `none`. Field khai báo sẵn nên UI tự dựng form, user không bao giờ thấy chữ "header".
- `validate`: sau khi nhập key, hub gọi ngay 1 tool đọc để (a) xác nhận key đúng, (b) tự đặt label tài khoản (tên shop). Đây chính là cảm giác "dễ như Claude": dán key xong thấy "Đã kết nối: Kim Khí Hà Lộc".
- `tool_meta`: phân loại đọc/ghi/nguy hiểm theo connector (chính xác hơn heuristic WRITE_HINTS hiện tại; heuristic giữ làm fallback cho custom).
- Catalog nạp từ app + cho phép refresh từ remote (GitHub raw) để thêm connector mới KHÔNG cần release app.

**Connection** = một tài khoản cụ thể của user, lưu ở `server/mcp_servers.json` (nâng schema, migration tự động):

```json
{
  "id": "abc123",
  "connector_id": "pancake-pos",
  "label": "Kim Khí Hà Lộc",
  "secrets": { "api_key": "<mã hoá>" },
  "config": {},
  "enabled": true,
  "perm": "readonly",
  "is_default": true
}
```

- Migration: dòng server cũ nào khớp URL catalog thì gán `connector_id` tương ứng, còn lại gán `custom` (custom connector = connector do user tự khai, form nâng cao giống Add custom connector của Claude, giữ nguyên năng lực hiện có).
- Secrets mã hoá at rest (Fernet, key sinh theo máy lưu ngoài file registry). Che secrets trong log và API trả về (đã có `_public`, giữ).

### 3.2 Hub runtime (nâng cấp mcp_client.py)

- **Session pool**: giữ session MCP sống giữa các tin nhắn (giữ `Mcp-Session-Id`, dùng chung `httpx.AsyncClient`), tools/list cache theo TTL, health check nền. Hết cảnh "mỗi tin nhắn kết nối lại nên chậm".
- **stdio support**: spawn tiến trình con, JSON-RPC qua stdin/stdout. Đây là điều kiện để Zalo CLI (và mọi MCP local) chạy được cho engine API chứ không riêng Claude Code.
- Khuyến nghị: chuyển client sang **SDK chính thức `mcp` (Python)** thay vì tự bảo trì protocol. SDK có sẵn Streamable HTTP + stdio + auth flow; phần server (aggregator) dùng luôn FastMCP hoặc tự viết mỏng trên FastAPI. Đỡ nợ kỹ thuật khi protocol lên phiên bản.

### 3.3 Aggregator: hub xuất hiện như MỘT MCP server

- Endpoint `POST /hub/mcp` (Streamable HTTP) ngay trên FastAPI đang chạy, bind localhost.
- `.mcp_config.json` của Claude Code và profile toml của Codex chỉ còn MỘT entry trỏ về hub (kèm token nội bộ chống tiến trình lạ trên máy gọi vào).
- Đặt tên tool: connector có 1 connection thì giữ tên gọn `pos__pos_order`; nhiều connection thì `pos_kim-khi-ha-loc__pos_order`. Kèm meta-tool `javis_connections` (liệt kê connector + tài khoản + quyền) để model tự biết đang có nguồn nào.
- Tuỳ chọn chống phình context khi user đấu nhiều connector: chế độ "lazy tools" (chỉ expose meta-tool `search_tools` + `run_tool`, kiểu Composio). ĐÃ LÀM (v0.9.146): `mcp_hub._apply_lazy` giấu tool pool (tool MCP có route entry `conn`) sau `javis_search_tools`/`javis_run_tool`, builtins + plugin vẫn hiện; tự bật khi số tool MCP vượt `settings.mcp.lazy_threshold` (mặc định 40), ép bật/tắt bằng `settings.mcp.lazy_tools`. Áp trong `discover_all` nên mọi engine (Claude Code, Codex, API) hưởng chung; quyền/audit giữ nguyên vì `run` đi qua `call_route` route đầy đủ.

### 3.4 Quyền tập trung tại hub

- Mỗi connection có `perm`: `readonly` (chỉ tool đọc) | `safe` (thêm ghi nháp, chặn danger) | `full`. Suy từ `tool_meta`, một toggle trên UI thay vì bắt user gõ tên tool cần chặn như hiện nay. `deny_tools` thủ công vẫn giữ cho power user.
- Loop mode map thẳng vào hub: loop `suggest` gọi hub với ngữ cảnh chỉ-đọc (hub từ chối mọi tool ghi bất kể connection perm), `auto` chặn nhóm danger, `full` theo perm của connection. An toàn thành lớp cứng, không còn phụ thuộc prompt.
- Audit log: mọi tools/call ghi lại (connection, tool, args rút gọn, kết quả ok/lỗi, thời gian) vào SQLite/JSONL, xem được từ UI.

### 3.5 OAuth do Javis tự lo (bỏ phụ thuộc claude mcp add)

- Implement chuẩn MCP Authorization (OAuth 2.1 + PKCE + Dynamic Client Registration): bấm "Kết nối" mở browser, callback về `http(s)://<dashboard>/connect/oauth/callback`, hub lưu + tự refresh token, gắn vào header khi gọi server.
- Chạy được cả trên VPS vì callback đi qua chính URL dashboard user đang mở (không cần terminal, không cần màn hình máy chủ).
- Server OAuth từ đó dùng được cho MỌI engine (hiện tại: chỉ Claude Code). Đường `claude mcp add` native giữ làm fallback một thời gian rồi gỡ.

## 4. UX trang "Kết nối" (thay trang MCP hiện tại)

Đổi nhãn menu: MCP -> **Kết nối** (phụ đề "Nguồn dữ liệu & công cụ"). Chữ MCP chỉ còn trong phần nâng cao.

Bố cục 2 khu + giữ khu ambient:

1. **Đã kết nối**: mỗi connector 1 card, trong card là các chip tài khoản: `● Kim Khí Hà Lộc (mặc định) | ● Shop B | + Thêm tài khoản`. Mỗi chip mở menu: đổi tên, đặt mặc định, test lại, chỉ đọc (toggle), tắt/bật, xem log, xoá.
2. **Kho kết nối**: grid card từ catalog (icon, tên, mô tả 1 dòng, badge "API key" / "OAuth" / "QR Zalo"), ô tìm kiếm, lọc theo nhóm. Cuối grid: card "Tự thêm (nâng cao)" = custom connector, giữ form cũ.
3. **MCP từ Claude Code** (ambient): giữ nguyên, chỉ xem.

Flow thêm tài khoản theo auth type:

- **apikey**: modal 1 ô dán key + dòng hướng dẫn lấy key ở đâu (text + link docs của hãng) -> bấm Kết nối -> hub validate ngay (gọi tool xác minh) -> hiện "✓ Đã kết nối: <tên shop>" và tự điền label -> chọn quyền (mặc định theo catalog, POS mặc định chỉ đọc). Sai key thì báo lỗi tại chỗ, kèm gợi ý.
- **oauth**: bấm Kết nối -> mở tab đăng nhập của hãng -> quay lại thấy account đã vào danh sách.
- **qr** (Zalo): modal hiện mã QR (Javis spawn CLI login, bắt QR đưa lên UI), poll trạng thái tới khi "✓ Đã đăng nhập: <tên Zalo>". Kèm cảnh báo rủi ro bắt buộc đọc (xem mục 6).
- Sau connection ĐẦU TIÊN của user: chạy 1 câu demo ngay trong trang ("Hôm nay bán được bao nhiêu?") để chứng minh giá trị tức thì.

Nguyên tắc: người thường không bao giờ thấy URL/transport/header. Kỹ thuật chỉ hiện trong "Tự thêm (nâng cao)" và khi mở chi tiết connection.

## 5. Engine parity: agent thực thụ trên mọi bộ não

Ma trận đích (hiện tại -> đích):

| Năng lực | Claude Code | Codex | OpenRouter/OpenAI API | Anthropic API |
|---|---|---|---|---|
| MCP | ✓ (giữ, qua hub) | ✓ http -> ✓ hub (cả stdio) | ✓ (nhanh hơn nhờ pool) | ✗ -> ✓ (tool loop mới) |
| Skill | ✓ native | ✗ -> ✓ (skill router) | ✗ -> ✓ (skill router) | ✗ -> ✓ |
| File vault | ✓ | ✓ | ✗ -> ✓ (built-in tools) | ✗ -> ✓ |
| Loop/agent/workflow | ✓ | một phần | ✗ -> ✓ | ✗ -> ✓ |

Việc cụ thể:

1. **Anthropic API tool loop**: viết `anthropic_chat_with_mcp` trong `engine.py` (Anthropic Messages API có tool use, pattern y hệt `openai_chat_with_mcp`). Việc nhỏ, giá trị ngay: gỡ dòng "Anthropic API = chat thuần" khỏi docs.
2. **Built-in tools cho engine API**: bộ tool file sandbox trong vault (read/list/write/append theo perm), đưa vào cùng vòng tool-calling với tool MCP. Từ đó loop/task/workflow chạy được trên engine API.
3. **Skill router mọi engine**: inject danh sách skill (name + description từ `.claude/skills/*/SKILL.md`) vào system prompt + meta-tool `use_skill(name)` trả về nội dung SKILL.md khi model kích hoạt (progressive disclosure, đúng cách Claude Code làm nhưng do Javis tự làm nên engine nào cũng chạy).
4. **Loop/agent/workflow nhận provider API**: trường `model` của agent mở rộng nhận cả provider API; runner map qua Engine interface chung.
5. Chuẩn hoá interface `Engine` (capabilities: native_mcp, native_skills, file_tools...) để chỗ gọi không if/else theo tên engine rải rác như hiện nay; badge engine trên UI đọc từ capability thật.

ChatGPT OAuth (responses API) không nhận function tool: giữ nguyên chiến lược đi qua Codex CLI, không cố ép.

## 6. Bốn connector cài sẵn đợt đầu

1. **Pancake POS** (chắc chắn nhất): endpoint `https://mcp-pos.pancake.biz/mcp` + API key, đã chạy thực tế. Việc còn lại: viết entry catalog + validate qua `pos_shop` + tool_meta phân loại đọc/ghi + multi-shop thành multi-connection chính thức. Docs: https://docs.pancake.biz/pos/st-f13/st-p2?lang=vi
2. **Webcake Landing**: hãng đã có MCP ("Để AI tự thiết kế & sửa landing page bằng lời nói"). Cần mở trang docs đầy đủ để lấy endpoint + cách phát key chính xác (trang là SPA, fetch tự động chỉ ra tiêu đề). Docs: https://docs.pancake.biz/landing/st-f7/st-p3?lang=vi
3. **Botcake**: trang docs đang nói chiều "Botcake AI đi tiêu thụ MCP server". Cần xác minh Botcake có EXPOSE MCP cho bên ngoài không; nếu chỉ có JSON API (mục Developer) thì viết wrapper MCP mỏng trong repo (`server/connectors/botcake_mcp.py`, mount vào hub như connector nội bộ). Pattern wrapper này tái dùng cho mọi dịch vụ chỉ có REST API. Docs: https://docs.pancake.biz/botcake/st-f2/st-p10/st-s2?lang=vi
4. **Zalo** (zalo-agent-cli, npm): CLI không chính thức trên zca-js, đăng nhập QR, hỗ trợ SẴN đa tài khoản + proxy riêng từng tài khoản (khớp mô hình connection), có MCP mode từ v1.2.0 (4 tools: đọc tin, gửi tin, liệt kê thread, đánh dấu đã đọc) và 15+ nhóm lệnh CLI. Catalog entry: transport stdio, command `zalo-agent-cli` (verify cú pháp chạy MCP + flag chọn account khi làm), auth type `qr`.
   - BẮT BUỘC hiển thị cảnh báo: API không chính thức, tài khoản có thể bị Zalo khoá. Mặc định `readonly` (đọc tin); gửi tin phải chủ động nâng quyền và xác nhận rủi ro. Thêm rate limit tại hub cho connector này.

## 6b. Đợt 2 - ba connector quảng cáo (research 2026-07-04, ship 0.9.2)

1. **Meta Ads (chính chủ)**: remote MCP `https://mcp.facebook.com/ads`, OAuth chuẩn MCP (đúng flow oauth_mcp của hub - không cần dev app/token). Open beta từ 29/04/2026, MỞ DẦN theo từng ad account, yêu cầu account thuộc Business Manager. 29 tool: đọc (`ads_get_*`, `ads_insights_*`, `ads_catalog_get_*`), ghi catalog (`ads_catalog_create`), nguy hiểm tiền thật (`ads_create_campaign/_ad_set/_ad`, `ads_update_entity`, `ads_activate_entity`). Guardrail phía Meta: entity tạo qua MCP luôn PAUSED. 3 scope tier chọn lúc đăng nhập (read-only / read-write / financial). Chưa test được live vì cần đăng nhập Facebook thật - validate + label tự động sẽ chạy lần kết nối đầu của user.
2. **Google Ads (chính chủ)**: local stdio, repo `googleads/google-ads-mcp` (KHÔNG có bản PyPI dùng được - gói PyPI cùng tên là placeholder 0.0.1). Chạy `uvx --from git+https://github.com/googleads/google-ads-mcp.git google-ads-mcp` - ĐÃ TEST THẬT trên Windows: server "Google Ads Server" v3.4.2, initialize + tools/list OK trong <90s (khớp timeout init của mcp_client). Tên tool THẬT có prefix namespace: `customers_list_accessible_customers`, `search_search`, `metadata_get_resource_metadata` (docs chỉ ghi tên không prefix). Read-only by design. Auth: developer token (API Center của MCC, mức Explorer đủ) + GCP project bật Google Ads API + ADC (gcloud auth application-default login --scopes=adwords,cloud-platform --client-id-file=oauth-client.json) - user dán nội dung file ADC, mcp_store ghi ra file + gán env GOOGLE_APPLICATION_CREDENTIALS. Qua agency/MCC thì thêm GOOGLE_ADS_LOGIN_CUSTOMER_ID.
3. **TikTok Ads (cộng đồng, chờ chính chủ)**: TikTok công bố MCP chính chủ tại TikTok World 13/05/2026 nhưng tới 07/2026 CHƯA GA (chưa có endpoint public; trang docs portal v1.3 là SPA chưa đọc được nội dung). Chọn gói PyPI `tiktok-ads-mcp` (ysntony, v0.1.4): stdio `uvx tiktok-ads-mcp` - ĐÃ TEST THẬT: 6 tool đều read-only, tên thật có hậu tố `_tool` (`get_authorized_ad_accounts_tool`, `get_campaigns_tool`, `get_reports_tool`...). Auth stateless dán thẳng env TIKTOK_APP_ID / TIKTOK_SECRET / TIKTOK_ACCESS_TOKEN (token Marketing API long-term không tự hết hạn) - hợp mô hình connection đa tài khoản. Đã CÂN NHẮC và LOẠI repo `AdsMCP/tiktok-ads-mcp-server` (user gửi link): không có trên PyPI (phải clone), auth OAuth tương tác qua tool trong chat, token lưu trong process không rõ persistence - không hợp hub. Khi TikTok mở bản chính chủ: thay entry `tiktok-ads` sang endpoint chính chủ (giữ id để connection cũ migrate được).

Kèm theo 0.9.2: callback `/connect/oauth/callback` sau khi đổi token thành công giờ tự gọi validate để đặt label (tên tài khoản ads) nếu label còn là tên mặc định, và ghi codex profile ngay (trước đây sót).

## 6c. Đợt 3 - Google Calendar + Gmail chính chủ (research 2026-07-04, ship 0.9.3)

Google đã ra MCP chính chủ dạng REMOTE cho Workspace, mỗi dịch vụ 1 endpoint (đã probe thật):
- Calendar `https://calendarmcp.googleapis.com/mcp/v1` - 8 tool: đọc (list_events, get_event, list_calendars, suggest_time), ghi (create_event, update_event, respond_to_event), nguy hiểm (delete_event).
- Gmail `https://gmailmcp.googleapis.com/mcp/v1` - 12 tool: đọc (list_drafts, get_thread, search_threads, list_labels), ghi (create_draft, create_label, *label*). ĐÁNG CHÚ Ý: KHÔNG có tool gửi thư - chỉ tạo nháp + gắn nhãn. An toàn tự nhiên.
- Drive `https://drivemcp.googleapis.com/mcp/v1` cũng có (chưa thêm đợt này).

Đặc điểm auth (khác Meta): initialize + tools/list trả 200 KHÔNG cần token; chỉ tools/call mới 401 kèm `WWW-Authenticate: Bearer resource_metadata=".../.well-known/oauth-protected-resource/<tool>"`. Resource metadata ở `/.well-known/oauth-protected-resource/mcp/v1` -> `authorization_servers: ["https://accounts.google.com/"]` + scopes_supported. accounts.google.com KHÔNG có registration_endpoint -> **không DCR** -> flow oauth_mcp cũ (chỉ DCR) không dùng được.

Giải pháp (0.9.3): thêm nhánh EXPLICIT trong `oauth_mcp.start_auth`. Connector khai sẵn `auth.authorize_url` + `token_url` + `scopes` + `authorize_params` + fields client_id/client_secret (BYO). Khi có authorize_url+token_url -> bỏ discover/DCR, đọc client BYO từ `mcp_store.connection_secrets(conn_id)`, dựng URL với scopes khai sẵn + `access_type=offline&prompt=consent` (BẮT BUỘC để Google phát refresh_token; thiếu là chết sau 1h). handle_callback + _refresh gửi kèm client_secret (Google Web app là confidential client). Tự đặt tên tài khoản = email bóc từ id_token (scope openid+email). Nhánh DISCOVERY (Meta) giữ nguyên.

Tại sao chọn remote chính chủ thay vì connector `google-workspace` (workspace-mcp local, đã có): remote không cần uv/node, chạy VPS headless, OAuth qua redirect dashboard (không mở browser lúc gọi tool - workspace-mcp local mở browser lần đầu nên fail trên headless). workspace-mcp phơi 45 tool (phình context nặng); 2 connector focus chỉ 8 + 12 tool. Giữ google-workspace cho ai cần cả Drive/Docs/Sheets trong 1 mối.

CHƯA test được vòng OAuth end-to-end (cần OAuth client + đăng nhập Google thật của user). Đã test: probe endpoint + tool list thật, dựng URL authorize (unit test: offline/consent/scope/PKCE/không có param resource), bóc email id_token, phân loại quyền 17 case. User phải: tạo OAuth client "Ứng dụng web" trong GCP, thêm redirect `http://localhost:7777/connect/oauth/callback` (+ domain nếu VPS), bật Calendar API / Gmail API, thêm mình vào Test users.

## 7. Lộ trình (mỗi phase ship được, dùng được ngay)

**P0 - Nền hub (backend)**
- Schema connector/connection + migration từ registry cũ (không phá server đang chạy).
- `system/mcp-catalog.json` + loader (`server/mcp_catalog.py`), entry đầu: pancake-pos, zalo, custom.
- Nâng `mcp_client.py`: session pool + stdio (cân nhắc chuyển SDK `mcp`).
- Mã hoá secrets. Endpoint mới: `/connect/catalog`, `/connect/add`, `/connect/validate`, giữ `/mcp/*` cũ chạy song song.
- Xong khi: thêm connection Pancake POS qua API mới, validate trả về tên shop, chat hỏi số vẫn chạy trên cả Claude Code lẫn OpenRouter.

**P1 - UI Kho kết nối**
- `console.js`: renderMcp -> renderConnect (2 khu + ambient), flow apikey guided + validate + auto label, toggle chỉ đọc 1 chạm, test/health, multi-account chips, câu demo sau kết nối đầu.
- Cập nhật docs/09.
- Xong khi: người không biết kỹ thuật tự đấu được 2 shop Pancake POS trong dưới 2 phút, không thấy chữ URL/header.

**P2 - Aggregator + quyền tập trung**
- `/hub/mcp` streamable HTTP + token nội bộ; Claude Code và Codex config chỉ còn 1 entry trỏ hub; engine API gọi hub in-process.
- Enforce perm 3 mức + loop mode tại hub; audit log + màn hình xem log.
- Xong khi: tắt registry per-server cũ, mọi engine chạy qua hub, loop suggest bị hub chặn tool ghi thật sự (test cố tình gọi pos_order).

**P3 - OAuth + QR**
- OAuth 2.1 PKCE + DCR + refresh, callback qua dashboard; gỡ dần đường `claude mcp add`.
- Flow QR Zalo end-to-end (spawn CLI, bắt QR lên modal, poll, map account CLI -> connection).
- Xong khi: connector OAuth bất kỳ đăng nhập được từ dashboard trên VPS headless; Zalo quét QR xong nhắn thử 1 tin (perm full, có xác nhận).

**P4 - Engine parity**
- Anthropic API tool loop; built-in file tools; skill router `use_skill`; loop/agent/workflow nhận provider API; interface Engine + capability flags; cập nhật docs/10.
- Xong khi: đổi Main Model sang Anthropic API hoặc OpenRouter mà vẫn: gọi POS ra số, kích hoạt skill, chạy 1 loop nền.

**P5 - Mở rộng kho**
- Webcake Landing + Botcake (sau khi verify endpoint), Facebook Ads và các connector user hay cần; catalog refresh từ remote; lazy tools khi nhiều connector; cân nhắc kho cộng đồng.

Ghi chú thứ tự: P4 (mục 1: Anthropic tool loop) độc lập, làm chen bất cứ lúc nào. P1 phụ thuộc P0. P2 nên trước P3 để OAuth token chỉ phải cắm vào một chỗ (hub).

## 8. Rủi ro & câu hỏi mở

- **Zalo ban account**: rủi ro thật của zca-js. Giảm nhẹ: cảnh báo bắt buộc, mặc định readonly, rate limit, khuyến nghị dùng tài khoản phụ. Không bao giờ để loop mode auto/suggest gửi tin Zalo.
- **Endpoint Webcake Landing + Botcake chưa xác minh**: trang docs là SPA, cần mở bằng browser (hoặc user cung cấp) để lấy URL MCP + cách phát key trước khi viết entry catalog.
- **OAuth với dịch vụ KHÔNG theo chuẩn MCP** (vd Google API thô): chuẩn DCR không áp được, cần app đăng ký riêng. Hướng: ưu tiên remote MCP chuẩn; trường hợp đặc biệt hướng dẫn BYO client id, hoặc đi qua aggregator bên thứ ba (Composio) như connector tuỳ chọn.
- **Phình context khi nhiều connector**: perm + deny đã lọc bớt; ngưỡng lớn thì bật lazy tools (P5).
- **Tương thích ngược**: registry cũ phải migrate êm, `/mcp/*` cũ giữ tới khi UI mới ổn định; codex profile + empty-mcp fork học giữ nguyên hành vi.
- **Bảo mật hub endpoint**: `/hub/mcp` bind localhost + token nội bộ sinh mỗi lần chạy, tránh tiến trình khác trên máy gọi trộm (hub cầm toàn bộ key của user).
