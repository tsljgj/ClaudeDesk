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
- **回答和追问。** 回答保留你的原问题。任何回答、通知、已经处理过的决定都能在页面最上面的追问框里追问；会话在听的话会接着回答，回答挂回你的追问下面，新的在上。
- **知道每个会话现在怎样。** 每条消息都记着发它的 Claude Code 会话。卡片上写着这个会话在等、还开着但没在听，还是已经结束，以及你的回复什么时候送到。每个会话只挂一个后台监听，回复和追问攒成一批送回去。
- **每个仓库一个标签。** 消息按会话所在的 git 仓库分开。标签可以关掉、再找回来；关掉的标签在那个仓库来新消息时自动回来。
- **为分拣设计。** 待决定队列条和 `N` 跳到下一条，"只看未处理"（`F`），任意选中的消息都能"标为已处理"（`R`，不惊动会话），按"早于 1 小时 / 1 天 / 7 天"归档已处理的，撤销（`Z`），键盘多选。
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
2. 文件开头定义 `desk` 的那一行写的是 `python C:/path/to/ClaudeDesk/desk.py`，把它换成你的 Python（3.10+）和 `ClaudeDesk.exe` 旁边那个 `desk.py`。
3. 想让每个会话都遵守，再在 `~/.claude/CLAUDE.md` 里加一段：

   ```markdown
   ## 和用户沟通：ClaudeDesk
   - 需要用户决定的事不用 AskUserQuestion，一律用 skill claude-desk 发 decision；回复由这个会话唯一的后台 `desk.py listen` 送回来。
   - 回答用户的问题时，对话里照常回答，再用 `--question-from-chat --body-from-chat` 发一条 answer。
   ```

skill 是用中文写的，和界面一致。英文会话里 Claude 一样照做，命令也完全相同。

### 会话怎么用它

- **每个会话不用单独设置。** `desk.py post` 自己记下它所在的 Claude Code 会话（Claude Code 给会话里的每条命令都设了 `CLAUDE_CODE_SESSION_ID` 和 `CLAUDE_PID`）和 git 仓库。回复、追问按会话送回去；`--source` 可以不写，只是显示用的名字。
- **每个会话只挂一个后台 `listen`。** `post` 在 stderr 提示没有 listen 在跑时，会话在后台启动 `desk.py listen`，不设超时。它把这个会话收到的东西（你对它的决定的回复、对它的消息的追问）一次交出来，每件一行 JSON；会话处理完这一批，再启动一次 `listen`。同一个会话再开第二个 `listen` 会立刻退出。子 agent 和主会话共用会话 id，不跑 listen。
- **回答只写一遍。** 会话在对话里写好回答，在同一条消息里紧接着运行 `desk.py post --kind answer --title "…" --question-from-chat --body-from-chat`。`desk.py` 从会话记录里取你的问题和这段回答，Claude 不用把回答再写一遍。
- **会话结束了也不丢。** 已经结束的会话的回复、追问都存着。同一个仓库里开的新会话用 `desk.py status` / `desk.py inbox` 能看到，用 `desk.py inbox --adopt` 接过来。

### 为什么省

后台命令每结束一次，Claude Code 就唤醒一次会话；每次唤醒都要把会话的整个上下文重新读一遍（prompt cache 还热时便宜，过期了就贵）。所以 ClaudeDesk 尽量少唤醒、少花 token：

- **每个会话一个监听。** 不是每条决定一个 `wait`、再加一个追问监听，而是每个会话一个 `listen`：回复了 N 条决定，不等于唤醒 N 次。
- **攒一下再唤醒。** 接连到的回复和追问（每件和上一件相隔 1.5 秒以内，最多等 6 秒）一次交出。连着回复三条决定，会话只醒一次。
- **回答不写第二遍。** `--body-from-chat` 从会话记录里取回答，不让 Claude 再把它写进文件一遍；输出 token 最贵。
- **不轮询。** 会话从不反复跑 `list` / `responses`。`listen` 每秒只看一眼数据文件的大小，变了才读；每件事是一行简短的 JSON，不带消息正文。
- **不会重复唤醒。** 重复的 `listen` 立刻退出；会话已经结束的 `listen` 不出声地退出，不会领走没人看的事。

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

- 窗口最上面一排是仓库标签，每个仓库一个，按名字排。没有把所有仓库混在一起的视图：每次只看一个仓库，或者你挑的几个。仓库名由 `desk.py post` 记下：发消息时当前目录所在的 git 仓库（origin 地址里的仓库名；worktree 认得出主仓库；不在 git 里就用当前目录名；`--repo` 可以手动指定）。
- 点一个标签看它；`Ctrl` / `Shift` + 点可以同时选几个（最后一个取消不掉）；`[` / `]` 在开着的标签之间切换。同时看几个仓库时，列表按仓库分组。视图上的数字、"全部标为已读"、"归档已处理的"都只算选中的仓库。
- 打开窗口时显示上次选的仓库；没有的话，显示有待决定、而且等得最久的仓库；再没有，就显示最近有消息的仓库。从托盘、系统通知或提示里打开一条消息时，自动切到它的仓库。
- **关掉标签**：点标签上的 × 或用鼠标中键。它的消息不再显示、不计数（那里还有待决定时会先问一下，`Z` 可以撤销）。关掉正在看的标签时，换到旁边那个。这个仓库来新消息时，标签自动回来。标签条右头的**已关闭 N** 和设置里都列着关掉的标签，点一下找回；标签全关掉时，列表里有**找回标签…**。
- 旧消息（记录仓库之前发的）会对到 Claude Code 自己的会话记录（`~/.claude/projects`，以及 `CLAUDE_CONFIG_DIR` 指的目录）里出现过的仓库。实在对不上的放进**未归类**，它只在有消息时出现。在分组标题旁点"归到…"或右键仓库标签，可以把某个来源归到一个仓库下，设置里可以撤销。
- 标签放不下时，滚轮可以横着翻；右边被挡住的标签里有待决定时，会出现一个小橙点指着它。

### 列表

- 四个视图：**全部**（每次打开窗口都在这里）、**决定**、**回答**、**归档**。橙色胶囊是待决定的条数，灰色数字是未读条数。
- **待决定队列条**：有待决定时，搜索框下面有一条"N 条待决定 · M 条紧急 · 最久已等 X"。点它或按 `N` 跳到选中仓库里的下一条待决定（紧急的、等得最久的在前；`Shift+N` 往回）；这里没有了，`N` 切到待决定等得最久的仓库并打开它。待决定的那一行，时间的位置写着会话已经等了多久。在看不到的地方来了新的待决定或紧急消息时，列表底部会出一条提示，按 `N` 直接打开它。
- 搜索框旁边的**只看未处理**（`F`）只留下待决定的和没读过的。正在看的那条要等你换到别的才走。这个开关会记住。
- 再旁边的**归档已处理的**（盒子图标）归档选中仓库里已读、不用再决定的消息，像清浏览器历史一样选范围：**早于 1 小时 / 早于 24 小时 / 早于 7 天 / 全部**，每档写着几条。"多久以前"按这条最后一次动静算：收到、你回复、你最后一次打开它。正在看的那条永远不动；上次选的那档会记住；`Z` 恰好撤销这一批。右上角"⋯"菜单里也有它，另有"全部标为已读"。
- 列表左边的圆点：**实心 = 没读过**；**橙色实心 = 没看过的待决定**；**橙色空心环 = 看过、还没决定**；**外面再套一圈 = 紧急的待决定**。第二行写着状态（待决定、✓ 你选的选项、✓ 已处理、已跳过、已追问 · 等回答）。用 `↑` `↓` 扫过去不算读，停 0.8 秒才标为已读。
- 鼠标移到一条上，右边会出现它自己的操作（已读 / 未读、标为已处理、归档、删除），左边出现勾选框。也可以右键。
- **多选**：点勾选框（`Shift` 连选）、`Ctrl` + 点、`X` 勾当前这条、`Shift+↑↓`、`Ctrl+A`。勾上以后出现批量栏：全选、标为已处理、已读、归档、删除。
- 搜索：`/` 或 `Ctrl+F`，在选中的仓库里按标题、正文、来源、原问题、选项搜。别的仓库里的结果在列表末尾按仓库各一个按钮（"其他项目：webapp 3 · …"），点了切到那个仓库、搜索词不变；被当前视图或关掉的标签挡住的结果也写在那里，点一下就能看到。
- 操作的确认、出错，以及撤销、重试按钮，都显示在列表底部，不会挡住正在看的消息。

### 决定

- 按 `1`–`9` 或点选项，需要的话在回复框里写补充（每条决定都有回复框），然后 `Ctrl+Enter`（焦点在哪都行）或点"提交"。没有选项的决定只收文字。选了一半、写了一半切到别的消息再回来，草稿还在。
- 决定卡片紧跟在标题下面，正文在它下方。推荐的选项带"推荐"标记。每条决定只能回复一次；提交后点"下一条待决定 →"（或按 `N`）继续。
- 卡片顶上那一行写着发它的会话现在怎样：

  | 那一行 | 意思 |
  |---|---|
  | 会话在等，提交后马上收到。（绿点） | 会话的 `listen` 在跑，回复马上送到 |
  | 会话还开着，但现在没在听：回复会存着，它下次查看时收到。 | 会话还开着，只是现在没在听；回复存着，等它再启动 `listen` 时送到 |
  | 这个会话已经结束：回复会存着；在同一个仓库开新会话时，可以用 desk.py inbox 找回。 | 会话的进程已经没了；回复存着，留给同一个仓库的新会话。"标为已处理"按钮会突出显示，这时通常就该点它 |
  | 会话已等 N 分钟 · 提交后立即继续 | 旧消息（旧版 `desk.py` 发的），没记是哪个会话 |

- 回复以后，"你的回复"写着会话收到没有：**已送达会话 · HH:MM**，或者**还没送达**加上原因（会话在等，马上就到 / 会话下次查看时收到 / 会话已经结束）。你标为已处理或跳过的决定写着**没有通知会话**。
- 列表里，会话已经结束的待决定带一个灰色的**会话已结束**标记。不需要了就选中它（或多选几条），按**标为已处理**（`R`）。
- **标为已处理**（`R`）对任意选中的消息都能用，而且不给会话发任何消息：用在你已经在对话里说过、或者这件事已经不重要的时候。待决定的直接关掉、不选选项（回复里带 `"resolved": true, "silent": true`），其余的标为已读。不会先问，`Z` 可以撤销：决定原样重新打开。
- 归档（`E`）或删除（`Delete`）一条还在等的决定时，按"跳过"关掉它（`"dismissed": true, "silent": true`），同样不通知会话；归档可以撤销，删除会先问。删除会把消息从收件箱文件里真正去掉；已经写下的回复、追问照样送得到会话。

### 追问

- 回答、通知，以及已经有回复的决定（选了选项、标为已处理、跳过了、在对话里处理了），标题下面紧跟着一个**追问**框，平时只有一行，点进去才展开。`Enter` 进入，`Ctrl+Enter` 发送。
- 每一页都是越往下越旧：最上面是追问框（还没决定的决定是决定卡片），然后是你的追问和它们的回答（新的在上），再往下是你对决定的回复，最底下是原问题和正文。
- 追问框下面那一行写着发这条消息的会话现在怎样，和决定一样：
  - **会话在等，发出后马上收到。** 它的 `listen` 在跑，追问马上送到。
  - **会话还开着，但现在没在听：追问会存着，它下次查看时收到。** 它下次启动 `listen` 时收到。
  - **会话收到了你的追问，正在回答。** 它刚领走你的追问，正在写回答。
  - **这个会话已经结束：追问会存着；在同一个仓库开新会话时，可以用 desk.py inbox 找回，也可以复制下来粘到对话里。**
- 每条还没回答的追问下面写着 **等待回答… · 已送达会话 · HH:MM**，或者 **等待回答… · 还没送达** 加上原因。会话的回答链接在你的追问下面，列表里标着"回应追问"，点开有链接回到原消息。
- 会话没在听时，点**复制追问**会把还在等的追问连同原消息的标题和 id 一起复制，粘到 Claude 对话里就行。回答来之前，那一行写着"已追问 · 等回答"。
- 没记会话的旧消息照旧：这个来源有 `desk.py wait --followups` 在跑时，追问框写着会话在线。

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

`desk.py` 只用标准库（Python 3.10+）。请用 `ClaudeDesk.exe` 旁边的那一份：程序会让它和自己保持同一版本。这一节讲的是会话协议 v2；完整的协议（文件、送达保证、边角情况、token 开销）见 [docs/PROTOCOL.md](docs/PROTOCOL.md)。

```bash
PY=python
DESK=C:/path/to/ClaudeDesk/desk.py

# 发一条决定；打印新消息的 id。正文放在 UTF-8 的 Markdown 文件里
# 调用它的 Claude Code 会话和 git 仓库自动记下
"$PY" "$DESK" post --kind decision --title "发布前先跑一轮完整回归测试吗？" \
    --body-file plan.md --option "先跑回归测试::约 25 分钟，最稳妥" \
    --option "直接发布::CI 已经跑过单元测试" --option "只跑冒烟测试::约 5 分钟" \
    --recommended 1 [--priority high]

# 这个会话唯一的监听。放在后台跑，不设超时。它把这个会话所有还没送达的回复和追问一次交出来，
# 每件一行 JSON；全部处理完，再启动一次
"$PY" "$DESK" listen

# 发一条刚在对话里写好的回答：原问题和回答都从会话记录里取
"$PY" "$DESK" post --kind answer --title "今天的 CI 为什么变慢了" --question-from-chat --body-from-chat

# 回答追问（id 是那条追问在 listen 输出里的 id）；原问题自动填追问原文
"$PY" "$DESK" post --kind answer --reply-to <追问 id> --title "大约 25 分钟" --body-from-chat

# 发一条通知。--body - 表示从 stdin 读正文
"$PY" "$DESK" post --kind info --title "长任务跑完了" --body "结果在 ..."

# 用户直接在对话里答了：把一条决定标成已处理，或者这个会话所有还在等的
"$PY" "$DESK" close --id <id> --text "用户在对话里选了 B"
"$PY" "$DESK" close --mine

# 检查、找回
"$PY" "$DESK" status                 # 一行：open=1 undelivered=0 listen=on
"$PY" "$DESK" inbox [--adopt]        # 已结束的会话在这个仓库留下、还没送达的；--adopt 接过来

# 查询
"$PY" "$DESK" list [--open] [--source S] [--repo R] [--json]
"$PY" "$DESK" responses [--source S] [--id ID] [--since 2026-01-15T09:00:00+00:00]
"$PY" "$DESK" followups [--source S] [--since 时间] [--json]
```

旧协议（每条决定一个后台 `wait`，每个来源一个追问监听）照样能用；没记会话的消息只能用它：

```bash
"$PY" "$DESK" wait --id <id> [--timeout 秒]              # 退出码 0，回复是一行 JSON
"$PY" "$DESK" wait --followups --source my-project      # 退出码 0，交出一条追问
```

| 子命令 | 参数 | 退出码 |
|---|---|---|
| `post` | `--kind {decision,answer,info}`、`--title`（必填）；`--source 名字`（只是显示用的名字；默认仓库名，不在仓库里用目录名）；`--body 文字` / `--body -`（stdin）/ `--body-file 文件` / `--body-from-chat`；`--question` / `--question-file` / `--question-from-chat`（回答）；`--option "label::description"`（可重复）、`--recommended N`（从 1 开始）、`--priority {normal,high}`（决定）；`--reply-to ID`；`--repo 仓库名`；`--session ID`；`--no-launch`；`--allow-text`（已不需要，留着兼容） | 0 发出，打印 id；1 参数不对、`--reply-to` 认不出，或 `--body-from-chat` / `--question-from-chat` 没取到文字 |
| `listen` | `--session ID`；`--timeout 秒`（0 = 一直等，默认） | 0 打印了事件；2 超时；4 会话进程已经没了（什么都不打印）；5 这个会话已经有一个 listen 在跑；1 不知道是哪个会话 |
| `close` | `--id ID` 或 `--mine`（二选一）；`--text 说明`；`--session ID`（配 `--mine`） | 0 已标成已处理；3 用户已经在 ClaudeDesk 里回复过（打印那条回复）；1 没有这条消息，或 `--mine` 不知道是哪个会话 |
| `inbox` | `--repo 仓库名`（默认当前仓库）；`--adopt`；`--session ID` | 0；1 `--adopt` 不知道是哪个会话 |
| `status` | `--session ID` | 0，打印一行；1 不知道是哪个会话 |
| `wait`（旧协议） | `--id ID`；或 `--source S` [`--since 时间`] 等这个来源的下一条回复；`--followups --source S` 等追问；`--timeout 秒`（0 = 一直等，默认）；`--interval 秒` | 0 打印回复或追问；2 超时；4（`--followups`）启动它的 shell 已经没了；1（`--followups`）`--since` 不是时间 |
| `responses` | `--source`、`--id`、`--since` | 0；每行一条回复 |
| `followups` | `--source`、`--since`、`--json` | 0；状态是已回答、已送达（交给了会话）或未送达 |
| `list` | `--open`（只看待决定）、`--source`、`--repo`、`--json` | 0 |

缺参数或参数冲突（比如 `close` 既没有 `--id` 也没有 `--mine`）是用法错误，和所有 `argparse` 程序一样退出码 2。

- **会话。** `post`、`listen`、`close --mine`、`inbox`、`status` 默认用 `$CLAUDE_CODE_SESSION_ID`（Claude Code 给会话里的每条命令都设了它），`--session` 可以改。`post` 还记下 `$CLAUDE_PID`（会话的 `claude.exe`）和这个进程的创建时间，ClaudeDesk 靠它们知道会话结束了没有。回复、追问按会话送，从不按 `--source`。
- **listen。** 这个会话没有 `listen` 在跑时，`post` 会在 stderr 提示一句，这时启动一个。每个会话只能跑一个 `listen`：再开第二个会立刻退出（退出码 5），stdout 什么都不打。第一件事到了以后，`listen` 等到 1.5 秒内没有新的（最多等 6 秒），一次全部打出来。会话的 `claude.exe` 没了时它不出声地退出（退出码 4），没人看的事不会被它领走。
- **--body-from-chat / --question-from-chat。** 正文是会话在这次调用之前写的最后一段连续文字（和它隔着工具调用的更早的文字不要，那多半是"我先看看…"这类过程话），所以要在同一条消息里、紧接着回答调用 `post`。原问题是用户最近一条消息，去掉 IDE 附带的上下文和系统提示。两样都从会话记录里取：`~/.claude/projects`（或 `$CLAUDE_CONFIG_DIR/projects`）下这个会话的记录，包括它的子 agent 的。取不到时 `post` 退出码 1，提示改用 `--body-file` / `--question`。
- **--reply-to** 填 `listen` 输出里那条追问的 `id`（原问题自动填好），或者填消息 id（这时用 `--question` 放追问原文）。
- **close。** `close --id` 写一条带 `"closed_by": "claude"` 的回复并打印出来。用户已经在 ClaudeDesk 里回复过时，改为打印那条回复，退出码 3：和对话里的答复核对一下。`close --mine` 把这个会话所有还在等的决定都标成已处理，打印 `{"closed": [ids]}`；这期间用户已经在 ClaudeDesk 里回复了的，先按 `listen` 的格式打出来，退出码 3。
- **status** 打印 `open=N undelivered=N listen=on|off`：这个会话的待决定、还没送到它的事、它的 `listen` 在不在。这个仓库里有已结束的会话留下没送达的回复或追问时，后面再加 `orphaned=N`。
- **inbox** 列出这个仓库里已结束的会话留下、还没送达的回复和追问，格式和 `listen` 一样，另带 `session` 的前 8 个字符；只是"已处理""跳过"的回复不列。会话的 `claude.exe` 没了、也没有 `listen` 在跑，才算结束。`--adopt` 把它们接过来：像 `listen` 一样打出来、记为已送达，以后这些消息的回复和追问也送到当前会话。
- `post` 发现 ClaudeDesk 没在运行时会自动以最小化启动它；`--no-launch`（或用了 `--data`）就不启动。没有 ClaudeDesk 在看这个数据目录时（比如用了别处的一份 `desk.py` 副本），`post` 会在 stderr 提醒：这时用户看不到消息，回复也送不回来。
- `--recommended` 是**从 1 开始**的选项序号。`--option` 写 `"label::description"`，description 可省。没有选项的决定只收文字回复。
- `--data 目录`（写在子命令前）或环境变量 `CLAUDEDESK_DATA` 可以让 `desk.py` 用别的数据目录，程序也认这两个。默认是 `desk.py` 旁边的 `data\`。
- `wait --id` 只按 id 认，已经有回复就立刻返回；它会把回复记为已送达，之后的 `listen` 不会再交一次。`wait --followups` 一次交出一条追问（最早的先交，24 小时以内的），并记为已送达。每个来源挂一个，每次回答完再挂上。

### 事件行（`listen`、`inbox`、`close --mine`）

每件事一行紧凑的 JSON，不带消息正文：

```json
{"ev":"reply","id":"20260115-093000-a1b2c3","title":"发布前先跑一轮完整回归测试吗？","choice":"先跑回归测试","choice_index":1,"text":"顺便把支付流程的用例也跑一遍"}
{"ev":"reply","id":"20260115-093200-c3d4e5","title":"先升级测试框架吗？","choice":null,"resolved":true}
{"ev":"followup","id":"20260115-095500-d4e5f6","msg":"20260115-094000-b2c3d4","kind":"answer","title":"今天的 CI 为什么变慢了","question":"今天的 CI 为什么比平时多跑了一倍时间？","text":"是新加的集成测试拖慢的吗？"}
{"ev":"followup","id":"20260115-100500-e5f6a7","msg":"20260115-093000-a1b2c3","kind":"decision","title":"发布前先跑一轮完整回归测试吗？","choice":"先跑回归测试","choice_index":1,"reply_text":"顺便把支付流程的用例也跑一遍","text":"回归测试要跑多久？"}
```

- **reply**：`id` 是那条决定，`choice` 是选项的 label（只写了文字时为 `null`），`choice_index` 从 1 开始；`text` 是你写的补充，空的时候不带。回复也可能不选选项，而是带 `"resolved": true`（标为已处理）或 `"dismissed": true`（还在等时被归档或删除）。会话自己用 `close` 写的回复不会再作为事件交回来。
- **followup**：`id` 是追问（填给 `--reply-to`），`msg` 是被追问的消息，`kind` 是那条消息的类型，`text` 是追问原文。追问的是回答时带上原问题 `question`（截到 200 字）；追问的是决定时带上用户当时的回复（`choice`、`choice_index`、`reply_text`，以及有的话 `resolved` / `dismissed` / `closed_by`）。

### 其他输出格式（`wait`、`close --id`）

`wait --id` 和 `close --id` 打印的回复，就是 `responses.jsonl` 里的那一行：

```json
{"id": "20260115-093000-a1b2c3", "ts": "2026-01-15T09:41:07.512+00:00", "choice": "先跑回归测试",
 "text": "顺便把支付流程的用例也跑一遍", "source": "my-project", "title": "发布前先跑一轮完整回归测试吗？",
 "session": "5e2d8c1a-7b4f-4c1e-9a3d-2f6b8e0c4d71", "choice_index": 1}
```

程序替你写的回复带一个标记，`choice` 为 `null`：`"resolved": true`、`"dismissed": true` 或 `"closed_by": "claude"`（`desk.py close`）。消息记了会话的，回复里也有 `session`。

`wait --followups` 打印的追问：

```json
{"id": "20260115-100500-e5f6a7", "ts": "…", "msg": "20260115-093000-a1b2c3", "kind": "decision", "source": "my-project",
 "title": "发布前先跑一轮完整回归测试吗？", "question": "", "choice": "先跑回归测试",
 "reply_text": "顺便把支付流程的用例也跑一遍", "text": "回归测试要跑多久？"}
```

## 工作原理

```text
Claude Code 会话                         data\                    ClaudeDesk（托盘程序）
  desk.py post --kind decision ...   ──►  inbox.jsonl        ──►  通知、角标、列表
                                          responses.jsonl    ◄──  你选选项、提交
                                          followups.jsonl    ◄──  你追问
  desk.py listen（后台）             ◄──  这个会话的回复和追问，一批交出
                                     ──►  deliveries.jsonl   ──►  "已送达会话 · HH:MM"
  desk.py post --reply-to <id>       ──►  inbox.jsonl        ──►  显示在你的追问下面
```

- `desk.py` 追加消息、盯着回复文件等；它从不通过网络和程序通信。
- 程序盯着这些文件（每秒看一次大小，只读新增的部分），在 Edge WebView2（pywebview）里的本地网页上显示消息，并写下你的回复。
- 每条消息都记着发它的 Claude Code 会话。你的回复和追问也带上这个会话，送回给它；它被 `desk.py inbox --adopt` 接管过的话，送给接管它的会话。
- **只送一次。** 每个把东西交给会话的命令（`listen`、`wait`、`close`、`inbox --adopt`）都在同一把锁里先查 `deliveries.jsonl`、再记一笔送达。所以新旧命令混着用，一条回复或追问也只交给会话一次；也不会丢：没送达的一直留着，等它的会话（或接管它的会话）来领。
- **攒一下。** 一个会话的第一件事到了以后，`listen` 等到 1.5 秒内没有新的（最多等 6 秒）再一起交出，接连来的几条回复只唤醒一次。
- **谁在。** 用命名管道做标记：每个数据目录一个（有程序在看），每个会话一个（它的 `listen`，同时只能有一个），旧协议还有每条在等的决定一个（`wait --id`）、每个来源一个（`wait --followups`）。进程退出时系统自动去掉它的管道。程序每 2 秒列一次管道，再查一遍每个会话的 `claude.exe` 还在不在（按进程号和进程创建时间认，进程号被重用不算），卡片上"在等 / 开着 / 已结束"那一行就是这么来的。
- 细节和边角情况（恢复的会话、子 agent、同一个仓库里的新会话、删掉的消息）见 [docs/PROTOCOL.md](docs/PROTOCOL.md)。

## 数据文件

都在 `ClaudeDesk.exe` 和 `desk.py` 旁边的 `data\` 里。

| 文件 | 谁写 | 内容 |
|---|---|---|
| `inbox.jsonl` | `desk.py post` 追加；你在界面里删除消息时程序整份重写 | 每行一条消息 |
| `responses.jsonl` | 程序（你的回复）和 `desk.py close`；只追加 | 每行一条回复 |
| `followups.jsonl` | 程序（你的追问）；只追加 | 每行一条追问。旧版还在这里写过"已送达"记录，照样认 |
| `deliveries.jsonl` | `desk.py listen`、`wait`、`close`、`inbox --adopt`；只追加，从不重写 | 什么时候把什么交给了哪个会话、会话接管、恢复的会话换了的进程号 |
| `state.json` | 程序 | 已读 / 已提醒 / 已归档 / 已删除的 id、项目归类、关掉的标签、设置、窗口位置 |
| `instance.json` | 程序 | 正在运行的那个实例的端口和 token，第二次启动时靠它把窗口交给已经在跑的那个 |
| `claudedesk.log` | 程序 | 运行日志（启动、更新、出错），满 1 MB 轮换 |
| `.lock` | 两边 | 跨进程锁文件 |

消息（`inbox.jsonl` 一行）：

```json
{"id": "20260115-093000-a1b2c3", "ts": "2026-01-15T09:30:00.123+00:00", "source": "my-project", "repo": "my-project",
 "kind": "decision", "title": "…", "body": "Markdown 正文", "priority": "normal",
 "session": "5e2d8c1a-7b4f-4c1e-9a3d-2f6b8e0c4d71", "session_pid": 12840, "session_pid_start": 134129412000000000,
 "options": [{"label": "方案 A", "description": "…"}], "recommended": 1, "allow_text": true}
```

- `kind`：`decision` / `answer` / `info`。回答可以带 `question`；回答追问的还带 `reply_to`（和 `followup_id`）。
- `repo`：发消息时所在的 git 仓库名，标签按它分。`desk.py` 不在仓库里、也没有可用的目录名时没有这个字段。
- `session`：发这条消息的 Claude Code 会话（`$CLAUDE_CODE_SESSION_ID`）；`session_pid`：它的 `claude.exe` 的进程号（`$CLAUDE_PID`）；`session_pid_start`：这个进程的创建时间（Windows FILETIME），进程号被别的进程重用时不会认错。旧版发的消息没有这几个字段，照旧走旧协议，界面上也是原来的说法。
- 回复（`responses.jsonl`）和追问（`followups.jsonl`）也带着原消息的 `session`，原消息删掉了也送得到。
- `priority`：`normal` / `high`。`source` 以 `selftest` 开头的消息默认不显示（启动参数 `--show-selftest` 可以显示）。

`deliveries.jsonl` 有四种记录：

```json
{"kind": "reply", "id": "<决定 id>", "session": "…", "via": "listen", "ts": "…", "pid": 4312}
{"kind": "followup", "id": "<追问 id>", "session": "…", "via": "listen", "ts": "…", "pid": 4312}
{"kind": "adopt", "from": "<已结束的会话>", "repo": "my-project", "session": "<新会话>", "session_pid": 9120, "session_pid_start": 134129430000000000, "ts": "…"}
{"kind": "pid", "session": "…", "session_pid": 9264, "session_pid_start": 134129448000000000, "ts": "…"}
```

`via` 是 `listen`、`wait`、`close` 或 `adopt`，`pid` 是交出去的那个 `desk.py` 进程。同一个 id 以第一条 `reply` / `followup` 记录为准。`adopt` 把一个已结束的会话在某个仓库里的消息交给新会话；`pid` 记下恢复的会话新的 `claude.exe`。

**并发与容错。** 四个 `.jsonl` 文件平时都只追加；唯一的例外是你在界面里删除消息时，程序在锁内整份重写 `inbox.jsonl`。每次追加先拿 `data\.lock` 的字节锁（`msvcrt.locking`），一次 `write` 写完整行并 `fsync`；文件末尾是别人崩溃留下的半行时，先补一个换行。实测 24 个进程同时 `post`，24 行全部完整。读的一方只读到最后一个换行，坏行跳过；文件被换掉（变小或换了文件号）就从头重读。"一条决定只能回复一次"（界面和 `close`）和"每条回复、追问只交给会话一次"（每个会交东西的 `desk.py` 命令）都在锁内检查。

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
- `desk.py post --body-from-chat` / `--question-from-chat` 会在本机读调用它的那个会话自己的记录（以及它的子 agent 的），在 `~/.claude/projects`（或 `CLAUDE_CONFIG_DIR`）下，只为把回答和原问题抄进消息。
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
docs/                     PROTOCOL.md（会话协议）和 README 截图
tests/                    pytest：数据层、命令行、会话协议、本机服务，以及用 Playwright 在 Chromium 里驱动真界面
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
