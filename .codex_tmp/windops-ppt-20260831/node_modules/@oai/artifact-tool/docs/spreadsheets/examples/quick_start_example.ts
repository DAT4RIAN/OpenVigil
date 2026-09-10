import fs from "node:fs/promises";

import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

/**
 * Quick Start Examples
 * This runnable TypeScript example mirrors:
 * lib/agent/tools/artifact_tool_v2/skills/python/spreadsheets/examples/quick_start_example.py
 */
async function quickApiExample(): Promise<void> {
  // Creating a workbook and adding sheets with data and basic formatting
  const workbook = Workbook.create();
  var sheet = workbook.worksheets.add("ExampleSheet");

  sheet = workbook.worksheets.getItem("ExampleSheet");
  sheet.getRange("A1:D4").values = [
    ["Name", "Personality Type", "Age", "Birthday"],
    ["John Doe", "Introvert", 30, new Date("1990-01-01T00:00:00Z")],
    ["Jane Smith", "Extrovert", 25, new Date("1995-02-15T00:00:00Z")],
    ["Jim Very Long Name", "Ambivert", 40, new Date("1980-03-20T00:00:00Z")],
  ];
  sheet.getRange("E1").values = [["Score"]];
  sheet.getRange("E2").formulas = [["=C2*10"]]; // score is 10 * age
  sheet.getRange("E2:E4").fillDown();
  const headerRange = sheet.getRange("A1:E1");

  // Styling
  const headerFormats = {
    fill: "#0F766E",
    font: { bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    rowHeight: 16,
  };
  headerRange.format = headerFormats;
  headerRange.format.autofitColumns();

  const dataRange = sheet.getRange("A2:D4");
  dataRange.format.wrapText = true;
  sheet.showGridLines = false;

  // Format dates properly.
  sheet.getRange("D2:D4").format.numberFormat = "MM/DD/YYYY";

  // Conditional formatting
  sheet.getRange("C2:C4").conditionalFormats.add("dataBar", {
    color: "#704023",
    gradient: true,
  });
  sheet.getRange("E2:E4").conditionalFormats.add("cellIs", {
    operator: "greaterThan",
    formula: 300,
    format: { font: { color: "#B91C1C" } },
  });
  sheet.conditionalFormattings.add({
    range: "B2:B4",
    rule: {
      type: "expression",
      formula: '=B2="Introvert"',
      format: { fill: "#FCA5A5" },
    },
  });

  // Data validation: Since Personality Type is a dropdown category, add data validation.
  sheet.getRange("B2:B4").dataValidation = {
    rule: {
      type: "list",
      values: ["Introvert", "Extrovert", "Ambivert"],
      // formula1: "CategoriesSheet!$A$2:$A$4", // Alternative: reference a tunable list
    },
  };

  // Tables: Turn it into a table (for example purposes! Make sure table names are unique)
  // NOTE: If hasHeaders=true, the range must include the header row.
  const table = sheet.tables.add("A1:E4", true, "PeopleTable");
  table.getHeaderRowRange();

  // First column is still wide since we only auto-fit the first row. Expand it manually.
  sheet.getRange("A1:A4").format.columnWidth = 20;

  // Create a compact chart helper range that references the source table.
  sheet.getRange("H1:I1").merge();
  sheet.getRange("H1").values = [["Charts"]];
  sheet.getRange("H1").format = headerFormats;
  sheet.getRange("H3:I3").values = [["Person", "Score"]];
  sheet.getRange("H4:I4").formulas = [["=A2", "=E2"]];
  sheet.getRange("H4:I6").fillDown();
  const chart = sheet.charts.add("bar", sheet.getRange("H3:I6"));
  chart.title = "Person by Scores";
  chart.hasLegend = true;
  chart.displayBlanksAs = "zero";
  chart.barOptions.direction = "column";
  chart.barOptions.grouping = "clustered";
  chart.setPosition("K2", "R16");

  // Granular control over chart axes
  chart.xAxis = {
    axisType: "textAxis",
    title: { text: "Person", textStyle: { fontSize: 13, bold: true } },
    position: "bottom",
    orientation: "minMax",
    textStyle: { fontSize: 10 },
  };
  chart.yAxis = {
    axisType: "textAxis",
    title: { text: "Scores", textStyle: { fontSize: 13, bold: true } },
    numberFormatCode: "0,000",
    numberFormatSourceLinked: false,
  };

  // Sparklines: add to the right of table
  const sparklinesHeader = sheet.getRange("F1");
  sparklinesHeader.values = [["Sparklines"]];
  sparklinesHeader.format = headerFormats;
  sparklinesHeader.format.autofitColumns();

  sheet.sparklines.add({
    type: "column", // "line" | "column" | "stacked"
    sourceData: sheet.getRange("E2:E4"),
    targetRange: sheet.getRange("F2:F4"),
    seriesColor: "#AAAAAA",
  });

  // Render
  await fs.mkdir("output", { recursive: true });
  const pngBlob = await workbook.render({
    sheetName: "ExampleSheet",
    autoCrop: "all",
    scale: 1,
    format: "png",
  });
  const pngBytes = new Uint8Array(await pngBlob.arrayBuffer());
  await fs.writeFile("output/example_sheet.png", pngBytes);
  console.log("Rendered first sheet to 'output/example_sheet.png'");

  // Export
  const out = "output/example_sheet.xlsx";
  const xlsx = await SpreadsheetFile.exportXlsx(workbook);
  await xlsx.save(out);
  console.log(`Spreadsheet saved to ${out}`);
}

quickApiExample().catch((error: unknown) => {
  console.error(error);
  process.exit(1);
});
