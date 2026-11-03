/* Timezone picker (0.443.0), shared by the first-run setup and the Settings page.
 *
 * The owner (2026-11-02): the timezone only showed up through the `datetime-vn` plugin, with no place to set it. Javis reads
 * `locale.tz` for "today", "yesterday", "tomorrow", reminders and report periods, so the owner picks it once, at setup, and can
 * change it in Settings.
 *
 * The list comes from the browser (`Intl.supportedValuesOf("timeZone")`), not from the server: the setup screen opens before
 * the admin account exists, so it cannot rely on an authenticated call. The server still checks every name it is handed
 * against its own tz database before saving, so a name the browser knows and the server does not is refused, not stored.
 *
 *   JavisTz.detect()               the browser's own timezone, current IANA spelling, e.g. "Asia/Ho_Chi_Minh" ("" when unknown)
 *   JavisTz.offsetLabel(name)      "UTC+07:00"
 *   JavisTz.options(selected)      <option> HTML: a short "suggested" group (selected, browser, a few common ones) then all
 *   JavisTz.nowIn(name)            "21:34" in that timezone, for a "time there now" confirmation line
 */
(function () {
  // Used only when the browser cannot list timezones (old Safari). Enough to cover the people Javis serves today.
  var FALLBACK = ["Asia/Ho_Chi_Minh", "Asia/Bangkok", "Asia/Jakarta", "Asia/Singapore", "Asia/Kuala_Lumpur", "Asia/Manila",
    "Asia/Shanghai", "Asia/Hong_Kong", "Asia/Taipei", "Asia/Seoul", "Asia/Tokyo", "Asia/Kolkata", "Asia/Dubai",
    "Australia/Sydney", "Europe/London", "Europe/Paris", "Europe/Berlin", "Europe/Moscow", "America/New_York",
    "America/Chicago", "America/Denver", "America/Los_Angeles", "America/Sao_Paulo", "UTC"];
  var COMMON = ["Asia/Ho_Chi_Minh", "Asia/Bangkok", "Asia/Singapore", "Asia/Tokyo", "Europe/London",
    "America/New_York", "America/Los_Angeles", "UTC"];

  // Browsers list CLDR's canonical names, which are often the OLD IANA spellings ("Asia/Saigon", "Asia/Calcutta",
  // "Europe/Kiev"), and report the device's own zone that way too. Javis stores the current IANA name (its default is
  // "Asia/Ho_Chi_Minh"), so a Vietnamese owner would otherwise see "Saigon" next to a saved "Ho Chi Minh" as two choices.
  var CURRENT = { "Asia/Saigon": "Asia/Ho_Chi_Minh", "Asia/Calcutta": "Asia/Kolkata", "Asia/Katmandu": "Asia/Kathmandu",
    "Asia/Rangoon": "Asia/Yangon", "Europe/Kiev": "Europe/Kyiv", "America/Godthab": "America/Nuuk",
    "Atlantic/Faeroe": "Atlantic/Faroe", "Pacific/Truk": "Pacific/Chuuk", "Pacific/Ponape": "Pacific/Pohnpei",
    "Pacific/Enderbury": "Pacific/Kanton", "Asia/Ulan_Bator": "Asia/Ulaanbaatar", "Etc/UTC": "UTC", "Etc/GMT": "UTC" };
  function canon(name) {
    var to = CURRENT[name];
    if (!to) return name;
    // Keep the old spelling on a browser too old to know the new one, or it would vanish from the list.
    try { new Intl.DateTimeFormat("en-US", { timeZone: to }); return to; } catch (e) { return name; }
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function tr(key, fallback) {
    try { var v = window.t ? window.t(key) : ""; return v && v !== key ? v : fallback; } catch (e) { return fallback; }
  }

  function detect() {
    try { return canon(Intl.DateTimeFormat().resolvedOptions().timeZone || ""); } catch (e) { return ""; }
  }

  // Offset in minutes east of UTC, right now (DST included). NaN when the name is unknown to this browser.
  function offsetMinutes(name) {
    try {
      var parts = new Intl.DateTimeFormat("en-US", { timeZone: name, hourCycle: "h23", year: "numeric", month: "numeric",
        day: "numeric", hour: "numeric", minute: "numeric" }).formatToParts(new Date());
      var g = {};
      parts.forEach(function (p) { g[p.type] = +p.value; });
      var asUtc = Date.UTC(g.year, g.month - 1, g.day, g.hour % 24, g.minute);
      var now = new Date(); now.setSeconds(0, 0);
      return Math.round((asUtc - now.getTime()) / 60000);
    } catch (e) { return NaN; }
  }

  function offsetLabel(name) {
    var m = offsetMinutes(name);
    if (isNaN(m)) return "";
    var sign = m < 0 ? "-" : "+", a = Math.abs(m);
    var hh = String(Math.floor(a / 60)).padStart(2, "0"), mm = String(a % 60).padStart(2, "0");
    return "UTC" + sign + hh + ":" + mm;
  }

  var _all = null;
  function all() {
    if (_all) return _all;
    var names = [];
    try { if (Intl.supportedValuesOf) names = Intl.supportedValuesOf("timeZone") || []; } catch (e) { names = []; }
    if (!names.length) names = FALLBACK.slice();
    names = names.map(canon);
    if (names.indexOf("UTC") < 0) names.push("UTC");
    names = names.filter(function (n, i) { return names.indexOf(n) === i; });
    _all = names.map(function (n) { return { name: n, off: offsetMinutes(n) }; })
      .filter(function (z) { return !isNaN(z.off); })
      .sort(function (a, b) { return a.off - b.off || a.name.localeCompare(b.name); });
    return _all;
  }

  function label(z) { return "(" + offsetLabel(z.name) + ") " + z.name.replace(/_/g, " "); }

  function options(selected) {
    var list = all(), seen = {}, byName = {};
    list.forEach(function (z) { byName[z.name] = z; });
    var cur = selected || "";
    // A saved name this browser does not list (spelling from an older browser) still shows, so the picker never lies about
    // what is saved.
    if (cur && !byName[cur]) byName[cur] = { name: cur, off: offsetMinutes(cur) };
    var picks = [cur, detect()].concat(COMMON).filter(function (n) {
      if (!n || seen[n] || !byName[n]) return false;
      seen[n] = true; return true;
    });
    var opt = function (z) {
      var text = isNaN(z.off) ? z.name : label(z);
      return '<option value="' + esc(z.name) + '"' + (z.name === cur ? " selected" : "") + ">" + esc(text) + "</option>";
    };
    var head = '<optgroup label="' + esc(tr("tz.group_suggested", "Suggested")) + '">' +
      picks.map(function (n) { return opt(byName[n]); }).join("") + "</optgroup>";
    // The selected one already sits in the suggested group; marking it twice would make the browser pick the last.
    var rest = '<optgroup label="' + esc(tr("tz.group_all", "All timezones")) + '">' +
      list.filter(function (z) { return !seen[z.name]; }).map(opt).join("") + "</optgroup>";
    return head + rest;
  }

  function nowIn(name) {
    try {
      return new Intl.DateTimeFormat("en-GB", { timeZone: name, hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
        .format(new Date());
    } catch (e) { return ""; }
  }

  window.JavisTz = { detect: detect, offsetLabel: offsetLabel, offsetMinutes: offsetMinutes, options: options, nowIn: nowIn };
})();
