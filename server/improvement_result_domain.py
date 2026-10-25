"""Product fences, never qualification/session or account authority.

Historical reports have no execution_domain field. An explicit domain is not
accepted by product consumers, even if malformed or labelled production. Future
qualification owners must also bind immutable M0 session/attempt/call records on
publication and cold read; this preliminary marker fence cannot detect omission.
"""
NATIVE_GATES = frozenset(('native_trace', 'native_authorization', 'native_qualification', 'native_input_delivery'))


def require_product_report(report):
    if type(report) is not dict:
        raise ValueError('invalid_product_report')
    if 'execution_domain' in report:
        raise PermissionError('non_product_execution_domain')
