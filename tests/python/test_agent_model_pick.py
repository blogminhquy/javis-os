"""A new assistant gets a model that fits, from the cards this machine runs (owner, 27/11/2026).

    python tests/run.py agent_model_pick      (no network, no model call)

Owner: "nếu mà tự tạo agent hoặc là cài đặt agent vào thì hãy tự lựa chọn theo các mô hình có sẵn ở trong máy để mà
cài đặt cho phù hợp". Before, every new assistant sat on "Default".

Simulated:

  1. The work tier read from an assistant: code, data, finance, research are heavy; marketing, sales, customer care
     are standard; translation and notes are light.
  2. The card: the first card of the usage order that is signed in and that an assistant runs on. Claude picks the
     line of the tier (Opus, Sonnet, Haiku); every other card keeps its own model. A thinking level only when the
     assistant has none.
  3. Every way a new assistant appears: the Partners form, a Store pack (the ledger still sees the pack's file, an
     update keeps the pick, an uninstall removes it), Javis in chat (after the turn), a team chat, self-learning.
  4. What is never touched: an assistant that already has a model, editing one back to "Default", Javis Core, and a
     machine with no card an assistant can run (it stays on "Default").
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import json
import os
import tempfile
from pathlib import Path

os.environ["JAVIS_STATE_DIR"] = tempfile.mkdtemp(prefix="javis-agent-model-pick-")
BR = Path(tempfile.mkdtemp(prefix="javis-agent-model-pick-brain-")).resolve()
(BR / "agents").mkdir()

import main  # noqa: E402
import agent_model_pick as amp  # noqa: E402
import config as cfgmod  # noqa: E402
import pack_vault  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  [{str(extra)[:400]}]" if extra and not cond else ""))
    if not cond:
        fails.append(name)


# ============================================================
# 1. The tier of an assistant's work
# ============================================================
check("a coding group is heavy", amp.tier_of({"name": "Người review code", "group": "Lập trình"}) == "deep")
check("a security reviewer with no group is heavy (role words)",
      amp.tier_of({"name": "Kiểm tra bảo mật", "role": "Tìm lỗ hổng bảo mật trong code"}) == "deep")
check("finance is heavy", amp.tier_of({"name": "Kế toán", "role": "Đối soát sổ sách, tài chính"}) == "deep")
check("research is heavy", amp.tier_of({"name": "Trợ lý nghiên cứu", "skills": ["query-wiki", "notes"]}) == "deep")
check("marketing is standard even with 'data' in its role",
      amp.tier_of({"name": "Chuyên viên quảng cáo", "group": "Marketing", "role": "Tối ưu bằng data"}) == "standard")
check("customer care is standard, not the lightest line (what a customer reads decides a sale)",
      amp.tier_of({"name": "Linh Hồn Javis Vũ", "role": "Chăm sóc khách hàng cho mọi ngành nghề"}) == "standard")
check("translation is light", amp.tier_of({"name": "Người phiên dịch", "role": "Dịch thuật tài liệu"}) == "light")
check("notes and reminders are light", amp.tier_of({"name": "Thư ký", "role": "Ghi chú cuộc họp, nhắc lịch"}) == "light")
check("an assistant that says little is standard", amp.tier_of({"name": "Bống"}) == "standard")
check("one word in the instructions alone does not make an assistant heavy",
      amp.tier_of({"name": "Bống"}, "Bạn có thể xem data khi cần.") == "standard")
check("the start of the instructions counts when it says it plainly",
      amp.tier_of({"name": "Minh"}, "Bạn là kỹ sư lập trình backend. Bạn viết code, review code và sửa lỗi code.")
      == "deep")

# ============================================================
# 2. The card and the model
# ============================================================
CLAUDE = {"provider": "anthropic-cli", "model": "opus", "models": ["fable", "opus", "sonnet", "haiku"]}
CODEX = {"provider": "openai-oauth", "model": "gpt-5.5", "models": []}
API = {"provider": "anthropic-api", "model": "claude-opus-5-5",
       "models": ["claude-fable-5-2", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"]}
GROQ = {"provider": "groq", "model": "qwen3-32b", "models": []}
check("Claude Code: Opus for heavy work", amp.pick("deep", [CLAUDE])["model"] == "opus")
check("Claude Code: Sonnet for standard work", amp.pick("standard", [CLAUDE])["model"] == "sonnet")
check("Claude Code: Haiku for light work", amp.pick("light", [CLAUDE])["model"] == "haiku")
check("Anthropic API: the newest id of the line", amp.pick("standard", [API])["model"] == "claude-sonnet-5-5")
check("ChatGPT keeps the model set on its card", amp.pick("light", [CODEX]) == {"provider": "openai-oauth",
                                                                               "model": "gpt-5.5", "tier": "light"})
check("the first card of the usage order wins", amp.pick("deep", [CODEX, CLAUDE])["provider"] == "openai-oauth")
check("a card with no known model is skipped", amp.pick("deep", [{"provider": "grok-cli", "model": ""}, GROQ])
      ["provider"] == "groq")
check("no card: nothing picked", amp.pick("deep", []) == {})
check("heavy work also thinks harder when the assistant set no level",
      amp.choose({"name": "Coder", "group": "Lập trình"}, "", [CODEX])
      == {"model": "gpt-5.5", "model_provider": "openai-oauth", "reasoning": "high"})
check("light work thinks less", amp.choose({"name": "Người phiên dịch"}, "", [CLAUDE]).get("reasoning") == "low")
check("standard work keeps the default level", "reasoning" not in amp.choose({"name": "Bống"}, "", [CLAUDE]))
check("a level the assistant set is kept", "reasoning" not in amp.choose(
    {"name": "Coder", "group": "Lập trình", "reasoning": "low"}, "", [CLAUDE]))
check("an assistant that already has a model is not touched", amp.choose({"model": "sonnet"}, "", [CLAUDE]) == {})

# The machine's cards, in the usage order, as main reads them.
VIEW = [{"id": "anthropic-cli", "configured": True, "cli_found": True, "models": ["fable", "opus", "sonnet", "haiku"]},
        {"id": "openai-oauth", "configured": True, "cli_found": True, "models": []},
        {"id": "groq", "configured": True, "models": ["qwen3-32b"]},
        {"id": "gemini", "configured": False, "models": ["gemini-2.5-pro"]}]
main._providers_view = lambda cfg: [dict(x) for x in VIEW]
main._routing_connected_ids = lambda cfg: ["anthropic-cli", "openai-oauth", "groq"]
MCFG = {"main": {"provider": "openai-oauth", "model": "gpt-5.5"}, "reasoning": "medium",
        "order": ["openai-oauth", "anthropic-cli", "groq", "gemini"], "groq_api_key": "gsk_test",
        "profiles": {"openai-oauth": {"model": "gpt-5.5", "reasoning": "medium"},
                     "anthropic-cli": {"model": "", "reasoning": "medium"},
                     "groq": {"model": "qwen3-32b", "reasoning": "low"}}}
cfgmod.update_settings({"model": json.loads(json.dumps(MCFG))})
cards = main._agent_model_cards()
check("cards follow the usage order of the Models page, signed-in ones only",
      [c["provider"] for c in cards] == ["openai-oauth", "anthropic-cli", "groq"], cards)
check("MAIN's card carries MAIN's model", cards[0]["model"] == "gpt-5.5", cards[0])
check("the usage order is not changed by reading it", cfgmod.read_settings()["model"]["order"][0] == "openai-oauth")
cfgmod.update_settings({"model": {"order": ["anthropic-cli", "openai-oauth", "groq", "gemini"],
                                  "main": {"provider": "anthropic-cli", "model": "opus"}}})
check("with Claude Code first, a coding assistant gets Opus on it",
      main._auto_agent_model({"name": "Coder", "group": "Lập trình"}) ==
      {"model": "opus", "model_provider": "anthropic-cli", "reasoning": "high"},
      main._auto_agent_model({"name": "Coder", "group": "Lập trình"}))
check("Javis Core is never given a model this way", main._auto_agent_model({"slug": "javis-core"}) == {})
saved_view = main._providers_view
main._providers_view = lambda cfg: [{"id": "gemini", "configured": False}]
check("no card an assistant can run: it stays on 'Default'", main._auto_agent_model({"name": "Coder"}) == {})
main._providers_view = saved_view

# ============================================================
# 3. Every way a new assistant appears
# ============================================================
client = TestClient(main.app, base_url="http://127.0.0.1:8080")
H = {"origin": "http://127.0.0.1:8080"}
B = str(BR)


def meta_of(slug, root=BR):
    return main._read_md(Path(root) / "agents" / f"{slug}.md")[0] or {}


# The Partners form
r = client.post("/agents", data={"name": "Kỹ sư backend", "role": "Viết và review code backend",
                                      "prompt": "Bạn là kỹ sư lập trình.", "brain": B, "tags": json.dumps(["Lập trình"])},
                headers=H)
check("a NEW assistant left on 'Default' in the form gets a model that fits",
      r.status_code == 200 and meta_of("ky-su-backend").get("model") == "opus"
      and meta_of("ky-su-backend").get("model_provider") == "anthropic-cli", (r.text, meta_of("ky-su-backend")))
check("...and the form is told what was picked", (r.json().get("auto_model") or {}).get("model") == "opus", r.text)
r = client.post("/agents", data={"name": "Bán hàng", "role": "Chốt đơn", "model": "gpt-5.5",
                                      "model_provider": "openai-oauth", "brain": B}, headers=H)
check("a model chosen in the form is kept", meta_of("ban-hang").get("model") == "gpt-5.5", meta_of("ban-hang"))
r = client.post("/agents", data={"name": "Kỹ sư backend", "slug": "ky-su-backend", "role": "Viết code",
                                      "model": "", "brain": B}, headers=H)
check("editing an assistant back to 'Default' keeps 'Default'", meta_of("ky-su-backend").get("model") == "",
      meta_of("ky-su-backend"))

# Javis in chat: the file appears during the turn, the model is given right after it
(BR / "agents" / "dich-gia.md").write_text("---\ntype: agent\nname: Dịch giả\nslug: dich-gia\nrole: Phiên dịch tài liệu\n"
                                           "model: ''\n---\nBạn dịch tài liệu.\n", encoding="utf-8", newline="\n")
got = main._apply_auto_agent_model(BR / "agents" / "dich-gia.md")
check("an assistant Javis wrote with no model gets one that fits",
      got == {"model": "haiku", "model_provider": "anthropic-cli", "reasoning": "low"}
      and meta_of("dich-gia").get("model") == "haiku", (got, meta_of("dich-gia")))
check("...and its instructions are kept", "Bạn dịch tài liệu." in (BR / "agents" / "dich-gia.md").read_text(encoding="utf-8"))
check("an assistant that already has a model is left alone", main._apply_auto_agent_model(BR / "agents" / "ban-hang.md")
      == {} and meta_of("ban-hang").get("model") == "gpt-5.5")
src = (ROOT / "server" / "main.py").read_text(encoding="utf-8")
check("the chat turn gives a model to each assistant it made, and names it in the receipt line",
      'if _it.get("kind") == "agent" and _it.get("act") == "new":' in src
      and "_apply_auto_agent_model," in src and "_it[\"title\"] = f\"{_it.get('title') or _it['id']} · {_am['model']}\"" in src)

# A team chat
slug = main._TeamAdmin().create_agent(B, "Kiểm thử viên", "Kiểm thử API và viết test", "Bạn kiểm thử phần mềm.")
check("an assistant a team chat makes gets a model that fits", meta_of(slug).get("model") == "opus", meta_of(slug))

# Self-learning
src_learn = (ROOT / "server" / "learn.py").read_text(encoding="utf-8")
check("a learned assistant asks for a model before it is written",
      "fm_data.update(self.deps.pick_agent_model(dict(fm_data), new_body) or {})" in src_learn
      and "pick_agent_model=lambda meta, body: _auto_agent_model(meta, body)," in src)

# A Store pack
PACK = Path(tempfile.mkdtemp(prefix="javis-agent-model-pick-pack-"))
(PACK / "agents").mkdir()
AG = "---\ntype: agent\nname: Người review code\nslug: agency-reviewer\nrole: Review code\ngroup: Lập trình\n" \
     "model: ''\nmodel_provider: ''\n---\nBạn review code.\n"
(PACK / "agents" / "agency-reviewer.md").write_text(AG, encoding="utf-8", newline="\n")
rep = pack_vault.cai("javis.test-reviewer", PACK, B)
m = meta_of("agency-reviewer")
check("an assistant a Store pack installs gets a model that fits", m.get("model") == "opus"
      and m.get("model_provider") == "anthropic-cli", (rep, m))
item = pack_vault.doc_so_brain("javis.test-reviewer", BR).get("agents/agency-reviewer") or {}
check("the pack's ledger still sees the file as the pack's own (hash taken after the pick)",
      item.get("hash") == pack_vault._hash(BR / "agents" / "agency-reviewer.md"), item)
cfgmod.update_settings({"model": {"order": ["openai-oauth", "anthropic-cli", "groq", "gemini"],
                                  "main": {"provider": "openai-oauth", "model": "gpt-5.5"}}})
(PACK / "agents" / "agency-reviewer.md").write_text(AG.replace("Bạn review code.", "Bạn review code, bản mới."),
                                                    encoding="utf-8", newline="\n")
rep = pack_vault.cai("javis.test-reviewer", PACK, B)
m = meta_of("agency-reviewer")
check("a pack update brings the new text and keeps the model picked at install",
      "bản mới" in (BR / "agents" / "agency-reviewer.md").read_text(encoding="utf-8")
      and m.get("model") == "opus" and m.get("model_provider") == "anthropic-cli", (rep, m))
gone = pack_vault.go("javis.test-reviewer")
check("uninstalling the pack removes its assistant (it was never seen as edited by the owner)",
      not (BR / "agents" / "agency-reviewer.md").exists(), gone)

print()
if fails:
    print(f"{len(fails)} FAIL")
    raise SystemExit(1)
print("all ok")
