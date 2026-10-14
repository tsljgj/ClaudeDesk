"""重新生成 README 里的截图：docs/screenshot-light.png、docs/screenshot-dark.png。

    python scripts/screenshots.py [--out docs] [--browser <Chromium / Edge 的 exe>] [--colors 256]

收件箱是这里现造的一份演示数据（虚构的仓库和内容），放在临时目录里：不读你自己的 data/，
也不读 Claude Code 的会话记录。起 Store + 本机服务，用 Playwright 打开界面，浅色、深色各拍一张：
打开一条待决定，露出选项和回复框。时钟固定在 2026-03-12 10:30 (UTC)，图里不会出现拍摄时的真实时间。

需要 `pip install playwright pillow`。浏览器默认用 Playwright 自带的 Chromium
（`python -m playwright install chromium`）；没装的话在 Windows 上会用系统的 Edge，也可以用 --browser 指定。
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import os
import secrets
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

import desk  # noqa: E402
from claudedesk.server import DeskServer  # noqa: E402
from claudedesk.store import Store  # noqa: E402

NOW = dt.datetime(2026, 3, 12, 10, 30, tzinfo=dt.timezone.utc)
VIEWPORT = {"width": 1300, "height": 820}
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

RELEASE_BODY = r"""有 3 个合并请求改了会话中间件，按惯例应该先跑**完整回归测试**。p95 延迟改善了 $\frac{640 - 512}{640} = 20\%$：

| 指标（预发布环境） | 上一版 | 这一版 |
|---|---:|---:|
| 首页 p50 延迟 | 182 ms | 141 ms |
| 首页 p95 延迟 | 640 ms | 512 ms |
"""

CI_BODY = """**结论：** 慢在依赖缓存没命中，不是测试本身变慢了。

1. 昨晚 `requirements.txt` 升级了 3 个包，缓存键跟着变了，今天第一次构建要重新下载、编译依赖（多了约 6 分钟）。
2. 测试本身的耗时和平时一样（11 分钟左右）。

下一次构建会命中新缓存，时间会回到正常水平。想彻底避免，可以把缓存键改成按 lock 文件计算：

```yaml
- uses: actions/cache@v4
  with:
    path: ~/.cache/pip
    key: pip-${{ hashFiles('requirements*.txt') }}
```
"""


def seed(d: Path) -> dict[str, str]:
    """造一份演示收件箱，返回 {名字: 消息 id}。"""

    def msg(ago_min: float, **kw) -> str:
        t = NOW - dt.timedelta(minutes=ago_min)
        m = desk.make_message(**kw)
        m["id"] = t.strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(3)
        m["ts"] = t.isoformat(timespec="milliseconds")
        return desk.post_message(m, d)

    ids = {}
    ids["release"] = msg(4, kind="decision", source="webapp/release", repo="webapp", priority="high",
                         title="发布前先跑一轮完整回归测试吗？", body=RELEASE_BODY,
                         options=["先跑回归测试::约 25 分钟，最稳妥", "直接发布::CI 已经跑过单元测试",
                                  "只跑冒烟测试::约 5 分钟，覆盖两条主流程"], recommended=1)
    ids["nightly"] = msg(35, kind="info", source="webapp/ci", repo="webapp",
                         title="夜间构建完成", body="build 2048 已部署到预发布环境，全部 1,290 个测试通过，耗时 7 分 12 秒。")
    ids["wal"] = msg(60 * 20, kind="answer", source="webapp", repo="webapp",
                     title="WAL 模式为什么写得更快？", question="SQLite 打开 WAL 以后，为什么写入快了这么多？",
                     body="写入只追加到 WAL 文件末尾，不用每次改动都回写主数据库文件……")
    ids["retry"] = msg(50, kind="decision", source="acme-data-pipeline/loader", repo="acme-data-pipeline",
                       title="增量导入遇到坏行：整批重试还是跳过？", body="今天的导入里有 3 行格式不对。",
                       options=["整批重试::修好源文件后重跑", "跳过坏行::记到日志里，其余照常导入"], recommended=2)
    ids["ci"] = msg(12, kind="answer", source="acme-data-pipeline", repo="acme-data-pipeline",
                    title="今天的 CI 为什么变慢了", question="今天的 CI 为什么比平时多跑了一倍时间？", body=CI_BODY)
    ids["logs"] = msg(60 * 5, kind="decision", source="acme-data-pipeline", repo="acme-data-pipeline",
                      title="日志保留多少天？", body="", options=["7 天", "30 天", "90 天"], recommended=2)
    ids["import"] = msg(60 * 3, kind="info", source="示例项目", repo="示例项目",
                        title="数据导入完成：1,200 条，耗时 4 分钟", body="没有报错，明细在 `import.log`。")
    ids["lint"] = msg(60 * 26, kind="decision", source="示例项目", repo="示例项目",
                      title="要不要把 lint 规则调严一点？", body="", options=["调严", "保持现状"])
    ids["regex"] = msg(60 * 24 * 3, kind="answer", source="随手记",
                       title="正则里的 (?<=…) 是什么意思？", question="(?<=…) 和 (?=…) 有什么区别？",
                       body="(?<=…) 是后行断言：只看前面，不占字符……")
    ids["old"] = msg(60 * 24 * 12, kind="info", source="webapp", repo="webapp", title="上周的发布说明", body="已归档。")
    return ids


def start(d: Path):
    ids = seed(d)
    store = Store(d)
    store.poll()
    store.mark_read([ids[k] for k in ("wal", "retry", "logs", "lint", "regex", "old", "import")])
    store.submit(ids["logs"], "30 天", "", choice_index=2)
    store.resolve([ids["lint"]])
    store.archive([ids["old"]])
    server = DeskServer(store).start_background()
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            store.poll()
            stop.wait(0.2)

    threading.Thread(target=loop, daemon=True).start()
    return store, server, ids, stop


def save_png(raw: bytes, path: Path, colors: int) -> None:
    from PIL import Image

    img = Image.open(io.BytesIO(raw)).convert("RGB")
    if colors:  # 界面截图颜色不多：调色板 PNG 小得多，看不出差别
        img = img.quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    img.save(path, optimize=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(ROOT / "docs"), help="输出目录（默认 docs/）")
    ap.add_argument("--browser", help="Chromium 内核浏览器的 exe（默认 Playwright 自带的 Chromium）")
    ap.add_argument("--colors", type=int, default=256, help="调色板颜色数；0 = 保留全彩")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import Error as PwError
    from playwright.sync_api import sync_playwright

    with tempfile.TemporaryDirectory(prefix="claudedesk-shots-", ignore_cleanup_errors=True) as tmp:
        store, server, ids, stop = start(Path(tmp))
        try:
            with sync_playwright() as p:
                try:
                    browser = p.chromium.launch(executable_path=a.browser) if a.browser else p.chromium.launch()
                except PwError:
                    if a.browser or not os.path.exists(EDGE):
                        raise
                    browser = p.chromium.launch(executable_path=EDGE)
                for theme in ("light", "dark"):
                    server.action({"action": "settings", "values": {"theme": theme}})
                    ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=2, locale="zh-CN", timezone_id="UTC")
                    page = ctx.new_page()
                    page.clock.set_fixed_time(NOW)
                    errors: list[str] = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.goto(server.url)
                    page.wait_for_selector(".item")
                    page.evaluate("id => window.deskOpen(id)", ids["release"])
                    page.wait_for_selector("#detail:not([hidden]) .opt")
                    page.evaluate("() => deskTest.pick(0)")
                    page.fill("#replyText", "顺便把支付流程的用例也跑一遍")
                    page.evaluate("() => document.activeElement && document.activeElement.blur()")
                    page.mouse.move(VIEWPORT["width"] - 2, VIEWPORT["height"] - 2)  # 鼠标挪开，别留下悬停样式
                    page.wait_for_timeout(1200)  # 字体、公式排好；停留 0.8 秒后标为已读
                    path = out / f"screenshot-{theme}.png"
                    save_png(page.screenshot(), path, a.colors)
                    print(path, f"{path.stat().st_size // 1024} KB", ("JS errors: " + "; ".join(errors)) if errors else "")
                    ctx.close()
                    store.mark_read([ids["release"]], False)  # 下一张图从同样的状态开始
                browser.close()
        finally:
            stop.set()
            server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
