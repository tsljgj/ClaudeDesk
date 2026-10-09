import json

import desk
import pytest
from claudedesk.store import DISMISS_TEXT, Store, plain_summary


def post(d, **kw):
    kw.setdefault("source", "proj")
    kw.setdefault("title", "t")
    return desk.post_message(desk.make_message(**kw), d)


def test_poll_reply_and_counts(tmp_path):
    a = post(tmp_path, kind="decision", options=["A::x", "B::y"])
    b = post(tmp_path, kind="answer", body="hello")
    s = Store(tmp_path)
    arrived = []
    s.on_arrived.append(arrived.extend)
    s.poll()
    assert {m["id"] for m in arrived} == {a, b}
    assert s.counts()["open"] == 1 and s.counts()["unread"] == 2
    s.submit(a, "B", "note")
    rec = [r for r in desk.read_all(tmp_path / desk.RESPONSES) if r["id"] == a][0]
    assert rec["choice"] == "B" and rec["choice_index"] == 2 and rec["text"] == "note"
    with pytest.raises(FileExistsError):
        s.submit(a, "A", "")
    with pytest.raises(ValueError):
        s.submit(b, "nope", "")
    assert s.counts()["open"] == 0


def test_archive_hides_and_dismisses_open_decision(tmp_path):
    a = post(tmp_path, kind="decision", options=["A"])
    b = post(tmp_path, kind="info")
    s = Store(tmp_path)
    s.poll()
    assert s.archive([a, b]) == 2
    assert [m["id"] for m in s.visible()] == []
    assert {m["id"] for m in s.visible(archived=True)} == {a, b}
    resp = desk.read_all(tmp_path / desk.RESPONSES)
    assert resp[0]["id"] == a and resp[0]["dismissed"] is True and resp[0]["text"] == DISMISS_TEXT
    assert s.archive([a], on=False) == 1
    assert [m["id"] for m in s.visible()] == [a]
    s.save_state()
    st = json.loads((tmp_path / desk.STATE).read_text(encoding="utf-8"))
    assert st["archived"] == [b]
    s2 = Store(tmp_path)  # 状态能恢复
    s2.poll()
    assert [m["id"] for m in s2.visible(archived=True)] == [b]


def test_delete_compacts_inbox(tmp_path):
    ids = [post(tmp_path, kind="answer", title=f"m{i}") for i in range(3)]
    (tmp_path / desk.INBOX).open("ab").write(b"{broken\n")  # 坏行原样保留
    s = Store(tmp_path)
    s.poll()
    assert s.delete([ids[1]]) == 1
    raw = (tmp_path / desk.INBOX).read_text(encoding="utf-8")
    assert ids[1] not in raw and ids[0] in raw and ids[2] in raw and "{broken" in raw
    assert sorted(m["id"] for m in s.visible()) == sorted([ids[0], ids[2]])
    # 删除后还能继续追加，Store 能读到新的
    c = post(tmp_path, kind="info")
    s.poll()
    assert c in s.msgs


def test_archive_handled_only_takes_read_and_closed(tmp_path):
    a = post(tmp_path, kind="decision", options=["A"])
    b = post(tmp_path, kind="answer")
    post(tmp_path, kind="answer")
    s = Store(tmp_path)
    s.poll()
    s.mark_read([a, b])
    assert s.archive_handled() == 1  # a 还开着，c 没读
    assert s.visible(archived=True)[0]["id"] == b


def test_wait_change_wakes(tmp_path):
    import threading

    s = Store(tmp_path)
    s.poll()
    v = s.version
    threading.Timer(0.2, lambda: (post(tmp_path, kind="info"), s.poll())).start()
    assert s.wait_change(v, 5) > v


def test_plain_summary():
    assert plain_summary("# 标题\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n```py\nx\n```\n$$x^2$$ [链接](http://x)") \
        == "标题 a b 1 2 [公式] 链接"


def test_resolve_writes_reply_and_marks_read(tmp_path):
    a = post(tmp_path, kind="decision", options=["A"])
    b = post(tmp_path, kind="answer")
    s = Store(tmp_path)
    s.poll()
    assert s.resolve([a, b]) == 1
    r = desk.read_all(tmp_path / desk.RESPONSES)
    assert len(r) == 1 and r[0]["id"] == a and r[0]["resolved"] is True and r[0]["choice"] is None
    assert not s.is_unread(s.msgs[a]) and not s.is_unread(s.msgs[b])
    assert s.summary(s.msgs[a])["resolved"] and not s.summary(s.msgs[a])["open"]
    assert s.resolve([a]) == 0  # 已经有回复：不再写


def test_project_of_and_scoped_bulk(tmp_path):
    from claudedesk.store import project_of
    assert project_of("osworld") == "osworld" and project_of("osworld/data") == "osworld"
    assert project_of("") == "unknown" and project_of("/x") == "/x"
    a = post(tmp_path, kind="answer", source="osworld")
    b = post(tmp_path, kind="answer", source="osworld/eval")
    c = post(tmp_path, kind="answer", source="cn-equity-research")
    s = Store(tmp_path)
    s.poll()
    assert s.summary(s.msgs[b])["project"] == "osworld"
    assert s.mark_all_read("osworld") == 2
    assert s.is_unread(s.msgs[c]) and not s.is_unread(s.msgs[a])
    assert s.archive_handled("cn-equity-research") == 0
    assert s.archive_handled("osworld") == 2 and c not in s.archived
