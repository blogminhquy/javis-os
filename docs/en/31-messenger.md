# 31 - Messenger (Facebook Page)

*[Tiếng Việt](../31-messenger.md) · **English***

From 0.134.0 a dedicated bot can answer a Facebook Page's inbox, the same way a bot answers on Zalo or Telegram: same Agent, same brain, same active hours, every chat in the inbox, and a human can take over when needed.

| | Messenger |
|---|---|
| How Javis connects | Webhook: Meta calls Javis, **needs an HTTPS domain** |
| Groups | No, private chats with the Page only |
| Files | Images and documents, both ways |
| Voice notes | Transcribed (needs a Groq key on the Models page) |
| Replies | Only within 24 hours of the customer's last message |
| Formatting | Plain text: Messenger shows no Markdown, Javis strips the symbols |
| Page comments | Yes (from 0.434.0): every top-level comment is a conversation in the inbox |

## Quickest way: the Log in with Facebook button (from 0.434.0)

No Graph API Explorer, no Page ID or token to copy. First time, and want every click on Meta's site: [Messenger step by step](31-messenger-step-by-step.md).

1. On [developers.facebook.com/apps](https://developers.facebook.com/apps), create an app with the Messenger use case (once, step 1.1 below).
2. Open Javis through its HTTPS domain, go to **Connections**, card **Facebook Messenger**, click **Connect**. The form shows two addresses with a **Copy** button:
   - **Redirect address**: paste it into **Valid OAuth Redirect URIs** in the app's Facebook Login settings.
   - **Privacy policy link**: Javis serves this page itself. Paste it into **App settings, Basic**, Privacy Policy URL and User data deletion.
3. Paste the **App ID** and **App secret**, pick how comments are handled, click **Log in with Facebook**. A Facebook tab opens: sign in, tick the Pages, accept the permissions.
4. Back on the Javis tab the Page list appears: tick the Pages to connect and click **Connect the ticked Pages**. Javis gets a non-expiring Page token, registers the webhook, subscribes each Page to the app and shows a checklist per Page.
5. Switch the app to **Live** (section 4), then open **Chatbot**, **Bots** to create a bot for the new channel.

## Page comments (from 0.434.0)

The way Pancake shows them: **every top-level comment under a post is its own conversation** in the inbox, and the replies under that comment join the same conversation. The conversation title quotes the start of the post. What you type in the inbox shows **publicly right under the top-level comment** on Facebook. An image can go with it, other files cannot (a comment only takes images).

Each Page picks one of three modes, on the connect form or in the list of connected Pages:

- **Show in the inbox, you reply** (default): comments land in the inbox, the bot does not answer them. Asking the bot to draft a reply works as in any other conversation.
- **The bot replies publicly**: the bot answers like a message, told that everyone can read the reply, so it keeps it short, shares nothing private and invites the person to message the Page when needed.
- **Off**: comments are ignored.

Comments need two more permissions, `pages_read_user_content` and `pages_manage_engagement` (Log in with Facebook asks for both). The checklist has a **Receives Page comments** row: yellow means a permission is missing or the Page does not send comments to Javis yet; log in with Facebook again, then click **Repair**. Without the comment permissions Messenger messages keep working.

## Pasting a token (from 0.311.0)

The step people get wrong is the token: a user token pasted where a Page token belongs (error 100, error 210), a short-lived token that dies within the hour, or a webhook saved without the `messages` field so the bot stays silent. This card does those steps for you.

1. On Meta, create an app with the Messenger use case and connect the Page (steps 1.1 to 1.3 below, no need to click Generate yet).
2. Open [Graph API Explorer](https://developers.facebook.com/tools/explorer), pick the right app, add `pages_show_list`, `pages_messaging`, `pages_manage_metadata`, `pages_read_engagement`, click **Generate Access Token** and tick the right Page. Copy the `EAA...` string.
3. Open Javis through its HTTPS domain, go to **Connections**, card **Facebook Messenger**, click **Connect**, then **Paste a token instead**. Paste the App ID, App secret, Page ID and the token, then click **Connect and check**.
4. Javis derives a non-expiring Page token, registers the app webhook with `messages` and `messaging_postbacks`, subscribes the Page to the app, saves the channel and shows a checklist with a fix for every red row.
5. Open **Chatbot**, **Bots** to create a bot for the new channel (section 3).

Every connected Page has **Check**, **Repair** (registers the webhook and subscribes the Page again) and **New token** buttons. Any brain can call the `messenger_check` and `messenger_repair` tools when the bot goes silent. Business verification and App Review for `pages_messaging` (section 4) still happen on Meta's site.

The manual steps below still work.

## 1. Create a Meta app (once)

1. Open [developers.facebook.com/apps](https://developers.facebook.com/apps) and click **Create app**. Pick the use case for messaging customers on Messenger and connect it to your Business portfolio.
2. In the app, go to **Messenger → Messenger API settings**.
3. Under **Generate access tokens**, click **Connect** (or **Add Page**), pick your Page, then **Generate** to get the **Page access token**. Copy it.
4. Go to **App settings → Basic** and click **Show** next to **App secret**. Copy it.
5. Get the **Page ID**: it shows next to the Page name in step 3, or under About → Page transparency on the Page.

## 2. Add the Messenger account in Javis

1. Open Javis **through its HTTPS domain** (not localhost or an IP), go to the **Chatbot** page, **Bots** tab, click **Add a channel**, choose **Messenger**.
2. The form shows a **Webhook address** and a **Verify token**. Back in the Meta app, under Messenger's **Configure webhooks**, paste them as the Callback URL and Verify token and click **Verify and save**. Tick the **messages** and **messaging_postbacks** fields.
3. Back in Javis, paste three things separated by spaces into the token field: `Page ID`, `Page access token`, `App secret`. Click **Check** (Javis asks Meta for the Page name), then **Save**.

## 3. Attach a bot

- **Reuse the bot already on Zalo:** open it on the Chatbot page, click **Edit**, tick the new Messenger account, **Save**. The bot answers on Zalo and Messenger with the same Agent and the same active hours.
- **Or create a new bot** for Messenger only.

Switch the bot on. Javis then subscribes the Page to the app's webhook by itself (no manual step); any error shows on the bot card in words. If the token lacks the permission to subscribe, the bot still runs and its card reminds you to subscribe the Page once by hand: Meta app, Messenger, Webhooks, **Add Subscriptions** for the Page.

## 4. Test, then open it to everyone

- While the app is in development mode, **only people with a role on the app** (admin, developer, tester) get replies. Test with your own Facebook account: send the Page a message.
- To answer **everyone**, switch the app to **Live**. Meta asks for a privacy policy link: use the **Privacy policy link** Javis shows on the connect form.
- Meta's documentation says an app that only messages **your own Page** needs no App Review. Some people still see the bot blocked when replying to strangers after going Live, so test with **a Facebook account that has no role on the app**. If Meta still blocks it, submit **App Review** for **pages_messaging** (usually with business verification). Meanwhile messages from the public still land in the inbox; the bot card shows the error and why.

## Common errors

| Javis says | Meaning | Fix |
|---|---|---|
| more than 24 hours since this person last wrote | The customer wrote over a day ago | Wait for them to write again, or answer from Meta Business Suite |
| the app may not message people outside it yet (200) | The app is still in development mode, or Meta wants App Review | Switch the app to Live (section 4); if it persists, submit pages_messaging for review |
| Facebook reports a blocked URL when signing in | The Redirect address is not in the app | Copy the Redirect address from the form into Valid OAuth Redirect URIs of Facebook Login |
| the app may not reply to comments yet | pages_manage_engagement is missing | Log in with Facebook again and accept every permission |
| the Page access token expired or is wrong (190) | Temporary or revoked token | Generate a new one (step 1.3) and paste it again on the channel account |
| Javis could not subscribe the Page to the webhook | Token lacks pages_manage_metadata | The bot still runs if the Page was subscribed by hand; otherwise click Add Subscriptions for the Page under Messenger, Webhooks, or generate the token again while you are a Page admin |
| The App secret does not belong to the app this Page access token was made in | App secret copied from another app | Copy the App secret again from App settings, Basic of the app that made the token. With a wrong secret Javis cannot trust the signature on Meta's messages, so it refuses it when you save |
| Meta cannot verify the webhook | Callback URL is not HTTPS, or wrong token | Open Javis through its HTTPS domain and copy the address from the form again |
