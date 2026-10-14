"""第四轮集成测试（浏览器）：关掉的标签、只看未处理、标为已处理、归档已处理、追问、正文宽度这几样功能互相之间的配合。"""
import threading
import time

import desk
from test_ui import env, post  # noqa: F401（env 是 fixture）
from test_ui_state import wait_until


def start(page, server):
    page.goto(server.url)
    page.wait_for_function("window.deskTest && deskTest.S.version >= 0")
    page.wait_for_selector(".item")


def shown(page, mid):
    page.wait_for_function("id => deskTest.S.shownKey && deskTest.S.shownKey.split('|')[0] === id", arg=mid)


def visible_titles(page):
    return page.evaluate("deskTest.S.visible.map(id => deskTest.S.byId[id].title)")


def test_followup_draft_on_a_handled_decision_survives_polls_and_switching(env):
    """回复过的决定上写了一半的追问：长轮询来了、换到别的再回来都还在。
    以前追问草稿和决定草稿共用 S.drafts[id]：决定有了回复，renderDecision 和 apply 都把"已回复的草稿"删掉，追问草稿跟着没了。"""
    d, store, server, page, errors = env
    dec = post(d, kind="decision", title="决定甲", options=["A", "B"])
    ans = post(d, kind="answer", title="回答乙", body="x")
    store.poll()
    store.submit(dec, "A", "")
    start(page, server)
    page.click(f'.item[data-id="{dec}"]')
    shown(page, dec)
    page.wait_for_selector("#followup:not([hidden])")
    page.click("#fuText")
    page.keyboard.type("我想追问")
    v = page.evaluate("deskTest.S.version")
    post(d, kind="info", title="让长轮询醒来", body="x")
    page.wait_for_function("v => deskTest.S.version > v", arg=v)
    assert page.evaluate(f"deskTest.S.drafts['{dec}'] && deskTest.S.drafts['{dec}'].text") == "我想追问"
    page.click(f'.item[data-id="{ans}"]')
    shown(page, ans)
    assert page.input_value("#fuText") == ""
    page.click(f'.item[data-id="{dec}"]')
    shown(page, dec)
    assert page.input_value("#fuText") == "我想追问"
    page.keyboard.press("Control+Enter")  # 发出去以后草稿才清掉
    page.wait_for_selector("#fuList .fu-item")
    assert [f["text"] for f in desk.read_followups(d)[0]] == ["我想追问"]
    assert page.evaluate(f"deskTest.S.drafts['{dec}']") is None and page.input_value("#fuText") == ""
    assert errors == []


def test_decision_draft_does_not_leak_into_the_followup_box(env):
    """决定还没回复时写的补充说明，决定在别处回复掉以后，不会变成追问框里的草稿。"""
    d, store, server, page, errors = env
    dec = post(d, kind="decision", title="决定丙", options=["A", "B"])
    store.poll()
    start(page, server)
    page.click(f'.item[data-id="{dec}"]')
    page.wait_for_selector("#replyText:not([hidden])")
    page.click('#options .opt[data-idx="1"]')
    page.click("#replyText")
    page.keyboard.type("补充说明")
    store.submit(dec, "A", "别处回的")  # 另一个窗口 / 会话那边先回了
    page.wait_for_selector("#followup:not([hidden])")
    assert page.input_value("#fuText") == ""
    assert page.evaluate(f"deskTest.S.drafts['{dec}']") is None
    assert errors == []


def test_todo_kept_row_leaves_once_you_leave_it_by_closing_its_tab_or_switching_scope(env):
    """只看未处理：正在看的那条读完了先留着；关掉它的标签（再撤销）、点到别的项目再回来，都算换走了，它不能再留在列表里。"""
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="甲的回答", body="x", repo="alpha")
    b = post(d, kind="answer", title="乙的回答", body="x", repo="beta")
    c = post(d, kind="answer", title="乙的另一条", body="x", repo="beta")
    store.poll()
    start(page, server)
    page.click('.ptab[data-project="alpha"]')
    page.click('.ptab[data-project="beta"]', modifiers=["Control"])  # 两个项目都看
    page.keyboard.press("f")
    page.click(f'.item[data-id="{a}"]')
    shown(page, a)
    assert wait_until(lambda: a in store.read)
    assert "甲的回答" in visible_titles(page)  # 读完了，还在看：留着
    page.hover('.ptab[data-project="alpha"]')
    page.click('.ptab[data-project="alpha"] .pclose')
    page.wait_for_function("() => !document.querySelector('.ptab[data-project=\"alpha\"]')")
    page.locator(".toast", has_text="已关闭「alpha」").wait_for()
    page.keyboard.press("z")
    page.wait_for_selector('.ptab[data-project="alpha"]')
    assert wait_until(lambda: store.hidden_projects == set())
    page.wait_for_function("() => deskTest.S.hidden.size === 0")
    assert page.evaluate("deskTest.S.current") is None
    assert sorted(page.evaluate("Array.from(deskTest.S.projects)")) == ["alpha", "beta"]  # 撤销：回到关之前的选择
    assert visible_titles(page) == ["乙的另一条", "乙的回答"]
    # 换项目：点"alpha"再 Ctrl + 点"beta"回到两个都看
    page.click(f'.item[data-id="{b}"]')
    shown(page, b)
    assert wait_until(lambda: b in store.read)
    page.click('.ptab[data-project="alpha"]')
    page.wait_for_function("() => deskTest.S.current === null")
    page.click('.ptab[data-project="beta"]', modifiers=["Control"])
    page.wait_for_function("() => deskTest.S.visible.length === 1")
    assert visible_titles(page) == ["乙的另一条"] and c
    assert errors == []


def test_reopening_a_tab_keeps_its_selection_when_a_snapshot_races_the_request(env):
    """找回标签（"已关闭"里点一个）的请求还在路上时，别的变化先让长轮询带回一份旧快照（标签还关着）：
    标签不能闪回关着、选中也不能丢；点旧通知打开关掉的标签里的消息时也一样（不能打开了又关上）。"""
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="甲的回答", body="x", repo="alpha")
    post(d, kind="answer", title="乙的回答", body="x", repo="beta")
    store.poll()
    store.hide_project("alpha")
    orig = server.action

    def slow(body):  # 找回标签之前：先有一条别的新消息（长轮询醒来拿到"alpha 还关着"），再慢一点才真的找回
        if body.get("action") == "show_project":
            post(d, kind="info", title=f"别处的新消息 {time.time()}", body="x", repo="beta")
            store.poll()
            time.sleep(0.6)
        return orig(body)

    server.action = slow
    start(page, server)
    page.click("#closedBtn")
    page.click('#popover [data-reopen="alpha"]')
    assert wait_until(lambda: store.hidden_projects == set())
    page.wait_for_function("() => deskTest.S.hidden.size === 0 && document.querySelector('.ptab[data-project=\"alpha\"]')")
    time.sleep(0.3)
    assert page.evaluate("Array.from(deskTest.S.projects)") == ["alpha"]
    assert visible_titles(page) == ["甲的回答"]
    # 点旧通知：消息在关掉的标签里
    store.hide_project("alpha")
    page.wait_for_function("() => deskTest.S.hidden.has('alpha')")
    page.evaluate("id => deskOpen(id)", a)
    assert wait_until(lambda: store.hidden_projects == set())
    time.sleep(0.8)
    assert page.evaluate("deskTest.S.current") == a
    shown(page, a)
    assert errors == []


def test_following_a_thread_link_does_not_leave_focus_on_a_hidden_button(env):
    """回应追问的那条顶上"原回答：…"：点了打开原来那条（它没有这一行，按钮藏起来了），焦点回到列表，键盘接着能用。"""
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="原回答", body="x")
    store.poll()
    f = store.add_followup(a, "再说说？")
    rep = desk.post_message(desk.make_message("answer", "proj", "再说说的回答", "y", reply_to=a, followup_id=f["id"]), d)
    store.poll()
    start(page, server)
    page.click(f'.item[data-id="{rep}"]')
    page.wait_for_selector(f'#threadRef:not([hidden]) [data-open="{a}"]')
    page.click(f'#threadRef [data-open="{a}"]')
    shown(page, a)
    page.wait_for_selector("#threadRef", state="hidden")
    assert page.evaluate("document.activeElement.id") == "list"
    page.keyboard.press("Enter")  # 列表上 Enter：去写追问
    page.wait_for_function("document.activeElement.id === 'fuText'")
    assert errors == []


def test_followup_box_stays_put_and_new_ones_land_on_top(env):
    """长回答上接连发三个追问：追问框在标题下面不动、焦点留在框里；发出的那条出现在列表最上面，紧挨着框（不用滚就看得见）。"""
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="长回答", body="\n\n".join(f"第 {i} 段" for i in range(60)))
    store.poll()
    start(page, server)
    page.click(f'.item[data-id="{a}"]')
    shown(page, a)
    page.wait_for_selector("#followup:not([hidden])")
    page.focus("#fuText")
    top = "() => Math.round(document.getElementById('fuText').getBoundingClientRect().top)"
    t0 = page.evaluate(top)
    for i in range(3):
        page.keyboard.type(f"第 {i} 个追问")
        page.keyboard.press("Control+Enter")
        page.wait_for_function(f"() => document.querySelectorAll('#fuList .fu-item').length === {i + 1}")
        assert page.evaluate("document.activeElement.id") == "fuText"
        assert page.evaluate(top) == t0 and page.evaluate("document.getElementById('scroller').scrollTop") == 0
        first = page.locator("#fuList .fu-item").first
        assert f"第 {i} 个追问" in first.inner_text()
        fb, sb = first.bounding_box(), page.locator("#scroller").bounding_box()
        assert fb["y"] + fb["height"] <= sb["y"] + sb["height"]  # 刚发的那条在屏幕上
    assert [f["text"] for f in desk.read_followups(d)[0]] == ["第 0 个追问", "第 1 个追问", "第 2 个追问"]
    assert page.evaluate("[...document.querySelectorAll('#fuList .fu-q')].map(e => e.textContent)") == ["第 2 个追问", "第 1 个追问", "第 0 个追问"]
    assert errors == []


def test_followup_card_catches_up_when_it_changes_again_while_loading(env):
    """追问卡片的详情还在路上时又变了一次（会话领走了追问）：那次因为"正在拿"被跳过，拿回来以后要再对一次，不能停在旧的样子。"""
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="原回答", body="x", source="S")
    store.poll()
    start(page, server)
    page.click(f'.item[data-id="{a}"]')
    shown(page, a)
    page.wait_for_selector("#followup:not([hidden])")
    orig, gate = store.detail, {"arm": True}

    def slow_detail(mid):  # 算好的详情晚一点才回去：这期间的变化它不含
        out = orig(mid)
        if mid == a and gate["arm"]:
            gate["arm"] = False
            time.sleep(0.8)
        return out

    store.detail = slow_detail
    store.add_followup(a, "再说说？")
    time.sleep(0.2)  # 卡片正在拿详情
    assert desk._claim_followup(d, "S", desk.parse_ts(desk.now_ts()).replace(year=2000), set())["text"] == "再说说？"
    page.wait_for_function("() => document.querySelector('#fuList .fu-wait') && document.querySelector('#fuList .fu-wait').textContent.includes('已送到会话')",
                           timeout=4000)
    assert errors == []


def test_unsorted_group_label_in_the_archive_view_still_filters(env):
    """"未归类"只剩归档的：平时没有标签；归档视图里点它的分组标题，要真的只看未归类（以前标签不在，选择马上被清掉，点了没反应）。"""
    d, store, server, page, errors = env
    post(d, kind="answer", title="甲", body="x", repo="alpha")
    al = post(d, kind="info", title="甲的旧通知", body="x", repo="alpha")
    o1 = post(d, kind="info", title="旧来源一", body="x", source="随手记")
    store.poll()
    store.archive([o1, al])
    start(page, server)
    assert page.evaluate("[...document.querySelectorAll('#projects .ptab')].map(t => t.dataset.project)") == ["alpha"]
    page.click('[data-view="archive"]')
    page.click('.ptab[data-project="__other__"]', modifiers=["Control"])  # 归档视图里它有标签：加选上，按项目分组
    page.wait_for_selector(f'.item[data-id="{o1}"]')
    page.click(".group-label.other .gname")
    page.wait_for_function("() => deskTest.S.visible.length === 1")
    assert page.evaluate("Array.from(deskTest.S.projects)") == ["__other__"]
    assert page.locator('.ptab[data-project="__other__"].on').count() == 1
    page.click('[data-view="answer"]')  # 离开归档：未归类没有没归档的，标签收起来，选择换到还在的 alpha；视图上的数按换了以后的范围算
    page.wait_for_function("() => !document.querySelector('.ptab[data-project=\"__other__\"]')")
    assert page.evaluate("Array.from(deskTest.S.projects)") == ["alpha"]
    assert visible_titles(page) == ["甲"]
    assert page.inner_text('.tab[data-view="answer"] .n') == "1" and page.inner_text('.tab[data-view="all"] .n') == "1"
    assert errors == []

