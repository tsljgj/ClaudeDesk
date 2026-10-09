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
    assert project_of("webapp") == "webapp" and project_of("webapp/data") == "webapp"
    assert project_of("") == "unknown" and project_of("/x") == "/x"
    a = desk.post_message(desk.make_message("answer", "eval-run", "t", repo="webapp"), tmp_path)
    b = post(tmp_path, kind="answer", source="webapp/eval")  # 旧消息：能对上已知仓库
    c = desk.post_message(desk.make_message("answer", "x", "t", repo="acme-data-pipeline"), tmp_path)
    s = Store(tmp_path)
    s.poll()
    assert s.summary(s.msgs[a])["project"] == "webapp" and s.summary(s.msgs[a])["project_kind"] == "repo"
    assert s.summary(s.msgs[b])["project"] == "webapp"
    assert s.mark_all_read("webapp") == 2
    assert s.is_unread(s.msgs[c]) and not s.is_unread(s.msgs[a])
    assert s.archive_handled("acme-data-pipeline") == 0
    assert s.archive_handled("webapp") == 2 and c not in s.archived


def test_legacy_sources_match_known_repos_or_become_other(tmp_path):
    desk.post_message(desk.make_message("answer", "s", "t", repo="WebApp"), tmp_path)
    old = [post(tmp_path, kind="info", source=src) for src in
           ("webapp-eval", "webapp_runner/2", "WebApp", "随手记", "scratch-notes")]
    s = Store(tmp_path)
    s.poll()
    info = [s.project_info(s.msgs[i]) for i in old]
    assert [(n, k) for n, k, _ in info] == [("WebApp", "repo"), ("WebApp", "repo"), ("WebApp", "repo"),
                                             ("随手记", "other"), ("scratch-notes", "other")]
    # 用户把没认出来的来源归到某个项目；再把那个项目归到另一个，链会被拉平
    s.set_alias("scratch-notes", "acme-data-pipeline")
    assert s.project_info(s.msgs[old[4]])[:2] == ("acme-data-pipeline", "repo")
    s.set_alias("acme-data-pipeline", "WebApp")
    assert s.aliases == {"scratch-notes": "WebApp", "acme-data-pipeline": "WebApp"}
    s.set_alias("scratch-notes", "")
    assert s.project_info(s.msgs[old[4]])[:2] == ("scratch-notes", "other")
    s.save_state()
    assert Store(tmp_path).aliases == {"acme-data-pipeline": "WebApp"}


def test_legacy_matching_uses_discovered_projects(tmp_path):
    old = {src: post(tmp_path, kind="info", source=src) for src in
           ("webapp", "webapp/eval", "WebApp-runner", "acme-data", "acme-data-pipeline", "随便写的")}
    s = Store(tmp_path)
    s.poll()
    assert all(s.project_info(s.msgs[i])[1] == "other" for i in old.values())  # 还不知道有哪些仓库
    s.set_known_projects({"WebApp", "acme-data-pipeline"})
    got = {src: s.project_info(s.msgs[i])[:2] for src, i in old.items()}
    assert got == {"webapp": ("WebApp", "repo"), "webapp/eval": ("WebApp", "repo"),
                   "WebApp-runner": ("WebApp", "repo"), "acme-data": ("acme-data-pipeline", "repo"),
                   "acme-data-pipeline": ("acme-data-pipeline", "repo"), "随便写的": ("随便写的", "other")}
