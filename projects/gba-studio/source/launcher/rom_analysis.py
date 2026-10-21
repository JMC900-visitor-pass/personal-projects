"""Cartridge identification and conservative, evidence-only block discovery.

GB opcode layout: https://gbdev.io/gb-opcodes/optables/
Headers: https://gbdev.io/pandocs/The_Cartridge_Header.html
GBA decoding uses GNU binutils' ARMv4T disassembler, never the language model.
"""
from pathlib import Path
import hashlib
import re
import shutil
import subprocess

EXTENSIONS = {'.gb', '.gbc', '.gba'}


def identify(path):
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in EXTENSIONS:
        raise ValueError('Expected a .gb, .gbc or .gba cartridge')
    size = path.stat().st_size
    limit = 32 * 1024 * 1024 if suffix == '.gba' else 8 * 1024 * 1024
    minimum = 192 if suffix == '.gba' else 0x150
    if not minimum <= size <= limit:
        raise ValueError(f'{path.name}: invalid cartridge size ({size} bytes)')
    data = path.read_bytes()
    warnings = []
    if suffix == '.gba':
        if data[0xb2] != 0x96 or ((-sum(data[0xa0:0xbd])-0x19) & 255) != data[0xbd]:
            raise ValueError(f'{path.name}: GBA header/checksum invalid')
        system, cpu, entry = 'GBA', 'ARMv4T', 0x08000000
        title = data[0xa0:0xac]
        code = data[0xac:0xb0].decode('ascii', 'replace')
        extra = {}
    else:
        checksum = 0
        for b in data[0x134:0x14d]:
            checksum = (checksum - b - 1) & 255
        if checksum != data[0x14d]:
            raise ValueError(f'{path.name}: GB/GBC header checksum invalid')
        color = bool(data[0x143] & 0x80)
        system, cpu, entry = ('GBC' if color else 'GB'), 'SM83', 0x100
        title = data[0x134:0x13f if color else 0x144]
        code = system
        sizecode = data[0x148]
        declared = (32768 << sizecode) if sizecode <= 8 else {0x52:72*16384, 0x53:80*16384, 0x54:96*16384}.get(sizecode)
        if declared != size:
            warnings.append('Header ROM size differs from file size; bank mapping needs review.')
        total = (sum(data) - data[0x14e] - data[0x14f]) & 0xffff
        if total != int.from_bytes(data[0x14e:0x150], 'big'):
            warnings.append('Global checksum differs (common for modified cartridges).')
        extra = {'cartridge_type':data[0x147], 'rom_size_code':sizecode,
                 'ram_size_code':data[0x149], 'cgb_flag':data[0x143]}
    return {'sha1':hashlib.sha1(data).hexdigest(), 'system':system, 'cpu':cpu,
            'entry':entry, 'title':title.rstrip(b'\0 ').decode('ascii','replace'),
            'code':code or system, 'size':size, 'warnings':warnings, **extra}


REG = ['b','c','d','e','h','l','[hl]','a']
PAIR = ['bc','de','hl','sp']
COND = ['nz','z','nc','c']
ALU = ['add a','adc a','sub','sbc a','and','xor','or','cp']


def gb_instruction(data, pc):
    """Decode one SM83 instruction in the fixed ROM bank. No bank assumptions."""
    op = data[pc]; x, y, z = op >> 6, (op >> 3) & 7, op & 7
    p, q = y >> 1, y & 1
    length, text, targets, stop, issue = 1, '', [], False, None
    n = data[pc+1] if pc+1 < len(data) else 0
    nn = int.from_bytes(data[pc+1:pc+3], 'little')
    rel = (pc+2+(n if n < 128 else n-256)) & 65535
    if x == 0:
        if z == 0:
            if y == 0: text = 'nop'
            elif y == 1: text, length = f'ld [0x{nn:04x}],sp', 3
            elif y == 2: text, length, stop, issue = 'stop', 2, True, 'STOP / speed switching needs platform semantics'
            else:
                text, length, stop = f'jr {"" if y == 3 else COND[y-4]+","}0x{rel:04x}', 2, True
                targets = [rel] + ([pc+2] if y != 3 else [])
        elif z == 1: text, length = (f'add hl,{PAIR[p]}',1) if q else (f'ld {PAIR[p]},0x{nn:04x}',3)
        elif z == 2:
            addr = ['bc','de','hl+','hl-'][p]
            text = f'ld a,[{addr}]' if q else f'ld [{addr}],a'
        elif z == 3: text = f'{"dec" if q else "inc"} {PAIR[p]}'
        elif z in (4,5): text = f'{"inc" if z == 4 else "dec"} {REG[y]}'
        elif z == 6: text, length = f'ld {REG[y]},0x{n:02x}',2
        else: text = ['rlca','rrca','rla','rra','daa','cpl','scf','ccf'][y]
    elif x == 1:
        text = 'halt' if op == 0x76 else f'ld {REG[y]},{REG[z]}'
        if op == 0x76: stop, targets, issue = True, [pc+1], 'HALT / interrupt wakeup needs platform semantics'
    elif x == 2: text = f'{ALU[y]} {REG[z]}'
    elif z == 0:
        if y < 4: text, stop, targets, issue = f'ret {COND[y]}',True,[pc+1],'Dynamic return target'
        else:
            text = [f'ldh [0xff{n:02x}],a',f'add sp,{n if n < 128 else n-256}',f'ldh a,[0xff{n:02x}]',f'ld hl,sp+({n if n < 128 else n-256})'][y-4]
            length = 2
    elif z == 1:
        if not q: text = f'pop {["bc","de","hl","af"][p]}'
        else:
            text = ['ret','reti','jp hl','ld sp,hl'][p]
            if p != 3: stop, issue = True,'Dynamic return/jump target'
    elif z == 2:
        if y < 4: text, length, stop, targets = f'jp {COND[y]},0x{nn:04x}',3,True,[nn,pc+3]
        else:
            text = ['ld [0xff00+c],a',f'ld [0x{nn:04x}],a','ld a,[0xff00+c]',f'ld a,[0x{nn:04x}]'][y-4]
            length = 3 if y & 1 else 1
    elif z == 3:
        if y == 0: text, length, stop, targets = f'jp 0x{nn:04x}',3,True,[nn]
        elif y == 1:
            length = 2
            a,b,c = n >> 6,(n >> 3) & 7,n & 7
            text = f'{["rlc","rrc","rl","rr","sla","sra","swap","srl"][b]} {REG[c]}' if a == 0 else f'{["", "bit", "res", "set"][a]} {b},{REG[c]}'
        elif y in (6,7): text = 'di' if y == 6 else 'ei'
    elif z == 4 and y < 4: text, length, stop, targets = f'call {COND[y]},0x{nn:04x}',3,True,[nn,pc+3]
    elif z == 5:
        if not q: text = f'push {["bc","de","hl","af"][p]}'
        elif p == 0: text, length, stop, targets = f'call 0x{nn:04x}',3,True,[nn,pc+3]
    elif z == 6: text, length = f'{ALU[y]} 0x{n:02x}',2
    elif z == 7: text, stop, targets = f'rst 0x{y*8:02x}',True,[y*8,pc+1]
    if not text: text, stop, issue = f'illegal 0x{op:02x}',True,'Illegal SM83 opcode'
    if pc+length > min(len(data),0x4000):
        raise ValueError('Instruction crosses fixed ROM bank boundary')
    return {'address':pc,'size':length,'bytes':data[pc:pc+length].hex(),
            'asm':text,'targets':targets,'stop':stop,'issue':issue}


def block(rom, system, address, mode, max_instructions=32):
    data = Path(rom).read_bytes()
    instructions, targets, issues = [], [], []
    if system in ('GB','GBC'):
        if not 0 <= address < min(len(data),0x4000):
            raise ValueError('Banked code needs a known mapper/bank; refusing to guess')
        pc = address
        for _ in range(max_instructions):
            if pc >= min(len(data),0x4000) or 0x104 <= pc < 0x150:
                issues.append('Reached header or bank boundary'); break
            ins = gb_instruction(data,pc); instructions.append(ins); pc += ins['size']
            if ins['issue']: issues.append(ins['issue'])
            if ins['stop']: targets = ins['targets']; break
        else: targets = [pc]
        next_blocks = []
        for target in targets:
            if 0 <= target < min(len(data),0x4000) and not 0x104 <= target < 0x150:
                next_blocks.append({'address':target,'mode':'sm83'})
            else: issues.append(f'Unresolved banked/non-ROM target 0x{target:04x}')
    else:
        tool = shutil.which('arm-none-eabi-objdump')
        if not tool: raise ValueError('Install ARM binutils: arm-none-eabi-objdump is required')
        if mode not in ('arm','thumb'): raise ValueError('Expected ARM or Thumb mode')
        width = 4 if mode == 'arm' else 2
        if address % width or not 0x08000000 <= address < 0x08000000+len(data):
            raise ValueError('Unaligned or non-ROM GBA address')
        end = min(address + max_instructions*4, 0x08000000+len(data))
        command = [tool,'-D','-z','-b','binary','-m','armv4t','--adjust-vma=0x08000000',
                   f'--start-address={address}',f'--stop-address={end}']
        if mode == 'thumb': command.append('-Mforce-thumb')
        result = subprocess.run([*command,str(rom)],capture_output=True,text=True,check=True,timeout=30)
        next_blocks = []
        for line in result.stdout.splitlines():
            match = re.match(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8}(?: [0-9a-f]{4})?)\s+(.+)',line)
            if not match: continue
            pc, raw, asm = int(match[1],16),match[2],match[3].strip()
            size = len(raw.replace(' ',''))//2
            off = pc-0x08000000
            ins = {'address':pc,'size':size,'bytes':data[off:off+size].hex(),'asm':asm}
            instructions.append(ins)
            mnemonic = asm.split()[0]
            if mnemonic.endswith('.n'): mnemonic = mnemonic[:-2]
            # Direct branches and calls, including ARM condition suffixes.
            branch = re.fullmatch(r'(b|bl)(eq|ne|cs|hs|cc|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le|al)?',mnemonic)
            if branch:
                dest = re.search(r'\b0x([0-9a-f]+)',asm)
                if dest:
                    target = int(dest[1],16)
                    if 0x08000000 <= target < 0x08000000+len(data): next_blocks.append({'address':target,'mode':mode})
                    else: issues.append(f'Branch outside ROM: 0x{target:08x}')
                else: issues.append('Unresolved branch target')
                if branch[1] == 'bl' or branch[2] not in (None,'al'): next_blocks.append({'address':pc+size,'mode':mode})
                break
            operands = asm[len(mnemonic):].split(';')[0].strip()
            if mnemonic.startswith(('bx','blx')) or re.search(r'\bpc\b',operands.split(',')[0]) or (mnemonic.startswith(('pop','ldm')) and 'pc' in operands):
                issues.append('Computed PC / ARM-Thumb transition needs resolved target'); break
            if mnemonic.startswith(('.','undefined')) or 'undefined' in asm:
                issues.append('Undecodable instruction / possible data'); break
            if len(instructions) >= max_instructions:
                next_blocks.append({'address':pc+size,'mode':mode}); break
        else:
            if instructions: issues.append('Reached disassembly boundary')
    if not instructions: raise ValueError('No instructions at selected entry')
    return {'address':address,'mode':mode,'instructions':instructions,
            'next':next_blocks,'issues':issues,
            'caveat':'Static reachable block candidate; code/data and behavior are not validated.'}
