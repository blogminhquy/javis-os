"""Gói Claude Code xác thực bằng gì, và cảnh báo có nói đúng lúc không.

    python tests/run.py claude_auth

Vì sao file này tồn tại: 0.26.17 gỡ đường Javis tự đọc token đăng nhập Claude Code rồi gọi
thẳng api.anthropic.com (Anthropic cấm, đã có người bị khoá tài khoản). Chủ repo CHỦ Ý không
tắt cứng đường chạy nền bằng gói subscription - đó là lựa chọn của người dùng. Đổi lại, hai
thứ phải luôn đúng, và đó là những gì file này canh:

  1. Chọn `api_key` thì key PHẢI xuống được tới tiến trình `claude`, và không được làm chết
     lượt chat khi người dùng chọn api_key mà quên dán key.
  2. Cảnh báo phải hiện ĐÚNG lúc đáng lo (gói subscription đang gánh việc nền) và im lúc
     không đáng - cảnh báo nhá suốt thì người ta học cách bỏ qua nó.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import sys

import claude_auth   # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def S(auth=None, key="", aux_prov=None):
    m = {}
    if auth is not None:
        m["claude_auth"] = auth
    if key:
        m["anthropic_api_key"] = key
    if aux_prov is not None:
        m["auxiliary"] = {"provider": aux_prov, "model": ""}
    return {"model": m}


# ---- 1. Đọc chế độ ----
check("mặc định là gói subscription", claude_auth.che_do(S()) == claude_auth.SUBSCRIPTION)
check("chọn api_key thì đọc ra api_key",
      claude_auth.che_do(S(auth="api_key")) == claude_auth.API_KEY)
check("hoa/thường và khoảng trắng không làm lệch",
      claude_auth.che_do(S(auth="  API_KEY ")) == claude_auth.API_KEY)
for _xau in ("", None, "apikey", "subscription", "full", 1, True):
    check(f"giá trị lạ {_xau!r} -> về subscription (fail-safe về cái không tốn tiền)",
          claude_auth.che_do(S(auth=_xau)) == claude_auth.SUBSCRIPTION)
check("cấu hình rỗng hoàn toàn cũng không nổ", claude_auth.che_do({}) == claude_auth.SUBSCRIPTION)

# ---- 2. Biến môi trường xuống tiến trình `claude` ----
check("chế độ subscription -> KHÔNG truyền env (để CLI dùng phiên đăng nhập sẵn)",
      claude_auth.env_cho_cli(S(key="sk-ant-x")) == {})
check("chế độ api_key + có key -> truyền ANTHROPIC_API_KEY",
      claude_auth.env_cho_cli(S(auth="api_key", key="sk-ant-x"))
      == {"ANTHROPIC_API_KEY": "sk-ant-x"})
# Ca thật hay gặp: bấm chọn "API key" trước, đi tìm key sau. Trả env rỗng là lui về phiên đăng
# nhập sẵn có; trả {"ANTHROPIC_API_KEY": ""} là mọi lượt chat chết bằng lỗi xác thực.
check("chọn api_key mà QUÊN dán key -> lui về phiên sẵn có, không làm chết lượt chat",
      claude_auth.env_cho_cli(S(auth="api_key")) == {})

# ---- 3. Cảnh báo: đúng lúc, và im lúc không đáng ----
check("subscription + việc nền chạy Claude -> CÓ cảnh báo",
      claude_auth.canh_bao_neu_can(S(aux_prov="anthropic-cli")) != "")
check("việc nền thiếu hẳn provider (cấu hình cũ = Claude) -> vẫn CÓ cảnh báo",
      claude_auth.canh_bao_neu_can(S()) != "")
check("subscription nhưng việc nền đã trỏ provider khác -> im",
      claude_auth.canh_bao_neu_can(S(aux_prov="groq")) == "")
check("đã chuyển sang api_key -> im, kể cả khi việc nền vẫn là Claude",
      claude_auth.canh_bao_neu_can(S(auth="api_key", key="sk", aux_prov="anthropic-cli")) == "")

_cb = claude_auth.canh_bao_neu_can(S())
for _phai_co in ("cá nhân", "VPS", "khoá tài khoản", "API key"):
    check(f"cảnh báo nói rõ {_phai_co!r}", _phai_co in _cb)
check("cảnh báo không dùng em dash (luật trình bày của Javis)", "—" not in _cb)
check("câu ngắn cũng không dùng em dash", "—" not in claude_auth.CANH_BAO_NGAN)

# ---- 4. Engine SDK thật sự có đọc chế độ này ----
_sdk = (SERVER / "claude_sdk_engine.py").read_text(encoding="utf-8")
check("engine SDK gọi claude_auth.env_cho_cli", "claude_auth.env_cho_cli()" in _sdk)
# Thay nguyên env thay vì merge là tiến trình con mất PATH/HOME và chết trước khi kịp chào.
check("env được MERGE với os.environ, không thay thế", "{**os.environ, **_env}" in _sdk)
check("có nhánh system prompt trần cho đường tiết kiệm", "self.system_prompt_raw" in _sdk)

# ---- 5. Server nhận và chuẩn hoá lựa chọn từ trang Models ----
_main = (SERVER / "main.py").read_text(encoding="utf-8")
check("POST /settings nhận khoá claude_auth", '"claude_auth" in patch' in _main)
check("/providers trả chế độ + cảnh báo cho thẻ Claude Code",
      'item["auth_mode"] = claude_auth.che_do(cfg)' in _main
      and 'item["auth_warning"] = claude_auth.canh_bao_neu_can(cfg)' in _main)
_js = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
check("trang Models có ô chọn và có gửi lên server",
      'name="claudeAuth"' in _js and 'saveSetting("model", { claude_auth: r.value })' in _js)

print()
if _fails:
    print(f"{len(_fails)} test HỎNG: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả test claude_auth đã qua.")
