"""Command-line interface for the stand-alone monster studio.

Card generation uses a local Ollama model. Level tables, build validation,
the rules reference, and matchup arithmetic also work without Ollama.
"""
import argparse
import json
import math
import shlex
import sys
from pathlib import Path

from .ollama import OllamaClient, models, DEFAULT_MODEL
from . import roles, studio, markdown
from .level import DEFAULT_RULES, ENEMIES, Rules, character, matchup

DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / 'runtime' / 'monsters' / 'roster.md'


def ask(text, default=''):
    value = input(f'{text}{f" [{default}]" if default != "" else ""}: ').strip()
    return value or str(default)


def interactive_args():
    """One short setup; advanced flags use the same parser as scripted runs."""
    print('\n=== Monster Studio · explore → develop → refine ===')
    status = models()
    if not status['available'] or not status['models']:
        raise ValueError(status.get('message') if not status['available'] else 'No local models installed')
    names = status['models']
    for index, name in enumerate(names, 1):
        print(f'{index}. {name}')
    default = names.index(DEFAULT_MODEL) + 1 if DEFAULT_MODEL in names else 1
    while True:
        choice = ask('Model number', default)
        if choice.isdigit() and 1 <= int(choice) <= len(names):
            model = names[int(choice) - 1]
            break
        print('Enter a number from the list.')
    while True:
        role = ask(f'Role ({", ".join(roles.ROLES)})', 'guard').lower()
        if role in roles.ROLES:
            break
        print('Choose a listed role.')
    while True:
        level = ask('Level (1–5)', '1')
        if level in ('1', '2', '3', '4', '5'):
            break
        print('Choose a level from 1 to 5.')
    concept = ''
    while not concept:
        concept = ask('Creature concept / brief')
    print('Optional flags: --count 2 --theme "old growth" --atk-role damage --level5-die 8 --no-think')
    while True:
        try:
            options = shlex.split(ask('Advanced flags (blank = defaults)'))
        except ValueError as exc:
            print(exc)
            continue
        return parser().parse_args(['build', role, '--model', model, '--level', level,
                                    '--concept', concept, *options])


def positive_int(text):
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError('must be at least 1')
    return value


def rule_options(command):
    command.add_argument('--atk-role', choices=('special', 'hit', 'damage'),
                         default=DEFAULT_RULES.atk_role,
                         help='ATK is reserved for special moves, adds to hit, or adds to damage (default: special)')
    command.add_argument('--bp-curve', choices=('linear', 'early'), default=DEFAULT_RULES.bp_curve,
                         help='linear: 0,1,2,3,4; early: 0,2,3,4,5 (default: linear)')
    command.add_argument('--level5-die', type=int, choices=(5, 8), default=DEFAULT_RULES.level5_die,
                         help='Level 5 die and die invariant ceiling (default: 5)')


def build_options(command):
    command.add_argument('--spend', action='append', default=[], metavar='STAT=N',
                         help='Spend N BP on a stat; repeat to allocate more stats')
    command.add_argument('--learn', action='append', default=[], metavar='NAME:COST',
                         help='Record a move/spell at its printed 2–4 BP cost; repeat as needed')


def selected_rules(args):
    return Rules(args.atk_role, args.bp_curve, args.level5_die)


def allocation(args):
    boosts, learned = {}, []
    for entry in args.spend:
        stat, separator, amount = entry.partition('=')
        if not separator:
            raise ValueError('--spend expects STAT=N, e.g. --spend atk=1')
        key = stat.strip().lower()
        value = int(amount)
        if value < 0:
            raise ValueError('BP increases cannot be negative')
        boosts[key] = boosts.get(key, 0) + value
    for entry in args.learn:
        name, separator, cost = entry.rpartition(':')
        if not separator:
            raise ValueError('--learn expects NAME:COST, e.g. --learn "Flame:2"')
        learned.append((name, int(cost)))
    return boosts, learned


def show_levels(args):
    rules = selected_rules(args)
    boosts, learned = allocation(args)
    if args.level is None and (boosts or learned):
        raise ValueError('Choose one level when spending BP: levels 3 --spend atk=1')
    levels = [args.level] if args.level is not None else range(1, 6)
    profiles = [character(number, rules, boosts, learned) for number in levels]
    if args.json:
        print(json.dumps(profiles, indent=2))
        return
    print(rules.summary)
    print(' L  HP ATK SPD DEF MAGIC TN  Die  BP pool/left')
    for row in profiles:
        s = row['stats']
        print(f'{row["level"]:2} {s["hp"]:3} {s["atk"]:3} {s["spd"]:3} {s["def"]:3}'
              f' {s["magic"]:5} {row["tn"]:2}  D{row["die"]:<2}'
              f'  {row["bp"]["pool"]}/{row["bp"]["remaining"]}')
        for ability in row['learned']:
            print(f'   Learned: {ability["name"]} ({ability["cost"]} BP; effects use its printed rules)')
    print('All five invariants pass. Universal actions: Punch, Kick, Push, Interact.')


def show_balance(args):
    rules = selected_rules(args)
    boosts, learned = allocation(args)
    attacker = character(args.level, rules, boosts, learned)
    overrides = {'tn': args.tn, 'def': args.defence, 'hp': args.hp}
    if any(value is not None for value in overrides.values()) and args.enemy is None:
        raise ValueError('Choose --enemy before overriding its TN, DEF, or HP')
    enemies = [ENEMIES[args.enemy]] if args.enemy else ENEMIES.values()
    results = []
    for enemy in enemies:
        target = {**enemy, **{key: value for key, value in overrides.items() if value is not None}}
        result = matchup(attacker, target, action=args.action, adjacent=args.adjacent)
        # JSON has no Infinity. A null turn estimate accompanies killable=false.
        if not math.isfinite(result['estimated_turns']):
            result['estimated_turns'] = None
        results.append(result)
    if args.json:
        print(json.dumps({'attacker': attacker, 'matchups': results}, indent=2, allow_nan=False))
        return
    print(rules.summary)
    print(f'Level {args.level} · {args.action} · one attack per turn')
    print('Enemy      TN DEF HP  Die   Hit %  Dmg/hit Dmg/turn  Est. turns')
    for row in results:
        turns = f'{row["estimated_turns"]:.2f}' if row['killable'] else 'unkillable'
        print(f'{row["enemy"]:<10} {row["target_tn"]:2} {row["effective_def"]:3}'
              f' {row["target_hp"]:2}  D{row["die"]:<2}'
              f' {100 * row["hit_probability"]:7.2f} {row["damage_on_hit"]:8.3f}'
              f' {row["damage_per_turn"]:8.3f}  {turns}')
    print('Est. turns = target HP / expected damage per turn; ignores retaliation and movement.')
    print('Base uses the level die. Punch and Kick always use D3; adjacent Kick adds 1 target DEF.')


def parser():
    cli = argparse.ArgumentParser(description='Monster Studio: Law of Level rules and local-model monster cards.')
    sub = cli.add_subparsers(dest='command')
    sub.add_parser('models', help='List installed local Ollama models')
    sub.add_parser('rules', help='Print the Law of Level reference and open decisions (no model needed)')
    levels = sub.add_parser('levels', help='Show level stats and validate BP spending (no model needed)')
    levels.add_argument('level', nargs='?', type=int, choices=range(1, 6))
    levels.add_argument('--json', action='store_true')
    rule_options(levels)
    build_options(levels)
    balance = sub.add_parser('balance', help='Calculate damage and estimated turns against the roster (no model needed)')
    balance.add_argument('--level', type=int, choices=range(1, 6), default=1)
    balance.add_argument('--enemy', choices=tuple(ENEMIES), help='Default: all three reference enemies')
    balance.add_argument('--tn', type=int, choices=range(3, 7), help='Override enemy TN')
    balance.add_argument('--def', dest='defence', type=int, help='Override enemy DEF')
    balance.add_argument('--hp', type=positive_int, help='Override enemy HP')
    balance.add_argument('--action', choices=('base', 'punch', 'kick'), default='base')
    balance.add_argument('--adjacent', action='store_true', help='Apply the adjacent Kick cover rule')
    balance.add_argument('--json', action='store_true')
    rule_options(balance)
    build_options(balance)
    build = sub.add_parser('build', help='Generate and pick one or more monster cards')
    build.add_argument('role', choices=roles.ROLES, help='Monster role to design')
    build.add_argument('--concept', default='', help='Story concept the card should belong to')
    build.add_argument('--theme', default='', help='Optional flavour theme keyword')
    build.add_argument('--count', type=positive_int, default=1, help='How many cards to build one after another')
    build.add_argument('--level', type=int, choices=range(1, 6), default=1,
                       help='Level for every generated card, regardless of role (default: 1)')
    rule_options(build)
    build.add_argument('--model', default=DEFAULT_MODEL, help=f'Installed local model (default: {DEFAULT_MODEL})')
    build.add_argument('--output', type=Path, default=DEFAULT_OUTPUT, help='Markdown file to write')
    build.add_argument('--seed', type=int, default=None, help='Fixed seed for repeatability')
    build.add_argument('--think', action=argparse.BooleanOptionalAction, default=None,
                       help='Thinking is automatic when supported; --no-think disables it')
    build.add_argument('--context', type=int, default=None, help='Optional model context window (at least 1024)')
    return cli


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if not args.command:
            args = interactive_args()
        if args.command == 'rules':
            print(Path(__file__).with_name('LAW-OF-LEVEL.md').read_text(encoding='utf-8'))
            return 0
        if args.command == 'levels':
            show_levels(args)
            return 0
        if args.command == 'balance':
            show_balance(args)
            return 0
        if args.command == 'models':
            status = models()
            if not status['available']:
                raise ValueError(status['message'])
            if not status['models']:
                raise ValueError('Ollama is running but has no installed local models')
            print('\n'.join(status['models']))
            return 0
        import secrets
        if not args.concept:
            raise ValueError('Give a creature brief with --concept, or run without arguments for setup')
        seed = args.seed if args.seed is not None else secrets.randbelow(2**31)
        rules = selected_rules(args)
        print(f'{rules.summary}\nModel: {args.model} · Seed: {seed}')
        client = OllamaClient(args.model, think=args.think, context_window=args.context)
        session = studio.Studio(client, seed, level=args.level, rules=rules,
                                progress=lambda m: print(m, file=sys.stderr, flush=True))
        cards = session.build(args.role, args.concept, args.theme, count=args.count)
        path = args.output
        path.parent.mkdir(parents=True, exist_ok=True)
        document = markdown.render_document(cards, title=f'{args.role.capitalize()} Roster')
        path.write_text(document, encoding='utf-8')
    except (ValueError, OSError, RuntimeError) as exc:
        print(f'Monster studio: {exc}', file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print('\nMonster studio: cancelled; nothing written.', file=sys.stderr)
        return 130

    print(f'\nWrote {path} ({len(cards)} card{"s" if len(cards) != 1 else ""}).')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
