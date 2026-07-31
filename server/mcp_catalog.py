"""
Catalog connector MCP - "kho kết nối" đi theo app (system/mcp-catalog.json).
Connector = MẪU (URL/command, cách đăng nhập, phân loại tool đọc/ghi).
Connection (mcp_store) = TÀI KHOẢN cụ thể user đã đấu theo mẫu đó.

Phân quyền: mỗi connection có perm, mỗi lượt chạy có mode (loop nền) - hub lấy mức CHẶT hơn:
  perm : readonly (chỉ tool đọc) | safe (thêm ghi thường, chặn danger) | full (tất cả)
  mode : suggest → ép readonly | auto → ép tối đa safe | full → theo perm
Tool đa hành động kiểu Pancake (1 tool, tham số action=list|create|...) phân loại theo
THAM SỐ qua arg_rules - enforcement thật diễn ra lúc tools/call (có args).
"""
import json
import re
import sys
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).parent.parent
CATALOG_PATH = ROOT / "system" / "mcp-catalog.json"

# Heuristic tên tool → nghi là "ghi" (fallback khi connector không khai tool_meta - vd custom).
# LƯU Ý: đây là denylist heuristic, connector lạ vẫn có thể lọt tool ghi tên khác thường -
# catalog connector chính chủ luôn khai tool_meta tường minh, custom thì khuyến nghị deny_tools.
WRITE_HINTS = ("create", "update", "delete", "add", "remove", "edit", "send", "set",
               "cancel", "refund", "pay", "post", "write", "upsert", "order", "purchase", "transaction",
               "reply", "accept", "invite", "join", "approve", "deploy", "publish", "upload",
               "execute", "submit", "launch", "react", "block", "kick")

PERM_RANK = {"readonly": 0, "safe": 1, "full": 2}
_MODE_CAP = {"suggest": "readonly", "auto": "safe", "full": "full"}

_cache = {"mtime": None, "by_id": {}}


def load():
    """Nạp catalog (cache theo mtime file). Trả dict id → connector."""
    try:
        mtime = CATALOG_PATH.stat().st_mtime
    except OSError:
        return {}
    if _cache["mtime"] == mtime:
        return _cache["by_id"]
    try:
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        by_id = {c["id"]: c for c in data.get("connectors", []) if c.get("id")}
    except Exception as e:
        print(f"[catalog] lỗi đọc {CATALOG_PATH.name}: {e}", file=sys.stderr)
        return _cache["by_id"]   # file hỏng → giữ bản cache cũ
    _cache.update(mtime=mtime, by_id=by_id)
    return by_id


def get(cid):
    return load().get(cid)


def public_catalog():
    """Bản cho UI - đủ vẽ kho + form đăng nhập, không lộ chi tiết nội bộ (validate/arg_rules)."""
    out = []
    for c in load().values():
        auth = c.get("auth") or {}
        out.append({
            "id": c["id"], "name": c.get("name", c["id"]), "icon": c.get("icon", "🔌"),
            "category": c.get("category", "Khác"), "description": c.get("description", ""),
            "status": c.get("status", "ready"), "transport": c.get("transport", "http"),
            "auth_type": auth.get("type", "apikey"),
            "fields": [{"key": f.get("key"), "label": f.get("label", f.get("key")),
                        "placeholder": f.get("placeholder", ""), "optional": bool(f.get("optional")),
                        "multiline": bool(f.get("multiline") or f.get("file"))}
                       for f in (auth.get("fields") or [])],
            "guide": auth.get("guide", ""), "guide_url": auth.get("guide_url", ""),
            "setup": auth.get("setup") or {},
            # Nhóm hiển thị (vd mọi dịch vụ Google gom về MỘT card) + wizard từng bước
            # thay guide tường chữ. steps: [{text, link?, link_label?, copy?}] -
            # copy="redirect" chèn ô sao chép Redirect URI ngay tại bước đó;
            # copy="domain" chèn ô sao chép tên miền trần (cho App Domains của Facebook).
            "group": c.get("group", ""), "group_line": c.get("group_line", ""),
            "steps": [{"text": s.get("text", ""), "link": s.get("link", ""),
                       "link_label": s.get("link_label", ""), "copy": s.get("copy", "")}
                      for s in (auth.get("steps") or [])],
            "risk": c.get("risk", ""), "default_perm": c.get("default_perm", "readonly"),
            # Có kho token riêng ngoài Javis → UI hiện nút "Đăng nhập lại Google (xoá quyền cũ)".
            # Chỉ trả CÓ hay KHÔNG (bool), không lộ tên biến môi trường ra frontend.
            "cred_dir": bool(c.get("cred_dir")),
        })
    return out


def match_url(url):
    """Đoán connector từ URL (dùng khi migrate registry cũ). So sánh prefix sau khi bỏ '/' cuối."""
    u = (url or "").strip().rstrip("/")
    if not u:
        return None
    for c in load().values():
        cu = (c.get("url") or "").strip().rstrip("/")
        if cu and (u == cu or u.startswith(cu + "/")):
            return c["id"]
    return None


def build_headers(connector, secrets):
    """Dựng headers thật từ template auth.fields (vd 'Authorization: Bearer {api_key}')."""
    headers = {}
    for f in ((connector or {}).get("auth") or {}).get("fields", []):
        tpl = f.get("header")
        key = f.get("key")
        if not tpl or not key:
            continue
        name, _, val = tpl.partition(":")
        if not name.strip():
            continue
        headers[name.strip()] = val.strip().replace("{" + key + "}", str((secrets or {}).get(key, "")))
    return headers


def build_url(connector, secrets):
    """Dựng URL thật cho connector khai `url_template` (vd '{base_url}/mcp-server/http').

    Vì sao cần: hầu hết MCP có MỘT địa chỉ dùng chung nên catalog ghi cứng `url` là đủ. Nhưng
    loại TỰ DỰNG (n8n, và mọi thứ self-host sau này) thì server nằm trên tên miền của chính
    người dùng - địa chỉ là một phần THÔNG TIN ĐĂNG NHẬP, không phải hằng số của app. Cho khai
    template rồi ghép từ ô người dùng gõ, thay vì bắt họ rơi sang connector "custom" (mất hướng
    dẫn, mất phân loại quyền đọc/ghi, mất cảnh báo rủi ro).

    Trả "" khi connector không khai template hoặc ô nguồn còn trống - caller tự rơi về url tĩnh.
    """
    tpl = (connector or {}).get("url_template") or ""
    if not tpl:
        return ""
    out = tpl
    for f in ((connector or {}).get("auth") or {}).get("fields", []):
        key = f.get("key")
        if not key or ("{" + key + "}") not in out:
            continue
        val = str((secrets or {}).get(key, "")).strip()
        if not val:
            return ""                      # thiếu ô nguồn thì đừng đẻ ra URL cụt
        if f.get("url_base"):
            val = normalize_base_url(val)
            if not val:
                return ""
        out = out.replace("{" + key + "}", val)
    return "" if "{" in out else out


def normalize_base_url(raw):
    """Chuẩn hoá địa chỉ instance người dùng gõ. Trả "" nếu không dùng được.

    Người ta gõ đủ kiểu: thiếu scheme ("cty.app.n8n.cloud"), thừa gạch chéo cuối, hoặc dán
    nguyên URL đang mở trên trình duyệt kèm đường dẫn và tham số. Cắt về đúng scheme + host
    (+ cổng) thì ghép template mới ra địa chỉ đúng, thay vì để người dùng tự mò khi Test đỏ.
    """
    u = (raw or "").strip()
    if not u or re.search(r"\s", u):
        return ""                          # có khoảng trắng thì chắc chắn không phải địa chỉ
    if "://" not in u:
        u = "https://" + u
    try:
        from urllib.parse import urlsplit
        p = urlsplit(u)
    except Exception:
        return ""
    if p.scheme not in ("http", "https") or not p.hostname:
        return ""
    # urlsplit rất dễ dãi, gần như chuỗi nào cũng ra được "hostname". Siết bằng bộ ký tự hợp lệ
    # của tên miền/IP (ngoặc vuông cho IPv6), nếu không thì chữ gõ nhầm lọt thành URL rồi tới
    # lúc Test mới báo lỗi khó hiểu.
    if not re.fullmatch(r"[A-Za-z0-9._\-\[\]:%]+", p.netloc):
        return ""
    return f"{p.scheme}://{p.netloc.lower()}"


def build_env(connector, secrets):
    """Dựng env thật từ auth.fields có khai 'env' (vd WEBCAKE_JWT). Bỏ qua giá trị rỗng.
    Field 'file' (dán nội dung file, vd service account JSON) KHÔNG map ở đây -
    mcp_store.resolved ghi ra file rồi mới gán env = đường dẫn.

    Connector còn khai được khối `env` TĨNH (hằng số kỹ thuật, KHÔNG phải secret) làm
    MẶC ĐỊNH - vd webcake-landing cần WEBCAKE_ENV=prod để package tự điền base URL API.
    Thứ hạng: ô đăng nhập user gõ > env tĩnh catalog; và env user tự đặt ở connection
    thắng cả hai (mcp_store.resolved đặt env connection trước rồi mới setdefault).
    Có khối này để KHỎI đẻ thêm ô nhập bắt user gõ URL kỹ thuật, cũng khỏi bắt user chạy
    lệnh login ngoài Javis."""
    env = {}
    for k, v in ((connector or {}).get("env") or {}).items():
        if k and v not in (None, ""):
            env[str(k)] = str(v)
    for f in ((connector or {}).get("auth") or {}).get("fields", []):
        ev = f.get("env")
        key = f.get("key")
        if not ev or not key or f.get("file"):
            continue
        val = str((secrets or {}).get(key, "") or "")
        if val:
            env[ev] = val
    return env


def classify(connector, tool, args=None):
    """'read' | 'write' | 'danger' cho MỘT lời gọi tool (tên GỐC, không namespace).
    args=None (lúc tools/list) → tool đa hành động tạm coi 'read' để còn LIỆT KÊ được;
    chặn thật diễn ra lúc tools/call khi đã có args."""
    c = connector or {}
    meta = c.get("tool_meta") or {}
    t = (tool or "").lower()

    def _in(patterns):
        return any(fnmatch(t, str(p).lower()) for p in (patterns or []))

    if _in(meta.get("read")):
        return "read"

    rules = c.get("arg_rules") or {}
    param = rules.get("param")
    # args=None (lúc tools/list) → rơi xuống phân loại TĨNH (danger/write list + heuristic).
    # Tool đa hành động muốn được liệt kê ở mức readonly thì hub tự kiểm schema (xem discover_all).
    # args là dict nhưng THIẾU param → cũng rơi xuống tĩnh (fail-closed: pos_order thiếu action = danger).
    if param and isinstance(args, dict) and args.get(param) is not None:
        v = str(args.get(param)).lower()
        if v in [str(x).lower() for x in rules.get("read_values", [])]:
            return "read"
        if any(v == p or v.startswith(p) for p in [str(x).lower() for x in rules.get("read_prefixes", [])]):
            return "read"
        return "danger" if _in(meta.get("danger")) else "write"

    if _in(meta.get("danger")):
        return "danger"
    if _in(meta.get("write")):
        return "write"
    if param and not isinstance(args, dict):
        return "read"   # đa hành động, chưa có args → xem ghi chú docstring
    if any(h in t for h in WRITE_HINTS):
        return "write"
    return "read"


def effective_perm(perm, mode):
    """Mức quyền HIỆU LỰC = chặt hơn giữa perm của connection và trần của mode."""
    perm = perm if perm in PERM_RANK else "full"
    cap = _MODE_CAP.get((mode or "full").strip().lower(), "full")
    return perm if PERM_RANK[perm] <= PERM_RANK[cap] else cap


def allowed(connector, perm, mode, tool, args=None):
    """(ok, lý_do_chặn_tiếng_Việt). Lớp CỨNG - không phụ thuộc prompt."""
    eff = effective_perm(perm, mode)
    if eff == "full":
        return True, ""
    cls = classify(connector, tool, args)
    if cls == "read":
        return True, ""
    if eff == "safe" and cls == "write":
        return True, ""
    vi_sao = ("loop/chạy nền đang ở chế độ giới hạn" if (mode or "full") in ("suggest", "auto")
              else "kết nối đang đặt mức quyền hạn chế")
    loai = "NGUY HIỂM (tiền/đơn/gửi tin)" if cls == "danger" else "ghi"
    return False, (f"Tool '{tool}' bị chặn: thao tác {loai} trong khi {vi_sao} (mức hiệu lực: {eff}). "
                   f"Nâng quyền ở trang Kết nối nếu thật sự cần.")
