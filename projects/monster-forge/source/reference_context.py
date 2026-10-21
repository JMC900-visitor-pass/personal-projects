"""Local, bounded retrieval from rules text and a FIREBALL session sample."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RULES = 'https://huggingface.co/datasets/jason-oneal/dnd-5e-dataset'
FIREBALL = 'https://huggingface.co/datasets/lara-martin/FIREBALL'
SESSION = 'filtered/00068c6b03adc2c102756053cf6edd05.jsonl'
STOP = set('the and for with from this that monster creature describe what dnd'.split())


def tokens(text):
    return set(re.findall(r'[a-z]{3,}', text.lower())) - STOP


def load():
    records = []
    for filename, dataset, source, license_name in [
        ('5e_alpaca_dataset.jsonl', RULES, '5e_alpaca_dataset.jsonl', 'MIT (dataset card)'),
        ('fireball-session.jsonl', FIREBALL, SESSION, 'CC BY 4.0')]:
        path = ROOT / 'data' / filename
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        for line_number, line in enumerate(path.open(encoding='utf-8'), 1):
            row = json.loads(line)
            if dataset == RULES:
                title = row['instruction']
                # Creature, condition, spell and trait entries enrich monster design.
                if not any(word in title.lower() for word in ('monster', 'condition', 'spell', 'trait', 'damage type')):
                    continue
                text = row['output'][:1800]
            else:
                title = 'Actual-play turn ' + str(line_number)
                # Exclude player identifiers and character levels from the projection.
                text = '\n'.join(str(x) for key in ('automation_results', 'after_utterances')
                                 for x in (row.get(key) or []))[:1200]
            if text.strip():
                records.append({'dataset': dataset, 'source_file': source, 'line': line_number,
                    'sha256': digest, 'license': license_name,
                    'attribution': ('jason-oneal' if dataset == RULES else
                        'Andrew Zhu, Karmanya Aggarwal, Alexander Feng, Lara J. Martin, Chris Callison-Burch (2023)'),
                    'title': title, 'text': text})
    return records


RECORDS = load()


def retrieve_context(brief, refs):
    query = tokens(' '.join(str(brief.get(k, '')) for k in ('name', 'description', 'type', 'role')))
    query |= tokens(' '.join(r['name'].replace('-', ' ') for r in refs))
    selected = []
    for dataset, limit in [(RULES, 3), (FIREBALL, 2)]:
        ranked = sorted((r for r in RECORDS if r['dataset'] == dataset),
            key=lambda r: len(query & tokens(r['title'])) * 3 + len(query & tokens(r['text'])), reverse=True)
        selected.extend(ranked[:limit])
    return selected
