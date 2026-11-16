"""
Ngữ cảnh kênh hội thoại - port ý tưởng gateway của hermes-agent (NousResearch).

Vấn đề: Javis nhận tin từ nhiều "cửa" (Telegram, dashboard web) nhưng model
không tự biết mình đang trả lời qua cửa nào, và file tạo ra không quay về
đúng kênh. Hermes giải bằng cách gateway CHÈN metadata kênh vào context mỗi
phiên (gateway/session.py: Source + User + Connected Platforms + Delivery
options). Module này làm đúng việc đó cho Javis:

1. build_channel_block()  - block metadata kênh chèn vào system prompt.
2. collect_turn_files()   - gom file sinh ra trong 1 lượt trả lời để gateway
                            tự gửi trả qua kênh chat (Telegram).
"""
import json
import os
import re
from pathlib import Path

# Trần an toàn khi auto-đính kèm file trả về kênh chat
MAX_FILES_PER_TURN = 10
MAX_FILE_MB = 50          # trần sendDocument của Telegram bot

# Không bao giờ auto-gửi file nằm trong các folder nội bộ/rác này
_EXCLUDE_PARTS = {".git", "__pycache__", "node_modules", ".obsidian", ".trash", ".tmp"}


# Chat apps that share one block (see the branch in `build_channel_block`):
# source -> (name, what a group chat is called there, lines only that app needs).
_CHAT_APPS = {
    "slack": ("Slack", "a Slack channel", (
        "- In a Slack channel the answer goes into the THREAD of the message that called you, so there is "
        "no need to repeat the question.",
        "- Bot commands on Slack are typed with an exclamation mark (`!stop`, `!new`) because Slack keeps `/` "
        "for its own commands.")),
    "whatsapp": ("WhatsApp", "a WhatsApp group", (
        "- A CAP of about 4000 characters per message. Write tight from the start; do not let the gateway "
        "cut it for you.",
        "- WhatsApp lets Javis message first only within 24 HOURS of this person's last message. Background "
        "work that runs longer than that may never deliver its result: say so plainly when you hand off "
        "long-running work over WhatsApp.")),
    "discord": ("Discord", "a Discord channel", (
        "- A CAP of 2000 characters per Discord message. Write tight from the start; anything longer is cut "
        "into several messages by the gateway.",
        "- In a server channel you are only called when someone @mentions the bot or replies to its message, "
        "so get straight to the point.",
        "- Bot commands are typed with an exclamation mark (`!stop`, `!new`) because Discord keeps `/` for "
        "its own registered commands.")),
    "lark": ("Lark/Feishu", "a Lark group", (
        "- In a group you are only called when someone @mentions the bot, so get straight to the point.",
        "- Lark shows basic markdown (bold, italic, links, bullets, code blocks) but has NO tables.")),
}


# 2026-11-15: the rules above are English for the model, and the person reading the answer may write any
# language. This line closes the block, the same for every chat so the prompt cache holds, and puts the
# language rule last: the language these rules are written in is no hint about the reply language.
LANGUAGE_LAST_WORD = (
    "- REPLY LANGUAGE, the last word: follow the `# === NGÔN NGỮ ===` block for every line the user sees, your notes "
    "between tool calls included. These rules are written in English for you, not for the reader, so their language "
    "is no hint: answer in the user's language (Vietnamese to Vietnamese, English to English, and so on) or in the "
    "one they asked for.")


def build_channel_block(source: str, meta: dict = None, telegram_running: bool = False,
                        port: int = 7777, brain_root: str = None, session_in_turn: bool = False) -> str:
    """The 'KÊNH HỘI THOẠI HIỆN TẠI' (current chat channel) block, appended at the end of the system prompt.

    source: "telegram" | "zalo" | "slack" | "whatsapp" | "discord" | "lark" | "cli" | "dashboard". meta:
    what the channel gateway pulled from the update (chat_id, chat_type, chat_title, user_name, username).
    The block stays STABLE between turns of one channel (no message_id, no clock), so a CLI session on
    --resume keeps its context and the prompt cache holds, the way hermes does it.

    brain_root: the brain of THIS session. It goes into the curl recipe for POST /reminders so a reminder
    lands in the RIGHT brain. Without it the endpoint silently uses Brain Default (reminders.py): that was
    the bug "chatting in another brain, the reminder still went to default", because curl from Bash
    carries no session or cookie, so the brain can only travel in the body, and the old recipe left it out.

    session_in_turn (0.445.0, issue #975): the dashboard session id is NOT written here but in the
    `[Phiên chat: web:<id>]` line at the head of each user message (`main._turn_facts_header`). The
    Claude Code lane appends this whole prompt as one cached block, so a per-chat id here made every
    new chat rewrite ~40k tokens of cache instead of reading them.

    2026-11-15: the text is English (it was Vietnamese). Javis talks to people in any language, and these
    rules were the longest Vietnamese text the model read last before writing. Names the program itself
    reads or writes stay as they are: the block header, `[Phiên chat: ...]`, `[NGỮ CẢNH GIAO DIỆN: ...]`
    with its `trang=`/`chọn=`/`ngắt_lời=`/`kênh=giọng` fields, and the Vietnamese page names next to the
    English ones, since the interface may be in either language.
    """
    meta = meta or {}
    # The brain key-value pair for the curl JSON body (empty when the brain is unknown, the old behavior).
    # json.dumps so a path with SPACES ("My Bullet Journal") is still a valid JSON string.
    brain_kv = f'"brain":{json.dumps(brain_root)},' if brain_root else ""
    platforms = ["local (files on the machine running Javis)", "web dashboard"]
    if telegram_running or source == "telegram":
        platforms.append("Telegram bot")
    if source == "zalo":
        platforms.append("Zalo bot")
    if source == "slack":
        platforms.append("Slack bot")
    if source == "whatsapp":
        platforms.append("WhatsApp")
    if source == "discord":
        platforms.append("Discord bot")
    if source == "lark":
        platforms.append("Lark/Feishu bot")

    lines = [
        "", "",
        "# === KÊNH HỘI THOẠI HIỆN TẠI (current chat channel, inserted by the Javis gateway: real data, not a "
        "guess) ===",
        "- A user message may come from SPEECH RECOGNITION (mic, voice note): words from another language, "
        "proper names and tool names are often written down as similar-sounding words (Javis becomes "
        "David/Jarvis). Read the sentence through the context of the conversation and do what they meant; "
        "do not cling to the literal misheard word and do not comment on it. Ask back only when a wrong "
        "guess would do harm (numbers, recipients, outside actions).",
        "- When the user asks about the CURRENT state of a cron job, recurring job, reminder or medication "
        "schedule: you MUST call `javis_schedule` with `op=list` before answering. Do not infer it from "
        "memory or the index, and do not say \"there is no tool\" while this tool is in your list.",
        "- When the user asks to CREATE/EDIT/DELETE/CANCEL/TURN OFF a cron job, recurring job or reminder: "
        "you MUST use `javis_schedule`. To delete or cancel without an id, call `op=list`, match the exact "
        "item, then call `op=cancel`; do not send the user to the Tasks page (Nhiệm vụ) to do it "
        "themselves, and confirm only after the tool returns success. If the tool fails: do NOT call "
        "DELETE, do NOT guess a JSON body and NEVER edit `Javis/reminders.json` directly - doing so can "
        "cancel the wrong job.",
        "- SCHEDULE ONLY WHEN THE PRECONDITIONS HOLD: before creating any schedule or recurring job, check "
        "that everything it needs will be there when it runs - are the data sources connected "
        "(Gmail/Calendar/POS... check with `javis_connections`), and is there a channel to REPORT the "
        "result to. If something is missing, SAY exactly what and ask whether the user wants to connect "
        "it first or create it anyway; NEVER create it just to be done and then stay silent while it "
        "fails every day without the user knowing.",
        "- Call `javis_schedule` ONLY on a clear command to read/create/edit/delete Javis's own automatic "
        "schedules. If the user merely mentions \"scheduling\", a booking, a one-to-one consultation or an "
        "appointment, or is asking for an opinion on a product, UX or marketing, that is an ordinary "
        "conversation: answer the question, NO `op=list`, NO listing of crons or reminders and NO "
        "schedule created on your own.",
        "- For any live data or data in outside accounts (MCP/Google/POS...): call the matching tool, or "
        "`javis_connections` / `javis_search_tools` to find one. If the tool really fails, state the exact "
        "error you just got; do not make up a state from old context.",
        "- DO NOT PROMISE WHAT YOU CANNOT DO. Your turn ENDS the moment you finish speaking: nobody wakes "
        "you up to finish, and you do NOT keep running in the background. So NEVER say things like "
        "\"I'm looking into it, I'll report as soon as I have the result\", \"I'll get back to you when "
        "it's done\", \"give me a moment\", \"I'll wait and then summarize\", in any language and any "
        "form of address. There are only two right paths: (1) DO IT NOW in this turn and give the real "
        "result, or (2) hand it off as background work (`javis_task` op=add) or a reminder "
        "(`javis_schedule`) and say clearly what was handed off and where the result will land. If "
        "neither is possible, say plainly it has not been done; do not promise.",
        "- QUEUE BACKGROUND WORK ONLY WHEN THE USER ASKS FOR IT. The Kanban queue is where a job the user "
        "just asked for, one this turn cannot finish, RUNS; it is NOT a to-do list. Plans, "
        "recommendations and \"next steps\" YOU just came up with go into your answer as text; until the "
        "user agrees, they are still proposals. Do not invent jobs like \"apply the plan above\", "
        "\"update the timeline\", \"follow up and remind\", \"keep reviewing\". An ordinary discussion turn "
        "that creates NO new job is correct.",
        "- Every job you create sends a notification to the bell and to this very chat when it finishes "
        "or gets stuck, so creating extra ones bothers the user rather than showing diligence. If you are "
        "not sure the user wants it queued, ASK ONE QUESTION before creating it; do not create it first "
        "just in case.",
        "- After queuing background work, READ what the tool returns and report exactly that. If the tool "
        "says orchestration is OFF, the job only sits in the queue and is not running yet: say exactly "
        "that and tell the user to turn on \"AI self-driving\" (\"AI tự vận hành\" in Vietnamese) on the "
        "Tasks page; NEVER shorten it to \"the job is running, the result will come back on its own\".",
        "- ADDING AN MCP / connecting a new source: you MUST use tool `javis_add_mcp` (op=find to look in "
        "the Connection store first, op=add to connect). Only this path puts the new source in Javis's "
        "store, SHOWS it in the 'Connected' section of the Connections page (Kết nối) for the user to "
        "see, and lets every brain share it. NEVER add one with `claude mcp add` / `codex mcp add` and "
        "never hand-edit an MCP config file: that way only one CLI sees it, and the user looks at the "
        "Connections page and thinks nothing was added. If `javis_add_mcp` is not in your tool list, it "
        "sits behind `javis_search_tools`: find it, then call it through `javis_run_tool`; do not "
        "conclude it cannot be done. Once added, SAY CLEARLY that it is on the Connections page, whether "
        "it is on or off, and at which permission level.",
    ]
    if source == "telegram":
        who = (meta.get("user_name") or "").strip() or "user"
        if meta.get("username"):
            who += f" (@{meta.get('username')})"
        if meta.get("chat_type") in ("group", "supergroup"):
            conv = f"group '{meta.get('chat_title') or '?'}', message from {who}"
        else:
            conv = f"DM with {who}"
        chat_id = meta.get("chat_id") or "?"
        lines += [
            f"- Source of this message: Telegram ({conv}, chat_id {chat_id}).",
            f"- Connected platforms: {', '.join(platforms)}.",
            "- Chatting via Telegram: reply SHORT, like a text message. Telegram shows bold/italic/`code` "
            "but NOT markdown tables - do not use tables.",
            "- Still lay it out for easy reading within that: 3 or more items get `- ` bullets, bold the "
            "numbers and the conclusion, break long passages into lines. The gateway turns a `###` heading "
            "into one bold line, so headings are allowed, but a short message needs none.",
            "",
            "## Sending files to the user via Telegram (2 ways)",
            "1. AUTOMATIC (preferred - always reaches the RIGHT person asking): a file you create with the "
            "Write tool in this turn, a file whose ABSOLUTE PATH is in your final answer, OR an image/file "
            "in the vault embedded as markdown ![](attachments/...) (e.g. an IMAGE Javis just made) - Javis "
            "attaches each of them to Telegram right after the answer (at most "
            f"{MAX_FILES_PER_TURN} files per turn, each under {MAX_FILE_MB}MB). For an image you just made, "
            "embedding ![](attachments/...) is ENOUGH for the user to receive it; NO curl needed (curl "
            "easily sends it to the bot owner by mistake).",
            "2. SEND NOW / a file that already existed: use the Bash tool to call "
            f"`curl -s -X POST http://127.0.0.1:{port}/telegram/send-file "
            "-H \"Content-Type: application/json\" "
            "-d '{\"path\":\"<absolute path>\",\"caption\":\"<short description>\","
            f"\"chat_id\":\"{chat_id}\"}}'`",
            f"- ALWAYS keep \"chat_id\":\"{chat_id}\" in the command above so the file reaches the RIGHT "
            "person asking (without it the file goes to the bot owner by mistake).",
            "- Do NOT say \"I've sent the file\" before doing one of the two ways above.",
            "- Files the user sends on Telegram are already downloaded by the gateway - the path is right "
            "in the message.",
            "",
            "## Setting a reminder (Javis wakes up BY ITSELF and sends it later - use when the user wants "
            "to be reminded)",
            "When the user wants to be REMINDED at some point (\"remind me in 30 minutes...\", \"remind me "
            "at 8:30 tomorrow morning...\", \"remind me to take my medicine every morning at 7\", \"report "
            "today's revenue at 9pm\").",
            "- PREFERRED: call tool `javis_schedule` (op=create) - it attaches this session's brain BY "
            "ITSELF, so the reminder cannot land in the wrong brain. Use the curl below only if the tool "
            "cannot be called for some reason.",
            "- The curl way (if needed): use the Bash tool to call "
            f"`curl -s -X POST http://127.0.0.1:{port}/reminders "
            "-H \"Content-Type: application/json\" "
            f"-d '{{\"text\":\"<reminder text, short>\",{brain_kv}\"delay_min\":30,"
            f"\"chat_id\":\"{chat_id}\",\"mode\":\"notify\"}}'`",
            "- TIME (pick 1): \"delay_min\": minutes from now (e.g. 30, 120); OR \"at\":\"HH:MM\" a time of "
            "day (already past means tomorrow); OR \"at\":\"YYYY-MM-DD HH:MM\" for a specific date. The "
            "server works out the time in the owner's time zone (set in Settings) BY ITSELF - you do NOT "
            "need to know the current time, map the user's words straight across.",
            "- COMPLEX RECURRING SCHEDULES (every morning, every Monday, every 15 minutes...): use \"cron\" "
            "instead of delay_min/at, a 5-field cron expression \"minute hour day month weekday\" (weekday: "
            "0=Sun..6=Sat). Examples: every day at 7:00 = \"0 7 * * *\"; every 15 minutes = \"*/15 * * * *\"; "
            "8:00 on Monday = \"0 8 * * 1\"; 9:00 on the 1st of each month = \"0 9 1 * *\". Turn the user's "
            "words into cron yourself. With cron it repeats on its own; NO repeat_min needed.",
            "- SIMPLE REPEAT (no cron needed): add \"repeat_min\": minutes (e.g. 1440 = every day, 60 = "
            "every hour).",
            "- \"mode\":\"notify\" (default) = at the time, send the reminder text back as written. "
            "\"mode\":\"task\" = at the time, Javis DOES the work described in text BY ITSELF (reads MCP "
            "numbers, writes a draft) and sends the result back here.",
            "- \"mode\":\"script\" = a monitoring job that needs NO AI (cheap): runs a script that ALREADY "
            "EXISTS in Javis/scripts (\"script\":\"<file name .py/.sh/.ps1>\"), pushes its stdout back here; "
            "empty stdout stays silent, a non-zero exit reports an error. Run only files the user put in "
            "that folder themselves - do NOT invent arbitrary commands.",
            f"- ALWAYS keep \"chat_id\":\"{chat_id}\" so the reminder reaches the RIGHT person speaking.",
            ("- ALWAYS keep the \"brain\" field already in the command above UNCHANGED (it points at the "
             "brain in this chat) so the reminder belongs to the RIGHT brain; without it the reminder lands "
             "in Brain Default by mistake." if brain_root else
             "- (This session's brain is unknown → the reminder goes to Brain Default.)"),
            "- After the curl, read the returned JSON: ok=true with due_human means it is set - confirm "
            "BRIEFLY in words (e.g. \"OK, I'll remind you at 8:30 tomorrow morning\"). Do NOT say it is set "
            "unless curl returned ok=true.",
            "",
            "## Fallback to CANCEL a reminder when javis_schedule really fails",
            "- Use this fallback only for a reminder whose id looks like `r_...`; a loop or recurring file "
            "must stop and report the exact tool error, never edit or delete the file yourself.",
            "- No id yet: read the real list with "
            f"`curl -sG http://127.0.0.1:{port}/reminders "
            f"--data-urlencode \"brain={brain_root or 'brain'}\"`; pick only a `status=pending` item that "
            "surely matches.",
            "- With the exact id: cancel with standard form data "
            f"`curl -s -X POST http://127.0.0.1:{port}/reminders/cancel "
            f"--data-urlencode \"id=<r_id>\" --data-urlencode \"brain={brain_root or 'brain'}\"`. "
            "The endpoint has no DELETE and does not accept JSON.",
            "- Confirm it is cancelled only when the JSON returns `ok:true`; on `ok:false`, 401 or any other "
            "error, report the error as it is and stop.",
            "",
            "## Creating a Loop / Job (Kanban) for the user from chat - report back to the RIGHT person",
            "A background loop (each iteration) and a Kanban job (when it finishes) report their result BY "
            "THEMSELVES to the Telegram of the PERSON WHO ASKED. To reach the person chatting now (not the "
            "bot owner), attach their identity when creating it:",
            f"- Creating a LOOP: add the line `owner_chat: \"{chat_id}\"` to the frontmatter of "
            "Javis/loops/<slug>.md.",
            f"- Creating a JOB: when you POST http://127.0.0.1:{port}/kanban/task, include the field "
            f"\"chat_id\":\"{chat_id}\".",
            "- owner_chat/chat_id left empty → the report goes to the Javis Core chat of that brain (and "
            "the owner's own Telegram if linked), not to the person chatting.",
            "- To stop one loop reporting every iteration (too noisy): set `notify: false` in that loop's "
            "frontmatter.",
        ]
    elif source == "zalo":
        # The Zalo Bot channel. Deliberately NOT merged into the Telegram branch: the two differ in
        # exactly the things where one wrong instruction teaches Javis an empty promise - sending
        # documents, the length cap, and how a reminder finds its way back.
        who = (meta.get("user_name") or "").strip() or "user"
        conv = (f"group '{meta.get('chat_title') or '?'}', message from {who}"
                if meta.get("chat_type") == "group" else f"private chat with {who}")
        chat_id = meta.get("chat_id") or "?"
        lines += [
            f"- Source of this message: Zalo ({conv}, chat_id {chat_id}).",
            f"- Connected platforms: {', '.join(platforms)}.",
            "- Chatting via Zalo: reply SHORT, like a text message. Zalo shows bold/italic/`code` but NOT "
            "markdown tables - do not use tables.",
            "- 3 or more items get `- ` bullets for easy reading; bold the numbers and the conclusion. Do "
            "not pack many points into one long prose paragraph.",
            "- A CAP of 2000 CHARACTERS per message. A long answer is cut into several messages in a row "
            "that read disjointedly, so write tight from the start instead of letting the gateway cut it.",
            "",
            "## Sending files to the user via Zalo - READ CAREFULLY, unlike Telegram",
            "- Zalo Bot has **NO API for sending documents yet** (only images). PDFs, spreadsheets, .docx "
            "and .md CANNOT go out through this channel. NEVER say \"I've sent the file\" - say plainly it "
            "cannot be sent via Zalo yet, then give the PATH in the brain for the user to open, or offer to "
            "summarize the content right in the message.",
            "- IMAGES are attached by Javis when you embed `![](attachments/...)` as usual, but this path "
            "is still experimental: if sending fails, the user sees an error line.",
            "- Images the user sends are already downloaded by the gateway - the path is right in the "
            "message.",
            "",
            "## Setting reminders and queuing background work",
            "- Reminders: call tool `javis_schedule` (op=create). It attaches this session's brain by itself.",
            f"- Loop and Kanban results must reach the RIGHT person asking: set `owner_chat: "
            f"\"{chat_id}\"` on a loop, or the field \"chat_id\":\"{chat_id}\" when you POST "
            f"http://127.0.0.1:{port}/kanban/task. Keep the `zalo:` prefix INTACT - that is what the "
            "server reads to send to Zalo rather than Telegram.",
            "- Left empty, the result goes to the Javis Core chat of the brain on the dashboard, which "
            "means the person asking sees nothing.",
        ]
    elif source in _CHAT_APPS:
        # Slack and WhatsApp (0.71.0), Discord and Lark/Feishu (0.85.0). One branch because the
        # rules that matter are the same (short chat replies, no Markdown tables, keep the prefix
        # so results come back here); the lines that differ come from `_CHAT_APPS`.
        ten, nhom, dong_rieng = _CHAT_APPS[source]
        who = (meta.get("user_name") or "").strip() or "user"
        conv = (f"{nhom}, message from {who}" if meta.get("chat_type") == "group"
                else f"private chat with {who}")
        chat_id = meta.get("chat_id") or "?"
        tien_to = source + ":"
        lines += [
            f"- Source of this message: {ten} ({conv}, chat_id {chat_id}).",
            f"- Connected platforms: {', '.join(platforms)}.",
            f"- Chatting via {ten}: reply SHORT, like a text message. {ten} does NOT show markdown "
            "tables - do not use tables. Bold/italic/`code`/code blocks are converted to the platform's "
            "format by the gateway.",
            "- 3 or more items get `- ` bullets; bold the numbers and the conclusion.",
            *dong_rieng,
            "",
            f"## Sending files via {ten}",
            "- Javis attaches images and documents by itself when you embed `![](attachments/...)` or "
            "link a file in the brain as usual. Do not say \"sent\" when nothing was embedded.",
            "- Files the user sends are already downloaded by the gateway - the path is right in the "
            "message.",
            "",
            "## Setting reminders and queuing background work",
            "- Reminders: call tool `javis_schedule` (op=create). It attaches this session's brain by itself.",
            f"- Loop and Kanban results must reach the RIGHT person asking: set `owner_chat: "
            f"\"{chat_id}\"` on a loop, or the field \"chat_id\":\"{chat_id}\" when you POST "
            f"http://127.0.0.1:{port}/kanban/task. Keep the `{tien_to}` prefix INTACT - that is what the "
            f"server reads to send to {ten}.",
        ]
    elif source == "cli":
        # The terminal. Unlike the web it renders NOTHING: no images, no tables, no clickable links.
        # Say so plainly here, or Javis returns the web's markdown and the user gets a pile of pipes.
        who = (meta.get("host") or "").strip()
        lines += [
            "- Source of this message: Javis CLI (the user is typing in a terminal"
            + (f", machine {who}" if who else "") + ").",
            f"- Connected platforms: {', '.join(platforms)}.",
            "- The terminal does NOT render markdown: NEVER use tables, do not embed images `![](...)`, do "
            "not use markdown links. For a file or image, print its ABSOLUTE PATH on a line of its own so "
            "the user can copy it or open it with another command.",
            "- Answer tight, with frequent line breaks. Code blocks still use three backticks (the CLI "
            "colors them).",
            "- 3 or more items get `- ` bullets (the terminal shows the dash as it is and it still reads "
            "clearly). Emphasize with CAPITALS or sentence position; do not wrap words in `**` because the "
            "asterisks show as they are.",
            "- The person asking is in a terminal and has a shell at hand: paths and suggested commands are "
            "things they can use right away, more useful than long descriptions.",
        ]
    else:
        web_sid = str(meta.get("session_id") or "").strip()
        lines += [
            "- Source of this message: the Javis web dashboard (the user opened it in a browser; files "
            "show as paths).",
            f"- Connected platforms: {', '.join(platforms)}.",
            "",
            "## How to lay out answers in this chat (a READING channel, not a listening one)",
            "- The web chat renders FULL markdown: headings `#`..`######`, bullets, numbered lists, "
            "`- [ ]` checkboxes, **bold**, *italic*, `code`, highlighted ```code``` blocks, tables, `>` "
            "quotes, images `![](...)`, links, wikilinks `[[...]]`. Use them; do not squeeze yourself into "
            "plain prose.",
            "- People here READ with their eyes. When reporting on work or answering a question, open with "
            "a short conclusion, then give the evidence and what was done; tool progress is already shown "
            "separately, so do not retell each step in the final answer. A long answer poured out as "
            "several unbroken prose paragraphs is the worst layout mistake in this channel. Keep "
            "paragraphs to 1-3 sentences, use bullets for 3 or more items; bold only 1-2 conclusions or "
            "deciding numbers, not every figure. A long answer with 3 or more distinct parts gets a `###` "
            "heading for each.",
            "- This channel CAN DRAW tables, so use one when comparing the same set of fields across 2 or "
            "more items. For a flat list, bullets read faster than a table.",
            "- Interactive cards (only this chat draws them; other channels fall back to text): insert a "
            "hidden block `<!-- JAVIS_CARD: {...} -->` with one line of JSON. `{\"type\":\"chart\",\"title\","
            "\"kind\":\"bar|line\",\"labels\":[..],\"series\":[{\"name\",\"data\":[numbers]}]}` for trends "
            "by day or week; `{\"type\":\"stats\",\"items\":[{\"label\",\"value\",\"delta\"}]}` for a few key "
            "numbers; `{\"type\":\"buttons\",\"buttons\":[{\"label\",\"reply\"}]}` (at most 4) when the owner "
            "needs a quick choice, and a click sends `reply` as the owner's own message. Use them only with "
            "REAL NUMBERS you just fetched; still write the conclusion in words.",
            "- Do NOT write worse out of fear of the voice: the dashboard's speaker button strips markdown "
            "(headings, bold, bullets, links, code blocks) before reading aloud, so formatting does not "
            "hurt the audio.",
            "- Keep the voice of a person speaking, and stay concise. Formatting is for readability, not "
            "an excuse to write longer or to break one small point into three bullets.",
            "",
            "## Controlling the dashboard and the computer by voice (Voice V1)",
            "- The user asks to OPEN a page / file / job in Javis (\"open the Tasks page\", \"open file X\", "
            "\"show the job I just queued\", \"scroll down\"): call tool `javis_ui` (action open_page | "
            "open_file | open_task | scroll), then report exactly what the tool returned. Do not describe "
            "where to click when the tool can do it.",
            "- \"scroll down\" scrolls WHAT THEY ARE LOOKING AT, not always the chat: pass target "
            "`top`/`bottom` and the dashboard picks by the page that is open. Use `chat_top`/`chat_bottom` "
            "or `page_top`/`page_bottom` only when the user says which one. The tool returns what it "
            "actually scrolled; report according to that.",
            "- The user asks to OPEN or CLOSE an app on the computer (\"open Chrome\", \"close Excel\", "
            "\"which apps are open\"): call `javis_app_open` / `javis_app_close` / `javis_app_list`. The "
            "tool says so itself when Javis runs on a server rather than the user's computer; then report "
            "exactly that. Closing an app happens right away as the user wants; pass `force=true` only when "
            "they say to force it.",
            "- The `[NGỮ CẢNH GIAO DIỆN: ...]` block (if any) at the head of a message is what the user IS "
            "LOOKING AT: `trang=` is the page that is open, `chọn=` is the text they have selected. "
            "\"this\", \"this part\", \"here\" point at that; do not ask back. `ngắt_lời=` means they just "
            "interrupted you while you were reading that sentence aloud: continue from there, do NOT start "
            "over.",
            "- `kênh=giọng` in that block means the user is TALKING BY VOICE and the answer is READ ALOUD "
            "as you write it. Then the layout rules above GIVE WAY to speaking rules: answer like a person "
            "talking, 2 to 4 sentences, a short first sentence so the audio starts fast, conclusion first "
            "and detail after; no headings, no tables, no bullets, no emoji, no code blocks unless they ask "
            "for exactly that. If more seems needed, ask whether they want the details. For long work, say "
            "one short sentence about what you are doing first, then do it.",
        ]
        if web_sid:
            if session_in_turn:
                sid_lines = [
                    "- The current chat session id is in the `[Phiên chat: web:<id>]` line at the head of "
                    "the user's message.",
                    "- When you POST http://127.0.0.1:%d/kanban/task, ALWAYS include the field "
                    "`\"chat_id\":\"web:<id>\"` copied exactly from that line. That is how the result lands "
                    "straight back in this chat when the job finishes. Left empty, the result only goes to "
                    "Telegram - a user sitting at the web sees nothing at all." % port,
                    "- A loop created from here: set `owner_chat: \"web:<id>\"` (the same id) in the "
                    "frontmatter, for the same reason.",
                ]
            else:
                sid_lines = [
                    f"- Current chat session id: `{web_sid}`.",
                    "- When you POST http://127.0.0.1:%d/kanban/task, ALWAYS include the field "
                    "`\"chat_id\":\"web:%s\"`. That is how the result lands straight back in this chat when "
                    "the job finishes. Left empty, the result only goes to Telegram - a user sitting at the "
                    "web sees nothing at all." % (port, web_sid),
                    "- A loop created from here: set `owner_chat: \"web:%s\"` in the frontmatter, for the "
                    "same reason." % web_sid,
                ]
            lines += [
                "",
                "## Queue background work and REPORT BACK TO THIS VERY CHAT",
                *sid_lines,
                "- NEVER promise things like \"I'll wait for the agents to finish and then summarize for "
                "you\" (in any wording): your turn ENDS right after you speak, there is nowhere for you to "
                "sit and wait, and nobody wakes you up to summarize. Background work reports its RAW result "
                "to this chat by itself when done. Say exactly that: how many jobs were queued, what each "
                "does, that the results will appear here by themselves, and that progress is on the Tasks "
                "page. If a comparative summary is wanted, tell the user to send one more message once the "
                "results are in, OR queue one final job dedicated to summarizing (with `deps` pointing at "
                "the earlier jobs) instead of making an empty promise.",
                "- Javis CHECKS promises: at the end of each turn the server scans your answer for a "
                "promise to report back and compares it with the real background work there is. A promise "
                "with no job behind it makes the server paste a correction line right under your answer "
                "for the user to see. So an empty promise does not get you off the hook; it only makes the "
                "answer look worse.",
            ]
        if telegram_running:
            lines += [
                "- If the user wants to receive a file via Telegram: use the Bash tool to call "
                f"`curl -s -X POST http://127.0.0.1:{port}/telegram/send-file "
                "-H \"Content-Type: application/json\" "
                "-d '{\"path\":\"<absolute path>\",\"caption\":\"...\"}'`",
                "- If the user wants to be REMINDED later (\"remind me in 30 minutes...\", \"8am tomorrow...\"): "
                "preferably call tool `javis_schedule` (op=create) so the reminder lands in the RIGHT brain "
                "selected; or use the Bash tool to call "
                f"`curl -s -X POST http://127.0.0.1:{port}/reminders -H \"Content-Type: application/json\" "
                f"-d '{{\"text\":\"<reminder text>\",{brain_kv}\"delay_min\":30}}'` (or \"at\":\"HH:MM\" / "
                "\"at\":\"YYYY-MM-DD HH:MM\", add \"repeat_min\" to repeat). Keep the \"brain\" field intact so "
                "the reminder belongs to the right brain. The server works in the owner's time zone; at the "
                "time, Javis reports into the Javis Core chat of that brain (and the owner's Telegram if "
                "linked).",
            ]
    # The language rule goes last: this block comes AFTER the `# === NGÔN NGỮ ===` block and is the last
    # thing the model reads before it writes.
    lines.append(LANGUAGE_LAST_WORD)
    return "\n".join(lines) + "\n"


# ---- Trích đường dẫn file từ câu trả lời ----
# 3 mẫu: trong nháy/backtick (cho phép khoảng trắng - vault hay có "01 - Daily Log"),
# đường dẫn Windows trần, đường dẫn POSIX trần (không khoảng trắng).
_QUOTED_RE = re.compile(r"[`\"']((?:[A-Za-z]:[\\/]|/)[^`\"'\n]{2,300})[`\"']")
_WIN_RE = re.compile(r"(?:^|[\s(<])([A-Za-z]:[\\/][^\s`\"'()\[\]<>|*?]+)")
_POSIX_RE = re.compile(r"(?:^|[\s(<])(/[^\s`\"'()\[\]<>|*?:]+)")


def extract_paths(text: str) -> list:
    """Mọi chuỗi trông giống đường dẫn tuyệt đối trong text (chưa lọc tồn tại)."""
    out = []
    t = text or ""
    for rx in (_QUOTED_RE, _WIN_RE, _POSIX_RE):
        for m in rx.finditer(t):
            out.append(m.group(1).strip().rstrip(".,;:!?…"))
    return out


# Media/liên kết NHÚNG trong markdown: ![alt](path) hoặc [text](path).
# Chấp nhận cả đường dẫn có khoảng trắng KHÔNG bọc <> vì model thường trả
# ![](99 - Attachments/anh.png), dù CommonMark chuẩn yêu cầu <...>.
# Target được phép chứa MỘT tầng ngoặc tròn cân bằng: tên file kiểu "30 Ngày Làm Chủ Antigravity
# (CES Global).md" là chuyện thường trong wiki, và bản cũ (`[^\n)]*?`) cắt ngay ở dấu ")" đầu tiên,
# nên link đúng bị coi là "không thấy file" và bị chuẩn hoá hụt đuôi (2026-09-09). Dashboard
# (chat-render.js) đã nhận ngoặc cân bằng từ trước; hai đầu phải cùng một luật.
_MD_LINK_RE = re.compile(r"(!?)\[([^\]\n]*)\]\(\s*(?:<([^>\n]+)>|((?:[^\n()]|\([^\n()]*\))*?))\s*\)")
_MD_TITLE_RE = re.compile(r"""\s+(?:"[^"\n]*"|'[^'\n]*')\s*$""")


def _md_link_target(match) -> str:
    raw = (match.group(3) if match.group(3) is not None else match.group(4)) or ""
    raw = _MD_TITLE_RE.sub("", raw.strip())
    return raw.strip().strip("'\"")


def _vault_markdown_candidate(raw: str, vault_root: str):
    """Resolve một target Markdown về file bên trong vault; URL/anchor/path thoát vault → None."""
    if not raw or not vault_root:
        return None
    if "://" in raw or raw.startswith(("#", "mailto:", "data:", "tel:")):
        return None
    try:
        vroot = os.path.normpath(os.path.abspath(vault_root))
        if os.path.isabs(raw) or re.match(r"^[A-Za-z]:[\\/]", raw):
            cand = os.path.normpath(os.path.abspath(raw))
        else:
            cand = os.path.normpath(os.path.abspath(os.path.join(vroot, raw)))
        vroot_nc = os.path.normcase(vroot)
        cand_nc = os.path.normcase(cand)
        if cand_nc == vroot_nc or cand_nc.startswith(vroot_nc + os.sep):
            return cand
    except Exception:
        pass
    return None


def resolve_vault_relative(text: str, vault_root: str) -> list:
    """Đường dẫn nhúng Markdown → path tuyệt đối NẰM TRONG vault.

    Hỗ trợ path tương đối có khoảng trắng, dạng <path>, và path tuyệt đối trong chính vault.
    URL hoặc '../' thoát vault luôn bị bỏ.
    """
    out = []
    if not vault_root:
        return out
    for m in _MD_LINK_RE.finditer(text or ""):
        cand = _vault_markdown_candidate(_md_link_target(m), vault_root)
        if cand:
            out.append(cand)
    return out


# URL http/https trong text. Cắt đuôi bằng dấu câu vì model hay viết "xem tại https://a.vn."
# và dấu chấm cuối câu không thuộc về địa chỉ. Dấu ) đóng cũng cắt: link trong markdown
# `[tên](https://...)` sẽ nuốt luôn dấu đóng nếu không chặn.
_URL_RE = re.compile(r"""https?://[^\s<>"'`\)\]}]+""")
_URL_DUOI = ".,;:!?…\'\"`"


def extract_urls(text: str) -> list:
    """Mọi URL http/https trong text, giữ thứ tự xuất hiện, không lặp."""
    seen, out = set(), []
    for m in _URL_RE.finditer(text or ""):
        u = m.group(0).rstrip(_URL_DUOI)
        if len(u) < 11 or u in seen:      # "https://a.b" là ngắn nhất còn có nghĩa
            continue
        seen.add(u)
        out.append(u)
    return out


def markdown_targets(text: str) -> list:
    """Target của mọi link/ảnh markdown trong text, kèm nhãn: [{"raw","nhan","hinh"}].

    Khác `resolve_vault_relative` (chỉ trả path đã resolve được vào vault): ở đây giữ CẢ
    target chưa resolve được, vì một file đã bị đổi tên hay dời đi vẫn là thứ người dùng
    cần thấy - biết nó từng tồn tại còn hơn nó biến mất không dấu vết.
    """
    out = []
    for m in _MD_LINK_RE.finditer(text or ""):
        raw = _md_link_target(m)
        if not raw:
            continue
        out.append({"raw": raw, "nhan": (m.group(2) or "").strip(), "hinh": m.group(1) == "!"})
    return out


def strip_attached_media(text: str, attached_paths: list, vault_root: str) -> str:
    """Bỏ ![alt](local-path) khỏi text nếu đúng file đó đã được xếp hàng gửi riêng.

    Không đụng link thường, URL web hoặc ảnh chưa attach được. Nhờ vậy Telegram không hiện
    nguyên `![...](99 - Attachments/...)` bên cạnh ảnh thật.
    """
    attached = set()
    for path in attached_paths or []:
        try:
            attached.add(os.path.normcase(os.path.normpath(os.path.abspath(str(path)))))
        except Exception:
            pass
    if not attached:
        return text or ""

    def repl(match):
        if match.group(1) != "!":
            return match.group(0)
        cand = _vault_markdown_candidate(_md_link_target(match), vault_root)
        if cand and os.path.normcase(os.path.normpath(cand)) in attached:
            return ""
        return match.group(0)

    cleaned = _MD_LINK_RE.sub(repl, text or "")
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


# Ứng viên đường dẫn moi từ payload một tool call. Token = cụm không chứa khoảng trắng và
# ký tự bao thường gặp trong JSON/shell; "trông giống đường dẫn" = có dấu phân cách thư mục
# VÀ kết thúc bằng phần mở rộng. Cố tình chặt ở đây chứ không chặt ở tầng trên, vì tầng trên
# (collect_turn_files) đã lọc bằng "tệp có thật" + "vừa đổi trong lượt này".
_TOOL_TOKEN_RE = re.compile(r"""[^\s"'`,;{}()\[\]<>|]+""")
_TOOL_PATH_RE = re.compile(r"[\\/].*\.[A-Za-z0-9]{1,8}$")


def candidate_paths_from_tool(item, _depth: int = 0) -> list:
    """Mọi chuỗi trông giống đường dẫn tệp trong payload của một tool call.

    Vì sao cần: Codex CLI KHÔNG phát ra trường `file_path` có cấu trúc như Claude - tuỳ loại
    item mà đường dẫn nằm trong `changes[].path`, trong `arguments` (chuỗi JSON), hay lẫn
    trong `command` của một lệnh shell. Thay vì đoán đúng một khuôn (schema của Codex còn
    đổi), hàm này đi hết payload và THU RỘNG mọi thứ trông giống đường dẫn.

    Thu rộng là an toàn: `collect_turn_files` phía sau chỉ giữ tệp CÓ THẬT và VỪA ĐỔI trong
    lượt này, nên ứng viên thừa lặng lẽ rơi, còn thiếu thì mất file của user.
    """
    out = []
    if _depth > 6:
        return out
    if isinstance(item, dict):
        for v in item.values():
            out += candidate_paths_from_tool(v, _depth + 1)
    elif isinstance(item, (list, tuple)):
        for v in item:
            out += candidate_paths_from_tool(v, _depth + 1)
    elif isinstance(item, str):
        s = item.strip()
        if s[:1] in ("{", "["):
            # `arguments` thường là chuỗi JSON: giải mã trước, kẻo dấu \ bị nhân đôi.
            try:
                return candidate_paths_from_tool(json.loads(s), _depth + 1)
            except Exception:
                pass
        for tok in _TOOL_TOKEN_RE.findall(s):
            tok = tok.rstrip(".,;:!?…")
            if _TOOL_PATH_RE.search(tok):
                out.append(tok)
    seen, uniq = set(), []
    for p in out:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    return uniq


def collect_turn_files(reply_text: str, written_paths: list, t0: float,
                       cwd: str = None, exclude: set = None, vault_root: str = None) -> list:
    """Danh sách file đáng gửi trả về kênh chat sau 1 lượt.

    Ứng viên = file agent ghi bằng tool Write (written_paths) + đường dẫn tuyệt đối
    nhắc trong câu trả lời cuối + đường dẫn TƯƠNG ĐỐI trong vault nhúng dạng markdown
    (![](attachments/x.png) - ảnh Javis tạo) khi có vault_root. Chỉ giữ file THẬT SỰ
    vừa thay đổi trong lượt (mtime >= t0) - nhắc tới file cũ sẽ không spam gửi lại; muốn
    gửi file cũ thì agent gọi endpoint /telegram/send-file. exclude = set path (normcase)
    đã gửi trong lượt qua endpoint, tránh gửi trùng.
    """
    cands = []
    for p in (written_paths or []):
        try:
            pp = Path(str(p))
            if not pp.is_absolute() and cwd:
                pp = Path(cwd) / pp
            cands.append(str(pp))
        except Exception:
            continue
    cands += extract_paths(reply_text)
    # Ảnh/tệp Javis tạo trong lượt thường được NHÚNG dạng path tương đối trong vault
    # (![](attachments/x.png)); resolve về gốc vault để tự đính kèm về ĐÚNG phiên chat.
    cands += resolve_vault_relative(reply_text, vault_root)

    seen = set(exclude or ())
    out = []
    for c in cands:
        try:
            rp = os.path.normpath(os.path.abspath(c))
            key = os.path.normcase(rp)
            if key in seen:
                continue
            p = Path(rp)
            if not p.is_file():
                continue
            if any(part in _EXCLUDE_PARTS for part in p.parts):
                continue
            st = p.stat()
            if not (0 < st.st_size <= MAX_FILE_MB * 1024 * 1024):
                continue
            if st.st_mtime < t0 - 2:   # chỉ file vừa tạo/sửa trong lượt này
                continue
            seen.add(key)
            out.append(rp)
            if len(out) >= MAX_FILES_PER_TURN:
                break
        except Exception:
            continue
    return out


# ============================================================
# Hạ khối điều khiển xuống chữ cho kênh không phải web
# ============================================================
# Javis nhúng khối điều khiển dạng HTML comment ở cuối câu trả lời cho dashboard
# đọc (hiện chỉ còn JAVIS_ASK - vẽ nút lựa chọn). Kênh chữ thuần như Telegram không
# hiểu mấy khối này, mà md_to_mdv2 chỉ escape chứ không bóc, nên không lọc là người
# dùng nhìn thấy nguyên cụm "<\!\-\- JAVIS\_ASK: ...".
# Regex để CHUNG cho mọi JAVIS_*, không liệt kê từng tên: khối lạ (vd JAVIS_METRICS
# thời còn bảng số liệu, hoặc ký ức cũ trong brain còn nhắc) thì lặng lẽ rơi mất
# thay vì lọt nguyên xi ra chat.
_CTRL_RE = re.compile(r"<!--\s*JAVIS_([A-Z_]+):\s*([\s\S]*?)\s*-->")
_MAX_ASK_OPTS = 4


def _ask_to_text(payload: str) -> str:
    """JSON của khối JAVIS_ASK -> câu hỏi + danh sách đánh số. JSON hỏng -> chuỗi rỗng.

    Người dùng Telegram nhắn lại "1" là xong: Javis đọc "1" trong ngữ cảnh câu hỏi
    vừa hỏi thì tự hiểu, không cần lưu state.
    """
    try:
        o = json.loads(payload)
    except Exception:
        return ""
    if not isinstance(o, dict):
        return ""
    q = str(o.get("question") or "").strip()
    opts = [x for x in (o.get("options") or [])
            if isinstance(x, dict) and str(x.get("label") or "").strip()]
    if not q or not opts:
        return ""
    lines = [q]
    for i, x in enumerate(opts[:_MAX_ASK_OPTS], 1):
        lines.append(f"{i}. {str(x['label']).strip()}")
    return "\n".join(lines)


SILENT_MARK = "[SILENT]"


def is_silent_report(text: str) -> bool:
    """True when a background answer carries the [SILENT] flag: "nothing to report, do not notify".

    The flag counts when it OPENS the answer or CLOSES it (0.408.0). Models told "start with [SILENT] when there is
    nothing to report" often write a sentence first and put the flag last ("I will check the failed POSCake runs.
    [SILENT]"), and that leaked into the bell as a report (owner, 2026-10-29). A flag in the middle of prose is the
    model explaining something, so it does not count. Control blocks, whitespace, quotes and markdown emphasis
    around the flag are ignored.
    """
    def _sach(dong: str) -> str:
        return dong.strip().strip("`*_>").strip()

    dong = [d for d in (_sach(x) for x in strip_control_blocks(text or "").splitlines()) if d]
    if not dong:
        return False
    return dong[0].upper().startswith(SILENT_MARK) or dong[-1].upper().endswith(SILENT_MARK)


def strip_control_blocks(text: str) -> str:
    """Bóc mọi khối <!-- JAVIS_*: ... --> khỏi text.

    JAVIS_ASK -> thay bằng câu hỏi + danh sách đánh số. Khối khác -> bỏ hẳn.
    Khối sai cú pháp cũng bị bỏ: một khối hỏng KHÔNG được phép nuốt mất câu trả lời.
    """
    def _sub(m):
        if m.group(1) == "ASK":
            t = _ask_to_text(m.group(2))
            return ("\n\n" + t) if t else ""
        if m.group(1) == "CARD":
            # 0.201.0: a chart, number tiles or buttons the dashboard draws; text channels get the plain version.
            import chat_cards
            t = chat_cards.card_to_text(m.group(2))
            return ("\n\n" + t) if t else ""
        return ""

    out = _CTRL_RE.sub(_sub, text or "")
    return re.sub(r"\n{3,}", "\n\n", out).strip()
