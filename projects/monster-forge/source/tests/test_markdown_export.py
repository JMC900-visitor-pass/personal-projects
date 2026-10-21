import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import app
import markdown_export as export
from test_forge import fixture


class MarkdownExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self.tmp.name)
        with patch.object(app, 'DB_PATH', self.directory / 'test.sqlite3'):
            app.init_db()
            with patch.object(app, 'ollama', return_value={'message': {'content': json.dumps(fixture(app.SCHEMA))}}):
                self.monster = app.build_monster(dict(name='The Antler: Elder / Stag',description='A woodland guardian.',
                    type='fey',cr='3',level=5,role='skirmisher',model='test-model'))

    def tearDown(self):
        self.tmp.cleanup()

    def test_complete_note_and_source_provenance(self):
        note = export.render_markdown(self.monster, 'The Whispering Wood\n[[Lantern Keepers]]\nThe Whispering Wood')
        self.assertTrue(note.startswith('---\n'))
        self.assertIn('challenge_rating: "3"', note)
        self.assertIn('xp: 700', note)
        self.assertIn('[[The Whispering Wood]]', note)
        self.assertIn('[[Lantern Keepers]]', note)
        self.assertIn('## Campaign notes', note)
        self.assertIn('## Loot and rewards', note)
        self.assertIn(export.CSV_URL, note)
        self.assertIn('test-model', note)
        self.assertIn('green-hag', note)
        self.assertIn('Monster Manual (SRD)', note)
        self.assertIn('dataset_sha256:', note)
        self.assertIn('### Original creative brief', note)
        self.assertNotIn('level:', note)
        self.assertNotIn('| Level |', note)
        self.assertIn('jason-oneal/dnd-5e-dataset', note)
        self.assertIn('lara-martin/FIREBALL', note)
        self.assertIn('CC BY 4.0', note)
        self.assertIn('Source SHA-256', note)

    def test_filename_and_table_escaping(self):
        self.monster['loot'][0]['description'] = 'A | B\nnext line'
        result = export.export_to_folder(self.monster, str(self.directory))
        path = Path(result['path'])
        self.assertEqual(path.parent, self.directory.resolve())
        self.assertNotIn('/', path.name)
        self.assertNotIn(':', path.name)
        self.assertIn(r'A \| B next line', path.read_text())
        self.assertTrue(Path(result['guide_path']).is_file())

    def test_repeated_export_preserves_edited_notes_and_guide(self):
        first = export.export_to_folder(self.monster, str(self.directory))
        Path(first['path']).write_text('My campaign edits')
        Path(first['guide_path']).write_text('My guide edits')
        second = export.export_to_folder(self.monster, str(self.directory))
        self.assertNotEqual(first['path'], second['path'])
        self.assertEqual(Path(first['path']).read_text(), 'My campaign edits')
        self.assertEqual(Path(first['guide_path']).read_text(), 'My guide edits')

    def test_invalid_folder_or_links_never_create_export(self):
        for folder, links in [('', ''), (str(self.directory / 'missing'), ''), (str(self.directory), 'bad[[link')]:
            with self.assertRaises(ValueError):
                export.export_to_folder(self.monster, folder, links)
        self.assertEqual(list(self.directory.glob('*.md')), [])

    def test_guide_can_be_excluded(self):
        result = export.export_to_folder(self.monster, str(self.directory), include_guide=False)
        self.assertIsNone(result['guide_path'])
        self.assertEqual(len(list(self.directory.glob('*.md'))), 1)

    def test_folder_browser_shows_folders_only(self):
        (self.directory / 'World').mkdir()
        (self.directory / '.obsidian').mkdir()
        (self.directory / 'note.md').write_text('hello')
        result = export.browse_folders(str(self.directory))
        self.assertEqual([f['name'] for f in result['folders']], ['World'])
        self.assertEqual(result['path'], str(self.directory.resolve()))


if __name__ == '__main__':
    unittest.main()
