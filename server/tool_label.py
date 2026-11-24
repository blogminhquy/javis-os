"""Mô tả NGẮN một lệnh gọi công cụ, để khối tiến trình trong khung chat ghi rõ đang làm gì.

Chủ repo báo 2026-09-24: khối "Đang chạy công cụ" chỉ có một cột "Đang gọi: Bash", "Đang gọi:
Read" lặp hai chục lần, nhìn không biết lệnh nào chạy, file nào được đọc. Engine CÓ gửi tham
số của lệnh gọi lên (Claude/Grok/Antigravity: `input`, Codex: `item` thô), chỉ là main.py
vứt đi, gửi mỗi cái tên xuống dashboard.

`chi_tiet` rút từ tham số đó ra MỘT dòng người đọc được: lệnh shell, đường dẫn file, mẫu tìm,
URL, câu tìm kiếm. Không đoán được thì trả "" và dashboard giữ nhãn cũ, không bịa.

Chỉ đọc, không ném lỗi: payload lạ kiểu gì cũng chỉ ra chuỗi rỗng.

Keys are matched without regard to case (owner, 2026-11-24): Antigravity names its parameters in
PascalCase (`CommandLine`, `Path`, `AbsolutePath`, `TargetFile`, measured on agy 1.5.15), so a
lowercase-only lookup gave every agy step an empty label and the chat showed a bare "Run command",
"Read file" twenty times over.
"""
import json

TRAN = 160   # một dòng trong khung chat; dài hơn thì cắt, bản đầy đủ không cần cho mắt người

# Order of preference, all lowercase: the key that says WHAT is being done (Bash's description,
# Antigravity's toolSummary, both written by the model for a human) comes before the technical
# detail (command). Paths, URLs and search text come after.
_KEYS = ("description", "toolsummary", "command", "cmd", "commandline",
         "file_path", "notebook_path", "absolutepath", "targetfile", "path",
         "directorypath", "url", "uri",
         "pattern", "query", "q", "searchpath", "searchdirectory", "prompt", "skill", "name", "title", "text")

# A shell wrapper around the real command: what the reader needs is the command inside.
_SHELL_PREFIXES = ("bash -lc ", "sh -c ", "/bin/bash -lc ", "/bin/sh -c ",
                   "cmd.exe /c ", "cmd /c ")


def _one_line(s: str) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= TRAN else s[:TRAN - 1].rstrip() + "…"


def _shorten_path(s: str) -> str:
    """Đường dẫn tuyệt đối dài (/root/.javis/brains/x/wiki/a.md) chỉ giữ 3 đoạn cuối."""
    if len(s) > 40 and (s.startswith("/") or (len(s) > 2 and s[1] == ":")) and " " not in s:
        parts = s.replace("\\", "/").rstrip("/").split("/")
        if len(parts) > 3:
            return "…/" + "/".join(parts[-3:])
    return s


def _unwrap_shell(v: str) -> str:
    low = v.lower()
    for prefix in _SHELL_PREFIXES:
        if low.startswith(prefix):
            return v[len(prefix):].strip().strip("'\"")
    return v


def _from_dict(d: dict, depth: int = 0) -> str:
    if depth > 3 or not isinstance(d, dict):
        return ""
    lowered = {}
    for k, v in d.items():
        lowered.setdefault(str(k).lower(), v)
    for k in _KEYS:
        v = lowered.get(k)
        if isinstance(v, list) and v and all(isinstance(x, str) for x in v):
            v = " ".join(v)            # Codex: command là mảng ["bash", "-lc", "..."]
        if isinstance(v, str) and v.strip():
            v = v.strip()
            if k in ("command", "cmd", "commandline"):
                v = _unwrap_shell(v)
            return _shorten_path(v)
    # Codex apply_patch: changes = [{path: ...}, ...] hoặc {path: {...}}
    ch = lowered.get("changes")
    if isinstance(ch, list):
        paths = [c.get("path") for c in ch if isinstance(c, dict) and c.get("path")]
        if paths:
            return ", ".join(_shorten_path(p) for p in paths[:3]) + (" …" if len(paths) > 3 else "")
    if isinstance(ch, dict) and ch:
        paths = list(ch.keys())
        return ", ".join(_shorten_path(p) for p in paths[:3]) + (" …" if len(paths) > 3 else "")
    # `arguments` là chuỗi JSON (function_call của Codex, MCP) hoặc dict lồng.
    for k in ("arguments", "input", "parameters", "args"):
        v = lowered.get(k)
        if isinstance(v, str) and v.strip()[:1] == "{":
            try:
                v = json.loads(v)
            except Exception:
                v = None
        if isinstance(v, dict):
            r = _from_dict(v, depth + 1)
            if r:
                return r
    return ""


def chi_tiet(ev) -> str:
    """Một dòng mô tả lệnh gọi từ sự kiện `tool_call` của engine. "" khi không rút được."""
    try:
        if not isinstance(ev, dict):
            return ""
        for k in ("input", "item"):
            r = _from_dict(ev.get(k))
            if r:
                return _one_line(r)
    except Exception:
        pass
    return ""
