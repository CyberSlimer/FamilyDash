#!/usr/bin/env bash
# Capture App Store screenshots from the iOS Simulator (macOS only).
#
#   cd app && npm run screenshots
#
# Builds the app in DEMO mode (sample data, no Pi needed), installs it on the
# simulators App Store Connect requires, and saves PNGs at the exact pixel
# sizes Apple accepts into app/screenshots/<device>/. You then tap through the
# tabs when prompted; the script captures each one.
#
# App Store Connect (2024+) needs at minimum:
#   - 6.9" or 6.7" iPhone  (1320x2868 / 1290x2796)   -> iPhone 16 Pro Max / 15 Pro Max
#   - 6.5" iPhone           (1284x2778 / 1242x2688)  -> iPhone 11 Pro Max  (older sets; optional now)
#   - 13" iPad              (2064x2752 / 2048x2732)  -> iPad Pro 13-inch    (only if the app supports iPad)
# Simulator screenshots come out at native resolution, so they're already the right size.

set -euo pipefail
cd "$(dirname "$0")/.."

OUT="screenshots"
BUNDLE_ID=$(node -e "console.log(require('./capacitor.config.json').appId)")
DEVICES=("iPhone 16 Pro Max" "iPhone 15 Pro Max" "iPad Pro 13-inch (M4)")
TABS=("recipes" "meals" "grocery" "pantry" "calendars")

echo "==> Building DEMO web bundle"
node scripts/build.js --demo
npx cap sync ios >/dev/null

echo "==> Building app for the simulator"
xcodebuild -workspace ios/App/App.xcworkspace -scheme App -configuration Debug \
  -destination 'generic/platform=iOS Simulator' -derivedDataPath build/sim \
  -quiet build
APP=$(find build/sim -name "App.app" -path "*iphonesimulator*" | head -1)
[ -n "$APP" ] || { echo "App.app not found"; exit 1; }

for DEVICE in "${DEVICES[@]}"; do
  UDID=$(xcrun simctl list devices available -j | node -e '
    const d = JSON.parse(require("fs").readFileSync(0, "utf8")).devices;
    const want = process.argv[1];
    for (const rt of Object.keys(d).sort().reverse()) for (const dev of d[rt]) if (dev.name === want) { console.log(dev.udid); process.exit(0); }
  ' "$DEVICE" || true)
  if [ -z "$UDID" ]; then
    echo "!!  No simulator named '$DEVICE' installed - skipping (Xcode > Settings > Platforms to add it)"
    continue
  fi

  SLUG=$(echo "$DEVICE" | tr -cs 'A-Za-z0-9' '-' | sed 's/-$//')
  mkdir -p "$OUT/$SLUG"
  echo "==> $DEVICE ($UDID)"
  xcrun simctl boot "$UDID" 2>/dev/null || true
  xcrun simctl bootstatus "$UDID" -b >/dev/null
  open -a Simulator --args -CurrentDeviceUDID "$UDID"
  xcrun simctl uninstall "$UDID" "$BUNDLE_ID" 2>/dev/null || true
  xcrun simctl install "$UDID" "$APP"
  xcrun simctl launch "$UDID" "$BUNDLE_ID" >/dev/null
  sleep 4

  for TAB in "${TABS[@]}"; do
    echo "    Tap the '$TAB' tab in the simulator, then press Enter to capture (s = skip)..."
    read -r ans </dev/tty
    [ "$ans" = "s" ] && continue
    xcrun simctl io "$UDID" screenshot --type=png "$OUT/$SLUG/$TAB.png" >/dev/null
    echo "    saved $OUT/$SLUG/$TAB.png"
  done
  xcrun simctl shutdown "$UDID" >/dev/null 2>&1 || true
done

echo
echo "==> Restoring a normal (non-demo) web bundle"
node scripts/build.js
npx cap sync ios >/dev/null
echo "Done. Screenshots are in app/$OUT/. Upload them in App Store Connect > your app > iOS App > Screenshots."
