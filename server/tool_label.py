"""Mô tả NGẮN một lệnh gọi công cụ, để khối tiến trình trong khung chat ghi rõ đang làm gì.

Chủ repo báo 2026-09-24: khối "Đang chạy công cụ" chỉ có một cột "Đang gọi: Bash", "Đang gọi:
Read" lặp hai chục lần, nhìn không biết lệnh nào chạy, file nào được đọc. Engine CÓ gửi tham
số của lệnh gọi lên (Claude/Grok/Antigravity: `input`, Codex: `item` thô), chỉ là main.py
vứt đi, gửi mỗi cái tên xuống dashboard.

`chi_tiet` rút từ tham số đó ra MỘT dòng người đọc được: lệnh shell, đường dẫn file, mẫu tìm,
URL, câu tìm kiếm. Không đoán được thì trả "" và dashboard giữ nhãn cũ, không bịa.

Chỉ đọc, không ném lỗi: payload lạ kiểu gì cũng chỉ ra chuỗi rỗng.
"""
import json

TRAN = 160   # một dòng trong khung chat; dài hơn thì cắt, bản đầy đủ không cần cho mắt người

# Thứ tự ưu tiên: khoá nói "việc gì" (description của Bash, do model tự viết cho người đọc)
# đứng trước khoá chi tiết kỹ thuật (command). Đường dẫn, URL, câu tìm đứng sau.
_KHOA = ("description", "command", "cmd", "file_path", "notebook_path", "path", "url",
         "pattern", "query", "q", "prompt", "skill", "name", "title", "text")


def _mot_dong(s: str) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= TRAN else s[:TRAN - 1].rstrip() + "…"


def _rut_gon_duong(s: str) -> str:
    """Đường dẫn tuyệt đối dài (/root/.javis/brains/x/wiki/a.md) chỉ giữ 3 đoạn cuối."""
    if len(s) > 40 and (s.startswith("/") or (len(s) > 2 and s[1] == ":")) and " " not in s:
        manh = s.replace("\\", "/").rstrip("/").split("/")
        if len(manh) > 3:
            return "…/" + "/".join(manh[-3:])
    return s


def _tu_dict(d: dict, sau: int = 0) -> str:
    if sau > 3 or not isinstance(d, dict):
        return ""
    for k in _KHOA:
        v = d.get(k)
        if isinstance(v, list) and v and all(isinstance(x, str) for x in v):
            v = " ".join(v)            # Codex: command là mảng ["bash", "-lc", "..."]
        if isinstance(v, str) and v.strip():
            v = v.strip()
            if k in ("command", "cmd"):
                # "bash -lc '<lệnh>'" của Codex: phần có nghĩa là lệnh bên trong.
                for dau in ("bash -lc ", "sh -c ", "/bin/bash -lc ", "/bin/sh -c "):
                    if v.startswith(dau):
                        v = v[len(dau):].strip().strip("'\"")
                        break
            return _rut_gon_duong(v)
    # Codex apply_patch: changes = [{path: ...}, ...] hoặc {path: {...}}
    ch = d.get("changes")
    if isinstance(ch, list):
        ds = [c.get("path") for c in ch if isinstance(c, dict) and c.get("path")]
        if ds:
            return ", ".join(_rut_gon_duong(p) for p in ds[:3]) + (" …" if len(ds) > 3 else "")
    if isinstance(ch, dict) and ch:
        ds = list(ch.keys())
        return ", ".join(_rut_gon_duong(p) for p in ds[:3]) + (" …" if len(ds) > 3 else "")
    # `arguments` là chuỗi JSON (function_call của Codex, MCP) hoặc dict lồng.
    for k in ("arguments", "input", "parameters", "args"):
        v = d.get(k)
        if isinstance(v, str) and v.strip()[:1] == "{":
            try:
                v = json.loads(v)
            except Exception:
                v = None
        if isinstance(v, dict):
            r = _tu_dict(v, sau + 1)
            if r:
                return r
    return ""


def chi_tiet(ev) -> str:
    """Một dòng mô tả lệnh gọi từ sự kiện `tool_call` của engine. "" khi không rút được."""
    try:
        if not isinstance(ev, dict):
            return ""
        for k in ("input", "item"):
            r = _tu_dict(ev.get(k))
            if r:
                return _mot_dong(r)
    except Exception:
        pass
    return ""
