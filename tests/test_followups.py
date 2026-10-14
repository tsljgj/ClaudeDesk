"""追问：desk.py（wait --followups、post --reply-to、followups）、Store、服务端动作。不用浏览器。"""
import json
import subprocess
import sys
import time
from pathlib import Path

import desk
import pytest
from claudedesk.server import ActionError, DeskServer
from claudedesk.store import Store

ROOT = Path(__file__).resolve().parents[1]


def post(d, **kw):
    kw.setdefault("source", "proj")
    return desk.post_message(desk.make_message(**kw), d)


def cli(d, *args, **kw):
    return subprocess.run([sys.executable, str(ROOT / "desk.py"), "--data", str(d), *args],
                          capture_output=True, encoding="utf-8", **kw)


def spawn_wait(d, *args):
    return subprocess.Popen([sys.executable, str(ROOT / "desk.py"), "--data", str(d), "wait", "--followups",
                             "--interval", "0.1", *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")


def until(cond, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def lines(p):
    return [json.loads(x) for x in Path(p).read_text(encoding="utf-8").splitlines() if x.strip()]


def test_wait_followups_wakes_on_its_source_only_and_holds_the_marker(tmp_path):
    d = tmp_path
    a = post(d, kind="answer", title="为什么慢", question="为什么这么慢？", body="因为……", source="s1")
    b = post(d, kind="answer", title="别的会话", body="x", source="s2")
    p = spawn_wait(d, "--source", "s1", "--timeout", "30")
    try:
        assert until(lambda: desk.listening_sources(["s1", "s2"], d) == {"s1"})  # 等的时候挂着"在听"标记，只标 s1
        desk.write_followup(desk.find_message(b, d), "别的来源的追问", d)
        time.sleep(0.8)
        assert p.poll() is None  # 别的来源的追问不叫醒它
        desk.write_followup(desk.find_message(a, d), "那换成 B 呢？", d)
        out, err = p.communicate(timeout=10)
    finally:
        p.kill()
    assert p.returncode == 0, err
    got = json.loads(out.strip())
    assert got["msg"] == a and got["title"] == "为什么慢" and got["question"] == "为什么这么慢？"
    assert got["text"] == "那换成 B 呢？" and got["source"] == "s1" and got["id"] and got["ts"]
    assert until(lambda: not desk.listening_sources(["s1"], d))  # 退出就放掉标记
    recs = lines(d / desk.FOLLOWUPS)
    assert {"delivered": got["id"]}.items() <= recs[-1].items()  # 交出去之前记了一条"送达"
    assert not (d / desk.RESPONSES).exists()  # 追问不进 responses.jsonl


def test_wait_followups_times_out_and_releases_the_marker(tmp_path):
    post(tmp_path, kind="answer", title="a", body="x", source="s1")
    t0 = time.monotonic()
    r = cli(tmp_path, "wait", "--followups", "--source", "s1", "--timeout", "0.6", "--interval", "0.1", timeout=20)
    assert r.returncode == 2 and "timeout" in r.stderr and time.monotonic() - t0 < 10
    assert not desk.listening_sources(["s1"], tmp_path)
    r = cli(tmp_path, "wait", "--followups", timeout=20)
    assert r.returncode == 2 and "--source" in r.stderr  # 没给来源：参数错误


def test_pending_followup_is_delivered_once_even_with_two_listeners(tmp_path):
    """会话没在听时（比如正在回答上一条）用户又追问了：下一次挂上 wait 立刻拿到；交过的不会再交给别的 wait。"""
    d = tmp_path
    a = post(d, kind="answer", title="a", body="x", source="s1")
    desk.write_followup(desk.find_message(a, d), "第一条", d)
    desk.write_followup(desk.find_message(a, d), "第二条", d)
    r1 = cli(d, "wait", "--followups", "--source", "s1", "--timeout", "5", timeout=20)
    r2 = cli(d, "wait", "--followups", "--source", "s1", "--timeout", "5", timeout=20)
    r3 = cli(d, "wait", "--followups", "--source", "s1", "--timeout", "0.5", "--interval", "0.1", timeout=20)
    assert [json.loads(r1.stdout)["text"], json.loads(r2.stdout)["text"]] == ["第一条", "第二条"]  # 一次一条，从早到晚
    assert r3.returncode == 2
    # --since 晚于追问：不算
    desk.write_followup(desk.find_message(a, d), "第三条", d)
    r4 = cli(d, "wait", "--followups", "--source", "s1", "--since", "2999-01-01T00:00:00+08:00",
             "--timeout", "0.5", "--interval", "0.1", timeout=20)
    assert r4.returncode == 2


def test_followup_already_answered_in_chat_is_not_delivered(tmp_path):
    d = tmp_path
    a = post(d, kind="answer", title="a", body="x", source="s1")
    desk.write_followup(desk.find_message(a, d), "粘到对话里问过了", d)
    r = cli(d, "post", "--kind", "answer", "--source", "s1", "--title", "答追问", "--body", "y", "--no-launch",
            "--reply-to", a, "--question", "粘到对话里问过了", "--repo", "r")
    assert r.returncode == 0, r.stderr
    r = cli(d, "wait", "--followups", "--source", "s1", "--timeout", "0.5", "--interval", "0.1", timeout=20)
    assert r.returncode == 2


def test_followups_never_wake_wait_id(tmp_path):
    d = tmp_path
    a = post(d, kind="answer", title="a", body="x", source="s1")
    desk.write_followup(desk.find_message(a, d), "追问", d)
    r = cli(d, "wait", "--id", a, "--timeout", "0.5", "--interval", "0.1", timeout=20)
    assert r.returncode == 2
    store = Store(d)
    store.poll()
    q = post(d, kind="decision", title="选？", options=["甲", "乙"], source="s1")
    store.poll()
    with pytest.raises(ValueError, match="还在等你回复"):  # 还没回复的决定：先回复才能追问
        store.add_followup(q, "决定还没回复")
    assert not (d / desk.RESPONSES).exists()


def test_followups_on_handled_decisions_and_info(tmp_path):
    """回复过的决定（选了、标为已解决、跳过、在对话里 close 掉）和通知都能追问；wait --followups 带上当时的回复。"""
    d = tmp_path
    chosen = post(d, kind="decision", title="选哪个？", options=["甲", "乙"], source="s1")
    resolved = post(d, kind="decision", title="清理旧环境？", options=["删", "留"], source="s1")
    skipped = post(d, kind="decision", title="跳过的", options=["x"], source="s1")
    closed = post(d, kind="decision", title="对话里答了", options=["x"], source="s1")
    info = post(d, kind="info", title="测试跑完了", body="3 个失败", source="s1")
    store = Store(d)
    store.poll()
    store.submit(chosen, "乙", "顺便改 README", 2)
    store.resolve([resolved])
    store.archive([skipped])
    assert cli(d, "close", "--id", closed, "--text", "用户在对话里选了 x").returncode == 0
    store.poll()

    def wake(mid, text):
        store.add_followup(mid, text)
        r = cli(d, "wait", "--followups", "--source", "s1", "--timeout", "5", timeout=20)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout)

    got = wake(chosen, "乙要多久？")
    assert (got["msg"], got["kind"], got["choice"], got["reply_text"], got["text"]) == (chosen, "decision", "乙", "顺便改 README", "乙要多久？")
    assert "resolved" not in got and "dismissed" not in got
    got = wake(resolved, "你那边也清了吗？")
    assert got["kind"] == "decision" and got["resolved"] is True and got["choice"] is None
    assert wake(skipped, "为什么要问这个？")["dismissed"] is True
    assert wake(closed, "再确认一下")["closed_by"] == "claude"
    got = wake(info, "哪 3 个？")
    assert got["kind"] == "info" and "choice" not in got and got["title"] == "测试跑完了"
    assert store.detail(chosen)["followups"][0]["text"] == "乙要多久？"
    assert len(desk.read_all(d / desk.RESPONSES)) == 4  # 追问不写回复


def test_parent_gone_listener_exits(tmp_path):
    """会话的 shell 被杀了、wait 却还在：它不能继续占着"在听"、把追问领走。"""
    code = (f"import subprocess, sys, time; subprocess.Popen([sys.executable, {str(ROOT / 'desk.py')!r}, '--data', "
            f"{str(tmp_path)!r}, 'wait', '--followups', '--source', 's1', '--timeout', '40']); time.sleep(3)")
    subprocess.run([sys.executable, "-c", code], timeout=20)
    assert until(lambda: desk.listening_sources(["s1"], tmp_path) == {"s1"}, timeout=2)  # 父进程退出时它还在听
    assert until(lambda: not desk.listening_sources(["s1"], tmp_path), timeout=15)


def test_post_reply_to_and_followups_listing(tmp_path):
    d = tmp_path
    a = post(d, kind="answer", title="原回答", body="x", source="s1")
    f1 = desk.write_followup(desk.find_message(a, d), "第一问", d)
    f2 = desk.write_followup(desk.find_message(a, d), "第二问", d)
    # 用追问 id 也行：记下 reply_to = 回答、followup_id，--question 默认是追问原文
    r = cli(d, "post", "--kind", "answer", "--source", "s1", "--title", "答第二问", "--body", "y", "--no-launch",
            "--reply-to", f2["id"], "--repo", "r")
    assert r.returncode == 0, r.stderr
    m = lines(d / desk.INBOX)[-1]
    assert m["reply_to"] == a and m["followup_id"] == f2["id"] and m["question"] == "第二问"
    r = cli(d, "post", "--kind", "answer", "--source", "s1", "--title", "x", "--body", "y", "--no-launch",
            "--reply-to", "no-such-id", "--repo", "r")
    assert r.returncode == 1 and "--reply-to" in r.stderr
    _claim = cli(d, "wait", "--followups", "--source", "s1", "--timeout", "5", timeout=20)
    assert json.loads(_claim.stdout)["id"] == f1["id"]
    r = cli(d, "followups", "--json")
    rows = {x["id"]: x for x in map(json.loads, r.stdout.splitlines())}
    assert rows[f1["id"]]["status"] == "delivered" and rows[f2["id"]]["status"] == "answered"
    r = cli(d, "followups", "--source", "s1")
    assert "已送达" in r.stdout and "已回答" in r.stdout and "第一问" in r.stdout
    assert cli(d, "followups", "--source", "nobody").stdout == ""
    assert cli(d, "list").returncode == 0


def test_pair_followups_rules():
    f = lambda i, ts, text: {"id": i, "ts": ts, "text": text}  # noqa: E731
    r = lambda i, ts, q="", fid="": {"id": i, "ts": ts, "question": q, "followup_id": fid}  # noqa: E731
    fus = [f("f1", "2026-10-14T10:00:00+08:00", "甲"), f("f2", "2026-10-14T10:01:00+08:00", "乙"),
           f("f3", "2026-10-14T10:02:00+08:00", "丙")]
    # 写明 followup_id 的先配；question 和原文一样的其次；剩下的按时间配最早的
    out = desk.pair_followups(fus, [r("r1", "2026-10-14T10:05:00+08:00"), r("r2", "2026-10-14T10:06:00+08:00", q="丙"),
                                    r("r3", "2026-10-14T10:07:00+08:00", fid="f1")])
    assert {k: v["id"] for k, v in out.items()} == {"f1": "r3", "f3": "r2", "f2": "r1"}
    assert desk.pair_followups(fus, [r("r0", "2026-10-14T09:00:00+08:00")]) == {}  # 追问之前发的不算回应


def test_listener_marker_in_process(tmp_path):
    with desk.hold_listener("s1", tmp_path) as ok1, desk.hold_listener("s1", tmp_path) as ok2:
        assert ok1 and ok2  # 同一来源可以有两个
        assert desk.listening_sources(["s1", "s2"], tmp_path) == {"s1"}
        assert not desk.listening_sources(["s1"], tmp_path / "other")  # 别的数据目录不算
    assert desk.listening_sources(["s1"], tmp_path) == set()


def test_store_followups_detail_links_and_listening(tmp_path):
    d = tmp_path
    a = post(d, kind="answer", title="原回答", question="原问题", body="x", source="s1")
    other = post(d, kind="answer", title="不相干", body="x", source="s2")
    store = Store(d)
    store.poll()
    s = {m["id"]: m for m in store.summaries()}
    assert s[a]["listening"] is False and "followup_pending" not in s[a] and "fstate" not in s[a]
    assert store.detail(a)["followups"] == [] and store.detail(a)["replies"] == []
    with pytest.raises(ValueError, match="不能为空"):
        store.add_followup(a, "   ")
    with pytest.raises(KeyError):
        store.add_followup("nope", "x")
    rec = store.add_followup(a, "  那 B 呢？ ")
    assert rec["text"] == "那 B 呢？" and rec["msg"] == a and rec["source"] == "s1" and rec["title"] == "原回答"
    assert lines(d / desk.FOLLOWUPS)[-1]["id"] == rec["id"]
    store.poll()  # 自己写的那行读回来不会重复
    det = store.detail(a)
    assert [(f["text"], f["delivered"], f["reply"]) for f in det["followups"]] == [("那 B 呢？", None, None)]
    s = {m["id"]: m for m in store.summaries()}
    assert s[a]["followup_pending"] is True and s[a]["fstate"] == "1.0.0" and "fstate" not in s[other]

    # 会话挂上监听：listening 变 True（列一次管道）
    with desk.hold_listener("s1", d):
        assert store.refresh_listening(force=True) is True
        assert {m["id"]: m for m in store.summaries()}[a]["listening"] is True
        assert store.detail(a)["listening"] is True and store.detail(other)["listening"] is False
    store.refresh_listening(force=True)
    assert store.detail(a)["listening"] is False

    # 会话领走（送达）再回应：两边都连上
    desk.append_jsonl(d / desk.FOLLOWUPS, {"delivered": rec["id"], "ts": "2026-10-14T10:00:00.000+08:00"})
    store.poll()
    det = store.detail(a)  # delivered：什么时候交给会话的
    assert det["followups"][0]["delivered"] == "2026-10-14T10:00:00+08:00" and det["fstate"] == "1.1.0"
    rep = desk.post_message(desk.make_message("answer", "s1", "B 也行", "因为……", question="那 B 呢？", reply_to=a), d)
    store.poll()
    det = store.detail(a)
    assert det["followups"][0]["reply"] == {"id": rep, "title": "B 也行"}
    assert det["replies"] == [{"id": rep, "title": "B 也行", "ts": det["replies"][0]["ts"], "paired": True}]
    s = {m["id"]: m for m in store.summaries()}
    assert s[a]["followup_pending"] is False and s[a]["fstate"] == "1.1.1" and s[rep]["reply_to"] == a
    assert store.detail(rep)["reply_ref"] == {"id": a, "title": "原回答", "kind": "answer", "exists": True, "text": "那 B 呢？"}
    # 回应没带 --question：从配对里找出追问原文；原回答删了：exists False
    rec2 = store.add_followup(a, "还有 C？")
    rep2 = desk.post_message(desk.make_message("answer", "s1", "C 不行", "x", reply_to=a), d)
    store.poll()
    assert store.detail(rep2)["reply_ref"]["text"] == "还有 C？"
    assert store.detail(a)["followups"][1]["id"] == rec2["id"]
    store.delete([a])
    assert store.detail(rep)["reply_ref"]["exists"] is False


def test_server_followup_action(tmp_path):
    d = tmp_path
    a = post(d, kind="answer", title="原回答", body="x")
    q = post(d, kind="decision", title="选？", options=["甲"])
    i = post(d, kind="info", title="通知", body="x")
    store = Store(d)
    store.poll()
    server = DeskServer(store)
    try:
        rec = server.action({"action": "followup", "id": a, "text": "再说说？"})
        assert rec["msg"] == a and rec["text"] == "再说说？"
        for body, msg in (({"action": "followup", "id": a, "text": " "}, "追问不能为空"),
                          ({"action": "followup", "id": q, "text": "x"}, "这条决定还在等你回复：先在上面选择或写回复，回复之后才能追问"),
                          ({"action": "followup", "id": "nope", "text": "x"}, "没有这条消息")):
            with pytest.raises(ActionError) as e:
                server.action(body)
            assert str(e.value) == msg
        assert [f["text"] for f in store.detail(a)["followups"]] == ["再说说？"]
        assert server.action({"action": "followup", "id": i, "text": "通知也能问"})["msg"] == i
        server.action({"action": "reply", "id": q, "choice": "甲", "text": ""})
        assert server.action({"action": "followup", "id": q, "text": "回复过的决定能追问"})["msg"] == q
    finally:
        server.httpd.server_close()
