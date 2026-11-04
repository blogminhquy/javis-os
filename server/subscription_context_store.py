"""Request measurements kept outside the qualified conversation-source schema."""
from __future__ import annotations


def migrate(connection):
    """Import only earlier request measurements, never historical turn totals.

    Early opt-in patches added bookkeeping columns to sessions. Move those values
    transactionally, preserving all conversation columns and native thread IDs.
    """
    connection.execute('SAVEPOINT subscription_context_migration')
    try:
        connection.execute('''CREATE TABLE IF NOT EXISTS subscription_request_context (
            session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
            provider TEXT NOT NULL DEFAULT '', input_tokens INTEGER NOT NULL DEFAULT 0)''')
        columns = {row[1] for row in connection.execute('PRAGMA table_info(sessions)')}
        if {'last_context_input_tokens', 'last_context_provider'} <= columns:
            connection.execute('''INSERT INTO subscription_request_context(session_id,provider,input_tokens)
                SELECT id,COALESCE(last_context_provider,''),MAX(0,CAST(last_context_input_tokens AS INTEGER))
                FROM sessions WHERE 1 ON CONFLICT(session_id) DO NOTHING''')
        if 'codex_last_request_input_tokens' in columns:
            connection.execute('''INSERT INTO subscription_request_context(session_id,provider,input_tokens)
                SELECT id,'codex',MAX(0,CAST(codex_last_request_input_tokens AS INTEGER)) FROM sessions
                WHERE codex_thread_id IS NOT NULL ON CONFLICT(session_id) DO NOTHING''')
        for column in ('last_context_input_tokens', 'last_context_provider', 'codex_last_request_input_tokens'):
            if column in columns:
                connection.execute('ALTER TABLE sessions DROP COLUMN ' + column)
        connection.execute('RELEASE subscription_context_migration')
    except Exception:
        connection.execute('ROLLBACK TO subscription_context_migration')
        connection.execute('RELEASE subscription_context_migration')
        raise


def clear(connection, session_id, provider):
    connection.execute('DELETE FROM subscription_request_context WHERE session_id=? AND provider=?',
                       (session_id, provider))
