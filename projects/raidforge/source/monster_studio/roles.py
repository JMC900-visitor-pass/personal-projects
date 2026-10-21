"""Creative monster design contracts: the model designs; code checks the budget."""
import re

from .level import DEFAULT_RULES, Rules, base_state, character, invariant_errors

ROLES = ('guard', 'knight', 'ranger', 'boss')
ROLE_GUIDES = {
    'guard': 'Defend a place or ally. Make the defence specific to this creature.',
    'knight': 'Pressure enemies in close combat. Prefer melee and a clear way to counter it.',
    'ranger': 'Fight at distance and care about positioning. Prefer a ranged attack.',
    'boss': 'Control a confrontation through a distinctive threat with readable counterplay.',
}
STATS = ('hp', 'atk', 'spd', 'def', 'magic')
SYSTEM = (
    'You are a tabletop monster designer. Return only the requested JSON artifact. '
    'The brief, theme and player feedback guide the design. The supplied level and '
    'rules are fixed, but the baseline is NOT a compulsory stat line. You own stat '
    'trade-offs within the stated budget, attack range, tactics, counterplay and '
    'one optional custom move. Make these choices express the creature. '
    'Keep rules in the move fields; flavour, identity and weakness grant no hidden bonuses. '
    'Write runnable effects: who is affected, when, how far, how long, and how often. '
    'Use one action per activation and at most one damaging action. No extra turns, '
    'unlimited loops, undefined conditions, or permanent changes to level/TN/dice. '
    'Develop the physical action or supernatural effect before naming it. Names should '
    'evoke what this particular creature does, not a generic adjective plus Strike. '
    'Natural names may be longer than three words. No lore essay or design reasoning '
    'is needed: deliver concise, playable cards. This is a playtest draft.'
)


def template(role, level=1, rules=DEFAULT_RULES):
    if role not in ROLES:
        raise ValueError(f'Unknown role: {role}')
    profile = character(level, rules)
    baseline = profile['stats']
    caps = base_state(5, rules)
    bounds = {}
    for stat, value in baseline.items():
        spread = 4 if stat == 'hp' else 1 if stat == 'def' else 2
        lower = max(4 if stat == 'hp' else 1 if stat in ('atk', 'spd') else 0, value - spread)
        upper = min(value + spread, caps[stat] + 2)
        if stat == 'def':
            upper = min(upper, profile['die'] - 1)
        bounds[stat] = [lower, upper]
    return {
        'role': role, 'role_guide': ROLE_GUIDES[role], 'level': level,
        'stats': baseline, 'bounds': bounds, 'tn': profile['tn'], 'die': profile['die'],
        'budget': sum(baseline.values()) + profile['bp']['pool'],
        'rules': rules.to_dict(), 'rules_summary': rules.summary,
        'combat_rules': rules.combat_rules(),
    }


def design_prompt(template, concept, theme='', previous=()):
    return {
        'brief': concept, 'theme': theme, 'role': template['role'],
        'role_guide': template['role_guide'], 'level': template['level'],
        'rules': template['rules'], 'combat_rules': template['combat_rules'],
        'design_limits': {
            'baseline_stats': template['stats'], 'stat_bounds': template['bounds'],
            'fixed_tn': template['tn'], 'fixed_damage_die': f'D{template["die"]}',
            'total_budget': template['budget'],
            'budget_rule': 'sum(hp, atk, spd, def, magic) + move.cost <= total_budget; null move costs 0',
            'tradeoffs': 'You may lower baseline stats to fund increases or a move. HP must be even. Use the budget deliberately.',
            'invariants': 'HP >= ATK; DEF < HP. TN and damage die stay fixed. ATK/SPD at least 1.',
            'attack_range': 'Choose 1–4 squares; 1 is melee, 2–4 are ranged. Role is guidance, not a fixed template.',
            'move': 'Optional ONE custom move: cost 2 for a small utility, 3 for strong positioning/control, 4 for a limited major effect. Spend from the same budget. State trigger, effect, and explicit limit. Prefer replacing the normal action; if it damages, use the printed attack roll/die and no additional damage roll. Define conditions inline.',
            'counterplay': 'A practical tactical weakness opponents can exploit, not an extra unpriced numeric modifier.',
        },
        'avoid_repeating': list(previous)[-12:],
    }


def card_schema(template):
    text = lambda limit: {'type': 'string', 'minLength': 1, 'maxLength': limit}
    stats = {}
    for key, (low, high) in template['bounds'].items():
        stats[key] = {'type': 'integer', 'minimum': low, 'maximum': high}
        if key == 'hp':
            stats[key]['multipleOf'] = 2
    move = {'type': 'object', 'additionalProperties': False,
            'required': ['name', 'trigger', 'effect', 'limit', 'cost'],
            'properties': {'name': text(72), 'trigger': text(160), 'effect': text(480),
                           'limit': text(220), 'cost': {'type': 'integer', 'minimum': 2, 'maximum': 4}}}
    fields = {
        'monster_name': text(72), 'identity': text(180), 'flavour': text(300),
        'stats': {'type': 'object', 'additionalProperties': False,
                  'required': list(STATS), 'properties': stats},
        'attack_name': text(72), 'range': {'type': 'integer', 'minimum': 1, 'maximum': 4},
        'move': {'anyOf': [{'type': 'null'}, move]},
        'tactics': text(320), 'weakness': text(220),
    }
    return {'type': 'object', 'additionalProperties': False,
            'required': list(fields), 'properties': fields}


def roster_schema(template):
    return {'type': 'object', 'additionalProperties': False, 'required': ['monsters'],
            'properties': {'monsters': {'type': 'array', 'minItems': 3, 'maxItems': 3,
                                        'items': card_schema(template)}}}


def _text(raw, key, limit):
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{key} must contain text')
    value = ' '.join(value.split())
    if len(value) > limit:
        raise ValueError(f'{key} exceeds {limit} characters; shorten it without truncating the name')
    return value


def name_key(value):
    return re.sub(r'\W+', '', value.casefold())


def clean_card(raw, role, template):
    if not isinstance(raw, dict):
        raise ValueError('Each card must be an object')
    expected = card_schema(template)['required']
    if set(raw) != set(expected):
        raise ValueError(f'Card fields must be exactly: {", ".join(expected)}')
    stats = raw['stats']
    if not isinstance(stats, dict) or set(stats) != set(STATS):
        raise ValueError('stats must contain exactly hp, atk, spd, def, magic')
    for stat, (low, high) in template['bounds'].items():
        if type(stats[stat]) is not int or not low <= stats[stat] <= high:
            raise ValueError(f'{stat.upper()} must be an integer from {low} to {high}')
    rules = Rules(**template['rules'])
    errors = invariant_errors({**stats, 'tn': template['tn'], 'die': template['die']}, rules)
    if errors:
        raise ValueError('; '.join(errors))
    reach = raw['range']
    if type(reach) is not int or not 1 <= reach <= 4:
        raise ValueError('Attack range must be an integer from 1 to 4')
    move = raw['move']
    if move is not None:
        fields = ('name', 'trigger', 'effect', 'limit', 'cost')
        if not isinstance(move, dict) or set(move) != set(fields):
            raise ValueError('A move needs name, trigger, effect, limit, and cost (or use null)')
        if type(move['cost']) is not int or not 2 <= move['cost'] <= 4:
            raise ValueError('Move cost must be 2–4')
        move = {key: _text(move, key, limit) for key, limit in
                [('name', 72), ('trigger', 160), ('effect', 480), ('limit', 220)]} | {'cost': move['cost']}
    cost = move['cost'] if move else 0
    spent = sum(stats.values()) + cost
    if spent > template['budget']:
        raise ValueError(f'Budget exceeded: stats {sum(stats.values())} + move {cost} = {spent}; maximum {template["budget"]}')
    name = _text(raw, 'monster_name', 72)
    attack = _text(raw, 'attack_name', 72)
    if move and name_key(move['name']) == name_key(attack):
        raise ValueError('The normal attack and custom move need distinct names')
    return {
        'name': name, 'role': role, 'level': template['level'],
        'identity': _text(raw, 'identity', 180), 'blurb': _text(raw, 'flavour', 300),
        'stats': {stat: stats[stat] for stat in STATS}, 'tn': template['tn'], 'melee': reach == 1,
        'attack': {'name': attack, 'test': rules.attack_test,
                   'damage_die': f'D{template["die"]}', 'range': reach,
                   'damage_bonus': stats['atk'] if rules.atk_role == 'damage' else 0},
        'move': move, 'tactics': _text(raw, 'tactics', 320),
        'weakness': _text(raw, 'weakness', 220),
        'budget': {'limit': template['budget'], 'stats': sum(stats.values()),
                   'move': cost, 'remaining': template['budget'] - spent},
        'rules': dict(template['rules']), 'rules_summary': template['rules_summary'],
    }


def design_data(card):
    """All editable fields, including mechanics, survive development/refinement."""
    return {'monster_name': card['name'], 'identity': card['identity'],
            'flavour': card['blurb'], 'stats': dict(card['stats']),
            'attack_name': card['attack']['name'], 'range': card['attack']['range'],
            'move': card['move'], 'tactics': card['tactics'], 'weakness': card['weakness']}


def summary(card):
    return {'name': card['name'], 'identity': card['identity'],
            'attack': card['attack']['name'], 'move': card['move']['name'] if card['move'] else None}


def validate_variations(cards, previous=()):
    if len(cards) != 3:
        raise ValueError('Return exactly three complete designs')
    for key, values in (
        ('monster names', [name_key(c['name']) for c in cards]),
        ('attack names', [name_key(c['attack']['name']) for c in cards]),
        ('stat lines', [tuple(c['stats'][s] for s in STATS) for c in cards]),
        ('identities', [name_key(c['identity']) for c in cards]),
    ):
        if len(set(values)) != 3:
            raise ValueError(f'The three designs must have different {key}; recolouring one card is not variation')
    old_names = {name_key(c['name']) for c in previous}
    if any(name_key(c['name']) in old_names for c in cards):
        raise ValueError('Choose fresh monster names instead of repeating earlier candidates')
    moves = [name_key(c['move']['name']) for c in cards if c['move']]
    if len(set(moves)) != len(moves):
        raise ValueError('Custom move names must differ between candidates')
