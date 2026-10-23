# Signing settings for install-totk-ios (dedicated signing Apple ID, never a personal one): .signing.env is gitignored,
# copy .signing.env.example to create it.
set dotenv-load
set dotenv-filename := ".signing.env"

path-totk := "./dumps/totk/totk.xci"
path-totk-update := "./dumps/totk/totk_update_v1.4.3.nsp"
path-prod-key := "./dumps/keys/prod.keys"
path-translator := "./build-artifacts/translator-offline/native"
path-totk-output := "./dist/totk-app/Tears of the Kingdom"

build-totk:
    python3.15 build_app.py "{{path-totk}}" --keys "{{path-prod-key}}" --update "{{path-totk-update}}" --output "{{path-totk-output}}.app"

# --no-shader-reminder: do not install shader_contrib_watch.py (a LaunchAgent that uploads shader lists to GitHub via gh).
built-totk-ios:
    python3.15 build_app.py "{{path-totk}}" --keys "{{path-prod-key}}" --update "{{path-totk-update}}" --platform "ios" --output "{{path-totk-output}}.ipa" --no-shader-reminder

# Sign the IPA with the dedicated signing Apple ID from .signing.env (MNG_SIGNING_TEAM ...) and install it on a device.
install-totk-ios device:
    python3.14 games/totk/ios/tools/install_device.py "{{path-totk-output}}.ipa" --device "{{device}}"

# Check the Homebrew libraries the build links against dependencies/homebrew-pins.json.
verify-pins:
    python3.14 tools/homebrew_pins.py verify

# Re-pin Homebrew libraries after reviewing a `brew upgrade` (then review `git diff dependencies/homebrew-pins.json`).
update-pins:
    python3.14 tools/homebrew_pins.py update

# Rebuild the native .NET shader translator from source using only local dependencies.
build-translator:
    /bin/zsh games/totk/tools/totk_xlate/publish_native.sh "{{path-translator}}"

# Remove packaged app/IPA outputs only; quit the game first. Keep inputs, caches and saves.
clean-totk:
    rm -rf -- "{{path-totk-output}}.app" "{{path-totk-output}}.app.partial"
    rm -f -- "{{path-totk-output}}.ipa"
