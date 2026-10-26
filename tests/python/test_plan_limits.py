"""Vòng tròn hạn mức gói (0.329.0): số 5 giờ và số tuần lấy đúng từ chính CLI, không đọc token.

    python tests/run.py plan_limits

Chủ repo 25/10 gửi ảnh "Plan usage limits" của Claude (phiên 9%, tuần 24%) và hỏi Javis có lấy
được không. Claude Code tự phát `rate_limit_event` trong luồng, Codex phát
`account/rateLimits/updated` và ghi `rate_limits` vào file rollout. Test này giữ ba đường đó.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="javis-pl-")
os.environ["JAVIS_STATE_DIR"] = _TMP
os.environ["JAVIS_CODEX_SESSIONS_DIR"] = os.path.join(_TMP, "codex")

import plan_limits as pl  # noqa: E402

fails = []


def check(ten, ok, them=None):
    print(("PASS: " if ok else "FAIL: ") + ten + ("" if ok or them is None else f"  [{them}]"))
    if not ok:
        fails.append(ten)


NOW = 1792960000
# Đúng payload thật bắt được từ luồng Claude Code của phiên làm tính năng này.
RAW = {"isUsingOverage": False, "overageStatus": "rejected", "rateLimitType": "five_hour",
       "resetsAt": NOW + 11000, "status": "allowed",
       "unifiedWindows": {"five_hour": {"resetsAt": NOW + 11000, "status": "allowed", "utilization": 0.09},
                          "seven_day": {"resetsAt": NOW + 531200, "status": "allowed", "utilization": 0.23}}}

# 1. Claude Code qua map_message của engine thật (RateLimitEvent của SDK). claude_sdk_engine.py bị khoá
#    bằng bằng chứng kiểm định native (PROFILE_SOURCES), nên móc từ ngoài chứ không sửa file đó.
from claude_agent_sdk.types import RateLimitEvent, RateLimitInfo  # noqa: E402
import claude_sdk_engine as eng  # noqa: E402

ev = RateLimitEvent(rate_limit_info=RateLimitInfo(status="allowed", resets_at=RAW["resetsAt"],
                                                  rate_limit_type="five_hour", utilization=0.09, raw=RAW),
                    uuid="u", session_id="s")
check("cài móc vào engine được", pl.cai_vao_claude_sdk() and pl.cai_vao_claude_sdk())
check("móc hai lần không bọc hai lớp", not getattr(eng.map_message.__wrapped__, "_plan_limits", False))
events, sid = eng.map_message(ev)
check("rate_limit_event không đẻ sự kiện chat nào", events == [] and sid is None, (events, sid))
d = pl.doc(now=NOW)
c = d["claude"] or {}
check("Claude: phiên 5 giờ 9%", (c.get("five_hour") or {}).get("pct") == 9, c)
check("Claude: tuần 23%", (c.get("seven_day") or {}).get("pct") == 23, c)
check("Claude: giờ làm mới giữ nguyên", c["five_hour"]["resets_at"] == NOW + 11000)
check("Claude: mức xanh khi cả hai còn thấp", c.get("muc") == "ok", c.get("muc"))

# 2. Gần hết tuần (5 giờ còn thấp) vẫn đỏ: đỏ theo cái nào sát hơn.
raw2 = json.loads(json.dumps(RAW))
raw2["unifiedWindows"]["seven_day"]["utilization"] = 0.86
pl.ghi_claude(raw2, now=NOW)
c = pl.doc(now=NOW)["claude"]
check("tuần 86% thì đỏ dù 5 giờ mới 9%", c["muc"] == "bad" and c["max"] == 86, c)
raw2["unifiedWindows"]["seven_day"]["utilization"] = 0.6
pl.ghi_claude(raw2, now=NOW)
check("60% thì vàng", pl.doc(now=NOW)["claude"]["muc"] == "warn")

# 3. CLI cũ chỉ gửi cửa sổ đang ràng buộc: gộp vào, cửa sổ kia giữ số cũ.
pl.ghi_claude({"status": "allowed_warning", "rateLimitType": "five_hour", "utilization": 0.82,
               "resetsAt": NOW + 9000}, now=NOW + 60)
c = pl.doc(now=NOW + 60)["claude"]
check("CLI cũ: 5 giờ cập nhật 82%", c["five_hour"]["pct"] == 82, c)
check("CLI cũ: tuần giữ 60%", c["seven_day"]["pct"] == 60, c)
check("CLI cũ: đỏ", c["muc"] == "bad")

# 4. Qua giờ làm mới: cửa sổ đó về 0, cờ moi bật.
c = pl.doc(now=NOW + 9001)["claude"]
check("qua giờ làm mới thì 5 giờ về 0", c["five_hour"]["pct"] == 0 and c["five_hour"]["moi"], c["five_hour"])
check("tuần chưa làm mới thì giữ", c["seven_day"]["pct"] == 60)

# 5. Codex app-server: camelCase, phân biệt bằng độ dài cửa sổ.
pl.ghi_codex({"rateLimits": {"primary": {"usedPercent": 41, "windowDurationMins": 300, "resetsAt": NOW + 3600},
                             "secondary": {"usedPercent": 12, "windowDurationMins": 10080, "resetsAt": NOW + 86400}}},
             now=NOW)
x = pl.doc(now=NOW)["codex"]
check("Codex: 5 giờ 41%", x["five_hour"]["pct"] == 41, x)
check("Codex: tuần 12%", x["seven_day"]["pct"] == 12, x)

# 6. Codex rollout: snake_case, dòng token_count cuối cùng thắng; dùng Codex ngoài Javis cũng thấy.
day = os.path.join(_TMP, "codex", "2026", "10", "25")
os.makedirs(day)
f = os.path.join(day, "rollout-2026-10-25T10-00-00-abc.jsonl")
dong = lambda pct: json.dumps({"timestamp": "2026-10-25T10:00:00Z", "type": "event_msg", "payload": {  # noqa: E731
    "type": "token_count", "info": None, "rate_limits": {
        "primary": {"used_percent": pct, "window_minutes": 300, "resets_at": NOW + 7200},
        "secondary": {"used_percent": 33.0, "window_minutes": 10080, "resets_at": NOW + 99999}}}})
with open(f, "w", encoding="utf-8") as fh:
    fh.write(dong(20.0) + "\n" + json.dumps({"type": "event_msg", "payload": {"type": "agent_message"}}) + "\n")
    fh.write(dong(91.0) + "\n")
os.utime(f, (NOW + 500, NOW + 500))
snap = pl.quet_codex(now=NOW + 600)
check("rollout: đọc dòng token_count cuối", snap and snap["five_hour"]["pct"] == 91.0, snap)
x = pl.doc(now=NOW + 600)["codex"]
check("rollout mới hơn bản lưu thì ghi đè", x["five_hour"]["pct"] == 91 and x["muc"] == "bad", x)
os.utime(f, (NOW - 999, NOW - 999))
pl._codex_cache.clear()
pl.ghi_codex({"rateLimits": {"primary": {"usedPercent": 5, "windowDurationMins": 300, "resetsAt": NOW + 3600}}},
             now=NOW + 700)
pl.quet_codex(now=NOW + 800)
check("rollout CŨ hơn bản lưu thì không đè", pl.doc(now=NOW + 800)["codex"]["five_hour"]["pct"] == 5)

# 7. Kho trống / file hỏng: không vỡ.
TRONG = {"claude": None, "codex": None, "grok": None, "agy": None}
os.remove(os.path.join(_TMP, "plan_limits.json"))
check("chưa có gì: cả bốn None", pl.doc(now=NOW) == TRONG)
with open(os.path.join(_TMP, "plan_limits.json"), "w") as fh:
    fh.write("{hong")
check("file hỏng: không vỡ", pl.doc(now=NOW) == TRONG)

# 8. Grok và Antigravity không báo số: chỉ đỏ khi CLI từ chối vì hết hạn mức (chủ repo 25/10).
check("lỗi quota của Antigravity được nhận", pl.la_het_han_muc("Error: RESOURCE_EXHAUSTED: quota exceeded for model"))
check("lỗi 429 của Grok được nhận", pl.la_het_han_muc("xAI API error 429 Too Many Requests"))
check("lỗi thường thì không", not pl.la_het_han_muc("connection reset by peer") and not pl.la_het_han_muc(""))
pl.ghi_het("grok-cli", 0, now=NOW)
g = pl.doc(now=NOW)["grok"]
check("Grok bị từ chối: đỏ, đầy vòng", g and g["muc"] == "bad" and g["max"] == 100 and g["het"]["at"] == NOW, g)
check("không có giờ làm mới thì đỏ 1 giờ", pl.doc(now=NOW + 3599)["grok"] is not None and pl.doc(now=NOW + 3601)["grok"] is None)
pl.ghi_het("antigravity-cli", NOW + 600, now=NOW)
check("có giờ làm mới thì đỏ tới đúng giờ đó", pl.doc(now=NOW + 599)["agy"]["het"]["reset"] == NOW + 600
      and pl.doc(now=NOW + 601)["agy"] is None)
pl.ghi_claude(RAW, now=NOW)
pl.ghi_het("claude-code", NOW + 900, now=NOW)
c = pl.doc(now=NOW)["claude"]
check("Claude bị từ chối: đỏ dù số cũ còn thấp, vẫn giữ hai thanh", c["muc"] == "bad" and c["five_hour"]["pct"] == 9, c)
check("hết hạn từ chối thì về màu theo số", pl.doc(now=NOW + 901)["claude"]["muc"] == "ok")
pl.ghi_het("gemini-cli", 0, now=NOW)
check("engine lạ không ghi gì", "gemini-cli" not in json.load(open(os.path.join(_TMP, "plan_limits.json"))))

# 9. Tên gói: chuẩn hoá, rỗng thì rỗng (không đoán).
check("max -> Max, pro -> Pro", pl.ten_goi("max") == "Max" and pl.ten_goi("pro") == "Pro")
check("ChatGPT plus -> Plus", pl.ten_goi("plus") == "Plus" and pl.ten_goi("chatgpt_plus") == "Plus")
check("tên có chữ hoa giữ nguyên", pl.ten_goi("SuperGrok") == "SuperGrok")
check("rỗng thì rỗng", pl.ten_goi("") == "" and pl.ten_goi(None) == "")
x = pl.tu_codex({"rateLimits": {"planType": "pro", "primary": {"usedPercent": 1, "windowDurationMins": 300}}})
check("Codex báo planType thì giữ lại", x["goi"] == "pro", x)

import hashlib  # noqa: E402
ev_pin = json.loads((ROOT / "docs/superpowers/evidence/2026-10-25-m5-native-qualification-cli310.json").read_text())
check("CANARY: claude_sdk_engine.py giữ nguyên đúng bản đã kiểm định native",
      hashlib.sha256((ROOT / "server/claude_sdk_engine.py").read_bytes()).hexdigest()
      == ev_pin["source_hashes"]["claude_sdk_engine.py"])
_cli = (ROOT / "server" / "claude_cli.py").read_text(encoding="utf-8")
_eng = _cli[_cli.find("def claude_engine("):]
check("móc gắn lúc tạo engine Claude (không phải lúc nạp main: khởi động phải nhẹ)",
      "plan_limits.cai_vao_claude_sdk()" in _eng[:_eng.find("return ClaudeSDK(")]
      and "cai_vao_claude_sdk" not in (ROOT / "server" / "main.py").read_text(encoding="utf-8"))

# 8. Route: Claude chạy API key thì không có gói, không hiện vòng.
src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
i = src.rfind('@app.get("/plan-limits")')
check("route /plan-limits đăng ký sau star_nudge", i > src.rfind("star_nudge_routes.register"))
check("Claude chỉ tính là gói khi không chạy bằng API key", "not claude_auth.env_cho_cli()" in src[i:])
than = src[i:i + 2500]
check("Grok chạy API key xAI thì không có gói", '"grok-cli": grok_k.get("method") != "xai-api-key"' in than)
check("tên gói chỉ hỏi khi mở bảng (goi=1)", "if goi:" in than and "claude_auth_status" in than)
cli = (ROOT / "server" / "claude_cli.py").read_text(encoding="utf-8")
check("tên gói Claude lấy riêng subscriptionType, không lẫn authMethod", '"goi": d.get("subscriptionType", "") or ""' in cli)
lf = src[src.find("def _limit_frame("):src.find("def _limit_frame(") + 2600]
check("lượt bị từ chối vì hết hạn mức thì vòng tròn đỏ", "plan_limits.ghi_het(engine_hint" in lf
      and 'engine_hint in ("grok-cli", "antigravity-cli") and plan_limits.la_het_han_muc(raw)' in lf)

if fails:
    raise SystemExit(f"{len(fails)} FAIL")
print("OK")
