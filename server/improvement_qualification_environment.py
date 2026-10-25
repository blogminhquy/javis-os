"""Pure dummy-only loopback environment for explicit future qualification callers.

This helper does not enable a startup protocol, register a release, inspect a
HOME, contact a provider or grant launch/account authority. Production validators
continue to reject these extra variables. Their use requires a separately scoped
and authenticated qualification entrypoint, with isolated empty storage.
"""
from __future__ import annotations

import re

from improvement_native_protocol import _ENV_FIXED, _ENV_OPTIONAL, _ENV_PATHS, _text, _tree

_DUMMY_KEY = 'javis-native-qualification-dummy'
_EXTRAS = frozenset(('ANTHROPIC_API_KEY', 'ANTHROPIC_BASE_URL'))


def _endpoint(value):
    if type(value) is not str:
        raise ValueError('qualification_endpoint_invalid')
    match = re.fullmatch(r'http://127\.0\.0\.1:([1-9][0-9]{0,4})', value)
    if match is None or int(match[1]) > 65535:
        raise ValueError('qualification_endpoint_invalid')
    return value


def _base(value):
    _tree(value)
    if (type(value) is not dict or not _ENV_PATHS | _ENV_FIXED.keys() <= value.keys()
            or not value.keys() <= _ENV_PATHS | _ENV_FIXED.keys() | _ENV_OPTIONAL):
        raise ValueError('qualification_environment_invalid')
    for name, item in value.items():
        _text(item)
        if name in _ENV_FIXED and item != _ENV_FIXED[name]:
            raise ValueError('qualification_environment_invalid')
    return dict(value)


def dummy_environment(base, *, endpoint):
    """Copy a closed production base and add only the literal local dummy pair."""
    return {**_base(base), 'ANTHROPIC_API_KEY': _DUMMY_KEY, 'ANTHROPIC_BASE_URL': _endpoint(endpoint)}


def validate_dummy_environment(value):
    """Revalidate the complete serialized environment, with no ambient fallback."""
    _tree(value)
    if type(value) is not dict or not _EXTRAS <= value.keys() or value['ANTHROPIC_API_KEY'] != _DUMMY_KEY:
        raise ValueError('qualification_environment_invalid')
    return dummy_environment({key: item for key, item in value.items() if key not in _EXTRAS},
        endpoint=value['ANTHROPIC_BASE_URL'])
