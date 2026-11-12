/* A custom MCP connection signed in with OAuth can be edited again, without moving its sign-in to another server.

       node tests/js/test_custom_oauth_mcp_edit.js

   PR #1204: after OAuth sign-in the account menu hid "Edit configuration", so changing the endpoint's query (for
   example which tools the server exposes) meant deleting the connection and signing in again. The edit form already
   kept auth=oauth on save; the menu now offers it, and the form refuses a different origin for an OAuth connection. */
const fs = require("fs");
const path = require("path");
const ROOT = path.join(__dirname, "../..");
const fails = [];
function check(name, cond) { console.log((cond ? "ok   " : "FAIL ") + name); if (!cond) fails.push(name); }

const src = fs.readFileSync(path.join(ROOT, "dashboard/console.js"), "utf8");
const menu = src.slice(src.indexOf("function openAccountMenu("), src.indexOf("function openAccountMenu(") + 900);
check("the account menu offers Edit to every custom connection, OAuth included",
  /\(c\.connector_id \|\| "custom"\) === "custom"\s*\n\s*\? '<button class="conn-menu-btn" data-m="edit">'/.test(menu));
check("Reconnect on an OAuth connection is still a new sign-in, not the edit form",
  /\(c\.connector_id \|\| "custom"\) === "custom" && c\.auth !== "oauth"\) \{ closeConnModal\(\); return openMcpForm\(el, c\); \}/.test(src));

const form = src.slice(src.indexOf("function openMcpForm("));
check("an OAuth connection cannot be switched to a local command", /if \(dangOauth && kieu !== "url"\)/.test(form));
check("the form compares the saved origin with the edited one",
  /currentEndpoint\.origin === updatedEndpoint\.origin/.test(form) && /!updatedEndpoint\.username && !updatedEndpoint\.password/.test(form));
check("a save keeps auth=oauth", /body\.auth = dangOauth \? "oauth" : "header"/.test(form));
check("the saved URL moves only after a successful save",
  form.indexOf('savedEndpointUrl = body.url || "";') > form.indexOf("if (!r || !r.ok) {"));

// The same rule the form applies, run on real URLs.
function sameOrigin(saved, edited) {
  try {
    const a = new URL(saved), b = new URL(edited);
    return a.origin === b.origin && !b.username && !b.password;
  } catch (_) { return false; }
}
check("a changed query on the same server is allowed", sameOrigin("https://mcp.example.com/mcp?tools=a", "https://mcp.example.com/mcp?tools=a,b"));
check("another host is refused", !sameOrigin("https://mcp.example.com/mcp", "https://evil.example.net/mcp"));
check("another port or protocol is refused",
  !sameOrigin("https://mcp.example.com/mcp", "https://mcp.example.com:8443/mcp") && !sameOrigin("https://mcp.example.com/mcp", "http://mcp.example.com/mcp"));
check("credentials inside the URL are refused", !sameOrigin("https://mcp.example.com/mcp", "https://u:p@mcp.example.com/mcp"));
check("a broken URL is refused", !sameOrigin("https://mcp.example.com/mcp", "not a url"));

for (const lang of ["vi", "en"]) {
  const dict = JSON.parse(fs.readFileSync(path.join(ROOT, "dashboard/i18n/" + lang + ".json"), "utf8"));
  check(lang + ".json has the origin-locked message", typeof dict["cs.mf_oauth_origin_locked"] === "string" && dict["cs.mf_oauth_origin_locked"].length > 10);
}

if (fails.length) { console.error(fails.length + " check(s) failed"); process.exit(1); }
console.log("all ok");
