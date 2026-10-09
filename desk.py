#!/usr/bin/env python3
"""ClaudeDesk 命令行工具：Claude 会话用它给用户发"待决定 / 回答 / 通知"，并等待用户回复。

只用标准库。也被桌面程序 ClaudeDesk.exe 当作库导入（文件读写、加锁、id、时间戳都在这里，
两边共用同一份实现）。

用法（Python 3.10）：
    python desk.py post --kind decision --source <名> --title <标题> --body-file a.md \
        --option "方案A::说明" --option "方案B::说明" --recommended 1 --allow-text
    python desk.py wait --source <名> --id <id> [--timeout 秒]     # 收到回复退出 0，超时退出 2
    python desk.py responses [--source <名>] [--since <ts>]
    python desk.py list [--open] [--source <名>] [--json]
    python desk.py close --id <id> [--text 说明]                  # 用户已在对话里答了，把 decision 标成已处理

数据目录默认是本文件旁边的 data/，可用环境变量 CLAUDEDESK_DATA 改。
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INBOX = "inbox.jsonl"
RESPONSES = "responses.jsonl"
STATE = "state.json"
LOCKFILE = ".lock"
KINDS = ("decision", "answer", "info")


# ---------------------------------------------------------------- 路径与时间

def data_dir(override: str | os.PathLike | None = None) -> Path:
    if override:
        d = Path(override)
    elif os.environ.get("CLAUDEDESK_DATA"):
        d = Path(os.environ["CLAUDEDESK_DATA"])
    else:
        d = ROOT / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def now_ts() -> str:
    """本地时间、带时区、精确到毫秒，例如 2026-10-03T14:22:05.123+08:00。"""
    return _dt.datetime.now().astimezone().isoformat(timespec="milliseconds")


def parse_ts(s: str | None) -> _dt.datetime | None:
    if not s:
        return None
    try:
        t = _dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.astimezone()  # 无时区的按本地时间理解
    return t


def new_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)


# ---------------------------------------------------------------- 加锁与 JSONL

@contextlib.contextmanager
def file_lock(directory: Path, timeout: float = 20.0):
    """跨进程互斥：对 data/.lock 的第 0 字节加锁（Windows: msvcrt.locking；其他系统: fcntl）。"""
    path = Path(directory) / LOCKFILE
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o666)
    try:
        deadline = time.monotonic() + timeout
        if os.name == "nt":
            import msvcrt

            while True:
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        raise TimeoutError(f"拿不到锁 {path}")
                    time.sleep(0.02)
            try:
                yield
            finally:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:  # pragma: no cover - 非 Windows 兜底
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        n = os.write(fd, view)
        view = view[n:]


def append_jsonl(path: Path, obj: dict, *, locked: bool = False) -> None:
    """原子追加一行。持有 data/.lock 时写；若文件末尾是别人崩溃留下的半行，先补换行。"""
    path = Path(path)
    line = (json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    ctx = contextlib.nullcontext() if locked else file_lock(path.parent)
    with ctx:
        flags = os.O_RDWR | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0)
        fd = os.open(path, flags, 0o666)
        try:
            size = os.fstat(fd).st_size
            if size > 0:
                os.lseek(fd, size - 1, os.SEEK_SET)
                if os.read(fd, 1) != b"\n":
                    line = b"\n" + line
            _write_all(fd, line)
            try:
                os.fsync(fd)
            except OSError:
                pass
        finally:
            os.close(fd)


def read_jsonl(path: Path, offset: int = 0) -> tuple[list[dict], int]:
    """从 offset 读到最后一个完整行；末尾的半行留到下次。坏行跳过。返回 (记录, 新 offset)。"""
    path = Path(path)
    try:
        with open(path, "rb") as f:
            f.seek(offset)
            data = f.read()
    except FileNotFoundError:
        return [], 0
    end = data.rfind(b"\n")
    if end < 0:
        return [], offset
    out = []
    for raw in data[: end + 1].splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out, offset + end + 1


def read_all(path: Path) -> list[dict]:
    return read_jsonl(path, 0)[0]


# ---------------------------------------------------------------- 消息与回复

def normalize_options(raw) -> list[dict]:
    out = []
    for o in raw or []:
        if isinstance(o, str):
            label, _, desc = o.partition("::")
            out.append({"label": label.strip(), "description": desc.strip()})
        elif isinstance(o, dict) and str(o.get("label", "")).strip():
            out.append({"label": str(o["label"]).strip(), "description": str(o.get("description") or "").strip()})
    return out


def detect_repo(cwd: str | os.PathLike | None = None, folder_fallback: bool = False) -> str | None:
    """当前目录所在的 git 仓库名，用来把消息按仓库分开。
    依次看：origin 远程地址里的仓库名 → 主仓库目录名（worktree 也认得出是哪个仓库）→ 工作区根目录名。
    不在 git 仓库里（或没装 git）：folder_fallback 时用当前目录名（家目录、盘符根目录除外），否则返回 None。"""
    flags = {"creationflags": 0x08000000} if os.name == "nt" else {}  # CREATE_NO_WINDOW

    def git(*args: str) -> str | None:
        try:
            r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=5,
                               stdin=subprocess.DEVNULL, **flags)
        except (OSError, subprocess.SubprocessError):
            return None
        out = (r.stdout or "").strip()
        return out if r.returncode == 0 and out else None

    if git("rev-parse", "--is-inside-work-tree") != "true":
        if not folder_fallback:
            return None
        here = Path(cwd or os.getcwd()).resolve()
        if here == Path.home().resolve() or here.parent == here or not here.name:
            return None
        return here.name
    url = git("config", "--get", "remote.origin.url")
    if url:
        name = re.split(r"[/:\\]", url.rstrip("/\\"))[-1]
        name = name[:-4] if name.lower().endswith(".git") else name
        if name:
            return name
    common = git("rev-parse", "--git-common-dir")
    if common:
        p = Path(common)
        if not p.is_absolute():
            p = Path(cwd or os.getcwd()) / p
        p = p.resolve()
        repo = p.parent if p.name == ".git" else p
        name = repo.name[:-4] if repo.name.lower().endswith(".git") else repo.name
        if name:
            return name
    top = git("rev-parse", "--show-toplevel")
    return Path(top).name if top else None


def make_message(kind, source, title, body="", question=None, options=None,
                 recommended=None, allow_text=False, priority="normal", repo=None) -> dict:
    if kind not in KINDS:
        raise ValueError(f"kind 必须是 {KINDS} 之一")
    if not str(title or "").strip():
        raise ValueError("title 不能为空")
    opts = normalize_options(options)
    if recommended is not None:
        recommended = int(recommended)
        if not (1 <= recommended <= len(opts)):
            raise ValueError(f"--recommended 是从 1 开始的选项序号，应在 1..{len(opts)}")
    if kind == "decision" and not opts:
        allow_text = True  # 没有选项就只能文字回复
    msg = {
        "id": new_id(),
        "ts": now_ts(),
        "source": str(source or "unknown"),
        "kind": kind,
        "title": str(title).strip(),
        "body": body or "",
        "priority": "high" if priority == "high" else "normal",
    }
    if repo:
        msg["repo"] = str(repo).strip()
    if question:
        msg["question"] = question
    if kind == "decision":
        msg["options"] = opts
        msg["recommended"] = recommended
        msg["allow_text"] = bool(allow_text)
    elif opts:
        msg["options"] = opts
    return msg


def post_message(msg: dict, ddir: Path | None = None) -> str:
    d = data_dir(ddir)
    append_jsonl(d / INBOX, msg)
    return msg["id"]


def find_message(msg_id: str, ddir: Path | None = None) -> dict | None:
    for m in read_all(data_dir(ddir) / INBOX):
        if m.get("id") == msg_id:
            return m
    return None


def write_response(msg_id: str, choice: str | None, text: str, source: str,
                   ddir: Path | None = None, extra: dict | None = None) -> dict:
    """写一条回复。同一 id 已有回复时拒绝（在锁内检查，跨进程也不会重复）。"""
    d = data_dir(ddir)
    rec = {"id": msg_id, "ts": now_ts(), "choice": choice, "text": text or "", "source": source}
    if extra:
        rec.update(extra)
    with file_lock(d):
        for r in read_all(d / RESPONSES):
            if r.get("id") == msg_id:
                raise FileExistsError("这条已经回复过了")
        append_jsonl(d / RESPONSES, rec, locked=True)
    return rec


# ---------------------------------------------------------------- 桌面程序

def pipe_name(ddir: Path | None = None) -> str:
    """单实例 / 控制通道的命名管道名。默认数据目录用固定名，其他数据目录加哈希（便于隔离测试）。"""
    import hashlib

    base = "ClaudeDesk-" + (os.environ.get("USERNAME") or "user")
    d = Path(ddir).resolve() if ddir else data_dir().resolve()
    if d == (ROOT / "data").resolve():
        return base
    return base + "-" + hashlib.sha1(str(d).lower().encode("utf-8")).hexdigest()[:8]


def app_running(ddir: Path | None = None) -> bool:
    if os.name != "nt":
        return False
    try:
        return pipe_name(ddir) in os.listdir(r"\\.\pipe\\")
    except OSError:
        return False


def launch_app() -> bool:
    exe = ROOT / "ClaudeDesk.exe"
    if not exe.exists() or os.name != "nt":
        return False
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([str(exe), "--minimized"], cwd=str(ROOT), creationflags=flags,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     close_fds=True)
    return True


# ---------------------------------------------------------------- 命令行

def _read_text_file(p: str) -> str:
    raw = Path(p).read_bytes()
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace")


def _read_stdin() -> str:
    raw = sys.stdin.buffer.read()
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", errors="replace")


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def cmd_post(a) -> int:
    if a.body_file:
        body = _read_text_file(a.body_file)
    elif a.body == "-":
        body = _read_stdin()
    else:
        body = a.body or ""
    question = a.question
    if a.question_file:
        question = _read_text_file(a.question_file)
    try:
        repo = a.repo if a.repo is not None else detect_repo(folder_fallback=True)
        msg = make_message(a.kind, a.source, a.title, body, question, a.option,
                           a.recommended, a.allow_text, a.priority, repo=repo or None)
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    post_message(msg, a.data)
    print(msg["id"])
    if not a.no_launch and not app_running(a.data):
        if not a.data and launch_app():
            print("（ClaudeDesk 没在运行，已启动）", file=sys.stderr)
        else:
            print("（注意：ClaudeDesk 没在运行）", file=sys.stderr)
    return 0


def cmd_wait(a) -> int:
    d = data_dir(a.data)
    path = d / RESPONSES
    since = parse_ts(a.since) if a.since else None
    if not a.id and since is None:
        since = _dt.datetime.now().astimezone()
    deadline = time.monotonic() + a.timeout if a.timeout and a.timeout > 0 else None
    offset = 0
    title_cache: dict[str, str] = {}
    while True:
        recs, offset2 = read_jsonl(path, offset)
        if offset2 < offset:  # 文件被换掉了
            recs, offset2 = read_jsonl(path, 0)
        offset = offset2
        hits = []
        for r in recs:
            if a.source and r.get("source") != a.source:
                continue
            if a.id:
                if r.get("id") != a.id:
                    continue
            else:
                t = parse_ts(r.get("ts"))
                if t is None or t < since:
                    continue
            hits.append(r)
        if hits:
            for r in hits:
                if "title" not in r:
                    if r.get("id") not in title_cache:
                        m = find_message(r.get("id"), d)
                        title_cache[r.get("id")] = (m or {}).get("title", "")
                    r = dict(r, title=title_cache[r.get("id")])
                print(_dump(r), flush=True)
            return 0
        if deadline is not None and time.monotonic() >= deadline:
            print("timeout：没有等到回复", file=sys.stderr)
            return 2
        time.sleep(a.interval)


def cmd_close(a) -> int:
    """用户在对话里已经答了：替他把这条 decision 标成已处理，界面上不再显示"待决定"。"""
    d = data_dir(a.data)
    m = find_message(a.id, d)
    if m is None:
        print(f"错误：没有这条消息 {a.id}", file=sys.stderr)
        return 1
    try:
        rec = write_response(a.id, None, a.text or "（已在对话中处理）", m.get("source", ""), d,
                             extra={"title": m.get("title", ""), "closed_by": "claude"})
    except FileExistsError:
        print("这条已经有回复了", file=sys.stderr)
        return 3
    print(_dump(rec))
    return 0


def cmd_responses(a) -> int:
    since = parse_ts(a.since) if a.since else None
    for r in read_all(data_dir(a.data) / RESPONSES):
        if a.source and r.get("source") != a.source:
            continue
        if a.id and r.get("id") != a.id:
            continue
        if since is not None:
            t = parse_ts(r.get("ts"))
            if t is None or t < since:
                continue
        print(_dump(r))
    return 0


def cmd_list(a) -> int:
    d = data_dir(a.data)
    msgs = read_all(d / INBOX)
    answered = {r.get("id"): r for r in read_all(d / RESPONSES)}
    rows = []
    for m in msgs:
        if a.source and m.get("source") != a.source:
            continue
        if a.repo and m.get("repo") != a.repo:
            continue
        is_open = m.get("kind") == "decision" and m.get("id") not in answered
        if a.open and not is_open:
            continue
        rows.append((m, is_open))
    if a.json:
        for m, is_open in rows:
            out = dict(m)
            out["status"] = "open" if is_open else ("answered" if m.get("id") in answered else "-")
            if m.get("id") in answered:
                out["response"] = answered[m["id"]]
            print(_dump(out))
        return 0
    for m, is_open in rows:
        status = "待决定" if is_open else ("已回复" if m.get("id") in answered else "")
        ts = str(m.get("ts", ""))[:19].replace("T", " ")
        print(f"{m.get('id','?'):24} {ts:19} {m.get('kind','?'):8} {status:4} [{m.get('source','')}] {m.get('title','')}")
    print(f"共 {len(rows)} 条", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(prog="desk.py", description="ClaudeDesk 命令行工具")
    p.add_argument("--data", help="数据目录（默认 desk.py 旁边的 data/，或环境变量 CLAUDEDESK_DATA）")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("post", help="发一条消息，打印 id")
    sp.add_argument("--kind", required=True, choices=KINDS)
    sp.add_argument("--source", required=True, help="会话或项目名")
    sp.add_argument("--repo", help="消息属于哪个仓库（默认自动识别：当前目录所在 git 仓库的名字；不在仓库里就用当前目录名）")
    sp.add_argument("--title", required=True)
    sp.add_argument("--body", help="正文 Markdown；写 - 表示从 stdin 读")
    sp.add_argument("--body-file", help="正文 Markdown 文件（UTF-8）")
    sp.add_argument("--question", help="answer 类：用户的原问题")
    sp.add_argument("--question-file", help="answer 类：原问题放在文件里")
    sp.add_argument("--option", action="append", default=[], help='选项 "label::description"，可重复')
    sp.add_argument("--recommended", type=int, help="推荐的选项序号（从 1 开始）")
    sp.add_argument("--allow-text", action="store_true", help="decision 类允许用户写补充文字")
    sp.add_argument("--priority", choices=("normal", "high"), default="normal")
    sp.add_argument("--no-launch", action="store_true", help="程序没在运行时不要自动启动")
    sp.set_defaults(func=cmd_post)

    sp = sub.add_parser("wait", help="阻塞到出现对应回复；超时退出码 2")
    sp.add_argument("--source", help="只等这个来源的回复")
    sp.add_argument("--id", help="只等这条消息的回复（已有回复则立即返回）")
    sp.add_argument("--since", help="不带 --id 时：只认这个时间之后的回复（默认=开始等待的时刻）")
    sp.add_argument("--timeout", type=float, default=0, help="秒；0 = 一直等")
    sp.add_argument("--interval", type=float, default=1.0, help="轮询间隔秒")
    sp.set_defaults(func=cmd_wait)

    sp = sub.add_parser("close", help="用户已在对话里答复：把 decision 标成已处理（写一条 closed_by=claude 的回复）")
    sp.add_argument("--id", required=True)
    sp.add_argument("--text", help="说明，例如：用户在对话里选了 B")
    sp.set_defaults(func=cmd_close)

    sp = sub.add_parser("responses", help="列出回复（每行一个 JSON）")
    sp.add_argument("--source")
    sp.add_argument("--id")
    sp.add_argument("--since")
    sp.set_defaults(func=cmd_responses)

    sp = sub.add_parser("list", help="列出消息")
    sp.add_argument("--open", action="store_true", help="只看还没回复的 decision")
    sp.add_argument("--source")
    sp.add_argument("--repo", help="只看这个仓库的")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_list)

    a = p.parse_args(argv)
    if a.cmd == "wait" and not a.source and not a.id:
        p.error("wait 需要 --source 或 --id")
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
