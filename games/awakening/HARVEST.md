# What we can use from LASRecomp

Source: [peiikai/LASRecomp](https://github.com/peiikai/LASRecomp) at `466fee6` (MIT). Every item below says where it
came from, so it can be checked again and credited.

**How to read the addresses.** LASRecomp loads `main` at `0x7000000000` and `sdk` at `0x7004000000`
(`runtime/rt.h`), so **main offset = LASRecomp address − `0x7000000000`**. All addresses are for *Link's Awakening*
**1.0.0**. They are unverified until stage 5 of [PLAYBOOK.md](PLAYBOOK.md) checks each instruction word against our
own `main` (they were written by AI).

## 1. Patch sites (`tools/patches.py`)

LASRecomp states the expected instruction word for each site. That is exactly the guard our patches need
(`game_patches.c`: check the original instruction, stop if it differs). Only the site, the word and what the patch
means carry over. LASRecomp emits C at these sites; we would branch to host code instead.

### Display (wanted for the first playable release)

| Purpose | main offset | Expected instruction | Notes |
|---|---|---|---|
| 16:9 aspect value | `+0x16afba4` (data) | — | A float of 16/9, loaded by `ldr sN, [xM, #0xba4]` |
| Camera aspect loads, sites 0–5 | `+0x1092c`, `+0x10b58`, `+0xc1c84`, `+0xc3228`, `+0xc3edc`, `+0x85f824` | `(w & 0xffc00000) == 0xbd400000`, imm×4 = `0xba4` | Replace the 16:9 load with the output aspect |
| Culling aspect | `+0x852ad4` | `0xbd457369` `ldr s9, [x27, #0x570]` | Without it, objects at the wide edges get culled. Same site as the community 32:9 patch (Jaddey / KeatonTheBot) |
| Vertical field of view (taller than 16:9) | `+0x10914` (`0xbd4566e0`, base x23), `+0x852ad0` (`0xbd456768`, base x27) | as listed | Camera field `+0x564`. Keep the horizontal view; widen the vertical one |
| Indoor shadow aspect | `+0x1023c70` | `ldr sN, =16/9` (imm `0xba4`) | **Leave it at 16:9.** LASRecomp uses it only to tell that an interior is being drawn (interiors keep 16:9 framing) |

Related runtime logic: `runtime/hle/widescreen.c` (`rt_aspect_site`, `rt_cull_aspect`, `rt_fovy`,
`rt_indoor_aspect`). Effects drawn as a mesh around the camera, sized to cover a 16:9 view, need their viewport
stretched when the view is widened. LASRecomp finds them by fragment shader hash:

- `0xffad3b2d795231a7`: Mysterious Woods fog ring
- `0xd66b33b13b2eac29`: Mysterious Woods haze layer
- `BACKDROP_HASHES 0x71fe31bbf03c3515`

These hashes come from **LASRecomp's own shader hashing**. Find the same shaders under our `totk_xlate` keys, for
example by disabling shaders in the Mysterious Woods.

### Timing

| Purpose | main offset | Expected | Notes |
|---|---|---|---|
| Swap interval read by the frame timer | `+0xc954` | `0xb8696908` `ldr w8, [x8, x9]` | Frame timer `+0xc910`; interval setter `+0x17800`; system object field `+0x812c`. **Finding:** gameplay advances one fixed step per frame. Forcing 2 steps did *not* change Link's speed, so off by default. Use it for frame-rate research, not as a fix |

### Quality-of-life options (optional, behind switches)

| Purpose | main offset | Expected | Notes |
|---|---|---|---|
| 8-way stick snap → 360° movement | `+0xded9f0` (function entry) | `0xd10103ff` `sub sp, sp, #0x40` | Input s1/s2 = stick x/y; returns an angle in w0 (full turn 2^32, 0 = down, 2^30 = right). `hle/qol.c` `rt_snap_dir` |
| Tilt-shift set-up → blur removal | `+0x1071220` | `0xd10243ff` `sub sp, sp, #0x90` | x0 = tilt-shift object; its shader parameter handle can be removed or restored at runtime (`hle/qol.c`). The LAS-Randomizer equivalent renames a string in the module (theboy181) |
| Button-prompt position | `+0xeab138` | `0x2d060102` `stp s2, s0, [x8, #0x30]` | Used together with the prompt textures replaced in `nvn/texpatch.c` |

### Probably not needed for us (but keep in mind)

| Purpose | main offset | Expected | Why |
|---|---|---|---|
| Missing event String parameter | `+0x109fca8` | `0x321c03e0` | The game throws a C++ exception and catches it (`tl/WindFishSong`, `tl/HippoModelSlap`). LASRecomp's translated C cannot unwind; **our native code can**, as long as the loader registers the unwind info. Keep it as a test: playing Marin's song must not crash |
| Missing event Float parameter | `+0x109fb18` | `0x321c03e0` | Same, randomizer only |

### Randomizer and warp hooks (later stages only)

Live save `+0x1cbb220`; `AddItem` `+0x7e18b0` (inner add `+0x8d08e0`); level-jump request `+0x81ba80`, with request
registration at `+0x80c464` (x20) and `+0x80d718` (x19). Further sites: `ITEM_NAME`, `ITEM_EXPLANATION`, `ITEMS_PAGE`,
`MAP_PAGE`, `DGN_MAP`, `BOSS_SPAWN`, `HOOKSHOT_ATTR`, `DIG_HOLE`, `HOLE_CAP`, `UNDERWATER_*`, `TUNIC_CLEAR`,
`NO_HANDLER`, `RES_NAME`, `MB_SEEN`, mini-boss sites. See `tools/patches.py` lines 88–680; each has an instruction
assert.

## 2. What LA uses from the SDK (`runtime/hle/*.c`, `runtime/services/*.c`)

LASRecomp replaces these 71 SDK and NVN functions by name. Our host must answer **the IPC they would have sent**,
for LA's 2019 SDK:

- **vi:** `Initialize`, `OpenDefaultDisplay`, `CloseDisplay`, `CreateLayer`, `DestroyLayer`, `SetLayerCrop`,
  `GetNativeWindow`, `GetDisplayVsyncEvent`, `Finalize` → `vi:m/u`, the display service, and binder/`nvdrv` for the
  native window
- **hid:** `GetNpadState` (FullKey, JoyDual, JoyLeft, JoyRight, Handheld), `GetNpadStyleSet`,
  `BindNpadStyleSetUpdateEvent`, the vibration calls (`GetVibrationDeviceHandles`, `...Info`, `Initialize...`)
  → `hid` with the **old shared-memory layout**, and `hid:sys`
- **pl:** `GetSharedFontAddress`, `GetSharedFontSize`, `GetSharedFontLoadState` → `pl:u` plus shared-font memory
  (fonts per language: LASRecomp PR #27 by @we11adam)
- **mem / lmem:** `StandardAllocator`, unit and frame heaps. These are plain library code and run natively, so
  probably no host work
- **time:** `StandardUserSystemClock::GetCurrentTime` → `time:u/s/a`
- **swkbd:** `ShowKeyboard` → our `swkbd_host.c` (as TOTK, check the arguments struct of the old SDK)
- **nv:** `InitializeGraphics`, `SetGraphicsAllocator`, `SetGraphicsDevtoolsAllocator`, `FinalizeGraphics`
- **NVN:** everything through `nvnBootstrapLoader` / `nvnDeviceGetProcAddress` (as in `d2r_gfx/gfx/nvn/hle_nvn.c`)
- **movie:** see §3
- IPC services LASRecomp answers itself: `sm:`, `set:sys`, `time:a/s/u`, `pctl:a/r/s`, `aoc:u`, `audout:u`,
  `audren:u`, `hid:sys`. Also see `services/am.c`, `acc.c`, `fs.c`, `misc.c` for the applet, account, save and
  settings commands LA issues.

Use this as the **checklist for stage 4**: run with an IPC trace and check off each service.

## 3. Movies (`runtime/hle/movie.c`)

LA plays `.webm` (VP9 video and **Vorbis** audio; the code also handles VP8, AVC and AAC) through the SDK `movie::`
library, which follows Android's MediaExtractor/MediaCodec. The game owns the objects (vtable at +0); LASRecomp keeps
its host state at +8.

- **Extractor vtable slots:** 4 `GetTrackCount(int*)`, 5 `GetTrackConfiguration(int, MediaData*)`,
  6 `SelectTrack(int)`, 9 `GetSampleTrackIndex(size_t*)`, 10 `Read(Buffer*)`, 11 `Advance()`,
  12 `GetSampleTime(int64*)`, 15 `SetDataSource(DataSource*, const char* path)`
- **Decoder vtable slots:** 2 `Configure`, 3 `RegisterClientEvents(EventType*[4])`, 4 `GetOutputFormat`,
  6 `Start`, 9 `AcquireInputBufferIndex`, 10 `GetInputBuffer`, 11 `SendInputBufferForDecode(idx, off, size, time,
  flags)`, 12 `AcquireOutputBufferIndex`, 13 `GetOutputBuffer`, 15 `ReleaseOutputBufferIndex`,
  18 `GetOutputBufferFormat`. End of stream = flag `4`
- MIME strings handed to the game: `video/x-vnd.on2.vp9`, `video/x-vnd.on2.vp8`, `video/avc`, `audio/vorbis`,
  `audio/mp4a-latm`
- Paths: `rom:/region_common/movie/title.webm`; `movie/opening.webm` can be skipped
- 6-channel Vorbis is handed over without being mixed down (`movie.c` around line 611)

Our `movie_host.c` (copied from Odyssey or TOTK) replaces only the VP9 **Decoder**, using the same vtable-by-symbol
method. For LA, add a **Vorbis decoder** (libvorbis, or the SDK's own if it decodes in software; check first), and
check whether the SDK's **Extractor** (WebM demuxing) works natively. If it doesn't, replace it using the slot map
above.

## 4. Rendering problems already found

| Problem | Where in LASRecomp | What to do here |
|---|---|---|
| Black walls in the Ukuku Prairie cave: **16 samplers per stage on Metal** | PR #216 (@rkammoun) | Check how `d2r_gfx` binds samplers; use argument buffers if a stage needs more than 16 |
| White Link on M1: the Metal compiler miscompiled integer-mask half-float merges | `nvn/maxwell/translate.c` ~l.2014, PR #18 (@Tensorlong) | Watch for the same in SPIRV-Cross output on M1 |
| ASTC textures | `nvn/astc.c`, `tools/test_astc*.c` | Apple GPUs sample ASTC natively; use this only as a check for the formats LA uses |
| Prompt and icon textures replaced (Xbox/PS, Hero Mode icon) | `nvn/texpatch.c` | Optional; the replacement art must come from the player, not from this repository |
| Tilt-shift DOF is LA's signature effect | `hle/qol.c` | Must look right before any performance work (CONTRIBUTING: picture first) |
| Output scale, dynamic resolution | `nvn/output_scale.c` | Ideas only; we use MetalFX |

## 5. Other findings

- **Heap:** LASRecomp gives a 3.25 GB heap (`HEAP_MAX 0xD0000000`) and a 4 GB alias region. Not a retail figure;
  get the real pool from `GetInfo` on LA's npdm.
- **Saves:** see `services/fs.c` for the save-data layout LASRecomp uses (one save per randomizer seed). We only need
  the vanilla save.
- **Controller:** `hle/input.c` handles a "test device" id `0x7E57` and a mapping file for unrecognised controllers
  (PR #26). Our `gamepad.m` already does more.
- **Fonts:** six shared fonts from the player's firmware; LASRecomp has fallbacks. We follow `--firmware` /
  `--shared-fonts`, as Odyssey does.

## 6. Credit

If any of this goes into `games/awakening`, add a row to the root `THIRD_PARTY_NOTICES.md`:

> Link's Awakening patch-site addresses, the movie API slot map and the rendering notes in `games/awakening` are from
> [LASRecomp](https://github.com/peiikai/LASRecomp) `466fee6` (MIT), reimplemented for this runtime.

and put LASRecomp's LICENSE in `games/awakening/third_party/licenses/LASRecomp.txt`. Credit the community mods behind
the options as well: Owen_Splat's *360 Controls (And More!)*, and theboy181 for blur removal.
