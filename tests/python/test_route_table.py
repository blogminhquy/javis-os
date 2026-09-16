"""Ảnh chụp bảng route - dây bảo hiểm cho đợt chẻ nhỏ main.py.

    python tests/run.py route_table            # so khớp (CI chạy cái này)
    python tests/run.py route_table --update   # chụp lại sau khi CỐ Ý đổi route

Vì sao cần: giai đoạn 4 của docs/superpowers/specs/2026-07-28-tai-cau-truc-server-design.md
bóc ~20 nhóm route từ main.py ra các module APIRouter riêng. Bóc đúng thì bảng route phải y
hệt từng ký tự. Test này biến "chắc là không sai" thành "chứng minh được", và bắt luôn cả
lỗi đổi thứ tự đăng ký.

Từ fastapi 0.141 (Javis 0.59.19), router con KHÔNG còn được gộp phẳng vào `app.routes` nữa
mà nằm trong một đối tượng bọc, nên hàm snapshot() phải đi đệ quy - xem chú thích của nó.

Khi test đỏ mà bạn KHÔNG cố ý đổi route thì đó là bug của lần bóc vừa rồi, đừng --update.
Chỉ --update khi thật sự thêm/xoá/đổi tên một endpoint, và commit file .json chung với thay đổi đó.

KHÔNG mạng. Dùng JAVIS_STATE_DIR tạm nên không đụng dữ liệu thật.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-routetest-"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import main  # noqa: E402

SNAPSHOT = Path(__file__).with_name("route_table.json")


def snapshot():
    """Mọi thứ gắn trên app: Route, WebSocketRoute, Mount, và route mặc định của FastAPI.

    Giữ cả thứ tự (khoá "order") vì Starlette khớp route theo thứ tự đăng ký - hai bảng
    cùng tập hợp nhưng khác thứ tự vẫn có thể định tuyến khác nhau khi có path chồng nhau.

    PHẢI ĐI ĐỆ QUY (từ 0.59.19): fastapi 0.115 gộp route của router con thẳng vào
    `app.routes`, nhưng fastapi 0.141 BỌC mỗi `include_router` thành một đối tượng
    `_IncludedRouter` và giữ route con bên trong nó. Bản đầu của hàm này chỉ đi một tầng, nên
    sau khi nâng thư viện nó thấy 245 mục thay vì 304 và báo MẤT 67 route (/kanban,
    /reminders, /loops, /learn, /packs, /domain, /graph...). Đã kiểm bằng request thật: cả 67
    route ĐỀU CÒN CHẠY, chỉ là nằm sâu hơn một tầng. Đi một tầng thì ảnh chụp này lặng lẽ
    thôi canh đúng 67 route đó - hỏng đúng cái việc nó sinh ra để làm.
    """
    out = []
    da_di = set()

    def di(routes, trong=None):
        for r in routes:
            out.append({
                "order": len(out),
                "type": type(r).__name__,
                "path": getattr(r, "path", None),
                "name": getattr(r, "name", None),
                "methods": sorted(getattr(r, "methods", None) or []),
                # "trong": order của route BỌC nó, để đọc ảnh chụp còn biết nhóm nào ở đâu.
                # None = gắn thẳng lên app.
                "trong": trong,
            })
            cha = out[-1]["order"]
            # Route con nằm ở `.routes` (Mount, Router) hoặc ở `.original_router.routes`
            # (_IncludedRouter của fastapi 0.141 - nó KHÔNG có .routes, đây là chỗ duy nhất
            # còn giữ 67 route của tám nhóm include_router).
            con = getattr(r, "routes", None)
            if not con:
                con = getattr(getattr(r, "original_router", None), "routes", None)
            # id() chặn vòng lặp nếu có ngày router trỏ vòng vào nhau. Mount của StaticFiles
            # có .routes nhưng rỗng, nên nhánh này không đụng gì tới nó.
            if con and id(r) not in da_di:
                da_di.add(id(r))
                di(con, trong=cha)

    di(main.app.routes)
    return out


def _fmt(e):
    m = ",".join(e["methods"]) or "-"
    return f'[{e["order"]:3d}] {e["type"]:<15} {m:<20} {e["path"]}  (name={e["name"]})'


def main_():
    cur = snapshot()

    if "--update" in sys.argv:
        # newline="\n" cố ý: file này bị sinh lại nhiều lần trong đợt chẻ main.py, mà git
        # chuẩn hoá về LF khi commit. Không ép ở đây thì trên Windows file ghi ra CRLF và
        # `git status` cứ báo bẩn sau mỗi lần --update dù nội dung không đổi.
        SNAPSHOT.write_text(
            json.dumps(cur, ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8", newline="\n",
        )
        print(f"Đã chụp lại {len(cur)} mục vào {SNAPSHOT.name}")
        print("Nhớ commit file này CHUNG với thay đổi route, kèm lý do trong commit message.")
        return 0

    if not SNAPSHOT.exists():
        print(f"FAIL thiếu {SNAPSHOT.name}. Chạy: python test_route_table.py --update")
        return 1

    old = json.loads(SNAPSHOT.read_text(encoding="utf-8"))

    if old == cur:
        n_ep = sum(1 for e in cur if e["type"] in ("APIRoute", "APIWebSocketRoute",
                                                   "Route", "WebSocketRoute"))
        print(f"ok  bảng route khớp: {len(cur)} mục ({n_ep} endpoint), đúng thứ tự")
        return 0

    # So theo khoá tự nhiên trước, rồi mới soi thứ tự - báo lỗi cho ra lỗi.
    def key(e):
        return (e["path"], tuple(e["methods"]), e["type"])

    old_k = {key(e): e for e in old}
    cur_k = {key(e): e for e in cur}

    added = [cur_k[k] for k in cur_k.keys() - old_k.keys()]
    removed = [old_k[k] for k in old_k.keys() - cur_k.keys()]
    moved = [
        (old_k[k], cur_k[k])
        for k in old_k.keys() & cur_k.keys()
        if old_k[k]["order"] != cur_k[k]["order"] or old_k[k]["name"] != cur_k[k]["name"]
    ]

    print(f"FAIL bảng route đổi: {len(old)} mục -> {len(cur)} mục")
    if removed:
        print(f"\n  MẤT {len(removed)} route:")
        for e in sorted(removed, key=lambda x: x["order"]):
            print("   -", _fmt(e))
    if added:
        print(f"\n  THÊM {len(added)} route:")
        for e in sorted(added, key=lambda x: x["order"]):
            print("   +", _fmt(e))
    if moved:
        print(f"\n  ĐỔI THỨ TỰ hoặc ĐỔI TÊN {len(moved)} route:")
        for o, c in sorted(moved, key=lambda x: x[1]["order"]):
            print(f'   ~ {c["path"]}  order {o["order"]}->{c["order"]}  '
                  f'name {o["name"]}->{c["name"]}')
    print("\n  Không cố ý đổi route thì đây là bug của lần bóc vừa rồi.")
    print("  Cố ý đổi thì chạy: python test_route_table.py --update")
    return 1


if __name__ == "__main__":
    sys.exit(main_())
