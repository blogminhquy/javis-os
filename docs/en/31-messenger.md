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
- To answer **everyone**, the app needs Meta's **App Review** for the **pages_messaging** permission (usually with business verification and a public privacy policy page), then switch the app to **Live**. Until then, messages from the public still land in the inbox but Meta blocks the bot's replies; the bot card shows the error and why.

## Common errors

| Javis says | Meaning | Fix |
|---|---|---|
| more than 24 hours since this person last wrote | The customer wrote over a day ago | Wait for them to write again, or answer from Meta Business Suite |
| the app may not message people outside it yet (200) | App Review not passed | Test with an account that has a role on the app, or submit pages_messaging for review |
| the Page access token expired or is wrong (190) | Temporary or revoked token | Generate a new one (step 1.3) and paste it again on the channel account |
| Javis could not subscribe the Page to the webhook | Token lacks pages_manage_metadata | The bot still runs if the Page was subscribed by hand; otherwise click Add Subscriptions for the Page under Messenger, Webhooks, or generate the token again while you are a Page admin |
| The App secret does not belong to the app this Page access token was made in | App secret copied from another app | Copy the App secret again from App settings, Basic of the app that made the token. With a wrong secret Javis cannot trust the signature on Meta's messages, so it refuses it when you save |
| Meta cannot verify the webhook | Callback URL is not HTTPS, or wrong token | Open Javis through its HTTPS domain and copy the address from the form again |
