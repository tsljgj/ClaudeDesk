"""在真浏览器（Playwright + Chromium）里驱动界面。没装 Playwright 时跳过。"""
import os
import threading

import desk
import pytest
from claudedesk.server import DeskServer
from claudedesk.store import Store

pw = pytest.importorskip("playwright.sync_api")

BODY = r"""背景说明。

| 指标 | 值 |
|---|---:|
| 范数 $\|\theta\|_2$ | 12.9 |
| 绝对值 $|x|$ | 3 |
| 命令 `a|b` | 1 |

$$
\begin{aligned} a &= b \\ c &= d \end{aligned}
$$

花了 $5 和 $10。行内 \(e^{i\pi}+1=0\)。

```python
print("hi")
```
"""


@pytest.fixture()
def env(tmp_path):
    store = Store(tmp_path)
    server = DeskServer(store).start_background()
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            store.poll()
            stop.wait(0.2)

    threading.Thread(target=loop, daemon=True).start()
    local = "/opt/pw-browsers/chromium"
    exe = os.environ.get("CHROMIUM_PATH") or (local if os.path.exists(local) else None)
    with pw.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1300, "height": 850})
        ctx.grant_permissions(["clipboard-read", "clipboard-write"])
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        yield tmp_path, store, server, page, errors
        browser.close()
    stop.set()
    server.shutdown()


def post(d, **kw):
    kw.setdefault("source", "proj")
    return desk.post_message(desk.make_message(**kw), d)


def test_render_reply_archive_delete(env):
    d, store, server, page, errors = env
    a = post(d, kind="decision", title="选哪个？", body=BODY, options=["甲::说明甲", "乙::说明乙"], recommended=2,
             allow_text=True, priority="high")
    b = post(d, kind="answer", title="一个回答", question="原问题？", body="答案 $x^2$")
    store.poll()
    page.goto(server.url)
    page.wait_for_selector(f'.item[data-id="{a}"]')
    page.click(f'.item[data-id="{a}"]')
    page.wait_for_selector("#body .katex")

    # 公式 / 表格
    assert page.locator("#body .katex-display").count() == 1
    cells = page.locator("#body table tbody tr").all()
    assert len(cells) == 3 and all(r.locator("td").count() == 2 for r in cells)  # 公式和代码里的 | 没把单元格切开
    assert page.locator("#body table .katex").count() == 2
    assert page.locator("#body table code").inner_text() == "a|b"
    assert "花了 $5 和 $10" in page.locator("#body").inner_text()  # 价格不是公式
    assert page.locator("#body .math-error").count() == 0
    assert page.locator("#body .codeblock .code-copy").count() == 1

    # 选择 + 补充 + 提交
    page.keyboard.press("2")
    page.fill("#replyText", "补充一句")
    page.keyboard.press("Control+Enter")
    page.wait_for_selector("#doneBox:not([hidden])")
    resp = [r for r in desk.read_all(d / desk.RESPONSES) if r["id"] == a]
    assert resp and resp[0]["choice"] == "乙" and resp[0]["text"] == "补充一句"
    page.wait_for_selector(f'.item[data-id="{a}"] .st.done')

    # 复制 Markdown
    page.click("#copyBtn")
    clip = page.evaluate("navigator.clipboard.readText()")
    assert clip.startswith("# 选哪个？") and "**我的选择：** 乙" in clip

    # 归档 → 撤销
    page.keyboard.press("e")
    page.wait_for_selector(".toast button")
    assert a in store.archived
    page.click(".toast button")
    page.wait_for_function(f"() => !!document.querySelector('.item[data-id=\"{a}\"]')")
    assert a not in store.archived

    # 删除（确认框）
    page.click(f'.item[data-id="{a}"]')
    page.keyboard.press("Delete")
    page.wait_for_selector("#modal:not([hidden])")
    page.click("#modalOk")
    page.wait_for_function(f"() => !document.querySelector('.item[data-id=\"{a}\"]')")
    assert a not in (d / desk.INBOX).read_text(encoding="utf-8")

    # 搜索正文
    page.click('[data-view="all"]')
    page.fill("#search", "答案")
    page.wait_for_function(
        f"() => document.querySelectorAll('.item').length === 1 && !!document.querySelector('.item[data-id=\"{b}\"]')")
    assert errors == []


def test_dismiss_open_decision_by_archive(env):
    d, store, server, page, errors = env
    a = post(d, kind="decision", title="还在等", options=["A"])
    store.poll()
    page.goto(server.url)
    page.locator(f'.item[data-id="{a}"]').hover()
    page.click(f'.item[data-id="{a}"] [data-act="archive"]')
    page.wait_for_selector("#modal:not([hidden])")
    page.click("#modalOk")
    page.wait_for_selector(".toast")
    r = [x for x in desk.read_all(d / desk.RESPONSES) if x["id"] == a][0]
    assert r["dismissed"] is True and r["choice"] is None
    page.click('[data-view="archive"]')
    page.wait_for_selector(f'.item[data-id="{a}"] .st.skip')
    assert errors == []


def test_multiselect_bulk_archive_and_print_layout(env):
    d, store, server, page, errors = env
    ids = [post(d, kind="answer", title=f"回答 {i}", body=f"正文 {i}") for i in range(3)]
    store.poll()
    page.goto(server.url)
    page.click('[data-view="answer"]')
    order = page.evaluate("deskTest.S.visible")
    page.click(f'.item[data-id="{order[0]}"]')
    page.click(f'.item[data-id="{order[-1]}"]', modifiers=["Shift"])
    page.wait_for_selector("#bulkbar:not([hidden])")
    assert "3" in page.inner_text("#bulkCount")
    page.click('[data-bulk="archive"]')
    page.wait_for_function("() => document.querySelectorAll('.item').length === 0")
    assert set(ids) <= store.archived

    # 打印 / PDF：只印文章
    page.click('[data-view="archive"]')
    page.click(f'.item[data-id="{ids[1]}"]')
    page.wait_for_function("() => document.getElementById('title').textContent === '回答 1'")
    page.evaluate("window.print = () => { window.__printed = document.getElementById('printRoot').innerText; }")
    page.click("#pdfBtn")
    printed = page.evaluate("window.__printed")
    assert "回答 1" in printed and "正文 1" in printed
    page.emulate_media(media="print")
    assert page.locator(".app").is_hidden()
    assert errors == []


def test_settings_persist(env):
    d, store, server, page, errors = env
    page.goto(server.url)
    page.click("#settingsBtn")
    page.click('[data-set="theme"][data-val="dark"]')
    page.click('[data-set="accent"][data-val="indigo"]')
    page.wait_for_function("() => document.documentElement.dataset.accent === 'indigo'")
    page.wait_for_timeout(200)
    assert store.setting("theme") == "dark" and store.setting("accent") == "indigo"
    page.reload()
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"
    assert errors == []


def test_hover_actions_and_checkbox_bulk(env):
    d, store, server, page, errors = env
    a = post(d, kind="decision", title="待定一", options=["A", "B"])
    b = post(d, kind="decision", title="待定二", options=["A", "B"])
    c = post(d, kind="answer", title="回答一", body="x")
    store.poll()
    page.goto(server.url)
    page.click('[data-view="all"]')
    item = page.locator(f'.item[data-id="{c}"]')
    item.wait_for()
    # 没悬停时操作按钮和勾选框都看不见
    assert item.locator(".acts").evaluate("e => getComputedStyle(e).opacity") == "0"
    assert item.locator(".cb").evaluate("e => getComputedStyle(e).opacity") == "0"
    item.hover()
    page.wait_for_function(f"() => getComputedStyle(document.querySelector('.item[data-id=\"{c}\"] .acts')).opacity === '1'")
    # 悬停归档：只动这一条，右边不用先打开
    item.locator('[data-act="archive"]').click()
    page.wait_for_function(f"() => !document.querySelector('.item[data-id=\"{c}\"]')")
    assert c in store.archived and store.is_unread(store.msgs[a])

    # 勾两条 → 批量"已解决"
    page.locator(f'.item[data-id="{a}"]').hover()
    page.locator(f'.item[data-id="{a}"] .cb').click()
    page.wait_for_selector("#bulkbar:not([hidden])")
    assert page.locator(f'.item[data-id="{b}"] .cb').evaluate("e => getComputedStyle(e).opacity") == "1"  # 多选时都显示
    page.locator(f'.item[data-id="{b}"] .cb').click()
    assert "2" in page.inner_text("#bulkCount")
    assert page.is_visible("#bulkResolve")
    page.click('[data-bulk="resolve"]')
    page.wait_for_selector("#bulkbar", state="hidden")
    resp = {r["id"]: r for r in desk.read_all(d / desk.RESPONSES)}
    assert resp[a]["resolved"] is True and resp[b]["resolved"] is True and resp[a]["choice"] is None
    page.wait_for_selector(f'.item[data-id="{a}"] .st.done')

    # 当前打开的那条有强调竖条
    page.click(f'.item[data-id="{b}"]')
    bar = page.locator(f'.item[data-id="{b}"]').evaluate("e => getComputedStyle(e, '::before').width")
    assert bar == "3px"
    # 全选框
    page.locator(f'.item[data-id="{b}"] .cb').click()
    page.click("#checkAll")
    page.wait_for_function("() => document.querySelectorAll('.item.multi').length === document.querySelectorAll('.item').length")
    page.click("#checkAll")
    page.wait_for_selector("#bulkbar", state="hidden")
    assert errors == []


def test_projects_are_separated(env):
    d, store, server, page, errors = env
    mk = lambda kind, source, title, repo=None, **kw: desk.post_message(  # noqa: E731
        desk.make_message(kind, source, title, repo=repo, **kw), d)
    a = mk("decision", "run-3", "OS 决定", repo="osworld", options=["A"])
    b = mk("answer", "osworld/eval", "OS 旧回答")  # 旧消息：来源能对上 osworld
    c = mk("answer", "x", "A 股回答", repo="cn-equity-research")
    o = mk("info", "数据清洗", "没认出来的")  # 旧消息：对不上任何仓库 -> 其他
    store.poll()
    page.goto(server.url)
    page.click('[data-view="all"]')
    page.wait_for_selector(".ptab")
    names = [t.split("\n")[0] for t in page.locator(".ptab .pname").all_inner_texts()]
    assert names == ["全部", "osworld", "cn-equity-research", "其他"]
    # 全部：按项目分组，同一项目挨在一起；对不上的在最后、标着"未识别"
    assert page.locator(".group-label .gname").all_inner_texts() == ["osworld", "cn-equity-research", "数据清洗"]
    order = page.evaluate("deskTest.S.visible")
    assert set(order[:2]) == {a, b} and order[2:] == [c, o]
    assert page.locator(".group-label.other .gtag").count() == 1
    # 点标签：只看它；视图计数跟着变；再点一次取消
    page.click('.ptab[data-project="cn-equity-research"]')
    page.wait_for_function("() => document.querySelectorAll('.item').length === 1")
    assert page.inner_text('.tab[data-view="decide"]').strip() == "决定"
    assert page.locator(".group-label").count() == 0
    page.click('.ptab[data-project="cn-equity-research"]')
    page.wait_for_function("() => document.querySelectorAll('.item').length === 4")
    # Ctrl + 点：同时看两个
    page.click('.ptab[data-project="cn-equity-research"]')
    page.click('.ptab[data-project="__other__"]', modifiers=["Control"])
    page.wait_for_function("() => document.querySelectorAll('.item').length === 2")
    assert page.locator(".ptab.on").count() == 2
    # 列表菜单"全部标为已读"只动选中的项目
    page.click("#listMenuBtn")
    page.click('[data-l="read_all"]')
    page.wait_for_function(f"() => !document.querySelector('.item[data-id=\"{c}\"].unread')")
    assert store.is_unread(store.msgs[a]) and not store.is_unread(store.msgs[o])
    # 把"未识别"的来源归到 osworld
    page.click('.ptab[data-project=""]')
    page.locator('.group-label.other .gmerge').click()
    page.click('.popover [data-to="osworld"]')
    page.wait_for_function("() => !document.querySelector('.ptab[data-project=\"__other__\"]')")
    assert store.aliases == {"数据清洗": "osworld"}
    assert store.summary(store.msgs[o])["project"] == "osworld"
    # [ ] 切换；从通知打开别的项目的消息：自动切过去
    page.keyboard.press("]")
    page.wait_for_function("() => deskTest.S.projects.size === 1")
    page.evaluate(f"deskOpen('{c}')")
    page.wait_for_function("() => deskTest.S.projects.has('cn-equity-research')")
    assert errors == []
