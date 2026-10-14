"""标为已处理 / 归档、删除待决定：只记一条 silent 的回复，不通知会话（listen、wait、inbox、status、close 都不把它当回复交出去），
可以撤销（unresolve 把那一行从 responses.jsonl 里去掉）；按时间归档已处理的要用的"最后打开时间"（read_at / last_active）。"""
import datetime as dt
import json
import os
import time

import desk
from claudedesk.store import DISMISS_TEXT, RESOLVE_TEXT, Store
from test_protocol import cli, events, fake_claude, spawn, until
from test_protocol import post as spost
from test_server import call, srv  # noqa: F401（srv 是 fixture）


def post(d, ago=None, **kw):
    kw.setdefault("source", "proj")
    kw.setdefault("title", "t")
    m = desk.make_message(**kw)
    if ago is not None:  # 发在 ago 以前
        m["ts"] = (dt.datetime.now().astimezone() - ago).isoformat(timespec="milliseconds")
    return desk.post_message(m, d)


def resp(d):
    return {r["id"]: r for r in desk.read_all(d / desk.RESPONSES)}


def test_resolve_and_dismiss_are_silent_and_unresolve_reopens_only_those(tmp_path):
    d = tmp_path
    a, b, c, e = (post(d, kind="decision", options=["A"]) for _ in range(4))
    ans = post(d, kind="answer")
    s = Store(d)
    s.poll()
    assert s.resolve([a, ans]) == 1
    s.archive([b])  # 归档待决定 = 跳过
    s.submit(c, "A", "真回复")
    r = resp(d)
    assert r[a]["resolved"] is True and r[a]["silent"] is True and r[a]["text"] == RESOLVE_TEXT
    assert r[b]["dismissed"] is True and r[b]["silent"] is True and r[b]["text"] == DISMISS_TEXT
    assert "silent" not in r[c] and ans not in r
    assert s.summary(s.msgs[a])["silent"] is True and "silent" not in s.summary(s.msgs[c])
    (d / desk.RESPONSES).open("ab").write(b"{broken\n")  # 坏行原样保留

    assert s.unresolve([c, ans]) == 0  # 真回复不动；没有回复的不算
    assert s.unresolve([a, b]) == 2
    raw = (d / desk.RESPONSES).read_text(encoding="utf-8")
    assert a not in raw and b not in raw and c in raw and "{broken" in raw
    assert s.is_open(s.msgs[a]) and s.is_open(s.msgs[b])
    s.poll()  # 文件换了：从头再读，不会把删掉的读回来，也不会丢别的
    assert s.is_open(s.msgs[a]) and set(s.responses) == {c}
    s2 = Store(d)
    s2.poll()
    assert s2.is_open(s2.msgs[a]) and not s2.is_open(s2.msgs[c])
    assert s.unresolve([a]) == 0  # 已经撤销过了
    s.submit(a, "A", "撤销以后又回复了")  # 重新打开的决定照常能回复
    assert resp(d)[a]["text"] == "撤销以后又回复了"

    # 防御：已经交给会话的收不回来
    s.resolve([e])
    desk.mark_delivered(d, "reply", e, "S", "close")
    assert s.unresolve([e]) == 0 and resp(d)[e]["resolved"] is True


def test_listen_batch_delivers_the_real_reply_but_not_the_silent_ones(tmp_path):
    d, me = tmp_path, os.getpid()
    a = spost(d, "S", me, kind="decision", title="标为已处理的", options=["x"])
    b = spost(d, "S", me, kind="decision", title="真回复的", options=["x", "y"])
    c = spost(d, "S", me, kind="decision", title="归档的", options=["x"])
    p = spawn(d, "listen", "--interval", "0.1", "--batch", "0.5", session="S", pid=me)
    try:
        assert until(lambda: "S" in desk.presence(d, sessions=["S"])[1])
        store = Store(d)
        store.poll()
        store.resolve([a])
        store.submit(b, "y", "")
        store.archive([c])
        out, err = p.communicate(timeout=20)
    finally:
        p.kill()
    assert p.returncode == 0, err
    assert events(out) == [{"ev": "reply", "id": b, "title": "真回复的", "choice": "y", "choice_index": 2}]
    assert [r["id"] for r in desk.read_all(d / desk.DELIVERIES) if r.get("kind") == "reply"] == [b]
    r = cli(d, "listen", "--timeout", "0.6", "--interval", "0.1", session="S", pid=me)  # silent 的永远不交
    assert r.returncode == 2 and r.stdout == ""
    # 撤销后用户真的回复了：照常交
    store.unresolve([a])
    store.submit(a, "x", "")
    r = cli(d, "listen", "--batch", "0.2", "--interval", "0.1", "--timeout", "10", session="S", pid=me)
    assert r.returncode == 0 and [e["id"] for e in events(r.stdout)] == [a]


def test_wait_id_keeps_waiting_past_a_silent_reply_and_survives_the_rewrite(tmp_path):
    d = tmp_path
    other = post(d, kind="decision", options=["x"])
    a = post(d, kind="decision", title="旧协议", options=["x"])
    store = Store(d)
    store.poll()
    store.submit(other, "x", "一段比较长的补充说明，让文件前面有点东西" * 3)
    w = spawn(d, "wait", "--id", a, "--interval", "0.1", "--timeout", "30")
    try:
        assert until(lambda: a in desk.presence(d, ids=[a])[2])
        store.resolve([a])
        time.sleep(0.6)  # wait 每 0.1 秒读一次：已经读到那条 silent 的了，它不算回复
        assert w.poll() is None
        store.unresolve([a])  # 文件整份换掉、变短了
        store.submit(a, "x", "")  # 这一行比原来那条短：只按旧位置读会读不到
        out, err = w.communicate(timeout=20)
    finally:
        w.kill()
    assert w.returncode == 0, err
    got = json.loads(out)
    assert got["id"] == a and got["choice"] == "x" and "silent" not in got


def test_close_status_close_mine_and_inbox_ignore_silent_replies(tmp_path):
    d, me = tmp_path, os.getpid()
    a = spost(d, "S", me, kind="decision", title="a", options=["x"])
    b = spost(d, "S", me, kind="decision", title="b", options=["x"])
    c = spost(d, "S", me, kind="decision", title="c", options=["x"])
    store = Store(d)
    store.poll()
    store.resolve([a])
    store.submit(c, "x", "")
    assert cli(d, "status", session="S").stdout.strip() == "open=1 undelivered=1 listen=off"  # a 不算待决定，也不算没送达

    r = cli(d, "close", "--id", a, session="S")
    assert r.returncode == 3 and json.loads(r.stdout)["resolved"] is True and "没有通知会话" in r.stderr
    assert not any(x.get("kind") == "reply" for x in desk.read_all(d / desk.DELIVERIES))  # 不记送达（撤销后还要交真回复）

    r = cli(d, "close", "--mine", session="S")
    assert r.returncode == 3, r.stderr
    evs = events(r.stdout)
    assert [e.get("id") for e in evs[:-1]] == [c] and evs[-1] == {"closed": [b]}  # a：已经处理掉了，不关、不报告
    assert resp(d)[a]["resolved"] is True and "closed_by" not in resp(d)[a]

    # 已结束的会话留下的：silent 的不列，接管时也不交
    claude = fake_claude()
    try:
        old = spost(d, "OLD", claude.pid, kind="decision", title="old", options=["x"], repo="r1")
        gone = spost(d, "OLD", claude.pid, kind="decision", title="old 归档的", options=["x"], repo="r1")
        store.poll()
        store.resolve([old])
        store.archive([gone])
    finally:
        claude.kill()
        claude.wait()
    r = cli(d, "inbox", "--repo", "r1", session="NEW", pid=me)
    assert r.returncode == 0 and r.stdout == "" and r.stderr.startswith("0 ")
    r = cli(d, "inbox", "--repo", "r1", "--adopt", session="NEW", pid=me)
    assert r.returncode == 0 and r.stdout == ""
    assert cli(d, "status", session="NEW", cwd=d).stdout.strip() == "open=0 undelivered=0 listen=off"


def test_read_at_counts_only_opening_and_feeds_last_active(tmp_path):
    d = tmp_path
    seen = post(d, ago=dt.timedelta(days=3), kind="answer")
    bulk = post(d, ago=dt.timedelta(days=3), kind="answer")
    dec = post(d, ago=dt.timedelta(days=3), kind="decision", options=["A"])
    gone = post(d, kind="answer")
    s = Store(d)
    s.poll()
    la = lambda i: dt.datetime.fromisoformat(s.summary(s.msgs[i])["last_active"])  # noqa: E731
    now = dt.datetime.now().astimezone()
    assert now - la(seen) > dt.timedelta(days=2)  # 只有消息本身的时间
    s.mark_read([seen], opened=True)  # 打开了（读过的再打开也一样会刷新）
    s.mark_read([bulk])  # 批量标为已读不算打开
    s.submit(dec, "A", "")  # 回复也算动静
    assert now - la(seen) < dt.timedelta(minutes=1) and now - la(dec) < dt.timedelta(minutes=1)
    assert now - la(bulk) > dt.timedelta(days=2)
    first = la(seen)
    time.sleep(0.05)  # Windows 的时钟粒度粗：隔开一点才看得出刷新了
    assert s.mark_read([seen], opened=True) == 0 and la(seen) > first  # 已读的再打开：状态没变，时间刷新
    s.mark_read([gone], opened=True)
    s.delete([gone])
    s.save_state()
    st = json.loads((d / desk.STATE).read_text(encoding="utf-8"))
    assert set(st["read_at"]) == {seen}  # 删掉的不留
    s2 = Store(d)
    s2.poll()
    assert s2.summary(s2.msgs[seen])["last_active"] == s.summary(s.msgs[seen])["last_active"]


def test_server_read_opened_and_unresolve_actions(srv):
    d, store, server = srv
    a = post(d, ago=dt.timedelta(days=2), kind="decision", options=["A"])
    store.poll()

    def act(body):
        st, data = call(server, "POST", "/api/action", body)
        assert st == 200
        return json.loads(data)

    assert act({"action": "read", "ids": [a], "opened": True}) == {"ok": True, "result": 1}
    assert a in store.read_at
    assert act({"action": "resolve", "ids": [a]})["result"] == 1 and not store.is_open(store.msgs[a])
    assert act({"action": "unresolve", "ids": [a]}) == {"ok": True, "result": 1}
    assert store.is_open(store.msgs[a]) and resp(d) == {}
    assert act({"action": "unresolve", "ids": [a]}) == {"ok": True, "result": 0}
