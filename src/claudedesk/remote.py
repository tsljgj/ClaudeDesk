"""手机访问：不在电脑前也能看 ClaudeDesk、回复决定。

做法是把电脑上的收件箱发布成一个网页（server.py 另开一个端口），手机浏览器打开就是同一个界面：
- 同一个 Wi-Fi：用局域网地址；
- 在外面：电脑和手机都装 Tailscale（免费），用 Tailscale 地址，流量是加密的，也不用开路由器端口。
内容一直留在这台电脑上，不经过任何第三方服务器。链接里带一把钥匙，第一次打开后换成 cookie；
换钥匙后旧链接、已经登录的手机都失效。

可选的手机推送：新消息到了往 ntfy（https://ntfy.sh 或自建的）发一条通知，点开就是那条消息。
推送只带标题（可以选连标题都不带），正文不出电脑；点开的地址不带钥匙。
"""
from __future__ import annotations

import ipaddress
import json
import logging
import os
import secrets
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request

from . import __version__, qr, winapi
from .store import Store, plain_summary

log = logging.getLogger("claudedesk")
DEFAULT_PORT = 47821
NTFY_SERVER = "https://ntfy.sh"
AWAY_AFTER = 300  # 离开电脑这么多秒以后才推（电脑前有托盘通知）
DETAILS = ("full", "title", "none")  # 推送带什么：标题和摘要 / 只有标题 / 什么都不带
TAILNET = ipaddress.ip_network("100.64.0.0/10")


def new_key() -> str:
    return secrets.token_urlsafe(24)


def new_topic() -> str:
    return "claudedesk-" + secrets.token_urlsafe(12)


def _tailscale_exe() -> str | None:
    exe = shutil.which("tailscale")
    if exe:
        return exe
    for p in (r"C:\Program Files\Tailscale\tailscale.exe", "/Applications/Tailscale.app/Contents/MacOS/Tailscale"):
        if os.path.exists(p):
            return p
    return None


def tailscale_self(timeout: float = 4.0) -> dict:
    """这台电脑在 Tailscale 里的名字和地址：{"name": "pc.tailnet.ts.net", "ips": [...]}；没装 / 没登录返回 {}。"""
    exe = _tailscale_exe()
    if not exe:
        return {}
    flags = {"creationflags": 0x08000000} if os.name == "nt" else {}  # CREATE_NO_WINDOW
    try:
        r = subprocess.run([exe, "status", "--json"], capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL, **flags)
        st = json.loads(r.stdout.decode("utf-8", "replace") or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        return {}
    me = st.get("Self") if isinstance(st, dict) else None
    if not isinstance(me, dict) or st.get("BackendState") not in (None, "Running"):
        return {}
    ips = [ip for ip in me.get("TailscaleIPs") or [] if isinstance(ip, str) and ":" not in ip]
    name = str(me.get("DNSName") or "").rstrip(".")
    magic = (st.get("CurrentTailnet") or {}).get("MagicDNSEnabled", True) if isinstance(st.get("CurrentTailnet"), dict) else True
    return {"name": name if name and magic else "", "ips": ips}


def local_ips() -> list[str]:
    """这台电脑的 IPv4 地址（不含回环、自动分配的 169.254.x.x）。"""
    ips: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.append(info[4][0])
    except OSError:
        pass
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:  # 往外连一下（UDP 不真的发包）：看默认走哪块网卡
        s.connect(("192.0.2.1", 9))
        ips.append(s.getsockname()[0])
    except OSError:
        pass
    finally:
        s.close()
    out = []
    for ip in ips:
        try:
            a = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if a.is_loopback or a.is_link_local or a.is_unspecified or ip in out:
            continue
        out.append(ip)
    return out


def addresses(ts: dict | None = None, ips: list[str] | None = None) -> list[dict]:
    """手机能用的地址，好用的在前：Tailscale 名字 → Tailscale IP → 局域网 IP → 别的。"""
    ts = tailscale_self() if ts is None else ts
    ips = local_ips() if ips is None else ips
    out = []
    if ts.get("name"):
        out.append({"host": ts["name"], "kind": "tailscale"})
    for ip in ts.get("ips", []) + [ip for ip in ips if ipaddress.ip_address(ip) in TAILNET]:
        if all(x["host"] != ip for x in out):
            out.append({"host": ip, "kind": "tailscale"})
    for ip in ips:
        if all(x["host"] != ip for x in out):
            out.append({"host": ip, "kind": "lan" if ipaddress.ip_address(ip).is_private else "other"})
    return out


class Remote:
    """手机访问的设置（存在 state.json 的 "remote" 里）、开关端口、给界面的状态、推送。"""

    def __init__(self, store: Store, server, idle=winapi.idle_seconds, post=None):
        self.store = store
        self.server = server
        self.idle = idle
        self._post = post or _ntfy_post
        self.error = ""
        self.push_error = ""
        self._addrs: list[dict] | None = None
        self._addrs_at = 0.0
        self._lock = threading.Lock()

    # ------------------------------------------------------------ 设置
    def cfg(self) -> dict:
        with self.store.lock:
            c = dict(self.store.state.get("remote") or {})
        push = dict(c.get("push") or {})
        port = c.get("port")
        return {
            "on": bool(c.get("on")),
            "port": port if isinstance(port, int) and 1 <= port <= 65535 else DEFAULT_PORT,
            "key": str(c.get("key") or ""),
            "push": {"on": bool(push.get("on")), "server": str(push.get("server") or NTFY_SERVER).rstrip("/"),
                     "topic": str(push.get("topic") or ""),
                     "detail": push.get("detail") if push.get("detail") in DETAILS else "title",
                     "away": push.get("away", True) is not False},
        }

    def _save(self, c: dict) -> None:
        with self.store.lock:
            self.store.state["remote"] = c
            self.store.schedule_save()
        self.store.save_state()  # 钥匙换了要马上落盘：程序崩了也不会退回旧钥匙
        self._publish()

    def _publish(self) -> None:
        """设置面板标题上的一句话（开没开、推没推）放进快照里；完整状态（链接、二维码）只在打开面板时给。"""
        c = self.cfg()
        self.server.meta["remote"] = {"on": c["on"], "running": self.server.remote_port is not None,
                                      "push": c["push"]["on"], "error": self.error}
        with self.store.lock:
            self.store._bump()

    # ------------------------------------------------------------ 开关
    def start(self) -> bool:
        """按设置开 / 关端口。开不了（端口被占用、没有网络权限）记下原因，界面上显示。"""
        c = self.cfg()
        self.error = ""
        if not c["on"]:
            self.server.stop_remote()
            self._publish()
            return False
        if not c["key"]:
            c["key"] = new_key()
            self._save(c)
        try:
            self.server.start_remote(c["key"], c["port"])
            log.info("remote access on port %s", c["port"])
        except OSError as e:
            self.server.stop_remote()
            self.error = f"开不了端口 {c['port']}：{e.strerror or e}（可能被别的程序占用了，换个端口试试）"
            log.warning("remote access: %s", self.error)
        self._publish()
        return self.server.remote_port is not None

    def addrs(self, refresh: bool = False) -> list[dict]:
        with self._lock:
            if refresh or self._addrs is None or time.monotonic() - self._addrs_at > 60:
                self._addrs = addresses()
                self._addrs_at = time.monotonic()
            return list(self._addrs)

    def links(self, refresh: bool = False) -> list[dict]:
        c = self.cfg()
        port = self.server.remote_port or c["port"]
        out = []
        for a in self.addrs(refresh):
            host = a["host"]
            base = f"http://{host}:{port}/"
            out.append({"kind": a["kind"], "host": host, "base": base, "url": f"{base}?k={c['key']}"})
        return out

    def status(self, refresh: bool = False) -> dict:
        c = self.cfg()
        running = self.server.remote_port is not None
        links = self.links(refresh) if running else []
        for x in links:
            try:
                x["qr"] = qr.svg(x["url"])
            except ValueError:
                x["qr"] = ""
        p = c["push"]
        return {"on": c["on"], "running": running, "port": c["port"], "error": self.error, "links": links,
                "tailscale": any(x["kind"] == "tailscale" for x in links),
                "push": {"on": p["on"], "server": p["server"], "topic": p["topic"], "detail": p["detail"], "away": p["away"],
                         "subscribe": f"{p['server']}/{p['topic']}" if p["topic"] else "", "error": self.push_error,
                         "idle_known": self.idle() is not None}}

    def action(self, body: dict):
        """界面（只有电脑上的窗口能调）：{"op": status | enable | new_key | port | push | push_test, …}。返回新状态。"""
        op = str(body.get("op") or "status")
        c = self.cfg()
        if op == "enable":
            c["on"] = bool(body.get("on"))
            if c["on"] and not c["key"]:
                c["key"] = new_key()
            self._save(c)
            self.start()
        elif op == "new_key":
            c["key"] = new_key()
            self._save(c)
            self.start()
        elif op == "port":
            try:
                port = int(body.get("port"))
            except (TypeError, ValueError):
                raise ValueError("端口要是数字") from None
            if not 1024 <= port <= 65535:
                raise ValueError("端口要在 1024 到 65535 之间")
            c["port"] = port
            self._save(c)
            self.start()
        elif op == "push":
            p = c["push"]
            if "on" in body:
                p["on"] = bool(body["on"])
                if p["on"] and not p["topic"]:
                    p["topic"] = new_topic()
            if body.get("detail") in DETAILS:
                p["detail"] = body["detail"]
            if "away" in body:
                p["away"] = bool(body["away"])
            if "server" in body:
                srv = str(body.get("server") or "").strip().rstrip("/") or NTFY_SERVER
                if not srv.startswith(("https://", "http://")):
                    raise ValueError("推送服务器要以 https:// 开头")
                p["server"] = srv
            if body.get("new_topic"):
                p["topic"] = new_topic()
            self.push_error = ""
            self._save(c)
        elif op == "push_test":
            self.push_error = ""
            self._send({"title": "ClaudeDesk 测试推送", "message": "收到这条，说明手机推送设好了。", "priority": 3,
                        "tags": ["white_check_mark"]}, wait=True)
        elif op != "status":
            raise ValueError(f"未知操作 {op!r}")
        return self.status(refresh=op in ("status", "enable", "new_key", "port"))

    # ------------------------------------------------------------ 推送
    def notify(self, msgs: list[dict]) -> None:
        """新消息到了（store.on_arrived）：开了推送、而且（设了的话）人不在电脑前，就往 ntfy 发一条。"""
        c = self.cfg()
        p = c["push"]
        if not (p["on"] and p["topic"] and msgs):
            return
        idle = self.idle()
        if p["away"] and idle is not None and idle < AWAY_AFTER:
            return
        self._send(lambda: self.payload(msgs, p["detail"]))  # 拼内容要查地址（可能要问 Tailscale）：放到后台线程里

    def payload(self, msgs: list[dict], detail: str) -> dict:
        st = self.store
        dec = [m for m in msgs if m["kind"] == "decision"]
        urgent = any(m["priority"] == "high" for m in msgs)
        target = (dec or msgs)[-1]
        head = {"decision": "需要你决定", "answer": "新回答", "info": "通知"}
        out: dict = {"priority": 5 if urgent else 4 if dec else 3,
                     "tags": ["bell"] if dec else ["speech_balloon"] if target["kind"] == "answer" else ["information_source"]}
        if detail == "none":
            out["title"] = "ClaudeDesk"
            out["message"] = (f"{len(dec)} 条新的待决定" if dec else f"{len(msgs)} 条新消息") + "，打开 ClaudeDesk 看看"
        elif len(msgs) == 1:
            m = msgs[0]
            project = st.project_info(m)[0]
            out["title"] = f"{'追问有回答了' if m.get('reply_to') else head[m['kind']]}：{m['title']}"[:120]
            snippet = plain_summary(m["body"], 160) if detail == "full" else ""
            out["message"] = f"[{project}] " + (snippet or m["title"])
        else:
            out["title"] = f"{len(msgs)} 条新消息" + (f"（{len(dec)} 条待决定）" if dec else "")
            out["message"] = "\n".join(f"· [{st.project_info(m)[0]}] {m['title']}" for m in msgs[-5:])
        base = next((x["base"] for x in self.links() if x["kind"] != "other"), None) if self.server.remote_port else None
        if base:  # 点通知打开那条（地址不带钥匙：手机浏览器里已经登录过）
            out["click"] = f"{base}#m={target['id']}"
        return out

    def _send(self, payload, wait: bool = False) -> None:
        """payload：要发的内容，或者返回内容的函数（在发送线程里调）。wait：等它发完，失败抛 ValueError。"""
        p = self.cfg()["push"]
        if not p["topic"]:
            raise ValueError("还没有推送主题：先打开推送")

        def go():
            try:
                self._post(p["server"], dict(payload() if callable(payload) else payload, topic=p["topic"]))
                self.push_error = ""
            except Exception as e:  # noqa: BLE001 - 推送失败不影响别的
                self.push_error = f"推送失败：{e}"
                log.warning(self.push_error)
                if wait:
                    raise ValueError(self.push_error) from None

        if wait:
            go()
        else:
            threading.Thread(target=go, name="push", daemon=True).start()


def _ntfy_post(server: str, body: dict, timeout: float = 10.0) -> None:
    """ntfy 的 JSON 发布接口（标题、正文是 UTF-8，不用塞进 HTTP 头）。"""
    req = urllib.request.Request(server + "/", data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": f"ClaudeDesk/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read()
    except urllib.error.HTTPError as e:
        raise OSError(f"HTTP {e.code} {e.read()[:200].decode('utf-8', 'replace')}") from None
