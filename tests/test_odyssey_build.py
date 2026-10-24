"""Super Mario Odyssey builds through build_app.py: separate base + update, 1.3.0 / 1.4.1, offline, org.mng identifiers."""
import argparse
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ODYSSEY = ROOT / 'games/odyssey'
sys.path.insert(0, str(ROOT))
import build_app  # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CombineInput(unittest.TestCase):
    def setUp(self):
        try:
            self.combine = load('odyssey_combine_input', ODYSSEY / 'scripts/combine_input.py')
        except ImportError as error:   # extract_exefs needs cryptography (the build's venv has it)
            self.skipTest(f'needs the build dependencies: {error}')
        self.folder = tempfile.TemporaryDirectory()
        self.tmp = Path(self.folder.name)

    def tearDown(self):
        self.folder.cleanup()

    def package(self, name, files):
        path = self.tmp / name
        path.write_bytes(self.combine.pfs0_header([(n, len(d)) for n, d in files]) + b''.join(d for _, d in files))
        return path

    def read(self, path):
        with path.open('rb') as f:
            kind, entries = self.combine.container_entries(f, path.stat().st_size)
            return kind, {name: (f.seek(offset), f.read(size))[1] for name, offset, size in entries}

    def test_base_and_update_become_one_package_byte_for_byte(self):
        base = self.package('base.nsp', [('a.nca', b'A' * 100), ('x.cert', b'C' * 7)])
        update = self.package('update.nsp', [('b.nca', b'B' * 50), ('x.cert', b'C' * 7), ('u.tik', b'T' * 9)])
        out = self.combine.combine(base, update, self.tmp / 'work/input/combined.nsp')
        self.assertEqual(self.read(out), ('nsp', {'a.nca': b'A' * 100, 'x.cert': b'C' * 7, 'b.nca': b'B' * 50, 'u.tik': b'T' * 9}))
        stamp = out.stat().st_mtime_ns
        self.combine.combine(base, update, out)   # the same two files: reused, not written again
        self.assertEqual(out.stat().st_mtime_ns, stamp)

    def test_a_file_differing_between_the_packages_stops(self):
        base = self.package('base.nsp', [('x.cert', b'C' * 7)])
        update = self.package('update.nsp', [('x.cert', b'C' * 8)])
        with self.assertRaisesRegex(ValueError, 'different contents'):
            self.combine.combine(base, update, self.tmp / 'combined.nsp')
        self.assertFalse((self.tmp / 'combined.nsp').exists())


class Versions(unittest.TestCase):
    def test_1_4_1_is_pinned_and_shares_1_3_0_code_and_data(self):
        v130 = json.loads((ODYSSEY / 'assets/expected-local-update.json').read_text())
        v141 = json.loads((ODYSSEY / 'assets/expected-v1.4.1.json').read_text())
        for key in ('title_id', 'main_build_id', 'exefs_sha256', 'rewritten_sha256', 'romfs'):
            self.assertEqual(v141[key], v130[key], key)
        self.assertRegex(v141['romfs']['sha256'], r'^[0-9a-f]{64}$')

    def test_builder_knows_both_versions(self):
        source = (ODYSSEY / 'scripts/build_odyssey.py').read_text()
        self.assertIn('"1.3.0": GAME_DIR / "assets/expected-local-update.json"', source)
        self.assertIn('"1.4.1": GAME_DIR / "assets/expected-v1.4.1.json"', source)
        self.assertIn("UPDATES = ('1.3.0', '1.4.1')", (ODYSSEY / 'scripts/inspect_version.py').read_text())


class Offline(unittest.TestCase):
    FETCH = re.compile(r'git\s+(clone|fetch|checkout)|https?://|curl|wget|urlopen|pip\s+install|brew\s+install')

    def test_builder_and_makefile_fetch_nothing(self):
        for path in (ODYSSEY / 'scripts/build_odyssey.py', ODYSSEY / 'scripts/combine_input.py', ODYSSEY / 'Makefile'):
            code = '\n'.join(line for line in path.read_text().splitlines() if not line.lstrip().startswith('#'))
            self.assertIsNone(self.FETCH.search(code), f'{path.name}: {self.FETCH.search(code)}')

    def test_makefile_uses_the_source_built_translator_never_prebuilt(self):
        make = (ODYSSEY / 'Makefile').read_text()
        rules = [line for line in make.splitlines() if not line.lstrip().startswith('#')]
        self.assertFalse([line for line in rules if 'prebuilt/' in line])
        self.assertIn('TRANSLATOR ?= ../../build-artifacts/translator-offline/native/totk_xlate', make)

    def test_build_app_passes_the_checked_local_copies(self):
        source = (ROOT / 'build_app.py').read_text()
        self.assertIn("'--translator', tree / STAGED_TRANSLATOR", source)
        self.assertIn("'--spirv-cross-src', work / 'src/SPIRV-Cross'", source)


class Dispatch(unittest.TestCase):
    def args(self, **kw):
        base = dict(platform='macos', mod=None, install_mod_romfs=False, work=Path('/tmp/w'), out=None)
        return argparse.Namespace(**{**base, **kw})

    def call(self, args, **kw):
        values = dict(tree=Path('/tmp/w/totk'), game=Path('/tmp/base.nsp'), update=None, keys=Path('/tmp/k'),
                      kind='nsp', firmware=None, shared_fonts=None, work=Path('/tmp/w'), out=Path('/tmp/o.app'),
                      py=Path('/usr/bin/python3'), env={}, logs=Path('/tmp/w/logs'), t0=0, fresh_work=False)
        values.update(kw)
        return build_app.build_odyssey(args, **values)

    def test_odyssey_is_a_known_game(self):
        self.assertEqual(build_app.TITLES['0100000000010000'], 'odyssey')
        self.assertEqual(build_app.APPS['odyssey'], ('Super Mario Odyssey', 'org.mng.odyssey', 'Odyssey'))
        self.assertEqual(build_app.title_kind('0100000000010800'), ('0100000000010000', 'update'))

    def test_mac_only_no_mods_no_shared_fonts(self):
        for platform in ('ios', 'visionos'):
            with self.assertRaisesRegex(build_app.BuildError, 'macos'):
                self.call(self.args(platform=platform))
        with self.assertRaisesRegex(build_app.BuildError, '--mod'):
            self.call(self.args(mod=Path('/tmp/mod')))
        with self.assertRaisesRegex(build_app.BuildError, '--firmware'):
            self.call(self.args(), shared_fonts=Path('/tmp/fonts'))


class App(unittest.TestCase):
    def test_app_identity_and_data_folder(self):
        package = (ODYSSEY / 'scripts/package_native_app.py').read_text()
        self.assertIn('"CFBundleIdentifier": "org.mng.odyssey"', package)
        self.assertIn('"CFBundleName": "Super Mario Odyssey"', package)
        self.assertNotIn('session-minutes', package)   # no session limit written at packaging
        launcher = (ODYSSEY / 'scripts/odyssey_app_launcher.c').read_text()
        self.assertIn('"Library/Application Support"', launcher)
        self.assertIn('"MacNativeGames"', launcher)
        self.assertNotIn('"Odyssey Data"', launcher)
        self.assertIn('double minutes = 0;', launcher)


class Identifiers(unittest.TestCase):
    def test_no_org_macnativegames_identifier(self):
        found = subprocess.run(['git', 'grep', '-n', r'org\.macnativegames', '--', '.', ':!AGENTS.md',
                                ':!games/awakening', ':!dependencies', ':!tests/test_odyssey_build.py'],
                               cwd=ROOT, capture_output=True, text=True).stdout
        self.assertEqual(found, '', 'use org.mng (AGENTS.md rule 10)')


if __name__ == '__main__':
    unittest.main()
