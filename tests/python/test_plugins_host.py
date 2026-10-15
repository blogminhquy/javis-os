"""Test hệ plugin (plugins_host). Chạy tay:

    python tests/run.py plugins_host

Không cần pytest, không chạm mạng: chỉ dùng plugin bundled trong system/plugins/.
Tự cô lập STATE_DIR sang thư mục tạm để không đụng state thật.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import asyncio
import json
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-plugtest-")

import plugins_host  # noqa: E402


def _names(tools):
    return {t["fn"] for t in tools}


async def main():
    # 1) khám phá bundled + trạng thái mặc định
    desc = {d["slug"]: d for d in plugins_host.describe(None)}
    assert "datetime-vn" in desc and "tool-audit" in desc, sorted(desc)
    assert desc["datetime-vn"]["enabled"] and desc["datetime-vn"]["loaded"]
    assert desc["tool-audit"]["enabled"] is False

    # 2) tool datetime-vn xuất hiện + chạy đúng
    tools, route = plugins_host.plugin_tools("full", None)
    assert {"javis_now", "javis_date_add"} <= _names(tools)
    assert "javis_tool_stats" not in _names(tools)
    now = json.loads(await route["javis_now"]["call"]({}))
    assert now["tz"].startswith("Asia/Ho_Chi_Minh")
    add = json.loads(await route["javis_date_add"]["call"]({"days": 3, "from": "2026-07-09"}))
    assert add["date"] == "2026-07-12", add

    # 3) gate min_mode theo mode chạy
    assert plugins_host._min_mode_ok("readonly", "suggest")
    assert not plugins_host._min_mode_ok("safe", "suggest")
    assert plugins_host._min_mode_ok("safe", "auto")
    assert not plugins_host._min_mode_ok("full", "auto")
    assert plugins_host._min_mode_ok("full", "full")

    # 4) bật tool-audit → hook chạy, đếm đúng
    assert plugins_host.set_enabled("tool-audit", True, None)["ok"]
    assert plugins_host.has_tool_hooks(None)
    tools2, route2 = plugins_host.plugin_tools("full", None)
    assert "javis_tool_stats" in _names(tools2)
    wrapped = plugins_host.wrap_with_hooks("javis_now", route2["javis_now"]["call"], "full", None)
    await wrapped({})
    await wrapped({})
    stats = json.loads(await route2["javis_tool_stats"]["call"]({}))
    assert stats["total_calls"] >= 2, stats
    assert any(t["tool"] == "javis_now" for t in stats["top"]), stats

    # 5) reserved / collision: plugin không được đè tool lõi
    assert "javis_read_file" not in _names(tools2)  # không do plugin cung cấp
    # 6) tắt lại → biến mất
    plugins_host.set_enabled("tool-audit", False, None)
    assert "javis_tool_stats" not in _names(plugins_host.plugin_tools("full", None)[0])

    # 7) 0.162.0, owner decision: user plugins LOAD BY DEFAULT; JAVIS_ENABLE_USER_PLUGINS=false opts out
    vault = tempfile.mkdtemp(prefix="javis-vault-")
    pdir = os.path.join(vault, "plugins", "demo-x")
    os.makedirs(pdir)
    with open(os.path.join(pdir, "plugin.yaml"), "w", encoding="utf-8") as f:
        f.write("name: Demo\nslug: demo-x\nenabled: true\nmin_mode: readonly\n")
    with open(os.path.join(pdir, "plugin.py"), "w", encoding="utf-8") as f:
        f.write("def register(ctx):\n"
                "    ctx.register_tool('demo_ping','ping',lambda a,c:'pong',min_mode='readonly')\n")
    os.environ.pop("JAVIS_ENABLE_USER_PLUGINS", None)
    os.environ.pop("JAVIS_ENABLE_VAULT_PLUGINS", None)   # nothing set: loads by default
    plugins_host.invalidate()
    assert "demo_ping" in _names(plugins_host.plugin_tools("full", vault)[0]), "an enabled vault plugin did not load by default"
    d = {x["slug"]: x for x in plugins_host.describe(vault)}
    assert d["demo-x"]["gated"] is False
    os.environ["JAVIS_ENABLE_VAULT_PLUGINS"] = "false"  # the old alias can still opt out
    plugins_host.invalidate()
    assert "demo_ping" not in _names(plugins_host.plugin_tools("full", vault)[0]), "opt-out through the old alias was ignored"
    assert {x["slug"]: x for x in plugins_host.describe(vault)}["demo-x"]["gated"] is True
    os.environ["JAVIS_ENABLE_USER_PLUGINS"] = "true"    # the new name wins over the old alias
    plugins_host.invalidate()
    assert "demo_ping" in _names(plugins_host.plugin_tools("full", vault)[0]), "JAVIS_ENABLE_USER_PLUGINS=true must win"
    os.environ.pop("JAVIS_ENABLE_USER_PLUGINS", None)

    # 8) GLOBAL plugin (STATE_DIR/plugins) - CHUNG mọi brain + nạp cả khi vault_root=None (đường Claude/Codex)
    os.environ.pop("JAVIS_ENABLE_VAULT_PLUGINS", None)
    gdir = os.path.join(plugins_host.GLOBAL_DIR, "demo-global")
    os.makedirs(gdir, exist_ok=True)
    with open(os.path.join(gdir, "plugin.yaml"), "w", encoding="utf-8") as f:
        f.write("name: Demo Global\nslug: demo-global\nenabled: true\nmin_mode: readonly\n")
    with open(os.path.join(gdir, "plugin.py"), "w", encoding="utf-8") as f:
        f.write("def register(ctx):\n"
                "    ctx.register_tool('demo_global','g',lambda a,c:'G',min_mode='readonly')\n")
    # opted out with =false: not loaded, reported as gated
    os.environ["JAVIS_ENABLE_USER_PLUGINS"] = "false"
    plugins_host.invalidate()
    assert "demo_global" not in _names(plugins_host.plugin_tools("full", None)[0]), "global plugin ran despite the opt-out"
    dg = {x["slug"]: x for x in plugins_host.describe(None)}
    assert dg["demo-global"]["source"] == "user" and dg["demo-global"]["gated"] is True
    # empty value counts as "not set": loads by default, and DESPITE vault_root=None (every brain + Claude/Codex)
    os.environ["JAVIS_ENABLE_USER_PLUGINS"] = ""
    plugins_host.invalidate()
    names_none = _names(plugins_host.plugin_tools("full", None)[0])          # đường hub (Claude/Codex)
    names_brainA = _names(plugins_host.plugin_tools("full", tempfile.mkdtemp())[0])  # brain bất kỳ
    assert "demo_global" in names_none, "global plugin không thấy ở đường vault_root=None"
    assert "demo_global" in names_brainA, "global plugin không dùng được ở brain khác"

    print("OK - test_plugins_host: tất cả assertion pass")


if __name__ == "__main__":
    asyncio.run(main())
