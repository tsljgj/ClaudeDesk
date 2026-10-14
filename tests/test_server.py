"""本机 HTTP 服务：静态资源、出错处理、回复接口。不用浏览器。"""
import http.client
import json
import os
import pathlib
import socket
import struct
import time

import desk
import pytest
from claudedesk.server import TOKEN_HEADER, DeskServer
from claudedesk.store import Store


@pytest.fixture()
def srv(tmp_path):
    store = Store(tmp_path)
    store.poll()
    server = DeskServer(store).start_background()
    yield tmp_path, store, server
    server.shutdown()


def call(server, method, path, body=None, token=True):
    c = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
    headers = {"Host": f"127.0.0.1:{server.port}"}  # 跨站请求带的也是这个 Host
    if token:
        headers[TOKEN_HEADER] = server.token
    if body is not None:
        body = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    c.request(method, path, body=body, headers=headers)
    r = c.getresponse()
    data = r.read()
    c.close()
    return r.status, data


def raw(server, text: str, rst: bool = False) -> bytes:
    s = socket.create_connection(("127.0.0.1", server.port), timeout=10)
    s.sendall(text.encode("utf-8"))
    if rst:  # 像浏览器放弃请求那样直接 RST
        s.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        s.close()
        return b""
    out = b""
    try:
        while chunk := s.recv(65536):
            out += chunk
    except socket.timeout:
        pass
    s.close()
    return out


def test_assets_never_touch_the_filesystem_with_request_paths(srv, monkeypatch):
    _, _, server = srv
    assert call(server, "GET", "/assets/app.js", token=False)[0] == 200
    st, data = call(server, "GET", "/assets/vendor/katex/katex.min.css", token=False)
    assert st == 200 and len(data) > 100
    touched = []

    def spy(name, real):
        def f(p, *a, **k):
            if "127.0.0.1" in str(p) or "win.ini" in str(p).lower():
                touched.append((name, str(p)))
            return real(p, *a, **k)
        return f

    for name in ("resolve", "is_file", "exists", "stat", "read_bytes"):
        monkeypatch.setattr(pathlib.Path, name, spy(name, getattr(pathlib.Path, name)))
    monkeypatch.setattr(os, "stat", spy("os.stat", os.stat))
    monkeypatch.setattr(os.path, "realpath", spy("realpath", os.path.realpath))
    for evil in ("/assets/%5C%5C127.0.0.1%5CC$%5CWindows%5Cwin.ini",  # UNC：Windows 会去连那台机器的 SMB
                 "/assets///127.0.0.1/C$/Windows/win.ini",
                 "/assets/C:%5CWindows%5Cwin.ini", "/assets/../server.py", "/assets/%2e%2e/server.py",
                 "/assets/vendor/../app.js", "/assets/"):
        assert call(server, "GET", evil, token=False)[0] == 404, evil
    assert touched == []


def test_aborted_long_poll_is_silent(srv, capsys):
    _, store, server = srv
    raw(server, f"GET /api/state?since={store.version}&wait=1 HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                f"{TOKEN_HEADER}: {server.token}\r\n\r\n", rst=True)
    time.sleep(1.6)  # 长轮询醒来写回复时才发现连接没了
    assert capsys.readouterr().err == ""


def test_handler_errors_are_logged_and_answered(srv, caplog):
    _, _, server = srv
    server.extra_actions["boom"] = lambda body: 1 / 0
    with caplog.at_level("ERROR", logger="claudedesk"):
        st, data = call(server, "POST", "/api/action", {"action": "boom"})
    assert st == 500 and json.loads(data) == {"ok": False, "error": "ZeroDivisionError",
                                               "message": "ZeroDivisionError: division by zero"}
    assert any(r.name == "claudedesk" and r.exc_info and r.exc_info[0] is ZeroDivisionError for r in caplog.records)
    st, data = call(server, "GET", "/api/state?since=abc&wait=nan")  # 参数写错按默认值
    assert st == 200 and "messages" in json.loads(data)
    out = raw(server, f"POST /api/action HTTP/1.1\r\nHost: 127.0.0.1\r\n{TOKEN_HEADER}: {server.token}\r\n"
                      "Content-Length: -5\r\n\r\n")
    assert out.startswith(b"HTTP/1.1 400")


def test_reply_with_choice_index(srv):
    d, store, server = srv
    a = desk.post_message(desk.make_message("decision", "p", "q", options=["继续::按方案 A", "继续::按方案 B"]), d)
    b = desk.post_message(desk.make_message("decision", "p", "q", options=["继续::按方案 A", "继续::按方案 B"]), d)
    store.poll()

    def reply(**kw):
        return json.loads(call(server, "POST", "/api/action", {"action": "reply", "text": "", **kw})[1])

    r = reply(id=a, choice="停", choice_index=2)
    assert r["ok"] is False and "对不上" in r["message"]
    r = reply(id=a, choice="继续", choice_index=2)
    assert r["ok"] is True and r["result"]["choice_index"] == 2
    assert reply(id=b, choice="继续")["result"]["choice_index"] == 1  # 旧界面：只有名字
    got = {x["id"]: (x["choice"], x["choice_index"]) for x in desk.read_all(d / desk.RESPONSES)}
    assert got == {a: ("继续", 2), b: ("继续", 1)}


def test_hide_and_show_project_actions(srv):
    d, store, server = srv
    a = desk.post_message(desk.make_message("decision", "s", "甲", repo="alpha", options=["A"]), d)
    b = desk.post_message(desk.make_message("answer", "s", "乙", repo="beta"), d)
    store.poll()

    def act(**kw):
        return json.loads(call(server, "POST", "/api/action", kw)[1])

    def state():
        return json.loads(call(server, "GET", "/api/state")[1])

    assert state()["hidden_projects"] == []
    assert act(action="hide_project", key="alpha") == {"ok": True, "result": ["alpha"]}
    st = state()
    assert st["hidden_projects"] == ["alpha"] and st["counts"]["open"] == 0 and st["counts"]["unread"] == 1
    # 消息照样给界面："已关闭"菜单要数条数，搜索要能说"另有 N 条在已关闭的标签里"，点旧通知要能找回
    assert {m["id"] for m in st["messages"]} == {a, b}
    assert act(action="hide_project", key="beta")["result"] == ["alpha", "beta"]
    assert state()["counts"]["unread"] == 0
    assert act(action="show_project", key="alpha")["result"] == ["beta"]
    assert act(action="show_project", all=True)["result"] == []
    assert state()["counts"]["unread"] == 2
    for bad in ({"action": "hide_project"}, {"action": "show_project", "key": " "}):
        r = act(**bad)
        assert r["ok"] is False and r["message"] == "缺少项目名"
