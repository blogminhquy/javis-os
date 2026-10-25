"""One fresh typed role process; model output never enters production dispatch."""
from __future__ import annotations

import sys
from pathlib import Path

_SERVER_DIR = str(Path(__file__).resolve().parent)
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)


async def run_request(payload, read_control, emit, *, adapter_factory=None, engine_factory=None, native_session=None):
    from improvement_cases import _digest, _fields, _frozen
    from improvement_claude import ClaudeTrialAdapter
    from improvement_operation_profile import OperationProfile
    from improvement_operation_workspace import OperationWorkspace
    from improvement_sandbox import TrialWorkspace
    from improvement_store import _hash, _json
    from improvement_worker import _sdk_hidden_processes

    payload = _frozen(payload)
    _fields(payload, {"version", "config_pin", "workspace_root", "receipt", "capability_hash"})
    if type(payload["version"]) is not int or payload["version"] != 1:
        raise ValueError("unsupported_operation_worker_protocol")
    _digest(payload["capability_hash"])
    root = Path(payload["workspace_root"])
    workspace = OperationWorkspace(root, brain_barrier=TrialWorkspace(root.parent / "trials"))
    receipt = payload["receipt"]
    manifest = workspace.validate(receipt)
    pin = payload["config_pin"]
    if manifest["engine_config_hash"] != _hash(pin):
        raise ValueError("operation_configuration_drift")
    if native_session is None:
        if manifest['version'] != 1: raise ValueError('operation_native_worker_required')
        verified = (adapter_factory or ClaudeTrialAdapter)(pin).verify()
    else:
        if manifest['version'] != 2: raise ValueError('operation_native_input2_required')
        from improvement_native_worker import prepare_native_runtime
        verified, _ = await prepare_native_runtime(native_session, payload, kind='operation')
        read_control, emit = native_session.receive, native_session.send
    if not verified.get("supported") or verified.get("capability_hash") != payload["capability_hash"]:
        raise ValueError("operation_capability_drift")
    identity = {key: receipt[key] for key in ("operation_id", "attempt", "role", "purpose", "input_hash")}
    await emit({"type": "worker_ready", **identity, "capability_hash": payload["capability_hash"]})

    async def before_query():
        await emit({"type": "engine_start_requested", **identity})
        acknowledgement = await read_control()
        if type(acknowledgement) is not dict or _json(acknowledgement) != _json({"type": "engine_start_ack", **identity}):
            raise ValueError("operation_engine_start_not_acknowledged")

    profile = OperationProfile(pin, workspace, receipt, payload["capability_hash"], before_query=before_query)
    if native_session is not None:
        profile.bind_native_runtime(native_session.runtime, environment=native_session._packet['environment'])
    if engine_factory is None:
        from claude_cli import claude_engine
        engine_factory = claude_engine
    engine = engine_factory(system_prompt=profile.system_prompt, cwd=receipt["path"],
        tag=f"improvement-operation:{receipt['operation_id']}:{receipt['attempt']}", allowed_tools=[], model=pin["model"])
    engine.trial_profile = profile
    from contextlib import nullcontext
    with (_sdk_hidden_processes() if native_session is None else nullcontext()):
        async for event in engine.query(profile.user_prompt()):
            await emit({"type": "engine_event", **identity, "event": event})
    if native_session is not None: await native_session.runtime.aclose()
    await emit({"type": "worker_complete", **identity, "tool_denials": profile.denials})


def main():
    import asyncio
    import contextlib
    import json
    maximum = 8 * 1024 * 1024
    output, sequence = sys.stdout.buffer, 0
    native_route = False

    def read_raw():
        raw = sys.stdin.buffer.readline(maximum + 1)
        if not raw or len(raw) > maximum or not raw.endswith(b"\n"):
            raise ValueError("invalid_operation_worker_packet")
        return raw

    def read_packet():
        raw = read_raw()
        value = json.loads(raw)
        if type(value) is not dict:
            raise ValueError("invalid_operation_worker_packet")
        return value

    async def emit(event):
        nonlocal sequence
        sequence += 1
        raw = json.dumps({"version": 1, "sequence": sequence, **event}, ensure_ascii=False,
                         allow_nan=False, separators=(",", ":")).encode() + b"\n"
        if len(raw) > maximum:
            raise ValueError("operation_worker_event_too_large")
        output.write(raw)
        output.flush()

    async def read_control():
        return await asyncio.to_thread(read_packet)

    try:
        raw = read_raw()
        payload = json.loads(raw)
        if type(payload) is not dict: raise ValueError('invalid_operation_worker_packet')
        if payload.get('version') == 3 or payload.get('type') == 'startup3':
            native_route = True
            raise ValueError('qualification_operation_forbidden')
        if payload.get('version') == 2 or payload.get('type') == 'startup2':
            native_route = True
            from improvement_native_worker import run_startup2
            with contextlib.redirect_stdout(sys.stderr):
                return asyncio.run(run_startup2(raw, entrypoint='operation'))
        with contextlib.redirect_stdout(sys.stderr):
            asyncio.run(run_request(payload, read_control, emit))
    except Exception as error:
        if native_route: return 1
        asyncio.run(emit({"type": "worker_error", "reason": "operation_worker_failed", "error_type": type(error).__name__}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
