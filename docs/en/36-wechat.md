# 36 - WeChat (Official Account)

*[Tiếng Việt](../36-wechat.md) · **English***

A dedicated bot can answer the people who write to your **WeChat Official Account** (the business account followers subscribe to), just like a bot on Zalo OA, Messenger or Telegram: the same Agent, the same brain, the same duty hours, every chat in the Inbox, and you can take over when a human is needed.

## WeChat has several doors. Why Javis uses the Official Account

| Door | Who can write to the bot | What it needs | Javis |
|---|---|---|---|
| **Official Account** (this guide) | Every WeChat user who follows the account | A verified account, a public domain | Yes, the **WeChat** channel |
| **WeChat ClawBot** (Tencent's iLink Bot API, 2026) | Only the person who scanned the QR code | A personal WeChat | Not yet. It is a personal assistant, not a customer channel |
| **WeCom customer service** | WeChat users who open the company's link | A verified WeCom company | Not yet |
| Personal account through unofficial tools | Anybody | Software that works around the protocol | No. Against WeChat's terms, and accounts get banned |

A chatbot is for CUSTOMERS to write to, so only the Official Account fits. Javis uses WeChat's official API (`api.weixin.qq.com`).

| | WeChat Official Account |
|---|---|
| How Javis connects | Webhook: WeChat calls Javis, **a public address is required** on port 443 (https) or 80 |
| Groups | No, private chats with the account only |
| Files | Receives text, images, voice, locations, links. Sends text and JPG/PNG/GIF images (up to 10MB). Cannot send documents |
| Voice | Transcribed (WeChat's own recognition when present, otherwise a Groq key on the Models page) |
| Replies | As "customer service messages", only within 48 hours of the follower's last message |
| Formatting | Plain text, 2048 bytes per message. Javis strips Markdown and splits long answers |
| Customer names | WeChat no longer lets an account read them. A customer shows as an OpenID |

## 1. What you need

- **A verified Official Account.** WeChat lets only verified accounts send customer service messages through the API. A company outside China can register a Service Account, with a yearly verification fee. On an unverified personal account the bot receives messages but cannot answer (error 48001).
- **To try it first:** use the free **sandbox test account** at [mp.weixin.qq.com/debug/cgi-bin/sandbox?t=sandbox/login](https://mp.weixin.qq.com/debug/cgi-bin/sandbox?t=sandbox/login). Scan with WeChat and you get an AppID, an AppSecret and every API permission at once. Up to 100 followers.
- **Javis reachable from the Internet** on a domain (see [guide 15](15-branding-and-domains.md)), on a machine with a **fixed outbound IP**: WeChat hands an access token only to an IP on the account's whitelist.

## 2. Get the address and the Token from Javis

1. Open Javis **through its domain**, go to **Chatbot**, tab **Bots**, click **Add channel** and choose **WeChat**.
2. The form shows two lines: the **Webhook address** (like `https://<domain>/wechat/webhook`) and the **Verify token**. That token is the **Token** field on WeChat. Javis generates it once for the machine and checks the signature of every message with it.

## 3. Configure WeChat

On [mp.weixin.qq.com](https://mp.weixin.qq.com), under **Settings and Development**, **Basic Configuration** (设置与开发, 基本配置). If you do not see it, WeChat may have moved it to its developer site; the field names are the same.

1. Copy the **AppID**, and create and copy the **AppSecret** (WeChat shows the AppSecret once).
2. **IP whitelist** (IP白名单): add the outbound IP of the machine running Javis. If you do not know it, go on: when you click Check, Javis tells you exactly which IP to add.
3. **Server Configuration** (服务器配置), click edit:
   - **URL**: paste the Webhook address from Javis.
   - **Token**: paste the Verify token from Javis.
   - **EncodingAESKey**: click to generate a random one and copy it.
   - **Message encryption**: choose **Safe mode** (安全模式).
4. Click **Submit**. WeChat calls Javis right then, and reports success when the Token matches. Then click **Enable** (启用).

The sandbox test account has no EncodingAESKey field: fill in the URL and the Token only, and it runs in Plaintext mode.

## 4. Add the WeChat account in Javis

1. In the Token field of **Add channel**, **WeChat**, paste these separated by spaces (any order, Javis tells them apart by shape):

   ```
   <AppID> <AppSecret> <EncodingAESKey>
   ```

   Leave out the EncodingAESKey when you run Plaintext mode.
2. Click **Check**. Javis asks for one access token: passing means the AppID and AppSecret are right and the IP is on the whitelist.
3. Click **Save**, then go to **Chatbot**, **Bots** to create a bot or attach an existing one to this channel. Once the bot is on, it answers.

## 5. Why Safe mode

In Plaintext mode WeChat's signature covers the Token, the time and a random number, **not the message itself**. Whoever captures one valid call address could attach a forged message to it. Safe mode encrypts the message with AES and signs the ciphertext, so it cannot be forged.

Javis adds two rules: a request whose time is more than 15 minutes old is refused, and an account that was given an EncodingAESKey **accepts encrypted messages only**.

**Several accounts in Plaintext mode:** an unencrypted message names the account only by its Original ID (`gh_...`), so Javis cannot tell which account it is for. Add the Original ID at the end of each account's credentials (`<AppID> <AppSecret> gh_...`), or use Safe mode. With one account nothing is needed.

## 6. WeChat limits worth knowing

- **Five seconds:** WeChat wants the server to answer within 5 seconds, and an Agent turn usually takes longer. So Javis acknowledges at once and sends the answer afterwards through the customer service message API. The follower sees the answer as usual.
- **48 hours:** once 48 hours have passed since the follower's last message, nothing can be sent. The window reopens when they write again.
- **A limited number of replies per incoming message.** Javis packs an answer into as few messages as it can; a very long answer split into many messages can hit the cap.
- **Events** such as follow, menu click and QR scan start no turn. The bot answers only when a follower writes.

## 7. When the bot is silent

- **Error 40164, IP not on the whitelist:** the error names the IP. Add it to the IP whitelist in step 3. A machine whose IP changes has to be added again, so use a VPS with a fixed IP.
- **Error 48001, API not authorised:** the account is not verified. Verify it, or try with the sandbox test account.
- **Error 40125 or 40001:** the AppSecret is wrong, or was reset. Edit the channel and paste the new AppSecret.
- **Error 45015:** the follower has not written for more than 48 hours.
- **Error 45047:** the replies WeChat allows after the follower's message are used up. Wait for their next message.
- **WeChat says "Token verification failed" on Submit:** the URL must be exactly the address Javis shows, the Token exactly the Verify token, and Javis must be reachable from the Internet.
- **The bot card says "WeChat is sending unencrypted messages":** you gave Javis an EncodingAESKey while WeChat runs Plaintext mode. Switch WeChat to Safe mode, or remove the EncodingAESKey in Javis.
- **Followers see "this account's service is unavailable":** Javis did not answer WeChat in time. Check that the Javis server is running and the domain still points to it.
