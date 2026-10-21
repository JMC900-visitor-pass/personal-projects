"""Conversation and integration contracts in unrelated, temporary codebases."""
import copy
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from design_agent.cli import main, parser
from design_agent.integration import (IntegrationAgent, check_reply, interview_questions,
                                      launch, show_report)
from design_agent.project import orient, test_commands as discover_tests
from design_agent.workspace import Workspace, run_task


def call(tool, **arguments):
    return {'tool': tool, 'arguments': arguments}


def proposal(questions=True):
    return {'intent': 'change', 'message': 'Add a greeting to this Python utility.',
            'questions': [{'question': 'What greeting?', 'default': 'Hello'},
                          {'question': 'Include punctuation?', 'default': 'yes'}] if questions else [],
            'options': [{'id': key, 'title': title, 'detail': detail} for key, title, detail in
                        [('A', 'A function', 'Add greet to app.py with a unit test.'),
                         ('B', 'A command', 'Add a command-line greeting in app.py.'),
                         ('C', 'Both', 'Provide a function and a command-line entry point.')]],
            'recommended': 'A'}


def reply(value):
    return (call('respond'), value)


class Writer:
    model = 'fixture:local'

    def __init__(self, *responses):
        self.responses = [item for response in responses for item in (response if isinstance(response, tuple) else [response])]
        self.requests, self.schemas = [], []

    def ask(self, system, prompt, schema, seed, **kwargs):
        self.requests.append(copy.deepcopy(prompt))
        self.schemas.append(copy.deepcopy(schema))
        if not self.responses:
            raise AssertionError('Unexpected model call')
        if schema.get('required') == ['tool']:
            return {'tool': self.responses[0]['tool']}
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return copy.deepcopy(value)


class Integration(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'README.md').write_text('# Greetings\nA small Python utility. Run python3 app.py.\n')
        (self.root / 'app.py').write_text('VALUE = 1\n')

    def inputs(self, *values):
        iterator = iter(values)
        return lambda prompt: next(iterator)

    def test_no_command_launches_and_old_commands_still_parse(self):
        with patch('design_agent.cli.launch', return_value=0) as start:
            self.assertEqual(main([]), 0)
        start.assert_called_once_with(root=None)
        self.assertTrue(parser().parse_args(['chat']).write)
        self.assertFalse(parser().parse_args(['chat', '--read-only']).write)
        self.assertFalse(parser().parse_args(['work', 'inspect']).write)
        for args in (['scan'], ['read', 'app.py'], ['validate'], ['test'], ['models'], ['build', 'idea']):
            self.assertEqual(parser().parse_args(args).command, args[0])

    def test_interview_accepts_partial_answers_defaults_and_free_text(self):
        questions = proposal()['questions']
        value = interview_questions(questions, self.inputs('n', '2=no'), lambda text: None)
        self.assertEqual([a['answer'] for a in value['answers']], ['Hello', 'no'])
        self.assertEqual([a['used_default'] for a in value['answers']], [True, False])
        skipped = interview_questions(questions, self.inputs(''), lambda text: None)
        self.assertTrue(all(a['used_default'] for a in skipped['answers']))
        value = interview_questions(questions, self.inputs('n', 'Make it friendly'), lambda text: None)
        self.assertEqual(value['notes'], 'Make it friendly')

    def test_bad_question_number_is_not_silently_ignored(self):
        value = interview_questions(proposal()['questions'], self.inputs('n', '8=yes', '1=Hi'), lambda text: None)
        self.assertEqual(value['answers'][0]['answer'], 'Hi')

    def test_exactly_three_distinct_options_required(self):
        for options in (proposal()['options'][:2], [proposal()['options'][0]] * 3):
            with self.assertRaises(ValueError):
                check_reply(dict(proposal(), options=options))

    def test_discovery_cannot_write_and_retries_invalid_options(self):
        invalid = dict(proposal(), options=[])
        writer = Writer(call('write', path='bad.py', text='bad', expected_sha256='new'),
                        call('respond'), invalid, proposal())
        agent = IntegrationAgent(self.root, writer, progress=lambda text: None)
        self.assertEqual(agent.prepare('Add greetings')['intent'], 'change')
        self.assertFalse((self.root / 'bad.py').exists())
        self.assertFalse(writer.requests[1]['history'][0]['result']['ok'])
        self.assertIn('exactly three', writer.requests[3]['repair']['error'])

    def test_launch_selects_once_orients_interviews_combines_edits_tests_and_remembers(self):
        source = 'def greet(name):\n    return f"Hi {name}!"\n'
        test = 'import unittest\nfrom app import greet\nclass Greeting(unittest.TestCase):\n    def test_greeting(self):\n        self.assertEqual(greet("Sam"), "Hi Sam!")\n'
        answer = {'intent': 'answer', 'message': 'The greeting is in app.py; its test passed.',
                  'questions': [], 'options': [], 'recommended': ''}
        writer = Writer({'summary': 'A Python greeting utility with app.py.'}, reply(proposal()),
                        reply(proposal(False)), call('read', path='app.py'),
                        call('write', path='app.py', text=source,
                             expected_sha256=hashlib.sha256(b'VALUE = 1\n').hexdigest()),
                        call('write', path='tests/test_app.py', text=test, expected_sha256='new'),
                        call('finish', message='Added the greeting and a matching test.'), reply(answer))
        events, output = [], []

        def model_status():
            events.append('models')
            return {'available': True, 'models': ['fixture:local']}

        values = iter(['', 'Add greetings', 'n', '1=Hi', 'A for the function, B for the interface',
                       'Where did you add it?', '/exit'])

        def input_fn(prompt):
            events.append(prompt)
            return next(values)

        with patch('design_agent.integration.models', side_effect=model_status) as model_list, \
             patch('design_agent.integration.OllamaWriter', return_value=writer) as factory:
            code = launch(self.root, input_fn=input_fn, output=output.append)
        self.assertEqual(code, 0)
        model_list.assert_called_once()
        factory.assert_called_once()
        self.assertEqual(events[0], 'models')
        self.assertEqual((self.root / 'app.py').read_text(), source)
        self.assertIn('tests/test_app.py', '\n'.join(output))
        self.assertIn('Tests: passed.', output)
        integration = next(request['integration'] for request in writer.requests if 'integration' in request)
        self.assertEqual(integration['interview']['answers'][0]['answer'], 'Hi')
        self.assertIn('A for the function', integration['selected_option_or_combination'])
        self.assertEqual(writer.requests[-1]['previous_conversation'][-1]['status'], 'complete')
        self.assertTrue(all('codebase' in request for request in writer.requests))
        records = list((self.root / 'runtime/agent-runs').glob('*/result.json'))
        report = json.loads(records[0].read_text())
        self.assertTrue(report['verification']['tests']['ok'])
        self.assertFalse(report['verification']['tests']['skipped'])
        self.assertEqual(Path(report['session'], '001.before').read_text(), 'VALUE = 1\n')

    def test_cancel_and_eof_never_apply_the_proposal(self):
        for end in ('cancel', 'no thanks', 'do not edit anything', 'eof'):
            writer = Writer({'summary': 'A Python utility.'}, reply(proposal(False)))
            values = iter(['Add greetings', end, '/exit'] if end != 'eof' else ['Add greetings'])

            def input_fn(prompt):
                try:
                    return next(values)
                except StopIteration:
                    raise EOFError from None

            with patch('design_agent.integration.OllamaWriter', return_value=writer):
                self.assertEqual(launch(self.root, model=writer.model, input_fn=input_fn, output=lambda text: None), 0)
            self.assertEqual((self.root / 'app.py').read_text(), 'VALUE = 1\n')

    def test_context_refreshes_after_an_external_edit(self):
        answer = {'intent': 'answer', 'message': 'Read the current value.', 'questions': [], 'options': [], 'recommended': ''}
        writer = Writer(reply(answer), reply(answer))
        agent = IntegrationAgent(self.root, writer, progress=lambda text: None)
        first = agent.prepare('What is the value?')
        agent.remember('What is the value?', first)
        (self.root / 'app.py').write_text('VALUE = 9\n')
        agent.prepare('And now?')
        files = writer.requests[-1]['codebase']['excerpts']
        self.assertIn('VALUE = 9', next(f['text'] for f in files if f['path'] == 'app.py'))
        self.assertEqual(writer.requests[-1]['previous_conversation'][0]['user'], 'What is the value?')

    def test_failed_check_returns_to_model_for_a_real_repair(self):
        bad, good = 'def broken(:\n', 'VALUE = 2\n'
        writer = Writer(call('write', path='new.py', text=bad, expected_sha256='new'),
                        call('finish', message='Done.'), call('read', path='new.py'),
                        call('write', path='new.py', text=good, expected_sha256=hashlib.sha256(bad.encode()).hexdigest()),
                        call('finish', message='Repaired the syntax.'))
        workspace = Workspace(self.root, allow_write=True)
        report = run_task(workspace, writer, 'Add a module', repair_attempts=1)
        self.assertEqual(report['status'], 'complete')
        self.assertFalse(writer.requests[2]['history'][-1]['result']['verification']['validation']['ok'])
        self.assertEqual((self.root / 'new.py').read_text(), good)
        self.assertTrue(report['verification']['tests']['skipped'])

    def test_malformed_edit_uses_required_arguments_on_retry(self):
        original = Workspace(self.root).read('app.py')
        writer = Writer(call('replace', path='app.py', old_text='VALUE = 1', expected_sha256=original['sha256']),
                        call('replace', path='app.py', old_text='VALUE = 1', text='VALUE = 2', expected_sha256=original['sha256']),
                        call('finish', message='Updated the value.'))
        report = run_task(Workspace(self.root, allow_write=True), writer, 'Set VALUE to 2')
        self.assertEqual(report['status'], 'complete')
        retry = writer.schemas[1]['properties']
        self.assertEqual(retry['tool']['enum'], ['replace'])
        self.assertIn('text', retry['arguments']['required'])
        self.assertNotIn('message', retry['arguments']['properties'])
        self.assertEqual((self.root / 'app.py').read_text(), 'VALUE = 2\n')

    def test_question_at_choice_keeps_discussion_read_only(self):
        answer = {'intent': 'answer', 'message': 'A is the smallest change.',
                  'questions': [], 'options': [], 'recommended': ''}
        writer = Writer({'summary': 'A Python utility.'}, reply(proposal(False)), reply(answer))
        with patch('design_agent.integration.OllamaWriter', return_value=writer):
            code = launch(self.root, model=writer.model,
                          input_fn=self.inputs('Add greetings', 'Why A?', '/exit'), output=lambda text: None)
        self.assertEqual(code, 0)
        self.assertEqual((self.root / 'app.py').read_text(), 'VALUE = 1\n')
        self.assertEqual(writer.requests[-1]['task'], 'Why A?')
        self.assertIn('Not applied', writer.requests[-1]['previous_conversation'][-1]['outcome'])

    def test_unresolved_failures_and_model_errors_never_claim_success(self):
        writer = Writer(call('write', path='bad.py', text='broken syntax !!', expected_sha256='new'),
                        call('finish', message='Done.'), ValueError('Model disconnected'))
        report = run_task(Workspace(self.root, allow_write=True), writer, 'Add a module', repair_attempts=1)
        self.assertEqual(report['status'], 'error')
        self.assertFalse(report['verification']['validation']['ok'])
        output = []
        show_report(report, output.append)
        self.assertIn('Validation: failed.', output)
        self.assertIn('Applied edits remain', '\n'.join(output))

    def test_keyboard_interrupt_keeps_cli_exit_code(self):
        with patch('design_agent.cli.launch', side_effect=KeyboardInterrupt), \
             patch('sys.stderr', new=io.StringIO()):
            self.assertEqual(main([]), 130)


class GeneralProjects(unittest.TestCase):
    def test_unrelated_web_project_scans_typescript_and_uses_its_test_script(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'package.json').write_text('{"scripts":{"test":"node --test"}}')
            (root / 'index.ts').write_text('export const count: number = 1;\n')
            (root / 'Dockerfile').write_text('FROM scratch\n')
            workspace = Workspace(root, allow_write=True)
            self.assertIn('index.ts', orient(workspace)['files'])
            self.assertEqual(discover_tests(workspace), [['npm', 'run', 'test']])
            self.assertTrue(workspace.validate()['ok'])
            original = workspace.read('index.ts')
            workspace.write('index.ts', 'export const count: number = 2;\n', original['sha256'])
            self.assertIn('2', (root / 'index.ts').read_text())

    def test_no_tests_is_reported_as_skipped_and_bad_json_fails_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'README.md').write_text('# Notes\n')
            workspace = Workspace(root)
            self.assertTrue(workspace.test()['skipped'])
            self.assertTrue(workspace.validate()['skipped'])
            (root / 'settings.json').write_text('{broken')
            self.assertFalse(workspace.validate()['ok'])


if __name__ == '__main__':
    unittest.main()
