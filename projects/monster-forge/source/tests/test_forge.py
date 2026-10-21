import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import app


def fixture(schema):
    kind = schema['type']
    if kind == 'object':
        return {k: fixture(v) for k, v in schema['properties'].items()}
    if kind == 'array':
        return [fixture(schema['items']) for _ in range(schema['minItems'])]
    if kind == 'integer':
        return max(schema['minimum'], min(12, schema['maximum']))
    return schema.get('enum', ['Test creature'])[0]


class ForgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = patch.object(app, 'DB_PATH', Path(self.tmp.name) / 'test.sqlite3')
        self.db.start()
        app.init_db()
        self.brief = dict(name='Test Antler', description='A forest guardian stag.', type='fey',
                          cr='3', level=5, role='skirmisher', model='test-model')
        self.monster = fixture(app.SCHEMA)

    def tearDown(self):
        self.db.stop()
        self.tmp.cleanup()

    def test_dataset_and_retrieval(self):
        self.assertEqual(len(app.MONSTERS), 762)
        refs = app.retrieve(self.brief)
        self.assertEqual(refs[0]['type'], 'fey')
        self.assertEqual(refs[0]['cr'], '3')
        self.assertTrue(all(r['ac'] and r['hp'] for r in refs))

    def test_input_rejects_invalid_cr_and_nontext(self):
        for key, value in [('cr', '1/3'),
                           ('description', ''), ('description', {}), ('type', 'bad'), ('model', '')]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                app.check_brief({**self.brief, key: value})

    def test_legacy_level_is_discarded(self):
        self.assertNotIn('level', app.check_brief(self.brief))
        without_level = {k: v for k, v in self.brief.items() if k != 'level'}
        self.assertEqual(app.check_brief(self.brief), app.check_brief(without_level))

    def test_schema_rejects_missing_bad_and_extra_fields(self):
        for change in [{'abilities': {'str': 50}}, {'hit_points': True}, {'loot': []}, {'extra': 1}]:
            with self.assertRaises(ValueError):
                app.validate({**self.monster, **change}, app.SCHEMA)

    def test_generated_sheet_uses_reference_context_and_fixed_math(self):
        self.monster['abilities']['dex'] = 17
        self.monster['saving_throw_proficiencies'] = ['dex']
        self.monster['actions'][0]['description'] = 'Hit: 9 (1d6 + 2) piercing damage.'
        with patch.object(app, 'ollama', return_value={'message': {'content': json.dumps(self.monster)}}) as call:
            sheet = app.build_monster(self.brief)
        self.assertEqual(sheet['name'], 'Test Antler')
        self.assertEqual(sheet['xp'], 700)
        self.assertEqual(sheet['proficiency_bonus'], 2)
        self.assertEqual(sheet['ability_modifiers']['dex'], 3)
        self.assertEqual(sheet['saving_throws']['dex'], 5)
        self.assertIn('5 (1d6 + 2)', sheet['actions'][0]['description'])
        self.assertEqual(app.library()[0]['id'], sheet['id'])
        context = json.loads(call.call_args.args[1]['messages'][1]['content'])
        self.assertEqual(len(context['numeric_references']), 4)
        self.assertNotIn('level', sheet)
        self.assertNotIn('level', context['brief'])
        details = context['rules_references']
        self.assertEqual(len(details), 5)
        self.assertEqual({r['dataset'] for r in details}, {app.retrieve_context.__globals__['RULES'], app.retrieve_context.__globals__['FIREBALL']})
        self.assertEqual(details, sheet['detail_references'])
        for ref in details:
            self.assertEqual(len(ref['sha256']), 64)
            self.assertGreater(ref['line'], 0)
            self.assertLessEqual(len(ref['text']), 1800)

    def test_fractional_and_high_cr_proficiency_xp(self):
        with patch.object(app, 'ollama', side_effect=lambda *a, **kw: {'message': {'content': json.dumps(self.monster)}}):
            for cr, xp, pb in [('0',10,2),('1/8',25,2),('1/2',100,2),('5',1800,3),('30',155000,9)]:
                sheet = app.build_monster({**self.brief, 'cr': cr})
                self.assertEqual((sheet['xp'], sheet['proficiency_bonus']), (xp,pb))

    def test_invalid_output_is_repaired_once(self):
        responses = [{'message': {'content': '{}'}}, {'message': {'content': json.dumps(self.monster)}}]
        with patch.object(app, 'ollama', side_effect=responses) as call:
            app.build_monster(self.brief)
            self.assertEqual(call.call_count, 2)

    def test_invalid_output_never_silently_saves(self):
        with patch.object(app, 'ollama', return_value={'message': {'content': 'not JSON'}}), self.assertRaises(RuntimeError):
            app.build_monster(self.brief)
        self.assertEqual(app.library(), [])

    def test_ollama_failure_never_silently_saves(self):
        with patch.object(app, 'ollama', side_effect=RuntimeError('Ollama offline')), self.assertRaises(RuntimeError):
            app.build_monster(self.brief)
        self.assertEqual(app.library(), [])

    def test_damage_averages_handle_negative_and_correct_values(self):
        self.monster['actions'][0]['description'] = 'Hit: 8 (2d6 - 1), then 10 (3d6) damage.'
        corrections = app.correct_damage_averages(self.monster)
        self.assertEqual(len(corrections), 1)
        self.assertIn('6 (2d6 - 1)', self.monster['actions'][0]['description'])


if __name__ == '__main__':
    unittest.main()
