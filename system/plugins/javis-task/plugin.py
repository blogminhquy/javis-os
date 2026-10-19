"""Plugin bundled: tool `javis_task` - giao việc Kanban và xem tiến độ, từ MỌI engine.

Vì sao tool này tồn tại
=======================
`CLAUDE.md` và `docs/10-models-va-engine.md` đều hứa mọi bộ não được cấp cùng một bộ đồ nghề,
trong đó có "giao việc Kanban", và khác biệt duy nhất là chạy được lệnh máy hay không.

Lời hứa đó SAI cho tới bản này. Đường duy nhất để giao việc là `POST /kanban/task`, mà gọi được
nó thì phải có Bash và curl - tức là chỉ Claude Code với Codex. Năm engine API đứng ngoài. Tệ
hơn, chính `CLAUDE.md` còn dặn Javis "đừng bao giờ nói mình không làm task được, sai sự thật",
nên một engine API sẽ TỰ TIN nhận lời rồi im lặng không làm gì - kiểu hỏng tệ nhất, vì người
dùng đợi một việc không bao giờ chạy.

Hai cách sửa: hạ tài liệu xuống cho khớp mã, hoặc nâng mã lên cho khớp tài liệu. Chủ repo chọn
cách hai (2026-08-04), vì giao việc là thứ dùng thật và để nó chỉ chạy trên hai engine thì lời
hứa "đổi não thoải mái không mất chức năng" thủng đúng chỗ đáng tiếc nhất.

Gọi THẲNG, không đi vòng qua HTTP
=================================
`javis-schedule` POST tới `/reminders` được vì route đó CỐ Ý miễn đăng nhập cho localhost
(`main._AUTH_LOCAL_EXACT`). `/kanban/task` thì không, và cách duy nhất để nó gọi được qua HTTP
là thêm vào danh sách miễn auth đó - nghĩa là bất kỳ tiến trình nào trên cùng máy chủ cũng giao
được việc cho Javis mà không cần credential. Không đáng, khi plugin vốn đã chạy IN-PROCESS:
`tasks.current()` cho ngay hàng đợi thật, không hở thêm cửa nào.

Mức quyền
=========
- Mặc định `full`: việc tự thao tác THẬT ra ngoài (tạo đơn, thanh toán, chạy quảng cáo, gửi
  tin) như lúc người dùng đang ngồi chat. Chủ repo bỏ luật "không giao tự động tiền/đơn/đăng
  bài/nhắn khách" ngày 2026-09-10; trước đó tool này từ chối thẳng `mode="full"` và mặc định
  `suggest`. Muốn việc nhẹ hơn thì truyền `mode="auto"` (ghi nháp) hoặc `"suggest"` (chỉ đọc).

Hai luật còn giữ, vì chúng không liên quan tới mức quyền mà tới việc chạy ĐÚNG brain và về ĐÚNG
người:
- `vault_root` rỗng -> báo lỗi rõ, TUYỆT ĐỐI không âm thầm rơi về Brain Default. Giao việc nhầm
  brain là việc chạy trên dữ liệu của người khác.
- `chat_id` rỗng thì CẢNH BÁO trong kết quả trả về chứ không nuốt: kết quả việc sẽ đi về ID
  Telegram đầu tiên trong whitelist, mà máy chưa đấu Telegram thì MẤT HÚT. Model phải lấy mã
  phiên từ khối "KÊNH HỘI THOẠI HIỆN TẠI" và truyền vào.

Phạm vi: `add`, `list` và `answer` (0.235.0). Chuyển cột, huỷ, duyệt việc chờ phê duyệt vẫn làm
ở trang Việc - đó là những thao tác cần nhìn thấy bảng, và mô tả tool nói thẳng như vậy thay vì
để model đoán.

`answer` (0.235.0): việc nền dừng lại hỏi (`[[NEEDS_INPUT]]`) thì câu hỏi về khung chat của
người giao việc. Người đó trả lời NGAY trong chat (web, Telegram, Zalo), model chuyển nguyên văn
vào đây và việc chạy tiếp với câu trả lời. Thiếu `id` mà brain chỉ có đúng MỘT việc đang chờ thì
dùng việc đó; nhiều hơn thì trả danh sách để model hỏi lại, KHÔNG đoán.

`route` (0.107.0): `auto` hoặc `wf:<slug>` của một quy trình CÓ THẬT. Trước bản này tool không
có tham số này, trong khi mô tả của `javis_workflow` lại bảo "dùng javis_task với route
wf:<slug>" - nên chat không có cách nào giao một lần chạy quy trình thật. Ngày 13/10 việc S07
được giao với route auto, tên quy trình chỉ nằm trong mô tả, và sáu agent của quy trình chưa
từng được gọi lần nào. Giờ route sai slug bị từ chối rõ, còn route auto mà tên việc nhắc đúng
một quy trình có thật thì kết quả trả về cảnh báo để model giao lại cho đúng.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

import tasks as tasks_mod
import workflow_graph

try:
    from skill_router import read_frontmatter_only
except Exception:          # chạy lẻ ngoài máy chủ
    read_frontmatter_only = None

try:
    import luot_dang_chay
except Exception:          # chạy ngoài máy chủ (test lẻ): không có sổ thì thôi đoán
    luot_dang_chay = None

# Trần ký tự cho phần liệt kê việc. Kết quả tool đi thẳng vào ngữ cảnh của lượt chat, và engine
# API còn bị cắt ở 8000 ký tự (engine._clip_tool_result) - liệt kê 200 việc là đẩy văng phần
# quan trọng của câu hỏi ra ngoài.
_LIST_MAX = 40

# Cột đáng báo cáo, theo thứ tự người dùng quan tâm: đang chạy trước, xong rồi để cuối.
_COT = [
    ("running", "đang chạy"),
    ("review", "chờ duyệt"),
    ("blocked", "kẹt"),
    ("ready", "sẵn sàng"),
    ("todo", "chờ tới lượt"),
    ("triage", "mới nhận"),
    ("done", "xong"),
]

_MODE_CHO_PHEP = ("suggest", "auto", "full")
_MODE_MAC_DINH = "full"

# Chỉ mức điều phối "auto" mới có dispatcher lấy việc ra chạy (`tasks.TaskRunner._dispatch`).
# "off" (mặc định của MỌI brain mới) và "manual" đều để việc nằm im vô thời hạn.
_CANH_BAO_DIEU_PHOI = (
    "LƯU Ý QUAN TRỌNG: điều phối việc nền của brain này đang ở mức \"{muc}\" nên việc chỉ nằm "
    "xếp hàng, KHÔNG tự chạy và sẽ không có kết quả nào tự về. Phải nói thẳng điều này với "
    "người dùng và bảo họ bật \"AI tự vận hành\" ở trang Việc, đừng hứa là việc đang chạy."
)


def _dieu_phoi_chay(muc) -> bool:
    return str(muc or "").strip().lower() == "auto"


def _workflows(f, vault_root) -> dict:
    """{slug: (name, status)} of the brain's workflows. Empty when unreadable."""
    try:
        d = Path(f.deps.workflows_dir(vault_root))
    except Exception:
        return {}
    out = {}
    try:
        files = sorted(d.glob("*.md")) if d.is_dir() else []
    except OSError:
        files = []
    for fp in files:
        meta = {}
        if read_frontmatter_only is not None:
            try:
                meta = read_frontmatter_only(fp)[0] or {}
            except Exception:
                meta = {}
        out[fp.stem] = (str(meta.get("name") or fp.stem), workflow_graph.workflow_status(meta))
    return out


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


def _workflow_nhac_toi(wfs: dict, title: str, intent: str) -> list:
    """Slugs of workflows the job text names (by slug or by display name)."""
    text = _norm(title + " " + intent)
    hits = []
    for slug, (name, _status) in wfs.items():
        if ((len(slug) >= 6 and slug.lower() in text)
                or (len(_norm(name)) >= 6 and _norm(name) in text)):
            hits.append(slug)
    return hits


def _feature():
    f = tasks_mod.current()
    if f is None:
        return None, ("ERROR: hàng đợi việc chưa sẵn sàng (máy chủ đang khởi động?). "
                      "Thử lại sau vài giây, hoặc giao việc ở trang Việc trên dashboard.")
    return f, ""


def _them(args, ctx) -> str:
    if not ctx.vault_root:
        return ("ERROR: chưa biết đang làm việc trên brain nào nên không giao việc được. "
                "Giao ở trang Việc trên dashboard, ở đó brain đã xác định rõ.")
    tieu_de = str((args or {}).get("title") or "").strip()
    if not tieu_de:
        return "ERROR: thiếu title - việc phải có tên thì người dùng mới theo dõi được."

    mode = str((args or {}).get("mode") or _MODE_MAC_DINH).strip().lower()
    # Mode lạ (model gõ sai, hoặc bịa ra tên mức) kẹp về mặc định thay vì để enqueue tự xử.
    if mode not in _MODE_CHO_PHEP:
        mode = _MODE_MAC_DINH

    f, loi = _feature()
    if loi:
        return loi

    route = str((args or {}).get("route") or "auto").strip() or "auto"
    wfs = _workflows(f, ctx.vault_root)
    canh_bao_route = ""
    if route != "auto":
        slug = route[3:].strip() if route.startswith("wf:") else ""
        if not slug:
            return ("ERROR: route chỉ nhận 'auto' hoặc 'wf:<slug>' của một quy trình có thật. "
                    "Quy trình đang có: " + (", ".join(sorted(wfs)) or "(chưa có quy trình nào)") + ".")
        if slug not in wfs:
            return (f"ERROR: không có quy trình '{slug}' trong brain này nên chưa giao việc. "
                    "Quy trình đang có: " + (", ".join(sorted(wfs)) or "(chưa có quy trình nào)")
                    + ". Hỏi lại người dùng nếu không chắc quy trình nào.")
        route = f"wf:{slug}"
        if wfs[slug][1] != "active":
            canh_bao_route = (f"LƯU Ý: quy trình '{wfs[slug][0]}' đang TẮT, nên việc này sẽ dừng "
                              "chờ ngay khi tới lượt chạy. Bảo người dùng bật quy trình ở trang Cộng "
                              "sự, rồi chạy lại việc ở trang Việc.")
    else:
        nhac = _workflow_nhac_toi(wfs, tieu_de, str((args or {}).get("intent") or ""))
        if nhac:
            canh_bao_route = (
                "CẢNH BÁO: việc này nhắc tới quy trình " + ", ".join(f"wf:{s}" for s in nhac)
                + " nhưng được giao với route auto, nên MỘT worker chung sẽ làm hết thay vì chạy "
                "đúng các agent của quy trình. Nếu người dùng muốn chạy quy trình đó thì giao lại "
                "với route=wf:<slug> (đặt tên việc khác đi, vì tên trùng sẽ bị từ chối).")

    chat_id = str((args or {}).get("chat_id") or "").strip()
    # Model quên chat_id thì hỏi sổ lượt đang chạy (0.64.49): đúng một khung chat đang hỏi trên
    # brain này thì đó chính là người giao việc. Không chắc thì để trống như cũ và cảnh báo.
    tu_gan = False
    if not chat_id and luot_dang_chay is not None:
        try:
            chat_id = luot_dang_chay.doan_chat_id(ctx.vault_root)
            tu_gan = bool(chat_id)
        except Exception:
            chat_id = ""
    deps = [d.strip() for d in str((args or {}).get("deps") or "").split(",") if d.strip()]
    try:
        tid = f.enqueue(
            ctx.vault_root,
            tieu_de,
            str((args or {}).get("intent") or "").strip() or tieu_de,
            route,
            2,
            deps,
            False,
            "chat",
            chat_id,
            "auto",
            mode,
            "",
        )
    except Exception as e:
        return f"ERROR: không giao được việc ({type(e).__name__}: {e})."

    # Kho việc TRẢ VỀ việc cũ khi trùng tên với một việc còn sống (kể cả đang kẹt hay chờ
    # duyệt) chứ không tạo việc mới. Bản trước tool vẫn báo "Đã giao việc" với mã cũ, người
    # dùng đợi một việc không bao giờ chạy. Nói thẳng để họ đổi tên hoặc xử lý việc cũ.
    try:
        _cu = f.store.get_task(tid) or {}
    except Exception:
        _cu = {}
    if _cu and (time.time() - float(_cu.get("created_at") or time.time())) > 5:
        return (f"CHƯA TẠO việc mới: đã có việc trùng tên \"{tieu_de}\" (mã {tid}) đang ở trạng thái "
                f"{_cu.get('status')}. Hãy nói rõ với người dùng, rồi hoặc đặt tên việc khác đi, "
                "hoặc xử lý việc cũ ở trang Việc (chạy lại / huỷ) trước khi giao lại.")

    ten_mode = {"suggest": "chỉ đọc và đề xuất", "auto": "được ghi file nháp trong brain",
                "full": "toàn quyền, tự thao tác ra ngoài"}[mode]
    ra = [f"Đã giao việc: {tieu_de}", f"Mã việc: {tid}", f"Mức quyền: {mode} ({ten_mode})"]
    if route != "auto":
        ra.append(f"Chạy quy trình: {route} ({wfs.get(route[3:], (route[3:], ''))[0]}), "
                  "từng bước do đúng agent của quy trình làm.")
    if canh_bao_route:
        ra.append(canh_bao_route)
    if deps:
        ra.append("Chờ xong: " + ", ".join(deps))
    if tu_gan:
        ra.append(f"Người nhận kết quả: tự gắn khung chat đang hỏi ({chat_id}).")
    if not chat_id:
        # Không nuốt: đây là lý do số một khiến người dùng "giao việc rồi không thấy gì".
        ra.append("CẢNH BÁO: chưa gắn người nhận (chat_id), nên kết quả sẽ về ID Telegram đầu "
                  "tiên trong whitelist - máy chưa đấu Telegram thì mất hút. Lần sau hãy truyền "
                  "chat_id lấy từ khối KÊNH HỘI THOẠI HIỆN TẠI.")

    # Lý do số hai, và là lý do LẶNG LẼ nhất: điều phối mặc định TẮT ở mọi brain mới, nên
    # "đã giao việc" và "việc đang chạy" là hai chuyện hoàn toàn khác nhau. Trước bản này tool
    # kết thúc bằng câu "Việc chạy nền. Kết quả tự về" trong MỌI trường hợp - một lời hứa sai
    # mà model không có cách nào biết là sai, rồi nó chuyển tiếp nguyên văn cho người dùng.
    muc = "off"
    try:
        muc = f.board_view(ctx.vault_root).get("orchestration") or "off"
    except Exception:
        pass
    if _dieu_phoi_chay(muc):
        ra.append("Việc chạy nền. Kết quả tự về, tiến độ xem ở trang Việc.")
    else:
        ra.append(_CANH_BAO_DIEU_PHOI.format(muc=muc))
    return "\n".join(ra)


def _liet_ke(args, ctx) -> str:
    if not ctx.vault_root:
        return "ERROR: chưa biết đang làm việc trên brain nào nên không xem được danh sách việc."
    f, loi = _feature()
    if loi:
        return loi
    try:
        view = f.board_view(ctx.vault_root)
    except Exception as e:
        return f"ERROR: không đọc được bảng việc ({type(e).__name__}: {e})."

    cols = view.get("columns") or {}
    dong, con = [], 0
    for khoa, nhan in _COT:
        ds = cols.get(khoa) or []
        if not ds:
            continue
        for t in ds:
            if len(dong) >= _LIST_MAX:
                con += 1
                continue
            hoi = _cau_hoi(t)
            dong.append(f"[{nhan}] {t.get('id', '')} · {t.get('title', '')}"
                        + (f" · CHỜ TRẢ LỜI: {hoi[:200]}" if hoi else ""))
    if not dong:
        return "Chưa có việc nào trong hàng đợi."
    if con:
        dong.append(f"…(+{con} việc nữa, xem đủ ở trang Việc)")

    # Điều phối TẮT thì việc nằm im mãi mãi mà không có một dòng lỗi nào. Nói ngay ở đây, vì đây
    # là chỗ model đang nhìn khi người dùng hỏi "việc chạy tới đâu rồi".
    #
    # `board_mode` trả CHUỖI "off"/"manual"/"auto", không phải bool - nên `not view.get(...)`
    # là sai: "off" là chuỗi rỗng-khác-rỗng nên luôn truthy, và cảnh báo này chưa từng in ra
    # một lần nào kể từ khi được viết. Đúng cổng phải là so với "auto": chỉ mức đó mới có
    # dispatcher lấy việc ra chạy (xem `tasks.TaskRunner._dispatch`).
    if not _dieu_phoi_chay(view.get("orchestration")):
        dong.append(_CANH_BAO_DIEU_PHOI.format(muc=str(view.get("orchestration") or "off")))
    return "\n".join(dong)


def _cau_hoi(t: dict) -> str:
    """Câu hỏi việc đang chờ chủ trả lời, "" khi không có. Cùng luật với tasks._cau_hoi_dang_cho."""
    return tasks_mod.TasksFeature._cau_hoi_dang_cho(t)


def _dang_cho(f, vault_root) -> list:
    """Các việc của brain này đang dừng chờ chủ trả lời."""
    try:
        cols = (f.board_view(vault_root).get("columns") or {})
    except Exception:
        return []
    return [t for t in (cols.get("blocked") or []) if _cau_hoi(t)]


async def _tra_loi(args, ctx) -> str:
    if not ctx.vault_root:
        return "ERROR: chưa biết đang làm việc trên brain nào nên không chuyển câu trả lời được."
    tra_loi = str((args or {}).get("answer") or "").strip()
    if not tra_loi:
        return "ERROR: thiếu answer - chép nguyên văn câu trả lời của người dùng vào đây."
    f, loi = _feature()
    if loi:
        return loi
    cho = _dang_cho(f, ctx.vault_root)
    tid = str((args or {}).get("id") or "").strip()
    if not tid:
        if len(cho) == 1:
            tid = str(cho[0].get("id") or "")
        elif not cho:
            return "Không có việc nào của brain này đang chờ câu trả lời."
        else:
            return ("ERROR: có " + str(len(cho)) + " việc đang chờ trả lời, chưa biết câu này cho việc "
                    "nào. Hỏi lại người dùng rồi gọi lại với id:\n"
                    + "\n".join(f"- {t.get('id')} · {t.get('title')}: {_cau_hoi(t)[:160]}" for t in cho))
    if tid not in {str(t.get("id") or "") for t in cho}:
        return (f"ERROR: việc {tid} không thuộc brain này hoặc không còn chờ câu trả lời. "
                "Gọi op=list để xem việc nào đang CHỜ TRẢ LỜI.")
    kq = await f.answer(tid, tra_loi, by="chat")
    if not kq.get("ok"):
        return f"ERROR: {kq.get('error') or 'không chuyển được câu trả lời'}."
    ra = [f"Đã chuyển câu trả lời cho việc {tid}. Việc quay lại hàng đợi và chạy tiếp với câu trả lời đó; "
          "kết quả tự về khung chat này."]
    if not _dieu_phoi_chay(kq.get("orchestration")):
        ra.append(_CANH_BAO_DIEU_PHOI.format(muc=str(kq.get("orchestration") or "off")))
    return "\n".join(ra)


def register(ctx):
    ctx.register_tool(
        "javis_task",
        "Giao việc nền vào hàng đợi Kanban, hoặc xem việc đang chạy tới đâu. "
        "CHỈ op=add khi NGƯỜI DÙNG bảo làm một việc cụ thể mà lượt này không làm xong được. "
        "KHÔNG giao việc cho kế hoạch hay 'bước tiếp theo' do chính bạn vừa nghĩ ra và user chưa "
        "gật (vd 'áp dụng kế hoạch vừa trình bày', 'cập nhật timeline', 'theo dõi rồi nhắc lại'): "
        "mỗi việc đều bắn thông báo về chuông và về khung chat khi nó xong hoặc kẹt. "
        "op=add: cần title; nên kèm chat_id (lấy từ khối KÊNH HỘI THOẠI HIỆN TẠI) để kết quả về "
        "đúng người, và intent nếu cần mô tả kỹ hơn tiêu đề. mode=full (mặc định: toàn quyền, "
        "tự thao tác ra ngoài như lúc chat), auto (chỉ ghi file nháp trong brain) hoặc suggest "
        "(chỉ đọc và đề xuất); chỉ hạ mức khi người dùng muốn vậy. deps='id1,id2' để việc này "
        "chờ việc khác xong. "
        "route: 'auto' (mặc định, một worker chung làm) hoặc 'wf:<slug>' để chạy ĐÚNG một quy trình "
        "có thật, từng bước do agent của quy trình làm; muốn chạy quy trình thì PHẢI đặt route, "
        "chép tên quy trình vào intent không làm nó chạy. "
        "op=list: liệt kê việc theo cột, việc đang dừng hỏi có ghi CHỜ TRẢ LỜI. "
        "op=answer: người dùng trả lời câu hỏi của một việc nền đang chờ -> truyền id và answer "
        "(chép nguyên văn); việc chạy tiếp với câu trả lời đó. "
        "Chuyển cột, huỷ việc và duyệt việc chờ phê duyệt thì làm ở trang Việc, tool này không có.",
        _chay,
        schema={
            "type": "object",
            "properties": {
                "op": {"type": "string", "enum": ["add", "list", "answer"]},
                "id": {"type": "string", "description": "Mã việc đang chờ trả lời (op=answer)"},
                "answer": {"type": "string", "description": "Câu trả lời nguyên văn của người dùng (op=answer)"},
                "title": {"type": "string", "description": "Tên việc, ngắn gọn (op=add)"},
                "intent": {"type": "string", "description": "Mô tả đầy đủ hơn nếu tiêu đề chưa đủ"},
                "mode": {"type": "string", "enum": ["suggest", "auto", "full"]},
                "chat_id": {"type": "string", "description": "Người nhận kết quả, vd web:<mã phiên>"},
                "deps": {"type": "string", "description": "Mã các việc phải xong trước, cách nhau dấu phẩy"},
                "route": {"type": "string",
                          "description": "auto, hoặc wf:<slug> để chạy một quy trình có thật"},
            },
            "required": ["op"],
        },
        min_mode="safe",
        emoji="🗂",
    )


async def _chay(args, ctx) -> str:
    op = str((args or {}).get("op") or "").strip().lower()
    if op == "add":
        return _them(args, ctx)
    if op == "list":
        return _liet_ke(args, ctx)
    if op == "answer":
        return await _tra_loi(args, ctx)
    return ("ERROR: op phải là 'add' (giao việc), 'list' (xem việc đang có) hoặc 'answer' "
            "(chuyển câu trả lời cho việc đang chờ).")
