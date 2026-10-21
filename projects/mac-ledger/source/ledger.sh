#!/bin/bash
set -euo pipefail
LEDGER_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "${LEDGER_PYTHON:-python3}" "$LEDGER_DIR/ledger.py" "$@"
