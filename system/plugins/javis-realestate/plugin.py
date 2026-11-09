# -*- coding: utf-8 -*-
"""Bundled plugin: the Real estate page's data for every engine.

`javis_realestate` (readonly) reads the current data, one region in full, or the waiting draft.
`javis_realestate_draft` (safe) writes a quarterly update as a DRAFT (server/realestate_store.py). There is no tool
to approve: the owner reviews the draft on the page and approves or discards it there.
Tool text sent to the model stays Vietnamese (docs/dev/them-mot-ngon-ngu.md).
"""
from __future__ import annotations

import json

import realestate_store as rs


def register(ctx):
    async def _read(args, cctx):
        args = args or {}
        op = str(args.get("op") or "summary").strip().lower()
        data, source, at = rs.current()
        if op == "summary":
            dm = rs.draft_meta()
            head = f"Nguồn số liệu: {'bản đã cập nhật' if source == 'updated' else 'bản gốc đi kèm app'}."
            if dm:
                head += f" Đang có bản nháp chờ duyệt (khu vực: {', '.join(dm['changed'])})."
            return head + "\n" + rs.summary(data)
        if op == "region":
            rid = str(args.get("region") or "").strip()
            src = (rs.draft() or {}).get("data") if args.get("draft") else data
            reg = next((r for r in (src or {}).get("regions") or [] if r.get("id") == rid), None)
            if not reg:
                ids = ", ".join(r.get("id", "") for r in data.get("regions") or [])
                return f"ERROR: không có khu vực '{rid}'. Khu vực hiện có: {ids}."
            fields = [f for f in (args.get("fields") or []) if isinstance(f, str)]
            if fields:
                reg = {k: reg[k] for k in fields if k in reg}
            return json.dumps(reg, ensure_ascii=False)
        if op == "draft":
            d = rs.draft()
            if not d:
                return "Không có bản nháp nào đang chờ duyệt."
            return f"Bản nháp ({', '.join(d.get('changed') or [])}), ghi chú: {d.get('note') or '-'}\n" + rs.summary(d["data"])
        return "ERROR: op phải là summary, region hoặc draft."

    ctx.register_tool(
        name="javis_realestate",
        description=(
            "Đọc số liệu trang Bất động sản của Javis (Đà Nẵng 'danang', TP.HCM 'hcm', Đồng Nai 'dongnai'): giá, "
            "thanh khoản, chuỗi giá 20 năm, khu vực con, hạ tầng, chính sách, dự báo, nguồn. op=summary (tóm tắt, "
            "kỳ số liệu, nguồn), op=region (JSON đầy đủ một khu vực; fields=['kpis','as_of'] để chỉ lấy vài trường; "
            "draft=true để đọc bản nháp), op=draft (bản nháp đang chờ duyệt). Dùng TRƯỚC khi cập nhật số liệu quý mới "
            "để biết cấu trúc và số cũ."),
        handler=_read, min_mode="readonly", emoji="🏠",
        schema={"type": "object", "properties": {
            "op": {"type": "string", "enum": ["summary", "region", "draft"]},
            "region": {"type": "string", "description": "danang, hcm hoặc dongnai"},
            "fields": {"type": "array", "items": {"type": "string"}},
            "draft": {"type": "boolean"}},
            "required": ["op"]},
    )

    async def _draft(args, cctx):
        args = args or {}
        op = str(args.get("op") or "set").strip().lower()
        if op == "discard":
            rs.discard()
            return "Đã bỏ bản nháp."
        rid = str(args.get("region") or "").strip()
        fields = args.get("fields")
        if isinstance(fields, str):
            try:
                fields = json.loads(fields)
            except Exception as e:
                return f"ERROR: fields không phải JSON hợp lệ ({e})."
        if not rid or not isinstance(fields, dict) or not fields:
            return "ERROR: cần region và fields (object chứa các trường đổi, vd {\"as_of\": \"Q4/2026\", \"kpis\": [...]})."
        res = rs.set_region(rid, fields, note=str(args.get("note") or ""), updated=str(args.get("updated") or ""))
        if not res.get("ok"):
            return "ERROR: bản nháp bị từ chối vì sẽ làm hỏng trang: " + "; ".join(res.get("errors") or [])
        dm = res["draft"]
        return (f"Đã ghi bản nháp cho {rid} (các khu vực trong nháp: {', '.join(dm['changed'])}). Bản nháp CHƯA hiện cho "
                "người dùng: họ cần mở trang Bất động sản để xem trước và bấm Duyệt. Báo lại cho họ đúng như vậy.")

    ctx.register_tool(
        name="javis_realestate_draft",
        description=(
            "Ghi bản cập nhật số liệu Bất động sản dạng NHÁP (chủ duyệt trên trang, tool này không xuất bản). "
            "op=set: region (danang|hcm|dongnai), fields = object CHỈ chứa các trường thay đổi, giữ nguyên cấu trúc "
            "và kiểu dữ liệu như op=region trả về (mọi chữ dạng {\"vi\": ..., \"en\": ...}); updated = 'YYYY-MM'; note = tóm "
            "tắt thay đổi và nguồn. Chỉ ghi số có nguồn thật (CBRE, DKRA, VARS, Savills, báo uy tín), ghi nguồn vào "
            "'sources' và 'source' của từng chỉ số; không bịa số. op=discard: bỏ bản nháp."),
        handler=_draft, min_mode="safe", emoji="📝",
        schema={"type": "object", "properties": {
            "op": {"type": "string", "enum": ["set", "discard"]},
            "region": {"type": "string"},
            "fields": {"type": "object", "description": "Các trường thay đổi của khu vực, vd as_of, summary, kpis, price_series, forecast, sources"},
            "updated": {"type": "string"},
            "note": {"type": "string"}},
            "required": ["op"]},
    )
