"""第四轮集成测试（不用浏览器）：追问文件写坏了、关掉的标签和计数 / 自动找回、追问协议的边角。"""
import json
import subprocess
import sys
import time
from pathlib import Path

import desk
from claudedesk.server import DeskServer
from claudedesk.store import OTHER_TAB, Store

ROOT = Path(__file__).resolve().parents[1]


def post(d, **kw):
    kw.setdefault("source", "proj")
    return desk.post_message(desk.make_message(**kw), d)


def cli(d, *args):
    return subprocess.run([sys.executable, str(ROOT / "desk.py"), "--data", str(d), *args],
                          capture_output=True, encoding="utf-8", timeout=60)


def until(cond, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_followup_records_with_wrong_types_do_not_crash_the_cli(tmp_path):
    """followups.jsonl 里有手改坏的行（id 是列表、msg 是对象）：desk.py followups / wait --followups 照常工作，好的那条照样交出去。
    以前 read_followups 原样返回，拿 id / msg 去查集合时 TypeError: unhashable type。"""
    d = tmp_path
    mid = post(d, kind="answer", title="m", body="x", source="M")
    good = desk.write_followup({"id": mid, "source": "M", "title": "m"}, "好的那条", d)
    with open(d / desk.FOLLOWUPS, "ab") as f:
        f.write(json.dumps({"id": ["x"], "msg": mid, "source": "M", "ts": desk.now_ts(), "text": "id 是列表"}).encode() + b"\n")
        f.write(json.dumps({"id": "fx", "msg": {"a": 1}, "source": "M", "ts": desk.now_ts(), "text": "msg 是对象"}).encode() + b"\n")
    r = cli(d, "followups", "--json")
    assert r.returncode == 0, r.stderr
    assert good["id"] in r.stdout
    r = cli(d, "wait", "--followups", "--source", "M", "--timeout", "5", "--interval", "0.05")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["text"] == "好的那条"
    st = Store(d)
    st.poll()  # 程序这边本来就不怕
    assert [f["text"] for f in st.detail(mid)["followups"]][0] == "好的那条"


def test_killed_listener_releases_the_marker_and_the_next_one_gets_the_followup(tmp_path):
    d = tmp_path
    mid = post(d, kind="answer", title="a", body="x", source="K")
    w = subprocess.Popen([sys.executable, str(ROOT / "desk.py"), "--data", str(d), "wait", "--followups", "--source", "K",
                          "--interval", "0.05"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
    try:
        assert until(lambda: desk.listening_sources(["K"], d) == {"K"})
    finally:
        w.kill()  # 会话被强行结束：不走 finally，标记靠系统放掉
        w.communicate(timeout=10)
    assert until(lambda: desk.listening_sources(["K"], d) == set(), 5)
    st = Store(d)
    st.poll()
    st.add_followup(mid, "杀掉之后的追问")
    assert not desk.read_followups(d)[1]  # 死掉的那个没领走任何东西
    r = cli(d, "wait", "--followups", "--source", "K", "--timeout", "5", "--interval", "0.05")
    assert r.returncode == 0 and json.loads(r.stdout)["text"] == "杀掉之后的追问"


def test_reply_to_a_followup_reopens_the_closed_tab_and_counts_follow(tmp_path):
    """追问的回答回到一个关掉的标签：标签回来、计数算上它；回答在别的仓库：原来那个标签还关着。"""
    d = tmp_path
    a = post(d, kind="answer", title="甲的回答", body="x", repo="alpha", source="alpha")
    post(d, kind="answer", title="乙", body="x", repo="beta", source="beta")
    st = Store(d)
    st.poll()
    st.mark_read([a])
    f = st.add_followup(a, "再说说")
    st.hide_project("alpha")
    st.hide_project("beta")
    assert st.counts()["unread"] == 0 and st.counts()["total"] == 0
    r = cli(d, "post", "--kind", "answer", "--source", "alpha", "--repo", "gamma", "--title", "别处回的", "--body", "x",
            "--reply-to", f["id"], "--no-launch")
    assert r.returncode == 0, r.stderr
    st.poll()
    assert st.hidden_projects == {"alpha", "beta"}  # 回答落在 gamma：alpha 还关着
    assert st.counts()["unread"] == 1
    r = cli(d, "post", "--kind", "answer", "--source", "alpha", "--repo", "alpha", "--title", "原处回的", "--body", "x",
            "--reply-to", a, "--no-launch")
    assert r.returncode == 0, r.stderr
    st.poll()
    assert st.hidden_projects == {"beta"}
    assert st.counts()["unread"] == 2 and st.counts()["total"] == 3
    srv = DeskServer(st)
    try:
        snap = srv.snapshot()
        assert snap["hidden_projects"] == ["beta"] and snap["counts"] == st.counts()
    finally:
        srv.httpd.server_close()
    assert OTHER_TAB not in st.hidden_projects
