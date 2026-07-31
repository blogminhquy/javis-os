"""Regression: Javis là AI agentic ĐỔI ĐƯỢC BỘ NÃO, không phải sản phẩm của Claude.

Hai lỗi thật khách báo ở 0.9.270:

1. Máy chưa từng cài Claude, đang chạy OpenRouter làm bộ não, mà banner đỏ "⚠ Bộ não
   claude mất đăng nhập" treo mãi. _engines nằm trong RAM và trước đây không ai dọn, nên
   đèn thắp hồi Claude còn là Main Model không bao giờ tắt.

2. Hỏi Javis thì nó tự nhận "không có Claude Code thì chỉ chat chơi thôi, không điều phối,
   không làm task được". Sai: từ 0.9 cả bốn provider API đều đi qua _api_stream_mcp - có
   MCP Javis, tool file brain và skill. Chỉ lệnh máy (Bash) là riêng của hai engine CLI.
   Nguồn của lời nói sai đó là chính system prompt + các nhãn "chat thuần (không MCP)"
   rải trên giao diện.

Chạy:
    .venv/Scripts/python.exe tests/python/test_engine_ngang_quyen.py
"""
import re

from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path

import connect_health  # noqa: E402
import config as cfgmod  # noqa: E402

fails = []


def check(name: str, condition: bool) -> None:
    print(("PASS: " if condition else "FAIL: ") + name)
    if not condition:
        fails.append(name)


# ─────────── 1. Đèn báo não chỉ tính bộ não người dùng THẬT SỰ chọn ───────────

_real_read_settings = cfgmod.read_settings


def _fake_settings(main_prov, aux_prov=None):
    model = {"main": {"provider": main_prov, "model": "x"}}
    if aux_prov is not None:
        model["auxiliary"] = {"provider": aux_prov, "model": "y"}
    cfgmod.read_settings = lambda: {"model": model}


try:
    _fake_settings("anthropic-cli")
    check("Main = Claude Code → đèn claude được tính", connect_health.engines_in_use() == {"claude"})

    _fake_settings("openrouter")
    check("Main = OpenRouter, việc nền để trống → KHÔNG có đèn nào",
          connect_health.engines_in_use() == set())

    _fake_settings("openrouter", "anthropic-cli")
    check("Việc nền đặt RÕ là Claude → đèn claude sống lại",
          connect_health.engines_in_use() == {"claude"})

    _fake_settings("openai-oauth", "openrouter")
    check("Main = ChatGPT → đèn codex; provider API không có đèn",
          connect_health.engines_in_use() == {"codex"})

    _fake_settings("gemini", "openai")
    check("Cả hai đều là provider API → không đèn nào (API key sai thì lỗi ngay tại lượt chạy)",
          connect_health.engines_in_use() == set())

    # Đúng kịch bản của khách: đèn đỏ thắp hồi Claude còn là Main, rồi đổi sang OpenRouter.
    connect_health._engines.clear()
    _fake_settings("anthropic-cli")
    connect_health._set_engine("claude", False, "Hết phiên đăng nhập.", "run")
    check("đèn đỏ hiện ra khi Claude đang là Main",
          connect_health.engines_snapshot().get("claude", {}).get("ok") is False)

    _fake_settings("openrouter")
    check("đổi sang OpenRouter → banner tắt NGAY, không chờ vòng quét 10 phút",
          connect_health.engines_snapshot() == {})
    check("đèn cũ vẫn còn trong RAM (snapshot chỉ lọc, chưa dọn)",
          "claude" in connect_health._engines)

    connect_health.probe_engines()
    check("probe_engines dọn hẳn đèn của bộ não không còn dùng",
          "claude" not in connect_health._engines)

    # Không dùng Claude thì probe không được đụng tới file token của máy.
    _probed = []
    _orig_probe = connect_health.probe_claude_credentials
    connect_health.probe_claude_credentials = lambda path=None: (_probed.append(1), (True, ""))[1]
    try:
        _fake_settings("openrouter")
        connect_health.probe_engines()
        check("không dùng Claude → probe KHÔNG đọc credentials Claude", not _probed)
        _fake_settings("anthropic-cli")
        connect_health.probe_engines()
        check("dùng Claude → probe có đọc credentials", len(_probed) == 1)
    finally:
        connect_health.probe_claude_credentials = _orig_probe
finally:
    cfgmod.read_settings = _real_read_settings
    connect_health._engines.clear()


# ─────────── 2. Không chỗ nào được nói provider API "chỉ chat, không MCP" ───────────

CLAUDE_MD = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
CONSOLE_JS = (ROOT / "dashboard" / "console.js").read_text(encoding="utf-8")
INDEX = (ROOT / "dashboard" / "index.html").read_text(encoding="utf-8")
MAIN_PY = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")
DOC10 = (ROOT / "docs" / "10-models-va-engine.md").read_text(encoding="utf-8")
DOC01 = (ROOT / "docs" / "01-bat-dau-thiet-lap.md").read_text(encoding="utf-8")

# "chat thuần" chỉ còn được phép xuất hiện khi đang KỂ LẠI rằng nhãn cũ đã sai. Ở giao
# diện và system prompt thì cấm tiệt - đó là chỗ người dùng và chính Javis đọc để hiểu
# mình làm được gì.
for name, text in (("system prompt (CLAUDE.md)", CLAUDE_MD),
                   ("dashboard/console.js", CONSOLE_JS),
                   ("dashboard/index.html", INDEX)):
    check(f'{name} không còn nhãn "chat thuần"', "chat thuần" not in text)
    check(f'{name} không còn nhãn "không MCP"', "không MCP" not in text)

check("nhãn kiểu của provider API là 'MCP Javis', không phải 'chat'",
      '"MCP Javis"' in CONSOLE_JS and re.search(r'p\.kind === "cli" \? "MCP/skill" : "chat"', CONSOLE_JS) is None)
check("dòng Main Model nói rõ provider API vẫn có MCP + skill + loop",
      "Gọi API thẳng - MCP Javis + skill + loop" in CONSOLE_JS)

# Gemini từng bị sót khỏi MCP_PROVIDERS nên trang Kết nối báo nhầm "chưa hỗ trợ gọi công cụ"
# dù _api_stream_mcp đã phục vụ nó. Danh sách trên UI phải khớp danh sách thật ở server.
_ui = re.search(r"const MCP_PROVIDERS = \[([^\]]*)\]", CONSOLE_JS)
check("tìm được MCP_PROVIDERS trên UI", _ui is not None)
_ui_set = set(re.findall(r'"([^"]+)"', _ui.group(1))) if _ui else set()
_srv = re.search(r'if prov in \("openrouter", "openai", "anthropic-api", "gemini", "groq"\)', MAIN_PY)
check("server cấp MCP cho cả 5 provider API (kể cả gemini, groq)", _srv is not None)
check(f"UI liệt kê đúng 5 provider API đó + Claude Code (đang có: {sorted(_ui_set)})",
      _ui_set == {"anthropic-cli", "openrouter", "openai", "anthropic-api", "gemini", "groq"})

# System prompt: Javis phải tự biết mình đổi được bộ não và không được tự hạ thấp.
check("system prompt gọi Javis là AI agentic đổi được bộ não",
      "ĐỔI ĐƯỢC BỘ NÃO" in CLAUDE_MD)
check("system prompt nói rõ MỌI bộ não dùng chung một bộ đồ nghề",
      "MỌI bộ não đều được cấp cùng một bộ đồ nghề" in CLAUDE_MD)
check("system prompt cấm Javis tự nhận 'chỉ chat được'",
      "chỉ chat được" in CLAUDE_MD and "sai sự thật" in CLAUDE_MD)
check("system prompt nêu đúng khác biệt duy nhất là lệnh máy",
      "lệnh máy" in CLAUDE_MD)

# Tài liệu giới thiệu: bán "đổi được model", không bán "chạy trên Claude".
check("README mở đầu bằng AI agentic đổi được bộ não",
      "đổi được bộ não" in README.split("## Javis là gì?")[0])
check("README nêu triết lý năng lực nằm ở Javis chứ không ở model",
      "năng lực nằm ở Javis, không nằm ở model" in README)
check("doc Models nêu đổi model không mất chức năng",
      "đổi model KHÔNG làm Javis mất chức năng" in DOC10.replace("**", ""))
check("doc Models có cột riêng cho lệnh máy để nói rõ khác biệt",
      "Chạy lệnh máy (Bash)" in DOC10)
check("doc Bắt đầu nói rõ chọn provider nào cũng đủ chức năng",
      "Chọn cái nào cũng ra một Javis đủ chức năng" in DOC01)


if fails:
    raise SystemExit(f"\nFAIL - test_engine_ngang_quyen: {len(fails)} lỗi")
print("\nOK - test_engine_ngang_quyen: tất cả pass")
