#!/usr/bin/env python3
"""Extract numeric expectations from an explicitly supplied mGBA suite io-read.c.

The upstream file remains external validation material. Output is a data-only
TSV used by io-conformance; this does not run the upstream UI/test ROM.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

parser = argparse.ArgumentParser()
parser.add_argument('source', type=Path)
parser.add_argument('output', type=Path)
args = parser.parse_args()
content = args.source.read_text()
body = content.split('ioReadTests[] = {', 1)[1].split('};', 1)[0]
pattern = r'\{\s*"([^"]+)",\s*(0x[0-9A-Fa-f]+),\s*(true|false),\s*(?:true|false),\s*(0x[0-9A-Fa-f]+|[0-9]+),'
cases = re.findall(pattern, body)
if not cases or len(cases) != body.count('{'):
    raise SystemExit('Unexpected upstream IO test table format')
args.output.write_text(''.join(f'{int(address, 0):x}\t{int(expected, 0):x}\t{int(store == "true")}\t{name}\n'
                               for name, address, store, expected in cases))
print(json.dumps({'source': str(args.source), 'sha256': hashlib.sha256(args.source.read_bytes()).hexdigest(), 'cases': len(cases)}))
