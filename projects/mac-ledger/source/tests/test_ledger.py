import tempfile
import json
import io
from contextlib import redirect_stdout
from pathlib import Path
import unittest
from unittest.mock import patch
import ledger

class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.root = self.base / 'root'
        self.root.mkdir()
    def snapshot(self, name):
        target = self.base / name
        ledger.scan(self.root, target)
        return target
    def test_mutations_and_deleted_subtree(self):
        (self.root / 'edit').write_text('old')
        (self.root / 'gone').mkdir()
        (self.root / 'gone' / 'child').write_text('x')
        before = self.snapshot('before')
        (self.root / 'edit').write_text('new content')
        (self.root / 'new').write_text('new')
        (self.root / 'gone' / 'child').unlink()
        (self.root / 'gone').rmdir()
        after = self.snapshot('after')
        changes = {Path(c['path']).name: c['status'] for c in ledger.diff(before, after)['changes']}
        self.assertEqual(changes, {'edit': 'modified', 'new': 'added', 'gone': 'removed', 'child': 'removed'})
    def test_permission_failure_is_unknown(self):
        (self.root / 'secret').write_text('x')
        before = self.snapshot('before')
        with patch.object(ledger.os, 'scandir', side_effect=PermissionError('blocked')):
            after = self.snapshot('after')
        result = ledger.diff(before, after)
        self.assertEqual(result['changes'][0]['status'], 'unknown')
        self.assertEqual(len(result['coverage_issues']), 1)
        report = ledger.read_md(after / 'coverage.md')
        self.assertEqual(report['status'], 'incomplete')
        self.assertEqual(report['directory_counts']['unreadable'], 1)

    def test_blocked_subtree_does_not_stop_readable_siblings(self):
        for name in ('blocked', 'readable'):
            (self.root / name).mkdir()
            (self.root / name / 'file').write_text('evidence')
        original = ledger.os.scandir
        def inspect(path):
            if Path(path) == self.root / 'blocked':
                raise PermissionError('blocked by fixture')
            return original(path)
        with patch.object(ledger.os, 'scandir', side_effect=inspect):
            output = self.snapshot('after')
        meta, _, entries = ledger.load_snapshot(output)
        self.assertIn(str(self.root / 'readable' / 'file'), entries)
        self.assertEqual(meta['coverage_status'], 'incomplete')
        report = ledger.read_md(output / 'coverage.md')
        self.assertEqual(report['directory_counts'], {'complete': 2, 'partial': 0, 'unreadable': 1})
        self.assertEqual(report['issues'][0]['path'], str(self.root / 'blocked'))
    def test_symlinks_output_exclusion_and_unique_paths(self):
        (self.root / 'a.b').mkdir()
        (self.root / 'a').mkdir()
        (self.root / 'a' / 'b').mkdir()
        (self.root / 'loop').symlink_to(self.root, target_is_directory=True)
        output = self.root / '.audit-index'
        ledger.scan(self.root, output)
        _, directories, entries = ledger.load_snapshot(output)
        self.assertEqual(len(directories), 4)
        self.assertEqual(entries[str(self.root / 'loop')]['kind'], 'symlink')
        self.assertNotIn(str(output), entries)
    def test_unchanged_and_overwrite(self):
        (self.root / 'file').write_text('same')
        before, after = self.snapshot('before'), self.snapshot('after')
        self.assertEqual(ledger.diff(before, after)['changes'], [])
        with self.assertRaises(FileExistsError):
            ledger.scan(self.root, before)
    def test_scope_mismatch(self):
        before = self.snapshot('before')
        other = self.base / 'other'
        other.mkdir()
        ledger.scan(other, self.base / 'after')
        with self.assertRaises(ValueError):
            ledger.diff(before, self.base / 'after')

    def test_plan_edit_and_execute(self):
        keep = self.root / 'keep'
        keep.mkdir()
        (keep / 'deep').mkdir()
        (keep / 'deep' / 'file').write_text('included beyond pre-list')
        skip = self.root / 'skip'
        skip.mkdir()
        (skip / 'secret').write_text('excluded')
        config = self.root / 'scan.json'
        plan = ledger.create_plan(config, self.root, depth=2)
        self.assertFalse((self.root / 'snapshots').exists())
        for entry in plan['entries']:
            if entry['path'] == str(skip):
                entry['enabled'] = False
        config.write_text(json.dumps(plan))
        (self.root / 'new-after-plan').write_text('included')
        args = ledger.read_plan(config)
        ledger.scan(*args)
        _, dirs, entries = ledger.load_snapshot(args[1])
        self.assertIn(str(keep / 'deep' / 'file'), entries)
        self.assertIn(str(self.root / 'new-after-plan'), entries)
        self.assertNotIn(str(skip), dirs)
        self.assertNotIn(str(skip), entries)
        self.assertNotIn(str(config), entries)
        self.assertNotIn(str(self.root / 'snapshots'), entries)
        with self.assertRaises(ValueError):
            ledger.read_plan(config)

    def test_plan_validation_and_relative_paths(self):
        config = self.base / 'scan.json'
        plan = ledger.create_plan(config, self.root)
        with self.assertRaises(FileExistsError):
            ledger.create_plan(config, self.root)
        plan.update(root='root', output='evidence', exclude=['skip'])
        config.write_text(json.dumps(plan))
        root, output, excludes, _ = ledger.read_plan(config)
        self.assertEqual(root, self.root)
        self.assertEqual(output, self.base / 'evidence')
        self.assertIn(self.root / 'skip', excludes)
        plan['entries'] = [{'path': '../outside', 'enabled': False}]
        config.write_text(json.dumps(plan))
        with self.assertRaises(ValueError):
            ledger.read_plan(config)
        plan['entries'] = [{'path': 'skip', 'enabled': 'false'}]
        config.write_text(json.dumps(plan))
        with self.assertRaises(ValueError):
            ledger.read_plan(config)

    def test_preview_edited_scope_access_and_existing_output(self):
        for name in ('blocked', 'skip', 'keep'):
            (self.root / name).mkdir()
        config = self.base / 'plan.json'
        plan = ledger.create_plan(config, self.root)
        for entry in plan['entries']:
            if entry['path'] == str(self.root / 'skip'):
                entry['enabled'] = False
        config.write_text(json.dumps(plan))
        Path(plan['output']).mkdir(parents=True)
        original = ledger.os.scandir
        def inspect(path):
            if Path(path) == self.root / 'skip':
                self.fail('Preview entered an excluded directory')
            if Path(path) == self.root / 'blocked':
                raise PermissionError('blocked')
            return original(path)
        with patch.object(ledger.os, 'scandir', side_effect=inspect):
            report = ledger.preview_plan(config)
        statuses = {Path(d['path']).name: d['status'] for d in report['directories']}
        self.assertEqual(statuses, {'root': 'complete', 'blocked': 'unreadable', 'keep': 'complete'})
        actions = {Path(e['path']).name: e['action'] for e in report['entries']}
        self.assertEqual(actions['skip'], 'excluded')
        self.assertTrue(report['output_exists'])
        self.assertFalse((Path(plan['output']) / 'snapshot.md').exists())

    def test_plan_unreadable_and_exclusion_before_descent(self):
        blocked = self.root / 'blocked'
        blocked.mkdir()
        excluded = self.root / 'excluded'
        excluded.mkdir()
        original = ledger.os.scandir
        def inspect(path):
            if Path(path) == excluded:
                self.fail('Excluded folder was traversed')
            if Path(path) == blocked:
                raise PermissionError('blocked')
            return original(path)
        with patch.object(ledger.os, 'scandir', side_effect=inspect):
            plan = ledger.create_plan(self.base / 'scan.json', self.root, depth=3,
                                      excludes=[str(excluded)])
        self.assertEqual(plan['coverage_issues'][0]['path'], str(blocked))
        self.assertEqual(plan['coverage_issues'][0]['status'], 'unreadable')

    def test_excluding_symlink_does_not_exclude_target(self):
        target = self.root / 'target'
        target.mkdir()
        link = self.root / 'link'
        link.symlink_to(target, target_is_directory=True)
        config = self.base / 'scan.json'
        plan = ledger.create_plan(config, self.root)
        for entry in plan['entries']:
            if entry['path'] == str(link):
                entry['enabled'] = False
        config.write_text(json.dumps(plan))
        args = ledger.read_plan(config)
        ledger.scan(*args)
        _, directories, entries = ledger.load_snapshot(args[1])
        self.assertIn(str(target), directories)
        self.assertNotIn(str(link), entries)

    def test_terminal_menu_destination_first_and_repeat_scan(self):
        database = self.root / 'my records'
        (self.root / 'nested').mkdir()
        (self.root / 'nested' / 'file.txt').write_text('test')
        answers = [str(database), str(self.root), 'n', 'first', 'r', 'n', 'second', 'r', 'q']
        log = io.StringIO()
        with patch('builtins.input', side_effect=answers), redirect_stdout(log):
            ledger.interactive()
        for name in ('first', 'second'):
            output = database / name
            self.assertTrue((output / 'index.md').exists())
            _, _, entries = ledger.load_snapshot(output)
            self.assertIn(str(self.root / 'nested' / 'file.txt'), entries)
            self.assertNotIn(str(database), entries)
            self.assertIn(str(output), log.getvalue())
        self.assertEqual(ledger.diff(database / 'first', database / 'second')['changes'], [])

    def test_terminal_cancel_does_not_create_database(self):
        database = self.base / 'records'
        with patch('builtins.input', side_effect=[str(database), str(self.root), 'q']), redirect_stdout(io.StringIO()):
            ledger.interactive()
        self.assertFalse(database.exists())

    def test_terminal_recovers_from_invalid_database_scope(self):
        database = self.base / 'records'
        answers = [str(self.base), str(self.root), str(database), str(self.root), 'n', '../escape', 'q']
        log = io.StringIO()
        with patch('builtins.input', side_effect=answers), redirect_stdout(log):
            ledger.interactive()
        self.assertIn('source cannot be inside', log.getvalue())
        self.assertIn('single folder name', log.getvalue())
        self.assertFalse(database.exists())

if __name__ == '__main__':
    unittest.main()
