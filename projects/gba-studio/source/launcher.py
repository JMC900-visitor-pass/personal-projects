#!/usr/bin/env python3
"""Choose a model and launch OpenCode with the bundled REA MCP server."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import urllib.request

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'rea-rea-agents-6.4.0'
STATE = ROOT / '.launcher.json'
OLLAMA_URL = os.environ.get('OLLAMA_HOST', 'http://127.0.0.1:11434').rstrip('/')
if '://' not in OLLAMA_URL:
    OLLAMA_URL = 'http://' + OLLAMA_URL
os.environ['PATH'] = os.pathsep.join([str(Path.home() / '.local/bin'), '/opt/homebrew/bin', '/usr/local/bin', os.environ.get('PATH', '')])


def executable(name):
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f'{name} is not installed or is missing from PATH.')
    return path


def preferences():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def ollama_models():
    try:
        with urllib.request.urlopen(OLLAMA_URL + '/api/tags', timeout=5) as response:
            data = json.load(response)
        return sorted(m['name'] for m in data['models'])
    except Exception as exc:
        raise RuntimeError(f'Cannot reach Ollama at {OLLAMA_URL}. Start Ollama and refresh. ({exc})') from exc


def configuration(model=None):
    # opencode v2 reads local MCP servers under mcp.servers.<name>; the legacy
    # mcp.<name> shape is ignored, which left REA unconnected.
    # Per-server 'timeout' is NOT allowed (silently drops entire MCP config).
    # Use top-level mcp.timeout instead.
    config = {
        '$schema': 'https://opencode.ai/config.json',
        'mcp': {'timeout': 30000, 'servers': {'rea': {'type': 'local', 'command': [executable('node'), str(SOURCE / 'scripts/rea.mjs'), 'mcp']}}},
        'instructions': [str(SOURCE / '.agents/skills/reverse-engineer-anything/SKILL.md')],
    }
    if model and model.startswith('rea_ollama/'):
        name = model.removeprefix('rea_ollama/')
        config['provider'] = {'rea_ollama': {'npm': '@ai-sdk/openai-compatible', 'name': 'Ollama via REA', 'options': {'baseURL': OLLAMA_URL + '/v1'}, 'models': {name: {'name': name}}}}
    return config


def environment(model=None):
    env = os.environ.copy()
    existing = json.loads(env.get('OPENCODE_CONFIG_CONTENT', '{}'))
    config = configuration(model)
    if 'mcp' in config:
        mcp = config.pop('mcp')
        servers = existing.setdefault('mcp', {}).setdefault('servers', {})
        servers.update(mcp.get('servers', {}))
        for key, value in mcp.items():
            if key != 'servers':
                existing['mcp'][key] = value
    if 'provider' in config:
        existing.setdefault('provider', {}).update(config.pop('provider'))
    existing['instructions'] = list(dict.fromkeys(existing.get('instructions', []) + config.pop('instructions')))
    existing.update(config)
    env['OPENCODE_CONFIG_CONTENT'] = json.dumps(existing)
    return env


def write_config_file(directory, model=None):
    # opencode v2 runs a persistent headless service and (re)loads MCP/provider/
    # instructions from a watched config file. An env-only OPENCODE_CONFIG_CONTENT
    # is read only when that service starts and is dropped on the next config
    # reload, so REA must also live in a file. We merge into the workspace's
    # opencode.json without clobbering any existing entries.
    config = configuration(model)
    path = Path(directory) / 'opencode.json'
    try:
        existing = json.loads(path.read_text()) if path.is_file() else {}
    except ValueError:
        existing = {}
    if 'provider' in config:
        existing.setdefault('provider', {}).update(config['provider'])
    if 'mcp' in config:
        mcp = config['mcp']
        servers = existing.setdefault('mcp', {}).setdefault('servers', {})
        servers.update(mcp.get('servers', {}))
        for key, value in mcp.items():
            if key != 'servers':
                existing.setdefault('mcp', {})[key] = value
    existing['instructions'] = list(dict.fromkeys((existing.get('instructions') or []) + config['instructions']))
    existing.setdefault('$schema', config['$schema'])
    path.write_text(json.dumps(existing, indent=2) + '\n')
    return path


def configured_models():
    result = subprocess.run([executable('opencode'), 'models'], cwd=ROOT / 'workspace', capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or 'OpenCode could not list models.')
    return sorted(line.strip() for line in result.stdout.splitlines() if '/' in line and not line.startswith('\x1b'))


def ensure_rea_loaded(directory, tries=4, delay=1.0):
    # opencode v2 runs a shared background service that watches the config file we
    # just wrote. Reading it immediately can still report the previous state until
    # the service finishes reloading, so wait briefly. Best effort and non-fatal:
    # a capped loop so a launch never hangs, returning False if REA never connects.
    import time
    for _ in range(tries):
        try:
            result = subprocess.run([executable('opencode'), 'mcp', 'list'], cwd=directory,
                                    capture_output=True, text=True, timeout=15)
            out = (result.stdout or '') + (result.stderr or '')
            if 'No MCP servers' not in out and 'error' not in out.lower() and 'connected' in out:
                return True
        except Exception:
            pass
        time.sleep(delay)
    return False


def check_ready():
    executable('node')
    executable('opencode')
    if not (SOURCE / 'dist/main.js').is_file():
        raise RuntimeError(f'REA has not been built. In {SOURCE}, run npm ci then npm run build:cached.')


def launch(model, workspace, prompt='', terminal=False):
    check_ready()
    if not model or '/' not in model:
        raise RuntimeError('Select a model first (provider/model).')
    directory = Path(workspace).expanduser().resolve()
    if not directory.is_dir():
        raise RuntimeError('Choose an existing workspace directory.')
    if model.startswith('rea_ollama/'):
        if model.removeprefix('rea_ollama/') not in ollama_models():
            raise RuntimeError('That model is no longer installed in Ollama. Refresh the list.')
    STATE.write_text(json.dumps({'model': model, 'workspace': str(directory)}, indent=2) + '\n')
    write_config_file(directory, model)
    ensure_rea_loaded(directory)
    if terminal:
        command = [executable('opencode'), str(directory)]
        if prompt:
            command += ['--prompt', prompt]
        return subprocess.call(command, cwd=directory, env=environment(model))
    # Terminal executes this same script; model and prompt are passed as argv, never shell code.
    import shlex
    command = [sys.executable, str(Path(__file__).resolve()), '--cli', '--model', model, '--workspace', str(directory)]
    if prompt:
        command += ['--prompt', prompt]
    script = 'tell application "Terminal"\nactivate\ndo script ' + json.dumps(shlex.join(command)) + '\nend tell'
    subprocess.run(['osascript', '-e', script], check=True, capture_output=True, text=True)
    return 0


def gui():
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    root = tk.Tk()
    root.title('REA · Agent launcher')
    root.geometry('760x430')
    root.minsize(640, 400)
    frame = ttk.Frame(root, padding=24)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='Reverse Engineer Anything', font=('', 22, 'bold')).pack(anchor='w')
    ttk.Label(frame, text='Choose a model. OpenCode runs the agent with REA tools connected.').pack(anchor='w', pady=(6, 20))
    saved = preferences()
    previous = saved.get('model', '')
    mode = tk.StringVar(value='Ollama' if not previous or previous.startswith('rea_ollama/') else 'Configured OpenCode providers')
    model = tk.StringVar(value=previous.removeprefix('rea_ollama/'))
    workspace = tk.StringVar(value=saved.get('workspace', str(ROOT / 'workspace')))
    status = tk.StringVar(value='Loading models…')
    row = ttk.Frame(frame)
    row.pack(fill='x')
    provider = ttk.Combobox(row, textvariable=mode, values=['Ollama', 'Configured OpenCode providers'], state='readonly', width=29)
    provider.pack(side='left')
    ttk.Label(frame, text='Model (select or type a model ID)').pack(anchor='w', pady=(14, 4))
    picker = ttk.Combobox(frame, textvariable=model)
    picker.pack(fill='x')
    ttk.Label(frame, text='Working directory').pack(anchor='w', pady=(14, 4))
    pathrow = ttk.Frame(frame)
    pathrow.pack(fill='x')
    ttk.Entry(pathrow, textvariable=workspace).pack(side='left', fill='x', expand=True)
    def browse():
        selected = filedialog.askdirectory(initialdir=workspace.get())
        if selected:
            workspace.set(selected)
    ttk.Button(pathrow, text='Browse…', command=browse).pack(side='right', padx=(8, 0))
    ttk.Label(frame, text='Optional starting task').pack(anchor='w', pady=(14, 4))
    prompt = ttk.Entry(frame)
    prompt.pack(fill='x')
    ttk.Label(frame, textvariable=status, wraplength=700).pack(anchor='w', pady=(14, 8))
    pending = []
    busy = False
    def poll():
        nonlocal busy
        if pending:
            models, error = pending.pop()
            busy = False
            refresh_button.configure(state='normal')
            provider.configure(state='readonly')
            picker.configure(values=models)
            if error:
                status.set(error)
            else:
                if model.get() not in models:
                    model.set(models[0] if models else '')
                status.set(f'{len(models)} models available. Launch opens an interactive Terminal session.')
        root.after(100, poll)
    def refresh(event=None):
        nonlocal busy
        if busy:
            return
        busy = True
        selection = mode.get()
        status.set('Loading models…')
        refresh_button.configure(state='disabled')
        provider.configure(state='disabled')
        def worker():
            try:
                pending.append((ollama_models() if selection == 'Ollama' else configured_models(), None))
            except Exception as exc:
                pending.append(([], str(exc)))
        threading.Thread(target=worker, daemon=True).start()
    refresh_button = ttk.Button(row, text='Refresh models', command=refresh)
    refresh_button.pack(side='right')
    provider.bind('<<ComboboxSelected>>', refresh)
    def start():
        try:
            selected = model.get().strip()
            if not selected:
                raise RuntimeError('Select a model first.')
            if mode.get() == 'Ollama':
                selected = 'rea_ollama/' + selected
            launch(selected, workspace.get(), prompt.get())
            status.set('Agent opened in Terminal. You can launch another session here.')
        except Exception as exc:
            messagebox.showerror('Could not launch REA', str(exc))
    ttk.Button(frame, text='Launch agent', command=start).pack(anchor='e')
    poll()
    refresh()
    root.mainloop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cli', action='store_true', help='Use the terminal model selector')
    parser.add_argument('--model', help='rea_ollama/MODEL or an OpenCode provider/model ID')
    parser.add_argument('--workspace', default=str(ROOT / 'workspace'))
    parser.add_argument('--prompt', default='')
    parser.add_argument('--check', action='store_true', help='Check REA and MCP without starting a model')
    args = parser.parse_args()
    if args.check:
        check_ready()
        directory = Path(args.workspace).expanduser().resolve()
        write_config_file(directory, args.model)
        return subprocess.call([executable('opencode'), 'mcp', 'list'], cwd=directory, env=environment(args.model))
    if args.cli or args.model:
        model = args.model
        if not model:
            models = ollama_models()
            if not models:
                raise RuntimeError('No Ollama models installed.')
            for number, name in enumerate(models, 1):
                print(f'{number:2}. {name}')
            try:
                index = int(input('Select model number: ')) - 1
            except ValueError:
                raise RuntimeError('Enter a model number.')
            if not 0 <= index < len(models):
                raise RuntimeError('Model number is out of range.')
            model = 'rea_ollama/' + models[index]
        return launch(model, args.workspace, args.prompt, terminal=True)
    gui()
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (KeyboardInterrupt, EOFError):
        sys.exit(130)
    except Exception as error:
        print(f'REA launcher: {error}', file=sys.stderr)
        sys.exit(1)
