# ClaudeDesk

[English](README.md) · 中文

Windows 托盘程序，专门接收 Claude Code 会话发给你的东西：

- **决定**：取代 Claude Code 自带的 AskUserQuestion。你在这里选一个选项、写两句补充，提交后 Claude 会话自动被唤醒并照办。
- **回答**：你问 Claude 的问题，它在对话里回答的同时也发到这里，不会被一屏屏工具输出淹没。
- **通知**：少量"长任务跑完了 / 出错了"。

正文是完整的 Markdown：表格、代码高亮、LaTeX 公式（`$…$`、`$$…$$`、`\(…\)`、`\[…\]`）都能正常显示。每条消息可以一键复制（Markdown / 富文本 / 纯文本）或导出 PDF，看完可以归档或删除。

![ClaudeDesk](docs/screenshot-light.png)

> 第三方工具，与 Anthropic 无关。

## 安装

需要 Windows 10/11（自带 Edge WebView2）。

1. 从 [Releases](https://github.com/tsljgj/ClaudeDesk/releases/latest) 下载 `ClaudeDesk.exe`，放进一个你有写权限的文件夹，例如 `%LOCALAPPDATA%\Programs\ClaudeDesk\`（不要放 `Program Files`，否则没法自动更新）。
2. 双击运行。它会在自己旁边放好 `desk.py`（给 Claude 用的命令行）和 `data\`（收件箱）。
3. 让 Claude Code 用它：把 [`skill/claude-desk/SKILL.md`](skill/claude-desk/SKILL.md) 复制到 `~/.claude/skills/claude-desk/SKILL.md`，把开头的 `DESK` 改成上面那个文件夹里的 `desk.py`，`PY` 改成你的 Python（3.10+）。想让每个会话都遵守，再在 `~/.claude/CLAUDE.md` 里加一句：

```markdown
## 和用户沟通：ClaudeDesk
- 需要用户决定的事不用 AskUserQuestion，一律用 skill claude-desk 发 decision，然后后台 wait。
- 回答用户的问题时，对话里照常回答，同时用 claude-desk 发 answer（附原问题和完整回答）。
```

从 1.x 升级：把下载的 `ClaudeDesk.exe` 覆盖进原来的仓库目录即可（先在托盘里退出旧版本），`data\` 原样沿用；旧的 `_internal\` 文件夹可以删掉。

### 自动更新

和 [agent-management](https://github.com/tsljgj/agent-management) 一样：CI 每次在 `main` 上构建通过，就发布一个 `build-<N>` release（附 `ClaudeDesk.exe` 和 `.sha256`）。程序启动约 45 秒后检查一次，之后每 6 小时一次；发现新版本就下载、校验 SHA-256，然后把自己改名为 `ClaudeDesk.exe.old`（Windows 允许给运行中的 exe 改名），新文件放到原位置并启动，旧进程退出。

- 窗口开着时不会打断你：等你把窗口关回托盘再装；左下角会出现"更新到 build N"，点一下立刻更新。
- 设置（左上角的滑块图标）或托盘菜单里可以关掉"自动更新"，也可以手动"检查更新"。
- 更新时 exe 会顺手把旁边的 `desk.py` 换成同版本，命令行和程序永远一致。
- 自己从源码 `build.cmd` 出来的 exe 是 build 0，不会自动更新。

## 日常使用

| 做什么 | 怎么做 |
|---|---|
| 打开 | 双击 `ClaudeDesk.exe` 或点托盘图标。已经在运行时再双击只会把窗口切到前台 |
| 开机自启 | 设置 / 托盘菜单里的"开机自启"（写在 `HKCU\...\Run`，开机后只待在托盘） |
| 关窗口 | 点 × 只是缩到托盘，程序继续收消息；右键托盘图标 → 退出 |
| 托盘图标 | 橙色方块里一个 "C•"。右下角数字 = 未读数；右上角白点 = 还有没回复的决定；**橙 / 黑交替闪** = 有没看过的决定或紧急消息 |

新消息到达时弹 Windows 通知（点通知直接打开那一条），任务栏按钮闪烁：决定类和紧急的一直闪到你切过来，普通的闪 3 次。

窗口里：

- 列表上方四个视图：**全部**（默认，每次打开都在这里）、**决定**（橙色数字 = 没回复的）、**回答**、**归档**。仓库标签按名字排，不会因为来了新消息就换位置；点按钮、读消息、勾选时，标签和列表都不会挪动。
- **按仓库分开（窗口最上面的标签页）**：标签就是仓库名（osworld、cn-equity-research…）。点一个只看它，再点一次取消（都不选 = 看全部，右边的 × 也能一下取消，或按 `Esc`）；`Ctrl` / `Shift` + 点可以同时选几个；`[` / `]` 切换。选了多个或都不选时，列表按仓库分组。视图上的数字、"全部标为已读"、"归档所有已处理的"都只算选中的仓库。
- 仓库名怎么来的：`desk.py post` 发消息时记下当前目录所在的 git 仓库（origin 地址里的仓库名；worktree 认得出主仓库；不在 git 里就用当前目录名；`--repo` 可以手动指定）。
- 旧消息（更新前发的，没有仓库信息）：程序会读 Claude Code 自己的会话记录（`~/.claude/projects`，以及 `CLAUDE_CONFIG_DIR` 指的目录），找出你在哪些仓库里用过 Claude，再把旧消息的来源对上去（`osworld`、`osworld/eval`、`osworld-runner` 都算 osworld）。实在对不上的放进最后的"未归类"，在分组标题旁点"归到…"（或右键仓库标签）就能归到某个仓库，设置里可以撤销。
- 列表左边的橙点 = 需要你处理，灰点 = 未读；第二行写着状态（"待决定"、"✓ 你选的选项"、"✓ 已解决"、"已跳过"）。当前打开的那条左边有一道橙色竖条。
- **鼠标移到一条上**，右边会出现它自己的操作：标为已读 / 未读、标为已解决（只对待决定的）、归档、删除；左边出现勾选框。不悬停时都不显示。
- 决定：按 `1`–`9` 或点选项，需要的话写补充，`Ctrl+Enter` 提交。提交后同一条不能再提交。
- 阅读区右上角只有复制（旁边的小箭头可选"富文本 / 纯文本"）和导出 PDF。代码块悬停时也有自己的复制按钮。
- **标为已解决**（`R`，或决定面板里的"标为已解决"）：不选选项，直接告诉等待中的会话"已经处理好了"（回复里带 `"resolved": true`），同时标为已读。
- **归档**（`E`）：收起来，在"归档"里还能找到，可以撤销 / 移出归档。**删除**（`Delete`）：从收件箱文件里真正去掉，不能恢复。归档或删除一条还没回复的决定时，会告诉等待中的会话"用户跳过了"。
- **多选 / 批量**：点勾选框（`Shift` 连选），或 `Ctrl` + 点击、`X` 勾当前这条、`Ctrl+A` 全选。勾上以后列表上方出现批量栏：全选、已读、已解决、归档、删除。也可以右键。列表右上角"⋯"里有"全部标为已读"和"归档所有已处理的"。
- 搜索：`/` 或 `Ctrl+F`，按标题、正文、来源、原问题、选项搜，空格分隔多个词。
- 设置：浅色 / 深色 / 跟随系统，四种强调色，正文字体（无衬线：Inter + 思源黑体；衬线：Source Serif + 思源宋体），字号，列表密度。
- 按 `?` 看全部快捷键。

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
| `state.json` | 程序 | 已读 / 已提醒 / 已归档 / 已删除的 id、项目归类、界面设置、窗口位置 |
| `claudedesk.log` | 程序 | 运行日志（启动、更新、出错） |
| `.lock` | 两边 | 跨进程锁文件（空文件，别删也无妨） |

消息（`inbox.jsonl` 一行）：

```json
{"id": "20261003-181209-abb336", "ts": "2026-10-03T18:12:09.123-04:00", "source": "my-project", "repo": "my-project",
 "kind": "decision", "title": "…", "body": "Markdown 正文", "priority": "normal",
 "options": [{"label": "方案 A", "description": "…"}], "recommended": 1, "allow_text": true}
```

- `kind`：`decision` / `answer` / `info`。answer 可带 `"question"`（你的原问题）。
- `repo`：发消息时所在的 git 仓库名（`desk.py` 自动识别，`--repo` 可覆盖；不在仓库里时没有这个字段）。界面按它分标签。
- `priority`：`normal` / `high`。
- `source` 以 `selftest` 开头的消息在界面里默认隐藏（留给自动测试用；启动参数 `--show-selftest` 可显示）。

回复（`responses.jsonl` 一行）：

```json
{"id": "<对应消息 id>", "ts": "…", "choice": "方案 A", "text": "你写的补充", "source": "<消息的 source>",
 "title": "<消息标题>", "choice_index": 1}
```

`choice` 是选项的 label（只写了文字时为 `null`）；`title`、`choice_index` 是附带的方便字段。`desk.py close` 写的回复带 `"closed_by": "claude"`。你在界面里把一条还没回复的决定**标为已解决**时，程序替你写一条 `"resolved": true`、`choice` 为 `null` 的回复。你在界面里归档或删除一条**还没回复的决定**时，程序会先替你写一条 `"dismissed": true`、`choice` 为 `null` 的回复，正在 `wait` 的会话会收到它并继续往下走，不会一直卡着。

并发与容错：

- 两个文件平时都只追加（唯一的例外：你在界面里**删除**消息时，程序在锁内整份重写 `inbox.jsonl`，去掉被删的行）。每次追加先拿 `data/.lock` 的字节锁（`msvcrt.locking`），一次 `write` 写完整行并 `fsync`；如果文件末尾是别人崩溃留下的半行，先补换行。实测 24 个进程同时 `post`，24 行全部完整。
- 读的一方只消费到最后一个换行，半行留到下一轮；坏行跳过。程序每秒看一次文件大小，有新内容才读增量，不需要重启。文件被换掉（变小 / 换了文件号）就整份重读。
- "不能重复提交"在锁内检查：同一个 id 已有回复，第二次写入会被拒绝（界面和 `close` 都走这条）。

## 从源码运行 / 构建

```bat
pip install -r requirements.txt
cd src
python -m claudedesk                 :: 托盘 + 窗口
python -m claudedesk --serve         :: 只起本机服务，用浏览器打开（任何系统都能用来调界面）
cd ..
build.cmd [-Install]                 :: 打包成单文件 ClaudeDesk.exe（build 0，不自动更新）
```

目录：

```text
desk.py                 命令行工具（只用标准库；也被程序当库用）
src/claudedesk/         app.py（托盘 / 窗口 / 自动更新）、store.py（数据层）、server.py（本机 HTTP 服务）、
                        update.py、icon.py、winapi.py、assets/（界面：index.html、app.css、app.js、markdown.js）
src/claudedesk/assets/vendor/   markdown-it、KaTeX、highlight.js、DOMPurify 和字体（离线可用；scripts/vendor.py 生成）
scripts/                PyInstaller 入口、vendor.py
tests/                  数据层测试 + 用真浏览器（Playwright）驱动界面的测试
skill/                  给 Claude Code 用的 skill
.github/workflows/      CI：测试 → 打包 → 打包后自检 → 真实托盘程序端到端（desk.py 发消息、回复、自更新）→ 发布 release
```

## 技术选型

- **界面**是本地网页，跑在 Edge WebView2 里（[pywebview](https://pywebview.flowrl.com/)），托盘用 [pystray](https://github.com/moses-palmer/pystray)，和 agent-management 同一套。换掉 1.x 的 Qt 控件是因为 Qt 的富文本不支持公式，表格解析也比较挑。
- Markdown：markdown-it（GitHub 风格表格、任务列表、自动链接）+ DOMPurify 清洗 + KaTeX 渲染公式 + highlight.js。表格里公式和行内代码中的 `|` 不会把单元格切开；`$5 和 $10` 这种价格不会被当成公式。
- 本机 HTTP 服务只绑 127.0.0.1，检查 Host 头，API 要带每次启动随机生成的 token。
- 导出 PDF 用 WebView2 自带的 PrintToPdf（打印样式只印文章本身）；不行时退回系统打印对话框（选"另存为 PDF"）。
- 单文件 exe，自动更新时整个替换。

## 许可

[MIT](LICENSE)。第三方前端库和字体的许可见 `src/claudedesk/assets/vendor/LICENSES.txt`（均为 MIT / BSD / Apache / OFL）。
