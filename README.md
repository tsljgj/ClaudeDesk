# ClaudeDesk

[![build](https://github.com/tsljgj/ClaudeDesk/actions/workflows/build.yml/badge.svg?branch=main)](https://github.com/tsljgj/ClaudeDesk/actions/workflows/build.yml)
[![release](https://img.shields.io/github/v/release/tsljgj/ClaudeDesk?display_name=tag)](https://github.com/tsljgj/ClaudeDesk/releases/latest)
[![license](https://img.shields.io/github/license/tsljgj/ClaudeDesk)](LICENSE)
![platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078D6)

English · [中文](README.zh-CN.md)

ClaudeDesk is a small Windows tray app that gives Claude Code sessions a place to reach you outside the terminal. Instead of the built-in AskUserQuestion prompt, a session posts a **decision** with options and waits in the background; you pick an option and add a note on your desktop, and the session wakes up and carries on. When you ask a session something, it also posts the question and the full **answer** here, so it doesn't get buried under tool output, and you can ask **follow-up questions** from the same place. Occasional **notices** ("the long run finished", "a job crashed") land here too.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/screenshot-dark.png">
  <img alt="ClaudeDesk main window: repo tabs, the message list and an open decision with its options and reply box" src="docs/screenshot-light.png">
</picture>

> Third-party tool, not affiliated with or endorsed by Anthropic. The interface is in Simplified Chinese.

## Contents

- [Features](#features)
- [Install](#install)
- [Quick start: connect Claude Code](#quick-start-connect-claude-code)
- [Everyday use](#everyday-use)
- [Keyboard shortcuts](#keyboard-shortcuts)
- [CLI reference (`desk.py`)](#cli-reference-deskpy)
- [How it works](#how-it-works)
- [Data files](#data-files)
- [Self-update](#self-update)
- [Security and privacy](#security-and-privacy)
- [Build from source](#build-from-source)
- [Contributing](#contributing)
- [License](#license)

## Features

- **Decisions with a reply box.** Options with descriptions and a recommended pick, plus a free-text note on every decision. The waiting session gets your choice as one line of JSON.
- **Answers and follow-ups.** Answers keep your original question. Ask a follow-up on any answer, notice or handled decision; a session that is listening answers it and the reply is linked back.
- **One tab per repo.** Messages are grouped by the git repo the session runs in. Tabs can be closed and reopened; a closed tab comes back by itself when that repo posts again.
- **Built for triage.** A waiting-decisions strip with `N` to jump to the next one, an "unhandled only" filter (`F`), mark handled (`R`) for any selection, one-click archive of everything handled, undo (`Z`), keyboard multi-select.
- **Full Markdown.** Tables, highlighted code and LaTeX math (`$…$`, `$$…$$`, `\(…\)`, `\[…\]`), rendered offline with bundled fonts. Copy any message as Markdown, rich text or plain text, or export it to PDF.
- **Hard to miss, easy to ignore.** Windows notifications, a tray badge and a taskbar badge with the unread count; urgent decisions keep flashing until you look.
- **Light, dark or system theme**, four accent colors, sans or serif reading font, three text sizes, three reading widths, two list densities.
- **Small and local.** One exe, a stdlib-only CLI, plain JSONL files next to it. No account, no telemetry. It updates itself from GitHub Releases.

## Install

Windows 10 or 11 (Edge WebView2 is built in).

1. Download `ClaudeDesk.exe` from [Releases](https://github.com/tsljgj/ClaudeDesk/releases/latest) into a folder you can write to, e.g. `%LOCALAPPDATA%\Programs\ClaudeDesk\`. Not `Program Files`, or it can't update itself.
2. Run it. It puts `desk.py` (the CLI that Claude uses) and `data\` (your inbox) next to itself and sits in the tray.
3. Connect Claude Code (next section).

Upgrading from 1.x: quit the old app from the tray and drop the new `ClaudeDesk.exe` into the old folder. `data\` carries over; the old `_internal\` folder can be deleted.

> Windows 11 hides new tray icons under "^". To keep it visible: Settings → Personalization → Taskbar → Other system tray icons → turn on ClaudeDesk.

## Quick start: connect Claude Code

1. Copy [`skill/claude-desk/SKILL.md`](skill/claude-desk/SKILL.md) to `~/.claude/skills/claude-desk/SKILL.md`.
2. At the top of that file, set `DESK` to the `desk.py` next to your `ClaudeDesk.exe` and `PY` to your Python 3.10+.
3. Optionally make it a standing rule for every session in `~/.claude/CLAUDE.md`:

   ```markdown
   ## Talking to the user: ClaudeDesk
   - For anything the user must decide, don't use AskUserQuestion: post a decision with skill claude-desk and wait for it in the background.
   - When answering a user's question, answer in the chat and also post it to ClaudeDesk as an answer (original question + full answer).
   ```

The skill is written in Chinese, to match the UI. Claude follows it either way, and the commands are the same.

## Everyday use

### Window and tray

| What | How |
|---|---|
| Open | Run `ClaudeDesk.exe` or click the tray icon. Running it again only brings the window to the front |
| Close | × only hides the window to the tray; messages keep arriving. Quit from the tray menu |
| Start with Windows | Settings or the tray menu (writes `HKCU\…\Run`; starts in the tray) |
| Tray icon | Red number = unread messages; red dot = nothing unread but a decision is still open; flashing = a decision or urgent message you haven't seen |
| Taskbar button | While the window is open or minimized it carries the same red badge. When a message arrives with the window in the tray, a minimized button appears with the badge and flashes: decisions and urgent messages until you look or they are handled elsewhere, others three times |

New messages also raise a Windows notification; clicking it opens that message.

### Repo tabs

- The tabs across the top are **全部项目** (all repos) followed by one tab per repo, sorted by name. The repo comes from `desk.py post`, which records the git repo of the directory it runs in (the origin URL's name; worktrees resolve to their repo; outside git, the folder name; `--repo` overrides).
- Click a tab to see only that repo; `Ctrl`/`Shift`-click to pick several; `[` / `]` step through them; `Esc` or 全部项目 goes back to all. With several repos in view the list is grouped by repo. View counts, "mark all read" and "archive handled" follow the selection.
- **Close a tab** with its × or a middle click: its messages are hidden and stop counting (it asks first if decisions are still waiting there, and `Z` undoes it). The tab comes back by itself when that repo posts a new message. **已关闭 N** at the right end of the tab bar, and Settings, list the closed tabs to reopen.
- Messages from before repo tracking are matched to repos found in Claude Code's own session history (`~/.claude/projects`, plus `CLAUDE_CONFIG_DIR`). Anything left over goes under **未归类** (unsorted), which only shows up when it has messages. "归到…" on a group header, or right-clicking a tab, files a source under a repo; Settings can undo it.
- When the tabs don't fit, the mouse wheel scrolls them sideways and a small orange dot points at hidden tabs with waiting decisions.

### The list

- Four views: **全部** (everything; the window always opens here), **决定** (decisions), **回答** (answers) and **归档** (archive). An orange pill counts waiting decisions; a grey number counts unread messages.
- **Waiting-decisions strip:** while decisions are waiting, a strip under the search box reads "N 条待决定 · M 条紧急 · 最久已等 X". Click it or press `N` for the next waiting decision in the selected repos (urgent first, then the longest-waiting; `Shift+N` goes back). Waiting rows show how long the session has been waiting instead of a clock time. When a new decision or urgent message arrives somewhere you can't see, a toast says so and `N` opens it.
- **只看未处理** (unhandled only, `F`) next to the search box hides everything except waiting decisions and unread messages. The message you are reading stays until you move on. The setting is remembered.
- **Archive handled** (the box icon next to it) archives everything in the selected repos that is read and no longer needs a decision, in one click, without asking; `Z` undoes it. The "⋯" menu has the same plus "mark all read".
- Marks: a solid dot is unread; an orange dot is a decision you haven't opened; an orange ring is a decision you've seen but not answered; an extra outer ring marks an urgent decision. The second line shows the status (待决定, ✓ your choice, ✓ 已处理, 已跳过, 已追问 · 等回答). Moving through the list with `↑`/`↓` marks a message read only after it stays open for 0.8 s.
- Hover a row for its own actions (read/unread, mark handled, archive, delete) and a checkbox. Right-click works too.
- **Select several:** tick checkboxes (`Shift` for a range), `Ctrl`-click, `X` for the current message, `Shift+↑↓`, `Ctrl+A`. The batch bar offers select all, mark handled, read, archive and delete.
- Search with `/` or `Ctrl+F` across titles, bodies, sources, questions and options. Matches hidden by the current view, repo or a closed tab are counted at the end of the list, one click away.

### Decisions

- Press `1`–`9` or click an option, optionally type a note in the reply box (every decision has one), then `Ctrl+Enter` (from anywhere) or 提交. A decision without options takes a text reply. A half-picked, half-written reply survives switching to another message and back.
- The recommended option is labelled 推荐 and the card shows how long the session has been waiting. Each decision can be answered once; afterwards "下一条待决定 →" (or `N`) moves on.
- **标为已处理** (mark handled, `R`) works on any selection: a waiting decision tells its session that the matter is handled, without picking an option (`"resolved": true` in the reply); everything else is marked read. `R` asks first when waiting decisions are involved, because the session is told right away; otherwise it can be undone.
- Archiving (`E`) or deleting (`Delete`) a decision that is still waiting tells its session you skipped it (`"dismissed": true`), so it never hangs. Delete really removes the message from the inbox file.

### Follow-up questions

- Answers, notices and decisions that already have a reply (picked, handled, skipped or closed in chat) have a **追问** (follow-up) box at the bottom. `Enter` jumps into it and `Ctrl+Enter` sends.
- If the session that posted the message is listening (`desk.py wait --followups`), the box says the session is online and the follow-up is delivered at once. The session's answer appears under your question and in the list as "回应追问", with a link back to the original.
- If nobody is listening, the follow-up is kept and **复制追问** copies it, with the original title and message id, for pasting into the Claude chat. The row shows "已追问 · 等回答" until an answer arrives.

### Reading, copying and settings

- The reader toolbar copies the message as Markdown (`C`; the arrow offers rich text or plain text) and exports it to PDF (`Ctrl+P`). Code blocks have their own copy button.
- Narrow windows (720 px or less) show the list and the reader one at a time: `↑`/`↓` move a cursor in the list, `Enter` opens, `Esc` or `Backspace` goes back.
- **Settings** (slider icon, top right, or `Ctrl+,`): theme (system, light, dark), accent color, reading font (sans: Inter + Noto Sans SC; serif: Source Serif + Noto Serif SC), text size, **正文宽度** (reading width: 适中 720 px, 宽 920 px (default), 铺满 full width), list density, start with Windows, auto-update, check for updates, open the data folder, repo filing and closed tabs.

## Keyboard shortcuts

Press `?` in the app for the same sheet.

| Browse | | Decide | |
|---|---|---|---|
| `↑` `↓` / `J` `K` | previous / next message | `1`–`9` | pick option N |
| `N` / `Shift+N` | next / previous waiting decision | `Ctrl+Enter` | submit, or send a follow-up |
| `Shift+↑` `↓` | extend the selection | `Enter` | open, or write a note / follow-up |
| `/`, `Ctrl+F` | search | `R` | mark handled |
| `[` `]` | previous / next repo tab | | |
| `F` | unhandled only, on / off | | |
| `Esc` | back one layer: menu or dialog → narrow reader → search → ticks → repo filter | | |

| Organize | | Other | |
|---|---|---|---|
| `E` | archive / unarchive | `C` | copy Markdown |
| `U` | read / unread | `Ctrl+P` | export PDF |
| `X` | tick the current message | `Ctrl+,` | settings |
| `Ctrl+A` | select all | `?` | shortcuts |
| `Delete` | delete | | |
| `Z`, `Ctrl+Z` | undo (while its toast is showing) | | |

## CLI reference (`desk.py`)

`desk.py` uses only the standard library (Python 3.10+). Use the copy next to `ClaudeDesk.exe`: the app keeps it at the same version as itself.

```bash
PY=python
DESK=C:/path/to/ClaudeDesk/desk.py

# Post a decision; prints the new message id. The body is a UTF-8 Markdown file.
"$PY" "$DESK" post --kind decision --source my-project --title "Run the full regression suite before releasing?" \
    --body-file plan.md --option "Full regression::about 25 minutes, safest" \
    --option "Release now::CI already ran the unit tests" --option "Smoke test only::about 5 minutes" \
    --recommended 1 [--priority high]

# Block until you reply (run it in the background). Exit 0 with the reply as one line of JSON.
"$PY" "$DESK" wait --id <id> [--timeout SECONDS]

# Post an answer: the user's original question plus the full answer.
"$PY" "$DESK" post --kind answer --source my-project --title "Why is CI slower today?" \
    --question "Why did today's CI run take twice as long?" --body-file answer.md

# Wait for a follow-up question on this source's messages, then answer it.
"$PY" "$DESK" wait --followups --source my-project
"$PY" "$DESK" post --kind answer --source my-project --reply-to <follow-up id> \
    --title "About 25 minutes" --body-file followup.md

# Post a notice. --body - reads the body from stdin.
"$PY" "$DESK" post --kind info --source my-project --title "Long run finished" --body "Results in ..."

# The user answered in the chat instead: mark the decision handled.
"$PY" "$DESK" close --id <id> --text "User answered in chat: B"

# Look things up.
"$PY" "$DESK" list [--open] [--source S] [--repo R] [--json]
"$PY" "$DESK" responses [--source S] [--id ID] [--since 2026-01-15T09:00:00+00:00]
"$PY" "$DESK" followups [--source S] [--since TS] [--json]
```

| Command | Options | Exit codes |
|---|---|---|
| `post` | `--kind {decision,answer,info}`, `--source` and `--title` (required); `--body TEXT` / `--body -` (stdin) / `--body-file FILE`; `--question` / `--question-file` (answers); `--option "label::description"` (repeatable), `--recommended N` (1-based), `--priority {normal,high}` (decisions); `--reply-to ID`; `--repo NAME`; `--no-launch`; `--allow-text` (no longer needed, kept for compatibility) | 0 posted, prints the id; 1 invalid input |
| `wait` | `--id ID`, or `--source S` [`--since TS`] for the next reply from that source; `--followups --source S` for follow-ups; `--timeout SECONDS` (0 = forever, the default); `--interval SECONDS` | 0 reply or follow-up printed; 2 timeout; 4 (`--followups`) the shell that started it is gone; 1 invalid `--since` |
| `close` | `--id ID` (required), `--text NOTE` | 0 closed; 3 the user already replied in ClaudeDesk (that reply is printed); 1 unknown id |
| `responses` | `--source`, `--id`, `--since` | 0; one reply per line |
| `followups` | `--source`, `--since`, `--json` | 0; status is answered, delivered (handed to a session) or stored |
| `list` | `--open` (waiting decisions only), `--source`, `--repo`, `--json` | 0 |

- `--data DIR` (before the subcommand) or the `CLAUDEDESK_DATA` environment variable points `desk.py` at another data folder; the app accepts the same. The default is `data\` next to `desk.py`.
- `post` starts ClaudeDesk (minimized) if it isn't running; `--no-launch` turns that off. If no running ClaudeDesk watches this data folder (for example a stray copy of `desk.py`), `post` warns on stderr: the user won't see the message and `wait` won't get a reply.
- `wait --id` matches on the id alone and returns at once if the reply already exists; a different `--source` only prints a note.
- `wait --followups` hands over one follow-up at a time (the oldest first, including ones sent while no session was listening, up to 24 hours back) and marks it delivered, so two listeners never get the same one. While it runs, ClaudeDesk shows the session as online. Run one per source and start it again after each answer.
- `--reply-to` takes the follow-up `id` from `wait --followups` (the question is filled in for you) or a message id (then pass the follow-up text as `--question`).

A reply, as printed by `wait`:

```json
{"id": "20260115-093000-a1b2c3", "ts": "2026-01-15T09:41:07.512+00:00", "choice": "Full regression",
 "text": "also run the payment tests", "source": "my-project", "title": "Run the full regression suite before releasing?",
 "choice_index": 1}
```

`choice` is the option's label (`null` for a text-only reply) and `choice_index` is 1-based. Replies written for you carry a flag and `"choice": null`: `"resolved": true` (marked handled), `"dismissed": true` (archived or deleted while waiting) or `"closed_by": "claude"` (`desk.py close`).

A follow-up, as printed by `wait --followups`:

```json
{"id": "20260115-095500-d4e5f6", "ts": "…", "msg": "20260115-093000-a1b2c3", "kind": "decision", "source": "my-project",
 "title": "Run the full regression suite before releasing?", "question": "", "choice": "Full regression",
 "reply_text": "also run the payment tests", "text": "How long will that take?"}
```

`msg` is the message being asked about and `text` is the follow-up. For a decision it also carries the user's reply (`choice`, `reply_text`, and `resolved` / `dismissed` / `closed_by` when set).

## How it works

```text
Claude Code session                          ClaudeDesk (tray app)
  desk.py post --kind decision ...   ──►  data/inbox.jsonl       ──►  notification, badge, list
  desk.py wait --id <id>  (background)                                 you pick an option, submit
      ◄── exits with the reply JSON   ◄──  data/responses.jsonl  ◄──
  desk.py wait --followups           ◄──  data/followups.jsonl   ◄──  you ask a follow-up
  desk.py post --reply-to <id>       ──►  data/inbox.jsonl       ──►  shown under your question
```

- `desk.py` appends messages and blocks on the reply files; it never talks to the app over the network.
- The app watches the files (it checks their size every second and reads only what is new), shows the messages in a local web page inside Edge WebView2 (pywebview), and writes your replies.
- A named pipe per data folder tells `desk.py` whether an app is watching; another per source tells the app whether a session is listening for follow-ups.

## Data files

Everything lives in `data\` next to `ClaudeDesk.exe` and `desk.py`.

| File | Written by | Contents |
|---|---|---|
| `inbox.jsonl` | `desk.py post` appends; the app rewrites it when you delete messages | One message per line |
| `responses.jsonl` | The app (your replies) and `desk.py close`; append-only | One reply per line |
| `followups.jsonl` | The app (your follow-ups) and `desk.py wait --followups` (delivery marks); append-only | Follow-ups and "delivered" records |
| `state.json` | The app | Read / notified / archived / deleted ids, repo filing, closed tabs, settings, window position |
| `instance.json` | The app | Port and token of the running instance, so a second launch hands over to it |
| `claudedesk.log` | The app | Log (start, update, errors), rotated at 1 MB |
| `.lock` | Both | Cross-process lock file |

A message (one line of `inbox.jsonl`):

```json
{"id": "20260115-093000-a1b2c3", "ts": "2026-01-15T09:30:00.123+00:00", "source": "my-project", "repo": "my-project",
 "kind": "decision", "title": "…", "body": "Markdown", "priority": "normal",
 "options": [{"label": "Option A", "description": "…"}], "recommended": 1, "allow_text": true}
```

- `kind` is `decision`, `answer` or `info`. Answers may carry `question`; answers to follow-ups carry `reply_to` (and `followup_id`).
- `repo` is the git repo the message was posted from; tabs are built from it. It is missing when `desk.py` ran outside a repo and had no folder name to use.
- `priority` is `normal` or `high`. Messages whose `source` starts with `selftest` are hidden unless the app runs with `--show-selftest`.

**Concurrency.** All three files are append-only, except that deleting messages in the app rewrites `inbox.jsonl` under the lock. Every append takes a byte lock on `data\.lock` (`msvcrt.locking`), writes the whole line in one `write` and `fsync`s it; a half line left by a crashed writer is closed with a newline first. Twenty-four processes posting at once produce 24 intact lines. Readers consume up to the last newline and skip malformed lines; a replaced file (smaller, or a new file id) is read again from the start. "Only one reply per decision" is checked inside the lock, for the app and `close` alike.

## Self-update

- Every green CI build on `main` is published as a GitHub release tagged `build-<N>`, with `ClaudeDesk.exe` and `ClaudeDesk.exe.sha256`.
- The app asks the GitHub Releases API for the latest release about 45 seconds after it starts and then every 6 hours. When there is a newer build it downloads the exe next to itself and checks its SHA-256.
- To swap, it renames itself to `ClaudeDesk.exe.old` (Windows allows renaming a running exe), puts the new exe in place, starts it and exits; the new instance deletes the `.old` file. The bundled `desk.py` is refreshed at the same time, so the CLI always matches the app.
- It never restarts under you while the window is open: it waits until you close the window to the tray, or you click "更新到 build N" in the bottom-left corner.
- Auto-update can be turned off in Settings or the tray menu. The app still looks for new builds and shows "更新到 build N", but installs only when you click it. "检查更新" checks by hand.
- An exe you build yourself reports build 0 and never updates itself.

## Security and privacy

- The UI server binds to `127.0.0.1` only, rejects unknown `Host` headers (against DNS rebinding) and requires a random per-launch token on every API call (against other web pages).
- Message bodies are Markdown rendered through DOMPurify; raw HTML in a body cannot run script or cover the app.
- The only network requests go to the GitHub Releases API and release downloads, for updates. There is no telemetry. Your messages stay in `data\`.
- See [SECURITY.md](SECURITY.md) for how to report a vulnerability.

## Build from source

Python 3.10+ on Windows for the tray app. The UI also runs in any browser on any OS with `--serve`.

```bat
pip install -r requirements.txt
cd src
python -m claudedesk                 :: tray + window
python -m claudedesk --serve         :: local server only; open the printed URL in a browser
cd ..
build.cmd [-Install]                 :: one-file ClaudeDesk.exe (build 0, no self-update)
```

Layout:

```text
desk.py                   CLI (standard library only; also the app's file layer)
src/claudedesk/           app.py (tray, window, updates), store.py (data), server.py (local HTTP),
                          update.py, projects.py, icon.py, winapi.py
src/claudedesk/assets/    UI: index.html, app.css, app.js, markdown.js
  vendor/                 markdown-it, KaTeX, highlight.js, DOMPurify and fonts (scripts/vendor.py)
scripts/                  PyInstaller entry point, vendor.py, screenshots.py
skill/claude-desk/        the Claude Code skill
tests/                    pytest: data layer, CLI, server, and the real UI in Chromium via Playwright
.github/workflows/        CI: tests → build → packaged self-test → end-to-end (post, reply, self-update) → release
```

Tests:

```bash
pip install -r requirements-dev.txt
python -m playwright install chromium
python -m pytest -q
```

On Windows you can skip the Chromium download and point the UI tests at Edge with `CHROMIUM_PATH`. Details in [CONTRIBUTING.md](CONTRIBUTING.md).

## Contributing

Bug reports, ideas and pull requests are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) first; changes are listed in [CHANGELOG.md](CHANGELOG.md).

## License

[MIT](LICENSE). Bundled front-end libraries and fonts are under MIT, BSD, Apache 2.0 and OFL licenses; see `src/claudedesk/assets/vendor/LICENSES.txt`.
