import fs from "node:fs/promises";

import { SpreadsheetFile, Workbook, ChartDataLabels } from "@oai/artifact-tool";

async function buildChartSuggestionWorkbook(outputDir: string): Promise<void> {
  await fs.mkdir(outputDir, { recursive: true });

  const workbook = Workbook.create();
  const sheet = workbook.worksheets.add("Charts");
  sheet.showGridLines = false;

  sheet.getRange("A1:C5").values = [
    ["Month", "Revenue", "EBITDA"],
    ["Jan", 100000, 18000],
    ["Feb", 121000, 23000],
    ["Mar", 132000, 28000],
    ["Apr", 149000, 34000],
  ];
  sheet.getRange("A1:C1").format = {
    fill: "#0F766E",
    font: { bold: true, color: "#FFFFFF" },
  };
  sheet.getRange("B2:C5").format.numberFormat = "$#,##0";
  sheet.getRange("A:C").format.columnWidthPx = 96;

  // Fast chart path: chart a continuous helper range. The helper range is
  // formula-backed so edits to the source table update the chart.
  sheet.getRange("F1:H1").values = [["Month", "Revenue", "EBITDA"]];
  sheet.getRange("F2:H2").formulas = [["=A2", "=B2", "=C2"]];
  sheet.getRange("F2:H5").fillDown();
  const lineChart = sheet.charts.add("line", sheet.getRange("F1:H5"));
  lineChart.setPosition("J1", "Q15");
  lineChart.title = "Revenue and EBITDA Trend";
  lineChart.titleTextStyle.fontSize = 12;
  lineChart.hasLegend = true;
  lineChart.xAxis = { axisType: "textAxis" };
  lineChart.yAxis = { numberFormatCode: "$#,##0" };

  const scatterPlot = sheet.charts.add("scatter", sheet.getRange("F1:H5"));
  scatterPlot.setPosition("J1", "Q15");
  scatterPlot.title = "Revenue and EBITDA Trend Scatter";
  scatterPlot.titleTextStyle.fontSize = 12;
  scatterPlot.hasLegend = true;
  scatterPlot.xAxis = { axisType: "textAxis" };
  scatterPlot.yAxis = { numberFormatCode: "$#,##0" };
  scatterPlot.dataLabels = new ChartDataLabels({showValue: true, position: 'above' });

  // Advanced path: manually define a single series by formula.
  const barChart = sheet.charts.add("bar", {
    title: "EBITDA by Month",
    hasLegend: false,
  });
  const series = barChart.series.add("EBITDA");
  series.categoryFormula = "'Charts'!$A$2:$A$5";
  series.formula = "'Charts'!$C$2:$C$5";
  series.fill = "#F472B6";
  barChart.setPosition("J18", "Q32");
  barChart.title = "EBITDA by Month";
  barChart.titleTextStyle.fontSize = 12;
  barChart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 10} };
  barChart.yAxis = { numberFormatCode: "$#,##0", textStyle: { fontSize: 10} };

  barChart.xAxis.title.text = "EBITDA";  

  barChart.yAxis.title.text = "Month";
  barChart.yAxis.min = 10_000;
  barChart.yAxis.max = 40_000;
  barChart.yAxis.majorUnit = 5;
  // TODO @vicky set default title text to be size 12

  // setData replaces the chart source range; use it when a chart exists before
  // the final source range is known.
  lineChart.setData(sheet.getRange("F1:H5"));

  const preview = await workbook.render({
    sheetName: "Charts",
    autoCrop: "all",
    scale: 1,
    format: "png",
  });
  await fs.writeFile(
    `${outputDir}/typescript_chart_suggestions.png`,
    new Uint8Array(await preview.arrayBuffer()),
  );

  const xlsx = await SpreadsheetFile.exportXlsx(workbook);
  await xlsx.save(`${outputDir}/typescript_chart_suggestions.xlsx`);

  console.log(`Rendered ${outputDir}/typescript_chart_suggestions.png`);
  console.log(`Saved ${outputDir}/typescript_chart_suggestions.xlsx`);
}

const outputDir = process.argv[2] ?? "output/chart_suggestions";
buildChartSuggestionWorkbook(outputDir).catch((error: unknown) => {
  console.error(error);
  process.exit(1);
});
