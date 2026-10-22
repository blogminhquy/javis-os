"""Claude Code phải tự lên bản mới, để model mới tự hiện trong Javis.

    python tests/run.py claude_tu_cap_nhat

Lỗi thật chủ repo báo 29/09/2026: "có sonnet 5.5 rồi mà trên javis chưa update, anh tưởng là
đã update tự động các mô hình rồi chứ?". Đường đọc danh mục model từ binary `claude` vẫn chạy
đúng; cái kẹt là chính binary. Claude Code chỉ tự cập nhật khi người ta mở nó gõ tay, còn Javis
gọi nó chạy ngầm, nên máy đứng ở 2.1.232 (14/08) suốt sáu tuần. Bản Docker kẹt theo kiểu khác:
cache gha giữ nguyên lớp `npm install -g @anthropic-ai/claude-code@latest` vì chuỗi lệnh
không đổi.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import asyncio
import os
import subprocess
import sys
import tempfile
import time

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-claude-upd-")

import claude_cli  # noqa: E402
import claude_update as cu  # noqa: E402
import config as cfgmod  # noqa: E402
import deploy_info  # noqa: E402
import main  # noqa: E402

_fails = []


def check(name, cond, them=""):
    print(("ok   " if cond else "FAIL ") + name + (("  [" + str(them) + "]") if them and not cond else ""))
    if not cond:
        _fails.append(name)


class _R:
    def __init__(self, rc, out):
        self.returncode, self.stdout, self.stderr = rc, out, ""


def _gia_chay(ban_truoc, ban_sau, rc_update=0, ra_update="Successfully updated"):
    """Giả `claude --version` / `claude update`: sau lệnh update thì --version ra bản mới."""
    trang = {"da_update": False, "lenh": []}

    def _chay(cmd, timeout):
        trang["lenh"].append(cmd[1:])
        if cmd[1:] == ["update"]:
            trang["da_update"] = rc_update == 0
            return _R(rc_update, ra_update)
        return _R(0, f"{ban_sau if trang['da_update'] else ban_truoc} (Claude Code)\n")
    return _chay, trang


_goc = (cu._chay, claude_cli.find_claude_cli, deploy_info.deploy_mode)
try:
    claude_cli.find_claude_cli = lambda: "C:/gia/claude.exe"
    deploy_info.deploy_mode = lambda: "windows"

    # 1. Chạy được, phiên bản đổi -> báo đổi và nhớ lại
    cu._chay, _t = _gia_chay("2.1.232", "2.1.284")
    _kq = cu.cap_nhat("tu_dong")
    check("cập nhật thành công thì ok và báo phiên bản đổi",
          _kq.get("ok") and _kq.get("doi") and (_kq["truoc"], _kq["sau"]) == ("2.1.232", "2.1.284"), _kq)
    check("gọi đúng lệnh `claude update`", ["update"] in _t["lenh"], _t["lenh"])
    check("trạng thái được ghi để thẻ Models đọc", cu.doc_trang_thai().get("sau") == "2.1.284")
    check("vừa thử xong thì chưa tới hạn chạy lại", not cu.den_han())
    check("qua 24 giờ thì tới hạn", cu.den_han(time.time() + cu.CHU_KY + 1))

    # 2. Đã mới nhất
    cu._chay, _ = _gia_chay("2.1.284", "2.1.284")
    _kq = cu.cap_nhat()
    check("đã mới nhất thì ok nhưng không báo đổi", _kq.get("ok") and not _kq.get("doi"), _kq)

    # 3. Hỏng -> câu CLI tự nói, không ném lỗi
    cu._chay, _ = _gia_chay("2.1.284", "2.1.284", rc_update=1,
                            ra_update="Checking...\nClaude is managed by Homebrew. Run brew upgrade.")
    _kq = cu.cap_nhat()
    check("hỏng thì trả ok=False kèm dòng lỗi cuối của CLI",
          not _kq.get("ok") and "Homebrew" in (_kq.get("error") or ""), _kq)

    # 4. Docker: không đụng tới CLI
    deploy_info.deploy_mode = lambda: "docker"
    cu._chay, _t = _gia_chay("1", "2")
    _kq = cu.cap_nhat()
    check("Docker không chạy `claude update` (CLI của root, user javis không ghi được)",
          _kq.get("docker") and not _t["lenh"], _kq)
    deploy_info.deploy_mode = lambda: "windows"

    # 5. Chưa cài
    claude_cli.find_claude_cli = lambda: None
    check("chưa cài Claude Code thì báo rõ", "Chưa thấy" in (cu.cap_nhat().get("error") or ""))
finally:
    cu._chay, claude_cli.find_claude_cli, deploy_info.deploy_mode = _goc

# 6. App Claude Desktop đặt DISABLE_AUTOUPDATER=1: phải gỡ ra, không thì `claude update` từ chối
os.environ["DISABLE_AUTOUPDATER"] = "1"
_r = cu._chay([sys.executable, "-c", "import os;print(os.environ.get('DISABLE_AUTOUPDATER'))"], 30)
check("gỡ DISABLE_AUTOUPDATER khỏi môi trường của lệnh con", _r.stdout.strip() == "None", _r.stdout)
os.environ.pop("DISABLE_AUTOUPDATER", None)

# 7. Tắt được bằng biến môi trường
os.environ["JAVIS_CLAUDE_AUTO_UPDATE"] = "0"
check("JAVIS_CLAUDE_AUTO_UPDATE=0 tắt vòng hằng ngày", not cu.bat())
os.environ.pop("JAVIS_CLAUDE_AUTO_UPDATE")
check("mặc định bật", cu.bat())

# 7b. On/off switch on the Models page (customer report 0.270, code 18). The env var stays an
#     override that can only force the updater OFF.
import json  # noqa: E402

check("the switch defaults to on in config", cfgmod._DEFAULT["model"].get(cu.SETTING_KEY) is True)
cfgmod.update_settings({"model": {cu.SETTING_KEY: False}})
check("the saved switch turns the daily update off", not cu.bat())
os.environ["JAVIS_CLAUDE_AUTO_UPDATE"] = "1"
check("env set to 1 does not override a switch the user turned off", not cu.bat())
cfgmod.update_settings({"model": {cu.SETTING_KEY: True}})
check("switch on and env 1 means on", cu.bat())
os.environ["JAVIS_CLAUDE_AUTO_UPDATE"] = "off"
check("env off still forces it off over a switch that is on", not cu.bat() and cu.env_off())
os.environ.pop("JAVIS_CLAUDE_AUTO_UPDATE")
check("no env var: env_off is False", not cu.env_off())

# POST /settings has a per-key allowlist: the new key needs its own branch or it is dropped.
_r = asyncio.run(main.settings_set(section="model", data=json.dumps({cu.SETTING_KEY: False})))
check("POST /settings section=model saves claude_auto_update=false",
      cfgmod.read_settings()["model"].get(cu.SETTING_KEY) is False and not cu.bat(), _r)
_r = asyncio.run(main.settings_set(section="model", data=json.dumps({cu.SETTING_KEY: True})))
check("POST /settings section=model saves claude_auto_update=true",
      cfgmod.read_settings()["model"].get(cu.SETTING_KEY) is True and cu.bat(), _r)

# /claude/status carries the switch state for the card, without running the CLI.
_goc_st = main.claude_auth_status
try:
    main.claude_auth_status = lambda bo_qua_cache=False: {"connected": True}
    cfgmod.update_settings({"model": {cu.SETTING_KEY: False}})
    _st = main.claude_status()
    check("/claude/status reports auto_update=false and no env lock",
          _st.get("auto_update") is False and _st.get("auto_update_env_off") is False, _st)
    os.environ["JAVIS_CLAUDE_AUTO_UPDATE"] = "0"
    _st = main.claude_status()
    check("/claude/status reports the env lock", _st.get("auto_update_env_off") is True, _st)
    os.environ.pop("JAVIS_CLAUDE_AUTO_UPDATE")
finally:
    main.claude_auth_status = _goc_st


# The background loop must read the switch on EVERY pass: off at startup must not kill the loop
# for good, and turning it off later must stop the next run, all without a restart.
class _Stop(BaseException):
    pass


def _drive_loop(passes, on_pass):
    """Run the startup loop for `passes` hourly passes; on_pass(i) runs before pass i+1."""
    runs, tasks = [], []
    real_sleep, real_task = asyncio.sleep, asyncio.create_task
    keep = (main._cap_nhat_claude, cu.den_han, claude_cli.find_claude_cli, deploy_info.deploy_mode)
    state = {"hour": 0}

    async def fake_sleep(sec):
        if sec == 3600:
            state["hour"] += 1
            if state["hour"] >= passes:
                raise _Stop()
            on_pass(state["hour"])
        await real_sleep(0)

    async def fake_update(reason):
        runs.append((state["hour"], reason))
        return {"ok": True}

    async def go():
        await main._tu_cap_nhat_claude()
        if tasks:
            try:
                await tasks[0]
            except _Stop:
                pass

    try:
        asyncio.sleep = fake_sleep
        asyncio.create_task = lambda coro: tasks.append(real_task(coro)) or tasks[-1]
        main._cap_nhat_claude = fake_update
        cu.den_han = lambda now=None: True
        claude_cli.find_claude_cli = lambda: "C:/fake/claude.exe"
        deploy_info.deploy_mode = lambda: "windows"
        asyncio.run(go())
    finally:
        asyncio.sleep, asyncio.create_task = real_sleep, real_task
        main._cap_nhat_claude, cu.den_han, claude_cli.find_claude_cli, deploy_info.deploy_mode = keep
    return runs, tasks


cfgmod.update_settings({"model": {cu.SETTING_KEY: False}})
_runs, _tasks = _drive_loop(3, lambda h: cfgmod.update_settings({"model": {cu.SETTING_KEY: h >= 1}}))
check("the loop still starts when the switch is off at startup", len(_tasks) == 1)
check("switch off: no update; switched on later: the next pass updates without a restart",
      [h for h, _ in _runs] == [1, 2], _runs)
cfgmod.update_settings({"model": {cu.SETTING_KEY: True}})
_runs, _ = _drive_loop(3, lambda h: cfgmod.update_settings({"model": {cu.SETTING_KEY: False}}))
check("switch on: updates; switched off later: the next pass does not", [h for h, _ in _runs] == [0], _runs)
cfgmod.update_settings({"model": {cu.SETTING_KEY: True}})

# 8. Server: sau khi lên bản mới thì báo đúng model MỚI
_goc2 = (cu.cap_nhat, claude_cli.list_models, main.provider_models_index)
try:
    _ds = {"v": ["sonnet", "claude-sonnet-5"]}
    claude_cli.list_models = lambda: list(_ds["v"])

    def _cap_nhat_gia(ly_do):
        _ds["v"] = ["sonnet", "claude-sonnet-5-5", "claude-sonnet-5"]
        return {"ok": True, "doi": True, "truoc": "2.1.232", "sau": "2.1.284"}
    cu.cap_nhat = _cap_nhat_gia

    async def _pmi(provider, refresh=False):
        return {"models": claude_cli.list_models(), "live": True}
    main.provider_models_index = _pmi
    main._PROV_MODELS_CACHE["anthropic-cli"] = {"ids": ["cu"], "ts": time.time()}
    _kq = asyncio.run(main._cap_nhat_claude("tay"))
    check("CANARY: báo Sonnet 5.5 là model mới", _kq.get("model_moi") == ["claude-sonnet-5-5"], _kq)
    check("xoá cache danh sách model cũ", "anthropic-cli" not in main._PROV_MODELS_CACHE)
finally:
    cu.cap_nhat, claude_cli.list_models, main.provider_models_index = _goc2

check("có endpoint POST /claude/update",
      any(getattr(r, "path", "") == "/claude/update" and "POST" in getattr(r, "methods", set())
          for r in main.app.routes))

# 9. Lưới cuối và ảnh Docker
_def = {d["id"]: d for d in main.PROVIDER_DEFS}
for _p in ("anthropic-cli", "anthropic-api"):
    check(f"danh sách dự phòng {_p} có Sonnet 5.5 và Opus 5.5",
          {"claude-sonnet-5-5", "claude-opus-5-5"} <= set(_def[_p]["default_models"]))
check("catalog mặc định trong config có Sonnet 5.5",
      "claude-sonnet-5-5" in cfgmod._DEFAULT["model"]["catalog"]["claude"])
_wf = open(os.path.join(ROOT, ".github", "workflows", "docker-publish.yml"), encoding="utf-8").read()
check("CI truyền số phiên bản Claude Code thật vào build (phá cache lớp npm)",
      "CLAUDE_CLI_VERSION=${{ env.CLAUDE_CLI_VERSION }}" in _wf
      and "npm view @anthropic-ai/claude-code@latest version" in _wf)

print()
if _fails:
    print(f"{len(_fails)} FAIL")
    sys.exit(1)
print("ALL PASS")
