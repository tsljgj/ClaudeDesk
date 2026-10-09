"""数据层：增量读 inbox.jsonl / responses.jsonl，维护已读 / 归档 / 删除状态，写回复。

不依赖任何 GUI 库：托盘、网页界面、测试都用同一个 Store。所有公开方法线程安全。
界面靠 `version` 做长轮询：任何可见变化都会让 version 加一并唤醒 `wait_change()`。
"""
from __future__ import annotations

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
RESOLVE_TEXT = "（用户在 ClaudeDesk 里把这条标为已解决：已经处理好了，不需要你再按选项做什么）"


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


def project_of(source: str) -> str:
    """来源的项目名：source 里第一个 / 之前的部分（skill 让同一项目的并行会话写成 项目/后缀）。"""
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
    m["project"] = project_of(m["source"])
    q = r.get("question")
    m["question"] = str(q) if q else ""
    m["options"] = desk.normalize_options(r.get("options"))
    try:
        rec = int(r.get("recommended")) if r.get("recommended") not in (None, "") else None
    except (TypeError, ValueError):
        rec = None
    m["recommended"] = rec if rec and 1 <= rec <= len(m["options"]) else None
    m["allow_text"] = bool(r.get("allow_text")) or (m["kind"] == "decision" and not m["options"])
    m["priority"] = "high" if r.get("priority") == "high" else "normal"
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
        self._inbox_pos = (None, 0)  # (st_ino, offset)
        self._resp_pos = (None, 0)
        self.state = self._load_state()
        self.read: set[str] = set(self.state.get("read", []))
        self.notified: set[str] = set(self.state.get("notified", []))
        self.archived: set[str] = set(self.state.get("archived", []))
        self.deleted: set[str] = set(self.state.get("deleted", []))
        self._loaded = False
        self._dirty = False
        self._save_at = 0.0
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
        with self.lock:
            if not self._loaded:
                return
            present = set(self.msgs)
            self.state["version"] = 2
            self.state["read"] = sorted(self.read & present)
            self.state["notified"] = sorted(self.notified & present)
            self.state["archived"] = sorted(self.archived & present)
            self.state["deleted"] = sorted(self.deleted & present)  # 压缩成功后自然清掉
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
        reset = (ino is not None and st.st_ino != ino) or st.st_size < off
        if reset:
            off = 0
        if st.st_size == off:
            return [], (st.st_ino, off), reset
        recs, off2 = desk.read_jsonl(path, off)
        return recs, (st.st_ino, off2), reset

    def poll(self) -> None:
        new: list[dict] = []
        with self.lock:
            changed = False
            recs, self._inbox_pos, reset = self._advance(self.inbox_path, self._inbox_pos)
            if reset:
                self.msgs.clear()
                changed = True
            for r in recs:
                m = normalize(r)
                if m["id"] in self.msgs:
                    continue
                self.msgs[m["id"]] = m
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

            first = not self._loaded
            self._loaded = True
            if new:
                for m in new:
                    self.notified.add(m["id"])
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
        self.flush_if_due()

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

    def counts(self) -> dict:
        with self.lock:
            vis = self.visible()
            return {
                "unread": sum(1 for m in vis if self.is_unread(m)),
                "open": sum(1 for m in vis if self.is_open(m)),
                "urgent": sum(1 for m in vis if self.is_urgent(m)),
                "unread_answers": sum(1 for m in vis if m["kind"] == "answer" and self.is_unread(m)),
                "unread_info": sum(1 for m in vis if m["kind"] == "info" and self.is_unread(m)),
                "archived": len(self.visible(archived=True)),
                "total": len(vis),
            }

    def summary(self, m: dict) -> dict:
        resp = self.responses.get(m["id"])
        return {
            "id": m["id"], "kind": m["kind"], "title": m["title"], "source": m["source"], "project": m["project"],
            "ts": m["_dt"].isoformat(), "priority": m["priority"], "snippet": m["_snippet"],
            "open": self.is_open(m), "answered": resp is not None, "unread": self.is_unread(m),
            "archived": m["id"] in self.archived,
            "choice": (resp or {}).get("choice"), "dismissed": bool((resp or {}).get("dismissed")),
            "resolved": bool((resp or {}).get("resolved")),
        }

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
            return d

    def search(self, q: str) -> list[str]:
        terms = q.lower().split()
        with self.lock:
            return [m["id"] for m in self.visible(archived=None) if all(t in m["_search"] for t in terms)]

    # ------------------------------------------------------------ 修改
    def _known(self, ids) -> list[str]:
        return [i for i in ids if i in self.msgs]

    def mark_read(self, ids, read: bool = True) -> int:
        with self.lock:
            ids = self._known(ids)
            before = len(self.read)
            if read:
                self.read.update(ids)
            else:
                self.read.difference_update(ids)
            n = abs(len(self.read) - before)
            if n:
                self.schedule_save()
                self._bump()
        if n:
            self._emit_changed()
        return n

    def mark_all_read(self, project: str | None = None) -> int:
        return self.mark_read([m["id"] for m in self.visible() if not project or m["project"] == project])

    def _dismiss_open(self, ids) -> None:
        """移走还在等回复的决定之前，先告诉等待的会话"用户跳过了"，免得它永远等下去。"""
        for mid in ids:
            m = self.msgs.get(mid)
            if m is not None and self.is_open(m):
                try:
                    rec = desk.write_response(mid, None, DISMISS_TEXT, m["source"], self.ddir,
                                              extra={"title": m["title"], "dismissed": True})
                    self.responses[mid] = rec
                except FileExistsError:
                    pass

    def resolve(self, ids) -> int:
        """标为已解决：还在等回复的决定写一条 resolved 回复（等待的会话会收到），所有选中的都标为已读。
        返回实际解决的决定数。"""
        done = 0
        with self.lock:
            ids = self._known(ids)
            for mid in ids:
                m = self.msgs[mid]
                if not self.is_open(m):
                    continue
                try:
                    rec = desk.write_response(mid, None, RESOLVE_TEXT, m["source"], self.ddir,
                                              extra={"title": m["title"], "resolved": True})
                    self.responses[mid] = rec
                    done += 1
                except FileExistsError:
                    pass
            self.read.update(ids)
            self.schedule_save()
            self._bump()
        self._emit_changed()
        return done

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
            ids = [m["id"] for m in self.visible() if not self.is_unread(m) and not self.is_open(m)
                   and (not project or m["project"] == project)]
        return self.archive(ids)

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
        失败（例如文件正被别的进程打开）没关系：state.json 里的删除标记照样让它们不显示，下次再试。"""
        with self.lock:
            dead = set(self.deleted)
        if not dead:
            return True
        try:
            with desk.file_lock(self.ddir):
                raw = self.inbox_path.read_bytes() if self.inbox_path.exists() else b""
                keep, dropped = [], 0
                for line in raw.splitlines(keepends=True):
                    s = line.strip()
                    if s:
                        try:
                            rec = json.loads(s.decode("utf-8-sig"))
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            rec = None
                        if isinstance(rec, dict) and normalize(rec)["id"] in dead:
                            dropped += 1
                            continue
                    keep.append(line if line.endswith(b"\n") else line + b"\n")
                if not dropped:
                    return True
                tmp = self.inbox_path.with_name(self.inbox_path.name + ".compact")
                with open(tmp, "wb") as f:
                    f.write(b"".join(keep))
                    f.flush()
                    os.fsync(f.fileno())
                _retry(lambda: os.replace(tmp, self.inbox_path))
        except (OSError, TimeoutError):
            return False
        self.poll()  # 文件号变了：整份重读，删掉的就不在 msgs 里了
        return True

    def submit(self, mid: str, choice: str | None, text: str) -> dict:
        """写回复；已回复过的抛 FileExistsError。"""
        with self.lock:
            m = self.msgs.get(mid)
            if m is None:
                raise KeyError("没有这条消息")
            if mid in self.responses:
                raise FileExistsError("这条已经回复过了")
            extra = {"title": m["title"]}
            if choice is not None:
                labels = [o["label"] for o in m["options"]]
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
        self.poll()
        return rec


def _retry(fn, attempts: int = 25, delay: float = 0.1):
    """Windows 上目标文件被别的进程短暂打开时 os.replace 会 PermissionError，稍等重试。"""
    for i in range(attempts):
        try:
            return fn()
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(delay)
