# AGENTS.md

Guidance for coding agents working in this repository. Project rules for the port itself (no game content, no CPU
emulation, picture quality) are in [CONTRIBUTING.md](CONTRIBUTING.md). Read it too; this file does not repeat it.

## Overview

Native Apple-silicon ports of Nintendo Switch games (Tears of the Kingdom, Breath of the Wild; others in progress). The
game's own ARM64 code is rewritten ahead of time and runs natively; NVN graphics run on Metal. `build_app.py` builds a
macOS `.app` or an unsigned iOS / visionOS `.ipa` from the user's own game dumps.

This is an **offline-hardened fork** of [ly05010419/MacNativeGames](https://github.com/ly05010419/MacNativeGames):
- `origin` = `git@github.com:kafka-enjoyer/mac-native-games.git` (push here, `main`)
- upstream has no remote configured; fetch it by URL (see [Merging upstream](#merging-upstream))

## Rules

1. **Builds are offline.** No build step may download code or data: no `git clone/fetch`, `pip` from an index, `curl`,
   CMake `FetchContent`, NuGet feeds, `brew install`. Everything comes from `dependencies/` and is hash-verified
   (`dependencies/manifest.json`, the Python lock, `dotnet/SHA256SUMS`, `dotnet/toolchain.txt`). The .NET and clang
   steps of the translator build run under `sandbox-exec` with networking denied. No network fallbacks.
2. **Homebrew libraries are pinned.** opus/libvpx (Mac game) and OpenSSL/Brotli (translator) must match
   `dependencies/homebrew-pins.json`; builds stop otherwise. Re-pin only on explicit request after a reviewed upgrade.
3. **The translator is source-built.** The app uses `build-artifacts/translator-offline/native/totk_xlate` (with its
   `.sha256`). `games/totk/prebuilt/` is upstream's binary, kept for reference only. It is never used and never a fallback.
4. **Disabled on purpose:** `tools/download_dependencies.py` and `games/totk/scripts/collect_shader_issues.py` raise
   errors (they fetch code / third-party data). Do not re-enable them without being asked.
5. **iOS signing uses a dedicated Apple ID**, never the user's personal one: `install_device.py` requires
   `MNG_SIGNING_TEAM` (from the gitignored `.signing.env`) and checks the profile and certificate team. Building an IPA
   needs no signing at all.
6. **Never commit game content or secrets**: dumps, keys, firmware, saves, `.signing.env`, `.p8` keys.
7. **Do not commit or push unless the user asks.** Show `git status` / the diff for review first.
8. **Never `git pull --rebase` / rebase `main`.** History contains merge commits whose conflict resolutions hold the
   offline adaptations; a rebase drops them. Use `git pull --ff-only` or `--no-rebase`.
9. **`games/awakening/` is developed by a separate agent on branch `awakening-poc`** (proof of concept). Do not edit
   it on `main`; the branch is merged into `main` only when the user asks (`merge: awakening-poc (<summary>)`).
10. **Identifiers use `org.mng`, never `org.macnativegames`.** Bundle IDs, data-bundle IDs, `defaults` domains,
    LaunchAgent labels and docs: `org.mng.<game>` (`org.mng.totk`, `org.mng.botw`, `org.mng.odyssey`, `org.mng.by3`).
    Upstream merges reintroduce `org.macnativegames`; rename it during conflict resolution.

## Directory structure

| Path | Contents | Git |
|---|---|---|
| `build_app.py` | The builder: extract, rewrite, shaders, package (`--platform macos\|ios\|visionos`) | tracked |
| `games/totk/` | Shared TOTK + BotW runtime (`runtime/`), NVN-on-Metal (`third_party/d2r_gfx`), rewriter, scripts, iOS project (`ios/`), translator sources (`tools/totk_xlate`), `Makefile` | tracked |
| `games/botw/` | BotW-specific assets, scripts, expected hashes | tracked |
| `games/odyssey/`, `games/by3/` | Other ports; each carries its own copies (see CONTRIBUTING) | tracked |
| `games/awakening/` | Link's Awakening proof of concept (notes so far), developed on `awakening-poc` (rule 9) | tracked |
| `vendor/ryujinx/` | Ryujinx shader translator sources (patched at build) | tracked |
| `tools/` | `homebrew_pins.py` (pin check/update), disabled `download_dependencies.py` | tracked |
| `tests/` | Python unit tests (`unittest`), incl. offline/supply-chain guards | tracked |
| `docs/` | Design and porting notes | tracked |
| `dependencies/` | Vendored sources, wheels, NuGet packages. **Only** the hash lists, locks, pins and READMEs are tracked | partly |
| `dumps/` | User's game files: `totk/`, `botw/`, `keys/prod.keys`, `firmware/` (zip + unpacked `23.0.1/`) | ignored |
| `build-artifacts/` | `translator-offline/native/` (source-built translator), `work/<game>/` (build work folders, tens of GB) | ignored |
| `dist/<game>/<platform>/` | Releases: `Tears of the Kingdom.app` / `.ipa`, `Breath of the Wild.app` / `.ipa` | ignored |

## Justfile recipes

Run `just --list`. Defaults: `game=totk`, `platform=mac`. Paths are just variables and can be overridden
(`just totk-update=dumps/totk/other.nsp build`).

| Recipe | What it does |
|---|---|
| `just build [totk\|botw] [mac\|ios\|visionos]` | Build from `dumps/` into `dist/<game>/<platform>/`, work folder `build-artifacts/work/<game>` (shared across platforms). Device builds pass `--no-shader-reminder`. BotW builds 1.9.0 (base + update + both DLC + firmware fonts); visionOS is TOTK only |
| `just install "<device>" [game] [ios\|visionos]` | Sign with the dedicated Apple ID (`.signing.env`) and install |
| `just clean [game\|all] [platform\|all]` | Remove releases only |
| `just clean-work [game\|all]` | Remove work folders (next build starts from scratch) |
| `just build-translator` | Rebuild the translator from source, offline. Needed after changes to `games/totk/tools/totk_xlate/` or `vendor/ryujinx/` |
| `just verify-pins` / `just update-pins` | Check / re-pin Homebrew libraries (update only when asked) |

Saves and shader caches live in `~/Library` and are never touched by these recipes.

## Testing

```sh
python3.14 -m venv /tmp/offvenv
PIP_CONFIG_FILE=/dev/null /tmp/offvenv/bin/pip --isolated install --no-index --find-links dependencies/wheels \
  --only-binary=:all: --require-hashes --no-deps -r dependencies/requirements-macos-arm64-py314.lock
/tmp/offvenv/bin/python -m unittest discover -s tests
```

All tests must pass before committing. To prove a change stays offline, run the build under
`sandbox-exec -p '(version 1) (allow default) (deny network*) (allow network* (local unix-socket))' just build`.
Full builds take a long time and ~60 GB; a smoke run can be stopped once step 1/4 starts.

## Commit conventions

- Conventional commits: `<type>[(scope)][!]: <description>`, types `feat, fix, refactor, docs, test, chore, perf, ci`
  (as in CONTRIBUTING). Use `!` plus a `BREAKING CHANGE:` footer for breaking changes.
- Upstream merges: `merge: upstream main (<summary>)`, with a body that lists the merged commits and how they were
  adapted for the offline build.
- Body: what changed and why, grouped by file or area. No game data, keys or personal paths in messages.

## Merging upstream

```sh
git fetch https://github.com/ly05010419/MacNativeGames.git main:refs/remotes/upstream/main
git log --oneline HEAD..upstream/main
git diff HEAD...upstream/main | grep '^+' | grep -nE 'git (clone|fetch)|curl|wget|urlopen|pip.*install|FetchContent|brew install|https?://'
git merge --no-ff --no-commit upstream/main
git grep -n 'org\.macnativegames' -- . ':!games/awakening'   # must find nothing (rule 10)
```

- Review every new commit for network access, new dependencies and new Homebrew links before merging.
- Resolve conflicts by keeping upstream's feature **and** the offline behaviour (local sources, hash checks, pins,
  dedicated signing). Upstream regularly reintroduces fetches (e.g. SPIRV-Cross in `publish_native.sh`); adapt them to
  `dependencies/` via `build_app.local_source()`.
- Translator sources changed → `just build-translator`. Then run the tests, commit, and push `main` only when asked.

## Gotchas

- `build_app.py` takes `-o/--out` (not `--output`) and puts its work folder **next to the game file** unless `--work`
  is given. Always use the recipes or pass `--work build-artifacts/work/<game>`.
- Use `python3.14` (the wheels target CPython 3.14 / macOS arm64).
- `publish_native.sh` stops if `brew`/Xcode/clang versions differ from `dependencies/dotnet/toolchain.txt`.
- The managed translator build (`--managed`, `make shader-tools`) cannot link SPIRV-Cross; use
  `TOTK_XLATE_SPIRV_CROSS=process` with it.
- BotW update `v1114112` is 1.9.0; firmware 23.0.1's shared fonts match the expected hashes.
- Identifiers are `org.mng.<game>` (rule 10); upstream uses `org.macnativegames.<game>`.
