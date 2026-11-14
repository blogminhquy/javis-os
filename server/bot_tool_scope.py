"""Host-owned tool scope for chatbots.

A bot may carry `tool_allowlist`: the exact tool names its turns may see and call. The scope
comes from the stored bot record and the account the message really arrived on, never from
model arguments, message metadata or request headers. An absent field keeps today's behaviour;
any other value that fails validation closes the bot down to no tools at all.
"""
import fnmatch
import re

# Brokers reach arbitrary tools or stored results by name, so they can never be allowlisted.
BROKERS = frozenset({'javis_run_tool', 'javis_search_tools', 'javis_query', 'javis_scout'})
_NAME = re.compile(r'[A-Za-z0-9_-]{1,200}')
_PATTERN = re.compile(r'[A-Za-z0-9_.*-]{1,200}')


def validate(value):
    """Only an absent field means unscoped. Explicit null, patterns and brokers are invalid."""
    if (not isinstance(value, list) or len(value) > 256
            or any(not isinstance(x, str) or not _NAME.fullmatch(x) or x in BROKERS for x in value)):
        raise ValueError('invalid_tool_allowlist')
    return sorted(set(value))


def from_bot(bot, account_id, channel):
    """Turn fields for one bot reply. The account must belong to the bot and to this channel,
    otherwise a scoped bot gets an empty scope instead of falling back to everything."""
    import channel_accounts
    import chatbot_store
    account = channel_accounts.get_account(account_id) if account_id else None
    valid = bool(account_id in chatbot_store.account_ids_of(bot)
                 and account and account.get('channel') == channel)
    allowlist = None
    if 'tool_allowlist' in bot:
        try:
            allowlist = validate(bot['tool_allowlist'])
        except ValueError:
            allowlist = []
        if not valid:
            allowlist = []
    return {'account_id': account_id if valid else '', 'bot_id': str(bot['id']),
            'tool_allowlist': allowlist}


def current():
    """The scope of the running turn: None when unscoped, else the exact allowed names."""
    import turn_context
    turn = turn_context.current() or {}
    if turn.get('tool_allowlist') is None:
        return None
    try:
        return validate(turn['tool_allowlist'])
    except ValueError:
        return []


def effective(requested=None):
    """Intersect a caller's requested names or patterns with the host scope. A caller can only
    narrow the host scope, never widen it."""
    host = current()
    if requested is not None:
        requested = list(requested) if isinstance(requested, tuple) else requested
        if (not isinstance(requested, list) or len(requested) > 256
                or any(not isinstance(x, str) or not _PATTERN.fullmatch(x) for x in requested)):
            raise ValueError('invalid_tool_allowlist')
    if host is None:
        return requested
    if requested is None:
        return host
    return [name for name in host if any(fnmatch.fnmatchcase(name, p) for p in requested)]


def permitted(name):
    allowed = current()
    return allowed is None or name in allowed


def native_engine_blocked():
    """CLI engines carry native tools (shell, file, web) that never pass through the hub, so a
    scoped turn must not start one until sandbox confinement can be proven."""
    return current() is not None
