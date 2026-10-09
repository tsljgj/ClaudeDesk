/* ClaudeDesk 界面逻辑。数据来自本机服务（/api/state 长轮询），操作走 /api/action。 */
(function () {
  "use strict";

  var BOOT = window.BOOT || {};
  var MD = window.DeskMarkdown;
  var $ = function (id) { return document.getElementById(id); };
  var esc = MD.escapeHtml;

  // ---------------------------------------------------------------- 图标（线性，24 网格）
  var ICONS = {
    decide: '<path d="M12 13v8"/><path d="M12 3v3"/><path d="M18 6a2 2 0 0 1 1.4.6l2.3 2.2a1 1 0 0 1 0 1.4l-2.3 2.2A2 2 0 0 1 18 13H6a2 2 0 0 1-1.4-.6L2.3 10.2a1 1 0 0 1 0-1.4L4.6 6.6A2 2 0 0 1 6 6z"/>',
    answer: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><path d="M8 8h8"/><path d="M8 12h5"/>',
    info: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
    all: '<path d="m12 2 10 5-10 5L2 7z"/><path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/>',
    archive: '<rect width="20" height="5" x="2" y="3" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"/><path d="M10 12h4"/>',
    unarchive: '<rect width="20" height="5" x="2" y="3" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h2"/><path d="M20 8v11a2 2 0 0 1-2 2h-2"/><path d="m9 15 3-3 3 3"/><path d="M12 12v9"/>',
    inbox: '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
    search: '<circle cx="11" cy="11" r="7.5"/><path d="m20.5 20.5-4-4"/>',
    copy: '<rect width="13" height="13" x="9" y="9" rx="2.5"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    fileDown: '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M12 18v-6"/><path d="m9 15 3 3 3-3"/>',
    mail: '<rect width="20" height="16" x="2" y="4" rx="2.5"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>',
    mailOpen: '<path d="M21.2 8.4c.5.38.8.97.8 1.6v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V10a2 2 0 0 1 .8-1.6l8-6a2 2 0 0 1 2.4 0l8 6Z"/><path d="m22 10-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 10"/>',
    trash: '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><path d="M10 11v6"/><path d="M14 11v6"/>',
    settings: '<path d="M20 7h-9"/><path d="M14 17H5"/><circle cx="17" cy="17" r="3"/><circle cx="7" cy="7" r="3"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    checks: '<path d="M18 6 7 17l-5-5"/><path d="m22 10-7.5 7.5L13 16"/>',
    chevronDown: '<path d="m6 9 6 6 6-6"/>',
    chevronLeft: '<path d="m15 18-6-6 6-6"/>',
    x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    more: '<circle cx="12" cy="12" r="1.2"/><circle cx="19" cy="12" r="1.2"/><circle cx="5" cy="12" r="1.2"/>',
    star: '<path d="M12 3.5l2.5 5.2 5.7.8-4.1 4 1 5.7L12 16.5l-5.1 2.7 1-5.7-4.1-4 5.7-.8z"/>',
    refresh: '<path d="M21 12a9 9 0 1 1-2.64-6.36L21 8"/><path d="M21 3v5h-5"/>',
    folder: '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
    keyboard: '<rect width="20" height="14" x="2" y="5" rx="2.5"/><path d="M6 9h.01M10 9h.01M14 9h.01M18 9h.01M7 15h10"/>',
    text: '<path d="M4 7V5h16v2"/><path d="M12 5v14"/><path d="M9 19h6"/>',
    rich: '<path d="M4 6h16"/><path d="M4 12h10"/><path d="M4 18h16"/><path d="M18 10l2 2-2 2"/>',
    sparkle: '<path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/>',
  };
  function icon(name, cls) {
    return '<i data-icon class="' + (cls || "") + '"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + (ICONS[name] || "") + "</svg></i>";
  }
  function paintIcons(root) {
    (root || document).querySelectorAll("i[data-icon]:empty").forEach(function (el) {
      var n = el.getAttribute("data-icon");
      el.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + (ICONS[n] || "") + "</svg>";
    });
  }

  // ---------------------------------------------------------------- 状态
  var VIEWS = [
    { id: "decide", label: "决定", empty: "没有要你决定的事", emptySub: "会话需要你拍板时，会出现在这里" },
    { id: "answer", label: "回答", empty: "还没有回答", emptySub: "你问 Claude 的问题，完整答案收在这里" },
    { id: "all", label: "全部", empty: "收件箱是空的", emptySub: "一切都处理完了" },
    { id: "archive", label: "归档", empty: "归档是空的", emptySub: "按 E 把处理完的消息收起来" },
  ];
  var KIND = { decision: "决定", answer: "回答", info: "通知" };

  var S = {
    version: -1, msgs: [], byId: {}, counts: {}, settings: BOOT.settings || {}, meta: {},
    view: load("view", "decide"), projects: loadSet("projects"), query: "", searchIds: null,
    current: null, multi: new Set(), anchor: null, choice: null,
    details: {}, shownKey: null, visible: [],
  };

  function loadSet(k) { try { var v = JSON.parse(load(k, "[]")); return new Set(Array.isArray(v) ? v : []); } catch (e) { return new Set(); } }
  function load(k, d) { try { var v = localStorage.getItem("desk." + k); return v == null ? d : v; } catch (e) { return d; } }
  function save(k, v) { try { localStorage.setItem("desk." + k, v); } catch (e) { /* 隐私模式等 */ } }

  // ---------------------------------------------------------------- 服务端
  function api(path) {
    return fetch(path, { headers: { "X-Desk-Token": BOOT.token } }).then(function (r) {
      if (!r.ok && r.status !== 404) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }
  function act(body) {
    return fetch("/api/action", {
      method: "POST", headers: { "X-Desk-Token": BOOT.token, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (!res.ok) throw new Error(res.message || "操作失败");
      return res.result;
    });
  }

  var polling = false;
  function poll() {
    if (polling) return;
    polling = true;
    var url = "/api/state?since=" + S.version + "&wait=" + (S.version >= 0 ? 25 : 0);
    api(url).then(function (st) {
      polling = false;
      apply(st);
      setTimeout(poll, 30);
    }).catch(function () {
      polling = false;
      setTimeout(poll, 2000);
    });
  }
  function refreshNow() { // 自己做了操作：不等长轮询，立刻拿一次
    return api("/api/state?since=-1").then(apply).catch(function () {});
  }

  function apply(st) {
    if (st.version === S.version && S.msgs.length) return;
    S.version = st.version;
    S.msgs = st.messages || [];
    S.byId = {};
    S.msgs.forEach(function (m) { S.byId[m.id] = m; });
    S.counts = st.counts || {};
    S.meta = st.meta || {};
    S.aliases = st.aliases || {};
    if (st.settings) applySettings(st.settings);
    S.multi.forEach(function (id) { if (!S.byId[id]) S.multi.delete(id); });
    if (S.current && !S.byId[S.current]) S.current = null;
    if (S.query) runSearch(); else renderAll();
  }

  function applySettings(s) {
    S.settings = s;
    var d = document.documentElement;
    d.dataset.theme = s.theme; d.dataset.accent = s.accent; d.dataset.font = s.font;
    d.dataset.size = s.size; d.dataset.density = s.density;
  }

  // ---------------------------------------------------------------- 列表筛选
  function inView(m, v) {
    if (v === "archive") return m.archived;
    if (m.archived) return false;
    if (v === "decide") return m.kind === "decision";
    if (v === "answer") return m.kind === "answer";
    return true;
  }
  // ---- 项目（仓库）。项目名由服务端给：desk.py 发消息时识别出的 git 仓库；旧消息按来源对到已知仓库，
  // 对不上的归"其他"（project_kind = other），可以右键"归到项目"。
  var OTHER = "__other__";
  // 项目颜色：避开橙 / 红（界面里橙色表示"要你处理"）
  var PCOLORS = ["#1C7ED6", "#2F9E44", "#9C36B5", "#0C8599", "#C2255C", "#5F3DC4", "#66A80F", "#495057"];
  var pcolorMap = (function () { try { return JSON.parse(load("pcolors", "{}")) || {}; } catch (e) { return {}; } })();
  function projectOf(m) { return m.project || "unknown"; }
  function tabKey(m) { return m.project_kind === "other" ? OTHER : projectOf(m); }
  function pcolor(name) {
    if (name === OTHER) return "var(--ink-4)";
    if (!(name in pcolorMap)) { // 新项目：给第一个还没人用的颜色，记下来，以后不变
      var used = {};
      Object.keys(pcolorMap).forEach(function (k) { used[pcolorMap[k]] = 1; });
      var i = 0;
      while (i < PCOLORS.length && used[i]) i++;
      if (i === PCOLORS.length) { // 都用过了：按名字散列
        i = 0;
        for (var j = 0; j < name.length; j++) i = (i * 31 + name.charCodeAt(j)) >>> 0;
        i %= PCOLORS.length;
      }
      pcolorMap[name] = i;
      save("pcolors", JSON.stringify(pcolorMap));
    }
    return PCOLORS[pcolorMap[name]];
  }
  function inScope(m) { return !S.projects.size || S.projects.has(tabKey(m)); }
  function onlyProject() { // 只选了一个真正的仓库时返回它的名字
    if (S.projects.size !== 1) return "";
    var k = S.projects.values().next().value;
    return k === OTHER ? "" : k;
  }
  // 标签：仓库按"有待决定的在前，再按最近一条消息"排，"其他"永远在最后
  function projectList() {
    var map = {};
    S.msgs.forEach(function (m) {
      var k = tabKey(m);
      var e = map[k] || (map[k] = { key: k, name: k === OTHER ? "其他" : k, open: 0, unread: 0, last: "", total: 0 });
      if (m.ts > e.last) e.last = m.ts;
      if (m.archived) return;
      e.total++;
      if (m.open) e.open++;
      if (m.unread) e.unread++;
    });
    return Object.keys(map).map(function (k) { return map[k]; }).sort(function (a, b) {
      return (a.key === OTHER) - (b.key === OTHER) || (b.open > 0) - (a.open > 0) ||
        (b.last > a.last ? 1 : b.last < a.last ? -1 : 0);
    });
  }
  function groupOrder() { // 分组顺序：仓库按标签顺序，"其他"里的各来源按最近时间
    var order = {}, n = 0, others = {};
    projectList().forEach(function (p) { if (p.key !== OTHER) order[p.key] = n++; });
    S.msgs.forEach(function (m) {
      if (m.project_kind === "other" && (!others[projectOf(m)] || m.ts > others[projectOf(m)])) others[projectOf(m)] = m.ts;
    });
    Object.keys(others).sort(function (a, b) { return others[b] > others[a] ? 1 : -1; })
      .forEach(function (k) { if (!(k in order)) order[k] = n++; });
    return order;
  }
  function grouped() {
    if (onlyProject()) return false;
    var seen = {}, n = 0;
    S.msgs.forEach(function (m) { if (inScope(m) && !seen[projectOf(m)]) { seen[projectOf(m)] = 1; n++; } });
    return n > 1;
  }

  function viewItems() {
    var v = S.view;
    var items = S.msgs.filter(function (m) { return inView(m, v) && inScope(m); });
    if (S.searchIds) items = items.filter(function (m) { return S.searchIds.has(m.id); });
    if (grouped()) { // 按项目分组，组内仍按时间倒序（服务端给的顺序）
      var order = groupOrder();
      items = items.map(function (m, i) { return [m, i]; }).sort(function (a, b) {
        return order[projectOf(a[0])] - order[projectOf(b[0])] || a[1] - b[1];
      }).map(function (x) { return x[0]; });
    }
    return items;
  }

  function scopeCounts() {
    var c = { open: 0, unread_answers: 0, unread: 0 };
    S.msgs.forEach(function (m) {
      if (m.archived || !inScope(m)) return;
      if (m.open) c.open++;
      if (m.unread) { c.unread++; if (m.kind === "answer") c.unread_answers++; }
    });
    return c;
  }

  // 点标签：只看这个；再点一次（它是唯一选中的）= 取消，回到全部。Ctrl / Shift + 点 = 加选 / 减选
  function clickTab(key, multi) {
    if (!key) S.projects = new Set();
    else if (multi) { if (S.projects.has(key)) S.projects.delete(key); else S.projects.add(key); }
    else if (S.projects.size === 1 && S.projects.has(key)) S.projects = new Set();
    else S.projects = new Set([key]);
    applyProjects();
  }
  function applyProjects() {
    save("projects", JSON.stringify(Array.from(S.projects)));
    S.multi.clear();
    if (S.current && S.byId[S.current] && !inScope(S.byId[S.current])) S.current = null;
    renderAll();
  }
  function setProject(p) { S.projects = p ? new Set([p]) : new Set(); applyProjects(); } // 测试 / 通知用
  function scopeLabel() {
    if (!S.projects.size) return "";
    if (S.projects.size === 1) { var k = S.projects.values().next().value; return k === OTHER ? "其他" : k; }
    return S.projects.size + " 个项目";
  }

  function dayKey(d) { return d.getFullYear() + "-" + d.getMonth() + "-" + d.getDate(); }
  function fmtTime(ts, full) {
    var d = new Date(ts), now = new Date();
    var hm = pad(d.getHours()) + ":" + pad(d.getMinutes());
    if (full) return d.getFullYear() + "年" + (d.getMonth() + 1) + "月" + d.getDate() + "日 " + hm;
    if (dayKey(d) === dayKey(now)) return hm;
    var yest = new Date(now); yest.setDate(now.getDate() - 1);
    if (dayKey(d) === dayKey(yest)) return "昨天";
    if (d.getFullYear() === now.getFullYear()) return (d.getMonth() + 1) + "月" + d.getDate() + "日";
    return d.getFullYear() + "/" + (d.getMonth() + 1) + "/" + d.getDate();
  }
  function pad(n) { return n < 10 ? "0" + n : "" + n; }

  // ---------------------------------------------------------------- 渲染
  function renderAll() {
    renderNav();
    renderList();
    renderReader();
    renderFoot();
  }

  function renderNav() {
    var c = S.counts, sc = scopeCounts();
    var n = { decide: [sc.open, true], answer: [sc.unread_answers], all: [sc.unread], archive: [0] };
    $("nav").innerHTML = VIEWS.map(function (v) {
      var k = n[v.id];
      return '<button class="tab' + (S.view === v.id ? " active" : "") + '" data-view="' + v.id + '">' + v.label +
        (k[0] ? '<span class="n' + (k[1] ? " hot" : "") + '">' + k[0] + "</span>" : "") + "</button>";
    }).join("");
    renderProjects();
    var t = [];
    if (c.open) t.push(c.open + " 待决定");
    if (c.unread) t.push(c.unread + " 未读");
    document.title = "ClaudeDesk" + (t.length ? " · " + t.join(" · ") : "");
  }

  function renderProjects() {
    var ps = projectList();
    var keys = {};
    ps.forEach(function (p) { keys[p.key] = 1; });
    var gone = Array.from(S.projects).filter(function (k) { return !keys[k]; });
    if (gone.length && S.msgs.length) { gone.forEach(function (k) { S.projects.delete(k); }); save("projects", JSON.stringify(Array.from(S.projects))); }
    var tab = function (p) {
      var on = p ? S.projects.has(p.key) : !S.projects.size;
      var badge = p ? (p.open ? '<span class="n hot">' + p.open + "</span>" : p.unread ? '<span class="n">' + p.unread + "</span>" : "") : "";
      var tip = p ? (p.key === OTHER ? "没认出仓库的消息（旧消息，或不在 git 仓库里发的）。右键分组标题可以归到某个项目" : p.name +
        (p.open ? " · " + p.open + " 条待决定" : "") + (p.unread ? " · " + p.unread + " 条未读" : "")) +
        "\n点：只看它（再点取消）· Ctrl/Shift + 点：多选 · 右键：归到别的项目" : "所有项目";
      return '<button class="ptab' + (on ? " on" : "") + (p && p.key === OTHER ? " other" : "") + '" data-project="' + esc(p ? p.key : "") +
        '" role="tab" aria-selected="' + on + '" title="' + esc(tip) + '">' +
        (p ? '<span class="pdot" style="background:' + pcolor(p.key) + '"></span>' : "") +
        '<span class="pname">' + esc(p ? p.name : "全部") + "</span>" + badge + "</button>";
    };
    var box = $("projects");
    box.innerHTML = tab(null) + ps.map(tab).join("");
    var on = box.querySelector(".ptab.on");
    if (on && (on.offsetLeft < box.scrollLeft || on.offsetLeft + on.offsetWidth > box.scrollLeft + box.clientWidth)) {
      box.scrollLeft = on.offsetLeft - 8;
    }
  }

  // 右键标签 / 分组标题：把这个项目（或没认出来的来源）归到另一个项目下
  function mergeMenu(x, y, from) {
    var targets = projectList().filter(function (p) { return p.key !== OTHER && p.key !== from; });
    var undo = Object.keys(S.aliases || {}).filter(function (k) { return S.aliases[k] === from; });
    var html = '<div class="menu-label">把「' + esc(from) + "」归到：</div>" +
      (targets.length ? targets.map(function (p) {
        return '<button class="menu-item" data-to="' + esc(p.key) + '"><span class="pdot" style="background:' + pcolor(p.key) + '"></span>' + esc(p.name) + "</button>";
      }).join("") : '<div class="menu-label">（还没有别的项目）</div>') +
      (undo.length ? '<div class="menu-sep"></div>' + undo.map(function (k) {
        return '<button class="menu-item" data-undo="' + esc(k) + '">' + icon("x") + "把「" + esc(k) + "」拆出来</button>";
      }).join("") : "");
    var fake = { getBoundingClientRect: function () { return { left: x, right: x + 1, top: y, bottom: y }; } };
    openPopover(fake, html, "", function (ev) {
      var b = ev.target.closest("[data-to],[data-undo]");
      if (!b) return;
      closePopover();
      var body = b.dataset.to ? { action: "alias", from: from, to: b.dataset.to } : { action: "alias", from: b.dataset.undo, to: "" };
      act(body).then(function () {
        toast(b.dataset.to ? "已把「" + from + "」归到「" + b.dataset.to + "」" : "已拆出「" + b.dataset.undo + "」");
        return refreshNow();
      }).catch(function (e) { toast(e.message, { bad: true }); });
    });
  }

  function renderList() {
    var v = VIEWS.filter(function (x) { return x.id === S.view; })[0] || VIEWS[0];
    var items = viewItems();
    S.visible = items.map(function (m) { return m.id; });
    var list = $("list");
    if (!items.length) {
      list.innerHTML = '<div class="list-empty"><b>' +
        (S.query ? "没有找到「" + esc(S.query) + "」" : (scopeLabel() ? esc(scopeLabel()) + "：" : "") + v.empty) + "</b>" +
        (S.query ? "换个关键词试试" : v.emptySub) + "</div>";
    } else if (grouped()) {
      var html = "", last = null, counts = {};
      items.forEach(function (m) { var p = projectOf(m); counts[p] = (counts[p] || 0) + 1; });
      items.forEach(function (m) {
        var p = projectOf(m), other = m.project_kind === "other";
        if (p !== last) {
          html += '<div class="group-label' + (other ? " other" : "") + '" data-project="' + esc(p) + '" data-tab="' + esc(tabKey(m)) + '">' +
            '<span class="pdot" style="background:' + pcolor(other ? OTHER : p) + '"></span>' +
            '<button class="gname" title="' + (other ? "只看「其他」" : "只看 " + esc(p)) + '">' + esc(p) + "</button>" +
            '<span class="gcount">' + counts[p] + "</span>" + (other ? '<span class="gtag">未识别</span>' : "") +
            '<button class="gmerge" title="归到某个项目下">归到…</button></div>';
          last = p;
        }
        html += itemHtml(m);
      });
      list.innerHTML = html;
    } else {
      list.innerHTML = items.map(itemHtml).join("");
    }
    renderBulk();
  }

  function itemHtml(m) {
    var checked = S.multi.has(m.id);
    var cls = "item" + (m.unread ? " unread" : "") + (m.open ? " open" : "") +
      (m.id === S.current ? " selected" : "") + (checked ? " multi" : "");
    var hot = m.open || (m.priority === "high" && m.unread);
    var p = projectOf(m), sl = m.source.toLowerCase(), pl = p.toLowerCase();
    var src = sl === pl ? "" : sl.indexOf(pl + "/") === 0 ? m.source.slice(p.length + 1) : m.source;
    var st = "";
    if (m.open) st = '<span class="st open">' + (m.priority === "high" ? "紧急 · " : "") + "待决定</span> · ";
    else if (m.kind === "decision" && m.resolved) st = '<span class="st done">✓ 已解决</span> · ';
    else if (m.kind === "decision" && m.dismissed) st = '<span class="st skip">已跳过</span> · ';
    else if (m.kind === "decision" && m.answered) st = '<span class="st done">✓ ' + esc(m.choice || "已回复") + "</span> · ";
    else if (m.priority === "high" && m.unread) st = '<span class="st open">紧急</span> · ';
    if (!m.open && (S.view === "all" || S.view === "archive" || S.query) && m.kind !== "decision") st = '<span class="st kind">' + KIND[m.kind] + "</span> · " + st;
    var acts = '<span class="acts">' +
      '<button class="act" data-act="read" title="' + (m.unread ? "标为已读" : "标为未读") + '（U）">' + icon(m.unread ? "mailOpen" : "mail") + "</button>" +
      (m.open ? '<button class="act" data-act="resolve" title="标为已解决（R）">' + icon("check") + "</button>" : "") +
      '<button class="act" data-act="archive" title="' + (m.archived ? "移出归档" : "归档") + '（E）">' + icon(m.archived ? "unarchive" : "archive") + "</button>" +
      '<button class="act danger" data-act="delete" title="删除（Delete）">' + icon("trash") + "</button></span>";
    return '<div class="' + cls + '" data-id="' + esc(m.id) + '" role="option" aria-selected="' + (m.id === S.current) + '">' +
      '<button class="cb' + (checked ? " on" : "") + '" data-act="check" title="选择（X）" aria-label="选择"></button>' +
      (m.unread || m.open ? '<span class="dot' + (hot ? " hot" : "") + '"></span>' : "") +
      '<div class="row1"><span class="t">' + esc(m.title) + '</span><span class="time">' + fmtTime(m.ts) + "</span>" + acts + "</div>" +
      '<div class="row2">' + st + (src ? '<span class="src">' + esc(src) + "</span>" + (m.snippet ? " · " : "") : "") + esc(m.snippet || "") + "</div></div>";
  }

  function renderBulk() {
    var n = S.multi.size;
    $("bulkbar").hidden = n < 1;
    $("list").classList.toggle("multi-mode", n > 0);
    if (!n) return;
    var ids = Array.from(S.multi);
    var all = S.visible.length && S.visible.every(function (id) { return S.multi.has(id); });
    var ca = $("checkAll");
    ca.classList.toggle("on", !!all);
    ca.classList.toggle("some", !all);
    $("bulkCount").textContent = "已选 " + n + " 条";
    $("bulkResolve").hidden = !hasOpen(ids);
    var allArch = ids.every(function (id) { return S.byId[id] && S.byId[id].archived; });
    $("bulkArchive").innerHTML = icon(allArch ? "unarchive" : "archive");
    $("bulkArchive").title = allArch ? "移出归档" : "归档";
  }

  function renderFoot() {
    $("ver").textContent = "v" + (BOOT.version || "") + (BOOT.build ? " · build " + BOOT.build : " · 源码");
    var u = S.meta.update;
    var chip = $("updateChip");
    if (u && u.latest && u.latest > (BOOT.build || 0) && u.state !== "installing") {
      chip.hidden = false;
      chip.innerHTML = icon("refresh") + "<span>更新到 build " + u.latest + "</span>";
    } else if (u && u.state === "installing") {
      chip.hidden = false;
      chip.innerHTML = icon("refresh") + "<span>正在更新…</span>";
    } else chip.hidden = true;
  }

  // ---------------------------------------------------------------- 阅读区
  function renderReader() {
    var m = S.current && S.byId[S.current];
    $("app").classList.toggle("reading", !!m);
    if (!m) {
      $("empty").hidden = false;
      $("detail").hidden = true;
      S.shownKey = null;
      return;
    }
    $("empty").hidden = true;
    $("detail").hidden = false;
    var key = m.id + "|" + m.answered;
    if (S.shownKey === key) { renderEyebrow(m); return; }
    var cached = S.details[key];
    if (cached) return showDetail(cached, key);
    api("/api/message?id=" + encodeURIComponent(m.id)).then(function (d) {
      if (!d || d.error) return;
      S.details[key] = d;
      if (S.current === m.id) showDetail(d, key);
    });
  }

  function renderEyebrow(m) {
    var bits = [KIND[m.kind], '<span class="src"><span class="pdot" style="background:' + pcolor(projectOf(m)) + '"></span>' + esc(m.source) + "</span>", fmtTime(m.ts, true)];
    if (m.priority === "high") bits.push('<span class="hot">紧急</span>');
    if (m.archived) bits.push("已归档");
    $("eyebrow").innerHTML = bits.join(" · ") + (m.open ? '<button class="jump" id="jumpBtn">去选择 ↓</button>' : "");
  }

  function showDetail(d, key) {
    var newMsg = !S.shownKey || S.shownKey.split("|")[0] !== d.id;
    S.shownKey = key;
    renderEyebrow(S.byId[d.id] || d);
    $("title").textContent = d.title;
    $("question").hidden = !d.question;
    $("questionText").textContent = d.question || "";
    var body = $("body");
    if ((d.body || "").trim()) {
      body.innerHTML = MD.toHtml(d.body);
      MD.hydrate(body);
    } else {
      body.innerHTML = '<p class="no-body">（没有正文）</p>';
    }
    renderDecision(d, newMsg);
    if (newMsg) {
      $("scroller").scrollTop = 0;
      $("toolbar").classList.remove("scrolled");
    }
  }

  function renderDecision(d, reset) {
    var box = $("decide");
    if (d.kind !== "decision") { box.hidden = true; return; }
    box.hidden = false;
    var r = d.response;
    if (reset || r) S.choice = null;
    var opts = $("options");
    opts.innerHTML = (d.options || []).map(function (o, i) {
      var chosen = r && r.choice === o.label;
      return '<button class="opt' + (chosen ? " chosen" : "") + '" data-idx="' + i + '"' + (r ? " disabled" : "") + ">" +
        '<span class="num">' + (chosen ? icon("check") : i + 1) + "</span>" +
        '<span class="txt"><span class="lab">' + esc(o.label) +
        (d.recommended === i + 1 ? '<span class="rec">推荐</span>' : "") + "</span>" +
        (o.description ? '<span class="desc">' + esc(o.description) + "</span>" : "") + "</span></button>";
    }).join("");
    opts.hidden = !(d.options || []).length;
    var ta = $("replyText");
    ta.hidden = !!r || !d.allow_text;
    if (reset) ta.value = "";
    ta.placeholder = (d.options || []).length ? "补充说明（可选）" : "写下你的回复";
    $("decideFoot").hidden = !!r;
    $("decideTitle").textContent = r ? "你的回复" : (d.options || []).length ? "请选择一个选项" : "请写下你的回复";
    var done = $("doneBox");
    if (r) {
      var when = r.ts ? fmtTime(r.ts, true) : "";
      done.hidden = false;
      done.className = "reply-done" + (r.dismissed ? " skip" : "");
      if (r.resolved) done.innerHTML = "<b>已标为已解决</b> · " + when + "<div>没有选择选项，等待的会话已收到「已经处理好了」。</div>";
      else if (r.dismissed) done.innerHTML = "<b>已跳过</b> · " + when + "<div>没有作出选择，等待的会话已收到通知。</div>";
      else if (r.closed_by === "claude") done.innerHTML = "<b>已在对话中处理</b> · " + when + (r.text ? '<div class="reply-text">' + esc(r.text) + "</div>" : "");
      else done.innerHTML = "<b>已提交</b> · " + when + (r.choice ? "　选择：<b>" + esc(r.choice) + "</b>" : "") +
        (r.text ? '<div class="reply-text">' + esc(r.text) + "</div>" : "");
      $("decideState").textContent = "";
    } else {
      done.hidden = true;
      $("decideState").textContent = d.recommended ? "推荐第 " + d.recommended + " 项" : "";
    }
    updateSubmit();
  }

  function currentDetail() {
    var m = S.current && S.byId[S.current];
    return m ? S.details[m.id + "|" + m.answered] : null;
  }

  function pick(idx) {
    var d = currentDetail();
    if (!d || d.response || !d.options || !d.options[idx]) return;
    S.choice = d.options[idx].label;
    $("options").querySelectorAll(".opt").forEach(function (b) {
      b.classList.toggle("checked", +b.dataset.idx === idx);
    });
    updateSubmit();
  }
  function updateSubmit() {
    var d = currentDetail();
    var ok = d && !d.response && (S.choice != null || (d.allow_text && $("replyText").value.trim()));
    $("submitBtn").disabled = !ok;
  }
  function submit() {
    var d = currentDetail();
    if (!d || d.response || $("submitBtn").disabled) return;
    $("submitBtn").disabled = true;
    var text = d.allow_text ? $("replyText").value.trim() : "";
    act({ action: "reply", id: d.id, choice: S.choice, text: text }).then(function () {
      toast("已提交，会话会马上收到");
      return refreshNow();
    }).catch(function (e) {
      toast(e.message, { bad: true });
      updateSubmit();
    });
  }

  // ---------------------------------------------------------------- 选择 / 导航
  function select(id, opts) {
    opts = opts || {};
    S.current = id;
    if (!opts.keepMulti) S.multi.clear();
    S.anchor = id;
    var m = S.byId[id];
    if (m && m.unread && !opts.noRead) {
      m.unread = false; // 乐观更新
      act({ action: "read", ids: [id] }).catch(function () {});
    }
    renderList();
    renderReader();
    var el = document.querySelector('.item[data-id="' + cssEsc(id) + '"]');
    if (el) el.scrollIntoView({ block: "nearest" });
  }
  function cssEsc(s) { return window.CSS && CSS.escape ? CSS.escape(s) : s.replace(/"/g, '\\"'); }
  function move(delta) {
    var ids = S.visible;
    if (!ids.length) return;
    var i = ids.indexOf(S.current);
    var j = i < 0 ? 0 : Math.max(0, Math.min(ids.length - 1, i + delta));
    select(ids[j]);
  }
  function setView(v) {
    S.view = v;
    save("view", v);
    S.multi.clear();
    renderNav();
    renderList();
    if (S.current && S.byId[S.current] && !inView(S.byId[S.current], v)) { S.current = null; renderReader(); }
  }
  // 当前条目被移走（归档 / 删除）后，选中下一条
  function nextAfter(ids) {
    var vis = S.visible, gone = new Set(ids);
    var i = vis.indexOf(S.current);
    for (var k = i + 1; k < vis.length; k++) if (!gone.has(vis[k])) return vis[k];
    for (k = i - 1; k >= 0; k--) if (!gone.has(vis[k])) return vis[k];
    return null;
  }

  function targets() {
    if (S.multi.size) return Array.from(S.multi);
    return S.current ? [S.current] : [];
  }

  // ---------------------------------------------------------------- 操作
  function hasOpen(ids) { return ids.some(function (id) { return S.byId[id] && S.byId[id].open; }); }

  function doArchive(ids, on) {
    if (!ids.length) return;
    if (on == null) on = !ids.every(function (id) { return S.byId[id] && S.byId[id].archived; });
    var go = function () {
      var next = S.view !== "all" || on ? nextAfter(ids) : S.current;
      act({ action: "archive", ids: ids, on: on }).then(function () {
        S.multi.clear();
        if (ids.indexOf(S.current) >= 0 && (S.view !== "archive" ? on : !on)) S.current = next;
        return refreshNow();
      }).then(function () {
        toast((on ? "已归档 " : "已移出归档 ") + ids.length + " 条", on ? {
          undo: function () { act({ action: "archive", ids: ids, on: false }).then(refreshNow); },
        } : null);
      }).catch(function (e) { toast(e.message, { bad: true }); });
    };
    if (on && hasOpen(ids)) {
      confirmBox("归档还在等你决定的消息？", "等待中的会话会收到「用户跳过了这条决定」，然后继续往下走。", "归档并跳过").then(function (ok) { if (ok) go(); });
    } else go();
  }

  function doDelete(ids) {
    if (!ids.length) return;
    var text = "删除后不能恢复，会从收件箱文件里真正移除。" +
      (hasOpen(ids) ? "\n其中有还在等你决定的消息：等待中的会话会收到「用户跳过了这条决定」。" : "");
    confirmBox(ids.length > 1 ? "删除这 " + ids.length + " 条消息？" : "删除这条消息？", text, "删除", true).then(function (ok) {
      if (!ok) return;
      var next = nextAfter(ids);
      act({ action: "delete", ids: ids }).then(function () {
        S.multi.clear();
        if (ids.indexOf(S.current) >= 0) S.current = next;
        return refreshNow();
      }).then(function () { toast("已删除 " + ids.length + " 条"); })
        .catch(function (e) { toast(e.message, { bad: true }); });
    });
  }

  function doResolve(ids) {
    if (!ids.length) return;
    var open = ids.filter(function (id) { return S.byId[id] && S.byId[id].open; }).length;
    act({ action: "resolve", ids: ids }).then(function () {
      S.multi.clear();
      return refreshNow();
    }).then(function () {
      toast(open ? "已标为已解决 " + open + " 条，等待的会话已收到" : "已标为已读");
    }).catch(function (e) { toast(e.message, { bad: true }); });
  }

  function toggleCheck(id, range) {
    if (range && S.anchor && S.visible.indexOf(S.anchor) >= 0) {
      var ids = S.visible, a = ids.indexOf(S.anchor), b = ids.indexOf(id);
      ids.slice(Math.min(a, b), Math.max(a, b) + 1).forEach(function (x) { S.multi.add(x); });
    } else if (S.multi.has(id)) S.multi.delete(id);
    else S.multi.add(id);
    S.anchor = id;
    renderList();
  }

  function doToggleRead(ids) {
    if (!ids.length) return;
    var anyUnread = ids.some(function (id) { return S.byId[id] && S.byId[id].unread; });
    act({ action: "read", ids: ids, read: anyUnread }).then(function () {
      if (ids.length > 1) { S.multi.clear(); toast((anyUnread ? "已标为已读 " : "已标为未读 ") + ids.length + " 条"); }
      return refreshNow();
    });
  }

  // ---- 复制
  function markdownOf(d) {
    var out = "# " + d.title + "\n\n";
    if (d.question) out += d.question.trim().split("\n").map(function (l) { return "> " + l; }).join("\n") + "\n\n";
    out += (d.body || "").trim() + "\n";
    if (d.response && d.response.choice) out += "\n---\n\n**我的选择：** " + d.response.choice + (d.response.text ? "\n\n" + d.response.text : "") + "\n";
    return out;
  }
  function writeClipboard(text, html) {
    if (html && window.ClipboardItem && navigator.clipboard && navigator.clipboard.write) {
      return navigator.clipboard.write([new ClipboardItem({
        "text/plain": new Blob([text], { type: "text/plain" }),
        "text/html": new Blob([html], { type: "text/html" }),
      })]);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) return navigator.clipboard.writeText(text);
    return new Promise(function (ok, bad) { // 老办法兜底
      var ta = document.createElement("textarea");
      ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy") ? ok() : bad(new Error("复制失败")); } catch (e) { bad(e); }
      ta.remove();
    });
  }
  function copy(mode) {
    var d = currentDetail();
    if (!d) return;
    var p;
    if (mode === "text") p = writeClipboard(plainOf());
    else if (mode === "rich") p = writeClipboard(plainOf(), richOf());
    else p = writeClipboard(markdownOf(d));
    p.then(function () {
      toast(mode === "text" ? "已复制纯文本" : mode === "rich" ? "已复制（保留格式，可粘到 Word / 飞书 / Notion）" : "已复制 Markdown");
    }).catch(function (e) { toast("复制失败：" + e.message, { bad: true }); });
  }
  function plainOf() {
    var a = $("article").cloneNode(true);
    a.querySelectorAll(".code-copy, .katex-mathml").forEach(function (e) { e.remove(); });
    a.querySelectorAll(".math[data-tex]").forEach(function (e) { e.textContent = e.classList.contains("math-display") ? "$$" + e.dataset.tex + "$$" : "$" + e.dataset.tex + "$"; });
    return a.innerText.trim() + "\n";
  }
  function richOf() {
    var a = $("article").cloneNode(true);
    a.querySelectorAll(".code-copy, .code-head, .eyebrow").forEach(function (e) { e.remove(); });
    a.querySelectorAll(".math[data-tex]").forEach(function (e) { // 富文本里公式写成 TeX 源码，粘到哪里都不丢
      var c = document.createElement("code");
      c.textContent = e.dataset.tex;
      e.replaceWith(c);
    });
    return '<meta charset="utf-8">' + a.innerHTML;
  }

  // ---- PDF
  function preparePrint(d) {
    var root = $("printRoot");
    var a = $("article").cloneNode(true);
    a.removeAttribute("id");
    a.querySelectorAll("[id]").forEach(function (e) { e.removeAttribute("id"); });
    root.innerHTML = "";
    root.appendChild(a);
    if (d.response) {
      var f = document.createElement("div");
      f.className = "md";
      f.innerHTML = "<hr><p><strong>我的回复：</strong>" + esc(d.response.choice || "（文字回复）") + "</p>" +
        (d.response.text ? "<p>" + esc(d.response.text).replace(/\n/g, "<br>") + "</p>" : "");
      a.appendChild(f);
    }
    var foot = document.createElement("div");
    foot.className = "print-foot";
    foot.textContent = "ClaudeDesk · " + d.source + " · " + fmtTime(d.ts, true);
    a.appendChild(foot);
  }
  function pdf() {
    var d = currentDetail();
    if (!d) return;
    preparePrint(d);
    var name = (d.title || "ClaudeDesk").replace(/[\\/:*?"<>|\r\n]+/g, " ").trim().slice(0, 80) || "ClaudeDesk";
    var fallback = function () {
      var old = document.title;
      document.title = name;
      window.print();
      document.title = old;
    };
    if (!BOOT.app) return fallback();
    act({ action: "export_pdf", name: name }).then(function (res) {
      if (res && res.path) toast("已保存 PDF", { action: "打开", run: function () { act({ action: "open_path", path: res.path }); } });
      else if (res && res.fallback) fallback();
    }).catch(function (e) {
      toast("直接导出失败，改用打印对话框（选“另存为 PDF”）", { bad: true });
      console.warn(e);
      fallback();
    });
  }

  // ---------------------------------------------------------------- 搜索
  var searchTimer = null;
  function onSearch() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function () {
      S.query = $("search").value.trim();
      runSearch();
    }, 120);
  }
  function runSearch() {
    if (!S.query) { S.searchIds = null; renderAll(); return; }
    var q = S.query;
    api("/api/search?q=" + encodeURIComponent(q)).then(function (r) {
      if (q !== S.query) return;
      S.searchIds = new Set(r.ids || []);
      renderAll();
    });
  }

  // ---------------------------------------------------------------- 弹层 / 提示
  var popOwner = null;
  function openPopover(anchor, html, cls, onClick) {
    var p = $("popover");
    if (popOwner === anchor && !p.hidden) { closePopover(); return; }
    p.className = "popover" + (cls ? " " + cls : "");
    p.innerHTML = html;
    p.hidden = false;
    popOwner = anchor;
    var r = anchor.getBoundingClientRect();
    var w = p.offsetWidth, h = p.offsetHeight;
    var left = Math.min(Math.max(8, r.right - w), window.innerWidth - w - 8);
    if (r.left < window.innerWidth / 3) left = Math.min(r.left, window.innerWidth - w - 8);
    var top = r.bottom + 6;
    if (top + h > window.innerHeight - 8) top = Math.max(8, r.top - h - 6);
    p.style.left = left + "px";
    p.style.top = top + "px";
    p.onclick = function (e) { onClick && onClick(e); };
  }
  function closePopover() { $("popover").hidden = true; popOwner = null; }

  function toast(text, opts) {
    opts = opts || {};
    var t = document.createElement("div");
    t.className = "toast" + (opts.bad ? " bad" : "");
    t.innerHTML = "<span>" + esc(text) + "</span>";
    if (opts.undo || opts.run) {
      var b = document.createElement("button");
      b.textContent = opts.undo ? "撤销" : opts.action;
      b.onclick = function () { (opts.undo || opts.run)(); t.remove(); };
      t.appendChild(b);
    }
    $("toasts").appendChild(t);
    setTimeout(function () { t.remove(); }, opts.undo || opts.run ? 6000 : 2600);
  }

  var modalResolve = null;
  function confirmBox(title, text, okLabel, danger) {
    $("modalTitle").textContent = title;
    $("modalText").textContent = text;
    $("modalOk").textContent = okLabel || "确定";
    $("modalOk").className = "primary" + (danger ? " danger" : "");
    $("modal").hidden = false;
    setTimeout(function () { $("modalOk").focus(); }, 0);
    return new Promise(function (res) { modalResolve = res; });
  }
  function closeModal(v) { $("modal").hidden = true; if (modalResolve) modalResolve(v); modalResolve = null; }

  // ---- 设置
  function seg(key, opts) {
    return '<div class="seg">' + opts.map(function (o) {
      return '<button data-set="' + key + '" data-val="' + o[0] + '" class="' + (S.settings[key] === o[0] ? "on" : "") + '">' + o[1] + "</button>";
    }).join("") + "</div>";
  }
  function settingsHtml() {
    var sw = { ember: "#F2541B", indigo: "#5146F5", jade: "#0E9F7A", rose: "#E62F6B" };
    var h = '<div class="set-row"><div class="menu-label">外观</div>' +
      seg("theme", [["system", "跟随系统"], ["light", "浅色"], ["dark", "深色"]]) + "</div>" +
      '<div class="set-row"><div class="menu-label">强调色</div><div class="swatches">' +
      Object.keys(sw).map(function (k) {
        return '<button class="swatch' + (S.settings.accent === k ? " on" : "") + '" data-set="accent" data-val="' + k + '" style="background:' + sw[k] + '" title="' + k + '"></button>';
      }).join("") + "</div></div>" +
      '<div class="set-row"><div class="menu-label">正文字体</div>' + seg("font", [["sans", "无衬线 · 清晰"], ["serif", "衬线 · 书卷"]]) + "</div>" +
      '<div class="set-row"><div class="menu-label">字号</div>' + seg("size", [["s", "小"], ["m", "中"], ["l", "大"]]) + "</div>" +
      '<div class="set-row"><div class="menu-label">列表密度</div>' + seg("density", [["cozy", "舒展"], ["compact", "紧凑"]]) + "</div>";
    if (BOOT.app) {
      var m = S.meta;
      h += '<div class="menu-sep"></div>' +
        '<button class="toggle-row" data-app="autostart">开机自启<span class="switch' + (m.autostart ? " on" : "") + '"></span></button>' +
        '<button class="toggle-row" data-app="auto_update">自动更新<span class="switch' + (m.auto_update ? " on" : "") + '"></span></button>' +
        '<button class="menu-item" data-app="check_update">' + icon("refresh") + "检查更新<span class=\"sub\">" + (BOOT.build ? "build " + BOOT.build : "源码运行") + "</span></button>" +
        '<button class="menu-item" data-app="open_data">' + icon("folder") + "打开数据目录</button>";
    }
    var al = Object.keys(S.aliases || {});
    if (al.length) {
      h += '<div class="menu-sep"></div><div class="set-row"><div class="menu-label">项目归类（点 × 拆出来）</div></div>' + al.map(function (k) {
        return '<button class="menu-item" data-unalias="' + esc(k) + '">' + esc(k) + ' → ' + esc(S.aliases[k]) + '<span class="sub">×</span></button>';
      }).join("");
    }
    h += '<button class="menu-item" data-app="shortcuts">' + icon("keyboard") + "快捷键<span class=\"sub\">?</span></button>";
    return h;
  }
  function openSettings() {
    openPopover($("settingsBtn"), settingsHtml(), "settings", function (e) {
      var b = e.target.closest("button");
      if (!b) return;
      if (b.dataset.set) {
        var vals = {}; vals[b.dataset.set] = b.dataset.val;
        var s = Object.assign({}, S.settings, vals);
        applySettings(s);
        act({ action: "settings", values: vals }).catch(function () {});
        $("popover").innerHTML = settingsHtml();
        if (S.current) { S.shownKey = null; renderReader(); } // 字号变了，公式重排
        return;
      }
      if (b.dataset.unalias) {
        act({ action: "alias", from: b.dataset.unalias, to: "" }).then(function () { return refreshNow(); })
          .then(function () { $("popover").innerHTML = settingsHtml(); });
        return;
      }
      var a = b.dataset.app;
      if (a === "shortcuts") { closePopover(); return showShortcuts(); }
      if (a === "autostart" || a === "auto_update") {
        act({ action: a, on: !S.meta[a] }).then(function (r) {
          S.meta[a] = !!r;
          $("popover").innerHTML = settingsHtml();
        }).catch(function (e2) { toast(e2.message, { bad: true }); });
        return;
      }
      if (a === "check_update") {
        toast("正在检查更新…");
        act({ action: "check_update" }).then(function (r) { toast(r || "检查完成"); refreshNow(); })
          .catch(function (e2) { toast(e2.message, { bad: true }); });
        return;
      }
      if (a === "open_data") { act({ action: "open_data" }); closePopover(); }
    });
  }
  function showShortcuts() {
    var rows = [["↑ ↓ / J K", "上一条 / 下一条"], ["1 – 9", "选择第 N 个选项"], ["Ctrl + Enter", "提交回复"],
      ["E", "归档 / 移出归档"], ["Delete", "删除"], ["U", "标为已读 / 未读"], ["R", "标为已解决"], ["X", "勾选当前这条"], ["C", "复制 Markdown"],
      ["Ctrl + P", "导出 PDF"], ["/", "搜索"], ["[ ]", "切换项目（顶部标签）"], ["Ctrl + 点标签", "同时看几个项目"], ["点左边的方框 / Ctrl + 点击", "多选（Shift 连选）"], ["Ctrl + A", "全选当前列表"], ["Esc", "取消选择 / 关闭"]];
    $("modalTitle").textContent = "快捷键";
    $("modalText").innerHTML = '<span class="kbd-table">' + rows.map(function (r) {
      return "<span>" + r[0].split(" ").map(function (k) { return /^[+/–]$/.test(k) ? k : "<kbd>" + esc(k) + "</kbd>"; }).join(" ") + "</span><span>" + r[1] + "</span>";
    }).join("") + "</span>";
    $("modalOk").textContent = "好的";
    $("modalOk").className = "primary";
    $("modalCancel").hidden = true;
    $("modal").hidden = false;
    modalResolve = function () { $("modalCancel").hidden = false; };
  }

  // ---------------------------------------------------------------- 事件
  function bind() {
    paintIcons();
    $("projects").addEventListener("click", function (e) {
      var b = e.target.closest(".ptab");
      if (b) clickTab(b.dataset.project, e.ctrlKey || e.metaKey || e.shiftKey);
    });
    $("projects").addEventListener("contextmenu", function (e) {
      var b = e.target.closest(".ptab");
      if (!b || !b.dataset.project || b.dataset.project === OTHER) return;
      e.preventDefault();
      mergeMenu(e.clientX, e.clientY, b.dataset.project);
    });
    $("nav").addEventListener("click", function (e) {
      var b = e.target.closest(".tab");
      if (b) setView(b.dataset.view);
    });
    $("list").addEventListener("click", function (e) {
      var gl = e.target.closest(".group-label");
      if (gl) {
        if (e.target.closest(".gmerge")) {
          var r = e.target.closest(".gmerge").getBoundingClientRect();
          return mergeMenu(r.left, r.bottom, gl.dataset.project);
        }
        return clickTab(gl.dataset.tab, false);
      }
      var it = e.target.closest(".item");
      if (!it) return;
      var id = it.dataset.id;
      var a = e.target.closest("[data-act]");
      if (a) {
        e.stopPropagation();
        var what = a.dataset.act;
        if (what === "check") return toggleCheck(id, e.shiftKey);
        var one = [id];
        if (what === "read") doToggleRead(one);
        if (what === "resolve") doResolve(one);
        if (what === "archive") doArchive(one);
        if (what === "delete") doDelete(one);
        return;
      }
      if (e.ctrlKey || e.metaKey) return toggleCheck(id, false);
      if (e.shiftKey && (S.anchor || S.current)) {
        var ids = S.visible, a = ids.indexOf(S.anchor || S.current), b = ids.indexOf(id);
        if (a >= 0 && b >= 0) {
          S.multi = new Set(ids.slice(Math.min(a, b), Math.max(a, b) + 1));
          renderList();
          return;
        }
      }
      select(id);
    });
    $("list").addEventListener("contextmenu", function (e) {
      var gl = e.target.closest(".group-label");
      if (gl) { e.preventDefault(); return mergeMenu(e.clientX, e.clientY, gl.dataset.project); }
      var it = e.target.closest(".item");
      if (!it) return;
      e.preventDefault();
      var id = it.dataset.id;
      if (!S.multi.has(id)) select(id, { noRead: true });
      var ids = targets(), m = S.byId[id];
      var html = '<button class="menu-item" data-m="read">' + icon(m.unread ? "mailOpen" : "mail") + (m.unread ? "标为已读" : "标为未读") + '<span class="sub">U</span></button>' +
        (hasOpen(ids) ? '<button class="menu-item" data-m="resolve">' + icon("check") + '标为已解决<span class="sub">R</span></button>' : "") +
        '<button class="menu-item" data-m="archive">' + icon(m.archived ? "unarchive" : "archive") + (m.archived ? "移出归档" : "归档") + '<span class="sub">E</span></button>' +
        '<div class="menu-sep"></div><button class="menu-item danger" data-m="delete">' + icon("trash") + "删除" + (ids.length > 1 ? " " + ids.length + " 条" : "") + '<span class="sub">Del</span></button>';
      var fake = { getBoundingClientRect: function () { return { left: e.clientX, right: e.clientX + 1, top: e.clientY, bottom: e.clientY }; } };
      openPopover(fake, html, "", function (ev) {
        var b = ev.target.closest("[data-m]");
        if (!b) return;
        closePopover();
        if (b.dataset.m === "read") doToggleRead(ids);
        if (b.dataset.m === "resolve") doResolve(ids);
        if (b.dataset.m === "archive") doArchive(ids);
        if (b.dataset.m === "delete") doDelete(ids);
      });
    });
    $("bulkbar").addEventListener("click", function (e) {
      var b = e.target.closest("[data-bulk]");
      if (!b) return;
      var ids = Array.from(S.multi);
      if (b.dataset.bulk === "all") {
        if (S.visible.every(function (id) { return S.multi.has(id); })) S.multi.clear(); else selectAll();
        renderList();
      }
      if (b.dataset.bulk === "clear") { S.multi.clear(); renderList(); }
      if (b.dataset.bulk === "read") act({ action: "read", ids: ids }).then(function () {
        S.multi.clear(); toast("已标为已读 " + ids.length + " 条"); return refreshNow();
      });
      if (b.dataset.bulk === "resolve") doResolve(ids);
      if (b.dataset.bulk === "archive") doArchive(ids);
      if (b.dataset.bulk === "delete") doDelete(ids);
    });
    $("listMenuBtn").addEventListener("click", function () {
      var scope = scopeLabel() ? "（" + esc(scopeLabel()) + "）" : "";
      var html = '<button class="menu-item" data-l="read_all">' + icon("checks") + "全部标为已读" + scope + "</button>" +
        '<button class="menu-item" data-l="archive_handled">' + icon("archive") + "归档所有已处理的" + scope + "<span class=\"sub\">已读且不用决定</span></button>" +
        '<button class="menu-item" data-l="select_all">' + icon("check") + "全选当前列表<span class=\"sub\">Ctrl+A</span></button>";
      openPopover($("listMenuBtn"), html, "", function (e) {
        var b = e.target.closest("[data-l]");
        if (!b) return;
        closePopover();
        if (b.dataset.l === "select_all") return selectAll();
        var mine = S.msgs.filter(function (m) { return !m.archived && inScope(m); });
        var req = b.dataset.l === "read_all"
          ? { action: "read", ids: mine.filter(function (m) { return m.unread; }).map(function (m) { return m.id; }) }
          : { action: "archive", ids: mine.filter(function (m) { return !m.unread && !m.open; }).map(function (m) { return m.id; }) };
        act(req).then(function (n) {
          toast(b.dataset.l === "read_all" ? "已全部标为已读" : n ? "已归档 " + n + " 条" : "没有可以归档的");
          refreshNow();
        });
      });
    });
    $("search").addEventListener("input", onSearch);
    $("search").addEventListener("keydown", function (e) {
      if (e.key === "Escape") { $("search").value = ""; onSearch(); $("search").blur(); }
      if (e.key === "ArrowDown" || e.key === "Enter") { e.preventDefault(); $("search").blur(); if (!S.current) move(0); }
    });
    $("options").addEventListener("click", function (e) {
      var b = e.target.closest(".opt");
      if (b && !b.disabled) pick(+b.dataset.idx);
    });
    $("replyText").addEventListener("input", updateSubmit);
    $("replyText").addEventListener("keydown", function (e) {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); submit(); }
    });
    $("submitBtn").addEventListener("click", submit);
    $("resolveBtn").addEventListener("click", function () { var d = currentDetail(); if (d) doResolve([d.id]); });
    $("copyBtn").addEventListener("click", function () { copy("md"); });
    $("copyMenuBtn").addEventListener("click", function () {
      var html = '<button class="menu-item" data-c="md">' + icon("copy") + "复制 Markdown<span class=\"sub\">C</span></button>" +
        '<button class="menu-item" data-c="rich">' + icon("rich") + "复制为富文本<span class=\"sub\">保留格式</span></button>" +
        '<button class="menu-item" data-c="text">' + icon("text") + "复制纯文本</button>";
      openPopover($("copyMenuBtn"), html, "", function (e) {
        var b = e.target.closest("[data-c]");
        if (b) { closePopover(); copy(b.dataset.c); }
      });
    });
    $("pdfBtn").addEventListener("click", pdf);
    $("backBtn").addEventListener("click", function () { S.current = null; renderList(); renderReader(); });
    $("settingsBtn").addEventListener("click", openSettings);
    $("updateChip").addEventListener("click", function () {
      act({ action: "install_update" }).then(function (r) { toast(r || "正在更新…"); refreshNow(); })
        .catch(function (e) { toast(e.message, { bad: true }); });
    });
    $("modalOk").addEventListener("click", function () { closeModal(true); });
    $("modalCancel").addEventListener("click", function () { closeModal(false); });
    $("modal").addEventListener("click", function (e) { if (e.target === $("modal")) closeModal(false); });
    $("eyebrow").addEventListener("click", function (e) {
      if (e.target.closest("#jumpBtn")) $("decide").scrollIntoView({ behavior: "smooth", block: "start" });
    });
    $("scroller").addEventListener("scroll", function () {
      $("toolbar").classList.toggle("scrolled", $("scroller").scrollTop > 4);
    });
    $("body").addEventListener("click", function (e) {
      var b = e.target.closest(".code-copy");
      if (!b) return;
      var code = b.closest(".codeblock").querySelector("code").innerText;
      writeClipboard(code).then(function () {
        b.textContent = "已复制"; b.classList.add("ok");
        setTimeout(function () { b.textContent = "复制"; b.classList.remove("ok"); }, 1400);
      });
    });
    document.addEventListener("mousedown", function (e) {
      var p = $("popover");
      if (!p.hidden && !p.contains(e.target) && !(popOwner && popOwner.contains && popOwner.contains(e.target))) closePopover();
    });
    window.addEventListener("resize", closePopover);
    document.addEventListener("keydown", onKey);
    window.addEventListener("beforeprint", function () { var d = currentDetail(); if (d && !$("printRoot").firstChild) preparePrint(d); });
    window.addEventListener("afterprint", function () { $("printRoot").innerHTML = ""; });
  }

  function selectAll() {
    S.multi = new Set(S.visible);
    renderList();
  }

  function onKey(e) {
    if (!$("modal").hidden) {
      if (e.key === "Escape") closeModal(false);
      if (e.key === "Enter") { e.preventDefault(); closeModal(true); }
      return;
    }
    var typing = /^(INPUT|TEXTAREA)$/.test(document.activeElement && document.activeElement.tagName);
    var k = e.key;
    if ((e.ctrlKey || e.metaKey) && k.toLowerCase() === "p") { e.preventDefault(); pdf(); return; }
    if ((e.ctrlKey || e.metaKey) && k.toLowerCase() === "f") { e.preventDefault(); $("search").focus(); $("search").select(); return; }
    if (typing) return;
    if ((e.ctrlKey || e.metaKey) && k.toLowerCase() === "a") { e.preventDefault(); selectAll(); return; }
    if ((e.ctrlKey || e.metaKey) && k.toLowerCase() === "c") {
      if (!String(window.getSelection())) { e.preventDefault(); copy("md"); }
      return;
    }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (k === "Escape") {
      closePopover();
      if (S.multi.size) { S.multi.clear(); renderList(); }
      return;
    }
    if (k === "ArrowDown" || k === "j") { e.preventDefault(); move(1); return; }
    if (k === "ArrowUp" || k === "k") { e.preventDefault(); move(-1); return; }
    if (k === "/") { e.preventDefault(); $("search").focus(); return; }
    if (k === "[" || k === "]") {
      var names = [""].concat(projectList().map(function (p) { return p.key; }));
      if (names.length > 2) {
        var cur = S.projects.size === 1 ? S.projects.values().next().value : "";
        var i = Math.max(0, names.indexOf(cur));
        S.projects = new Set();
        var nk = names[(i + (k === "]" ? 1 : names.length - 1)) % names.length];
        if (nk) S.projects.add(nk);
        applyProjects();
      }
      return;
    }
    if (k === "?") { showShortcuts(); return; }
    if (k === "e" || k === "E") { doArchive(targets()); return; }
    if (k === "Delete" || k === "#") { doDelete(targets()); return; }
    if (k === "u" || k === "U") { doToggleRead(targets()); return; }
    if (k === "r" || k === "R") { doResolve(targets()); return; }
    if ((k === "x" || k === "X") && S.current) { toggleCheck(S.current, e.shiftKey); return; }
    if (k === "c" || k === "C") { copy("md"); return; }
    if (/^[1-9]$/.test(k)) { pick(+k - 1); return; }
    if (k === "Enter") {
      var d = currentDetail();
      if (d && d.kind === "decision" && !d.response && d.allow_text) { e.preventDefault(); $("replyText").focus(); }
    }
  }

  // ---------------------------------------------------------------- 启动
  if (!VIEWS.some(function (v) { return v.id === S.view; })) S.view = "decide";
  bind();
  renderNav();
  renderFoot();
  poll();
  // 外部（托盘 / 通知点击）要求打开某条消息
  window.deskOpen = function (id, view) {
    var go = function () {
      if (!S.byId[id]) return false;
      var m = S.byId[id];
      if (!inScope(m)) { S.projects = new Set([tabKey(m)]); applyProjects(); }
      if (!inView(m, S.view)) setView(view || (m.archived ? "archive" : m.kind === "decision" ? "decide" : m.kind === "answer" ? "answer" : "all"));
      if (S.query) { $("search").value = ""; S.query = ""; S.searchIds = null; renderAll(); }
      select(id);
      return true;
    };
    if (!go()) refreshNow().then(go);
  };
  window.deskTest = { setProject: setProject, S: S, select: select, setView: setView, pick: pick, submit: submit, copy: copy, markdownOf: markdownOf };
})();
