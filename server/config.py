"""
Cấu hình tập trung của Javis OS - đọc/ghi server/settings.json (gitignored, chứa secret).
Gồm: workspace, tài khoản admin (mật khẩu hash), model engine, telegram.
Auth CHỈ bật khi đã đặt mật khẩu → bản local chưa đặt vẫn chạy như cũ.
"""
import json
import os
import hashlib
import secrets
from pathlib import Path

# Mọi state Javis tự ghi (settings, auth sessions, loop config) nằm ở JAVIS_STATE_DIR.
# Mặc định = server/ (không đổi trên máy cũ). Docker/VPS đặt = /data/state (volume ghi được,
# vì code tree /app là read-only trong container).
STATE_DIR = Path(os.getenv("JAVIS_STATE_DIR", str(Path(__file__).parent)))
try:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

SETTINGS_PATH = STATE_DIR / "settings.json"
# Logo/avatar tùy chỉnh (đổi qua UI) lưu ở đây - ghi được + giữ qua update (Docker volume),
# vì code tree dashboard/ là read-only trong container.
BRANDING_DIR = STATE_DIR / "branding"

_DEFAULT = {
    "workspace_name": "Javis OS",
    "setup_done": False,                       # đã qua bộ cài đặt lần đầu chưa
    "auth": {"username": "", "password_hash": "", "salt": ""},
    # Logo/avatar hiển thị (góc trên, thanh bên, màn đăng nhập). logo_ext rỗng = dùng ảnh mặc định.
    "branding": {"logo_ext": "", "logo_v": 0},
    # Tên miền riêng cho HTTPS tự động (Caddy On-Demand TLS hỏi /tls-check trước khi xin cert).
    "domain": {"custom": ""},
    # Nhà cung cấp giọng đọc (TTS). edge = Edge TTS miễn phí (mặc định, dự phòng).
    # openai = OpenAI TTS (dùng model.openai_api_key). elevenlabs = ElevenLabs (key riêng).
    "voice": {
        "tts_provider": "edge",                       # edge | openai | elevenlabs
        "openai_tts_voice": "alloy",                  # alloy|echo|fable|onyx|nova|shimmer|ash|sage|coral
        "openai_tts_model": "gpt-4o-mini-tts",        # hoặc tts-1 / tts-1-hd
        "elevenlabs_key": "",
        "elevenlabs_voice": "21m00Tcm4TlvDq8ikWAM",   # Rachel (premade, đa ngôn ngữ) - đổi được
        "elevenlabs_model": "eleven_multilingual_v2",
    },
    "model": {
        # --- Mô hình MAIN MODEL theo provider (mới) ---
        # Rỗng = suy ra từ legacy engine (config cũ không vỡ); UI set vào đây khi user đổi model.
        "main": {"provider": "", "model": ""},
        # Model phụ cho việc NỀN (loop/metrics/ingest) - alias Claude qua CLI. "" = dùng mặc định
        # (không đổi). Đặt model rẻ (vd haiku) để tiết kiệm khi chạy nền nhiều.
        "auxiliary": {"model": ""},
        # Độ sâu suy nghĩ (reasoning/thinking) khi trả lời chat: off | low | medium | high.
        # Anthropic API/OpenRouter → adaptive thinking + effort; OpenAI → reasoning_effort (chỉ o-series);
        # Claude Code CLI → chèn từ khoá think/ultrathink vào prompt. off = trả lời nhanh như cũ.
        "reasoning": "off",
        # --- Credentials theo provider ---
        # Gói Claude Code (provider 'anthropic-cli') xác thực bằng CÁI GÌ:
        #   "subscription" (mặc định) - phiên đăng nhập của chính Claude Code, tức gói Pro/Max
        #       người dùng đang trả. Javis KHÔNG đọc token đó nữa; nó chỉ chạy binary `claude`
        #       và để chính sản phẩm của Anthropic lo đăng nhập.
        #   "api_key" - truyền `anthropic_api_key` xuống cho binary `claude` qua biến môi
        #       trường, tức trả tiền theo lượt dùng qua Claude Console. Đây là đường Anthropic
        #       chỉ định cho sản phẩm bên thứ ba (xem claude_auth.CANH_BAO_SUBSCRIPTION).
        # Đổi ở trang Models. Cả hai đều giữ NGUYÊN năng lực: Bash, WebFetch, MCP, nối phiên cũ.
        "claude_auth": "subscription",
        "openrouter_key": "",
        "anthropic_api_key": "",               # provider Anthropic API (P2)
        "openai_api_key": "",                  # provider OpenAI (ChatGPT API)
        "gemini_api_key": "",                  # provider Google Gemini (endpoint OpenAI-compat)
        "groq_api_key": "",                    # provider Groq (endpoint OpenAI-compat, suy luận rất nhanh)
        # Provider 'ollama' = Ollama Cloud (ollama.com). Bản chạy trên máy nhà KHÔNG được đấu,
        # cố ý: nó đòi thêm một ô địa chỉ - ca đặc biệt duy nhất của cả lớp nhà cung cấp -
        # trong khi phần đông người dùng Javis chạy nó trên VPS, nơi "localhost" là chính cái
        # container chứ không phải máy họ.
        "ollama_key": "",
        # Provider 'openai-oauth' - đăng nhập ChatGPT Plus/Pro qua device-code (xem openai_oauth.py).
        "openai_oauth": {"access_token": "", "refresh_token": "", "id_token": "", "account_id": "", "plan": "", "expires_at": 0},
        # --- Legacy: giữ đồng bộ với main để engine cũ không vỡ (engine/claude_model/openrouter_model) ---
        "engine": "cli",                       # cli (Claude Code, đủ MCP) | openrouter | anthropic-api
        "claude_model": "",                    # "" = mặc định CLI; hoặc opus/sonnet/haiku/fable
        "openrouter_model": "openai/gpt-4o-mini",
        # Catalog model theo provider (Telegram /model dùng key 'claude'+'openrouter'; picker dùng cả 3).
        "catalog": {
            # anthropic-cli: danh sách nền, LUÔN dùng được kể cả khi máy không có API key.
            # /provider/models hỏi API Anthropic bằng `anthropic_api_key` (nếu có) rồi ghi đè
            # danh sách THẬT vào đây. Không có key thì giữ nguyên các alias dưới đây - chúng
            # luôn trỏ tới bản mới nhất của từng dòng nên không bao giờ lạc hậu.
            "claude": ["opus", "sonnet", "haiku", "fable"],
            "anthropic-api": ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"],
            "openai": ["gpt-4o", "gpt-4o-mini", "o3-mini"],                        # OpenAI API
            "gemini": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],  # Google Gemini API (picker load động)
            "groq": ["llama-3.3-70b-versatile", "qwen3-32b", "openai/gpt-oss-120b"],  # Groq (picker load động)
            # Không ghim model Codex: /provider/models lấy catalog LIVE bằng
            # codex app-server model/list và nhớ lại lần thành công gần nhất.
            "openai-oauth": [],
            "openrouter": ["openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet", "google/gemini-2.0-flash-001", "deepseek/deepseek-chat"],
        },
    },
    # Ảnh sinh bằng javis_generate_image.
    # strip_c2pa: gỡ Content Credentials (C2PA) - dấu nguồn gốc do nhà cung cấp ảnh nhúng sẵn
    # để nói "ảnh này do AI tạo". MẶC ĐỊNH TẮT: giữ nguyên dấu là hành vi an toàn, và bản fork
    # nào cũng bắt đầu ở trạng thái này. Bật lên là quyết định CÓ Ý THỨC của chủ workspace,
    # kèm trách nhiệm tự công bố nội dung AI theo luật/điều khoản nền tảng nơi họ đăng.
    "image": {"strip_c2pa": False},
    # Vùng cache media của brain: attachments/ + inbox/. Ảnh là NGUYÊN LIỆU đi qua, không
    # phải tri thức - đọc xong rút thành .md là đủ dùng, nên chúng tự hết hạn thay vì nằm
    # mãi làm phình đĩa VPS. Muốn giữ ảnh lâu dài thì đấu kho ngoài (Drive), đừng để Javis ôm.
    # max_age_days / max_mb <= 0 = tắt luật tương ứng. enabled=False = không dọn gì cả.
    # staging_days: hạn RIÊNG cho STATE_DIR/.staging - nơi file dán vào khung chat rơi xuống.
    # Ngắn hơn hẳn vì đó là chỗ trung chuyển một lượt chat, không ai mở lại bao giờ.
    "media": {"enabled": True, "max_age_days": 30, "max_mb": 300, "staging_days": 3},
    "telegram": {"enabled": False, "token": "", "chat_id": ""},
    # Kênh Zalo Bot của CHỦ (API chính thức bot.zaloplatforms.com). Cùng hình dạng với telegram
    # để trang Kênh và mọi chỗ định tuyến thông báo chỉ phải học một khuôn.
    #
    # `chat_id` là whitelist, và trên Zalo nó là chuỗi HEX chứ không phải số. Zalo KHÔNG có
    # công cụ kiểu @userinfobot để tự tra id của mình, nên đừng bắt user đi tìm: người lạ nhắn
    # cho bot thì Javis đưa họ vào hàng chờ kèm mã ghép nối, chủ bấm một nút là xong.
    # Xem `_ZALO_CHO` trong main.py.
    "zalo_bot": {"enabled": False, "token": "", "chat_id": ""},
    # Backup brain lên GitHub (repo RIÊNG TƯ). token = GitHub PAT (fine-grained, quyền Contents).
    # Lưu trong settings.json (đã gitignored) - KHÔNG bao giờ đẩy lên brain repo.
    "backup": {"enabled": False, "repo_url": "", "token": "", "branch": "main",
               "interval_hours": 6, "last_backup": 0.0, "last_status": ""},
    "dashboard": {
        # graph_enabled=False → vào thẳng Console, KHÔNG dựng đồ thị (nhẹ cho VPS/điện thoại).
        # Frontend cũng tự ép lite-mode khi màn hình hẹp dù cờ này bật.
        "graph_enabled": True,
    },
    # MCP do Javis quản lý (registry connection ở mcp_servers.json). strict=True → CHỈ dùng
    # kết nối của Javis (--strict-mcp-config), bỏ qua config MCP sẵn có của máy.
    # hub=True (mặc định): mọi engine đấu qua MCP HUB (1 entry "javis" - đa tài khoản, quyền,
    # audit tại hub). Đặt false để về chế độ cũ (per-server) nếu gặp sự cố.
    # lazy_tools: chống phình context khi đấu nhiều connector. "auto" = tự bật khi số tool
    # MCP vượt lazy_threshold (mặc định); True/False = ép bật/tắt. Khi bật, hub chỉ phơi
    # 2 meta-tool javis_search_tools/javis_run_tool thay cho hàng trăm schema -> model tự
    # tìm tool theo NGỮ CẢNH rồi mới nạp. lazy_top_k = số tool search trả về mỗi lần.
    # ambient_hint: kèm connector đấu vào TÀI KHOẢN Claude (Drive/Gmail...) vào javis_connections
    # + lazy search cho engine Claude, để model biết chúng tồn tại (gọi qua tool native mcp__*).
    # lazy_char_budget: trần KÝ TỰ schema tool được phơi thẳng trước khi ép bật lazy. Đếm số
    # tool không nói lên chi phí (một javis_use_skill nhúng cả danh sách skill có thể nặng hơn
    # mười tool gọn), nên 'auto' xét cả hai: đông tool HOẶC schema nặng.
    "mcp": {"strict": False, "hub": True, "lazy_tools": "auto", "lazy_threshold": 40,
            "lazy_top_k": 8, "lazy_char_budget": 6000, "ambient_hint": True},
    # Adaptive Context Runtime Phase 0-8. Mọi canary rollout mặc định bằng 0 và mode
    # vẫn shadow, nên production chưa đổi dispatch. Muốn canary phải đồng thời đổi mode=canary,
    # allocation_basis_points > 0 và khai hard quota trong quota_profiles.
    "context_runtime": {
        "mode": "shadow",
        "retention_days": 14,
        "export_enabled": False,
        "estimate_chars_per_token": 3.0,   # heuristic observe-only, reconcile bằng usage thật
        # CHỮ KÝ lựa chọn mức tiết kiệm của người dùng. Rỗng = chưa ai chọn, mức đang chạy
        # chỉ là mặc định của bản đã cài. Xem `_ap_muc_mac_dinh` để biết vì sao thiếu trường
        # này thì mọi lần đổi mặc định về sau đều không tới được máy đã cài.
        # source: "user" (người dùng tự bấm/tự đổi) | "" (chưa chọn bao giờ).
        "preset_choice": {"level": "", "source": "", "at": ""},
        "canary": {
            "policy_version": "fast-path-canary-v1",
            "allocation_basis_points": 0,  # 100 = 1%; hash ổn định theo session
            "salt": "fast-path-canary-v1",
            # Telegram và CLI cũng đi được đường tắt. Tới 0.23.1 danh sách này chỉ có
            # "dashboard", nên người dùng bấm mức Siêu tiết kiệm rồi nhắn qua Telegram
            # vẫn gửi nguyên CLAUDE.md mỗi lượt - trang Cài đặt báo đã bật, mà kênh họ
            # dùng nhiều nhất thì không đi qua dòng code nào của nó.
            "channels": ["dashboard", "telegram", "cli"],
            # Cả ba loại bộ não. "oauth" (gói ChatGPT) gọi thẳng qua Codex Responses, "cli"
            # (gói Claude Code) gọi thẳng qua Messages API bằng chính access token OAuth mà
            # CLI đã lưu. Bản trước để "cli" ngoài danh sách vì chưa có đường gọi thẳng nào
            # không cần API key; nay có rồi, và nếu token hỏng thì lượt đó tự lui về đường
            # thường chứ không ném lỗi ra cho người dùng.
            "provider_kinds": ["api", "oauth", "cli"],
            "registry_max_age_seconds": 900,
            "estimator_safety_factor": 1.35,
            "max_objective_chars": 12000,
            # Điểm khớp tối thiểu để coi là "câu này có thể cần tool" và nhường đường thường.
            # Xét ĐIỂM chứ không xét số ứng viên dò trúng chữ: máy đấu vài trăm tool MCP thì
            # câu nào cũng dò trúng vài cái qua một từ chung, và đường tắt sẽ không bao giờ
            # chạy. Hạ số này = đi tắt nhiều hơn nhưng dễ trả lời hụt; nâng lên = an toàn hơn
            # nhưng tiết kiệm ít đi. Cùng thang điểm với readonly_canary.min_resolver_score.
            "min_resolver_score": 0.45,
            # Không hardcode quota thương mại. Operator thêm rule versioned theo tài khoản thật:
            # {"id":"groq-free", "provider":"groq", "model_pattern":"llama-*",
            #  "rolling_tpm":12000, "context_window":131072,
            #  "reserved_output_tokens":1200, "window_seconds":60}
            "quota_profiles": [],
        },
        # Phase 6: đúng một capability read-only, một vòng lập arguments và một vòng tổng hợp.
        # Chỉ capability khớp capability_profiles mới được chạy. Danh sách rỗng là fail-closed.
        "readonly_canary": {
            "policy_version": "readonly-single-step-v1",
            "allocation_basis_points": 0,
            "salt": "readonly-single-step-v1",
            "channels": ["dashboard"],
            "provider_kinds": ["api"],
            "registry_max_age_seconds": 900,
            "min_resolver_score": 0.45,
            "estimator_safety_factor": 1.35,
            # Nếu để trống, quota dùng các rule Phase 5 ở trên.
            "quota_profiles": [],
            # Ví dụ allowlist: id, source_type, name_pattern, timeout_seconds,
            # excerpt_chars, lease_ttl_seconds, max_artifact_bytes, retention_seconds.
            "capability_profiles": [],
        },
        # Phase 7: planner manifest nhỏ -> exact schema theo step -> evidence bundle.
        # Canary và allowlist riêng Phase 6. quota profile phải có giá input/output thật để
        # monetary budget fail-closed; repository không đoán giá hay quota theo tên provider.
        "orchestrator_canary": {
            "policy_version": "readonly-orchestrator-v1",
            "allocation_basis_points": 0,
            "salt": "readonly-orchestrator-v1",
            "channels": ["dashboard"],
            "provider_kinds": ["api"],
            "registry_max_age_seconds": 900,
            "min_resolver_score": 0.32,
            "estimator_safety_factor": 1.35,
            "max_candidate_manifests": 8,
            "max_cycles": 2,
            "max_total_steps": 6,
            "max_parallel": 3,
            "max_model_rounds": 10,
            "max_evidence": 8,
            "max_task_input_tokens": 20000,
            "max_task_output_tokens": 6000,
            "max_cost_usd": 0.05,
            "deadline_seconds": 90,
            # Resume sau restart cần cửa sổ deadline mới, nếu không task chết lâu hơn
            # deadline là không bao giờ resume được. Có trần để một task hỏng không
            # được hồi sinh mãi.
            "max_deadline_extensions": 2,
            "planner_output_tokens": 600,
            "argument_output_tokens": 500,
            "min_information_gain": 0.20,
            "per_evidence_excerpt_chars": 2500,
            "failure_repeat_limit": 2,
            # Có thể dùng quota Phase 5, nhưng rule Phase 7 chỉ hợp lệ nếu thêm:
            # input_cost_per_million và output_cost_per_million.
            "quota_profiles": [],
            # Danh sách rỗng luôn fail-closed. Mỗi group có thể giới hạn args/TTL/timeout riêng.
            "capability_profiles": [],
        },
        # Phase 10: workflow chạy qua đồ thị có checkpoint thay vì vòng lặp không trạng thái.
        # Danh sách slug rỗng = fail-closed. Node ghi LUÔN dừng hỏi người dùng, cờ dưới
        # chỉ quyết định workflow CÓ node ghi được chạy tới chỗ hỏi hay bị chặn từ đầu.
        "workflow_canary": {
            "policy_version": "workflow-graph-canary-v1",
            "allocation_basis_points": 0,
            "salt": "workflow-graph-canary-v1",
            "allowed_slugs": [],
            "max_nodes": 24,
            "max_parallel": 3,
            "node_timeout_seconds": 300,
            "max_nesting_depth": 1,
            "allow_write_nodes": False,
        },
        # Phase 11: agent = workflow có quyền tự lập lại kế hoạch. Tập quyền được ghim
        # từ đồ thị gốc và KHÔNG BAO GIỜ nới ra khi replan. Danh sách rỗng = fail-closed.
        "agent_canary": {
            "policy_version": "agent-replan-canary-v1",
            "allocation_basis_points": 0,
            "salt": "agent-replan-canary-v1",
            "allowed_slugs": [],
            "max_replan_rounds": 2,
            "max_total_nodes": 24,
            "max_nodes_per_replan": 3,
            "failure_repeat_limit": 2,
        },
        # Phase 12: chọn model theo từng bước. Lọc năng lực TRƯỚC, xếp hạng giá SAU -
        # rẻ hơn không bao giờ thắng nếu thiếu năng lực bắt buộc (spec mục 9.3).
        # Không đoán năng lực theo tên model: rule nào không khai `supports` thì coi
        # như không có năng lực đó. Danh sách rỗng = giữ nguyên model người dùng chọn.
        "model_router_canary": {
            "policy_version": "model-router-canary-v1",
            "allocation_basis_points": 0,
            "salt": "model-router-canary-v1",
            "step_kinds": ["model_step"],
            "allow_downgrade_on_risk": False,
            # Ví dụ một rule: {"id":"...", "provider":"groq", "model":"llama-3.3",
            #  "supports":["tools"], "context_window":131072,
            #  "input_cost_per_million":0.59, "output_cost_per_million":0.79,
            #  "latency_hint_ms":1200, "reliability":0.99, "data_classes":[]}
            "models": [],
        },
        # Phase 8 dùng hard quota operator khai báo; không đoán TPM/context theo tên model.
        # Có thể để trống để dùng quota_profiles của Fast Path ở trên.
        "context_sources": {"quota_profiles": []},
        # NGÂN SÁCH NGỮ CẢNH cho engine chạy bằng GÓI THUÊ BAO (Claude Code, ChatGPT/Codex).
        #
        # Vì sao phải có mục riêng: quota_profiles ở trên khai hạn mức THƯƠNG MẠI (token mỗi
        # phút, giá tiền) - thứ chỉ tài khoản API mới có và mới tra được. Gói thuê bao không
        # công bố con số nào tương đương, nên đòi khai nó là ép người vận hành bịa số, và
        # fail-closed sẽ cho mọi lượt Claude Code rơi về đường cũ mãi mãi.
        #
        # Ở đây chỉ khai TRẦN NGỮ CẢNH - thứ có thật, tra được, và không dính gì tới tiền.
        # Nó cho Context Compiler một ngân sách để CHỌN LỌC nguồn, chứ không dùng để chặn
        # lượt chat: xem AdaptiveContextCanary._quota và nhánh subscription_soft.
        # 180k là mức thận trọng dưới cửa sổ 200k của các model Claude đang bán.
        "subscription_context": {
            "context_window": 180000,
            "reserved_output_tokens": 8000,
        },
        # TRẦN NGỮ CẢNH MẶC ĐỊNH cho engine dùng API KEY, khi chưa biết gì khác.
        #
        # Vì sao phải có: cùng một lỗ hổng như trần thuê bao ở trên, nhưng ở phía API key và
        # rộng hơn nhiều. `_quota` chỉ nhận hạn mức người vận hành khai tay, mà bảng gợi ý
        # `model_limits.KNOWN_LIMITS` hiện CHỈ có Groq. Nên người dùng OpenRouter, OpenAI,
        # Gemini hay Anthropic API bấm mức Tối ưu là bật một đường fail-closed: trang báo
        # "đã bật, giảm 89%", còn mọi lượt vẫn lặng lẽ gửi nguyên CLAUDE.md. Bốn trên năm
        # engine API key rơi vào ca này.
        #
        # Đây KHÔNG phải suy đoán hạn mức thương mại - thứ module model_limits cố ý từ chối
        # làm. Con số này chỉ là NGÂN SÁCH ĐỂ BIÊN SOẠN: cho Context Compiler biết gói tối đa
        # bao nhiêu, không dùng để chặn lượt chat (soft, vượt thì về đường cũ chứ không
        # reject) và không tự nhận là biết TPM của ai. Nhà cung cấp vẫn là bên duy nhất có
        # quyền nói không, và lần nó nói thì limit_learner ghi lại con số THẬT, con số đó
        # xét trước cái trần này ngay từ lượt sau.
        #
        # 32k là mức thận trọng: nằm dưới cửa sổ của gần như mọi model API đang bán, mà vẫn
        # rộng gấp nhiều lần một capsule Javis điển hình (khoảng 1.000 token).
        "api_context": {
            "context_window": 32000,
            "reserved_output_tokens": 4000,
        },
        # NGÂN SÁCH TỪ HẠN MỨC JAVIS TỰ HỌC ĐƯỢC (limit_learner).
        #
        # Vì sao cần: fail-closed bắt phải khai quota_profiles trước, nên tới khi có người
        # ngồi khai thì mọi lượt đã rơi về đường cũ - đúng lúc bị siết lại là đúng lúc phần
        # tiết kiệm không chạy. Nhưng chính câu báo lỗi của nhà cung cấp ĐÃ nói ra hạn mức
        # thật của tài khoản này, đáng tin hơn mọi con số tra tài liệu. Sau lần bị từ chối
        # đầu tiên, dùng luôn con số đó làm ngân sách thay vì đợi khai tay.
        #
        # safety_factor: chừa biên vì hạn mức mỗi phút là cửa sổ TRƯỢT (phần vừa gửi hỏng vẫn
        # còn nằm trong cửa sổ) và bộ đếm token của Javis chỉ là ước lượng.
        "learned_quota": {
            "enabled": True,
            "reserved_output_tokens": 1200,
            "safety_factor": 0.85,
        },
        # Ba rollout độc lập. Nguồn nào lỗi/thiếu tự tin chỉ nguồn đó quay về cơ chế cũ.
        #
        # conversation_state CHỈ chạy trên engine API, cố ý. Claude Code và Codex tự nối lại
        # mạch hội thoại bằng session/thread của chính chúng (--resume, codex exec resume),
        # nên nhét thêm một cửa sổ transcript vào system prompt là gửi lịch sử HAI LẦN - vừa
        # tốn token vừa dễ làm model lẫn thứ tự. Hai nguồn kia không có vấn đề đó.
        "conversation_state_canary": {
            "policy_version": "conversation-state-v1",
            "allocation_basis_points": 0,
            "salt": "conversation-state-v1",
            "channels": ["dashboard"], "provider_kinds": ["api"],
            "recent_messages": 6,
        },
        "memory_canary": {
            "policy_version": "sourced-memory-v1",
            "allocation_basis_points": 0,
            "salt": "sourced-memory-v1",
            "channels": ["dashboard", "telegram", "cli"], "provider_kinds": ["api", "cli", "oauth"],
            "max_items": 6, "min_confidence": 0.38,
        },
        "lazy_skill_canary": {
            "policy_version": "lazy-skill-v1",
            "allocation_basis_points": 0,
            "salt": "lazy-skill-v1",
            "channels": ["dashboard", "telegram", "cli"], "provider_kinds": ["api", "cli", "oauth"],
            "max_body_chars": 12000,
        },
        # Phase 9: tool WRITE, bật theo TỪNG capability group, không có cờ chung.
        # Ba tầng fail-closed: allocation 0, capability_profiles rỗng, và mọi write
        # đều phải được người dùng gõ lại mã xác nhận mới chạy.
        # Mẫu một group (KHÔNG phải giá trị mặc định):
        #   {"id": "calendar-create", "source_type": "mcp",
        #    "source_id_pattern": "google-calendar", "name_pattern": "*create_event*",
        #    "timeout_seconds": 30, "lease_ttl_seconds": 300,
        #    "resource_lock_fields": ["calendar_id", "start"],
        #    "reconcile_capability_id": "<id capability read để kiểm chứng>",
        #    "reconcile_arguments": {...}, "reconcile_success_marker": "<chuỗi nhận biết>"}
        # Group không khai được đường reconcile thì mặc định về legacy, trừ khi
        # operator chấp nhận rủi ro bằng "allow_unreconcilable": true.
        "write_canary": {
            "policy_version": "write-single-step-v1",
            "allocation_basis_points": 0,
            "salt": "write-single-step-v1",
            "channels": ["dashboard"], "provider_kinds": ["api"],
            "registry_max_age_seconds": 900,
            "min_resolver_score": 0.55,
            "estimator_safety_factor": 1.35,
            "confirmation_ttl_seconds": 900,
            "quota_profiles": [],
            "capability_profiles": [],
        },
    },
}


# Các trường SECRET trong settings.json → mã hoá at rest (Fernet, qua secrets_store) như MCP secret.
# Backward-compat: giá trị plaintext cũ đọc vẫn ra nguyên văn; lần ghi kế tiếp tự bọc "enc:".
# Mất file .secret_key → decrypt trả "" (nhập lại key) - đánh đổi giống MCP secret, an toàn hơn lộ key.
_SECRET_PATHS = (
    "model.openrouter_key", "model.anthropic_api_key", "model.openai_api_key", "model.gemini_api_key",
    "model.groq_api_key", "model.ollama_key",
    "model.openai_oauth.access_token", "model.openai_oauth.refresh_token", "model.openai_oauth.id_token",
    "telegram.token", "zalo_bot.token", "backup.token", "voice.elevenlabs_key",
)


def _transform_secret_fields(cfg, fn):
    """Áp fn (encrypt|decrypt) lên các trường secret theo _SECRET_PATHS, tại chỗ. Bỏ qua nếu thiếu."""
    for path in _SECRET_PATHS:
        parts = path.split(".")
        parent = cfg
        for p in parts[:-1]:
            if isinstance(parent, dict) and isinstance(parent.get(p), dict):
                parent = parent[p]
            else:
                parent = None
                break
        key = parts[-1]
        if isinstance(parent, dict) and isinstance(parent.get(key), str) and parent.get(key):
            parent[key] = fn(parent[key])
    return cfg


# Cache read_settings theo (mtime_ns, size) của settings.json: middleware auth/CSRF gọi
# gate_active() -> read_settings() TRÊN MỌI REQUEST, mỗi lần đọc file + giải mã Fernet ~5-8ms
# (x2 middleware = 10-16ms/request chỉ để check đăng nhập). File đổi (kể cả write_settings
# ghi đè) thì mtime/size đổi -> tự đọc lại. Trả deep copy để caller sửa thoải mái không bẩn cache.
_SETTINGS_CACHE = {"sig": None, "cfg": None}


def _deep_merge(base: dict, patch: dict) -> dict:
    """Gộp `patch` lên `base` ĐỆ QUY, sửa tại chỗ, trả lại `base`.

    Vì sao phải đệ quy chứ không phải `.update()` một tầng như trước: các cấu hình quan
    trọng nằm sâu từ HAI tầng trở lên, ví dụ
    `context_runtime.canary.allocation_basis_points`. Với merge một tầng, ghi vào
    settings.json đúng một trường

        {"context_runtime": {"canary": {"allocation_basis_points": 100}}}

    sẽ THAY THẾ trọn sub-dict `canary`, làm `quota_profiles` và `capability_profiles` biến
    mất. Mà thiết kế fail-closed nói thiếu quota profile thì rơi về legacy. Kết quả: người
    vận hành bật canary lên 1 phần trăm, tưởng đã bật, và KHÔNG CÓ GÌ xảy ra cả - im lặng,
    không lỗi, không cảnh báo. Đây là kiểu hỏng tệ nhất vì knob xoay được mà đèn không sáng.

    List cố ý THAY THẾ chứ không nối: `quota_profiles` là danh sách luật, nối thêm vào danh
    sách luật gần như luôn là ý sai (sinh luật trùng, luật cũ không xoá được).
    """
    for k, v in (patch or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


RUNTIME_MODES = ("off", "observe", "shadow", "canary", "on")

# MỖI MỨC TIẾT KIỆM BẬT NHỮNG ĐƯỜNG NÀO. Bảng này là nguồn sự thật; `main.RUNTIME_PRESETS`
# chỉ khoác thêm nhãn và mô tả cho người đọc. Để ở config vì `_ap_muc_mac_dinh` bên dưới cần
# nó, mà config thì không import được main (vòng lặp import).
PRESET_DUONG = {
    "off": {"mode": "shadow", "duong": {}},
    "saving": {"mode": "canary", "duong": {
        "conversation_state_canary": 10000,
        "memory_canary": 10000,
        "lazy_skill_canary": 10000,
    }},
    "max": {"mode": "canary", "duong": {
        "conversation_state_canary": 10000,
        "memory_canary": 10000,
        "lazy_skill_canary": 10000,
        "canary": 10000,
    }},
}

# MỨC XUẤT XƯỞNG CỦA BẢN NÀY. Đổi đúng dòng này là đổi mặc định cho MỌI máy chưa từng tự
# chọn mức, kể cả máy đã cài từ lâu. Đừng sửa `_DEFAULT` ở trên để đổi mặc định: xem
# `_ap_muc_mac_dinh` để biết vì sao sửa ở đó không tới được máy nào.
#
# Từ 0.24.7 là "max" (Siêu tiết kiệm). Trước đó là "off", tức mặc định gửi trọn CLAUDE.md +
# MEMORY.md + đặc tả tool mỗi lượt, và người dùng phải tự tìm ra trang tiết kiệm rồi tự bật.
# Gần như không ai bật, nên mặc định ấy là con số thật mà đa số đang trả. Đo trên một brain
# mẫu: mức Tắt ~8.900 token cố định mỗi lượt, mức Siêu tiết kiệm ~460.
#
# Đây là mặc định AN TOÀN được, không phải liều: mọi đường trong mức này đều fail-closed -
# thiếu điều kiện thì lượt đó tự rơi về chế độ Đầy đủ chứ không trả lời sai. Và người đã tự
# chọn mức thì hàm trên không đụng tới, kể cả người cố ý chọn Tắt.
PRESET_MAC_DINH = "max"


def _ap_muc_mac_dinh(cfg: dict) -> bool:
    """Nâng mức tiết kiệm lên ÍT NHẤT mức xuất xưởng, nếu người dùng CHƯA TỪNG tự chọn mức.

    Vì sao phải có, và vì sao sửa `_DEFAULT` là không đủ. `write_settings` ghi lại TOÀN BỘ
    config đã trộn, nên ngay lần đầu người dùng bấm bất cứ nút nào ở trang Cài đặt, giá trị
    mặc định của NGÀY HÔM ĐÓ bị đóng băng vào settings.json. `read_settings` lại trộn file ĐÈ
    LÊN mặc định. Hệ quả: về sau ta có nâng mặc định lên mức Tối ưu hay Siêu tiết kiệm thì
    máy đã cài rồi KHÔNG BAO GIỜ thấy - mặc định mới chỉ tới được máy cài mới tinh. Đúng con
    bệnh đã cắn `provider_kinds` hồi 0.12.4 (xem `_no_rong_pham_vi_bo_nao`), lần này rơi vào
    thứ quyết định mỗi lượt chat tốn bao nhiêu token.

    Cái khó riêng của mức tiết kiệm: số 0 nằm trong file có HAI nghĩa hoàn toàn khác nhau -
    "người dùng đã cân nhắc và cố ý chọn Tắt", hoặc "chưa ai chọn gì, đây là mặc định cũ
    đóng băng lại". Không phân biệt được hai cái đó thì hoặc là ta giẫm lên quyết định của
    người dùng, hoặc là mặc định mới không bao giờ tới nơi. Nên từ bản này, mọi lần người
    dùng tự đổi mức đều để lại chữ ký `preset_choice.source == "user"`, và có chữ ký thì hàm
    này không đụng vào gì hết.

    CHỈ NÂNG, KHÔNG BAO GIỜ HẠ. Máy đang chạy mức cao hơn mặc định (kể cả do sửa tay
    settings.json, thứ không để lại chữ ký nào) vẫn giữ nguyên mức của nó. Nhờ vậy trường
    hợp mơ hồ duy nhất còn lại là máy cũ từng cố ý chọn Tắt TRƯỚC khi có chữ ký: máy đó sẽ
    được nâng theo mặc định mới. Đổi lại, không có gì người dùng đã bật bị tắt đi, và bấm
    "Tắt" một lần sau khi cập nhật là ghim vĩnh viễn.

    Trả về True nếu có sửa gì, để chỗ gọi biết mà ghi file lại nếu muốn.
    """
    rt = cfg.get("context_runtime")
    if not isinstance(rt, dict):
        return False
    chon = rt.get("preset_choice")
    if isinstance(chon, dict) and str(chon.get("source") or "") == "user":
        return False
    muc = PRESET_DUONG.get(PRESET_MAC_DINH) or {}
    doi = False
    for ten, bp in (muc.get("duong") or {}).items():
        entry = rt.get(ten)
        if not isinstance(entry, dict):
            continue
        if int(entry.get("allocation_basis_points") or 0) < int(bp):
            entry["allocation_basis_points"] = int(bp)
            doi = True
    # `mode` là công tắc TRÙM: nâng allocation mà quên nâng mode là bật đúng cái kiểu hỏng
    # "knob xoay được mà đèn không sáng". Các phase khác (readonly/orchestrator/write) không
    # bị mode này bật lây vì allowlist capability của chúng mặc định rỗng, và riêng write
    # còn đòi người dùng gõ lại mã xác nhận.
    #
    # Mức xuất xưởng KHÔNG bật đường nào (hôm nay là mức Tắt) thì đừng đụng vào mode: chẳng
    # có gì để bật, mà mode lại là công tắc dùng chung với các phase khác. Đi sửa một thứ
    # không cần sửa là cách rẻ nhất để tạo ra một lỗi không ai ngờ tới.
    can = str(muc.get("mode") or "")
    if muc.get("duong") and can in RUNTIME_MODES:
        dang = str(rt.get("mode") or "")
        i_dang = RUNTIME_MODES.index(dang) if dang in RUNTIME_MODES else -1
        if i_dang < RUNTIME_MODES.index(can):
            rt["mode"] = can
            doi = True
    return doi


def _no_rong_pham_vi_bo_nao(cfg: dict) -> bool:
    """Nới `provider_kinds` của các mảng tiết kiệm về ÍT NHẤT bằng mặc định hiện tại.

    Vì sao phải có. `write_settings` ghi lại TOÀN BỘ config đã trộn, nên giá trị mặc định
    của ngày hôm đó bị đóng băng vào settings.json ngay lần đầu người dùng bấm bất cứ thứ gì.
    `read_settings` lại trộn file ĐÈ LÊN mặc định, nên về sau ta có sửa mặc định cho rộng ra
    thì máy đã cài rồi KHÔNG BAO GIỜ thấy. Mặc định mới chỉ tới được máy cài mới.

    Nó cắn đúng chỗ đau nhất: trước 0.12.4, `memory_canary` và `lazy_skill_canary` chỉ cho
    "api". Mọi máy chạy Javis từ trước mốc đó có file settings.json ghim cứng `["api"]`. Chủ
    máy nâng cấp lên, bấm mức Tối ưu, thấy trang báo xanh "đã bật, có hiệu lực ngay" - rồi
    mọi lượt chat trên gói ChatGPT hay gói Claude vẫn gửi nguyên CLAUDE.md, vì cả ba nguồn
    đều bị loại với lý do `provider_kind_not_allowed`. Không lỗi, không cảnh báo, chỉ có dòng
    "Đầy đủ" dưới mỗi câu trả lời và hoá đơn token không giảm.

    Chỉ NỚI RỘNG, không bao giờ thu hẹp: hợp giá trị đang có với mặc định. Nên mảng nào cố ý
    chỉ chạy trên engine API (conversation_state_canary - Claude Code và Codex tự nhớ mạch
    hội thoại của chúng, gửi thêm là gửi hai lần) vẫn giữ nguyên đúng phạm vi của nó.

    Trả về True nếu có sửa gì, để chỗ gọi biết mà ghi file lại nếu muốn.
    """
    rt = cfg.get("context_runtime")
    goc = _DEFAULT.get("context_runtime") or {}
    if not isinstance(rt, dict):
        return False
    doi = False
    for ten, mac_dinh in goc.items():
        if not isinstance(mac_dinh, dict) or "provider_kinds" not in mac_dinh:
            continue
        muc = rt.get(ten)
        if not isinstance(muc, dict):
            continue
        for truong in ("provider_kinds", "channels"):
            can = [str(x) for x in (mac_dinh.get(truong) or [])]
            if not can:
                continue
            dang_co = [str(x) for x in (muc.get(truong) or [])]
            thieu = [x for x in can if x not in dang_co]
            if thieu:
                muc[truong] = dang_co + thieu
                doi = True
    return doi


def read_settings():
    try:
        st = SETTINGS_PATH.stat()
        sig = (st.st_mtime_ns, st.st_size)
    except OSError:
        sig = None
    if sig is not None and sig == _SETTINGS_CACHE["sig"] and _SETTINGS_CACHE["cfg"] is not None:
        return json.loads(_SETTINGS_CACHE["cfg"])
    cfg = json.loads(json.dumps(_DEFAULT))   # deep copy
    try:
        if SETTINGS_PATH.exists():
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            _deep_merge(cfg, data or {})
    except Exception:
        pass
    _no_rong_pham_vi_bo_nao(cfg)
    _ap_muc_mac_dinh(cfg)
    try:
        import secrets_store   # lazy: secrets_store import config → tránh vòng lặp import
        _transform_secret_fields(cfg, secrets_store.decrypt)
    except Exception as e:
        print(f"[config] giải mã secret lỗi: {e}", file=__import__('sys').stderr)
    if sig is not None:
        _SETTINGS_CACHE["sig"] = sig
        _SETTINGS_CACHE["cfg"] = json.dumps(cfg, ensure_ascii=False)
    return cfg


def write_settings(cfg):
    # Deep-copy rồi mã hoá BẢN SAO: caller vẫn giữ cfg plaintext để dùng tiếp (không bị hỏng).
    out = json.loads(json.dumps(cfg))
    try:
        import secrets_store
        _transform_secret_fields(out, secrets_store.encrypt)   # encrypt idempotent (bỏ qua enc:/plain:)
    except Exception as e:
        print(f"[config] mã hoá secret lỗi: {e}", file=__import__('sys').stderr)
    SETTINGS_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")


_TOOL_ENV_OWNED = False   # ELEVENLABS_API_KEY trong env hiện do apply_tool_env đặt → được phép gỡ khi user xoá key


def apply_tool_env(cfg=None):
    """Bơm secret dùng chung từ Cài đặt vào os.environ để TOOL NGOÀI thừa kế khi engine CLI
    (Claude Code/Codex) spawn tiến trình con (Bash -> python/node). Hiện có: key ElevenLabs
    (Cài đặt > Giọng đọc) -> ELEVENLABS_API_KEY cho video-use phiên âm khi cắt sửa video.
    Lưu ý phạm vi: đặt vào env của CẢ server nên mọi tiến trình con (MCP stdio, script vault...)
    đều thừa kế - chấp nhận vì mục đích chính là đến được Bash con của engine, và cùng user
    thì con nào cũng đọc được settings.json + .secret_key; blast radius chỉ là key TTS.
    Chỉ ghi đè khi settings có giá trị; user xoá key trong settings thì gỡ khỏi env (nhưng
    không đụng biến user tự đặt ngoài shell). Gọi lúc startup + sau khi lưu Cài đặt giọng đọc."""
    global _TOOL_ENV_OWNED
    try:
        if cfg is None:
            cfg = read_settings()
        k = ((cfg.get("voice") or {}).get("elevenlabs_key") or "").strip()
        if k and not k.startswith("••••"):   # bỏ qua giá trị che mà client lỡ gửi lại
            os.environ["ELEVENLABS_API_KEY"] = k
            _TOOL_ENV_OWNED = True
        elif not k and _TOOL_ENV_OWNED:
            os.environ.pop("ELEVENLABS_API_KEY", None)
            _TOOL_ENV_OWNED = False
    except Exception as e:
        print(f"[config] apply_tool_env lỗi: {e}", file=__import__('sys').stderr)
    # Windows: helper Python con (vd video-use) in Unicode ra console cp1252 sẽ crash
    # (UnicodeEncodeError) -> ép UTF-8 cho mọi tiến trình con. Tôn trọng giá trị user tự đặt.
    if os.name == "nt" and not os.environ.get("PYTHONUTF8"):
        os.environ["PYTHONUTF8"] = "1"


# ---- Mật khẩu ----
def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()
    return h, salt


def auth_enabled(cfg=None):
    cfg = cfg or read_settings()
    return bool(cfg.get("auth", {}).get("password_hash"))


def require_login():
    """Có BẮT BUỘC đăng nhập để dùng Javis không (kể cả khi CHƯA đặt mật khẩu → ép setup).
    - JAVIS_REQUIRE_LOGIN=1/0 ép bật/tắt tường minh.
    - Mặc định: BẬT khi server nghe public (JAVIS_HOST=0.0.0.0, vd Docker/Hostinger/VPS) -
      vì Claude chạy full quyền, không được để hở ai cũng vào được."""
    v = os.getenv("JAVIS_REQUIRE_LOGIN", "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    # FAIL-CLOSED: bind KHÔNG phải loopback (0.0.0.0, ::, IP LAN…) → coi là public → bắt buộc login.
    # Chỉ tắt khi nghe thuần localhost. (Localhost + tunnel: đặt JAVIS_REQUIRE_LOGIN=1.)
    host = os.getenv("JAVIS_HOST", "127.0.0.1").strip().lower()
    return host not in ("127.0.0.1", "localhost", "::1")


def gate_active():
    """Có cần kiểm tra session trước khi cho truy cập không (đã đặt mật khẩu HOẶC bắt buộc login)."""
    return auth_enabled() or require_login()


def verify_password(password, cfg=None):
    cfg = cfg or read_settings()
    a = cfg.get("auth", {})
    if not a.get("password_hash"):
        return False
    h, _ = hash_password(password, a.get("salt"))
    return secrets.compare_digest(h, a["password_hash"])


# ---- Session (lưu ra file → restart KHÔNG bị đăng xuất) ----
# Lưu {token: created_ts} để session CÓ HẠN (chống token bất tử nếu lỡ rò).
import time as _time
_SESS_PATH = STATE_DIR / ".sessions.json"
_SESSION_TTL = 30 * 86400   # 30 ngày


def _load_sessions():
    try:
        if _SESS_PATH.exists():
            data = json.loads(_SESS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {k: float(v) for k, v in data.items()}
            if isinstance(data, list):   # tương thích định dạng cũ → coi như vừa tạo
                return {k: _time.time() for k in data}
    except Exception:
        pass
    return {}


SESSIONS = _load_sessions()


def _save_sessions():
    try:
        _SESS_PATH.write_text(json.dumps(SESSIONS), encoding="utf-8")
    except Exception:
        pass


def new_session():
    t = secrets.token_urlsafe(32)
    SESSIONS[t] = _time.time()
    _save_sessions()
    return t


def valid_session(token):
    if not token or token not in SESSIONS:
        return False
    if _time.time() - SESSIONS.get(token, 0) > _SESSION_TTL:
        SESSIONS.pop(token, None)
        _save_sessions()
        return False
    return True


def drop_session(token):
    SESSIONS.pop(token, None)
    _save_sessions()


def clear_sessions():
    SESSIONS.clear()
    _save_sessions()



# ---- TOKEN API cho client ngoài trình duyệt (CLI, script, cron) ----
# Vì sao không dùng lại session: session sinh ra cho trình duyệt - lưu {token: created_ts},
# TTL 30 ngày, không có tên, không thu hồi riêng lẻ được. Một credential dán sang máy khác thì
# cần đủ ba thứ: có TÊN để biết nó của máy nào, THU HỒI được từng cái, và KHÔNG BAO GIỜ nằm ở
# dạng đọc lại được trên đĩa.
#
# Mức quyền: `full` ngang phiên đăng nhập dashboard, `chat` chỉ chạm được đường hội thoại.
# Nói thẳng chứ không giả vờ có phân quyền tinh vi - `full` không phải quyền MỚI, nó đúng bằng
# cái quyền chủ máy đã có khi mở dashboard; chỉ là một loại credential khác.
_TOKENS_PATH = STATE_DIR / ".api_tokens.json"
TOKEN_PREFIX = "jvs_"
# Đường mà token scope `chat` được đi. Danh sách TRẮNG, khớp theo tiền tố: thiếu tên nào thì
# token đó bị từ chối chứ không lọt - fail-closed, đúng nếp của mọi hàng rào khác trong Javis.
TOKEN_SCOPE_CHAT = ("/chat", "/version", "/health", "/sessions")


def _load_tokens():
    try:
        if _TOKENS_PATH.exists():
            data = json.loads(_TOKENS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]
    except Exception:
        pass
    return []


def _save_tokens(items):
    try:
        _TOKENS_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(_TOKENS_PATH, 0o600)
        except Exception:
            pass
    except Exception as e:
        print(f"[auth] không ghi được token: {e}", file=__import__('sys').stderr)


def _token_hash(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def create_api_token(name: str, scope: str = "full") -> dict:
    """Sinh token mới. Trả BẢN THÔ đúng một lần - về sau trên đĩa chỉ còn bản băm."""
    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    item = {
        "id": "tok_" + secrets.token_hex(6),
        "name": (str(name or "").strip() or "không tên")[:60],
        "scope": "chat" if str(scope) == "chat" else "full",
        "hash": _token_hash(raw),
        "prefix": raw[:12],
        "created_at": _time.time(),
        "last_used_at": 0.0,
    }
    items = _load_tokens()
    items.append(item)
    _save_tokens(items)
    ra = {k: v for k, v in item.items() if k != "hash"}
    ra["token"] = raw
    return ra


def list_api_tokens():
    """Danh sách token, KHÔNG kèm bản băm - không có lý do nào để nó ra khỏi đĩa."""
    return [{k: v for k, v in x.items() if k != "hash"} for x in _load_tokens()]


def revoke_api_token(token_id: str) -> bool:
    items = _load_tokens()
    con = [x for x in items if x.get("id") != str(token_id or "")]
    if len(con) == len(items):
        return False
    _save_tokens(con)
    return True


def verify_api_token(raw: str, path: str = ""):
    """Token có hợp lệ cho `path` này không. Trả mục token (đã bỏ hash) hoặc None.

    So bằng `compare_digest` trên bản băm chứ không so chuỗi thô: so chuỗi thường thoát sớm ở
    ký tự đầu khác nhau, và thời gian chênh đó đủ để dò token theo từng ký tự.
    """
    raw = str(raw or "").strip()
    if not raw or not raw.startswith(TOKEN_PREFIX):
        return None
    h = _token_hash(raw)
    for x in _load_tokens():
        if secrets.compare_digest(str(x.get("hash") or ""), h):
            if str(x.get("scope")) == "chat" and path:
                if not any(str(path).startswith(p) for p in TOKEN_SCOPE_CHAT):
                    return None
            x["last_used_at"] = _time.time()
            _save_tokens(_load_tokens_touch(x))
            return {k: v for k, v in x.items() if k != "hash"}
    return None


def _load_tokens_touch(moi_nhat):
    """Ghi lại last_used_at của đúng một token, giữ nguyên phần còn lại."""
    items = _load_tokens()
    for x in items:
        if x.get("id") == moi_nhat.get("id"):
            x["last_used_at"] = moi_nhat.get("last_used_at") or _time.time()
    return items


# ---- Chặn dò token ----
# Token là chuỗi 43 ký tự ngẫu nhiên nên dò mù gần như bất khả, nhưng đếm và chặn vẫn đáng làm:
# nó biến một cuộc dò thành thứ NHÌN THẤY ĐƯỢC trong nhật ký thay vì im lặng chạy hàng tháng.
_AUTH_FAIL = {}          # ip -> [mốc thời gian thất bại]
_AUTH_AUDIT = STATE_DIR / "auth_audit.jsonl"
_FAIL_MAX, _FAIL_WINDOW, _BAN_SECONDS = 10, 300, 900


def token_ip_banned(ip: str) -> bool:
    hs = _AUTH_FAIL.get(str(ip or ""), [])
    if len(hs) < _FAIL_MAX:
        return False
    return (_time.time() - hs[-1]) < _BAN_SECONDS


def note_token_failure(ip: str, thu: str = ""):
    ip = str(ip or "")
    now = _time.time()
    hs = [t for t in _AUTH_FAIL.get(ip, []) if now - t < _FAIL_WINDOW]
    hs.append(now)
    _AUTH_FAIL[ip] = hs[-50:]
    try:
        with open(_AUTH_AUDIT, "a", encoding="utf-8") as f:
            # Ghi TIỀN TỐ thôi, không ghi token thô: nhật ký là thứ hay bị gửi đi kèm báo lỗi.
            f.write(json.dumps({"ts": now, "ip": ip, "prefix": str(thu or "")[:12],
                                "fails": len(hs)}, ensure_ascii=False) + "\n")
    except Exception:
        pass

# ---- Setup token: chống CHIẾM ADMIN lần đầu trên public ----
# Khi chạy public mà CHƯA có admin, /auth/setup PHẢI kèm token này - token chỉ in ra LOG server
# lúc khởi động, nên chỉ chính chủ (xem được log/terminal) tạo được tài khoản. Kẻ chỉ-có-URL bó tay.
_SETUP_TOKEN_PATH = STATE_DIR / ".setup_token"


def setup_token_required():
    return require_login() and not auth_enabled()


def get_or_create_setup_token():
    """Đọc/sinh token thiết lập 1 lần. None nếu không cần (local, hoặc đã có admin)."""
    if not setup_token_required():
        return None
    try:
        if _SETUP_TOKEN_PATH.exists():
            t = _SETUP_TOKEN_PATH.read_text(encoding="utf-8").strip()
            if t:
                return t
        t = secrets.token_urlsafe(24)
        _SETUP_TOKEN_PATH.write_text(t + "\n", encoding="utf-8")  # xuống dòng → cat ra sạch, dễ copy
        return t
    except Exception:
        return None


def check_setup_token(provided):
    try:
        if not _SETUP_TOKEN_PATH.exists():
            return False
        real = _SETUP_TOKEN_PATH.read_text(encoding="utf-8").strip()
        return bool(real) and secrets.compare_digest(real, (provided or "").strip())
    except Exception:
        return False


def clear_setup_token():
    try:
        _SETUP_TOKEN_PATH.unlink()
    except Exception:
        pass


def provision_admin_from_env():
    """Có JAVIS_ADMIN_PASSWORD (+ tùy chọn JAVIS_ADMIN_USER) và CHƯA có admin → tạo admin lúc boot
    → đóng /auth/setup cho mọi người (cách an toàn nhất cho deploy public). Trả True nếu vừa tạo."""
    if auth_enabled():
        return False
    pw = os.getenv("JAVIS_ADMIN_PASSWORD", "")
    if not pw:
        return False
    user = (os.getenv("JAVIS_ADMIN_USER", "admin").strip() or "admin")
    h, salt = hash_password(pw)
    cfg = read_settings()
    cfg["auth"] = {"username": user, "password_hash": h, "salt": salt}
    write_settings(cfg)
    return True
