"""Giao việc Kanban phải làm được từ MỌI bộ não, không chỉ hai engine chạy lệnh máy.

    python tests/run.py giao_viec_moi_engine

Lỗi thật, phát hiện 2026-08-04 khi chủ repo hỏi "engine API có thao tác được như Claude Code
với Codex không".

`CLAUDE.md` và `docs/10-models-va-engine.md` đều hứa mọi bộ não được cấp cùng bộ đồ nghề, trong
đó có "giao việc Kanban", và khác biệt DUY NHẤT là chạy được lệnh máy hay không. Lời hứa đó sai:
đường duy nhất để giao việc là `POST /kanban/task`, mà gọi được nó thì phải có Bash và curl - tức
là chỉ Claude Code với Codex. Năm engine API đứng ngoài.

Tệ hơn cả việc thiếu: `CLAUDE.md` còn dặn Javis "đừng bao giờ nói mình không làm task được, sai
sự thật". Nên engine API sẽ TỰ TIN nhận lời rồi im lặng không làm gì. Người dùng ngồi đợi một
việc không bao giờ chạy, và không có một dòng lỗi nào ở đâu cả.

Chủ repo chọn sửa MÃ chứ không hạ tài liệu. File này canh cái sửa đó đứng vững, theo đúng thứ
tự rủi ro:

1. **Tool phải tới được tay engine API.** Đây là toàn bộ lý do tính năng tồn tại. Đường đi thật
   là qua MCP Hub, và hiện lazy đang bật nên nó nằm sau `javis_search_tools`/`javis_run_tool` -
   test phải đi đúng đường đó chứ không gọi tắt vào hàm.
2. **Không được đẻ ra việc mức `full`.** Việc full tự thao tác thật ra ngoài (tạo đơn, tiêu
   tiền, chạy quảng cáo, gửi tin) và không hoàn tác được. Luật CLAUDE.md: không bao giờ tự đặt.
3. **Không được im lặng nuốt các thiếu sót** làm việc chạy vào hư không: sai brain, mất người
   nhận kết quả.
4. **Tài liệu phải khớp mã.** Đây là lỗi gốc, nên nó cũng phải có canary riêng.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import pathlib
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-viec-")

import mcp_hub  # noqa: E402
import plugins_host  # noqa: E402
import tasks as tasks_mod  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


_VAULT = pathlib.Path(tempfile.mkdtemp(prefix="javis-vault-"))
(_VAULT / "Javis").mkdir(parents=True, exist_ok=True)


# ============================================================
# 0. Plugin nạp được và khai đúng
# ============================================================
_mo_ta = {p.get("slug"): p for p in plugins_host.describe(None)}
_pl = _mo_ta.get("javis-task") or {}
check("có plugin javis-task", bool(_pl))
check("plugin nạp không lỗi", not _pl.get("error"))
check("plugin bật sẵn (nếu tắt thì lời hứa vẫn thủng)", _pl.get("enabled") is True)
check("đi theo app, không phải bản người dùng tự cài", _pl.get("source") == "bundled")
check("khai đúng tool", _pl.get("tools") == ["javis_task"])
# Hai chỗ khai min_mode: manifest (thứ trang Plugins HIỆN cho người dùng) và register_tool
# (thứ thật sự ENFORCE). Gate chỉ đọc cái thứ hai. Lệch nhau là trang Plugins nói dối về quyền
# của chính nó - người dùng đọc "chỉ đọc" rồi yên tâm, trong khi tool vẫn ghi được.
check("CANARY: min_mode hiện ra khớp min_mode enforce thật",
      _pl.get("min_mode") == "safe"
      and 'min_mode="safe"' in (ROOT / "system" / "plugins" / "javis-task" / "plugin.py")
      .read_text(encoding="utf-8"))


async def _chay():
    # ============================================================
    # 1. Tool tới được tay engine API, qua ĐÚNG đường hub
    # ============================================================
    tools, route = await mcp_hub.discover_all("full", vault_root=str(_VAULT))
    ten = [t.get("fn") or t.get("name") for t in tools]

    if "javis_search_tools" in ten:
        # Lazy bật: mọi tool trừ nhóm hạt nhân nằm sau meta-tool. Đây là đường đi THẬT của
        # engine API khi đã đấu nhiều nguồn, nên phải test đúng nó chứ không gọi tắt vào hàm.
        tim = await route["javis_search_tools"]["call"]({"query": "giao việc chạy nền kanban"})
        check("CANARY: engine API tìm ra được tool giao việc", "javis_task" in tim)
        _run = route["javis_run_tool"]["call"]

        async def goi(a):
            return await _run({"name": "javis_task", "args": a})
    else:
        check("CANARY: engine API thấy tool giao việc", "javis_task" in ten)
        _c = (route.get("javis_task") or {}).get("call")

        async def goi(a):
            return await _c(a)

    # ============================================================
    # 2. Rào an toàn - kiểm TRƯỚC khi có hàng đợi, để chắc rào đứng độc lập
    # ============================================================
    out = await goi({"op": "add", "title": "chạy quảng cáo hộ anh", "mode": "full"})
    check("CANARY: KHÔNG đẻ được việc mức full", "ERROR" in out)
    check("từ chối kèm lý do, không chỉ nói không", "không hoàn tác" in out)
    check("chỉ luôn đường đi tiếp cho người dùng", "trang Việc" in out)

    # Hàng đợi chưa dựng (máy chủ đang khởi động) thì phải báo rõ chứ không nổ ra traceback:
    # tool call nổ giữa lượt chat là engine thấy một đống stack trace thay vì lời giải thích.
    out = await goi({"op": "list"})
    check("chưa có hàng đợi thì báo rõ, không nổ", "ERROR" in out and "hàng đợi" in out)

    # Kèm title hẳn hoi: nếu op lạ bị đối xử như `add` thì nó sẽ THÀNH CÔNG chứ không lỗi, và
    # một test chỉ soi chữ "ERROR" trên lời gọi thiếu title sẽ xanh trong khi tool đang giao
    # việc cho mọi op nó không hiểu.
    out = await goi({"op": "xoa-sach-moi-thu", "title": "việc lọt cửa"})
    check("CANARY: op lạ bị từ chối, KHÔNG bị hiểu thành giao việc",
          "ERROR" in out and "op phải là" in out)

    # ============================================================
    # 3. Dựng hàng đợi thật rồi giao việc thật
    # ============================================================
    from fastapi import FastAPI
    feat = tasks_mod.register(FastAPI(), tasks_mod.TasksDeps(
        brain_root=lambda b: b if os.path.isdir(b) else str(_VAULT),
        atomic_write_text=lambda p, s: pathlib.Path(p).write_text(s, encoding="utf-8"),
        execute_workflow=None, workflows_dir=lambda b: str(_VAULT / "Javis" / "workflows"),
        build_system_prompt=lambda *a, **k: "", aux_model=lambda *a, **k: ("", ""),
        aux_swap=None, safe_tools=[], state_dir=pathlib.Path(os.environ["JAVIS_STATE_DIR"]),
        scheduler_brains=lambda: [str(_VAULT)], apply_mcp=None,
        mcp_allow_patterns=lambda *a, **k: [], report=None))
    check("tasks.current() trả đúng hàng đợi đang chạy", tasks_mod.current() is feat)

    out = await goi({"op": "add", "title": "soạn báo cáo tuần", "chat_id": "web:phien123"})
    check("giao được việc", "Đã giao việc" in out)
    check("trả mã việc để theo dõi tiếp", "Mã việc:" in out)
    check("CANARY: mặc định là suggest, không phải auto", "suggest" in out)

    # Nói thẳng rằng lượt trả lời này KHÔNG đợi việc chạy xong. Luật CLAUDE.md, và là hiểu nhầm
    # số một của người dùng khi giao việc lần đầu.
    #
    # Từ 0.24.9 câu này PHỤ THUỘC mức điều phối, và đó mới là sự thật: brain mới mặc định
    # `orchestration="off"` nên không có dispatcher nào lấy việc ra chạy. Nói "việc chạy nền,
    # kết quả tự về" ở trạng thái đó là hứa hộ một thứ sẽ không xảy ra, rồi model chuyển tiếp
    # nguyên văn cho người dùng - đúng lỗi "giao việc xong không thấy gì, không chạy luôn".
    check("CANARY: điều phối TẮT thì KHÔNG được hứa việc đang chạy",
          "KHÔNG tự chạy" in out and "chạy nền" not in out)
    check("nói luôn cách bật cho người dùng", "AI tự vận hành" in out)

    # ============================================================
    # 4. Không nuốt thiếu sót
    # ============================================================
    out = await goi({"op": "add", "title": "việc mồ côi"})
    check("CANARY: thiếu người nhận thì CẢNH BÁO, không nuốt", "CẢNH BÁO" in out)
    check("cảnh báo nói rõ hậu quả", "mất hút" in out)

    out = await goi({"op": "add"})
    check("thiếu title bị từ chối", "ERROR" in out)

    # Mode lạ (model gõ sai, hoặc bịa ra tên mức) phải KẸP VỀ suggest. Thả trôi thì enqueue tự
    # kẹp về "auto" - tức là model gõ sai một chữ là việc được nâng quyền ghi file, im lặng.
    out = await goi({"op": "add", "title": "việc mode lạ", "mode": "sieu-cap",
                     "chat_id": "web:phien123"})
    check("CANARY: mode lạ kẹp về suggest, không trôi thành auto",
          "Đã giao việc" in out and "suggest" in out and "auto" not in out)

    # ============================================================
    # 5. Việc nằm THẬT trong kho, đúng thuộc tính
    # ============================================================
    out = await goi({"op": "list"})
    check("liệt kê thấy việc vừa giao", "soạn báo cáo tuần" in out)

    board = feat.board_view(str(_VAULT))
    moi = [t for c in (board.get("columns") or {}).values() for t in c]
    check("việc vào thật trong kho, không phải chỉ in ra chữ", len(moi) == 3)
    check("CANARY: execution_mode lưu đúng suggest",
          all(t.get("execution_mode") == "suggest" for t in moi))
    check("CANARY: chat_id lưu đúng để kết quả về đúng người",
          any(t.get("chat_id") == "web:phien123" for t in moi))
    check("việc ghi nhận do chat tạo", all(t.get("created_by") == "chat" for t in moi))

    # ============================================================
    # 6. Hai rào phụ thuộc NGỮ CẢNH, phải thử ở đúng ngữ cảnh đó
    # ============================================================
    # Chế độ suggest (chỉ đọc): giao việc là hành động ghi, phải bị chặn ở TẦNG QUYỀN chứ không
    # phải trông vào tự giác của tool. Đây là lý do plugin khai min_mode=safe.
    _t2, _r2 = await mcp_hub.discover_all("suggest", vault_root=str(_VAULT))
    if "javis_search_tools" in [x.get("fn") for x in _t2]:
        out = await _r2["javis_run_tool"]["call"]({"name": "javis_task",
                                                  "args": {"op": "add", "title": "lén giao việc"}})
    else:
        out = await (_r2.get("javis_task") or {}).get("call")({"op": "add", "title": "lén giao việc"})
    check("CANARY: chế độ chỉ-đọc CHẶN giao việc ở tầng quyền",
          "ERROR" in out and "quyền" in out)
    check("số việc trong kho không đổi sau lần bị chặn",
          len([t for c in (feat.board_view(str(_VAULT)).get("columns") or {}).values() for t in c]) == 3)

    # Không biết brain nào thì PHẢI từ chối, không được âm thầm rơi về Brain Default - giao việc
    # nhầm brain là việc chạy trên dữ liệu của người khác. (Đúng lỗi image_gen từng dính.)
    _t3, _r3 = await mcp_hub.discover_all("full", vault_root=None)
    if "javis_search_tools" in [x.get("fn") for x in _t3]:
        out = await _r3["javis_run_tool"]["call"]({"name": "javis_task",
                                                   "args": {"op": "add", "title": "việc lạc brain"}})
        check("CANARY: không biết brain thì TỪ CHỐI, không rơi về brain mặc định",
              "ERROR" in out and "brain" in out)
        check("việc lạc brain không lọt vào kho nào",
              len([t for c in (feat.board_view(str(_VAULT)).get("columns") or {}).values() for t in c]) == 3)

    # ============================================================
    # 6b. Mặt kia của cổng điều phối - đặt CUỐI vì nó đẻ thêm một việc vào kho
    # ============================================================
    # Bật "AI tự vận hành" rồi thì câu "việc chạy nền, kết quả tự về" mới là sự thật, và tool
    # phải nói đúng như vậy. Kiểm cả hai chiều mới chứng minh được cổng đang ĐỌC mức điều phối
    # chứ không phải cứ dán cứng một câu (bản trước dán cứng, nên nó sai ở mức off suốt).
    feat.store.set_orchestration(str(_VAULT), "auto")
    out_auto = await goi({"op": "add", "title": "việc khi đã bật điều phối",
                          "chat_id": "web:phien123"})
    check("bật AI tự vận hành rồi thì mới nói việc chạy nền", "chạy nền" in out_auto)
    feat.store.set_orchestration(str(_VAULT), "off")

    # Cảnh báo ở op=list cũng vậy. Trước đây cổng viết là `not view.get("orchestration")`, mà
    # giá trị là CHUỖI "off" nên luôn truthy - dòng cảnh báo đó chưa từng in ra lần nào.
    check("CANARY: op=list cảnh báo khi điều phối tắt",
          "KHÔNG tự chạy" in await goi({"op": "list"}))


asyncio.run(_chay())


# ============================================================
# 7. Cả BA đường nạp tool, không chỉ đường engine API
# ============================================================
# "Mọi bộ não" là ba đường khác nhau, không phải một:
#   - engine API   -> mcp_hub.discover_all() in-process   (mục 1 ở trên đã canh)
#   - Codex        -> hub qua HTTP, có header X-Javis-Vault
#   - Claude Code  -> plugins_host.plugin_tools() nạp THẲNG vào SDK, KHÔNG qua hub
# Đường Claude đi riêng hẳn (nó gửi X-Javis-No-Plugins để hub bỏ nhóm plugin, rồi tự nạp
# in-process), nên một thay đổi làm hỏng đúng đường đó sẽ không bị mục 1 phát hiện.
_pt, _pr = plugins_host.plugin_tools("full", str(_VAULT), scope_vault=False)
check("CANARY: đường Claude Code cũng có tool giao việc",
      "javis_task" in [x["fn"] for x in _pt])
check("rào full đứng vững trên cả đường đó",
      "ERROR" in asyncio.run(_pr["javis_task"]["call"](
          {"op": "add", "title": "chạy quảng cáo", "mode": "full"})))

# Chế độ chỉ-đọc phải chặn ở đường này nữa - min_mode nằm trong route của plugin_tools(mode).
_pt2, _pr2 = plugins_host.plugin_tools("suggest", str(_VAULT), scope_vault=False)
if "javis_task" in _pr2:
    check("CANARY: đường Claude Code cũng chặn giao việc ở chế độ chỉ-đọc",
          "ERROR" in asyncio.run(_pr2["javis_task"]["call"]({"op": "add", "title": "lén"})))
else:
    check("chế độ chỉ-đọc thì tool giao việc không lộ ra ở đường Claude Code", True)


# ============================================================
# 6. Tài liệu khớp mã
# ============================================================
# Đây là lỗi GỐC: tài liệu hứa một thứ mã không làm được, suốt nhiều bản. Nay mã đã làm được thì
# canary đổi chiều - nó canh tài liệu đừng lại nói THIẾU đi so với thực tế, và canh cái câu
# "khác biệt duy nhất là Bash" đừng quay lại, vì nó vẫn sai: WebFetch/WebSearch/Task cũng là của
# riêng hai engine CLI.
_CL = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
_DOC = (ROOT / "docs" / "10-models-va-engine.md").read_text(encoding="utf-8")

check("CLAUDE.md vẫn hứa mọi bộ não giao được việc Kanban", "queue Kanban work" in _CL)
check("CANARY: CLAUDE.md không còn nói khác biệt DUY NHẤT là lệnh máy",
      "Khác biệt DUY NHẤT" not in _CL)
check("CANARY: CLAUDE.md kể cả WebFetch/WebSearch là của riêng engine CLI",
      "WebFetch" in _CL)
check("CANARY: docs/10 không còn nói khác biệt duy nhất là chạy lệnh máy",
      "Khác biệt **duy nhất** là chạy được lệnh máy hay không" not in _DOC)
check("docs/10 có nhắc tool giao việc cho engine API", "javis_task" in _DOC)

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    raise SystemExit(1)
print("OK - test_giao_viec_moi_engine: tất cả pass")
