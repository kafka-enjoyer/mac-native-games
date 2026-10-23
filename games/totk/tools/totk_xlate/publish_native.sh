#!/bin/zsh
# Rebuild from vendored NuGet packages using the pinned Homebrew/Xcode toolchain.
# No dependency downloads: restore uses only local feeds and publishing uses --no-restore.
# SPIRV-Cross is compiled in (spirv_cross_inproc.cpp: its own main.cpp's compile_iteration), so the service needs no
# process per shader. Its sources are the hash-verified local snapshot dependencies/sources/SPIRV-Cross (the pinned
# commit in dependencies/manifest.json), with the sources and flags build_app.py builds the spirv-cross program from.
# Usage: publish_native.sh [--managed] [output-directory]
# Default output: build-artifacts/translator-offline/native (native executable + SHA-256).
set -euo pipefail
HERE=${0:A:h}
REPO=${HERE:h:h:h:h}
DEPS="$REPO/dependencies/dotnet"
MANAGED=0
if [[ "${1:-}" == --managed ]]; then MANAGED=1; shift; fi
if (( $# > 1 )); then echo 'usage: publish_native.sh [--managed] [output-directory]' >&2; exit 2; fi
OUT=${1:-$REPO/build-artifacts/translator-offline/native}
OUT=${OUT:A}
if [[ ! -f "$DEPS/SHA256SUMS" ]]; then
  echo 'Missing dependencies/dotnet bundle; restore it before building (no download fallback).' >&2
  exit 1
fi
(cd "$DEPS" && shasum --quiet -a 256 -c SHA256SUMS)
export HOMEBREW_NO_AUTO_UPDATE=1 HOMEBREW_NO_ANALYTICS=1
command -v brew >/dev/null || { echo 'Homebrew is required; see dependencies/dotnet/README.md' >&2; exit 1; }
WORK=$(mktemp -d -t totk-xlate)
trap 'rm -rf "$WORK"' EXIT INT TERM HUP
{
  for formula in dotnet openssl@4 brotli; do brew list --versions "$formula"; done
  xcodebuild -version
  xcrun clang --version | head -n 1
} > "$WORK/toolchain.txt"
if ! cmp -s "$DEPS/toolchain.txt" "$WORK/toolchain.txt"; then
  echo 'Toolchain differs from dependencies/dotnet/toolchain.txt. Restore the pinned versions or explicitly update the pin.' >&2
  diff -u "$DEPS/toolchain.txt" "$WORK/toolchain.txt" >&2 || true
  exit 1
fi
# Versions alone are not enough: the translator links (and later loads) these Homebrew dylibs, so their hashes are pinned
# in dependencies/homebrew-pins.json too (tools/homebrew_pins.py; dependency-injection guard).
python3.14 "$REPO/tools/homebrew_pins.py" verify translator
export DOTNET_ROOT="$(brew --prefix dotnet)/libexec"
export DOTNET_CLI_HOME="$WORK/home" NUGET_PACKAGES="$WORK/packages"
export NUGET_HTTP_CACHE_PATH="$WORK/http-cache" NUGET_PLUGINS_CACHE_PATH="$WORK/plugin-cache"
export DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_GENERATE_ASPNET_CERTIFICATE=false DOTNET_NOLOGO=1
export DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE=true DOTNET_CLI_DO_NOT_USE_MSBUILD_SERVER=1
export MSBuildEnableWorkloadResolver=false NUGET_CERT_REVOCATION_MODE=offline
export LIBRARY_PATH="$(brew --prefix openssl@4)/lib:$(brew --prefix brotli)/lib"
# Deny IP networking in both restore and compilation; allow local Unix sockets
# used by MSBuild. Package sources are still restricted to the vendored feed.
RUN_DOTNET=(/usr/bin/sandbox-exec -p '(version 1) (allow default) (deny network*) (allow network* (local unix-socket))' "$DOTNET_ROOT/dotnet")
cp "$DEPS/global.json" "$WORK/global.json"
mkdir -p "$WORK/ryujinx-src" "$WORK/xlate"
cp -R "$REPO/vendor/ryujinx/." "$WORK/ryujinx-src/"
find "$WORK/ryujinx-src/src" -maxdepth 2 \( -name obj -o -name bin \) -type d -exec rm -rf {} +
for p in "$HERE"/patches/*.patch; do patch -s -d "$WORK/ryujinx-src" -p1 --forward < "$p"; done
cp "$HERE"/*.cs "$HERE/totk_xlate.csproj" "$WORK/xlate/"
cp -R "$DEPS/locks/." "$WORK/"
# SPIRV-Cross for the in-process library: verify every file of the local snapshot against dependencies/manifest.json and
# copy it into the work folder (build_app.local_source: the same check the app build uses; never fetched). The upstream
# git fetch and its unverified SPIRV_CROSS_SRC override are deliberately not used.
SPVC_SRC="$WORK/spirv-cross-src"
(cd "$REPO" && python3.14 -c 'import sys, build_app; from pathlib import Path; build_app.local_source("SPIRV-Cross", Path(sys.argv[1]), Path(sys.argv[2]))' \
  "$SPVC_SRC" "$WORK/spirv-cross-copy.log")
SOURCES=(${(f)"$(cd "$REPO" && python3.14 -c 'import build_app; print("\n".join(s for s in build_app.SPIRV_CROSS_SOURCES if s != "main.cpp"))')"})
FLAGS=(${(f)"$(cd "$REPO" && python3.14 -c 'import build_app; print("\n".join(build_app.SPIRV_CROSS_FLAGS))')"})
FLAGS+=(-mmacosx-version-min=12.0)   # as the NativeAOT link of the service (otherwise every object warns and may need a newer macOS)
NO_NET=(/usr/bin/sandbox-exec -p '(version 1) (allow default) (deny network*) (allow network* (local unix-socket))')
mkdir -p "$WORK/spvc"
for f in "${SOURCES[@]}"; do "${NO_NET[@]}" xcrun clang++ "${FLAGS[@]}" -c "$SPVC_SRC/$f" -o "$WORK/spvc/${f%.cpp}.o" & done
"${NO_NET[@]}" xcrun clang++ "${FLAGS[@]}" -I"$SPVC_SRC" -c "$HERE/spirv_cross_inproc.cpp" -o "$WORK/spvc/spirv_cross_inproc.o" &   # includes main.cpp
wait
for f in "${SOURCES[@]}" spirv_cross_inproc.cpp; do [[ -f "$WORK/spvc/${f%.cpp}.o" ]] || { echo "SPIRV-Cross: $f did not compile" >&2; exit 1; }; done
"${NO_NET[@]}" xcrun ar rcs "$WORK/libtotk_spirv_cross.a" "$WORK"/spvc/*.o
cd "$WORK"
echo "Building with local .NET SDK $("${RUN_DOTNET[@]}" --version); empty package cache, no network."
PROPERTIES=(-p:PublishAot=true -p:InvariantGlobalization=true -p:RuntimeFrameworkVersion=10.0.13
  "-p:RyuSrc=$WORK/ryujinx-src" -p:UseSharedCompilation=false -p:NuGetAudit=false -m:1 -nr:false)
# NativeAOT links the SPIRV-Cross library in; the managed build (--managed) cannot, so it runs the spirv-cross program
# per shader instead (set TOTK_XLATE_SPIRV_CROSS=process when using it).
(( MANAGED )) || PROPERTIES+=("-p:TotkSpirvCrossLib=$WORK/libtotk_spirv_cross.a")
PROJECT="$WORK/xlate/totk_xlate.csproj"
"${RUN_DOTNET[@]}" restore "$PROJECT" --configfile "$DEPS/NuGet.Config" --source "$DEPS/packages" \
  --packages "$WORK/packages" --locked-mode --disable-parallel --runtime osx-arm64 "${PROPERTIES[@]}"
mkdir -p "$OUT"
if (( MANAGED )); then
  "${RUN_DOTNET[@]}" build "$PROJECT" --no-restore -c Release -r osx-arm64 "${PROPERTIES[@]}" -o "$WORK/out"
  cp -R "$WORK/out/." "$OUT/"
  echo "built managed translator in $OUT"
else
  "${RUN_DOTNET[@]}" publish "$PROJECT" --no-restore -c Release -r osx-arm64 "${PROPERTIES[@]}" -o "$WORK/out"
  codesign --verify --strict "$WORK/out/totk_xlate"
  cp "$WORK/out/totk_xlate" "$OUT/totk_xlate"
  shasum -a 256 "$OUT/totk_xlate" | awk '{print $1}' > "$OUT/totk_xlate.sha256"
  echo "built $OUT/totk_xlate"
  shasum -a 256 "$OUT/totk_xlate"
fi
