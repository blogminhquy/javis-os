# The Zalo Bot channel

*[Tiếng Việt](../26-kenh-zalo-bot.md) · **English***

Ask Javis right inside Zalo, with no dashboard and no Telegram install. You message a dedicated Zalo bot as you would message a person, and Javis answers with the very brain and memory running on your machine or VPS.

This channel uses Zalo's **official API**, so there is no risk of the account being locked.

## Do not confuse it with the two other Zalo things in Javis

Javis touches Zalo in three places. Read this table once and you never have to guess.

| | Page | Who it is | What it is for |
|---|---|---|---|
| **The Zalo Bot channel** (this page) | Channels | A dedicated bot | **You** messaging Javis |
| [Chatbot](25-chatbots.md) | Chatbot | A dedicated bot, under an Agent's name | **Customers** messaging Javis |
| [Zalo Agent MCP](12-zalo-agent-mcp.md) | Connections | Your own Zalo account | Javis **acting on your behalf** |

The first two use the official API and are safe, but they only see what people send directly to the bot. The third signs into your real account so it can read conversations and message anyone, at the cost of the account possibly being restricted or locked.

Running all three at once is fine, they do not collide.

## Getting the bot token

1. Open the Zalo app and find the Official Account **Zalo Bot Manager**.
2. In the chat, choose **Create bot**.
3. Name the bot. The name **must start with the word "Bot"**, for example "Bot Javis Của Tôi".
4. Zalo sends you the token by message, shaped `123456789:abc-xyz`.

The token **does not expire** until you reset it yourself in Zalo Bot Manager. Keep it private, because whoever has it controls the bot.

## Turning the channel on

1. Open the dashboard, the **Connections** group, the **Channels** item.
2. Scroll to the **Zalo** card.
3. Tick **Enable the Zalo bot** and paste the token into the Bot token field.
4. **Leave the "Allowed Chat IDs" field empty.** Click **Save and enable**.
5. Open Zalo on your phone, find the bot you just created, and send it any message.
6. The bot replies with a 4-digit **pairing code**.
7. Return to the Zalo card on the dashboard. You will see a **Waiting for your approval** block with your Zalo name and that exact code. Click **Allow**.
8. Message the bot again. This time Javis answers for real.

### Why the roundabout flow

Zalo offers no way to look up your own Zalo id, and that id is a string like `6ede9afa66b88fe6d6a9` rather than a readable number. So instead of making you hunt for it, Javis reverses the direction: whoever messages the bot appears on the dashboard with their **real Zalo name**, and one click is enough.

The pairing code is there so you can be sure you are approving the right person when two people share a name. Ask them to read the code from the bot's reply and compare.

### An empty Chat ID field means NOBODY is allowed

Javis **deliberately differs from Telegram** here, so do not be surprised.

In [Telegram](11-telegram.md), leaving the Chat ID field empty means anyone who finds the bot can use it, and the documentation has to warn you not to leave it empty. In Zalo, leaving it empty means **nobody is allowed yet**, and everyone who messages lands in a queue.

Without that, the very flow above would create a bot anyone could reach your brain through, during the window between enabling the bot and clicking Allow.

## What you can do over Zalo

Almost everything Telegram does: asking for figures through MCP, reading and writing files in the brain, calling skills, queueing background work, setting reminders. Every engine works because the tools go through the MCP Hub rather than being tied to one brain.

The quick commands (`/status`, `/reset`, `/stop`, `/model`, `/brain`, `/notes`...) work too, but **Zalo shows no command menu** as Telegram does, so you have to type them.

Results of background work and reminders set from Zalo **come back to that same Zalo chat**, never diverting to Telegram.

### Commanding by voice message

Hold the microphone in Zalo, speak, release. Javis turns that into text and acts exactly as if you had typed it.

**A Groq API key is required**, which is where Javis borrows speech-to-text (the Whisper model). In the dashboard, go to the **Models** page, the **Groq (API)** section, paste the key from [console.groq.com](https://console.groq.com) and save. Without it, sending a voice message makes Javis state plainly that the key is needed rather than going silent. Once pasted it works immediately, with no need to restart the bot.

It is **the same key as the Telegram channel**: attach it once and both channels can listen.

A few things to know:

- **Anything with an outside effect makes Javis confirm first.** Sending a message, publishing, booking a calendar slot, spending money, editing a file: Javis opens with a line "I heard: ..." then waits for your confirmation. Asking for figures, looking things up and summarising happen straight away.
- **The audio file is not saved into the brain.** Once heard and transcribed, it is done.
- If it cannot be transcribed, the file is too large, or Groq returns an error, the bot states the reason. There is no silent path.
- **One risk specific to Zalo:** Zalo has not published the data shape of voice messages, so Javis may fail to find the audio file's URL in the message Zalo sends. In that case the bot says outright that it could not download the file, and the server logs a line `[zalo voice] could not find the voice file path in the payload` with a data sample. Sending that line to the developer gets it fixed quickly. Telegram has no such risk because its data shape is clearly published.

## Four places where Zalo does less than Telegram

Stated up front so you do not mistake them for bugs.

**No status message.** Zalo allows neither editing nor deleting a sent message, so Javis cannot show a "calling a tool..." line and update it as it does on Telegram. While waiting you only see the "typing" dots. In exchange, the answer carries a trace line at the end such as `⚙ pos_statistics · Read · 8s` telling you which tools that turn touched.

**Documents cannot be sent.** The Zalo Bot API has no document-sending endpoint, so PDFs, spreadsheets and .docx cannot travel through this channel. Javis says plainly that it could not send and gives the path inside the brain for you to open, rather than swallowing the file silently. Images are experimental.

**A 2000-character ceiling per message** (Telegram's is 4096). A long answer is split into consecutive messages automatically.

**No buttons.** When Javis has to ask back for a parameter, it degrades to a question with a numbered list and you reply with the number.

## The Send test button

Click **Send test** to fire a test message to every allowed ID. It proves the token and Chat ID are right, it does **not** prove the bot is receiving messages. To know that, read the status line, which must say **The bot is receiving messages**.

## Common problems

**Pasting the token reports "Invalid token (Zalo refused it)".** Check whether you pasted the Telegram token by mistake. The two channels use completely different tokens.

**You message the bot and nothing happens.** Look at the status line under the Zalo card. If it says the bot is receiving messages and it is still silent, check the **Waiting for your approval** block: most likely you have not clicked Allow for yourself.

**The bot keeps replying with a pairing-code request.** That is exactly what "not yet allowed" looks like. Go to the dashboard, click Allow, then message again.

**The bot reports a rate limit.** Zalo has published no rate-limit figures. On a 429 Javis rests for a minute then retries, and shows the error on the status line.

**The bot is green but answers nobody.** Check the server log for the line `[zalo getUpdates] unfamiliar response shape`. Zalo's documentation has not published the response shape of `getUpdates`, so Javis accepts several shapes and speaks up when it meets an unknown one. Sending that line to the developer gets it fixed fast.

## Related

- [The Telegram channel](11-telegram.md) - the other channel, with more features but less used in Vietnam.
- [Chatbot](25-chatbots.md) - the bot CUSTOMERS message, which also runs on Zalo.
- [Zalo Agent MCP](12-zalo-agent-mcp.md) - signing into a personal Zalo account so Javis can act on your behalf.
- [Recurring jobs and reminders](08-recurring-jobs.md) - where the background reports sent to this channel come from.
