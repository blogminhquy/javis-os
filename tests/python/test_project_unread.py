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

    # 2026-11-20 (owner): chats in no project light "Chưa xếp nhóm" the same way a project lights its folder.
    def ungrouped():
        return store.count_unread(brain=["/b"], project="none")
    base = ungrouped()
    loose = chat(None)
    chat(None, channel="agent:writer")
    chat(None, brain="/other")
    assert ungrouped() == base + 1, "Only unread history chats of this brain with no project count"
    store.set_project(loose, first)
    assert ungrouped() == base, "Moving a chat into a project clears the ungrouped dot"
    store.set_project(loose, None)
    assert ungrouped() == base + 1, "Taking it out of its project brings the dot back"
    store.mark_read(loose)
    assert ungrouped() == base, "Reading the chat clears the ungrouped dot"

    # 2026-11-20 (owner): a chat still running (or open on screen) is not unread yet; the dashboard skips it.
    working = chat(second)
    assert counts()[second] == 1
    assert {p["id"]: p["unread_count"] for p in store.list_projects(brain="/b", skip=[working])}[second] == 0, \
        "A running chat does not light its project folder"
    store.set_project(working, None)
    assert store.count_unread(brain=["/b"], project="none", skip=[working]) == ungrouped() - 1, \
        "A running chat does not light the ungrouped row"
    summary, skipped = store.unread_summary(["/b"]), store.unread_summary(["/b"], skip=[working, "", "x' OR 1"])
    assert skipped["chat"] == summary["chat"] - 1, "A running chat does not light the rail"
    assert store.count_unread(brain=["/b"], project="none", skip=["s%d" % i for i in range(500)]) == ungrouped(), \
        "A long skip list is capped, never a huge query"
    store._conn.close()

print("OK - project unread counts")
