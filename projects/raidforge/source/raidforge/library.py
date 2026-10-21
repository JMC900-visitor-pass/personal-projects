"""Saved skirmishes: one validated JSON file per generated packet."""
import json
import os
import re
import tempfile
from pathlib import Path

from .skirmish import ROOT, load_packet, upgrade_legacy_packet, validate_packet

DEFAULT_DIR = ROOT / 'runtime' / 'skirmishes'
EXAMPLE_ID = 'example'
SAVED_ID = re.compile(r'^[a-z0-9][a-z0-9_]{0,79}$')


class Library:
    def __init__(self, folder=None):
        self.folder = Path(folder) if folder else DEFAULT_DIR

    def _path(self, skirmish_id):
        if not isinstance(skirmish_id, str) or not SAVED_ID.match(skirmish_id):
            raise ValueError('Unknown skirmish')
        return self.folder / f'{skirmish_id}.json'

    def save(self, packet):
        validate_packet(packet)
        self.folder.mkdir(parents=True, exist_ok=True)
        base = f'{packet["scenario"]["id"][:60]}_{packet.get("generation", {}).get("seed", 0)}'
        skirmish_id, suffix = base, 2
        while skirmish_id == EXAMPLE_ID or self._path(skirmish_id).exists():
            skirmish_id, suffix = f'{base}_{suffix}', suffix + 1
        packet = {**packet, 'saved_id': skirmish_id}
        handle, temporary = tempfile.mkstemp(dir=self.folder, suffix='.tmp')
        with os.fdopen(handle, 'w', encoding='utf-8') as out:
            json.dump(packet, out, indent=2, ensure_ascii=False)
        os.replace(temporary, self._path(skirmish_id))
        return packet

    def get(self, skirmish_id):
        if skirmish_id == EXAMPLE_ID:
            return {**load_packet(), 'saved_id': EXAMPLE_ID}
        path = self._path(skirmish_id)
        if not path.exists():
            raise ValueError('Unknown skirmish')
        with path.open(encoding='utf-8') as handle:
            return validate_packet(upgrade_legacy_packet(json.load(handle)))

    def list(self):
        entries = []
        for path in self.folder.glob('*.json') if self.folder.exists() else []:
            try:
                packet = self.get(path.stem)
            except (ValueError, OSError, json.JSONDecodeError):
                continue
            generation = packet.get('generation', {})
            entries.append({'id': path.stem, 'name': packet['scenario']['name'],
                            'backend': generation.get('backend'), 'created_at': generation.get('created_at', ''),
                            'monsters': sum(m['count'] for m in packet['monsters'])})
        entries.sort(key=lambda entry: entry['created_at'], reverse=True)
        example = load_packet()
        return entries + [{'id': EXAMPLE_ID, 'name': example['scenario']['name'] + ' (example)', 'backend': 'bundled',
                           'created_at': '', 'monsters': sum(m['count'] for m in example['monsters'])}]
