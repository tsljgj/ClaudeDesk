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
    var match = md.linkify.match.bind(md.linkify);
    md.linkify.match = function (text) {
      return (match(text) || []).filter(function (m) { return /^(https?:\/\/|ftp:\/\/|mailto:|www\.)/i.test(m.raw); });
    };
    md.inline.ruler.before("escape", "math_inline", mathInline);
    md.block.ruler.after("blockquote", "math_block", mathBlock, { alt: ["paragraph", "reference", "blockquote", "list"] });
    md.core.ruler.after("inline", "task_lists", taskLists);
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
  var CLASS_OK = /^(math|math-inline|math-display|codeblock|code-head|code-lang|hljs|hljs-[\w-]+|language-[\w+#.-]+|[\w-]+_|task|done|task-item|table-wrap)$/;
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
    });
  }

  global.DeskMarkdown = { toHtml: toHtml, hydrate: hydrate, escapeHtml: escapeHtml };
})(typeof window !== "undefined" ? window : globalThis);
