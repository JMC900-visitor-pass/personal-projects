"""Run: python3 -m unittest discover -s tests -v. No Ollama or user ROM required."""
from pathlib import Path
import hashlib
import importlib
import json
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'launcher'))
import backend
import conversion
import rom_analysis as analysis


def cartridge(system='GB'):
    data = bytearray(32768)
    if system == 'GBA':
        data[:4] = bytes.fromhex('2e0000ea')  # b 0x080000c0
        data[0xc0:0xc4] = bytes.fromhex('feffffea')  # b self
        data[0xa0:0xac] = b'TEST CART   '
        data[0xac:0xb0] = b'TSTE'
        data[0xb2] = 0x96
        data[0xbd] = (-sum(data[0xa0:0xbd])-0x19)&255
    else:
        data[0x100:0x104] = bytes.fromhex('00c35001')  # nop; jp 0x150
        data[0x150:0x152] = bytes.fromhex('18fe')  # jr self
        data[0x134:0x13b] = b'TEST GB'
        data[0x143] = 0x80 if system == 'GBC' else 0
        data[0x14d] = (-sum(data[0x134:0x14d])-25)&255
        total = sum(data)&65535
        data[0x14e:0x150] = total.to_bytes(2,'big')
    return data


class Workspace(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.state = self.root/'state'; self.state.mkdir()
        self.patches = [patch.object(backend,'STATE',self.state),patch.object(conversion,'STATE',self.state)]
        for item in self.patches:item.start()
        self.db = {}

    def tearDown(self):
        for item in self.patches:item.stop()
        self.temp.cleanup()

    def add(self,system='GB',name='Selected Game'):
        rom = self.root/(name+'.'+system.lower()); rom.write_bytes(cartridge(system))
        backend.import_one(rom,self.db)
        sha = hashlib.sha1(rom.read_bytes()).hexdigest()
        return self.db[sha],sha,rom


class HeaderTests(Workspace):
    def test_all_systems_and_filename_preserved(self):
        for system in ('GB','GBC','GBA'):
            game,sha,rom = self.add(system,name='Chosen '+system)
            self.assertEqual(game['system'],system)
            self.assertEqual(game['name'],'Chosen '+system)
            self.assertEqual(Path(game['path']).read_bytes(),rom.read_bytes())
        backend.publish(self.db)
        self.assertEqual(len((self.state/'library.tsv').read_text().splitlines()),3)

    def test_cgb_detected_by_header_even_with_gb_extension(self):
        p = self.root/'color.gb';p.write_bytes(cartridge('GBC'))
        self.assertEqual(analysis.identify(p)['system'],'GBC')

    def test_bad_headers_rejected(self):
        for system in ('GB','GBC','GBA'):
            data=cartridge(system);data[0xb2 if system=='GBA' else 0x134]^=1
            p=self.root/('bad.'+system.lower());p.write_bytes(data)
            with self.assertRaises(ValueError):backend.import_one(p,self.db)
        self.assertFalse(self.db)

    def test_size_limits(self):
        p=self.root/'tiny.gb';p.write_bytes(b'123')
        with self.assertRaises(ValueError):analysis.identify(p)

    def test_reimport_keeps_user_label(self):
        game,sha,rom=self.add();self.db[sha]['name']='My custom title'
        backend.import_one(rom,self.db)
        self.assertEqual(self.db[sha]['name'],'My custom title')

    def test_project_hash_is_identity(self):
        game,sha,_=self.add(name='Same title')
        a=conversion.project_path(game,sha)
        b=conversion.project_path(game,'a'*40)
        self.assertNotEqual(a,b)
        self.assertIn('Same-title',a.name)
        project,_=conversion.prepare(game,sha)
        game['name']='renamed'
        self.assertEqual(conversion.project_path(game,sha),project)


class DecoderTests(Workspace):
    def test_sm83_entry_and_self_loop(self):
        game,sha,_=self.add()
        evidence=analysis.block(game['path'],'GB',0x100,'sm83')
        self.assertEqual([x['asm'] for x in evidence['instructions']],['nop','jp 0x0150'])
        self.assertEqual(evidence['next'],[{'address':0x150,'mode':'sm83'}])
        loop=analysis.block(game['path'],'GB',0x150,'sm83')
        self.assertEqual(loop['next'][0]['address'],0x150)

    def test_sm83_opcode_groups(self):
        samples = {'010034':('ld bc,0x3400',3),'cb7e':('bit 7,[hl]',2),
                   'f8ff':('ld hl,sp+(-1)',2),'e0ff':('ldh [0xffff],a',2),
                   'd9':('reti',1),'e9':('jp hl',1),'f1':('pop af',1)}
        for raw,(asm,size) in samples.items():
            ins=analysis.gb_instruction(bytes.fromhex(raw)+bytes(4),0)
            self.assertEqual((ins['asm'],ins['size']),(asm,size))

    def test_all_sm83_opcodes_and_illegal_set(self):
        illegal=[]
        for op in range(256):
            ins=analysis.gb_instruction(bytes([op,0,0,0]),0)
            self.assertIn(ins['size'],(1,2,3))
            if ins['asm'].startswith('illegal'):illegal.append(op)
        self.assertEqual(illegal,[0xd3,0xdb,0xdd,0xe3,0xe4,0xeb,0xec,0xed,0xf4,0xfc,0xfd])

    def test_conditional_branch_has_both_successors(self):
        data=bytes.fromhex('2006')+bytes(8)
        self.assertEqual(analysis.gb_instruction(data,0)['targets'],[8,2])

    def test_bank_switch_not_guessed(self):
        game,_,_=self.add()
        with self.assertRaisesRegex(ValueError,'bank'):analysis.block(game['path'],'GB',0x4000,'sm83')

    @unittest.skipUnless(shutil.which('arm-none-eabi-objdump'),'ARM binutils unavailable')
    def test_arm_and_thumb_disassembly(self):
        game,_,rom=self.add('GBA')
        evidence=analysis.block(rom,'GBA',0x08000000,'arm')
        self.assertEqual(evidence['next'],[{'address':0x080000c0,'mode':'arm'}])
        self.assertEqual(evidence['instructions'][0]['bytes'],'2e0000ea')
        data=bytearray(rom.read_bytes());data[0xc0:0xc2]=bytes.fromhex('fee7');rom.write_bytes(data)
        self.assertEqual(analysis.block(rom,'GBA',0x080000c0,'thumb')['next'][0]['address'],0x080000c0)


class RecoveryTests(Workspace):
    def fake_request(self,endpoint,payload=None,timeout=20):
        if endpoint == '/api/show':return {}
        if endpoint == '/api/chat':
            prompt=payload['messages'][0]['content']
            key=prompt.split('void block_',1)[1].split('(',1)[0]
            source=f'#include "recovery.h"\n/* Instructions executed in system mode. */\nvoid block_{key}(Machine *m) {{ m->pc = 0x150; }}'
            return {'message':{'content':json.dumps({'c_source':source,'explanation':'fixture','unresolved':['timing']})}}
        raise AssertionError(endpoint)

    @unittest.skipUnless(shutil.which('clang'),'Clang unavailable')
    def test_recovery_compile_resume_and_no_false_playable(self):
        game,sha,_=self.add()
        with patch.object(conversion,'local_models',return_value=[conversion.DEFAULT_MODEL]),patch.object(conversion,'request',side_effect=self.fake_request):
            project=conversion.recover(game,sha,limit=1)
            original=(project/'src/sm83_00000100.c').read_bytes()
            conversion.recover(game,sha,limit=3)
            self.assertEqual((project/'src/sm83_00000100.c').read_bytes(),original)
        manifest=json.loads((project/'project.json').read_text())
        self.assertEqual(len(manifest['units']),2)
        self.assertEqual(manifest['queue'],[])
        self.assertFalse(manifest['playable'])
        self.assertTrue(all(u['compiled'] and not u['validated'] for u in manifest['units'].values()))
        conversion.build_drafts(game,sha)
        backend.publish(self.db)
        self.assertIn('\tdraft\t',(self.state/'library.tsv').read_text())

    def test_failure_persists_queue_for_retry(self):
        game,sha,_=self.add()
        with patch.object(conversion,'local_models',side_effect=RuntimeError('Ollama offline')):
            with self.assertRaisesRegex(RuntimeError,'offline'):conversion.recover(game,sha,1)
        manifest=conversion.manifest_for(game,sha)
        self.assertEqual(manifest['status'],'error')
        self.assertEqual(len(manifest['queue']),1)
        self.assertFalse(manifest['playable'])

    def test_tampered_rom_refused(self):
        game,sha,_=self.add();Path(game['path']).write_bytes(cartridge('GBC'))
        with self.assertRaisesRegex(ValueError,'changed'):conversion.prepare(game,sha)

    def test_empty_compile_is_not_success(self):
        game,sha,_=self.add()
        with self.assertRaisesRegex(ValueError,'no C drafts'):conversion.build_drafts(game,sha)

    def test_exhausted_queue_does_not_call_model(self):
        game,sha,_=self.add();project,manifest=conversion.prepare(game,sha)
        manifest['queue']=[];conversion.save(project,manifest)
        with patch.object(conversion,'request',side_effect=AssertionError('Should not contact model')):
            conversion.recover(game,sha,1)
        self.assertFalse(conversion.manifest_for(game,sha)['playable'])

    @unittest.skipUnless(shutil.which('clang'),'Clang unavailable')
    def test_edited_draft_preserved_after_interruption(self):
        game,sha,_=self.add();project,_=conversion.prepare(game,sha)
        source=project/'src/sm83_00000100.c'
        text='#include "recovery.h"\nvoid block_sm83_00000100(Machine *m) { m->pc=0x150; } /* hand edited */\n'
        source.write_text(text)
        with patch.object(conversion,'local_models',return_value=[conversion.DEFAULT_MODEL]),patch.object(conversion,'request',side_effect=self.fake_request):
            conversion.recover(game,sha,1)
        self.assertEqual(source.read_text(),text)

    @unittest.skipUnless(shutil.which('clang'),'Clang unavailable')
    def test_failed_rebuild_clears_stale_object(self):
        game,sha,_=self.add();project,_=conversion.prepare(game,sha)
        source=project/'src/test.c';source.write_text('int fixture(void) { return 1; }')
        self.assertTrue(conversion.compile_one(project,source,'test')[0])
        source.write_text('this is not valid C')
        self.assertFalse(conversion.compile_one(project,source,'test')[0])
        self.assertFalse((project/'objects/test.o').exists())

    def test_project_lock(self):
        game,sha,_=self.add();project=conversion.project_path(game,sha)
        with conversion.lock(project):
            with self.assertRaisesRegex(ValueError,'already'):
                with conversion.lock(project):pass

    def test_cloud_models_filtered(self):
        models=[{'name':'local:1','size':2000000},{'name':'bad:cloud','size':2000000},
                {'name':'remote:1','size':2000000,'remote_host':'example.com'},
                {'name':'stub','size':100}]
        with patch.object(conversion,'request',return_value={'models':models}):
            self.assertEqual(conversion.local_models(),['local:1'])

    def test_cloud_show_refused(self):
        game,sha,_=self.add()
        with patch.object(conversion,'local_models',return_value=[conversion.DEFAULT_MODEL]),patch.object(conversion,'request',return_value={'remote_host':'example.com'}):
            with self.assertRaisesRegex(ValueError,'Cloud'):conversion.recover(game,sha,1)

    @unittest.skipUnless(shutil.which('clang'),'Clang unavailable')
    def test_compiler_feedback_repair_preserves_first_draft(self):
        game,sha,_=self.add()
        def answer(endpoint,payload=None,timeout=20):
            result=self.fake_request(endpoint,payload,timeout)
            if endpoint=='/api/chat' and 'Previous draft and compiler diagnostics' not in payload['messages'][0]['content']:
                value=json.loads(result['message']['content'])
                value['c_source']=value['c_source'].replace('m->pc = 0x150','m->nonexistent = 0x150')
                result['message']['content']=json.dumps(value)
            return result
        with patch.object(conversion,'local_models',return_value=[conversion.DEFAULT_MODEL]),patch.object(conversion,'request',side_effect=answer):
            project=conversion.recover(game,sha,1)
        self.assertIn('nonexistent',(project/'evidence/sm83_00000100.initial.c').read_text())
        self.assertTrue(conversion.manifest_for(game,sha)['units']['sm83_00000100']['compiled'])

    def test_malformed_response_retains_retry_queue(self):
        game,sha,_=self.add()
        def malformed(endpoint,payload=None,timeout=20):
            return {} if endpoint=='/api/show' else {'message':{'content':'not JSON'}}
        with patch.object(conversion,'local_models',return_value=[conversion.DEFAULT_MODEL]),patch.object(conversion,'request',side_effect=malformed):
            with self.assertRaises(ValueError):conversion.recover(game,sha,1)
        manifest=conversion.manifest_for(game,sha)
        self.assertEqual(len(manifest['queue']),1)
        self.assertEqual(manifest['units'],{})

    def test_native_build_locked_for_unknown_rom(self):
        game,sha,_=self.add();backend.publish(self.db)
        args=type('Args',(),{'action':'build','paths':[sha]})()
        with self.assertRaisesRegex(ValueError,'No validated native'):backend.run(args)


if __name__=='__main__':unittest.main()
