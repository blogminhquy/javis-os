# -*- coding: utf-8 -*-
"""Bundled plugin: `javis_files`, scan drives (local, mapped, NAS) and find duplicate files, for every engine.

Version 1 is read-only on the owner's files. The work lives in server/file_scan.py; this file only turns tool calls
into scans and readable answers.

  drives      readonly  local, removable and network drives (mapped letters with their UNC path, NAS mounts)
  scan        readonly  starts a background scan, waits up to `wait` seconds, then answers with progress
  status      readonly  how the running or last scan went
  cancel      readonly  stops the running scan (it only ever read files)
  duplicates  readonly  groups of identical files from the index, biggest waste first
  stats       readonly  space by file type, heaviest folders, biggest files
  report      safe      writes the full Markdown report into the brain's exports/ folder

A finished scan that outlived its chat turn leaves a note in the bell (inbox), so the result is never lost.
Tool text sent to the model stays Vietnamese (docs/dev/them-mot-ngon-ngu.md).
"""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import file_scan as fs

OPS = ("drives", "scan", "status", "cancel", "duplicates", "stats", "report")
_KIND_VI = {"local": "ổ trong máy", "removable": "ổ rời/USB", "network": "ổ mạng/NAS", "optical": "ổ đĩa quang",
            "ramdisk": "ổ RAM", "unknown": "không rõ"}
_CAT_VI = {"image": "Ảnh", "video": "Video", "audio": "Âm thanh", "document": "Tài liệu", "archive": "File nén",
           "installer": "File cài đặt", "code": "Mã nguồn", "other": "Khác"}


def _roots(args) -> list:
    raw = args.get("roots") or args.get("root") or []
    if isinstance(raw, str):
        raw = [x for x in raw.replace("\n", ";").split(";")]
    return [str(r).strip() for r in raw if str(r or "").strip()]


def _missing_root_hint(root: str) -> str:
    if fs.is_network_path(root) or (os.name == "nt" and len(root) >= 2 and root[1] == ":"):
        return (f"ERROR: không mở được `{root}`. Nếu là ổ mạng hoặc NAS: kiểm tra NAS đang bật, máy đã đăng nhập vào "
                "thư mục chia sẻ (mở thử trong File Explorer), và nếu Javis chạy như dịch vụ nền thì ký tự ổ map (Z:) "
                "có thể không thấy được, hãy dùng đường dẫn mạng dạng \\\\ten-nas\\thu-muc. Gọi op=drives để xem ổ đang có.")
    return (f"ERROR: không mở được `{root}`. Nếu Javis chạy trong Docker, thư mục hoặc NAS phải được gắn (mount) vào "
            "container trước. Gọi op=drives để xem ổ đang có.")


def _progress_line(st: dict) -> str:
    p = st.get("progress") or {}
    phase = p.get("phase")
    if phase == "walk":
        if "files" in p:
            return f"đang liệt kê file: đã thấy {p['files']:,} file, {fs.human_size(p.get('bytes', 0))}"
        return "đang liệt kê thư mục"
    if phase == "edge":
        return f"đang so nhanh phần đầu và cuối file: {p.get('done', 0):,}/{p.get('total', 0):,}"
    if phase == "full":
        return f"đang so toàn bộ nội dung các file nghi trùng: {p.get('done', 0):,}/{p.get('total', 0):,}"
    return "đang khởi động"


def _summary_text(res: dict) -> str:
    groups = fs.duplicates(res.get("roots"))
    wasted = sum(g["wasted"] for g in groups)
    lines = [f"Quét xong {', '.join(f'`{r}`' for r in res['roots'])} trong {res.get('seconds', 0):.0f} giây: "
             f"{res['files']:,} file, {fs.human_size(res['bytes'])}.",
             f"Tìm thấy {len(groups):,} nhóm file trùng giống hệt, chiếm thừa {fs.human_size(wasted)}."]
    if res.get("errors"):
        lines.append(f"{res['errors']:,} thư mục hoặc file không đọc được (thiếu quyền hoặc mạng chập chờn).")
    for g in groups[:5]:
        lines.append(f"- {os.path.basename(g['keep'])}: {g['count']} bản, thừa {fs.human_size(g['wasted'])}")
    lines.append("Chưa di chuyển hay xoá file nào. Dùng op=duplicates để xem chi tiết, op=report để lưu báo cáo đầy đủ.")
    return "\n".join(lines)


def _notify_done(state: dict) -> None:
    """Leave the result in the bell: the chat turn that started a long scan is usually over by now."""
    try:
        import inbox
        import localefmt
        if state.get("status") == "done":
            res = state["result"]
            groups = fs.duplicates(res.get("roots"))
            wasted = sum(g["wasted"] for g in groups)
            title = localefmt.chu(f"Quét file xong: {len(groups):,} nhóm trùng, thừa {fs.human_size(wasted)}",
                                  f"File scan done: {len(groups):,} duplicate groups, {fs.human_size(wasted)} wasted")
            body = localefmt.chu(
                f"{', '.join(res['roots'])}: {res['files']:,} file, {fs.human_size(res['bytes'])}. "
                "Hỏi Javis \"xem file trùng\" hoặc \"lưu báo cáo quét file\" để xem chi tiết.",
                f"{', '.join(res['roots'])}: {res['files']:,} files, {fs.human_size(res['bytes'])}. "
                "Ask Javis \"show duplicate files\" or \"save the file scan report\" for details.")
        elif state.get("status") == "error":
            title = localefmt.chu("Quét file bị lỗi", "File scan failed")
            body = str(state.get("error") or "")
        else:
            return
        inbox.add(body, kind="report", title=title, label="javis-files", source="file-scan",
                  dedup=f"file-scan:{state.get('started')}")
    except Exception:
        pass


def register(ctx):
    async def _handle(args, cctx):
        args = args or {}
        op = str(args.get("op") or "status").strip().lower()

        if op == "drives":
            ds = await asyncio.to_thread(fs.list_drives)
            if not ds:
                return "Không liệt kê được ổ đĩa trên máy này. Hãy hỏi người dùng đường dẫn thư mục cần quét."
            lines = []
            for d in ds:
                s = f"- `{d['path']}` ({_KIND_VI.get(d['kind'], d['kind'])})"
                if d.get("unc"):
                    s += f", trỏ tới `{d['unc']}`"
                if d.get("label"):
                    s += f", tên \"{d['label']}\""
                if d.get("total"):
                    s += f", trống {fs.human_size(d.get('free', 0))}/{fs.human_size(d['total'])}"
                lines.append(s)
            return ("Các ổ đang thấy được từ máy chạy Javis:\n" + "\n".join(lines) +
                    "\nNAS chưa map thành ổ vẫn quét được bằng đường dẫn mạng dạng \\\\ten-nas\\thu-muc.")

        if op == "scan":
            roots = _roots(args)
            if not roots:
                return ("ERROR: cần roots (thư mục, ổ đĩa như E:\\, ổ mạng Z:\\ hoặc NAS \\\\ten-nas\\thu-muc). "
                        "Hỏi người dùng muốn quét chỗ nào, hoặc gọi op=drives để liệt kê.")
            for r in roots:
                if not os.path.isdir(fs.normalize_root(r)):
                    return _missing_root_hint(r)
            if fs.JOB.running():
                return "Đang có một lượt quét chạy (" + _progress_line(fs.JOB.state) + "). Đợi xong hoặc op=cancel."
            excludes = args.get("exclude") or []
            if isinstance(excludes, str):
                excludes = [x for x in excludes.split(";")]
            min_size = int(args.get("min_size_kb") or 0) * 1024 or fs.DEFAULT_MIN_SIZE
            fs.JOB.start(roots, excludes, min_size=min_size, on_done=_notify_done)
            wait = max(0.0, min(float(args.get("wait") or 45), 110.0))
            done = await asyncio.to_thread(fs.JOB.wait, wait)
            st = fs.JOB.state
            if done:
                if st["status"] == "done":
                    return _summary_text(st["result"])
                return f"ERROR: lượt quét {st['status']}: {st.get('error', '')}"
            net = any(fs.is_network_path(r) for r in st.get("roots", []))
            return (f"Lượt quét đang chạy nền ({_progress_line(st)})." +
                    (" Quét ổ mạng/NAS chậm hơn ổ trong máy vì mọi file nghi trùng phải đọc qua mạng." if net else "") +
                    " Khi xong, kết quả nằm trong chuông thông báo; người dùng cũng có thể hỏi lại để xem. "
                    "Nói đúng như vậy, KHÔNG hứa tự báo trong khung chat này.")

        if op == "status":
            st = fs.JOB.state
            if st.get("status") == "running":
                mins = (time.time() - st.get("started", time.time())) / 60
                return f"Đang quét {', '.join(st['roots'])} được {mins:.0f} phút: {_progress_line(st)}."
            if st.get("status") == "done":
                return _summary_text(st["result"])
            if st.get("status") in ("error", "cancelled"):
                return f"Lượt quét gần nhất: {st['status']} {st.get('error', '')}".strip()
            idx = await asyncio.to_thread(fs.stats, None, 1)
            if not idx["roots"]:
                return "Chưa quét lần nào. Dùng op=scan với roots."
            return "Chưa có lượt quét nào trong phiên này. Đã có chỉ mục của: " + ", ".join(
                f"`{r['root']}` ({time.strftime('%Y-%m-%d %H:%M', time.localtime(r['scanned_at']))})" for r in idx["roots"])

        if op == "cancel":
            return "Đã dừng lượt quét." if fs.JOB.cancel() else "Không có lượt quét nào đang chạy."

        roots = _roots(args) or None
        if op == "duplicates":
            limit = max(1, min(int(args.get("limit") or 20), 100))
            min_size = int(args.get("min_size_kb") or 0) * 1024 or fs.DEFAULT_MIN_SIZE
            groups = await asyncio.to_thread(fs.duplicates, roots, min_size)
            if not groups:
                return "Không có file trùng nào trong chỉ mục (hoặc chưa quét: dùng op=scan)."
            wasted = sum(g["wasted"] for g in groups)
            out = [f"{len(groups):,} nhóm file trùng giống hệt, chiếm thừa {fs.human_size(wasted)}. "
                   f"{min(limit, len(groups))} nhóm lớn nhất (bản đề xuất giữ là bản cũ nhất):"]
            for i, g in enumerate(groups[:limit], 1):
                out.append(f"{i}. {g['count']} bản x {fs.human_size(g['size'])}, thừa {fs.human_size(g['wasted'])}")
                out.append(f"   giữ: {g['keep']}")
                for c in g["copies"][:10]:
                    out.append(f"   trùng: {c}")
                if len(g["copies"]) > 10:
                    out.append(f"   ... và {len(g['copies']) - 10} bản nữa")
            out.append("Phiên bản này CHỈ ĐỌC: không có lệnh xoá. Nếu người dùng muốn dọn, hướng dẫn họ tự kiểm tra rồi xoá.")
            return "\n".join(out)

        if op == "stats":
            st = await asyncio.to_thread(fs.stats, roots, 10)
            if not st["files"]:
                return "Chỉ mục trống. Dùng op=scan trước."
            out = [f"Tổng {st['files']:,} file, {fs.human_size(st['bytes'])}."]
            out.append("Theo loại: " + "; ".join(
                f"{_CAT_VI.get(c['category'], c['category'])} {fs.human_size(c['bytes'])} ({c['files']:,})"
                for c in st["categories"]))
            out.append("Thư mục nặng nhất:")
            out += [f"- {f['path']}: {fs.human_size(f['bytes'])}" for f in st["folders"]]
            out.append("File lớn nhất:")
            out += [f"- {b['path']}: {fs.human_size(b['size'])}" for b in st["biggest"]]
            if st["offline"]:
                out.append(f"{st['offline']:,} file chỉ có trên đám mây, không so nội dung.")
            return "\n".join(out)

        if op == "report":
            if not ctx.vault_root:
                return "ERROR: không có brain nào để lưu báo cáo."
            md = await asyncio.to_thread(fs.report_markdown, roots)
            folder = Path(ctx.vault_root) / "exports"
            folder.mkdir(parents=True, exist_ok=True)
            name = f"bao-cao-quet-file-{time.strftime('%Y-%m-%d-%H%M')}.md"
            (folder / name).write_text(md, encoding="utf-8")
            return (f"Đã lưu báo cáo: exports/{name}. Gửi người dùng link [{name}](exports/{name}) để mở. "
                    "Báo cáo chỉ liệt kê, chưa đụng tới file nào.")

        return "ERROR: op phải là một trong " + ", ".join(OPS) + "."

    ctx.register_tool(
        name="javis_files",
        description=(
            "Quét file trên máy chạy Javis: ổ trong máy, USB, ổ mạng map (Z:\\) hoặc NAS (\\\\ten-nas\\thu-muc, hoặc "
            "thư mục đã mount trên Linux/macOS); tìm file TRÙNG GIỐNG HỆT (so dung lượng, rồi băm đầu cuối, rồi băm toàn "
            "bộ), thống kê dung lượng theo loại và thư mục. CHỈ ĐỌC: không di chuyển, không xoá. "
            "op=drives (liệt kê ổ, gồm ổ mạng), op=scan (roots=[...], exclude=[...], min_size_kb, wait giây; chạy nền, "
            "lần sau chỉ băm file đã đổi), op=status, op=cancel, op=duplicates (limit, roots để lọc), op=stats, "
            "op=report (lưu báo cáo Markdown vào exports/ của brain). Chưa rõ quét chỗ nào thì hỏi người dùng."),
        handler=_handle, min_mode="readonly", emoji="🗂️",
        op_modes={"drives": "readonly", "scan": "readonly", "status": "readonly", "cancel": "readonly",
                  "duplicates": "readonly", "stats": "readonly", "report": "safe"},
        schema={"type": "object", "properties": {
            "op": {"type": "string", "enum": list(OPS)},
            "roots": {"type": "array", "items": {"type": "string"},
                      "description": "Thư mục hoặc ổ cần quét / lọc, vd [\"E:\\\\\", \"Z:\\\\Ảnh\", \"\\\\\\\\nas\\\\share\"]"},
            "exclude": {"type": "array", "items": {"type": "string"}, "description": "Thư mục bỏ qua"},
            "min_size_kb": {"type": "integer", "description": "Bỏ qua file nhỏ hơn (KB) khi tìm trùng"},
            "wait": {"type": "number", "description": "Số giây chờ lượt quét (mặc định 45, tối đa 110)"},
            "limit": {"type": "integer", "description": "Số nhóm trùng trả về (mặc định 20)"}},
            "required": ["op"]},
    )
