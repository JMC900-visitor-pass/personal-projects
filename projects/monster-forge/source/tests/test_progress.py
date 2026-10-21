import io
import json
import unittest
from unittest.mock import patch
import app


class ProgressTests(unittest.TestCase):
    def test_partial_fields_ignore_nested_keys_and_quoted_braces(self):
        content = '{"name":"A } \\\" beast", "abilities":{"str":12}, "traits":[{"name":"nested"}], "actions":['
        fields, current = app.stream_fields(content)
        self.assertEqual(fields, ['name', 'abilities', 'traits'])
        self.assertEqual(current, 'actions')

    def test_unfinished_number_and_string_do_not_count_as_complete(self):
        for content in ['{"hit_points":1', '{"name":"not finished']:
            self.assertEqual(app.stream_fields(content)[0], [])
        self.assertEqual(app.stream_fields('{"hit_points":15,')[0], ['hit_points'])

    def test_stream_assembles_content_and_reports_each_packet(self):
        packets = [{'message':{'content':'{"name":'}}, {'message':{'content':'"Test"}'}}, {'done':True, 'eval_count':6}]
        response = io.BytesIO(('\n'.join(json.dumps(p) for p in packets)+'\n').encode())
        updates = []
        with patch.object(app, 'urlopen', return_value=response):
            result = app.ollama('/api/chat', {'stream':True}, on_chunk=updates.append)
        self.assertEqual(result['message']['content'], '{"name":"Test"}')
        self.assertEqual(len(updates), 3)
        self.assertEqual(result['eval_count'], 6)

    def test_incomplete_or_error_stream_is_rejected(self):
        for packet in [{'message':{'content':'{}'}}, {'error':'model unavailable'}]:
            response = io.BytesIO((json.dumps(packet)+'\n').encode())
            with patch.object(app, 'urlopen', return_value=response), self.assertRaises(RuntimeError):
                app.ollama('/api/chat', {'stream':True})

    def test_retry_keeps_progress_and_logs_stage_changes(self):
        app.JOBS['progress-test'] = {'percent':88, 'stage':'Validating', 'events':[]}
        try:
            app.update_job('progress-test', percent=15, stage='Repairing')
            self.assertEqual(app.JOBS['progress-test']['percent'], 88)
            self.assertEqual(app.JOBS['progress-test']['events'][-1]['stage'], 'Repairing')
            app.update_job('progress-test', percent=100, stage='Ready')
            self.assertEqual(app.JOBS['progress-test']['percent'],100)
        finally:
            del app.JOBS['progress-test']


if __name__ == '__main__':
    unittest.main()
