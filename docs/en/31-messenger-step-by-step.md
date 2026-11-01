# Connect a Facebook Page to Javis step by step (messages, comments, posts)

*[Tiếng Việt](../31-messenger-tung-buoc.md) · **English***

This guide walks through every click, for people doing it the first time. The first setup takes about 20 minutes, mostly setting up the app on Meta's site. Each extra Page later is a few clicks.

> **Connect once, use it for three jobs:** the bot answers messages, replies to comments, and Javis posts to the Page (when you ask or automatically on a schedule). Everything in Javis happens in one place: the **Facebook Messenger** card on the **Connections** page. Once connected, the Page is already in the channel list on the Chatbot page; there is nothing to add anywhere else.

Before you start you need:

- Javis reachable through an **HTTPS domain** (Settings, Remote access). Meta does not send messages to localhost or an IP address.
- A Facebook account that is an **admin** of the Page.
- A Meta app of your own. If you have none, do Part 0. If you already have one (for example the app made for the Facebook Pages card in the store), reuse it and skip Part 0: one app serves all your Pages.

> **Security:** anyone with the App secret or a token controls the Page. Never send them to anyone, and do not take screenshots while they are visible.

---

## Overview

**On Meta's site (once):**

0. Create a Meta app (only if you have none)
1. Add Messenger and the permissions it needs
2. Set up Facebook Login and Javis's two addresses

**In Javis:**

3. Click Log in with Facebook and pick the Pages
4. Attach a bot to the new channel

**Open it to real customers:**

5. Switch the app to Live and test

If the Log in with Facebook button fails, use the [token path](#if-log-in-with-facebook-does-not-work-paste-a-token) at the end.

---

## Part 0. Create a Meta app (only if you have none)

A Meta app is the "permit" that lets Javis talk to Facebook on your behalf. It is free and made once.

1. Open [developers.facebook.com](https://developers.facebook.com) and log in with the Facebook account that is an admin of the Page.
2. The first time, Meta asks you to register as a developer: click **Get started**, verify a phone number or email, pick any role (for example "Business owner").
3. Go to **My Apps** and click **Create app**.
4. Give the app any **name** (for example your shop's name plus "Bot"), fill in a contact email, click **Next**.
5. At the use case step, pick **Engage with customers on Messenger from Meta** (under Business messaging). If it is not listed, pick **Other**, then the **Business** type.
6. At the Business portfolio step, pick the portfolio that manages the Page, or "I don't want to connect a business portfolio yet" if you have none. Click **Create app** and type your Facebook password again if asked.

You now have an app that cannot do anything yet. Part 1 gives it its permissions.

**Find the Page ID:** open the Page, go to **About, Page transparency**; the **Page ID** line is a number. On the Log in with Facebook path you do not need it: Javis lists the Pages for you.

---

## Part 1. Add Messenger and the permissions it needs

Go to **developers.facebook.com, My Apps, your app, Use cases**.

**1.1. Add Messenger**

- Click **Add use case** and filter by "Business messaging".
- Tick **Engage with customers on Messenger from Meta**, click **Save**. This use case brings messaging (`pages_messaging`), the Page list (`pages_show_list`) and subscribing the Page to the app (`pages_manage_metadata`).

**1.2. Add the comment and posting permissions**

- On the **Manage everything on your Page** row, click **Customize**.
- Click **Add** for 4 permissions:
  - `pages_read_engagement`: read posts and comments
  - `pages_read_user_content`: read what people write
  - `pages_manage_engagement`: reply to comments
  - `pages_manage_posts`: publish posts, photos and videos, edit and delete posts
- If a box asks about "affecting other use cases", click **Add**.

Done right: every permission shows **Ready for testing**. A missing one shows up at login as an "Invalid Scopes" error naming it.

---

## Part 2. Set up Facebook Login and Javis's two addresses

**2.1. Take the two addresses from Javis**

- Open Javis through its HTTPS domain, go to **Connections**, card **Facebook Messenger**, click **Connect**.
- The form shows two rows, each with a **Copy** button:
  - **Redirect address**, shaped like `https://<your-javis-domain>/messenger/oauth/callback`
  - **Privacy policy link**, shaped like `https://<your-javis-domain>/messenger/privacy`
- Leave the form open; you come back to it in Part 3.

**2.2. Put the redirect address into Facebook Login**

- In the Meta app, find **Facebook Login** in the left menu. It may be called **Facebook Login for Business**. If it is not there, click **Add product** (or **Add use case**) and pick it.
- Open its **Settings**.
- **Client OAuth login** and **Web OAuth login** must be **On** (they are by default).
- In **Valid OAuth Redirect URIs**, paste the **Redirect address**, character for character.
- Click **Save changes**.

Without this step, Log in with Facebook stops with "URL blocked".

**2.3. Fill in the app's basic details**

Go to **App settings, Basic**:

- **Privacy Policy URL** and **User data deletion**: paste the **Privacy policy link** from Javis into both. Javis serves that page on your own domain.
- **Category** and **App icon**: pick anything that fits your shop.
- Click **Save changes**.
- Copy two things from this page for Part 3: the **App ID** and the **App secret** (click **Show**, 32 characters).

---

## Part 3. Click Log in with Facebook and pick the Pages

Back on the Facebook Messenger form in Javis (Part 2.1):

1. Fill in the **App ID** and **App secret**.
2. Under **Page comments**, pick one:
   - **Show in the inbox, you reply** (default): each top-level comment becomes an inbox conversation, you reply by hand or ask the bot to draft.
   - **The bot replies publicly**: the bot answers right under the comment.
   - **Off**: comments are ignored.
3. Click **Log in with Facebook**. A Facebook tab opens:
   - Log in with the Page admin account.
   - Click **Edit settings** (or **Choose Pages**) and tick the Pages to connect.
   - Accept **every** permission Facebook asks for; do not switch any off.
   - The tab then says "Signed in with Facebook" and closes itself.
4. Back on the Javis tab the Page list appears, all ticked. Untick any Page you do not want and click **Connect the ticked Pages**.

Javis does the rest for each Page: a non-expiring Page token, the webhook in the Meta app, the message and comment subscriptions, then a checklist. Green means done. Yellow is a reminder; the bot still runs. Red has its fix right under it, or click **Repair** in the list of Pages.

> If the browser blocks the new tab, a link **Open the Facebook sign-in page** appears under the button; click it.

---

## Part 4. Attach a bot to the new channel

Until a bot is on, Javis does not take in messages and the inbox stays empty.

- Open **Chatbot, Bots**, create a bot or click **Edit** on one you have (for example the bot already on Zalo).
- Tick the Messenger channel you just connected. It is already in the list; no need for **Add channel**.
- Click **Save** and switch the bot on.

One bot can serve several channels at once (several Pages, Zalo too) with one Agent and one set of active hours.

**Posting:** nothing else to install. Ask Javis "post this to the Page with these 3 photos" or "every day at 8am post a product introduction" and it uses this same connection. Publishing and editing posts are real, public actions, so they only run when Javis is at Full access. To change comment handling later: **Connections**, Facebook Messenger card, **View details**, the Page comments box on each Page.

---

## Part 5. Switch the app to Live and test

In development mode the bot only answers people with a role on the app (admin, developer, tester). To answer real customers:

**5.1. Go Live**

In the Meta app, flip **App mode** from Development to **Live**. Meta needs the details from Part 2.3 and points at any field still missing.

**5.2. Test as an outsider**

Ask someone, or use a Facebook account with **no role on the app**: message the Page and comment under a post. Both must show in the Javis **inbox**, and the bot must answer (if it is on).

**5.3. If Meta still blocks it: ask for Advanced Access**

Meta's documentation says an app serving only your own Pages needs no review. If the test in 5.2 still gets no bot reply for outsiders, these permissions need **App Review**:

- `pages_messaging`
- `pages_read_engagement`, `pages_read_user_content`, `pages_manage_engagement`
- `pages_manage_metadata`

Open "App Review", **Request permissions**, describe the use and record the demo video Meta asks for. Meanwhile customers' messages still reach the inbox, and you can answer them from Meta Business Suite.

---

## Adding another Page

Click **Connect** on the Facebook Messenger card again, fill in the App ID and App secret, **Log in with Facebook** and tick the new Page. Parts 0 to 2 do not need redoing. Then tick the new channel on the bot as in Part 4.

---

## If Log in with Facebook does not work: paste a token

Use this when Part 3 fails and you cannot fix it. Parts 0, 1 and 2.3 are still needed; Part 2.2 (Facebook Login) is not.

**A. Get a token in Graph API Explorer**

> Do not use the **Generate** button in section 2 of Messenger API settings: that token can only send messages and cannot reply to comments.

- Open [Graph API Explorer](https://developers.facebook.com/tools/explorer).
- **Meta App:** pick your app. **User or Page:** pick **User Token**.
- **Permissions:** add all 7: `pages_show_list`, `pages_messaging`, `pages_manage_metadata`, `pages_read_engagement`, `pages_read_user_content`, `pages_manage_engagement`, `pages_manage_posts`.
- Click **Generate Access Token**, click **Edit settings**, pick **opt in to all current and future Pages**, leave every switch **On**, **Save**.
- Copy the `EAA...` string in the **Access Token** box. It lives about an hour; Javis turns it into a non-expiring Page token, so there is no need to extend it.

**B. Paste it into Javis**

- On the Facebook Messenger form, fill in the **App ID** and **App secret**.
- Click **Paste a token instead**, fill in the **Page ID** (Part 0 says where to find it) and paste the **token**.
- Click **Connect and check**. Javis does the rest as in Part 3.

Then continue with Parts 4 and 5.

---

## When the checklist shows the webhook red: do it by hand

Javis usually registers it by itself. Only do this when the **App webhook** or **Page is subscribed to the app** row is still red after **Repair**.

In the Meta app: **Use cases, Messenger from Meta, Customize, Messenger API settings**.

- **Configure webhooks (section 1):** paste the **Webhook address** into **Callback URL** and the **Verify token** into **Verify token** (both are on the Facebook Messenger form, each with a Copy button). Click **Verify and save**.
- **Subscribe the Page (section 2):** on the Page's row, click **Add subscriptions**, tick exactly 3 fields `messages`, `messaging_postbacks`, `feed`, click **Confirm**. Do not tick everything: extra fields send events Javis does not handle.

Then go back to the Messenger card and click **Check** on that Page.

---

## Common errors

| What you see | Why | Fix |
|---|---|---|
| Facebook says "URL blocked" at login | The redirect address is not in Facebook Login | Do Part 2.2, character for character |
| Facebook says "Invalid Scopes" with a permission name | The app has not added that permission | Do Part 1, add every permission, log in again |
| Javis says "The App ID or App secret is wrong" | A typo, or the secret of another app | Copy both again from App settings, Basic |
| Javis says the account manages no Page | No Page was ticked at login | Log in with Facebook again, click Edit settings, tick the right Pages |
| Connected, but customers write and the bot stays silent | No bot attached, or the app is still in development mode | Do Parts 4 and 5 |
| Javis says it may not post yet | The Page was connected before 0.438.0, or `pages_manage_posts` was not added | Add it in Part 1.2, then Log in with Facebook again on the Messenger card |
| Messages work but comments do not arrive | Comment permissions missing, or Page comments is Off | Add the permissions in Part 1.2 and log in again; change Page comments |
| Comments reach the inbox but the bot does not reply | Page comments is set to "Show in the inbox" | Switch to "The bot replies publicly" if you want the bot to answer |
| The checklist shows the webhook red | Javis could not register the webhook | Click Repair; if it stays red, do it by hand as in the section above |
