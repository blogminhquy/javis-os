"""A text-only Codex team turn offers the model no code-mode tool (field report 23/11/2026).

Codex 0.171 still handed the model code mode's run-code tool when only `features.code_mode_host` was off. The model
called it, got "code-mode host is disabled" and told the team it "could not read the config". The text-only turn now
switches code mode itself off too."""
from _paths import ROOT, SERVER  # noqa: F401
import team_engine


class FakeCodex:
    def __init__(self):
        self.extra_config = ['features.code_mode=true', 'model="gpt-6-astra"']
        self.profile, self.hub_turn, self.sandbox = "javis", True, "workspace-write"


cc = team_engine.codex_text_only(FakeCodex())
for feat in ("code_mode", "code_mode_only", "code_mode_host"):
    assert f"features.{feat}=false" in cc.extra_config, (feat, cc.extra_config)
assert "features.code_mode=true" not in cc.extra_config, cc.extra_config
assert cc.profile is None and not cc.hub_turn and cc.sandbox == "read-only"
print("ALL PASS")
