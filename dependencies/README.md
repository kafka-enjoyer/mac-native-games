# Local, offline build dependencies

This folder contains the dependencies previously downloaded by `build_app.py`.
The source/Python bundle is about **95 MB**; [`dotnet/`](dotnet/README.md) adds
about **11 MB** of locked NuGet packages for rebuilding the translator. Keep the
entire folder when moving this project to another Mac. The app build does not invoke the downloader, Git fetch/clone, or a Python
package index. Missing or modified dependencies stop the build; there is no
network fallback.

## Contents

| Snapshot | Commit | Used for |
|---|---|---|
| `sources/SPIRV-Cross` | `aa217aeb6c9f0ace7a0ab233b28807edf45eb165` | Shader translation, all builds |
| `sources/hactool` | `1d64a83450e025622f3468c28fc4164dad2c5ef6` | Updated game data / BOTW extraction |
| `sources/opus` (v1.6.1) | `a5d6c1b6f4e582df97390f9ac5c6e7c51cbffffe` | iOS audio library |
| `sources/libvpx` (v1.16.0) | `04def0a07f8bfa95785e30e6db95036cda17f9b2` | iOS movie library |

Snapshots are Git archives without `.git` directories. Their original license
files are included. `manifest.json` records upstream URLs, resolved immutable
commits, SHA-256 hashes of every source file, all wheels, and the requirements.
The build checks the source inventory and hashes before copying sources into its
writable work directory; it never patches these reference snapshots.

`wheels/` contains **13 binary wheels**, including all transitive dependencies.
`requirements-macos-arm64-py314.lock` pins every package and its SHA-256 hash.
Installation uses `--no-index --no-deps --only-binary=:all: --require-hashes`,
with pip's version check, cache, environment settings and config files disabled.
No source distributions or installation-time build backends are used.

**The wheelhouse targets CPython 3.14 on macOS Apple silicon.** Python 3.15 is
not supported by this bundle. Mac builds still use the already-installed
Homebrew `opus` and `libvpx` static libraries, and the translator loads Homebrew
OpenSSL/Brotli. They are not bundled, but their versions and SHA-256 hashes are
pinned in `homebrew-pins.json`; `build_app.py`, the Makefile and
`publish_native.sh` stop when they differ (`just verify-pins`; re-pin after a
reviewed `brew upgrade` with `just update-pins`).

## Build

Use the normal command from the repository root, for example:

```sh
just build-translator  # once, and after changing the translator sources
python3.14 build_app.py /path/to/game.xci -k /path/to/prod.keys
```

The app uses the verified source build in `build-artifacts/translator-offline/native`,
not the legacy precompiled executable.

No dependency preparation command is needed for this downloaded copy. The local
snapshots also cover `--platform ios`; full Xcode and its iOS/Metal SDKs must
already be installed. `make dependencies` in `games/totk` also installs offline.

## Rebuild the shader translator offline

The translator's SDK stays in Homebrew; its exact SDK/runtime, linker-library
and Xcode versions are pinned and checked. All NuGet dependencies and project
locks are in [`dotnet/`](dotnet/README.md). No SDK vendoring or linking-policy
change is needed:

```sh
zsh games/totk/tools/totk_xlate/publish_native.sh "$PWD/build-artifacts/translator-offline/native"
```

This starts from an empty package cache, uses a local-only locked restore,
publishes with `--no-restore`, and blocks IP networking during both stages.

## Online preparation (disabled)

`tools/download_dependencies.py` is **disabled**: running it raises an error,
because it fetches code from the network and rewrites this bundle and its
hashes. To refresh dependencies deliberately, re-enable it in a reviewed change
and run it on an isolated machine. When enabled, it reuses the manifest's commits and the existing Python lock, including hashes.
To change direct Python requirements, edit `games/totk/requirements.txt`, review
the change, then remove the generated lock and run preparation again to resolve
and record a new complete dependency set. To change a source revision, update
its downloader entry and the corresponding manifest commit deliberately.

The hash lists (`manifest.json`, the Python lock, `homebrew-pins.json`,
`dotnet/SHA256SUMS`, `dotnet/toolchain.txt`, the NuGet locks) are tracked in
Git while the large wheels, sources and packages are not, so a changed file
together with a changed hash shows up as a Git diff. They are still not
independent proof of upstream trust or a security audit. This removes build-time dependency fetching, not all possible operating
system network activity (for example, macOS signing/reputation checks).
