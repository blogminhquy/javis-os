# 30 - Discord and Lark/Feishu

*[Tiếng Việt](../30-discord-lark.md) · **English***

Since 0.85.0 you can talk to Javis right inside Discord and Lark (or Feishu, Lark's mainland China edition). Both are **admin channels**: the person messaging is you, with the same power as the dashboard (your brain, tools, background work). Set them up on the **Admin channels** page, one tab per channel.

Bots that answer **customers** are a different thing, on the **Chatbot** page. Discord and Lark are not available there yet.

| | Discord | Lark / Feishu |
|---|---|---|
| How Javis connects | Gateway: Javis opens the connection, **no domain needed** | Persistent connection: Javis opens the connection, **no domain needed** |
| What you need | A bot token | App ID and App Secret of a custom app |
| In groups | Javis answers when @mentioned or when you reply to the bot | Javis answers when @mentioned |
| Files | Images and documents, both ways (10 MB max when sending) | Images and documents, both ways |
| Voice messages | Transcribed (needs a Groq key on the Models page) | Transcribed (same) |
| Bot commands | `!stop`, `!new`... (Discord keeps `/` for its own commands) | `/stop` or `!stop` both work |

Both channels are **locked by default**: until you allow someone, nobody can use them. A stranger who messages the bot gets a 4-digit pairing code and shows up on that channel's tab; click **Allow** and you are done. No hunting for IDs by hand.

---

## Discord

### 1. Create the bot (once, about 3 minutes)

1. Open [discord.com/developers/applications](https://discord.com/developers/applications), click **New Application**, name it (for example "Javis").
2. Open **Bot**, click **Reset Token**, copy the token. It is shown only once; if you lose it, reset again.
3. Open **OAuth2** → **URL Generator**: tick the **bot** scope, then the **View Channels**, **Send Messages**, **Read Message History** and **Attach Files** permissions. Open the generated link to invite the bot to your server.

There is no need to turn on **Message Content Intent** or any privileged intent. Javis only reads direct messages to the bot and messages that @mention it, and Discord delivers the full text of both without that intent.

### 2. Connect it to Javis

1. **Admin channels** page → **Discord** tab: paste the token into **Bot token**, click **Save and turn on**.
2. The label next to the channel name turns **Running**.
3. DM the bot once on Discord (you must share at least one server with it). The bot replies with a pairing code, and the Discord tab shows your name with that same code. Click **Allow**.
4. Click **Send a test** to make sure messages from Javis get through too.

In a server channel, type `@Javis your question`: Javis answers right below, as a reply to your message. Conversation between people in the channel that does not @mention the bot is ignored.

### Common problems

- **"Discord rejected the bot token"**: the token is wrong, or you clicked Reset Token after copying it. Reset, paste the new one, Save.
- **"The bot asks for an intent that is not enabled"**: does not happen with this version. If you see it, you are running something older than 0.85.0.
- **The test cannot open a DM**: the allowed person must share a server with the bot and accept direct messages from server members.
- **The bot is silent in a channel**: it lacks **View Channels** or **Send Messages** there. Check the bot role's permissions in the channel settings.

---

## Lark / Feishu

Lark (open.larksuite.com) and Feishu (open.feishu.cn) are separate platforms: an app made on one does not exist on the other. Businesses outside mainland China almost always use **Lark**, and that is the default in the **Platform** field.

### 1. Create the app (once, about 5 minutes)

1. Open the developer console: [open.larksuite.com/app](https://open.larksuite.com/app) for Lark, [open.feishu.cn/app](https://open.feishu.cn/app) for Feishu. Click **Create Custom App** and name it.
2. **Add features**: add **Bot**.
3. **Permissions & Scopes**: add the permissions to read direct messages to the bot, read group messages that @mention the bot, send messages as the bot, and read files in messages (search for `im:message` and `im:resource`).
4. **Credentials & Basic Info**: copy the **App ID** (looks like `cli_...`) and the **App Secret**.

### 2. Connect it to Javis, then turn on events

The order matters: the Lark console only lets you save "persistent connection" mode while a connection is open, so turn Javis on first.

1. **Admin channels** page → **Lark** tab: pick the **Platform** (Lark or Feishu), paste the **App ID** and **App Secret**, click **Save and turn on**. The label turns **Running**.
2. Back in the console, **Events & Callbacks**: choose **Receive events through persistent connection** and save. Click **Add Events** and add **Message received** (`im.message.receive_v1`).
3. **Version Management & Release**: create a version and publish it. If your company has an admin, they need to approve it.
4. In Lark, find the bot by name and DM it once. The bot replies with a pairing code, the Lark tab shows you with that code: click **Allow**.

In a group, add the bot to the group and type `@Javis your question`. Javis answers right under that message. While it works, Javis puts an "on it" reaction on your question, since Lark has no typing indicator for bots.

### Common problems

- **"Lark refused the App ID / App Secret"**: a character is missing, or the platform is wrong (a Lark app with Platform set to Feishu, or the other way round).
- **Running, but messages get no answer**: the `im.message.receive_v1` event is not added, persistent connection mode is not selected, or no new version was published after changing permissions. Every permission change needs a new release.
- **"Lark refused the connection ... too many connections"**: another Javis is connected with the same app. Use one app per Javis.
- **The test fails with "this user cannot see the bot"**: the app's availability does not include that person. Fix the user scope when publishing.
