# Branding and custom domains

*[Tiếng Việt](../15-thuong-hieu-ten-mien.md) · **English***

This page covers two things: changing Javis's logo/avatar to your own image, and pointing a custom domain (`javis.yourname.com`, say) at Javis so it runs over HTTPS. Both live under **Settings → General**.

## What this feature is

- **Avatar (logo):** replace the default JAVIS OS image with your own. The new image appears immediately in the top left corner, in the sidebar, on the sign-in screen, in the welcome window, and becomes the browser tab icon (favicon) too.
- **Custom domain (HTTPS):** instead of opening Javis by IP and port (something like `http://12.34.56.78:7777`), you use a memorable domain with the HTTPS padlock. Javis obtains the HTTPS certificate itself (On-Demand TLS through Caddy), and there is an **Enable SSL** button to request the certificate on demand rather than waiting.

One important note up front: the **Custom domain** section only works when you deploy Javis with Docker on a VPS with ports 80/443 open. If you run Javis on a personal machine (Windows, macOS), use the **Remote access** section right below it instead: Javis sets up a Cloudflare Tunnel itself, with HTTPS and even your own domain, no VPS needed. See [Remote access on a Windows or macOS computer](#remote-access-on-a-windows-or-macos-computer). Deploy details in [.env configuration](16-env-configuration.md) and the `DEPLOY.md` file in the project folder.

## Where to open it in Javis

Both features are under **Settings → General**. The General tab contains two cards:

- The **AVATAR** box: a preview image, an **Upload image** button and a **Restore default** button.
- The **DOMAIN AND SSL** box: an input (placeholder "e.g. javis.yourname.com"), a **Save and check** button, two status badges for DNS and SSL, two buttons **Enable SSL** and **Check again**, plus a three-step wizard whose content matches your actual VPS/Hostinger environment.

Every time you open Settings, Javis reloads the current values, checks DNS/HTTPS and shows the correct next step.

## Changing the logo/avatar (step by step)

1. Open **Settings → General** and find the **AVATAR** box.
2. Click **Upload image**. Your machine's file picker opens.
3. Pick an image file. Accepted formats: PNG, JPG, WEBP, GIF. Maximum size 5MB.
4. After picking, Javis shows the status line **Uploading…** then **Image updated ✓** when done. The new image replaces the old one everywhere immediately (top corner, sidebar, sign-in screen, preview box) with no page reload.

The browser tab icon (favicon) is the one exception and lags a beat: Javis serves it with a 5-minute cache, and browsers hold onto icons stubbornly. To see it right away, reopen the tab or reload bypassing the cache.

### Restoring the default image

1. In the **AVATAR** box, click **Restore default**.
2. Javis shows **Restoring…** then **Back to the default image.** The logo returns to the system original.

### Image status messages you may see

| Message | Meaning |
|---|---|
| Using a custom image. | You uploaded your own image and Javis is using it. |
| Using the default image. | No custom image uploaded, or you restored the default. |
| Uploading… | The image is being sent to the server. |
| Image updated ✓ | The new image was accepted and applied. |
| Restoring… | The custom image is being removed. |
| Back to the default image. | Removal finished, the original image is in use again. |
| Upload failed | The server rejected the file (wrong format, too large or empty). The specific reason replaces this line when the server sends one. |
| Network error while uploading | The connection dropped midway, try again. |
| Could not restore | The custom image could not be removed, try again. |

## Pointing a custom domain and enabling HTTPS (step by step)

This section assumes you deployed Javis with Docker on a VPS, enabled Caddy (On-Demand TLS) and opened ports 80/443. If not, do the deploy part first following `DEPLOY.md`.

### Step A: enter and save the domain

1. Open **Settings → General** and find the **DOMAIN AND SSL** box.
2. Enter the domain (or subdomain) you want in the input, for example `javis.yourname.com`. No need to type `https://`; if you do, Javis strips it.
3. Click **Save and check** (or press Enter in the input). Javis shows **Saving and checking…**, saves the domain, then runs the DNS/SSL check and draws the three-step wizard right in the UI.
4. If the domain is malformed, Javis reports that the domain is invalid and gives the example format. Fix it and save again.

To **remove** the domain: clear the input and click **Save and check**. Javis reports the domain was removed and hides the instructions.

### Step B: create the DNS record as instructed

After saving (or when you click **Check again**), the wizard shows step **2. Point DNS at the VPS** with the record to create and a **Copy record** button. The record appears as one compact line `A · <domain> · <server IP>`:

1. Go to the domain management page at your provider (where you bought the domain) and create a record:

   | Field | Value |
   |---|---|
   | Type | A |
   | Name/Host | the domain you just entered, e.g. `javis.yourname.com` |
   | Value/Points to | your VPS server's IP address (Javis detects and prefills this IP in the wizard) |

2. Wait for DNS to propagate (a few minutes to a few hours), then click **Check again**. Once DNS is right, step 2 turns into a ✓ and the description changes to say the A record points at the server IP.

### Step C: click Enable SSL to request the certificate

Once step 2 is ✓, the wizard shows step **3. Enable HTTPS** with the line saying that once DNS is correct you should click Enable SSL so Javis requests the certificate.

1. Click **Enable SSL**. Javis shows **Enabling SSL and requesting the certificate… (may take about 10 seconds)**.
2. The server records the intent to enable SSL then opens `https://<domain>/health` from itself. That very call is what forces Caddy to go and fetch the certificate the first time, instead of you having to open a browser manually.
3. When it finishes, Javis re-runs the check and updates the badges. Once the certificate is live, the status line reads **HTTPS is running for `<domain>`.**, the button relabels to **Re-activate**, and the wizard adds an **Open https://`<domain>` ↗** link.
4. If it did not come up, Javis states the reason and adds the line **"On a VPS run: docker compose -f docker-compose.yml -f docker-compose.https.yml up -d"** when you are on the Docker build without the HTTPS layer enabled.

The **Check again** button is usable at any time: it only reads state (showing **Checking…** then redrawing the badges) and never touches the certificate.

On Hostinger the **Enable SSL** button is hidden, because hPanel's Traefik is what issues certificates. See the Hostinger section below.

## Remote access on a Windows or macOS computer

The **REMOTE ACCESS** section (Settings, right below Domain & SSL) opens Javis to the Internet through a **Cloudflare Tunnel** (or privately through **Tailscale**, see Option 3), with no VPS, no router port and no terminal. Javis downloads `cloudflared` (Cloudflare's official free tool) in the right build for the machine (Windows x64/ARM, macOS Intel/Apple Silicon, Linux), runs it alongside Javis and reconnects when the network drops. It is HTTPS, so the microphone and voice work on a phone.

**Set a login password first** (Login account section). While the tunnel is on, Javis always asks for a login and does not let you turn login off. If the password is removed (for example with `reset-auth`), the tunnel stops within seconds.

### Option 1: Quick link (no account)

1. Pick **Quick link** and click **Turn on remote access**.
2. The first time, Javis downloads `cloudflared` (about 40 MB), then shows a link like `https://three-random-words.trycloudflare.com`.
3. Open that link on your phone and sign in with your password.

The link **changes every time Javis restarts**, which is fine for trying it out or short-term use.

### Option 2: Your own domain (fixed link)

You need a free Cloudflare account and a domain that uses Cloudflare DNS.

1. Go to [one.dash.cloudflare.com](https://one.dash.cloudflare.com), **Networks**, **Tunnels**, click **Create a tunnel**, pick **Cloudflared** and give it a name.
2. On the connector install step, copy the command (the Windows or the Mac one, either works). **You do not need to run it**: paste the whole line into the **Cloudflare tunnel token** box in Javis, and Javis picks the token out of it.
3. On the **Public Hostname** step: pick a subdomain (for example `javis.yourdomain.com`), set Service to **HTTP** and put the service address Javis shows in the URL box (by default `127.0.0.1:7777`, with a copy button).
4. Back in Javis, pick **Your own domain** and click **Turn on remote access**. Once the status reads **Running**, Javis reads the hostname you set and shows the link `https://javis.yourdomain.com`.

The token is stored encrypted, never sent back to the browser, and handed to `cloudflared` through an environment variable rather than on the command line.

### Option 3: Tailscale (private, only your devices)

Best when only you use it: the link is not on the Internet at all, and only devices signed in to your Tailscale account can open it. Javis does not install Tailscale itself (it needs system rights and an account sign-in), but it handles the rest.

1. Install [Tailscale](https://tailscale.com/download) on the computer running Javis and on your phone, signed in to the same account.
2. In Javis pick **Tailscale** and click **Turn on remote access**. Javis runs `tailscale serve` itself, no commands needed.
3. The first time, Tailscale may ask to switch HTTPS on for your network: Javis shows an **Open the HTTPS page** link; click it, then **Enable**. Javis retries on its own.
4. Open the `https://machine-name.tailnet-name.ts.net` link on a phone with Tailscale on.

The Tailscale link keeps working while Javis restarts; **Turn off** removes only what Javis added and leaves your other Tailscale settings alone. People outside your Tailscale network cannot open it, so it does not serve share links or webhooks from outside services; use Option 1 or 2 for those.

### Worth knowing

- When the computer is off or asleep, the link is down too. For 24/7 access, turn off Sleep (Windows) or enable "Prevent automatic sleeping" (macOS).
- Javis turns the tunnel back on after a restart or an update if you left it on.
- If Javis says Cloudflare points to a different address, change the service URL in the Public Hostname to the address Javis shows.
- The Docker build on a VPS can still use the older way (`docker compose --profile tunnel`) in `DEPLOY.md`.

## Quick reference of buttons and states

The two badges sit right under the domain input:

| DNS badge | Meaning |
|---|---|
| DNS: checking | No result yet (the page just opened) |
| DNS: pointing correctly | The A record matches the server IP |
| DNS: wrong IP (`<ip>`) | A record exists but points elsewhere, the actual IP in brackets |
| DNS: not pointed | No record could be resolved for the domain |

| SSL badge | Meaning |
|---|---|
| SSL: checking | No result yet |
| SSL: on | HTTPS genuinely runs for the domain |
| SSL: via Hostinger | Deployed on Hostinger, hPanel's Traefik handles the certificate |
| SSL: pending | You enabled SSL but the certificate is not live yet |
| SSL: off | SSL is not enabled for this domain |

| Button | What happens |
|---|---|
| **Save and check** | Saves the domain into Javis then runs the DNS/SSL check |
| **Enable SSL** | Records the intent and actively forces Caddy to request the certificate now |
| **Re-activate** | The same button relabelled once HTTPS is running; click to request the certificate again |
| **Check again** | Only reads DNS/SSL state, never touches the certificate |
| **Copy record** | Copies the line `A · <domain> · <IP>` to the clipboard (changes to "Copied ✓" for about a second) |
| **Copy variable** | Only in the Hostinger wizard: copies the line `DOMAIN_NAME=<domain>` |

The status line at the bottom of the card can read:

| Status line | Meaning | What to do |
|---|---|---|
| No domain set. | No domain saved yet. | Enter a domain then click Save and check. |
| Saving and checking… / Checking… | Running, wait a moment. | Nothing. |
| Saved. Checking DNS/SSL… | The domain was written, DNS is being resolved. | Wait for the result. |
| Domain removed. | You just saved an empty field. | Nothing. |
| HTTPS is running for `<domain>`. | All done. | Nothing more needed. |
| You are on HTTPS | You are accessing that very domain over HTTPS. | Done. |
| Certificate not valid yet, DNS is not pointing correctly or the certificate has not been issued | The connection works but the certificate is unusable. | Check the DNS badge; if DNS is right, wait a bit then click Enable SSL again. |
| Cannot reach port 443, Caddy/HTTPS is not running or another proxy holds ports 80/443 | Nothing answers on port 443. | Enable the HTTPS layer with the command Javis suggests, and check whether another service holds ports 80/443. |
| Saved in Javis; the DOMAIN_NAME and Redeploy steps on Hostinger remain. | Hostinger: the Traefik route does not match the domain yet. | Do step 3 of the Hostinger wizard. |
| Enter and save a domain first. | You clicked Enable SSL with the domain field empty. | Enter a domain and save. |
| Invalid domain (e.g. javis.yourname.com) | The string is not shaped like a domain. | Drop spaces, drop any trailing path, type it as `name.yourname.com`. |
| Enabling SSL failed | The server refused to enable it. | Read the accompanying reason line. |
| Could not check (network error). | The browser could not reach the server. | Try again in a few minutes. |
| Network error while saving / Network error while enabling SSL | The connection dropped midway. | Try again. |

## About Caddy and On-Demand TLS (worth knowing)

- Javis uses Caddy to obtain and renew HTTPS certificates automatically (Let's Encrypt) through On-Demand TLS. You never install a certificate by hand.
- To prevent abuse, before issuing a certificate Caddy asks Javis (through the internal `/tls-check` gate) and only issues for the exact domain you entered in the app. A stranger pointing DNS at your server IP cannot force it to request arbitrary certificates.
- To change or remove the domain on a Caddy VPS, just edit the **DOMAIN AND SSL** field, click **Save and check**, then **Enable SSL** for the new domain. Hostinger needs a Redeploy when the Traefik route changes.
- Enabling Caddy (running `docker compose ... up -d` with the HTTPS config file) and opening ports 80/443 are infrastructure deploy steps outside this interface. See the detailed deploy guide in the project's `DEPLOY.md`.
- When you reach Javis through the custom domain over HTTPS, the server marks the login cookie `secure` on its own, with no need to set `JAVIS_SECURE_COOKIE` manually. See [Security and accounts](14-security-and-accounts.md).

## If you deploy on Hostinger (a different path)

> 🛒 No Hostinger VPS yet? [Get one here](https://www.hostinger.com?REFERRALCODE=UTRBLOGMIDSN).

A Hostinger VPS already runs the Traefik reverse proxy handling SSL, and Traefik holds ports 80/443. Javis still lets you enter a domain, check DNS and prepare the variable you need right in the UI, but the container has no authority to edit hPanel's Traefik routes. So the **Enable SSL** button is hidden, the SSL badge reads **SSL: via Hostinger**, and step 3 of the wizard becomes **3. Activate the HTTPS route on Hostinger**:

1. Point DNS: the record `A  <your domain> → <Hostinger VPS IP>`.
2. Deploy with the compose file carrying Hostinger's Traefik labels: `docker-compose.hostinger.yml` (Docker Manager → Compose → URL).
3. Click **Copy variable** in the wizard, set `DOMAIN_NAME=<your domain>` in Docker Manager then click **Redeploy**. The wizard also shows the current Traefik route so you can compare.
4. Open `https://<domain>`; Traefik requests the certificate on the first visit. No more entering through `:7777`.

If you try to click Enable SSL on Hostinger (through the API, say), Javis refuses and states plainly that Hostinger manages HTTPS through Traefik, so set `DOMAIN_NAME` in Docker Manager and Redeploy.

After the Redeploy, return to Settings and click **Check again**. Details and troubleshooting are in the "Domain + HTTPS on Hostinger" section of `DEPLOY.md`; both documentation links also sit right under the domain card.

### What the SSL badge says (since 0.248.0)

On each Check again, Javis opens `https://<domain>` from the server itself, looks at what answers, and names the broken step on the badge:

- **SSL: on**: done, the link works.
- **SSL: Hostinger has no route yet**: DNS reaches the VPS but Traefik has no route for this domain. The project's `traefik...rule=Host(...)` still holds the old name: set `DOMAIN_NAME` to the domain (or edit the `Host` line in the YAML directly), then **Redeploy**. This is the most common case: the domain was entered in Javis and DNS points right, but the stack was not redeployed with the new name.
- **SSL: certificate pending**: the route reaches Javis, Let's Encrypt has not issued the certificate yet. Wait a few minutes and check again.
- **SSL: proxy cannot reach Javis**: Traefik answers 502; check that the Javis container is running.
- **SSL: domain opens another site**: the domain points to another site or another Javis (a second stack on the same VPS, for example).
- **SSL: port 443 unreachable**: nothing answers on the VPS's HTTPS port.

If you edit the `Host(...)` line in the YAML instead of setting `DOMAIN_NAME`, Javis no longer says "Redeploy still needed" once the domain works over HTTPS.

## Tips

- The logo image should be square (1:1) so it is not cropped oddly, since Javis shows it in a rounded square frame.
- If somewhere still shows the old image after an upload, wait about a minute or reload the page; the system caches the logo briefly (the favicon longer, about 5 minutes).
- If you have no VPS or custom domain but still want remote access over HTTPS, use the **Remote access** section (see above).
- Use a proper **A** record (IPv4). Do not use a CNAME for this domain unless you fully understand the consequences.
- Do not click **Enable SSL** repeatedly while DNS is still wrong. Each click makes Javis force Caddy to request a certificate, and many failed requests hit Let's Encrypt rate limits.

## Common problems

- **Saving reports "Invalid domain":** check the spelling, no spaces, no trailing path. The correct shape is `name.yourname.com`.
- **The A record exists but the badge still says "DNS: not pointed":** DNS needs time to propagate. Wait a few more minutes to a few hours then click **Check again**.
- **The badge says "DNS: wrong IP (...)":** the IP in the A record differs from the Javis server's IP. Copy the exact IP Javis shows in step 2 of the wizard and update the A record.
- **DNS is right but Enable SSL reports "Cannot reach port 443":** the HTTPS layer is not running. On a Docker VPS, run exactly the command Javis suggests (`docker compose -f docker-compose.yml -f docker-compose.https.yml up -d`) then click again, and check that ports 80/443 are open and not held by another proxy.
- **Enable SSL reports "Certificate not valid yet":** usually DNS only just became correct and Caddy has not finished issuing. Wait a minute or two then click again.
- **There is no Enable SSL button:** you are running on Hostinger. Javis hides it because only hPanel's Traefik can issue the certificate; follow the Hostinger wizard above.
- **The upload reports a format error or "too large":** use only PNG, JPG, WEBP or GIF, under 5MB.
- **The Domain field does not behave as expected on a personal machine:** this feature is for the Docker deploy on a VPS with ports 80/443. On a personal machine the domain/HTTPS part will not activate.

## Related

- [Getting started and first setup](01-getting-started.md)
- [Security and accounts](14-security-and-accounts.md)
- [.env configuration](16-env-configuration.md)
- [Troubleshooting and FAQ](17-troubleshooting.md)
