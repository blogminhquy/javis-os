"""Confirmed customer cases sent to the bot owner's fixed staff contact."""
import hashlib
import json
import re
import sqlite3
import time
from contextlib import closing

import bot_price_request as pricing
import bot_case_images

NAME = 'javis_handoff_confirmed_case'
PROMPT_HINT = (
    'After the customer confirms the service scope and fee, call javis_handoff_confirmed_case '
    'in the SAME turn to hand the case to the configured staff contact, including at auto. '
    'Call with {} to read this conversation first. Resolve which company, work and fee were '
    'actually confirmed. A short yes or thumbs-up must refer to the agreed service and fee, '
    'not just receipt of a tax id. Use company_name, tax_id, work_items, fee_vnd (final total), '
    'fee_note (VAT details if confirmed), confirmation_source (customer source_ref) and '
    'source_message_ids supporting the company, work and fee. Human/assistant messages may '
    'support a previously quoted fee, but only a customer message can confirm it. '
    'Keep each company separate. Never copy sample company data or another case price. '
    'For a NEW incorporation use case_type="new_company" and omit tax_id or leave it empty: '
    'a company being formed does not yet have a tax id. Its company_name must appear in the '
    'selected conversation sources. Put outstanding documents in missing_information, such as '
    'the accountant identity-card number. Hand over the agreed case with those gaps clearly '
    'listed so staff can proceed and collect them; do not claim all documents are complete. '
    'Handoffs must include the customer ID-card photos for THIS case. Read image_messages in '
    'the context result, identify the relevant customer photos from the surrounding conversation '
    'and pass their ids as image_message_ids. Never attach photos from an earlier/different case '
    'or price-list images. If the available images are unrelated, state no_case_images_reason. '
    'For a previously delivered text handoff, call again with the same case details and image ids '
    'to supplement its photos without repeating the text. Check attachments.ok before claiming '
    'the complete case was delivered. A photo failure must be reported as partial delivery. '
    'Do not stop at acknowledging the customer or report that generic send tools are hidden. '
    'This scoped handoff tool is available directly. Only ok=true with message_id proves delivery. '
    'The tool sends the customer an acknowledgement after the case and selected images have '
    'delivery receipts. When customer_notified=true, do not send another acknowledgement; '
    'return [IM_LANG] unless there is additional requested information to answer. '
    'If handoff_delivered=true but customer_notified=false, staff already has the case: '
    'report the acknowledgement failure without handing the case over again. '
    'If a handoff already succeeded, '
    'do not send it again. Report actual failures privately to the owner.'
)


def build(mode, raw_route, guard):
    spec = {'fn': NAME, 'description': PROMPT_HINT,
            'schema': {'type': 'object', 'additionalProperties': False, 'properties': {
                'company_name': {'type': 'string', 'minLength': 1, 'maxLength': 200},
                'case_type': {'type': 'string', 'enum': ['existing_company', 'new_company']},
                'tax_id': {'type': 'string', 'pattern': r'^(?:\d{10}(?:-\d{3})?)?$'},
                'missing_information': {'type': 'array', 'maxItems': 12,
                                        'items': {'type': 'string', 'minLength': 1, 'maxLength': 300}},
                'image_message_ids': {'type': 'array', 'maxItems': 10, 'items': {'type': 'string'}},
                'no_case_images_reason': {'type': 'string', 'maxLength': 300},
                'work_items': {'type': 'array', 'minItems': 1, 'maxItems': 12,
                               'items': {'type': 'string', 'minLength': 1, 'maxLength': 500}},
                'fee_vnd': {'type': 'integer', 'minimum': 1},
                'fee_note': {'type': 'string', 'maxLength': 120},
                'confirmation_source': {'type': 'string'},
                'source_message_ids': {'type': 'array', 'minItems': 1, 'maxItems': 20,
                                       'items': {'type': 'string'}}}}}

    async def call(args):
        scope = pricing._scope(mode)
        if not scope:
            return 'ERROR: No authorized customer case handoff for this turn.'
        turn, contact = scope
        context = pricing._request_context(turn)
        if args == {}:
            return json.dumps({'ok': True, 'status': 'context_ready', 'sent': False,
                               'messages': context, 'image_messages': [
                                   {'message_id': row['message_id']} for row in bot_case_images.candidates(turn, context)],
                               'next': PROMPT_HINT}, ensure_ascii=False)
        required = {'company_name', 'work_items', 'fee_vnd',
                    'confirmation_source', 'source_message_ids'}
        if (not isinstance(args, dict) or not required.issubset(args)
                or set(args) - required - {'fee_note', 'tax_id', 'case_type', 'missing_information',
                                          'image_message_ids', 'no_case_images_reason'}
                or not isinstance(args['company_name'], str)
                or not 1 <= len(args['company_name'].strip()) <= 200
                or args.get('case_type', 'existing_company') not in ('existing_company', 'new_company')
                or not isinstance(args.get('tax_id', ''), str)
                or (args.get('tax_id') and not re.fullmatch(r'\d{10}(?:-\d{3})?', args['tax_id']))
                or (args.get('case_type', 'existing_company') == 'existing_company' and not args.get('tax_id'))
                or not isinstance(args.get('missing_information', []), list)
                or len(args.get('missing_information', [])) > 12
                or any(not isinstance(value, str) or not 1 <= len(value.strip()) <= 300
                       for value in args.get('missing_information', []))
                or not isinstance(args.get('image_message_ids', []), list)
                or len(args.get('image_message_ids', [])) > 10
                or any(not isinstance(mid, str) for mid in args.get('image_message_ids', []))
                or not isinstance(args.get('no_case_images_reason', ''), str)
                or len(args.get('no_case_images_reason', '')) > 300
                or not isinstance(args['work_items'], list) or not 1 <= len(args['work_items']) <= 12
                or any(not isinstance(item, str) or not 1 <= len(item.strip()) <= 500
                       for item in args['work_items'])
                or type(args['fee_vnd']) is not int or not 1 <= args['fee_vnd'] <= 10**12
                or not isinstance(args.get('fee_note', ''), str) or len(args.get('fee_note', '')) > 120
                or not isinstance(args['confirmation_source'], str)
                or not isinstance(args['source_message_ids'], list)
                or not 1 <= len(args['source_message_ids']) <= 20):
            return 'ERROR: Provide the confirmed company, tax id, work items, fee and message sources.'
        sources = {ref: row for row in context if row['speaker'] in ('customer', 'human', 'ai')
                   for ref in (row['source_ref'], row['message_id'], row['stored_message_id']) if ref}
        refs = args['source_message_ids'] + [args['confirmation_source']]
        if any(not isinstance(ref, str) or ref not in sources for ref in refs):
            return 'ERROR: Use source_ref values from this handoff tool context: ' + json.dumps(context, ensure_ascii=False)
        if sources[args['confirmation_source']]['speaker'] != 'customer':
            return 'ERROR: The handoff needs a customer confirmation message.'
        evidence = [sources[ref] for ref in refs]
        tax_id = args.get('tax_id', '')
        company_name = args['company_name'].strip()
        normalized_name = ' '.join(company_name.casefold().split())
        if tax_id and not any(tax_id in re.findall(r'\b\d{10}(?:-\d{3})?\b', row['text']) for row in evidence):
            return 'ERROR: The tax id must appear in the selected conversation sources.'
        if not tax_id and not any(normalized_name in ' '.join(row['text'].casefold().split()) for row in evidence):
            return 'ERROR: The new company name must appear in the selected conversation sources.'
        image_ids = args.get('image_message_ids', [])
        available = {row['message_id'] for row in bot_case_images.candidates(turn, evidence)}
        if any(mid not in available for mid in image_ids):
            return 'ERROR: Images must be customer image messages from this case and conversation.'
        if available and not image_ids and not args.get('no_case_images_reason', '').strip():
            return json.dumps({'ok': False, 'status': 'images_required', 'sent': False,
                               'image_message_ids': sorted(available),
                               'next': 'Select the customer ID-card photos for this case and pass image_message_ids. '
                               'If these images belong to another case, explain no_case_images_reason.'}, ensure_ascii=False)
        items = [item.strip() for item in args['work_items']]
        missing = [value.strip() for value in args.get('missing_information', [])]
        total = f"{args['fee_vnd']:,}".replace(',', '.')
        heading = f"{company_name} ({tax_id})" if tax_id else f"{company_name} (thành lập mới, chưa có MST)"
        text = (heading + '\n' + '\n'.join('- ' + item for item in items)
                + ('\nCần bổ sung: ' + '; '.join(missing) if missing else '') + f'\nPhí: {total} đồng'
                + (f" ({args['fee_note'].strip()})" if args.get('fee_note', '').strip() else ''))
        payload = {'threadId': contact['thread_id'], 'threadType': 0, 'text': text}
        entry = next((entry for entry in raw_route.values()
                      if (entry.get('conn') or {}).get('id') == contact['account_id']
                      and entry.get('tool') == 'zalo_send_message'), None)
        if not entry:
            return 'ERROR: The configured Zalo staff contact account is unavailable.'

        def authorized(actual):
            connection = pricing.mcp_store.get_connection(contact['account_id']) or {}
            return bool(pricing._scope(mode) == scope and actual == payload
                        and connection.get('enabled') and connection.get('perm') == 'full'
                        and entry['conn'].get('perm') == 'full'
                        and 'zalo_send_message' not in connection.get('deny_tools', []))

        identity = ['handoff', turn['bot_id'], contact['account_id'], contact['thread_id'],
                    turn['chat_id'], tax_id or 'new-company:' + normalized_name, args['fee_vnd'],
                    sorted(' '.join(item.casefold().split()) for item in items)]
        key = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()

        async def complete(result):
            if result.startswith('ERROR:'):
                return result
            data = json.loads(result)
            if not data.get('ok'):
                return result
            if image_ids:
                images = await bot_case_images.send(mode, raw_route, guard, turn, contact, key, image_ids)
                data.update(ok=images['ok'], text_sent=True, attachments=images)
                if not images['ok']:
                    return json.dumps(data, ensure_ascii=False)
            notice = ('Dạ, em đã chuyển thông tin hồ sơ ' + company_name
                      + (' cùng ảnh đính kèm' if image_ids else '')
                      + ' cho người phụ trách để tiếp nhận xử lý ạ.'
                      + ('\nPhần còn cần bổ sung: ' + '; '.join(missing)[:1000] if missing else ''))
            acknowledgement = {'threadId': turn['chat_id'], 'threadType': 0, 'text': notice}

            def can_acknowledge(actual):
                allowed = authorized(payload) and actual == acknowledgement
                if allowed:
                    import zalo_personal_channel
                    zalo_personal_channel.ghi_da_gui(contact['account_id'], turn['chat_id'], notice)
                return allowed

            ack_key = hashlib.sha256(json.dumps(['case-customer-ack', key]).encode()).hexdigest()
            ack_claimed, prior_ack = pricing._claim(ack_key)
            if ack_claimed:
                try:
                    raw_ack = await guard(entry, 'javis_case_customer_ack', mode,
                                          authorize=can_acknowledge)(acknowledgement)
                    ack = json.loads(raw_ack) if isinstance(raw_ack, str) and not raw_ack.startswith('ERROR:') else raw_ack
                    notification = {'ok': bool(isinstance(ack, dict) and ack.get('success') is True
                                               and ack.get('messageId')), 'handoff_id': key,
                                    'customer_chat_id': turn['chat_id'], 'text': notice}
                    if notification['ok']:
                        notification['message_id'] = ack['messageId']
                    else:
                        notification['error'] = 'Customer acknowledgement not confirmed: ' + str(raw_ack)[:200]
                except Exception as exc:
                    notification = {'ok': False, 'error': f'Customer acknowledgement uncertain: {type(exc).__name__}'}
                pricing._finish(ack_key, json.dumps(notification, ensure_ascii=False))
            else:
                notification = json.loads(prior_ack) if not prior_ack.startswith('ERROR:') else {
                    'ok': False, 'error': prior_ack}
            data.update(ok=notification['ok'], handoff_delivered=True,
                        customer_notified=notification['ok'], customer_notification=notification)
            return json.dumps(data, ensure_ascii=False)

        claimed, previous = pricing._claim(key)
        if not claimed:
            return await complete(previous)
        try:
            with closing(sqlite3.connect(pricing.STATE_DIR / 'bot_price_requests.sqlite3')) as db, db:
                db.execute('CREATE TABLE IF NOT EXISTS case_handoffs '
                           '(id TEXT PRIMARY KEY, bot TEXT, account TEXT, contact TEXT, customer TEXT, '
                           'tax_id TEXT, summary TEXT, sources TEXT, confirmation TEXT, receipt TEXT, created REAL)')
                db.execute('INSERT INTO case_handoffs VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                           (key, turn['bot_id'], contact['account_id'], contact['thread_id'], turn['chat_id'],
                            tax_id, text, json.dumps(evidence, ensure_ascii=False),
                            sources[args['confirmation_source']]['message_id'], '', time.time()))
            if authorized(payload):
                import zalo_personal_channel
                zalo_personal_channel.ghi_da_gui(contact['account_id'], contact['thread_id'], text)
            raw = await guard(entry, NAME, mode, authorize=authorized)(payload)
            data = json.loads(raw) if isinstance(raw, str) and not raw.startswith('ERROR:') else raw
            if isinstance(data, dict) and data.get('success') is True and data.get('messageId'):
                with closing(sqlite3.connect(pricing.STATE_DIR / 'bot_price_requests.sqlite3')) as db, db:
                    db.execute('UPDATE case_handoffs SET receipt=? WHERE id=?', (str(data['messageId']), key))
                result = json.dumps({'ok': True, 'handoff_id': key, 'message_id': data['messageId'],
                                     'tax_id': tax_id, 'customer_chat_id': turn['chat_id']})
            else:
                result = 'ERROR: Case handoff delivery not confirmed: ' + str(raw)[:300]
        except Exception as exc:
            result = f'ERROR: Case handoff delivery uncertain: {type(exc).__name__}: {str(exc)[:200]}'
        pricing._finish(key, result)
        return await complete(result)

    return spec, {'call': call, 'effect': 'danger', 'required_mode': 'safe', 'hat_nhan': True}
