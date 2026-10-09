"""打包版 exe 的自动更新（从 GitHub Releases）。做法和 agent-management 的 redline 一样。

CI 每次在 main 或 claude/* 分支构建通过，就发布一个 `build-<N>` release，附带 `ClaudeDesk.exe`
和 `ClaudeDesk.exe.sha256`。运行中的 exe 比较 N 和自己的 BUILD，有新版就把新 exe 下载到旁边、
校验 SHA-256，然后换文件：Windows 允许给正在运行的 exe *改名*，所以当前的改名成
`ClaudeDesk.exe.old`，新的放到原位置并启动，旧进程退出。新进程启动时删掉 `.old`。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from ._build import BUILD

REPO = "tsljgj/ClaudeDesk"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
TAG_RE = re.compile(r"^build-(\d+)$")
ASSET = "ClaudeDesk.exe"
UA = {"User-Agent": f"claudedesk-updater/{BUILD}", "Accept": "application/vnd.github+json"}


class UpdateError(Exception):
    pass


@dataclass
class Release:
    build: int
    tag: str
    name: str
    exe_url: str
    sha_url: str
    html_url: str


def is_packaged() -> bool:
    return bool(getattr(sys, "frozen", False)) and BUILD > 0


def can_self_update() -> bool:
    return is_packaged() and sys.platform == "win32"


def _feed() -> str:
    # CLAUDEDESK_UPDATE_FEED：本地的 release JSON（和 GitHub 的同格式），端到端测试用
    return os.environ.get("CLAUDEDESK_UPDATE_FEED") or LATEST_API


def _get(url: str, timeout: int = 20) -> bytes:
    if not url.startswith(("http://", "https://")):
        return Path(url.removeprefix("file://")).read_bytes()
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise UpdateError(f"HTTP {e.code}：{url}") from None
    except urllib.error.URLError as e:
        raise UpdateError(f"网络错误：{e.reason}") from None


def latest() -> Release | None:
    doc = json.loads(_get(_feed()))
    m = TAG_RE.match(doc.get("tag_name") or "")
    if not m:
        return None
    assets = {a.get("name"): a.get("browser_download_url") for a in doc.get("assets") or []}
    if ASSET not in assets or ASSET + ".sha256" not in assets:
        return None
    return Release(int(m.group(1)), doc["tag_name"], doc.get("name") or doc["tag_name"],
                   assets[ASSET], assets[ASSET + ".sha256"], doc.get("html_url") or "")


def check() -> tuple[Release | None, str]:
    """(更新的版本或 None, 给人看的状态)。"""
    if not is_packaged():
        return None, "从源码运行（build 0）：用 git pull 更新"
    rel = latest()
    if rel is None:
        return None, "还没有发布的版本"
    if rel.build <= BUILD:
        return None, f"已是最新（build {BUILD}）"
    return rel, f"有新版本：build {BUILD} → {rel.build}"


def _download(url: str, dest: Path) -> str:
    if not url.startswith(("http://", "https://")):
        data = Path(url.removeprefix("file://")).read_bytes()
        dest.write_bytes(data)
        return hashlib.sha256(data).hexdigest()
    h = hashlib.sha256()
    req = urllib.request.Request(url, headers={"User-Agent": UA["User-Agent"]})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 16):
            h.update(chunk)
            f.write(chunk)
    return h.hexdigest()


def install(rel: Release, handoff_dir: Path, extra_args: list[str] | None = None, window: dict | None = None) -> None:
    """下载、校验、换文件、启动新 exe。调用方随后必须退出。"""
    if not can_self_update():
        raise UpdateError("只有打包好的 Windows exe 能自动更新")
    exe = Path(sys.executable)
    new = exe.with_name(exe.name + ".download")
    old = exe.with_name(exe.name + ".old")
    expected = _get(rel.sha_url).decode().split()[0].strip().lower()
    got = _download(rel.exe_url, new)
    if got != expected:
        new.unlink(missing_ok=True)
        raise UpdateError(f"build {rel.build} 校验和不对，已放弃更新")
    try:
        old.unlink(missing_ok=True)
    except OSError:
        pass
    # 杀毒软件可能短暂占着文件（WinError 32），稍等重试
    _retry(lambda: os.replace(exe, old))
    try:
        _retry(lambda: os.replace(new, exe))
    except OSError:
        _retry(lambda: os.replace(old, exe))
        raise
    write_handoff(handoff_dir, window)
    launch_detached(str(exe), ["--updated-from", str(BUILD), *(extra_args or [])])


def write_handoff(ddir: Path, window: dict | None = None) -> None:
    """告诉新进程"你是更新后启动的"，以及更新前窗口开着没有，新进程照原样恢复。"""
    try:
        doc = {"from": BUILD, "at": time.time(), "pid": os.getpid(), "window": window or {}}
        (Path(ddir) / "update-handoff.json").write_text(json.dumps(doc), encoding="utf-8")
    except OSError:
        pass


def take_handoff(ddir: Path, max_age: float = 180) -> dict:
    p = Path(ddir) / "update-handoff.json"
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        p.unlink()
    except (OSError, ValueError):
        return {}
    if time.time() - float(doc.get("at", 0)) > max_age:
        return {}
    return doc


def child_env() -> dict[str, str]:
    """单文件 exe 会通过 _PYI_* / _MEIPASS2 告诉子进程自己的解压目录。新 exe 若继承这些变量，
    会去用旧进程的临时目录，旧进程一退出它就崩。PYINSTALLER_RESET_ENVIRONMENT=1 让它独立启动。"""
    env = {k: v for k, v in os.environ.items() if not (k.startswith("_PYI_") or k.startswith("_MEIPASS"))}
    if getattr(sys, "frozen", False):
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


def launch_detached(exe: str, args: list[str]) -> None:
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([exe, *args], env=child_env(), creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _retry(fn, attempts: int = 30, delay: float = 0.2):
    for i in range(attempts):
        try:
            return fn()
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(delay)


def cleanup_old() -> None:
    if not is_packaged():
        return
    old = Path(sys.executable).with_name(Path(sys.executable).name + ".old")
    for _ in range(20):  # 旧进程可能还没退干净
        try:
            old.unlink(missing_ok=True)
            return
        except OSError:
            time.sleep(0.5)
