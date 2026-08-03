"""Test sức khoẻ kết nối (connect_health) - phân loại lỗi + check + sweep + snapshot."""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import asyncio
import time

import connect_health


# ---- classify_error: đủ nhánh, ưu tiên đúng thứ tự ----

def test_classify_auth():
    for err in ("HTTP 401 Unauthorized",
                "TokenError: invalid_grant",
                "Failed to authenticate: OAuth session expired and could not be refreshed",
                "invalid token provided"):
        kind, msg = connect_health.classify_error(err)
        assert kind == "auth", err
        assert "Kết nối lại" in msg


def test_classify_spawn():
    for err in ("FileNotFoundError: uvx",
                "'uvx' is not recognized as an internal or external command",
                "process exited with code 1"):
        kind, msg = connect_health.classify_error(err)
        assert kind == "spawn", err
        assert "máy chạy Javis" in msg


def test_classify_net():
    for err in ("ReadTimeout: timed out",
                "ConnectError: getaddrinfo failed",
                "Server disconnected without response",
                "HTTP 503 Service Unavailable"):
        kind, msg = connect_health.classify_error(err)
        assert kind == "net", err


def test_classify_unknown_giu_thong_diep_goc():
    kind, msg = connect_health.classify_error("ValueError: something odd " + "x" * 300)
    assert kind == "unknown"
    assert msg.startswith("ValueError")
    assert len(msg) <= 160


def test_classify_auth_thang_net_khi_ca_hai_khop():
    # "401" + "timeout" trong cùng chuỗi: auth phải thắng vì có hành động gắn kèm
    kind, _ = connect_health.classify_error("401 unauthorized after timeout")
    assert kind == "auth"


# ---- check_one / sweep với pool giả ----

class _FakePool:
    def __init__(self, tools=None, raise_error=None):
        self.tools = tools if tools is not None else [{"name": "a"}, {"name": "b"}]
        self.raise_error = raise_error
        self.calls = 0

    async def list_tools(self, spec):
        self.calls += 1
        if self.raise_error:
            raise self.raise_error
        return self.tools


def _conn(cid="c1", **kw):
    base = {"id": cid, "label": "Test", "transport": "http",
            "url": "http://example.local/mcp", "headers": {}, "args": [],
            "env": {}, "secrets": {}, "config": {}, "auth": "apikey"}
    base.update(kw)
    return base


def test_check_one_song():
    connect_health._state.clear()
    rec = asyncio.run(connect_health.check_one(_conn(), _FakePool()))
    assert rec["ok"] is True and rec["tools"] == 2
    assert connect_health.snapshot()["c1"]["ok"] is True


def test_check_one_loi_auth():
    connect_health._state.clear()
    pool = _FakePool(raise_error=RuntimeError("HTTP 401 unauthorized"))
    rec = asyncio.run(connect_health.check_one(_conn(), pool))
    assert rec["ok"] is False and rec["kind"] == "auth"
    assert "Kết nối lại" in rec["message"]


def test_check_one_oauth_chua_dang_nhap_bao_do_khong_dial():
    """Xác oauth bỏ dở (chưa từng có token) phải đỏ với lý do thật, không dial server.
    Vụ Meta Ads: connection mồ côi hiện như tài khoản thật, xanh oan trên UI."""
    connect_health._state.clear()
    pool = _FakePool()
    rec = asyncio.run(connect_health.check_one(_conn("orphan", auth="oauth"), pool))
    assert rec["ok"] is False and rec["kind"] == "auth"
    assert "Chưa hoàn tất đăng nhập" in rec["message"]
    assert pool.calls == 0


def test_check_one_connector_ao_luon_song():
    """Connector ảo (không url/command, tool do plugin phục vụ) không được báo đỏ oan."""
    connect_health._state.clear()
    pool = _FakePool(raise_error=RuntimeError("would explode"))
    rec = asyncio.run(connect_health.check_one(_conn(url="", command=""), pool))
    assert rec["ok"] is True
    assert pool.calls == 0


def test_sweep_mot_conn_loi_khong_giet_ca_vong(monkeypatch):
    connect_health._state.clear()

    def fake_resolved(enabled_only=True):
        return [_conn("ok1"), _conn("die1"), _conn("ok2")]

    class _PickyPool(_FakePool):
        async def list_tools(self, spec):
            self.calls += 1
            if spec["key"] == "die1":
                raise RuntimeError("timed out")
            return self.tools

    import mcp_store
    monkeypatch.setattr(mcp_store, "resolved", fake_resolved)
    n = asyncio.run(connect_health.sweep(_PickyPool()))
    snap = connect_health.snapshot()
    assert n == 3
    assert snap["ok1"]["ok"] and snap["ok2"]["ok"]
    assert snap["die1"]["kind"] == "net"


def test_check_by_id_khong_thay(monkeypatch):
    import mcp_store
    monkeypatch.setattr(mcp_store, "resolved", lambda enabled_only=False: [])
    rec = asyncio.run(connect_health.check_by_id("ma"))
    assert rec["ok"] is False and "Không tìm thấy" in rec["message"]


def test_forget_xoa_trang_thai():
    connect_health._state.clear()
    asyncio.run(connect_health.check_one(_conn("gone"), _FakePool()))
    assert "gone" in connect_health.snapshot()
    connect_health.forget("gone")
    assert "gone" not in connect_health.snapshot()


def test_snapshot_tra_ban_sao():
    connect_health._state.clear()
    asyncio.run(connect_health.check_one(_conn("s1"), _FakePool()))
    snap = connect_health.snapshot()
    snap["s1"]["ok"] = False
    assert connect_health.snapshot()["s1"]["ok"] is True


# ---- Đèn báo não (engine health) ----

def _reset_engines():
    connect_health._engines.clear()
    connect_health.on_engine_down = None


def test_flag_engine_bat_den_voi_loi_that():
    """Chuỗi lỗi THẬT của vụ 2026-07-27 phải bật đèn."""
    _reset_engines()
    hit = connect_health.flag_engine_auth_error(
        "claude", "Failed to authenticate: OAuth session expired and could not be refreshed")
    assert hit is True
    assert connect_health.engines_snapshot()["claude"]["ok"] is False


def test_flag_engine_bat_voi_loi_refresh_token_codex(monkeypatch):
    """Chuỗi lỗi THẬT của vụ 2026-07-30: Codex mất phiên nhưng nói theo kiểu khác hẳn.

    Không câu nào khớp mẫu cũ nên đèn im, user chỉ thấy ba bong bóng lỗi liên tiếp
    mà không ai nói cho biết phải đăng nhập lại.

    Phải giả lập người dùng ĐANG chọn gói ChatGPT: engines_snapshot() cố ý chỉ trả đèn của
    bộ não đang được giao việc (xem engines_in_use), nếu không thì máy chạy OpenRouter vẫn
    bị nagging 'bộ não claude mất đăng nhập'. Không đặt provider thì mặc định là claude, và
    đèn codex vừa bật đã bị lọc mất - test cũ thiếu đúng chỗ này nên đỏ, mà nó chưa từng
    chạy trong CI (thiếu block __main__) nên không ai biết.
    """
    monkeypatch.setattr(connect_health, "engines_in_use", lambda: {"codex"})
    for raw in (
        "Codex: Your access token could not be refreshed because your refresh token "
        "was already used. Please log out and sign in again.",
        "Your refresh token was already used.",
        "Please log out and sign in again.",
    ):
        _reset_engines()
        assert connect_health.flag_engine_auth_error("codex", raw) is True, raw
        assert connect_health.engines_snapshot()["codex"]["ok"] is False


def test_flag_engine_khong_bat_voi_ket_qua_thuong():
    _reset_engines()
    assert connect_health.flag_engine_auth_error("claude", "Doanh thu hôm nay 5 triệu.") is False
    assert "claude" not in connect_health.engines_snapshot()


def test_notify_dung_mot_lan_moi_dot_chet():
    """Chết báo Telegram MỘT lần; chết tiếp không spam; hồi sinh rồi chết lại thì báo lại."""
    _reset_engines()
    calls = []
    connect_health.on_engine_down = lambda text: calls.append(text)
    connect_health.flag_engine_auth_error("claude", "failed to authenticate")
    connect_health.flag_engine_auth_error("claude", "failed to authenticate")
    assert len(calls) == 1 and "claude" in calls[0]
    connect_health.engine_run_ok("claude")
    assert connect_health.engines_snapshot()["claude"]["ok"] is True
    connect_health.flag_engine_auth_error("claude", "failed to authenticate")
    assert len(calls) == 2
    _reset_engines()


def test_probe_khong_de_den_do_do_luot_chay(monkeypatch):
    """Đèn đỏ do lượt chạy thật (source=run) mạnh hơn suy đoán từ file token - probe không đè."""
    _reset_engines()
    import config as _cfg
    monkeypatch.setattr(_cfg, "read_settings",
                        lambda: {"model": {"main": {"provider": "anthropic-cli"}}})
    monkeypatch.setattr(connect_health, "probe_claude_credentials", lambda path=None: (True, ""))
    connect_health.flag_engine_auth_error("claude", "failed to authenticate")
    connect_health.probe_engines()
    assert connect_health.engines_snapshot()["claude"]["ok"] is False
    _reset_engines()


def test_probe_claude_credentials_cac_nhanh(tmp_path, monkeypatch):
    import json as _json
    import time as _time
    # ép non-darwin để nhánh "chưa có file" không rơi sang đường Keychain khi chạy test trên Mac
    monkeypatch.setattr(connect_health.sys, "platform", "linux")
    p = tmp_path / "cred.json"
    # chưa có file
    ok, msg = connect_health.probe_claude_credentials(p)
    assert ok is False and "Chưa đăng nhập" in msg
    # có refreshToken → sống dù access token quá hạn
    p.write_text(_json.dumps({"claudeAiOauth": {"refreshToken": "r", "expiresAt": 1}}), encoding="utf-8")
    assert connect_health.probe_claude_credentials(p)[0] is True
    # không refreshToken, token còn hạn → sống
    p.write_text(_json.dumps({"claudeAiOauth": {"expiresAt": (_time.time() + 3600) * 1000}}), encoding="utf-8")
    assert connect_health.probe_claude_credentials(p)[0] is True
    # không refreshToken, token quá hạn → chết kèm lý do
    p.write_text(_json.dumps({"claudeAiOauth": {"expiresAt": 1000}}), encoding="utf-8")
    ok, msg = connect_health.probe_claude_credentials(p)
    assert ok is False and "hết hạn" in msg


def test_probe_mac_doc_keychain_khong_bao_do_oan(tmp_path, monkeypatch):
    """Vụ Mac 0.9.229: Claude Code trên macOS cất OAuth trong Keychain, KHÔNG có file
    ~/.claude/.credentials.json → probe cũ kết luận nhầm 'Chưa đăng nhập' và banner đỏ
    treo vĩnh viễn dù não vẫn chạy tốt. Nhánh darwin phải hỏi Keychain, và khi không
    xác định được thì coi là sống (thà bỏ sót còn hơn báo oan)."""
    missing = tmp_path / "khong-ton-tai.json"
    monkeypatch.setattr(connect_health.sys, "platform", "darwin")
    # Keychain có credentials (kèm refreshToken) → sống
    monkeypatch.setattr(connect_health, "_mac_keychain_creds",
                        lambda: ({"claudeAiOauth": {"refreshToken": "r"}}, True))
    assert connect_health.probe_claude_credentials(missing)[0] is True
    # Keychain trả lời chắc chắn KHÔNG có item → thật sự chưa đăng nhập
    monkeypatch.setattr(connect_health, "_mac_keychain_creds", lambda: (None, True))
    ok, msg = connect_health.probe_claude_credentials(missing)
    assert ok is False and "Chưa đăng nhập" in msg
    # Không xác định được (security bị chặn/treo/JSON hỏng) → coi là sống, không báo oan
    monkeypatch.setattr(connect_health, "_mac_keychain_creds", lambda: (None, False))
    assert connect_health.probe_claude_credentials(missing)[0] is True
    # Keychain có item nhưng token hết hạn, không refreshToken → chết kèm lý do hết hạn
    monkeypatch.setattr(connect_health, "_mac_keychain_creds",
                        lambda: ({"claudeAiOauth": {"expiresAt": 1000}}, True))
    ok, msg = connect_health.probe_claude_credentials(missing)
    assert ok is False and "hết hạn" in msg


if __name__ == "__main__":
    # CI chạy TỪNG FILE như script (`python tests/python/test_x.py`), không gọi pytest.
    # Thiếu block này thì file chỉ định nghĩa hàm rồi thoát 0 - test "xanh" mà chưa từng
    # chạy một assertion nào. Bảy file từng ở tình trạng đó, và bốn assertion trong số
    # chúng đang ĐỎ mà không ai biết (xem CHANGELOG 0.13.2).
    import sys
    try:
        import pytest
    except ImportError:
        print("bỏ qua: chưa cài pytest")
        sys.exit(0)
    sys.exit(pytest.main([__file__, "-q"]))
