# Kế hoạch: Tầng Gói mở rộng (Pack Layer) cho Javis OS

> Bản kế hoạch dev, viết 2026-09-03 trên nền code v0.55.7. Mục tiêu: đưa connector và plugin
> thành GÓI cài được lúc chạy (zip, URL hoặc repo riêng, và về sau là kho công khai), giữ
> nguyên lõi FastAPI. Kèm việc xoá kết nối cho sạch và một đợt đóng băng ngôn ngữ mã nguồn.

## Bối cảnh

Javis đã có nền. Vấn đề bây giờ không phải thiếu tính năng mà là **mọi năng lực mới đều phải đi qua một bản phát hành**. Đo trên repo:

- **524 lần bump VERSION trong 3 tháng** (tháng 7: 326, tháng 8: 181, tháng 9: 17).
- **60 lần trong số đó chỉ để sửa `system/mcp-catalog.json`**, tức thêm hoặc vá một connector.

Nguyên nhân nằm ở một dòng: `server/mcp_catalog.py:19` trỏ cứng vào đúng một file trong repo, `load()` ở `:35-50` không merge, không override, và không endpoint nào ghi được vào đó. Trên Docker cây code lại root-owned read-only (`Dockerfile:81,112`), chỉ `/data` ghi được. Nên thêm một kết nối nghĩa là ra bản mới, không có đường nào khác.

Plugin thì gần đích hơn nhiều. `server/plugins_host.py` (605 dòng) đã quét ba tầng, đã hot reload thật theo mtime (`_signature` :323-337), đã có cổng quyền chạy bằng code chứ không bằng prompt (`_make_call` :446-473). Thiếu đúng ba thứ: **không có đường cài, không có đường gỡ, và cổng env là bật-tất-cả-hoặc-tắt-tất-cả**.

Mục tiêu của kế hoạch này: một **gói (pack)** cài được lúc chạy từ file zip, từ URL hoặc repo riêng, và về sau từ một kho công khai. Giữ nguyên lõi FastAPI, không viết lại theo kiểu seam của deepseek-harness. Gỡ gói phải sạch, xoá kết nối phải sạch.

---

## Bốn thứ hỏng phát hiện được khi khảo sát

Đây là lỗi thật, đã tự kiểm chứng lại, không phải suy đoán. Ba cái đầu là tiền đề của kế hoạch nên phải sửa trước.

**1. Xoá kết nối đang để lại rác, trong đó có credential sống.**
`POST /connect/delete` (`main.py:3212-3221`) gọi `mcp_store.delete_connection` **trước** rồi mới `mcp_hub.invalidate_cache`, mà `invalidate_cache` (`mcp_hub.py:890-899`) lại lặp qua `list_connections()` để tìm session cần đóng. Hàng đã bị xoá nên session không bao giờ được đóng, tiến trình con stdio sống tới `_IDLE_TTL = 900` giây. Và `STATE_DIR/connector-home/` **không có ai xoá cả**: hai chỗ ghi (`mcp_store.py:428`, `zalo_login.py:161`), không chỗ nào xoá. Trên máy khảo sát lúc viết bản này có **5 thư mục `connector-home/zalo-*` mồ côi** trong khi không còn kết nối Zalo nào, một trong số đó chứa credential phiên đăng nhập.

**2. `safeHref` chặn nhầm, và ba chỗ render bỏ qua nó.**
`dashboard/console.js:156` chỉ nhận `^https?://`, nên `guide_url: "/static/docs/substack.html"` trong catalog trả về `#`: **link hướng dẫn Substack đang chết**. Nghiêm trọng hơn, ba chỗ render (`:4227`, `:4263`, `:4491`) nội suy thẳng `esc(con.guide_url)` vào `href=` mà không qua `safeHref`. `esc()` chỉ escape `& < > " '`, nên `javascript:` đi lọt. Hôm nay chưa khai thác được vì catalog do mình viết; ngày gói của người khác cấp được `guide_url` thì đó là XSS trên chính origin của dashboard.

**3. Hai hàm slugify lệch nhau, một cái ăn mất chữ Đ.**
`share_bundle.py:55 slugify` dùng NFKD rồi `encode("ascii","ignore")`, mà U+0111 (đ) không có phân rã NFKD nên bị **xoá thẳng**. Chạy thử: `"Đo lường doanh thu"` ra `"o-luong-doanh-thu"`. Đây là đường export/import agent, nên một vòng xuất rồi nhập lại là hỏng tên. `main.py:4567 _ascii_slug` làm đúng vì có `replace("đ","d")` tường minh.

**4. Bộ dò chatbot bí chỉ biết tiếng Việt.**
`chatbot_runtime.py:515 _DAU_BI` là 9 cụm tiếng Việt thuần. Chatbot phục vụ khách nói tiếng Anh sẽ **không bao giờ** bị ghi nhận là đang bí, tab bot-bí hiện trống trong khi bot đang hỏng. Đây là lỗi đúng nghĩa, chỉ khoác áo ngôn ngữ.

---

## Gói là gì

Một đơn vị. Một thư mục. Một manifest. Connector và plugin **dùng chung một định dạng**, chỉ khác nhau ở phần `provides:` nào được điền. Lý do: `meta-ads-graph` hôm nay đã là một tính năng bị chẻ làm hai hiện vật, dính nhau bằng chuỗi `CONNECTOR_ID = "meta-ads-graph"` viết cứng ở `system/plugins/meta-ads-graph/plugin.py:13`. Tách định dạng làm hai là hợp thức hoá cái lỗi đó.

```
STATE_DIR/packs/<id>/
    javis-pack.yaml       manifest, giữ nguyên văn tác giả viết
    pack.json             bản đã chuẩn hoá + kiểm, do trình cài ghi
    connectors/*.yaml     mỗi file một connector
    plugins/<slug>/       plugin.yaml + plugin.py, ĐỂ NGUYÊN TẠI CHỖ
    assets/               icon, phục vụ tại /packs/<id>/asset/<path>
    pages/                trang hướng dẫn
STATE_DIR/packs.json          sổ cài đặt
STATE_DIR/packs-state/<id>.json   sổ hiệu ứng (thứ ghi RA NGOÀI thư mục gói)
STATE_DIR/packs-staging/      file đã soi nhưng chưa cài, dọn sau 30 phút
```

**Quyết định làm cho việc gỡ trở nên khả thi:** plugin của gói nằm luôn trong `STATE_DIR/packs/<id>/plugins/<slug>/`, **không bao giờ copy** sang `STATE_DIR/plugins/`. Gỡ khi đó là `rmtree` cộng phát lại sổ hiệu ứng, chứ không phải đi diff.

### Manifest, spec 1

Khoá tiếng Anh toàn bộ ngay từ ngày đầu (đây là hợp đồng công khai mới). `name` và `description` là map đa ngôn ngữ.

```yaml
format: javis-pack
spec: 1                        # phiên bản SCHEMA, không phải phiên bản gói
id: acme.pos-vn                # ^[a-z0-9][a-z0-9._-]{0,63}$, bất biến, = tên thư mục
version: 1.0.0
name: {en: "Vietnam POS", vi: "POS Viet Nam"}
description: {en: "...", vi: "..."}
author: {name: "Acme", url: "https://acme.dev"}
license: MIT
icon: assets/pos.png           # CHỈ đường dẫn tương đối trong gói
category: sales                # slug tiếng Anh
category_label: {en: "Sales", vi: "Bán hàng"}
compat: {app: ">=0.57.0 <2.0.0"}   # kiểm lúc cài VÀ lúc khởi động
permissions:                   # KHAI BÁO của tác giả, để hiện trước khi cài. KHÔNG phải cưỡng chế.
  code: false                  # trình cài tự tính, không tin file
  network: ["api.pos.vn"]
  filesystem: none
provides:
  connectors: [connectors/pos.yaml]
  plugins: []
  assets: [assets/]
  pages: [{id: guide, file: pages/guide.md}]
update: {channel: manual, source: ""}
signature: {}                  # ĐỂ DÀNH, spec 1 chỉ kiểm có mặt
listing:                       # ĐỂ DÀNH cho chợ, trình cài bỏ qua
  price: {amount: 0, currency: VND, model: free}
  purchase_url: ""
  entitlement: {required: false, check_url: ""}
```

`plugin.yaml` cũ không có khoá `format:` được một shim ~20 dòng trong `packs.py` quy về `{spec: 0, id: <tên thư mục>, provides: {plugins: ["."]}}`. **Mọi plugin đang có, bundled lẫn của người dùng, chạy tiếp mãi mãi, không phải sửa một byte nào.**

Một file `connectors/pos.yaml` là **y nguyên** một phần tử của mảng `connectors[]` trong `system/mcp-catalog.json` hôm nay, thêm `category_key` và đường dẫn icon/guide tương đối.

### Hai điểm nút

Cả ba lượt phản biện đều xác nhận chỉ cần chạm hai chỗ:

- `mcp_catalog.load()` (`:35-50`): một lần đọc có cache theo mtime, trả `{id: connector}`. **Mọi** hàm phía sau (`get`, `public_catalog`, `build_headers`, `build_url`, `build_env`, `classify`, `allowed`, và `mcp_store.resolved()` :373-501) đều đã nhận connector dưới dạng **dict tham số**. Nên biến `load()` thành hàm merge là thay đổi khép kín.
- `plugins_host._iter_plugin_dirs` (`:170-182`): một tuple ba nguồn dedupe theo tên thư mục. Thêm nguồn thứ tư là chèn một phần tử, và `_signature()` vốn đã stat mọi `plugin.yaml`/`plugin.py` nó trả ra, nên **hot reload cho plugin của gói là miễn phí**.

**Luật chống deadlock:** `server/packs.py` chỉ import `config`, `secrets_store`, `fastyaml` và stdlib. Không bao giờ import `plugins_host`, `mcp_store`, `mcp_hub` hay `main`. Spec 1 **không có** `ctx.register_connector`, nên code của gói không thể quay ngược vào lớp merge catalog trong lúc `plugins_host._lock` (:57) đang bị giữ qua `reg(ctx)` (:403).

---

## Ranh giới tin cậy: "bề mặt thực thi", không phải "không có file .py"

Đây là điều chỉnh quan trọng nhất, và là lý do một kho công khai có thể an toàn.

`transport: stdio` chép `command`/`args` từ connector vào connection (`mcp_store.py:225-229`), rồi `mcp_client.py:216-220` spawn nó với `env = dict(os.environ)`, và `POST /connect/add` (`main.py:3112`) dial ngay. **Một gói không chứa một dòng Python nào vẫn chạy được `npx -y goi-doc-hai` với toàn bộ biến môi trường của server chỉ bằng một cú bấm.** Plugin `javis-connect` đã biết chuyện này và ép mọi kết nối stdio do model thêm về `enabled: False` (`plugin.py:224-228`).

Nên phân **ba bậc, do trình cài tự tính từ cây file đã giải nén, không tin lời tác giả khai**:

**Bậc DATA** - cài được không cần đồng ý chạy code:
transport `http`/`sse`; `url`/`url_template` **chỉ https cổng 443**, tên miền hiện lên màn hình xác nhận; `auth.type` là `apikey`/`none`/`oauth` với `provider` thuộc phương ngữ đã có (`meta`, `google`, `generic`); `tool_meta`, `validate`, `arg_rules`, `rate_limit`, `risk`; icon và trang hướng dẫn **chỉ đường dẫn trong gói** (icon `http://` bị từ chối vì đó là beacon nổ mỗi lần vẽ trang Kết nối); và `default_perm` bị **ép về `readonly`** cho mọi connector đến từ gói, người dùng tự nâng từng kết nối qua UI cũ nơi cảnh báo rủi ro đã có sẵn.

**Bậc CODE** - đòi đồng ý riêng từng gói, gắn với hash nội dung:
bất kỳ file `.py` nào; `transport: stdio` hoặc bất kỳ `command`/`args`; khối `env` tĩnh; `cred_dir`, `isolate_home`, `oauth_file`, `needs_local_browser`; `auth.exchange`.

**Gói chứa Python là chuyện BÌNH THƯỜNG, không phải ngoại lệ phải xin phép hai lần.** Chủ dự án chốt 2026-09-03: gói mở cho mã Python, vì chính chủ là người xem gói trước khi cài. Nên **cổng env `JAVIS_ENABLE_USER_PLUGINS` KHÔNG áp cho gói cài qua trình cài.** Việc này nhất quán chứ không phải nới lỏng, và lý do đáng viết ra:

Cổng env sinh ra để bịt đúng một lỗ: `STATE_DIR/plugins/` và `<brain>/plugins/` là thư mục **ghi được**, nên bất cứ thứ gì ghi được vào đó là chạy được code trong tiến trình server mà **không ai bấm gì cả** - kể cả một model đang thao tác file trong brain. Trình cài phá bỏ đúng điều kiện đó: có người bấm, có màn hình liệt kê từng file `.py` trước khi bấm, và có digest ghi lại để lần nạp sau đối chiếu. Ba thứ đó là cùng một loại bảo đảm mà cổng env cung cấp, chỉ chính xác hơn vì nó theo TỪNG gói thay vì bật-tắt-tất-cả.

Nên phân đường, không phân mức tin:

| Đường vào | Điều kiện chạy code |
|---|---|
| Cài qua trình cài (zip, URL, repo riêng, kho) | Đồng ý từng gói, gắn digest. **Không cần env.** |
| Thả tay thư mục vào `STATE_DIR/plugins/` hoặc `<brain>/plugins/` | Vẫn cần `JAVIS_ENABLE_USER_PLUGINS=true` như hôm nay |

Cổng env vì thế **không bị gỡ**, chỉ thôi chắn con đường vốn đã có người gác. Nó vẫn là đường cứu khi cần tắt sạch mọi plugin người dùng cài mà không vào được dashboard, và `JAVIS_DISABLE_PACKS` là công tắc tương ứng cho gói.

**TỪ CHỐI thẳng ở spec 1**, nêu đích danh trường sai:
`transport: internal` và khoá `internal:` (vì `mcp_client.py:37 _INTERNAL` là **allowlist bảo vệ** `importlib.import_module`, không phải bảng tra); `auth.type: qr` (Zalo là đường riêng); `provider` OAuth lạ; và **id connector trùng với catalog gốc hoặc với gói khác**. Không có `override: true` trong spec 1. Một luật này giết luôn đòn hiểm nhất: một gói ship `id: pancake-pos` kèm `url_template: https://evil.host/mcp` sẽ **âm thầm bẻ hướng một kết nối đang đăng nhập thật**, vì `mcp_store.py:383-388, 489-495` dựng lại url và header **từ connector** ở mỗi lần resolve.

**Ai tin nguồn nào là lựa chọn của người cài, và Javis phải cho họ thấy đủ để chọn.** Chính chủ review gói của chính mình thì đủ; nhưng khi có kho công khai, người fork Javis cài gói của người thứ ba, ở đó "tác giả đã review" không còn là bảo đảm cho họ. Nên gói mang **nhãn nguồn** (chính chủ / kho công khai / zip tự tải / repo riêng) hiện cạnh tên ở mọi chỗ, và màn hình đồng ý của gói chưa qua review nói dài hơn một dòng. Javis không thay người dùng quyết định tin ai; nó chỉ không được để họ bấm mà không biết mình đang bấm gì.

**Nói thẳng trên màn hình xác nhận, không làm mềm:** `min_mode` chỉ chặn cái **model** được gọi, không chặn cái `register()` được làm. `permissions.network` và `permissions.filesystem` là lời khai, không có tầng chặn. Không có sandbox. Câu chữ bắt buộc: **"Gói này chạy Python thật bên trong server Javis. Nó đọc được mọi khoá API, token và file mà Javis đọc được. Chỉ cài gói từ nguồn bạn tin."** Không icon ổ khoá.

---

## Ba sự thật khó nghe

Nói trước để không ai kỳ vọng sai.

**Một: chỉ 13 trong 29 connector hiện có diễn đạt được bằng gói DATA hôm nay**, không phải 24 như bản thiết kế đầu tiên tự nhận. Sau giai đoạn code pack là khoảng 25. Ba cái (`zalo` qr, `botcake` và `substack` internal) vĩnh viễn cần lõi. Con số này sẽ do `tests/python/test_pack_coverage.py` tự tính từ catalog và in lý do từ chối từng cái, chứ không chép tay, vì bản thiết kế đầu đã sai con số này 11 đơn vị.

**Hai: cái này KHÔNG rút ngắn vòng lặp của chính đội phát triển bao nhiêu.** Trong 60 commit chạm `system/mcp-catalog.json` gần đây, **41 cái đồng thời chạm `server/*.py`**, 18 chạm `tests/`, 17 chạm `console.js`. Tầng gói chỉ bỏ được bản phát hành cho những connector vốn đã không cần sửa server, tức đúng phần rẻ nhất. **Thứ chương trình này thật sự mua là gói của bên thứ ba và gói riêng của người phát hành**, chứ không phải giảm con số 60 kia.

**Ba: 29 connector gốc GIỮ NGUYÊN CHỖ trong `system/mcp-catalog.json`, nhưng phải gỡ được.** Đây là chỗ chủ dự án chỉnh lại bản đầu (2026-09-03): không xoá gì bây giờ, cũng không di chuyển dữ liệu, nhưng **code phải đúng cấu trúc để gỡ được**, vì đích đến là bao giờ có kho thì xoá bớt, để lại đúng bộ lõi mặc định và người dùng tự cài thêm.

Hai việc này khác nhau, và tách chúng ra là cả điểm cốt lõi: **di trú dữ liệu** (chẻ file catalog thành 29 gói rời) là việc đắt, gãy 18 file test đọc file đó bằng đường dẫn nguyên văn, và mua được đúng số không cho người dùng hôm nay. **Lớp gỡ được** thì rẻ, không đụng một byte nào của catalog, và mua ngay được thứ cần có: người dùng tắt bớt connector không dùng, và ngày xoá thật thì đường đã sẵn.

Nên làm lớp gỡ, đừng di trú. Xem mục "Bộ lõi và cái cài thêm" ngay dưới.

---

## Bộ lõi và cái cài thêm

Đích đến chủ dự án đặt ra: **bao giờ có kho thì xoá bớt, để lại đúng cấu trúc mặc định của Javis, còn lại người dùng tự chọn cài thêm plugin, skill hay kết nối.** Bây giờ chưa xoá gì, nhưng cấu trúc phải sẵn.

Cấu trúc đó chỉ cần một ý: **mọi năng lực mặc định đều gỡ được, và trạng thái "đã gỡ" ghi ở `STATE_DIR` chứ không sửa vào cây code.** Cây code là read-only trên Docker và bị `git pull` ghi đè trên bản native, nên đó là chỗ duy nhất trạng thái sống được qua một lần cập nhật.

Ba loại năng lực mặc định, ba chỗ ghi, một cách hiểu:

| Loại | Nằm ở đâu | Sổ ghi "đã gỡ" | Có sẵn chưa |
|---|---|---|---|
| Connector lõi (29 cái) | `system/mcp-catalog.json` | `STATE_DIR/core-off.json` khoá `connectors[]` | Chưa, làm ở Giai đoạn 1 |
| Plugin bundled (11 cái) | `system/plugins/<slug>/` | `STATE_DIR/plugins.json` khoá `removed[]` | Đã có `enabled`/`disabled`, thêm `removed` ở Giai đoạn 2 |
| Skill hệ thống (6 cái) | `.claude/skills/`, `system_sync` đồng bộ vào brain | `<brain>/skills/.disabled/` | **Đã chạy rồi** (`system_sync` tôn trọng nó) |

Ba luật đi kèm, và cả ba đều để tránh cùng một loại lời hứa sai:

1. **"Gỡ" khác "xoá file".** Với thứ ship kèm app, gỡ nghĩa là biến mất khỏi danh sách chính, khỏi mọi engine, khỏi prompt; file vẫn ở trong image. Xoá file thật thì trên Docker sẽ `EACCES`, còn trên bản native thì `git pull` sau đó mọc lại - một thứ "đã xoá" mà tự quay về thì tệ hơn một thứ đang tắt.
2. **Gỡ được thì cài lại được, bằng một cú bấm.** Đây là điều kiện để "gỡ" không đáng sợ, và cũng là điều làm nó khác xoá.
3. **Gỡ một connector lõi KHÔNG xoá kết nối đã đấu theo nó.** Kết nối là dữ liệu của người dùng; connector chỉ là cái khuôn. Gỡ khuôn mà kết nối còn thì kết nối thành **mồ côi**, và chốt mồ côi ở Giai đoạn 1 chính là thứ làm trạng thái đó an toàn thay vì âm thầm mất quyền. Giao diện hỏi thẳng: gỡ khuôn thôi, hay xoá cả kết nối.

Ngày xoá thật thì việc phải làm chỉ còn là chẻ `system/mcp-catalog.json` thành các gói rời và sửa 18 file test đang đọc nó bằng đường dẫn nguyên văn. Lúc đó là một lần cố ý, có kho để người dùng cài lại ngay, chứ không phải một lần vá vội giữa đường.

---

## Lộ trình

Mỗi giai đoạn merge riêng được, CI xanh, và tự nó đã có ích.

### Giai đoạn 0 - Xoá kết nối cho sạch (4 ngày)

Nửa còn lại của yêu cầu đặt ra, đồng thời là rò rỉ credential đang sống, đồng thời là tiền đề của việc gỡ gói. Làm trước và làm riêng.

- File mới `server/purge.py`, **chủ sở hữu duy nhất** của câu hỏi "một kết nối có thể để lại những gì". API: `plan_connection(cid)`, `async purge_connection(cid, mode="trash", purge_audit=False)`, `gc_trash(days=30)`. Mọi thao tác xoá đường dẫn đi qua một guard `_inside(path, base)` dùng `resolve()`, vì `config.home_dir` người dùng sửa được qua `POST /connect/update`, thiếu guard thì "xoá kết nối" thành `rmtree` tuỳ ý.
- `SessionPool.close_now(key)` mới trong `mcp_client.py` cạnh `invalidate` (:451-455): pop rồi **await** `obj.close()` để chạm `_kill_tree` (:308-338). `invalidate` là bắn-rồi-quên qua `_close_later`, đúng cho đổi cấu hình, sai khi sắp `rmtree`.
- Thứ tự cố định: **làm im** (`await close_now`) → **chụp lại** (dời vào `STATE_DIR/purge-trash/conn-<cid>__<ts>/` kèm `manifest.json`) → **gỡ** (`oauth_mcp.forget`, `connect_health.forget`, `mcp_hub.forget_rate` mới, `capability_registry.drop_source` mới xoá cứng, `purge_home_dir` mới, rồi `mcp_store.delete_connection`) → **invalidate** → **báo cáo**.
- `purge_home_dir`: đọc `config.home_dir` trước, thiếu thì glob theo tiền tố `connector-home/<connector_id>-<slug>*`, và từ chối mọi thứ trượt `_inside`. Hai chỗ ghi dùng hai dạng tên khác nhau nên suy từ id và slug là bỏ sót mọi thư mục do QR tạo, tức đúng 5 thư mục đang có trên máy khảo sát.
- Dòng audit **mặc định giữ lại**, chỉ xoá trường nhãn. Một nhật ký mà cái gói tự xoá được thì không còn là nhật ký. Có ô tick riêng để xoá hẳn.
- Nếu `pool.dang_goi_tool(spec)` đang true thì trả `{"ok": false, "busy": true}` và để UI nói ra, vì đóng session stdio là SIGKILL cả cây tiến trình có thể đang đặt đơn.
- Tách `_kill_tree` ra `server/winproc.py` và gọi từ `zalo_login.cancel` (:191-203), chỗ hôm nay chỉ giết `cmd.exe /c npx` mà bỏ sót tiến trình node thật đang giữ thư mục home.
- **Sửa `safeHref`** (`console.js:156`) nhận thêm đường dẫn cùng origin một dấu gạch đầu (không bao giờ `//`), và **cả sáu** chỗ render `guide_url` đi qua nó.
- Endpoint mới `GET /connect/purge-plan?id=`. Hộp xác nhận **vẽ từ chính cái plan** để lời cảnh báo không trôi lệch khỏi việc thật sự làm. Thêm trường `purge_warning` **trong catalog** (không phải trong JS), mục zalo ghi: "Xoá kết nối này là mất phiên đăng nhập QR. Muốn dùng lại phải mở app Zalo trên điện thoại quét mã lần nữa." Với connector có trường đó, nút chính là "Chuyển vào thùng rác 30 ngày", còn "Xoá hẳn ngay" bắt gõ đúng nhãn kết nối, theo đúng luật `confirm == name` của `/brains/delete` (`main.py:4517-4518`). Đưa "Tắt tạm" và "Đăng nhập lại" **lên trên** Xoá trong menu.

**Xong khi:** xoá một kết nối stdio đang sống thì `ps` thấy tiến trình con biến mất trong một giây chứ không phải 900. `server/connector-home/` không còn thư mục của nó, kể cả thư mục do QR tạo với `home_dir` tuỳ biến. Một test chụp `STATE_DIR`, thêm kết nối, dùng thử, xoá, rồi khẳng định diff rỗng ngoại trừ `mcp_audit.jsonl` và `logs/`. `purge_connection` trên kết nối có `home_dir` là `C:\` thì từ chối và thư mục đích còn nguyên. `javascript:...` ra `#` ở cả sáu chỗ render.

### Giai đoạn 1 - Sổ gói, lớp phủ catalog, và lớp gỡ được (4 ngày)

Chưa có UI cài, chưa chạm mạng. Thả một thư mục vào là connector hiện ra, không cần ra bản mới. Và connector lõi **tắt được**, tức cấu trúc gỡ được có mặt từ đây chứ không chờ tới kho.

- `server/packs.py` mới: `load_manifest`, `installed()`, `catalog_signature()`, `connector_layers()`, `plugin_dirs()` (tạm trả rỗng), `asset_path()`, `page_path()`, shim spec 0.
- Sửa `mcp_catalog.py`: khoá cache thành `(chữ ký file gốc, packs.catalog_signature())`; dựng `by_id` từ file gốc rồi phủ `connector_layers()` lên, gắn nhãn `_pack: "<id>"`. Import `packs` là lazy và bọc `try/except` để `packs.py` hỏng thì thoái về đúng hành vi hôm nay, khớp nhánh file-hỏng sẵn có ở `:46-48`.
- **Trùng id connector là từ chối, không bao giờ merge.** Kiểm id theo `_SLUG_RE` **trước khi** dựng bất kỳ đường dẫn nào từ nó: `mcp_catalog.py:44` hôm nay không kiểm gì, mà `mcp_store.py:301, 421, 428` nội suy id đó vào đường dẫn, một trong số đó dẫn tới `shutil.rmtree`.
- `public_catalog()` viết lại icon và guide tương đối thành `/packs/<id>/asset/...` **ở phía server**, nên `iconInner` (`console.js:4062-4075`, vốn đã route dấu `/` sang `<img>`) không cần đổi.
- `classify()` với entry có `_pack`: heuristic `WRITE_HINTS` thành **sàn** chứ không phải phương án dự phòng, tức gói chỉ được làm phân loại **chặt hơn**, không được nới.
- **Chốt mồ côi** (bắt buộc có trước khi bất cứ thứ gì gỡ được): `mcp_store.resolved()` :386-408 hôm nay chịu được `con = None` và im lặng bỏ header, env, cred_dir; tệ hơn, `mcp_hub._guard` khi đó gọi `allowed(None, perm, ...)` với `perm` mặc định `"full"` và hàm trả True vô điều kiện (`mcp_catalog.py:327-328`). Sửa: kết nối có `connector_id` không ai cung cấp bị đánh dấu mồ côi, `resolved()` từ chối dựng spec, và có quét lúc khởi động để hiện băng đỏ mời "Cài lại gói" hoặc "Xoá kết nối".
- `mcp_hub._store_mtime()` trả `max(mtime mcp_servers.json, mtime packs.json)`. Một lệnh `stat` thêm, đóng được ca thả tay trong TTL 60 giây sẵn có. **Không** đi quét mọi manifest trên đường nóng.
- `.gitignore` **và** `.dockerignore` thêm sáu đường mới, cập nhật `test_ignore_files.py`. Nhớ `STATE_DIR` mặc định là `server/` (`config.py:15`) nên trên bản native, gói rơi **vào trong cây git**. Thêm luôn `server/connector-cred/`, hiện không có trong file nào cả.
- Từ chối id gói trùng tên module top-level của `server/` (vì `server/` nằm trên `sys.path` và `__init__.py` là entry file hợp lệ).
- **LỚP GỠ ĐƯỢC cho connector lõi.** `STATE_DIR/core-off.json` dạng `{"connectors": ["tiktok-ads", "lark"]}`, đọc trong `packs.py` (cùng chỗ, cùng kiểu cache theo `(mtime_ns, size)`), và `mcp_catalog.load()` lọc chúng ra **sau** khi phủ gói. Ba điểm phải đúng:
  - Lọc ở `load()` chứ không ở `public_catalog()`: lọc ở chỗ hiển thị thì tool vẫn ra tới engine, tức "đã gỡ" là lời hứa sai. `load()` là nơi duy nhất mọi đường đi qua.
  - `catalog_signature()` gộp mtime của `core-off.json`, nên tắt một connector có hiệu lực ở lần load kế mà không phải khởi động lại.
  - Endpoint `POST /connect/core-toggle {id, off}`. Gỡ khuôn **không** xoá kết nối đã đấu theo nó: chúng thành mồ côi và chốt mồ côi ở gạch đầu dòng trên lo phần an toàn. API trả về số kết nối sẽ thành mồ côi để giao diện hỏi lại một câu.
  - Danh sách đã gỡ hiện ở một khu gập trên trang Kết nối, mỗi thẻ một nút Cài lại. Không xoá file trong `system/`, xem mục "Bộ lõi và cái cài thêm".

**Xong khi:** một thư mục gói mẫu trong `STATE_DIR` tạm làm `mcp_catalog.get("acme.pos-vn")` trả về connector, `public_catalog()` có nó với URL icon tuyệt đối, `POST /connect/add` tạo được kết nối thật, xoá thư mục thì nó biến mất ở lần load kế. Gỡ `tiktok-ads` thì `mcp_catalog.get("tiktok-ads")` trả `None`, thẻ của nó rời khỏi kho, tool của nó biến khỏi `mcp_hub.discover_all`, và bấm Cài lại là quay về đủ - **không byte nào của `system/mcp-catalog.json` bị sửa trong cả vòng đó**. **Toàn bộ 18 file test đọc catalog vẫn xanh mà không sửa dòng nào.** `server/bench_hotpath.py` không lùi quá mốc 150,8ms.

### Giai đoạn 2 - Cài từ zip, màn hình đồng ý, gỡ sạch, trang Gói (9 ngày)

Giai đoạn giao đúng phần cần nhất: gói riêng bằng zip, và gỡ sạch.

- `server/routes/packs.py` mới theo đúng khuôn factory của `server/routes/__init__.py` (không bao giờ import `main`, mọi thứ qua dataclass `Deps`). **Đăng ký cả 14 endpoint một lượt**, cái của giai đoạn sau trả 501 nhưng **để đúng tên hàm cuối cùng**, vì `test_route_table.py:95-99` bắt cả thứ tự lẫn tên. Cả chương trình chỉ regenerate `route_table.json` **hai lần**.
- **Mọi `/packs/*` đòi session thật, vô điều kiện**, không phụ thuộc `gate_active()` (`config.py:811-813` trả False trên bản local mặc định, khiến `main.py:190-207` bỏ qua guard). Cài đòi session chứ không nhận API token. **Không tool, skill hay agent nào chạm được `/packs/install`**: endpoint không nằm trong bảng route của hub, và điều này viết vào tài liệu, vì `javis_add_mcp` chính là tiền lệ model chạm được bề mặt dạng cài đặt.
- **Cài hai bước.** `POST /packs/inspect` stream file lên `packs-staging/<sha256>.zip` (đọc theo khối 1MB, huỷ khi quá 25MB, **đừng** chép cách `/import` ở `main.py:5952` vì nó `await file.read()` nạp hết vào RAM rồi mới kiểm), mở archive chỉ-đọc, đọc manifest, chạy mọi luật, trả về `{manifest, permissions, provides, tier, conflicts, sha256, staging_id}`. **Chưa giải nén gì cả.** `POST /packs/install {staging_id, consent_sha256, ...}` từ chối nếu hash không khớp, tức **buộc cái đã hiện ra phải chính là cái được cài**.
- **Luật zip.** Chép hằng số và vị từ chống traversal từ `share_bundle.py:36-38, 250-255` (chép logic, **không gọi**, vì `_bad` là closure bên trong `import_bundle` và hàm đó có hình dạng bundle riêng). Thêm cái `share_bundle` chưa cần: từ chối member không phải file thường qua `(info.external_attr >> 16) & 0o170000` (một symlink tên `plugin.py` trỏ vào `.secret_key` sẽ bị mọi endpoint file phục vụ lại); giải nén cố định 0o644/0o755, không nghe mode trong archive; chặn tỉ lệ nén quá 100:1; từ chối thẳng `.env`, `*.pem`, `id_rsa*`, `*.p12`; **chỉ zip, không tar** (Python 3.12 `extractall` vẫn mặc định `filter=None`); chặn kích thước manifest trước khi `safe_load` vì SafeLoader vẫn nở anchor.
- **Cài nguyên tử có rollback.** Giải nén ra `packs/.tmp-<id>-<pid>-<ts>/`, kiểm trên cây đã giải nén, `os.replace` bản cũ sang `.trash-<id>-<ts>` **trước**, rồi `os.replace(tmp, packs/<id>)`. Hỏng ở bất cứ bước nào thì rmtree tmp và trả bản cũ về. Rồi ghi sổ và gọi đúng bộ ba mà `/plugins/toggle` đang dùng (`main.py:8091-8095`).
- **Sổ cài đặt** `packs.json` ghi `{version, enabled, tier, installed_at, source, sha256, code_consent, connectors[], plugins[], assets[], pages[]}`; bốn trường cuối chính là bản kê để gỡ. Ghi bằng tmp + `os.replace` như `plugins_host._write_state` (:142-150), kèm xoay `.bak` và `POST /packs/repair` dựng lại từ quét thư mục (mất bản ghi đồng ý, nên sẽ hỏi lại, đúng hướng an toàn).
- **Gỡ.** `GET /packs/uninstall-plan` trả đúng những gì sẽ chết kèm số lượng và dung lượng, hộp thoại vẽ từ đó. Rồi: từ chối nếu có kết nối đang bận; **bắt buộc** purge mọi kết nối thuộc connector của gói (không có đường để lại mồ côi, vì một hàng mồ côi vẫn spawn được lệnh stdio của nó với cổng quyền đã biến mất); phát lại sổ hiệu ứng ngược LIFO, mỗi cái một `try/except`; chỉ `rmtree plugin-data/<slug>` khi người dùng tick (mặc định **không** tick: code gói là thứ vứt đi được, dữ liệu gói thì không); `os.replace` sang `.trash-` rồi rmtree; bỏ hàng trong `packs.json` và mọi mục `plugins.json` của nó; invalidate ba cache. Trả biên nhận để UI in một dòng thật thà.
- **Không bao giờ xoá được plugin bundled** trong `system/plugins/`. Cây code read-only nên có cố cũng EACCES, và một thứ "đã xoá" mà mọi lần pull image lại mọc lại thì tệ hơn là để nó tắt.

- **Nhưng plugin mặc định vẫn phải GỠ được, theo nghĩa người dùng hiểu** (chủ dự án hỏi thẳng
  2026-09-03: "sẽ có các plugin mặc định được tải lên sẵn mà máy khách có thể gỡ"). Cách đạt
  điều đó mà không đánh nhau với cây code read-only: thêm trạng thái **đã gỡ**, ghi vào
  `STATE_DIR/plugins.json` bên cạnh `enabled`/`disabled` sẵn có (`plugins_host._read_state`
  :127, `_effective_enabled` :213-223). Thẻ biến mất khỏi danh sách chính và rơi xuống một mục
  gập "Đã gỡ, cài lại được"; `_load_all` bỏ qua nó nên tool biến mất khỏi mọi engine y hệt xoá
  thật. Khác xoá đúng hai điểm, và cả hai đều là điểm cộng: bản cập nhật app không làm nó mọc
  lại, và bấm nhầm thì cài lại bằng một cú bấm chứ không phải đi tải lại. Chi phí khoảng nửa
  ngày, so với vài ngày nếu chuyển 11 plugin bundled thành gói cài sẵn. Đây là ô thứ hai của
  bảng trong mục "Bộ lõi và cái cài thêm"; ô thứ nhất (connector lõi) làm ở Giai đoạn 1, ô thứ
  ba (skill hệ thống) thì `system_sync` đã chạy sẵn, chỉ cần đưa lên cùng một chỗ hiển thị.
  Không chuyển plugin bundled thành gói ở spec 1: chúng đi kèm app nên vẫn cần một bản phát
  hành để đổi, tức chuyển đi không mua được gì, mà lại thêm một đường di trú phải bảo trì.
- **Skill hệ thống chỉ cần một nút, phần khó đã có.** `system_sync` đã tôn trọng
  `<brain>/skills/.disabled/`: gỡ một skill là dời thư mục nó vào đó, và lượt đồng bộ sau không
  mọc lại. Nên việc ở đây là một nút Gỡ trên trang Skills đi qua đúng đường đó, cộng một khu
  gập "Đã gỡ" có nút Cài lại - không phải cơ chế mới. Nói riêng ra vì bản kế hoạch đầu đã xếp
  skill ra ngoài spec 1, mà chủ dự án nêu rõ 2026-09-03 là muốn cả plugin, skill lẫn kết nối
  đều cài thêm và gỡ được.
- `dashboard/packs.js` mới phơi `window.JavisPacks = {render}`, gọi từ chỗ dispatch của console.js theo cách `studio.js` đang làm. **Đừng nuôi console.js to thêm** (đã 6.951 dòng). Đăng ký trang ở năm chỗ: `VIEW_ICON`, `RAIL_ITEMS`, `RAIL_GROUPS`, khoá `page.packs.label`/`sub` trong **cả hai** từ điển i18n (đang cân 715/715, test JS đỏ nếu lệch), và một thẻ `<script src>` gần `index.html:803`. Trước khi viết i18n trong code gói, **đổi tên 11 biến cục bộ tên `t` trong console.js**, đáng chú ý là `const [t, c] = SRC[s]` (:1431) và `const chip = (t, iconName)` (:1436), cả hai nằm ngay trong `renderPlugins()`.
- **Màn hình đồng ý**, vẽ hoàn toàn từ `/packs/inspect`: tên và phiên bản; xuất xứ nguyên văn (tên file kèm đầu sha256, hoặc repo @ ref @ commit); bậc tin cậy; với bậc CODE là khối đỏ không gập được kèm câu chữ ở trên, liệt kê mọi file `.py` và dung lượng, và bắt gõ đúng id gói; liệt kê tool và hook kèm ghi chú **hook nhìn thấy mọi lần gọi tool và cả kết quả** (`wrap_with_hooks` :533-542 bọc mọi tool trong route, kể cả MCP và builtin); một dòng nói `permissions` là lời khai chứ không phải cưỡng chế; nút Huỷ được focus mặc định, không Enter-để-gửi; ô "Bật sau khi cài" **mặc định TẮT**, đúng luật trong CLAUDE.md là năng lực tạo từ chat không bao giờ tự bật.
- Trên trang Plugins, plugin đến từ gói được badge `pack` và một link "Quản lý ở trang Gói" thay cho nút xoá, để chỉ có **một** chỗ gỡ. `plugins_host.describe()` (:226-253) phải học nguồn `"pack"`, nếu không một plugin gói đang chạy sẽ hiện sai là "bật (chưa nạp)".

**Xong khi:** kéo một zip mẫu chỉ có dữ liệu lên trang Gói, đọc màn hình đồng ý có nêu tên miền nó sẽ nói chuyện, cài, thấy thẻ với icon riêng trên trang Kết nối, tạo kết nối, và **gọi được tool đó từ một engine API** (OpenRouter hoặc Gemini, không phải engine CLI) để chứng minh nó đi qua `mcp_hub.discover_all` chứ không chỉ đường SDK. Rồi gỡ kèm purge: bản chụp băm đệ quy toàn bộ `STATE_DIR` trước khi cài **bằng đúng từng byte** với bản chụp sau khi gỡ, trừ `mcp_audit.jsonl` và `logs/`. Zip chứa `../../x`, member tuyệt đối, member symlink, tỉ lệ 500:1, hay 600 file đều bị từ chối mà không ghi gì ra đĩa.

### Giai đoạn 3 - Trình bày cho gói (4 ngày)

Phục vụ icon và trang hướng dẫn của gói, kèm guard resolve-rồi-kiểm-tiền-tố và allowlist content-type **hẹp**: `png`, `webp`, `jpg`. **Không SVG** (SVG phục vụ cùng origin thì trơ trong `<img>` nhưng chạy script khi mở thẳng một tab). Gửi kèm `X-Content-Type-Options: nosniff` và một `Content-Security-Policy` chặt trên đúng hai route này; hiện app **chưa có CSP ở đâu cả**.

Trang hướng dẫn của gói là **Markdown render phía server ra HTML đã lọc**, không phải HTML của tác giả: một trang HTML lạ trên origin của dashboard chỉ cách `POST /packs/install` đúng một lỗ XSS.

Thêm `category_key` cho cả 29 entry gốc trong một commit máy móc, **giữ nguyên `category`** cũ; `public_catalog()` phát cả hai; console đọc `category_key` qua `t("catalog.cat." + key)` có fallback nên không chỗ nào trắng. Gói cấp `category` lạ kèm `category_label` thì tự hiện nhãn của nó, không cần sửa repo. Badge "từ gói `<tên>`" trên thẻ connector và trên chi tiết kết nối, để connector do gói cấp không bao giờ lẫn với hàng chính chủ.

### Giai đoạn 4 - Gói có code (7 ngày)

`_iter_plugin_dirs` thêm nguồn `("pack", d)`, thứ tự **bundled → pack → user → vault**. **Gói có thư mục plugin trùng tên slug bundled thì bị từ chối ngay lúc cài** (danh sách cấm là 11 slug bundled). Việc này giữ nguyên bit-for-bit hành vi user/vault-đè-bundled hôm nay, đồng thời chặn một gói lặng lẽ thay thế `javis_task`/`javis_schedule`/`javis_add_mcp` dưới một màn hình đồng ý chỉ nói "cái này chạy code".

**Cổng env KHÔNG áp cho gói.** Plugin của gói nạp khi gói có `code_consent` hợp lệ, thế là đủ; `_env_user_enabled()` giữ nguyên từng bit cho hai nguồn `user` và `vault` như hôm nay. Lý do đầy đủ ở mục "Ranh giới tin cậy": cổng env bịt lỗ "thư mục ghi được mà không ai bấm gì", còn trình cài thì có người bấm, có màn hình liệt kê từng file `.py`, và có digest ghi lại - cùng loại bảo đảm, chỉ theo từng gói thay vì bật-tắt-tất-cả. `JAVIS_DISABLE_PACKS` là công tắc tắt sạch tương ứng cho gói.

**Đồng ý được kiểm lúc NẠP, không phải lúc cài.** `code_consent` ghi digest của mọi file `.py` trong gói; `_load_all` tính lại digest từ đĩa và từ chối nạp khi lệch, và digest nằm trong `_signature()` để đổi nội dung là buộc nạp lại chứ không cưỡi lên cache mtime. Ai ghi được `plugin.py` thì cũng ghi được `packs.json`.

`ctx.on_unload(fn)` và `ctx.record_effect(kind, ref)`. Tool và hook **vốn đã** đảo ngược được (register chỉ append vào list trên `LoadedPlugin` trong cache, không có registry toàn cục, và hub dựng lại bảng route mỗi lần cache miss). Cái **chưa** đảo ngược được: `sys.modules[mod_name]` đặt ở :340-341 và không bao giờ pop, cùng mọi thread/socket/atexit mà `register()` mở ra. Nên `plugins_host.unload(slug)` chạy `on_unload` ngược LIFO, bỏ cache, rồi pop mọi khoá `javis_plugin_*_<slug>`. `set_enabled(..., False)` đi qua `unload` để nút "Tắt" là dừng thật. Thêm khoá manifest `unload: clean | restart-required` để UI nói "cần khởi động lại" thay vì nói dối.

**Sửa `sys.path.insert(0, plugin_dir)`** ở `_import_entry` :348-350: một gói chứa `config.py` hay `mcp_hub.py` hiện đang **che module của chính server** trong suốt thân module của nó. Dùng `submodule_search_locations` thay vì chọc `sys.path`.

**Quét tương thích lúc khởi động:** `compat.app` kiểm lúc cài là chưa đủ, vì `update.sh` (`git pull`) và `updater.py:326` không bao giờ chạy lại trình cài. Thêm một lượt lúc boot **tắt** (không bao giờ xoá) gói có dải không còn khớp `VERSION`, kèm lý do trên thẻ.

Không chuyển `meta-ads-graph`, `meta-pages-graph`, `fb-monitor-apify` thành gói ở spec 1. Chúng là bằng chứng cho việc một định dạng là đúng, không phải đích di trú: chỗ dính `CONNECTOR_ID` chỉ gỡ được khi có `ctx.connector_id`, mà đó là việc về sau.

### Giai đoạn 5 - Cài từ URL và repo riêng (4 ngày)

`server/packs_fetch.py` mới. **Chỉ zip qua HTTPS.** Không dùng `git clone` dù image có git, vì ba lý do: token nằm trong argv và `/proc/<pid>/cmdline` đọc được (chính là hình dạng `_auth_url` ở `git_brain.py:489-503`, lý do `_redact` tồn tại); clone kéo cả lịch sử nên không chặn được dung lượng trước khi byte rơi xuống; và `httpx` đã pin sẵn nên đường HTTPS không thêm dependency lẫn subprocess. Token đi bằng **header**.

- `owner/repo@ref` → `api.github.com/repos/<o>/<r>/zipball/<ref>` với `Authorization: Bearer`.
- GitLab → `repository/archive.zip?sha=<ref>` với `PRIVATE-TOKEN`.
- `git+https://` **không có** trong spec 1: không subprocess, không bề mặt tiêm tham số.

**Chốt SSRF**, thứ hôm nay server **không có ở đâu cả**: chỉ `https`, chỉ cổng 443, và mọi địa chỉ đã resolve phải trượt `is_private / is_loopback / is_link_local / is_reserved / is_multicast`; tối đa 3 redirect, **kiểm lại theo địa chỉ socket đã resolve sau mỗi chặng**, không phải theo hostname. Chuyện này rất cụ thể: `mcp_hub.py:82` đặt hub ở `http://127.0.0.1:7777/hub/mcp`, và hub là nơi giữ toàn bộ khoá của người dùng. Nói cho đủ: `/hub/mcp` bỏ qua guard cookie (nó nằm trong `_AUTH_PUBLIC_EXACT`, main.py:158-162) nhưng KHÔNG hở - `handle_http` đòi `Bearer hub_token` so sánh hằng-thời-gian. Cái chốt SSRF chặn là một tầng khác: một URL do người khác đưa mà trỏ vào loopback thì request đi RA từ chính tiến trình server, tức nó ở sẵn bên trong vành đai mạng, và bất cứ dịch vụ nội bộ nào tin localhost đều thành đích. Chốt phải có trước khi mở đường tải từ URL, không phải sau.

**Token lưu theo host, mã hoá Fernet trong settings.** `config.py:452 _SECRET_PATHS` thêm `"packs.tokens.*"`, cần sửa ~6 dòng trong `_transform_secret_fields` để hiểu dấu `*` cuối là "mọi khoá của dict này", và phải thêm cùng ký tự đó vào `secret_paths_hong()` nếu không việc báo secret hỏng lặng lẽ ngừng phủ chúng.

**Ghim phiên bản:** ghi lại `ref` đã yêu cầu, `commit` đã resolve, và `sha256` của archive. Ghim theo nhánh thì hiện chip hổ phách "đang bám main". **Không bao giờ tự động cập nhật gói có code.** Khi cập nhật, tính lại `permissions` và digest code; nếu rộng ra thì cài ở trạng thái **tắt** và hỏi lại. Giữ một thế hệ rollback ở `packs/.prev/<id>/`.

### Giai đoạn 6 - Kho công khai (4 ngày)

`server/packs_store.py` fetch `packs.store_url` **phía server** (giữ token và chốt SSRF ở server, tránh luôn CORS), `If-None-Match`, cache TTL 6 giờ. Schema index công bố ở `docs/dev/pack-store-index.md`, mỗi mục soi gương manifest cộng `download: {url, sha256, size}`, `verified`, `updated`, và khối `listing` để dành. **Các trường giá có mặt từ v1** để một gói bán tiền sau này chỉ là một nút "Mua" mở `purchase_url`, không phải một lần phá định dạng.

`sha256` **ghim từ lần cài đầu**, trong sổ. Kiểm một bản tải về bằng hash do chính index đó cấp thì không chứng minh gì về người phát hành; từ chối một hiện vật **đã đổi** ở **cùng một phiên bản** thì có.

**Kho công khai liệt kê được gói bậc CODE**, nhưng một chạm từ kho vẫn phải đi qua đúng màn hình đồng ý như zip và URL - không có đường tắt "cài ngay" cho gói chứa Python. Kèm hai thứ để người cài thấy mình đang chọn gì: **nhãn nguồn** (chính chủ / cộng đồng / chưa review) và một dòng nói rõ gói này chạy mã. Gói của chính chủ dán nhãn `verified` trong index; gói cộng đồng thì không, và màn hình đồng ý của nó nói dài hơn. Javis không thay người dùng quyết định tin ai.

Ba trạng thái suy giảm, không cái nào là stack trace: có cache thì hiện dòng hổ phách và vẫn vẽ lưới; không cache thì trạng thái rỗng kèm "vẫn cài được từ zip hoặc URL"; `format_version` lạ thì nói thẳng "kho này cần Javis mới hơn", không bao giờ parse nửa vời.

Thêm biến môi trường `JAVIS_DISABLE_PACKS` đọc live, deny thắng, tắt sạch mọi gói không-bundled mà không cần vào dashboard.

Coi index là **dữ liệu không tin được**: `name`, `description` và mô tả tool của gói đi thẳng vào danh sách tool của những engine đang cầm Bash.

### Giai đoạn L - Đóng băng ngôn ngữ (10 ngày, chạy song song)

Chạy lúc nào cũng được, ràng buộc thứ tự duy nhất là `category_key` phải xong trước giai đoạn 6.

- **Cổng chặn.** `tests/python/test_ngon_ngu_ma_nguon.py` mới, quét AST với **danh sách CLEAN theo đường dẫn kiểu bánh cóc**, đúng khuôn repo đã dùng hai lần (`MIEN_TRU` trong `test_lang_bat_bien.py`, `I18N_MIGRATED` ở `tests/js/test_i18n.mjs:178`). Gieo CLEAN bằng `server/routes/**` (đo được 0 cờ thật), `server/packs*.py`, `server/purge.py`, `dashboard/packs.js`. Luật trong CONTRIBUTING.md: mọi module mới vào CLEAN ngay trong commit sinh ra nó. Cộng thêm một kiểm toàn cây không allowlist rằng không định danh nào chứa ký tự ngoài ASCII (hôm nay đo được **đúng 0**, nên là cái bánh cóc miễn phí). Lối thoát `# lang-ok: <lý do>` có in số lần dùng.
  Không dùng ruff (repo không có ruff, và không luật nào diễn đạt được "đây có phải từ tiếng Việt không"), không quét theo git diff (`actions/checkout@v4` không có `with:` nên fetch-depth 1, không có merge base), không dùng baseline 853 mục (dương tính giả không giảm được ở `cap`, `do`, `con`, `day`, `ban`, `tin`, `set`).
- **Gộp slugify**, đây là sửa lỗi chứ không phải dọn dẹp. Nâng một `ascii_slug()` duy nhất theo bản đúng ở `main.py:4567`, route cả `share_bundle` lẫn trình nạp gói qua đó, và chuyển `main.py:4709, 5887, 7138` khỏi `_slugify` (dùng `\w` với `re.UNICODE` nên **giữ nguyên dấu**, tức mọi brain mới đang được gieo sẵn một file agent có slug mang dấu).
- **Đổi tên hợp đồng công khai**, mỗi cái một chiến lược đọc-cả-hai-ghi-cái-mới có nêu thời hạn: 7 đường URL tiếng Việt (không phải 5, sót `/usage/tong-quan` và `/usage/bao-cao`), alias nối thành **một khối ở cuối** danh sách route để `route_table.json` chỉ dài thêm 7 dòng mà không đánh số lại; ~13 trường JSON trả về đổi cùng với chỗ tiêu thụ trong dashboard trong một commit (không cần alias, mọi consumer đều là JS chính chủ trong repo này); 5 khoá settings cộng `nguon_tra_loi` thêm bước `_migrate_key_names` vào chuỗi chuẩn hoá của `read_settings` (`config.py:698`) và bước đó phải **pop** khoá cũ, vì `_deep_merge` để cả hai cùng sống; và `muc_quyen` → `permission` (140 chỗ, 15 file, món to nhất, và cùng một khái niệm với `min_mode` trong `plugin.yaml` lẫn `discover_all(mode)`, nên định dạng gói tuyệt đối không được đẻ ra cái tên thứ tư).
- **Mã lỗi thay vì dựng framework i18n cho server.** Trả `{"ok": false, "error_code": "tts_no_audio", "error": "<chữ tiếng Việt>"}` rồi để dashboard render `t("err." + error_code)` với fallback về chính câu tiếng Việt. Việc này biến một dự án vô hạn ở phía server thành một dự án khoá-từ-điển hữu hạn, ở đúng cái tầng đã có sẵn 715/715 tiếng Anh.
- Chuyển `chatbot_runtime.py:515 _DAU_BI` và `conversation_state.py:26 _GOAL_RE` vào `server/lexicon/` (lỗi số 4 ở trên).

**Xong khi:** thêm `def _kiem_tra_moi(): pass` vào `server/routes/domain.py` làm `python tests/run.py lang` đỏ và nêu đúng file, dòng, từ; thêm `# lang-ok:` làm nó xanh với số lần dùng bằng 1. `ascii_slug("Đo lường doanh thu") == "do-luong-doanh-thu"` và một agent có chữ Đ trong tên sống sót một vòng export/import từng byte. Cả hai cách viết của cả 7 URL trả về byte y hệt nhau.

---

## Sau khi xong hết, việc gì vẫn phải ra bản mới

Nói thẳng, vì con số đau là 524 bản trong 3 tháng và chương trình này **không** làm nó giảm một nửa.

Cần nói lại một chỗ so với bản đầu: **29 connector lõi giờ GỠ được từ Giai đoạn 1**, nên danh sách dưới đây chỉ còn đúng với việc SỬA hoặc THÊM một connector lõi, không còn đúng với việc bỏ nó khỏi máy người dùng.

**Vẫn cần bản mới:** một phương ngữ OAuth mới (`meta`, `google`, `generic` gói chọn được, cái thứ tư là PR vào lõi, và tách các nhánh Meta ra là thay đổi dễ gây hồi quy nhất trong repo này, hỏng thì 60 ngày sau mới hiện ra dưới dạng token hết hạn im lặng chứ không phải test đỏ); một luồng đăng nhập kiểu QR Zalo; `transport: internal`; **một trường mới trong mô tả connector** (schema vẫn đang lớn: `inject_args` thêm 19/08, `url_template` thêm 31/07, `env` tĩnh, `cred_dir`, `isolate_home` đều mới vài tháng, và 8 trong 60 commit catalog gần đây có sửa chính `mcp_catalog.py`; chính sách là khoá lạ thì **bỏ qua, không bao giờ từ chối**); sửa hoặc thêm một trong 29 connector lõi; mọi UI dashboard vượt quá một icon và một trang hướng dẫn (không có build step, 34 thẻ script đánh phiên bản tay, thêm trình nạp JS cho gói là đẻ ra hệ mở rộng thứ hai); và `notifications/tools/list_changed` cho phiên CLI đang mở.

**Không còn cần bản mới:** một connector apikey/http mới kèm icon, trang hướng dẫn, nhãn nhóm, `tool_meta`, `validate`, `arg_rules`, `rate_limit`; một plugin mới có tool và hook; và **chính hai thứ đó ship riêng cho một khách bằng zip hoặc repo private**, đúng mục tiêu đặt ra.

**Những cặp song song sẽ tồn tại vĩnh viễn, nêu ra để không ai bất ngờ:** `system/mcp-catalog.json` cạnh YAML connector của gói; `plugin.yaml` (spec 0) cạnh `javis-pack.yaml`; `system/plugins/` cạnh `STATE_DIR/packs/`; `plugins.json` cạnh `packs.json`; `/plugins` cạnh `/packs`; `connector_id="custom"` cạnh gói. Mỗi cặp đều có lý do riêng. Không cặp nào chết đi.

---

## Công sức

| Giai đoạn | Nội dung | Ngày |
|---|---|---|
| 0 | Xoá kết nối sạch, `purge.py`, `close_now`, `safeHref` | 4 |
| 1 | `packs.py`, lớp phủ catalog, chốt mồ côi, lớp gỡ được | 4 |
| 2 | Cài zip, màn đồng ý, gỡ sạch, routes, trang Gói | 9 |
| 3 | Asset, trang hướng dẫn, CSP, `category_key`, badge | 4 |
| 4 | Gói có code, đồng ý theo hash, `unload`, `sys.path` | 7 |
| 5 | Cài từ URL và repo riêng, chốt SSRF, lưu token | 4 |
| 6 | Kho công khai, kill switch, kiểm bản mới | 4 |
| L | Cổng ngôn ngữ, slugify, đổi tên hợp đồng, mã lỗi | 10 |

Tổng khoảng **46 ngày công**, trong đó **giai đoạn 0 đến 2 (17 ngày) đã giao đủ**: xoá sạch, tầng gói chạy được, và gói riêng bằng zip. Các giai đoạn 0, 1, 2, 3, 5, 6 merge độc lập. Giai đoạn L chạy song song.

---

## Nghiệm thu

```
.venv\Scripts\python tests\run.py              # đủ 234 file; python hệ thống thiếu lib
.venv\Scripts\python tests\run.py packs
.venv\Scripts\python tests\run.py purge
.venv\Scripts\python tests\run.py cred_dir     # phải xanh: canh delete_connection vẫn gọi forget_cred_dir
.venv\Scripts\python tests\run.py catalog      # không em dash, guide wrap, độ dài dòng, nay quét cả gói
.venv\Scripts\python tests\run.py i18n         # cân từ điển, cân placeholder, bánh cóc I18N_MIGRATED
.venv\Scripts\python tests\run.py lang         # cổng định danh
.venv\Scripts\python server\bench_hotpath.py   # build_system_prompt không lùi quá 150,8ms
```

Test mới đáng kể nhất là **`test_packs_purge.py`**: chụp băm đệ quy `STATE_DIR`, cài gói mẫu, tạo kết nối theo connector của nó, gọi một tool, gỡ kèm purge, rồi khẳng định bản chụp giống hệt từng byte. Kèm dạng chống hồi quy: khẳng định chuỗi `cid` xuất hiện ở **không** tên file và **không** nội dung file nào dưới `STATE_DIR`. Chính vế thứ hai mới là cái bắt được loại hiện vật **tiếp theo** mà ai đó thêm vào mà quên báo cho `purge.py`.

Kèm theo: `test_pack_coverage.py` (tự tính con số 13/29 và in lý do từ chối), `test_packs_zip_safety.py` (traversal, member tuyệt đối, symlink, bit thực thi, tỉ lệ 500:1, 600 file, YAML alias bomb), `test_purge_giet_tien_trinh.py` (spawn tiến trình thật, purge, khẳng định `poll() is not None` ngay chứ không phải 900 giây sau), `test_packs_fetch_ssrf.py` (302 từ host công khai sang `169.254.169.254` phải bị chặn, chứng minh guard chạy lại từng chặng), `test_packs_secret.py` (token trên đĩa phải bắt đầu bằng `enc:`).

**Chạy tay, đầu tới cuối:** dựng zip mẫu → kéo lên trang Gói → đọc màn hình đồng ý → cài với ô "Bật sau khi cài" **không** tick → bật → tạo kết nối → gọi tool đó **trên cả ba loại engine** (Claude Code, Codex, và một engine API như OpenRouter; cái thứ ba mới là cái chứng minh nó đi qua `mcp_hub.discover_all` chứ không chỉ đường SDK) → chạy thêm một tick loop nền → gỡ kèm purge → `tools/list` sạch → diff bản chụp rỗng. **Rồi lặp lại toàn bộ trong Docker** với cây code read-only dưới user non-root, khẳng định mọi byte rơi vào `/data/state/packs/` và **không gì** ghi vào `/app`, và `docker compose restart` thì gói còn nguyên.

Một việc phải làm bằng tay, không tự động: **đừng tự xoá 5 thư mục `connector-home/zalo-*` mồ côi trên máy đang chạy.** Báo cáo ra rồi mời dọn một lượt, vì một trong số đó có thể còn giữ phiên người dùng vẫn cần.

---

## Trả lời câu hỏi "sửa tiếng Việt bây giờ có kịp không"

Kịp, và rẻ hơn cảm giác ban đầu nhiều. Số đo thật:

- **0 định danh có dấu** trong toàn bộ `server/**/*.py`. Không một hàm hay biến nào.
- Định danh tiếng Việt không dấu: **181 hàm (7,2%), 0 class, 81 biến**. Gần như toàn bộ là helper private có gạch dưới đầu.
- Hợp đồng công khai dính tiếng Việt: **khoảng 22 chỗ**, đã liệt kê hết ở giai đoạn L.
- **Frontmatter agent/workflow/loop và toàn bộ 35 bảng SQLite đã dùng khoá tiếng Anh sẵn**, có luật viết thẳng trong `server/meta_tools.py:79` bắt phải thế.
- `dashboard/i18n/en.json` **đã đủ 715/715 khoá**.

Nghĩa là phần **đắt nhất** của việc quốc tế hoá, tức đổi schema dữ liệu đã lưu trên đĩa của người dùng, **gần như không tồn tại**. Không phải bắt ai di trú brain.

Cái còn nợ thật, xếp theo mức cản một người dùng nói tiếng Anh **ngay hôm nay**:

1. **`CLAUDE.md`, 33,7KB tiếng Việt, đọc nguyên văn vào mọi system prompt.** Không cản, vì model đọc hướng dẫn tiếng Việt rồi trả lời tiếng Anh bình thường, và tài liệu của chính dự án đã bác chuyện dịch nó ra N bản (N bản là N thứ trôi lệch). Tốn token thì có.
2. **~2.081 chuỗi tiếng Việt còn ghim cứng trong JS**, mới rút ra từ điển được ~25% (`console.js` 328 chỗ gọi `t()`, `studio.js` 96, `app.js` đúng 4, 30 file còn lại con số 0). **Cái này cản thật.** Đây là việc bóc dần theo bánh cóc `I18N_MIGRATED`, không phải làm một lượt.
3. **~2.244 chuỗi trong Python, phủ 0%**, và không có hàm `t()` nào ở phía server. Cản, nhưng cách rẻ là **mã lỗi** ở giai đoạn L chứ không phải dựng cả framework.
4. Tài liệu, commit message, CHANGELOG tiếng Việt. Không cản, chỉ là chưa gọn.

Nói gọn: khởi đầu bằng tiếng Việt không phải sai lầm. Dự án đã vô tình làm đúng chỗ tốn kém nhất (khoá dữ liệu tiếng Anh), và chỗ còn lại là chuỗi hiển thị, tức thứ bóc dần được mà không gãy gì.
