// ---------- 界面语言：跟随浏览器语言，简中原文 / 繁中 / 英文 ----------
// 独立文件与 app.js 同块注入（gallery.render 先拼 i18n.js 再拼 app.js），
// t()/UI_LANG 是 app.js 的前置依赖，勿调换顺序
const I18N = {
  "zh-CN": {
    "search.placeholder": "搜索演员 · 番号 · 厂商 · 导演",
    "sort.by": "排序方式",
    "sort.date_desc": "发行日期 · 新到旧",
    "sort.date_asc": "发行日期 · 旧到新",
    "sort.added_desc": "入库时间 · 新到旧",
    "stat.movies": "部影片",
    "dim.actor": "演员",
    "dim.studio": "厂商",
    "dim.director": "导演",
    "chips.all": "全部",
    "more": "更多 {n}",
    "searchIn": "搜索{dim}",
    "noMatch": "没有匹配的{dim}",
    "moreHint": "还有 {n} 项未列出，输入关键词过滤",
    "empty": "没有找到匹配的影片",
    "clear": "清空",
    "copied": "已复制路径",
    "copyFailed": "复制失败，路径见悬停提示",
  },
  "zh-TW": {
    "search.placeholder": "搜尋演員 · 番號 · 廠商 · 導演",
    "sort.by": "排序方式",
    "sort.date_desc": "發行日期 · 新到舊",
    "sort.date_asc": "發行日期 · 舊到新",
    "sort.added_desc": "入庫時間 · 新到舊",
    "stat.movies": "部影片",
    "dim.actor": "演員",
    "dim.studio": "廠商",
    "dim.director": "導演",
    "chips.all": "全部",
    "more": "更多 {n}",
    "searchIn": "搜尋{dim}",
    "noMatch": "沒有相符的{dim}",
    "moreHint": "還有 {n} 項未列出，輸入關鍵詞過濾",
    "empty": "沒有找到相符的影片",
    "clear": "清空",
    "copied": "已複製路徑",
    "copyFailed": "複製失敗，路徑見懸停提示",
  },
  "en": {
    "search.placeholder": "Search actors · numbers · studios · directors",
    "sort.by": "Sort by",
    "sort.date_desc": "Release Date · Newest First",
    "sort.date_asc": "Release Date · Oldest First",
    "sort.added_desc": "Date Added · Newest First",
    "stat.movies": "movies",
    "dim.actor": "actors",
    "dim.studio": "studios",
    "dim.director": "directors",
    "chips.all": "All",
    "more": "{n} more",
    "searchIn": "Search {dim}",
    "noMatch": "No matching {dim}",
    "moreHint": "{n} more items — type to filter",
    "empty": "No matching movies",
    "clear": "Clear",
    "copied": "Path copied",
    "copyFailed": "Copy failed — see tooltip",
  },
};

// 繁体地区标记由 gallery.py 从 kuraya.i18n 注入，判定规则只有一份
const TRADITIONAL_CODES = {{TRADITIONAL_CODES}};

const LANG_KEY = "kuraya.lang";
const HASH = new URLSearchParams(location.hash.slice(1));

function savedLang() {
  try { return localStorage.getItem(LANG_KEY); } catch (e) { return null; }
}

const UI_LANG = (() => {
  const picked = HASH.get("lang") || savedLang();
  if (picked && I18N[picked]) return picked;
  const lang = (navigator.language || "").toLowerCase();
  if (!lang.startsWith("zh")) return "en";
  return TRADITIONAL_CODES.some(p => lang.startsWith(p))
    ? "zh-TW" : "zh-CN";
})();

function t(key, vars) {
  let out = (I18N[UI_LANG] && I18N[UI_LANG][key]) || I18N["zh-CN"][key] || key;
  if (vars) for (const k in vars) out = out.replace("{" + k + "}", vars[k]);
  return out;
}

function setLang(code) {
  try { localStorage.setItem(LANG_KEY, code); } catch (e) { /* 存不住就只靠 hash */ }
  HASH.set("lang", code);
  location.hash = HASH.toString();
  location.reload();
}

[["zh-CN", "简体"], ["zh-TW", "繁體"], ["en", "EN"]].forEach(([code, label], i) => {
  const box = document.getElementById("langs");
  if (!box) return;
  if (i) {
    const rule = document.createElement("span");
    rule.className = "lang-rule";
    box.appendChild(rule);
  }
  const b = document.createElement("button");
  b.className = "lang" + (code === UI_LANG ? " on" : "");
  b.textContent = label;
  b.onclick = () => setLang(code);
  box.appendChild(b);
});

// 把模板里的静态文案换成当前语言
document.querySelectorAll("[data-i18n]").forEach(el => {
  el.textContent = t(el.dataset.i18n);
});
document.querySelectorAll("[data-i18n-placeholder]").forEach(el => {
  el.placeholder = t(el.dataset.i18nPlaceholder);
});
document.querySelectorAll("[data-i18n-aria]").forEach(el => {
  el.setAttribute("aria-label", t(el.dataset.i18nAria));
});
