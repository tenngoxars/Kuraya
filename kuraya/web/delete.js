const confirmModal = document.getElementById("confirmModal");
const confirmClose = document.getElementById("confirmClose");
const confirmCancel = document.getElementById("confirmCancel");
const confirmSubmit = document.getElementById("confirmSubmit");
const confirmBackdrop = confirmModal.querySelector(".confirm-backdrop");
const confirmDescription = document.getElementById("confirmDescription");
const confirmNote = document.getElementById("confirmNote");
const confirmTarget = document.getElementById("confirmTarget");
const pageContent = document.getElementById("pageContent");

const DELETE_KEY = "kuraya.delete.pending";
const DELETE_HASH_KEY = "kuraya-delete";
const DELETE_TIMEOUT = 60000;
const DELETE_RETRY_DELAYS = [250, 500, 1000, 2000, 4000, 8000, 10000];
let pendingDelete = null;
let deleteFocus = null;
let deleteRecoveryTimer = null;
let deleteRestoreItem = null;

function setDeleteModalOpen(open) {
  if (!pageContent) return;
  pageContent.setAttribute("aria-hidden", String(open));
  if (open) pageContent.setAttribute("inert", "");
  else pageContent.removeAttribute("inert");
}

function requestDelete(it) {
  pendingDelete = {it};
  deleteFocus = document.activeElement;
  confirmDescription.textContent = t("delete.description");
  confirmNote.textContent = t("delete.note");
  confirmTarget.textContent = it.code;
  confirmModal.hidden = false;
  document.body.classList.add("modal-open");
  setDeleteModalOpen(true);
  window.setTimeout(() => {
    if (!pendingDelete) return;
    confirmModal.classList.add("open");
    confirmClose.focus();
  }, 0);
}

function closeDeleteDialog() {
  if (!pendingDelete) return;
  pendingDelete = null;
  confirmModal.classList.remove("open");
  document.body.classList.remove("modal-open");
  setDeleteModalOpen(false);
  const focus = deleteFocus;
  deleteFocus = null;
  window.setTimeout(() => {
    if (!confirmModal.classList.contains("open")) confirmModal.hidden = true;
  }, 180);
  if (focus && focus.focus) focus.focus();
}

function normalizeDeleteMarker(value) {
  if (!value || typeof value.path !== "string" || !value.path) return null;
  const startedAt = Number(value.startedAt);
  const attempt = Number(value.attempt);
  const rendered = Number(value.rendered);
  const scrollY = Number(value.scrollY);
  const item = value.item && typeof value.item === "object"
    && value.item.delete_path === value.path ? value.item : null;
  return {
    path: value.path,
    startedAt: Number.isFinite(startedAt) ? startedAt : Date.now(),
    attempt: Number.isFinite(attempt) && attempt >= 0 ? attempt : 0,
    rendered: Number.isFinite(rendered) && rendered >= 0 ? rendered : null,
    scrollY: Number.isFinite(scrollY) && scrollY >= 0 ? scrollY : null,
    item,
    filters: value.filters && typeof value.filters === "object"
      ? value.filters : null,
  };
}

function readHashDeleteMarker() {
  const raw = new URLSearchParams(location.hash.slice(1)).get(DELETE_HASH_KEY);
  if (!raw) return [];
  try {
    return normalizeDeleteMarkers(JSON.parse(raw));
  } catch (e) {
    // 旧格式是单个 JSON 对象，按单条包装
    return normalizeDeleteMarkers({path: raw});
  }
}

function updateDeleteHash(update) {
  const params = new URLSearchParams(location.hash.slice(1));
  update(params);
  try {
    const url = new URL(location.href);
    url.hash = params.toString();
    history.replaceState(null, "", url.href);
  } catch (e) {
    location.hash = params.toString();
  }
}

// 单槽只能记一条 pending：连续删除第二条会覆盖第一条，首删失败时
// 无人恢复也无提示，因此存储一律用数组，一次刷新推进全部条目
function normalizeDeleteMarkers(raw) {
  const list = Array.isArray(raw) ? raw : (raw ? [raw] : []);
  return list.map(normalizeDeleteMarker).filter(Boolean);
}

function writeHashDeleteMarkers(markers) {
  updateDeleteHash(params => params.set(DELETE_HASH_KEY, JSON.stringify(markers)));
}

function clearHashDeleteMarkers() {
  updateDeleteHash(params => params.delete(DELETE_HASH_KEY));
}

function writeDeleteMarkers(markers) {
  let saved = false;
  try {
    sessionStorage.setItem(DELETE_KEY, JSON.stringify(markers));
    saved = true;
  } catch (e) {
    // file:// 页面上的 sessionStorage 可能不可用，退回 hash。
  }
  if (!saved) writeHashDeleteMarkers(markers);
}

function readDeleteMarkers() {
  try {
    const saved = normalizeDeleteMarkers(
      JSON.parse(sessionStorage.getItem(DELETE_KEY) || "null"));
    if (saved.length) return saved;
  } catch (e) {
    // 继续尝试 hash 回退。
  }
  return readHashDeleteMarker();
}

function clearDeleteMarkers() {
  try { sessionStorage.removeItem(DELETE_KEY); } catch (e) { /* 无存储权限 */ }
  clearHashDeleteMarkers();
}

function deleteStatus(kind, text) {
  let status = document.getElementById("deleteStatus");
  if (!status) {
    status = document.createElement("div");
    status.id = "deleteStatus";
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    status.setAttribute("aria-atomic", "true");
    grid.parentNode.insertBefore(status, grid);
  }
  status.className = `delete-status ${kind}`;
  status.textContent = text;
}

function updateDeleteStats() {
  if (totalEl) totalEl.textContent = DATA.length;
  countEl.textContent = dirty() ? `${result.length} / ${DATA.length}` : "";
}

function removeItemFromPage(item) {
  const visibleIndex = result.indexOf(item);
  const index = DATA.indexOf(item);
  if (index >= 0) DATA.splice(index, 1);
  result = result.filter(entry => entry !== item);
  rendered = renderedAfterDelete(rendered, visibleIndex);
  const card = [...grid.querySelectorAll(".card")]
    .find(node => node.querySelector(".code")?.textContent === item.code);
  if (card) card.remove();
  if (!result.length) grid.innerHTML = `<div class="empty">${t("empty")}</div>`;
  updateDeleteStats();
}

function reloadAfterDelete() {
  const url = new URL(location.href);
  url.searchParams.set("kuraya-reload", Date.now());
  location.replace(url.href);
}

function scheduleDeleteReload() {
  if (deleteRecoveryTimer !== null) return;
  const markers = readDeleteMarkers();
  if (!markers.length) return;
  const attempt = Math.min(...markers.map(m => m.attempt)) + 1;
  writeDeleteMarkers(markers.map(m => ({...m, attempt})));
  const delay = DELETE_RETRY_DELAYS[
    Math.min(attempt - 1, DELETE_RETRY_DELAYS.length - 1)];
  deleteRecoveryTimer = window.setTimeout(() => {
    deleteRecoveryTimer = null;
    reloadAfterDelete();
  }, delay);
}

function confirmDelete() {
  if (!pendingDelete) return;
  const {it} = pendingDelete;
  const marker = {
    path: it.delete_path,
    startedAt: Date.now(),
    attempt: 0,
    item: it,
    rendered,
    scrollY: window.scrollY,
    // 刷新后恢复同样的筛选上下文：搜索词、三维筛选、排序
    filters: {search: search.value, active: {...active}, sortKey},
  };
  deleteFocus = null;
  closeDeleteDialog();
  const markers = readDeleteMarkers();
  markers.push(marker);
  writeDeleteMarkers(markers);
  deleteRestoreItem = it;
  removeItemFromPage(it);
  deleteStatus("pending", t("delete.pending"));
  scheduleDeleteReload();
  window.location.href = deleteUrl(it);
}

function recoverDeleteFailure(marker) {
  const restored = restoreDeleteItems(DATA, {
    ...marker,
    item: deleteRestoreItem || marker.item,
  });
  if (restored !== DATA) {
    DATA.splice(0, DATA.length, ...restored);
  }
  // 超时判定要求条目仍在数据里，restoreDeleteItems 必然原样返回，
  // 恢复不能挂在那次比对后面——否则筛选与位置永远回不来
  restoreDeleteView([marker]);
  deleteStatus("error", t("delete.failed"));
}

function applyDeleteFilters(filters) {
  if (!filters) return false;
  let changed = false;
  if (typeof filters.search === "string" && filters.search !== search.value) {
    search.value = filters.search;
    changed = true;
  }
  for (const key of ["actor", "label", "director"]) {
    const want = (filters.active && filters.active[key]) || null;
    if (active[key] !== want) {
      active[key] = want;
      changed = true;
    }
  }
  if (typeof filters.sortKey === "string" && SORT_NAMES[filters.sortKey]
      && filters.sortKey !== sortKey) {
    sortKey = filters.sortKey;
    changed = true;
  }
  return changed;
}

function restoreDeleteView(markers) {
  // 先恢复筛选上下文，再按删除前快照渲染到对应批次数并回到原位置。
  // force 让筛选状态下也能恢复（dirty 时 render 默认不恢复滚动）
  const snapshot = lastDeleteSnapshot(markers);
  if (snapshot) browseSnapshot = {...snapshot, force: true};
  const changed = applyDeleteFilters(latestFilters(markers));
  if (changed) {
    sortLabel.textContent = SORT_NAMES[sortKey];
    sortOpts.forEach((opt, i) =>
      opt.setAttribute("aria-selected", String(opt.dataset.value === sortKey)));
    updateClearBtn();
    buildChips();
    buildPills();
  }
  if (changed || snapshot) render();
}

function startDeleteRecovery() {
  const markers = readDeleteMarkers();
  if (!markers.length) return;
  const {done, timedOut, retry} = advanceDeleteMarkers(
    markers, DATA, Date.now(), DELETE_TIMEOUT);
  // done：重建后的数据已不含该路径，直接丢弃标记
  for (const marker of timedOut) recoverDeleteFailure(marker);
  for (const marker of retry) {
    const item = DATA.find(entry => entry.delete_path === marker.path);
    if (item) {
      deleteRestoreItem = item;
      removeItemFromPage(item);
    }
  }
  if (retry.length) {
    writeDeleteMarkers(retry);
    deleteStatus("pending", t("delete.pending"));
    // 删除还没确认完：保持删除前的筛选与位置，避免自动刷新闪回顶部
    restoreDeleteView(retry);
    scheduleDeleteReload();
    return;
  }
  // 删除完成（或全部超时已恢复）：回到用户删除时的筛选与位置
  restoreDeleteView(done);
  deleteRestoreItem = null;
  clearDeleteMarkers();
}

confirmClose.addEventListener("click", closeDeleteDialog);
confirmCancel.addEventListener("click", closeDeleteDialog);
confirmSubmit.addEventListener("click", confirmDelete);
confirmBackdrop.addEventListener("click", closeDeleteDialog);
document.addEventListener("keydown", e => {
  if (!confirmModal.classList.contains("open")) return;
  if (e.key === "Escape") {
    e.preventDefault();
    closeDeleteDialog();
    return;
  }
  if (e.key !== "Tab") return;
  const focusable = [confirmClose, confirmCancel, confirmSubmit];
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault();
    first.focus();
  }
});
