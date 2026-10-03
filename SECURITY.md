# Security Policy

Javis runs an AI brain with full rights on the machine it is installed on, so security reports matter a great deal to us. Thank you for taking the time.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.** Report it privately instead:

1. Open a private report at **[Security → Report a vulnerability](https://github.com/blogminhquy/javis-os/security/advisories/new)** on this repository. Only you and the maintainers can see it.
2. If that page is not available, open a normal issue that says only "I have a security report, please give me a private contact", with no details, and the maintainer will reply with one.

Useful things to include: the version (shown under **Settings → Updates**, or in the `VERSION` file), how Javis is deployed (Docker, VPS, local), the steps to reproduce, and what an attacker could do.

## What to expect

- An acknowledgement within a few days.
- A fix released as a new version as soon as it is ready. Javis updates itself through the Updates page, so fixes reach users quickly.
- Credit in the changelog if you would like it.

## Supported versions

Only the latest release receives security fixes. Please check that the problem still exists on the current `main` before reporting.

## Scope notes

Some behaviour is by design and documented: the CLI brains can run shell commands on the host, user plugins run real Python inside the server (blocked until `JAVIS_ENABLE_USER_PLUGINS=true`), and connections at **Full access** can act on real accounts. A way to get past those safeguards (login, CSRF and DNS-rebinding protection, the plugin gate, connection permission levels) is exactly what we want to hear about.
