// DataTable.jsx
import React, { useState, useMemo, useRef } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'   // ✅ nouveau hook
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
} from '@tanstack/react-table'

export default function DataTable({ columns, data }) {
  const [sorting, setSorting] = useState([])

  const columnDefs = useMemo(
    () => columns.map(k => ({ accessorKey: k, header: k })),
    [columns]
  )

  const table = useReactTable({
    data,
    columns: columnDefs,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  /* virtualisation v4 */
  const parentRef = useRef(null)
  const rowVirtualizer = useVirtualizer({
    count: table.getRowModel().rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 34, // hauteur de ligne (px)
  })
  const virtualRows = rowVirtualizer.getVirtualItems()
  const paddingTop  = virtualRows.length ? virtualRows[0].start : 0
  const paddingBottom =
    virtualRows.length
      ? rowVirtualizer.getTotalSize() - virtualRows[virtualRows.length - 1].end
      : 0

  return (
    <div ref={parentRef} className="h-96 overflow-y-auto">
      <table className="min-w-full text-sm">
        <thead className="sticky top-0 bg-gray-100">
          {table.getHeaderGroups().map(hg => (
            <tr key={hg.id}>
              {hg.headers.map(h => (
                <th
                  key={h.id}
                  onClick={h.column.getToggleSortingHandler()}
                  className="px-2 py-1 cursor-pointer select-none"
                >
                  {flexRender(h.column.columnDef.header, h.getContext())}
                  {{
                    asc: ' 🔼',
                    desc: ' 🔽',
                  }[h.column.getIsSorted()] ?? null}
                </th>
              ))}
            </tr>
          ))}
        </thead>

        <tbody>
          {/* top padding spacer */}
          {paddingTop > 0 && (
            <tr style={{ height: `${paddingTop}px` }}>
              <td />
            </tr>
          )}

          {/* lignes visibles seulement */}
          {virtualRows.map(vRow => {
            const row = table.getRowModel().rows[vRow.index]
            return (
              <tr key={row.id} className="even:bg-gray-50">
                {row.getVisibleCells().map(cell => (
                  <td key={cell.id} className="border px-2 py-1">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            )
          })}

          {/* bottom padding spacer */}
          {paddingBottom > 0 && (
            <tr style={{ height: `${paddingBottom}px` }}>
              <td />
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}
