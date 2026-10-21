"""World settings and read-only canon indexing, shared with the growth worker."""
import hashlib
import json
import os
import re
import sqlite3
import stat
import threading
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

DB_PATH = Path(__file__).resolve().parent / 'data' / 'world.sqlite3'
LOCK = threading.RLock()
CRS = ['0', '1/8', '1/4', '1/2'] + [str(n) for n in range(1, 31)]
FIELDS = {
    'world': ['seed', 'tone', 'geography', 'factions', 'canon_constraints'],
    'region': ['geography', 'climate'], 'city': ['population', 'economy', 'factions'],
    'district': ['purpose'], 'town': ['population', 'economy'],
    'village': ['population', 'livelihood'], 'woods': ['terrain', 'hazards'],
    'cave_system': ['entrances', 'hazards'], 'building': ['purpose', 'owner'],
    'npc': ['occupation', 'motives', 'schedule'], 'creature': ['challenge_rating', 'habitat'],
}
SCHEMAS = {kind: {'type': 'object', 'required': ['id', 'name', 'kind'] + fields,
    'properties': {k: {'type': 'string'} for k in ['id', 'name', 'kind', 'parent', 'description'] + fields}}
    for kind, fields in FIELDS.items()}
for kind, schema in SCHEMAS.items():
    schema['properties']['kind'] = {'type': 'string', 'enum': [kind]}
    schema['properties']['relationships'] = {'type': 'array', 'items': {'type': 'string'}}
SCHEMAS['creature']['properties']['challenge_rating']['enum'] = CRS


def connect():
    db = sqlite3.connect(DB_PATH)
    db.execute('CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    return db


def read_state(db, key, fallback):
    row = db.execute('SELECT value FROM state WHERE key=?', (key,)).fetchone()
    return json.loads(row[0]) if row else fallback


def put(db, key, value):
    db.execute('INSERT OR REPLACE INTO state VALUES (?, ?)', (key, json.dumps(value)))


def status():
    with LOCK, closing(connect()) as db:
        return {'settings': read_state(db, 'settings', None), 'graph': read_state(db, 'graph', None), 'schemas': SCHEMAS}


def text(data, key, limit=4000):
    value = data.get(key, '')
    if not isinstance(value, str) or len(value) > limit or '\x00' in value:
        raise ValueError(f'{key} must be text, at most {limit} characters.')
    return value.strip()


def save_settings(data):
    settings = {key: text(data, key) for key in ['name', 'seed', 'tone', 'geography', 'factions', 'canon_constraints']}
    settings['model'] = text(data, 'model', 200)
    if not settings['name'] or not settings['seed']:
        raise ValueError('Give the world a name and seed.')
    vault = Path(text(data, 'vault')).expanduser()
    folder = Path(text(data, 'folder')).expanduser()
    if not vault.is_absolute() or not folder.is_absolute():
        raise ValueError('Choose existing absolute vault and world folder paths.')
    vault = vault.resolve(strict=True)
    folder = folder.resolve(strict=True)
    if not vault.is_dir() or not folder.is_dir() or not folder.is_relative_to(vault):
        raise ValueError('The world folder must be inside the selected vault.')
    settings.update(vault=str(vault), folder=str(folder))
    with LOCK, closing(connect()) as db, db:
        previous = read_state(db, 'settings', {})
        growth = read_state(db, 'growth', {})
        if growth.get('status') == 'running':
            raise ValueError('Pause or stop world growth before changing settings.')
        settings['id'] = previous.get('id') if previous.get('folder') == str(folder) else uuid.uuid4().hex
        put(db, 'settings', settings)
        if previous.get('folder') != str(folder):
            db.execute("DELETE FROM state WHERE key IN ('graph', 'identities', 'growth')")
        elif growth.get('task'):
            task = growth['task']
            growth['task'] = {k: task[k] for k in ('id', 'kind', 'purpose', 'parent')} | {'phase': 'draft'}
            put(db, 'growth', growth)
    return status()


def open_root(folder):
    # Open every component without following symlinks, including ancestors replaced
    # after setup. All subsequent traversal is relative to these directory handles.
    path = Path(folder)
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_notes(root_fd):
    notes, warnings = [], []
    total_bytes = 0
    def walk(fd, prefix='', depth=0):
        nonlocal total_bytes
        if depth > 40:
            raise ValueError('World exceeds the 40-folder nesting limit.')
        for name in sorted(os.listdir(fd)):
            if name.startswith('.'):
                continue
            relative = prefix + name
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                warnings.append(f'{relative}: symlink skipped (world access never follows links).')
            elif stat.S_ISDIR(info.st_mode):
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    walk(child, relative + '/', depth + 1)
                finally:
                    os.close(child)
            elif stat.S_ISREG(info.st_mode) and name.lower().endswith('.md'):
                file_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
                with os.fdopen(file_fd, 'rb') as stream:
                    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                        raise ValueError(f'{relative}: no longer a regular file; retry indexing.')
                    raw = stream.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ValueError(f'{relative}: note exceeds the 2 MB limit.')
                total_bytes += len(raw)
                if total_bytes > 20_000_000:
                    raise ValueError('World Markdown exceeds the 20 MB total limit; select a smaller world folder.')
                try:
                    content = raw.decode('utf-8-sig')
                except UnicodeError:
                    raise ValueError(f'{relative}: save this note as UTF-8 before indexing.')
                notes.append({'path': relative, 'content': content, 'hash': hashlib.sha256(raw).hexdigest()})
                if len(notes) > 10000:
                    raise ValueError('World exceeds the 10,000-note limit.')
    walk(root_fd)
    return notes, warnings


def scalar(value):
    value = value.strip()
    if not value:
        return ''
    if value.startswith('"') or value.startswith('[') or value.startswith('{'):
        return json.loads(value)
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1].replace("''", "'")
    if value.startswith(('&', '*', '!', '>', '|')):
        raise ValueError('unsupported YAML syntax')
    value = re.split(r'\s+#', value, maxsplit=1)[0].rstrip()
    if value in ('true', 'false', 'null', '~'):
        return {'true': True, 'false': False, 'null': None, '~': None}[value]
    return value


def frontmatter(content):
    """Common Obsidian properties; preserve unsupported YAML verbatim with a warning.

    Supports flat mappings, quoted/plain/JSON values, block scalar text and block
    scalar lists. Nested YAML, tags, anchors and non-JSON flow syntax are flagged.
    """
    lines = content.splitlines()
    if not lines or lines[0] != '---':
        return {}, '', []
    end = next((i for i in range(1, len(lines)) if lines[i] in ('---', '...')), None)
    if end is None:
        return {}, content, ['Unclosed YAML frontmatter.']
    raw = '\n'.join(lines[1:end])
    props, warnings = {}, []
    i = 1
    while i < end:
        line = lines[i]
        i += 1
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        match = re.fullmatch(r'([\w-]+):(?:\s+(.*))?', line)
        if not match:
            warnings.append(f'Unsupported YAML line: {line[:100]}')
            continue
        key, value = match.group(1), match.group(2) or ''
        block = []
        while i < end and (lines[i].startswith((' ', '\t')) or not lines[i].strip()):
            block.append(lines[i]); i += 1
        try:
            if key in props:
                raise ValueError('duplicate property')
            if value in ('|', '|-', '|+', '>', '>-', '>+'):
                props[key] = (' ' if value.startswith('>') else '\n').join(s.strip() for s in block)
            elif block and any(s.strip() for s in block):
                if value or any(s.strip() and not s.lstrip().startswith('- ') for s in block):
                    raise ValueError('nested YAML is unsupported')
                props[key] = [scalar(s.lstrip()[2:]) for s in block if s.strip()]
            else:
                props[key] = scalar(value)
        except (ValueError, TypeError):
            warnings.append(f'Unsupported or invalid YAML property: {key}; raw text retained.')
    return props, raw, warnings


def normalize_link(target, source):
    target = target.split('|', 1)[0].split('#', 1)[0].strip().replace('\\', '/')
    if not target:
        return source
    if target.lower().endswith('.md'):
        target = target[:-3]
    if target.startswith('./') or target.startswith('../'):
        target = str(PurePosixPath(source).parent / target)
    parts = []
    for part in target.split('/'):
        if part == '..':
            if not parts:
                return None
            parts.pop()
        elif part not in ('', '.'):
            parts.append(part)
    return '/'.join(parts).casefold()


def scan(include_content=False):
    with LOCK, closing(connect()) as db, db:
        settings = read_state(db, 'settings', None)
        if not settings:
            raise ValueError('Select and save a world folder first.')
        fd = open_root(settings['folder'])
        try:
            notes, warnings = read_notes(fd)
        finally:
            os.close(fd)
        old = read_state(db, 'identities', [])
        entities, assigned = [], set()
        current_paths = {n['path'] for n in notes}
        for note in notes:
            props, raw_yaml, issues = frontmatter(note['content'])
            warnings.extend(f'{note["path"]}: {issue}' for issue in issues)
            explicit = props.get('id')
            if explicit is not None and (not isinstance(explicit, str) or not explicit.strip()):
                warnings.append(f'{note["path"]}: id must be nonempty text.')
                explicit = None
            same_path = next((n for n in old if n['path'] == note['path']), None)
            hash_matches = list({n['id']: n for n in old if n['hash'] == note['hash'] and n['path'] not in current_paths}.values())
            identity = explicit or (same_path or (hash_matches[0] if len(hash_matches) == 1 else {})).get('id') or uuid.uuid4().hex
            if identity in assigned:
                warnings.append(f'{note["path"]}: duplicate entity ID {identity}; fix IDs before expansion.')
            assigned.add(identity)
            kind = props.get('kind', '')
            if kind == 'monster':
                kind = 'creature'
            if kind and (not isinstance(kind, str) or kind not in SCHEMAS):
                warnings.append(f'{note["path"]}: unknown entity kind {kind}.')
            elif kind:
                for key in SCHEMAS[kind]['required']:
                    val = props.get(key)
                    if key == 'kind':
                        continue
                    if key == 'id' and not explicit:
                        continue  # Indexed ID supplies identity for unmodified existing notes.
                    if not isinstance(val, str) or not val.strip():
                        warnings.append(f'{note["path"]}: {kind} schema needs text property {key}.')
                if kind == 'creature' and str(props.get('challenge_rating', '')) not in CRS:
                    warnings.append(f'{note["path"]}: creature requires a valid challenge_rating (CR).')
            entity = {**note, 'id': identity, 'name': str(props.get('name') or PurePosixPath(note['path']).stem),
                      'kind': kind or 'note', 'properties': props, 'yaml': raw_yaml}
            entities.append(entity)
        paths, names = {}, {}
        for entity in entities:
            path = entity['path'][:-3].casefold()
            paths.setdefault(path, []).append(entity)
            for name in {PurePosixPath(path).name, entity['name'].casefold()}:
                names.setdefault(name, []).append(entity)
        ids = {}
        for entity in entities:
            ids.setdefault(entity['id'], []).append(entity)
        edges = []
        for entity in entities:
            targets = [('link', t) for t in re.findall(r'\[\[([^\]\n]+)\]\]', entity['content'])]
            parent = entity['properties'].get('parent')
            if parent:
                targets.append(('parent', str(parent).removeprefix('[[').removesuffix(']]')))
            rels = entity['properties'].get('relationships', [])
            if isinstance(rels, list):
                targets.extend(('relationship', str(t).removeprefix('[[').removesuffix(']]')) for t in rels)
            for relation, target in dict.fromkeys(targets):
                key = normalize_link(target, entity['path'][:-3])
                matches = ids.get(target) or paths.get(key, []) or (names.get(key, []) if key and '/' not in key else [])
                state = 'resolved' if len(matches) == 1 else 'ambiguous' if matches else 'unresolved'
                edges.append({'source': entity['id'], 'source_path': entity['path'], 'relation': relation,
                    'target': matches[0]['id'] if state == 'resolved' else None, 'link': target, 'status': state})
                if state != 'resolved':
                    warnings.append(f'{entity["path"]}: {state} {relation} [[{target}]].')
        graph = {'indexed_at': datetime.now(timezone.utc).isoformat(),
                 'entities': [{k: v for k, v in e.items() if k != 'content'} for e in entities],
                 'relationships': edges, 'diagnostics': warnings}
        # Retain identity history for deleted/reappearing notes, without retaining their prose.
        history = {n['path']: n for n in old}
        history.update({e['path']: {k: e[k] for k in ('path', 'id', 'hash')} for e in entities})
        put(db, 'identities', list(history.values()))
        put(db, 'graph', graph)
        result = {'settings': settings, 'graph': graph}
        if include_content:
            result['canon'] = [{'id': e['id'], 'path': e['path'], 'hash': e['hash'], 'content': e['content']} for e in entities]
            result['ready_for_expansion'] = not warnings
        return result
