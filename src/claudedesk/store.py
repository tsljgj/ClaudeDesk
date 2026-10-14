"""数据层：增量读 inbox.jsonl / responses.jsonl / followups.jsonl，维护已读 / 归档 / 删除状态，写回复和追问。

不依赖任何 GUI 库：托盘、网页界面、测试都用同一个 Store。所有公开方法线程安全。
界面靠 `version` 做长轮询：任何可见变化都会让 version 加一并唤醒 `wait_change()`。
"""
from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Callable

import desk

KINDS = desk.KINDS
DISMISS_TEXT = "（用户在 ClaudeDesk 里移除了这条决定，没有作出选择）"
RESOLVE_TEXT = "（用户在 ClaudeDesk 里把这条标为已处理：已经处理好了（可能已经在对话里直接处理），不需要你再按选项做什么）"
COMPACT_RETRY_FIRST, COMPACT_RETRY_MAX = 5.0, 300.0  # 压缩失败后重试的间隔：5 秒起，每次翻倍，最长 5 分钟
OTHER_TAB = "__other__"  # 界面上"未归类"标签的键：没认出属于哪个仓库的消息
LISTEN_EVERY = 2.0  # 隔几秒看一次哪些会话在听追问（列一次命名管道）


def _now() -> dt.datetime:
    return dt.datetime.now().astimezone()


def plain_summary(md: str, n: int = 140) -> str:
    s = re.sub(r"```.*?```", " ", md or "", flags=re.S)
    s = re.sub(r"\$\$.*?\$\$", " [公式] ", s, flags=re.S)
    s = re.sub(r"(?m)^\s*\|?[\s:|-]+\|?\s*$", " ", s)  # 表格分隔行
    s = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", s)  # 链接 / 图片只留文字
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"[#>*_`|~]+", " ", s)
    s = re.sub(r"(?m)^\s*[-+]\s+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:n] + ("…" if len(s) > n else "")


def norm_name(name: str) -> str:
    """比较项目名用：不分大小写，空格 / 下划线 / 点都当成 -。"""
    return re.sub(r"[\s_.]+", "-", str(name or "").strip().lower())


def project_of(source: str) -> str:
    """旧消息（没有 repo 字段）的项目名猜测：source 里第一个 / 之前的部分。"""
    s = str(source or "").strip()
    return (s.split("/", 1)[0].strip() if "/" in s[1:] else s) or "unknown"


def normalize(r: dict) -> dict:
    m = dict(r)
    mid = str(r.get("id") or "").strip()
    if not mid:  # 没有 id 的行：用内容哈希合成一个稳定 id
        mid = "noid-" + hashlib.sha1(json.dumps(r, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
    m["id"] = mid
    kind = str(r.get("kind") or "info")
    m["kind"] = kind if kind in KINDS else "info"
    m["title"] = str(r.get("title") or "（无标题）").strip()
    m["body"] = str(r.get("body") or "")
    m["source"] = str(r.get("source") or "unknown")
    m["repo"] = str(r.get("repo") or "").strip()  # desk.py 发消息时自动识别的 git 仓库名
    m["_legacy"] = project_of(m["source"])
    q = r.get("question")
    m["question"] = str(q) if q else ""
    m["options"] = desk.normalize_options(r.get("options"))
    try:
        rec = int(r.get("recommended")) if r.get("recommended") not in (None, "") else None
    except (TypeError, ValueError):
        rec = None
    m["recommended"] = rec if rec and 1 <= rec <= len(m["options"]) else None
    m["allow_text"] = m["kind"] == "decision" or bool(r.get("allow_text"))  # 决定一律可以写补充说明（不管发的时候写没写）
    m["priority"] = "high" if r.get("priority") == "high" else "normal"
    m["reply_to"] = str(r.get("reply_to") or "").strip()  # 回答用户追问的消息：指向被追问的那条
    m["followup_id"] = str(r.get("followup_id") or "").strip()
    m["session"] = str(r.get("session") or "").strip()  # 发它的 Claude Code 会话（协议 v2）；旧消息没有
    m["session_pid"], m["session_pid_start"] = desk._as_int(r.get("session_pid")), desk._as_int(r.get("session_pid_start"))
    m["_dt"] = desk.parse_ts(r.get("ts")) or _now()
    m["_search"] = " ".join([m["title"], m["body"], m["source"], m["question"],
                             " ".join(o["label"] + " " + o["description"] for o in m["options"])]).lower()
    m["_snippet"] = plain_summary(m["question"] + " " + m["body"] if m["question"] else m["body"])
    return m


class Store:
    def __init__(self, ddir: Path, show_selftest: bool = False):
        self.ddir = Path(ddir)
        self.ddir.mkdir(parents=True, exist_ok=True)
        self.inbox_path = self.ddir / desk.INBOX
        self.resp_path = self.ddir / desk.RESPONSES
        self.state_path = self.ddir / desk.STATE
        self.show_selftest = show_selftest
        self.lock = threading.RLock()
        self.cond = threading.Condition(self.lock)
        self.version = 0
        self.msgs: dict[str, dict] = {}
        self.responses: dict[str, dict] = {}
        self.fu_path = self.ddir / desk.FOLLOWUPS
        self.followups: dict[str, list[dict]] = {}  # 消息 id -> 用户对它的追问（按时间）
        self.fu_by_id: dict[str, dict] = {}
        self.delivered: dict[str, str] = {}  # 已经交给会话（wait --followups 领走）的追问 id -> 什么时候
        self.replies: dict[str, list[str]] = {}  # 消息 id -> 回应它的追问的消息 id（reply_to 指向它）
        self.listening: set[str] = set()  # 现在有 wait --followups 在听的来源
        self._listen_at = 0.0
        # 协议 v2：按会话送（deliveries.jsonl）
        self.dl_path = self.ddir / desk.DELIVERIES
        self.dl_reply: dict[str, str] = {}  # 决定 id -> 回复什么时候交给了会话
        self.dl_fu: dict[str, str] = {}  # 追问 id -> 什么时候交给了会话（旧版记在 followups.jsonl 的在 self.delivered）
        self.adopted: dict[tuple, str] = {}  # (已结束的会话, 仓库) -> 接管它的会话（desk.py inbox --adopt）
        self.spid: dict[str, tuple] = {}  # 会话 -> (pid, 创建时间, 什么时候知道的)，取最新的
        self.live_sessions: set[str] = set()  # 有 listen 在跑的会话
        self.waiting_ids: set[str] = set()  # 有 wait --id 在等的决定（旧协议）
        self.alive: dict[str, bool] = {}  # 会话进程还在不在（只有知道 pid 的会话）
        self._dead: set[tuple] = set()  # 查到已经退出的 (pid, 创建时间)：不会再活过来，不用再查
        self._inbox_pos = (None, 0)  # (st_ino, offset)
        self._resp_pos = (None, 0)
        self._fu_pos = (None, 0)
        self._dl_pos = (None, 0)
        self.state = self._load_state()
        self.read: set[str] = set(self.state.get("read", []))
        self.notified: set[str] = set(self.state.get("notified", []))
        self.archived: set[str] = set(self.state.get("archived", []))
        self.deleted: set[str] = set(self.state.get("deleted", []))
        aliases = self.state.get("aliases")
        self.aliases: dict[str, str] = {str(k): str(v) for k, v in aliases.items()} if isinstance(aliases, dict) else {}
        hp = self.state.get("hidden_projects")  # 用户关掉的项目标签（标签键）：消息不显示、不计数，来新消息时自动回来
        self.hidden_projects: set[str] = {str(k) for k in hp} if isinstance(hp, list) else set()
        ra = self.state.get("read_at")  # 消息 id -> 用户最后一次在界面里打开它的时间（按时间归档已处理的：刚看过的不算旧）
        self.read_at: dict[str, dt.datetime] = {}
        for k, v in (ra.items() if isinstance(ra, dict) else ()):
            t = desk.parse_ts(v) if isinstance(v, str) else None
            if t is not None:
                self.read_at[str(k)] = t
        self._repos: dict[str, str] = {}  # 消息里见过的仓库名：规范化名 -> 原名
        self._discovered: dict[str, str] = {}  # 从 Claude Code 会话记录里找到的项目名
        self._loaded = False
        self._dirty = False
        self._save_at = 0.0
        self._save_lock = threading.Lock()  # 几个线程同时存盘：按顺序写，最后落盘的一定是最新的
        self._compact_fails = 0  # 压缩连续失败次数，决定下次重试的间隔
        self._compact_at = 0.0  # 不早于这个时刻（monotonic）再试
        self.on_arrived: list[Callable[[list[dict]], None]] = []  # 新到、还没通知过的消息
        self.on_changed: list[Callable[[], None]] = []

    # ------------------------------------------------------------ 状态文件
    def _load_state(self) -> dict:
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                st = json.load(f)
            return st if isinstance(st, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def save_state(self) -> None:
        with self._save_lock:  # 拍快照和写盘一起排队：不会两个线程同写一个 .tmp，也不会旧快照盖掉新的
            with self.lock:
                if not self._loaded:
                    return
                present = set(self.msgs)
                self.state["version"] = 2
                self.state["read"] = sorted(self.read & present)
                self.state["notified"] = sorted(self.notified & present)
                self.state["archived"] = sorted(self.archived & present)
                self.state["deleted"] = sorted(self.deleted & present)  # 压缩成功后自然清掉
                self.state["aliases"] = dict(self.aliases)
                self.state["hidden_projects"] = sorted(self.hidden_projects)
                self.state["read_at"] = {k: v.isoformat() for k, v in sorted(self.read_at.items()) if k in present}
                data = json.dumps(self.state, ensure_ascii=False, indent=1)
                self._dirty = False
            tmp = self.state_path.with_name(self.state_path.name + ".tmp")
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    f.write(data)
                _retry(lambda: os.replace(tmp, self.state_path))
            except OSError:
                pass

    def schedule_save(self) -> None:
        self._dirty = True
        self._save_at = time.monotonic() + 0.4

    def flush_if_due(self) -> None:
        if self._dirty and time.monotonic() >= self._save_at:
            self.save_state()

    def setting(self, key, default=None):
        with self.lock:
            return self.state.get("ui", {}).get(key, default)

    def set_setting(self, key, value) -> None:
        with self.lock:
            self.state.setdefault("ui", {})[key] = value
            self.schedule_save()
            self._bump()

    # ------------------------------------------------------------ 变更通知
    def _bump(self) -> None:
        """持锁调用：版本加一，唤醒长轮询。"""
        self.version += 1
        self.cond.notify_all()

    def _emit_changed(self) -> None:
        for cb in list(self.on_changed):
            try:
                cb()
            except Exception:  # noqa: BLE001 - 回调出错不能拖垮数据层
                pass

    def wait_change(self, since: int, timeout: float) -> int:
        with self.cond:
            if self.version <= since:
                self.cond.wait_for(lambda: self.version > since, timeout=timeout)
            return self.version

    # ------------------------------------------------------------ 读取
    @staticmethod
    def _advance(path: Path, pos):
        ino, off = pos
        try:
            st = os.stat(path)
        except FileNotFoundError:
            return [], (None, 0), off != 0
        except PermissionError:
            return [], pos, False
        reset = (ino is not None and st.st_ino != ino) or st.st_size < off
        if reset:
            off = 0
        if st.st_size == off:
            return [], (st.st_ino, off), reset
        try:
            recs, off2 = desk.read_jsonl(path, off, retry=0.2)
        except PermissionError:  # 文件正被换掉（压缩）或被别人独占：这一轮当没有新内容，位置不动，下轮再读
            return [], pos, False
        return recs, (st.st_ino, off2), reset

    def poll(self) -> None:
        new: list[dict] = []
        with self.lock:
            changed = False
            recs, self._inbox_pos, reset = self._advance(self.inbox_path, self._inbox_pos)
            if reset:
                self.msgs.clear()
                self._repos.clear()
                self.replies.clear()
                changed = True
            for r in recs:
                try:
                    m = normalize(r)
                except Exception:  # noqa: BLE001 - 格式不对的记录跳过；位置已经往后挪了，不能让它连累后面的
                    continue
                if m["id"] in self.msgs:
                    continue
                self.msgs[m["id"]] = m
                if m["repo"]:
                    self._repos.setdefault(norm_name(m["repo"]), m["repo"])
                if m["reply_to"]:
                    self.replies.setdefault(m["reply_to"], []).append(m["id"])
                if m["session"] and m["session_pid"]:
                    self._note_pid(m["session"], m["session_pid"], m["session_pid_start"], m["_dt"])
                changed = True
                if not self.hidden(m) and m["id"] not in self.read and m["id"] not in self.notified:
                    new.append(m)

            recs, self._resp_pos, reset = self._advance(self.resp_path, self._resp_pos)
            if reset:
                self.responses.clear()
                changed = True
            for r in recs:
                rid = str(r.get("id") or "")
                if rid and rid not in self.responses:
                    self.responses[rid] = r
                    changed = True

            recs, self._fu_pos, reset = self._advance(self.fu_path, self._fu_pos)
            if reset:
                self.followups.clear()
                self.fu_by_id.clear()
                self.delivered.clear()
                changed = True
            for r in recs:
                changed = self._add_followup_rec(r) or changed

            recs, self._dl_pos, reset = self._advance(self.dl_path, self._dl_pos)
            if reset:
                self.dl_reply.clear()
                self.dl_fu.clear()
                self.adopted.clear()
                changed = True
            for r in recs:
                changed = self._add_delivery_rec(r) or changed

            first = not self._loaded
            self._loaded = True
            if new:
                for m in new:
                    self.notified.add(m["id"])
                    self.hidden_projects.discard(self.tab_key(m))  # 关掉的标签来了新消息：标签自动回来（通知、计数跟着对）
                self.schedule_save()
            if changed or first:
                self._bump()
        if new:
            for cb in list(self.on_arrived):
                try:
                    cb(new)
                except Exception:  # noqa: BLE001
                    pass
        if changed or first:
            self._emit_changed()
        self.refresh_listening()
        self.flush_if_due()

    def _add_followup_rec(self, r: dict) -> bool:
        """持锁调用：收一行 followups.jsonl（追问，或"已交给会话"）。返回有没有变化。"""
        if r.get("delivered"):
            fid = str(r["delivered"])
            if fid in self.delivered:
                return False
            self.delivered[fid] = (desk.parse_ts(r.get("ts")) or _now()).isoformat()
            return True
        fid, mid = str(r.get("id") or ""), str(r.get("msg") or "")
        if not fid or not mid or fid in self.fu_by_id:
            return False
        f = {"id": fid, "ts": str(r.get("ts") or ""), "msg": mid, "text": str(r.get("text") or ""),
             "_dt": desk.parse_ts(r.get("ts")) or _now()}
        self.fu_by_id[fid] = f
        lst = self.followups.setdefault(mid, [])
        lst.append(f)
        lst.sort(key=lambda x: x["_dt"])
        return True

    def _add_delivery_rec(self, r: dict) -> bool:
        """持锁调用：收一行 deliveries.jsonl（送达、接管、会话换了进程）。返回有没有变化。"""
        k, rid = r.get("kind"), str(r.get("id") or "")
        when = desk.parse_ts(r.get("ts")) or _now()
        if k in ("reply", "followup") and rid:
            dst = self.dl_reply if k == "reply" else self.dl_fu
            if rid in dst:
                return False
            dst[rid] = when.isoformat()
            return True
        s = str(r.get("session") or "")
        if k not in ("adopt", "pid") or not s:
            return False
        if k == "adopt" and r.get("from") and r["from"] != s:
            self.adopted[(str(r["from"]), str(r.get("repo") or "").lower())] = s
        pid = desk._as_int(r.get("session_pid"))
        if pid:
            self._note_pid(s, pid, desk._as_int(r.get("session_pid_start")), when)
        return True

    def _note_pid(self, session: str, pid: int, start, when) -> None:
        """持锁调用：记下会话最新的进程（会话恢复后 pid 会变；按时间取最晚的）。"""
        old = self.spid.get(session)
        if old is None or when >= old[2]:
            self.spid[session] = (pid, start, when)

    def owner(self, m: dict) -> str:
        """消息现在归哪个会话：发它的会话；被接管过的按接管后的（可以接力）。旧消息返回空串。"""
        return desk.owner_of(m.get("session") or "", self.adopted, m.get("repo")) or ""

    def fu_delivered(self, fid: str) -> str | None:
        return self.dl_fu.get(fid) or self.delivered.get(fid)

    def session_state(self, m: dict) -> str:
        """listening：会话在等（listen；旧协议的 wait --id 在等这条决定、wait --followups 在听这个来源的追问也算）；
        open：会话还开着但没在听；gone：会话进程已经没了；unknown：旧消息，不知道是哪个会话。"""
        s = self.owner(m)
        if not s:
            return "unknown"
        if s in self.live_sessions:
            return "listening"
        if self.is_open(m) and m["id"] in self.waiting_ids or not self.is_open(m) and m["source"] in self.listening:
            return "listening"
        return "gone" if self.alive.get(s) is False else "open"

    def refresh_listening(self, force: bool = False) -> bool:
        """看哪些会话在听、哪些会话还在，最多每 LISTEN_EVERY 秒一次：列一次管道目录（listen、wait --id、wait --followups
        占着的标记），再按 pid 查一遍会话进程（已经退出的记住，不再查）。列的时候不持锁。变了返回 True。"""
        now = time.monotonic()
        if not force and now < self._listen_at:
            return False
        self._listen_at = now + LISTEN_EVERY
        with self.lock:
            sources = {m["source"] for m in self.msgs.values()}
            sessions = {self.owner(m) for m in self.msgs.values() if m["session"]}
            ids = {m["id"] for m in self.msgs.values() if self.is_open(m)}
            pids = {s: self.spid[s][:2] for s in sessions if s in self.spid}
        live, sess, waiting = desk.presence(self.ddir, sources, sessions, ids)
        alive = {}
        for s, key in pids.items():
            if key not in self._dead:
                alive[s] = desk.pid_alive(*key)
                if not alive[s]:
                    self._dead.add(key)
            else:
                alive[s] = False
        with self.lock:
            if (live, sess, waiting, alive) == (self.listening, self.live_sessions, self.waiting_ids, self.alive):
                return False
            self.listening, self.live_sessions, self.waiting_ids, self.alive = live, sess, waiting, alive
            self._bump()
        self._emit_changed()
        return True

    # ------------------------------------------------------------ 查询
    def hidden(self, m: dict) -> bool:
        if m["id"] in self.deleted:
            return True
        return (not self.show_selftest) and m["source"].lower().startswith("selftest")

    def visible(self, archived: bool | None = False) -> list[dict]:
        """archived=False：不含归档；True：只要归档；None：都要。"""
        with self.lock:
            out = [m for m in self.msgs.values() if not self.hidden(m)]
            if archived is None:
                return out
            return [m for m in out if (m["id"] in self.archived) == archived]

    def is_open(self, m: dict) -> bool:
        return m["kind"] == "decision" and m["id"] not in self.responses

    def is_unread(self, m: dict) -> bool:
        return m["id"] not in self.read

    def is_urgent(self, m: dict) -> bool:
        return self.is_unread(m) and m["id"] not in self.archived and (self.is_open(m) or m["priority"] == "high")

    def closed(self, m: dict) -> bool:
        """在用户关掉的标签里：界面不显示，托盘 / 任务栏也不计数。"""
        return bool(self.hidden_projects) and self.tab_key(m) in self.hidden_projects

    def counts(self) -> dict:
        with self.lock:
            vis = [m for m in self.visible() if not self.closed(m)]
            return {
                "unread": sum(1 for m in vis if self.is_unread(m)),
                "open": sum(1 for m in vis if self.is_open(m)),
                "urgent": sum(1 for m in vis if self.is_urgent(m)),
                "unread_answers": sum(1 for m in vis if m["kind"] == "answer" and self.is_unread(m)),
                "unread_info": sum(1 for m in vis if m["kind"] == "info" and self.is_unread(m)),
                "archived": sum(1 for m in self.visible(archived=True) if not self.closed(m)),
                "total": len(vis),
            }

    def project_info(self, m: dict) -> tuple[str, str, str]:
        """(项目名, 类型, 归类键)。类型 repo = 认得出是哪个仓库；other = 没认出来（旧消息的来源对不上任何仓库）。
        归类键是用户"合并到…"时用的名字（合并前的名字）。"""
        if m["repo"]:
            name, kind = m["repo"], "repo"
        else:
            raw = m["_legacy"]
            hit = self._match_repo(raw)
            name, kind = (hit, "repo") if hit else (raw, "other")
        key = name
        if key in self.aliases:
            name, kind = self.aliases[key], "repo"
        return name, kind, key

    def tab_key(self, m: dict) -> str:
        """界面上这条消息所在的标签：归类后的项目名；没认出仓库的都在 OTHER_TAB（"未归类"）。"""
        name, kind, _ = self.project_info(m)
        return OTHER_TAB if kind == "other" else name

    def _match_repo(self, raw: str) -> str | None:
        """旧消息的来源名对到已知仓库：完全一样；或来源是"仓库名-后缀"（取最长的那个）；
        或来源是某个仓库名的唯一前缀（acme-data 对 acme-data-pipeline）。"""
        known = {**self._discovered, **self._repos}
        n = norm_name(raw)
        if not n:
            return None
        if n in known:
            return known[n]
        longer = [k for k in known if n.startswith(k + "-")]
        if longer:
            return known[max(longer, key=len)]
        prefix_of = [k for k in known if k.startswith(n + "-")]
        return known[prefix_of[0]] if len(prefix_of) == 1 else None

    def set_known_projects(self, names) -> None:
        """后台从 Claude Code 会话记录里找到的项目名（见 projects.py）。"""
        d = {norm_name(x): x for x in names if x}
        with self.lock:
            if d == self._discovered:
                return
            self._discovered = d
            self._bump()
        self._emit_changed()

    def summary(self, m: dict) -> dict:
        resp = self.responses.get(m["id"])
        project, pkind, pkey = self.project_info(m)
        s = {
            "id": m["id"], "kind": m["kind"], "title": m["title"], "source": m["source"],
            "project": project, "project_kind": pkind, "project_key": pkey, "repo": m["repo"],
            "ts": m["_dt"].isoformat(), "priority": m["priority"], "snippet": m["_snippet"],
            "open": self.is_open(m), "answered": resp is not None, "unread": self.is_unread(m),
            "archived": m["id"] in self.archived,
            "choice": (resp or {}).get("choice"), "dismissed": bool((resp or {}).get("dismissed")),
            "resolved": bool((resp or {}).get("resolved")),
            "last_active": self.last_active(m, resp).isoformat(),
        }
        if resp is not None and resp.get("silent"):  # 标为已处理 / 跳过时没有通知会话（旧记录没有这个标记：当时通知了）
            s["silent"] = True
        # 追问（除了还没回复的决定，每条都能追问）：listening = 它的会话现在在不在听；有追问 / 回应的带
        # followup_pending（有追问还没回应）和 fstate（追问数.已送达数.回应数，变了界面就重新拿详情）；回应追问的消息带 reply_to
        s["listening"] = m["source"] in self.listening
        # 协议 v2：session_state = listening / open / gone / unknown（见 session_state）；delivered = 回复什么时候交给了会话
        s["session_state"] = self.session_state(m)
        if s["session_state"] == "listening":
            s["listening"] = True
        if m["id"] in self.dl_reply:
            s["delivered"] = self.dl_reply[m["id"]]
        if m["reply_to"]:
            s["reply_to"] = m["reply_to"]
        if m["id"] in self.followups or m["id"] in self.replies:
            fus, reps, pairs = self._thread(m["id"])
            s["followup_pending"] = any(f["id"] not in pairs for f in fus)
            s["fstate"] = f"{len(fus)}.{sum(bool(self.fu_delivered(f['id'])) for f in fus)}.{len(reps)}"
        return s

    def last_active(self, m: dict, resp: dict | None = None) -> dt.datetime:
        """这条消息最后一次有动静：收到它、回复它、用户在界面里打开它，取最晚的。按时间归档已处理的按它算。"""
        resp = self.responses.get(m["id"]) if resp is None else resp
        ts = [m["_dt"], self.read_at.get(m["id"]), desk.parse_ts((resp or {}).get("ts"))]
        return max(t for t in ts if t is not None)

    def _thread(self, mid: str):
        """持锁调用：(这条消息的追问, 回应它们的消息, {追问 id: 回应})。删掉的回应不算。"""
        fus = self.followups.get(mid, [])
        reps = [self.msgs[r] for r in self.replies.get(mid, []) if r in self.msgs and not self.hidden(self.msgs[r])]
        reps.sort(key=lambda r: r["_dt"])
        return fus, reps, (desk.pair_followups(fus, reps) if fus and reps else {})

    def _thread_detail(self, m: dict, d: dict) -> None:
        """持锁调用：详情里加上追问这一串。followups：每条追问（delivered = 什么时候交给了会话、reply = 哪条消息回应了它）；
        replies：所有回应它的消息；回应追问的消息另有 reply_ref = 原来那条（id、标题、类型、还在不在）和它回应的追问原文。"""
        fus, reps, pairs = self._thread(m["id"])
        d["followups"] = [{"id": f["id"], "ts": f["_dt"].isoformat(), "text": f["text"], "delivered": self.fu_delivered(f["id"]),
                           "reply": {"id": pairs[f["id"]]["id"], "title": pairs[f["id"]]["title"]} if f["id"] in pairs else None}
                          for f in fus]
        paired = {r["id"] for r in pairs.values()}
        d["replies"] = [{"id": r["id"], "title": r["title"], "ts": r["_dt"].isoformat(), "paired": r["id"] in paired}
                        for r in reps]
        if m["reply_to"]:
            o = self.msgs.get(m["reply_to"])
            ok = o is not None and not self.hidden(o)
            text = m["question"]
            if not text and m["followup_id"] in self.fu_by_id:
                text = self.fu_by_id[m["followup_id"]]["text"]
            if not text and ok:  # 会话没带 --question：看配对配上的是哪条追问
                text = next((self.fu_by_id[fid]["text"] for fid, r in self._thread(o["id"])[2].items() if r["id"] == m["id"]), "")
            d["reply_ref"] = {"id": m["reply_to"], "title": o["title"] if ok else "", "kind": o["kind"] if ok else "",
                              "exists": ok, "text": text}

    def summaries(self) -> list[dict]:
        with self.lock:
            items = self.visible(archived=None)
            items.sort(key=lambda m: (m["_dt"], m["id"]), reverse=True)
            return [self.summary(m) for m in items]

    def detail(self, mid: str) -> dict | None:
        with self.lock:
            m = self.msgs.get(mid)
            if m is None or self.hidden(m):
                return None
            d = self.summary(m)
            d.update(body=m["body"], question=m["question"], options=m["options"],
                     recommended=m["recommended"], allow_text=m["allow_text"],
                     response=self.responses.get(mid))
            self._thread_detail(m, d)
            return d

    def search(self, q: str) -> list[str]:
        terms = q.lower().split()
        with self.lock:
            return [m["id"] for m in self.visible(archived=None) if all(t in m["_search"] for t in terms)]

    # ------------------------------------------------------------ 修改
    def _known(self, ids) -> list[str]:
        return [i for i in ids if i in self.msgs]

    def mark_read(self, ids, read: bool = True, opened: bool = False) -> int:
        """标为已读 / 未读，返回状态真的变了的条数。opened：用户在界面里打开了它（读过的也算），记下时间（read_at）：
        按时间归档已处理的时，刚看过的不算旧。批量标为已读不算打开。"""
        with self.lock:
            ids = self._known(ids)
            before = len(self.read)
            if read:
                self.read.update(ids)
            else:
                self.read.difference_update(ids)
            n = abs(len(self.read) - before)
            touched = bool(read and opened and ids)
            if touched:
                now = _now()
                for i in ids:
                    self.read_at[i] = now
            if n or touched:
                self.schedule_save()
                self._bump()
        if n or touched:
            self._emit_changed()
        return n

    def mark_all_read(self, project: str | None = None) -> int:
        return self.mark_read([m["id"] for m in self.visible() if not self.closed(m)
                               and (not project or self.project_info(m)[0] == project)])

    def _dismiss_open(self, ids) -> None:
        """移走（归档 / 删除）还在等回复的决定之前，记一条"跳过了"的回复：它不再算待决定。
        silent：不通知会话（listen 不交、不叫醒它）；会话 close 它时会看到这条（退出 3）。"""
        for mid in ids:
            m = self.msgs.get(mid)
            if m is not None and self.is_open(m):
                try:
                    rec = desk.write_response(mid, None, DISMISS_TEXT, m["source"], self.ddir,
                                              extra={"title": m["title"], "dismissed": True, "silent": True, **_sess(m)})
                    self.responses[mid] = rec
                except FileExistsError:
                    pass

    def set_alias(self, frm: str, to: str | None) -> dict:
        """把项目（或没认出来的来源）frm 归到 to 下面；to 为空表示撤销。"""
        frm, to = str(frm or "").strip(), str(to or "").strip()
        if not frm:
            raise ValueError("缺少要归类的项目名")
        with self.lock:
            if to and to != frm:
                self.aliases[frm] = to
                for k, v in list(self.aliases.items()):  # 已经归到 frm 的，一起改到 to（不留链）
                    if v == frm:
                        self.aliases[k] = to
                # frm 不再是单独的标签：它的"已关闭"作废（关掉的 frm 归到开着的 to，消息跟着 to 显示，to 不会跟着不见）；
                # 归到一个关掉的 to：用户刚明确要把 frm 放进去，to 回来，免得 frm 一归过去就不见了
                self.hidden_projects.discard(frm)
                self.hidden_projects.discard(to)
            else:
                self.aliases.pop(frm, None)
            self.schedule_save()
            self._bump()
            out = dict(self.aliases)
        self._emit_changed()
        return out

    def resolve(self, ids) -> int:
        """标为已处理：还在等回复的决定写一条 resolved 回复，所有选中的都标为已读。返回实际解决的决定数。
        回复带 silent：不通知会话（用户多半已经在对话里说过，或者这件事不重要了；叫醒会话要花 token）。可以 unresolve 撤销。"""
        done = 0
        with self.lock:
            ids = self._known(ids)
            for mid in ids:
                m = self.msgs[mid]
                if not self.is_open(m):
                    continue
                try:
                    rec = desk.write_response(mid, None, RESOLVE_TEXT, m["source"], self.ddir,
                                              extra={"title": m["title"], "resolved": True, "silent": True, **_sess(m)})
                    self.responses[mid] = rec
                    done += 1
                except FileExistsError:
                    pass
            self.read.update(ids)
            self.schedule_save()
            self._bump()
        self._emit_changed()
        return done

    def unresolve(self, ids) -> int:
        """撤销"标为已处理 / 跳过"：从 responses.jsonl 里删掉这几条决定的 silent 回复，决定重新变成待决定。
        只删没通知过会话的（silent 的 resolved / dismissed，而且没有送达记录）：交给了会话的收不回来，用户的真回复也不动。
        在 data/.lock 锁内整份重写（和 compact 一样换文件）；锁的顺序和 resolve 一样：self.lock → data/.lock。
        返回删了几条；写不了抛 OSError / TimeoutError（界面提示，下次再撤销也行）。"""
        want = {str(i) for i in ids}
        if not want:
            return 0
        tmp = self.resp_path.with_name(self.resp_path.name + ".unresolve")
        dropped: set[str] = set()
        with self.lock:
            try:
                with desk.file_lock(self.ddir, timeout=2.0):
                    raw = self.resp_path.read_bytes() if self.resp_path.exists() else b""
                    sent = desk.read_ledger(self.ddir)["reply"]
                    keep = []
                    for line in raw.splitlines(keepends=True):
                        rec = None
                        if line.strip():
                            try:
                                rec = json.loads(line.strip().decode("utf-8-sig"))
                            except Exception:  # noqa: BLE001 - 坏行原样保留
                                rec = None
                        rid = str(rec.get("id") or "") if isinstance(rec, dict) else ""
                        if rid and rid in want and rec.get("silent") and (rec.get("resolved") or rec.get("dismissed")) \
                                and rid not in sent:
                            dropped.add(rid)
                            continue
                        keep.append(line if line.endswith(b"\n") else line + b"\n")
                    if dropped:
                        with open(tmp, "wb") as f:
                            f.write(b"".join(keep))
                            f.flush()
                            os.fsync(f.fileno())
                        _retry(lambda: os.replace(tmp, self.resp_path), attempts=20, delay=0.05)
            except BaseException:
                with contextlib.suppress(OSError):
                    tmp.unlink(missing_ok=True)
                raise
            if not dropped:
                return 0
            for mid in dropped:
                self.responses.pop(mid, None)
            self._resp_pos = (None, 0)  # 文件换了：下一轮从头读（已经有的不会重复加）
            self._bump()
        self._emit_changed()
        return len(dropped)

    def archive(self, ids, on: bool = True) -> int:
        with self.lock:
            ids = self._known(ids)
            if on:
                self._dismiss_open(ids)
                todo = [i for i in ids if i not in self.archived]
                self.archived.update(todo)
                self.read.update(todo)
            else:
                todo = [i for i in ids if i in self.archived]
                self.archived.difference_update(todo)
            if todo:
                self.schedule_save()
                self._bump()
        if todo:
            self._emit_changed()
        return len(todo)

    def archive_handled(self, project: str | None = None) -> int:
        """把已读、且不用再处理（不是待决定）的消息全部归档。给了 project 就只动这个项目的。"""
        with self.lock:
            ids = [m["id"] for m in self.visible() if not self.is_unread(m) and not self.is_open(m) and not self.closed(m)
                   and (not project or self.project_info(m)[0] == project)]
        return self.archive(ids)

    def hide_project(self, key: str) -> list[str]:
        """关掉一个项目标签（key：归类后的项目名，或 OTHER_TAB）。返回关着的全部标签。"""
        key = str(key or "").strip()
        if not key:
            raise ValueError("缺少要关闭的项目")
        return self._set_hidden(lambda h: h.add(key))

    def show_project(self, key: str | None = None) -> list[str]:
        """找回关掉的标签；key 为 None 时全部找回。"""
        return self._set_hidden(lambda h: h.clear() if key is None else h.discard(str(key)))

    def _set_hidden(self, change) -> list[str]:
        with self.lock:
            before = set(self.hidden_projects)
            change(self.hidden_projects)
            changed = self.hidden_projects != before
            if changed:
                self.schedule_save()
                self._bump()
            out = sorted(self.hidden_projects)
        if changed:
            self._emit_changed()
        return out

    def delete(self, ids) -> int:
        with self.lock:
            ids = [i for i in self._known(ids) if i not in self.deleted]
            if not ids:
                return 0
            self._dismiss_open(ids)
            self.deleted.update(ids)
            self.schedule_save()
            self._bump()
        self._emit_changed()
        self.compact()
        return len(ids)

    def compact(self) -> bool:
        """把已删除的消息从 inbox.jsonl 里真正去掉（在 data/.lock 锁内整份重写）。
        失败（例如文件正被别的进程打开）没关系：state.json 里的删除标记照样让它们不显示；
        轮询线程会用 compact_if_due() 过一阵再试，间隔越拉越长。data/.lock 只拿一小会儿，免得 desk.py post 卡住。"""
        with self.lock:
            dead = set(self.deleted)
        if not dead:
            return True
        tmp = self.inbox_path.with_name(self.inbox_path.name + ".compact")
        dropped = 0
        try:
            with desk.file_lock(self.ddir, timeout=2.0):
                raw = self.inbox_path.read_bytes() if self.inbox_path.exists() else b""
                keep = []
                for line in raw.splitlines(keepends=True):
                    s = line.strip()
                    if s:
                        try:
                            rec = json.loads(s.decode("utf-8-sig"))
                            mid = normalize(rec)["id"] if isinstance(rec, dict) else None
                        except Exception:  # noqa: BLE001 - 坏行、格式不对的记录原样保留
                            mid = None
                        if mid in dead:
                            dropped += 1
                            continue
                    keep.append(line if line.endswith(b"\n") else line + b"\n")
                if dropped:
                    with open(tmp, "wb") as f:
                        f.write(b"".join(keep))
                        f.flush()
                        os.fsync(f.fileno())
                    _retry(lambda: os.replace(tmp, self.inbox_path), attempts=5, delay=0.05)
        except (OSError, TimeoutError):
            with self.lock:
                self._compact_fails += 1
                self._compact_at = time.monotonic() + min(COMPACT_RETRY_MAX,
                                                          COMPACT_RETRY_FIRST * 2 ** (self._compact_fails - 1))
            with contextlib.suppress(OSError):
                tmp.unlink(missing_ok=True)
            return False
        with self.lock:
            self._compact_fails = 0
            if not dropped:  # 文件里已经没有了（例如别的线程刚压缩完）：内存里也不留，免得 compact_if_due 一直来
                for mid in dead:
                    self.msgs.pop(mid, None)
        if dropped:
            try:
                self.poll()  # 文件号变了：整份重读，删掉的就不在 msgs 里了
            except OSError:
                pass  # 轮询线程下一轮会读
        return True

    def compact_if_due(self) -> bool | None:
        """轮询线程每轮调用：还有删掉了却仍在 inbox.jsonl 里的消息（上次压缩失败，或者启动时发现的），
        而且到了重试时间，就再压缩一次。没做返回 None。"""
        with self.lock:
            due = bool(self.deleted & set(self.msgs)) and time.monotonic() >= self._compact_at
        return self.compact() if due else None

    def submit(self, mid: str, choice: str | None, text: str, choice_index=None) -> dict:
        """写回复；已回复过的抛 FileExistsError。
        choice_index（从 1 开始）是界面上点的第几个选项：有它就按它记（两个选项同名时也不会记错），
        并且要和 choice 对得上；旧界面只发 choice，就按名字找第一个。"""
        with self.lock:
            m = self.msgs.get(mid)
            if m is None:
                raise KeyError("没有这条消息")
            if mid in self.responses:
                raise FileExistsError("这条已经回复过了")
            extra = {"title": m["title"], **_sess(m)}
            labels = [o["label"] for o in m["options"]]
            if choice_index is not None:
                s = str(choice_index).strip()
                if isinstance(choice_index, bool) or not s.isdecimal() or not 1 <= int(s) <= len(labels):
                    raise ValueError(f"没有第 {choice_index} 个选项")
                idx = int(s)
                if choice is not None and choice != labels[idx - 1]:
                    raise ValueError(f"第 {idx} 个选项是「{labels[idx - 1]}」，和提交的「{choice}」对不上，请重新选择")
                choice = labels[idx - 1]
                extra["choice_index"] = idx
            elif choice is not None:
                if choice not in labels:
                    raise ValueError("没有这个选项")
                extra["choice_index"] = labels.index(choice) + 1
            elif not (text or "").strip():
                raise ValueError("请选择一个选项或写下回复")
            rec = desk.write_response(mid, choice, text, m["source"], self.ddir, extra=extra)
            self.read.add(mid)
            self.responses[mid] = rec
            self.schedule_save()
            self._bump()
        self._emit_changed()
        try:
            self.poll()
        except OSError:  # 回复已经写好了：这里读不到不能让界面以为提交失败
            pass
        return rec


    def add_followup(self, mid: str, text: str) -> dict:
        """用户对一条消息追问（回答、通知、已经回复过的决定都行）：在 data/.lock 锁内追加到 followups.jsonl，
        在听的会话（wait --followups）会领走。只写追问文件，不碰 responses.jsonl：追问不会让等这条 id 的 wait 醒来。
        还没回复的决定不能追问：它有自己的回复框，回复了才能追问。"""
        text = str(text or "").strip()
        with self.lock:
            m = self.msgs.get(mid)
            if m is None or self.hidden(m):
                raise KeyError("没有这条消息")
            if self.is_open(m):
                raise ValueError("这条决定还在等你回复：先在上面选择或写回复，回复之后才能追问")
            if not text:
                raise ValueError("追问不能为空")
            rec = desk.write_followup({"id": mid, "source": m["source"], "title": m["title"], **_sess(m)}, text, self.ddir)
            self._add_followup_rec(rec)
            self._bump()
        self._emit_changed()
        return rec


def _sess(m: dict) -> dict:
    """写回复 / 追问时带上消息的会话：原消息删掉了也知道送给谁。"""
    return {"session": m["session"]} if m.get("session") else {}


def _retry(fn, attempts: int = 25, delay: float = 0.1):
    """Windows 上目标文件被别的进程短暂打开时 os.replace 会 PermissionError，稍等重试。"""
    for i in range(attempts):
        try:
            return fn()
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(delay)
