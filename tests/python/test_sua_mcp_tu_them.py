"""Sửa một MCP tự thêm: đổi URL, thay key, và XOÁ được header/env đã bỏ.

    python tests/run.py sua_mcp_tu_them

Trước 0.64.31 `update_connection` chỉ gộp thêm header: một header gõ sai tên (vd dán key của
Composio vào `Authorization` thay vì `x-consumer-api-key`) nằm lì trong kết nối, không có đường
gỡ ngoài xoá cả kết nối đi làm lại. Form Sửa mới gửi `prune: true` kèm đủ danh sách tên còn giữ.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import tempfile
from pathlib import Path

import mcp_store
import secrets_store

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


_tmp = Path(tempfile.mkdtemp(prefix="javis-mcp-sua-"))
mcp_store.STORE = _tmp / "mcp_servers.json"
mcp_store._LEGACY_STORE = _tmp / "khong-co.json"
mcp_store.CONFIG = _tmp / ".mcp_config.json"


def headers(cid):
    c = next(x for x in mcp_store._load()["connections"] if x["id"] == cid)
    return secrets_store.decrypt_map(c.get("headers") or {}), secrets_store.decrypt_map(c.get("env") or {}), c

sid = mcp_store.add_server({"name": "composio", "transport": "http", "url": "https://a.example/mcp",
                            "auth": "header", "headers": {"Authorization": "ck_sai", "x-trace": "1"}})
check("thêm được", bool(sid))

# Sửa kiểu cũ (không prune): chỉ gộp, giữ nguyên hành vi cho mọi chỗ gọi khác.
mcp_store.update_server(sid, {"headers": {"x-consumer-api-key": "ck_dung"}})
h, _, _ = headers(sid)
check("không prune thì chỉ gộp thêm", h == {"Authorization": "ck_sai", "x-trace": "1", "x-consumer-api-key": "ck_dung"})

# Form Sửa: bỏ Authorization, giữ x-trace (giá trị rỗng = giữ cũ), đổi URL.
mcp_store.update_server(sid, {"url": "https://b.example/mcp", "prune": True,
                              "headers": {"x-consumer-api-key": "", "x-trace": ""}})
h, _, c = headers(sid)
check("prune xoá header đã bỏ, giữ giá trị cũ khi để trống", h == {"x-trace": "1", "x-consumer-api-key": "ck_dung"})
check("đổi được URL", c["url"] == "https://b.example/mcp")

# Đổi hẳn sang chạy lệnh: header cũ phải đi hết, env mới vào.
mcp_store.update_server(sid, {"transport": "stdio", "url": "", "command": "npx", "args": ["-y", "pkg"],
                              "prune": True, "headers": {}, "env": {"TOKEN": "t1"}})
h, e, c = headers(sid)
check("đổi sang stdio: header cũ bị dọn", h == {})
check("đổi sang stdio: env mới được lưu", e == {"TOKEN": "t1"})
check("đổi sang stdio: lệnh và tham số", c["transport"] == "stdio" and c["command"] == "npx" and c["args"] == ["-y", "pkg"])
check("_public chỉ lộ tên key, không lộ giá trị",
      mcp_store.get_connection(sid)["env_keys"] == ["TOKEN"] and "t1" not in str(mcp_store.get_connection(sid)))

if _fails:
    raise SystemExit(f"{len(_fails)} FAIL")
print("Tất cả xanh")
