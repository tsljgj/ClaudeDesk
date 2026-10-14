"""协议 v2：按会话送回复 / 追问（listen、inbox、close --mine、status）、post 记会话、--body-from-chat / --question-from-chat。
真的起 desk.py 子进程；会话记录用合成的（结构照 Claude Code 的真记录：一个内容块一行、parentUuid 串链），不碰真的会话记录。"""
import datetime as dt
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import desk
import pytest
from claudedesk.store import Store

ROOT = Path(__file__).resolve().parents[1]
CLEAN = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}


def env_for(session=None, pid=None, **extra):
    e = dict(CLEAN)
    if session:
        e["CLAUDE_CODE_SESSION_ID"] = session
    if pid:
        e["CLAUDE_PID"] = str(pid)
    e.update({k: str(v) for k, v in extra.items()})
    return e


def cli(d, *args, session=None, pid=None, cwd=None, extra=None, **kw):
    return subprocess.run([sys.executable, str(ROOT / "desk.py"), "--data", str(d), *args], cwd=cwd,
                          env=env_for(session, pid, **(extra or {})), capture_output=True, encoding="utf-8", timeout=60, **kw)


def spawn(d, *args, session=None, pid=None):
    return subprocess.Popen([sys.executable, str(ROOT / "desk.py"), "--data", str(d), *args], env=env_for(session, pid),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")


def until(cond, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def fake_claude():
    """当会话进程（claude.exe）用：一个睡着的 Python。"""
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])


def dead_pid():
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def post(d, session=None, pid=None, **kw):
    kw.setdefault("source", "proj")
    kw.setdefault("repo", "proj")
    start = desk.proc_info(pid)[1] if pid else None
    return desk.post_message(desk.make_message(session=session, session_pid=pid, session_pid_start=start, **kw), d)


def events(out):
    return [json.loads(x) for x in out.splitlines() if x.strip()]


def listening(d, s):
    return s in desk.presence(d, sessions=[s])[1]


# ---------------------------------------------------------------- post 记下会话

def test_post_records_session_pid_and_default_source(tmp_path):
    d, work = tmp_path / "data", tmp_path / "my-folder"
    work.mkdir()
    r = cli(d, "post", "--kind", "info", "--title", "t", "--body", "b", "--no-launch", session="S1", pid=os.getpid(), cwd=work)
    assert r.returncode == 0, r.stderr
    m = desk.find_message(r.stdout.strip(), d)
    assert m["session"] == "S1" and m["session_pid"] == os.getpid() and m["source"] == "my-folder"  # 没给 --source：仓库名 / 目录名
    assert m["session_pid_start"] == desk.proc_info(os.getpid())[1]
    assert "listen" in r.stderr  # 这个会话没有 listen 在跑：提示一句
    r = cli(d, "post", "--kind", "info", "--title", "t", "--body", "b", "--no-launch", "--session", "OTHER", "--source", "x",
            session="S1", pid=os.getpid(), cwd=work)
    m = desk.find_message(r.stdout.strip(), d)
    assert m["session"] == "OTHER" and "session_pid" not in m and m["source"] == "x"  # 别的会话的 pid 不知道
    with desk.hold_marker(desk.session_marker("S1", d), d, exclusive=True):
        r = cli(d, "post", "--kind", "info", "--title", "t", "--body", "b", "--no-launch", session="S1", cwd=work)
    assert "listen" not in r.stderr
    r = cli(d, "post", "--kind", "info", "--title", "t", "--body", "b", "--no-launch", cwd=work)  # 不在会话里：照旧
    assert "session" not in desk.find_message(r.stdout.strip(), d) and "listen" not in r.stderr


# ---------------------------------------------------------------- listen

def test_two_quick_replies_make_one_wake_and_are_delivered_once(tmp_path):
    d, me = tmp_path, os.getpid()
    a = post(d, "S", me, kind="decision", title="甲还是乙？", options=["甲", "乙"])
    b = post(d, "S", me, kind="decision", title="写点什么", body="正文不该出现在事件里")
    other = post(d, "T", me, kind="decision", title="别的会话的", options=["x"])
    p = spawn(d, "listen", "--interval", "0.1", session="S", pid=me)
    try:
        assert until(lambda: listening(d, "S"))
        store = Store(d)
        store.poll()
        store.submit(other, "x", "")  # 别的会话的回复不叫醒它
        store.submit(a, "乙", "顺便改 README", 2)
        time.sleep(0.6)
        store.submit(b, None, "写好了")
        out, err = p.communicate(timeout=20)
    finally:
        p.kill()
    assert p.returncode == 0, err
    evs = events(out)
    assert evs == [{"ev": "reply", "id": a, "title": "甲还是乙？", "choice": "乙", "choice_index": 2, "text": "顺便改 README"},
                   {"ev": "reply", "id": b, "title": "写点什么", "choice": None, "text": "写好了"}]  # 一次醒来带两件；不带正文
    dl = [r for r in desk.read_all(d / desk.DELIVERIES) if r.get("kind") == "reply"]
    assert [(r["id"], r["session"], r["via"]) for r in dl] == [(a, "S", "listen"), (b, "S", "listen")]
    assert until(lambda: not listening(d, "S"))
    r = cli(d, "listen", "--timeout", "1", "--interval", "0.1", session="S", pid=me)  # 交过的不再交
    assert r.returncode == 2 and r.stdout == ""
    store.poll()
    assert store.summary(store.msgs[a])["delivered"] and "delivered" not in store.summary(store.msgs[other])


def test_duplicate_listen_exits_5_and_never_double_delivers(tmp_path):
    d, me = tmp_path, os.getpid()
    a = post(d, "S", me, kind="decision", title="q", options=["x"])
    p = spawn(d, "listen", "--interval", "0.1", session="S", pid=me)
    try:
        assert until(lambda: listening(d, "S"))
        r = cli(d, "listen", session="S", pid=me)
        assert r.returncode == 5 and r.stdout == "" and len(r.stderr.strip().splitlines()) == 1
        desk.write_response(a, "x", "", "proj", d)
        out, _ = p.communicate(timeout=20)
    finally:
        p.kill()
    assert [e["id"] for e in events(out)] == [a]
    r = cli(d, "listen", "--timeout", "0.5", "--interval", "0.1", session="S", pid=me)
    assert r.returncode == 2  # 第一个退出了，可以再开；没东西可交


def test_listen_exits_silently_when_the_session_process_dies(tmp_path):
    d = tmp_path
    r = cli(d, "listen", session="S", pid=dead_pid())  # 一开始会话就不在了
    assert (r.returncode, r.stdout, r.stderr) == (4, "", "")
    claude = fake_claude()
    p = spawn(d, "listen", "--interval", "0.1", session="S", pid=claude.pid)
    try:
        assert until(lambda: listening(d, "S"))
        claude.kill()
        out, err = p.communicate(timeout=20)
    finally:
        p.kill()
        claude.kill()
    assert (p.returncode, out, err) == (4, "", "")
    assert not listening(d, "S")
    r = cli(d, "listen")  # 不知道是哪个会话
    assert r.returncode == 1 and "CLAUDE_CODE_SESSION_ID" in r.stderr


def test_listen_followups_own_close_and_wait_id_delivery(tmp_path):
    d, me = tmp_path, os.getpid()
    ans = post(d, "S", me, kind="answer", title="为什么慢", question="为什么这么慢？", body="因为 IO" * 50)
    dec = post(d, "S", me, kind="decision", title="清理吗？", options=["删", "留"])
    closed = post(d, "S", me, kind="decision", title="对话里答了", options=["x"])
    waited = post(d, "S", me, kind="decision", title="旧协议 wait --id", options=["x"])
    legacy = desk.post_message(desk.make_message("answer", "proj", "旧消息", "x"), d)  # 没有会话信息：listen 不管
    store = Store(d)
    store.poll()
    assert cli(d, "close", "--id", closed, "--text", "用户在对话里选了 x", session="S").returncode == 0  # 会话自己关的不算事件

    w = spawn(d, "wait", "--id", waited, "--interval", "0.1", session="S")  # 旧协议的 wait --id：挂"在等"标记，领走算送达
    try:
        assert until(lambda: waited in desk.presence(d, ids=[waited])[2])
        store.submit(waited, "x", "")
        out, _ = w.communicate(timeout=20)
    finally:
        w.kill()
    assert json.loads(out)["id"] == waited
    assert any(r.get("id") == waited and r.get("via") == "wait" for r in desk.read_all(d / desk.DELIVERIES))

    store.submit(dec, "删", "")
    store.add_followup(dec, "删了能恢复吗？")
    store.add_followup(ans, "换成 SSD 呢？")
    store.add_followup(legacy, "旧消息的追问")
    r = cli(d, "listen", "--batch", "0.2", "--interval", "0.1", session="S", pid=me)
    assert r.returncode == 0, r.stderr
    evs = events(r.stdout)
    assert [e["ev"] for e in evs] == ["reply", "followup", "followup"]
    assert evs[0] == {"ev": "reply", "id": dec, "title": "清理吗？", "choice": "删", "choice_index": 1}
    fu_dec, fu_ans = evs[1], evs[2]
    assert (fu_dec["msg"], fu_dec["kind"], fu_dec["choice"], fu_dec["text"]) == (dec, "decision", "删", "删了能恢复吗？")
    assert (fu_ans["msg"], fu_ans["kind"], fu_ans["question"], fu_ans["text"]) == (ans, "answer", "为什么这么慢？", "换成 SSD 呢？")
    assert "body" not in fu_ans and "因为 IO" not in r.stdout
    # 用追问 id 回答，配上了；旧版 wait --followups 也看得到送达标记，不会再交一次
    assert cli(d, "post", "--kind", "answer", "--title", "能", "--body", "x", "--reply-to", fu_dec["id"], "--no-launch",
               session="S").returncode == 0
    assert cli(d, "wait", "--followups", "--source", "proj", "--timeout", "0.5", "--interval", "0.1").stdout.count("旧消息的追问") == 1
    assert cli(d, "listen", "--timeout", "0.6", "--interval", "0.1", session="S", pid=me).returncode == 2


# ---------------------------------------------------------------- close --mine / status / inbox

def test_close_mine_and_status(tmp_path):
    d, me = tmp_path, os.getpid()
    a = post(d, "S", me, kind="decision", title="a", options=["x"])
    b = post(d, "S", me, kind="decision", title="b", options=["x"])
    c = post(d, "S", me, kind="decision", title="c", options=["x", "y"])
    t = post(d, "T", me, kind="decision", title="别的会话", options=["x"])
    r = cli(d, "status", session="S")
    assert r.stdout.strip() == "open=3 undelivered=0 listen=off"
    desk.write_response(c, "y", "", "proj", d, extra={"title": "c", "session": "S"})  # 用户在 ClaudeDesk 里先答了 c
    assert cli(d, "status", session="S").stdout.strip() == "open=2 undelivered=1 listen=off"
    r = cli(d, "close", "--mine", "--text", "对话里一起答了", session="S")
    assert r.returncode == 3, r.stderr
    evs = events(r.stdout)
    assert evs[0] == {"ev": "reply", "id": c, "title": "c", "choice": "y"} and sorted(evs[1]["closed"]) == sorted([a, b])
    resp = {x["id"]: x for x in desk.read_all(d / desk.RESPONSES)}
    assert resp[a]["closed_by"] == "claude" and resp[a]["text"] == "对话里一起答了" and t not in resp
    assert cli(d, "status", session="S").stdout.strip() == "open=0 undelivered=0 listen=off"
    r = cli(d, "close", "--mine", session="S")
    assert r.returncode == 0 and events(r.stdout) == [{"closed": []}]
    assert cli(d, "close", "--mine").returncode == 1 and cli(d, "close").returncode == 2


def test_inbox_lists_and_adopts_what_a_dead_session_left(tmp_path):
    d, me = tmp_path, os.getpid()
    claude = fake_claude()
    try:
        old = "OLD-SESSION"
        dec = post(d, old, claude.pid, kind="decision", title="old 的决定", options=["甲", "乙"], repo="r1")
        ans = post(d, old, claude.pid, kind="answer", title="old 的回答", question="原问题", body="x", repo="r1")
        res = post(d, old, claude.pid, kind="decision", title="标为已处理的", options=["x"], repo="r1")
        elsewhere = post(d, old, claude.pid, kind="answer", title="别的仓库", body="x", repo="r2")
        store = Store(d)
        store.poll()
        store.submit(dec, "乙", "")
        store.add_followup(ans, "再说说？")
        store.add_followup(elsewhere, "别的仓库的追问")
        store.resolve([res])
        r = cli(d, "inbox", "--repo", "r1", session="NEW", pid=me)
        assert r.returncode == 0 and r.stdout == "" and r.stderr.startswith("0 ")  # 会话还在：不是孤儿
        assert cli(d, "status", session="NEW", cwd=tmp_path).stdout.strip() == "open=0 undelivered=0 listen=off"
    finally:
        claude.kill()
        claude.wait()
    r = cli(d, "inbox", "--repo", "r1", session="NEW", pid=me)
    evs = events(r.stdout)
    assert [(e["ev"], e["id"] if e["ev"] == "reply" else e["msg"], e["session"]) for e in evs] == \
        [("reply", dec, old[:8]), ("followup", ans, old[:8])]  # 标为已处理的、别的仓库的不列
    assert not any(r.get("kind") in ("reply", "followup") for r in desk.read_all(d / desk.DELIVERIES))  # 只列不领
    r = cli(d, "inbox", "--repo", "r1", "--adopt", session="NEW", pid=me)
    assert r.returncode == 0, r.stderr
    assert [e["ev"] for e in events(r.stdout)] == ["reply", "followup"] and "session" not in events(r.stdout)[0]
    assert cli(d, "inbox", "--repo", "r1", session="NEW", pid=me).stdout == ""  # 领过了
    adopt = [x for x in desk.read_all(d / desk.DELIVERIES) if x.get("kind") == "adopt"]
    assert [(x["from"], x["repo"], x["session"], x["session_pid"]) for x in adopt] == [(old, "r1", "NEW", me)]
    # 接管以后：old 在 r1 的消息上的新追问送到 NEW；界面上它们跟着 NEW 的状态走。别的仓库的不接
    store.poll()
    store.add_followup(dec, "乙要多久？")
    r = cli(d, "listen", "--batch", "0.2", "--interval", "0.1", session="NEW", pid=me)
    assert [(e["ev"], e["msg"], e["text"]) for e in events(r.stdout)] == [("followup", dec, "乙要多久？")]
    store.refresh_listening(force=True)
    assert store.owner(store.msgs[dec]) == "NEW" and store.session_state(store.msgs[dec]) == "open"
    assert store.owner(store.msgs[elsewhere]) == old and store.session_state(store.msgs[elsewhere]) == "gone"
    assert cli(d, "inbox", "--adopt", session=None).returncode == 1


def test_listen_records_a_resumed_sessions_new_pid(tmp_path):
    """会话恢复后 claude.exe 换了 pid：listen 记一笔，程序不会把它当成已经结束、inbox 也不会把它的东西领走。"""
    d, me = tmp_path, os.getpid()
    a = post(d, "S", dead_pid(), kind="decision", title="恢复前发的", options=["x"])
    store = Store(d)
    store.poll()
    store.refresh_listening(force=True)
    assert store.session_state(store.msgs[a]) == "gone"
    assert cli(d, "listen", "--timeout", "0.3", "--interval", "0.1", session="S", pid=me).returncode == 2
    store.poll()
    store.refresh_listening(force=True)
    assert store.session_state(store.msgs[a]) == "open"
    desk.write_response(a, "x", "", "proj", d)
    assert cli(d, "inbox", "--repo", "proj", session="NEW").stdout == ""


# ---------------------------------------------------------------- 程序这边：会话状态、送达

def test_store_session_states_and_delivery(tmp_path):
    d, me = tmp_path, os.getpid()
    lis = post(d, "L", me, kind="decision", title="在等", options=["x"])
    opn = post(d, "O", me, kind="decision", title="开着", options=["x"])
    gone = post(d, "G", dead_pid(), kind="decision", title="结束了", options=["x"])
    nopid = post(d, "N", None, kind="decision", title="不知道 pid", options=["x"])
    legacy = desk.post_message(desk.make_message("decision", "proj", "旧消息", options=["x"]), d)
    store = Store(d)
    store.poll()
    with desk.hold_marker(desk.session_marker("L", d), d, exclusive=True) as h1, \
            desk.hold_marker(desk.session_marker("L", d), d, exclusive=True) as h2:
        assert (h1, h2) == ("ok", "dup")
        assert store.refresh_listening(force=True) is True
        st = {m["id"]: m for m in store.summaries()}
        assert [st[i]["session_state"] for i in (lis, opn, gone, nopid, legacy)] == ["listening", "open", "gone", "open", "unknown"]
        assert st[lis]["listening"] is True and st[legacy]["listening"] is False
    store.refresh_listening(force=True)
    assert store.summary(store.msgs[lis])["session_state"] == "open"
    with desk.hold_marker(desk.wait_marker(legacy, d), d):  # 旧消息有 wait --id 在等：也算会话在等
        store.refresh_listening(force=True)
        assert store.session_state(store.msgs[legacy]) == "unknown"  # 不知道会话：照旧
        with desk.hold_marker(desk.wait_marker(opn, d), d):
            store.refresh_listening(force=True)
            assert store.session_state(store.msgs[opn]) == "listening"
    store.submit(opn, "x", "")
    assert desk.read_all(d / desk.RESPONSES)[-1]["session"] == "O"  # 回复带着会话：原消息删了也送得到
    assert "delivered" not in store.summary(store.msgs[opn])
    desk.mark_delivered(d, "reply", opn, "O", "listen")
    assert desk.mark_delivered(d, "reply", opn, "O", "listen") is False  # 只记一次
    store.poll()
    assert store.summary(store.msgs[opn])["delivered"]
    f = store.add_followup(opn, "追问")
    assert f["session"] == "O"
    desk.mark_delivered(d, "followup", f["id"], "O", "listen")
    store.poll()
    assert store.detail(opn)["followups"][0]["delivered"] and store.summary(store.msgs[opn])["fstate"] == "1.1.0"


# ---------------------------------------------------------------- --body-from-chat / --question-from-chat

class Tx:
    """合成的 Claude Code 会话记录：和真记录一样，一个内容块一行（同一条 API 消息的几行 message.id 相同），parentUuid 串成链，
    中间夹着没有 uuid 的杂项行（last-prompt、ai-title、queue-operation）和 attachment。"""

    def __init__(self, sid):
        self.sid, self.recs, self.last, self.n = sid, [], None, 0

    def _rec(self, typ, message=None, **extra):
        self.n += 1
        u = str(uuid.uuid4())
        r = {"parentUuid": self.last, "isSidechain": False, "userType": "external", "cwd": "C:\\work\\proj",
             "sessionId": self.sid, "version": "2.1.296", "gitBranch": "main", "type": typ, "uuid": u,
             "timestamp": (dt.datetime(2026, 10, 14, 1, 0, tzinfo=dt.timezone.utc) + dt.timedelta(seconds=self.n)).isoformat()}
        if message is not None:
            r["message"] = message
        r.update(extra)
        self.recs.append(r)
        self.last = u
        return r

    def noise(self):
        self.recs += [{"type": "last-prompt", "lastPrompt": "x", "sessionId": self.sid},
                      {"type": "ai-title", "aiTitle": "t", "sessionId": self.sid},
                      {"type": "queue-operation", "operation": "enqueue", "sessionId": self.sid, "timestamp": "2026-10-14T01:00:00Z"}]

    def user(self, *texts, **extra):
        blocks = [{"type": "text", "text": t} for t in texts]
        return self._rec("user", {"role": "user", "content": blocks}, origin={"kind": "human"}, promptSource="sdk",
                         turnOrigin="human", promptId=str(uuid.uuid4()), **extra)

    def user_str(self, text, **extra):
        return self._rec("user", {"role": "user", "content": text}, **extra)

    def assistant(self, *blocks, split=True):
        mid = "msg_" + uuid.uuid4().hex[:20]

        def msg(bl):
            return {"model": "claude-opus-5-5", "id": mid, "type": "message", "role": "assistant", "content": bl,
                    "stop_reason": None, "usage": {"input_tokens": 1, "output_tokens": 1}}
        if split:
            for b in blocks:
                self._rec("assistant", msg([b]), requestId="req_1")
        else:
            self._rec("assistant", msg(list(blocks)), requestId="req_1")
        return [b.get("id") for b in blocks if b.get("type") == "tool_use"]

    def tool_result(self, tid, text="ok"):
        self._rec("user", {"role": "user", "content": [{"tool_use_id": tid, "type": "tool_result", "content": text}]},
                  toolUseResult={"stdout": text}, sourceToolAssistantUUID=self.last)
        self._rec("attachment", attachment={"type": "hook_success"})

    def write(self, cfg, sub=None):
        p = cfg / "projects" / "C--work-proj" / (f"{self.sid}.jsonl" if sub is None else f"{self.sid}/subagents/{sub}.jsonl")
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            for r in self.recs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return p


def think():
    return {"type": "thinking", "thinking": "（思考）", "signature": "sig"}


def text(t):
    return {"type": "text", "text": t}


def tool(cmd, tid=None):
    return {"type": "tool_use", "id": tid or "toolu_" + uuid.uuid4().hex[:12], "name": "Bash",
            "input": {"command": cmd, "description": "x"}}


POST = 'python desk.py post --kind answer --title "t" --question-from-chat --body-from-chat'
ANSWER = "**结论**：会自动同步。\n\n1. hook 在 SessionStart 跑\n2. 新者胜"


def typical(sid, split=True):
    """用户问 → 过程话 + 工具调用 → 后台任务通知（不是用户写的）→ 回答 + 在同一条消息里调用 post。"""
    t = Tx(sid)
    t.user("更早的问题")
    t.assistant(text("更早的回答"))
    t.noise()
    t.user("今天的 CI 为什么比平时多跑了一倍时间？", "<ide_opened_file>The user opened C:\\x\\a.md</ide_opened_file>")
    t.assistant(think(), text("我先看看同步脚本。"), tool("cat sync.py", "toolu_1"))
    t.tool_result("toolu_1")
    t.user_str("<task-notification><task-id>b1</task-id><status>completed</status></task-notification>",
               origin={"kind": "task-notification"}, promptSource="system", turnOrigin="task_notification")
    t.user_str("<command-name>/foo</command-name>")
    t._rec("user", {"role": "user", "content": [{"type": "text", "text": "Base directory for this skill: …"}]}, isMeta=True)
    t.noise()
    t.assistant(think(), text(ANSWER), tool(POST), split=split)
    return t


@pytest.mark.parametrize("split", [True, False])
def test_chat_text_typical_turn(tmp_path, monkeypatch, split):
    """回答写在调用 post 的同一条消息里：真记录里文字和 tool_use 各占一行（split），旧版记录在同一行。"""
    sid = str(uuid.uuid4())
    typical(sid, split).write(tmp_path)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    assert desk.chat_text(sid, "body") == ANSWER  # 只要最后一段：前面"我先看看…"是过程话
    assert desk.chat_text(sid, "question") == "今天的 CI 为什么比平时多跑了一倍时间？"  # IDE 附带的那块不算


def test_chat_text_answer_in_the_previous_record_and_branches(tmp_path, monkeypatch):
    sid = str(uuid.uuid4())
    t = Tx(sid)
    t.user("第一个问题")
    t.assistant(text("回答的第一段。"))  # 这一轮没调工具：文字之后紧接着另一条消息里调用 post
    t.assistant(text("回答的第二段。"))
    fork = t.last
    t.assistant(tool(POST))
    # 回退后的另一条分支（文件里更靠后，但不在当前这条链上）
    t.last = fork
    t.user("被回退掉的问题")
    t.assistant(text("被回退掉的回答"))
    p = t.write(tmp_path)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    assert desk.chat_text(sid, "body") == "回答的第一段。\n\n回答的第二段。"
    assert desk.chat_text(sid, "question") == "第一个问题"
    # 长会话：链伸出最后 2 MB 也能找到（往前多读）
    big = Tx(sid)
    big.user("很早以前问的")
    for i in range(400):
        tid = f"toolu_{i}"
        big.assistant(tool("x" * 6000, tid))
        big.tool_result(tid, "y" * 2000)
    big.assistant(text("最后的回答"), tool(POST))
    big.write(tmp_path)
    assert p.stat().st_size > 3 << 20
    assert desk.chat_text(sid, "body") == "最后的回答" and desk.chat_text(sid, "question") == "很早以前问的"


def test_chat_text_errors_and_subagent_transcript(tmp_path, monkeypatch):
    sid = str(uuid.uuid4())
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    with pytest.raises(desk.ChatError, match="没找到会话记录"):
        desk.chat_text(sid, "body")
    t = Tx(sid)
    t.user_str("This session is being continued from a previous conversation…", isCompactSummary=True)
    t.assistant(tool("ls", "toolu_9"))
    t.tool_result("toolu_9")
    t.assistant(tool(POST))  # 工具结果之后直接调用 post，没写文字
    t.write(tmp_path)
    with pytest.raises(desk.ChatError, match="没有文字"):
        desk.chat_text(sid, "body")
    with pytest.raises(desk.ChatError, match="没找到用户发的消息"):  # 压缩摘要不是用户写的
        desk.chat_text(sid, "question")
    # 子 agent 和主会话的会话 id 一样：看哪份记录里有最新的这次调用
    sub = Tx(sid)
    for r in t.recs[-1:]:
        r["timestamp"] = "2026-10-14T00:00:00+00:00"
    sub.user("子 agent 的任务")
    sub.assistant(text("子 agent 写的回答"), tool(POST))
    for r in sub.recs:
        r["isSidechain"] = True
        r["timestamp"] = "2026-10-14T05:00:00+00:00"
    sub.write(tmp_path, sub="agent-abc")
    t.write(tmp_path)
    assert desk.chat_text(sid, "body") == "子 agent 写的回答"
    with pytest.raises(desk.ChatError, match="不知道是哪个会话"):
        desk.chat_text(None, "body")


def test_post_body_and_question_from_chat_end_to_end(tmp_path):
    sid, d, cfg = str(uuid.uuid4()), tmp_path / "data", tmp_path / "cfg"
    typical(sid).write(cfg)
    r = cli(d, "post", "--kind", "answer", "--title", "两边会同步吗", "--question-from-chat", "--body-from-chat", "--no-launch",
            session=sid, pid=os.getpid(), extra={"CLAUDE_CONFIG_DIR": cfg})
    assert r.returncode == 0, r.stderr
    m = desk.find_message(r.stdout.strip(), d)
    assert (m["body"], m["question"], m["session"]) == (ANSWER, "今天的 CI 为什么比平时多跑了一倍时间？", sid)
    r = cli(d, "post", "--kind", "answer", "--title", "x", "--question", "自己给的", "--body-from-chat", "--no-launch",
            session=sid, extra={"CLAUDE_CONFIG_DIR": cfg})
    assert desk.find_message(r.stdout.strip(), d)["question"] == "自己给的"  # --question 优先
    r = cli(d, "post", "--kind", "answer", "--title", "x", "--body-from-chat", "--no-launch",
            session=str(uuid.uuid4()), extra={"CLAUDE_CONFIG_DIR": cfg})
    assert r.returncode == 1 and "--body-file" in r.stderr and "没找到会话记录" in r.stderr
    r = cli(d, "post", "--kind", "answer", "--title", "x", "--body", "b", "--question-from-chat", "--no-launch",
            extra={"CLAUDE_CONFIG_DIR": cfg})
    assert r.returncode == 1 and "--question" in r.stderr
