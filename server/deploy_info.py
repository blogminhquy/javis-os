"""Javis đang chạy Ở ĐÂU - dùng chung cho updater và các tính năng cần biết "cùng máy hay không".

Tách khỏi main.py vì `ollama_local.py` cần hai hàm này, mà main.py thì import ollama_local -
để nguyên là một vòng import. Repo này đã có 3 vòng đang phải phá bằng mẹo import-trong-hàm
(xem .github/workflows/ci.yml), nên thêm vòng thứ tư là đi ngược hướng dọn dẹp.

main.py giữ nguyên tên `_deploy_mode`/`_host_platform` như hai lớp vỏ mỏng gọi vào đây, nên
mọi chỗ gọi cũ không phải sửa.
"""
from __future__ import annotations

import os
import socket
import struct
import sys


def deploy_mode() -> str:
    """docker | windows | native - quyết định cách cập nhật, VÀ quyết định Javis có đứng
    trên cùng máy vật lý với thứ nó đang nói chuyện hay không."""
    if os.path.exists("/.dockerenv") or os.getenv("JAVIS_STATE_DIR", "").startswith("/data"):
        return "docker"
    if os.name == "nt":
        return "windows"
    return "native"


def docker_gateway() -> str:
    """IP của MÁY CHỦ nhìn từ trong container ("" nếu không đọc được / không ở trong Docker).

    Vì sao phải DÒ chứ không viết cứng 172.17.0.1: con số đó là cổng của mạng bridge MẶC ĐỊNH
    (docker0), chỉ đúng khi chạy `docker run` trần. Javis lại được cài bằng docker-compose, mà
    compose dựng một mạng RIÊNG cho từng project - dải cấp phát bắt đầu từ 172.18.0.0/16 trở
    đi vì 172.17 đã bị docker0 chiếm. Nên với gần như mọi người cài Javis theo hướng dẫn,
    172.17.0.1 là một địa chỉ SAI, điền vào là không nối được.

    Cổng mặc định trong bảng định tuyến của container CHÍNH LÀ máy chủ trên mạng bridge đó,
    nên đọc nó ra là có câu trả lời đúng cho từng máy, không phải đoán.
    """
    if deploy_mode() != "docker":
        return ""
    try:
        with open("/proc/net/route", encoding="utf-8") as f:
            for dong in f.readlines()[1:]:
                phan = dong.split()
                # Destination 00000000 = tuyến mặc định; Gateway là cột thứ ba, little-endian hex.
                if len(phan) > 2 and phan[1] == "00000000" and phan[2] != "00000000":
                    return socket.inet_ntoa(struct.pack("<L", int(phan[2], 16)))
    except (OSError, ValueError, struct.error):
        pass
    return ""


def host_platform() -> str:
    """windows | mac | linux - nền tảng thật của máy (để UI ghi đúng nhãn, vd Mac cũng là
    mode 'native' nhưng không có systemd)."""
    if os.name == "nt":
        return "windows"
    return "mac" if sys.platform == "darwin" else "linux"
