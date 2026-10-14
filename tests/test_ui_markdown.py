"""Markdown 渲染（markdown.js）：在一个真页面里跑 DeskMarkdown.toHtml + hydrate，按表核对结构。"""
from test_ui import BODY, env, post  # noqa: F401  env 是 fixture

# 每条：(名字, 输入, 期望)。期望的键：
#   text        渲染后的纯文本（公式换成 ⟦tex⟧，去掉首尾空白）完全相等
#   has / lacks 纯文本里必须有 / 不能有的片段；html_lacks：hydrate 之后的 HTML 里不能有的片段
#   count       {选择器: 个数}；texts：{选择器: [各元素的文字]}
#   attrs       {选择器: [{属性: 值}, …]}，逐个元素比对给出的属性（None = 没有这个属性；katex = 公式已渲染；text = 文字）
CASES = [
    # F5：中文粗体的结尾 ** 紧挨全角标点
    ("F5 冒号后收尾", "**结论：**建议选方案 B。", {"texts": {"strong": ["结论："]}, "text": "结论：建议选方案 B。"}),
    ("F5 括号后收尾", "请看**第 3 节（附录）**的说明。", {"texts": {"strong": ["第 3 节（附录）"]}, "lacks": ["**"]}),
    ("F5 中文引号", "这里用**“方案 B”**更稳。", {"texts": {"strong": ["“方案 B”"]}, "lacks": ["**"]}),
    ("F5 英文引号", '这里用**"方案 B"**更稳。', {"texts": {"strong": ['"方案 B"']}, "lacks": ["**"]}),
    ("F5 对照", "先说结论：**建议选方案 B**，代价最小。", {"texts": {"strong": ["建议选方案 B"]}}),
    ("F5 斜体和删除线", "*（中）*文，~~删除：~~后面", {"texts": {"em": ["（中）"], "s": ["删除："]}}),
    ("F5 任务列表里", "- [x] 完成 **结论：**好", {"texts": {"strong": ["结论："]}, "count": {"li.task-item .task.done": 1}}),
    ("F5 英文仍按 CommonMark", 'foo**bar**baz, *foo*bar, a*"foo"*b, __foo__bar, _foo_bar, ** x **',
     {"texts": {"strong": ["bar"], "em": ["foo"]}, "has": ['a*"foo"*b', "__foo__bar", "_foo_bar", "** x **"]}),

    # F8：data-tex 不能被 DOMPurify 当成网址删掉
    ("F8 映射记号", r"映射 $f: X \to Y$ 是单射。", {"attrs": {".math": [{"data-tex": r"f: X \to Y", "katex": True}]}}),
    ("F8 块公式", "$$\nT: V \\to W,\\quad T(v) = Av\n$$",
     {"attrs": {".math-display": [{"data-tex": r"T: V \to W,\quad T(v) = Av", "katex": True}]}}),
    ("F8 对照", "$g(x) = x^2$", {"attrs": {".math": [{"data-tex": "g(x) = x^2", "katex": True}]}}),

    # F9：$ 的判定（表格、代码段、货币）
    ("F9 价格表", "| 项目 | 旧价 | 新价 |\n|---|---|---|\n| 服务器 | $5 | $10 |\n| 存储 | $1 | $2 |",
     {"texts": {"tbody td": ["服务器", "$5", "$10", "存储", "$1", "$2"]}, "count": {".math": 0}}),
    ("F9 价格和公式同一行", "| 价 | 式 |\n|---|---|\n| $5 | $a|b$ |",
     {"count": {"tbody td": 2}, "texts": {"tbody td:first-child": ["$5"]},
      "attrs": {".math": [{"data-tex": "a|b", "katex": True}]}}),
    ("F9 $env 和代码段", "先设置 $env:PATH，再运行 `$env:PATH` 检查。",
     {"texts": {"code": ["$env:PATH"]}, "count": {".math": 0}, "text": "先设置 $env:PATH，再运行 $env:PATH 检查。"}),
    ("F9 数字后的 $", "这个大约 5$，那个 10$。", {"count": {".math": 0}, "text": "这个大约 5$，那个 10$。"}),
    ("F9 美元前缀", "价格 US$5 到 US$10，以及 $x$ 和 $y$。",
     {"attrs": {".math": [{"data-tex": "x"}, {"data-tex": "y"}]}, "has": ["US$5 到 US$10"]}),
    ("F9 汉字紧挨公式", "设$x$为实数，且 $x>0$。",
     {"attrs": {".math": [{"data-tex": "x", "katex": True}, {"data-tex": "x>0", "katex": True}]}}),
    ("F9 表格里公式的竖线", "| 式 | 码 |\n|---|---|\n| $|x|$ | `p|q` |",
     {"count": {"tbody td": 2}, "texts": {"td code": ["p|q"]}, "attrs": {".math": [{"data-tex": "|x|", "katex": True}]}}),

    # F10：自动链接、看着像 HTML 的文字、相对链接
    ("F10 文件名不是网址", "改了 server.py、app.js 和 README.md，见 setup.py、desk.py。",
     {"count": {"a": 0}, "text": "改了 server.py、app.js 和 README.md，见 setup.py、desk.py。"}),
    ("F10 真网址", "见 https://example.com/a 和 www.example.org。",
     {"attrs": {"a": [{"href": "https://example.com/a", "target": "_blank", "rel": "noopener noreferrer"},
                      {"href": "http://www.example.org", "target": "_blank"}]}}),
    ("F10 不猜邮箱", "仓库 git@github.com:x/y.git", {"count": {"a": 0}}),
    ("F10 占位符和泛型", "运行 desk.py wait <id> 等回复，或者 git checkout <branch>。返回值是 Vec<String>，Option<T>。",
     {"text": "运行 desk.py wait <id> 等回复，或者 git checkout <branch>。返回值是 Vec<String>，Option<T>。"}),
    ("F10 独占一行的占位符", "用法：\n\n<id>\n\n<title> 的格式", {"has": ["<id>", "<title> 的格式"], "count": {"title": 0}}),
    ("F10 注释和占位符同段", "运行 desk.py wait <id> <!-- 注释 --> 继续", {"has": ["desk.py wait <id>", "继续"], "lacks": ["注释"]}),
    ("F10 不认的标签原样显示", "<script>alert(1)</script> 和 <style>p{}</style>",
     {"count": {"script": 0, "style": 0}, "has": ["<script>alert(1)</script>", "<style>p{}</style>"]}),
    ("F10 真 HTML 照常", "<details>\n<summary>展开</summary>\n\n内容 **粗**<br>按 <kbd>Ctrl</kbd>，H<sub>2</sub>O，x<sup>2</sup>\n\n</details>",
     {"count": {"details": 1, "summary": 1, "br": 1, "kbd": 1, "sub": 1, "sup": 1}, "texts": {"strong": ["粗"]}, "lacks": ["<"]}),
    ("F10 相对链接", "见 [app.js](src/claudedesk/assets/app.js) 和 [上文](#x)、[接口](/api/state)。",
     {"count": {"a": 0}, "attrs": {"span[title]": [{"title": "src/claudedesk/assets/app.js", "text": "app.js"},
                                                   {"title": "#x", "text": "上文"}, {"title": "/api/state", "text": "接口"}]}}),
    ("F10 外链照常", "[外链](https://example.com/x)",
     {"attrs": {"a": [{"href": "https://example.com/x", "target": "_blank", "rel": "noopener noreferrer"}]}}),

    # F15d：原始 HTML 不能跳出正文
    ("F15d 浮层 style", '<div style="position:fixed;inset:0;z-index:99;background:red;color:blue;text-align:center">盖住</div>',
     {"attrs": {"div": [{"style": "color:blue;text-align:center"}]}, "html_lacks": ["position", "z-index", "inset", "background"]}),
    ("F15d 转义绕过", '<span style="po\\73ition:fixed">x</span> <img src="https://example.com/a.png" style="position:absolute;width:20px">',
     {"attrs": {"span": [{"style": None}], "img": [{"style": "width:20px"}]}}),
    ("F15d class 和 id", '<div id="modal" class="modal-back">x</div>', {"attrs": {"div": [{"class": None, "id": "user-content-modal"}]}}),
    ("F15d 表格对齐和高亮保留", "| a | b |\n|---|---:|\n| 1 | 2 |\n\n```python\nclass Foo(Bar):\n    pass\n```",
     {"count": {'td[style="text-align:right"]': 1, ".hljs-title.class_": 2, ".hljs-title.class_.inherited__": 1}}),

    # 回归：test_ui 的 BODY
    ("回归 BODY", BODY,
     {"count": {"tbody tr": 3, "tbody td": 6, "table .math .katex": 2, ".math-display .katex-display": 1, ".math-error": 0,
                ".codeblock .code-copy": 1},
      "texts": {"table code": ["a|b"]}, "has": ["花了 $5 和 $10"],
      "attrs": {"p .math": [{"data-tex": r"e^{i\pi}+1=0", "katex": True}]}}),
]

# test_ui 的 BODY 在改动前渲染出的 HTML（清洗后、hydrate 前），必须一字不差
BODY_HTML = (
    '<p>背景说明。</p>\n'
    '<div class="table-wrap"><table>\n'
    '<thead>\n'
    '<tr>\n'
    '<th>指标</th>\n'
    '<th style="text-align:right">值</th>\n'
    '</tr>\n'
    '</thead>\n'
    '<tbody>\n'
    '<tr>\n'
    '<td>范数 <span class="math math-inline" data-tex="\\|\\theta\\|_2">$\\|\\theta\\|_2$</span></td>\n'
    '<td style="text-align:right">12.9</td>\n'
    '</tr>\n'
    '<tr>\n'
    '<td>绝对值 <span class="math math-inline" data-tex="|x|">$|x|$</span></td>\n'
    '<td style="text-align:right">3</td>\n'
    '</tr>\n'
    '<tr>\n'
    '<td>命令 <code>a|b</code></td>\n'
    '<td style="text-align:right">1</td>\n'
    '</tr>\n'
    '</tbody>\n'
    '</table></div>\n'
    '<div class="math math-display" data-tex="\\begin{aligned} a &amp;= b \\\\ c &amp;= d \\end{aligned}">$$\\begin{aligned} a &amp;= b \\\\ c &amp;= d \\end{aligned}$$</div>\n'
    '<p>花了 $5 和 $10。行内 <span class="math math-inline" data-tex="e^{i\\pi}+1=0">$e^{i\\pi}+1=0$</span>。</p>\n'
    '<div class="codeblock"><div class="code-head"><span class="code-lang">python</span></div><pre><code class="hljs language-python"><span class="hljs-built_in">print</span>(<span class="hljs-string">"hi"</span>)</code></pre></div>'
)

RENDER = """cases => cases.map(([src, sels]) => {
  const d = document.createElement("div");
  d.className = "md";
  document.body.appendChild(d);
  d.innerHTML = DeskMarkdown.toHtml(src);
  DeskMarkdown.hydrate(d);
  const q = {};
  sels.forEach(s => { q[s] = Array.from(d.querySelectorAll(s)).map(e => {
    const a = { text: e.textContent, katex: !!e.querySelector(".katex") };
    for (const at of e.attributes) a[at.name] = at.value;
    return a;
  }); });
  const html = d.innerHTML;
  d.querySelectorAll(".math").forEach(m => m.replaceWith("⟦" + m.getAttribute("data-tex") + "⟧"));
  const r = { q: q, html: html, text: d.textContent.trim() };
  d.remove();
  return r;
})"""


def _check(exp, r):
    bad = []
    if "text" in exp and r["text"] != exp["text"]:
        bad.append(f"text = {r['text']!r}")
    bad += [f"text 里没有 {s!r}" for s in exp.get("has", ()) if s not in r["text"]]
    bad += [f"text 里不该有 {s!r}" for s in exp.get("lacks", ()) if s in r["text"]]
    bad += [f"html 里不该有 {s!r}" for s in exp.get("html_lacks", ()) if s in r["html"]]
    for sel, n in exp.get("count", {}).items():
        if len(r["q"][sel]) != n:
            bad.append(f"{sel} 有 {len(r['q'][sel])} 个，应为 {n}")
    for sel, want in exp.get("texts", {}).items():
        got = [e["text"] for e in r["q"][sel]]
        if got != want:
            bad.append(f"{sel} 文字 = {got!r}")
    for sel, want in exp.get("attrs", {}).items():
        got = r["q"][sel]
        if len(got) != len(want) or any(g.get(k) != v for g, w in zip(got, want) for k, v in w.items()):
            bad.append(f"{sel} = {got!r}")
    return bad


def test_markdown_cases(env):
    d, store, server, page, errors = env
    page.goto(server.url)
    page.wait_for_function("!!window.DeskMarkdown && typeof window.markdownitCjkFriendly === 'function'")
    sels = [sorted({*e.get("count", {}), *e.get("texts", {}), *e.get("attrs", {})}) for _, _, e in CASES]
    res = page.evaluate(RENDER, [[src, s] for (_, src, _), s in zip(CASES, sels)])
    bad = [f"{name}: {b}" for (name, _, exp), r in zip(CASES, res) for b in _check(exp, r)]
    assert bad == [], "\n" + "\n".join(bad)
    assert page.evaluate("src => DeskMarkdown.toHtml(src)", BODY) == BODY_HTML
    assert errors == []


def test_body_html_stays_inside_reader(env):
    """真阅读器里：网页拷来的浮层盖不住列表，相对链接不会打开本机 404，占位符照常显示。"""
    d, store, server, page, errors = env
    a = post(d, kind="answer", title="浮层", body='报告如下：\n\n<div style="position:fixed;inset:0;z-index:99;'
             'background:#fff" class="modal-back">拷来的 HTML</div>\n\n见 [app.js](src/claudedesk/assets/app.js)，'
             '运行 desk.py wait <id>。')
    b = post(d, kind="answer", title="另一条", body="正文")
    store.poll()
    page.goto(server.url)
    page.wait_for_selector(f'.item[data-id="{a}"]')
    page.click(f'.item[data-id="{a}"]')
    page.wait_for_function("() => document.querySelector('#body').textContent.includes('拷来的 HTML')")
    box = page.locator(f'.item[data-id="{b}"]').bounding_box()
    hit = page.evaluate("([x, y]) => !!document.elementFromPoint(x, y).closest('.item')",
                        [box["x"] + box["width"] / 2, box["y"] + box["height"] / 2])
    assert hit  # 列表上露出来的还是列表项，不是正文里的浮层
    assert page.locator("#body a").count() == 0
    assert "desk.py wait <id>" in page.locator("#body").inner_text()
    page.click(f'.item[data-id="{b}"]', timeout=3000)
    page.wait_for_function("() => document.querySelector('#title').textContent === '另一条'")
    assert errors == []
