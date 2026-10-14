# Changelog

All notable changes to ClaudeDesk are listed here. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

The version is the one shown in the window footer (`v2.1.0 · build N`). Every green build on `main` is also published as a release tagged `build-<N>`; installed copies update to the newest build, so one version usually spans several builds.

## [2.1.0] - 2026-10-14

### Added

- **Follow-up questions (追问).** Answers, notices and decisions that already have a reply get a follow-up box. If the session that posted the message is listening, the follow-up is delivered at once and its answer appears under your question; otherwise it is kept and can be copied into the Claude chat. The list shows "已追问 · 等回答" until an answer arrives.
- `desk.py wait --followups --source S` waits for the next follow-up on that source's messages (exit 4 when the shell that started it is gone), `desk.py post --reply-to <id>` answers one, and `desk.py followups` lists them with their status. Follow-ups are stored in `data/followups.jsonl`.
- **Closable repo tabs.** Close a tab with its × or a middle click; its messages are hidden and stop counting, and the tab comes back by itself when that repo posts again. "已关闭 N" at the end of the tab bar and Settings list the closed tabs to reopen. Search results inside closed tabs are counted at the end of the list.
- **只看未处理** (unhandled only, `F`): show only waiting decisions and unread messages.
- **One-click archive of handled messages** next to the search box (read and no longer waiting for a decision; undo with `Z`).
- **正文宽度** (reading width) setting: 适中 (720 px), 宽 (920 px) or 铺满 (full width).
- Contributor docs: `CONTRIBUTING.md`, `SECURITY.md`, this changelog, issue and pull request templates, `.editorconfig`, `requirements-dev.txt`, and `scripts/screenshots.py` to regenerate the README screenshots from demo data.

### Changed

- **标为已处理** (mark handled, `R`; formerly 标为已解决) works on any selection: waiting decisions tell their session the matter is handled, everything else is marked read. It is also in the batch bar, the row's hover actions and the right-click menu.
- Every decision has a reply box, with or without options. `desk.py post --allow-text` is no longer needed and is kept for compatibility.
- The reading column is wider by default (920 px, 32 px margins).
- **未归类** (unsorted) only shows up as a tab while it has unarchived messages. The tab bar no longer shows the logo.
- Release notes list the subject lines of the commits since the previous build and link to this changelog.
- READMEs rewritten (English and Chinese in parity) with new screenshots.

## [2.0.0] - 2026-10-09

2.0.0 shipped as rolling builds, from `build-3` (2026-10-09) to `build-23` (2026-10-14). Everything below landed in that range.

### Added

- New window: a local web page in Edge WebView2 (pywebview) with a pystray tray icon, replacing the PySide6 window. The UI also runs in any browser with `--serve`.
- Markdown rendered with markdown-it, DOMPurify, KaTeX and highlight.js, bundled for offline use with the fonts: tables, highlighted code and `$…$`, `$$…$$`, `\(…\)`, `\[…\]` math.
- Light, dark and system themes, four accent colors, sans (Inter + Noto Sans SC) or serif (Source Serif + Noto Serif SC) reading font, text size and list density.
- Copy a message as Markdown, rich text or plain text; per-code-block copy; export to PDF.
- Archive, unarchive and delete. Archiving or deleting a waiting decision tells its session it was skipped (`"dismissed": true`).
- Self-update from GitHub Releases: download, SHA-256 check, in-place swap, never while the window is open; the bundled `desk.py` is refreshed too.
- Repo tabs. `desk.py post` records the git repo it runs in (`--repo` overrides, `list --repo` filters). Older messages are matched to repos found in Claude Code's session history; the rest go under 未归类 and can be filed under a repo.
- Hover actions, checkboxes and a batch bar; "mark resolved" (`R`) writes `"resolved": true` so a waiting session knows the matter is handled.
- Waiting-decisions strip with `N` / `Shift+N` to the next waiting decision, wait times on waiting rows, and toasts for arrivals you can't see.
- Taskbar badge with the unread count; a red tray badge drawn at tray size.
- Keyboard: `Ctrl+Enter` submits from anywhere, layered `Esc`, keyboard multi-select, `Z` undo, keyboard menus and a shortcut sheet (`?`).
- Per-message reply drafts; `choice_index` in replies.
- Narrow-window layout (720 px or less) with a list cursor.
- CI: real-browser UI tests, a packaged-exe self-test and a Windows end-to-end run (post, reply, self-update).

### Changed

- The window always opens on 全部. Tabs, counts and rows keep still when you click; repo tabs and groups are sorted by name.
- List marks: bright unread dots and distinct marks for unopened, seen and urgent decisions.
- Contrast-checked greys and accent text, pills for pending counts, relative dates and bigger hit areas. The accent color only means "needs you".
- Releases are published from `main` only.

### Fixed

- Taskbar flashing never worked: the window handle was read before the window existed.
- Markdown: CJK-friendly bold, stricter `$` math, placeholders like `<id>` stay visible, no fuzzy links, and HTML in a body can't cover the app.
- Data layer: a running marker per data folder (a stray copy of `desk.py` now warns), UTF-8 git output, static assets served from a fixed list, retries around compaction, malformed lines skipped one by one, quieter server errors.
- State: no acting on a message that was just archived or deleted, faster list updates, bounded detail cache, in-flight submit state.
- No light flash when starting in dark mode; the taskbar stops flashing once nothing needs you; a clearer message when a second copy is started; `build.ps1` works under a GBK code page.
- Twelve cross-feature bugs found by fuzzing: stale wait times, undo of the wrong action, lost keyboard focus, late snapshots rolling state back, deleted rows flashing back, stale details over a closed decision.
- Opening a message clears the narrow-list cursor; closing a dialog never leaves focus on its hidden button.

## 1.0.0 - 2026-10-08

### Added

- `desk.py`, a standard-library-only CLI: sessions post decisions, answers and notices to an append-only JSONL inbox and wait for the reply (`post`, `wait`, `close`, `responses`, `list`).
- `ClaudeDesk.exe` (PySide6): a tray app with notifications, taskbar flashing and a tray badge that renders Markdown bodies and writes replies back.
- A cross-process byte lock around every append; each decision can be answered once.
- The Claude Code skill, a PyInstaller build script (`build.cmd -Install` adds a Startup shortcut) and English and Chinese READMEs. MIT licensed.

[2.1.0]: https://github.com/tsljgj/ClaudeDesk/compare/build-23...main
[2.0.0]: https://github.com/tsljgj/ClaudeDesk/releases/tag/build-23
