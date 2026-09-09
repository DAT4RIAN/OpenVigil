import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const source = await readFile(
  new URL("../components/data-display/data-table.tsx", import.meta.url),
  "utf8",
);

test("shared DataTable owns the complete operational table contract", () => {
  assert.match(source, /searchTextForRow/);
  assert.match(source, /filterControls/);
  assert.match(source, /getSortedRowModel/);
  assert.match(source, /columnVisibility/);
  assert.match(source, /rowSelection/);
  assert.match(source, /getPaginationRowModel/);
  assert.match(source, /bulkActions/);
  assert.match(source, /downloadCsv/);
  assert.match(source, /onRowActivate/);
});

test("core asset and knowledge tables consume the shared DataTable", async () => {
  const [windFarmSource, knowledgeSource] = await Promise.all([
    readFile(new URL("../components/pages/wind-farm-page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/pages/knowledge-base-page.tsx", import.meta.url), "utf8"),
  ]);

  for (const pageSource of [windFarmSource, knowledgeSource]) {
    assert.match(pageSource, /<DataTable/);
    assert.match(pageSource, /csvExport=/);
    assert.match(pageSource, /bulkActions=/);
  }
});

test("alarm, mission, and work-order lists delegate operational table behavior", async () => {
  const [alarmSource, missionSource, workOrderSource] = await Promise.all([
    readFile(new URL("../components/pages/alarm-center-page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/pages/mission-center-page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../components/pages/work-order-page.tsx", import.meta.url), "utf8"),
  ]);

  for (const pageSource of [alarmSource, missionSource, workOrderSource]) {
    assert.match(pageSource, /<DataTable/);
    assert.match(pageSource, /searchTextForRow=/);
    assert.match(pageSource, /filterControls=/);
    assert.match(pageSource, /csvExport=/);
    assert.match(pageSource, /bulkActions=/);
    assert.match(pageSource, /onRowActivate=/);
    assert.doesNotMatch(pageSource, /<table\b/);
    assert.doesNotMatch(pageSource, /table-pagination/);
  }

  assert.match(alarmSource, /确认所选活跃告警/);
  assert.match(alarmSource, /apiPost\("\/api\/alarms"/);
  assert.match(alarmSource, /mutateAlarm\(alarm, "acknowledge"\)/);
  assert.doesNotMatch(alarmSource, /setAcknowledgedIds|assignmentOverrides/);
  assert.match(missionSource, /打开首个所选 Mission/);
  assert.match(missionSource, /window\.location\.assign/);
  assert.match(workOrderSource, /打开首个所选工单/);
  assert.match(workOrderSource, /setSelectedId\(workOrder\.id\)/);

  for (const pageSource of [alarmSource, workOrderSource]) {
    assert.doesNotMatch(pageSource, /URL\.createObjectURL/);
    assert.doesNotMatch(pageSource, /selectedIds/);
    assert.doesNotMatch(pageSource, /setPage\(/);
  }
});
