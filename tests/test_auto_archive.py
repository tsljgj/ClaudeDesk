"""自动归档已处理的：按设置（默认 1 小时）把很久没动静的已读消息收进归档；待决定、没读的、追问了还在等回答的不动。
还有：同一版本的状态快照只算一次摘要；托盘提醒默认不放提示音。"""
import datetime as dt
import json
import sys
import types

import desk
from claudedesk.store import AUTO_ARCHIVE_DEFAULT, Store
from test_server import call, srv  # noqa: F401（srv 是 fixture）


def post(d, ago, **kw):
    kw.setdefault("source", "proj")
    kw.setdefault("title", "t")
    m = desk.make_message(**kw)
    m["ts"] = (dt.datetime.now().astimezone() - ago).isoformat(timespec="milliseconds")
    return desk.post_message(m, d)


H = dt.timedelta(hours=1)


def test_auto_archive_takes_only_old_handled_messages(tmp_path):
    d = tmp_path
    old = post(d, 2 * H, kind="answer", title="旧回答")
    fresh = post(d, dt.timedelta(minutes=10), kind="answer", title="新回答")
    unread = post(d, 2 * H, kind="info", title="没读的")
    open_dec = post(d, 2 * H, kind="decision", title="还在等你", options=["A"])
    asked = post(d, 2 * H, kind="answer", title="追问了")
    s = Store(d)
    s.poll()
    assert AUTO_ARCHIVE_DEFAULT == "1h" and s.setting("auto_archive") is None  # 没设过：按默认 1 小时
    s.read.update([old, fresh, open_dec, asked])
    s.add_followup(asked, "还有呢？")
    s.read_at.pop(asked, None)
    assert s.auto_archive() == 1
    assert old in s.archived and not {fresh, unread, open_dec, asked} & s.archived

    # 刚在界面里打开过的不算旧
    s.archive([old], on=False)
    s.mark_read([old], opened=True)
    assert s.auto_archive() == 0

    # 换成 7 天：两小时前的不动；关掉：一条也不动
    s.set_setting("auto_archive", "7d")
    assert s.auto_archive(now=dt.datetime.now().astimezone() + dt.timedelta(days=1)) == 0
    assert s.auto_archive(now=dt.datetime.now().astimezone() + dt.timedelta(days=8)) == 2  # old 和 fresh
    s.archive([old, fresh], on=False)
    s.set_setting("auto_archive", "off")
    assert s.auto_archive(now=dt.datetime.now().astimezone() + dt.timedelta(days=30)) == 0


def test_auto_archive_if_due_runs_at_most_once_a_minute(tmp_path):
    d = tmp_path
    a = post(d, 2 * H, kind="answer")
    s = Store(d)
    s.poll()
    s.read.add(a)
    assert s.auto_archive_if_due() == 1
    b = post(d, 2 * H, kind="answer")
    s.poll()
    s.read.add(b)
    assert s.auto_archive_if_due() == 0  # 一分钟内不再看
    s._auto_at = 0.0
    assert s.auto_archive_if_due() == 1


def act(server, body):
    status, data = call(server, "POST", "/api/action", body)
    assert status == 200
    return json.loads(data)


def test_auto_archive_setting_goes_through_the_server(srv):  # noqa: F811
    d, store, server = srv
    assert server.settings()["auto_archive"] == "1h"
    r = act(server, {"action": "settings", "values": {"auto_archive": "1d"}})
    assert r["ok"] and r["result"]["auto_archive"] == "1d" and store.setting("auto_archive") == "1d"
    store._auto_at = 1e18
    act(server, {"action": "settings", "values": {"auto_archive": "7d"}})
    assert store._auto_at == 0.0  # 改了档：下一轮就按新的来
    act(server, {"action": "settings", "values": {"auto_archive": "2h"}})  # 不认得的档不收
    assert store.setting("auto_archive") == "7d"


def test_snapshot_reuses_summaries_within_one_version(srv):  # noqa: F811
    d, store, server = srv
    desk.post_message(desk.make_message("answer", "proj", "一条"), d)
    store.poll()
    n = {"calls": 0}
    real = store.summaries

    def counted():
        n["calls"] += 1
        return real()
    store.summaries = counted
    a, b = server.snapshot(), server.snapshot()
    assert n["calls"] == 1 and a["messages"] == b["messages"]
    store.mark_all_read()  # 版本变了：重新算
    c = server.snapshot()
    assert n["calls"] == 2 and c["messages"][0]["unread"] is False


def test_tray_balloon_is_silent_unless_sound_is_on(tmp_path, monkeypatch):
    from claudedesk import app

    sent = []
    win32 = types.SimpleNamespace(NIM_MODIFY=1, NIF_INFO=16)
    monkeypatch.setitem(sys.modules, "pystray._util.win32", win32)
    icon = types.SimpleNamespace(_message=lambda code, flags, **kw: sent.append(("msg", code, flags, kw)),
                                 notify=lambda text, title: sent.append(("notify", text, title)))
    t = app.TrayApp.__new__(app.TrayApp)
    t.store = Store(tmp_path)
    t.icon = icon
    t._balloon("正文", "标题")
    assert sent == [("msg", 1, 16, {"szInfo": "正文", "szInfoTitle": "标题", "dwInfoFlags": app.NIIF_NOSOUND})]
    sent.clear()
    t.store.state.setdefault("app", {})["notify_sound"] = True
    t._balloon("正文", "标题")
    assert sent == [("notify", "正文", "标题")]
