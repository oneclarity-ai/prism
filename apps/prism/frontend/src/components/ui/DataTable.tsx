import type { Key, ReactNode } from "react";

const NUMERIC = /^(runs|tokens|cost|duration|tasks|success rate|input tokens|output tokens)$/i;

/** A full-width `<tr class="workspace-date-group"><th scope="rowgroup">` separator row. */
export interface DataTableGroupRow {
  group: string;
  key?: Key;
}

export interface DataTableCellsRow {
  cells: readonly ReactNode[];
  key?: Key;
  className?: string;
}

/** A plain array is the cells of a row; null/undefined cells render as an em dash. */
export type DataTableRow = readonly ReactNode[] | DataTableGroupRow | DataTableCellsRow;

export interface DataTableProps {
  headers: readonly string[];
  rows: readonly DataTableRow[];
  className?: string;
}

const isGroup = (row: DataTableRow): row is DataTableGroupRow => !Array.isArray(row) && "group" in row;

export function DataTable({ headers, rows, className = "" }: DataTableProps) {
  const numeric = headers.map((text) => NUMERIC.test(text));
  return (
    <div className={`workspace-table-wrap ${className}`}>
      <table className="workspace-table">
        <thead>
          <tr>
            {headers.map((text, index) => (
              <th key={index} className={numeric[index] ? "numeric" : undefined} scope="col">
                {text}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => {
            if (isGroup(row)) {
              return (
                <tr key={row.key ?? rowIndex} className="workspace-date-group">
                  <th colSpan={headers.length} scope="rowgroup" className={numeric[0] ? "numeric" : undefined}>
                    {row.group}
                  </th>
                </tr>
              );
            }
            const cells = Array.isArray(row) ? (row as readonly ReactNode[]) : (row as DataTableCellsRow).cells;
            const meta = Array.isArray(row) ? undefined : (row as DataTableCellsRow);
            return (
              <tr key={meta?.key ?? rowIndex} className={meta?.className}>
                {cells.map((content, index) => (
                  <td key={index} className={numeric[index] ? "numeric" : undefined}>
                    {content ?? "—"}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
