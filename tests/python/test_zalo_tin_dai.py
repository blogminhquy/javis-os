"""Tin bot soạn quá dài thì cắt thành nhiều tin trên Zalo cá nhân (0.171.2).

    python tests/run.py zalo_tin_dai      (KHÔNG mạng)

Chủ repo 16/10/2026: "Tin bot soạn quá dài thì Zalo từ chối, không gửi được gì. Đây là lần thứ 3
em gặp lỗi này, sau 2 lần của khách Khang Duy Dao." Hàm `gui` đẩy nguyên câu vào `zalo_send_message`
một lần, Zalo từ chối tin quanh 2000 ký tự, khách không nhận gì.

File này canh bốn chuyện, thiếu một là lỗi quay lại dưới dạng khác:
1. Cắt ở chỗ đọc tự nhiên (hết đoạn, hết câu), không cắt giữa chữ hay giữa link.
2. Gửi đủ, đúng thứ tự, và dừng ở đoạn đầu tiên hỏng.
3. Nhớ TỪNG đoạn là tiếng vọng, không thì vòng đọc tưởng chủ nhắn tay và bot im 10 phút.
4. Trong nhóm chỉ tag người được trả lời một lần.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-zalo-dai-")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import zalo_personal_channel as zc  # noqa: E402
from channels import zalo_personal as zp  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


# ============================================================
# 1. Cắt
# ============================================================
check("tin ngắn giữ nguyên một tin", zp.cat_tin("Dạ em chào anh ạ") == ["Dạ em chào anh ạ"])
check("tin rỗng thì không có đoạn nào", zp.cat_tin("   ") == [])

doan_van = ["Đoạn " + str(i) + ". " + "Nước mắm nhĩ cá cơm ủ chượp mười hai tháng. " * 12 for i in range(6)]
dai = "\n\n".join(doan_van)
ds = zp.cat_tin(dai)
check("tin dài bị cắt thành nhiều đoạn", len(ds) > 1, len(ds))
check("không đoạn nào vượt trần", all(len(x) <= zp.TIN_TOI_DA for x in ds), [len(x) for x in ds])
check("ghép lại không mất chữ nào", "".join(dai.split()) == "".join("".join(ds).split()))
check("cắt ở chỗ hết đoạn văn khi có", all(x.rstrip().endswith(".") for x in ds[:-1]), [x[-20:] for x in ds])

lien = ("Giá sỉ áp dụng từ 100 chai trở lên, giao toàn quốc trong ba ngày làm việc " * 40).strip()
ds = zp.cat_tin(lien)
check("không có xuống dòng thì cắt ở khoảng trắng, không cắt giữa chữ",
      all(len(x) <= zp.TIN_TOI_DA for x in ds) and all(not x.endswith("ngà") for x in ds)
      and "".join(lien.split()) == "".join("".join(ds).split()))

link = "https://shop.example.vn/san-pham/nuoc-mam-nhi-ca-com?utm_source=zalo&utm_campaign=thang10"
co_link = ("Anh xem thêm ở đây nhé " + link + " ") * 30
ds = zp.cat_tin(co_link)
check("CANARY: không link nào bị cắt đôi", sum(x.count(link) for x in ds) == 30, [x[-60:] for x in ds])

ds = zp.cat_tin("x" * (zp.TIN_TOI_DA * 2 + 10))
check("chuỗi liền không khoảng trắng thì cắt cứng, vẫn đủ trần",
      all(len(x) <= zp.TIN_TOI_DA for x in ds) and sum(len(x) for x in ds) == zp.TIN_TOI_DA * 2 + 10)

# ============================================================
# 2. Gửi
# ============================================================
GUI = []
HONG_O = {"lan": 0}


async def _goi_gia(conn, tool, args):
    if tool == "zalo_send_message":
        GUI.append(dict(args))
        if HONG_O["lan"] and len(GUI) == HONG_O["lan"]:
            return {"success": False, "error": "Zalo từ chối"}
        return {"success": True}
    return {}


zc._ket_noi = lambda: [{"id": "zalo-1", "label": "Zalo", "connector_id": "zalo"}]
zc._goi = _goi_gia
zp.NGHI_GIUA_DOAN = 0

dai = "\n\n".join(doan_van)
so_doan = len(zp.cat_tin(dai))
ok, loi = asyncio.run(zp.gui({"id": "zalo-1"}, "u1", dai))
check("tin dài: gửi được", ok and not loi, loi)
check("tin dài: gửi đủ số đoạn, mỗi đoạn một lần gọi", len(GUI) == so_doan, len(GUI))
check("tin dài: đúng thứ tự", [a["text"] for a in GUI] == zp.cat_tin(dai))
check("tin dài: không lần gọi nào vượt trần", all(len(a["text"]) <= zp.TIN_TOI_DA for a in GUI))

# Tiếng vọng: người gọi (Transport._gui, Hộp thư) chỉ nhớ CẢ câu. Mỗi đoạn về vòng đọc như một tin
# riêng, đoạn nào không nhận ra là bị coi như chủ vừa nhắn tay.
zc._DA_GUI.clear()
GUI.clear()
zc.ghi_da_gui("zalo-1", "u2", dai)          # y như Transport._gui làm trước khi gọi gui
asyncio.run(zp.gui({"id": "zalo-1"}, "u2", dai))
check("CANARY: mọi đoạn về vòng đọc đều được nhận là tiếng vọng của bot",
      all(zc._la_tieng_vong("zalo-1", "u2", a["text"]) for a in GUI))

GUI.clear()
asyncio.run(zp.gui({"id": "zalo-1"}, "u3", "Dạ em chào anh ạ"))
check("tin ngắn: vẫn một lần gọi như cũ", len(GUI) == 1 and GUI[0]["text"] == "Dạ em chào anh ạ")

GUI.clear()
HONG_O["lan"] = 2
ok, loi = asyncio.run(zp.gui({"id": "zalo-1"}, "u4", dai))
HONG_O["lan"] = 0
check("đoạn hỏng thì dừng, không gửi tiếp các đoạn sau", not ok and len(GUI) == 2, len(GUI))
check("lỗi nói rõ hỏng ở đoạn mấy", "2/" in loi, loi)

# ============================================================
# 3. Nhóm: chỉ tag người được trả lời ở đoạn đầu
# ============================================================
TAG = []


async def _tag_gia(conn, chat_id, text, mention):
    TAG.append(mention)
    return None     # để gửi thường, chỉ ghi lại ai được tag


_goc = zp._send_tagged
zp._send_tagged = _tag_gia
GUI.clear()
asyncio.run(zp.gui({"id": "zalo-1"}, "g1", dai, "group", {"uid": "123", "name": "Lan"}))
zp._send_tagged = _goc
check("nhóm: người được trả lời chỉ bị tag ở đoạn đầu",
      TAG and TAG[0] == {"uid": "123", "name": "Lan"} and all(m is None for m in TAG[1:]), TAG)
check("nhóm: vẫn gửi đủ các đoạn", len(GUI) == so_doan)

print()
if _fails:
    print(f"{len(_fails)} FAIL: " + ", ".join(_fails))
    sys.exit(1)
print("ALL PASS")
