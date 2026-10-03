# Adding a language to Javis

*[Tiếng Việt](them-mot-ngon-ngu.md) · **English***

The Vietnamese file is the maintainer's original; this translation follows it, and was checked against the code when it was written.

This document is the **acceptance test** for the whole multilingual layer. If adding a language
forces you to edit a file that is not on the list below, the architecture is broken somewhere:
**fix the architecture first, do not quietly patch one spot and move on**.

The full design lives in [`2026-08-da-ngon-ngu-spec.md`](2026-08-da-ngon-ngu-spec.md) (the
multilingual spec, in Vietnamese). This file is the to-do list.

Running example throughout: adding **Thai (`th`)**.

---

## READ FIRST: Javis already answers in Thai

Without registering anything, a user who types in Thai gets an answer in Thai. Since 0.35.0
the REPLY language is handled by the **model**: the prompt tells it to follow the language the
user just wrote in, and it can do that for every language.

So what does registering get you? Exactly four things, all in places where **there is no model
in the loop**:

| What you get | Without registering |
|--------------|---------------------|
| Translatable on-screen text | the interface shows English (since 0.66.0; Vietnamese before that) |
| A TTS voice in the right language | read aloud with the Vietnamese voice, sounds like a broken machine |
| A matching number format (`number_locale`) | numbers formatted the Vietnamese way. Time zone and currency are NOT derived from the language either way: they stay at the Vietnamese defaults until the user changes them (see "What you do **not** need to do") |
| The token-saving shortcut can switch on | still works, only costs more |

In other words this is work you **should** do, not work you **must** do before Javis can speak
that language. Do not make anyone wait for all four steps below before inviting Thai users in.

---

## Four required steps

### 1. Declare the language in the registry

In `server/lang_registry.py`, add an entry to `LANGS`:

```python
"th": Lang(
    code="th", native="ไทย", english="Thai", script="thai", rtl=False,
    stopwords=("และ", "ที่", "เป็น", "ของ", "ไม่", ...),   # function words, used for DETECTION
    request_words=("thai", "tieng thai", "tiếng thái", "ภาษาไทย"),  # how users ASK for this language
    stt="th", tts={"edge": "th-TH-PremwadeeNeural", ...},
    tz_default="Asia/Bangkok", currency="THB", first_day=0,
    number_locale="th-TH", plural=True,
    nudge="...", weekdays=(...), clock_template="...",
    lang_directive="Thai",                                 # the language NAME, spliced into a prompt sentence
),
```

Fields that people tend to get wrong:

- **`stopwords`** are the evidence `lang.detect()` scores against, and the detector now only
  serves the SAFETY GATES and the VOICE; it no longer decides the reply language. Pick function
  words that are **common and distinctive** for that language, and **only function words, never
  nouns**: nouns cross languages (a trial once added "week" and "report" to English, and Dutch
  sentences turned into English). Also avoid words that collide with Vietnamese typed without
  diacritics; the comments above `lang._TU_NGOAI` and on the `en` stopwords in
  `lang_registry.py` list the words already excluded and why. Stopwords are only consulted for
  Latin-script text: a non-Latin script such as Thai is recognised by its Unicode range (see
  below) before any word scoring happens.
- **`request_words`** are the names users type when they explicitly ASK for this language ("reply
  in Thai", "trả lời bằng tiếng Thái"), written in any language and matched without diacritics.
  `lang._yeu_cau_thang()` looks for them next to a reply verb. They are not generic request
  phrases.
- **`lang_directive`** is a language name, not a sentence: it is inserted into Vietnamese prompt
  sentences such as "Viết TOÀN BỘ câu trả lời bằng {lang_directive} ({code})" (write the whole
  answer in ...). The existing entries use `"Tiếng Việt"` and `"English"`.
- **`weekdays`** follow `datetime.weekday()`, so **0 = Monday**. Cron uses 0 = Sunday.
  `cron_util._ten_thu()` already corrects for this offset; do not correct it a second time.

`tests/python/test_lang_bat_bien.py` requires `nudge`, `weekdays` (exactly 7),
`clock_template` (with all of `{hm}`, `{weekday}`, `{date}`, `{tz}`) and `lang_directive` to be
filled in for every registered language.

For a non-Latin script, also add its Unicode range to `lang._KHOANG_CHU` (Thai is already
there). That table is checked **in priority order**, not first-match-wins: Japanese must come
before Chinese because Japanese text mixes kanji and kana.

### 2. Copy and translate the interface dictionary

```
cp dashboard/i18n/vi.json dashboard/i18n/th.json
```

Then translate the values (`vi.json` and `en.json` carry exactly the same keys, so if you
translate from English, copying `en.json` works just as well). **You do not have to translate
everything at once.** A missing key falls back to `en`, then to `vi`, then to the key name
itself (`dashboard/i18n/index.js`): the interface never breaks, it is just mixed-language until
the translation fills in.

Two technical keys to change: `_meta.name` and `_meta.number_locale`. `_meta.number_locale` is
what the dashboard passes to `toLocaleString`. The name shown in the language picker does not
come from `_meta.name`: the picker is built from the registry (`lang_registry.cho_giao_dien()`,
field `native`), so step 1 is what makes the language appear there.

### 3. Write the vocabulary for the safety gates (**optional, but read this part carefully**)

`server/lexicon/th.py`, declaring all 12 set names listed in `lexicon.BAT_BUOC` (the required
sets: `DENY`, `ALLOW`, `WRITE_INTENT`, `STATE_REF`, `FALSE_ACTION`, `ACTION_VERBS`,
`QUANTITATIVE`, `CAPABILITY_DENIAL`, `PROMISE`, `REMEMBER`, `DENSE`, `STUCK`).

**Not writing it is fine. Writing HALF of it is more dangerous than not writing it.**

This is the easiest place to go wrong in the whole multilingual layer, so here is exactly why:

- **No `th.py`**: `lexicon.get("th")` returns `None`, the gates know they are blind, the
  token-saving shortcut turns itself off, and the guard rails fall back to the secondary-model
  layer. Javis runs **correctly**, it just costs more.
- **A `th.py` whose sets exist but are thin**, `DENY` above all: the gate believes it can read
  Thai. A sentence that matches `ALLOW` goes straight through, and nothing stops it. **A leak,
  and a silent one.** (This is the real bug that created the layer: English `DENY` had no
  "orders", so "summarize my orders" slipped through the shortcut and the model invented a
  number.)

So either write all 12 sets properly, or do not create the file. `lexicon/__init__.py` checks
at load time (`_kiem_parity`) that every name in `BAT_BUOC` is declared. Note what that check
does on failure: it raises `ImportError`, which `lexicon.get()` catches, so a file missing a
whole set is treated as **no lexicon at all** (safe, but silent: nothing turns red). It cannot
tell a complete set from a thin one; only your own care can. `test_lang_bat_bien.py` checks the
other end: every lexicon that loads must belong to a language in the registry.

Writing it after you already have real users is fine too: that is the right order, not laziness.

### 4. Run the tests

```
python tests/run.py
```

The multilingual tests live in `tests/python/`:

- `test_lang_bat_bien.py` checks the registry invariants (the required fields above, lexicon
  sets) and scans `server/` and `dashboard/` for hard-coded language branching such as
  `lang == "vi"`.
- `test_locale.py` guards the things that tend to grow back (UTC+7 pinned in code, locale
  inferred from language, the cron weekday offset).
- `test_da_ngon_ngu.py` covers detection, language resolution and the gates per lexicon.

None of these compares keys between the interface dictionaries; individual feature tests in
`tests/js/` and `tests/python/` check their own keys in `vi.json` and `en.json` only.

Thai is also the tests' stand-in for "a language with no lexicon": `test_da_ngon_ngu.py`
asserts `lexicon.get("th") is None` and that a Thai sentence is refused the shortcut for
`no_lexicon`. If you add `server/lexicon/th.py` for real, move those canaries to another
unregistered language in the same change.

---

## Optional steps, can be done later

### 5. Skill descriptions per language

In `SKILL.md`, add a `description_th` key (and `name_th` if the name needs translating too)
next to the original:

```yaml
---
name: Notes
description: Lưu tin nhắn hiện tại nguyên văn vào sources/ ...
description_en: Save the current message verbatim into sources/ ...
description_th: ...
group: AI
---
```

If it is missing, it falls back to the original `description` (`skill_router.theo_ngon_ngu`).
The skill description is the **matching surface** between what the user just typed and the
skill list, so the same language routes more sharply, but a different language still works.

The translation is subject to the same `SKILL_DESC_MAX` ceiling (150 characters) as the
original, because it goes into the same place in the prompt. `system_sync._cap_desc` trims
every description key, not just the original one.

### 6. Server-side text, Connections store, starter brain, website

Since 0.67.0, server-side text follows the interface language of the DEVICE making the request
(cookie `javis_lang`, set by `dashboard/i18n/index.js`). Anything with no Thai version yet is
shown in English (the order is: chosen language, then English, then Vietnamese, see
`lang_registry.chon_ban_dich`), so none of the steps below is required before inviting Thai
users in.

- **Server messages** are written in two versions right where they are used:
  `localefmt.chu("Đã lưu", "Saved")` ("Đã lưu" = "Saved"). There is no slot for a third version
  yet, so Thai shows English. When it is really needed, extend `chu()` to accept more versions
  keyed by language code; do not branch `if lang == ...` at the call sites. Note that `chu()`'s
  `**bien` keyword arguments are already taken by the format variables (`n=3` in
  `chu("Đã lưu {n} mục", "Saved {n} items", n=3)`), so the extra versions need their own
  parameter.
- **Connections store (Kho Kết nối):** copy `system/mcp-catalog.en.json` to
  `system/mcp-catalog.th.json` and translate the text. Wizard steps and setup links are matched
  by POSITION, so keep exactly the same count. Until the file exists, Thai readers get the
  English overlay; once it exists, any connector or field missing from it shows the Vietnamese
  original (`server/catalog_i18n.py`).
- **Starter files of a new brain:** add a `"th"` version for each entry in `HAT_GIONG` in
  `server/brain_seed_i18n.py`.
- **Cron descriptions:** the phrases that turn a cron expression into words ("every day",
  "every {n} minutes"...) live in `cron_util._CHU_CRON`. Weekday names come from the registry,
  but a language with no entry there falls back to the Vietnamese phrases, so add a `"th"` entry.
- **Currency symbol:** `localefmt._TIEN` only knows VND, USD and EUR; any other currency prints
  as the number followed by its code ("1,234.00 THB"), which is correct but plain.
- **Website:** add `website/th/index.html`, plus an `hreflang` line in the `<head>` of the other
  versions and a link in their visible language switchers (header and footer).

### 7. Documentation

User documentation is translated by hand, not through a dictionary. Since 0.66.0 the root
README (`README.md`) is the **English** version; README translations live in
`docs/i18n/<code>/README.md` (Vietnamese: `docs/i18n/vi/`), and the language bar at the top of
README.md must gain the new language. Other documents still follow the old convention:
`QUICKSTART.en.md`, `docs/en/*.md`. Each version carries a cross-link line at the top of the
file, and translated pairs are registered in `CAP` in `tests/python/test_tai_lieu_song_ngu.py`,
which checks those links.

---

## What you do **not** need to do

Listed here because this is where people tend to overdo it:

- **Do not** translate the system prompt or `CLAUDE.md`. The prompt stays in Vietnamese; the
  `# === NGÔN NGỮ ===` (language) block at the end is what decides which language Javis answers
  in. The model reads Vietnamese instructions and answers in Thai, which is perfectly normal,
  and one prompt set per language is one more set to drift out of sync.
- **Do not** translate the section labels in the prompt (`# === SKILL KHẢ DỤNG` (available
  skills), `# === KÊNH HỘI THOẠI HIỆN TẠI` (current chat channel)...). They are **measurement
  markers**: `context_runtime` counts tokens per section by matching those exact strings
  (`context_runtime._SYSTEM_MARKERS`). Translating them silently stops the measurement for
  exactly the group of users you just added.
- **Do not** infer locale from language. Reading the English interface while living in Vietnam
  is perfectly normal; time zone and currency live in `server/localefmt.py` and are chosen
  separately. (The `tz_default`, `currency` and `first_day` fields of `Lang` are not read
  anywhere yet.)
- **Do not** write `if lang == "th"` anywhere outside `lang_registry.py`. A test guards against
  this kind of branching (`test_lang_bat_bien.py`), but its pattern only catches the codes `vi`
  and `en`, so a hard-coded `"th"` would pass unnoticed: the rule is on you.

---

## REGISTERED languages

Again: this is NOT the list of languages Javis can speak. Javis can answer in any language.
This is the list of languages that have their own interface, voice and safety gates.

| Code | Name | Interface dictionary | Gate vocabulary | Skill descriptions |
|------|------|----------------------|-----------------|--------------------|
| `vi` | Tiếng Việt | complete | complete | original |
| `en` | English | complete | complete | complete |
