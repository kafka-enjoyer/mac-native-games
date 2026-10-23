"""Dependency-injection guards: Homebrew pins, disabled network tools, dedicated iOS signing team."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, REPO / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class HomebrewPinTests(unittest.TestCase):
    def setUp(self):
        self.pins = load('homebrew_pins_under_test', 'tools/homebrew_pins.py')
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(['rm', '-rf', str(self.root)]))
        keg = self.root / 'Cellar/opus/1.0'
        (keg / 'lib').mkdir(parents=True)
        (keg / 'lib/libopus.a').write_bytes(b'archive')
        (self.root / 'opt').mkdir()
        (self.root / 'opt/opus').symlink_to(keg)
        self.groups = {'g': {'opus': ['lib/libopus.a']}}
        self.pin_file = self.root / 'pins.json'
        for name, value in (('BREW', self.root / 'opt'), ('PINS', self.pin_file), ('GROUPS', self.groups)):
            patcher = mock.patch.object(self.pins, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_matching_pins_pass_and_any_change_fails(self):
        with mock.patch('builtins.print'):
            self.pins.update()
        self.assertEqual(self.pins.problems(), [])
        (self.root / 'Cellar/opus/1.0/lib/libopus.a').write_bytes(b'injected')
        self.assertTrue(any('SHA-256 differs' in p for p in self.pins.problems()))

    def test_version_change_fails(self):
        with mock.patch('builtins.print'):
            self.pins.update()
        pins = json.loads(self.pin_file.read_text())
        pins['g']['opus']['version'] = '0.9'
        self.pin_file.write_text(json.dumps(pins))
        self.assertTrue(any('pinned 0.9' in p for p in self.pins.problems()))

    def test_missing_pin_file_fails(self):
        self.assertTrue(self.pins.problems())

    def test_repository_pins_cover_every_group(self):
        pins = json.loads((REPO / 'dependencies/homebrew-pins.json').read_text())
        real = load('homebrew_pins_real', 'tools/homebrew_pins.py')
        for group, formulas in real.GROUPS.items():
            self.assertEqual(set(pins[group]), set(formulas))


class DisabledNetworkToolTests(unittest.TestCase):
    def test_download_dependencies_refuses_to_run(self):
        module = load('download_dependencies_under_test', 'tools/download_dependencies.py')
        with mock.patch('subprocess.run') as run:
            with self.assertRaisesRegex(RuntimeError, 'disabled'):
                module.main()
            with self.assertRaisesRegex(RuntimeError, 'disabled'):
                module.run(['git', 'fetch'])
            run.assert_not_called()

    def test_collect_shader_issues_refuses_network_entry_points(self):
        sys.path.insert(0, str(REPO / 'games/totk/scripts'))
        self.addCleanup(sys.path.remove, str(REPO / 'games/totk/scripts'))
        import collect_shader_issues as module
        with mock.patch('urllib.request.urlopen') as urlopen, mock.patch('subprocess.run') as run:
            for call in (module.main, lambda: module.gh('issue', 'list'), lambda: module.download('https://x', '')):
                with self.assertRaisesRegex(RuntimeError, 'disabled'):
                    call()
            urlopen.assert_not_called()
            run.assert_not_called()


class DedicatedSigningTeamTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(REPO / 'games/totk/ios/tools'))
        self.addCleanup(sys.path.remove, str(REPO / 'games/totk/ios/tools'))
        import install_device
        self.install = install_device

    def env(self, **values):
        clean = {k: v for k, v in os.environ.items() if not k.startswith('MNG_SIGNING_')}
        return mock.patch.dict(os.environ, {**clean, **values}, clear=True)

    def test_no_team_is_never_guessed(self):
        with self.env(), mock.patch.object(self.install, 'teams', return_value=['ONLYTEAM01']):
            with self.assertRaises(SystemExit):
                self.install.signing_team(None)

    def test_team_comes_from_the_dedicated_setting(self):
        with self.env(MNG_SIGNING_TEAM='abcde12345'):
            self.assertEqual(self.install.signing_team(None), 'ABCDE12345')

    def test_forbidden_team_is_refused(self):
        with self.env(MNG_SIGNING_TEAM='ABCDE12345', MNG_SIGNING_FORBIDDEN_TEAMS='XYZ, abcde12345'):
            with self.assertRaises(SystemExit):
                self.install.signing_team(None)

    def test_api_key_needs_all_three_values(self):
        with self.env(MNG_SIGNING_KEY_ID='K'):
            with self.assertRaises(SystemExit):
                self.install.api_key_args()
        with self.env():
            self.assertEqual(self.install.api_key_args(), [])
        with tempfile.NamedTemporaryFile(suffix='.p8') as key, \
                self.env(MNG_SIGNING_KEY_PATH=key.name, MNG_SIGNING_KEY_ID='K', MNG_SIGNING_ISSUER_ID='I'):
            self.assertEqual(self.install.api_key_args()[::2],
                             ['-authenticationKeyPath', '-authenticationKeyID', '-authenticationKeyIssuerID'])


class JustfileTests(unittest.TestCase):
    def test_ios_rebuild_skips_the_shader_contribution_agent(self):
        recipe = (REPO / '.justfile').read_text().split('built-totk-ios:')[1].split('\n\n')[0]
        self.assertIn('--no-shader-reminder', recipe)


if __name__ == '__main__':
    unittest.main()
