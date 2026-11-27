#!/bin/bash
# SessionStart: nhắc phiên Claude Code trên cloud đặt số phiên bản Javis OS lúc bắt đầu vào đầu tên phiên,
# để mở danh sách phiên là biết phiên nào làm từ bản nào (chủ repo, 27/11/2026).
# Chỉ chạy trên cloud: Javis trên máy người dùng cũng gọi claude với cwd là repo này, ở đó script im lặng.
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || exit 0
f="${CLAUDE_PROJECT_DIR:-.}/VERSION"
[ -f "$f" ] || exit 0
v="$(tr -d ' \r\n' < "$f")"
[ -n "$v" ] || exit 0
echo "Phiên này bắt đầu từ Javis OS v$v. Trong lượt đầu, trước việc khác: gọi get_session (không truyền session_id) lấy tên phiên, rồi set_session_title đổi thành \"v$v · <tên hiện tại>\". Tên đã mở đầu bằng \"v\" kèm số phiên bản thì để nguyên."
