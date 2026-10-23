"""App builds must stage and use the locally compiled translator, never prebuilt/."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import build_app

ROOT = Path(__file__).resolve().parents[1]


class SourceTranslatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source/totk_xlate'
        self.write_translator(self.source, b'locally compiled translator')
        self.tree = self.root / 'work/totk'

    def write_translator(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        path.chmod(0o755)
        path.with_suffix('.sha256').write_text(build_app.sha256(path) + '\n')

    def stage_fixture(self):
        staged = self.tree / build_app.STAGED_TRANSLATOR
        self.write_translator(staged, b'locally compiled translator')
        tool = self.tree / 'build/spirv-cross/spirv-cross'
        tool.parent.mkdir(parents=True, exist_ok=True)
        tool.write_bytes(b'test tool')
        # A different legacy executable must not be selected even when present.
        legacy = self.tree / 'prebuilt/macos-arm64/totk_xlate'
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(b'legacy precompiled translator')
        return staged

    def test_accepts_valid_source_build(self):
        self.assertEqual(build_app.checked_translator(self.source), self.source)

    def test_missing_executable_requests_source_build(self):
        self.source.unlink()
        with self.assertRaisesRegex(build_app.BuildError, 'just build-translator'):
            build_app.checked_translator(self.source)

    def test_missing_hash_requests_source_build(self):
        self.source.with_suffix('.sha256').unlink()
        with self.assertRaisesRegex(build_app.BuildError, 'just build-translator'):
            build_app.checked_translator(self.source)

    def test_changed_binary_is_rejected(self):
        self.source.write_bytes(b'changed binary')
        with self.assertRaisesRegex(build_app.BuildError, 'SHA-256'):
            build_app.checked_translator(self.source)

    def test_non_executable_file_is_rejected(self):
        self.source.chmod(0o644)
        with self.assertRaisesRegex(build_app.BuildError, 'execute permission'):
            build_app.checked_translator(self.source)

    def test_legacy_binary_does_not_satisfy_missing_source_build(self):
        self.stage_fixture()
        self.source.unlink()
        with mock.patch.object(build_app, 'SOURCE_TRANSLATOR', self.source), \
             mock.patch.object(build_app, 'local_python_dependencies', return_value=(self.root/'lock', self.root/'wheels')), \
             mock.patch.object(build_app, 'run') as run:
            with self.assertRaisesRegex(build_app.BuildError, 'just build-translator'):
                build_app.prepare_work(self.root/'work', Path('/usr/bin/python3'), self.root/'logs')
        run.assert_not_called()

    def test_work_directory_gets_verified_private_copy_of_source_build(self):
        staged = self.stage_fixture()
        staged.write_bytes(b'stale work-folder helper')
        with mock.patch.object(build_app, 'SOURCE_TRANSLATOR', self.source), \
             mock.patch.object(build_app, 'local_python_dependencies', return_value=(self.root/'lock', self.root/'wheels')), \
             mock.patch.object(build_app, 'local_source'), mock.patch.object(build_app, 'run') as run:
            tree = build_app.prepare_work(self.root/'work', Path('/usr/bin/python3'), self.root/'logs')
        self.assertEqual(staged, tree / build_app.STAGED_TRANSLATOR)
        self.assertEqual(staged.read_bytes(), self.source.read_bytes())
        self.assertEqual(build_app.checked_translator(staged), staged)
        self.assertIn('--exclude=/prebuilt', run.call_args_list[0].args[0])
        self.write_translator(self.source, b'next source build')
        self.assertEqual(staged.read_bytes(), b'locally compiled translator')

    def test_totk_shader_preparation_uses_staged_source_build(self):
        staged = self.stage_fixture()
        with mock.patch.object(build_app, 'run') as run:
            build_app.step_shaders(self.tree, self.root/'logs', version='v143')
        command = run.call_args.args[0]
        self.assertEqual(command[command.index('--translator') + 1], staged)

    def test_botw_shader_preparation_uses_staged_source_build(self):
        staged = self.stage_fixture()
        with mock.patch.object(build_app, 'run') as run:
            build_app.step_shaders_botw(self.tree, self.root/'botw', self.root/'logs')
        command = run.call_args.args[0]
        self.assertEqual(command[command.index('--translator') + 1], staged)

    @unittest.skipUnless(shutil.which('just'), 'just is not installed')
    def test_just_translator_recipe_matches_app_input_without_rebuilding_on_every_game_build(self):
        result = subprocess.run(['just', '--dry-run', 'build-translator'], cwd=ROOT, capture_output=True, text=True, check=True)
        commands = result.stdout + result.stderr
        self.assertIn('publish_native.sh', commands)
        self.assertIn(str(build_app.SOURCE_TRANSLATOR.parent.relative_to(ROOT)), commands)
        game = subprocess.run(['just', '--dry-run', 'build'], cwd=ROOT, capture_output=True, text=True, check=True)
        self.assertIn('build_app.py', game.stdout + game.stderr)
        self.assertNotIn('publish_native.sh', game.stdout + game.stderr)


if __name__ == '__main__':
    unittest.main()
