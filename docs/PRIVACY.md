# FamilyDash Privacy Policy

_Last updated: September 17, 2026_

FamilyDash is a companion app for a **self-hosted** family dashboard that you run yourself on a
Raspberry Pi (or any computer) in your own home. This policy explains what the app does and does
not do with your information.

## The short version

- FamilyDash does **not** collect, store, or transmit any personal data to us or to anyone else.
- The app talks **only** to the dashboard server **you** configure — a device on your own network.
- There are no accounts, no analytics, no advertising, no tracking, and no third-party SDKs that
  phone home.

## What the app stores on your device

The only thing FamilyDash saves on your phone is the **address of your dashboard server** (for
example `192.168.1.50:5000`), so you don't have to type it every time. It is stored locally on
the device and is removed when you delete the app.

## What the app sends, and where

Everything you do in the app — adding recipes, planning meals, editing grocery and pantry lists,
configuring calendars — is sent **directly to your own dashboard server** over your local network.
That server is under your control. We never see this data.

If you connect calendar feeds (Google Calendar, iCloud, Outlook, etc.), it is **your dashboard
server**, not the app and not us, that fetches those calendars using the credentials you provide.
Those credentials are stored on your server, in a configuration file you own.

## Demo mode

Entering `demo` as the server address runs the app on built-in sample data. In demo mode the app
makes no network requests at all.

## Local network permission

iOS asks for permission to access your local network the first time FamilyDash connects to your
dashboard. This is required to reach a device on your home Wi-Fi. The app does not scan your
network or communicate with any device other than the server address you enter.

## Children

FamilyDash is a household tool and does not knowingly collect any information from anyone,
including children.

## Changes

If this policy changes, the updated version will be published at the same address with a new
"last updated" date.

## Contact

Questions about this policy or the app: open an issue at
<https://github.com/CyberSlimer/FamilyDash/issues>.
