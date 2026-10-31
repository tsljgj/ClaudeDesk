"""手机访问的界面：电脑上在设置里打开、拿链接和二维码、换链接；手机上（小屏、触屏）打开链接就是同一个收件箱，
能回复，点推送通知（#m=<id>）直接打开那条，外观只改手机自己的。"""
import socket

import desk
import pytest
from claudedesk import remote as rm
from test_ui import env, post  # noqa: F401  env 是 fixture


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture()
def desk_env(env, monkeypatch):
    d, store, server, page, errors = env
    monkeypatch.setattr(rm, "addresses", lambda: [{"host": "127.0.0.1", "kind": "lan"},
                                                  {"host": "pc.tailnet.ts.net", "kind": "tailscale"}])
    r = rm.Remote(store, server, idle=lambda: None, post=lambda srv, body: None)
    server.extra_actions["remote"] = r.action
    server.meta["app"] = True
    store.state["remote"] = {"port": free_port()}
    r.start()
    return d, store, server, page, errors, r


def phone(page):
    ctx = page.context.browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    p = ctx.new_page()
    errs = []
    p.on("pageerror", lambda e: errs.append(str(e)))
    return ctx, p, errs


def test_turn_on_from_settings_copy_link_and_rotate_key(desk_env):
    d, store, server, page, errors, r = desk_env
    page.goto(server.url)
    page.click("#settingsBtn")
    page.wait_for_selector('#popover [data-app="remote"]')
    assert "关" in page.locator('#popover [data-app="remote"]').inner_text()
    page.click('#popover [data-app="remote"]')
    page.wait_for_selector('#remotePanel [data-rp="enable"][aria-pressed="false"]')
    assert page.locator(".rp-qr").count() == 0
    page.click('[data-rp="enable"]')
    page.wait_for_selector(".rp-qr svg")
    key = store.state["remote"]["key"]
    port = server.remote_port
    assert page.locator(".rp-url").inner_text() == f"http://127.0.0.1:{port}/?k={key}"
    assert page.locator(".rp-links button").all_inner_texts() == ["局域网", "Tailscale"]
    page.click('[data-rp-link="1"]')
    assert page.locator(".rp-url").inner_text() == f"http://pc.tailnet.ts.net:{port}/?k={key}"
    assert "在哪都能打开" in page.locator(".rp-hint").inner_text()
    page.click('[data-rp="copy"]')
    page.wait_for_function("async u => (await navigator.clipboard.readText()) === u", arg=f"http://pc.tailnet.ts.net:{port}/?k={key}")

    page.click('[data-rp="new_key"]')  # 换链接要再问一句；取消就什么都不变
    page.wait_for_selector("#modalOk.danger")
    page.click("#modalCancel")
    page.wait_for_selector(".rp-qr svg")
    assert store.state["remote"]["key"] == key
    page.click('[data-rp="new_key"]')
    page.wait_for_selector("#modalOk.danger")
    page.click("#modalOk")
    page.wait_for_function("k => !document.querySelector('.rp-url').textContent.endsWith(k)", arg=key)
    assert store.state["remote"]["key"] != key

    page.click('[data-rp="push"]')  # 推送：打开就有主题
    page.wait_for_selector(".rp-topic")
    assert page.locator(".rp-topic").inner_text().startswith("claudedesk-")
    page.click('[data-rp-detail="none"]')
    page.wait_for_selector('[data-rp-detail="none"].on')
    assert store.state["remote"]["push"]["detail"] == "none"
    page.click("#modalOk")
    page.wait_for_selector("#modal", state="hidden")
    page.click("#settingsBtn")
    page.wait_for_function("() => document.querySelector('#popover [data-app=\"remote\"]').textContent.includes('已开 · 推送')")
    assert errors == []


def test_phone_opens_the_link_replies_and_follows_push_links(desk_env):
    d, store, server, page, errors, r = desk_env
    a = post(d, kind="decision", title="手机上回的决定", body="正文 https://example.com/x", options=["甲::", "乙::"])
    b = post(d, kind="answer", title="另一个项目的回答", body="答", repo="acme-data-pipeline")
    store.poll()
    r.action({"op": "enable", "on": True})
    key, port = store.state["remote"]["key"], server.remote_port
    ctx, p, errs = phone(page)
    try:
        p.goto(f"http://127.0.0.1:{port}/")
        assert "需要 ClaudeDesk 里的链接" in p.content()
        p.goto(f"http://127.0.0.1:{port}/?k={key}")
        p.wait_for_selector(f'.item[data-id="{a}"]')
        assert p.url == f"http://127.0.0.1:{port}/"  # 钥匙不留在地址栏里
        assert p.evaluate("BOOT.remote") is True and p.evaluate("BOOT.app") is False
        p.tap(f'.item[data-id="{a}"]')
        p.wait_for_selector("#app.reading")
        assert p.locator("#pdfBtn").is_hidden() and p.locator("#decideHint").is_hidden()
        assert p.evaluate("getComputedStyle(document.querySelector('#replyText')).fontSize") == "16px"
        p.tap('.opt[data-idx="1"]')
        p.fill("#replyText", "在手机上回的")
        p.tap("#submitBtn")
        p.wait_for_selector("#doneBox:not([hidden])")
        resp = [x for x in desk.read_all(d / desk.RESPONSES) if x.get("id") == a]
        assert [(x["choice"], x["text"]) for x in resp] == [("乙", "在手机上回的")]
        # 链接照常在新标签页打开（不交给电脑）
        assert p.locator('#body a[href="https://example.com/x"][target="_blank"]').count() == 1

        # 点推送通知：#m=<id>，别的项目里的也直接打开
        p.goto(f"http://127.0.0.1:{port}/#m={b}")
        p.wait_for_function("() => document.querySelector('#title').textContent === '另一个项目的回答'")
        p.wait_for_function("() => location.hash === ''")

        # 外观只改手机自己的
        p.tap("#backBtn")
        p.wait_for_selector("#app:not(.reading)")
        p.tap("#settingsBtn")
        p.wait_for_selector('#popover [data-set="theme"][data-val="dark"]')
        assert p.locator('#popover [data-app="remote"]').count() == 0
        p.tap('#popover [data-set="theme"][data-val="dark"]')
        p.wait_for_function("() => document.documentElement.dataset.theme === 'dark'")
        assert store.setting("theme", "system") == "system"
        p.reload()
        p.wait_for_selector(".item")
        assert p.evaluate("document.documentElement.dataset.theme") == "dark"
        assert errs == []
    finally:
        ctx.close()

    # 换了链接：手机上的页面打不开了
    r.action({"op": "new_key"})
    ctx, p, errs = phone(page)
    try:
        p.goto(f"http://127.0.0.1:{server.remote_port}/?k={key}")
        assert "需要 ClaudeDesk 里的链接" in p.content()
    finally:
        ctx.close()
    assert errors == []
