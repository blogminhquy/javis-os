"""Test tool javis_schedule (plugin bundled). Chạy tay / CI:

    python tests/run.py javis_schedule

Bối cảnh: trước tool này, chat muốn tạo việc định kỳ phải TỰ GÕ YAML frontmatter vào
Javis/loops/<slug>.md, hoặc shell ra curl POST /reminders (reminders.py:17). Tool gói cả hai
lại và tự route: nhắc/cron/một-lần -> kho reminders; việc lặp + bền -> file .md.

KHÔNG chạm mạng: mọi test đều gọi hàm thuần hoặc ghi file trong thư mục tạm.

Phủ:
- _route_kind: phân loại đúng lịch -> kho nào.
- _slugify_vn: tên tiếng Việt -> slug ascii, không đụng file đã có.
- op=create việc lặp -> ghi .md đúng chỗ, frontmatter đọc lại được, enabled=false.
- op=create nhắc -> KHÔNG ghi .md (phải đi đường reminders).
- Tool đăng ký đúng tên + min_mode.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import asyncio
import inspect
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-schedtest-"))
sys.path.insert(0, str(ROOT / "system" / "plugins" / "javis-schedule"))

import yaml  # noqa: E402
import plugin as sched  # noqa: E402
import self_improve  # noqa: E402 - dùng để chặn C2 bằng LƯỚI THẬT (self_improve._norm_loop qua get_loop)

_fails = []


def check(name, cond):
    print(("ok  " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- 1. Route: lịch nào về kho nào ----
check("route: '120m' -> loop (lặp, bền)", sched._route_kind("120m", False) == "loop")
check("route: 'mỗi 2 tiếng' -> loop", sched._route_kind("mỗi 2 tiếng", False) == "loop")
check("route: '0 7 * * *' -> reminder (cron, reminders đã có sẵn)",
      sched._route_kind("0 7 * * *", False) == "reminder")
check("route: '30 phút nữa' -> reminder (một lần)", sched._route_kind("30 phút nữa", False) == "reminder")
check("route: notify_only ép về reminder dù lịch lặp",
      sched._route_kind("120m", True) == "reminder")

# ---- 2. Slug ----
check("slug: bỏ dấu tiếng Việt", sched._slugify_vn("Đọc source mỗi 2 tiếng") == "doc-source-moi-2-tieng")
check("slug: không rỗng khi tên toàn ký tự lạ", sched._slugify_vn("!!!") != "")

# ---- 3. Tạo việc lặp -> ghi .md ----
_vault = tempfile.mkdtemp(prefix="javis-vault-")
res = sched._create_loop_file(_vault, name="Quét đơn mỗi 2 tiếng",
                              prompt="Mỗi vòng đọc số đơn hôm nay qua MCP POS rồi ghi nháp.",
                              schedule="120m", owner_chat="123")
f = Path(_vault) / "Javis" / "loops" / "quet-don-moi-2-tieng.md"
check("loop: ghi đúng <vault>/Javis/loops/<slug>.md", f.is_file())
body = f.read_text(encoding="utf-8") if f.is_file() else ""
check("loop: frontmatter có type: loop", "type: loop" in body)
check("loop: MẶC ĐỊNH enabled: false (user bấm Bật ở trang Việc)", "enabled: false" in body)
# 2026-09-10: chủ repo bỏ luật "không giao tự động tiền/đơn/đăng bài/nhắn khách", nên loop tạo
# qua chat mặc định toàn quyền. Muốn nhẹ hơn thì truyền muc_quyen.
check("loop: MẶC ĐỊNH mode: full (Javis tự thao tác)", "mode: full" in body)
check("loop: kết quả nói rõ mức quyền", "toàn quyền" in str(res))
_res_nhe = sched._create_loop_file(_vault, name="Chỉ đọc rồi báo",
                                   prompt="Mỗi vòng đọc số đơn rồi đề xuất.",
                                   schedule="60m", mode="suggest")
_f_nhe = Path(_vault) / "Javis" / "loops" / "chi-doc-roi-bao.md"
check("loop: muc_quyen=suggest hạ được xuống mode: suggest",
      _f_nhe.is_file() and "mode: suggest" in _f_nhe.read_text(encoding="utf-8"))
_res_la = sched._create_loop_file(_vault, name="Mode lạ", prompt="x", schedule="60m", mode="sieu-cap")
_f_la = Path(_vault) / "Javis" / "loops" / "mode-la.md"
check("loop: mode lạ kẹp về full, không nổ",
      _f_la.is_file() and "mode: full" in _f_la.read_text(encoding="utf-8"))
check("loop: interval_min từ '120m'", "interval_min: 120" in body)
check("loop: giữ owner_chat để báo đúng người", 'owner_chat: "123"' in body)
check("loop: thân file LÀ prompt (tự đủ, không phụ thuộc chat)", "MCP POS" in body)
check("loop: trả về đường dẫn cho model biết đã ghi đâu", "quet-don-moi-2-tieng" in str(res))

# ---- 4. Không ghi đè loop đã có bằng bản ascii song song ----
# self_improve.py:273 lấy ĐỊNH DANH theo TÊN FILE. Tạo trùng slug -> phải báo, không âm thầm fork.
res2 = sched._create_loop_file(_vault, name="Quét đơn mỗi 2 tiếng", prompt="khác", schedule="60m")
check("loop: trùng slug -> báo lỗi rõ, không đẻ bản sao",
      str(res2).startswith("ERROR:") or "đã có" in str(res2).lower())

# ---- 5. Hồi quy Lỗi 1: tên việc chứa ký tự chỉ-thị YAML không được làm loop CHẾT ÂM THẦM ----
# Trước khi vá, _yaml_scalar chỉ escape [:#'"\n], bỏ sót '-' đầu chuỗi, '@', '*', '!', '%', '?',
# '|', '&', '>' - ghi ra frontmatter vỡ, yaml.safe_load ném ScannerError/ConstructorError, rồi
# self_improve.list_loops() nuốt lỗi bằng try/except nên loop biến mất khỏi tab Việc dù tool đã
# báo "đã tạo thành công". Lưới thật: yaml.safe_load ĐỌC LẠI ĐƯỢC và name khớp NGUYÊN VĂN - không
# chỉ tìm chuỗi con "name:" trong file (test đó không phát hiện được frontmatter vỡ).
_boundary_names = [
    "- rm -rf test",
    "@weird",
    "!weird",
    "*sao",
    "%phantram",
    "tên: có hai chấm",
    'tên "có nháy"',
]
for _nm in _boundary_names:
    _v = tempfile.mkdtemp(prefix="javis-vault-yaml-")  # vault riêng: tránh 2 tên trùng slug ("@weird"/"!weird")
    _res = sched._create_loop_file(_v, name=_nm, prompt="x", schedule="120m")
    check(f"yaml-safe tên {_nm!r}: tạo không lỗi", not str(_res).startswith("ERROR"))
    _files = list((Path(_v) / "Javis" / "loops").glob("*.md"))
    check(f"yaml-safe tên {_nm!r}: ghi đúng 1 file", len(_files) == 1)
    if _files:
        _body = _files[0].read_text(encoding="utf-8")
        _fm_text = _body.split("---")[1] if _body.count("---") >= 2 else ""
        try:
            _fm = yaml.safe_load(_fm_text) or {}
            _parse_ok = True
        except yaml.YAMLError:
            _fm = {}
            _parse_ok = False
        check(f"yaml-safe tên {_nm!r}: yaml.safe_load đọc lại được", _parse_ok)
        check(f"yaml-safe tên {_nm!r}: name khớp NGUYÊN VĂN", isinstance(_fm, dict) and _fm.get("name") == _nm)

# owner_chat cũng nối chuỗi tay trước khi vá (f'owner_chat: "{...}"') - phải qua _yaml_scalar y hệt name.
_v_owner = tempfile.mkdtemp(prefix="javis-vault-yaml-")
sched._create_loop_file(_v_owner, name="Việc test owner", prompt="x", schedule="120m",
                        owner_chat='chat"tiem-an-loi')
_f_owner = list((Path(_v_owner) / "Javis" / "loops").glob("*.md"))
if _f_owner:
    _fm_owner_text = _f_owner[0].read_text(encoding="utf-8").split("---")[1]
    try:
        _fm_owner = yaml.safe_load(_fm_owner_text) or {}
        check("yaml-safe owner_chat chứa dấu nháy kép: đọc lại được",
              _fm_owner.get("owner_chat") == 'chat"tiem-an-loi')
    except yaml.YAMLError:
        check("yaml-safe owner_chat chứa dấu nháy kép: đọc lại được", False)
else:
    check("yaml-safe owner_chat chứa dấu nháy kép: ghi được file", False)

# ---- 6. Tool đăng ký đúng ----
_regs = []


class _FakeCtx:
    # data_dir là @property trên PluginContext thật (plugins_host.py:223) nên KHÔNG gán được;
    # fake ctx chỉ cần thứ handler thật sự đọc.
    vault_root = _vault
    slug = "javis-schedule"

    def register_tool(self, **kw):
        _regs.append(kw)

    def register_hook(self, *a, **k):
        pass


sched.register(_FakeCtx())
check("đăng ký: đúng 1 tool", len(_regs) == 1)
check("đăng ký: tên javis_schedule", _regs and _regs[0].get("name") == "javis_schedule")
check("đăng ký: min_mode=safe (tạo việc là GHI, chặn ở suggest)",
      _regs and _regs[0].get("min_mode") == "safe")
desc = (_regs[0].get("description") or "") if _regs else ""
check("đăng ký: mô tả nói rõ KHI NÀO gọi", len(desc) > 60 and "op" in desc)
props = ((_regs[0].get("schema") or {}).get("properties") or {}) if _regs else {}
check("đăng ký: schema có op/name/schedule/prompt",
      {"op", "name", "schedule", "prompt"}.issubset(set(props)))


# ---- 7. Chặn C1 (hồi quy deadlock): handler + 3 hàm HTTP BẮT BUỘC là coroutine ----
# Trước khi vá, javis_schedule là `def` thuần gọi httpx.post ĐỒNG BỘ vào chính server đang chạy
# nó -> khoá event loop uvicorn (1 worker, main.py:5037) -> deadlock/ReadTimeout, treo TOÀN BỘ
# server. Lưới này chặn ai đó quay lại lối sync ở lần sửa sau.
check("C1: javis_schedule là coroutine (không còn def thuần đồng bộ)",
      inspect.iscoroutinefunction(sched.javis_schedule))
check("C1: _post_reminder là coroutine", inspect.iscoroutinefunction(sched._post_reminder))
check("C1: _get_reminders là coroutine", inspect.iscoroutinefunction(sched._get_reminders))
check("C1: _cancel_reminder là coroutine", inspect.iscoroutinefunction(sched._cancel_reminder))
check("C1: _do_create/_do_list/_do_cancel cũng là coroutine (await được xuống httpx)",
      inspect.iscoroutinefunction(sched._do_create)
      and inspect.iscoroutinefunction(sched._do_list)
      and inspect.iscoroutinefunction(sched._do_cancel))


# ---- 8. Chặn C2 (LƯỚI THẬT, không chỉ kiểm tra chữ đã ghi) ----
# Assert "MCP POS" in body (mục 3) chỉ chứng minh chữ đã được GHI ra file, KHÔNG chứng minh loop
# sẽ ĐỌC nó. self_improve.py:250 `goal = fm.get("goal", "business")` - THIẾU dòng 'goal: custom'
# trong frontmatter thì self_improve._norm_loop tự rơi về 'business', và goal=='business'
# (self_improve.py:546) KHÔNG đọc loop["body"] một chữ nào - loop "tạo thành công" nhưng chạy
# nhầm việc khác hoàn toàn (hoặc skip vô hạn nếu chưa có MCP số liệu). Test này đưa file loop qua
# ĐÚNG hàm self_improve dùng thật (LoopFeature.get_loop -> _norm_loop) để chặn tận gốc.
def _c2_atomic_write(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


_c2_deps = self_improve.LoopDeps(
    build_system_prompt=lambda brain: "SYS",
    brain_root=lambda brain: brain,   # test dùng thẳng path vault làm "brain" - identity map
    aux_model=lambda: None,
    atomic_write_text=_c2_atomic_write,
    project_root=Path("."),
    state_dir=Path(os.environ["JAVIS_STATE_DIR"]),
    safe_tools=[], readonly_tools=[],
)
_c2_feat = self_improve.LoopFeature(_c2_deps)

_vault_c2 = tempfile.mkdtemp(prefix="javis-vault-c2-")
_res_c2 = sched._create_loop_file(
    _vault_c2, name="Doc source moi vong",
    prompt="Moi vong doc 1 source unprocessed roi de xuat wiki.", schedule="120m")
check("C2: tạo loop qua tool không lỗi", not str(_res_c2).startswith("ERROR"))
_lp_c2 = _c2_feat.get_loop(_vault_c2, "doc-source-moi-vong")
check("C2: self_improve (LoopFeature.get_loop -> _norm_loop) đọc lại được loop vừa tạo",
      bool(_lp_c2))
check("C2 LƯỚI THẬT: goal == 'custom' (KHÔNG rơi về mặc định 'business' của self_improve.py:250)",
      bool(_lp_c2) and _lp_c2.get("goal") == "custom")
check("C2 LƯỚI THẬT: thân file (prompt) TỚI ĐƯỢC self_improve - đúng chỗ sẽ chạy thật",
      bool(_lp_c2) and "de xuat wiki" in _lp_c2.get("body", ""))


# ---- 9. Chặn I2: notify_only phải đổi mode 'notify'/'task' thật trong payload gửi /reminders ----
_captured_payload = {}


async def _fake_post_reminder(payload, brain_name=""):
    _captured_payload.clear()
    _captured_payload.update(payload)
    return "Đã đặt nhắc hẹn lúc ? (id fake)."


_real_post_reminder = sched._post_reminder
sched._post_reminder = _fake_post_reminder
try:
    asyncio.run(sched._do_create(_vault_c2, {
        "name": "Goi khach", "prompt": "Nhac goi khach X", "schedule": "30 phut nua",
        "notify_only": True,
    }))
    check("I2: notify_only=True -> payload mode='notify' (không dựng engine chạy LLM)",
          _captured_payload.get("mode") == "notify")

    asyncio.run(sched._do_create(_vault_c2, {
        "name": "Goi khach 2", "prompt": "Nhac goi khach Y", "schedule": "30 phut nua",
        "notify_only": False,
    }))
    check("I2: notify_only=False -> payload mode='task' (đọc MCP + ghi nháp như trước)",
          _captured_payload.get("mode") == "task")
finally:
    sched._post_reminder = _real_post_reminder


# ---- 10. Chặn I3: đơn vị ngày/tuần/tháng + mốc giờ cố định -> cron + lịch mơ hồ -> ERROR ----
# Trước khi vá, reviewer chạy thật: 'mỗi tuần'/'mỗi ngày'/'mỗi sáng'/'mỗi tháng' đều ra
# interval_min=5 (sàn cứng, KHÔNG phải chu kỳ thật), và 'mỗi sáng 7h' ra interval_min=420
# (hiểu nhầm thành "mỗi 7 tiếng" thay vì "7h sáng mỗi ngày").
check("I3: _interval_min('mỗi tuần') == 10080 (7 ngày, không phải sàn 5 phút)",
      sched._interval_min("mỗi tuần") == 10080)
check("I3: _interval_min('mỗi ngày') == 1440", sched._interval_min("mỗi ngày") == 1440)
check("I3: _interval_min('mỗi tháng') == 43200", sched._interval_min("mỗi tháng") == 43200)
check("I3: _interval_min('120m') vẫn == 120 (không phá đường cũ)", sched._interval_min("120m") == 120)
check("I3: _interval_min('2 tiếng') vẫn == 120", sched._interval_min("2 tiếng") == 120)

# Lịch mơ hồ (không số, không đơn vị, không mốc giờ) -> None, KHÔNG ĐƯỢC là 5.
check("I3 AN TOÀN: _interval_min('mỗi sáng') mơ hồ -> None (không âm thầm ra 5 phút)",
      sched._interval_min("mỗi sáng") is None)
check("I3 AN TOÀN: _interval_min('mỗi khi rảnh') mơ hồ -> None",
      sched._interval_min("mỗi khi rảnh") is None)
_vault_amb = tempfile.mkdtemp(prefix="javis-vault-amb-")
_res_amb = sched._create_loop_file(_vault_amb, name="Việc mơ hồ", prompt="x", schedule="mỗi sáng")
check("I3 AN TOÀN: tạo loop với lịch mơ hồ -> ERROR rõ ràng, KHÔNG tạo file",
      str(_res_amb).startswith("ERROR"))
check("I3 AN TOÀN: ERROR gợi ý cách sửa (số+đơn vị hoặc cron)",
      "cron" in _res_amb.lower() or "đơn vị" in _res_amb)
check("I3 AN TOÀN: không có file .md nào được ghi khi lịch mơ hồ",
      not list((Path(_vault_amb) / "Javis" / "loops").glob("*.md")))

# Mốc giờ cố định lặp hằng ngày -> route sang reminder + cron đúng giờ, KHÔNG phải interval 420.
check("I3: 'mỗi sáng 7h' -> route 'reminder' (cron), không còn là loop interval=420 phút",
      sched._route_kind("mỗi sáng 7h", False) == "reminder")
check("I3: _reminder_time_payload('mỗi sáng 7h') == cron '0 7 * * *'",
      sched._reminder_time_payload("mỗi sáng 7h") == {"cron": "0 7 * * *"})
check("I3: 'mỗi ngày lúc 8h' -> cron '0 8 * * *'",
      sched._reminder_time_payload("mỗi ngày lúc 8h") == {"cron": "0 8 * * *"})
check("I3: '7h sáng hằng ngày' (không có từ 'mỗi') -> vẫn ra cron '0 7 * * *'",
      sched._reminder_time_payload("7h sáng hằng ngày") == {"cron": "0 7 * * *"})
# 'mỗi 2 tiếng'/'mỗi 7h' KHÔNG có buổi trong ngày -> vẫn là duration, không bị hiểu nhầm thành cron.
check("I3: 'mỗi 2 tiếng' KHÔNG bị hiểu nhầm thành cron (route vẫn 'loop')",
      sched._route_kind("mỗi 2 tiếng", False) == "loop")
check("I3: 'mỗi 7h' (không buổi trong ngày) vẫn là duration, không thành cron",
      sched._route_kind("mỗi 7h", False) == "loop" and sched._interval_min("mỗi 7h") == 420)


# ---- 11. Dispatcher: op sai -> lỗi rõ; ctx.vault_root rỗng -> ERROR (không fallback Brain Default) ----
class _EmptyVaultCtx:
    vault_root = ""
    slug = "javis-schedule"

    def register_tool(self, **kw):
        pass

    def register_hook(self, *a, **k):
        pass


_res_novault = asyncio.run(sched.javis_schedule({"op": "list"}, _EmptyVaultCtx()))
check("dispatcher: ctx.vault_root rỗng -> ERROR, không âm thầm rơi về Brain Default",
      str(_res_novault).startswith("ERROR"))

_res_badop = asyncio.run(sched.javis_schedule({"op": "khong-ton-tai"}, _FakeCtx()))
check("dispatcher: op không hợp lệ -> báo lỗi rõ (không im lặng/crash)",
      str(_res_badop).startswith("ERROR") and "khong-ton-tai" in _res_badop)


if _fails:
    print(f"\nFAIL - test_javis_schedule: {len(_fails)} lỗi: {_fails}")
    sys.exit(1)
print("\nOK - test_javis_schedule: tất cả pass")
