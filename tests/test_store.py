import json

import desk
import pytest
from claudedesk.store import DISMISS_TEXT, OTHER_TAB, Store, plain_summary


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


def test_resolve_text_says_handled_and_every_decision_allows_text(tmp_path):
    """标为已处理：等待的会话收到的话说"已处理（可能已经在对话里处理）"；决定一律能写补充说明（旧消息没写 allow_text 也一样）。"""
    from claudedesk.store import RESOLVE_TEXT, normalize
    a = post(tmp_path, kind="decision", options=["A"])
    s = Store(tmp_path)
    s.poll()
    s.resolve([a])
    assert desk.read_all(tmp_path / desk.RESPONSES)[0]["text"] == RESOLVE_TEXT
    assert RESOLVE_TEXT == "（用户在 ClaudeDesk 里把这条标为已处理：已经处理好了（可能已经在对话里直接处理），不需要你再按选项做什么）"
    assert normalize({"id": "x", "kind": "decision", "title": "t", "options": ["A"]})["allow_text"] is True
    assert normalize({"id": "y", "kind": "decision", "title": "t", "options": ["A"], "allow_text": False})["allow_text"] is True
    assert normalize({"id": "z", "kind": "answer", "title": "t"})["allow_text"] is False
    assert s.detail(a)["allow_text"] is True


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


def test_malformed_record_does_not_drop_later_ones(tmp_path):
    first = post(tmp_path, kind="info", title="before")
    s = Store(tmp_path)
    s.poll()
    with open(tmp_path / desk.INBOX, "a", encoding="utf-8") as f:  # 手写 / 别的工具写的记录：类型不对
        f.write(json.dumps({"id": "bad-1", "kind": "decision", "title": "x", "options": 5}) + "\n")
        f.write(json.dumps({"id": "bad-2", "kind": "info", "title": "y", "options": "A::x"}) + "\n")
    later = post(tmp_path, kind="decision", title="posted right after", options=["A"])
    s.poll()
    assert later in s.msgs and s.msgs["bad-1"]["options"] == [] and s.msgs["bad-2"]["options"] == []
    cold = Store(tmp_path)  # 冷启动同样不丢
    cold.poll()
    assert {first, later, "bad-1", "bad-2"} <= set(cold.msgs)
    assert s.delete([first]) == 1  # 压缩也不会被这种记录卡住；它们原样保留
    raw = (tmp_path / desk.INBOX).read_text(encoding="utf-8")
    assert first not in raw and "bad-1" in raw and later in raw


def test_poll_skips_record_that_fails_to_normalize(tmp_path, monkeypatch):
    from claudedesk import store as store_mod

    a = post(tmp_path, kind="info", title="a")
    b = post(tmp_path, kind="info", title="b")
    real = store_mod.normalize

    def flaky(r):
        if r.get("id") == a:
            raise TypeError("boom")
        return real(r)

    monkeypatch.setattr(store_mod, "normalize", flaky)
    s = Store(tmp_path)
    s.poll()
    assert b in s.msgs and a not in s.msgs


def test_poll_and_submit_tolerate_permission_error(tmp_path, monkeypatch):
    """compact() 换文件的一瞬间，别的读者 open 会 PermissionError：这一轮当没有新内容，下一轮照常读到。"""
    a = post(tmp_path, kind="decision", options=["A", "B"])
    c = post(tmp_path, kind="decision", options=["A", "B"])
    s = Store(tmp_path)
    s.poll()

    def boom():
        raise PermissionError(13, "x")

    with monkeypatch.context() as mp:  # submit 后面那次 poll 出错：回复已经写好，不算失败
        mp.setattr(s, "poll", boom)
        assert s.submit(c, "A", "")["choice"] == "A"
    b = post(tmp_path, kind="info")
    real = desk.read_jsonl

    def busy(path, *args, **kw):
        if str(path).endswith(desk.INBOX):
            raise PermissionError(13, "being replaced")
        return real(path, *args, **kw)

    monkeypatch.setattr(desk, "read_jsonl", busy)
    s.poll()  # 不抛
    assert b not in s.msgs
    rec = s.submit(a, "B", "")  # 回复已经写好：后面的 poll 读不到 inbox 也不算提交失败
    assert rec["choice"] == "B" and [r["id"] for r in desk.read_all(tmp_path / desk.RESPONSES)] == [c, a]
    monkeypatch.setattr(desk, "read_jsonl", real)
    s.poll()
    assert b in s.msgs and a in s.responses


def test_failed_compaction_is_retried_with_backoff(tmp_path, monkeypatch):
    import os
    import time

    keep = post(tmp_path, kind="answer", title="keep")
    gone = post(tmp_path, kind="answer", title="delete me")
    s = Store(tmp_path)
    s.poll()
    real = os.replace

    def held(src, dst):  # 例如别的程序开着 inbox.jsonl（没给 FILE_SHARE_DELETE）
        if str(dst).endswith(desk.INBOX):
            raise PermissionError(13, "held open")
        return real(src, dst)

    monkeypatch.setattr(os, "replace", held)
    t0 = time.monotonic()
    assert s.delete([gone]) == 1
    assert time.monotonic() - t0 < 1.5  # 失败也不长时间占着 data/.lock
    assert gone in (tmp_path / desk.INBOX).read_text(encoding="utf-8")
    assert [m["id"] for m in s.visible()] == [keep]  # 照样不显示
    assert s.compact_if_due() is None  # 还没到重试时间
    s._compact_at = 0
    assert s.compact_if_due() is False
    assert 8 < s._compact_at - time.monotonic() <= 10.001  # 第二次失败：间隔翻倍（Windows 时钟粗，留一点浮点余量）
    s.save_state()

    monkeypatch.setattr(os, "replace", real)
    s2 = Store(tmp_path)  # 重启后（启动时第一轮）也会补上
    s2.poll()
    assert s2.compact_if_due() is True
    assert gone not in (tmp_path / desk.INBOX).read_text(encoding="utf-8")
    assert s2.compact_if_due() is None and [m["id"] for m in s2.visible()] == [keep]
    s._compact_at = 0  # 旧实例：文件里已经没有了，内存里也清掉，之后不再反复尝试
    assert s.compact_if_due() is True and s.compact_if_due() is None


def test_submit_choice_index(tmp_path):
    a = post(tmp_path, kind="decision", options=["继续::按方案 A", "继续::按方案 B", "停"])
    b, c, d = (post(tmp_path, kind="decision", options=["X", "Y"]) for _ in range(3))
    s = Store(tmp_path)
    s.poll()
    with pytest.raises(ValueError, match="对不上"):
        s.submit(a, "停", "", choice_index=2)
    for bad in (0, 4, "x", True, 1.5, -1):
        with pytest.raises(ValueError):
            s.submit(a, "继续", "", choice_index=bad)
    assert a not in s.responses
    rec = s.submit(a, "继续", "", choice_index=2)  # 两个选项同名：按点的那个记
    assert rec["choice"] == "继续" and rec["choice_index"] == 2
    assert s.submit(b, "Y", "")["choice_index"] == 2  # 旧界面只发名字
    assert s.submit(c, None, "", choice_index="1")["choice"] == "X"  # 只给序号：补上名字
    with pytest.raises(ValueError):
        s.submit(d, "Z", "")
    got = {r["id"]: r.get("choice_index") for r in desk.read_all(tmp_path / desk.RESPONSES)}
    assert got == {a: 2, b: 2, c: 1}


def test_concurrent_save_state_keeps_newest(tmp_path):
    import threading

    ids = [post(tmp_path, kind="answer", title=f"t{i}") for i in range(50)]
    s = Store(tmp_path)
    s.poll()
    for _ in range(20):
        with s.lock:
            s.read = set(ids[:5])
        t = threading.Thread(target=s.save_state)
        t.start()
        with s.lock:
            s.read = set(ids)
        s.save_state()
        t.join()
        st = json.loads((tmp_path / desk.STATE).read_text(encoding="utf-8"))
        assert len(st["read"]) == len(ids)


def test_closed_tabs_leave_counts_and_come_back_on_a_new_message(tmp_path):
    a = post(tmp_path, kind="decision", options=["A"], repo="alpha", priority="high")
    b = post(tmp_path, kind="answer", repo="beta")
    o = post(tmp_path, kind="info", source="随手记")  # 没认出仓库：在"未归类"
    s = Store(tmp_path)
    s.poll()
    assert s.counts()["unread"] == 3 and s.counts()["open"] == 1 and s.tab_key(s.msgs[o]) == OTHER_TAB
    changed = []
    s.on_changed.append(lambda: changed.append(1))
    v = s.version
    assert s.hide_project("alpha") == ["alpha"]
    assert s.version > v and changed  # 长轮询、托盘图标都会被叫醒
    c = s.counts()
    assert (c["open"], c["urgent"], c["unread"], c["total"]) == (0, 0, 2, 2)  # 托盘 / 任务栏的数字跟着掉
    assert s.hide_project("alpha") == ["alpha"] and s.hide_project(OTHER_TAB) == [OTHER_TAB, "alpha"]
    assert s.counts()["unread"] == 1
    with pytest.raises(ValueError):
        s.hide_project("  ")
    s.save_state()
    assert json.loads((tmp_path / desk.STATE).read_text(encoding="utf-8"))["hidden_projects"] == [OTHER_TAB, "alpha"]
    s2 = Store(tmp_path)  # 重启后还关着
    s2.poll()
    assert s2.hidden_projects == {OTHER_TAB, "alpha"} and s2.counts()["unread"] == 1
    # 托盘的"全部标为已读"、"归档所有已处理的"不动关掉的标签
    s2.mark_all_read()
    assert s2.is_unread(s2.msgs[a]) and s2.is_unread(s2.msgs[o]) and not s2.is_unread(s2.msgs[b])
    s2.mark_read([o])
    s2.archive_handled()
    assert s2.archived == {b}
    # 关掉的项目来了新消息：标签自动回来，照常通知、计数
    arrived = []
    s2.on_arrived.append(arrived.extend)
    n = post(tmp_path, kind="decision", options=["X"], repo="alpha")
    s2.poll()
    assert [m["id"] for m in arrived] == [n]
    assert s2.hidden_projects == {OTHER_TAB} and s2.counts()["open"] == 2
    # 旧消息被重读（删除后压缩重写 inbox）不算新到：关着的"未归类"不会回来
    s2.delete([b])
    assert b not in s2.msgs and s2.hidden_projects == {OTHER_TAB}
    assert s2.show_project(OTHER_TAB) == [] and s2.counts()["unread"] == 2  # o 刚标过已读
    s2.hide_project("alpha")
    s2.hide_project(OTHER_TAB)
    assert s2.show_project() == [] and s2.counts()["unread"] == 2  # 全部找回


def test_merging_and_closed_tabs_follow_the_resolved_name(tmp_path):
    a = post(tmp_path, kind="answer", repo="alpha")
    post(tmp_path, kind="answer", repo="beta")
    g = post(tmp_path, kind="answer", repo="gamma")
    s = Store(tmp_path)
    s.poll()
    # 关掉的 alpha 归到开着的 beta：beta 的消息不会跟着不见，alpha 的消息跟着 beta 显示；alpha 的"已关闭"作废
    s.hide_project("alpha")
    s.set_alias("alpha", "beta")
    assert s.hidden_projects == set() and s.counts()["unread"] == 3 and s.tab_key(s.msgs[a]) == "beta"
    # 开着的 gamma 归到关掉的 beta：beta 回来（刚明确放进去的，不能一归过去就不见了）
    s.hide_project("beta")
    assert s.counts()["unread"] == 1
    s.set_alias("gamma", "beta")
    assert s.hidden_projects == set() and s.counts()["unread"] == 3
    # 关掉 beta：归过来的 alpha、gamma 一起关；把 gamma 拆出来，它自己回来，beta 还关着
    s.hide_project("beta")
    assert s.counts()["unread"] == 0
    s.set_alias("gamma", "")
    assert s.hidden_projects == {"beta"} and s.counts()["unread"] == 1 and s.tab_key(s.msgs[g]) == "gamma"
