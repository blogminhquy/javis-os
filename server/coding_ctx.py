"""Ngữ cảnh làm việc của một phiên Coding, cho engine KHÔNG có tool file native.

Vì sao có file này
------------------
Trang Coding 0.63.0 đổi `cwd` của engine sang repo qua `main._cwd_luot_chat`. Nhưng **chỉ
engine CLI hưởng**, vì chỉ chúng có tool file native chạy theo `cwd`.

Engine API và engine Web đọc ghi qua `mcp_hub`, mà hub nhận `vault_root = _brain_root(brain)`
VÔ ĐIỀU KIỆN (`main.py:2190`), không hỏi `coding_store` một lần nào. Hệ quả: chọn
`chatgpt-web` rồi ngồi trong một phiên Coding thì model **không đọc nổi một file nào của
repo**, vì `_builtin_tools._read` chặn mọi đường dẫn ngoài vault.

Module này là chỗ gom ngữ cảnh ấy lại, để hub và các tool coding cùng đọc một nguồn thay vì
mỗi chỗ tự hỏi `coding_store` một kiểu.

Ba ranh giới có chủ ý
---------------------
1. **Rỗng là bình thường, không phải lỗi.** Phiên chat thường không có ràng buộc coding nào;
   lúc đó `workspace_root` rỗng và mọi thứ chạy y như trước. Đây là điều kiện để thay đổi này
   không đụng một lượt chat thường nào.
2. **Suy từ KHO, không suy từ tên kênh.** Kênh chỉ nói "phiên này thuộc trang Coding"; repo
   có thể đã bị gỡ khỏi sổ hoặc worktree bị xoá tay. Đọc `coding_store` thì hai cảnh đó tự
   trả về rỗng, đúng như `main._cwd_luot_chat` đang làm.
3. **KHÔNG đụng vault_root của MCP, cron, nhắc hẹn.** Nhánh Codex đã ghi rõ: "Hub vẫn trỏ
   BRAIN kể cả khi cwd là repo: MCP, cron và nhắc hẹn thuộc về bộ não của người dùng, không
   thuộc về cây mã nguồn đang mở." Đúng cho ba thứ đó. Sai cho tool FILE. Nên ở đây tách đúng
   một thứ là gốc của tool file, phần còn lại giữ nguyên brain.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import coding_store

# Mức quyền, giữ đúng tên của `coding_store` để không phải dịch qua lại.
SUGGEST = "suggest"
AUTO = "auto"
FULL = "full"


@dataclass(frozen=True)
class CodingToolContext:
    """Phiên này đang làm việc ở đâu, với quyền gì.

    `workspace_root` rỗng = không phải phiên coding. Mọi caller phải chịu được cảnh đó.
    """
    session_id: str = ""
    workspace_root: str = ""
    permission_mode: str = FULL
    repo_id: str = ""
    branch: str = ""
    worktree: str = ""
    is_git_repo: bool = False

    @property
    def active(self) -> bool:
        """Có phải phiên coding có nơi làm việc thật không."""
        return bool(self.workspace_root)

    @property
    def cho_ghi(self) -> bool:
        """Mức quyền này có cho GHI file không. `suggest` chỉ đọc."""
        return self.permission_mode in (AUTO, FULL)

    @property
    def cho_chay_lenh(self) -> bool:
        """Mức quyền này có cho chạy lệnh không. `suggest` thì không."""
        return self.permission_mode in (AUTO, FULL)

    @classmethod
    def from_session(cls, session_id: str) -> "CodingToolContext":
        """Dựng từ kho `coding_store`. Không phải phiên coding thì trả bản rỗng.

        Nuốt mọi lỗi của kho: một phiên chat không được chết chỉ vì sổ repo hỏng.
        """
        sid = str(session_id or "").strip()
        if not sid:
            return cls()
        try:
            cwd = coding_store.cwd_cua_phien(sid) or ""
        except Exception:
            return cls()
        if not cwd:
            return cls()

        rb = {}
        try:
            rb = coding_store.rang_buoc(sid) or {}
        except Exception:
            rb = {}

        try:
            quyen = coding_store.muc_quyen_cua_phien(sid) or FULL
        except Exception:
            quyen = FULL

        try:
            la_git = coding_store.la_git(cwd)
        except Exception:
            la_git = False

        return cls(
            session_id=sid,
            workspace_root=str(Path(cwd).resolve()) if cwd else "",
            permission_mode=str(quyen).strip().lower() or FULL,
            repo_id=str(rb.get("thu_muc") or ""),
            branch=str(rb.get("nhanh") or ""),
            worktree=str(rb.get("worktree") or ""),
            is_git_repo=bool(la_git),
        )

    def mo_ta(self) -> str:
        """Một dòng mô tả cho prompt. Rỗng khi không phải phiên coding.

        Ngắn là có chủ ý: engine Web không có system role, nên mọi chữ ở đây nằm trong chính
        tin nhắn đầu và cạnh tranh chỗ với system prompt của Javis.
        """
        if not self.active:
            return ""
        phan = [f"Thư mục làm việc: {self.workspace_root}"]
        if self.branch:
            phan.append(f"nhánh {self.branch}")
        if self.worktree:
            phan.append("đang ở worktree riêng")
        phan.append(f"mức quyền {self.permission_mode}")
        return ". ".join(phan) + "."


def for_session(session_id: str) -> CodingToolContext:
    """Bí danh gọn cho `CodingToolContext.from_session`."""
    return CodingToolContext.from_session(session_id)


def workspace_root_cua_phien(session_id: str) -> Optional[str]:
    """Gốc thư mục làm việc của phiên, hoặc None. Dùng ở chỗ chỉ cần mỗi đường dẫn."""
    ctx = CodingToolContext.from_session(session_id)
    return ctx.workspace_root or None
