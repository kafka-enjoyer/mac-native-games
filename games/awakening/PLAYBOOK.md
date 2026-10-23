# Link's Awakening port: plan

How to build `games/awakening` the way `games/odyssey` was built, using what [HARVEST.md](HARVEST.md) collected from
LASRecomp. Each stage has a **done when** line. Don't start a stage before the previous one is done.

Status: **planning** (2026-10-23). Nothing below has been run.

## Stage 0: Set up the folder

- Copy the newest single-game runtime, `games/odyssey` (it already has `system_services.c`, `audio_out.c`,
  `freeze_watchdog.c`, and a single-version `build_*.py`), into `games/awakening/`:
  - `runtime/`, `third_party/d2r`, `third_party/d2r_gfx`, `prebuilt/macos-arm64/` (`totk_xlate` and its SHA-256),
    and the scripts `build_odyssey.py` will need (renamed `build_awakening.py`);
  - also the copied script folders `third_party/totk-scripts/` and `third_party/by3-scripts/`.
- Write `third_party/COPIES.md`: each folder, where it came from, the commit.
- Add `.gitignore` (copy Odyssey's: `*.xci *.nsp *.nsz *.keys *_build/ .venv/ __pycache__/`).
- Rename everything game-specific: in `game_version.h` add `GAME_NAME "Link's Awakening"`, `GAME_FOLDER "Awakening"`,
  `GAME_LOG "awakening"` and the game dir; then the app bundle id, the window title and the save path.
- Add `third_party/licenses/LASRecomp.txt` and the `THIRD_PARTY_NOTICES.md` row (HARVEST.md §6).

**Done when:** `git grep -nE '\.\./(totk|botw|by3|odyssey)|games/(totk|botw|by3|odyssey)' -- games/awakening` finds only
comments, and `make -C games/awakening` builds the runtime without game files.

## Stage 1: Identify and extract the game

- `scripts/inspect_input.py`: accept an XCI or NSP of title `01006BB00C6F0000` (confirm it), version 1.0.0 (v0).
  Reject anything else by hash.
- `scripts/extract_code.py`: ExeFS → `main`, `sdk`, `rtld`, `main.npdm`. **There is no `subsdk0`.**
- RomFS: no update, so no BKTR merge is needed. Plain extraction with IVFC verification is enough.
- Shared fonts from `--firmware` (six fonts, checked against the reference hashes).
- Note main's build ID: our 1.0.0 must be the binary LASRecomp's addresses are for.

**Done when:** `assets/expected-v1.0.0.json` pins the hashes of the NSOs, npdm and RomFS, and a flipped byte is caught.

## Stage 2: Rewrite and verify

- `DM_RULESET=native DM_PRIVATE_GATES=0 python third_party/d2r/patch_nso.py <exefs>/<m> <work>/rewritten <m>` for
  `sdk` and `main`.
- Run `structck.py` (0 violations) and `equiv.py` (every site, random states, mutation controls caught).
- Expect new instruction patterns. LA is built with an older toolchain than TOTK; Bayonetta 3 needed `site_spset`.
  Write any new rule into `patch_nso.py` together with its equivalence test.

**Done when:** the rewritten hashes are in `expected-v1.0.0.json`, and the results table is in README.md (as Bayonetta 3
has it).

## Stage 3: Load the modules

- In `runtime/loader.c` set `modules[]` = `{main, sdk}`. Check every `"subsdk0"` reference, including
  `runtime_module_base` callers and probes.
- Read the memory layout and pool size from LA's `main.npdm` and `GetInfo`. Don't copy LASRecomp's 3.25 GB.
- Check that C++ exception unwinding works natively. LA throws and catches inside event handling (HARVEST.md §1,
  "Probably not needed"). The loader must register the modules' `.eh_frame_hdr` the way the Switch rtld does.

**Done when:** `nn::init::Start` runs and `nnMain` is entered, and the log shows the first IPC requests.

## Stage 4: Host services for the 2019 SDK (the largest stage)

Work from HARVEST.md §2 as the checklist. Trace every IPC request (`TOTK_IPC_TRACE` or Odyssey's equivalent) and
answer each until the title screen appears.

| Service | Watch out for |
|---|---|
| `sm:` | Old `RegisterClient` / `GetService` forms |
| `hid` | **Shared-memory layout of the old SDK** (Npad entries, ring buffer sizes), style sets, vibration |
| `vi:m/u` and binder, `nvdrv` | The native window, the vsync event, `SetLayerCrop` |
| `pl:u` | Shared-font memory, per language |
| `audren:u` / `audout:u` | **Audio renderer revision** of the old SDK: input/output sizes in `audio_renderer.c` depend on the revision |
| `fs` | Save data mount; RomFS from the extracted image |
| `am` / `appletOE` | Focus, operation mode (docked / handheld), the launch parameter |
| `acc`, `time:*`, `set:sys`, `pctl:*`, `aoc:u` | Offline answers, as in Odyssey |

Rule: fix it in the platform layer. Don't patch game code to get past a service.

**Done when:** the title screen shows (the picture may still be wrong), there is sound, and the controller and keyboard
move the cursor.

## Stage 5: Picture

- NVN on Metal through `d2r_gfx`; shaders through `totk_xlate`. Start `assets/shader_list.tsv` (empty), and make the
  seed tool point at it, not at the TOTK list.
- Check first: samplers per stage (more than 16, as in the Ukuku Prairie cave), the tilt-shift DOF, the ASTC formats,
  and half precision on M1 (HARVEST.md §4).
- Compare against your own console (or an emulator, outside the port) at fixed spots: Mabe Village, Tail Cave,
  Mysterious Woods, Ukuku Prairie cave, Color Dungeon.

**Done when:** these spots look like the original, with no missing objects or black blocks, and their screenshots are in
the test evidence.

## Stage 6: Movies

- Copy `movie_host.c` (VP9 through libvpx). Add Vorbis, or confirm the SDK decodes it in software.
- Check whether the SDK's `movie::Extractor` reads WebM natively. If not, replace it using the slot map in
  HARVEST.md §3.
- Pace frames by presentation time, as Odyssey and TOTK do.

**Done when:** `opening.webm` and `title.webm` play at the right speed with sound, and skipping the opening works.

## Stage 7: Game patches (each checks its instruction word and can be switched off)

1. **Widescreen:** six aspect sites, the culling aspect, and the fovy sites. The indoor site stays at 16:9 and only
   marks interiors. Then find the Mysterious Woods fog and haze shaders by our own shader keys, and stretch their
   viewport.
2. **Frame rate:** LA's 60 fps target drops in busy areas. Measure first (Instruments, Metal HUD). Per LASRecomp,
   gameplay advances one step per frame, so above 60 fps needs interpolation (MetalFX frame interpolation, as TOTK
   does), not a faster world.
3. **Options:** 360° movement (`+0xded9f0`), blur removal (`+0x1071220`). Both off by default.

**Done when:** each patch has a `verify_*.py` that checks the original word in our 1.0.0 `main`, and 21:9 and 32:9
screenshots show no edges where nothing is drawn.

## Stage 8: Build script and app

- `scripts/build_awakening.py --game <xci|nsp> --keys prod.keys --firmware <dir>`, with the same steps as Odyssey's:
  check the input → extract → fonts → rewrite → verify → tools and runtime → shader seed → icon and app. Skip a
  step when its verified output exists.
- Saves, shader cache and logs go in `~/Library/Application Support/MacNativeGames/Awakening`.
- Add one line to the root README's update history.

**Done when:** a build from an empty work folder makes an app that plays from a new save into Tail Cave. Record the
time and the Mac model in README.md.

## Stage 9 (optional, later): Randomizer

- Phase A: RomFS only. LAS-Randomizer (MIT; its helper pulls in GPL oead/evfl, so it stays a separate program)
  writes a modified RomFS, which goes in through the existing RomFS mod path. Only seed options that need no code
  hooks.
- Phase B: code hooks (souls, keysanity, pets, shop) through the patch sites in HARVEST.md §1 ("Randomizer and warp
  hooks"). Every one behind a switch, in line with "change game logic as little as possible".

## Risks

| Risk | Effect | How we find out |
|---|---|---|
| The old SDK's hid / audren layouts | Stage 4 takes longer | Trace in stage 3 |
| New instruction patterns in the rewrite | Stage 2 needs new rules | `structck.py` on day one |
| Native C++ unwinding not set up | Crash at Marin's song (`tl/WindFishSong`) | Stage 3 test |
| Vorbis or WebM in the SDK library needs NvMM | Movies abort | Stage 6 |
| LASRecomp's addresses don't match | Patches stop at their guards (safe) | `verify_*.py` in stage 7 |
| Wrong picture in wide views | Visible edges | Stage 7 screenshots |
