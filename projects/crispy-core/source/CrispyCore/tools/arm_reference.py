#!/usr/bin/env python3
"""Select a documented prefix of complete external ARM7TDMI binary vectors.

Useful for bounded runs and interrupted downloads. Never pads or invents tests.
The original upstream header declares the full count; output declares precisely
how many untouched complete records were selected. Provenance is emitted as JSON.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

parser = argparse.ArgumentParser()
parser.add_argument('source', type=Path)
parser.add_argument('output', type=Path)
parser.add_argument('--limit', type=int, default=256)
args = parser.parse_args()
if args.limit <= 0:
    raise SystemExit('limit must be positive')
blob = args.source.read_bytes()
if len(blob) < 8:
    raise SystemExit('Missing external vector header')
magic, total = struct.unpack_from('<II', blob)
if magic != 0xd33dbae0:
    raise SystemExit('Unexpected vector format')
position = 8
selected = min(total, args.limit)
for index in range(selected):
    if position + 4 > len(blob):
        raise SystemExit(f'Only {index} complete records available; requested {selected}')
    size, = struct.unpack_from('<I', blob, position)
    if size < 356 or position + size > len(blob):
        raise SystemExit(f'Truncated or invalid record {index}')
    position += size
result = struct.pack('<II', magic, selected) + blob[8:position]
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_bytes(result)
print(json.dumps({'source': str(args.source), 'upstream_count': total, 'selected_first': selected,
                  'source_bytes': len(blob), 'selected_bytes': len(result),
                  'prefix_sha256': hashlib.sha256(blob[:position]).hexdigest(),
                  'output_sha256': hashlib.sha256(result).hexdigest()}))
