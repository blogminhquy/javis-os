# Connect a Facebook Page to Javis step by step (messages and comment replies)

*[Tiếng Việt](../31-messenger-tung-buoc.md) · **English***

This guide walks through every click on Meta's site, for people doing it the first time. The first setup takes about 20 minutes. Each extra Page later takes about 2 minutes.

> **Everything in Javis happens in one place:** the **Facebook Messenger** card on the **Connections** page. It has a **Log in with Facebook** button (the quickest way, see [31 - Messenger](31-messenger.md)) and a **Paste a token instead** section (this guide). Once a Page is connected there it is already in the channel list on the Chatbot page; there is nothing to add again.

Before you start you need:

- Javis reachable through an **HTTPS domain** (Settings, Remote access). Meta does not send messages to localhost or an IP address.
- A Facebook account that is an **admin** of the Page.
- A Meta app of your own. If you have none, do Part 0 below. If you already have one (for example the app made for the Facebook Pages card in the store), reuse it and skip Part 0: one app serves all your Pages.

> **Security:** anyone with the token or the App secret controls the Page. Never send them to anyone, and do not take screenshots while a token is visible.

---

## Overview

0. Create a Meta app (only if you have none)
1. Prepare the Meta app (add Messenger and the comment permissions)
2. Get a token in Graph API Explorer
3. Paste it into the Facebook Messenger card on the Connections page (Javis registers the webhook and subscribes the Page)
4. Attach a bot
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

**Find the Page ID:** open the Page, go to **About, Page transparency**; the **Page ID** line is a number. Or in Graph API Explorer (Part 2), type `me/accounts?fields=name,id` and click Submit to see every Page ID.

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

## Part 2. Get a token in Graph API Explorer

> Do not use the **Generate** button in section 2 of Messenger API settings: that token can only send messages and cannot reply to comments.

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
- Copy the `EAA...` string in the **Access Token** box.

This token lives about an hour, which is fine: in Part 3 Javis turns it into a **Page token that never expires**. You do not need to extend it or fetch the Page token yourself.

---

## Part 3. Paste it into the Facebook Messenger card on the Connections page

**3.1. Get the App ID and App secret**

- In your app: **App settings, Basic**.
- **App ID** is the App ID. In the **App secret** field click **Show**; that is the App secret (32 characters).
- One app serves every Page, so both can be reused for later Pages.

**3.2. Connect**

- Open Javis through its HTTPS domain, go to **Connections**, card **Facebook Messenger**, click **Connect**.
- Fill in the **App ID** and **App secret**.
- Click **Paste a token instead**, fill in the **Page ID** and paste the **token** you copied in Part 2.
- Click **Connect and check**.

Javis does the rest: it gets a non-expiring Page token, registers the webhook in the Meta app, subscribes the Page to `messages`, `messaging_postbacks` and `feed`, and shows a checklist row by row. A red row has its fix right under it, or click **Repair**.

---

## Part 4. Attach a bot

- Open **Chatbot, Bots**, create a bot or edit one.
- Tick the Messenger channel you just connected (it is already in the list, no need for **Add channel**), click **Save** and switch the bot on.
- For the bot to answer comments too: in the list of Pages on the Messenger card, set Page comments to **The bot replies publicly**. By default comments only show in the inbox for you to answer.

---

## Part 5. Switch the app to Live

In development mode the bot only answers people with a role on the app (admin, developer, tester). To answer real customers:

**5.1. Fill in the required details**

In your app: **App settings, Basic**:

- **Privacy Policy URL:** copy the **Privacy policy link** on the Messenger card (shaped like `https://<your-javis-domain>/messenger/privacy`) and paste it here and into User data deletion.
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

## When the checklist shows the webhook red: do it by hand

Javis usually registers it by itself. Only do this when the **App webhook** or **Page is subscribed to the app** row is still red after **Repair**.

In the Meta app: **Use cases, Messenger from Meta, Customize, Messenger API settings**.

**Configure webhooks (section 1)**

- **Callback URL:** copy the **Webhook address** on the Messenger card on the Connections page.
- **Verify token:** copy the **Verify token** right under it on the same card.
- Click **Verify and save**. A green tick means done.

**Subscribe the Page (section 2)**

- On the Page's row, click **Add subscriptions** (or "View all fields", **Edit**).
- Tick exactly 3 fields: `messages`, `messaging_postbacks`, `feed`. Click **Confirm**.

> Do not tick everything. Extra fields (calls, standby, messaging_handovers...) send events Javis does not handle and only add noise.

Then go back to the Messenger card and click **Check** on that Page.

---

## Adding another Page (about 2 minutes each)

1. Get a fresh token in Part 2 (the old one lives about an hour). If you opted in to all current and future Pages, nothing else changes.
2. Redo Part 3.2 with the new **Page ID**. The App ID and App secret stay the same.
3. In Part 4, tick the new channel on the bot you already have.

Or click **Log in with Facebook** on the Messenger card and tick several Pages at once.

Each Page is its own channel in Javis. One bot can serve several channels at once (several Pages, Zalo too), so there is no need for a bot per Page.

---

## Common errors

| What you see | Why | Fix |
|---|---|---|
| Javis says the token expired | The Part 2 token lives about an hour | Click Generate Access Token for a new one and paste it right away |
| Javis says the token was made in another app | The wrong app was picked in Graph API Explorer | Pick the right app under Meta App and generate the token again |
| The bot answers messages but not comments | The token lacks the comment permissions, or Page comments is set to "Show in the inbox" | Get a token with all 6 permissions (Part 2); set Page comments to "The bot replies publicly" |
| Customers write and the bot stays silent | The app is still in development mode, or no bot is on for this channel | Do Part 5; check under Chatbot, Bots that the bot is on |
| The permission popup only offers "messaging" | You used the "Add Page" button in Messenger API settings | Use Graph API Explorer (Part 2) |
| The checklist shows the webhook red | Javis could not register the webhook in the app | Click Repair; if it stays red, follow "When the checklist shows the webhook red" |
