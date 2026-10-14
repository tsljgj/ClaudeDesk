---
name: claude-desk
description: 通过桌面程序 ClaudeDesk 和用户沟通。需要用户拍板时发 decision（不用 AskUserQuestion）；回答用户的问题时，对话里答完再发一份 answer，免得被工具输出淹没；少量进展用 info。回复和追问由每个会话唯一的后台 listen 送回来。
---

# ClaudeDesk 速查

命令里的 `desk` = `python C:/path/to/ClaudeDesk/desk.py`（安装时换成真的 Python 3.10+ 和 desk.py 路径）。
desk.py 自己记下当前会话和仓库，不用给 `--source`。正文用文件或 `--body-from-chat`，不要把多行 Markdown 塞进命令行；不写凭据。

## 什么时候发什么
- 要用户决定 → `decision`。一律用它，不用 AskUserQuestion。
- 用户问了问题 → 对话里照常答，再发 `answer`。下达任务、"好的 / 收到"不发。
- `info` 少用：长任务完成、跑挂了要人管、机器或环境出了问题。
- 子 agent 不发 decision、不跑 listen：要用户定的事交回主会话。

## 决定
1. Write 一个 .md：背景、各选项的后果和代价、推荐哪个和理由。要能单独看懂（用户可能几小时后才看）。
2. `desk post --kind decision --title "<一个问题，30 字内>" --body-file <md> --option "短标签::一句说明" … --recommended N`
   卡住、不定就做不下去的加 `--priority high`。
3. 对话里只说一句"已发到 ClaudeDesk：<标题>"，继续做不依赖它的事；没事可做就结束这一轮。
4. 确保 listen 在跑（下一节）。

## listen：每个会话只要一个
- post 在 stderr 提示"没有 listen 在跑"时，用 Bash `run_in_background: true`、不设超时启动 `desk listen`。已经在跑就别再开（重复的立刻退出 5）。
- 醒来（退出 0）时 stdout 每行一件事。**一次处理完这一批，再重启一次 listen。**
  - `{"ev":"reply","id","title","choice","choice_index","text"}`：先在对话里复述一句"用户选了 X（补充：…），开始做"，再按 choice 做，text 里的补充也要遵守；只有 text 或和 choice 冲突时以 text 为准；看不懂就再发 decision，不要猜。选项同名时以 choice_index 为准。
  - 带 `"resolved":true`（用户标为已处理）或 `"dismissed":true`（跳过）：不按任何选项做，说一句就继续。
  - `{"ev":"followup","id","msg","kind","title","question","text"}`（追问回复过的决定时还带 choice、reply_text）：在对话里回答，然后在同一条消息里 `desk post --kind answer --reply-to <id> --title "<概括>" --body-from-chat`。
- 退出 4（会话没了）、5（重复）不用处理。不要用 `list` / `responses` 轮询。

## 回答
对话里写好完整回答，紧接着**在同一条消息里**调用（中间不要再写别的文字）：
`desk post --kind answer --title "<概括，30 字内>" --question-from-chat --body-from-chat`
- 正文就是你刚写的那段，原问题是用户最近一条消息，都从会话记录里取，不用再写一遍。
- 报错（找不到会话记录 / 没取到文字）时改用 `--body-file <md>`、`--question "<原文>"`。
- 一轮里用户问了几个问题，答完合成一条发。

## 用户在对话里答了决定
- 一条：`desk close --id <id> --text "用户在对话里选了 B"`；本会话所有还在等的：`desk close --mine`。
- 退出 3 = 用户也在 ClaudeDesk 里答了（stdout 有那条回复）：一致就照做，不一致就在对话里问清以哪个为准。

## 新会话、检查
- `desk status`：一行，`open=待决定 undelivered=没送达 listen=on/off`；有 `orphaned=N` 表示这个仓库里已结束的会话留下了没送达的回复或追问。
- 用户提到之前在 ClaudeDesk 里回复过、或 status 显示 orphaned 时：`desk inbox` 看一眼，`desk inbox --adopt` 接过来（输出和 listen 一样，照样处理，然后确保 listen 在跑）。

## 出问题
- post 提示"没有 ClaudeDesk 在看这个数据目录"：`desk` 指向了别处的 desk.py 副本，改成安装目录里的那个再发。
- 程序没反应：看托盘图标；日志在 `<ClaudeDesk 目录>/data/claudedesk.log`。
