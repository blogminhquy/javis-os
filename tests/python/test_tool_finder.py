"""tool_finder: the ranking behind javis_search_tools in the lazy tier.

    python tests/run.py tool_finder

Each case below is a request the old word count got wrong on a real brain (2026-11-19): a Vietnamese request
against English tool descriptions, a syllable of a phrase matching an account label, the skill loader winning
every search on description length, three accounts returning the same tool three times, a name without its
source prefix.
"""
from _paths import ROOT, SERVER  # noqa: E402,F401
import os
import tempfile

os.environ.setdefault("JAVIS_STATE_DIR", tempfile.mkdtemp(prefix="javis-toolfinder-"))

import tool_finder  # noqa: E402

_fails = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        _fails.append(name)


def tool(ns, name, desc, label=""):
    return {"fn": f"{ns}__{name}", "name": name, "namespace": ns, "label": label or ns, "description": desc}


_SKILL_DESC = ("Load a skill by name and follow it. Skills: " + ", ".join(
    f"skill-{i} for order report revenue cost history message post product customer" for i in range(60)))

POS_TOOLS = [
    ("pos_describe", "Describe this POS connection and shop."),
    ("pos_address", "Look up provinces, districts and communes for an address."),
    ("pos_auto_voice", "Toggle the automatic voice announcement on new orders."),
    ("pos_list_orders", "List orders of the shop, filter by status and created date."),
    ("pos_get_order", "Get one order by id with its items and payment."),
    ("pos_statistic_revenue", "Revenue statistics: total sales and order count per day for a date range."),
    ("pos_list_products", "List products and variations with price and stock."),
    ("pos_inventory", "Inventory and stock per warehouse."),
    ("pos_list_customers", "List customers with phone and total spent."),
]


def _pool():
    pool = []
    for shop, label in (("pos-lcx", "Làng Chài Xưa"), ("pos-ngocthu", "Ngọc Thu"), ("pos-ab", "AB Store")):
        for name, desc in POS_TOOLS:
            pool.append(tool(shop, name, desc, label))
    for acc, label in (("zalo-vu", "Javis Vũ"), ("zalo-quy", "Minh Quý")):
        pool += [
            tool(acc, "zalo_send_typing", "Show the typing indicator in a Zalo thread.", label),
            tool(acc, "zalo_send_message", "Send a text message to a Zalo user or group thread.", label),
            tool(acc, "zalo_get_history", "Get the message history of a Zalo thread, newest first.", label),
            tool(acc, "zalo_list_threads", "List recent Zalo conversations (threads).", label),
        ]
    pool += [
        tool("google-ads", "ads_campaign_report", "Campaign performance report: cost, clicks, conversions.",
             "Google Ads"),
        tool("google-ads", "ads_list_campaigns", "List campaigns of the Google Ads account.", "Google Ads"),
        tool("google-sheets", "sheets_get_values", "Read cell values from a Google Sheets spreadsheet.",
             "Google Sheets"),
        tool("google-sheets", "sheets_append", "Append rows to a Google Sheets spreadsheet.", "Google Sheets"),
        tool("javis", "javis_use_skill", _SKILL_DESC, "Javis"),
        tool("javis", "javis_search_tools", "Search tools.", "Javis"),
    ]
    return pool


POOL = _pool()
IDX = tool_finder.Index(POOL)


def top(query, k=3):
    res = IDX.search(query)
    return [t["fn"] for t, _s in res["hits"][:k]], res


# ---- Vietnamese request, English descriptions ----
fns, res = top("Xem doanh thu hôm nay trên POS Làng Chài Xưa")
check("doanh thu + named shop: revenue tool first", fns[:1] == ["pos-lcx__pos_statistic_revenue"])
check("doanh thu + named shop: stays inside that shop", all(f.startswith("pos-lcx__") for f in fns))
check("'thu' of 'doanh thu' does not pick the account Ngọc Thu",
      "pos-ngocthu" not in res["scope"])

fns, _ = top("lấy lịch sử tin nhắn Zalo")
check("lịch sử tin nhắn zalo: history tool first", fns and fns[0].endswith("__zalo_get_history"))
check("lịch sử tin nhắn zalo: typing indicator is not first", not fns[0].endswith("zalo_send_typing"))

fns, _ = top("chi phí Google Ads tuần này")
check("chi phí google ads: campaign report first", fns[:1] == ["google-ads__ads_campaign_report"])
check("chi phí google ads: Sheets is not first", not fns[0].startswith("google-sheets"))

fns, _ = top("đơn hàng chưa giao")
check("đơn hàng: an order tool first", fns and "order" in fns[0])

# ---- the skill loader no longer wins on description length ----
for q in ("doanh thu POS", "chi phí quảng cáo Google Ads", "đơn hàng hôm nay"):
    fns, _ = top(q)
    check(f"'{q}': javis_use_skill is not first", fns and fns[0] != "javis__javis_use_skill")

# ---- meta tools are never results ----
check("meta tool javis_search_tools never listed",
      all(t["fn"] != "javis__javis_search_tools" for t, _s in IDX.search("search tools")["hits"]))

# ---- exact name ----
fns, _ = top("zalo_get_history", k=5)
check("exact tool name: every account's copy, nothing else",
      sorted(fns) == ["zalo-quy__zalo_get_history", "zalo-vu__zalo_get_history"])

# ---- naming only a source lists it ----
res = IDX.search("zalo")
check("only a source named: browse mode", res["browse"] is True)
check("only a source named: lists that source's tools",
      {t["namespace"] for t, _s in res["hits"]} == {"zalo-vu", "zalo-quy"})
res = IDX.search("google ads")
check("'google ads': only Google Ads tools, not Sheets",
      res["hits"] and {t["namespace"] for t, _s in res["hits"]} == {"google-ads"})

# ---- empty and nonsense ----
check("empty query: no hits", IDX.search("")["hits"] == [])
check("nonsense query: no hits", IDX.search("zzzxxqqq")["hits"] == [])

# ---- spelling ----
fns, res = top("lịch sử tin nhắn zlao")
check("misspelt source 'zlao': history tool still first", fns and fns[0].endswith("__zalo_get_history"))
res = IDX.search("doanh thu Lang Chai Xua")
check("source named without diacritics still scopes to it", res["scope"] == ["pos-lcx"])

# ---- identical tools of several accounts are grouped ----
res = IDX.search("doanh thu POS")
groups = tool_finder.group_hits(res["hits"])
check("three shops' revenue tool: one group of three",
      any(len(g) == 3 and g[0]["name"] == "pos_statistic_revenue" for g in groups))

# ---- names for javis_run_tool ----
fns_all = [t["fn"] for t in POOL]
s = tool_finder.suggest_names("zalo_get_history", fns_all)
check("suggest_names: bare tool name -> every account's copy",
      sorted(s) == ["zalo-quy__zalo_get_history", "zalo-vu__zalo_get_history"])
s = tool_finder.suggest_names("google-ads__ads_campain_report", fns_all)
check("suggest_names: typo -> the real name", s[:1] == ["google-ads__ads_campaign_report"])
check("suggest_names: empty -> []", tool_finder.suggest_names("", fns_all) == [])

# ---- text helpers ----
check("fold drops diacritics and đ", tool_finder.fold("Làng Chài Xưa đơn") == "lang chai xua don")
check("words splits snake and camel case", tool_finder.words("getOrderHistory zalo_send") ==
      ["get", "order", "history", "zalo", "send"])

if _fails:
    print(f"\n{len(_fails)} FAILED")
    raise SystemExit(1)
print("\nall ok")
