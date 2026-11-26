"""回复里的本机文件路径：点一下打开（或在资源管理器里选中）。

界面只把认出来的路径字符串交过来，这里再把关一遍：消息是 Claude 会话写的，会话又可能读过别人的网页、
文件，所以路径不能全信——
- 只认本机盘符路径（C:\\…、C:/…、Git Bash 的 /c/…、file:///C:/…）。UNC（\\\\server\\share）、
  \\\\?\\、file://server/… 一律不认：打开网络路径会把 Windows 登录凭据发给那台机器。
- 双击就会运行的文件（.exe、.bat、.ps1、.py、.lnk…）不直接打开，改成在资源管理器里选中它，让人自己决定。

都是纯函数（只用 ntpath），Linux 上也能测；真正打开 / 选中在 winapi.py。
"""
from __future__ import annotations

import ntpath
import os
import re
from typing import Callable
from urllib.parse import unquote, urlsplit

MAX_PATH_LEN = 1024
_DRIVE = re.compile(r"^[A-Za-z]:\\")
_GITBASH = re.compile(r"^/([A-Za-z])(?:/|$)")
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
_BAD_CHARS = set('<>"|?*')
# 打开 = 运行（或装东西、改注册表、挂载磁盘）的扩展名：只在资源管理器里选中。另外还看 PATHEXT
RUNS = frozenset("""
.exe .com .bat .cmd .ps1 .psm1 .psd1 .ps1xml .ps2 .ps2xml .psc1 .psc2 .vbs .vbe .vb .js .jse .wsf .wsh .wsc .ws .hta
.scr .pif .cpl .msc .msi .msp .mst .lnk .url .website .reg .inf .scf .sct .shs .jar .py .pyw .pyz .pyzw .pyc .pyo .sh
.bash .appref-ms .application .xbap .gadget .settingcontent-ms .library-ms .search-ms .searchconnector-ms .appx
.appxbundle .msix .msixbundle .appinstaller .diagcab .chm .hlp .xll .sys .dll .ocx .drv .job .mof .theme .themepack
.deskthemepack .iso .img .vhd .vhdx .vsix .msh .msh1 .msh2 .mshxml .msh1xml .msh2xml .ins .isp .crt .cer .der
""".split())
# 路径后面紧跟的汉字（"见 C:\\work\\data下面"）：找不到文件时一个个去掉再试
_CJK_TAIL = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]$")


def local_path(raw) -> str | None:
    """界面认出来的路径 -> 规范的 Windows 绝对路径（C:\\a\\b.txt）；不是本机盘符路径就返回 None。"""
    s = str(raw or "").strip()
    if not s or len(s) > MAX_PATH_LEN or any(ord(c) < 32 or ord(c) == 127 for c in s):
        return None
    if s[:5].lower() == "file:":
        parts = urlsplit(s)
        if parts.netloc and parts.netloc.lower() != "localhost":  # file://server/share：网络路径
            return None
        s = unquote(parts.path)
        if re.match(r"^/[A-Za-z]:", s):
            s = s[1:]
    s = s.replace("/", "\\")
    m = _GITBASH.match(s.replace("\\", "/"))
    if m:  # Git Bash：/c/Users/… -> C:\Users\…
        s = m.group(1) + ":\\" + s[3:]
    if not _DRIVE.match(s):
        return None
    s = ntpath.normpath(s)
    # Windows 自己会去掉每段末尾的点和空格（"a.exe." 就是 a.exe）：先去掉，后面按扩展名判断才准
    s = "\\".join([s[:2]] + [p.rstrip(". ") for p in s[3:].split("\\")]) if len(s) > 3 else s
    s = s if len(s) > 2 else s + "\\"
    if not _DRIVE.match(s) or ":" in s[2:] or _BAD_CHARS & set(s):  # 冒号：NTFS 备用数据流（a.txt:x.exe）
        return None
    for part in s[3:].split("\\"):
        if part.split(".")[0].strip().upper() in _RESERVED:  # CON、NUL、COM1…：设备，不是文件
            return None
    return s[0].upper() + s[1:]


def runs_when_opened(path: str) -> bool:
    ext = ntpath.splitext(path)[1].lower()
    if not ext:
        return False
    pathext = {e.strip().lower() for e in os.environ.get("PATHEXT", "").split(";") if e.strip()}
    return ext in RUNS or ext in pathext


def existing(path: str, exists: Callable[[str], bool] = os.path.exists) -> str | None:
    """路径在不在；不在而末尾是汉字的，一个个去掉再看（文字里路径常常紧挨着"下面""里"）。"""
    p = path
    for _ in range(16):
        if exists(p):
            return p
        if not _CJK_TAIL.search(p):
            return None
        p = p[:-1]
    return None


class Opener:
    """两个界面动作：open_path（打开 / 在文件夹里选中）和 path_info（先查一批路径在不在、是文件还是文件夹）。
    打开、选中、查盘符这些系统调用由调用方传进来：托盘程序传 winapi 的，测试传假的。"""

    def __init__(self, open_fn: Callable[[str], object], reveal_fn: Callable[[str], object],
                 remote_fn: Callable[[str], bool] = lambda p: False,
                 exists: Callable[[str], bool] = os.path.exists, isdir: Callable[[str], bool] = os.path.isdir):
        self.open_fn, self.reveal_fn, self.remote_fn, self.exists, self.isdir = open_fn, reveal_fn, remote_fn, exists, isdir

    def open_path(self, body: dict) -> dict:
        from .server import ActionError

        p = local_path(body.get("path"))
        if not p:
            raise ActionError("只能打开这台电脑上的文件（C:\\… 这样带盘符的路径）")
        found = existing(p, self.exists)
        if not found:
            raise ActionError(f"找不到 {p}")
        reveal = bool(body.get("reveal"))
        runs = not reveal and not self.isdir(found) and runs_when_opened(found)
        if reveal or runs:
            self.reveal_fn(found)
        else:
            self.open_fn(found)
        return {"path": found, "revealed": reveal or runs, "runs": runs}

    def path_info(self, body: dict) -> dict:
        """{原样的路径: {"kind": file / dir / gone / unknown, "path": 实际找到的}}。最多查 100 个；
        网络盘上的不查（服务器连不上时一查卡好几秒），当它在。"""
        out = {}
        for raw in list(body.get("paths") or [])[:100]:
            raw = str(raw)
            p = local_path(raw)
            if not p:
                out[raw] = {"kind": "gone", "path": None}
            elif self.remote_fn(p):
                out[raw] = {"kind": "unknown", "path": p}
            else:
                found = existing(p, self.exists)
                out[raw] = {"kind": ("dir" if self.isdir(found) else "file") if found else "gone", "path": found or p}
        return out
