# Native executable guard component

Goal M0–M8 section12 applies. Base f131d958; current native profile972175a2 is
qualified/registered and final-head CI40005387321 is running. No account retry.

Own-file probes demonstrate real file-sharing enforcement and a leaf-only
junction namespace bypass. READ_ATTRIBUTES-only directory handles do not deny
write/delete sharing. GENERIC_READ/shareREAD directory handles opened with
BACKUP_SEMANTICS|OPEN_REPARSE_POINT do, with actual junction removal refusal and
post-release controls. POSIX replacement flags3/existing held target confirms
shareDELETE would permit pathname replacement while old handle bytes stay valid.

Implement one real host component before changing the native lifecycle:

- New improvement_native_image.ImageReadGuard acquires ancestors root-to-leaf,
  using actual read access/shareREAD and nofollow reparse handles. Inspect each
  actual handle: expected ordinary directory/regular leaf, no reparse point,
  normalized final path and stable volume/file identity. Refuse unsupported
  paths/filesystems instead of claiming a portable loaded-image proof.
- Hash the held leaf handle, bounded size, before/after descriptor identity;
  require exact expected digest. Retain every guard until explicit close. No
  account/auth/model/input bytes, updater mutation or installed SDK changes.
- RED/GREEN real Windows tests for protected bytes, replacement, ancestor
  rename, hash-mismatch cleanup, junction before/during acquisition, preexisting
  writer/mapping conflicts, unrelated child writes and close/idempotency.
  Tests sequential; no native/model account inference.
- Independent scoped component review and affected tests. This component is
  not yet reachable from a native worker, so it does not by itself establish
  runtime qualification, a new receipt or production model dispatch proof.
  Existing source-qualified runner/profile evidence remains historical and
  only applies to unchanged reachable code.

Next integrate this component into the existing guardian through full job drain,
then actual suspended spawn/host attestation/ack, versioned configuration proof,
immutable asset broker/result correlation and complete native qualification.
No registration or real account call on a changed reachable footprint until the
complete boundary passes. No full18 gate, lease/deadline or owner policy change.

Self-review: ancestor handles must have real read access, not metadata-only.
An old opened leaf is insufficient when its lexical namespace can be swapped.
Reject reparse handles even when their targets happen to have expected bytes.
Constructor failure must close every acquired handle; close cannot silently
discard ownership if an OS close fails. Guardian crash behavior remains a
separate integration test, not supplied by this component.

## Actual scoped component checkpoint

17 parent checksPASS0.250s; independent17PASS0.199s, limited component only.
Partial-close and failed-entry cleanup findings reproduced before correction;
constructor/entry/exit cleanup failures retain guard ownership for retry.
Attribute-only reparse mutation is not excluded; snapshot records metadata and
loaded-image coverage UNKNOWN. Fresh checks detect observed drift but do not
close a future mutation race. No guardian/native-execution integration yet;
current81 profile pins remain972175a2. Public probe/component evidence records
all successes, failed help fixture and unsupported boundaries.
