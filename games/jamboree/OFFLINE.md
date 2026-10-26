# Super Mario Party Jamboree 2.3.0: not yet built in this offline fork

Merged from upstream as-is (`merge: upstream main`, 2026-10-25). Its build entry points are disabled on purpose and stop
with `NotImplementedError` / `NotImplemented` (AGENTS.md rule 1: builds are offline, every input is local and
hash-checked). `just build jamboree` prints `NotYetImplemented`. Remove the guards only once every item below is done:

- `scripts/build_jamboree.py` `main()`
- `third_party/nxnative/build_ipa_from_nsp.py` `main()`
- `runtime/ios/tools/build_ipa.sh` (exits at the top)
- `Makefile` (parse-time `$(error)`)

## Offline changes needed

- **Shader translator:** its own prebuilt .NET `prebuilt/macos-arm64/dmsh_xlate` (binary DLLs, checked only against a hash list in this folder). Needs a source build from vendored packages, or review and pinning in `dependencies/`.
- **.NET restore:** builds with `dotnet`, with a local feed holding only LibHac 0.19.0 (`--libhac-package`); unverified whether restore reaches nuget.org for other packages. It must run under `sandbox-exec` with networking denied, with all packages in `dependencies/dotnet`.
- **Unpinned Homebrew tools:** `zstd`, `spirv-cross`, `glslang` (`glslangValidator`) and `xcodegen` come from Homebrew without pins; the nxnative builder suggests `brew install` / `pip install` (`lz4 capstone fonttools backports.zstd`). Use `dependencies/` (wheels from the Python lock, SPIRV-Cross source) and the pin checker.
- **Vendored sources:** `runtime/third_party/libvpx`, `libwebp`, `stb_vorbis` and `bcdec` are copied in-tree, not listed in `dependencies/manifest.json`; add them to the manifest with hashes.
- **nxnative copy:** `third_party/nxnative` is a full copy of seedds/nxnative at `7861e7c`; review it for network access before use.

## Already done in the merge

- Identifiers renamed to `org.mng.*` (AGENTS.md rule 10).

## When adapting

Follow `games/odyssey` (BUILD_ALIGNMENT.md): call the builder from `build_app.py` after the shared offline checks, take
the staged source-built translator (`build_app.STAGED_TRANSLATOR`) and `dependencies/sources/SPIRV-Cross`
(`build_app.local_source()`), verify Homebrew libraries with `tools/homebrew_pins.py`, then add a `just build` branch
and tests in `tests/`.
