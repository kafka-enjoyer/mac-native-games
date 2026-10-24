# Odyssey build alignment

Status (23 October 2026): **implemented; built offline from a base NSP + 1.4.1 update NSP; plays (known issues: flicker, stutters).**

Goal: build Super Mario Odyssey the way Tears of the Kingdom and Breath of the Wild are built, from the same command
shape, offline, from separate base and update files, for update 1.3.0 and 1.4.1.

```sh
just build odyssey     # dumps/odyssey/odyssey-base-v0.nsp + odyssey-update-v393216.nsp -> dist/odyssey/mac/
python3.14 build_app.py BASE.nsp --update UPDATE.nsp -k prod.keys --firmware FIRMWARE_DIR \
  --work build-artifacts/work/odyssey -o "dist/odyssey/mac/Super Mario Odyssey.app"
```

## Decisions

| # | Question | Decision |
|---|---|---|
| 1 | Architecture | `build_app.py` recognises Odyssey by title ID and calls the builder in `games/odyssey` (kept self-contained) |
| 2 | Saves location | `~/Library/Application Support/MacNativeGames/Odyssey`; no migration of old "Odyssey Data" (none existed) |
| 3 | Translator | the shared source-built `totk_xlate`, unless later translator changes break Odyssey |
| 4 | 1.4.1 RomFS pin | recorded after the first IVFC-verified build |
| 5 | App name | `Super Mario Odyssey.app`, bundle `org.mng.odyssey` (AGENTS.md rule 10) |
| 6 | Session limit | dropped (opt-in `session-minutes.txt` kept for test sessions) |
| 7 | Inputs | base + `--update` like TOTK/BotW; a new function combines them into the one container the upstream scripts read, so those scripts stay unchanged |
| 8 | iOS | out of scope for the Mac phase; planned as phase 2 below |
| 9 | iOS / visionOS tooling | **copy** `games/totk/ios` into `games/odyssey/ios` (CONTRIBUTING: own copies, listed in `third_party/COPIES.md`), not shared |
| 10 | Test devices | iPhone 16 Pro (A18 Pro, 8 GB) and Apple Vision Pro (M5) |

## Done

**Architecture (1, 5)**
- [x] `build_app.py`: `TITLES['0100000000010000'] = 'odyssey'`, `APPS['odyssey'] = ('Super Mario Odyssey',
      'org.mng.odyssey', 'Odyssey')`, `build_odyssey()`. It rejects `--platform ios|visionos`, `--mod` and
      `--shared-fonts`, checks package roles (`check_package`), decompresses an NSZ update
      (`prepare_update_container`), runs the builder with the work folder's Python, then runs `lsregister`. If
      `--work`/`-o` are not given, the defaults are next to the game file (`Odyssey_build`, `Super Mario Odyssey.app`).
- [x] `scripts/build_odyssey.py` keeps upstream's eight steps and adds `--update`, `--out`, `--translator`,
      `--spirv-cross-src`. Its work layout is `<work>/odyssey/v<version>/`, which holds upstream's `extracted/local`
      etc., so `prepare_runtime.py`, the launcher and the runtime keep their `local` paths.

**Separate base and update (7)**
- [x] `scripts/combine_input.py` (new): writes a PFS0 holding every file of the base (NSP, or the XCI secure
      partition) and the update NSP, byte for byte, into `<work>/odyssey/input/combined.nsp`. A file in both packages
      must have the same size. The result is cached by source path, size and mtime, and deleted after a successful
      build (6 GB). A combined XCI/NSP without `--update` still works.

**Versions (4)**
- [x] Update version chosen from the update's Control NACP (`inspect_version.py`, which now accepts `1.3.0`/`1.4.1`
      and puts its temp folder in the work folder), never from the file name.
- [x] `assets/expected-v1.4.1.json`. ExeFS and rewrite hashes are the same as 1.3.0 (the build confirmed them). The
      RomFS was recorded from the first build and **equals 1.3.0's** (size 5,678,168,236, SHA-256 `6bb432a4…`).
      1.3.0 keeps upstream's file name `expected-local-update.json`, so merges stay easy.
- [x] `prepare_runtime.py --expected <file>`; an unpinned RomFS (`null`) is accepted IVFC-only, with its values
      printed.
- [x] 1.4.1's update stores its AES-CTR-Ex table only up to the indirect table. `third_party/by3-scripts/merge_romfs.py`
      accepts that layout; the indirect table is then plain AES-CTR with the section's generation.
- [x] Version string from the build: Makefile `GAME_VERSION` sets `-DTOTK_GAME_VERSION` (`game_version.h` keeps 1.3.0
      as its default). The shader seed is labelled through `ODYSSEY_VERSION`, and the icon is taken from the update's
      Control data whatever its version.

**Offline and pinned (3)**
- [x] SPIRV-Cross: the hash-checked copy from `dependencies/` (`local_source`), passed as Makefile `SPIRV_CROSS_SRC`.
      No `git clone`.
- [x] Translator: the staged source-built `totk_xlate` (`checked_translator`), passed as Makefile `TRANSLATOR`. The
      default is the repository's source build; `prebuilt/` is reference only.
- [x] Python from the hash-locked venv; Homebrew opus/libvpx checked against the pins by `prerequisites()`; no
      `pip install`/`brew install` hints.
- [x] `make` gets absolute paths: any work folder without spaces works.
- [x] `prepare_runtime.py` imports `relr` from its own `third_party/d2r` instead of `games/by3`.

**Packaging (2, 6)**
- [x] Launcher: data in `~/Library/Application Support/MacNativeGames/Odyssey` (saves, shader cache, `last-run.log`,
      backups); no session limit by default.
- [x] `package_native_app.py`: `org.mng.odyssey`, "Super Mario Odyssey"; no seeding of saves or of the session limit
      file. The builder puts the app at `--out` (an APFS clone, replacing the old app only when complete).

**Justfile, docs, tests**
- [x] `.justfile`: `odyssey-game`, `odyssey-update`, `just build odyssey` (Mac only), `clean`/`clean-work odyssey`,
      the firmware unzip shared with BotW.
- [x] `AGENTS.md`, `games/odyssey/README.md`, `third_party/COPIES.md` updated.
- [x] `tests/test_odyssey_build.py`: combining base and update, version pins, no fetches, no `prebuilt/`, dispatch
      checks, app identity and data folder, only `org.mng` identifiers.

**Verified:** `sandbox-exec` (networking denied) `just build odyssey` from an empty work folder in 7 minutes: 28,131
seed shaders from the source-built translator; app signature valid; `CFBundleIdentifier` `org.mng.odyssey`. Repo tests
382/382 and Odyssey tests 4/4 pass.

## Open

- [x] **Play 1.4.1**: the app starts and plays (user, 23 October). Occasional flicker and stutters remain: listed in
      AGENTS.md "Known issues", to be debugged later.
- [ ] Load a 1.3.0 save in the 1.4.1 build (same executables, so it is expected to work).
- [ ] Metal cache warm-up and a `--check` start after packaging, as TOTK/BotW do (needs a check mode in the
      launcher). Optional.
- [ ] Logs: currently `last-run.log` in the data folder (the runtime's "Show Log" reads it there). Moving them to
      `~/Library/Logs/MacNativeGames/odyssey.log` like TOTK/BotW would also need a runtime change.
- [ ] Root README: Odyssey usage line (base + update, 1.4.1).
- [ ] iOS and visionOS: phase 2 below.

## Phase 2: iOS and visionOS (plan, not started)

Target: the same command shape as Tears of the Kingdom's device builds.

```sh
just build odyssey ios          # dist/odyssey/ios/Super Mario Odyssey.ipa (unsigned)
just build odyssey visionos     # dist/odyssey/visionos/Super Mario Odyssey.ipa (unsigned)
just install "iPhone 16 Pro" odyssey ios
just install "Apple Vision Pro" odyssey visionos
```

### What is already there (checked 23 October)

- iOS mechanism: iOS allows no unsigned executable memory, so TOTK's iOS build has the Mac build of the runtime dump
  the final patched game code (`<host> <rewritten> export-ios`, `TOTK_EXPORT_IOS`) and links it into the app binary
  (`gen_embed.py` -> `embed.S` / `ios_embed.h`). Odyssey's `runtime/loader.c` already has both halves
  (`export_ios_text`, the embedded-module loader under `TARGET_OS_IPHONE`); `runtime/frontend_ios.m` exists.
- Test compile against the SDKs, with the generated headers of the 1.4.1 build:
  - **iOS (iphoneos, `-mcpu=apple-a15`)**: 56 of 58 runtime/graphics files compile unchanged. The other two need
    build-generated inputs only: `loader.c` needs `ios_embed.h` (`gen_embed.py`), `opus_codec.c` needs `opus.h`
    (device opus built from `dependencies/` by `build_deps.py`).
  - **visionOS (xros)**: 54 of 56 compile. `runtime/frontend_ios.m` uses `UIScreen` and
    `third_party/d2r_gfx/gfx/nvn/totk_mfx.m` uses `MTL4FXFrameInterpolator`, both unavailable on visionOS. TOTK's
    copies already handle this (17 visionOS guards in TOTK, 0 in Odyssey): port those guards.
- `gamepad_feedback.m` already keeps its IOKit HID code Mac-only (`!TARGET_OS_OSX`), as TOTK's does.
- Device libraries: `build_app.prepare_work(ios=True)` already copies the pinned opus/libvpx sources from
  `dependencies/` for device builds.

### Tasks

**1. Copy the iOS project** (`games/totk/ios` -> `games/odyssey/ios`, record the source commit in `COPIES.md`)
- [ ] `project.yml`: target `OdysseyIOS`, product `Odyssey`; sources = Odyssey's `runtime/` (excluding `frontend.m`,
      `gpu_path_probe.m`, `vpool_probe.m`, `loader.c`, which is added again with `-Dmain=totk_host_main`) and its own
      `third_party/d2r_gfx`; `-DGAME_ODYSSEY=1 -DTOTK_GAME_VERSION="<version>"`; bundle `org.mng.odyssey`; iOS 26,
      iPhone/iPad (`TARGETED_DEVICE_FAMILY 1,2`); visionOS variant via `project_for_platform` (as TOTK).
- [ ] `Sources/main.m`: TOTK's app (scene delegate, audio session and interruption handling, seed pack unpacking, debug
      log switch, Documents layout) with Odyssey's environment from `scripts/odyssey_app_launcher.c`:
      `TOTK_GPU_ALLOW_SUBMIT/WIDEN/BLOCKRT`, `TOTK_SHADER_ASYNC=1`, `TOTK_ROMFS`, `TOTK_SHARED_FONTS`, `TOTK_PROFILE_DIR`,
      `TOTK_SHADER_CACHE` (`rt-<chain>` folder), `TOTK_GAME_SLOT_DIR`, `TOTK_SLOT_OWNER=user`. Remove TOTK-only parts:
      add-on content (`TOTK_AOC`), the RomFS overlays and the optional external 17 GB image (Odyssey's 5.7 GB goes in
      the app), the shared-list contribution file. Save backups as in the Mac launcher (last five sessions).
- [ ] `Sources/Info.plist`, `Settings.bundle` (language, debug log), entitlements: keep
      `com.apple.developer.kernel.increased-memory-limit` (Odyssey uses about 3.5 GB on the Mac).
- [ ] `touch_pad.m/.h`: on-screen controls with Odyssey's buttons (A jump, B, Y cap throw, X, ZL/ZR crouch, + pause);
      check the layout on the iPhone 16 Pro.

**2. Copy and adapt the tools** (`ios/tools/`)
- [ ] `build_ipa.py`: one version per build (`--version 1.3.0|1.4.1`), work tree `<work>/odyssey/vNNN`; generated
      headers from its `build/`; `export-ios` with `build/odyssey-native`; `gen_embed.py` for `main subsdk0 sdk`; the
      seed `build/shader-seed` compiled to metallibs (`compile_seed.py`, iphoneos / xros); GameData = merged RomFS
      (`romfs.bin`, `runtime-index.bin`), shared fonts, seed, `pso_title.tsv`; the game's icon from
      `app-assets/OdysseyIcon.jpg`; no TOTK shader list export (Odyssey has none).
- [ ] `gen_embed.py`, `compile_seed.py`, `build_deps.py` (opus/libvpx from the copied pinned sources, no fetch),
      `xcode_dir.py`: copied as they are, paths adjusted.
- [ ] `install_device.py`: copy; `Odyssey.app` payload, default bundle `org.mng.odyssey` + `.<team>`; the dedicated
      signing Apple ID (`MNG_SIGNING_TEAM` from `.signing.env`, profile and certificate team checks) unchanged; iOS
      and visionOS profiles.

**3. Builder and dispatch**
- [ ] `scripts/build_odyssey.py --platform macos|ios|visionos`: steps 1-7 unchanged (step 6 still builds the Mac
      runtime: it runs `export-ios`); step 8 runs `ios/tools/build_ipa.py` instead of packaging the Mac app.
- [ ] `build_app.py build_odyssey()`: allow `ios` / `visionos`, `prepare_work(ios=True)`, `.ipa` output, no shader
      reminder agent; device disk check (IPA about 6-7 GB plus the metallib seed).
- [ ] `.justfile`: drop the Mac-only guard for Odyssey; `install` accepts `odyssey` (passes Odyssey's
      `install_device.py`).

**4. visionOS**
- [ ] Port TOTK's visionOS guards into Odyssey's `runtime/frontend_ios.m` (no `UIScreen`; drawable size from the view,
      `runtime_ios_sync_drawable`) and `totk_mfx.m` (no frame interpolator on visionOS).
- [ ] main.m visionOS branch as TOTK: docked mode, 1280x720 16:9 window, `GCEventInteraction` so controller input is not
      turned into pinches, MetalFX upscale off by default; no asset-catalog icon (as TOTK).

**5. Tests and docs**
- [ ] `tests/test_odyssey_build.py`: device builds accepted, Odyssey's iOS project uses only `games/odyssey` sources
      (no `../totk` paths), bundle `org.mng.odyssey`, device deps from `dependencies/` only, visionOS project swap.
- [ ] README (Odyssey) device section; AGENTS.md justfile table; this file.

### Device checks (iPhone 16 Pro, Apple Vision Pro M5)
- [ ] Installs and starts; first start imports the seed; reaches Cap Kingdom; save and load.
- [ ] Memory: stays under the iPhone's limit with the increased-memory entitlement (8 GB device); watch for jetsam.
- [ ] Frame rate and render size (Mac: 1600x900 with MetalFX upscale). Choose the iPhone defaults from measurements.
- [ ] Controllers (MFi / DualSense / Joy-Con / Pro Controller) and touch controls; Vision Pro with a controller.
- [ ] Audio (interruptions, speaker / headphones), movies (VideoToolbox H.264 path, `runtime/movie_host.c`).
- [ ] Known Mac issues (flicker, stutters, AGENTS.md "Known issues"): compare on the devices.

### Risks
- Memory headroom on the iPhone (about 3.5 GB in play on the Mac).
- GPU stability: the Mac launcher's history mentions GPU driver panics in long sessions with the copied renderer.
- Motion controls: some moves use Joy-Con motion; a regular controller or touch may need a button mapping.
- Build time and size: about 28,000 seed shaders compiled to metallibs per SDK; IPA about 6-7 GB.

## Upstream merges

Upstream keeps working on `scripts/build_odyssey.py`, `Makefile`, `package_native_app.py` and the launcher. To keep
merges manageable, the fork's changes there are small and grouped; new logic lives in new files (`combine_input.py`,
`expected-v1.4.1.json`). After merging upstream Odyssey changes, keep:
`--update`/`--out`/`--translator`/`--spirv-cross-src`, no `git clone`, no `prebuilt/`, `org.mng.odyssey`, the data
folder, no session limit. `tests/test_odyssey_build.py` checks these.
