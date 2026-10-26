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

# Reviewed path-independent release closures. Registration is external authority,
# deliberately excluded from its own source/manifest fingerprint. Empty until
# the complete production pipeline has passed actual qualification.
# Key: (platform, CLI version/hash, SDK version, profile version/hash, fingerprint).
# Value: SHA-256 of retained reviewed qualification evidence.
REVIEWED_RELEASES = {}

# Reviewed candidates may be exercised only by the separate local-dummy
# QualificationSession. This is not live profile registration or account
# readiness. Same exact seven-part key; value pins the candidate review evidence.
# Remains empty until a final candidate closure has been independently reviewed.
REVIEWED_QUALIFICATION_CANDIDATES = {}

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
    'bf793edf18abf0cbeecf83983ee619ae4a4c96415b844cc488b2ed1ed9c09a4a',
    # Final 0.314.0 source (M2D1 integrated, M2E activation schema), CLI 2.1.310; all20 native enforcement checks.
    # docs/superpowers/evidence/2026-10-25-m2-native-qualification-cli310.json
    ('win32', '2.1.310',
    'f9a3920634ae3b961ee92c2eb58d0051f5f8852b120983d0a4f57b6a5efeba61', '0.2.116',
    'claude-isolated-roles-v2', 'ee73f81305f01f7c1b43ed72744c9c2abf22ceff04b1661f60e48fd058273acd'):
    '3bed71341ff0f181092e35617acbe73326e0dc5d4633ed7d6e33ee0b2d6881f9',
    # M3 source (canary schema 12 in the store footprint), CLI 2.1.310; all20 native enforcement checks.
    # docs/superpowers/evidence/2026-10-25-m3-native-qualification-cli310.json
    ('win32', '2.1.310',
    'f9a3920634ae3b961ee92c2eb58d0051f5f8852b120983d0a4f57b6a5efeba61', '0.2.116',
    'claude-isolated-roles-v2', '7849768b28e6793a033d7126f8780256f66bb6ce2e98b864e71eeffc9820f837'):
    '669d299a2c1494dd466cc27c5a3f4e729207e35d4c0fa2c3037bddc8e0c763eb',
    # M4 source (routing schema 13 in the store footprint), CLI 2.1.310; all20 native enforcement checks.
    # docs/superpowers/evidence/2026-10-25-m4-native-qualification-cli310.json
    ('win32', '2.1.310',
    'f9a3920634ae3b961ee92c2eb58d0051f5f8852b120983d0a4f57b6a5efeba61', '0.2.116',
    'claude-isolated-roles-v2', '1a8a08a07394d0ab31ecab33eeed216b8b971c0d0ed0d8a5a42b131c72f3f0c1'):
    'a6031003c09b2f4f5cfa7db968979ebec376ea6f74a39238b231b5c0fd020bf1',
    # M5 source (agent procedure schema 14 in the store footprint), CLI 2.1.310; all20 native enforcement checks.
    # docs/superpowers/evidence/2026-10-25-m5-native-qualification-cli310.json
    ('win32', '2.1.310',
    'f9a3920634ae3b961ee92c2eb58d0051f5f8852b120983d0a4f57b6a5efeba61', '0.2.116',
    'claude-isolated-roles-v2', 'c509f9a1560d3c93631c38ad1a461d5a5430f3149cf20ab51724fab6bfd6ed19'):
    '9ef3d110ba01f71f24378166a31cba679adcd425bdf5d680b9a3abf2cc36347d',
    # M6 source (bundle schema 15 in the store footprint), CLI 2.1.310; all20 native enforcement checks.
    # docs/superpowers/evidence/2026-10-26-m6-native-qualification-cli310.json
    ('win32', '2.1.310',
    'f9a3920634ae3b961ee92c2eb58d0051f5f8852b120983d0a4f57b6a5efeba61', '0.2.116',
    'claude-isolated-roles-v2', 'b609a52ac28ea3d8837b74b7738ee3fd5c45b9d16169bb8564ed3b7f423da403'):
    '03337d8cfac919e427647a0e9b68f4e6641c4f2dffe31f3273261e2f1326867e',
    # M7 source (team schema 16 in the store footprint), CLI 2.1.310; all20 native enforcement checks.
    # docs/superpowers/evidence/2026-10-26-m7-native-qualification-cli310.json
    ('win32', '2.1.310',
    'f9a3920634ae3b961ee92c2eb58d0051f5f8852b120983d0a4f57b6a5efeba61', '0.2.116',
    'claude-isolated-roles-v2', '3c5543a3c14634b3736b51eb278b7c7f805554e3ab59ac8a908772230151d1f5'):
    '6867a378c310670b094fd29d36814c41d189dac67d74de2880f6450813df250f',
    # M8 source (library schema 17 in the store footprint), CLI 2.1.310; all20 native enforcement checks.
    # docs/superpowers/evidence/2026-10-26-m8-native-qualification-cli310.json
    ('win32', '2.1.310',
    'f9a3920634ae3b961ee92c2eb58d0051f5f8852b120983d0a4f57b6a5efeba61', '0.2.116',
    'claude-isolated-roles-v2', 'fdfd0d2fca59ae27143004881945c5ba176754a333ca5882e83fe162efa69dbb'):
    '337ad0abd2e1ff108e528a4f077e59f45d4a3584b4caf35b123c880a504c31df'}


def profile_qualification(pin, platform):
    key = (platform, pin["cli_version"], pin["cli_hash"], pin["sdk_version"],
           pin["profile_version"], pin["profile_hash"])
    evidence = QUALIFIED_PROFILES.get(key)
    return evidence if type(evidence) is str and re.fullmatch(r"[0-9a-f]{64}", evidence) else None
