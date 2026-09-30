"""Plugin zalo-group: tag ĐÚNG người trong nhóm Zalo, ghi chú, nhắc hẹn, poll.

    python tests/run.py zalo_group      (KHÔNG mạng: thay chỗ chạy CLI bằng bản ghi lại lệnh)

Chủ dự án (2026-09-30): "trong nhóm Javis không tag được tên chính xác như @minhquy", muốn có cả ghi chú, nhắc hẹn, poll. Thứ dễ hỏng
và không rút lại được nên được canh kỹ nhất:
  1. TAG NHẦM NGƯỜI. Zalo tag bằng uid, người dùng chỉ nói tên. Trùng tên hoặc không thấy thì phải HỎI LẠI kèm ứng viên, không đoán.
  2. VỊ TRÍ CHỮ. Zalo đọc pos/len theo đơn vị UTF-16 như JavaScript: emoji chiếm 2. Tính theo ký tự Python là vệt tô lệch chữ.
  3. GIỜ NHẮC HẸN. CLI đọc --time theo múi giờ của MÁY; người dùng nói theo giờ của Javis. VPS ở UTC thì "9 giờ sáng" thành 16 giờ.
  4. CLI KHÔNG thoát mã khác 0 khi Zalo từ chối: lỗi phải nổi lên chứ không được báo "đã gửi".
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import zalo_cli  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


spec = importlib.util.spec_from_file_location("zalo_group_plugin", ROOT / "system" / "plugins" / "zalo-group" / "plugin.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)

ESC = chr(27)
MOT = [{"id": "c1", "label": "Zalo chính", "home": "/state/zalo-a"}]
HAI = MOT + [{"id": "c2", "label": "Zalo phụ", "home": "/state/zalo-b"}]

RAN = []          # mỗi lệnh CLI đã "chạy": {"argv", "home"}
REPLY = {"rc": 0, "out": "{}", "err": ""}
QUEUE = []        # trả lời theo thứ tự từng lệnh (nếu có), rồi mới rơi về REPLY


def fake_world(conns=MOT, local=None, replies=None):
    zalo_cli.AUTO_INSTALL = False      # không cài thật bản ghim trong test
    zalo_cli.connections = lambda: list(conns)
    zalo_cli.check = lambda: None
    zalo_cli.shutil = type("S", (), {"which": staticmethod(lambda n: "/usr/bin/npx" if n == "npx" else None)})
    zalo_cli.os = type("O", (), {"name": "posix", "environ": {}, "path": __import__("os").path})
    P.local_members = lambda conn, thread: [dict(m) for m in (local or [])]
    QUEUE.clear()
    QUEUE.extend(replies or [])
    REPLY.update(rc=0, out="{}", err="")

    async def run(argv, home, timeout=120):
        RAN.append({"argv": argv, "home": home})
        r = QUEUE.pop(0) if QUEUE else REPLY
        return r["rc"], r["out"], r["err"]
    zalo_cli.run = run


def call(fn, args):
    RAN.clear()
    return asyncio.run(fn(args, None))


def ans(out):
    return json.loads(out)


def cli_args():
    """Phần sau `--json` của lệnh cuối cùng đã chạy."""
    a = RAN[-1]["argv"]
    return a[a.index("--json") + 1:]


def m(uid, name):
    return {"uid": uid, "name": name, "source": "hop_thu"}


MEMBERS = [m("1001", "Minh Quý"), m("1002", "Lan Anh"), m("1003", "Hùng"), m("1004", "Quý Nguyễn")]

# ============================================================
# 1. Chuẩn hoá và tìm tên
# ============================================================
check("norm bỏ dấu, hoa thường, dấu cách và @", P.norm("@Minh Quý") == "minhquy" and P.norm("Đặng  Văn") == "dangvan")
check("clean_uid bỏ hậu tố phiên bản của Zalo", P.clean_uid("123_0") == "123" and P.clean_uid("123") == "123" and P.clean_uid(None) == "")
check("utf16_len: emoji chiếm 2 đơn vị (như JavaScript)", P.utf16_len("a🎉b") == 4 and P.utf16_len("Quý") == 3)
check("tìm KHÔNG phân biệt dấu/hoa thường: 'minhquy' ra Minh Quý",
      [x["uid"] for x in P.find_members("minhquy", MEMBERS)] == ["1001"])
check("khớp chính xác thì thắng khớp chứa: 'Hùng' chỉ ra Hùng",
      [x["uid"] for x in P.find_members("hung", MEMBERS)] == ["1003"])
check("'quý' vừa khớp Minh Quý vừa Quý Nguyễn (khớp chứa) = 2 người, để hỏi lại",
      sorted(x["uid"] for x in P.find_members("quý", MEMBERS)) == ["1001", "1004"])
check("không thấy thì rỗng, chuỗi rỗng thì rỗng", P.find_members("khong co", MEMBERS) == [] and P.find_members("@", MEMBERS) == [])

# ============================================================
# 2. Dựng tin có tag: vị trí chữ
# ============================================================
T1 = {"uid": "1001", "display": "Minh Quý", "typed": ["minhquy", "Minh Quý"]}
T2 = {"uid": "1002", "display": "Lan Anh", "typed": ["lan", "Lan Anh"]}
txt, ms = P.build_mention_message("@minhquy họp lúc 9h nhé", [T1])
check("@minhquy trong tin được thay bằng tên thật và tính đúng vị trí", txt == "@Minh Quý họp lúc 9h nhé"
      and ms == [{"uid": "1001", "pos": 0, "len": 9, "display": "Minh Quý"}], (txt, ms))
txt, ms = P.build_mention_message("Nhờ @lan gửi báo cáo cho @MINH QUÝ giúp", [T1, T2])
check("hai người, thứ tự trong tin khác thứ tự yêu cầu: vị trí đúng và tăng dần",
      txt == "Nhờ @Lan Anh gửi báo cáo cho @Minh Quý giúp" and [x["uid"] for x in ms] == ["1002", "1001"]
      and txt[ms[0]["pos"]:ms[0]["pos"] + ms[0]["len"]] == "@Lan Anh" and txt[ms[1]["pos"]:ms[1]["pos"] + ms[1]["len"]] == "@Minh Quý", (txt, ms))
txt, ms = P.build_mention_message("Họp lúc 9h nhé", [T1])
check("không có @ trong tin thì chèn tên ở ĐẦU tin", txt == "@Minh Quý Họp lúc 9h nhé" and ms[0]["pos"] == 0 and ms[0]["len"] == 9, (txt, ms))
txt, ms = P.build_mention_message("🎉 chúc mừng @minhquy nhé", [T1])
check("CANARY: có emoji trước tên thì pos tính theo UTF-16 (emoji = 2), không theo ký tự Python",
      ms[0]["pos"] == 13 - 1 - 9 + 1 + 0 or ms[0]["pos"] == P.utf16_len("🎉 chúc mừng "), ms)
check("và pos ấy khác vị trí ký tự Python (chứng tỏ có khác biệt để mà canh)", ms[0]["pos"] == len("🎉 chúc mừng ") + 1)
txt, ms = P.build_mention_message("@Quýnh ơi", [{"uid": "9", "display": "Quý", "typed": ["Quý"]}])
check("CANARY: '@Quý' không ăn vào đầu '@Quýnh' (tên dài hơn)", txt.startswith("@Quý ") and ms[0]["pos"] == 0 and txt == "@Quý @Quýnh ơi", (txt, ms))
txt, ms = P.build_mention_message("@all mọi người ơi", [{"uid": "-1", "display": "All", "typed": ["All"]}])
check("@All dùng uid -1", txt == "@All mọi người ơi" and ms[0]["uid"] == "-1" and ms[0]["len"] == 4, (txt, ms))
txt, ms = P.build_mention_message("@minhquy và @minhquy nữa", [T1])
check("cùng một người xuất hiện hai lần thì chỉ tag lần đầu", len(ms) == 1 and ms[0]["pos"] == 0)

# ============================================================
# 3. Tìm người để tag
# ============================================================
fake_world(local=MEMBERS)
tg, why = asyncio.run(P.resolve_targets(MOT[0], "g1", [{"name": "minhquy", "uid": ""}]))
check("tên duy nhất thì ra uid, KHÔNG gọi mạng", not why and tg[0]["uid"] == "1001" and RAN == [], (tg, why))
tg, why = asyncio.run(P.resolve_targets(MOT[0], "g1", [{"name": "quý", "uid": ""}]))
check("CANARY: trùng tên thì HỎI LẠI kèm ứng viên, không tag ai", tg == [] and "Minh Quý" in why and "Quý Nguyễn" in why and "KHÔNG đoán" in why, why)
check("nhắc rõ tag nhầm không rút lại được", "không rút lại" in why)
tg, why = asyncio.run(P.resolve_targets(MOT[0], "g1", [{"name": "", "uid": "5555"}]))
check("đã có uid thì dùng thẳng, không cần biết tên", not why and tg[0]["uid"] == "5555" and tg[0]["display"] == "5555" or tg[0]["display"], (tg, why))
tg, why = asyncio.run(P.resolve_targets(MOT[0], "g1", [{"name": "Minh Quý", "uid": ""}, {"name": "minhquy", "uid": ""}]))
check("cùng một người được nêu hai lần chỉ tag một lần", len(tg) == 1)

INFO = json.dumps({"gridInfoMap": {"g1": {"memberIds": ["1001_0", "2001_0", "2002_0"],
                                            "currentMems": [{"id": "2001", "dName": "Bảo Trân"}]}}})
PROFILES = json.dumps({"profiles": {"2002": {"displayName": "Đức Thắng", "zaloName": "thang"}}})
fake_world(local=MEMBERS, replies=[{"rc": 0, "out": INFO, "err": ""}, {"rc": 0, "out": PROFILES, "err": ""}])
tg, why = asyncio.run(P.resolve_targets(MOT[0], "g1", [{"name": "bao tran", "uid": ""}]))
check("không thấy trong người đã nhắn thì hỏi Zalo: 'bao tran' ra Bảo Trân (uid 2001)", not why and tg[0]["uid"] == "2001", (tg, why))
argvs = [r["argv"][r["argv"].index("--json") + 1:] for r in RAN]
check("gọi `group info <id nhóm>` rồi `group members-info` cho các id mà Zalo chưa kèm tên trong `group info`",
      argvs[0] == ["group", "info", "g1"] and argvs[1] == ["group", "members-info", "1001", "2002"], argvs)
check("và chạy trong HOME của phiên Zalo", all(r["home"] == "/state/zalo-a" for r in RAN))

fake_world(local=MEMBERS, replies=[{"rc": 0, "out": INFO, "err": ""}, {"rc": 0, "out": PROFILES, "err": ""}])
tg, why = asyncio.run(P.resolve_targets(MOT[0], "g1", [{"name": "thang", "uid": ""}]))
check("người chưa nhắn lần nào vẫn tìm được qua danh sách thành viên của Zalo", not why and tg[0]["uid"] == "2002" and tg[0]["display"] == "Đức Thắng", (tg, why))

fake_world(local=MEMBERS, replies=[{"rc": 0, "out": INFO, "err": ""}, {"rc": 0, "out": PROFILES, "err": ""}])
tg, why = asyncio.run(P.resolve_targets(MOT[0], "g1", [{"name": "ngoc anh", "uid": ""}]))
check("không thấy ai thì báo lỗi kèm vài thành viên và cách xem đủ", tg == [] and "zalo_group_members" in why and "Minh Quý" in why, why)

fake_world(local=[], replies=[{"rc": 0, "out": "", "err": ESC + "[31m  ✗ Group not found" + ESC + "[39m"}])
tg, why = asyncio.run(P.resolve_targets(MOT[0], "g1", [{"name": "ai đó", "uid": ""}]))
check("không thấy trong Hộp thư và Zalo cũng lỗi thì nói cả hai và gợi ý đưa uid", tg == [] and "Group not found" in why and "uid" in why, why)

# ============================================================
# 4. zalo_send_mention từ đầu đến cuối
# ============================================================
SENT = json.dumps({"message": {"msgId": "777"}})
fake_world(local=MEMBERS, replies=[{"rc": 0, "out": SENT, "err": ""}])
r = call(P._send_mention, {"thread_id": "g1", "text": "@minhquy họp lúc 9h nhé", "mentions": ["minhquy"]})
d = ans(r)
a = cli_args()
check("gửi được: trả JSON có tên thật, uid, vị trí, id tin", d["ok"] and d["text"] == "@Minh Quý họp lúc 9h nhé"
      and d["mentions"] == [{"uid": "1001", "name": "Minh Quý", "pos": 0, "len": 9}] and d["message_id"] == "777", r)
check("lệnh đúng: msg send <nhóm> <nội dung> -t 1 --mention pos:uid:len",
      a == ["msg", "send", "g1", "@Minh Quý họp lúc 9h nhé", "-t", "1", "--mention", "0:1001:9"], a)
check("chạy trong HOME của đúng tài khoản", RAN[-1]["home"] == "/state/zalo-a")

fake_world(local=MEMBERS, replies=[{"rc": 0, "out": SENT, "err": ""}])
r = call(P._send_mention, {"thread_id": "g1", "text": "- nhờ @Hùng làm giúp", "mentions": [{"name": "Hùng", "uid": "1003"}]})
a = cli_args()
check("CANARY: tin bắt đầu bằng '-' thì cờ đứng trước, rồi `--`, rồi nhóm và nội dung (không bị coi là cờ)",
      ans(r)["ok"] and a == ["msg", "send", "-t", "1", "--mention", "6:1003:5", "--", "g1", "- nhờ @Hùng làm giúp"], a)

fake_world(local=MEMBERS, replies=[{"rc": 0, "out": SENT, "err": ""}])
r = call(P._send_mention, {"thread_id": "g1", "text": "chào cả nhà", "mention_all": True})
check("mention_all thì @All với uid -1", ans(r)["ok"] and "--mention" in cli_args() and cli_args()[-1].split(":")[1] == "-1", cli_args())

fake_world(local=MEMBERS)
r = call(P._send_mention, {"thread_id": "g1", "text": "hi", "mentions": ["quý"]})
check("CANARY: trùng tên thì TỪ CHỐI, KHÔNG gửi gì", r.startswith("ERROR") and "khớp 2 người" in r and RAN == [], r)
r = call(P._send_mention, {"thread_id": "g1", "text": "hi"})
check("không nêu ai để tag thì từ chối, không gửi", r.startswith("ERROR") and "mentions" in r and RAN == [])
r = call(P._send_mention, {"text": "hi", "mentions": ["minhquy"]})
check("thiếu thread_id thì chỉ cách tìm", "zalo_search_threads" in r and RAN == [])
r = call(P._send_mention, {"thread_id": "g1", "mentions": ["minhquy"]})
check("thiếu nội dung thì báo", r.startswith("ERROR") and "text" in r and RAN == [])
r = call(P._send_mention, {"thread_id": "g1", "text": "x" * 2001, "mentions": ["minhquy"]})
check("tin quá dài thì từ chối", r.startswith("ERROR") and RAN == [])
r = call(P._send_mention, {"thread_id": "g1", "text": "hi", "mentions": [str(i) for i in range(1000, 1030)]})
check("tag quá nhiều người một tin thì từ chối", r.startswith("ERROR") and RAN == [])

fake_world(conns=HAI, local=MEMBERS)
r = call(P._send_mention, {"thread_id": "g1", "text": "hi", "mentions": ["minhquy"]})
check("CANARY: hai tài khoản Zalo mà không nêu rõ thì TỪ CHỐI (không gửi dưới danh tính người khác)", r.startswith("ERROR")
      and "connection_id" in r and RAN == [] and "Zalo phụ" in r)
fake_world(conns=HAI, local=MEMBERS, replies=[{"rc": 0, "out": SENT, "err": ""}])
r = call(P._send_mention, {"thread_id": "g1", "text": "hi", "mentions": ["minhquy"], "connection_id": "c2"})
check("nêu connection_id thì gửi bằng đúng tài khoản", ans(r)["account"] == "Zalo phụ" and RAN[-1]["home"] == "/state/zalo-b")

fake_world(local=MEMBERS, replies=[{"rc": 0, "out": "", "err": ESC + "[31m  ✗ Send failed: bạn không còn trong nhóm" + ESC + "[39m"}])
r = call(P._send_mention, {"thread_id": "g1", "text": "hi", "mentions": ["minhquy"]})
check("CANARY: CLI thoát mã 0 nhưng Zalo từ chối thì báo LỖI, không báo đã gửi", r.startswith("ERROR") and "không còn trong nhóm" in r, r)

fake_world(local=MEMBERS, replies=[{"rc": None, "out": None, "err": "quá 120 " + zalo_cli.TIMEOUT_MARK}])
r = call(P._create_poll, {"group_id": "g1", "question": "Trưa nay ăn gì?", "options": ["Phở", "Bún"]})
check("CANARY: poll quá giờ thì báo KHÔNG RÕ đã tạo chưa và dặn xem nhóm trước khi thử lại (kẻo ra hai poll)",
      r.startswith("ERROR") and "KHÔNG rõ" in r and "hai lần" in r and "khoá quyền" not in r, r)

# ============================================================
# 5. Ghi chú
# ============================================================
fake_world(replies=[{"rc": 0, "out": json.dumps({"topicId": "n42"}), "err": ""}])
r = call(P._create_note, {"group_id": "g1", "title": "Họp thứ Hai lúc 9h", "pin": True})
check("tạo ghi chú: lệnh và id", ans(r)["ok"] and ans(r)["note_id"] == "n42" and ans(r)["pinned"] is True
      and cli_args() == ["group", "note-create", "g1", "Họp thứ Hai lúc 9h", "--pin"], (r, cli_args()))
fake_world(replies=[{"rc": 0, "out": "{}", "err": ""}])
call(P._create_note, {"group_id": "g1", "title": "- Việc cần làm"})
check("ghi chú bắt đầu bằng '-' có `--`", cli_args() == ["group", "note-create", "--", "g1", "- Việc cần làm"], cli_args())
fake_world()
check("thiếu tiêu đề hoặc nhóm thì báo", call(P._create_note, {"group_id": "g1"}).startswith("ERROR") and call(P._create_note, {"title": "x"}).startswith("ERROR") and RAN == [])
check("ghi chú quá dài thì từ chối", call(P._create_note, {"group_id": "g1", "title": "x" * 501}).startswith("ERROR") and RAN == [])
fake_world(replies=[{"rc": 0, "out": "", "err": "  ✗ Create note failed: Bạn không có quyền"}])
r = call(P._create_note, {"group_id": "g1", "title": "x"})
check("nhóm khoá quyền: báo thẳng lý do từ Zalo", r.startswith("ERROR") and "không có quyền" in r and "khoá quyền" in r, r)

# ============================================================
# 6. Nhắc hẹn: giờ theo múi giờ của Javis, đổi sang đồng hồ máy
# ============================================================
VN = timezone(timedelta(hours=7))
import localefmt  # noqa: E402

real_now = localefmt.now
localefmt.now = lambda: datetime.now(VN)
future = (datetime.now(VN) + timedelta(days=3)).replace(hour=9, minute=0, second=0, microsecond=0)
want_local = future.astimezone().strftime("%Y-%m-%d %H:%M")
got, why = P.machine_local_time(future.strftime("%Y-%m-%d %H:%M"))
check("CANARY: 9 giờ theo giờ Javis (UTC+7) được đổi sang đồng hồ của máy (VPS ở UTC thì không được gửi nguyên chữ)",
      got == want_local and not why, (got, want_local))
got, why = P.machine_local_time("2000-01-01 09:00")
check("giờ đã qua thì từ chối", got is None and "đã qua" in why)
for bad in ("mai 9h", "2026-13-40 25:61", "", "2026-10-02", None):
    check(f"định dạng giờ sai bị từ chối: {bad!r}", P.machine_local_time(bad)[0] is None)
got, why = P.machine_local_time(future.strftime("%Y-%m-%dT%H:%M"))
check("chấp nhận dấu T thay dấu cách", got == want_local)

fake_world(replies=[{"rc": 0, "out": json.dumps({"reminderId": "r9"}), "err": ""}])
r = call(P._create_reminder, {"thread_id": "g1", "title": "Nộp báo cáo", "time": future.strftime("%Y-%m-%d %H:%M"),
                              "repeat": "weekly", "emoji": "📌"})
a = cli_args()
check("tạo nhắc hẹn: lệnh đúng (nhóm mặc định, giờ máy, lặp, emoji)", ans(r)["ok"] and ans(r)["reminder_id"] == "r9" and a[:4] == ["reminder", "create", "g1", "Nộp báo cáo"]
      and a[a.index("-t") + 1] == "1" and a[a.index("--time") + 1] == want_local and a[a.index("--repeat") + 1] == "weekly"
      and a[a.index("--emoji") + 1] == "📌", (r, a))
check("kết quả trả lại giờ THEO NGƯỜI DÙNG (không lộ giờ máy làm người đọc rối)", ans(r)["time"] == future.strftime("%Y-%m-%d %H:%M"))
fake_world(replies=[{"rc": 0, "out": "{}", "err": ""}])
call(P._create_reminder, {"thread_id": "u1", "title": "Gọi lại khách", "time": future.strftime("%Y-%m-%d %H:%M"), "thread_type": 0})
check("chat riêng thì -t 0, mặc định không lặp", cli_args()[cli_args().index("-t") + 1] == "0" and cli_args()[cli_args().index("--repeat") + 1] == "none")
fake_world()
for args, lab in (({"thread_id": "g1", "title": "x", "time": "2000-01-01 09:00"}, "giờ đã qua"),
                  ({"thread_id": "g1", "title": "x", "time": future.strftime("%Y-%m-%d %H:%M"), "repeat": "hourly"}, "lặp lạ"),
                  ({"thread_id": "g1", "time": future.strftime("%Y-%m-%d %H:%M")}, "thiếu tiêu đề"),
                  ({"title": "x", "time": future.strftime("%Y-%m-%d %H:%M")}, "thiếu thread_id"),
                  ({"thread_id": "g1", "title": "x"}, "thiếu giờ")):
    check(f"nhắc hẹn sai bị từ chối trước khi gọi CLI: {lab}", call(P._create_reminder, args).startswith("ERROR") and RAN == [])
localefmt.now = real_now

# ============================================================
# 7. Poll
# ============================================================
fake_world(replies=[{"rc": 0, "out": json.dumps({"poll_id": "p5", "options": [{"option_id": 1, "content": "Phở"}]}), "err": ""}])
r = call(P._create_poll, {"group_id": "g1", "question": "Trưa nay ăn gì?", "options": ["Phở", "Bún", "Cơm"], "multi": True,
                          "anonymous": True, "hide_results_until_voted": True, "allow_add_options": True, "expire_minutes": 90})
a = cli_args()
check("tạo poll: id và lệnh đúng (câu hỏi + lựa chọn đứng trước, cờ đứng sau)", ans(r)["ok"] and ans(r)["poll_id"] == "p5"
      and a[:6] == ["poll", "create", "g1", "Trưa nay ăn gì?", "Phở", "Bún"] and a[6] == "Cơm"
      and {"--multi", "--anonymous", "--hide-preview", "--add-options"} <= set(a) and a[a.index("--expire") + 1] == "90", (r, a))
fake_world(replies=[{"rc": 0, "out": "{}", "err": ""}])
call(P._create_poll, {"group_id": "g1", "question": "Đi không?", "options": ["Có", "có", "Có", "Không"]})
check("lựa chọn trùng chữ chính xác bị gộp", cli_args()[:6] == ["poll", "create", "g1", "Đi không?", "Có", "có"] or cli_args().count("Có") == 1, cli_args())
check("không cờ nào bật thì không truyền cờ", not any(x.startswith("--") for x in cli_args()), cli_args())
fake_world()
for args, lab in (({"group_id": "g1", "question": "x", "options": ["chỉ một"]}, "một lựa chọn"),
                  ({"group_id": "g1", "question": "x", "options": [str(i) for i in range(11)]}, "11 lựa chọn"),
                  ({"group_id": "g1", "question": "x", "options": ["a", "a"]}, "hai lựa chọn giống hệt"),
                  ({"group_id": "g1", "question": "x", "options": ["a", "b" * 101]}, "lựa chọn quá dài"),
                  ({"group_id": "g1", "question": "q" * 201, "options": ["a", "b"]}, "câu hỏi quá dài"),
                  ({"group_id": "g1", "options": ["a", "b"]}, "thiếu câu hỏi"),
                  ({"question": "x", "options": ["a", "b"]}, "thiếu group_id"),
                  ({"group_id": "g1", "question": "x", "options": ["a", "b"], "expire_minutes": "abc"}, "hạn không phải số"),
                  ({"group_id": "g1", "question": "x", "options": ["a", "b"], "expire_minutes": 999999}, "hạn quá dài")):
    check(f"poll sai bị từ chối trước khi gọi CLI: {lab}", call(P._create_poll, args).startswith("ERROR") and RAN == [])
fake_world(replies=[{"rc": 0, "out": "", "err": "  ✗ Create poll failed: chỉ quản trị viên được tạo poll"}])
r = call(P._create_poll, {"group_id": "g1", "question": "x", "options": ["a", "b"]})
check("Zalo từ chối (mã 0 nhưng ✗): báo lỗi kèm gợi ý quyền nhóm", r.startswith("ERROR") and "quản trị viên" in r and "khoá quyền" in r, r)

# ============================================================
# 8. Danh sách thành viên
# ============================================================
fake_world(local=[m("1001", "Minh Quý")], replies=[{"rc": 0, "out": INFO, "err": ""}, {"rc": 0, "out": PROFILES, "err": ""}])
r = call(P._members, {"thread_id": "g1"})
d = ans(r)
names = {x["uid"]: x["name"] for x in d["members"]}
check("gộp người đã nhắn với thành viên của Zalo, đủ tên", d["ok"] and names == {"1001": "Minh Quý", "2001": "Bảo Trân", "2002": "Đức Thắng"}, names)
fake_world(local=[m("1001", "Minh Quý")], replies=[{"rc": 0, "out": INFO, "err": ""}, {"rc": 0, "out": PROFILES, "err": ""}])
d = ans(call(P._members, {"thread_id": "g1", "query": "thang"}))
check("query lọc theo tên, không dấu", [x["uid"] for x in d["members"]] == ["2002"] and d["query"] == "thang", d)
fake_world(local=[m("1001", "Minh Quý")], replies=[{"rc": 0, "out": "", "err": "  ✗ mạng lỗi"}])
d = ans(call(P._members, {"thread_id": "g1"}))
check("Zalo lỗi mà còn danh sách người đã nhắn thì vẫn trả, kèm ghi chú vì sao thiếu", d["count"] == 1 and "mạng lỗi" in d["note"], d)
fake_world(local=[], replies=[{"rc": 0, "out": "", "err": "  ✗ mạng lỗi"}])
check("không có gì cả thì báo lỗi", call(P._members, {"thread_id": "g1"}).startswith("ERROR"))
check("thiếu thread_id thì chỉ cách tìm", "zalo_search_threads" in call(P._members, {}))

# ============================================================
# 9. Khai báo plugin
# ============================================================
import fastyaml  # noqa: E402

y = fastyaml.safe_load((ROOT / "system" / "plugins" / "zalo-group" / "plugin.yaml").read_text(encoding="utf-8"))


class Ctx:
    def __init__(self):
        self.tools = []

    def register_tool(self, **kw):
        self.tools.append(kw)


tc = Ctx()
P.register(tc)
by = {t["name"]: t for t in tc.tools}
check("năm tool, khớp plugin.yaml", sorted(by) == sorted(y["tools"]) and len(by) == 5, sorted(by))
check("plugin khai min_mode full và bật sẵn", y.get("min_mode") == "full" and y.get("enabled") is True and y.get("slug") == "zalo-group")
check("CANARY: bốn tool ghi/gửi ở mức full (chế độ suggest không tự tag hay đăng poll được)",
      all(by[n]["min_mode"] == "full" for n in ("zalo_send_mention", "zalo_create_note", "zalo_create_reminder", "zalo_create_poll")))
check("tra danh sách thành viên là chỉ đọc", by["zalo_group_members"]["min_mode"] == "readonly")
check("mọi tool có check_fn và handler", all(callable(t["check_fn"]) and callable(t["handler"]) for t in tc.tools))
check("schema bắt buộc đúng tham số", by["zalo_send_mention"]["schema"]["required"] == ["thread_id", "text"]
      and by["zalo_create_poll"]["schema"]["required"] == ["group_id", "question", "options"]
      and by["zalo_create_reminder"]["schema"]["required"] == ["thread_id", "title", "time"])
check("mô tả tool phân biệt nhắc hẹn Zalo với nhắc hẹn riêng của Javis (tránh model nhầm hai loại)",
      "javis_schedule" in by["zalo_create_reminder"]["description"])
check("mô tả dặn hỏi lại khi trùng tên, không đoán", "HỎI LẠI" in by["zalo_send_mention"]["description"])

check("không dùng em dash trong plugin và test này", chr(0x2014) not in open(__file__, encoding="utf-8").read()
      and chr(0x2014) not in (ROOT / "system" / "plugins" / "zalo-group" / "plugin.py").read_text(encoding="utf-8"))

if fails:
    print("\nFAIL - test_zalo_group: " + str(len(fails)) + " lỗi: " + ", ".join(fails))
    sys.exit(1)
print("\nOK - test_zalo_group: tất cả pass")
