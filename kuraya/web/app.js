const PACK_FIELDS = {{PACK_FIELDS}};
const LIB_BASE = {{LIB_BASE}};
const PATH_SEP = {{PATH_SEP}};

const DATA = {{DATA_JSON}}.map(row => {
  const r = {};
  PACK_FIELDS.forEach((f, i) => { r[f] = row[i]; });
  const dir = r.dir || r.code;
  return {
    actress_folder: r.folder,
    code: r.code,
    studio: r.studio,
    director: r.director,
    date: r.date,
    runtime: r.runtime,
    actors: r.actors || r.folder,
    poster_url: r.poster
      ? [r.folder, dir, r.poster].map(encodeURIComponent).join("/") : "",
    video_path: [LIB_BASE, r.folder, dir, r.video].join(PATH_SEP),
    added_ts: r.added,
  };
});

// "protocol" 时点封面直接唤起播放器；"copy" 时只能复制路径，
// 因为注册自定义协议要写注册表，非 Windows 平台没有这条路
const PLAY_MODE = "{{PLAY_MODE}}";

// i18n.js 在本文件之前注入：t()/UI_LANG 已就绪（gallery.render 拼接顺序保证）

const grid = document.getElementById("grid");
const search = document.getElementById("search");
const clearBtn = document.getElementById("clearBtn");
const countEl = document.getElementById("count");
const chipsEl = document.getElementById("chips");
const pillsEl = document.getElementById("pills");
const sortWrap = document.getElementById("sortWrap");
const sortBtn = document.getElementById("sortBtn");
const sortLabel = document.getElementById("sortLabel");
const sortMenu = document.getElementById("sortMenu");
const sortOpts = [...sortMenu.querySelectorAll(".select-opt")];

const SORT_NAMES = {
  date_desc: t("sort.date_desc"),
  date_asc: t("sort.date_asc"),
  added_desc: t("sort.added_desc"),
};
const DEFAULT_SORT = "date_desc";
let sortKey = DEFAULT_SORT;

// 分批渲染：首屏只建 PAGE 张卡片，滚动接近底部时追加下一批，
// 避免大库一次性构建数千 DOM 节点卡死主线程
const PAGE = 60;
const FULL_RENDER = !("IntersectionObserver" in window);
let result = [];     // 当前筛选/排序结果：render 算一次、loadMore 复用
let rendered = 0;

function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// 每部影片拆分出参演女优名单（多人合集用「、」分隔）
function actorList(it) {
  return it.actors.split("、").map(s => s.trim()).filter(Boolean);
}

const NEW_DAYS = 7;
function isNew(it) {
  return it.added_ts > Date.now() / 1000 - NEW_DAYS * 86400;
}

// ---------- 筛选维度 ----------
// 三个维度统一计算计数后再过滤：没有任何值的维度（如整库无导演）
// 直接不出现，避免「导演 0」这种点开也是空的按钮
const ALL_DIMS = [
  { key: "actor", label: t("dim.actor"), of: it => actorList(it) },
  { key: "studio", label: t("dim.studio"), of: it => it.studio ? [it.studio] : [] },
  { key: "director", label: t("dim.director"), of: it => it.director ? [it.director] : [] },
];

for (const dim of ALL_DIMS) {
  const counts = new Map();
  DATA.forEach(it => dim.of(it).forEach(v =>
    counts.set(v, (counts.get(v) || 0) + 1)));
  dim.values = [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "ja"));
}

const DIMS = ALL_DIMS.filter(d => d.values.length > 0);

let activeDim = "actor";
const active = { actor: null, studio: null, director: null };

const SEPARATORS = /[\s\-_.·・]/g;
const squash = s => s.replace(SEPARATORS, "");
DATA.forEach(it => {
  it._fields = [it.code, it.actors, it.studio || "", it.director || "",
                it.actress_folder].map(f => f.toLowerCase());
  it._squashed = it._fields.map(squash);
});

function sortData(list, key) {
  const arr = [...list];
  switch (key) {
    case "date_desc": arr.sort((a,b) => (b.date||"").localeCompare(a.date||"")); break;
    case "date_asc": arr.sort((a,b) => (a.date||"").localeCompare(b.date||"")); break;
    case "added_desc": arr.sort((a,b) => b.added_ts - a.added_ts); break;
  }
  return arr;
}

function visibleList() {
  const q = search.value.trim().toLowerCase();
  let list = DATA;

  for (const dim of DIMS) {
    const v = active[dim.key];
    if (v) list = list.filter(it => dim.of(it).includes(v));
  }
  if (q) {
    const qs = squash(q);
    list = list.filter(it =>
      it._fields.some(f => f.includes(q)) ||
      (qs && it._squashed.some(f => f.includes(qs))));
  }
  return sortData(list, sortKey);
}

// 播放由 kuraya: 协议交给主程序处理。
// 注意不能写成 kuraya://，浏览器会把后面的内容当主机名解析而破坏路径。
function playUrl(it) {
  return "kuraya:" + encodeURIComponent(it.video_path);
}

// 复制模式下的兜底：把路径放进剪贴板，用户粘到播放器或终端里去。
// 浏览器不允许网页直接启动本机程序，没有协议就只能到这一步为止。
function copyPath(it, card) {
  const hint = card.querySelector(".card-hint");
  const done = ok => {
    if (hint) hint.textContent = ok ? t("copied") : t("copyFailed");
    card.classList.add(ok ? "copied" : "copy-failed");
    setTimeout(() => card.classList.remove("copied", "copy-failed"), 1400);
  };

  // 选中一个临时文本框再执行复制。file:// 打开的页面不算安全上下文，
  // clipboard API 在那里根本不可用，而片库页面正是双击 index.html 打开的
  const legacy = () => {
    const box = document.createElement("textarea");
    box.value = it.video_path;
    box.style.position = "fixed";
    box.style.opacity = "0";
    document.body.appendChild(box);
    box.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
    document.body.removeChild(box);
    return ok;
  };

  if (navigator.clipboard && window.isSecureContext) {
    // 被拒是常事——缺少用户激活、权限被关都会走到这里，此时还有老办法可试，
    // 不能直接报失败
    navigator.clipboard.writeText(it.video_path)
      .then(() => done(true), () => done(legacy()));
    return;
  }
  done(legacy());
}

function cardEl(it, i) {
  const card = document.createElement("a");
  card.className = "card";
  if (PLAY_MODE === "protocol") {
    card.href = playUrl(it);
  } else {
    card.href = "#";
    card.title = it.video_path;
    card.addEventListener("click", ev => {
      ev.preventDefault();
      copyPath(it, card);
    });
  }
  // 逐个错开出现，最多延迟到 24 个，避免长列表末尾等待过久
  card.style.animationDelay = Math.min(i, 24) * 22 + "ms";
  const cover = it.poster_url
    ? `<img src="${esc(it.poster_url)}" loading="lazy" alt="">`
    : `<div class="no-cover">NO COVER</div>`;
  const badge = isNew(it) ? `<div class="badge-new">NEW</div>` : "";
  const link = (dim, v) =>
    `<span class="meta-link" data-dim="${dim}" data-val="${esc(v)}">${esc(v)}</span>`;
  const actorsHtml = actorList(it).map(n => link("actor", n))
    .join('<span class="actor-sep">、</span>');
  const subParts = [];
  if (it.studio) {
    subParts.push(`<span class="studio meta-link" data-dim="studio"`
      + ` data-val="${esc(it.studio)}">${esc(it.studio)}</span>`);
  }
  if (it.director) subParts.push(link("director", it.director));
  if (it.date) subParts.push(`<span class="date">${esc(it.date)}</span>`);

  card.innerHTML = `
    <div class="cover-wrap">
      ${cover}
      ${badge}
      <div class="play"><span>
        ${PLAY_MODE === "protocol"
          ? `<svg width="13" height="15" viewBox="0 0 13 15" fill="#fff"><path d="M0 0l13 7.5L0 15z"/></svg>`
          : `<svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="#fff" stroke-width="1.4">
               <rect x="5.5" y="5.5" width="9" height="9" rx="1.6"/>
               <path d="M10.5 5.5v-3a1 1 0 0 0-1-1h-7a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h3"/>
             </svg>`}
      </span></div>
      ${PLAY_MODE === "protocol" ? "" : `<div class="card-hint"></div>`}
    </div>
    <div class="meta">
      <div class="code">${esc(it.code)}</div>
      <div class="actors">${actorsHtml}</div>
      <div class="sub">${subParts.join('<span class="dot"></span>')}</div>
    </div>
  `;
  card.querySelectorAll(".meta-link").forEach(el => {
    el.addEventListener("click", e => {
      e.preventDefault();
      e.stopPropagation();
      setFilter(el.dataset.dim, el.dataset.val);
    });
  });
  return card;
}

function appendCards(cards) {
  const frag = document.createDocumentFragment();
  cards.forEach(c => frag.appendChild(c));
  grid.appendChild(frag);
}

function appendRange(from, count) {
  const batch = result.slice(from, from + count);
  rendered = from + batch.length;
  appendCards(batch.map((it, i) => cardEl(it, from + i)));
}

function loadMore() {
  if (rendered >= result.length) return;
  appendRange(rendered, PAGE);
}

function render() {
  result = visibleList();
  rendered = FULL_RENDER ? Infinity : PAGE;
  countEl.textContent = dirty() ? `${result.length} / ${DATA.length}` : "";
  grid.innerHTML = "";

  if (!result.length) {
    grid.innerHTML = `<div class="empty">${t("empty")}</div>`;
    return;
  }
  appendRange(0, rendered);
}

// 滚动接近底部时追加下一批；旧浏览器无 IntersectionObserver 时
// 走 FULL_RENDER 全量渲染，行为与分批前一致
if (!FULL_RENDER) {
  const sentinel = document.getElementById("sentinel");
  if (sentinel) {
    const observer = new IntersectionObserver(entries => {
      if (entries[0].isIntersecting) loadMore();
    }, { rootMargin: "300px" });
    observer.observe(sentinel);
  }
}


function updateClearBtn() {
  clearBtn.classList.toggle("show", search.value.length > 0);
}

// ---------- 排序下拉 ----------
function setSort(key) {
  sortKey = key;
  sortLabel.textContent = SORT_NAMES[key];
  sortOpts.forEach(opt =>
    opt.setAttribute("aria-selected", String(opt.dataset.value === key)));
  closeSort();
  buildPills();
  render();
}

function openSort() {
  sortWrap.classList.add("open");
  sortBtn.setAttribute("aria-expanded", "true");
  const cur = sortOpts.find(opt => opt.dataset.value === sortKey);
  (cur || sortOpts[0]).focus();
}

function closeSort() {
  sortWrap.classList.remove("open");
  sortBtn.setAttribute("aria-expanded", "false");
}

sortBtn.addEventListener("click", () => {
  sortWrap.classList.contains("open") ? closeSort() : openSort();
});
sortBtn.addEventListener("keydown", e => {
  if (["Enter", " ", "ArrowDown", "ArrowUp"].includes(e.key)) {
    e.preventDefault();
    openSort();
  }
});
sortOpts.forEach((opt, i) => {
  opt.addEventListener("click", () => setSort(opt.dataset.value));
  opt.addEventListener("keydown", e => {
    const next = (i + sortOpts.length + (e.key === "ArrowUp" ? -1 : 1))
      % sortOpts.length;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      sortOpts[next].focus();
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setSort(opt.dataset.value);
    } else if (e.key === "Escape") {
      e.preventDefault();
      closeSort();
      sortBtn.focus();
    }
  });
});
// 点击面板外部收起
document.addEventListener("click", e => {
  if (!sortWrap.contains(e.target)) closeSort();
});
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && sortWrap.classList.contains("open")) {
    closeSort();
    sortBtn.focus();
  }
});

search.addEventListener("input", () => {
  updateClearBtn();
  buildPills();
  render();
});
clearBtn.addEventListener("click", () => { resetAll(); search.focus(); });
document.addEventListener("keydown", (e) => {
  if (e.key === "/" && document.activeElement !== search) { e.preventDefault(); search.focus(); }
  if (e.key === "Escape" && document.activeElement === search) {
    search.value = "";
    search.blur();
    updateClearBtn();
    buildPills();
    render();
  }
});

buildChips();
buildPills();
render();

// 窗口/容器宽度变化时重测筛选行。旧浏览器（与无 IntersectionObserver 的
// FULL_RENDER 回退同一批老环境）通常也没有 ResizeObserver——首屏测量已
// 在 buildChips 里完成，没有它只损失窗口变化后的重排，不致命
if ("ResizeObserver" in window) {
  let lastChipsW = chipsEl.clientWidth;
  new ResizeObserver(() => {
    if (chipsEl.clientWidth === lastChipsW) return;
    lastChipsW = chipsEl.clientWidth;
    buildChips();
  }).observe(chipsEl);
}
