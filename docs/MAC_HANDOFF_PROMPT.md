# Prompt for the Mac session

> **Done — kept for reference.** This prompt was run on 2026-09-18: pod install, signing
> (Team 5X895J3VYD), simulator/device checks, screenshots, the App Store Connect record and
> TestFlight builds 1–2 are all complete, and build 3 followed on 2026-09-19. The Mac clone
> lives at `~/dev/FamilyDash`. For any later build, follow the "Day-to-day after setup" section
> of [`app/README.md`](../app/README.md) instead of re-running this.

Paste everything inside the code block into Claude Code on the Mac. It contains all the
context needed; no prior conversation required.

````text
I'm continuing work on my FamilyDash project — a Raspberry Pi family dashboard whose phone
management UI is packaged as a native iOS app with Capacitor. All code is done and pushed;
the ONLY remaining work is the macOS-specific part: CocoaPods, Xcode signing, running on my
iPhone, App Store screenshots, and a TestFlight upload. Work autonomously: make routine
decisions yourself, don't stop to ask unless something is genuinely destructive, and push to
GitHub when done.

Repo: https://github.com/CyberSlimer/FamilyDash (branch main). Clone into ~/code/FamilyDash
and move the session there. Read these first, in order:
  1. app/README.md                     — the build/sign/TestFlight steps for this exact project
  2. docs/APP_STORE_SUBMISSION.md      — every App Store Connect field, pre-written
  3. app/scripts/screenshots.sh        — the screenshot capture script

What already exists (do NOT redo or restructure):
- app/ is a Capacitor 6 project: appId com.cyberslimer.familydash, appName FamilyDash,
  webDir www. app/scripts/build.js bundles frontend/mobile.html -> app/www/index.html.
  There is intentionally ONE copy of the UI; never edit app/www or app/ios/App/App/public.
- app/ios/ is the generated Xcode project. `pod install` has never run (generated on
  Windows), so app/ios/App/App.xcworkspace/contents.xcworkspacedata and Podfile.lock don't
  exist yet — expected; pod install creates them.
- Info.plist already has NSAppTransportSecurity (local networking + arbitrary loads, because
  the Pi is plain http://), NSLocalNetworkUsageDescription, NSBonjourServices, and
  ITSAppUsesNonExemptEncryption=false. Keep all of them.
- Icons + splash are already in Assets.xcassets. app/ExportOptions.plist exists
  (method app-store-connect, automatic signing).
- The app has a DEMO MODE: typing `demo` as the server address runs it on built-in sample
  data with no server. `node scripts/build.js --demo` pre-selects it (used for screenshots
  only — never ship a demo build; screenshots.sh restores a normal build afterwards).

Do this, in order:

1. Prerequisites. Check for Xcode (full app, not just CLT), `xcode-select -p`, Node 18+,
   CocoaPods. Install what's missing: Node via Homebrew; CocoaPods via `brew install cocoapods`
   (avoid `gem install` / system Ruby). If Xcode isn't installed, tell me to install it from
   the App Store and stop — that's the one thing you can't do. Run
   `sudo xcodebuild -license accept` if needed, and make sure at least the iPhone 16 Pro Max
   and iPad Pro 13-inch (M4) simulators exist (`xcrun simctl list devices available`;
   add via Xcode > Settings > Platforms if not).

2. Build: `cd app && npm install && npm run build && npx cap sync ios` (runs pod install;
   on failure `pod repo update` and retry). Confirm contents.xcworkspacedata now exists.

3. Signing. In app/ios/App/App.xcworkspace (the WORKSPACE, not .xcodeproj), App target ->
   Signing & Capabilities: automatic signing ON, select my Team. My Apple Developer account
   should be signed into Xcode > Settings > Accounts; if it isn't, tell me to add it and
   wait. If bundle id com.cyberslimer.familydash is rejected as taken, choose a variant and
   update BOTH the Xcode target AND app/capacitor.config.json appId. Prefer editing
   project.pbxproj / config files over telling me to click; verify with
   `xcodebuild -showBuildSettings`.

4. Simulator sanity check before touching a device:
   `xcodebuild -workspace App.xcworkspace -scheme App -configuration Debug
    -destination 'generic/platform=iOS Simulator' build`
   then boot an iPhone simulator, install and launch (`xcrun simctl`), confirm the
   "Dashboard Server" screen appears, type demo, confirm the tabs load sample data.
   Take a screenshot for the report.

5. Physical iPhone if one is plugged in (`xcrun devicectl list devices`): build, install,
   launch. Tell me if I need to trust the developer certificate on the phone
   (Settings > General > VPN & Device Management). If no phone, say so and move on.

6. App Store screenshots: run `npm run screenshots` from app/. It's interactive — it asks
   me to tap each tab in the simulator and press Enter. If I'm not around, capture at
   least the first tab per device automatically (`xcrun simctl io <udid> screenshot`) and
   leave the rest for me. Output goes to app/screenshots/. Do not commit the PNGs unless
   they total under ~15 MB; otherwise add app/screenshots/ to .gitignore and tell me where
   they are.

7. Archive + upload to TestFlight. Ensure MARKETING_VERSION=1.0.0, CURRENT_PROJECT_VERSION=1.
   `xcodebuild ... archive` then `xcodebuild -exportArchive -exportOptionsPlist
   ../../ExportOptions.plist` (see docs/APP_STORE_SUBMISSION.md §8). Upload with whatever
   works non-interactively using credentials Xcode already holds (Organizer, Transporter,
   or `xcrun altool` with an App Store Connect API key). If the app record doesn't exist in
   App Store Connect yet, create it using the exact values in
   docs/APP_STORE_SUBMISSION.md §1 and tell me what you did. If any step truly needs my
   Apple ID password or 2FA, stop and tell me precisely what to do — never ask me to paste
   credentials into the chat.

8. Commit: Podfile.lock, contents.xcworkspacedata, any pbxproj signing changes, and an
   updated ExportOptions.plist if you added the teamID. Never commit build/, DerivedData,
   app/www, or app/ios/App/App/public. Commit message ends with:
   Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
   Push to origin main.

9. Update app/README.md or docs/APP_STORE_SUBMISSION.md only where reality differed
   (different bundle id, an extra step that was needed, a simulator name that changed).

Finish with a short report: tools installed, final bundle id and Team, simulator/device
results, whether the TestFlight upload succeeded, which screenshots were captured, and a
numbered list of anything I still have to do by hand in App Store Connect (adding internal
testers, filling metadata for public release — pointing to the sections in
docs/APP_STORE_SUBMISSION.md).
````
