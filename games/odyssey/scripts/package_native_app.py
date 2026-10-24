#!/usr/bin/env python3
"""Build <work>/Odyssey.app: a self-contained, locally signed Mac app around the native runtime.

The bundle carries the runtime, shader tools, rewritten modules, merged RomFS and shared fonts (large files are APFS
clones, so they take no extra space). Saves, the shader cache and the log go to
~/Library/Application Support/MacNativeGames/Odyssey (scripts/odyssey_app_launcher.c); packaging writes nothing there.
scripts/build_odyssey.py then puts the app at its --out path as "Super Mario Odyssey.app". The app contains game data
from the user's own dump and must not be shared.
"""
from pathlib import Path
import os
import plistlib
import shutil
import subprocess

GAME = Path(__file__).resolve().parents[1]
BUILD = Path(os.environ.get("ODYSSEY_WORK", GAME / "Odyssey_build")).resolve()   # ODYSSEY_WORK: another build folder (scripts/build_odyssey.py)
APP = BUILD / "Odyssey.app"
ICON = BUILD / "app-assets/OdysseyIcon.jpg"
CHAIN = "rt-totk-native-v4-unverified"


def clone(source: Path, target: Path):
    """APFS copy-on-write clone (no extra space); plain copy elsewhere."""
    target.parent.mkdir(parents=True, exist_ok=True)
    if subprocess.run(["cp", "-c", str(source), str(target)]).returncode != 0:
        shutil.copy2(source, target)


def main():
    native = BUILD / "build/odyssey-native"
    for need in (native, ICON, BUILD / "build/shader-service/totk_xlate", BUILD / "build/spirv-cross/spirv-cross",
                 BUILD / "extracted/local/romfs/romfs.bin", BUILD / "extracted/firmware/shared-fonts"):
        if not need.exists():
            raise SystemExit(f"missing {need}; build the Odyssey Native target and prepare the local data first")
    if APP.exists():
        shutil.rmtree(APP)
    contents = APP / "Contents"; macos = contents / "MacOS"; resources = contents / "Resources"; game = resources / "game"
    macos.mkdir(parents=True)
    clone(native, game / "build/odyssey-native")
    clone(BUILD / "build/shader-service/totk_xlate", game / "build/shader-service/totk_xlate")
    clone(BUILD / "build/spirv-cross/spirv-cross", game / "build/spirv-cross/spirv-cross")
    rewritten = BUILD / "rewritten"
    for item in rewritten.iterdir():
        if item.is_file() and not item.is_symlink():
            clone(item, game / "rewritten" / item.name)
    os.symlink("../rewritten", game / "rewritten/local")   # the module directory the runtime is given, as in Odyssey_build
    for name in ("romfs.bin", "runtime-index.bin"):
        clone(BUILD / "extracted/local/romfs" / name, game / "romfs" / name)
    for font in sorted((BUILD / "extracted/firmware/shared-fonts").glob("*.bfttf")):
        clone(font, game / "fonts" / font.name)
    slot = BUILD / "analysis/game-slot"
    if slot.is_dir():
        (game / "slot-dir.txt").write_text(str(slot) + "\n")
    os.symlink("../Resources/game/build/odyssey-native", macos / "odyssey-native")
    # Metal libraries precompiled from the shader cache (scripts/precompile_cached_shaders.py, needs Xcode's Metal
    # Toolchain). The runtime looks for them next to the executable path it was started by (nvn_mtl.m exe_rel, not
    # resolved), which here is Contents/MacOS, so they are linked there too.
    libs = BUILD / "build/shader-libs"
    if libs.is_dir():
        for lib in libs.glob("*.metallib"):
            clone(lib, game / "build/shader-libs" / lib.name)
        os.symlink("../Resources/game/build/shader-libs", macos / "shader-libs")
    # The whole-game shader seed (scripts/prepare_odyssey_shader_seed.py): the runtime imports build/shader-seed beside its
    # real executable (totk_shader_rt.m root_dir, symlinks resolved) into "Odyssey Data"'s cache on the first launch,
    # checking every file against seed-manifest.json; later launches only compare the receipt.
    seed = BUILD / "build/shader-seed"
    if (seed / "seed-manifest.json").is_file():
        subprocess.run(["cp", "-cR", str(seed), str(game / "build/shader-seed")], check=True)
    # Pipelines the title screen needs (Applier session, recorded 22 October): the first frame waits only for this list
    # (nvn_mtl.m warm_start reads it beside the shader map, i.e. the executable path, Contents/MacOS).
    title = BUILD / "build/pso_title.tsv"
    if title.is_file():
        clone(title, game / "build/pso_title.tsv")
        os.symlink("../Resources/game/build/pso_title.tsv", macos / "pso_title.tsv")
    subprocess.run(["xcrun", "clang", "-O2", "-Wall", "-Wextra", "-Werror", "-o", str(macos / "Odyssey"),
                    str(GAME / "scripts/odyssey_app_launcher.c")], check=True)
    subprocess.run(["sips", "-s", "format", "icns", str(ICON), "--out", str(resources / "OdysseyIcon.icns")],
                   check=True, stdout=subprocess.DEVNULL)
    info = {
        "CFBundleDevelopmentRegion": "en", "CFBundleDisplayName": "Super Mario Odyssey", "CFBundleName": "Super Mario Odyssey",
        "CFBundleExecutable": "Odyssey", "CFBundleIconFile": "OdysseyIcon",
        "CFBundleIdentifier": "org.mng.odyssey", "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundlePackageType": "APPL", "CFBundleShortVersionString": "0.2", "CFBundleVersion": "2",
        "LSApplicationCategoryType": "public.app-category.games", "LSMinimumSystemVersion": "26.0",
        "NSHighResolutionCapable": True,
    }
    with (contents / "Info.plist").open("wb") as file:
        plistlib.dump(info, file)
    subprocess.run(["codesign", "--force", "--sign", "-", str(APP)], check=True, stdout=subprocess.DEVNULL)
    print(APP)


if __name__ == "__main__":
    main()
