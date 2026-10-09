# ClaudeDesk

English · [中文](README.zh-CN.md)

A small Windows tray app that gives Claude Code sessions a place to reach you, outside the terminal:

- **Decisions.** Instead of the built-in AskUserQuestion prompt, a session posts a decision with options. You pick one (and optionally add a note) in ClaudeDesk; the session, which has been waiting in the background, wakes up and carries on.
- **Answers.** When you ask a session a question, it answers in the chat as usual *and* posts the question plus the full answer here, so the answer doesn't get buried under pages of tool output.
- **Info.** Occasional notices ("the long run finished", "a job crashed").

Several sessions, in several projects, can post at once; each message shows its source.

> Third-party tool. Not affiliated with or endorsed by Anthropic.
>
> The user interface is currently in Simplified Chinese only.

## How it works

```text
Claude Code session                         ClaudeDesk (tray app)
  desk.py post --kind decision ...  ──►  data/inbox.jsonl      ──► toast, taskbar flash, tray badge
  desk.py wait --id <id>  (background)                              you click an option, Submit
      ◄── exits with the reply JSON  ◄──  data/responses.jsonl ◄──
```

- `desk.py` is a standard-library-only CLI. Claude runs it; it appends messages to `data/inbox.jsonl` and blocks on `data/responses.jsonl` until you reply.
- `ClaudeDesk.exe` (PySide6) watches the inbox, notifies you, renders the Markdown body (tables, code blocks), and writes your reply.
- Both files are append-only JSON Lines guarded by a cross-process byte lock, so any number of sessions can post at once. A decision can only be answered once.

## Install

Requires Windows 10/11 and Python 3.10+ (used once, to create the build venv).

```bat
git clone https://github.com/tsljgj/ClaudeDesk.git
cd ClaudeDesk
build.cmd -Install
```

`-Install` builds `ClaudeDesk.exe`, adds a `--minimized` shortcut to your Startup folder, and launches the app. Omit it to just build. If Python isn't found, pass `-Python C:\path\to\python.exe`.

To run from source without building: `pip install PySide6-Essentials`, then `python src\claudedesk.py`.

## Hook it up to Claude Code

1. Copy [`skill/claude-desk/SKILL.md`](skill/claude-desk/SKILL.md) to `~/.claude/skills/claude-desk/SKILL.md` and set the `PY` / `DESK` variables at the top to your Python and your `desk.py` path.
2. Optionally make it a standing rule in `~/.claude/CLAUDE.md`, e.g.:

   ```markdown
   ## Talking to the user: ClaudeDesk
   - For anything the user must decide, don't use AskUserQuestion: post a decision with skill claude-desk and wait for it in the background.
   - When answering a user's question, answer in the chat and also post it to ClaudeDesk as an answer (original question + full answer).
   ```

The skill is written in Chinese, to match the UI; Claude follows it fine either way, and the commands are the same.

## CLI reference (`desk.py`)

```bash
PY=python
DESK=C:/path/to/ClaudeDesk/desk.py

# Post a decision; prints the new message id. Body is a UTF-8 Markdown file.
"$PY" "$DESK" post --kind decision --source my-project --title "Review before freezing?" \
    --body-file plan.md --option "Freeze now::2 hours" --option "Review first::about 6 hours" \
    --recommended 2 --allow-text [--priority high]

# Block until you reply (run in the background). Exit 0 with the reply JSON; exit 2 on --timeout.
"$PY" "$DESK" wait --source my-project --id <id> [--timeout SECONDS]

# Post an answer: your original question plus the full answer.
"$PY" "$DESK" post --kind answer --source my-project --title "Do the two config dirs sync?" \
    --question "If I edit a skill in one, does the other change?" --body-file answer.md

# Other
"$PY" "$DESK" post --kind info --source X --title "Run finished" --body "Results in ..."   # --body - reads stdin
"$PY" "$DESK" responses [--source X] [--id ID] [--since ISO_TIMESTAMP]
"$PY" "$DESK" list [--open] [--source X] [--json]
"$PY" "$DESK" close --id <id> --text "User answered in chat: B"   # mark a decision handled
```

- `post` starts ClaudeDesk (minimized) if it isn't running; `--no-launch` turns that off.
- `--recommended` is a 1-based option index. Options are `"label::description"`; the description is optional. A decision with no options accepts a free-text reply.
- Data lives in `data/` next to `desk.py`. Override with `--data DIR` (before the subcommand) or the `CLAUDEDESK_DATA` environment variable; the app accepts the same.

A reply looks like:

```json
{"id": "20261003-181209-abb336", "ts": "2026-10-03T18:20:01.512-04:00", "choice": "Review first",
 "text": "only check G4", "source": "my-project", "title": "Review before freezing?", "choice_index": 2}
```

File formats, concurrency details, the hidden self-test channel, design notes and measured memory use are documented in the [Chinese README](README.zh-CN.md).

## Using the app

- Close (×) hides to the tray; quit from the tray menu. Running the exe again just brings the window forward.
- Tray icon: an orange "C"; a red badge counts unread messages; a yellow dot means decisions you've seen but not answered; the icon flashes orange/amber while there's an unseen decision or a high-priority message.
- New messages pop a Windows toast and flash the taskbar button. Decisions and high-priority messages keep flashing until you look.
- Three filters: decisions awaiting you (pinned to the top), answers, everything. Ctrl+F searches title, body, source, question and options.

## Project layout

```text
desk.py          CLI, also imported by the app (file I/O, locking, ids, timestamps)
src/             claudedesk.py (UI), store.py (data layer), icons.py (icon drawing)
packaging/       version.txt (exe version resource)
skill/           the Claude Code skill
build.ps1/.cmd   build with PyInstaller (onedir) into ClaudeDesk.exe + _internal/
```

`data/`, `.venv/`, `build/`, `ClaudeDesk.exe` and `_internal/` are local and git-ignored.

## License

[MIT](LICENSE)
