"""Cơ chế của catalog connector, kiểm bằng KHUÔN GIẢ chứ không bằng connector có thật.

    python tests/run.py catalog_co_che

Không cần pytest, không chạm mạng.

Vì sao có file này
------------------
Bốn cơ chế bên dưới - env tĩnh, url_template, inject_args, phân loại quyền - là MÃ CỦA APP
(`server/mcp_catalog.py`). Trước 0.55.36 chúng được kiểm gián tiếp qua bốn connector có thật:
webcake-landing (env), n8n (url_template), shopify (inject_args), hostinger (phân loại). Cách
đó có một chỗ dột: 0.55.36 dọn 16 khuôn connector sang repo kho, và bốn test kia đỏ hết cùng
lúc - không phải vì cơ chế hỏng, mà vì dữ liệu chúng mượn để kiểm đã đi chỗ khác.

Nên chỗ này đổi trục: mỗi cơ chế được kiểm bằng một khuôn GIẢ dựng ngay trong test. Khuôn giả
không bao giờ bị dọn đi, không phụ thuộc vào việc app còn ship connector nào, và nó nói thẳng
ra cơ chế đang được kiểm là gì - đọc test là hiểu luật, không phải đi tra một connector.

Phần dữ liệu (khuôn `n8n` có đúng url_template không, 330 tool của Hostinger xếp đúng nhóm
chưa) đi theo dữ liệu sang repo kho `blogminhquy/javis-store`, nơi `tools/kiem-tra.py` chạy
trên mọi Pull Request. Giữ bản chụp của chúng ở đây chỉ là tự trấn an: kho đổi được mà không
cần bản Javis mới, nên test ở repo này không canh nổi thứ người dùng thật sự cài.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import json
import sys

import mcp_catalog as mc

loi = []


def check(ten, dieu_kien, them=""):
    print(("ok   " if dieu_kien else "FAIL ") + ten
          + (("  [" + str(them) + "]") if them and not dieu_kien else ""))
    if not dieu_kien:
        loi.append(ten)


# ============================================================
# 1. env tĩnh mức connector + thứ tự ưu tiên
#
# Có server MCP cần một biến môi trường mà NGƯỜI DÙNG không nên phải biết (base URL của API,
# tên môi trường). Khai `env` ở connector là cách đưa nó vào mà không đẻ thêm một ô nhập kỹ
# thuật giữa màn hình đăng nhập.
# ============================================================
KHUON_ENV = {
    "id": "gia-env", "transport": "stdio", "command": "npx",
    "env": {"FOO_BASE": "https://foo.example", "FOO_ENV": "prod", "TRONG_RONG": ""},
    "auth": {"type": "apikey", "fields": [
        {"key": "tok", "env": "FOO_TOKEN"},
        {"key": "org", "env": "FOO_ORG", "optional": True},
    ]},
}
env = mc.build_env(KHUON_ENV, {"tok": "T1", "org": "O1"})
check("env tĩnh mức connector được nạp", env.get("FOO_BASE") == "https://foo.example")
check("giá trị rỗng trong env tĩnh bị bỏ qua", "TRONG_RONG" not in env, env)
check("env tĩnh và ô đăng nhập sống chung", env.get("FOO_TOKEN") == "T1" and env.get("FOO_ORG") == "O1")

# Ô tuỳ chọn bỏ trống thì KHÔNG được đẻ ra một biến rỗng: nhiều package coi "có biến nhưng
# rỗng" khác hẳn "không có biến", và ca đó hỏng theo kiểu rất khó lần.
env_trong = mc.build_env(KHUON_ENV, {"tok": "T1"})
check("ô tuỳ chọn bỏ trống -> KHÔNG có biến rỗng", "FOO_ORG" not in env_trong, env_trong)
check("bỏ trống ô tuỳ chọn thì env tĩnh vẫn còn", env_trong.get("FOO_ENV") == "prod")

KHUON_DUNG = {
    "id": "gia-dung", "transport": "stdio", "command": "npx",
    "env": {"FOO_TOKEN": "mac-dinh"},
    "auth": {"type": "apikey", "fields": [{"key": "tok", "env": "FOO_TOKEN"}]},
}
check("trùng tên biến: giá trị user gõ THẮNG env tĩnh",
      mc.build_env(KHUON_DUNG, {"tok": "user-go"}).get("FOO_TOKEN") == "user-go")
check("trùng tên biến nhưng user bỏ trống: giữ env tĩnh làm mặc định",
      mc.build_env(KHUON_DUNG, {"tok": ""}).get("FOO_TOKEN") == "mac-dinh")


# ============================================================
# 2. url_template: server nằm trên tên miền của CHÍNH người dùng
#
# Người ta gõ đủ kiểu. Luật: ghép được thì chuẩn hoá, không ghép được thì trả RỖNG để caller
# rơi về url tĩnh hoặc báo thiếu - tuyệt đối không đẻ ra một URL nửa vời rồi để người dùng ngồi
# đoán vì sao kết nối đỏ.
# ============================================================
KHUON_URL = {
    "id": "gia-url", "transport": "http",
    "url_template": "{base_url}/mcp-server/http",
    "auth": {"type": "apikey", "fields": [
        {"key": "base_url", "url_base": True},
        {"key": "token", "header": "Authorization: Bearer {token}"},
    ]},
}


def _url(raw):
    return mc.build_url(KHUON_URL, {"base_url": raw, "token": "tok"})


TOT = [
    ("https://cty.app.n8n.cloud", "https://cty.app.n8n.cloud/mcp-server/http"),
    # Quên scheme, thừa gạch chéo, hoặc dán nguyên URL đang mở trên trình duyệt.
    ("cty.app.n8n.cloud", "https://cty.app.n8n.cloud/mcp-server/http"),
    ("https://cty.app.n8n.cloud/", "https://cty.app.n8n.cloud/mcp-server/http"),
    ("https://cty.app.n8n.cloud/home/workflows?x=1", "https://cty.app.n8n.cloud/mcp-server/http"),
    ("  https://cty.app.n8n.cloud  ", "https://cty.app.n8n.cloud/mcp-server/http"),
    ("HTTPS://Cty.App.N8N.Cloud", "https://cty.app.n8n.cloud/mcp-server/http"),
    # Máy tự dựng trong mạng nội bộ: giữ nguyên http và cổng, đừng ép lên https.
    ("http://192.168.1.9:5678", "http://192.168.1.9:5678/mcp-server/http"),
    ("http://localhost:5678/", "http://localhost:5678/mcp-server/http"),
]
for raw, mong in TOT:
    check("địa chỉ " + repr(raw) + " -> đúng", _url(raw) == mong, _url(raw))

RAC = ["", "   ", "không phải url", "ftp://a.b", "javascript:alert(1)", "https://a.b/x y", "https:///"]
for raw in RAC:
    check("CANARY: đầu vào rác " + repr(raw) + " -> rỗng", _url(raw) == "", _url(raw))

check("CANARY: thiếu hẳn ô địa chỉ -> rỗng, không ra URL cụt",
      mc.build_url(KHUON_URL, {"token": "tok"}) == "", mc.build_url(KHUON_URL, {"token": "tok"}))
check("connector url tĩnh không dính url_template",
      mc.build_url({"id": "x", "url": "https://a.b/mcp", "auth": {"fields": [{"key": "k"}]}},
                   {"k": "v"}) == "")
check("header dựng đúng từ token",
      mc.build_headers(KHUON_URL, {"base_url": "https://a.b", "token": "TOK"})
      == {"Authorization": "Bearer TOK"})


# ============================================================
# 3. inject_args: tham số BẮT BUỘC mà model không có cách nào biết
#
# Vài server đòi mỗi lời gọi tool kèm một khối meta (vd hồ sơ agent UCP của Shopify). Model
# không biết điền gì, nên catalog khai và tầng client tự ghép. Luật sống còn: tham số của MODEL
# luôn thắng, và ghép phải SÂU - ghép nông là nuốt mất một nhánh.
# ============================================================
MAC_DINH = "https://vi.du/system/ucp-agent-profile.json"
KHUON_INJ = {
    "id": "gia-inj",
    "auth": {"type": "apikey", "fields": [
        {"key": "agent_profile", "default": MAC_DINH},
    ]},
    "inject_args": {"meta": {"ucp-agent": {"profile": "{agent_profile}"}}},
}
check("ô trống -> rơi về giá trị mặc định của catalog",
      mc.build_inject_args(KHUON_INJ, {}) == {"meta": {"ucp-agent": {"profile": MAC_DINH}}},
      mc.build_inject_args(KHUON_INJ, {}))
check("user tự trỏ giá trị riêng -> đi theo user",
      mc.build_inject_args(KHUON_INJ, {"agent_profile": "https://toi.com/p.json"})
      == {"meta": {"ucp-agent": {"profile": "https://toi.com/p.json"}}})

# Khai được nhưng KHÔNG có nguồn thì bỏ hẳn nhánh, đừng gửi "{k}" thô cho server.
KHUON_THIEU = {"id": "x", "auth": {"fields": [{"key": "k"}]},
               "inject_args": {"meta": {"a": "{k}"}, "giu": "hang so"}}
check("CANARY: placeholder không có nguồn -> bỏ nhánh, không gửi chuỗi thô",
      mc.build_inject_args(KHUON_THIEU, {}) == {"giu": "hang so"},
      mc.build_inject_args(KHUON_THIEU, {}))
check("CANARY: connector không khai inject_args -> rỗng, không đụng gì",
      mc.build_inject_args({"id": "x", "auth": {"fields": [{"key": "k"}]}}, {"k": "v"}) == {})

inj = mc.build_inject_args(KHUON_INJ, {})
check("tham số model giữ nguyên, meta được thêm vào",
      mc.merge_inject_args({"catalog": {"query": "giày"}}, inj)
      == {"catalog": {"query": "giày"}, "meta": {"ucp-agent": {"profile": MAC_DINH}}})
# Tool tự đặt meta["idempotency-key"]; ghép NÔNG là nuốt mất ucp-agent hoặc nuốt key.
check("CANARY: deep-merge - key của model sống chung với khối được chèn",
      mc.merge_inject_args({"meta": {"idempotency-key": "abc"}}, inj)
      == {"meta": {"idempotency-key": "abc", "ucp-agent": {"profile": MAC_DINH}}},
      mc.merge_inject_args({"meta": {"idempotency-key": "abc"}}, inj))
check("CANARY: model tự đặt profile thì KHÔNG bị đè",
      mc.merge_inject_args({"meta": {"ucp-agent": {"profile": "CUA-MODEL"}}}, inj)
      == {"meta": {"ucp-agent": {"profile": "CUA-MODEL"}}})
check("inject rỗng -> trả nguyên tham số model", mc.merge_inject_args({"a": 1}, {}) == {"a": 1})


# ============================================================
# 4. Phân loại quyền
#
# Đây là luật an toàn quan trọng nhất của cả tầng connector: xếp nhầm một tool tiêu tiền hay
# xoá dữ liệu xuống nhóm ghi thường, và mức Ghi nháp tự chạy được nó.
#
# Hai đường vào: `tool_meta` do connector KHAI (thắng), và heuristic theo tên tool (đỡ cho
# server bày hàng trăm tool mà catalog không liệt kê hết).
# ============================================================
KHUON_QUYEN = {
    "id": "gia-quyen", "default_perm": "readonly",
    "auth": {"type": "apikey", "fields": [{"key": "k"}]},
    "tool_meta": {
        "read": ["search_workflows", "get_workflow"],
        "write": ["create_workflow", "update_workflow"],
        # Chạy một workflow là gửi mail, đăng bài, gọi API tính tiền - nguy hiểm, không phải
        # ghi thường. Tên nó KHÔNG có "delete" nên heuristic không tự bắt được.
        "danger": ["execute_workflow", "delete_workflow"],
    },
}
LOAI = {
    "search_workflows": "read", "get_workflow": "read",
    "create_workflow": "write", "update_workflow": "write",
    "execute_workflow": "danger", "delete_workflow": "danger",
}
for tool, mong in LOAI.items():
    got = mc.classify(KHUON_QUYEN, tool)
    check("phân loại " + tool + " -> " + mong, got == mong, got)

# Tool KHÔNG khai trong tool_meta rơi xuống heuristic tên: có dấu hiệu ghi thì là "write",
# còn lại là "read". KHÔNG có nhánh nào tự đoán ra "danger" - và đó là điều quan trọng nhất
# phải biết về tầng này:
#
#   Mức NGUY HIỂM chỉ tồn tại khi connector TỰ KHAI nó.
#
# Một server bày hàng trăm tool (Hostinger có hơn 330) thì tool xoá, tool tiêu tiền nằm lẫn
# trong đó, và nếu khuôn quên khai thì chúng tụt xuống nhóm ghi thường - tức mức Ghi nháp tự
# chạy được. Từ 0.55.36 phần lớn khuôn sống ở repo kho, nên phép kiểm "đã khai đủ chưa" thuộc
# về `tools/kiem-tra.py` bên đó. Ở đây chốt đúng một điều: hành vi mặc định là gì, để ai đọc
# cũng biết mình đang dựa vào lời khai chứ không dựa vào phép màu.
check("tool lạ có dấu hiệu ghi -> write (KHÔNG tự thành danger)",
      mc.classify(KHUON_QUYEN, "delete_dns_record") == "write",
      mc.classify(KHUON_QUYEN, "delete_dns_record"))
check("tool lạ không dấu hiệu gì -> read", mc.classify(KHUON_QUYEN, "list_domains") == "read")

# Khai theo GLOB là đường duy nhất phủ nổi hàng trăm tool. Hostinger dựa hoàn toàn vào nó
# (`DNS_delete*V1`), nên hỏng cái này là hỏng lặng lẽ trên diện rộng.
KHUON_GLOB = dict(KHUON_QUYEN, tool_meta={"read": ["DNS_get*"], "danger": ["DNS_delete*", "*_purchase*"]})
check("glob trong tool_meta.danger có tác dụng",
      mc.classify(KHUON_GLOB, "DNS_deleteDNSRecordsV1") == "danger",
      mc.classify(KHUON_GLOB, "DNS_deleteDNSRecordsV1"))
check("glob trong tool_meta.read có tác dụng",
      mc.classify(KHUON_GLOB, "DNS_getDNSRecordsV1") == "read")
check("glob giữa tên cũng khớp", mc.classify(KHUON_GLOB, "domains_purchaseNewDomainV1") == "danger")
check("CANARY: mức Ghi nháp KHÔNG chạm được tool khai danger bằng glob",
      not mc.allowed(KHUON_GLOB, "safe", "full", "DNS_deleteDNSRecordsV1")[0])

check("mức Chỉ đọc vẫn xem được", mc.allowed(KHUON_QUYEN, "readonly", "full", "get_workflow")[0])
check("CANARY: mức Chỉ đọc chặn cả tạo mới",
      not mc.allowed(KHUON_QUYEN, "readonly", "full", "create_workflow")[0])
check("mức Ghi nháp tạo/sửa được",
      mc.allowed(KHUON_QUYEN, "safe", "full", "create_workflow")[0]
      and mc.allowed(KHUON_QUYEN, "safe", "full", "update_workflow")[0])
check("CANARY: mức Ghi nháp KHÔNG được tự chạy workflow",
      not mc.allowed(KHUON_QUYEN, "safe", "full", "execute_workflow")[0])
check("mức Toàn quyền mới chạy được",
      mc.allowed(KHUON_QUYEN, "full", "full", "execute_workflow")[0])
# Loop nền ở chế độ gợi ý bị ép về chỉ đọc dù kết nối để Toàn quyền.
check("CANARY: loop chế độ suggest không chạy được dù kết nối Toàn quyền",
      not mc.allowed(KHUON_QUYEN, "full", "suggest", "execute_workflow")[0])


# ============================================================
# 5. Hồ sơ agent UCP - tệp của APP, nên vẫn kiểm ở đây
#
# `system/ucp-agent-profile.json` ở lại trong app dù connector Shopify đã sang kho: gói shopify
# trong kho trỏ tới bản phục vụ qua GitHub raw của repo này, nên nội dung nó khai vẫn là lời của
# Javis chứ không phải của kho.
# ============================================================
prof = ROOT / "system" / "ucp-agent-profile.json"
check("file hồ sơ agent có thật trong repo", prof.exists(), str(prof))
if prof.exists():
    pj = json.loads(prof.read_text(encoding="utf-8"))
    check("hồ sơ khai phiên bản UCP", bool((pj.get("ucp") or {}).get("version")))
    ten_nl = [c.get("name") for c in (pj.get("capabilities") or [])]
    check("hồ sơ khai năng lực catalog + cart",
          "dev.ucp.shopping.catalog" in ten_nl and "dev.ucp.shopping.cart" in ten_nl, ten_nl)
    # Javis dừng ở giỏ hàng rồi đưa link cho người thật bấm - khai checkout là tự nhận quyền
    # thanh toán mà app không hề có đường đi tới.
    check("CANARY: hồ sơ KHÔNG khai năng lực thanh toán",
          not any("checkout" in str(n) for n in ten_nl), ten_nl)


# ============================================================
# 6. Catalog thật vẫn phải lành lặn sau khi dọn nhà
# ============================================================
data = json.loads((ROOT / "system" / "mcp-catalog.json").read_text(encoding="utf-8"))
ids = [c.get("id") for c in data.get("connectors", [])]
check("id không trùng nhau", len(ids) == len(set(ids)), ids)
check("catalog không rỗng", len(ids) >= 5, len(ids))
# Ba thứ này KHÔNG đóng gói được (xem tools/tu-catalog.py của repo kho: transport internal là
# allowlist bảo vệ import_module, còn auth qr là đường riêng của Zalo trong app). Chúng phải ở
# lại catalog vĩnh viễn - dọn nhầm là mất hẳn năng lực, không có gói nào cài lại được.
for cid in ("zalo", "botcake", "substack"):
    check("CANARY: '" + cid + "' còn trong app (không đóng gói được)", cid in ids)
for c in data.get("connectors", []):
    icon = c.get("icon") or ""
    if icon.startswith("/static/"):
        p = ROOT / "dashboard" / icon[len("/static/"):]
        check("file logo có thật: " + icon, p.exists(), str(p))

# Bất biến bảo mật của TOÀN catalog: không khuôn nào được nhét credential vào `url`.
#
# Tài liệu của vài server gợi ý kiểu link `https://.../mcp?jwt=<token>`. Javis không được dùng
# kiểu đó: `mcp_store.add_connection` lưu `url` KHÔNG qua `secrets_store`, và `public_catalog`
# trả nguyên `url` ra frontend - chỉ headers/env/secrets mới được che. Token trong url là rơi
# thẳng ra dashboard và ra log.
CRED = ("jwt=", "token=", "api_key=", "apikey=", "secret=", "password=", "access_token=")
ban = [c.get("id") for c in data.get("connectors", [])
       if any(p in (c.get("url") or "").lower() for p in CRED)]
check("không khuôn nào nhét credential vào url", not ban, ban)
# Chứng minh phép kiểm trên có quyền lực thật chứ không xanh chỉ vì catalog đang sạch.
check("CANARY: url kiểu dán-link-kèm-token bị bắt",
      any(p in "https://a.b/mcp?jwt=TOKEN-THAT".lower() for p in CRED))

# ============================================================
# 7. Đường thật: thêm kết nối -> resolved() dựng lại URL từ template
#
# Chỗ dễ hỏng nhất khi refactor: URL phải được dựng LẠI ở `resolved()` chứ không chỉ lúc thêm
# kết nối. Dựng một lần rồi cất là user sửa địa chỉ xong mà kết nối vẫn trỏ về địa chỉ cũ, im
# lặng, cho tới khi họ xoá đi đấu lại.
#
# Chạy trên một catalog GIẢ ghi ra thư mục tạm: sau 0.55.36 không còn connector thật nào khai
# `url_template`, mà cơ chế thì vẫn phải sống - gói trong kho dùng nó.
# ============================================================
import os        # noqa: E402
import tempfile  # noqa: E402
from pathlib import Path  # noqa: E402

CATALOG_GIA = {"version": 1, "connectors": [dict(KHUON_URL, name="Giả URL", category="Khác",
                                                 status="ready", default_perm="readonly")]}

with tempfile.TemporaryDirectory() as tmp:
    os.environ["JAVIS_STATE_DIR"] = tmp
    # Hai bước, thiếu bước nào thì test ghi thẳng vào kho kết nối THẬT của người đang chạy:
    #
    # (1) Nạp lại `config` nữa, không chỉ hai module dưới: `config.STATE_DIR` tính MỘT LẦN lúc
    #     import, và `mcp_store` lấy nó bằng `from config import STATE_DIR`.
    # (2) Tạo sẵn một file store RỖNG trong thư mục tạm. `mcp_store._load` có đường lui về
    #     `server/mcp_servers.json` khi file ở STATE_DIR chưa tồn tại, nên một thư mục tạm
    #     trống vẫn rơi đúng vào kho thật.
    #
    # Đã xảy ra thật: máy chủ repo tích được 7 kết nối rác sau nhiều lượt chạy, rồi lượt sau
    # lấy nhầm hàng của lượt trước nên test đỏ oan.
    (Path(tmp) / "mcp_servers.json").write_text('{"version": 2, "connections": []}',
                                                encoding="utf-8")
    duong_gia = Path(tmp) / "catalog-gia.json"
    duong_gia.write_text(json.dumps(CATALOG_GIA, ensure_ascii=False), encoding="utf-8")
    for mod in ("mcp_store", "secrets_store", "config"):
        sys.modules.pop(mod, None)
    import config as _cfg_moi   # noqa: E402
    check("STATE_DIR trỏ vào thư mục tạm", str(_cfg_moi.STATE_DIR) == tmp, _cfg_moi.STATE_DIR)
    mc.CATALOG_PATH = duong_gia
    mc._cache.update(sig=None, by_id={})
    import mcp_store  # noqa: E402
    check("kho tạm rỗng - không đọc nhầm kho thật", not mcp_store.list_connections())

    cid, err = mcp_store.add_connection("gia-url", {
        "fields": {"base_url": "cty.vi.du/home/workflows?x=1", "token": "TOK123"},
        "label": "thử url_template"})
    check("thêm được kết nối từ khuôn có url_template", not err, err)
    if not err:
        r = [x for x in mcp_store.resolved(enabled_only=False) if x["connector_id"] == "gia-url"][0]
        check("resolved: URL ghép đúng từ ô địa chỉ",
              r["url"] == "https://cty.vi.du/mcp-server/http", r["url"])
        check("resolved: header Bearer đúng token",
              r["headers"] == {"Authorization": "Bearer TOK123"}, r["headers"])
        check("resolved: mặc định mức Chỉ đọc", r["perm"] == "readonly", r["perm"])

        mcp_store.update_connection(cid, {"fields": {"base_url": "https://moi.vi.du",
                                                     "token": "TOK456"}})
        r2 = [x for x in mcp_store.resolved(enabled_only=False) if x["connector_id"] == "gia-url"][0]
        check("CANARY: user sửa địa chỉ thì URL đi theo, không kẹt địa chỉ cũ",
              r2["url"] == "https://moi.vi.du/mcp-server/http", r2["url"])
        check("user đổi token thì header đi theo",
              r2["headers"] == {"Authorization": "Bearer TOK456"}, r2["headers"])

print()
if loi:
    print("ĐỎ " + str(len(loi)) + ": " + ", ".join(loi))
    sys.exit(1)
print("XANH - cơ chế catalog còn nguyên")
