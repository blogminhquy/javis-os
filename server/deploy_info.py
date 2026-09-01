"""Javis đang chạy Ở ĐÂU - dùng chung cho updater và các tính năng cần biết "cùng máy hay không".

Tách khỏi main.py vì `ollama_local.py` cần hai hàm này, mà main.py thì import ollama_local -
để nguyên là một vòng import. Repo này đã có 3 vòng đang phải phá bằng mẹo import-trong-hàm
(xem .github/workflows/ci.yml), nên thêm vòng thứ tư là đi ngược hướng dọn dẹp.

main.py giữ nguyên tên `_deploy_mode`/`_host_platform` như hai lớp vỏ mỏng gọi vào đây, nên
mọi chỗ gọi cũ không phải sửa.
"""
from __future__ import annotations

import os
import sys


def deploy_mode() -> str:
    """docker | windows | native - quyết định cách cập nhật, VÀ quyết định Javis có đứng
    trên cùng máy vật lý với thứ nó đang nói chuyện hay không."""
    if os.path.exists("/.dockerenv") or os.getenv("JAVIS_STATE_DIR", "").startswith("/data"):
        return "docker"
    if os.name == "nt":
        return "windows"
    return "native"


def host_platform() -> str:
    """windows | mac | linux - nền tảng thật của máy (để UI ghi đúng nhãn, vd Mac cũng là
    mode 'native' nhưng không có systemd)."""
    if os.name == "nt":
        return "windows"
    return "mac" if sys.platform == "darwin" else "linux"
