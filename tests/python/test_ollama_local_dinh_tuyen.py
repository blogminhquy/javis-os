"""Chat bằng model Ollama MÁY NHÀ phải chạy đúng engine Ollama, không rơi xuống `claude`.

    python tests/run.py ollama_local_dinh_tuyen     (KHÔNG mạng)

Chủ repo báo kèm ảnh (02/09): chọn model local `qwen3:4b-instruct`, gõ "hello", Javis trả
về "There's an issue with the selected model (qwen3:4b-instruct). It may not exist or you
may not have access to it." Câu đó KHÔNG có trong mã nguồn Javis - nó do chính binary
`claude` in ra. Badge dưới câu trả lời ghi `cli · qwen3:4b-instruct`, tức lượt chat đã bị
đưa cho Claude Code kèm tên model của Ollama.

Gốc của lỗi: `ollama-local` có `key_field = None`, vì thứ xác thực nó là một ĐỊA CHỈ chứ
không phải một khoá. Nhưng mọi cổng định tuyến trong main.py hỏi `kind == "api" and
api_key` để biết một nhà API có chạy được không - khoá rỗng vĩnh viễn nghĩa là trượt hết
các nhánh API rồi rơi xuống nhánh CLI cuối cùng. `aux_engine` đã miễn kiểm khoá rỗng cho
nhà này từ lâu (agent chạy được), chỉ đường chat bị bỏ quên.

Hai lớp chắn, mỗi lớp một canary - bỏ lớp nào lỗi cũng quay lại ở hình dạng hơi khác:
  1. `_provider_key` dịch ĐỊA CHỈ thành khoá dùng được, nên các cổng kia tự đúng.
  2. Nhánh CLI không cầm tên model của nhà khác nữa: rơi về bộ não mặc định là có chủ ý,
     nhưng phải rơi CẢ MODEL theo nó, không thì `claude --model qwen3:4b-instruct`.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


import main  # noqa: E402

# Lấy qua getattr: thiếu hàm thì test phải báo hỏng GỌN rồi chạy tiếp mấy khẳng định định
# tuyến bên dưới - đó mới là chỗ nói lên bệnh thật. Chết bằng traceback ngay đây thì người
# đọc log chỉ thấy "thiếu hàm", không thấy "lượt chat đi nhầm engine".
_pkey = getattr(main, "_provider_key", None)
DEF_OL = main._provider_def("ollama-local")
CO_DIA_CHI = {"main": {"provider": "ollama-local", "model": "qwen3:4b-instruct"},
              "ollama_local_endpoint": "http://127.0.0.1:11434"}

# ---- 1. Địa chỉ là thứ xác thực, không phải khoá ----
check("card Ollama máy nhà vẫn KHÔNG đòi khoá (key_field None)",
      DEF_OL["key_field"] is None and DEF_OL["kind"] == "api")
check("có hàm dịch địa chỉ thành khoá dùng được", callable(_pkey))
_pkey = _pkey or (lambda *a, **k: "")
check("có địa chỉ, không đặt khoá → vẫn ra một khoá dùng được",
      _pkey(CO_DIA_CHI, DEF_OL) == "local")
check("người dùng có đặt khoá (Ollama sau reverse proxy) → dùng đúng khoá đó",
      _pkey({**CO_DIA_CHI, "ollama_local_key": "bi-mat"}, DEF_OL) == "bi-mat")
check("CANARY: chưa đặt địa chỉ thì khoá RỖNG THẬT (ghim rơi về mặc định chung)",
      _pkey({"ollama_local_endpoint": ""}, DEF_OL) == "")
check("nhà khác không bị hàm này đụng tới",
      _pkey({"groq_api_key": "gsk_x"}, main._provider_def("groq")) == "gsk_x")

# ---- 2. Model chính là Ollama máy nhà ----
prov, kind, key, model = main._chat_provider(CO_DIA_CHI)
check("model chính Ollama máy nhà → định tuyến đúng nhà, đúng tên model",
      prov == "ollama-local" and kind == "api" and model == "qwen3:4b-instruct")
# Đây là bất biến THẬT sự bị vỡ trong ảnh chủ repo gửi: 8 cổng trong main.py đều hỏi đúng
# biểu thức này, nên chỉ cần nó đúng là cả 8 cổng cùng đúng.
check("CANARY: cổng `kind == 'api' and api_key` cho qua (8 cổng định tuyến đều hỏi câu này)",
      bool(kind == "api" and key))

# ---- 3. Ghim theo phiên ----
prov, kind, key, model = main._chat_provider_for_session(
    CO_DIA_CHI, {"pinned_provider": "ollama-local", "pinned_model": "qwen3:4b-instruct"})
check("CANARY: ghim phiên vào Ollama máy nhà KHÔNG bị coi là ghim hỏng",
      prov == "ollama-local" and model == "qwen3:4b-instruct" and bool(key))

# Gỡ địa chỉ sau khi ghim = ghim hỏng thật, phải rơi về mặc định chung chứ không chết lượt.
prov, kind, key, model = main._chat_provider_for_session(
    {"main": {"provider": "anthropic-cli", "model": "opus"}, "ollama_local_endpoint": ""},
    {"pinned_provider": "ollama-local", "pinned_model": "qwen3:4b-instruct"})
check("gỡ địa chỉ sau khi ghim → rơi về mặc định chung như mọi ghim hỏng khác",
      prov == "anthropic-cli" and model == "opus")

SRC = (ROOT / "server" / "main.py").read_text(encoding="utf-8")

# ---- 4. Thanh model phải nói đúng sự thật ----
# Đây chính là chữ "ghim hỏng" trong ảnh: /sessions/{id}/meta tính pin_ok bằng khoá, nên
# Ollama máy nhà chạy ngon mà nhãn vẫn kêu hỏng. Hai nơi phải giải nghĩa khoá GIỐNG NHAU.
check("CANARY: pin_ok dùng chung cách giải nghĩa khoá với đường định tuyến",
      "key = _provider_key(mcfg, d) if d else \"\"" in SRC
      and 'key = mcfg.get(d["key_field"], "") if d and d.get("key_field") else ""' not in SRC)

# ---- 5. Nhánh CLI không được cầm tên model của nhà khác ----
check("CANARY: nhánh Claude Code chỉ nhận model khi provider ĐÚNG là anthropic-cli",
      SRC.count('cli.model = ((api_model if prov == "anthropic-cli" else "")') == 2)
check("CANARY: không còn chỗ nào ném thẳng api_model cho binary `claude`",
      "cli.model = api_model or mcfg.get" not in SRC)

if _fails:
    print(f"\nFAIL {len(_fails)} muc: " + ", ".join(_fails))
    sys.exit(1)
print("\nOK - test_ollama_local_dinh_tuyen: tat ca pass")
