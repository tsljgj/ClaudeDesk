"""Windows 小工具：单实例互斥量、给 desk.py 看的"程序在运行"标记、任务栏闪烁、开机自启、消息框。

非 Windows 上全部变成无害的空操作（方便在 Linux / macOS 上跑测试和浏览器模式）。
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
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
    """开一个（不接受连接的）命名管道 \\\\.\\pipe\\<pipe>：desk.py post 靠列出管道名判断程序有没有在跑。"""
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
