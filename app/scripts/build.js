#!/usr/bin/env node
/**
 * Assemble the web bundle Capacitor packages into the iOS app.
 *
 * The app is the same single-file UI the Pi serves at /mobile, so this just
 * copies frontend/mobile.html to www/index.html (plus icons/manifest) rather
 * than maintaining a second copy. Run automatically by `npm run sync`.
 */

const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..', '..');
const frontend = path.join(root, 'frontend');
const www = path.join(__dirname, '..', 'www');

// Clean the contents rather than the folder itself (a dev server may have it open)
fs.mkdirSync(www, { recursive: true });
for (const entry of fs.readdirSync(www)) {
    fs.rmSync(path.join(www, entry), { recursive: true, force: true });
}

// mobile.html -> index.html
let html = fs.readFileSync(path.join(frontend, 'mobile.html'), 'utf8');
// Inside the app the page is loaded from the bundle; a web manifest is meaningless there.
html = html.replace(/\s*<link rel="manifest"[^>]*>/, '');

// `node build.js --demo` (or FAMILYDASH_DEMO=1) pre-selects demo mode so a simulator
// opens straight onto sample data - used for App Store screenshots. Never ship this.
const demo = process.argv.includes('--demo') || process.env.FAMILYDASH_DEMO === '1';
if (demo) {
    const seed = '    <script>try { if (!localStorage.getItem("familydash.server")) localStorage.setItem("familydash.server", "demo"); } catch (e) {}</script>\n</head>';
    html = html.replace('</head>', seed);
}
fs.writeFileSync(path.join(www, 'index.html'), html);

// Icons referenced by the page
fs.cpSync(path.join(frontend, 'icons'), path.join(www, 'icons'), { recursive: true });

const bytes = fs.statSync(path.join(www, 'index.html')).size;
console.log(`Built www/index.html (${(bytes / 1024).toFixed(1)} KB) from frontend/mobile.html${demo ? '  [DEMO BUILD - not for release]' : ''}`);
