"""阅读页的顺序（真浏览器）：标题 → 要你做的（待决定的卡片 / 追问框）→ 往来记录（新的在上）→ 原消息（原问题、正文）。
追问框平时一行、点进去或有草稿才长高；Tab 顺序跟着走；打印 / 复制照原样读（标题、原问题、正文）。"""
import datetime as dt

import desk
from test_ui import env, post  # noqa: F401  （env 是 fixture）

# 阅读区里看得见的几块，从上到下
ORDER = "() => [...document.getElementById('scroller').children].filter(e => !e.hidden).map(e => e.id)"
TOPS = "ids => ids.map(id => document.getElementById(id).getBoundingClientRect().top)"
HEIGHT = "() => document.getElementById('fuText').getBoundingClientRect().height"
RULE = "() => getComputedStyle(document.getElementById('article'), '::before').content"


def opened(page, mid):
    page.evaluate("id => deskOpen(id)", mid)
    page.wait_for_function("id => deskTest.S.shownKey && deskTest.S.shownKey.split('|')[0] === id", arg=mid)


def ago(minutes):
    return (dt.datetime.now().astimezone() - dt.timedelta(minutes=minutes)).isoformat(timespec="milliseconds")


def post_at(d, minutes, **kw):
    kw.setdefault("source", "proj")
    m = desk.make_message(**kw)
    m["ts"] = ago(minutes)
    return desk.post_message(m, d)


def followup_at(d, minutes, mid, text):
    rec = {"id": desk.new_id(), "ts": ago(minutes), "msg": mid, "source": "proj", "title": "", "text": text}
    desk.append_jsonl(d / desk.FOLLOWUPS, rec)
    return rec


def focused(page):
    return page.evaluate("() => { const a = document.activeElement; return a.id || (a.dataset.open ? 'open:' + a.dataset.open : a.className); }")


def test_open_decision_card_comes_right_after_the_title(env):
    d, store, server, page, errors = env
    a = post(d, kind="decision", title="先做哪个？", question="原问题？", options=["甲", "乙"],
             body="\n\n".join(f"第 {i} 段背景。" for i in range(40)))
    store.poll()
    page.goto(server.url)
    page.wait_for_selector(".item")
    opened(page, a)
    assert page.evaluate(ORDER) == ["head", "decide", "article"]  # 追问框藏着：回复了才能追问
    tops = page.evaluate(TOPS, ["title", "options", "replyText", "decideFoot", "question", "body"])
    assert tops == sorted(tops)
    assert page.evaluate("document.getElementById('scroller').scrollTop") == 0
    # 卡片一打开就整个在屏幕上，用不着"去选择 ↓"
    assert page.evaluate("""() => { const c = document.getElementById('decide').getBoundingClientRect(),
        s = document.getElementById('scroller').getBoundingClientRect(); return c.top >= s.top && c.bottom <= s.bottom; }""")
    assert page.locator("#jumpBtn, .eyebrow button").count() == 0
    # 卡片紧跟标题，不画上边线；原消息上面有一道线
    assert page.evaluate("getComputedStyle(document.querySelector('#decide .decide-card')).borderTopWidth") == "0px"
    assert page.evaluate(RULE) != "none"
    # Tab 顺序：选项 → 补充说明 → 标为已处理
    page.focus('#options .opt[data-idx="0"]')
    seen = []
    for _ in range(3):
        page.keyboard.press("Tab")
        seen.append(page.evaluate("document.activeElement.id || document.activeElement.dataset.idx"))
    assert seen == ["1", "replyText", "resolveBtn"]
    assert errors == []


def test_answer_composer_then_followups_newest_first_then_the_original(env):
    d, store, server, page, errors = env
    a = post_at(d, 10, kind="answer", title="为什么慢", question="为什么这么慢？", body="因为 IO。")
    loose = post_at(d, 9, kind="answer", title="顺手补充", body="y", reply_to=a)  # 在追问之前就有的回应：配不上追问，单独一行
    f1 = followup_at(d, 8, a, "第一个追问")
    rep = post_at(d, 7, kind="answer", title="第一个的回答", body="x", reply_to=a, followup_id=f1["id"])
    followup_at(d, 6, a, "第二个追问")
    store.poll()
    page.goto(server.url)
    page.wait_for_selector(".item")
    opened(page, a)
    page.wait_for_selector("#fuList .fu-item")
    assert page.evaluate(ORDER) == ["head", "followup", "article"]
    # 追问框在记录上面；记录新的在上：第二个（还在等）→ 第一个（带回答的链接）→ 更早的那条回应
    rows = page.evaluate("[...document.getElementById('fuList').children].map(e => e.className + ':' + e.textContent)")
    assert len(rows) == 3
    assert rows[0].startswith("fu-item:") and "第二个追问" in rows[0] and "等待回答" in rows[0]
    assert rows[1].startswith("fu-item:") and "第一个追问" in rows[1] and "Claude 的回答：第一个的回答 →" in rows[1]
    assert rows[2] == "fu-a:Claude 的回答：顺手补充 →"
    tops = page.evaluate(TOPS, ["title", "fuText", "fuState", "fuList", "question", "body"])
    assert tops == sorted(tops)
    assert page.evaluate(RULE) != "none"  # 记录和原消息之间有一道线
    # Tab 顺序：追问框 → 复制追问（没在听、有存着的追问）→（发送按不了，跳过）→ 记录里的链接，从新到旧
    page.focus("#fuText")
    seen = []
    for _ in range(3):
        page.keyboard.press("Tab")
        seen.append(focused(page))
    assert seen == ["fuCopy", "open:" + rep, "open:" + loose]

    # 回应追问的那条：出处在最上面，再是标题、追问框
    page.click(f'#fuList [data-open="{rep}"]')
    page.wait_for_function("() => document.getElementById('title').textContent === '第一个的回答'")
    assert page.evaluate(ORDER) == ["threadRef", "head", "followup", "article"]

    # 窄窗口：一样的顺序，状态行和按钮不撑出横向滚动
    page.set_viewport_size({"width": 600, "height": 800})
    opened(page, a)
    assert page.evaluate(ORDER) == ["head", "followup", "article"]
    assert page.evaluate("(() => { const s = document.getElementById('scroller'); return s.scrollWidth <= s.clientWidth; })()")
    sb, fb = page.locator("#scroller").bounding_box(), page.locator("#fuSend").bounding_box()
    assert fb["x"] + fb["width"] <= sb["x"] + sb["width"]
    assert errors == []


def test_answered_decision_record_sits_between_the_followups_and_the_original(env):
    d, store, server, page, errors = env
    q = post(d, kind="decision", title="清理旧环境？", body="正文在最下面", options=["全删", "留 base"])
    store.poll()
    store.submit(q, "留 base", "先留着")
    store.add_followup(q, "base 留多久？")
    page.goto(server.url)
    page.wait_for_selector(".item")
    opened(page, q)
    page.wait_for_selector("#fuList .fu-item")
    assert page.evaluate(ORDER) == ["head", "followup", "decide", "article"]
    # 追问框 → 追问（新的）→ 你当时的回复（选项打了 ✓、"你的回复"）→ 正文
    tops = page.evaluate(TOPS, ["title", "fuText", "fuList", "options", "doneBox", "body"])
    assert tops == sorted(tops)
    assert page.inner_text("#decideTitle") == "你的回复"
    assert page.locator("#options .opt.chosen").inner_text().endswith("留 base")
    # 回复的记录和上面的追问之间、和下面的正文之间各有一道线
    assert page.evaluate("getComputedStyle(document.querySelector('#decide .decide-card')).borderTopWidth") == "1px"
    assert page.evaluate(RULE) != "none"
    assert errors == []


def test_composer_is_one_line_until_focused_or_holding_a_draft(env):
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="短回答", question="问题？", body="正文")
    b = post(d, kind="answer", title="另一条", body="x")
    store.poll()
    page.goto(server.url)
    page.wait_for_selector(".item")
    opened(page, a)
    page.wait_for_selector("#followup:not([hidden])")
    assert page.evaluate(HEIGHT) < 50  # 平时一行
    # 不把正文往下推多少：标题到原消息之间就是一行框、一行状态
    gap = page.evaluate("document.getElementById('question').getBoundingClientRect().top - document.getElementById('title').getBoundingClientRect().bottom")
    assert gap < 180, gap
    page.focus("#fuText")
    page.wait_for_function(f"() => ({HEIGHT})() >= 80")  # 点进去：长高
    page.evaluate("document.activeElement.blur()")
    page.wait_for_function(f"() => ({HEIGHT})() < 50")  # 空着离开：收回一行
    # 写了字：离开也不收（不会有收起的过渡），换走再回来草稿还在，框也是展开的
    page.fill("#fuText", "写了一半")
    page.wait_for_function("() => { const t = document.getElementById('fuText'); return !t.getAnimations().length && getComputedStyle(t).minHeight === '84px'; }")
    assert page.evaluate("""() => { const t = document.getElementById('fuText'); t.blur();
        return [document.activeElement === t, getComputedStyle(t).minHeight, t.getAnimations().length]; }""") == [False, "84px", 0]
    opened(page, b)
    page.wait_for_function(f"() => document.getElementById('fuText').value === '' && ({HEIGHT})() < 50")
    opened(page, a)
    page.wait_for_function(f"() => document.getElementById('fuText').value === '写了一半' && ({HEIGHT})() >= 80")
    # 写得多：跟着字长高（浏览器支持 field-sizing 时）
    if page.evaluate("CSS.supports('field-sizing', 'content')"):
        page.fill("#fuText", "\n".join(f"第 {i} 行" for i in range(8)))
        page.wait_for_function(f"() => ({HEIGHT})() > 150")
    assert errors == []


def test_a_sent_followup_appears_at_the_top_of_the_list(env):
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="原回答", body="x")
    store.poll()
    store.add_followup(a, "早一点的追问")
    page.goto(server.url)
    page.wait_for_selector(".item")
    opened(page, a)
    page.wait_for_selector("#fuList .fu-item")
    page.fill("#fuText", "刚发的追问")
    page.click("#fuSend")
    page.wait_for_function("() => document.querySelectorAll('#fuList .fu-item').length === 2")
    assert page.evaluate("[...document.querySelectorAll('#fuList .fu-q')].map(e => e.textContent)") == ["刚发的追问", "早一点的追问"]
    # 紧挨着追问框下面
    assert page.evaluate("""() => document.querySelector('#fuList .fu-item').getBoundingClientRect().top
        - document.querySelector('.fu-bar').getBoundingClientRect().bottom""") < 40
    assert page.input_value("#fuText") == ""
    assert errors == []


def test_print_and_plain_copy_read_title_question_body_in_order(env):
    d, store, server, page, errors = env
    q = post(d, kind="decision", title="打印的标题", question="打印的原问题", body="打印的正文", options=["甲", "乙"])
    store.poll()
    store.submit(q, "乙", "")
    store.add_followup(q, "打印时不带的追问")
    page.goto(server.url)
    page.wait_for_selector(".item")
    opened(page, q)
    page.wait_for_selector("#fuList .fu-item")
    page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
    pr = page.evaluate("document.getElementById('printRoot').textContent")
    idx = [pr.index(s) for s in ("打印的标题", "打印的原问题", "打印的正文", "我的回复：乙")]
    assert idx == sorted(idx)
    assert "打印时不带的追问" not in pr and "追问 Claude" not in pr
    assert page.evaluate("document.querySelectorAll('#printRoot [id]').length") == 0  # 克隆出来的不能和阅读区重 id
    page.evaluate("window.dispatchEvent(new Event('afterprint'))")
    page.evaluate("deskTest.copy('text')")
    page.wait_for_function("() => [...document.querySelectorAll('.toast')].some(t => t.textContent.includes('已复制纯文本'))")
    clip = page.evaluate("navigator.clipboard.readText()")
    idx = [clip.index(s) for s in ("打印的标题", "打印的原问题", "打印的正文")]
    assert idx == sorted(idx) and "打印时不带的追问" not in clip
    assert errors == []
