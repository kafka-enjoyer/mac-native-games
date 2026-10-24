#!/usr/bin/env python3
"""Build Super Mario Odyssey.app from your own Super Mario Odyssey dump (update 1.3.0 or 1.4.1).

Run it through the repository's builder, which checks the offline dependencies, the Homebrew pins and the source-built
shader translator first, then calls this script with the work folder's Python:

    python3.14 build_app.py BASE.nsp --update UPDATE.nsp -k prod.keys --firmware FIRMWARE_DIR [-o OUT.app] [--work DIR]

Direct use (what build_app.py passes):
    <venv>/bin/python scripts/build_odyssey.py --game BASE.xci|BASE.nsp [--update UPDATE.nsp] --keys prod.keys
        --work DIR --out OUT.app --translator <checked totk_xlate> --spirv-cross-src <checked SPIRV-Cross copy>

Nothing is downloaded: SPIRV-Cross and the translator are the hash-checked local copies build_app.py prepares.
With --update, the base and the update are first combined into one NSP in the work folder (scripts/combine_input.py),
the input the steps below read; a combined XCI/NSP without --update still works.

Steps (each is skipped when its verified output already exists, so a failed run can simply be started again):
 1. check the input (title, version, integrity; prints no keys or game data); the update's display version (1.3.0 or
    1.4.1) selects assets/expected-*.json and the version folder <work>/v<version>
 2. extract the program modules (main, sdk, subsdk0) and merge the base + update RomFS
 3. extract the system fonts from the game card's system-update partition (NSP: pass --firmware)
 4. rewrite the ARM64 modules ahead of time (third_party/d2r/patch_nso.py, native ruleset)
 5. loader tables: verifies ExeFS, rewrite and RomFS against the version's assets/expected-*.json
 6. shader tools (the local SPIRV-Cross and the source-built translator) and the runtime
 7. the whole-game shader seed (the longest step; --skip-seed leaves it out)
 8. extract the game's icon, package the app and put it at --out; saves, shader cache and log go to
    ~/Library/Application Support/MacNativeGames/Odyssey

Everything written stays in the work folder, which Git ignores; it holds game data, so never share or commit it.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

GAME_DIR = Path(__file__).resolve().parents[1]
GAMES = GAME_DIR.parent
MODULES = ("main", "sdk", "subsdk0")
# Supported update display versions: their expected hashes (1.3.0 keeps upstream's file name, to ease merges).
VERSIONS = {"1.3.0": GAME_DIR / "assets/expected-local-update.json", "1.4.1": GAME_DIR / "assets/expected-v1.4.1.json"}


def step(n, title):
    print(f"\n== {n}. {title}", flush=True)
    return time.monotonic()


def done(t0, note=""):
    print(f"   done in {time.monotonic() - t0:.0f} s{(' — ' + note) if note else ''}", flush=True)


def run(cmd, env=None, cwd=GAME_DIR):
    print("   $ " + " ".join(str(c) for c in cmd), flush=True)
    subprocess.run([str(c) for c in cmd], check=True, cwd=cwd, env={**os.environ, **(env or {})})


def link(path: Path, target: str):
    if path.is_symlink() or path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(target, path)


def install_app(app: Path, out: Path):
    """Put the packaged app at out: an APFS clone (no extra space on the same volume), replacing an older app only once
    the new one is complete."""
    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_name(out.name + ".partial")
    old = out.with_name(out.name + ".old")
    for leftover in (partial, old):
        if leftover.exists():
            shutil.rmtree(leftover)
    if subprocess.run(["cp", "-cR", str(app), str(partial)]).returncode != 0:   # another volume: a plain copy
        shutil.rmtree(partial, ignore_errors=True)
        shutil.copytree(app, partial, symlinks=True)
    if out.exists():
        out.rename(old)
    partial.rename(out)
    if old.exists():
        shutil.rmtree(old)
    print(f"   app: {out}")


def preflight(args, py):
    problems = []
    if sys.platform != "darwin" or os.uname().machine != "arm64":
        problems.append("an Apple silicon Mac is required")
    for name in ("capstone", "cryptography", "lz4"):   # from the repository's hash-locked wheels (build_app.py's venv)
        if subprocess.run([py, "-c", f"import {name}"], capture_output=True).returncode:
            problems.append(f"Python module {name} is missing: run this through build_app.py, which uses the local wheels")
    for lib in ("/opt/homebrew/opt/opus/lib/libopus.a", "/opt/homebrew/opt/libvpx/lib/libvpx.a"):
        if not Path(lib).exists():   # the versions are checked against dependencies/homebrew-pins.json by build_app.py
            problems.append(f"{lib} is missing (see dependencies/homebrew-pins.json)")
    if not Path(args.developer_dir, "usr/bin/xcodebuild").exists():
        problems.append(f"Xcode not found at {args.developer_dir} (--developer-dir)")
    for path in (args.game, args.keys, *([args.update] if args.update else [])):
        if not path.is_file():
            problems.append(f"{path} not found")
    if not (args.translator.is_file() and args.translator.with_suffix(".sha256").is_file()):
        problems.append(f"the source-built shader translator is missing: {args.translator} (just build-translator)")
    if not (args.spirv_cross_src / "spirv_msl.cpp").is_file():
        problems.append(f"the local SPIRV-Cross copy is missing: {args.spirv_cross_src} (build_app.py prepares it)")
    if " " in str(args.work):
        problems.append(f"make cannot build into a folder whose path has a space: {args.work}; pick another --work")
    if (args.update or args.game.suffix.lower() == ".nsp") and not args.firmware:
        problems.append("an NSP carries no system fonts: pass --firmware <unpacked firmware NCA directory>")
    # About 12 GB in all plus the combined input (6 GB, removed after a successful build); the merged RomFS (5.6 GB)
    # is most of it, so a resumed build needs less.
    done_before = any(args.work.glob("v*/extracted/local/romfs/index.json"))
    need = (5 if done_before else 12) + (6 if args.update else 0)
    free = shutil.disk_usage(args.work.parent if not args.work.exists() else args.work).free / 2**30
    if free < need:
        problems.append(f"only {free:.0f} GB free; about {need} GB more are needed")
    if problems:
        raise SystemExit("cannot build:\n - " + "\n - ".join(problems))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--game", type=Path, required=True,
                   help="your Odyssey base game (XCI or NSP), or one XCI/NSP holding the base game and the update")
    p.add_argument("--update", type=Path, help="the separate update NSP (1.3.0 or 1.4.1)")
    p.add_argument("--keys", type=Path, required=True, help="prod.keys dumped from your own Switch")
    p.add_argument("--work", type=Path, default=GAME_DIR / "Odyssey_build", help="build folder (default Odyssey_build)")
    p.add_argument("--out", type=Path, help="the app to write (default: <work>/Super Mario Odyssey.app)")
    p.add_argument("--firmware", type=Path, help="unpacked firmware NCA directory, for the system fonts of an NSP build")
    p.add_argument("--translator", type=Path, required=True, help="the checked source-built totk_xlate (build_app.py)")
    p.add_argument("--spirv-cross-src", type=Path, required=True, help="the checked local SPIRV-Cross copy (build_app.py)")
    p.add_argument("--developer-dir", default="/Applications/Xcode.app/Contents/Developer")
    p.add_argument("--skip-seed", action="store_true", help="leave out the whole-game shader seed (more first-play stutter)")
    p.add_argument("--jobs", type=int, default=os.cpu_count() or 8)
    args = p.parse_args()
    args.game, args.keys, args.work = args.game.resolve(), args.keys.resolve(), args.work.resolve()
    args.update = args.update.resolve() if args.update else None
    args.translator, args.spirv_cross_src = args.translator.resolve(), args.spirv_cross_src.resolve()
    out = (args.out or args.work / "Super Mario Odyssey.app").resolve()
    py = sys.executable
    preflight(args, py)
    args.work.mkdir(parents=True, exist_ok=True)
    keyargs = ["--keys", args.keys]
    started = time.monotonic()

    t = step(1, "Check the input")
    combined = None
    if args.update:   # base + update -> the one container the steps read (scripts/combine_input.py)
        combined = args.work / "input/combined.nsp"
        run([py, "scripts/combine_input.py", args.game, args.update, "--output", combined])
        args.game = combined
    run([py, "scripts/inspect_input.py", args.game, *keyargs])
    report = args.work / "analysis/versions.json"
    run([py, "scripts/inspect_version.py", args.game, *keyargs, "--output", report])
    version = next(v["display_version"] for v in json.loads(report.read_text())["versions"] if v["display_version"] != "1.0.0")
    if version not in VERSIONS:
        raise SystemExit(f"update {version} is not supported (supported: {', '.join(VERSIONS)})")
    expected = VERSIONS[version]
    work = args.work / f"v{version.replace('.', '')}"   # one folder per version: extracted/local etc. as upstream's
    ext = work / "extracted"
    work.mkdir(exist_ok=True)
    print(f"   Super Mario Odyssey {version}; version folder {work}")
    done(t)

    t = step(2, "Program modules and the merged RomFS")
    if (ext / "extraction-manifest.json").is_file():
        print("   modules already extracted")
    else:
        run([py, "scripts/extract_code.py", args.game, *keyargs, "--output", ext])
    link(ext / "local/exefs", "..")
    if (ext / "local/romfs/index.json").is_file():
        print("   RomFS already merged")
    else:
        run([py, "scripts/merge_romfs.py", args.game, *keyargs, "--output", ext / "local/romfs"])
    done(t)

    t = step(3, "System fonts")
    fonts = ext / "firmware/shared-fonts"
    if len(list(fonts.glob("*.bfttf"))) >= 6:
        print("   fonts already extracted")
    else:
        source = ["--firmware", args.firmware] if args.firmware else ["--xci", args.game]
        try:
            run([py, GAME_DIR / "third_party/totk-scripts/extract_shared_fonts.py", *keyargs, *source, "--output", fonts,
                 "--inventory", work / "analysis/firmware-inventory.json"])
        except subprocess.CalledProcessError:
            if args.firmware:
                raise
            # Not every card's system-update partition carries the font data (seen 23 October on a 1.3.0 card).
            raise SystemExit("this game card's system-update partition has no shared-font data: dump your Switch's "
                             "firmware (its NCA files) and pass the folder with --firmware, then run this again")
    done(t)

    t = step(4, "Rewrite the ARM64 modules")
    rewritten = work / "rewritten"
    rewritten.mkdir(exist_ok=True)
    link(rewritten / "local", "../rewritten")
    for name in MODULES:
        if (rewritten / f"{name}.patched.bin").is_file():
            print(f"   {name} already rewritten")
            continue
        run([py, GAME_DIR / "third_party/d2r/patch_nso.py", ext / name, rewritten, name],
            env={"DM_RULESET": "native", "DM_PRIVATE_GATES": "0"})
    done(t)

    t = step(5, f"Loader tables (verifies every input against the pinned {version} hashes)")
    run([py, "scripts/prepare_runtime.py", "--work", work, "--expected", expected])
    done(t)

    t = step(6, "Shader tools and the runtime")
    # Offline: the hash-checked SPIRV-Cross copy and the source-built translator from build_app.py; nothing is fetched.
    # make cannot handle spaces in target paths (checked in preflight), so the paths are passed absolute.
    run(["make", f"-j{args.jobs}", "runtime", f"WORK={work}", f"PY={py}", f"GAME_VERSION={version}",
         f"SPIRV_CROSS_SRC={args.spirv_cross_src}", f"TRANSLATOR={args.translator}"],
        env={"DEVELOPER_DIR": args.developer_dir})
    done(t)

    seed = work / "build/shader-seed"
    t = step(7, "Whole-game shader seed")
    if args.skip_seed:
        print("   skipped (--skip-seed)")
    elif (seed / "seed-manifest.json").is_file():
        print("   seed already prepared")
    else:
        env = {"ODYSSEY_WORK": str(work), "ODYSSEY_VERSION": version}
        try:
            run([py, "scripts/prepare_odyssey_shader_seed.py", "--output", seed], env=env)
        except subprocess.CalledProcessError:
            # The shared tool can fail in its last step after translating everything (seen 22 October); publish the
            # translated partial seed and finish it, as prepare_odyssey_shader_seed.py --salvage does.
            print("   the seed's last step failed; salvaging the translated shaders")
            run([py, "scripts/prepare_odyssey_shader_seed.py", "--output", seed, "--salvage"], env=env)
        run([py, "scripts/prepare_odyssey_shader_seed.py", "--output", seed, "--rules"], env=env)
    done(t)

    t = step(8, "Package the app")
    icon = work / "app-assets/OdysseyIcon.jpg"
    if not icon.is_file():   # the game's own icon, from its Control data
        run([py, "scripts/extract_app_icon.py", args.game, *keyargs, "--output", icon])
    run([py, "scripts/package_native_app.py"], env={"ODYSSEY_WORK": str(work)})
    install_app(work / "Odyssey.app", out)
    done(t)
    if combined:   # 6 GB; made again from the two packages when a later build needs it
        combined.unlink(missing_ok=True)
        combined.with_suffix(".json").unlink(missing_ok=True)
    print(f"\nBuilt {out} (Super Mario Odyssey {version}) in {(time.monotonic() - started) / 60:.0f} min. It contains "
          "game data from your own dump: do not share it.")


if __name__ == "__main__":
    main()
