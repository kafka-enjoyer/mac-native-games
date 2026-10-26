# Offline builds: game dumps in dumps/, work folders in build-artifacts/work/<game>, releases in dist/<game>/<platform>/.
#   just build                    Tears of the Kingdom for the Mac
#   just build totk ios           Tears of the Kingdom IPA (iPhone / iPad)
#   just build totk visionos      Tears of the Kingdom IPA (Vision Pro)
#   just build botw               Breath of the Wild 1.9.0 for the Mac (base + update + both DLC packs)
#   just build odyssey            Super Mario Odyssey 1.4.1 for the Mac (base + update; Mac only)
#   just games                    every game and whether it builds yet (the others print NotYetImplemented)
#   just install "My iPhone"      sign with the dedicated Apple ID (.signing.env) and install
#   just clean / just clean-work  remove releases / work folders (saves and caches in ~/Library are kept)
# Any path below can be overridden: just totk-update=dumps/totk/other.nsp build

# Signing settings for `install` (dedicated signing Apple ID, never a personal one): .signing.env is gitignored,
# copy .signing.env.example to create it.
set dotenv-load
set dotenv-filename := ".signing.env"

python := "python3.14"
dumps := "dumps"
keys := dumps / "keys/prod.keys"
work-root := "build-artifacts/work"
dist := "dist"
translator := "build-artifacts/translator-offline/native"

# Games `build` makes; the rest are recognised but not built yet and print NotYetImplemented:
#   ports merged from upstream, disabled until they build offline (games/<game>/OFFLINE.md): ssbu wonder mvdk ori jamboree,
#   and by3 (Bayonetta 3, built by hand in games/by3); proofs of concept with dumps only: awakening (Link's Awakening,
#   games/awakening on branch awakening-poc), echo (Echoes of Wisdom), sky (Skyward Sword HD).
implemented := "totk botw odyssey"
planned := "ssbu wonder mvdk ori jamboree by3 awakening echo sky"

# Tears of the Kingdom: the card image (its firmware partition provides the shared fonts) and the 1.4.3 update
totk-game := dumps / "totk/totk.xci"
totk-update := dumps / "totk/totk_update_v1.4.3.nsp"

# Breath of the Wild 1.9.0: base card + the 1.9.0 update (version 1114112) + each add-on content pack (optional, but both
# are given here) + an unpacked firmware for the shared fonts (no NSP carries them; unpacked from the zip on first build)
botw-game := dumps / "botw/botw-base-v1.5.0.xci"
botw-update := dumps / "botw/botw-update-v1114112.nsp"
botw-dlc1 := dumps / "botw/botw-dlc-pack1-v196608.nsp"
botw-dlc2 := dumps / "botw/botw-dlc-pack2-v196608.nsp"
firmware-zip := dumps / "firmware/Firmware.23.0.1.zip"
firmware := dumps / "firmware/23.0.1"

# Super Mario Odyssey: base NSP + the 1.4.1 update (version 393216; 1.3.0 works too) + the unpacked firmware for the
# shared fonts. Mac only.
odyssey-game := dumps / "odyssey/odyssey-base-v0.nsp"
odyssey-update := dumps / "odyssey/odyssey-update-v393216.nsp"

# The games in `planned` print NotYetImplemented (just games).
# Build a game: game = totk | botw | odyssey, platform = mac | ios | visionos. iOS / visionOS builds are unsigned IPAs.
build game="totk" platform="mac":
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ " {{planned}} " == *" {{game}} "* ]]; then echo "NotYetImplemented"; exit 0; fi
    resolved=$({{quote(just_executable())}} --justfile {{quote(justfile())}} _resolve {{quote(game)}} {{quote(platform)}})   # fails here on a bad choice
    eval "$resolved"
    for input in "${required[@]}"; do [[ -e "$input" ]] || { echo "missing input: $input" >&2; exit 1; }; done
    if [[ ( {{quote(game)}} == botw || {{quote(game)}} == odyssey ) && ! -d {{quote(firmware)}} ]]; then
        echo "unpacking the firmware for the shared fonts (local, once): {{firmware}}"
        mkdir -p {{quote(firmware)}} && unzip -q {{quote(firmware-zip)}} -d {{quote(firmware)}}
    fi
    mkdir -p "$out_dir" "$work"
    # --no-shader-reminder (iOS / visionOS): no shader_contrib_watch.py LaunchAgent uploading shader lists to GitHub
    {{python}} build_app.py "${inputs[@]}" --keys {{quote(keys)}} --platform "$flag" --work "$work" --out "$out" \
        ${extra[@]+"${extra[@]}"}

# Sign an IPA from `build` with the dedicated signing Apple ID (.signing.env: MNG_SIGNING_TEAM ...) and install it.
install device game="totk" platform="ios":
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ " {{planned}} " == *" {{game}} "* ]]; then echo "NotYetImplemented"; exit 0; fi
    resolved=$({{quote(just_executable())}} --justfile {{quote(justfile())}} _resolve {{quote(game)}} {{quote(platform)}})   # fails here on a bad choice
    eval "$resolved"
    [[ $ext == ipa ]] || { echo "only ios / visionos builds are installed on a device" >&2; exit 2; }
    [[ -f $out ]] || { echo "no build at $out: run just build {{game}} {{platform}}" >&2; exit 1; }
    {{python}} games/totk/ios/tools/install_device.py "$out" --device {{quote(device)}}

# game = all | totk | botw | odyssey (or a planned game: nothing to remove yet), platform = all | mac | ios | visionos
# Remove releases in dist/<game>/<platform> (app / IPA, .signed, partial outputs); saves and caches in ~/Library stay.
clean game="all" platform="all":
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ " {{planned}} " == *" {{game}} "* ]]; then echo "NotYetImplemented"; exit 0; fi
    case {{quote(game)}} in all) games=({{implemented}});; totk|botw|odyssey) games=({{quote(game)}});; *) echo "game: all | {{implemented}} | {{planned}}" >&2; exit 2;; esac
    case {{quote(platform)}} in all) platforms=(mac ios visionos);; mac|ios|visionos) platforms=({{quote(platform)}});; *) echo "platform: all | mac | ios | visionos" >&2; exit 2;; esac
    for g in "${games[@]}"; do for p in "${platforms[@]}"; do
        if [[ -e "{{dist}}/$g/$p" ]]; then rm -rf -- "{{dist}}/$g/$p"; echo "removed {{dist}}/$g/$p"; fi
    done; rmdir "{{dist}}/$g" 2>/dev/null || true; done

# Remove work folders (extracted game data, rewritten code, shader seeds: tens of GB; the next build starts over).
clean-work game="all":
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ " {{planned}} " == *" {{game}} "* ]]; then echo "NotYetImplemented"; exit 0; fi
    case {{quote(game)}} in all) games=({{implemented}});; totk|botw|odyssey) games=({{quote(game)}});; *) echo "game: all | {{implemented}} | {{planned}}" >&2; exit 2;; esac
    for g in "${games[@]}"; do
        if [[ -e "{{work-root}}/$g" ]]; then rm -rf -- "{{work-root}}/$g"; echo "removed {{work-root}}/$g"; fi
    done

# Every game `build` knows: built ones, and the ones that print NotYetImplemented.
games:
    #!/usr/bin/env bash
    printf '%-10s %s\n' totk "Tears of the Kingdom (mac, ios, visionos)" botw "Breath of the Wild 1.9.0 (mac, ios)" \
        odyssey "Super Mario Odyssey 1.4.1 (mac)"
    printf '%-10s %s\n' ssbu "Super Smash Bros. Ultimate: NotYetImplemented (games/ssbu/OFFLINE.md)" \
        wonder "Super Mario Bros. Wonder: NotYetImplemented (games/wonder/OFFLINE.md)" \
        mvdk "Mario vs. Donkey Kong: NotYetImplemented (games/mvdk/OFFLINE.md)" \
        ori "Ori and the Blind Forest: NotYetImplemented (games/ori/OFFLINE.md)" \
        jamboree "Super Mario Party Jamboree: NotYetImplemented (games/jamboree/OFFLINE.md)" \
        by3 "Bayonetta 3: NotYetImplemented (built by hand, games/by3/README.md)" \
        awakening "Link's Awakening: NotYetImplemented (proof of concept, branch awakening-poc)" \
        echo "Echoes of Wisdom: NotYetImplemented (proof of concept, dumps only)" \
        sky "Skyward Sword HD: NotYetImplemented (proof of concept, dumps only)"

# Rebuild the native .NET shader translator (with SPIRV-Cross built in) from source using only local dependencies.
build-translator:
    /bin/zsh games/totk/tools/totk_xlate/publish_native.sh {{quote(translator)}}

# Check the Homebrew libraries the build links against dependencies/homebrew-pins.json.
verify-pins:
    {{python}} tools/homebrew_pins.py verify

# Re-pin Homebrew libraries after reviewing a `brew upgrade` (then review `git diff dependencies/homebrew-pins.json`).
update-pins:
    {{python}} tools/homebrew_pins.py update

# Shell assignments for a game / platform (inputs, output, work folder), shared by build and install.
[private]
_resolve game platform:
    #!/usr/bin/env bash
    set -euo pipefail
    case {{quote(game)}} in
        totk) app="Tears of the Kingdom"
              inputs=({{quote(totk-game)}} --update {{quote(totk-update)}})
              required=({{quote(totk-game)}} {{quote(totk-update)}} {{quote(keys)}});;
        botw) app="Breath of the Wild"
              inputs=({{quote(botw-game)}} --update {{quote(botw-update)}} --dlc {{quote(botw-dlc1)}} --dlc {{quote(botw-dlc2)}} --firmware {{quote(firmware)}})
              required=({{quote(botw-game)}} {{quote(botw-update)}} {{quote(botw-dlc1)}} {{quote(botw-dlc2)}} {{quote(keys)}});;
        odyssey) app="Super Mario Odyssey"
              inputs=({{quote(odyssey-game)}} --update {{quote(odyssey-update)}} --firmware {{quote(firmware)}})
              required=({{quote(odyssey-game)}} {{quote(odyssey-update)}} {{quote(keys)}});;
        *) echo "unknown game {{quote(game)}}: {{implemented}} (not yet: {{planned}})" >&2; exit 2;;
    esac
    if [[ {{quote(game)}} == odyssey && {{quote(platform)}} != mac ]]; then
        echo "Super Mario Odyssey builds for the Mac only" >&2; exit 2
    fi
    case {{quote(platform)}} in
        mac) flag=macos; ext=app; extra=();;
        ios) flag=ios; ext=ipa; extra=(--no-shader-reminder);;
        visionos) [[ {{quote(game)}} == totk ]] || { echo "visionOS builds support Tears of the Kingdom only" >&2; exit 2; }
                  flag=visionos; ext=ipa; extra=(--no-shader-reminder);;
        *) echo "unknown platform {{quote(platform)}}: mac | ios | visionos" >&2; exit 2;;
    esac
    out_dir="{{dist}}/{{game}}/{{platform}}"
    printf 'app=%q flag=%q ext=%q out_dir=%q out=%q work=%q\n' "$app" "$flag" "$ext" "$out_dir" "$out_dir/$app.$ext" "{{work-root}}/{{game}}"
    printf 'inputs=('; printf '%q ' "${inputs[@]}"; printf ')\n'
    printf 'required=('; printf '%q ' "${required[@]}"; printf ')\n'
    printf 'extra=('; for x in ${extra[@]+"${extra[@]}"}; do printf '%q ' "$x"; done; printf ')\n'
