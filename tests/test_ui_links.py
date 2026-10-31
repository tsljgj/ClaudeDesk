"""链接和右键菜单：网址都能点、在系统浏览器里打开（桌面程序交给 open_url）；右键能复制、复制链接、粘贴。"""
import desk
from claudedesk.server import external_url
from test_ui import env, post  # noqa: F401  env 是 fixture


def app_mode(server):
    """当成桌面程序里的窗口：BOOT.app = true，open_url / clipboard_text 记下调用，不真的开浏览器、读剪贴板。"""
    opened = []
    server.meta["app"] = True
    server.extra_actions["open_url"] = lambda body: (opened.append(external_url(body.get("url"))), True)[1]
    server.extra_actions["clipboard_text"] = lambda body: "剪贴板里的字"
    return opened


def open_msg(page, server, mid):
    page.goto(server.url)
    page.wait_for_selector(f'.item[data-id="{mid}"]')
    page.click(f'.item[data-id="{mid}"]')
    page.wait_for_function("id => document.querySelector('#detail') && !document.querySelector('#detail').hidden", arg=mid)


def test_links_everywhere_open_in_the_system_browser(env):
    d, store, server, page, errors = env
    opened = app_mode(server)
    a = post(d, kind="decision", title="要合并吗？", question="看下 https://example.com/q 再说",
             body="见https://example.com/a查看，代码在 `https://example.com/pr/12`。",
             options=["合并::CI 在 https://example.com/ci 全绿", "再等等::"])
    store.poll()
    open_msg(page, server, a)
    page.wait_for_selector('#body a[href="https://example.com/a"]')
    pages = len(page.context.pages)

    def click(sel, **kw):
        with page.expect_response(lambda r: r.url.endswith("/api/action") and r.request.post_data_json.get("action") == "open_url"):
            page.click(sel, **kw)

    click('#body a[href="https://example.com/a"]')
    click('#body code a[href="https://example.com/pr/12"]')
    click('#questionText a[href="https://example.com/q"]')
    click('.opt .desc a[href="https://example.com/ci"]')  # 选项说明里的链接：只打开，不选这一项
    click('.opt .desc a[href="https://example.com/ci"]', button="middle")
    assert opened == ["https://example.com/a", "https://example.com/pr/12", "https://example.com/q",
                      "https://example.com/ci", "https://example.com/ci"]
    assert page.locator(".opt.checked").count() == 0
    assert len(page.context.pages) == pages  # 没有在窗口里开新页
    page.click('.opt[data-idx="0"] .lab')  # 点选项别处照常选中
    assert page.locator('.opt[data-idx="0"].checked').count() == 1
    assert errors == []


def test_follow_ups_and_replies_link_urls(env):
    d, store, server, page, errors = env
    app_mode(server)
    a = post(d, kind="answer", title="回答", body="正文")
    store.poll()
    store.add_followup(a, "那 https://example.com/x 呢？")
    b = post(d, kind="decision", title="决定", body="b", options=["甲::"])
    store.poll()
    store.submit(b, "甲", "补充：参考 https://example.com/y")
    open_msg(page, server, a)
    page.wait_for_selector('.fu-q a[href="https://example.com/x"]')
    page.click(f'.item[data-id="{b}"]')
    page.wait_for_selector('.reply-text a[href="https://example.com/y"]')
    assert errors == []


def test_right_click_menu_copies_links_text_and_pastes(env):
    d, store, server, page, errors = env
    app_mode(server)
    a = post(d, kind="decision", title="右键", body="一段**可以复制**的文字，链接 https://example.com/r 。\n\n```\ncode line\n```",
             options=["甲::"])
    store.poll()
    open_msg(page, server, a)
    page.wait_for_selector('#body a[href="https://example.com/r"]')

    page.click('#body a[href="https://example.com/r"]', button="right")
    page.wait_for_selector('#popover:not([hidden]) [data-ctx="copy_link"]')
    labels = page.locator("#popover [data-ctx]").all_inner_texts()
    assert any("在浏览器中打开" in x for x in labels) and any("复制链接地址" in x for x in labels)
    page.click('#popover [data-ctx="copy_link"]')
    page.wait_for_function("() => document.querySelector('#popover').hidden")
    assert page.evaluate("navigator.clipboard.readText()") == "https://example.com/r"

    # 选中一段文字再右键：复制选中的（带格式）
    page.evaluate("""() => {
      const s = document.querySelector('#body strong'), r = document.createRange();
      r.selectNodeContents(s); getSelection().removeAllRanges(); getSelection().addRange(r);
      const b = s.getBoundingClientRect();
      s.dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, cancelable: true, clientX: b.left + 2, clientY: b.top + 2}));
    }""")
    page.wait_for_selector('#popover:not([hidden]) [data-ctx="copy"]')
    page.click('#popover [data-ctx="copy"]')
    page.wait_for_function("async () => (await navigator.clipboard.readText()) === '可以复制'")

    # 代码块：复制这段代码；阅读区：复制整条
    page.click("#body pre code", button="right")
    page.wait_for_selector('#popover:not([hidden]) [data-ctx="copy_code"]')
    assert page.locator('#popover [data-ctx="copy_md"]').count() == 1
    page.click('#popover [data-ctx="copy_code"]')
    page.wait_for_function("async () => (await navigator.clipboard.readText()) === 'code line'")

    # 输入框：粘贴（走程序读剪贴板）、全选、剪切
    page.fill("#replyText", "前后")
    page.evaluate("""() => {
      const t = document.querySelector('#replyText'), b = t.getBoundingClientRect();
      t.focus(); t.setSelectionRange(1, 1);
      t.dispatchEvent(new MouseEvent('contextmenu', {bubbles: true, cancelable: true, clientX: b.left + 5, clientY: b.top + 5}));
    }""")
    page.wait_for_selector('#popover:not([hidden]) [data-ctx="paste"]')
    assert page.locator('#popover [data-ctx="cut"]').is_disabled()  # 没选中东西
    page.click('#popover [data-ctx="paste"]')
    page.wait_for_function("() => document.querySelector('#replyText').value === '前剪贴板里的字后'")
    assert page.evaluate("document.activeElement.id") == "replyText"
    assert not page.locator("#submitBtn").is_disabled()  # 和打字一样：提交按钮跟着亮
    page.click("#replyText", button="right", position={"x": 5, "y": 5})
    page.click('#popover [data-ctx="field_all"]')
    page.click("#replyText", button="right", position={"x": 5, "y": 5})
    page.click('#popover [data-ctx="cut"]')
    page.wait_for_function("() => document.querySelector('#replyText').value === ''")
    assert page.evaluate("navigator.clipboard.readText()") == "前剪贴板里的字后"

    # 列表行还是自己的菜单
    page.click(f'.item[data-id="{a}"]', button="right")
    page.wait_for_selector('#popover:not([hidden]) [data-m="read"]')
    assert page.locator("#popover [data-ctx]").count() == 0
    page.keyboard.press("Escape")
    assert errors == []


def test_browser_keeps_its_own_menu_and_links(env):
    """--serve / 手机：不拦右键，链接照常 target=_blank。"""
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="浏览器", body="见 https://example.com/b")
    store.poll()
    open_msg(page, server, a)
    page.wait_for_selector('#body a[href="https://example.com/b"][target="_blank"]')
    prevented = page.evaluate("""() => {
      const a = document.querySelector('#body a');
      const e = new MouseEvent('contextmenu', {bubbles: true, cancelable: true, clientX: 10, clientY: 10});
      a.dispatchEvent(e);
      return e.defaultPrevented;
    }""")
    assert prevented is False and page.locator("#popover").is_hidden()
    assert errors == []


def test_external_url_only_allows_web_and_mail_links():
    ok = ["https://example.com/a?b=1&c=%E4%B8%AD", "http://localhost:8080/", "mailto:someone@example.com"]
    bad = ["", None, "javascript:alert(1)", "file:///C:/Windows/system32/calc.exe", "ms-settings:display",
           "https://exa mple.com", "https://example.com/\r\nx", "http:/x", "mailto:", "C:\\x.exe", "//example.com"]
    assert [external_url(u) for u in ok] == ok
    assert [external_url(u) for u in bad] == [None] * len(bad)
    assert desk  # 保持导入（和别的测试文件一样用真 desk.py 发消息）
