"""Test lấy model Claude LIVE cho provider anthropic-cli. Chạy tay / CI:

    python tests/run.py claude_models

Không chạm mạng: chỉ kiểm phần suy alias + fallback khi không có API key.

Từ 0.26.17 file này KHÔNG còn kiểm phần đọc credential, vì phần đó đã bị gỡ khỏi mã: Javis
không đọc token OAuth của Claude Code nữa (Anthropic cấm dùng token gói Free/Pro/Max ngoài
Claude Code và Claude.ai - xem server/claude_auth.py). Nguồn duy nhất còn lại cho danh sách
live là `anthropic_api_key`. Mục 3 dưới đây là canary chống hồi quy: hễ có ai đưa lại đường
đọc credential vào module này thì test đỏ.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import asyncio
import sys


import claude_models as cm   # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


# ---- 1. Suy alias từ danh sách live ----
IDS = ["claude-opus-5", "claude-sonnet-5", "claude-fable-5", "claude-opus-4-8",
       "claude-haiku-4-5-20251001", "claude-opus-4-1-20250805"]
al = cm.aliases(IDS)
check("alias gồm đủ các dòng model", al == ["opus", "sonnet", "fable", "haiku"])
check("alias không trùng lặp", len(al) == len(set(al)))
check("bỏ qua id lạ", cm.aliases(["gpt-4o", "claude", "claude-", "x-opus-5"]) == [])

# ---- 2. Không có API key → None để caller giữ catalog tĩnh ----
# Đây là đường BÌNH THƯỜNG chứ không phải lỗi: phần đông người dùng chạy bằng gói subscription
# và không có API key. Bốn alias trong config.py vẫn trỏ bản mới nhất nên picker vẫn đủ dùng.
check("không key → None", asyncio.run(cm.fetch_models("")) is None)
check("key toàn khoảng trắng cũng là không key", asyncio.run(cm.fetch_models("   ")) is None)

# ---- 3. CANARY: module không được đọc credential của người dùng ----
# Soi bằng TOKEN MÃ chứ không bằng lời văn: tên file credential và chữ "OAuth" vẫn còn trong
# docstring của module (nó kể lại vì sao đường cũ bị gỡ), nên canary bắt chữ sẽ đỏ vì chính
# đoạn giải thích - bắt lời văn thay vì bắt mã. Mấy chuỗi dưới đây thì không bao giờ nằm trong
# một câu tiếng Việt.
_src = (SERVER / "claude_models.py").read_text(encoding="utf-8")
for _cam in ("subprocess", "read_text(", "os.getenv(", "Path.home()", '"Authorization"',
             "claudeAiOauth", "find-generic-password"):
    check(f"CANARY: không còn mã đọc credential ({_cam!r})", _cam not in _src)
check("CANARY: không còn hàm oauth_token", not hasattr(cm, "oauth_token"))
check("CANARY: module chỉ còn đúng hai hàm công khai",
      sorted(n for n in vars(cm) if not n.startswith("_") and callable(getattr(cm, n)))
      == ["aliases", "fetch_models"])
check("chỉ xác thực bằng x-api-key", "x-api-key" in _src)

print()
if _fails:
    print(f"{len(_fails)} test HỎNG: " + ", ".join(_fails))
    sys.exit(1)
print("Tất cả test claude_models đã qua.")
