"""项目标签：关掉（×、中键、右键）、有待决定时先确认、撤销；"已关闭 N"和设置里找回；新消息 / 点旧通知自动找回；
搜索不含关掉的；"未归类"只在有没归档的消息时才有标签；顶栏没有图标，"全部项目"和列表对齐。"""
from test_ui import env, post  # noqa: F401（env 是 fixture）
from test_ui_state import wait_until

VIS = "k => getComputedStyle(document.querySelector(`.ptab[data-project=\"${k}\"] .pclose`)).visibility"
BOXES = "() => [...document.querySelectorAll('.ptab')].map(e => { const r = e.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.width)]; })"


def start(page, server):
    page.goto(server.url)
    page.wait_for_function("window.deskTest && deskTest.S.version >= 0")
    page.wait_for_selector(".item")


def tabs(page):
    return page.evaluate("[...document.querySelectorAll('#projects .ptab')].map(t => t.dataset.project)")


def scope(page):
    return page.evaluate("Array.from(deskTest.S.projects)")


def gone(page, key):
    page.wait_for_function("k => !document.querySelector(`.ptab[data-project=\"${k}\"]`)", arg=key)


def seed(d, store):
    ids = {
        "a_dec": post(d, kind="decision", title="甲的决定", options=["A", "B"], repo="alpha"),
        "a_ans": post(d, kind="answer", title="甲的回答", body="甲 正文", repo="alpha"),
        "b_ans": post(d, kind="answer", title="乙的回答 独有词", body="乙 正文", repo="beta"),
        "b_info": post(d, kind="info", title="乙的通知", body="x", repo="beta"),
        "c_ans": post(d, kind="answer", title="丙的回答", body="x", repo="gamma"),
    }
    store.poll()
    return ids


def test_close_a_tab_with_its_x_then_undo(env):
    d, store, server, page, errors = env
    ids = seed(d, store)
    start(page, server)
    assert tabs(page) == ["", "alpha", "beta", "gamma"]
    b0 = page.evaluate(BOXES)
    assert page.evaluate(VIS, "beta") == "hidden" and page.locator(".ptab.all .pclose").count() == 0  # "全部项目"关不掉
    page.hover('.ptab[data-project="beta"]')
    assert page.evaluate(VIS, "beta") == "visible" and page.evaluate(BOXES) == b0  # 悬停才出现；一直占着位置，标签不变宽、不挪
    page.click('.ptab[data-project="beta"]')
    page.mouse.move(600, 500)
    assert page.evaluate(VIS, "beta") == "visible" and page.evaluate(VIS, "alpha") == "hidden"  # 选中的一直显示
    assert page.evaluate(BOXES) == b0
    # 点 ×：没有待决定，不问；标签和它的消息都不见了，选择回到"全部项目"
    page.click('.ptab[data-project="beta"] .pclose')
    gone(page, "beta")
    assert page.locator("#modal").is_hidden() and scope(page) == []
    vis = page.evaluate("deskTest.S.visible")
    assert ids["b_ans"] not in vis and ids["b_info"] not in vis and ids["a_ans"] in vis
    assert wait_until(lambda: store.hidden_projects == {"beta"})
    toast = page.locator(".toast", has_text="已关闭「beta」")
    toast.wait_for()
    assert toast.locator("button").inner_text() == "撤销（Z）"
    # 哪个数都不算它：视图标签、窗口标题（服务端的计数，托盘 / 任务栏用的也是它）
    page.wait_for_function("() => document.title === 'ClaudeDesk · 1 待决定 · 3 未读'")
    assert page.inner_text('.tab[data-view="all"] .n') == "3"
    assert store.counts()["unread"] == 3
    # 右头"已关闭 1"
    btn = page.locator("#closedBtn")
    assert btn.is_visible() and "已关闭" in btn.inner_text() and btn.inner_text().strip().endswith("1")
    assert btn.get_attribute("title") == "已关闭 1 个标签：它们的消息不显示、不计数。点开找回"
    # Z：标签回来，还选着它
    page.keyboard.press("z")
    page.wait_for_selector('.ptab[data-project="beta"].on')
    assert wait_until(lambda: store.hidden_projects == set())
    assert scope(page) == ["beta"] and tabs(page) == ["", "alpha", "beta", "gamma"]
    btn.wait_for(state="hidden")
    assert errors == []


def test_closing_a_tab_with_open_decisions_asks_first(env):
    d, store, server, page, errors = env
    seed(d, store)
    start(page, server)
    page.click('.ptab[data-project="alpha"]', button="middle")  # 中键 = 关（和浏览器一样）
    page.wait_for_selector("#modal:not([hidden])")
    assert page.inner_text("#modalTitle") == "关闭「alpha」？"
    assert page.inner_text("#modalText") == "「alpha」还有 1 条待决定没回复。关掉后它们不再显示、也不计入未读；这个项目来新消息时标签会自动回来。"
    assert page.inner_text("#modalOk") == "关闭"
    page.click("#modalCancel")
    assert tabs(page) == ["", "alpha", "beta", "gamma"] and store.hidden_projects == set()
    # 右键菜单：归到…，最后是"关闭这个标签"
    page.click('.ptab[data-project="alpha"]', button="right")
    page.wait_for_selector("#popover:not([hidden])")
    assert page.locator('#popover [data-to="beta"]').count() == 1
    assert page.locator("#popover .menu-item").last.get_attribute("data-close") is not None
    page.click("#popover [data-close]")
    page.wait_for_selector("#modal:not([hidden])")
    page.keyboard.press("Enter")
    gone(page, "alpha")
    assert wait_until(lambda: store.hidden_projects == {"alpha"} and store.counts()["open"] == 0)
    # 待决定都在关掉的标签里：队列条收起，"全部项目"不带胶囊，N 说没有
    assert page.locator("#queueBtn").is_hidden() and page.inner_text(".ptab.all .n") == ""
    page.locator("#list").focus()
    page.keyboard.press("n")
    page.locator(".toast", has_text="没有待决定的事").wait_for()
    # [ ] 只在开着的标签之间转
    page.keyboard.press("]")
    assert scope(page) == ["beta"]
    page.keyboard.press("[")
    page.keyboard.press("[")
    assert scope(page) == ["gamma"]
    assert errors == []


def test_reopen_from_the_closed_menu_and_from_settings(env):
    d, store, server, page, errors = env
    seed(d, store)
    store.hide_project("beta")
    store.hide_project("gamma")
    start(page, server)
    assert tabs(page) == ["", "alpha"]
    btn = page.locator("#closedBtn")
    assert btn.get_attribute("title").startswith("已关闭 2 个标签")
    # 键盘：焦点在按钮上回车打开；焦点进菜单，↓ 移动，回车找回并选中它
    btn.focus()
    page.keyboard.press("Enter")
    page.wait_for_selector("#popover:not([hidden])")
    rows = page.evaluate("[...document.querySelectorAll('#popover [data-reopen]')].map(b => [b.dataset.reopen, b.querySelector('.sub').textContent])")
    assert rows == [["beta", "2 条"], ["gamma", "1 条"]]
    assert page.locator("#popover .menu-item").last.inner_text() == "全部恢复"
    assert page.evaluate("document.activeElement.dataset.reopen") == "beta"
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    page.wait_for_selector('.ptab[data-project="gamma"].on')
    assert scope(page) == ["gamma"] and page.evaluate("document.activeElement.id") == "list"
    assert wait_until(lambda: store.hidden_projects == {"beta"})
    page.wait_for_function("() => document.getElementById('closedBtn').title.startsWith('已关闭 1 个标签')")
    page.click("#closedBtn")
    assert page.locator("#popover [data-reopen-all]").count() == 0  # 只有一个：不要"全部恢复"
    page.keyboard.press("Escape")
    # 重新打开窗口还关着（存在服务端）；设置里也能找回，不改当前选的标签
    page.reload()
    page.wait_for_selector(".item")
    assert tabs(page) == ["", "alpha", "gamma"] and btn.is_visible()
    page.keyboard.press("Control+,")
    page.wait_for_selector("#popover.settings:not([hidden])")
    row = page.locator('#popover [data-reopen="beta"]')
    assert row.locator(".sub").inner_text() == "恢复"
    assert page.locator("#popover .menu-item").last.get_attribute("data-app") == "shortcuts"
    row.click()
    page.wait_for_selector('.ptab[data-project="beta"]')
    assert wait_until(lambda: store.hidden_projects == set())
    assert scope(page) == ["gamma"] and page.locator('#popover [data-reopen="beta"]').count() == 0
    btn.wait_for(state="hidden")
    page.keyboard.press("Escape")
    # 全部恢复
    store.hide_project("alpha")
    store.hide_project("beta")
    page.wait_for_function("() => document.getElementById('closedBtn').title.startsWith('已关闭 2 个标签')")
    page.click("#closedBtn")
    page.click("#popover [data-reopen-all]")
    page.wait_for_function("() => document.querySelectorAll('#projects .ptab').length === 4")
    assert wait_until(lambda: store.hidden_projects == set())
    btn.wait_for(state="hidden")
    assert errors == []


def test_a_new_message_or_a_notification_click_brings_a_closed_tab_back(env):
    d, store, server, page, errors = env
    ids = seed(d, store)
    store.hide_project("alpha")
    store.hide_project("gamma")
    start(page, server)
    page.click('.ptab[data-project="beta"]')
    # 关掉的项目来了新消息：服务端把标签放回来，照常提示（只看 beta，所以弹提示）
    n = post(d, kind="decision", title="甲又来一个决定", options=["好"], repo="alpha")
    page.wait_for_selector('.ptab[data-project="alpha"]')
    page.locator(".toast", has_text="alpha 需要你决定：甲又来一个决定").wait_for()
    assert store.hidden_projects == {"gamma"} and store.counts()["open"] == 2
    assert page.evaluate("id => !!deskTest.S.byId[id]", n)
    # 新到的不能把找回来的旧消息也当成新的（只弹一条）
    assert page.locator(".toast", has_text="需要你决定").count() == 1
    # 点旧通知打开关掉的标签里的消息：先找回标签，切过去，打开它
    page.evaluate("id => deskOpen(id)", ids["c_ans"])
    page.wait_for_function("() => document.getElementById('title').textContent === '丙的回答'")
    assert scope(page) == ["gamma"] and page.locator('.ptab[data-project="gamma"].on').count() == 1
    assert wait_until(lambda: store.hidden_projects == set())
    assert errors == []


def test_search_leaves_out_closed_tabs_and_offers_to_bring_them_back(env):
    d, store, server, page, errors = env
    ids = seed(d, store)
    store.hide_project("beta")
    start(page, server)
    page.fill("#search", "独有词")
    page.wait_for_selector(".search-more")
    assert page.locator(".item").count() == 0
    assert page.inner_text(".search-more").startswith("另有 1 条在已关闭的标签里")
    page.click("[data-more-closed]")
    page.wait_for_selector(f'.item[data-id="{ids["b_ans"]}"]')
    assert wait_until(lambda: store.hidden_projects == set())
    assert page.evaluate("deskTest.S.view") == "all" and scope(page) == []
    # 两种都有：各一行
    store.hide_project("beta")
    gone(page, "beta")
    page.click('[data-view="decide"]')
    page.fill("#search", "正文")
    page.wait_for_function("() => document.querySelectorAll('.search-more').length === 2")
    texts = page.locator(".search-more").all_inner_texts()
    assert texts[0].startswith("另有 1 条在其他视图或项目里") and texts[1].startswith("另有 1 条在已关闭的标签里")
    assert errors == []


def test_unsorted_tab_only_when_it_has_unarchived_messages(env):
    d, store, server, page, errors = env
    post(d, kind="answer", title="甲", body="x", repo="alpha")
    o1 = post(d, kind="info", title="旧来源一", body="x", source="随手记")
    o2 = post(d, kind="info", title="旧来源二", body="x", source="老实验")
    store.poll()
    store.archive([o1])
    start(page, server)
    assert tabs(page) == ["", "alpha", "__other__"]
    # 归档掉最后一条没归档的：标签不见了；归档视图里它们照样按来源分组
    page.click(f'.item[data-id="{o2}"]')
    page.keyboard.press("e")
    gone(page, "__other__")
    page.click('[data-view="archive"]')
    page.wait_for_selector(f'.item[data-id="{o1}"]')
    assert sorted(page.locator(".group-label.other .gname").all_inner_texts()) == ["老实验", "随手记"]
    page.reload()  # 一开始就只有归档的：没有这个标签
    page.wait_for_selector(".ptab")
    assert tabs(page) == ["", "alpha"]
    # 来了新的：标签回来；右键它只有"关闭这个标签"（归类在分组标题上做）
    post(d, kind="info", title="旧来源三", body="x", source="老实验")
    page.wait_for_selector('.ptab[data-project="__other__"]')
    page.click('.ptab[data-project="__other__"]', button="right")
    page.wait_for_selector("#popover:not([hidden])")
    assert page.locator("#popover button").count() == 1
    page.click("#popover [data-close]")
    gone(page, "__other__")
    assert wait_until(lambda: store.hidden_projects == {"__other__"})
    page.click('[data-view="archive"]')  # 关掉的标签：归档里的也不显示
    assert page.locator(".item").count() == 0
    assert errors == []


def test_top_bar_has_no_logo_and_lines_up_with_the_list(env):
    d, store, server, page, errors = env
    post(d, kind="decision", title="甲的决定", options=["A"], repo="alpha")
    post(d, kind="answer", title="乙的回答", body="x", repo="beta")
    store.poll()
    start(page, server)
    assert page.locator(".topbar > svg, .mark").count() == 0  # 窗口标题栏和任务栏已经有图标
    assert page.evaluate("document.querySelector('.topbar').firstElementChild.id") == "projects"
    xs = page.evaluate("""() => { const r = document.createRange(), t = document.querySelector('.ptab.all').firstChild;
        r.selectNodeContents(t); return { allText: Math.round(r.getBoundingClientRect().left),
          searchIcon: Math.round(document.querySelector('.search i').getBoundingClientRect().left) }; }""")
    assert xs == {"allText": 20, "searchIcon": 20}  # "全部项目"的字落在列表的图标列上
    assert errors == []
