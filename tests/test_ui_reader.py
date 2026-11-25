"""阅读页的顺序（真浏览器）：标题 →（待决定的卡片 / 你的回复）→ 原消息（原问题、正文）→ 往来记录（按时间，像对话）；
追问框固定在底部、跟着字长高，打字不会拽动阅读区；Tab 顺序跟着走；打印 / 复制照原样读（标题、原问题、正文）。"""
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


def test_original_then_the_thread_oldest_first_and_the_composer_docked_at_the_bottom(env):
    d, store, server, page, errors = env
    a = post_at(d, 10, kind="answer", title="为什么慢", question="为什么这么慢？", body="因为 IO。")
    loose = post_at(d, 9, kind="answer", title="顺手补充", body="补充的正文", reply_to=a)  # 在追问之前就有的回应：配不上追问，单独一条
    f1 = followup_at(d, 8, a, "第一个追问")
    rep = post_at(d, 7, kind="answer", title="第一个的回答", body="回答的**正文**", reply_to=a, followup_id=f1["id"])
    followup_at(d, 6, a, "第二个追问")
    store.poll()
    page.goto(server.url)
    page.wait_for_selector(".item")
    opened(page, a)
    page.wait_for_selector("#fuList .fu-item")
    assert page.evaluate(ORDER) == ["head", "article", "thread"]  # 追问框不在滚动区里
    # 记录按时间从上往下：更早的那条回应 → 第一个（下面直接是回答的正文）→ 第二个（还在等）
    rows = page.evaluate("[...document.getElementById('fuList').children].map(e => e.className + ':' + e.textContent)")
    assert len(rows) == 3
    assert rows[0].startswith("fu-loose:") and "Claude 的回答：顺手补充 →" in rows[0] and "补充的正文" in rows[0]
    assert rows[1].startswith("fu-item:") and "第一个追问" in rows[1] and "Claude 的回答：第一个的回答 →" in rows[1]
    assert page.inner_text("#fuList .fu-item .fu-ans strong") == "正文"  # 回答按 Markdown 显示
    assert rows[2].startswith("fu-item:") and "第二个追问" in rows[2] and "等待回答" in rows[2]
    tops = page.evaluate(TOPS, ["title", "question", "body", "fuList"])
    assert tops == sorted(tops)
    # 追问框在阅读页最底下、滚动区外面：滚到哪都在
    box = page.evaluate("""() => { const s = document.getElementById('scroller').getBoundingClientRect(),
        f = document.getElementById('followup').getBoundingClientRect(), d = document.getElementById('detail').getBoundingClientRect();
        return [f.top >= s.bottom - 1, Math.abs(f.bottom - d.bottom) < 2]; }""")
    assert box == [True, True]
    before = page.evaluate("document.getElementById('fuText').getBoundingClientRect().top")
    page.evaluate("document.getElementById('scroller').scrollTop = 1e6")
    assert page.evaluate("document.getElementById('fuText').getBoundingClientRect().top") == before
    # Tab：记录里的链接从旧到新；追问框 → 复制追问（没在听、有存着的追问）
    page.focus(f'#fuList [data-open="{loose}"]')
    page.keyboard.press("Tab")
    assert focused(page) == "open:" + rep
    page.focus("#fuText")
    page.keyboard.press("Tab")
    assert focused(page) == "fuCopy"

    # 回应追问的那条：出处在最上面，再是标题、正文
    page.click(f'#fuList [data-open="{rep}"]')
    page.wait_for_function("() => document.getElementById('title').textContent === '第一个的回答'")
    assert page.evaluate(ORDER) == ["threadRef", "head", "article"]
    assert page.is_visible("#followup")

    # 窄窗口：一样的顺序，状态行和按钮不撑出横向滚动
    page.set_viewport_size({"width": 600, "height": 800})
    opened(page, a)
    assert page.evaluate(ORDER) == ["head", "article", "thread"]
    assert page.evaluate("(() => { const s = document.getElementById('scroller'); return s.scrollWidth <= s.clientWidth; })()")
    db, fb = page.locator("#followup").bounding_box(), page.locator("#fuSend").bounding_box()
    assert fb["x"] + fb["width"] <= db["x"] + db["width"]
    assert errors == []


def test_answered_decision_record_sits_under_the_title_and_the_thread_after_the_original(env):
    d, store, server, page, errors = env
    q = post(d, kind="decision", title="清理旧环境？", body="正文在中间", options=["全删", "留 base"])
    store.poll()
    store.submit(q, "留 base", "先留着")
    store.add_followup(q, "base 留多久？")
    page.goto(server.url)
    page.wait_for_selector(".item")
    opened(page, q)
    page.wait_for_selector("#fuList .fu-item")
    assert page.evaluate(ORDER) == ["head", "decide", "article", "thread"]
    # 你当时的回复（选项打了 ✓、"你的回复"）→ 正文 → 追问 → 底下的追问框
    tops = page.evaluate(TOPS, ["title", "options", "doneBox", "body", "fuList", "fuText"])
    assert tops == sorted(tops)
    assert page.inner_text("#decideTitle") == "你的回复"
    assert page.locator("#options .opt.chosen").inner_text().endswith("留 base")
    assert page.evaluate(RULE) != "none"  # 回复的记录和下面的正文之间有一道线
    assert errors == []


def test_composer_grows_with_text_and_typing_never_scrolls_the_reader(env):
    """追问框平时一行；写多了跟着长高。在上面翻着读时往框里打字（输入法一次上屏一串也一样），阅读区不会被拽回框那里。"""
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="长回答", question="问题？", body="\n\n".join(f"第 {i} 段。" + "很长的正文。" * 20 for i in range(40)))
    b = post(d, kind="answer", title="另一条", body="x")
    store.poll()
    page.goto(server.url)
    page.wait_for_selector(".item")
    opened(page, a)
    page.wait_for_selector("#followup:not([hidden])")
    assert page.evaluate(HEIGHT) < 60  # 平时一行
    page.focus("#fuText")
    assert page.evaluate(HEIGHT) < 60  # 点进去不跳
    page.evaluate("document.getElementById('scroller').scrollTop = 1500")
    top = page.evaluate("document.getElementById('scroller').scrollTop")
    page.keyboard.type("一边翻一边写")
    page.keyboard.insert_text("，输入法上屏的一整串")
    assert page.evaluate("document.getElementById('scroller').scrollTop") == top
    assert page.input_value("#fuText") == "一边翻一边写，输入法上屏的一整串"
    # 换走再回来草稿还在
    opened(page, b)
    page.wait_for_function("() => document.getElementById('fuText').value === ''")
    opened(page, a)
    page.wait_for_function("() => document.getElementById('fuText').value === '一边翻一边写，输入法上屏的一整串'")
    # 写得多：跟着字长高（浏览器支持 field-sizing 时）
    if page.evaluate("CSS.supports('field-sizing', 'content')"):
        page.fill("#fuText", "\n".join(f"第 {i} 行" for i in range(8)))
        page.wait_for_function(f"() => ({HEIGHT})() > 150")
    assert errors == []


def test_a_sent_followup_appears_at_the_bottom_and_is_scrolled_into_view(env):
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="原回答", body="\n\n".join(f"第 {i} 段。" for i in range(80)))
    store.poll()
    store.add_followup(a, "早一点的追问")
    page.goto(server.url)
    page.wait_for_selector(".item")
    opened(page, a)
    page.wait_for_selector("#fuList .fu-item")
    page.emulate_media(reduced_motion="reduce")
    page.fill("#fuText", "刚发的追问")
    page.click("#fuSend")
    page.wait_for_function("() => document.querySelectorAll('#fuList .fu-item').length === 2")
    assert page.evaluate("[...document.querySelectorAll('#fuList .fu-q')].map(e => e.textContent)") == ["早一点的追问", "刚发的追问"]
    # 滚到了刚发的那条
    page.wait_for_function("""() => { const r = document.querySelector('#fuList .fu-item:last-child').getBoundingClientRect(),
        s = document.getElementById('scroller').getBoundingClientRect(); return r.top >= s.top && r.bottom <= s.bottom + 1; }""")
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
