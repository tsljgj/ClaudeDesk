"""会话状态（真浏览器）：决定卡片、追问卡片的状态行（在等 / 开着没在听 / 已结束 / 旧消息），回复和追问送达了没有，
列表里"会话已结束"的标记，以及和真的 desk.py listen 进程端到端。"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import claudedesk.store as store_mod
import desk
import pytest
from test_ui import env  # noqa: F401  （env 是 fixture）

ROOT = Path(__file__).resolve().parents[1]
LISTENING = "会话在等，提交后马上收到。"
OPEN = "会话还开着，但现在没在听：回复会存着，它下次查看时收到。"
GONE = "这个会话已经结束：回复会存着；在同一个仓库开新会话时，可以用 desk.py inbox 找回。"
FU_LISTENING = "会话在等，发出后马上收到。"
FU_OPEN = "会话还开着，但现在没在听：追问会存着，它下次查看时收到。"
FU_GONE = "这个会话已经结束：追问会存着；在同一个仓库开新会话时，可以用 desk.py inbox 找回，也可以复制下来粘到对话里。"


@pytest.fixture(autouse=True)
def fast_presence(monkeypatch):
    monkeypatch.setattr(store_mod, "LISTEN_EVERY", 0.1)  # 测试里不用等 2 秒才看出会话上下线


def dead_pid():
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def post(d, session=None, pid=None, **kw):
    kw.setdefault("source", "proj")
    return desk.post_message(desk.make_message(session=session, session_pid=pid, **kw), d)


def show(page, mid, title):
    page.click(f'.item[data-id="{mid}"]')
    page.wait_for_function(f"() => document.getElementById('title').textContent === {json.dumps(title)}")


def wait_text(page, sel, text):
    page.wait_for_function(f"() => document.querySelector({json.dumps(sel)}).textContent === {json.dumps(text)}")


def row2(page, mid):
    return page.inner_text(f'.item[data-id="{mid}"] .row2')


def test_decision_card_states_live_changes_and_list_tag(env):
    d, store, server, page, errors = env
    me = os.getpid()
    lis = post(d, "L", me, kind="decision", title="在等的", options=["甲", "乙"])
    opn = post(d, "O", me, kind="decision", title="开着的", options=["甲", "乙"])
    gone = post(d, "G", dead_pid(), kind="decision", title="结束了的", options=["甲", "乙"])
    legacy = post(d, kind="decision", title="旧消息", options=["甲", "乙"])
    store.poll()
    with desk.hold_marker(desk.session_marker("L", d), d, exclusive=True):
        page.goto(server.url)
        show(page, lis, "在等的")
        wait_text(page, "#decideState", LISTENING)
        assert page.get_attribute("#decideState", "class") == "decide-state sess on"
        show(page, opn, "开着的")
        wait_text(page, "#decideState", OPEN)
        assert page.get_attribute("#decideState", "class") == "decide-state sess"
        show(page, gone, "结束了的")
        wait_text(page, "#decideState", GONE)
        assert page.evaluate("document.getElementById('decide').classList.contains('gone')")
        assert page.inner_text("#decideHint") == "会话已经结束 · 不需要了就标为已处理（R）"
        page.click('#options .opt[data-idx="1"]')  # 选了就照常提示
        assert page.inner_text("#decideHint") == "Ctrl+Enter 提交「乙」"
        show(page, legacy, "旧消息")
        assert re.fullmatch(r"会话已等 .+ · 提交后立即继续", page.inner_text("#decideState"))  # 旧消息照旧
        assert page.get_attribute("#decideState", "class") == "decide-state"
        assert not page.evaluate("document.getElementById('decide').classList.contains('gone')")
        # 列表：只有会话已结束的待决定带标记
        assert "会话已结束" in row2(page, gone)
        assert all("会话已结束" not in row2(page, i) for i in (lis, opn, legacy))
        show(page, opn, "开着的")
        with desk.hold_marker(desk.session_marker("O", d), d, exclusive=True):  # 会话挂上 listen：不用重开就变
            wait_text(page, "#decideState", LISTENING)
        wait_text(page, "#decideState", OPEN)
    # 会话已结束的：标为已处理最自然；完成框说不用再通知它
    show(page, gone, "结束了的")
    page.focus("#list")
    page.keyboard.press("r")
    page.wait_for_selector("#doneBox:not([hidden])")
    assert "已标为已处理" in page.inner_text("#doneBox") and "会话已经结束，不用再通知它" in page.inner_text("#doneBox")
    page.wait_for_function(f"() => !document.querySelector('.item[data-id=\"{gone}\"] .row2').textContent.includes('会话已结束')")
    assert errors == []


def test_reply_delivery_lines(env):
    d, store, server, page, errors = env
    me = os.getpid()
    opn = post(d, "O", me, kind="decision", title="开着的", options=["甲", "乙"])
    gone = post(d, "G", dead_pid(), kind="decision", title="结束了的", options=["甲"])
    legacy = post(d, kind="decision", title="旧消息", options=["甲"])
    store.poll()
    page.goto(server.url)
    show(page, opn, "开着的")
    page.click('#options .opt[data-idx="0"]')
    page.fill("#replyText", "顺便改 README")
    page.keyboard.press("Control+Enter")
    page.wait_for_selector("#doneBox:not([hidden])")
    done = page.inner_text("#doneBox")
    assert re.match(r"已提交 · 今天 \d\d:\d\d · 还没送达\n会话下次查看时收到。\n顺便改 README", done), done
    assert page.inner_text("#decideState") == ""
    desk.mark_delivered(d, "reply", opn, "O", "listen")  # listen 交给了会话
    page.wait_for_function("() => document.getElementById('doneBox').textContent.includes('已送达会话 · ')")
    assert re.match(r"已提交 · 今天 \d\d:\d\d · 已送达会话 · \d\d:\d\d\n顺便改 README", page.inner_text("#doneBox"))
    store.submit(gone, "甲", "")
    show(page, gone, "结束了的")
    page.wait_for_selector("#doneBox:not([hidden])")
    assert "还没送达\n会话已经结束：在同一个仓库开新会话时，可以用 desk.py inbox 找回。" in page.inner_text("#doneBox")
    store.submit(legacy, "甲", "")
    show(page, legacy, "旧消息")
    page.wait_for_selector("#doneBox:not([hidden])")
    assert re.match(r"已提交 · 今天 \d\d:\d\d · 会话已收到$", page.inner_text("#doneBox").split("\n")[0])  # 旧消息照旧
    assert errors == []


def test_followup_card_states_and_delivery(env):
    d, store, server, page, errors = env
    me = os.getpid()
    a_open = post(d, "O", me, kind="answer", title="开着的回答", body="x")
    a_gone = post(d, "G", dead_pid(), kind="answer", title="结束了的回答", body="x")
    store.poll()
    page.goto(server.url)
    show(page, a_gone, "结束了的回答")
    page.wait_for_selector("#followup:not([hidden])")
    wait_text(page, "#fuState", FU_GONE)
    page.fill("#fuText", "那换成 SSD 呢？")
    page.click("#fuSend")
    page.wait_for_selector("#fuList .fu-item")
    assert page.inner_text("#fuList .fu-wait") == "等待回答… · 还没送达 · 会话已经结束"
    page.wait_for_selector("#fuCopy:not([hidden])")  # 会话结束了：可以复制到对话里

    show(page, a_open, "开着的回答")
    wait_text(page, "#fuState", FU_OPEN)
    page.fill("#fuText", "再展开一点？")
    page.click("#fuSend")
    page.wait_for_selector("#fuList .fu-item")
    assert page.inner_text("#fuList .fu-wait") == "等待回答… · 还没送达 · 会话下次查看时收到"
    with desk.hold_marker(desk.session_marker("O", d), d, exclusive=True):
        wait_text(page, "#fuState", FU_LISTENING)
        wait_text(page, "#fuList .fu-wait", "等待回答… · 还没送达 · 会话在等，马上就到")  # 送达前那几秒
        assert page.is_hidden("#fuCopy")
        fid = desk.read_followups(d)[0][-1]["id"]
        desk.mark_delivered(d, "followup", fid, "O", "listen")
        page.wait_for_function("() => /^等待回答… · 已送达会话 · \\d\\d:\\d\\d$/.test(document.querySelector('#fuList .fu-wait').textContent)")
    wait_text(page, "#fuState", "会话收到了你的追问，正在回答。")  # listen 交出去就退出了：这时不说"没在听"
    assert errors == []


def test_end_to_end_with_a_real_listen(env):
    """真的 desk.py listen 进程（会话 = 测试自己这个进程）：界面显示"在等"，提交后 listen 醒来带回回复，界面写"已送达会话"。"""
    d, store, server, page, errors = env
    me = os.getpid()
    mid = post(d, "E2E", me, kind="decision", title="端到端", options=["甲", "乙"])
    store.poll()
    page.goto(server.url)
    show(page, mid, "端到端")
    wait_text(page, "#decideState", OPEN)
    e = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
    e.update(CLAUDE_CODE_SESSION_ID="E2E", CLAUDE_PID=str(me))
    p = subprocess.Popen([sys.executable, str(ROOT / "desk.py"), "--data", str(d), "listen", "--interval", "0.1", "--batch", "0.3"],
                         env=e, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
    try:
        wait_text(page, "#decideState", LISTENING)
        page.click('#options .opt[data-idx="1"]')
        page.keyboard.press("Control+Enter")
        out, err = p.communicate(timeout=20)
    finally:
        p.kill()
    assert p.returncode == 0, err
    assert json.loads(out) == {"ev": "reply", "id": mid, "title": "端到端", "choice": "乙", "choice_index": 2}
    page.wait_for_function("() => document.getElementById('doneBox').textContent.includes('已送达会话 · ')")
    t0 = time.monotonic()
    while "会话" in page.inner_text("#decideState") and time.monotonic() - t0 < 5:
        time.sleep(0.1)
    assert page.inner_text("#decideState") == ""
    assert errors == []
