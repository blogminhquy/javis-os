"""drive_write_guard.py - policy FAIL-CLOSED cho GHI lên Google Drive/Docs/Sheets qua Composio.

Phạm vi: chỉ quyết định ALLOW/DENY cho một lời gọi tool. Không gọi mạng, không sửa file.
Mặc định GUARD_MODE = "off": module không được gọi, hành vi cũ giữ nguyên.

Chế độ (đọc từ env JAVIS_DRIVE_WRITE_GUARD):
    off     - không kiểm tra
    shadow  - tính quyết định, ghi log, KHÔNG chặn
    enforce - chặn lời gọi bị DENY

Tên tool và tham số đã đối chiếu với COMPOSIO_GET_TOOL_SCHEMAS (2026-11-24):
    GOOGLEDRIVE_CREATE_FILE      (parents)
    GOOGLEDRIVE_MOVE_FILE        (file_id, add_parents, remove_parents)
    GOOGLEDRIVE_TRASH_FILE       (file_id)
    GOOGLEDRIVE_UPDATE_DRIVE     (driveId)            - shared drive, luôn DENY khi không phải own
    GOOGLEDRIVE_CREATE_PERMISSION(file_id)
    GOOGLEDRIVE_COPY_FILE        (file_id)            - DEPRECATED, vẫn coi là ghi
    GOOGLEDRIVE_PARSE_FILE       (file_id)            - đọc (export)
    GOOGLESHEETS_UPDATE_VALUES_BATCH (spreadsheet_id)
    GOOGLESHEETS_CLEAR_VALUES    (spreadsheet_id)
    GOOGLEDOCS_CREATE_DOCUMENT   (không có ID đích; tạo ở root -> DENY)
    GOOGLEDOCS_COPY_DOCUMENT     (document_id; bản sao nằm root -> DENY)
    COMPOSIO_MULTI_EXECUTE_TOOL  (tools[].tool_slug, tools[].arguments)
    COMPOSIO_PROXY_EXECUTE       KHÔNG có trong schema hub -> coi là không xác định -> DENY.

Nguyên tắc fail-closed:
    - Actor không xác định hoặc không có trong WRITE_ROOTS -> DENY mọi thao tác ghi.
    - Tool không nằm trong danh sách đọc tường minh -> coi là GHI.
    - MỌI ID đích và ID thư mục đích (file, sheet, doc, parents, add_parents, remove_parents)
      phải nằm dưới WRITE_ROOT của chính actor. Thiếu ID -> DENY.
    - Tool cổng: xét TỪNG lệnh con; lồng tool cổng -> DENY.
    - Proxy: chỉ GET tường minh; thiếu method -> DENY.
    - Lỗi trong quá trình quyết định -> DENY.
"""
from __future__ import annotations

import os
from typing import Callable, Iterable, Optional

MODE_ENV = "JAVIS_DRIVE_WRITE_GUARD"
MODES = ("off", "shadow", "enforce")

# Cấu hình RIÊNG của từng cài đặt (ID thư mục Drive, tên actor, account Composio) KHÔNG nằm trong mã nguồn.
# Đọc từ file JSON local: biến môi trường JAVIS_DRIVE_GUARD_CONFIG, nếu không có thì drive_guard.local.json
# cạnh file này (đã nằm trong .gitignore). Dạng file:
#   {"composio_account": "<tên account Composio đọc metadata>",
#    "write_roots":     {"<slug agent>": "<folder ID WRITE riêng>", ...},
#    "protected_roots": {"root": "<ID>", "governance": "<ID>", "shared": "<ID>", "inbox": "<ID>", "archive": "<ID>"}}
# Thiếu file -> không có WRITE_ROOT nào -> mọi thao tác ghi bị DENY (fail-closed). Đọc vẫn được.
CONFIG_ENV = "JAVIS_DRIVE_GUARD_CONFIG"


def load_config(path: Optional[str] = None) -> dict:
    import json
    import os
    p = path or os.environ.get(CONFIG_ENV) or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                           "drive_guard.local.json")
    if not os.path.isfile(p):
        return {}
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("cấu hình drive guard phải là object JSON")
    return data


_CFG = load_config()
COMPOSIO_ACCOUNT: str = str(_CFG.get("composio_account") or "")
WRITE_ROOTS: dict[str, str] = {str(k): str(v) for k, v in (_CFG.get("write_roots") or {}).items()}
PROTECTED_ROOTS: dict[str, str] = {str(k): str(v) for k, v in (_CFG.get("protected_roots") or {}).items()}

# Tool ĐỌC tường minh (theo schema thật). Mọi tool Drive/Docs/Sheets khác là GHI.
READ_TOOLS: frozenset[str] = frozenset({
    "GOOGLEDRIVE_LIST_FILES",
    "GOOGLEDRIVE_GET_FILE_METADATA",
    "GOOGLEDRIVE_PARSE_FILE",
    "GOOGLEDRIVE_DOWNLOAD_FILE",
    "GOOGLEDRIVE_LIST_PERMISSIONS",
    "GOOGLEDRIVE_GET_PERMISSION",
    "GOOGLEDRIVE_LIST_REVISIONS",
    "GOOGLEDRIVE_FIND_FILE",
    "GOOGLEDRIVE_SEARCH_FILES",
    "GOOGLESHEETS_GET_VALUES",
    "GOOGLESHEETS_BATCH_GET",
    "GOOGLESHEETS_GET_SPREADSHEET",
    "GOOGLESHEETS_GET_SPREADSHEET_INFO",
    "GOOGLEDOCS_GET_DOCUMENT",
    "GOOGLEDOCS_GET_DOCUMENT_BY_ID",
})

_DRIVE_TOOL_PREFIXES = ("GOOGLEDRIVE_", "GOOGLEDOCS_", "GOOGLESHEETS_")

# Ghi tạo đối tượng ở vị trí do Drive chọn (root), không có tham số đích -> luôn DENY.
_NO_DEST_CONTROL = frozenset({"GOOGLEDOCS_COPY_DOCUMENT", "GOOGLEDOCS_CREATE_DOCUMENT"})
_CONTROL_TOOLS = frozenset({"COMPOSIO_MULTI_EXECUTE_TOOL", "COMPOSIO_PROXY_EXECUTE"})

# Mọi khóa chứa ID file/sheet/doc/thư mục/drive. Cả snake_case lẫn camelCase.
_ID_KEYS = (
    "file_id", "fileId",
    "spreadsheet_id", "spreadsheetId",
    "document_id", "documentId",
    "driveId", "drive_id",
    "folder_id", "folderId",
    "parents", "parent_id", "parentId",
    "add_parents", "addParents",
    "remove_parents", "removeParents",
    "id",
)

MAX_DEPTH = 40
MAX_NEST = 3


def current_mode(env: Optional[dict] = None) -> str:
    raw = ((env if env is not None else os.environ).get(MODE_ENV) or "off").strip().lower()
    return raw if raw in MODES else "off"


def is_read_tool(tool: str) -> bool:
    return tool.upper() in READ_TOOLS


def is_drive_tool(tool: str) -> bool:
    return tool.upper().startswith(_DRIVE_TOOL_PREFIXES)


def _ids_from(args: dict, keys: Iterable[str]) -> list[str]:
    out: list[str] = []
    for k in keys:
        if k not in args:
            continue
        v = args.get(k)
        if isinstance(v, str):
            if v.strip():
                out.append(v.strip())
            else:
                out.append("")  # ô rỗng -> sẽ bị coi là thiếu ID
        elif isinstance(v, list):
            for x in v:
                if isinstance(x, str):
                    out.append(x.strip())
                else:
                    out.append("")
        else:
            out.append("")
    return out


def _all_within(start_id: str, root: str, parents_of: Callable[[str], list[str]]) -> bool:
    """True CHỈ KHI mọi đường đi ngược từ start_id đều tới root (multi-parent: mọi cha đều phải trong vùng).
    Fail-closed: không có cha, chu trình, vượt MAX_DEPTH -> False."""
    ok_nodes: set[str] = set()
    budget = [MAX_DEPTH * 4]
    path: set[str] = set()

    def walk(cur: str, depth: int) -> bool:
        if cur == root:
            return True
        if cur in ok_nodes:
            return True
        if cur in path or depth >= MAX_DEPTH or budget[0] <= 0:
            return False
        budget[0] -= 1
        ps = parents_of(cur) or []
        if not ps:
            return False
        path.add(cur)
        try:
            for par in ps:
                if not walk(par, depth + 1):
                    return False
        finally:
            path.discard(cur)
        ok_nodes.add(cur)
        return True

    return walk(start_id, 0)


def decide(actor: Optional[str], tool: str, args, parents_of: Callable[[str], list[str]],
           _depth: int = 0) -> dict:
    """ALLOW/DENY cho một lời gọi. Không ném lỗi: mọi ngoại lệ thành DENY."""
    try:
        return _decide(actor, tool, args, parents_of, _depth)
    except Exception as e:  # fail-closed
        return {"allow": False, "reason": f"lỗi nội bộ khi kiểm quyền ghi ({type(e).__name__})"}


def _decide(actor, tool, args, parents_of, depth) -> dict:
    if depth > MAX_NEST:
        return {"allow": False, "reason": "lệnh lồng quá sâu"}
    if not isinstance(tool, str) or not tool.strip():
        return {"allow": False, "reason": "tool không xác định"}
    tool = tool.strip().upper()
    if not isinstance(args, dict):
        return {"allow": False, "reason": "tham số không phải object"}

    if tool == "COMPOSIO_PROXY_EXECUTE":
        # Không có trong schema hub đã kiểm; nếu xuất hiện, chỉ cho GET tường minh.
        raw_method = args.get("method")
        if not isinstance(raw_method, str) or not raw_method.strip():
            return {"allow": False, "reason": "proxy thiếu method (fail-closed)"}
        if raw_method.strip().upper() == "GET":
            return {"allow": True, "reason": "proxy GET (đọc)"}
        return {"allow": False, "reason": f"proxy {raw_method.strip().upper()} không được phép qua hub"}

    if tool == "COMPOSIO_MULTI_EXECUTE_TOOL":
        subs = args.get("tools")
        if not isinstance(subs, list) or not subs:
            return {"allow": False, "reason": "tool cổng không có danh sách lệnh con"}
        for sub in subs:
            if not isinstance(sub, dict):
                return {"allow": False, "reason": "lệnh con không hợp lệ"}
            name = sub.get("tool_slug")
            if not isinstance(name, str) or not name.strip():
                return {"allow": False, "reason": "lệnh con thiếu tool_slug"}
            if name.strip().upper() in _CONTROL_TOOLS:
                return {"allow": False, "reason": "tool cổng lồng trong tool cổng không được phép"}
            sub_args = sub.get("arguments")
            if not isinstance(sub_args, dict):
                return {"allow": False, "reason": f"lệnh con {name} thiếu arguments (fail-closed)"}
            r = _decide(actor, name, sub_args, parents_of, depth + 1)
            if not r["allow"]:
                return {"allow": False, "reason": f"lệnh con {name}: {r['reason']}"}
        return {"allow": True, "reason": "mọi lệnh con đều được phép"}

    if is_read_tool(tool):
        return {"allow": True, "reason": f"đọc tường minh ({tool})"}

    if not is_drive_tool(tool):
        # Ngoài Drive/Docs/Sheets: guard này không quyết (lớp allowed() xử lý).
        return {"allow": True, "reason": "ngoài phạm vi guard Drive"}

    # Từ đây là GHI trên Drive/Docs/Sheets. Fail-closed.
    if actor not in WRITE_ROOTS:
        return {"allow": False, "reason": f"actor '{actor}' không có WRITE_ROOT (fail-closed)"}
    own = WRITE_ROOTS[actor]

    if tool in _NO_DEST_CONTROL:
        return {"allow": False, "reason": f"{tool} đặt bản sao ở thư mục gốc, không kiểm được đích (fail-closed)"}

    ids = _ids_from(args, _ID_KEYS)
    if not ids:
        return {"allow": False, "reason": "không xác định được file/thư mục đích"}
    for i in ids:
        if not i:
            return {"allow": False, "reason": "ID đích rỗng hoặc sai kiểu (fail-closed)"}
        if i in PROTECTED_ROOTS.values():
            return {"allow": False, "reason": "đích là thư mục được bảo vệ"}

    for i in ids:
        if not _all_within(i, own, parents_of):
            return {"allow": False, "reason": f"ID {i} nằm ngoài WRITE_ROOT của agent"}
    return {"allow": True, "reason": f"mọi ID nằm trong WRITE_ROOT {actor}"}


def enforce_decision(mode: str, decision: dict) -> bool:
    """True = chặn. Chỉ enforce mới chặn."""
    return mode == "enforce" and not decision.get("allow", False)


# ---------------------------------------------------------------------------
# Connector claude.ai đi TRỰC TIẾP (không qua hub). Claude Code nạp chúng qua setting_sources
# (user/project/local) ở các lượt không gated. Ở chế độ enforce, ta thêm deny rule theo tên server
# vào disallowed_tools của ClaudeAgentOptions (cùng cách memory_control làm). Chỉ enforce mới bật.
# Tên server lấy từ tên tool quan sát được: mcp__claude_ai_Google_Drive__update_file -> server
# "claude_ai_Google_Drive". Chưa kiểm chứng trên Claude Code thật: xem drive-write-guard.md.
DIRECT_CONNECTOR_SERVERS = (
    "mcp__claude_ai_Google_Drive",
    "mcp__claude_ai_Google_Docs",
    "mcp__claude_ai_Google_Sheets",
)
_DIRECT_MARK = "_javis_drive_direct_deny"


def direct_deny_rules(env: Optional[dict] = None) -> list[str]:
    """Deny rules cho connector trực tiếp. Chỉ có khi mode == enforce; off/shadow trả []."""
    return list(DIRECT_CONNECTOR_SERVERS) if current_mode(env) == "enforce" else []


def add_direct_deny(opts, env: Optional[dict] = None):
    """Gộp deny rule vào opts.disallowed_tools. No-op khi không enforce. Trả opts."""
    rules = direct_deny_rules(env)
    if not rules or opts is None or not hasattr(opts, "disallowed_tools"):
        return opts
    cur = list(getattr(opts, "disallowed_tools", None) or [])
    opts.disallowed_tools = cur + [r for r in rules if r not in cur]
    return opts


def install_direct_deny() -> bool:
    """Bọc ClaudeSDK._options một lần. Idempotent. Trả False nếu không cài được."""
    import claude_sdk_engine as eng
    cls = eng.ClaudeSDK
    f = cls._options
    while f is not None:
        if getattr(f, _DIRECT_MARK, False):
            return True
        f = getattr(f, "__wrapped__", None)
    original = cls._options

    def _options(self):
        return add_direct_deny(original(self))

    setattr(_options, _DIRECT_MARK, True)
    _options.__wrapped__ = original
    cls._options = _options
    return True
