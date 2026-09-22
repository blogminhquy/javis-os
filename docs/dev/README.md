# Wiki kỹ thuật Javis OS

Tài liệu dành cho **người sửa code Javis** (không phải người dùng cuối). Người dùng cuối đọc `docs/01..18-*.md`.

Mục tiêu: một người mới clone repo về có thể hiểu **cái gì nằm ở đâu, vì sao lại thế, sửa thì sửa chỗ nào** mà không phải đọc hết 18k dòng Python.

## Đọc theo thứ tự này

| # | Trang | Trả lời câu hỏi |
|---|-------|-----------------|
| 1 | [Kiến trúc tổng quan](01-kien-truc.md) | Javis gồm những lớp nào, một lượt chat chạy qua đâu |
| 2 | [Backend - server/](02-backend.md) | 5000 dòng `main.py` chia thế nào, API nào có sẵn, thêm endpoint ra sao |
| 3 | [Frontend - dashboard/](03-frontend.md) | Rail + router trang, thêm một trang mới, các thủ thuật DOM cần biết |
| 4 | [Bộ não, MCP Hub, Plugin, Skill](04-engine-hub-plugin-skill.md) | Engine chọn provider kiểu gì, tool đi qua đâu, 3 mức quyền enforce ở đâu |
| 5 | [Brain (vault) và quy ước file](05-brain-vault.md) | Cấu trúc vault, agent/skill/workflow/loop/memory/wiki ghi ở đâu |
| 6 | [Bẫy, quy ước, quy trình phát hành](06-bay-quy-uoc-release.md) | Những chỗ đã cắn người trước, và cách ra một phiên bản |

## Hồ sơ kế hoạch (lịch sử quyết định)

Hai tài liệu này ghi **vì sao** kiến trúc thành ra như hiện tại. Đọc khi cần hiểu bối cảnh một quyết định cũ:

- [Kế hoạch Agent SDK](2026-07-ke-hoach-agent-sdk.md) - bỏ nhánh spawn Claude CLI bằng Popen, chuyển hẳn sang `claude-agent-sdk`. Đã khép ở v0.9.37.
- [Kế hoạch Kết nối Hub](2026-07-ke-hoach-ket-noi-hub.md) - vì sao có `mcp_hub.py` và kho connector đa tài khoản.

## Đề xuất đang mở

- [Gộp menu cài đặt](2026-07-gop-menu-cai-dat.md) - rail hiện có 18 mục, 7 trong đó là cài đặt. Kèm một khối UI chết cần xoá.
- [Adaptive Context Runtime](2026-08-adaptive-context-runtime-spec.md) - Phase 0-4 đang chạy shadow: trace, Registry, Resolver và Context Compiler thích ứng để capability tăng mà prompt ban đầu không tăng tuyến tính.
- [Javis CLI](2026-08-cli-spec.md) - đưa Javis ra terminal như một KÊNH thứ ba (sau dashboard và Telegram), bằng client mỏng chứ không nhân bản runtime. Kèm bốn chỗ đang thiếu và kế hoạch bốn giai đoạn.
- [Bot chuyên trách](2026-08-bot-chuyen-trach-spec.md) - biến Agent sẵn có thành chatbot chuyên một lĩnh vực, trả lời khách qua Telegram và trong nhóm chăm sóc khách hàng. Điểm cốt lõi: bot khách hàng KHÔNG phải bot của chủ đổi prompt, vì mọi giả định an toàn đảo ngược khi người nhắn là khách lạ. Đã chốt mỗi bot một brain riêng, một token riêng, và có trang Chatbot làm cửa vào. **Kiến trúc chốt xong, chưa viết mã.**
- [Kênh Zalo Bot](2026-08-zalo-bot-spec.md) - đấu API Bot chính thức của Zalo làm KÊNH THỨ TƯ (sau dashboard, Telegram, CLI). Điểm cốt lõi: chỉ viết một lớp vận chuyển mới cắm vào `_tg_answer` sẵn có, không nhân bản gateway. Kèm bảy chỗ Zalo khác Telegram làm gãy UX hiện tại (không sửa/xoá được tin, không có nút bấm, không có sendDocument) và bảy giai đoạn. **Chưa viết mã.**
- [Đa ngôn ngữ](2026-08-da-ngon-ngu-spec.md) - Javis nói được nhiều thứ tiếng, và thêm ngôn ngữ thứ N+1 là thêm DỮ LIỆU chứ không phải sửa mã. Điểm cốt lõi: "đa ngôn ngữ" là BỐN việc khác nhau bị gọi chung một tên (trả lời, giao diện, logic, locale), và tầng LOGIC là tầng nguy hiểm nhất vì nó hỏng trong im lặng - 9 cổng chặn và bộ phân loại đang khoá cứng vào từ khoá tiếng Việt, người dùng nói tiếng khác thì đường tắt nuốt câu hỏi cần dữ liệu live và bộ bắt "khai man đã làm xong" không bao giờ nổ. Chốt một bản `CLAUDE.md` duy nhất, lớp bộ từ vựng thay regex nhúng cứng, và luật suy biến "thiếu từ vựng làm Javis TỐN HƠN chứ không LỎNG HƠN". Kèm sổ tay thêm ngôn ngữ mới và sáu giai đoạn. **Chưa viết mã.**
- [Spec 10 ý tưởng trong sổ tay](2026-08-backlog-spec.md) - chốt cách làm cho sổ "Ý tưởng phát triển Javis" ngày 2026-08-04: ghim/Project/icon cho hội thoại, link .md bấm được, khung sửa dính, chọn skill có tìm kiếm, phân trang nhật ký, connector NotebookLM, gửi ảnh Zalo. Chín ý đã làm ở 0.18.0; ý "chatbot cho Agent" còn để mở kèm ba cách hiểu.
- [Tầng Gói mở rộng](2026-09-tang-goi-mo-rong-spec.md) - connector và plugin thành GÓI cài được lúc chạy (zip, URL hoặc repo riêng, sau đó là kho công khai), giữ nguyên lõi FastAPI, không đi theo kiểu seam của deepseek-harness. Điểm cốt lõi: chỉ cần chạm HAI điểm nút (`mcp_catalog.load` và `plugins_host._iter_plugin_dirs`), và ranh giới tin cậy là BỀ MẶT THỰC THI chứ không phải "có file .py hay không" - một gói không một dòng Python vẫn chạy được `npx` với toàn bộ biến môi trường của server qua `transport: stdio`. Kèm bốn lỗi thật tìm ra lúc khảo sát (xoá kết nối để lại credential sống và tiến trình con 900 giây, `safeHref` chặn nhầm kèm ba chỗ render bỏ qua nó, `share_bundle.slugify` ăn mất chữ Đ, bộ dò chatbot bí chỉ biết tiếng Việt) và tám giai đoạn. **Giai đoạn 0 xong ở 0.55.19** (xoá kết nối cho sạch, `server/purge.py`), **Giai đoạn 1 xong ở 0.55.20 và 0.55.21** (`core_off.py` gỡ được connector lõi kèm chốt mồ côi; `packs.py` nạp gói từ `STATE_DIR/packs/`). **Giai đoạn 2 xong ở 0.55.22** (`pack_install.py` + `routes/packs.py` + trang Gói: cài từ .zip có màn hình xem trước, gỡ sạch, plugin bundled gỡ được). **Giai đoạn 4 xong ở 0.55.23** (gói mang được tool, mã khoá theo chữ ký nội dung). **Kho gói xong ở 0.55.24** (`packs_fetch` chốt SSRF, `packs_store`, lưới kho, `docs/dev/pack-store-index.md`). **Gói mang được agent/workflow/skill, tab gói cộng đồng và token repo riêng xong ở 0.55.25** (`pack_vault.py` dùng lại khuôn hash của `system_sync`: không bao giờ ghi đè hay xoá thứ người dùng đã sửa). Còn lại: trang hướng dẫn của gói, và Giai đoạn L.
- [Voice V1](2026-09-voice-v1-spec.md) - nâng giọng nói từ "ghi xong, gửi, đợi, đọc cả câu" thành hội thoại có đạo diễn, KHÔNG phụ thuộc OpenAI Realtime: tai vẫn là Web Speech, não là engine đang chọn, miệng là Edge TTS stream. Mượn thiết kế của livekit/agents (endpointing hai ngưỡng, chen ngang tạm dừng rồi hoàn nguyên, chỉ lưu phần đã nghe thấy), không mượn dependency. Kèm tool `javis_ui` (mở trang/file/việc trên dashboard, có ack) và plugin `desktop-apps` (mở/đóng app trên máy chạy Javis). Ba tài liệu: [bản đồ hiện trạng](2026-09-voice-v1-ban-do-hien-trang.md) (Phase 0), spec, [kế hoạch task](2026-09-voice-v1-ke-hoach.md). **Làm xong ở 0.56.0** (2026-09-14).
- [Voice V2](2026-09-voice-v2-spec.md) - bộ não giọng nói riêng (`voice_brain.py`: một tiến trình `agy --input-format stream-json` sống lâu, đo 1,3-2,0 s mỗi lượt; hoặc Groq/Gemini/OpenAI/OpenRouter), nghe bằng Groq Whisper qua `POST /stt`, và bậc Live nghe nói thẳng (`voice_live.py`: Gemini Live / OpenAI Realtime sau một giao diện provider, proxy qua `/ws/voice-live`). Cả ba chọn ở thẻ mới trong Cài đặt → Giọng nói. **Làm xong ở 0.57.0** (2026-09-14).
- [Coding Workspace](2026-09-coding-workspace-spec.md) - mục thứ hai của nhóm Code (sau Terminal): một phiên coding gắn với một repo, một nhánh, một worktree và một mức quyền. Phạm vi gói trong MỘT phiên sửa (năm việc), vì ba chỗ then chốt đã sẵn: `cwd` là tham số của engine (`claude_cli.py:988`, seam `main.py:2021`), kho phiên đã có cột `channel` để lọc theo tiền tố `coding:`, và khung chat cho mượn qua `_borrowChatNodes`. Bề mặt mã mới còn ba thứ: sổ repo, hàng chip ngữ cảnh, worktree kèm điểm hồi git. KHÔNG có auto switch model (chủ dự án chốt 2026-09-22: đổi engine giữa chừng làm hỏng mạch code), chỉ đổi bằng tay. Bỏ khỏi v0.1: quota router, cột Work Tree cố định, tầng Handoff riêng, ép model API qua Codex CLI, nhánh ASA. **Làm xong ở 0.63.0**, rồi ba lượt sửa theo phản hồi dùng thử: **0.63.1** (vào là chat được ngay, THƯ MỤC chứ không phải repo), **0.63.2** (cột trái là chính cột hội thoại bên Trò chuyện, thêm chế độ Plan), **0.63.4** (thêm thư mục bằng hộp duyệt `JavisFolderPicker` thay vì gõ đường dẫn, icon `</>`).
- [Nhân prompt và tầng luật theo carrier](2026-09-nhan-prompt-va-tang-luat-spec.md) - `CLAUDE.md` chạm trần CI còn 23 ký tự, và trần đã bị nâng một lần. Điểm cốt lõi: vấn đề không phải luật quá nhiều mà là viết prose là cách RẺ NHẤT để đánh thuế lên một bậc tự do thừa của model, nên mọi luật đều lăn xuống một file; dọn chỗ trống mà để nguyên độ dốc thì chỗ trống sẽ đầy lại. Chốt ba hằng số: nhân chỉ chứa thứ tỉ lệ với TÍNH CÁCH Javis (bề mặt đi cùng carrier của nó), trần nhân 8.000 ký tự đóng băng và không vay được, và mỗi luật phải khai `enforced_by` để luật nào code đã ép thì tự động bị xoá khỏi prompt. Bằng chứng nằm sẵn trong repo: `javis_schedule` có tool nên tốn ~600 ký tự prose, tạo agent không có tool nên tốn 2.875 cho việc đơn giản hơn. Kèm khung DỐC và VÁCH để đọc mọi con số hiệu suất (gọt nghìn ký tự là dốc, vượt trần argv là vách 30-60 giây), sáu lỗi thật (`AGY_BOOTSTRAP_MAX_CHARS` mâu thuẫn với `_tran_argv` nên Antigravity luôn phải đi đường file, hook `pre_tool_call` không chặn được gì, skill thứ 21 vô hình với router, `_fit_memory_index` có bậc cuối là mất ký ức, `build_system_prompt` chạy lại mỗi lượt, cache 1 giờ viết sẵn chưa ai gọi), bảng hoà vốn cho ngưỡng dừng 98%, và 15 việc. **Chưa viết mã.**

## Đã cân nhắc rồi quyết định KHÔNG làm

Giữ lại vì lý do từ chối thường bền hơn thứ bị từ chối, và vì phần khảo sát bên trong vẫn
dùng lại được cho việc khác.

- [Đấu 9Router vào trang Models](2026-08-9router-spec.md) - gác lại 2026-08-04. 9Router là
  proxy chạy TẠI MÁY người dùng, giá trị cốt lõi là ghép nhiều tài khoản rẻ lại với nhau, đi
  ngược hướng doanh nghiệp mà Javis đang nhắm. Ba phần vẫn dùng lại được: bức tường "localhost
  trên VPS không phải máy người dùng", phép thử mất tool calling trong im lặng, và bản đồ chỗ
  phải chạm khi thêm một nhà cung cấp mới.

## Quy ước của chính tài liệu này

- Tiếng Việt, văn nói, không dùng ký tự em dash (làm giọng đọc TTS bị khựng - đây là luật toàn dự án, xem `CLAUDE.md`).
- Trỏ tới code bằng `đường/dẫn.py:dòng` để bấm được trong editor.
- Nói **vì sao** trước, **cái gì** sau. Cái gì thì đọc code là ra, vì sao thì không.
