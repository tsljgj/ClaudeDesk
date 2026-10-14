"""项目标签：关掉（×、中键、右键）、有待决定时先确认、撤销；"已关闭 N"和设置里找回；新消息 / 点旧通知自动找回；
搜索不含关掉的；"未归类"只在有没归档的消息时才有标签；顶栏没有图标，第一个标签和列表对齐。
没有"全部项目"：默认选哪个、选择不能是空的、关掉选着的标签选邻居、标签都关掉时的空状态、[ ] 切换、
N 跨项目、从通知打开别的项目的消息、搜索结果在别的项目里时按项目给按钮。"""
import datetime as dt
import json

import desk

from test_ui import env, post  # noqa: F401（env 是 fixture）
from test_ui_state import SAME, wait_until

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


def ago(d, minutes, **kw):
    """发一条 minutes 分钟前的消息（默认选择要比时间先后，不能靠连着发的几条恰好差几毫秒）。"""
    kw.setdefault("source", "proj")
    m = desk.make_message(**kw)
    m["ts"] = (dt.datetime.now().astimezone() - dt.timedelta(minutes=minutes)).isoformat(timespec="milliseconds")
    return desk.post_message(m, d)


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
    assert tabs(page) == ["alpha", "beta", "gamma"] and page.locator(".ptab.all").count() == 0  # 没有"全部项目"
    assert "全部项目" not in page.inner_text("#projects")
    b0 = page.evaluate(BOXES)
    assert page.evaluate(VIS, "beta") == "hidden"
    page.hover('.ptab[data-project="beta"]')
    assert page.evaluate(VIS, "beta") == "visible" and page.evaluate(BOXES) == b0  # 悬停才出现；一直占着位置，标签不变宽、不挪
    page.click('.ptab[data-project="beta"]')
    page.mouse.move(600, 500)
    assert page.evaluate(VIS, "beta") == "visible" and page.evaluate(VIS, "alpha") == "hidden"  # 选中的一直显示
    assert page.evaluate(BOXES) == b0
    # 点 ×：没有待决定，不问；标签和它的消息都不见了，选择换到右边的邻居
    page.click('.ptab[data-project="beta"] .pclose')
    gone(page, "beta")
    assert page.locator("#modal").is_hidden() and scope(page) == ["gamma"]
    assert page.locator('.ptab[data-project="gamma"].on').count() == 1
    vis = page.evaluate("deskTest.S.visible")
    assert ids["b_ans"] not in vis and ids["b_info"] not in vis and vis == [ids["c_ans"]]
    assert wait_until(lambda: store.hidden_projects == {"beta"})
    toast = page.locator(".toast", has_text="已关闭「beta」")
    toast.wait_for()
    assert toast.locator("button").inner_text() == "撤销（Z）"
    # 哪个数都不算它：视图标签、窗口标题（服务端的计数，托盘 / 任务栏用的也是它）
    page.wait_for_function("() => document.title === 'ClaudeDesk · 1 待决定 · 3 未读'")
    assert page.inner_text('.tab[data-view="all"] .n') == "1"
    page.click('.ptab[data-project="alpha"]', modifiers=["Control"])  # 两个开着的都选上：未读数里还是没有它
    page.wait_for_function("() => document.querySelector('.tab[data-view=\"all\"] .n').textContent === '3'")
    assert store.counts()["unread"] == 3
    # 右头"已关闭 1"
    btn = page.locator("#closedBtn")
    assert btn.is_visible() and "已关闭" in btn.inner_text() and btn.inner_text().strip().endswith("1")
    assert btn.get_attribute("title") == "已关闭 1 个标签：它们的消息不显示、不计数。点开找回"
    # Z：标签回来，选择回到关之前（只选着它）
    page.keyboard.press("z")
    page.wait_for_selector('.ptab[data-project="beta"].on')
    assert wait_until(lambda: store.hidden_projects == set())
    assert scope(page) == ["beta"] and tabs(page) == ["alpha", "beta", "gamma"]
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
    assert tabs(page) == ["alpha", "beta", "gamma"] and store.hidden_projects == set()
    assert scope(page) == ["alpha"]  # 默认选有待决定的那个
    # 右键菜单：归到…，最后是"关闭这个标签"
    page.click('.ptab[data-project="alpha"]', button="right")
    page.wait_for_selector("#popover:not([hidden])")
    assert page.locator('#popover [data-to="beta"]').count() == 1
    assert page.locator("#popover .menu-item").last.get_attribute("data-close") is not None
    page.click("#popover [data-close]")
    page.wait_for_selector("#modal:not([hidden])")
    page.keyboard.press("Enter")
    gone(page, "alpha")
    assert scope(page) == ["beta"]  # 关的是选着的：换到右边的邻居
    assert wait_until(lambda: store.hidden_projects == {"alpha"} and store.counts()["open"] == 0)
    # 待决定都在关掉的标签里：队列条收起，哪个标签都不带胶囊，N 说没有
    assert page.locator("#queueBtn").is_hidden() and page.locator("#projects .n.hot").count() == 0
    page.locator("#list").focus()
    page.keyboard.press("n")
    page.locator(".toast", has_text="没有待决定的事").wait_for()
    # [ ] 只在开着的标签之间转（关掉的 alpha 不算），到头绕回来
    page.keyboard.press("]")
    assert scope(page) == ["gamma"]
    page.keyboard.press("]")
    assert scope(page) == ["beta"]
    page.keyboard.press("[")
    assert scope(page) == ["gamma"]
    assert errors == []


def test_reopen_from_the_closed_menu_and_from_settings(env):
    d, store, server, page, errors = env
    seed(d, store)
    store.hide_project("beta")
    store.hide_project("gamma")
    start(page, server)
    assert tabs(page) == ["alpha"] and scope(page) == ["alpha"]
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
    assert tabs(page) == ["alpha", "gamma"] and btn.is_visible()
    assert scope(page) == ["gamma"]  # 选择也记着（存在本机）
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
    page.wait_for_function("() => document.querySelectorAll('#projects .ptab').length === 3")
    assert wait_until(lambda: store.hidden_projects == set())
    btn.wait_for(state="hidden")
    assert scope(page) == ["gamma"]  # 全部恢复不改当前选的
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
    assert page.evaluate("deskTest.S.view") == "all" and scope(page) == ["beta"]  # 只选找回的那个，不是大杂烩
    # 两种都有：各一行（选着的 beta 在服务端被关掉：按默认的换到有待决定的 alpha）
    store.hide_project("beta")
    gone(page, "beta")
    assert scope(page) == ["alpha"]
    page.click('[data-view="decide"]')
    page.fill("#search", "正文")
    page.wait_for_function("() => document.querySelectorAll('.search-more').length === 2")
    texts = page.locator(".search-more").all_inner_texts()
    assert texts[0].startswith("另有 1 条在其他视图里") and texts[1].startswith("另有 1 条在已关闭的标签里")
    assert errors == []


def test_unsorted_tab_only_when_it_has_unarchived_messages(env):
    d, store, server, page, errors = env
    ago(d, 10, kind="answer", title="甲", body="x", repo="alpha")
    o1 = ago(d, 20, kind="info", title="旧来源一", body="x", source="随手记")
    o2 = ago(d, 1, kind="info", title="旧来源二", body="x", source="老实验")
    store.poll()
    store.archive([o1])
    start(page, server)
    assert tabs(page) == ["alpha", "__other__"]
    assert scope(page) == ["__other__"]  # 没有待决定：默认选最近来过消息的
    # 归档掉最后一条没归档的：标签不见了，选择换到还在的 alpha；归档视图里它又有标签，选上它，里面照样按来源分组
    page.click(f'.item[data-id="{o2}"]')
    page.keyboard.press("e")
    gone(page, "__other__")
    assert scope(page) == ["alpha"]
    page.click('[data-view="archive"]')
    page.click('.ptab[data-project="__other__"]')
    page.wait_for_selector(f'.item[data-id="{o1}"]')
    assert sorted(page.locator(".group-label.other .gname").all_inner_texts()) == ["老实验", "随手记"]
    page.reload()  # 一开始就只有归档的：没有这个标签（记着的选择是它，也只好换成 alpha）
    page.wait_for_selector('.ptab[data-project="alpha"]')
    assert tabs(page) == ["alpha"] and scope(page) == ["alpha"]
    # 来了新的：标签回来；右键它只有"关闭这个标签"（归类在分组标题上做）
    post(d, kind="info", title="旧来源三", body="x", source="老实验")
    page.wait_for_selector('.ptab[data-project="__other__"]')
    page.click('.ptab[data-project="__other__"]')
    page.click('.ptab[data-project="__other__"]', button="right")
    page.wait_for_selector("#popover:not([hidden])")
    assert page.locator("#popover button").count() == 1
    page.click("#popover [data-close]")
    gone(page, "__other__")
    assert wait_until(lambda: store.hidden_projects == {"__other__"})
    assert scope(page) == ["alpha"]  # 关的是选着的、右边没有了：换到左边的
    page.click('[data-view="archive"]')  # 关掉的标签：归档里也没有它的标签、它的消息也不显示
    assert tabs(page) == ["alpha"] and page.locator(".item").count() == 0
    assert errors == []


def test_top_bar_has_no_logo_and_lines_up_with_the_list(env):
    d, store, server, page, errors = env
    post(d, kind="decision", title="甲的决定", options=["A"], repo="alpha")
    post(d, kind="answer", title="乙的回答", body="x", repo="beta")
    store.poll()
    start(page, server)
    assert page.locator(".topbar > svg, .mark").count() == 0  # 窗口标题栏和任务栏已经有图标
    assert page.evaluate("document.querySelector('.topbar').firstElementChild.id") == "projects"
    page.wait_for_selector('.ptab[data-project="alpha"]')
    xs = page.evaluate("""() => ({ firstDot: Math.round(document.querySelector('#projects .ptab .pdot').getBoundingClientRect().left),
          searchIcon: Math.round(document.querySelector('.search i').getBoundingClientRect().left) })""")
    assert xs == {"firstDot": 20, "searchIcon": 20}  # 第一个标签的圆点落在列表的图标列上
    assert errors == []


def reopen_keys(page):
    return page.evaluate("[...document.querySelectorAll('#popover [data-reopen]')].map(b => b.dataset.reopen)")


def test_default_selection_saved_then_oldest_decision_then_latest(env):
    """启动时选谁：记着的选择（标签还在、没关的那些）→ 有最久待决定的项目 → 最近来过消息的项目。"""
    d, store, server, page, errors = env
    ago(d, 5, kind="answer", title="甲的回答", body="x", repo="alpha")
    ago(d, 1, kind="answer", title="乙的回答", body="x", repo="beta")
    ago(d, 30, kind="answer", title="丙的回答", body="x", repo="gamma")
    store.poll()
    # 没有待决定：最近来过消息的
    start(page, server)
    assert scope(page) == ["beta"] and page.locator(".ptab.on").count() == 1
    assert page.locator('.ptab[data-project="beta"]').get_attribute("aria-selected") == "true"
    # 有待决定：等得最久的那条所在的项目（不管谁的消息最新）
    ago(d, 20, kind="decision", title="丙的决定", options=["A"], repo="gamma")
    ago(d, 3, kind="decision", title="甲的决定", options=["A"], repo="alpha")
    store.poll()
    page.evaluate("localStorage.removeItem('desk.projects')")
    page.goto("about:blank")
    start(page, server)
    assert scope(page) == ["gamma"]
    # 记着的选择：重新打开还是它（多选也一样）
    page.click('.ptab[data-project="alpha"]')
    page.click('.ptab[data-project="beta"]', modifiers=["Control"])
    assert json.loads(page.evaluate("localStorage.getItem('desk.projects')")) == ["alpha", "beta"]
    page.goto("about:blank")
    start(page, server)
    assert sorted(scope(page)) == ["alpha", "beta"]
    # 记着的里有关掉了的：只留开着的那些
    page.goto("about:blank")
    store.hide_project("beta")
    start(page, server)
    assert scope(page) == ["alpha"]
    # 记着的都关掉了：回到有最久待决定的项目（关掉的 alpha 里的决定不算）
    page.goto("about:blank")
    store.hide_project("alpha")
    start(page, server)
    assert scope(page) == ["gamma"] and tabs(page) == ["gamma"]
    assert errors == []


def test_closing_the_selected_tab_selects_a_neighbour_and_all_closed_shows_a_way_back(env):
    d, store, server, page, errors = env
    for i, k in enumerate(["alpha", "beta", "gamma"]):
        ago(d, 10 - i, kind="answer", title=f"{k} 的回答", body="x", repo=k)
    store.poll()
    start(page, server)
    page.click('.ptab[data-project="beta"]')

    def close(k):
        page.hover(f'.ptab[data-project="{k}"]')
        page.click(f'.ptab[data-project="{k}"] .pclose')
        gone(page, k)

    close("beta")  # 右边有：选右边的
    assert scope(page) == ["gamma"] and page.locator('.ptab[data-project="gamma"].on').count() == 1
    assert page.evaluate("deskTest.S.visible.length") == 1
    close("gamma")  # 右边没有了：选左边的
    assert scope(page) == ["alpha"]
    close("alpha")  # 一个都不剩：列表说清楚，给个找回的入口
    page.wait_for_selector(".list-empty [data-reopen-menu]")
    assert scope(page) == [] and page.locator("#projects .ptab").count() == 0 and page.locator(".item").count() == 0
    assert page.inner_text(".list-empty b") == "项目标签都关掉了"
    assert "来新消息时标签会自动回来" in page.inner_text(".list-empty")
    assert page.inner_text(".list-empty [data-reopen-menu]") == "找回标签…"
    # 点它：打开和"已关闭 N"同一个菜单；找回一个就选中它
    page.click(".list-empty [data-reopen-menu]")
    page.wait_for_selector("#popover:not([hidden]) [data-reopen-all]")
    assert reopen_keys(page) == ["alpha", "beta", "gamma"]
    page.click('#popover [data-reopen="beta"]')
    page.wait_for_selector('.ptab[data-project="beta"].on')
    assert scope(page) == ["beta"] and page.locator(".list-empty").count() == 0
    assert wait_until(lambda: store.hidden_projects == {"alpha", "gamma"})
    # 多选时关掉其中一个：剩下的照旧选着
    page.click("#closedBtn")
    page.click("#popover [data-reopen-all]")
    page.wait_for_function("() => document.querySelectorAll('#projects .ptab').length === 3")
    page.click('.ptab[data-project="gamma"]', modifiers=["Control"])
    close("beta")
    assert scope(page) == ["gamma"]
    assert errors == []


def test_brackets_cycle_through_open_tabs_only(env):
    d, store, server, page, errors = env
    seed(d, store)
    store.hide_project("gamma")
    ago(d, 1, kind="answer", title="丁的回答", body="x", repo="delta")
    store.poll()
    start(page, server)
    assert tabs(page) == ["alpha", "beta", "delta"] and scope(page) == ["alpha"]
    page.locator("#list").focus()
    seen = []
    for k in ["]", "]", "]", "["]:
        page.keyboard.press(k)
        seen.append(scope(page))
    assert seen == [["beta"], ["delta"], ["alpha"], ["delta"]]  # 关掉的 gamma 不算；到头绕回来；没有"全部项目"那一格
    # 多选时：] 从选着的最右那个往右，[ 从最左那个往左
    page.click('.ptab[data-project="alpha"]')
    page.click('.ptab[data-project="beta"]', modifiers=["Control"])
    page.locator("#list").focus()
    page.keyboard.press("]")
    assert scope(page) == ["delta"]
    page.click('.ptab[data-project="beta"]', modifiers=["Control"])
    page.locator("#list").focus()
    page.keyboard.press("[")
    assert scope(page) == ["alpha"]
    # 只剩一个开着的标签：[ ] 不动
    store.hide_project("beta")
    store.hide_project("delta")
    page.wait_for_function("() => document.querySelectorAll('#projects .ptab').length === 1")
    page.keyboard.press("]")
    page.keyboard.press("[")
    assert scope(page) == ["alpha"]
    assert errors == []


def test_n_moves_through_this_project_then_crosses_to_the_oldest_decision(env):
    d, store, server, page, errors = env
    a1 = ago(d, 30, kind="decision", title="甲一", options=["A"], repo="alpha")
    a2 = ago(d, 10, kind="decision", title="甲二", options=["A"], repo="alpha")
    g1 = ago(d, 60, kind="decision", title="丙一", options=["A"], repo="gamma")
    b1 = ago(d, 20, kind="decision", title="乙一", options=["A"], repo="beta")
    store.poll()
    start(page, server)
    assert scope(page) == ["gamma"]  # 默认：等得最久的那条所在的项目
    page.click('.ptab[data-project="alpha"]')
    assert page.inner_text("#queueBtn span").startswith("2 条待决定")  # 队列条只数这个项目的
    page.locator("#list").focus()
    seq = []
    for _ in range(3):
        page.keyboard.press("n")
        seq.append(page.evaluate("deskTest.S.current"))
    assert seq == [a1, a2, a1] and scope(page) == ["alpha"]  # 这里还有别的：在这个项目里转
    # 这个项目的都回掉了：阅读区说别的项目还有，N 切到等得最久的那个项目、打开那条
    store.submit(a1, "A", "")
    store.submit(a2, "A", "")
    page.wait_for_selector("#queueBtn", state="hidden")
    page.evaluate("document.getElementById('backBtn').click()")
    page.wait_for_function("() => document.querySelector('#empty .empty-lead').textContent === '这里没有待决定的事'")
    assert page.inner_text("#empty .empty-sub") == "其他项目还有 2 条待决定"
    assert page.inner_text("#startBtn") == "去处理（N）"
    page.locator("#list").focus()
    page.keyboard.press("n")
    page.wait_for_function("id => deskTest.S.current === id", arg=g1)
    page.wait_for_function(SAME)
    assert scope(page) == ["gamma"] and page.locator('.ptab[data-project="gamma"].on').count() == 1
    # 正在看的就是这里唯一的一条：N 接着去下一个项目
    page.keyboard.press("n")
    page.wait_for_function("id => deskTest.S.current === id", arg=b1)
    assert scope(page) == ["beta"]
    # 都回掉了：N 说没有，选择不动
    store.submit(g1, "A", "")
    store.submit(b1, "A", "")
    page.wait_for_function("() => !deskTest.S.msgs.some(m => m.open)")
    page.locator("#list").focus()
    page.keyboard.press("n")
    page.locator(".toast", has_text="没有待决定的事").wait_for()
    assert scope(page) == ["beta"]
    assert errors == []


def test_opening_another_projects_message_switches_to_its_project(env):
    d, store, server, page, errors = env
    ids = seed(d, store)
    start(page, server)
    page.click('.ptab[data-project="alpha"]')
    page.click('.ptab[data-project="gamma"]', modifiers=["Control"])
    page.click('[data-view="decide"]')
    # 托盘 / 通知点开 beta 的一条：只选 beta（不是加进多选，也不清空选择），切到看得见它的视图，打开它
    page.evaluate("id => deskOpen(id)", ids["b_ans"])
    page.wait_for_function("id => deskTest.S.current === id", arg=ids["b_ans"])
    page.wait_for_function(SAME)
    assert scope(page) == ["beta"] and page.evaluate("deskTest.S.view") == "answer"
    assert page.locator('.ptab[data-project="beta"].on').count() == 1 and page.locator(".ptab.on").count() == 1
    # 本来就在看的项目里的：选择不动
    page.click('.ptab[data-project="alpha"]', modifiers=["Control"])
    page.evaluate("id => deskOpen(id)", ids["a_ans"])
    page.wait_for_function("id => deskTest.S.current === id", arg=ids["a_ans"])
    assert sorted(scope(page)) == ["alpha", "beta"]
    assert errors == []


def test_search_offers_matches_in_other_projects_as_buttons(env):
    d, store, server, page, errors = env
    a = ago(d, 30, kind="decision", title="发布窗口选哪个", options=["A"], repo="示例项目")
    w = [ago(d, 5 + i, kind="answer", title=f"发布记录 {i}", body="x", repo="webapp") for i in range(3)]
    p = [ago(d, 9 + i, kind="answer", title=f"发布说明 {i}", body="x", repo="acme-data-pipeline") for i in range(2)]
    g = ago(d, 40, kind="answer", title="发布旧稿", body="x", repo="gamma")
    ago(d, 2, kind="answer", title="不相干", body="x", repo="webapp")
    store.poll()
    store.archive([g])
    start(page, server)
    assert scope(page) == ["示例项目"]
    page.fill("#search", "发布")
    page.wait_for_selector(".search-other")
    assert page.evaluate("deskTest.S.visible") == [a]  # 结果只来自当前项目
    # 多的在前（按钮会各自折行，innerText 在按钮前后断行：比文字本身）
    assert page.text_content(".search-other") == "其他项目：webapp 3 · acme-data-pipeline 2 · gamma 1"
    assert page.locator(".search-other [data-more-project]").count() == 3
    assert page.locator(".search-more").count() == 0
    # 点一个：只选它，搜索词留着
    page.click('.search-other [data-more-project="webapp"]')
    page.wait_for_function("() => deskTest.S.projects.has('webapp') && deskTest.S.projects.size === 1")
    assert page.input_value("#search") == "发布" and page.evaluate("deskTest.S.query") == "发布"
    assert sorted(page.evaluate("deskTest.S.visible")) == sorted(w) and page.evaluate("deskTest.S.view") == "all"
    names = page.evaluate("[...document.querySelectorAll('#projects .pname')].map(e => e.textContent)")
    assert names.index("示例项目") < names.index("gamma")  # 一样多的按标签的顺序
    assert page.text_content(".search-other") == "其他项目：acme-data-pipeline 2 · 示例项目 1 · gamma 1"
    assert page.evaluate("document.activeElement.id") == "list"
    # 那个项目的结果只在归档里：切过去时换到归档视图
    page.click('.search-other [data-more-project="gamma"]')
    page.wait_for_function(f"() => deskTest.S.visible.length === 1 && deskTest.S.visible[0] === '{g}'")
    assert scope(page) == ["gamma"] and page.evaluate("deskTest.S.view") == "archive"
    # 归档视图里看不到 acme 的结果（没归档）：切过去时换回"全部"
    page.click('.search-other [data-more-project="acme-data-pipeline"]')
    page.wait_for_function("() => deskTest.S.projects.has('acme-data-pipeline')")
    assert page.evaluate("deskTest.S.view") == "all" and sorted(page.evaluate("deskTest.S.visible")) == sorted(p)
    # 当前项目里被视图挡住的：还是"另有 N 条在其他视图里"，只换视图，项目不动
    page.click('[data-view="decide"]')
    page.wait_for_selector(".search-more")
    assert page.inner_text(".search-more").startswith("另有 2 条在其他视图里")
    page.click(".search-more")
    page.wait_for_function("() => deskTest.S.view === 'all'")
    assert scope(page) == ["acme-data-pipeline"] and len(page.evaluate("deskTest.S.visible")) == 2
    assert errors == []


def test_the_selection_cannot_become_empty(env):
    d, store, server, page, errors = env
    seed(d, store)
    start(page, server)
    assert scope(page) == ["alpha"]
    page.locator("#list").focus()
    page.keyboard.press("j")
    page.keyboard.press("x")  # 勾上一条：点唯一选着的标签什么都不做，勾选也不丢
    assert page.evaluate("deskTest.S.multi.size") == 1
    page.click('.ptab[data-project="alpha"]')
    assert scope(page) == ["alpha"] and page.evaluate("deskTest.S.multi.size") == 1
    for mod in ("Control", "Shift"):  # Ctrl / Shift + 点唯一选着的：减不掉
        page.click('.ptab[data-project="alpha"]', modifiers=[mod])
        assert scope(page) == ["alpha"]
    page.click('.ptab[data-project="beta"]', modifiers=["Control"])
    assert scope(page) == ["alpha", "beta"]
    page.click('.ptab[data-project="alpha"]', modifiers=["Control"])
    assert scope(page) == ["beta"]
    page.click('.ptab[data-project="beta"]', modifiers=["Shift"])
    assert scope(page) == ["beta"] and page.locator(".ptab.on").count() == 1
    # Esc 不再清项目：退到最后一层也还选着
    page.locator("#list").focus()
    for _ in range(3):
        page.keyboard.press("Escape")
    assert scope(page) == ["beta"]
    assert errors == []
