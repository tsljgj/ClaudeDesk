---
name: claude-desk
description: 通过桌面程序 ClaudeDesk 和用户沟通。需要用户决定时使用（一律发 decision 并后台 wait，不用 AskUserQuestion）；回答用户问题时使用（对话里回答之外，再把原问题和完整回答发成 answer，免得被工具输出淹没）；少量进展通知用 info。发过消息就后台挂一个 wait --followups 接用户的追问。
---

# ClaudeDesk：给用户发"待决定 / 回答 / 通知"

用途：需要用户决策时，不用 Claude Code 自带的弹出问题，而是发到桌面程序 ClaudeDesk 提醒用户；用户问的问题，回答除了写在对话里，也发到 ClaudeDesk，免得被指令执行的输出淹没。

程序：`<ClaudeDesk 目录>\ClaudeDesk.exe`（托盘常驻）。说明：https://github.com/tsljgj/ClaudeDesk#readme
命令行（只用标准库）。**安装时把下面两个变量改成你机器上的路径：**

```bash
PY=python                              # 任意 Python 3.10+ 的完整路径
DESK=C:/path/to/ClaudeDesk/desk.py
```

`post` 发现程序没开会自动启动它，不用自己检查。如果 `post` 在 stderr 打出"注意：没有 ClaudeDesk 在看这个数据目录…"，说明这条消息用户看不到（`wait` 也等不到回复）：多半是 `DESK` 指向了别处的 desk.py 副本，要改成 ClaudeDesk 安装目录里的那个，再重发。

## 规则

1. **需要用户决定的事：一律 `post --kind decision`，然后后台 `wait`。不要用 AskUserQuestion。**
2. **回答用户的问题：对话里照常回答，同时 `post --kind answer`**，`--question` 放用户原问题（原文），正文放完整回答。用户下达的是任务而不是提问时不用发；"好的 / 收到"这类也不用发。发完确认挂着追问监听（见"追问"）。
3. **进展通知 `--kind info`：少用。** 只用于用户明确在等的事：长任务完成、跑挂了需要人管、机器或环境出了问题。
4. **`--source` 用项目名**（仓库名，例如 `my-project`）；同一项目里有多条并行会话时加后缀（`my-project/data`）。同一会话里保持不变。ClaudeDesk 按**仓库**分标签：`post` 会自动记下当前目录所在 git 仓库的名字（origin 地址里的仓库名），所以要在项目目录里运行 `desk.py`（Bash 默认就在）。不在 git 仓库里时用当前目录名；要指定就加 `--repo <仓库名>`。
5. **子 agent 不要发 decision 等回复，也不挂追问监听。** 子 agent 不适合长时间挂起等待；把要决定的事交回主会话，由主会话发。

## 发决定（decision）

1. 用 Write 把正文写进草稿目录（scratchpad）里的 `.md` 文件。正文要能**单独看懂**：用户可能几小时后才看，而且看不到对话里的工具输出。写清楚：
   - 背景：现在在做什么、卡在哪；
   - 各选项的后果、代价（时间、成本、风险）；
   - 你推荐哪个、为什么。
   支持 Markdown 标题、粗体、列表、表格、代码块。
2. 发出去，记下打印出来的 id：

```bash
"$PY" "$DESK" post --kind decision --source my-project \
  --title "发布前先跑一轮完整回归测试吗？" \
  --body-file "<scratchpad>/decision.md" \
  --option "先跑回归测试::约 25 分钟，最稳妥" \
  --option "直接发布::CI 已经跑过单元测试" \
  --option "暂停::先做别的任务" \
  --recommended 1
```

   - 标题写成一个问题，30 字以内。
   - 选项写成 `"label::description"`：label 短（10 字左右），description 一行。`--recommended` 从 1 开始。
   - 每条决定都带回复框，用户随时能写补充条件（`--allow-text` 已经不需要，加了也没关系）。没有选项的 decision 只收文字。
   - 卡住、不决定就没法往下做的，加 `--priority high`：图标和任务栏会一直闪到用户看过为止。
3. **用后台命令跑 `wait`**（Bash 的 `run_in_background: true`），不设超时：

```bash
"$PY" "$DESK" wait --id <id>
```

   带 `--id` 时只按 id 认回复（`--source` 不用加，加了也不影响）。

4. 在对话里只说一句"已发到 ClaudeDesk，等你决定：<标题>"，然后继续做不依赖这个决定的事；没有别的可做就结束这一轮。
5. 用户一提交，`wait` 退出（退出码 0），会话被唤醒。输出是一行 JSON：

```json
{"id": "…", "ts": "…", "choice": "先跑回归测试", "text": "顺便把支付流程的用例也跑一遍", "source": "my-project", "title": "…", "choice_index": 1}
```

   - 按 `choice` 执行，`text` 里的补充条件同样要遵守。`choice_index` 是用户点的第几个选项（从 1 开始）；选项名字有重复时以它为准。
   - `text` 和 `choice` 冲突、或者只写了文字时，以文字为准；看不懂就再发一条 decision 问清楚，不要猜。
   - 回复里带 `"resolved": true`（`choice` 为 `null`）表示用户在 ClaudeDesk 里把这条**标为已处理**：事情已经处理好了（可能是用户自己做了，或者不再需要）。不要按任何选项执行；在对话里说一句"这条决定用户标为已处理了"，继续做不依赖它的事。
   - 回复里带 `"dismissed": true`（`choice` 为 `null`）表示用户在 ClaudeDesk 里把这条归档 / 删除了、没有作出选择：不要按任何选项执行，在对话里说一句"这条决定被跳过了"，继续做不依赖它的事，或者结束这一轮等用户在对话里说。
   - 执行前在对话里用一句话复述"用户选了 X（补充：…），现在开始做"。
   - 然后确认挂着追问监听（见"追问"）：用户可能对处理过的决定再追问。
6. 特殊情况：
   - **用户直接在对话里答了**：停掉后台 `wait`，先 `"$PY" "$DESK" close --id <id> --text "用户在对话里选了 …"`，让 ClaudeDesk 里那条不再显示"待决定"，再按对话里的答复执行。
     `close` 退出码 3 表示**用户已经在 ClaudeDesk 里回复过了**：stdout 那行 JSON 就是那条回复（也可以 `responses --id <id>` 查）。和对话里的答复一致就照做；不一致（或者是 resolved / dismissed）就在对话里说明两边的差别，问清楚以哪个为准，不要默默只按其中一个做。
   - **`wait` 被中断或会话重启了**：`"$PY" "$DESK" responses --id <id>` 查有没有回复，没有就重新挂 `wait`。
   - **检查还有哪些没回复**：`"$PY" "$DESK" list --open --source <名>`。

## 发回答（answer）

```bash
"$PY" "$DESK" post --kind answer --source my-project \
  --title "今天的 CI 为什么变慢了" \
  --question "今天的 CI 为什么比平时多跑了一倍时间？" \
  --body-file "<scratchpad>/answer.md"
```

- `--question` 放用户原话；很长就用 `--question-file`。
- 正文就是完整回答，和对话里的回答一致或更完整。先给结论，再给依据，数字和路径写全。
- 一轮里用户问了几个问题，合成一条发，标题概括。

## 追问（follow-up）

用户可以在 ClaudeDesk 里对你发的任何一条消息追问：answer、info、已经回复过的 decision（选了选项、写了回复、标为已处理、跳过、`close` 掉的都算；还在等回复的 decision 不能追问）。会话挂着监听才收得到；挂着时 ClaudeDesk 告诉用户"会话在线"，没挂时提示用户把追问复制到对话里。一个监听管你这个来源的所有消息。

1. **发完 answer / info、或者 decision 收到回复之后，确认你这个来源有一个、且只有一个后台监听**（Bash 的 `run_in_background: true`，不设超时）。你的上一个还在跑就不要再开：

```bash
"$PY" "$DESK" wait --followups --source my-project
```

2. 用户一发追问，`wait` 退出（退出码 0），输出一行 JSON：`msg` 是被追问的消息 id，`kind` 是它的类型，`question` 是它的原问题，`text` 是追问原文。追问的是 decision 时另有用户当时的回复：`choice`、`reply_text`，标为已处理 / 跳过 / 在对话里处理的还带 `resolved` / `dismissed` / `closed_by`：

```json
{"id": "<追问 id>", "ts": "…", "msg": "<原消息 id>", "kind": "decision", "source": "my-project", "title": "原消息的标题", "question": "", "choice": "先跑回归测试", "reply_text": "顺便把支付流程的用例也跑一遍", "text": "回归测试要跑多久？"}
```

3. 醒来后：
   1. 在对话里回答这条追问；
   2. 把回答发回 ClaudeDesk，`--reply-to` 填那行 JSON 里的 `id`（自动记下原消息，`--question` 自动填追问原文，命令行里不用再引用用户的话）：

```bash
"$PY" "$DESK" post --kind answer --source my-project --reply-to <追问 id> \
  --title "大约 25 分钟" --body-file "<scratchpad>/followup.md"
```

   3. 重新挂上监听（第 1 步）。你回答期间用户又发的追问不会丢：重新挂上时立刻拿到。

- 一次只交出一条；同一条只会交给一个监听。
- 用户把带「ClaudeDesk 追问 · 原消息 id：…」的文字贴进对话：照样在对话里答，再用 `--reply-to <那个 id> --question '<追问原文>'` 发回去。
- 查追问和状态（已回答 / 已送达 / 未送达）：`"$PY" "$DESK" followups --source my-project`。
- 退出码：2 = 超时（只在加了 `--timeout` 时）；4 = 启动它的 shell 已经没了，不用处理。

## 发通知（info）

```bash
"$PY" "$DESK" post --kind info --source my-project --title "全量测试跑完了" --body "结果：… 报告在 …"
```

短正文可以直接用 `--body`。长正文用 `--body-file`，或者 `--body -` 从 stdin 读。

## 注意

- 正文一律用文件或 stdin 传，不要把多行 Markdown 塞进命令行参数。命令行只放标题、选项这类短文本，用单引号包起来。
- 不要往消息里写凭据、token。
- 数据在 `<ClaudeDesk 目录>\data\`：`responses.jsonl`、`followups.jsonl` 只追加；`inbox.jsonl` 平时只追加，用户在 ClaudeDesk 里删除消息时会整份重写（去掉删掉的）。都不要手改；要标"已处理"用 `close`。
- 程序没响应时先看托盘里有没有图标；日志在 `<ClaudeDesk 目录>\data\claudedesk.log`。
