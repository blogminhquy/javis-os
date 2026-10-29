"""A denied gated Team step must point to a safe recovery, not full mode."""
from _paths import SERVER  # noqa: F401
import team_gate


def test_codex_docker_denial_explains_safe_owner_recovery():
    result = team_gate.provider_support(team_gate.CODEX, codex_sandbox=None)
    assert result['ok'] is False
    assert result['approved_actions'] is False
    message = team_gate.unsupported_text(result['reason'])
    assert 'Cộng sự' in message
    assert 'Thử lại' in message
    assert 'Claude' in message
    assert 'Nhóm tự làm hành động ra ngoài' not in message
    assert 'chưa được tự chạy' in message


def test_provider_support_never_changes_the_gated_contract():
    assert not team_gate.provider_support(team_gate.CODEX, codex_sandbox=None)['ok']
    assert team_gate.provider_support(team_gate.CODEX, codex_sandbox='workspace-write')['ok']
    assert team_gate.provider_support(team_gate.CLAUDE)['ok']
    assert team_gate.provider_support('openrouter', api_providers=('openrouter',))['ok']
    assert not team_gate.provider_support(team_gate.ANTIGRAVITY)['ok']


def test_official_docker_default_is_denied():
    dockerfile = (SERVER.parent / 'Dockerfile').read_text(encoding='utf-8')
    assert 'ENV JAVIS_CODEX_SANDBOX=off' in dockerfile
    assert team_gate.provider_support(team_gate.CODEX, codex_sandbox=None)['ok'] is False


if __name__ == '__main__':
    test_codex_docker_denial_explains_safe_owner_recovery()
    test_provider_support_never_changes_the_gated_contract()
    test_official_docker_default_is_denied()
    print('PASS: safe gated-provider recovery')
