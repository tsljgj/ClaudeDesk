"""消息归哪个仓库（界面上的项目标签）：按会话开在哪个仓库认，Agent cd 到别处、随手给 --repo 都不会多出标签。
会话记录用合成的（CLAUDE_CONFIG_DIR 指到临时目录），不碰真的会话记录。"""
import json
import os
import subprocess
import sys
from pathlib import Path

import desk
from claudedesk import projects
from claudedesk.store import Store

ROOT = Path(__file__).resolve().parents[1]
CLEAN = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def make_repo(path: Path, origin: str | None = None) -> Path:
    path.mkdir(parents=True)
    git(path, "init", "-q")
    if origin:
        git(path, "remote", "add", "origin", origin)
    return path


def transcript(cfg: Path, session: str, cwd: str) -> None:
    """一份最小的会话记录：开头几行没有 cwd（和真记录一样），后面每行带着启动目录。"""
    p = cfg / "projects" / "-encoded-path"
    p.mkdir(parents=True, exist_ok=True)
    lines = [{"type": "queue-operation", "operation": "x"},
             {"type": "user", "cwd": cwd, "sessionId": session, "message": {"role": "user", "content": "hi"}},
             {"type": "assistant", "cwd": str(Path(cwd).parent), "message": {"content": []}}]
    (p / f"{session}.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")


def post(data, cfg, session, cwd, *extra):
    env = dict(CLEAN, CLAUDE_CONFIG_DIR=str(cfg))
    if session:
        env["CLAUDE_CODE_SESSION_ID"] = session
    return subprocess.run([sys.executable, str(ROOT / "desk.py"), "--data", str(data), "post", "--kind", "info",
                           "--title", "t", "--body", "b", "--no-launch", *extra],
                          cwd=cwd, env=env, capture_output=True, encoding="utf-8", timeout=60)


def repos(data):
    return [m.get("repo") for m in desk.read_all(data / desk.INBOX)]


def test_post_uses_the_sessions_own_repo_wherever_the_shell_is(tmp_path):
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    home = make_repo(tmp_path / "code" / "webapp-local", "https://github.com/me/webapp.git")
    nested = make_repo(home / "third_party" / "lib", "https://github.com/other/lib.git")  # 子目录里另一个仓库
    scratch = tmp_path / "scratch" / "tmp-xyz"
    scratch.mkdir(parents=True)
    transcript(cfg, "S1", str(home))
    for cwd in (home, nested, scratch, tmp_path):
        r = post(data, cfg, "S1", cwd)
        assert r.returncode == 0, r.stderr
    assert repos(data) == ["webapp"] * 4
    # Agent 自己起的 --repo：不用，提示一句
    r = post(data, cfg, "S1", nested, "--repo", "my-feature")
    assert r.returncode == 0 and "没用 --repo" in r.stderr
    assert repos(data)[-1] == "webapp"
    r = post(data, cfg, "S1", nested, "--repo", "WebApp")  # 和会话的仓库是同一个：不吭声
    assert r.returncode == 0 and "--repo" not in r.stderr and repos(data)[-1] == "webapp"


def test_post_falls_back_to_the_shell_when_the_session_root_is_not_a_repo(tmp_path):
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    parent = tmp_path / "code"  # 在一堆仓库的上一层开的会话
    repo = make_repo(parent / "acme-data-pipeline")
    other = tmp_path / "elsewhere" / "notes"
    other.mkdir(parents=True)
    transcript(cfg, "S2", str(parent))
    assert post(data, cfg, "S2", repo).returncode == 0  # cd 进了某个仓库：用它
    assert post(data, cfg, "S2", other).returncode == 0  # 都不是仓库：用会话的目录名，不用 Bash 当时所在的目录
    r = post(data, cfg, "S2", other, "--repo", "示例项目")  # 会话不在仓库里：--repo 照用
    assert r.returncode == 0 and "--repo" not in r.stderr
    assert repos(data) == ["acme-data-pipeline", "code", "示例项目"]


def test_post_without_a_session_keeps_the_old_rules(tmp_path):
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    repo = make_repo(tmp_path / "webapp")
    assert post(data, cfg, None, repo).returncode == 0
    assert post(data, cfg, None, repo, "--repo", "other").returncode == 0
    assert post(data, cfg, "NO-TRANSCRIPT", repo, "--repo", "third").returncode == 0  # 找不到会话记录：也照旧
    assert repos(data) == ["webapp", "other", "third"]


def test_session_root_skips_subagents_and_bad_input(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(cfg))
    transcript(cfg, "S3", "/work/main")
    sub = cfg / "projects" / "-encoded-path" / "S3" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-1.jsonl").write_text(json.dumps({"type": "user", "cwd": "/work/other"}) + "\n", encoding="utf-8")
    assert desk.session_root("S3") == "/work/main"
    assert desk.session_root("missing") is None
    assert desk.session_root("../evil") is None
    assert desk.session_root(None) is None


def test_store_regroups_old_messages_under_the_sessions_repo(tmp_path, monkeypatch):
    """以前的 desk.py 按 Bash 当前目录记的仓库名：按会话认回来，旧的怪标签消失；没有会话的旧消息不动。"""
    cfg, data = tmp_path / "cfg", tmp_path / "data"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(cfg))
    home = make_repo(tmp_path / "webapp")
    transcript(cfg, "S4", str(home))
    a = desk.post_message(desk.make_message("info", "lib", "在子仓库里发的", repo="lib", session="S4"), data)
    b = desk.post_message(desk.make_message("info", "webapp", "正常的", repo="webapp", session="S4"), data)
    c = desk.post_message(desk.make_message("info", "other", "没有会话", repo="other"), data)
    d = desk.post_message(desk.make_message("info", "x", "会话记录没了", repo="tmp-xyz", session="GONE"), data)
    st = Store(data)
    st.poll()
    assert st.sessions() == {"S4", "GONE"}
    assert st.project_info(st.msgs[a])[0] == "lib"
    found = projects.session_repos(st.sessions(), {})
    assert found == {"S4": "webapp"}
    v = st.version
    st.set_session_repos(found)
    assert st.version > v
    assert [st.project_info(st.msgs[i])[:2] for i in (a, b, c, d)] == [
        ("webapp", "repo"), ("webapp", "repo"), ("other", "repo"), ("tmp-xyz", "repo")]
    v = st.version
    st.set_session_repos(dict(found))  # 没变：不打扰界面
    assert st.version == v
