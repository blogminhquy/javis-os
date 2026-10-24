"""Closed owner controls; runtime pins and schedule positions are host-owned."""
import improvement_cases as IC
from improvement_experiments import _generation, _identifier
from improvement_trial_requests import TrialRequestError, _json_tree

_FIELDS = {
    "create": {"experiment_id", "contract_id", "case_set_id", "base_bundle_id", "expected_context_generation", "repeat_policy", "timeout_seconds"},
    "bind": {"candidate_id", "authority_id", "expected_generation"},
    "freeze": {"ordinal", "kind", "expected_generation"},
    "next": {"comparison_id", "expected_generation"},
    "report": {"comparison_id", "expected_generation"},
    'view-freeze': {'comparison_id', 'expected_generation'},
    'view-evidence': {'comparison_id', 'expected_generation'},
    "select": {"choice", "ordinal", "expected_generation"},
    "cancel": {"expected_generation"}, "resume": {"expected_generation"}, "recover": set(),
    'preparation-freeze': {'expected_generation'}, 'preparation-next': {'expected_generation'},
    'preparation-complete': {'expected_generation'}, 'propose': {'expected_generation'},
    'semantic-review': {'candidate_id', 'expected_generation'},
    'semantic-arbitrate': {'candidate_id', 'receipt_id', 'expected_generation', 'expected_binding_hash', 'verdict', 'reason'},
    'semantic-evidence': {'candidate_id', 'expected_generation'},
    'compose-preview': {'expected_generation'}, 'compose-authorize': {'expected_generation'},
    'compose': {'authorization_id', 'expected_generation'},
    'compose-revoke': {'authorization_id', 'expected_generation'},
}
WORKFLOW_CONTROLS = frozenset(('preparation-freeze', 'preparation-next', 'preparation-complete',
    'propose', 'semantic-review', 'semantic-arbitrate', 'semantic-evidence',
    'compose-preview', 'compose-authorize', 'compose', 'compose-revoke'))


def validate(value, operation):
    try:
        _json_tree(value)
        fields = _FIELDS[operation] | {"event_key"}
        if operation == 'create' and type(value) is dict and 'candidate_policy' in value:
            fields = fields | {'candidate_policy'}
            if (type(value['candidate_policy']) is not str
                    or value['candidate_policy'] != 'two_proposals_and_one_compose'):
                raise ValueError('invalid_experiment_candidate_policy')
        IC._fields(value, fields)
        if type(value["event_key"]) is not str or not 8 <= len(value["event_key"]) <= 160:
            raise ValueError("invalid_event_key")
        for key in ("experiment_id", "contract_id", "case_set_id", "base_bundle_id", "candidate_id", "authority_id", "comparison_id", 'receipt_id', 'authorization_id'):
            if key in value:
                _identifier(value[key])
        for key in ("expected_generation", "expected_context_generation"):
            if key in value:
                _generation(value[key])
        if operation == "create":
            if (type(value["repeat_policy"]) is not str or value["repeat_policy"] not in ("feasibility", "pilot")
                    or type(value["timeout_seconds"]) is not int or not 1 <= value["timeout_seconds"] <= 300):
                raise ValueError("invalid_experiment_request")
        if operation == "freeze":
            if type(value["ordinal"]) is not int or value["ordinal"] not in (1, 2, 3) or value["kind"] not in ("tuning", "final"):
                raise ValueError("invalid_experiment_comparison")
        if operation == "select":
            if not ((value["choice"] == "keep_base" and value["ordinal"] is None)
                    or (value["choice"] == "candidate" and type(value["ordinal"]) is int and value["ordinal"] in (1, 2, 3))):
                raise ValueError("invalid_experiment_selection")
        if operation == 'semantic-arbitrate':
            IC._digest(value['expected_binding_hash'])
            IC._text(value['reason'], 4000)
            if type(value['verdict']) is not str or value['verdict'] not in ('pass', 'fail', 'unknown'):
                raise ValueError('invalid_semantic_owner_verdict')
        return IC._frozen(value)
    except (KeyError, TypeError, ValueError, RecursionError):
        raise TrialRequestError() from None
