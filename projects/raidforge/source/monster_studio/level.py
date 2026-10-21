"""The Law of Level: deterministic growth, build checks, and combat arithmetic.

The three v1.0 decisions remain explicit configuration, rather than silently
declaring a proposed v1.1 final. No model or skirmish modules are needed here.
"""
from dataclasses import asdict, dataclass
from math import inf


STAT_NAMES = ('hp', 'atk', 'spd', 'def', 'magic', 'tn', 'die')
TIERS = {3: 'Easy', 4: 'Normal', 5: 'Hard', 6: 'Boss'}
UNIVERSAL_ACTIONS = ('Punch', 'Kick', 'Push', 'Interact')
ENEMIES = {
    'zombie': {'name': 'Zombie', 'tn': 3, 'def': 1, 'hp': 6, 'die': 2},
    'tinman': {'name': 'Tinman', 'tn': 4, 'def': 2, 'hp': 10, 'die': 3},
    'vampire': {'name': 'Vampire', 'tn': 6, 'def': 4, 'hp': 16, 'die': 4},
}


def _integer(name, value, minimum=None):
    if type(value) is not int or (minimum is not None and value < minimum):
        suffix = f' >= {minimum}' if minimum is not None else ''
        raise ValueError(f'{name} must be an integer{suffix}')


@dataclass(frozen=True)
class Rules:
    atk_role: str = 'special'
    bp_curve: str = 'linear'
    level5_die: int = 5

    def __post_init__(self):
        if self.atk_role not in ('special', 'hit', 'damage'):
            raise ValueError('ATK role must be special, hit, or damage')
        if self.bp_curve not in ('linear', 'early'):
            raise ValueError('BP curve must be linear or early')
        if type(self.level5_die) is not int or self.level5_die not in (5, 8):
            raise ValueError('Level 5 die must be 5 or 8')

    @property
    def attack_test(self):
        return '1D6 + ATK ≥ target TN' if self.atk_role == 'hit' else '1D6 ≥ target TN'

    @property
    def summary(self):
        atk = {'special': 'reserved for special moves', 'hit': 'added to hit',
               'damage': 'added to damage'}[self.atk_role]
        bp = 'L−1' if self.bp_curve == 'linear' else '0,2,3,4,5'
        return f'Law of Level (draft): ATK {atk}; BP {bp}; Level 5 D{self.level5_die}'

    def to_dict(self):
        return asdict(self)

    def combat_rules(self):
        return {
            'atk': {
                'special': 'ATK is reserved for special moves; no ATK bonus to basic hits or damage.',
                'hit': 'Add ATK to the D6 hit roll only. ATK does not increase damage.',
                'damage': 'Add ATK to damage before DEF. Do not add ATK to the D6 hit roll.',
            }[self.atk_role],
            'def': 'Subtract target DEF from damage, minimum 0. No defence roll or change to TN.',
            'tn': 'Meet or beat the target TN. Character TN is 4 at L1–3, 5 at L4, 6 at L5.',
            'damage': ('Roll the damage die, add ATK, subtract target DEF, minimum 0.'
                       if self.atk_role == 'damage' else
                       'Roll the damage die, subtract target DEF, minimum 0.'),
            'cover': 'Kick is ranged: an adjacent target gains +1 DEF against Kick.',
            'actions': 'Punch and Kick use D3 at every level. Push repositions; Interact is non-combat.',
        }


DEFAULT_RULES = Rules()


def base_state(level, rules=DEFAULT_RULES):
    _integer('Level', level, 1)
    if level > 5:
        raise ValueError('Level must be between 1 and 5; extending the table requires new rules')
    return {
        'hp': 8 + 2 * (level - 1), 'atk': level, 'spd': 3,
        'def': level - 1, 'magic': level,
        'tn': 4 if level <= 3 else level + 1,
        'die': rules.level5_die if level == 5 else 3 + (level - 1) // 2,
    }


def bp_pool(level, rules=DEFAULT_RULES):
    base_state(level, rules)
    return level - 1 if rules.bp_curve == 'linear' or level == 1 else level


def invariant_errors(state, rules=DEFAULT_RULES):
    errors = []
    for stat in STAT_NAMES:
        if type(state.get(stat)) is not int or state[stat] < 0:
            errors.append(f'{stat.upper()} must be a nonnegative integer')
    if errors:
        return errors
    if state['hp'] < state['atk']:
        errors.append('HP must be at least ATK')
    if not 4 <= state['tn'] <= 6:
        errors.append('TN must stay between 4 and 6')
    if not 3 <= state['die'] <= rules.level5_die:
        errors.append(f'Damage die must stay between D3 and D{rules.level5_die}')
    if state['def'] >= state['hp']:
        errors.append('DEF must be below HP')
    if state['hp'] % 2:
        errors.append('HP must remain even; buy HP increases in pairs (2 BP for +2 HP)')
    return errors


def character(level, rules=DEFAULT_RULES, boosts=None, learned=None):
    """Validate a complete BP allocation; unspent points are retained.

    Learned entries are (name, printed cost) pairs. No ability catalogue or
    invented move effects are implied by recording their 2–4 BP costs.
    """
    state = base_state(level, rules)
    caps = {key: value + 2 for key, value in base_state(5, rules).items()}
    spent = 0
    for stat, amount in (boosts or {}).items():
        if stat not in STAT_NAMES:
            raise ValueError(f'Unknown stat {stat!r}; choose {", ".join(STAT_NAMES)}')
        _integer(f'{stat.upper()} increase', amount, 0)
        state[stat] += amount
        spent += amount
        if state[stat] > caps[stat]:
            raise ValueError(f'{stat.upper()} exceeds its Level 5 + 2 cap ({caps[stat]})')
    abilities = []
    for name, cost in learned or ():
        if not isinstance(name, str) or not name.strip():
            raise ValueError('A learned move or spell needs a name')
        _integer('Move/spell cost', cost, 2)
        if cost > 4:
            raise ValueError('Move/spell cost must be between 2 and 4 BP')
        abilities.append({'name': name.strip(), 'cost': cost})
        spent += cost
    pool = bp_pool(level, rules)
    if spent > pool:
        raise ValueError(f'Build spends {spent} BP, but Level {level} has only {pool}')
    errors = invariant_errors(state, rules)
    if errors:
        raise ValueError('; '.join(errors))
    return {
        'level': level, 'stats': {key: state[key] for key in STAT_NAMES[:5]},
        'tn': state['tn'], 'die': state['die'], 'tier': TIERS[state['tn']],
        'bp': {'pool': pool, 'spent': spent, 'remaining': pool - spent},
        'learned': abilities, 'actions': list(UNIVERSAL_ACTIONS),
        'rules': rules.to_dict(),
    }


def hit_probability(tn, hit_bonus=0):
    _integer('TN', tn, 1)
    _integer('Hit bonus', hit_bonus)
    return max(0, min(6, 7 + hit_bonus - tn)) / 6


def damage_on_hit(die, defence, damage_bonus=0):
    """Average max(0, X + bonus - DEF) over all faces, including full armour."""
    _integer('Damage die', die, 1)
    _integer('DEF', defence, 0)
    _integer('Damage bonus', damage_bonus)
    # Arithmetic series from the first positive damage through the last.
    offset = damage_bonus - defence
    first_face = max(1, 1 - offset)
    if first_face > die:
        return 0.0
    return (die - first_face + 1) * (first_face + die + 2 * offset) / (2 * die)


def matchup(attacker, enemy, rules=None, action='base', adjacent=False):
    """Outgoing damage only. HP/E is an estimate, not an exact duel simulation."""
    rules = rules or Rules(**attacker['rules'])
    if action not in ('base', 'punch', 'kick'):
        raise ValueError('Choose a damaging action: base, punch, or kick')
    if adjacent and action != 'kick':
        raise ValueError('--adjacent applies only to Kick')
    for stat in ('tn', 'hp', 'def'):
        _integer(f'Target {stat.upper()}', enemy[stat], 0 if stat == 'def' else 1)
    if enemy['tn'] not in TIERS:
        raise ValueError('Enemy TN must be between 3 and 6')
    die = attacker['die'] if action == 'base' else 3
    atk = attacker['stats']['atk']
    hit_bonus = atk if rules.atk_role == 'hit' else 0
    damage_bonus = atk if rules.atk_role == 'damage' else 0
    defence = enemy['def'] + int(action == 'kick' and adjacent)
    chance = hit_probability(enemy['tn'], hit_bonus)
    on_hit = damage_on_hit(die, defence, damage_bonus)
    expected = chance * on_hit
    return {
        'enemy': enemy.get('name', 'Custom target'), 'action': action,
        'die': die, 'hit_bonus': hit_bonus, 'damage_bonus': damage_bonus,
        'target_tn': enemy['tn'], 'target_hp': enemy['hp'],
        'effective_def': defence, 'hit_probability': chance,
        'damage_on_hit': on_hit, 'damage_per_turn': expected,
        'killable': expected > 0,
        'estimated_turns': enemy['hp'] / expected if expected else inf,
    }
