# -*- coding: utf-8 -*-
"""Bundled plugin: the Investment compass page's outlook for every engine.

`javis_compass` (readonly) reads the current outlook, one part of it in full, or the waiting draft.
`javis_compass_draft` (safe) writes a monthly update as a DRAFT (server/compass_store.py). There is no tool to
approve: the owner reviews the draft on the page and approves or discards it there.
Tool text sent to the model stays Vietnamese (docs/dev/them-mot-ngon-ngu.md).
"""
from __future__ import annotations

import json

import compass_store as cs

PARTS = ("verdict", "summary", "actions", "clock", "assets", "factors", "sentiment", "commodities", "profiles",
         "rules", "calendar", "playbook", "history", "sources", "pulse")


def register(ctx):
    async def _read(args, cctx):
        args = args or {}
        op = str(args.get("op") or "summary").strip().lower()
        data, source, at = cs.current()
        if op == "summary":
            dm = cs.draft_meta()
            head = f"Nguồn: {'bản đã cập nhật' if source == 'updated' else 'bản gốc đi kèm app'}."
            if dm:
                head += f" Đang có bản nháp chờ duyệt (đã đổi: {', '.join(dm['changed'])})."
            return head + "\n" + cs.summary(data)
        if op == "part":
            src = (cs.draft() or {}).get("data") if args.get("draft") else data
            src = src or data
            part = str(args.get("part") or "").strip()
            if part not in src:
                return f"ERROR: không có phần '{part}'. Các phần: {', '.join(k for k in src.keys())}."
            val = src[part]
            aid = str(args.get("asset") or "").strip()
            if part == "assets" and aid:
                val = next((a for a in val if a.get("id") == aid), None)
                if val is None:
                    return f"ERROR: không có kênh '{aid}'. Các kênh: {', '.join(cs.ASSET_IDS)}."
            return json.dumps(val, ensure_ascii=False)
        if op == "draft":
            d = cs.draft()
            if not d:
                return "Không có bản nháp nào đang chờ duyệt."
            return f"Bản nháp (đã đổi: {', '.join(d.get('changed') or [])}), ghi chú: {d.get('note') or '-'}\n" + cs.summary(d["data"])
        return "ERROR: op phải là summary, part hoặc draft."

    ctx.register_tool(
        name="javis_compass",
        description=(
            "Đọc nhận định trang La bàn đầu tư của Javis: lúc này nên nghiêng vốn về nhà đất Việt Nam 're_vn', chứng "
            "khoán Việt Nam 'stocks_vn', chứng khoán thế giới 'stocks_world', vàng 'gold', tiền số 'crypto', tiết kiệm "
            "'savings' hay USD 'usd'; kèm chu kỳ kinh tế, yếu tố tác động, tâm lý, tỷ trọng theo khẩu vị rủi ro, lịch sự "
            "kiện, nguồn. op=summary (tóm tắt), op=part (JSON đầy đủ một phần: part=assets|factors|clock|profiles|"
            "calendar|...; asset=<id> để lấy một kênh; draft=true để đọc bản nháp), op=draft (bản nháp chờ duyệt). "
            "Dùng TRƯỚC khi cập nhật nhận định tháng mới để biết cấu trúc và số cũ."),
        handler=_read, min_mode="readonly", emoji="🧭",
        schema={"type": "object", "properties": {
            "op": {"type": "string", "enum": ["summary", "part", "draft"]},
            "part": {"type": "string", "enum": list(PARTS)},
            "asset": {"type": "string", "enum": list(cs.ASSET_IDS)},
            "draft": {"type": "boolean"}},
            "required": ["op"]},
    )

    async def _draft(args, cctx):
        args = args or {}
        op = str(args.get("op") or "set").strip().lower()
        if op == "discard":
            cs.discard()
            return "Đã bỏ bản nháp."
        fields = args.get("fields")
        if isinstance(fields, str):
            try:
                fields = json.loads(fields)
            except Exception as e:
                return f"ERROR: fields không phải JSON hợp lệ ({e})."
        if not isinstance(fields, dict) or not fields:
            return ("ERROR: cần fields (object chứa các phần đổi, vd {\"verdict\": {...}, \"assets\": [{\"id\": \"gold\", "
                    "\"stance\": \"accumulate\", \"score\": 1}]}).")
        res = cs.set_fields(fields, note=str(args.get("note") or ""), updated=str(args.get("updated") or ""),
                            as_of=str(args.get("as_of") or ""))
        if not res.get("ok"):
            return "ERROR: bản nháp bị từ chối vì sẽ làm hỏng trang: " + "; ".join(res.get("errors") or [])
        dm = res["draft"]
        return (f"Đã ghi bản nháp (các phần đã đổi: {', '.join(dm['changed'])}). Bản nháp CHƯA hiện cho người dùng: họ "
                "cần mở trang La bàn đầu tư để xem trước và bấm Duyệt. Báo lại cho họ đúng như vậy.")

    ctx.register_tool(
        name="javis_compass_draft",
        description=(
            "Ghi bản cập nhật nhận định La bàn đầu tư dạng NHÁP (chủ duyệt trên trang, tool này không xuất bản). "
            "op=set: fields = object CHỈ chứa các phần thay đổi, giữ nguyên cấu trúc và kiểu như op=part trả về (mọi chữ "
            "dạng {\"vi\": ..., \"en\": ...}). 'assets' là danh sách CHỈ các kênh đổi, mỗi kênh có 'id' và các trường đổi "
            "(stance accumulate|hold|reduce, score -2..2, one_liner, verdict, thesis...); các phần khác (verdict, summary, "
            "actions, clock, factors, sentiment, commodities, profiles, calendar, playbook, sources) thay nguyên khối. "
            "updated = 'YYYY-MM-DD', as_of = 'MM/YYYY', note = tóm tắt thay đổi. Chỉ ghi số có nguồn thật (Fed, Tổng cục "
            "Thống kê, Ngân hàng Nhà nước, CBRE, FiinTrade, Reuters, báo uy tín), thêm vào 'sources'; không bịa số; không "
            "dùng dấu gạch dài. op=discard: bỏ bản nháp."),
        handler=_draft, min_mode="safe", emoji="📝",
        schema={"type": "object", "properties": {
            "op": {"type": "string", "enum": ["set", "discard"]},
            "fields": {"type": "object", "description": "Các phần thay đổi, vd verdict, summary, actions, assets (chỉ kênh đổi), factors, calendar, sources"},
            "updated": {"type": "string"},
            "as_of": {"type": "string"},
            "note": {"type": "string"}},
            "required": ["op"]},
    )
