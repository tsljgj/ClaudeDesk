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
    eyeOff: '<path d="M10.7 5.1A10.7 10.7 0 0 1 21.9 11.7a1 1 0 0 1 0 .7 10.7 10.7 0 0 1-1.4 2.5"/><path d="M14.1 14.2a3 3 0 0 1-4.2-4.2"/><path d="M17.5 17.5a10.8 10.8 0 0 1-15.4-5.2 1 1 0 0 1 0-.7 10.8 10.8 0 0 1 4.4-5.1"/><path d="m2 2 20 20"/>',
    filter: '<path d="M3 6h18"/><path d="M7 12h10"/><path d="M10 18h4"/>',
    archiveDone: '<rect width="20" height="5" x="2" y="3" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"/><path d="m9 14.5 2 2 4-4"/>',
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
    { id: "all", label: "全部", empty: "收件箱是空的", emptySub: "一切都处理完了" },
    { id: "decide", label: "决定", empty: "没有待决定的事", emptySub: "会话需要你拍板时，会出现在这里" },
    { id: "answer", label: "回答", empty: "还没有回答", emptySub: "你问 Claude 的问题，完整答案收在这里" },
    { id: "archive", label: "归档", empty: "归档是空的", emptySub: "按 E 把处理完的消息收起来" },
  ];
  var KIND = { decision: "决定", answer: "回答", info: "通知" };

  var S = {
    version: -1, msgs: [], byId: {}, counts: {}, settings: BOOT.settings || {}, meta: {},
    view: "all", projects: loadSet("projects"), query: "", searchIds: null,
    current: null, multi: new Set(), anchor: null, choice: null,
    details: {}, shownKey: null, visible: [],
    drafts: {}, choiceIdx: null, submitting: {}, fresh: {}, // 每条的草稿（选项序号 + 文字）/ 正在提交的 id / 新到的高亮到期时间
    gone: {}, // 在这里删掉的 id：删除还在路上时到的旧快照里还有它们，不能让它们当成"新消息"闪回来
    all: [], allById: {}, hidden: new Set(), // 全部消息（含关掉的标签里的）/ 关掉的标签键（服务端存）。msgs / byId 只有没关掉的
    cursor: null, jump: null, // 窄窗口列表页的光标（↑↓ 只挪它）/ 新到提示里那条：{ id, el }，提示还在时 N 先打开它
    todo: load("todo", "") === "1", keep: null, // 只看未处理（记在本机）/ 正在看的那条：读完了也先留在列表里，换到别的才走
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
  function refreshNow(force) { // 自己做了操作：不等长轮询，立刻拿一次。force：版本没变也重画（长轮询可能已经先到了）
    return api("/api/state?since=-1").then(function (st) { apply(st, force === true); }).catch(function () {});
  }

  function apply(st, force) {
    if (st.version < S.version) return; // 晚到的旧快照（操作后的 refreshNow 被更新的长轮询抢先了）：不能把界面倒回去
    if (!force && st.version === S.version && S.all.length) return;
    var old = S.allById, first = S.version < 0; // 和全部消息比：找回的标签里的旧消息不算新到
    S.version = st.version;
    S.all = (st.messages || []).filter(function (m) { return !S.gone[m.id]; });
    S.allById = {};
    S.all.forEach(function (m) { S.allById[m.id] = m; });
    S.hidden = new Set(st.hidden_projects || []);
    filterClosed();
    S.counts = st.counts || {};
    S.meta = st.meta || {};
    S.aliases = st.aliases || {};
    if (st.settings) applySettings(st.settings);
    S.multi.forEach(function (id) { if (!S.byId[id]) S.multi.delete(id); });
    if (S.current && !S.byId[S.current]) S.current = null;
    // 缓存瘦身：删掉的消息不留详情；已经有回复的不留草稿
    Object.keys(S.details).forEach(function (k) { if (!S.allById[k.split("|")[0]]) delete S.details[k]; }); // 关掉的标签里的留着：找回来还在
    Object.keys(S.drafts).forEach(function (id) { if (!S.allById[id] || S.allById[id].answered) delete S.drafts[id]; });
    var arr = first ? null : arrivals(old);
    if (S.query) runSearch(); else renderAll();
    if (!arr) return;
    var hot = arr.hot, L = $("list").getBoundingClientRect(), covered = narrow() && S.current; // 窄窗口在看一条：阅读页盖住了列表
    arr.lit.forEach(function (id) { // 在这个视图里、但滚出了屏幕（或被盖住）：也算没看见
      var m = S.byId[id], el = rowEl(id), r = el && el.getBoundingClientRect();
      if (m && (m.open || m.priority === "high") && (!r || covered || r.top < L.top || r.bottom > L.bottom)) hot.push(m);
    });
    if (!hot.length) return;
    hot.sort(function (a, b) { return (b.open - a.open) || ((b.priority === "high") - (a.priority === "high")) || new Date(a.ts) - new Date(b.ts); });
    var h = hot[0];
    var t = toast(hot.length === 1 ? (h.open ? projectOf(h) + " 需要你决定：" + h.title : "紧急：" + h.title) : hot.length + " 条新的待决定",
                  { action: "查看（N）", run: function () { window.deskOpen(h.id); } });
    S.jump = { id: h.id, el: t }; // 提示还在时按 N：先打开它（跨项目）
  }

  // 新到的消息：看得见的那几行高亮 1.6 秒（lit）；看不见的（别的标签 / 视图、被搜索筛掉）里有待决定或紧急的（hot），交给 apply 弹提示
  function arrivals(old) {
    var hot = [], until = Date.now() + 1600, lit = [];
    S.msgs.forEach(function (m) {
      if (old[m.id]) return;
      if (inView(m, S.view) && inScope(m) && (!S.searchIds || S.searchIds.has(m.id))) { S.fresh[m.id] = until; lit.push(m.id); }
      else if (m.open || m.priority === "high") hot.push(m);
    });
    if (lit.length) setTimeout(function () {
      lit.forEach(function (id) {
        if (S.fresh[id] !== until) return;
        delete S.fresh[id];
        var el = rowEl(id);
        if (el) el.classList.remove("fresh");
      });
    }, 1650);
    return { hot: hot, lit: lit };
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
  // 未处理 = 还在等你决定的，或者还没读过的（归档的不算）。"只看未处理"在归档视图里不起作用
  function needsYou(m) { return !m.archived && (m.open || m.unread); }
  function todoOn() { return S.todo && S.view !== "archive"; }
  // ---- 项目（仓库）。项目名由服务端给：desk.py 发消息时识别出的 git 仓库；旧消息按来源对到已知仓库，
  // 对不上的归"其他"（project_kind = other），可以右键"归到项目"。
  var OTHER = "__other__";
  // 项目颜色：避开橙 / 红（界面里橙色表示"要你处理"）
  var PCOLORS = ["#1C7ED6", "#2F9E44", "#9C36B5", "#0C8599", "#C2255C", "#5F3DC4", "#66A80F", "#495057"];
  var pcolorMap = (function () { try { return JSON.parse(load("pcolors", "{}")) || {}; } catch (e) { return {}; } })();
  function projectOf(m) { return m.project || "unknown"; }
  function tabKey(m) { return m.project_kind === "other" ? OTHER : projectOf(m); }
  function pcolor(name) {
    if (name === OTHER) return "var(--ink-5)";
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
  var plMemo = null; // renderAll 期间只算一次（标签、分组顺序都要用）
  function projectList() {
    if (plMemo) return plMemo;
    var map = {};
    S.msgs.forEach(function (m) {
      var k = tabKey(m);
      var e = map[k] || (map[k] = { key: k, name: k === OTHER ? "未归类" : k, open: 0, unread: 0, last: "", total: 0 });
      if (m.ts > e.last) e.last = m.ts;
      if (m.archived) return;
      e.total++;
      if (m.open) e.open++;
      if (m.unread) e.unread++;
    });
    return Object.keys(map).map(function (k) { return map[k]; }).filter(function (p) { return p.key !== OTHER || p.total; }) // "未归类"只剩归档的：不要标签（归档视图里照样分组显示）
      .sort(function (a, b) { return (a.key === OTHER) - (b.key === OTHER) || byName(a.name, b.name); });
  }
  function byName(a, b) { return a.localeCompare(b, "zh-CN", { sensitivity: "base", numeric: true }); }
  function groupOrder() { // 分组顺序和标签一样按名字，"未归类"里的各来源排在最后；不随消息进出而跳动
    var order = {}, n = 0, others = {};
    projectList().forEach(function (p) { if (p.key !== OTHER) order[p.key] = n++; });
    S.msgs.forEach(function (m) { if (m.project_kind === "other") others[projectOf(m)] = 1; });
    Object.keys(others).sort(byName).forEach(function (k) { if (!(k in order)) order[k] = n++; });
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
    if (todoOn()) items = items.filter(function (m) { return needsYou(m) || m.id === S.keep; }); // 正在看的那条读完了也先留着
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

  // 点标签：只看这个（再点一次不变）；点"全部项目"回到全部。Ctrl / Shift + 点 = 加选 / 减选
  function clickTab(key, multi) {
    if (!key) S.projects = new Set();
    else if (multi) { if (S.projects.has(key)) S.projects.delete(key); else S.projects.add(key); }
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
    if (S.projects.size === 1) { var k = S.projects.values().next().value; return k === OTHER ? "未归类" : k; }
    return S.projects.size + " 个项目";
  }

  // ---- 关掉的标签：它的消息不进 msgs / byId（列表、计数、搜索、队列、N 键、[ ] 都只看这两个），服务端也不计数；
  // 这个项目来新消息时服务端把标签放回来。标签条右头"已关闭 N"、设置里都能找回
  function closedOf(m) { return S.hidden.has(tabKey(m)); }
  function tabName(k) { return k === OTHER ? "未归类" : k; }
  function filterClosed() {
    S.msgs = S.all.filter(function (m) { return !S.gone[m.id] && !closedOf(m); });
    S.byId = {};
    S.msgs.forEach(function (m) { S.byId[m.id] = m; });
    var n = S.projects.size;
    S.projects.forEach(function (k) { if (S.hidden.has(k)) S.projects.delete(k); }); // 选着的标签关掉了：从选择里拿掉
    if (S.projects.size !== n) save("projects", JSON.stringify(Array.from(S.projects)));
  }
  function closedList() { // 关着、还有消息的标签：[{ key, name, live 没归档的, total, open }]，和标签一样按名字排
    var map = {};
    S.all.forEach(function (m) {
      if (S.gone[m.id] || !closedOf(m)) return;
      var k = tabKey(m), e = map[k] || (map[k] = { key: k, name: tabName(k), live: 0, total: 0, open: 0 });
      e.total++;
      if (!m.archived) e.live++;
      if (m.open) e.open++;
    });
    return Object.keys(map).map(function (k) { return map[k]; }).sort(function (a, b) { return (a.key === OTHER) - (b.key === OTHER) || byName(a.name, b.name); });
  }
  // 关掉一个标签：先在本地关好、重画，再发请求；还有待决定的先确认。可以撤销（Z）
  function closeTab(key) {
    if (!key) return;
    var name = tabName(key), open = S.msgs.filter(function (m) { return m.open && tabKey(m) === key; }).length;
    var go = function () {
      var was = S.projects.has(key);
      dropUndo();
      S.hidden.add(key);
      filterClosed();
      S.multi.forEach(function (id) { if (!S.byId[id]) S.multi.delete(id); });
      if (S.current && !S.byId[S.current]) S.current = null;
      renderAll();
      refocusList();
      act({ action: "hide_project", key: key }).then(function () { return refreshNow(true); }).then(function () {
        toast("已关闭「" + name + "」", { undo: function () {
          reopenTabs([key]);
          if (was) S.projects.add(key); // 关之前选着它：撤销后还选着
          applyProjects();
        } });
      }).catch(function (e) { toast(e.message, { bad: true }); refreshNow(true); });
    };
    if (open) confirmBox("关闭「" + name + "」？", "「" + name + "」还有 " + open + " 条待决定没回复。关掉后它们不再显示、也不计入未读；这个项目来新消息时标签会自动回来。", "关闭").then(function (ok) { if (ok) go(); });
    else go();
  }
  // 找回关掉的标签（keys 为 null：全部）。先在本地放回来；选不选它、什么时候重画由调用的人定
  function reopenTabs(keys) {
    (keys || Array.from(S.hidden)).forEach(function (k) { S.hidden.delete(k); });
    filterClosed();
    var reqs = keys ? keys.map(function (k) { return act({ action: "show_project", key: k }); }) : [act({ action: "show_project", all: true })];
    return Promise.all(reqs).then(function () { return refreshNow(true); }).catch(function (e) { toast(e.message, { bad: true }); refreshNow(true); });
  }
  function closedSub(p) { return (p.live ? p.live + " 条" : p.total + " 条已归档") + (p.open ? " · " + p.open + " 待决定" : ""); }
  function renderClosed() { // 标签条右头"已关闭 N"：有关掉的标签才出现
    var b = $("closedBtn"), n = closedList().length;
    b.hidden = !n;
    if (!n || b.dataset.n === String(n)) return;
    b.dataset.n = n;
    b.innerHTML = icon("eyeOff") + '<span class="lbl">已关闭</span><span>' + n + "</span>";
    b.title = "已关闭 " + n + " 个标签：它们的消息不显示、不计数。点开找回";
    b.setAttribute("aria-label", b.title);
  }
  function openClosedMenu() {
    var cs = closedList();
    var html = '<div class="menu-label">已关闭的标签 · 点一个找回</div>' + cs.map(function (p) {
      return '<button class="menu-item" data-reopen="' + esc(p.key) + '"><span class="pdot" style="background:' + pcolor(p.key) + '"></span>' +
        '<span class="mname">' + esc(p.name) + '</span><span class="sub">' + closedSub(p) + "</span></button>";
    }).join("") + (cs.length > 1 ? '<div class="menu-sep"></div><button class="menu-item" data-reopen-all>' + icon("refresh") + "全部恢复</button>" : "");
    openPopover($("closedBtn"), html, "", function (e) {
      var b = e.target.closest("[data-reopen],[data-reopen-all]");
      if (!b) return;
      closePopover();
      var k = b.dataset.reopen;
      reopenTabs(k ? [k] : null);
      if (k) S.projects = new Set([k]); // 找回的那个：选中它
      applyProjects();
      $("list").focus();
    });
  }

  function dayKey(d) { return d.getFullYear() + "-" + d.getMonth() + "-" + d.getDate(); }
  function fmtTime(ts, full) {
    var d = new Date(ts), now = new Date();
    var hm = pad(d.getHours()) + ":" + pad(d.getMinutes());
    if (full) return d.getFullYear() + "年" + (d.getMonth() + 1) + "月" + d.getDate() + "日 " + hm;
    if (dayKey(d) === dayKey(now)) return hm;
    var yest = new Date(now); yest.setDate(now.getDate() - 1);
    if (dayKey(d) === dayKey(yest)) return "昨天 " + hm; // 刚过午夜时，11 分钟前的也是"昨天"：带上时间
    if (d.getFullYear() === now.getFullYear()) return (d.getMonth() + 1) + "月" + d.getDate() + "日";
    return d.getFullYear() + "/" + (d.getMonth() + 1) + "/" + d.getDate();
  }
  function pad(n) { return n < 10 ? "0" + n : "" + n; }
  // 等了多久：短的给列表时间格（"等 25 分"），长的放句子里（"25 分钟"）
  function waitMin(ts) { return Math.max(0, Math.floor((Date.now() - new Date(ts)) / 60000)); }
  function fmtWait(ts, short) {
    var n = waitMin(ts);
    if (n < 60) return Math.max(1, n) + (short ? " 分" : " 分钟");
    return n < 1440 ? Math.floor(n / 60) + " 小时" : Math.floor(n / 1440) + " 天";
  }
  function fmtRel(ts) { // 阅读区顶上的日期："今天 22:59 · 25 分钟前" / "昨天 18:02" / "10月3日 18:02"
    var d = new Date(ts), now = new Date(), hm = pad(d.getHours()) + ":" + pad(d.getMinutes()), n = waitMin(ts);
    var yest = new Date(now); yest.setDate(now.getDate() - 1);
    if (dayKey(d) === dayKey(now)) return "今天 " + hm + " · " + (n < 1 ? "刚刚" : n < 60 ? n + " 分钟前" : Math.floor(n / 60) + " 小时前");
    if (dayKey(d) === dayKey(yest)) return "昨天 " + hm;
    return (d.getFullYear() === now.getFullYear() ? "" : d.getFullYear() + "年") + (d.getMonth() + 1) + "月" + d.getDate() + "日 " + hm;
  }
  function timeCell(m) { // 待决定的那行显示等了多久（≥ 30 分钟变强调色），别的显示时间；悬停看完整日期
    if (!m.open) return '<span class="time">' + fmtTime(m.ts) + "</span>";
    return '<span class="time wait' + (waitMin(m.ts) >= 30 ? " long" : "") + '" data-ts="' + esc(m.ts) + '" title="' + fmtTime(m.ts, true) + '">等 ' + fmtWait(m.ts, true) + "</span>";
  }

  // ---- 待你决定的队列（当前项目范围内）：紧急的在前，再按等得最久的在前。列表本身不重排
  function queue() {
    return S.msgs.filter(function (m) { return m.open && !m.archived && inScope(m); }).sort(function (a, b) {
      return (b.priority === "high") - (a.priority === "high") || new Date(a.ts) - new Date(b.ts);
    });
  }
  function queueText(q) {
    var urgent = q.filter(function (m) { return m.priority === "high"; }).length;
    var oldest = q.reduce(function (a, m) { return new Date(m.ts) < new Date(a.ts) ? m : a; });
    return q.length + " 条待决定" + (urgent ? " · " + urgent + " 条紧急" : "") + " · 最久已等 " + fmtWait(oldest.ts);
  }
  function renderQueue() { // 只在有待决定时出现（全部 / 决定视图）；没有就收起，把地方让给列表
    var b = $("queueBtn"), q = queue();
    b.hidden = !q.length || (S.view !== "all" && S.view !== "decide");
    if (!q.length) return;
    b.title = "跳到下一条待决定（N / Shift+N 上一条）：紧急的在前，再按等得久的";
    b.innerHTML = "<span>" + queueText(q) + "</span><kbd>N</kbd>";
  }
  function renderEmpty() { // 阅读区什么都没打开时：不重复队列条，写出 N 会打开的那条
    var q = queue(), m = q[0], unread = q.length ? 0 : scopeCounts().unread;
    keepFocus($("empty"), function () {
      $("empty").innerHTML = '<div class="empty-box">' + (q.length
        ? '<p class="empty-lead">' + esc(m.title) + '</p><p class="empty-sub">' + esc(projectOf(m)) + (m.priority === "high" ? " · 紧急" : "") +
          " · 已等 " + fmtWait(m.ts) + (q.length > 1 ? " · 后面还有 " + (q.length - 1) + " 条" : "") + '</p><button class="primary" id="startBtn">开始处理（N）</button>'
        : unread ? '<p class="empty-lead">没有待决定的事</p><p class="empty-sub">还有 ' + unread + " 条未读 · <kbd>↓</kbd> 开始看</p>"
        : '<p class="empty-lead">都处理完了</p><p class="empty-sub"><kbd>↑</kbd> <kbd>↓</kbd> 切换　<kbd>?</kbd> 快捷键</p>') + "</div>";
    });
  }
  function nextDecision(dir) { // N / Shift+N：下一条 / 上一条待决定，到头绕回来
    if (dir > 0 && S.jump && document.contains(S.jump.el)) { // 新到提示还在：先打开它说的那条（跨项目）
      var j = S.byId[S.jump.id]; S.jump.el.remove(); S.jump = null;
      if (j && j.id !== S.current && (j.open || j.unread)) { window.deskOpen(j.id); return; }
    }
    var q = queue();
    if (!q.length) { toast("没有待决定的事"); return; }
    var i = q.map(function (m) { return m.id; }).indexOf(S.current);
    var m = q[i < 0 ? (dir > 0 ? 0 : q.length - 1) : (i + dir + q.length) % q.length];
    if (S.query && !(S.searchIds && S.searchIds.has(m.id))) { $("search").value = ""; S.query = ""; S.searchIds = null; renderAll(); }
    if (!inView(m, S.view)) setView("decide");
    select(m.id, { scroll: true });
  }
  function tickWaits() { // 每分钟走一次：只改等待时间、队列条和阅读区那几行字，不重画列表
    document.querySelectorAll(".item .time.wait[data-ts]").forEach(function (el) {
      var ts = el.getAttribute("data-ts");
      el.textContent = "等 " + fmtWait(ts, true);
      el.classList.toggle("long", waitMin(ts) >= 30);
    });
    renderQueue();
    var m = S.current && S.byId[S.current], d = currentDetail(), ds = $("eyebrow").querySelector(":scope > span[title]");
    if (!m) return renderEmpty();
    if (ds) ds.textContent = ebDate(m); // 只换日期那几个字，不重画（焦点不丢）
    if (d && d.kind === "decision" && !d.response) $("decideState").textContent = waitState(d);
  }
  function waitState(d) { return "会话已等 " + fmtWait(d.ts) + " · 提交后立即继续"; }

  // ---------------------------------------------------------------- 渲染
  function renderAll() {
    plMemo = null;
    plMemo = projectList();
    try {
      renderNav();
      renderList();
      renderReader();
      renderFoot();
    } finally { plMemo = null; }
  }

  function renderNav() {
    var c = S.counts, sc = scopeCounts();
    var n = { decide: [sc.open, true, " 条待决定"], answer: [sc.unread_answers, false, " 条未读回答"], all: [sc.unread, false, " 条未读"], archive: [0] };
    keepFocus($("nav"), function () {
      $("nav").innerHTML = VIEWS.map(function (v) {
        var k = n[v.id], tip = k[2] ? k[0] + k[2] : ""; // 数字是什么意思写在悬停提示里
        return '<button class="tab' + (S.view === v.id ? " active" : "") + '" data-view="' + v.id + '"' +
          (tip ? ' title="' + tip + '" aria-label="' + v.label + "，" + tip + '"' : "") + ">" + v.label +
          '<span class="n' + (k[0] && k[1] ? " hot" : "") + '">' + (k[0] || "") + "</span></button>";
      }).join("");
    });
    renderProjects();
    renderQueue();
    renderTools();
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
      var on = S.projects.has(p.key);
      var badge = '<span class="n' + (p.open ? " hot" : "") + '">' + (p.open || p.unread || "") + "</span>";
      var tip = (p.key === OTHER ? "没认出属于哪个仓库的旧消息 · 右键或点「归到…」可以归到某个仓库" : p.name +
        (p.open ? " · " + p.open + " 条待决定" : "") + (p.unread ? " · " + p.unread + " 条未读" : "")) +
        "\n点：只看它 · Ctrl/Shift + 点：多选 · ×（或中键）：关掉" + (p.key === OTHER ? "" : " · 右键：归到别的仓库");
      return '<button class="ptab' + (on ? " on" : "") + (p.key === OTHER ? " other" : "") + '" data-project="' + esc(p.key) +
        '" role="tab" aria-selected="' + on + '" title="' + esc(tip) + '">' +
        '<span class="pdot" style="background:' + pcolor(p.key) + '"></span>' +
        '<span class="pname">' + esc(p.name) + "</span>" + badge +
        '<span class="pclose" title="关闭这个标签：它的消息不再显示、不计数，来新消息时自动回来">' + icon("x") + "</span></button>";
    };
    var box = $("projects"), open = ps.reduce(function (s, p) { return s + p.open; }, 0), all = !S.projects.size;
    keepFocus(box, function () {
      box.innerHTML = '<button class="ptab all' + (all ? " on" : "") + '" data-project="" role="tab" aria-selected="' + all + '" title="看所有仓库' +
        (open ? " · " + open + " 条待决定" : "") + '（Esc）">全部项目<span class="n' + (open ? " hot" : "") + '">' + (open || "") + "</span></button>" +
        ps.map(tab).join("");
    });
    renderClosed(); // 先定好右头按钮在不在：下面量标签条宽度要用
    var on = box.querySelector(".ptab.on");
    if (on && (on.offsetLeft < box.scrollLeft || on.offsetLeft + on.offsetWidth > box.scrollLeft + box.clientWidth)) {
      box.scrollLeft = on.offsetLeft - 8;
    }
    ptabFade();
  }
  // 搜索框右边的两个按钮："只看未处理"开关、一键归档已处理的。归档视图里都收起来
  function handledIds() { // 已处理 = 已读、不用再决定；只算当前项目范围（和"⋯"菜单里"归档所有已处理的"一样）
    return S.msgs.filter(function (m) { return !m.archived && inScope(m) && !m.unread && !m.open; }).map(function (m) { return m.id; });
  }
  function renderTools() {
    var arch = S.view === "archive", t = $("todoBtn"), h = $("handledBtn"), n = arch ? 0 : handledIds().length;
    t.hidden = h.hidden = arch;
    t.classList.toggle("on", S.todo);
    t.setAttribute("aria-pressed", S.todo ? "true" : "false");
    h.setAttribute("aria-disabled", n ? "false" : "true"); // 不用 disabled：按不了也要能看到悬停提示
    h.title = n ? "归档已处理的 " + n + " 条（" + (scopeLabel() ? scopeLabel() + " · " : "") + "已读、不用再决定）" : "没有已处理的可以归档（已读、不用再决定的）";
    h.setAttribute("aria-label", h.title);
  }
  function setTodo(on) { // F 或点开关。正在看的这条留着（换到别的才走），勾选清掉（只作用在眼前这些）
    S.todo = !!on;
    save("todo", S.todo ? "1" : "");
    S.keep = S.current;
    S.multi.clear();
    renderNav();
    renderList();
  }
  function archiveHandled() { // 一键归档已处理的：不问，可以撤销（撤销只放回这一批）
    var ids = handledIds();
    if (!ids.length) return toast("没有已处理的可以归档");
    dropUndo();
    act({ action: "archive", ids: ids, on: true }).then(function (n) {
      toast(n ? "已归档 " + n + " 条" : "没有已处理的可以归档", n ? { undo: undoArchive(ids, true, []) } : null);
      return refreshNow(true);
    }).catch(function (e) { toast(e.message, { bad: true }); });
  }

  function ptabFade() { // 标签放不下时，哪头还有就在哪头淡出
    var b = $("projects");
    b.classList.toggle("fade-l", b.scrollLeft > 1);
    b.classList.toggle("fade-r", b.scrollLeft + b.clientWidth < b.scrollWidth - 1);
    // 右边看不见的标签里有待决定：标签条右头亮一个小圆点，点了滚过去
    var box = b.getBoundingClientRect(); // 用屏幕坐标量：标签的 offsetLeft 不是相对标签条算的
    var hid = Array.prototype.filter.call(b.querySelectorAll(".ptab"), function (t) { return t.querySelector(".n.hot") && t.getBoundingClientRect().right > box.right + 1; });
    var more = $("ptabMore"); more.hidden = !hid.length;
    more.title = "右边还有 " + hid.length + " 个项目在等你决定";
    more.onclick = function () {
      if (hid[0]) b.scrollTo({ left: b.scrollLeft + hid[0].getBoundingClientRect().left - b.getBoundingClientRect().left - 8, behavior: reduced() ? "auto" : "smooth" });
    };
  }

  // 右键标签 / 分组标题：把这个项目（或没认出来的来源）归到另一个项目下
  function mergeMenu(x, y, from, tab) { // tab：右键的是顶上的标签，最后再加"关闭这个标签"（"未归类"只有这一项）
    var targets = projectList().filter(function (p) { return p.key !== OTHER && p.key !== from; });
    var undo = Object.keys(S.aliases || {}).filter(function (k) { return S.aliases[k] === from; });
    var html = '<div class="menu-label">把「' + esc(from) + "」归到：</div>" +
      (targets.length ? targets.map(function (p) {
        return '<button class="menu-item" data-to="' + esc(p.key) + '"><span class="pdot" style="background:' + pcolor(p.key) + '"></span>' + esc(p.name) + "</button>";
      }).join("") : '<div class="menu-label">（还没有别的项目）</div>') +
      (undo.length ? '<div class="menu-sep"></div>' + undo.map(function (k) {
        return '<button class="menu-item" data-undo="' + esc(k) + '">' + icon("x") + "把「" + esc(k) + "」拆出来</button>";
      }).join("") : "");
    if (tab) html = (from === OTHER ? "" : html + '<div class="menu-sep"></div>') + '<button class="menu-item" data-close>' + icon("eyeOff") + "关闭这个标签<span class=\"sub\">中键</span></button>";
    var fake = { getBoundingClientRect: function () { return { left: x, right: x + 1, top: y, bottom: y }; } };
    openPopover(fake, html, "", function (ev) {
      var b = ev.target.closest("[data-to],[data-undo],[data-close]");
      if (!b) return;
      closePopover();
      if (b.hasAttribute("data-close")) return closeTab(from);
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
    var vis = new Set(S.visible); // 勾选只留看得见的（在别处归档了、被搜索筛掉的不留）：批量操作只作用在眼前这些
    S.multi.forEach(function (id) { if (!vis.has(id)) S.multi.delete(id); });
    var more = searchMore(); // 搜索命中但被视图 / 项目挡住的："另有 N 条…"一行，和列表一起写
    if (!items.length) {
      setList('<div class="list-empty"><b>' +
        (S.query ? (more ? "「" + v.label + (scopeLabel() ? " · " + esc(scopeLabel()) : "") + "」里没有「" + esc(S.query) + "」" : "没有找到「" + esc(S.query) + "」")
          : (scopeLabel() ? esc(scopeLabel()) + "：" : "") + (todoOn() ? "没有未处理的了" : v.empty)) + "</b>" +
        (S.query ? (more ? "" : "换个关键词试试") : todoOn() ? "处理过的都收起来了 · 按 F 显示全部" : v.emptySub) + "</div>" + more);
    } else if (grouped()) {
      var html = "", last = null; // 分组标题不带数：顶部标签已经有，下面的行也各有圆点
      items.forEach(function (m) {
        var p = projectOf(m), other = m.project_kind === "other";
        if (p !== last) {
          html += '<div class="group-label' + (other ? " other" : "") + '" data-project="' + esc(p) + '" data-tab="' + esc(tabKey(m)) + '">' +
            '<span class="pdot" style="background:' + pcolor(other ? OTHER : p) + '"></span>' +
            '<button class="gname" title="' + (other ? "只看「未归类」：没认出属于哪个仓库的旧消息 · 右键或点「归到…」可以归到某个仓库" : "只看 " + esc(p)) + '">' + esc(p) + "</button>" +
            '<button class="gmerge" tabindex="-1" title="归到某个项目下">归到…</button></div>';
          last = p;
        }
        html += itemHtml(m);
      });
      setList(html + more);
    } else {
      setList(items.map(itemHtml).join("") + more);
    }
    renderBulk();
  }
  // 列表 HTML 和上次一样就不重建（长轮询每次醒来都会重画；上千条时重建要上百毫秒，还会丢悬停）
  var lastListHtml = null;
  function setList(html) {
    if (html === lastListHtml) return;
    $("list").innerHTML = html;
    lastListHtml = html;
  }
  function rowEl(id) { return id ? $("list").querySelector('.item[data-id="' + cssEsc(id) + '"]') : null; }
  function renderRow(id) { // 只重画一行（选中 / 已读变了）；DOM 和上次整份写的不一样了，下次整份重画不能跳过
    var el = rowEl(id), m = S.byId[id];
    lastListHtml = null;
    if (el && m) el.outerHTML = itemHtml(m);
  }

  function itemHtml(m) {
    var checked = S.multi.has(m.id);
    var cls = "item" + (m.unread ? " unread" : "") + (m.open ? " open" : "") +
      (m.id === S.current ? " selected" : "") + (checked ? " multi" : "") + (S.fresh[m.id] > Date.now() ? " fresh" : "") +
      (!S.current && m.id === S.cursor ? " cursor" : "");
    // 状态圆点：实心 = 没读过；强调色 = 等你处理；空心环 = 看过、还没决定；外加一圈 = 紧急的待决定（只给决定，处理完才消失）
    var dot = m.open ? (m.priority === "high" ? "hot urgent" : m.unread ? "hot" : "hot seen") : m.unread ? (m.priority === "high" ? "hot" : "new") : "";
    var p = projectOf(m), sl = m.source.toLowerCase(), pl = p.toLowerCase();
    var src = sl === pl ? "" : sl.indexOf(pl + "/") === 0 ? m.source.slice(p.length + 1) : m.source;
    var bits = []; // 第二行：类型 · 状态 · 来源 · 摘要，缺哪段就跳过，不留多余的 " · "
    if (!m.open && (S.view === "all" || S.view === "archive" || S.query) && m.kind !== "decision") bits.push('<span class="st kind">' + KIND[m.kind] + "</span>");
    if (m.open) bits.push('<span class="st open">' + (m.priority === "high" ? "紧急 · " : "") + "待决定</span>");
    else if (m.kind === "decision" && m.resolved) bits.push('<span class="st done">✓ 已处理</span>');
    else if (m.kind === "decision" && m.dismissed) bits.push('<span class="st skip">已跳过</span>');
    else if (m.kind === "decision" && m.answered) bits.push('<span class="st done">✓ ' + esc(m.choice || "已回复") + "</span>");
    else if (m.priority === "high" && m.unread) bits.push('<span class="st open">紧急</span>');
    if (m.followup_pending) bits.push('<span class="st fu">已追问 · 等回答</span>'); // 你追问了，会话还没回应（等的是 Claude，不用强调色）
    else if (m.reply_to) bits.push('<span class="st kind">回应追问</span>');
    if (src) bits.push('<span class="src">' + esc(src) + "</span>");
    if (m.snippet) bits.push(esc(m.snippet));
    // 悬停按钮和勾选框不进 Tab 顺序（平时看不见；键盘有 U / R / E / Delete / X）
    var acts = '<span class="acts">' +
      '<button class="act" tabindex="-1" data-act="read" title="' + (m.unread ? "标为已读" : "标为未读") + '（U）">' + icon(m.unread ? "mailOpen" : "mail") + "</button>" +
      (m.open || m.unread ? '<button class="act" tabindex="-1" data-act="resolve" title="标为已处理（R）">' + icon("check") + "</button>" : "") +
      '<button class="act" tabindex="-1" data-act="archive" title="' + (m.archived ? "移出归档" : "归档") + '（E）">' + icon(m.archived ? "unarchive" : "archive") + "</button>" +
      '<button class="act danger" tabindex="-1" data-act="delete" title="删除（Delete）">' + icon("trash") + "</button></span>";
    return '<div class="' + cls + '" data-id="' + esc(m.id) + '" role="option" aria-selected="' + (m.id === S.current) + '">' +
      '<button class="cb' + (checked ? " on" : "") + '" tabindex="-1" data-act="check" title="选择（X）" aria-label="选择"></button>' +
      (dot ? '<span class="dot ' + dot + '"></span>' : "") +
      '<div class="row1"><span class="t">' + esc(m.title) + "</span>" + timeCell(m) + acts + "</div>" +
      '<div class="row2">' + (bits.join(" · ") || "&nbsp;") + "</div></div>";
  }

  function renderBulk() {
    var n = S.multi.size;
    if (n < 1 && $("bulkbar").contains(document.activeElement)) $("list").focus(); // 批量栏要收起来了，焦点还在它的按钮上：交给列表
    $("bulkbar").hidden = n < 1;
    $("list").classList.toggle("multi-mode", n > 0);
    if (!n) return;
    var ids = Array.from(S.multi);
    var all = S.visible.length && S.visible.every(function (id) { return S.multi.has(id); });
    var ca = $("checkAll");
    ca.classList.toggle("on", !!all);
    ca.classList.toggle("some", !all);
    $("bulkCount").innerHTML = '<span class="pre">已选 </span>' + n + " 条"; // 列表 320px 时"已选"省掉，给"标为已处理"让地方
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
      renderEmpty();
      return;
    }
    $("empty").hidden = true;
    $("detail").hidden = false;
    var key = m.id + "|" + m.answered;
    if (S.shownKey === key) { renderEyebrow(m); syncFollowup(m); return; }
    var cached = S.details[key];
    if (cached) return showDetail(keepDetail(key, cached), key);
    api("/api/message?id=" + encodeURIComponent(m.id)).then(function (d) {
      if (!d || d.error) return;
      keepDetail(key, d);
      var cm = S.current && S.byId[S.current]; // 回来晚了：这期间它可能已经有了回复（在对话里处理掉了），旧的"未回复"版不能再盖上去
      if (cm && cm.id + "|" + cm.answered === key) showDetail(d, key);
    });
  }
  // 详情缓存：最近用过的排在最后，最多留 60 条；有了"已回复"版就丢掉旧的"未回复"版
  function keepDetail(key, d) {
    delete S.details[key];
    S.details[key] = d;
    if (/\|true$/.test(key)) delete S.details[key.replace(/\|true$/, "|false")];
    var ks = Object.keys(S.details);
    for (var i = 0; i < ks.length - 60; i++) delete S.details[ks[i]];
    return d;
  }

  // 待决定：卡片上已经写了"会话已等 25 分钟"，这里只写日期
  function ebDate(m) { return m.open ? fmtRel(m.ts).split(" · ")[0] : fmtRel(m.ts); }
  function renderEyebrow(m) { // 每段包一层 .eb，分隔点画在后一段前面（CSS），折行时不会挂在行末
    var bits = ['<span class="eb">' + KIND[m.kind] + "</span>", '<span class="eb"><span class="src"><span class="pdot" style="background:' + pcolor(tabKey(m)) + '"></span>' + esc(m.source) + "</span></span>",
      '<span class="eb" title="' + fmtTime(m.ts, true) + '">' + ebDate(m) + "</span>"];
    if (m.priority === "high") bits.push('<span class="eb"><span class="hot">紧急</span></span>');
    if (m.archived) bits.push('<span class="eb">已归档</span>');
    keepFocus($("eyebrow"), function () {
      $("eyebrow").innerHTML = bits.join("") + (m.open ? '<button class="jump" id="jumpBtn">去选择 ↓</button>' : "");
    });
    updateJump();
  }
  // 整块重写 innerHTML 会把焦点丢到 body：键盘停在里面某个按钮上时（长轮询、计时器随时会重画），重画后还给同一个按钮。
  // 只管键盘焦点（:focus-visible）：鼠标点过留下的看不见的焦点照旧丢掉，免得之后按 Enter 又点了一次这个按钮
  function keepFocus(box, write) {
    var a = document.activeElement, sel = null;
    if (a && a !== box && box.contains(a) && a.matches(":focus-visible")) {
      sel = a.id ? "#" + cssEsc(a.id) : a.dataset.view ? '[data-view="' + cssEsc(a.dataset.view) + '"]' :
        a.dataset.project != null ? '[data-project="' + cssEsc(a.dataset.project) + '"]' : null;
    }
    write();
    var b = sel && box.querySelector(sel);
    if (b && document.activeElement !== b) b.focus();
  }
  // "去选择 ↓"：决定卡片已经露出来了就不显示
  function updateJump() { var j = $("jumpBtn"); if (j) j.hidden = $("decide").hidden || $("decide").getBoundingClientRect().top < $("scroller").getBoundingClientRect().bottom - 48; }

  function showDetail(d, key) {
    var newMsg = !S.shownKey || S.shownKey.split("|")[0] !== d.id;
    S.shownKey = key;
    renderEyebrow(S.byId[d.id] || d);
    $("title").textContent = d.title;
    $("question").hidden = !d.question;
    $("questionText").textContent = d.question || "";
    renderBody(d);
    renderDecision(d, newMsg);
    renderFollowup(d, newMsg);
    renderThreadRef(d);
    syncFollowup(S.byId[d.id] || d); // 缓存里的详情可能比列表旧（期间又追问 / 送达 / 有了回应）
    if (newMsg) {
      $("scroller").scrollTop = 0;
      $("toolbar").classList.remove("scrolled");
    }
    requestAnimationFrame(updateJump); // 正文、卡片排好之后再量
  }
  function renderBody(d) { // 设置（字号 / 字体）变了只重画正文，选项和没写完的回复不动
    var body = $("body");
    if ((d.body || "").trim()) {
      body.innerHTML = MD.toHtml(d.body);
      MD.hydrate(body);
    } else {
      body.innerHTML = '<p class="no-body">（没有正文）</p>';
    }
  }
  function shownId() { return S.shownKey ? S.shownKey.split("|")[0] : null; }

  function renderDecision(d, reset) {
    var box = $("decide");
    if (d.kind !== "decision") { box.hidden = true; S.choice = S.choiceIdx = null; return; }
    box.hidden = false;
    var r = d.response, dr = S.drafts[d.id];
    if (r) { S.choice = S.choiceIdx = null; delete S.drafts[d.id]; } // 已有回复：草稿作废
    else if (reset) { // 换了一条：恢复这条自己的草稿（选项按序号记，同名选项也分得开）
      S.choiceIdx = dr && dr.idx != null && d.options && d.options[dr.idx] ? dr.idx : null;
      S.choice = S.choiceIdx != null ? d.options[S.choiceIdx].label : null;
    }
    var busy = !r && !!S.submitting[d.id];
    var opts = $("options");
    opts.innerHTML = (d.options || []).map(function (o, i) {
      var chosen = r && (r.choice_index ? r.choice_index === i + 1 : r.choice === o.label);
      return '<button class="opt' + (chosen ? " chosen" : "") + (!r && S.choiceIdx === i ? " checked" : "") + '" data-idx="' + i + '"' + (r || busy ? " disabled" : "") + ">" +
        '<span class="num">' + (chosen ? icon("check") : i + 1) + "</span>" +
        '<span class="txt"><span class="lab">' + esc(o.label) +
        (d.recommended === i + 1 ? '<span class="rec">推荐</span>' : "") + "</span>" +
        (o.description ? '<span class="desc">' + esc(o.description) + "</span>" : "") + "</span></button>";
    }).join("");
    opts.hidden = !(d.options || []).length;
    var ta = $("replyText");
    ta.hidden = !!r; // 每条决定都能写补充说明（不管发的时候 allow_text 写没写）
    if (reset) ta.value = !r && dr ? dr.text : "";
    ta.readOnly = busy;
    box.setAttribute("aria-busy", busy ? "true" : "false");
    $("submitBtn").textContent = busy ? "提交中…" : "提交";
    $("resolveBtn").disabled = busy;
    ta.placeholder = (d.options || []).length ? "补充说明（可选）" : "写下你的回复";
    $("decideFoot").hidden = !!r;
    $("decideTitle").textContent = r ? "你的回复" : (d.options || []).length ? "请选择一个选项" : "请写下你的回复";
    var done = $("doneBox");
    if (r) {
      var when = r.ts ? fmtRel(r.ts).split(" · ")[0] : ""; // 和阅读区顶上一样写"今天 00:07"
      done.hidden = false;
      done.className = "reply-done" + (r.dismissed ? " skip" : "");
      if (r.resolved) done.innerHTML = "<b>已标为已处理</b> · " + when + "<div>没有选择选项，等待的会话已收到「已经处理好了」。</div>";
      else if (r.dismissed) done.innerHTML = "<b>已跳过</b> · " + when + "<div>没有作出选择，等待的会话已收到通知。</div>";
      else if (r.closed_by === "claude") done.innerHTML = "<b>已在对话中处理</b> · " + when + (r.text ? '<div class="reply-text">' + esc(r.text) + "</div>" : "");
      else done.innerHTML = "<b>已提交</b> · " + (when ? when + " · " : "") + "会话已收到" + // 选了哪项看上面打了 ✓ 的那项，不再重复
        (r.text ? '<div class="reply-text">' + esc(r.text) + "</div>" : "");
      // 还有别的待决定：给个按钮过去，但不自动跳（列表和阅读区不突然变）
      if (queue().some(function (x) { return x.id !== d.id; })) done.insertAdjacentHTML("beforeend", '<button class="ghost next-dec" data-next>下一条待决定 →（N）</button>');
      $("decideState").textContent = "";
    } else {
      done.hidden = true;
      $("decideState").textContent = waitState(d);
    }
    updateSubmit();
  }

  function currentDetail() {
    var m = S.current && S.byId[S.current];
    return m ? S.details[m.id + "|" + m.answered] : null;
  }

  function pick(idx) {
    var d = currentDetail();
    if (!d || d.response || S.submitting[d.id] || !d.options || !d.options[idx]) return;
    S.choice = d.options[idx].label;
    S.choiceIdx = idx;
    $("options").querySelectorAll(".opt").forEach(function (b) {
      b.classList.toggle("checked", +b.dataset.idx === idx);
    });
    saveDraft(d.id);
    updateSubmit();
  }
  function saveDraft(id) { // 每条消息各记各的：切走、改设置、返回列表再回来都还在
    var text = $("replyText").value;
    if (S.choiceIdx == null && !text.trim()) delete S.drafts[id];
    else S.drafts[id] = { idx: S.choiceIdx, text: text };
  }
  function updateSubmit() {
    var d = currentDetail();
    var ok = d && !d.response && !S.submitting[d.id] && (S.choice != null || !!$("replyText").value.trim()); // 只写字、不选选项也能交
    $("submitBtn").disabled = !ok;
    renderHint(d);
  }
  // 卡片底部的提示要说真话：还没选 → 按数字选；选了 → Ctrl+Enter 提交「这一项」
  function renderHint(d) {
    if (!d || d.response) return;
    if (S.submitting[d.id]) { $("decideHint").textContent = "正在发给会话…"; return; } // 提交中：不再说"Ctrl+Enter 提交"
    var n = (d.options || []).length, text = $("replyText").value.trim();
    $("decideHint").textContent = S.choice != null ? "Ctrl+Enter 提交「" + S.choice + "」" :
      !n ? (text ? "Ctrl+Enter 提交" : "写好后 Ctrl+Enter 提交") :
      "按 " + (n > 1 ? "1–" + Math.min(n, 9) : "1") + " 选择" + (text ? "，或 Ctrl+Enter 提交" : "，或直接写回复");
  }
  function reduced() { return !!(window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches); }
  // 数字键选了之后：选中的那项不在屏幕上就滚过去，免得选在看不见的地方
  function revealDecide() {
    var o = $("options").querySelector(".opt.checked"), box = $("decide");
    if (!o || box.hidden) return;
    var r = o.getBoundingClientRect(), s = $("scroller").getBoundingClientRect();
    if (r.top >= s.top && r.bottom <= s.bottom) return;
    (box.offsetHeight <= s.height ? box : o).scrollIntoView({ block: "nearest", behavior: reduced() ? "auto" : "smooth" });
  }
  function submit() {
    var d = currentDetail();
    if (!d || d.kind !== "decision" || d.response || S.submitting[d.id] || $("submitBtn").disabled) return;
    var text = $("replyText").value.trim();
    var o = S.choice != null && d.options && d.options[S.choiceIdx];
    var body = { action: "reply", id: d.id, choice: S.choice, text: text };
    if (o && o.label === S.choice) body.choice_index = S.choiceIdx + 1; // 按序号提交：同名的两个选项不会报错成第一个
    // 提交中：按钮写"提交中…"，选项、输入框锁住；失败原样恢复，可以重试
    S.submitting[d.id] = 1;
    renderDecision(d, false);
    act(body).then(function () {
      delete S.submitting[d.id];
      delete S.drafts[d.id];
      if (shownId() !== d.id) toast("已提交「" + d.title + "」，会话会马上收到"); // 还在看这条：下面的回复框就写着，不再弹提示挡住它
      return refreshNow(true);
    }).catch(function (e) {
      delete S.submitting[d.id];
      var sd = S.details[S.shownKey]; // 用最新的详情恢复（期间可能已经在对话里被处理掉了）
      if (sd && sd.id === d.id) renderDecision(sd, false);
      toast("提交失败：" + e.message, { bad: true, action: "重试", run: function () {
        var cd = currentDetail();
        if (cd && cd.id === d.id) submit(); else window.deskOpen(d.id); // 已经换到别的消息：先带回这条，不替别的消息提交
      } });
    });
  }

  // ---------------------------------------------------------------- 追问（每条消息底部；还没回复的决定只有自己的回复框，回复了才出现）
  // 会话挂着 wait --followups 时（listening）发出去它就接着答；它领走一条就退出、答完再挂上，这段时间说"正在回答"
  // （delivered 是领走的时间；一小时还没回应，多半是会话没了，不再这么说）
  function canFollow(d) { return !!d && !(d.kind === "decision" && !d.response); }
  var fuSending = {}; // 正在发追问的消息 id（和决定的 S.submitting 分开：决定刚提交完、卡片刚出现时不能是锁着的）
  function fuAnswering(f) { return !!f.delivered && !f.reply && Date.now() - new Date(f.delivered) < 3600e3; }
  function fuState(d) {
    var m = S.byId[d.id] || d;
    if (m.listening) return ["on", "会话在线，发出后它会接着回答。"];
    if ((d.followups || []).some(fuAnswering)) return ["on", "会话收到了你的追问，正在回答。"];
    return ["off", "这个会话现在没在听（可能已经结束了）。追问会存在这里；也可以复制下来，直接粘到 Claude 对话里。"];
  }
  function fuStored(d) { return (d.followups || []).filter(function (f) { return !f.reply && !fuAnswering(f); }); } // 可以复制到对话里的
  function renderFollowup(d, reset) {
    var box = $("followup");
    if (!canFollow(d)) { box.hidden = true; return; }
    box.hidden = false;
    var busy = !!fuSending[d.id], link = function (r) { return '<button class="fu-a" data-open="' + esc(r.id) + '">Claude 的回答：' + esc(r.title) + " →</button>"; };
    // 你的追问按时间排，每条下面是回应它的那条回答（点了打开），还没有就"等待回答…"
    var html = (d.followups || []).map(function (f) {
      return '<div class="fu-item"><div class="fu-when" title="' + fmtTime(f.ts, true) + '">你的追问 · ' + fmtRel(f.ts).split(" · ")[0] + "</div>" +
        '<div class="fu-q">' + esc(f.text) + "</div>" + (f.reply ? link(f.reply) :
        '<div class="fu-wait">等待回答…' + (f.delivered ? " · 已送到会话" : "") + "</div>") + "</div>";
    }).join("") + (d.replies || []).filter(function (r) { return !r.paired; }).map(link).join(""); // 配不上追问的回应也列出来
    $("fuList").innerHTML = html;
    $("fuList").hidden = !html;
    var ta = $("fuText"), dr = S.drafts[d.id];
    if (reset || ta.dataset.id !== d.id) ta.value = dr ? dr.text : ""; // 每条各记各的草稿；决定刚回复、卡片刚出现时也换成它自己的
    ta.dataset.id = d.id;
    ta.readOnly = busy;
    box.setAttribute("aria-busy", busy ? "true" : "false");
    $("fuSend").textContent = busy ? "发送中…" : "发送";
    renderFuState(d);
  }
  function renderFuState(d) { // 会话上线 / 下线、打字：只重画状态行和按钮
    var st = fuState(d), busy = !!fuSending[d.id], text = $("fuText").value.trim();
    $("fuState").className = "fu-state " + st[0];
    $("fuState").textContent = st[1];
    $("fuCopy").hidden = st[0] === "on" || !fuStored(d).length;
    $("fuSend").disabled = busy || !text;
    $("fuHint").textContent = busy ? "正在发送…" : text ? "Ctrl+Enter 发送" : "";
  }
  // 长轮询来了：追问 / 送达 / 回应变了（列表里的 fstate 和详情的对不上）就重新拿这条的详情，只重画追问卡片；否则只更新在线状态
  var fuFetching = {};
  function syncFollowup(m) {
    var d = S.details[S.shownKey];
    if (!m || !d || d.id !== m.id) return;
    if ((d.fstate || "") === (m.fstate || "")) { if (canFollow(d)) renderFuState(d); return; }
    if (fuFetching[m.id]) return;
    fuFetching[m.id] = 1;
    api("/api/message?id=" + encodeURIComponent(m.id)).then(function (nd) {
      delete fuFetching[m.id];
      var cm = S.byId[m.id];
      if (!nd || nd.error || !cm || nd.answered !== cm.answered) return;
      var key = cm.id + "|" + cm.answered;
      keepDetail(key, nd);
      if (S.shownKey === key) { renderFollowup(nd, false); renderThreadRef(nd); }
    }).catch(function () { delete fuFetching[m.id]; });
  }
  function sendFollowup() {
    var d = currentDetail();
    if (!canFollow(d) || fuSending[d.id]) return;
    var text = $("fuText").value.trim();
    if (!text) { $("fuText").focus(); return; } // 还没写：Ctrl+Enter 先把光标放进追问框
    fuSending[d.id] = 1; // 发送中：按钮写"发送中…"，输入框锁住；失败原样恢复，可以重试
    renderFollowup(d, false);
    act({ action: "followup", id: d.id, text: text }).then(function () {
      delete fuSending[d.id];
      delete S.drafts[d.id];
      var cd = currentDetail();
      if (cd && cd.id === d.id) { $("fuText").value = ""; renderFollowup(cd, false); }
      else toast("已追问「" + d.title + "」");
      return refreshNow(true);
    }).catch(function (e) {
      delete fuSending[d.id];
      var cd = currentDetail();
      if (cd && cd.id === d.id) renderFollowup(cd, false);
      toast("追问没发出去：" + e.message, { bad: true });
    });
  }
  function copyFollowup() { // 会话没在听：带上原消息的标题（原问题、我当时的选择）复制，粘到对话里会话也知道问的是哪条
    var d = currentDetail(), fs = d ? fuStored(d) : [];
    if (!fs.length) return;
    var cut = function (s) { s = (s || "").replace(/\s+/g, " ").trim(); return s.length > 100 ? s.slice(0, 100) + "…" : s; };
    var q = cut(d.question), r = d.response, mine = r && (r.resolved ? "标为已处理" : r.dismissed ? "跳过了" : cut(r.choice || r.text));
    var text = "关于你在 ClaudeDesk 里发的" + KIND[d.kind] + "「" + d.title + "」" + (q ? "（原问题：" + q + "）" : "") +
      (mine ? "（我当时的回复：" + mine + "）" : "") + "，我追问：\n\n" + fs.map(function (f) { return f.text; }).join("\n\n") +
      "\n\n（ClaudeDesk 追问 · 原消息 id：" + d.id + "）\n";
    writeClipboard(text).then(function () { toast("已复制追问，粘到 Claude 对话里就行"); })
      .catch(function (e) { toast("复制失败：" + e.message, { bad: true }); });
  }
  function renderThreadRef(d) { // 回应追问的那条：顶上写它回应的是哪句追问，点了回到被追问的那条
    var r = d.reply_ref, el = $("threadRef");
    el.hidden = !r;
    if (!r) return;
    var q = (r.text || "").replace(/\s+/g, " ").trim(), k = KIND[r.kind] || "消息";
    if (q === (d.question || "").replace(/\s+/g, " ").trim()) q = ""; // 追问原文就在下面的引用块里，不重复
    el.innerHTML = '<span class="tr-q">↩ 回应你的追问' + (q ? "：「" + esc(q.length > 60 ? q.slice(0, 60) + "…" : q) + "」" : "") + "</span>" +
      (r.exists ? '<button class="tr-link" data-open="' + esc(r.id) + '" title="回到被追问的那条">原' + k + "：" + esc(r.title) + "</button>" : "<span>（原消息已删除）</span>");
  }

  // ---------------------------------------------------------------- 选择 / 导航
  function select(id, opts) {
    opts = opts || {};
    var was = S.keep && S.byId[S.keep], drop = was && S.keep !== id && todoOn() && !needsYou(was); // 只看未处理：刚才看完的那条换走了，这才从列表里走
    S.current = S.keep = id;
    S.cursor = id; // 窄窗口返回列表时，光标停在刚看的这条
    if (!opts.keepMulti) { S.multi.clear(); S.anchor = id; } // 多选时锚点不动，Shift + ↑↓ 从它连选
    var m = S.byId[id];
    var marked = false;
    clearTimeout(readTimer);
    if (m && m.unread && !opts.noRead) {
      if (opts.via === "key") readTimer = setTimeout(function () { if (markRead(id)) { renderRow(id); renderNav(); } }, 800); // j/k 扫过去不算读：停 0.8 秒才算
      else marked = markRead(id);
    }
    // 只改前后两行，不重建整个列表（上千条时每按一次 ↑↓ 都重建会卡）
    if (drop || S.multi.size || $("list").classList.contains("multi-mode") || !rowEl(id)) renderList();
    else {
      $("list").querySelectorAll(".item.selected").forEach(function (el) { el.classList.remove("selected"); el.setAttribute("aria-selected", "false"); });
      $("list").querySelectorAll(".item.cursor").forEach(function (el) { el.classList.remove("cursor"); }); // 打开了一条：窄窗口的列表光标不再画
      renderRow(id);
    }
    if (marked) renderNav();
    renderReader();
    if (opts.scroll) {
      var el = document.querySelector('.item[data-id="' + cssEsc(id) + '"]');
      if (el) el.scrollIntoView({ block: "nearest" });
    }
  }
  var readTimer = null;
  function markRead(id) { // 乐观更新，再告诉服务端；已经换走了就不算
    var m = S.byId[id];
    if (S.current !== id || !m || !m.unread) return false;
    m.unread = false;
    act({ action: "read", ids: [id] }).catch(function () {});
    return true;
  }
  function cssEsc(s) { return window.CSS && CSS.escape ? CSS.escape(s) : s.replace(/"/g, '\\"'); }
  // ↑↓：有勾选时只挪光标，不丢勾选、不标已读；extend（Shift）= 从锚点连选到光标
  var ext = null; // 这一轮 Shift 连选：{ base: 开始前已勾的, anchor, at: 光标, size }，往回按能缩回去
  function move(delta, extend) {
    var ids = S.visible;
    if (!ids.length) return;
    if (narrow() && !S.current && !extend) { // 窄窗口列表页：↑↓ 只挪光标，不打开（Enter 才打开）
      var c = ids.indexOf(S.cursor), k = c < 0 ? 0 : Math.max(0, Math.min(ids.length - 1, c + delta)), prev = S.cursor;
      S.cursor = ids[k]; renderRow(prev); renderRow(S.cursor);
      var ce = rowEl(S.cursor); if (ce) ce.scrollIntoView({ block: "nearest" });
      return;
    }
    var i = ids.indexOf(S.current);
    var j = i < 0 ? 0 : Math.max(0, Math.min(ids.length - 1, i + delta));
    if (extend) {
      if (!ext || ext.at !== S.current || ext.anchor !== S.anchor || ext.size !== S.multi.size) { // 新的一轮
        if (!S.multi.size || !S.anchor || ids.indexOf(S.anchor) < 0) S.anchor = i < 0 ? ids[j] : ids[i];
        ext = { base: new Set(S.multi), anchor: S.anchor };
      }
      var a = ids.indexOf(S.anchor);
      S.multi = new Set(ext.base);
      ids.slice(Math.min(a, j), Math.max(a, j) + 1).forEach(function (x) { S.multi.add(x); });
      ext.at = ids[j]; ext.size = S.multi.size;
    } else ext = null;
    var keep = extend || S.multi.size > 0;
    select(ids[j], keep ? { scroll: true, keepMulti: true, noRead: true, via: "key" } : { scroll: true, via: "key" });
    if (extend) renderList(); // 勾选变了：列表要重画（select 以后可能只挪高亮）
  }
  function setView(v) {
    S.view = v;
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
  function moveOn(ids, next) { // 换到 next；"读完先留着的那条"跟着换（被移走的不再留）
    if (S.current !== next || ids.indexOf(S.keep) >= 0) S.keep = next;
    S.current = next;
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
    var unread = ids.filter(isUnread); // 归档会顺手标已读：撤销时把它们改回未读
    var go = function () {
      // 先在本地改好、移走选中并重画，再发请求：长轮询比操作的回应先到也不会"看的是 A、键盘操作的是 B"
      var cur = S.current, leaves = ids.indexOf(cur) >= 0 && (S.view !== "archive" ? on : !on);
      var next = leaves ? nextAfter(ids) : cur;
      ids.forEach(function (id) { if (S.byId[id]) S.byId[id].archived = on; });
      S.multi.clear();
      moveOn(ids, next);
      dropUndo();
      renderAll();
      refocusList();
      act({ action: "archive", ids: ids, on: on }).then(function () {
        return refreshNow(true);
      }).then(function () {
        toast((on ? "已归档 " : "已移出归档 ") + ids.length + " 条", { undo: undoArchive(ids, on, unread) });
      }).catch(function (e) { toast(e.message, { bad: true }); refreshNow(true); });
    };
    if (on && hasOpen(ids)) {
      confirmBox("归档还在等你决定的消息？", "等待中的会话会收到「用户跳过了这条决定」，然后继续往下走。", "归档并跳过").then(function (ok) { if (ok) go(); });
    } else go();
  }

  function doDelete(ids) {
    if (!ids.length) return;
    var text = "删除后不能恢复，会从收件箱文件里真正移除。" +
      (hasOpen(ids) ? "\n其中有还在等你决定的消息：等待中的会话会收到「用户跳过了这条决定」。" : "");
    var one = ids.length === 1 && S.byId[ids[0]], t = one ? one.title : "";
    if (t.length > 40) t = t.slice(0, 40) + "…";
    confirmBox(ids.length > 1 ? "删除这 " + ids.length + " 条消息？" : one ? "删除「" + t + "」？" : "删除这条消息？", text, "删除", true).then(function (ok) {
      if (!ok) return;
      // 和归档一样：先在本地删掉、选好下一条并重画，再发请求
      var cur = S.current, next = ids.indexOf(cur) >= 0 ? nextAfter(ids) : cur;
      ids.forEach(function (id) { S.gone[id] = 1; delete S.byId[id]; });
      S.msgs = S.msgs.filter(function (m) { return !S.gone[m.id]; });
      S.multi.clear();
      moveOn(ids, next);
      renderAll();
      refocusList();
      act({ action: "delete", ids: ids }).then(function () {
        return refreshNow(true);
      }).then(function () { toast("已删除 " + ids.length + " 条"); })
        .catch(function (e) { ids.forEach(function (id) { delete S.gone[id]; }); toast(e.message, { bad: true }); refreshNow(true); });
    });
  }

  // 标为已处理（R / ✓ / 批量栏 / 右键 / 决定卡片）：待决定的告诉等待的会话"已经处理好了"，其余的标为已读。
  // 只看未处理时，标完的从列表里走掉（正在看的也一样，和归档一样换到下一条）
  function doResolve(ids) {
    if (!ids.length) return;
    var open = ids.filter(function (id) { return S.byId[id] && S.byId[id].open; }).length;
    var unread = ids.filter(isUnread), n = ids.filter(function (id) { return S.byId[id] && (S.byId[id].open || S.byId[id].unread); }).length;
    if (ids.indexOf(S.current) >= 0) clearTimeout(readTimer); // 撤销后停留计时不能再把它标回已读
    dropUndo();
    var next = todoOn() && ids.indexOf(S.current) >= 0 ? nextAfter(ids) : S.current;
    unread.forEach(function (id) { S.byId[id].unread = false; }); // 先在本地改好再发请求（和归档一样）
    S.multi.clear();
    moveOn(ids, next);
    renderAll();
    refocusList();
    if (!open && !unread.length) return toast(ids.length > 1 ? "选中的都已经处理过了" : "这条已经处理过了");
    act({ action: "resolve", ids: ids }).then(function () {
      return refreshNow(true);
    }).then(function () { // 已经发给会话的回复收不回来：有待决定的就不给撤销
      toast("已标为已处理 " + n + " 条" + (open ? "，" + open + " 条待决定已告诉会话" : ""), open ? null : { undo: undoRead(unread, false) });
    }).catch(function (e) { toast(e.message, { bad: true }); refreshNow(true); });
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
    var flip = ids.filter(function (id) { return S.byId[id] && !!S.byId[id].unread === anyUnread; }); // 真的会变的那些
    if (ids.indexOf(S.current) >= 0) clearTimeout(readTimer); // 自己按了 U：停留计时不能事后再把它标回已读（撤销后也一样）
    dropUndo();
    act({ action: "read", ids: ids, read: anyUnread }).then(function () {
      if (ids.length > 1) S.multi.clear();
      toast((anyUnread ? "已标为已读" : "已标为未读") + (ids.length > 1 ? " " + ids.length + " 条" : ""), { undo: undoRead(flip, !anyUnread) });
      return refreshNow(true);
    });
  }

  // ---- 撤销（Z / Ctrl+Z 或提示条上的按钮）：把刚才的操作反过来做一遍
  function isUnread(id) { return !!(S.byId[id] && S.byId[id].unread); }
  function undoRead(ids, read) {
    return function () { act({ action: "read", ids: ids, read: read }).then(function () { return refreshNow(true); }).catch(function (e) { toast(e.message, { bad: true }); }); };
  }
  function undoArchive(ids, on, unread) {
    return function () {
      act({ action: "archive", ids: ids, on: !on }).then(function () {
        return on && unread.length ? act({ action: "read", ids: unread, read: false }) : null;
      }).then(function () { return refreshNow(true); }).catch(function (e) { toast(e.message, { bad: true }); });
    };
  }
  var lastUndo = null; // 最近一个还能撤销的操作 { run, el }：跟着它的提示条，提示条没了就不能撤销了
  // 新的可撤销操作一开始就作废旧的：它的提示条要等请求回来才出现，这之间按 Z 不能撤到更早的那个上
  function dropUndo() { if (lastUndo) { lastUndo.el.remove(); lastUndo = null; } }
  // 归档 / 删除拿掉了有焦点的按钮（行上的悬停按钮、批量栏）：焦点回到列表，键盘接着用
  function refocusList() {
    var a = document.activeElement;
    if (!a || a === document.body || !a.offsetParent) $("list").focus();
  }
  function undoLast() {
    var u = lastUndo;
    if (!u) return toast("没有可以撤销的操作");
    lastUndo = null;
    u.el.remove();
    u.run();
    toast("已撤销");
  }
  // R 键：牵涉待决定的会发给等待的会话、不能撤销，所以先确认；没有待决定的直接标（可以撤销）
  function askResolve(ids) {
    if (!ids.length) return;
    var open = ids.filter(function (id) { return S.byId[id] && S.byId[id].open; }).length;
    if (!open) return doResolve(ids);
    confirmBox(ids.length > 1 ? "把 " + ids.length + " 条标为已处理？" : "标为已处理？",
      ids.length > 1 ? "其中 " + open + " 条待决定会告诉等待中的会话「已经处理好了」。" : "等待中的会话会收到「已经处理好了」，然后继续往下走。",
      "标为已处理").then(function (ok) { if (ok) doResolve(ids); });
  }

  // ---- 复制
  function markdownOf(d) {
    var out = "# " + d.title + "\n\n";
    if (d.question) out += d.question.trim().split("\n").map(function (l) { return "> " + l; }).join("\n") + "\n\n";
    out += (d.body || "").trim() + "\n";
    if (d.response && d.response.choice) out += "\n---\n\n**我的选择：** " + d.response.choice + (d.response.text ? "\n\n" + d.response.text : "") + "\n";
    else if (d.response && d.response.text && !d.response.dismissed && !d.response.resolved && !d.response.closed_by) { // 只写了文字的回复（跳过 / 已处理 / 对话里处理的不算）
      out += "\n---\n\n**我的回复：** " + d.response.text + "\n";
    }
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
    var eb = a.querySelector(".eyebrow"); // 顶上那行的分隔点是 CSS 画的：纯文本里补回 " · "
    if (eb) eb.textContent = Array.prototype.map.call(eb.querySelectorAll(".eb"), function (e) { return e.textContent; }).join(" · ");
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
    } else if (d.kind === "decision" && (d.options || []).length) { // 还没决定：选项在 #decide 里，不在文章里，单独印出来
      var o = document.createElement("div");
      o.className = "md";
      o.innerHTML = "<hr><p><strong>待决定的选项：</strong></p><ol>" + d.options.map(function (x, i) {
        return "<li><strong>" + esc(x.label) + "</strong>" + (d.recommended === i + 1 ? "（推荐）" : "") +
          (x.description ? "：" + esc(x.description) : "") + "</li>";
      }).join("") + "</ol>";
      a.appendChild(o);
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
  function onSearch(e) {
    if (e && e.isComposing) return; // 输入法还在拼字（拼音）：等 compositionend 再搜
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function () {
      S.query = $("search").value.trim();
      runSearch();
    }, 120);
  }
  var searching = null; // 还在路上的那次搜索：↓ / Enter 要等它回来，才知道第一条结果是谁
  function runSearch() {
    if (!S.query) { S.searchIds = null; searching = null; renderAll(); return; }
    var q = S.query;
    return (searching = api("/api/search?q=" + encodeURIComponent(q)).then(function (r) {
      if (q !== S.query) return;
      S.searchIds = new Set(r.ids || []);
      renderAll();
    }));
  }
  function clearSearch() { $("search").value = ""; clearTimeout(searchTimer); S.query = ""; runSearch(); }
  // 搜索框里 ↓ / Enter：打开第一条结果，焦点回到列表（还在防抖、没搜的先搜完）
  function searchFirst() {
    var go = function () { if (S.visible.length) select(S.visible[0], { scroll: true }); $("list").focus(); };
    var q = $("search").value.trim();
    clearTimeout(searchTimer);
    if (q === S.query) return searching ? searching.then(go, go) : go(); // 防抖已过、结果还没回来：等它
    S.query = q;
    var p = runSearch();
    if (p) p.then(go); else go();
  }
  // 搜到了、但被当前视图 / 项目挡住的条数：列表末尾给一行"另有 N 条…"，点了去能看到它们的地方
  function searchMore() {
    if (!S.searchIds) return "";
    var shown = new Set(S.visible), live = 0, arch = 0, done = 0, ch = closedHits(); // done：只是被"只看未处理"收起来的
    S.searchIds.forEach(function (id) {
      var m = S.byId[id];
      if (m && !shown.has(id)) { if (m.archived) arch++; else live++; if (todoOn() && !m.archived && !needsYou(m)) done++; }
    });
    return (live || arch ? '<button class="search-more" data-more="' + (live ? "all" : "archive") + '">另有 ' + (live + arch) +
      (done ? " 条已处理或在其他视图、项目里" : " 条在其他视图或项目里") + "<span>" + (live ? "查看全部结果" : "去归档里看") + " →</span></button>" : "") +
      (ch.n ? '<button class="search-more" data-more-closed>另有 ' + ch.n + " 条在已关闭的标签里<span>找回并查看 →</span></button>" : "");
  }
  function closedHits() { // 搜到了、但在关掉的标签里的：{ n, keys, live 有没归档的 }
    var r = { n: 0, keys: [], live: false };
    if (S.searchIds) S.searchIds.forEach(function (id) {
      var m = S.allById[id];
      if (!m || S.byId[id] || S.gone[id] || !closedOf(m)) return;
      r.n++;
      if (!m.archived) r.live = true;
      if (r.keys.indexOf(tabKey(m)) < 0) r.keys.push(tabKey(m));
    });
    return r;
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
    var first = p.querySelector("button:not([disabled])");
    if (first) first.focus(); // 焦点进菜单，键盘能直接 ↑↓ / 回车
  }
  function closePopover() {
    var p = $("popover"), back = !p.hidden && p.contains(document.activeElement);
    p.hidden = true;
    if (back) (popOwner && popOwner.focus ? popOwner : $("list")).focus(); // 焦点还给打开它的按钮；右键菜单还给列表
    popOwner = null;
  }
  // 菜单 / 设置里的键盘：↑↓ ←→ Home End 在按钮间移动，Esc 关掉，Tab 关掉并接着往下走
  function popoverKey(e) {
    var k = e.key, bs = Array.prototype.filter.call($("popover").querySelectorAll("button"), function (b) { return !b.disabled; });
    var n = bs.length, i = bs.indexOf(document.activeElement), j = -1;
    if (k === "Escape") { e.preventDefault(); e.stopPropagation(); closePopover(); return; }
    if (k === "Tab") { closePopover(); return; }
    if (!n) return;
    if (k === "ArrowDown" || k === "ArrowRight") j = (i + 1) % n;
    else if (k === "ArrowUp" || k === "ArrowLeft") j = i <= 0 ? n - 1 : i - 1;
    else if (k === "Home") j = 0;
    else if (k === "End") j = n - 1;
    if (j < 0) return;
    e.preventDefault(); e.stopPropagation();
    bs[j].focus();
  }

  function toast(text, opts) {
    opts = opts || {};
    var t = document.createElement("div");
    t.className = "toast" + (opts.bad ? " bad" : "");
    t.innerHTML = "<span>" + esc(text) + "</span>";
    var gone = function () { t.remove(); if (lastUndo && lastUndo.el === t) lastUndo = null; };
    if (opts.undo || opts.run) {
      var b = document.createElement("button");
      b.textContent = opts.undo ? "撤销（Z）" : opts.action;
      b.onclick = function () { (opts.undo || opts.run)(); gone(); };
      t.appendChild(b);
    }
    if (opts.undo) { if (lastUndo) lastUndo.el.remove(); lastUndo = { run: opts.undo, el: t }; } // 只留最新的一个撤销
    $("toasts").appendChild(t);
    // 带撤销的留 8 秒；鼠标停在上面时暂停计时
    var ms = opts.undo ? 8000 : opts.run ? 6000 : 2600, h, t0;
    var arm = function () { t0 = Date.now(); h = setTimeout(gone, ms); };
    t.onmouseenter = function () { clearTimeout(h); ms = Math.max(1500, ms - (Date.now() - t0)); };
    t.onmouseleave = arm;
    arm();
    return t;
  }

  var modalResolve = null, modalBack = null;
  function confirmBox(title, text, okLabel, danger) {
    $("modalTitle").textContent = title;
    $("modalText").textContent = text;
    $("modalOk").textContent = okLabel || "确定";
    $("modalOk").className = "primary" + (danger ? " danger" : "");
    modalBack = document.activeElement;
    $("modal").hidden = false;
    setTimeout(function () { $("modalOk").focus(); }, 0);
    return new Promise(function (res) { modalResolve = res; });
  }
  function closeModal(v) {
    $("modal").hidden = true; $("modal").firstElementChild.classList.remove("sheet"); if (modalResolve) modalResolve(v); modalResolve = null;
    // 焦点回到打开对话框之前的地方；那里没有（body、已经被删掉的行按钮）就回列表，别停在藏起来的按钮上
    if (modalBack && modalBack !== document.body && modalBack.focus && document.contains(modalBack)) modalBack.focus();
    else $("list").focus();
    modalBack = null;
  }
  // 对话框里：Tab / Shift+Tab 只在对话框的按钮之间转
  function trapModalTab(back) {
    var bs = Array.prototype.filter.call($("modal").querySelectorAll("button"), function (b) { return !b.hidden; });
    var i = bs.indexOf(document.activeElement), n = bs.length;
    if (n) bs[i < 0 ? (back ? n - 1 : 0) : (i + (back ? n - 1 : 1)) % n].focus();
  }

  // ---- 设置
  function seg(key, opts) {
    return '<div class="seg">' + opts.map(function (o) {
      return '<button data-set="' + key + '" data-val="' + o[0] + '" class="' + (S.settings[key] === o[0] ? "on" : "") +
        '" aria-pressed="' + (S.settings[key] === o[0]) + '">' + o[1] + "</button>";
    }).join("") + "</div>";
  }
  function settingsHtml() {
    var sw = { ember: "#F2541B", indigo: "#5146F5", jade: "#0E9F7A", rose: "#E62F6B" };
    var swName = { ember: "珊瑚橙", indigo: "靛蓝", jade: "翡翠绿", rose: "玫红" };
    var h = '<div class="set-row"><div class="menu-label">外观</div>' +
      seg("theme", [["system", "跟随系统"], ["light", "浅色"], ["dark", "深色"]]) + "</div>" +
      '<div class="set-row"><div class="menu-label">强调色</div><div class="swatches">' +
      Object.keys(sw).map(function (k) {
        return '<button class="swatch' + (S.settings.accent === k ? " on" : "") + '" data-set="accent" data-val="' + k + '" style="background:' + sw[k] +
          '" title="' + swName[k] + '" aria-label="' + swName[k] + '" aria-pressed="' + (S.settings.accent === k) + '"></button>';
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
    var cs = closedList();
    if (cs.length) {
      h += '<div class="menu-sep"></div><div class="set-row"><div class="menu-label">已关闭的标签</div></div>' + cs.map(function (p) {
        return '<button class="menu-item" data-reopen="' + esc(p.key) + '"><span class="pdot" style="background:' + pcolor(p.key) + '"></span>' +
          '<span class="mname">' + esc(p.name) + '</span><span class="sub">恢复</span></button>';
      }).join("") + '<div class="menu-sep"></div>'; // 和下面的"快捷键"隔开，不像是同一串
    }
    h += '<button class="menu-item" data-app="shortcuts">' + icon("keyboard") + "快捷键<span class=\"sub\">?</span></button>";
    return h;
  }
  // 重画设置面板；焦点留在同一个位置的按钮上（键盘改设置时不丢焦点）
  function repaintSettings() {
    var p = $("popover"), i = Array.prototype.indexOf.call(p.querySelectorAll("button"), document.activeElement);
    p.innerHTML = settingsHtml();
    var bs = p.querySelectorAll("button");
    if (i >= 0 && bs.length) bs[Math.min(i, bs.length - 1)].focus();
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
        repaintSettings();
        var cd = currentDetail(); // 字号变了，公式重排：只重画正文，选项和没写完的回复不动
        if (cd && shownId() === cd.id) renderBody(cd);
        return;
      }
      if (b.dataset.reopen) { reopenTabs([b.dataset.reopen]); renderAll(); repaintSettings(); return; } // 找回关掉的标签（不改当前选的）
      if (b.dataset.unalias) {
        act({ action: "alias", from: b.dataset.unalias, to: "" }).then(function () { return refreshNow(); })
          .then(function () { repaintSettings(); });
        return;
      }
      var a = b.dataset.app;
      if (a === "shortcuts") { closePopover(); return showShortcuts(); }
      if (a === "autostart" || a === "auto_update") {
        act({ action: a, on: !S.meta[a] }).then(function (r) {
          S.meta[a] = !!r;
          repaintSettings();
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
  function showShortcuts() { // 分四组、宽时两栏；只列键盘（鼠标操作看悬停提示）
    var groups = [["浏览", [["↑ ↓ / J K", "上一条 / 下一条"], ["N / Shift + N", "下一条 / 上一条待决定"], ["Shift + ↑ ↓", "连续勾选"],
        ["/", "搜索"], ["[ ]", "切换项目"], ["F", "只看未处理（开 / 关）"], ["Esc", "退一层"]]],
      ["决定", [["1 – 9", "选第 N 项"], ["Ctrl + Enter", "提交 / 发追问"], ["Enter", "打开 / 写补充说明或追问"], ["R", "标为已处理"]]],
      ["整理", [["E", "归档"], ["U", "已读 / 未读"], ["X", "勾选"], ["Ctrl + A", "全选"], ["Delete", "删除"], ["Z", "撤销"]]],
      ["其他", [["C", "复制 Markdown"], ["Ctrl + P", "导出 PDF"], ["Ctrl + ,", "设置"], ["?", "快捷键"]]]];
    $("modalTitle").textContent = "快捷键";
    $("modal").firstElementChild.classList.add("sheet");
    $("modalText").innerHTML = '<div class="kbd-groups">' + groups.map(function (g) {
      return '<div class="kbd-group"><h4>' + g[0] + '</h4><span class="kbd-table">' + g[1].map(function (r) {
        return "<span>" + r[0].split(" ").map(function (k, i, a) { return a.length > 1 && /^[+/–]$/.test(k) ? k : "<kbd>" + esc(k) + "</kbd>"; }).join(" ") + "</span><span>" + r[1] + "</span>";
      }).join("") + "</span></div>";
    }).join("") + "</div>";
    $("modalOk").textContent = "好的";
    $("modalOk").className = "primary";
    $("modalCancel").hidden = true;
    modalBack = document.activeElement;
    $("modal").hidden = false;
    setTimeout(function () { $("modalOk").focus(); }, 0);
    modalResolve = function () { $("modalCancel").hidden = false; };
  }

  // ---------------------------------------------------------------- 事件
  function bind() {
    paintIcons();
    $("projects").addEventListener("click", function (e) {
      var b = e.target.closest(".ptab");
      if (b && e.target.closest(".pclose")) closeTab(b.dataset.project);
      else if (b) clickTab(b.dataset.project, e.ctrlKey || e.metaKey || e.shiftKey);
    });
    $("projects").addEventListener("mousedown", function (e) { if (e.button === 1 && e.target.closest(".ptab:not(.all)")) e.preventDefault(); }); // 中键：不要进自动滚动
    $("projects").addEventListener("auxclick", function (e) { // 中键点标签：关掉（和浏览器一样）
      var b = e.target.closest(".ptab:not(.all)");
      if (e.button === 1 && b) { e.preventDefault(); closeTab(b.dataset.project); }
    });
    $("projects").addEventListener("contextmenu", function (e) {
      var b = e.target.closest(".ptab");
      if (!b || !b.dataset.project) return;
      e.preventDefault();
      mergeMenu(e.clientX, e.clientY, b.dataset.project, true);
    });
    $("closedBtn").addEventListener("click", openClosedMenu);
    $("projects").addEventListener("wheel", function (e) { // 竖着滚轮也能横着翻标签
      var b = $("projects");
      if (b.scrollWidth <= b.clientWidth || Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return;
      b.scrollLeft += e.deltaY;
      e.preventDefault();
    }, { passive: false });
    $("projects").addEventListener("scroll", ptabFade);
    $("queueBtn").addEventListener("click", function (e) { // 鼠标点的：焦点交给列表，不然之后按 Enter（写补充说明）会再按一次队列条，跳到别的决定
      nextDecision(1);
      if (e.detail) $("list").focus();
    });
    // 鼠标点的：焦点交给列表（不然之后按 Enter / 空格又按了一次这个按钮）
    $("todoBtn").addEventListener("click", function (e) { setTodo(!S.todo); if (e.detail) $("list").focus(); });
    $("handledBtn").addEventListener("click", function (e) { archiveHandled(); if (e.detail) $("list").focus(); });
    $("empty").addEventListener("click", function (e) { if (e.target.closest("#startBtn")) nextDecision(1); });
    $("doneBox").addEventListener("click", function (e) { if (e.target.closest("[data-next]")) nextDecision(1); });
    $("nav").addEventListener("click", function (e) {
      var b = e.target.closest(".tab");
      if (b) setView(b.dataset.view);
    });
    $("list").addEventListener("click", function (e) {
      var more = e.target.closest("[data-more]"); // "另有 N 条在其他视图或项目里"
      if (more) {
        if (more.dataset.more === "all" && S.todo) { S.todo = false; save("todo", ""); } // 查看全部结果：已处理的也要露出来
        S.projects = new Set(); setView(more.dataset.more); applyProjects(); return $("list").focus();
      }
      if (e.target.closest("[data-more-closed]")) { // "另有 N 条在已关闭的标签里"：找回这些标签，去看得到它们的视图
        var ch = closedHits();
        if (S.todo) { S.todo = false; save("todo", ""); } // 找回来的可能已经处理过了：别让"只看未处理"又把它们藏起来
        reopenTabs(ch.keys); S.projects = new Set(); setView(ch.live ? "all" : "archive"); applyProjects();
        return $("list").focus();
      }
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
        (ids.some(function (x) { return S.byId[x] && (S.byId[x].open || S.byId[x].unread); }) ? '<button class="menu-item" data-m="resolve">' + icon("check") + '标为已处理<span class="sub">R</span></button>' : "") +
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
      if (b.dataset.bulk === "read") {
        var was = ids.filter(isUnread);
        dropUndo();
        act({ action: "read", ids: ids }).then(function () {
          S.multi.clear(); toast("已标为已读 " + ids.length + " 条", was.length ? { undo: undoRead(was, false) } : null); return refreshNow(true); // 勾选清了：长轮询先到了也要重画
        });
      }
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
        if (b.dataset.l === "archive_handled") return archiveHandled(); // 和搜索框右边的按钮同一条路
        var req = { action: "read", ids: S.msgs.filter(function (m) { return !m.archived && inScope(m) && m.unread; }).map(function (m) { return m.id; }) };
        dropUndo();
        act(req).then(function (n) {
          toast("已全部标为已读", n ? { undo: undoRead(req.ids, false) } : null);
          refreshNow();
        });
      });
    });
    $("search").addEventListener("input", onSearch);
    $("search").addEventListener("compositionend", onSearch); // 输入法选完字才搜
    $("search").addEventListener("keydown", function (e) {
      if (e.isComposing || e.keyCode === 229) return; // 输入法拼字时的回车 / Esc 是给输入法的
      var k = e.key;
      if (k !== "Escape" && k !== "ArrowDown" && k !== "Enter") return;
      e.preventDefault(); e.stopPropagation(); // 自己处理完，别再触发全局快捷键
      if (k === "Escape") { if ($("search").value) clearSearch(); else $("list").focus(); return; } // 先清字，再离开
      searchFirst();
    });
    $("options").addEventListener("click", function (e) {
      var b = e.target.closest(".opt");
      if (b && !b.disabled) pick(+b.dataset.idx);
    });
    $("replyText").addEventListener("input", function () { var id = shownId(); if (id) saveDraft(id); updateSubmit(); });
    $("submitBtn").addEventListener("click", submit);
    $("fuText").addEventListener("input", function () {
      var d = currentDetail(), t = $("fuText").value;
      if (!canFollow(d) || shownId() !== d.id) return;
      if (t.trim()) S.drafts[d.id] = { idx: null, text: t }; else delete S.drafts[d.id]; // 和决定的草稿放在一起，按消息 id 记
      renderFuState(d);
    });
    $("fuSend").addEventListener("click", sendFollowup);
    $("fuCopy").addEventListener("click", copyFollowup);
    [$("followup"), $("threadRef")].forEach(function (box) { // "Claude 的回答 →" / "原回答（原决定…）"：打开那一条
      box.addEventListener("click", function (e) { var b = e.target.closest("[data-open]"); if (b) window.deskOpen(b.dataset.open); });
    });
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
      if (e.target.closest("#jumpBtn")) $("decide").scrollIntoView({ behavior: reduced() ? "auto" : "smooth", block: "start" });
    });
    $("scroller").addEventListener("scroll", function () {
      $("toolbar").classList.toggle("scrolled", $("scroller").scrollTop > 4);
      updateJump();
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
    $("popover").addEventListener("keydown", popoverKey);
    window.addEventListener("resize", ptabFade);
    document.addEventListener("keydown", onKey);
    window.addEventListener("beforeprint", function () { var d = currentDetail(); if (d && !$("printRoot").firstChild) preparePrint(d); });
    window.addEventListener("afterprint", function () { $("printRoot").innerHTML = ""; });
  }

  function selectAll() {
    S.multi = new Set(S.visible);
    renderList();
  }

  // 窄窗口（≤720px）阅读页铺满整个窗口：Esc / Backspace 回到列表
  function narrow() { return !!(window.matchMedia && matchMedia("(max-width: 720px)").matches); }
  function backToList() { // 光标留在刚看的那条：接着 ↓ 就是下一条
    S.cursor = S.current; S.current = null; renderList(); renderReader(); $("list").focus();
    var el = rowEl(S.cursor); if (el) el.scrollIntoView({ block: "nearest" });
  }
  function findBox() { if (narrow() && S.current) backToList(); $("search").focus(); } // 窄窗口的阅读页盖住了搜索框：先回到列表，不然字打进看不见的框里
  // Esc 一次只退一层：菜单 → 窄窗口的阅读页 → 搜索 → 勾选 → 项目筛选
  function escLayer() {
    if (!$("popover").hidden) return closePopover();
    if (narrow() && S.current) return backToList();
    if (S.query || $("search").value) return clearSearch();
    if (S.multi.size) { S.multi.clear(); return renderList(); }
    if (S.projects.size) { S.projects = new Set(); applyProjects(); }
  }

  function onKey(e) {
    if (e.isComposing || e.keyCode === 229) return; // 输入法正在拼字
    if (!$("modal").hidden) {
      var onBtn = $("modal").contains(document.activeElement) && document.activeElement.tagName === "BUTTON";
      if (e.key === "Escape") closeModal(false);
      else if (e.key === "Tab") { e.preventDefault(); trapModalTab(e.shiftKey); }
      else if (e.key === "Enter" && !onBtn) { e.preventDefault(); closeModal(true); } // 焦点在按钮上：回车按的就是那个按钮
      return;
    }
    var typing = /^(INPUT|TEXTAREA)$/.test(document.activeElement && document.activeElement.tagName);
    var k = e.key;
    if ((e.ctrlKey || e.metaKey) && k.toLowerCase() === "p") { e.preventDefault(); pdf(); return; }
    if ((e.ctrlKey || e.metaKey) && k.toLowerCase() === "f") { e.preventDefault(); findBox(); $("search").select(); return; }
    if ((e.ctrlKey || e.metaKey) && k === ",") { e.preventDefault(); openSettings(); return; }
    if ((e.ctrlKey || e.metaKey) && k === "Enter") { // 决定还没回复：焦点在哪都能提交；别的（含回复过的决定）：发追问
      var dd = currentDetail();
      if (dd && dd.kind === "decision" && !dd.response) { e.preventDefault(); submit(); }
      else if (canFollow(dd)) { e.preventDefault(); sendFollowup(); }
      return;
    }
    if (typing) return;
    if ((e.ctrlKey || e.metaKey) && k.toLowerCase() === "a") { e.preventDefault(); selectAll(); return; }
    if ((e.ctrlKey || e.metaKey) && k.toLowerCase() === "c") {
      if (!String(window.getSelection())) { e.preventDefault(); copy("md"); }
      return;
    }
    if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && k.toLowerCase() === "z") { e.preventDefault(); undoLast(); return; }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (k === "Escape") { escLayer(); return; }
    if (k === "Backspace" && narrow() && S.current) { e.preventDefault(); backToList(); return; }
    if (k === "z" || k === "Z") { undoLast(); return; }
    if (k === "ArrowDown" || k === "j" || k === "J") { e.preventDefault(); move(1, e.shiftKey); return; }
    if (k === "ArrowUp" || k === "k" || k === "K") { e.preventDefault(); move(-1, e.shiftKey); return; }
    if (k === "/") { e.preventDefault(); findBox(); return; }
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
    if (k === "n" || k === "N") { nextDecision(e.shiftKey ? -1 : 1); return; }
    if (k === "?") { showShortcuts(); return; }
    if (k === "e" || k === "E") { doArchive(targets()); return; }
    if (k === "Delete" || k === "#") { doDelete(targets()); return; }
    if (k === "u" || k === "U") { doToggleRead(targets()); return; }
    if (k === "r" || k === "R") { askResolve(targets()); return; }
    if (k === "f" || k === "F") { if (S.view === "archive") toast("归档里不分未处理"); else setTodo(!S.todo); return; }
    if ((k === "x" || k === "X") && S.current) { toggleCheck(S.current, e.shiftKey); return; }
    if (k === "c" || k === "C") { copy("md"); return; }
    if (/^[1-9]$/.test(k)) { pick(+k - 1); revealDecide(); return; }
    if (k === "Enter") {
      if (document.activeElement && document.activeElement.closest && document.activeElement.closest("button")) return; // 让按钮自己响应
      if (narrow() && !S.current && S.cursor && S.visible.indexOf(S.cursor) >= 0) { e.preventDefault(); select(S.cursor, { scroll: true }); return; } // 窄窗口列表页：打开光标那条
      var d = currentDetail();
      if (d && d.kind === "decision" && !d.response) { e.preventDefault(); $("replyText").focus(); }
      else if (canFollow(d)) { e.preventDefault(); $("fuText").focus(); } // 别的：写追问
    }
  }

  // ---------------------------------------------------------------- 启动
  if (!VIEWS.some(function (v) { return v.id === S.view; })) S.view = "all";
  bind();
  renderNav();
  renderFoot();
  poll();
  setInterval(tickWaits, 60000); // 等待时间每分钟走一次
  // 外部（托盘 / 通知点击）要求打开某条消息
  window.deskOpen = function (id, view) {
    var go = function () {
      var c = S.allById[id];
      if (c && !S.byId[id] && !S.gone[id] && closedOf(c)) { reopenTabs([tabKey(c)]); renderAll(); } // 关掉的标签里的（点了旧通知）：先找回标签
      if (!S.byId[id]) return false;
      var m = S.byId[id];
      if (!inScope(m)) { S.projects = new Set([tabKey(m)]); applyProjects(); }
      if (!inView(m, S.view)) setView(view || (m.archived ? "archive" : m.kind === "decision" ? "decide" : m.kind === "answer" ? "answer" : "all"));
      if (S.query) { $("search").value = ""; S.query = ""; S.searchIds = null; renderAll(); }
      select(id, { scroll: true });
      return true;
    };
    if (!go()) refreshNow().then(go);
  };
  window.deskTest = { setProject: setProject, S: S, select: select, setView: setView, pick: pick, submit: submit, copy: copy, markdownOf: markdownOf, itemHtml: itemHtml };
})();
