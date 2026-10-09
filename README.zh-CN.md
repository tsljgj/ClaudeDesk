# ClaudeDesk

[English](README.md) · 中文

Windows 桌面程序（不是网页），专门接收 Claude Code 会话发给你的两类内容：

- **待你决定**：取代 Claude Code 自带的 AskUserQuestion 弹窗。你在这里点选项、写补充，提交后 Claude 会话自动被唤醒并照办。
- **给你的回答**：你问 Claude 的问题，它在对话里回答的同时也发到这里，不会被一屏屏工具输出淹没。

另有少量 **通知**（info），只在"全部"里出现。

> 第三方工具，与 Anthropic 无关。

## 安装

需要 Windows 10/11 和 Python 3.10 或更新版本（只在第一次构建时用来建虚拟环境）。

```bat
git clone https://github.com/tsljgj/ClaudeDesk.git
cd ClaudeDesk
build.cmd -Install
```

`-Install` 会构建 `ClaudeDesk.exe`、在"启动"文件夹放一个开机自启快捷方式（参数 `--minimized`），然后启动程序。只想构建就去掉 `-Install`。找不到 Python 时用 `build.cmd -Python C:\path\to\python.exe` 指定。

然后让 Claude Code 用它：把 [`skill/claude-desk/SKILL.md`](skill/claude-desk/SKILL.md) 复制到 `~/.claude/skills/claude-desk/SKILL.md`，把文件开头的 `PY` / `DESK` 两个变量改成你机器上的路径。想让 Claude 每个会话都遵守，再在全局 `~/.claude/CLAUDE.md` 里加一句，例如：

```markdown
## 和用户沟通：ClaudeDesk
- 需要用户决定的事不用 AskUserQuestion，一律用 skill claude-desk 发 decision，然后后台 wait。
- 回答用户的问题时，对话里照常回答，同时用 claude-desk 发 answer（附原问题和完整回答）。
```

## 启动与日常使用

| 做什么 | 怎么做 |
|---|---|
| 启动 | 双击 `ClaudeDesk.exe`。已经在运行时再双击，只会把已有窗口切到前台 |
| 开机自启 | `build.cmd -Install` 会在"启动"文件夹放快捷方式 `ClaudeDesk.lnk`（开机后只待在托盘）。托盘菜单"开机自启"可以开 / 关 |
| 关窗口 | 点 × 只是缩到托盘，程序继续收消息 |
| 退出 | 右键托盘图标 → 退出 |
| 托盘图标 | 橙色"C"。右下红圈数字 = 未读数；右上小黄点 = 还有没回复的决定（但都看过了）；**橙 / 黄交替闪** = 有没看过的决定或高优先级消息 |

新消息到达时：

- 弹 Windows 通知（决定类是黄色感叹号，回答类是蓝色 i）。点通知直接打开那一条。
- 任务栏按钮闪烁。决定类和高优先级的**一直闪到你切到窗口**，托盘图标也一直闪到你看过那一条；普通消息闪 3 次后保持高亮。
- 窗口藏在托盘时，会以"最小化、不抢焦点"的方式放回任务栏，好让任务栏能闪。不会打断你正在打字的窗口。

窗口里：

- 左边三个筛选：**待你决定**（没回复的置顶、橙色高亮）、**给你的回答**、**全部**。按钮上的数字分别是：未回复的决定数、未读回答数、全部未读数。
- 搜索框（Ctrl+F）按标题、正文、来源、原问题、选项搜，空格分隔多个词表示"都要包含"。
- 点开一条就算已读；右上角按钮或右键可以"标为未读"；左下"全部标为已读"。
- 决定：点一个选项卡片（标"推荐"的是 Claude 推荐的），需要的话写补充，点"提交"（或 Ctrl+Enter）。提交后显示"已回复"和你的回复，**同一条不能再提交**。
- 回答：正文上方的灰框是你当时问的原问题。

> Windows 11 默认把新托盘图标收进"^"里。想让它常驻显示：设置 → 个性化 → 任务栏 → 其他系统托盘图标 → 打开 ClaudeDesk。

## 给 Claude 用的命令行：`desk.py`

只用标准库，Python 3.10 或更新版本：

```bash
PY=python                          # 任意 Python 3.10+
DESK=C:/path/to/ClaudeDesk/desk.py

# 发一条决定（正文放在 UTF-8 的 Markdown 文件里）；打印新消息 id
"$PY" "$DESK" post --kind decision --source my-project --title "要不要先复核再冻结？" \
    --body-file plan.md --option "直接冻结::2 小时" --option "先复核::约 6 小时" --option "暂停" \
    --recommended 2 --allow-text [--priority high]

# 阻塞到你回复（Claude 用后台命令跑它；你一提交它就退出，会话被唤醒）
"$PY" "$DESK" wait --source my-project --id <id> [--timeout 秒]   # 回复 → 退出码 0；超时 → 2

# 发一条回答：原问题 + 完整回答
"$PY" "$DESK" post --kind answer --source my-project --title "两个配置目录会同步吗" \
    --question "我在 D 盘改了 skill，C 盘会不会跟着变？" --body-file answer.md

# 其他
"$PY" "$DESK" post --kind info --source X --title "回测跑完了" --body "结果在 ..."   # --body - 表示从 stdin 读
"$PY" "$DESK" responses --source X [--since 2026-10-03T18:00:00-04:00]
"$PY" "$DESK" list [--open] [--source X] [--json]
"$PY" "$DESK" close --id <id> --text "用户在对话里选了 B"   # 你在对话里答了，把这条决定标成已处理
```

- `post` 发现 ClaudeDesk 没在运行时会自动以 `--minimized` 启动它；启动后对"程序关着时到的、还没提醒过的消息"补一次通知。`--no-launch` 关掉自动启动。
- `wait --id`：那一条已经有回复就立刻返回；只给 `--source` 时，等这个来源在"开始等待之后"（或 `--since` 之后）的新回复。
- `--recommended` 是**从 1 开始**的选项序号。`--option` 写 `"label::description"`，description 可省。
- 没有选项的 decision 自动允许文字回复。
- 数据目录默认 `desk.py` 旁边的 `data/`；`--data <目录>`（写在子命令前）或环境变量 `CLAUDEDESK_DATA` 可以改。程序也认 `--data` 与同一个环境变量。

Claude 会话的用法规范见 [`skill/claude-desk/SKILL.md`](skill/claude-desk/SKILL.md)。

## 数据格式

都在 `data\`（`ClaudeDesk.exe` / `desk.py` 旁边）：

| 文件 | 谁写 | 内容 |
|---|---|---|
| `inbox.jsonl` | Claude（`desk.py post`），只追加 | 每行一条消息 |
| `responses.jsonl` | 程序（你提交时），只追加 | 每行一条回复 |
| `state.json` | 程序 | 已读 / 已提醒的 id、窗口位置、当前筛选 |
| `.lock` | 两边 | 跨进程锁文件（空文件，别删也无妨） |

消息（`inbox.jsonl` 一行）：

```json
{"id": "20261003-181209-abb336", "ts": "2026-10-03T18:12:09.123-04:00", "source": "my-project",
 "kind": "decision", "title": "…", "body": "Markdown 正文", "priority": "normal",
 "options": [{"label": "方案 A", "description": "…"}], "recommended": 1, "allow_text": true}
```

- `kind`：`decision` / `answer` / `info`。answer 可带 `"question"`（你的原问题）。
- `priority`：`normal` / `high`。
- `source` 以 `selftest` 开头的消息在界面里默认隐藏（留给自动测试用；启动参数 `--show-selftest` 可显示）。

回复（`responses.jsonl` 一行）：

```json
{"id": "<对应消息 id>", "ts": "…", "choice": "方案 A", "text": "你写的补充", "source": "<消息的 source>",
 "title": "<消息标题>", "choice_index": 1}
```

`choice` 是选项的 label（只写了文字时为 `null`）；`title`、`choice_index` 是附带的方便字段。`desk.py close` 写的回复带 `"closed_by": "claude"`。

并发与容错：

- 两个文件都只追加。每次追加先拿 `data/.lock` 的字节锁（`msvcrt.locking`），一次 `write` 写完整行并 `fsync`；如果文件末尾是别人崩溃留下的半行，先补换行。实测 24 个进程同时 `post`，24 行全部完整。
- 读的一方只消费到最后一个换行，半行留到下一轮；坏行跳过。程序每秒看一次文件大小，有新内容才读增量，不需要重启。文件被换掉（变小 / 换了文件号）就整份重读。
- "不能重复提交"在锁内检查：同一个 id 已有回复，第二次写入会被拒绝（界面和 `close` 都走这条）。

## 重新构建

```bat
build.cmd            :: 只构建
build.cmd -Install   :: 构建 + 放开机自启快捷方式 + 启动
```

`build.ps1` 会：没有 `.venv` 时建一个（优先 `py -3`，其次 PATH 上的 `python`，或用 `-Python` 指定）并装 `PySide6-Essentials`、`pyinstaller`；生成图标；用 PyInstaller 打包（onedir）；**先结束正在运行的 ClaudeDesk**，再把 `ClaudeDesk.exe` 和 `_internal\` 复制到根目录。

目录：

```text
ClaudeDesk.exe   程序（构建产物，依赖旁边的 _internal\，两者要放在一起）
_internal\       Python 运行时 + Qt（构建产物）
desk.py          命令行工具（也被程序当库用）
src\             claudedesk.py（界面）、store.py（数据层）、icons.py（图标）
packaging\       version.txt（exe 的版本信息）
skill\           给 Claude Code 用的 skill
build\           构建中间文件（不进仓库）
data\            收件箱（不进仓库）
.venv\           构建用的独立虚拟环境（不进仓库）
```

从源码直接跑：`.venv\Scripts\python.exe src\claudedesk.py [--data 测试目录]`。用别的数据目录时命名管道名也不同，可以和正式实例同时开着。

## 测试入口（隐藏）

`ClaudeDesk.exe --selftest '<JSON 命令>' --out 结果.json` 把命令发给正在运行的实例，结果写进文件：

| op | 作用 |
|---|---|
| `state` | 未读 / 待决定 / 是否在闪 / 窗口状态 / 当前列表 |
| `screenshot` | `{"path": png, "id"?: 选中哪条, "filter"?: 0/1/2, "tray_path"?: 托盘图标 png}`，默认不抢焦点 |
| `reply` | `{"id", "choice": label 或从 1 开始的序号, "text"}`：走界面路径（选中 → 点卡片 → 填字 → 点"提交"） |
| `submit_direct` | 直接调写回复的函数（用来验证重复提交被拒） |
| `select` / `filter` / `hide` / `quit` | 选中一条 / 切筛选 / 关到托盘 / 退出 |

## 技术选型

Python 3.10 + PySide6（只装 `PySide6-Essentials`）+ PyInstaller **onedir**。

- Markdown 用 Qt 自带的 md4c（GitHub 方言）解析，再补样式：表格边框 / 表头底色、代码块底色与等宽字体（Cascadia Mono / Consolas，中文回落微软雅黑）、行内代码、引用块、1.45 倍行距。
- 选 onedir 不选单文件：单文件 exe 每次启动要把约 70 MB 解压到临时目录（启动慢好几秒，重复启动"只激活已有窗口"也要等这么久），而且常驻时是两个进程；onedir 只有一个进程，内存更小。代价是 exe 旁边多一个 `_internal\` 目录。
- 单实例和测试通道：Qt 本地套接字（命名管道 `ClaudeDesk-<用户名>`）。
- 界面固定浅色主题（Fusion + 显式调色板），不受系统深色模式影响。

## 内存（实测，3840×2160、225% 缩放）

| 状态 | 工作集 | 私有内存 |
|---|---:|---:|
| 开机自启、只在托盘 | 约 24 MB | 约 28 MB |
| 窗口打开 | 约 55 MB | 约 44 MB |
| 关回托盘后（程序会主动裁剪工作集） | 约 4 MB | 约 44 MB |

## 已知问题

- 界面只有中文。
- Windows 通知必须用系统图标（黄色感叹号 / 蓝色 i）。实测 Qt 在 Windows 上 `showMessage` 传自定义图标时通知根本不弹，所以没用 ClaudeDesk 自己的图标。
- 开着"请勿打扰 / 专注"时，Windows 只把通知收进通知中心、不弹出；任务栏闪烁和托盘闪烁不受影响。
- 托盘图标在 16 px 下显示两位数未读时字很小；超过 99 显示"99+"。
- 只认 `data\` 里的文件。手工编辑 `inbox.jsonl` 时请只追加完整行。

## 许可

[MIT](LICENSE)
