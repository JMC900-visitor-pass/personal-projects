import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import world
import world_growth as growth


def fake_model(path, body, **kwargs):
    task = json.loads(body['messages'][1]['content'])['task']
    fields = body['format']['required']
    result = {key: 'A useful campaign detail.' for key in fields}
    result['name'] = task['kind'].title() + ' ' + task['id'][:8]
    result['body'] = '## People and tensions\nRiver traders protect the old crossing.'
    result['description'] = 'A river settlement under a sleeping giant.'
    packet = {'message': {'content': json.dumps(result)}}
    kwargs['on_chunk'](packet)
    return packet


class GrowthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.patch = patch.object(world, 'DB_PATH', self.root / 'state.sqlite3')
        self.patch.start()
        world.save_settings(dict(name='Rivergate', seed='Sleeping giant', vault=str(self.root), folder=str(self.root)))
        self.original_worker = growth.WORKER
        growth.WORKER = None

    def tearDown(self):
        growth.control('stop')
        if growth.WORKER:
            growth.WORKER.join(3)
        growth.WORKER = self.original_worker
        self.patch.stop()
        self.tmp.cleanup()

    def wait_finished(self):
        growth.WORKER.join(5)
        self.assertFalse(growth.WORKER.is_alive())
        return growth.status()

    def test_continuous_worker_budget_and_resume_no_duplicates(self):
        growth.start({'model': 'mock', 'note_budget': 3, 'delay': 0}, fake_model)
        run = self.wait_finished()
        self.assertEqual(run['status'], 'paused')
        self.assertEqual(run['completed'], 3)
        self.assertEqual(len(list(self.root.glob('*.md'))), 3)
        self.assertFalse(world.scan()['graph']['diagnostics'])
        growth.start({'model': 'mock', 'note_budget': 1, 'delay': 0}, fake_model)
        run = self.wait_finished()
        self.assertEqual(run['completed'], 4)
        self.assertEqual(len(list(self.root.glob('*.md'))), 4)

    def test_pause_during_draft_defers_publication_and_resume_uses_stage(self):
        entered, release = threading.Event(), threading.Event()
        def blocked(*args, **kw):
            entered.set(); release.wait(3)
            return fake_model(*args, **kw)
        growth.start({'model': 'mock', 'note_budget': 1, 'delay': 0}, blocked)
        self.assertTrue(entered.wait(2))
        growth.control('pause'); release.set()
        run = self.wait_finished()
        self.assertEqual(run['task']['phase'], 'staged')
        self.assertEqual(list(self.root.glob('*.md')), [])
        def must_not_call(*args, **kwargs):
            raise AssertionError('Staged note should not be regenerated')
        growth.start({'model': 'mock', 'note_budget': 1, 'delay': 0}, must_not_call)
        self.assertEqual(self.wait_finished()['completed'], 1)

    def test_repeated_failure_pauses_and_retains_checkpoint(self):
        def fail(*args, **kwargs):
            raise RuntimeError('Model offline')
        growth.start({'model': 'mock', 'delay': 0}, fail)
        run = self.wait_finished()
        self.assertEqual(run['status'], 'paused')
        self.assertEqual(run['failures'], 3)
        self.assertIsNotNone(run['task'])
        self.assertFalse(list(self.root.glob('*.md')))

    def test_atomic_publication_recovery_and_changed_canon(self):
        context = world.scan(True)
        run = {'completed': 0, 'model': 'mock'}
        task = growth.generate(growth.task_for(run, context), context, run, fake_model, lambda n: None)
        growth.publish(task, str(self.root))
        growth.publish(task, str(self.root))
        self.assertEqual(len(list(self.root.glob('*.md'))), 1)
        target = self.root / task['filename']
        target.write_text('My edits')
        with self.assertRaisesRegex(ValueError, 'destination was edited'):
            growth.publish(task, str(self.root))
        self.assertEqual(target.read_text(), 'My edits')
        second = growth.generate(growth.task_for({'completed': 1}, world.scan(True)), world.scan(True), run, fake_model, lambda n: None)
        target.write_text('Further edits')
        with self.assertRaisesRegex(ValueError, 'Canon changed'):
            growth.publish(second, str(self.root))
        self.assertFalse((self.root / second['filename']).exists())

    def test_restart_recovers_publication_before_checkpoint_without_duplicate(self):
        context = world.scan(True)
        run = growth.status()
        run.update(completed=0, model='mock', world_id=context['settings']['id'],
            folder=str(self.root), status='running', note_budget=1, time_budget=0, delay=0)
        task = growth.generate(growth.task_for(run, context), context, run, fake_model, lambda n: None)
        growth.publish(task, str(self.root))
        run['task'] = task
        growth.store(run)
        growth.recover()
        self.assertEqual(growth.status()['status'], 'paused')
        def must_not_generate(*args, **kwargs):
            raise AssertionError('Already-published note should be recovered')
        growth.start({'model': 'mock', 'note_budget': 1, 'delay': 0}, must_not_generate)
        self.assertEqual(self.wait_finished()['completed'], 1)
        self.assertEqual(len(list(self.root.glob('*.md'))), 1)

    def test_stop_during_delay_keeps_notes_and_ends_worker(self):
        growth.start({'model': 'mock', 'delay': 60}, fake_model)
        deadline = time.time() + 3
        while growth.status()['completed'] < 1 and time.time() < deadline:
            time.sleep(0.01)
        growth.control('stop')
        run = self.wait_finished()
        self.assertEqual(run['status'], 'stopped')
        self.assertEqual(run['completed'], 1)
        self.assertEqual(len(list(self.root.glob('*.md'))), 1)

    def test_symlink_root_never_receives_generated_note(self):
        context = world.scan(True)
        task = growth.generate(growth.task_for({'completed': 0}, context), context, {'model': 'mock'}, fake_model, lambda n: None)
        link = self.root / 'link'
        link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(OSError):
            growth.publish(task, str(link))
        self.assertFalse(list(self.root.glob('*.md')))


if __name__ == '__main__':
    unittest.main()
