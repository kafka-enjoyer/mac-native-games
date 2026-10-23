# Pinned offline translator dependencies

Homebrew stays in the toolchain. This folder vendors only the **59 NuGet package
archives** needed by the translator (about **11 MB**), not the .NET SDK. There is
no change to native/static/dynamic linking policy: the translator still uses
NativeAOT and Homebrew's OpenSSL/Brotli libraries.

## Pinned toolchain

- Homebrew `dotnet` **10.0.402**, runtime/NativeAOT **10.0.13**.
- Homebrew `openssl@4` **4.0.3**, `brotli` **1.2.0**.
- Xcode **27.0**, build **27A266a**, with its Clang and macOS SDK.

Exact installed versions are checked against `toolchain.txt`. SDK selection is
also pinned by `global.json` with roll-forward disabled. Homebrew's three
formulae were pinned with:

```sh
brew pin dotnet openssl@4 brotli
```

On another Mac, install the same toolchain before going offline. No toolchain
is installed or upgraded by the rebuild script. An unexpected version causes
an error rather than silently changing the build.

## Rebuild

From the repository root:

```sh
just build-translator
# Equivalent without just:
zsh games/totk/tools/totk_xlate/publish_native.sh
```

The native executable and its hash are written to
`build-artifacts/translator-offline/native/`. `build_app.py` requires this local
source build and stages a private, verified copy for shader preparation and app
packaging; it never uses `games/totk/prebuilt`. Run this recipe once before
`just build-totk`, and again after changing the translator. It is intentionally
not an automatic dependency of every game build, so unchanged shader caches can
be reused. The packaged Mac helper retains its Homebrew OpenSSL/Brotli runtime
dependencies; it is not a fully static, portable replacement.

`make -C games/totk shader-service` uses the same offline recipe and writes
`games/totk/build/shader-service`. `make shader-tools` builds the managed/JIT
variant through the same locked restore (`--managed`).

The script:

1. Verifies `SHA256SUMS` for every package, lock, toolchain pin and NuGet config.
2. Checks the installed toolchain and copies vendored sources/patches to a fresh
   temporary directory.
3. Uses a **new, empty NuGet package cache** on every build. It does not depend
   on `~/.nuget` or the previous rebuild's cache.
4. Restores with `--locked-mode`, the four checked-in project locks in `locks/`,
   and a local-only `NuGet.Config`/package source. Homebrew SDK-provided packs
   are also local and are part of the pinned toolchain.
5. Publishes with `--no-restore`. IP networking is denied for restore and build
   by `sandbox-exec`; local Unix sockets remain available for MSBuild IPC.

Missing or changed inputs fail the build. NuGet advisory fetching is disabled
for offline builds; that is not a substitute for a separate online dependency
audit. Package integrity is still checked by SHA-256 and NuGet's locked content
hashes. The SDK, NuGet packages, source and compiler remain trusted inputs; this
setup is not a malware audit or a guarantee of byte-identical output.

## Provenance and updates

These archives were copied from the successful source rebuild's NuGet cache.
Most came from `https://api.nuget.org/v3/index.json`; the ILCompiler/ILLink build
packages were supplied by Homebrew's pinned SDK `library-packs`. Each archive
includes its upstream license notices. NuGet's complete resolved dependency
graph and content hashes are in the project locks; `SHA256SUMS` records the exact
archive bytes.

Updating is a deliberate maintenance step: use a separate connected preparation
workspace, regenerate the locks, copy any new `.nupkg` files here, update the
SDK/toolchain pins, and regenerate `SHA256SUMS`. The app build and translator
rebuild do **not** perform this preparation or have an online fallback.

Only the normal app build and the translator targets are covered. Other legacy
research/diagnostic .NET projects in the Makefile are not part of this bundle.
