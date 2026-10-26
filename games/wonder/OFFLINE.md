# Super Mario Bros. Wonder 1.0.0 / 1.2.1: not yet built in this offline fork

Merged from upstream as-is (`merge: upstream main`, 2026-10-25). Its build entry points are disabled on purpose and stop
with `NotImplementedError` / `NotImplemented` (AGENTS.md rule 1: builds are offline, every input is local and
hash-checked). `just build wonder` prints `NotYetImplemented`. Remove the guards only once every item below is done:

- `scripts/build_wonder.py` `main()`
- `Makefile` (parse-time `$(error)`)

## Offline changes needed

- **SPIRV-Cross:** `scripts/build_wonder.py` `git_fetch()` clones `SPIRV_CROSS` (commit `aa217ae`) from GitHub. Use the hash-checked copy in `dependencies/sources/SPIRV-Cross`.
- **Shader translator:** uses this folder's `prebuilt/macos-arm64/totk_xlate` (upstream binary). Use the source-built translator from `build-artifacts/translator-offline/native` (rule 3) instead. `step_app` copies it into the app.
- **Homebrew libraries:** links opus and libvpx from `/opt/homebrew/opt` without checking `dependencies/homebrew-pins.json` (rule 2). Add a pin group (re-pin only on request) and verify it before linking.
- **Launcher network access:** `app/launcher.m` downloads shader-list contributions from `gist.githubusercontent.com` and runs the GitHub CLI (`gh`) to submit them. Disable it, as for TOTK (`--no-shader-reminder`, no uploads).
- **LLVM:** `third_party/d2r/structck.py` defaults to `/opt/homebrew/opt/llvm@23` (developer check only; not pinned).

## Already done in the merge

- Identifiers renamed to `org.mng.*` (AGENTS.md rule 10).

## When adapting

Follow `games/odyssey` (BUILD_ALIGNMENT.md): call the builder from `build_app.py` after the shared offline checks, take
the staged source-built translator (`build_app.STAGED_TRANSLATOR`) and `dependencies/sources/SPIRV-Cross`
(`build_app.local_source()`), verify Homebrew libraries with `tools/homebrew_pins.py`, then add a `just build` branch
and tests in `tests/`.
