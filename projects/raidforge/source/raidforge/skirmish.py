"""Canonical data and validation for the core skirmish rules.

A skirmish packet contains a brief story, square-grid map, monster cards, the
universal level-1 character, and level-up choices. The numbers and action
format are fixed by ``docs/CORE-RULES.md``; a writer may supply only flavour.
"""
import copy
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RULES_VERSION = 'skirmish-0.4-core'
LEGACY_RULES_VERSION = 'skirmish-0.3-draft'
PRE_CORE_RULES_VERSIONS = {LEGACY_RULES_VERSION, 'skirmish-0.4-onepage'}
PACKET_PATH = ROOT / 'data' / 'skirmish-v0.4.json'
DEFERRED_CONTENT_KEYS = {'items', 'loot', 'shops', 'weapons', 'armour', 'chest'}
SCOPE = {'brief_story', 'map', 'monsters', 'base_character', 'level_up_choices'}
LEVEL_UP_CHOICES = {'max_hp', 'atk', 'spd', 'def', 'magic', 'martial_move', 'spell', 'gear_effect'}
LEVEL_UP_PROFILE = {
    'max_hp': {'track': 'stat', 'name': 'Maximum HP', 'effect': '+2 maximum HP'},
    'atk': {'track': 'stat', 'name': 'ATK', 'effect': '+1 ATK'},
    'spd': {'track': 'stat', 'name': 'SPD', 'effect': '+1 SPD'},
    'def': {'track': 'stat', 'name': 'DEF', 'effect': '+1 DEF'},
    'magic': {'track': 'stat', 'name': 'MAGIC', 'effect': '+1 MAGIC'},
    'martial_move': {'track': 'move', 'name': 'Martial move', 'effect': 'Learn or improve one martial move.'},
    'spell': {'track': 'spell', 'name': 'Spell', 'effect': 'Learn or improve one spell.'},
    'gear_effect': {
        'track': 'gear effect', 'name': 'Gear effect',
        'effect': 'Locked until the equipment rules are complete.', 'available': False,
    },
}
TERRAIN = {'#', '.', '+'}
RESERVED_MARKERS = {'E', 'O'}
MAX_MONSTER_KINDS = 6
MAX_MONSTERS_OF_KIND = 8
MAX_MAP_SIDE = 40
ID_PATTERN = re.compile(r'^[a-z0-9][a-z0-9_]{0,63}$')

BASE_CHARACTER_STATS = {'hp': 8, 'atk': 1, 'spd': 3, 'def': 0, 'magic': 1}
ATTACK_TEST = '1D6 + ATK ≥ target TN'
COMBAT_RULES = {
    'atk': 'Add ATK to the D6 hit roll when an action uses ATK, such as Punch. It does not increase damage.',
    'def': 'Subtract current DEF from each incoming damage roll, to a minimum of 0 damage. No defence roll; DEF does not change TN.',
    'tn': "Meet or beat the target's TN to hit. A monster attacks against the character's TN, normally 4.",
    'damage': "Roll the action's damage die separately, then subtract the target's current DEF. The target loses that much HP (minimum 0 damage).",
}
DICE_PROFILE = {
    'test_die': 'D6',
    'basic_damage_die': 'D3',
    'heavy_damage_die': 'D12',
    'epic_die': 'D20',
    'test_rule': '1D6 + linked stat ≥ TN',
    'minor_success_total': 5,
    'major_success_total': 6,
}
LEGACY_MONSTER_BEHAVIOUR = (
    'Attack a visible character in range. Otherwise move by the shortest legal route toward the nearest visible '
    'character. If nobody is visible, move toward the objective or last seen character.'
)
DEFAULT_MONSTER_BEHAVIOUR = (
    'Use Core Rules section 9. Attack the nearest visible standing character in range, then end without moving. '
    'Otherwise pursue the nearest visible standing character with a reachable attack position; move up to SPD '
    'by a shortest legal route without attacking. Otherwise search toward the remembered square, then O '
    'if that square is unusable. Stop on empty squares; break ties randomly.'
)
LEGACY_BOSS_BEHAVIOUR = 'Protect the objective. Otherwise use the standard monster activation order.'
BOSS_BEHAVIOUR = (
    "Protect the objective: stay in O's chamber; attacks may target outside it. If shoved out, spend the next "
    'activation moving back toward O without attacking. Otherwise use Core Rules section 9, including '
    'standing targets, pursuit, search, and random ties.'
)
COMPLETION = (
    'After a win, everyone who started, including Down or removed characters, gains +1 Level and +1 Build Point. '
    'Level caps at 5; Build Points continue. Award once per victory; a loss grants neither.'
)

# Role templates exist for skirmish generation only. They use the same card
# fields and D6 + ATK tests that the core rules prescribe.
MONSTER_ROLES = {
    'minion': {
        'threat': 1, 'stats': {'hp': 2, 'atk': 1, 'spd': 3, 'def': 0}, 'tn': 3,
        'attack': {'test': ATTACK_TEST, 'damage_die': 'D3', 'range': 1}, 'behaviour': DEFAULT_MONSTER_BEHAVIOUR,
    },
    'guard': {
        'threat': 2, 'stats': {'hp': 4, 'atk': 1, 'spd': 2, 'def': 0}, 'tn': 4,
        'attack': {'test': ATTACK_TEST, 'damage_die': 'D3', 'range': 1}, 'behaviour': DEFAULT_MONSTER_BEHAVIOUR,
    },
    'hunter': {
        'threat': 2, 'stats': {'hp': 5, 'atk': 1, 'spd': 3, 'def': 0}, 'tn': 4,
        'attack': {'test': ATTACK_TEST, 'damage_die': 'D3', 'range': 1}, 'behaviour': DEFAULT_MONSTER_BEHAVIOUR,
    },
    'shooter': {
        'threat': 2, 'stats': {'hp': 3, 'atk': 1, 'spd': 3, 'def': 0}, 'tn': 4,
        'attack': {'test': ATTACK_TEST, 'damage_die': 'D3', 'range': 4}, 'behaviour': DEFAULT_MONSTER_BEHAVIOUR,
    },
    'brute': {
        'threat': 3, 'stats': {'hp': 7, 'atk': 2, 'spd': 2, 'def': 1}, 'tn': 5,
        'attack': {'test': ATTACK_TEST, 'damage_die': 'D12', 'range': 1}, 'behaviour': DEFAULT_MONSTER_BEHAVIOUR,
    },
    'boss': {
        'threat': 5, 'stats': {'hp': 8, 'atk': 2, 'spd': 4, 'def': 1}, 'tn': 6,
        'attack': {'test': ATTACK_TEST, 'damage_die': 'D12', 'range': 1},
        'behaviour': BOSS_BEHAVIOUR,
    },
}
NAMED_MONSTER_ROLES = {'zombie': 'guard', 'chaos spawn': 'hunter', 'vampire': 'boss'}


def _positive_int(value, label, zero=False, maximum=None):
    minimum = 0 if zero else 1
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        kind = 'non-negative' if zero else 'positive'
        raise ValueError(f'{label} must be a {kind} integer')
    if maximum is not None and value > maximum:
        raise ValueError(f'{label} must be at most {maximum}')


def _text(value, label, limit=600):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'{label} must contain 1–{limit} characters')


def reachable_squares(board, start):
    """Orthogonally reachable non-wall squares from ``start`` (y, x).

    An orthogonal route is always legal under the more permissive diagonal
    movement rule, so this confirms every generated marker is reachable.
    """
    reachable = {start}
    pending = [start]
    while pending:
        y, x = pending.pop()
        for next_y, next_x in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if (0 <= next_y < len(board) and 0 <= next_x < len(board[0])
                    and board[next_y][next_x] != '#' and (next_y, next_x) not in reachable):
                reachable.add((next_y, next_x))
                pending.append((next_y, next_x))
    return reachable


def _validate_monsters(monsters):
    if not isinstance(monsters, list) or not 1 <= len(monsters) <= MAX_MONSTER_KINDS:
        raise ValueError(f'A skirmish needs 1–{MAX_MONSTER_KINDS} monster cards')
    ids, symbols, names = set(), set(), set()
    for monster in monsters:
        if not isinstance(monster, dict):
            raise ValueError('Monster card is missing')
        monster_id = monster.get('id')
        if not isinstance(monster_id, str) or not ID_PATTERN.match(monster_id) or monster_id in ids:
            raise ValueError('Every monster needs a unique lower-case id')
        _text(monster.get('name'), f'monster {monster_id} name', 60)
        if monster['name'].casefold() in names:
            raise ValueError(f'Duplicate monster name: {monster["name"]}')
        symbol = monster.get('symbol')
        if (not isinstance(symbol, str) or len(symbol) != 1 or not 'A' <= symbol <= 'Z'
                or symbol in RESERVED_MARKERS or symbol in symbols):
            raise ValueError(f'Monster {monster_id} needs a unique map letter other than E or O')
        _positive_int(monster.get('count'), f'monster {monster_id} count', maximum=MAX_MONSTERS_OF_KIND)
        for field in ('role', 'brief', 'behaviour'):
            _text(monster.get(field), f'monster {monster_id} {field}')
        role_key = monster['role'].casefold()
        if role_key not in MONSTER_ROLES:
            raise ValueError(f'Monster {monster_id} has an unknown role')
        named_role = NAMED_MONSTER_ROLES.get(monster['name'].casefold())
        if named_role is not None and role_key != named_role:
            raise ValueError(f'Monster {monster_id} must use its named one-page card')
        template = MONSTER_ROLES[role_key]
        if monster.get('stats') != template['stats']:
            raise ValueError(f'Monster {monster_id} stats must use its role template')
        if monster.get('tn') != template['tn']:
            raise ValueError(f'Monster {monster_id} TN must use its role template')
        attack = monster.get('attack', {})
        _text(attack.get('name'), f'monster {monster_id} attack name', 60)
        if attack != {'name': attack['name'], **template['attack']}:
            raise ValueError(f'Monster {monster_id} attack must use its role template')
        ids.add(monster_id)
        symbols.add(symbol)
        names.add(monster['name'].casefold())
    return {monster['symbol']: monster for monster in monsters}


def _validate_map(scenario, by_symbol):
    board = scenario.get('map')
    if (not isinstance(board, list) or not 3 <= len(board) <= MAX_MAP_SIDE
            or not all(isinstance(row, str) and len(row) == len(board[0]) for row in board)
            or not 3 <= len(board[0]) <= MAX_MAP_SIDE):
        raise ValueError(f'Skirmish map rows must be rectangular and 3–{MAX_MAP_SIDE} squares per side')
    allowed = TERRAIN | RESERVED_MARKERS | set(by_symbol)
    unknown = {square for row in board for square in row} - allowed
    if unknown:
        raise ValueError('Map uses symbols without a monster card: ' + ', '.join(sorted(unknown)))
    positions = {}
    for y, row in enumerate(board):
        for x, square in enumerate(row):
            if square not in TERRAIN:
                positions.setdefault(square, []).append((y, x))
    for marker, label in (('E', 'entrance'), ('O', 'objective')):
        if len(positions.get(marker, [])) != 1:
            raise ValueError(f'Skirmish map needs exactly one {label} ({marker})')
    for symbol, monster in by_symbol.items():
        if len(positions.get(symbol, [])) != monster['count']:
            raise ValueError(f'Map must place exactly {monster["count"]} {monster["name"]} ({symbol})')
    reachable = reachable_squares(board, positions['E'][0])
    if any(square not in reachable for squares in positions.values() for square in squares):
        raise ValueError('The objective and every monster must be reachable from the entrance')
    legend = scenario.get('legend', {})
    if not isinstance(legend, dict) or not set(positions) | {'+'} <= set(legend):
        raise ValueError('Map legend must explain every marker')


def validate_packet(packet):
    """Reject packets that do not implement the core rules profile."""
    if not isinstance(packet, dict) or packet.get('rules_version') != RULES_VERSION:
        raise ValueError('Unknown skirmish rules version')
    forbidden = DEFERRED_CONTENT_KEYS.intersection(packet)
    if forbidden:
        raise ValueError('Skirmish packet contains deferred content: ' + ', '.join(sorted(forbidden)))
    scope = packet.get('product_scope', {})
    if set(scope.get('included', [])) != SCOPE:
        raise ValueError('Skirmish product scope is incomplete')
    if not {'items', 'loot', 'shops', 'equipment_catalog'}.issubset(scope.get('deferred', [])):
        raise ValueError('Item systems must remain explicitly deferred')
    if packet.get('dice') != DICE_PROFILE:
        raise ValueError('Skirmish packet must use the one-page D6, D3, D12, and D20 dice profile')
    if packet.get('combat_rules') != COMBAT_RULES:
        raise ValueError('Skirmish packet must use the core ATK, DEF, TN, and damage rules')

    base = packet.get('base_character')
    if not isinstance(base, dict) or base.get('stats') != BASE_CHARACTER_STATS:
        raise ValueError('Every character must use the universal one-page stat profile')
    if base.get('level') != 1 or base.get('build_points') != 0:
        raise ValueError('Every character must begin at level 1 with no build points')
    if base.get('tn') != 4:
        raise ValueError('Every character must use the universal target TN 4')
    attack = base.get('attack', {})
    if attack != {'name': 'Punch', 'test': ATTACK_TEST, 'damage_die': 'D3', 'range': 1}:
        raise ValueError('Base character must use the one-page Punch action')
    _text(base.get('rule'), 'base character rule')

    level_up = packet.get('level_up', {})
    if (level_up.get('levels_gained') != 1 or level_up.get('build_points_gained') != 1
            or level_up.get('maximum_level') != 5):
        raise ValueError('A completed skirmish must grant one level and one build point, up to level 5')
    choices = {choice.get('id'): choice for choice in level_up.get('choices', []) if isinstance(choice, dict)}
    if set(choices) != LEVEL_UP_CHOICES:
        raise ValueError('Level-up choices must match the one-page rules')
    for choice_id, expected in LEVEL_UP_PROFILE.items():
        if any(choices[choice_id].get(field) != value for field, value in expected.items()):
            raise ValueError('Level-up choices must use the one-page effects')

    by_symbol = _validate_monsters(packet.get('monsters'))
    scenario = packet.get('scenario', {})
    if not isinstance(scenario.get('id'), str) or not ID_PATTERN.match(scenario['id']):
        raise ValueError('Skirmish needs a lower-case id')
    _text(scenario.get('name'), 'Skirmish name', 80)
    for field in ('story', 'objective', 'completion'):
        _text(scenario.get(field), f'Skirmish {field}', 1200)
    _validate_map(scenario, by_symbol)
    return packet


def load_packet():
    """Load the bundled example skirmish (The Sunless Crypt)."""
    with PACKET_PATH.open(encoding='utf-8') as handle:
        return validate_packet(json.load(handle))


def rules_frame():
    """Everything in a packet that generation must never change."""
    packet = load_packet()
    return {key: copy.deepcopy(packet[key]) for key in (
        'rules_version', 'status', 'product_scope', 'dice', 'combat_rules', 'base_character', 'level_up')}


def upgrade_legacy_packet(packet):
    """Update a saved scenario without altering the user's file.

    Core saves receive missing combat explanations and monster attack tests.
    Pre-core mechanics are replaced by the fixed current profile. Story, map,
    names, counts, and attack flavour are retained.
    """
    if isinstance(packet, dict) and packet.get('rules_version') == RULES_VERSION:
        upgraded = copy.deepcopy(packet)
        upgraded.setdefault('combat_rules', copy.deepcopy(COMBAT_RULES))
        for monster in upgraded.get('monsters', []):
            if isinstance(monster, dict) and isinstance(monster.get('attack'), dict):
                monster['attack'].setdefault('test', ATTACK_TEST)
                # Upgrade only recognised old summaries; retain authored exceptions.
                if monster.get('behaviour') == LEGACY_MONSTER_BEHAVIOUR:
                    monster['behaviour'] = DEFAULT_MONSTER_BEHAVIOUR
                elif monster.get('behaviour') == LEGACY_BOSS_BEHAVIOUR:
                    monster['behaviour'] = BOSS_BEHAVIOUR
        if isinstance(upgraded.get('scenario'), dict):
            if upgraded['scenario'].get('completion') == 'After a win, every participating character gains +1 Level and +1 Build Point.':
                upgraded['scenario']['completion'] = COMPLETION
        return upgraded
    if not isinstance(packet, dict) or packet.get('rules_version') not in PRE_CORE_RULES_VERSIONS:
        return packet
    upgraded = copy.deepcopy(packet)
    upgraded.update(rules_frame())
    for monster in upgraded.get('monsters', []):
        role_key = str(monster.get('role', '')).casefold()
        if role_key not in MONSTER_ROLES:
            name_key = str(monster.get('name', '')).casefold()
            role_key = NAMED_MONSTER_ROLES.get(name_key, 'guard')
        role_key = NAMED_MONSTER_ROLES.get(str(monster.get('name', '')).casefold(), role_key)
        template = MONSTER_ROLES[role_key]
        old_attack = monster.get('attack', {}) if isinstance(monster.get('attack'), dict) else {}
        monster.pop('level', None)
        monster['role'] = role_key.capitalize()
        monster['stats'] = copy.deepcopy(template['stats'])
        monster['tn'] = template['tn']
        monster['attack'] = {'name': old_attack.get('name') or 'Attack', **copy.deepcopy(template['attack'])}
        monster['behaviour'] = template['behaviour']
    scenario = upgraded.get('scenario')
    if isinstance(scenario, dict):
        scenario['completion'] = COMPLETION
    return upgraded
