"""Plugin bundled: gửi ẢNH / FILE qua Zalo.

Vì sao có plugin này. MCP chuẩn của `zalo-agent-cli` chỉ khai đúng `text` cho
`zalo_send_message`, nên Javis tạo được ảnh (tool `javis_generate_image`) hay xuất được báo
cáo mà vẫn không gửi cho ai qua Zalo được. Trong khi thư viện bên dưới (`zca-js`) làm được từ
lâu: `sendMessage({ msg, attachments: [...] }, threadId, type)`, và chính CLI đó đã có lệnh
`msg send-image` / `msg send-file` dùng đúng dạng ấy. Bản 1.6.2 là bản MỚI NHẤT trên npm, nên
chờ upstream phơi thêm tham số là chờ vô hạn.

Cách làm: gọi lại CHÍNH cái CLI đó bằng lệnh con nó đã có, với `HOME` trỏ vào đúng thư mục
phiên của kết nối Zalo đang đăng nhập. Không fork package Node, không viết lại giao thức, và
không bắt user quét QR lần thứ hai - phiên nằm trong HOME cô lập (xem server/zalo_login.py) và
`mcp_store.resolved()` đã tính sẵn đường dẫn đó cho mỗi kết nối. Lấy từ đó chứ không tự ghép
lại, để một nguồn sự thật duy nhất về "phiên Zalo nằm ở đâu".

`min_mode: full`: gửi tin ra ngoài là hành động THẬT và không rút lại được, đúng hạng với
`zalo_send_message` vốn đã nằm trong nhóm `danger` của connector.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import zalo_cli

# Phần dùng chung (chọn kết nối, dựng lệnh an toàn, chạy tiến trình con, đọc kết quả) nằm ở `server/zalo_cli.py` vì plugin
# `zalo-group` cần y hệt. Các tên dưới đây giữ lại làm điểm nối để test còn thay được từng chỗ chạm thế giới thật.
CONNECTOR_ID = zalo_cli.CONNECTOR_ID
_CLI_PACKAGE = zalo_cli.CLI_PACKAGE
_MAX_FILES = 10                          # gửi cả chục file một lượt đã là bất thường
_TIMEOUT = zalo_cli.DEFAULT_TIMEOUT      # tải file lên Zalo có thể lâu, nhưng không lâu vô hạn

# Đuôi Zalo hiểu là ẢNH. Còn lại đi đường send-file (docx, pdf, zip...). Gửi nhầm đường thì
# CLI báo lỗi khó hiểu, nên chia ở đây cho rõ.
_ANH = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def _ket_noi_zalo():
    """Các kết nối Zalo đang BẬT, kèm env đã tính sẵn (trong đó có HOME của phiên). Xem `zalo_cli.connections`."""
    return zalo_cli.connections()


def _check():
    if not shutil.which("npx"):
        return ("Máy chạy Javis chưa có Node.js 20+ (lệnh npx) nên không gửi được ảnh Zalo. "
                "Cài tại nodejs.org rồi thử lại.")
    if not _ket_noi_zalo():
        return ("Chưa đấu tài khoản Zalo nào. Vào trang Kết nối, chọn 'Zalo Agent MCP', "
                "quét QR bằng app Zalo rồi gọi lại tool này.")
    return None


def _duong_dan_that(p, vault_root):
    """Đường dẫn người gọi đưa vào -> đường dẫn tuyệt đối ĐÃ KIỂM TRA, hoặc (None, lý do).

    Nhận đường dẫn tương đối GỐC VAULT (đúng quy ước Javis vẫn ghi trong chat, vd
    'attachments/anh.jpg') hoặc tuyệt đối. Nhưng dù đường nào thì kết quả cũng PHẢI nằm trong
    vault: thiếu rào này thì một câu chat khéo léo là gửi được /etc/passwd hay file khoá ra
    ngoài qua Zalo, và tin đã gửi thì không thu hồi được.
    """
    raw = str(p or "").strip()
    if not raw:
        return None, "đường dẫn rỗng"
    if not vault_root:
        return None, "chưa biết brain đang dùng nên không kiểm được đường dẫn"
    root = Path(vault_root).resolve()
    cand = Path(raw)
    full = (cand if cand.is_absolute() else root / cand)
    try:
        full = full.resolve()
    except OSError as e:
        return None, f"đường dẫn không hợp lệ ({e})"
    try:
        full.relative_to(root)
    except ValueError:
        return None, f"'{raw}' nằm NGOÀI brain - chỉ gửi được file trong brain"
    if not full.is_file():
        return None, f"không thấy file '{raw}'"
    return full, None


async def _chay(argv, home):
    """Chạy lệnh con trong HOME của phiên Zalo. Xem `zalo_cli.run` (cờ không cửa sổ console nằm ở đó)."""
    return await zalo_cli.run(argv, home, _TIMEOUT)


async def _send(args, ctx):
    args = args or {}
    loi = _check()
    if loi:
        return "ERROR: " + loi

    thread_id = str(args.get("thread_id") or "").strip()
    if not thread_id:
        return ("ERROR: thiếu thread_id. Tìm bằng tool zalo_search_threads hoặc zalo_list_threads "
                "rồi truyền đúng threadId vào đây.")

    paths = args.get("paths")
    if isinstance(paths, str):
        paths = [paths]
    paths = [p for p in (paths or []) if str(p or "").strip()]
    if not paths:
        return "ERROR: thiếu paths (danh sách đường dẫn file trong brain, vd attachments/anh.jpg)."
    if len(paths) > _MAX_FILES:
        return f"ERROR: tối đa {_MAX_FILES} file mỗi lần gửi, đang đưa vào {len(paths)}."

    thuc = []
    for p in paths:
        full, why = _duong_dan_that(p, ctx.vault_root)
        if why:
            return "ERROR: " + why
        thuc.append(full)

    # Trộn ảnh với file trong MỘT lệnh là Zalo hiển thị sai kiểu, nên chia theo đuôi và chỉ
    # cho một loại mỗi lượt - nói thẳng thay vì tự đoán rồi gửi ra thứ người nhận thấy khác ý.
    la_anh = [f.suffix.lower() in _ANH for f in thuc]
    if any(la_anh) and not all(la_anh):
        return ("ERROR: một lượt chỉ gửi được cùng một loại - hoặc toàn ẢNH, hoặc toàn FILE. "
                "Gọi tool hai lần cho hai nhóm.")
    lenh = "send-image" if all(la_anh) else "send-file"

    conns = _ket_noi_zalo()
    cid = str(args.get("connection_id") or "").strip()
    if cid:
        chon = [c for c in conns if c["id"] == cid]
        if not chon:
            return f"ERROR: không có kết nối Zalo nào id '{cid}'."
    elif len(conns) == 1:
        chon = conns
    else:
        # Nhiều tài khoản mà đoán bừa là gửi đi dưới danh tính người khác - hỏi lại rẻ hơn nhiều.
        ds = "; ".join(f"{c['label']} (id={c['id']})" for c in conns)
        return f"ERROR: đang có {len(conns)} tài khoản Zalo, hãy nêu rõ connection_id. Danh sách: {ds}"

    try:
        ttype = int(args.get("thread_type", 0))
    except (TypeError, ValueError):
        ttype = 0
    if ttype not in (0, 1):
        ttype = 0
    caption = str(args.get("caption") or "")

    options = ["-t", str(ttype)]
    if caption:
        options += ["-m", caption]
    argv = zalo_cli.build_argv(["msg", lenh], [thread_id] + [str(f) for f in thuc], options)
    if argv is None:
        return "ERROR: máy chưa có Node.js 20+ (lệnh npx)."
    why = zalo_cli.unsafe_for_cmd(argv)
    if why:
        return "ERROR: " + why

    rc, out, err = await _chay(argv, chon[0]["home"])
    if rc is None:
        return f"ERROR: gửi Zalo {err}. File nặng thì thử gửi từng cái một."
    # CLI KHÔNG đặt mã thoát khác 0 khi Zalo từ chối (xem zalo_cli.interpret): chỉ tin khi có JSON ở stdout.
    ok, _data, loi = zalo_cli.interpret(rc, out, err)
    if not ok:
        return f"ERROR: {loi}"
    return json.dumps({
        "ok": True,
        "sent": len(thuc),
        "kind": "image" if lenh == "send-image" else "file",
        "thread_id": thread_id,
        "thread_type": ttype,
        "account": chon[0]["label"],
        "files": [f.name for f in thuc],
        "caption": caption,
    }, ensure_ascii=False)


def register(ctx):
    ctx.register_tool(
        name="zalo_send_image",
        description=(
            "Gửi ẢNH (hoặc file) qua Zalo kèm lời nhắn, bằng tài khoản Zalo đã đấu ở trang Kết nối. "
            "Dùng khi cần gửi ảnh vừa tạo, ảnh trong brain, hay file báo cáo - tool zalo_send_message "
            "chỉ gửi được chữ. Tham số: thread_id (lấy từ zalo_search_threads/zalo_list_threads), "
            "paths (danh sách đường dẫn trong brain), caption, thread_type (0=cá nhân, 1=nhóm). "
            "Một lượt gửi cùng loại: hoặc toàn ảnh, hoặc toàn file."
        ),
        handler=_send, min_mode="full", check_fn=_check,
        schema={
            "type": "object",
            "properties": {
                "thread_id": {"type": "string",
                              "description": "threadId của cuộc chat Zalo (từ zalo_search_threads)"},
                "paths": {"type": "array", "items": {"type": "string"},
                          "description": "Đường dẫn file, tương đối gốc brain (vd attachments/anh.jpg). "
                                         f"Tối đa {_MAX_FILES} file, phải nằm trong brain."},
                "caption": {"type": "string", "description": "Lời nhắn gửi kèm (tuỳ chọn)"},
                "thread_type": {"type": "integer", "enum": [0, 1],
                                "description": "0 = chat cá nhân, 1 = nhóm. Mặc định 0."},
                "connection_id": {"type": "string",
                                  "description": "id kết nối Zalo, chỉ cần khi đã đấu nhiều tài khoản"},
            },
            "required": ["thread_id", "paths"],
        },
    )
