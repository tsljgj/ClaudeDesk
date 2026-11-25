"""手机访问：另开的端口只认钥匙（链接 → cookie）、只放行看消息和回复的操作、换钥匙就失效；手机推送（ntfy）的内容和时机。
不用浏览器，也不真的往外发推送。"""
import http.client
import json
import socket
import threading
import time

import desk
import pytest
from claudedesk import remote as rm
from claudedesk.server import REMOTE_COOKIE, TOKEN_HEADER, DeskServer
from claudedesk.store import Store


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(rm, "addresses", lambda: [{"host": "pc.tailnet.ts.net", "kind": "tailscale"},
                                                  {"host": "192.168.1.20", "kind": "lan"}])
    store = Store(tmp_path)
    store.poll()
    server = DeskServer(store).start_background()
    sent = []
    r = rm.Remote(store, server, idle=lambda: None, post=lambda srv, body: sent.append((srv, body)))
    server.extra_actions["remote"] = r.action
    store.state["remote"] = {"port": free_port()}
    yield tmp_path, store, server, r, sent
    server.shutdown()


def req(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    h = {"Host": "pc.tailnet.ts.net:1234", **(headers or {})}
    if body is not None:
        body = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"
    c.request(method, path, body=body, headers=h)
    r = c.getresponse()
    data = r.read()
    c.close()
    return r.status, dict(r.getheaders()), data


def test_off_by_default_and_turning_on_opens_a_port(env):
    d, store, server, r, sent = env
    assert r.start() is False and server.remote_port is None
    assert server.meta["remote"] == {"on": False, "running": False, "push": False, "error": ""}
    st = r.action({"op": "enable", "on": True})
    assert st["on"] and st["running"] and server.remote_port == store.state["remote"]["port"]
    key = store.state["remote"]["key"]
    assert len(key) >= 24
    assert [x["url"] for x in st["links"]] == [f"http://pc.tailnet.ts.net:{server.remote_port}/?k={key}",
                                               f"http://192.168.1.20:{server.remote_port}/?k={key}"]
    assert st["tailscale"] and all(x["qr"].startswith("<svg") for x in st["links"])
    assert json.loads((d / "state.json").read_text(encoding="utf-8"))["remote"]["key"] == key  # 马上落盘
    r.action({"op": "enable", "on": False})
    assert server.remote_port is None
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", store.state["remote"]["port"]), timeout=2).close()


def test_link_becomes_a_cookie_and_only_safe_actions_pass(env):
    d, store, server, r, sent = env
    mid = desk.post_message(desk.make_message("decision", "webapp", "要合并吗？", "正文", options=["合并::", "等等::"]), d)
    store.poll()
    r.action({"op": "enable", "on": True})
    port, key = server.remote_port, store.state["remote"]["key"]

    code, _, body = req(port, "GET", "/")
    assert code == 401 and "需要 ClaudeDesk 里的链接".encode() in body and key.encode() not in body
    assert req(port, "GET", "/?k=wrong" + key)[0] == 401
    code, h, _ = req(port, "GET", f"/?k={key}")
    assert code == 303 and h["Location"] == "/"
    cookie = h["Set-Cookie"]
    assert cookie.startswith(f"{REMOTE_COOKIE}={key};") and "HttpOnly" in cookie and "SameSite=Lax" in cookie
    code, h, page = req(port, "GET", "/", headers={"Cookie": f"other=1; {REMOTE_COOKIE}={key}"})
    assert code == 200 and h["X-Frame-Options"] == "DENY" and h["Referrer-Policy"] == "no-referrer"
    boot = json.loads(page.decode("utf-8").split("window.BOOT = ", 1)[1].split(";</script>", 1)[0])
    assert boot["token"] == key and boot["remote"] is True and boot["app"] is False
    assert server.token not in page.decode("utf-8")  # 电脑窗口用的 token 不给手机
    assert req(port, "GET", "/assets/app.js")[0] == 200  # 静态资源不含秘密
    assert req(port, "GET", "/manifest.webmanifest")[0] == 200 and req(port, "GET", "/icon-192.png")[0] == 200

    assert req(port, "GET", "/api/state")[0] == 401
    assert req(port, "GET", "/api/state", headers={TOKEN_HEADER: server.token})[0] == 401
    code, _, data = req(port, "GET", "/api/state", headers={TOKEN_HEADER: key})
    snap = json.loads(data)
    assert code == 200 and [m["id"] for m in snap["messages"]] == [mid]
    assert set(snap["meta"]) == {"build", "version"}  # 不给托盘程序的状态（更新、手机访问设置）

    def act(body):
        return json.loads(req(port, "POST", "/api/action", body, headers={TOKEN_HEADER: key})[2])

    for name in ("open_path", "open_url", "quit", "remote", "settings", "install_update", "clipboard_text", "show"):
        assert act({"action": name, "path": "C:/x", "op": "new_key"}) == {"ok": False, "message": "手机上不能做这个操作"}
    assert act({"action": "read", "ids": [mid], "opened": True})["ok"]
    assert act({"action": "reply", "id": mid, "choice": "合并", "choice_index": 1, "text": "手机上回的"})["ok"]
    assert [x["choice"] for x in desk.read_all(d / desk.RESPONSES)] == ["合并"]
    assert store.state["remote"]["key"] == key  # 手机上换不了钥匙
    # 电脑上的端口还是只认自己的 token 和 127.0.0.1
    c = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    c.request("GET", "/api/state", headers={"Host": f"127.0.0.1:{server.port}", TOKEN_HEADER: key})
    assert c.getresponse().status == 401
    c.close()


def test_new_key_locks_out_old_links_and_waiting_phones(env):
    d, store, server, r, sent = env
    r.action({"op": "enable", "on": True})
    port, old = server.remote_port, store.state["remote"]["key"]
    since = store.version
    out = {}

    def waiting():  # 手机在长轮询里等着
        out["res"] = req(port, "GET", f"/api/state?since={since}&wait=20", headers={TOKEN_HEADER: old})

    t = threading.Thread(target=waiting)
    t.start()
    time.sleep(0.3)  # 让它先进去等着（等的是服务端状态，没有可查询的标志）
    r.action({"op": "new_key"})
    t.join(10)
    assert out["res"][0] == 401
    new = store.state["remote"]["key"]
    port = server.remote_port
    assert new != old
    assert req(port, "GET", "/", headers={"Cookie": f"{REMOTE_COOKIE}={old}"})[0] == 401
    assert req(port, "GET", "/api/state", headers={TOKEN_HEADER: old})[0] == 401
    assert req(port, "GET", "/", headers={"Cookie": f"{REMOTE_COOKIE}={new}"})[0] == 200


def test_port_in_use_is_reported_and_port_can_be_changed(env):
    d, store, server, r, sent = env
    busy = socket.socket()
    busy.bind(("0.0.0.0", 0))
    busy.listen(1)
    try:
        store.state["remote"]["port"] = busy.getsockname()[1]
        st = r.action({"op": "enable", "on": True})
        assert st["on"] and not st["running"] and "开不了端口" in st["error"]
        assert server.meta["remote"]["error"] == st["error"]
        with pytest.raises(ValueError):
            r.action({"op": "port", "port": 80})
        p = free_port()
        while p < 1024:
            p = free_port()
        st = r.action({"op": "port", "port": p})
        assert st["running"] and st["error"] == "" and server.remote_port == p
    finally:
        busy.close()


def test_push_content_timing_and_privacy(env):
    d, store, server, r, sent = env
    r.action({"op": "enable", "on": True})
    st = r.action({"op": "push", "on": True})
    topic = st["push"]["topic"]
    assert topic.startswith("claudedesk-") and st["push"]["subscribe"] == f"https://ntfy.sh/{topic}"
    a = desk.post_message(desk.make_message("decision", "webapp", "要合并吗？", "**秘密**正文", repo="webapp",
                                            options=["合并::"], priority="high"), d)
    seen = []
    store.on_arrived.append(lambda msgs: seen.extend(msgs))
    store.on_arrived.append(r.notify)
    store.poll()
    deadline = time.monotonic() + 5
    while not sent and time.monotonic() < deadline:
        time.sleep(0.02)
    srv, body = sent[-1]
    assert srv == "https://ntfy.sh" and body["topic"] == topic
    assert body["title"] == "需要你决定：要合并吗？" and body["message"] == "[webapp] 要合并吗？"  # 默认不带正文
    assert body["priority"] == 5 and body["click"] == f"http://pc.tailnet.ts.net:{server.remote_port}/#m={a}"
    assert store.state["remote"]["key"] not in json.dumps(body)  # 地址不带钥匙
    m = seen[0]
    assert "秘密" in r.payload([m], "full")["message"]
    none = r.payload([m], "none")
    assert "要合并吗" not in json.dumps(none, ensure_ascii=False) and none["message"].startswith("1 条新的待决定")
    two = r.payload([m, dict(m, id="x2", kind="answer", title="回答", priority="normal")], "title")
    assert two["title"] == "2 条新消息（1 条待决定）" and two["click"].endswith(f"#m={a}")

    # 人在电脑前（刚动过鼠标）：不推；离开 5 分钟以上：推
    n = len(sent)
    r.idle = lambda: 12.0
    r.notify([m])
    r.idle = lambda: 400.0
    r.notify([m])
    r.action({"op": "push", "away": False})
    r.idle = lambda: 1.0
    r.notify([m])
    deadline = time.monotonic() + 5
    while len(sent) < n + 2 and time.monotonic() < deadline:
        time.sleep(0.02)
    time.sleep(0.1)
    assert len(sent) == n + 2

    r.action({"op": "push", "on": False})
    r.notify([m])
    time.sleep(0.1)
    assert len(sent) == n + 2


def test_push_test_reports_failures(env):
    d, store, server, r, sent = env
    with pytest.raises(ValueError):
        r.action({"op": "push_test"})  # 还没有主题
    r.action({"op": "push", "on": True})
    r.action({"op": "push_test"})
    assert sent[-1][1]["title"] == "ClaudeDesk 测试推送"

    def boom(srv, body):
        raise OSError("HTTP 429 limit")

    r._post = boom
    with pytest.raises(ValueError, match="429"):
        r.action({"op": "push_test"})
    assert "429" in r.status()["push"]["error"]
    with pytest.raises(ValueError):
        r.action({"op": "push", "server": "ftp://x"})
    assert r.action({"op": "push", "server": "https://ntfy.example.org/"})["push"]["server"] == "https://ntfy.example.org"


def test_addresses_put_tailscale_first():
    got = rm.addresses(ts={"name": "pc.tailnet.ts.net", "ips": ["100.100.1.2"]},
                       ips=["192.168.1.5", "100.100.1.2", "100.64.9.9", "10.0.0.3", "8.8.4.4"])
    assert got == [{"host": "pc.tailnet.ts.net", "kind": "tailscale"}, {"host": "100.100.1.2", "kind": "tailscale"},
                   {"host": "100.64.9.9", "kind": "tailscale"}, {"host": "192.168.1.5", "kind": "lan"},
                   {"host": "10.0.0.3", "kind": "lan"}, {"host": "8.8.4.4", "kind": "other"}]
    assert rm.addresses(ts={}, ips=[]) == []
    assert all(not ip.startswith(("127.", "169.254.")) for ip in rm.local_ips())
