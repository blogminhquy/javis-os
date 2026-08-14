"""
meta_tools.py - Bộ khung "compounding wiki" phổ quát, seed vào mỗi brain (create-if-missing).

Gồm: schema doc (CLAUDE.md + AGENTS.md ở gốc brain, để Claude Code lẫn Codex tự nạp) + file
điều hướng wiki (index / log / _open-questions / _session-handoff). Đây là tài liệu SỐNG -
người dùng + AI cùng tiến hoá sau khi seed, nên CHỈ tạo khi thiếu, update app KHÔNG ghi đè.

LƯU Ý KIẾN TRÚC: các NĂNG LỰC hệ thống (skill javis-builder / ingest-source / query-wiki /
lint-wiki + loop tự-cải-tiến) KHÔNG còn nằm ở đây. Chúng thuộc tầng app - nguồn chuẩn ở
<project>/.claude/skills và <project>/system/loops, đồng bộ vào brain qua system_sync.py
(có manifest, update theo phiên bản, tôn trọng bản user đã sửa). Xem server/system_sync.py.

Quy tắc làm-rõ-prompt nằm ở CLAUDE.md (system prompt) - rẻ, áp mọi lượt chat.
"""
from __future__ import annotations

from pathlib import Path


# ── SCHEMA phổ quát cho vault (seed thành CLAUDE.md + AGENTS.md để Claude Code lẫn Codex tự nạp) ──
# Trung lập ngành: KHÔNG có folder marketing/sales... hay Bullet Journal. Chỉ giữ pattern LLM Wiki
# (compounding) + 3 kỷ luật chống bịa + 3 phép toán + HANDOFF. Taxonomy mọc dần theo source người dùng.
_VAULT_SCHEMA = """# Vault Schema (Javis Second Brain)

> AI làm việc trên vault này PHẢI đọc file này trước. Mục tiêu: biến vault thành một **wiki
> tích luỹ (compounding)** - tri thức được chưng cất MỘT LẦN từ nguồn rồi DUY TRÌ sống, không
> RAG lại mỗi câu hỏi. Vault tiến hoá dần theo người dùng; taxonomy tự mọc theo nội dung thật.

## 1. Ba lớp (phân quyền rõ)

| Lớp | Thư mục | Ai sửa | Tính chất |
|---|---|---|---|
| Nguồn thô | `sources/` | Người dùng | BẤT BIẾN với AI - chỉ đọc, không sửa nội dung (được đổi tên/thêm frontmatter). Source of truth. |
| Wiki | `wiki/` | AI | AI toàn quyền tạo/cập nhật/merge/archive. Người đọc và định hướng. |
| Schema | `CLAUDE.md` / `AGENTS.md` | Người + AI cùng tiến hoá | Quy ước; chỉnh khi workflow đổi. |
| Bộ nhớ | `memory/` | AI | Ký ức dài hạn về người dùng (facts + MEMORY.md index + conversations). |
| Vận hành | `agents/`, `workflows/`, `skills/` (mirror `.claude/skills`) | AI + người | Agent, workflow, kỹ năng. |

Nguyên lý: Sources -> (INGEST) -> Wiki. Tri thức TÍCH LUỸ, không tái phát hiện.

## 2. Đặt tên & wikilink
- Wiki: tên khái niệm rõ ràng (vd `Nguyên Lý Pareto.md`). Liên kết bằng `[[Tên Wiki]]`.
- Tên trùng giữa các folder -> dùng path `[[nhóm/Tên]]`. Khi 2 thực thể trùng tên -> hỏi người dùng trước khi tạo trang mới.
- Trong chat: ưu tiên `[[wikilink]]` để người dùng click mở.

## 3. Ba kỷ luật chống Wiki rỗng/sai (BẮT BUỘC)
1. **Citation trong thân bài.** Mọi khẳng định cụ thể (số liệu/quy trình/framework/trích dẫn) phải kèm `[[Nguồn]]` cuối câu/đoạn. Không nguồn = câu đáng ngờ, dễ bịa.
2. **Phân biệt mục tiêu vs thực tế.** Câu nói về tương lai/mong muốn -> ghi rõ "mục tiêu/kế hoạch". Câu về hiện trạng đo được -> ghi rõ "thực tế tính đến [thời điểm]". Không chắc -> trích nguyên văn + "(cần xác minh)" thay vì viết thành claim chắc nịch.
3. **Mâu thuẫn giữ rõ, không ghi đè.** Source mới mâu thuẫn Wiki cũ -> KHÔNG xoá cái cũ. Thêm section `## Mâu thuẫn` (ghi cả 2 quan điểm + nguồn) và append 1 dòng vào `wiki/_open-questions.md`. Người dùng quyết định hợp nhất.

## 4. Ba phép toán
### INGEST - tiêu hoá 1 source
Kiểm frontmatter source: `status: processed` -> DỪNG, hỏi re-ingest. `unprocessed`/chưa có -> làm.
- Source dài (>= ~10.000 dòng / sách / transcript) -> 3-pass: (1) đọc lướt lập mục lục theo dòng, (2) đọc sâu từng đoạn ~1.000-1.500 dòng và viết Wiki ngay từng đoạn (đừng nén cả file 1 lần), (3) tự hỏi 5 câu kiểm độ phủ, thiếu thì quét bổ sung.
- Các bước: đọc (kèm ảnh nếu có) -> tóm tắt 3-5 ý -> rút insight/framework -> xác định trang Wiki mới/cập nhật/merge -> viết Wiki (1 trang = 1 ý, có `[[...]]` ngược) -> cập nhật `wiki/index.md` -> set source `status: processed` + `wiki_links` -> append `wiki/log.md` -> đề xuất task nếu có (không tự thêm). Báo cáo ngắn.

### QUERY - trả lời câu hỏi
Đọc `wiki/index.md` trước -> đọc trang liên quan -> thiếu thì đọc `sources/` -> vẫn thiếu thì append `wiki/_open-questions.md`. Trả lời có `[[citation]]`. Câu trả lời giá trị tái dùng -> đề xuất lưu thành trang Wiki mới (compounding).

### LINT - health-check định kỳ (chỉ trả CHECKLIST, KHÔNG tự sửa 50 chỗ)
Quét `wiki/`: mâu thuẫn, claim cũ, orphan (không inbound link), khái niệm thiếu trang riêng, broken `[[link]]`, trùng lặp nên merge, vùng mỏng cần thêm source, open-question tồn lâu. Báo cáo -> người dùng chọn sửa từng cái.

## 5. Điều hướng
- `wiki/index.md` - catalog nội dung (link + mô tả 1 dòng), cập nhật mỗi INGEST. Đọc file này TRƯỚC khi QUERY.
- `wiki/log.md` - nhật ký thời gian, append-only, mỗi entry mở đầu `## [YYYY-MM-DD] loại | tiêu đề`.
- `wiki/_open-questions.md` - câu hỏi Wiki chưa trả lời đủ.
- `wiki/_session-handoff.md` - trạng thái phiên hiện hành để CHUYỂN GIỮA CÁC MODEL/AI (Claude <-> Codex...) không mất mạch. Ghi: mục tiêu, đã xong, đang làm, quyết định, chưa xác minh, bước tiếp, file liên quan. Khi xong đặt `status: clear`. AI nhận bàn giao đọc: schema -> handoff -> file liên kết.

## 6. Frontmatter
Wiki: `type: wiki`, `status: active|draft|archived`, `tags: [wiki, <nhóm>]`, `created`, `updated`, `source: [[...]]`.
Source: `type: source`, `source_kind: article|book|podcast|video|own-note|screenshot|chat`, `status: unprocessed|processed`, `created`, `processed_at`, `wiki_links: [...]`, `url`.

## 7. Chỉ mục năng lực
- `Javis/index.md` - chỉ mục MỌI năng lực (agents/skills/workflows/loops/lịch), tự sinh từ file (đừng sửa tay). Đọc file này để biết Javis đang có gì; kiểm TRƯỚC khi tạo năng lực mới để khỏi trùng. Song song `wiki/index.md` (tri thức).

## 8. Tiến hoá theo người dùng
- Nhóm chủ đề trong `wiki/` MỌC DẦN theo source thực tế (tạo subfolder khi một chủ đề đủ dày), không định sẵn theo ngành.
- Cần bộ khung sẵn (vd Bullet Journal, nghiên cứu, đọc sách) -> người dùng áp "gói mẫu" (opt-in), không seed mặc định.
- Viết bằng ngôn ngữ ghi ở khối `# === NGÔN NGỮ ===` của prompt (mặc định tiếng Việt); code/tag/frontmatter key luôn dùng tiếng Anh. Tone thực tế, ngắn gọn. KHÔNG dùng ký tự em dash.
"""

_WIKI_INDEX = """# Wiki Index

Catalog nội dung wiki (cập nhật mỗi lần INGEST). Đọc file này trước khi trả lời câu hỏi.

_(Chưa có trang wiki nào. Thả source vào `sources/` rồi bảo Javis "tiêu hoá giúp tôi" để bắt đầu tích luỹ tri thức.)_
"""

_WIKI_LOG = """# Wiki Log

Nhật ký thời gian (append-only). Mỗi entry: `## [YYYY-MM-DD] loại | tiêu đề` (loại: init/ingest/update/query/lint/migrate).
"""

_OPEN_QUESTIONS = """# Open Questions

Câu hỏi wiki chưa trả lời đủ. Format mỗi dòng:
- [ ] (YYYY-MM-DD) [[Chủ đề]]: câu hỏi/khoảng trống - status: open
"""

_SESSION_HANDOFF = """---
type: session-handoff
status: clear
updated:
---

# Session Handoff

Trạng thái phiên hiện hành để chuyển giữa các AI/model mà không mất mạch. Cập nhật khi chuẩn bị đổi model hoặc dừng giữa việc dài.

- **Mục tiêu:**
- **Đã hoàn thành:**
- **Đang làm:**
- **Quyết định đã chốt:**
- **Chưa xác minh:**
- **Bước tiếp theo:**
- **File liên quan:**
"""


def ensure_brain_pattern(root: str, wiki_dir: str = "") -> dict:
    """Seed bộ khung 'compounding wiki' phổ quát vào brain (create-if-missing):
    schema doc (CLAUDE.md + AGENTS.md ở gốc, để Claude Code + Codex tự nạp) + file điều hướng
    wiki (index/log/_open-questions/_session-handoff). wiki_dir: thư mục wiki đã resolve
    (vd 'wiki' hoặc '07 - Wiki'); rỗng -> mặc định <root>/wiki."""
    root = Path(root)
    created = []
    for fname in ("CLAUDE.md", "AGENTS.md"):
        try:
            fp = root / fname
            if not fp.exists():
                fp.write_text(_VAULT_SCHEMA, encoding="utf-8")
                created.append(f"schema:{fname}")
        except Exception as e:
            print(f"[brain pattern {fname}] {e}", file=__import__('sys').stderr)
    wd = Path(wiki_dir) if wiki_dir else (root / "wiki")
    nav = {"index.md": _WIKI_INDEX, "log.md": _WIKI_LOG,
           "_open-questions.md": _OPEN_QUESTIONS, "_session-handoff.md": _SESSION_HANDOFF}
    for fn, content in nav.items():
        try:
            fp = wd / fn
            if not fp.exists():
                fp.parent.mkdir(parents=True, exist_ok=True)
                fp.write_text(content, encoding="utf-8")
                created.append(f"wiki:{fn}")
        except Exception as e:
            print(f"[brain pattern {fn}] {e}", file=__import__('sys').stderr)
    return {"created": created}
