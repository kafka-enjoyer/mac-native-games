# Ori and the Blind Forest: Definitive Edition 1.0.1: not yet built in this offline fork

Merged from upstream as-is (`merge: upstream main`, 2026-10-25). Its build entry points are disabled on purpose and stop
with `NotImplementedError` / `NotImplemented` (AGENTS.md rule 1: builds are offline, every input is local and
hash-checked). `just build ori` prints `NotYetImplemented`. Remove the guards only once every item below is done:

- `scripts/build_ori.py` `main()`
- `Makefile` (parse-time `$(error)`)

## Offline changes needed

- **SPIRV-Cross:** `Makefile` runs `git clone` of SPIRV-Cross into `tooling/spirv-cross`. Use the hash-checked copy in `dependencies/sources/SPIRV-Cross`.
- **hactool:** `Makefile` runs `git clone https://github.com/SciresM/hactool.git`. Use the local pinned snapshot `build_app.py` builds.
- **Shader translator:** uses this folder's `prebuilt/macos-arm64/totk_xlate` (upstream binary). Use the source-built translator from `build-artifacts/translator-offline/native` (rule 3) instead. This folder carries its own translator sources in `tools/totk_xlate`; build them with the offline .NET toolchain (`dependencies/dotnet`) or switch to the shared translator.
- **Homebrew libraries:** links opus and libvpx from `/opt/homebrew/opt` without checking `dependencies/homebrew-pins.json` (rule 2). Add a pin group (re-pin only on request) and verify it before linking.
- **LLVM:** `third_party/d2r/structck.py` defaults to `/opt/homebrew/opt/llvm@23` (developer check only; not pinned).

## Already done in the merge

- Identifiers renamed to `org.mng.*` (AGENTS.md rule 10).

## When adapting

Follow `games/odyssey` (BUILD_ALIGNMENT.md): call the builder from `build_app.py` after the shared offline checks, take
the staged source-built translator (`build_app.STAGED_TRANSLATOR`) and `dependencies/sources/SPIRV-Cross`
(`build_app.local_source()`), verify Homebrew libraries with `tools/homebrew_pins.py`, then add a `just build` branch
and tests in `tests/`.
