"""Regression: việc chạy nền phải BÁO VỀ đúng khung chat đã giao nó.

Lỗi thật 0.9.289: người dùng ngồi dashboard bảo Javis chạy mấy agent nền. Javis đáp "em sẽ
đợi các agent chạy nền hoàn tất (có thông báo tự động khi xong) rồi tổng hợp cho anh" rồi
im lặng vĩnh viễn - không trạng thái, không hồi âm.

Hai gốc rễ, test này canh cả hai:
  1. `_notify_owner` CHỈ biết gửi Telegram. Máy không đấu Telegram thì nó trả (False, ...) và
     `TaskRunner._report` nuốt luôn - kết quả bay vào hư không. Người dùng web không có kênh
     nào nhận cả.
  2. System prompt hứa "tự có thông báo khi xong" mà không nói kênh nào, nên Javis còn hứa
     thêm là sẽ NGỒI ĐỢI rồi tổng hợp - điều nó không làm được: lượt trả lời đóng lại ngay
     sau khi nó nói xong, không ai đánh thức nó dậy.

Chạy:
    .venv/Scripts/python.exe tests/python/test_bao_viec_ve_chat_web.py
"""
import asyncio
import os
import re
import sys
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-push-test-"))

from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path

import channel_context  # noqa: E402
import main  # noqa: E402

APP = (ROOT / "dashboard" / "app.js").read_text(encoding="utf-8")
CLAUDE_MD = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")

fails = []


def check(name: str, condition: bool) -> None:
    print(("PASS: " if condition else "FAIL: ") + name)
    if not condition:
        fails.append(name)


# ─────────── 1. Đường báo: việc xong -> đúng phiên chat web ───────────
SID = "sid_test_bao_viec"


async def _run():
    got = []

    async def writer(obj):
        got.append(obj)

    main._CHAT_RUNTIME.add_client("test-client", writer)
    store = main.get_store()
    store.get_or_create(SID, brain="brain", engine="cli", model="x")

    ok, err = await main._notify_owner(main.WEB_CHAT_PREFIX + SID, "✅ Việc 'So sánh skill' đã xong.")
    check(f"việc giao từ web báo được dù Telegram TẮT (err={err!r})", ok is True)

    pushes = [e for e in got if e.get("type") == "push"]
    check("bắn đúng 1 sự kiện push qua WebSocket", len(pushes) == 1)
    check("push mang đúng session_id để client định tuyến",
          bool(pushes) and pushes[0].get("session_id") == SID)
    check("push mang nội dung báo cáo",
          bool(pushes) and "So sánh skill" in (pushes[0].get("content") or ""))

    # Ghi vào kho phiên TRƯỚC khi bắn: đóng tab / F5 rồi mở lại vẫn còn.
    msgs = store.get_messages(SID)
    check("kết quả lưu vào kho phiên (F5 vẫn còn)",
          bool(msgs) and msgs[-1]["role"] == "assistant" and "So sánh skill" in msgs[-1]["content"])

    # Không được bịa thành công khi chẳng có kênh nào.
    ok2, err2 = await main._notify_owner("", "báo linh tinh")
    check("không rõ người nhận + Telegram tắt -> vẫn báo thất bại có lý do",
          ok2 is False and "Telegram" in err2)
    ok3, err3 = await main._notify_owner(main.WEB_CHAT_PREFIX, "rỗng")
    check("tiền tố web: nhưng thiếu mã phiên -> thất bại, không im lặng",
          ok3 is False and "phiên chat web" in err3)

    # Telegram vẫn là đường riêng: chat_id thường KHÔNG được coi là phiên web.
    ok4, err4 = await main._notify_owner("123456789", "gửi telegram")
    check("chat_id Telegram vẫn đi nhánh Telegram như cũ",
          ok4 is False and "Telegram" in err4)


asyncio.run(_run())


# ─────────── 2. Javis phải BIẾT mã phiên và nói đúng sự thật ───────────
blk = channel_context.build_channel_block("dashboard", {"session_id": "abc123"}, port=7777)
check("khối kênh dashboard nêu mã phiên chat hiện tại", "abc123" in blk)
check("dạy Javis gắn chat_id 'web:<sid>' khi giao việc", '"chat_id":"web:abc123"' in blk)
check("dạy Javis gắn owner_chat cho loop", 'owner_chat: "web:abc123"' in blk)
check("cấm hứa ngồi đợi rồi tổng hợp",
      "KHÔNG hứa" in blk and "đợi các agent chạy xong" in blk)
check("chỉ đường thay thế: giao thêm việc tổng hợp bằng deps", "deps" in blk)

# Không có mã phiên (đường gọi cũ) thì không được vỡ, chỉ là thiếu khối đó.
blk0 = channel_context.build_channel_block("dashboard", port=7777)
check("thiếu mã phiên vẫn dựng được khối kênh, không nổ", "Dashboard web Javis" in blk0)
check("thiếu mã phiên thì không bịa ra hướng dẫn web:", "web:" not in blk0)

# Telegram giữ nguyên đường cũ.
tblk = channel_context.build_channel_block("telegram", {"chat_id": "999"}, port=7777)
check("nhánh Telegram vẫn dạy kèm chat_id như cũ", '\\"chat_id\\":\\"999\\"' in tblk or '"chat_id":"999"' in tblk)


# ─────────── 3. Client hiển thị được tin đẩy vào ───────────
_push = APP.split('if (data.type === "push")', 1)
check("app.js có nhánh xử lý sự kiện push", len(_push) == 2)
_body = _push[1].split("if (data.type === \"status\")", 1)[0] if len(_push) == 2 else ""
check("push vẽ thành bong bóng Javis", "appendJavisMessage(data.content" in _body)
# Bỏ chú thích trước khi soi: chú thích được quyền NHẮC tới turns[sid] để giải thích vì sao
# không đụng vào nó.
_code = re.sub(r"//[^\n]*", "", _body)
check("push KHÔNG đụng turns[sid] (lượt đang chạy vẫn stream bình thường)",
      "turns[" not in _code and "t.bubble" not in _code)
check("đang xem phiên khác thì vẫn làm tươi Lịch sử để phiên đó nổi lên",
      "notifySessions();" in _body)


# ─────────── 4. System prompt ───────────
check("system prompt nêu 3 kênh nhận báo theo nơi giao việc",
      '"web:<mã phiên chat>"' in CLAUDE_MD and "chat_id của người đang nói" in CLAUDE_MD)
check("system prompt cảnh báo bỏ trống là mất hút khi chưa đấu Telegram",
      "mất hút" in CLAUDE_MD)
check("system prompt cấm hứa ngồi đợi tổng hợp",
      re.search(r"KHÔNG hứa .*đợi việc chạy xong rồi tổng hợp", CLAUDE_MD) is not None)


if fails:
    raise SystemExit(f"\nFAIL - test_bao_viec_ve_chat_web: {len(fails)} lỗi")
print("\nOK - test_bao_viec_ve_chat_web: tất cả pass")
