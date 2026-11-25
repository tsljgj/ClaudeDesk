"""回复里的本机路径：认出来变成能点的链接，点了交给程序打开（Ctrl / 中键 / 右键打开所在文件夹）；
程序查过不在的不像链接；浏览器、手机里点了复制路径。"""
from claudedesk.localfiles import Opener
from test_ui import env, post  # noqa: F401  env 是 fixture
from test_ui_links import open_msg

FILES = {"C:\\work\\report.md", "C:\\Program Files\\App\\readme.txt", "C:\\work\\a b.md", "C:\\work\\setup.exe"}
DIRS = {"D:\\proj\\data", "C:\\work"}


def app_mode(server):
    """当成桌面程序：open_path / path_info 用假的文件系统，记下打开、选中了什么。"""
    calls = []
    server.meta["app"] = True
    o = Opener(lambda p: calls.append(("open", p)), lambda p: calls.append(("reveal", p)),
               exists=lambda p: p in FILES or p in DIRS, isdir=lambda p: p in DIRS)
    server.extra_actions["open_path"] = o.open_path
    server.extra_actions["path_info"] = o.path_info
    return calls


BODY = ("报告在 C:\\work\\report.md，配置见 `C:\\Program Files\\App\\readme.txt`。\n\n"
        "数据放在 D:\\proj\\data下面，链接写法：[说明](file:///C:/work/a%20b.md)、[安装包](C:/work/setup.exe)。\n\n"
        "选项 A:/B 不是路径；网址 https://example.com/c/d 照旧。\n\n```\nC:\\work\\report.md\n```")


def test_paths_become_links_and_open(env):
    d, store, server, page, errors = env
    calls = app_mode(server)
    a = post(d, kind="decision", title="看文件", question="C:\\work 里的哪个？", body=BODY,
             options=["报告::见 C:\\work\\report.md", "再说::"])
    store.poll()
    open_msg(page, server, a)
    page.wait_for_selector('#body .path-link[data-st="dir"]')
    links = page.evaluate("""() => [...document.querySelectorAll('#detail .path-link')].map(a =>
        [a.closest('#body') ? 'body' : a.closest('#questionText') ? 'q' : 'opt', a.textContent, a.dataset.path, a.dataset.st])""")
    assert ["body", "C:\\work\\report.md", "C:\\work\\report.md", "file"] in links
    assert ["body", "C:\\Program Files\\App\\readme.txt", "C:\\Program Files\\App\\readme.txt", "file"] in links  # 行内代码：整段
    assert ["body", "D:\\proj\\data", "D:\\proj\\data", "dir"] in links  # "下面"挪出了链接
    assert ["body", "说明", "C:\\work\\a b.md", "file"] in links  # file:/// 的 Markdown 链接
    assert ["body", "安装包", "C:\\work\\setup.exe", "file"] in links
    assert ["body", "A:/B", "A:/B", "gone"] in links  # 认错了的：查过不在，不像链接
    assert ["q", "C:\\work", "C:\\work", "dir"] in links and ["opt", "C:\\work\\report.md", "C:\\work\\report.md", "file"] in links
    assert page.locator("#body pre .path-link").count() == 0  # 代码块里不动
    assert page.locator('#body a[href="https://example.com/c/d"]').count() == 1
    assert "下面" in page.locator("#body").inner_text()

    def act(sel, **kw):
        with page.expect_response(lambda r: r.url.endswith("/api/action") and r.request.post_data_json.get("action") == "open_path"):
            page.click(sel, **kw)

    act('#body .path-link[data-path="C:\\\\work\\\\report.md"]')
    act('#body .path-link[data-path="D:\\\\proj\\\\data"]', modifiers=["Control"])  # Ctrl + 点：所在文件夹
    act('#body .path-link[data-path="C:\\\\work\\\\a b.md"]', button="middle")
    act('#body .path-link[data-path="C:\\\\work\\\\setup.exe"]')  # 会运行的：只选中
    page.wait_for_selector(".toast:has-text('已在文件夹里选中')")
    act('.opt .desc .path-link')  # 选项说明里的路径：只打开，不选这一项
    assert page.locator(".opt.checked").count() == 0
    assert calls == [("open", "C:\\work\\report.md"), ("reveal", "D:\\proj\\data"), ("reveal", "C:\\work\\a b.md"),
                     ("reveal", "C:\\work\\setup.exe"), ("open", "C:\\work\\report.md")]

    act('#body .path-link[data-st="gone"]')  # 不在的点了：说找不到
    page.wait_for_selector(".toast:has-text('找不到')")
    assert len(calls) == 5
    assert errors == []


def test_path_right_click_menu(env):
    d, store, server, page, errors = env
    calls = app_mode(server)
    a = post(d, kind="answer", title="菜单", body="见 C:\\work\\report.md")
    store.poll()
    open_msg(page, server, a)
    page.wait_for_selector('#body .path-link[data-st="file"]')
    page.click("#body .path-link", button="right")
    page.wait_for_selector('#popover:not([hidden]) [data-ctx="open_dir"]')
    assert page.locator('#popover [data-ctx="open_file"]').count() == 1
    page.click('#popover [data-ctx="open_dir"]')
    page.wait_for_function("() => document.querySelector('#popover').hidden")
    page.click("#body .path-link", button="right")
    page.click('#popover [data-ctx="copy_path"]')
    page.wait_for_function("async () => (await navigator.clipboard.readText()) === 'C:\\\\work\\\\report.md'")
    assert calls == [("reveal", "C:\\work\\report.md")]
    assert errors == []


def test_follow_ups_and_answers_link_paths(env):
    d, store, server, page, errors = env
    calls = app_mode(server)
    a = post(d, kind="answer", title="回答", body="正文")
    store.poll()
    store.add_followup(a, "C:\\work\\report.md 是最新的吗？")
    b = post(d, kind="answer", title="追问的回答", body="是的，另存在 C:/work/a b.md 之前的版本没了。", reply_to=a)
    store.poll()
    open_msg(page, server, a)
    page.wait_for_selector('.fu-q .path-link[data-st="file"]')
    page.wait_for_selector('.fu-ans .path-link[data-st]')
    assert page.locator('.fu-ans .path-link[data-path="C:/work/a b.md"]').count() == 1  # 有空格、没引号：接上了
    with page.expect_response(lambda r: r.url.endswith("/api/action") and r.request.post_data_json.get("action") == "open_path"):
        page.click(".fu-q .path-link")
    assert calls == [("open", "C:\\work\\report.md")] and b
    assert errors == []


def test_browser_copies_the_path(env):
    """浏览器、手机打不开电脑上的文件：点了复制路径。"""
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="浏览器", body="见 C:\\work\\report.md")
    store.poll()
    open_msg(page, server, a)
    page.wait_for_selector('#body .path-link[data-st="copy"]')
    page.click("#body .path-link")
    page.wait_for_selector(".toast:has-text('已复制路径')")
    assert page.evaluate("navigator.clipboard.readText()") == "C:\\work\\report.md"
    assert errors == []
