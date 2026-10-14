"""几条线（键盘 / 状态 / 视觉）合在一起以后才出现的问题：勾选和长轮询、撤销和还在路上的请求、
停留计时和撤销、整块重画和键盘焦点、窄窗口和搜索、晚到的旧快照、删除时闪回来的行。
每条都是 QA 模糊测试（随机操作 + 服务端同时改数据）找到后缩成的确定性复现。"""
import time

import desk
from test_ui import env, post  # noqa: F401  （env 是 fixture）
from test_ui_state import wait_until

FOCUSED = "sel => document.activeElement === document.querySelector(sel)"
# 页面里的 fetch 换成可以拖慢的：url 里含 window.__slow 的那一个请求，回应晚 700 ms 才交给页面
SLOW_FETCH = """() => { const f = window.fetch; window.__slow = null;
  window.fetch = function (url) { const p = f.apply(this, arguments), s = window.__slow;
    if (s && String(url).indexOf(s) >= 0) { window.__slow = null; return p.then(r => new Promise(ok => setTimeout(() => ok(r), 700))); }
    return p; }; }"""


def open_page(page, server):
    page.goto(server.url)
    page.wait_for_selector(".item")


def slow_action(server, name, before=0.0, after=0.0, first=None):
    """服务端的某个操作变慢（改之前 / 改之后睡一会儿）；first 在改之前先跑（例如插一条别的变化）。"""
    orig = server.action

    def run(body):
        if body.get("action") != name:
            return orig(body)
        if first:
            first()
        time.sleep(before)
        r = orig(body)
        time.sleep(after)
        return r

    server.action = run


def test_selection_keeps_only_rows_that_are_still_visible(env):
    """勾着的一条在别的窗口被归档了、或被搜索筛掉了：以前还留在勾选里（"已选 2 条"，只看得见 1 条），批量删除会把看不见的也删掉。"""
    d, store, server, page, errors = env
    a, b, c, e = (post(d, kind="answer", title=t, body="x") for t in ("苹果", "香蕉", "橘子", "葡萄"))
    store.poll()
    open_page(page, server)
    page.click(f'.item[data-id="{a}"] .t', modifiers=["Control"])
    page.click(f'.item[data-id="{b}"] .t', modifiers=["Control"])
    assert page.inner_text("#bulkCount") == "已选 2 条"
    server.action({"action": "archive", "ids": [a]})  # 别的窗口
    page.wait_for_function(f"() => !document.querySelector('.item[data-id=\"{a}\"]')")
    assert page.evaluate("Array.from(deskTest.S.multi)") == [b]
    assert page.inner_text("#bulkCount") == "已选 1 条"
    page.click(f'.item[data-id="{c}"] .t', modifiers=["Control"])
    page.fill("#search", "橘子")
    page.wait_for_function("() => deskTest.S.visible.length === 1")
    assert page.evaluate("Array.from(deskTest.S.multi)") == [c]
    assert page.inner_text("#bulkCount") == "已选 1 条"
    page.click('#bulkbar [data-bulk="delete"]')
    assert page.inner_text("#modalTitle") == "删除「橘子」？"
    page.click("#modalOk")
    assert wait_until(lambda: c in store.deleted)
    assert b not in store.deleted and e not in store.deleted
    assert errors == []


def test_bulk_read_clears_the_selection_when_the_long_poll_wins(env):
    """批量"标为已读"：服务端改完先唤醒了长轮询，操作的回应慢一步回来。以前勾选清了，列表和批量栏却没重画（还写着"已选 2 条"）。"""
    d, store, server, page, errors = env
    ids = [post(d, kind="answer", title=f"消息 {i}", body="x") for i in range(3)]
    store.poll()
    slow_action(server, "read", after=0.3)
    open_page(page, server)
    for i in ids[:2]:
        page.click(f'.item[data-id="{i}"] .t', modifiers=["Control"])
    page.click('#bulkbar [data-bulk="read"]')
    page.wait_for_selector(".toast >> text=已标为已读 2 条")
    page.wait_for_function("() => document.getElementById('bulkbar').hidden")
    assert page.locator(".item.multi").count() == 0
    assert not page.evaluate("document.getElementById('list').classList.contains('multi-mode')")
    assert errors == []


def test_z_during_an_archive_never_undoes_the_one_before(env):
    """归档 A（出了撤销提示）→ 归档 B，请求还在路上就按 Z：以前撤的是 A（A 被移出归档，B 留在归档里）。
    现在旧的撤销一开始就作废；B 的提示出来以后，Z 撤的是 B。"""
    d, store, server, page, errors = env
    for i in range(4):
        post(d, kind="answer", title=f"消息 {i}", body="x")
    store.poll()
    open_page(page, server)
    page.click(".item >> nth=0")
    a = page.evaluate("deskTest.S.current")
    page.keyboard.press("e")
    page.wait_for_selector(".toast button >> text=撤销")
    b = page.evaluate("deskTest.S.current")
    slow_action(server, "archive", before=0.4)
    page.keyboard.press("e")
    page.keyboard.press("z")
    assert wait_until(lambda: b in store.archived)
    time.sleep(0.2)
    assert a in store.archived  # 没有撤到更早的 A 上
    page.wait_for_selector(".toast button >> text=撤销")  # B 的提示
    page.keyboard.press("z")
    assert wait_until(lambda: b not in store.archived)
    assert a in store.archived
    assert errors == []


def test_keyboard_focus_survives_background_updates(env):
    """键盘停在视图标签、项目标签、"开始处理"、"去选择"上时，新消息到了（长轮询整块重画这些地方）焦点不能掉到 body。"""
    d, store, server, page, errors = env
    post(d, kind="answer", title="甲", body="x", repo="alpha")
    post(d, kind="answer", title="乙", body="x", repo="beta")
    # 正文长一点：决定卡片在屏幕下面，"去选择 ↓"才会出现（卡片已经露出来时它是隐藏的）
    dec = post(d, kind="decision", title="要决定的", body="很长的背景。\n\n" * 80, options=["A", "B"], repo="alpha")
    store.poll()
    open_page(page, server)
    page.wait_for_selector("#startBtn")
    for i, sel in enumerate(['#nav .tab[data-view="answer"]', '#projects .ptab[data-project="beta"]', "#startBtn"]):
        page.focus(sel)
        v = page.evaluate("deskTest.S.version")
        post(d, kind="info", title=f"新来的 {i}", body="x", repo="alpha")
        page.wait_for_function("v => deskTest.S.version > v", arg=v)
        assert page.evaluate(FOCUSED, sel), sel
    page.click(f'.item[data-id="{dec}"]')
    page.wait_for_selector("#jumpBtn")
    page.keyboard.press("Shift")  # 点过鼠标了：先按个键，下面的焦点算键盘焦点（:focus-visible）
    page.focus("#jumpBtn")
    v = page.evaluate("deskTest.S.version")
    post(d, kind="info", title="又来一条", body="x", repo="beta")
    page.wait_for_function("v => deskTest.S.version > v", arg=v)
    assert page.evaluate(FOCUSED, "#jumpBtn")
    # 鼠标点的标签：焦点照旧不留（看不见的焦点留着，之后按 Enter 会又点一次这个标签）
    page.click('#nav .tab[data-view="answer"]')
    assert not page.evaluate(FOCUSED, '#nav .tab[data-view="answer"]')
    assert errors == []


def test_slash_in_the_narrow_reader_goes_back_to_the_list(env):
    """窄窗口里阅读页盖住了列表：以前按 / 把焦点放进被盖住的搜索框，之后打的字（还有 j / k / e）都进了看不见的框。"""
    d, store, server, page, errors = env
    post(d, kind="answer", title="甲", body="x")
    post(d, kind="answer", title="乙", body="x")
    store.poll()
    page.set_viewport_size({"width": 600, "height": 800})
    open_page(page, server)
    page.click(".item >> nth=0")
    page.wait_for_selector("#app.reading")
    page.keyboard.press("/")
    page.wait_for_function("() => !document.getElementById('app').classList.contains('reading')")
    assert page.evaluate(FOCUSED, "#search")
    page.wait_for_timeout(300)  # 阅读页滑走的动画
    assert page.evaluate("""() => { const r = document.getElementById('search').getBoundingClientRect();
      return document.getElementById('search').contains(document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2)); }""")
    page.keyboard.type("乙")
    page.wait_for_function("() => deskTest.S.visible.length === 1")
    assert errors == []


def test_a_late_older_snapshot_does_not_close_the_message_just_opened(env):
    """按 U 之后的 refreshNow 回应晚到了，比更新的长轮询还晚：以前界面被倒回旧版本，刚点开的新消息不在旧版本里，阅读区被关掉。"""
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="甲", body="x")
    store.poll()
    open_page(page, server)
    page.evaluate(SLOW_FETCH)
    page.click(f'.item[data-id="{a}"]')
    page.evaluate("window.__slow = 'since=-1'")
    page.keyboard.press("u")  # 标为未读 → refreshNow(true)，回应被拖 0.7 秒
    page.wait_for_timeout(150)
    b = post(d, kind="answer", title="新来的", body="x")
    page.wait_for_selector(f'.item[data-id="{b}"]')
    page.click(f'.item[data-id="{b}"]')
    page.wait_for_function("() => window.__slow === null")
    page.wait_for_timeout(900)  # 晚到的旧快照已经到了
    assert page.evaluate("deskTest.S.current") == b
    assert page.inner_text("#title") == "新来的" and page.locator(f'.item[data-id="{b}"].selected').count() == 1
    assert errors == []


def test_dwell_timer_does_not_override_an_explicit_unread(env):
    """j 停到一条未读上（0.8 秒后才算读），马上按 U 标已读、再按 Z 撤销（改回未读）：以前计时一到又把它标成已读。"""
    d, store, server, page, errors = env
    for i in range(3):
        post(d, kind="answer", title=f"消息 {i}", body="x")
    store.poll()
    open_page(page, server)
    page.focus("#list")
    page.keyboard.press("j")
    cur = page.evaluate("deskTest.S.current")
    page.keyboard.press("u")
    assert wait_until(lambda: cur in store.read)
    page.wait_for_selector(".toast button >> text=撤销")
    page.keyboard.press("z")
    assert wait_until(lambda: cur not in store.read)
    page.wait_for_timeout(1000)  # 停留计时早就过了
    assert cur not in store.read
    assert page.locator(f'.item[data-id="{cur}"].unread').count() == 1
    assert errors == []


def test_focus_returns_to_the_list_after_removing_with_buttons(env):
    """用行上的按钮 / 批量栏归档、删除以后，有焦点的按钮没了：以前焦点掉到 body（焦点环没了，Tab 从头开始）。"""
    d, store, server, page, errors = env
    for i in range(8):
        post(d, kind="answer", title=f"消息 {i}", body="x")
    store.poll()
    open_page(page, server)
    page.click(".item >> nth=0")
    row = page.locator(".item").nth(1)
    row.hover()
    row.locator('[data-act="delete"]').click()
    page.click("#modalOk")
    page.wait_for_function("() => deskTest.S.visible.length === 7")
    assert page.evaluate(FOCUSED, "#list")
    row = page.locator(".item").nth(1)
    row.hover()
    row.locator('[data-act="archive"]').click()
    page.wait_for_function("() => deskTest.S.visible.length === 6")
    assert page.evaluate(FOCUSED, "#list")
    page.click(".item >> nth=0", modifiers=["Control"])
    page.click(".item >> nth=1", modifiers=["Control"])
    page.focus('#bulkbar [data-bulk="archive"]')
    page.keyboard.press("Enter")
    page.wait_for_function("() => deskTest.S.visible.length === 4")
    assert page.evaluate(FOCUSED, "#list")
    page.click(".item >> nth=0", modifiers=["Control"])
    page.focus('#bulkbar [data-bulk="delete"]')
    page.keyboard.press("Enter")
    page.wait_for_selector("#modal:not([hidden])")
    page.keyboard.press("Enter")
    page.wait_for_function("() => deskTest.S.visible.length === 3")
    assert page.evaluate(FOCUSED, "#list")
    for what in ("clear", "read"):  # 批量栏收起来的别的路：取消选择、标为已读
        page.click(".item >> nth=0", modifiers=["Control"])
        page.focus(f'#bulkbar [data-bulk="{what}"]')
        page.keyboard.press("Enter")
        page.wait_for_function("() => document.getElementById('bulkbar').hidden")
        assert page.evaluate(FOCUSED, "#list"), what
    assert errors == []


def test_deleted_rows_do_not_flash_back_while_the_delete_is_in_flight(env):
    """删除还在路上时，别的变化先唤醒了长轮询（快照里还有要删的那几条）：以前它们回到列表里，还被当成新消息高亮。"""
    d, store, server, page, errors = env
    ids = [post(d, kind="decision", title=f"决定 {i}", options=["A", "B"]) for i in range(3)]
    store.poll()

    def bump():
        post(d, kind="info", title="插队的", body="x")
        store.poll()

    slow_action(server, "delete", before=0.5, first=bump)
    open_page(page, server)
    for i in ids[:2]:
        page.click(f'.item[data-id="{i}"] .t', modifiers=["Control"])
    page.keyboard.press("Delete")
    page.click("#modalOk")
    page.wait_for_selector(".item >> text=插队的")  # 旧快照已经到了，删除还在路上
    assert page.evaluate("ids => ids.filter(id => document.querySelector('.item[data-id=\"' + id + '\"]'))", ids[:2]) == []
    assert page.evaluate("ids => ids.filter(id => deskTest.S.fresh[id])", ids[:2]) == []
    assert wait_until(lambda: all(i in store.deleted for i in ids[:2]))
    page.wait_for_selector(".toast >> text=已删除 2 条")
    assert page.locator(".item").count() == 2
    assert errors == []


def test_enter_after_clicking_the_queue_strip_stays_on_the_decision(env):
    """用鼠标点了队列条，焦点留在它上面：以前按 1 选好、再按 Enter（写补充说明）等于又点了一次队列条，跳到了另一条决定。"""
    d, store, server, page, errors = env
    a = post(d, kind="decision", title="先来的", options=["x", "y"], allow_text=True)
    time.sleep(0.01)
    post(d, kind="decision", title="后来的", options=["x", "y"], allow_text=True)
    store.poll()
    open_page(page, server)
    page.click("#queueBtn")
    assert page.evaluate("deskTest.S.current") == a
    page.wait_for_selector("#options .opt")
    page.keyboard.press("1")
    page.keyboard.press("Enter")
    assert page.evaluate("deskTest.S.current") == a
    assert page.evaluate(FOCUSED, "#replyText")
    # 键盘按的队列条（Tab 过去按 Enter）照旧：焦点留在条上，可以接着按
    page.focus("#queueBtn")
    page.keyboard.press("Enter")
    assert page.evaluate("deskTest.S.current") != a and page.evaluate(FOCUSED, "#queueBtn")
    assert errors == []


def test_a_late_detail_does_not_reopen_a_decision_closed_in_chat(env):
    """点开一条决定，详情还在路上时会话用 desk.py close 在对话里处理掉了：已回复的版本先显示，
    晚到的"未回复"版本以前又盖了上去（选项能点、回复框回来了，提交只会报"已经回复过了"）。"""
    d, store, server, page, errors = env
    other = post(d, kind="answer", title="先看这条", body="x")
    a = post(d, kind="decision", title="要决定的", options=["甲", "乙"], allow_text=True)
    store.poll()
    open_page(page, server)
    page.click(f'.item[data-id="{other}"]')
    page.wait_for_selector("#title >> text=先看这条")
    page.evaluate(SLOW_FETCH)
    page.evaluate("window.__slow = '/api/message'")
    page.click(f'.item[data-id="{a}"]')
    m = desk.find_message(a, d)
    desk.write_response(a, None, "（已在对话中处理）", m["source"], d, extra={"title": m["title"], "closed_by": "claude"})
    page.wait_for_selector("#doneBox:not([hidden]) >> text=已在对话中处理")
    page.wait_for_timeout(900)  # 晚到的"未回复"详情已经到了
    assert page.evaluate("deskTest.S.shownKey") == a + "|true"
    assert page.is_visible("#doneBox") and page.is_hidden("#replyText")
    assert page.locator("#options .opt:not([disabled])").count() == 0
    assert errors == []


def test_enter_in_search_waits_for_the_results_in_flight(env):
    """防抖已过、搜索请求还在路上时按 Enter：以前打开的是没筛过的列表里的第一条（不是搜索结果）。"""
    d, store, server, page, errors = env
    for i in range(3):
        post(d, kind="answer", title=f"普通 {i}", body="x")
    hit = post(d, kind="answer", title="目标 needle", body="x")
    for i in range(3):
        post(d, kind="answer", title=f"后来的 {i}", body="x")
    store.poll()
    open_page(page, server)
    page.evaluate(SLOW_FETCH)
    page.evaluate("window.__slow = '/api/search'")
    page.keyboard.press("/")
    page.keyboard.type("needle")
    page.wait_for_timeout(250)  # 防抖（120 ms）已过，请求还在路上
    page.keyboard.press("Enter")
    page.wait_for_function("id => deskTest.S.current === id", arg=hit)
    assert page.evaluate("deskTest.S.visible") == [hit] and page.evaluate(FOCUSED, "#list")
    assert errors == []


def test_opening_a_message_clears_the_narrow_list_cursor(env):
    """窄窗口：列表页 ↓ 挪的光标在点开另一条之后不能还画着（只重画了新选中的那一行，旧光标行留着灰底）。"""
    d, store, server, page, errors = env
    ids = [post(d, kind="answer", title=f"消息 {i}", body="x") for i in range(3)]
    store.poll()
    store.mark_read(ids)  # 都读过：点开不会引起服务端变化、整份重画，旧光标行只能靠 select 自己清
    page.set_viewport_size({"width": 600, "height": 800})
    open_page(page, server)
    page.focus("#list")
    page.keyboard.press("j")
    page.keyboard.press("j")
    assert page.locator(".item.cursor").count() == 1
    page.click(f'.item[data-id="{ids[0]}"]')
    page.wait_for_selector("#app.reading")
    assert page.locator(".item.cursor").count() == 0
    assert errors == []


def test_closing_a_dialog_opened_from_nowhere_puts_focus_on_the_list(env):
    """对话框打开前焦点在 body：关掉以后焦点回列表，不停在藏起来的"确定"按钮上（之后的按键都失灵）。"""
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="甲", body="x")
    store.poll()
    open_page(page, server)
    page.click(f'.item[data-id="{a}"]')
    page.evaluate("document.activeElement.blur()")
    page.keyboard.press("Delete")
    page.wait_for_selector("#modal:not([hidden])")
    page.keyboard.press("Escape")
    page.wait_for_selector("#modal", state="hidden")
    assert page.evaluate("document.activeElement.id") == "list"
    assert errors == []
