#!/usr/bin/env python3
"""Sign the unsigned TOTK (or Breath of the Wild) IPA with a DEDICATED signing Apple ID and install it on a connected iPhone / iPad.

A free (Personal Team) Apple ID signs for 7 days, a paid membership for a year: run this again to renew. Reinstalling
with the same team and bundle identifier keeps the saves and the shader cache (they are in the app's Documents).

  python3 games/totk/ios/tools/install_device.py "Tears of the Kingdom.ipa" --device "Jack iPhone"

An IPA built with --ios-game-data documents carries no 17 GB game image: pass --game-data <work>/totk/extracted/v143/
romfs/romfs.bin and it is copied once into the app's Documents/GameData in 1 GiB parts (devicectl drops the connection on
one file that size); a later install skips it while the device holds the same image (romfs.sha256 there).

Dedicated signer (never a personal Apple ID): signing happens only for the team named by --team / MNG_SIGNING_TEAM, a
separate Apple ID created just for signing these IPAs. There is no "pick the only certificate" default any more.
  MNG_SIGNING_TEAM             team ID of the dedicated signing Apple ID (required)
  MNG_SIGNING_FORBIDDEN_TEAMS  comma-separated team IDs that must never sign (e.g. your personal Apple ID's team)
  MNG_SIGNING_KEY_PATH / MNG_SIGNING_KEY_ID / MNG_SIGNING_ISSUER_ID
                               optional App Store Connect API key of the dedicated (paid) account: xcodebuild then
                               authenticates with this key instead of any Apple ID signed in to Xcode
Without an API key, add the dedicated Apple ID in Xcode > Settings > Accounts; Xcode provisions with the account that owns
the pinned team. The provisioning profile and the signing certificate are both checked to belong to the pinned team
before anything is signed. `just install-totk-ios` reads these from .signing.env (gitignored; see .signing.env.example).
The provisioning profile comes from a throwaway Xcode project built with the same bundle identifier and entitlements
(-allowProvisioningUpdates registers the device and the App ID).
"""
import argparse, time, hashlib, json, os, plistlib, re, shutil, subprocess, sys, tempfile, zipfile
from datetime import timezone
from pathlib import Path

ENTITLEMENT = 'com.apple.developer.kernel.increased-memory-limit'
CACHE = Path.home()/'Library/Caches/MacNativeGames/ios-signing'

def run(cmd, **kw): return subprocess.run([str(x) for x in cmd], check=True, **kw)
def out(cmd): return subprocess.run([str(x) for x in cmd], check=True, capture_output=True, text=True).stdout

def teams():
    pems = out(['security','find-certificate','-a','-c','Apple Development','-p'])
    found = set()
    for pem in re.findall(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', pems, re.S):
        subject = subprocess.run(['openssl','x509','-noout','-subject'], input=pem, capture_output=True, text=True).stdout
        if m := re.search(r'OU\s*=\s*([A-Z0-9]{10})', subject): found.add(m.group(1))
    return sorted(found)

def devices():
    with tempfile.NamedTemporaryFile(suffix='.json') as f:
        run(['xcrun','devicectl','list','devices','--json-output',f.name], capture_output=True)
        return [d for d in json.load(open(f.name))['result']['devices']
                if d.get('hardwareProperties',{}).get('platform') == 'iOS']

def pick_device(name):
    devs = devices()
    match = [d for d in devs if name in (d['deviceProperties'].get('name'), d['identifier'], d['hardwareProperties'].get('udid'))] if name else devs
    if len(match) != 1:
        listed = '\n'.join(f"  {d['deviceProperties'].get('name')} ({d['hardwareProperties'].get('marketingName')})" for d in devs)
        sys.exit(f"choose the device with --device <name>:\n{listed}" if devs else 'no paired iPhone / iPad found: connect it with a cable and trust this Mac')
    return match[0]

def team_of_identity(signed_app):
    """The team (certificate OU) of the identity Xcode signed the throwaway app with."""
    with tempfile.TemporaryDirectory() as d:
        run(['codesign','-d','--extract-certificates='+d+'/cert','-v',signed_app], capture_output=True)
        subject = out(['openssl','x509','-inform','DER','-in',d+'/cert0','-noout','-subject'])
    m = re.search(r'OU\s*=\s*([A-Z0-9]{10})', subject)
    return m.group(1) if m else None

def api_key_args():
    """xcodebuild -authenticationKey* for the dedicated account's App Store Connect API key, or [] when none is set."""
    keys = {k: os.environ.get(k, '').strip() for k in ('MNG_SIGNING_KEY_PATH','MNG_SIGNING_KEY_ID','MNG_SIGNING_ISSUER_ID')}
    if not any(keys.values()): return []
    if not all(keys.values()): sys.exit('set all three of MNG_SIGNING_KEY_PATH, MNG_SIGNING_KEY_ID and MNG_SIGNING_ISSUER_ID, or none')
    path = Path(keys['MNG_SIGNING_KEY_PATH']).expanduser()
    if not path.is_file(): sys.exit(f'MNG_SIGNING_KEY_PATH: no such file {path}')
    return ['-authenticationKeyPath',str(path),'-authenticationKeyID',keys['MNG_SIGNING_KEY_ID'],
            '-authenticationKeyIssuerID',keys['MNG_SIGNING_ISSUER_ID']]

def signing_team(arg):
    """The dedicated signing team: explicit only, never guessed, never a forbidden (personal) team."""
    team = (arg or os.environ.get('MNG_SIGNING_TEAM', '')).strip().upper()
    if not team:
        found = teams()
        sys.exit('no signing team given: set MNG_SIGNING_TEAM (or --team) to the team ID of the dedicated signing Apple ID. '
                 'This script no longer picks a certificate on its own, so a personal Apple ID is never used by accident.'
                 + (f' Teams with an Apple Development certificate in this keychain: {", ".join(found)}' if found else ''))
    if not re.fullmatch(r'[A-Z0-9]{10}', team): sys.exit(f'not a team ID: {team!r}')
    forbidden = {t.strip().upper() for t in os.environ.get('MNG_SIGNING_FORBIDDEN_TEAMS', '').split(',') if t.strip()}
    if team in forbidden: sys.exit(f'team {team} is listed in MNG_SIGNING_FORBIDDEN_TEAMS: refusing to sign with it')
    return team

def profile(team, bundle_id, udid):
    """Build an empty app with the game's bundle identifier and entitlements; Xcode makes the profile for it."""
    proj = CACHE/bundle_id; proj.mkdir(parents=True, exist_ok=True)
    (proj/'main.m').write_text('int main(void) { return 0; }\n')
    (proj/'TOTK.entitlements').write_bytes(plistlib.dumps({ENTITLEMENT: True}))
    (proj/'project.yml').write_text(f'''name: TOTKSigning
options: {{deploymentTarget: {{iOS: "26.0"}}}}
targets:
  TOTK:
    type: application
    platform: iOS
    sources: [main.m]
    settings:
      GENERATE_INFOPLIST_FILE: YES
      PRODUCT_BUNDLE_IDENTIFIER: {bundle_id}
      DEVELOPMENT_TEAM: {team}
      CODE_SIGN_STYLE: Automatic
      CODE_SIGN_ENTITLEMENTS: TOTK.entitlements
''')
    run(['xcodegen','generate','--quiet'], cwd=proj)
    derived = proj/'derived'
    log = proj/'xcodebuild.log'
    with log.open('w') as f:
        r = subprocess.run(['xcodebuild','-project','TOTKSigning.xcodeproj','-scheme','TOTK','-configuration','Debug',
                            '-destination',f'id={udid}','-derivedDataPath',str(derived),
                            '-allowProvisioningUpdates','-allowProvisioningDeviceRegistration',*api_key_args(),'build'],
                           cwd=proj, stdout=f, stderr=subprocess.STDOUT)
    if r.returncode:
        errors = [l for l in log.read_text(errors='replace').splitlines() if 'error:' in l]
        sys.exit('Xcode could not make a provisioning profile:\n' + '\n'.join(errors[-8:]) + f'\nfull log: {log}')
    app = derived/'Build/Products/Debug-iphoneos/TOTK.app'
    return app/'embedded.mobileprovision', app

def identity_of(signed_app):
    """The SHA-1 of the certificate Xcode signed the empty app with: the same identity signs the game."""
    with tempfile.TemporaryDirectory() as d:
        run(['codesign','-d','--extract-certificates='+d+'/cert','-v',signed_app], capture_output=True)
        der = Path(d+'/cert0').read_bytes()
    return hashlib.sha1(der).hexdigest().upper()

PART = 1 << 30
def device_files(dev, bundle_id, sub):
    """{name: size} of the app's Documents/<sub> on the device, {} when there is none. A device that cannot be reached is
    an error, not "nothing there": taken as empty, an install began copying the 16 GiB again and marked the copy on the
    device stale before failing (2026-10-23, the phone had locked)."""
    with tempfile.NamedTemporaryFile(suffix='.json') as f:
        r = subprocess.run(['xcrun','devicectl','device','info','files','--device',dev,'--domain-type','appDataContainer',
                            '--domain-identifier',bundle_id,'--subdirectory',sub,'--json-output',f.name], capture_output=True)
        if r.returncode:
            if sub != 'Documents' and device_files(dev, bundle_id, 'Documents') is not None: return {}   # reachable: the folder is not there yet
            sys.exit(f'cannot read Documents/{sub} on the device (is it connected by cable and unlocked?): {r.stderr.decode(errors="replace").strip()[-300:]}')
        files = json.load(open(f.name)).get('result', {}).get('files', [])
    return {Path(x.get('relativePath', x.get('name', ''))).name: x.get('metadata', {}).get('size', 0) for x in files}   # devicectl's JSON

def push_game_data(dev, bundle_id, image):
    """The RomFS image into Documents/GameData as romfs.bin.000, .001, ... (ios/Sources/main.m reads it there), then
    romfs.sha256 naming it, so the next install skips it. While copying, the marker says "copying <sha256>": a copy that
    stopped (the cable, a locked phone) goes on from the parts of that image already there at their full size."""
    sha = json.loads((image.parent/'index.json').read_text())['romfs_sha256']
    size = image.stat().st_size; parts = (size + PART - 1) // PART
    have = device_files(dev, bundle_id, 'Documents/GameData')
    if have.get('romfs.sha256') == 64 + 1 and all(f'romfs.bin.{i:03d}' in have for i in range(parts)):
        with tempfile.TemporaryDirectory() as d:
            got = Path(d)/'romfs.sha256'
            r = subprocess.run(['xcrun','devicectl','device','copy','from','--device',dev,'--domain-type','appDataContainer',
                                '--domain-identifier',bundle_id,'--source','Documents/GameData/romfs.sha256','--destination',got], capture_output=True)
            if r.returncode == 0 and got.read_text().strip() == sha:
                print('game data: the device already has this image'); return
    # every part there at its full size but the marker not (an install stopped between writing "stale" and the first part):
    # the parts are this image, only the marker is written again
    if all(have.get(f'romfs.bin.{i:03d}') == min(PART, size - i * PART) for i in range(parts)) and have.get('romfs.sha256') != 64 + 1:
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'romfs.sha256').write_text(sha + '\n')
            run(['xcrun','devicectl','device','copy','to','--device',dev,'--domain-type','appDataContainer','--domain-identifier',
                 bundle_id,'--source',Path(d)/'romfs.sha256','--destination','Documents/GameData/romfs.sha256'], capture_output=True)
        print('game data: every part is on the device; only its marker was written again'); return
    copying = f'copying {sha}'
    resume = False
    if have.get('romfs.sha256') == len(copying) + 1:
        with tempfile.TemporaryDirectory() as d:
            got = Path(d)/'romfs.sha256'
            r = subprocess.run(['xcrun','devicectl','device','copy','from','--device',dev,'--domain-type','appDataContainer',
                                '--domain-identifier',bundle_id,'--source','Documents/GameData/romfs.sha256','--destination',got], capture_output=True)
            resume = r.returncode == 0 and got.read_text().strip() == copying
    print(f'game data: copying {size / 2**30:.1f} GiB in {parts} parts (once; later installs keep it)' +
          (', going on from the parts already there' if resume else ''), flush=True)
    with tempfile.TemporaryDirectory() as d, open(image, 'rb') as src:
        def copy(local, name):
            for attempt in range(3):
                r = subprocess.run(['xcrun','devicectl','device','copy','to','--device',dev,'--domain-type','appDataContainer',
                                    '--domain-identifier',bundle_id,'--source',str(local),'--destination',f'Documents/GameData/{name}'],
                                   capture_output=True, text=True)
                if r.returncode == 0: return
                print(f'  {name}: copy failed (attempt {attempt + 1} of 3): {(r.stderr or r.stdout).strip().splitlines()[-1:]}', flush=True)
                time.sleep(10)
            sys.exit(f'game data: {name} could not be copied (keep the device unlocked and connected); run this again to go on from there')
        if not resume: (Path(d)/'romfs.sha256').write_text(copying + '\n'); copy(Path(d)/'romfs.sha256', 'romfs.sha256')   # until every part is there
        for i in range(parts):
            part = Path(d)/f'romfs.bin.{i:03d}'
            if resume and have.get(part.name) == min(PART, size - i * PART):
                src.seek(min(PART, size - i * PART), os.SEEK_CUR); print(f'  part {i + 1}/{parts}: already there', flush=True); continue
            part.write_bytes(src.read(PART)); copy(part, part.name); part.unlink()
            print(f'  part {i + 1}/{parts}', flush=True)
        (Path(d)/'romfs.sha256').write_text(sha + '\n'); copy(Path(d)/'romfs.sha256', 'romfs.sha256')

def write_pack(seed, names, d, folder, size, done):
    """The files `names` of `seed` as one stream (ios/Sources/main.m seed_unpack: "TOTKPACK1", then per file a u16 name
    length, the name, a u64 size and the bytes, a zero name length last) in parts of `size` bytes, d/<folder>.pack.NNN;
    done(path) is called with each part once it is complete."""
    part, out, n = 0, None, 0
    def roll():
        nonlocal part, out, n
        if out:
            out.close(); done(d/f'{folder}.pack.{part:03d}'); part += 1
        out = open(d/f'{folder}.pack.{part:03d}', 'wb'); n = 0
    def write(b):
        nonlocal n
        while b:
            if n >= size: roll()
            k = min(len(b), size - n); out.write(b[:k]); n += k; b = b[k:]
    roll(); write(b'TOTKPACK1')
    for name in names:
        raw = name.encode()
        write(len(raw).to_bytes(2, 'little') + raw + (seed/name).stat().st_size.to_bytes(8, 'little'))
        write((seed/name).read_bytes())
    write((0).to_bytes(2, 'little'))
    out.close(); done(d/f'{folder}.pack.{part:03d}')

def push_seed(dev, bundle_id, seed):
    """The startup shaders of an app built with --ios-game-data documents (<app>-shader-seed beside it) into Documents/
    GameData as one stream in 1 GiB parts (<folder>.pack.000, ...), then shader-seed.txt naming the folder; the app unpacks
    them on its next start (ios/Sources/main.m seed_unpack). devicectl copying the folder itself stopped after ~25,000 of
    its 128,000 files over the cable (2026-10-23). Skipped while the device has this content (fingerprint.txt)."""
    fp = (seed/'fingerprint.txt').read_text().strip()
    with tempfile.TemporaryDirectory(dir=seed.parent) as d:   # beside the seed: 1 GiB parts, not on the system disk
        got = Path(d)/'shader-seed.txt'
        r = subprocess.run(['xcrun','devicectl','device','copy','from','--device',dev,'--domain-type','appDataContainer',
                            '--domain-identifier',bundle_id,'--source','Documents/GameData/shader-seed.txt','--destination',got], capture_output=True)
        lines = got.read_text().split('\n') if r.returncode == 0 and got.is_file() else []
        have = device_files(dev, bundle_id, 'Documents/GameData')
        if len(lines) >= 2 and lines[1].strip() == fp and (lines[0] in have or f'{lines[0]}.pack.000' in have):
            print('shaders: the device already has these'); return
        folder = f'shader-seed-{fp[:12]}-{int(time.time())}'
        names = sorted(p.name for p in seed.iterdir() if p.is_file())
        total = sum((seed/n).stat().st_size for n in names)
        print(f'shaders: copying {len(names)} files, {total / 2**30:.1f} GiB, as one pack (once per shader list; later installs keep them)')
        def copy(local, name):
            run(['xcrun','devicectl','device','copy','to','--device',dev,'--domain-type','appDataContainer','--domain-identifier',
                 bundle_id,'--source',local,'--destination',f'Documents/GameData/{name}'], capture_output=True)
        got.write_text('stale\n'); copy(got, 'shader-seed.txt')   # until every part is there
        def push(local):
            copy(local, local.name); local.unlink(); print(f'  {local.name}', flush=True)
        write_pack(seed, names, Path(d), folder, PART, push)
        got.write_text(f'{folder}\n{fp}\n'); copy(got, 'shader-seed.txt')

def built_bundle_id(ipa, team):
    """The identifier build_app.py gave the app (org.macnativegames.totk, or .botw for Breath of the Wild); a .app folder
    signed before carries it with the team suffix this script added."""
    try:
        if ipa.is_dir(): raw = (ipa/'Info.plist').read_bytes()
        else:
            with zipfile.ZipFile(ipa) as z: raw = z.read('Payload/TOTK.app/Info.plist')
        bid = plistlib.loads(raw).get('CFBundleIdentifier', '')
    except (OSError, KeyError, zipfile.BadZipFile, plistlib.InvalidFileException): bid = ''
    bid = bid.removesuffix('.' + team.lower())
    return bid if bid.startswith(('org.macnativegames.', 'org.mng.')) else 'org.macnativegames.totk'

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('ipa', type=Path, help='the unsigned IPA (or .app folder) from build_app.py --platform ios')
    ap.add_argument('--device', help='device name (as in Finder) or identifier; needed when several are paired')
    ap.add_argument('--team', help='team ID of the dedicated signing Apple ID (default: $MNG_SIGNING_TEAM; required)')
    ap.add_argument('--bundle-id', help='default: the build\'s identifier (org.macnativegames.totk or .botw) + .<team>, so it is free to register on your team')
    ap.add_argument('--game-data', type=Path, help='romfs.bin (index.json beside it) for an IPA built with --ios-game-data documents')
    a = ap.parse_args()
    team = signing_team(a.team)
    bundle_id = a.bundle_id or f'{built_bundle_id(a.ipa, team)}.{team.lower()}'
    dev = pick_device(a.device)
    udid = dev['hardwareProperties']['udid']
    print(f"team {team}, bundle {bundle_id}, device {dev['deviceProperties'].get('name')} ({udid})")

    print('provisioning profile: asking Xcode')
    prov, signed = profile(team, bundle_id, udid)
    info = plistlib.loads(out(['security','cms','-D','-i',prov]).encode())
    ents = info['Entitlements']
    if team not in info.get('TeamIdentifier', []) or team_of_identity(signed) != team:
        sys.exit(f'Xcode provisioned or signed with a team other than the dedicated {team} '
                 f'(profile {info.get("TeamIdentifier")}, certificate {team_of_identity(signed)}): refusing to sign')
    if not ents.get(ENTITLEMENT):
        print(f'warning: your team cannot grant {ENTITLEMENT}; iOS may close the game when it runs out of memory')
    expires = info['ExpirationDate'].replace(tzinfo=timezone.utc).astimezone()  # plistlib returns naive UTC
    print(f"provisioning profile valid until {expires:%Y-%m-%d %H:%M} local time (run this again before then)")

    # Unpack once per IPA; later runs only re-sign. 16 GiB of game data is signed in place.
    work = a.ipa.with_suffix('.signed'); stamp = work/'.ipa-mtime'
    app = work/'Payload/TOTK.app'
    if a.ipa.is_dir():   # an unsigned .app (build_app.py -o X.app): signed where it is, a build's own output (no copy)
        app = a.ipa.resolve(); work.mkdir(exist_ok=True)
    elif not stamp.is_file() or stamp.read_text() != str(a.ipa.stat().st_mtime_ns):
        print(f'unpacking {a.ipa.name}')
        shutil.rmtree(work, ignore_errors=True); work.mkdir()
        run(['ditto','-x','-k',a.ipa,work])
        stamp.write_text(str(a.ipa.stat().st_mtime_ns))
    plist = app/'Info.plist'
    infoplist = plistlib.loads(plist.read_bytes()); infoplist['CFBundleIdentifier'] = bundle_id
    plist.write_bytes(plistlib.dumps(infoplist, fmt=plistlib.FMT_BINARY))
    shutil.copy2(prov, app/'embedded.mobileprovision')
    entfile = work/'entitlements.plist'
    entfile.write_bytes(plistlib.dumps({k: ents[k] for k in ('application-identifier','com.apple.developer.team-identifier',
                                                                'get-task-allow', ENTITLEMENT) if k in ents}))
    print('signing (a few minutes: every game file is hashed)')
    run(['codesign','--force','--sign',identity_of(signed),'--entitlements',entfile,'--generate-entitlement-der',app])
    print('installing (a few minutes over the cable)')
    run(['xcrun','devicectl','device','install','app','--device',dev['identifier'],app])
    if a.game_data: push_game_data(dev['identifier'], bundle_id, a.game_data)
    seed = a.ipa.with_name(a.ipa.stem + '-shader-seed')   # build_ipa.py --image-outside
    if a.ipa.is_dir() and not (app/'GameData/shader-seed').is_dir() and (seed/'fingerprint.txt').is_file():
        push_seed(dev['identifier'], bundle_id, seed)
    print('installed. First time on this device: Settings > General > VPN & Device Management > trust your Apple ID.')

if __name__ == '__main__': main()
