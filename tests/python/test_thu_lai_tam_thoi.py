"""Nhà cung cấp gãy TẠM THỜI thì thử lại, đừng giết cả lượt trả lời.

    python tests/run.py thu_lai_tam_thoi      (KHÔNG mạng)

Chủ repo gửi ảnh chụp một con bot chuyên trách đang trực: khách nhắn "Tao đang có mấy khách",
bot trả lời "Em đang gặp trục trặc kỹ thuật, anh chị nhắn lại giúp em sau ít phút ạ", và người
trực bị gọi dậy kèm lý do:

    ⚠ Anthropic 429: {"type":"error","error":{"type":"rate_limit_error","message":"Error"}}

429 là lỗi TẠM THỜI. Việc đúng là chờ một nhịp rồi hỏi lại, không phải bỏ cuộc, xin lỗi khách
và đánh thức người thật.

Chuyện đã sai ở đâu: `engine.py` có sẵn ĐỦ bộ đồ nghề để thử lại từ lâu - `_RETRY_STATUS`,
`_is_transient_body`, `_parse_retry_after`, `_jittered_backoff` - nhưng chỉ `openrouter_stream`
dùng chúng. Bảy đường gọi model còn lại và cả bốn vòng tool đều bỏ cuộc ngay ở lần gãy đầu
tiên. Không ai thấy vì trên máy sạch thì nhà cung cấp không 429 bao giờ.

File này canh ba tầng, vì sửa hụt một tầng là lỗi quay lại nguyên vẹn:

1. **Dấu đặt tại nguồn.** Chỉ chỗ gọi HTTP mới còn status thật, body thật và header
   `Retry-After`. Lên tới tầng trên thì tất cả đã thành một chuỗi chữ.
2. **Thử lại có ĐIỀU KIỆN.** Đã nhả chữ ra ngoài thì thôi (câu trả lời sẽ hiện hai lần), đã
   chạy tool thì càng thôi (lượt đó đã gửi tin, đã ghi file, đã đặt lịch).
3. **Cả tám bộ não.** Sửa cho Anthropic rồi bỏ bảy đường kia là đúng kiểu hỏng đang sửa.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import asyncio
import os
import sys
import tempfile

_STATE = tempfile.mkdtemp(prefix="javis-thulai-")
os.environ["JAVIS_STATE_DIR"] = _STATE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx  # noqa: E402
import engine  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# Thử lại thật thì mỗi lần chờ 1-3 giây. Test không cần chờ, chỉ cần biết nó CÓ chờ.
_da_cho = []
engine._jittered_backoff = lambda attempt, **kw: (_da_cho.append((attempt, kw)), 0.001)[1]


def chay(gen):
    async def _thu():
        return [ev async for ev in gen()]
    return asyncio.run(_thu())


# Đúng body Anthropic đã trả trong ảnh chụp của chủ repo. Giữ nguyên văn: `limit_learner` đọc
# body để rút hạn mức, và body này KHÔNG có con số nào nên nó phải trả None - nếu nó rút ra
# được một "fact" thì lượt này bị coi là hết quota thật và không được thử lại.
BODY_429 = ('{"type":"error","error":{"type":"rate_limit_error","message":"Error"},'
            '"request_id":"req_011CdkmsAc4h815zVMMP33vs"}')


# ============================================================
# 1. Dấu "tạm thời" đặt tại nguồn
# ============================================================
import limit_learner  # noqa: E402

check("429 kiểu Anthropic không rút ra hạn mức nào -> phải coi là tạm thời",
      limit_learner.parse_limit_error(429, BODY_429) is None)

_ev = engine.ev_loi_http("Anthropic", 429, BODY_429)
check("429 -> đánh dấu tạm thời", _ev.get("tam_thoi") is True)
check("và vẫn giữ nguyên câu lỗi gốc cho người đọc",
      "Anthropic 429" in _ev["content"] and "rate_limit_error" in _ev["content"])

for _s in (408, 429, 502, 503, 504, 529):
    check(f"{_s} là lỗi tạm thời", engine.ev_loi_http("X", _s, "bận").get("tam_thoi") is True)
# Sai token, sai model, hết tiền: thử lại bao nhiêu lần cũng y hệt, chỉ tốn thêm lượt gọi.
for _s in (400, 401, 403, 404, 422):
    check(f"{_s} KHÔNG phải lỗi tạm thời",
          engine.ev_loi_http("X", _s, "sai khoá").get("tam_thoi") is None)

check("status không nằm trong danh sách nhưng body kêu quá tải -> vẫn tạm thời",
      engine.ev_loi_http("X", 400, "server is Overloaded, try again").get("tam_thoi") is True)

# Nhà cung cấp vừa nói hạn mức THẬT của tài khoản. Đó không phải sự cố chớp nhoáng, và thử lại
# y nguyên chỉ để nhận lại đúng lỗi đó. Phải co payload lại hoặc chờ cửa sổ trượt qua trước.
class _Fact:
    kind, limit, requested, remedy, raw = "context", 200000, 300000, "shrink", ""


check("đã đọc ra hạn mức thật -> KHÔNG thử lại",
      engine.ev_loi_http("X", 429, "quá dài", fact=_Fact()).get("tam_thoi") is None)

_ev = engine.ev_loi_http("X", 429, "bận", headers={"retry-after": "7"})
check("có header Retry-After thì nghe theo nhà cung cấp", _ev.get("cho") == 7.0)

check("lỗi mạng -> tạm thời",
      engine.ev_loi_exc("X lỗi", httpx.ReadTimeout("quá lâu")).get("tam_thoi") is True)
check("lỗi lập trình -> KHÔNG tạm thời",
      engine.ev_loi_exc("X lỗi", ValueError("thiếu khoá")).get("tam_thoi") is None)


# ============================================================
# 2. Vòng thử lại: khi nào chạy lại, khi nào chịu
# ============================================================
def lam_stream(kich_ban, dem):
    """kich_ban = danh sách các lượt, mỗi lượt là danh sách sự kiện sẽ phát ra."""
    def _tao():
        i = min(len(dem), len(kich_ban) - 1)
        dem.append(1)

        async def _gen():
            for ev in kich_ban[i]:
                yield ev
        return _gen()
    return _tao


LOI_429 = engine.ev_loi_http("Anthropic", 429, BODY_429)
TRA_LOI = [{"type": "text", "content": "Dạ bên em còn hàng ạ."}, {"type": "usage", "input": 9, "output": 4}]

_dem = []
_evs = chay(lambda: engine.thu_lai_khi_tam_thoi(
    lam_stream([[LOI_429], [LOI_429], TRA_LOI], _dem), nhan="t"))
check("gãy tạm thời hai lần rồi được -> vẫn trả lời", any(e["type"] == "text" for e in _evs))
check("và không để lại lỗi nào cho tầng trên", not any(e["type"] == "error" for e in _evs))
check("đã gọi đủ ba lượt", len(_dem) == 3)

_dem = []
_evs = chay(lambda: engine.thu_lai_khi_tam_thoi(lam_stream([[LOI_429]], _dem), nhan="t"))
_loi = [e for e in _evs if e["type"] == "error"]
check("hỏng cả ba lượt -> báo lỗi ĐÚNG MỘT lần", len(_loi) == 1 and len(_dem) == 3)
check("lỗi cuối giữ nguyên câu gốc", "Anthropic 429" in _loi[0]["content"])
check("và nói rõ đã thử lại mấy lần", "đã thử lại 3 lần" in _loi[0]["content"])
# Gỡ dấu ở lượt cuối là thứ giữ cho bọc chồng hai lớp không nở thành chín lần gọi model, và
# cũng là thứ giữ `openrouter_stream` (vốn tự thử lại bên trong) khỏi bị thử thêm một tầng.
check("CANARY: lỗi cuối KHÔNG còn mời chạy lại", _loi[0].get("tam_thoi") is None)

_dem = []
_evs = chay(lambda: engine.thu_lai_khi_tam_thoi(
    lambda: engine.thu_lai_khi_tam_thoi(lam_stream([[LOI_429]], _dem), nhan="trong"),
    nhan="ngoài"))
check("bọc chồng hai lớp KHÔNG nở thành chín lượt gọi model", len(_dem) == 3)
check("và vẫn chỉ một câu lỗi đi ra",
      len([e for e in _evs if e["type"] == "error"]) == 1)

# Điều kiện 1: đã nhả chữ ra ngoài rồi thì thôi. Chạy lại là người ta đọc câu trả lời hai lần.
_dem = []
_evs = chay(lambda: engine.thu_lai_khi_tam_thoi(
    lam_stream([[{"type": "text", "content": "Dạ bên em"}, LOI_429], TRA_LOI], _dem), nhan="t"))
check("đã nhả chữ rồi thì KHÔNG chạy lại", len(_dem) == 1)
check("và lỗi vẫn tới được tầng trên", any(e["type"] == "error" for e in _evs))

# Điều kiện 2, quan trọng hơn hẳn: vòng tool có thể đã gửi tin, đã ghi file, đã đặt lịch. Chạy
# lại cả vòng là làm lại từ đầu những việc đó.
_dem = []
_evs = chay(lambda: engine.thu_lai_khi_tam_thoi(
    lam_stream([[{"type": "tool_call", "name": "zalo_send_message"}, LOI_429], TRA_LOI], _dem),
    nhan="t"))
check("CANARY: đã chạy tool rồi thì TUYỆT ĐỐI không chạy lại", len(_dem) == 1)

# Nhà cung cấp bảo chờ lâu hơn ngưỡng người ta chịu ngồi im thì báo ngay, đừng để màn hình
# đứng yên nửa phút rồi mới nói.
_dem = []
_lau = engine.ev_loi_http("X", 429, "bận", headers={"retry-after": str(engine._WINDOW_WAIT_MAX + 30)})
chay(lambda: engine.thu_lai_khi_tam_thoi(lam_stream([[_lau]], _dem), nhan="t"))
check("Retry-After dài quá ngưỡng -> báo ngay chứ không ngồi chờ", len(_dem) == 1)

_dem = []
_evs = chay(lambda: engine.thu_lai_khi_tam_thoi(
    lam_stream([[{"type": "meta", "model": "opus"}, LOI_429],
                [{"type": "meta", "model": "opus"}] + TRA_LOI], _dem), nhan="t"))
check("meta chỉ phát MỘT lần dù chạy lại", len([e for e in _evs if e["type"] == "meta"]) == 1)

# Lỗi KHÔNG mang dấu thì đi thẳng, không ai được tự đoán lại bằng cách dò chữ trong câu lỗi.
_dem = []
chay(lambda: engine.thu_lai_khi_tam_thoi(
    lam_stream([[{"type": "error", "content": "Anthropic 429: bận"}]], _dem), nhan="t"))
check("lỗi không mang dấu -> không chạy lại", len(_dem) == 1)


# ============================================================
# 3. Cả tám bộ não đều được thử lại, không con nào bị bỏ lại
# ============================================================
import main  # noqa: E402

main.openai_oauth.valid_creds = lambda: {"access_token": "tok", "account_id": "acc"}

_lan = {}


def _lam_engine(ten):
    def _fn(*a, **kw):
        _lan[ten] = _lan.get(ten, 0) + 1

        async def _gen():
            if _lan[ten] == 1:
                yield engine.ev_loi_http("X", 429, BODY_429)
                return
            yield {"type": "text", "content": "xong"}
        return _gen()
    return _fn


for _ten in ("openrouter_stream", "openai_stream", "gemini_stream", "groq_stream",
             "ollama_stream", "openai_responses_stream", "anthropic_stream"):
    setattr(main.engine, _ten, _lam_engine(_ten))
# Gói Claude Code KHÔNG đi qua engine.* nữa: từ 0.26.17 nó chạy binary `claude` (đường mượn
# token OAuth đã gỡ, xem claude_auth.py). Nó vẫn phải nằm TRONG vòng thử lại - đó chính là
# điều canary này canh - nên chỉ đổi chỗ cắm giả, không nới điều kiện.
main._claude_sub_stream = _lam_engine("_claude_sub_stream")
# Gemini CLI (bộ não thứ 9) cùng cảnh: chạy binary `gemini` chứ không qua engine.*, nhưng vẫn
# phải nằm trong vòng thử lại như mọi bộ não khác.
main._gemini_sub_stream = _lam_engine("_gemini_sub_stream")
# Antigravity CLI (bộ não thứ 10) cùng cảnh: chạy binary `agy`, không qua engine.*.
main._antigravity_sub_stream = _lam_engine("_antigravity_sub_stream")
# Grok Build CLI (bộ não thứ 11) cùng cảnh: chạy binary `grok`, không qua engine.*.
main._grok_sub_stream = _lam_engine("_grok_sub_stream")

_bo_sot = []
for _p in [d["id"] for d in main.PROVIDER_DEFS]:
    _lan.clear()
    _evs = chay(lambda p=_p: main._api_stream(p, "k", "m", [{"role": "user", "content": "hi"}]))
    if not any(e["type"] == "text" for e in _evs) or sum(_lan.values()) < 2:
        _bo_sot.append(_p)
check(f"CANARY: cả {len(main.PROVIDER_DEFS)} bộ não đều tự thử lại sau 429", _bo_sot == [])
if _bo_sot:
    print("     bị bỏ lại: " + ", ".join(_bo_sot))


# ============================================================
# 4. Đúng ca của chủ repo: bot chuyên trách gặp 429 giữa ca trực
# ============================================================
# Đây là mục đo THẲNG cái ảnh chụp: một cú 429 chớp nhoáng không được phép biến thành lời xin
# lỗi kỹ thuật gửi cho người đang nhắn, và càng không được đánh thức người trực.
BOT = {"id": "bot_x", "name": "CRM - Coaching", "brain": "brain-bot", "muc_quyen": "suggest",
       "agent": {"brain": "brain-bot", "slug": "coach"},
       "_tai_lieu": {"co": True, "khoi": "### Lịch\n\nHọc phí 5 triệu", "nguon": ["gia.md"]}}

_dem_bot = []


def _anthropic_429_roi_on(*a, **kw):
    _dem_bot.append(1)

    async def _gen():
        if len(_dem_bot) == 1:
            yield engine.ev_loi_http("Anthropic", 429, BODY_429)
            return
        yield {"type": "text", "content": "Dạ lớp còn chỗ ạ."}
        yield {"type": "usage", "input": 30, "output": 9}
    return _gen()


main.engine.anthropic_stream = _anthropic_429_roi_on

_r = asyncio.run(main._tg_answer_engine(
    "còn chỗ không em", {"chat_id": "1", "chat_type": "private"}, None,
    chat_id="1", sess={"last": None, "sent": set()}, brain="brain-bot", mcfg={},
    prov="anthropic-api", kind="api", api_key="k", api_model="opus", bot=BOT))
check("CANARY: bot gặp 429 một nhịp -> vẫn trả lời khách bình thường",
      isinstance(_r, dict) and "còn chỗ" in (_r.get("text") or ""))
check("và không trả về chuỗi lỗi (chuỗi lỗi là thứ gọi người trực dậy)",
      not isinstance(_r, str))
check("đã thật sự gọi lại lần hai", len(_dem_bot) == 2)

# Hỏng thật thì vẫn phải báo hỏng - đây không phải cái cớ để nuốt lỗi.
_dem_bot.clear()


def _anthropic_429_mai(*a, **kw):
    _dem_bot.append(1)

    async def _gen():
        yield engine.ev_loi_http("Anthropic", 429, BODY_429)
    return _gen()


main.engine.anthropic_stream = _anthropic_429_mai
_r = asyncio.run(main._tg_answer_engine(
    "còn chỗ không em", {"chat_id": "1", "chat_type": "private"}, None,
    chat_id="1", sess={"last": None, "sent": set()}, brain="brain-bot", mcfg={},
    prov="anthropic-api", kind="api", api_key="k", api_model="opus", bot=BOT))
check("hết đường thì vẫn báo lỗi cho người trực", isinstance(_r, str) and "429" in _r)
check("và nói luôn là đã thử lại rồi", isinstance(_r, str) and "đã thử lại" in _r)

check("KHÔNG có em dash trong câu lỗi trả ra", "—" not in (_r if isinstance(_r, str) else ""))


# ============================================================
# 5. Chờ ĐÚNG NHỊP: 429 không phải một cú vấp mạng
# ============================================================
# Chủ repo gửi lại đúng cái thẻ bot đó vào 2026-08-09, lần này kèm dòng "(đã thử lại 3 lần)".
# Nghĩa là máy thử lại đủ ba lần rồi vẫn ăn 429. Nhìn con số thì thấy ngay vì sao: nhịp chờ
# mặc định là 1s, 2s, 4s, nên cả ba lần hỏi lại gói gọn trong bảy giây, trong khi cửa sổ hạn
# mức của Anthropic tính bằng phút. Ba lần hỏi trong bảy giây chỉ là ăn đúng cú 429 đó ba lần.
from datetime import datetime, timedelta, timezone  # noqa: E402


def _moc(sau_bao_giay):
    return (datetime.now(timezone.utc) + timedelta(seconds=sau_bao_giay)) \
        .strftime("%Y-%m-%dT%H:%M:%SZ")


# 5a. Anthropic không phải lúc nào cũng gửi Retry-After, nhưng LUÔN gửi mốc cửa sổ mở lại.
# Bỏ qua mấy header đó là tự bịt mắt rồi đoán, mà đoán 1 giây cho cửa sổ tính bằng phút.
_h = {"anthropic-ratelimit-requests-reset": _moc(40),
      "anthropic-ratelimit-tokens-reset": _moc(90)}
_cho = engine._parse_retry_after(_h)
check("thiếu Retry-After thì đọc mốc reset của Anthropic", _cho is not None)
check("và lấy cửa sổ mở SỚM NHẤT (chờ hụt còn lượt sau, chờ dư là ngồi im vô ích)",
      _cho is not None and 30 < _cho <= 45)

check("Retry-After vẫn thắng khi có cả hai",
      engine._parse_retry_after(dict(_h, **{"retry-after": "3"})) == 3.0)
check("mốc đã trôi qua thì bỏ (đồng hồ hai máy lệch nhau là thường)",
      engine._parse_retry_after({"anthropic-ratelimit-tokens-reset": _moc(-30)}) is None)
check("mốc không đọc được thì bỏ, không nổ",
      engine._parse_retry_after({"anthropic-ratelimit-tokens-reset": "hôm qua"}) is None)
check("không có header nào thì vẫn None như cũ", engine._parse_retry_after({}) is None)

# 5b. Không nhà cung cấp nào nói gì thì tự đoán, nhưng đoán theo LOẠI lỗi.
check("429 mang theo status thật để tầng trên chọn nhịp",
      engine.ev_loi_http("X", 429, "bận").get("ma") == 429)

_da_cho.clear()
chay(lambda: engine.thu_lai_khi_tam_thoi(lam_stream([[LOI_429]], []), nhan="t"))
_base_429 = [kw.get("base") for _, kw in _da_cho]
check("429 chờ theo nhịp hạn mức, không phải nhịp vấp mạng",
      _base_429 and all(b and b >= 5.0 for b in _base_429))

_da_cho.clear()
_loi502 = engine.ev_loi_http("X", 502, "bận")
chay(lambda: engine.thu_lai_khi_tam_thoi(lam_stream([[_loi502]], []), nhan="t"))
check("5xx giữ nhịp nhanh như cũ (một giây sau thường đã ngon)",
      _da_cho and all(not kw.get("base") for _, kw in _da_cho))

# 5c. Câu cuối đi thẳng lên thẻ bot của CHỦ. Một cục JSON không nói được phải làm gì tiếp.
_cuoi = chay(lambda: engine.thu_lai_khi_tam_thoi(lam_stream([[LOI_429]], []), nhan="t"))[-1]
check("hết đường thì nói rõ đây là hạn mức, không chỉ dán JSON",
      "hạn mức" in _cuoi["content"])
check("và chỉ luôn đường đi tiếp", "Models" in _cuoi["content"])
check("vẫn giữ nguyên lỗi gốc để còn tra được",
      "Anthropic 429" in _cuoi["content"] and "rate_limit_error" in _cuoi["content"])
check("không em dash", "—" not in _cuoi["content"])

# Nhà cung cấp bảo chờ lâu hơn ngưỡng ngồi im được thì nói luôn còn bao lâu, thay vì bỏ lửng.
_lau429 = engine.ev_loi_http("X", 429, "bận",
                             headers={"retry-after": str(engine._WINDOW_WAIT_MAX + 40)})
_c2 = chay(lambda: engine.thu_lai_khi_tam_thoi(lam_stream([[_lau429]], []), nhan="t"))[-1]
check("chờ quá lâu thì báo ngay VÀ nói còn bao lâu", "cửa sổ mở lại sau" in _c2["content"])

print(("\nFAILED: " + ", ".join(_fails)) if _fails else "\nAll passed")
sys.exit(1 if _fails else 0)
