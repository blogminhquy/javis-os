"""Input formats selected by an exact host-pinned profile, never a request knob.

The new version is planned support, not a qualification/registration or global
runtime switch. Historical profile versions retain their original formats.
"""
from __future__ import annotations

NATIVE_PROFILE_VERSION = 'claude-owned-images-v3'
_LEGACY = {'baseline': 1, 'view': 3, 'operation': 1}
_NATIVE = {'baseline': 5, 'view': 4, 'operation': 2}


def input_version(pin, surface):
    if type(surface) is not str or surface not in _LEGACY:
        raise ValueError('native_input_surface_invalid')
    if type(pin) is not dict:
        raise ValueError('native_input_profile_invalid')
    if pin.get('profile_version') != NATIVE_PROFILE_VERSION:
        return _LEGACY[surface]
    from improvement_claude import ClaudeTrialAdapter, profile_hash
    # Constructor validates the entire existing configuration grammar without
    # probing a runtime, account, source or process.
    selected = ClaudeTrialAdapter(pin).pin
    if (selected['provider'] != 'anthropic-cli' or selected['engine_id'] != 'claude-sdk'
            or selected['profile_hash'] != profile_hash()):
        raise ValueError('native_input_profile_drift')
    return _NATIVE[surface]
