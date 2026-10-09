"""本机 HTTP 服务：给 WebView2 窗口（或浏览器）提供界面和 API。

安全：只绑 127.0.0.1，拒绝陌生 Host 头（防 DNS rebinding），每个 API 请求都要带本进程
随机生成的 token 头（防别的网页跨站调用）。静态资源（字体、脚本）不含秘密，不要求 token。
"""
from __future__ import annotations

import json
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
}
SETTING_DEFAULTS = {"theme": "system", "accent": "ember", "font": "sans", "size": "m", "density": "cozy"}


def assets_dir() -> Path:
    base = Path(getattr(sys, "_MEIPASS", "")) / "claudedesk" if getattr(sys, "frozen", False) else Path(__file__).parent
    return base / "assets"


class ActionError(Exception):
    pass


class DeskServer:
    def __init__(self, store: Store, host: str = "127.0.0.1", port: int = 0):
        self.store = store
        self.token = secrets.token_urlsafe(24)
        self.extra_actions: dict[str, Callable[[dict], object]] = {}  # 托盘程序注册的动作（导出 PDF、更新…）
        self.meta: dict = {"build": BUILD, "version": __version__, "update": None, "app": False}
        self.httpd = ThreadingHTTPServer((host, port), self._handler())
        self.httpd.daemon_threads = True
        self.host = host
        self.port = self.httpd.server_address[1]
        self.assets = assets_dir()

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
                    "settings": self.settings(), "meta": self.meta}

    def action(self, body: dict):
        st = self.store
        name = str(body.get("action") or "")
        ids = [str(i) for i in body.get("ids") or ([body["id"]] if body.get("id") else [])]
        if name == "read":
            return st.mark_read(ids, bool(body.get("read", True)))
        if name == "read_all":
            return st.mark_all_read(body.get("project") or None)
        if name == "archive":
            return st.archive(ids, bool(body.get("on", True)))
        if name == "alias":
            return st.set_alias(str(body.get("from") or ""), body.get("to"))
        if name == "resolve":
            return st.resolve(ids)
        if name == "archive_handled":
            return st.archive_handled(body.get("project") or None)
        if name == "delete":
            return st.delete(ids)
        if name == "reply":
            try:
                return st.submit(str(body.get("id")), body.get("choice"), str(body.get("text") or ""))
            except (KeyError, ValueError, FileExistsError) as e:
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
                root = server.assets.resolve()
                p = (root / unquote(rel)).resolve()
                if root not in p.parents or not p.is_file():
                    return self._send(404, b"not found", "text/plain")
                ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
                if p.suffix == ".woff2":
                    ctype = "font/woff2"
                elif p.suffix in (".js", ".mjs"):
                    ctype = "text/javascript; charset=utf-8"
                elif p.suffix == ".css":
                    ctype = "text/css; charset=utf-8"
                self._send(200, p.read_bytes(), ctype, cache="/vendor/" in "/" + rel)

            def do_GET(self):
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
                    since = int((q.get("since") or ["-1"])[0] or -1)
                    wait = min(float((q.get("wait") or ["0"])[0] or 0), 30.0)
                    if wait > 0 and since >= 0:
                        server.store.wait_change(since, wait)
                    return self._json(200, server.snapshot())
                if path == "/api/message":
                    d = server.store.detail((q.get("id") or [""])[0])
                    return self._json(200 if d else 404, d or {"error": "没有这条消息"})
                if path == "/api/search":
                    return self._json(200, {"ids": server.store.search((q.get("q") or [""])[0])})
                self._send(404, b"not found", "text/plain")

            def do_POST(self):
                if not self._host_ok():
                    return self._send(403, b"bad host", "text/plain")
                if not self._authed():
                    return self._json(401, {"error": "missing token"})
                if urlsplit(self.path).path != "/api/action":
                    return self._send(404, b"not found", "text/plain")
                length = int(self.headers.get("Content-Length") or 0)
                if length > MAX_BODY:
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
