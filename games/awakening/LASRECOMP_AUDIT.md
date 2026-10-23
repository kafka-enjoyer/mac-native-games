# LASRecomp compared with this repository

Reviewed: [peiikai/LASRecomp](https://github.com/peiikai/LASRecomp) at `466fee6` (2026-10-22), MIT license.

## In short

LASRecomp and MacNativeGames run Switch games in two different ways, so LASRecomp's core cannot be merged here.
What carries over is what it has learned about *Link's Awakening*: addresses, the SDK and services the game uses, the
movie API, and rendering problems. [HARVEST.md](HARVEST.md) lists those, and [PLAYBOOK.md](PLAYBOOK.md) plans the port
on this repository's pipeline.

## Side by side

| | MacNativeGames (`games/totk`, `by3`, `odyssey`) | LASRecomp |
|---|---|---|
| CPU model | ARM64 code runs **as it is**. Ahead of time, `third_party/d2r/patch_nso.py` rewrites only x18, TLS, `svc` and the counter registers. | **Static recompilation**: `tools/gen.py` and `lifter.py` (Capstone, plus Unicorn to resolve jump tables) turn ARM64 into C, which is compiled into `lasgame.dylib/.so/.dll` with clang or zig, on the player's machine |
| Verifying the rewrite | `structck.py`, `equiv.py` (emulator comparison with negative controls) and pinned `expected-*.json` hashes | `GAMELIB_ID` is a hash of the generator sources and flags; there is no site-by-site equivalence check |
| OS layer | Horizon **svc and IPC** answered by the host (`ipc.c`, `services.c`, `audio_renderer.c` and so on) | **SDK functions replaced by symbol name** (`HLE_FUNC("_ZN2nn3hid12GetNpadState...")`, 71 of them), plus a small IPC layer (`sm:`, `set:sys`, `time:*`, `pctl:*`, `aoc:u`, `audout:u`, `audren:u`, `hid:sys`) |
| Threads | `threads.c`, host pthreads, guest code on its own stacks | `kernel.c` scheduler; threads longjmp back to `thread_main` at safe points |
| Graphics | `d2r_gfx` NVN on Metal 4 | Its own NVN layer: `nvn/objects.c`, `cmdbuf.c`, `metal.m` / `renderer.m`, and a Vulkan backend |
| Shaders | Ryujinx `Graphics.Shader` → SPIR-V → SPIRV-Cross → MSL (`totk_xlate`, NativeAOT) | Its own Maxwell SM5 → MSL/GLSL translator in C (`nvn/maxwell/translate.c`, about 2.3k lines) |
| Movies | `movie_host.c`: replaces the VP9 `movie::Decoder` (libvpx) | `hle/movie.c`: replaces both `movie::Extractor` and `movie::Decoder` with FFmpeg (VP9/VP8/AVC video, Vorbis/AAC audio) |
| Input files | XCI/NSP plus `prod.keys`, extracted and verified by the build | Already-extracted `exefs/` and `romfs/` of v1.0.0 |
| Platforms | macOS 26 (Metal 4), iOS 26 | macOS 15+, Windows x86-64, Linux x86-64 and aarch64 |
| Extras | Shader seed and shared shader list, MetalFX, frame interpolation | Randomizer (vendored LAS-Randomizer), ImGui overlay, save editor, warp menu, quality-of-life options |

## Why we can't merge it

1. **The CPU model is against the rules here.** CONTRIBUTING.md requires that "the game's own ARM64 code runs
   natively". LASRecomp runs a C translation of it instead. Its build also uses Unicorn (a CPU emulator), even if
   only to resolve jump tables.
2. **The OS layer sits at a different level.** LASRecomp replaces `nn::hid`, `nn::vi`, `nn::pl` and `nv::` at the
   symbol level, so it never sees the IPC those SDK functions would send. We run the game's `sdk` module as it is,
   so our host has to answer that IPC, for an SDK about four years older than the TOTK SDK the current host was
   written for.
3. **Game patches are written as code-generator hooks.** Every patch in `tools/patches.py` returns *C source* that
   replaces one instruction. For us the addresses and the expected instruction words carry over; the way each patch
   is applied does not. We would need branch-out stubs through the rewriter's gate or patch-site system, as
   `game_patches.c` does in the other games.
4. **The repository layout.** Each game here carries its own runtime. LASRecomp's runtime cannot sit beside the
   d2r loader.

## Where LASRecomp helps

- It shows LA 1.0.0 can be played start to finish from a reconstructed OS layer and an NVN replacement. Nothing
  about the game rules out the port.
- It maps exactly which SDK features LA uses (see HARVEST.md §2). That cuts down the host work to plan for.
- Patch sites are documented with the expected instruction word, which matches our patch-guard rule.
- Its known rendering problems (16 samplers per stage, M1 half precision, ASTC, effects that show at the edges of a
  wide view) tell us where to look first.

## What we won't take

| Component | Why not |
|---|---|
| `tools/gen.py`, `lifter.py`, `analyze.py`, `passes.py`, `simd_c.py`, `runtime/simd*.h`, `cpu.h` | The C-translation model; not needed when the code runs natively |
| `runtime/kernel.c`, `dispatch.c`, `gamelib.c`, `gamebuild.c` | Its scheduler and how it builds and loads the translated library |
| `runtime/nvn/maxwell/translate.c` | We already have the more widely tested Ryujinx translator. Keep it in mind only as a comparison when a shader breaks |
| `runtime/nvn/vulkan/*`, `platform/windows.c`, `platform/linux.c` | Not our targets |
| `runtime/ui/*.mm` (ImGui) | Our frontend is AppKit/UIKit (`frontend.m`) |
| Randomizer code hooks (`hle/souls.c`, `keysanity.c`, `pets.c`, ...) | They depend on the generator's hook sites. Possible later (PLAYBOOK stage 9) |
| The seed generator (oead, evfl, Keystone: GPL) | It's a separate tool. If we ever ship it, it stays a separate program, as LASRecomp keeps it |
