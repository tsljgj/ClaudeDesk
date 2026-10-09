import json
import subprocess
import sys
from pathlib import Path

import desk

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
                                    cwd=repo, capture_output=True, text=True, check=True)
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
