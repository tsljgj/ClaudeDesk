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

协议 v2（按会话路由，见 docs/PROTOCOL.md）：post 自动记下调用它的会话（$CLAUDE_CODE_SESSION_ID、$CLAUDE_PID）。
    python desk.py listen [--session S] [--timeout 秒]             # 这个会话的回复 / 追问：攒一下一起交，每件一行 JSON，退出 0；
                                                                  # 已经有一个在听退出 5；会话进程没了不出声退出 4；超时退出 2
    python desk.py post --kind answer --title <标题> --question-from-chat --body-from-chat   # 正文 / 原问题取自会话记录
    python desk.py close --mine [--text 说明]                      # 这个会话所有还在等的决定都标成已处理
    python desk.py inbox [--repo R] [--adopt]                      # 已结束的会话留下、还没送达的回复 / 追问；--adopt 接过来
    python desk.py status                                          # 一行：这个会话的待决定、未送达、listen 在不在

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
DELIVERIES = "deliveries.jsonl"  # 协议 v2：送达标记（什么交给了哪个会话、什么时候）、会话接管、会话进程
STATE = "state.json"
LOCKFILE = ".lock"
PIPE_DIR = r"\\.\pipe\\"  # 列命名管道（"程序在运行"、"有会话在听追问"两种标记）
KINDS = ("decision", "answer", "info")
FOLLOWUP_LOOKBACK = 24 * 3600  # wait --followups 不带 --since 时：这么久以内、还没交给会话的追问也算（会话没在听时用户发的）
BATCH_QUIET, BATCH_MAX = 1.5, 6.0  # listen 看到第一件事后：再安静这么多秒（最多等到这么多秒）才交，接连几件一次交完、只叫醒会话一次
EXIT_TIMEOUT, EXIT_GONE, EXIT_DUP, EXIT_ANSWERED = 2, 4, 5, 3


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
                 reply_to=None, followup_id=None, session=None, session_pid=None, session_pid_start=None) -> dict:
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
    if session:  # 哪个 Claude Code 会话发的（回复、追问按它送回去）；session_pid_start 用来认出 pid 被别的进程重用
        msg["session"] = str(session).strip()
        if session_pid:
            msg["session_pid"] = int(session_pid)
            if session_pid_start:
                msg["session_pid_start"] = int(session_pid_start)
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
    if msg.get("session"):  # 原消息被删掉了也知道该送给哪个会话
        rec["session"] = msg["session"]
    append_jsonl(data_dir(ddir) / FOLLOWUPS, rec)
    return rec


def read_followups(ddir: Path | None = None) -> tuple[list[dict], set[str]]:
    """(追问, 已经交给会话的追问 id)。送达标记在 deliveries.jsonl；旧版写在 followups.jsonl 里的照样认。"""
    d = data_dir(ddir)
    fus, sent = [], set()
    for r in read_all(d / FOLLOWUPS):
        if r.get("delivered"):
            sent.add(str(r["delivered"]))
        elif r.get("id") and r.get("msg"):
            fus.append(dict(r, id=str(r["id"]), msg=str(r["msg"])))  # 手改 / 写坏的行里可能不是字符串：拿来当键（集合、字典）会出错
    sent.update(str(r["id"]) for r in read_all(d / DELIVERIES) if r.get("kind") == "followup" and r.get("id"))
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


# ---------------------------------------------------------------- 会话（协议 v2，详见 docs/PROTOCOL.md）
# 每条消息记着发它的 Claude Code 会话（session = $CLAUDE_CODE_SESSION_ID，session_pid = $CLAUDE_PID 即 claude.exe）。
# 决定的回复、追问都按会话送：一个会话只挂一个 listen，有事就攒一下一起交。
# deliveries.jsonl 只追加，三种行（kind）：
#   reply / followup  {"kind", "id": 消息 id / 追问 id, "session", "via": listen|wait|close|adopt, "ts", "pid"}  交给了哪个会话
#   adopt             {"kind", "from": 已结束的会话, "repo", "session": 接管的会话, "session_pid", "session_pid_start", "ts"}
#   pid               {"kind", "session", "session_pid", "session_pid_start", "ts"}  会话换了进程（恢复会话后 pid 会变）

def session_env() -> tuple[str | None, int | None]:
    """调用 desk.py 的 Claude Code 会话：(会话 id, claude.exe 的 pid)。Claude Code 给会话里的每条命令都设了这两个环境变量。"""
    sid = (os.environ.get("CLAUDE_CODE_SESSION_ID") or "").strip() or None
    pid = (os.environ.get("CLAUDE_PID") or "").strip()
    return sid, (int(pid) if pid.isdigit() else None)


def _session_arg(a) -> tuple[str | None, int | None]:
    """--session 优先，否则环境变量。pid 只在会话就是环境变量里那个时才算（别的会话的 pid 不知道）。"""
    env_s, env_pid = session_env()
    s = (getattr(a, "session", None) or "").strip() or env_s
    return s, (env_pid if s and s == env_s else None)


def _as_int(v) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    return int(v) if isinstance(v, str) and v.strip().isdigit() else None


_K32 = None


def _kernel32():
    global _K32
    if _K32 is None:
        import ctypes
        from ctypes import wintypes

        k = ctypes.WinDLL("kernel32", use_last_error=True)  # 自己的实例：改 argtypes 不影响别人
        k.OpenProcess.restype = wintypes.HANDLE
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.WaitForSingleObject.restype = wintypes.DWORD
        k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        _K32 = k
    return _K32


def proc_info(pid) -> tuple[bool, int | None]:
    """(进程还在不在, 创建时间)。创建时间用来认出 pid 被别的进程重用（Windows 上 pid 回收得很快）。"""
    pid = _as_int(pid)
    if not pid or pid <= 0:
        return False, None
    if os.name != "nt":  # 非 Windows：kill(0) 看在不在；Linux 再从 /proc 看状态和启动时间
        try:
            os.kill(pid, 0)
        except PermissionError:
            pass
        except OSError:
            return False, None
        try:  # 僵尸进程（已经退出、没被回收）kill(0) 也成功，要看状态；第 22 个字段是启动时间
            with open(f"/proc/{pid}/stat", "rb") as f:
                rest = f.read().rsplit(b")", 1)[1].split()
            if rest[0] in (b"Z", b"X"):
                return False, None
            return True, int(rest[19])
        except (OSError, IndexError, ValueError):  # macOS 等没有 /proc：不查创建时间
            return True, None
    import ctypes
    from ctypes import wintypes

    k = _kernel32()
    h = k.OpenProcess(0x00100000 | 0x1000, False, pid)  # SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ctypes.get_last_error() == 5, None  # 拒绝访问：进程在，只是没权限
    try:
        if k.WaitForSingleObject(h, 0) != 0x102:  # 不是 WAIT_TIMEOUT：已经退出（句柄还被谁拿着也算退出）
            return False, None
        ft = [wintypes.FILETIME() for _ in range(4)]
        if not k.GetProcessTimes(h, *[ctypes.byref(x) for x in ft]):
            return True, None
        return True, (ft[0].dwHighDateTime << 32) | ft[0].dwLowDateTime
    finally:
        k.CloseHandle(h)


def pid_alive(pid, start=None) -> bool:
    """会话进程还在：pid 在跑，而且（知道创建时间的话）还是当初那个进程。"""
    alive, t = proc_info(pid)
    return alive and (not start or t is None or t == _as_int(start))


def _hash(s: str, n: int = 12) -> str:
    import hashlib

    return hashlib.sha1(str(s).encode("utf-8")).hexdigest()[:n]


def session_marker(session: str, ddir: Path | None = None, base: str | None = None) -> str:
    """"这个会话有 listen 在跑"标记（命名管道）的名字。base：pipe_name(ddir)，批量算时传进来省得重复算。"""
    return (base or pipe_name(ddir)) + "-s-" + _hash(session)


def wait_marker(msg_id: str, ddir: Path | None = None, base: str | None = None) -> str:
    """"有 wait --id 在等这条决定"标记的名字（旧协议：一条决定一个 wait）。"""
    return (base or pipe_name(ddir)) + "-w-" + _hash(msg_id)


@contextlib.contextmanager
def hold_marker(name: str, ddir: Path | None = None, exclusive: bool = False):
    """等待期间一直占着一个标记，进程退出（包括被杀）时系统自动放掉。yield "ok" / "dup"（exclusive 而且已经有了）/ "fail"（没挂上）。
    Windows：一个不接受连接的命名管道，exclusive 时用 FILE_FLAG_FIRST_PIPE_INSTANCE，同名的只能有一个；程序列一次管道目录就知道都有谁。
    其他系统：对 data/.m-<哈希> 加锁（exclusive 用排他锁）。"""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateNamedPipeW.restype = wintypes.HANDLE
        k32.CreateNamedPipeW.argtypes = [wintypes.LPCWSTR] + [wintypes.DWORD] * 6 + [ctypes.c_void_p]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        # PIPE_ACCESS_INBOUND（+ FILE_FLAG_FIRST_PIPE_INSTANCE）、PIPE_REJECT_REMOTE_CLIENTS
        h = k32.CreateNamedPipeW("\\\\.\\pipe\\" + name, 0x1 | (0x00080000 if exclusive else 0), 0x8,
                                 1 if exclusive else 255, 0, 0, 0, None)
        ok = bool(h) and h != ctypes.c_void_p(-1).value
        err = 0 if ok else ctypes.get_last_error()
        try:
            yield "ok" if ok else ("dup" if exclusive and err in (5, 231) else "fail")  # 拒绝访问 / 管道忙：已经有一个了
        finally:
            if ok:
                k32.CloseHandle(h)
    else:  # pragma: no cover - 非 Windows 兜底
        import fcntl

        fd = os.open(data_dir(ddir) / (".m-" + _hash(name)), os.O_RDWR | os.O_CREAT, 0o666)
        try:
            try:
                fcntl.flock(fd, (fcntl.LOCK_EX | fcntl.LOCK_NB) if exclusive else fcntl.LOCK_SH)
                state = "ok"
            except OSError:
                state = "dup"
            yield state
        finally:
            os.close(fd)


def presence(ddir: Path | None = None, sources=(), sessions=(), ids=()) -> tuple[set, set, set]:
    """一次看全：(有 wait --followups 在听的来源, 有 listen 在跑的会话, 有 wait --id 在等的消息)。Windows 上只列一次管道目录。"""
    sources, sessions, ids = set(sources), set(sessions), set(ids)
    if os.name == "nt":
        try:
            names = set(os.listdir(PIPE_DIR))
        except OSError:
            return set(), set(), set()
        base = pipe_name(ddir)
        return ({s for s in sources if base + "-listen-" + _src_hash(s) in names},
                {s for s in sessions if session_marker(s, base=base) in names},
                {i for i in ids if wait_marker(i, base=base) in names})
    import fcntl  # pragma: no cover - 非 Windows 兜底：锁得上就是没人占着

    def held(name):
        try:
            fd = os.open(data_dir(ddir) / (".m-" + _hash(name)), os.O_RDWR)
        except OSError:
            return False
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False
        except OSError:
            return True
        finally:
            os.close(fd)
    base = pipe_name(ddir)
    return (listening_sources(sources, ddir), {s for s in sessions if held(session_marker(s, base=base))},
            {i for i in ids if held(wait_marker(i, base=base))})


def read_ledger(ddir: Path | None = None) -> dict:
    """deliveries.jsonl（加上 followups.jsonl 里旧版的送达标记）读成：
    reply / followup：{id: 送达记录}；adopt：{(旧会话, 仓库): 新会话}；pid：[(会话, pid, 创建时间, ts)]（按文件顺序）。"""
    d = data_dir(ddir)
    led = {"reply": {}, "followup": {}, "adopt": {}, "pid": []}
    for r in read_all(d / DELIVERIES):
        k = r.get("kind")
        if k in ("reply", "followup") and r.get("id"):
            led[k].setdefault(str(r["id"]), r)
        elif k in ("adopt", "pid") and r.get("session"):
            if k == "adopt" and r.get("from") and r["from"] != r["session"]:
                led["adopt"][(str(r["from"]), str(r.get("repo") or "").lower())] = str(r["session"])
            if _as_int(r.get("session_pid")):
                led["pid"].append((str(r["session"]), _as_int(r["session_pid"]), _as_int(r.get("session_pid_start")), r.get("ts")))
    for r in read_all(d / FOLLOWUPS):
        if r.get("delivered"):
            led["followup"].setdefault(str(r["delivered"]), {"kind": "followup", "id": r["delivered"], "ts": r.get("ts")})
    return led


def owner_of(session: str | None, adopt: dict, repo: str | None = None) -> str | None:
    """接管过的会话归到接管它的会话（可以接力：A → B → C）。接管按仓库算：(旧会话, 仓库) -> 新会话；没写仓库的接管管所有仓库。"""
    seen, repo = set(), str(repo or "").lower()
    while session and session not in seen:
        seen.add(session)
        nxt = adopt.get((session, repo)) or adopt.get((session, ""))
        if not nxt:
            break
        session = nxt
    return session


def session_pids(msgs, led: dict) -> dict[str, tuple]:
    """每个会话最新知道的 (pid, 创建时间)：消息里记的、接管 / pid 记录里的，按时间取最晚的。"""
    far = _dt.datetime.min.replace(tzinfo=_dt.timezone.utc)
    best: dict[str, tuple] = {}
    rows = [(m.get("session"), _as_int(m.get("session_pid")), _as_int(m.get("session_pid_start")), m.get("ts")) for m in msgs]
    for s, pid, start, ts in rows + led["pid"]:
        if not s or not pid:
            continue
        t = parse_ts(ts) or far
        if s not in best or t >= best[s][2]:
            best[s] = (pid, start, t)
    return {s: v[:2] for s, v in best.items()}


def _clip(s, n: int) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _reply_fields(r: dict) -> dict:
    """用户对决定的回复里会话要的那几样（标为已处理 / 跳过的只给标记，不给界面写的那句说明）。"""
    out = {"choice": r.get("choice")}
    if r.get("choice_index"):
        out["choice_index"] = r["choice_index"]
    flags = {k: True for k in ("resolved", "dismissed") if r.get(k)}
    if r.get("text") and not flags:
        out["text"] = r["text"]
    out.update(flags)
    return out


def pending_events(ddir: Path | None = None) -> list[dict]:
    """所有还没送达的事（按时间）：决定的回复、追问。每项 {"session": 归属会话（接管过的按接管后的）, "orig": 原会话, "repo",
    "key": (reply|followup, id), "ev": 交给会话的那一行（不带消息正文）}。没有会话信息的旧消息不算（它们走 wait --id / wait --followups）；
    会话自己 close 掉的不算；已经在对话里回应过的追问（会话 --reply-to 回过）也不算。"""
    d = data_dir(ddir)
    msgs = {str(m["id"]): m for m in read_all(d / INBOX) if m.get("id")}
    led = read_ledger(d)
    far = _dt.datetime.max.replace(tzinfo=_dt.timezone.utc)
    out = []

    def add(base, m, key, ev, ts):
        out.append({"session": owner_of(base, led["adopt"], m.get("repo")), "orig": base, "repo": m.get("repo") or "", "key": key,
                    "ev": ev, "_t": parse_ts(ts) or far})

    for r in read_all(d / RESPONSES):
        mid = str(r.get("id") or "")
        if not mid or mid in led["reply"] or r.get("closed_by") == "claude":
            continue
        m = msgs.get(mid) or {}
        base = m.get("session") or r.get("session")
        if base:
            add(base, m, ("reply", mid), {"ev": "reply", "id": mid, "title": r.get("title") or m.get("title", ""),
                                          **_reply_fields(r)}, r.get("ts"))
    all_fus = read_followups(d)[0]
    fus = [f for f in all_fus if str(f["id"]) not in led["followup"]]
    if fus:
        reps: dict[str, list[dict]] = {}
        for m in msgs.values():
            if m.get("reply_to"):
                reps.setdefault(str(m["reply_to"]), []).append(m)
        answered: set[str] = set()
        for mid in {str(f["msg"]) for f in fus}:
            if mid in reps:
                answered.update(pair_followups([x for x in all_fus if str(x.get("msg")) == mid], reps[mid]))
        resp = {str(r.get("id")): r for r in read_all(d / RESPONSES)} if any(
            (msgs.get(str(f["msg"])) or {}).get("kind") == "decision" for f in fus) else {}
        for f in fus:
            m = msgs.get(str(f["msg"])) or {}
            base = m.get("session") or f.get("session")
            if not base or f["id"] in answered:
                continue
            ev = {"ev": "followup", "id": f["id"], "msg": f["msg"], "kind": m.get("kind", ""),
                  "title": m.get("title") or f.get("title", "")}
            if m.get("question"):
                ev["question"] = _clip(m["question"], 200)  # 原问题（截短）：会话压缩过上下文、或者是接管来的，也知道问的是哪条
            if m.get("kind") == "decision":  # 追问的是回复过的决定：带上用户当时的回复
                r = resp.get(str(f["msg"])) or {}
                ev.update({("reply_text" if k == "text" else k): v for k, v in _reply_fields(r).items()})
                if r.get("closed_by"):
                    ev["closed_by"] = r["closed_by"]
            ev["text"] = f.get("text", "")
            add(base, m, ("followup", f["id"]), ev, f.get("ts"))
    out.sort(key=lambda e: e["_t"])
    for e in out:
        del e["_t"]
    return out


def claim_events(ddir: Path | None, events: list[dict], session: str | None, via: str, pre=()) -> list[dict]:
    """在 data/.lock 锁内再查一遍、记下送达，返回这次真正交出去的那几行：同一件事只交一次，几个进程同时来领也一样。
    pre：同一把锁里先写进 deliveries.jsonl 的记录（接管）。"""
    d = data_dir(ddir)
    with file_lock(d):
        for rec in pre:
            append_jsonl(d / DELIVERIES, rec, locked=True)
        led = read_ledger(d)
        got = [e for e in events if e["key"][1] not in led[e["key"][0]]]
        for e in got:
            append_jsonl(d / DELIVERIES, {"kind": e["key"][0], "id": e["key"][1], "session": session, "via": via,
                                          "ts": now_ts(), "pid": os.getpid()}, locked=True)
    return [e["ev"] for e in got]


def mark_delivered(ddir: Path | None, kind: str, item_id: str, session: str | None, via: str) -> bool:
    """记一条送达（已经有了就不记）。返回这次是不是新记的。"""
    return bool(claim_events(ddir, [{"key": (kind, item_id), "ev": {}}], session, via))


def _line(ev: dict) -> str:
    return json.dumps(ev, ensure_ascii=False, separators=(",", ":"))


def _files_sig(d: Path) -> tuple:
    """几个数据文件的 (大小, 修改时间)：没变就不用重算还有什么没送达。"""
    out = []
    for name in (INBOX, RESPONSES, FOLLOWUPS, DELIVERIES):
        try:
            st = os.stat(d / name)
            out.append((st.st_size, st.st_mtime_ns))
        except OSError:
            out.append(None)
    return tuple(out)


def _gone_sessions(d: Path, sessions, msgs=None, led=None) -> set[str]:
    """这些会话里已经结束的：知道它的进程、进程没了、也没有 listen 在跑。不知道 pid 的不算结束（说不准）。"""
    sessions = {s for s in sessions if s}
    if not sessions:
        return set()
    led = led if led is not None else read_ledger(d)
    pids = session_pids(msgs if msgs is not None else read_all(d / INBOX), led)
    live = presence(d, sessions=sessions)[1]
    return {s for s in sessions if s not in live and s in pids and not pid_alive(*pids[s])}


# ---------------------------------------------------------------- 会话记录（post --body-from-chat / --question-from-chat）
# Claude Code 把会话存在 <配置目录>/projects/<编码后的路径>/<会话 id>.jsonl，子 agent 的在 <会话 id>/subagents/*.jsonl。
# 一条 API 消息按内容块拆成好几行（thinking / text / tool_use 各一行，message.id 相同），用 parentUuid 串成链（回退、编辑会分叉）。
# 调用 desk.py 的那个 tool_use 在 desk.py 运行时已经写进去了：从它沿 parentUuid 往回走，就是"刚才在对话里写的"。

_WRAPPERS = ("<command-name>", "<command-message>", "<command-args>", "<local-command-stdout>", "<local-command-stderr>",
             "<local-command-caveat>", "<task-notification>", "<bash-input>", "<bash-stdout>", "<bash-stderr>",
             "<user-prompt-submit-hook>", "<system-reminder>", "Caveat:", "[Request interrupted",
             "This session is being continued")
_SIDE_BLOCKS = ("<ide_", "<system-reminder>")  # 用户消息里 IDE 附带的"打开的文件 / 选中的文字"、系统提示：不是用户写的


class ChatError(LookupError):
    pass


def _config_dirs() -> list[Path]:
    """Claude Code 的配置目录：设了 CLAUDE_CONFIG_DIR 就只看它（会话记录就在那里），否则 ~/.claude。"""
    return [Path(os.environ["CLAUDE_CONFIG_DIR"])] if os.environ.get("CLAUDE_CONFIG_DIR") else [Path.home() / ".claude"]


def find_transcripts(session: str) -> list[Path]:
    """这个会话的记录：主记录（按修改时间新的在前），再加上它的子 agent 的（子 agent 和主会话的会话 id 一样）。"""
    if not session or not re.fullmatch(r"[A-Za-z0-9_.-]+", session):
        return []
    mtime = lambda p: p.stat().st_mtime  # noqa: E731
    for base in _config_dirs():
        try:
            main = sorted((base / "projects").glob(f"*/{session}.jsonl"), key=mtime, reverse=True)
        except OSError:
            continue
        if main:
            out = []
            for p in main:
                out.append(p)
                try:
                    out += sorted((p.parent / session / "subagents").glob("*.jsonl"), key=mtime, reverse=True)[:8]
                except OSError:
                    pass
            return out
    return []


def _tail_records(path: Path, nbytes: int) -> tuple[list[dict], bool]:
    """文件最后 nbytes 字节里的记录（第一行不完整的丢掉）。返回 (记录, 是不是整个文件)。"""
    size = path.stat().st_size
    start = max(0, size - nbytes)
    with open(path, "rb") as f:
        f.seek(start)
        data = f.read()
    if start:
        data = data[data.find(b"\n") + 1:] if b"\n" in data else b""
    out = []
    for raw in data.splitlines():
        try:
            r = json.loads(raw.decode("utf-8", "replace"))
        except json.JSONDecodeError:
            continue
        if isinstance(r, dict):
            out.append(r)
    return out, start == 0


def _blocks(r: dict) -> list[dict]:
    c = (r.get("message") or {}).get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return [b for b in c if isinstance(b, dict)] if isinstance(c, list) else []


def _user_text(r: dict) -> str | None:
    """真正由用户写的消息的文字；工具结果、后台任务通知、命令外壳、系统 / 元信息、压缩摘要返回 None。"""
    if r.get("type") != "user" or r.get("isMeta") or r.get("isCompactSummary") or r.get("isVisibleInTranscriptOnly"):
        return None
    o = r.get("origin")
    if isinstance(o, dict) and o.get("kind") not in (None, "human"):  # 新版记了来源：只认人发的
        return None
    bl = _blocks(r)
    if not bl or any(b.get("type") == "tool_result" for b in bl):
        return None
    texts = [str(b.get("text") or "") for b in bl if b.get("type") == "text"]
    if texts and texts[0].lstrip().startswith(_WRAPPERS):
        return None
    text = "\n\n".join(t.strip() for t in texts if t.strip() and not t.lstrip().startswith(_SIDE_BLOCKS)).strip()
    return text or None


def _anchor(recs: list[dict]) -> tuple[dict, int] | None:
    """调用 desk.py 的那个 tool_use（输入里有 -from-chat 的最新一个）：(记录, 它在记录里是第几块)。"""
    for r in reversed(recs):
        if r.get("type") != "assistant":
            continue
        for i, b in enumerate(_blocks(r)):
            if b.get("type") == "tool_use" and "-from-chat" in json.dumps(b.get("input"), ensure_ascii=False):
                return r, i
    return None


def _chat_from(recs: list[dict], anchor: tuple[dict, int] | None) -> tuple[str, str | None, bool]:
    """从 anchor 沿 parentUuid 往回走到最近一条用户消息。返回 (刚写的回答, 用户的问题, 走完了没有)。
    回答 = 最近一段连续的文字（中间隔着工具调用、工具结果的算两段，只要最后一段：前面多半是"我先看看…"这类过程话）。"""
    by = {r["uuid"]: r for r in recs if isinstance(r.get("uuid"), str)}
    if anchor is None:
        last = next((r for r in reversed(recs) if r.get("type") in ("user", "assistant")), None)
        if last is None:
            return "", None, False
        anchor = (last, len(_blocks(last)))
    cur, cut = anchor
    run: list[str] = []
    body, question, seen = None, None, set()
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        q = _user_text(cur)
        if q is not None or cur.get("isCompactSummary"):
            question = q
            break
        t = cur.get("type")
        msg = cur.get("message") or {}
        if t == "assistant" and not cur.get("isApiErrorMessage") and msg.get("model") != "<synthetic>":
            bl = _blocks(cur)[:cut] if cut is not None else _blocks(cur)
            for b in reversed(bl):
                if b.get("type") == "text" and str(b.get("text") or "").strip():
                    run.insert(0, str(b["text"]).strip())
                elif b.get("type") == "tool_use" and run and body is None:
                    body = "\n\n".join(run)
        elif t == "user" and run and body is None:  # 工具结果、通知：一段文字到头了
            body = "\n\n".join(run)
        cut = None
        p = cur.get("parentUuid")
        if not p:
            return body or "\n\n".join(run), None, True  # 到了会话开头
        cur = by.get(p)
        if cur is None:
            return body or "\n\n".join(run), None, False  # 链出了读进来的这一段：要多读一些
    return body or "\n\n".join(run), question, True


def chat_text(session: str | None, want: str) -> str:
    """want = "body"：会话刚在对话里写的回答；"question"：用户最近一条消息原文。找不到抛 ChatError（带原因）。"""
    if not session:
        raise ChatError("不知道是哪个会话（没有 $CLAUDE_CODE_SESSION_ID，也没给 --session）")
    paths = find_transcripts(session)
    if not paths:
        raise ChatError(f"没找到会话记录 projects/*/{session}.jsonl")
    n, best, errs = 1 << 21, None, []
    for path in paths:  # 这次调用在哪份记录里（主会话，还是某个子 agent）：看哪份末尾有最新的那个 tool_use
        try:
            recs, whole = _tail_records(path, n)
        except OSError as e:
            errs.append(str(e))
            continue
        anc = _anchor(recs)
        t = parse_ts(anc[0].get("timestamp")) if anc else None
        if best is None or (t is not None and (best[0] is None or t > best[0])):
            best = (t, path, recs, whole, anc)
    if best is None:
        raise ChatError("读不了会话记录：" + "; ".join(errs))
    _, path, recs, whole, anc = best
    while True:
        body, question, done = _chat_from(recs, anc)
        if done or whole:
            break
        n *= 4  # 链伸出了读进来的这一段：多读一些（最后读整个文件）
        recs, whole = _tail_records(path, n)
        anc = _anchor(recs) if anc is not None else None
    text = (body if want == "body" else question) or ""
    if not text.strip():
        raise ChatError("会话记录里刚才那段没有文字（回答要先写在对话里，紧接着在同一条消息里调用 post）"
                        if want == "body" else "会话记录里没找到用户发的消息")
    return text.strip()


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


def _chat_or_fail(session, want: str) -> str:
    """从会话记录取文字；刚写进去的可能还没落盘：最多再等 1.2 秒。"""
    for i in range(4):
        try:
            return chat_text(session, want)
        except ChatError:
            if i == 3:
                raise
            time.sleep(0.4)
    raise AssertionError  # pragma: no cover


def cmd_post(a) -> int:
    session, spid = _session_arg(a)
    try:
        if a.body_from_chat:
            body = _chat_or_fail(session, "body")
        elif a.body_file:
            body = _read_text_file(a.body_file)
        elif a.body == "-":
            body = _read_stdin()
        else:
            body = a.body or ""
    except ChatError as e:
        print(f"错误：--body-from-chat 没取到正文：{e}。改用 --body-file <文件>。", file=sys.stderr)
        return 1
    question = a.question
    if a.question_file:
        question = _read_text_file(a.question_file)
    elif a.question_from_chat and not a.question:
        try:
            question = _chat_or_fail(session, "question")
        except ChatError as e:
            print(f"错误：--question-from-chat 没取到用户的问题：{e}。改用 --question '<原文>' 或 --question-file <文件>。",
                  file=sys.stderr)
            return 1
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
        source = a.source or repo or Path.cwd().name or "unknown"  # 只是显示用的名字；送回复按会话
        msg = make_message(a.kind, source, a.title, body, question, a.option,
                           a.recommended, a.allow_text, a.priority, repo=repo or None,
                           reply_to=reply_to, followup_id=fu_id, session=session, session_pid=spid,
                           session_pid_start=proc_info(spid)[1] if spid else None)
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1
    post_message(msg, a.data)
    print(msg["id"])
    if session and session not in presence(a.data, sessions=[session])[1]:
        print("提示：这个会话没有 listen 在跑；要收到回复 / 追问，后台启动一个 desk.py listen", file=sys.stderr)
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
    if not a.id:
        return _wait_responses(a, d)
    with hold_marker(wait_marker(a.id, d), d):  # 界面靠它显示"会话在等"（旧协议：一条决定一个 wait）
        return _wait_responses(a, d)


def _wait_responses(a, d: Path) -> int:
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
            if a.id:  # 交给会话了：listen 不会再交一次
                mark_delivered(d, "reply", a.id, session_env()[0], "wait")
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
        append_jsonl(d / DELIVERIES, {"kind": "followup", "id": f["id"], "session": session_env()[0], "via": "wait",
                                      "ts": now_ts(), "pid": os.getpid()}, locked=True)
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


def _note_pid(d: Path, session: str, pid: int | None) -> None:
    """会话恢复（--resume）后 claude.exe 换了 pid：记一笔，程序和 inbox 才不会把它当成已经结束。"""
    if not pid:
        return
    start = proc_info(pid)[1]
    if session_pids(read_all(d / INBOX), read_ledger(d)).get(session) != (pid, start):
        append_jsonl(d / DELIVERIES, {"kind": "pid", "session": session, "session_pid": pid,
                                      "session_pid_start": start, "ts": now_ts()})


def cmd_listen(a) -> int:
    """这个会话唯一的监听：等到它的消息有了回复 / 追问，再等一小会儿把接连来的一起收齐，每件一行 JSON 打出来，记下送达，退出 0。
    已经有一个在听：退出 5（不打 stdout）。会话进程（$CLAUDE_PID）没了：什么都不打，退出 4。--timeout 到了：退出 2。"""
    d = data_dir(a.data)
    me, pid = _session_arg(a)
    if not me:
        print("错误：不知道是哪个会话（没有 $CLAUDE_CODE_SESSION_ID，也没给 --session）", file=sys.stderr)
        return 1
    with hold_marker(session_marker(me, d), d, exclusive=True) as held:
        if held == "dup":
            print("listen 已经在跑了（这个会话只要一个），不用再开", file=sys.stderr)
            return EXIT_DUP
        if held == "fail":
            print("注意：没挂上\"在听\"标记，ClaudeDesk 会显示这个会话没在听（回复照样收得到）", file=sys.stderr)
        start = proc_info(pid)[1] if pid else None
        if pid and not pid_alive(pid, start):
            return EXIT_GONE
        _note_pid(d, me, pid)
        deadline = time.monotonic() + a.timeout if a.timeout and a.timeout > 0 else None
        sig, mine, first, last, check_at = None, [], None, None, time.monotonic() + 2
        while True:
            now = time.monotonic()
            s2 = _files_sig(d)
            if s2 != sig:  # 文件变了才重算
                sig = s2
                now_mine = [e for e in pending_events(d) if e["session"] == me]
                if now_mine and len(now_mine) != len(mine):
                    first, last = first or now, now  # 又来了一件：安静计时从头算
                mine = now_mine
                if not mine:
                    first = last = None
            if first is not None and (now - last >= a.batch or now - first >= BATCH_MAX):
                got = claim_events(d, mine, me, "listen")
                if got:
                    for ev in got:
                        print(_line(ev), flush=True)
                    return 0
                sig, mine, first, last = None, [], None, None  # 被别人领走了（例如 close）：接着等
            if pid and now >= check_at:
                check_at = now + 2
                if not pid_alive(pid, start):
                    return EXIT_GONE  # 会话没了：不出声
            if deadline is not None and now >= deadline:
                print("timeout：没有等到回复或追问", file=sys.stderr)
                return EXIT_TIMEOUT
            time.sleep(min(a.interval, 0.25) if first is not None else a.interval)


def cmd_inbox(a) -> int:
    """新会话用：这个仓库里、已经结束的会话留下的还没送达的回复 / 追问（标为已处理、跳过的不算，没人要处理）。
    --adopt：把那些会话接到当前会话名下（以后它们的回复、追问也送到这里），打出来（和 listen 一样的行），记下送达。"""
    d = data_dir(a.data)
    me, pid = _session_arg(a)
    if a.adopt and not me:
        print("错误：--adopt 要知道当前会话（没有 $CLAUDE_CODE_SESSION_ID，也没给 --session）", file=sys.stderr)
        return 1
    repo = a.repo if a.repo is not None else detect_repo(folder_fallback=True)
    norm = lambda s: str(s or "").strip().lower()  # noqa: E731
    msgs = read_all(d / INBOX)
    led = read_ledger(d)
    evs = [e for e in pending_events(d) if e["session"] != me and norm(e["repo"]) == norm(repo)]
    gone = _gone_sessions(d, {e["session"] for e in evs}, msgs, led)
    evs = [e for e in evs if e["session"] in gone]
    quiet = [e for e in evs if e["ev"]["ev"] == "reply" and (e["ev"].get("resolved") or e["ev"].get("dismissed"))]
    evs = [e for e in evs if e not in quiet]
    if not a.adopt:
        for e in evs:
            print(_line(dict(e["ev"], session=e["session"][:8])))
        print(f"{len(evs)} 条（仓库 {repo or '?'}）" + ("；desk.py inbox --adopt 接过来" if evs else ""), file=sys.stderr)
        return 0
    start = proc_info(pid)[1] if pid else None
    pre = [{"kind": "adopt", "from": s, "repo": repo or "", "session": me, "session_pid": pid, "session_pid_start": start,
            "ts": now_ts()} for s in sorted({e["session"] for e in evs + quiet})]
    got = claim_events(d, evs, me, "adopt", pre=pre)
    claim_events(d, quiet, me, "adopt")  # 用户标为已处理 / 跳过的：没什么要做的，记成送达，免得以后 listen 再交
    for ev in got:
        print(_line(ev))
    print(f"接过来 {len(got)} 条（{len(pre)} 个已结束的会话）", file=sys.stderr)
    return 0


def cmd_status(a) -> int:
    """一行：这个会话还在等回复的决定、还没送达的事、listen 在不在；这个仓库有已结束的会话留下的事时加 orphaned=N。"""
    d = data_dir(a.data)
    me, _ = _session_arg(a)
    if not me:
        print("错误：不知道是哪个会话（没有 $CLAUDE_CODE_SESSION_ID，也没给 --session）", file=sys.stderr)
        return 1
    msgs = read_all(d / INBOX)
    led = read_ledger(d)
    answered = {str(r.get("id")) for r in read_all(d / RESPONSES)}
    n_open = sum(1 for m in msgs if m.get("kind") == "decision" and str(m.get("id")) not in answered
                 and owner_of(m.get("session"), led["adopt"], m.get("repo")) == me)
    evs = pending_events(d)
    repo = (detect_repo(folder_fallback=True) or "").lower()
    others = [e for e in evs if e["session"] != me and str(e["repo"]).lower() == repo
              and not (e["ev"]["ev"] == "reply" and (e["ev"].get("resolved") or e["ev"].get("dismissed")))]
    gone = _gone_sessions(d, {e["session"] for e in others}, msgs, led)
    orphaned = sum(1 for e in others if e["session"] in gone)
    on = me in presence(d, sessions=[me])[1]
    print(f"open={n_open} undelivered={sum(1 for e in evs if e['session'] == me)} listen={'on' if on else 'off'}"
          + (f" orphaned={orphaned}" if orphaned else ""))
    return 0


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
    if a.mine:
        return cmd_close_mine(a, d)
    m = find_message(a.id, d)
    if m is None:
        print(f"错误：没有这条消息 {a.id}", file=sys.stderr)
        return 1
    me = session_env()[0]
    try:
        rec = write_response(a.id, None, a.text or "（已在对话中处理）", m.get("source", ""), d,
                             extra={"title": m.get("title", ""), "closed_by": "claude",
                                    **({"session": m["session"]} if m.get("session") else {})})
    except FileExistsError:  # 用户已经在 ClaudeDesk 里答了：把那条回复打出来，会话要按它执行或和对话里的答复核对
        old = next((r for r in read_all(d / RESPONSES) if r.get("id") == a.id), None)
        if old is not None:
            print(_dump(dict(old, title=old.get("title") or m.get("title", ""))))
            mark_delivered(d, "reply", a.id, me, "close")  # 这就算交给会话了
        print("这条已经有回复了（用户已在 ClaudeDesk 里答复，见 stdout 那行 JSON）", file=sys.stderr)
        return EXIT_ANSWERED
    mark_delivered(d, "reply", a.id, me, "close")
    print(_dump(rec))
    return 0


def cmd_close_mine(a, d: Path) -> int:
    """这个会话所有还在等回复的决定都标成已处理（用户在对话里一起答了）。期间用户已经在 ClaudeDesk 里回复了的：
    把回复打出来（和 listen 一样的行），退出 3，会话要和对话里的答复核对。"""
    me, _ = _session_arg(a)
    if not me:
        print("错误：不知道是哪个会话（没有 $CLAUDE_CODE_SESSION_ID，也没给 --session）", file=sys.stderr)
        return 1
    led = read_ledger(d)
    answered = {str(r.get("id")) for r in read_all(d / RESPONSES)}
    mine = [m for m in read_all(d / INBOX) if m.get("kind") == "decision" and m.get("id")
            and owner_of(m.get("session"), led["adopt"], m.get("repo")) == me]
    closed = []
    for m in mine:
        if str(m["id"]) in answered:
            continue
        try:
            write_response(m["id"], None, a.text or "（已在对话中处理）", m.get("source", ""), d,
                           extra={"title": m.get("title", ""), "closed_by": "claude", "session": m["session"]})
            mark_delivered(d, "reply", m["id"], me, "close")
            closed.append(m["id"])
        except FileExistsError:
            pass  # 刚好被用户回复了：下面当成回复交出去
    ids = {str(m["id"]) for m in mine}
    got = claim_events(d, [e for e in pending_events(d) if e["key"][0] == "reply" and e["key"][1] in ids], me, "close")
    for ev in got:
        print(_line(ev))
    print(_line({"closed": closed}))
    if got:
        print(f"其中 {len(got)} 条用户已经在 ClaudeDesk 里回复了（见上面的 reply 行），要和对话里的答复核对", file=sys.stderr)
        return EXIT_ANSWERED
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
    sp.add_argument("--source", help="显示用的名字（默认：仓库名，不在仓库里用当前目录名）")
    sp.add_argument("--repo", help="消息属于哪个仓库（默认自动识别：当前目录所在 git 仓库的名字；不在仓库里就用当前目录名）")
    sp.add_argument("--session", help="发消息的会话（默认 $CLAUDE_CODE_SESSION_ID）：回复、追问送回这个会话")
    sp.add_argument("--title", required=True)
    sp.add_argument("--body", help="正文 Markdown；写 - 表示从 stdin 读")
    sp.add_argument("--body-file", help="正文 Markdown 文件（UTF-8）")
    sp.add_argument("--body-from-chat", action="store_true",
                    help="正文取自会话记录：刚在对话里写的那段回答（紧接着在同一条消息里调用 post）")
    sp.add_argument("--question", help="answer 类：用户的原问题")
    sp.add_argument("--question-file", help="answer 类：原问题放在文件里")
    sp.add_argument("--question-from-chat", action="store_true", help="answer 类：原问题取自会话记录（用户最近一条消息原文）")
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
    sp.add_argument("--id")
    sp.add_argument("--mine", action="store_true", help="这个会话所有还在等回复的决定")
    sp.add_argument("--session", help="--mine 用：哪个会话（默认 $CLAUDE_CODE_SESSION_ID）")
    sp.add_argument("--text", help="说明，例如：用户在对话里选了 B")
    sp.set_defaults(func=cmd_close)

    sp = sub.add_parser("listen", help="这个会话的回复 / 追问：有了就（攒一下）每件一行 JSON 打出来，退出 0；"
                                       "已有一个在听退出 5；会话进程没了不出声退出 4；超时退出 2")
    sp.add_argument("--session", help="默认 $CLAUDE_CODE_SESSION_ID")
    sp.add_argument("--timeout", type=float, default=0, help="秒；0 = 一直等")
    sp.add_argument("--interval", type=float, default=1.0, help=argparse.SUPPRESS)
    sp.add_argument("--batch", type=float, default=BATCH_QUIET, help=argparse.SUPPRESS)
    sp.set_defaults(func=cmd_listen)

    sp = sub.add_parser("inbox", help="已结束的会话在这个仓库留下的、还没送达的回复 / 追问；--adopt 接到当前会话")
    sp.add_argument("--repo", help="默认自动识别当前目录的仓库")
    sp.add_argument("--adopt", action="store_true")
    sp.add_argument("--session", help="默认 $CLAUDE_CODE_SESSION_ID")
    sp.set_defaults(func=cmd_inbox)

    sp = sub.add_parser("status", help="一行：这个会话的待决定、未送达、listen 在不在")
    sp.add_argument("--session", help="默认 $CLAUDE_CODE_SESSION_ID")
    sp.set_defaults(func=cmd_status)

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
    if a.cmd == "close" and bool(a.id) == bool(a.mine):
        p.error("close 需要 --id 或 --mine（二选一）")
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
