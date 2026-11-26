"""第二轮：页内查找、缩放、记住阅读位置、回到顶部 / 底部、按时间整理（归档 / 删除 / 处理待决定）、
按会话处理待决定、消息类型的小胶囊、提示块、自动补发的标记。在真浏览器里点、按键，看界面和服务端。"""
import datetime as dt

import desk
from test_ui import env  # noqa: F401（env 是 fixture）
from test_ui_handled import post, post_ago, wait_toast
from test_ui_keys import opened, resp, start

LONG = "\n\n".join(f"第 {i} 段：" + "示例项目的说明文字，" * 30 for i in range(60))


def find(page):
    return page.evaluate("deskTest.find()")


def test_find_in_message_counts_steps_and_hands_off_to_global_search(env):
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="苹果和梨", body="苹果一个。\n\n" + LONG + "\n\n又一个苹果。\n\n- 第三个苹果")
    store.poll()
    start(page, server)
    opened(page, a)
    page.locator("#scroller").focus()
    page.keyboard.press("Control+f")
    page.wait_for_selector("#findBar:not([hidden])")
    assert page.evaluate("document.activeElement.id") == "findText"
    page.keyboard.type("苹果")
    page.wait_for_function("document.getElementById('findCount').textContent === '1 / 4'")  # 标题里一个、正文里三个
    assert page.evaluate("CSS.highlights.has('find') && CSS.highlights.has('find-cur')")
    page.keyboard.press("Enter")
    assert page.inner_text("#findCount") == "2 / 4"
    page.keyboard.press("Shift+Enter")
    page.keyboard.press("Shift+Enter")
    assert page.inner_text("#findCount") == "4 / 4"
    # 当前那个滚进视野：最后一个在长正文底下
    top = page.evaluate("document.getElementById('scroller').scrollTop")
    assert top > 1000
    # 找不到：写"无结果"，整条变成提示色
    page.fill("#findText", "不存在的字")
    page.wait_for_function("document.getElementById('findCount').textContent === '无结果'")
    assert "none" in page.get_attribute("#findBar", "class") and find(page)["n"] == 0
    # Esc 关掉：高亮清掉，焦点回阅读区
    page.keyboard.press("Escape")
    assert page.is_hidden("#findBar") and not page.evaluate("CSS.highlights.has('find')")
    assert page.evaluate("document.activeElement.id") == "scroller"
    # "搜全部"：同样的字拿到列表的搜索框里
    page.keyboard.press("Control+f")
    page.fill("#findText", "梨")
    page.click("#findAll")
    assert page.is_hidden("#findBar") and page.input_value("#search") == "梨"
    assert page.evaluate("document.activeElement.id") == "search"
    # 没在看消息时 Ctrl+F / 任何时候 Ctrl+Shift+F：直接去搜全部
    opened(page, a)
    page.locator("#scroller").focus()
    page.keyboard.press("Control+Shift+f")
    assert page.is_hidden("#findBar") and page.evaluate("document.activeElement.id") == "search"
    assert errors == []


def test_zoom_with_keys_and_ctrl_wheel_is_remembered(env):
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="放大看", body="正文")
    store.poll()
    start(page, server)
    opened(page, a)
    z = lambda: page.evaluate("deskTest.zoom()")  # noqa: E731
    size = lambda: page.locator("#body").evaluate("e => e.getBoundingClientRect().height")  # noqa: E731
    h0 = size()
    page.locator("#scroller").focus()
    page.keyboard.press("Control+=")
    page.keyboard.press("Control+=")
    assert z() == 1.2 and page.evaluate("localStorage.getItem('desk.zoom')") == "1.2"
    assert size() > h0 * 1.1  # 正文真的变大了
    assert page.locator(".item").first.evaluate("e => getComputedStyle(e).zoom") == "1.2"  # 列表一起变
    assert page.locator("#toolbar").evaluate("e => getComputedStyle(e).zoom") == "1"  # 工具栏不变
    page.wait_for_function("[...document.querySelectorAll('.toast > span')].some(s => s.textContent.startsWith('缩放 120%'))")
    page.keyboard.press("Control+-")
    assert z() == 1.1
    page.keyboard.press("Control+0")
    assert z() == 1
    # Ctrl + 滚轮：往上放大，往下缩小；页面本身不跟着缩放
    page.mouse.move(600, 300)
    page.keyboard.down("Control")
    page.mouse.wheel(0, -120)
    page.wait_for_function("deskTest.zoom() === 1.1")
    page.mouse.wheel(0, 240)
    page.wait_for_function("deskTest.zoom() < 1.1")
    page.keyboard.up("Control")
    for _ in range(20):  # 有上下限
        page.keyboard.press("Control+=")
    assert z() == 1.8
    page.reload()
    page.wait_for_function("window.deskTest && deskTest.S.version >= 0")
    assert z() == 1.8 and page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--zoom').trim()") == "1.8"
    assert errors == []


def test_reopening_a_message_returns_to_where_you_were_and_jump_buttons(env):
    d, store, server, page, errors = env
    long = post(d, kind="answer", title="很长的回答", body=LONG)
    other = post(d, kind="answer", title="另一条", body="短")
    store.poll()
    start(page, server)
    page.set_viewport_size({"width": 1200, "height": 700})
    opened(page, long)
    sc = page.locator("#scroller")
    assert page.is_hidden("#toTop") or "show" not in page.get_attribute("#toTop", "class")
    assert "show" in page.get_attribute("#toBottom", "class")  # 在顶上：只有"到底部"
    sc.evaluate("e => { e.scrollTop = 1500; e.dispatchEvent(new Event('scroll')); }")
    page.wait_for_function("document.getElementById('toTop').classList.contains('show')")
    page.wait_for_timeout(400)  # 位置写盘有一点延迟
    opened(page, other)
    assert sc.evaluate("e => e.scrollTop") == 0  # 别的消息从头看
    opened(page, long)
    page.wait_for_function("Math.abs(document.getElementById('scroller').scrollTop - 1500) < 3")
    # 重新打开程序也记得
    page.reload()
    page.wait_for_function("window.deskTest && deskTest.S.version >= 0")
    opened(page, long)
    page.wait_for_function("Math.abs(document.getElementById('scroller').scrollTop - 1500) < 3")
    # 回到顶部 / 到底部：按钮和 Home / End
    page.click("#toTop")
    page.wait_for_function("document.getElementById('scroller').scrollTop === 0")
    page.locator("#scroller").focus()
    page.keyboard.press("End")
    page.wait_for_function("(e => e.scrollHeight - e.scrollTop - e.clientHeight < 2)(document.getElementById('scroller'))")
    page.wait_for_function("!document.getElementById('toBottom').classList.contains('show')")
    page.keyboard.press("Home")
    page.wait_for_function("document.getElementById('scroller').scrollTop === 0")
    page.click("#toBottom")
    page.wait_for_function("(e => e.scrollHeight - e.scrollTop - e.clientHeight < 2)(document.getElementById('scroller'))")
    # 滚回顶上：位置不再记着（下次从头看）
    sc.evaluate("e => { e.scrollTop = 0; e.dispatchEvent(new Event('scroll')); }")
    page.wait_for_timeout(400)
    assert long not in page.evaluate("JSON.parse(localStorage.getItem('desk.pos') || '{}')")
    assert errors == []


def open_tidy(page):
    page.click("#listMenuBtn")
    page.click('#popover [data-l="tidy"]')
    page.wait_for_selector("#tidyPanel .tidy-row")


def tidy_btn(page, k):
    return page.locator(f'#tidyPanel [data-tidy="{k}"]')


def test_tidy_archives_and_deletes_by_age_in_one_tab_or_all(env):
    d, store, server, page, errors = env
    H = dt.timedelta(hours=1)
    mk = lambda ago, title, repo="webapp", kind="answer", **kw: post_ago(d, ago, kind=kind, title=title, body="x", repo=repo, **kw)  # noqa: E731
    new = mk(H / 4, "刚才的")
    h3 = mk(3 * H, "三小时前")
    h8 = mk(8 * H, "八小时前")
    d2 = mk(48 * H, "两天前")
    dec = mk(48 * H, "两天前的决定", kind="decision", options=["A"])
    other = mk(48 * H, "别的项目两天前", repo="acme-data-pipeline")
    other_dec = mk(2 * H, "别的项目的决定", repo="acme-data-pipeline", kind="decision", options=["A"])
    store.poll()
    start(page, server)
    page.wait_for_selector(".item")
    page.click('.ptab[data-project="webapp"]')
    open_tidy(page)
    # 默认：当前标签、早于 1 小时；还在等你决定的不算
    assert page.get_attribute('#tidyPanel [data-tidy-scope="tab"]', "aria-pressed") == "true"
    assert page.get_attribute('#tidyPanel [data-tidy-age="1h"]', "aria-pressed") == "true"
    assert [b.inner_text() for b in page.locator("#tidyPanel [data-tidy-age]").all()] == ["1 小时", "6 小时", "12 小时", "24 小时", "7 天", "不限"]
    assert tidy_btn(page, "archive").inner_text() == "归档 3 条"
    page.click('#tidyPanel [data-tidy-age="6h"]')
    assert tidy_btn(page, "archive").inner_text() == "归档 2 条"
    page.click('#tidyPanel [data-tidy="open"]')  # 也包括待决定的
    assert tidy_btn(page, "archive").inner_text() == "归档 3 条"
    page.click('#tidyPanel [data-tidy="open"]')
    page.click('#tidyPanel [data-tidy-scope="all"]')  # 全部标签
    assert tidy_btn(page, "archive").inner_text() == "归档 3 条"
    assert tidy_btn(page, "resolve").inner_text() == "待决定全部标为已处理（2）"
    tidy_btn(page, "archive").click()
    wait_toast(page, "已归档 3 条")
    assert store.archived == {h8, d2, other}
    # 记住上次选的
    assert page.evaluate("[localStorage.getItem('desk.tidyScope'), localStorage.getItem('desk.tidyAge')]") == ["all", "6h"]

    # 删除：先问，焦点在"取消"上（回车不会误删）；删除算上归档里的
    open_tidy(page)
    page.click('#tidyPanel [data-tidy-age="1h"]')
    assert tidy_btn(page, "delete").inner_text() == "删除 4 条"
    tidy_btn(page, "delete").click()
    page.wait_for_function("document.activeElement && document.activeElement.id === 'modalCancel'")
    assert "不能恢复" in page.inner_text("#modalText")
    page.keyboard.press("Enter")
    page.wait_for_selector("#modal", state="hidden")
    assert set(store.msgs) >= {h3, h8, d2, other}
    open_tidy(page)
    tidy_btn(page, "delete").click()
    page.wait_for_function("document.activeElement && document.activeElement.id === 'modalCancel'")
    page.click("#modalOk")
    wait_toast(page, "已删除 4 条")
    page.wait_for_function("ids => ids.every(id => !deskTest.S.byId[id])", arg=[h3, h8, d2, other])
    assert not ({h3, h8, d2, other} & set(store.msgs)) and {new, dec, other_dec} <= set(store.msgs)
    assert errors == []


def test_tidy_resolves_every_open_decision_in_the_tab_or_everywhere(env):
    d, store, server, page, errors = env
    a1 = post(d, kind="decision", title="甲一", options=["A"], repo="webapp")
    a2 = post(d, kind="decision", title="甲二", options=["A"], repo="webapp")
    b1 = post(d, kind="decision", title="乙一", options=["A"], repo="acme-data-pipeline")
    store.poll()
    start(page, server)
    page.wait_for_selector(".item")
    page.click('.ptab[data-project="webapp"]')
    open_tidy(page)
    page.click('#tidyPanel [data-tidy-scope="tab"]')
    assert tidy_btn(page, "resolve").inner_text() == "待决定全部标为已处理（2）"
    tidy_btn(page, "resolve").click()
    page.wait_for_function("ids => ids.every(id => !deskTest.S.byId[id].open)", arg=[a1, a2])
    assert all(resp(d, x)[0]["resolved"] and resp(d, x)[0]["silent"] for x in (a1, a2)) and resp(d, b1) == []
    open_tidy(page)
    page.click('#tidyPanel [data-tidy-scope="all"]')
    assert tidy_btn(page, "resolve").inner_text() == "待决定全部标为已处理（1）"
    tidy_btn(page, "resolve").click()
    page.wait_for_function("id => !deskTest.S.byId[id].open", arg=b1)
    assert resp(d, b1)[0]["resolved"]
    open_tidy(page)
    assert tidy_btn(page, "resolve").is_disabled()
    assert errors == []


def test_row_menu_resolves_the_whole_session(env):
    d, store, server, page, errors = env
    s1 = post(d, kind="decision", title="会话一的第一个", options=["A"], session="sess-one")
    s2 = post(d, kind="decision", title="会话一的第二个", options=["A"], session="sess-one")
    t1 = post(d, kind="decision", title="会话二的", options=["A"], session="sess-two")
    store.poll()
    start(page, server)
    page.wait_for_selector(".item")
    page.click(f'.item[data-id="{s1}"]', button="right")
    item = page.locator('#popover [data-m="resolve_session"]')
    assert item.locator(".sub").inner_text() == "2"
    item.click()
    page.wait_for_function("ids => ids.every(id => !deskTest.S.byId[id].open)", arg=[s1, s2])
    assert page.evaluate("id => deskTest.S.byId[id].open", t1) is True
    page.click(f'.item[data-id="{t1}"]', button="right")  # 会话里只剩它自己：菜单里不重复"标为已处理"
    page.wait_for_selector("#popover:not([hidden])")
    assert page.locator('#popover [data-m="resolve_session"]').count() == 0
    assert errors == []


def test_kind_chip_callouts_and_auto_posted_mark(env):
    d, store, server, page, errors = env
    m = desk.make_message(kind="answer", source="proj", title="自动发的回答",
                          body="> [!WARNING]\n> 会删掉示例项目的缓存\n\n> [!TIP]\n> 先备份\n\n> 普通引用")
    m["auto"] = "stop-hook"
    a = desk.post_message(m, d)
    dec = post(d, kind="decision", title="要选", options=["A"])
    store.poll()
    start(page, server)
    opened(page, a)
    assert page.get_attribute("#detail", "data-kind") == "answer"
    assert page.inner_text("#eyebrow .kind.k-answer") == "回答"
    assert "自动补发" in page.inner_text("#eyebrow")
    assert page.inner_text(".md .callout-warning .callout-title") == "注意"
    assert page.inner_text(".md .callout-tip .callout-title") == "提示"
    assert "[!" not in page.inner_text("#body")
    assert page.locator(".md blockquote:not(.callout)").count() == 1
    warn = page.locator(".md .callout-warning").evaluate("e => getComputedStyle(e).borderLeftColor")
    tip = page.locator(".md .callout-tip").evaluate("e => getComputedStyle(e).borderLeftColor")
    assert warn != tip
    opened(page, dec)
    assert page.get_attribute("#detail", "data-kind") == "decision"
    assert page.inner_text("#eyebrow .kind.k-decision") == "决定" and "自动补发" not in page.inner_text("#eyebrow")
    assert errors == []


def test_buttons_press_in_and_claude_code_setup_is_app_only(env):
    d, store, server, page, errors = env
    a = post(d, kind="decision", title="要选", options=["A"])
    store.poll()
    start(page, server)
    opened(page, a)
    # 按钮有过渡：悬停、按下不是"啪"一下
    assert page.locator("#submitBtn").evaluate("e => getComputedStyle(e).transitionDuration") != "0s"
    assert page.locator("#copyBtn").evaluate("e => getComputedStyle(e).transitionDuration") != "0s"
    # 浏览器里（不是桌面程序）设置里没有"接入 Claude Code"：要改这台电脑上的文件
    page.click("#settingsBtn")
    page.wait_for_selector("#popover:not([hidden])")
    assert page.locator('[data-app="claude_code"]').count() == 0
    assert errors == []
