import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from monster_studio import Monster_Cli, cli, markdown, roles
from monster_studio.level import (ENEMIES, Rules, base_state, character,
                                  damage_on_hit, hit_probability, matchup)
from monster_studio.studio import Studio


def drafts(prompt):
    base = prompt['design_limits']['baseline_stats']
    cards = []
    for index, (name, identity, attack) in enumerate([
        ('Toll Keeper', 'A patient sentinel that holds the narrow crossing.', 'Bar the Crossing'),
        ('Brass Collector', 'A quick enforcer that drives stragglers back.', 'Collect the Unpaid Toll'),
        ('Bell-Eater', 'A frail ambusher that steals a safe retreat.', 'Snap the Bell Cord'),
    ]):
        stats = dict(base)
        move = None
        if index == 1:
            stats['hp'] -= 2
            stats['atk'] += 1
            stats['spd'] += 1
        if index == 2:
            stats['hp'] -= 2
            stats['magic'] -= 1
            move = {'name': 'Ring the Road Shut', 'cost': 3,
                    'trigger': 'As its action, instead of attacking.',
                    'effect': 'Move one adjacent enemy one square directly away into an empty square.',
                    'limit': 'Once per encounter. Cannot move a target through blocked terrain.'}
        cards.append({'monster_name': name, 'identity': identity, 'flavour': 'A toll is still owed.',
                      'stats': stats, 'attack_name': attack, 'range': index + 1,
                      'move': move, 'tactics': 'Hold a narrow passage and target the closest visible enemy.',
                      'weakness': 'Approach from several directions to split its attention.'})
    return cards


class FakeModel:
    def __init__(self, *responses):
        self.requests, self.options, self.responses = [], [], list(responses)

    def ask(self, system, prompt, schema, seed, **kwargs):
        self.requests.append(copy.deepcopy(prompt))
        self.options.append(kwargs)
        if self.responses:
            response = self.responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response(prompt) if callable(response) else copy.deepcopy(response)
        if 'monsters' in schema['required']:
            return {'monsters': drafts(prompt)}
        return copy.deepcopy(prompt['chosen_card'])


class LevelRules(unittest.TestCase):
    def test_supplied_locked_table(self):
        expected = [
            (8, 1, 3, 0, 1, 4, 3, 0), (10, 2, 3, 1, 2, 4, 3, 1),
            (12, 3, 3, 2, 3, 4, 4, 2), (14, 4, 3, 3, 4, 5, 4, 3),
            (16, 5, 3, 4, 5, 6, 5, 4),
        ]
        for number, row in enumerate(expected, 1):
            with self.subTest(level=number):
                result = character(number)
                self.assertEqual((*result['stats'].values(), result['tn'], result['die'], result['bp']['pool']), row)
                self.assertEqual(result['bp']['spent'], 0)
                self.assertEqual(result['learned'], [])
                self.assertEqual(result['actions'], ['Punch', 'Kick', 'Push', 'Interact'])

    def test_all_configuration_combinations_are_valid_at_each_level(self):
        for atk in ('special', 'hit', 'damage'):
            for curve in ('linear', 'early'):
                for ceiling in (5, 8):
                    for number in range(1, 6):
                        row = character(number, Rules(atk, curve, ceiling))
                        self.assertEqual(row['die'], ceiling if number == 5 else (3, 3, 4, 4)[number - 1])
                        expected_bp = (0, 1, 2, 3, 4) if curve == 'linear' else (0, 2, 3, 4, 5)
                        self.assertEqual(row['bp']['pool'], expected_bp[number - 1])

    def test_bp_accounts_for_stats_and_learned_costs_together(self):
        row = character(5, boosts={'atk': 1, 'spd': 1}, learned=[('Flame', 2)])
        self.assertEqual(row['stats']['atk'], 6)
        self.assertEqual(row['stats']['spd'], 4)
        self.assertEqual(row['bp'], {'pool': 4, 'spent': 4, 'remaining': 0})
        with self.assertRaisesRegex(ValueError, 'spends 5 BP'):
            character(5, boosts={'atk': 1, 'spd': 1}, learned=[('Flame', 3)])
        for cost in (1, 5, True, 2.5):
            with self.assertRaises(ValueError):
                character(5, learned=[('Flame', cost)])

    def test_caps_and_invariants_are_enforced_after_spending(self):
        self.assertEqual(character(3, boosts={'hp': 2})['stats']['hp'], 14)
        self.assertEqual(character(5, boosts={'atk': 2})['stats']['atk'], 7)
        self.assertEqual(character(5, boosts={'hp': 2})['stats']['hp'], 18)
        for boosts, message in [({'hp': 1}, 'even'), ({'hp': 4}, 'cap'),
                                ({'spd': 3}, 'cap'), ({'tn': 1}, 'between 4 and 6'),
                                ({'die': 1}, 'D3 and D5'), ({'atk': 3}, 'cap'),
                                ({'magic': -1}, 'integer'), ({'atk': True}, 'integer'),
                                ({'luck': 1}, 'Unknown stat')]:
            with self.subTest(boosts=boosts), self.assertRaisesRegex(ValueError, message):
                character(5, boosts=boosts)
        with self.assertRaisesRegex(ValueError, 'D3 and D8'):
            character(5, Rules(level5_die=8), boosts={'die': 1})

    def test_invalid_levels_and_rules_fail(self):
        for level in (0, 6, -1, True, 2.5, '3'):
            with self.subTest(level=level), self.assertRaises(ValueError):
                base_state(level)
        for kwargs in ({'atk_role': 'both'}, {'bp_curve': 'exponential'}, {'level5_die': 6}):
            with self.assertRaises(ValueError):
                Rules(**kwargs)


class CombatMath(unittest.TestCase):
    def test_formula_matches_exhaustive_dice_outcomes(self):
        for tn in range(1, 13):
            for bonus in range(-5, 10):
                expected = sum(face + bonus >= tn for face in range(1, 7)) / 6
                self.assertEqual(hit_probability(tn, bonus), expected)
        for die in range(1, 9):
            for defence in range(13):
                for bonus in range(-3, 9):
                    expected = sum(max(0, face + bonus - defence) for face in range(1, die + 1)) / die
                    self.assertAlmostEqual(damage_on_hit(die, defence, bonus), expected)

    def test_reference_enemy_estimates_and_vampire_correction(self):
        for level, enemy, damage, turns in ((1, 'zombie', 2 / 3, 9),
                                           (3, 'tinman', 3 / 8, 80 / 3),
                                           (5, 'vampire', 1 / 30, 480)):
            row = matchup(character(level), ENEMIES[enemy])
            self.assertTrue(row['killable'])
            self.assertAlmostEqual(row['damage_per_turn'], damage)
            self.assertAlmostEqual(row['estimated_turns'], turns)

    def test_atk_moves_to_hit_or_damage_without_double_counting(self):
        hit = matchup(character(5, Rules(atk_role='hit')), ENEMIES['vampire'])
        self.assertEqual(hit['hit_probability'], 1)
        self.assertAlmostEqual(hit['damage_per_turn'], 0.2)
        self.assertEqual(hit['damage_bonus'], 0)
        damage = matchup(character(5, Rules(atk_role='damage')), ENEMIES['vampire'])
        self.assertEqual(damage['hit_probability'], 1 / 6)
        self.assertEqual(damage['hit_bonus'], 0)
        self.assertAlmostEqual(damage['estimated_turns'], 24)
        d8 = matchup(character(5, Rules('damage', 'linear', 8)), ENEMIES['vampire'])
        self.assertAlmostEqual(d8['damage_per_turn'], 11 / 12)
        self.assertAlmostEqual(d8['estimated_turns'], 192 / 11)

    def test_universal_dice_and_adjacent_kick_cover(self):
        hero = character(5, Rules(level5_die=8))
        for action in ('punch', 'kick'):
            row = matchup(hero, ENEMIES['vampire'], action=action)
            self.assertEqual(row['die'], 3)
            self.assertFalse(row['killable'])
        plain = matchup(hero, ENEMIES['tinman'], action='kick')
        covered = matchup(hero, ENEMIES['tinman'], action='kick', adjacent=True)
        self.assertTrue(plain['killable'])
        self.assertFalse(covered['killable'])
        self.assertEqual(covered['effective_def'], 3)
        for action in ('base', 'punch', 'push', 'interact'):
            with self.assertRaises(ValueError):
                matchup(hero, ENEMIES['tinman'], action=action, adjacent=True)


class CreativeDesign(unittest.TestCase):
    def setUp(self):
        self.model = FakeModel()
        self.session = Studio(self.model, 42, progress=lambda _: None)

    def test_level_one_has_real_stat_variation_and_a_funded_move(self):
        cards = self.session.generate_variations('guard', 'a haunted bridge', 'brass')
        self.assertEqual(len({tuple(c['stats'].values()) for c in cards}), 3)
        self.assertEqual({c['level'] for c in cards}, {1})
        self.assertEqual({c['tn'] for c in cards}, {4})
        self.assertEqual(cards[2]['move']['name'], 'Ring the Road Shut')
        self.assertEqual(cards[2]['budget']['remaining'], 0)
        self.assertEqual(cards[2]['stats']['hp'], 6)
        self.assertEqual(character(1)['stats']['hp'], 8)
        self.assertEqual(character(1)['learned'], [])
        for card in cards:
            self.assertLessEqual(card['budget']['stats'] + card['budget']['move'], card['budget']['limit'])

    def test_selected_design_is_developed_with_full_context_then_refined(self):
        self.session = Studio(self.model, 42, level=5, rules=Rules('damage', 'early', 8))
        cards = self.session.generate_variations('boss', 'a haunted bridge', 'brass')
        developed = self.session.develop('boss', 'a haunted bridge', cards[2], 'brass')
        refined = self.session.refine('boss', 'a haunted bridge', developed, 'rename the attack', 'brass')
        self.session.refine('boss', 'a haunted bridge', refined, 'make the trigger clearer', 'brass')
        for request in self.model.requests[1:]:
            self.assertEqual(request['chosen_card']['move'], cards[2]['move'])
            self.assertEqual(request['chosen_card']['stats'], cards[2]['stats'])
            self.assertEqual(request['theme'], 'brass')
        self.assertEqual(self.model.requests[-1]['feedback_history'], ['rename the attack', 'make the trigger clearer'])
        self.assertGreaterEqual(self.model.options[0]['max_tokens'], 4500)
        output = markdown.render_document([refined])
        for text in ('Level 5', 'MAGIC', 'D8 + ATK (5)', 'Ring the Road Shut', 'Trigger:', 'Limit:', 'Counterplay:'):
            self.assertIn(text, output)
        self.assertEqual(output.count('Law of Level'), 1)

    def test_budget_errors_and_duplicates_are_repaired_not_silently_clamped(self):
        def overbudget(prompt):
            cards = drafts(prompt)
            cards[0]['stats']['hp'] = 12
            return {'monsters': cards}
        def duplicate(prompt):
            return {'monsters': [drafts(prompt)[0]] * 3}
        model = FakeModel(overbudget, duplicate)
        cards = Studio(model, 1, progress=lambda _: None).generate_variations('guard', 'a bridge', '')
        self.assertEqual(len(model.requests), 3)
        self.assertIn('Budget exceeded', model.requests[1]['repair']['error'])
        self.assertIn('different monster names', model.requests[2]['repair']['error'])
        self.assertEqual(cards[0]['stats']['hp'], 8)

    def test_shape_checks_reject_short_rosters_bool_stats_and_missing_move_fields(self):
        template = roles.template('guard')
        prompt = roles.design_prompt(template, 'a bridge')
        card = drafts(prompt)[0]
        for mutation in (lambda c: c['stats'].update(hp=True),
                         lambda c: c.update(range=True),
                         lambda c: c.update(level=99),
                         lambda c: c.update(move={'name': 'Broken'}),
                         lambda c: c['stats'].update(hp=7),
                         lambda c: c.update(attack_name='A' * 73)):
            broken = copy.deepcopy(card)
            mutation(broken)
            with self.assertRaises(ValueError):
                roles.clean_card(broken, 'guard', template)
        model = FakeModel(*[{'monsters': [card]}] * 3)
        with self.assertRaisesRegex(RuntimeError, 'exactly three'):
            Studio(model, 1, progress=lambda _: None).generate_variations('guard', 'a bridge', '')
        self.assertEqual(len(model.requests), 3)

    def test_all_levels_and_rules_keep_fixed_tn_die_and_valid_variation(self):
        for level in range(1, 6):
            for atk in ('special', 'hit', 'damage'):
                for die in (5, 8):
                    rules = Rules(atk, 'linear', die)
                    cards = Studio(FakeModel(), 1, level=level, rules=rules).generate_variations('knight', 'a bridge', '')
                    for card in cards:
                        self.assertEqual(card['tn'], character(level, rules)['tn'])
                        self.assertEqual(card['attack']['damage_die'], f'D{character(level, rules)["die"]}')
                        self.assertEqual(card['attack']['damage_bonus'], card['stats']['atk'] if atk == 'damage' else 0)

    def test_repeated_requests_remember_previous_designs(self):
        self.session.generate_variations('guard', 'a bridge', '')
        with self.assertRaisesRegex(RuntimeError, 'fresh monster names'):
            self.session.generate_variations('guard', 'a bridge', '')
        self.assertEqual(len(self.model.requests[1]['avoid_repeating']), 3)

    def test_refining_second_choice_preserves_other_candidates_and_no_repick(self):
        with patch('builtins.input', side_effect=['2', 'r', 'clearer wording', 'b', '1', '']), redirect_stdout(io.StringIO()):
            result = self.session.session('guard', 'a bridge', '')
        self.assertEqual(result['name'], 'Toll Keeper')
        self.assertEqual(self.model.requests[1]['chosen_card']['monster_name'], 'Brass Collector')
        self.assertEqual(self.model.requests[2]['chosen_card']['monster_name'], 'Brass Collector')
        self.assertEqual(self.model.requests[3]['chosen_card']['monster_name'], 'Toll Keeper')
        self.assertEqual(self.model.requests[3]['feedback_history'], [])

    def test_stream_failures_repair_but_transport_failures_do_not_retry(self):
        from monster_studio.ollama import ModelOutputError
        model = FakeModel(ModelOutputError('truncated'))
        Studio(model, 1, progress=lambda _: None).generate_variations('guard', 'a bridge', '')
        self.assertIn('truncated', model.requests[1]['repair']['error'])
        model = FakeModel(ValueError('Ollama unavailable'))
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            Studio(model, 1, progress=lambda _: None).generate_variations('guard', 'a bridge', '')
        self.assertEqual(len(model.requests), 1)


class CommandLine(unittest.TestCase):
    def run_cli(self, args):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            code = cli.main(args)
        return code, output.getvalue(), errors.getvalue()

    def test_offline_tools_and_bp_validation_still_work(self):
        with patch.object(cli, 'OllamaClient', side_effect=AssertionError('unexpected model call')):
            code, output, _ = self.run_cli(['levels', '--json'])
            self.assertEqual(code, 0)
            self.assertEqual(len(json.loads(output)), 5)
            code, output, _ = self.run_cli(['balance', '--level', '5', '--action', 'punch', '--json'])
            self.assertIsNone(json.loads(output)['matchups'][-1]['estimated_turns'])
            code, output, _ = self.run_cli(['levels', '5', '--spend', 'atk=2', '--learn', 'Flame:2', '--json'])
            self.assertEqual(json.loads(output)[0]['bp']['remaining'], 0)
            self.assertEqual(self.run_cli(['levels', '1', '--spend', 'atk=1'])[0], 1)
            self.assertEqual(self.run_cli(['rules'])[0], 0)

    def test_build_develops_selected_card_and_exports_move(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'roster.md'
            model = FakeModel()
            with patch.object(cli, 'OllamaClient', return_value=model) as factory, patch('builtins.input', side_effect=['3', 'r', 'clearer wording', '']):
                code, _, errors = self.run_cli(['build', 'boss', '--level', '5', '--atk-role', 'damage',
                                               '--level5-die', '8', '--concept', 'a haunted bridge', '--output', str(target)])
            self.assertEqual(code, 0, errors)
            self.assertIn('D8 + ATK (5)', target.read_text())
            self.assertIn('Ring the Road Shut', target.read_text())
            self.assertEqual(len(model.requests), 3)
            self.assertIsNone(factory.call_args.kwargs['think'])

    def test_no_argument_setup_shares_build_flow_and_advanced_flags(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'wizard.md'
            options = f'--atk-role damage --level5-die 8 --no-think --context 8192 --output {target}'
            with patch.object(cli, 'models', return_value={'available': True, 'models': ['fake:local']}), \
                    patch.object(cli, 'OllamaClient', return_value=FakeModel()) as factory, \
                    patch('builtins.input', side_effect=['', 'knight', '5', 'a haunted bridge', options, '3', '']):
                code, _, errors = self.run_cli([])
            self.assertEqual(code, 0, errors)
            self.assertIn('Level 5', target.read_text())
            self.assertEqual(factory.call_args.kwargs['think'], False)
            self.assertEqual(factory.call_args.kwargs['context_window'], 8192)

    def test_eof_and_invalid_model_do_not_overwrite_output(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'roster.md'
            target.write_text('original')
            with patch.object(cli, 'OllamaClient', return_value=FakeModel()), patch('builtins.input', side_effect=EOFError):
                code, _, _ = self.run_cli(['build', 'guard', '--concept', 'a bridge', '--output', str(target)])
            self.assertEqual(code, 130)
            self.assertEqual(target.read_text(), 'original')
            with patch.object(cli, 'OllamaClient', return_value=FakeModel(*[{}] * 3)):
                code, _, _ = self.run_cli(['build', 'guard', '--concept', 'a bridge', '--output', str(target)])
            self.assertEqual(code, 1)
            self.assertEqual(target.read_text(), 'original')

    def test_script_supports_commands_from_another_directory(self):
        script = Path(Monster_Cli.__file__).resolve()
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run([sys.executable, str(script), 'levels', '5', '--json'],
                                    cwd=folder, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)[0]['level'], 5)


class OllamaProtocol(unittest.TestCase):
    def test_thinking_is_automatic_cached_and_gets_its_own_budget(self):
        from monster_studio import ollama
        with patch.object(ollama, 'models', return_value={'available': True, 'models': ['fake:local']}), \
                patch.object(ollama, '_post', return_value={'capabilities': ['thinking']}) as show:
            client = ollama.OllamaClient('fake:local')
            for _ in range(2):
                payload = {'options': {'num_predict': 4500}}
                client._prepare(payload)
                self.assertTrue(payload['think'])
                self.assertEqual(payload['options']['num_predict'], 10500)
            self.assertEqual(show.call_count, 1)
            client = ollama.OllamaClient('fake:local', think=False)
            payload = {'options': {'num_predict': 4500}}
            client._prepare(payload)
            self.assertFalse(payload['think'])
            self.assertEqual(payload['options']['num_predict'], 4500)

    def test_truncated_malformed_and_incomplete_streams_are_repairable(self):
        from monster_studio import ollama
        for chunks in ([{'response': '{}', 'done': True, 'done_reason': 'length'}],
                       [{'response': '{broken', 'done': True}], [{'response': '{}'}],
                       [{'response': '[]', 'done': True}]):
            response = io.BytesIO(b'\n'.join(json.dumps(chunk).encode() for chunk in chunks))
            with patch.object(ollama.OllamaClient, '_prepare'), \
                    patch.object(ollama.urllib.request, 'urlopen', return_value=response):
                with self.assertRaises(ollama.ModelOutputError):
                    ollama.OllamaClient('fake:local').ask('system', {}, {}, 1)


if __name__ == '__main__':
    unittest.main()
