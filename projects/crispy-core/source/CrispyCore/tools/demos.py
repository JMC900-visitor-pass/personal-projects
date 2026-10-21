#!/usr/bin/env python3
"""Generate original, BIOS-free bring-up ROMs. No game or boot-ROM assets."""
from pathlib import Path
import struct, sys

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)

def gb(colour):
    rom = bytearray(32768)
    rom[0x100:0x104] = bytes([0, 0xc3, 0x50, 1])
    title = b'CRISPY GBC' if colour else b'CRISPY GB'
    rom[0x134:0x134+len(title)] = title
    rom[0x143] = 0x80 if colour else 0
    rom[0x147] = rom[0x148] = rom[0x149] = 0
    rom[0x14a] = 1
    checksum = 0
    for b in rom[0x134:0x14d]: checksum = (checksum-b-1)&255
    rom[0x14d] = checksum
    code = bytearray(); labels = {}; fixups = []
    def emit(*values): code.extend(values)
    def label(name): labels[name] = len(code)
    def jr(op, target): emit(op, 0); fixups.append((len(code)-1, target))
    emit(0xf3, 0x31, 0xfe, 0xff) # DI; LD SP,$FFFE
    emit(0xaf, 0xe0, 0x40) # LCD off
    emit(0x21, 0x00, 0x80) # LD HL,$8000
    for y in range(8):
        emit(0x36, 0xf0 if y&2 else 0x0f, 0x23)
        emit(0x36, 0xcc if y&2 else 0x33, 0x23)
    if colour:
        emit(0x3e, 0x80, 0xe0, 0x68)
        for b in [0xff,0x7f,0x1f,0,0xe0,3,0,0x7c]: emit(0x3e,b,0xe0,0x69)
    emit(0x3e, 0xe4, 0xe0, 0x47, 0x3e, 0x91, 0xe0, 0x40)
    # Serial handshake is observed by the headless runner.
    for index,b in enumerate((b'CRISPY GBC READY\n' if colour else b'CRISPY GB READY\n')):
        emit(0x3e,b,0xe0,1,0x3e,0x81,0xe0,2)
        label(f'serial{index}'); emit(0xf0,2,0xcb,0x7f); jr(0x20,f'serial{index}')
    label('forever'); emit(0x76); jr(0x18,'forever') # HALT; JR (LCD keeps running)
    for pos,target in fixups:
        offset = labels[target] - (pos+1)
        assert -128 <= offset < 128
        code[pos] = offset&255
    rom[0x150:0x150+len(code)] = code
    # Header intentionally omits Nintendo's logo and assumes a skipped boot ROM.
    (out/('crispy-demo.gbc' if colour else 'crispy-demo.gb')).write_bytes(rom)

def gba():
    rom = bytearray(32768)
    struct.pack_into('<I',rom,0,0xea00002e) # ARM branch to $080000C0
    rom[0xa0:0xac] = b'CRISPY GBA  '
    rom[0xb2] = 0x96
    words = [
        0xe59f0028, # LDR r0,=$04000000 (literal at $F0)
        0xe3a01b01, # MOV r1,#$400
        0xe3811003, # ORR r1,r1,#3
        0xe1c010b0, # STRH r1,[r0] -- Mode 3, BG2 enabled
        0xe59f001c, # LDR r0,=$06000000 (literal at $F4)
        0xe59f101c, # LDR r1,=38400 (literal at $F8)
        0xe3a02000, # MOV r2,#0
        0xe0c020b2, # STRH r2,[r0],#2
        0xe2822001, # ADD r2,r2,#1
        0xe2511001, # SUBS r1,r1,#1
        0x1afffffb, # BNE to STRH (pc+8 -20)
        0xeafffffe, # B forever
        0x04000000, 0x06000000, 38400,
    ]
    for i,word in enumerate(words): struct.pack_into('<I',rom,0xc0+i*4,word)
    rom[0xbd] = (-sum(rom[0xa0:0xbd])-0x19)&255
    (out/'crispy-demo.gba').write_bytes(rom)

def gba_startup():
    """Exercise startup modes, BIOS calls and a real VBlank IRQ callback."""
    rom = bytearray(32768)
    struct.pack_into('<I',rom,0,0xea00002e)
    rom[0xa0:0xac] = b'CRISPY BOOT '
    rom[0xb2] = 0x96
    words, labels, literals, branches = [], {}, [], []
    def emit(word): words.append(word)
    def label(name): labels[name] = 0x080000c0 + len(words)*4
    def load(reg, value):
        literals.append((len(words),reg,value));emit(0)
    def branch(name): branches.append((len(words),name));emit(0)
    for mode,stack in [(0xd2,0x03007fa0),(0xd3,0x03007fe0),(0x1f,0x03007f00)]:
        emit(0xe3a00000|mode);emit(0xe129f000);load(13,stack)
    emit(0xe3a000ff);emit(0xef010000) # RegisterRamReset all modeled memory/IO
    load(0,'colour');load(1,0x06000000);load(2,(1<<26)|(1<<24)|19200);emit(0xef0b0000)
    load(0,0x04000000);load(1,0x403);emit(0xe1c010b0) # Bitmap mode 3
    load(0,0x03007ffc);load(1,'irq');emit(0xe5801000)
    load(0,0x04000004);emit(0xe3a01008);emit(0xe1c010b0) # VBlank IRQ enable
    load(0,0x04000200);emit(0xe3a01001);emit(0xe1c010b0) # IE
    load(0,0x04000208);emit(0xe1c010b0) # IME
    label('wait');emit(0xef050000);branch('wait')
    label('irq')
    load(0,0x04000202);emit(0xe3a01001);emit(0xe1c010b0) # Acknowledge VBlank
    load(0,0x03007ff8);emit(0xe1d020b0);emit(0xe1822001);emit(0xe1c020b0) # BIOS flags
    load(0,0x02000000);emit(0xe5902000);emit(0xe2822001);emit(0xe5802000);emit(0xe12fff1e)
    label('colour');emit(0x03e003e0)
    for index,reg,value in literals:
        address=0x080000c0+len(words)*4
        offset=address-(0x080000c0+index*4+8)
        assert 0<=offset<4096
        words[index]=0xe59f0000|(reg<<12)|offset
        emit(labels[value] if isinstance(value,str) else value)
    for index,name in branches:
        offset=(labels[name]-(0x080000c0+index*4+8))//4
        words[index]=0xea000000|(offset&0xffffff)
    for index,word in enumerate(words): struct.pack_into('<I',rom,0xc0+index*4,word)
    rom[0xbd]=(-sum(rom[0xa0:0xbd])-0x19)&255
    (out/'crispy-startup.gba').write_bytes(rom)

gb(False); gb(True); gba(); gba_startup()
print(f'Original GB/GBC/GBA demo ROMs: {out}')
