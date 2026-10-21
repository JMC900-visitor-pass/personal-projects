"""Compatibility launcher. The complete CLI lives in cli.py.

Run this file from anywhere, with optional subcommands/flags.
"""
import sys
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from monster_studio.cli import main

if __name__ == '__main__':
    raise SystemExit(main())
