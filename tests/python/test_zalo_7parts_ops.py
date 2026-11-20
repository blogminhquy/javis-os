"""Kiểm thử đồng bộ bộ 7 phần Zalo trên Javis OS: 3 chỗ ghim, tool_meta 24 công cụ,
cấu hình Scheduler/Workflow (Nhóm im lặng 22:30 -> 05:30 giờ VN, vòng đời Poll nexme marathon),
Cutover Checklist và kỷ luật văn bản (0 em/en-dash, 0 đường dẫn máy cá nhân, 0 từ cấm).

    python tests/run.py zalo_7parts_ops
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from zoneinfo import ZoneInfo

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-z7p-"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import cron_util  # noqa: E402
import mcp_catalog  # noqa: E402
import tools.release as release_tool  # noqa: E402
import workflow_graph  # noqa: E402
import zalo_cli  # noqa: E402
import zalo_login  # noqa: E402

fails = []


def check(name: str, cond: bool, extra: object = "") -> None:
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(extra) + "]") if extra and not cond else ""))
    if not cond:
        fails.append(name)


# ============================================================
# 1. Ba chỗ ghim và phân loại đủ 24 công cụ MCP Zalo
# ============================================================
catalog = json.loads((ROOT / "system" / "mcp-catalog.json").read_text(encoding="utf-8"))
zalo = next(c for c in catalog["connectors"] if c["id"] == "zalo")

check("ba chỗ ghim javis-zalo khớp tuyệt đối ở v1.14.0",
      zalo_cli.CLI_PACKAGE == zalo_login._CLI_PACKAGE
      and zalo["args"] == ["-y", "--prefer-offline", zalo_cli.CLI_PACKAGE, "mcp", "start"]
      and zalo_cli.CLI_PACKAGE.endswith("/v1.14.0"),
      (zalo_cli.CLI_PACKAGE, zalo_login._CLI_PACKAGE, zalo["args"]))

EXPECTED_READ = {
    "zalo_get_messages",
    "zalo_get_history",
    "zalo_search_history",
    "zalo_get_group_joins",
    "zalo_list_join_requests",
    "zalo_list_threads",
    "zalo_search_threads",
    "zalo_view_media",
    "zalo_get_labels",
    "zalo_get_group_settings",
    "zalo_get_poll",
}
EXPECTED_WRITE = {"zalo_mark_read"}
EXPECTED_DANGER = {
    "zalo_send_message",
    "zalo_send_link",
    "zalo_send_typing",
    "zalo_send_file",
    "zalo_send_voice",
    "zalo_send_video",
    "zalo_undo_message",
    "zalo_add_reaction",
    "zalo_review_join_requests",
    "zalo_update_group_settings",
    "zalo_create_poll",
    "zalo_lock_poll",
}

check("tool_meta.read khai đủ 11 công cụ đọc",
      set(zalo["tool_meta"]["read"]) == EXPECTED_READ,
      set(zalo["tool_meta"]["read"]) ^ EXPECTED_READ)
check("tool_meta.write khai đúng zalo_mark_read",
      set(zalo["tool_meta"]["write"]) == EXPECTED_WRITE,
      zalo["tool_meta"]["write"])
check("tool_meta.danger khai đủ 12 công cụ gửi/thay đổi trạng thái",
      set(zalo["tool_meta"]["danger"]) == EXPECTED_DANGER,
      set(zalo["tool_meta"]["danger"]) ^ EXPECTED_DANGER)

for t in EXPECTED_READ:
    check(f"classify({t}) == read & cho phép ở mức readonly",
          mcp_catalog.classify(zalo, t) == "read"
          and mcp_catalog.allowed(zalo, "readonly", "full", t)[0])

for t in EXPECTED_DANGER:
    check(f"classify({t}) == danger, chặn ở readonly/safe/suggest và mở ở full",
          mcp_catalog.classify(zalo, t) == "danger"
          and not mcp_catalog.allowed(zalo, "readonly", "full", t)[0]
          and not mcp_catalog.allowed(zalo, "safe", "full", t)[0]
          and not mcp_catalog.allowed(zalo, "full", "suggest", t)[0]
          and mcp_catalog.allowed(zalo, "full", "full", t)[0])

# ============================================================
# 2. Kiểm chứng cấu hình Scheduler & Workflow trong Playbook
# ============================================================
playbook_path = ROOT / "docs" / "dev" / "2026-11-zalo-7parts-ops-playbook.md"
playbook_text = playbook_path.read_text(encoding="utf-8")
m = re.search(r"```json:javis-zalo-7parts-schedules\n(.*?)\n```", playbook_text, re.S)
check("playbook chứa khối cấu hình JSON javis-zalo-7parts-schedules", m is not None)
spec = json.loads(m.group(1)) if m else {}

check("cấu hình khoá cứng 1 tài khoản Zalo = 1 kết nối WebSocket và múi giờ Asia/Ho_Chi_Minh",
      spec.get("single_websocket_invariant") is True and spec.get("timezone") == "Asia/Ho_Chi_Minh")

sandbox = spec.get("sandbox") or {}
check("cấu hình sandbox khoá cứng vào profile=nexme, Test nhom zalo, threadId=2928062252153346304",
      sandbox.get("profile") == "nexme"
      and sandbox.get("group_name") == "Test nhom zalo"
      and sandbox.get("thread_id") == "2928062252153346304"
      and sandbox.get("thread_type") == 1
      and set(sandbox.get("forbidden_profiles") or []) >= {"congdau", "haiyen"},
      sandbox)

NINE_FLAGS = [
    "blockName", "signAdminMsg", "setTopicOnly",
    "enableMsgHistory", "joinAppr", "lockCreatePost",
    "lockCreatePoll", "lockSendMsg", "lockViewMember",
]
check("khai báo bảo toàn đủ 9 cờ cài đặt nhóm theo PR #21 (có lockViewMember, không có addMemberOnly)",
      spec.get("preserved_group_flags") == NINE_FLAGS
      and "addMemberOnly" not in (spec.get("preserved_group_flags") or []),
      spec.get("preserved_group_flags"))

UNPRESERVED_GUARDS = [
    "blocked_members", "addMemberOnly", "bannFeature", "dirtyMedia", "banDuration",
]
check("khai báo đủ 5 trường cảnh vệ không bảo toàn được (blocked_members + UNPRESERVED_ZERO_FIELDS)",
      spec.get("unpreserved_guard_fields") == UNPRESERVED_GUARDS,
      spec.get("unpreserved_guard_fields"))

rems = {r["slug"]: r for r in (spec.get("reminders") or [])}
check("có đủ 5 lịch nhắc hẹn chuẩn (khoá nhóm 22:30, mở nhóm 05:30, tạo/đối chiếu/khoá poll)",
      set(rems) == {
          "zalo-quiet-hours-lock",
          "zalo-quiet-hours-unlock",
          "zalo-marathon-poll-create",
          "zalo-marathon-poll-reconcile",
          "zalo-marathon-poll-lock",
      },
      list(rems))

vn_tz = ZoneInfo("Asia/Ho_Chi_Minh")
anchor = datetime(2026, 11, 21, 12, 0, 0, tzinfo=vn_tz).timestamp()

for slug, r in rems.items():
    norm_cron = cron_util.validate_cron(r["cron"])
    check(f"reminder {slug}: mode=task, muc_quyen=full, once_ledger=True, cron hợp lệ ({norm_cron})",
          r.get("mode") == "task"
          and r.get("muc_quyen") == "full"
          and r.get("once_ledger") is True
          and r.get("timezone") == "Asia/Ho_Chi_Minh"
          and norm_cron == r["cron"])
    for tool_name in r.get("mcp_tools") or []:
        check(f"reminder {slug}: tool {tool_name} có trong catalog và chạy được ở mức full",
              mcp_catalog.allowed(zalo, "full", "full", tool_name)[0])

lock_dt = datetime.fromtimestamp(cron_util.cron_next(rems["zalo-quiet-hours-lock"]["cron"], anchor, vn_tz), vn_tz)
unlock_dt = datetime.fromtimestamp(cron_util.cron_next(rems["zalo-quiet-hours-unlock"]["cron"], anchor, vn_tz), vn_tz)
check("lịch khoá nhóm chạy đúng 22:30 giờ VN và mở nhóm chạy đúng 05:30 sáng hôm sau",
      (lock_dt.hour, lock_dt.minute) == (22, 30)
      and (unlock_dt.hour, unlock_dt.minute) == (5, 30)
      and unlock_dt > lock_dt
      and rems["zalo-quiet-hours-lock"].get("desired_value") is True
      and rems["zalo-quiet-hours-unlock"].get("desired_value") is False
      and rems["zalo-quiet-hours-lock"].get("verify_readback") is True
      and rems["zalo-quiet-hours-unlock"].get("verify_readback") is True,
      (lock_dt.isoformat(), unlock_dt.isoformat()))

for q_slug in ("zalo-quiet-hours-lock", "zalo-quiet-hours-unlock"):
    q_prompt = rems[q_slug].get("prompt") or ""
    check(f"reminder {q_slug}: prompt kiểm tra isAdmin, blocked_members và các cờ không bảo toàn được",
          "isAdmin" in q_prompt
          and "lockViewMember" in q_prompt
          and all(g in q_prompt for g in UNPRESERVED_GUARDS),
          q_prompt)

check("lịch poll ghi rõ ràng buộc Zalo API không cho mở lại poll đã khoá (irreversible)",
      rems["zalo-marathon-poll-lock"].get("irreversible_lock") is True
      and "zalo_create_poll" in (rems["zalo-marathon-poll-lock"].get("reopen_policy") or "")
      and rems["zalo-marathon-poll-create"]["poll_defaults"]["isAnonymous"] is False
      and rems["zalo-marathon-poll-reconcile"].get("companion_skill") == "nexme-ops")

# Biên dịch các workflow mẫu qua workflow_graph.compile_workflow
wfs = {w["slug"]: w for w in (spec.get("workflows") or [])}
check("có đủ 2 workflow mẫu cho khung giờ im lặng và đối chiếu poll nexme marathon",
      set(wfs) == {"zalo-quiet-hours-guard", "zalo-poll-nexme-reconcile"},
      list(wfs))
for slug, w in wfs.items():
    g = workflow_graph.compile_workflow(w["meta"], slug)
    check(f"workflow {slug} biên dịch hợp lệ qua workflow_graph ({len(g.nodes)} nodes, adapter={g.adapter})",
          g.slug == slug and g.adapter == workflow_graph.NATIVE_ADAPTER_VERSION and len(g.nodes) >= 2)

# ============================================================
# 3. Kiểm tra Cutover Checklist đầy đủ các thành phần nexme_marathon
# ============================================================
REQUIRED_CUTOVER_TOKENS = (
    "zca-serve",
    "serve-with-ids.ts",
    "56789",
    "zca-spike-serve",
    "56790",
    "zca-listener-nexme",
    "zca-listener-congdau",
    "ZcaGroupQuietHours",
    "ZcaSchedule",
    "ZcaPollLog",
    "zcaNexmeQueue",
    "zcaCongdauQueue",
    "zcaHaiyenQueue",
    "ZCA_FLOW",
    "quietHoursJob",
    "zcaSchedulerJob",
    "zcaHealthJob",
    "zalo-poll-create.mjs",
    "zalo-poll-lock.mjs",
    "active_polls.json",
    "2928062252153346304",
    "Rollback",
)
missing_tokens = [tok for tok in REQUIRED_CUTOVER_TOKENS if tok not in playbook_text]
check("Cutover Checklist liệt kê đủ tiến trình PM2, cổng, hàng đợi, cronjob, sandbox và rollback",
      not missing_tokens, missing_tokens)

# ============================================================
# 4. Kỷ luật văn bản & changelog fragment
# ============================================================
frag_path = ROOT / "changelog.d" / "zalo-7parts-ops.md"
parsed_frag = release_tool.parse_fragment(frag_path.read_text(encoding="utf-8"), frag_path.name)
check("changelog.d/zalo-7parts-ops.md hợp lệ qua tools/release.py parse_fragment",
      parsed_frag["bump"] == "minor" and bool(parsed_frag["vi"]) and bool(parsed_frag["en"]))

TOUCHED_FILES = [
    ROOT / "system" / "mcp-catalog.json",
    ROOT / "system" / "mcp-catalog.en.json",
    ROOT / "server" / "zalo_cli.py",
    ROOT / "server" / "zalo_login.py",
    ROOT / "docs" / "12-zalo.md",
    ROOT / "docs" / "en" / "12-zalo-agent-mcp.md",
    ROOT / "docs" / "dev" / "2026-11-zalo-7parts-ops-playbook.md",
    ROOT / "changelog.d" / "zalo-7parts-ops.md",
    ROOT / "tests" / "python" / "test_zalo_mcp.py",
    ROOT / "tests" / "python" / "test_zalo_send_file.py",
    Path(__file__),
]

BANNED_PHRASES = tuple(
    " ".join(parts)
    for parts in (
        ("thực", "chiến"),
        ("hành", "trình"),
        ("vô", "vàn"),
        ("tuyệt", "vời"),
        ("đỉnh", "cao"),
        ("tối", "ưu", "hoá"),
        ("tối", "ưu", "hóa"),
        ("bức", "tranh", "toàn", "cảnh"),
        ("chốt", "khách"),
        ("chốt", "đơn"),
        ("chốt", "sale"),
        ("xuống", "tiền"),
        ("lời", "thêm"),
    )
)
BAD_MARATHON_CASES = (
    " ".join(("Nexme", "Marathon")),
    " ".join(("NEXME", "MARATHON")),
    " ".join(("Nexme", "marathon")),
)
USER_PATH_PREFIX = "/" + "Users/"

for p in TOUCHED_FILES:
    txt = p.read_text(encoding="utf-8")
    rel = p.relative_to(ROOT).as_posix()
    check(f"{rel}: 0 em-dash / en-dash", chr(0x2014) not in txt and chr(0x2013) not in txt)
    check(f"{rel}: 0 đường dẫn máy cá nhân", USER_PATH_PREFIX not in txt)
    low = txt.lower()
    hit_banned = [w for w in BANNED_PHRASES if w in low]
    check(f"{rel}: 0 từ sáo rỗng AI hoặc từ sale cấm", not hit_banned, hit_banned)
    check(f"{rel}: 'nexme marathon' luôn viết thường",
          all(bad not in txt for bad in BAD_MARATHON_CASES))

if fails:
    print(f"\nFAIL - test_zalo_7parts_ops: {len(fails)} lỗi: {', '.join(fails)}")
    sys.exit(1)
print("\nOK - test_zalo_7parts_ops: tất cả pass")
