"""Frozen legacy attachment templates plus actual main scratch-file parity."""
from _paths import ROOT, SERVER  # noqa: F401
import ast
import importlib.util
import os
import tempfile
import unittest
import weakref
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRATCH = Path(tempfile.mkdtemp(prefix="main-attachments-"))
for key, child in {"JAVIS_STATE_DIR": "state", "BRAINS_DIR": "brains", "OBSIDIAN_VAULT_PATH": "vault",
                   "BRAIN_PATH": "brain", "SOURCES_PATH": "sources", "JAVIS_SESSIONS_DB": "sessions.sqlite3"}.items():
    os.environ[key] = str(SCRATCH / child)

import main

if importlib.util.find_spec("main_attachment_rendering"):
    import main_attachment_rendering as R
else:
    R = None

# Literal production source frozen before extraction, independent of the new module.
LEGACY_SOURCE = r'''
def _project_block(project_id: str, chi_huong_dan: bool = False) -> str:
    """Khối hướng dẫn + tài liệu của project, để ghép vào system prompt. "" nếu không có gì.

    `chi_huong_dan=True`: CHỈ lấy phần hướng dẫn, bỏ danh sách tài liệu. Dùng cho đường tiết
    kiệm (Phase 8). Vì sao tách đôi chứ không bỏ cả khối như spec đề nghị: hướng dẫn là HỢP
    ĐỒNG HÀNH XỬ ("luôn trả lời bằng tiếng Anh", "tránh màu xanh dương"), còn danh sách tài
    liệu là dữ liệu TRA CỨU. Bỏ dữ liệu tra cứu lúc siết ngân sách thì model cùng lắm phải hỏi
    lại; bỏ hợp đồng hành xử thì cùng một project, cùng một câu hỏi, lượt này tuân luật lượt
    kia không - và người dùng không có cách nào biết vì sao, chỉ thấy Javis bướng.

    GHIM FILE = NẠP NỘI DUNG. Spec ban đầu chỉ liệt kê tên và thêm chữ "(ghim)", tức là ghim
    chỉ đổi thứ tự danh sách. Nhưng người dùng ghim bảng giá vào project thì họ nghĩ Javis đã
    BIẾT bảng giá, chứ không phải biết TÊN nó. Nạp nội dung mới làm cái nút ghim thành công
    tắc thật, và trần ở trên để chính họ cầm cán cân token.
    """
    try:
        p = get_store().get_project_full(project_id)
    except Exception:
        return ""
    if not p:
        return ""
    ra = main_prompt_rendering.render_project_instructions(
        p.get("name") or "", p.get("instructions") or "", instructions_max=sessions.PROJECT_INSTRUCTIONS_MAX)
    if chi_huong_dan:
        return ra

    files = p.get("files") or []
    links = p.get("links") or []
    if not files and not links:
        return ra

    dong, da_nap = _liet_ke_tai_lieu(p.get("brain") or "brain", files, links)
    if dong:
        ra += ("\n\n# === TÀI LIỆU & LINK CỦA PROJECT (project documents and links) ===\n"
               "This is a LIST, not the content: open a file with a file-reading tool when needed; "
               "do not guess its content from its name. A link opens only if this turn has a web-browsing tool; "
               "without one, say so plainly instead of guessing the page.\n" + "\n".join(dong))
    if da_nap:
        ra += ("\n\n# === NỘI DUNG FILE ĐÃ GHIM (pinned file content, preloaded: no need to open it again) ===" + "".join(da_nap))
    return ra

def _liet_ke_tai_lieu(brain: str, files: list, links: list):
    """(dòng liệt kê, nội dung file đã ghim) cho một danh sách tài liệu + link.

    Tách khỏi `_project_block` vì khung "file & link của CUỘC TRÒ CHUYỆN" gắn tay dùng lại
    nguyên bộ luật này. Hai chỗ mà chép đôi thì trần token trôi lệch, và trần token trôi lệch
    là kiểu hỏng không ai thấy cho tới lúc hoá đơn hoặc lỗi quá hạn mức xuất hiện.
    """
    dong, da_nap, con_lai = [], [], PROJECT_GHIM_TONG_MAX
    for f in files[:PROJECT_FILES_LIET_KE]:
        ten, duong = f.get("name") or "", f.get("path") or ""
        if not f.get("pinned"):
            dong.append(f"- [file] {ten} - {duong}")
            continue
        duoi = os.path.splitext(duong)[1].lower()
        if duoi not in PROJECT_GHIM_DUOI:
            # Nói THẲNG là ghim nhưng không nạp được, kèm lý do. Im lặng bỏ qua thì người dùng
            # ghim xong tưởng Javis đã đọc, rồi ngạc nhiên vì nó trả lời như chưa thấy gì.
            dong.append(f"- [file, pinned but binary - open it yourself when needed] {ten} - {duong}")
            continue
        try:
            # `_safe_serve_path` chứ không phải `_safe_path`: đây là đường ĐỌC, và trần duyệt
            # có thể nằm CAO hơn gốc brain (vd localhost duyệt tới cả ổ đĩa). Lúc đó một đường
            # dẫn lưu theo gốc brain sẽ không resolve được từ trần, và ngược lại - hàm serve
            # thử cả hai quy ước, cả hai đều bị khoá trong trần. Nhánh THÊM file thì vẫn dùng
            # `_safe_path` (chặt hơn): ở đó người dùng chọn từ trình duyệt file nên đường dẫn
            # chắc chắn theo trần, và ghi vào kho thì phải chặt.
            noi_dung = _safe_serve_path(brain, duong).read_text(
                encoding="utf-8", errors="replace")
        except Exception:
            dong.append(f"- [file, pinned but unreadable] {ten} - {duong}")
            continue
        cat = noi_dung[:min(PROJECT_GHIM_FILE_MAX, max(0, con_lai))]
        if not cat:
            dong.append(f"- [file, pinned but no room left to load it this turn] {ten} - {duong}")
            continue
        con_lai -= len(cat)
        thieu = " (clipped)" if len(cat) < len(noi_dung) else ""
        da_nap.append(f"\n## {ten} - {duong}{thieu}\n{cat}")
    for l in links[:PROJECT_FILES_LIET_KE]:
        dong.append(f"- [link] {l.get('label') or l.get('url')} - {l.get('url')}"
                    + (" (pinned)" if l.get("pinned") else ""))
    return dong, da_nap

def _session_block(session_id: str) -> str:
    """Tài liệu & link người dùng TỰ GẮN vào CUỘC TRÒ CHUYỆN này. "" nếu chưa gắn gì.

    Song sinh với `_project_block`, và cố ý cùng trần token: project là "luôn dùng cho mọi
    cuộc trong nhóm", còn cái này là "chỉ cuộc này". Không có nó thì nút thêm file chỉ là một
    danh sách để ngắm - người dùng gắn bảng giá vào cuộc rồi hỏi ngay, và Javis trả lời như
    chưa hề thấy gì.

    Ghim thì NẠP NỘI DUNG, y như project: gắn tên vào cho biết chỗ mà tìm, ghim vào là bảo
    Javis đọc sẵn.
    """
    if not session_id:
        return ""
    try:
        store = get_store()
        sess = store.get_session(session_id)
        if not sess:
            return ""
        files = store.list_session_files(session_id)
        links = store.list_session_links(session_id)
    except Exception:
        return ""
    if not files and not links:
        return ""
    dong, da_nap = _liet_ke_tai_lieu(sess.get("brain") or "brain", files, links)
    ra = ""
    if dong:
        ra += ("\n\n# === TÀI LIỆU & LINK NGƯỜI DÙNG GẮN VÀO CUỘC NÀY (documents and links the user attached to this chat) ===\n"
               "The user attached these by hand in the \"In this conversation\" panel, so they "
               "matter to THIS chat. Still a LIST, not the content: "
               "open a file with a file-reading tool when needed; do not guess its content from its name.\n"
               + "\n".join(dong))
    if da_nap:
        ra += ("\n\n# === NỘI DUNG FILE ĐÃ GHIM TRONG CUỘC NÀY (pinned file content of this chat, preloaded: no need to open it again) ==="
               + "".join(da_nap))
    return ra
'''


class AttachmentRenderingTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(R, "Pure shared attachment rendering is missing")
        self.limits = dict(list_max=15, allowed_suffixes=main.PROJECT_GHIM_DUOI, file_max=2000, total_max=6000)

    def legacy(self, files, links, loaded, *, reader=None, store=None):
        queues = {}
        for item, text in zip(files[:15], loaded):
            if item.get("pinned") and os.path.splitext(item.get("path") or "")[1].lower() in main.PROJECT_GHIM_DUOI:
                queues.setdefault(item.get("path") or "", []).append(text)
        calls = []

        def read_path(brain, path):
            calls.append(path)
            value = queues[path].pop(0)
            def read_text(**kwargs):
                self.assertEqual(kwargs, {"encoding": "utf-8", "errors": "replace"})
                if value is None:
                    raise OSError("synthetic unavailable")
                return value
            return SimpleNamespace(read_text=read_text)

        namespace = dict(os=os, PROJECT_FILES_LIET_KE=15, PROJECT_GHIM_FILE_MAX=2000,
                         PROJECT_GHIM_TONG_MAX=6000, PROJECT_GHIM_DUOI=main.PROJECT_GHIM_DUOI,
                         _safe_serve_path=reader or read_path, get_store=lambda: store,
                         main_prompt_rendering=main.main_prompt_rendering, sessions=main.sessions)
        exec(LEGACY_SOURCE, namespace)
        return namespace, calls

    def assert_legacy_lists(self, files, links, loaded):
        namespace, _ = self.legacy(files, links, loaded)
        self.assertEqual(R.render_attachment_lists(files, links, loaded, **self.limits),
                         namespace["_liet_ke_tai_lieu"]("brain", files, links))

    def test_empty_and_links_only_keep_exact_legacy_output(self):
        self.assert_legacy_lists([], [], [])
        self.assert_legacy_lists([], [{"url": "https://example.test", "label": "Reference", "pinned": 1},
                                     {"url": "https://other.test", "label": "", "pinned": 0}], [])

    def test_binary_unreadable_empty_unpinned_and_uppercase_suffix_keep_status_messages(self):
        files = [{"name": "Unpinned", "path": "a.md", "pinned": 0},
                 {"name": "Binary", "path": "b.pdf", "pinned": 1},
                 {"name": "Unavailable", "path": "c.txt", "pinned": 1},
                 {"name": "Empty", "path": "d.md", "pinned": 1},
                 {"name": "Text", "path": "e.TXT", "pinned": 1}]
        self.assert_legacy_lists(files, [], [None, None, None, "", "text\r\n"])

    def test_file_total_and_separate_listing_caps_match_frozen_legacy(self):
        files = [{"name": str(i), "path": f"{i}.md", "pinned": 1} for i in range(18)]
        links = [{"url": f"https://example.test/{i}", "pinned": i % 2} for i in range(18)]
        loaded = [str(i) * 3500 for i in range(18)]
        self.assert_legacy_lists(files, links, loaded)
        lines, sections = R.render_attachment_lists(files, links, loaded, **self.limits)
        self.assertEqual(len(sections), 3)
        self.assertTrue(all("no room left" in line for line in lines[:12]))
        self.assertEqual(len([line for line in lines if line.startswith("- [link]")]), 15)

    def test_duplicate_stored_paths_preserve_each_rows_observed_content_and_failure(self):
        files = [{"name": f"row-{i}", "path": "same.md", "pinned": 1} for i in range(4)]
        self.assert_legacy_lists(files, [], ["first observation", None, "", "later observation"])
        _, sections = R.render_attachment_lists(files, [], ["first observation", None, "", "later observation"], **self.limits)
        self.assertEqual(sections, ["\n## row-0 - same.md\nfirst observation", "\n## row-3 - same.md\nlater observation"])

    def test_full_protected_preserves_every_pinned_text_byte_and_all_metadata_beyond_caps(self):
        files = [{"name": str(i), "path": f"{i}.md", "pinned": 1} for i in range(20)]
        files.append({"name": "Unpinned", "path": "last.md", "pinned": 0})
        links = [{"url": f"https://example.test/{i}"} for i in range(20)]
        loaded = [" \r\n" + str(i) * 7000 + "\r\n " for i in range(20)] + [None]
        lines, sections = R.render_attachment_lists(files, links, loaded, list_max=1,
            allowed_suffixes=main.PROJECT_GHIM_DUOI, file_max=1, total_max=1, preserve_full_protected=True)
        self.assertEqual(len(sections), 20)
        for i, section in enumerate(sections):
            self.assertEqual(section, f"\n## {i} - {i}.md\n" + loaded[i])
        self.assertEqual(len(lines), 21)
        self.assertIn("- [file] Unpinned - last.md", lines)
        self.assertFalse(any("(clipped)" in section for section in sections))

    def test_full_protected_empty_source_is_known_empty_without_budget_message(self):
        files = [{"name": "Empty", "path": "empty.md", "pinned": 1}]
        self.assertEqual(R.render_attachment_lists(files, [], [""], **self.limits, preserve_full_protected=True),
                         ([], ["\n## Empty - empty.md\n"]))

    def test_full_protected_binary_and_missing_remain_explicit_for_host_rejection(self):
        files = [{"name": "Binary", "path": "x.pdf", "pinned": 1},
                 {"name": "Missing", "path": "x.txt", "pinned": 1}]
        self.assertEqual(R.render_attachment_lists(files, [], [None, None], **self.limits, preserve_full_protected=True),
                         R.render_attachment_lists(files, [], [None, None], **self.limits))

    def test_actual_main_project_and_session_blocks_match_frozen_scratch_file_oracle(self):
        root = Path(tempfile.mkdtemp(dir=SCRATCH))
        files = []
        for i in range(19):
            path = f"{i}.txt"
            (root / path).write_bytes((" \r\n" + str(i) * 3500 + "\r\n ").encode("utf-8"))
            files.append({"name": f"Document {i}", "path": path, "pinned": 1})
        (root / "bad.txt").write_bytes(b"invalid:\xff\r\n")
        files[1] = {"name": "Invalid UTF-8", "path": "bad.txt", "pinned": 1}
        files[2] = {"name": "Unavailable", "path": "missing.txt", "pinned": 1}
        links = [{"url": "https://example.test", "label": "Reference", "pinned": 1}]
        project = {"name": "Owner Project", "instructions": " Preserve rule.\r\n ", "brain": "brain", "files": files, "links": links}
        store = SimpleNamespace(get_project_full=lambda identifier: project,
                                get_session=lambda identifier: {"brain": "brain"},
                                list_session_files=lambda identifier: files, list_session_links=lambda identifier: links)
        reader = lambda brain, relative: root / relative
        namespace, _ = self.legacy(files, links, [], reader=reader, store=store)
        with patch.object(main, "get_store", return_value=store), patch.object(main, "_safe_serve_path", side_effect=reader):
            self.assertEqual(main._project_block("project"), namespace["_project_block"]("project"))
            self.assertEqual(main._session_block("session"), namespace["_session_block"]("session"))
            self.assertEqual(main._project_block("project", True), namespace["_project_block"]("project", True))

    def test_actual_main_reads_every_legacy_row_in_order_even_after_budget_is_spent(self):
        files = [{"name": str(i), "path": "same.md" if i < 3 else f"{i}.md", "pinned": 1} for i in range(18)]
        calls = []
        def read_path(brain, path):
            calls.append(path)
            return SimpleNamespace(read_text=lambda **kwargs: str(len(calls)) * 3500)
        namespace, _ = self.legacy(files, [], [], reader=read_path)
        expected = namespace["_liet_ke_tai_lieu"]("brain", files, [])
        expected_calls = calls[:]
        calls.clear()
        with patch.object(main, "_safe_serve_path", side_effect=read_path):
            actual = main._liet_ke_tai_lieu("brain", files, [])
        self.assertEqual(actual, expected)
        self.assertEqual(calls, expected_calls)
        self.assertEqual(len(calls), 15)

    def test_actual_main_does_not_retain_all_large_raw_sources_until_rendering(self):
        class TrackedText(str):
            pass

        files = [{"name": str(i), "path": f"{i}.md", "pinned": 1} for i in range(15)]
        references, peaks = [], []

        def read_path(brain, path):
            def read_text(**kwargs):
                value = TrackedText(path + "x" * 100000)
                references.append(weakref.ref(value))
                peaks.append(sum(reference() is not None for reference in references))
                return value
            return SimpleNamespace(read_text=read_text)

        namespace, _ = self.legacy(files, [], [], reader=read_path)
        expected = namespace["_liet_ke_tai_lieu"]("brain", files, [])
        self.assertLessEqual(max(peaks), 2)
        references.clear()
        peaks.clear()
        with patch.object(main, "_safe_serve_path", side_effect=read_path):
            actual = main._liet_ke_tai_lieu("brain", files, [])
        self.assertEqual(actual, expected)
        self.assertLessEqual(max(peaks), 2, "Ordinary rendering retained every complete raw source")

    def test_prepared_prefix_retains_original_clipping_and_cannot_claim_full_protected_source(self):
        self.assertTrue(hasattr(R, "PreparedAttachmentText"), "Bounded ordinary attachment DTO is missing")
        files = [{"name": "Large", "path": "large.md", "pinned": 1}]
        prepared = R.PreparedAttachmentText("x" * 2000, 100000)
        self.assertEqual(R.render_attachment_lists(files, [], [prepared], **self.limits),
                         R.render_attachment_lists(files, [], ["x" * 100000], **self.limits))
        with self.assertRaisesRegex(ValueError, "full"):
            R.render_attachment_lists(files, [], [prepared], **self.limits, preserve_full_protected=True)

    def test_project_session_headers_match_frozen_templates_for_each_nonempty_part(self):
        for lines, sections in (([], []), (["line"], []), ([], ["\nsection"]), (["line"], ["\nsection"])):
            project = {"name": "", "instructions": "", "files": [1], "links": []}
            store = SimpleNamespace(get_project_full=lambda identifier: project, get_session=lambda identifier: {},
                                    list_session_files=lambda identifier: [1], list_session_links=lambda identifier: [])
            namespace, _ = self.legacy([], [], [], store=store)
            namespace["_liet_ke_tai_lieu"] = lambda *args: (lines, sections)
            # Empty session records are false; the production path needs a real brain field.
            store.get_session = lambda identifier: {"brain": "brain"}
            self.assertEqual(R.render_project_assets(lines, sections), namespace["_project_block"]("project"))
            self.assertEqual(R.render_session_assets(lines, sections), namespace["_session_block"]("session"))

    def test_pure_module_has_no_io_runtime_or_callback_dependencies(self):
        tree = ast.parse(Path(R.__file__).read_text(encoding="utf-8"))
        imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        imported |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
        self.assertFalse(imported - {"__future__", "os", "dataclasses"})
        with patch("builtins.open", side_effect=AssertionError("unexpected I/O")):
            lines, sections = R.render_attachment_lists([{"path": "x.md", "pinned": 1}], [], ["raw"], **self.limits)
            self.assertIn("raw", R.render_project_assets(lines, sections))
            self.assertIn("raw", R.render_session_assets(lines, sections))


if __name__ == "__main__":
    unittest.main()
