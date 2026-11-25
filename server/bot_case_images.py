"""Send only customer images belonging to an already-confirmed case to its fixed staff contact."""
import hashlib
import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

import bot_price_request as pricing

NAME = 'javis_handoff_case_images'


def candidates(turn, evidence):
    import conversations
    rows = conversations.tin_gan_day('zalo_personal', turn['account_id'], turn['chat_id'], 80)
    current = next((i for i, row in enumerate(rows)
                    if str(row.get('external_message_id') or '') == str(turn['message_id'])), None)
    if current is None:
        return []
    refs = {row['message_id'] for row in evidence}
    starts = [i for i, row in enumerate(rows[:current + 1])
              if str(row.get('external_message_id') or '') in refs]
    if not starts:
        return []
    images = []
    for row in rows[min(starts):current + 1]:
        if row.get('sender_type') != 'customer' or row.get('message_type') != 'image':
            continue
        try:
            metadata = row.get('metadata') or json.loads(row.get('metadata_json') or '{}')
        except (TypeError, ValueError):
            continue
        if not isinstance(metadata, dict) or not row.get('external_message_id'):
            continue
        url = str(metadata.get('image_url') or '')
        if url:
            images.append({'message_id': str(row['external_message_id']), 'url': url})
    return images


async def send(mode, raw_route, guard, turn, contact, handoff_id, image_ids):
    import image_vision
    import zalo_cli
    with closing(sqlite3.connect(pricing.STATE_DIR / 'bot_price_requests.sqlite3')) as db:
        db.row_factory = sqlite3.Row
        case = db.execute('SELECT * FROM case_handoffs WHERE id=? AND bot=? AND account=? '
                          'AND contact=? AND customer=? AND receipt<>?',
                          (handoff_id, turn['bot_id'], contact['account_id'], contact['thread_id'],
                           turn['chat_id'], '')).fetchone()
    if not case:
        return {'ok': False, 'error': 'No delivered handoff in this bot/account/conversation.'}
    available = {row['message_id']: row for row in candidates(turn, json.loads(case['sources']))}
    if (not isinstance(image_ids, list) or not 1 <= len(image_ids) <= 10
            or any(not isinstance(mid, str) or mid not in available for mid in image_ids)):
        return {'ok': False, 'error': 'Select customer image message ids from this case context.'}
    entry = next((entry for entry in raw_route.values()
                  if (entry.get('conn') or {}).get('id') == contact['account_id']
                  and entry.get('tool') == 'zalo_send_file'), None)
    if not entry:
        return {'ok': False, 'error': 'The configured Zalo account has no image/file send route.'}
    home = zalo_cli.home_of(entry['conn'])
    if not home:
        return {'ok': False, 'error': 'The configured Zalo account has no upload session.'}
    outbox = zalo_cli.outbox_dir(home)
    outbox.mkdir(parents=True, exist_ok=True)
    results = []
    for mid in dict.fromkeys(image_ids):
        key = hashlib.sha256(json.dumps(['case-image', handoff_id, mid]).encode()).hexdigest()
        with closing(sqlite3.connect(pricing.STATE_DIR / 'bot_price_requests.sqlite3')) as db:
            existing = db.execute('SELECT result FROM requests WHERE id=?', (key,)).fetchone()
        if existing:
            try:
                previous = json.loads(existing[0]) if existing[0] else None
            except (TypeError, ValueError):
                previous = None
            if not isinstance(previous, dict):
                previous = {'ok': False, 'error': 'Image delivery pending or uncertain.'}
            results.append(previous)
            if not previous.get('ok'):
                return {'ok': False, 'images': results}
            continue
        with tempfile.TemporaryDirectory(prefix='case-image-', dir=outbox) as stage:
            assert Path(stage).resolve().is_relative_to(outbox.resolve())
            path, error = await image_vision.fetch_image(available[mid]['url'], Path(stage), 'customer-image')
            if not path:
                return {'ok': False, 'images': results, 'error': error}
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            payload = {'threadId': contact['thread_id'], 'threadType': 0, 'paths': [str(path.resolve())],
                       'caption': 'Ảnh khách gửi kèm hồ sơ: ' + case['summary'].splitlines()[0]}

            def authorized(actual):
                connection = pricing.mcp_store.get_connection(contact['account_id']) or {}
                fresh = {row['message_id']: row for row in candidates(turn, json.loads(case['sources']))}
                allowed = bool(pricing._scope(mode) == (turn, contact) and actual == payload
                            and fresh.get(mid) == available[mid] and path.is_file()
                            and hashlib.sha256(path.read_bytes()).hexdigest() == digest
                            and connection.get('enabled') and connection.get('perm') == 'full'
                            and entry['conn'].get('perm') == 'full'
                            and 'zalo_send_file' not in connection.get('deny_tools', []))
                if allowed:
                    import zalo_personal_channel
                    zalo_personal_channel.ghi_da_gui_anh(contact['account_id'], contact['thread_id'], 1)
                return allowed

            claimed, _ = pricing._claim(key)
            if not claimed:
                return {'ok': False, 'images': results, 'error': 'Image delivery already claimed; check its receipt.'}
            try:
                raw = await guard(entry, NAME, mode, authorize=authorized)(payload)
                data = json.loads(raw) if isinstance(raw, str) and not raw.startswith('ERROR:') else raw
                receipts = data.get('messageIds') if isinstance(data, dict) else None
                result = {'ok': bool(isinstance(data, dict) and data.get('success') is True
                                     and isinstance(receipts, list) and receipts and all(receipts)),
                          'handoff_id': handoff_id, 'source_message_id': mid, 'sha256': digest}
                if result['ok']:
                    result['message_ids'] = receipts
                else:
                    result['error'] = 'Image delivery not confirmed: ' + str(raw)[:200]
            except Exception as exc:
                result = {'ok': False, 'handoff_id': handoff_id, 'source_message_id': mid,
                          'error': f'Image delivery uncertain: {type(exc).__name__}: {str(exc)[:200]}'}
            pricing._finish(key, json.dumps(result, ensure_ascii=False))
            results.append(result)
            if not result['ok']:
                return {'ok': False, 'images': results}
    return {'ok': True, 'images': results}
