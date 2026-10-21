"""Obsidian-friendly notes and non-destructive folder exports."""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

DATASET = 'https://huggingface.co/datasets/alan-txi/dnd-monsters'
CSV_URL = DATASET + '/resolve/main/dnd_monsters.csv'
GUIDE_NAME = 'Monster Forge - Obsidian Guide'
ROOT = Path(__file__).resolve().parent


def md(value):
    # Keep generated prose literal inside Markdown tables, headings, and lists.
    return re.sub(r'([\\`*_{}\[\]<>|#!])', r'\\\1', str(value or '').replace('\r', '').replace('\n', ' '))


def safe_name(value):
    name = re.sub(r'[\x00-\x1f<>:"/\\|?*#\[\]^]', '-', value).strip(' .')[:120].strip(' .')
    return name or 'Monster'


def world_links(value):
    if not isinstance(value, str) or len(value) > 3000:
        raise ValueError('World links must be text, up to 3,000 characters.')
    links = []
    for line in value.splitlines():
        name = line.strip().removeprefix('[[').removesuffix(']]').strip()
        if not name:
            continue
        if len(name) > 200 or any(char in name for char in '[]|<>\x00'):
            raise ValueError('Use one note name per line, without brackets or aliases.')
        if name not in links:
            links.append(name)
    if len(links) > 30:
        raise ValueError('Use at most 30 world links.')
    return links


def external_link(label, url):
    if not url or urlparse(url).scheme not in ('http', 'https'):
        return md(label)
    return f'[{md(label)}](<{url.replace(chr(62), "%3E").replace(chr(60), "%3C").replace(chr(10), "")}>)'


def render_markdown(monster, links_text=''):
    links = world_links(links_text)
    signed = lambda n: f'{n:+d}'
    frontmatter = {
        'id': monster['id'], 'name': monster['name'], 'kind': 'monster',
        'tags': ['bestiary', 'monster', 'homebrew', 'monster/' + monster['type']],
        'creature_type': monster['type'], 'challenge_rating': monster['cr'],
        'xp': monster['xp'], 'armor_class': monster['armor_class'], 'hit_points': monster['hit_points'],
        'role': monster['role'], 'ruleset': monster['ruleset'], 'created': monster['created_at'],
        'generator': 'Monster Forge', 'ollama_model': monster['model'],
        'dataset': DATASET, 'dataset_csv': CSV_URL,
        'dataset_sha256': hashlib.sha256((ROOT / 'data' / 'dnd_monsters.csv').read_bytes()).hexdigest(),
        'world_links': [f'[[{link}]]' for link in links],
    }
    lines = ['---'] + [f'{key}: {json.dumps(value, ensure_ascii=False)}' for key, value in frontmatter.items()]
    lines += ['---', '', f'# {md(monster["name"])}', '', f'*{md(monster["subtitle"])}*', '',
              f'{md(monster["size"])} {md(monster["type"])} · {md(monster["alignment"])} · {md(monster["role"])}', '',
              monster['description'], '', '## Combat profile', '',
              '| CR | XP | AC | HP | Proficiency |', '| --- | --- | --- | --- | --- |',
              f'| {monster["cr"]} | {monster["xp"]:,} | {monster["armor_class"]} | {monster["hit_points"]} | {signed(monster["proficiency_bonus"])} |', '',
              '| STR | DEX | CON | INT | WIS | CHA |', '| --- | --- | --- | --- | --- | --- |',
              '| ' + ' | '.join(f'{monster["abilities"][key]} ({signed(monster["ability_modifiers"][key])})' for key in ['str','dex','con','int','wis','cha']) + ' |', '']
    saves = ', '.join(f'{key.upper()} {signed(value)}' for key, value in monster['saving_throws'].items()) or 'None'
    details = [('Speed', monster['speed']), ('Saving throws', saves), ('Skills', monster['skills']),
               ('Senses', monster['senses']), ('Languages', monster['languages']),
               ('Damage resistances', monster['resistances']), ('Damage immunities', monster['immunities']),
               ('Condition immunities', monster['condition_immunities']), ('Vulnerabilities', monster['vulnerabilities']),
               ('Habitat', monster['habitat'])]
    lines += [f'- **{key}:** {md(value)}' for key, value in details]
    for title, key in [('Traits','traits'), ('Actions','actions'), ('Bonus actions','bonus_actions'),
                       ('Reactions','reactions'), ('Legendary actions','legendary_actions')]:
        if monster[key]:
            lines += ['', f'## {title}', '']
            for feature in monster[key]:
                lines += [f'### {md(feature["name"])}', '', feature['description'], '']
    lines += ['', '## Running the encounter', '', monster['tactics'], '', '## Loot and rewards', '',
              f'**XP:** {monster["xp"]:,} · **Guaranteed coins:** {monster["treasure_gp"]:,} gp', '',
              'Roll each item’s drop chance independently. Listed value is the total value of that drop.', '',
              '| Drop | Quantity | Rarity | Chance | Value (gp) | Description |',
              '| --- | --- | --- | --- | --- | --- |']
    for item in monster['loot']:
        lines += ['| ' + ' | '.join([md(item['name']), md(item['quantity']), md(item['rarity']),
                   f'{item["chance_percent"]}%', f'{item["value_gp"]:,}', md(item['description'])]) + ' |']
    lines += ['', '## Lore', '', monster['lore'], '', '## Adventure hook', '', monster['adventure_hook'], '',
              '## World connections', '']
    lines += [f'- [[{link}]]' for link in links] or ['Add links here to locations, factions, NPCs, quests, and sessions as your world grows.']
    lines += ['', '## Campaign notes', '', '<!-- Record sightings, encounters, consequences, and discoveries here. -->', '',
              '## Design notes', '', monster['balance_notes'], '']
    lines += [f'- {md(note)}' for note in monster['review_notes'] if not note.startswith('Level is a campaign label')]
    lines += ['', '## Sources and generation', '',
              '- Generator: Monster Forge — local Ollama creature workshop.',
              f'- Usage guide: [[{GUIDE_NAME}]]',
              f'- Reference dataset: {external_link("alan-txi/dnd-monsters", DATASET)}',
              f'- Dataset file: {external_link("dnd_monsters.csv", CSV_URL)}',
              f'- Dataset SHA-256: `{frontmatter["dataset_sha256"]}`',
              f'- Model: {md(monster["model"])}', f'- Generated: {md(monster["created_at"])}',
              f'- Stable monster ID: `{monster["id"]}`', '',
              'The dataset supplied numeric reference examples. Ollama created this original homebrew creature’s abilities, lore, and treasure. XP, proficiency, ability modifiers, proficient saves, and printed single-term dice averages were calculated by the app. Review encounter balance before play.', '',
              '### Reference creatures used', '', '| Creature | Type | CR | AC | HP | Original source |',
              '| --- | --- | --- | --- | --- | --- |']
    for ref in monster['references']:
        lines += ['| ' + ' | '.join([external_link(ref['name'], ref.get('url')), md(ref['type']),
                   md(ref['cr']), str(ref['ac']), str(ref['hp']), md(ref['source'])]) + ' |']
    for ref in monster.get('detail_references', []):
        lines += ['', '### ' + md(ref['title']), '',
                  '- Dataset: ' + external_link(ref['dataset'].rsplit('/', 2)[-2] + '/' + ref['dataset'].rsplit('/', 1)[-1], ref['dataset']),
                  '- Source file: ' + md(ref['source_file']) + ' · line ' + str(ref['line']),
                  '- Attribution: ' + md(ref.get('attribution', 'See dataset card')),
                  '- License: ' + md(ref['license']), '- Source SHA-256: `' + ref['sha256'] + '`',
                  '- Retrieved excerpt (truncated):', '', '> ' + md(ref['text'])]
    lines += ['', '### Original creative brief', '', md(monster['brief']['description']), '',
              '## Using this entry', '',
              'Use the combat profile and action sections during play. Challenge rating sets combat targets, XP and proficiency. Open **World connections** links to connect the creature to your vault. Add session history and changes under **Campaign notes**. Keep the source metadata with the note when sharing or adapting it.', '']
    return '\n'.join(lines)


def browse_folders(folder=''):
    if not isinstance(folder, str) or len(folder) > 4000:
        raise ValueError('Choose a valid folder path.')
    path = Path(folder).expanduser().resolve() if folder else Path.home()
    if not path.is_dir():
        raise ValueError('That folder does not exist. Choose an existing folder in your vault.')
    children = []
    for child in path.iterdir():
        if not child.name.startswith('.') and child.is_dir():
            children.append({'name': child.name, 'path': str(child)})
    children.sort(key=lambda item: item['name'].casefold())
    return {'path': str(path), 'parent': str(path.parent), 'folders': children}


def export_to_folder(monster, folder, links_text='', include_guide=True):
    if not isinstance(folder, str) or not folder.strip():
        raise ValueError('Select an export folder first.')
    if type(include_guide) is not bool:
        raise ValueError('Include guide must be true or false.')
    directory = Path(folder).expanduser().resolve()
    if not directory.is_dir():
        raise ValueError('That folder does not exist. Choose an existing folder in your vault.')
    content = render_markdown(monster, links_text)
    stem = safe_name(monster['name'])
    # Exclusive creation protects existing notes, including edits made in Obsidian.
    for counter in range(1, 10001):
        filename = f'{stem}{"" if counter == 1 else f" ({counter})"}.md'
        destination = directory / filename
        try:
            with destination.open('x', encoding='utf-8') as f:
                f.write(content)
            break
        except FileExistsError:
            continue
    else:
        raise ValueError('Too many existing exports with this name. Choose another folder.')
    guide_path = None
    guide_warning = None
    if include_guide:
        guide = directory / (GUIDE_NAME + '.md')
        try:
            with guide.open('x', encoding='utf-8') as f:
                f.write((ROOT / 'docs' / (GUIDE_NAME + '.md')).read_text(encoding='utf-8'))
            guide_path = str(guide)
        except FileExistsError:
            guide_path = str(guide)
        except OSError as e:
            guide_warning = f'Monster saved, but the guide could not be saved: {e}'
    return {'path': str(destination), 'guide_path': guide_path, 'warning': guide_warning}
