import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer
import app
import world


class WorldTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.vault = self.root / 'Vault'
        self.folder = self.vault / 'World'
        self.folder.mkdir(parents=True)
        self.patch = patch.object(world, 'DB_PATH', self.root / 'world.sqlite3')
        self.patch.start()
        self.settings = dict(name='Riverworld', vault=str(self.vault), folder=str(self.folder),
            seed='A sleeping giant', tone='Hopeful', geography='River valley',
            factions='Ferrymen', canon_constraints='The giant must not wake.')
        world.save_settings(self.settings)

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def note(self, name, content):
        path = self.folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def test_settings_schemas_and_restore(self):
        state = world.status()
        self.assertEqual(state['settings']['seed'], self.settings['seed'])
        self.assertEqual(set(state['schemas']), set(world.FIELDS))
        self.assertNotIn('level', str(state['schemas']))
        self.assertIn('1/2', state['schemas']['creature']['properties']['challenge_rating']['enum'])
        identity = state['settings']['id']
        world.save_settings({**self.settings, 'tone': 'Dark'})
        self.assertEqual(world.status()['settings']['id'], identity)
        self.assertEqual(world.status()['settings']['tone'], 'Dark')

    def test_graph_yaml_and_manual_canon_refresh(self):
        city = self.note('Rivergate.md', '---\nid: city-1\nname: Rivergate\nkind: city\npopulation: "1500"\neconomy: Trade\nfactions:\n  - Ferrymen\n---\nThe giant sleeps. [[Shop|Old shop]]')
        shop = self.note('Shop.md', '---\nid: shop-1\nname: Shop\nkind: building\npurpose: General store\nowner: Mara\nparent: city-1\nrelationships: ["[[Rivergate]]"]\n---\nHandwritten canon.')
        (self.vault / 'Private.md').write_text('OUTSIDE CANON')
        before = shop.read_bytes()
        result = world.scan(True)
        self.assertEqual(len(result['graph']['entities']), 2)
        self.assertTrue(all(e['status'] == 'resolved' for e in result['graph']['relationships']))
        self.assertEqual(result['graph']['entities'][0]['properties']['factions'], ['Ferrymen'])
        city.write_text(city.read_text().replace('The giant sleeps.', 'The giant has awakened.'))
        updated = world.scan(True)
        canon = next(e for e in updated['canon'] if e['id'] == 'city-1')
        self.assertIn('has awakened', canon['content'])
        self.assertNotEqual(canon['hash'], result['canon'][0]['hash'])
        self.assertEqual(shop.read_bytes(), before)
        self.assertNotIn('OUTSIDE CANON', json.dumps(updated))

    def test_identity_survives_edits_restart_and_unambiguous_rename(self):
        path = self.note('Old.md', 'Original prose')
        first = world.scan()['graph']['entities'][0]['id']
        path.write_text('Manual edits')
        self.assertEqual(world.scan()['graph']['entities'][0]['id'], first)
        path.rename(self.folder / 'New.md')
        self.assertEqual(world.scan()['graph']['entities'][0]['id'], first)
        self.assertEqual(world.status()['graph']['entities'][0]['id'], first)
        path = self.folder / 'New.md'
        path.rename(self.folder / 'Third.md')
        self.assertEqual(world.scan()['graph']['entities'][0]['id'], first)
        path = self.folder / 'Third.md'
        path.unlink()
        world.scan()
        path.write_text('Manual edits')
        self.assertEqual(world.scan()['graph']['entities'][0]['id'], first)

    def test_boundary_symlinks_and_replaced_root(self):
        outside = self.root / 'Outside'
        outside.mkdir()
        (outside / 'Secret.md').write_text('SECRET')
        self.note('Safe.md', 'Safe')
        (self.folder / 'escape').symlink_to(outside, target_is_directory=True)
        (self.folder / 'secret.md').symlink_to(outside / 'Secret.md')
        result = world.scan(True)
        self.assertEqual(len(result['canon']), 1)
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertEqual(len(result['graph']['diagnostics']), 2)
        with self.assertRaises(ValueError):
            world.save_settings({**self.settings, 'folder': str(outside)})
        with self.assertRaises(ValueError):
            world.save_settings({**self.settings, 'folder': str(self.folder / 'escape')})
        self.folder.rename(self.vault / 'Original')
        self.folder.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            world.scan(True)
        self.assertEqual(world.status()['graph'], result['graph'])

    def test_duplicates_unresolved_ambiguous_and_schema_diagnostics(self):
        self.note('A.md', '---\nid: duplicate\nkind: creature\nchallenge_rating: "99"\n---\n[[Missing]] [[Same]]')
        self.note('B.md', '---\nid: duplicate\n---')
        self.note('one/Same.md', 'First')
        self.note('two/Same.md', 'Second')
        result = world.scan(True)
        diagnostics = '\n'.join(result['graph']['diagnostics'])
        for issue in ('duplicate entity ID', 'unresolved', 'ambiguous', 'valid challenge_rating'):
            self.assertIn(issue, diagnostics)
        self.assertFalse(result['ready_for_expansion'])

    def test_invalid_yaml_retained_and_scans_fail_without_replacing_index(self):
        self.note('Nested.md', '---\nname: Keep me\ncustom:\n  nested: value\n---\nManual prose')
        result = world.scan(True)
        self.assertIn('nested: value', result['graph']['entities'][0]['yaml'])
        self.assertTrue(result['graph']['diagnostics'])
        self.note('Bad.md', 'x' * 2_000_001)
        with self.assertRaises(ValueError):
            world.scan()
        self.assertEqual(world.status()['graph'], result['graph'])

    def test_switching_folder_clears_graph(self):
        self.note('Note.md', 'Canon')
        world.scan()
        other = self.vault / 'Other'
        other.mkdir()
        state = world.save_settings({**self.settings, 'folder': str(other)})
        self.assertIsNone(state['graph'])
        self.assertEqual(world.scan(True)['canon'], [])

    def test_api_roundtrip(self):
        self.note('Canon.md', 'Current canon')
        server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with urlopen(base + '/api/world') as response:
                self.assertEqual(json.load(response)['settings']['name'], 'Riverworld')
            for endpoint in ('index', 'canon'):
                request = Request(base + '/api/world/' + endpoint, data=b'{}', headers={'Content-Type': 'application/json'})
                with urlopen(request) as response:
                    result = json.load(response)
                self.assertEqual(len(result['graph']['entities']), 1)
                if endpoint == 'canon':
                    self.assertEqual(result['canon'][0]['content'], 'Current canon')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
