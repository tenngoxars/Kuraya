const DATA = {{DATA_JSON}};

// "protocol" 时点封面直接唤起播放器；"copy" 时只能复制路径，
// 因为注册自定义协议要写注册表，非 Windows 平台没有这条路
const PLAY_MODE = "{{PLAY_MODE}}";

const grid = document.getElementById("grid");
const search = document.getElementById("search");
const clearBtn = document.getElementById("clearBtn");
const countEl = document.getElementById("count");
const sortSel = document.getElementById("sortSel");
const chipsEl = document.getElementById("chips");

let activeActor = null;

// 每部影片拆分出参演女优名单（多人合集用「、」分隔）
function actorList(it) {
  return it.actors.split("、").map(s => s.trim()).filter(Boolean);
}

// 顶部统计（按去重后的演员名计）
const allActorNames = new Set();
DATA.forEach(d => actorList(d).forEach(n => allActorNames.add(n)));
document.getElementById("statActress").textContent = allActorNames.size;
document.getElementById("statStudio").textContent = new Set(DATA.map(d => d.studio).filter(Boolean)).size;

// 演员筛选（只展示作品数 >= 2 的，避免一长串单部演员刷屏）
const counts = {};
DATA.forEach(d => actorList(d).forEach(n => { counts[n] = (counts[n] || 0) + 1; }));
const topActors = Object.entries(counts)
  .filter(([, n]) => n >= 2)
  .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], "ja"));

function setActiveActor(name) {
  activeActor = (activeActor === name) ? null : name;
  buildChips();
  render();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function buildChips() {
  chipsEl.innerHTML = "";
  const all = document.createElement("button");
  all.className = "chip" + (activeActor === null ? " on" : "");
  all.textContent = "全部";
  all.onclick = () => { activeActor = null; buildChips(); render(); };
  chipsEl.appendChild(all);

  for (const [name, n] of topActors) {
    const b = document.createElement("button");
    b.className = "chip" + (activeActor === name ? " on" : "");
    b.innerHTML = `${name}<span class="n">${n}</span>`;
    b.onclick = () => setActiveActor(name);
    chipsEl.appendChild(b);
  }
}

function sortData(list, key) {
  const arr = [...list];
  switch (key) {
    case "date_desc": arr.sort((a,b) => (b.date||"").localeCompare(a.date||"")); break;
    case "date_asc": arr.sort((a,b) => (a.date||"").localeCompare(b.date||"")); break;
    case "added_desc": arr.sort((a,b) => b.added_ts - a.added_ts); break;
  }
  return arr;
}

// 播放由 kuraya: 协议交给主程序处理。
// 注意不能写成 kuraya://，浏览器会把后面的内容当主机名解析而破坏路径。
function playUrl(it) {
  return "kuraya:" + encodeURIComponent(it.video_path);
}

// 复制模式下的兜底：把路径放进剪贴板，用户粘到播放器或终端里去。
// 浏览器不允许网页直接启动本机程序，没有协议就只能到这一步为止。
function copyPath(it, card) {
  const done = ok => {
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

function render() {
  const q = search.value.trim().toLowerCase();
  let list = DATA;

  if (activeActor) list = list.filter(it => actorList(it).includes(activeActor));
  if (q) {
    list = list.filter(it =>
      it.actors.toLowerCase().includes(q) ||
      it.code.toLowerCase().includes(q) ||
      (it.studio||"").toLowerCase().includes(q) ||
      it.actress_folder.toLowerCase().includes(q)
    );
  }
  list = sortData(list, sortSel.value);

  countEl.textContent = `${list.length} / ${DATA.length}`;
  grid.innerHTML = "";

  if (!list.length) {
    grid.innerHTML = `<div class="empty">没有找到匹配的影片</div>`;
    return;
  }

  list.forEach((it, i) => {
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
      ? `<img src="${it.poster_url}" loading="lazy" alt="">`
      : `<div class="no-cover">NO COVER</div>`;
    const actorsHtml = actorList(it)
      .map(name => `<span class="actor-link" data-actor="${name}">${name}</span>`)
      .join('<span class="actor-sep">、</span>');
    card.innerHTML = `
      <div class="cover-wrap">
        ${cover}
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
        <div class="code">${it.code}</div>
        <div class="actors">${actorsHtml}</div>
        <div class="sub">
          ${it.studio ? `<span class="studio">${it.studio}</span><span class="dot"></span>` : ""}
          <span class="date">${it.date || ""}${it.runtime ? " · " + it.runtime + "min" : ""}</span>
        </div>
      </div>
    `;
    card.querySelectorAll(".actor-link").forEach(el => {
      el.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        setActiveActor(el.dataset.actor);
      });
    });
    grid.appendChild(card);
  });
}

function updateClearBtn() {
  clearBtn.classList.toggle("show", search.value.length > 0);
}

// 清空按钮：清空搜索词 + 取消演员筛选 + 恢复默认排序，回到首页初始状态
function resetToHome() {
  search.value = "";
  activeActor = null;
  sortSel.value = "date_desc";
  updateClearBtn();
  buildChips();
  render();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

search.addEventListener("input", () => { render(); updateClearBtn(); });
clearBtn.addEventListener("click", () => { resetToHome(); search.focus(); });
sortSel.addEventListener("change", render);
document.addEventListener("keydown", (e) => {
  if (e.key === "/" && document.activeElement !== search) { e.preventDefault(); search.focus(); }
  if (e.key === "Escape" && document.activeElement === search) { search.value = ""; search.blur(); render(); updateClearBtn(); }
});

buildChips();
render();
