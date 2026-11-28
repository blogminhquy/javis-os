"""End-to-end encrypted Zalo messages: recognise the ciphertext and show a sentence instead.

Owner report 28/11/2026: after signing a personal Zalo account into Javis, a private chat showed lines like
"AzMo6XoI2Qow1goSlQVA+XAu8TEhg5qq..." instead of the messages, old and new alike. That chat has Zalo's end-to-end
encryption turned on. Zalo then hands every device the Signal-protocol ciphertext, and only the devices that joined
the encryption hold the keys. javis-zalo signs in like Zalo Web, which never gets those keys, so the text cannot be
decrypted here at all. Decoded, such a line starts with a type byte (1-3), the version byte 0x33 and a protobuf field,
exactly the layout of a Signal `PreKeySignalMessage` / `SignalMessage`.

Left as it was, the ciphertext also did harm: the bot was handed it as a customer message (it can only guess at it),
and the inbox counted it as the customer asking for A.I. ("Có người gọi A.I. 2 lần...").
"""
from __future__ import annotations

import base64
import binascii
import re

import localefmt

MIN_LEN = 60        # a Signal message is well over 40 bytes; a short base64-looking word is never one
_B64 = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")
# The first protobuf key after the version byte: the fields of SignalMessage (1-4) and PreKeySignalMessage (1-6).
_PROTO_KEYS = {0x08, 0x0A, 0x12, 0x1A, 0x22, 0x28, 0x30}
_VERSIONS = {0x33, 0x44}


def is_ciphertext(text) -> bool:
    """True when `text` is one Signal-protocol ciphertext in base64 and nothing else."""
    s = str(text or "").strip()
    if len(s) < MIN_LEN or not _B64.match(s):
        return False
    try:
        raw = base64.b64decode(s + "=" * (-len(s) % 4), validate=True)
    except (binascii.Error, ValueError):
        return False
    if len(raw) < 40:
        return False
    if raw[0] in (1, 2, 3) and raw[1] in _VERSIONS:
        return raw[2] in _PROTO_KEYS
    return raw[0] in _VERSIONS and raw[1] in _PROTO_KEYS


def placeholder() -> str:
    """What the inbox shows in place of the ciphertext."""
    return localefmt.chu("[Tin nhắn mã hoá đầu cuối: chỉ xem được trong app Zalo]",
                         "[End-to-end encrypted message: open the Zalo app to read it]")
