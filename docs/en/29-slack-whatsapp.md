# 29 - Slack and WhatsApp

*[Tiếng Việt](../29-slack-whatsapp.md) · **English***

Since 0.71.0 Javis talks on Slack and WhatsApp, in the same two ways as Telegram and Zalo:

- **Control channel:** you chat with Javis itself (your brain, your tools, background work). Set it up on the **Admin channels** page.
- **Customer bot:** a dedicated agent answers your customers or team, with every chat in the shared inbox and takeover when a human is needed. Set it up on the **Chatbot** page.

| | Slack | WhatsApp |
|---|---|---|
| How Javis connects | Socket Mode: Javis opens the connection, **no domain needed** | Webhook: Meta calls Javis, **needs an HTTPS domain** |
| Groups | Channels (Javis answers when mentioned, in the thread) | Private chats only |
| Files | Images and documents, both ways | Images and documents, both ways |
| Voice messages | Transcribed (needs a Groq key on the Models page) | Transcribed (same) |
| Writing first | Anytime | Only within 24 hours of the person's last message |

---

## Slack

### 1. Create the Slack app (once, about 3 minutes)

1. Open [api.slack.com/apps](https://api.slack.com/apps), click **Create New App**, choose **From an app manifest**, pick your workspace.
2. Paste this manifest (YAML), then **Create**:

```yaml
display_information:
  name: Javis
features:
  bot_user:
    display_name: Javis
    always_online: true
  app_home:
    messages_tab_enabled: true
    messages_tab_read_only_enabled: false
oauth_config:
  scopes:
    bot:
      - app_mentions:read
      - chat:write
      - im:history
      - im:read
      - im:write
      - channels:history
      - groups:history
      - files:read
      - files:write
      - users:read
settings:
  event_subscriptions:
    bot_events:
      - app_mention
      - message.im
      - message.channels
      - message.groups
  socket_mode_enabled: true
  org_deploy_enabled: false
  token_rotation_enabled: false
```

3. **Basic Information → App-Level Tokens → Generate Token and Scopes**: add the scope `connections:write`, generate, copy the token that starts with `xapp-`.
4. **Install App → Install to Workspace**, then copy the **Bot User OAuth Token** that starts with `xoxb-`.

### 2a. Control channel (you talk to Javis)

1. **Admin channels** page → **Slack** tab: paste the bot token and the app token, click **Save and turn on**.
2. Open Slack, find the app under **Apps**, send it any message. You appear on the card with a 4-digit code; check the code and click **Allow**. The list starts empty on purpose: nobody can reach your brain until you allow them.
3. From then on: DM the bot, or mention `@Javis` in a channel it was invited to (`/invite @Javis`); it answers in the thread.

Bot commands start with `!` instead of `/` on Slack, because Slack keeps `/` for its own commands: `!stop`, `!new`.

### 2b. Customer bot

1. Use a **separate** Slack app (repeat step 1 with another name) so customers never reach your control channel.
2. **Chatbot** page → **Accounts** → add an account, channel **Slack**, paste both tokens **separated by a space**: `xoxb-... xapp-...`.
3. Create the bot on the same page and attach the account.

---

## WhatsApp

WhatsApp only works through Meta's official **WhatsApp Business Cloud API**. Javis never logs into a personal WhatsApp account (that breaks WhatsApp's terms and gets numbers banned).

### Before you start

- Javis must be reachable over **HTTPS on a domain** (a VPS with a domain, see [DEPLOY.en.md](../../DEPLOY.en.md)). Meta refuses plain `http://` and IP addresses.
- When no login password is set, the domain must be one Javis knows (your custom domain, see [15 - Branding and domains](15-branding-and-domains.md), or `JAVIS_ALLOWED_HOSTS`), otherwise Javis answers Meta with 403.
- Meta may charge for some conversations; check their current pricing page.

### 1. Create the Meta app (once)

1. [developers.facebook.com](https://developers.facebook.com) → **My Apps → Create App** → type **Business** → add the **WhatsApp** product.
2. **WhatsApp → API Setup**: note the **Phone number ID** (an ID, not the phone number). The free test number can only message up to 5 numbers you verify there; add a real number for production.
3. A **permanent access token**: Business Settings → **Users → System users** → add one, assign your app with full control, **Generate token** with `whatsapp_business_messaging` and `whatsapp_business_management`. (The token on the API Setup page dies after 24 hours.)
4. **App settings → Basic**: show and copy the **App secret**. Javis uses it to check that every webhook call really comes from Meta.

### 2a. Control channel

1. **Admin channels** page → **WhatsApp** tab: fill in Phone number ID, Access token, App secret, click **Save and turn on**.
2. The card shows a **Callback URL** and a **Verify token**. In Meta: **WhatsApp → Configuration → Webhook → Edit**, paste both, **Verify and save**, then subscribe to the **messages** field.
3. Message the business number from your own WhatsApp. You appear on the card with a code; click **Allow**.

### 2b. Customer bot

1. Use another number (each number belongs to one bot).
2. **Chatbot** page → **Accounts** → add an account, channel **WhatsApp**, paste the three values **separated by spaces**: `<phone number id> <access token> <app secret>`.
3. The webhook is the same Callback URL and Verify token as on the Admin channels page: one URL serves every number, and Javis routes each message by the number it was sent to.

### The 24-hour window

WhatsApp lets a business write freely only within **24 hours** of the person's last message. After that only pre-approved templates go through. In practice:

- Answers to messages are never affected.
- A background result (loop, Kanban task, reminder) that finishes more than 24 hours after you last wrote cannot be delivered on WhatsApp. It is not lost: every result also lands in the dashboard inbox (the bell). Send the bot any message to reopen the window.

---

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Slack card: `invalid_auth` | Wrong or revoked bot token. Reinstall the app and copy the new `xoxb-` token. |
| Slack card: app token refused | The `xapp-` token is missing `connections:write`, or Socket Mode is off. |
| Slack: no answer in a channel | Invite the bot (`/invite @Javis`) and mention it. |
| WhatsApp: Meta says the callback could not be verified | The URL is not HTTPS, the domain is not allowed, or the verify token was mistyped. |
| WhatsApp: messages arrive nowhere | The **messages** field is not subscribed, or the Phone number ID belongs to another number. |
| WhatsApp error 190 | The access token expired: use a System User token, not the 24-hour one. |
| WhatsApp error 131047 | Outside the 24-hour window, see above. |
