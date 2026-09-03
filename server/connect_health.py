"""Sức khoẻ kết nối - vòng check nền cho trang Kết nối.

Mỗi HEALTH_INTERVAL giây, ping từng connection đang bật bằng tools/list qua session
pool (rẻ, không gọi tool thật, không tốn quota dịch vụ). Kết quả giữ IN-MEMORY:
sau restart quét lại sớm (delay ngắn) thay vì persist - trạng thái sống mới có giá trị.

Lỗi được PHÂN LOẠI SANG TIẾNG NGƯỜI ngay tại server (classify_error) để UI chỉ việc
hiển thị, và để nhóm `auth` (hết phiên đăng nhập) kích hoạt nút "Kết nối lại" một chạm.
Bài học vụ 0.9.189: thông điệp lỗi mù mờ làm cả agent lẫn người dùng chẩn đoán sai -
nói thẳng nguyên nhân là một tính năng, không phải trang trí.
"""
import asyncio
import sys
import time

import mcp_client
import mcp_store

HEALTH_INTERVAL = 600     # giây giữa hai vòng quét
_STARTUP_DELAY = 25       # chờ server ổn định rồi mới quét vòng đầu
_CHECK_TIMEOUT = 60       # trần một lần ping (stdio spawn nguội trên Windows có thể chậm)

_state: dict = {}         # conn_id -> {ok, kind, message, checked_at, tools}
_task = None


# Thứ tự các nhánh CÓ Ý NGHĨA: auth soi trước (chuỗi 401/unauthorized đặc trưng),
# spawn trước net (lỗi spawn stdio hay kèm chữ chung chung như "connection closed").
_AUTH_HINTS = ("401", "unauthorized", "invalid_grant", "oauth session expired",
               "token expired", "invalid token", "invalid_token", "authentication",
               "hết phiên đăng nhập")
_SPAWN_HINTS = ("filenotfounderror", "no such file", "not recognized", "enoent",
                "spawn", "exited with", "exit code", "notimplementederror")
_NET_HINTS = ("timeout", "timed out", "getaddrinfo", "connection refused",
              "connecterror", "connectionerror", "ssl", "network", "unreachable",
              "connection closed", "server disconnected", "502", "503", "504")


def classify_error(err: str) -> tuple[str, str]:
    """Chuỗi lỗi kỹ thuật -> (kind, thông điệp tiếng người).

    kind: auth | spawn | net | unknown. Nhóm `auth` là nhóm duy nhất UI gắn hành động
    (nút Kết nối lại) nên thà bỏ sót (rơi vào unknown) còn hơn bắt nhầm."""
    low = (err or "").lower()
    if any(s in low for s in _AUTH_HINTS):
        return "auth", "Hết phiên đăng nhập - bấm Kết nối lại để đăng nhập lại."
    if any(s in low for s in _SPAWN_HINTS):
        return "spawn", "Không khởi động được trình kết nối trên máy chạy Javis."
    if any(s in low for s in _NET_HINTS):
        return "net", "Dịch vụ không phản hồi - có thể do mạng hoặc máy chủ dịch vụ."
    return "unknown", (err or "Lỗi không rõ").strip()[:160]


async def check_one(conn, pool=None) -> dict:
    """Ping MỘT connection, cập nhật _state và trả bản ghi kết quả."""
    pool = pool or mcp_client.pool
    rec = {"ok": False, "kind": "", "message": "", "checked_at": time.time(), "tools": 0}
    # Connection OAuth CHƯA TỪNG có token (đăng nhập bỏ dở giữa chừng) → đỏ với lý do
    # thật, khỏi dial cho tốn công. Soi TRƯỚC nhánh connector ảo: meta-ads-graph/facebook-
    # pages cũng là oauth ảo, chưa đăng nhập mà báo xanh là nói dối.
    if (conn.get("auth") == "oauth"):
        try:
            import oauth_mcp
            if not oauth_mcp.status(conn["id"]).get("connected"):
                rec.update(kind="auth",
                           message="Chưa hoàn tất đăng nhập - bấm Kết nối lại để đăng nhập.")
                _state[conn["id"]] = rec
                return rec
            # Đăng nhập rồi nhưng token THIẾU PHẠM VI QUYỀN: tools/list của Google không cần
            # token nên ping bên dưới vẫn xanh, chỉ tool thật mới chết. Không soi ở đây thì
            # trang Kết nối nói dối là mọi thứ ổn (vụ Lịch thiếu calendar.events.freebusy).
            missing = oauth_mcp.scope_report(conn["id"]).get("missing") or []
            if missing:
                rec.update(kind="auth",
                           message="Thiếu quyền: " + ", ".join(oauth_mcp.short_scopes(missing))
                                   + " - bấm Kết nối lại và tick đủ mọi ô quyền. Google không"
                                   " hiện ô tick nào (quyền cũ đã cấp) thì gỡ Javis tại"
                                   " myaccount.google.com/permissions rồi kết nối lại.")
                _state[conn["id"]] = rec
                return rec
        except Exception:
            pass
    # Connector ẢO (không URL, không command, không phải internal): tool do plugin phục vụ (vd
    # Meta Ads Graph), không có server nào để dial - coi là sống, khỏi báo đỏ oan.
    #
    # Connector `internal` (Substack, Botcake) có module Python thật để gọi nên KHÔNG đi lối
    # này: nó phải được dial như mọi connector khác, không thì đèn sức khoẻ xanh vĩnh viễn kể
    # cả lúc tool chết hẳn.
    if not mcp_client.co_server_de_dial(conn):
        rec["ok"] = True
        _state[conn["id"]] = rec
        return rec
    spec = mcp_client._conn_spec(conn)
    try:
        spec["headers"].update(await mcp_client._oauth_headers(conn))
        tools = await asyncio.wait_for(pool.list_tools(spec), timeout=_CHECK_TIMEOUT)
        rec.update(ok=True, tools=len(tools))
        # Nối được nhưng hộp công cụ RỖNG thì không được tô xanh. Đèn xanh ghi "Hoạt động
        # bình thường (0 công cụ)" là câu nói dối tai hại nhất trang này: người dùng tin là
        # nguồn ổn nên đi tìm lỗi ở chỗ khác, còn bộ não thì đọc `javis_connections` thấy
        # "ổn" rồi kết luận bừa (vụ 03/09: "POS ổn nhưng không có tool nào" - model quay ra
        # đổ cho brain chưa gắn nguồn). Máy chủ có thật mà không có tool là hỏng, nói thẳng.
        if not tools:
            rec.update(ok=False, kind="empty",
                       message="Nối được nhưng máy chủ không đưa ra công cụ nào - phiên có "
                               "thể vừa bị máy chủ xoá. Bấm Kiểm tra để nối lại.")
    except Exception as e:
        # Quá hạn TRONG LÚC phiên đang chạy dở một tool call thật (lên đơn POS, gửi tin): ping
        # chỉ đang xếp hàng chờ khoá chứ nguồn không hề hỏng. Báo đỏ ở đây là trang Kết nối nói
        # dối đúng lúc nguồn đang LÀM VIỆC, rồi người dùng đi sửa một thứ không hỏng.
        ban = (isinstance(e, (asyncio.TimeoutError, TimeoutError))
               and pool.dang_goi_tool(spec))
        if ban:
            rec.update(ok=True, kind="ban",
                       message="Đang chạy tool nên chưa ping được - không phải lỗi kết nối.")
        else:
            kind, msg = classify_error(f"{type(e).__name__}: {e}")
            rec.update(kind=kind, message=msg)
    _state[conn["id"]] = rec
    return rec


async def check_by_id(conn_id, pool=None) -> dict:
    """Ép check ngay một connection theo id (nút test trên UI)."""
    conn = next((c for c in mcp_store.resolved(enabled_only=False)
                 if c["id"] == conn_id), None)
    if not conn:
        return {"ok": False, "kind": "unknown", "message": "Không tìm thấy kết nối",
                "checked_at": time.time(), "tools": 0}
    return await check_one(conn, pool)


async def sweep(pool=None) -> int:
    """Quét mọi connection đang bật. Trả số connection đã check."""
    n = 0
    for conn in mcp_store.resolved(enabled_only=True):
        try:
            await check_one(conn, pool)
            n += 1
        except Exception as e:   # lỗi 1 connection không được giết cả vòng
            print(f"[connect health] {conn.get('label')}: {type(e).__name__}: {e}",
                  file=sys.stderr)
    return n


def snapshot() -> dict:
    """Trạng thái hiện có cho GET /connect/health. Connection chưa check thì vắng mặt
    (UI hiểu là 'chưa rõ' - chấm vàng)."""
    return {cid: dict(rec) for cid, rec in _state.items()}


def forget(conn_id) -> None:
    """Xoá trạng thái khi connection bị xoá (khỏi hiện ma)."""
    _state.pop(conn_id, None)


# ─────────────── Đèn báo não (engine health) ───────────────
# Não chết thì chính não KHÔNG tự báo được (mọi thông báo thông minh đều đi qua engine),
# nên tín hiệu phải do server tự thắp: (1) probe hạn token định kỳ trong sweep,
# (2) cờ phản ứng khi một lượt chạy engine trả lỗi đăng nhập (flag_engine_auth_error).

_engines: dict = {}       # name -> {ok, message, source, ts, notified}
on_engine_down = None     # main.py gắn: async fn(text) gửi Telegram MỘT lần khi não chuyển chết

# Mẫu lỗi đăng nhập trong OUTPUT một lượt chạy engine (vụ 2026-07-27: Claude CLI hết phiên,
# mọi task trả "Failed to authenticate: OAuth session expired and could not be refreshed").
# Vụ 2026-07-30: Codex CLI trả "Your access token could not be refreshed because your
# refresh token was already used. Please log out and sign in again." Không câu nào khớp
# mẫu cũ, nên đèn không sáng và user chỉ thấy ba bong bóng lỗi khó hiểu liên tiếp - đúng
# thứ tính năng này sinh ra để tránh. Thêm cả ba cách nói của Codex.
_ENGINE_AUTH_PATTERNS = ("failed to authenticate", "oauth session expired",
                         "oauth token has expired", "please run /login",
                         "api key not found", "not logged in", "invalid api key",
                         "could not be refreshed", "refresh token was already used",
                         "log out and sign in again")

# Việc người dùng CẦN LÀM khi một bộ não hỏng. Mọi đường đều dẫn về trang Models: đó là chỗ
# kết nối duy nhất giờ đây, kể cả Claude (trước đây phải mở terminal gõ /login - hướng dẫn đó
# đã sai và từng làm người dùng đi nhầm đường).
ENGINE_FIX = {
    "claude": "Vào trang Models để kết nối lại.",
    "codex": "Vào trang Models để kết nối lại ChatGPT.",
}
ENGINE_FIX_DEFAULT = "Vào trang Models để kết nối và sử dụng Javis."


def _set_engine(name, ok, message="", source="probe"):
    prev = _engines.get(name) or {}
    rec = {"ok": ok, "message": message, "source": source, "ts": time.time(),
           "notified": bool(prev.get("notified"))}
    if ok:
        rec["notified"] = False   # hồi sinh → lần chết sau lại được báo
    _engines[name] = rec
    if not ok and not rec["notified"] and on_engine_down:
        # Chỉ báo Telegram khi bộ não này ĐANG là Main Model. Đèn của bộ não khác (vd lượt
        # chạy việc nền bằng Claude phát hiện mất đăng nhập trên máy Main Codex) vẫn được
        # ghi lại, nhưng câu "Javis chưa dùng được" là SAI với người dùng đó - việc nền đã
        # tự chạy tiếp bằng bộ não chat (_FallbackChain, 0.43.3).
        try:
            if name not in engines_in_use():
                return
        except Exception:
            pass
        rec["notified"] = True
        try:
            # Nói theo góc NGƯỜI DÙNG: với họ chỉ có một sự thật là chưa dùng được Javis,
            # và một việc phải làm. Tên engine để trong ngoặc cho ai cần đi tra, không đặt
            # lên đầu câu.
            coro = on_engine_down(
                "⚠ Javis chưa dùng được: chưa kết nối được Model AI. "
                + ENGINE_FIX.get(name, ENGINE_FIX_DEFAULT)
                + f" (chi tiết: {name} - {message})")
            if asyncio.iscoroutine(coro):
                asyncio.ensure_future(coro)
        except Exception as e:
            print(f"[engine health] notify lỗi: {e}", file=sys.stderr)


def flag_engine_auth_error(name, raw) -> bool:
    """Gọi từ engine khi một lượt chạy kết thúc: text khớp mẫu lỗi đăng nhập thì bật đèn đỏ.
    Trả True nếu đã bật (caller khỏi phân tích lại)."""
    low = (raw or "").lower()
    if not any(p in low for p in _ENGINE_AUTH_PATTERNS):
        return False
    _set_engine(name, False, "Hết phiên đăng nhập (phát hiện khi chạy).", "run")
    return True


def engine_run_ok(name) -> None:
    """Một lượt chạy thành công → não sống, tắt đèn (rẻ, chỉ ghi khi đang đỏ)."""
    rec = _engines.get(name)
    if rec and not rec.get("ok"):
        _set_engine(name, True, "", "run")


def _mac_keychain_creds() -> tuple[dict | None, bool]:
    """macOS: Claude Code KHÔNG ghi ~/.claude/.credentials.json mà cất OAuth trong Keychain
    (generic password, service 'Claude Code-credentials'). Đọc CHỈ-ĐỌC qua CLI `security`.
    Trả (creds, known): known=False = KHÔNG XÁC ĐỊNH ĐƯỢC (security bị chặn/treo/JSON hỏng)
    - caller phải coi như não sống, thà bỏ sót còn hơn báo đỏ oan (vụ Mac 0.9.229: banner
    'mất đăng nhập' treo vĩnh viễn dù đã đăng nhập)."""
    import json as _json
    import subprocess
    try:
        import winproc
        r = subprocess.run(
            ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            capture_output=True, text=True, timeout=5, creationflags=winproc.no_window())
    except Exception:
        return None, False
    if r.returncode != 0:
        # errSecItemNotFound: keychain khẳng định KHÔNG có item → thật sự chưa đăng nhập.
        if "could not be found" in (r.stderr or "").lower():
            return None, True
        return None, False   # bị từ chối quyền / lỗi lạ → không kết luận
    try:
        return _json.loads(r.stdout.strip()), True
    except Exception:
        return None, False


def probe_claude_credentials(path=None) -> tuple[bool, str]:
    """Đọc hạn token Claude CLI (~/.claude/.credentials.json; macOS rơi về Keychain).
    CHỈ ĐỌC - tuyệt đối không tự refresh (tự refresh làm user bị đăng xuất, xem bài học cũ).
    Có refreshToken → CLI tự làm mới được, coi là sống dù access token đã quá hạn."""
    from pathlib import Path
    p = Path(path) if path else Path.home() / ".claude" / ".credentials.json"
    data = None
    try:
        import json as _json
        data = _json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if sys.platform == "darwin":
            creds, known = _mac_keychain_creds()
            if not known:
                return True, ""   # không xác định được → coi là sống; đèn do lượt chạy thật lo
            if not creds:
                return False, "Chưa đăng nhập Claude Code trên máy này."
            data = creds
        else:
            return False, "Chưa đăng nhập Claude Code trên máy này."
    except Exception:
        return False, "Không đọc được thông tin đăng nhập Claude Code."
    oa = (data or {}).get("claudeAiOauth") or {}
    if not oa:
        return False, "Chưa đăng nhập Claude Code trên máy này."
    if oa.get("refreshToken"):
        return True, ""
    exp = oa.get("expiresAt") or 0
    if exp / 1000 > time.time():
        return True, ""
    return False, "Phiên đăng nhập Claude Code đã hết hạn và không tự làm mới được."


# Provider nào có "phiên đăng nhập CLI" để mà mất. Các provider API (openrouter, openai,
# anthropic-api, gemini) chạy bằng API key: key sai thì lượt chạy báo lỗi ngay tại chỗ,
# không có phiên nào hết hạn ngầm, nên chúng KHÔNG có đèn báo não.
_PROVIDER_ENGINE = {"anthropic-cli": "claude", "openai-oauth": "codex",
                    "grok-cli": "grok-cli"}


def engines_in_use() -> set:
    """Tên đèn của bộ não MAIN MODEL - thứ DUY NHẤT banner 'Chưa kết nối Model AI' nói về.

    Model việc nền KHÔNG soi ở đây nữa (0.47.4). Từ 0.43.3 việc nền có _FallbackChain:
    Claude không sẵn sàng thì nó tự chạy bằng chính bộ não chat - tức 'model việc nền
    chưa đăng nhập' KHÔNG còn nghĩa là 'Javis chưa dùng được'. Trong khi đó banner đọc
    đúng nghĩa đen như vậy, và trong một ngày (27/08) đã hai lần bắt oan máy Main Model
    Codex chỉ vì cấu hình việc nền còn trỏ một model Claude (bản đầu lọc mỗi ca
    'anthropic-cli + model rỗng' của nút Về mặc định - vẫn sót ca chọn hẳn haiku theo
    gợi ý 'model rẻ đỡ hạn mức' của chính UI). Sức khoẻ việc nền có chỗ riêng của nó:
    thẻ Model việc nền ở trang Models."""
    try:
        import config as _cfg
        m = (_cfg.read_settings().get("model") or {})
    except Exception:
        return {"claude"}
    prov = (m.get("main") or {}).get("provider") or "anthropic-cli"
    return {_PROVIDER_ENGINE[prov]} if prov in _PROVIDER_ENGINE else set()


def probe_engines() -> None:
    """Probe định kỳ (gọi trong sweep). Chỉ soi bộ não người dùng đang giao việc, và
    XOÁ đèn của bộ não không còn được giao việc nữa.

    Xoá là phần quan trọng: _engines nằm trong RAM và không ai dọn, nên đèn đỏ thắp hồi
    Claude còn là Main Model sẽ treo vĩnh viễn sau khi người dùng đổi sang OpenRouter -
    đúng lỗi khách gặp (banner đỏ 'bộ não claude mất đăng nhập' trên máy chưa từng cài
    Claude). Đèn do lượt chạy bật (source=run) không bị probe đè sang xanh - lỗi lúc
    chạy là bằng chứng mạnh hơn suy đoán từ file token."""
    live = engines_in_use()
    for name in [n for n in _engines if n not in live]:
        _engines.pop(name, None)
    # Đèn Codex (Main Model là gói ChatGPT): trước 0.47.4 đèn này KHÔNG TỒN TẠI - không
    # probe, và flag_engine_auth_error("codex") không có ai gọi - nên ngắt ChatGPT thật
    # cũng không banner nào báo. Probe rẻ: status() chỉ đọc settings (có token hay không),
    # không gọi mạng, nên không có ca báo đỏ oan vì mạng chập chờn.
    if "codex" in live:
        try:
            import openai_oauth
            ok = bool(openai_oauth.status().get("connected"))
            cur = _engines.get("codex") or {}
            if not (ok and cur.get("source") == "run" and not cur.get("ok")):
                _set_engine("codex", ok,
                            "" if ok else "Chưa kết nối ChatGPT (OAuth).", "probe")
        except Exception:
            pass
    if "claude" not in live:
        return
    # Gói Claude Code chạy bằng API KEY (chọn ở trang Models) thì không có "phiên đăng nhập
    # CLI" nào để mà mất - probe file token lúc này là soi nhầm chỗ, và nó từng làm banner
    # 'chưa kết nối' treo mãi trên máy đã dán key đầy đủ. Key sai thì lượt chạy báo tại chỗ
    # (flag_engine_auth_error có mẫu "invalid api key"), giống mọi provider API khác.
    try:
        import claude_auth
        if claude_auth.che_do() == claude_auth.API_KEY and claude_auth.api_key():
            ok, msg = True, ""
        else:
            ok, msg = probe_claude_credentials()
    except Exception:
        ok, msg = probe_claude_credentials()
    cur = _engines.get("claude") or {}
    if ok and cur.get("source") == "run" and not cur.get("ok"):
        return   # đèn đỏ do lượt chạy thật - chờ engine_run_ok tắt, probe không đè
    _set_engine("claude", ok, msg, "probe")


def engine_reconnected(name) -> None:
    """Người dùng vừa đăng nhập lại / đổi cấu hình bộ não này ở trang Models: mọi bằng
    chứng cũ (kể cả đèn đỏ do lượt chạy bật) đã lỗi thời, xoá đi rồi probe lại ngay.

    Không có hàm này thì banner 'chưa kết nối Model AI' treo thêm tới 10 phút sau khi
    người dùng ĐÃ kết nối xong (probe chỉ chạy mỗi HEALTH_INTERVAL), và đèn đỏ
    source=run còn treo vô hạn vì probe không được đè nó."""
    _engines.pop(name, None)
    try:
        probe_engines()
    except Exception as e:
        print(f"[engine health] probe sau kết nối lỗi: {e}", file=sys.stderr)


def engines_snapshot() -> dict:
    """Lọc lại theo bộ não ĐANG dùng ngay lúc hỏi, không chờ vòng quét kế tiếp.

    probe_engines() cũng dọn, nhưng nó chạy mỗi HEALTH_INTERVAL (10 phút): đổi Main Model
    xong mà banner đỏ còn treo thêm 10 phút thì người dùng tưởng đổi không ăn. read_settings
    có cache theo mtime nên lọc ở đây gần như không tốn gì."""
    live = engines_in_use()
    return {n: dict(r) for n, r in _engines.items() if n in live}


async def _loop():
    await asyncio.sleep(_STARTUP_DELAY)
    while True:
        try:
            probe_engines()
            await sweep()
        except Exception as e:
            print(f"[connect health] vòng quét lỗi: {type(e).__name__}: {e}",
                  file=sys.stderr)
        await asyncio.sleep(HEALTH_INTERVAL)


def start() -> None:
    """Gọi từ startup của app. Idempotent."""
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())
