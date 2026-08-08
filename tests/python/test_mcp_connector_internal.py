"""Connector NỘI BỘ (Substack, Botcake) phải đi qua vòng dò tool như mọi connector khác.

    python tests/python/test_mcp_connector_internal.py

Không cần pytest, KHÔNG chạm mạng (`list_tools` của hai module này trả danh sách tĩnh).

Bệnh (Javis tự chẩn ra 2026-08-08, đã kiểm lại bằng mã): kết nối Substack bật, quyền full,
token còn sống, trang Kết nối hiện "Đã kết nối" - mà KHÔNG bộ não nào gọi được tool nào của
nó, và không có một dòng lỗi ở đâu cả.

Nguyên nhân: ba chỗ cùng hỏi một câu "connection này có server để dial không", và cả ba đều
tự viết tay `not (url or command)`:

  - `mcp_client.discover_resolved`   -> quét sạch khỏi vòng dò (đây là chỗ làm tool biến mất)
  - `mcp_hub.validate_connection`    -> nút Test trả "ổn" mà chưa hề gọi thử
  - `connect_health`                 -> đèn sức khoẻ xanh vĩnh viễn

Transport `internal` gọi thẳng một module Python trong repo nên nó KHÔNG có url cũng KHÔNG có
command, và rơi trọn vào nhánh "không có server". Hai chỗ sau còn tệ hơn chỗ đầu: chúng nói
rằng mọi thứ ổn, nên không có đường nào để phát hiện ra chỗ đầu đang hỏng.

Cách sửa: MỘT hàm dùng chung `mcp_client.co_server_de_dial`. File này canh cả hành vi lẫn
việc ba chỗ đó thật sự gọi hàm chung, vì bệnh gốc chính là ba bản chép tay trôi lệch.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import asyncio
import sys
from pathlib import Path

import mcp_client

loi = []


def check(ten, dieu_kien, them=""):
    print(("ok   " if dieu_kien else "FAIL ") + ten + (("  [" + repr(them) + "]") if them and not dieu_kien else ""))
    if not dieu_kien:
        loi.append(ten)


def conn(**kw):
    """Đúng hình dạng `mcp_store.resolved()` trả ra."""
    c = {"id": "c1", "connector_id": "x", "label": "X", "slug": "x", "namespace": "x",
         "transport": "http", "url": "", "command": "", "args": [], "headers": {}, "env": {},
         "internal": "", "secrets": {}, "config": {}, "perm": "full", "deny_tools": [],
         "is_default": False, "auth": None, "connector": {}}
    c.update(kw)
    return c


SUBSTACK = conn(id="c_sub", connector_id="substack", namespace="substack", transport="internal",
                internal="substack", secrets={"token": "x", "publication": "y"})
BOTCAKE = conn(id="c_bc", connector_id="botcake", namespace="botcake", transport="internal",
               internal="botcake")
# Connection chỉ giữ token OAuth cho một plugin dùng (Meta Ads Graph API). Đây là thứ câu chặn
# ban đầu SINH RA để loại, và nó vẫn phải bị loại.
OAUTH_ONLY = conn(id="c_meta", connector_id="meta-ads-graph", namespace="meta", auth="oauth")


# ---- 1. Câu hỏi "có server để dial không" trả lời đúng cho cả năm dạng ----

check("internal Substack: CÓ server để dial", mcp_client.co_server_de_dial(SUBSTACK))
check("internal Botcake: CÓ server để dial", mcp_client.co_server_de_dial(BOTCAKE))
check("OAuth-only: KHÔNG (đây là thứ câu chặn sinh ra để loại)",
      not mcp_client.co_server_de_dial(OAUTH_ONLY))
check("http có url: CÓ", mcp_client.co_server_de_dial(conn(url="https://a.b/mcp")))
check("stdio có command: CÓ", mcp_client.co_server_de_dial(conn(transport="stdio", command="npx")))
# Bản ghi hỏng: cho đi tiếp chỉ đổi một lỗi im lặng thành KeyError mỗi vòng dò.
check("internal mà thiếu tên module: KHÔNG",
      not mcp_client.co_server_de_dial(conn(transport="internal", internal="")))
check("internal với tên module lạ: KHÔNG",
      not mcp_client.co_server_de_dial(conn(transport="internal", internal="khong-co-that")))


# ---- 2. Vòng dò thật sự nhìn thấy tool của connector nội bộ ----

ts, route = asyncio.run(mcp_client.discover_resolved([SUBSTACK, BOTCAKE, OAUTH_ONLY]))
ten = [t["fn"] for t in ts]

check("Substack ra tool", any(t.startswith("substack__") for t in ten), ten[:4])
check("Botcake ra tool", any(t.startswith("botcake__") for t in ten), ten[:4])
check("OAuth-only KHÔNG ra tool nào", not any(t.startswith("meta__") for t in ten), ten)
check("tool đăng ký được vào bảng định tuyến để gọi",
      all(f in route for f in ten) and len(route) == len(ten))
check("ba tool cốt lõi của Substack đều có",
      {"substack__substack_list_drafts", "substack__substack_create_draft",
       "substack__substack_publish"} <= set(ten), ten)
check("route giữ đúng mức quyền của connection để hub còn chặn",
      all((route[f].get("conn") or {}).get("perm") == "full" for f in ten))


# ---- 3. Ba chỗ hỏi cùng một câu phải gọi CÙNG một hàm ----
# Bệnh gốc là ba bản chép tay trôi lệch, nên đây mới là phần giữ cho nó không tái phát.

def src(ten_file):
    return (Path(SERVER) / ten_file).read_text(encoding="utf-8")

CLI, HUB, HEALTH = src("mcp_client.py"), src("mcp_hub.py"), src("connect_health.py")

check("vòng dò gọi hàm chung", "if not co_server_de_dial(spec):" in CLI)
check("nút Test gọi hàm chung", "if not mcp_client.co_server_de_dial(conn):" in HUB)
check("vòng kiểm sức khoẻ gọi hàm chung", "if not mcp_client.co_server_de_dial(conn):" in HEALTH)

# Không còn bản chép tay nào sót lại. So trên DÒNG MÃ thật: chuỗi cũ còn nằm trong chú thích
# kể lại con bọ, và một test bắt cả chú thích thì cấm luôn việc ghi lại vì sao đã sửa.
for ten_file, noi_dung in (("mcp_client.py", CLI), ("mcp_hub.py", HUB),
                           ("connect_health.py", HEALTH)):
    dong_ma = [d for d in noi_dung.split("\n") if not d.strip().startswith("#")]
    con_sot = [d.strip() for d in dong_ma
               if 'get("url")' in d and 'get("command")' in d and ("if not" in d or "continue" in d)]
    check(f"{ten_file}: không còn bản chép tay của câu chặn", not con_sot, con_sot)

check("hàm chung nói rõ vì sao internal khác OAuth-only",
      "internal" in CLI.split("def co_server_de_dial")[1][:1600] and
      "Substack" in CLI.split("def co_server_de_dial")[1][:1600])


print()
if loi:
    print(f"{len(loi)} test ĐỎ: " + ", ".join(loi))
    sys.exit(1)
print("Tất cả test xanh.")
