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

if _fails:
    print(f"\n{len(_fails)} FAIL:", _fails)
    sys.exit(1)
print("\nOK")
