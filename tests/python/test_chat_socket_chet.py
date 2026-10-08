"""Socket chết mà không đóng: trang tự phát hiện và nối lại, không để "đang suy nghĩ" đếm mãi (0.85.11).

    python tests/run.py chat_socket_chet      (KHÔNG mạng)

Lỗi thật, khách báo 08/10/2026 kèm ảnh: ra lệnh xong Javis xử lý một lúc rồi đứng im, chip
"Javis đang suy nghĩ..." đếm tới 5 phút, phải gửi lại câu lệnh mới chạy tiếp.

Gốc: máy ngủ, đổi Wi-Fi, router rớt kết nối thì trình duyệt vẫn giữ WebSocket ở trạng thái OPEN
và không bao giờ gọi onclose. Lượt chat vẫn chạy xong trên server (job không thuộc socket), nhưng
câu trả lời không tới được trang. Bộ hồi sức cũ chỉ chạy khi tab bị ẩn quá 20 giây, mà máy ngủ
thường không phát sự kiện đó. Gửi lại câu lệnh "chữa" được chỉ vì lần ghi vào socket chết làm nó
lộ ra, rồi socket mới kéo về câu trả lời đã có sẵn.

Điều được ghim:
  1. Trang ghi mốc khung cuối cùng nhận được; im quá 30 giây thì gửi `ping`, 10 giây không có gì
     về thì bỏ socket đó (gỡ handler để onclose cũ không nối trùng) và nối socket mới.
  2. Server trả `pong` cho `ping` ngay trong vòng nhận, không đụng lượt đang chạy.
  3. `pong` không đi vào handleMessage.
  4. Nút Dừng luôn gửi thêm qua HTTP /stop: lệnh Dừng gửi vào socket chết là rơi mất.
  5. Socket mới chào "hello" mà phiên đang xem không còn chạy thì bỏ chip "đang suy nghĩ" còn sót.
"""
from _paths import ROOT, SERVER, DASHBOARD  # noqa: E402,F401
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

APP = (DASHBOARD / "app.js").read_bytes().decode("utf-8")
MAIN = (SERVER / "main.py").read_text(encoding="utf-8")

_fails = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else f"  [{detail!r}]"))
    if not cond:
        _fails.append(name)


def fn(name):
    i = APP.index(f"function {name}(")
    j = APP.index("\n}\n", i)
    return APP[i:j]


check("ngưỡng im 30 giây, chờ pong 10 giây", "const WS_IM_MS = 30000, WS_PONG_MS = 10000;" in APP)
check("kiểm socket theo nhịp", "setInterval(_checkSocket, 5000);" in APP)

conn = fn("connect")
check("mỗi khung nhận được đều dời mốc và xoá ping đang chờ",
      "_wsLastFrameAt = Date.now(); _wsPingAt = 0;" in conn and "ws.onmessage" in conn)
check("pong không vào handleMessage", 'if (data.type !== "pong") handleMessage(data);' in conn)

chk = fn("_checkSocket")
check("chỉ kiểm socket OPEN và tab đang hiện", "ws.readyState !== WebSocket.OPEN" in chk and "document.hidden" in chk)
check("im quá ngưỡng thì gửi ping", 'action: "ping"' in chk and "now - _wsLastFrameAt < WS_IM_MS" in chk)
check("ping không ai đáp thì bỏ socket", "now - _wsPingAt > WS_PONG_MS) _dropDeadSocket()" in chk)

drop = fn("_dropDeadSocket")
check("bỏ socket cũ: gỡ handler để onclose cũ không nối trùng",
      "cu.onclose = null" in drop and "cu.onmessage = null" in drop and drop.index("ws = null") < drop.index("connect()"))
check("bỏ socket cũ: báo đứt mạng rồi nối lại", "baoDutMang(true)" in drop and "connect();" in drop)

stop = fn("stopCurrent")
check("Dừng luôn gửi thêm qua HTTP /stop",
      re.search(r"\n  if \(sid\) \{\s*\n(\s*//.*\n)*\s*fetch\(\"/stop\"", stop) is not None
      and "} else if (sid) {" not in stop)

i = APP.index('if (data.type === "hello") {')
hello = APP[i:APP.index("guiTinDutMang();", i)]
check("hello: phiên đang xem không còn chạy thì bỏ chip còn sót",
      "!(turns[savedSessionId] && turns[savedSessionId].running)) hideActivity();" in hello
      and hello.index("(data.running || []).forEach") < hello.index("hideActivity()"))

i = MAIN.index('            if action == "ping":')
seg = MAIN[i:i + 400]
check("server trả pong cho ping rồi đi tiếp vòng nhận",
      'await send_client({"type": "pong"})' in seg and "continue" in seg
      and MAIN.index('            if action == "ping":') < MAIN.index('            if action == "stop":'))

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả xanh.")
