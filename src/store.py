"""数据层：增量读 inbox.jsonl / responses.jsonl，维护已读状态，写回复。"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal

import desk

KINDS = desk.KINDS


def _now() -> dt.datetime:
    return dt.datetime.now().astimezone()


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
    return m


class Store(QObject):
    changed = Signal()
    arrived = Signal(list)  # 新到、还没通知过的消息

    def __init__(self, ddir: Path, show_selftest: bool = False):
        super().__init__()
        self.ddir = Path(ddir)
        self.ddir.mkdir(parents=True, exist_ok=True)
        self.inbox_path = self.ddir / desk.INBOX
        self.resp_path = self.ddir / desk.RESPONSES
        self.state_path = self.ddir / desk.STATE
        self.show_selftest = show_selftest
        self.msgs: dict[str, dict] = {}
        self.responses: dict[str, dict] = {}
        self._inbox_pos = (None, 0)  # (st_ino, offset)
        self._resp_pos = (None, 0)
        self.state = self._load_state()
        self.read: set[str] = set(self.state.get("read", []))
        self.notified: set[str] = set(self.state.get("notified", []))
        self._loaded = False
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(400)
        self._save_timer.timeout.connect(self.save_state)

    # ------------------------------------------------------------ 状态文件
    def _load_state(self) -> dict:
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                st = json.load(f)
            return st if isinstance(st, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def save_state(self) -> None:
        if not self._loaded:
            return
        present = set(self.msgs)
        self.state["version"] = 1
        self.state["read"] = sorted(self.read & present)
        self.state["notified"] = sorted(self.notified & present)
        tmp = self.state_path.with_name(self.state_path.name + ".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.state_path)
        except OSError:
            pass

    def schedule_save(self) -> None:
        self._save_timer.start()

    def ui(self, key, default=None):
        return self.state.get("ui", {}).get(key, default)

    def set_ui(self, key, value) -> None:
        self.state.setdefault("ui", {})[key] = value
        self.schedule_save()

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
        changed = False
        new: list[dict] = []
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
            self.arrived.emit(new)
        if changed or first:
            self.changed.emit()

    # ------------------------------------------------------------ 查询
    def hidden(self, m: dict) -> bool:
        return (not self.show_selftest) and m["source"].lower().startswith("selftest")

    def visible(self) -> list[dict]:
        return [m for m in self.msgs.values() if not self.hidden(m)]

    def is_open(self, m: dict) -> bool:
        return m["kind"] == "decision" and m["id"] not in self.responses

    def is_unread(self, m: dict) -> bool:
        return m["id"] not in self.read

    def is_urgent(self, m: dict) -> bool:
        return self.is_unread(m) and (self.is_open(m) or m["priority"] == "high")

    def counts(self) -> dict:
        vis = self.visible()
        return {
            "unread": sum(1 for m in vis if self.is_unread(m)),
            "open": sum(1 for m in vis if self.is_open(m)),
            "urgent": sum(1 for m in vis if self.is_urgent(m)),
            "unread_answers": sum(1 for m in vis if m["kind"] == "answer" and self.is_unread(m)),
            "total": len(vis),
        }

    # ------------------------------------------------------------ 修改
    def mark_read(self, ids, read: bool = True) -> None:
        ids = [i for i in ids if i in self.msgs]
        before = len(self.read)
        if read:
            self.read.update(ids)
        else:
            self.read.difference_update(ids)
        if len(self.read) != before:
            self.schedule_save()
            self.changed.emit()

    def mark_all_read(self) -> None:
        self.mark_read([m["id"] for m in self.visible()])

    def submit(self, mid: str, choice: str | None, text: str) -> dict:
        """写回复；已回复过的抛 FileExistsError。"""
        m = self.msgs[mid]
        if mid in self.responses:
            raise FileExistsError("这条已经回复过了")
        extra = {"title": m["title"]}
        if choice is not None:
            labels = [o["label"] for o in m["options"]]
            if choice in labels:
                extra["choice_index"] = labels.index(choice) + 1
        rec = desk.write_response(mid, choice, text, m["source"], self.ddir, extra=extra)
        self.read.add(mid)
        self.schedule_save()
        self.poll()
        if mid not in self.responses:
            self.responses[mid] = rec
            self.changed.emit()
        return rec
