"""Regression tests use temporary stores only; never write to user accounts."""
import ast
import hashlib
import json
import os
from pathlib import Path
import string
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import csm
import csbridge
import cspack
import i18n


class Bundles(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='csm-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.projects = self.root / 'source-home' / 'projects'
        self.source_cwd = self.root / 'source_project with spaces'
        self.target_cwd = self.root / 'target-project'
        self.store = self.root / 'claude-code-sessions'
        self.cli = 'source-cli-id'
        self.project = self.projects / csbridge.claude_project_dir_name(str(self.source_cwd))
        self.project.mkdir(parents=True)
        self.source_cwd.mkdir()
        self.store.mkdir()
        self.transcript = self.project / (self.cli + '.jsonl')
        self.transcript.write_text(json.dumps({'type': 'user', 'sessionId': self.cli,
            'cwd': str(self.source_cwd), 'message': {'role': 'user', 'content': 'hello'}}) + '\n', encoding='utf-8')
        self.write(self.project / self.cli / 'subagents' / 'agent-demo.jsonl', str(self.source_cwd))
        self.write(self.project / 'memory' / 'notes.md', 'source memory')
        self.write(self.root / 'scratch' / self.project.name / self.cli / 'task.txt', 'scratch')
        for part, sub in cspack.SESSION_DIRS.items():
            self.write(self.projects.parent / sub / self.cli / 'data.txt', str(self.source_cwd))
        self.write(self.source_cwd / '.claude' / 'agents' / 'demo.md', 'source agent')
        self.write(self.source_cwd / '.claude' / 'node_modules' / 'skip.txt', 'do not include')
        self.session = {'kind': 'code', 'path': None, 'rel': None, 'cli': self.cli,
            'sid': None, 'cwd': str(self.source_cwd), 'title': 'Demo session',
            'last': 1700000000000, 'transcript': self.transcript, 'tr_size': self.transcript.stat().st_size}
        for p in [patch.object(csm, 'projects_dir', lambda: self.projects),
                  patch.object(csm, 'existing_bases', lambda kind='code': [self.store]),
                  patch.object(cspack, 'claude_temp_root', lambda: self.root / 'scratch'),
                  patch.object(csbridge, 'codex_home', lambda: self.root / 'codex'),
                  patch.object(csbridge, 'detect_claude_version', lambda: 'test')]:
            p.start()
            self.addCleanup(p.stop)

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')

    def export(self, include=None):
        bundle = self.root / 'demo.csmpack'
        manifest = cspack.export_bundle([cspack.make_item('code', self.session)], bundle, include=include)
        return bundle, manifest, manifest['sessions'][0]

    def restore(self, bundle, manifest, entry, **kwargs):
        self.projects = self.root / 'target-home' / 'projects'
        return cspack.import_entry(bundle, entry, manifest=manifest,
            cwd_map={str(self.source_cwd): str(self.target_cwd)}, **kwargs)

    def test_terminal_export_includes_new_parts_and_skips_dependencies(self):
        bundle, manifest, entry = self.export()
        self.assertEqual(set(entry['parts']), {'transcript', 'extras', 'memory', 'scratch',
            'file_history', 'session_env', 'todos', 'project_config'})
        with zipfile.ZipFile(bundle) as z:
            self.assertFalse(any('node_modules' in n for n in z.namelist()))
        self.assertEqual(cspack.read_bundle(bundle), manifest)

    def test_optional_groups_are_excluded(self):
        _, _, entry = self.export(include={'transcript'})
        self.assertEqual(set(entry['parts']), {'transcript'})

    def test_restore_preserves_existing_files_and_maps_paths(self):
        bundle, manifest, entry = self.export()
        target_project = self.root / 'target-home' / 'projects' / csbridge.claude_project_dir_name(str(self.target_cwd))
        self.write(target_project / 'memory' / 'notes.md', 'existing memory')
        self.write(self.target_cwd / '.claude' / 'agents' / 'demo.md', 'existing agent')
        source_hash = hashlib.sha256(self.transcript.read_bytes()).hexdigest()
        result = self.restore(bundle, manifest, entry, account=None)
        self.assertEqual(result['status'], 'ok', result)
        self.assertTrue(result['skipped_memory'])
        self.assertTrue(result['skipped_project'])
        self.assertEqual((target_project / 'memory' / 'notes.md').read_text(), 'existing memory')
        self.assertEqual((self.target_cwd / '.claude' / 'agents' / 'demo.md').read_text(), 'existing agent')
        record = json.loads((target_project / (self.cli + '.jsonl')).read_text())
        self.assertEqual(record['cwd'], str(self.target_cwd))
        for sub in cspack.SESSION_DIRS.values():
            path = self.projects.parent / sub / self.cli / 'data.txt'
            self.assertEqual(path.read_text(), str(self.target_cwd))
        self.assertEqual(hashlib.sha256(self.transcript.read_bytes()).hexdigest(), source_hash)

    def test_explicit_overwrite_replaces_project_and_memory(self):
        bundle, manifest, entry = self.export()
        target_project = self.root / 'target-home' / 'projects' / csbridge.claude_project_dir_name(str(self.target_cwd))
        self.write(target_project / 'memory' / 'notes.md', 'existing memory')
        self.write(self.target_cwd / '.claude' / 'agents' / 'demo.md', 'existing agent')
        result = self.restore(bundle, manifest, entry, overwrite_memory=True, overwrite_project=True)
        self.assertEqual(result['status'], 'ok', result)
        self.assertEqual((target_project / 'memory' / 'notes.md').read_text(), 'source memory')
        self.assertEqual((self.target_cwd / '.claude' / 'agents' / 'demo.md').read_text(), 'source agent')

    def test_terminal_restore_creates_target_desktop_record(self):
        bundle, manifest, entry = self.export()
        account = {'id': 'target-account', 'dir': self.store / 'target-account', 'sessions': [], 'email':'demo@example.com'}
        result = self.restore(bundle, manifest, entry, account=account)
        self.assertEqual(result['status'], 'ok', result)
        records = list(self.store.rglob('local_*.json'))
        self.assertEqual(len(records), 1)
        record = json.loads(records[0].read_text())
        self.assertEqual(record['cliSessionId'], self.cli)
        self.assertEqual(record['cwd'], str(self.target_cwd))
        self.assertIn('target-account', records[0].parts)

    def test_owner_bound_transfer_clones_and_preserves_source(self):
        record_path = self.root / 'source-account' / 'workspace-a' / 'local_source.json'
        record = {'sessionId': 'local_source', 'cliSessionId': self.cli,
            'cwd': str(self.source_cwd), 'bridgeSessionIds': ['source-cloud-id']}
        self.write(record_path, json.dumps(record))
        data = {'type': 'user', 'ownerAccountUuid': 'source-account', 'sessionId': self.cli,
            'cwd': str(self.source_cwd), 'message': {'role':'user','content':'hello'}}
        self.transcript.write_text(json.dumps(data) + '\n')
        original = self.transcript.read_bytes()
        session = {**self.session, 'path':record_path, 'entry':record,
            'sid':'local_source', 'rel':Path('source-account/workspace-a/local_source.json')}
        written, errors = csm.perform_copy([self.store], session,
            Path('target-account/workspace-b/local_source.json'))
        self.assertFalse(errors, errors)
        target_record = json.loads(written[0].read_text())
        self.assertNotEqual(target_record['cliSessionId'], self.cli)
        self.assertEqual(target_record['bridgeSessionIds'], [])
        target_transcript = self.project / (target_record['cliSessionId'] + '.jsonl')
        self.assertEqual(json.loads(target_transcript.read_text())['ownerAccountUuid'], 'target-account')
        self.assertEqual(self.transcript.read_bytes(), original)
        self.assertTrue((self.project / target_record['cliSessionId'] / 'subagents' / 'agent-demo.jsonl').exists())


class Translations(unittest.TestCase):
    def test_languages_and_placeholders_match(self):
        formatter = string.Formatter()
        for key, values in i18n.T.items():
            with self.subTest(key=key):
                self.assertEqual(set(values), {'en', 'tr'})
                fields = lambda text: sorted(name for _, name, _, _ in formatter.parse(text) if name is not None)
                self.assertEqual(fields(values['en']), fields(values['tr']))

    def test_literal_translation_calls_exist(self):
        for name in ('csm.py', 'csmui.py', 'csbridge.py', 'cspack.py'):
            tree = ast.parse((ROOT / name).read_text(encoding='utf-8-sig'))
            for call in ast.walk(tree):
                if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == 't' and call.args:
                    key = call.args[0]
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        self.assertIn(key.value, i18n.T, name + ': ' + key.value)


if __name__ == '__main__':
    unittest.main()
