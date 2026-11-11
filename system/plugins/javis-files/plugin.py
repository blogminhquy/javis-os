# -*- coding: utf-8 -*-
"""Bundled plugin: `javis_files`, scan drives (local, mapped, NAS), find duplicates and look-alike photos, quarantine.

The work lives in server/file_scan.py; this file only turns tool calls into scans and readable answers. The Disk
cleanup page (dashboard/cleanup.js) shares the same index and the same background scan.

  drives      readonly  local, removable and network drives (mapped letters with their UNC path, NAS mounts)
  scan        readonly  starts a background scan, waits up to `wait` seconds, then answers with progress
  status      readonly  how the running or last scan went
  cancel      readonly  stops the running scan (it only ever read files)
  duplicates  readonly  groups of identical files from the index, biggest waste first
  stats       readonly  space by file type, heaviest folders, biggest files
  report      safe      writes the full Markdown report into the brain's exports/ folder
  similar     readonly  look-alike photo groups (needs Pillow)
  batches     readonly  quarantine batches and what is in them
  quarantine  full      MOVES chosen copies into <scanned folder>/.javis-quarantine/<batch>/ (refuses the last copy)
  restore     full      puts a quarantine batch back

There is deliberately no tool to delete for good: emptying quarantine is a button on the Disk cleanup page.

A finished scan that outlived its chat turn leaves a note in the bell (inbox), so the result is never lost.
Tool text sent to the model stays Vietnamese (docs/dev/them-mot-ngon-ngu.md).
"""
from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import file_scan as fs

OPS = ("drives", "scan", "status", "cancel", "duplicates", "stats", "report", "similar", "batches", "quarantine",
       "restore")
_REFUSED_VI = {"not_indexed": "chưa có trong chỉ mục (quét lại)", "changed": "đã thay đổi từ lần quét trước",
               "last_copy": "là bản cuối cùng, không còn bản nào khác giữ lại", "outside_root": "nằm ngoài thư mục đã quét",
               "os_error": "lỗi khi di chuyển"}
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
    if res.get("images"):
        lines.append(f"Đã lập dấu vân tay cho {res['images']:,} ảnh; op=similar để xem ảnh gần giống.")
    lines.append("Chưa di chuyển hay xoá file nào. Dùng op=duplicates để xem chi tiết, op=report để lưu báo cáo đầy đủ, "
                 "hoặc mở trang Dọn ổ đĩa để chọn và dọn.")
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
                if d.get("host"):
                    s += f", là `{d['host']}` của máy chủ Docker"
                if d.get("readonly"):
                    s += ", CHỈ ĐỌC (quét được, không dọn được)"
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
            out.append("Muốn dọn: op=quarantine với paths là các bản 'trùng' người dùng đã đồng ý (chuyển vào cách ly, "
                       "hoàn tác được), hoặc chỉ họ sang trang Dọn ổ đĩa.")
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

        if op == "similar":
            if not fs.pillow_ready():
                return "ERROR: máy chưa cài Pillow nên chưa tìm được ảnh gần giống (pip install Pillow rồi khởi động lại Javis)."
            limit = max(1, min(int(args.get("limit") or 15), 60))
            groups = await asyncio.to_thread(fs.similar, roots)
            if not groups:
                return "Không có nhóm ảnh gần giống nào (hoặc chưa quét ảnh: op=scan)."
            out = [f"{len(groups):,} nhóm ảnh gần giống (đổi cỡ, nén lại, chỉnh nhẹ). Bản đề xuất giữ là ảnh lớn nhất:"]
            for i, g in enumerate(groups[:limit], 1):
                out.append(f"{i}. {g['count']} ảnh, các bản phụ chiếm {fs.human_size(g['bytes'])}")
                for f in g["files"][:8]:
                    tag = "giữ" if f["path"] == g["keep"] else "phụ"
                    out.append(f"   {tag}: {f['path']} ({f['w']}x{f['h']}, {fs.human_size(f['size'])})")
            out.append("Ảnh gần giống KHÔNG giống hệt: chỉ dọn khi người dùng đã xem và đồng ý (op=quarantine, similar=true).")
            return "\n".join(out)

        if op == "batches":
            bs = await asyncio.to_thread(fs.batches)
            live = [b for b in bs if b["state"] == "quarantined"]
            if not bs:
                return "Chưa có lần dọn nào."
            out = [f"{len(live)} lần dọn còn file trong cách ly:"]
            for b in bs[:20]:
                out.append(f"- {b['id']}: {b['files']} file, {fs.human_size(b['bytes'])}, trạng thái {b['state']}"
                           + (f", ghi chú: {b['note']}" if b["note"] else ""))
            out.append("Khôi phục: op=restore batch=<mã>. Xoá hẳn chỉ làm được trên trang Dọn ổ đĩa.")
            return "\n".join(out)

        if op == "quarantine":
            paths = args.get("paths") or []
            if isinstance(paths, str):
                paths = [x for x in paths.replace("\n", ";").split(";")]
            paths = [str(x).strip() for x in paths if str(x or "").strip()]
            if not paths:
                return "ERROR: cần paths, danh sách các bản trùng muốn chuyển vào cách ly."
            if fs.JOB.running():
                return "ERROR: đang có lượt quét chạy, đợi xong rồi hãy dọn."
            res = await asyncio.to_thread(fs.quarantine, paths, bool(args.get("similar")), str(args.get("note") or ""))
            out = []
            if res["moved"]:
                out.append(f"Đã chuyển {len(res['moved'])} file ({fs.human_size(res['bytes'])}) vào cách ly, mã lần dọn "
                           f"{res['batch']}. File nằm trong thư mục .javis-quarantine ngay trong thư mục đã quét, khôi "
                           f"phục được bằng op=restore batch={res['batch']} hoặc trên trang Dọn ổ đĩa.")
            for r in res["refused"][:20]:
                out.append(f"Không chuyển {r['path']}: {_REFUSED_VI.get(r['reason'], r['reason'])}.")
            return "\n".join(out) or "Không chuyển file nào."

        if op == "restore":
            batch = str(args.get("batch") or "").strip()
            if not batch:
                return "ERROR: cần batch (mã lần dọn, xem op=batches)."
            try:
                res = await asyncio.to_thread(fs.restore, batch)
            except fs.QuarantineError:
                return f"ERROR: lần dọn {batch} không còn file nào trong cách ly."
            out = [f"Đã khôi phục {len(res['restored'])} file về chỗ cũ."]
            for k in res["kept"][:20]:
                why = {"taken": "chỗ cũ đã có file khác", "missing": "không còn trong cách ly"}.get(k["reason"], k["reason"])
                out.append(f"Chưa khôi phục {k['path']}: {why}.")
            return "\n".join(out)

        return "ERROR: op phải là một trong " + ", ".join(OPS) + "."

    ctx.register_tool(
        name="javis_files",
        description=(
            "Quét file trên máy chạy Javis: ổ trong máy, USB, ổ mạng map (Z:\\) hoặc NAS (\\\\ten-nas\\thu-muc, hoặc "
            "thư mục đã mount trên Linux/macOS); tìm file TRÙNG GIỐNG HỆT (so dung lượng, rồi băm đầu cuối, rồi băm toàn "
            "bộ), ảnh GẦN GIỐNG (op=similar), thống kê dung lượng. "
            "op=drives (liệt kê ổ, gồm ổ mạng), op=scan (roots=[...], exclude=[...], min_size_kb, wait giây; chạy nền, "
            "lần sau chỉ băm file đã đổi), op=status, op=cancel, op=duplicates (limit, roots để lọc), op=stats, "
            "op=report (lưu báo cáo Markdown vào exports/ của brain). Dọn: op=quarantine paths=[bản trùng] (similar=true "
            "cho ảnh gần giống) CHUYỂN file vào thư mục cách ly, từ chối bản cuối cùng; op=batches, op=restore batch=<mã>. "
            "Không có lệnh xoá hẳn (chỉ trên trang Dọn ổ đĩa). Chưa rõ quét chỗ nào thì hỏi người dùng."),
        handler=_handle, min_mode="readonly", emoji="🗂️",
        op_modes={"drives": "readonly", "scan": "readonly", "status": "readonly", "cancel": "readonly",
                  "duplicates": "readonly", "stats": "readonly", "report": "safe", "similar": "readonly",
                  "batches": "readonly", "quarantine": "full", "restore": "full"},
        schema={"type": "object", "properties": {
            "op": {"type": "string", "enum": list(OPS)},
            "roots": {"type": "array", "items": {"type": "string"},
                      "description": "Thư mục hoặc ổ cần quét / lọc, vd [\"E:\\\\\", \"Z:\\\\Ảnh\", \"\\\\\\\\nas\\\\share\"]"},
            "exclude": {"type": "array", "items": {"type": "string"}, "description": "Thư mục bỏ qua"},
            "min_size_kb": {"type": "integer", "description": "Bỏ qua file nhỏ hơn (KB) khi tìm trùng"},
            "wait": {"type": "number", "description": "Số giây chờ lượt quét (mặc định 45, tối đa 110)"},
            "limit": {"type": "integer", "description": "Số nhóm trùng trả về (mặc định 20)"},
            "paths": {"type": "array", "items": {"type": "string"}, "description": "op=quarantine: các bản cần chuyển vào cách ly"},
            "similar": {"type": "boolean", "description": "op=quarantine: cho phép dọn ảnh gần giống (không giống hệt)"},
            "note": {"type": "string", "description": "op=quarantine: ghi chú cho lần dọn"},
            "batch": {"type": "string", "description": "op=restore: mã lần dọn"}},
            "required": ["op"]},
    )
