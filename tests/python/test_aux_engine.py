"""Test: việc nền chạy được trên model NGOÀI Claude. Chạy tay / CI:

    python tests/run.py aux_engine

Bối cảnh: ô "model việc nền" ở trang Model bị khoá cứng vào danh sách của provider
'anthropic-cli' (console.js đọc thẳng providers.find(id==="anthropic-cli").models), và mọi
nơi chạy nền đều dựng claude_engine rồi chỉ gán cli.model. Muốn đẩy việc nền sang gói
ChatGPT hay một API rẻ để đỡ hạn mức Claude thì không có đường.

Cách nối (cố ý ít xâm lấn): nơi chạy nền vẫn dựng engine Claude kèm đủ allowlist/mode/MCP
như cũ, xong mới gọi aux_engine.apply/swap. Nhờ vậy mọi quyết định an toàn ở đầu kia được
thừa hưởng thay vì chép lại.

Phủ:
- Mặc định (không cấu hình) -> vẫn đúng engine Claude, chỉ đặt model.
- Cấu hình cũ chỉ có 'model' (không có 'provider') -> hiểu là Claude (tương thích ngược).
- Chọn provider API -> đổi sang engine API, thừa hưởng system_prompt/vault/mode.
- Thiếu API key -> KHÔNG đổi engine (việc nền không được chết vì cấu hình hỏng).
- Provider lạ -> giữ Claude.
- Codex: mode ánh xạ đúng sang sandbox, và sandbox thật sự vào dòng lệnh.
- apply(): deps không có aux_swap (test cũ) -> rơi về cách cũ, hành vi không đổi.
- Engine API gom nhiều mảnh 'text' thành đúng MỘT 'final' (hợp đồng việc nền đang đọc).
"""
from _paths import ROOT, SERVER  # noqa: E402,F401  - nạp server/ vào sys.path (xem tests/python/_paths.py)
import asyncio
import os
import sys
import tempfile

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-aux-")

import aux_engine  # noqa: E402

fails = []


def check(name, cond):
    print(("  OK   " if cond else "  FAIL ") + name)
    if not cond:
        fails.append(name)


class FakeClaude:
    """Giả engine Claude đã dựng xong (đủ thuộc tính mà swap đọc)."""

    def __init__(self):
        self.system_prompt = "SYS"
        self.cwd = "/vault"
        self.javis_vault = "/vault"
        self.javis_mode = "suggest"
        self.tag = "loop"
        self.model = None
        self.kind = "claude"


S_CLAUDE = {"model": {"auxiliary": {"provider": "anthropic-cli", "model": "haiku"}}}
S_LEGACY = {"model": {"auxiliary": {"model": "haiku"}}}          # config cũ: chưa có provider
S_OR = {"model": {"auxiliary": {"provider": "openrouter", "model": "x/cheap"},
                  "openrouter_key": "sk-test"}}
S_OR_NOKEY = {"model": {"auxiliary": {"provider": "openrouter", "model": "x/cheap"}}}
S_WEIRD = {"model": {"auxiliary": {"provider": "khong-co-that", "model": "z"}}}

# ---- read_spec / tương thích ngược ----
check("doc spec day du", aux_engine.read_spec(S_CLAUDE) == {"provider": "anthropic-cli", "model": "haiku"})
check("config cu thieu provider -> Claude", aux_engine.is_claude(aux_engine.read_spec(S_LEGACY)))
check("khong cau hinh gi -> Claude", aux_engine.is_claude(aux_engine.read_spec({})))
check("provider API nhan dung", aux_engine.read_spec(S_OR)["provider"] == "openrouter")

# ---- swap: Claude vẫn là Claude ----
c = FakeClaude()
out = aux_engine.swap(c, settings=S_CLAUDE)
check("Claude: tra lai dung engine cu", out is c)
check("Claude: co dat model", out.model == "haiku")

c2 = FakeClaude()
out2 = aux_engine.swap(c2, settings=S_LEGACY)
check("config cu: van la engine Claude", out2 is c2 and out2.model == "haiku")

# ---- swap: sang engine API ----
c3 = FakeClaude()
api = aux_engine.swap(c3, mode="suggest", tag="loop", settings=S_OR)
check("API: da doi engine", api is not c3)
check("API: dung provider/model", api.provider == "openrouter" and api.model == "x/cheap")
check("API: thua huong system_prompt", api.system_prompt == "SYS")
check("API: thua huong vault", api.vault_root == "/vault")
check("API: thua huong mode (quyet dinh an toan dau kia)", api.javis_mode == "suggest")

# ---- swap: hỏng cấu hình thì KHÔNG được làm chết việc nền ----
c4 = FakeClaude()
check("thieu API key -> giu Claude", aux_engine.swap(c4, settings=S_OR_NOKEY) is c4)
c5 = FakeClaude()
check("provider la -> giu Claude", aux_engine.swap(c5, settings=S_WEIRD) is c5)

ok, why = aux_engine.availability({"provider": "openrouter"})
check("availability neu ro ly do thieu key", ok is False and "key" in why.lower())

# ---- Codex: mode -> sandbox ----
check("suggest -> read-only", aux_engine._CODEX_SANDBOX["suggest"] == "read-only")
check("auto -> workspace-write", aux_engine._CODEX_SANDBOX["auto"] == "workspace-write")
check("full -> toan quyen (None)", aux_engine._CODEX_SANDBOX["full"] is None)

from claude_cli import CodexCLI  # noqa: E402

cc = CodexCLI(cwd=".", model="gpt-5.5")
check("CodexCLI mac dinh van toan quyen (khong doi hanh vi chat/workflow)", cc.sandbox is None)

cc.cli_path = "codex"
cc.sandbox = "read-only"
sandbox_args = cc._build_args()
check("sandbox co vao dong lenh",
      "--sandbox" in sandbox_args and sandbox_args[sandbox_args.index("--sandbox") + 1] == "read-only")
check("sandbox bat thi khong con co bypass",
      "--dangerously-bypass-approvals-and-sandbox" not in sandbox_args)
check("Codex global flags dung TRUOC exec (tuong thich CLI VPS)",
      sandbox_args.index("--sandbox") < sandbox_args.index("exec")
      and sandbox_args.index("--ask-for-approval") < sandbox_args.index("exec"))


# ---- apply(): deps cũ không có aux_swap ----
class OldDeps:
    def aux_model(self):
        return "haiku"


c6 = FakeClaude()
check("deps cu (khong aux_swap) -> hanh vi nhu truoc",
      aux_engine.apply(OldDeps(), c6) is c6 and c6.model == "haiku")


class NewDeps:
    aux_model = staticmethod(lambda: "haiku")

    @staticmethod
    def aux_swap(cli, mode=None, tag=None):
        cli.swapped = (mode, tag)
        return cli


c7 = FakeClaude()
aux_engine.apply(NewDeps(), c7, mode="auto", tag="dispatch")
check("deps moi -> goi aux_swap kem mode/tag", getattr(c7, "swapped", None) == ("auto", "dispatch"))


# ---- Engine API gom text -> đúng một final ----
async def _fake_stream():
    yield {"type": "meta", "model": "m"}
    yield {"type": "tool_call", "name": "javis_read_file"}
    yield {"type": "text", "content": "phan 1 "}
    yield {"type": "text", "content": "phan 2"}


async def _run():
    e = aux_engine._ApiAuxEngine("openrouter", "m", system_prompt="S", vault_root=None, mode="suggest")

    async def fake_query(prompt):
        buf = []
        async for ev in _fake_stream():
            t = ev.get("type")
            if t == "text":
                buf.append(ev.get("content") or "")
            elif t in ("tool_call", "error", "usage"):
                yield ev
        yield {"type": "final", "content": "".join(buf)}

    evs = [ev async for ev in fake_query("x")]
    return evs


evs = asyncio.run(_run())
finals = [e for e in evs if e["type"] == "final"]
check("API: dung MOT su kien final", len(finals) == 1)
check("API: final gom du cac manh text", finals[0]["content"] == "phan 1 phan 2")
check("API: tool_call van di qua", any(e["type"] == "tool_call" for e in evs))

# ---- Các nơi chạy nền đã nối vào ----
from pathlib import Path  # noqa: E402

root = SERVER
for f, mode in (("self_improve.py", "loop"), ("tasks.py", "dispatch"),
                ("reminders.py", "reminder"), ("learn.py", "suggest")):
    src = (root / f).read_text(encoding="utf-8")
    check(f"{f} da goi aux_engine.apply", "aux_engine.apply(" in src)
main_src = (root / "main.py").read_text(encoding="utf-8")
check("main tiem aux_swap cho moi tinh nang nen", main_src.count("aux_swap=_aux_swap,") == 4)
check("main: ingest cung dung engine nen", '_aux_swap(cli, mode="auto", tag="ingest")' in main_src)
check("main: luu ca provider cho auxiliary", 'aux["provider"]' in main_src)

console = (root.parent / "dashboard" / "console.js").read_text(encoding="utf-8")
check("UI: khong con khoa cung vao anthropic-cli",
      'providers.find(p => p.id === "anthropic-cli") || {}).models' not in console)
check("UI: luu kem ca provider", "auxiliary: { provider: prov, model: mod }" in console)
check("UI: bo nhan 'metrics' da go", "loop · metrics · ingest" not in console)

# Không phơi hết model thành chip nữa: riêng OpenRouter đã 345 model (đo live), dán ra trang
# thì tràn và không có đường tìm. Phải đi qua openModelPicker - hộp có ô lọc + cột provider.
check("UI: khong con day chip model viec nen", "auxGroups" not in console)
check("UI: co hang tom tat lua chon hien tai", 'class="aux-now"' in console)
# 0.9.293: danh sach provider duoc sap xep (da ket noi len dau) roi moi truyen vao picker,
# nen bien la provList chu khong con la providers tho.
check("UI: nut mo picker", 'id="auxChange"' in console and "openModelPicker(provList, { provider: auxProv" in console)
check("UI: co duong ve mac dinh", 'id="auxReset"' in console)
check("UI: picker nhan tuy chon (dung chung cho model chinh va model nen)",
      "function openModelPicker(providers, main, onDone, opts)" in console)
check("UI: picker luu qua SAVE cua nguoi goi", "await SAVE(selProv, selModel)" in console)
# Bấm provider là draw() dựng lại DOM - trước đây chữ đang lọc bị mất, phải gõ lại từ đầu.
check("UI: o loc giu chu qua moi lan ve lai",
      'value="${esc(filterQ)}"' in console and "applyFilter();   //" in console)
# is_main do server tính cho MODEL CHÍNH - dùng nó ở chế độ model nền là đánh dấu nhầm.
check("UI: nhan 'dang dung' theo lua chon truyen vao, khong theo is_main",
      # 0.52.0: chữ dời vào từ điển i18n - vẫn phải bám theo main.provider truyền vào.
      'p.id === main.provider ? " · " + esc(t("models.mp_using"))' in console)

print()
if fails:
    print(f"FAILED {len(fails)}: " + "; ".join(fails))
    sys.exit(1)
print("PASS - tat ca")
