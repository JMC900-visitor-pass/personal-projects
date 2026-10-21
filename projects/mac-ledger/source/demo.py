#!/usr/bin/env python3
"""Create a disposable dummy system and two canonical snapshots."""
from pathlib import Path
import tempfile
import ledger
base = Path(tempfile.mkdtemp(prefix='mac-ledger-demo-')).resolve()
root = base / 'dummy-mac'
project = root / 'projects' / 'example'
project.mkdir(parents=True)
(project / 'requirements.txt').write_text('example-dependency==1.0\n')
(project / 'old-note.md').write_text('Disposable fixture\n')
ledger.scan(root, base / 'before')
(project / 'old-note.md').unlink()
(project / 'requirements.txt').write_text('example-dependency==2.0\n')
(project / 'diagnostic.txt').write_text('Fixture: dependency unavailable\n')
ledger.scan(root, base / 'after')
result = ledger.diff(base / 'before', base / 'after')
ledger.write_md(base / 'delta.md', 'Dummy filesystem delta', result)
print(f'Demo evidence: {base}')
for item in result['changes']:
    print(item['status'], item['path'])
