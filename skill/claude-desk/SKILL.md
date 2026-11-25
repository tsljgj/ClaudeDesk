---
name: claude-desk
description: 通过桌面程序 ClaudeDesk 和用户沟通。需要用户拍板时发 decide（不用 AskUserQuestion）；回答了用户的问题就紧接着 desk answer 发一份，免得被工具输出淹没；少量进展用 info。回复和追问由每个会话唯一的后台 listen 送回来。
---

# ClaudeDesk 速查

命令里的 `desk` = `python C:/path/to/ClaudeDesk/desk.py`（在 ClaudeDesk 设置里点"接入 Claude Code"会换成真的路径；手动安装时换成 Python 3.10+ 和 desk.py 的路径）。
desk.py 自己认得当前会话和它开在哪个仓库（cd 到别处也不变），不要给 `--source`、`--repo`。正文用文件或从对话里取，不要把多行 Markdown 塞进命令行；不写凭据。

## 什么时候发什么
- 用户问了问题 → 对话里照常答完，**在同一条消息里**紧接着 `desk answer`。下达任务、"好的 / 收到"不发。
- 要用户拍板 → `desk decide`。一律用它，不用 AskUserQuestion。
- `desk info` 少用：长任务完成、跑挂了要人管、机器或环境出了问题。
- 子 agent 不发 decide、不跑 listen：要用户定的事交回主会话。

## 回答
`desk answer`：不用参数。正文是你刚写的那一段（最后一次工具调用之后的文字），原问题是用户最近一条消息，标题取问题第一行，都从会话记录里取。
- 所以答完立刻调用，中间不要再写别的话。想自己定标题：`desk answer "<概括，30 字内>"`。
- 报错（找不到会话记录 / 没取到文字）时改用 `desk answer "<标题>" --body-file <md> --question "<原文>"`。
- 一轮里用户问了几个问题，答完合成一条发。

## 决定
1. Write 一个 .md：背景、各选项的后果和代价、推荐哪个和理由。要能单独看懂（用户可能几小时后才看）。
2. `desk decide "<一个问题，30 字内>" --body-file <md> -o "短标签::一句说明" -o "…" --rec N`
   卡住、不定就做不下去的加 `--high`。
3. 对话里只说一句"已发到 ClaudeDesk：<标题>"，继续做不依赖它的事；没事可做就结束这一轮。
4. 确保 listen 在跑（下一节）。

## listen：每个会话只要一个
- 发过 decide、或 desk 在 stderr 提示"没有 listen 在跑"时，用 Bash `run_in_background: true`、不设超时启动 `desk listen`。已经在跑就别再开（重复的立刻退出 5）。
- 醒来（退出 0）时 stdout 每行一件事。**一次处理完这一批，再重启一次 listen。**
  - `{"ev":"reply","id","title","choice","choice_index","text"}`：先在对话里复述一句"用户选了 X（补充：…），开始做"，再按 choice 做，text 里的补充也要遵守；只有 text 或和 choice 冲突时以 text 为准；看不懂就再发 decide，不要猜。选项同名时以 choice_index 为准。
  - 用户在 ClaudeDesk 里标为已处理、跳过的决定不会送来，不用等。旧记录还可能带 `"resolved":true` / `"dismissed":true`：不按任何选项做，说一句就继续。
  - `{"ev":"followup","id","msg","kind","title","question","text"}`（追问回复过的决定时还带 choice、reply_text）：在对话里回答，然后**在同一条消息里** `desk answer --reply-to <id>`（id 原样抄）。一批里有几条追问就一条一条答、一条一条发。
- 退出 4（会话没了）、5（重复）不用处理。不要用 `list` / `responses` 轮询。

## 用户在对话里答了决定
- 一条：`desk close --id <id> --text "用户在对话里选了 B"`；本会话所有还在等的：`desk close --mine`。
- 退出 3 = 用户也在 ClaudeDesk 里答了（stdout 有那条回复）：一致就照做，不一致就在对话里问清以哪个为准。那条带 `"resolved":true` 或 `"dismissed":true` = 用户在那边处理掉了，不用为它做什么。

## 新会话、检查
- `desk status`：一行，`open=待决定 undelivered=没送达 listen=on/off`；有 `orphaned=N` 表示这个仓库里已结束的会话留下了没送达的回复或追问。
- 用户提到之前在 ClaudeDesk 里回复过、或 status 显示 orphaned 时：`desk inbox` 看一眼，`desk inbox --adopt` 接过来（输出和 listen 一样，照样处理，然后确保 listen 在跑）。

## 兜底（装了 hooks 才有）
会话开始时会提醒这些规则；AskUserQuestion 会被拦下，改用 decide；一轮结束时答了问题没发、追问没回，会自动补发或提醒你补上；有待决定但 listen 没在跑，会提醒你启动。兜底不是替代，照常自己发。

## 出问题
- 老写法 `desk post --kind answer|decision|info …` 照样能用。
- post 提示"没有 ClaudeDesk 在看这个数据目录"：`desk` 指向了别处的 desk.py 副本，改成安装目录里的那个再发。
- 程序没反应：看托盘图标；日志在 `<ClaudeDesk 目录>/data/claudedesk.log`。
