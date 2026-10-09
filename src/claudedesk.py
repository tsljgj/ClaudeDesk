"""ClaudeDesk：接收 Claude 会话发来的"待你决定 / 给你的回答 / 通知"的桌面程序（PySide6）。"""
from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import json
import os
import re
import subprocess
import sys
import traceback
from ctypes import wintypes
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
HERE = Path(__file__).resolve().parent
if not FROZEN:
    sys.path.insert(0, str(HERE.parent))
    sys.path.insert(0, str(HERE))

import desk  # noqa: E402
import icons  # noqa: E402
from store import Store  # noqa: E402

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, QTimer, QUrl, Signal  # noqa: E402
from PySide6.QtGui import (  # noqa: E402
    QAction, QBrush, QColor, QDesktopServices, QFont, QKeySequence, QPalette, QPen, QShortcut,
    QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument, QTextFormat, QTextFrameFormat,
)
from PySide6.QtNetwork import QLocalServer, QLocalSocket  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QAbstractItemView, QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMenu, QPlainTextEdit, QPushButton, QScrollArea, QSplitter,
    QStackedWidget, QStyle, QStyledItemDelegate, QSystemTrayIcon, QTextBrowser, QVBoxLayout, QWidget,
)

APP = "ClaudeDesk"
UI_FONT = "Microsoft YaHei UI"
MONO = ["Cascadia Mono", "Consolas", UI_FONT]
KIND_LABEL = {"decision": "决定", "answer": "回答", "info": "通知"}
F_DECIDE, F_ANSWER, F_ALL = 0, 1, 2


def app_dir() -> Path:
    return Path(sys.executable).resolve().parent if FROZEN else HERE.parent


# ------------------------------------------------------------------ Windows 小工具
if os.name == "nt":
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32

    class FLASHWINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("hwnd", wintypes.HWND), ("dwFlags", wintypes.DWORD),
                    ("uCount", wintypes.UINT), ("dwTimeout", wintypes.DWORD)]

    _user32.FlashWindowEx.argtypes = [ctypes.POINTER(FLASHWINFO)]
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    _user32.AllowSetForegroundWindow.argtypes = [wintypes.DWORD]
    _user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    _user32.BringWindowToTop.argtypes = [wintypes.HWND]
    _kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    _kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    _kernel32.SetProcessWorkingSetSize.argtypes = [wintypes.HANDLE, ctypes.c_size_t, ctypes.c_size_t]


def win_flash(hwnd: int, urgent: bool) -> None:
    """任务栏闪烁。urgent：一直闪到窗口被切到前台；否则闪 3 次后保持高亮。"""
    if os.name != "nt" or not hwnd:
        return
    FLASHW_TRAY, FLASHW_TIMERNOFG = 0x2, 0xC
    info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd,
                      FLASHW_TRAY | (FLASHW_TIMERNOFG if urgent else 0), 0 if urgent else 3, 0)
    _user32.FlashWindowEx(ctypes.byref(info))


def win_force_foreground(hwnd: int) -> None:
    """用户明确要求打开窗口时（重复启动 / 托盘 / 通知点击）把窗口切到前台。
    Windows 的前台锁会挡住后台进程的 SetForegroundWindow，临时挂到前台线程的输入队列上绕过。"""
    if os.name != "nt" or not hwnd:
        return
    fg = _user32.GetForegroundWindow()
    if fg == hwnd:
        return
    fg_tid = _user32.GetWindowThreadProcessId(fg, None) if fg else 0
    me = _kernel32.GetCurrentThreadId()
    attached = bool(fg_tid and fg_tid != me and _user32.AttachThreadInput(me, fg_tid, True))
    try:
        _user32.BringWindowToTop(hwnd)
        _user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            _user32.AttachThreadInput(me, fg_tid, False)


def win_stop_flash(hwnd: int) -> None:
    if os.name == "nt" and hwnd:
        info = FLASHWINFO(ctypes.sizeof(FLASHWINFO), hwnd, 0, 0, 0)
        _user32.FlashWindowEx(ctypes.byref(info))


def trim_working_set() -> None:
    if os.name == "nt":
        _kernel32.SetProcessWorkingSetSize(_kernel32.GetCurrentProcess(), ctypes.c_size_t(-1), ctypes.c_size_t(-1))


def startup_link() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup/ClaudeDesk.lnk"


def set_autostart(enable: bool) -> bool:
    link = startup_link()
    if not enable:
        try:
            link.unlink()
        except FileNotFoundError:
            pass
        return True
    exe = Path(sys.executable).resolve()
    q = lambda s: str(s).replace("'", "''")  # noqa: E731
    ps = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{q(link)}');"
          f"$s.TargetPath='{q(exe)}';$s.Arguments='--minimized';$s.WorkingDirectory='{q(exe.parent)}';"
          f"$s.IconLocation='{q(exe)},0';$s.Description='ClaudeDesk';$s.Save()")
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                       creationflags=0x08000000, capture_output=True)
    return r.returncode == 0 and link.exists()


# ------------------------------------------------------------------ 格式化
def fmt_time(t: dt.datetime) -> str:
    now = dt.datetime.now().astimezone()
    lt = t.astimezone()
    if lt.date() == now.date():
        return lt.strftime("%H:%M")
    if lt.year == now.year:
        return lt.strftime("%m-%d %H:%M")
    return lt.strftime("%Y-%m-%d")


def fmt_full(t: dt.datetime) -> str:
    return t.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def plain_summary(md: str, n: int = 120) -> str:
    s = re.sub(r"```.*?```", " ", md, flags=re.S)
    s = re.sub(r"(?m)^\s*\|?[\s:|-]+\|?\s*$", " ", s)  # 表格分隔行
    s = re.sub(r"[#>*_`|\-]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:n] + ("…" if len(s) > n else "")


def html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ------------------------------------------------------------------ Markdown 排版
def style_document(doc: QTextDocument) -> None:
    """setMarkdown 之后补样式：表格边框 / 表头底色、代码块底色与等宽字体、行距。"""
    seen_tables = set()
    code_bg = QColor("#F4F6F8")
    block = doc.begin()
    inline_ranges = []
    quote_blocks = []
    while block.isValid():
        cur = QTextCursor(block)
        table = cur.currentTable()
        if table is not None and table.firstPosition() not in seen_tables:
            seen_tables.add(table.firstPosition())
            tf = table.format()
            tf.setBorder(1)
            tf.setBorderStyle(QTextFrameFormat.BorderStyle_Solid)
            tf.setBorderBrush(QBrush(QColor("#D5DAE1")))
            tf.setBorderCollapse(True)
            tf.setCellSpacing(0)
            tf.setCellPadding(6)
            tf.setTopMargin(6)
            tf.setBottomMargin(10)
            table.setFormat(tf)
            for c in range(table.columns()):
                cell = table.cellAt(0, c)
                cf = cell.format().toTableCellFormat()
                cf.setBackground(QColor("#EEF2F6"))
                cell.setFormat(cf)
        bf = block.blockFormat()
        is_code = (bf.hasProperty(QTextFormat.BlockCodeFence) or bf.hasProperty(QTextFormat.BlockCodeLanguage)
                   or bf.nonBreakableLines())
        if is_code:
            nf = QTextBlockFormat(bf)
            nf.setBackground(code_bg)
            nf.setLeftMargin(bf.leftMargin() + 2)
            nf.setTopMargin(0)
            nf.setBottomMargin(0)
            cur.setBlockFormat(nf)
            sel = QTextCursor(block)
            sel.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
            cf = QTextCharFormat()
            cf.setFontFamilies(MONO)
            sel.mergeCharFormat(cf)
        else:
            if table is None:
                nf = QTextBlockFormat(bf)
                nf.setLineHeight(145, 1)  # ProportionalHeight
                if bf.hasProperty(QTextFormat.BlockQuoteLevel):
                    nf.setBackground(QColor("#F5F7FA"))
                    quote_blocks.append(block)
                cur.setBlockFormat(nf)
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid() and frag.charFormat().fontFixedPitch():
                    inline_ranges.append((frag.position(), frag.position() + frag.length()))
                it += 1
        block = block.next()
    for qb in quote_blocks:
        sel = QTextCursor(qb)
        sel.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        cf = QTextCharFormat()
        cf.setForeground(QColor("#475467"))
        sel.mergeCharFormat(cf)
    for a, b in inline_ranges:
        sel = QTextCursor(doc)
        sel.setPosition(a)
        sel.setPosition(b, QTextCursor.KeepAnchor)
        cf = QTextCharFormat()
        cf.setFontFamilies(MONO)
        cf.setBackground(QColor("#EDEFF2"))
        cf.setForeground(QColor("#B4233C"))
        sel.mergeCharFormat(cf)


def render_message(doc: QTextDocument, m: dict) -> None:
    doc.clear()
    doc.setDefaultFont(QFont(UI_FONT, 10))
    doc.setDocumentMargin(16)
    cur = QTextCursor(doc)
    if m.get("question"):
        ff = QTextFrameFormat()
        ff.setBackground(QColor("#F1F5F9"))
        ff.setBorder(1)
        ff.setBorderBrush(QBrush(QColor("#CBD5E1")))
        ff.setBorderStyle(QTextFrameFormat.BorderStyle_Solid)
        ff.setPadding(10)
        ff.setBottomMargin(14)
        cur.insertFrame(ff)
        lab = QTextCharFormat()
        lab.setFontWeight(QFont.Bold)
        lab.setForeground(QColor("#475569"))
        cur.insertText("你的问题", lab)
        cur.insertBlock()
        txt = QTextCharFormat()
        txt.setForeground(QColor("#0F172A"))
        cur.insertText(m["question"].strip(), txt)
        first = QTextCursor(doc.begin())  # 根框架开头那个空段落：压到 1px，避免问题框上方留白
        if doc.begin().text() == "" and first.currentFrame() == doc.rootFrame():
            bf0 = QTextBlockFormat()
            bf0.setLineHeight(1, 2)  # FixedHeight
            bf0.setTopMargin(0)
            bf0.setBottomMargin(0)
            first.setBlockFormat(bf0)
            cf0 = QTextCharFormat()
            cf0.setFontPointSize(1)
            first.setBlockCharFormat(cf0)
        cur = QTextCursor(doc)
        cur.movePosition(QTextCursor.End)
        cur.setCharFormat(QTextCharFormat())
    body = m.get("body") or ""
    if body.strip():
        cur.insertMarkdown(body, QTextDocument.MarkdownDialectGitHub)
    else:
        gray = QTextCharFormat()
        gray.setForeground(QColor("#98A2B3"))
        cur.insertText("（没有正文）", gray)
    style_document(doc)


# ------------------------------------------------------------------ 列表绘制
class MessageDelegate(QStyledItemDelegate):
    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        self.store = store
        self.f_title = QFont(UI_FONT, 10)
        self.f_title_b = QFont(UI_FONT, 10)
        self.f_title_b.setBold(True)
        self.f_meta = QFont(UI_FONT, 8)
        self.f_tag = QFont(UI_FONT, 8)
        self.f_tag.setBold(True)

    def sizeHint(self, option, index):
        return QSize(260, 64)

    def _pill(self, p, right: float, y: float, text: str, fg: str, bg: str) -> float:
        p.setFont(self.f_tag)
        w = p.fontMetrics().horizontalAdvance(text) + 12
        rect = QRectF(right - w, y, w, 18)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(bg))
        p.drawRoundedRect(rect, 9, 9)
        p.setPen(QColor(fg))
        p.drawText(rect, Qt.AlignCenter, text)
        return right - w - 6

    def paint(self, p, option, index):
        m = self.store.msgs.get(index.data(Qt.UserRole))
        if m is None:
            return
        p.save()
        p.setRenderHint(p.RenderHint.Antialiasing)
        r = option.rect
        selected = bool(option.state & QStyle.State_Selected)
        hover = bool(option.state & QStyle.State_MouseOver)
        is_open = self.store.is_open(m)
        unread = self.store.is_unread(m)
        if selected:
            bg = QColor("#DBE7FB")
        elif is_open:
            bg = QColor("#FFF3DC") if not hover else QColor("#FFEBC7")
        else:
            bg = QColor("#F3F4F6") if hover else QColor("#FFFFFF")
        p.fillRect(r, bg)
        if is_open:
            p.fillRect(QRectF(r.left(), r.top(), 4, r.height()), QColor("#F59E0B"))
        elif m["priority"] == "high" and unread:
            p.fillRect(QRectF(r.left(), r.top(), 4, r.height()), QColor("#E5484D"))
        p.setPen(QPen(QColor("#ECEEF1")))
        p.drawLine(r.left(), r.bottom(), r.right(), r.bottom())

        x = r.left() + 14
        if unread:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#2563EB"))
            p.drawEllipse(QRectF(x - 1, r.top() + 15, 8, 8))
        x += 13
        right = r.right() - 10.0
        # 右上角标签
        tag_right = right
        if is_open:
            tag_right = self._pill(p, tag_right, r.top() + 10, "待决定", "#8A4B00", "#FFD99A")
        elif m["kind"] == "decision":
            tag_right = self._pill(p, tag_right, r.top() + 10, "已回复", "#116B3A", "#D3F2DF")
        if m["priority"] == "high":
            tag_right = self._pill(p, tag_right, r.top() + 10, "高", "#FFFFFF", "#E5484D")
        # 标题
        p.setFont(self.f_title_b if unread or is_open else self.f_title)
        p.setPen(QColor("#101828") if unread or is_open else QColor("#344054"))
        title_rect = QRectF(x, r.top() + 8, tag_right - x, 22)
        p.drawText(title_rect, Qt.AlignVCenter | Qt.AlignLeft,
                   p.fontMetrics().elidedText(m["title"], Qt.ElideRight, int(title_rect.width())))
        # 第二行：类型 · 来源 · 时间
        p.setFont(self.f_meta)
        p.setPen(QColor("#667085"))
        meta = f"{KIND_LABEL[m['kind']]} · {m['source']}"
        tstr = fmt_time(m["_dt"])
        tw = p.fontMetrics().horizontalAdvance(tstr)
        p.drawText(QRectF(right - tw, r.top() + 36, tw, 18), Qt.AlignVCenter | Qt.AlignRight, tstr)
        mrect = QRectF(x, r.top() + 36, right - tw - 10 - x, 18)
        p.drawText(mrect, Qt.AlignVCenter | Qt.AlignLeft,
                   p.fontMetrics().elidedText(meta, Qt.ElideRight, int(mrect.width())))
        p.restore()


# ------------------------------------------------------------------ 选项卡片
class OptionCard(QFrame):
    clicked = Signal(int)

    def __init__(self, idx: int, label: str, desc: str, recommended: bool):
        super().__init__()
        self.idx = idx
        self.label = label
        self.setObjectName("optionCard")
        self.setProperty("checked", False)
        self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(10)
        self.dot = QLabel("○")
        self.dot.setObjectName("optDot")
        self.dot.setFixedWidth(18)
        self.dot.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        lay.addWidget(self.dot)
        col = QVBoxLayout()
        col.setSpacing(2)
        row = QHBoxLayout()
        row.setSpacing(8)
        t = QLabel(f"{idx + 1}. {html_escape(label)}")
        t.setObjectName("optTitle")
        t.setTextFormat(Qt.RichText)
        t.setWordWrap(True)
        row.addWidget(t, 1)
        if recommended:
            rec = QLabel("推荐")
            rec.setObjectName("recTag")
            row.addWidget(rec, 0, Qt.AlignTop)
        col.addLayout(row)
        if desc:
            d = QLabel(desc)
            d.setObjectName("optDesc")
            d.setWordWrap(True)
            d.setTextInteractionFlags(Qt.TextSelectableByMouse)
            col.addWidget(d)
        lay.addLayout(col, 1)

    def setChecked(self, on: bool) -> None:
        self.setProperty("checked", on)
        self.dot.setText("●" if on else "○")
        for w in (self, self.dot):
            w.style().unpolish(w)
            w.style().polish(w)

    def mousePressEvent(self, e):
        if self.isEnabled() and e.button() == Qt.LeftButton:
            self.clicked.emit(self.idx)
        super().mousePressEvent(e)

    def click(self) -> None:
        if self.isEnabled():
            self.clicked.emit(self.idx)


class DecisionPanel(QFrame):
    submitted = Signal(str, object, str)  # id, choice, text

    def __init__(self):
        super().__init__()
        self.setObjectName("decisionPanel")
        self.mid = None
        self.choice = None
        self.answered = False
        self.allow_text = False
        self.cards: list[OptionCard] = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(8)
        self.head = QLabel("请选择")
        self.head.setObjectName("panelHead")
        outer.addWidget(self.head)
        self.cards_box = QVBoxLayout()
        self.cards_box.setSpacing(6)
        outer.addLayout(self.cards_box)
        self.text = QPlainTextEdit()
        self.text.setObjectName("replyText")
        self.text.setPlaceholderText("补充说明（可选）")
        self.text.setFixedHeight(64)
        self.text.textChanged.connect(self._update_enabled)
        outer.addWidget(self.text)
        self.done = QLabel()
        self.done.setObjectName("doneBox")
        self.done.setWordWrap(True)
        self.done.setTextInteractionFlags(Qt.TextSelectableByMouse)
        outer.addWidget(self.done)
        # 提交行放在滚动区外面（由主窗口摆在面板下方），选项再多也看得见"提交"
        self.footer = QWidget()
        self.footer.setObjectName("panelFooter")
        row = QHBoxLayout(self.footer)
        row.setContentsMargins(16, 8, 16, 10)
        self.hint = QLabel("Ctrl+Enter 提交")
        self.hint.setObjectName("hint")
        row.addWidget(self.hint)
        row.addStretch(1)
        self.submit_btn = QPushButton("提交")
        self.submit_btn.setObjectName("primary")
        self.submit_btn.setCursor(Qt.PointingHandCursor)
        self.submit_btn.clicked.connect(self._submit)
        row.addWidget(self.submit_btn)
        outer.addStretch(1)
        sc = QShortcut(QKeySequence("Ctrl+Return"), self.text)
        sc.activated.connect(self._submit)
        sc2 = QShortcut(QKeySequence("Ctrl+Enter"), self.text)
        sc2.activated.connect(self._submit)

    def load(self, m: dict, response: dict | None) -> None:
        self.mid = m["id"]
        self.choice = None
        for c in self.cards:
            c.setParent(None)
            c.deleteLater()
        self.cards = []
        for i, o in enumerate(m["options"]):
            card = OptionCard(i, o["label"], o["description"], m["recommended"] == i + 1)
            card.clicked.connect(self._pick)
            self.cards_box.addWidget(card)
            self.cards.append(card)
        self.head.setText("请选择一个选项" if m["options"] else "请写下你的回复")
        self.text.setPlaceholderText("补充说明（可选）" if m["options"] else "写下你的回复")
        self.text.clear()
        answered = response is not None
        self.answered = answered
        self.allow_text = m["allow_text"] and not answered
        self.text.setVisible(self.allow_text)
        self.submit_btn.setVisible(not answered)
        self.hint.setVisible(not answered and m["allow_text"])
        self.done.setVisible(answered)
        self.footer.setVisible(not answered)
        if answered:
            self.head.setText("你的回复")
            ch = response.get("choice")
            for c in self.cards:
                c.setChecked(c.label == ch)
                c.setEnabled(False)
            parts = [f"<b>已回复</b>　<span style='color:#475467'>{fmt_full(desk.parse_ts(response.get('ts')) or m['_dt'])}</span>"]
            if ch:
                parts.append(f"选择：<b>{html_escape(str(ch))}</b>")
            if response.get("text"):
                parts.append("补充：" + html_escape(str(response["text"])).replace("\n", "<br>"))
            self.done.setText("<br>".join(parts))
        self._update_enabled()

    def _pick(self, idx: int) -> None:
        self.choice = self.cards[idx].label
        for c in self.cards:
            c.setChecked(c.idx == idx)
        self._update_enabled()

    def _update_enabled(self) -> None:
        ok = self.choice is not None or (self.allow_text and bool(self.text.toPlainText().strip()))
        self.submit_btn.setEnabled(ok and not self.answered)

    def _submit(self) -> None:
        if self.answered or not self.submit_btn.isEnabled() or self.mid is None:
            return
        self.submit_btn.setEnabled(False)
        self.submitted.emit(self.mid, self.choice, self.text.toPlainText().strip() if self.allow_text else "")


# ------------------------------------------------------------------ 主窗口
STYLE = """
QMainWindow, #central { background: #F5F6F8; }
#leftPanel { background: #FFFFFF; }
QPushButton#filterBtn { border: 1px solid #D0D5DD; background: #FFFFFF; color: #344054;
    padding: 5px 9px; border-radius: 6px; }
QPushButton#filterBtn:hover { background: #F2F4F7; }
QPushButton#filterBtn:checked { background: #1F2937; color: #FFFFFF; border-color: #1F2937; }
QLineEdit { border: 1px solid #D0D5DD; border-radius: 6px; padding: 5px 8px; background: #FFFFFF; }
QLineEdit:focus { border-color: #2563EB; }
QListWidget { border: none; background: #FFFFFF; outline: 0; }
QPushButton#plain { border: 1px solid #D0D5DD; background: #FFFFFF; color: #344054; padding: 5px 12px;
    border-radius: 6px; }
QPushButton#plain:hover { background: #F2F4F7; }
QPushButton#primary { background: #2563EB; color: #FFFFFF; border: none; border-radius: 6px;
    padding: 7px 26px; font-weight: bold; }
QPushButton#primary:hover { background: #1D4ED8; }
QPushButton#primary:disabled { background: #A9C0F2; }
#detail { background: #FFFFFF; }
#titleLabel { color: #101828; }
#metaLabel { color: #475467; }
QTextBrowser { border: none; background: #FFFFFF; selection-background-color: #BFD4FA; }
#decisionPanel { background: #FAFBFC; border-top: 1px solid #E4E7EC; }
#panelHead { color: #101828; font-weight: bold; }
#optionCard { border: 1px solid #D0D5DD; border-radius: 8px; background: #FFFFFF; }
#optionCard:hover { border-color: #84A9F0; }
#optionCard[checked="true"] { border: 2px solid #2563EB; background: #EEF4FF; }
#optionCard:disabled { background: #F9FAFB; }
#optionCard[checked="true"]:disabled { border: 2px solid #12B76A; background: #ECFDF3; }
#optDot { color: #98A2B3; font-size: 13pt; }
#optionCard[checked="true"] #optDot { color: #2563EB; }
#optTitle { color: #101828; font-weight: bold; }
#optDesc { color: #475467; }
#recTag { background: #DCFCE7; color: #166534; border-radius: 9px; padding: 1px 8px; font-weight: bold; }
QPlainTextEdit#replyText { border: 1px solid #D0D5DD; border-radius: 6px; background: #FFFFFF; padding: 4px; }
QPlainTextEdit#replyText:focus { border-color: #2563EB; }
#doneBox { background: #ECFDF3; border: 1px solid #ABEFC6; border-radius: 6px; padding: 8px 10px; color: #054F31; }
#hint { color: #98A2B3; }
#panelFooter { background: #FAFBFC; border-top: 1px solid #EEF0F3; }
#placeholder { color: #98A2B3; background: #FFFFFF; }
QSplitter::handle { background: #E4E7EC; }
QScrollArea { border: none; background: #FAFBFC; }
"""


class MainWindow(QMainWindow):
    def __init__(self, store: Store):
        super().__init__()
        self.store = store
        self.current: str | None = None
        self._rendered = (None, None)
        self.quitting = False
        self.tray: Tray | None = None
        self.setWindowTitle(APP)
        self.setStyleSheet(STYLE)

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        self.split = QSplitter(Qt.Horizontal)
        self.split.setHandleWidth(1)
        root.addWidget(self.split)

        # 左侧
        left = QWidget()
        left.setObjectName("leftPanel")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(10, 10, 10, 8)
        lv.setSpacing(8)
        frow = QHBoxLayout()
        frow.setSpacing(6)
        self.filter_group = QButtonGroup(self)
        self.filter_btns = []
        for i, name in enumerate(("待你决定", "给你的回答", "全部")):
            b = QPushButton(name)
            b.setObjectName("filterBtn")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.filter_group.addButton(b, i)
            self.filter_btns.append(b)
            frow.addWidget(b)
        frow.addStretch(1)
        lv.addLayout(frow)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索标题、正文、来源…")
        self.search.setClearButtonEnabled(True)
        lv.addWidget(self.search)
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list.setUniformItemSizes(True)
        self.list.setMouseTracking(True)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list.setItemDelegate(MessageDelegate(store, self.list))
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._list_menu)
        lv.addWidget(self.list, 1)
        brow = QHBoxLayout()
        self.count_label = QLabel()
        self.count_label.setObjectName("hint")
        brow.addWidget(self.count_label)
        brow.addStretch(1)
        self.all_read_btn = QPushButton("全部标为已读")
        self.all_read_btn.setObjectName("plain")
        self.all_read_btn.clicked.connect(self.store.mark_all_read)
        brow.addWidget(self.all_read_btn)
        lv.addLayout(brow)
        self.split.addWidget(left)

        # 右侧
        self.stack = QStackedWidget()
        ph = QLabel("在左边选一条消息")
        ph.setObjectName("placeholder")
        ph.setAlignment(Qt.AlignCenter)
        self.stack.addWidget(ph)
        detail = QWidget()
        detail.setObjectName("detail")
        dv = QVBoxLayout(detail)
        dv.setContentsMargins(0, 0, 0, 0)
        dv.setSpacing(0)
        head = QWidget()
        hv = QVBoxLayout(head)
        hv.setContentsMargins(18, 14, 18, 8)
        hv.setSpacing(4)
        self.title_label = QLabel()
        self.title_label.setObjectName("titleLabel")
        self.title_label.setWordWrap(True)
        self.title_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        tf = QFont(UI_FONT, 14)
        tf.setBold(True)
        self.title_label.setFont(tf)
        hv.addWidget(self.title_label)
        mrow = QHBoxLayout()
        self.meta_label = QLabel()
        self.meta_label.setObjectName("metaLabel")
        self.meta_label.setTextFormat(Qt.RichText)
        mrow.addWidget(self.meta_label, 1)
        self.read_btn = QPushButton("标为未读")
        self.read_btn.setObjectName("plain")
        self.read_btn.clicked.connect(self._toggle_read)
        mrow.addWidget(self.read_btn)
        hv.addLayout(mrow)
        dv.addWidget(head)
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background:#E4E7EC;")
        dv.addWidget(line)
        self.vsplit = QSplitter(Qt.Vertical)
        self.vsplit.setHandleWidth(1)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.vsplit.addWidget(self.browser)
        self.panel = DecisionPanel()
        self.panel.submitted.connect(self._on_submit)
        self.panel_scroll = QScrollArea()
        self.panel_scroll.setWidgetResizable(True)
        self.panel_scroll.setWidget(self.panel)
        self.vsplit.addWidget(self.panel_scroll)
        self.vsplit.setStretchFactor(0, 3)
        self.vsplit.setStretchFactor(1, 2)
        self.vsplit.setCollapsible(0, False)
        dv.addWidget(self.vsplit, 1)
        dv.addWidget(self.panel.footer)
        self.stack.addWidget(detail)
        self.split.addWidget(self.stack)
        self.split.setStretchFactor(0, 0)
        self.split.setStretchFactor(1, 1)
        self.split.setCollapsible(0, False)
        self.split.setCollapsible(1, False)

        # 状态恢复
        self.resize(1180, 760)
        geo = store.ui("geometry")
        if geo:
            try:
                self.restoreGeometry(bytes.fromhex(geo))
            except ValueError:
                pass
        sp = store.ui("split")
        if sp:
            self.split.restoreState(bytes.fromhex(sp))
        else:
            self.split.setSizes([400, 780])
        f = store.ui("filter", F_DECIDE)
        self.filter_btns[f if f in (0, 1, 2) else 0].setChecked(True)

        self.filter_group.idClicked.connect(self._filter_changed)
        self.search.textChanged.connect(self.refresh_list)
        self.list.itemSelectionChanged.connect(self._selection_changed)
        store.changed.connect(self.on_store_changed)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: (self.search.setFocus(), self.search.selectAll()))
        self.on_store_changed()

    # ---------------------------------------------------------- 列表
    def filter_id(self) -> int:
        return self.filter_group.checkedId()

    def visible_messages(self) -> list[dict]:
        f = self.filter_id()
        items = self.store.visible()
        if f == F_DECIDE:
            items = [m for m in items if m["kind"] == "decision"]
        elif f == F_ANSWER:
            items = [m for m in items if m["kind"] == "answer"]
        terms = self.search.text().lower().split()
        if terms:
            items = [m for m in items if all(t in m["_search"] for t in terms)]
        if f == F_ANSWER:
            items.sort(key=lambda m: m["_dt"], reverse=True)
        else:
            items.sort(key=lambda m: m["_dt"], reverse=True)
            items.sort(key=lambda m: 0 if self.store.is_open(m) else 1)
        return items

    def refresh_list(self) -> None:
        items = self.visible_messages()
        self.list.blockSignals(True)
        self.list.clear()
        sel_row = -1
        for i, m in enumerate(items):
            it = QListWidgetItem()
            it.setData(Qt.UserRole, m["id"])
            self.list.addItem(it)
            if m["id"] == self.current:
                sel_row = i
        if sel_row >= 0:
            self.list.setCurrentRow(sel_row)
        self.list.blockSignals(False)
        self.count_label.setText(f"{len(items)} 条")

    def update_counts(self) -> None:
        c = self.store.counts()
        names = (("待你决定", c["open"]), ("给你的回答", c["unread_answers"]), ("全部", c["unread"]))
        for b, (n, k) in zip(self.filter_btns, names):
            b.setText(f"{n} {k}" if k else n)
        bits = []
        if c["open"]:
            bits.append(f"待决定 {c['open']}")
        if c["unread"]:
            bits.append(f"未读 {c['unread']}")
        self.setWindowTitle(APP + ("　—　" + " · ".join(bits) if bits else ""))

    def on_store_changed(self) -> None:
        self.refresh_list()
        self.update_counts()
        if self.current and self.current in self.store.msgs:
            m = self.store.msgs[self.current]
            key = (self.current, self.current in self.store.responses)
            if key != self._rendered:
                self.show_message(self.current, mark=False)
            self.read_btn.setText("标为未读" if not self.store.is_unread(m) else "标为已读")
        elif self.current:
            self.current = None
            self.stack.setCurrentIndex(0)
        if self.tray:
            self.tray.refresh()

    def _filter_changed(self, fid: int) -> None:
        self.store.set_ui("filter", fid)
        self.refresh_list()

    def _selection_changed(self) -> None:
        items = self.list.selectedItems()
        if items:
            self.show_message(items[0].data(Qt.UserRole), mark=True)

    def _list_menu(self, pos) -> None:
        it = self.list.itemAt(pos)
        if not it:
            return
        mid = it.data(Qt.UserRole)
        m = self.store.msgs.get(mid)
        if not m:
            return
        menu = QMenu(self)
        if self.store.is_unread(m):
            menu.addAction("标为已读", lambda: self.store.mark_read([mid]))
        else:
            menu.addAction("标为未读", lambda: self.store.mark_read([mid], False))
        menu.exec(self.list.viewport().mapToGlobal(pos))

    def select_message(self, mid: str) -> bool:
        if mid not in self.store.msgs:
            return False
        if self.search.text():
            self.search.clear()
        m = self.store.msgs[mid]
        if not any(x["id"] == mid for x in self.visible_messages()):
            target = F_DECIDE if m["kind"] == "decision" else F_ANSWER if m["kind"] == "answer" else F_ALL
            self.filter_btns[target].setChecked(True)
            self.refresh_list()
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == mid:
                self.list.setCurrentRow(i)
                self.list.scrollToItem(self.list.item(i))
                break
        self.show_message(mid, mark=True)
        return True

    # ---------------------------------------------------------- 详情
    def show_message(self, mid: str, mark: bool) -> None:
        m = self.store.msgs.get(mid)
        if not m:
            return
        changed_msg = mid != self.current
        self.current = mid
        resp = self.store.responses.get(mid)
        self.title_label.setText(m["title"])
        kind_colors = {"decision": ("#8A4B00", "#FFE7BA"), "answer": ("#1E40AF", "#DBEAFE"),
                       "info": ("#344054", "#EAECF0")}
        fg, bg = kind_colors[m["kind"]]
        meta = (f"<span style='background:{bg};color:{fg};font-weight:bold'>&nbsp;{KIND_LABEL[m['kind']]}&nbsp;</span>"
                f"&nbsp;&nbsp;来源 <b>{html_escape(m['source'])}</b>&nbsp;&nbsp;·&nbsp;&nbsp;{fmt_full(m['_dt'])}")
        if m["priority"] == "high":
            meta += "&nbsp;&nbsp;<span style='background:#E5484D;color:white;font-weight:bold'>&nbsp;高优先级&nbsp;</span>"
        if m["kind"] == "decision":
            meta += ("&nbsp;&nbsp;<span style='color:#12B76A;font-weight:bold'>已回复</span>" if resp else
                     "&nbsp;&nbsp;<span style='color:#B54708;font-weight:bold'>等待你的决定</span>")
        self.meta_label.setText(meta)
        if changed_msg or self._rendered[0] != mid:
            render_message(self.browser.document(), m)
            self.browser.moveCursor(QTextCursor.Start)
            self.browser.verticalScrollBar().setValue(0)
            QTimer.singleShot(0, lambda: self.browser.verticalScrollBar().setValue(0))
        if m["kind"] == "decision":
            self.panel.load(m, resp)
            self.panel_scroll.show()
            if changed_msg:
                total = max(self.vsplit.height(), 400)
                want = min(self.panel.sizeHint().height() + 4, int(total * 0.55))
                self.vsplit.setSizes([total - want, want])
        else:
            self.panel_scroll.hide()
            self.panel.footer.hide()
        self._rendered = (mid, resp is not None)
        self.stack.setCurrentIndex(1)
        if mark and self.store.is_unread(m):
            self.store.mark_read([mid])
        self.read_btn.setText("标为未读" if not self.store.is_unread(m) else "标为已读")

    def _toggle_read(self) -> None:
        if not self.current:
            return
        m = self.store.msgs[self.current]
        self.store.mark_read([self.current], read=self.store.is_unread(m))

    def _on_submit(self, mid: str, choice, text: str) -> None:
        try:
            self.store.submit(mid, choice, text)
        except FileExistsError:
            pass
        except Exception as e:  # noqa: BLE001
            self.panel.done.setText(f"写回复失败：{html_escape(str(e))}")
            self.panel.done.show()
            self.panel.submit_btn.setEnabled(True)
            return
        self._rendered = (None, None)
        self.show_message(mid, mark=False)

    # ---------------------------------------------------------- 窗口行为
    def bring_to_front(self) -> None:
        st = self.windowState()
        if st & Qt.WindowMinimized:
            self.setWindowState((st & ~Qt.WindowMinimized) | Qt.WindowActive)
        self.show()
        self.raise_()
        self.activateWindow()
        win_force_foreground(int(self.winId()))
        win_stop_flash(int(self.winId()))

    def show_for_flash(self) -> None:
        """窗口藏在托盘时，以最小化、不抢焦点的方式放回任务栏，好让任务栏按钮闪。"""
        if not self.isVisible():
            self.setWindowState(Qt.WindowMinimized)
            self.show()

    def closeEvent(self, e) -> None:
        self.save_ui()
        if self.quitting:
            e.accept()
            return
        e.ignore()
        self.hide()
        if self.tray and not self.store.state.get("tray_hint_shown"):
            self.tray.showMessage(APP, "ClaudeDesk 还在托盘里运行，有新消息会提醒你。右键托盘图标可以退出。",
                                  QSystemTrayIcon.Information, 5000)
            self.store.state["tray_hint_shown"] = True
            self.store.schedule_save()
        QTimer.singleShot(300, trim_working_set)

    def changeEvent(self, e) -> None:
        if e.type() == QEvent.ActivationChange and self.isActiveWindow():
            win_stop_flash(int(self.winId()))
        super().changeEvent(e)

    def save_ui(self) -> None:
        self.store.set_ui("geometry", bytes(self.saveGeometry().data()).hex())
        self.store.set_ui("split", bytes(self.split.saveState().data()).hex())


# ------------------------------------------------------------------ 托盘
class Tray(QSystemTrayIcon):
    def __init__(self, win: MainWindow, store: Store):
        super().__init__()
        self.win = win
        self.store = store
        self.toast_target: str | None = None
        self._phase = False
        self._icon_key = None
        self.blink = QTimer(self)
        self.blink.setInterval(650)
        self.blink.timeout.connect(self._blink)
        menu = QMenu()
        menu.addAction("打开 ClaudeDesk", self.win.bring_to_front)
        menu.addAction("全部标为已读", self.store.mark_all_read)
        menu.addSeparator()
        self.auto_act = QAction("开机自启", menu)
        self.auto_act.setCheckable(True)
        self.auto_act.setChecked(startup_link().exists())
        self.auto_act.setEnabled(FROZEN)
        self.auto_act.toggled.connect(self._toggle_autostart)
        menu.addAction(self.auto_act)
        menu.addAction("打开数据目录", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(store.ddir))))
        menu.addSeparator()
        menu.addAction("退出", self.quit_app)
        self._menu = menu
        self.setContextMenu(menu)
        self.activated.connect(self._activated)
        self.messageClicked.connect(self._message_clicked)
        self.refresh()

    def _toggle_autostart(self, on: bool) -> None:
        set_autostart(on)
        self.auto_act.blockSignals(True)
        self.auto_act.setChecked(startup_link().exists())
        self.auto_act.blockSignals(False)

    def _activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.win.bring_to_front()

    def _message_clicked(self) -> None:
        self.win.bring_to_front()
        if self.toast_target:
            self.win.select_message(self.toast_target)

    def quit_app(self) -> None:
        self.win.quitting = True
        self.win.save_ui()
        self.store.save_state()
        self.hide()
        QApplication.quit()

    def current_icon_args(self):
        c = self.store.counts()
        alert = c["urgent"] > 0 and self._phase
        return (c["unread"], alert, c["open"] > 0)

    def refresh(self) -> None:
        c = self.store.counts()
        if c["urgent"] > 0:
            if not self.blink.isActive():
                self.blink.start()
        else:
            self.blink.stop()
            self._phase = False
        self._apply_icon()
        tip = [APP]
        if c["open"]:
            tip.append(f"待你决定 {c['open']}")
        tip.append(f"未读 {c['unread']}")
        self.setToolTip("\n".join(tip))

    def _apply_icon(self) -> None:
        key = self.current_icon_args()
        if key != self._icon_key:
            self._icon_key = key
            icon = icons.make_icon(*key)
            self.setIcon(icon)
            if not key[1]:
                self.win.setWindowIcon(icon)

    def _blink(self) -> None:
        self._phase = not self._phase
        self._apply_icon()

    def notify(self, msgs: list[dict]) -> None:
        if not msgs:
            return
        urgent = [m for m in msgs if self.store.is_urgent(m)]
        target = (urgent or msgs)[-1]
        self.toast_target = target["id"]
        if len(msgs) == 1:
            m = msgs[0]
            head = {"decision": "需要你决定", "answer": "新回答", "info": "通知"}[m["kind"]]
            title = f"{head}：{m['title']}"
            text = f"[{m['source']}] " + (plain_summary(m["question"], 60) + " → " if m["question"] else "") \
                + plain_summary(m["body"], 100)
        else:
            nd = sum(1 for m in msgs if m["kind"] == "decision")
            title = f"ClaudeDesk：{len(msgs)} 条新消息" + (f"（{nd} 条待决定）" if nd else "")
            text = "\n".join(f"· [{m['source']}] {m['title']}" for m in msgs[-4:])
        # 注意：Windows 上 showMessage 传自定义 QIcon 时通知不会弹出（实测），只能用系统图标
        self.showMessage(title[:63], text[:250] or " ",
                         QSystemTrayIcon.Warning if urgent else QSystemTrayIcon.Information,
                         15000 if urgent else 7000)
        if not (self.win.isVisible() and self.win.isActiveWindow()):
            self.win.show_for_flash()
            win_flash(int(self.win.winId()), urgent=bool(urgent))
        self.refresh()


# ------------------------------------------------------------------ 控制通道（单实例 + 自测）
class Controller:
    def __init__(self, win: MainWindow, tray: Tray, store: Store, name: str):
        self.win, self.tray, self.store = win, tray, store
        self.server = QLocalServer()
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
        self.ok = self.server.listen(name)
        self.server.newConnection.connect(self._new)
        self._bufs = {}

    def _new(self) -> None:
        while self.server.hasPendingConnections():
            s = self.server.nextPendingConnection()
            self._bufs[id(s)] = bytearray()
            s.readyRead.connect(lambda s=s: self._read(s))
            s.disconnected.connect(lambda s=s: (self._bufs.pop(id(s), None), s.deleteLater()))

    def _read(self, s: QLocalSocket) -> None:
        buf = self._bufs.setdefault(id(s), bytearray())
        buf += bytes(s.readAll().data())
        if b"\n" not in buf:
            return
        line = bytes(buf[: buf.index(b"\n")])
        try:
            cmd = json.loads(line.decode("utf-8"))
            res = self.dispatch(cmd)
        except Exception as e:  # noqa: BLE001
            res = {"ok": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()}
        s.write((json.dumps(res, ensure_ascii=False) + "\n").encode("utf-8"))
        s.flush()
        s.waitForBytesWritten(2000)
        s.disconnectFromServer()

    def state(self) -> dict:
        c = self.store.counts()
        hwnd = int(self.win.winId())
        return {
            "ok": True, "counts": c, "window_title": self.win.windowTitle(), "tooltip": self.tray.toolTip(),
            "visible": self.win.isVisible(), "minimized": self.win.isMinimized(),
            "active": self.win.isActiveWindow(),
            "foreground_is_us": bool(os.name == "nt" and _user32.GetForegroundWindow() == hwnd),
            "blinking": self.tray.blink.isActive(), "tray_visible": self.tray.isVisible(),
            "filter": self.win.filter_id(), "current": self.win.current,
            "list": [self.win.list.item(i).data(Qt.UserRole) for i in range(self.win.list.count())],
            "filter_labels": [b.text() for b in self.win.filter_btns],
            "pid": os.getpid(),
        }

    def dispatch(self, cmd: dict) -> dict:
        op = cmd.get("op")
        app = QApplication.instance()
        if op == "noop":
            return {"ok": True}
        if op == "activate":
            self.win.bring_to_front()
            return {"ok": True}
        if op == "state":
            return self.state()
        if op == "hide":
            self.win.close()
            app.processEvents()
            return self.state()
        if op == "filter":
            self.win.filter_btns[int(cmd.get("filter", 2))].setChecked(True)
            self.win.search.setText(cmd.get("search", ""))
            self.win.refresh_list()
            return self.state()
        if op == "select":
            return {"ok": self.win.select_message(cmd["id"]), **self.state()}
        if op == "screenshot":
            # 默认不抢焦点：窗口藏着就以"不激活"方式临时显示，截完再藏回去
            was_visible = self.win.isVisible() and not self.win.isMinimized()
            was_minimized = self.win.isVisible() and self.win.isMinimized()
            if cmd.get("show") == "activate":
                self.win.bring_to_front()
            elif not was_visible:
                self.win.setAttribute(Qt.WA_ShowWithoutActivating, True)
                self.win.setWindowState(self.win.windowState() & ~Qt.WindowMinimized)
                self.win.show()
                self.win.setAttribute(Qt.WA_ShowWithoutActivating, False)
            if cmd.get("filter") is not None:
                self.win.filter_btns[int(cmd["filter"])].setChecked(True)
                self.win.refresh_list()
            if cmd.get("id"):
                self.win.select_message(cmd["id"])
            for _ in range(5):
                app.processEvents()
            self.win.grab().save(cmd["path"], "PNG")
            if cmd.get("tray_path"):
                self.tray.icon().pixmap(64, 64).save(cmd["tray_path"], "PNG")
            st = self.state()
            if not was_visible and cmd.get("show") != "activate" and cmd.get("restore", True):
                if was_minimized:
                    self.win.setWindowState(self.win.windowState() | Qt.WindowMinimized)
                else:
                    self.win.hide()
            return {"ok": True, **st}
        if op == "reply":
            # 走界面路径：选中消息 → 点选项卡片 → 填文字 → 点"提交"
            mid = cmd["id"]
            if not self.win.select_message(mid):
                return {"ok": False, "error": "没有这条消息"}
            app.processEvents()
            panel = self.win.panel
            if panel.answered:
                return {"ok": False, "error": "已回复，提交按钮已隐藏", "response": self.store.responses.get(mid)}
            ch = cmd.get("choice")
            if ch is not None:
                idx = ch - 1 if isinstance(ch, int) else [c.label for c in panel.cards].index(ch)
                panel.cards[idx].click()
            if cmd.get("text") and panel.allow_text:
                panel.text.setPlainText(cmd["text"])
            app.processEvents()
            if not panel.submit_btn.isEnabled():
                return {"ok": False, "error": "提交按钮不可用"}
            panel.submit_btn.click()
            app.processEvents()
            return {"ok": mid in self.store.responses, "response": self.store.responses.get(mid),
                    "panel_answered_after": panel.answered,
                    "submit_hidden_after": panel.submit_btn.isHidden()}
        if op == "submit_direct":
            try:
                rec = self.store.submit(cmd["id"], cmd.get("choice"), cmd.get("text", ""))
                return {"ok": True, "response": rec}
            except FileExistsError as e:
                return {"ok": False, "error": str(e)}
        if op == "quit":
            QTimer.singleShot(100, self.tray.quit_app)
            return {"ok": True}
        return {"ok": False, "error": f"未知 op {op!r}"}


def send_to_running(name: str, cmd: dict, timeout_ms: int = 60000) -> dict | None:
    s = QLocalSocket()
    s.connectToServer(name)
    if not s.waitForConnected(800):
        return None
    if os.name == "nt":
        _user32.AllowSetForegroundWindow(0xFFFFFFFF)  # ASFW_ANY：允许已有实例把窗口切到前台
    s.write((json.dumps(cmd, ensure_ascii=False) + "\n").encode("utf-8"))
    s.flush()
    buf = b""
    while b"\n" not in buf:
        if not s.waitForReadyRead(timeout_ms):
            break
        buf += bytes(s.readAll().data())
    s.disconnectFromServer()
    try:
        return json.loads(buf.split(b"\n")[0].decode("utf-8"))
    except (ValueError, IndexError):
        return {"ok": False, "error": "没有收到回应"}


def light_palette() -> QPalette:
    pal = QPalette()
    for role, color in [(QPalette.Window, "#F5F6F8"), (QPalette.WindowText, "#101828"), (QPalette.Base, "#FFFFFF"),
                        (QPalette.AlternateBase, "#F9FAFB"), (QPalette.Text, "#101828"), (QPalette.Button, "#FFFFFF"),
                        (QPalette.ButtonText, "#101828"), (QPalette.Highlight, "#2563EB"),
                        (QPalette.HighlightedText, "#FFFFFF"), (QPalette.ToolTipBase, "#FFFFFF"),
                        (QPalette.ToolTipText, "#101828"), (QPalette.PlaceholderText, "#98A2B3"),
                        (QPalette.Link, "#1D4ED8")]:
        pal.setColor(role, QColor(color))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor("#98A2B3"))
    pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor("#98A2B3"))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#98A2B3"))
    return pal


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog=APP)
    ap.add_argument("--minimized", action="store_true", help="启动后只留在托盘（开机自启用）")
    ap.add_argument("--data", help="数据目录（默认 exe 旁边的 data/）")
    ap.add_argument("--show-selftest", action="store_true", help="显示 source=selftest* 的消息")
    ap.add_argument("--selftest", help=argparse.SUPPRESS)  # 测试入口：把 JSON 命令发给已运行的实例
    ap.add_argument("--out", help=argparse.SUPPRESS)
    args, _ = ap.parse_known_args(argv)

    ddir = Path(args.data) if args.data else (Path(os.environ["CLAUDEDESK_DATA"]) if os.environ.get("CLAUDEDESK_DATA")
                                                else app_dir() / "data")
    ddir.mkdir(parents=True, exist_ok=True)
    if desk.data_dir(ddir).resolve() == (app_dir() / "data").resolve():
        name = "ClaudeDesk-" + (os.environ.get("USERNAME") or "user")
    else:
        name = desk.pipe_name(ddir)

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP)
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")
    app.setPalette(light_palette())
    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    except AttributeError:
        pass
    app.setFont(QFont(UI_FONT, 10))

    if args.selftest:
        res = send_to_running(name, json.loads(args.selftest))
        out = json.dumps(res if res is not None else {"ok": False, "error": "没有运行中的实例"},
                         ensure_ascii=False, indent=1)
        if args.out:
            Path(args.out).write_text(out, encoding="utf-8")
        elif sys.stdout:
            print(out)
        return 0 if res and res.get("ok") else 1

    res = send_to_running(name, {"op": "noop" if args.minimized else "activate"}, 5000)
    if res is not None:
        return 0  # 已有实例：只激活它

    store = Store(ddir, show_selftest=args.show_selftest)
    win = MainWindow(store)
    tray = Tray(win, store)
    win.tray = tray
    tray.show()
    ctl = Controller(win, tray, store, name)
    if not ctl.ok:
        return 0
    store.arrived.connect(tray.notify)

    timer = QTimer()
    timer.setInterval(1000)
    timer.timeout.connect(store.poll)
    timer.start()

    if not args.minimized:
        win.show()
    # 第一次读取稍后做：托盘图标先注册好；程序没开时到的、还没提醒过的消息会在这次补提醒
    QTimer.singleShot(700, store.poll)
    if args.minimized:
        QTimer.singleShot(2500, trim_working_set)
    rc = app.exec()
    store.save_state()
    return rc


if __name__ == "__main__":
    sys.exit(main())
