"""Offline dependency staging: fail closed, verify snapshots, never fetch or resolve from an index."""
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import build_app


class OfflineDependencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.deps = self.root / 'dependencies'
        self.source = self.deps / 'sources/example'
        self.source.mkdir(parents=True)
        (self.source / 'source.c').write_bytes(b'verified source')
        self.game = self.root / 'game'
        self.game.mkdir()
        (self.game / 'requirements.txt').write_text('example==1.0\n')
        self.lock = self.deps / 'requirements-macos-arm64-py314.lock'
        self.lock.write_text('example==1.0 --hash=sha256:fake\n')
        self.wheel = self.deps / 'wheels/example.whl'
        self.wheel.parent.mkdir()
        self.wheel.write_bytes(b'wheel fixture')
        self.manifest = {
            'python': '3.14', 'platform': 'macos-arm64',
            'sources': {'example': {'files': {'source.c': build_app.sha256(self.source / 'source.c')}}},
            'requirements_sha256': build_app.sha256(self.lock),
            'input_requirements_sha256': build_app.sha256(self.game / 'requirements.txt'),
            'wheels': {self.wheel.name: build_app.sha256(self.wheel)},
        }
        (self.deps / 'manifest.json').write_text(json.dumps(self.manifest))
        self.patch = mock.patch.object(build_app, 'DEPENDENCIES', self.deps)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.game_patch = mock.patch.object(build_app, 'GAME', self.game)
        self.game_patch.start()
        self.addCleanup(self.game_patch.stop)
        translator = self.root / 'source-translator/totk_xlate'
        translator.parent.mkdir()
        translator.write_bytes(b'source-built translator')
        translator.chmod(0o755)
        translator.with_suffix('.sha256').write_text(build_app.sha256(translator))
        source_patch = mock.patch.object(build_app, 'SOURCE_TRANSLATOR', translator)
        source_patch.start()
        self.addCleanup(source_patch.stop)

    def test_missing_manifest_does_not_run_any_command(self):
        (self.deps / 'manifest.json').unlink()
        with mock.patch.object(build_app, 'run') as run, self.assertRaisesRegex(build_app.BuildError, 'manifest'):
            build_app.prepare_work(self.root / 'work', Path(sys.executable), self.root / 'logs')
        run.assert_not_called()

    def test_missing_source_has_no_network_fallback(self):
        shutil.rmtree(self.source)
        with mock.patch.object(build_app, 'run') as run, self.assertRaisesRegex(build_app.BuildError, 'missing local'):
            build_app.local_source('example', self.root / 'copy', self.root / 'copy.log')
        run.assert_not_called()

    def test_tampered_source_is_rejected_before_copying(self):
        (self.source / 'source.c').write_bytes(b'tampered')
        with mock.patch.object(build_app, 'run') as run, self.assertRaisesRegex(build_app.BuildError, 'SHA-256'):
            build_app.local_source('example', self.root / 'copy', self.root / 'copy.log')
        run.assert_not_called()

    def test_extra_source_file_is_rejected(self):
        (self.source / 'unexpected.c').write_bytes(b'unlisted code')
        with mock.patch.object(build_app, 'run') as run, self.assertRaisesRegex(build_app.BuildError, 'inventory'):
            build_app.local_source('example', self.root / 'copy', self.root / 'copy.log')
        run.assert_not_called()

    @unittest.skipUnless(shutil.which('rsync'), 'rsync needed for real local-copy check')
    def test_work_source_is_a_private_copy_and_stale_files_are_removed(self):
        dest = self.root / 'copy'
        dest.mkdir()
        (dest / 'stale.c').write_bytes(b'stale')
        build_app.local_source('example', dest, self.root / 'copy.log')
        self.assertFalse((dest / 'stale.c').exists())
        self.assertEqual((dest / 'source.c').read_bytes(), b'verified source')
        (dest / 'source.c').write_bytes(b'work patch')
        self.assertEqual((self.source / 'source.c').read_bytes(), b'verified source')

    def test_wheels_and_requirements_are_verified(self):
        self.assertEqual(build_app.local_python_dependencies(), (self.lock, self.wheel.parent))
        self.wheel.write_bytes(b'tampered wheel')
        with self.assertRaisesRegex(build_app.BuildError, 'SHA-256'):
            build_app.local_python_dependencies()

    def test_missing_wheel_is_rejected(self):
        self.wheel.unlink()
        with self.assertRaisesRegex(build_app.BuildError, 'missing local Python wheel'):
            build_app.local_python_dependencies()

    def test_modified_input_requirements_require_repreparation(self):
        (self.game / 'requirements.txt').write_text('example==2.0\n')
        with self.assertRaisesRegex(build_app.BuildError, 'Python input requirements'):
            build_app.local_python_dependencies()

    def test_pip_is_offline_binary_only_and_hash_locked(self):
        with mock.patch.object(build_app, 'local_source'), mock.patch.object(build_app, 'run') as run:
            build_app.prepare_work(self.root / 'work', Path(sys.executable), self.root / 'logs')
        commands = [call.args[0] for call in run.call_args_list]
        pip_call = next(call for call in run.call_args_list if 'pip' in call.args[0])
        pip = pip_call.args[0]
        self.assertEqual(pip_call.kwargs['env']['PIP_CONFIG_FILE'], os.devnull)
        for option in ('--isolated', '--disable-pip-version-check', '--no-index', '--no-deps',
                       '--only-binary=:all:', '--require-hashes', '--no-cache-dir'):
            self.assertIn(option, pip)
        self.assertEqual(pip[pip.index('--find-links') + 1], self.wheel.parent)
        self.assertEqual(pip[pip.index('-r') + 1], self.lock)
        self.assertFalse(any(str(cmd[0]) == 'git' for cmd in commands))
        self.assertFalse(any('https://' in str(arg) for cmd in commands for arg in cmd))

    def test_ios_sources_are_staged_locally(self):
        with mock.patch.object(build_app, 'local_source') as stage, mock.patch.object(build_app, 'run'):
            build_app.prepare_work(self.root / 'work', Path(sys.executable), self.root / 'logs', ios=True)
        self.assertEqual([call.args[0] for call in stage.call_args_list], ['SPIRV-Cross', 'opus', 'libvpx'])

    def test_ios_compilation_uses_only_staged_sources(self):
        script = Path(build_app.__file__).parent / 'games/totk/ios/tools/build_deps.py'
        sources = (self.root / 'ios-source').resolve()
        for relative in ('opus/CMakeLists.txt', 'libvpx/configure'):
            path = sources / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('local source fixture')
        argv = [str(script), str(self.root / 'ios-deps'), '--sources', str(sources)]
        with mock.patch.object(sys, 'argv', argv), mock.patch.object(subprocess, 'run') as run, \
             mock.patch.object(subprocess, 'check_output', side_effect=['/sdk/iPhoneOS.sdk', '/sdk/iPhoneOS.sdk', '/Xcode/Developer']), \
             mock.patch.object(shutil, 'copy2'), mock.patch.object(shutil, 'copytree'):
            runpy.run_path(str(script), run_name='__main__')
        self.assert_local_only(run, sources, 'iOS')

    def test_visionos_compilation_uses_only_staged_sources(self):
        script = Path(build_app.__file__).parent / 'games/totk/ios/tools/build_deps.py'
        sources = (self.root / 'xros-source').resolve()
        for relative in ('opus/CMakeLists.txt', 'libvpx/configure'):
            path = sources / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('local source fixture')
        argv = [str(script), str(self.root / 'xros-deps'), 'xros', '--sources', str(sources)]
        with mock.patch.object(sys, 'argv', argv), mock.patch.object(subprocess, 'run') as run, \
             mock.patch.object(subprocess, 'check_output', side_effect=['/sdk/XROS.sdk', '/sdk/iPhoneOS.sdk', '/Xcode/Developer']), \
             mock.patch.object(shutil, 'copy2'), mock.patch.object(shutil, 'copytree'):
            runpy.run_path(str(script), run_name='__main__')
        self.assert_local_only(run, sources, 'visionOS')

    def assert_local_only(self, run, sources, system):
        commands = [call.args[0] for call in run.call_args_list]
        self.assertFalse(any(cmd[0] == 'git' for cmd in commands))
        self.assertFalse(any('https://' in str(arg) for cmd in commands for arg in cmd))
        cmake = commands[0]
        self.assertEqual(cmake[cmake.index('-S') + 1], str(sources / 'opus'))
        self.assertIn('-DFETCHCONTENT_FULLY_DISCONNECTED=ON', cmake)
        self.assertIn(f'-DCMAKE_SYSTEM_NAME={system}', cmake)
        configure = next(cmd for cmd in commands if str(cmd[0]).endswith('/configure'))
        self.assertEqual(configure[0], str(sources / 'libvpx/configure'))

    def test_ios_missing_sources_stops_before_running_tools(self):
        script = Path(build_app.__file__).parent / 'games/totk/ios/tools/build_deps.py'
        argv = [str(script), str(self.root / 'ios-deps'), '--sources', str(self.root / 'absent')]
        with mock.patch.object(sys, 'argv', argv), mock.patch.object(subprocess, 'run') as run, \
             mock.patch.object(subprocess, 'check_output') as output, self.assertRaises(SystemExit):
            runpy.run_path(str(script), run_name='__main__')
        run.assert_not_called()
        output.assert_not_called()


if __name__ == '__main__':
    unittest.main()
