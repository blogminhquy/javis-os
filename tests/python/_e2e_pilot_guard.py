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


# ───────────── Review e2e vòng 2 ─────────────

MANAGED_DIR_NAMES = ("managed-settings.d",)
MANAGED_FILE_HINTS = ("managed", "remote-settings", "policy")
ANCILLARY_KEYS = ("hooks", "enabledPlugins", "extraKnownMarketplaces", "mcpServers", "enableAllProjectMcpServers",
                  "enabledMcpjsonServers", "statusLine")


def managed_sources(config_dir: Path, bases=None, registry=None) -> list:
    """Nguồn settings do quản trị đặt mà cổng KHÔNG đánh giá nội dung: managed-settings.json và thư mục
    managed-settings.d/*.json ở các vị trí hệ thống, khoá registry policy của Claude Code (Windows), và file cache
    kiểu managed/remote trong thư mục cấu hình người dùng. Có bất kỳ nguồn nào thì pilot coi là môi trường CHƯA hỗ trợ
    và dừng (review e2e vòng 2). Trả danh sách mô tả ngắn, không có nội dung."""
    found = []
    if bases is None:
        bases = [Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "ClaudeCode",
                 Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "ClaudeCode",
                 Path("/Library/Application Support/ClaudeCode"), Path("/etc/claude-code")]
    for b in bases:
        b = Path(b)
        if (b / "managed-settings.json").is_file():
            found.append(f"{b.name}/managed-settings.json")
        for d in MANAGED_DIR_NAMES:
            if (b / d).is_dir():
                found += [f"{b.name}/{d}/{x.name}" for x in sorted((b / d).glob("*.json"))] or [f"{b.name}/{d}/"]
    cfg = Path(config_dir)
    if cfg.is_dir():
        for x in sorted(cfg.iterdir()):
            if x.is_file() and x.name != "settings.json" and x.name != "settings.local.json" \
                    and any(h in x.name.lower() for h in MANAGED_FILE_HINTS):
                found.append(f"config/{x.name}")
    if registry is None:
        registry = _registry_policy_keys()
    found += [f"registry:{k}" for k in registry]
    return found


def _registry_policy_keys() -> list:
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []
    out = []
    for hive, name in ((winreg.HKEY_LOCAL_MACHINE, "HKLM"), (winreg.HKEY_CURRENT_USER, "HKCU")):
        try:
            winreg.CloseKey(winreg.OpenKey(hive, r"SOFTWARE\Policies\ClaudeCode"))
            out.append(name + r"\SOFTWARE\Policies\ClaudeCode")
        except OSError:
            pass
    return out


def ancillary_sources(paths) -> list:
    """Cấu hình có thể chạy tiến trình hay dịch vụ riêng ngoài phạm vi cổng xác thực (hook, plugin, MCP...). Cổng
    KHÔNG chứng minh các thứ này không tiêu tiền; báo cáo ghi TÊN khoá tìm thấy để nói rõ phạm vi bảo đảm."""
    out = []
    for p in paths:
        p = Path(p)
        if not p.is_file():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8") or "{}")
        except Exception:  # noqa: BLE001
            continue
        if isinstance(d, dict):
            out += [f"{p.parent.name}/{p.name}:{k}" for k in ANCILLARY_KEYS if d.get(k)]
    return out


def check_engines(resolved: dict, expected: dict) -> tuple:
    """So engine runtime SẼ chạy (resolve bằng luật runtime) với cấu hình người dùng đã duyệt. resolved/expected:
    {"main": {"provider","model"}, "aux": {...}, "claude_model": ...}; khoá vắng trong expected thì không kiểm."""
    for role in ("main", "aux"):
        exp = expected.get(role)
        if not exp:
            continue
        got = (resolved or {}).get(role) or {}
        for k in ("provider", "model"):
            if exp.get(k) and got.get(k) != exp[k]:
                return False, f"{role}.{k} là {got.get(k)!r}, đã duyệt {exp[k]!r}"
    if expected.get("claude_model") and (resolved or {}).get("claude_model") not in (None, "", expected["claude_model"]):
        return False, f"claude_model là {resolved.get('claude_model')!r}, đã duyệt {expected['claude_model']!r}"
    return True, ""


def _date_re(ddmm: str):
    import re
    d, m = ddmm.split("/")
    return re.compile(rf"(?<!\d)0?{int(d)}\s*/\s*0?{int(m)}(?!\d)")


def content_has_triples(text: str, triples) -> list:
    """Bộ (người, hạn) nào THIẾU trong sản phẩm: cùng một dòng phải có tên người và ngày (cho phép 9/10 hay 09/10,
    có thể kèm năm). Trả danh sách thiếu; rỗng là đủ."""
    lines = str(text or "").lower().splitlines()
    miss = []
    for who, when in triples:
        rx = _date_re(when)
        if not any(who.lower() in ln and rx.search(ln) for ln in lines):
            miss.append(f"{who} {when}")
    return miss


def review_wake_ok(due_at: float, t_ref: float, min_s: float, max_s: float, tol: float = 300) -> bool:
    """Lịch xem lại có giới hạn ở CẢ HAI đầu so với mốc đánh giá: [t_ref + min_s - tol, t_ref + max_s + tol]."""
    return (t_ref + min_s - tol) <= float(due_at) <= (t_ref + max_s + tol)


# ───────────── Review e2e vòng 3: chấm đủ bộ VIỆC, NGƯỜI, HẠN trong cùng một đơn vị trình bày ─────────────

def _units(text: str) -> list:
    """Tách sản phẩm thành các đơn vị trình bày để chấm quan hệ việc/người/hạn: mỗi hàng bảng; mỗi mục danh sách
    cùng các dòng tiếp nối (thụt vào, hoặc không mở mục mới) tới dòng trống; mỗi đoạn văn; và mỗi mục dưới một tiêu
    đề (tiêu đề cùng mọi dòng tới tiêu đề kế tiếp, cho bố cục gom theo người hay theo hạn). Không tìm trên toàn văn
    để khỏi ghép nhầm việc của người này với hạn của người khác."""
    import re
    lines = str(text or "").splitlines()
    units, cur = [], []
    bullet = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")

    def flush():
        if cur:
            units.append("\n".join(cur))
            cur.clear()

    for ln in lines:
        st = ln.strip()
        if not st:
            flush()
            continue
        if st.startswith("|"):
            flush()
            if not re.fullmatch(r"\|?[\s:|-]+\|?", st):
                units.append(st)
            continue
        if st.startswith("#"):
            flush()
            cur.append(ln)
            flush()
            continue
        if bullet.match(ln) and not ln.startswith((" ", "\t")):
            flush()
            cur.append(ln)
            continue
        if bullet.match(ln) and cur and not bullet.match(cur[0]):
            flush()
        cur.append(ln)
    flush()
    # Mục dưới tiêu đề: tiêu đề cùng các dòng sau nó tới tiêu đề kế tiếp.
    sec, sections = [], []
    for ln in lines:
        if ln.strip().startswith("#"):
            if sec:
                sections.append("\n".join(sec))
            sec = [ln]
        elif sec:
            sec.append(ln)
    if sec:
        sections.append("\n".join(sec))
    # Mỗi dòng cũng là một đơn vị: các dòng không gạch đầu dòng liền nhau (một "đoạn") có thể là ba việc của ba người.
    return units + [x for x in sections if "\n" in x] + [ln.strip() for ln in lines if ln.strip()]


def _norm(s: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFC", str(s or "")).casefold()


def _has_person(unit: str, who: str) -> bool:
    import re
    return re.search(r"(?<!\w)" + re.escape(_norm(who)) + r"(?!\w)", _norm(unit)) is not None


def _has_task(unit: str, item: dict) -> bool:
    u = _norm(unit)
    return any(all(_norm(k) in u for k in alt) for alt in item["task_keys"])


def content_contract(text: str, items) -> dict:
    """Chấm sản phẩm theo hợp đồng ba bộ việc/người/hạn. items: [{"who", "when", "task", "task_keys": [[cụm,...],
    ...]}]; một phương án cụm khớp khi MỌI cụm của nó có trong đơn vị. Trả {"verdict": met | not_met | unverified,
    "items": [{"who", "verdict", "why"}]}.

    - met: có một đơn vị chứa người, đúng hạn và đúng việc của người đó.
    - not_met: không thấy người; đơn vị của người chỉ có người và hạn, không có chữ việc; việc của NGƯỜI KHÁC nằm ở đơn
      vị của người này (gán sai); hay hạn của người khác thay cho hạn của người này.
    - unverified: đơn vị của người có chữ mô tả việc nhưng không khớp cụm đặc trưng nào (có thể là cách nói đồng
      nghĩa chưa hỗ trợ). KHÔNG tính là đạt; giữ sản phẩm cho người review, không kết luận bộ não làm sai."""
    import re
    units = _units(text)
    out, verdicts = [], []
    for it in items:
        own_date = _date_re(it["when"])
        others = [o for o in items if o is not it]
        # Chỉ đơn vị nói về ĐÚNG MỘT người của hợp đồng: đơn vị có nhiều người thì quan hệ việc/người/hạn không rõ.
        mine = [u for u in units if _has_person(u, it["who"]) and not any(_has_person(u, o["who"]) for o in others)]
        v, why = "not_met", "không thấy người này trong sản phẩm"
        if any(own_date.search(_norm(u)) and _has_task(u, it) for u in mine):
            v, why = "met", "đủ việc, người, hạn trong cùng một đơn vị"
        elif mine:
            v, why = "not_met", "không đơn vị nào có đủ việc, người và đúng hạn"
            for u in mine:
                nu = _norm(u)
                wrong_task = [o["who"] for o in others if _has_task(u, o) and not _has_person(u, o["who"])]
                wrong_date = (not own_date.search(nu)) and any(_date_re(o["when"]).search(nu) for o in others)
                if wrong_task:
                    v, why = "not_met", "việc của người khác nằm ở đơn vị của người này: " + ", ".join(wrong_task)
                    break
                if wrong_date:
                    v, why = "not_met", "hạn của người khác thay cho hạn của người này"
                    break
                rest = re.sub(r"(?<!\w)" + re.escape(_norm(it["who"])) + r"(?!\w)", " ", nu)
                for o in items:
                    rest = _date_re(o["when"]).sub(" ", rest)
                rest = re.sub(r"[\W_\d]+", " ", rest).split()
                filler = {"hạn", "chót", "người", "phụ", "trách", "việc", "ngày", "deadline", "là", "và"}
                if own_date.search(nu) and [w for w in rest if w not in filler] and not _has_task(u, it):
                    v, why = "unverified", "có mô tả việc nhưng không khớp cụm đặc trưng nào (cách nói chưa hỗ trợ)"
        out.append({"who": it["who"], "verdict": v, "why": why})
        verdicts.append(v)
    overall = "met" if verdicts and all(x == "met" for x in verdicts) else (
        "not_met" if "not_met" in verdicts else "unverified")
    return {"verdict": overall, "items": out}
