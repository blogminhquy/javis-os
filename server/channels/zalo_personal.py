"""Kênh Zalo CÁ NHÂN: tài khoản đã quét QR ở trang Kết nối (MCP `zalo-agent-cli`). Đọc tin bằng
vòng cursor ở `zalo_personal_channel`, gửi tin bằng tool `zalo_send_message` của chính MCP đó.

Gửi từ kênh này là gửi DƯỚI DANH TÍNH CHỦ (không phải bot), nên Hộp thư nói rõ điều đó ở ô
soạn tin; ngoài ra nó là một kênh như mọi kênh khác, không có mục riêng nào trên giao diện.
"""
from __future__ import annotations

from channels import KenhSpec

SPEC = KenhSpec(
    id="zalo_personal", nhan="Zalo cá nhân", kind="account", logo="zalo", mau="#0068FF",
    tom_tat="Tài khoản Zalo của chính bạn. Ghi khi bật, trả lời dưới tên bạn.",
    nang_luc={"nhom": True, "gui_chu": True, "gui_file": False},
)


def tai_khoan():
    import zalo_personal_channel
    return zalo_personal_channel.tai_khoan()


def bat(account_id: str, on: bool) -> dict:
    import zalo_personal_channel
    return zalo_personal_channel.bat(account_id, on)


def trang_thai() -> dict:
    import zalo_personal_channel
    return zalo_personal_channel.trang_thai()


async def gui(tk: dict, chat_id: str, text: str, chat_type: str = "private"):
    """Gửi qua MCP: tham số theo mcp-guide của zalo-agent-cli (threadId, text, type 0|1)."""
    import zalo_personal_channel
    conn = zalo_personal_channel.ket_noi_theo_id(str(tk.get("id") or tk.get("external_id") or ""))
    if not conn:
        return False, "tài khoản Zalo này không còn ở trang Kết nối (hoặc đang tắt)"
    try:
        d = await zalo_personal_channel._goi(conn, "zalo_send_message", {
            "threadId": str(chat_id), "text": str(text or ""),
            "type": 1 if str(chat_type or "") == "group" else 0,
        })
    except Exception as e:
        return False, str(e)[:300]
    if isinstance(d, dict) and d.get("success") is False:
        return False, str(d.get("error") or d.get("message") or "Zalo từ chối")[:300]
    return True, ""
