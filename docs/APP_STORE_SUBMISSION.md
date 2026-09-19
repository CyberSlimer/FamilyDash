# FamilyDash — iOS Submission Kit

Everything needed to get FamilyDash onto iPhones through Apple, prepared in advance so the Mac
session is just execution. Two routes; pick based on who needs the app.

| Route | Review? | Who can install | Effort |
|---|---|---|---|
| **A. TestFlight internal testing** ← start here | No | Up to 100 people you invite (App Store Connect users) | Archive + upload, add testers. ~30 min. |
| **B. Public App Store** | Yes (1–3 days typically) | Anyone | Route A + metadata, screenshots, privacy answers, review notes. ~2 hrs. |

Route A is enough for a household and skips review entirely; builds expire after 90 days, so you
re-upload occasionally. Route B is only needed if strangers should be able to install it.
Everything below covers both; B-only items are marked.

---

## 0. One-time prerequisites (done already ✔ / to do ☐)

- ✔ Apple Developer Program membership (paid) — you have this.
- ✔ Xcode project with bundle id, icons, launch screen, permissions (`app/ios/`).
- ✔ `ITSAppUsesNonExemptEncryption = NO` in Info.plist (skips the export-compliance question on every upload).
- ✔ Demo mode (`demo` as server) so the app works with no Pi — for screenshots and for App Review.
- ✔ NSCameraUsageDescription / NSPhotoLibraryUsageDescription for the Display tab's photo upload.
- ✔ Privacy policy: [`docs/PRIVACY.md`](PRIVACY.md).
- ☐ Sign in to Xcode → Settings → Accounts with your Apple ID on the Mac.
- ☐ Decide iPhone-only vs iPhone+iPad (see §4). Default in the project is both.

---

## 1. App Store Connect — create the app record

<https://appstoreconnect.apple.com> → **My Apps** → **+** → **New App**

| Field | Value |
|---|---|
| Platforms | iOS |
| Name | **`Family Dashboard Planner`** — created 2026-09-18 (App ID 6813711751). `FamilyDash` was the original plan; the listing name only has to be unique on the App Store, the on-device name stays FamilyDash. |
| Primary language | English (U.S.) |
| Bundle ID | `com.cyberslimer.familydash` — appears in the dropdown only after the first Xcode archive/registration of that id. If it's not there yet, register it at developer.apple.com → Identifiers → **+** → App IDs, or let Xcode do it by archiving once with automatic signing. |
| SKU | `familydash-ios` |
| User access | Full Access |

---

## 2. Version information (copy-paste)

**Version:** `1.0.0`  **Build:** `1` (Xcode: `MARKETING_VERSION` / `CURRENT_PROJECT_VERSION`; bump the build number for every upload)

**Subtitle** (30 chars max)
```
Your family's Pi dashboard
```

**Promotional text** (170 chars; can change without a new build)
```
Manage calendars, meals, groceries and the pantry for the family dashboard on your Raspberry Pi — from your phone.
```

**Description**
```
FamilyDash is the phone companion for the Family Dashboard — the open-source command center that runs on a Raspberry Pi and a wall-mounted screen in your home.

The dashboard rotates through today's schedule and weather, this week's meal plan, the grocery list, and favorite recipes plus pantry items about to expire. FamilyDash lets everyone in the house keep that screen up to date from wherever they are on your Wi-Fi.

CALENDARS
• Bring every family calendar together: Google Calendar, iCloud, Outlook, school and sports feeds — anything with an ICS/webcal link or a CalDAV account
• Test a feed before saving it, pick a color for each calendar, and see at a glance whether it's syncing
• Recurring, all-day and multi-day events are handled correctly

MEALS & RECIPES
• Save recipes by hand or import them from a URL
• Plan the week's breakfasts, lunches and dinners
• Mark favorites so they show on the big screen

GROCERIES & PANTRY
• Generate the shopping list straight from the meal plan
• Check items off as you shop, organized by store section
• Track what's in the fridge, freezer and pantry, and get warned before it expires

PRIVATE BY DESIGN
FamilyDash talks only to the dashboard server you run yourself. There are no accounts, no cloud, no analytics and no ads. Your data never leaves your home.

REQUIREMENTS
You need the Family Dashboard server running on your network (free and open source — see the support link). Don't have one yet? Enter "demo" as the server address to explore the app with sample data.
```

**Keywords** (100 chars max, comma-separated, no spaces after commas)
```
family,calendar,dashboard,raspberry pi,meal plan,grocery list,pantry,recipes,home,kiosk,self-hosted
```

**Support URL:** `https://github.com/CyberSlimer/FamilyDash/issues`
**Marketing URL** (optional): `https://github.com/CyberSlimer/FamilyDash`
**Privacy Policy URL:** `https://github.com/CyberSlimer/FamilyDash/blob/main/docs/PRIVACY.md`
**Copyright:** `2026 CyberSlimer`

**Category:** Primary **Productivity** · Secondary **Lifestyle**

**What's New in This Version** (1.0.0)
```
First release.
```

---

## 3. App Review information _(Route B)_

**Sign-in required:** No

**Contact:** your name, phone, email (Apple may call/email during review).

**Notes for the reviewer** — this is the important one; without it the app looks broken to a reviewer who has no Raspberry Pi:
```
FamilyDash is a companion app for a self-hosted home dashboard server (open source: https://github.com/CyberSlimer/FamilyDash). In normal use it connects to a Raspberry Pi on the user's own Wi-Fi, which is not reachable from outside the home.

TO TEST WITHOUT A SERVER: on the first screen ("Dashboard Server"), type   demo   in the address field (or tap "Try the demo") and press Connect. The app then runs fully on built-in sample data — every tab (Recipes, Meals, Grocery, Pantry, Calendars, Display) works, including adding and deleting items, generating a shopping list from the meal plan, marking a meal cooked, testing a calendar feed, changing the dashboard's appearance, and the settings screen via the gear icon.

PHOTOS: the Display tab can add photos that appear on the user's own dashboard screen at home. On a real server the photo is uploaded to that machine and nowhere else. In demo mode nothing is uploaded — a picked photo is read on the device only, to preview it. The camera and photo-library permission prompts appear only if you choose to add a photo.

The Local Network permission prompt appears only when connecting to a real server; it is not triggered in demo mode. No account, login, or purchase exists anywhere in the app.
```

**Attachment:** none needed.

---

## 4. Screenshots _(Route B; TestFlight needs none)_

Run on the Mac: `cd app && npm run screenshots`. It builds the app in demo mode, boots each
simulator, and saves PNGs at the exact required sizes into `app/screenshots/<device>/` — you
tap each tab when prompted. Upload 3–10 per device size; the first two are what people see in
search results, so lead with **Calendars** and **Meals**.

Required sizes (App Store Connect will tell you which are mandatory for your setup):

| Slot | Simulator | Pixels |
|---|---|---|
| iPhone 6.9" | iPhone 16 Pro Max | 1320 × 2868 |
| iPhone 6.7" | iPhone 15 Pro Max | 1290 × 2796 |
| iPad 13" (only if iPad is supported) | iPad Pro 13-inch (M4) | 2064 × 2752 |

**iPhone-only vs iPad.** The project currently targets both (`TARGETED_DEVICE_FAMILY = "1,2"`).
iPad support means iPad screenshots are mandatory and the review checks iPad layout (the page is
responsive, so it looks fine). To ship iPhone-only and skip that: in Xcode → App target → General →
**Supported Destinations**, remove iPad (this sets `TARGETED_DEVICE_FAMILY = 1`). Recommendation:
keep iPad — a kitchen iPad is a natural place for this app.

Suggested order and caption ideas (captions are optional; add them in a design tool or skip):
1. Calendars — "Every family calendar in one place"
2. Meals — "Plan the week in seconds"
3. Grocery — "Shopping list, generated from the meal plan"
4. Pantry — "Know what's expiring before it does"
5. Recipes — "Import recipes from any site"

---

## 5. App Privacy questionnaire _(Route B; answers)_

App Store Connect → App Privacy → **Get Started**.

- **Do you or your third-party partners collect data from this app?** → **No, we do not collect data from this app.**

That's the whole questionnaire; the label will read **"Data Not Collected."** This is accurate:
the app stores only the server address locally and sends user content to the user's own server.

---

## 6. Age rating _(Route B)_

Answer **None / No** to every content question (violence, sexual content, profanity, gambling,
contests, unrestricted web access, medical info, etc.). Result: **4+**.

---

## 7. Pricing & availability

- Price: **Free**
- Availability: all territories (or just United States — either is fine)
- No in-app purchases, no subscriptions.

---

## 8. Build & upload (both routes)

From the Mac, after `npm run sync` (see `app/README.md`):

**Xcode GUI:** Product → **Archive** → Organizer → **Distribute App** → **App Store Connect** → Upload.
Xcode handles signing, symbols and the export-compliance question (already answered by Info.plist).

**Command line** (what the Mac handoff prompt does):
```bash
cd app/ios/App
xcodebuild -workspace App.xcworkspace -scheme App -configuration Release \
  -destination 'generic/platform=iOS' -archivePath ../../build/FamilyDash.xcarchive archive
xcodebuild -exportArchive -archivePath ../../build/FamilyDash.xcarchive \
  -exportOptionsPlist ../../ExportOptions.plist -exportPath ../../build/export
# upload: Xcode Organizer, Transporter.app, or:
xcrun altool --upload-app -f ../../build/export/App.ipa -t ios --apiKey KEY_ID --apiIssuer ISSUER_ID
```
`app/ExportOptions.plist` (method `app-store-connect`, automatic signing, teamID filled in) is
included in the repo. Add `-allowProvisioningUpdates` to both commands so Xcode can create the
Apple Distribution certificate and profile on first use.

**Verified on the Mac (2026-09-18):** both commands succeed once the Apple Account in
Xcode → Settings → Accounts has a live session (an expired session shows up as
*"Unable to log in with account … login details were rejected"* from `xcodebuild`; sign in
again in the GUI). Uploading non-interactively (`destination: upload` in ExportOptions, or
altool) **requires the app record from §1 to exist first** — without it the upload fails with
`missingApp(bundleId: "com.cyberslimer.familydash")`. The Xcode Organizer route is the one
path that offers to create the record for you during Upload.

The build appears under **TestFlight** in App Store Connect after ~10–30 min of processing.

Build 1 (2026-09-18) drew an App Store Connect warning that the minimum iOS version was too low —
the project shipped with Capacitor's default `IPHONEOS_DEPLOYMENT_TARGET = 13.0`. Fixed for build 2:
target and Podfile are on **iOS 15.0** (the Podfile's `post_install` pins the Capacitor pods to
match). Keep it at 15 or higher for future builds.

Build 3 (2026-09-19) carries the inventory loop and the Display tab (first build with the
camera/photo-library usage strings). Archived and uploaded with the two commands above, using a
copy of `ExportOptions.plist` with `destination` set to `upload` — the committed file stays on
`export` so a plain `-exportArchive` only produces an .ipa.

---

## 9a. Route A — TestFlight internal testers

**Status 2026-09-18:** internal group **"Family"** exists with automatic distribution on and
builds 1.0.0 (1), (2) and (3) attached (build 3 uploaded 2026-09-19); `ryan.j.probst@icloud.com` invited. To add family members:
Users and Access → + (role *Customer Support* is enough) → then TestFlight → Family → + tester.

App Store Connect → your app → **TestFlight** → **Internal Testing** → **+** create a group
(e.g. "Family") → add testers. Each tester needs to be added as a **User** under Users and Access
(role: Customer Support or Developer is fine) with their Apple ID email. They get an email, install
the **TestFlight** app, and the build appears. Internal builds need **no review**.

_External testing_ (people who aren't App Store Connect users, up to 10,000) requires a brief
"Beta App Review" — same notes as §3 apply.

## 9b. Route B — submit for review

App Store Connect → your app → **iOS App 1.0.0** → fill §2–§7 → **Build** → select the uploaded
build → **Add for Review** → **Submit to App Review**. Typical turnaround 24–72 h. Choose
**Manually release this version** if you want to control the go-live moment.

Common rejection reasons for this kind of app and how they're pre-empted:
- *"App requires hardware we don't have"* → Reviewer notes point to demo mode (§3).
- *Guideline 4.2 minimum functionality (thin web wrapper)* → The app has a native setup flow,
  offline/timeout handling, local-network permission, and is a full CRUD tool, not a website
  view. If it comes up anyway, reply via Resolution Center citing those and the open-source server.
- *Missing privacy policy URL* → §2.
- *iPad screenshots missing* → §4.

---

## 10. After 1.0

Each update: bump `CURRENT_PROJECT_VERSION` (and `MARKETING_VERSION` for user-visible versions),
`npm run sync`, Archive, Upload. TestFlight testers get it automatically; App Store users after
you submit the new version (metadata can be reused).

Future native features that would justify the app over the PWA: push notifications when an event
is starting or an item is expiring (needs a small change on the Pi to send them), a home-screen
widget with today's events, Siri Shortcuts ("add milk to the grocery list").
