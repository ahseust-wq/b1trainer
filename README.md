# Developer website (static, ready to upload)

Plain HTML/CSS. No build step, no cookies, no tracking, no external fonts or scripts.

```
index.html                  Home (German)            en/index.html            Home (English)
impressum/                  Impressum (§ 5 DDG)      en/legal-notice/         English translation
datenschutz/                Website privacy (DE)     en/privacy/              Website privacy (EN)
b1trainer/privacy/          B1 app privacy policy (DE/EN/TR) -> this URL goes into Play Console
app-ads.txt                 AdMob seller line (must stay at the domain root)
404.html, robots.txt, favicon.png, apple-touch-icon.png, assets/
```

## 1. Fill in your details (required before going live)
Run `./check-placeholders.sh`. It lists every yellow placeholder:
- Street, postcode and city, e-mail (Impressum, both privacy pages, app privacy policy)
- Phone: strongly recommended in the Impressum (courts expect a second fast contact channel
  next to e-mail). If you don't want to publish a phone number, use a contact form instead.
- VAT ID: only if you have one; otherwise delete that section in `impressum/index.html`.
- Hosting provider: in `datenschutz/` and `en/privacy/`, keep the paragraph for the host you use,
  delete the other, and delete the "Wählen Sie…/Keep the matching…" sentence. Check that your host
  is listed at https://www.dataprivacyframework.gov/list before publishing the DPF sentence.
- Your federal state's data protection authority (datenschutz/, "Ihre Rechte").
Upload only when the script prints nothing. This is a template, not legal advice; if in doubt,
have the Impressum and privacy texts checked.

## 2. Deploy

### Option A: Cloudflare Pages (recommended)
1. dash.cloudflare.com > Workers & Pages > Create > Pages > Upload assets.
2. Project name e.g. `seus`, drag this folder in, Deploy. Live at `https://seus.pages.dev`.
3. Custom domains > Set up a custom domain > `seus.app` (buy it in Cloudflare Registrar or point
   your registrar's DNS to Cloudflare). HTTPS is automatic.
4. Settings: accept the Data Processing Addendum (dash > Manage account > Configurations).
Updates: Create deployment > upload the folder again.

### Option B: GitHub Pages
1. New public repo named `<username>.github.io`, push this folder's contents to `main`.
2. Repo Settings > Pages > Source: Deploy from branch, `main`, `/ (root)`.
3. Custom domain: rename `CNAME.example` to `CNAME` with your domain inside, add the DNS records
   GitHub shows (4 A records for the apex domain), tick "Enforce HTTPS".
Without a custom domain the site is `https://<username>.github.io` and app-ads.txt still works,
because a user site is served from the domain root.

## 3. After it is live
- Open `https://<domain>/app-ads.txt`: it must show the single google.com line.
- Play Console > Store settings > Website: `https://<domain>` (exactly the domain hosting app-ads.txt).
- Play Console > App content > Privacy policy: `https://<domain>/b1trainer/privacy/`
- AdMob > Apps > app-ads.txt: "Check for updates". Verification can take up to 24 hours after the
  app is live on Play.
- Each new app: copy `b1trainer/privacy/` to `<app>/privacy/`, adapt it, and add an `<article class="app">`
  block on both home pages.
