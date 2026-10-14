import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import desk
import pytest

ROOT = Path(__file__).resolve().parents[1]


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_detect_repo_origin_worktree_and_plain(tmp_path):
    repo = tmp_path / "local-folder-name"
    repo.mkdir()
    git(repo, "init", "-q")
    assert desk.detect_repo(repo) == "local-folder-name"  # 没有 origin：用目录名
    (repo / "sub").mkdir()
    assert desk.detect_repo(repo / "sub") == "local-folder-name"
    git(repo, "remote", "add", "origin", "https://github.com/someone/webapp.git")
    assert desk.detect_repo(repo / "sub") == "webapp"  # origin 的仓库名优先
    git(repo, "remote", "set-url", "origin", "git@github.com:someone/acme-data-pipeline.git")
    assert desk.detect_repo(repo) == "acme-data-pipeline"
    git(repo, "remote", "remove", "origin")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x")
    wt = tmp_path / "some-worktree"
    git(repo, "worktree", "add", "-q", str(wt))
    assert desk.detect_repo(wt) == "local-folder-name"  # worktree 认出主仓库
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    assert desk.detect_repo(plain) is None


def test_post_records_repo(tmp_path):
    repo = tmp_path / "work"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "remote", "add", "origin", "https://github.com/x/webapp")
    data = tmp_path / "data"
    run = lambda *a: subprocess.run([sys.executable, str(ROOT / "desk.py"), "--data", str(data), *a],  # noqa: E731
                                    cwd=repo, capture_output=True, encoding="utf-8", check=True)
    run("post", "--kind", "info", "--source", "eval-run-7", "--title", "t", "--body", "b", "--no-launch")
    run("post", "--kind", "info", "--source", "x", "--title", "t2", "--body", "b", "--repo", "other", "--no-launch")
    msgs = [json.loads(line) for line in (data / desk.INBOX).read_text(encoding="utf-8").splitlines()]
    assert [m.get("repo") for m in msgs] == ["webapp", "other"]
    out = run("list", "--repo", "webapp", "--json").stdout.strip().splitlines()
    assert len(out) == 1 and json.loads(out[0])["title"] == "t"


def test_folder_fallback_outside_git(tmp_path):
    d = tmp_path / "acme-data-pipeline"
    d.mkdir()
    assert desk.detect_repo(d) is None
    assert desk.detect_repo(d, folder_fallback=True) == "acme-data-pipeline"


def test_discover_projects_from_claude_sessions(tmp_path, monkeypatch):
    from claudedesk import projects

    cfg = tmp_path / "cfg"
    repo = tmp_path / "code" / "local-name"
    repo.mkdir(parents=True)
    git(repo, "init", "-q")
    git(repo, "remote", "add", "origin", "https://github.com/me/webapp.git")

    def session(folder, cwd):
        p = cfg / "projects" / folder
        p.mkdir(parents=True)
        lines = [{"type": "summary", "summary": "x"}, {"type": "user", "cwd": cwd, "message": {}}]
        (p / "s1.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")

    session("a", str(repo))                                    # 真仓库：用 origin 里的名字
    session("b", r"D:\code\acme-data-pipeline")                # 别的机器上的路径：用目录名
    session("c", r"D:\code\acme-data-pipeline\.claude\worktrees\feat-x")  # worktree 算回主目录
    session("d", str(Path.home()))                             # 家目录不算项目
    assert projects.discover([cfg]) == {"webapp", "acme-data-pipeline"}


def cli(data, *args, cwd=None, env=None):
    """跑真的 desk.py；输出按 UTF-8 解（desk.py 把 stdout / stderr 设成了 UTF-8）。"""
    return subprocess.run([sys.executable, str(ROOT / "desk.py"), "--data", str(data), *args], cwd=cwd, env=env,
                          capture_output=True, encoding="utf-8", errors="replace")


def test_detect_repo_non_ascii_names(tmp_path):
    """git 输出的是 UTF-8：中文仓库名在中文 Windows（cp936）上也要认对，不能乱码、不能退回 worktree 目录名。"""
    names = {}
    for repo_name, wt_name in (("示例项目", "wt-任务"), ("演示仓库", "wt2")):
        repo = tmp_path / repo_name
        repo.mkdir()
        git(repo, "init", "-q")
        git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x")
        git(repo, "worktree", "add", "-q", str(tmp_path / wt_name))
        names[repo_name] = desk.detect_repo(tmp_path / wt_name)
    assert names == {"示例项目": "示例项目", "演示仓库": "演示仓库"}
    data = tmp_path / "data"
    r = cli(data, "post", "--kind", "info", "--source", "s", "--title", "t", "--body", "b", "--no-launch",
            cwd=tmp_path / "wt2")
    assert r.returncode == 0 and "Traceback" not in r.stderr
    assert [m.get("repo") for m in desk.read_all(data / desk.INBOX)] == ["演示仓库"]


def test_read_jsonl_retries_while_file_is_replaced(tmp_path, monkeypatch):
    p = tmp_path / desk.INBOX
    desk.append_jsonl(p, {"id": "a"})
    real, st = open, {"fail": 3, "calls": 0}

    def flaky(*args, **kw):  # 压缩换文件的一瞬间 Windows 上 open 会 PermissionError
        st["calls"] += 1
        if st["fail"] > 0:
            st["fail"] -= 1
            raise PermissionError(13, "delete pending")
        return real(*args, **kw)

    monkeypatch.setattr(desk, "open", flaky, raising=False)
    assert [r["id"] for r in desk.read_all(p)] == ["a"] and st["calls"] == 4
    st["fail"] = 10**9  # 一直打不开：重试到时间就报错，不能当成空文件
    with pytest.raises(PermissionError):
        desk.read_jsonl(p, retry=0.1)


def test_normalize_options_ignores_non_lists():
    assert desk.normalize_options(5) == [] and desk.normalize_options("A::x") == []
    assert desk.normalize_options(True) == [] and desk.normalize_options({"label": "A"}) == []
    assert desk.normalize_options(("A::x", {"label": "B"})) == [{"label": "A", "description": "x"},
                                                                  {"label": "B", "description": ""}]


def test_pipe_name_identifies_data_dir(tmp_path):
    """每份 desk.py 默认的 data/ 都不一样，"程序在运行"的标记也要不一样：别的目录里的副本不能以为有人在看它。"""
    env = {k: v for k, v in os.environ.items() if k != "CLAUDEDESK_DATA"}
    got = []
    for folder in ("InstallA", "InstallB"):
        (tmp_path / folder).mkdir()
        shutil.copy(ROOT / "desk.py", tmp_path / folder / "desk.py")
        out = subprocess.run([sys.executable, "-c", "import desk; print(desk.pipe_name())"], cwd=tmp_path / folder,
                             env=env, capture_output=True, text=True, check=True).stdout.strip()
        got.append(out)
        assert out == desk.pipe_name(tmp_path / folder / "data")
    assert got[0] != got[1]
    assert desk.pipe_name(tmp_path / "x") == desk.pipe_name(str(tmp_path / "x") + os.sep)


def test_post_warns_when_no_app_watches_its_data_dir(tmp_path):
    data = tmp_path / "data"
    r = cli(data, "post", "--kind", "decision", "--source", "s", "--title", "t", "--option", "A", "--no-launch")
    assert r.returncode == 0 and "没有 ClaudeDesk 在看这个数据目录" in r.stderr and str(data) in r.stderr
    assert "wait 也等不到回复" in r.stderr
    if os.name != "nt":
        return
    from claudedesk import winapi

    other = winapi.running_marker(desk.pipe_name(tmp_path / "other"))  # 有程序在跑，但看的是别的目录
    try:
        r = cli(data, "post", "--kind", "info", "--source", "s", "--title", "t", "--no-launch")
        assert "没有 ClaudeDesk 在看这个数据目录" in r.stderr
    finally:
        winapi.release(other)
    mine = winapi.running_marker(desk.pipe_name(data))
    try:
        r = cli(data, "post", "--kind", "info", "--source", "s", "--title", "t", "--no-launch")
        assert r.returncode == 0 and r.stderr == ""
    finally:
        winapi.release(mine)


@pytest.mark.skipif(os.name != "nt", reason="命名管道只在 Windows 上用")
def test_marker_pipe_retried_until_old_instance_closes_it(tmp_path):
    """自动更新后旧进程的同名管道可能还没关：新进程要在后台重试，而不是从此没有标记。"""
    import time

    from claudedesk import app, winapi

    name = desk.pipe_name(tmp_path)
    old = winapi.running_marker(name)
    held = app.hold_marker(name)
    assert old and held == []
    winapi.release(old)
    deadline = time.monotonic() + 5
    while not held and time.monotonic() < deadline:
        time.sleep(0.05)
    try:
        assert held and desk.app_running(tmp_path)
    finally:
        for h in held:
            winapi.release(h)
    assert not desk.app_running(tmp_path)


def test_wait_matches_id_whatever_the_source_and_close_reports_existing_reply(tmp_path):
    from claudedesk.store import Store

    data = tmp_path / "data"
    mid = cli(data, "post", "--kind", "decision", "--source", "proj/data", "--title", "q", "--option", "A",
              "--option", "B", "--no-launch").stdout.strip()
    s = Store(data)
    s.poll()
    s.submit(mid, "B", "")  # 用户在 ClaudeDesk 里答了
    r = cli(data, "wait", "--source", "proj", "--id", mid, "--timeout", "5")
    assert r.returncode == 0 and json.loads(r.stdout)["choice"] == "B" and "proj/data" in r.stderr
    r = cli(data, "close", "--id", mid, "--text", "用户在对话里选了 A")
    assert r.returncode == 3
    rec = json.loads(r.stdout)
    assert rec["id"] == mid and rec["choice"] == "B" and rec["title"] == "q" and "closed_by" not in rec
