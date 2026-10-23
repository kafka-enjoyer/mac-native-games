#!/usr/bin/env python3
"""Pin the preinstalled Homebrew files the build links or runs against (dependency-injection guard).

The app build never installs or upgrades Homebrew packages, but it does link whatever is in /opt/homebrew:
  mac-runtime  opus + libvpx static libraries and headers, linked into the Mac game binary (games/totk/Makefile)
  translator   OpenSSL + Brotli dylibs the source-built shader translator loads at run time (publish_native.sh)
Their exact versions and SHA-256 hashes are recorded in dependencies/homebrew-pins.json (tracked in Git). A build stops
when any pinned file differs, e.g. after `brew upgrade`. Review the upgrade, then re-pin explicitly:

  python3 tools/homebrew_pins.py verify [group ...]   # default: all groups
  python3 tools/homebrew_pins.py update               # rewrite the pins from the installed files (review the git diff)
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PINS = ROOT / 'dependencies/homebrew-pins.json'
BREW = Path('/opt/homebrew/opt')
# group -> formula -> file globs inside the formula's keg (what the build actually consumes)
GROUPS = {
    'mac-runtime': {'opus': ['lib/libopus.a', 'include/opus/*.h'],
                    'libvpx': ['lib/libvpx.a', 'include/vpx/*.h']},
    'translator': {'openssl@4': ['lib/libssl.4.dylib', 'lib/libcrypto.4.dylib', 'lib/ossl-modules/*.dylib'],
                   'brotli': ['lib/libbrotlienc.1.dylib', 'lib/libbrotlidec.1.dylib', 'lib/libbrotlicommon.1.dylib']},
}


def sha256(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def installed(formula, globs):
    """(version, {relative path: sha256}) of an installed formula; the version is the Cellar folder name."""
    keg = BREW / formula
    if not keg.is_dir():
        raise FileNotFoundError(f'Homebrew formula {formula} is not installed ({keg})')
    version = keg.resolve().name
    files = {}
    for pattern in globs:
        matches = sorted(keg.glob(pattern))
        if not matches:
            raise FileNotFoundError(f'{formula}: nothing matches {pattern}')
        for path in matches:
            files[path.relative_to(keg).as_posix()] = sha256(path.resolve())
    return version, files


def problems(groups=None):
    """A list of human-readable mismatches between the installed files and the pins; [] when they all match."""
    try:
        pins = json.loads(PINS.read_text())
    except (OSError, ValueError) as e:
        return [f'Homebrew pin file unavailable or invalid ({PINS}): {e}']
    found = []
    for group in groups or GROUPS:
        if group not in GROUPS:
            return [f'unknown pin group {group!r} (known: {", ".join(GROUPS)})']
        for formula, globs in GROUPS[group].items():
            want = pins.get(group, {}).get(formula)
            if not want:
                found.append(f'{formula}: not pinned in {PINS.name}')
                continue
            try:
                version, files = installed(formula, globs)
            except FileNotFoundError as e:
                found.append(str(e))
                continue
            if version != want['version']:
                found.append(f'{formula}: installed {version}, pinned {want["version"]}')
            for rel in sorted(set(files) | set(want['files'])):
                if files.get(rel) != want['files'].get(rel):
                    found.append(f'{formula}/{rel}: ' + ('not pinned' if rel not in want['files'] else
                                                         'missing' if rel not in files else 'SHA-256 differs from the pin'))
    return found


def update():
    pins = {group: {formula: dict(zip(('version', 'files'), installed(formula, globs)))
                    for formula, globs in formulas.items()} for group, formulas in GROUPS.items()}
    PINS.write_text(json.dumps(pins, indent=2, sort_keys=True) + '\n')
    for group, formulas in pins.items():
        for formula, pin in formulas.items():
            print(f'{group}: {formula} {pin["version"]} ({len(pin["files"])} files)')
    print(f'wrote {PINS}; review it with git diff before committing')


def main(argv):
    if argv[:1] == ['update'] and len(argv) == 1:
        return update()
    if argv[:1] != ['verify']:
        sys.exit(__doc__)
    found = problems(argv[1:])
    if found:
        sys.exit('Homebrew files differ from dependencies/homebrew-pins.json:\n  ' + '\n  '.join(found) +
                 '\nReinstall the pinned versions, or review the upgrade and run python3 tools/homebrew_pins.py update.')
    print('Homebrew pins OK: ' + ', '.join(argv[1:] or GROUPS))


if __name__ == '__main__':
    main(sys.argv[1:])
