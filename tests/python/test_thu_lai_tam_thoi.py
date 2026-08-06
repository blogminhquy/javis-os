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
engine._jittered_backoff = lambda attempt, **kw: (_da_cho.append(attempt), 0.001)[1]


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
main.claude_models.oauth_token = lambda: "tok-claude"

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

print(("\nFAILED: " + ", ".join(_fails)) if _fails else "\nAll passed")
sys.exit(1 if _fails else 0)
