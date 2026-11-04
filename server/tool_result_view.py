"""Explicit JSON views of a tool result, after the normal authorized execution.

No cache, source-file writes, result replay or tool re-execution occurs here.
Unrecognized shapes and every detected error retain the original result.
"""
from __future__ import annotations

import hashlib
import json

_META = frozenset({'id', 'url', 'source', 'sources', 'source_refs', 'citations',
                   'status', 'status_code', 'success', 'successful', 'isError',
                   'error', 'errors', 'request_id', 'trace_id', 'next_cursor', 'has_more',
                   'path', 'file_path', 'record_id', 'timestamp', 'created_at', 'updated_at',
                   'verified_at', 'source_read_at', 'compiled_at', 'total_count', 'total',
                   'next_page', 'operation', 'action', 'affected_count'})


def _has_error(value, depth=0):
    if depth > 50:
        return True
    if isinstance(value, dict):
        if value.get('isError') is True or value.get('success') is False or value.get('successful') is False:
            return True
        if value.get('error') or value.get('errors'):
            return True
        if str(value.get('status', '')).lower() in ('error', 'failed', 'failure'):
            return True
        if isinstance(value.get('status_code'), int) and value['status_code'] >= 400:
            return True
        return any(_has_error(x, depth + 1) for x in value.values())
    if isinstance(value, list):
        return any(_has_error(x, depth + 1) for x in value)
    return False


def project_result(original, view, *, tool_name=''):
    """Select an explicit JSON pointer, fields and page; never guess a response shape."""
    if not isinstance(view, dict) or not view:
        return original
    try:
        raw = original if isinstance(original, str) else json.dumps(original, ensure_ascii=False)
        if raw.lstrip().startswith('ERROR:'):
            return original
        data = json.loads(raw)
        if _has_error(data):
            return original
        pointer = view.get('pointer', '')
        if not isinstance(pointer, str) or pointer and not pointer.startswith('/'):
            return original
        selected = data
        metadata = []
        for part in pointer.split('/')[1:] if pointer else []:
            if isinstance(selected, dict):
                meta = {k: v for k, v in selected.items() if k in _META}
                if meta:
                    metadata.append(meta)
            key = part.replace('~1', '/').replace('~0', '~')
            if isinstance(selected, list):
                if not key.isdigit():
                    return original
                selected = selected[int(key)]
            else:
                selected = selected[key]
        fields = view.get('fields')
        if fields is not None and (not isinstance(fields, list) or not all(isinstance(k, str) for k in fields)):
            return original

        def record(item):
            if not fields or not isinstance(item, dict):
                return item
            return {k: v for k, v in item.items() if k in fields or k in _META}

        offset = int(view.get('offset', 0))
        limit = int(view.get('limit', 20))
        if offset < 0 or not 1 <= limit <= 200:
            return original
        if isinstance(selected, list):
            total = len(selected)
            result = [record(item) for item in selected[offset:offset + limit]]
            next_offset = offset + len(result) if offset + len(result) < total else None
        elif offset:
            return original
        else:
            total, result, next_offset = None, record(selected), None
        return json.dumps({'result_view': {'tool': tool_name, 'pointer': pointer,
                           'fields': fields, 'offset': offset, 'total_items': total,
                           'next_offset': next_offset, 'original_chars': len(raw),
                           'original_sha256': hashlib.sha256(raw.encode()).hexdigest(),
                           'note': 'Explicit view only. Omitted fields are not evidence of absence. '
                                   'Use an authorized read to retrieve more; never repeat a write for pagination.'},
                           'source_metadata': metadata, 'data': result}, ensure_ascii=False)
    except (ValueError, TypeError, KeyError, IndexError, RecursionError, OverflowError, UnicodeError):
        return original
