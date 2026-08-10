const test = require("node:test");
const assert = require("node:assert/strict");

const {
  deleteEnabled,
  browseRenderCount,
  renderedAfterDelete,
  deletePollState,
  restoreDeleteItems,
  advanceDeleteMarkers,
  lastDeleteSnapshot,
  latestFilters,
} = require("../kuraya/web/state.js");

test("copy mode does not enable destructive actions", () => {
  assert.equal(deleteEnabled("protocol"), true);
  assert.equal(deleteEnabled("copy"), false);
});

test("restoring a deep browse position renders the old number of batches first", () => {
  assert.equal(
    browseRenderCount({rendered: 240}, 320, 60, false),
    240,
  );
  assert.equal(
    browseRenderCount({rendered: 240}, 100, 60, false),
    100,
  );
});

test("removing a rendered card keeps the next batch contiguous", () => {
  assert.equal(renderedAfterDelete(60, 20), 59);
  assert.equal(renderedAfterDelete(60, 60), 60);
});

test("delete polling waits while the old item is still in the rebuilt data", () => {
  const pending = {path: "/library/演员/ABC-001", startedAt: 1000, attempt: 1};
  assert.equal(
    deletePollState(pending, [{delete_path: pending.path}], 2500, 60000).status,
    "retry",
  );
});

test("delete polling completes when the rebuilt data no longer contains the item", () => {
  const pending = {path: "/library/演员/ABC-001", startedAt: 1000, attempt: 1};
  assert.equal(deletePollState(pending, [], 2500, 60000).status, "done");
});

test("delete polling gives up after its bounded timeout", () => {
  const pending = {path: "/library/演员/ABC-001", startedAt: 1000, attempt: 4};
  assert.equal(
    deletePollState(pending, [{delete_path: pending.path}], 62001, 60000).status,
    "timeout",
  );
});

test("a failed delete restores the removed item exactly once", () => {
  const item = {delete_path: "/library/演员/ABC-001", code: "ABC-001"};
  const marker = {path: item.delete_path, item};
  const restored = restoreDeleteItems([], marker);
  assert.deepEqual(restored, [item]);
  assert.strictEqual(restoreDeleteItems(restored, marker), restored);
});

test("advance splits concurrent delete markers into three states", () => {
  const done = {path: "/library/演员/ABC-001", startedAt: 1000, attempt: 1};
  const timedOut = {path: "/library/演员/ABC-002", startedAt: 1000, attempt: 4};
  const retry = {path: "/library/演员/ABC-003", startedAt: 5000, attempt: 1};
  const items = [
    {delete_path: timedOut.path},
    {delete_path: retry.path},
  ];
  const now = 62001;  // 距 startedAt 分别 61s/57s：一个超时一个仍在等待
  const groups = advanceDeleteMarkers([done, timedOut, retry], items, now, 60000);
  assert.deepEqual(groups.done, [done]);
  assert.deepEqual(groups.timedOut, [timedOut]);
  assert.deepEqual(groups.retry, [retry]);
});

test("advance with no pending markers returns three empty groups", () => {
  const groups = advanceDeleteMarkers([], [], 0, 60000);
  assert.deepEqual(groups, {done: [], timedOut: [], retry: []});
});

test("restore snapshot prefers the most recent delete marker", () => {
  assert.deepEqual(
    lastDeleteSnapshot([
      {path: "/a", rendered: 60, scrollY: 100},
      {path: "/b", rendered: 240, scrollY: 480},
    ]),
    {rendered: 240, scrollY: 480},
  );
});

test("restore snapshot keeps rendered and scroll independent", () => {
  assert.deepEqual(
    lastDeleteSnapshot([{path: "/a", scrollY: 0}, {path: "/b", rendered: 60}]),
    {rendered: 60, scrollY: null},
  );
  assert.deepEqual(
    lastDeleteSnapshot([{path: "/a", rendered: 60, scrollY: 100}]),
    {rendered: 60, scrollY: 100},
  );
  assert.equal(lastDeleteSnapshot([{path: "/a"}]), null);
  assert.equal(lastDeleteSnapshot([]), null);
});

test("latest filters come from the most recent marker that saved any", () => {
  const filters = {search: "ABC", active: {actor: "演员甲"}, sortKey: "added_desc"};
  assert.deepEqual(
    latestFilters([
      {path: "/a"},
      {path: "/b", filters},
      {path: "/c", filters: null},
    ]),
    filters,
  );
  assert.equal(latestFilters([{path: "/a"}]), null);
  assert.equal(latestFilters([]), null);
});
