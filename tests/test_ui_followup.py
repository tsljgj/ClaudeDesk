"""追问卡片（真浏览器）：发送和发送中、在线 / 没在听 / 正在回答、复制、两边的链接、草稿、键盘，以及和真的 wait --followups 进程端到端。"""
import datetime as dt
import json
import subprocess
import sys
import threading
from pathlib import Path

import claudedesk.store as store_mod
import desk
import pytest
from test_ui import env, post  # noqa: F401  （env 是 fixture）

ROOT = Path(__file__).resolve().parents[1]
STATE = "() => document.getElementById('fuState').textContent"
ONLINE, ANSWERING = "会话在线，发出后它会接着回答。", "会话收到了你的追问，正在回答。"
OFFLINE = "这个会话现在没在听（可能已经结束了）。追问会存在这里；也可以复制下来，直接粘到 Claude 对话里。"


@pytest.fixture(autouse=True)
def fast_listening(monkeypatch):
    monkeypatch.setattr(store_mod, "LISTEN_EVERY", 0.1)  # 测试里不用等 2 秒才看出会话上下线


def wait_state(page, text):
    page.wait_for_function(f"() => ({STATE})() === {json.dumps(text)}")


def row2(page, mid):
    return page.inner_text(f'.item[data-id="{mid}"] .row2')


def test_send_in_flight_history_copy_and_list_status(env):
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="为什么慢", question="为什么这么慢？", body="因为 IO。")
    q = post(d, kind="decision", title="选哪个？", options=["甲", "乙"])
    i = post(d, kind="info", title="一条通知", body="x")
    store.poll()
    gate, orig = threading.Event(), server.action

    def slow(body):
        if body.get("action") == "followup":
            gate.wait(10)
        return orig(body)

    server.action = slow
    page.goto(server.url)
    for mid, title, shown in ((q, "选哪个？", False), (i, "一条通知", True)):  # 还没回复的决定没有追问卡片；通知有
        page.click(f'.item[data-id="{mid}"]')
        page.wait_for_function(f"() => document.getElementById('title').textContent === {json.dumps(title)}")
        assert page.is_visible("#followup") is shown
    page.click(f'.item[data-id="{a}"]')
    page.wait_for_selector("#followup:not([hidden])")
    assert page.inner_text("#fuState") == OFFLINE and page.get_attribute("#fuState", "class") == "fu-state off"
    assert page.get_attribute("#fuText", "placeholder") == "追问 Claude…（Ctrl+Enter 发送）"
    assert page.is_disabled("#fuSend") and page.is_hidden("#fuCopy") and page.is_hidden("#fuList")

    page.click("#fuText")
    page.keyboard.type("那换成 SSD 呢？")
    assert page.is_enabled("#fuSend") and page.inner_text("#fuHint") == "Ctrl+Enter 发送"
    page.keyboard.press("Control+Enter")
    page.wait_for_function("() => document.getElementById('fuSend').textContent === '发送中…'")
    st = page.evaluate("""() => ({ busy: document.getElementById('followup').getAttribute('aria-busy'),
        btn: document.getElementById('fuSend').disabled, ro: document.getElementById('fuText').readOnly,
        hint: document.getElementById('fuHint').textContent })""")
    assert st == {"busy": "true", "btn": True, "ro": True, "hint": "正在发送…"}
    gate.set()
    page.wait_for_selector("#fuList .fu-item")
    assert page.input_value("#fuText") == "" and page.inner_text("#fuSend") == "发送" and page.is_disabled("#fuSend")
    item = page.inner_text("#fuList .fu-item")
    assert "你的追问" in item and "那换成 SSD 呢？" in item and "等待回答…" in item and "已送到会话" not in item
    recs, _ = desk.read_followups(d)
    assert [(r["msg"], r["text"], r["source"], r["title"]) for r in recs] == [(a, "那换成 SSD 呢？", "proj", "为什么慢")]

    # 会话没在听：可以复制追问（带上原回答的标题、原问题和 id），粘到对话里
    page.wait_for_selector("#fuCopy:not([hidden])")
    page.click("#fuCopy")
    page.wait_for_selector(".toast", state="attached")
    clip = page.evaluate("navigator.clipboard.readText()")
    assert "「为什么慢」" in clip and "为什么这么慢？" in clip and "那换成 SSD 呢？" in clip and a in clip

    # 列表：这条回答写"已追问 · 等回答"
    page.wait_for_function(f"() => document.querySelector('.item[data-id=\"{a}\"] .row2').textContent.includes('已追问 · 等回答')")
    assert "已追问" not in row2(page, q)

    # 两小时前就交给了会话、一直没回应（会话多半没了）：不说"正在回答"，照样能复制
    old = (dt.datetime.now().astimezone() - dt.timedelta(hours=2)).isoformat(timespec="milliseconds")
    desk.append_jsonl(d / desk.FOLLOWUPS, {"delivered": recs[0]["id"], "ts": old})
    page.wait_for_function("() => document.querySelector('#fuList .fu-wait').textContent === '等待回答… · 已送到会话'")
    assert page.inner_text("#fuState") == OFFLINE and page.is_visible("#fuCopy")
    assert errors == []


def test_online_delivered_answering_and_links_both_ways(env):
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="原来的回答", question="原问题", body="正文")
    store.poll()
    page.goto(server.url)
    page.click(f'.item[data-id="{a}"]')
    page.wait_for_selector("#followup:not([hidden])")
    with desk.hold_listener("proj", d):  # 会话挂着 wait --followups
        wait_state(page, ONLINE)
        assert page.get_attribute("#fuState", "class") == "fu-state on"
        page.fill("#fuText", "再展开一点？")
        page.click("#fuSend")
        page.wait_for_selector("#fuList .fu-item")
        assert page.is_hidden("#fuCopy")  # 在线：不用复制
        fid = desk.read_followups(d)[0][0]["id"]
        desk.append_jsonl(d / desk.FOLLOWUPS, {"delivered": fid, "ts": desk.now_ts()})  # 会话领走了
        page.wait_for_function("() => document.querySelector('#fuList .fu-wait').textContent === '等待回答… · 已送到会话'")
    # 领走以后它就退出了（答完再挂上）：这时不能说"没在听"
    wait_state(page, ANSWERING)
    assert page.is_hidden("#fuCopy")

    rep = desk.post_message(desk.make_message("answer", "proj", "展开说说", "细节……", question="再展开一点？", reply_to=a), d)
    link = page.locator(f'#fuList .fu-a[data-open="{rep}"]')
    link.wait_for()
    assert link.inner_text() == "Claude 的回答：展开说说 →"
    wait_state(page, OFFLINE)  # 回应到了，会话也没在听
    page.wait_for_function(f"() => !document.querySelector('.item[data-id=\"{a}\"] .row2').textContent.includes('已追问')")
    assert "回应追问" in row2(page, rep)

    link.click()  # 打开回应：顶上写"回应你的追问"，点"原回答"回去
    page.wait_for_function("() => document.getElementById('title').textContent === '展开说说'")
    ref = page.inner_text("#threadRef")
    assert "回应你的追问" in ref and "原回答：原来的回答" in ref
    assert "「" not in ref and page.inner_text("#questionText") == "再展开一点？"  # 追问原文在引用块里，顶上不重复
    assert page.is_visible("#followup")  # 回应也是回答：可以接着追问
    page.click(f'#threadRef [data-open="{a}"]')
    page.wait_for_function("() => document.getElementById('title').textContent === '原来的回答'")
    assert page.is_hidden("#threadRef")

    # 会话没带 --question：顶上写出追问原文
    store.add_followup(a, "还有呢？")
    rep2 = desk.post_message(desk.make_message("answer", "proj", "还有一点", "x", reply_to=a), d)
    page.locator(f'#fuList .fu-a[data-open="{rep2}"]').click()
    page.wait_for_function("() => document.getElementById('title').textContent === '还有一点'")
    assert "回应你的追问：「还有呢？」" in page.inner_text("#threadRef")
    assert errors == []


def test_follow_up_on_answered_and_resolved_decisions(env):
    """回复过的决定也能追问：卡片在"你的回复"下面出现；标为已处理的同样能追问。"""
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="回答 A", body="a")
    q = post(d, kind="decision", title="先复核还是直接冻结？", options=["先复核", "直接冻结"], allow_text=True)
    r = post(d, kind="decision", title="清理旧环境？", options=["全删", "留 base"])
    store.poll()
    page.goto(server.url)
    page.click(f'.item[data-id="{a}"]')
    page.wait_for_selector("#followup:not([hidden])")
    page.fill("#fuText", "A 的草稿")  # 别的消息的草稿不能带进刚回复的决定里
    page.click(f'.item[data-id="{q}"]')
    page.wait_for_function("() => document.getElementById('title').textContent === '先复核还是直接冻结？'")
    assert page.is_hidden("#followup")  # 还在等回复：只有回复框
    page.click('#options .opt[data-idx="0"]')
    page.keyboard.press("Control+Enter")  # 提交决定（不是发追问）
    page.wait_for_selector("#doneBox:not([hidden])")
    page.wait_for_selector("#followup:not([hidden])")
    assert store.responses[q]["choice"] == "先复核" and not desk.read_followups(d)[0]
    assert page.evaluate("document.getElementById('followup').getBoundingClientRect().top >= "
                         "document.getElementById('doneBox').getBoundingClientRect().bottom")  # 在"你的回复"下面
    assert page.input_value("#fuText") == ""
    page.fill("#fuText", "复核要多久？")
    page.keyboard.press("Control+Enter")  # 回复过了：Ctrl+Enter 发追问
    page.wait_for_selector("#fuList .fu-item")
    assert [(f["msg"], f["text"]) for f in desk.read_followups(d)[0]] == [(q, "复核要多久？")]
    page.wait_for_function(f"() => document.querySelector('.item[data-id=\"{q}\"] .row2').textContent.includes('已追问 · 等回答')")
    assert "✓ 先复核" in row2(page, q)

    store.resolve([r])  # 标为已处理的也能追问
    page.click(f'.item[data-id="{r}"]')
    page.wait_for_function("() => document.getElementById('title').textContent === '清理旧环境？'")
    page.wait_for_selector("#followup:not([hidden])")
    assert "已标为已处理" in page.inner_text("#doneBox")
    page.fill("#fuText", "你那边也清了吗？")
    page.click("#fuSend")
    page.wait_for_selector("#fuList .fu-item")
    page.wait_for_selector("#fuCopy:not([hidden])")
    page.click("#fuCopy")
    page.wait_for_function("() => [...document.querySelectorAll('.toast')].some(t => t.textContent.includes('已复制追问'))")
    clip = page.evaluate("navigator.clipboard.readText()")
    assert "决定「清理旧环境？」" in clip and "我当时的回复：标为已处理" in clip and r in clip
    rep = desk.post_message(desk.make_message("answer", "proj", "清了", "x", question="你那边也清了吗？", reply_to=r), d)
    page.locator(f'#fuList .fu-a[data-open="{rep}"]').click()
    page.wait_for_function("() => document.getElementById('title').textContent === '清了'")
    assert "原决定：清理旧环境？" in page.inner_text("#threadRef")
    assert page.evaluate("deskTest.S.drafts").get(a, {}).get("text") == "A 的草稿"
    assert errors == []


def test_drafts_keyboard_and_esc(env):
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="回答 A", body="a")
    b = post(d, kind="answer", title="回答 B", body="b")
    c = post(d, kind="decision", title="决定 C", options=["甲", "乙"])
    store.poll()
    page.goto(server.url)
    page.click(f'.item[data-id="{a}"]')
    page.wait_for_selector("#followup:not([hidden])")
    page.focus("#list")
    page.keyboard.press("Enter")  # 回答上按 Enter：去写追问
    page.wait_for_function("document.activeElement.id === 'fuText'")
    page.keyboard.type("草稿一 ejku")  # 单键快捷键在输入框里不生效
    assert page.evaluate("deskTest.S.current") == a and not page.evaluate(f"deskTest.S.byId['{a}'].archived")
    page.keyboard.press("Escape")  # 输入框里的 Esc 不退出阅读、不丢字
    assert page.evaluate("deskTest.S.current") == a and page.input_value("#fuText") == "草稿一 ejku"

    page.click(f'.item[data-id="{b}"]')
    page.wait_for_function("() => document.getElementById('title').textContent === '回答 B'")
    assert page.input_value("#fuText") == ""
    page.fill("#fuText", "草稿二")
    page.click(f'.item[data-id="{c}"]')
    page.wait_for_function("() => document.getElementById('title').textContent === '决定 C'")
    assert page.is_hidden("#followup")
    page.click(f'.item[data-id="{a}"]')
    page.wait_for_function("() => document.getElementById('title').textContent === '回答 A'")
    assert page.input_value("#fuText") == "草稿一 ejku"  # 每条各记各的草稿
    page.click(f'.item[data-id="{b}"]')
    page.wait_for_function("() => document.getElementById('fuText').value === '草稿二'")

    # Ctrl+Enter：决定照样提交决定
    page.click(f'.item[data-id="{c}"]')
    page.wait_for_function("() => document.getElementById('title').textContent === '决定 C'")
    page.click('#options .opt[data-idx="0"]')
    page.keyboard.press("Control+Enter")
    page.wait_for_selector("#doneBox:not([hidden])")
    assert store.responses[c]["choice"] == "甲" and not desk.read_followups(d)[0]

    # 回答：焦点不在输入框也能 Ctrl+Enter 发出草稿；草稿空着时只把光标放进追问框
    page.click(f'.item[data-id="{a}"]')
    page.wait_for_function("() => document.getElementById('fuText').value === '草稿一 ejku'")
    page.focus("#list")
    page.keyboard.press("Control+Enter")
    page.wait_for_selector("#fuList .fu-item")
    assert [f["text"] for f in desk.read_followups(d)[0]] == ["草稿一 ejku"]
    page.focus("#list")
    page.keyboard.press("Control+Enter")
    page.wait_for_function("document.activeElement.id === 'fuText'")
    assert len(desk.read_followups(d)[0]) == 1
    assert page.evaluate(f"deskTest.S.drafts['{a}']") is None and page.evaluate(f"deskTest.S.drafts['{b}'].text") == "草稿二"

    # 窄窗口：输入框里 Esc 不退；离开输入框再按 Esc 回到列表
    page.set_viewport_size({"width": 600, "height": 800})
    page.focus("#fuText")
    page.keyboard.type("x")
    page.keyboard.press("Escape")
    assert page.evaluate("deskTest.S.current") == a
    page.evaluate("document.activeElement.blur()")
    page.keyboard.press("Escape")
    page.wait_for_function("() => deskTest.S.current === null")
    assert errors == []


def test_end_to_end_with_a_real_listener(env):
    """真的 desk.py wait --followups 进程 + 界面发追问 + desk.py post --reply-to 回应。"""
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="端到端的回答", question="原问题？", body="正文", source="e2e")
    store.poll()
    page.goto(server.url)
    page.click(f'.item[data-id="{a}"]')
    page.wait_for_selector("#followup:not([hidden])")
    wait_state(page, OFFLINE)
    p = subprocess.Popen([sys.executable, str(ROOT / "desk.py"), "--data", str(d), "wait", "--followups", "--source", "e2e",
                          "--timeout", "60", "--interval", "0.2"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
    try:
        wait_state(page, ONLINE)
        page.fill("#fuText", "端到端：再说一遍？")
        page.keyboard.press("Control+Enter")
        out, err = p.communicate(timeout=20)
        assert p.returncode == 0, err
        got = json.loads(out)
        assert (got["msg"], got["title"], got["question"], got["text"]) == (a, "端到端的回答", "原问题？", "端到端：再说一遍？")
        wait_state(page, ANSWERING)
        r = subprocess.run([sys.executable, str(ROOT / "desk.py"), "--data", str(d), "post", "--kind", "answer", "--source", "e2e",
                            "--title", "再说一遍", "--body", "好的……", "--reply-to", got["msg"], "--question", got["text"],
                            "--no-launch", "--repo", "x"], capture_output=True, encoding="utf-8", timeout=20)
        assert r.returncode == 0, r.stderr
        page.locator("#fuList .fu-a", has_text="Claude 的回答：再说一遍 →").wait_for()
        wait_state(page, OFFLINE)
    finally:
        p.kill()
    assert errors == []
