"""Owner-scoped price enquiries, without granting bots a general send tool."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path

import chatbot_store
import localefmt
import mcp_store
import turn_context
from config import STATE_DIR

NAME = 'javis_request_service_price'
PROMPT_HINT = (
    'When a customer asks a service price absent from approved sources, call '
    'javis_request_service_price with no arguments to READ the current conversation first. '
    'Read the returned messages to identify the service the customer currently wants priced, '
    'including reminders such as "Báo phí nha e". Follow topic changes and corrections. '
    'Then call it with service_request (a concise Vietnamese request naming the service and only '
    'relevant confirmed facts) and source_message_ids copied from customer source_ref values '
    'in the returned context. Use "current" for the current customer message. If sources are '
    'rejected, read the returned context and retry with its valid references. '
    'Do not quote a vague reminder as the service request. Do not combine unrelated older services. '
    'If several services remain possible, ask the customer which service before sending. '
    'The destination is the owner-configured pricing contact, including at auto permission. '
    'Do not use a general Zalo send tool for this. A context_ready result only reads context. '
    'Only ok=true together with a message_id proves delivery. '
    'If it fails, notify the owner with the actual error. Never invent a price or claim delivery '
    'before success. Keep internal pricing discussions out of the customer reply. '
    'Use the same process when the customer supplies additional pricing facts, retaining the service '
    'being discussed. At the pricing contact, call '
    'javis_service_price_requests to find the original request, then javis_service_price_reply '
    'to ask the original customer for missing facts or deliver the confirmed quote. Choose a request '
    'only from verified message linkage; ask the contact when ambiguous. Never just acknowledge a '
    'confirmed quote and stop. These scoped tools work at auto; generic send tools remain blocked. '
    'A generic send tool being absent does not prove a connection error. Report the exact scoped '
    'tool failure to the owner, never tell the pricing contact to raise general connection permissions.'
)


def clean_contact(value):
    if isinstance(value, str):
        value = json.loads(value)
    if value == {}:
        return {}
    if not isinstance(value, dict) or set(value) - {'account_id', 'thread_id', 'label'}:
        raise ValueError('Invalid price contact')
    account = value.get('account_id')
    thread = value.get('thread_id')
    if (not isinstance(account, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', account)
            or not isinstance(thread, str) or not re.fullmatch(r'[0-9]{1,40}', thread)):
        raise ValueError('Price contact requires an account id and a DM thread id')
    return {'account_id': account, 'thread_id': thread, 'label': str(value.get('label') or '')[:80]}


def _scope(mode, *, contact_turn=False):
    turn = turn_context.current() or {}
    bot = chatbot_store.get_bot(turn.get('bot_id') or '') or {}
    try:
        contact = clean_contact(bot.get('price_contact') or {})
    except (ValueError, TypeError):
        return None
    if (not turn.get('bot_id') or bot.get('id') != turn['bot_id']
            or mode != 'auto' or turn.get('bot_mode') != 'auto' or not bot.get('enabled')
            or turn.get('price_request_live') is not True
            or bot.get('muc_quyen') != 'auto' or not contact or turn.get('la_chu')
            or turn.get('kenh') != 'zalo_personal'
            or turn.get('account_id') != contact['account_id']
            or contact['account_id'] not in chatbot_store.account_ids_of(bot)
            or not turn.get('chat_id') or not turn.get('message_id')
            or not str(turn.get('customer_question') or '').strip()
            or turn.get('chat_type') != 'private'
            or (contact_turn and (turn['chat_id'] != contact['thread_id']
                                  or turn.get('sender_id') != contact['thread_id']))
            or (not contact_turn and turn['chat_id'] == contact['thread_id'])):
        return None
    return turn, contact


def _database():
    db = sqlite3.connect(Path(STATE_DIR) / 'bot_price_requests.sqlite3')
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS enquiries '
               '(id TEXT PRIMARY KEY, bot TEXT, account TEXT, contact TEXT, customer TEXT, '
               'message TEXT, question TEXT, receipt TEXT, created REAL, closed INTEGER DEFAULT 0)')
    return db


def _request_context(turn):
    """Read only this account/chat, ending at the actual message of this turn."""
    import conversations
    rows = conversations.tin_gan_day('zalo_personal', turn['account_id'], turn['chat_id'], 80)
    current = next((i for i, row in enumerate(rows)
                    if str(row.get('external_message_id') or '') == str(turn['message_id'])), None)
    current_row = rows[current] if current is not None else {}
    if current is None:
        rows = []
    else:
        rows = rows[:current]
    context = [{'message_id': str(row.get('external_message_id') or ''),
                'source_ref': str(row.get('external_message_id') or ''),
                'stored_message_id': str(row.get('id') or ''),
                'speaker': row.get('sender_type'), 'text': str(row.get('text') or '')[:2000]}
               for row in rows if row.get('message_type') == 'text' and row.get('text')]
    context.append({'message_id': str(turn['message_id']), 'source_ref': 'current',
                    'stored_message_id': str(current_row.get('id') or ''), 'speaker': 'customer',
                    'text': str(turn['customer_question'])[:3000]})
    return context


def _claim(key):
    path = Path(STATE_DIR) / 'bot_price_requests.sqlite3'
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('CREATE TABLE IF NOT EXISTS requests (id TEXT PRIMARY KEY, result TEXT)')
        row = db.execute('SELECT result FROM requests WHERE id=?', (key,)).fetchone()
        if row:
            return False, row[0] or 'ERROR: Price request delivery is pending or uncertain; do not resend.'
        inserted = db.execute('INSERT OR IGNORE INTO requests VALUES (?, NULL)', (key,)).rowcount
    return bool(inserted), 'ERROR: Price request already claimed; do not resend.'


def _finish(key, result):
    with closing(sqlite3.connect(Path(STATE_DIR) / 'bot_price_requests.sqlite3')) as db, db:
        db.execute('UPDATE requests SET result=? WHERE id=?', (result, key))


def build(mode, raw_route, guard):
    """Read context, then send a grounded summary to the host-owned pricing contact."""
    spec = {'fn': NAME, 'description': 'Ask the owner-configured contact for the price of the current '
            'service. First call with no arguments to read this conversation. Resolve the service from '
            'the conversation, not just the final reminder. Then supply service_request naming the '
            'service and relevant facts, with source_message_ids copied from customer source_ref values '
            'in that context. Use "current" for the current customer message. '
            'Ask the customer if the service remains ambiguous. Available to configured Zalo bots at auto. '
            'Returns ok=true only after Zalo confirms delivery; errors must be reported to the owner.',
            'schema': {'type': 'object', 'additionalProperties': False,
                       'properties': {'service_request': {'type': 'string', 'minLength': 1, 'maxLength': 2000},
                                      'source_message_ids': {'type': 'array', 'minItems': 1, 'maxItems': 20,
                                                             'items': {'type': 'string'},
                                                             'description': 'Copy customer source_ref from context, '
                                                             'or use "current" for the current message.'}}}}

    async def call(args):
        scope = _scope(mode)
        if not scope:
            return 'ERROR: No authorized price enquiry for this bot turn.'
        turn, contact = scope
        context = _request_context(turn)
        if args == {}:
            return json.dumps({'ok': True, 'status': 'context_ready', 'sent': False, 'messages': context,
                               'next': 'Identify the current service from these messages. Send a concise '
                               'service_request with supporting customer source_message_ids, or ask the '
                               'customer if ambiguous. No message has been sent.'}, ensure_ascii=False)
        if (not isinstance(args, dict) or set(args) != {'service_request', 'source_message_ids'}
                or not isinstance(args['service_request'], str)
                or not 1 <= len(args['service_request'].strip()) <= 2000
                or not isinstance(args['source_message_ids'], list)
                or not 1 <= len(args['source_message_ids']) <= 20):
            return 'ERROR: Provide the resolved service_request and supporting source_message_ids.'
        customer_ids = {value for row in context if row['speaker'] == 'customer'
                        for value in (row['message_id'], row['source_ref'], row['stored_message_id']) if value}
        if any(isinstance(mid, bool) or not isinstance(mid, (str, int))
               or str(mid).strip() not in customer_ids for mid in args['source_message_ids']):
            return 'ERROR: ' + json.dumps({
                'ok': False, 'status': 'invalid_sources', 'sent': False,
                'error': 'Sources must be customer messages in this account and current conversation.',
                'messages': context,
                'next': 'Retry with customer source_ref values from these messages. Use "current" '
                        'for the current message. No message has been sent.'}, ensure_ascii=False)
        entry = next((e for e in raw_route.values() if (e.get('conn') or {}).get('id') == contact['account_id']
                      and e.get('tool') == 'zalo_send_message'), None)
        if not entry:
            return 'ERROR: The configured Zalo account is unavailable.'
        payload = {'threadId': contact['thread_id'], 'threadType': 0,
                   'text': localefmt.chu('Chị báo giúp em phí dịch vụ cho yêu cầu này của khách ạ:\n\n',
                                         'Please confirm the service price for this customer request:\n\n')
                   + args['service_request'].strip()}

        def authorized(actual):
            fresh = _scope(mode)
            connection = mcp_store.get_connection(contact['account_id']) or {}
            return bool(fresh and fresh == scope and actual == payload
                        and connection.get('enabled') and connection.get('perm') == 'full'
                        and 'zalo_send_message' not in connection.get('deny_tools', [])
                        and entry['conn'].get('perm') == 'full')

        key = hashlib.sha256(json.dumps([turn['bot_id'], contact['account_id'], contact['thread_id'], turn['chat_id'],
                                        turn['message_id']], sort_keys=True).encode()).hexdigest()
        # Claim on disk BEFORE sending. A crash/timeout must never silently send a second message.
        claimed, previous = _claim(key)
        if not claimed:
            return previous
        try:
            raw = await guard(entry, NAME, mode, authorize=authorized)(payload)
            data = json.loads(raw) if isinstance(raw, str) and not raw.startswith('ERROR:') else raw
            if isinstance(data, dict) and data.get('success') is True and data.get('messageId'):
                with closing(_database()) as db, db:
                    db.execute('INSERT OR IGNORE INTO enquiries '
                               '(id,bot,account,contact,customer,message,question,receipt,created) '
                               'VALUES (?,?,?,?,?,?,?,?,?)',
                               (key, turn['bot_id'], contact['account_id'], contact['thread_id'],
                                turn['chat_id'], turn['message_id'], payload['text'],
                                str(data['messageId']), time.time()))
                result = json.dumps({'ok': True, 'message_id': data['messageId'],
                                     'request_id': key,
                                     'customer_chat_id': turn['chat_id'],
                                     'request_message_id': turn['message_id']})
            else:
                result = 'ERROR: Price request delivery not confirmed: ' + str(raw)[:300]
        except Exception as exc:
            result = f'ERROR: Price request delivery uncertain: {type(exc).__name__}: {str(exc)[:200]}'
        _finish(key, result)
        return result

    # The prompt names this scoped workflow directly, so it must remain visible in lazy tool mode.
    return spec, {'call': call, 'effect': 'danger', 'required_mode': 'safe', 'hat_nhan': True}


def build_tools(mode, raw_route, guard):
    """Price-request and contact-to-customer continuation, without a general send grant."""
    spec, entry = build(mode, raw_route, guard)
    import bot_case_handoff
    handoff_spec, handoff_route = bot_case_handoff.build(mode, raw_route, guard)
    list_name, reply_name = 'javis_service_price_requests', 'javis_service_price_reply'

    async def pending(args):
        scope = _scope(mode, contact_turn=True)
        if args or not scope:
            return 'ERROR: Only the configured pricing contact may read pending requests.'
        turn, contact = scope
        with closing(_database()) as db:
            rows = db.execute('SELECT id,customer,message,question,receipt FROM enquiries '
                              'WHERE bot=? AND account=? AND contact=? AND closed=0 '
                              'ORDER BY created DESC LIMIT 30',
                              (turn['bot_id'], contact['account_id'], contact['thread_id'])).fetchall()
        return json.dumps({'requests': [dict(row) for row in rows]}, ensure_ascii=False)

    async def reply(args):
        scope = _scope(mode, contact_turn=True)
        if (not scope or not isinstance(args, dict) or set(args) != {'request_id', 'kind', 'text'}
                or args['kind'] not in ('ask_customer', 'quote')
                or not isinstance(args['text'], str) or not 1 <= len(args['text'].strip()) <= 2000
                or not isinstance(args['request_id'], str)):
            return 'ERROR: No authorized pricing follow-up for this turn.'
        turn, contact = scope
        with closing(_database()) as db:
            row = db.execute('SELECT * FROM enquiries WHERE id=? AND bot=? AND account=? '
                             'AND contact=? AND closed=0', (args['request_id'], turn['bot_id'],
                             contact['account_id'], contact['thread_id'])).fetchone()
        if not row:
            return 'ERROR: No pending request for this bot, account and pricing contact.'
        customer = row['customer']
        payload = {'threadId': customer, 'threadType': 0, 'text': args['text'].strip()}
        target = next((e for e in raw_route.values()
                       if (e.get('conn') or {}).get('id') == contact['account_id']
                       and e.get('tool') == 'zalo_send_message'), None)
        if not target:
            return 'ERROR: The configured Zalo account is unavailable.'

        def authorized(actual):
            connection = mcp_store.get_connection(contact['account_id']) or {}
            with closing(_database()) as db:
                fresh_row = db.execute('SELECT * FROM enquiries WHERE id=?', (row['id'],)).fetchone()
            return bool(_scope(mode, contact_turn=True) == scope and actual == payload
                        and fresh_row and dict(fresh_row) == dict(row)
                        and connection.get('enabled') and connection.get('perm') == 'full'
                        and 'zalo_send_message' not in connection.get('deny_tools', []))

        # One contact message has ONE outbound continuation even if the model selects two requests.
        key = hashlib.sha256(json.dumps(['reply', turn['bot_id'], contact['account_id'],
                                         contact['thread_id'], turn['message_id']]).encode()).hexdigest()
        claimed, previous = _claim(key)
        if not claimed:
            return previous
        try:
            raw = await guard(target, reply_name, mode, authorize=authorized)(payload)
            data = json.loads(raw) if isinstance(raw, str) and not raw.startswith('ERROR:') else raw
            if isinstance(data, dict) and data.get('success') is True and data.get('messageId'):
                if args['kind'] == 'quote':
                    with closing(_database()) as db, db:
                        db.execute('UPDATE enquiries SET closed=1 WHERE id=?', (row['id'],))
                result = json.dumps({'ok': True, 'message_id': data['messageId'],
                                     'customer_chat_id': customer, 'request_id': row['id']})
            else:
                result = 'ERROR: Pricing follow-up delivery not confirmed: ' + str(raw)[:300]
        except Exception as exc:
            result = f'ERROR: Pricing follow-up delivery uncertain: {type(exc).__name__}: {str(exc)[:200]}'
        _finish(key, result)
        return result

    list_spec = {'fn': list_name, 'description': 'List pending pricing requests for the verified pricing '
                 'contact in this live Zalo DM. Use actual receipt linkage, never guess a customer.',
                 'schema': {'type': 'object', 'properties': {}, 'additionalProperties': False}}
    reply_spec = {'fn': reply_name, 'description': 'From the verified pricing contact turn only, ask the '
                  'original customer for pricing facts or return the confirmed quote. Destination is fixed '
                  'by a pending request. Verify the request linkage and only include customer-facing text.',
                  'schema': {'type': 'object', 'additionalProperties': False,
                             'properties': {'request_id': {'type': 'string'},
                                            'kind': {'type': 'string', 'enum': ['ask_customer', 'quote']},
                                            'text': {'type': 'string', 'minLength': 1, 'maxLength': 2000}},
                             'required': ['request_id', 'kind', 'text']}}
    return [spec, list_spec, reply_spec, handoff_spec], {
        handoff_spec['fn']: handoff_route,
        spec['fn']: entry,
        list_name: {'call': pending, 'effect': 'read', 'required_mode': 'readonly', 'hat_nhan': True},
        reply_name: {'call': reply, 'effect': 'danger', 'required_mode': 'safe', 'hat_nhan': True}}
