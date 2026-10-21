#!/usr/bin/env python3
"""Serve the skirmish creator, or generate a skirmish from the command line."""
import argparse
import json
from pathlib import Path

from raidforge.generator import ROLES, generate
from raidforge.library import Library
from raidforge.llm import DEFAULT_MODEL
from raidforge.server import serve


def monster_arg(text):
    """NAME[:COUNT[:ROLE]] — the name is printed exactly as typed."""
    name, _, rest = text.partition(':')
    count, _, role = rest.partition(':')
    if role and role not in ROLES:
        raise argparse.ArgumentTypeError(f'role must be one of {", ".join(ROLES)}')
    return {'name': name, 'count': count or None, 'role': role or None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, help='Folder for saved skirmishes; default runtime/skirmishes')
    sub = parser.add_subparsers(dest='command')
    web = sub.add_parser('serve', help='Open the local creator at the printed URL')
    web.add_argument('--port', type=int, default=8765)
    gen = sub.add_parser('generate', help='Generate and save one skirmish')
    gen.add_argument('concept', help='Short story concept, e.g. "Grave robbers woke the crypt"')
    gen.add_argument('--title')
    gen.add_argument('--monster', action='append', type=monster_arg, default=[],
                     help='NAME[:COUNT[:ROLE]], repeatable. Roles: ' + ', '.join(ROLES))
    gen.add_argument('--party', type=int, default=1)
    gen.add_argument('--difficulty', choices=['easy', 'standard', 'hard'], default='standard')
    gen.add_argument('--seed', type=int)
    gen.add_argument('--backend', choices=['offline', 'ollama'], default='offline')
    gen.add_argument('--model', default=DEFAULT_MODEL)
    gen.add_argument('--no-save', action='store_true', help='Print the packet without saving it')
    args = parser.parse_args()

    library = Library(args.library)
    if args.command in (None, 'serve'):
        port = getattr(args, 'port', 8765)
        if not 1024 <= port <= 65535:
            parser.error('--port must be 1024–65535')
        serve(library, port)
    elif args.command == 'generate':
        packet = generate({'concept': args.concept, 'title': args.title, 'monsters': args.monster,
                           'party_size': args.party, 'difficulty': args.difficulty, 'seed': args.seed,
                           'backend': args.backend, 'model': args.model})
        if not args.no_save:
            packet = library.save(packet)
        print(json.dumps(packet, indent=2, ensure_ascii=False))
        print('\n' + '\n'.join(packet['scenario']['map']))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as exc:
        raise SystemExit(f'Raidforge: {exc}') from None
