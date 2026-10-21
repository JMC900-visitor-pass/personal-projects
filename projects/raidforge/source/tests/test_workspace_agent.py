"""Workspace edits, error paths, and actual project-check regressions."""
import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from design_agent.core import ROOT
from design_agent.validation import validate_project
from design_agent.workspace import Workspace, run_task
from raidforge.generator import generate
from raidforge.skirmish import (COMPLETION, DEFAULT_MONSTER_BEHAVIOUR, LEGACY_MONSTER_BEHAVIOUR,
                                load_packet, upgrade_legacy_packet)


class Writer:
    model = 'scripted-local'

    def __init__(self, *calls):
        self.calls = list(calls)
        self.requests = []

    def ask(self, system, prompt, schema, seed, **kwargs):
        self.requests.append(copy.deepcopy(prompt))
        value = self.calls.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def action(tool, **arguments):
    return {'tool': tool, 'arguments': arguments}


class WorkspaceTools(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'docs').mkdir()
        (self.root / 'docs/CORE-RULES.md').write_text('# Core\n\n## Rules\nKeep these.\n')
        (self.root / 'docs/SKIRMISH-REDESIGN-TODO.md').write_text('# TODO\n- [ ] Feature\n')
        self.workspace = Workspace(self.root, allow_write=True)

    def test_scan_search_is_literal_and_ignores_hidden_backups_and_symlinks(self):
        for name in ('.secret', 'runtime/backups', 'runtime/agent-runs', '.venv'):
            folder = self.root / name
            folder.mkdir(parents=True)
            (folder / 'private.txt').write_text('Keep these.')
        (self.root / 'linked.md').symlink_to(self.root / 'docs/CORE-RULES.md')
        result = self.workspace.scan('keep these.')
        self.assertEqual([row['path'] for row in result['results']], ['docs/CORE-RULES.md'])
        self.assertFalse(self.workspace.scan('.*')['results'])

    def test_paths_cannot_escape_or_follow_symlinks(self):
        (self.root / 'link').symlink_to(self.root / 'docs', target_is_directory=True)
        for name in ('../outside.md', '/tmp/outside.md', '.git/config', 'runtime/backups/a.md',
                     'link/CORE-RULES.md', 'binary.png'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.workspace.read(name)

    def test_write_is_disabled_by_default_and_core_needs_separate_flag(self):
        with self.assertRaisesRegex(ValueError, '--write'):
            Workspace(self.root).write('new.md', 'hello', 'new')
        before = self.workspace.read('docs/CORE-RULES.md')
        with self.assertRaisesRegex(ValueError, '--allow-rules'):
            self.workspace.write(before['path'], 'replacement', before['sha256'])
        self.assertEqual(self.workspace.read(before['path']), before)

    def test_replace_requires_current_hash_and_preserves_other_text_and_backup(self):
        source = self.workspace.read('docs/SKIRMISH-REDESIGN-TODO.md')
        result = self.workspace.call('replace', {'path': source['path'], 'old_text': '[ ] Feature',
                                                'text': '[x] Feature', 'expected_sha256': source['sha256']})
        self.assertEqual((self.root / source['path']).read_text(), '# TODO\n- [x] Feature\n')
        self.assertEqual((self.workspace.session / result['backup']).read_text(), source['text'])
        self.assertIn('- [ ] Feature', (self.workspace.session / '001.diff').read_text())
        with self.assertRaisesRegex(ValueError, 'File changed'):
            self.workspace.write(source['path'], 'stale edit', source['sha256'])

    def test_replace_rejects_ambiguous_occurrences_and_new_does_not_overwrite(self):
        self.workspace.write('note.md', 'same same', 'new')
        read = self.workspace.read('note.md')
        with self.assertRaisesRegex(ValueError, 'exactly once'):
            self.workspace.write('note.md', 'different', read['sha256'], old_text='same')
        with self.assertRaisesRegex(ValueError, 'File changed'):
            self.workspace.write('note.md', 'different', 'new')

    def test_tools_reject_shell_arguments_and_unknown_fields(self):
        for tool, args in [('shell', {'text': 'echo bad'}), ('test', {'suite': 'python; echo bad'}),
                           ('read', {'path': 'x.md', 'command': 'echo bad'}), ('write', {'path': 'x.md'})]:
            with self.subTest(tool=tool), self.assertRaises(ValueError):
                self.workspace.call(tool, args)

    def test_test_runner_uses_fixed_argv_cwd_and_propagates_failures(self):
        with patch('design_agent.workspace.subprocess.run') as run:
            run.return_value.returncode = 1
            result = self.workspace.test('python')
        self.assertFalse(result['ok'])
        self.assertEqual(run.call_args.args[0][1:], ['-m', 'unittest', 'discover', '-s', 'tests', '-v'])
        self.assertEqual(run.call_args.kwargs['cwd'], self.root.resolve())
        self.assertNotIn('shell', run.call_args.kwargs)

    def test_timeout_and_missing_node_are_explicit_failures(self):
        for error, expected in [(subprocess.TimeoutExpired('node', 1), 124), (FileNotFoundError('node'), 127)]:
            with patch('design_agent.workspace.subprocess.run', side_effect=error):
                result = self.workspace.test('ui')
            self.assertFalse(result['ok'])
            self.assertEqual(result['results'][0]['exit_code'], expected)

    def run_agent(self, writer, **kwargs):
        with patch.object(self.workspace, 'validate', return_value={'ok': True}), \
             patch.object(self.workspace, 'test', return_value={'ok': True}):
            return run_task(self.workspace, writer, 'Progress the task', **kwargs)

    def test_model_can_read_write_and_finish_with_persisted_evidence(self):
        writer = Writer(action('read', path='docs/SKIRMISH-REDESIGN-TODO.md'),
                        action('write', path='docs/proposal.md', text='A proposal.\n', expected_sha256='new'),
                        action('finish', message='Wrote a proposal.'))
        result = self.run_agent(writer)
        self.assertEqual(result['status'], 'complete')
        self.assertTrue(result['verification']['tests']['ok'])
        self.assertEqual((self.root / 'docs/proposal.md').read_text(), 'A proposal.\n')
        self.assertEqual(json.loads((self.workspace.session / 'result.json').read_text())['status'], 'complete')
        self.assertIn('sha256', writer.requests[1]['history'][0]['result'])

    def test_failed_checks_override_model_success(self):
        with patch.object(self.workspace, 'validate', return_value={'ok': False}):
            result = run_task(self.workspace, Writer(action('finish', message='Everything passed!')), 'Review')
        self.assertEqual(result['status'], 'checks_failed')

    def test_model_errors_after_edit_preserve_backups_and_run_checks(self):
        writer = Writer(action('write', path='docs/new.md', text='New', expected_sha256='new'),
                        ValueError('Model unavailable'))
        result = self.run_agent(writer)
        self.assertEqual(result['status'], 'error')
        self.assertEqual(len(result['changes']), 1)
        self.assertIn('tests', result['verification'])

    def test_bad_tool_call_returns_error_and_can_be_repaired(self):
        writer = Writer(action('read', path='../secret.md'), action('finish', message='Cannot read outside project.'))
        self.run_agent(writer)
        self.assertFalse(writer.requests[1]['history'][0]['result']['ok'])

    def test_step_limit_is_not_success_and_context_stops_before_call(self):
        result = self.run_agent(Writer(action('scan')), max_steps=1)
        self.assertEqual(result['status'], 'step_limit')
        writer = Writer()
        result = self.run_agent(writer, context=1)
        self.assertEqual(result['status'], 'error')
        self.assertEqual(writer.requests, [])


class ProjectAlignment(unittest.TestCase):
    def test_current_project_validates(self):
        report = validate_project(ROOT)
        self.assertTrue(report['ok'], report['errors'])

    def test_validation_detects_document_drift_and_malformed_saved_packet(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / 'docs', root / 'docs')
            shutil.copytree(ROOT / 'data', root / 'data')
            # No link checks are expected to pass in this deliberately incomplete fixture.
            path = root / 'docs/ONEPAGE-RULES.md'
            path.write_text(path.read_text().replace('| 8 | 1 | 3 | 0 | 1 | 4 | D3 |', '| 9 | 1 | 3 | 0 | 1 | 4 | D3 |'))
            saved = root / 'runtime/skirmishes'
            saved.mkdir(parents=True)
            (saved / 'broken.json').write_text('{')
            report = validate_project(root)
            self.assertFalse(report['ok'])
            self.assertTrue(any('starting profile' in e['error'] for e in report['errors']))
            self.assertTrue(any('broken.json' in e['check'] for e in report['errors']))

    def test_generated_objective_and_reward_follow_clarifications(self):
        packet = generate({'concept': 'Zombie crypt', 'seed': 4})
        self.assertIn('from O or an adjacent square', packet['scenario']['objective'])
        self.assertIn('voluntarily enter E', packet['scenario']['objective'])
        self.assertEqual(packet['scenario']['completion'], COMPLETION)
        self.assertIn('Down or removed', COMPLETION)
        self.assertIn('standing character', packet['monsters'][0]['behaviour'])

    def test_old_behaviour_summary_upgrades_without_mutation_or_overriding_custom_cards(self):
        old = load_packet()
        old['monsters'][0]['behaviour'] = LEGACY_MONSTER_BEHAVIOUR
        old['monsters'][1]['behaviour'] = 'Explicit authored exception.'
        new = upgrade_legacy_packet(old)
        self.assertEqual(new['monsters'][0]['behaviour'], DEFAULT_MONSTER_BEHAVIOUR)
        self.assertEqual(old['monsters'][0]['behaviour'], LEGACY_MONSTER_BEHAVIOUR)
        self.assertEqual(new['monsters'][1]['behaviour'], 'Explicit authored exception.')


if __name__ == '__main__':
    unittest.main()
