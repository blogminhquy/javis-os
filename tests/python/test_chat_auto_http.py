"""Session selection HTTP contract, isolated from the user's state."""
from _paths import ROOT, SERVER
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

state = tempfile.mkdtemp(prefix="javis-auto-http-")
os.environ.update(JAVIS_STATE_DIR=state, JAVIS_SESSIONS_DB=str(Path(state) / "sessions.db"),
                  BRAINS_DIR=str(Path(state) / "brains"), JAVIS_ALLOWED_HOSTS="testserver",
                  JAVIS_REQUIRE_LOGIN="0")
import main
from fastapi.testclient import TestClient

client = TestClient(main.app)
store = main.get_store()
store.create_session(session_id="one", brain="brain")
store.create_session(session_id="other", brain="other", channel="agent:an")
store.set_pinned_model("other", "openai-oauth", "gpt-6.1-sol")
before = store.get_session("other")
with patch.object(main, "_chat_auto_candidates", AsyncMock(return_value={"low": {"id": "gpt-6-luna"}})):
    response = client.post("/sessions/one/model", data={"routing_mode": "auto"})
    assert response.status_code == 200, response.text
    assert client.get("/sessions/one/meta").json()["routing_mode"] == "auto"
    assert client.post("/sessions/other/model", data={"routing_mode": "auto"}).status_code == 400
    assert store.get_session("other") == before
    with patch.object(main._CHAT_RUNTIME, "get_job", return_value=object()):
        assert client.post("/sessions/one/model", data={"routing_mode": "default"}).status_code == 409
        assert store.get_session("one")["routing_mode"] == "auto"
    assert client.post("/sessions/one/model", data={"provider": "openai-oauth", "model": "auto"}).status_code == 400
    response = client.post("/sessions/one/model", data={"provider": "openai-oauth", "model": "gpt-6.1-sol"})
    assert response.status_code == 200
    assert store.get_session("one")["routing_mode"] == "pinned"
    assert main._chat_provider_for_session({}, store.get_session("one"))[3] == "gpt-6.1-sol"
with patch.object(main, "_chat_auto_candidates", AsyncMock(return_value={})):
    assert client.post("/sessions/one/model", data={"routing_mode": "auto"}).status_code == 409
    assert store.get_session("one")["routing_mode"] == "pinned"
with patch.object(main, "_chat_auto_candidates", AsyncMock(return_value={"low": {"id": "gpt-6-luna"}})):
    # The session was idle on entry but started a turn during the OAuth await.
    with patch.object(main._CHAT_RUNTIME, "get_job", side_effect=[None, object()]):
        assert client.post("/sessions/one/model", data={"routing_mode": "auto"}).status_code == 409
        assert store.get_session("one")["routing_mode"] == "pinned"
        assert store.get_session("one")["pinned_model"] == "gpt-6.1-sol"
assert client.post("/sessions/one/model", data={"routing_mode": "default"}).status_code == 200
assert store.get_session("one")["pinned_provider"] is None
assert store.get_session("other") == before
print("PASS: isolated Auto/default/pin HTTP, busy guard, unavailable, agent pin")
