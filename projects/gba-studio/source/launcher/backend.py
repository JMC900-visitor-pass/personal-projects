"""GB/GBC/GBA library, local C recovery and verified native build adapters."""
from pathlib import Path
import argparse, hashlib, json, os, shutil, subprocess, sys, tempfile, signal
import conversion
from rom_analysis import identify, EXTENSIONS
ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / 'workspace/launcher'
EMERALD = 'f3ae088181bf583e55daf962a92bb46f4f1d07b7'
APP = ROOT / 'build/mvp/Emerald MVP.app'

def atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, delete=False) as f:
        f.write(text); name=f.name
    os.replace(name, path)

def library():
    p=STATE/'library.json'
    return json.loads(p.read_text()) if p.exists() else {}

def publish(db):
    atomic(STATE/'library.json', json.dumps(db, indent=2))
    rows=[]
    for sha,g in sorted(db.items(), key=lambda item:item[1]['name'].lower()):
        clean=lambda x: ''.join(c if c.isprintable() and c not in '\t\r\n' else ' ' for c in str(x))
        ready=sha==EMERALD and (APP/'Contents/MacOS/emerald').exists()
        project=conversion.manifest_for(g,sha)
        status='ready' if ready else 'build' if sha==EMERALD else (project['status'] if project else 'new')
        system=g.get('system','GBA')
        units=len(project['units']) if project else 0
        queued=len(project['queue']) if project else 0
        rows.append('\t'.join(map(clean,[sha,g['name'],g['code'],status,g['size'],system,units,queued])))
    atomic(STATE/'library.tsv','\n'.join(rows)+'\n')
    config=conversion.settings()
    atomic(STATE/'model.txt',config['model']+'\n')

def import_one(path, db):
    if path.suffix.lower() not in EXTENSIONS:return False
    meta=identify(path)
    data=path.read_bytes()
    sha=meta.pop('sha1')
    dest=STATE/'roms'/f'{sha}{path.suffix.lower()}';dest.parent.mkdir(parents=True,exist_ok=True)
    if not dest.exists():
        with tempfile.NamedTemporaryFile('wb',dir=dest.parent,delete=False) as f:f.write(data);tmp=f.name
        os.replace(tmp,dest)
    name=db.get(sha,{}).get('name',path.stem)
    db[sha]={**meta,'name':name,'path':str(dest),'original':str(path.resolve())}
    print(f'Imported {name} ({meta["system"]}) — '+('verified C port available' if sha==EMERALD else 'ready for local C recovery'),flush=True)
    for warning in meta['warnings']:print('Note: '+warning,flush=True)
    return True

def pick(folder=False):
    script='POSIX path of (choose folder with prompt "Import a GB, GBC or GBA game folder")' if folder else 'POSIX path of (choose file with prompt "Import a .gb, .gbc or .gba game")'
    r=subprocess.run(['osascript','-e',script],capture_output=True,text=True)
    if r.returncode:return None
    return Path(r.stdout.strip())

def run(args):
    os.environ['PATH']='/opt/homebrew/bin:'+str(Path.home()/'.local/bin')+':'+os.environ.get('PATH','')
    STATE.mkdir(parents=True,exist_ok=True)
    db=library()
    if args.action=='refresh':publish(db);return
    if args.action=='models':
        names=conversion.local_models()
        atomic(STATE/'models.txt','\n'.join(names)+'\n')
        print('\n'.join(names) if names else 'No local models installed.',flush=True);return
    if args.action=='model':
        if not args.paths:raise ValueError('Supply a local model name')
        conversion.select_model(args.paths[0]);publish(db);print('Selected local model: '+args.paths[0],flush=True);return
    if args.action in ('import','pick','folder'):
        paths=[Path(p) for p in args.paths] if args.action=='import' else [pick(args.action=='folder')]
        errors=[];n=0
        for path in paths:
            if path is None:continue
            candidates=sorted(path.rglob('*')) if path.is_dir() else [path]
            for p in candidates:
                if p.is_file() and p.suffix.lower() in EXTENSIONS:
                    try:n+=import_one(p,db)
                    except (OSError,ValueError) as e:errors.append(str(e))
        publish(db)
        print(f'{n} game(s) imported. {len(errors)} rejected.',flush=True)
        for e in errors:print(e,flush=True)
        return
    if args.action=='emulator':
        r=subprocess.run(['osascript','-e','POSIX path of (choose application with prompt "Choose your GBA emulator (for example mGBA)")'],capture_output=True,text=True)
        if not r.returncode:atomic(STATE/'emulator.txt',r.stdout.strip());print('Emulator selected. Its own display/control settings apply.')
        return
    if not args.paths or args.paths[0] not in db:raise ValueError('Select an imported game first')
    sha=args.paths[0];game=db[sha];rom=Path(game['path'])
    if hashlib.sha1(rom.read_bytes()).hexdigest()!=sha:raise ValueError('Imported ROM changed: re-import it before continuing')
    if args.action in ('recover','project','compile','seed'):
        try:
            if args.action=='recover':conversion.recover(game,sha,args.blocks)
            elif args.action=='compile':conversion.build_drafts(game,sha)
            elif args.action=='seed':
                if args.address is None or args.mode is None:raise ValueError('seed requires --address and --mode')
                conversion.seed(game,sha,args.address,args.mode)
            else:
                with conversion.lock(conversion.project_path(game,sha)):
                    project,_=conversion.prepare(game,sha)
                subprocess.run(['open',str(project)],check=True)
        finally:publish(db)
    elif args.action=='build':
        if sha!=EMERALD:raise ValueError('No validated native port exists yet. Recover C and compile drafts from this game’s project.')
        print('Building the matching recovered-C Emerald port. The imported ROM identifies the supported revision.',flush=True)
        env=dict(os.environ);env['PATH']='/opt/homebrew/bin:'+str(Path.home()/'.local/bin')+':'+env.get('PATH','')
        subprocess.run(['make','native-raylib','-j8'],cwd=ROOT/'sources/pokeemerald-wasm',env=env,check=True)
        subprocess.run([sys.executable,str(ROOT/'scripts/package_mvp.py')],env=env,check=True)
        print('C build complete. Ready to play.',flush=True);publish(db)
    elif args.action=='play':
        if sha!=EMERALD:raise ValueError('Use Play via emulator for this game.')
        exe=APP/'Contents/MacOS/emerald'
        if not exe.exists():raise ValueError('Build this game first')
        cfg=STATE/f'{sha}.cfg'
        if not cfg.exists():cfg=STATE/'global.cfg'
        savedir=Path.home()/'Library/Application Support/Build GBa MVP';savedir.mkdir(parents=True,exist_ok=True)
        print('Starting Emerald — compiled C / Raylib. Esc: close; F11: fullscreen.',flush=True)
        subprocess.run([str(exe),'--save',str(savedir/'emerald.sav'),'--config',str(cfg)],check=True)
    elif args.action=='fallback':
        p=STATE/'emulator.txt';emulator=p.read_text().strip() if p.exists() else '/Applications/mGBA.app'
        if not Path(emulator).is_dir():raise ValueError('Select an installed emulator from the Library page first. mGBA is not installed.')
        # Only the managed ROM copy is passed, so external saves do not touch original ROM folders.
        subprocess.run(['open','-a',emulator,str(rom)],check=True)
        print('Opened in emulator fallback. This is not a C conversion. Emulator settings apply.',flush=True)

if __name__=='__main__':
    def interrupted(signum, frame):raise InterruptedError('Task stopped; saved recovery blocks can be resumed')
    signal.signal(signal.SIGTERM,interrupted)
    p=argparse.ArgumentParser();p.add_argument('action',choices=['refresh','import','pick','folder','build','play','fallback','emulator','recover','project','compile','models','model','seed']);p.add_argument('paths',nargs='*')
    p.add_argument('--blocks',type=int,help='Number of blocks to recover this batch (1-64)')
    p.add_argument('--address',type=lambda x:int(x,0),help='Resolved instruction address for seed')
    p.add_argument('--mode',choices=['arm','thumb','sm83'])
    try:run(p.parse_args())
    except Exception as e:print(f'ERROR: {e}',file=sys.stderr,flush=True);sys.exit(1)
