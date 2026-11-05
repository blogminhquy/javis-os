"""Explicit result projection preserves authority, errors, pagination and evidence."""
from _paths import ROOT, SERVER
import json
import unittest
import asyncio
from tool_result_view import project_result


class ResultViewTests(unittest.TestCase):
    def test_gateway_executes_guarded_route_once_before_projection(self):
        import mcp_hub
        calls = []
        async def guarded(args):
            calls.append(args)
            return '{"success":true,"data":[{"id":1,"body":"large"},{"id":2}]}'
        _, routes = mcp_hub._lazy_tools_and_route([], [], [], {'source_read': {'call': guarded}}, 5)
        result = asyncio.run(routes['javis_run_tool']['call'](
            {'name': 'source_read', 'args': {'owner': 'fixture'}, 'result_view': {'pointer': '/data', 'limit': 1}}))
        self.assertEqual(calls, [{'owner': 'fixture'}])
        self.assertEqual(json.loads(result)['data'], [{'id': 1, 'body': 'large'}])
        denied = asyncio.run(routes['javis_run_tool']['call'](
            {'name': 'not_authorized', 'result_view': {'limit': 1}}))
        self.assertTrue(denied.startswith('ERROR:'))
        self.assertEqual(len(calls), 1)

    def test_large_list_has_explicit_page_fields_sources_and_receipt(self):
        original = json.dumps({'successful': True, 'request_id': 'r1', 'data': [
            {'id': n, 'title': f'Task {n}', 'body': 'X' * 1000, 'url': f'https://example.test/{n}'}
            for n in range(500)]})
        result = project_result(original, {'pointer': '/data', 'fields': ['title'], 'limit': 3}, tool_name='read_tasks')
        value = json.loads(result)
        self.assertLess(len(result), len(original) // 20)
        self.assertEqual(value['result_view']['total_items'], 500)
        self.assertEqual(value['result_view']['next_offset'], 3)
        self.assertEqual(value['source_metadata'][0]['request_id'], 'r1')
        self.assertEqual(value['data'][0], {'id': 0, 'title': 'Task 0', 'url': 'https://example.test/0'})
        page = json.loads(project_result(original, {'pointer': '/data', 'offset': 499, 'limit': 3}))
        self.assertEqual(len(page['data']), 1)
        self.assertIsNone(page['result_view']['next_offset'])

    def test_errors_and_execution_failure_remain_verbatim(self):
        for original in ['ERROR: denied', json.dumps({'successful': False, 'data': []}),
                         json.dumps({'data': [{'error': 'partial failure'}]}),
                         json.dumps({'data': {'status_code': 403}})]:
            self.assertEqual(project_result(original, {'pointer': '/data', 'limit': 1}), original)

    def test_default_invalid_views_and_non_json_do_not_lose_data(self):
        raw = '{"data":[1,2,3]}'
        for view in [None, {}, {'pointer': '/missing'}, {'limit': 0}, {'limit': 300}, {'fields': 'title'}]:
            self.assertEqual(project_result(raw, view), raw)
        self.assertEqual(project_result('native text output', {'limit': 2}), 'native text output')

    def test_json_pointer_escaping_and_scalar_result(self):
        raw = '{"a/b":{"~key":42}}'
        self.assertEqual(json.loads(project_result(raw, {'pointer': '/a~1b/~0key'}))['data'], 42)


if __name__ == '__main__':
    unittest.main()
