"""Bot chuyên trách: ba mức quyền, và cái giá của mỗi mức.

    python tests/run.py chatbot_muc_quyen      (KHÔNG mạng)

Chủ repo mở phạm vi ngày 2026-08-05: "ở chức năng tạo bot đang là chỉ đọc, anh muốn thêm chức
năng được ghi và toàn quyền. Vì cơ bản anh vẫn muốn có thể thực hiện nhiều task, nhưng em thêm
phần thông báo cho anh để hiểu rõ nguy cơ khi sử dụng."

Nới quyền cho một con bot đang nói chuyện với NGƯỜI LẠ là thay đổi nguy hiểm nhất tính năng
này từng có, nên file này canh đúng bốn chỗ mà một lần sửa ẩu là mở toang:

1. **Fail-closed.** Chỉ đúng hai chữ đã khai mới mở tool. Bản ghi cũ thiếu khoá, file sửa tay
   gõ sai, giá trị None - tất cả rơi về Chỉ đọc. Viết ngược lại ("khác suggest thì mở tool")
   là một lỗi chính tả trong chatbots.json cũng đủ cấp tool cho bot đang chat với khách.

2. **Nâng mức phải CÓ Ý THỨC.** Cùng lý do "bot mới luôn tắt": từ lúc bấm xong, mọi câu khách
   nhắn đều chạy ở mức mới. Rào nằm ở KHO chứ không chỉ ở route, vì route chỉ là một trong
   nhiều đường vào.

3. **Mức đi thẳng xuống hub, đúng brain của bot.** `muc_quyen` thành `mode` của hub mà không
   qua bảng dịch nào, và `vault_root` là brain CỦA BOT. Sai một trong hai là hoặc cấp nhầm
   quyền, hoặc mở toang brain của chủ.

4. **Cả tám bộ não đều có tool.** Lời hứa gốc của Javis: đổi bộ não thì năng lực không đổi.
   Cấp tool cho sáu engine API rồi bỏ hai gói thuê bao lại là kiểu hỏng im lặng tệ nhất - chủ
   đặt Toàn quyền, bot vẫn lễ phép trả lời, và không làm gì cả.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import asyncio
import os
import sys
import tempfile

_STATE = tempfile.mkdtemp(prefix="javis-mucquyen-")
os.environ["JAVIS_STATE_DIR"] = _STATE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_store  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# CHỐT CHẶN - kho ghi ra STATE_DIR thật thì test này đè lên danh sách bot THẬT của người dùng.
if _STATE not in str(chatbot_store.STORE_PATH):
    print(f"FAIL kho không nằm trong thư mục tạm: {chatbot_store.STORE_PATH}. DỪNG.")
    sys.exit(1)


# ============================================================
# 1. Kho: mặc định Chỉ đọc, nâng mức thì phải xác nhận
# ============================================================
bid, why = chatbot_store.create_bot({"name": "Bot mặc định", "agent_slug": "cskh",
                                     "brain": "shop", "token": "1:AA"})
check("tạo bot không nói gì về quyền -> Chỉ đọc", bool(bid) and
      chatbot_store.get_bot(bid)["muc_quyen"] == "suggest")

bad, why = chatbot_store.create_bot({"name": "Bot ghi", "agent_slug": "cskh", "brain": "shop",
                                     "muc_quyen": "auto"})
check("tạo bot mức Được ghi mà chưa xác nhận -> TỪ CHỐI", bad is None and why)
bad, why = chatbot_store.create_bot({"name": "Bot full", "agent_slug": "cskh", "brain": "shop",
                                     "muc_quyen": "full"})
check("tạo bot mức Toàn quyền mà chưa xác nhận -> TỪ CHỐI", bad is None and why)

bid2, _ = chatbot_store.create_bot({"name": "Bot ghi", "agent_slug": "cskh", "brain": "shop",
                                    "muc_quyen": "auto", "xac_nhan_rui_ro": True,
                                    "token": "2:BB"})
check("có xác nhận thì tạo được mức Được ghi",
      bool(bid2) and chatbot_store.get_bot(bid2)["muc_quyen"] == "auto")

# Đây mới là đường hay đi hơn: bot sống nhiều tháng ở Chỉ đọc rồi một hôm được nâng lên. Thiếu
# rào ở update thì cái gate lúc tạo chỉ là trang trí.
ok, why = chatbot_store.update_bot(bid, {"muc_quyen": "full"})
check("NÂNG mức qua bản vá mà chưa xác nhận -> TỪ CHỐI", ok is False and why)
check("và bot vẫn ở mức cũ", chatbot_store.get_bot(bid)["muc_quyen"] == "suggest")

ok, _ = chatbot_store.update_bot(bid, {"muc_quyen": "full", "xac_nhan_rui_ro": True})
check("có xác nhận thì nâng được", ok and chatbot_store.get_bot(bid)["muc_quyen"] == "full")

# HẠ mức thì không đòi gì cả: hạ quyền luôn an toàn, bắt xác nhận chỉ làm chủ ngại bấm đúng
# lúc họ đang muốn dập một sự cố.
ok, _ = chatbot_store.update_bot(bid, {"muc_quyen": "suggest"})
check("HẠ mức xuống Chỉ đọc thì không đòi xác nhận",
      ok and chatbot_store.get_bot(bid)["muc_quyen"] == "suggest")

# Giá trị lạ GIỮ NGUYÊN mức cũ chứ không rơi về mặc định: bot đang Toàn quyền mà một bản vá gõ
# sai chữ lại lặng lẽ hạ nó xuống thì chủ tưởng bot vẫn làm việc, còn nó thì từ chối mọi tool.
chatbot_store.update_bot(bid2, {"muc_quyen": "toan-quyen-luon"})
check("mức lạ bị bỏ qua, giữ nguyên mức cũ",
      chatbot_store.get_bot(bid2)["muc_quyen"] == "auto")

# Bản ghi tạo trước 0.22.0 không có khoá này. Thiếu nó mà đọc bằng .get() thì ra None, và None
# rơi vào nhánh mặc định của NGƯỜI GỌI chứ không phải nhánh mình chọn.
_raw = chatbot_store._load()
for b in _raw["bots"]:
    b.pop("muc_quyen", None)
chatbot_store._save(_raw)
check("bản ghi CŨ (chưa có khoá) đọc ra vẫn là Chỉ đọc",
      all(x["muc_quyen"] == "suggest" for x in chatbot_store.list_bots()))
chatbot_store.update_bot(bid2, {"muc_quyen": "auto", "xac_nhan_rui_ro": True})


# ============================================================
# 2. Cảnh báo: nói ra cái MẤT ĐƯỢC, không phải "hãy cẩn thận"
# ============================================================
check("mức Chỉ đọc không có cảnh báo nào (nó không lấy đi gì)",
      chatbot_store.canh_bao_muc("suggest") == [])
for m in ("auto", "full"):
    cb = chatbot_store.canh_bao_muc(m)
    check(f"mức '{m}' có danh sách cảnh báo", len(cb) >= 3)
    check(f"mức '{m}' có nhãn tiếng Việt", bool(chatbot_store.MUC_NHAN.get(m)))

_full = " ".join(chatbot_store.canh_bao_muc("full")).lower()
check("cảnh báo Toàn quyền kể ra loại thao tác mất được",
      "gửi đi" in _full and "thanh toán" in _full and "xoá" in _full)
check("cảnh báo Toàn quyền nói rõ ai là người điều khiển", "người nhắn cho nó" in _full)
check("cảnh báo Toàn quyền nói rõ không hoàn tác được", "hoàn tác" in _full)

_auto = " ".join(chatbot_store.canh_bao_muc("auto")).lower()
check("cảnh báo Được ghi nói rõ vẫn CHẶN nhóm thao tác ra ngoài",
      "không gửi đi" in _auto and "không thanh toán" in _auto)

# CANARY - cảnh báo phải tả theo LOẠI THAO TÁC, không kể tên việc của một ngành.
#
# Bản đầu viết "tạo đơn, tiêu tiền quảng cáo, đăng bài": đọc lọt tai với người bán hàng, vô
# nghĩa với người dùng Javis để quản lý dự án, chăm sức khoẻ hay dạy học. Tệ hơn: người đó đọc
# xong tưởng cảnh báo không áp cho mình, rồi bật Toàn quyền vì nghĩ mình không có gì để mất.
# Chủ repo bác đúng chỗ này (2026-08-05): "nó cá nhân hóa với anh quá".
for nganh in ("đơn hàng", "tạo đơn", "quảng cáo", "khách hàng", "cửa hàng", "bán hàng",
              "bảng giá", "POS", "shop"):
    check(f"CANARY: cảnh báo KHÔNG kể tên việc của một ngành - '{nganh}'",
          all(nganh.lower() not in " ".join(chatbot_store.canh_bao_muc(m)).lower()
              for m in chatbot_store.MUC_QUYEN))
# Hai rào không đổi theo mức. Không nói ra thì chủ ngại nâng mức một cách vô cớ; nói sai thì
# chủ tin vào một rào không tồn tại. Cả hai mức đều phải nhắc.
for m in ("auto", "full"):
    t = " ".join(chatbot_store.canh_bao_muc(m)).lower()
    check(f"mức '{m}' nhắc hai rào giữ nguyên (brain khác + lệnh máy)",
          "brain khác" in t and "lệnh máy" in t)

check("KHÔNG có em dash trong cảnh báo",
      all("—" not in s for m in chatbot_store.MUC_QUYEN
          for s in chatbot_store.canh_bao_muc(m)))


# ============================================================
# 3. Lượt chạy: rẽ đúng đường, và fail-closed
# ============================================================
import main  # noqa: E402
import mcp_hub  # noqa: E402

BOT = {"id": "bot_x", "name": "Bot", "brain": "brain-bot",
       "agent": {"brain": "brain", "slug": "coach"},
       "_tai_lieu": {"co": True, "khoi": "### Giá\n\n185.000đ", "nguon": ["gia.md"]}}

_da_goi = {}


async def _discover_gia(mode="full", vault_root=None, **kw):
    _da_goi["mode"] = mode
    _da_goi["vault_root"] = str(vault_root or "")
    return ([{"fn": "javis_doc_file", "server": "javis", "name": "javis_doc_file",
              "schema": {"type": "object", "properties": {}}}],
            {"javis_doc_file": {"call": None}})


mcp_hub.discover_all = _discover_gia

_goi = []


def _stream_khong_tool(prov, key, model, messages, reasoning="off"):
    _goi.append({"prov": prov, "co_tool": False, "messages": [dict(m) for m in messages]})

    async def _gen():
        yield {"type": "text", "content": "Chào anh chị."}
        yield {"type": "usage", "input": 10, "output": 5}
    return _gen()


def _lam_stream_co_tool(prov):
    def _fn(*a, **kw):
        _goi.append({"prov": prov, "co_tool": True})

        async def _gen():
            yield {"type": "tool_call", "name": "javis_doc_file"}
            yield {"type": "text", "content": "Em làm xong rồi ạ."}
            yield {"type": "usage", "input": 20, "output": 7}
        return _gen()
    return _fn


main._api_stream = _stream_khong_tool
for _ten in ("openrouter_chat_with_mcp", "openai_chat_with_mcp", "gemini_chat_with_mcp",
             "groq_chat_with_mcp", "ollama_chat_with_mcp", "anthropic_chat_with_mcp",
             "responses_with_mcp"):
    setattr(main.engine, _ten, _lam_stream_co_tool(_ten))
# Gói ChatGPT: đường có tool đọc creds OAuth. Không giả thì nó rơi vào nhánh "chưa đăng nhập".
main.openai_oauth.valid_creds = lambda: {"access_token": "tok", "account_id": "acc"}
main.claude_models.oauth_token = lambda: "tok-claude"


def chay(prov, kind, bot, sess=None, hoi="giá bao nhiêu"):
    return asyncio.run(main._tg_answer_engine(
        hoi, {"chat_id": "1", "chat_type": "private"}, None,
        chat_id="1", sess=sess if sess is not None else {"last": None, "sent": set()},
        brain="brain-bot", mcfg={}, prov=prov, kind=kind, api_key="k", api_model="m", bot=bot))


_goi.clear()
r = chay("openrouter", "api", {**BOT, "muc_quyen": "suggest"})
check("mức Chỉ đọc -> đi đường KHÔNG tool",
      isinstance(r, dict) and _goi and _goi[-1]["co_tool"] is False)

# Fail-closed, và đây là mục quan trọng nhất cả file: mọi giá trị KHÔNG nằm trong danh sách đã
# khai đều phải rơi về đường không tool, không phải "khác suggest thì mở".
for xau in (None, "", "sugest", "toan_quyen", "FULL ", "auto ", 1, True, "readonly"):
    _goi.clear()
    chay("openrouter", "api", {**BOT, "muc_quyen": xau})
    mo = bool(_goi) and _goi[-1]["co_tool"]
    # "FULL " và "auto " có khoảng trắng thừa: mã chuẩn hoá bằng strip().lower() nên chúng HỢP
    # LỆ và mở tool. Giữ chúng trong danh sách để ai đó bỏ strip() thì test đỏ ngay.
    nen_mo = str(xau).strip().lower() in chatbot_store.MUC_NANG
    check(f"mức lạ {xau!r} -> {'có' if nen_mo else 'KHÔNG'} tool", mo is nen_mo)

# Bản ghi thiếu hẳn khoá (bot tạo trước 0.22.0, đọc thẳng từ file cũ chứ không qua _public).
_goi.clear()
_khong_khoa = {k: v for k, v in BOT.items()}
chay("openrouter", "api", _khong_khoa)
check("bản ghi THIẾU HẲN khoá muc_quyen -> không tool", _goi[-1]["co_tool"] is False)


# ============================================================
# 4. Mức đi thẳng xuống hub, cắm vào ĐÚNG brain của bot
# ============================================================
for m in ("auto", "full"):
    _goi.clear()
    _da_goi.clear()
    r = chay("openrouter", "api", {**BOT, "muc_quyen": m})
    check(f"mức '{m}' -> đi đường CÓ tool", isinstance(r, dict) and _goi[-1]["co_tool"] is True)
    check(f"mức '{m}' truyền THẲNG xuống hub, không qua bảng dịch", _da_goi.get("mode") == m)
    check(f"mức '{m}' cắm hub vào brain của BOT",
          _da_goi.get("vault_root") == str(main._brain_root("brain-bot")))


# ============================================================
# 5. Cả tám bộ não đều được cấp tool - không con nào bị bỏ lại
# ============================================================
# Đây là lời hứa gốc của Javis, và là chỗ dễ hụt nhất: `_api_stream_mcp` chỉ phục vụ sáu engine
# API, nên copy nguyên nó sang là hai gói thuê bao lặng lẽ chạy không tool. Chủ đặt Toàn quyền,
# bot vẫn lễ phép trả lời, và không làm gì cả.
_thieu = []
for prov, kind in [(d["id"], d["kind"]) for d in main.PROVIDER_DEFS]:
    _goi.clear()
    r = chay(prov, kind, {**BOT, "muc_quyen": "full"},
             sess={"last": None, "sent": set()})
    if not (_goi and _goi[-1]["co_tool"] and isinstance(r, dict) and r.get("text")):
        _thieu.append(prov)
check(f"cả {len(main.PROVIDER_DEFS)} bộ não đều gọi được tool ở mức Toàn quyền",
      _thieu == [])
if _thieu:
    print("     bị bỏ lại: " + ", ".join(_thieu))

# ============================================================
# 5b. Engine không chạy nổi vòng tool -> bot vẫn phải TRẢ LỜI
# ============================================================
# Đây là ca ĐÃ XẢY RA THẬT, không phải phòng xa. Bản 0.24.0 nối mức Được ghi của gói ChatGPT
# vào `engine.responses_with_mcp` - một hàm tới lúc đó CHƯA TỪNG được gọi từ đâu và tự ghi
# EXPERIMENTAL trong docstring. Chạy thật thì nó trả rỗng, và hậu quả không dừng ở "tính năng
# mới chưa chạy": MỌI câu người ta nhắn cho bot đều nhận một lời xin lỗi kỹ thuật.
#
# Luật rút ra, và đây là thứ file này canh: **nâng mức quyền không được phép LẤY ĐI năng lực
# đã có.** Bot chạy tốt ở mức Chỉ đọc thì nâng lên Được ghi, xấu nhất, phải vẫn chạy như mức
# Chỉ đọc - kèm một câu nói rõ cho chủ, chứ không được chết.
def _lam_stream_rong(prov):
    def _fn(*a, **kw):
        _goi.append({"prov": prov, "co_tool": True})

        async def _gen():
            yield {"type": "error", "content": "ChatGPT trả về rỗng (backend Codex chưa hỗ trợ tool)."}
        return _gen()
    return _fn


for _ten in ("openrouter_chat_with_mcp", "responses_with_mcp"):
    setattr(main.engine, _ten, _lam_stream_rong(_ten))

_goi.clear()
r = chay("openai-oauth", "oauth", {**BOT, "muc_quyen": "auto"})
check("engine không gọi nổi tool -> bot VẪN trả lời được", isinstance(r, dict) and r.get("text"))
check("và lượt đó chạy lại bằng stream KHÔNG tool",
      len(_goi) == 2 and _goi[0]["co_tool"] is True and _goi[1]["co_tool"] is False)
# Trả lời được nhưng chạy THIẾU QUYỀN so với mức chủ đặt. Im lặng ở đây là kiểu hỏng tệ nhất:
# chủ tưởng bot đang làm việc thật, còn nó chỉ đang nói chuyện.
_cb = (r or {}).get("canh_bao") or ""
check("và kèm cảnh báo cho chủ, không im lặng hạ mức", bool(_cb))
check("cảnh báo nói rõ mức đang chạy khác mức đã đặt", "Chỉ đọc" in _cb and "Được ghi" in _cb)
check("cảnh báo nói luôn việc cần làm", "trang Models" in _cb or "hạ mức" in _cb)

# Cảnh báo phải đi tới THẺ BOT, không chỉ nằm trong biến. Và phải tách khỏi `loi` - `loi` kéo
# theo bộ đếm bí rồi kéo theo gọi người trực, trong khi đây là lượt trả lời bình thường.
import chatbot_log  # noqa: E402

chatbot_log.ghi("bot_cb", {"hoi": "x", "dap": "y", "canh_bao": "chạy thiếu quyền"})
check("nhật ký giữ cảnh báo tách khỏi lỗi",
      chatbot_log.canh_bao_gan_nhat("bot_cb") == "chạy thiếu quyền"
      and chatbot_log.loi_gan_nhat("bot_cb") == "")
check("lượt có cảnh báo KHÔNG bị tính là bí (không gọi người trực oan)",
      chatbot_log.doc("bot_cb")[0].get("bi") is False)
check("thẻ bot nhận được cảnh báo lượt gần nhất",
      'b["canh_bao_luot"] = chatbot_log.canh_bao_gan_nhat(b["id"])' in
      (SERVER / "main.py").read_text(encoding="utf-8"))

# Cả hai engine cùng gãy (tool rỗng VÀ không-tool cũng rỗng) thì mới được báo hỏng.
main._api_stream = _stream_hong_luon = lambda *a, **kw: _gen_rong()


def _gen_rong():
    async def _g():
        yield {"type": "error", "content": "hết quota"}
    return _g()


r = chay("openai-oauth", "oauth", {**BOT, "muc_quyen": "auto"})
check("gãy cả hai đường -> mới báo hỏng, và nói đúng lý do",
      isinstance(r, str) and "quota" in r)
main._api_stream = _stream_khong_tool
for _ten in ("openrouter_chat_with_mcp", "responses_with_mcp"):
    setattr(main.engine, _ten, _lam_stream_co_tool(_ten))


# Hub không trả tool nào (chưa đấu nguồn nào, hoặc hub tắt): bot vẫn phải TRẢ LỜI được thay vì
# im. Nhưng lượt đó là "chỉ chat", nên nó phải đi đúng stream không tool chứ không gọi vòng
# tool rỗng - vòng tool rỗng thì engine API nào cũng có con báo lỗi schema.
async def _discover_rong(mode="full", vault_root=None, **kw):
    return [], {}


mcp_hub.discover_all = _discover_rong
_goi.clear()
r = chay("openrouter", "api", {**BOT, "muc_quyen": "full"})
check("hub không có tool nào -> bot vẫn trả lời được",
      isinstance(r, dict) and r.get("text"))
check("và lượt đó rơi về stream không tool", _goi[-1]["co_tool"] is False)
check("chưa đấu nguồn nào cũng phải cảnh báo, đừng để chủ tưởng bot đang làm việc",
      bool((r or {}).get("canh_bao")))

# Hub NỔ giữa chừng cũng không được làm gãy lượt của khách đang chờ.
async def _discover_no(mode="full", vault_root=None, **kw):
    raise RuntimeError("hub sập")


mcp_hub.discover_all = _discover_no
r = chay("openrouter", "api", {**BOT, "muc_quyen": "auto"})
check("hub nổ -> bot vẫn trả lời, không gãy lượt", isinstance(r, dict) and r.get("text"))
mcp_hub.discover_all = _discover_gia


# ============================================================
# 6. Nhật ký ghi lại mức lượt đó CHẠY THẬT
# ============================================================
# Chủ hạ mức sau một sự cố thì cấu hình hiện tại không còn nói lên được "hôm đó bot làm gì".
import chatbot_log  # noqa: E402

chatbot_log.ghi("bot_test_muc", {"hoi": "x", "dap": "y", "muc_quyen": "full"})
check("nhật ký giữ mức quyền của từng lượt",
      chatbot_log.doc("bot_test_muc")[0].get("muc_quyen") == "full")
chatbot_log.ghi("bot_test_muc2", {"hoi": "x", "dap": "y"})
check("lượt không khai mức -> ghi là Chỉ đọc",
      chatbot_log.doc("bot_test_muc2")[0].get("muc_quyen") == "suggest")


# ============================================================
# 7. Route: chặn nâng quyền, và trả về ĐỦ thứ giao diện cần để hỏi lại
# ============================================================
_SRC = (SERVER / "main.py").read_text(encoding="utf-8")
check("route tạo bot nhận mức quyền + xác nhận",
      "muc_quyen: str = Form(\"\")" in _SRC and "xac_nhan_rui_ro: str = Form(\"\")" in _SRC)
check("route trả can_force kèm lý do, không im lặng hạ mức",
      '"can_force": True' in _SRC and "chatbot_store.canh_bao_muc(m)" in _SRC)
check("danh sách bot kèm luôn nhãn + cảnh báo từng mức (giao diện không chép cứng)",
      '"muc_quyen": [' in _SRC and "chatbot_store.MUC_NHAN.get(m, m)" in _SRC)
check("rào xác nhận trả 400 chứ không phải 404",
      "status_code=400 if err == chatbot_store.LOI_CHUA_XAC_NHAN else 404" in _SRC)

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả xanh.")
