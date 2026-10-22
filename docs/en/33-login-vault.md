# 33 - Cookies (Login vault)

*[Tiếng Việt](../33-kho-dang-nhap.md) · **English***

From 0.251.0 Javis has a **Cookies** page (called Login vault before 0.261.0): a place to keep your own sign-ins (cookies) so Javis can reuse them. You sign in once in your own browser, hand the cookies to Javis, and Javis can then read pages that only show when you are signed in: your Shopee seller center, affiliate dashboards, your website's admin pages.

The vault is optional. With no sign-ins in it, Javis works exactly as before.

## Add a sign-in

1. Install the **Cookie-Editor** extension for Chrome or Edge.
2. Open the site while signed in, click the Cookie-Editor icon, choose **Export** then **JSON**. The cookies are copied to the clipboard.
3. In Javis open the sidebar, group **Connections**, item **Cookies** (the cookie icon). Press **Add cookies**.
4. Give it a name you will recognise (for example "Shopee seller"), paste the cookies and press **Save and check**.

If you already have a cookie file (a JSON file exported by Cookie-Editor, or a `cookies.txt` from the Get cookies.txt LOCALLY extension), press **Upload file** at the top of the page, the **Choose file** button in the form, or drop the file on the box. Javis reads the file in your browser and names the entry after the file when the Name box is empty. Files are limited to 1 MB.

Javis also reads a `cookies.txt` file and a `name=value; ...` string (then also fill in the Website field, for example `shopee.com`).

## What each card tells you

| Part | Meaning |
|---|---|
| **Signed in** | The last check opened the page without being sent to the sign-in screen |
| **Expired** | The site sent us to its sign-in page or answered 401/403 |
| **Page failed to load** | The page could not be loaded (network, site down). Not necessarily expired |
| **Valid until / N days left** | From the expiry dates inside the cookies |
| **Let Javis use it** | Off means the AI and page watches no longer use this sign-in; the cookies stay |

**Check** opens the **test page** with that sign-in. It defaults to the domain's home page; set it in the three-dot menu to a page you can only see when signed in (an orders page, say) for a more accurate answer. **Update** is where you paste fresh cookies when the session expires.

## Where Javis uses a sign-in

- **In chat:** every engine has the `javis_login` tool. Say "check my Shopee orders page" with the link, and Javis opens the page with the stored sign-in and reads it. When the sign-in has expired Javis says so plainly and asks you to update it, instead of retrying.
- **Page watch:** the form on the Page watch tab (Recurring work page) has a **Sign-in** field. Pick one and Javis can watch a page that needs a sign-in. When the session expires the watch pauses itself and tells you once.

Javis only **reads** pages (it downloads the page and takes the text). It does not click buttons, send forms or post with this sign-in. Pages built entirely in JavaScript may give little text.

## Safety

- Cookies are **encrypted** on the server. When the machine cannot encrypt (the `cryptography` library is missing) Javis refuses to save instead of writing them in the clear.
- **The AI never sees a cookie value.** The tool returns the page text and the sign-in's name only.
- A cookie only goes to the domain it belongs to, checked again on **every redirect hop**: a page that redirects to another site does not carry the cookies along.
- The Cookies page needs a **real dashboard sign-in**: an API token can neither read nor add sign-ins.
- **Customer chatbots never see this tool.**

## Honest caveats

- A cookie is a key to the account. Never paste someone else's, never send yours to anyone.
- Facebook and Google often ask to verify when a session is used from a different IP than the one you signed in from (for example Javis on a VPS). Smaller sites are usually more relaxed.
- Every session expires at some point. Then sign in again in your browser, export the cookies and press **Update**.
- If a site has an official API or MCP (Facebook Ads, Gmail, Calendar), prefer that: it is sturdier and safer than cookies.

## Technical details

Module `server/login_vault.py`, store `login_vault.sqlite3` in the data folder (mode 600), routes `/logins` and `/logins/action`, tool `javis_login` (plugin `javis-login`, level `readonly`, listed in `OWNER_ONLY_TOOLS`), page `dashboard/login-vault.js`. Page watches gain a `login_id` column.
