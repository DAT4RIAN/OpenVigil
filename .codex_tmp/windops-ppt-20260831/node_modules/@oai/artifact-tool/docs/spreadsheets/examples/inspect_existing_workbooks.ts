import * as fs from "node:fs/promises";
import * as path from "node:path";

import {
  FileBlob,
  SpreadsheetFile,
} from "../../../../oai_js_artifact_tool";

const DEFAULT_WORKBOOK_INPUTS = [
  "/Users/vicky/code/openai/output/spreadsheet-atv/fitness-tracker-20260409",
];

type InspectResult = {
  ndjson: string;
};

async function resolveWorkbookPath(inputPath: string): Promise<string> {
  const expandedPath = inputPath.startsWith("~")
    ? path.join(process.env.HOME ?? "", inputPath.slice(1))
    : inputPath;
  const stats = await fs.stat(expandedPath);
  if (stats.isFile()) {
    return expandedPath;
  }
  if (stats.isDirectory()) {
    const candidates = (await fs.readdir(expandedPath))
      .filter((entry) => entry.endsWith(".xlsx"))
      .sort();
    if (candidates.length > 0) {
      return path.join(expandedPath, candidates[0]);
    }
    throw new Error(`No .xlsx files found in directory: ${expandedPath}`);
  }
  throw new Error(`Workbook path is not a file or directory: ${expandedPath}`);
}

function printInspect(title: string, result: InspectResult): void {
  console.log(`\n=== ${title} ===`);
  if (result.ndjson) {
    console.log(result.ndjson);
    return;
  }
  console.log("(no rows returned)");
}

async function inspectWorkbook(workbookPath: string): Promise<void> {
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(workbookPath));
  const firstSheet = workbook.worksheets.getItemAt(0);
  const firstSheetName = firstSheet.name;

  console.log(`\n########## Inspecting ${workbookPath} ##########`);
  console.log(`First worksheet: ${firstSheetName}`);

  const summary = await workbook.inspect({
    kind: "workbook,sheet,table",
    maxChars: 6000,
    tableMaxRows: 6,
    tableMaxCols: 6,
    tableMaxCellChars: 80,
  });
  printInspect("Workbook summary", summary);

  const sheetsIndex = await workbook.inspect({
    kind: "sheet",
    include: "id,name",
  });
  printInspect("Sheets index", sheetsIndex);

  const firstRegion = await workbook.inspect({
    kind: "region",
    sheetId: firstSheetName,
    range: "A1:Z30",
    maxChars: 2500,
    tableMaxRows: 12,
    tableMaxCols: 8,
    tableMaxCellChars: 50,
  });
  printInspect(`First sheet region preview (${firstSheetName}!A1:Z30)`, firstRegion);

  const formulas = await workbook.inspect({
    kind: "formula",
    sheetId: firstSheetName,
    maxChars: 2000,
  });
  printInspect(`Formula snapshot (${firstSheetName})`, formulas);

  const drawings = await workbook.inspect({
    kind: "drawing",
    sheetId: firstSheetName,
    maxChars: 2000,
  });
  printInspect(`Drawing snapshot (${firstSheetName})`, drawings);
}

async function inspectExistingWorkbooks(inputPaths: string[]): Promise<void> {
  for (const inputPath of inputPaths) {
    const workbookPath = await resolveWorkbookPath(inputPath);
    await inspectWorkbook(workbookPath);
  }
}

async function main(): Promise<void> {
  const inputPaths =
    process.argv.slice(2).length > 0
      ? process.argv.slice(2)
      : DEFAULT_WORKBOOK_INPUTS;
  await inspectExistingWorkbooks(inputPaths);
}

main().catch((error: unknown) => {
  console.error(error);
  process.exit(1);
});
