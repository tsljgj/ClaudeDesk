#!/usr/bin/env python3
"""ClaudeDesk 命令行工具：Claude 会话用它给用户发"待决定 / 回答 / 通知"，并等待用户回复。

只用标准库。也被桌面程序 ClaudeDesk.exe 当作库导入（文件读写、加锁、id、时间戳都在这里，
两边共用同一份实现）。

用法（Python 3.10）：
    python desk.py post --kind decision --source <名> --title <标题> --body-file a.md \
        --option "方案A::说明" --option "方案B::说明" --recommended 1 --allow-text
    python desk.py wait --id <id> [--timeout 秒]                  # 收到回复退出 0，超时退出 2
    python desk.py responses [--source <名>] [--since <ts>]
    python desk.py list [--open] [--source <名>] [--json]
    python desk.py close --id <id> [--text 说明]                  # 用户已在对话里答了，把 decision 标成已处理；
                                                                  # 用户已在 ClaudeDesk 里答了则打印那条回复、退出 3
    python desk.py wait --followups --source <名> [--since <ts>] [--timeout 秒]
                                                                  # 等用户对这个来源的消息发"追问"：交出一条退出 0，超时退出 2
    python desk.py post --kind answer --reply-to <追问 id> ...    # 回答追问（也可以 --reply-to <消息 id> --question <追问原文>）
    python desk.py followups [--source <名>] [--since <ts>] [--json]

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
FOLLOWUPS = "followups.jsonl"
STATE = "state.json"
LOCKFILE = ".lock"
PIPE_DIR = r"\\.\pipe\\"  # 列命名管道（"程序在运行"、"有会话在听追问"两种标记）
KINDS = ("decision", "answer", "info")
FOLLOWUP_LOOKBACK = 24 * 3600  # wait --followups 不带 --since 时：这么久以内、还没交给会话的追问也算（会话没在听时用户发的）


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


def read_jsonl(path: Path, offset: int = 0, retry: float = 1.0) -> tuple[list[dict], int]:
    """从 offset 读到最后一个完整行；末尾的半行留到下次。坏行跳过。返回 (记录, 新 offset)。
    程序删除消息时会整份换掉 inbox.jsonl，换的那一瞬间 Windows 上 open 会 PermissionError：最多重试 retry 秒。"""
    path = Path(path)
    deadline = time.monotonic() + retry
    while True:
        try:
            with open(path, "rb") as f:
                f.seek(offset)
                data = f.read()
            break
        except FileNotFoundError:
            return [], 0
        except PermissionError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.02)
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
    if not isinstance(raw, (list, tuple)):  # 手写 / 别的工具写的记录里可能是数字、字符串
        return out
    for o in raw:
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
            r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, timeout=5,
                               stdin=subprocess.DEVNULL, **flags)
        except (OSError, subprocess.SubprocessError):
            return None
        out = (r.stdout or b"").decode("utf-8", "replace").strip()  # git 输出的路径是 UTF-8，不是系统的 ANSI 代码页
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
                 recommended=None, allow_text=False, priority="normal", repo=None,
                 reply_to=None, followup_id=None) -> dict:
    if kind not in KINDS:
        raise ValueError(f"kind 必须是 {KINDS} 之一")
    if not str(title or "").strip():
        raise ValueError("title 不能为空")
    opts = normalize_options(options)
    if recommended is not None:
        recommended = int(recommended)
        if not (1 <= recommended <= len(opts)):
            raise ValueError(f"--recommended 是从 1 开始的选项序号，应在 1..{len(opts)}")
    if kind == "decision":
        allow_text = True  # 决定一律可以写补充说明（没有选项时就只收文字）；allow_text 参数 / --allow-text 留着兼容
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
    if reply_to:  # 回答用户的追问：指向原来那条回答（followup_id：具体是哪条追问，知道的话）
        msg["reply_to"] = str(reply_to).strip()
        if followup_id:
            msg["followup_id"] = str(followup_id).strip()
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


# ---------------------------------------------------------------- 追问
# followups.jsonl 只追加，两种行：
#   追问  {"id", "ts", "msg": 被追问的消息 id, "source", "title", "text"}   用户在 ClaudeDesk 里发的
#         （回答、通知、已经回复过的决定都能追问；还在等回复的决定不能）
#   送达  {"delivered": 追问 id, "ts", "pid"}                         wait --followups 把它交给会话时记的
# 和 responses.jsonl 分开放：追问永远不会让 wait --id 醒来。

def write_followup(msg: dict, text: str, ddir: Path | None = None) -> dict:
    rec = {"id": new_id(), "ts": now_ts(), "msg": msg["id"], "source": msg.get("source", ""),
           "title": msg.get("title", ""), "text": text}
    append_jsonl(data_dir(ddir) / FOLLOWUPS, rec)
    return rec


def read_followups(ddir: Path | None = None) -> tuple[list[dict], set[str]]:
    """(追问, 已经交给会话的追问 id)。"""
    fus, sent = [], set()
    for r in read_all(data_dir(ddir) / FOLLOWUPS):
        if r.get("delivered"):
            sent.add(str(r["delivered"]))
        elif r.get("id") and r.get("msg"):
            fus.append(dict(r, id=str(r["id"]), msg=str(r["msg"])))  # 手改 / 写坏的行里可能不是字符串：拿来当键（集合、字典）会出错
    return fus, sent


def pair_followups(followups: list[dict], replies: list[dict]) -> dict[str, dict]:
    """一条消息的追问，和回应它们的消息（reply_to 指向这条）配对，返回 {追问 id: 回应}。
    依次认：回应里写明的 followup_id → question 和追问原文一样 → 回应发出之前最早一条还没配上的追问。"""
    far = _dt.datetime.max.replace(tzinfo=_dt.timezone.utc)
    t = lambda x: parse_ts(x.get("ts")) or far  # noqa: E731
    fus, reps = sorted(followups, key=t), sorted(replies, key=t)
    out: dict[str, dict] = {}
    used: set[int] = set()
    rules = (lambda f, r: f.get("id") == r.get("followup_id"),
             lambda f, r: str(r.get("question") or "").strip() == str(f.get("text") or "").strip() != "",
             lambda f, r: t(f) <= t(r))
    for rule in rules:
        for i, r in enumerate(reps):
            hit = None if i in used else next((f for f in fus if f.get("id") not in out and rule(f, r)), None)
            if hit is not None:
                out[hit["id"]] = r
                used.add(i)
    return out


def _src_hash(source: str) -> str:
    import hashlib

    return hashlib.sha1(str(source).encode("utf-8")).hexdigest()[:8]


def listener_name(source: str, ddir: Path | None = None) -> str:
    """"有会话在听这个来源的追问"标记（Windows 命名管道）的名字：pipe_name 再加来源的短哈希。"""
    return pipe_name(ddir) + "-listen-" + _src_hash(source)


def _listen_lock(source: str, ddir: Path | None = None) -> Path:
    return data_dir(ddir) / (".listen-" + _src_hash(source))


@contextlib.contextmanager
def hold_listener(source: str, ddir: Path | None = None):
    """wait --followups 等待期间一直占着"有人在听"标记；进程退出（包括被杀掉）时系统自动放掉。yield 是否挂上了。
    Windows：开一个不接受连接的命名管道（listener_name），程序列一次管道目录就知道哪些来源有人在听；
    同名的可以开几个，全关掉才算没人听。其他系统：对 data/.listen-<哈希> 加共享锁。"""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)  # 自己的实例：改 restype 不影响同进程里别人用 windll
        k32.CreateNamedPipeW.restype = wintypes.HANDLE
        k32.CreateNamedPipeW.argtypes = [wintypes.LPCWSTR] + [wintypes.DWORD] * 6 + [ctypes.c_void_p]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        # PIPE_ACCESS_INBOUND, PIPE_REJECT_REMOTE_CLIENTS, PIPE_UNLIMITED_INSTANCES
        h = k32.CreateNamedPipeW("\\\\.\\pipe\\" + listener_name(source, ddir), 0x1, 0x8, 255, 0, 0, 0, None)
        ok = bool(h) and h != ctypes.c_void_p(-1).value
        try:
            yield ok
        finally:
            if ok:
                k32.CloseHandle(h)
    else:  # pragma: no cover - 非 Windows 兜底
        import fcntl

        fd = os.open(_listen_lock(source, ddir), os.O_RDWR | os.O_CREAT, 0o666)
        try:
            fcntl.flock(fd, fcntl.LOCK_SH)
            yield True
        finally:
            os.close(fd)


def listening_sources(sources, ddir: Path | None = None) -> set[str]:
    """这些来源里，哪些现在有 wait --followups 在听。Windows 上只列一次管道。"""
    sources = set(sources)
    if not sources:
        return set()
    if os.name == "nt":
        try:
            names = set(os.listdir(PIPE_DIR))
        except OSError:
            return set()
        base = pipe_name(ddir) + "-listen-"
        return {s for s in sources if base + _src_hash(s) in names}
    import fcntl  # pragma: no cover - 非 Windows 兜底：锁得上就是没人在听

    out = set()
    for s in sources:
        try:
            fd = os.open(_listen_lock(s, ddir), os.O_RDWR)
        except OSError:
            continue
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            out.add(s)
        finally:
            os.close(fd)
    return out


def _parent_alive(ppid: int) -> bool:
    """启动 wait 的进程（会话的后台 shell）还在不在。会话没了 wait 却还挂着的话，它会把追问领走，却没人回答。"""
    if os.name != "nt":  # pragma: no cover - 父进程没了会被过继给别的进程
        return os.getppid() == ppid
    import ctypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = ctypes.c_void_p
    k32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    k32.WaitForSingleObject.restype = ctypes.c_uint32
    k32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    h = k32.OpenProcess(0x00100000, False, ppid)  # SYNCHRONIZE
    if not h:
        return ctypes.get_last_error() == 5  # 拒绝访问：进程在，只是没权限
    try:
        return k32.WaitForSingleObject(h, 0) == 0x102  # WAIT_TIMEOUT：还在跑
    finally:
        k32.CloseHandle(h)


# ---------------------------------------------------------------- 桌面程序

def pipe_name(ddir: Path | None = None) -> str:
    """标记管道（"程序在运行"）的名字，带数据目录的哈希：只有看着这个数据目录的程序才算在运行
    （别的目录里的 desk.py 副本不会误以为有人在看它的 data/）。app.py 开管道时也用这个函数。"""
    import hashlib

    base = "ClaudeDesk-" + (os.environ.get("USERNAME") or os.environ.get("USER") or "user")
    d = Path(ddir).resolve() if ddir else data_dir().resolve()
    return base + "-data-" + hashlib.sha1(str(d).lower().encode("utf-8")).hexdigest()[:8]


def app_running(ddir: Path | None = None) -> bool:
    if os.name != "nt":
        return False
    try:
        return pipe_name(ddir) in os.listdir(PIPE_DIR)
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
    reply_to = fu_id = None
    if a.reply_to:  # 回答 id；也认追问 id（wait --followups 输出里的 "id"），认得出就记下具体是哪条追问
        fus, _ = read_followups(a.data)
        fu = next((f for f in fus if f.get("id") == a.reply_to), None)
        if fu is not None:
            reply_to, fu_id = fu["msg"], fu["id"]
            question = question or fu.get("text")
        elif find_message(a.reply_to, a.data) or any(f.get("msg") == a.reply_to for f in fus):
            reply_to = a.reply_to
        else:
            print(f"错误：--reply-to {a.reply_to} 既不是消息 id 也不是追问 id（用 wait --followups 输出里的 \"msg\"）",
                  file=sys.stderr)
            return 1
    try:
        repo = a.repo if a.repo is not None else detect_repo(folder_fallback=True)
        msg = make_message(a.kind, a.source, a.title, body, question, a.option,
                           a.recommended, a.allow_text, a.priority, repo=repo or None,
                           reply_to=reply_to, followup_id=fu_id)
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    post_message(msg, a.data)
    print(msg["id"])
    if not app_running(a.data):
        if not a.no_launch and not a.data and launch_app():
            print("（ClaudeDesk 没在运行，已启动）", file=sys.stderr)
        else:
            print(f"注意：没有 ClaudeDesk 在看这个数据目录（{data_dir(a.data)}），用户看不到这条消息"
                  + ("，wait 也等不到回复" if a.kind == "decision" else "") + "。"
                  "请用 ClaudeDesk 安装目录里的 desk.py（或用 --data / CLAUDEDESK_DATA 指向程序的数据目录），"
                  "并确认程序在运行。", file=sys.stderr)
    return 0


def cmd_wait(a) -> int:
    if a.followups:
        return cmd_wait_followups(a)
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
            if a.id:  # id 是唯一的：只按 id 认，--source 写得不一样也不能一直等下去
                if r.get("id") != a.id:
                    continue
                if a.source and r.get("source") != a.source:
                    print(f"（注意：这条回复的来源是 {r.get('source')!r}，不是 --source {a.source!r}；按 --id 认）",
                          file=sys.stderr)
            else:
                if a.source and r.get("source") != a.source:
                    continue
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


def _replies_by_msg(d: Path) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for m in read_all(d / INBOX):
        if m.get("reply_to"):
            out.setdefault(str(m["reply_to"]), []).append(m)
    return out


def _claim_followup(d: Path, source: str, since, answered: set[str]) -> dict | None:
    """这个来源最早一条还没交出去、也还没有回应的追问：在锁内记一条"送达"再返回，同一条不会交给两个 wait。
    answered：已经知道有回应的追问 id（用户把追问贴到对话里、会话已经 --reply-to 回过了），下次不用再查。"""
    fus, sent = read_followups(d)
    after = lambda f: (parse_ts(f.get("ts")) or since - _dt.timedelta(1)) >= since  # noqa: E731 - 时间坏了的不算
    todo = [f for f in fus if f.get("source") == source and f["id"] not in sent and f["id"] not in answered and after(f)]
    if not todo:
        return None
    reps = _replies_by_msg(d)
    for f in todo:
        if f["id"] in pair_followups([x for x in fus if x.get("msg") == f["msg"]], reps.get(f["msg"], [])):
            answered.add(f["id"])
    todo = sorted((f for f in todo if f["id"] not in answered), key=lambda f: parse_ts(f["ts"]))
    if not todo:
        return None
    with file_lock(d):
        _, sent = read_followups(d)
        f = next((x for x in todo if x["id"] not in sent), None)
        if f is None:
            return None
        append_jsonl(d / FOLLOWUPS, {"delivered": f["id"], "ts": now_ts(), "pid": os.getpid()}, locked=True)
    m = find_message(f["msg"], d) or {}
    out = {"id": f["id"], "ts": f.get("ts"), "msg": f["msg"], "kind": m.get("kind", ""), "source": f.get("source", ""),
           "title": m.get("title") or f.get("title", ""), "question": m.get("question") or ""}
    if m.get("kind") == "decision":  # 追问的是已经回复过的决定：带上用户当时的回复（选了什么、写了什么、是不是标为已处理 / 跳过）
        r = next((x for x in read_all(d / RESPONSES) if x.get("id") == f["msg"]), None) or {}
        out.update(choice=r.get("choice"), reply_text=r.get("text") or "")
        out.update({k: r[k] for k in ("resolved", "dismissed", "closed_by") if r.get(k)})
    out["text"] = f.get("text", "")
    return out


def cmd_wait_followups(a) -> int:
    """等用户在 ClaudeDesk 里对这个来源的消息发追问。一次交出一条（最早的）；会话没在听时发的（FOLLOWUP_LOOKBACK
    以内）也算，所以醒来到重新挂上之间用户又追问的不会漏。等的时候占着"有人在听"标记，界面靠它告诉用户会话在不在线。"""
    d = data_dir(a.data)
    if a.since:
        since = parse_ts(a.since)
        if since is None:
            print(f"错误：--since 不是时间：{a.since}", file=sys.stderr)
            return 1
    else:
        since = _dt.datetime.now().astimezone() - _dt.timedelta(seconds=FOLLOWUP_LOOKBACK)
    deadline = time.monotonic() + a.timeout if a.timeout and a.timeout > 0 else None
    if listening_sources([a.source], d):
        print(f"注意：来源 {a.source!r} 已经有一个 wait --followups 在跑；每条追问只会交给其中一个。", file=sys.stderr)
    ppid = os.getppid()
    watch, check_at = _parent_alive(ppid), time.monotonic() + 5  # 一开始就查不到父进程的（被 start 之类甩开了）不看它
    answered: set[str] = set()
    with hold_listener(a.source, d) as held:
        if not held:
            print("注意：没挂上\"在听\"标记，ClaudeDesk 会显示这个会话没在听（追问照样等得到）", file=sys.stderr)
        while True:
            hit = _claim_followup(d, a.source, since, answered)
            if hit:
                print(_dump(hit), flush=True)
                return 0
            if deadline is not None and time.monotonic() >= deadline:
                print("timeout：没有等到追问", file=sys.stderr)
                return 2
            if watch and time.monotonic() >= check_at:
                check_at = time.monotonic() + 5
                if not _parent_alive(ppid):
                    print("启动这个 wait 的进程已经退出（会话不在了），不再等追问", file=sys.stderr)
                    return 4
            time.sleep(a.interval)


def cmd_followups(a) -> int:
    d = data_dir(a.data)
    fus, sent = read_followups(d)
    since = parse_ts(a.since) if a.since else None
    reps = _replies_by_msg(d)
    pairs: dict[str, dict] = {}
    for mid in {f["msg"] for f in fus}:
        pairs.update(pair_followups([f for f in fus if f["msg"] == mid], reps.get(mid, [])))
    rows = []
    for f in fus:
        if a.source and f.get("source") != a.source:
            continue
        if since is not None:
            t = parse_ts(f.get("ts"))
            if t is None or t < since:
                continue
        rows.append((f, "answered" if f["id"] in pairs else "delivered" if f["id"] in sent else "stored"))
    if a.json:
        for f, st in rows:
            print(_dump(dict(f, status=st, reply=pairs[f["id"]].get("id")) if st == "answered" else dict(f, status=st)))
        return 0
    label = {"answered": "已回答", "delivered": "已送达", "stored": "未送达"}
    for f, st in rows:
        ts = str(f.get("ts", ""))[:19].replace("T", " ")
        text = " ".join(str(f.get("text", "")).split())
        print(f"{str(f['id']):24} {ts:19} {label[st]} [{f.get('source', '')}] {f.get('title', '')} ← {text[:80]}")
    print(f"共 {len(rows)} 条", file=sys.stderr)
    return 0


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
    except FileExistsError:  # 用户已经在 ClaudeDesk 里答了：把那条回复打出来，会话要按它执行或和对话里的答复核对
        old = next((r for r in read_all(d / RESPONSES) if r.get("id") == a.id), None)
        if old is not None:
            print(_dump(dict(old, title=old.get("title") or m.get("title", ""))))
        print("这条已经有回复了（用户已在 ClaudeDesk 里答复，见 stdout 那行 JSON）", file=sys.stderr)
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
        mid, kind = str(m.get("id", "?")), str(m.get("kind", "?"))  # 手写的记录里可能不是字符串
        print(f"{mid:24} {ts:19} {kind:8} {status:4} [{m.get('source', '')}] {m.get('title', '')}")
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
    sp.add_argument("--reply-to", help="回答用户的追问：wait --followups 输出里的 id（追问 id，--question 自动填追问原文）"
                                       "或 msg（被追问的消息 id，--question 自己放追问原文）")
    sp.add_argument("--option", action="append", default=[], help='选项 "label::description"，可重复')
    sp.add_argument("--recommended", type=int, help="推荐的选项序号（从 1 开始）")
    sp.add_argument("--allow-text", action="store_true", help="（已不需要，留着兼容）decision 一律可以写补充文字")
    sp.add_argument("--priority", choices=("normal", "high"), default="normal")
    sp.add_argument("--no-launch", action="store_true", help="程序没在运行时不要自动启动")
    sp.set_defaults(func=cmd_post)

    sp = sub.add_parser("wait", help="阻塞到出现对应回复（--followups：追问）；超时退出码 2")
    sp.add_argument("--followups", action="store_true",
                    help="等用户对这个 --source 的消息发追问：交出一条（一行 JSON）退出 0；等的时候 ClaudeDesk 显示会话在线")
    sp.add_argument("--source", help="不带 --id 时：只等这个来源的回复（带 --id 时只按 id 认）")
    sp.add_argument("--id", help="只等这条消息的回复（已有回复则立即返回）")
    sp.add_argument("--since", help="不带 --id 时：只认这个时间之后的回复（默认=开始等待的时刻；"
                                    "--followups 默认是 24 小时内还没交给会话的追问）")
    sp.add_argument("--timeout", type=float, default=0, help="秒；0 = 一直等")
    sp.add_argument("--interval", type=float, default=1.0, help="轮询间隔秒")
    sp.set_defaults(func=cmd_wait)

    sp = sub.add_parser("close", help="用户已在对话里答复：把 decision 标成已处理（写一条 closed_by=claude 的回复）；"
                                      "用户已在 ClaudeDesk 里回复过则打印那条回复，退出码 3")
    sp.add_argument("--id", required=True)
    sp.add_argument("--text", help="说明，例如：用户在对话里选了 B")
    sp.set_defaults(func=cmd_close)

    sp = sub.add_parser("responses", help="列出回复（每行一个 JSON）")
    sp.add_argument("--source")
    sp.add_argument("--id")
    sp.add_argument("--since")
    sp.set_defaults(func=cmd_responses)

    sp = sub.add_parser("followups", help="列出追问（已回答 / 已送达 = 交给了会话 / 未送达）")
    sp.add_argument("--source")
    sp.add_argument("--since")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_followups)

    sp = sub.add_parser("list", help="列出消息")
    sp.add_argument("--open", action="store_true", help="只看还没回复的 decision")
    sp.add_argument("--source")
    sp.add_argument("--repo", help="只看这个仓库的")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(func=cmd_list)

    a = p.parse_args(argv)
    if a.cmd == "wait" and a.followups and (not a.source or a.id):
        p.error("wait --followups 需要 --source（不带 --id）")
    if a.cmd == "wait" and not a.source and not a.id:
        p.error("wait 需要 --source 或 --id")
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
