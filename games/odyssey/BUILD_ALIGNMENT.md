# Odyssey build alignment

Status (23 October 2026): **implemented; built offline from a base NSP + 1.4.1 update NSP.** Not played yet.

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
| 8 | iOS | out of scope for now |

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
      checks, app identity and data folder, no `org.macnativegames`.

**Verified:** `sandbox-exec` (networking denied) `just build odyssey` from an empty work folder in 7 minutes: 28,131
seed shaders from the source-built translator; app signature valid; `CFBundleIdentifier` `org.mng.odyssey`. Repo tests
382/382 and Odyssey tests 4/4 pass.

## Open

- [ ] **Play 1.4.1**: start the app, reach Cap Kingdom, save, load the save again. With the same code and data this
      should behave exactly as 1.3.0.
- [ ] Load a 1.3.0 save in the 1.4.1 build (same executables, so it is expected to work).
- [ ] Metal cache warm-up and a `--check` start after packaging, as TOTK/BotW do (needs a check mode in the
      launcher). Optional.
- [ ] Logs: currently `last-run.log` in the data folder (the runtime's "Show Log" reads it there). Moving them to
      `~/Library/Logs/MacNativeGames/odyssey.log` like TOTK/BotW would also need a runtime change.
- [ ] Root README: Odyssey usage line (base + update, 1.4.1).
- [ ] iOS: later phase (the runtime has `frontend_ios.m`, but it is not in the Makefile).

## Upstream merges

Upstream keeps working on `scripts/build_odyssey.py`, `Makefile`, `package_native_app.py` and the launcher. To keep
merges manageable, the fork's changes there are small and grouped; new logic lives in new files (`combine_input.py`,
`expected-v1.4.1.json`). After merging upstream Odyssey changes, keep:
`--update`/`--out`/`--translator`/`--spirv-cross-src`, no `git clone`, no `prebuilt/`, `org.mng.odyssey`, the data
folder, no session limit. `tests/test_odyssey_build.py` checks these.
