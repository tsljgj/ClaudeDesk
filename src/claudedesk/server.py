"""本机 HTTP 服务：给 WebView2 窗口（或浏览器）提供界面和 API。

安全：只绑 127.0.0.1，拒绝陌生 Host 头（防 DNS rebinding），每个 API 请求都要带本进程
随机生成的 token 头（防别的网页跨站调用）。静态资源（字体、脚本）不含秘密，不要求 token。

手机访问（用户在设置里打开，见 remote.py）：另开一个绑在所有网卡上的端口。那边不看 Host 头，改认链接里的
钥匙（?k=…，第一次打开后换成 cookie，地址栏里不留）；API 照样要 token 头；只放行看消息、回复用的操作
（REMOTE_ACTIONS），托盘程序注册的动作（打开文件、退出、更新…）一律不行。换钥匙后旧链接和已登录的手机都失效。
"""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import secrets
import socket
import sys
import threading
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, unquote, urlsplit

from . import __version__
from ._build import BUILD
from .store import AUTO_ARCHIVE, AUTO_ARCHIVE_DEFAULT, Store

LOOPBACK = {"127.0.0.1", "localhost", "::1"}
TOKEN_HEADER = "X-Desk-Token"
MAX_BODY = 1 << 20
REMOTE_COOKIE = "desk_remote"
# 手机上能做的：看、回复、追问、整理。不含 settings（手机自己记外观）和托盘程序的动作
REMOTE_ACTIONS = frozenset({"read", "read_all", "archive", "archive_handled", "alias", "resolve", "unresolve",
                            "hide_project", "show_project", "delete", "reply", "followup"})
SETTINGS = {  # 界面设置：键 -> 允许的值
    "theme": ("system", "light", "dark"),
    "accent": ("ember", "indigo", "jade", "rose"),
    "font": ("sans", "serif"),
    "size": ("s", "m", "l"),
    "density": ("cozy", "compact"),
    "width": ("m", "l", "full"),
    "auto_archive": tuple(AUTO_ARCHIVE),  # 自动归档已处理的（只在电脑上改：手机不能发 settings）
}
SETTING_DEFAULTS = {"theme": "system", "accent": "ember", "font": "sans", "size": "m", "density": "cozy", "width": "l",
                    "auto_archive": AUTO_ARCHIVE_DEFAULT}
GONE = (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)  # 客户端自己断开了（长轮询被放弃、页面刷新）
log = logging.getLogger("claudedesk")


def assets_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", "")) / "claudedesk" if getattr(sys, "frozen", False) else Path(__file__).parent
    return base / "assets"


def asset_index(root: Path) -> dict[str, Path]:
    """启动时列一遍 assets/ 下的文件：相对路径（/ 分隔）-> 文件。请求只按这张表查，
    请求里的路径从不直接交给文件系统（否则 /assets/%5C%5Chost%5Cshare 这种 UNC 路径会让 Windows 先去连那台机器的 SMB）。"""
    try:
        return {p.relative_to(root).as_posix(): p for p in root.rglob("*") if p.is_file()}
    except OSError:
        return {}


class ActionError(Exception):
    pass


def external_url(url) -> str | None:
    """能交给系统浏览器打开的链接：只认 http(s) 和 mailto，不带空白和控制字符。
    别的协议（file:、ms-settings:、自定义协议）在 Windows 上可能直接启动程序，界面上点到也不开。"""
    u = str(url or "").strip()
    if len(u) > 4096 or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in u):
        return None
    parts = urlsplit(u)
    if parts.scheme.lower() in ("http", "https") and parts.netloc:
        return u
    if parts.scheme.lower() == "mailto" and len(u) > 7:
        return u
    return None


class _HTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        """默认实现把 traceback 打到 stderr：有控制台时满屏噪音，打包的 exe 里又什么都看不到。
        客户端断开的不用管；别的错误写进 claudedesk.log。"""
        if isinstance(sys.exc_info()[1], GONE):
            return
        log.exception("http handler error (client %s)", client_address)


class _RemoteHTTPServer(_HTTPServer):
    """手机访问的端口。Windows 上 SO_REUSEADDR 会让两个程序同时绑到一个端口（谁收到连接说不准），
    "端口被占用"也就报不出来：那边改成独占绑定。"""
    allow_reuse_address = os.name != "nt"

    def server_bind(self):
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class DeskServer:
    def __init__(self, store: Store, host: str = "127.0.0.1", port: int = 0):
        self.store = store
        self.token = secrets.token_urlsafe(24)
        self.extra_actions: dict[str, Callable[[dict], object]] = {}  # 托盘程序注册的动作（导出 PDF、更新…）
        self.meta: dict = {"build": BUILD, "version": __version__, "update": None, "app": False}
        self._snap: tuple = (None, None, [])  # (版本, store, 摘要列表)：见 snapshot
        self.httpd = _HTTPServer((host, port), self._handler())
        self.host = host
        self.port = self.httpd.server_address[1]
        self.assets = assets_dir()
        self.asset_files = asset_index(self.assets)
        self.remote_httpd: _HTTPServer | None = None  # 手机访问的端口（开着时）
        self.remote_token = ""
        self._remote_lock = threading.Lock()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def start_background(self) -> "DeskServer":
        threading.Thread(target=self.httpd.serve_forever, name="desk-http", daemon=True).start()
        return self

    def shutdown(self) -> None:
        self.stop_remote()
        self.httpd.shutdown()
        with self.store.cond:
            self.store.cond.notify_all()

    # ------------------------------------------------------------ 手机访问
    def start_remote(self, token: str, port: int, host: str = "0.0.0.0") -> int:
        """在 host:port 上开手机访问。已经开在这个端口上：只换钥匙（旧链接、旧 cookie、等着的长轮询都失效）；
        开在别的端口：先关掉再开。返回实际端口；端口被占用等抛 OSError。"""
        if len(token or "") < 16:
            raise ValueError("钥匙太短")
        with self._remote_lock:
            h = self.remote_httpd
            if h is not None and h.server_address[1] == port and h.server_address[0] == host:
                if token != self.remote_token:
                    self.remote_token = token
                    self._wake()
                return port
            self._stop_remote_locked()
            httpd = _RemoteHTTPServer((host, port), self._handler(remote=True))
            self.remote_token = token
            self.remote_httpd = httpd
            threading.Thread(target=httpd.serve_forever, name="desk-remote", daemon=True).start()
            return httpd.server_address[1]

    def stop_remote(self) -> None:
        with self._remote_lock:
            self._stop_remote_locked()

    def _stop_remote_locked(self) -> None:
        httpd, self.remote_httpd = self.remote_httpd, None
        self.remote_token = ""
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
            self._wake()

    def _wake(self) -> None:
        """在长轮询里等着的手机请求：版本加一叫醒它们，各自再查一遍钥匙（换了就回 401）。"""
        with self.store.lock:
            self.store._bump()

    @property
    def remote_port(self) -> int | None:
        h = self.remote_httpd
        return h.server_address[1] if h is not None else None

    # ------------------------------------------------------------ 数据
    def settings(self) -> dict:
        out = dict(SETTING_DEFAULTS)
        for k in SETTINGS:
            v = self.store.setting(k)
            if v in SETTINGS[k]:
                out[k] = v
        return out

    def page(self, remote: bool = False) -> bytes:
        boot = {"token": self.remote_token if remote else self.token, "build": BUILD, "version": __version__,
                "settings": self.settings(), "platform": sys.platform, "app": bool(self.meta.get("app")) and not remote,
                "remote": remote}
        html = (self.assets / "index.html").read_text(encoding="utf-8")
        return html.replace("/*__BOOT__*/{}", json.dumps(boot, ensure_ascii=False)).encode("utf-8")

    def snapshot(self, remote: bool = False) -> dict:
        st = self.store
        meta = {"build": BUILD, "version": __version__} if remote else self.meta  # 手机上不给托盘程序的状态（更新、手机访问设置）
        with st.lock:
            # 同一版本只算一次全部摘要：长轮询醒来、操作后的刷新、手机一起来拿时不用每次都把上千条重算一遍
            if self._snap[0] != st.version or self._snap[1] is not st:
                self._snap = (st.version, st, st.summaries())
            return {"version": st.version, "messages": self._snap[2], "counts": st.counts(), "aliases": dict(st.aliases),
                    "hidden_projects": sorted(st.hidden_projects), "settings": self.settings(), "meta": meta}

    def action(self, body: dict, remote: bool = False):
        st = self.store
        name = str(body.get("action") or "")
        if remote and name not in REMOTE_ACTIONS:
            raise ActionError("手机上不能做这个操作")
        ids = [str(i) for i in body.get("ids") or ([body["id"]] if body.get("id") else [])]
        if name == "read":  # opened：用户打开了这条（读过的也记下时间，按时间归档已处理的时不算旧）
            return st.mark_read(ids, bool(body.get("read", True)), bool(body.get("opened")))
        if name == "read_all":
            return st.mark_all_read(body.get("project") or None)
        if name == "archive":
            return st.archive(ids, bool(body.get("on", True)))
        if name == "alias":
            return st.set_alias(str(body.get("from") or ""), body.get("to"))
        if name == "resolve":
            return st.resolve(ids)
        if name == "unresolve":  # 撤销标为已处理 / 归档待决定：没通知过会话的那条回复删掉，决定重新打开
            return st.unresolve(ids)
        if name in ("hide_project", "show_project"):  # 关掉 / 找回项目标签：消息还在，只是不显示、不计数。找回全部：{all: true}
            key = str(body.get("key") or "").strip()
            if name == "show_project" and body.get("all"):
                return st.show_project(None)
            if not key:
                raise ActionError("缺少项目名")
            return st.hide_project(key) if name == "hide_project" else st.show_project(key)
        if name == "archive_handled":
            return st.archive_handled(body.get("project") or None)
        if name == "delete":
            return st.delete(ids)
        if name == "reply":
            try:  # choice_index：界面上点的第几个（从 1 开始）；旧界面不发
                return st.submit(str(body.get("id")), body.get("choice"), str(body.get("text") or ""),
                                 body.get("choice_index"))
            except (KeyError, ValueError, FileExistsError) as e:
                raise ActionError(str(e).strip("'\"")) from None
        if name == "followup":  # 追问（还没回复的决定不行）
            try:
                return st.add_followup(str(body.get("id") or ""), str(body.get("text") or ""))
            except (KeyError, ValueError) as e:
                raise ActionError(str(e).strip("'\"")) from None
        if name == "settings":
            for k, v in (body.get("values") or {}).items():
                if k in SETTINGS and v in SETTINGS[k]:
                    st.set_setting(k, v)
                    if k == "auto_archive":
                        st._auto_at = 0.0  # 改了档：下一轮就按新的归档，不用等一分钟
            return self.settings()
        if name in self.extra_actions:
            return self.extra_actions[name](body)
        raise ActionError(f"未知操作 {name!r}")

    # ------------------------------------------------------------ HTTP
    def _handler(self, remote: bool = False):
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _send(self, code: int, body: bytes, ctype: str, cache: bool = False, headers: dict | None = None):
                self._started = True
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "max-age=86400" if cache else "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                if remote:  # 手机访问的页面不许被别的网站嵌进框里；不把地址（带钥匙）透露给点出去的网站
                    self.send_header("X-Frame-Options", "DENY")
                    self.send_header("Referrer-Policy", "no-referrer")
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(body)

            def _json(self, code: int, obj) -> None:
                self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

            def _host_ok(self) -> bool:
                if remote:  # 手机用局域网 IP / Tailscale 名字访问：Host 什么都有可能，靠钥匙把关
                    return True
                host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
                return host in LOOPBACK

            def _token(self) -> str:
                return server.remote_token if remote else server.token

            def _authed(self) -> bool:
                tok = self._token()
                return bool(tok) and secrets.compare_digest(self.headers.get(TOKEN_HEADER, "").encode(), tok.encode())

            def _key_ok(self, key: str) -> bool:
                tok = server.remote_token
                return bool(tok) and secrets.compare_digest(str(key).encode(), tok.encode())

            def _cookie_ok(self) -> bool:
                c = SimpleCookie()
                try:
                    c.load(self.headers.get("Cookie") or "")
                except CookieError:
                    return False
                return REMOTE_COOKIE in c and self._key_ok(c[REMOTE_COOKIE].value)

            def _remote_page(self, parts) -> None:
                """手机打开首页：带着钥匙来的，记成 cookie 后跳到不带钥匙的地址；已经有 cookie 的直接给页面。"""
                key = (parse_qs(parts.query).get("k") or [""])[0]
                if key and self._key_ok(key):
                    cookie = f"{REMOTE_COOKIE}={server.remote_token}; Path=/; Max-Age=31536000; HttpOnly; SameSite=Lax"
                    return self._send(303, b"", "text/plain", headers={"Location": "/", "Set-Cookie": cookie})
                if self._cookie_ok():
                    return self._send(200, server.page(remote=True), "text/html; charset=utf-8")
                return self._send(401, LOCKED_PAGE, "text/html; charset=utf-8")

            def _static(self, rel: str):
                p = server.asset_files.get(unquote(rel))
                if p is None:
                    return self._send(404, b"not found", "text/plain")
                ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
                if p.suffix == ".woff2":
                    ctype = "font/woff2"
                elif p.suffix in (".js", ".mjs"):
                    ctype = "text/javascript; charset=utf-8"
                elif p.suffix == ".css":
                    ctype = "text/css; charset=utf-8"
                self._send(200, p.read_bytes(), ctype, cache="/vendor/" in "/" + rel)

            def _guard(self, fn) -> None:
                """处理函数出错：写日志，回 500 JSON（界面能显示原因），而不是直接断开连接。"""
                self._started = False
                try:
                    fn()
                except GONE:
                    raise  # 交给 _HTTPServer.handle_error 安静地处理
                except Exception as e:  # noqa: BLE001
                    log.exception("%s %s failed", self.command, urlsplit(self.path).path)
                    self.close_connection = True
                    if not self._started:  # 已经开始回了就不能再回一次
                        self._json(500, {"ok": False, "error": type(e).__name__, "message": f"{type(e).__name__}: {e}"})

            def do_GET(self):
                self._guard(self._get)

            def do_POST(self):
                self._guard(self._post)

            def _get(self):
                if not self._host_ok():
                    return self._send(403, b"bad host", "text/plain")
                parts = urlsplit(self.path)
                path = parts.path
                if path == "/" and remote:
                    return self._remote_page(parts)
                if path == "/":
                    return self._send(200, server.page(), "text/html; charset=utf-8")
                if path == "/manifest.webmanifest":  # 手机"添加到主屏幕"：像个应用一样单独打开
                    return self._send(200, MANIFEST, "application/manifest+json", cache=True)
                if path.startswith("/icon-") and path.endswith(".png") and path[6:-4] in ("180", "192", "512"):
                    from .icon import png_bytes

                    return self._send(200, png_bytes(int(path[6:-4])), "image/png", cache=True)
                if path == "/favicon.png":
                    from .icon import png_bytes

                    return self._send(200, png_bytes(64), "image/png", cache=True)
                if path.startswith("/assets/"):
                    return self._static(path[len("/assets/"):])
                if not path.startswith("/api/"):
                    return self._send(404, b"not found", "text/plain")
                if not self._authed():
                    return self._json(401, {"error": "missing token"})
                q = parse_qs(parts.query)
                if path == "/api/state":
                    since = _num(q, "since", int, -1)
                    wait = min(_num(q, "wait", float, 0.0), 30.0)
                    if wait > 0 and since >= 0:
                        server.store.wait_change(since, wait)
                    if not self._authed():  # 等的时候换了钥匙 / 关了手机访问
                        return self._json(401, {"error": "missing token"})
                    return self._json(200, server.snapshot(remote=True) if remote else server.snapshot())
                if path == "/api/message":
                    d = server.store.detail((q.get("id") or [""])[0])
                    return self._json(200 if d else 404, d or {"error": "没有这条消息"})
                if path == "/api/search":
                    return self._json(200, {"ids": server.store.search((q.get("q") or [""])[0])})
                self._send(404, b"not found", "text/plain")

            def _post(self):
                if not self._host_ok():
                    return self._send(403, b"bad host", "text/plain")
                if not self._authed():
                    return self._json(401, {"error": "missing token"})
                if urlsplit(self.path).path != "/api/action":
                    return self._send(404, b"not found", "text/plain")
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    length = -1
                if length < 0:
                    self.close_connection = True
                    return self._json(400, {"ok": False, "message": "Content-Length 不对"})
                if length > MAX_BODY:
                    self.close_connection = True  # 没读的正文还在连接里：不能再复用
                    return self._json(413, {"ok": False, "message": "请求太大"})
                try:
                    body = json.loads(self.rfile.read(length) or b"{}")
                    if not isinstance(body, dict):
                        raise ValueError("body 必须是对象")
                    result = server.action(body, remote=True) if remote else server.action(body)
                except ActionError as e:
                    return self._json(200, {"ok": False, "message": str(e)})
                except (json.JSONDecodeError, OSError, ValueError, TimeoutError) as e:
                    return self._json(200, {"ok": False, "message": f"{type(e).__name__}: {e}"})
                return self._json(200, {"ok": True, "result": result})

            def log_message(self, *args):
                pass

        return Handler


LOCKED_PAGE = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>ClaudeDesk</title>
<style>body{font:16px/1.6 system-ui,sans-serif;margin:0;padding:48px 24px;max-width:28em}h1{font-size:20px}</style></head>
<body><h1>需要 ClaudeDesk 里的链接</h1>
<p>在电脑上打开 ClaudeDesk → 设置 → 手机访问，用手机扫码或打开那里的链接。</p>
<p>以前能打开、现在打不开：电脑上换过链接，或者关掉了手机访问。</p></body></html>""".encode("utf-8")
MANIFEST = json.dumps({
    "name": "ClaudeDesk", "short_name": "ClaudeDesk", "start_url": "/", "scope": "/", "display": "standalone",
    "icons": [{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
              {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}],
}, ensure_ascii=False).encode("utf-8")


def _num(q: dict, key: str, cast, default):
    """查询参数转数字；写错了（since=abc、wait=nan）按默认值。"""
    try:
        v = cast((q.get(key) or [""])[0])
    except ValueError:
        return default
    return v if v == v else default  # NaN 不等于自己
