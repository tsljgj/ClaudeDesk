"""接入 Claude Code：简写命令（answer / decide / info）、setup 装 skill 和 hooks、三个兜底 hook。
会话记录用 test_protocol 里合成的（Tx），配置目录用临时目录，不碰真的 ~/.claude。"""
import datetime as dt
import json
import subprocess
import sys
import uuid

import desk
import pytest
from test_protocol import ROOT, Tx, cli, env_for, text, tool

DESK = 'python "C:/Tools/ClaudeDesk/desk.py"'


def fresh(t):
    """合成记录的时间改成"刚刚"：hook 按这一轮开始的时间认"这一轮发过 / 交过什么"。"""
    now = dt.datetime.now(dt.timezone.utc)
    n = len(t.recs)
    for i, r in enumerate(t.recs):
        if "timestamp" in r and "uuid" in r:
            r["timestamp"] = (now - dt.timedelta(seconds=(n - i) * 0.01 + 1)).isoformat()
    return t


def old_post(d, **kw):
    """这一轮开始之前就发过的消息。"""
    m = desk.make_message(source="示例项目", **kw)
    m["ts"] = "2026-01-01T00:00:00Z"
    desk.post_message(m, d)
    return m


def setup_env(tmp_path, monkeypatch):
    d = tmp_path / "data"
    d.mkdir()
    (d / desk.INBOX).touch()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
    return d, str(uuid.uuid4())


def msgs(d):
    return desk.read_all(d / desk.INBOX)


# ---------------------------------------------------------------- skill 原文

def test_embedded_skill_matches_file():
    assert desk.SKILL_MD == (ROOT / "skill" / "claude-desk" / "SKILL.md").read_text(encoding="utf-8")
    assert desk.SKILL_PLACEHOLDER in desk.SKILL_MD


def test_derive_title():
    assert desk.derive_title("## **为什么** CI 变慢了？\n第二行") == "为什么 CI 变慢了？"
    assert desk.derive_title("", None, "1. 先看这个") == "先看这个"
    assert len(desk.derive_title("长" * 80)) == 30


# ---------------------------------------------------------------- 简写命令

def test_answer_shortcut_takes_everything_from_chat(tmp_path):
    cfg, d, sid = tmp_path / "cfg", tmp_path / "data", str(uuid.uuid4())
    t = Tx(sid)
    t.user("acme-data-pipeline 的同步多久跑一次？")
    t.assistant(text("我先看一下配置。"), tool("cat cron.yaml", "toolu_1"))
    t.tool_result("toolu_1")
    t.assistant(text("**每 15 分钟**一次，夜里改成每小时。"), tool(f'{DESK} --data "C:/x/data" answer'))
    t.write(cfg)
    r = cli(d, "answer", "--no-launch", session=sid, extra={"CLAUDE_CONFIG_DIR": cfg})
    assert r.returncode == 0, r.stderr
    m = msgs(d)[-1]
    assert m["kind"] == "answer" and m["body"] == "**每 15 分钟**一次，夜里改成每小时。"
    assert m["question"] == "acme-data-pipeline 的同步多久跑一次？" and m["title"] == m["question"]
    r = cli(d, "answer", "自己的标题", "--body", "b", "--question", "q", "--no-launch", session=sid)
    assert r.returncode == 0 and msgs(d)[-1]["title"] == "自己的标题" and msgs(d)[-1]["question"] == "q"


def test_answer_shortcut_without_question_still_posts(tmp_path):
    """原问题取不到（比如这一轮是 listen 叫醒的、记录里找不到）也照发：问题只是给用户对照的。"""
    d = tmp_path / "data"
    r = cli(d, "answer", "标题", "--body", "正文", "--no-launch", session="S-none",
            extra={"CLAUDE_CONFIG_DIR": tmp_path / "cfg"})
    assert r.returncode == 0, r.stderr
    assert msgs(d)[-1]["body"] == "正文" and "question" not in msgs(d)[-1]


def test_answer_reply_to_followup(tmp_path):
    d = tmp_path / "data"
    m = old_post(d, kind="answer", title="原来的回答", body="b", session="S1")
    f = desk.write_followup(m, "那夜里为什么改成每小时？", d)
    r = cli(d, "answer", "--reply-to", f["id"], "--body", "省钱", "--no-launch", session="S1")
    assert r.returncode == 0, r.stderr
    last = msgs(d)[-1]
    assert last["reply_to"] == m["id"] and last["followup_id"] == f["id"]
    assert last["question"] == "那夜里为什么改成每小时？" and last["title"] == "那夜里为什么改成每小时？"


def test_decide_and_info_shortcuts(tmp_path):
    d = tmp_path / "data"
    md = tmp_path / "a.md"
    md.write_text("背景", encoding="utf-8")
    r = cli(d, "decide", "用哪个方案？", "--body-file", md, "-o", "A::快", "-o", "B::稳", "--rec", "2", "--high",
            "--no-launch", session="S1")
    assert r.returncode == 0, r.stderr
    m = msgs(d)[-1]
    assert m["kind"] == "decision" and m["priority"] == "high" and m["recommended"] == 2
    assert [o["label"] for o in m["options"]] == ["A", "B"] and m["body"] == "背景"
    r = cli(d, "info", "跑完了", "--body", "全部通过", "--no-launch", session="S1")
    assert r.returncode == 0 and msgs(d)[-1]["kind"] == "info" and msgs(d)[-1]["title"] == "跑完了"


def test_anchor_recognises_answer_command():
    rec = {"type": "assistant", "message": {"content": [{"type": "tool_use", "input": {"command": f"{DESK} answer"}}]}}
    assert desk._anchor([rec]) is not None
    for cmd in (f'{DESK} --data "C:/a b/data" answer "t"', "python desk.py answer --reply-to x"):
        rec["message"]["content"][0]["input"]["command"] = cmd
        assert desk._anchor([rec]) is not None
    rec["message"]["content"][0]["input"]["command"] = f"{DESK} decide 'answer this'"
    assert desk._anchor([rec]) is None


# ---------------------------------------------------------------- setup

def test_setup_installs_merges_and_removes(tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    mine = {"model": "x", "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}],
                                    "PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "lint"}]}]}}
    (cfg / "settings.json").write_text(json.dumps(mine), encoding="utf-8")
    res = desk.setup_claude("C:\\Py 3\\python.exe", "C:\\Program Files\\ClaudeDesk\\desk.py", cfg)
    assert res["command"] == '"C:/Py 3/python.exe" "C:/Program Files/ClaudeDesk/desk.py"'
    st = json.loads((cfg / "settings.json").read_text(encoding="utf-8"))
    assert st["model"] == "x"
    assert [h["command"] for g in st["hooks"]["Stop"] for h in g["hooks"]] == ["echo mine", res["command"] + " hook stop"]
    ask = [g for g in st["hooks"]["PreToolUse"] if g.get("matcher") == "AskUserQuestion"]
    assert ask and ask[0]["hooks"][0]["command"].endswith(" hook ask")
    assert st["hooks"]["SessionStart"][0]["hooks"][0]["command"].endswith(" hook session-start")
    assert json.loads((cfg / "settings.json.claudedesk.bak").read_text(encoding="utf-8")) == mine
    skill = (cfg / "skills" / "claude-desk" / "SKILL.md").read_text(encoding="utf-8")
    assert res["command"] in skill and desk.SKILL_PLACEHOLDER not in skill
    stat = desk.setup_status(cfg)
    assert stat["ok"] and sorted(stat["hooks"]) == ["ask", "session-start", "stop"] and stat["command"] == res["command"]

    again = desk.setup_claude("C:\\Py 3\\python.exe", "C:\\Program Files\\ClaudeDesk\\desk.py", cfg)
    assert not again["settings_changed"] and not again["skill_changed"]  # 再装一次：不重复挂
    moved = desk.setup_claude("C:/Py/python.exe", "D:/ClaudeDesk/desk.py", cfg, block_ask=False)  # 换了路径：替换旧的
    st = json.loads((cfg / "settings.json").read_text(encoding="utf-8"))
    cmds = [h["command"] for gs in st["hooks"].values() for g in gs for h in g["hooks"]]
    assert sum("desk.py" in c for c in cmds) == 2 and all(moved["command"] in c for c in cmds if "desk.py" in c)

    desk.setup_claude("x", "y/desk.py", cfg, remove=True)
    assert json.loads((cfg / "settings.json").read_text(encoding="utf-8")) == mine
    assert not (cfg / "skills" / "claude-desk").exists()
    assert not desk.setup_status(cfg)["ok"]


def test_setup_refuses_broken_settings_and_dry_run(tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "settings.json").write_text("{ broken", encoding="utf-8")
    with pytest.raises(desk.SetupError):
        desk.setup_claude("py", "desk.py", cfg)
    assert (cfg / "settings.json").read_text(encoding="utf-8") == "{ broken"
    r = cli(tmp_path / "data", "setup", "--config", tmp_path / "c2", "--dry-run")
    assert r.returncode == 0 and "desk.py" in r.stdout and not (tmp_path / "c2").exists()
    r = cli(tmp_path / "data", "setup", "--config", tmp_path / "c2")
    assert r.returncode == 0 and desk.setup_status(tmp_path / "c2")["ok"]


# ---------------------------------------------------------------- hooks

def test_hook_cli_never_fails():
    for stdin in ("", "not json", "[1,2]", '{"session_id": 5}'):
        r = subprocess.run([sys.executable, str(ROOT / "desk.py"), "hook", "stop"], input=stdin, env=env_for(),
                           capture_output=True, encoding="utf-8", timeout=60)
        assert r.returncode == 0


def test_session_start_injects_rules_and_status(tmp_path, monkeypatch):
    d, sid = setup_env(tmp_path, monkeypatch)
    old_post(d, kind="decision", title="选哪个", options=["A", "B"], session=sid)
    out = desk.hook_session_start({"session_id": sid, "source": "compact"}, d)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "desk answer" in ctx and "desk decide" in ctx and str(ROOT / "desk.py").replace("\\", "/") in ctx
    assert "1 个待决定" in ctx and "listen 没在跑" in ctx


def test_ask_hook_denies_with_ready_command(tmp_path, monkeypatch):
    d, _ = setup_env(tmp_path, monkeypatch)
    inp = {"tool_name": "AskUserQuestion", "tool_input": {"questions": [
        {"question": "部署到哪个环境？", "header": "环境", "options": [{"label": "预发", "description": "先验证"},
                                                                   {"label": "生产", "description": "直接上"}]}]}}
    assert desk.hook_ask(inp, d) is None  # 程序没在运行：放行
    monkeypatch.setattr(desk, "app_running", lambda *_: True)
    out = desk.hook_ask(inp, d)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    assert 'decide "部署到哪个环境？" --body-file <md> -o "预发::先验证" -o "生产::直接上"' in out["permissionDecisionReason"]


def turn_with_answer(sid, question, answer, calls=()):
    t = Tx(sid)
    t.user("更早的")
    t.assistant(text("更早的回答"))
    t.user(question)
    t.assistant(text("我查一下。"), tool("grep -r sync .", "toolu_9"))
    t.tool_result("toolu_9")
    for c in calls:
        t.assistant(tool(c))
    t.assistant(text(answer))
    return fresh(t)


LONG = "同步每 15 分钟跑一次。" * 20


def test_stop_auto_posts_forgotten_answer(tmp_path, monkeypatch):
    d, sid = setup_env(tmp_path, monkeypatch)
    p = turn_with_answer(sid, "acme-data-pipeline 的同步多久跑一次？", LONG).write(tmp_path / "cfg")
    out = desk.hook_stop({"session_id": sid, "transcript_path": str(p)}, d)
    m = msgs(d)[-1]
    assert m["kind"] == "answer" and m["body"] == LONG and m["auto"] == "stop-hook"
    assert m["question"] == "acme-data-pipeline 的同步多久跑一次？" and m["session"] == sid
    assert "自动补发" in out["systemMessage"] and "decision" not in out
    # 再停一次（同一轮）：已经发过了，不重复
    assert desk.hook_stop({"session_id": sid, "transcript_path": str(p)}, d) is None
    assert len(msgs(d)) == 1


@pytest.mark.parametrize("question,answer,calls", [
    ("把 README 的错别字改掉", LONG, ()),                         # 不是问题，是任务
    ("这个怎么配置？", "改好了。", ()),                            # 回答太短
    ("这个怎么配置？", LONG, (f"{DESK} answer",)),                 # 自己发过了
])
def test_stop_leaves_alone(tmp_path, monkeypatch, question, answer, calls):
    d, sid = setup_env(tmp_path, monkeypatch)
    p = turn_with_answer(sid, question, answer, calls).write(tmp_path / "cfg")
    assert desk.hook_stop({"session_id": sid, "transcript_path": str(p)}, d) is None
    assert msgs(d) == []


def test_stop_uses_last_assistant_message_and_skips_unused_data_dir(tmp_path, monkeypatch):
    d, sid = setup_env(tmp_path, monkeypatch)
    p = turn_with_answer(sid, "为什么会慢？", "短").write(tmp_path / "cfg")
    desk.hook_stop({"session_id": sid, "transcript_path": str(p), "last_assistant_message": LONG}, d)
    assert msgs(d)[-1]["body"] == LONG
    assert desk.hook_stop({"session_id": sid, "transcript_path": str(p)}, tmp_path / "never-used") is None


def followup_turn(tmp_path, d, sid, n):
    m = old_post(d, kind="answer", title="原来的回答", body="b", session=sid)
    fus = [desk.write_followup(m, f"第 {i + 1} 个追问：为什么？", d) for i in range(n)]
    t = Tx(sid)
    t.user("最开始的问题")
    t.assistant(text("回答"), tool(f"{DESK} answer"))
    t.tool_result("toolu_x")
    p = fresh(t).write(tmp_path / "cfg")
    for f in fus:
        desk.mark_delivered(d, "followup", f["id"], sid, "listen")
    t.user_str("<task-notification><status>completed</status></task-notification>", origin={"kind": "task-notification"})
    t.assistant(text("追问的回答：因为夜里没人用，每小时一次就够了。"))
    t.write(tmp_path / "cfg")
    return m, fus, p


def test_stop_auto_replies_single_followup(tmp_path, monkeypatch):
    d, sid = setup_env(tmp_path, monkeypatch)
    m, (f,), p = followup_turn(tmp_path, d, sid, 1)
    out = desk.hook_stop({"session_id": sid, "transcript_path": str(p)}, d)
    last = msgs(d)[-1]
    assert last["reply_to"] == m["id"] and last["followup_id"] == f["id"] and last["auto"] == "stop-hook"
    assert last["body"] == "追问的回答：因为夜里没人用，每小时一次就够了。"
    assert "追问" in out["systemMessage"]
    assert desk.hook_stop({"session_id": sid, "transcript_path": str(p)}, d) is None  # 回过了


def test_stop_blocks_on_several_unanswered_followups(tmp_path, monkeypatch):
    d, sid = setup_env(tmp_path, monkeypatch)
    _, fus, p = followup_turn(tmp_path, d, sid, 2)
    out = desk.hook_stop({"session_id": sid, "transcript_path": str(p)}, d)
    assert out["decision"] == "block"
    assert all(f"answer --reply-to {f['id']}" in out["reason"] for f in fus)
    assert desk.hook_stop({"session_id": sid, "transcript_path": str(p), "stop_hook_active": True}, d) is None


def test_stop_blocks_when_listen_missing(tmp_path, monkeypatch):
    d, sid = setup_env(tmp_path, monkeypatch)
    old_post(d, kind="decision", title="选哪个", options=["A", "B"], session=sid)
    p = turn_with_answer(sid, "把 README 改掉", "改好了").write(tmp_path / "cfg")
    out = desk.hook_stop({"session_id": sid, "transcript_path": str(p)}, d)
    assert out["decision"] == "block" and "listen" in out["reason"] and "1 个待决定" in out["reason"]
    assert desk.hook_stop({"session_id": sid, "transcript_path": str(p), "stop_hook_active": True}, d) is None
    p = turn_with_answer(sid, "把 README 改掉", "改好了", (f"{DESK} listen",)).write(tmp_path / "cfg")
    assert desk.hook_stop({"session_id": sid, "transcript_path": str(p)}, d) is None  # 这一轮刚启动了 listen
