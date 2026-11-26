"""回复里的本机路径：哪些认、规范成什么样，打开时哪些只在文件夹里选中。系统调用都换成假的，Linux 上也能跑。"""
import pytest

from claudedesk.localfiles import Opener, existing, local_path, runs_when_opened
from claudedesk.server import ActionError


@pytest.mark.parametrize("raw, want", [
    ("C:\\work\\report.md", "C:\\work\\report.md"),
    ("c:/work/report.md", "C:\\work\\report.md"),
    ("  D:\\数据\\年报 2025.xlsx ", "D:\\数据\\年报 2025.xlsx"),
    ("/c/work/a.py", "C:\\work\\a.py"),
    ("file:///C:/work/a%20b.md", "C:\\work\\a b.md"),
    ("file://localhost/C:/work/a.md", "C:\\work\\a.md"),
    ("C:\\work\\..\\other\\.\\x.txt", "C:\\other\\x.txt"),
    ("C:\\work\\run.exe.", "C:\\work\\run.exe"),  # Windows 自己会去掉末尾的点
    ("C:\\", "C:\\"),
])
def test_local_paths_are_normalized(raw, want):
    assert local_path(raw) == want


@pytest.mark.parametrize("raw", [
    "", None, "work\\report.md", "src/app.py",
    "\\\\server\\share\\a.txt", "//server/share/a.txt", "\\\\?\\C:\\a.txt", "\\\\.\\PhysicalDrive0",
    "file://server/share/a.txt", "https://example.com/a",
    "C:\\a.txt:hidden.exe", "C:\\a?.txt", "C:\\a\nb.txt", "C:\\dev\\NUL", "C:\\x\\con.txt",
    "C:\\" + "a" * 2000,
])
def test_non_local_or_odd_paths_are_refused(raw):
    assert local_path(raw) is None


def test_runnable_files_are_only_revealed(monkeypatch):
    monkeypatch.setenv("PATHEXT", ".COM;.EXE;.BAT;.CMD;.FOO")
    for p in ("C:\\a\\setup.exe", "C:\\a\\x.BAT", "C:\\a\\run.ps1", "C:\\a\\tool.py", "C:\\a\\go.lnk", "C:\\a\\b.foo"):
        assert runs_when_opened(p), p
    for p in ("C:\\a\\report.md", "C:\\a\\data.csv", "C:\\a\\page.html", "C:\\a\\Makefile", "C:\\a\\pic.png"):
        assert not runs_when_opened(p), p


def test_trailing_chinese_is_trimmed_until_the_file_is_found():
    have = {"D:\\proj\\data", "C:\\work\\报告.md"}
    assert existing("D:\\proj\\data下面", have.__contains__) == "D:\\proj\\data"
    assert existing("C:\\work\\报告.md", have.__contains__) == "C:\\work\\报告.md"
    assert existing("C:\\work\\报告", have.__contains__) is None  # 不是去掉汉字能找到的
    assert existing("C:\\nothing.txt", have.__contains__) is None


def make(files=(), dirs=(), remote=()):
    calls = []
    o = Opener(lambda p: calls.append(("open", p)), lambda p: calls.append(("reveal", p)),
               remote_fn=lambda p: p[0] in remote,
               exists=lambda p: p in files or p in dirs, isdir=lambda p: p in dirs)
    return o, calls


def test_open_path_opens_reveals_and_refuses():
    o, calls = make(files={"C:\\work\\report.md", "C:\\work\\setup.exe"}, dirs={"C:\\work"})
    assert o.open_path({"path": "C:/work/report.md"}) == {"path": "C:\\work\\report.md", "revealed": False, "runs": False}
    assert o.open_path({"path": "C:\\work\\report.md", "reveal": True})["revealed"] is True
    assert o.open_path({"path": "C:\\work\\setup.exe"}) == {"path": "C:\\work\\setup.exe", "revealed": True, "runs": True}
    assert o.open_path({"path": "/c/work"})["path"] == "C:\\work"  # 文件夹：打开它
    assert calls == [("open", "C:\\work\\report.md"), ("reveal", "C:\\work\\report.md"),
                     ("reveal", "C:\\work\\setup.exe"), ("open", "C:\\work")]
    with pytest.raises(ActionError, match="找不到"):
        o.open_path({"path": "C:\\work\\gone.md"})
    with pytest.raises(ActionError, match="只能打开这台电脑上的文件"):
        o.open_path({"path": "\\\\server\\share\\a.md"})
    assert len(calls) == 4


def test_path_info_reports_kind_and_found_path():
    o, _ = make(files={"C:\\work\\report.md"}, dirs={"D:\\proj\\data"}, remote={"Z"})
    info = o.path_info({"paths": ["C:\\work\\report.md", "D:\\proj\\data下面", "C:\\nope.txt", "Z:\\share\\a.txt", "A:/B",
                                  "\\\\server\\x"]})
    assert info["C:\\work\\report.md"] == {"kind": "file", "path": "C:\\work\\report.md"}
    assert info["D:\\proj\\data下面"] == {"kind": "dir", "path": "D:\\proj\\data"}
    assert info["C:\\nope.txt"]["kind"] == "gone"
    assert info["Z:\\share\\a.txt"] == {"kind": "unknown", "path": "Z:\\share\\a.txt"}  # 网络盘：不先查
    assert info["A:/B"]["kind"] == "gone"
    assert info["\\\\server\\x"] == {"kind": "gone", "path": None}
    assert len(o.path_info({"paths": [f"C:\\{i}.txt" for i in range(300)]})) == 100
