"""Tin nói VỀ quy trình không được nhồi vào một lần chạy. Chạy tay / CI:

    python tests/run.py tin_ve_quy_trinh

Chuyện thật 16/09 (chủ dự án chụp lại): ở phiên workflow:<slug> của trang Cộng sự, MỌI tin
đều thành `{{input}}` của một lần chạy. Chủ dự án gõ hai câu nói về chính quy trình:

    "tôi muốn cập nhật lại workflow là có xuất bài viết ngay cả khi chưa đạt..."
    "Tự đánh giá lại quy trình với 7 bước hiện tại... Giảm số bước xuống..."

Quy trình đem cả hai đi VIẾT BÀI: 7 bước, 640 giây, tiêu hạn mức gói thuê bao, rồi trả về một
bản kiểm duyệt article.md không liên quan gì tới câu hỏi ("làm workflow nó trả ra cái gì ấy").
Cùng lần chạy đó còn in nguyên văn câu tiếng Anh của nhà cung cấp làm KẾT QUẢ.

Phủ ba tầng:
1. `workflow_chat.quyet_dinh_luot` - hàng rào thuần: câu nào là đề bài, câu nào là nói về
   quy trình, đường thoát "chạy:" và cờ của nút Chạy.
2. `_run_workflow_step` (đường graph Phase 10) - câu báo hết lượt không được thành kết quả
   bước, và KHÔNG được đem cho agent kiểm chứng (đốt thêm một lượt của gói vừa hết).
3. Dây nối ở bộ điều phối lượt + hai file dashboard (đối chiếu mã nguồn): quyết định nằm
   trong hàm thuần đã test, nhưng nếu không ai GỌI nó thì cả tầng 1 chỉ là trang trí.

KHÔNG chạm mạng, không engine thật: tầng 2 chạy bằng engine giả.
KHÔNG dùng ký tự em dash.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from types import SimpleNamespace

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-tinwf-"))

import workflow_chat  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ============================================================
# 1. Hàng rào thuần: đề bài thì CHẠY, nói về quy trình thì TRẢ LỜI
# ============================================================
def _viec(msg, ep_chay=False):
    return workflow_chat.quyet_dinh_luot(msg, ep_chay=ep_chay)[0]


# Hai câu THẬT của ngày 16/09 - hai ca phải đúng, còn lại là để nó đừng đúng một cách bừa bãi.
_THAT_1 = ("tôi muốn cập nhật lại workflow là có xuất bài viết ngay cả khi chưa đạt để tôi "
           "sửa lại sau, thêm một ghi chú bổ sung dưới mỗi bài viết xem còn thiếu gì")
_THAT_2 = ("- Tự đánh giá lại quy trình với 7 bước hiện tại đã đáp ứng đầu ra 1 bài viết tốt "
           "nhất hay chưa. - Giảm số bước xuống nhưng vẫn sở hữu đủ các nội dung yêu cầu của "
           "7 bước. - Tóm tắt các ý chính của quy trình này")
check("THẬT 16/09: 'cập nhật lại workflow...' KHÔNG chạy quy trình", _viec(_THAT_1) == "tra_loi")
check("THẬT 16/09: 'đánh giá lại quy trình 7 bước, giảm số bước' KHÔNG chạy",
      _viec(_THAT_2) == "tra_loi")

for m in ("Sau đó giản lược lại thành 3 bước nhưng đáp ứng tiêu chí cốt lõi của 7 bước.",
          "quy trình này có gộp bớt bước nào được không",
          "bỏ bước kiểm chứng đi",
          "thêm bước QC ảnh vào cuối",
          "gộp bước 2 và 3 lại",
          "sửa quy trình hiện tại: cho phép xuất bản khi chưa đạt",
          "giai thich quy trinh nay cho toi",          # gõ KHÔNG DẤU vẫn phải nhận ra
          "update the workflow to always export the draft",
          "can you simplify this workflow to 3 steps",
          # Động từ SỬA dính liền danh từ, sau đó không phải một cụm định danh.
          "cập nhật quy trình: luôn xuất bài dù chưa đạt",
          "sửa quy trình đi",
          "rút gọn quy trình còn 4 bước",
          "đánh giá quy trình, có dư bước nào không"):
    check(f"nói về quy trình: {m[:44]!r}", _viec(m) == "tra_loi")

# Mặt còn lại, quan trọng ngang: một ĐỀ BÀI phải chạy. Nhận nhầm phía này là người dùng mất
# đúng lần chạy họ muốn, và cái giá "một lượt chat rẻ" không còn đúng nữa.
for m in ("Viết bài về cách chơi baccarat cho người mới, tone thân thiện, 1500 từ",
          "Viết bài tóm tắt quy trình làm nước mắm truyền thống của gia đình",
          "Viết bài: quy trình 5 bước chăm sóc khách hàng VIP của casino online",
          "Viết hướng dẫn 7 bước đăng ký tài khoản cho người mới",
          "liệt kê các bước làm bánh mì rồi viết thành bài",
          "viết bài theo từng bước một, đừng gộp ý",
          "chủ đề: top 5 nhà cung cấp game slot 2026, từ khoá chính: slot uy tín",
          "Tóm tắt bài viết vừa rồi thành 5 gạch đầu dòng",
          # "quy trình LÀM NƯỚC MẮM" / "quy trình NẠP TIỀN" là quy trình KHÁC, không phải
          # workflow đang mở: động từ dính liền danh từ cũng không được nhận.
          "viết bài cập nhật quy trình nạp tiền mới của nhà cung cấp",
          "Viết bài tóm tắt quy trình, chi tiết từng bước cho người mới",
          "Viết bài hướng dẫn nạp rút tiền: quy trình nạp gồm 4 bước, nêu rõ từng bước",
          "Kiểm tra lại bài viết vừa rồi xem còn lỗi chính tả không"):
    check(f"đề bài vẫn CHẠY: {m[:44]!r}", _viec(m) == "chay")

# Đường thoát khi hàng rào đoán sai: tiền tố ở đầu tin, và cờ của nút Chạy.
_ep, _msg = workflow_chat.quyet_dinh_luot("chạy: đánh giá lại quy trình 7 bước")
check("tiền tố 'chạy:' ép chạy dù câu nghe như nói về quy trình", _ep == "chay")
check("tiền tố bị BÓC khỏi đầu vào (không lọt vào {{input}})", _msg == "đánh giá lại quy trình 7 bước")
check("tiền tố 'run:' cũng ép chạy", workflow_chat.quyet_dinh_luot("run: rebuild the article")[0] == "chay")
check("nút Chạy (wf_run) thắng hàng rào", _viec(_THAT_2, ep_chay=True) == "chay")
check("tin rỗng không bị coi là nói về quy trình", _viec("") == "chay")

# Câu nói ra phải NÓI RÕ là chưa chạy, kèm đúng hai đường ép chạy.
_cau = workflow_chat.tin_khong_chay("Viết bài chuyên sâu")
check("câu báo nêu tên quy trình", "Viết bài chuyên sâu" in _cau)
check("câu báo nói rõ KHÔNG chạy và chỉ hai đường ép chạy",
      "trả lời thay vì chạy" in _cau and "Chạy" in _cau and "chạy:" in _cau)

# Khối ngữ cảnh: bộ não chính phải biết file nào, bước nào, và KHÔNG được tự chạy quy trình.
_khoi = workflow_chat.khoi_quy_trinh_dang_mo(
    "Viết bài chuyên sâu", "viet-bai-chuyen-sau", "/brains/Trang Javis/workflows/viet-bai.md", 2,
    [{"agent": "nguoi-viet", "task": "viết bản thảo"}, {"agent": "nguoi-sua", "task": "sửa {{prev}}"}])
check("khối ngữ cảnh mang ĐƯỜNG DẪN file quy trình", "/brains/Trang Javis/workflows/viet-bai.md" in _khoi)
check("khối ngữ cảnh liệt kê bước + agent", "B1. nguoi-viet: viết bản thảo" in _khoi
      and "B2. nguoi-sua" in _khoi)
check("khối ngữ cảnh cấm tự chạy quy trình", "KHÔNG tự chạy" in _khoi)
check("khối ngữ cảnh mở bằng dấu hiệu máy đọc được", _khoi.startswith("[QUY TRÌNH ĐANG MỞ"))


# ============================================================
# 2. Đường graph: câu "hết lượt gói" không được thành kết quả bước
# ============================================================
# Runner cũ đã chặn từ 0.59.2 (tests/python/test_workflow_turn_ws.py). Đường graph Phase 10
# dùng CHUNG _run_workflow_step mà lại không soi, nên cùng một lần chạy, cùng một câu tiếng
# Anh, hai đường cho ra hai kết cục khác nhau - đúng kiểu hỏng mà chú thích ở
# _workflow_agent_helpers dặn phải tránh bằng cách dùng chung code.
import main  # noqa: E402

_CAU_HET_LUOT = "You've hit your session limit · resets 12pm (UTC)"
_da_goi = []


class _EngineGia:
    def __init__(self, evs):
        self._evs = evs

    async def query(self, prompt):
        _da_goi.append(prompt)
        for ev in self._evs:
            yield ev


def _mk_gia(kich_ban):
    hang = list(kich_ban)
    del _da_goi[:]

    def _mk(sysprompt, model=None, provider=""):
        return _EngineGia(hang.pop(0) if hang else [{"type": "final", "content": ""}])
    return _mk


def _sysprompt_gia(slug):
    return ({"nguoi-viet": "Người viết"}.get(slug, slug), "bạn là agent",
            "claude-sonnet-4", "anthropic-cli")


def _chay_buoc(kich_ban, verify=""):
    node = SimpleNamespace(id="n1", kind="model_step", agent="nguoi-viet",
                           verify_agent=verify, max_retries=1, metadata={"legacy_index": 0})
    khung = []

    async def sink(ev):
        khung.append(ev)

    async def _go():
        return await main._run_workflow_step(node, "viết bài", _mk_gia(kich_ban),
                                             _sysprompt_gia, sink, session_id="s1")
    return asyncio.run(_go()), khung


_kq, _khung = _chay_buoc([[{"type": "final", "content": _CAU_HET_LUOT}]], verify="nguoi-sua")
check("graph: hết lượt thì bước HỎNG, không trả kết quả", _kq.get("error") and not _kq.get("output"))
check("graph: câu lỗi là tiếng Việt, không phải nguyên văn tiếng Anh",
      "Hết lượt" in _kq.get("error", "") and "session limit" not in _kq.get("error", ""))
check("graph: nói lại được mốc reset nhà cung cấp đã báo", "12pm" in _kq.get("error", ""))
check("graph: có phát step_error cho cột phải",
      [k for k in _khung if k.get("type") == "step_error"])
check("graph: KHÔNG gọi agent kiểm chứng (khỏi đốt thêm lượt của gói vừa hết)",
      len(_da_goi) == 1 and not [k for k in _khung if k.get("type") == "step_verify"])

# Mặt còn lại: một bài viết CÓ TRÍCH câu báo đó vẫn là bài viết thật.
_trich = ('Bài viết: khi gặp thông báo "You have reached your session limit" thì nên chờ '
          'tới giờ reset rồi làm tiếp.')
_kq2, _khung2 = _chay_buoc([[{"type": "final", "content": _trich}]])
check("graph: câu TRÍCH trong bài không bị coi là hết lượt",
      not _kq2.get("error") and _kq2.get("output") == _trich)
_kq3, _ = _chay_buoc([[{"type": "final", "content": "BẢN THẢO"}]])
check("graph: lần chạy sạch không đổi gì", not _kq3.get("error") and _kq3.get("output") == "BẢN THẢO")


# ============================================================
# 3. Dây nối: hàng rào phải được GỌI, và nút Chạy phải gửi cờ
# ============================================================
src = (SERVER / "main.py").read_text(encoding="utf-8")
check("CANARY: bộ điều phối lượt gọi quyet_dinh_luot cho phiên workflow",
      "workflow_chat.quyet_dinh_luot(" in src)
check("cờ wf_run của nút Chạy được đọc từ payload", 'ep_chay=bool(payload.get("wf_run"))' in src)
check("nhánh trả lời đi run_turn kèm khối QUY TRÌNH ĐANG MỞ",
      "_ten_wf, _khoi_wf = _khoi_quy_trinh_mo(brain, _pers[1])" in src
      and "conv_sid, _khoi_wf +" in src)
check("nhánh trả lời nói ra là không chạy (khung system)",
      "workflow_chat.tin_khong_chay(" in src)
check("nhánh chạy dùng tin ĐÃ BÓC tiền tố, không phải tin thô",
      "run_workflow_turn(\n                        conv_sid, _msg_wf," in src)

app_js = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
ws_js = (ROOT / "dashboard" / "workspace.js").read_text(encoding="utf-8")
check("app.js gửi cờ wf_run trong gói WebSocket", "wf_run: !!(opts && opts.wfRun)" in app_js)
check("workspace.js: nút Chạy gửi wfRun", "{ wfRun: true }" in ws_js)

if _fails:
    print(f"\nFAIL {len(_fails)} muc: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_tin_ve_quy_trinh: tat ca pass")
