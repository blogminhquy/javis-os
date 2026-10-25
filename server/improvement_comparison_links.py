"""SQL-only comparison format selection; no grant, source or native readiness."""
from improvement_experiment_protocol import _id
import improvement_store as IM


def _installed(connection, table):
    return connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def comparison_tables(connection):
    """Literal installed formats, sharing one comparison-cell bound."""
    return tuple(table for table in ('improvement_experiment_trial_links', 'improvement_view_trial_links')
        if _installed(connection, table))


def experiment_trial_scope(connection, brain, experiment_id):
    """SQL-scoped union before attempts; never a large unbounded ID list."""
    tables = comparison_tables(connection)
    if _installed(connection, 'improvement_preparation_trial_links'):
        tables += ('improvement_preparation_trial_links',)
    if not tables:
        raise PermissionError('experiment_trial_scope_unavailable')
    return (' UNION ALL '.join('SELECT trial_id,brain_id FROM ' + table + ' WHERE brain_id=? AND experiment_id=?' for table in tables),
        tuple(value for _ in tables for value in (brain, experiment_id)))


def comparison_table(connection, brain, comparison_id):
    """Select one frozen format, never fall back to legacy after view binding."""
    if has_view_binding(connection, brain, comparison_id):
        if not _installed(connection, 'improvement_view_trial_links'):
            raise IM.ConflictError('view_trial_links_unavailable')
        if connection.execute('SELECT 1 FROM improvement_experiment_trial_links WHERE comparison_id=? AND brain_id=? LIMIT 1',
                (comparison_id, brain)).fetchone():
            raise IM.ConflictError('comparison_runtime_changed')
        return 'improvement_view_trial_links'
    if _installed(connection, 'improvement_view_trial_links') and connection.execute(
            'SELECT 1 FROM improvement_view_trial_links WHERE comparison_id=? AND brain_id=? LIMIT 1', (comparison_id, brain)).fetchone():
        raise IM.ConflictError('comparison_runtime_changed')
    return 'improvement_experiment_trial_links'


def has_view_binding(connection, brain, comparison_id):
    _id(comparison_id)
    installed = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='improvement_comparison_views'").fetchone()
    return bool(installed and connection.execute('SELECT 1 FROM improvement_comparison_views WHERE comparison_id=? AND brain_id=?',
        (comparison_id, brain)).fetchone())


def require_legacy_comparison(connection, brain, comparison_id):
    if has_view_binding(connection, brain, comparison_id):
        raise PermissionError('view_trial_version_required')
    # A composed arm always needs its own reviewed view, including its baseline
    # counterpart before any view has been published. Legacy baseline admission
    # must not turn missing independent checks into a native probe or call.
    if _installed(connection, 'improvement_comparisons') and connection.execute(
            'SELECT 1 FROM improvement_comparisons WHERE id=? AND brain_id=? AND ordinal=3',
            (comparison_id, brain)).fetchone():
        raise PermissionError('view_trial_version_required')
