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

  function make() {
    var md = global.markdownit({ html: true, linkify: true, typographer: false, breaks: false });
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

  // 表格行里 $…$ / \(…\) 中的竖线换成占位符（代码段里的不动）
  function protectTablePipes(src) {
    var inFence = false;
    return src.split("\n").map(function (line) {
      if (/^\s*(```|~~~)/.test(line)) { inFence = !inFence; return line; }
      if (inFence || line.indexOf("|") < 0 || !/[$`]|\\\(/.test(line)) return line;
      return line.split(/(`+[^`]*`+)/).map(function (seg, i) {
        if (i % 2) return seg.split("|").join(PIPE); // 代码段里的 | 也不该切单元格
        return seg.replace(/\$\$[^$]+\$\$|\$[^$\s][^$]*?\$|\\\([\s\S]*?\\\)/g, function (m) { return m.split("|").join(PIPE); });
      }).join("");
    }).join("\n");
  }

  function toHtml(src) {
    if (!engine) engine = make();
    var html = engine.render(protectTablePipes(String(src || "")));
    html = html.split(PIPE).join("|");
    if (global.DOMPurify) {
      html = global.DOMPurify.sanitize(html, {
        ADD_ATTR: ["target", "data-tex"],
        FORBID_TAGS: ["style", "form", "input", "button", "textarea", "select", "iframe", "object", "embed"],
        ALLOW_DATA_ATTR: false,
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
      a.setAttribute("target", "_blank");
      a.setAttribute("rel", "noopener noreferrer");
    });
  }

  global.DeskMarkdown = { toHtml: toHtml, hydrate: hydrate, escapeHtml: escapeHtml };
})(typeof window !== "undefined" ? window : globalThis);
