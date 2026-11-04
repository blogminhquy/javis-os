---
bump: patch
title: Reduce subscription context and separate request usage from turn totals
---
## vi
### Sửa lỗi
- Prompt gọn cho Codex được bật riêng, giữ hồ sơ, project, phiên và đường khám phá skill. Bộ nhớ có thể trả rỗng khi không liên quan, vẫn giữ recall theo tên và câu tiếp nối.
- Xoay thread dựa vào input request cuối đã đo, không lấy tổng nhiều vòng. Telemetry tách cache, uncached, tổng lượt, event và số request được xác minh.

## en
### Fixed
- An opt-in compact Codex prompt preserves profile, project, session and skill discovery. Memory may return no unrelated results while retaining name and continuation recall.
- Thread rotation uses measured last-request input instead of multi-request turn totals. Telemetry separates cache, uncached input, turn totals, observations and verified requests.
