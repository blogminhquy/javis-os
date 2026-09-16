"""Ô form RỖNG được coi là KHÔNG GỬI - luật của fastapi, ghim lại để không ai bị bất ngờ.

    python tests/run.py form_chuoi_rong     (KHÔNG mạng)

Bối cảnh 0.59.19, phát hiện khi nâng fastapi 0.115.0 -> 0.141.1: một phép thử đỏ vì gửi
`path=""` không còn vào tới hàm nữa. Truy ra thì đây là thay đổi ngữ nghĩa của fastapi, và
nó áp cho MỌI endpoint nhận form:

    fastapi 0.115: thân form lấy giá trị bằng `.get()` thẳng -> chuỗi rỗng VÀO TỚI HÀM.
                   (luật "rỗng = không gửi" chỉ áp cho query/header/cookie)
    fastapi 0.141: thân form cũng đi qua `_get_multidict_value` -> chuỗi rỗng bị coi là
                   KHÔNG GỬI.

Hệ quả có HAI mặt, mặt thứ hai mới đáng sợ:
  1. `Form(...)` (bắt buộc) nhận "" -> 422, không vào hàm. Ồn ào, dễ thấy.
  2. `Form(<mặc định>)` nhận "" -> hàm nhận chính CÁI MẶC ĐỊNH, không phải "". Im lặng. Với
     `Form(None)` mà hàm hiểu None là "đừng đụng tới trường này" thì một cú "xoá trắng ô
     này" biến thành "giữ nguyên" - không lỗi, không log, người dùng tưởng đã xoá.

ĐÃ SOI TOÀN BỘ khi nâng (16/09), và kết luận là mặt thứ hai KHÔNG chạm Javis hôm nay: cả chín
chỗ dashboard gửi ô rỗng (`content`, `due`, `endpoint`, `path` của mkdir, `provider`/`model`/
`brain` của sessions/model, `lang` của /stt, `id` của thu hồi token) đều rơi vào field khai
`Form("")`, mà mặc định "" thì nhận "" hay nhận mặc định cũng như nhau. Riêng `id` của thu hồi
token là `Form(...)`, nhưng nó chỉ rỗng khi hàng token không có id, và 422 hay lỗi của hàm thì
đều là "không thu hồi được".

File này ghim LUẬT, để lần sau ai thêm một endpoint `Form(None)` rồi cho dashboard gửi ô rỗng
vào đó thì còn có chỗ đọc mà hiểu vì sao trường của mình tự về mặc định.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import re
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-formrong-"))

from fastapi import FastAPI, Form   # noqa: E402
from fastapi.testclient import TestClient   # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- 1. Luật của fastapi, đo trên một app tí hon cho khỏi lẫn với logic của Javis ----
_app = FastAPI()


@_app.post("/bat-buoc")
def _bb(x: str = Form(...)):
    return {"x": x}


@_app.post("/mac-dinh-rong")
def _mdr(x: str = Form("")):
    return {"x": x}


@_app.post("/mac-dinh-none")
def _mdn(x: str = Form(None)):
    return {"x": x, "la_none": x is None}


@_app.post("/mac-dinh-chu")
def _mdc(x: str = Form("MAC_DINH")):
    return {"x": x}


_c = TestClient(_app)

r = _c.post("/bat-buoc", data={"x": ""})
check("Form(...) nhận ô rỗng -> 422, KHÔNG vào hàm", r.status_code == 422)
check("và lý do là 'thiếu trường' chứ không phải lỗi khác",
      r.status_code == 422 and r.json()["detail"][0]["type"] == "missing")
check("Form(...) nhận giá trị thật thì vẫn vào hàm",
      _c.post("/bat-buoc", data={"x": "co"}).json() == {"x": "co"})

check("Form('') nhận ô rỗng -> hàm nhận '' (mặc định trùng nên KHÔNG đổi hành vi)",
      _c.post("/mac-dinh-rong", data={"x": ""}).json() == {"x": ""})

check("Form(None) nhận ô rỗng -> hàm nhận None, KHÔNG phải ''",
      _c.post("/mac-dinh-none", data={"x": ""}).json().get("la_none") is True)

check("Form('MAC_DINH') nhận ô rỗng -> hàm nhận 'MAC_DINH', KHÔNG phải ''",
      _c.post("/mac-dinh-chu", data={"x": ""}).json() == {"x": "MAC_DINH"})

# ---- 2. Chín chỗ dashboard gửi ô rỗng phải rơi vào field khai Form("") ----
# Canary thật: nó đọc mã nguồn, nên thêm một chỗ gửi rỗng vào field Form(None) là đỏ.
SRC = (SERVER / "main.py").read_text(encoding="utf-8", errors="replace")

# (đường dẫn endpoint, tên ô mà dashboard gửi rỗng)
GUI_O_RONG = [
    ("/files/write", "content"),
    ("/files/mkdir", "path"),
    ("/files/taskadd", "due"),
    ("/ollama-local/endpoint", "endpoint"),
    ("/sessions/{session_id}/model", "model"),
    ("/stt", "lang"),
]


def khai_cua(duong, o):
    """Chuỗi khai tham số `o` trong hàm ngay dưới @app.post(duong). None nếu không thấy."""
    m = re.search(r'@app\.post\("' + re.escape(duong) + r'"\)\s*\n(?:async )?def [^(]+\((.*?)\)\s*(?:->[^:]+)?:',
                  SRC, re.S)
    if not m:
        return None
    m2 = re.search(re.escape(o) + r"\s*:\s*[^=,]+=\s*(Form\([^)]*\))", m.group(1))
    return m2.group(1) if m2 else None


for duong, o in GUI_O_RONG:
    khai = khai_cua(duong, o)
    check(f"đọc được khai báo của ô '{o}' ở {duong}", khai is not None)
    if khai is not None:
        check(f"{duong}: ô '{o}' khai Form(\"\") nên ô rỗng vẫn là '' (đang là {khai})",
              khai == 'Form("")')

if _fails:
    print("\nFAIL:", len(_fails), _fails)
    raise SystemExit(1)
print("\nOK - form_chuoi_rong")
