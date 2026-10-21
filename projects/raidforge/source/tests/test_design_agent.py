"""Design workflow tests use scripted model responses, not network access."""
import copy
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from design_agent.cli import main
from design_agent.audit import audit_probabilities
from design_agent.core import DesignAgent, Rules, arithmetic_reference, load_design, save_run
from design_agent.schema import validate_design
from raidforge.llm import OllamaWriter


PLAN = {'goal': 'Test attack choices', 'deliverables': ['Attack playtest'],
        'constraints': ['Preserve the core rules'], 'assumptions': []}
DESIGN = {'title': 'Attack playtest', 'pitch': 'Compare two legal actions.',
          'sections': [{'id': 'attacks', 'title': 'Run the comparison', 'kind': 'playtest',
                        'body': 'Record hits and HP loss separately.', 'rules_refs': ['1. Tests']}],
          'assumptions': [], 'open_questions': []}
CLEAN = {'summary': 'Ready to try at the table.', 'issues': [], 'playtests': ['Record outcomes over several games.']}
ISSUE = {'severity': 'major', 'section_id': 'attacks', 'problem': 'Missing procedure.',
         'fix': 'State how many rounds to play.', 'rules_refs': ['1. Tests']}
FLAGGED = {**CLEAN, 'issues': [ISSUE]}


class FakeWriter:
    model = 'fake:local'

    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests = []

    def ask(self, system, prompt, schema, seed, **options):
        self.requests.append(copy.deepcopy({'system': system, 'prompt': prompt, 'schema': schema, 'seed': seed}))
        if not self.answers:
            raise AssertionError('Unexpected extra model call')
        response = self.answers.pop(0)
        if isinstance(response, Exception):
            raise response
        return copy.deepcopy(response)


class Workflow(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'rules.md'
        self.path.write_text('# Rules\n\n## 1. Tests\nUse D6 + ATK.\n\n## 2. Movement\nMove up to SPD.\n')
        self.rules = Rules.load(self.path)

    def test_every_stage_receives_exact_rules_and_final_review_follows_revision(self):
        revised = copy.deepcopy(DESIGN)
        revised['sections'][0]['body'] = 'Play six rounds and record hits and HP loss separately.'
        writer = FakeWriter(PLAN, DESIGN, FLAGGED, revised, CLEAN)
        result = DesignAgent(writer, self.rules, seed=23).run('Compare attacks')
        self.assertEqual(result['status'], 'ready_for_playtest')
        self.assertEqual(result['design'], revised)
        self.assertEqual([row['stage'] for row in result['trace']], ['plan', 'draft', 'review', 'revise', 'review'])
        for call in writer.requests:
            self.assertEqual(call['prompt']['rules_source'], self.rules.prompt())
        self.assertEqual(writer.requests[-1]['prompt']['design'], revised)
        self.assertEqual([call['seed'] for call in writer.requests], list(range(23, 28)))

    def test_unresolved_major_issue_is_saved_as_needing_revision(self):
        writer = FakeWriter(PLAN, DESIGN, FLAGGED, DESIGN, FLAGGED)
        result = DesignAgent(writer, self.rules, rounds=1).run('Compare attacks')
        self.assertEqual(result['model_calls'], 5)
        self.assertEqual(result['status'], 'needs_revision')
        folder = save_run(result, self.rules, self.root / 'runs')
        self.assertIn('needs revision', (folder / 'review.md').read_text())

    def test_zero_rounds_still_reviews_and_stops_after_three_calls(self):
        writer = FakeWriter(PLAN, DESIGN, FLAGGED)
        result = DesignAgent(writer, self.rules, rounds=0).run('Compare attacks')
        self.assertEqual(result['status'], 'needs_revision')
        self.assertEqual(result['model_calls'], 3)

    def test_dice_reference_counts_success_at_the_threshold(self):
        reference = arithmetic_reference()
        self.assertIn('| 1 | 5/6 (83.3%) | 4/6 (66.7%) |', reference['hit_chances'])
        self.assertIn('| 3 | 6/6 (100.0%) | 6/6 (100.0%) |', reference['hit_chances'])
        self.assertIn('| 3 | 0 | 3.75 |', reference['damage_on_hit'])

    def test_wrong_explicit_probability_cannot_be_approved_by_model(self):
        wrong = copy.deepcopy(DESIGN)
        wrong['sections'][0]['body'] = 'Test: D6 + 1 vs TN 4 (hit chance: 5/6 = 83.3%)'
        writer = FakeWriter(PLAN, wrong, CLEAN)
        result = DesignAgent(writer, self.rules, rounds=0).run('Compare attacks')
        self.assertEqual(result['status'], 'needs_revision')
        self.assertIn('4/6', result['review']['issues'][0]['fix'])
        self.assertTrue(writer.requests[-1]['prompt']['calculated_findings'])

    def test_explicit_probability_checks_handle_rounding_and_avoid_unrelated_numbers(self):
        for body in ('D6 + 1 vs TN 4 = 66.7%', 'D6 + 3 against TN 4 (hit chance: 6/6)',
                     'D6 + 1 vs TN 4. On a hit, deal 2 damage.'):
            design = copy.deepcopy(DESIGN)
            design['sections'][0]['body'] = body
            self.assertEqual(audit_probabilities(design), [])
        design['sections'][0]['body'] = 'D6 + 1 against TN 4 = 50%'
        self.assertEqual(len(audit_probabilities(design)), 1)
        design['sections'][0]['kind'] = 'rule_proposal'
        self.assertEqual(audit_probabilities(design), [])
        design['sections'][0]['kind'] = 'martial_move'
        design['sections'][0]['body'] = 'D6 + 1 against TN 4 = 50%. Reroll special results as printed.'
        self.assertEqual(audit_probabilities(design), [])

    def test_draft_must_match_planned_deliverable_count(self):
        extra = copy.deepcopy(DESIGN)
        extra['sections'].append(dict(extra['sections'][0], id='unrequested'))
        writer = FakeWriter(PLAN, extra, DESIGN, CLEAN)
        DesignAgent(writer, self.rules).run('One playtest')
        self.assertIn('needs 1–1 entries', writer.requests[2]['prompt']['repair']['validation_error'])

    def test_invalid_citation_is_repaired_once(self):
        invalid = copy.deepcopy(DESIGN)
        invalid['sections'][0]['rules_refs'] = ['99. Invented rule']
        writer = FakeWriter(PLAN, invalid, DESIGN, CLEAN)
        result = DesignAgent(writer, self.rules).run('Compare attacks')
        self.assertEqual(result['model_calls'], 4)
        self.assertIn('validation_error', writer.requests[2]['prompt']['repair'])

    def test_repeated_invalid_response_fails_without_unbounded_retries(self):
        writer = FakeWriter({}, {})
        with self.assertRaisesRegex(ValueError, 'after one repair'):
            DesignAgent(writer, self.rules).run('Compare attacks')
        self.assertEqual(len(writer.requests), 2)

    def test_review_must_reference_real_design_section(self):
        invalid = copy.deepcopy(FLAGGED)
        invalid['issues'][0]['section_id'] = 'invented'
        writer = FakeWriter(PLAN, DESIGN, invalid, invalid)
        with self.assertRaisesRegex(ValueError, 'section_id'):
            DesignAgent(writer, self.rules).run('Compare attacks')

    def test_duplicate_and_reserved_ids_rejected(self):
        duplicated = copy.deepcopy(DESIGN)
        duplicated['sections'].append(copy.deepcopy(duplicated['sections'][0]))
        with self.assertRaisesRegex(ValueError, 'unique'):
            validate_design(duplicated, self.rules.headings)
        duplicated['sections'] = [dict(duplicated['sections'][0], id='overall')]
        with self.assertRaisesRegex(ValueError, 'reserved'):
            validate_design(duplicated, self.rules.headings)

    def test_source_snapshot_stays_stable_and_new_runs_read_changed_file(self):
        original = self.path.read_bytes()
        self.path.write_text('# Revised\n\n## 3. Replacement\nDifferent rules.\n')
        changed = Rules.load(self.path)
        self.assertNotEqual(changed.sha256, self.rules.sha256)
        result = DesignAgent(FakeWriter(PLAN, DESIGN, CLEAN), self.rules).run('Compare attacks')
        first = save_run(result, self.rules, self.root / 'runs')
        second = save_run(result, self.rules, self.root / 'runs')
        self.assertNotEqual(first, second)
        self.assertEqual((first / 'rules.md').read_bytes(), original)
        self.assertEqual(hashlib.sha256(original).hexdigest(), json.loads((first / 'manifest.json').read_text())['rules_sha256'])
        self.assertIn('Different rules.', self.path.read_text())
        self.assertEqual(load_design(first), DESIGN)

    def test_failed_save_leaves_no_partial_run(self):
        result = DesignAgent(FakeWriter(PLAN, DESIGN, CLEAN), self.rules).run('Compare attacks')
        original = Path.write_text

        def fail_on_design(path, *args, **kwargs):
            if path.name == 'design.md':
                raise OSError('Disk full')
            return original(path, *args, **kwargs)

        with patch.object(Path, 'write_text', fail_on_design):
            with self.assertRaisesRegex(OSError, 'Disk full'):
                save_run(result, self.rules, self.root / 'runs')
        self.assertEqual(list((self.root / 'runs').iterdir()), [])

    def test_rules_hash_and_snapshot_preserve_crlf_bytes(self):
        original = b'# Rules\r\n\r\n## 1. Tests\r\nUse D6 + ATK.\r\n'
        self.path.write_bytes(original)
        rules = Rules.load(self.path)
        result = DesignAgent(FakeWriter(PLAN, DESIGN, CLEAN), rules).run('Compare attacks')
        folder = save_run(result, rules, self.root / 'runs')
        self.assertEqual((folder / 'rules.md').read_bytes(), original)
        self.assertEqual(rules.sha256, hashlib.sha256(original).hexdigest())

    def test_missing_empty_and_duplicate_heading_rules_fail(self):
        with self.assertRaises(OSError):
            Rules.load(self.root / 'missing.md')
        for text in ('', '# No sections', '## Same\nText\n## Same\nMore'):
            self.path.write_text(text)
            with self.assertRaises(ValueError):
                Rules.load(self.path)

    def test_old_citations_can_be_loaded_for_revision(self):
        old = copy.deepcopy(DESIGN)
        old['sections'][0]['rules_refs'] = ['7. Old heading']
        path = self.root / 'old.json'
        path.write_text(json.dumps(old))
        previous = load_design(path)
        writer = FakeWriter(PLAN, DESIGN, CLEAN)
        DesignAgent(writer, self.rules).run('Compare attacks', previous, 'Update citations')
        self.assertEqual(writer.requests[1]['prompt']['previous_design'], old)
        self.assertEqual(writer.requests[1]['prompt']['user_feedback'], 'Update citations')

    def test_context_overflow_stops_before_model_call(self):
        writer = FakeWriter()
        with self.assertRaisesRegex(ValueError, 'context budget'):
            DesignAgent(writer, self.rules, context_window=1024).run('Compare attacks')
        self.assertEqual(writer.requests, [])

    def test_dry_run_never_calls_model_or_creates_output(self):
        output = self.root / 'dry-output'
        stdout = io.StringIO()
        with patch.object(OllamaWriter, 'ask', side_effect=AssertionError('Network access')), redirect_stdout(stdout):
            code = main(['build', 'Compare attacks', '--rules', str(self.path), '--output', str(output), '--dry-run'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue())['prompt']['rules_source']['markdown'], self.rules.markdown)
        self.assertFalse(output.exists())

    def test_cli_returns_three_with_review_artifact_for_unresolved_issues(self):
        output = self.root / 'runs'
        with patch('design_agent.cli.OllamaWriter', return_value=FakeWriter(PLAN, DESIGN, FLAGGED)):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = main(['build', 'Compare attacks', '--rules', str(self.path), '--output', str(output), '--rounds', '0'])
        self.assertEqual(code, 3)
        self.assertEqual(len(list(output.glob('*/review.md'))), 1)

    def test_model_failure_does_not_save_or_fall_back(self):
        output = self.root / 'runs'
        with patch('design_agent.cli.OllamaWriter', return_value=FakeWriter(ValueError('Model disconnected'))):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                code = main(['build', 'Compare attacks', '--rules', str(self.path), '--output', str(output)])
        self.assertEqual(code, 1)
        self.assertFalse(output.exists())


class ModelTransport(unittest.TestCase):
    def test_cloud_names_are_rejected_without_contacting_server(self):
        for name in ('gpt-oss:120b-cloud', 'glm-5.3:cloud', 'TEST:cloud'):
            with self.subTest(model=name), self.assertRaisesRegex(ValueError, 'cloud'):
                OllamaWriter(name)

    def test_context_option_is_sent_only_when_requested(self):
        for context in (None, 32768):
            with self.subTest(context=context):
                response = io.BytesIO((json.dumps({'response': '{"ok": true}', 'done': True}) + '\n').encode())
                writer = OllamaWriter('fake:local', context_window=context)
                with patch.object(writer, '_prepare'), patch('urllib.request.urlopen', return_value=response) as opened:
                    self.assertEqual(writer.ask('system', {}, {}, 1), {'ok': True})
                options = json.loads(opened.call_args.args[0].data)['options']
                if context is None:
                    self.assertNotIn('num_ctx', options)
                else:
                    self.assertEqual(options['num_ctx'], context)

    def test_unreachable_server_is_not_reported_as_missing_model(self):
        writer = OllamaWriter('fake:local')
        status = {'available': False, 'models': [], 'message': 'Ollama unavailable: permission denied'}
        with patch('raidforge.llm.models', return_value=status):
            with self.assertRaisesRegex(ValueError, 'permission denied'):
                writer.ask('system', {}, {}, 1)


if __name__ == '__main__':
    unittest.main()
