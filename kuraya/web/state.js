function deleteEnabled(playMode) {
  return playMode === "protocol";
}

function browseRenderCount(snapshot, resultLength, page, fullRender) {
  if (fullRender) return Infinity;
  const saved = snapshot && Number.isFinite(snapshot.rendered)
    ? snapshot.rendered : page;
  return Math.min(Math.max(saved, page), resultLength);
}

function renderedAfterDelete(rendered, index) {
  return index >= 0 && index < rendered ? rendered - 1 : rendered;
}

function deletePollState(pending, items, now, timeout) {
  if (!pending) return {status: "idle"};
  if (!items.some(item => item.delete_path === pending.path)) {
    return {status: "done"};
  }
  if (now - pending.startedAt >= timeout) return {status: "timeout"};
  return {status: "retry"};
}

function restoreDeleteItems(items, marker) {
  if (!marker || !marker.item || marker.item.delete_path !== marker.path) {
    return items;
  }
  if (items.some(item => item.delete_path === marker.path)) return items;
  return [...items, marker.item];
}

// 一批待确认删除按当前页面数据分三组：已完成、已超时、仍需等待。
// 连续删除会把多条 pending 记在一起，刷新一次统一推进全部条目
function advanceDeleteMarkers(markers, items, now, timeout) {
  const done = [];
  const timedOut = [];
  const retry = [];
  for (const marker of markers) {
    const state = deletePollState(marker, items, now, timeout);
    if (state.status === "done") done.push(marker);
    else if (state.status === "timeout") timedOut.push(marker);
    else retry.push(marker);
  }
  return {done, timedOut, retry};
}

// 从一组待确认删除里取最近一次的有效浏览快照（最后删除的那条优先）：
// 刷新后回到用户删除的位置，而不是掉回页面顶部。rendered 与 scrollY
// 各自独立校验，缺失的字段保持 null
function lastDeleteSnapshot(markers) {
  for (let i = markers.length - 1; i >= 0; i--) {
    const m = markers[i];
    if (!m) continue;
    const rendered = Number(m.rendered);
    const scrollY = Number(m.scrollY);
    const hasRendered = Number.isFinite(rendered) && rendered >= 0;
    const hasScroll = Number.isFinite(scrollY) && scrollY >= 0;
    if (hasRendered || hasScroll) {
      return {
        rendered: hasRendered ? rendered : null,
        scrollY: hasScroll ? scrollY : null,
      };
    }
  }
  return null;
}

// 最近一次删除时保存的筛选状态（搜索词、三维筛选、排序），没有则 null
function latestFilters(markers) {
  for (let i = markers.length - 1; i >= 0; i--) {
    const filters = markers[i] && markers[i].filters;
    if (filters) return filters;
  }
  return null;
}

if (typeof module !== "undefined") {
  module.exports = {
    deleteEnabled, browseRenderCount, renderedAfterDelete, deletePollState,
    restoreDeleteItems, advanceDeleteMarkers, lastDeleteSnapshot,
    latestFilters,
  };
}
