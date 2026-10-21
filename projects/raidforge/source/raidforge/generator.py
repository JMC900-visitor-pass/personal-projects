"""Skirmish generation agent: brief story, square-grid map, and monster cards.

Code owns every number (role stat blocks, quantities, map geometry, marker
placement). The writer — a local Ollama model or the offline templates — only
supplies names, story, objective wording, card blurbs, and attack names.
Monster names typed by the user are printed exactly and never rewritten.
"""
import copy
import math
import random
import re
import secrets
import unicodedata
from datetime import datetime, timezone

from .llm import OllamaWriter, DEFAULT_MODEL
from .skirmish import (
    COMPLETION,
    COMBAT_RULES,
    MAX_MONSTER_KINDS,
    MAX_MONSTERS_OF_KIND,
    MONSTER_ROLES,
    NAMED_MONSTER_ROLES,
    RESERVED_MARKERS,
    rules_frame,
    validate_packet,
)


# Re-exported for the CLI and callers that offer the bounded generation roles.
ROLES = MONSTER_ROLES
ROLE_TEXT = {
    'minion': ('Weak alone and dangerous in numbers, it throws itself at whoever is closest.', 'Clawing rush'),
    'guard': ('Set here to hold the way, it follows the last order it was given.', 'Heavy blow'),
    'hunter': ('It hunts by movement and closes the distance faster than it should.', 'Rending claws'),
    'shooter': ('It prefers to strike from the dark and keep clear of blades.', 'Loosed shot'),
    'brute': ('Slow and heavy, it shrugs off blows that would fell a lesser creature.', 'Crushing slam'),
    'boss': ('The master of this place, certain no challenger will reach what it guards.', 'Master’s strike'),
}
# (keywords, printed name, role, card blurb, attack name) for offline rosters and role guesses.
FAMILIES = [
    (('zombie', 'ghoul', 'corpse', 'risen'), 'Zombie', 'guard', 'A newly risen corpse that follows the last order it heard.', 'Grave grasp'),
    (('vampire',), 'Vampire', 'boss', 'A pale master whose perfect manners barely hide an ancient hunger.', 'Velvet fangs'),
    (('chaos', 'spawn', 'mutant', 'warp'), 'Chaos Spawn', 'hunter', 'An unfinished knot of claws and eyes that hunts by movement.', 'Warped talons'),
    (('skeleton', 'bone'), 'Skeleton Archer', 'shooter', 'Dry bones that still remember how to draw a bow.', 'Rattling arrow'),
    (('goblin',), 'Goblin', 'minion', 'Quick, spiteful, and never alone for long.', 'Rusty stab'),
    (('rat', 'vermin'), 'Giant Rat', 'minion', 'Swollen on crypt scraps and bold in the dark.', 'Gnawing bite'),
    (('cultist', 'cult'), 'Cultist', 'minion', 'A hooded zealot chanting a name best left unspoken.', 'Ritual knife'),
    (('bandit', 'thief', 'raider'), 'Bandit', 'minion', 'A hired blade who fights for coin, not glory.', 'Cudgel swing'),
    (('orc',), 'Orc Raider', 'guard', 'A scarred warrior who holds a doorway like a wall.', 'Cleaver chop'),
    (('spider',), 'Cave Spider', 'hunter', 'It drops from the ceiling without a sound.', 'Venom bite'),
    (('wolf', 'hound'), 'Wolf', 'hunter', 'Lean, patient, and hungry.', 'Savage bite'),
    (('ghost', 'spirit', 'wraith', 'phantom'), 'Wraith', 'hunter', 'A cold shape that drifts through the dark toward warmth.', 'Chilling touch'),
    (('golem', 'construct', 'clay', 'statue'), 'Clay Golem', 'brute', 'Fired in a forgotten kiln, it still guards a vanished maker.', 'Fired-clay fist'),
    (('ogre', 'troll', 'giant'), 'Troll', 'brute', 'Huge, foul, and far too hard to put down.', 'Crushing slam'),
    (('necromancer', 'lich', 'witch', 'sorcer', 'warlock'), 'Necromancer', 'boss', 'Its whispered orders keep the dead on their feet.', 'Grave bolt'),
    (('dragon', 'drake', 'wyrm'), 'Young Drake', 'boss', 'Scales still soft, temper already legendary.', 'Searing bite'),
]
FALLBACK_ROSTER = [('Shambling Thrall', 'guard'), ('Skittering Horror', 'hunter'), ('Nameless Master', 'boss')]
OFFLINE_TITLES = ['The Sunless Crypt', 'The Drowned Chapel', 'The Broken Watchtower', 'The Hollow Mill',
                  'The Ashen Vault', 'The Silent Barrow', 'The Salt Cellars', 'The Cinder Stair']
OFFLINE_GOALS = ['Break the seal', 'Recover the lost relic', 'Relight the warding lamp', 'Free the captive',
                 'Destroy the ritual circle', 'Ring the old bell']
DIFFICULTY = {'easy': (3, 3), 'standard': (5, 4), 'hard': (7, 5)}  # threat budget = base + per-character × party size
MAX_TOTAL_MONSTERS = 20
ROOM_W, ROOM_H = 5, 3


# ---------------------------------------------------------------- brief input

def _text(value, label, limit, required=True):
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValueError(f'{label} is required')
        return None
    if not isinstance(value, str) or len(value.strip()) > limit:
        raise ValueError(f'{label} must be at most {limit} characters')
    return ' '.join(value.split())


def _integer(value, label, low, high, default=None):
    if value is None or value == '':
        return default
    if isinstance(value, bool):
        raise ValueError(f'{label} must be a whole number')
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f'{label} must be a whole number') from None
    if str(number) != str(value).strip() or not low <= number <= high:
        raise ValueError(f'{label} must be between {low} and {high}')
    return number


def parse_brief(data):
    """Validate a creator request from the web form or command line."""
    if not isinstance(data, dict):
        raise ValueError('Expected a skirmish brief')
    monsters = data.get('monsters') or []
    if not isinstance(monsters, list) or len(monsters) > MAX_MONSTER_KINDS:
        raise ValueError(f'List at most {MAX_MONSTER_KINDS} monster types')
    roster, seen = [], set()
    for index, entry in enumerate(monsters, 1):
        if not isinstance(entry, dict):
            raise ValueError('Each monster needs a name')
        name = _text(entry.get('name'), f'Monster {index} name', 60, required=False)
        if name is None:
            continue
        if name.casefold() in seen:
            raise ValueError(f'Monster {name} is listed twice')
        role = entry.get('role') or None
        if role is not None and role not in ROLES:
            raise ValueError(f'Monster role must be one of: {", ".join(ROLES)}')
        seen.add(name.casefold())
        roster.append({'name': name, 'role': role,
                       'count': _integer(entry.get('count'), f'{name} quantity', 1, MAX_MONSTERS_OF_KIND)})
    backend = data.get('backend', 'offline')
    if backend not in ('offline', 'ollama'):
        raise ValueError('Backend must be offline or ollama')
    difficulty = data.get('difficulty') or 'standard'
    if difficulty not in DIFFICULTY:
        raise ValueError('Difficulty must be easy, standard, or hard')
    return {
        'concept': _text(data.get('concept'), 'Story concept', 600),
        'title': _text(data.get('title'), 'Title', 80, required=False),
        'monsters': roster,
        'party_size': _integer(data.get('party_size'), 'Party size', 1, 6, 1),
        'difficulty': difficulty,
        'seed': _integer(data.get('seed'), 'Seed', 0, 2**31 - 1, secrets.randbelow(2**31)),
        'backend': backend,
        'model': _text(data.get('model'), 'Model', 160, required=False) or DEFAULT_MODEL,
        'think': data.get('think') is True,
    }


# ---------------------------------------------------------------- helpers

def slug(text, limit=48):
    ascii_text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '_', ascii_text.lower()).strip('_')[:limit] or 'skirmish'


def _family_for(text):
    folded = text.casefold()
    return next((family for family in FAMILIES if any(key in folded for key in family[0])), None)


def _assign_symbols(monsters):
    used = set(RESERVED_MARKERS)
    for monster in monsters:
        letters = [c for c in unicodedata.normalize('NFKD', monster['name']).upper() if 'A' <= c <= 'Z']
        options = letters + [chr(code) for code in range(ord('A'), ord('Z') + 1)]
        monster['symbol'] = next(letter for letter in options if letter not in used)
        used.add(monster['symbol'])


def _assign_ids(monsters):
    used = set()
    for monster in monsters:
        base = slug(monster['name'], 40)
        monster_id, suffix = base, 2
        while monster_id in used:
            monster_id, suffix = f'{base}_{suffix}', suffix + 1
        monster['id'] = monster_id
        used.add(monster_id)


def threat_budget(party_size, difficulty):
    base, per_character = DIFFICULTY[difficulty]
    return base + per_character * party_size


def assign_counts(monsters, budget):
    """Fill unspecified quantities from the threat budget; locked counts are kept."""
    for monster in monsters:
        if monster.get('count') is None:
            monster['count'] = 1
            monster['auto_count'] = True
    spent = sum(ROLES[m['role']]['threat'] * m['count'] for m in monsters)
    growable = [m for m in monsters if m.pop('auto_count', False) and m['role'] != 'boss']
    while growable:
        grew = False
        for monster in growable:
            cost = ROLES[monster['role']]['threat']
            total = sum(m['count'] for m in monsters)
            if (spent + cost <= budget and monster['count'] < MAX_MONSTERS_OF_KIND
                    and total < MAX_TOTAL_MONSTERS):
                monster['count'] += 1
                spent += cost
                grew = True
        if not grew:
            break
    if sum(m['count'] for m in monsters) > MAX_TOTAL_MONSTERS:
        raise ValueError(f'A skirmish can place at most {MAX_TOTAL_MONSTERS} monsters')
    return spent


# ---------------------------------------------------------------- map

def _neighbours(cell, cols, rows):
    x, y = cell
    for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
        if 0 <= nx < cols and 0 <= ny < rows:
            yield nx, ny


def generate_map(monsters, rng):
    """Connected rooms on a square grid with entrance, objective, and every monster placed."""
    total = sum(m['count'] for m in monsters)
    room_count = max(3, min(6, 2 + math.ceil(total / 3)))
    cols, rows = (2, 2) if room_count <= 4 else (3, 2)
    start = rng.choice([(x, y) for y in range(rows) for x in range(cols)])
    rooms, links = [start], []
    while len(rooms) < room_count:
        frontier = [(a, b) for a in rooms for b in _neighbours(a, cols, rows) if b not in rooms]
        a, b = rng.choice(frontier)
        rooms.append(b)
        links.append((a, b))
    loops = [(a, b) for a in rooms for b in _neighbours(a, cols, rows)
             if b in rooms and a < b and (a, b) not in links and (b, a) not in links]
    if loops and rng.random() < 0.35:
        links.append(rng.choice(loops))

    grid = [['#'] * (cols * (ROOM_W + 1) + 1) for _ in range(rows * (ROOM_H + 1) + 1)]
    interiors = {}
    for cx, cy in rooms:
        squares = [(cy * (ROOM_H + 1) + 1 + dy, cx * (ROOM_W + 1) + 1 + dx) for dy in range(ROOM_H) for dx in range(ROOM_W)]
        for y, x in squares:
            grid[y][x] = '.'
        interiors[(cx, cy)] = squares
    for a, b in links:
        (ax, ay), (bx, by) = sorted((a, b))
        if ay == by:
            grid[ay * (ROOM_H + 1) + 1 + rng.randrange(ROOM_H)][(ax + 1) * (ROOM_W + 1)] = '+'
        else:
            grid[(ay + 1) * (ROOM_H + 1)][ax * (ROOM_W + 1) + 1 + rng.randrange(ROOM_W)] = '+'

    distance, pending = {start: 0}, [start]
    graph = {room: set() for room in rooms}
    for a, b in links:
        graph[a].add(b)
        graph[b].add(a)
    while pending:
        room = pending.pop(0)
        for other in graph[room]:
            if other not in distance:
                distance[other] = distance[room] + 1
                pending.append(other)
    farthest = max(distance.values())
    goal_room = rng.choice(sorted(room for room, d in distance.items() if d == farthest))

    def doorway(y, x):
        return any(grid[ny][nx] == '+' for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)))

    def place(symbol, candidates):
        free = [(y, x) for y, x in candidates if grid[y][x] == '.' and not doorway(y, x)]
        if not free:
            return False
        y, x = rng.choice(free)
        grid[y][x] = symbol
        return True

    place('E', interiors[start])
    place('O', interiors[goal_room])
    goal_y, goal_x = next((y, x) for y, x in interiors[goal_room] if grid[y][x] == 'O')
    beside_goal = [(y, x) for y, x in interiors[goal_room] if max(abs(y - goal_y), abs(x - goal_x)) == 1]
    others = [room for room in rooms if room != start] or rooms
    copies = [m for m in monsters if m['role'] != 'boss' for _ in range(m['count'])]
    rng.shuffle(copies)
    for monster in (m for m in monsters if m['role'] == 'boss'):
        for _ in range(monster['count']):
            if not (place(monster['symbol'], beside_goal) or place(monster['symbol'], interiors[goal_room])):
                copies.append(monster)
    for index, monster in enumerate(copies):
        order = others[index % len(others):] + others[:index % len(others)]
        if not any(place(monster['symbol'], interiors[room]) for room in order):
            raise ValueError('Too many monsters to place on this map; lower the quantities')
    return [''.join(row) for row in grid]


# ---------------------------------------------------------------- writers

def _clip(value, label, limit):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'Local generation failed: the model left {label} empty. Nothing was saved; retry.')
    value = ' '.join(value.split())
    if len(value) > limit:
        value = value[:limit].rsplit(' ', 1)[0].rstrip(',;:') + '…'
    return value


def _silent(event):
    pass


class OfflineWriter:
    """Deterministic templates; no model required."""
    label = 'offline'
    model = None
    emit = staticmethod(_silent)

    def roster(self, brief, rng):
        found = []
        for family in FAMILIES:
            if any(key in brief['concept'].casefold() for key in family[0]) and len(found) < 3:
                found.append({'name': family[1], 'role': family[2], 'count': None})
        return found or [{'name': name, 'role': role, 'count': None} for name, role in FALLBACK_ROSTER]

    def write(self, brief, monsters, rng):
        title = brief['title'] or rng.choice(OFFLINE_TITLES)
        bosses = [m['name'] for m in monsters if m['role'] == 'boss']
        hook = (f'Somewhere past the last door, the {bosses[0]} waits.' if bosses
                else 'Push through, reach what you came for, and get out alive.')
        cards = {}
        for monster in monsters:
            if monster['role'] is None:
                monster['role'] = 'guard'
            family = _family_for(monster['name'])
            brief_text, attack = (family[3], family[4]) if family else ROLE_TEXT[monster['role']]
            cards[monster['id']] = {'brief': brief_text, 'attack_name': attack}
        return {'name': title, 'story': f'{brief["concept"].rstrip(".")}. {hook}',
                'objective_goal': rng.choice(OFFLINE_GOALS), 'monsters': cards}


class ModelWriter:
    """Local Ollama model writes flavour inside a JSON schema; code keeps the numbers."""
    label = 'ollama'
    SYSTEM = ('You write content for a tactical tabletop skirmish game played on a square grid. '
              'Return ONLY the requested JSON object. The user concept is canon: stay close to it. '
              'Monster names are fixed and must never be changed, translated, or pluralised. '
              'The supplied combat_rules are fixed context, not writing to include in your response. '
              'Use the stat named by the action: Punch uses ATK; Kick uses SPD. '
              'Flavour text is never rules: no numbers, dice, damage, bonuses, ranges, or special abilities. ')

    emit = staticmethod(_silent)

    def __init__(self, model, writer=None, think=False):
        self.writer = writer or OllamaWriter(model, think=think)
        self.model = self.writer.model

    def _ask(self, step, system, prompt, schema, seed):
        def on_token(channel, text):
            self.emit({'type': 'token', 'step': step, 'channel': channel, 'text': text})
        return self.writer.ask(system, {**prompt, 'combat_rules': copy.deepcopy(COMBAT_RULES)},
                               schema, seed, on_token=on_token)

    def roster(self, brief, rng):
        schema = {'type': 'object', 'required': ['monsters'], 'properties': {'monsters': {
            'type': 'array', 'minItems': 2, 'maxItems': 3, 'items': {
                'type': 'object', 'required': ['name', 'role'],
                'properties': {'name': {'type': 'string', 'maxLength': 40}, 'role': {'type': 'string', 'enum': list(ROLES)}}}}}}
        result = self._ask(
            'roster', self.SYSTEM + 'Design the monster types for this skirmish: 2–3 distinct creatures that belong in the '
            'concept, with short evocative names (1–3 words) and at most one boss.',
            {'concept': brief['concept'], 'title': brief['title'], 'roles': {k: ROLE_TEXT[k][0] for k in ROLES}},
            schema, brief['seed'])
        roster, seen = [], set()
        for entry in result.get('monsters', [])[:3]:
            name = _clip(entry.get('name') if isinstance(entry, dict) else None, 'a monster name', 40)
            role = entry.get('role')
            if role not in ROLES or name.casefold() in seen:
                continue
            if role == 'boss' and any(m['role'] == 'boss' for m in roster):
                role = 'brute'
            seen.add(name.casefold())
            roster.append({'name': name, 'role': role, 'count': None})
        if not roster:
            raise ValueError('Local generation failed: the model proposed no usable monsters. Nothing was saved; retry.')
        return roster

    def write(self, brief, monsters, rng):
        card_schema = {}
        for monster in monsters:
            properties = {'brief': {'type': 'string', 'maxLength': 220}, 'attack_name': {'type': 'string', 'maxLength': 36}}
            if monster['role'] is None:
                properties['role'] = {'type': 'string', 'enum': list(ROLES)}
            card_schema[monster['id']] = {'type': 'object', 'properties': properties, 'required': list(properties)}
        properties = {'story': {'type': 'string', 'maxLength': 650},
                      'objective_goal': {'type': 'string', 'maxLength': 80},
                      'monsters': {'type': 'object', 'properties': card_schema, 'required': list(card_schema)}}
        if not brief['title']:
            properties['name'] = {'type': 'string', 'maxLength': 60}
        schema = {'type': 'object', 'properties': properties, 'required': list(properties)}
        prompt = {
            'concept': brief['concept'], 'title': brief['title'], 'party_size': brief['party_size'],
            'monsters': [{'id': m['id'], 'name': m['name'], 'role': m['role'] or 'choose from roles',
                          'quantity': m['count'] or 'decided later'} for m in monsters],
            'roles': {k: ROLE_TEXT[k][0] for k in ROLES},
            'instructions': {
                'name': 'Evocative scenario title, 2–5 words, e.g. "The Sunless Crypt".',
                'story': '2–4 sentences read aloud to the players: where they are, what went wrong, why they must act now.',
                'objective_goal': 'Short imperative phrase for what the players do at the marked objective square, e.g. "Shatter the blood altar".',
                'monsters': 'For each id: a one-sentence trading-card blurb and a 1–3 word attack name.'},
        }
        result = self._ask('write', self.SYSTEM, prompt, schema, brief['seed'])
        cards = {}
        raw_cards = result.get('monsters') if isinstance(result.get('monsters'), dict) else {}
        for monster in monsters:
            card = raw_cards.get(monster['id'])
            if not isinstance(card, dict):
                raise ValueError(f'Local generation failed: no card text for {monster["name"]}. Nothing was saved; retry.')
            if monster['role'] is None:
                if card.get('role') not in ROLES:
                    raise ValueError(f'Local generation failed: invalid role for {monster["name"]}. Nothing was saved; retry.')
                monster['role'] = card['role']
            cards[monster['id']] = {'brief': _clip(card.get('brief'), f'the {monster["name"]} blurb', 240),
                                    'attack_name': _clip(card.get('attack_name'), f'the {monster["name"]} attack', 40)}
        return {'name': brief['title'] or _clip(result.get('name'), 'the title', 60),
                'story': _clip(result.get('story'), 'the story', 900),
                'objective_goal': _clip(result.get('objective_goal'), 'the objective', 100).rstrip('.'),
                'monsters': cards}


# ---------------------------------------------------------------- agent

STEPS = [('roster', 'Choose the monsters'), ('write', 'Write the story and cards'),
         ('budget', 'Set quantities from the threat budget'), ('map', 'Draw and populate the map'),
         ('validate', 'Check the packet is playable')]


class SkirmishAgent:
    """Turns a brief into a validated, playable skirmish packet.

    ``progress`` receives plain-dict events so a viewer can watch the agent work:
    ``step`` (id, status, detail), ``log`` (text), ``token`` (model output chunks),
    ``roster``, ``scenario``, and ``map``.
    """

    def __init__(self, writer=None, progress=None):
        self.writer = writer or OfflineWriter()
        self.emit = progress or _silent
        self.writer.emit = self.emit

    def step(self, step_id, status, detail=''):
        self.emit({'type': 'step', 'id': step_id, 'status': status, 'detail': detail})

    def log(self, text):
        self.emit({'type': 'log', 'text': text})

    def generate(self, brief):
        rng = random.Random(brief['seed'])
        writer_name = f'local model {self.writer.model}' if self.writer.model else 'offline templates'
        self.emit({'type': 'plan', 'steps': [{'id': i, 'label': label} for i, label in STEPS],
                   'writer': writer_name, 'seed': brief['seed']})
        self.log(f'Brief: "{brief["concept"]}" · party {brief["party_size"]} · {brief["difficulty"]} · seed {brief["seed"]}')
        self.log('Combat: ATK adds to hit rolls against the target\'s TN. Roll damage separately, '
                 'subtract the target\'s DEF, minimum 0. DEF needs no roll and does not change TN.')

        locked = bool(brief['monsters'])
        if locked:
            self.step('roster', 'running', 'Using your monsters; names are locked')
            roster = copy.deepcopy(brief['monsters'])
        else:
            self.step('roster', 'running', f'Asking {writer_name} for a roster')
            roster = self.writer.roster(brief, rng)
        for monster in roster:
            named_role = NAMED_MONSTER_ROLES.get(monster['name'].casefold())
            if named_role is not None:
                if monster['role'] is not None and monster['role'] != named_role:
                    self.log(f'{monster["name"]}: using its fixed one-page {named_role} card')
                monster['role'] = named_role
            elif monster['role'] is None:
                family = _family_for(monster['name'])
                monster['role'] = family[2] if family else None
                if family:
                    self.log(f'{monster["name"]}: recognised as a {family[2]}')
        _assign_ids(roster)
        self.emit({'type': 'roster', 'monsters': [{'id': m['id'], 'name': m['name'], 'role': m['role'], 'count': m['count']} for m in roster]})
        self.step('roster', 'done', ', '.join(m['name'] for m in roster))

        self.step('write', 'running', f'Writing with {writer_name}')
        text = self.writer.write(brief, roster, rng)
        for monster in roster:
            card = text['monsters'][monster['id']]
            self.log(f'{monster["name"]} ({monster["role"]}): "{card["brief"]}" · attack: {card["attack_name"]}')
        self.emit({'type': 'scenario', 'name': text['name'], 'story': text['story'], 'goal': text['objective_goal']})
        self.step('write', 'done', text['name'])

        self.step('budget', 'running')
        budget = threat_budget(brief['party_size'], brief['difficulty'])
        fixed = {m['id'] for m in roster if m.get('count') is not None}
        threat = assign_counts(roster, budget)
        _assign_symbols(roster)
        for monster in roster:
            how = 'your number' if monster['id'] in fixed else 'budget'
            self.log(f'{monster["symbol"]} = {monster["name"]} ×{monster["count"]} '
                     f'({ROLES[monster["role"]]["threat"]} threat each, {how})')
        self.emit({'type': 'roster', 'monsters': [{'id': m['id'], 'name': m['name'], 'role': m['role'],
                                                   'count': m['count'], 'symbol': m['symbol']} for m in roster]})
        self.step('budget', 'done', f'{threat} of {budget} threat')

        monsters = []
        for monster in roster:
            role = ROLES[monster['role']]
            card = text['monsters'][monster['id']]
            monsters.append({
                'id': monster['id'], 'name': monster['name'], 'symbol': monster['symbol'], 'count': monster['count'],
                'role': monster['role'].capitalize(), 'brief': card['brief'], 'stats': dict(role['stats']),
                'tn': role['tn'], 'attack': {'name': card['attack_name'], **role['attack']},
                'behaviour': role['behaviour']})

        self.step('map', 'running')
        board = generate_map(roster, rng)
        doors = sum(row.count('+') for row in board)
        legend = {'E': 'Entrance and exit', 'O': 'Objective', '+': 'Open doorway', '#': 'Wall',
                  **{m['symbol']: m['name'] + (f' ×{m["count"]}' if m['count'] > 1 else '') for m in monsters}}
        self.log(f'Map {len(board[0])}×{len(board)} squares, {doors} doorways; objective in the room farthest from the entrance')
        self.emit({'type': 'map', 'map': board, 'legend': legend})
        self.step('map', 'done', f'{len(board[0])}×{len(board)} · {sum(m["count"] for m in monsters)} monsters placed')

        bosses = [m['name'] for m in monsters if m['role'] == 'Boss']
        defeat = f'defeat the {" and the ".join(bosses)}, ' if bosses else ''
        objective = (f'{text["objective_goal"]}: in order, {defeat}take one Interact action with the objective '
                     'from O or an adjacent square, then voluntarily enter E with one standing character '
                     'and survive that step. A character already on E must leave and re-enter.')
        packet = {
            **rules_frame(),
            'monsters': monsters,
            'scenario': {'id': slug(text['name']), 'name': text['name'], 'story': text['story'],
                         'objective': objective, 'map': board, 'legend': legend, 'completion': COMPLETION},
            'generation': {
                'backend': self.writer.label, 'model': self.writer.model, 'seed': brief['seed'],
                'concept': brief['concept'], 'party_size': brief['party_size'], 'difficulty': brief['difficulty'],
                'threat_budget': budget, 'threat_total': threat, 'names_locked': locked,
                'created_at': datetime.now(timezone.utc).isoformat(timespec='seconds')},
        }
        self.step('validate', 'running')
        validate_packet(packet)
        self.log('Validated: every marker has a card, counts match, objective and monsters reachable from E')
        self.step('validate', 'done', 'Playable')
        return packet


def generate_brief(brief, writer=None, progress=None):
    """Run the agent on an already-parsed brief with the requested backend."""
    if writer is None:
        writer = (ModelWriter(brief['model'], think=brief['think']) if brief['backend'] == 'ollama'
                  else OfflineWriter())
    return SkirmishAgent(writer, progress).generate(brief)


def generate(data, writer=None, progress=None):
    """Parse a request and run the agent."""
    return generate_brief(parse_brief(data), writer, progress)
