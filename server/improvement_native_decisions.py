"""Durable host image decisions in the existing improvement event/blob owners.

This validates joined data consistency and persistence, not native provenance.
The trusted host callback must check current source/configuration and actual
lease/generation in the supplied transaction. No caller or production route is
enabled here, and no image decision substitutes for the accounting ACK.
"""
from __future__ import annotations

import hashlib
import inspect
from contextlib import closing

import improvement_store as IM
from improvement_blobs import AssetUnavailable, MAX_ASSET_BYTES
from improvement_native_protocol import _canonical, _digest, _fields, _parse, _uint, MAX_PRIVATE_BYTES


def attempt_scope(*, kind, brain_id, receipt, config_pin, capability_hash):
    """Lexical attempt binding shared by the actual writer and historical reader."""
    from improvement_native_protocol import _identity, _text, _tree
    if type(kind) is not str or kind not in ('trial', 'operation'):
        raise ValueError('invalid_native_attempt_scope')
    _text(brain_id, 1000); _digest(capability_hash)
    _tree(receipt); _tree(config_pin)
    if type(receipt) is not dict or type(config_pin) is not dict:
        raise ValueError('invalid_native_attempt_scope')
    return IM._hash({'version': 1, 'kind': kind, 'brain_id': brain_id,
        'identity': _identity(kind, receipt), 'workspace_hash': IM._hash(receipt),
        'engine_config_hash': IM._hash(config_pin), 'capability_hash': capability_hash})


def _joined(value):
    raw = _canonical(value)
    value = _parse(raw)
    _fields(value, {'version', 'launch_nonce', 'worker_pid', 'worker_birth', 'purpose', 'nonce',
        'native_pid', 'native_birth', 'dispatch_hash', 'observation_hash', 'dispatch', 'image'})
    if type(value['version']) is not int or value['version'] != 2:
        raise ValueError('invalid_native_decision')
    for key in ('launch_nonce', 'nonce', 'dispatch_hash', 'observation_hash'): _digest(value[key])
    for key in ('worker_pid', 'native_pid'): _uint(value[key], 32)
    for key in ('worker_birth', 'native_birth'): _uint(value[key])
    if (type(value['purpose']) is not str or value['purpose'] not in
            ('adapter_version', 'auth_status', 'sdk_version', 'query') or value['nonce'] == value['launch_nonce']):
        raise ValueError('invalid_native_decision')
    dispatch = value['dispatch']
    _fields(dispatch, {'version', 'purpose', 'basis', 'argument_consistency', 'environment_hash', 'source_policy_hash'})
    if (type(dispatch['version']) is not int or dispatch['version'] != 1 or dispatch['purpose'] != value['purpose']
            or type(dispatch['basis']) is not str or dispatch['basis'] != 'native_argument_consistency'
            or type(dispatch['argument_consistency']) is not dict):
        raise ValueError('invalid_native_decision')
    for key in ('environment_hash', 'source_policy_hash'): _digest(dispatch[key])
    if hashlib.sha256(_canonical(dispatch)).hexdigest() != value['dispatch_hash']:
        raise ValueError('invalid_native_decision')
    image = value['image']
    if type(image) is not dict or image.get('type') != 'image_observed':
        raise ValueError('invalid_native_decision')
    # Reuse the actual host control grammar/hash recipe. Supplied consistency
    # does not authenticate a peer, launch or native image by itself.
    from improvement_native_transport import _decode_guardian_control2, _control_json
    _decode_guardian_control2(_control_json(image), launch_nonce=value['launch_nonce'],
        expected_sequence=image.get('sequence'), invocations=[{'purpose': value['purpose'], 'nonce': value['nonce']}],
        worker_identity={key: value[key] for key in ('worker_pid', 'worker_birth')})
    if any(type(image[key]) is not type(value[key]) or image[key] != value[key] for key in
            ('purpose', 'nonce', 'native_pid', 'native_birth', 'observation_hash')):
        raise ValueError('invalid_native_decision')
    return value, raw


def _decision(current, connection, joined):
    result = current(connection, _parse(_canonical(joined)))
    if type(result) is not str or result not in ('allow', 'deny'):
        if inspect.iscoroutine(result): result.close()
        raise ValueError('invalid_native_authority_decision')
    return 'deny' if joined['image']['comparison']['matches'] is not True else result


class NativeImageDecisionStore:
    def __init__(self, assets):
        if type(assets) is not IM.ImprovementStore:
            raise TypeError('concrete_improvement_store_required')
        self.assets = assets

    def read(self, principal, joined, *, scope_hash, connection=None):
        """Read exact historical evidence; never authorize a current invocation.

        A result publisher supplies its own final transaction connection to keep
        the event/bytes check in the same publication boundary. No live source,
        current callback, lease transition or native process is touched here.
        """
        brain = IM._brain(principal)
        _digest(scope_hash)
        joined, raw = _joined(joined)
        digest = hashlib.sha256(raw).hexdigest()
        key = 'native-image:' + IM._hash([scope_hash, joined['launch_nonce'], joined['purpose']])

        def load(conn):
            record = self.assets._replay(conn, brain, key, 'native_image_decision',
                {'scope_hash': scope_hash, 'joined_hash': digest})
            if record is None:
                raise PermissionError('native_decision_unavailable')
            _fields(record, {'version', 'scope_hash', 'joined_hash', 'decision', 'blob_hashes'})
            if (type(record['version']) is not int or record['version'] != 1
                    or record['scope_hash'] != scope_hash or record['joined_hash'] != digest
                    or type(record['decision']) is not str or record['decision'] not in ('allow', 'deny')
                    or type(record['blob_hashes']) is not list
                    or not 1 <= len(record['blob_hashes']) <= MAX_PRIVATE_BYTES // MAX_ASSET_BYTES):
                raise AssetUnavailable('native_decision_evidence_unavailable')
            chunks = []
            for blob_hash in record['blob_hashes']:
                _digest(blob_hash)
                chunks.append(self.assets.blobs.read(brain, blob_hash))
            if b''.join(chunks) != raw:
                raise AssetUnavailable('native_decision_evidence_mismatch')
            return {'decision': record['decision'], 'durable_evidence_hash': IM._hash(record)}

        if connection is not None:
            return load(connection)
        if not IM.has_schema(self.assets.store):
            raise PermissionError('improvement_store_unavailable')
        with closing(self.assets.store._conn()) as owned:
            return load(owned)

    def persist(self, principal, joined, *, scope_hash, current):
        brain = IM._brain(principal)
        _digest(scope_hash)
        if (not callable(current) or inspect.iscoroutinefunction(current)
                or inspect.iscoroutinefunction(getattr(current, '__call__', None))):
            raise ValueError('synchronous_native_authority_required')
        joined, raw = _joined(joined)
        digest = hashlib.sha256(raw).hexdigest()
        payload = {'scope_hash': scope_hash, 'joined_hash': digest}
        key = 'native-image:' + IM._hash([scope_hash, joined['launch_nonce'], joined['purpose']])
        assets = self.assets
        if not IM.has_schema(assets.store):
            raise PermissionError('improvement_store_unavailable')
        with assets.store._Tx(assets.store) as connection:
            decision = _decision(current, connection, joined)
            record = assets._replay(connection, brain, key, 'native_image_decision', payload)
            replayed = record is not None
            if record is not None:
                _fields(record, {'version', 'scope_hash', 'joined_hash', 'decision', 'blob_hashes'})
                if (type(record['version']) is not int or record['version'] != 1
                        or record['scope_hash'] != scope_hash or record['joined_hash'] != digest
                        or type(record['decision']) is not str or record['decision'] not in ('allow', 'deny')
                        or type(record['blob_hashes']) is not list
                        or not 1 <= len(record['blob_hashes']) <= MAX_PRIVATE_BYTES // MAX_ASSET_BYTES):
                    raise AssetUnavailable('native_decision_evidence_unavailable')
                chunks = []
                for blob_hash in record['blob_hashes']:
                    _digest(blob_hash)
                    chunks.append(assets.blobs.read(brain, blob_hash))
                if b''.join(chunks) != raw:
                    raise AssetUnavailable('native_decision_evidence_mismatch')
                if record['decision'] != decision:
                    raise IM.ConflictError('native_decision_authority_changed')
            else:
                hashes = [assets.blobs.write(brain, raw[offset:offset + MAX_ASSET_BYTES])
                    for offset in range(0, len(raw), MAX_ASSET_BYTES)]
                record = {'version': 1, **payload, 'decision': decision, 'blob_hashes': hashes}
            if _decision(current, connection, joined) != decision:
                raise IM.ConflictError('native_decision_authority_changed')
            if not replayed:
                assets._event(connection, principal, key, 'native_image_decision', payload, record)
        return {'decision': decision, 'durable_evidence_hash': IM._hash(record)}
