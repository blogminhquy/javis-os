"""Cổng an toàn cho pilot đầu-cuối Resonance (review e2e P1-2): chỉ chạy khi CHỨNG MINH được bộ não dùng đăng nhập
gói thuê bao, không có đường sang API trả phí hay nhà cung cấp đám mây chưa duyệt.

Ba lớp, đều không gọi model:
1. clean_env: môi trường cho server sandbox như một Javis bình thường của người dùng (bỏ biến của phiên Claude Code
   đang chạy bộ chạy, khoá và bộ chọn nhà cung cấp).
2. scan_settings: soát các nguồn settings Claude Code mà engine chat nạp (`setting_sources` user, project, local, và
   managed) tìm `apiKeyHelper`, lệnh làm mới credential đám mây, hay `env` chọn khoá/nhà cung cấp/đường gọi. Chỉ ghi
   TÊN khoá tìm thấy, không ghi giá trị. File không đọc được thì tính là rủi ro (đóng an toàn).
3. check_auth_status: đọc `claude auth status --json` chạy bằng ĐÚNG binary, cwd và môi trường của engine; chỉ nhận
   loggedIn, authMethod claude.ai, apiProvider firstParty, có subscriptionType.
Tài liệu thứ tự chọn credential: https://code.claude.com/docs/en/authentication#authentication-precedence
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DROP_PREFIXES = ("CLAUDE", "ANTHROPIC", "OPENAI", "OPENROUTER", "GEMINI", "GOOGLE_", "GROQ", "XAI", "OLLAMA", "CODEX",
                 "AWS_", "AZURE_", "VERTEX", "BEDROCK", "CLOUDSDK", "GCLOUD")
DROP_SUFFIXES = ("_API_KEY", "_AUTH_TOKEN", "_ACCESS_TOKEN")
RISKY_TOP = ("apiKeyHelper", "awsAuthRefresh", "awsCredentialExport", "gcpAuthRefresh", "otelHeadersHelper")
RISKY_ENV_PREFIXES = ("ANTHROPIC_", "CLAUDE_CODE_USE_", "CLAUDE_CODE_OAUTH", "AWS_", "GOOGLE_", "VERTEX",
                      "BEDROCK", "AZURE_")


# Giữ: thư mục cấu hình Claude của người dùng (nếu họ đặt). Bỏ nó thì tiến trình quay về thư mục mặc định, không phải
# hồ sơ sạch, và không còn là cấu hình Javis bình thường của họ (review e2e P1-2). Cổng xác thực đọc thư mục cấu hình
# từ CHÍNH môi trường này rồi soát settings ở đó.
KEEP = ("CLAUDE_CONFIG_DIR",)


def clean_env(environ: dict) -> dict:
    return {k: v for k, v in environ.items()
            if k.upper() in KEEP or (not k.upper().startswith(DROP_PREFIXES) and not k.upper().endswith(DROP_SUFFIXES))}


def settings_paths(config_dir: Path, project_dir: Path) -> list:
    """Các file settings engine chat có thể nạp: user, project, local (project), managed (Windows, macOS, Linux)."""
    out = [Path(config_dir) / "settings.json", Path(config_dir) / "settings.local.json",
           Path(project_dir) / ".claude" / "settings.json", Path(project_dir) / ".claude" / "settings.local.json"]
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramData", r"C:\ProgramData")):
        out.append(Path(base) / "ClaudeCode" / "managed-settings.json")
    out += [Path("/Library/Application Support/ClaudeCode/managed-settings.json"),
            Path("/etc/claude-code/managed-settings.json")]
    return out


def scan_settings(paths) -> dict:
    """{"files": [{"source", "exists", "risky": [tên khoá]}], "risky": bool}. Không ghi giá trị nào."""
    files, risky_any = [], False
    for p in paths:
        p = Path(p)
        row = {"source": p.name if p.parent.name in (".claude", "ClaudeCode") else f"{p.parent.name}/{p.name}",
               "exists": p.is_file(), "risky": []}
        if p.is_file():
            try:
                d = json.loads(p.read_text(encoding="utf-8") or "{}")
                if not isinstance(d, dict):
                    raise ValueError("không phải object")
            except Exception:  # noqa: BLE001
                row["risky"] = ["<không đọc được>"]
            else:
                row["risky"] = sorted(k for k in RISKY_TOP if d.get(k))
                env = d.get("env") if isinstance(d.get("env"), dict) else {}
                row["risky"] += sorted(f"env.{k}" for k in env if str(k).upper().startswith(RISKY_ENV_PREFIXES)
                                       or str(k).upper().endswith(DROP_SUFFIXES))
        risky_any = risky_any or bool(row["risky"])
        files.append(row)
    return {"files": files, "risky": risky_any}


def check_auth_status(d) -> tuple:
    """(được phép, lý do). Chỉ nhận đăng nhập gói thuê bao Claude, nhà cung cấp gốc."""
    if not isinstance(d, dict):
        return False, "không đọc được auth status"
    if d.get("loggedIn") is not True:
        return False, "CLI chưa đăng nhập"
    if d.get("authMethod") != "claude.ai":
        return False, f"phương thức xác thực không phải gói thuê bao: {d.get('authMethod')!r}"
    if d.get("apiProvider") != "firstParty":
        return False, f"nhà cung cấp không phải Anthropic gốc: {d.get('apiProvider')!r}"
    if not d.get("subscriptionType"):
        return False, "không thấy loại gói thuê bao"
    return True, ""


def auth_metadata(d) -> dict:
    d = d if isinstance(d, dict) else {}
    return {k: d.get(k) for k in ("loggedIn", "authMethod", "apiProvider", "subscriptionType")}
