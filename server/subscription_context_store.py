"""Measured input of the LAST model request of a native thread (Codex app-server).

Kept in its own table, not as a column of `sessions`, so the conversation schema stays as it
is. A row is only written from a real per-request measurement; the old turn totals in
`sessions.last_input_tokens` are never copied here. Rows are cleared whenever the native
thread they describe is replaced or dropped, so a number never outlives its thread.
"""
from __future__ import annotations


def migrate(connection):
    connection.execute('''CREATE TABLE IF NOT EXISTS subscription_request_context (
        session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
        provider TEXT NOT NULL DEFAULT '', input_tokens INTEGER NOT NULL DEFAULT 0)''')


def clear(connection, session_id, provider):
    connection.execute('DELETE FROM subscription_request_context WHERE session_id=? AND provider=?',
                       (session_id, provider))
