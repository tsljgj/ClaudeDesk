import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture(autouse=True)
def _no_claude_session(monkeypatch):
    """在 Claude Code 会话里跑测试时，环境里有这个会话的 CLAUDE_CODE_SESSION_ID / CLAUDE_PID：去掉，
    免得测试里（包括子进程）发的消息都记成那个会话的。要会话的测试自己设。"""
    for k in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_PID", "CLAUDE_CONFIG_DIR"):
        monkeypatch.delenv(k, raising=False)
