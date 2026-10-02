"""File hạt giống của brain mới theo ngôn ngữ của người dùng (0.67.0).

Brain mới được rải sẵn vài file cho người dùng ĐỌC: Dashboard, chỉ mục bộ nhớ, README của lớp
điều phối, bốn file điều hướng wiki. Trước bản này chúng luôn là tiếng Việt, nên người dùng
tiếng Anh mở brain đầu tiên ra đã thấy toàn chữ Việt.

Cố ý KHÔNG có ở đây: `CLAUDE.md`/`AGENTS.md` của brain. Đó là hướng dẫn cho AI, và luật của
repo là không dịch prompt (`docs/dev/them-mot-ngon-ngu.md`, mục "Những gì không phải làm").

Hai đường vào:
  - `chon(goc)`: lúc TẠO file. Có request (tạo brain từ dashboard) thì theo thiết bị đang gọi.
  - `doi_ngon_ngu(root, ma)`: lúc người dùng CHỐT ngôn ngữ giao diện. Brain mặc định được tạo
    ngay khi server khởi động, trước khi có trình duyệt nào ghé, nên nó luôn ra tiếng Việt;
    hàm này viết lại những file hạt giống CÒN NGUYÊN (nội dung đúng y một bản hạt giống) sang
    ngôn ngữ vừa chọn. File người dùng đã sửa dù một ký tự thì không bao giờ bị đụng tới.
"""
from __future__ import annotations

import re
from pathlib import Path

import lang_registry
import localefmt

# ---------------------------------------------------------------------------
# Các bản hạt giống. Khoá = tên hạt giống; mỗi hạt giống có một bản cho từng ngôn ngữ.
# Bản tiếng Việt PHẢI giống từng ký tự với hằng số gốc trong main.py / meta_tools.py: đó là
# cách `doi_ngon_ngu` nhận ra file còn nguyên. Test test_brain_seed_ngon_ngu.py canh chuyện đó.
# ---------------------------------------------------------------------------
_TASKS = (
    "```tasks\nnot done\ndue before today\nsort by due\nlimit 20\n```\n\n",
    "```tasks\nnot done\ndue today\n```\n\n",
    "```tasks\nnot done\ndue after today\nsort by due\nlimit 20\n```\n\n",
    "```tasks\nnot done\nno due date\nlimit 20\n```\n",
)

HAT_GIONG = {
    "dashboard": {
        "vi": ("# Dashboard\n\n"
               "## 🔴 Nhiệm vụ quá hạn\n\n" + _TASKS[0] +
               "## 🟡 Nhiệm vụ hôm nay\n\n" + _TASKS[1] +
               "## 🟢 Sắp tới\n\n" + _TASKS[2] +
               "## 📥 Chưa có hạn\n\n" + _TASKS[3]),
        "en": ("# Dashboard\n\n"
               "## 🔴 Overdue\n\n" + _TASKS[0] +
               "## 🟡 Due today\n\n" + _TASKS[1] +
               "## 🟢 Coming up\n\n" + _TASKS[2] +
               "## 📥 No due date\n\n" + _TASKS[3]),
    },
    "memory": {
        "vi": ("# Bộ nhớ Javis - Index\n\n"
               "> Chỉ mục bộ nhớ dài hạn của Javis. Mỗi dòng = 1 ký ức, trỏ tới file trong `facts/`.\n"
               "> Nội dung file này được nạp vào đầu mỗi câu hỏi để Javis nhớ ngữ cảnh.\n\n"
               "_(Chưa có ký ức nào. Javis sẽ học dần sau mỗi hội thoại.)_\n"),
        "en": ("# Javis Memory - Index\n\n"
               "> Index of Javis's long-term memory. One line = one memory, pointing to a file in `facts/`.\n"
               "> This file is loaded at the start of every question so Javis remembers the context.\n\n"
               "_(No memories yet. Javis learns a little after every conversation.)_\n"),
    },
    "javis_readme": {
        "vi": ("# Javis\n\nLớp điều phối của Javis OS trong vault này.\n\n"
               "- `agents/` - các Agent (vai trò + skills + bộ nhớ riêng)\n"
               "- `workflows/` - quy trình nhiều agent (status active/off)\n"
               "- Skills dùng chung ở `skills/` (tự mirror sang `.claude/skills` cho Claude Code native)\n"),
        "en": ("# Javis\n\nThe Javis OS orchestration layer of this vault.\n\n"
               "- `agents/` - Agents (role + skills + their own memory)\n"
               "- `workflows/` - multi-agent workflows (status active/off)\n"
               "- Shared skills live in `skills/` (mirrored to `.claude/skills` for native Claude Code)\n"),
    },
    "wiki_index": {
        "vi": ("# Wiki Index\n\n"
               "Catalog nội dung wiki (cập nhật mỗi lần INGEST). Đọc file này trước khi trả lời câu hỏi.\n\n"
               "_(Chưa có trang wiki nào. Thả source vào `sources/` rồi bảo Javis \"tiêu hoá giúp tôi\" để bắt đầu tích luỹ tri thức.)_\n"),
        "en": ("# Wiki Index\n\n"
               "Catalogue of the wiki's content (updated on every INGEST). Read this file before answering a question.\n\n"
               "_(No wiki pages yet. Drop a source into `sources/` and ask Javis to \"digest it\" to start building up knowledge.)_\n"),
    },
    "wiki_log": {
        "vi": ("# Wiki Log\n\n"
               "Nhật ký thời gian (append-only). Mỗi entry: `## [YYYY-MM-DD] loại | tiêu đề` (loại: init/ingest/update/query/lint/migrate).\n"),
        "en": ("# Wiki Log\n\n"
               "Time-ordered log (append-only). Each entry: `## [YYYY-MM-DD] kind | title` (kind: init/ingest/update/query/lint/migrate).\n"),
    },
    "open_questions": {
        "vi": ("# Open Questions\n\n"
               "Câu hỏi wiki chưa trả lời đủ. Format mỗi dòng:\n"
               "- [ ] (YYYY-MM-DD) [[Chủ đề]]: câu hỏi/khoảng trống - status: open\n"),
        "en": ("# Open Questions\n\n"
               "Questions the wiki cannot fully answer yet. One per line:\n"
               "- [ ] (YYYY-MM-DD) [[Topic]]: question or gap - status: open\n"),
    },
    "session_handoff": {
        "vi": ("---\ntype: session-handoff\nstatus: clear\nupdated:\n---\n\n"
               "# Session Handoff\n\n"
               "Trạng thái phiên hiện hành để chuyển giữa các AI/model mà không mất mạch. Cập nhật khi chuẩn bị đổi model hoặc dừng giữa việc dài.\n\n"
               "- **Mục tiêu:**\n- **Đã hoàn thành:**\n- **Đang làm:**\n- **Quyết định đã chốt:**\n"
               "- **Chưa xác minh:**\n- **Bước tiếp theo:**\n- **File liên quan:**\n"),
        "en": ("---\ntype: session-handoff\nstatus: clear\nupdated:\n---\n\n"
               "# Session Handoff\n\n"
               "Current session state, so work can move between AIs/models without losing the thread. Update it before switching models or pausing a long job.\n\n"
               "- **Goal:**\n- **Done:**\n- **In progress:**\n- **Decisions made:**\n"
               "- **Not yet verified:**\n- **Next step:**\n- **Related files:**\n"),
    },
}

# Dòng giữ chỗ của chỉ mục bộ nhớ ở MỌI ngôn ngữ. learn.py thay dòng này bằng ký ức đầu tiên,
# nên nó phải nhận ra cả bản tiếng Anh, không thì brain tiếng Anh giữ dòng "No memories yet"
# mãi bên cạnh các ký ức thật.
GIU_CHO_BO_NHO = re.compile(r"_\((?:Chưa có ký ức|No memories yet).*?\)_", re.DOTALL)

_TEN_THEO_VI = {ban["vi"]: ten for ten, ban in HAT_GIONG.items()}


def _ma(ma: str | None = None) -> str:
    return lang_registry.chuan_hoa(ma or "") or localefmt.ngon_ngu_giao_dien()


def ban(ten: str, ma: str | None = None) -> str:
    """Bản của hạt giống `ten` cho ngôn ngữ `ma` (mặc định: ngôn ngữ giao diện hiện tại)."""
    return lang_registry.chon_ban_dich(_ma(ma), HAT_GIONG[ten])


def chon(goc: str, ma: str | None = None) -> str:
    """Nhận đúng hằng số hạt giống tiếng Việt, trả bản theo ngôn ngữ. Chuỗi lạ trả nguyên văn,
    nên gọi bọc quanh một hằng số chưa được đăng ký ở đây là vô hại."""
    ten = _TEN_THEO_VI.get(goc)
    return ban(ten, ma) if ten else goc


def _thu_muc_con(root: Path, mau: str, mac_dinh: str) -> Path:
    try:
        for p in sorted(root.iterdir()):
            if p.is_dir() and re.match(mau, p.name, re.I):
                return p
    except OSError:
        pass
    return root / mac_dinh


def _vi_tri(root: Path) -> dict:
    wiki = _thu_muc_con(root, r"^(\d+\s*[-_.]\s*)?wiki$", "wiki")
    return {
        "dashboard": _thu_muc_con(root, r"^(\d+\s*[-_.]\s*)?dashboard$", "00 - Dashboard") / "Dashboard.md",
        "memory": root / "memory" / "MEMORY.md",
        "javis_readme": root / "Javis" / "README.md",
        "wiki_index": wiki / "index.md",
        "wiki_log": wiki / "log.md",
        "open_questions": wiki / "_open-questions.md",
        "session_handoff": wiki / "_session-handoff.md",
    }


def doi_ngon_ngu(root, ma: str) -> list:
    """Viết lại các file hạt giống CÒN NGUYÊN của brain `root` sang ngôn ngữ `ma`.

    "Còn nguyên" = nội dung đúng y một bản hạt giống của bất kỳ ngôn ngữ nào. Trả về danh sách
    tên hạt giống đã đổi. Không ném lỗi: đây là việc phụ chạy lúc lưu cài đặt."""
    ma = lang_registry.chuan_hoa(ma or "")
    if not ma:
        return []
    doi = []
    for ten, p in _vi_tri(Path(root)).items():
        try:
            if not p.is_file():
                continue
            hien = p.read_text(encoding="utf-8")
            if hien not in HAT_GIONG[ten].values():
                continue   # người dùng đã sửa: không đụng
            moi = ban(ten, ma)
            if moi != hien:
                p.write_text(moi, encoding="utf-8")
                doi.append(ten)
        except Exception:
            continue
    return doi
