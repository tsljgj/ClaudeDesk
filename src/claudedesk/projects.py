"""从 Claude Code 自己的会话记录里找出你在哪些仓库里用过 Claude，拿来认旧消息属于哪个仓库。

Claude Code 把每个项目的会话存在 <配置目录>/projects/<编码后的路径>/<会话>.jsonl，
每行 JSON 里带着当时的工作目录 "cwd"。取每个项目最近一个会话的 cwd，
再看它是哪个 git 仓库（和 desk.py 发消息时的识别方法一样），就得到一份"你的仓库"名单。
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path, PurePosixPath, PureWindowsPath

import desk

_WIN_PATH = re.compile(r"^[A-Za-z]:[\\/]|\\")


def claude_dirs() -> list[Path]:
    """可能的 Claude Code 配置目录：环境变量 CLAUDE_CONFIG_DIR 指的，加上默认的 ~/.claude。"""
    out = []
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        out.append(Path(env))
    out.append(Path.home() / ".claude")
    seen, uniq = set(), []
    for d in out:
        k = str(d.resolve()) if d.exists() else str(d)
        if k not in seen:
            seen.add(k)
            uniq.append(d)
    return uniq


def session_cwd(project_dir: Path, max_lines: int = 200) -> str | None:
    """这个项目最近一个会话记录里的工作目录。"""
    try:
        files = sorted(project_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return None
    for f in files[:3]:
        try:
            with open(f, "r", encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh):
                    if i >= max_lines:
                        break
                    if '"cwd"' not in line:
                        continue
                    try:
                        cwd = json.loads(line).get("cwd")
                    except (ValueError, AttributeError):
                        continue
                    if isinstance(cwd, str) and cwd.strip():
                        return cwd.strip()
        except OSError:
            continue
    return None


def name_from_cwd(cwd: str) -> str | None:
    """工作目录 -> 项目名：worktree（.claude/worktrees/xxx）算回主目录；家目录、盘符根目录不算项目。"""
    p = PureWindowsPath(cwd) if _WIN_PATH.search(cwd) else PurePosixPath(cwd)
    parts = list(p.parts)
    low = [x.lower() for x in parts]
    for i in range(len(low) - 1):
        if low[i] == ".claude" and low[i + 1] == "worktrees":
            parts = parts[:i]
            break
    if len(parts) <= 1:
        return None
    name = parts[-1]
    home = Path.home()
    if name.lower() in {home.name.lower(), "users", "home", "desktop", "documents", "downloads"}:
        return None
    return name or None


def discover(dirs: list[Path] | None = None, cache: dict[str, str | None] | None = None) -> set[str]:
    """所有用过 Claude Code 的项目名（优先用 git 仓库名，目录不在了就用目录名）。cache: cwd -> 名字，跨次调用复用。"""
    cache = {} if cache is None else cache
    names: set[str] = set()
    for base in dirs or claude_dirs():
        proj = base / "projects"
        try:
            subs = [d for d in proj.iterdir() if d.is_dir()]
        except OSError:
            continue
        for d in subs:
            cwd = session_cwd(d)
            if not cwd:
                continue
            if cwd not in cache:
                name = None
                try:
                    if Path(cwd).is_dir():
                        name = desk.detect_repo(cwd)
                except OSError:
                    name = None
                cache[cwd] = name or name_from_cwd(cwd)
            if cache[cwd]:
                names.add(cache[cwd])
    return names
