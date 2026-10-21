import copy
import json
import tempfile
import unittest

from raidforge.generator import ROLES, ModelWriter, generate, parse_brief, threat_budget
from raidforge.library import Library
from raidforge.skirmish import (
    ATTACK_TEST,
    BASE_CHARACTER_STATS,
    COMBAT_RULES,
    DICE_PROFILE,
    LEGACY_RULES_VERSION,
    ROOT,
    RULES_VERSION,
    load_packet,
    reachable_squares,
    upgrade_legacy_packet,
    validate_packet,
)


class FakeOllama:
    """Stands in for OllamaWriter; returns canned JSON and records prompts."""
    model = 'fake:1b'

    def __init__(self, *responses):
        self.responses = list(responses)
        self.prompts = []
        self.systems = []

    def ask(self, system, prompt, schema, seed, on_token=None, **_):
        self.prompts.append((prompt, schema))
        self.systems.append(system)
        response = self.responses.pop(0)
        if on_token:
            on_token('thinking', 'Hmm, a bell tower.')
            text = json.dumps(response)
            for start in range(0, len(text), 10):
                on_token('response', text[start:start + 10])
        return copy.deepcopy(response)


def markers(packet):
    board = packet['scenario']['map']
    found = {}
    for y, row in enumerate(board):
        for x, square in enumerate(row):
            if square not in '#.+':
                found.setdefault(square, []).append((y, x))
    return board, found


class BundledPacket(unittest.TestCase):
    def test_example_is_narrow_and_uses_exact_zombie(self):
        packet = load_packet()
        self.assertFalse({'items', 'loot', 'shops', 'weapons', 'armour'} & packet.keys())
        self.assertEqual(packet['rules_version'], RULES_VERSION)
        self.assertEqual(packet['base_character']['level'], 1)
        self.assertEqual(packet['base_character']['stats'], BASE_CHARACTER_STATS)
        self.assertEqual(packet['base_character']['tn'], 4)
        self.assertEqual(packet['base_character']['attack']['test'], '1D6 + ATK ≥ target TN')
        self.assertEqual(packet['dice'], DICE_PROFILE)
        self.assertEqual(packet['combat_rules'], COMBAT_RULES)
        self.assertTrue(all(monster['attack']['test'] == ATTACK_TEST for monster in packet['monsters']))
        self.assertEqual(packet['level_up']['build_points_gained'], 1)
        zombie = next(monster for monster in packet['monsters'] if monster['name'] == 'Zombie')
        self.assertEqual(zombie['stats'], {'hp': 4, 'atk': 1, 'spd': 2, 'def': 0})
        self.assertEqual(zombie['tn'], 4)
        self.assertEqual(zombie['attack']['damage_die'], 'D3')

    def test_rejects_old_dice_profile_and_stat_line(self):
        broken = copy.deepcopy(load_packet())
        broken['dice']['test_die'] = 'D8'
        with self.assertRaisesRegex(ValueError, 'dice profile'):
            validate_packet(broken)
        broken = copy.deepcopy(load_packet())
        broken['base_character']['stats']['magic'] = 2
        with self.assertRaisesRegex(ValueError, 'universal one-page stat profile'):
            validate_packet(broken)

    def test_legacy_packet_is_translated_to_current_rules(self):
        legacy = copy.deepcopy(load_packet())
        legacy['rules_version'] = LEGACY_RULES_VERSION
        legacy['base_character']['stats'] = {'health': 8, 'move': 4, 'skill': 2, 'defence': 0}
        legacy['base_character']['attack'] = {'name': 'Basic strike', 'attack_dice': 2, 'damage': 1, 'range': 1}
        legacy['monsters'][0]['level'] = 1
        legacy['monsters'][0]['stats'] = {'health': 4, 'move': 2, 'skill': 1, 'defence': 0}
        legacy['monsters'][0]['attack'] = {'name': 'Old grave grasp', 'attack_dice': 1, 'damage': 2, 'range': 1}
        current = upgrade_legacy_packet(legacy)
        self.assertEqual(current['rules_version'], RULES_VERSION)
        self.assertEqual(current['base_character']['stats'], BASE_CHARACTER_STATS)
        self.assertEqual(current['monsters'][0]['attack']['name'], 'Old grave grasp')
        self.assertNotIn('level', current['monsters'][0])
        validate_packet(current)

    def test_rejects_contradictory_combat_rules(self):
        for stat, rule in [('atk', 'Add ATK to damage.'), ('def', 'Add DEF to Target TN.')]:
            with self.subTest(stat=stat):
                broken = load_packet()
                broken['combat_rules'][stat] = rule
                with self.assertRaisesRegex(ValueError, 'ATK, DEF, TN, and damage'):
                    validate_packet(broken)

    def test_rejects_attacks_using_own_tn_or_extra_damage_bonuses(self):
        for change in ({'test': '1D6 + ATK ≥ TN 6'}, {'damage_bonus': 'ATK'}, {'damage_die': 'D12 + ATK'}):
            with self.subTest(change=change):
                broken = load_packet()
                vampire = next(monster for monster in broken['monsters'] if monster['name'] == 'Vampire')
                vampire['attack'].update(change)
                with self.assertRaisesRegex(ValueError, 'attack must use its role template'):
                    validate_packet(broken)
        broken = load_packet()
        broken['base_character']['attack']['damage_bonus'] = 'ATK'
        with self.assertRaisesRegex(ValueError, 'Punch action'):
            validate_packet(broken)

    def test_core_upgrade_does_not_hide_conflicting_rules(self):
        broken = load_packet()
        broken['combat_rules']['def'] = 'Roll defence against the attack.'
        with self.assertRaisesRegex(ValueError, 'ATK, DEF, TN, and damage'):
            validate_packet(upgrade_legacy_packet(broken))
        broken = load_packet()
        broken['monsters'][0]['attack']['test'] = '1D6 + ATK ≥ own TN'
        with self.assertRaisesRegex(ValueError, 'attack must use its role template'):
            validate_packet(upgrade_legacy_packet(broken))

    def test_rejects_unknown_marker_and_wrong_count(self):
        packet = load_packet()
        broken = copy.deepcopy(packet)
        broken['scenario']['map'][1] = broken['scenario']['map'][1].replace('....#', '..Q.#', 1)
        with self.assertRaisesRegex(ValueError, 'without a monster card'):
            validate_packet(broken)
        broken = copy.deepcopy(packet)
        broken['monsters'][0]['count'] = 2
        with self.assertRaisesRegex(ValueError, 'exactly 2'):
            validate_packet(broken)

    def test_rejects_unreachable_objective_and_deferred_items(self):
        broken = copy.deepcopy(load_packet())
        broken['scenario']['map'][6] = broken['scenario']['map'][6].replace('+', '#')
        with self.assertRaisesRegex(ValueError, 'reachable'):
            validate_packet(broken)
        with self.assertRaisesRegex(ValueError, 'deferred'):
            validate_packet({**load_packet(), 'loot': []})

    def test_no_legacy_code_is_imported(self):
        sources = ' '.join(path.read_text() for path in (ROOT / 'raidforge').glob('*.py')
                           if path.name in {'skirmish.py', 'generator.py', 'library.py', 'llm.py', 'server.py'})
        for legacy in ('.store', '.game', '.service', '.export', '.agents', '/legacy'):
            self.assertNotIn(legacy, sources)


class OfflineAgent(unittest.TestCase):
    def test_generated_maps_are_valid_across_many_seeds(self):
        for seed in range(60):
            packet = generate({'concept': 'Zombies, chaos spawn and a vampire in a crypt', 'seed': seed,
                               'party_size': 1 + seed % 6, 'difficulty': ['easy', 'standard', 'hard'][seed % 3]})
            board, found = markers(packet)
            reach = reachable_squares(board, found['E'][0])
            self.assertTrue(all(square in reach for squares in found.values() for square in squares))
            self.assertLessEqual(packet['generation']['threat_total'], max(packet['generation']['threat_budget'], 9))

    def test_same_seed_repeats_map_and_roster(self):
        brief = {'concept': 'Goblins in a mill', 'seed': 42}
        first, second = generate(brief), generate(brief)
        self.assertEqual(first['scenario']['map'], second['scenario']['map'])
        self.assertEqual(first['monsters'], second['monsters'])

    def test_user_names_and_quantities_are_exact(self):
        packet = generate({'concept': 'A barrow', 'seed': 3, 'monsters': [
            {'name': 'Zombie', 'count': 3}, {'name': 'the Bell-Ringer', 'role': 'boss'}, {'name': 'Mudling'}]})
        by_name = {m['name']: m for m in packet['monsters']}
        self.assertEqual(set(by_name), {'Zombie', 'the Bell-Ringer', 'Mudling'})
        self.assertEqual(by_name['Zombie']['count'], 3)
        self.assertEqual(by_name['the Bell-Ringer']['role'], 'Boss')
        self.assertEqual(by_name['the Bell-Ringer']['count'], 1)
        _, found = markers(packet)
        for monster in packet['monsters']:
            self.assertEqual(len(found[monster['symbol']]), monster['count'])

    def test_monster_numbers_come_from_role_templates(self):
        packet = generate({'concept': 'x', 'seed': 1, 'monsters': [{'name': 'Troll', 'count': 1}]})
        troll = packet['monsters'][0]
        self.assertEqual(troll['stats'], ROLES['brute']['stats'])
        self.assertEqual(troll['behaviour'], ROLES['brute']['behaviour'])

    def test_all_roles_use_target_tn_and_separate_damage(self):
        packet = generate({'concept': 'A mixed warband', 'seed': 10, 'monsters': [
            {'name': f'Test {role}', 'role': role, 'count': 1} for role in ROLES]})
        self.assertEqual(packet['combat_rules'], COMBAT_RULES)
        for monster in packet['monsters']:
            with self.subTest(role=monster['role']):
                self.assertEqual(monster['attack']['test'], '1D6 + ATK ≥ target TN')
                self.assertIn(monster['attack']['damage_die'], ('D3', 'D12'))
                self.assertNotIn('damage_bonus', monster['attack'])

    def test_named_one_page_monsters_keep_their_printed_cards(self):
        packet = generate({'concept': 'x', 'seed': 1, 'monsters': [
            {'name': 'Zombie', 'role': 'minion'}, {'name': 'Chaos Spawn', 'role': 'brute'},
            {'name': 'Vampire', 'role': 'guard'},
        ]})
        cards = {monster['name']: monster for monster in packet['monsters']}
        self.assertEqual((cards['Zombie']['role'], cards['Zombie']['tn']), ('Guard', 4))
        self.assertEqual((cards['Chaos Spawn']['role'], cards['Chaos Spawn']['tn']), ('Hunter', 4))
        self.assertEqual((cards['Vampire']['role'], cards['Vampire']['attack']['damage_die']), ('Boss', 'D12'))

    def test_larger_party_and_difficulty_raise_budget_not_base_stats(self):
        easy = generate({'concept': 'Goblins', 'seed': 2, 'party_size': 1, 'difficulty': 'easy'})
        hard = generate({'concept': 'Goblins', 'seed': 2, 'party_size': 4, 'difficulty': 'hard'})
        self.assertGreater(sum(m['count'] for m in hard['monsters']), sum(m['count'] for m in easy['monsters']))
        self.assertEqual(easy['base_character'], hard['base_character'])
        self.assertLess(threat_budget(1, 'easy'), threat_budget(4, 'hard'))

    def test_brief_validation(self):
        for bad in ({}, {'concept': 'x', 'party_size': 9}, {'concept': 'x', 'difficulty': 'brutal'},
                    {'concept': 'x', 'monsters': [{'name': 'A'}, {'name': 'a'}]},
                    {'concept': 'x', 'monsters': [{'name': 'A', 'role': 'dragon'}]},
                    {'concept': 'x', 'monsters': [{'name': 'A', 'count': 99}]}):
            with self.assertRaises(ValueError):
                parse_brief(bad)


class ModelAgent(unittest.TestCase):
    def test_model_writes_flavour_but_cannot_rename_or_set_numbers(self):
        fake = FakeOllama({'name': 'The Drowned Bell', 'story': 'The tide has turned red. Go now.',
                           'objective_goal': 'Silence the drowned bell.',
                           'monsters': {'zombie': {'brief': 'Wet and hungry.', 'attack_name': 'Brine grip',
                                                   'stats': {'atk': 99, 'def': 99}, 'tn': 99,
                                                   'attack': {'test': '1D6 + ATK ≥ own TN', 'damage_bonus': 'ATK'}},
                                        'mudling': {'brief': 'Silt given spite.', 'attack_name': 'Muck lash', 'role': 'minion'}}})
        packet = generate({'concept': 'A flooded bell tower', 'seed': 4, 'backend': 'ollama',
                           'monsters': [{'name': 'Zombie'}, {'name': 'Mudling'}]}, writer=ModelWriter('fake', fake))
        self.assertEqual([m['name'] for m in packet['monsters']], ['Zombie', 'Mudling'])
        self.assertEqual(packet['scenario']['name'], 'The Drowned Bell')
        self.assertTrue(packet['scenario']['objective'].startswith('Silence the drowned bell:'))
        self.assertEqual(packet['monsters'][1]['stats'], ROLES['minion']['stats'])
        self.assertEqual(packet['generation']['backend'], 'ollama')
        self.assertEqual(packet['monsters'][0]['stats'], ROLES['guard']['stats'])
        self.assertEqual(packet['monsters'][0]['tn'], 4)
        self.assertEqual(packet['monsters'][0]['attack'], {'name': 'Brine grip', **ROLES['guard']['attack']})
        prompt, schema = fake.prompts[0]
        self.assertEqual(prompt['combat_rules'], COMBAT_RULES)
        self.assertIn('Kick uses SPD', fake.systems[0])
        self.assertNotIn('role', schema['properties']['monsters']['properties']['zombie']['properties'])

    def test_model_proposes_roster_when_none_given(self):
        fake = FakeOllama({'monsters': [{'name': 'Tide Wraith', 'role': 'hunter'}, {'name': 'Tide Wraith', 'role': 'boss'},
                                        {'name': 'Bell Warden', 'role': 'boss'}]},
                          {'name': 'Low Tide', 'story': 'Story.', 'objective_goal': 'Ring it',
                           'monsters': {'tide_wraith': {'brief': 'b', 'attack_name': 'a'},
                                        'bell_warden': {'brief': 'b', 'attack_name': 'a'}}})
        packet = generate({'concept': 'Lighthouse', 'seed': 8, 'backend': 'ollama'}, writer=ModelWriter('fake', fake))
        self.assertEqual([m['name'] for m in packet['monsters']], ['Tide Wraith', 'Bell Warden'])
        self.assertEqual(len(fake.prompts), 2)
        for prompt, _ in fake.prompts:
            self.assertEqual(prompt['combat_rules'], COMBAT_RULES)

    def test_bad_model_output_is_rejected_not_substituted(self):
        fake = FakeOllama({'name': 'X', 'story': '', 'objective_goal': 'Go', 'monsters': {'zombie': {'brief': 'b', 'attack_name': 'a'}}})
        with self.assertRaisesRegex(ValueError, 'Nothing was saved'):
            generate({'concept': 'x', 'seed': 1, 'backend': 'ollama', 'monsters': [{'name': 'Zombie'}]},
                     writer=ModelWriter('fake', fake))

    def test_progress_events_let_a_viewer_watch_the_agent(self):
        events = []
        fake = FakeOllama({'name': 'Low Tide', 'story': 'Story.', 'objective_goal': 'Ring it',
                           'monsters': {'zombie': {'brief': 'b', 'attack_name': 'a'}}})
        generate({'concept': 'x', 'seed': 2, 'backend': 'ollama', 'monsters': [{'name': 'Zombie'}]},
                 writer=ModelWriter('fake', fake), progress=events.append)
        self.assertEqual(events[0]['type'], 'plan')
        steps = [(e['id'], e['status']) for e in events if e['type'] == 'step']
        self.assertEqual(steps, [(s, status) for s in ('roster', 'write', 'budget', 'map', 'validate')
                                 for status in ('running', 'done')])
        tokens = [e for e in events if e['type'] == 'token']
        self.assertEqual({e['channel'] for e in tokens}, {'thinking', 'response'})
        self.assertEqual(json.loads(''.join(e['text'] for e in tokens if e['channel'] == 'response'))['name'], 'Low Tide')
        types = [e['type'] for e in events]
        self.assertLess(types.index('token'), types.index('scenario'))
        self.assertLess(types.index('scenario'), types.index('map'))

    def test_cloud_model_rejected(self):
        with self.assertRaisesRegex(ValueError, 'cloud'):
            generate({'concept': 'x', 'backend': 'ollama', 'model': 'gpt-oss:120b-cloud'})


class SavedLibrary(unittest.TestCase):
    def test_earlier_core_save_gets_combat_explanations_without_rewriting_file(self):
        previous = load_packet()
        previous.pop('combat_rules')
        for monster in previous['monsters']:
            monster['attack'].pop('test')
        original = copy.deepcopy(previous)
        with tempfile.TemporaryDirectory() as folder:
            library = Library(folder)
            path = library.folder / 'earlier_core.json'
            path.write_text(json.dumps(previous), encoding='utf-8')
            before = path.read_bytes()
            current = library.get('earlier_core')
            self.assertEqual(current['combat_rules'], COMBAT_RULES)
            self.assertEqual(current['scenario'], previous['scenario'])
            self.assertEqual(current['base_character'], previous['base_character'])
            for old, new in zip(previous['monsters'], current['monsters']):
                self.assertEqual(new, {**old, 'attack': {**old['attack'], 'test': ATTACK_TEST}})
            self.assertIn('earlier_core', [entry['id'] for entry in library.list()])
            self.assertEqual(path.read_bytes(), before)
        upgrade_legacy_packet(previous)
        self.assertEqual(previous, original)

    def test_save_list_get_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            library = Library(folder)
            saved = library.save(generate({'concept': 'Goblins', 'seed': 5}))
            again = library.save(generate({'concept': 'Goblins', 'seed': 5}))
            self.assertNotEqual(saved['saved_id'], again['saved_id'])
            ids = [entry['id'] for entry in library.list()]
            self.assertEqual(ids[-1], 'example')
            self.assertIn(saved['saved_id'], ids)
            self.assertEqual(library.get(saved['saved_id'])['scenario'], saved['scenario'])
            with self.assertRaises(ValueError):
                library.get('../secrets')


if __name__ == '__main__':
    unittest.main()
