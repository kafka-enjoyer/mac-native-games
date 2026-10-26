"""Offline fork guards for games that do not build offline yet (AGENTS.md rule 1).

The ports merged from upstream as-is (games/ssbu, wonder, mvdk, ori, jamboree) fetch code, use a prebuilt translator or
link unpinned Homebrew libraries: their build entry points must stop with NotImplementedError until adapted
(games/<game>/OFFLINE.md). The just recipes print NotYetImplemented for them, Bayonetta 3 and the proofs of concept.
"""
import ast
import re
import shutil
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
UNPORTED = {
    'ssbu': ['scripts/build_ssbu.py'],
    'wonder': ['scripts/build_wonder.py'],
    'mvdk': ['scripts/build_mvdk.py'],
    'ori': ['scripts/build_ori.py'],
    'jamboree': ['scripts/build_jamboree.py', 'third_party/nxnative/build_ipa_from_nsp.py'],
}
PLANNED = ('ssbu', 'wonder', 'mvdk', 'ori', 'jamboree', 'by3', 'awakening', 'echo', 'sky')


def main_raises_not_implemented(path):
    """True when the first statement of main() (after a docstring) raises NotImplementedError."""
    tree = ast.parse(path.read_text())
    mains = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main']
    if len(mains) != 1:
        return False
    body = mains[0].body
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], 'value', None), ast.Constant):
        body = body[1:]
    first = body[0] if body else None
    return (isinstance(first, ast.Raise) and isinstance(first.exc, ast.Call)
            and getattr(first.exc.func, 'id', None) == 'NotImplementedError')


class UnportedGames(unittest.TestCase):
    def test_builders_raise_not_implemented(self):
        for game, scripts in UNPORTED.items():
            for rel in scripts:
                with self.subTest(game=game, script=rel):
                    self.assertTrue(main_raises_not_implemented(REPO / 'games' / game / rel))

    def test_makefiles_stop_at_parse_time(self):
        for game in UNPORTED:
            with self.subTest(game=game):
                first = [line for line in (REPO / 'games' / game / 'Makefile').read_text().splitlines()
                         if line.strip() and not line.startswith('#')][0]
                self.assertTrue(first.startswith('$(error NotImplemented:'), first)

    def test_jamboree_ipa_script_exits_first(self):
        lines = (REPO / 'games/jamboree/runtime/ios/tools/build_ipa.sh').read_text().splitlines()
        code = [line for line in lines[1:] if line.strip() and not line.startswith('#')]
        self.assertRegex(code[0], r'^echo "NotImplemented: .*; exit 1$')

    def test_offline_notes_exist(self):
        for game in UNPORTED:
            with self.subTest(game=game):
                self.assertIn('NotImplementedError', (REPO / 'games' / game / 'OFFLINE.md').read_text())

    def test_justfile_lists_every_planned_game(self):
        text = (REPO / '.justfile').read_text()
        planned = re.search(r'^planned := "([^"]*)"', text, re.M).group(1).split()
        self.assertEqual(sorted(planned), sorted(PLANNED))
        self.assertEqual(re.search(r'^implemented := "([^"]*)"', text, re.M).group(1).split(), ['totk', 'botw', 'odyssey'])

    @unittest.skipUnless(shutil.which('just'), 'just needed')
    def test_planned_games_print_not_yet_implemented(self):
        for game in PLANNED:
            with self.subTest(game=game):
                result = subprocess.run(['just', '--justfile', REPO / '.justfile', 'build', game], cwd=REPO,
                                        capture_output=True, text=True, timeout=60)
                self.assertEqual((result.returncode, result.stdout.strip()), (0, 'NotYetImplemented'))


class SharedTranslator(unittest.TestCase):
    def test_runtime_and_update_never_use_prebuilt(self):
        source = (REPO / 'build_app.py').read_text()
        self.assertNotIn("tree / 'prebuilt/macos-arm64/totk_xlate'", source)
        self.assertIn('clone(tree / STAGED_TRANSLATOR, res / STAGED_TRANSLATOR)', source)
        self.assertIn('return checked_translator(tree / STAGED_TRANSLATOR)', source)

    def test_update_runtime_checks_homebrew_pins(self):
        self.assertIn("f'HOMEBREW_PINS={build_app.REPO / \"tools/homebrew_pins.py\"}'",
                      (REPO / 'update_runtime.py').read_text())

    def test_totk_binaries_wait_for_the_pin_check(self):
        text = (REPO / 'games/totk/Makefile').read_text()
        for target in ('build/totk-native', 'build/totk-native-v112', 'build/totk-native-v121', 'build/totk-native-v143',
                       'build/totk-native-botw160', 'build/totk-native-botw190'):
            with self.subTest(target=target):
                line = re.search(rf'^{re.escape(target)}: .*$', text, re.M).group(0)
                self.assertTrue(line.endswith('| homebrew-pins'), target)


if __name__ == '__main__':
    unittest.main()
