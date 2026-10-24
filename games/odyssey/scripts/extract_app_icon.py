#!/usr/bin/env python3
"""Extract the verified Control icon of the local Odyssey update (1.3.0 or 1.4.1) for the app.

The icon is game-derived. Write it only to an ignored work folder (a *_build folder of games/odyssey, the repository's
build-artifacts/, or a folder outside the repository); never commit it.
"""
import argparse
import tempfile
from pathlib import Path

from inspect_version import (
    Ctr, common_tickets, container_entries, index_romfs, load_keys,
    nca_ctr_key, nca_inventory, require, romfs_section, verify_ivfc,
)

HERE = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('game', type=Path)
    parser.add_argument('--keys', required=True, type=Path)
    parser.add_argument('--output', type=Path,
                        default=HERE / 'Odyssey_build/app-assets/OdysseyIcon.jpg')
    args = parser.parse_args()
    out = args.output.resolve()   # a *_build folder in games/odyssey or build-artifacts/: ignored by .gitignore
    repo = HERE.resolve().parents[1]
    require(not out.is_relative_to(repo) or out.is_relative_to(repo / 'build-artifacts')
            or any(parent.parent == HERE.resolve() and parent.name.endswith('_build') for parent in out.parents),
            'Icon output must stay in an ignored folder (a *_build folder of games/odyssey, or build-artifacts/)')
    out.parent.mkdir(parents=True, exist_ok=True)
    keys = load_keys(args.keys)
    with args.game.open('rb') as source:
        _, entries = container_entries(source, args.game.stat().st_size)
        tickets = common_tickets(source, entries)
        controls = [(record, hdr) for record, hdr in nca_inventory(source, entries, keys)
                    if record['content_type'] == 2 and record['title_id'] == '0100000000010000']
        require(len(controls) == 2, 'Expected base and update Control NCAs')
        for record, hdr in controls:
            start, end, fs = romfs_section(hdr)
            require(fs[4] == 3, 'Expected direct AES-CTR Control RomFS')
            ctr = Ctr(source, record['nca_offset'], record['size'], nca_ctr_key(hdr, keys, tickets))
            require(end <= ctr.size, 'Control RomFS exceeds stored NCA')
            upper = fs[0x140:0x148][::-1]
            with tempfile.TemporaryDirectory(dir=out.parent) as temp:
                image = Path(temp) / 'control-romfs.bin'
                verify_ivfc(fs, end - start,
                            lambda offset, length: ctr.read(start + offset, length, upper), image)
                files = index_romfs(image)
                nacp = next(item for item in files if item['path'] == 'control.nacp')
                with image.open('rb') as data:
                    data.seek(nacp['offset'] + 0x3060)
                    version = data.read(16).split(b'\0', 1)[0].decode('ascii')
                if version == '1.0.0':   # the base game's Control data; the icon comes from the update's
                    continue
                icons = [item for item in files if item['path'].startswith('icon_')]
                require(icons, 'Update Control RomFS contains no title icon')
                icon = next((item for item in icons if item['path'] == 'icon_AmericanEnglish.dat'), icons[0])
                with image.open('rb') as data:
                    data.seek(icon['offset'])
                    contents = data.read(icon['size'])
                require(contents.startswith(b'\xff\xd8\xff') and contents.endswith(b'\xff\xd9'),
                        'Control icon is not a complete JPEG')
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_bytes(contents)
                print(f'Verified local {version} title icon -> {args.output}')
                return
    raise SystemExit('Update Control icon not found')


if __name__ == '__main__':
    main()
