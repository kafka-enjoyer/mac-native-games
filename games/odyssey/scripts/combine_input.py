#!/usr/bin/env python3
"""Combine a base game (XCI or NSP) and a separate update NSP into one NSP, the input the Odyssey scripts read.

The scripts (inspect_input, extract_code, merge_romfs, inspect_version, extract_app_icon) look for the base and the
update NCAs in one container. This writes a new PFS0 holding every file of both packages (an XCI contributes its secure
partition), byte for byte; nothing is decrypted or changed, and every later step verifies what it reads (NCA headers,
FS header hashes, IVFC levels). A file present in both packages must be identical in size, or the combination stops.

The output holds game data from the user's own dump: write it only to an ignored work folder and never share it.
usage: combine_input.py <base.xci|base.nsp> <update.nsp> --output <work>/input/combined.nsp
"""
import argparse
import json
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'third_party/by3-scripts'))
from extract_exefs import container_entries, require   # noqa: E402  (own copy, games/odyssey/third_party)

CHUNK = 16 * 1024 * 1024


def entries_of(path):
    with path.open('rb') as f:
        kind, entries = container_entries(f, path.stat().st_size)
    return kind, [(name, offset, size, path) for name, offset, size in entries]


def pfs0_header(files):
    """PFS0 header for (name, size) pairs; data offsets are relative to the end of the header."""
    names = bytearray()
    table = bytearray()
    offset = 0
    for name, size in files:
        table += struct.pack('<QQII', offset, size, len(names), 0)
        names += name.encode('utf-8') + b'\0'
        offset += size
    header_size = 16 + len(table) + len(names)
    names += b'\0' * ((-header_size) % 0x20)   # pad the string table so the data starts 32-byte aligned
    return struct.pack('<4sIII', b'PFS0', len(files), len(names), 0) + table + names


def source_record(paths):
    return [dict(path=str(p.resolve()), size=p.stat().st_size, mtime_ns=p.stat().st_mtime_ns) for p in paths]


def combine(base, update, output):
    """Write output (if it is not already the combination of these exact files) and return it."""
    manifest = output.with_suffix('.json')
    sources = source_record((base, update))
    try:
        if output.is_file() and json.loads(manifest.read_text())['sources'] == sources:
            print(f'   combined input already prepared: {output}')
            return output
    except (OSError, ValueError, KeyError):
        pass
    base_kind, base_entries = entries_of(base)
    update_kind, update_entries = entries_of(update)
    require(update_kind == 'nsp', 'The update must be an NSP')
    files, seen = [], {}
    for name, offset, size, path in base_entries + update_entries:
        if name in seen:
            require(seen[name] == size, f'{name} is in both packages with different contents')
            continue
        seen[name] = size
        files.append((name, offset, size, path))
    require(files, 'The packages hold no files')
    header = pfs0_header([(name, size) for name, _, size, _ in files])
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.name + '.partial')
    manifest.unlink(missing_ok=True)
    with partial.open('wb') as out:
        out.write(header)
        for name, offset, size, path in files:
            with path.open('rb') as src:
                src.seek(offset)
                left = size
                while left:
                    data = src.read(min(CHUNK, left))
                    require(data, f'{path.name} is truncated ({name})')
                    out.write(data)
                    left -= len(data)
    os.replace(partial, output)
    manifest.write_text(json.dumps(dict(base_kind=base_kind, files=len(files), sources=sources), indent=2) + '\n')
    print(f'   combined {base_kind.upper()} base + update NSP ({len(files)} files) -> {output}')
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('base', type=Path, help='the base game: XCI or NSP')
    parser.add_argument('update', type=Path, help='the update NSP')
    parser.add_argument('--output', type=Path, required=True, help='the combined NSP to write')
    args = parser.parse_args()
    try:
        combine(args.base.resolve(), args.update.resolve(), args.output.resolve())
    except (OSError, ValueError) as error:
        raise SystemExit(f'cannot combine the packages: {error}')


if __name__ == '__main__':
    main()
