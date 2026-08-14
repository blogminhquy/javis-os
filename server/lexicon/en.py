"""Bộ từ vựng TIẾNG ANH - viết mới cho ngang bằng bản tiếng Việt.

Đây không phải bản dịch của `vi.py`. Nó được soạn để **bịt đúng những lỗ đã đo được** khi
tiếng Anh mới chỉ được phục vụ một nửa. Ca kiểm chứng trên mã trước khi có file này:

    "summarize my orders"           -> LỌT đường tắt (ALLOW `summarize` khớp, DENY không có
                                       "orders") -> model bịa số đơn hàng
    "how much did we make in july"  -> LỌT (không có "revenue", không có "today")
    "remind me tomorrow at 7am"     -> không lọt, nhưng vì `intent_uncertain` chứ không phải
                                       vì DENY bắt được - tức là đúng do may, không do luật

Nguyên tắc soạn: nhóm DENY phải phủ ĐÚNG những khái niệm mà bản tiếng Việt phủ, kể cả khi
tiếng Anh diễn đạt bằng từ hoàn toàn khác. Hụt một từ ở DENY nghĩa là một câu hỏi cần dữ liệu
thật đi vào đường không phát tool, và model trả lời bằng con số tự nghĩ ra.

Nhóm ALLOW thì ngược lại, soạn HẸP: thừa một từ ở ALLOW cũng dẫn tới đúng tai nạn đó. Khi
phân vân thì bỏ ra khỏi ALLOW, vì rơi vào `intent_uncertain` chỉ tốn thêm token.
"""
import re

DENY = (
    ("attachment", re.compile(
        r"\b(file|files|attachment|attached|document|doc|pdf|spreadsheet|image|photo|"
        r"screenshot|uploaded|i uploaded|the document i|this image|this file)\b"
    )),
    ("url_reference", re.compile(r"(https?://|www\.)")),
    ("live_data", re.compile(
        # thời điểm
        r"\b(today|yesterday|tomorrow|now|right now|current|currently|latest|recent|"
        r"this week|this month|this quarter|this year|last week|last month|last quarter|"
        r"so far|to date|year to date|ytd|mtd|"
        # số liệu kinh doanh - chỗ bản cũ hụt nhiều nhất
        r"revenue|sales|orders|order count|invoice|invoices|refund|refunds|"
        r"inventory|stock level|in stock|out of stock|profit|margin|expenses|spend|"
        r"how much did|how many did|how much have|how many have|"
        # nguồn ngoài
        r"weather|news|stock price|share price|exchange rate|gold price|"
        r"my email|my inbox|my calendar|my schedule|my messages|unread)\b"
    )),
    ("external_source", re.compile(
        r"\b(web|internet|google|drive|gmail|calendar|github|repository|repo|database|"
        r"api|mcp|tool|tools|vault|obsidian|slack|notion|airtable|facebook|instagram|"
        r"tiktok|zalo|telegram|shopify|stripe|pos)\b"
    )),
    ("side_effect", re.compile(
        r"\b(send|email him|email her|email them|message|text them|delete|remove|cancel|"
        r"create|add a|book|schedule|remind me|set a reminder|set up a|upload|publish|"
        r"post to|post it|update the|edit the|change the|rename|move the|save (it |this )?to|"
        r"write to|make a note|add to my)\b"
    )),
    ("conversation_state", re.compile(
        r"\b(previously|earlier|last time|before|we discussed|you said|i said|you told me|"
        r"do you remember|my last message|this conversation|as i mentioned|like i said|"
        r"that one|the same|continue|carry on|go on|keep going)\b"
    )),
    ("agentic", re.compile(
        r"\b(execute|run|check my|check the|look up|search for|find my|find the|fetch|"
        r"open my|pull up|go through|review my|analyze my|analyse my)\b"
    )),
)

ALLOW = (
    ("conversation", re.compile(r"^(hello|hi|hey|thanks|thank you|good morning|good evening)\b")),
    ("explanation", re.compile(
        r"\b(what is|what are|explain|why is|why do|why does|how does|definition|concept|"
        r"difference between|meaning of|stands for)\b"
    )),
    ("writing", re.compile(
        r"\b(rewrite|reword|draft|headline|tagline|brainstorm|outline|name ideas|"
        r"come up with|suggest some|give me ideas)\b"
    )),
    ("transform", re.compile(r"\b(translate|paraphrase|shorten|make it shorter|simplify)\b")),
    ("reasoning", re.compile(
        r"\b(calculate|compute|solve|pros and cons|trade[- ]?offs?|compare these|"
        r"which is better)\b"
    )),
)

STATE_REF = re.compile(
    r"\b(previously|earlier|last time|before|remember|that one|the same|same as before|"
    r"you said|i said|as mentioned|continue|carry on)\b"
)

WRITE_INTENT = re.compile(
    r"\b(send|email|message|delete|remove|cancel|create|make|add|update|edit|change|"
    r"rename|move|publish|post|upload|book|schedule|remind|save|write|set up|set a)\b"
)

ACTION_VERBS = (
    r"(?:sent|send|deleted|delete|removed|remove|created|create|updated|update|"
    r"published|publish|posted|post|booked|book|scheduled|schedule|uploaded|upload|"
    r"saved|save|emailed|email|messaged|message|added|add|cancelled|canceled|cancel)"
)

FALSE_ACTION = re.compile(
    r"(?i)(?:"
    r"\bi\s+(?:have\s+|just\s+|already\s+)?" + ACTION_VERBS + r"\b"
    r"|\bi've\s+(?:just\s+|already\s+)?" + ACTION_VERBS + r"\b"
    r"|\bwe\s+(?:have\s+|just\s+)?" + ACTION_VERBS + r"\b"
    r"|\bjavis\s+(?:has\s+|just\s+)?" + ACTION_VERBS + r"\b"
    r"|\bsuccessfully\s+" + ACTION_VERBS + r"\b"
    r"|\b(?:was|were|has been|have been)\s+(?:sent|deleted|removed|created|updated|"
    r"published|posted|booked|scheduled|uploaded|saved|cancelled|canceled)\b"
    r"|(?:^|[.!?\n]\s*)(?:done|all set|all done)\b"
    r"|\b" + ACTION_VERBS + r"\s+(?:it |them |that )?successfully\b"
    r")"
)

QUANTITATIVE = re.compile(
    r"(?i)(?:\d[\d.,]*\s*(?:%|percent|\$|usd|eur|gbp|k\b|m\b|bn\b|million|billion|"
    r"orders?|customers?|visits?|clicks?|users?|hours?|hrs?|minutes?|mins?|days?)"
    r"|(?:revenue|sales|profit|margin|cost|costs|expenses|total|spend)\s*(?:is|was|:)?\s*[\$]?\d"
    r"|[\$]\s*\d)"
)

CAPABILITY_DENIAL = (
    "i do not have access to tools", "i don't have access to tools",
    "no tools available", "i don't have any tools", "i cannot access tools",
    "i'm not able to access", "i am unable to access",
)

PROMISE = (
    ("get_back_to_you", re.compile(
        r"\b(i(?:'| wi)?ll|i will|we(?:'| wi)?ll|we will)\s+"
        r"(get back to you|report back|update you|let you know|keep you posted|"
        r"follow up|circle back|come back to you)\b"
    )),
    ("checking_will_report", re.compile(
        r"\b(i(?:'|)m|i am|we(?:'|)re|we are)\s+"
        r"(checking|looking into|investigating|working on|running|analyzing|analysing|"
        r"reviewing|digging into|scanning)\b"
        r"[^.!?]{0,90}?\b(let you know|update you|report back|get back|tell you|share)\b"
    )),
    ("give_me_a_moment", re.compile(
        r"\b(give me|just)\s+(a|one)\s+(moment|minute|min|sec|second|bit)\b"
        r"|\bhang on\b|\bbear with me\b|\bone moment\b"
    )),
    ("once_done", re.compile(
        r"\b(once|when|after)\s+(i|we)\s+(?:have\s+)?"
        r"(finish|finished|done|complete|completed|get|got)\b"
        r"[^.!?]{0,50}?\b(i(?:'| wi)?ll|i will|we(?:'| wi)?ll|we will)\b"
    )),
    ("will_wait_then", re.compile(
        r"\b(i(?:'| wi)?ll|i will)\s+(wait|monitor|watch|keep an eye)\b"
        r"[^.!?]{0,60}?\b(then|and)\b[^.!?]{0,30}?"
        r"\b(summar|report|update|tell you|let you know)"
    )),
)

REMEMBER = re.compile(
    r"(remember this|remember that|keep in mind|note that|make a note|save this|"
    r"store this|don't forget|do not forget|for future reference|remember i)", re.I
)

DENSE = re.compile(
    r"(what is|what are|how does .{0,20}work|framework|methodology|principle|process for|"
    r"steps to|concept of|definition of|model for|approach to)", re.I
)

STUCK = ("i don't have that information", "i do not have that information",
         "no information about", "i'm not sure about that", "i am not sure about that",
         "let me transfer you", "transfer you to", "contact our team",
         "reach out to our team", "a human will", "our staff will",
         "i can't answer that", "i cannot answer that")
