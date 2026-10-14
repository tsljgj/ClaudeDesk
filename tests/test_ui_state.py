"""界面状态：归档 / 删除和长轮询的竞态、每条消息的草稿、按序号提交、j/k 浏览的已读、新消息提示、提交中的状态。"""
import json
import re
import threading
import time

import desk
from claudedesk.server import ActionError
from test_ui import env, post  # noqa: F401  （env 是 fixture）

# 选中的、阅读区显示的、列表里高亮的，必须是同一条
SAME = """() => { const S = deskTest.S, m = S.current && S.byId[S.current], sel = document.querySelector('.item.selected');
  return !!m && !document.getElementById('detail').hidden && document.getElementById('title').textContent === m.title
    && !!sel && sel.dataset.id === S.current && document.querySelectorAll('.item.selected').length === 1; }"""


def wait_until(fn, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.05)
    return fn()


def next_after(page, cur):
    vis = page.evaluate("deskTest.S.visible")
    i = vis.index(cur)
    return vis[i + 1] if i + 1 < len(vis) else vis[i - 1]


def archive_then_delete(d, store, server, page, errors):
    ids = [post(d, kind="answer", title=f"消息 {i:02d}", body=f"正文 {i}") for i in range(12)]
    store.poll()
    page.goto(server.url)
    page.wait_for_selector(".item")
    page.click(".item >> nth=0")
    page.wait_for_function(SAME)
    for _ in range(4):  # E：选中移到下一条，阅读区、高亮跟着走
        cur = page.evaluate("deskTest.S.current")
        want = next_after(page, cur)
        page.keyboard.press("e")
        page.wait_for_function("id => deskTest.S.current === id", arg=want)
        page.wait_for_function(SAME)
        assert wait_until(lambda: cur in store.archived)
        page.wait_for_timeout(250)  # 晚到的长轮询 / 操作回应都不能再把选中挪走
        assert page.evaluate("deskTest.S.current") == want and page.evaluate(SAME)
    for _ in range(2):  # Delete：确认框写明删哪条；删的就是眼前这条，然后选中下一条
        cur = page.evaluate("deskTest.S.current")
        title = page.inner_text("#title")
        want = next_after(page, cur)
        page.keyboard.press("Delete")
        page.wait_for_selector("#modal:not([hidden])")
        assert page.inner_text("#modalTitle") == f"删除「{title}」？"
        page.click("#modalOk")
        page.wait_for_function("id => deskTest.S.current === id", arg=want)
        page.wait_for_function(SAME)
        assert wait_until(lambda: cur not in store.msgs)
        page.wait_for_timeout(250)
        assert page.evaluate("deskTest.S.current") == want and page.evaluate(SAME)
        # 删掉的消息不留详情缓存
        assert not [k for k in page.evaluate("Object.keys(deskTest.S.details)") if k.startswith(cur + "|")]
    assert errors == []
    return ids


def test_archive_delete_keep_reader_and_selection_in_step(env):
    archive_then_delete(*env)


def test_archive_delete_when_long_poll_beats_the_action_reply(env):
    """服务端先 bump（长轮询先到），操作的回应慢 150 ms 才回来：以前阅读区停在旧消息上，键盘却作用在下一条。"""
    d, store, server, page, errors = env
    orig = server.action

    def slow(body):
        r = orig(body)
        if body.get("action") in ("archive", "delete"):
            time.sleep(0.15)
        return r

    server.action = slow
    store.on_changed.append(lambda: time.sleep(0.01))  # 真程序里托盘图标重画也在这一步
    archive_then_delete(d, store, server, page, errors)
    # 多选里有当前这条：一起删掉后选中下一条没被删的
    vis = page.evaluate("deskTest.S.visible")
    cur = page.evaluate("deskTest.S.current")
    i = vis.index(cur)
    pair = [cur, vis[i + 1]]
    want = vis[i + 2]
    page.click(f'.item[data-id="{pair[1]}"]', modifiers=["Control"])
    page.click(f'.item[data-id="{pair[0]}"]', modifiers=["Control"])  # 当前这条也勾上
    page.wait_for_selector("#bulkbar:not([hidden])")
    page.click('[data-bulk="delete"]')
    assert page.inner_text("#modalTitle") == "删除这 2 条消息？"
    page.click("#modalOk")
    page.wait_for_function("id => deskTest.S.current === id", arg=want)
    page.wait_for_function(SAME)
    page.wait_for_selector("#bulkbar", state="hidden")
    assert errors == []


def test_drafts_survive_switching_settings_deskopen_and_back(env):
    d, store, server, page, errors = env
    a = post(d, kind="decision", title="决定甲", body="正文 $x^2$", options=["一", "二", "三"], allow_text=True)
    b = post(d, kind="decision", title="决定乙", options=["是", "否"], allow_text=True)
    c = post(d, kind="answer", title="一个回答", body="x")
    store.poll()
    page.goto(server.url)

    def show(mid, title, how="click"):
        if how == "click":
            page.click(f'.item[data-id="{mid}"]')
        else:
            page.evaluate("id => deskOpen(id)", mid)
        page.wait_for_function("t => document.getElementById('title').textContent === t", arg=title)

    def draft():
        return (page.input_value("#replyText"), page.evaluate(
            "[...document.querySelectorAll('#options .opt.checked')].map(b => +b.dataset.idx)"), page.evaluate("deskTest.S.choice"))

    show(a, "决定甲")
    page.click('#options .opt[data-idx="1"]')
    page.fill("#replyText", "草稿甲")
    show(b, "决定乙")
    assert draft() == ("", [], None)  # 别的消息不带过去
    page.click('#options .opt[data-idx="0"]')
    page.fill("#replyText", "草稿乙")
    show(c, "一个回答")
    show(a, "决定甲")
    assert draft() == ("草稿甲", [1], "二")
    assert page.is_enabled("#submitBtn")

    # 改设置：只重画正文，选项和文字不动
    page.click("#settingsBtn")
    page.click('[data-set="density"][data-val="compact"]')
    page.click('[data-set="size"][data-val="l"]')
    page.wait_for_function("() => document.documentElement.dataset.size === 'l'")
    assert draft() == ("草稿甲", [1], "二")
    assert page.locator("#body .katex").count() == 1
    page.click("#settingsBtn")

    # 从通知打开别的消息，再回来
    show(b, "决定乙", how="open")
    assert draft() == ("草稿乙", [0], "是")
    show(a, "决定甲", how="open")
    assert draft() == ("草稿甲", [1], "二")

    # 窄窗口：返回列表再打开
    page.set_viewport_size({"width": 600, "height": 800})
    page.click("#backBtn")
    page.wait_for_selector("#detail", state="hidden")
    show(a, "决定甲")
    assert draft() == ("草稿甲", [1], "二")

    # 提交成功后草稿丢掉
    page.click("#submitBtn")
    page.wait_for_selector("#doneBox:not([hidden])")
    r = [x for x in desk.read_all(d / desk.RESPONSES) if x["id"] == a][0]
    assert r["choice"] == "二" and r["text"] == "草稿甲"
    assert a not in page.evaluate("Object.keys(deskTest.S.drafts)")
    assert b in page.evaluate("Object.keys(deskTest.S.drafts)")
    assert errors == []


def test_duplicate_labels_submit_and_show_by_index(env):
    d, store, server, page, errors = env
    mid = post(d, kind="decision", title="怎么继续？", options=["继续::按方案 A", "继续::按方案 B"])
    done = post(d, kind="decision", title="已经回复过的", options=["继续::甲", "继续::乙"])
    store.poll()
    desk.write_response(done, "继续", "", "proj", d, extra={"choice_index": 2})
    store.poll()
    sent = []
    orig = server.action
    server.action = lambda body: (sent.append(dict(body)), orig(body))[1]
    page.goto(server.url)
    page.click(f'.item[data-id="{mid}"]')
    page.wait_for_function("() => document.getElementById('title').textContent === '怎么继续？'")
    page.click('#options .opt[data-idx="1"]')  # 第二个"继续"
    assert page.evaluate("[deskTest.S.choice, deskTest.S.choiceIdx]") == ["继续", 1]
    page.click("#submitBtn")
    page.wait_for_selector("#doneBox:not([hidden])")
    reply = [b for b in sent if b.get("action") == "reply"][0]
    assert reply["choice"] == "继续" and reply["choice_index"] == 2

    # 已回复的：按 choice_index 标出选中的那一个，不是两个同名的都标
    page.click(f'.item[data-id="{done}"]')
    page.wait_for_function("() => document.getElementById('title').textContent === '已经回复过的'")
    page.wait_for_selector("#options .opt.chosen")
    assert page.evaluate("[...document.querySelectorAll('#options .opt.chosen')].map(b => +b.dataset.idx)") == [1]
    assert errors == []


def test_keyboard_skim_marks_read_only_after_dwell(env):
    d, store, server, page, errors = env
    ids = [post(d, kind="answer", title=f"回答 {i}", body="x") for i in range(4)]
    store.poll()
    page.goto(server.url)
    page.wait_for_selector(".item")
    order = page.evaluate("deskTest.S.visible")
    unread = lambda i: store.is_unread(store.msgs[order[i]])  # noqa: E731

    page.click(f'.item[data-id="{order[0]}"]')  # 点击：马上算读过
    assert wait_until(lambda: not unread(0))
    page.keyboard.press("j")
    page.keyboard.press("j")
    page.wait_for_function("id => deskTest.S.current === id", arg=order[2])
    page.wait_for_timeout(300)
    assert unread(1) and unread(2)
    assert page.locator(f'.item[data-id="{order[2]}"].unread').count() == 1
    assert page.locator(f'.item[data-id="{order[2]}"].selected').count() == 1
    # 停 0.8 秒：这一条才算读过；路过的那条还是未读
    page.wait_for_function("id => !document.querySelector('.item[data-id=\"' + id + '\"].unread')", arg=order[2])
    assert wait_until(lambda: not unread(2))
    page.wait_for_timeout(300)
    assert unread(1)
    assert page.inner_text('.tab[data-view="all"] .n') == "2"  # 计数跟着变
    # 从通知打开：马上算读过
    page.evaluate("id => deskOpen(id)", order[3])
    assert wait_until(lambda: not unread(3), timeout=0.6)
    assert errors == []


def test_new_arrivals_toast_when_hidden_and_highlight_when_visible(env):
    d, store, server, page, errors = env

    def mk(kind, title, repo, **kw):
        return desk.make_message(kind, "s", title, repo=repo, **kw)

    def drop(*msgs):  # 一次写进收件箱，保证同一轮长轮询一起拿到
        with open(d / desk.INBOX, "a", encoding="utf-8") as f:
            f.write("".join(json.dumps(m, ensure_ascii=False) + "\n" for m in msgs))
        store.poll()
        return [m["id"] for m in msgs]

    drop(mk("answer", "旧回答", "dotfiles"), mk("decision", "旧决定", "webapp", options=["A"]))
    page.goto(server.url)
    page.wait_for_selector(".item")
    page.click('.ptab[data-project="dotfiles"]')
    page.wait_for_function("() => document.querySelectorAll('.item').length === 1")
    page.wait_for_timeout(300)
    assert page.locator(".toast").count() == 0  # 刚打开时已有的消息不算新到

    # 别的项目来了一条待决定：弹一条提示，"查看"跳过去
    [x] = drop(mk("decision", "要不要合并？", "webapp", options=["要", "不要"]))
    t = page.locator(".toast", has_text="webapp 需要你决定：要不要合并？")
    t.wait_for()
    t.locator("button", has_text="查看").click()
    page.wait_for_function("id => deskTest.S.current === id", arg=x)
    page.wait_for_function(SAME)

    # 看得见的新消息：高亮一下，不弹提示
    [y] = drop(mk("info", "看得见的新通知", "webapp", priority="high"))
    page.wait_for_selector(f'.item.fresh[data-id="{y}"]')
    assert page.locator(".toast").count() == 0
    page.wait_for_selector(f'.item.fresh[data-id="{y}"]', state="detached", timeout=4000)
    assert page.locator(f'.item[data-id="{y}"]').count() == 1

    # 看不见的一次来了几条：只弹一条
    drop(mk("info", "紧急一", "dotfiles", priority="high"), mk("decision", "再决定", "dotfiles", options=["A"]),
         mk("info", "普通通知", "dotfiles"))
    page.locator(".toast", has_text="2 条新的待决定").wait_for()
    assert page.locator(".toast").count() == 1
    # 只有一条紧急通知时写"紧急："
    page.evaluate("document.getElementById('toasts').innerHTML = ''")
    drop(mk("info", "数据源 403", "dotfiles", priority="high"))
    page.locator(".toast", has_text="紧急：数据源 403").wait_for()
    assert errors == []


def _dropper(d, store):
    def mk(kind, title, repo, **kw):
        return desk.make_message(kind, "s", title, repo=repo, **kw)

    def drop(*msgs):  # 一次写进收件箱，保证同一轮长轮询一起拿到
        with open(d / desk.INBOX, "a", encoding="utf-8") as f:
            f.write("".join(json.dumps(m, ensure_ascii=False) + "\n" for m in msgs))
        store.poll()
        return [m["id"] for m in msgs]
    return mk, drop


def test_arrival_off_screen_toasts_and_n_opens_it_across_projects(env):
    """全部项目视图里，新到的待决定插在屏幕外：也弹提示；提示还在时按 N 先打开它，筛着别的项目也能跨过去。"""
    d, store, server, page, errors = env
    mk, drop = _dropper(d, store)
    drop(*[mk("answer", f"回答 {i}", "aaa") for i in range(20)], mk("decision", "aaa 的决定", "aaa", options=["A"]))
    page.goto(server.url)
    page.wait_for_selector(".item")
    page.click(".item >> nth=1")  # 在看一条回答
    page.wait_for_function(SAME)
    # 新的待决定来自排在最后的项目：插在列表底下，屏幕外
    [x] = drop(mk("decision", "要不要发版？", "zzz", options=["发", "不发"], priority="high"))
    t = page.locator(".toast", has_text="zzz 需要你决定：要不要发版？")
    t.wait_for()
    assert t.locator("button").inner_text() == "查看（N）"
    assert page.evaluate("""id => document.querySelector('.item[data-id="' + id + '"]').getBoundingClientRect().top
        >= document.getElementById('list').getBoundingClientRect().bottom""", x)
    page.keyboard.press("n")  # 提示还在：N 打开它，不是队列里 aaa 的那条
    page.wait_for_function("id => deskTest.S.current === id", arg=x)
    page.wait_for_function(SAME)
    assert page.locator(".toast", has_text="要不要发版？").count() == 0  # 用过的提示收起来

    # 只看 aaa 时，zzz 又来一条：N 跨项目打开它
    page.click('.ptab[data-project="aaa"]')
    page.wait_for_function("() => deskTest.S.projects.has('aaa') && !deskTest.S.current")
    [y] = drop(mk("decision", "第二个要决定的", "zzz", options=["A"]))
    page.locator(".toast", has_text="zzz 需要你决定：第二个要决定的").wait_for()
    page.keyboard.press("n")
    page.wait_for_function("id => deskTest.S.current === id", arg=y)
    page.wait_for_function(SAME)
    assert page.evaluate("Array.from(deskTest.S.projects)") == ["zzz"]
    page.keyboard.press("n")  # 之后照常走队列（紧急的先）
    page.wait_for_function("id => deskTest.S.current === id", arg=x)
    assert errors == []


def test_arrival_toast_in_a_narrow_window(env):
    """窄窗口在看一条时，阅读页盖住了列表：同一项目新到的待决定也弹提示；提示条用满宽度，长标题最多两行，按钮不折行。"""
    d, store, server, page, errors = env
    mk, drop = _dropper(d, store)
    [a] = drop(mk("decision", "正在看的决定", "proj", options=["A", "B"]))
    page.set_viewport_size({"width": 480, "height": 800})
    page.goto(server.url)
    page.wait_for_selector(".item")
    page.evaluate("id => deskOpen(id)", a)
    page.wait_for_function("document.getElementById('app').classList.contains('reading')")
    long = "发布前要不要先把 build 129 推到测试通道，让 app-ui 和 app-core 的改动先在内部跑一天、确认没问题以后再推给所有人？"
    drop(mk("decision", long, "proj", options=["推", "不推"], priority="high"))
    t = page.locator(".toast", has_text="proj 需要你决定")
    t.wait_for()
    page.wait_for_function("document.getElementById('reader').getBoundingClientRect().left === 0")  # 提示条在阅读页里：等它滑进来停稳再量
    tb, bb = t.bounding_box(), t.locator("button").bounding_box()
    assert tb["x"] >= 15 and tb["x"] + tb["width"] <= 465 and tb["width"] > 400  # 原来只有半个窗口宽
    assert tb["height"] <= 60 and bb["height"] <= 28  # 两行以内；"查看（N）"不一字一行
    assert errors == []


def test_submit_in_flight_state_failure_and_retry(env):
    d, store, server, page, errors = env
    a = post(d, kind="decision", title="慢慢提交", options=["甲", "乙"], allow_text=True)
    store.poll()
    orig = server.action
    gate = threading.Event()
    mode = {"fail": True}

    def patched(body):
        if body.get("action") == "reply":
            gate.wait(10)
            if mode["fail"]:
                raise ActionError("服务端忙")
        return orig(body)

    server.action = patched
    page.goto(server.url)
    page.click(f'.item[data-id="{a}"]')
    page.wait_for_function("() => document.getElementById('title').textContent === '慢慢提交'")
    page.click('#options .opt[data-idx="1"]')
    page.fill("#replyText", "补充一句")
    page.click("#submitBtn")

    # 提交中：按钮写"提交中…"，选项、输入框锁住，#decide aria-busy
    page.wait_for_function("() => document.getElementById('submitBtn').textContent === '提交中…'")
    st = page.evaluate("""() => ({ busy: document.getElementById('decide').getAttribute('aria-busy'),
        btn: document.getElementById('submitBtn').disabled, ro: document.getElementById('replyText').readOnly,
        opts: [...document.querySelectorAll('#options .opt')].map(b => b.disabled),
        checked: [...document.querySelectorAll('#options .opt.checked')].map(b => +b.dataset.idx) })""")
    assert st == {"busy": "true", "btn": True, "ro": True, "opts": [True, True], "checked": [1]}
    assert page.inner_text("#decideHint") == "正在发给会话…"  # 不再说"Ctrl+Enter 提交「乙」"
    page.click('#options .opt[data-idx="0"]', force=True)  # 锁住时点别的选项没用
    assert page.evaluate("deskTest.S.choiceIdx") == 1

    # 失败：原样恢复，提示里有"重试"
    gate.set()
    bad = page.locator(".toast.bad", has_text="提交失败：服务端忙")
    bad.wait_for()
    st = page.evaluate("""() => ({ busy: document.getElementById('decide').getAttribute('aria-busy'),
        text: document.getElementById('submitBtn').textContent, btn: document.getElementById('submitBtn').disabled,
        ro: document.getElementById('replyText').readOnly, val: document.getElementById('replyText').value,
        opts: [...document.querySelectorAll('#options .opt')].map(b => b.disabled),
        checked: [...document.querySelectorAll('#options .opt.checked')].map(b => +b.dataset.idx) })""")
    assert st == {"busy": "false", "text": "提交", "btn": False, "ro": False, "val": "补充一句", "opts": [False, False], "checked": [1]}
    assert page.inner_text("#decideHint") == "Ctrl+Enter 提交「乙」"
    assert a not in store.responses

    # 重试成功：完成框写"已提交 · 今天 00:07 · 会话已收到"和补充的话；选了哪项看打了 ✓ 的那项，不再重复
    mode["fail"] = False
    bad.locator("button", has_text="重试").click()
    page.wait_for_selector("#doneBox:not([hidden])")
    done = page.inner_text("#doneBox")
    assert re.match(r"已提交 · (今天|昨天) \d\d:\d\d · 会话已收到", done), done
    assert "补充一句" in done and "选择：" not in done
    assert page.evaluate("[...document.querySelectorAll('#options .opt.chosen')].map(b => b.dataset.idx + ':' + b.textContent)") == ["1:乙"]
    r = [x for x in desk.read_all(d / desk.RESPONSES) if x["id"] == a][0]
    assert r["choice"] == "乙" and r["text"] == "补充一句"
    assert errors == []


def test_print_options_copy_text_reply_and_legacy_colour(env):
    d, store, server, page, errors = env
    a = post(d, kind="decision", title="接下来做什么？", body="说说你的想法", options=["先修 CI::再发版", "直接发版"],
             recommended=1, allow_text=True)
    old = post(d, kind="answer", title="旧消息", body="x", source="old-experiment")
    store.poll()
    page.goto(server.url)
    page.click(f'.item[data-id="{a}"]')
    page.wait_for_function("() => document.getElementById('title').textContent === '接下来做什么？'")
    # PDF / 打印：还没决定的选项也印出来，标出推荐
    page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
    pr = page.evaluate("document.getElementById('printRoot').textContent")
    assert "先修 CI（推荐）：再发版" in pr and "直接发版" in pr
    page.evaluate("window.dispatchEvent(new Event('afterprint'))")
    # 复制 Markdown：只写了文字的回复也带上；跳过 / 已处理的系统文字不算"我的回复"
    md = page.evaluate("deskTest.markdownOf({ title: 't', body: 'b', response: { choice: null, text: '先把 CI 修好' } })")
    assert md.endswith("**我的回复：** 先把 CI 修好\n")
    md = page.evaluate("deskTest.markdownOf({ title: 't', body: 'b', response: { choice: null, text: '跳过', dismissed: true } })")
    assert "我的回复" not in md
    # 认不出仓库的旧来源：阅读区的圆点是灰的，不占项目颜色
    page.click(f'.item[data-id="{old}"]')
    page.wait_for_function("() => document.getElementById('title').textContent === '旧消息'")
    assert "old-experiment" not in json.loads(page.evaluate("localStorage.getItem('desk.pcolors') || '{}'"))
    assert errors == []


def test_detail_cache_is_capped(env):
    d, store, server, page, errors = env
    ids = [post(d, kind="answer", title=f"回答 {i}", body="x") for i in range(70)]
    store.poll()
    page.goto(server.url)
    page.wait_for_selector(".item")
    page.evaluate("""async ids => { for (const id of ids) { deskTest.select(id, { noRead: true });
        while (!(deskTest.S.shownKey || '').startsWith(id + '|')) await new Promise(r => setTimeout(r, 5)); } }""", ids)
    keys = page.evaluate("Object.keys(deskTest.S.details)")
    assert len(keys) <= 60 and keys[-1].startswith(ids[-1] + "|")
    assert errors == []
