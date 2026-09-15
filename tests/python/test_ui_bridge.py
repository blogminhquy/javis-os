"""Cầu nối tool -> dashboard (server/ui_bridge.py) và tool javis_ui.

    python tests/run.py ui_bridge

Voice V1: model gọi `javis_ui` để mở trang/file/việc trên dashboard. Tool chạy ở server, việc
làm nằm trong trình duyệt, nên phải có chỗ ĐỢI trình duyệt trả lời. Bốn chỗ dễ vỡ:
  1. Không có tab nào mở -> trả lỗi NGAY bằng một câu, không treo 4 giây.
  2. Có tab -> frame `ui_action` đúng khuôn (id, action, target, session_id); ack giải future.
  3. Tab khác phiên trả `skipped` thì KHÔNG được giải future (tab đúng phiên còn đáp sau).
  4. Không ai đáp -> hết giờ, trả câu lỗi có ghi số giây.
Cộng: javis_ui chặn trang lạ và đường dẫn `..` TRƯỚC khi hỏi dashboard; /ws có nhánh ui_result.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-uib-"))

import ui_bridge  # noqa: E402
from chat_runtime import ChatRuntime  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


async def main():
    rt = ChatRuntime()
    ui_bridge.attach(rt)

    # 1) không client
    r = await ui_bridge.request("open_page", "kanban")
    check("không tab: ok=False", r["ok"] is False)
    check("không tab: nói rõ không có dashboard", "dashboard" in r["detail"])

    # 2) có client, ack đúng id
    received = []

    async def writer(ev):
        received.append(ev)
        if ev.get("type") == "ui_action":
            ui_bridge.resolve(ev["id"], True, "trang Việc")

    rt.add_client("c1", writer)
    r = await ui_bridge.request("open_page", "kanban", session_id="abc")
    check("có tab: ok", r["ok"] is True and r["detail"] == "trang Việc")
    fr = received[-1]
    check("frame type ui_action", fr.get("type") == "ui_action")
    check("frame mang action/target/session_id", fr.get("action") == "open_page" and fr.get("target") == "kanban"
          and fr.get("session_id") == "abc")
    check("frame có id", bool(fr.get("id")))
    check("không còn future treo", ui_bridge.pending_count() == 0)

    # 3) skipped không giải future; ack thật sau đó mới giải
    rt.remove_client("c1")

    async def writer2(ev):
        if ev.get("type") != "ui_action":
            return
        ui_bridge.resolve(ev["id"], False, "khác phiên", skipped=True)
        loop = asyncio.get_running_loop()
        loop.call_later(0.05, lambda: ui_bridge.resolve(ev["id"], True, "đã mở"))

    rt.add_client("c2", writer2)
    r = await ui_bridge.request("open_file", "Wiki/a.md", timeout=1.0)
    check("skipped bị bỏ qua, ack thật thắng", r["ok"] is True and r["detail"] == "đã mở")
    rt.remove_client("c2")

    # 4) hết giờ
    async def writer3(ev):
        pass

    rt.add_client("c3", writer3)
    r = await ui_bridge.request("scroll", "bottom", timeout=0.2)
    check("hết giờ: ok=False, nêu số giây", r["ok"] is False and "0.2" in r["detail"])
    check("hết giờ: dọn future", ui_bridge.pending_count() == 0)
    rt.remove_client("c3")

    # 5) resolve id lạ -> False, không nổ
    check("resolve id lạ trả False", ui_bridge.resolve("nope", True) is False)

    # 6) plugin javis_ui: kiểm target trước khi hỏi dashboard
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "javis_ui_plugin", ROOT / "system" / "plugins" / "javis-ui" / "plugin.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    check("resolve_page: bí danh 'việc' -> kanban", m.resolve_page("việc") == "kanban")
    check("resolve_page: 'trang Cài đặt' -> settings", m.resolve_page("trang Cài đặt") == "settings")
    check("resolve_page: id chuẩn giữ nguyên", m.resolve_page("models") == "models")
    check("resolve_page: lạ -> rỗng", m.resolve_page("trang lạ hoắc") == "")
    # Thanh bên đã Việt hoá (0.57.6): nói đúng chữ đang hiện trên màn hình phải mở được trang.
    check("resolve_page: 'công cụ' -> plugins", m.resolve_page("công cụ") == "plugins")
    check("resolve_page: 'mở trang kỹ năng' -> skills", m.resolve_page("mở trang kỹ năng") == "skills")
    check("resolve_page: 'trợ lý' -> workspace", m.resolve_page("trợ lý") == "workspace")
    check("resolve_page: 'cho xem trang quy trình' -> workspace",
          m.resolve_page("cho xem trang quy trình") == "workspace")
    check("resolve_page: 'cộng sự' -> workspace", m.resolve_page("cộng sự") == "workspace")
    check("resolve_group: 'mở mục Năng lực' -> nang_luc", m.resolve_group("mở mục Năng lực") == "nang_luc")
    check("open_file chặn ..", bool(m.check_target("open_file", "../x.md")))
    check("open_file chặn tuyệt đối", bool(m.check_target("open_file", "C:/x.md")) and bool(m.check_target("open_file", "/etc/passwd")))
    check("open_file nhận tương đối", m.check_target("open_file", "Wiki/a.md") == "")
    check("scroll chỉ top/bottom", bool(m.check_target("scroll", "left")) and m.check_target("scroll", "xuống") == "")
    check("normalize scroll 'xuống' -> bottom", m.normalize_target("scroll", "xuống") == "bottom")
    # BUG-001: "cuộn xuống" phải cuộn thứ người dùng đang nhìn, nên target mang theo phạm vi.
    check("scroll: 'cuộn trang này xuống' -> page_bottom",
          m.normalize_target("scroll", "cuộn trang này xuống") == "page_bottom")
    check("scroll: 'cuộn khung chat lên' -> chat_top",
          m.normalize_target("scroll", "cuộn khung chat lên") == "chat_top")
    check("scroll: 'cuộn màn hình xuống dưới' -> page_bottom",
          m.resolve_scroll("cuộn màn hình xuống dưới") == "page_bottom")
    check("scroll: nói trống không thì để dashboard tự chọn",
          m.resolve_scroll("cuộn xuống dưới") == "bottom")
    check("scroll: dạng chuẩn đi qua nguyên vẹn",
          all(m.resolve_scroll(x) == x for x in m.SCROLL_TARGETS))
    check("action lạ bị chặn", bool(m.check_target("nuke", "x")))

    # handler: target lạ -> ERROR mà KHÔNG chạm cầu nối (không client vẫn trả lỗi trang)
    rt2 = ChatRuntime()
    ui_bridge.attach(rt2)
    out = await m._ui({"action": "open_page", "target": "trang lạ"}, None)
    check("handler: trang lạ -> ERROR nêu trang hợp lệ", out.startswith("ERROR") and "kanban" in out)
    out = await m._ui({"action": "open_page", "target": "việc"}, None)
    check("handler: không tab -> ERROR không có dashboard", out.startswith("ERROR") and "dashboard" in out)

    async def w(ev):
        if ev.get("type") == "ui_action":
            check("handler bỏ tiền tố web: ở session_id", ev.get("session_id") == "s1")
            ui_bridge.resolve(ev["id"], True, "")
    rt2.add_client("x", w)
    out = await m._ui({"action": "open_page", "target": "việc", "session_id": "web:s1"}, None)
    check("handler: thành công nói 'Đã mở trang kanban'", out.startswith("Đã mở trang kanban"))

    # Câu thuật lại phải lấy từ thứ dashboard THẬT SỰ cuộn, không đoán "khung chat" như trước:
    # model đọc câu này rồi nói lại cho người dùng, đoán sai là nói sai.
    rt3 = ChatRuntime()
    ui_bridge.attach(rt3)

    async def w3(ev):
        if ev.get("type") == "ui_action":
            ui_bridge.resolve(ev["id"], True, "nội dung trang")

    rt3.add_client("y", w3)
    out = await m._ui({"action": "scroll", "target": "cuộn trang này xuống"}, None)
    check("handler scroll: thuật đúng thứ dashboard vừa cuộn",
          out == "Đã cuộn nội dung trang xuống cuối.")

    # 7) /ws có nhánh ui_result
    main_src = (SERVER / "main.py").read_text(encoding="utf-8")
    check("main gắn runtime vào ui_bridge", "ui_bridge.attach(_CHAT_RUNTIME)" in main_src)
    check("/ws xử lý action ui_result", 'if action == "ui_result":' in main_src and "ui_bridge.resolve(" in main_src)
    # Đường TẮT giọng nói (dòng JAVIS_UI:) phải tra bí danh trước khi bắn sang dashboard. Thiếu
    # bước này thì model giọng viết "công cụ" là trình duyệt trả "trang không tồn tại" (lỗi 0.57.5).
    check("đường tắt giọng nói chuẩn hoá target qua ui_targets",
          "ui_targets.normalize_target(act, tgt)" in main_src)


asyncio.run(main())
if _fails:
    print("\nFAIL:", len(_fails), _fails)
    raise SystemExit(1)
print("\nOK - ui_bridge + javis_ui")
