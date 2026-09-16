"""Đường dẫn dùng chung cho mọi test Python, và nạp server/ vào sys.path.

Vì sao có file này: trước 0.9.242 các test nằm CHUNG thư mục với mã nguồn, nên chúng lấy
đường dẫn bằng `Path(__file__).parent` (ra server/) và `Path(__file__).parent.parent` (ra
gốc repo). Khi test dọn sang tests/python/ thì cả hai lệch một tầng, và 37 chỗ như vậy nằm
rải trong 30 file. Gom về một chỗ thì sửa một lần, và lần sau có dời nữa cũng chỉ sửa ở đây.

Import nó cũng đồng thời NẠP server/ vào sys.path, nên test gọi `import main` được từ bất kỳ
thư mục làm việc nào. Trước đây test phải chạy đúng từ server/ mới import được; nay không còn
ràng buộc đó, kể cả với các test mở file nguồn bằng đường dẫn.

    from _paths import ROOT, SERVER     # đặt TRƯỚC mọi `import <module server>`

Ngoài đường dẫn, file này giữ `moi_duong_dan(app)`: cách DUY NHẤT đúng để liệt kê đường dẫn
của app. Xem chú thích của hàm - đọc thẳng `app.routes` là sai từ fastapi 0.141.
"""
import sys
from pathlib import Path

# tests/python/_paths.py -> parents[0]=python, [1]=tests, [2]=gốc repo
ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
DASHBOARD = ROOT / "dashboard"
SYSTEM = ROOT / "system"

if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))


def moi_route(app):
    """Mọi route của app, ĐI ĐỆ QUY qua các router con. Trả danh sách đối tượng route.

    VÌ SAO KHÔNG ĐỌC THẲNG `app.routes` (0.59.19): fastapi 0.115 gộp route của
    `include_router` thẳng vào `app.routes`, nhưng fastapi 0.141 BỌC mỗi lần include thành
    một đối tượng `_IncludedRouter` và giữ route con trong `.original_router.routes`. Đối
    tượng bọc đó KHÔNG có `.path`, nên code cũ hoặc nổ AttributeError (test_cli_kenh) hoặc
    im lặng không thấy 67 endpoint (test_jobs, test_route_table) - kiểu thứ hai tệ hơn, vì
    một phép thử "endpoint này phải còn" sẽ đỏ oan, còn phép thử "endpoint này phải mất" thì
    xanh oan.
    """
    ra, da_di = [], set()

    def di(routes):
        for r in routes:
            ra.append(r)
            con = getattr(r, "routes", None)
            if not con:
                con = getattr(getattr(r, "original_router", None), "routes", None)
            if con and id(r) not in da_di:
                da_di.add(id(r))
                di(con)

    di(getattr(app, "routes", []) or [])
    return ra


def moi_duong_dan(app):
    """Tập hợp đường dẫn của mọi route, đi đệ quy. Xem moi_route()."""
    return {getattr(r, "path", "") for r in moi_route(app)}
