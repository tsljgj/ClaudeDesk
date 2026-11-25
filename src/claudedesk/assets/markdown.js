/* Markdown → 安全的 HTML：GitHub 风格表格 / 任务列表 / 代码高亮 / LaTeX 公式（KaTeX）。
 *
 * 公式先在解析阶段换成占位元素 <span class="math" data-tex>，经过 DOMPurify 清洗后再由
 * KaTeX 渲染进去，所以既允许正文里夹带少量 HTML（<br>、<details> 等），又不会被公式里的
 * 尖括号、竖线、下划线搞乱表格和强调。
 *
 * 支持的公式写法：$…$、$$…$$、\(…\)、\[…\]、```math 代码块。
 * 行内 $ 采用 pandoc 规则：开头 $ 后面不能是空白，结尾 $ 前面不能是空白、后面不能紧跟数字，
 * 所以 "花了 $5 和 $10" 这种价格不会被当成公式。
 */
(function (global) {
  "use strict";

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  var PIPE = "\uE000"; // 表格行里公式中的 |，先换成占位符，免得把单元格切开

  // ---------------------------------------------------------------- 网址
  // 中文里网址常常紧挨着汉字、全角标点（"见https://x.com/a查看。"）：网址到这些字符为止
  var CJK = "\u2018-\u201f\u2026\u3000-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff\uff00-\uffef";
  var CJK_RE = new RegExp("[" + CJK + "]");
  var URL_RE = new RegExp("(?:https?:\\/\\/|www\\.)[^\\s<>\"'`" + CJK + "]+", "gi");
  var PAIRS = { ")": "(", "]": "[", "}": "{" };
  function tidyUrl(u) { // 句末的标点、没配对的右括号不算网址（"(见 https://x.com/a)。"）
    for (;;) {
      var c = u.charAt(u.length - 1);
      if (/[.,;:!?*'"]/.test(c) || (PAIRS[c] && u.split(c).length > u.split(PAIRS[c]).length)) u = u.slice(0, -1);
      else return u;
    }
  }
  function okUrl(u) { return /^(https?:\/\/[^\/?#\s.]+[^\/?#\s]*|www\.[^\/?#\s.]+\.[^\/?#\s]+)/i.test(u); } // 至少有个主机名
  function hrefOf(u) { return /^www\./i.test(u) ? "http://" + u : u; }
  // 纯文本（选项说明、追问、回复、原问题）转义后把网址变成链接
  function linkText(s) {
    s = String(s == null ? "" : s);
    var out = "", last = 0, m;
    URL_RE.lastIndex = 0;
    while ((m = URL_RE.exec(s))) {
      var u = tidyUrl(m[0]);
      if (!okUrl(u)) continue;
      out += escapeHtml(s.slice(last, m.index)) + '<a href="' + escapeHtml(hrefOf(u)) + '" target="_blank" rel="noopener noreferrer" title="点击在浏览器中打开">' +
        escapeHtml(u) + "</a>";
      last = m.index + u.length;
      URL_RE.lastIndex = last;
    }
    return out + escapeHtml(s.slice(last));
  }
  // markdown-it 的自动链接会把紧跟着的汉字也算进网址：截到第一个汉字 / 全角标点为止
  function trimMatch(m) {
    if (!m) return m;
    var i = m.raw.search(CJK_RE), raw = tidyUrl(i < 0 ? m.raw : m.raw.slice(0, i)), cut = m.raw.length - raw.length;
    if (!cut) return m;
    if (!/^mailto:/i.test(raw) && !okUrl(raw)) return null;
    m.raw = m.text = raw;
    m.url = m.url.slice(0, m.url.length - cut);
    m.lastIndex -= cut;
    return m;
  }
  // 解析器没变成链接的网址（行内代码里的、贴着汉字的）：在 DOM 上补。代码块里的不动（拖着选代码时不会变成拖链接）
  function autolink(root) {
    var w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null), hits = [], n;
    while ((n = w.nextNode())) {
      if (/https?:\/\/|www\./i.test(n.nodeValue) && !n.parentNode.closest("a, pre, .math, .katex, button, textarea")) hits.push(n);
    }
    hits.forEach(function (t) {
      var html = linkText(t.nodeValue);
      if (html.indexOf("<a ") < 0) return;
      var box = document.createElement("span"), frag = document.createDocumentFragment();
      box.innerHTML = html;
      while (box.firstChild) frag.appendChild(box.firstChild);
      t.parentNode.replaceChild(frag, t);
    });
  }

  function mathTag(tex, display, block) {
    tex = tex.split(PIPE).join("|");
    var tag = block ? "div" : "span";
    return "<" + tag + ' class="math ' + (display ? "math-display" : "math-inline") + '" data-tex="' +
      escapeHtml(tex) + '">' + escapeHtml(display ? "$$" + tex + "$$" : "$" + tex + "$") + "</" + tag + ">";
  }

  // ---------------------------------------------------------------- 行内公式
  function mathInline(state, silent) {
    var src = state.src, pos = state.pos, max = state.posMax, ch = src.charCodeAt(pos);
    var start, end, display = false, content;

    if (ch === 0x5c /* \ */ && pos + 1 < max) {
      var nx = src[pos + 1];
      if (nx !== "(" && nx !== "[") return false;
      var close = nx === "(" ? "\\)" : "\\]";
      end = src.indexOf(close, pos + 2);
      if (end < 0 || end >= max) return false;
      content = src.slice(pos + 2, end);
      if (!content.trim()) return false;
      if (!silent) {
        var t = state.push("math_inline", "math", 0);
        t.content = content;
        t.markup = nx === "(" ? "\\(" : "\\[";
        t.meta = { display: nx === "[" };
      }
      state.pos = end + 2;
      return true;
    }

    if (ch !== 0x24 /* $ */) return false;
    if (pos > 0 && src.charCodeAt(pos - 1) === 0x5c) return false; // \$ 是转义的美元符号

    if (src.charCodeAt(pos + 1) === 0x24) { // 行内 $$…$$：按块级公式显示
      start = pos + 2;
      end = src.indexOf("$$", start);
      if (end < 0 || end >= max) return false;
      content = src.slice(start, end);
      if (!content.trim()) return false;
      display = true;
      if (!silent) {
        var td = state.push("math_inline", "math", 0);
        td.content = content;
        td.markup = "$$";
        td.meta = { display: true };
      }
      state.pos = end + 2;
      return true;
    }

    if (pos > 0 && /[0-9A-Za-z]/.test(src[pos - 1])) return false; // "5$，那个 10$" 里的 $ 是货币单位，不是公式开头
    start = pos + 1;
    if (start >= max) return false;
    var first = src.charCodeAt(start);
    if (first === 0x20 || first === 0x09 || first === 0x0a) return false;
    // 下一个没转义的 $ 必须就是合法的结尾，否则整个不算公式（"$5 和 $10" 这类价格就不会被吞掉）
    end = start;
    for (;;) {
      end = src.indexOf("$", end);
      if (end < 0 || end >= max) return false;
      if (src.charCodeAt(end - 1) === 0x5c) { end += 1; continue; }
      break;
    }
    var prev = src.charCodeAt(end - 1);
    var next = end + 1 < src.length ? src.charCodeAt(end + 1) : 0;
    if (prev === 0x20 || prev === 0x09 || prev === 0x0a || (next >= 0x30 && next <= 0x39)) return false;
    content = src.slice(start, end);
    if (content.indexOf("`") >= 0) return false; // "$env:PATH … `$env:PATH`"：结尾的 $ 在代码段里，不能把代码段吞掉
    if (!silent) {
      var ti = state.push("math_inline", "math", 0);
      ti.content = content;
      ti.markup = "$";
      ti.meta = { display: display };
    }
    state.pos = end + 1;
    return true;
  }

  // ---------------------------------------------------------------- 块级公式 $$ … $$ / \[ … \]
  function mathBlock(state, startLine, endLine, silent) {
    var pos = state.bMarks[startLine] + state.tShift[startLine];
    var max = state.eMarks[startLine];
    if (state.sCount[startLine] - state.blkIndent >= 4) return false;
    var line = state.src.slice(pos, max);
    var open, close;
    if (line.indexOf("$$") === 0) { open = "$$"; close = "$$"; }
    else if (line.indexOf("\\[") === 0) { open = "\\["; close = "\\]"; }
    else return false;

    var rest = line.slice(open.length);
    var content, next = startLine, found = false;
    var endIdx = rest.indexOf(close);
    if (endIdx >= 0) { // 一行内开也关
      if (rest.slice(endIdx + close.length).trim()) return false; // 后面还有字：交给行内规则
      content = rest.slice(0, endIdx);
      found = true;
    } else {
      var lines = [rest];
      for (next = startLine + 1; next < endLine; next++) {
        var p = state.bMarks[next] + state.tShift[next];
        var m = state.eMarks[next];
        if (p < m && state.sCount[next] < state.blkIndent) break;
        var l = state.src.slice(p, m);
        var ci = l.indexOf(close);
        if (ci >= 0) {
          lines.push(l.slice(0, ci));
          found = true;
          break;
        }
        lines.push(state.src.slice(state.bMarks[next], m));
      }
      content = lines.join("\n");
    }
    if (!found || !content.trim()) return false;
    if (silent) return true;
    state.line = next + 1;
    var t = state.push("math_block", "math", 0);
    t.block = true;
    t.content = content.trim();
    t.map = [startLine, state.line];
    t.markup = open;
    return true;
  }

  // ---------------------------------------------------------------- 提示块：> [!NOTE] / [!TIP] / [!IMPORTANT] / [!WARNING] / [!CAUTION]
  // GitHub 的写法；agent 常用它标"注意 / 风险"。引用块第一行是标记就整块换成带标题的彩色提示框
  var CALLOUT = { note: "说明", tip: "提示", important: "重要", warning: "注意", caution: "警告" };
  var CALLOUT_RE = /^\[!(note|tip|important|warning|caution)\][ \t]*(?:\n|$)/i;
  function callouts(state) {
    var t = state.tokens;
    for (var i = 0; i + 3 < t.length; i++) {
      if (t[i].type !== "blockquote_open" || t[i + 1].type !== "paragraph_open" || t[i + 2].type !== "inline") continue;
      var inl = t[i + 2], m = CALLOUT_RE.exec(inl.content);
      if (!m) continue;
      t[i].meta = t[i].meta || {};
      t[i].meta.callout = m[1].toLowerCase();
      var rest = inl.content.slice(m[0].length);
      inl.content = rest;
      inl.children = [];
      if (rest.trim()) state.md.inline.parse(rest, state.md, state.env, inl.children);
      else { t[i + 1].hidden = true; t[i + 3].hidden = true; } // 标记单独一行：不留空段落
    }
  }

  // ---------------------------------------------------------------- 任务列表 [ ] / [x]
  function taskLists(state) {
    var tokens = state.tokens;
    for (var i = 2; i < tokens.length; i++) {
      var t = tokens[i];
      if (t.type !== "inline" || tokens[i - 1].type !== "paragraph_open" || tokens[i - 2].type !== "list_item_open") continue;
      var m = /^\[([ xX])\]\s+/.exec(t.content);
      if (!m) continue;
      var checked = m[1] !== " ";
      t.content = t.content.slice(m[0].length);
      if (t.children && t.children.length && t.children[0].type === "text") {
        t.children[0].content = t.children[0].content.replace(/^\[[ xX]\]\s+/, "");
      }
      var box = new state.Token("html_inline", "", 0);
      box.content = '<span class="task' + (checked ? " done" : "") + '"></span>';
      t.children.unshift(box);
      tokens[i - 2].attrJoin("class", "task-item");
    }
  }

  function highlight(code, lang) {
    var hl = global.hljs;
    var label = lang ? escapeHtml(lang) : "";
    var html;
    try {
      if (hl && lang && hl.getLanguage(lang)) html = hl.highlight(code, { language: lang, ignoreIllegals: true }).value;
      else html = escapeHtml(code);
    } catch (e) {
      html = escapeHtml(code);
    }
    return '<div class="codeblock"><div class="code-head"><span class="code-lang">' + label +
      '</span></div><pre><code class="hljs' +
      (lang ? " language-" + label : "") + '">' + html + "</code></pre></div>";
  }

  // 正文里当真 HTML 用的标签（只认小写）。其余的像 <id>、<branch>、Vec<String>、<T> 都是占位符 / 泛型，原样显示
  var HTML_OK = /^(a|abbr|b|blockquote|br|caption|cite|code|col|colgroup|dd|del|details|div|dl|dt|em|figcaption|figure|h[1-6]|hr|i|img|ins|kbd|li|mark|ol|p|pre|q|rp|rt|ruby|s|samp|small|span|strong|sub|summary|sup|table|tbody|td|tfoot|th|thead|tr|u|ul|wbr)$/;
  var HTML_TAG = /<\/?([A-Za-z][A-Za-z0-9-]*)(?:\s+[^\s"'>\/=]+(?:\s*=\s*(?:[^\s"'=<>`]+|'[^']*'|"[^"]*"))?)*\s*\/?>/g;
  function safeTags(html) { // 注释本来就不显示，先去掉（留着会让 DOMPurify 把同段的 "<id>" 文字连段落一起删掉）；<?…?>、<!…> 原样显示
    return html.replace(/<!--[\s\S]*?-->/g, "").replace(/<(?=[?!])/g, "&lt;")
      .replace(HTML_TAG, function (t, name) { return HTML_OK.test(name) ? t : escapeHtml(t); });
  }

  function make() {
    var md = global.markdownit({ html: true, linkify: true, typographer: false, breaks: false });
    // 中文粗体："**结论：**建议" 这类结尾 ** 紧挨全角标点、后面跟汉字的，CommonMark 原规则闭合不了
    if (global.markdownitCjkFriendly) md.use(global.markdownitCjkFriendly);
    // 只把 http(s):// / www. / mailto: 开头的变成链接：server.py、README.md 的后缀也是顶级域名，不能当网址
    var match = md.linkify.match.bind(md.linkify), LINKISH = /^(https?:\/\/|ftp:\/\/|mailto:|www\.)/i;
    md.linkify.match = function (text) {
      return (match(text) || []).map(trimMatch).filter(function (m) { return m && LINKISH.test(m.raw); });
    };
    if (md.linkify.matchAtStart) { // "见https://…"：紧跟在汉字后面的网址走的是这条路
      var atStart = md.linkify.matchAtStart.bind(md.linkify);
      md.linkify.matchAtStart = function (text) {
        var m = trimMatch(atStart(text));
        return m && LINKISH.test(m.raw) ? m : null;
      };
    }
    md.inline.ruler.before("escape", "math_inline", mathInline);
    md.block.ruler.after("blockquote", "math_block", mathBlock, { alt: ["paragraph", "reference", "blockquote", "list"] });
    md.core.ruler.after("inline", "task_lists", taskLists);
    md.core.ruler.after("inline", "callouts", callouts);
    md.renderer.rules.blockquote_open = function (tokens, idx, options, env, self) {
      var c = tokens[idx].meta && tokens[idx].meta.callout;
      if (!c) return self.renderToken(tokens, idx, options);
      return '<blockquote class="callout callout-' + c + '"><p class="callout-title">' + CALLOUT[c] + "</p>\n";
    };
    md.renderer.rules.math_inline = function (tokens, idx) {
      return mathTag(tokens[idx].content, !!(tokens[idx].meta && tokens[idx].meta.display));
    };
    md.renderer.rules.math_block = function (tokens, idx) { return mathTag(tokens[idx].content, true, true) + "\n"; };
    md.renderer.rules.fence = function (tokens, idx) {
      var t = tokens[idx];
      var lang = (t.info || "").trim().split(/\s+/)[0].toLowerCase();
      if (lang === "math" || lang === "katex") return mathTag(t.content.trim(), true, true) + "\n";
      return highlight(t.content.replace(/\n$/, ""), lang);
    };
    md.renderer.rules.code_block = function (tokens, idx) { return highlight(tokens[idx].content.replace(/\n$/, ""), ""); };
    md.renderer.rules.html_inline = function (tokens, idx) { return safeTags(tokens[idx].content); };
    md.renderer.rules.html_block = function (tokens, idx, options, env) {
      var c = tokens[idx].content, m = /^\s*<\/?([A-Za-z][A-Za-z0-9-]*)/.exec(c);
      if (m ? HTML_OK.test(m[1]) : /^\s*<!--/.test(c)) return safeTags(c);
      // 独占一行的 <id>、<title>、<?xml …?> 也会被当成 HTML 块：退回普通段落，里面的 Markdown 照常解析
      return "<p>" + md.renderInline(c.trim(), env) + "</p>\n";
    };
    md.renderer.rules.table_open = function () { return '<div class="table-wrap"><table>\n'; };
    md.renderer.rules.table_close = function () { return "</table></div>\n"; };
    var defaultLink = md.renderer.rules.link_open || function (tokens, idx, options, env, self) {
      return self.renderToken(tokens, idx, options);
    };
    md.renderer.rules.link_open = function (tokens, idx, options, env, self) {
      tokens[idx].attrSet("target", "_blank");
      tokens[idx].attrSet("rel", "noopener noreferrer");
      return defaultLink(tokens, idx, options, env, self);
    };
    return md;
  }

  var engine = null;

  // 表格行里 $…$ / \(…\) 中的竖线换成占位符（代码段里的不动）。$…$ 的判定和 mathInline 一致，
  // 否则 "| $5 | $10 |" 这种价格会被当成一个公式，表格少一列
  var TABLE_MATH = /\$\$[^$]+\$\$|(?<![0-9A-Za-z\\])\$(?=[^$\s])(?:\\\$|[^$`])*?[^$\s\\]\$(?!\d)|\\\([\s\S]*?\\\)/g;
  function protectTablePipes(src) {
    var inFence = false;
    return src.split("\n").map(function (line) {
      if (/^\s*(```|~~~)/.test(line)) { inFence = !inFence; return line; }
      if (inFence || line.indexOf("|") < 0 || !/[$`]|\\\(/.test(line)) return line;
      return line.split(/(`+[^`]*`+)/).map(function (seg, i) {
        if (i % 2) return seg.split("|").join(PIPE); // 代码段里的 | 也不该切单元格
        return seg.replace(TABLE_MATH, function (m) { return m.split("|").join(PIPE); });
      }).join("");
    }).join("\n");
  }

  // 正文里的原始 HTML 不能跳出正文：style 只留排版用的几项（position、z-index、inset、transform 能盖住整个界面），
  // class 只留本文件自己生成的（否则 class="modal-back" 之类会套上界面自己的浮层样式）
  var STYLE_OK = /^(text-align|vertical-align|color|background-color|font-weight|font-style|text-decoration(-[a-z]+)?|white-space|(min-|max-)?(width|height))$/;
  var CLASS_OK = /^(math|math-inline|math-display|codeblock|code-head|code-lang|hljs|hljs-[\w-]+|language-[\w+#.-]+|[\w-]+_|task|done|task-item|table-wrap|callout|callout-(?:note|tip|important|warning|caution|title))$/;
  function cleanAttr(node, data) {
    var kept;
    if (data.attrName === "style") {
      kept = String(data.attrValue).split(";").filter(function (d) {
        var i = d.indexOf(":");
        return i > 0 && STYLE_OK.test(d.slice(0, i).trim().toLowerCase()) && !/url\(|expression|\/\*|\\/i.test(d);
      });
      data.attrValue = kept.join(";");
    } else if (data.attrName === "class") {
      kept = String(data.attrValue).split(/\s+/).filter(function (c) { return CLASS_OK.test(c); });
      data.attrValue = kept.join(" ");
    } else return;
    if (!kept.length) data.keepAttr = false;
  }

  function toHtml(src) {
    if (!engine) {
      engine = make();
      if (global.DOMPurify) global.DOMPurify.addHook("uponSanitizeAttribute", cleanAttr);
    }
    var html = engine.render(protectTablePipes(String(src || "")));
    html = html.split(PIPE).join("|");
    if (global.DOMPurify) {
      html = global.DOMPurify.sanitize(html, {
        ADD_ATTR: ["target", "data-tex"],
        ADD_URI_SAFE_ATTR: ["data-tex"], // 否则 "f: X \to Y" 像个未知协议的网址，data-tex 会被删掉，公式出不来
        FORBID_TAGS: ["style", "form", "input", "button", "textarea", "select", "iframe", "object", "embed"],
        ALLOW_DATA_ATTR: false,
        SANITIZE_NAMED_PROPS: true, // id="modal" 之类加前缀 user-content-，不会和界面自己的 id 撞上
      });
    }
    return html;
  }

  // 把占位元素渲染成公式；渲染失败就原样显示 TeX 并标红
  function hydrate(root) {
    var katex = global.katex;
    root.querySelectorAll(".math[data-tex]").forEach(function (el) {
      var tex = el.getAttribute("data-tex");
      var display = el.classList.contains("math-display");
      if (!katex) return;
      try {
        katex.render(tex, el, { displayMode: display, throwOnError: true, strict: "ignore", trust: false, output: "htmlAndMathml" });
      } catch (e) {
        el.classList.add("math-error");
        el.textContent = display ? tex : "$" + tex + "$";
        el.title = String((e && e.message) || e);
      }
    });
    root.querySelectorAll(".code-head").forEach(function (h) {  // 复制按钮在清洗之后加，免得被 DOMPurify 去掉
      if (h.querySelector(".code-copy")) return;
      var b = document.createElement("button");
      b.type = "button";
      b.className = "code-copy";
      b.textContent = "复制";
      h.appendChild(b);
    });
    autolink(root);
    root.querySelectorAll("a[href]").forEach(function (a) {
      if (a.origin === location.origin) { // [app.js](src/…) 这类相对链接指向本机服务器，打开只会 404：换成文字，悬停看路径
        var s = document.createElement("span");
        s.title = a.getAttribute("href");
        while (a.firstChild) s.appendChild(a.firstChild);
        a.parentNode.replaceChild(s, a);
        return;
      }
      a.setAttribute("target", "_blank");
      a.setAttribute("rel", "noopener noreferrer");
      // 程序窗口没有状态栏：[文字](网址) 悬停时看得到会打开哪里
      if (!a.title) a.title = a.textContent.trim() !== a.getAttribute("href") ? a.href : "点击在浏览器中打开";
    });
  }

  global.DeskMarkdown = { toHtml: toHtml, hydrate: hydrate, escapeHtml: escapeHtml, linkText: linkText };
})(typeof window !== "undefined" ? window : globalThis);
