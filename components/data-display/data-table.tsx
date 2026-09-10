"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, InputHTMLAttributes, KeyboardEvent, MouseEvent, ReactNode } from "react";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  ChevronLeft,
  ChevronRight,
  Columns3,
  Download,
  Search,
  X,
} from "lucide-react";
import { flexRender } from "@tanstack/react-table";
import type {
  ColumnVisibilityState,
  PaginationState,
  RowData,
  RowSelectionState,
  SortingState,
} from "@tanstack/react-table";
import {
  getCoreRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useLegacyTable,
} from "@tanstack/react-table/legacy";
import type { LegacyColumnDef } from "@tanstack/react-table/legacy";

import styles from "./data-table.module.css";

function SelectionCheckbox({
  indeterminate = false,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { readonly indeterminate?: boolean }) {
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate;
  }, [indeterminate]);

  return <input ref={ref} type="checkbox" {...props} />;
}

export interface DataTableProps<TData extends RowData> {
  readonly data: readonly TData[];
  readonly columns: readonly LegacyColumnDef<TData, unknown>[];
  readonly getRowId: (row: TData) => string;
  readonly onRowActivate?: (row: TData) => void;
  readonly selectedRowId?: string | null;
  readonly initialSorting?: SortingState;
  readonly pageSize?: number;
  readonly emptyMessage?: string;
  readonly searchTextForRow?: (row: TData) => string;
  readonly searchPlaceholder?: string;
  readonly filterControls?: ReactNode;
  readonly bulkActions?: readonly DataTableBulkAction<TData>[];
  readonly csvExport?: DataTableCsvExport<TData>;
  readonly onSelectionChange?: (rows: readonly TData[]) => void;
}

export interface DataTableBulkAction<TData> {
  readonly label: string;
  readonly onActivate: (rows: readonly TData[]) => void | Promise<void>;
}

export interface DataTableCsvExport<TData> {
  readonly filename: string;
  readonly columns: readonly {
    readonly label: string;
    readonly value: (row: TData) => string | number | boolean | null | undefined;
  }[];
}

const csvCell = (value: string | number | boolean | null | undefined): string =>
  `"${String(value ?? "").replaceAll('"', '""')}"`;

function downloadCsv<TData>(config: DataTableCsvExport<TData>, rows: readonly TData[]): void {
  const header = config.columns.map((column) => csvCell(column.label)).join(",");
  const body = rows.map((row) =>
    config.columns.map((column) => csvCell(column.value(row))).join(","),
  );
  const blob = new Blob(["\uFEFF", [header, ...body].join("\r\n")], {
    type: "text/csv;charset=utf-8",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = config.filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function DataTable<TData extends RowData>({
  data,
  columns,
  getRowId,
  onRowActivate,
  selectedRowId = null,
  initialSorting = [],
  pageSize = 6,
  emptyMessage = "没有匹配的记录",
  searchTextForRow,
  searchPlaceholder = "搜索记录…",
  filterControls,
  bulkActions = [],
  csvExport,
  onSelectionChange,
}: DataTableProps<TData>) {
  const [sorting, setSorting] = useState<SortingState>(initialSorting);
  const [columnVisibility, setColumnVisibility] = useState<ColumnVisibilityState>({});
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [pagination, setPagination] = useState<PaginationState>({
    pageIndex: 0,
    pageSize,
  });
  const [query, setQuery] = useState("");
  const filteredData = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized || !searchTextForRow) return [...data];
    return data.filter((row) => searchTextForRow(row).toLocaleLowerCase().includes(normalized));
  }, [data, query, searchTextForRow]);

  const selectionColumn = useMemo<LegacyColumnDef<TData, unknown>>(
    () => ({
      id: "select",
      header: ({ table }) => (
        <SelectionCheckbox
          aria-label="选择当前页全部记录"
          checked={table.getIsAllPageRowsSelected()}
          indeterminate={table.getIsSomePageRowsSelected()}
          onChange={table.getToggleAllPageRowsSelectedHandler()}
          onClick={(event: MouseEvent<HTMLInputElement>) => event.stopPropagation()}
        />
      ),
      cell: ({ row }) => (
        <SelectionCheckbox
          aria-label={`选择记录 ${row.id}`}
          checked={row.getIsSelected()}
          disabled={!row.getCanSelect()}
          indeterminate={row.getIsSomeSelected()}
          onChange={row.getToggleSelectedHandler()}
          onClick={(event: MouseEvent<HTMLInputElement>) => event.stopPropagation()}
        />
      ),
      enableHiding: false,
      enableSorting: false,
      size: 44,
    }),
    [],
  );
  const tableColumns = useMemo(
    () => [selectionColumn, ...columns] as LegacyColumnDef<TData, unknown>[],
    [columns, selectionColumn],
  );

  const table = useLegacyTable({
    data: filteredData,
    columns: tableColumns,
    state: { sorting, columnVisibility, rowSelection, pagination },
    onSortingChange: setSorting,
    onColumnVisibilityChange: setColumnVisibility,
    onRowSelectionChange: setRowSelection,
    onPaginationChange: setPagination,
    getRowId,
    enableRowSelection: true,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
  });

  useEffect(() => {
    table.setPageIndex(0);
  }, [filteredData, table]);

  const visibleRows = table.getRowModel().rows;
  const selectedCount = Object.keys(rowSelection).length;
  const selectedRows = useMemo(
    () => filteredData.filter((row) => rowSelection[getRowId(row)]),
    [filteredData, getRowId, rowSelection],
  );
  const exportRows = selectedRows.length ? selectedRows : filteredData;
  const pageCount = Math.max(1, table.getPageCount());
  const pageIndex = Math.min(pagination.pageIndex, pageCount - 1);

  const activateRow = (row: TData): void => onRowActivate?.(row);
  const cameFromInteractiveChild = (
    event: KeyboardEvent<HTMLTableRowElement> | MouseEvent<HTMLTableRowElement>,
  ): boolean => {
    if (event.target === event.currentTarget || !(event.target instanceof Element)) return false;
    return Boolean(
      event.target.closest(
        'a[href],button,input,select,textarea,summary,[role="button"],[role="link"],[contenteditable="true"],[tabindex]:not([tabindex="-1"]),[data-row-activation-ignore]',
      ),
    );
  };
  const onRowKeyDown = (event: KeyboardEvent<HTMLTableRowElement>, row: TData): void => {
    if (cameFromInteractiveChild(event)) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      activateRow(row);
    }
  };

  useEffect(() => {
    onSelectionChange?.(selectedRows);
  }, [onSelectionChange, selectedRows]);

  return (
    <div className={styles.root}>
      <div className={styles.toolbar}>
        <div className={styles.toolbarPrimary}>
          {searchTextForRow ? (
            <div className={styles.searchGroup}>
              <label className={styles.searchField}>
                <Search size={14} aria-hidden="true" />
                <span className={styles.srOnly}>搜索表格</span>
                <input
                  aria-label="搜索表格"
                  placeholder={searchPlaceholder}
                  type="search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </label>
              {query ? (
                <button
                  className={styles.clearSearch}
                  type="button"
                  aria-label="清除表格搜索"
                  onClick={() => setQuery("")}
                >
                  <X size={14} aria-hidden="true" />
                </button>
              ) : null}
            </div>
          ) : null}
          {filterControls}
          <span aria-live="polite">
            {filteredData.length} 条记录 · 已选择 {selectedCount} 条
          </span>
        </div>
        <div className={styles.toolbarActions}>
          {bulkActions.map((action) => (
            <button
              disabled={!selectedRows.length}
              key={action.label}
              type="button"
              onClick={() =>
                void Promise.resolve(action.onActivate(selectedRows)).then(() =>
                  setRowSelection({}),
                )
              }
            >
              {action.label}
            </button>
          ))}
          {csvExport ? (
            <button
              disabled={!exportRows.length}
              type="button"
              onClick={() => downloadCsv(csvExport, exportRows)}
            >
              <Download size={14} aria-hidden="true" /> 导出 CSV
            </button>
          ) : null}
          <details className={styles.columnsMenu}>
            <summary>
              <Columns3 size={14} aria-hidden="true" /> 列显示
            </summary>
            <div className={styles.columnsPopover}>
              {table
                .getAllLeafColumns()
                .filter((column) => column.getCanHide())
                .map((column) => (
                  <label key={column.id}>
                    <input
                      checked={column.getIsVisible()}
                      type="checkbox"
                      onChange={(event: ChangeEvent<HTMLInputElement>) =>
                        column.toggleVisibility(event.target.checked)
                      }
                    />
                    {typeof column.columnDef.header === "string"
                      ? column.columnDef.header
                      : column.id}
                  </label>
                ))}
            </div>
          </details>
        </div>
      </div>

      <div className={styles.scroller}>
        <table className={styles.table}>
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  const sort = header.column.getIsSorted();
                  return (
                    <th key={header.id} style={{ width: header.getSize() }}>
                      {header.isPlaceholder ? null : header.column.getCanSort() ? (
                        <button
                          className={styles.sortButton}
                          type="button"
                          onClick={header.column.getToggleSortingHandler()}
                        >
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          {sort === "asc" ? (
                            <ArrowUp size={13} aria-label="升序" />
                          ) : sort === "desc" ? (
                            <ArrowDown size={13} aria-label="降序" />
                          ) : (
                            <ArrowUpDown size={13} aria-label="可排序" />
                          )}
                        </button>
                      ) : (
                        flexRender(header.column.columnDef.header, header.getContext())
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {visibleRows.length > 0 ? (
              visibleRows.map((row) => (
                <tr
                  className={selectedRowId === row.id ? styles.activeRow : undefined}
                  key={row.id}
                  tabIndex={onRowActivate ? 0 : undefined}
                  onClick={(event) => {
                    if (!cameFromInteractiveChild(event)) activateRow(row.original);
                  }}
                  onKeyDown={(event) => onRowKeyDown(event, row.original)}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))
            ) : (
              <tr>
                <td className={styles.empty} colSpan={table.getVisibleLeafColumns().length}>
                  {emptyMessage}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className={styles.pagination}>
        <span>
          第 {pageIndex + 1} / {pageCount} 页
        </span>
        <div>
          <button
            aria-label="上一页"
            disabled={!table.getCanPreviousPage()}
            type="button"
            onClick={() => table.previousPage()}
          >
            <ChevronLeft size={15} />
          </button>
          <button
            aria-label="下一页"
            disabled={!table.getCanNextPage()}
            type="button"
            onClick={() => table.nextPage()}
          >
            <ChevronRight size={15} />
          </button>
        </div>
      </div>
    </div>
  );
}
