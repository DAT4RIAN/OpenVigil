import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const pageFiles = [
  "maintenance-plan-page.tsx",
  "resource-center-page.tsx",
  "predictive-maintenance-page.tsx",
  "data-center-page.tsx",
];

const pageSources = await Promise.all(
  pageFiles.map((filename) =>
    readFile(new URL(`../components/pages/${filename}`, import.meta.url), "utf8"),
  ),
);

test("remaining high-value ledgers use the shared operational DataTable", () => {
  for (const source of pageSources) {
    assert.match(source, /<DataTable/);
    assert.match(source, /initialSorting=/);
    assert.match(source, /pageSize=/);
    assert.match(source, /searchTextForRow=/);
    assert.match(source, /bulkActions=/);
    assert.match(source, /csvExport=/);
  }
});

test("maintenance and predictive tables preserve row-driven detail selection", () => {
  const [maintenanceSource, , predictiveSource] = pageSources;

  assert.match(
    maintenanceSource,
    /onRowActivate=\{\(plan\) => setSelectedId\(plan\.workOrderId\)\}/,
  );
  assert.match(
    predictiveSource,
    /onRowActivate=\{\(assessment\) => setSelectedId\(assessment\.turbineId\)\}/,
  );
});

test("catalog and spare-parts exports retain honest identifiers and deep links", () => {
  const [, resourceSource, , dataCenterSource] = pageSources;

  assert.match(resourceSource, /openvigil-spare-parts\.csv/);
  assert.match(resourceSource, /reservedForWorkOrderIds/);
  assert.match(dataCenterSource, /openvigil-data-catalog\.csv/);
  assert.match(dataCenterSource, /href=\{row\.original\.queryHref\}/);
});
