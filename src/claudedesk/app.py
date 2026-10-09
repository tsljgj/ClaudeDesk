"""ClaudeDesk 托盘程序入口。

    ClaudeDesk.exe                 托盘 + 窗口（Edge WebView2）
    ClaudeDesk.exe --minimized     只留在托盘（开机自启用）
    ClaudeDesk.exe --serve         不开窗口，只起本机服务，用浏览器打开（调试 / 非 Windows）
    ClaudeDesk.exe --self-test     打包后的冒烟测试，结果写到 CLAUDEDESK_SELFTEST_OUT

界面是 assets/ 里的网页，由本进程的本机 HTTP 服务提供；窗口用 pywebview（WebView2）显示。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import logging.handlers
import os
import shutil
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
if not FROZEN:  # 从源码跑：desk.py 在仓库根目录
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import desk  # noqa: E402

from . import __version__, update, winapi  # noqa: E402
from ._build import BUILD  # noqa: E402
from .server import TOKEN_HEADER, DeskServer  # noqa: E402
from .store import Store, plain_summary  # noqa: E402

APP = "ClaudeDesk"
log = logging.getLogger("claudedesk")
WIN_W, WIN_H, MIN_W, MIN_H = 1240, 800, 380, 420
UPDATE_EVERY = 6 * 3600


def app_dir() -> Path:
    return Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parents[2]


def data_dir(arg: str | None) -> Path:
    if arg:
        d = Path(arg)
    elif os.environ.get("CLAUDEDESK_DATA"):
        d = Path(os.environ["CLAUDEDESK_DATA"])
    else:
        d = app_dir() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def instance_name(ddir: Path) -> str:
    """和 desk.pipe_name 一致：默认数据目录用固定名，别的目录加哈希（测试实例可以和正式的同时开）。"""
    base = "ClaudeDesk-" + (os.environ.get("USERNAME") or os.environ.get("USER") or "user")
    if ddir.resolve() == (app_dir() / "data").resolve():
        return base
    return base + "-" + hashlib.sha1(str(ddir.resolve()).lower().encode("utf-8")).hexdigest()[:8]


def setup_log(ddir: Path) -> None:
    if log.handlers:
        return
    try:
        h = logging.handlers.RotatingFileHandler(ddir / "claudedesk.log", maxBytes=1_000_000, backupCount=1,
                                                 encoding="utf-8")
    except OSError:
        return
    h.setFormatter(logging.Formatter(f"%(asctime)s [{os.getpid()}] %(levelname)s %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)

    def hook(t, e, tb):
        log.critical("uncaught exception", exc_info=(t, e, tb))

    sys.excepthook = hook
    threading.excepthook = lambda a: log.critical("uncaught in thread %s", getattr(a.thread, "name", "?"),
                                                  exc_info=(a.exc_type, a.exc_value, a.exc_traceback))


def sync_cli() -> None:
    """打包版：把 exe 里带的 desk.py 放到 exe 旁边（Claude 会话调用的就是它），保证命令行和程序同版本。"""
    if not FROZEN:
        return
    src = Path(getattr(sys, "_MEIPASS", "")) / "bundled" / "desk.py"
    dst = app_dir() / "desk.py"
    try:
        new = src.read_bytes()
        if not dst.exists() or dst.read_bytes() != new:
            tmp = dst.with_suffix(".py.tmp")
            tmp.write_bytes(new)
            os.replace(tmp, dst)
            log.info("desk.py updated next to the exe")
    except OSError as e:
        log.warning("could not write desk.py: %s", e)


# ------------------------------------------------------------------ 单实例交接
def instance_file(ddir: Path) -> Path:
    return ddir / "instance.json"


def write_instance(ddir: Path, port: int, token: str) -> None:
    p = instance_file(ddir)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid(), "port": port, "token": token, "build": BUILD}, f)


def clear_instance(ddir: Path) -> None:
    try:
        if json.loads(instance_file(ddir).read_text(encoding="utf-8")).get("pid") == os.getpid():
            instance_file(ddir).unlink()
    except (OSError, ValueError):
        pass


def ask_running(ddir: Path, action: str = "show", timeout: float = 3.0) -> bool:
    try:
        st = json.loads(instance_file(ddir).read_text(encoding="utf-8"))
        req = urllib.request.Request(
            f"http://127.0.0.1:{int(st['port'])}/api/action", data=json.dumps({"action": action}).encode(),
            headers={TOKEN_HEADER: str(st["token"]), "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return bool(json.loads(r.read()).get("ok"))
    except (OSError, ValueError, KeyError, urllib.error.URLError):
        return False


# ------------------------------------------------------------------ 托盘程序
class TrayApp:
    def __init__(self, store: Store, server: DeskServer, webview_mod, ddir: Path):
        import pystray

        from .icon import render

        self.pystray = pystray
        self.render = render
        self.store = store
        self.server = server
        self.webview = webview_mod
        self.ddir = ddir
        self.window = None
        self.hwnd = 0
        self.visible = False
        self.quitting = False
        self.toast_target: str | None = None
        self._icon_key = None
        self._phase = False
        self._pending_update = None
        self._show_when_ready = False
        self._handoff_window: dict = {}

        M, Item = pystray.Menu, pystray.MenuItem
        self.icon = pystray.Icon(APP, render(64), APP, menu=M(
            Item("打开 ClaudeDesk", lambda: self.show(), default=True),
            Item("全部标为已读", lambda: store.mark_all_read()),
            M.SEPARATOR,
            Item("开机自启", self._toggle_autostart, checked=lambda _: winapi.autostart_enabled(),
                 visible=winapi.WIN and FROZEN),
            Item("自动更新", self._toggle_auto_update, checked=lambda _: self.auto_update,
                 visible=update.is_packaged()),
            Item(lambda _: f"检查更新（build {BUILD}）", lambda: threading.Thread(
                target=self.check_updates, args=(True,), daemon=True).start(), visible=update.is_packaged()),
            Item("打开数据目录", lambda: winapi.open_path(ddir)),
            M.SEPARATOR,
            Item("退出", lambda: self.quit()),
        ))
        if winapi.WIN:  # 点通知（气泡 / Toast）时打开那条消息：pystray 没管这个事件，自己接
            try:
                from pystray._util import win32 as pw

                orig = self.icon._message_handlers[pw.WM_NOTIFY]

                def on_notify(wparam, lparam, orig=orig):
                    if lparam == 0x405:  # NIN_BALLOONUSERCLICK
                        threading.Thread(target=self.show, args=(self.toast_target,), daemon=True).start()
                        return 0
                    return orig(wparam, lparam)

                self.icon._message_handlers[pw.WM_NOTIFY] = on_notify
            except Exception:  # noqa: BLE001
                log.exception("could not hook notification clicks")

        store.on_changed.append(self.refresh_icon)
        store.on_arrived.append(self.notify)
        ea = server.extra_actions
        ea["show"] = lambda body: (threading.Thread(target=self.show, args=(body.get("id"),), daemon=True).start(), "ok")[1]
        ea["export_pdf"] = self.export_pdf
        ea["open_path"] = lambda body: winapi.open_path(Path(str(body.get("path"))))
        ea["open_data"] = lambda body: winapi.open_path(ddir)
        ea["autostart"] = lambda body: self._set_autostart(bool(body.get("on")))
        ea["auto_update"] = lambda body: self._set_auto_update(bool(body.get("on")))
        ea["check_update"] = lambda body: self.check_updates(manual=True, install=False)
        ea["install_update"] = lambda body: self.check_updates(manual=True, install=True)
        ea["quit"] = lambda body: (threading.Timer(0.2, self.quit).start(), "ok")[1]
        server.meta.update(app=True, autostart=winapi.autostart_enabled(), auto_update=self.auto_update)

    # ------------------------------------------------------------ 设置
    @property
    def auto_update(self) -> bool:
        return bool(self.store.state.get("app", {}).get("auto_update", True))

    def _set_auto_update(self, on: bool) -> bool:
        with self.store.lock:
            self.store.state.setdefault("app", {})["auto_update"] = on
            self.store.schedule_save()
        self.server.meta["auto_update"] = on
        self.icon.update_menu()
        return on

    def _toggle_auto_update(self, *_):
        self._set_auto_update(not self.auto_update)

    def _set_autostart(self, on: bool) -> bool:
        try:
            r = winapi.set_autostart(on)
        except OSError as e:
            log.warning("autostart: %s", e)
            r = winapi.autostart_enabled()
        self.server.meta["autostart"] = r
        self.icon.update_menu()
        return r

    def _toggle_autostart(self, *_):
        self._set_autostart(not winapi.autostart_enabled())

    # ------------------------------------------------------------ 图标 / 通知
    def refresh_icon(self) -> None:
        c = self.store.counts()
        key = (min(c["unread"], 100), c["urgent"] > 0 and self._phase, c["open"] > 0)
        if key != self._icon_key:
            self._icon_key = key
            self.icon.icon = self.render(64, count=c["unread"], alert=key[1], pending=key[2])
        tip = [APP]
        if c["open"]:
            tip.append(f"待你决定 {c['open']}")
        tip.append(f"未读 {c['unread']}")
        self.icon.title = "\n".join(tip)

    def _blink_loop(self) -> None:
        while not self.quitting:
            time.sleep(0.65)
            urgent = self.store.counts()["urgent"] > 0
            if urgent or self._phase:
                self._phase = not self._phase if urgent else False
                self.refresh_icon()

    def notify(self, msgs: list[dict]) -> None:
        urgent = [m for m in msgs if self.store.is_urgent(m)]
        target = (urgent or msgs)[-1]
        self.toast_target = target["id"]
        if len(msgs) == 1:
            m = msgs[0]
            head = {"decision": "需要你决定", "answer": "新回答", "info": "通知"}[m["kind"]]
            title = f"{head}：{m['title']}"
            text = f"[{m.get('repo') or m['source']}] " + (plain_summary(m["question"], 60) + " → " if m["question"] else "") \
                + plain_summary(m["body"], 100)
        else:
            nd = sum(1 for m in msgs if m["kind"] == "decision")
            title = f"{len(msgs)} 条新消息" + (f"（{nd} 条待决定）" if nd else "")
            text = "\n".join(f"· [{m['source']}] {m['title']}" for m in msgs[-4:])
        if getattr(self.icon, "HAS_NOTIFICATION", False):
            try:
                self.icon.notify(text[:250] or " ", title[:63])
            except Exception:  # noqa: BLE001
                log.exception("notify failed")
        if self.hwnd and not winapi.is_foreground(self.hwnd):
            if not self.visible:
                self._show_minimized()  # 任务栏上要有按钮才能闪
            winapi.flash(self.hwnd, urgent=bool(urgent))
        self.refresh_icon()

    # ------------------------------------------------------------ 窗口
    def _native(self, fn):
        """在 WinForms 界面线程上执行 fn（拿到 window.native 之后才能用）。"""
        from System import Func, Object  # type: ignore  # pythonnet，pywebview 在 Windows 上自带

        form = self.window.native
        return form.Invoke(Func[Object](fn))

    def _show_minimized(self) -> None:
        if self.window is None or not winapi.WIN:
            return
        try:
            import System.Windows.Forms as WinForms  # type: ignore

            def go():
                form = self.window.native
                form.WindowState = WinForms.FormWindowState.Minimized
                form.Show()
                return None

            self._native(go)
            self.visible = True
        except Exception:  # noqa: BLE001
            log.exception("show minimized failed")

    def show(self, mid: str | None = None) -> None:
        if self.window is None:
            self._show_when_ready = True
            return
        try:
            self.window.show()
            self.window.restore()
        except Exception:  # noqa: BLE001
            log.exception("show failed")
            return
        self.visible = True
        if self.hwnd:
            winapi.force_foreground(self.hwnd)
            winapi.stop_flash(self.hwnd)
        if mid:
            try:
                self.window.evaluate_js(f"window.deskOpen && window.deskOpen({json.dumps(mid)})")
            except Exception:  # noqa: BLE001
                log.exception("open message failed")

    def hide(self) -> None:
        self._save_geometry()
        if self.window is not None:
            self.window.hide()
        self.visible = False
        rel, self._pending_update = self._pending_update, None
        if rel is not None and not self.quitting:  # 用户看完关掉了窗口：现在悄悄装
            threading.Thread(target=self._install, args=(rel, False), daemon=True).start()

    def _on_closing(self):
        if self.quitting:
            return True
        threading.Thread(target=self.hide, daemon=True).start()
        if not self.store.state.get("tray_hint_shown"):
            self.store.state["tray_hint_shown"] = True
            self.store.schedule_save()
            try:
                self.icon.notify("ClaudeDesk 还在托盘里运行，有新消息会提醒你。右键托盘图标可以退出。", APP)
            except Exception:  # noqa: BLE001
                pass
        return False  # 取消关闭，留在托盘

    def _save_geometry(self) -> None:
        w = self.window
        if w is None:
            return
        try:
            if getattr(w, "native", None) is not None and winapi.WIN:
                import System.Windows.Forms as WinForms  # type: ignore

                form = w.native
                if form.WindowState != WinForms.FormWindowState.Normal:
                    return  # 最小化 / 最大化时的尺寸不记
            geo = {"w": int(w.width), "h": int(w.height), "x": int(w.x), "y": int(w.y)}
            if geo["w"] >= MIN_W and geo["h"] >= MIN_H:
                self.store.state["window"] = geo
                self.store.schedule_save()
        except Exception:  # noqa: BLE001
            pass

    def _geometry(self):
        g = self._handoff_window if self._handoff_window.get("w") else self.store.state.get("window") or {}
        w, h = int(g.get("w") or WIN_W), int(g.get("h") or WIN_H)
        x, y = g.get("x"), g.get("y")
        try:
            s = self.webview.screens[0]
            w, h = min(w, s.width), min(h, s.height)
            if isinstance(x, int) and isinstance(y, int):
                x, y = min(max(0, x), max(0, s.width - w)), min(max(0, y), max(0, s.height - h))
            else:
                x, y = None, None
        except Exception:  # noqa: BLE001
            x, y = None, None
        return max(MIN_W, w), max(MIN_H, h), x, y

    # ------------------------------------------------------------ 导出 PDF（WebView2 自带的 PrintToPdf）
    def export_pdf(self, body: dict):
        if self.window is None or not winapi.WIN:
            return {"fallback": True}
        name = str(body.get("name") or "ClaudeDesk").strip() or "ClaudeDesk"
        downloads = Path.home() / "Downloads"
        start_dir = str(downloads if downloads.exists() else Path.home())
        res = self.window.create_file_dialog(self.webview.FileDialog.SAVE, directory=start_dir,
                                             save_filename=name + ".pdf", file_types=("PDF 文件 (*.pdf)",))
        if not res:
            return {"cancelled": True}
        path = res if isinstance(res, str) else res[0]
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        try:
            ok = self._print_to_pdf(path)
        except Exception:  # noqa: BLE001
            log.exception("PrintToPdf failed")
            ok = False
        return {"path": path} if ok else {"fallback": True}

    def _print_to_pdf(self, path: str, timeout: float = 60) -> bool:
        from System import Action, Boolean, Func, Object  # type: ignore
        from System.Threading.Tasks import Task  # type: ignore

        done = threading.Event()
        out = {"ok": False}

        def finished(task):
            try:
                out["ok"] = bool(task.Result)
            except Exception:  # noqa: BLE001
                log.exception("PrintToPdf task")
            done.set()

        def start():
            core = self.window.native.browser.webview.CoreWebView2
            settings = core.Environment.CreatePrintSettings()
            settings.ShouldPrintBackgrounds = True
            settings.ShouldPrintHeaderAndFooter = False
            core.PrintToPdfAsync(path, settings).ContinueWith(Action[Task[Boolean]](finished))
            return None

        self.window.native.Invoke(Func[Object](start))
        if not done.wait(timeout):
            raise TimeoutError("PrintToPdf timed out")
        return out["ok"] and Path(path).exists()

    # ------------------------------------------------------------ 自动更新
    def _update_loop(self) -> None:
        time.sleep(45)
        while not self.quitting:
            self.check_updates(manual=False)
            time.sleep(UPDATE_EVERY)

    def check_updates(self, manual: bool = False, install: bool | None = None) -> str:
        try:
            rel, status = update.check()
            self.server.meta["update"] = {"latest": rel.build if rel else BUILD, "state": "", "checked": time.time()}
        except Exception as e:  # noqa: BLE001
            status = f"检查更新失败：{e}"
            log.warning(status)
            if manual:
                self._toast(status)
            return status
        self._bump_ui()
        if rel is None:
            if manual:
                self._toast(status)
            return status
        want = self.auto_update if install is None else install
        if not (want and update.can_self_update()):
            if manual:
                self._toast(f"ClaudeDesk build {rel.build} 可以更新了")
            return status
        if not manual and self.visible:
            self._pending_update = rel  # 不在用户看着的时候重启：等窗口关掉
            self.server.meta["update"]["state"] = "pending"
            return f"build {rel.build} 会在关掉窗口后安装"
        return self._install(rel, manual)

    def _install(self, rel, manual: bool) -> str:
        self._pending_update = None
        self.server.meta["update"] = {"latest": rel.build, "state": "installing", "checked": time.time()}
        self._bump_ui()
        log.info("update: build %s -> %s (manual=%s)", BUILD, rel.build, manual)
        window = {"show": self.visible}
        if self.visible and self.window is not None:
            try:
                window.update(w=int(self.window.width), h=int(self.window.height), x=int(self.window.x), y=int(self.window.y))
            except Exception:  # noqa: BLE001
                pass
        try:
            self.store.save_state()
            update.install(rel, self.ddir, extra_args=["--show"] if self.visible else ["--minimized"], window=window)
        except Exception as e:  # noqa: BLE001
            log.exception("update failed")
            self.server.meta["update"]["state"] = "failed"
            self._bump_ui()
            msg = f"更新失败：{e}"
            self._toast(msg)
            return msg
        threading.Timer(0.5, self.quit).start()  # 新 exe 已经在启动了
        return f"正在更新到 build {rel.build}，马上重启…"

    def _bump_ui(self) -> None:
        with self.store.lock:
            self.store._bump()

    def _toast(self, text: str) -> None:
        try:
            self.icon.notify(text, APP)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ 运行 / 退出
    def quit(self) -> None:
        log.info("quit")
        self.quitting = True
        killer = threading.Timer(5, os._exit, args=(0,))  # 不管下面卡在哪，5 秒后一定退出（新版本在等锁）
        killer.daemon = True
        killer.start()
        self._save_geometry()
        self.store.save_state()
        clear_instance(self.ddir)
        for step in (self.server.shutdown, self.icon.stop, lambda: self.window and self.window.destroy()):
            try:
                step()
            except Exception:  # noqa: BLE001
                log.exception("quit step failed")

    def run(self, show: bool, handoff: dict) -> int:
        self._handoff_window = handoff.get("window") if isinstance(handoff.get("window"), dict) else {}
        threading.Thread(target=self._blink_loop, name="blink", daemon=True).start()
        threading.Thread(target=update.cleanup_old, daemon=True).start()
        if update.is_packaged():
            threading.Thread(target=self._update_loop, name="update", daemon=True).start()
        if handoff.get("from"):
            log.info("updated from build %s", handoff["from"])
        self._show_when_ready = show
        self.refresh_icon()
        if self.webview is None:  # 没装 pywebview：用浏览器
            import webbrowser

            if show:
                webbrowser.open(self.server.url)
            self.server.extra_actions["show"] = lambda body: (webbrowser.open(self.server.url), "ok")[1]
            self.icon.run()
            return 0
        w, h, x, y = self._geometry()
        self.window = self.webview.create_window(
            APP, self.server.url, width=w, height=h, x=x, y=y, min_size=(MIN_W, MIN_H), hidden=True,
            background_color="#F4F4F6", text_select=True, zoomable=True)
        self.window.events.closing += self._on_closing
        threading.Thread(target=self.icon.run, name="tray", daemon=True).start()
        storage = self.ddir / "webview"
        log.info("gui starting (show=%s)", show)
        self.webview.start(self._gui_started, private_mode=False, storage_path=str(storage))
        log.info("gui stopped")
        return 0

    def _gui_started(self) -> None:
        try:
            self.hwnd = int(self._native(lambda: self.window.native.Handle.ToInt64()))
        except Exception:  # noqa: BLE001
            self.hwnd = 0
        if self._show_when_ready:
            self._show_when_ready = False
            self.show()


# ------------------------------------------------------------------ 自检（CI 用）
def self_test(ddir: Path) -> int:
    out = os.environ.get("CLAUDEDESK_SELFTEST_OUT")
    res: dict = {"build": BUILD, "version": __version__}
    tmp = Path(tempfile.mkdtemp(prefix="claudedesk-selftest-"))
    server = None
    try:
        try:
            import pystray  # noqa: F401

            res["pystray"] = True
        except Exception as e:  # noqa: BLE001 - Linux 没有图形界面时 pystray 导入就会失败
            res["pystray"] = True if not winapi.WIN else f"{type(e).__name__}: {e}"
        try:
            import webview  # noqa: F401

            res["webview"] = True
        except Exception:  # noqa: BLE001
            res["webview"] = False
        from .icon import render

        res["icon"] = render(64, count=3).size == (64, 64)
        store = Store(tmp, show_selftest=True)
        server = DeskServer(store).start_background()
        server.meta["app"] = True
        mid = desk.post_message(desk.make_message("decision", "selftest-ci", "自检", "表格 | a |\n|---|\n| $x^2$ |",
                                                  options=["A::甲", "B::乙"], allow_text=True), tmp)
        store.poll()
        with urllib.request.urlopen(server.url, timeout=5) as r:
            html = r.read().decode("utf-8")
        res["page"] = server.token in html and "ClaudeDesk" in html
        for asset in ("assets/app.js", "assets/markdown.js", "assets/vendor/katex/katex.min.js",
                      "assets/vendor/fonts.css", "assets/vendor/markdown-it.min.js"):
            with urllib.request.urlopen(server.url + asset, timeout=5) as r:
                res.setdefault("assets", {})[asset] = r.status == 200 and len(r.read()) > 100
        try:
            urllib.request.urlopen(server.url + "api/state", timeout=5)
            res["auth"] = False
        except urllib.error.HTTPError as e:
            res["auth"] = e.code == 401

        def call(path, body=None):
            headers = {TOKEN_HEADER: server.token, "Content-Type": "application/json"}
            req = urllib.request.Request(server.url + path, headers=headers,
                                         data=json.dumps(body).encode() if body is not None else None)
            with urllib.request.urlopen(req, timeout=5) as r:
                return json.loads(r.read())

        st = call("api/state")
        res["state"] = any(m["id"] == mid for m in st["messages"])
        rep = call("api/action", {"action": "reply", "id": mid, "choice": "B", "text": "ok"})
        res["reply"] = rep.get("ok") and any(r.get("id") == mid and r.get("choice") == "B"
                                             for r in desk.read_all(tmp / desk.RESPONSES))
        res["archive"] = call("api/action", {"action": "archive", "ids": [mid]}).get("result") == 1
        res["delete"] = call("api/action", {"action": "delete", "ids": [mid]}).get("result") == 1 and \
            not any(m.get("id") == mid for m in desk.read_all(tmp / desk.INBOX))
        res["bundled_cli"] = (not FROZEN) or (Path(getattr(sys, "_MEIPASS", "")) / "bundled" / "desk.py").exists()
        checks = [v for k, v in res.items() if k in ("pystray", "icon", "page", "auth", "state", "reply", "archive",
                                                     "delete", "bundled_cli")] + list(res["assets"].values())
        res["ok"] = all(v is True for v in checks)
    except Exception as e:  # noqa: BLE001 - 没有控制台，出错也要写进结果
        res["ok"] = False
        res["error"] = f"{type(e).__name__}: {e}"
    finally:
        if server:
            server.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
    text = json.dumps(res, ensure_ascii=False)
    if out:
        Path(out).write_text(text, encoding="utf-8")
    elif sys.stdout:
        print(text)
    return 0 if res.get("ok") else 1


# ------------------------------------------------------------------ main
def _poll_loop(store: Store, stop: threading.Event) -> None:
    stop.wait(1.5)  # 第一次读取稍后做：托盘图标先注册好，程序关着时到的消息才能补提醒
    while not stop.is_set():
        try:
            store.poll()
        except Exception:  # noqa: BLE001
            log.exception("poll failed")
        stop.wait(1.0)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog=APP)
    ap.add_argument("--minimized", action="store_true", help="启动后只留在托盘（开机自启用）")
    ap.add_argument("--show", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--data", help="数据目录（默认 exe 旁边的 data/）")
    ap.add_argument("--show-selftest", action="store_true", help="显示 source=selftest* 的消息")
    ap.add_argument("--serve", action="store_true", help="只起本机服务，在浏览器里用")
    ap.add_argument("--port", type=int, default=0, help="--serve 时的端口（默认随机）")
    ap.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--updated-from", type=int, help=argparse.SUPPRESS)
    args, _ = ap.parse_known_args(argv)

    ddir = data_dir(args.data)
    setup_log(ddir)
    if args.self_test:
        return self_test(ddir)

    handoff = update.take_handoff(ddir)
    after_update = args.updated_from is not None or bool(handoff)
    log.info("start build=%s exe=%s args=%s after_update=%s", BUILD, sys.executable, sys.argv[1:], after_update)

    name = instance_name(ddir)
    lock = winapi.single_instance(name)
    deadline = time.time() + (20 if after_update else 0)
    while lock is None and time.time() < deadline:  # 更新后旧进程可能还在退出
        time.sleep(0.5)
        lock = winapi.single_instance(name)
    if lock is None:
        if args.minimized:
            return 0
        winapi.allow_foreground_any()
        if ask_running(ddir, "show"):
            return 0
        winapi.message_box("ClaudeDesk 已经在运行，但没有响应。\n请在任务管理器里结束 ClaudeDesk.exe 后再打开。")
        return 1
    marker = winapi.running_marker(name)  # noqa: F841 - 句柄要一直开着

    sync_cli()
    if winapi.WIN and FROZEN:
        try:
            if winapi.autostart_enabled():
                winapi.set_autostart(True)  # 迁移 1.x 的启动文件夹快捷方式；顺便更新 exe 路径
        except OSError:
            pass

    store = Store(ddir, show_selftest=args.show_selftest)
    server = DeskServer(store, port=args.port if args.serve else 0).start_background()
    write_instance(ddir, server.port, server.token)
    stop = threading.Event()
    threading.Thread(target=_poll_loop, args=(store, stop), name="poll", daemon=True).start()

    if args.serve:
        print(f"ClaudeDesk 在 {server.url}  （Ctrl-C 退出）", flush=True)
        server.extra_actions["show"] = lambda body: "ok"
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
        finally:
            stop.set()
            store.save_state()
            clear_instance(ddir)
        return 0

    try:
        import webview
    except ImportError:
        webview = None
    show = args.show or (not args.minimized and not after_update) or bool((handoff.get("window") or {}).get("show"))
    try:
        rc = TrayApp(store, server, webview, ddir).run(show=show, handoff=handoff)
    finally:
        stop.set()
        store.save_state()
        clear_instance(ddir)
        winapi.release(lock)
    return rc


if __name__ == "__main__":
    sys.exit(main())
