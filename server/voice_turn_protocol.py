"""Durable, transactional voice receipts. No audio, model calls or transcript rewriting."""
import contextvars
import re
import time

response_id = contextvars.ContextVar('voice_response_id', default='')
CLOSINGS = {'vâng anh hiểu rồi', 'anh hiểu rồi', 'cảm ơn', 'được rồi cảm ơn', 'vâng cảm ơn'}


def normalize(text):
    return re.sub(r'[^\w\s]', ' ', str(text).lower()).strip()


def answer_complete(message):
    """Only a narrow declarative explanation is eligible; unfamiliar answers stay unknown.

    This is server-derived metadata, never a client/model-provided permission to ignore a reply.
    Any structured ask, tool or invitation vetoes it, with or without punctuation.
    """
    if not message or message['role'] != 'assistant' or message.get('tool_calls'):
        return False
    text = str(message.get('content') or '').lower().strip()
    if re.search(r'[?？]|javis_ask|xác nhận|đồng ý|muốn|cần|không|em có thể|cho phép|hãy|vui lòng|nhé|chọn|confirm|would you|do you', text):
        return False
    # Free MVP has no general semantic intent classifier. Only reviewed, complete
    # definitions qualify. A prefix plus arbitrary model prose is NOT trusted intent.
    definitions = {
        'thời gian chờ là khoảng nghỉ trước khi gửi câu nói',
        'thời gian chờ là một khoảng nghỉ',
        'điều này có nghĩa là javis đợi bạn nói hết câu trước khi trả lời',
        'response timing is the pause before sending your utterance',
    }
    normalized = re.sub(r'\s+', ' ', normalize(text))
    return normalized in definitions


def _schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS voice_answer_intents (
        message_id INTEGER PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,
        intent TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS voice_receipts (
        session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        utterance_id TEXT NOT NULL, message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
        response_policy TEXT NOT NULL, continuation_of TEXT NOT NULL DEFAULT '',
        answer_requested INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'committed',
        PRIMARY KEY(session_id, utterance_id))''')


def commit(store, sid, uid, text, requested='auto', continuation_of=''):
    if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', uid or ''):
        raise ValueError('Invalid utterance ID')
    def write(conn):
        _schema(conn)
        row = conn.execute('SELECT r.*,m.content FROM voice_receipts r JOIN messages m ON m.id=r.message_id WHERE r.session_id=? AND utterance_id=?', (sid,uid)).fetchone()
        if row:
            if row['content'] != text:
                raise ValueError('An utterance ID cannot change its transcript')
            return {**dict(row), 'created':False}
        last = conn.execute('SELECT id,role,content,tool_calls_json FROM messages WHERE session_id=? ORDER BY id DESC LIMIT 1',(sid,)).fetchone()
        last = dict(last) if last else None
        if last and last.get('tool_calls_json'): last['tool_calls'] = True
        closing = re.sub(r'\s+', ' ', normalize(text)) in CLOSINGS
        intent = conn.execute('SELECT intent FROM voice_answer_intents WHERE message_id=?',(last['id'],)).fetchone() if last else None
        policy = 'ack_only' if requested == 'ack_only' and closing and intent and intent['intent']=='answer_complete' else 'auto'
        now = time.time()
        mid = conn.execute('INSERT INTO messages(session_id,role,content,ts) VALUES(?,?,?,?)',(sid,'user',text,now)).lastrowid
        conn.execute('UPDATE sessions SET msg_count=msg_count+1,updated_at=? WHERE id=?',(now,sid))
        conn.execute('INSERT INTO voice_receipts(session_id,utterance_id,message_id,response_policy,continuation_of,state) VALUES(?,?,?,?,?,?)', (sid,uid,mid,policy,str(continuation_of or '')[:100], 'acknowledged' if policy=='ack_only' else 'committed'))
        return dict(session_id=sid,utterance_id=uid,message_id=mid,response_policy=policy,created=True,state='acknowledged' if policy=='ack_only' else 'committed')
    return store._write(write)


def note_answer(store, mid, raw_answer):
    # Inspect BEFORE control blocks are stripped. A declarative answer followed by
    # JAVIS_ASK is still a question, even when the readable stored text looks complete.
    intent='answer_complete' if answer_complete({'role':'assistant','content':raw_answer}) else 'unknown'
    def write(conn):
        _schema(conn)
        conn.execute('INSERT OR REPLACE INTO voice_answer_intents(message_id,intent) VALUES(?,?)',(mid,intent))
    store._write(write)


def lookup(store, sid, uid):
    def read(conn):
        _schema(conn)
        row=conn.execute('SELECT r.*,m.content FROM voice_receipts r JOIN messages m ON m.id=r.message_id WHERE r.session_id=? AND utterance_id=?',(sid,uid)).fetchone()
        return {**dict(row),'created':False} if row else None
    return store._write(read)


def request_answer(store, sid, mid):
    def write(conn):
        _schema(conn)
        row=conn.execute('SELECT r.*,m.content FROM voice_receipts r JOIN messages m ON m.id=r.message_id WHERE r.session_id=? AND r.message_id=? AND response_policy=\'ack_only\' AND answer_requested=0',(sid,mid)).fetchone()
        if not row: return None
        conn.execute('UPDATE voice_receipts SET answer_requested=1,state=\'committed\' WHERE session_id=? AND message_id=?',(sid,mid))
        return dict(row)
    return store._write(write)


def finish(store, sid, uid, state):
    def write(conn):
        _schema(conn)
        conn.execute('UPDATE voice_receipts SET state=? WHERE session_id=? AND utterance_id=?',(state,sid,uid))
    store._write(write)


async def run(coro, store, sid, uid):
    token=response_id.set(uid)
    state='finished'
    try:
        return await coro
    except BaseException:
        state='interrupted'
        raise
    finally:
        finish(store,sid,uid,state)
        response_id.reset(token)


def frame(obj):
    uid=response_id.get()
    return {**obj,'utterance_id':uid} if uid else obj
