# Full D2 consumer context: source audit, not runtime proof

Read-only audit of implementation commit
ffcd1b44ee7d021be70ab5803ac0d9a3d8c7875a. This supplements the existing D2 map;
disabled-routing, per-read containment and global-registry findings are reused.
No source, test, account or runtime was changed by the audit. It does not claim
main0.298 readiness, native production policy parity or a durable effective pin.

| Consumer | Existing host identity | Remaining boundary |
| --- | --- | --- |
| Dashboard DM | main.run_turn binds TurnTrace, session/message identity, agent and authority_seq; engine creation restores sessions.cli_session_id. | Resolve an immutable host binding before native resume. Session history records native ID/session/time, not effective identity. |
| Team | team_runner request carries team_id/task_id/step_id/turn_id/job_revision/attempt; main binds these before threaded engine construction. | Resolve the durable task/revision pin and attach it explicitly to every new engine, retaining gate context. req.thread alone does not establish native resume. |
| Workflow | execute_workflow_graph creates a local trace; node_executor(node,prompt) and WorkflowCanary._run_node do not carry/bind it. Resume has the same gap. | Bind task/node/attempt around executor and verifier. An inherited enclosing DM/Kanban trace can identify the wrong execution. Preserve parent and workflow identity separately. |
| Kanban | tasks binds kanban job identity; claimed task retains current_run_id and _base_cli receives the full task. | Resolve from stored task/run, preserve across attempts, attach after auxiliary-engine selection. |
| Reminder | reminders.ledger_job(id,slot) deliberately survives retries; _fire retains slot/retry count locally. | Carry firing identity/attempt into _run_task and pin once per firing, rather than per cron definition or retry. |
| Loop | self_improve has brain/slug and a cycle lock; _make_cli distinguishes verification. | Create durable cycle identity before engine construction. last_run is written at completion and cannot identify an in-flight cycle. |
| Goal | resonance.run_once has goal ID/revision/action_id; _ask passes only prompt/tag to its factory. | Preserve operation identity through _ask/_resonance_engine. These internal engines are text-only; the pin must not silently grant skill/tool access. |

turn_context.execution_metadata currently whitelists Team/improvement identifiers
and rejects ordinary execution metadata without team_id. It is not a generic
pin authority; keep durable pin authorization separate from usage telemetry.
Tracing may be disabled and an opaque turn key does not replace a stored pin.

The ordinary ClaudeSDKEngine._options is a narrow adapter consumer, but reusing
trial_profile would replace ordinary owner policy. Use a separate immutable host
binding, including warm_ping, which rebuilds options outside a normal turn.
Runtime checkpoints retain registry revisions rather than immutable asset pins;
resume requires explicit effective identity and compatibility checks.

Task overlays must never overwrite the global capability registry. Missing or
foreign/stale task identity must not silently switch an already pinned task to
canonical baseline. Preserve owner policy, model/reasoning, grants, disabled state
and existing text-only roles. Full D1 native observations and full D2 remain open;
these source findings are inputs to later implementation and verification.
