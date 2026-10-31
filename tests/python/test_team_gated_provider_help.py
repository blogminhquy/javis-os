"""PR #904 (hwangrin): a refused gated Team step must point to a recovery that works on this machine.

    python tests/python/test_team_gated_provider_help.py

The stock Docker image runs Codex without its sandbox, so a gated Work step on Codex is refused before the engine
starts. The message must lead with the recovery (the runner keeps 300 characters of it, the job list 200), name the
assistant, offer only providers that can run the step, and never suggest full mode.
"""
from _paths import ROOT, SERVER  # noqa: F401
import localefmt
import team_gate

localefmt.dat_ngon_ngu_yeu_cau("vi")   # the checks below read the Vietnamese text; English has its own test

# What the team runner and the job list do with the text (team_runner `_run_turn`, agent_jobs `_excerpt`).
RUNNER_PREFIX = "Trợ lý gặp lỗi khi làm: Không dựng được engine: "
LONGEST_REASON = max((team_gate.provider_support(p, codex_sandbox=None)["reason"]
                      for p in (team_gate.CODEX, team_gate.GROK, team_gate.ANTIGRAVITY)), key=len)


def test_recovery_first_survives_the_cuts():
    msg = team_gate.unsupported_text(LONGEST_REASON, assistant="Trợ lý Marketing Tổng Hợp",
                                     choices=("Claude Code", "OpenRouter", "DeepSeek"))
    assert msg.startswith("Bước này chưa chạy.")
    shown_in_runner = msg[:300]
    shown_in_list = (RUNNER_PREFIX + msg)[:200]
    assert "Thử lại" in shown_in_runner and "Thử lại" in shown_in_list, shown_in_list
    assert "Trợ lý Marketing Tổng Hợp" in shown_in_list
    assert "Claude Code, OpenRouter hoặc DeepSeek" in msg
    assert LONGEST_REASON in msg


def test_no_full_mode_and_no_fixed_provider_list():
    msg = team_gate.unsupported_text("x", choices=("OpenRouter",))
    assert "Nhóm tự làm hành động ra ngoài" not in msg
    assert "sang OpenRouter rồi" in msg and "Codex" not in msg and "Claude" not in msg
    assert "trợ lý làm bước này" in msg


def test_no_connected_choice_sends_to_models():
    msg = team_gate.unsupported_text("x")
    assert "trang Models" in msg and "Thử lại" in msg and "Cộng sự" in msg


def test_at_most_three_choices():
    msg = team_gate.unsupported_text("x", choices=("A", "B", "C", "D", ""))
    assert "A, B hoặc C" in msg and "D" not in msg.split("Lý do")[0]


def test_english_screen():
    token = localefmt.dat_ngon_ngu_yeu_cau("en")
    try:
        msg = team_gate.unsupported_text("x", assistant="Writer", choices=("Claude Code", "OpenRouter"))
        bare = team_gate.unsupported_text("x")
    finally:
        localefmt.bo_ngon_ngu_yeu_cau(token)
    assert msg.startswith("This step did not run.") and "switch Writer to Claude Code or OpenRouter" in msg, msg
    assert "Try again" in msg and "Partners page" in msg
    assert "Models page" in bare and "the assistant of this step" in bare


def test_gate_contract_unchanged():
    assert not team_gate.provider_support(team_gate.CODEX, codex_sandbox=None)["ok"]
    assert team_gate.provider_support(team_gate.CODEX, codex_sandbox="workspace-write")["ok"]
    assert team_gate.provider_support(team_gate.CLAUDE)["ok"]
    assert team_gate.provider_support("openrouter", api_providers=("openrouter",))["ok"]
    assert not team_gate.provider_support(team_gate.GROK)["ok"]
    assert not team_gate.provider_support(team_gate.ANTIGRAVITY)["ok"]


def test_official_docker_image_is_the_refused_case():
    assert "ENV JAVIS_CODEX_SANDBOX=off" in (ROOT / "Dockerfile").read_text(encoding="utf-8")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok  ", name)
    print("\nALL OK")
