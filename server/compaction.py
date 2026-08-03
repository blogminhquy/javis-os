"""
Nén hội thoại dài cho engine API (openrouter / openai / anthropic-api / gemini).

Vấn đề: engine API resend toàn bộ lịch sử mỗi lượt. Trước đây _trim_history chỉ CẮT BỎ
phần cũ quá cửa sổ 12 message - model quên sạch những gì đã bàn trước đó trong phiên dài.

Cách nén (port ý tưởng session_memory_compaction của anthropics/claude-cookbooks):
- Sau mỗi lượt, nếu phần lịch sử NẰM NGOÀI cửa sổ mà chưa được nén đủ lớn (>= MIN_CHUNK
  message) → gọi nền 1 request tóm tắt GỘP (tóm tắt cũ + đoạn mới → tóm tắt mới),
  lưu vào sessions.compact_summary + compact_count (số message đầu đã phủ).
- Lượt sau seed lại lịch sử: bỏ qua compact_count message đầu, chèn tóm tắt làm system
  message thứ 2 → model vẫn "nhớ" mạch cũ mà payload không phình.
- Engine CLI (Claude Code) tự quản context nên KHÔNG đi qua đây.
"""
import sys

MAX_HISTORY_MSGS = 12   # cửa sổ message gần nhất giữ NGUYÊN VẸN (≈6 lượt hỏi-đáp)
MIN_CHUNK = 6           # phần cũ chưa nén phải >= N message mới đáng tốn 1 request tóm tắt
MAX_SUMMARY_CHARS = 6000
_MSG_CLIP = 1500        # mỗi message đưa vào prompt tóm tắt cắt còn ~1500 ký tự
# Trần ký tự của bản mồi lại mạch mới. Đây mới là chỗ NGỮ CẢNH THẬT SỰ MẤT, chứ không phải
# cái ngưỡng xoay mạch bên dưới - và hai con số đó đi ngược nhau theo cách phản trực giác:
# ngưỡng càng cao thì xoay càng hiếm, nhưng mỗi lần xoay lại rơi càng sâu. Ở ngưỡng 120k, rơi
# xuống 60.000 ký tự (~20k token) là mất sáu lần. Ở ngưỡng 1 triệu, cùng cái trần đó thành
# mất năm mươi lần.
#
# Chủ repo chốt hướng: giữ ngưỡng 1 triệu cho khỏi bị cắt mạch vặt, nhưng nâng trần này lên để
# lúc xoay không rơi tự do. 300.000 ký tự ~ 100k token: đủ dày để mang theo cả một phiên làm
# việc dài, mà vẫn nhỏ hơn nhiều so với một triệu token vừa bỏ đi.
CODEX_BOOTSTRAP_MAX_CHARS = 300_000
# Đuôi hội thoại CHƯA nén dài quá ngưỡng này → nén ĐỒNG BỘ ngay trong lượt trước khi gửi,
# để phần cũ vào tóm tắt thay vì bị cắt câm. Hay xảy ra khi đổi từ engine Claude (CLI - không
# tạo tóm tắt) sang engine API giữa chừng, hoặc nén nền chưa kịp bắt đầu.
SYNC_COMPACT_TAIL = 24

# ── Mạch hội thoại của engine gói thuê bao (Claude Code, Codex) ──────────────────────────
#
# Hai engine này tự quản mạch: Javis chỉ đưa `--resume <id>` rồi chúng gửi lại toàn bộ
# transcript ở phía chúng. Nghĩa là phần TO NHẤT của mỗi lượt nằm ngoài tầm với của mọi cơ
# chế tiết kiệm ngữ cảnh - Phase 8 gọt bộ luật xuống còn vài trăm token thì mạch cũ vẫn kéo
# theo hàng trăm nghìn. Số đo thật của chủ repo: lượt đầu hội thoại 36k, cùng hội thoại đó
# vài lượt sau đã 191k, có lượt chạm 412k. Bộ luật + bộ nhớ + mô tả tool của anh chỉ khoảng
# 10.6k, tức phần Javis gọt được chưa tới 3% của lượt nặng nhất.
#
# Javis không chèn được vào giữa mạch của chúng, nhưng làm được một việc: khi mạch đã phình
# quá ngưỡng thì THÔI resume, mở mạch MỚI và mồi lại bằng transcript đã nén trong SQLite
# (codex_bootstrap_prompt ở dưới). Đổi lại là mất phần ngữ cảnh ngầm mà engine tự giữ, nên
# ngưỡng phải đủ cao để chỉ chạm tới khi mạch thật sự đã quá dài.
#
# 1 triệu, do chủ repo chốt sau khi dùng thật, và số đo ủng hộ con số đó. Ba lượt liên tiếp
# trong cùng một hội thoại của anh: 83k, rồi 552k (lượt đi tra thời tiết, Codex chạy cả vòng
# lặp web search), rồi 36k. Nghĩa là một lượt NẶNG thường nặng vì công việc của chính lượt
# đó, không vì mạch dài - và mạch tự co lại ngay lượt sau.
#
# Đặt 120k như bản đầu là gần như lượt nào cũng vượt, tức xoay mạch liên tục: mỗi lần xoay là
# một lần vứt phần ngữ cảnh ngầm engine đang giữ, đổi lấy gần như không gì. Mốc chống xoay
# liên tục bên dưới có chặn bớt, nhưng chặn một hành vi sai vẫn không bằng đừng làm nó.
SUBSCRIPTION_THREAD_MAX_TOKENS = 1_000_000
# Số message tối thiểu phải tích thêm kể từ lần xoay trước thì mới được xoay tiếp.
#
# Vì sao cần cái này, và vì sao nó QUAN TRỌNG hơn nó trông. Token vào của engine thuê bao
# phần lớn KHÔNG đến từ độ dài mạch, mà từ vòng lặp agentic bên trong nó: một lượt Codex gọi
# model nhiều vòng, mỗi vòng gửi lại toàn bộ ngữ cảnh đã tích. Số đo thật của chủ repo cho
# thấy đúng điều đó - model chỉ viết ra 266 tới 1.496 token trong khi đọc vào 35k tới 412k.
# Nghĩa là một lượt NẶNG có thể nặng vì công việc, không phải vì mạch dài. Xoay mạch trong ca
# đó không giúp gì cả: lượt sau vẫn nặng, lại xoay tiếp, và mỗi lần xoay là một lần Javis
# quên mất phần ngữ cảnh ngầm mà engine đang giữ. Mốc này bắt buộc phải có tiến triển thật
# (thêm hai lượt hỏi-đáp) mới cho xoay lần nữa.
SUBSCRIPTION_ROTATE_MIN_MSGS = 4


def nen_mach_thue_bao(last_input_tokens, nguong: int = SUBSCRIPTION_THREAD_MAX_TOKENS,
                      msg_count=None, rotated_at=None,
                      min_msgs: int = SUBSCRIPTION_ROTATE_MIN_MSGS) -> bool:
    """Mạch hội thoại của engine thuê bao đã đáng xoay chưa.

    Tách thành hàm riêng vì đây là một QUYẾT ĐỊNH, không phải một phép so sánh: nó đánh đổi
    ngữ cảnh ngầm lấy token, và đó là thứ phải test được, phải chỉnh được, và phải đọc ra
    lý do được. Giá trị rác (None, chuỗi, số âm) đều coi như chưa đáng xoay - thà bỏ sót còn
    hơn cắt mạch của người đang nói dở.

    Hai điều kiện phải cùng đúng: lượt trước đã vượt ngưỡng token, VÀ đã có đủ message mới
    kể từ lần xoay gần nhất (xem SUBSCRIPTION_ROTATE_MIN_MSGS).
    """
    try:
        tokens = int(last_input_tokens or 0)
    except (TypeError, ValueError):
        return False
    try:
        muc = int(nguong or 0)
    except (TypeError, ValueError):
        muc = SUBSCRIPTION_THREAD_MAX_TOKENS
    if not (muc > 0 and tokens > muc):
        return False
    try:
        moc = int(rotated_at or 0)
    except (TypeError, ValueError):
        moc = 0
    if moc <= 0:
        return True          # chưa xoay lần nào, không có gì phải chờ
    try:
        hien_tai = int(msg_count or 0)
    except (TypeError, ValueError):
        return True          # không đọc được số message thì đừng chặn quyết định
    return hien_tai - moc >= max(1, int(min_msgs or 1))


SUMMARY_HEADER = ("[Tóm tắt phần đầu hội thoại - đã nén để tiết kiệm context. "
                  "Coi đây là ký ức về những gì hai bên đã trao đổi trước đó:]\n")


def bootstrap_prompt(raw_msgs, current_prompt: str,
                     max_chars: int = CODEX_BOOTSTRAP_MAX_CHARS,
                     summary: str = "") -> str:
    """Gói transcript trong SQLite thành MỘT prompt để mồi lại một mạch hội thoại mới.

    Dùng cho mọi engine tự quản mạch (Codex, Claude Code), ở ba tình huống: phiên cũ chưa có
    thread id, rollout cũ bị mất trên máy, và mạch đã phình quá ngưỡng nên Javis chủ động mở
    mạch mới. Sau khi engine phát thread mới thì các lượt kế tiếp resume native, không resend
    transcript này nữa.

    Giữ phần GẦN NHẤT trong ngân sách ký tự; current_prompt luôn được giữ nguyên.

    `summary` là bản tóm tắt đã nén của phần đầu hội thoại, nếu phiên có. Nó được đặt TRƯỚC
    transcript và KHÔNG bị cắt, vì một dòng tóm tắt đại diện cho hàng chục lượt đã rơi khỏi
    ngân sách - bỏ nó để nhét thêm hai lượt thô là đổi sai chiều. Phiên chạy engine gói thuê
    bao thường chưa có tóm tắt (bộ nén nền chỉ chạy cho engine API key); khi đó phần này rỗng
    và hàm hoạt động y như trước.
    """
    usable = [m for m in (raw_msgs or [])
              if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()]
    tom_tat = str(summary or "").strip()
    if not usable:
        return current_prompt

    header = (
        "[KHÔI PHỤC NGỮ CẢNH HỘI THOẠI]\n"
        "Các đoạn dưới đây là lịch sử thật của cùng cuộc trò chuyện Javis. "
        "Hãy tiếp tục đúng mạch, không coi chúng là yêu cầu mới cần làm lại.\n"
    )
    if tom_tat:
        header += SUMMARY_HEADER + tom_tat + "\n"
    footer = "\n[HẾT LỊCH SỬ]\n\n[YÊU CẦU HIỆN TẠI]\n"
    budget = max(1000, int(max_chars)) - len(header) - len(footer) - len(current_prompt)
    blocks = []
    truncated = False
    for m in reversed(usable):
        who = "User" if m.get("role") == "user" else "Javis"
        block = f"\n<{who}>\n{m.get('content') or ''}\n</{who}>\n"
        if len(block) <= budget:
            blocks.append(block)
            budget -= len(block)
            continue
        truncated = True
        if not blocks and budget > 300:
            # Một message gần nhất quá dài: giữ phần cuối vì thường chứa kết luận/trạng thái mới nhất.
            blocks.append("\n[...đầu message đã lược bớt...]\n" + block[-budget:])
        break
    blocks.reverse()
    note = "\n[...phần lịch sử cũ hơn đã lược bớt...]\n" if truncated else ""
    return header + note + "".join(blocks) + footer + current_prompt


# Tên cũ, giữ lại vì đã có sẵn ở nhiều chỗ gọi. Hàm chưa bao giờ riêng cho Codex, nay Claude
# Code dùng chung nên tên chính đổi cho đúng việc nó làm.
codex_bootstrap_prompt = bootstrap_prompt


def trim_history(messages, max_msgs: int = MAX_HISTORY_MSGS):
    """Giữ RUN system message dẫn đầu (system prompt + tóm tắt nén) + max_msgs message
    gần nhất. Bỏ assistant dẫn đầu phần tail vì Anthropic yêu cầu message đầu (sau system)
    phải là role=user. Trả về list mới; không mutate input."""
    if not messages:
        return messages
    n_head = 0
    while n_head < len(messages) and messages[n_head].get("role") == "system":
        n_head += 1
    if len(messages) - n_head <= max_msgs:
        return messages
    head = messages[:n_head]
    tail = messages[len(messages) - max_msgs:]
    while tail and tail[0].get("role") == "assistant":
        tail = tail[1:]
    return head + tail


def seed_messages(store, conv_sid, raw_msgs):
    """Lịch sử để seed lại 1 lượt chat: phần đầu đã nén thay bằng tóm tắt (system message).
    raw_msgs = list {role, content} user/assistant theo thứ tự thời gian (đã lọc rỗng)."""
    sess = store.get_session(conv_sid) or {}
    summary = (sess.get("compact_summary") or "").strip()
    count = int(sess.get("compact_count") or 0)
    if not summary or count <= 0:
        return raw_msgs
    tail = raw_msgs[count:] if count < len(raw_msgs) else []
    return [{"role": "system", "content": SUMMARY_HEADER + summary}] + tail


async def prepare_history(head, store, conv_sid, raw_msgs, prov, api_key, model, api_stream,
                          keep: int = MAX_HISTORY_MSGS, sync_tail: int = SYNC_COMPACT_TAIL):
    """Ghép payload lịch sử cho 1 lượt engine API mà KHÔNG bao giờ bỏ CÂM ngữ cảnh.

    head = các system message dẫn đầu (system prompt + dòng khai model). raw_msgs = lịch sử
    user/assistant theo thứ tự thời gian, ĐÃ bỏ câu user hiện tại (lượt gọi sẽ tự append sau).

    Trả về: head + [tóm tắt nén nếu có] + đuôi hội thoại CHƯA nén. Khác trim_history cũ (giữ
    cứng 12 message gần nhất, CẮT BỎ phần cũ hơn kể cả khi chưa có tóm tắt → mất trí nhớ khi
    phiên dài hoặc vừa đổi từ engine Claude/CLI sang API): ở đây phần cũ CHỈ rời payload khi
    đã nằm trong tóm tắt. Nếu đuôi chưa nén quá dài thì nén ĐỒNG BỘ ngay (1 request, chặn lượt
    một nhịp) để gấp phần cũ vào tóm tắt trước khi gửi - hiếm khi chạm, chủ yếu ở lượt API đầu
    tiên sau một mạch chat bằng Claude Code."""
    sess = store.get_session(conv_sid) or {}
    count = int(sess.get("compact_count") or 0)
    uncompacted = max(0, len(raw_msgs) - count)
    if uncompacted > sync_tail:
        # min_chunk=1: buộc nén ngay cả phần cũ nhỏ, miễn có gì để gấp vào tóm tắt.
        await maybe_compact(store, conv_sid, prov, api_key, model, api_stream,
                            keep=keep, min_chunk=1)
    return list(head) + seed_messages(store, conv_sid, raw_msgs)


async def _summarize(old, chunk, prov, api_key, model, api_stream):
    """Gọi provider tóm tắt GỘP `old` (tóm tắt cũ, có thể rỗng) + `chunk` (list message
    user/assistant) → chuỗi tóm tắt mới (đã strip + clip MAX_SUMMARY_CHARS).
    Trả '' nếu provider lỗi hoặc ra rỗng - caller tự quyết fallback."""
    lines = []
    for m in chunk:
        c = m.get("content") or ""
        if len(c) > _MSG_CLIP:
            c = c[:_MSG_CLIP] + " (...)"
        lines.append(("User: " if m.get("role") == "user" else "Javis: ") + c)
    prompt = (
        "Bạn đang nén lịch sử hội thoại giữa User và trợ lý Javis để tiết kiệm context.\n\n"
        f"TÓM TẮT HIỆN CÓ (các phần trước đó nữa):\n{old or '(chưa có)'}\n\n"
        "ĐOẠN HỘI THOẠI MỚI CẦN GỘP THÊM:\n" + "\n\n".join(lines) + "\n\n"
        "Viết TÓM TẮT MỚI gộp cả hai (tối đa ~350 từ), giữ lại: chủ đề chính, quyết định đã chốt, "
        "con số/tên riêng/đường dẫn quan trọng, việc đang dang dở, sở thích hay yêu cầu User đã nêu. "
        "Bỏ chào hỏi xã giao. Viết gọn dạng gạch đầu dòng '- '. CHỈ in tóm tắt, không mở bài."
    )
    text = ""
    async for ev in api_stream(prov, api_key, model, [{"role": "user", "content": prompt}], "off"):
        t = ev.get("type")
        if t == "text":
            text += ev.get("content") or ""
        elif t == "error":
            print(f"[compact] provider lỗi: {ev.get('content')}", file=sys.stderr)
            return ""
    return text.strip()[:MAX_SUMMARY_CHARS]


async def maybe_compact(store, conv_sid, prov, api_key, model, api_stream,
                        keep: int = MAX_HISTORY_MSGS, min_chunk: int = MIN_CHUNK):
    """Chạy NỀN sau 1 lượt chat: nén phần lịch sử cũ sắp rơi khỏi cửa sổ vào compact_summary.
    api_stream = main._api_stream (inject để test không cần mạng). Trả True nếu có nén.
    Lỗi ở đây KHÔNG được phá lượt chat - nuốt + log, lượt sau còn nguyên fallback trim."""
    try:
        msgs = [m for m in store.get_messages(conv_sid)
                if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()]
        sess = store.get_session(conv_sid) or {}
        count = int(sess.get("compact_count") or 0)
        old = (sess.get("compact_summary") or "").strip()
        cut = len(msgs) - keep
        if cut - count < min_chunk:
            return False
        text = await _summarize(old, msgs[count:cut], prov, api_key, model, api_stream)
        if not text:
            return False
        store.set_compact(conv_sid, text, cut)
        return True
    except Exception as e:
        print(f"[compact] {type(e).__name__}: {e}", file=sys.stderr)
        return False


def _split_mem(msgs):
    """Tách list lịch sử IN-MEMORY thành (head, prev_summary, convo):
      head        = các system message CỐ ĐỊNH dẫn đầu (system prompt + dòng khai model),
      prev_summary= nội dung system 'tóm tắt nén' cũ nếu có (đã bỏ SUMMARY_HEADER),
      convo       = message user/assistant còn nội dung, theo thứ tự thời gian.
    Phân biệt system tóm tắt với system cố định bằng SUMMARY_HEADER ở đầu content."""
    head, prev_summary, i = [], "", 0
    while i < len(msgs) and msgs[i].get("role") == "system":
        c = msgs[i].get("content") or ""
        if c.startswith(SUMMARY_HEADER):
            prev_summary = c[len(SUMMARY_HEADER):].strip()
        else:
            head.append(msgs[i])
        i += 1
    convo = [m for m in msgs[i:]
             if m.get("role") in ("user", "assistant") and (m.get("content") or "").strip()]
    return head, prev_summary, convo


async def compact_mem(msgs, prov, api_key, model, api_stream,
                      keep: int = MAX_HISTORY_MSGS, min_chunk: int = MIN_CHUNK):
    """Nén danh sách lịch sử GIỮ TRONG RAM - dành cho phiên Telegram (giữ sess['or'] in-memory,
    KHÔNG rebuild từ SQLite mỗi lượt như dashboard). Thay cho trim_history cứng: phần cũ rơi
    khỏi cửa sổ được TÓM TẮT (gộp cả tóm tắt cũ) rồi chèn làm system message ngay sau phần đầu,
    thay vì bị CẮT CÂM - phiên Telegram dài / vừa đổi từ engine Claude sang API không còn mất
    trí nhớ phần đầu (cùng lớp lỗi đã vá cho dashboard).

    msgs vào/ra cùng dạng: [system cố định...] (+ [system tóm tắt cũ]) + user/assistant...
    Trả về LIST MỚI (không mutate input). Chưa đủ phần cũ để đáng 1 request tóm tắt → giữ
    nguyên. Nén hỏng (provider lỗi) → fallback trim_history để payload vẫn bị chặn kích thước."""
    try:
        head, prev_summary, convo = _split_mem(msgs)
        cut = len(convo) - keep
        if cut < min_chunk:
            return list(msgs)
        new_summary = await _summarize(prev_summary, convo[:cut], prov, api_key, model, api_stream)
        if not new_summary:
            return trim_history(msgs, keep)
        tail = convo[cut:]
        while tail and tail[0].get("role") == "assistant":
            tail = tail[1:]   # message đầu sau system phải là user (yêu cầu Anthropic)
        summary_msg = {"role": "system", "content": SUMMARY_HEADER + new_summary}
        return list(head) + [summary_msg] + tail
    except Exception as e:
        print(f"[compact_mem] {type(e).__name__}: {e}", file=sys.stderr)
        return trim_history(msgs, keep)
