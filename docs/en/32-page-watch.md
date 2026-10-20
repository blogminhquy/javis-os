# 32 - Web page watch (no tokens spent)

*[Tiếng Việt](../32-theo-doi-trang.md) · **English***

Since 0.239.0 Javis can watch a web page on a schedule **without spending tokens**. Each check only loads the page and compares its text with the previous one, without calling AI. When something new happens, Javis reports it to the chat and the inbox.

Use it when the job is just keeping an eye on a page: a competitor's price, a new offer on WarriorPlus, an ad policy page, stock coming back. This used to need a loop, and every loop cycle was an AI call.

| Alert when | Meaning |
|---|---|
| **The page changes** | A new line, a line whose number changed (price, stock) or a removed line |
| **Some text appears** | For example "In stock". Reported once when it appears, not again while it stays |
| **A price drops below** | For example a threshold of "$20": reported when the page shows a lower price |

## Create it by asking in chat

Tell Javis something like "watch this page and tell me when the shirt drops below $20", with the link. Javis uses the `javis_watch` tool and replies with the watch id. Every engine can do this.

## Create it on the Recurring work page

1. Open **Recurring work**, then the **Page watch** tab.
2. Paste the **Page address**, pick **Alert when**, and fill in the text or price threshold if needed.
3. Set **Check every** (5 minutes to 7 days, 60 minutes by default) and a name.
4. Press **Start watching**. The first check runs within 30 seconds.

Each watch has **Check now**, **Pause** / **Resume** and **Delete**. Its card shows how many checks ran, the last alert and the last error if any.

## Prices Javis understands

`1.250.000đ`, `990.000 ₫`, `2,000,000 VND`, `1,25 triệu`, `1tr2`, `250k`, `$12.99`, `1,299.00 USD`. The threshold can be written the same ways. A threshold in dong is only compared with dong prices, a dollar threshold only with dollar prices.

## Why it does not cry wolf

- **Times that tick on their own do not count:** "3 minutes ago", "posted 2 hours ago", "yesterday", and the Vietnamese equivalents.
- **Lines where only a number changed** are listed as "Updated", apart from "New" and "Removed", so a price change stands out.
- **Every alert has its own key:** a server restart never sends the same alert twice.
- **The first check only records a baseline** for "The page changes"; alerts start from the next check.

## When the page fails

Javis waits longer between tries: 2, 4, 8, 16 minutes, at most 60. After **5 failures in a row** the watch pauses itself and tells you **exactly once**. Press **Resume** once the page works again.

## AI summary (optional)

Tick **Summarize changes with AI** and Javis calls the background model **once per change** to explain what it means. Off by default. The model gets text only, no tools, and is told to treat the page content as data, not instructions.

## Limits

- Javis reads the page text the way a browser first downloads it. Content that only appears after JavaScript runs (some marketplaces, pages behind a login) is not visible. Use a loop with browser tools for those.
- Pages with clocks, anti-bot tokens or rotating ads may report "changed" often. Switch to **Some text appears** or **A price drops below** instead.
- Only public pages on port 80 or 443 can be watched. Addresses that point into a private network (your server, router, cloud metadata) are blocked, even when a public page redirects there.
- Alerts reach the web chat and the inbox. To get them on your phone, connect Telegram or Zalo, see [Telegram](11-telegram.md).

## Where the data lives

`web_watch.sqlite3` in the Javis state folder (`JAVIS_STATE_DIR`), next to `kanban.sqlite3`.

## Related

- [Recurring jobs](08-recurring-jobs.md)
- [Kanban work](21-kanban-work.md)
