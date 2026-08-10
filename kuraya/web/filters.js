// ---------- 筛选行：维度切换 + 宽度自适应的 chips + 更多面板 ----------
// 独立文件与 i18n.js、state.js、delete.js、app.js 同块注入（gallery.render
// 顺序：i18n.js → state.js → delete.js → app.js → filters.js）。依赖
// DIMS/active/activeDim/chipsEl/pillsEl 等
// app.js 顶层的定义；本文件顶层不要放会立即执行的 const（app.js 末尾
// 的 buildChips() 调用先于本文件执行到，const 会落在 TDZ 抛错）

function buildChips() {
  // 预留给「更多 N ▾」按钮的宽度余量，chips 溢出即收进面板
  const MORE_RESERVE = 118;
  // 空库（或全部维度无值）时没有可筛的东西，筛选行整体留空
  if (!DIMS.length) { chipsEl.innerHTML = ""; return; }
  const dim = DIMS.find(d => d.key === activeDim);
  chipsEl.innerHTML = "";

  const dims = document.createElement("div");
  dims.className = "dims";
  for (const d of DIMS) {
    const b = document.createElement("button");
    b.className = "dim" + (d.key === activeDim ? " on" : "");
    b.innerHTML = `${esc(d.label)}<span class="c">${d.values.length}</span>`;
    b.onclick = () => { activeDim = d.key; buildChips(); };
    dims.appendChild(b);
  }
  chipsEl.appendChild(dims);
  const rule = document.createElement("span");
  rule.className = "dim-rule";
  chipsEl.appendChild(rule);

  const cur = active[dim.key];
  const all = document.createElement("button");
  all.className = "chip" + (cur === null ? " on" : "");
  all.textContent = t("chips.all");
  all.onclick = () => setFilter(dim.key, null);
  chipsEl.appendChild(all);

  const chip = ([name, n]) => {
    const b = document.createElement("button");
    b.className = "chip" + (cur === name ? " on" : "");
    b.innerHTML = `${esc(name)}<span class="n">${n}</span>`;
    b.onclick = () => setFilter(dim.key, name);
    return b;
  };

  const padRight = parseFloat(getComputedStyle(chipsEl).paddingRight);
  const hardEdge = chipsEl.getBoundingClientRect().right - padRight;
  const softEdge = hardEdge - MORE_RESERVE;

  let shown = 0;
  for (const [i, entry] of dim.values.entries()) {
    const b = chip(entry);
    chipsEl.appendChild(b);
    const edge = (i === dim.values.length - 1) ? hardEdge : softEdge;
    if (b.getBoundingClientRect().right > edge) { b.remove(); break; }
    shown++;
  }

  const rest = dim.values.slice(shown);
  if (rest.length) chipsEl.appendChild(moreEl(dim, rest));
}

function moreEl(dim, rest) {
  const wrap = document.createElement("div");
  wrap.className = "more-wrap";
  wrap.innerHTML = `
    <button class="chip more" type="button">${t("more", {n: rest.length})} ▾</button>
    <div class="more-panel">
      <input class="more-search" type="text"
             placeholder="${esc(t("searchIn", {dim: dim.label}))}">
      <div class="more-list"></div>
    </div>`;
  const btn = wrap.querySelector(".more");
  const box = wrap.querySelector(".more-search");
  const list = wrap.querySelector(".more-list");

  const fill = () => {
    const q = box.value.trim().toLowerCase();
    const source = q ? dim.values : rest;
    // 与主搜索同一套规则：分隔符归一化后匹配，ABC-001 与 abc001 互通；
    // 空 sq（纯分隔符查询）必须跳过归一化分支，否则 includes("") 恒真
    const sq = squash(q);
    const hits = source.filter(([n]) => !q
      || n.toLowerCase().includes(q)
      || (sq && squash(n.toLowerCase()).includes(sq)));
    list.innerHTML = "";
    if (!hits.length) {
      list.innerHTML = `<div class="more-empty">${esc(t("noMatch", {dim: dim.label}))}</div>`;
      return;
    }
    for (const [name, n] of hits.slice(0, 300)) {
      const o = document.createElement("button");
      o.className = "more-opt";
      o.innerHTML = `<span>${esc(name)}</span><span class="n">${n}</span>`;
      o.onclick = () => { setFilter(dim.key, name); closeMore(); };
      list.appendChild(o);
    }
    // 超出渲染上限的条目不是不可达：输入关键词即从全量过滤，此处只是提示
    if (hits.length > 300) {
      const hint = document.createElement("div");
      hint.className = "more-empty";
      hint.textContent = t("moreHint", {n: hits.length - 300});
      list.appendChild(hint);
    }
  };

  btn.onclick = e => {
    e.stopPropagation();
    const open = wrap.classList.toggle("open");
    if (!open) return;
    box.value = "";
    fill();
    void wrap.offsetHeight;
    box.focus();
  };
  box.oninput = fill;
  box.onkeydown = e => {
    if (e.key === "Escape") { closeMore(); btn.focus(); }
  };
  wrap.onclick = e => e.stopPropagation();
  return wrap;
}

function closeMore() {
  document.querySelectorAll(".more-wrap.open")
    .forEach(w => w.classList.remove("open"));
}
document.addEventListener("click", closeMore);

// ---------- 已激活的筛选 ----------
function dirty() {
  return !!search.value.trim() || DIMS.some(d => active[d.key])
    || sortKey !== DEFAULT_SORT;
}

function rememberBrowsePosition(force = false) {
  if (browseSnapshot === null && (force || !dirty())) {
    browseSnapshot = {scrollY: window.scrollY, rendered};
  }
}

function scrollAfterFilterChange() {
  if (dirty()) {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
}

function buildPills() {
  pillsEl.innerHTML = "";
  for (const dim of DIMS) {
    const v = active[dim.key];
    if (!v) continue;
    const b = document.createElement("button");
    b.className = "pill";
    b.innerHTML = `<span class="k">${esc(dim.label)}</span>${esc(v)}`
      + `<span class="x">×</span>`;
    b.onclick = () => setFilter(dim.key, null);
    pillsEl.appendChild(b);
  }
  if (dirty()) {
    const r = document.createElement("button");
    r.className = "reset";
    r.innerHTML = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" stroke-width="2" stroke-linecap="round">
      <path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/></svg>${esc(t("clear"))}`;
    r.onclick = resetAll;
    pillsEl.appendChild(r);
  }
}

function setFilter(key, value) {
  rememberBrowsePosition();
  active[key] = (active[key] === value) ? null : value;
  buildChips();
  buildPills();
  render();
  scrollAfterFilterChange();
}

function resetAll() {
  if (dirty()) rememberBrowsePosition(true);
  search.value = "";
  DIMS.forEach(d => { active[d.key] = null; });
  sortKey = DEFAULT_SORT;
  sortLabel.textContent = SORT_NAMES[sortKey];
  sortOpts.forEach((opt, i) =>
    opt.setAttribute("aria-selected", String(i === 0)));
  updateClearBtn();
  buildChips();
  buildPills();
  render();
}
