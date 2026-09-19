# FamilyDash iOS App

A native iOS shell (via [Capacitor](https://capacitorjs.com)) around the same
management UI the Raspberry Pi serves at `/mobile`. There is **one** copy of the
UI — `frontend/mobile.html` — and `npm run build` bundles it into the app, so
anything you change for the web version ships in the app too.

On first launch the app asks for the Pi's address (e.g. `192.168.1.50:5000` or
`raspberrypi.local:5000`), verifies it against `/api/health`, and remembers it.
The ⚙️ button in the header changes it later. Typing **`demo`** instead runs the app on
built-in sample data with no server — used for App Store screenshots and App Review.

**Submitting to Apple?** Everything App Store Connect asks for is pre-written in
[`docs/APP_STORE_SUBMISSION.md`](../docs/APP_STORE_SUBMISSION.md), and
[`docs/MAC_HANDOFF_PROMPT.md`](../docs/MAC_HANDOFF_PROMPT.md) is a paste-ready prompt for a
Claude Code session on the Mac that does the whole build/sign/upload.

## Layout

```
app/
├── capacitor.config.json   # app id, name, iOS options
├── package.json            # Capacitor deps + scripts
├── ExportOptions.plist     # for xcodebuild -exportArchive (App Store Connect upload)
├── scripts/
│   ├── build.js            # frontend/mobile.html -> www/index.html  (--demo for screenshots)
│   ├── screenshots.sh      # captures App Store screenshots from the simulator (macOS)
│   └── make_icons.py       # regenerates resources/* and frontend/icons/*
├── resources/              # 1024px icon + 2732px splash (source images)
├── www/                    # generated - do not edit (git-ignored)
└── ios/                    # Xcode project (committed)
    └── App/
        ├── App.xcworkspace # <- open THIS in Xcode, not App.xcodeproj
        ├── App/Info.plist  # local-network permissions live here
        └── Podfile
```

## Everything that runs on any OS

```bash
cd app
npm install                 # once
npm run build               # bundle the web UI into www/
npm run build:demo          # same, but the app opens in demo mode (screenshots only - never ship)
npm run assets              # regenerate iOS icons/splash from resources/ (only after changing them)
python scripts/make_icons.py   # regenerate resources/ + PWA icons from code
```

## The Mac part (one-time setup, ~10 minutes)

You need a Mac with **Xcode** (App Store) and **CocoaPods**:

```bash
sudo gem install cocoapods      # or: brew install cocoapods
```

Then:

```bash
git clone https://github.com/CyberSlimer/FamilyDash.git
cd FamilyDash/app
npm install
npm run ios                     # = build + cap sync ios (runs pod install) + open Xcode
```

In Xcode:

1. Select the **App** target → **Signing & Capabilities** → tick *Automatically manage signing* and choose your **Team** (your Apple developer account).
2. If Xcode complains the bundle id is taken, change it in the same pane (and in `capacitor.config.json` → `appId` to keep them in sync). Default is `com.cyberslimer.familydash`.
3. Plug in your iPhone (or pick a simulator), press **▶ Run**.
4. First run on a device: on the phone go to *Settings → General → VPN & Device Management* and trust your developer certificate.

The first time the app talks to the Pi, iOS asks *"FamilyDash would like to find and connect to devices on your local network"* — tap **Allow**. (That prompt comes from `NSLocalNetworkUsageDescription` in `Info.plist`; the `NSAppTransportSecurity` entry there is what permits plain `http://` to the Pi.)

After pod install succeeds, commit `ios/App/Podfile.lock` so builds are reproducible.
(Done 2026-09-18 with Xcode 26.6 / CocoaPods 1.16.2 via Homebrew — CocoaPods wants
`export LANG=en_US.UTF-8` in the shell.)

## App Store screenshots

```bash
npm run screenshots         # macOS: builds demo mode, boots simulators, saves app/screenshots/<device>/*.png
```

A full set (iPhone 16 Pro Max 1320×2868 and iPad Pro 13-inch M4 2064×2752, one per tab) is
committed under `screenshots/`; re-run only after a visible UI change.

## Shipping to the family (TestFlight)

1. In Xcode: **Product → Archive**, then **Distribute App → TestFlight & App Store**.
2. In [App Store Connect](https://appstoreconnect.apple.com) → your app → **TestFlight** → add family members as internal testers (up to 100, no review needed).
3. They install the TestFlight app, accept the invite, and get updates automatically.

Bump `MARKETING_VERSION` / `CURRENT_PROJECT_VERSION` in Xcode (or `agvtool`) before each new archive.

## Day-to-day after setup

Whenever `frontend/mobile.html` changes:

```bash
cd app && npm run sync          # rebuild www/ and copy into the Xcode project
```

then Run/Archive from Xcode as usual. Nothing in `ios/` needs hand-editing for UI changes.

To push a new build to TestFlight from the command line instead (what each build so far has
used), bump `CURRENT_PROJECT_VERSION` in `ios/App/App.xcodeproj/project.pbxproj` (two
occurrences, Debug and Release), then:

```bash
cd app/ios/App
xcodebuild -workspace App.xcworkspace -scheme App -configuration Release \
  -destination 'generic/platform=iOS' -archivePath ../../build/FamilyDash.xcarchive \
  -allowProvisioningUpdates archive
cp ../../ExportOptions.plist /tmp/ExportOptions-upload.plist
/usr/libexec/PlistBuddy -c 'Set :destination upload' /tmp/ExportOptions-upload.plist
xcodebuild -exportArchive -archivePath ../../build/FamilyDash.xcarchive \
  -exportOptionsPlist /tmp/ExportOptions-upload.plist -exportPath ../../build/export \
  -allowProvisioningUpdates
```

`app/build/` is git-ignored. The build shows up under TestFlight in App Store Connect after
10–30 minutes and the "Family" group gets it automatically. Build history and gotchas are in
[`docs/APP_STORE_SUBMISSION.md`](../docs/APP_STORE_SUBMISSION.md) §8.

## Troubleshooting

- **"Can't reach http://…" banner** — the phone isn't on the same Wi-Fi as the Pi, the Pi is off, or the address changed. Tap the banner to fix the address. Giving the Pi a static IP / DHCP reservation on your router avoids this.
- **`raspberrypi.local` doesn't resolve** — some routers/phones don't do mDNS reliably; use the IP address instead (shown at the end of `install.sh`, or `hostname -I` on the Pi).
- **Pod install fails** — run `pod repo update` then `npx cap sync ios` again.
- **Blank white screen** — run `npm run build` (www/ was empty) then `npx cap sync ios`.
