"""Cổng an toàn của pilot đầu-cuối Resonance (review e2e P1-2), kiểm bằng fixture giả: không chạy CLI, không gọi model.

    python tests/run.py resonance_e2e_guard -v
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _e2e_pilot_guard as G  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


env = {"PATH": "x", "USERPROFILE": "u", "ANTHROPIC_API_KEY": "k", "ANTHROPIC_BASE_URL": "u", "CLAUDE_CODE_X": "1",
       "CLAUDECODE": "1", "AWS_PROFILE": "p", "GOOGLE_APPLICATION_CREDENTIALS": "f", "OPENROUTER_API_KEY": "k",
       "MY_SERVICE_API_KEY": "k", "AZURE_OPENAI_ENDPOINT": "e", "CLOUDSDK_CONFIG": "c", "LOCALAPPDATA": "l",
       "CLAUDE_CONFIG_DIR": "cfg"}
ce = G.clean_env(env)
check("clean_env bỏ biến phiên Claude, khoá, bộ chọn AWS/Google/Azure; giữ PATH, hồ sơ người dùng và thư mục cấu "
      "hình Claude của người dùng", set(ce) == {"PATH", "USERPROFILE", "LOCALAPPDATA", "CLAUDE_CONFIG_DIR"})

tmp = Path(tempfile.mkdtemp(prefix="e2eguard-"))
cfg, proj = tmp / "cfg", tmp / "proj"
(cfg).mkdir()
(proj / ".claude").mkdir(parents=True)
paths = [cfg / "settings.json", cfg / "settings.local.json", proj / ".claude" / "settings.json",
         proj / ".claude" / "settings.local.json"]
check("không có file settings nào: không rủi ro", G.scan_settings(paths)["risky"] is False)
(cfg / "settings.json").write_text(json.dumps({"theme": "dark", "env": {"FOO": "1"}}), encoding="utf-8")
check("settings bình thường: không rủi ro", G.scan_settings(paths)["risky"] is False)
(cfg / "settings.json").write_text(json.dumps({"apiKeyHelper": "/bin/get-key.sh"}), encoding="utf-8")
r = G.scan_settings(paths)
check("apiKeyHelper ở settings người dùng: rủi ro, chỉ ghi TÊN khoá", r["risky"] is True
      and r["files"][0]["risky"] == ["apiKeyHelper"] and "/bin/get-key.sh" not in json.dumps(r))
(cfg / "settings.json").write_text("{}", encoding="utf-8")
(proj / ".claude" / "settings.local.json").write_text(json.dumps({"env": {"CLAUDE_CODE_USE_BEDROCK": "1",
                                                                         "ANTHROPIC_API_KEY": "sk-x"}}), encoding="utf-8")
r = G.scan_settings(paths)
check("env chọn nhà cung cấp/khoá ở settings dự án: rủi ro, không lộ giá trị", r["risky"] is True
      and "env.CLAUDE_CODE_USE_BEDROCK" in r["files"][3]["risky"] and "sk-x" not in json.dumps(r))
(proj / ".claude" / "settings.local.json").write_text("{không phải json", encoding="utf-8")
check("file settings không đọc được: tính là rủi ro (đóng an toàn)", G.scan_settings(paths)["risky"] is True)
check("danh sách nguồn có user, project, local và managed",
      len(G.settings_paths(cfg, proj)) >= 6 and any("managed-settings" in str(x) for x in G.settings_paths(cfg, proj)))

ok = {"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty", "subscriptionType": "max",
      "email": "x@y"}
check("auth status gói thuê bao, nhà cung cấp gốc: được phép", G.check_auth_status(ok)[0] is True)
for bad, why in ((dict(ok, authMethod="apiKey"), "api key"), (dict(ok, authMethod="apiKeyHelper"), "helper"),
                 (dict(ok, apiProvider="bedrock"), "bedrock"), (dict(ok, loggedIn=False), "chưa đăng nhập"),
                 (dict(ok, subscriptionType=None), "không có gói"), ("lỗi", "không phải dict")):
    check(f"auth status {why}: bị từ chối", G.check_auth_status(bad)[0] is False)
check("metadata xác thực chỉ có 4 trường, không có email hay id",
      G.auth_metadata(ok) == {"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty",
                              "subscriptionType": "max"})

# ───────────── Review e2e vòng 2 ─────────────
sysb = tmp / "sys" / "ClaudeCode"
(sysb / "managed-settings.d").mkdir(parents=True)
(sysb / "managed-settings.d" / "20-credentials.json").write_text(json.dumps({"apiKeyHelper": "/fake.sh"}),
                                                                  encoding="utf-8")
ms = G.managed_sources(cfg, bases=[sysb], registry=[])
check("managed-settings.d/*.json (fixture apiKeyHelper của người review) được phát hiện, không lộ nội dung",
      ms == ["ClaudeCode/managed-settings.d/20-credentials.json"] and "/fake.sh" not in json.dumps(ms))
check("không có nguồn managed nào: danh sách rỗng", G.managed_sources(cfg, bases=[tmp / "khong-co"], registry=[]) == [])
check("khoá registry policy được tính là nguồn managed",
      G.managed_sources(cfg, bases=[], registry=["HKLM\\SOFTWARE\\Policies\\ClaudeCode"]) ==
      ["registry:HKLM\\SOFTWARE\\Policies\\ClaudeCode"])
(cfg / "remote-settings.json").write_text("{}", encoding="utf-8")
check("cache settings kiểu remote/managed trong thư mục cấu hình được tính là nguồn managed",
      "config/remote-settings.json" in G.managed_sources(cfg, bases=[], registry=[]))
(cfg / "remote-settings.json").unlink()
(cfg / "settings.json").write_text(json.dumps({"hooks": {"PreToolUse": []}, "enabledPlugins": {"x": True},
                                               "theme": "dark"}), encoding="utf-8")
anc = G.ancillary_sources([cfg / "settings.json"])
check("hook và plugin được ghi là ngoài phạm vi cổng (chỉ tên khoá)",
      anc == ["cfg/settings.json:hooks", "cfg/settings.json:enabledPlugins"])

APPROVED = {"main": {"provider": "anthropic-cli", "model": "claude-opus-5-5"},
            "aux": {"provider": "anthropic-cli", "model": "sonnet"}, "claude_model": "claude-opus-5-5"}
good = {"main": {"provider": "anthropic-cli", "model": "claude-opus-5-5"},
        "aux": {"provider": "anthropic-cli", "model": "sonnet"}, "claude_model": "claude-opus-5-5"}
check("engine đúng cấu hình đã duyệt: qua", G.check_engines(good, APPROVED)[0] is True)
for name, bad in (("bộ não chính chọn Codex", {**good, "main": {"provider": "openai-oauth", "model": "gpt-5"}}),
                  ("việc nền chọn OpenRouter", {**good, "aux": {"provider": "openrouter", "model": "x"}}),
                  ("model bộ não khác", {**good, "main": {"provider": "anthropic-cli", "model": "sonnet"}}),
                  ("claude_model khác", {**good, "claude_model": "haiku"}),
                  ("không resolve được", {})):
    check(f"engine sai so với cấu hình duyệt ({name}): dừng", G.check_engines(bad, APPROVED)[0] is False)
check("dry chỉ kiểm việc nền bị chặn, không ép giống real",
      G.check_engines({"aux": {"provider": "grok-cli", "model": "grok-dry"}},
                      {"aux": {"provider": "grok-cli"}})[0] is True)

TRIPLES = [("Lan", "09/10"), ("Minh", "10/10"), ("Hà", "12/10")]
ok_txt = "| Người | Việc | Hạn |\n|---|---|---|\n| Lan | Soạn kế hoạch | 09/10 |\n| Minh | Kiểm lịch | 10/10/2026 |\n" \
         "- **Hà**: gửi bảng số liệu, hạn 12/10\n"
check("sản phẩm đủ ba bộ người và hạn (bảng hay danh sách, có thể kèm năm): đạt", G.content_has_triples(ok_txt, TRIPLES) == [])
check("cho phép ngày viết 9/10 thay 09/10", G.content_has_triples("Lan - 9/10", [("Lan", "09/10")]) == [])
check("đoạn không có người và ngày được yêu cầu (ca sai của người review): thiếu cả ba",
      G.content_has_triples("Một ghi chú chung chung, đủ dài.", TRIPLES) == ["Lan 09/10", "Minh 10/10", "Hà 12/10"])
check("người và ngày ở hai dòng khác nhau không tính", G.content_has_triples("Lan\n09/10", [("Lan", "09/10")]) ==
      ["Lan 09/10"])
check("ngày 19/10 không bị nhận nhầm là 9/10", G.content_has_triples("Lan 19/10", [("Lan", "09/10")]) == ["Lan 09/10"])
t0 = 1_800_000_000.0
check("lịch xem lại trong [6 giờ, 24 giờ] sau mốc đánh giá: đạt", G.review_wake_ok(t0 + 24 * 3600, t0, 6 * 3600,
                                                                                   24 * 3600))
check("lịch xem lại MỘT NĂM sau (ca của người review): KHÔNG đạt",
      G.review_wake_ok(t0 + 365 * 86400, t0, 6 * 3600, 24 * 3600) is False)
check("lịch xem lại quá sớm (1 giờ): KHÔNG đạt", G.review_wake_ok(t0 + 3600, t0, 6 * 3600, 24 * 3600) is False)

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
