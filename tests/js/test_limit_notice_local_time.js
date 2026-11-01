// Regression for real subscription-limit text: display local reset only, keep raw intact.
// Run: node tests/js/test_limit_notice_local_time.js
const assert = require("node:assert/strict");
const originalTZ = process.env.TZ;
process.env.TZ = "Asia/Ho_Chi_Minh";
try {
  const { localizeNotice, fmtWhen } = require("../../dashboard/limit-resume.js");
  const raw = "You've hit your 5-hour limit · resets 5:20pm (UTC)";
  const epoch = Date.parse("2026-11-01T17:20:00Z") / 1000;
  const now = Date.parse("2026-11-01T15:10:00Z") / 1000;
  const shown = localizeNotice(raw, { reset_epoch: epoch }, now);
  assert.match(shown, /You've hit your 5-hour limit/);
  assert.match(shown, /00:20/);
  assert.match(shown, /02\/11/);  // UTC Nov 1 -> Vietnam Nov 2
  assert.match(shown, /giờ địa phương/);
  assert.doesNotMatch(shown, /5:20pm \(UTC\)/);
  assert.equal(raw, "You've hit your 5-hour limit · resets 5:20pm (UTC)");
  assert.match(fmtWhen(epoch, now), /00:20/);

  assert.equal(localizeNotice(raw, null, now), raw); // no trusted epoch -> no guessing
  assert.equal(localizeNotice(raw, { reset_epoch: 0 }, now), raw);
  assert.equal(localizeNotice("I quoted: You've hit your limit · resets 5:20pm (UTC) in a long report. ".repeat(8),
      { reset_epoch: epoch }, now).includes("5:20pm (UTC)"), true);
  assert.equal(localizeNotice("The meeting resets 5:20pm (UTC)", { reset_epoch: epoch }, now),
      "The meeting resets 5:20pm (UTC)");
  console.log("PASS local reset notice: UTC to next-day Vietnam, raw preserved");
} finally {
  if (originalTZ == null) delete process.env.TZ;
  else process.env.TZ = originalTZ;
}
