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
# Tools that would let a scoped bot step outside its scope, so they are refused like the brokers.
# Work they create (reminders, Kanban jobs, team hand-offs, workflows, goals, job follow-ups, page
# watches) runs later, outside this turn, at the default level with every tool. The rest hand the
# bot a shell or a way to change Javis itself.
ESCAPES = frozenset({
    'javis_schedule', 'javis_task', 'javis_team', 'javis_workflow', 'javis_goal', 'javis_job',
    'javis_watch',
    'javis_terminal', 'javis_run_command', 'javis_process',
    'javis_improve', 'javis_plugin', 'javis_add_mcp',
})
REFUSED = BROKERS | ESCAPES
_NAME = re.compile(r'[A-Za-z0-9_-]{1,200}')
_PATTERN = re.compile(r'[A-Za-z0-9_.*-]{1,200}')


def refused(value):
    """The listed names a scoped bot may never hold, so the owner can be told which ones."""
    if not isinstance(value, list):
        return []
    return sorted({x for x in value if isinstance(x, str) and x in REFUSED})


def validate(value):
    """Only an absent field means unscoped. Explicit null, patterns, brokers and escape tools
    are invalid."""
    if (not isinstance(value, list) or len(value) > 256
            or any(not isinstance(x, str) or not _NAME.fullmatch(x) or x in REFUSED for x in value)):
        raise ValueError('invalid_tool_allowlist')
    return sorted(set(value))


def invalid_message(value):
    """Owner-facing reason a list was rejected, naming refused tools when there are any."""
    import localefmt
    names = refused(value)
    if names:
        joined = ', '.join(names)
        return localefmt.chu(
            f"Bot bị giới hạn công cụ không được dùng: {joined}. Các công cụ này tạo việc chạy về sau "
            "ngoài giới hạn của bot, hoặc cho bot chạy lệnh trên máy.",
            f"A scoped bot cannot hold: {joined}. These tools create work that runs later outside the "
            "bot's scope, or give the bot a shell.")
    return localefmt.chu("Danh sách công cụ không hợp lệ", "Invalid tool allowlist")


def _warn_no_scope(bot, account_id, account, channel):
    """A scoped bot whose message cannot be tied to one of its own accounts gets zero tools.
    That is the safe outcome, but the owner must be able to see why, once per bot and reason."""
    import localefmt
    if not account_id:
        why = 'no_account'
        vi = ("tin nhắn đến không mang mã tài khoản (thường gặp ở bot Telegram dùng token), nên "
              "không xác định được tin đến từ tài khoản nào")
        en = ("the message carried no account id (usual for Telegram token bots), so its account "
              "could not be confirmed")
    elif not account:
        why = 'unknown_account'
        vi, en = "tài khoản nhận tin không còn tồn tại", "the receiving account no longer exists"
    elif account.get('channel') != channel:
        why = 'wrong_channel'
        vi, en = "tài khoản nhận tin thuộc kênh khác", "the receiving account belongs to another channel"
    else:
        why = 'not_linked'
        vi, en = "tài khoản nhận tin chưa gắn với bot này", "the receiving account is not linked to this bot"
    name = str(bot.get('name') or bot.get('id'))
    try:
        import inbox
        inbox.add(localefmt.chu(
            f"Bot {name} đang bị giới hạn công cụ nhưng {vi}. Để an toàn, lượt trả lời này chạy với "
            "0 công cụ. Gắn đúng tài khoản cho bot, hoặc bỏ giới hạn công cụ nếu bot không cần.",
            f"Bot {name} is tool-scoped but {en}. To stay safe this reply ran with zero tools. Link "
            "the right account to the bot, or remove the tool scope if the bot does not need it."),
            kind='system', title=localefmt.chu(f"Bot {name} chạy không có công cụ",
                                               f"Bot {name} ran with no tools"),
            source='bot_tool_scope', dedup=f"bot_tool_scope:{bot.get('id')}:{why}")
    except Exception:
        pass
    return why


def _warn_invalid(bot):
    """A stored list that no longer validates (for example one saved before a tool was refused)
    closes the bot to zero tools; tell the owner which names to remove."""
    import localefmt
    name = str(bot.get('name') or bot.get('id'))
    try:
        import inbox
        inbox.add(localefmt.chu(
            f"Bot {name} chạy với 0 công cụ vì danh sách công cụ đã lưu không hợp lệ. "
            + invalid_message(bot.get('tool_allowlist')),
            f"Bot {name} ran with zero tools because its saved tool list is invalid. "
            + invalid_message(bot.get('tool_allowlist'))),
            kind='system', title=localefmt.chu(f"Bot {name} chạy không có công cụ",
                                               f"Bot {name} ran with no tools"),
            source='bot_tool_scope', dedup=f"bot_tool_scope:{bot.get('id')}:invalid")
    except Exception:
        pass


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
            _warn_invalid(bot)
        if not valid:
            allowlist = []
            _warn_no_scope(bot, account_id, account, channel)
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
