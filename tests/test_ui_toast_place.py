"""提示条放在哪：不浮在正文和决定卡片上面。宽窗口、窄窗口的列表页放列表底栏；窄窗口在看一条时放工具栏下面，把正文往下推。"""
import json
import re

import desk
from claudedesk.server import ActionError
from test_ui import env, post  # noqa: F401（env 是 fixture）
from test_ui_keys import opened, start

LONG = "\n\n".join(f"示例正文第 {i} 段，长一点，铺满阅读区，看提示条会不会盖住它。" for i in range(1, 40))


def box(page, sel):
    return page.locator(sel).bounding_box()


def hits(a, b):  # 两个矩形有没有重叠（贴边不算）
    return a["x"] < b["x"] + b["width"] and b["x"] < a["x"] + a["width"] and a["y"] < b["y"] + b["height"] and b["y"] < a["y"] + a["height"]


def inside(a, b):
    return a["x"] >= b["x"] - .5 and a["y"] >= b["y"] - .5 and a["x"] + a["width"] <= b["x"] + b["width"] + .5 and a["y"] + a["height"] <= b["y"] + b["height"] + .5


def clip(a, b):  # a 落在 b 里看得见的那一块（b 是滚动区）
    x, y = max(a["x"], b["x"]), max(a["y"], b["y"])
    r, btm = min(a["x"] + a["width"], b["x"] + b["width"]), min(a["y"] + a["height"], b["y"] + b["height"])
    return {"x": x, "y": y, "width": max(0, r - x), "height": max(0, btm - y)}


def on_top(page, sel):  # 提示条中间那一点没被别的东西盖住
    return page.evaluate("""s => { const t = document.querySelector(s), r = t.getBoundingClientRect();
        const e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return !!e && t.contains(e); }""", sel)


def where(page):  # 提示条现在在哪个槽里
    return page.evaluate("""() => { const b = document.getElementById('toasts');
        return b.closest('.list-foot') ? 'foot' : b.previousElementSibling === document.getElementById('toolbar') ? 'toolbar' : '?'; }""")


def rgb(s):  # "rgb(1, 2, 3)" 或 color-mix 算出来的 "color(srgb .99 .95 .95)"
    v = [float(x) for x in re.findall(r"[\d.]+", s)][:3]
    return [x * 255 for x in v] if s.startswith("color(") else v


def contrast(a, b):
    def lum(c):
        c = [v / 255 for v in c]
        c = [v / 12.92 if v <= .03928 else ((v + .055) / 1.055) ** 2.4 for v in c]
        return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]
    hi, lo = sorted([lum(a), lum(b)], reverse=True)
    return (hi + .05) / (lo + .05)


def texts(page):
    return page.evaluate("[...document.querySelectorAll('#toasts .toast > span')].map(s => s.textContent)")


def reader_settled(page):  # 窄窗口阅读页滑进来 / 滑出去要 0.2 秒：等它停下再量
    page.wait_for_function("""() => { const r = document.getElementById('reader').getBoundingClientRect();
        return document.getElementById('app').classList.contains('reading') ? r.left === 0 : r.left >= innerWidth; }""")


def test_wide_toast_sits_in_the_list_footer_not_over_the_reader(env):
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="归档我", body="x")
    post(d, kind="answer", title="留着", body="x")
    dec = post(d, kind="decision", title="正在看的决定", body=LONG, options=["甲", "乙"])
    store.poll()
    start(page, server)
    opened(page, dec)
    assert page.is_visible("#ver")
    item = page.locator(f'.item[data-id="{a}"]')
    item.hover()
    item.locator('[data-act="archive"]').click()
    t = page.locator(".toast", has_text="已归档 1 条")
    t.wait_for()
    tb = t.bounding_box()
    assert not hits(tb, box(page, "#reader")) and not hits(tb, box(page, "#scroller"))  # 不挡正文和决定卡片
    assert inside(tb, box(page, "#listpane")) and where(page) == "foot" and on_top(page, ".toast")
    assert tb["y"] + tb["height"] <= 850 and tb["x"] < 40  # 列表底栏，左下角
    assert page.is_hidden("#ver")  # 占了版本号那一行
    assert page.evaluate("deskTest.S.current") == dec  # 正在看的那条还开着

    # 撤销按钮照样能用
    t.locator("button", has_text="撤销（Z）").click()
    page.wait_for_function(f"() => deskTest.S.byId['{a}'] && !deskTest.S.byId['{a}'].archived")
    assert a not in store.archived
    page.wait_for_function("!document.querySelector('#toasts .toast')")
    assert page.is_visible("#ver")  # 提示没了，版本号回来

    # Z 也能撤销
    item.hover()
    item.locator('[data-act="archive"]').click()
    page.locator(".toast button", has_text="撤销（Z）").wait_for()
    assert a in store.archived
    page.keyboard.press("z")
    page.wait_for_function(f"() => deskTest.S.byId['{a}'] && !deskTest.S.byId['{a}'].archived")
    assert a not in store.archived
    page.emulate_media(media="print")
    assert page.evaluate("getComputedStyle(document.getElementById('toasts')).display") == "none"  # 打印不带提示条
    page.emulate_media(media="screen")
    assert errors == []


def test_narrow_reading_toast_goes_under_the_toolbar_and_n_opens_it(env):
    d, store, server, page, errors = env

    def mk(kind, title, **kw):
        return desk.make_message(kind, "s", title, repo="webapp", **kw)

    def drop(m):  # 直接写进收件箱，和会话发来的一样
        with open(d / desk.INBOX, "a", encoding="utf-8") as f:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
        store.poll()
        return m["id"]

    a = drop(mk("decision", "正在看的决定", body=LONG, options=["甲", "乙"]))
    page.set_viewport_size({"width": 480, "height": 800})
    start(page, server)
    page.wait_for_selector(".item")
    opened(page, a)
    reader_settled(page)
    b = drop(mk("decision", "示例项目 新来的决定：要不要把夜间任务改到凌晨三点跑，避开备份窗口？", options=["改", "不改"]))
    t = page.locator(".toast", has_text="webapp 需要你决定")
    t.wait_for()
    assert where(page) == "toolbar" and on_top(page, ".toast")
    tb, sc = t.bounding_box(), box(page, "#scroller")
    assert tb["y"] >= box(page, "#toolbar")["y"] + 40 and tb["y"] + tb["height"] <= sc["y"] + .5  # 工具栏正下方，把正文往下推
    assert not hits(tb, clip(box(page, "#article"), sc))  # 看得见的正文
    page.evaluate("document.getElementById('decide').scrollIntoView({ block: 'end' })")
    page.wait_for_function("() => { const s = document.getElementById('scroller'); return s.scrollTop > 0; }")
    assert t.is_visible() and not hits(t.bounding_box(), clip(box(page, "#decide .decide-card"), box(page, "#scroller")))  # 决定卡片
    assert tb["width"] > 400  # 用满宽度

    # 提示还在时按 N：打开它说的那条
    page.keyboard.press("n")
    page.wait_for_function("id => deskTest.S.current === id", arg=b)
    assert page.locator(".toast", has_text="webapp 需要你决定").count() == 0
    assert errors == []


def test_narrow_list_toast_sits_in_the_footer_and_follows_the_layout(env):
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="归档我", body="x")
    rest = post(d, kind="answer", title="留着", body=LONG)
    store.poll()
    page.clock.install()  # 提示条到点会收起：停住时钟，换几次地方慢慢量
    start(page, server)
    opened(page, a)
    page.keyboard.press("e")  # 宽窗口：列表底栏
    page.locator(".toast button", has_text="撤销（Z）").wait_for()
    assert where(page) == "foot"
    opened(page, rest)

    # 在看一条时变窄：阅读页盖住了列表，提示条跟着挪到工具栏下面
    page.set_viewport_size({"width": 480, "height": 800})
    page.wait_for_function("document.getElementById('toasts').previousElementSibling === document.getElementById('toolbar')")
    reader_settled(page)
    assert on_top(page, ".toast") and not hits(box(page, ".toast"), box(page, "#scroller"))

    # 回到列表：回底栏
    page.keyboard.press("Escape")
    page.wait_for_function("!!document.getElementById('toasts').closest('.list-foot')")
    reader_settled(page)
    tb = box(page, ".toast")
    assert inside(tb, box(page, "#listpane")) and inside(tb, {"x": 0, "y": 0, "width": 480, "height": 800}) and on_top(page, ".toast")
    assert tb["y"] + tb["height"] > 700  # 列表底下
    assert page.is_hidden("#ver")

    # 再打开一条、再回来，跟着走
    opened(page, rest)
    page.wait_for_function("document.getElementById('toasts').previousElementSibling === document.getElementById('toolbar')")
    page.keyboard.press("Escape")
    page.wait_for_function("!!document.getElementById('toasts').closest('.list-foot')")
    page.keyboard.press("z")  # 撤销照样能用
    page.wait_for_function(f"() => deskTest.S.byId['{a}'] && !deskTest.S.byId['{a}'].archived")
    assert errors == []


def test_error_toast_keeps_the_danger_color(env):
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="归档会失败", body="x")
    store.poll()
    orig = server.action

    def patched(body):
        if body.get("action") == "archive":
            raise ActionError("示例错误：文件被占用")
        return orig(body)

    server.action = patched
    start(page, server)
    opened(page, a)
    page.keyboard.press("e")
    bad = page.locator(".toast.bad", has_text="示例错误：文件被占用")
    bad.wait_for()
    st = bad.evaluate("""t => { const c = document.createElement('i'); document.body.appendChild(c);
        const px = v => { c.style.color = 'var(' + v + ')'; return getComputedStyle(c).color; };
        const r = { color: getComputedStyle(t).color, bg: getComputedStyle(t).backgroundColor,
                    danger: px('--danger'), ink: px('--ink') };
        c.remove(); return r; }""")
    fg, bg = rgb(st["color"]), rgb(st["bg"])
    assert st["color"] == st["danger"] and bg[0] > bg[1] + 4 and bg[0] > 200  # 出错：红字、淡红底
    assert contrast(fg, bg) >= 4.5
    assert st["bg"] != st["ink"]  # 不再是反色的深色胶囊
    ok = page.evaluate("""() => { const t = document.createElement('div'); t.className = 'toast'; document.getElementById('toasts').appendChild(t);
        const c = document.createElement('i'); document.body.appendChild(c); c.style.color = 'var(--sunken)';
        const r = [getComputedStyle(t).backgroundColor, getComputedStyle(c).color]; t.remove(); c.remove(); return r; }""")
    assert ok[0] == ok[1]  # 平常的提示：浅灰底
    assert not hits(bad.bounding_box(), box(page, "#reader"))
    assert errors == []


def test_at_most_two_toasts_newest_at_the_bottom(env):
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="归档我", body="x")
    store.poll()
    page.clock.install()  # 不让提示条到点收起，只看条数
    start(page, server)
    opened(page, a)
    page.keyboard.press("z")
    page.keyboard.press("n")
    assert texts(page) == ["没有可以撤销的操作", "没有待决定的事"]
    page.keyboard.press("e")
    page.wait_for_function("() => [...document.querySelectorAll('.toast > span')].some(s => s.textContent === '已归档 1 条')")
    assert texts(page) == ["没有待决定的事", "已归档 1 条"]  # 第三条挤掉最旧的
    ys = page.evaluate("[...document.querySelectorAll('#toasts .toast')].map(t => t.getBoundingClientRect().top)")
    assert ys[0] < ys[1]  # 新的在下面
    assert page.locator(".toast button").inner_text() == "撤销（Z）"

    # 撤销的提示条被挤掉了，就不能再撤销
    page.keyboard.press("n")
    page.keyboard.press("n")
    assert texts(page) == ["没有待决定的事", "没有待决定的事"]
    page.keyboard.press("z")
    assert texts(page)[-1] == "没有可以撤销的操作" and len(texts(page)) == 2
    assert a in store.archived
    assert errors == []
