"""本机 HTTP 服务：给 WebView2 窗口（或浏览器）提供界面和 API。

安全：只绑 127.0.0.1，拒绝陌生 Host 头（防 DNS rebinding），每个 API 请求都要带本进程
随机生成的 token 头（防别的网页跨站调用）。静态资源（字体、脚本）不含秘密，不要求 token。
"""
from __future__ import annotations

import json
import logging
import mimetypes
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, unquote, urlsplit

from . import __version__
from ._build import BUILD
from .store import Store

LOOPBACK = {"127.0.0.1", "localhost", "::1"}
TOKEN_HEADER = "X-Desk-Token"
MAX_BODY = 1 << 20
SETTINGS = {  # 界面设置：键 -> 允许的值
    "theme": ("system", "light", "dark"),
    "accent": ("ember", "indigo", "jade", "rose"),
    "font": ("sans", "serif"),
    "size": ("s", "m", "l"),
    "density": ("cozy", "compact"),
    "width": ("m", "l", "full"),
}
SETTING_DEFAULTS = {"theme": "system", "accent": "ember", "font": "sans", "size": "m", "density": "cozy", "width": "l"}
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


class _HTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        """默认实现把 traceback 打到 stderr：有控制台时满屏噪音，打包的 exe 里又什么都看不到。
        客户端断开的不用管；别的错误写进 claudedesk.log。"""
        if isinstance(sys.exc_info()[1], GONE):
            return
        log.exception("http handler error (client %s)", client_address)


class DeskServer:
    def __init__(self, store: Store, host: str = "127.0.0.1", port: int = 0):
        self.store = store
        self.token = secrets.token_urlsafe(24)
        self.extra_actions: dict[str, Callable[[dict], object]] = {}  # 托盘程序注册的动作（导出 PDF、更新…）
        self.meta: dict = {"build": BUILD, "version": __version__, "update": None, "app": False}
        self.httpd = _HTTPServer((host, port), self._handler())
        self.host = host
        self.port = self.httpd.server_address[1]
        self.assets = assets_dir()
        self.asset_files = asset_index(self.assets)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def start_background(self) -> "DeskServer":
        threading.Thread(target=self.httpd.serve_forever, name="desk-http", daemon=True).start()
        return self

    def shutdown(self) -> None:
        self.httpd.shutdown()
        with self.store.cond:
            self.store.cond.notify_all()

    # ------------------------------------------------------------ 数据
    def settings(self) -> dict:
        out = dict(SETTING_DEFAULTS)
        for k in SETTINGS:
            v = self.store.setting(k)
            if v in SETTINGS[k]:
                out[k] = v
        return out

    def page(self) -> bytes:
        boot = {"token": self.token, "build": BUILD, "version": __version__, "settings": self.settings(),
                "platform": sys.platform, "app": bool(self.meta.get("app"))}
        html = (self.assets / "index.html").read_text(encoding="utf-8")
        return html.replace("/*__BOOT__*/{}", json.dumps(boot, ensure_ascii=False)).encode("utf-8")

    def snapshot(self) -> dict:
        st = self.store
        with st.lock:
            return {"version": st.version, "messages": st.summaries(), "counts": st.counts(), "aliases": dict(st.aliases),
                    "hidden_projects": sorted(st.hidden_projects), "settings": self.settings(), "meta": self.meta}

    def action(self, body: dict):
        st = self.store
        name = str(body.get("action") or "")
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
            return self.settings()
        if name in self.extra_actions:
            return self.extra_actions[name](body)
        raise ActionError(f"未知操作 {name!r}")

    # ------------------------------------------------------------ HTTP
    def _handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _send(self, code: int, body: bytes, ctype: str, cache: bool = False):
                self._started = True
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "max-age=86400" if cache else "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)

            def _json(self, code: int, obj) -> None:
                self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

            def _host_ok(self) -> bool:
                host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
                return host in LOOPBACK

            def _authed(self) -> bool:
                return secrets.compare_digest(self.headers.get(TOKEN_HEADER, ""), server.token)

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
                if path == "/":
                    return self._send(200, server.page(), "text/html; charset=utf-8")
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
                    return self._json(200, server.snapshot())
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
                    result = server.action(body)
                except ActionError as e:
                    return self._json(200, {"ok": False, "message": str(e)})
                except (json.JSONDecodeError, OSError, ValueError, TimeoutError) as e:
                    return self._json(200, {"ok": False, "message": f"{type(e).__name__}: {e}"})
                return self._json(200, {"ok": True, "result": result})

            def log_message(self, *args):
                pass

        return Handler


def _num(q: dict, key: str, cast, default):
    """查询参数转数字；写错了（since=abc、wait=nan）按默认值。"""
    try:
        v = cast((q.get(key) or [""])[0])
    except ValueError:
        return default
    return v if v == v else default  # NaN 不等于自己
