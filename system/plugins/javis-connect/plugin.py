"""Plugin bundled: tool `javis_add_mcp` - đấu thêm MCP server vào kho Kết nối của Javis.

Vì sao tool này tồn tại
=======================
Người dùng bảo "thêm MCP này cho anh" thì trước bản này Javis không có đường nào ĐÚNG để làm.
Kho kết nối chỉ ghi được qua endpoint `/connect/add`, mà endpoint đó nằm sau lớp đăng nhập nên
chỉ trang web gọi được. Còn lại Javis chỉ có hai lối, cả hai đều hỏng theo cách riêng:

1. Chạy `claude mcp add ...` bằng Bash. Server đó rơi vào config RIÊNG của Claude Code, nên
   (a) chỉ mỗi engine Claude thấy, sáu bộ não còn lại đứng ngoài, (b) trên trang Kết nối nó
   không nằm ở khu "Đã kết nối" mà lọt xuống khu gập "Kết nối sẵn của Claude Code và Codex",
   khu này mặc định ĐÓNG và chỉ tải khi bấm mở. Người dùng nhìn trang Kết nối thấy y như cũ và
   kết luận Javis nói dối. Đó chính là bug được báo.
2. Nói suông "anh vào trang Kết nối tự thêm nhé". Đúng nhưng vô dụng, vì việc này Javis làm được.

Tool này đi thẳng vào `mcp_store` - CÙNG một kho mà trang Kết nối đọc (`/connect/catalog`), nên
thêm xong là thấy ngay ở khu "Đã kết nối", dùng chung cho MỌI bộ não qua hub, có phân quyền và
nhật ký như tài khoản đấu bằng tay.

An toàn (BẮT BUỘC, không tham số nào mở được)
=============================================
- `op=add` cần mức Toàn quyền (full), `op=find` chỉ cần safe; chatbot trả lời khách không thấy tool này
  (OWNER_ONLY_TOOLS trong mcp_hub.py). Vá bảo mật 2026-11-05: trước đó op=add chỉ cần safe, nên một
  chatbot mức "auto" do người lạ điều khiển, hay một việc nền mức auto, cắm được máy chủ MCP lạ vào kho
  CHUNG của mọi brain và bắt máy chủ Javis gọi tới địa chỉ bất kỳ, kể cả mạng nội bộ.
- Mức quyền mặc định là `readonly`. Luật `CLAUDE.md`: "Javis KHÔNG tự nâng quyền - user tự nâng ở
  trang Kết nối". Model chỉ được truyền `perm` cao hơn khi người dùng nói rõ họ muốn vậy, và câu
  trả lời phải nói ra mình đã đặt mức nào.
- Transport `stdio` = CHẠY MỘT LỆNH trên máy chủ Javis. Thêm xong để TẮT, không thử kết nối, vì
  chỉ riêng việc dial thử đã là chạy lệnh đó. Người dùng tự đọc lệnh rồi bật ở trang Kết nối.
  Không có tham số nào bật thẳng được: engine API vốn không có Bash, cho nó đẻ một stdio tự chạy
  là mở cửa hậu đúng bằng Bash.
- Dịch vụ đã có sẵn trong Kho kết nối (Gmail, Lịch, POS...) thì KHÔNG đẻ bản "custom" song song.
  Chúng cần đăng nhập OAuth hoặc key theo mẫu riêng; tool chỉ tay sang đúng card, vì một
  connection rỗng token nằm lại trang Kết nối trông y hệt tài khoản thật mà không chạy được
  (chính là vụ Meta Ads "xoá rồi cứ mọc lại" đã phải vá bằng tay ở `/connect/oauth/start`).
"""
from __future__ import annotations

import json
import re
import shlex

import mcp_catalog
import mcp_store

# Trần ký tự cho phần liệt kê ở op=find. Kết quả tool đi thẳng vào ngữ cảnh lượt chat và engine
# API còn bị cắt ở 8000 ký tự (engine._clip_tool_result) - kể cả kho 30 connector cũng không được
# nuốt mất câu hỏi của người dùng.
_FIND_MAX = 12

_TEN_HOP_LE = re.compile(r"^[^\x00-\x1f]{1,60}$")


def _chuoi(v) -> str:
    return str(v or "").strip()


def _cap_key_value(raw, dau_phan_cach) -> dict:
    """Đọc header/env model gõ ra. Nhận cả ba dạng vì mỗi model quen một kiểu: dict thật, chuỗi
    JSON, hoặc nhiều dòng "Khoá: giá trị" / "KHOA=giá trị". Dạng lạ thì bỏ qua chứ không nổ."""
    if isinstance(raw, dict):
        return {_chuoi(k): _chuoi(v) for k, v in raw.items() if _chuoi(k) and _chuoi(v)}
    text = _chuoi(raw)
    if not text:
        return {}
    if text.startswith("{"):
        try:
            d = json.loads(text)
            if isinstance(d, dict):
                return {_chuoi(k): _chuoi(v) for k, v in d.items() if _chuoi(k) and _chuoi(v)}
        except ValueError:
            pass
    out = {}
    for dong in text.replace("\\n", "\n").split("\n"):
        dong = dong.strip().lstrip("-").strip()
        if not dong or dau_phan_cach not in dong:
            continue
        k, v = dong.split(dau_phan_cach, 1)
        if _chuoi(k) and _chuoi(v):
            out[_chuoi(k)] = _chuoi(v)
    return out


def _tham_so(raw) -> list:
    """args của lệnh stdio: nhận mảng sẵn, hoặc chuỗi kiểu dòng lệnh ("-y abc --port 3000")."""
    if isinstance(raw, (list, tuple)):
        return [_chuoi(x) for x in raw if _chuoi(x)]
    text = _chuoi(raw)
    if not text:
        return []
    try:
        return [x for x in shlex.split(text) if x]
    except ValueError:
        return [x for x in text.split() if x]


def _chuan_url(u: str) -> str:
    return _chuoi(u).rstrip("/").lower()


def _trung(url: str, command: str, args: list):
    """Connection ĐÃ CÓ trỏ cùng chỗ, hoặc None. Chặn đẻ bản sao khi người dùng nhờ hai lần."""
    u = _chuan_url(url)
    cmd = _chuoi(command)
    for c in mcp_store.list_connections():
        if u and _chuan_url(c.get("url")) == u:
            return c
        if cmd and _chuoi(c.get("command")) == cmd and list(c.get("args") or []) == list(args):
            return c
    return None


def _tu_kho(tu_khoa: str) -> list:
    """Connector trong Kho kết nối khớp từ khoá (tìm trong tên, id, mô tả, nhóm)."""
    q = _chuoi(tu_khoa).lower()
    if not q:
        return []
    tu = [t for t in re.split(r"[^\w]+", q, flags=re.UNICODE) if len(t) >= 2]
    out = []
    for c in mcp_catalog.public_catalog():
        moi = " ".join([c.get("id", ""), c.get("name", ""), c.get("group", ""),
                        c.get("category", ""), c.get("description", "")]).lower()
        if q in moi or (tu and all(t in moi for t in tu)):
            out.append(c)
    return out


def _mo_ta_card(c: dict) -> str:
    o = [f"- {c.get('name')} (card '{c.get('group') or c.get('name')}' trong Kho kết nối"
         + (f", nhóm {c.get('category')}" if c.get("category") else "") + ")"]
    if c.get("auth_type") == "oauth":
        o.append("  Cần ĐĂNG NHẬP (OAuth) nên phải bấm ở trang Kết nối, Javis không đăng nhập hộ được.")
    else:
        ten_o = ", ".join(f.get("label") or f.get("key") for f in (c.get("fields") or []))
        o.append("  Cần điền: " + (ten_o or "không rõ, xem tại trang Kết nối") + ".")
    return "\n".join(o)


def _xem_o_dau(cid: str) -> str:
    return (f"Xem và chỉnh ở trang Kết nối, khu 'Đã kết nối' (mã {cid}): đổi tên, nâng mức quyền, "
            "bật/tắt, xoá.")


def _tim(args, ctx) -> str:
    q = _chuoi((args or {}).get("name")) or _chuoi((args or {}).get("url"))
    kho = _tu_kho(q)
    dang_co = mcp_store.list_connections()
    dong = []
    if kho:
        dong.append(f"Kho kết nối có sẵn {len(kho)} dịch vụ khớp '{q}':")
        dong += [_mo_ta_card(c) for c in kho[:_FIND_MAX]]
        if len(kho) > _FIND_MAX:
            dong.append(f"…(+{len(kho) - _FIND_MAX} dịch vụ nữa, xem đủ ở trang Kết nối)")
        dong.append("Dịch vụ trong kho thì đấu bằng card của nó chứ ĐỪNG thêm kiểu tự khai URL - "
                    "card mới có sẵn mẫu đăng nhập và phân loại tool đọc/ghi.")
    else:
        dong.append(f"Kho kết nối không có dịch vụ nào khớp '{q}'. Nếu người dùng đưa được địa chỉ "
                    "MCP (URL) hoặc lệnh chạy thì gọi lại tool này với op=add để tự khai.")
    if dang_co:
        dong.append("")
        dong.append("Đang đấu sẵn: " + ", ".join(
            f"{c.get('label')}{'' if c.get('enabled') else ' (đang tắt)'}" for c in dang_co[:_FIND_MAX]))
    return "\n".join(dong)


async def _them(args, ctx) -> str:
    args = args or {}
    ten = _chuoi(args.get("name"))
    url = _chuoi(args.get("url"))
    command = _chuoi(args.get("command"))
    tham_so = _tham_so(args.get("args"))

    # Lệnh gõ nguyên cụm ("npx -y abc") là kiểu model hay viết nhất - tách ra chứ đừng bắt
    # người dùng gõ lại cho vừa ý máy.
    if command and not tham_so and (" " in command):
        phan = _tham_so(command)
        command, tham_so = phan[0], phan[1:]

    if not _TEN_HOP_LE.match(ten):
        return ("ERROR: thiếu name - đặt tên hiển thị cho nguồn này (vd 'Context7', 'POS shop 2'). "
                "Tên này là thứ người dùng thấy ở trang Kết nối.")

    if not url and not command:
        kho = _tu_kho(ten)
        if kho:
            return ("Chưa đấu gì cả. Dịch vụ này ĐÃ CÓ SẴN trong Kho kết nối, đấu bằng card của nó "
                    "chứ không tự khai:\n" + "\n".join(_mo_ta_card(c) for c in kho[:_FIND_MAX])
                    + "\nNói người dùng mở trang Kết nối, tìm card đó rồi bấm Kết nối. "
                    "Javis không tự đăng nhập hộ được.")
        return ("ERROR: thiếu url (MCP chạy qua mạng) hoặc command (MCP chạy bằng lệnh trên máy). "
                "Hỏi người dùng địa chỉ MCP, hoặc gọi op=find để tra xem Kho kết nối có sẵn dịch vụ này chưa.")

    cu = _trung(url, command, tham_so)
    if cu:
        return (f"Đã có sẵn rồi, KHÔNG thêm trùng: '{cu.get('label')}' "
                f"({'đang bật' if cu.get('enabled') else 'ĐANG TẮT, bật lại ở trang Kết nối'}), "
                f"mức quyền {cu.get('perm')}. " + _xem_o_dau(cu.get("id")))

    transport = _chuoi(args.get("transport")).lower()
    if transport not in ("http", "sse", "stdio"):
        transport = "stdio" if command else "http"
    if transport == "stdio" and not command:
        return "ERROR: transport=stdio thì phải có command (lệnh chạy MCP server)."
    if transport in ("http", "sse") and not url:
        return f"ERROR: transport={transport} thì phải có url."

    perm = _chuoi(args.get("perm")).lower()
    if perm not in mcp_catalog.PERM_RANK:
        perm = "readonly"

    cid, loi = mcp_store.add_connection("custom", {
        "label": ten,
        "transport": transport,
        "url": url,
        "command": command,
        "args": tham_so,
        "headers": _cap_key_value(args.get("headers"), ":"),
        "env": _cap_key_value(args.get("env"), "="),
        "perm": perm,
    })
    if loi:
        return f"ERROR: không thêm được - {loi}"

    import mcp_hub   # nạp muộn: mcp_hub nạp plugins_host, import ở đầu file là vòng tròn

    # stdio = chạy lệnh trên máy chủ. Để TẮT và KHÔNG dial thử (dial là chạy lệnh đó rồi).
    if transport == "stdio":
        mcp_store.update_connection(cid, {"enabled": False})
        mcp_hub.invalidate_cache()
        lenh = " ".join([command] + tham_so)
        return (f"Đã thêm '{ten}' vào trang Kết nối nhưng ĐỂ TẮT, vì nguồn này chạy bằng lệnh trên "
                f"máy chủ Javis: `{lenh}`. Người dùng tự đọc lệnh, thấy ổn thì bật ở trang Kết nối "
                f"(Javis không tự bật loại này). Mức quyền đang đặt: {perm}. " + _xem_o_dau(cid))

    val = await mcp_hub.validate_connection(cid)
    if not val.get("ok"):
        # KHÔNG xoá như `/connect/add` làm. Người dùng nhờ qua chat thì thứ họ cần là NHÌN THẤY
        # nó nằm đó và biết vì sao chưa chạy, chứ không phải một câu lỗi rồi trang Kết nối trống trơn.
        mcp_store.update_connection(cid, {"enabled": False})
        mcp_hub.invalidate_cache()
        return (f"Đã thêm '{ten}' vào trang Kết nối nhưng ĐỂ TẮT vì thử kết nối không được: "
                f"{val.get('error') or 'không rõ lý do'}\n"
                "Nói đúng lỗi này cho người dùng, gợi ý kiểm tra lại URL hoặc key rồi sửa và bật lại. "
                + _xem_o_dau(cid))

    if val.get("label") and not ten:
        mcp_store.update_connection(cid, {"label": val["label"]})
    mcp_hub.invalidate_cache()
    try:
        mcp_hub.codex_profile("full")   # để engine ChatGPT/Codex thấy nguồn mới ở lượt sau
    except Exception:
        pass
    return (f"Đã đấu xong '{ten}' và nó đang chạy: thấy {val.get('tools', 0)} tool, mức quyền "
            f"{perm} (mặc định an toàn, muốn cho ghi thì người dùng tự nâng ở trang Kết nối). "
            "Mọi bộ não đều dùng được nguồn này qua hub. " + _xem_o_dau(cid))


async def _chay(args, ctx) -> str:
    op = _chuoi((args or {}).get("op")).lower()
    if op == "add":
        return await _them(args, ctx)
    if op == "find":
        return _tim(args, ctx)
    return "ERROR: op phải là 'add' (đấu nguồn mới) hoặc 'find' (tra Kho kết nối xem đã có sẵn chưa)."


def register(ctx):
    ctx.register_tool(
        "javis_add_mcp",
        "Đấu thêm một MCP server vào kho Kết nối của Javis, để nó HIỆN ra trang Kết nối và MỌI bộ "
        "não dùng chung. Dùng tool này mỗi khi người dùng bảo thêm/đấu/nối một MCP hay một nguồn "
        "dữ liệu; TUYỆT ĐỐI không dùng `claude mcp add` hay `codex mcp add` (rơi vào config riêng "
        "của một CLI, người dùng không thấy trên trang Kết nối). "
        "op=find: tra xem Kho kết nối có sẵn dịch vụ đó chưa (gọi trước khi tự khai URL). "
        "op=add: cần name, cộng url (MCP qua mạng) hoặc command (MCP chạy bằng lệnh). headers cho "
        "key dạng 'Authorization: Bearer xxx'. Mức quyền mặc định là chỉ đọc; chỉ truyền perm cao "
        "hơn khi người dùng nói rõ. Nguồn chạy bằng lệnh luôn được thêm ở trạng thái TẮT để người "
        "dùng tự duyệt. Báo lại cho người dùng biết nó nằm ở trang Kết nối.",
        _chay,
        schema={
            "type": "object",
            "properties": {
                "op": {"type": "string", "enum": ["add", "find"]},
                "name": {"type": "string", "description": "Tên hiển thị ở trang Kết nối (op=add), "
                                                          "hoặc từ khoá dịch vụ (op=find)"},
                "url": {"type": "string", "description": "Địa chỉ MCP, vd https://mcp.abc.com/mcp"},
                "command": {"type": "string", "description": "Lệnh chạy MCP trên máy, vd npx"},
                "args": {"type": "string", "description": "Tham số của lệnh, vd '-y @abc/mcp-server'"},
                "transport": {"type": "string", "enum": ["http", "sse", "stdio"]},
                "headers": {"type": "string", "description": "Header xác thực, mỗi dòng 'Khoá: giá trị'"},
                "env": {"type": "string", "description": "Biến môi trường cho lệnh, mỗi dòng 'KHOA=giá trị'"},
                "perm": {"type": "string", "enum": ["readonly", "safe", "full"],
                         "description": "Mặc định readonly. Chỉ nâng khi người dùng yêu cầu rõ."},
            },
            "required": ["op"],
        },
        min_mode="safe",
        op_modes={"add": "full", "find": "safe"},
        emoji="🔌",
    )
