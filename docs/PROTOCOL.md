# ClaudeDesk session protocol (v2)

This is the maintainer reference for how Claude Code sessions talk to ClaudeDesk through `desk.py`.
The session-facing summary is `skill/claude-desk/SKILL.md`; keep the two in sync.

Goals: no wasted tokens, efficient, always in sync. In short:

- every message remembers **which session** posted it;
- each session runs **one** background `desk.py listen`, which returns once with **all** pending events for that session;
- answers are written once (in chat) and copied from the session transcript (`--body-from-chat`);
- the app shows, per message, whether the session is waiting, open but not listening, or gone.

## 1. Identity

Claude Code sets these for every command a session runs:

| variable | meaning |
|---|---|
| `CLAUDE_CODE_SESSION_ID` | session UUID (stable across `--resume`; **shared by the session's subagents**) |
| `CLAUDE_PID` | PID of the session's `claude.exe` |
| `CLAUDE_CONFIG_DIR` | set when a non-default config dir is used (transcripts live under it) |

`post` stores `session` (env, or `--session`), `session_pid` (env `CLAUDE_PID`, only when the session is the env one)
and `session_pid_start` (the process creation time, Windows FILETIME ticks). A PID counts as the session only while a
process with that PID **and** that creation time exists, so PID reuse is not mistaken for a live session.

`--source` is optional and only a display label (default: detected repo name, else the folder name). Routing never uses it.

## 2. Files (all in the data dir, all JSONL, appended under `data/.lock`)

| file | written by | records |
|---|---|---|
| `inbox.jsonl` | `post` | messages; v2 adds `session`, `session_pid`, `session_pid_start`. Rewritten by the app only to drop deleted messages. |
| `responses.jsonl` | app (reply / resolve / dismiss), `close` | one reply per message id; v2 adds `session` (so a reply can be routed after its message is deleted) |
| `followups.jsonl` | app | follow-ups `{id, ts, msg, source, title, text, session}`; legacy delivery marks `{"delivered": fid}` (read, no longer written) |
| `deliveries.jsonl` | `listen`, `wait`, `close`, `inbox --adopt` | see below; never rewritten |

`deliveries.jsonl` records, discriminated by `kind`:

```json
{"kind":"reply","id":"<message id>","session":"S","via":"listen|wait|close|adopt","ts":"…","pid":123}
{"kind":"followup","id":"<follow-up id>","session":"S","via":"listen|wait|adopt","ts":"…","pid":123}
{"kind":"adopt","from":"OLD","repo":"r1","session":"NEW","session_pid":456,"session_pid_start":133…,"ts":"…"}
{"kind":"pid","session":"S","session_pid":789,"session_pid_start":133…,"ts":"…"}
```

- **delivered**: an item is delivered if a `reply` / `followup` record names it (or, for follow-ups, a legacy
  `{"delivered": fid}` line exists in `followups.jsonl`). First record wins.
- **adopt**: messages of session `OLD` in repo `repo` now belong to `NEW` (chains are followed: A→B→C). A record without
  `repo` applies to every repo.
- **pid**: the session got a new `claude.exe` (resumed). The latest known PID of a session is the newest of: its messages'
  `session_pid`, its `adopt` and `pid` records.

## 3. Events

An **event** is an undelivered item owned by a session:

- a reply (`responses.jsonl`) to a message whose owner is S. Replies the session wrote itself (`closed_by: "claude"`) are never events;
- a follow-up on a message whose owner is S, unless a message already answers it (`reply_to` pairing, see `pair_followups`).

Owner = the message's `session`, mapped through adoptions for the message's repo. Legacy messages without `session`
never produce events; they keep using `wait --id` / `wait --followups`.

Event lines are compact one-line JSON, without message bodies:

```json
{"ev":"reply","id":"…","title":"…","choice":"B","choice_index":2,"text":"also update the README"}
{"ev":"reply","id":"…","title":"…","choice":null,"resolved":true}
{"ev":"followup","id":"<follow-up id>","msg":"<message id>","kind":"answer","title":"…","question":"<≤200 chars>","text":"…"}
{"ev":"followup","id":"…","msg":"…","kind":"decision","title":"…","choice":"B","reply_text":"…","text":"…"}
```

`text` is omitted when empty and for `resolved` / `dismissed` replies (the flag says it all). Follow-ups carry the original
`question` (clipped) so a session whose context was compacted, or that adopted the event, knows what was asked.
Answer a follow-up with `post --reply-to <follow-up id>`.

## 4. Commands

| command | stdout | exit codes |
|---|---|---|
| `post … [--session S] [--body-from-chat] [--question-from-chat]` | message id | 0; 1 bad args / transcript text not found. stderr hints when this session has no `listen` running |
| `listen [--session S] [--timeout s]` | one event per line | 0 delivered; 2 timeout; **4 session process gone (prints nothing)**; **5 this session already has a listener** (one stderr line); 1 no session |
| `close --id ID [--text T]` | the closing reply, or the user's existing reply | 0; **3 the user already replied in ClaudeDesk** (that reply is printed and marked delivered) |
| `close --mine [--text T]` | reply events for this session's decisions the user already answered, then `{"closed":[ids]}` | 0; 3 if any reply events were printed |
| `inbox [--repo R] [--adopt] [--session S]` | events left by **gone** sessions in repo R (default: detected), with `session` (8-char prefix); with `--adopt`: the same lines as `listen` | 0; 1 `--adopt` without a session |
| `status [--session S]` | `open=N undelivered=N listen=on/off[ orphaned=N]` | 0; 1 no session |
| `wait --id ID` (legacy) | the reply | 0; 2 timeout. Holds a per-decision presence marker; marks the reply delivered |
| `wait --followups --source X` (legacy) | one follow-up | 0; 2; 4. Marks into `deliveries.jsonl` |

### listen

1. Take the session's **exclusive** presence marker (named pipe `<pipe_name>-s-<sha1(session)[:12]>` created with
   `FILE_FLAG_FIRST_PIPE_INSTANCE`, max 1 instance). If it already exists: exit 5. The OS drops it when the process dies.
2. If `CLAUDE_PID` is set and that process (with its creation time) is not alive: exit 4, silently. Otherwise record a
   `pid` line if the session's latest known PID differs (resumed session).
3. Loop: `stat` the four files every `--interval` (1 s); recompute pending events only when a size/mtime changed.
   Once this session has events, wait until no new event arrived for **1.5 s** (`BATCH_QUIET`), at most **6 s**
   (`BATCH_MAX`) after the first, then **claim** them: under `data/.lock`, re-read the delivery marks, drop what was
   delivered meanwhile, append one delivery record per event, print them, exit 0. If everything was claimed by someone
   else (e.g. `close`), keep waiting.
4. Every 2 s check `CLAUDE_PID`; if the session is gone, exit 4 without output. Nobody reads it, and an orphaned
   listener must not keep claiming events.

### Delivery semantics

- **Exactly once**: every path that hands an item to a session (`listen`, `wait --id`, `wait --followups`, `close`,
  `inbox --adopt`) appends its delivery mark inside the same `data/.lock` critical section in which it re-checks the marks.
  Two listeners for one session cannot coexist (exclusive pipe), and legacy waiters see the same marks.
- **Old and new commands agree**: a reply consumed by legacy `wait --id` is marked (`via: wait`), so a later `listen`
  does not deliver it again. `close` marks both its own reply and an existing user reply it prints.
- Nothing is ever lost: undelivered events stay pending until the owner (or an adopter) claims them.

### --body-from-chat / --question-from-chat

Transcript: `<CLAUDE_CONFIG_DIR or ~/.claude>/projects/*/<session>.jsonl`, plus `<session>/subagents/*.jsonl`
(subagents share the session id). Each API message is split into one record per content block (`thinking`, `text`,
`tool_use`), all with the same `message.id`, chained by `parentUuid` (rewinds create branches). Records without `uuid`
(`last-prompt`, `ai-title`, `queue-operation`, …) and `attachment` records are ignored.

1. Read the last 2 MB of each candidate transcript; the **anchor** is the newest assistant `tool_use` whose input
   contains `-from-chat` (this very call; Claude Code writes it before running the tool). The transcript with the newest
   anchor wins (main session vs. subagent).
2. Walk `parentUuid` back from the anchor (only blocks before the anchor in its own record count) to the newest **real
   user message**: `type: user`, not `isMeta` / `isCompactSummary` / `isVisibleInTranscriptOnly`, `origin.kind` absent or
   `human`, no `tool_result`, and not a wrapper (`<command-name>`, `<local-command-…>`, `<task-notification>`,
   `[Request interrupted…`, …). If the chain leaves the window, read 4× more (finally the whole file).
3. **Body** = the newest run of assistant text blocks: text blocks not separated by a `tool_use` or a user record
   (tool result, notification). Earlier runs are usually narration ("let me check …") and are dropped. API-error and
   `<synthetic>` messages are skipped.
4. **Question** = the real user message's text blocks, minus IDE context blocks (`<ide_…>`) and `<system-reminder>`.
5. Empty or not found → exit 1 with `错误：--body-from-chat 没取到正文：<why>。改用 --body-file <文件>。`
   (or the `--question` equivalent). The lookup retries for ~1.2 s in case the record is not flushed yet.

## 5. Presence and session state (app)

The store reads `deliveries.jsonl` incrementally like the other files. Every `LISTEN_EVERY` (2 s) it lists `\\.\pipe\`
**once** and checks:

- `<pipe_name>-s-<hash(session)>`: a `listen` for that session;
- `<pipe_name>-w-<hash(message id)>`: a legacy `wait --id` for that decision;
- `<pipe_name>-listen-<hash(source)>`: a legacy `wait --followups` for that source;
- the latest PID of each known session (`OpenProcess` + `WaitForSingleObject` + `GetProcessTimes`); a PID found dead is
  cached and never checked again.

Per message (`summary.session_state`):

| state | when | decision card | follow-up card |
|---|---|---|---|
| `listening` | session has a `listen` (or legacy waiter for this item) | 会话在等，提交后马上收到。 | 会话在等，发出后马上收到。 |
| `open` | session PID alive (or unknown), not listening | 会话还开着，但现在没在听：回复会存着，它下次查看时收到。 | 会话还开着，但现在没在听：追问会存着，它下次查看时收到。（a delivered, unanswered follow-up shows 会话收到了你的追问，正在回答。） |
| `gone` | latest PID dead, not listening | 这个会话已经结束：回复会存着；在同一个仓库开新会话时，可以用 desk.py inbox 找回。 + 标为已处理 is emphasized, no confirm | same, plus copy-to-chat |
| `unknown` | legacy message without `session` | 会话已等 N 分钟 · 提交后立即继续 (unchanged) | unchanged legacy wording |

After a reply: `已送达会话 · HH:MM` (from `summary.delivered`) or `还没送达` with a state hint. Each follow-up line:
`等待回答… · 已送达会话 · HH:MM` / `等待回答… · 还没送达 · <hint>`. Open decisions of a gone session get a subtle
`会话已结束` tag in the list.

## 6. Edge cases

- **Resumed session** (`--resume`): same session id, new `claude.exe`. `listen` records a `pid` line, so the app and
  `inbox` see it alive again; its own pending events are delivered by session id as usual.
- **Subagents** share the session id and `CLAUDE_PID`: they must not run `listen` (it would be the session's single
  listener, and a subagent's prompt cache expires in minutes). The transcript lookup still finds a subagent's call.
- **New session in the same repo**: `inbox` lists events whose owner is gone (PID known and dead, no listener) and whose
  message repo matches; resolved/dismissed replies are not listed. `--adopt` writes `adopt` records for (old session,
  repo), claims the listed events and silently marks the old session's resolved/dismissed replies delivered. Later
  follow-ups on the old session's messages in that repo route to the adopter.
- **User answers in chat and in ClaudeDesk**: `close` exits 3 and prints the ClaudeDesk reply (marked delivered).
- **Message deleted** while a reply / follow-up is pending: responses and follow-ups carry `session`, so they still route.
- **Session without `CLAUDE_PID`** (`--session` by hand): state is `open` unless listening; never considered gone.
- **Two data dirs**: all marker names include the data-dir hash (`pipe_name`), so copies of `desk.py` elsewhere never
  look like listeners for this app.
- **Non-Windows**: markers are `flock`s on `data/.m-<hash>`; process checks use `kill(pid, 0)` without creation time.

## 7. Cost model

A session's turn costs input tokens for its whole context. Claude Code serves it from the prompt cache when warm
(cache read ≈ 0.1× the input price); the main session's cache lives about an hour, a subagent's about five minutes.
After expiry the next turn re-writes the context into the cache, ≈ **1.25× the context** in input-price terms. A
400k-token session woken after an hour therefore costs about 500k tokens before it does anything.

So the protocol minimises **wakes**, not lines of output:

- **One listener per session**, not one `wait` per decision plus one follow-up listener: every background task that
  exits wakes the session. With N decisions answered one by one the old protocol woke the session N times (plus once
  per follow-up); `listen` wakes it once per batch.
- **Batching** (1.5 s quiet, 6 s cap) folds bursts (answering several decisions in a row, a reply plus a follow-up)
  into one wake.
- **Duplicates exit immediately (5)** and dead sessions' listeners exit silently (4): a duplicate that later delivered
  something would be a second wake, and an orphan would steal events nobody reads. `post` says when no listener runs,
  so the session never has to check (`status` is a one-line check when needed).
- **No polling**: `list` / `responses` loops cost a turn each.
- **No double generation**: an answer is output once in chat; `--body-from-chat` copies it from the transcript.
  Writing it again into a file would cost the answer's output tokens a second time (output tokens are the most
  expensive), plus the tool-call input.
- **Compact events**: one short JSON line per event, never message bodies; the session already has them, and the
  follow-up `question` is clipped to 200 characters.
- `listen` itself is cheap: it `stat`s four files once a second and parses them only when they change.
