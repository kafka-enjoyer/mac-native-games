"""The translator's NuGet feed is complete, locked, checksummed and offline-only."""
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
DEPS = ROOT / 'dependencies/dotnet'
SCRIPT = ROOT / 'games/totk/tools/totk_xlate/publish_native.sh'


class DotnetDependencies(unittest.TestCase):
    def test_local_bundle_checksums(self):
        entries = (DEPS / 'SHA256SUMS').read_text().splitlines()
        self.assertTrue(entries)
        for entry in entries:
            expected, relative = entry.split('  ', 1)
            path = DEPS / relative
            self.assertTrue(path.resolve().is_relative_to(DEPS.resolve()))
            with path.open('rb') as f:
                self.assertEqual(hashlib.file_digest(f, 'sha256').hexdigest(), expected, relative)

    def test_lock_files_cover_all_transitive_packages_in_local_feed(self):
        locks = sorted((DEPS / 'locks').rglob('packages.lock.json'))
        self.assertEqual(len(locks), 4)
        required = set()
        for lock in locks:
            for packages in json.loads(lock.read_text())['dependencies'].values():
                for name, data in packages.items():
                    if data['type'] in ('Direct', 'Transitive'):
                        required.add(f'{name.lower()}.{data["resolved"].lower()}.nupkg')
        self.assertTrue(required)
        self.assertTrue(required.issubset({p.name for p in (DEPS / 'packages').glob('*.nupkg')}))

    def test_sdk_and_sources_are_pinned(self):
        sdk = json.loads((DEPS / 'global.json').read_text())['sdk']
        self.assertEqual(sdk['rollForward'], 'disable')
        self.assertFalse(sdk['allowPrerelease'])
        self.assertIn(f'dotnet {sdk["version"]}', (DEPS / 'toolchain.txt').read_text().splitlines())
        sources = ET.parse(DEPS / 'NuGet.Config').getroot().find('packageSources')
        self.assertIsNotNone(sources.find('clear'))
        self.assertEqual([s.attrib['value'] for s in sources.findall('add')], ['packages'])
        recipe = SCRIPT.read_text()
        for option in ('--locked-mode', '--no-restore', '--configfile', 'deny network*', 'SHA256SUMS'):
            self.assertIn(option, recipe)
        self.assertNotIn('https://', recipe)

    @unittest.skipUnless(platform.system() == 'Darwin', 'macOS shell recipe')
    def test_shell_recipe_syntax(self):
        subprocess.run(['/bin/zsh', '-n', str(SCRIPT)], check=True, capture_output=True)

    def fixture_recipe(self, root):
        script = root / 'games/totk/tools/totk_xlate/publish_native.sh'
        script.parent.mkdir(parents=True)
        shutil.copy2(SCRIPT, script)
        return script

    @unittest.skipUnless(platform.system() == 'Darwin', 'macOS shell recipe')
    def test_missing_bundle_stops_before_toolchain_or_build(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            script = self.fixture_recipe(root)
            result = subprocess.run(['/bin/zsh', str(script), str(root / 'out')], capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('no download fallback', result.stderr)
            self.assertFalse((root / 'out').exists())

    @unittest.skipUnless(platform.system() == 'Darwin', 'macOS shell recipe')
    def test_tampered_package_stops_before_toolchain_or_build(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            script = self.fixture_recipe(root)
            deps = root / 'dependencies/dotnet'
            deps.mkdir(parents=True)
            (deps / 'package.nupkg').write_bytes(b'tampered')
            expected = hashlib.sha256(b'original').hexdigest()
            (deps / 'SHA256SUMS').write_text(f'{expected}  package.nupkg\n')
            result = subprocess.run(['/bin/zsh', str(script), str(root / 'out')], capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('FAILED', result.stdout + result.stderr)
            self.assertFalse((root / 'out').exists())


if __name__ == '__main__':
    unittest.main()
