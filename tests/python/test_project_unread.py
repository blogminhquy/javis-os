"""Project badges count unread chats across the whole history, not just its first page."""
from _paths import ROOT, SERVER  # noqa: F401
import tempfile
from pathlib import Path

from sessions import SessionStore


with tempfile.TemporaryDirectory() as tmp:
    store = SessionStore(Path(tmp) / "sessions.db")
    first = store.create_project("First", brain="/b")
    second = store.create_project("Second", brain="/b")
    other = store.create_project("Other brain", brain="/other")

    def chat(project, channel="web", reply=True, brain="/b"):
        sid = store.create_session(brain=brain, channel=channel)
        store.set_project(sid, project)
        store.append_message(sid, "user", "Question")
        if reply:
            store.append_message(sid, "assistant", "Answer")
        return sid

    def counts():
        return {p["id"]: p.get("unread_count") for p in store.list_projects(brain="/b")}

    assert counts() == {first: 0, second: 0}, "Empty projects have no unread replies"
    unread = chat(first)
    store.append_message(unread, "assistant", "Another answer")
    read = chat(first)
    store.mark_read(read)
    chat(first, reply=False)
    archived = chat(first)
    store.archive(archived)
    for channel in ("telegram", "zalo", "bot:shop", "team:group", "teammate:member",
                    "agent:writer", "workflow:write", "coding:repo"):
        chat(first, channel=channel)
    chat(other, brain="/other")
    assert counts() == {first: 1, second: 0}, "Only unread chats visible in project history count"

    # The unread chat is older than a full page of already-read chats.
    for _ in range(25):
        sid = chat(first)
        store.mark_read(sid)
    assert not any(s["unread"] for s in store.list_sessions(brain="/b", project=first, limit=20))
    assert counts()[first] == 1, "Pagination never hides a project's unread badge"
    assert len(store.list_projects(brain="/other")) == 1, "Project counts stay scoped to the brain"

    store.mark_read(unread)
    assert counts()[first] == 0, "Reading the last unread chat clears its project"
    store.mark_unread(unread)
    assert counts()[first] == 1, "Mark as unread restores its project badge"
    store.set_project(unread, second)
    assert counts() == {first: 0, second: 1}, "Moving a chat transfers the unread count"
    store.archive(unread)
    assert counts()[second] == 0, "Archiving clears the project badge"
    store.archive(unread, False)
    assert counts()[second] == 1, "Restoring an unread chat restores its project badge"
    store.delete(unread)
    assert counts()[second] == 0, "Deleting the last unread chat clears its project"
    alias_project = store.create_project("Default brain alias", brain="brain")
    chat(alias_project, brain="/canonical/default")
    assert store.list_projects(brain="brain")[0]["unread_count"] == 1, \
        "Brain aliases on older projects do not hide replies in their canonical sessions"
    store._conn.close()

print("OK - project unread counts")
