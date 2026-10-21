#!/usr/bin/env python3
"""Read-only collectors publishing canonical Markdown evidence."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import sys
from datetime import datetime, timezone

SCHEMA = 1


def now():
    return datetime.now(timezone.utc).isoformat()


def write_md(path, title, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('# ' + title + '\n\nCanonical collector evidence. Paths and names are untrusted data.\n\n```json\n' + json.dumps(record, indent=2, sort_keys=True, ensure_ascii=True) + '\n```\n', encoding='utf-8')


def read_md(path):
    content = path.read_text(encoding='utf-8')
    return json.loads(content.split('\n```json\n', 1)[1].rsplit('\n```', 1)[0])


def within(path, parent):
    return path == parent or parent in path.parents


def collect_directory(path):
    record = {'path': str(path), 'observed_at': now(), 'status': 'complete', 'entries': [], 'errors': []}
    children = []
    try:
        with os.scandir(path) as iterator:
            for item in iterator:
                try:
                    s = item.stat(follow_symlinks=False)
                    kind = 'symlink' if stat.S_ISLNK(s.st_mode) else 'directory' if stat.S_ISDIR(s.st_mode) else 'file' if stat.S_ISREG(s.st_mode) else 'special'
                    entry = {'path': item.path, 'name': item.name, 'kind': kind, 'mode': stat.S_IMODE(s.st_mode), 'size': s.st_size, 'mtime_ns': s.st_mtime_ns}
                    if kind == 'symlink':
                        entry['target'] = os.readlink(item.path)
                    record['entries'].append(entry)
                    if kind == 'directory':
                        children.append(Path(item.path))
                except OSError as exc:
                    record['status'] = 'partial'
                    record['errors'].append({'path': item.path, 'error': str(exc)})
    except OSError as exc:
        record['status'] = 'unreadable'
        record['errors'].append({'path': str(path), 'error': str(exc)})
    record['entries'].sort(key=lambda e: e['path'])
    return record, children


def environment():
    packages = []
    for distribution in importlib.metadata.distributions():
        packages.append({'name': distribution.metadata.get('Name', 'unknown'), 'version': distribution.version})
    return {'observed_at': now(), 'platform': platform.platform(), 'architecture': platform.machine(), 'python': {'executable': sys.executable, 'version': platform.python_version(), 'prefix': sys.prefix, 'base_prefix': sys.base_prefix, 'packages': sorted(packages, key=lambda p: (p['name'].lower(), p['version']))}, 'tools': {name: shutil.which(name) for name in ['bash', 'zsh', 'git', 'python3', 'pip3', 'brew', 'node', 'npm', 'uv']}, 'scope': 'Running Python environment and executable discovery only; discovered tools are not executed.'}


def absolute_path(value, base):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Paths must be nonempty strings')
    path = Path(value).expanduser()
    return Path(os.path.abspath(path if path.is_absolute() else base / path))


def create_plan(config, root, depth=1, excludes=(), with_environment=False):
    """Pre-list metadata only; a plan never creates a snapshot."""
    config = Path(config).expanduser().resolve()
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise ValueError('Scan root must be an existing directory')
    if depth < 1:
        raise ValueError('Pre-list depth must be at least 1')
    storage = config.parent / 'snapshots'
    excluded = sorted(set([str(absolute_path(p, root)) for p in excludes] +
                          [str(config), str(storage)]))
    if any(within(root, Path(p)) for p in excluded):
        raise ValueError('An exclusion must not contain the scan root')
    plan = {'schema': 1, 'created_at': now(), 'root': str(root),
            'output': str(storage / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')),
            'environment': with_environment, 'exclude': excluded,
            'prelist_depth': depth, 'entries': [], 'coverage_issues': [],
            'instructions': 'Edit root, output, environment, exclude, or entry enabled flags. '
            'Disabled entries exclude their entire subtree. All other current paths, including '
            'new paths and descendants beyond the pre-list depth, are scanned recursively. '
            'Deleting an entry does NOT exclude it. Relative entry/exclude paths use root; '
            'relative root/output paths use this config folder. Regenerate the plan when changing root.'}
    pending = [(root, 0)]
    while pending:
        directory, level = pending.pop()
        record, children = collect_directory(directory)
        if record['status'] != 'complete':
            plan['coverage_issues'].append({'path': str(directory), 'status': record['status'], 'errors': record['errors']})
        for entry in record['entries']:
            enabled = not any(within(Path(entry['path']), Path(p)) for p in excluded)
            plan['entries'].append({'path': entry['path'], 'kind': entry['kind'], 'enabled': enabled})
        if level + 1 < depth:
            pending.extend((p, level + 1) for p in sorted(children, reverse=True)
                           if not any(within(p, Path(e)) for e in excluded))
    plan['entries'].sort(key=lambda entry: entry['path'])
    config.parent.mkdir(parents=True, exist_ok=True)
    with config.open('x', encoding='utf-8') as stream:
        json.dump(plan, stream, indent=2, ensure_ascii=True)
        stream.write('\n')
    return plan


def read_plan(config, require_new_output=True):
    config = Path(config).expanduser().resolve()
    plan = json.loads(config.read_text(encoding='utf-8'))
    if not isinstance(plan, dict) or type(plan.get('schema')) is not int or plan['schema'] != 1:
        raise ValueError('Unsupported scan configuration')
    root = absolute_path(plan['root'], config.parent).resolve()
    output = absolute_path(plan['output'], config.parent).resolve()
    if type(plan.get('environment')) is not bool:
        raise ValueError('environment must be true or false')
    if not isinstance(plan.get('exclude'), list) or not isinstance(plan.get('entries'), list):
        raise ValueError('exclude and entries must be lists')
    excludes = [absolute_path(p, root) for p in plan['exclude']]
    for entry in plan['entries']:
        if not isinstance(entry, dict) or type(entry.get('enabled')) is not bool:
            raise ValueError('Every pre-list entry needs an enabled boolean')
        path = absolute_path(entry['path'], root)
        if path == root or not within(path, root):
            raise ValueError(f'Pre-list entry is outside root: {path}; regenerate the plan for a new root')
        if not entry['enabled']:
            excludes.append(path)
    excludes = sorted(set(excludes + [config]))
    if not root.is_dir():
        raise ValueError('Scan root must be an existing directory')
    if within(root, output):
        raise ValueError('Snapshot output must not contain the scan root')
    if any(within(root, p) for p in excludes):
        raise ValueError('An exclusion must not contain the scan root')
    if require_new_output and output.exists():
        raise ValueError('Snapshot output already exists; edit output to a new folder')
    return root, output, excludes, plan['environment']


def preview_plan(config, depth=2):
    """Probe selected directory listings to a bounded depth using collector permissions."""
    if depth < 1:
        raise ValueError('Preview depth must be at least 1')
    root, output, excludes, env = read_plan(config, require_new_output=False)
    report = {'observed_at': now(), 'root': str(root), 'output': str(output),
              'output_exists': output.exists(), 'environment': env,
              'exclusions': [str(p) for p in excludes], 'depth': depth,
              'read_method': 'Directory listings and metadata only; symlinks are not followed.',
              'limits': 'Only listed directories are probed. Deeper access is unknown until scanning. '
              'Results reflect this collector process at this time, not another agent or terminal.',
              'directories': [], 'entries': []}
    pending = [(root, 0)]
    while pending:
        directory, level = pending.pop()
        record, children = collect_directory(directory)
        report['directories'].append({'path': str(directory), 'status': record['status'], 'errors': record['errors']})
        def skipped(path):
            return within(path, output) or any(within(path, p) for p in excludes)
        for entry in record['entries']:
            path = Path(entry['path'])
            action = ('excluded' if skipped(path) else
                      'record_link_only' if entry['kind'] == 'symlink' else
                      'recurse' if entry['kind'] == 'directory' else 'record_metadata')
            report['entries'].append({'path': str(path), 'kind': entry['kind'], 'action': action})
        if level + 1 < depth:
            pending.extend((p, level + 1) for p in sorted(children, reverse=True) if not skipped(p))
    return report


def scan(root, output, excludes=(), with_environment=False, progress=None):
    root, output = Path(root).resolve(), Path(output).resolve()
    if not root.is_dir():
        raise ValueError('Scan root must be an existing directory')
    if within(root, output):
        raise ValueError('Snapshot output must not contain the scan root')
    excluded = sorted(set(str(absolute_path(str(p), root)) for p in excludes))
    if any(within(root, Path(p)) for p in excluded):
        raise ValueError('An exclusion must not contain the scan root')
    output.mkdir(parents=True, exist_ok=False)
    manifest = {'schema': SCHEMA, 'root': str(root), 'started_at': now(), 'finished_at': None, 'status': 'collecting', 'exclusions': excluded, 'directories': []}
    write_md(output / 'snapshot.md', 'Snapshot', manifest)
    coverage = {'root': str(root), 'exclusions': excluded, 'output_exclusion': str(output),
                'directory_counts': {'complete': 0, 'partial': 0, 'unreadable': 0},
                'entries_recorded': 0, 'issues': [],
                'read_method': 'Directory listings and file metadata; symlinks are not followed; file contents are not read.'}
    pending = [root]
    index = ['# Filesystem snapshot', '', f'Scan root: `{root}`', '',
             '[Coverage report](coverage.md)', '', '## Folder listings', '']
    while pending:
        directory = pending.pop()
        record, children = collect_directory(directory)
        def skipped(p):
            return within(Path(p), output) or any(within(Path(p), Path(e)) for e in excluded)
        record['entries'] = [e for e in record['entries'] if not skipped(e['path'])]
        coverage['directory_counts'][record['status']] += 1
        coverage['entries_recorded'] += len(record['entries'])
        if record['status'] != 'complete':
            coverage['issues'].append({'path': str(directory), 'status': record['status'], 'errors': record['errors']})
        name = 'directories/' + hashlib.sha256(str(directory).encode()).hexdigest() + '.md'
        write_md(output / name, 'Directory evidence', record)
        manifest['directories'].append(name)
        label = json.dumps(str(directory), ensure_ascii=True).replace('[', '\\[').replace(']', '\\]')
        index.append(f'- [{label}]({name}) — {record["status"]}')
        if progress is not None:
            progress(len(manifest['directories']))
        pending.extend(sorted((p for p in children if not skipped(p)), reverse=True))
    if with_environment:
        write_md(output / 'environment.md', 'Environment evidence', environment())
    coverage['finished_at'] = now()
    coverage['status'] = 'incomplete' if coverage['issues'] else 'complete'
    write_md(output / 'coverage.md', 'Scan coverage report', coverage)
    (output / 'index.md').write_text('\n'.join(index) + '\n', encoding='utf-8')
    manifest.update(finished_at=coverage['finished_at'], status='complete', output_exclusion=str(output),
                    coverage_status=coverage['status'], coverage_report='coverage.md')
    write_md(output / 'snapshot.md', 'Snapshot', manifest)
    return manifest


def load_snapshot(folder):
    folder = Path(folder)
    meta = read_md(folder / 'snapshot.md')
    if meta['schema'] != SCHEMA or meta['status'] != 'complete':
        raise ValueError('Unsupported or unfinished snapshot')
    directories = {}
    for name in meta['directories']:
        path = (folder / name).resolve()
        if not within(path, folder.resolve()):
            raise ValueError('Invalid snapshot record path')
        record = read_md(path)
        directories[record['path']] = record
    entries = {e['path']: e for d in directories.values() for e in d['entries']}
    return meta, directories, entries


def known_absent(path, directories, entries, root):
    # Absence is evidence only when a complete ancestor listing proves it.
    cursor = Path(path)
    while str(cursor) != root:
        parent = directories.get(str(cursor.parent))
        if parent is not None:
            return parent['status'] == 'complete' and str(cursor) not in entries
        ancestor = entries.get(str(cursor.parent))
        if ancestor and ancestor['kind'] != 'directory':
            return True
        cursor = cursor.parent
        if cursor == cursor.parent:
            break
    return False


def signature(entry):
    keys = ['kind', 'mode', 'target'] if entry['kind'] == 'directory' else ['kind', 'mode', 'size', 'mtime_ns', 'target']
    return {key: entry.get(key) for key in keys}


def diff(before, after):
    bm, bd, be = load_snapshot(before)
    am, ad, ae = load_snapshot(after)
    if (bm['root'], bm['exclusions']) != (am['root'], am['exclusions']):
        raise ValueError('Snapshots must have the same root and exclusions')
    excluded = [Path(m['output_exclusion']) for m in (bm, am)]
    changes = []
    for path in sorted(be.keys() | ae.keys()):
        if any(within(Path(path), p) for p in excluded):
            continue
        old, new = be.get(path), ae.get(path)
        if old is None:
            status = 'added' if known_absent(path, bd, be, bm['root']) else 'unknown'
        elif new is None:
            status = 'removed' if known_absent(path, ad, ae, am['root']) else 'unknown'
        elif signature(old) != signature(new):
            status = 'modified'
        else:
            continue
        changes.append({'status': status, 'path': path, 'before': old, 'after': new})
    coverage = [{'snapshot': label, 'path': p, 'status': d['status'], 'errors': d['errors']} for label, ds in [('before', bd), ('after', ad)] for p, d in sorted(ds.items()) if d['status'] != 'complete']
    return {'schema': SCHEMA, 'compared_at': now(), 'before': str(before), 'after': str(after), 'changes': changes, 'coverage_issues': coverage, 'scope': 'Filesystem metadata only; no content recovery or environment comparison.'}


def terminal_path(prompt):
    value = input(prompt).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        value = value[1:-1]
    return absolute_path(value, Path.cwd()).resolve()


def snapshot_name():
    return datetime.now().astimezone().strftime('scan-%Y%m%d-%H%M%S-%f')


def interactive():
    """Destination-first terminal workflow. No writes until the user selects Run."""
    print('\nMac Ledger — save recursive folder listings as Markdown')
    print('Choose your records folder first, then the folder to scan. Q cancels at the menu.')
    print('Paths may be absolute, relative to this terminal, or start with ~. Ctrl+C cancels any prompt.')
    database = source = None
    name = snapshot_name()
    env = False
    try:
        while True:
            try:
                if database is None:
                    candidate = terminal_path('Save records in which database folder? ')
                    if candidate.exists() and not candidate.is_dir():
                        raise ValueError('The database path must be a folder')
                    database = candidate
                if source is None:
                    candidate = terminal_path('Which folder should be scanned recursively? ')
                    if not candidate.is_dir():
                        raise ValueError('The source must be an existing folder')
                    if within(candidate, database):
                        database = None
                        raise ValueError('The source cannot be inside the database folder; choose a separate records folder')
                    source = candidate
                output = database / name
                print(f'\nDatabase folder: {database}\nScan source:     {source}\nSnapshot saves:  {output}')
                print(f'Mode: {"Folder listings + Python environment" if env else "Folder listings only"}')
                print('All subfolders included; symlinks recorded without following; database folder excluded.')
                print('[D] Database  [P] Source path  [N] Snapshot name  [M] Mode  [R] Run  [Q] Quit')
                key = input('Choose a key: ').strip().lower()
                if key == 'q':
                    return
                if key == 'd':
                    database = source = None
                elif key == 'p':
                    source = None
                elif key == 'n':
                    candidate = input('Snapshot folder name (one name, no slashes): ').strip()
                    if not candidate or candidate in ('.', '..') or '/' in candidate or '\x00' in candidate:
                        raise ValueError('Enter a single folder name')
                    name = candidate
                elif key == 'm':
                    env = not env
                elif key == 'r':
                    if output.exists():
                        raise ValueError('That snapshot already exists. Press N to choose a new name')
                    print(f'\nScanning {source}\nSaving Markdown to {output}', flush=True)
                    def progress(count):
                        if count == 1 or count % 100 == 0:
                            print(f'  {count} folders recorded...', flush=True)
                    result = scan(source, output, [str(database)], env, progress=progress)
                    print(f'\nSaved {len(result["directories"])} folder listings. Coverage: {result["coverage_status"]}.')
                    print(f'Open: {output / "index.md"}\nAccess report: {output / "coverage.md"}')
                    name = snapshot_name()
                else:
                    print('Use D, P, N, M, R, or Q.')
            except (OSError, ValueError) as exc:
                print(f'Cannot proceed: {exc}')
    except (EOFError, KeyboardInterrupt):
        print('\nStopped. Any interrupted snapshot is left unfinished and cannot be compared.')


def main():
    if len(sys.argv) == 1:
        interactive()
        return
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('menu', help='Open the interactive destination-first terminal menu')
    p = commands.add_parser('plan', help='Save an editable JSON pre-list before scanning')
    p.add_argument('config')
    scope = p.add_mutually_exclusive_group(required=True)
    scope.add_argument('--root', help='Folder to scan')
    scope.add_argument('--whole-disk', action='store_true', help='Use / as the scan root')
    p.add_argument('--depth', type=int, default=1, help='Folder levels to pre-list (default: 1)')
    p.add_argument('--exclude', action='append', default=[])
    p.add_argument('--environment', action='store_true')
    r = commands.add_parser('run', help='Execute an edited scan configuration')
    r.add_argument('config')
    r.add_argument('--dry-run', action='store_true', help='Validate and display scope without scanning')
    v = commands.add_parser('preview', help='Probe directory access and show how the edited scope will be read')
    v.add_argument('config')
    v.add_argument('--depth', type=int, default=2, help='Folder levels to probe (default: 2)')
    v.add_argument('--output', help='Save a new Markdown scope report instead of printing JSON')
    s = commands.add_parser('scan')
    s.add_argument('root'); s.add_argument('output')
    s.add_argument('--exclude', action='append', default=[])
    s.add_argument('--environment', action='store_true')
    d = commands.add_parser('diff')
    d.add_argument('before'); d.add_argument('after'); d.add_argument('--output')
    q = commands.add_parser('query', help='Literal search of Markdown evidence only')
    q.add_argument('snapshot'); q.add_argument('text')
    args = parser.parse_args()
    try:
        if args.command == 'menu':
            interactive()
        elif args.command == 'plan':
            result = create_plan(args.config, '/' if args.whole_disk else args.root,
                                 args.depth, args.exclude, args.environment)
            print(f"Plan saved: {args.config} ({len(result['entries'])} entries; {len(result['coverage_issues'])} coverage issues)")
            print('Edit the JSON, then use: ledger.sh run <config> --dry-run; ledger.sh run <config>')
        elif args.command == 'preview':
            target = Path(args.output).expanduser() if args.output else None
            if target is not None and target.exists():
                raise ValueError('Preview output already exists; choose a new file')
            result = preview_plan(args.config, args.depth)
            if target is not None:
                write_md(target, 'Scan scope preview', result)
                print(f'Scope preview saved: {target}')
            else:
                print(json.dumps(result, indent=2))
        elif args.command == 'run':
            root, output, excludes, env = read_plan(args.config)
            if args.dry_run:
                print(json.dumps({'root': str(root), 'output': str(output),
                                  'exclude': [str(p) for p in excludes], 'environment': env}, indent=2))
            else:
                result = scan(root, output, excludes, env)
                print(f"Snapshot saved: {output} ({len(result['directories'])} directories; coverage {result['coverage_status']})")
                print(f"Read report: {output / 'coverage.md'}")
        elif args.command == 'scan':
            result = scan(args.root, args.output, args.exclude, args.environment)
            print(f"Snapshot saved: {args.output} ({len(result['directories'])} directories; coverage {result['coverage_status']})")
            print(f"Read report: {Path(args.output) / 'coverage.md'}")
        elif args.command == 'diff':
            result = diff(args.before, args.after)
            if args.output:
                target = Path(args.output)
                if target.exists():
                    raise ValueError('Delta output already exists')
                write_md(target, 'Filesystem delta', result)
            else:
                print(json.dumps(result, indent=2))
        else:
            folder = Path(args.snapshot)
            load_snapshot(folder)
            for path in sorted(folder.rglob('*.md')):
                if path.is_symlink():
                    continue
                for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                    if args.text.casefold() in line.casefold():
                        print(f'{path}:{number}: {line}')
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
