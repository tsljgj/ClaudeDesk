"""只看未处理 / 标为已处理（不通知会话，可以撤销）/ 每条决定都有补充说明框 / 按时间归档已处理的：在真浏览器里点、按键，看界面和服务端。"""
import datetime as dt
import itertools
import re

import desk
from claudedesk.store import RESOLVE_TEXT
from test_ui import env  # noqa: F401（env 是 fixture）
from test_ui_keys import opened, resp, start

_seq = itertools.count()


def post(d, **kw):  # 时间一条比一条晚（同一毫秒里发的几条顺序不定）：列表顺序 = 后发的在前
    kw.setdefault("source", "proj")
    m = desk.make_message(**kw)
    m["ts"] = (dt.datetime.now().astimezone() - dt.timedelta(hours=1, seconds=-next(_seq))).isoformat(timespec="milliseconds")
    return desk.post_message(m, d)


def vis(page):
    return page.evaluate("deskTest.S.visible.slice()")


def wait_vis(page, ids):
    page.wait_for_function("ids => JSON.stringify(deskTest.S.visible) === JSON.stringify(ids)", arg=ids)


def wait_toast(page, text):  # 提示条的文字（不含按钮）
    page.wait_for_function("t => [...document.querySelectorAll('.toast > span')].some(s => s.textContent === t)", arg=text)


def toast_button(page, text):
    return page.evaluate("t => { const s = [...document.querySelectorAll('.toast > span')].find(s => s.textContent === t);"
                         " const b = s && s.parentElement.querySelector('button'); return b ? b.textContent : null; }", text)


def test_only_unhandled_toggle_filters_each_view_and_persists(env):
    d, store, server, page, errors = env
    arch = post(d, kind="info", title="归档的", body="x")
    done = post(d, kind="decision", title="决定过了", options=["A", "B"])
    old = post(d, kind="answer", title="读过的回答", body="x")
    seen = post(d, kind="decision", title="看过还没决定", options=["A", "B"])
    info = post(d, kind="info", title="没读的通知", body="x")
    ans = post(d, kind="answer", title="没读的回答", body="x")
    dec = post(d, kind="decision", title="没读的决定", options=["A", "B"])
    store.poll()
    store.mark_read([done, old, seen])
    store.submit(done, "A", "")
    store.archive([arch])
    start(page, server)
    page.wait_for_selector(".item")
    assert vis(page) == [dec, ans, info, seen, old, done]
    btn = page.locator("#todoBtn")
    assert btn.get_attribute("aria-pressed") == "false" and "（F）" in btn.get_attribute("title")
    nav = page.inner_text("#nav")

    # 打开：全部 = 还要你处理的（待决定 + 没读过的）；点完焦点回列表（之后按 Enter 不会又按了它）
    btn.click()
    wait_vis(page, [dec, ans, info, seen])
    assert btn.get_attribute("aria-pressed") == "true" and page.evaluate("document.activeElement.id") == "list"
    assert page.inner_text("#nav") == nav  # 视图上的数不变
    page.click('[data-view="decide"]')
    wait_vis(page, [dec, seen])
    page.click('[data-view="answer"]')
    wait_vis(page, [ans])
    page.click('[data-view="archive"]')  # 归档里不起作用：两个按钮都收起来
    wait_vis(page, [arch])
    assert page.is_hidden("#todoBtn") and page.is_hidden("#handledBtn")
    page.keyboard.press("f")
    wait_toast(page, "归档里不分未处理")
    page.click('[data-view="all"]')
    wait_vis(page, [dec, ans, info, seen])

    # 记在本机：重新打开还是开着
    page.reload()
    page.wait_for_function("window.deskTest && deskTest.S.version >= 0")
    wait_vis(page, [dec, ans, info, seen])
    assert page.get_attribute("#todoBtn", "aria-pressed") == "true"

    # F 开 / 关
    page.keyboard.press("f")
    wait_vis(page, [dec, ans, info, seen, old, done])
    assert page.get_attribute("#todoBtn", "aria-pressed") == "false"
    page.keyboard.press("f")
    wait_vis(page, [dec, ans, info, seen])

    # 都处理完了：空状态
    store.resolve([dec, ans, info, seen])
    page.wait_for_selector(".list-empty")
    assert page.inner_text(".list-empty b") == "没有未处理的了"
    assert "处理过的都收起来了" in page.inner_text(".list-empty")
    assert errors == []


def test_the_message_you_are_reading_stays_until_you_move_on(env):
    d, store, server, page, errors = env
    a0, a1, a2, a3 = (post(d, kind="answer", title=f"回答 {i}", body="x") for i in range(4))
    store.poll()
    start(page, server)
    page.wait_for_selector(".item")
    page.keyboard.press("f")
    wait_vis(page, [a3, a2, a1, a0])

    # 点开 = 马上读了；还留在列表里（长轮询带回"已读"以后也一样）
    page.click(f'.item[data-id="{a3}"]')
    page.wait_for_function(f"() => !deskTest.S.byId['{a3}'].unread")
    page.wait_for_timeout(500)
    assert vis(page) == [a3, a2, a1, a0] and page.locator(f'.item[data-id="{a3}"].selected').count() == 1

    # ↓ 停 0.8 秒才算读：a3 换走了才走，a2 读完了照样留着
    page.keyboard.press("j")
    wait_vis(page, [a2, a1, a0])
    page.wait_for_function(f"() => !deskTest.S.byId['{a2}'].unread")
    page.wait_for_timeout(300)
    assert vis(page) == [a2, a1, a0]
    # 扫过去（没停够）的不算读，留在列表里
    page.keyboard.press("j")
    page.keyboard.press("j")
    wait_vis(page, [a1, a0])
    assert store.is_unread(store.msgs[a1]) and page.evaluate("deskTest.S.current") == a0

    # 自己标为已处理的：马上走，换到下一条
    page.keyboard.press("r")
    wait_vis(page, [a1])
    assert page.evaluate("deskTest.S.current") == a1 and page.is_hidden("#modal")
    # 归档的也走
    page.keyboard.press("e")
    page.wait_for_selector(".list-empty")
    assert a1 in store.archived
    assert errors == []


def test_mark_handled_on_a_mixed_selection_is_silent_and_can_be_undone(env):
    d, store, server, page, errors = env
    d1 = post(d, kind="decision", title="决定一", options=["A", "B"])
    d2 = post(d, kind="decision", title="决定二", options=["A", "B"])
    ans = post(d, kind="answer", title="没读的回答", body="x")
    store.poll()
    start(page, server)
    page.wait_for_selector(".item")
    page.keyboard.press("f")
    page.focus("#list")
    page.keyboard.press("Control+a")  # 只看未处理时全选 = 把还要处理的都勾上
    page.wait_for_selector("#bulkbar:not([hidden])")
    assert page.inner_text("#bulkCount") == "已选 3 条" and "on" in page.get_attribute("#checkAll", "class").split()
    page.keyboard.press("Escape")
    page.wait_for_selector("#bulkbar", state="hidden")
    # Shift + 点勾选框：连选一段
    page.locator(f'.item[data-id="{ans}"]').hover()
    page.click(f'.item[data-id="{ans}"] .cb')
    page.click(f'.item[data-id="{d1}"] .cb', modifiers=["Shift"])
    page.wait_for_function("deskTest.S.multi.size === 3")
    assert page.is_visible("#bulkResolve") and page.inner_text("#bulkResolve") == "标为已处理"
    assert page.get_attribute("#bulkResolve", "title") == "不通知会话：待决定的直接关掉，其余的标为已读（R）"
    page.click("#bulkResolve")  # 点按钮：一下就好，不问
    wait_toast(page, "已标为已处理 3 条")
    assert page.is_hidden("#modal")
    assert toast_button(page, "已标为已处理 3 条") == "撤销（Z）"  # 没通知会话：撤销得了
    for x in (d1, d2):
        r = resp(d, x)[0]
        assert r["resolved"] is True and r["choice"] is None and r["text"] == RESOLVE_TEXT and r["silent"] is True
    assert not store.is_unread(store.msgs[ans]) and resp(d, ans) == []
    page.wait_for_selector(".list-empty")
    # Z：两条决定重新打开（那条已处理的回复删掉了），回答改回未读，都回到列表里
    page.keyboard.press("z")
    wait_vis(page, [ans, d2, d1])
    assert resp(d, d1) == [] and resp(d, d2) == [] and store.is_unread(store.msgs[ans])
    assert page.evaluate(f"['{d1}', '{d2}'].every(id => deskTest.S.byId[id].open)")
    assert errors == []


def test_r_never_asks_and_undo_reopens_decisions_and_restores_unread(env):
    d, store, server, page, errors = env
    dec = post(d, kind="decision", title="等你", options=["A", "B"])
    a1 = post(d, kind="answer", title="回答一", body="x")
    a2 = post(d, kind="answer", title="回答二", body="x")
    store.poll()
    start(page, server)
    page.wait_for_selector(".item")
    page.click(f'.item[data-id="{a1}"]', modifiers=["Control"])  # Ctrl + 点 = 勾选，不打开、不算读
    page.click(f'.item[data-id="{a2}"]', modifiers=["Control"])
    page.keyboard.press("r")
    wait_toast(page, "已标为已处理 2 条")
    assert page.is_hidden("#modal") and toast_button(page, "已标为已处理 2 条") == "撤销（Z）"
    assert not store.is_unread(store.msgs[a1]) and not store.is_unread(store.msgs[a2])
    page.keyboard.press("z")
    page.wait_for_function(f"() => deskTest.S.byId['{a1}'].unread && deskTest.S.byId['{a2}'].unread")
    assert store.is_unread(store.msgs[a1]) and store.is_unread(store.msgs[a2])

    # 牵涉待决定也不问（不通知会话），一样能撤销
    page.focus("#list")
    page.keyboard.press("Control+a")
    page.keyboard.press("r")
    wait_toast(page, "已标为已处理 3 条")
    assert page.is_hidden("#modal") and toast_button(page, "已标为已处理 3 条") == "撤销（Z）"
    r = resp(d, dec)[0]
    assert r["resolved"] is True and r["silent"] is True and not store.is_unread(store.msgs[a2])
    page.wait_for_selector(f'.item[data-id="{dec}"] .st.done')
    assert page.inner_text(f'.item[data-id="{dec}"] .st.done') == "✓ 已处理"
    page.keyboard.press("z")
    page.wait_for_selector(f'.item[data-id="{dec}"] .st.open')
    assert resp(d, dec) == [] and store.is_open(store.msgs[dec])
    page.wait_for_function(f"() => ['{dec}', '{a1}', '{a2}'].every(id => deskTest.S.byId[id].unread)")
    assert errors == []


def test_check_button_and_menu_item_show_on_every_unhandled_row(env):
    d, store, server, page, errors = env
    old = post(d, kind="answer", title="读过的", body="x")
    new = post(d, kind="answer", title="没读的", body="x")
    dec = post(d, kind="decision", title="要决定", options=["A", "B"])
    store.poll()
    store.mark_read([old])
    start(page, server)
    page.wait_for_selector(".item")
    acts = lambda i: page.evaluate(f"[...document.querySelectorAll('.item[data-id=\"{i}\"] .act')].map(b => b.dataset.act)")  # noqa: E731
    assert acts(new) == ["read", "resolve", "archive", "delete"] and acts(dec) == acts(new)
    assert acts(old) == ["read", "archive", "delete"]
    assert page.get_attribute(f'.item[data-id="{new}"] [data-act="resolve"]', "title") == "标为已处理 · 不通知会话（R）"
    menu = lambda i: (page.click(f'.item[data-id="{i}"]', button="right"), page.wait_for_selector("#popover:not([hidden])"),  # noqa: E731
                      page.evaluate("[...document.querySelectorAll('#popover [data-m]')].map(b => b.dataset.m + ':' + b.textContent)"))[2]
    assert "resolve:标为已处理R" in menu(new)
    assert page.get_attribute('#popover [data-m="resolve"]', "title") == "不通知会话：你已经在对话里说过，或者这件事不重要了"
    page.keyboard.press("Escape")
    assert not any(m.startswith("resolve") for m in menu(old))
    page.keyboard.press("Escape")

    # 点 ✓：一下就好；没读过的回答 = 标为已读（不写回复），这行留着（没开"只看未处理"）
    page.locator(f'.item[data-id="{new}"]').hover()
    page.click(f'.item[data-id="{new}"] [data-act="resolve"]')
    wait_toast(page, "已标为已处理 1 条")
    assert page.is_hidden("#modal") and not store.is_unread(store.msgs[new]) and resp(d, new) == []
    assert new in vis(page)

    # 决定卡片：按钮写"标为已处理"，点了以后写"已标为已处理 · 没有通知会话"
    opened(page, dec)
    assert page.inner_text("#resolveBtn") == "标为已处理"
    assert page.get_attribute("#resolveBtn", "title") == "不通知会话：你已经在对话里说过，或者这件事不重要了（R）"
    page.click("#resolveBtn")
    page.wait_for_selector("#doneBox:not([hidden])")
    assert page.inner_text("#doneBox b") == "已标为已处理"
    assert re.match(r"已标为已处理 · 没有通知会话 · (今天|昨天) \d\d:\d\d$", page.inner_text("#doneBox").split("\n")[0])
    assert resp(d, dec)[0]["text"] == RESOLVE_TEXT
    assert errors == []


def test_every_decision_has_a_reply_box_and_text_alone_can_be_sent(env):
    d, store, server, page, errors = env
    a = post(d, kind="decision", title="没写 allow_text", options=["甲", "乙"])
    b = post(d, kind="decision", title="没有选项")
    store.poll()
    start(page, server)
    hint = lambda: page.inner_text("#decideHint")  # noqa: E731
    opened(page, b)
    assert page.is_visible("#replyText") and page.get_attribute("#replyText", "placeholder") == "写下你的回复"
    opened(page, a)
    assert page.is_visible("#replyText") and page.get_attribute("#replyText", "placeholder") == "补充说明（可选）"
    assert hint() == "按 1–2 选择，或直接写回复" and page.is_disabled("#submitBtn")
    page.keyboard.press("Enter")  # Enter：跳进输入框
    assert page.evaluate("document.activeElement.id") == "replyText"
    page.keyboard.type("我在对话里说过了")
    assert hint() == "按 1–2 选择，或 Ctrl+Enter 提交" and page.is_enabled("#submitBtn")

    # 草稿：换一条再回来还在
    opened(page, b)
    opened(page, a)
    assert page.input_value("#replyText") == "我在对话里说过了"

    # 只写字、不选选项：交上去 choice 是 null
    page.keyboard.press("Control+Enter")
    page.wait_for_selector("#doneBox:not([hidden])")
    r = resp(d, a)[0]
    assert r["choice"] is None and r["text"] == "我在对话里说过了"
    assert errors == []


def post_ago(d, ago, **kw):  # 发在 ago 以前
    kw.setdefault("source", "proj")
    m = desk.make_message(**kw)
    m["ts"] = (dt.datetime.now().astimezone() - ago).isoformat(timespec="milliseconds")
    return desk.post_message(m, d)


def ages(page):  # 菜单里每一档：[档, 读屏念的"早于 N · M 条", 按不按得了]
    return page.evaluate("[...document.querySelectorAll('#popover [data-age]')].map(b => [b.dataset.age, b.getAttribute('aria-label'), !b.disabled])")


def test_archive_handled_by_age(env):
    """按时间归档已处理的：#handledBtn 和"⋯"菜单打开同一个菜单（早于 1 小时 / 24 小时 / 7 天 / 全部，各写条数，0 条的按不了）。
    "早于"按最后一次动静算（收到、回复、在界面里打开）；正在看的那条永远不动；只动当前项目；记住上次选的那档；能用键盘；
    撤销恰好放回这一批。"""
    d, store, server, page, errors = env
    H, D = dt.timedelta(hours=1), dt.timedelta(days=1)
    mk = lambda ago, title, repo="alpha", kind="answer", **kw: post_ago(d, ago, kind=kind, title=title, body="x", repo=repo, **kw)  # noqa: E731
    h2 = mk(2 * H, "两小时前")
    d2 = mk(2 * D, "两天前")
    w2 = mk(10 * D, "十天前")
    seen = mk(3 * D, "三天前发的、刚看过")
    recent = mk(H / 6, "十分钟前")
    cur = mk(10 * D, "正在看的")
    unread = mk(10 * D, "没读的")
    dec = mk(10 * D, "没决定的", kind="decision", options=["A"])
    beta = mk(10 * D, "别的项目的", repo="beta")
    store.poll()
    store.mark_read([h2, d2, w2, recent, cur, dec, beta])  # 批量标为已读：不算打开
    store.mark_read([seen], opened=True)  # 三天前发的，刚在界面里打开过
    start(page, server)
    page.wait_for_selector(".item")
    page.click('.ptab[data-project="alpha"]')
    page.click(f'.item[data-id="{cur}"]')
    h = page.locator("#handledBtn")
    page.wait_for_function("document.getElementById('handledBtn').title === '归档已处理的…：选早于多久（alpha · 共 5 条已读、不用再决定）'")

    # 点按钮：先出菜单，不直接归档；焦点在第一档，↓ 回车选"早于 24 小时"
    h.click()
    page.wait_for_selector("#popover:not([hidden])")
    assert ages(page) == [["1h", "早于 1 小时 · 3 条", True], ["24h", "早于 24 小时 · 2 条", True],
                          ["7d", "早于 7 天 · 1 条", True], ["all", "全部 · 5 条", True]]
    assert store.archived == set() and page.evaluate("document.activeElement.dataset.age") == "1h"
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    wait_toast(page, "已归档 2 条（早于 24 小时）")
    assert store.archived == {d2, w2}  # 三天前发的那条刚看过：不算旧
    assert page.is_hidden("#popover") and toast_button(page, "已归档 2 条（早于 24 小时）") == "撤销（Z）"
    assert page.evaluate("localStorage.getItem('desk.handledAge')") == "24h"
    page.keyboard.press("z")  # 撤销恰好放回这一批
    page.wait_for_function(f"() => !deskTest.S.byId['{d2}'].archived && !deskTest.S.byId['{w2}'].archived")
    assert store.archived == set()

    # "⋯"菜单里的"归档已处理的…"打开同一个菜单：上次选的那档打勾，焦点在它上面；鼠标点"早于 7 天"，焦点回列表
    page.click("#listMenuBtn")
    page.click('[data-l="archive_handled"]')
    page.wait_for_selector("#popover [data-age]")
    assert page.evaluate("document.activeElement.dataset.age") == "24h"
    assert page.evaluate("[...document.querySelectorAll('#popover .menu-item.last')].map(b => b.dataset.age)") == ["24h"]
    page.click('#popover [data-age="7d"]')
    wait_toast(page, "已归档 1 条（早于 7 天）")
    assert store.archived == {w2} and page.evaluate("document.activeElement.id") == "list"

    # 0 条的那档按不了，键盘跳过它；Esc 关掉菜单，焦点回到按钮，回车再打开
    h.click()
    page.wait_for_selector("#popover:not([hidden])")
    assert ages(page) == [["1h", "早于 1 小时 · 2 条", True], ["24h", "早于 24 小时 · 1 条", True],
                          ["7d", "早于 7 天 · 0 条", False], ["all", "全部 · 4 条", True]]
    assert page.evaluate("document.activeElement.dataset.age") == "1h"  # 上次选的那档现在是 0 条：焦点在第一档
    page.keyboard.press("Escape")
    assert page.is_hidden("#popover") and page.evaluate("document.activeElement.id") == "handledBtn"
    page.keyboard.press("Enter")
    page.wait_for_selector("#popover:not([hidden])")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    assert page.evaluate("document.activeElement.dataset.age") == "all"
    page.keyboard.press("Enter")
    wait_toast(page, "已归档 4 条")
    assert store.archived == {w2, h2, d2, seen, recent}  # 正在看的、没读的、没决定的、别的项目的都不动
    assert page.evaluate("deskTest.S.current") == cur and not page.evaluate(f"deskTest.S.byId['{unread}'].archived")

    # 只剩正在看的那条：按钮灰掉，点了只提示，不出菜单
    page.wait_for_function("document.getElementById('handledBtn').getAttribute('aria-disabled') === 'true'")
    assert h.get_attribute("title") == "没有已处理的可以归档（已读、不用再决定的）"
    h.click(force=True)
    wait_toast(page, "没有已处理的可以归档")
    assert page.is_hidden("#popover") and not ({cur, unread, dec, beta} & store.archived)
    page.click('[data-view="archive"]')
    assert page.is_hidden("#handledBtn")
    assert errors == []


def test_delete_of_an_open_decision_says_the_session_is_not_told(env):
    d, store, server, page, errors = env
    dec = post(d, kind="decision", title="还在等", options=["A"])
    store.poll()
    start(page, server)
    page.click(f'.item[data-id="{dec}"]')
    page.keyboard.press("Delete")
    page.wait_for_function("document.activeElement.id === 'modalOk'")
    assert page.inner_text("#modalText") == "删除后不能恢复，会从收件箱文件里真正移除。\n其中有还在等你决定的消息：删除不会通知会话。"
    page.keyboard.press("Enter")
    wait_toast(page, "已删除 1 条")
    r = resp(d, dec)[0]
    assert r["dismissed"] is True and r["silent"] is True
    assert errors == []


def test_old_resolved_records_keep_their_wording(env):
    """以前写的"标为已处理"（没有 silent）当时通知了会话：完成框照旧那么说。"""
    d, store, server, page, errors = env
    a = post(d, kind="decision", title="以前标的", options=["A"])
    desk.write_response(a, None, RESOLVE_TEXT, "proj", d, extra={"title": "以前标的", "resolved": True})
    store.poll()
    start(page, server)
    opened(page, a)
    page.wait_for_selector("#doneBox:not([hidden])")
    assert "等待的会话已收到「已经处理好了」。" in page.inner_text("#doneBox")
    assert "没有通知会话" not in page.inner_text("#doneBox")
    assert errors == []


def test_search_queue_and_n_still_work_with_the_filter(env):
    d, store, server, page, errors = env
    old = post(d, kind="answer", title="苹果 读过", body="x")
    new = post(d, kind="answer", title="苹果 没读", body="x")
    dec = post(d, kind="decision", title="香蕉 要决定", options=["A"])
    store.poll()
    store.mark_read([old])
    start(page, server)
    page.wait_for_selector(".item")
    page.keyboard.press("f")
    wait_vis(page, [dec, new])
    assert page.is_visible("#queueBtn")

    # N：照样跳到待决定
    page.keyboard.press("n")
    page.wait_for_function(f"deskTest.S.current === '{dec}'")

    # 搜索：只在未处理的里找；被收起来的已处理的给一行"另有 N 条…"，点了关掉筛选看全部结果
    page.keyboard.press("/")
    page.keyboard.type("苹果")
    page.keyboard.press("Enter")
    wait_vis(page, [new])
    more = page.locator(".search-more")
    assert more.inner_text().startswith("另有 1 条已处理或在其他视图、项目里")
    more.click()
    wait_vis(page, [new, old])
    assert page.get_attribute("#todoBtn", "aria-pressed") == "false"
    assert errors == []


def test_buttons_fit_the_list_header(env):
    """列表 360px（宽窗口）、320px（窗口 ≤ 960）和 480 的窄窗口里，两个按钮都放得下，搜索框也不会挤没。"""
    d, store, server, page, errors = env
    for i in range(12):
        post(d, kind="decision" if i % 3 == 0 else "answer", title=f"消息 {i}", body="x", options=["A"] if i % 3 == 0 else None)
    store.poll()
    for w in (1300, 900, 480):
        page.set_viewport_size({"width": w, "height": 800})
        start(page, server)
        page.wait_for_selector(".item")
        box = page.evaluate("""() => { const r = s => document.querySelector(s).getBoundingClientRect();
            return { pane: r('#listpane').right, tabs: r('#nav').right, more: r('#listMenuBtn').left, todo: r('#todoBtn'), h: r('#handledBtn'),
              search: r('.search').width, row: r('.search-row').top, scroll: (h => h.scrollWidth - h.clientWidth)(document.querySelector('.list-head')) }; }""")
        assert box["h"]["right"] <= box["pane"] - 12 and box["todo"]["right"] < box["h"]["left"], w
        assert box["todo"]["top"] >= box["row"] and box["search"] >= 120 and box["scroll"] <= 0, w
        assert box["tabs"] <= box["more"], w  # 视图标签那一行也没挤
        page.focus("#list")
        page.keyboard.press("Control+a")  # 批量栏：文字按钮和四个图标放得下，"已选 N 条"不折行
        bar = page.evaluate("""() => { const b = document.getElementById('bulkbar'), c = document.getElementById('bulkCount');
            return [b.scrollWidth - b.clientWidth, c.getBoundingClientRect().height, document.getElementById('bulkResolve').offsetWidth]; }""")
        assert bar[0] <= 0 and bar[1] < 24 and bar[2] > 60, (w, bar)
    assert errors == []
