# 35 - Zalo OA (Official Account)

*[Tiếng Việt](../35-zalo-oa.md) · **English***

From 0.412.0 a dedicated bot can answer the inbox of a **Zalo Official Account** (the business page customers follow), just like a bot answering on Zalo Bot, Messenger or Telegram: same Agent, same brain, same hours, every chat in the Inbox, and a person can take over when needed.

This channel is different from the two Zalo channels Javis already had:

- **Zalo Bot** (guide 26): a bot made in "Zalo Bot Manager", whose name must start with Bot. No domain needed.
- **Personal Zalo** (guide 12): your own Zalo account, signed in with a QR code.
- **Zalo OA** (this guide): your business Official Account, through Zalo's official OA Open API v3.

| | Zalo OA |
|---|---|
| How Javis connects | Webhook: Zalo calls Javis, **needs an HTTPS domain** |
| Groups | No, private chats with the OA only |
| Files | Receives images, files, voice. Sends JPG/PNG/GIF images (up to 1MB) and PDF, DOC, DOCX (up to 5MB) |
| Voice messages | Transcribed (needs a Groq key on the Models page) |
| Replies | As "consultation messages", only within the window Zalo allows after the customer's last message |
| Formatting | Plain text: Zalo shows no Markdown, Javis strips the symbols |

## 1. Create an app on Zalo for Developers (once)

1. Open [developers.zalo.me](https://developers.zalo.me), sign in with the OA admin account, choose **Create app**.
2. In the app, under **Official Account**, link your OA to the app.
3. Copy the **App ID** and the **App secret key** from the app information page.

## 2. Verify the domain and set the webhook

Zalo only delivers to an HTTPS address on a verified domain.

1. Open Javis **through its HTTPS domain**, go to **Chatbot**, **Bots**, choose **Add channel**, pick **Zalo OA**. The form shows the **Webhook address** and a **Zalo domain verification code** box.
2. On Zalo, under **Domain verification**, enter Javis's domain and choose verification by **HTML file**. Zalo gives a file name like `zalo_verifier<code>.html`.
3. Paste that file name (or the meta tag Zalo shows) into Javis's box and press **Save code**. Javis now serves that exact file. Go back to Zalo and press **Verify**.
4. Open the app's **Webhook** section, paste the **Webhook address** Javis shows (like `https://<domain>/zalo-oa/webhook`) and enable the events **user_send_text**, **user_send_image**, **user_send_file**, **user_send_audio**, **user_send_sticker**, **user_send_location**.
5. The Webhook section also shows the **OA secret key**. Copy it: Javis checks the signature of every event with it and drops anything not signed with it.

## 3. Register the Callback URL for OAuth v4 (once)

Zalo moved OA authorization to **OAuth v4** (an authorization code with PKCE). Javis runs that flow, so you no longer copy a refresh token by hand.

1. In **Add channel**, **Zalo OA**, Javis shows the **Callback URL**, like `https://<domain>/zalo-oa/oauth/callback`.
2. On developers.zalo.me, in the app, under **Official Account**, paste that address into **Callback URL** and save. The domain must be the one you verified in step 2.

## 4. Add the Zalo OA account in Javis

### The quick way: Grant access with Zalo (OAuth v4)

1. In the Token field of **Add channel**, **Zalo OA**, paste three things separated by spaces:

   ```
   <App ID> <App secret key> <OA secret key>
   ```

   To be sure about the order of the two short keys, name them: `app_secret=...` and `oa_secret=...`.
2. Click **Grant access with Zalo**. A Zalo tab opens: pick the right OA and click **Allow**. The tab closes by itself.
3. Javis exchanges the grant code for an access token and a refresh token, reads the OA name and saves the channel by itself. No Check or Save needed.
4. Go to **Chatbot**, **Bots** to create a bot or put an existing one on duty for this channel. Once the bot is on, it answers customers who message the OA.

An access token lives about 25 hours and a refresh token about 3 months, and each works **once**. Javis refreshes by itself and saves every new pair straight away in the encrypted account store, so a bot that keeps running never needs a new grant.

**Grant again:** if the refresh token dies (Javis was off for over 3 months, or you revoked the app), open **Edit** on the Zalo OA channel and click **Grant access again with Zalo**. Javis uses the saved keys, so the Token field can stay empty. A bot on duty restarts with the new pair.

### The old way: paste a refresh token from API Explorer

Still works if you have not registered the Callback URL.

1. Open **API Explorer** on developers.zalo.me (under Tools), pick **OA Access Token**, the right app and OA, request the token, allow the app to access the OA and copy the **Refresh token**.
2. In the Token field, paste four things: `<App ID> <App secret key> <OA secret key> <Refresh token>`.
3. Click **Check**, then **Save** right after. The check spent the refresh token you pasted; the new pair waits in Javis for about 30 minutes and is written to the account when you save.

## 5. When the bot stays silent

- **The bot reports a missing OA secret key:** Javis will not start the bot without it, because every event would fail its signature check unnoticed. Edit the channel and paste the keys again.
- **The Zalo page reports a wrong redirect_uri / callback:** the Callback URL on the Zalo app must match exactly the address Javis shows on the form (step 3), and you must open Javis through that same domain.
- **"Zalo could not refresh the token":** the refresh token is wrong, already used, or older than 3 months. Open Edit on the channel and click **Grant access again with Zalo**.
- **Error -230 or "the customer has not written for too long":** Zalo only lets the OA reply within a window after the customer's last message. It reopens when they write again.
- **Error -224:** the OA's service package does not allow this through the API. Check the package on [oa.zalo.me](https://oa.zalo.me).
- **No messages arrive at all:** check the webhook points to Javis's HTTPS address and the user_send_* events are on. Zalo drops a webhook that fails several times in a row; turn it back on in the app page.

Javis cannot read OA messages from before the connection: the Inbox starts with the first event that arrives through the webhook.
