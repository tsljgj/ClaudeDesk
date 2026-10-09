---
name: claude-desk
description: 通过桌面程序 ClaudeDesk 和用户沟通。需要用户决定时使用（一律发 decision 并后台 wait，不用 AskUserQuestion）；回答用户问题时使用（对话里回答之外，再把原问题和完整回答发成 answer，免得被工具输出淹没）；少量进展通知用 info。
---

# ClaudeDesk：给用户发"待决定 / 回答 / 通知"

用途：需要用户决策时，不用 Claude Code 自带的弹出问题，而是发到桌面程序 ClaudeDesk 提醒用户；用户问的问题，回答除了写在对话里，也发到 ClaudeDesk，免得被指令执行的输出淹没。

程序：`<ClaudeDesk 目录>\ClaudeDesk.exe`（托盘常驻）。说明：同目录的 `README.md`。
命令行（只用标准库）。**安装时把下面两个变量改成你机器上的路径：**

```bash
PY=python                              # 任意 Python 3.10+ 的完整路径
DESK=C:/path/to/ClaudeDesk/desk.py
```

`post` 发现程序没开会自动启动它，不用自己检查。

## 规则

1. **需要用户决定的事：一律 `post --kind decision`，然后后台 `wait`。不要用 AskUserQuestion。**
2. **回答用户的问题：对话里照常回答，同时 `post --kind answer`**，`--question` 放用户原问题（原文），正文放完整回答。用户下达的是任务而不是提问时不用发；"好的 / 收到"这类也不用发。
3. **进展通知 `--kind info`：少用。** 只用于用户明确在等的事：长任务完成、跑挂了需要人管、额度或机器出问题。
4. **`--source` 用项目名**（仓库名，例如 `my-project`）；同一项目里有多条并行会话时加后缀（`my-project/data`）。同一会话里保持不变。ClaudeDesk 按**仓库**分标签：`post` 会自动记下当前目录所在 git 仓库的名字（origin 地址里的仓库名），所以要在项目目录里运行 `desk.py`（Bash 默认就在）。不在 git 仓库里时可以加 `--repo <仓库名>` 指定。
5. **子 agent 不要发 decision 等回复。** 子 agent 等不起（它的 prompt cache 很快过期）；把要决定的事交回主会话，由主会话发。

## 发决定（decision）

1. 用 Write 把正文写进草稿目录（scratchpad）里的 `.md` 文件。正文要能**单独看懂**：用户可能几小时后才看，而且看不到对话里的工具输出。写清楚：
   - 背景：现在在做什么、卡在哪；
   - 各选项的后果、代价（时间、额度、风险）；
   - 你推荐哪个、为什么。
   支持 Markdown 标题、粗体、列表、表格、代码块。
2. 发出去，记下打印出来的 id：

```bash
"$PY" "$DESK" post --kind decision --source my-project \
  --title "第 6 轮之后：先复核还是直接冻结？" \
  --body-file "<scratchpad>/decision.md" \
  --option "先复核::再跑一轮复核然后冻结，约 6 小时" \
  --option "直接冻结::读一次验证集，2 小时" \
  --option "暂停::先做别的任务" \
  --recommended 1 --allow-text
```

   - 标题写成一个问题，30 字以内。
   - 选项写成 `"label::description"`：label 短（10 字左右），description 一行。`--recommended` 从 1 开始。
   - 默认加 `--allow-text`，让用户能补充条件。没有选项的 decision 自动只收文字。
   - 卡住、不决定就没法往下做的，加 `--priority high`：图标和任务栏会一直闪到用户看过为止。
3. **用后台命令跑 `wait`**（Bash 的 `run_in_background: true`），不设超时：

```bash
"$PY" "$DESK" wait --source my-project --id <id>
```

4. 在对话里只说一句"已发到 ClaudeDesk，等你决定：<标题>"，然后继续做不依赖这个决定的事；没有别的可做就结束这一轮。
5. 用户一提交，`wait` 退出（退出码 0），会话被唤醒。输出是一行 JSON：

```json
{"id": "…", "ts": "…", "choice": "先复核", "text": "复核只看第 4 项", "source": "my-project", "title": "…", "choice_index": 1}
```

   - 按 `choice` 执行，`text` 里的补充条件同样要遵守。
   - `text` 和 `choice` 冲突、或者只写了文字时，以文字为准；看不懂就再发一条 decision 问清楚，不要猜。
   - 回复里带 `"resolved": true`（`choice` 为 `null`）表示用户在 ClaudeDesk 里把这条**标为已解决**：事情已经处理好了（可能是用户自己做了，或者不再需要）。不要按任何选项执行；在对话里说一句"这条决定用户标为已解决了"，继续做不依赖它的事。
   - 回复里带 `"dismissed": true`（`choice` 为 `null`）表示用户在 ClaudeDesk 里把这条归档 / 删除了、没有作出选择：不要按任何选项执行，在对话里说一句"这条决定被跳过了"，继续做不依赖它的事，或者结束这一轮等用户在对话里说。
   - 执行前在对话里用一句话复述"用户选了 X（补充：…），现在开始做"。
6. 特殊情况：
   - **用户直接在对话里答了**：按对话里的答复执行，停掉后台 `wait`，再 `"$PY" "$DESK" close --id <id> --text "用户在对话里选了 …"`，让 ClaudeDesk 里那条不再显示"待决定"。
   - **`wait` 被中断或会话重启了**：`"$PY" "$DESK" responses --id <id>` 查有没有回复，没有就重新挂 `wait`。
   - **检查还有哪些没回复**：`"$PY" "$DESK" list --open --source <名>`。

## 发回答（answer）

```bash
"$PY" "$DESK" post --kind answer --source my-project \
  --title "两个配置目录的 skill 会自动同步吗" \
  --question "我在 D 盘改了 skill，C 盘那边会不会跟着变？" \
  --body-file "<scratchpad>/answer.md"
```

- `--question` 放用户原话；很长就用 `--question-file`。
- 正文就是完整回答，和对话里的回答一致或更完整。先给结论，再给依据，数字和路径写全。
- 一轮里用户问了几个问题，合成一条发，标题概括。

## 发通知（info）

```bash
"$PY" "$DESK" post --kind info --source my-project --title "全量测试跑完了" --body "结果：… 报告在 …"
```

短正文可以直接用 `--body`。长正文用 `--body-file`，或者 `--body -` 从 stdin 读。

## 注意

- 正文一律用文件或 stdin 传，不要把多行 Markdown 塞进命令行参数。命令行只放标题、选项这类短文本，用单引号包起来。
- 不要往消息里写凭据、token。
- 数据在 `<ClaudeDesk 目录>\data\`（`inbox.jsonl` / `responses.jsonl`，都只追加）。不要手改；要标"已处理"用 `close`。
- 程序没响应时先看托盘里有没有图标；日志在 `<ClaudeDesk 目录>\data\claudedesk.log`。
