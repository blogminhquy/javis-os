"""Kênh CLI: chat qua HTTP, token API, và hợp đồng đầu ra cho terminal.

    python tests/run.py cli_kenh

Bốn thứ file này canh, theo đúng thứ tự rủi ro.

1. **Lượt CLI phải đi qua ĐÚNG vỏ mà Telegram đang chạy.** Vỏ đó (`_tg_answer`) là chỗ duy
   nhất biết khớp phiên trong kho, ghi bộ nhớ hội thoại, gắn trace runtime và chấm chất
   lượng. Viết vỏ thứ hai thì lượt CLI vắng mặt ở `/sessions` và ở vòng tự học - đúng lỗ hổng
   nhánh Telegram từng dính trước 0.9.244, chỉ khác là lần này biết trước mà vẫn làm.

2. **Token là cửa MỚI vào một máy chủ đang phơi ra Internet.** Nên: băm khi lưu, so bằng
   compare_digest, thu hồi là chết ngay, và KHÔNG được dùng token để đẻ token.

3. **Kênh phải đi tới tận hợp đồng đầu ra.** Thiếu nhánh `cli` thì Javis trả markdown của web
   và người dùng nhận một đống ký tự gạch dọc trong terminal.

4. **Luật Unix của CLI.** Câu trả lời ra stdout, mọi thứ khác ra stderr. Hỏng luật đó thì
   `javis "..." > ghi-chu.md` dính spinner vào giữa nội dung.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import json
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-cli-")

import config as cfg  # noqa: E402
import channel_context  # noqa: E402
import context_compiler  # noqa: E402
import main  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


_SRC = (ROOT / "server" / "main.py").read_text(encoding="utf-8")


# ============================================================
# 1. Chat qua HTTP dùng lại vỏ của Telegram
# ============================================================
_paths = [r.path for r in main.app.routes]
check("có endpoint chat một lượt", "/chat" in _paths)
check("có endpoint chat dạng luồng", "/chat/stream" in _paths)

# CANARY quan trọng nhất của cả file: hai endpoint phải gọi _tg_answer với channel="cli",
# không được có lõi riêng.
check("CANARY: lượt CLI đi qua đúng vỏ chung, không đẻ lõi thứ hai",
      'await _tg_answer(message, meta=meta, progress=progress, channel="cli")' in _SRC)
# Không ghim dấu đóng ngoặc: thứ cần canh là vỏ chung CÓ tham số kênh, không phải vỏ chung
# vĩnh viễn không được thêm tham số nào nữa (Bot chuyên trách thêm `bot=None` ở 0.19.0).
check("vỏ chung nhận tham số kênh", 'async def _tg_answer(text, meta=None, progress=None, channel="telegram"' in _SRC)
check("trace runtime gắn đúng kênh", 'conv_sid or f"{channel}:{chat_id}", brain, channel)' in _SRC)
check("chấm chất lượng cũng theo kênh", "(out.get(\"text\") or \"\") if isinstance(out, dict) else str(out or \"\"),\n            channel," in _SRC)
# Bật cờ telegram_running cho lượt CLI là dạy Javis công thức gửi file qua Telegram trong khi
# người hỏi đang ngồi ở terminal - nó sẽ hứa gửi rồi không ai nhận được gì.
check("CANARY: lượt CLI không bị dạy công thức gửi file Telegram",
      'telegram_running=(channel == "telegram")' in _SRC)

# Khoá phiên: phải có tiền tố cli: để không đụng khoá Telegram trong cùng một map.
check("khoá phiên CLI có tiền tố riêng", main._cli_sess_key("abc") == "cli:abc")
check("phiên trống về mặc định", main._cli_sess_key("") == "cli:default")
# Khoá đi thẳng vào tên file/log nên phải lọc; và người dùng gõ gì cũng không được thành
# đường dẫn lạ.
check("CANARY: khoá phiên lọc ký tự lạ", main._cli_sess_key("../../etc/passwd") == "cli:etcpasswd")
check("khoá phiên có trần độ dài", len(main._cli_sess_key("x" * 500)) <= 68)

_ok = main._cli_payload({"text": "xong", "files": ["/a/b.md"], "ctx_path": "fast"}, "cli:t1")
check("gói trả lời mang đủ chữ, phiên, file, đường chạy",
      _ok["ok"] and _ok["text"] == "xong" and _ok["session"] == "cli:t1"
      and _ok["files"] == ["/a/b.md"] and _ok["ctx_path"] == "fast")
# Lõi trả CHUỖI nghĩa là lỗi. Đóng gói nhầm thành ok=true là CLI in lỗi ra stdout rồi thoát 0,
# và script gọi nó tưởng mọi thứ ổn.
check("CANARY: lõi trả chuỗi = lỗi, không được đóng gói thành thành công",
      main._cli_payload("engine chết", "cli:t1")["ok"] is False)


# ============================================================
# 2. Token API
# ============================================================
_t = cfg.create_api_token("laptop", "full")
check("tạo được token", _t["token"].startswith(cfg.TOKEN_PREFIX))
check("token đủ dài để không dò được", len(_t["token"]) >= 40)
check("bản thô KHÔNG lộ ra ở chỗ khác",
      all("token" not in x for x in cfg.list_api_tokens()))
check("CANARY: bản băm không bao giờ rời đĩa",
      all("hash" not in x for x in cfg.list_api_tokens()))
check("có tiền tố để người dùng nhận ra token nào", _t["prefix"] and len(_t["prefix"]) <= 12)

_raw = (cfg.STATE_DIR / ".api_tokens.json").read_text(encoding="utf-8")
check("CANARY: token thô KHÔNG nằm trên đĩa", _t["token"] not in _raw)
check("trên đĩa chỉ có bản băm", "hash" in _raw)

check("token đúng thì qua", bool(cfg.verify_api_token(_t["token"], "/chat")))
check("token sai thì trượt", cfg.verify_api_token("jvs_khonghopl", "/chat") is None)
check("chuỗi không đúng tiền tố cũng trượt", cfg.verify_api_token("abc123", "/chat") is None)
check("rỗng thì trượt", cfg.verify_api_token("", "/chat") is None)

_tc = cfg.create_api_token("chỉ chat", "chat")
check("scope chat vào được đường chat", bool(cfg.verify_api_token(_tc["token"], "/chat")))
check("scope chat vào được /version", bool(cfg.verify_api_token(_tc["token"], "/version")))
# Danh sách TRẮNG: đường nào không khai thì trượt. Sai chiều (danh sách đen) là mỗi endpoint
# mới thêm vào server tự động phơi ra cho token hẹp.
check("CANARY: scope chat KHÔNG chạm được cài đặt",
      cfg.verify_api_token(_tc["token"], "/settings") is None)
check("CANARY: scope chat KHÔNG chạm được kho token",
      cfg.verify_api_token(_tc["token"], "/auth/tokens") is None)

check("thu hồi được", cfg.revoke_api_token(_t["id"]) is True)
check("CANARY: thu hồi rồi là chết ngay", cfg.verify_api_token(_t["token"], "/chat") is None)
check("thu hồi id không có thì báo false", cfg.revoke_api_token("tok_khongco") is False)

# So sánh phải là compare_digest trên bản băm. So chuỗi thường thoát sớm ở ký tự đầu khác
# nhau, và chênh lệch thời gian đó đủ để dò token theo từng ký tự.
_CFG_SRC = (ROOT / "server" / "config.py").read_text(encoding="utf-8")
check("CANARY: so token bằng compare_digest, không so chuỗi",
      "secrets.compare_digest(str(x.get(\"hash\") or \"\"), h)" in _CFG_SRC)
check("băm bằng sha256", "hashlib.sha256" in _CFG_SRC)

# Chặn dò
_ip = "203.0.113.9"
check("chưa sai lần nào thì không bị chặn", cfg.token_ip_banned(_ip) is False)
# Đưa vào đây một token THẬT, không phải chuỗi giả ngắn. Thứ giữ token khỏi nhật ký là phép
# cắt [:12] trong note_token_failure; chuỗi giả ngắn thì cắt hay không cũng ra một kết quả, nên
# test sẽ mù đúng cái nó định canh. Kẻ dò thật cũng gửi token dài chứ không gửi "jvs_thu".
for _ in range(cfg._FAIL_MAX):
    cfg.note_token_failure(_ip, _tc["token"])
check("CANARY: sai quá nhiều thì IP bị chặn", cfg.token_ip_banned(_ip) is True)
_audit = (cfg.STATE_DIR / "auth_audit.jsonl").read_text(encoding="utf-8")
check("có ghi nhật ký để một cuộc dò nhìn thấy được", _tc["token"][:12] in _audit)
check("CANARY: nhật ký chỉ ghi tiền tố, KHÔNG ghi token thô", _tc["token"] not in _audit)

# Hàng rào ở tầng endpoint
check("CANARY: không cho dùng token để đẻ token",
      "Tạo token phải đăng nhập bằng trình duyệt" in _SRC)
check("hàng rào xác thực có nhánh Bearer", "_token_ok(request, path)" in _SRC)
check("chặn dò được kiểm TRƯỚC khi băm", "if cfgmod.token_ip_banned(ip):" in _SRC)
# Nhánh token phải nằm SAU nhánh cookie: dashboard gọi hàng chục request mỗi lần mở trang,
# bắt nó đọc file token mỗi lần là trả giá cho một thứ nó không dùng.
check("nhánh token đặt sau nhánh cookie",
      _SRC.index("cfgmod.valid_session(request.cookies") < _SRC.index("if not _token_ok(request, path)"))


# ============================================================
# 3. Kênh cli đi tới tận hợp đồng đầu ra
# ============================================================
_khoi = channel_context.build_channel_block("cli", {"host": "macbook"})
check("khối kênh nhận diện đúng nguồn", "Javis CLI" in _khoi)
check("có tên máy để Javis biết đang nói với ai", "macbook" in _khoi)
check("CANARY: cấm bảng markdown trong terminal", "không dùng bảng" in _khoi.lower()
      or "TUYỆT ĐỐI không dùng bảng" in _khoi)
check("CANARY: cấm nhúng ảnh, bắt in đường dẫn", "ĐƯỜNG DẪN TUYỆT ĐỐI" in _khoi)
# Khối của web dạy công thức "chat_id":"web:..." - lọt sang CLI là Javis gắn sai người nhận.
check("CANARY: không lẫn công thức của kênh web", "web:" not in _khoi)

_hd = context_compiler.ContextCompiler._channel_contract("cli")
check("hợp đồng đầu ra biết kênh cli", "terminal" in _hd.lower())
check("hợp đồng cấm bảng", "Markdown" in _hd)
_out = context_compiler.ContextCompiler._output_contract_text("cli")
check("phần cách trả lời cũng biết kênh cli", "CLI" in _out)


# ============================================================
# 4. Gói CLI: luật Unix và luật phụ thuộc
# ============================================================
_CLI = ROOT / "cli"
check("có gói CLI", (_CLI / "pyproject.toml").is_file())
_pyproj = (_CLI / "pyproject.toml").read_text(encoding="utf-8")
check("lệnh cài xong tên là javis", 'javis = "javis_cli.__main__:main"' in _pyproj)
# Gói này phải cài được trên máy chưa từng có Javis. Kéo theo fastapi/uvicorn là bắt người
# dùng tải cả một web framework về chỉ để gõ một câu hỏi.
#
# Soát ĐÚNG dòng dependencies chứ không quét cả file: chính lời giải thích trong pyproject có
# nhắc tên những gói bị cấm, nên quét cả file là test tự bắt lời chú thích của mình. Đã dính
# đúng bẫy này một lần ở 0.14.3 nên lần này viết cho chắc.
_deps = ""
for _dong in _pyproj.split("\n"):
    if _dong.strip().startswith("dependencies"):
        _deps = _dong
check("khai được danh sách phụ thuộc", bool(_deps))
for _cam in ("fastapi", "uvicorn", "starlette", "pydantic", "rich"):
    check(f"CANARY: CLI không kéo theo {_cam}", _cam not in _deps)
check("chỉ phụ thuộc httpx", _deps.strip() == 'dependencies = ["httpx>=0.24"]')

_render = (_CLI / "javis_cli" / "render.py").read_text(encoding="utf-8")
check("câu trả lời ra stdout", "sys.stdout.write" in _render)
check("trạng thái ra stderr", "sys.stderr.write" in _render)
# Đây là luật sống còn: chỉ hàm tra_loi được ghi stdout. Thêm một chỗ nữa là pipe dính rác.
check("CANARY: đúng MỘT chỗ ghi stdout", _render.count("sys.stdout.write") == 1)
check("không tô màu khi đổ vào pipe", "isatty" in _render)

_cmds = (_CLI / "javis_cli" / "commands.py").read_text(encoding="utf-8")
check("CANARY: gói lạ bị bỏ qua im lặng, không làm vỡ CLI",
      "Mọi `type` lạ: BỎ QUA im lặng" in _cmds)
check("lỗi thì thoát khác 0", "return 1" in _cmds)
check("javis up nói rõ nó KHÔNG chứa server",
      "KHÔNG chứa server bên trong" in _cmds)

_cfg_cli = (_CLI / "javis_cli" / "config.py").read_text(encoding="utf-8")
check("CANARY: file cấu hình chứa token phải chmod 600", "0o600" in _cfg_cli)
check("biến môi trường đè lên file (cho CI/Docker)", "JAVIS_TOKEN" in _cfg_cli)

# Chạy THẬT bộ phân tích tham số: `javis "câu hỏi"` phải là đường chính, không bắt gõ lệnh con.
sys.path.insert(0, str(_CLI))
import javis_cli.__main__ as cli_main  # noqa: E402

_goi = {}
_goc_hoi = cli_main.cmd.hoi
cli_main.cmd.hoi = lambda args, cau, session="": _goi.setdefault("cau", cau) or 0
try:
    cli_main.main(["doanh", "thu", "tuần", "này"])
    check("CANARY: gõ thẳng câu hỏi là chạy, không cần lệnh con",
          _goi.get("cau") == "doanh thu tuần này")
    _goi.clear()
    cli_main.main(["-q", "hôm nay thế nào"])
    check("cờ đứng trước câu hỏi vẫn hiểu", _goi.get("cau") == "hôm nay thế nào")
finally:
    cli_main.cmd.hoi = _goc_hoi

print()
if _fails:
    print(f"THẤT BẠI {len(_fails)}: {_fails}")
    sys.exit(1)
print("OK - test_cli_kenh: tất cả pass")
