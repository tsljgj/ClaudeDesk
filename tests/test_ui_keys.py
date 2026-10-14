"""键盘、焦点、菜单、对话框：在真浏览器里按键，看界面和服务端的状态。"""
import desk
from test_ui import env, post  # noqa: F401（env 是 fixture）


def resp(d, mid):
    return [r for r in desk.read_all(d / desk.RESPONSES) if r["id"] == mid]


def start(page, server):
    page.goto(server.url)
    page.wait_for_function("window.deskTest && deskTest.S.version >= 0")


def opened(page, mid):  # 打开一条，等正文和决定卡片画好
    page.evaluate("id => deskOpen(id)", mid)
    page.wait_for_function("id => deskTest.S.shownKey && deskTest.S.shownKey.split('|')[0] === id", arg=mid)


def js(page, expr):
    return page.evaluate(expr)


def test_modal_enter_on_cancel_cancels_and_tab_is_trapped(env):
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="留着", body="x")
    store.poll()
    start(page, server)
    page.click(f'.item[data-id="{a}"]')
    page.keyboard.press("Delete")
    page.wait_for_function("document.activeElement.id === 'modalOk'")
    page.keyboard.press("Shift+Tab")
    assert js(page, "document.activeElement.id") == "modalCancel"
    page.keyboard.press("Enter")  # 焦点在"取消"上：回车 = 取消
    page.wait_for_selector("#modal", state="hidden")
    page.wait_for_timeout(300)
    assert a not in store.deleted and page.locator(f'.item[data-id="{a}"]').count() == 1
    assert js(page, "document.activeElement.id") == "list"  # 焦点回到打开对话框之前的地方

    # Tab / Shift+Tab 只在对话框的两个按钮之间转，不会跑到后面的页面上
    page.keyboard.press("Delete")
    page.wait_for_function("document.activeElement.id === 'modalOk'")
    seen = []
    for key in ["Tab", "Tab", "Tab", "Shift+Tab", "Shift+Tab"]:
        page.keyboard.press(key)
        seen.append(js(page, "document.activeElement.id"))
    assert seen == ["modalCancel", "modalOk", "modalCancel", "modalOk", "modalCancel"]
    page.keyboard.press("Escape")
    page.wait_for_selector("#modal", state="hidden")
    assert a not in store.deleted

    # 焦点在"删除"上回车：确认
    page.keyboard.press("Delete")
    page.wait_for_function("document.activeElement.id === 'modalOk'")
    page.keyboard.press("Enter")
    page.wait_for_function(f"() => !document.querySelector('.item[data-id=\"{a}\"]')")
    assert a in store.deleted
    assert errors == []


def test_ctrl_enter_submits_from_anywhere_and_enter_presses_buttons(env):
    d, store, server, page, errors = env
    a = post(d, kind="decision", title="只有选项", options=["甲", "乙"])
    b = post(d, kind="decision", title="能写字", options=["丙", "丁"], allow_text=True)
    c = post(d, kind="decision", title="用按钮", options=["戊", "己"], allow_text=True)
    t = post(d, kind="decision", title="只写字", allow_text=True)
    store.poll()
    start(page, server)
    hint = lambda: page.inner_text("#decideHint")  # noqa: E731

    # 发的时候没写 allow_text：也有输入框（提示说可以直接写）；2 → Ctrl+Enter
    opened(page, a)
    assert hint() == "按 1–2 选择，或直接写回复" and page.is_visible("#replyText")
    page.keyboard.press("2")
    assert hint() == "Ctrl+Enter 提交「乙」"
    page.keyboard.press("Control+Enter")
    page.wait_for_selector("#doneBox:not([hidden])")
    assert resp(d, a)[0]["choice"] == "乙"

    # 能写字：焦点不在输入框里，1 → Ctrl+Enter 也能交
    opened(page, b)
    page.keyboard.press("1")
    page.keyboard.press("Control+Enter")
    page.wait_for_selector("#doneBox:not([hidden])")
    assert resp(d, b)[0]["choice"] == "丙"

    # Tab 到选项上回车 = 选它（不是跳进输入框）；焦点在"提交"上回车 = 提交
    opened(page, c)
    page.focus('#options .opt[data-idx="1"]')
    page.keyboard.press("Enter")
    assert js(page, "deskTest.S.choice") == "己"
    assert js(page, "document.activeElement.id") != "replyText"
    page.fill("#replyText", "补一句")
    assert hint() == "Ctrl+Enter 提交「己」"
    page.focus("#submitBtn")
    page.keyboard.press("Enter")
    page.wait_for_selector("#doneBox:not([hidden])")
    r = resp(d, c)[0]
    assert r["choice"] == "己" and r["text"] == "补一句"

    # 没有选项：提示随输入变化；在输入框里 Ctrl+Enter 提交
    opened(page, t)
    assert hint() == "写好后 Ctrl+Enter 提交"
    page.fill("#replyText", "就这样")
    assert hint() == "Ctrl+Enter 提交"
    page.keyboard.press("Control+Enter")
    page.wait_for_selector("#doneBox:not([hidden])")
    assert resp(d, t)[0]["text"] == "就这样"
    assert errors == []


def test_number_key_scrolls_the_picked_option_into_view(env):
    d, store, server, page, errors = env
    body = "\n\n".join(f"第 {i} 段。" + "很长的正文。" * 30 for i in range(40))
    a = post(d, kind="decision", title="很长", body=body, options=["甲", "乙"])
    store.poll()
    page.emulate_media(reduced_motion="reduce")  # 减少动效：直接跳过去，不平滑滚动
    start(page, server)
    opened(page, a)
    assert js(page, "document.getElementById('scroller').scrollTop") == 0
    page.keyboard.press("2")
    page.wait_for_function("""() => { const o = document.querySelector('#options .opt.checked');
        const r = o.getBoundingClientRect(), s = document.getElementById('scroller').getBoundingClientRect();
        return r.top >= s.top && r.bottom <= s.bottom; }""")
    assert js(page, "document.getElementById('scroller').scrollTop") > 0
    assert errors == []


def test_search_keys_stay_in_the_box_and_esc_is_layered(env):
    d, store, server, page, errors = env
    mk = lambda title, repo: desk.post_message(desk.make_message("answer", "s", title, repo=repo), d)  # noqa: E731
    a1, a2, b1 = mk("苹果 一", "alpha"), mk("苹果 二", "alpha"), mk("香蕉", "beta")
    store.poll()
    start(page, server)
    page.click('.ptab[data-project="alpha"]')
    page.keyboard.press("/")
    page.keyboard.type("苹果")
    page.wait_for_function("deskTest.S.query === '苹果' && !!deskTest.S.searchIds")

    # 搜索框里 Esc：第一下只清字（项目筛选不动，焦点还在框里），第二下离开搜索框
    page.keyboard.press("Escape")
    assert js(page, "deskTest.S.query") == "" and page.input_value("#search") == ""
    assert js(page, "document.activeElement.id") == "search"
    assert js(page, "Array.from(deskTest.S.projects)") == ["alpha"]
    page.keyboard.press("Escape")
    assert js(page, "document.activeElement.id") == "list"
    assert js(page, "Array.from(deskTest.S.projects)") == ["alpha"]

    # ↓：打开第一条结果（不是第二条），防抖还没跑完也先搜完
    page.keyboard.press("/")
    page.keyboard.type("苹果")
    page.keyboard.press("ArrowDown")
    page.wait_for_function("deskTest.S.current && deskTest.S.current === deskTest.S.visible[0]")
    assert js(page, "deskTest.S.visible.length") == 2 and js(page, "document.activeElement.id") == "list"
    page.keyboard.press("Escape")  # 列表里：先清搜索
    assert js(page, "deskTest.S.query") == ""
    page.keyboard.press("/")
    page.keyboard.type("苹果 二")
    page.keyboard.press("Enter")  # Enter 也一样
    # a2 本来就是当前这条（上面 ↓ 选的）：要等搜完、焦点回到列表，不然下面的 x 会打进搜索框
    page.wait_for_function(f"deskTest.S.current === '{a2}' && document.activeElement.id === 'list'")

    # 列表里 Esc 一次一层：搜索 → 勾选 → 项目
    page.keyboard.press("x")
    assert js(page, "deskTest.S.multi.size") == 1
    page.keyboard.press("Escape")
    assert js(page, "deskTest.S.query") == "" and js(page, "deskTest.S.multi.size") == 1
    page.keyboard.press("Escape")
    assert js(page, "deskTest.S.multi.size") == 0 and js(page, "deskTest.S.projects.size") == 1
    page.keyboard.press("Escape")
    assert js(page, "deskTest.S.projects.size") == 0

    # 菜单开着：Esc 只关菜单，勾选和项目都不动，焦点回到列表
    page.click('.ptab[data-project="alpha"]')
    page.keyboard.press("Control+a")
    page.click(f'.item[data-id="{a1}"]', button="right")
    page.wait_for_selector("#popover:not([hidden])")
    page.keyboard.press("Escape")
    assert js(page, "document.getElementById('popover').hidden")
    assert js(page, "deskTest.S.multi.size") == 2 and js(page, "deskTest.S.projects.size") == 1
    assert js(page, "document.activeElement.id") == "list"
    assert b1 and errors == []


def test_search_tells_about_hits_hidden_by_view_or_project(env):
    d, store, server, page, errors = env
    a = post(d, kind="decision", title="发布窗口选哪个", options=["A"])
    b = post(d, kind="answer", title="归档里的发布记录", body="x")
    store.poll()
    store.archive([b])
    start(page, server)
    page.click('[data-view="answer"]')
    page.fill("#search", "发布窗口")
    page.wait_for_selector(".search-more")
    assert "「回答」里没有「发布窗口」" in page.inner_text(".list-empty")
    assert "另有 1 条在其他视图或项目里" in page.inner_text(".search-more")
    page.click(".search-more")
    page.wait_for_selector(f'.item[data-id="{a}"]')
    assert js(page, "deskTest.S.view") == "all" and page.locator(".search-more").count() == 0

    # 只在归档里有：给"去归档里看"
    page.fill("#search", "发布记录")
    page.wait_for_function("() => (document.querySelector('.search-more') || {}).textContent?.includes('去归档里看')")
    page.click(".search-more")
    page.wait_for_selector(f'.item[data-id="{b}"]')
    assert js(page, "deskTest.S.view") == "archive"
    assert errors == []


def test_ime_composition_neither_searches_nor_triggers_keys(env):
    d, store, server, page, errors = env
    ids = [post(d, kind="answer", title=t, body="x") for t in ("测试一下", "别的", "还有")]
    store.poll()
    start(page, server)
    page.wait_for_selector(".item")
    cdp = page.context.new_cdp_session(page)
    page.focus("#search")
    for part in ["c", "ce", "ces", "cesh", "ceshi"]:  # 拼音还在拼
        cdp.send("Input.imeSetComposition", {"text": part, "selectionStart": len(part), "selectionEnd": len(part)})
        page.wait_for_timeout(40)
    page.wait_for_timeout(400)
    assert js(page, "deskTest.S.query") == "" and page.locator(".item").count() == 3
    cdp.send("Input.insertText", {"text": "测试"})  # 选字
    page.wait_for_function("deskTest.S.query === '测试' && document.querySelectorAll('.item').length === 1")

    # 拼字时的按键不当快捷键用
    page.keyboard.press("Escape")
    page.keyboard.press("Escape")
    page.click(f'.item[data-id="{ids[1]}"]')
    page.evaluate("document.getElementById('list').dispatchEvent(new KeyboardEvent('keydown', {key: 'e', isComposing: true, bubbles: true}))")
    page.wait_for_timeout(300)
    assert ids[1] not in store.archived
    assert errors == []


def test_focus_is_visible_and_hidden_controls_are_not_tab_stops(env):
    d, store, server, page, errors = env
    mk = lambda kind, title, repo, **kw: desk.post_message(desk.make_message(kind, "s", title, repo=repo, **kw), d)  # noqa: E731
    a = mk("decision", "要选", "alpha", options=["A"], allow_text=True)
    mk("answer", "回答", "beta")
    store.poll()
    start(page, server)
    page.wait_for_selector(".group-label .gmerge")
    assert js(page, "[...document.querySelectorAll('.item .cb, .item .act, .gmerge')].every(b => b.tabIndex === -1)")
    # Tab 走一圈：每一站都看得见，而且有焦点环
    page.evaluate("document.activeElement.blur()")
    for _ in range(14):
        page.keyboard.press("Tab")
        el = js(page, """(() => { const e = document.activeElement, s = getComputedStyle(e);
            return { op: s.opacity, outline: s.outlineStyle, id: e.id, cls: e.className, tag: e.tagName }; })()""")
        assert el["op"] == "1", el
        if el["id"] not in ("list", "search") and el["tag"] != "BODY":  # 列表 / 搜索框另有焦点样式；走到头会落在 body
            assert el["outline"] == "solid", el
    # 用键盘时，列表里当前这条有焦点环
    page.click(f'.item[data-id="{a}"]')
    page.keyboard.press("k")
    page.wait_for_function("getComputedStyle(document.querySelector('.item.selected')).boxShadow.includes('inset')")
    # 焦点环、输入框 / 搜索框获得焦点：中性的深灰（强调色只留给"等你处理"）
    accent, ink3 = "rgb(242, 84, 27)", "rgb(100, 100, 111)"
    assert js(page, "getComputedStyle(document.querySelector('.item.selected')).boxShadow").startswith(ink3)
    page.wait_for_selector("#replyText", state="visible")  # 正文是异步取的：慢机器上卡片还没出来就 focus 会落空
    page.focus("#replyText")
    assert js(page, "getComputedStyle(document.getElementById('replyText')).borderTopColor") == ink3 != accent
    page.focus("#search")
    assert js(page, "getComputedStyle(document.querySelector('.search')).borderTopColor") == ink3
    page.keyboard.press("Tab")  # 键盘焦点环
    assert js(page, "getComputedStyle(document.activeElement).outlineColor") == "rgb(69, 69, 79)"  # --ink-2
    assert errors == []


def test_keyboard_multiselect(env):
    d, store, server, page, errors = env
    for i in range(6):
        post(d, kind="answer", title=f"回答 {i}", body="x")
    store.poll()
    start(page, server)
    page.wait_for_selector(".item")
    v = js(page, "deskTest.S.visible")
    multi = lambda: set(js(page, "Array.from(deskTest.S.multi)"))  # noqa: E731
    page.keyboard.press("j")
    page.keyboard.press("x")
    page.keyboard.press("j")
    page.keyboard.press("j")  # 有勾选时 ↓ 不丢勾选
    assert multi() == {v[0]} and js(page, "deskTest.S.current") == v[2]
    page.wait_for_timeout(200)
    assert store.is_unread(store.msgs[v[1]])  # 勾选时挪光标不标已读
    page.keyboard.press("x")
    assert multi() == {v[0], v[2]}
    page.keyboard.press("Shift+J")
    page.keyboard.press("Shift+ArrowDown")  # 从锚点（刚勾的那条）连选
    assert multi() == {v[0], v[2], v[3], v[4]}
    page.keyboard.press("Shift+K")  # 往回缩；这一轮之前勾的不动
    assert multi() == {v[0], v[2], v[3]}
    assert page.inner_text("#bulkCount") == "已选 3 条"
    assert page.locator(".item.multi").count() == 3

    # 没勾选时 Shift+↓ 从当前这条开始
    page.keyboard.press("Escape")
    page.keyboard.press("Shift+ArrowUp")
    assert multi() == {v[2], v[3]}

    # 批量归档 → Z 撤销：移回来，原来未读的仍是未读
    page.keyboard.press("e")
    page.wait_for_function("document.querySelector('.toast button')?.textContent === '撤销（Z）'")
    assert {v[2], v[3]} <= store.archived
    page.keyboard.press("z")
    page.wait_for_function(f"() => document.querySelectorAll('.item[data-id=\"{v[2]}\"], .item[data-id=\"{v[3]}\"]').length === 2")
    page.wait_for_timeout(200)
    assert not ({v[2], v[3]} & store.archived)
    assert store.is_unread(store.msgs[v[2]]) and store.is_unread(store.msgs[v[3]])  # 光标经过时没标已读，撤销后仍未读
    assert errors == []


def test_z_and_ctrl_z_undo_archive_and_read(env):
    d, store, server, page, errors = env
    ids = [post(d, kind="answer", title=f"回答 {i}", body="x") for i in range(3)]
    store.poll()
    start(page, server)
    page.wait_for_selector(".item")
    v = js(page, "deskTest.S.visible")

    # 单条归档 → Z
    page.click(f'.item[data-id="{v[0]}"]')
    page.keyboard.press("e")
    page.wait_for_function("document.querySelector('.toast button')?.textContent === '撤销（Z）'")
    assert v[0] in store.archived
    page.keyboard.press("z")
    page.wait_for_function("[...document.querySelectorAll('.toast')].some(t => t.textContent === '已撤销')")
    page.wait_for_function(f"() => !!document.querySelector('.item[data-id=\"{v[0]}\"]')")
    assert v[0] not in store.archived
    assert page.locator(".toast button").count() == 0  # 撤销过的提示条收起来了

    # 单条 U → Ctrl+Z
    page.click(f'.item[data-id="{v[1]}"]')
    page.wait_for_timeout(300)
    assert not store.is_unread(store.msgs[v[1]])
    page.keyboard.press("u")
    page.wait_for_function(f"() => !!document.querySelector('.item[data-id=\"{v[1]}\"].unread')")
    page.keyboard.press("Control+z")
    page.wait_for_function(f"() => !document.querySelector('.item[data-id=\"{v[1]}\"].unread')")
    assert not store.is_unread(store.msgs[v[1]])

    # 全部标为已读 → Z：原来未读的改回未读
    unread = [i for i in ids if store.is_unread(store.msgs[i])]
    assert unread
    page.click("#listMenuBtn")
    page.click('[data-l="read_all"]')
    page.wait_for_function("document.querySelectorAll('.item.unread').length === 0")
    page.keyboard.press("z")
    page.wait_for_function(f"document.querySelectorAll('.item.unread').length === {len(unread)}")

    # 归档已处理的（菜单里选"全部"；正在看的那条不动）→ Z
    cur = js(page, "deskTest.S.current")
    handled = [i for i in ids if not store.is_unread(store.msgs[i]) and i != cur]
    assert handled
    page.click("#listMenuBtn")
    page.click('[data-l="archive_handled"]')
    page.click('#popover [data-age="all"]')
    page.wait_for_function(f"document.querySelectorAll('.item').length === {3 - len(handled)}")
    assert store.archived == set(handled)
    page.keyboard.press("z")
    page.wait_for_function("document.querySelectorAll('.item').length === 3")
    assert not (set(ids) & store.archived)

    # 没有可撤销的：只提示，不出错
    page.keyboard.press("z")
    page.wait_for_function("[...document.querySelectorAll('.toast')].some(t => t.textContent === '没有可以撤销的操作')")
    assert errors == []


def test_undo_toast_lasts_8s_and_pauses_on_hover(env):
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="归档我", body="x")
    store.poll()
    page.clock.install()
    start(page, server)
    page.click(f'.item[data-id="{a}"]')
    page.keyboard.press("e")
    page.wait_for_selector(".toast button")
    page.clock.run_for(7000)
    assert page.locator(".toast button").count() == 1  # 原来 6 秒就没了
    page.hover(".toast")
    page.clock.run_for(10000)
    assert page.locator(".toast button").count() == 1  # 鼠标停在上面：不走
    page.mouse.move(5, 5)
    page.clock.run_for(3000)
    assert page.locator(".toast button").count() == 0
    page.keyboard.press("z")  # 提示条没了就不能撤销了
    page.clock.run_for(100)
    assert a in store.archived
    assert errors == []


def test_r_resolves_without_asking_and_z_reopens(env):
    d, store, server, page, errors = env
    a = post(d, kind="decision", title="等你", options=["A", "B"])
    b = post(d, kind="answer", title="一个回答", body="x")
    c = post(d, kind="decision", title="点勾", options=["A"])
    store.poll()
    start(page, server)
    opened(page, a)
    page.keyboard.press("2")  # 选了一半
    page.keyboard.press("r")  # 不问：不通知会话，可以撤销
    page.wait_for_function("[...document.querySelectorAll('.toast')].some(t => t.textContent === '已标为已处理 1 条撤销（Z）')")
    assert js(page, "document.getElementById('modal').hidden")
    assert resp(d, a)[0]["resolved"] is True and resp(d, a)[0]["silent"] is True
    page.wait_for_selector("#doneBox:not([hidden])")
    assert page.inner_text("#doneBox").startswith("已标为已处理 · 没有通知会话 · ")
    page.keyboard.press("z")  # 决定重新打开，选了一半的还在
    page.wait_for_selector("#decideFoot:not([hidden])")
    page.wait_for_selector(f'.item[data-id="{a}"] .st.open')
    assert resp(d, a) == [] and store.is_open(store.msgs[a]) and page.is_hidden("#doneBox")
    assert js(page, f"deskTest.S.drafts['{a}'].idx") == 1
    opened(page, b)
    opened(page, a)  # 换走再回来：草稿照常恢复
    assert js(page, "deskTest.S.choiceIdx") == 1

    # 不是待决定的消息：R 直接标为已处理（= 标为已读，可以撤销）
    opened(page, b)
    page.keyboard.press("u")
    page.wait_for_function(f"() => !!document.querySelector('.item[data-id=\"{b}\"].unread')")
    page.keyboard.press("r")
    page.wait_for_function("[...document.querySelectorAll('.toast')].some(t => t.textContent === '已标为已处理 1 条撤销（Z）')")
    assert js(page, "document.getElementById('modal').hidden") and not store.is_unread(store.msgs[b]) and resp(d, b) == []

    # 点 ✓ 按钮仍是一下就好（点击是有意的）
    page.locator(f'.item[data-id="{c}"]').hover()
    page.click(f'.item[data-id="{c}"] [data-act="resolve"]')
    page.wait_for_function(f"() => !!document.querySelector('.item[data-id=\"{c}\"] .st.done')")
    assert js(page, "document.getElementById('modal').hidden") and resp(d, c)[0]["resolved"] is True
    assert errors == []


def test_menus_and_settings_work_from_the_keyboard(env):
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="一", body="x")
    store.poll()
    start(page, server)
    page.wait_for_selector(".item")
    active = "(() => { const e = document.activeElement; return e.id || e.dataset.set + ':' + e.dataset.val; })()"

    # Ctrl+, 打开设置，焦点进到面板里；↑↓ Home End 移动
    page.keyboard.press("Control+,")
    page.wait_for_selector("#popover.settings:not([hidden])")
    assert js(page, active) == "theme:system"
    page.keyboard.press("ArrowDown")
    assert js(page, active) == "theme:light"
    page.keyboard.press("End")
    assert js(page, "document.activeElement.dataset.app") == "shortcuts"
    page.keyboard.press("Home")
    page.keyboard.press("ArrowUp")  # 到头了绕回最后一个
    assert js(page, "document.activeElement.dataset.app") == "shortcuts"

    # 色块和分段按钮的中文名字 / 按下状态
    sw = page.locator(".swatch")
    assert [sw.nth(i).get_attribute("aria-label") for i in range(4)] == ["珊瑚橙", "靛蓝", "翡翠绿", "玫红"]
    assert sw.nth(0).get_attribute("title") == "珊瑚橙" and sw.nth(0).get_attribute("aria-pressed") == "true"
    assert page.get_attribute('[data-set="theme"][data-val="system"]', "aria-pressed") == "true"

    # 回车改设置：焦点留在原来的按钮上
    page.keyboard.press("Home")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    page.wait_for_function("document.documentElement.dataset.theme === 'dark'")
    assert js(page, active) == "theme:dark"
    assert page.get_attribute('[data-set="theme"][data-val="dark"]', "aria-pressed") == "true"

    # Esc：关掉，焦点回到设置按钮
    page.keyboard.press("Escape")
    assert js(page, "document.getElementById('popover').hidden") and js(page, active) == "settingsBtn"
    # Tab：关掉并接着往下走
    page.keyboard.press("Control+,")
    page.wait_for_selector("#popover:not([hidden])")
    page.keyboard.press("Tab")
    assert js(page, "document.getElementById('popover').hidden")
    assert js(page, "document.getElementById('popover').contains(document.activeElement)") is False
    assert js(page, "document.activeElement.id") != "settingsBtn"

    # 右键菜单：焦点在菜单里，↓ 移动，Esc 回到列表
    page.click(f'.item[data-id="{a}"]', button="right")
    page.wait_for_selector("#popover:not([hidden])")
    assert js(page, "document.activeElement.dataset.m") == "read"
    page.keyboard.press("ArrowDown")
    assert js(page, "document.activeElement.dataset.m") == "resolve"  # 没读过的也能"标为已处理"
    page.keyboard.press("ArrowDown")
    assert js(page, "document.activeElement.dataset.m") == "archive"
    page.keyboard.press("Escape")
    assert js(page, "document.activeElement.id") == "list"

    # 快捷键表：分组列出键盘操作；焦点在"好的"上
    page.keyboard.press("?")
    page.wait_for_function("document.activeElement.id === 'modalOk'")
    sheet = page.inner_text("#modalText")
    for s in ["浏览", "整理", "设置", "撤销", "连续勾选", "退一层", "下一条 / 上一条待决定", "打开 / 写补充说明", "标为已处理", "只看未处理（开 / 关）", "Ctrl + A"]:
        assert s in sheet, s
    keys = js(page, "[...document.querySelectorAll('#modalText .kbd-table > span:nth-child(odd)')].map(e => e.textContent)")
    assert len(keys) == 21 and len(set(keys)) == 21
    assert js(page, "[...document.querySelectorAll('#modalText kbd')].some(k => k.textContent === '/')")  # "/" 单独一个键也画成按键
    page.keyboard.press("Enter")
    page.wait_for_selector("#modal", state="hidden")
    assert js(page, "document.getElementById('modalCancel').hidden") is False
    assert errors == []


def test_narrow_window_esc_and_backspace_go_back_to_the_list(env):
    d, store, server, page, errors = env
    for i in range(3):
        post(d, kind="answer", title=f"回答 {i}", body="x")
    store.poll()
    page.set_viewport_size({"width": 480, "height": 800})
    start(page, server)
    page.wait_for_selector(".item")
    assert page.get_attribute("#backBtn", "title") == "返回列表（Esc）"
    reading = "document.getElementById('app').classList.contains('reading')"
    page.keyboard.press("j")  # 窄窗口列表页：j 只挪光标，Enter 才打开
    page.keyboard.press("Enter")
    page.wait_for_function(reading)
    page.keyboard.press("Escape")
    page.wait_for_function("!" + reading)
    assert js(page, "document.activeElement.id") == "list"
    page.keyboard.press("j")
    page.keyboard.press("Enter")
    page.wait_for_function(reading)
    page.keyboard.press("Backspace")
    page.wait_for_function("!" + reading)
    assert js(page, "document.activeElement.id") == "list"
    # 减少动效：阅读页不滑进来
    assert js(page, "getComputedStyle(document.getElementById('reader')).transitionDuration") != "0s"
    page.emulate_media(reduced_motion="reduce")
    assert js(page, "getComputedStyle(document.getElementById('reader')).transitionDuration") == "0s"
    assert errors == []


def test_narrow_list_has_a_cursor_so_esc_then_j_moves_on(env):
    """窄窗口：j 只挪光标（不打开、不标已读），Enter 打开；Esc 回到列表时光标停在刚看的那条，再按 j 就是下一条。"""
    d, store, server, page, errors = env
    for i in range(4):
        post(d, kind="answer", title=f"回答 {i}", body="x")
    store.poll()
    page.set_viewport_size({"width": 480, "height": 800})
    start(page, server)
    page.wait_for_selector(".item")
    v = js(page, "deskTest.S.visible")
    reading = "document.getElementById('app').classList.contains('reading')"
    cur = lambda: js(page, "[deskTest.S.current, deskTest.S.cursor, [...document.querySelectorAll('.item.cursor')].map(e => e.dataset.id)]")  # noqa: E731
    page.focus("#list")
    page.keyboard.press("j")
    assert cur() == [None, v[0], [v[0]]] and not js(page, reading)
    page.keyboard.press("j")
    assert cur() == [None, v[1], [v[1]]]
    page.wait_for_timeout(1000)
    assert store.is_unread(store.msgs[v[0]]) and store.is_unread(store.msgs[v[1]])  # 光标扫过去不算读
    # 光标那条有键盘焦点环；列表本身不再描整圈强调色的框
    shadow = js(page, f"getComputedStyle(document.querySelector('.item[data-id=\"{v[1]}\"]')).boxShadow")
    assert "inset" in shadow and js(page, "getComputedStyle(document.getElementById('list')).outlineStyle") == "none"
    page.keyboard.press("Enter")
    page.wait_for_function(reading)
    assert js(page, "deskTest.S.current") == v[1]
    page.keyboard.press("Escape")
    page.wait_for_function("!" + reading)
    assert cur() == [None, v[1], [v[1]]] and js(page, "document.activeElement.id") == "list"
    page.keyboard.press("j")  # 接着往下，不是又回到第一条
    assert cur() == [None, v[2], [v[2]]] and not js(page, reading)
    page.keyboard.press("Enter")
    page.wait_for_function(reading)
    assert js(page, "deskTest.S.current") == v[2]
    page.keyboard.press("Escape")
    page.keyboard.press("k")
    page.keyboard.press("k")
    assert cur() == [None, v[0], [v[0]]]
    page.keyboard.press("k")  # 到头了停住
    assert cur()[1] == v[0]
    # 宽窗口照旧：↓ 直接打开下一条
    page.set_viewport_size({"width": 1300, "height": 800})
    page.keyboard.press("j")
    assert js(page, "deskTest.S.current") is not None
    assert errors == []
