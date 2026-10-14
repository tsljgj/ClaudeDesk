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
    page.wait_for_function("() => (document.querySelector('#queueBtn span') || {}).textContent?.startsWith('2 条')")
    assert q.locator("span").inner_text() == "2 条待决定 · 1 条紧急 · 最久已等 2 小时"
    assert q.locator("kbd").inner_text() == "N"
    # 阅读区空着：不重复队列条那句话，写出 N 会打开的那条（紧急的先）+ "开始处理"
    assert page.inner_text("#empty .empty-lead") == "紧急的决定"
    assert page.inner_text("#empty .empty-sub") == "beta · 紧急 · 已等 5 分钟 · 后面还有 1 条"
    assert page.inner_text("#startBtn") == "开始处理（N）"
    # 全部 / 决定 显示，回答不显示；跟着项目范围走
    page.click('.tab[data-view="answer"]')
    assert q.is_hidden()
    page.click('.tab[data-view="decide"]')
    assert q.is_visible()
    page.click('.ptab[data-project="alpha"]')
    assert q.locator("span").inner_text() == "1 条待决定 · 最久已等 2 小时"
    page.click(".ptab.all")
    page.click('.tab[data-view="all"]')
    # 点队列条 = N：紧急的先
    q.click()
    assert page.evaluate("deskTest.S.current") == hot
    # 都处理完：队列条整条收起，列表往上让出它的 40 px（32 高 + 8 间距）
    top0 = page.locator("#list").bounding_box()["y"]
    store.submit(old, "A", "")
    store.submit(hot, "A", "")
    page.wait_for_function("() => document.getElementById('queueBtn').hidden")
    assert q.is_hidden() and top0 - page.locator("#list").bounding_box()["y"] == 40
    # 阅读区：没有待决定、但还有未读时不说"都处理完了"
    page.evaluate("document.getElementById('backBtn').click()")  # 关掉阅读区
    unread = page.evaluate("deskTest.S.msgs.filter(m => m.unread).length")
    assert unread > 0
    assert page.inner_text("#empty .empty-lead") == "没有待决定的事"
    assert page.inner_text("#empty .empty-sub") == f"还有 {unread} 条未读 · ↓ 开始看"
    store.mark_read(list(store.msgs))
    page.wait_for_function("() => document.querySelector('#empty .empty-lead').textContent === '都处理完了'")
    assert errors == []


def test_queue_strip_hidden_on_an_empty_inbox(env):
    d, store, server, page, errors = env
    page.goto(server.url)
    page.wait_for_function("window.deskTest && deskTest.S.version >= 0")
    assert page.locator("#queueBtn").is_hidden()
    head = page.locator(".list-head").bounding_box()
    srch = page.locator(".search").bounding_box()
    assert head["y"] + head["height"] - (srch["y"] + srch["height"]) <= 6  # 搜索框下面直接是列表，没有空着的灰条
    page.click('.tab[data-view="decide"]')
    assert page.locator("#queueBtn").is_hidden() and page.inner_text(".list-empty b") == "没有待决定的事"  # 同一件事只有一种说法
    page.click('.tab[data-view="all"]')
    # 来了一条待决定：出现；处理掉：又收起
    a = post(d, kind="decision", title="来了", options=["A"])
    store.poll()
    page.wait_for_selector("#queueBtn:not([hidden])")
    store.submit(a, "A", "")
    page.wait_for_selector("#queueBtn", state="hidden")
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
    now = dt.datetime.now().astimezone()
    noon = (now - dt.timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
    y = post_ago(d, (now - noon).total_seconds() / 60, kind="answer", title="昨天中午的回答", body="x")
    store.poll()
    page.clock.install()
    page.goto(server.url)
    page.wait_for_selector(f'.item[data-id="{c}"]')
    t = lambda i: page.locator(f'.item[data-id="{i}"] .time')  # noqa: E731
    assert t(a).inner_text() == "等 29 分" and "long" not in t(a).get_attribute("class")
    assert t(b).inner_text() == "等 5 分"
    assert t(c).inner_text() == "等 3 天" and "long" in t(c).get_attribute("class")
    assert re.fullmatch(r"(昨天 )?\d\d:\d\d", t(n).inner_text())  # 别的照旧显示时间（刚过半夜时 2 分钟前算"昨天"）
    assert t(y).inner_text() == "昨天 12:00"  # 昨天的也带时间（刚过午夜时，"昨天"可能才过了几分钟）
    assert re.fullmatch(r"\d{4}年\d+月\d+日 \d\d:\d\d", t(a).get_attribute("title"))
    color = lambda i: t(i).evaluate("e => getComputedStyle(e).color")  # noqa: E731
    assert color(c) != color(b)  # 等了 30 分钟以上换强调色
    # 决定卡片：说清楚会话在等多久；推荐只是胶囊，推荐的那项边框和别的一样（只有选中的才带强调色）
    page.click(f'.item[data-id="{a}"]')
    page.wait_for_selector("#detail:not([hidden]) .opt")
    assert page.inner_text("#decideState") == "会话已等 29 分钟 · 提交后立即继续"
    assert page.locator(".opt .rec").evaluate("e => e.closest('.opt').dataset.idx") == "1"
    assert page.locator(".opt .rec").evaluate("e => getComputedStyle(e).backgroundColor") != "rgba(0, 0, 0, 0)"
    border = lambda i: page.locator(f'.opt[data-idx="{i}"]').evaluate("e => getComputedStyle(e).borderTopColor")  # noqa: E731
    assert border(1) == border(0) and page.locator(".opt.rec-opt").count() == 0
    # 顶上的日期：待决定只写日期（等了多久卡片上已经写了，不重复"29 分钟前"）
    date = page.locator("#eyebrow > span[title]")
    assert re.fullmatch(r"今天 \d\d:\d\d|昨天 \d\d:\d\d", date.inner_text())
    assert re.fullmatch(r"\d{4}年\d+月\d+日 \d\d:\d\d", date.get_attribute("title"))
    # 一分钟后自己走
    page.clock.fast_forward("01:00")
    page.wait_for_function(f"() => document.querySelector('.item[data-id=\"{a}\"] .time').textContent === '等 30 分'")
    assert "long" in t(a).get_attribute("class")
    assert page.inner_text("#decideState") == "会话已等 30 分钟 · 提交后立即继续"
    assert re.fullmatch(r"今天 \d\d:\d\d|昨天 \d\d:\d\d", date.inner_text())
    assert page.locator("#queueBtn span").inner_text().endswith("最久已等 3 天")
    # 不是待决定的：日期后面照旧写"几分钟前"
    page.click(f'.item[data-id="{n}"]')
    page.wait_for_function("() => document.getElementById('title').textContent === '回答'")
    assert re.fullmatch(r"今天 \d\d:\d\d · \d+ 分钟前|昨天 \d\d:\d\d", date.inner_text())
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
    assert tab("decide").get_attribute("title") == "1 条待决定"
    assert tab("answer").get_attribute("title") == "2 条未读回答"
    assert tab("decide").get_attribute("aria-label") == "决定，1 条待决定"
    bg = lambda loc: loc.evaluate("e => getComputedStyle(e).backgroundColor")  # noqa: E731
    # "等你决定"是实心胶囊，未读只是数字；两种一样高
    assert "hot" in tab("decide").locator(".n").get_attribute("class") and bg(tab("decide").locator(".n")) != "rgba(0, 0, 0, 0)"
    assert bg(tab("all").locator(".n")) == "rgba(0, 0, 0, 0)"
    assert tab("decide").locator(".n").bounding_box()["height"] == tab("all").locator(".n").bounding_box()["height"]
    assert page.locator('.ptab[data-project="alpha"] .n.hot').inner_text() == "1"
    assert page.locator('.ptab[data-project="beta"] .n').inner_text() == "1"
    assert "hot" not in page.locator('.ptab[data-project="beta"] .n').get_attribute("class")
    # 分组标题不带数（顶部标签已经有，下面的行也各有圆点）
    assert page.locator(".group-label .n").count() == 0
    assert page.locator(".gcount, .gtag").count() == 0
    # 没有数的标签不留空位，文字居中（"归档"从来没有数）
    centred = """e => { const r = e.getBoundingClientRect(), g = document.createRange(); g.selectNodeContents(e.firstChild);
        const t = g.getBoundingClientRect(); return Math.abs((t.left - r.left) - (r.right - t.right)) <= 1; }"""
    assert tab("archive").evaluate(centred)
    # 数没了：那个标签收窄、文字居中；别的标签不变宽窄
    w0 = [tab(v).bounding_box()["width"] for v in ("all", "decide", "answer")]
    p0 = page.locator('.ptab[data-project="alpha"]').bounding_box()["width"]
    store.submit(x, "A", "")
    page.wait_for_function("() => !document.querySelector('.tab[data-view=\"decide\"] .n.hot')")
    assert tab("decide").locator(".n").is_hidden() and tab("decide").evaluate(centred)
    w1 = [tab(v).bounding_box()["width"] for v in ("all", "decide", "answer")]
    assert w1[1] < w0[1] and [w1[0], w1[2]] == [w0[0], w0[2]]
    assert page.locator('.ptab[data-project="alpha"]').bounding_box()["width"] == p0  # 胶囊换成未读数：一样宽
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
    page.wait_for_selector('.ptab[data-project="__other__"]')  # 数据到了再看（"全部项目"一开始就在）
    first = page.locator(".ptab").first
    assert first.inner_text().startswith("全部项目") and "on" in first.get_attribute("class")
    assert first.get_attribute("aria-selected") == "true"
    assert first.locator(".n.hot").inner_text() == "2"  # 一直带着所有项目的待决定总数：点别的标签时它不会冒出来把标签挤走
    assert "2 条待决定" in first.get_attribute("title")
    assert page.locator(".ptab-clear").count() == 0
    other = page.locator('.ptab[data-project="__other__"]')
    assert "没认出属于哪个仓库的旧消息" in other.get_attribute("title") and "未识别" not in page.content()
    # 点一个：只看它；再点一次不取消；点"全部项目"回来
    page.click('.ptab[data-project="alpha"]')
    assert "on" not in first.get_attribute("class")
    assert first.locator(".n.hot").inner_text() == "2"
    page.click('.ptab[data-project="alpha"]')
    assert page.evaluate("Array.from(deskTest.S.projects)") == ["alpha"]
    page.click(".ptab.all")
    assert page.evaluate("deskTest.S.projects.size") == 0 and "on" in first.get_attribute("class")
    assert first.locator(".n.hot").inner_text() == "2"
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
    """小字 ≥ 4.5:1（浅 / 深 × 四种强调色）；强调色按钮、胶囊保持白字；状态圆点在白底和选中行上 ≥ 3:1。"""
    d, store, server, page, errors = env
    page.goto(server.url)
    page.wait_for_function("window.deskTest && deskTest.S.version >= 0")
    keys = ["--bg", "--sunken", "--ink-3", "--ink-4", "--ink-calm", "--accent-ink", "--accent-soft", "--accent-btn",
            "--accent-btn-hover", "--on-accent", "--ok-ink", "--danger", "--danger-btn", "--ink", "--hot"]
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
            sel = [c["--ink"][i] * .08 + bg[i] * .92 for i in range(3)] + [1.0]  # 选中行：color-mix(--ink 8%, --bg)
            for name, (f, b) in {"hot/bg": (c["--hot"], bg), "hot/selected": (c["--hot"], sel), "ink-3/selected": (c["--ink-3"], sel)}.items():
                if _contrast(f, b) < (4.5 if name.startswith("ink") else 3):
                    bad.append(f"{theme}/{acc} {name} {_contrast(f, b):.2f}")
            assert c["--on-accent"][:3] == [255, 255, 255]  # 提交按钮一直是白字
    assert bad == []
    assert errors == []


def _var(page, k):  # 变量算出来的颜色（rgb(...)），和 getComputedStyle 的结果能直接比
    return page.evaluate("""k => { const p = document.createElement('i'); p.style.color = 'var(' + k + ')'; document.body.append(p);
        const c = getComputedStyle(p).color; p.remove(); return c; }""", k)


def test_list_pane_lines_up_on_two_columns(env):
    """列表这一栏左边只有两条竖线：圆点 / 图标在 x 20，文字在 x 40；批量栏的全选框和每行的勾选框对齐。"""
    d, store, server, page, errors = env
    post(d, kind="decision", title="甲的决定", options=["A"], repo="alpha")
    for i in range(14):
        post(d, kind="answer", title=f"乙的回答 {i}", body="x", repo="beta")
    store.poll()
    page.goto(server.url)
    page.wait_for_selector(".group-label")
    xs = page.evaluate("""() => { const X = e => Math.round(e.getBoundingClientRect().left);
        const T = e => { const w = document.createTreeWalker(e, NodeFilter.SHOW_TEXT, { acceptNode: n => n.data.trim() ? 1 : 3 });
          const r = document.createRange(); r.selectNodeContents(w.nextNode()); return Math.round(r.getBoundingClientRect().left); };
        const q = s => document.querySelector(s);
        return { searchIcon: X(q('.search i')), queueText: T(q('#queueBtn span')), groupDot: X(q('.group-label .pdot')), itemDot: X(q('.item .dot')),
          searchInput: X(q('#search')), groupName: T(q('.group-label .gname')), itemTitle: T(q('.item .t')) }; }""")
    assert xs == {"searchIcon": 20, "queueText": 20, "groupDot": 20, "itemDot": 20, "searchInput": 40, "groupName": 40, "itemTitle": 40}
    # 分组标题吸顶时紧贴列表上沿，上面不漏出底下滚过的字
    page.evaluate("document.getElementById('list').scrollTop = 40")
    page.wait_for_timeout(100)
    assert page.locator(".group-label").first.bounding_box()["y"] == page.locator("#list").bounding_box()["y"]
    # 批量栏：全选框和行里的勾选框同一列，"已选 N 条"在文字那一列；"标为已处理"是文字按钮，没有待决定时也在
    page.click(f'.item[data-id="{page.evaluate("deskTest.S.visible[1]")}"]')
    page.keyboard.press("x")
    page.wait_for_selector("#bulkbar:not([hidden])")
    assert page.locator("#checkAll").bounding_box()["x"] == page.locator(".item .cb").first.bounding_box()["x"] == 16
    assert page.evaluate("(() => { const r = document.createRange(); r.selectNodeContents(document.getElementById('bulkCount')); return Math.round(r.getBoundingClientRect().left); })()") == 40
    assert page.locator("#bulkResolve").is_visible() and page.inner_text("#bulkResolve") == "标为已处理"
    gap = page.evaluate("""(() => { const b = [...document.querySelectorAll('#bulkbar .icon-btn')].filter(e => e.offsetParent).map(e => e.getBoundingClientRect());
        return b.slice(1).map((r, i) => Math.round(r.left - b[i].right)); })()""")
    assert len(set(gap)) == 1  # 按钮之间的距离都一样
    assert errors == []


def test_eyebrow_separators_travel_with_the_next_bit(env):
    d, store, server, page, errors = env
    a = post(d, kind="decision", title="一个很长的决定", options=["A"], priority="high",
             source="acme-data-pipeline/refactor-incremental-loader-with-a-very-long-name")
    store.poll()
    page.set_viewport_size({"width": 480, "height": 800})
    page.goto(server.url)
    page.evaluate("id => deskOpen(id)", a)
    page.wait_for_selector("#detail:not([hidden]) .opt")
    bits = page.evaluate("""[...document.querySelectorAll('#eyebrow > .eb')].map(e => [e.textContent, getComputedStyle(e, '::before').content])""")
    assert bits[0][0] == "决定" and bits[-1][0] == "紧急"
    assert bits[0][1] == "none" and all(b[1] == '"·"' for b in bits[1:])  # 点画在后一段前面：折行时跟着走，不挂在行末
    loose = page.evaluate("[...document.getElementById('eyebrow').childNodes].filter(n => n.nodeType === 3).map(n => n.data).join('')")
    assert "·" not in loose
    assert errors == []


def test_shortcut_sheet_fits_short_windows(env):
    d, store, server, page, errors = env
    page.set_viewport_size({"width": 1300, "height": 720})
    page.goto(server.url)
    page.wait_for_function("window.deskTest && deskTest.S.version >= 0")
    page.keyboard.press("?")
    page.wait_for_function("document.activeElement.id === 'modalOk'")
    box, ok = page.locator(".modal").bounding_box(), page.locator("#modalOk").bounding_box()
    assert box["y"] >= 0 and box["y"] + box["height"] <= 720 and ok["y"] + ok["height"] <= 720 - 16
    assert box["height"] <= 560  # 分两栏（原来一栏 845 px，"好的"在窗口外面）
    assert page.locator(".kbd-group h4").all_inner_texts() == ["浏览", "决定", "整理", "其他"]
    tops = [page.locator(".kbd-group").nth(i).bounding_box()["y"] for i in range(4)]
    assert tops[0] == tops[1] and tops[2] == tops[3] and tops[2] > tops[0]  # 宽时两栏
    sheet = page.inner_text("#modalText")
    assert "点标签" not in sheet and "方框" not in sheet  # 只列键盘
    page.keyboard.press("Escape")
    assert "sheet" not in page.locator(".modal").get_attribute("class")  # 关掉后别的对话框照旧是窄的
    # 窄而矮：一栏，在对话框里面滚，"好的"按得到
    page.set_viewport_size({"width": 480, "height": 600})
    page.keyboard.press("?")
    page.wait_for_function("document.activeElement.id === 'modalOk'")
    box, ok = page.locator(".modal").bounding_box(), page.locator("#modalOk").bounding_box()
    assert box["y"] >= 0 and box["y"] + box["height"] <= 600 and ok["y"] + ok["height"] <= 600
    assert page.evaluate("(() => { const m = document.querySelector('.modal'); return m.scrollHeight > m.clientHeight; })()")
    page.keyboard.press("Enter")
    page.wait_for_selector("#modal", state="hidden")
    assert errors == []


def test_more_dot_points_at_pending_tabs_out_of_sight(env):
    d, store, server, page, errors = env
    for i in range(8):
        post(d, kind="answer", title=f"仓库 {i}", body="x", repo=f"a-long-repository-name-{i}")
    z = post(d, kind="decision", title="最右边的决定", options=["A"], repo="zz-last")
    store.poll()
    page.set_viewport_size({"width": 720, "height": 800})
    page.emulate_media(reduced_motion="reduce")
    page.goto(server.url)
    more = page.locator("#ptabMore")
    more.wait_for()
    assert more.get_attribute("title") == "右边还有 1 个项目在等你决定"
    assert more.evaluate("e => getComputedStyle(e).backgroundColor") == _var(page, "--hot")
    seen = """() => { const b = document.getElementById('projects').getBoundingClientRect(),
        t = document.querySelector('.ptab[data-project="zz-last"]').getBoundingClientRect(); return t.left >= b.left && t.right <= b.right + 1; }"""
    assert not page.evaluate(seen)
    more.click()  # 点了滚过去；看得见了，小圆点收起
    page.wait_for_function(seen)
    more.wait_for(state="hidden")
    page.evaluate("(() => { const b = document.getElementById('projects'); b.scrollLeft = 0; b.dispatchEvent(new Event('scroll')); })()")
    more.wait_for()
    store.submit(z, "A", "")  # 没有待决定藏在右边：不出现
    more.wait_for(state="hidden")
    assert errors == []


def test_decision_card_states_stay_distinct(env):
    d, store, server, page, errors = env
    short = post(d, kind="decision", title="短的", options=["甲", "乙"], recommended=1)
    long = post(d, kind="decision", title="长的", body="\n\n".join("很长的正文。" * 30 for _ in range(30)), options=["甲", "乙"])
    store.poll()
    page.emulate_media(reduced_motion="reduce")
    page.goto(server.url)
    page.evaluate("id => deskOpen(id)", short)
    page.wait_for_function("() => document.getElementById('title').textContent === '短的'")
    css = lambda sel, prop: page.locator(sel).evaluate(f"e => getComputedStyle(e).{prop}")  # noqa: E731
    # 还没选：提交按钮是灰的（不是发浑的强调色）
    assert page.is_disabled("#submitBtn")
    assert css("#submitBtn", "backgroundColor") == _var(page, "--sunken") and css("#submitBtn", "opacity") == "1"
    # 卡片整个露在屏幕上："去选择 ↓"不出现
    page.wait_for_timeout(100)
    assert page.locator("#jumpBtn").is_hidden()
    # 选 2，鼠标停在它上面：选中的强调色边框还在；没选的那项悬停照旧变深（边框有 0.1 秒过渡，等它走完再量）
    page.keyboard.press("2")
    page.hover('.opt[data-idx="1"]')
    page.wait_for_timeout(250)
    assert css('.opt[data-idx="1"]', "borderTopColor") == _var(page, "--accent")
    page.hover('.opt[data-idx="0"]')
    page.wait_for_timeout(250)
    assert css('.opt[data-idx="0"]', "borderTopColor") == _var(page, "--ink-4")
    # 键盘焦点环是中性色，和"选中"分得开
    page.focus('.opt[data-idx="1"]')
    page.keyboard.press("Shift+Tab")
    assert page.evaluate("document.activeElement.dataset.idx") == "0"
    assert css('.opt[data-idx="0"]', "outlineColor") == _var(page, "--ink-2") != _var(page, "--accent")
    # 长正文：卡片在下面，"去选择 ↓"出现；滚到卡片，它就收起
    page.evaluate("id => deskOpen(id)", long)
    page.wait_for_function("() => document.getElementById('title').textContent === '长的'")
    page.wait_for_selector("#jumpBtn:not([hidden])")
    page.click("#jumpBtn")
    page.wait_for_selector("#jumpBtn", state="hidden")
    assert errors == []


def test_reading_width_setting(env):
    """正文宽度：默认"宽"（920px、左右 32px），设置里可以换成"适中"（720px）或"铺满"；决定卡片跟着一起变。"""
    d, store, server, page, errors = env
    a = post(d, kind="decision", title="宽度", body="正文" * 400, options=["A", "B"])
    store.poll()
    page.set_viewport_size({"width": 1600, "height": 900})
    page.goto(server.url)
    page.click(f'.item[data-id="{a}"]')
    page.wait_for_selector("#detail:not([hidden]) .opt")
    css = lambda sel, prop: page.locator(sel).evaluate(f"e => getComputedStyle(e).{prop}")  # noqa: E731
    assert css("#article", "maxWidth") == "920px" and css("#article", "paddingLeft") == "32px"
    assert css("#decide", "maxWidth") == "920px"
    page.click("#settingsBtn")
    page.click('[data-set="width"][data-val="full"]')
    assert css("#article", "maxWidth") == "none" and css("#decide", "maxWidth") == "none"
    page.click('[data-set="width"][data-val="m"]')
    assert css("#article", "maxWidth") == "720px" and css("#article", "paddingLeft") == "48px"
    assert server.settings()["width"] == "m"
    assert errors == []
