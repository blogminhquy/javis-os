"""Vì sao máy này không có nút "Cập nhật ngay" - phải nói ra được, không được im.

Chạy:  python tests/python/test_nut_cap_nhat_ly_do.py

/version có thử hỏi GitHub xem bản mới nhất là gì; hỏi trượt thì nó tự nuốt lỗi vào trường
`error`, nên test này chạy được cả khi không có mạng - chỉ chậm hơn vài giây.

Chủ repo báo (2026-08-12): "một số máy VPS không có nút update, anh không hiểu vì sao".

Điều tra ra: KHÔNG có lỗi nào cả. Watchtower - thứ nhận lệnh từ nút bấm - nằm trong
`profiles: ["update"]` của docker-compose.yml, nên `docker compose up -d` quen tay không bật
nó. Máy nào từng chạy `--profile update` thì có nút, máy nào không thì không. Đúng thiết kế.

Nhưng app gộp hai lý do rất khác nhau vào MỘT câu chung chung ("cập nhật bằng Redeploy"),
nên người dùng không có cách nào tự biết máy mình thiếu gì:

  - watchtower_off: bật được, bằng đúng một lệnh.
  - no_token:      không bật được (stack Hostinger), phải Redeploy.

Gộp lại là cướp mất thông tin duy nhất người dùng cần. Nên thứ file này canh không phải là
"có tự cập nhật được không" mà là "có NÓI RA ĐÚNG lý do không".
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os, sys, asyncio, tempfile, re, io
os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-nutcapnhat-")

_fails = []
def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)

import main  # noqa: E402

# ============================================================
# 1. Mã lý do phân biệt được hai trường hợp
# ============================================================
check("có hàm trả mã lý do", callable(getattr(main, "_watchtower_ly_do", None)))

_token_cu = os.environ.get("WATCHTOWER_TOKEN")

# Không có token = stack Hostinger, nơi CỐ TÌNH không kèm Watchtower.
os.environ.pop("WATCHTOWER_TOKEN", None)
check("CANARY: không có token -> no_token (Hostinger, không bật được)",
      asyncio.run(main._watchtower_ly_do()) == "no_token")

# Có token nhưng không nối được tới container: đây là VPS chạy `docker compose up -d` mà quên
# `--profile update`. Trong test không có host "watchtower" nên nối là trượt - đúng tình huống.
os.environ["WATCHTOWER_TOKEN"] = "javis-update"
check("CANARY: có token mà không nối được -> watchtower_off (bật được bằng 1 lệnh)",
      asyncio.run(main._watchtower_ly_do()) == "watchtower_off")

# Hàm bool cũ vẫn phải đúng: /update còn dùng nó, và test_update.py còn vá đè lên nó.
check("hàm bool cũ còn dùng được", asyncio.run(main._watchtower_reachable()) is False)

if _token_cu is None:
    os.environ.pop("WATCHTOWER_TOKEN", None)
else:
    os.environ["WATCHTOWER_TOKEN"] = _token_cu

# ============================================================
# 2. /version phải ĐEM mã lý do ra cho UI
# ============================================================
# Không có trường này thì frontend không có gì để phân biệt, và mọi việc ở trên thành vô ích.
_mode_cu = main._deploy_mode
_lydo_cu = main._watchtower_ly_do

async def _lydo_off():
    return "watchtower_off"

async def _lydo_ok():
    return ""

main._deploy_mode = lambda: "docker"
main._watchtower_ly_do = _lydo_off
_r = asyncio.run(main.version_info())
check("/version có trường self_update_off", "self_update_off" in _r)
check("CANARY: docker không watchtower -> báo đúng mã", _r.get("self_update_off") == "watchtower_off")
check("docker không watchtower -> can_self_update False", _r.get("can_self_update") is False)

main._watchtower_ly_do = _lydo_ok
_r2 = asyncio.run(main.version_info())
check("docker CÓ watchtower -> tự cập nhật được", _r2.get("can_self_update") is True)
check("tự cập nhật được thì không kèm lý do", _r2.get("self_update_off") == "")

# native/windows luôn tự cập nhật được và KHÔNG được đi dò watchtower (tốn 4 giây timeout cho
# một thứ không liên quan - máy Windows làm gì có compose network nào).
async def _no_goi():
    raise AssertionError("native/windows KHÔNG được dò watchtower")

main._deploy_mode = lambda: "native"
main._watchtower_ly_do = _no_goi
_r3 = asyncio.run(main.version_info())
check("native luôn tự cập nhật được", _r3.get("can_self_update") is True)
check("CANARY: native KHÔNG đi dò watchtower", _r3.get("self_update_off") == "")

main._deploy_mode = _mode_cu
main._watchtower_ly_do = _lydo_cu

# ============================================================
# 3. Dashboard phải nói ra LỆNH BẬT, không chỉ nói "thiếu Watchtower"
# ============================================================
# Biết mình thiếu gì mà không biết gõ gì thì vẫn tắc. Lệnh này là toàn bộ giá trị của bản vá.
CON = io.open(os.path.join(ROOT, "dashboard", "console.js"), encoding="utf-8").read()
check("dashboard đọc mã lý do từ server", "self_update_off" in CON)
check("CANARY: nhánh watchtower_off chỉ ra ĐÚNG lệnh bật",
      "docker compose --profile update up -d" in CON)
check("nhánh no_token nói Hostinger dùng Redeploy",
      re.search(r'no_token[\s\S]{0,600}Redeploy', CON) is not None)
# Chủ repo gõ đúng lệnh rồi vẫn lãnh "no configuration file provided: not found" - đứng sai thư
# mục, vì tên thư mục tuỳ lúc clone (javis hay javis-os). Bảo người ta "chạy ở thư mục chứa file
# compose" là đúng nhưng vô dụng khi họ KHÔNG BIẾT nó nằm đâu. Docker biết, nên phải hỏi nó.
check("CANARY: có cách TÌM thư mục compose, không chỉ bảo 'đúng thư mục'",
      "com.docker.compose.project.working_dir" in CON)
check("gọi tên đúng câu báo lỗi để người dùng nhận ra mình",
      "no configuration file provided" in CON)
# Server cũ chưa trả mã lý do (app mới, server chưa update): không được vỡ, giữ câu cũ.
check("thiếu mã lý do vẫn có câu dự phòng",
      re.search(r'docker compose up -d --pull always', CON) is not None)

# ============================================================
# 4. Tiền đề: Watchtower THẬT SỰ nằm trong profile update
# ============================================================
# Cả bản vá dựa trên sự thật này. Ngày nào ai đó bỏ profile đi thì lời khuyên trong app thành
# sai, mà không có gì báo - nên canh thẳng vào file compose.
COMPOSE = io.open(os.path.join(ROOT, "docker-compose.yml"), encoding="utf-8").read()
check("CANARY: watchtower vẫn nằm trong profiles [update]",
      re.search(r'watchtower:[\s\S]{0,400}profiles:\s*\["update"\]', COMPOSE) is not None)
# Hostinger cố tình không có watchtower - nhánh no_token dựa vào đúng điều này.
HOST = io.open(os.path.join(ROOT, "docker-compose.hostinger.yml"), encoding="utf-8").read()
check("CANARY: stack Hostinger vẫn không có service watchtower",
      re.search(r'^\s{2}watchtower:', HOST, re.M) is None)

# Tài liệu phải ghi cùng một lệnh - lệch nhau là người dùng gõ theo tài liệu rồi vẫn không có nút.
for f in ("DEPLOY.md", "docs/01-bat-dau-thiet-lap.md", "docs/17-khac-phuc-su-co.md"):
    t = io.open(os.path.join(ROOT, f), encoding="utf-8").read()
    check(f"{f} ghi đúng lệnh bật Watchtower",
          "docker compose --profile update up -d" in t)

_sc = io.open(os.path.join(ROOT, "docs", "17-khac-phuc-su-co.md"), encoding="utf-8").read()
check("tài liệu sự cố có bảng phân biệt ba kiểu 'not found'",
      all(k in _sc for k in ("no configuration file provided",
                             "docker: command not found",
                             "is not a docker command")))

print("")
if _fails:
    print("THẤT BẠI " + str(len(_fails)) + ": " + ", ".join(_fails))
    sys.exit(1)
print("OK - test_nut_cap_nhat_ly_do: tất cả pass")
