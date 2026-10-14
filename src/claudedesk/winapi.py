"""Windows 小工具：单实例互斥量、给 desk.py 看的"程序在运行"标记、任务栏闪烁和角标、开机自启、消息框。

非 Windows 上全部变成无害的空操作（方便在 Linux / macOS 上跑测试和浏览器模式）。
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import uuid
from pathlib import Path

WIN = sys.platform == "win32"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "ClaudeDesk"

if WIN:
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _u32 = ctypes.WinDLL("user32", use_last_error=True)
    _k32.CreateMutexW.restype = wintypes.HANDLE
    _k32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.CreateNamedPipeW.restype = wintypes.HANDLE
    _k32.CreateNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                      wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]

    class FLASHWINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND), ("dwFlags", wintypes.DWORD),
                    ("uCount", wintypes.UINT), ("dwTimeout", wintypes.DWORD)]

    _u32.FlashWindowEx.argtypes = [ctypes.POINTER(FLASHWINFO)]
    _u32.GetForegroundWindow.restype = wintypes.HWND
    _u32.SetForegroundWindow.argtypes = [wintypes.HWND]
    _u32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
    _u32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
    _u32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _u32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    _u32.BringWindowToTop.argtypes = [wintypes.HWND]
    _u32.MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]
    _k32.GetCurrentThreadId.restype = wintypes.DWORD
    # 任务栏角标
    _u32.FindWindowExW.restype = wintypes.HWND
    _u32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
    _u32.MonitorFromWindow.restype = ctypes.c_void_p
    _u32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    try:  # Windows 10 1607 起才有
        _u32.GetDpiForWindow.restype = wintypes.UINT
        _u32.GetDpiForWindow.argtypes = [wintypes.HWND]
        _u32.GetSystemMetricsForDpi.argtypes = [ctypes.c_int, wintypes.UINT]
    except AttributeError:
        pass
    _u32.CreateIconFromResourceEx.restype = wintypes.HICON
    _u32.CreateIconFromResourceEx.argtypes = [ctypes.c_char_p, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD,
                                              ctypes.c_int, ctypes.c_int, wintypes.UINT]
    _u32.DestroyIcon.argtypes = [wintypes.HICON]
    _u32.RegisterWindowMessageW.restype = wintypes.UINT
    _u32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
    _u32.ChangeWindowMessageFilterEx.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.DWORD, ctypes.c_void_p]
    _ole = ctypes.WinDLL("ole32")
    _ole.CoInitializeEx.restype = ctypes.c_long
    _ole.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    _ole.CoCreateInstance.restype = ctypes.c_long
    _ole.CoCreateInstance.argtypes = [ctypes.c_char_p, ctypes.c_void_p, wintypes.DWORD, ctypes.c_char_p, ctypes.c_void_p]
    _cc = ctypes.WinDLL("comctl32")
    _SUBCLASSPROC = ctypes.WINFUNCTYPE(wintypes.LPARAM, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
                                       ctypes.c_size_t, ctypes.c_size_t)
    _cc.SetWindowSubclass.argtypes = [wintypes.HWND, _SUBCLASSPROC, ctypes.c_size_t, ctypes.c_size_t]
    _cc.RemoveWindowSubclass.argtypes = [wintypes.HWND, _SUBCLASSPROC, ctypes.c_size_t]
    _cc.DefSubclassProc.restype = wintypes.LPARAM
    _cc.DefSubclassProc.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]

INVALID_HANDLE = ctypes.c_void_p(-1).value


def single_instance(name: str):
    """拿到就返回一个要一直留着的句柄；已有实例在跑返回 None。"""
    if not WIN:
        import fcntl
        import tempfile

        f = open(Path(tempfile.gettempdir()) / f"{name}.lock", "w")
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            f.close()
            return None
        return f
    h = _k32.CreateMutexW(None, False, "Local\\" + name)
    if not h:
        return None
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS：拿到的是别人的互斥量，要关掉
        _k32.CloseHandle(h)
        return None
    return h


def release(handle) -> None:
    if handle is None:
        return
    if WIN:
        _k32.CloseHandle(handle)
    else:
        handle.close()


def running_marker(pipe: str):
    """开一个（不接受连接的）命名管道 \\\\.\\pipe\\<pipe>：desk.py post 靠列出管道名判断程序有没有在跑。
    名字用 desk.pipe_name（带数据目录哈希）；同名管道还在（旧进程没退干净）时返回 None。"""
    if not WIN:
        return None
    PIPE_ACCESS_INBOUND, PIPE_REJECT_REMOTE = 0x1, 0x8
    h = _k32.CreateNamedPipeW("\\\\.\\pipe\\" + pipe, PIPE_ACCESS_INBOUND, PIPE_REJECT_REMOTE, 1, 0, 0, 0, None)
    return None if h in (None, 0, INVALID_HANDLE) else h


def flash(hwnd: int, urgent: bool) -> None:
    """任务栏闪烁。urgent：一直闪到窗口被切到前台；否则闪 3 次后保持高亮。"""
    if not WIN or not hwnd:
        return
    FLASHW_TRAY, FLASHW_TIMERNOFG = 0x2, 0xC
    info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, FLASHW_TRAY | (FLASHW_TIMERNOFG if urgent else 0),
                      0 if urgent else 3, 0)
    _u32.FlashWindowEx(ctypes.byref(info))


def stop_flash(hwnd: int) -> None:
    if WIN and hwnd:
        info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, 0, 0, 0)
        _u32.FlashWindowEx(ctypes.byref(info))


# ------------------------------------------------------------------ 任务栏按钮角标（ITaskbarList3::SetOverlayIcon）
def small_icon_size(hwnd: int = 0) -> int:
    """任务栏上小图标（托盘图标、按钮角标）的像素数 = 任务栏那块屏幕 DPI 下的 SM_CXSMICON（16/20/24/32…）。
    问任务栏窗口自己的 DPI：Explorer 按显示器感知，本进程只是"系统 DPI 感知"（pywebview 设的），改了缩放不注销时
    自己的 DPI 是旧的。给了 hwnd 就用它所在显示器上的那条任务栏，否则用主任务栏。"""
    if not WIN:
        return 16
    try:
        mon = _u32.MonitorFromWindow(hwnd, 2) if hwnd else None  # MONITOR_DEFAULTTONEAREST
        dpi = 0
        for cls in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
            h = None
            while True:
                h = _u32.FindWindowExW(None, h, cls, None)
                if not h:
                    break
                d = _u32.GetDpiForWindow(h)
                if mon and d and _u32.MonitorFromWindow(h, 2) == mon:
                    return _u32.GetSystemMetricsForDpi(49, d)  # SM_CXSMICON
                dpi = dpi or d
        return _u32.GetSystemMetricsForDpi(49, dpi or _u32.GetDpiForSystem() or 96)
    except (AttributeError, OSError):  # Windows 10 1607 之前没有这些按 DPI 的函数
        return _u32.GetSystemMetrics(49) or 16


def icon_from_png(png: bytes, size: int) -> int:
    """PNG → HICON（CreateIconFromResourceEx 认 PNG 格式的图标资源，透明度原样保留）。用完要 destroy_icon。"""
    h = _u32.CreateIconFromResourceEx(png, len(png), True, 0x30000, size, size, 0)
    if not h:
        raise ctypes.WinError(ctypes.get_last_error())
    return h


def destroy_icon(h: int) -> None:
    if WIN and h:
        _u32.DestroyIcon(h)


class TaskbarList:
    """ITaskbarList3 的最小 ctypes 封装（只用 SetOverlayIcon），不用 comtypes / pywin32，打包版里也能用。
    它是单线程套间（STA）的 COM 对象：创建、调用、释放都要在窗口的界面线程上。"""
    CLSID = "56FDF344-FD6D-11d0-958A-006097C9A090"  # CLSID_TaskbarList
    IID = "EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF"    # IID_ITaskbarList3

    def __init__(self):
        if not WIN:
            raise OSError("Windows only")
        _ole.CoInitializeEx(None, 0x2)  # 界面线程本来就是 STA（WinForms），这句只是保险；S_FALSE 不要紧
        p = ctypes.c_void_p()
        hr = _ole.CoCreateInstance(uuid.UUID(self.CLSID).bytes_le, None, 1, uuid.UUID(self.IID).bytes_le, ctypes.byref(p))
        if hr < 0 or not p.value:
            raise OSError(f"CoCreateInstance(TaskbarList) 0x{hr & 0xFFFFFFFF:08X}")
        self._p = p.value
        hr = self._call(3)  # HrInit
        if hr < 0:
            self.close()
            raise OSError(f"ITaskbarList::HrInit 0x{hr & 0xFFFFFFFF:08X}")

    def _call(self, index: int, argtypes=(), *args) -> int:
        vtbl = ctypes.cast(self._p, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)(vtbl[index])(self._p, *args)

    def set_overlay(self, hwnd: int, hicon: int, desc: str = "") -> int:
        """hicon=0 清掉角标；desc 给读屏软件。返回 HRESULT（< 0 失败）。注意：窗口还没有任务栏按钮时也返回成功，
        但什么都不留下——按钮建好后要再设一次（TaskbarButtonCreated）。"""
        return self._call(18, (wintypes.HWND, wintypes.HICON, wintypes.LPCWSTR), hwnd, hicon or None, desc or None)

    def close(self) -> None:
        if self._p:
            self._call(2)  # Release
            self._p = None


_hooks: dict = {}  # ctypes 回调对象要一直有人引用：被回收后窗口再来一条消息进程就崩了


def watch_message(hwnd: int, name: str, fn) -> bool:
    """窗口收到注册消息 name（如 "TaskbarButtonCreated"）时调用 fn()。用 comctl32 的窗口子类挂在原窗口过程前面，
    所有消息照常往下传。必须在创建窗口的线程（界面线程）上调用；fn 也在那个线程上跑，要快。"""
    if not WIN or not hwnd:
        return False
    msg = _u32.RegisterWindowMessageW(name)
    if not msg:
        return False
    _u32.ChangeWindowMessageFilterEx(hwnd, msg, 1, None)  # MSGFLT_ALLOW：以管理员身份运行时 Explorer 的消息默认被挡

    def proc(h, m, wp, lp, sid, ref):
        if m == msg:
            try:
                fn()
            except Exception:  # noqa: BLE001 - 异常不能漏进窗口过程
                pass
        elif m == 0x82:  # WM_NCDESTROY：窗口没了，摘掉子类
            _cc.RemoveWindowSubclass(h, cb, sid)
        return _cc.DefSubclassProc(h, m, wp, lp)

    cb = _SUBCLASSPROC(proc)
    if not _cc.SetWindowSubclass(hwnd, cb, msg, 0):
        return False
    _hooks[(hwnd, msg)] = cb
    return True


def is_foreground(hwnd: int) -> bool:
    return bool(WIN and hwnd and _u32.GetForegroundWindow() == hwnd)


def force_foreground(hwnd: int) -> None:
    """用户明确要打开窗口时把它切到前台（绕过 Windows 对后台进程的前台锁）。"""
    if not WIN or not hwnd:
        return
    fg = _u32.GetForegroundWindow()
    if fg == hwnd:
        return
    fg_tid = _u32.GetWindowThreadProcessId(fg, None) if fg else 0
    me = _k32.GetCurrentThreadId()
    attached = bool(fg_tid and fg_tid != me and _u32.AttachThreadInput(me, fg_tid, True))
    try:
        _u32.BringWindowToTop(hwnd)
        _u32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            _u32.AttachThreadInput(me, fg_tid, False)


def allow_foreground_any() -> None:
    if WIN:
        _u32.AllowSetForegroundWindow(0xFFFFFFFF)  # ASFW_ANY：让已在运行的实例能把窗口切到前台


def message_box(text: str, title: str = "ClaudeDesk", yes_no: bool = False) -> bool:
    if not WIN:
        print(text, file=sys.stderr)
        return True
    MB_YESNO, MB_ICONINFO, MB_ICONQ, IDYES = 0x4, 0x40, 0x20, 6
    r = _u32.MessageBoxW(None, text, title, (MB_YESNO | MB_ICONQ) if yes_no else MB_ICONINFO)
    return r == IDYES if yes_no else True


def open_path(path) -> None:
    p = str(path)
    if WIN:
        os.startfile(p)  # noqa: S606 - 打开用户自己的文件 / 目录
    elif sys.platform == "darwin":
        subprocess.Popen(["open", p])
    else:
        subprocess.Popen(["xdg-open", p])


# ------------------------------------------------------------------ 开机自启（HKCU\...\Run，不需要管理员）
def _old_startup_link() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup/ClaudeDesk.lnk"


def autostart_command() -> str:
    return f'"{Path(sys.executable).resolve()}" --minimized'


def apps_dark_mode() -> bool:
    """Windows 设置里"应用模式"是不是深色（Personalize 下的 AppsUseLightTheme = 0）。"""
    if not WIN:
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def autostart_enabled() -> bool:
    if not WIN:
        return False
    if _old_startup_link().exists():  # 1.x 版本用的是"启动"文件夹里的快捷方式
        return True
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_VALUE)
        return True
    except OSError:
        return False


def set_autostart(on: bool) -> bool:
    if not WIN:
        return False
    import winreg

    try:
        _old_startup_link().unlink()
    except OSError:
        pass
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, RUN_VALUE, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, RUN_VALUE)
            except FileNotFoundError:
                pass
    return autostart_enabled()
