"""Rào DUY NHẤT của bot chuyên trách: nó chỉ thấy brain của chính nó.

    python tests/run.py chatbot_cach_ly      (KHÔNG mạng)

Chủ repo chốt phạm vi ngày 2026-08-04: "Anh có Agent và quy định của nó rồi, em đừng tự thêm
vào quy định của nó. Chỉ có làm việc chống chỉ định xem các brain khác ngoài brain agent đang
ở thôi."

Nên file này canh HAI thứ, và chỉ hai thứ đó:

A. **Prompt là của Agent, không phải của Javis.** Không chèn khối luật nào lên trên hướng dẫn
   người dùng viết. Bản 0.19.0 tới 0.20.1 đều chèn, và nó cãi nhau với chính Agent.

B. **Cách ly brain, bằng MÃ chứ không bằng chữ.** Đây là phần đáng canh nhất, vì nó KHÔNG hiện
   ra khi dùng thử: bot vẫn trả lời đúng, vẫn lịch sự, và chủ không có cách nào biết nó vừa
   đọc được brain khác.

   Cách giải: **bot không được cấp tool nào cả.** Tài liệu do `chatbot_grounding` tra sẵn bằng
   Python TRƯỚC khi model chạy và nằm sẵn trong prompt, nên bỏ tool không làm bot mất khả năng
   đọc brain - chỉ bỏ khả năng đi lang thang trong đó. Không có tool thì không có gì để khoá.

   Hai bản trước đi đường vòng và đều hỏng theo kiểu riêng, ghi lại để đừng quay về:
     - 0.19.0-0.20.1 hạ mức quyền MCP xuống 'suggest'. Chỉ lọc tool của HUB, không đụng tool
       NATIVE của Claude Code (Bash, Read, Glob, Grep) - bot đọc được cả máy.
     - 0.21.0 khoá `allowed_tools` cho Claude Code, rồi TỪ CHỐI chạy trên Codex vì Codex không
       khoá được phạm vi đọc. Vá được lỗ nhưng phá lời hứa gốc của Javis: đổi bộ não thì năng
       lực phải giữ nguyên. Chủ repo bác đúng chỗ đó.

C. **Cùng một trải nghiệm trên cả tám bộ não.** Hệ quả của (B), và cũng là yêu cầu riêng:
   "dù là claude hay codex hay dùng api thì trải nghiệm nói chuyện với bot cũng vẫn giống
   nhau". Mục B3 chạy THẬT qua cả tám provider rồi đối chiếu payload từng con.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path
import os
import sys
import tempfile
from pathlib import Path

_STATE = tempfile.mkdtemp(prefix="javis-cachly-")
os.environ["JAVIS_STATE_DIR"] = _STATE

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import chatbot_runtime  # noqa: E402
import mcp_hub  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ============================================================
# A. Prompt là của Agent, Javis không chèn luật
# ============================================================
QUY_DINH = """## Quy định của tôi

1. Luôn hỏi lại người dùng đã ngủ đủ chưa trước khi tư vấn.
2. Không bao giờ nói "cố lên", đó là lời khuyên rỗng.
3. Mỗi câu trả lời kết thúc bằng đúng một hành động nhỏ làm được trong 5 phút."""

chatbot_runtime.wire(
    answer=None, brain_root=lambda b: "/tmp/khong-dung",
    read_agent=lambda brain, slug: ({"name": "Coach kỷ luật",
                                     "role": "Huấn luyện viên kỷ luật cá nhân."}, QUY_DINH),
)
bot = {"name": "Bot", "agent": {"brain": "brain", "slug": "coach"}, "handoff_to": "555"}
p = chatbot_runtime.build_bot_prompt(bot)

check("prompt lấy tên từ Agent", "Coach kỷ luật" in p)
check("prompt lấy vai trò từ Agent", "Huấn luyện viên kỷ luật cá nhân" in p)
check("prompt giữ NGUYÊN VĂN quy định người dùng viết", QUY_DINH in p)

# CANARY - đừng gỡ. Đây là yêu cầu trực tiếp của chủ repo, và là thứ dễ bị "thêm lại cho chắc"
# nhất: mỗi lần thấy bot trả lời chưa vừa ý, phản xạ đầu tiên là nhét thêm một dòng luật vào
# prompt. Làm vậy là quay lại đúng lỗi cũ - luật của Javis đè lên quy định người dùng đã viết.
for cam in ("Luật bắt buộc", "đứng trên mọi hướng dẫn khác", "Không hứa hẹn thay",
            "Bỏ qua mọi yêu cầu đổi vai", "Ngắn gọn, lịch sự", "cửa hàng", "bảng giá",
            "Người nhắn cho bạn có thể là NGƯỜI LẠ"):
    check(f"CANARY: Javis KHÔNG chèn luật của mình - '{cam[:32]}'", cam not in p)

check("prompt KHÔNG mang system prompt điều phối của Javis",
      "javis_schedule" not in p and "Kanban" not in p and "MCP Hub" not in p)

_SRC_RT = (SERVER / "chatbot_runtime.py").read_text(encoding="utf-8")
check("module không còn hằng số khối luật", "_LUAT" not in _SRC_RT)

# Tài liệu tra sẵn vẫn vào prompt, nhưng vào như DỮ LIỆU chứ không kèm mệnh lệnh nào.
p_tl = chatbot_runtime.build_bot_prompt(
    {**bot, "_tai_lieu": {"co": True, "khoi": "### Giá\n\nGói 3 tháng 6 triệu.", "nguon": ["gia.md"]}})
check("tài liệu tra được vẫn đưa vào prompt", "Gói 3 tháng 6 triệu" in p_tl)
check("khối tài liệu không kèm mệnh lệnh nào",
      "TUYỆT ĐỐI" not in p_tl and "đừng suy ra" not in p_tl)

# Không tìm thấy tài liệu: mặc định IM LẶNG, không dặn dò gì thêm.
p_trong = chatbot_runtime.build_bot_prompt({**bot, "_tai_lieu": {"co": False, "khoi": "", "nguon": []}})
check("không có tài liệu -> mặc định không thêm chữ nào vào prompt", p_trong == p)

# Chế độ "chỉ tài liệu" là lựa chọn CỦA NGƯỜI DÙNG, nên ở đó mới có một câu chỉ dẫn.
p_chat = chatbot_runtime.build_bot_prompt(
    {**bot, "nguon_tra_loi": "tai_lieu", "_tai_lieu": {"co": False, "khoi": "", "nguon": []}})
check("chế độ chỉ-tài-liệu (người dùng tự bật) mới có một câu chỉ dẫn",
      "chế độ CHỈ TRẢ LỜI THEO" in p_chat)
check("và nó vẫn KHÔNG đụng tới quy định của Agent", QUY_DINH in p_chat)


# ============================================================
# B1. Hub khoá đường đọc file trong vault
# ============================================================
GOC = Path(tempfile.mkdtemp(prefix="javis-cachly-brains-"))
(GOC / "brain-bot").mkdir()
(GOC / "brain-bot" / "gia.md").write_text("Gói 3 tháng 6 triệu.\n", encoding="utf-8")
(GOC / "brain-chu").mkdir()
(GOC / "brain-chu" / "bi-mat.md").write_text("Giá vốn 400k, biên 70%.\n", encoding="utf-8")

BOT_ROOT = GOC / "brain-bot"
check("đọc file TRONG brain của bot -> được",
      mcp_hub._safe_path(BOT_ROOT, "gia.md") == (BOT_ROOT / "gia.md").resolve())
check("chính gốc vault -> được", mcp_hub._safe_path(BOT_ROOT, ".") == BOT_ROOT.resolve())

# Mọi kiểu trèo ra ngoài đều phải nổ, không phải trả về rỗng: trả rỗng thì model tưởng file
# không tồn tại và thử tiếp bằng đường khác.
for xau in ("../brain-chu/bi-mat.md",
            "../../etc/passwd",
            "./../brain-chu/bi-mat.md",
            "a/b/../../../brain-chu/bi-mat.md",
            str(GOC / "brain-chu" / "bi-mat.md"),      # đường dẫn TUYỆT ĐỐI
            "/etc/passwd"):
    try:
        mcp_hub._safe_path(BOT_ROOT, xau)
        ok = False
    except ValueError:
        ok = True
    check(f"CANARY: chặn đường ra brain khác - '{xau[:40]}'", ok)

# Bẫy tên: "brain-bot-khac" có tiền tố trùng "brain-bot" nên so chuỗi thô sẽ cho lọt.
(GOC / "brain-bot-khac").mkdir()
(GOC / "brain-bot-khac" / "x.md").write_text("của người khác\n", encoding="utf-8")
try:
    mcp_hub._safe_path(BOT_ROOT, "../brain-bot-khac/x.md")
    ok = False
except ValueError:
    ok = True
check("CANARY: brain trùng tiền tố tên cũng bị chặn (không so chuỗi thô)", ok)


# ============================================================
# B2. Bot KHÔNG được cấp tool nào - cùng một đường cho cả tám bộ não
# ============================================================
# Đây là lời giải cuối cùng, và nó thay cho hai bản chắp vá trước đó (khoá allowed_tools cho
# Claude Code ở 0.21.0, và TỪ CHỐI chạy trên Codex vì Codex không khoá được phạm vi đọc).
#
# Chủ repo đặt lại bài đúng chỗ: "dù là claude hay codex hay dùng api thì trải nghiệm nói
# chuyện với bot cũng vẫn giống nhau". Đi bốn nhánh engine thì không bao giờ giống nhau được -
# Claude Code có Bash, Codex có kho MCP riêng, engine API bị trần 8 vòng gọi tool.
#
# Bỏ tool giải cả hai bài cùng lúc: mọi engine nhận CÙNG prompt + CÙNG tài liệu + CÙNG lịch sử
# nên trả lời như nhau, và không có tool thì không có gì để khoá - cách ly brain thành hệ quả
# của kiến trúc chứ không phải một rào phải canh.
import asyncio  # noqa: E402
import types  # noqa: E402

import main  # noqa: E402

_SRC = (SERVER / "main.py").read_text(encoding="utf-8")

# Lượt bot phải THOÁT khỏi _tg_answer_engine trước MỌI nhánh engine. Đứng sau một nhánh nào là
# lượt đó đã kịp dựng CLI hoặc kịp nạp tool MCP rồi.
_than = _SRC[_SRC.index("async def _tg_answer_engine"):]
_vi_bot = _than.index("return await _bot_tra_loi(")
for moc, ten in ((_than.index('if prov == "openai-oauth":'), "nhánh Codex"),
                 (_than.index("_api_stream_mcp("), "nhánh engine API"),
                 (_than.index("claude_engine("), "nhánh Claude Code"),
                 (_than.index("_schedule_cancel_action("), "xử lý lệnh lịch của chủ")):
    check(f"lượt bot thoát ra TRƯỚC {ten}", _vi_bot < moc)

check("bot đi đường không tool (_api_stream), không phải đường có tool (_api_stream_mcp)",
      "_api_stream(prov, api_key, api_model, messages, reasoning)" in _SRC)
# Cắt ĐÚNG thân `_bot_tra_loi` - đường của mức Chỉ đọc. Từ 0.22.0 có thêm `_bot_tra_loi_co_tool`
# cho hai mức nới quyền, và nó nằm ngay dưới; cắt tới `_tg_answer_engine` như trước là nuốt luôn
# hàm kia vào rồi báo động giả. Mốc cắt phải là hàm ngay sau, không phải "hàm nào đó ở xa".
_ham = _SRC[_SRC.index("async def _bot_tra_loi("):_SRC.index("def _bot_stream_co_tool(")]
for cam in ("_api_stream_mcp", "mcp_hub", "discover_all", "claude_engine", "CodexCLI",
            "_apply_mcp", "collect_turn_files"):
    check(f"đường của bot KHÔNG đụng tới '{cam}'", cam not in _ham)
check("bot không nhận block kênh (dạy gửi file + lộ đường dẫn brain thật)",
      "build_channel_block" not in _ham)

# Mức nới quyền (0.22.0) KHÔNG được làm mềm rào này. Hai thứ phải giữ ở MỌI mức:
#   - tool file đi qua `_safe_path(vault_root)` của ĐÚNG brain bot, không trèo ra được;
#   - không có Bash/WebFetch/WebSearch/Task.
#
# Tới 0.26.16 cả hai là HỆ QUẢ MIỄN PHÍ của một sự thật kiến trúc: không engine nào của bot mở
# CLI, nên không con nào có tool native, nên chẳng có gì để trèo. 0.26.17 phải bỏ sự thật đó -
# gói Claude Code trước đây chạy bằng token OAuth moi từ Claude Code, thứ Anthropic cấm, nên
# nay nó chạy bằng chính binary `claude` và binary ấy CÓ tool native.
#
# Nên hai tính chất trên không còn miễn phí, và canary đổi theo: thay vì canh "đừng mở CLI",
# nó canh ĐÚNG BỐN LỚP đang thay thế cho sự thật cũ. Mất một lớp là mất rào.
_ham_tool = _SRC[_SRC.index("def _bot_stream_co_tool("):_SRC.index("async def _tg_answer_engine")]
check("CANARY: đường bot CÓ TOOL không tự dựng engine, chỉ gọi đúng hàm đã bọc rào",
      "claude_engine" not in _ham_tool and "CodexCLI" not in _ham_tool
      and "_claude_sub_stream_tools(" in _ham_tool)
check("bot không nhận block kênh, kể cả ở mức có tool",
      "build_channel_block" not in _ham_tool)
check("tool của bot lấy từ hub, cắm vào ĐÚNG brain của bot",
      "discover_all(muc_quyen, vault_root=_brain_root(brain))" in _ham_tool)
check("mức quyền đi thẳng xuống hub, không qua bảng dịch nào",
      "discover_all(muc_quyen" in _ham_tool)

# Bốn lớp rào của nhánh Claude Code, soi trong chính hàm dựng engine cho nó.
_ham_sub = _SRC[_SRC.index("def _claude_sub_stream_tools("):_SRC.index("def _api_stream_goc(")]
check("LỚP 1: allowlist chỉ có hub, nên cổng can_use_tool từ chối mọi tool native per-call",
      "allowed_tools=list(mcp_hub.allow_patterns())" in _ham_sub)
check("LỚP 2: chặn thẳng nhóm tool native",
      "cli.disallowed_tools = list(BOT_CAM_NATIVE)" in _ham_sub)
for _t in ('"Bash"', '"WebFetch"', '"WebSearch"', '"Task"', '"Read"', '"Write"', '"Edit"',
           '"Glob"', '"Grep"'):
    check(f"LỚP 2 gồm {_t}", _t in _SRC[_SRC.index("BOT_CAM_NATIVE = ["):
                                        _SRC.index("BOT_CAM_NATIVE = [") + 400])
check("LỚP 3: config hub mang brain CỦA BOT, nên tool file bị _safe_path khoá đúng brain đó",
      "mcp_hub.claude_config_path(mode, vault_root=vault)" in _ham_sub)
check("LỚP 4: strict, nên bot không thấy MCP ambient của máy chủ",
      "cli.mcp_strict = cli.mcp_config is not None" in _ham_sub)
check("và cwd của engine cũng là brain của bot, không phải gốc project",
      "cwd=vault" in _ham_sub)

# Fail-closed: chỉ HAI chữ đã khai mới mở tool, mọi thứ khác (bản ghi cũ thiếu khoá, file sửa
# tay gõ sai, None) rơi về đường không tool. Viết ngược lại - "khác 'suggest' thì mở tool" - là
# một lỗi chính tả trong chatbots.json cũng đủ cấp tool cho bot đang chat với người lạ.
_ren = _SRC[_SRC.index("async def _tg_answer_engine"):]
_ren = _ren[:_ren.index("return await _bot_tra_loi(")]
check("rẽ sang đường có tool CHỈ khi mức nằm trong danh sách đã khai",
      "if _muc in chatbot_store.MUC_NANG:" in _ren)

# _api_stream phục vụ đủ TÁM provider, kể cả hai gói subscription - nên không con nào phải mở
# CLI, và không con nào bị bỏ lại.
_as = _SRC[_SRC.index("def _api_stream(prov, key, model"):_SRC.index("async def _api_stream_mcp")]
for pid in [d["id"] for d in main.PROVIDER_DEFS]:
    check(f"_api_stream phục vụ được '{pid}'",
          f'prov == "{pid}"' in _as or pid == "anthropic-api")   # anthropic-api là nhánh mặc định
check("gói ChatGPT dùng token OAuth, không cần API key", "openai_oauth.valid_creds()" in _as)
# Gói Claude Code cũng không cần API key, nhưng KHÔNG phải bằng cách mượn token đăng nhập nữa:
# nó chạy qua binary `claude`. Đây là canary chống hồi quy cho đúng chỗ đã làm khoá tài khoản.
check("gói Claude Code không cần API key, và không mượn token đăng nhập của ai",
      "_claude_sub_stream(" in _as and "claude_models.oauth_token" not in _as)


# ============================================================
# B3. Chạy THẬT: tám bộ não, cùng một đầu vào
# ============================================================
# Kiểm bằng hành vi chứ không bằng đọc mã: ghi lại đúng thứ được gửi đi cho từng provider rồi
# đối chiếu. Đây mới là thứ trả lời được câu hỏi của chủ repo.
_goi = []


def _stream_gia(prov, key, model, messages, reasoning="off"):
    _goi.append({"prov": prov, "messages": [dict(m) for m in messages], "reasoning": reasoning})

    async def _gen():
        yield {"type": "text", "content": "Chào anh chị."}
        yield {"type": "usage", "input": 10, "output": 5}
    return _gen()


main._api_stream = _stream_gia
BOT = {"id": "bot_x", "name": "Bot", "brain": "brain-bot",
       "agent": {"brain": "brain", "slug": "coach"}}


def chay(prov, kind, sess=None, hoi="giá bao nhiêu"):
    return asyncio.run(main._tg_answer_engine(
        hoi, {"chat_id": "1", "chat_type": "private"}, None,
        chat_id="1", sess=sess if sess is not None else {"last": None, "sent": set()},
        brain="brain-bot", mcfg={}, prov=prov, kind=kind, api_key="k", api_model="m",
        bot={**BOT, "_tai_lieu": {"co": True, "khoi": "### Giá\n\n185.000đ", "nguon": ["gia.md"]}}))


_goi.clear()
ket = {}
for prov, kind in [(d["id"], d["kind"]) for d in main.PROVIDER_DEFS]:
    ket[prov] = chay(prov, kind)

check("cả tám bộ não đều trả lời được", all(isinstance(v, dict) and v["text"] for v in ket.values()))
check("cả tám đều đi qua đúng một đường", len(_goi) == len(main.PROVIDER_DEFS))
check("KHÔNG con nào bị từ chối vì engine",
      not any("chưa chạy được" in v.get("text", "") for v in ket.values() if isinstance(v, dict)))

# Đây là câu trả lời cho "đổi bộ não mà trải nghiệm không đổi": cùng một câu hỏi thì mọi engine
# nhận y hệt nhau, khác biệt còn lại đúng bằng khác biệt giữa các model.
_mau = _goi[0]["messages"]
check("CANARY: tám bộ não nhận CÙNG một payload", all(g["messages"] == _mau for g in _goi))
check("payload có system prompt của Agent", _mau[0]["role"] == "system")
check("payload có tài liệu đã tra sẵn", "185.000" in _mau[0]["content"])
check("payload có câu hỏi của người dùng", _mau[-1] == {"role": "user", "content": "giá bao nhiêu"})
check("payload KHÔNG kèm tool nào", all("tool" not in str(k).lower() for m in _mau for k in m))

# Nhớ mạch hội thoại, và cắt lịch sử để không phình vô hạn.
_sess = {"last": None, "sent": set()}
for i in range(15):
    chay("openrouter", "api", _sess, hoi=f"câu {i}")
check("bot nhớ mạch hội thoại", len(_sess["bot"]) > 2)
check("lịch sử bị cắt, không phình vô hạn", len(_sess["bot"]) <= main.BOT_LICH_SU_MAX)
check("cắt xong vẫn còn câu hỏi gần nhất",
      _sess["bot"][-2] == {"role": "user", "content": "câu 14"})

# Lượt hỏng thì không để câu hỏi treo lơ lửng không có câu trả lời.
def _stream_hong(prov, key, model, messages, reasoning="off"):
    async def _gen():
        yield {"type": "error", "content": "hết quota"}
    return _gen()


main._api_stream = _stream_hong
_sess2 = {"last": None, "sent": set()}
r = chay("groq", "api", _sess2)
check("lượt hỏng trả về chuỗi lỗi", isinstance(r, str) and "hết quota" in r)
check("lượt hỏng KHÔNG để câu hỏi treo trong lịch sử", _sess2["bot"] == [])



# ============================================================
# B4. Lượt bot được ghi ĐÚNG đường trên trang Tiết kiệm token
# ============================================================
# Chủ repo hỏi: "anh thấy chưa qua chức năng tiết kiệm và siêu tiết kiệm của bot".
#
# Đúng là bot không đi Phase 5 (đường tắt) hay Phase 8 (bộ nhớ chọn lọc) - hai tầng đó nằm
# TRONG websocket_endpoint, tức chỉ chạy cho chat trên dashboard. Nhưng bot cũng KHÔNG CẦN
# chúng: nó vốn đã nhẹ hơn cả mức Siêu tiết kiệm, vì hai tầng kia sinh ra để gọt đúng những
# thứ bot chưa bao giờ có (CLAUDE.md, MEMORY.md, đặc tả tool).
#
# Cái SAI thật nằm ở báo cáo: `pin_execution_path` chỉ nhận một danh sách tên cố định, tên lạ
# rơi hết về "legacy". Lượt bot không ghim gì nên bị xếp vào "Đầy đủ" - đường ĐẮT NHẤT - trong
# khi nó là đường RẺ NHẤT hệ thống. Trang đo nói ngược hẳn sự thật.
import context_runtime  # noqa: E402

check("'bot' là một đường hợp lệ, không rơi về legacy",
      '"workflow", "sources", "bot"' in (SERVER / "context_runtime.py").read_text(encoding="utf-8"))
check("lượt bot tự ghim đường của nó", '_CONTEXT_RUNTIME.pin_execution_path(' in _SRC
      and '"bot", None, context_runtime.RUNTIME_VERSION' in _SRC)
# Bảng nhãn đường giờ chỉ còn MỘT bản, nằm ở khung chat (app.js): trang Tiết kiệm gộp vào
# Mức dùng ở 0.24.7 và mang theo bản sao thứ hai của bảng này.
check("giao diện có nhãn tiếng Việt cho đường bot",
      'bot: "Bot chuyên trách"' in (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8"))

# Đo thật: prompt của bot phải nhỏ hơn hẳn capsule của mức Siêu tiết kiệm. Đây là bằng chứng
# cho câu "bot không cần hai tầng đó", chứ không phải lời khẳng định suông.
import context_compiler  # noqa: E402

_cc = context_compiler
_capsule = (_cc.CORE_CONTRACT + "Runtime identity: provider=x; model=y. "
            + _cc.ContextCompiler._channel_contract("dashboard") + _cc.dong_ho()
            + _cc.ContextCompiler._output_contract_text("dashboard"))
_p_bot = chatbot_runtime.build_bot_prompt(bot)
check(f"prompt bot ({len(_p_bot)} ký tự) nhỏ hơn capsule Siêu tiết kiệm ({len(_capsule)} ký tự)",
      len(_p_bot) < len(_capsule))

print()
if _fails:
    print(f"ĐỎ {len(_fails)} mục: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả xanh.")
