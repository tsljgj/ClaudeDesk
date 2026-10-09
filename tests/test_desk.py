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
    git(repo, "remote", "add", "origin", "https://github.com/someone/osworld.git")
    assert desk.detect_repo(repo / "sub") == "osworld"  # origin 的仓库名优先
    git(repo, "remote", "set-url", "origin", "git@github.com:someone/cn-equity-research.git")
    assert desk.detect_repo(repo) == "cn-equity-research"
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
    git(repo, "remote", "add", "origin", "https://github.com/x/osworld")
    data = tmp_path / "data"
    run = lambda *a: subprocess.run([sys.executable, str(ROOT / "desk.py"), "--data", str(data), *a],  # noqa: E731
                                    cwd=repo, capture_output=True, text=True, check=True)
    run("post", "--kind", "info", "--source", "eval-run-7", "--title", "t", "--body", "b", "--no-launch")
    run("post", "--kind", "info", "--source", "x", "--title", "t2", "--body", "b", "--repo", "other", "--no-launch")
    msgs = [json.loads(line) for line in (data / desk.INBOX).read_text(encoding="utf-8").splitlines()]
    assert [m.get("repo") for m in msgs] == ["osworld", "other"]
    out = run("list", "--repo", "osworld", "--json").stdout.strip().splitlines()
    assert len(out) == 1 and json.loads(out[0])["title"] == "t"
