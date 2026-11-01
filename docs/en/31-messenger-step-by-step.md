# Connect a Facebook Page to Javis step by step (messages and comment replies)

*[Tiếng Việt](../31-messenger-tung-buoc.md) · **English***

This guide walks through every click on Meta's site, for people doing it the first time. The first setup takes about 20 minutes. Each extra Page later takes about 2 minutes.

> **There is a faster way:** from 0.434.0 the **Facebook Messenger** card on the **Connections** page has a **Log in with Facebook** button. Log in, tick the Pages, and Javis gets the tokens itself, so you can skip Parts 3 and 4 below. See [31 - Messenger](31-messenger.md). This guide is the manual token path, for when the login button does not work or you want to control every step.

Before you start you need:

- Javis reachable through an **HTTPS domain** (Settings, Remote access). Meta does not send messages to localhost or an IP address.
- A Facebook account that is an **admin** of the Page.
- A Meta app of your own. If you have none, do Part 0 below. If you already have one (for example the app made for the Facebook Pages card in the store), reuse it and skip Part 0: one app serves all your Pages.

> **Security:** anyone with the token or the App secret controls the Page. Never send them to anyone, and do not take screenshots while a token is visible.

---

## Overview

0. Create a Meta app (only if you have none)
1. Prepare the Meta app (add Messenger and the comment permissions)
2. Set the webhook and subscribe the Page to events
3. Create a Page token with every permission that never expires
4. Paste it into Javis
5. Switch the app to Live

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

**Find the Page ID:** open the Page, go to **About, Page transparency**; the **Page ID** line is a number. You can also get it in Part 3.3.

---

## Part 1. Prepare the Meta app (once)

Go to **developers.facebook.com, My Apps, your app, Use cases**.

**1.1. Add Messenger**

- Click **Add use case** and filter by "Business messaging".
- Tick **Engage with customers on Messenger from Meta**, click **Save**.

**1.2. Add the comment permissions**

- On the **Manage everything on your Page** row, click **Customize**.
- Click **Add** for 3 permissions:
  - `pages_read_engagement`: read posts and comments
  - `pages_read_user_content`: read what people write
  - `pages_manage_engagement`: reply to, edit and delete comments
- If a box asks about "affecting other use cases", click **Add**.

Done right: every permission shows **Ready for testing**.

---

## Part 2. Webhook and event subscription

Go to **Use cases, Messenger from Meta, Customize, Messenger API settings**.

**2.1. Configure the webhook (section 1)**

Take two things from the Javis form: **Chatbot, Channels, Add channel, Messenger**. The form shows the **Webhook address (Callback URL)** and the **Verify token**.

- Callback URL: paste the webhook address, shaped like `https://<your-javis-domain>/messenger/webhook`
- Verify token: paste the verify token
- Click **Verify and save**. A green tick means done.

**2.2. Subscribe the Page to events (section 2)**

- On the row of the Page the bot will serve, click **Add subscriptions** (or "View all fields", **Edit**).
- Tick exactly these 3 fields:
  - `messages`: messages
  - `messaging_postbacks`: button taps
  - `feed`: comments and posts
- Click **Confirm**.

> Do not tick everything. Extra fields (calls, standby, messaging_handovers...) send events Javis does not handle and only add noise.

---

## Part 3. A Page token with every permission that never expires

> Do not use the **Generate** button in section 2 of Messenger API settings: that token can only send messages and cannot reply to comments.

**3.1. Create a user token with every permission**

- Open [Graph API Explorer](https://developers.facebook.com/tools/explorer).
- **Meta App:** pick your app.
- **User or Page:** pick **User Token**.
- **Permissions:** add all 6 (type the name, then click the suggestion):
  - `pages_show_list`
  - `pages_messaging`
  - `pages_manage_metadata`
  - `pages_read_engagement`
  - `pages_read_user_content`
  - `pages_manage_engagement`
- Click **Generate Access Token**. When the popup opens:
  - Click **Edit settings** (not Continue).
  - Pick **opt in to all current and future Pages**, click **Continue**.
  - Leave every switch **On**, click **Save**, then **OK**.

**3.2. Extend it to a long-lived token**

- Click the **(i)** icon next to the Access Token box, choose **Open in Access Token Tool**.
- Scroll down, click **Extend Access Token**, type your Facebook password again if asked.
- Copy the new token shown under that button.

Check: paste the token into the debugger; it must say **Type: User**, **Expires: Never**, and the Scopes must list all 6 permissions.

**3.3. Get each Page's token**

- Back in Graph API Explorer, paste the long-lived token into the **Access Token** box.
- **Do not click Generate Access Token again** (that throws the long-lived token away).
- In the query box type `PAGE_ID?fields=name,access_token` (replace `PAGE_ID` with the Page's numeric ID).
- Click **Submit** and copy the `access_token` value (the part inside the quotes, without the quotes).

To see every Page's token at once, type `me/accounts?fields=name,id,access_token`.

---

## Part 4. Paste it into Javis

**4.1. Get the App secret**

- In your app: **App settings, Basic**, the **App secret** field, click **Show**.
- One App secret serves every Page of the same app.

**4.2. Build one line**

Open a text editor and put the 3 things on **one line**, separated by **one space**:

```
PAGE_ID PAGE_TOKEN APP_SECRET
```

Javis tells the parts apart by their shape, but keep this order so it is easy to check.

**4.3. Save in Javis**

- In Javis, **Chatbot, Channels, Add channel, Messenger**.
- Paste the line into the **Messenger token** field and click **Check**.
- Done right, it shows: "✓ Bot PAGE_ID (Page name)".
- Fill in a **Label** and click **Save**.
- Open **Chatbot, Bots**, create a bot or edit one, tick the new Messenger channel and switch the bot on.

> Another way: the **Facebook Messenger** card on the **Connections** page, under **Paste a token instead**, takes the App ID, App secret, Page ID and token in separate fields, then registers the webhook, subscribes the Page and shows a checklist. Wherever you connect it, it is the same channel and shows on both pages.

---

## Part 5. Switch the app to Live

In development mode the bot only answers people with a role on the app (admin, developer, tester). To answer real customers:

**5.1. Fill in the required details**

In your app: **App settings, Basic**:

- **Privacy Policy URL:** Javis serves this page at `https://<your-javis-domain>/messenger/privacy`; paste it here and into User data deletion.
- **Category**
- **App icon**
- Click **Save changes**.

**5.2. Go Live**

Flip **App mode** from Development to **Live**.

**5.3. Ask for Advanced Access**

Test with a Facebook account that has **no role on the app**: message the Page and comment on a post. If the bot answers, you are done. If Meta still blocks it, these permissions need **App Review** to answer every customer reliably:

- `pages_messaging`
- `pages_read_engagement`, `pages_read_user_content`, `pages_manage_engagement`
- `pages_manage_metadata`

Open section 3 "Complete App Review", **Request permissions**, describe the use and record the demo video Meta asks for.

---

## Adding another Page (about 2 minutes each)

The long-lived user token from Part 3.2 can be reused, no need to start over:

1. **Part 2.2:** subscribe the new Page to `messages`, `messaging_postbacks`, `feed`.
2. **Part 3.3:** change `PAGE_ID` in the query and get the new Page's token.
3. **Part 4:** add a new Messenger channel in Javis and paste `PAGE_ID PAGE_TOKEN APP_SECRET`.

Each Page is its own token and its own channel in Javis. One bot can serve several channels at once (several Pages, Zalo too), so there is no need for a bot per Page.

---

## Common errors

| What you see | Why | Fix |
|---|---|---|
| Javis says "Missing: Page ID, App secret" | Only the token was pasted | Paste all 3 things on one line (Part 4.2) |
| The bot answers messages but not comments | The token lacks the comment permissions, or the Page is not subscribed to `feed` | Check the token's Scopes (Part 3.2) and subscribe to `feed` (Part 2.2) |
| Customers write and the bot stays silent | The app is still in development mode, or no bot is on for this channel | Do Part 5; check under Chatbot, Bots that the bot is on |
| The permission popup only offers "messaging" | You used the "Add Page" button in Messenger API settings | Use Graph API Explorer (Part 3.1) |
| An old token stopped working | Generate was clicked again, or the Facebook password changed | Redo Part 3 and update the token in Javis |
| "Data access expires: in about 3 months" | Meta's rule for user data access | Open the app now and then, or redo Part 3.1 when asked |
