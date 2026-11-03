"""Inbox row actions that reach the platform (0.447.0): view profile, block, delete.

The owner asked for what Messenger's own row menu offers ("View profile", "Block", "Delete chat"), on Facebook Pages
and on Zalo. What each platform allows through its API decides what each action really does, and the dashboard says
so before anyone clicks:

  - Profile. Messenger: name and picture from the User Profile API; Facebook never gives an app the person's profile
    link. Instagram: name, @username, picture and a link to instagram.com/<username>. Zalo personal account: display
    name, Zalo name, avatar and phone when the person shares it (`javis-zalo friend info`). Groups have no profile.
  - Block. Messenger: the Page's block list (`POST /<page>/blocked` with the PSID). Zalo personal account:
    `javis-zalo friend block`. Instagram and comment threads: the API has no block, so the action is not offered.
  - Delete. A Facebook or Instagram comment thread: the top-level comment is deleted on the platform (its replies go
    with it). Zalo personal account: the conversation is deleted on Zalo (`javis-zalo conv delete`). Messenger and
    Instagram direct messages: Meta lets no app delete them, so only the copy in Javis goes. In every case the
    conversation then leaves the Javis inbox. When the platform refuses, nothing is deleted in Javis either, so the
    owner can retry instead of losing the record of something still online.

Each function takes a conversation as `conversations.chi_tiet` returns it and never raises: errors come back as text.
"""
from __future__ import annotations

import json
from typing import Optional

import channel_accounts
import localefmt

PROFILE, BLOCK, DELETE_REMOTE = "profile", "block", "delete_remote"


def _raw_account(c: dict) -> str:
    key = str(c.get("channel_account_id") or "")
    return key.split(":", 1)[1] if ":" in key else key


def kind(c: dict) -> str:
    """messenger_dm, fb_comment, ig_dm, ig_comment, zalo_private, zalo_group, or "" for any other chat."""
    ch = str(c.get("channel") or "")
    chat = str(c.get("external_chat_id") or "")
    if ch == "messenger":
        if chat.startswith("cmt:"):
            return "fb_comment"
        if chat.startswith("igc:"):
            return "ig_comment"
        if chat.startswith("ig:"):
            return "ig_dm"
        return "messenger_dm"
    if ch == "zalo_personal":
        return "zalo_group" if str(c.get("chat_type") or "") == "group" else "zalo_private"
    return ""


# What each kind of chat can do on its platform. The dashboard reads the same table (`capabilities`).
_CAN = {
    "messenger_dm": {PROFILE, BLOCK},
    "ig_dm": {PROFILE},
    "fb_comment": {DELETE_REMOTE},
    "ig_comment": {DELETE_REMOTE},
    "zalo_private": {PROFILE, BLOCK, DELETE_REMOTE},
    "zalo_group": {DELETE_REMOTE},
}


def capabilities(c: dict) -> list:
    return sorted(_CAN.get(kind(c), set()))


def _no(what: str) -> dict:
    return {"ok": False, "error": localefmt.chu(f"Kênh này không cho {what} qua Javis",
                                                f"This channel does not allow {what} from Javis")}


def _messenger_creds(c: dict) -> dict:
    import messenger_bot
    return messenger_bot.split_credentials(channel_accounts.get_token(_raw_account(c)))


def _graph_error(d: dict, fallback: str) -> str:
    import messenger_bot
    e = (d or {}).get("error") or {}
    return messenger_bot._explain_error(e.get("code"), e.get("message") or fallback, e.get("error_subcode"))


async def _graph(method: str, path: str, token: str, params: Optional[dict] = None, client=None) -> dict:
    import httpx
    import messenger_bot
    own = client is None
    client = client or httpx.AsyncClient(timeout=20)
    try:
        r = await client.request(method, f"{messenger_bot.GRAPH}/{path}", params={**(params or {}), "access_token": token})
        try:
            return r.json() or {}
        except Exception:
            return {"error": {"message": f"HTTP {r.status_code}"}}
    except Exception as e:
        return {"error": {"message": f"{type(e).__name__}: {e}"}}
    finally:
        if own:
            await client.aclose()


def _zalo_conn(c: dict) -> tuple:
    """(session {"home"}, error) of the Zalo personal account a conversation belongs to."""
    import zalo_cli
    import zalo_personal_channel as zc
    conn = zc.ket_noi_theo_id(_raw_account(c))
    home = zalo_cli.home_of(conn) if conn else ""
    if not home:
        return None, localefmt.chu("tài khoản Zalo này chưa đăng nhập hoặc đã tắt", "this Zalo account is not signed in or is off")
    return {"home": home}, ""


async def profile(c: dict) -> dict:
    """{"ok", "name", "username", "picture", "url", "phone", "note"} for the person in a one-to-one chat."""
    k = kind(c)
    if PROFILE not in _CAN.get(k, set()):
        return _no(localefmt.chu("xem trang cá nhân", "viewing a profile"))
    who = str(c.get("external_chat_id") or "")
    base = {"ok": True, "name": str(c.get("customer_name") or c.get("title") or ""), "username": "", "picture": "",
            "url": "", "phone": "", "note": ""}
    if k in ("messenger_dm", "ig_dm"):
        cr = _messenger_creds(c)
        if not cr.get("access_token"):
            return {"ok": False, "error": localefmt.chu("tài khoản Messenger này chưa có token", "this Messenger account has no token")}
        uid = who[3:] if k == "ig_dm" else who
        fields = "name,username,profile_pic" if k == "ig_dm" else "name,first_name,last_name,profile_pic"
        d = await _graph("GET", uid, cr["access_token"], {"fields": fields})
        if d.get("error"):
            return {**base, "note": _graph_error(d, "profile lookup failed")}
        name = str(d.get("name") or " ".join(x for x in (d.get("first_name"), d.get("last_name")) if x) or base["name"])
        out = {**base, "name": name, "picture": str(d.get("profile_pic") or "")}
        if k == "ig_dm" and d.get("username"):
            out.update(username=str(d["username"]), url="https://www.instagram.com/" + str(d["username"]).strip("@/"))
        if k == "messenger_dm":
            out["note"] = localefmt.chu("Facebook không cho ứng dụng lấy link trang cá nhân của khách.",
                                        "Facebook does not give apps a customer's profile link.")
        return out
    sess, err = _zalo_conn(c)
    if not sess:
        return {"ok": False, "error": err}
    import zalo_cli
    ok, data, err = await zalo_cli.run_cli(sess, ["friend", "info"], [who], timeout=40)
    if not ok:
        return {**base, "note": str(err or "")[:200]}
    p = ((data or {}).get("changed_profiles") or {}).get(who) or {}
    return {**base, "name": str(p.get("displayName") or p.get("zaloName") or base["name"]),
            "username": str(p.get("zaloName") or ""), "picture": str(p.get("avatar") or ""),
            "phone": str(p.get("phoneNumber") or "")}


async def block(c: dict) -> dict:
    """Block the person of a one-to-one chat on the platform. {"ok"} or {"ok": False, "error"}."""
    k = kind(c)
    if BLOCK not in _CAN.get(k, set()):
        return _no(localefmt.chu("chặn", "blocking"))
    who = str(c.get("external_chat_id") or "")
    if k == "messenger_dm":
        cr = _messenger_creds(c)
        d = await _graph("POST", f"{cr.get('page_id', '')}/blocked", cr.get("access_token", ""),
                         {"psid": json.dumps([who])})
        if d.get("error") or not d.get(who, True):
            return {"ok": False, "error": _graph_error(d, "block failed")}
        return {"ok": True}
    sess, err = _zalo_conn(c)
    if not sess:
        return {"ok": False, "error": err}
    import zalo_cli
    ok, _d, err = await zalo_cli.run_cli(sess, ["friend", "block"], [who], timeout=40)
    return {"ok": True} if ok else {"ok": False, "error": str(err or "")[:300]}


async def delete_remote(c: dict) -> dict:
    """Delete the conversation (or the comment) on the platform where it can be. {"ok", "remote": bool}."""
    k = kind(c)
    if DELETE_REMOTE not in _CAN.get(k, set()):
        return {"ok": True, "remote": False}
    chat = str(c.get("external_chat_id") or "")
    if k in ("fb_comment", "ig_comment"):
        cr = _messenger_creds(c)
        cid = chat.split(":", 1)[1]
        d = await _graph("DELETE", cid, cr.get("access_token", ""))
        if d.get("error") or not d.get("success", True):
            e = (d.get("error") or {})
            # Already gone on the platform (deleted by hand, or by the commenter): nothing left to delete there.
            if str(e.get("code")) == "100" and "does not exist" in str(e.get("message") or ""):
                return {"ok": True, "remote": False}
            return {"ok": False, "error": _graph_error(d, "delete failed")}
        return {"ok": True, "remote": True}
    sess, err = _zalo_conn(c)
    if not sess:
        return {"ok": False, "error": err}
    import zalo_cli
    ok, _d, err = await zalo_cli.run_cli(sess, ["conv", "delete"], [chat],
                                         options=["-t", "1" if k == "zalo_group" else "0"], timeout=40)
    return {"ok": True, "remote": True} if ok else {"ok": False, "error": str(err or "")[:300]}
