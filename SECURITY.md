# Security policy

## Supported versions

Only the latest release (the newest `build-<N>` on the [Releases page](https://github.com/tsljgj/ClaudeDesk/releases/latest)) is supported. Installed copies update themselves to it, so fixes ship as a new build.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub: open the repository's **Security** tab and choose **Report a vulnerability** ([direct link](https://github.com/tsljgj/ClaudeDesk/security/advisories/new)). Don't open a public issue.

Include what you found, how to reproduce it, the version and build from the window footer (`v2.2.0 · build N`) and your Windows version. Leave real inbox content out of the report. You should get a first reply within a week; once a fix is released, the advisory is published with credit to you unless you prefer otherwise.

## How ClaudeDesk is put together

These are the boundaries the design relies on. Reports that break one of them are especially welcome.

- **Local UI server.** The window is a web page served by the app itself. The server binds to `127.0.0.1` only, rejects requests whose `Host` header isn't a loopback name (against DNS rebinding), and requires a random token, generated at every launch, in the `X-Desk-Token` header of every API call (against other web pages calling it). Static assets (fonts, scripts) need no token and contain no secrets. Asset paths are looked up in a fixed list built at startup; request paths never reach the file system.
- **Message content.** Bodies are Markdown from Claude Code sessions. They are rendered with markdown-it and sanitized with DOMPurify, so HTML in a body cannot run script or cover the app's own controls.
- **Local files.** Messages, replies and follow-ups are JSONL files in `data\` next to the exe; `data\instance.json` holds the running instance's port and token. Anything running as the same Windows user can read and write these files, and that is out of scope: such a process already has your user's access. The named pipes used as "app is running" and "session is listening" markers reject remote clients.
- **Self-update.** The app checks the GitHub Releases API over HTTPS, downloads `ClaudeDesk.exe` from the latest release and verifies it against the SHA-256 published in the same release before swapping itself. This protects against corrupted or partial downloads, not against a compromised repository or CI; the exe is not code-signed yet. Auto-update can be turned off in Settings.
- **No telemetry.** Apart from the update check and download, the app makes no network requests.
