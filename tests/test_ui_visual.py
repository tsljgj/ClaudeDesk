"""视觉和信息层：待决定队列条、N 键、等待时间、计数胶囊和提示、"全部项目"标签、文字对比度。"""
import datetime as dt
import re

import desk

from test_ui import env, post  # noqa: F401  （env 是 fixture）


def post_ago(d, minutes, **kw):
    kw.setdefault("source", "proj")
    m = desk.make_message(**kw)
    m["ts"] = (dt.datetime.now().astimezone() - dt.timedelta(minutes=minutes)).isoformat(timespec="milliseconds")
    return desk.post_message(m, d)


def test_queue_strip_and_empty_reader(env):
    d, store, server, page, errors = env
    old = post_ago(d, 130, kind="decision", title="等了很久的决定", options=["A", "B"], repo="alpha")
    hot = post_ago(d, 5, kind="decision", title="紧急的决定", options=["A"], priority="high", repo="beta")
    post_ago(d, 1, kind="answer", title="一个回答", body="x", repo="alpha")
    store.poll()
    page.goto(server.url)
    q = page.locator("#queueBtn")
    page.wait_for_function("() => document.querySelector('#queueBtn span').textContent.startsWith('2 条')")
    assert q.locator("span").inner_text() == "2 条待你决定 · 1 条紧急 · 最久已等 2 小时"
    assert q.locator("kbd").inner_text() == "N"
    h0 = q.bounding_box()["height"]
    # 阅读区空着：同一句话 + "开始处理"
    assert page.inner_text("#empty .empty-lead") == "2 条待你决定 · 1 条紧急 · 最久已等 2 小时"
    assert page.inner_text("#startBtn") == "开始处理（N）"
    # 全部 / 决定 显示，回答不显示；跟着项目范围走
    page.click('.tab[data-view="answer"]')
    assert q.is_hidden()
    page.click('.tab[data-view="decide"]')
    assert q.is_visible()
    page.click('.ptab[data-project="alpha"]')
    assert q.locator("span").inner_text() == "1 条待你决定 · 最久已等 2 小时"
    page.click(".ptab.all")
    page.click('.tab[data-view="all"]')
    # 点队列条 = N：紧急的先
    q.click()
    assert page.evaluate("deskTest.S.current") == hot
    # 都处理完：灰色的一行，高度不变，按不了
    store.submit(old, "A", "")
    store.submit(hot, "A", "")
    page.wait_for_function("() => document.getElementById('queueBtn').classList.contains('none')")
    assert q.inner_text() == "没有待决定的事" and q.is_disabled()
    assert q.bounding_box()["height"] == h0
    page.evaluate("document.getElementById('backBtn').click()")  # 关掉阅读区
    assert page.inner_text("#empty .empty-lead") == "都处理完了"
    assert errors == []


def test_n_key_jumps_through_open_decisions(env):
    d, store, server, page, errors = env
    newer = post_ago(d, 10, kind="decision", title="较新的决定", options=["A"], repo="alpha")
    older = post_ago(d, 60, kind="decision", title="较早的决定", options=["A"], repo="alpha")
    urgent = post_ago(d, 2, kind="decision", title="紧急但最新", options=["A"], priority="high", repo="beta")
    done = post_ago(d, 90, kind="decision", title="已经回过的", options=["A"], repo="beta")
    for i in range(3):
        post_ago(d, 1, kind="answer", title=f"回答 {i}", body="x", repo="alpha")
    store.poll()
    store.submit(done, "A", "")
    page.goto(server.url)
    page.wait_for_selector(f'.item[data-id="{done}"] .st.done')
    order = page.evaluate("deskTest.S.visible")
    seq = []
    for _ in range(4):
        page.keyboard.press("n")
        seq.append(page.evaluate("deskTest.S.current"))
    assert seq == [urgent, older, newer, urgent]  # 紧急的先，再按等得最久的；到头绕回来
    page.keyboard.press("Shift+N")
    assert page.evaluate("deskTest.S.current") == newer
    assert page.evaluate("deskTest.S.visible") == order  # 列表本身不重排
    # 在"回答"视图按 N：切到"决定"再跳
    page.click('.tab[data-view="answer"]')
    page.keyboard.press("n")
    assert page.evaluate("[deskTest.S.view, deskTest.S.current]") == ["decide", urgent]
    # 快捷键表里有
    page.keyboard.press("?")
    assert "下一条 / 上一条待决定" in page.inner_text("#modalText")
    page.click("#modalOk")
    # 回复之后：完成框里有"下一条待决定"，不自动跳
    page.keyboard.press("1")
    page.click("#submitBtn")
    page.wait_for_selector("#doneBox [data-next]")
    assert page.evaluate("deskTest.S.current") == urgent
    page.click("#doneBox [data-next]")
    assert page.evaluate("deskTest.S.current") == older
    assert errors == []


def test_wait_time_text_and_minute_refresh(env):
    d, store, server, page, errors = env
    a = post_ago(d, 29.5, kind="decision", title="快半小时了", options=["A", "B"], recommended=2)
    b = post_ago(d, 5, kind="decision", title="刚来的", options=["A"])
    c = post_ago(d, 3 * 24 * 60 + 5, kind="decision", title="三天前的", options=["A"])
    n = post_ago(d, 2, kind="answer", title="回答", body="x")
    store.poll()
    page.clock.install()
    page.goto(server.url)
    page.wait_for_selector(f'.item[data-id="{c}"]')
    t = lambda i: page.locator(f'.item[data-id="{i}"] .time')  # noqa: E731
    assert t(a).inner_text() == "等 29 分" and "long" not in t(a).get_attribute("class")
    assert t(b).inner_text() == "等 5 分"
    assert t(c).inner_text() == "等 3 天" and "long" in t(c).get_attribute("class")
    assert re.fullmatch(r"\d\d:\d\d", t(n).inner_text())  # 别的照旧显示时间
    assert re.fullmatch(r"\d{4}年\d+月\d+日 \d\d:\d\d", t(a).get_attribute("title"))
    color = lambda i: t(i).evaluate("e => getComputedStyle(e).color")  # noqa: E731
    assert color(c) != color(b)  # 等了 30 分钟以上换强调色
    # 决定卡片：说清楚会话在等多久；推荐是胶囊，推荐的那项有淡强调边框
    page.click(f'.item[data-id="{a}"]')
    page.wait_for_selector("#detail:not([hidden]) .opt")
    assert page.inner_text("#decideState") == "会话已等待 29 分钟 · 提交后立即继续"
    assert page.locator(".opt.rec-opt").get_attribute("data-idx") == "1"
    assert page.locator(".opt .rec").evaluate("e => getComputedStyle(e).backgroundColor") != "rgba(0, 0, 0, 0)"
    date = page.locator("#eyebrow > span[title]")
    assert re.fullmatch(r"今天 \d\d:\d\d · 29 分钟前|昨天 \d\d:\d\d", date.inner_text())
    assert re.fullmatch(r"\d{4}年\d+月\d+日 \d\d:\d\d", date.get_attribute("title"))
    # 一分钟后自己走
    page.clock.fast_forward("01:00")
    page.wait_for_function(f"() => document.querySelector('.item[data-id=\"{a}\"] .time').textContent === '等 30 分'")
    assert "long" in t(a).get_attribute("class")
    assert page.inner_text("#decideState") == "会话已等待 30 分钟 · 提交后立即继续"
    assert re.fullmatch(r"今天 \d\d:\d\d · 30 分钟前|昨天 \d\d:\d\d", date.inner_text())
    assert page.locator("#queueBtn span").inner_text().endswith("最久已等 3 天")
    assert errors == []


def test_count_pills_and_tooltips(env):
    d, store, server, page, errors = env
    x = post(d, kind="decision", title="甲项目的决定", options=["A"], repo="alpha")
    post(d, kind="answer", title="甲的回答", body="x", repo="alpha")
    post(d, kind="answer", title="乙的回答", body="y", repo="beta")
    store.poll()
    page.goto(server.url)
    page.wait_for_selector(".group-label")
    tab = lambda v: page.locator(f'.tab[data-view="{v}"]')  # noqa: E731
    assert tab("all").get_attribute("title") == "3 条未读"
    assert tab("decide").get_attribute("title") == "1 条待你决定"
    assert tab("answer").get_attribute("title") == "2 条未读回答"
    assert tab("decide").get_attribute("aria-label") == "决定，1 条待你决定"
    bg = lambda loc: loc.evaluate("e => getComputedStyle(e).backgroundColor")  # noqa: E731
    # "等你决定"是实心胶囊，未读只是数字；两种一样高
    assert "hot" in tab("decide").locator(".n").get_attribute("class") and bg(tab("decide").locator(".n")) != "rgba(0, 0, 0, 0)"
    assert bg(tab("all").locator(".n")) == "rgba(0, 0, 0, 0)"
    assert tab("decide").locator(".n").bounding_box()["height"] == tab("all").locator(".n").bounding_box()["height"]
    assert page.locator('.ptab[data-project="alpha"] .n.hot').inner_text() == "1"
    assert page.locator('.ptab[data-project="beta"] .n').inner_text() == "1"
    assert "hot" not in page.locator('.ptab[data-project="beta"] .n').get_attribute("class")
    # 分组标题：有待决定才显示胶囊，别的数不显示
    assert page.locator('.group-label[data-project="alpha"] .n.hot').inner_text() == "1"
    assert page.locator('.group-label[data-project="alpha"] .n').get_attribute("title") == "1 条待你决定"
    assert page.locator('.group-label[data-project="beta"] .n').count() == 0
    assert page.locator(".gcount, .gtag").count() == 0
    # 数没了，标签不变宽窄
    w0 = [tab(v).bounding_box()["width"] for v in ("all", "decide", "answer")]
    p0 = page.locator('.ptab[data-project="alpha"]').bounding_box()["width"]
    store.submit(x, "A", "")
    page.wait_for_function("() => !document.querySelector('.tab[data-view=\"decide\"] .n.hot')")
    assert [tab(v).bounding_box()["width"] for v in ("all", "decide", "answer")] == w0
    assert page.locator('.ptab[data-project="alpha"]').bounding_box()["width"] == p0
    assert errors == []


def test_all_projects_tab_wheel_and_fade(env):
    d, store, server, page, errors = env
    post(d, kind="decision", title="甲", options=["A"], repo="alpha")
    post(d, kind="decision", title="乙", options=["A"], repo="beta")
    for i in range(6):
        post(d, kind="answer", title=f"仓库 {i}", body="x", repo=f"a-rather-long-repository-name-{i}")
    post(d, kind="info", title="没认出来的", body="x", source="随手记")
    store.poll()
    page.set_viewport_size({"width": 480, "height": 800})
    page.goto(server.url)
    page.wait_for_selector(".ptab")
    first = page.locator(".ptab").first
    assert first.inner_text().startswith("全部项目") and "on" in first.get_attribute("class")
    assert first.get_attribute("aria-selected") == "true"
    assert first.locator(".n.hot").inner_text() == "2"
    assert page.locator(".ptab-clear").count() == 0
    other = page.locator('.ptab[data-project="__other__"]')
    assert "没认出属于哪个仓库的旧消息" in other.get_attribute("title") and "未识别" not in page.content()
    # 点一个：只看它；再点一次不取消；点"全部项目"回来
    page.click('.ptab[data-project="alpha"]')
    assert "on" not in first.get_attribute("class")
    page.click('.ptab[data-project="alpha"]')
    assert page.evaluate("Array.from(deskTest.S.projects)") == ["alpha"]
    page.click(".ptab.all")
    assert page.evaluate("deskTest.S.projects.size") == 0 and "on" in first.get_attribute("class")
    # 放不下：右边淡出；竖着滚轮横着翻，翻过去左边也淡出
    bar = page.locator("#projects")
    assert "fade-r" in bar.get_attribute("class") and "fade-l" not in bar.get_attribute("class")
    bb = bar.bounding_box()
    page.mouse.move(bb["x"] + 60, bb["y"] + 15)
    page.mouse.wheel(0, 400)
    page.wait_for_function("() => document.getElementById('projects').scrollLeft > 0")
    assert "fade-l" in bar.get_attribute("class")
    assert errors == []


def test_hit_area_hover_title_caret_and_toast_corner(env):
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="一个特别特别特别特别特别特别特别特别特别特别长的标题，悬停时省略号要停在操作条前面", body="x")
    store.poll()
    page.goto(server.url)
    item = page.locator(f'.item[data-id="{a}"]')
    item.hover()
    cb = item.locator(".cb").bounding_box()
    assert (cb["width"], cb["height"]) == (16, 16)  # 看起来不变
    hit = "([x, y]) => { const e = document.elementFromPoint(x, y); return !!(e && e.classList.contains('cb')); }"
    assert page.evaluate(hit, [cb["x"] - 7, cb["y"] - 7]) and page.evaluate(hit, [cb["x"] + 23, cb["y"] + 23])  # 32×32
    ends = item.evaluate("""e => { const t = e.querySelector('.t'), a = e.querySelector('.acts');
        return [t.getBoundingClientRect().right - parseFloat(getComputedStyle(t).paddingRight), a.getBoundingClientRect().left]; }""")
    assert ends[0] <= ends[1]  # 省略号停在操作条前面
    assert page.locator("#copyMenuBtn").evaluate("e => getComputedStyle(e).width") == "24px"
    assert page.get_attribute("#toasts", "aria-live") == "polite" and page.get_attribute("#toasts", "role") == "status"
    item.locator('[data-act="archive"]').click()
    page.wait_for_selector(".toast")
    tb = page.locator(".toast").bounding_box()
    assert tb["x"] > 650 and 1300 - (tb["x"] + tb["width"]) <= 24  # 宽窗口：右下角，不挡正文
    assert errors == []


def _rgb(s):
    s = s.strip()
    if s.startswith("#"):
        return [int(s[i:i + 2], 16) for i in (1, 3, 5)] + [1.0]
    nums = [float(v) for v in re.findall(r"[\d.]+", s)]
    return nums[:3] + [nums[3] if len(nums) > 3 else 1.0]


def _over(fg, bg):
    a = fg[3]
    return [fg[i] * a + bg[i] * (1 - a) for i in range(3)] + [1.0]


def _contrast(a, b):
    def lum(c):
        ch = [v / 255 for v in c[:3]]
        ch = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in ch]
        return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]
    hi, lo = sorted([lum(a), lum(b)], reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_text_contrast_all_themes_and_accents(env):
    """小字 ≥ 4.5:1（浅 / 深 × 四种强调色）；强调色按钮、胶囊、勾选框保持白字。"""
    d, store, server, page, errors = env
    page.goto(server.url)
    page.wait_for_selector("#queueBtn")
    keys = ["--bg", "--sunken", "--ink-3", "--ink-4", "--ink-calm", "--accent-ink", "--accent-soft", "--accent-btn",
            "--accent-btn-hover", "--on-accent", "--ok-ink", "--danger", "--danger-btn"]
    bad = []
    for theme in ("light", "dark"):
        for acc in ("ember", "indigo", "jade", "rose"):
            v = page.evaluate("""([t, a, keys]) => { const r = document.documentElement; r.dataset.theme = t; r.dataset.accent = a;
                const s = getComputedStyle(r), o = {}; keys.forEach(k => o[k] = s.getPropertyValue(k));
                const b = document.getElementById('submitBtn'), cs = getComputedStyle(b);
                o.btn = [cs.color, cs.backgroundColor]; return o; }""", [theme, acc, keys])
            c = {k: _rgb(v[k]) for k in keys}
            bg, soft = c["--bg"], _over(c["--accent-soft"], c["--bg"])
            checks = {
                "ink-3/bg": (c["--ink-3"], bg), "ink-3/sunken": (c["--ink-3"], c["--sunken"]),
                "ink-4/bg": (c["--ink-4"], bg), "ink-4/sunken": (c["--ink-4"], c["--sunken"]),
                "ink-calm/bg": (c["--ink-calm"], bg), "accent-ink/bg": (c["--accent-ink"], bg),
                "accent-ink/soft": (c["--accent-ink"], soft), "ok-ink/bg": (c["--ok-ink"], bg), "danger/bg": (c["--danger"], bg),
                "white/danger-btn": ([255, 255, 255, 1], c["--danger-btn"]),
                "on-accent/btn": (c["--on-accent"], c["--accent-btn"]), "on-accent/btn-hover": (c["--on-accent"], c["--accent-btn-hover"]),
                "submit": (_rgb(v["btn"][0]), _rgb(v["btn"][1])),
            }
            for name, (f, b) in checks.items():
                if _contrast(f, b) < 4.5:
                    bad.append(f"{theme}/{acc} {name} {_contrast(f, b):.2f}")
            assert c["--on-accent"][:3] == [255, 255, 255]  # 提交按钮一直是白字
    assert bad == []
    assert errors == []
