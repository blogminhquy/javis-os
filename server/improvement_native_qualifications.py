"""Reviewed release registrations for exact native-profile qualification evidence.

Keys bind platform, binary/version, SDK and the complete profile source hash.
Values are SHA-256 of actual qualification evidence retained with the release.
This host source is the registration authority, deliberately outside the profile
hash to avoid a self-referential digest. No environment/HTTP/model can register a
profile. Add an entry only after its native black-box qualification has passed;
changing profile source invalidates the entry. Historical receipts stay readable.
"""
from __future__ import annotations

import re

# Exact dummy-auth/native enforcement evidence; this does not attest account
# readiness, actual call usage, business quality or final eligibility.
# docs/superpowers/evidence/2026-10-23-m2c-native-qualification.json
QUALIFIED_PROFILES = {('win32', '2.1.308',
    'c9796ba22a9221586b36371b36f5b66198d66eb4badf6a4cf4a5f7b07becea53', '0.2.116',
    'claude-isolated-roles-v2', '9dcf718470e70957d07454bb8b50fbde79575a3b23d8c06e24cc9b749051116b'):
    '98ee4e8c406091ee84db2862cbf80b11a5f15cf88f7d4d96188d5e2360822ea7',
    # Exact paired-view/solver/typed-role/native-lifetime enforcement, local dummy providers.
    # docs/superpowers/evidence/2026-10-23-m2d1-native-qualification-final.json
    ('win32', '2.1.309',
    '5441781f2b6bbd07354b4a74560ee88c68c9bf05d6db3c7e24c452c91673dc53', '0.2.116',
    'claude-isolated-roles-v2', '4d346a3ae4f1afa99784fc51307258ad99a8d470ac6a0c46f1d330e6b0e656fa'):
    '012d9e37690e8711da75a344dfee0677df8d6c690b90f689ddbb14574c82f295',
    # Exact changed semantic-outcome footprint, same native runtime and full enforcement suites.
    # docs/superpowers/evidence/2026-10-23-m2d1-native-qualification-outcome.json
    ('win32', '2.1.309',
    '5441781f2b6bbd07354b4a74560ee88c68c9bf05d6db3c7e24c452c91673dc53', '0.2.116',
    'claude-isolated-roles-v2', '958527ac69c3b5728044b22cf6d3bdebb920da7cbe46a9da261e899568ced1ef'):
    '1f3391cf9c1bf621d3ef2de44dd181acf17dd7d922fed4a80ae66bef36c8fab4',
    # Exact raw-artifact prompt footprint, same native runtime; all20 enforcement checks.
    # docs/superpowers/evidence/2026-10-24-m2d1-native-qualification-format.json
    ('win32', '2.1.309',
    '5441781f2b6bbd07354b4a74560ee88c68c9bf05d6db3c7e24c452c91673dc53', '0.2.116',
    'claude-isolated-roles-v2', 'e7aaa5bd9902860e440349f0654f2a6ec92271770030f8bfaf6a0d584efb2a60'):
    'c5e0acc9150c8a4c392a4ae644761b71495dc7d70a8a6663580e0ff78e9800d0',
    # Exact bounded read-only CLI-observation footprint, all20 native enforcement checks.
    # docs/superpowers/evidence/2026-10-24-m2d1-native-qualification-observation.json
    ('win32', '2.1.309',
    '5441781f2b6bbd07354b4a74560ee88c68c9bf05d6db3c7e24c452c91673dc53', '0.2.116',
    'claude-isolated-roles-v2', 'be4a5866a411fdcbb68bc7728d6cec9418fac19132ca4a46dce40ac1cb45ca0b'):
    'fd52de7a70862b3b04d7b79c257bc11ca77262b78d85157531c3b8aabcdbc96c',
    # Exact preparation-heartbeat footprint; all20 native enforcement checks.
    # docs/superpowers/evidence/2026-10-24-m2d1-native-qualification-preparation-heartbeat.json
    ('win32', '2.1.309',
    '5441781f2b6bbd07354b4a74560ee88c68c9bf05d6db3c7e24c452c91673dc53', '0.2.116',
    'claude-isolated-roles-v2', '972175a29309295afc596902ef711ea51400ba77c2f39e27aab1141f9a0f6a10'):
    'a84d266da09b3d4bd029eaa99a5ef3821e86e7439a7517197994cc6d89e7d109',
    # Exact83-source versioned skill-read footprint; all20 local native checks.
    # docs/superpowers/evidence/2026-10-24-m2d1-native-qualification-skill-reads.json
    ('win32', '2.1.309',
    '5441781f2b6bbd07354b4a74560ee88c68c9bf05d6db3c7e24c452c91673dc53', '0.2.116',
    'claude-isolated-roles-v2', '04c8c77baec04d04019752bc8abc2f9a5906e094ededfbdd56cfc3c712aef126'):
    'bf793edf18abf0cbeecf83983ee619ae4a4c96415b844cc488b2ed1ed9c09a4a'}


def profile_qualification(pin, platform):
    key = (platform, pin["cli_version"], pin["cli_hash"], pin["sdk_version"],
           pin["profile_version"], pin["profile_hash"])
    evidence = QUALIFIED_PROFILES.get(key)
    return evidence if type(evidence) is str and re.fullmatch(r"[0-9a-f]{64}", evidence) else None
