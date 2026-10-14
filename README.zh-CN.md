# ClaudeDesk

[![build](https://github.com/tsljgj/ClaudeDesk/actions/workflows/build.yml/badge.svg?branch=main)](https://github.com/tsljgj/ClaudeDesk/actions/workflows/build.yml)
[![release](https://img.shields.io/github/v/release/tsljgj/ClaudeDesk?display_name=tag)](https://github.com/tsljgj/ClaudeDesk/releases/latest)
[![license](https://img.shields.io/github/license/tsljgj/ClaudeDesk)](LICENSE)
![platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078D6)

[English](README.md) · 中文

ClaudeDesk 是一个 Windows 托盘小程序，让 Claude Code 会话在终端之外找得到你。需要你拍板时，会话不再用自带的 AskUserQuestion，而是发来一条**决定**，带着选项在后台等；你在桌面上选一个、写两句补充，会话就被唤醒、接着干活。你问会话的问题，它除了在对话里回答，也把原问题和完整**回答**发到这里，不会被一屏屏工具输出淹没；看完还能直接在这里**追问**。偶尔的**通知**（"长任务跑完了"、"任务挂了"）也发到这里。

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/screenshot-dark.png">
  <img alt="ClaudeDesk 主窗口：仓库标签、消息列表，以及一条打开的决定（选项和回复框）" src="docs/screenshot-light.png">
</picture>

> 第三方工具，与 Anthropic 无关，也未经其认可。界面是简体中文。

## 目录

- [功能](#功能)
- [安装](#安装)
- [快速上手：接入 Claude Code](#快速上手接入-claude-code)
- [日常使用](#日常使用)
- [快捷键](#快捷键)
- [命令行参考（`desk.py`）](#命令行参考deskpy)
- [工作原理](#工作原理)
- [数据文件](#数据文件)
- [自动更新](#自动更新)
- [安全与隐私](#安全与隐私)
- [从源码构建](#从源码构建)
- [参与贡献](#参与贡献)
- [许可](#许可)

## 功能

- **决定都带回复框。** 选项可以带说明、标出推荐的那个，每条决定都能另写补充文字。等待中的会话收到的是一行 JSON。
- **回答和追问。** 回答保留你的原问题。任何回答、通知、已经处理过的决定都能追问；会话在听的话会接着回答，回答挂回你的追问下面。
- **每个仓库一个标签。** 消息按会话所在的 git 仓库分开。标签可以关掉、再找回来；关掉的标签在那个仓库来新消息时自动回来。
- **为分拣设计。** 待决定队列条和 `N` 跳到下一条，"只看未处理"（`F`），任意选中的消息都能"标为已处理"（`R`），一键归档已处理的，撤销（`Z`），键盘多选。
- **完整的 Markdown。** 表格、代码高亮、LaTeX 公式（`$…$`、`$$…$$`、`\(…\)`、`\[…\]`），字体和渲染库都打包在本地，离线可用。每条消息可以复制成 Markdown、富文本或纯文本，也可以导出 PDF。
- **不会错过，也不吵。** Windows 通知、托盘角标和任务栏角标显示未读数；紧急的决定一直闪到你看过为止。
- **浅色 / 深色 / 跟随系统**，四种强调色，无衬线或衬线正文字体，三档字号，三档正文宽度，两种列表密度。
- **小、全在本地。** 一个 exe，一个只用标准库的命令行，旁边几份普通的 JSONL 文件。不用注册，不收集数据，从 GitHub Releases 自动更新。

## 安装

需要 Windows 10 或 11（自带 Edge WebView2）。

1. 从 [Releases](https://github.com/tsljgj/ClaudeDesk/releases/latest) 下载 `ClaudeDesk.exe`，放进一个你有写权限的文件夹，例如 `%LOCALAPPDATA%\Programs\ClaudeDesk\`。不要放 `Program Files`，否则没法自动更新。
2. 双击运行。它会在自己旁边放好 `desk.py`（给 Claude 用的命令行）和 `data\`（收件箱），然后待在托盘里。
3. 接入 Claude Code（见下一节）。

从 1.x 升级：先在托盘里退出旧版本，把新的 `ClaudeDesk.exe` 放进原来的文件夹即可。`data\` 原样沿用；旧的 `_internal\` 文件夹可以删掉。

> Windows 11 默认把新托盘图标收进"^"里。想让它常驻显示：设置 → 个性化 → 任务栏 → 其他系统托盘图标 → 打开 ClaudeDesk。

## 快速上手：接入 Claude Code

1. 把 [`skill/claude-desk/SKILL.md`](skill/claude-desk/SKILL.md) 复制到 `~/.claude/skills/claude-desk/SKILL.md`。
2. 把文件开头的 `DESK` 改成 `ClaudeDesk.exe` 旁边那个 `desk.py`，`PY` 改成你的 Python（3.10+）。
3. 想让每个会话都遵守，再在 `~/.claude/CLAUDE.md` 里加一段：

   ```markdown
   ## 和用户沟通：ClaudeDesk
   - 需要用户决定的事不用 AskUserQuestion，一律用 skill claude-desk 发 decision，然后后台 wait。
   - 回答用户的问题时，对话里照常回答，同时用 claude-desk 发 answer（附原问题和完整回答）。
   ```

skill 是用中文写的，和界面一致。英文会话里 Claude 一样照做，命令也完全相同。

## 日常使用

### 窗口和托盘

| 做什么 | 怎么做 |
|---|---|
| 打开 | 双击 `ClaudeDesk.exe` 或点托盘图标。已经在运行时再双击只会把窗口切到前台 |
| 关窗口 | 点 × 只是缩到托盘，消息照样收；在托盘菜单里退出 |
| 开机自启 | 设置或托盘菜单里的"开机自启"（写在 `HKCU\…\Run`，开机后只待在托盘） |
| 托盘图标 | 红色数字 = 未读数；没有未读、但还有没回复的决定 = 红点；闪烁 = 有没看过的决定或紧急消息 |
| 任务栏按钮 | 窗口开着或最小化时带同样的红色角标。窗口关在托盘里时来了消息，任务栏会冒出一个最小化的按钮，带着角标闪：决定和紧急的一直闪到你切过来或在别处处理完，其余的闪 3 次 |

新消息到达时还会弹 Windows 通知，点通知直接打开那一条。

### 仓库标签

- 窗口最上面一排是**全部项目**，后面每个仓库一个标签，按名字排。仓库名由 `desk.py post` 记下：发消息时当前目录所在的 git 仓库（origin 地址里的仓库名；worktree 认得出主仓库；不在 git 里就用当前目录名；`--repo` 可以手动指定）。
- 点一个标签只看它；`Ctrl` / `Shift` + 点可以同时选几个；`[` / `]` 切换；`Esc` 或点"全部项目"回到全部。同时看几个仓库时，列表按仓库分组。视图上的数字、"全部标为已读"、"归档已处理的"都只算选中的仓库。
- **关掉标签**：点标签上的 × 或用鼠标中键。它的消息不再显示、不计数（那里还有待决定时会先问一下，`Z` 可以撤销）。这个仓库来新消息时，标签自动回来。标签条右头的**已关闭 N** 和设置里都列着关掉的标签，点一下找回。
- 旧消息（记录仓库之前发的）会对到 Claude Code 自己的会话记录（`~/.claude/projects`，以及 `CLAUDE_CONFIG_DIR` 指的目录）里出现过的仓库。实在对不上的放进**未归类**，它只在有消息时出现。在分组标题旁点"归到…"或右键仓库标签，可以把某个来源归到一个仓库下，设置里可以撤销。
- 标签放不下时，滚轮可以横着翻；右边被挡住的标签里有待决定时，会出现一个小橙点指着它。

### 列表

- 四个视图：**全部**（每次打开窗口都在这里）、**决定**、**回答**、**归档**。橙色胶囊是待决定的条数，灰色数字是未读条数。
- **待决定队列条**：有待决定时，搜索框下面有一条"N 条待决定 · M 条紧急 · 最久已等 X"。点它或按 `N` 跳到选中仓库里的下一条待决定（紧急的、等得最久的在前；`Shift+N` 往回）。待决定的那一行，时间的位置写着会话已经等了多久。在看不到的地方来了新的待决定或紧急消息时，会弹一条提示，按 `N` 直接打开它。
- 搜索框旁边的**只看未处理**（`F`）只留下待决定的和没读过的。正在看的那条要等你换到别的才走。这个开关会记住。
- 再旁边的**归档已处理的**（盒子图标）一键归档选中仓库里已读、不用再决定的消息，不问，`Z` 可以撤销。右上角"⋯"菜单里也有它，另有"全部标为已读"。
- 列表左边的圆点：**实心 = 没读过**；**橙色实心 = 没看过的待决定**；**橙色空心环 = 看过、还没决定**；**外面再套一圈 = 紧急的待决定**。第二行写着状态（待决定、✓ 你选的选项、✓ 已处理、已跳过、已追问 · 等回答）。用 `↑` `↓` 扫过去不算读，停 0.8 秒才标为已读。
- 鼠标移到一条上，右边会出现它自己的操作（已读 / 未读、标为已处理、归档、删除），左边出现勾选框。也可以右键。
- **多选**：点勾选框（`Shift` 连选）、`Ctrl` + 点、`X` 勾当前这条、`Shift+↑↓`、`Ctrl+A`。勾上以后出现批量栏：全选、标为已处理、已读、归档、删除。
- 搜索：`/` 或 `Ctrl+F`，按标题、正文、来源、原问题、选项搜。被当前视图、仓库或关掉的标签挡住的结果，列表末尾会写出有几条，点一下就能看到。

### 决定

- 按 `1`–`9` 或点选项，需要的话在回复框里写补充（每条决定都有回复框），然后 `Ctrl+Enter`（焦点在哪都行）或点"提交"。没有选项的决定只收文字。选了一半、写了一半切到别的消息再回来，草稿还在。
- 推荐的选项带"推荐"标记，卡片上写着会话已经等了多久。每条决定只能回复一次；提交后点"下一条待决定 →"（或按 `N`）继续。
- **标为已处理**（`R`）对任意选中的消息都能用：待决定的告诉等待中的会话"已经处理好了"，不选选项（回复里带 `"resolved": true`）；其余的标为已读。牵涉待决定时 `R` 会先问一下，因为会话马上就会收到；不牵涉的可以撤销。
- 归档（`E`）或删除（`Delete`）一条还在等的决定时，会告诉等待中的会话"用户跳过了"（`"dismissed": true`），会话不会一直卡着。删除会把消息从收件箱文件里真正去掉。

### 追问

- 回答、通知，以及已经有回复的决定（选了选项、标为已处理、跳过了、在对话里处理了），底部都有一个**追问**框。`Enter` 进入，`Ctrl+Enter` 发送。
- 发这条消息的会话在听（`desk.py wait --followups`）时，追问框写着会话在线，追问马上送到。会话的回答显示在你的追问下面，列表里标着"回应追问"，点开有链接回到原消息。
- 没有会话在听时，追问先存着；点**复制追问**会连同原消息的标题和 id 一起复制，粘到 Claude 对话里就行。回答来之前，那一行写着"已追问 · 等回答"。

### 阅读、复制和设置

- 阅读区右上角：复制成 Markdown（`C`；旁边的小箭头可选富文本或纯文本），导出 PDF（`Ctrl+P`）。代码块有自己的复制按钮。
- 窄窗口（宽度 720 像素以内）：列表和阅读页轮流占满窗口；`↑` `↓` 在列表里挪光标，回车打开，`Esc` 或 `Backspace` 返回。
- **设置**（右上角的滑块图标，或 `Ctrl+,`）：外观（跟随系统、浅色、深色）、强调色、正文字体（无衬线：Inter + 思源黑体；衬线：Source Serif + 思源宋体）、字号、**正文宽度**（适中 720 像素、宽 920 像素（默认）、铺满）、列表密度、开机自启、自动更新、检查更新、打开数据目录、项目归类、已关闭的标签。

## 快捷键

在程序里按 `?` 看同一张表。

| 浏览 | | 决定 | |
|---|---|---|---|
| `↑` `↓` / `J` `K` | 上一条 / 下一条 | `1`–`9` | 选第 N 项 |
| `N` / `Shift+N` | 下一条 / 上一条待决定 | `Ctrl+Enter` | 提交，或发追问 |
| `Shift+↑` `↓` | 连续勾选 | `Enter` | 打开，或写补充说明 / 追问 |
| `/`、`Ctrl+F` | 搜索 | `R` | 标为已处理 |
| `[` `]` | 切换仓库标签 | | |
| `F` | 只看未处理（开 / 关） | | |
| `Esc` | 退一层：菜单或对话框 → 窄窗口的阅读页 → 搜索 → 勾选 → 仓库筛选 | | |

| 整理 | | 其他 | |
|---|---|---|---|
| `E` | 归档 / 移出归档 | `C` | 复制 Markdown |
| `U` | 已读 / 未读 | `Ctrl+P` | 导出 PDF |
| `X` | 勾选当前这条 | `Ctrl+,` | 设置 |
| `Ctrl+A` | 全选 | `?` | 快捷键 |
| `Delete` | 删除 | | |
| `Z`、`Ctrl+Z` | 撤销（提示还在时） | | |

## 命令行参考（`desk.py`）

`desk.py` 只用标准库（Python 3.10+）。请用 `ClaudeDesk.exe` 旁边的那一份：程序会让它和自己保持同一版本。

```bash
PY=python
DESK=C:/path/to/ClaudeDesk/desk.py

# 发一条决定；打印新消息的 id。正文放在 UTF-8 的 Markdown 文件里
"$PY" "$DESK" post --kind decision --source my-project --title "发布前先跑一轮完整回归测试吗？" \
    --body-file plan.md --option "先跑回归测试::约 25 分钟，最稳妥" \
    --option "直接发布::CI 已经跑过单元测试" --option "只跑冒烟测试::约 5 分钟" \
    --recommended 1 [--priority high]

# 阻塞到你回复（放在后台跑）。退出码 0，回复是一行 JSON
"$PY" "$DESK" wait --id <id> [--timeout 秒]

# 发一条回答：用户的原问题 + 完整回答
"$PY" "$DESK" post --kind answer --source my-project --title "今天的 CI 为什么变慢了" \
    --question "今天的 CI 为什么比平时多跑了一倍时间？" --body-file answer.md

# 等用户对这个来源的消息追问，再回答它
"$PY" "$DESK" wait --followups --source my-project
"$PY" "$DESK" post --kind answer --source my-project --reply-to <追问 id> \
    --title "大约 25 分钟" --body-file followup.md

# 发一条通知。--body - 表示从 stdin 读正文
"$PY" "$DESK" post --kind info --source my-project --title "长任务跑完了" --body "结果在 ..."

# 用户直接在对话里答了：把这条决定标成已处理
"$PY" "$DESK" close --id <id> --text "用户在对话里选了 B"

# 查询
"$PY" "$DESK" list [--open] [--source S] [--repo R] [--json]
"$PY" "$DESK" responses [--source S] [--id ID] [--since 2026-01-15T09:00:00+00:00]
"$PY" "$DESK" followups [--source S] [--since 时间] [--json]
```

| 子命令 | 参数 | 退出码 |
|---|---|---|
| `post` | `--kind {decision,answer,info}`、`--source`、`--title`（必填）；`--body 文字` / `--body -`（stdin）/ `--body-file 文件`；`--question` / `--question-file`（回答）；`--option "label::description"`（可重复）、`--recommended N`（从 1 开始）、`--priority {normal,high}`（决定）；`--reply-to ID`；`--repo 仓库名`；`--no-launch`；`--allow-text`（已不需要，留着兼容） | 0 发出，打印 id；1 参数不对 |
| `wait` | `--id ID`；或 `--source S` [`--since 时间`] 等这个来源的下一条回复；`--followups --source S` 等追问；`--timeout 秒`（0 = 一直等，默认）；`--interval 秒` | 0 打印回复或追问；2 超时；4（`--followups`）启动它的 shell 已经没了；1 `--since` 不是时间 |
| `close` | `--id ID`（必填）、`--text 说明` | 0 已标成已处理；3 用户已经在 ClaudeDesk 里回复过（打印那条回复）；1 没有这条消息 |
| `responses` | `--source`、`--id`、`--since` | 0；每行一条回复 |
| `followups` | `--source`、`--since`、`--json` | 0；状态是已回答、已送达（交给了会话）或未送达 |
| `list` | `--open`（只看待决定）、`--source`、`--repo`、`--json` | 0 |

- `--data 目录`（写在子命令前）或环境变量 `CLAUDEDESK_DATA` 可以让 `desk.py` 用别的数据目录，程序也认这两个。默认是 `desk.py` 旁边的 `data\`。
- `post` 发现 ClaudeDesk 没在运行时会自动以最小化启动它；`--no-launch` 关掉。没有 ClaudeDesk 在看这个数据目录时（比如用了别处的一份 `desk.py` 副本），`post` 会在 stderr 提醒：这时用户看不到消息，`wait` 也等不到回复。
- `wait --id` 只按 id 认，已经有回复就立刻返回；`--source` 写得不一样只会提醒一句。
- `wait --followups` 一次交出一条追问（最早的先交，没人在听时发的、24 小时以内的也算），并记为已送达，两个监听不会拿到同一条。它运行期间 ClaudeDesk 显示会话在线。每个来源挂一个，每次回答完再挂上。
- `--reply-to` 填 `wait --followups` 输出里的追问 `id`（原问题自动填好），或者填消息 id（这时用 `--question` 放追问原文）。

`wait` 打印的回复：

```json
{"id": "20260115-093000-a1b2c3", "ts": "2026-01-15T09:41:07.512+00:00", "choice": "先跑回归测试",
 "text": "顺便把支付流程的用例也跑一遍", "source": "my-project", "title": "发布前先跑一轮完整回归测试吗？",
 "choice_index": 1}
```

`choice` 是选项的 label（只写了文字时为 `null`），`choice_index` 从 1 开始。程序替你写的回复带一个标记，`choice` 为 `null`：`"resolved": true`（标为已处理）、`"dismissed": true`（还在等时被归档或删除）、`"closed_by": "claude"`（`desk.py close`）。

`wait --followups` 打印的追问：

```json
{"id": "20260115-095500-d4e5f6", "ts": "…", "msg": "20260115-093000-a1b2c3", "kind": "decision", "source": "my-project",
 "title": "发布前先跑一轮完整回归测试吗？", "question": "", "choice": "先跑回归测试",
 "reply_text": "顺便把支付流程的用例也跑一遍", "text": "回归测试要跑多久？"}
```

`msg` 是被追问的消息，`text` 是追问原文。追问的是决定时，还带着用户当时的回复（`choice`、`reply_text`，以及有的话 `resolved` / `dismissed` / `closed_by`）。

## 工作原理

```text
Claude Code 会话                              ClaudeDesk（托盘程序）
  desk.py post --kind decision ...   ──►  data/inbox.jsonl       ──►  通知、角标、列表
  desk.py wait --id <id>（后台）                                        你选选项、提交
      ◄── 带着回复 JSON 退出          ◄──  data/responses.jsonl  ◄──
  desk.py wait --followups           ◄──  data/followups.jsonl   ◄──  你追问
  desk.py post --reply-to <id>       ──►  data/inbox.jsonl       ──►  显示在你的追问下面
```

- `desk.py` 追加消息、盯着回复文件等；它从不通过网络和程序通信。
- 程序盯着这些文件（每秒看一次大小，只读新增的部分），在 Edge WebView2（pywebview）里的本地网页上显示消息，并写下你的回复。
- 每个数据目录一个命名管道，`desk.py` 靠它知道有没有程序在看；每个来源另有一个，程序靠它知道有没有会话在听追问。

## 数据文件

都在 `ClaudeDesk.exe` 和 `desk.py` 旁边的 `data\` 里。

| 文件 | 谁写 | 内容 |
|---|---|---|
| `inbox.jsonl` | `desk.py post` 追加；你在界面里删除消息时程序整份重写 | 每行一条消息 |
| `responses.jsonl` | 程序（你的回复）和 `desk.py close`；只追加 | 每行一条回复 |
| `followups.jsonl` | 程序（你的追问）和 `desk.py wait --followups`（送达记录）；只追加 | 追问和"已送达"记录 |
| `state.json` | 程序 | 已读 / 已提醒 / 已归档 / 已删除的 id、项目归类、关掉的标签、设置、窗口位置 |
| `instance.json` | 程序 | 正在运行的那个实例的端口和 token，第二次启动时靠它把窗口交给已经在跑的那个 |
| `claudedesk.log` | 程序 | 运行日志（启动、更新、出错），满 1 MB 轮换 |
| `.lock` | 两边 | 跨进程锁文件 |

消息（`inbox.jsonl` 一行）：

```json
{"id": "20260115-093000-a1b2c3", "ts": "2026-01-15T09:30:00.123+00:00", "source": "my-project", "repo": "my-project",
 "kind": "decision", "title": "…", "body": "Markdown 正文", "priority": "normal",
 "options": [{"label": "方案 A", "description": "…"}], "recommended": 1, "allow_text": true}
```

- `kind`：`decision` / `answer` / `info`。回答可以带 `question`；回答追问的还带 `reply_to`（和 `followup_id`）。
- `repo`：发消息时所在的 git 仓库名，标签按它分。`desk.py` 不在仓库里、也没有可用的目录名时没有这个字段。
- `priority`：`normal` / `high`。`source` 以 `selftest` 开头的消息默认不显示（启动参数 `--show-selftest` 可以显示）。

**并发与容错。** 三个文件平时都只追加；唯一的例外是你在界面里删除消息时，程序在锁内整份重写 `inbox.jsonl`。每次追加先拿 `data\.lock` 的字节锁（`msvcrt.locking`），一次 `write` 写完整行并 `fsync`；文件末尾是别人崩溃留下的半行时，先补一个换行。实测 24 个进程同时 `post`，24 行全部完整。读的一方只读到最后一个换行，坏行跳过；文件被换掉（变小或换了文件号）就从头重读。"一条决定只能回复一次"在锁内检查，界面和 `close` 都一样。

## 自动更新

- CI 每次在 `main` 上构建通过，就发布一个 tag 为 `build-<N>` 的 GitHub release，附 `ClaudeDesk.exe` 和 `ClaudeDesk.exe.sha256`。
- 程序启动约 45 秒后向 GitHub Releases API 查一次最新版本，之后每 6 小时一次。有新版本就把 exe 下载到自己旁边，校验 SHA-256。
- 替换时先把自己改名为 `ClaudeDesk.exe.old`（Windows 允许给运行中的 exe 改名），新文件放到原位置并启动，旧进程退出；新进程启动后删掉 `.old`。同时把旁边的 `desk.py` 换成同版本，命令行和程序永远一致。
- 窗口开着时不会打断你：等你把窗口关回托盘再装，或者点左下角的"更新到 build N"立刻更新。
- 设置或托盘菜单里可以关掉"自动更新"。关掉后程序照样查新版本、显示"更新到 build N"，但只在你点它时才装。"检查更新"可以手动查。
- 自己从源码构建的 exe 是 build 0，不会自动更新。

## 安全与隐私

- 界面用的本机服务只绑 `127.0.0.1`，拒绝陌生的 `Host` 头（防 DNS rebinding），每个 API 请求都要带每次启动随机生成的 token（防别的网页跨站调用）。
- 正文 Markdown 渲染后经过 DOMPurify 清洗，正文里的 HTML 不能执行脚本，也盖不住界面。
- 唯一的网络请求是为了更新：访问 GitHub Releases API 和下载 release 文件。不收集任何数据，消息只在 `data\` 里。
- 发现安全问题请按 [SECURITY.md](SECURITY.md) 私下报告。

## 从源码构建

托盘程序需要 Windows 上的 Python 3.10+。界面用 `--serve` 在任何系统的浏览器里都能跑。

```bat
pip install -r requirements.txt
cd src
python -m claudedesk                 :: 托盘 + 窗口
python -m claudedesk --serve         :: 只起本机服务，用浏览器打开打印出来的地址
cd ..
build.cmd [-Install]                 :: 打包成单文件 ClaudeDesk.exe（build 0，不自动更新）
```

目录：

```text
desk.py                   命令行工具（只用标准库；也是程序的文件读写层）
src/claudedesk/           app.py（托盘、窗口、更新）、store.py（数据层）、server.py（本机 HTTP 服务）、
                          update.py、projects.py、icon.py、winapi.py
src/claudedesk/assets/    界面：index.html、app.css、app.js、markdown.js
  vendor/                 markdown-it、KaTeX、highlight.js、DOMPurify 和字体（scripts/vendor.py 生成）
scripts/                  PyInstaller 入口、vendor.py、screenshots.py
skill/claude-desk/        给 Claude Code 用的 skill
tests/                    pytest：数据层、命令行、本机服务，以及用 Playwright 在 Chromium 里驱动真界面
.github/workflows/        CI：测试 → 打包 → 打包后自检 → 端到端（发消息、回复、自更新）→ 发布 release
```

测试：

```bash
pip install -r requirements-dev.txt
python -m playwright install chromium
python -m pytest -q
```

在 Windows 上也可以不下载 Chromium，用 `CHROMIUM_PATH` 让界面测试直接用 Edge。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 参与贡献

欢迎报告问题、提建议和 pull request。动手前先看 [CONTRIBUTING.md](CONTRIBUTING.md)；版本变化见 [CHANGELOG.md](CHANGELOG.md)。

## 许可

[MIT](LICENSE)。打包进来的前端库和字体分别使用 MIT、BSD、Apache 2.0 和 OFL 许可，见 `src/claudedesk/assets/vendor/LICENSES.txt`。
