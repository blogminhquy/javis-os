"""Zalo voice reminders: tag the owner, "ring", speak the note, repeat, and read the owner's Vietnamese right.

    python tests/run.py zalo_voice_reminder      (no network, no real Zalo, no TTS engine)

Owner, 2026-11-16: when I book something by Zalo, tag my name at that time, make a virtual call with a voice message
saying what it is, repeat it as often as I asked, and learn how I write Vietnamese. The official name of a person is the
one THEY set for themselves, never the nickname the owner saved.

Checked here: which Zalo name wins; the lexicon (built-in shorthand, learned entries, the memory fact it mirrors,
teaching by quoted pairs); repeat levels; the delivery order and its failure rules; and the real reminder store firing a
repeating Zalo reminder up to `max_runs` and then stopping.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import sys
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="zvr-state-")
sys.path.insert(0, str(ROOT / "system" / "plugins" / "javis-schedule"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import zalo_voice_reminder as Z  # noqa: E402
import reminders  # noqa: E402

fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        fails.append(name)


# ============================================================
# 1. Names: the self-set one is official
# ============================================================
check("self-set name beats the owner's nickname for the person",
      Z.canonical_name({"alias": "Thế cầu cảng", "zaloName": "Bosun. Nguyễn Văn Thế", "displayName": "Thế"})
      == "Bosun. Nguyễn Văn Thế")
check("displayName is used when zaloName is missing, still not the alias",
      Z.canonical_name({"alias": "anh Bơm", "displayName": "Nguyễn Văn Thế"}) == "Nguyễn Văn Thế")
check("the nickname is only a last resort, so a tag is never empty",
      Z.canonical_name({"alias": "Anh Bơm"}) == "Anh Bơm")
check("nothing known gives an empty name, not a crash", Z.canonical_name(None) == "" and Z.canonical_name({}) == "")
check("blanks and double spaces are cleaned", Z.canonical_name({"zaloName": "  Nguyễn   Văn  Thế "}) == "Nguyễn Văn Thế")

# ============================================================
# 2. Vietnamese lexicon
# ============================================================
ROOT_B = tempfile.mkdtemp(prefix="zvr-brain-")
check("shorthand is spelled out: ko, dc", Z.normalize("ko dc quên nhé", ROOT_B) == "không được quên nhé",
      Z.normalize("ko dc quên nhé", ROOT_B))
check("the owner's one-letter 'a' before a name is 'anh' (from his own screenshot)",
      Z.normalize("nhớ call ngay cho a Thế nhé", ROOT_B) == "nhớ call ngay cho anh Thế nhé", Z.normalize("nhớ call ngay cho a Thế nhé", ROOT_B))
check("'e Lan' is 'em Lan' and 'c Hoa' is 'chị Hoa'", Z.normalize("gọi e Lan và c Hoa", ROOT_B) == "gọi em Lan và chị Hoa")
check("clock shorthand: 7h, 7h30", Z.normalize("họp lúc 7h rồi 7h30 đi ăn", ROOT_B) == "họp lúc 7 giờ rồi 7 giờ 30 đi ăn",
      Z.normalize("họp lúc 7h rồi 7h30 đi ăn", ROOT_B))
check("money and units are left alone: 5k, 100kg, link", Z.normalize("trả 5k và 100kg tại a.com/ko", ROOT_B) == "trả 5k và 100kg tại a.com/ko",
      Z.normalize("trả 5k và 100kg tại a.com/ko", ROOT_B))
check("plain English is returned untouched", Z.normalize("call a Tom at 7h", ROOT_B) == "call a Tom at 7h")
check("a real word is never rewritten: 'không', 'được'", Z.normalize("không được", ROOT_B) == "không được")

check("learn: a slip is stored", Z.learn(ROOT_B, "mai kia", "ngày mốt") is True)
check("learned entries are applied", Z.normalize("nhắc mai kia họp", ROOT_B) == "nhắc ngày mốt họp", Z.normalize("nhắc mai kia họp", ROOT_B))
check("learned beats built-in", Z.learn(ROOT_B, "dc", "đã được") and Z.normalize("dc rồi", ROOT_B) == "đã được rồi")
check("learn rejects empty and identical pairs", not Z.learn(ROOT_B, "", "x") and not Z.learn(ROOT_B, "x", "X"))
fact = Path(ROOT_B) / "memory" / "facts" / "vi-speech-lexicon.md"
index = Path(ROOT_B) / "memory" / "MEMORY.md"
check("the lexicon is mirrored as a memory fact the model reads", fact.is_file() and '"mai kia" nghĩa là "ngày mốt"' in fact.read_text(encoding="utf-8"))
check("MEMORY.md has exactly one pointer line", index.read_text(encoding="utf-8").count("vi-speech-lexicon.md") == 1)
Z.learn(ROOT_B, "mai kia", "ngày kia")
check("learning again updates in place, still one pointer line",
      index.read_text(encoding="utf-8").count("vi-speech-lexicon.md") == 1 and Z.load(ROOT_B)["mai kia"]["count"] == 2)
check("forget removes the entry", Z.forget(ROOT_B, "mai kia") and "mai kia" not in Z.load(ROOT_B))

check("teaching with a quoted pair is detected", Z.detect_correction('"mai kia" là "ngày mốt"') == [("mai kia", "ngày mốt")],
      Z.detect_correction('"mai kia" là "ngày mốt"'))
check("'ý anh là X chứ không phải Y' teaches Y -> X",
      Z.detect_correction('ý anh là "mai" chứ không phải "may"') == [("may", "mai")], Z.detect_correction('ý anh là "mai" chứ không phải "may"'))
check("ordinary speech teaches nothing", Z.detect_correction("mai là thứ hai nhé, nhớ gọi anh") == [])

EMPTY_B = tempfile.mkdtemp(prefix="zvr-empty-")
Z.learn(EMPTY_B, "xx", "yy")
Z.forget(EMPTY_B, "xx")
check("forgetting the last entry removes the fact and the pointer",
      not (Path(EMPTY_B) / "memory" / "facts" / "vi-speech-lexicon.md").exists()
      and "vi-speech-lexicon.md" not in (Path(EMPTY_B) / "memory" / "MEMORY.md").read_text(encoding="utf-8"))

# ============================================================
# 3. Repeat levels
# ============================================================
check("light is once", Z.repeat_preset("nhẹ") == (0, 1) and Z.repeat_preset("Light") == (0, 1))
check("medium: every 10 minutes, 3 times", Z.repeat_preset("vừa") == (10, 3))
check("urgent: every 5 minutes, 6 times; 'khẩn' is tighter", Z.repeat_preset("gắt") == (5, 6) and Z.repeat_preset("khẩn") == (3, 10))
check("an unknown level is one run", Z.repeat_preset("???") == (0, 1) and Z.repeat_preset(None) == (0, 1))

# ============================================================
# 4. Target
# ============================================================
check("target without a thread id is refused", Z.clean_target({"name": "Thế"}) is None and Z.clean_target("x") is None)
tg = Z.clean_target({"thread": "123456789", "type": 1, "uid": "987654", "alias": "Anh Bơm", "zaloName": "Nguyễn Văn Thế"})
check("target keeps the self-set name, group type and uid", tg and tg["name"] == "Nguyễn Văn Thế" and tg["type"] == 1 and tg["uid"] == "987654", tg)
check("a thread id with junk is cleaned to digits", Z.clean_target({"thread": "12-34 5"})["thread"] == "12345")

# ============================================================
# 5. One firing
# ============================================================
class Log:
    def __init__(self, text_ok=True, voice_ok=True, make_ok=True, fail_on=None):
        self.calls, self.text_ok, self.voice_ok, self.make_ok, self.fail_on = [], text_ok, voice_ok, make_ok, fail_on

    async def send_text(self, line, mention=None):
        self.calls.append(("text", line, mention))
        if self.fail_on and line.startswith(self.fail_on):
            return False, "Zalo refused"
        return self.text_ok, ("" if self.text_ok else "Zalo refused")

    async def send_voice(self, path):
        self.calls.append(("voice", path))
        return self.voice_ok, ("" if self.voice_ok else "no confirm")

    async def make_voice(self, line):
        self.calls.append(("make", line))
        if not self.make_ok:
            raise RuntimeError("tts down")
        return "/tmp/v.mp3"


async def fire(target, text, log, root=ROOT_B):
    return await Z.deliver(target, text, send_text=log.send_text, send_voice=log.send_voice, make_voice=log.make_voice, root=root)


GROUP = {"thread": "111222333", "type": 1, "uid": "987654", "zaloName": "Nguyễn Văn Thế"}
PRIVATE = {"thread": "444555666", "type": 0, "zaloName": "Nguyễn Văn Thế"}

lg = Log()
ok, err = asyncio.run(fire(GROUP, "nhớ gọi cho a Thế lúc 7h", lg))
kinds = [c[0] for c in lg.calls]
check("order: ring line, voice made, voice sent, written line", kinds == ["text", "make", "voice", "text"], kinds)
check("the call succeeds with no warning", ok and err == "")
check("in a group the ring line is a real tag of the right person",
      lg.calls[0][2] == {"uid": "987654", "name": "Nguyễn Văn Thế"} and lg.calls[0][1].startswith("@Nguyễn Văn Thế "), lg.calls[0])
check("the voice says the name first and the note with shorthand spelled out",
      lg.calls[1][1] == "Nguyễn Văn Thế ơi, nhớ gọi cho anh Thế lúc 7 giờ", lg.calls[1][1])
check("the written line is the reminder, spelled out", lg.calls[3][1] == "⏰ nhớ gọi cho anh Thế lúc 7 giờ", lg.calls[3][1])

lg = Log()
asyncio.run(fire(PRIVATE, "uống thuốc", lg))
check("in a private chat there is no tag, the name is plain text", lg.calls[0][2] is None and lg.calls[0][1].startswith("Nguyễn Văn Thế 📞"), lg.calls[0])

lg = Log(voice_ok=False)
ok, err = asyncio.run(fire(PRIVATE, "uống thuốc", lg))
check("a voice note that does not send is a warning, the reminder still arrived", ok and "voice not sent" in err, (ok, err))
lg = Log(make_ok=False)
ok, err = asyncio.run(fire(PRIVATE, "uống thuốc", lg))
check("a voice engine that fails is a warning too, and the written line still goes",
      ok and "voice" in err and lg.calls[-1][0] == "text" and lg.calls[-1][1].startswith("⏰"), (ok, err))
lg = Log(fail_on="Nguyễn")
ok, err = asyncio.run(fire(PRIVATE, "uống thuốc", lg))
check("a ring line Zalo refuses fails the firing and stops (nothing half-sent)", not ok and err.startswith("ring:") and len(lg.calls) == 1, (ok, err, lg.calls))
lg = Log(fail_on="⏰")
ok, err = asyncio.run(fire(PRIVATE, "uống thuốc", lg))
check("a written line Zalo refuses fails the firing", not ok and err.startswith("text:"), (ok, err))
lg = Log()
ok, err = asyncio.run(fire({"thread": "444555666", "type": 0, "name": "Thế", "ring": False, "voice": False}, "x", lg))
check("ring and voice can be switched off: only the written line goes", ok and [c[0] for c in lg.calls] == ["text"], lg.calls)
ok, err = asyncio.run(fire({}, "x", Log()))
check("no thread: refused with a reason, no crash", (not ok) and "thread" in err, (ok, err))

# ============================================================
# 6. The reminder store: Zalo target, repeat, stop after max_runs
# ============================================================
BRAIN = Path(tempfile.mkdtemp(prefix="zvr-rem-brain-"))
seen = []
reported = []


def atomic_write(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


async def fake_report(chat_id, text, **kw):
    reported.append((chat_id, text))
    return True, ""


async def fake_zalo(rem, text, brain):
    seen.append((rem["zalo"]["thread"], text, rem.get("runs_done")))
    return True, ""


def mk(zalo_deliver=fake_zalo):
    return reminders.RemindersFeature(reminders.RemindersDeps(
        brain_root=lambda _b: str(BRAIN), atomic_write_text=atomic_write, send_telegram=fake_report,
        build_system_prompt=lambda _b: "", aux_model=lambda: None, safe_tools=[], readonly_tools=[],
        scheduler_brains=lambda: [], zalo_deliver=zalo_deliver))


feat = mk()
rem = feat._create(str(BRAIN), "nhớ gọi cho a Thế", delay_min=1, repeat_min=5, max_runs=3, mode="notify",
                   zalo={"thread": "111222333", "type": 1, "uid": "987654", "zaloName": "Thế"}, allow_no_channel=True)
check("the Zalo target and the run cap are stored", rem["zalo"]["thread"] == "111222333" and rem["max_runs"] == 3, rem)
check("the view shows them to the Tasks page", feat._view(rem)["zalo"]["name"] == "Thế" and feat._view(rem)["max_runs"] == 3)
try:
    feat._create(str(BRAIN), "x", delay_min=1, zalo={"name": "no thread"}, allow_no_channel=True)
    check("a Zalo target without a chat id is refused at creation", False)
except ValueError:
    check("a Zalo target without a chat id is refused at creation", True)

statuses = []
for i in range(4):
    cur = next(r for r in feat._load(str(BRAIN))["reminders"] if r["id"] == rem["id"])
    if cur["status"] != "pending":
        break
    asyncio.run(feat._fire(str(BRAIN), dict(cur)))
    statuses.append(next(r for r in feat._load(str(BRAIN))["reminders"] if r["id"] == rem["id"])["status"])
check("it fired exactly max_runs times, then stopped as done", len(seen) == 3 and statuses == ["pending", "pending", "done"], (len(seen), statuses))
check("each firing reached Zalo with the reminder text", all("nhớ gọi cho a Thế" in s[1] for s in seen), seen)
check("the owner's usual report channel still got the reminder too", len(reported) == 3, reported)

# a Zalo failure is a failed firing, visible in the error
async def zalo_down(rem, text, brain):
    return False, "Zalo refused"

feat2 = mk(zalo_down)
rem2 = feat2._create(str(BRAIN), "kiểm tra", delay_min=1, mode="notify", zalo={"thread": "222333444"}, allow_no_channel=True)
asyncio.run(feat2._fire(str(BRAIN), dict(rem2)))
done2 = next(r for r in feat2._load(str(BRAIN))["reminders"] if r["id"] == rem2["id"])
check("a Zalo failure marks the run failed with the reason", done2["status"] == "failed" and "Zalo refused" in done2["error"], done2)

# no deliver dependency: the target is ignored, nothing crashes
feat3 = mk(None)
rem3 = feat3._create(str(BRAIN), "bình thường", delay_min=1, mode="notify", zalo={"thread": "222333444"}, allow_no_channel=True)
asyncio.run(feat3._fire(str(BRAIN), dict(rem3)))
check("without a Zalo deliverer the reminder still runs normally",
      next(r for r in feat3._load(str(BRAIN))["reminders"] if r["id"] == rem3["id"])["status"] == "done")

# ============================================================
# 7. The tool passes the target and the level through
# ============================================================
import plugin as sched  # noqa: E402

captured = {}


async def fake_post(payload, brain_name=""):
    captured.update(payload)
    return "ok"


sched._post_reminder = fake_post
asyncio.run(sched._do_create(str(BRAIN), {
    "name": "Gọi anh Thế", "prompt": "gọi a Thế", "schedule": "30 phút nữa", "notify_only": True,
    "zalo": {"thread": "111222333", "type": 0, "name": "Thế"}, "intensity": "gắt"}))
check("javis_schedule sends the Zalo target", captured.get("zalo", {}).get("thread") == "111222333", captured)
check("intensity 'gắt' becomes every 5 minutes, 6 runs", captured.get("repeat_min") == 5 and captured.get("max_runs") == 6, captured)
captured.clear()
asyncio.run(sched._do_create(str(BRAIN), {
    "name": "Một lần", "prompt": "x", "schedule": "30 phút nữa", "notify_only": True,
    "zalo": {"thread": "111222333"}, "intensity": "nhẹ"}))
check("intensity 'nhẹ' stays a single run", "max_runs" not in captured and not captured.get("repeat_min"), captured)
captured.clear()
asyncio.run(sched._do_create(str(BRAIN), {
    "name": "Đúng 4 lần", "prompt": "x", "schedule": "30 phút nữa", "notify_only": True,
    "zalo": {"thread": "111222333"}, "max_runs": 4}))
check("an exact max_runs wins", captured.get("max_runs") == 4, captured)

LEX_B = tempfile.mkdtemp(prefix="zvr-lex-")
check("op=lexicon teaches a pair", asyncio.run(sched.javis_schedule(
    {"op": "lexicon", "wrong": "mai mốt", "right": "ngày mốt"}, type("C", (), {"vault_root": LEX_B})())).startswith("Learned"))
check("op=lexicon lists what was taught", "mai mốt -> ngày mốt" in asyncio.run(sched.javis_schedule(
    {"op": "lexicon"}, type("C", (), {"vault_root": LEX_B})())))
check("op=lexicon forgets an entry", asyncio.run(sched.javis_schedule(
    {"op": "lexicon", "wrong": "mai mốt", "forget": True}, type("C", (), {"vault_root": LEX_B})())).startswith("Forgot"))

if fails:
    print(f"\nFAIL - test_zalo_voice_reminder: {len(fails)} lỗi: {fails}")
    sys.exit(1)
print("\nOK - test_zalo_voice_reminder: tất cả pass")
